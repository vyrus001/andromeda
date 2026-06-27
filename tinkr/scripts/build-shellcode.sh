#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    echo "usage: $0 <source.c> <output.bin> [target-triple]" >&2
    echo "  Linux ELF targets:" >&2
    echo "    x86_64-linux-gnu, aarch64-linux-gnu, arm-linux-gnueabihf, i686-linux-gnu" >&2
    echo "  macOS Mach-O targets:" >&2
    echo "    arm64-apple-macos, x86_64-apple-macos" >&2
    exit 2
fi

src=$1
out=$2
target=${3:-}
shellvm_so=${SHELLVM_SO:-/opt/shellvm/shellvm.so}
repo_root="$(cd "$(dirname "$0")/.." && pwd)"
extra_cflags=()
if [ -n "${TINKR_EXTRA_CFLAGS:-}" ]; then
    # Intentional shell-style splitting: callers pass simple compiler flags
    # such as "-I/tailor/include -DNAME=VALUE".
    read -r -a extra_cflags <<< "$TINKR_EXTRA_CFLAGS"
fi

if [ ! -f "$shellvm_so" ]; then
    echo "shellvm.so not found at $shellvm_so" >&2
    exit 1
fi

# ---- target classification ----------------------------------------
target_class=elf            # default; linux & friends
macho_arch=
case "$target" in
    *apple*|*darwin*)
        target_class=macho
        case "$target" in
            arm64-*|aarch64-*) macho_arch=arm64  ;;
            x86_64-*)          macho_arch=x86_64 ;;
            *) echo "unsupported apple target arch: $target" >&2; exit 2 ;;
        esac
        ;;
    *-windows-*|*-win32|*-mingw*)
        target_class=pe
        ;;
esac

clang_target=()
llc_target=()
if [ -n "$target" ]; then
    clang_target=(--target="$target")
    llc_target=(-mtriple="$target")
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

# ---- 1. clang -> bitcode -----------------------------------------
clang "${clang_target[@]}" -I "$repo_root" "${extra_cflags[@]}" \
      -O1 -Xclang -disable-llvm-passes \
      -fno-stack-protector -fno-discard-value-names \
      -fno-unwind-tables -fno-asynchronous-unwind-tables \
      -emit-llvm -c -o "$tmp/in.bc" "$src"

# ---- 2. opt + SheLLVM passes -------------------------------------
opt --load-pass-plugin="$shellvm_so" \
    --passes='always-inline,shellvm-prepare,shellvm-flatten,shellvm-global2stack,sroa,instcombine,mem2reg,globaldce,lowerswitch,shellvm-postcheck' \
    -o "$tmp/out.bc" "$tmp/in.bc"

# ---- 3. llc -> object --------------------------------------------
llc "${llc_target[@]}" -relocation-model=pic -filetype=obj \
    -o "$tmp/out.o" "$tmp/out.bc"

# ---- 4. link + extract -------------------------------------------
case "$target_class" in
    elf)
        # ELF: linker script concatenates .text + .rodata at VMA 0 into
        # one .blob section, all relocations resolved.
        ld.lld -static -nostdlib --no-dynamic-linker \
            -T "$(dirname "$0")/blob.ld" \
            -o "$tmp/out.elf" "$tmp/out.o"
        llvm-objcopy -O binary --only-section=.blob "$tmp/out.elf" "$out"
        ;;

    macho)
        # Link to resolve any intra-__TEXT relocations (e.g. RIP-relative
        # __text → __literal16 from x86_64 vector-constant materialization).
        # ld64.lld's -static/-no_uuid are unimplemented warnings — ignore.
        ld_out=$(ld64.lld -arch "$macho_arch" \
            -e _entry \
            -platform_version macos 11.0 11.0 \
            -dead_strip \
            -o "$tmp/out.macho" "$tmp/out.o" 2>&1) || {
                echo "ld64.lld failed:" >&2
                echo "$ld_out" >&2
                exit 1
            }

        # Extract the WHOLE __TEXT segment (code + inlined constants).
        # `llvm-objcopy -O binary` writes a truncated Mach-O on Mach-O
        # input, not raw bytes; we have our own parser instead.
        python3 "$(dirname "$0")/../tools/extract-macho-segment.py" \
            "$tmp/out.macho" __TEXT "$out"
        ;;

    pe)
        # PE/COFF: link with lld-link, extract .text + .rdata via the
        # RVA-aware Python tool. We pass /entry:entry — on Win64 the C
        # symbol name has no leading underscore, unlike Win32/Mach-O.
        # /nodefaultlib + /noimplib keep us off the C runtime; our blob
        # imports nothing (the seed provides all externals).
        #
        # /align:0x10 /filealign:0x10 — minimum useful alignment that
        # both lld-link accepts AND that produces a tight blob. Below
        # 0x10 the blob doesn't get smaller (we're at the actual code-
        # size floor) but real PE loaders won't load it. We don't
        # care: extract-pe-sections.py reads raw bytes by section RVA.
        # /merge:.rdata=.text packs read-only data into the code
        # section, eliminating the RVA gap between them.
        # The "/align without /driver" warning from lld-link is benign
        # for our use case (extract & strip the PE wrapper anyway).
        lld_out=$(lld-link \
            "/entry:entry" \
            /nodefaultlib /noimplib \
            /subsystem:console \
            "/align:0x10" "/filealign:0x10" \
            "/merge:.rdata=.text" \
            "/out:$tmp/out.exe" \
            "$tmp/out.o" 2>&1) || {
                echo "lld-link failed:" >&2
                echo "$lld_out" >&2
                exit 1
            }

        python3 "$(dirname "$0")/../tools/extract-pe-sections.py" \
            "$tmp/out.exe" "$out"
        ;;
esac

size=$(stat -c%s "$out")
echo "wrote $out ($size bytes${target:+, target=$target})"

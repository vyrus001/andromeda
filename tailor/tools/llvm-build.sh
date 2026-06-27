#!/usr/bin/env bash
set -euo pipefail

usage() {
    cat >&2 <<'USAGE'
usage: tools/llvm-build.sh <exe|bytecode> <output> [target-triple]

Build modes:
  exe       Build Tailor as a normal native executable/library set with clang.
  bytecode  Use Tinkr's SheLLVM pipeline to emit raw native bytecode only.

Environment:
  TINKR_ROOT   Path to the sibling Tinkr repo or /work inside its container.
               Defaults to /work when present, else ../tinkr.
USAGE
}

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    usage
    exit 2
fi

mode=$1
out=$2
target=${3:-}
tailor_root="$(cd "$(dirname "$0")/.." && pwd)"
tinkr_root=${TINKR_ROOT:-}
if [ -z "$tinkr_root" ]; then
    if [ -d /work/scripts ] && [ -f /work/scripts/build-shellcode.sh ]; then
        tinkr_root=/work
    else
        tinkr_root="$(cd "$tailor_root/../tinkr" 2>/dev/null && pwd || true)"
    fi
fi

case "$mode" in
    exe)
        mkdir -p "$(dirname "$out")"
        tmp=$(mktemp -d)
        trap 'rm -rf "$tmp"' EXIT
        make -C "$tailor_root" \
            TARGET="$target" \
            BUILD_DIR="$tmp/build" \
            BIN_DIR="$tmp/bin" \
            LIB_DIR="$tmp/lib" \
            all
        cp "$tmp/bin/tailor-profile" "$out"
        ;;

    bytecode)
        if [ -z "$tinkr_root" ] || [ ! -x "$tinkr_root/scripts/build-shellcode.sh" ]; then
            echo "Tinkr build-shellcode.sh not found; set TINKR_ROOT" >&2
            exit 1
        fi
        format_cflag=
        case "$target" in
            *apple*|*darwin*) format_cflag="-DTAILOR_BYTECODE_ONLY_MACHO" ;;
            *linux*) format_cflag="-DTAILOR_BYTECODE_ONLY_ELF" ;;
            *-windows-*|*-win32|*-mingw*) format_cflag="-DTAILOR_BYTECODE_ONLY_PE" ;;
        esac
        mkdir -p "$(dirname "$out")"
        TINKR_EXTRA_CFLAGS="-I$tailor_root/include $format_cflag ${TINKR_EXTRA_CFLAGS:-}" \
            "$tinkr_root/scripts/build-shellcode.sh" \
            "$tailor_root/src/bytecode_entry.c" "$out" "$target"
        ;;

    *)
        usage
        exit 2
        ;;
esac

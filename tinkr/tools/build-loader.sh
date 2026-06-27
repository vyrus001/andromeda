#!/usr/bin/env bash
set -euo pipefail

# Build the test loader, optionally cross-compiled. Uses lld to avoid
# needing gnu binutils for each target arch — multiarch libc6-dev gives
# us the headers and libraries, clang+lld does the rest.

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ]; then
    echo "usage: $0 <output-path> [target-triple]" >&2
    echo "  target-triple defaults to host" >&2
    exit 2
fi

out=$1
target=${2:-}
repo_root="$(cd "$(dirname "$0")/.." && pwd)"

flags=(-O2)
if [ -n "$target" ]; then
    flags+=(--target="$target" -fuse-ld=lld)
fi
# The loader assigns real glibc functions (e.g. `lseek`) into seeds.h
# function-pointer fields that use portable types (`long long off_t`
# vs glibc's `__off_t`). The ABIs match (size + sign); demote clang's
# strict pointer-type check so the loader compiles.
flags+=(-Wno-incompatible-function-pointer-types -Wno-incompatible-pointer-types)
# Need -ldl for dlopen/dlsym/dlclose populated into linux_libc.
flags+=(-ldl)

clang "${flags[@]}" -I "$repo_root" -o "$out" "$repo_root/tools/loader.c"
echo "wrote $out${target:+ (target=$target)}"

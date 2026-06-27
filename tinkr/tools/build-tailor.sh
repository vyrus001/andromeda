#!/usr/bin/env bash
set -euo pipefail

if [ "$#" -lt 2 ] || [ "$#" -gt 3 ]; then
    cat >&2 <<'USAGE'
usage: tools/build-tailor.sh <exe|bytecode> <output> [target-triple]

Modes:
  exe       Build Tailor as a normal executable using the container LLVM toolchain.
  bytecode  Build Tailor's bytecode entry through Tinkr's SheLLVM pipeline.

TAILOR_ROOT defaults to /tailor, which docker-compose mounts from ../tailor.
USAGE
    exit 2
fi

tailor_root=${TAILOR_ROOT:-/tailor}
if [ ! -x "$tailor_root/tools/llvm-build.sh" ]; then
    echo "Tailor compiler wrapper not found at $tailor_root/tools/llvm-build.sh" >&2
    exit 1
fi

export TINKR_ROOT=${TINKR_ROOT:-/work}
exec "$tailor_root/tools/llvm-build.sh" "$@"

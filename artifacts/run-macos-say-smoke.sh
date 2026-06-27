#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
exec ./tailor/bin/tailor-run ./artifacts/macos-say-smoke-arm64.bin --verbose

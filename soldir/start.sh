#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

has_uv=0
if command -v uv >/dev/null 2>&1; then
  has_uv=1
fi

if [ ! -d ".venv" ] && [[ "$has_uv" == "1" ]]; then
  uv sync
elif [ ! -d ".venv" ] && ! python3 -c 'import soldir' >/dev/null 2>&1; then
  echo "uv is required unless Soldir is already installed in this Python environment." >&2
  exit 1
fi

if [ ! -d "node_modules" ]; then
  npm install
fi

test_mode=0
case "${SOLDIR_TEST_MODE:-}" in
  1|true|TRUE|yes|YES|on|ON) test_mode=1 ;;
esac
for arg in "$@"; do
  if [[ "$arg" == "--test-mode" ]]; then
    test_mode=1
  fi
done

if [[ "$test_mode" != "1" ]]; then
  echo "Soldir test mode is off. Start it with: ./start.sh --test-mode"
fi

if [[ "$has_uv" == "1" ]]; then
  exec uv run soldir "$@"
fi

exec python3 -m soldir.server "$@"

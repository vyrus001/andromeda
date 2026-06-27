#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

pid_file=.run/tailor-listener.pid
if [[ -f "$pid_file" ]]; then
  pid=$(cat "$pid_file")
  if kill -0 "$pid" >/dev/null 2>&1; then
    kill "$pid"
    echo "Stopped Tailor listener PID $pid"
  fi
  rm -f "$pid_file"
fi

docker compose down

#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

test_mode=0
listener=1
build=1
for arg in "$@"; do
  case "$arg" in
    --test-mode) test_mode=1 ;;
    --no-listener) listener=0 ;;
    --no-build) build=0 ;;
    *)
      echo "usage: ./start.sh [--test-mode] [--no-listener] [--no-build]" >&2
      exit 2
      ;;
  esac
done

if [[ "$test_mode" == "1" ]]; then
  export SOLDIR_TEST_MODE=1
else
  unset SOLDIR_TEST_MODE || true
fi

has_provider_setting() {
  local name="$1"
  if [[ -n "${!name:-}" ]]; then
    return 0
  fi
  if [[ -f .env ]] && grep -Eq "^[[:space:]]*(export[[:space:]]+)?${name}=[^#[:space:]]+" .env; then
    return 0
  fi
  return 1
}

configured_llm_providers=()
if has_provider_setting XAI_API_KEY; then
  configured_llm_providers+=("grok/xAI")
fi
if has_provider_setting OPENAI_API_KEY; then
  configured_llm_providers+=("OpenAI")
fi
if has_provider_setting ANTHROPIC_API_KEY; then
  configured_llm_providers+=("Claude")
fi
if has_provider_setting OLLAMA_BASE_URL; then
  configured_llm_providers+=("Ollama")
fi

if (( ${#configured_llm_providers[@]} )); then
  provider_list=$(IFS=,; echo "${configured_llm_providers[*]}")
  echo "Passing LLM provider environment into Soldir: ${provider_list}"
else
  echo "No LLM provider environment found. Export XAI_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY, or OLLAMA_BASE_URL before ./start.sh to enable chat providers."
fi

if [[ "$build" == "1" ]]; then
  docker compose up -d --build soldir
else
  docker compose up -d soldir
fi

for _ in {1..30}; do
  if curl -fsS http://127.0.0.1:8765/health >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl -fsS http://127.0.0.1:8765/health >/dev/null

if [[ "$listener" == "1" ]]; then
  make -C tailor >/dev/null
  mkdir -p .run logs
  pid_file=.run/tailor-listener.pid
  if [[ -f "$pid_file" ]] && kill -0 "$(cat "$pid_file")" >/dev/null 2>&1; then
    echo "Tailor listener already running as PID $(cat "$pid_file")"
  else
    nohup env PYTHONUNBUFFERED=1 python3 tailor/tools/tailor-listen.py \
      --soldir-url http://127.0.0.1:8765 \
      --verbose \
      < /dev/null > logs/tailor-listener.log 2>&1 &
    echo $! > "$pid_file"
    echo "Tailor listener started as PID $(cat "$pid_file")"
  fi
fi

echo "Andromeda is running at http://127.0.0.1:8765"
echo "Stop it with ./stop.sh"

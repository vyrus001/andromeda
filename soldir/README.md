# Soldir

Soldir is the web and orchestration layer for Andromeda. It provides the realtime D3 node graph, GraphQLite-backed check-in storage, browser chat surface, Tailor WebSocket broker, and Tinkr bytecode job endpoints.

## Run From Andromeda

Use the top-level scripts whenever possible:

```sh
cd /Users/carl/personal/andromeda
./start.sh
./stop.sh
```

## Run Soldir Alone

```sh
cd /Users/carl/personal/andromeda/soldir
./start.sh
```

The app listens on `http://127.0.0.1:8765` by default.

## Container

The top-level compose file is the authoritative container entrypoint. It builds Soldir with sibling contexts:

- `../tinkr` copied into the image as `/tinkr`
- `../tailor` copied into the image as `/tailor`

Soldir still keeps a local `docker-compose.yml` for isolated development, but the Andromeda root is the preferred workflow.

The container inherits LLM provider configuration from the shell or Compose `.env` used at startup. The top-level `./start.sh` reports configured provider names only and does not print API key values.

## Tailor Check-In Flow

A Tailor host listener posts to `/api/checkins`. Soldir returns a Tailor-specific WebSocket URL such as `/ws/tailor/<instance_id>`. Jobs are delivered over that socket as `execute_bytecode` messages with base64 bytecode. Results come back as `execution_result`.

## macOS Say Smoke Job

```sh
curl -fsS -X POST http://127.0.0.1:8765/api/jobs/macos-say-smoke \
  -H 'content-type: application/json' \
  -d '{"target_triple":"arm64-apple-macos","message":"smoke test of pwnage"}'
```

The job builds a deterministic context-aware Tinkr blob that resolves `execve` from Tailor's live resolver context and runs `/usr/bin/say` on the host.

## Chat Providers

The browser selects a provider/model and sends the message over Soldir's UI WebSocket. API keys stay server-side and are passed into the container from the startup environment.

| Provider | Environment |
| --- | --- |
| Grok/xAI | `XAI_API_KEY`, optional `XAI_BASE_URL`, `XAI_MODEL` |
| OpenAI | `OPENAI_API_KEY`, optional `OPENAI_BASE_URL`, `OPENAI_MODEL` |
| Claude | `ANTHROPIC_API_KEY`, optional `ANTHROPIC_BASE_URL`, `ANTHROPIC_MODEL` |
| Ollama | optional `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |

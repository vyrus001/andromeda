# Andromeda Demo

This demo shows the local Andromeda workflow without UX/test graph data. Soldir starts with an empty graph, a Tailor instance checks in from the host workstation, and Soldir uses Tinkr to generate and deliver a macOS `say` payload to that specific Tailor instance.

## Prerequisites

- Docker is running.
- The host workstation is macOS arm64 with `/usr/bin/say` available.
- You are running this only on a workstation you own or are explicitly authorized to test.

## 1. Start Andromeda With A Blank Graph

Start only the Soldir container. Do not use `--test-mode`, and do not start the Tailor listener yet.

```sh
cd /Users/carl/personal/andromeda
./stop.sh
docker compose down -v
./start.sh --no-listener
```

`docker compose down -v` clears prior check-in data from the Soldir volume so the graph starts empty for the demo.

Open the interface:

```text
http://127.0.0.1:8765
```

The graph should be blank because no UX/test graph is running and no Tailor instance has checked in yet. You can confirm the server state with:

```sh
curl -fsS http://127.0.0.1:8765/health
```

Expected shape:

```json
{"ok":true,"nodes":0,"tailor_clients":[]}
```

## 2. Start A Tailor Instance On The Host

In a second terminal, start the host-side Tailor listener. This command builds the local Tailor tools if needed, posts a check-in/profile to Soldir, and then keeps the returned Tailor WebSocket open for bytecode jobs.

```sh
cd /Users/carl/personal/andromeda
make -C tailor
python3 tailor/tools/tailor-listen.py \
  --soldir-url http://127.0.0.1:8765 \
  --instance-id local-macos-arm64 \
  --verbose
```

The listener should print a WebSocket URL similar to:

```text
[tailor-listen] websocket ws://127.0.0.1:8765/ws/tailor/local-macos-arm64
```

Refresh or watch the Soldir interface. The Tailor instance should appear as a node in the graph. Confirm by checking health again:

```sh
curl -fsS http://127.0.0.1:8765/health
```

Expected shape:

```json
{"ok":true,"nodes":1,"tailor_clients":["local-macos-arm64"]}
```

A raw `curl` POST to `/api/checkins` can create a graph node for API testing, but it will not execute payloads unless a Tailor listener is also connected to the returned WebSocket.

## 3. Tell Soldir To Run A Payload On That Tailor Instance

For the deterministic demo path, use the Soldir job API to ask for a macOS `say` payload and target the checked-in Tailor instance explicitly:

```sh
curl -fsS -X POST http://127.0.0.1:8765/api/jobs/macos-say-smoke \
  -H 'content-type: application/json' \
  -d '{
    "target_triple": "arm64-apple-macos",
    "target_instance_id": "local-macos-arm64",
    "message": "smoke test of pwnage"
  }'
```

Soldir then performs the workflow:

1. Selects `local-macos-arm64` as the target Tailor instance.
2. Uses Tinkr to generate a context-aware `arm64-apple-macos` bytecode blob.
3. Sends an `execute_bytecode` message over `/ws/tailor/local-macos-arm64`.
4. Tailor writes the blob to a local temp file and executes it with `tailor/bin/tailor-run`.
5. The payload resolves host functions through the Tailor runtime context and runs `/usr/bin/say` with the requested message.
6. Tailor sends an `execution_result` message back to Soldir.

The workstation should audibly say:

```text
smoke test of pwnage
```

The equivalent operator instruction in the Soldir chat is:

```text
Tell local-macos-arm64 to say "smoke test of pwnage" using the macOS say payload.
```

## 4. Inspect Job Results

List jobs:

```sh
curl -fsS http://127.0.0.1:8765/api/jobs
```

A completed job should have this shape:

```json
{
  "status": "completed",
  "target_instance_id": "local-macos-arm64",
  "target_triple": "arm64-apple-macos",
  "returncode": 0
}
```

The Tailor listener terminal should also show the incoming `execute_bytecode` message and `tailor-run` context output.

## 5. Stop The Demo

Stop the foreground Tailor listener with `Ctrl-C`, then stop Soldir:

```sh
cd /Users/carl/personal/andromeda
./stop.sh
```

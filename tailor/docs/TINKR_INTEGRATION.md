# Tinkr Integration

Tailor and Tinkr are linked by two contracts:

1. Tinkr can compile Tailor through its Dockerized LLVM + SheLLVM toolchain.
2. Tailor can supply a live resolver context to Tinkr-generated blobs.

The expected local layout is:

```text
~/personal/andromeda/tailor
~/personal/andromeda/tinkr
```

Tinkr's `docker-compose.yml` mounts `../tailor` at `/tailor`.

## Verify the Container Toolchain

```bash
cd ~/personal/andromeda/tinkr
docker compose build dev agent

docker compose run --rm dev bash -lc '
  command -v clang
  command -v opt
  command -v llc
  command -v llvm-ar
  printf "TAILOR_ROOT=%s\n" "${TAILOR_ROOT:-unset}"
  test -d /tailor && printf "tailor-mounted\n"
'
```

Expected:

- LLVM tools are present under `/usr/bin`.
- `TAILOR_ROOT=/tailor`.
- `/tailor` exists.

## Build Tailor from Tinkr

Standard executable mode:

```bash
docker compose run --rm dev \
  tools/build-tailor.sh exe /work/tailor-profile-container

docker compose run --rm dev \
  /work/tailor-profile-container --symbol write --format tsv
```

Raw bytecode mode:

```bash
docker compose run --rm dev \
  tools/build-tailor.sh bytecode /work/tailor-bytecode-entry.bin \
  arm64-apple-macos
```

The executable mode builds in a temporary directory inside the container and
copies only the requested output. It should not overwrite host `bin/`, `build/`,
or `lib/` artifacts under `/tailor`.

## Generate a Tinkr Symbol List

Tinkr skills define the indirect-call functions the agent might need. Tailor can
extract those names without depending on PyYAML:

```bash
python3 ~/personal/andromeda/tailor/tools/tinkr-symbols.py ~/personal/andromeda/tinkr/skills \
  > ~/personal/andromeda/tinkr/tailor-symbols.txt
```

Generate a host profile limited to those exact names:

```bash
~/personal/andromeda/tailor/bin/tailor-profile \
  --symbols ~/personal/andromeda/tinkr/tailor-symbols.txt \
  > ~/personal/andromeda/tinkr/tailor-profile.json
```

The profile lives in Tinkr's worktree so containers can see it at
`/work/tailor-profile.json`.

## Deterministic Context Fixture

The fixture at `~/personal/andromeda/tinkr/examples/context_write/hello.c` avoids the LLM
path and directly tests the runtime contract:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev \
  scripts/build-shellcode.sh examples/context_write/hello.c \
  /work/context-write-fixture.bin arm64-apple-macos

~/personal/andromeda/tailor/bin/tailor-run \
  ~/personal/andromeda/tinkr/context-write-fixture.bin --verbose
```

Expected:

```text
[tailor-run] context: <module-count> modules, <function-count> functions
[tailor-run] entry returned 0
context hi
```

This proves:

- Tinkr can build a context-aware raw blob.
- Tailor can build `struct tinkr_context` from the live process.
- The blob can resolve `write` from the context and call it.

## Agent Context Mode

The agent accepts a Tailor JSON or TSV profile:

```bash
docker compose run --rm agent \
  --context-profile /work/tailor-profile.json \
  --skills macos/libSystem/write \
  --target arm64-apple-macos \
  -o /work/context-write-agent.bin \
  "write 'hi' to stdout using the supplied resolver context"
```

When `--context-profile` is present, generated code should:

- Include both `seeds.h` and `tinkr_context.h`.
- Cast `args` to `struct tinkr_context *`.
- Resolve listed indirect-call functions with
  `tinkr_context_resolve(ctx, MODULE_HASH, FUNCTION_HASH)`.
- Check resolved pointers for null before calling.

The agent path sends selected profile metadata to the configured LLM provider.
For private host profiles, run the deterministic fixture or explicitly approve
the external API call.

## Local Agent Parser Check

This verifies Docker-side parsing without calling the external API:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm --entrypoint python3 agent -c '
import sys
sys.path.insert(0, "/work/agent")
import agent
entries = agent.load_context_profile("/work/tailor-profile.json")
block = agent.build_context_block(entries, ["macos/libSystem/write"])
print(f"entries={len(entries)}")
print(block)
'
```

The `write` row should include:

```text
function_hash = 0xb93a12b0d06caefc
```

On the verified macOS arm64 host, the matched module was
`libsystem_kernel.dylib` with module hash `0xfe69aae3cc4a86ab` and offset
`0x482c`.

## Cross-Target Build Checks

Context fixture:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev bash -lc '
set -e
for target in \
  x86_64-linux-gnu \
  aarch64-linux-gnu \
  arm-linux-gnueabihf \
  i686-linux-gnu \
  arm64-apple-macos \
  x86_64-apple-macos \
  x86_64-pc-windows-msvc
do
  scripts/build-shellcode.sh examples/context_write/hello.c \
    "/work/context-write-${target}.bin" "$target"
done
'
```

Tailor bytecode entry:

```bash
docker compose run --rm dev bash -lc '
set -e
for target in \
  x86_64-linux-gnu \
  aarch64-linux-gnu \
  arm-linux-gnueabihf \
  i686-linux-gnu \
  arm64-apple-macos \
  x86_64-apple-macos \
  x86_64-pc-windows-msvc
do
  tools/build-tailor.sh bytecode \
    "/work/tailor-bytecode-entry-${target}.bin" "$target"
done
'
```

## Troubleshooting

`LLVM ERROR: More than one function in module!`

- SheLLVM's postcheck saw helper functions after optimization.
- Ensure Tinkr's `scripts/build-shellcode.sh` runs `always-inline` before the
  SheLLVM passes.
- Ensure Tailor bytecode helpers are `TAILOR_INLINE` and recursive code paths
  have been removed.

`undefined symbol: __chkstk` for Windows bytecode

- The Windows blob has a stack frame large enough to need compiler runtime
  support.
- Ensure `tools/llvm-build.sh` passes `TAILOR_BYTECODE_ONLY_PE` for Windows
  triples so the ELF and Mach-O parser state is not compiled into PE blobs.

`.env not found`

- Tinkr's compose file should mark `.env` as optional for non-API commands.
- API-backed agent generation still requires `ANTHROPIC_API_KEY`.

Host Tailor binary becomes Linux after Docker tests

- Executable mode should pass temporary `BUILD_DIR`, `BIN_DIR`, and `LIB_DIR`
  values to Tailor's Makefile. The host `bin/tailor-profile` should remain a
  Mach-O executable on macOS.

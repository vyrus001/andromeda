# Testing

This file captures the repeatable test matrix used for the Tailor/Tinkr
integration. Commands assume:

```text
~/personal/andromeda/tailor
~/personal/andromeda/tinkr
```

## Local Tailor Tests

```bash
cd ~/personal/andromeda/tailor
make
make test
```

`make test` currently checks JSON, TSV, and exact-symbol filtering against the
current host process.

Additional smoke:

```bash
bin/tailor-profile --symbol write --format json
bin/tailor-profile --symbols tests/symbols.txt --format tsv
bin/tailor-run --help
```

## Docker Toolchain Verification

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

## Tailor Executable Mode in Docker

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev \
  tools/build-tailor.sh exe /work/tailor-profile-container

docker compose run --rm dev \
  /work/tailor-profile-container --symbol write --format tsv
```

Expected result: TSV rows from the container runtime, including a `write` row
from `libc.so.6`.

Check that the host binary was not clobbered:

```bash
file ~/personal/andromeda/tailor/bin/tailor-profile
```

On macOS arm64 this should still report `Mach-O 64-bit executable arm64`.

## Tailor Bytecode Mode in Docker

Single target:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev \
  tools/build-tailor.sh bytecode /work/tailor-bytecode-entry.bin \
  arm64-apple-macos
```

All Tinkr-supported targets:

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

Expected result: each target writes a `.bin` file under the Tinkr worktree.

## Generate a Host Resolver Profile

```bash
python3 ~/personal/andromeda/tailor/tools/tinkr-symbols.py ~/personal/andromeda/tinkr/skills \
  > ~/personal/andromeda/tinkr/tailor-symbols.txt

~/personal/andromeda/tailor/bin/tailor-profile \
  --symbols ~/personal/andromeda/tinkr/tailor-symbols.txt \
  > ~/personal/andromeda/tinkr/tailor-profile.json
```

Sanity check for macOS:

```bash
~/personal/andromeda/tailor/bin/tailor-profile \
  --symbols ~/personal/andromeda/tinkr/tailor-symbols.txt \
  --symbol write \
  --format json
```

Expected `function_hash` for normalized `write`:

```text
0xb93a12b0d06caefc
```

## Deterministic End-to-End Loop

Compile:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev \
  scripts/build-shellcode.sh examples/context_write/hello.c \
  /work/context-write-fixture.bin arm64-apple-macos
```

Run:

```bash
~/personal/andromeda/tailor/bin/tailor-run \
  ~/personal/andromeda/tinkr/context-write-fixture.bin --verbose
```

Expected:

```text
[tailor-run] context: <module-count> modules, <function-count> functions
[tailor-run] entry returned 0
context hi
```

This is the main local proof that Tailor and Tinkr agree on the resolver
context ABI.

## Fixture Cross-Target Compile

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

This only proves compilation for non-host targets. Runtime verification still
requires a compatible loader and host or emulator.

## Agent Context Parser Without API

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

Expected: the generated context block contains a `write` row with the known
FNV-1a function hash.

## API-Backed Agent Test

This test sends selected resolver-profile metadata to the configured external
LLM provider. Run it only when that is acceptable for the profile being used.

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm agent \
  --context-profile /work/tailor-profile.json \
  --skills macos/libSystem/write \
  --target arm64-apple-macos \
  --keep-source \
  --show-source \
  -o /work/context-write-agent.bin \
  "write 'agent context hi\n' to stdout using the supplied resolver context"

~/personal/andromeda/tailor/bin/tailor-run \
  ~/personal/andromeda/tinkr/context-write-agent.bin --verbose
```

Expected runtime output:

```text
agent context hi
```

## Soldir Integration Readiness

Before the Tailor + Tinkr + Soldir glue test, confirm:

- Tailor can generate the target runtime profile.
- Tinkr can compile a context-aware blob for the target triple.
- The blob accepts `args` as `struct tinkr_context *`.
- Soldir's side of the contract states whether it receives raw blobs, profile
  JSON, live `struct tinkr_context`, or all three.
- The final runner validates ABI versions before executing a blob.

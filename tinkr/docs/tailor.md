# Tailor Integration

Tinkr integrates with the sibling Tailor project in two directions:

1. Tinkr's Docker image is the standardized LLVM + SheLLVM compiler for Tailor.
2. Tinkr can generate blobs that resolve functions from a Tailor runtime
   profile instead of depending only on `struct seeds`.

Expected local layout:

```text
~/personal/andromeda/tinkr
~/personal/andromeda/tailor
```

`docker-compose.yml` mounts Tailor into the dev and agent containers:

```text
../tailor:/tailor
```

Inside the container, `TAILOR_ROOT=/tailor`.

## Compiler Modes

The Tinkr wrapper is `tools/build-tailor.sh`:

```bash
docker compose run --rm dev \
  tools/build-tailor.sh exe /work/tailor-profile-container

docker compose run --rm dev \
  tools/build-tailor.sh bytecode /work/tailor-bytecode-entry.bin \
  arm64-apple-macos
```

Modes:

- `exe` builds Tailor as a standard executable/library set using container
  LLVM and copies `tailor-profile` to the requested output path.
- `bytecode` compiles Tailor's bytecode profiler entry through the same
  SheLLVM pipeline used for ordinary Tinkr blobs.

The Tailor wrapper builds executable mode in a temporary directory so Docker
tests do not overwrite host `~/personal/andromeda/tailor/bin` artifacts.

## Verify the Docker Toolchain

```bash
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

- `clang`, `opt`, `llc`, and `llvm-ar` are available.
- `TAILOR_ROOT=/tailor`.
- `/tailor` exists.

## Generate a Tailor Profile for Agent Context

The Tailor helper extracts indirect-call names from Tinkr skills:

```bash
python3 ~/personal/andromeda/tailor/tools/tinkr-symbols.py ~/personal/andromeda/tinkr/skills \
  > ~/personal/andromeda/tinkr/tailor-symbols.txt
```

Then Tailor profiles the current host process:

```bash
~/personal/andromeda/tailor/bin/tailor-profile \
  --symbols ~/personal/andromeda/tinkr/tailor-symbols.txt \
  > ~/personal/andromeda/tinkr/tailor-profile.json
```

The profile is written into the Tinkr worktree so Docker sees it as
`/work/tailor-profile.json`.

## Context-Aware Codegen

The agent accepts:

```text
--context-profile /work/tailor-profile.json
```

When present, the codegen prompt includes matched function hashes and offsets
for selected indirect-call skills. Generated source may include
`tinkr_context.h`, cast `args` to `struct tinkr_context *`, resolve pointers by
hash, and call the resolved functions.

Example:

```bash
docker compose run --rm agent \
  --context-profile /work/tailor-profile.json \
  --skills macos/libSystem/write \
  --target arm64-apple-macos \
  -o /work/context-write-agent.bin \
  "write 'hi' to stdout using the supplied resolver context"
```

This path sends selected resolver-profile data to the configured LLM provider.
Use it only when that is acceptable for the profile. For local verification,
use the deterministic fixture below.

## Deterministic Fixture

`examples/context_write/hello.c` is a hand-written context-aware blob. It
resolves `write` from `args` as `struct tinkr_context *` and writes
`context hi`.

```bash
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

## Cross-Target Checks

Context fixture:

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

## ABI Contract

The runtime entrypoint does not change:

```c
int entry(struct seeds *s, void *args, size_t args_len);
```

For context-aware blobs:

- `args` points to `struct tinkr_context`.
- `args_len` is at least `sizeof(struct tinkr_context)`.
- `tinkr_context_resolve(ctx, module_hash, function_hash)` returns
  `module_base + offset`.

The header `tinkr_context.h` is mirrored from Tailor. Keep both copies in sync
when `TINKR_CONTEXT_ABI_VERSION` or struct layout changes.

## Soldir Handoff

Soldir should not need to know Tinkr's temporary build paths or Tailor's
internal allocation layout. The portable handoff is:

- Tailor profile JSON or TSV for build-time planning.
- Raw Tinkr blob bytes for the selected target triple.
- Live `struct tinkr_context` at runtime.
- Integer blob return code and any output capture defined by the runner.

The Tailor side tracks the detailed handoff checklist in
`~/personal/andromeda/tailor/docs/SOLDIR_HANDOFF.md`.

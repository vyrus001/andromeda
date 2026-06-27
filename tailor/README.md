# Tailor

Tailor is the Andromeda host-side directory for the Tailor runtime. Tailor profiles function addresses that are already visible inside the process
that runs it. It emits stable function-name hash and module-relative offset
pairs so Tinkr can generate position-independent bytecode for that runtime
context without baking absolute addresses into the blob.

Tailor is part of the Andromeda workspace:

```text
~/personal/andromeda/
  tailor/   process-local symbol profiler and Tinkr context runner
  tinkr/    LLVM + SheLLVM blob compiler and agent
  soldir/   graph UI, broker, and orchestration service
```

Tailor does not inspect unrelated processes. The default tools profile and run
inside their own current process. Embedding hosts can link the library or use the
startup profiler to collect the same kind of manifest at process initialization.

## Current Status

- Host profiling works on macOS and Linux through platform loaders.
- Bytecode profiling builds for ELF, Mach-O, and PE targets through Tinkr's
  Dockerized LLVM + SheLLVM toolchain.
- The shared Tinkr resolver ABI is implemented in
  `include/tailor/tinkr_context.h` and mirrored in Tinkr.
- `bin/tailor-run` can load a Tinkr raw blob, build a live resolver context,
  and pass that context as `args` to the normal Tinkr entrypoint.
- The local deterministic loop has been verified: Tailor profile -> Tinkr
  bytecode -> Tailor runtime context -> resolved `write` call.
- The API-backed agent path is documented but requires explicit approval before
  sending host-derived resolver metadata to an external LLM provider.

## Quick Start

Build Tailor locally:

```bash
make
make test
```

Generate a profile for the current process:

```bash
bin/tailor-profile --symbol write --format json
bin/tailor-profile --all-modules --format tsv
bin/tailor-profile --symbols tests/symbols.txt --addresses
```

Build and run the deterministic Tinkr context fixture:

```bash
cd ~/personal/andromeda/tinkr
docker compose build dev agent
docker compose run --rm dev \
  scripts/build-shellcode.sh examples/context_write/hello.c \
  /work/context-write-fixture.bin arm64-apple-macos

~/personal/andromeda/tailor/bin/tailor-run \
  ~/personal/andromeda/tinkr/context-write-fixture.bin --verbose
```

Expected runtime shape:

```text
[tailor-run] context: <module-count> modules, <function-count> functions
[tailor-run] entry returned 0
context hi
```

## Build Outputs

`make` builds:

- `bin/tailor-profile` - CLI manifest generator.
- `bin/tailor-run` - local blob runner that supplies `struct tinkr_context`.
- `lib/libtailor_profile.a` - embeddable profiling API.
- `lib/libtailor_autoprofile.dylib` on macOS or `.so` on Linux - constructor
  profiler enabled by environment variables.

Tailor defaults to clang and prefers LLVM binutils. The Makefile supports
isolated output directories through `BUILD_DIR`, `BIN_DIR`, and `LIB_DIR` so
container builds do not clobber host binaries.

## Tinkr Compiler Modes

Tinkr mounts the Tailor directory at `/tailor` and exposes `tools/build-tailor.sh` from the
Tinkr worktree:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev \
  tools/build-tailor.sh exe /work/tailor-profile-container

docker compose run --rm dev \
  tools/build-tailor.sh bytecode /work/tailor-bytecode-entry.bin \
  arm64-apple-macos
```

Modes:

- `exe` builds Tailor as a normal executable/library set with the container
  LLVM toolchain, then copies `tailor-profile` to the requested output.
- `bytecode` compiles `src/bytecode_entry.c` through Tinkr's SheLLVM pipeline
  and emits raw native bytes only.

## CLI Reference

```text
usage: tailor-profile [options]

Options:
  --format json|tsv        Output format (default: json)
  --system-only            Keep system libraries only
  --all-modules            Include non-system images (default)
  --module TEXT            Keep module path/name containing TEXT
  --symbol TEXT            Keep symbol name containing TEXT
  --symbols FILE           Keep exact symbol names listed in FILE
  --addresses              Include observed absolute addresses
  --no-names               Omit cleartext names from JSON/TSV
  --raw-symbol-names       Disable platform symbol normalization
  --help                   Show this help
```

`tailor-run`:

```text
usage: tailor-run <blob.bin> [options]

Options:
  --system-only     Build context from system libraries only
  --raw-symbols     Disable platform symbol normalization
  --verbose         Print context sizes before executing
  --help            Show this help
```

`tools/tailor-listen.py` checks in with Soldir, opens the returned Tailor
WebSocket, and executes delivered Tinkr bytecode through `bin/tailor-run`:

```bash
tools/tailor-listen.py --soldir-url http://127.0.0.1:8765 --verbose
```

Use `--once` for one-shot smoke tests.

## Profile Schema

JSON output uses a compact v1 schema:

```json
{
  "format": "tailor.symbol-profile.v1",
  "hash": "fnv1a64-case-sensitive",
  "offset_base": "loaded-module-image-base",
  "entries": [
    {
      "module_hash": "0xfe69aae3cc4a86ab",
      "function_hash": "0xb93a12b0d06caefc",
      "offset": "0x482c",
      "module": "libsystem_kernel.dylib",
      "path": "/usr/lib/system/libsystem_kernel.dylib",
      "name": "write"
    }
  ]
}
```

Hashing is 64-bit FNV-1a over the exact normalized name. On Mach-O, Tailor
strips one leading C symbol underscore before hashing unless
`--raw-symbol-names` is set. `module_hash` is computed over the module basename.

## Documentation

- [Architecture](docs/ARCHITECTURE.md) - data model, platform parsers, ABI
  contracts, and invariants.
- [Tinkr Integration](docs/TINKR_INTEGRATION.md) - Docker compiler modes,
  context-aware blob generation, and troubleshooting.
- [Testing](docs/TESTING.md) - reproducible local and Docker verification
  commands.
- [Soldir Handoff](docs/SOLDIR_HANDOFF.md) - explicit contract for the final
  Tailor + Tinkr + Soldir glue step.

## Authorized Use

This is compiler, loader, and runtime-introspection infrastructure. Use it only
in processes, environments, and systems you own or are explicitly authorized to
test.

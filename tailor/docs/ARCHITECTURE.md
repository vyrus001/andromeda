# Tailor Architecture

Tailor exists to turn process-local native symbols into a data structure that a
Tinkr blob can use at runtime. The stable part is not the address. The stable
part is:

```text
module basename hash + function name hash + module-relative offset
```

The loaded module base is discovered inside the process that runs the blob.
The final address is reconstructed as:

```c
void *address = (char *)module_base + offset;
```

## Goals

- Profile as many exported native functions as possible from the current
  runtime context.
- Emit compact hash/offset pairs that do not depend on absolute ASLR addresses.
- Keep the blob ABI compatible with Tinkr's existing
  `entry(struct seeds *s, void *args, size_t args_len)` signature.
- Support every target class Tinkr builds today: ELF, Mach-O, and PE/COFF.
- Allow two build modes: standard executable and raw native bytecode.

## Non-Goals

- Tailor does not attach to or inspect unrelated processes.
- Tailor does not resolve debug symbols or private non-exported functions from
  symbol servers.
- Tailor does not make bytecode generation decisions. Tinkr owns codegen.
- Tailor does not own the final orchestration layer. Soldir is expected to
  provide that glue once its interface is ready.

## Data Model

Every profile entry describes one function export:

| Field | Meaning |
| --- | --- |
| `module_hash` | FNV-1a 64 hash of the module basename, for example `libsystem_kernel.dylib` or `libc.so.6`. |
| `function_hash` | FNV-1a 64 hash of the normalized function name. |
| `offset` | Function address minus loaded module base. |
| `module` | Optional cleartext module basename for diagnostics and agent prompting. |
| `path` | Optional cleartext loaded image path. |
| `name` | Optional cleartext normalized symbol name. |
| `address` | Optional absolute observed address, emitted only for debugging. |
| `module_base` | Optional absolute observed module base, emitted only for debugging. |

Hashing is case-sensitive 64-bit FNV-1a. There is no terminator byte and no case
folding. Mach-O C symbols normally begin with `_`; Tailor strips one leading
underscore before hashing unless raw symbol mode is requested.

## Runtime Views

Tailor has four ways to use the same core concepts.

### 1. CLI Profiler

`bin/tailor-profile` profiles the process that runs it and writes JSON or TSV.
This is the fastest way to produce an agent prompt context or inspect the
current host.

### 2. Library Profiler

`lib/libtailor_profile.a` exposes:

```c
int tailor_profile_collect(tailor_profile *profile, unsigned flags);
int tailor_profile_write_json(FILE *stream,
                              const tailor_profile *profile,
                              unsigned write_flags);
int tailor_profile_write_tsv(FILE *stream,
                             const tailor_profile *profile,
                             unsigned write_flags);
```

Embedding hosts can collect the same profile without shelling out.

### 3. Startup Profiler

`lib/libtailor_autoprofile.dylib` or `.so` writes a profile from a constructor
when `TAILOR_PROFILE_OUT` is set:

```bash
TAILOR_PROFILE_OUT=/tmp/tailor-profile.json your-host-program
```

Optional environment variables:

- `TAILOR_PROFILE_SYSTEM_ONLY=1`
- `TAILOR_PROFILE_ADDRESSES=1`
- `TAILOR_PROFILE_NO_NAMES=1`
- `TAILOR_PROFILE_RAW_SYMBOL_NAMES=1`

### 4. Tinkr Context Runner

`bin/tailor-run` builds a live `struct tinkr_context`, maps a raw Tinkr blob,
and calls byte 0 as:

```c
int entry(struct seeds *s, void *args, size_t args_len);
```

`s` is currently passed through as a placeholder. `args` points to a
`struct tinkr_context`, and `args_len` is `sizeof(struct tinkr_context)`.

## Tinkr Resolver ABI

The shared resolver ABI lives in `include/tailor/tinkr_context.h` and is copied
into Tinkr as `tinkr_context.h`.

```c
struct tinkr_context_module {
    tinkr_u64 module_hash;
    tinkr_u64 module_base;
};

struct tinkr_context_function {
    tinkr_u64 module_hash;
    tinkr_u64 function_hash;
    tinkr_u64 offset;
    tinkr_u32 module_index;
    tinkr_u32 flags;
};

struct tinkr_context {
    tinkr_u32 version;
    tinkr_u32 flags;
    tinkr_u32 module_count;
    tinkr_u32 function_count;
    tinkr_u64 modules_ptr;
    tinkr_u64 functions_ptr;
};
```

The helper:

```c
void *tinkr_context_resolve(struct tinkr_context *ctx,
                            tinkr_u64 module_hash,
                            tinkr_u64 function_hash);
```

returns `module_base + offset` after matching `function_hash` and, when
non-zero, `module_hash`. `tinkr_context_resolve_any(ctx, function_hash)` is a
convenience wrapper for cases where the skill or prompt does not require a
specific module.

## Bytecode ABI

Tailor's raw bytecode entry is a profiler that does not call libc or allocate.
The host passes a `struct tailor_bytecode_args` from `include/tailor/bytecode.h`:

```c
struct tailor_bytecode_args {
    tailor_u32 version;
    tailor_u32 flags;
    tailor_u32 image_count;
    tailor_u32 entry_capacity;
    tailor_u64 images_ptr;
    tailor_u64 entries_ptr;
    tailor_u64 entry_count_ptr;
};
```

`images_ptr` points to an array of `struct tailor_image_view`. `entries_ptr`
points to caller-owned output storage for `struct tailor_manifest_entry`.
`entry_count_ptr` points to a `tailor_u32` written by the bytecode.

The bytecode entry has the Tinkr shape:

```c
int entry(struct seeds *s, void *args, size_t args_len);
```

It ignores `s`, validates `args`, walks the provided image memory, and writes
hash/offset entries into the caller's buffer.

## Platform Parsers

| Format | Host profiler | Bytecode parser | Notes |
| --- | --- | --- | --- |
| Mach-O | `src/profile_macho.c` | export trie in `src/bytecode_entry.c` | Leading C underscore normalized by default. |
| ELF | `src/profile_elf.c` | dynamic symbol table in `src/bytecode_entry.c` | Supports SysV and GNU hash tables for symbol count discovery. |
| PE | `src/profile_pe.c` | export directory in `src/bytecode_entry.c` | Bytecode mode builds for `x86_64-pc-windows-msvc`. |

Tinkr's SheLLVM postcheck requires one remaining function in the transformed
module. Tailor's bytecode source therefore uses forced inlining and a
non-recursive Mach-O export-trie walk. `tools/llvm-build.sh` also defines one
of these target selectors for bytecode mode:

- `TAILOR_BYTECODE_ONLY_MACHO`
- `TAILOR_BYTECODE_ONLY_ELF`
- `TAILOR_BYTECODE_ONLY_PE`

That keeps each target blob smaller and prevents Windows builds from needing
compiler runtime helpers such as `__chkstk`.

## Build Modes

Local host build:

```bash
make
make test
```

Tinkr container executable build:

```bash
cd ~/personal/andromeda/tinkr
docker compose run --rm dev \
  tools/build-tailor.sh exe /work/tailor-profile-container
```

Tinkr container bytecode build:

```bash
docker compose run --rm dev \
  tools/build-tailor.sh bytecode /work/tailor-bytecode-entry.bin \
  arm64-apple-macos
```

## Invariants

- Profiles are only valid for a compatible runtime context. Offsets are stable
  within a loaded image, but module availability and versioning still matter.
- Consumers should prefer `(module_hash, function_hash)` lookups. Function-only
  lookups are convenient but can be ambiguous.
- Cleartext names are optional diagnostics. Hash/offset pairs are the execution
  contract.
- Absolute `address` and `module_base` fields are debugging aids, not portable
  inputs for generated bytecode.
- `TINKR_CONTEXT_ABI_VERSION` and `TAILOR_BYTECODE_ABI_VERSION` gate ABI
  changes. Bump them when struct layout or semantics change.

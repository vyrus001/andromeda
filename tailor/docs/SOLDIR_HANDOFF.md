# Soldir Handoff

Soldir was not present in the local workspace when these docs were written.
This file documents the contract Tailor and Tinkr can offer to the final
integration layer without assuming Soldir's implementation details.

## Existing Pieces

Tailor provides:

- Process-local profile generation as JSON or TSV.
- An embeddable profiling library.
- A startup profiler for initialization-time manifests.
- A raw bytecode profiler entry that can be compiled through Tinkr.
- `bin/tailor-run`, which builds a live `struct tinkr_context` and executes a
  raw Tinkr blob with that context as `args`.

Tinkr provides:

- Dockerized LLVM + SheLLVM compilation.
- Cross-target raw blob extraction for ELF, Mach-O, and PE/COFF.
- A skill catalog that names indirect-call functions.
- Context-aware agent prompting via `--context-profile`.
- A deterministic context fixture that resolves `write` without using the LLM.

## Glue Objective

The final system should support this loop:

```text
1. Instantiate or enter the target runtime context.
2. Tailor profiles loaded modules and exported native functions.
3. Tailor emits hash/offset profile data.
4. Tinkr consumes that profile and generates context-aware bytecode.
5. Soldir transports, stores, launches, or orchestrates the blob.
6. The blob receives a live tinkr_context and resolves functions in-process.
7. Runtime output and status are returned to the orchestrator.
```

Step 5 is the unknown. Soldir may be a launcher, transport, packaging layer,
agent runtime, or something else. The rest of the contract should not require
absolute addresses or platform-specific loader internals from Soldir.

## Minimum Interface

Soldir needs to be able to handle these artifacts:

| Artifact | Producer | Consumer | Format |
| --- | --- | --- | --- |
| Runtime profile | Tailor | Tinkr, optionally Soldir | JSON or TSV `tailor.symbol-profile.v1` |
| Raw blob | Tinkr | Soldir or Tailor runner | Native bytes for target triple |
| Resolver context | Tailor or Soldir host | Blob | `struct tinkr_context` |
| Execution result | Blob runner | Soldir | Integer return code plus stdout/stderr or caller-defined output |

The key execution ABI remains:

```c
int entry(struct seeds *s, void *args, size_t args_len);
```

For context-aware blobs:

- `args` points to `struct tinkr_context`.
- `args_len` is at least `sizeof(struct tinkr_context)`.
- `ctx->version == TINKR_CONTEXT_ABI_VERSION`.
- `ctx->modules_ptr` points to `struct tinkr_context_module[]`.
- `ctx->functions_ptr` points to `struct tinkr_context_function[]`.

## Recommended Soldir Contract

If Soldir is the orchestrator, give it a narrow API like this:

```text
target_triple: required
blob: raw bytes
context_profile: optional Tailor JSON/TSV for build-time planning
runtime_context: required live tinkr_context or a way to ask Tailor to build it
args_payload: optional caller payload for future non-context blob modes
expected_abi:
  tinkr_context: 1
  tailor_profile: tailor.symbol-profile.v1
```

The runtime should reject execution when:

- The target triple does not match the blob runner.
- The context ABI version is unsupported.
- Required module/function hashes are absent.
- The blob is empty or cannot be mapped executable under host policy.

## Open Questions for the Soldir Thread

- Is Soldir responsible for launching a process, entering an existing process
  context, or only coordinating local tools?
- Does Soldir need to persist profiles and blobs, or are they ephemeral?
- Does Soldir need a language-neutral wire format for `struct tinkr_context`,
  or can it pass the live C struct in memory?
- Will Soldir call Tailor as a subprocess, link Tailor as a library, or consume
  Tailor's bytecode profiler entry?
- Does Soldir need to multiplex multiple generated blobs into one process?
- How should runtime output be captured: stdout/stderr, memory buffer, callback,
  or host-specific event channel?

## Integration Checklist

Use this checklist when the Soldir worktree is ready:

1. Confirm Soldir's role in the loop.
2. Add a tiny Soldir fixture that accepts a raw blob and a live context.
3. Generate `tailor-profile.json` from the same process Soldir will execute in.
4. Build `examples/context_write/hello.c` through Tinkr for the target triple.
5. Execute that blob through Soldir with Tailor's `struct tinkr_context`.
6. Confirm `context hi` and return code `0`.
7. Replace the deterministic fixture with an agent-generated context blob.
8. Add one test that fails cleanly when a required hash is absent.
9. Add one test that fails cleanly on ABI version mismatch.
10. Document the final command sequence in Soldir's README and link back here.

## Do Not Couple To

Avoid making Soldir depend on:

- Absolute addresses from Tailor JSON.
- Tailor's internal `tailor_profile` allocation layout.
- Tinkr's temporary build directories.
- Cleartext symbol names at runtime.
- macOS-only, Linux-only, or Windows-only loader behavior unless the target
  triple explicitly requires it.

The portable contract is hash/offset profile data at build time and
`struct tinkr_context` at runtime.

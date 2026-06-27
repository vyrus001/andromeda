#!/usr/bin/env python3
"""tinkr-agent: turn a natural-language prompt into a PIC blob.

Two-stage pipeline:

  prompt
    └─► stage 1: Claude routes against the skill index → list of skill paths
        └─► stage 2: Claude codegens with only those skills loaded
            └─► .c source → scripts/build-shellcode.sh → blob.bin
                                                              └─► [optional]
                                                                  test loader
                                                                  + qemu

The split keeps stage-2's system prompt small (only the ~10 selected
skills, not the full 100+ catalog), so input-token cost stays roughly
flat as the catalog grows.
"""
import argparse
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    import yaml
except ModuleNotFoundError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"
SEEDS_H = REPO_ROOT / "seeds.h"
TINKR_CONTEXT_H = REPO_ROOT / "tinkr_context.h"
BUILD_SHELLCODE = REPO_ROOT / "scripts" / "build-shellcode.sh"
BUILD_LOADER = REPO_ROOT / "tools" / "build-loader.sh"

MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
DEFAULT_TOPK = 12

TRIPLE_TO_QEMU = {
    "x86_64-linux-gnu": ("qemu-x86_64-static", "x86_64"),
    "aarch64-linux-gnu": ("qemu-aarch64-static", "aarch64"),
    "arm-linux-gnueabihf": ("qemu-arm-static", "armv7l"),
    "i686-linux-gnu": ("qemu-i386-static", "i686"),
}


def load_skill_yaml(path):
    if yaml is not None:
        return yaml.safe_load(path.read_text()) or {}

    # Fallback for local helper tests when PyYAML is unavailable. It only
    # reads top-level scalar keys; the container path still uses PyYAML.
    data = {}
    for line in path.read_text().splitlines():
        if not line or line[:1].isspace() or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.split("#", 1)[0].strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        data[key] = value
    return data

# ──────────────────────────────────────────────────────────────────────
# Stage 1: skill router. Takes the user prompt + a compact one-line-per-
# skill catalog and returns the paths most relevant to the request.
# Cached forever (the index changes only when skills/ changes).
# ──────────────────────────────────────────────────────────────────────

STAGE1_SYSTEM = """\
You're a router for the tinkr skill catalog. tinkr compiles natural-
language prompts into position-independent native code that calls OS
APIs through a runtime "seed" of function pointers and syscall helpers.
Each skill describes one OS API.

The user will describe what they want a blob to do. Your job: pick the
skills (by path) that the code-generation step will need.

Output rules:
- ONE skill path per line, no other text, no leading dashes, no quotes.
- Paths look like `linux/libc/write`, `windows/kernel32/WriteFile`,
  `macos/Foundation/NSString_stringWithUTF8String`, etc. (no `.yaml`).
- Pick 5–15 skills. Lean broader than narrower — if you might need it,
  include it.
- Always include the platform's foundational primitives even if not
  explicitly asked: e.g. if the prompt is linux+syscall, include the
  appropriate exit/close/etc. relevant to clean blob behaviour.
- For macOS Cocoa requests, always include the libobjc trio
  (objc_getClass, sel_registerName, objc_msgSend) since every
  objc_msgsend skill needs them.

The catalog (path — [lowering] — one-line description):

{{INDEX}}
"""


# ──────────────────────────────────────────────────────────────────────
# Stage 2: codegen. Static portion (rules + seeds.h) cached forever;
# dynamic portion (selected skill bodies) cached per unique selection.
# ──────────────────────────────────────────────────────────────────────

STAGE2_STATIC = """\
You compile natural-language prompts into C source for a position-
independent code generation pipeline. The C you emit will be compiled
by clang, transformed by SheLLVM's passes (flatten, global2stack, ...),
and linked into a flat PIC blob loadable at any address.

# Hard rules (violating these breaks the build)

1. **Single translation unit.** Only `#include "seeds.h"` — no system headers, no other includes. If a runtime resolver context is supplied, you may also include `#include "tinkr_context.h"`.
2. **Exactly one function** with `__attribute__((annotate("shellvm-main")))`, signature:
       int entry(struct seeds *s, void *args, size_t args_len)
3. **No `extern` declarations.** Every external call must go through `s` (per the skills) or be implemented via inline assembly (for syscalls).
4. **No file-scope variables.** No global state, no static data outside `entry`. Local arrays inside `entry` are fine — SheLLVM's `global2stack` pass relies on this.
5. **No TLS, no thread-locals.**
6. **Helper functions at file scope ARE allowed.** SheLLVM's `flatten` inlines them.
7. **String literals must be local to `entry`** (e.g. `const char msg[] = "...";` inside the function), never at file scope.

# Contract: seeds.h

The loader populates this struct and passes a pointer to it as the first argument. Use only fields that exist:

```c
{{SEEDS_H}}
```

# Lowering patterns

For `lowering: indirect_call` skills, call through the seed: `s->libc->write(1, msg, len)`. If the skill has `seed.type` (used for variadic functions like `objc_msgSend` and `NSLog`), the seed field is an opaque pointer — you MUST cast at the call site.

If a runtime resolver context is supplied, prefer resolving listed indirect-call functions from `args` instead of using `s`. In that mode, cast `args` to `struct tinkr_context *`, use `tinkr_context_resolve(ctx, MODULE_HASH, FUNCTION_HASH)`, check for NULL, cast the result to the exact function-pointer type from the skill signature, then call it. Keep syscall and objc_msgsend helper lowerings unchanged unless their infrastructure functions are explicitly listed in the resolver context.

For `lowering: syscall` skills, paste the per-arch `helper:` block at file scope inside `#if defined(__<arch>__)` branches, then call the helper from `entry`. Always emit ALL architectures the skill lists.

For `lowering: objc_msgsend` skills (macOS Cocoa), paste the `helper:` block at file scope (it wraps objc_getClass + sel_registerName + typed-cast + objc_msgSend). Then call the helper from `entry`. Requires `s->libobjc` to be populated.

# Output format

Respond with ONLY one fenced ```c code block containing the complete .c source. No prose before, no prose after, no other blocks.
"""


def build_skill_index():
    """One-line summary per skill for the stage-1 router."""
    lines = []
    for path in sorted(SKILLS_DIR.rglob("*.yaml")):
        try:
            data = load_skill_yaml(path)
        except Exception:
            continue
        if not data:
            continue
        rel = path.relative_to(SKILLS_DIR).with_suffix("")
        lowering = data.get("lowering", "?")
        desc_lines = (data.get("description") or "").strip().splitlines()
        desc = desc_lines[0] if desc_lines else ""
        # Trim long descriptions to one tight sentence-ish.
        if len(desc) > 100:
            desc = desc[:97] + "..."
        lines.append(f"{rel} — [{lowering}] — {desc}")
    return "\n".join(lines)


def select_skills(client, prompt, *, top_k=DEFAULT_TOPK, debug=False):
    """Stage-1: return list of skill paths the codegen step should see."""
    system = STAGE1_SYSTEM.replace("{{INDEX}}", build_skill_index())
    msg = client.messages.create(
        model=MODEL,
        max_tokens=512,
        system=[{
            "type": "text",
            "text": system,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": prompt}],
    )
    if debug:
        u = msg.usage
        print(
            f"[agent] stage1 tokens: input={u.input_tokens} "
            f"output={u.output_tokens} "
            f"cache_create={getattr(u, 'cache_creation_input_tokens', 0)} "
            f"cache_read={getattr(u, 'cache_read_input_tokens', 0)}",
            file=sys.stderr,
        )
    text = msg.content[0].text
    paths = []
    for line in text.splitlines():
        line = line.strip().lstrip("- ").rstrip(".yaml")
        if line and "/" in line:
            paths.append(line)
    # Validate each path exists; silently drop bogus ones.
    valid = []
    for p in paths:
        if (SKILLS_DIR / f"{p}.yaml").exists():
            valid.append(p)
        elif debug:
            print(f"[agent] stage1 returned unknown skill: {p}", file=sys.stderr)
    return valid[:top_k]


def build_stage2_static():
    text = STAGE2_STATIC.replace("{{SEEDS_H}}", SEEDS_H.read_text().rstrip())
    text += (
        "\n# Optional contract: tinkr_context.h\n\n"
        "When a runtime resolver context is supplied, this header is available:\n\n"
        "```c\n"
        f"{TINKR_CONTEXT_H.read_text().rstrip()}\n"
        "```\n"
    )
    return text


def build_skills_block(selected_paths):
    parts = ["# Selected skills\n"]
    for path_str in selected_paths:
        skill_path = SKILLS_DIR / f"{path_str}.yaml"
        if not skill_path.exists():
            continue
        parts.append(
            f"### `skills/{path_str}.yaml`\n\n"
            f"```yaml\n{skill_path.read_text().rstrip()}\n```\n"
        )
    return "\n".join(parts)


def fnv1a64(text):
    h = 14695981039346656037
    for b in text.encode("utf-8"):
        h ^= b
        h = (h * 1099511628211) & 0xffffffffffffffff
    return h


def parse_hex_int(value):
    if isinstance(value, int):
        return value
    if value is None:
        return 0
    return int(str(value), 0)


def load_context_profile(path):
    """Load a Tailor JSON or TSV profile into normalized entry dicts."""
    p = Path(path)
    text = p.read_text()
    entries = []
    if p.suffix.lower() == ".json" or text.lstrip().startswith("{"):
        data = json.loads(text)
        for e in data.get("entries", []):
            entries.append({
                "module": e.get("module", ""),
                "path": e.get("path", ""),
                "name": e.get("name", ""),
                "module_hash": parse_hex_int(e.get("module_hash")),
                "function_hash": parse_hex_int(e.get("function_hash")),
                "offset": parse_hex_int(e.get("offset")),
            })
        return entries

    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    for row in reader:
        entries.append({
            "module": row.get("module", ""),
            "path": row.get("path", ""),
            "name": row.get("name", ""),
            "module_hash": parse_hex_int(row.get("module_hash")),
            "function_hash": parse_hex_int(row.get("function_hash")),
            "offset": parse_hex_int(row.get("offset")),
        })
    return entries


def selected_indirect_names(selected_paths):
    names = {}
    for path_str in selected_paths:
        skill_path = SKILLS_DIR / f"{path_str}.yaml"
        if not skill_path.exists():
            continue
        try:
            data = load_skill_yaml(skill_path)
        except Exception:
            continue
        if data.get("lowering") != "indirect_call":
            continue
        name = data.get("name")
        if name:
            names.setdefault(name, []).append(path_str)
    return names


def build_context_block(context_entries, selected_paths):
    names = selected_indirect_names(selected_paths)
    wanted_hashes = {fnv1a64(name): name for name in names}
    matched = []
    for e in context_entries:
        fname = e.get("name") or wanted_hashes.get(e["function_hash"], "")
        if e["function_hash"] not in wanted_hashes and fname not in names:
            continue
        matched.append({**e, "resolved_name": fname})

    lines = [
        "# Runtime resolver context",
        "",
        "A Tailor resolver profile was supplied. The loader will pass `args` as `struct tinkr_context *`.",
        "Include `#include \"tinkr_context.h\"` in addition to `#include \"seeds.h\"`.",
        "For the functions listed below, resolve by hash from the context and call the resolved pointer instead of using the seed field.",
        "Always check the resolved pointer for NULL and return a negative error if a required function is missing.",
        "",
        "| Skill name | Module | Module hash | Function hash | Offset |",
        "| --- | --- | --- | --- | --- |",
    ]
    for e in matched:
        module = e.get("module") or e.get("path") or "<unnamed>"
        lines.append(
            f"| `{e['resolved_name']}` | `{module}` | "
            f"`0x{e['module_hash']:016x}` | `0x{e['function_hash']:016x}` | "
            f"`0x{e['offset']:x}` |"
        )

    if not matched:
        lines.append("| <none matched selected indirect-call skills> | | | | |")

    return "\n".join(lines)


def codegen(client, prompt, selected_paths, *, context_entries=None, debug=False):
    """Stage-2: produce C source given the selected skill subset."""
    system = [
        {
            "type": "text",
            "text": build_stage2_static(),
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": build_skills_block(selected_paths),
            "cache_control": {"type": "ephemeral"},
        },
    ]
    if context_entries is not None:
        system.append({
            "type": "text",
            "text": build_context_block(context_entries, selected_paths),
            "cache_control": {"type": "ephemeral"},
        })

    msg = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if debug:
        u = msg.usage
        print(
            f"[agent] stage2 tokens: input={u.input_tokens} "
            f"output={u.output_tokens} "
            f"cache_create={getattr(u, 'cache_creation_input_tokens', 0)} "
            f"cache_read={getattr(u, 'cache_read_input_tokens', 0)}",
            file=sys.stderr,
        )
    return msg.content[0].text


def extract_c_block(text):
    m = re.search(r"```(?:c|cpp|C)?\n(.*?)\n```", text, re.DOTALL)
    if not m:
        raise SystemExit(
            "[agent] response was not a fenced code block. Raw output:\n" + text
        )
    return m.group(1)


def host_arch():
    return os.uname().machine


def run(cmd, **kw):
    print(f"[agent] $ {' '.join(str(c) for c in cmd)}", file=sys.stderr)
    return subprocess.run(cmd, **kw)


def main():
    p = argparse.ArgumentParser(prog="tinkr-agent")
    p.add_argument("prompt", nargs="?", help="prompt text (or use -f)")
    p.add_argument("-f", "--prompt-file", help="read prompt from file")
    p.add_argument("-o", "--output", default="blob.bin",
                   help="output blob path (default: blob.bin)")
    p.add_argument("--target", default="",
                   help="LLVM target triple (default: host arch)")
    p.add_argument("--exec", action="store_true",
                   help="build a loader and run the blob")
    p.add_argument("--keep-source", action="store_true",
                   help="keep the generated .c source next to the blob")
    p.add_argument("--show-source", action="store_true",
                   help="print the generated source to stderr")
    p.add_argument("--debug", action="store_true",
                   help="extra logging (per-stage token counts, skill selection)")
    p.add_argument("--top-k", type=int, default=DEFAULT_TOPK,
                   help=f"max skills to pull into stage 2 (default: {DEFAULT_TOPK})")
    p.add_argument("--skills", help="comma-separated list of skill paths to use; "
                                    "skips stage-1 routing (for testing)")
    p.add_argument("--context-profile",
                   help="Tailor JSON/TSV profile whose hash/offset entries are "
                        "made available to codegen as a tinkr_context resolver")
    args = p.parse_args()

    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text()
    elif args.prompt:
        prompt = args.prompt
    else:
        p.error("provide a prompt arg or use -f")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("[agent] ANTHROPIC_API_KEY not set")

    import anthropic

    client = anthropic.Anthropic()

    if args.skills:
        selected = [s.strip() for s in args.skills.split(",") if s.strip()]
        print(f"[agent] using supplied skills: {selected}", file=sys.stderr)
    else:
        print("[agent] stage 1: routing skills...", file=sys.stderr)
        selected = select_skills(client, prompt, top_k=args.top_k, debug=args.debug)
        if args.debug:
            print(f"[agent] selected: {selected}", file=sys.stderr)

    if not selected:
        sys.exit("[agent] no skills selected — refusing to proceed blind")

    context_entries = None
    if args.context_profile:
        context_entries = load_context_profile(args.context_profile)
        print(
            f"[agent] loaded context profile: {len(context_entries)} entries",
            file=sys.stderr,
        )

    print("[agent] stage 2: codegen...", file=sys.stderr)
    response = codegen(client, prompt, selected, context_entries=context_entries, debug=args.debug)
    source = extract_c_block(response)

    if args.show_source:
        print("[agent] --- generated source ---", file=sys.stderr)
        print(source, file=sys.stderr)
        print("[agent] --- end source ---", file=sys.stderr)

    src_path = Path(args.output).with_suffix(".c")
    src_path.write_text(source)
    print(f"[agent] wrote source: {src_path}", file=sys.stderr)

    blob_path = Path(args.output)
    build_cmd = [str(BUILD_SHELLCODE), str(src_path), str(blob_path)]
    if args.target:
        build_cmd.append(args.target)
    r = run(build_cmd)
    if r.returncode != 0:
        print(f"[agent] build failed. Source preserved at {src_path}", file=sys.stderr)
        sys.exit(r.returncode)

    if not args.keep_source:
        src_path.unlink()

    if not args.exec:
        return

    with tempfile.TemporaryDirectory() as td:
        loader_path = Path(td) / "loader"
        loader_cmd = [str(BUILD_LOADER), str(loader_path)]
        if args.target:
            loader_cmd.append(args.target)
        if run(loader_cmd).returncode != 0:
            sys.exit("[agent] loader build failed")

        run_cmd = []
        if args.target and args.target in TRIPLE_TO_QEMU:
            qemu, target_host = TRIPLE_TO_QEMU[args.target]
            if target_host != host_arch():
                run_cmd.append(qemu)
        run_cmd.extend([str(loader_path), str(blob_path)])
        r = run(run_cmd)
        sys.exit(r.returncode)


if __name__ == "__main__":
    main()

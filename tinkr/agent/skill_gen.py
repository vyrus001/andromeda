#!/usr/bin/env python3
"""tinkr-skill-gen: produce a single YAML skill from a function spec.

Generates skills/<platform>/<lib>/<function>.yaml. Calls Claude with
the existing skill catalog as few-shot exemplars and asks for one
skill following the project's schema.

Usage:
  skill-gen --platform linux  --lib libc      --function read
  skill-gen --platform windows --lib kernel32 --function VirtualFree \\
            --doc-url https://learn.microsoft.com/en-us/windows/win32/api/memoryapi/nf-memoryapi-virtualfree
  skill-gen --platform macos  --lib bsd-syscall --function read --lowering syscall

If --doc-url is given, the URL is fetched (up to 200 KB) and included
in the user message. If --lowering is omitted, the agent infers it
from (platform, lib): *syscall* libs get the syscall lowering;
Foundation classes get objc_msgsend; everything else is indirect_call.
"""
import argparse
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import anthropic

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIR = REPO_ROOT / "skills"

MODEL = "claude-opus-4-7"
MAX_TOKENS = 4096
URL_FETCH_MAX = 200 * 1024  # 200 KB

EXEMPLAR_PATHS = [
    "linux/libc/write.yaml",
    "linux/libc/open.yaml",
    "linux/syscall/write.yaml",
    "macos/libSystem/mmap.yaml",
    "macos/bsd-syscall/write.yaml",
    "macos/libobjc/objc_msgSend.yaml",
    "macos/Foundation/NSString_stringWithUTF8String.yaml",
    "windows/kernel32/WriteFile.yaml",
    "windows/kernel32/CreateFileW.yaml",
    "windows/ntdll/NtAllocateVirtualMemory.yaml",
]


SYSTEM_TEMPLATE = """\
You produce a single YAML skill file for the tinkr project. tinkr compiles
natural-language prompts into position-independent native code; skills are
the knowledge base that teaches the codegen agent how to call platform APIs.

# Output schema

Top-level keys, in this order for readability:

  name          string, function name as it appears in the platform's docs
  platform      string: linux | macos | windows
  lib           string: which sub-library (libc, libSystem, kernel32, ntdll,
                Foundation, libobjc, syscall, bsd-syscall, ...)
  description   block scalar, plain prose, one paragraph
  lowering      one of: indirect_call | syscall | objc_msgsend
  [lowering-specific keys]
  signature     object: { return: {c_type, on_failure?}, params: [{name, c_type}, ...] }
  example       block scalar, a C usage snippet
  notes         BLOCK SCALAR (mark with `|`), bullet-point prose

CRITICAL: `notes:` must be a block scalar (`notes: |`) — NEVER a YAML
list. Backticks and colons in unquoted YAML list items break pyyaml.

# Lowering-specific keys

## lowering: indirect_call

  seed:
    header: <C struct name, e.g. linux_libc, windows_kernel32>
    field:  <field name within sub-struct, e.g. write, WriteFile>
    access: "s-><sub-struct field>-><field>"
    type:   "void *"   (OPTIONAL — only for variadic functions; the
                        seed field becomes opaque and the caller MUST
                        cast at the call site)

The seed.access string is parsed by tools/gen-seeds-h.py to derive
the seeds-level field name. Use lowercase library name without any
platform prefix: linux_libc -> "s->libc->...", windows_kernel32 ->
"s->kernel32->...", macos_libsystem -> "s->libsystem->..." etc.

## lowering: syscall

  arch:
    arm64:
      syscall_number: <int>
      helper: |
        <C function with inline asm; agent pastes at file scope>
    x86_64:
      syscall_number: <int>
      helper: |
        <C function with inline asm>
    # include all archs you can reasonably support: arm64, x86_64,
    # arm, i386 for Linux; arm64, x86_64 for macOS

Helpers must normalize errors to "negative return = -errno" regardless
of platform. macOS syscalls use the carry flag; the helper handles
this with a branch-on-no-carry + neg.

## lowering: objc_msgsend (macOS Cocoa methods only)

  class_name: <Objective-C class name, e.g. NSString>
  selector:   "<selector with trailing colon(s) for arg slots>"
  receiver_kind: class | instance
  requires:
    - macos/libobjc/objc_getClass        (always required)
    - macos/libobjc/sel_registerName     (always required)
    - macos/libobjc/objc_msgSend         (always required)
  helper: |
    <C typed wrapper around objc_msgSend; agent pastes at file scope>

# Type conventions

Skill `signature` uses portable C types only:

  ssize_t         → write as `long` (no <sys/types.h> in seeds.h)
  off_t           → `long long`
  size_t          → fine, comes from <stddef.h>
  int, unsigned int, long, long long, char, void *  fine
  HANDLE          → `void *`
  DWORD           → `unsigned int`
  BOOL            → `int`
  LPCSTR          → `const char *`
  LPCWSTR         → `const unsigned short *`  (UTF-16, 2-byte chars)
  LPVOID          → `void *`
  LPCVOID         → `const void *`
  NTSTATUS        → `int`
  FARPROC, HMODULE → `void *`

Document the MSDN / Apple typed names in `notes:` so a reader can
cross-reference docs.

# ABI / calling convention reminders (encode in notes when relevant)

- Win64: rcx, rdx, r8, r9 + 32-byte shadow space. Clang handles this
  when --target=x86_64-pc-windows-*.
- macOS BSD syscalls use the carry flag for errors (not negative-return).
- Variadic functions (NSLog, objc_msgSend, printf-family) MUST use
  seed.type: "void *" because the typed function-pointer form invokes
  the variadic ABI on arm64, which differs from named-args.

# Output format

Respond with ONLY a fenced ```yaml code block. No prose before, no
prose after, exactly one fenced block. The YAML must parse with
default pyyaml.safe_load.

# Existing skills — use these as reference for tone, depth, and structure

{{EXEMPLARS}}
"""


def load_exemplars():
    parts = []
    for rel in EXEMPLAR_PATHS:
        path = SKILLS_DIR / rel
        if path.exists():
            parts.append(
                f"### `skills/{rel}`\n\n```yaml\n{path.read_text().rstrip()}\n```\n"
            )
    return "\n".join(parts)


def fetch_doc(url):
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "tinkr-skill-gen/0.1"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read(URL_FETCH_MAX)
        return data.decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError) as e:
        print(f"[skill-gen] WARNING: failed to fetch {url}: {e}", file=sys.stderr)
        return None


def extract_yaml_block(text):
    m = re.search(r"```(?:yaml|yml)?\n(.*?)\n```", text, re.DOTALL)
    if not m:
        raise RuntimeError(
            "[skill-gen] response was not a fenced yaml block. Raw output:\n" + text
        )
    return m.group(1)


def build_user_msg(platform, lib, function, lowering=None, doc_url=None, doc_text=None):
    msg = (
        f"Produce a tinkr skill for:\n"
        f"  platform: {platform}\n"
        f"  lib:      {lib}\n"
        f"  function: {function}\n"
    )
    if lowering:
        msg += f"  lowering: {lowering}\n"
    if doc_url:
        doc = fetch_doc(doc_url)
        if doc:
            msg += (
                f"\nReference documentation fetched from {doc_url} "
                f"(truncated to first {URL_FETCH_MAX // 1024} KB):\n\n{doc}\n"
            )
    if doc_text:
        msg += f"\nReference text:\n\n{doc_text}\n"
    return msg


def call_claude(client, system_text, user_msg, debug=False, log_prefix="[skill-gen]"):
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[{
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }],
        messages=[{"role": "user", "content": user_msg}],
    )
    if debug:
        u = resp.usage
        print(
            f"{log_prefix} tokens: input={u.input_tokens} output={u.output_tokens} "
            f"cache_create={getattr(u, 'cache_creation_input_tokens', 0)} "
            f"cache_read={getattr(u, 'cache_read_input_tokens', 0)}",
            file=sys.stderr,
        )
    return resp.content[0].text


def generate_one(client, system_text, platform, lib, function,
                 lowering=None, doc_url=None, doc_text=None,
                 force=False, debug=False):
    """Generate one skill YAML and write it. Returns the output path."""
    out_path = SKILLS_DIR / platform / lib / f"{function}.yaml"
    if out_path.exists() and not force:
        raise FileExistsError(str(out_path))

    user_msg = build_user_msg(platform, lib, function, lowering, doc_url, doc_text)
    response = call_claude(client, system_text, user_msg, debug=debug)
    yaml_text = extract_yaml_block(response).rstrip() + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml_text)
    return out_path


def main_batch(args, client, system_text):
    import yaml as _yaml
    with open(args.batch) as f:
        spec = _yaml.safe_load(f)
    entries = spec.get("skills", [])
    if not entries:
        sys.exit(f"[skill-gen] {args.batch}: empty 'skills:' list")

    print(f"[skill-gen] batch: {len(entries)} skill(s) requested", file=sys.stderr)
    written, skipped, failed = 0, 0, 0
    for i, entry in enumerate(entries, 1):
        platform = entry["platform"]
        lib = entry["lib"]
        function = entry["function"]
        rel = f"{platform}/{lib}/{function}"
        try:
            out_path = generate_one(
                client, system_text,
                platform, lib, function,
                lowering=entry.get("lowering"),
                doc_url=entry.get("doc_url"),
                doc_text=entry.get("doc_text"),
                force=args.force,
                debug=args.debug,
            )
            print(f"[skill-gen] [{i}/{len(entries)}] wrote {out_path.relative_to(REPO_ROOT)}",
                  file=sys.stderr)
            written += 1
        except FileExistsError:
            print(f"[skill-gen] [{i}/{len(entries)}] skip (exists): {rel}", file=sys.stderr)
            skipped += 1
        except Exception as e:
            print(f"[skill-gen] [{i}/{len(entries)}] FAILED {rel}: {e}", file=sys.stderr)
            failed += 1

    print(f"[skill-gen] done: wrote={written} skipped={skipped} failed={failed}", file=sys.stderr)
    if failed:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(prog="tinkr-skill-gen")
    p.add_argument("--platform", help="linux | macos | windows")
    p.add_argument("--lib", help="libc, libSystem, kernel32, ntdll, Foundation, libobjc, syscall, bsd-syscall, ...")
    p.add_argument("--function", help="function name as it appears in the platform's docs")
    p.add_argument("--lowering", help="indirect_call | syscall | objc_msgsend (omit to let claude infer)")
    p.add_argument("--doc-url", help="URL of authoritative docs to include in the prompt")
    p.add_argument("--doc-text", help="reference text/snippet provided directly")
    p.add_argument("--batch", metavar="YAML",
                   help="path to a YAML file with a top-level `skills:` list of "
                        "{platform, lib, function, lowering?, doc_url?} entries; "
                        "alternative to --platform/--lib/--function")
    p.add_argument("--force", action="store_true",
                   help="overwrite existing skill files")
    p.add_argument("--debug", action="store_true")
    args = p.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("[skill-gen] ANTHROPIC_API_KEY not set")

    system = SYSTEM_TEMPLATE.replace("{{EXEMPLARS}}", load_exemplars())
    client = anthropic.Anthropic()

    if args.batch:
        return main_batch(args, client, system)

    if not (args.platform and args.lib and args.function):
        sys.exit("[skill-gen] supply --platform, --lib, --function (or use --batch)")

    out_path = SKILLS_DIR / args.platform / args.lib / f"{args.function}.yaml"
    if out_path.exists() and not args.force:
        sys.exit(f"[skill-gen] {out_path} already exists; pass --force to overwrite")

    user_msg = build_user_msg(args.platform, args.lib, args.function,
                              args.lowering, args.doc_url, args.doc_text)
    print("[skill-gen] calling claude...", file=sys.stderr)
    response = call_claude(client, system, user_msg, debug=args.debug)
    yaml_text = extract_yaml_block(response).rstrip() + "\n"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(yaml_text)
    print(f"[skill-gen] wrote {out_path.relative_to(REPO_ROOT)}")
    print(
        "[skill-gen] regenerate seeds.h with:\n"
        "             docker compose run --rm --entrypoint python3 agent /work/tools/gen-seeds-h.py",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

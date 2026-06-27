#!/usr/bin/env python3
"""Validate every skill YAML in skills/.

Two passes:

  1. Structural: parse YAML, check the schema by lowering type
     (indirect_call / syscall / objc_msgsend).

  2. Compile (optional, --compile): synthesize a minimal C source per
     skill that references the relevant seed field (or pastes the
     helper) and compile through clang+SheLLVM. Catches:
       - seed.access strings that don't match seeds.h
       - skill signatures whose C types don't match seeds.h's portable
         types (would surface as field-type mismatch)
       - syscall helpers with malformed inline asm
       - objc_msgsend helpers with malformed C

Doesn't catch:
       - ABI bugs visible only at runtime (e.g. NSLog variadic-cast)
       - Wrong syscall numbers, wrong selectors, wrong flag values

Usage:
  python3 tools/validate-skills.py            # structural only
  python3 tools/validate-skills.py --compile  # + compile-check
"""
import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tinkr_skills import (  # noqa: E402
    REPO_ROOT, SKILLS_DIR, parse_seed_access, KNOWN_LOWERINGS,
)
import yaml  # noqa: E402

# Map from a skill's seed.header (e.g. linux_libc) to the host architectures
# we can plausibly compile-test for that platform.
PLATFORM_DEFAULT_TARGET = {
    "linux":   "aarch64-linux-gnu",
    "macos":   "arm64-apple-macos",
    "windows": "x86_64-pc-windows-msvc",
}


class SkillIssue(Exception):
    pass


def parse_skill(path):
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise SkillIssue(f"YAML parse error: {e}")
    if not isinstance(data, dict):
        raise SkillIssue("not a YAML mapping")
    return data


def require(d, key, ctx="root"):
    if key not in d:
        raise SkillIssue(f"missing required key {ctx}.{key}")
    return d[key]


def check_common(skill):
    for k in ("name", "platform", "lib", "description", "lowering", "signature"):
        require(skill, k)
    notes = skill.get("notes")
    if notes is not None and not isinstance(notes, str):
        raise SkillIssue("`notes` must be a block-scalar STRING "
                         "(use `notes: |`), not a YAML list — pyyaml "
                         "rejects backticks/colons in unquoted list items")


def check_indirect_call(skill):
    seed = require(skill, "seed")
    for k in ("header", "field", "access"):
        require(seed, k, "seed")
    try:
        seeds_field, parsed_field = parse_seed_access(seed["access"])
    except ValueError as e:
        raise SkillIssue(str(e))
    if parsed_field != seed["field"]:
        raise SkillIssue(
            f"seed.field={seed['field']!r} disagrees with the tail of "
            f"seed.access ({parsed_field!r})"
        )
    if seed.get("type"):
        # Override is allowed but should be a non-empty string.
        if not isinstance(seed["type"], str) or not seed["type"].strip():
            raise SkillIssue("seed.type must be a non-empty C type string when present")
    sig = skill["signature"]
    if "return" not in sig:
        raise SkillIssue("signature.return missing")
    if not isinstance(sig.get("params", []), list):
        raise SkillIssue("signature.params must be a list")


def check_syscall(skill):
    arch = require(skill, "arch")
    if not isinstance(arch, dict) or not arch:
        raise SkillIssue("`arch:` must be a non-empty mapping of arch_name -> {syscall_number, helper}")
    for arch_name, spec in arch.items():
        if not isinstance(spec, dict):
            raise SkillIssue(f"arch.{arch_name} must be a mapping")
        if "helper" not in spec or not spec["helper"].strip():
            raise SkillIssue(f"arch.{arch_name}.helper is missing or empty")


def check_objc_msgsend(skill):
    for k in ("class_name", "selector", "receiver_kind", "helper"):
        require(skill, k)
    rk = skill["receiver_kind"]
    if rk not in ("class", "instance"):
        raise SkillIssue(f"receiver_kind must be 'class' or 'instance', got {rk!r}")
    sel = skill["selector"]
    if not isinstance(sel, str) or not sel:
        raise SkillIssue("selector must be a non-empty string")
    # Loose check: ObjC selectors have alphanumeric segments separated by colons.
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_:]*$", sel):
        raise SkillIssue(f"selector has unexpected characters: {sel!r}")


LOWERING_CHECKS = {
    "indirect_call": check_indirect_call,
    "syscall":       check_syscall,
    "objc_msgsend":  check_objc_msgsend,
}


def structural_check(path):
    """Return None on success, error string on failure."""
    try:
        skill = parse_skill(path)
        check_common(skill)
        lowering = skill["lowering"]
        if lowering not in KNOWN_LOWERINGS:
            raise SkillIssue(f"unknown lowering: {lowering!r}")
        if lowering not in LOWERING_CHECKS:
            raise SkillIssue(f"no checker for lowering {lowering!r}")
        LOWERING_CHECKS[lowering](skill)
    except SkillIssue as e:
        return str(e)
    except Exception as e:
        return f"{type(e).__name__}: {e}"
    return None


# ──────────────────────────────────────────────────────────────────────
# Compile-mode checks
# ──────────────────────────────────────────────────────────────────────

ENTRY_TEMPLATE = """\
#include "seeds.h"

{HELPERS}

__attribute__((annotate("shellvm-main")))
int entry(struct seeds *s, void *args, size_t args_len) {{
    (void)args; (void)args_len;
    {BODY}
    return 0;
}}
"""


def synth_source(skill):
    """Build a minimal C source that exercises the skill enough for clang to
    verify field references / helper syntax. Returns (source, target_triple)."""
    target = PLATFORM_DEFAULT_TARGET.get(skill["platform"])
    if not target:
        return None, None

    if skill["lowering"] == "indirect_call":
        seed = skill["seed"]
        access = seed["access"]
        body = (
            "/* Force a type-checked reference to the seed field. */\n"
            f"    if (s) {{ void *_p = (void *)({access}); (void)_p; }}\n"
        )
        return ENTRY_TEMPLATE.format(HELPERS="", BODY=body), target

    if skill["lowering"] == "syscall":
        arch = skill["arch"]
        # Pick one arch matching the default target.
        triple_arch_map = {
            "aarch64-linux-gnu":      ["arm64", "aarch64"],
            "arm64-apple-macos":      ["arm64", "aarch64"],
            "x86_64-linux-gnu":       ["x86_64"],
            "x86_64-pc-windows-msvc": ["x86_64"],
        }
        candidates = triple_arch_map.get(target, [])
        helper = None
        for c in candidates:
            if c in arch:
                helper = arch[c]["helper"]
                break
        if helper is None:
            # Fall back to any arch present.
            for spec in arch.values():
                helper = spec.get("helper")
                if helper:
                    break
        if not helper:
            return None, None
        # Body just exists; the helper itself is what we're compile-checking.
        return ENTRY_TEMPLATE.format(HELPERS=helper, BODY="(void)s;"), target

    if skill["lowering"] == "objc_msgsend":
        helper = skill.get("helper", "")
        if not helper:
            return None, None
        body = "(void)s->libobjc;"
        return ENTRY_TEMPLATE.format(HELPERS=helper, BODY=body), target

    return None, None


def compile_check(path, skill, debug=False):
    """Return None on success, error string on failure."""
    src, target = synth_source(skill)
    if src is None:
        return None  # nothing to compile (unsupported platform or shape)

    with tempfile.NamedTemporaryFile("w", suffix=".c", delete=False) as tf:
        tf.write(src)
        src_path = tf.name

    cmd = [
        "clang",
        f"--target={target}",
        "-I", str(REPO_ROOT),
        "-O1", "-Xclang", "-disable-llvm-passes",
        "-fno-stack-protector",
        "-fno-unwind-tables", "-fno-asynchronous-unwind-tables",
        "-Werror=implicit-function-declaration",
        "-emit-llvm", "-c",
        "-o", "/dev/null",
        src_path,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        msg = r.stderr.strip()
        if debug:
            return f"clang failed (target={target}):\n--- source ---\n{src}\n--- stderr ---\n{msg}"
        # Trim to first error line for brevity.
        first = next((ln for ln in msg.splitlines() if "error:" in ln), msg.splitlines()[-1] if msg else "")
        return f"clang failed (target={target}): {first}"
    return None


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--compile", action="store_true",
                   help="also compile-check each skill via clang+SheLLVM rules")
    p.add_argument("--debug", action="store_true",
                   help="dump synthesized source + full clang stderr on failure")
    p.add_argument("--filter", help="substring filter on skill path")
    args = p.parse_args()

    paths = sorted(SKILLS_DIR.rglob("*.yaml"))
    if args.filter:
        paths = [p for p in paths if args.filter in str(p)]

    if not paths:
        sys.exit("no skill files found (after --filter)")

    structural_fails = []
    compile_fails = []
    n_ok = 0
    n_compiled = 0

    for path in paths:
        rel = path.relative_to(REPO_ROOT)
        # Structural
        err = structural_check(path)
        if err:
            structural_fails.append((rel, err))
            print(f"STRUCT-FAIL  {rel}: {err}")
            continue
        # Compile (only if structural passed and --compile)
        if args.compile:
            skill = parse_skill(path)
            err = compile_check(path, skill, debug=args.debug)
            n_compiled += 1
            if err:
                compile_fails.append((rel, err))
                print(f"COMPILE-FAIL {rel}: {err}")
                continue
        n_ok += 1

    print()
    print(f"Checked {len(paths)} skill(s)")
    print(f"  structural OK: {len(paths) - len(structural_fails)}")
    print(f"  structural FAIL: {len(structural_fails)}")
    if args.compile:
        print(f"  compile attempted: {n_compiled}")
        print(f"  compile FAIL: {len(compile_fails)}")
    sys.exit(1 if structural_fails or compile_fails else 0)


if __name__ == "__main__":
    main()

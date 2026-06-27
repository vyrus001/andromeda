#!/usr/bin/env python3
"""Extract indirect-call symbol names from a Tinkr skills tree.

The script intentionally uses only the Python standard library. Tinkr YAML
files keep the fields we need at top level, so a small line parser is enough
and avoids making Tailor depend on PyYAML.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


FIELD_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*?)\s*(?:#.*)?$")


def unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def read_top_level_fields(path: Path) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line[:1].isspace():
            continue
        match = FIELD_RE.match(line)
        if match:
            fields[match.group(1)] = unquote(match.group(2))
    return fields


def iter_symbols(skills_dir: Path, include_platform: bool) -> list[str]:
    symbols: set[str] = set()
    for path in sorted(skills_dir.rglob("*.yaml")):
        fields = read_top_level_fields(path)
        if fields.get("lowering") != "indirect_call":
            continue
        name = fields.get("name")
        if not name:
            continue
        if include_platform:
            platform = fields.get("platform", path.relative_to(skills_dir).parts[0])
            lib = fields.get("lib", path.relative_to(skills_dir).parts[1])
            symbols.add(f"{platform}/{lib}/{name}")
        else:
            symbols.add(name)
    return sorted(symbols)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "skills_dir",
        nargs="?",
        default=str(Path.home() / "personal" / "tinkr" / "skills"),
        help="path to Tinkr's skills directory",
    )
    parser.add_argument(
        "--qualified",
        action="store_true",
        help="emit platform/lib/name instead of just name",
    )
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir).expanduser()
    if not skills_dir.is_dir():
        print(f"tinkr-symbols: not a directory: {skills_dir}", file=sys.stderr)
        return 2

    for symbol in iter_symbols(skills_dir, args.qualified):
        print(symbol)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


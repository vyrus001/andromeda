"""Shared utilities for tinkr scripts.

Anything that touches skill YAML files or seeds.h ABI conventions
should live here. Import from anywhere via:

    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # if in tools/ or agent/
    from tinkr_skills import iter_skills, parse_seed_access, ...

The module lives at the repo root so the `sys.path.insert` parent
calculation works the same way from tools/ and agent/.
"""
import re
from pathlib import Path
from typing import Iterator, Optional, Tuple

import yaml

# When tinkr_skills.py lives at /work/tinkr_skills.py, REPO_ROOT = /work.
REPO_ROOT = Path(__file__).resolve().parent
SKILLS_DIR = REPO_ROOT / "skills"
SEEDS_H = REPO_ROOT / "seeds.h"

# A seed.access string has the shape: s->LIB_FIELD->FIELD
# where LIB_FIELD is the seeds-level pointer name (libc, kernel32, ...)
# and FIELD is the field name within that sub-struct.
SEED_ACCESS_RE = re.compile(r"^\s*s\s*->\s*(\w+)\s*->\s*(\w+)\s*$")

# Skills express POSIX-y types for clarity; seeds.h emits portable
# equivalents that don't require <sys/types.h>.
PORTABLE_TYPE_MAP = {
    "ssize_t": "long",
    "off_t":   "long long",
}

KNOWN_LOWERINGS = {"indirect_call", "syscall", "objc_msgsend"}


def portabilise_type(c_type: str) -> str:
    """Replace skill's POSIX-y types with seeds.h's portable equivalents."""
    return PORTABLE_TYPE_MAP.get(c_type.strip(), c_type)


def parse_seed_access(access: str) -> Tuple[str, str]:
    """Parse 's->libc->write' into ('libc', 'write'). Raises ValueError."""
    m = SEED_ACCESS_RE.match(access)
    if not m:
        raise ValueError(f"unexpected seed.access shape: {access!r}")
    return m.group(1), m.group(2)


def iter_skills() -> Iterator[Tuple[Path, dict]]:
    """Yield (path, parsed_dict) for every readable skill yaml.

    Files that fail YAML parse are silently skipped — callers that
    want strict validation should use the structural checker in
    validate-skills.py instead.
    """
    for path in sorted(SKILLS_DIR.rglob("*.yaml")):
        try:
            data = yaml.safe_load(path.read_text())
        except yaml.YAMLError:
            continue
        if isinstance(data, dict):
            yield path, data


def skill_relpath(path: Path) -> str:
    """`/work/skills/linux/libc/write.yaml` -> `linux/libc/write`."""
    return str(path.relative_to(SKILLS_DIR).with_suffix(""))


def first_line(text: Optional[str]) -> str:
    """First non-empty line of a (possibly None) description block."""
    if not text:
        return ""
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return ""

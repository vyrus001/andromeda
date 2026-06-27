#!/usr/bin/env python3
"""Generate SKILLS.md — a human-readable index of every skill.

Auto-generated like seeds.h. Run after adding/removing skills:

    docker compose run --rm --entrypoint python3 agent /work/tools/gen-skills-md.py
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from tinkr_skills import (  # noqa: E402
    REPO_ROOT, iter_skills, skill_relpath, first_line,
)

OUT = REPO_ROOT / "SKILLS.md"

HEADER = """\
# tinkr skill catalog

Auto-generated from `skills/**/*.yaml`. Regenerate with
`tools/gen-skills-md.py`. The source-of-truth is the YAML files; this
file is for browsing.

"""


def short_return(skill):
    sig = skill.get("signature") or {}
    ret = sig.get("return") or {}
    return ret.get("c_type", "?")


def main():
    # Group by (platform, lib).
    by_lib = defaultdict(list)
    total = 0
    for path, skill in iter_skills():
        rel = skill_relpath(path)
        platform = skill.get("platform", "?")
        lib = skill.get("lib", "?")
        lowering = skill.get("lowering", "?")
        name = skill.get("name", path.stem)
        desc = first_line(skill.get("description"))
        ret_c = short_return(skill)
        # ObjC skills carry class_name; surface it.
        cls = skill.get("class_name")
        display_name = f"{cls}.{name}" if cls else name
        by_lib[(platform, lib, lowering)].append(
            (display_name, ret_c, desc, rel)
        )
        total += 1

    if total == 0:
        print("[gen-skills-md] no skills found", file=sys.stderr)
        OUT.write_text(HEADER + "_(no skills)_\n")
        return

    # Header summary.
    lib_count = len(by_lib)
    summary = (
        f"**{total} skills across {lib_count} (platform, lib) groups.**\n\n"
        "| Group | Lowering | Count |\n"
        "| --- | --- | --- |\n"
    )
    for (platform, lib, lowering), entries in sorted(by_lib.items()):
        summary += f"| `{platform}/{lib}` | {lowering} | {len(entries)} |\n"
    summary += "\n"

    # Per-group sections.
    sections = []
    for (platform, lib, lowering), entries in sorted(by_lib.items()):
        entries.sort(key=lambda e: e[0].lower())
        title = f"## `{platform}/{lib}` — {len(entries)} {lowering}\n"
        if lowering == "objc_msgsend":
            heading = "| Method | Returns | Description |\n| --- | --- | --- |\n"
        else:
            heading = "| Function | Returns | Description |\n| --- | --- | --- |\n"
        rows = []
        for display_name, ret_c, desc, rel in entries:
            # markdown-escape pipes if any (rare in our descriptions).
            d = desc.replace("|", "\\|")
            rows.append(
                f"| [`{display_name}`](skills/{rel}.yaml) | `{ret_c}` | {d} |"
            )
        sections.append(title + "\n" + heading + "\n".join(rows) + "\n")

    OUT.write_text(HEADER + summary + "\n".join(sections))
    print(f"[gen-skills-md] wrote {OUT.relative_to(REPO_ROOT)} "
          f"({total} skills, {lib_count} groups)")


if __name__ == "__main__":
    main()

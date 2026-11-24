"""Count TODO style markers and compute their density per thousand lines of code."""

from __future__ import annotations

import re

from .languages import CODE_LANGUAGES

MARKER_RE = re.compile(r"\b(TODO|FIXME|HACK|XXX)\b")


def todo_density(files) -> dict:
    by_tag: dict[str, int] = {}
    per_file = []
    code_lines = 0
    for info in files:
        if info.language not in CODE_LANGUAGES or info.text is None:
            continue
        code_lines += info.lines
        tags = MARKER_RE.findall(info.text)
        if not tags:
            continue
        for tag in tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1
        per_file.append(
            {
                "path": info.path,
                "count": len(tags),
                "lines": info.lines,
                "per_kloc": round(1000.0 * len(tags) / max(info.lines, 1), 1),
            }
        )
    total = sum(by_tag.values())
    per_file.sort(key=lambda f: (-f["count"], f["path"]))
    return {
        "total": total,
        "code_lines": code_lines,
        "per_kloc": round(1000.0 * total / code_lines, 1) if code_lines else 0.0,
        "by_tag": dict(sorted(by_tag.items())),
        "files": per_file,
    }

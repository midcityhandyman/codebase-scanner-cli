"""Assemble the scan report and render it as JSON or Markdown."""

from __future__ import annotations

import json
from pathlib import Path

from . import __version__
from .deadfiles import find_dead_files
from .languages import language_mix
from .manifests import summarize_manifests
from .risks import SEVERITIES, scan_risks
from .todos import todo_density
from .walker import DEFAULT_MAX_FILE_BYTES, walk


def structure_summary(files) -> dict:
    """Top level entries with file and line counts, plus overall depth."""
    top: dict[str, dict] = {}
    dirs: set[str] = set()
    max_depth = 0
    for info in files:
        parts = info.path.split("/")
        max_depth = max(max_depth, len(parts) - 1)
        for i in range(1, len(parts)):
            dirs.add("/".join(parts[:i]))
        name = parts[0] + "/" if len(parts) > 1 else "(root files)"
        entry = top.setdefault(name, {"name": name, "files": 0, "lines": 0, "bytes": 0})
        entry["files"] += 1
        entry["lines"] += info.lines
        entry["bytes"] += info.size
    return {
        "directories": len(dirs),
        "max_depth": max_depth,
        "top_level": sorted(top.values(), key=lambda e: (-e["files"], e["name"])),
    }


def build_report(root, top_n: int = 10, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> dict:
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"not a directory: {root}")
    files = walk(root, max_file_bytes=max_file_bytes)
    largest = sorted(files, key=lambda f: (-f.size, f.path))[:top_n]
    return {
        "tool": {"name": "codebase-scanner", "version": __version__},
        "root": root.resolve().name,
        "totals": {
            "files": len(files),
            "lines": sum(f.lines for f in files),
            "bytes": sum(f.size for f in files),
            "binary_files": sum(1 for f in files if f.binary),
            "oversize_files_not_read": sum(1 for f in files if not f.binary and f.text is None),
        },
        "structure": structure_summary(files),
        "languages": language_mix(files),
        "largest_files": [
            {"path": f.path, "bytes": f.size, "lines": f.lines, "language": f.language}
            for f in largest
        ],
        "manifests": summarize_manifests(files),
        "todos": todo_density(files),
        "dead_files": find_dead_files(files),
        "risks": scan_risks(files),
    }


def to_json(report: dict) -> str:
    return json.dumps(report, indent=2, sort_keys=False) + "\n"


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _table(headers: list[str], rows: list[list]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(" --- " for _ in headers) + "|"]
    lines += ["| " + " | ".join(_cell(v) for v in row) + " |" for row in rows]
    return lines + [""]


def to_markdown(report: dict, max_rows: int = 25) -> str:
    totals, structure = report["totals"], report["structure"]
    todos, risks = report["todos"], report["risks"]
    out = [
        f"# Codebase scan: {report['root']}",
        "",
        f"- Files: {totals['files']} in {structure['directories']} directories "
        f"(max depth {structure['max_depth']})",
        f"- Lines: {totals['lines']}, bytes: {totals['bytes']}, "
        f"binary files: {totals['binary_files']}",
        f"- TODO markers: {todos['total']} ({todos['per_kloc']} per 1000 lines of code)",
        f"- Likely dead files: {len(report['dead_files'])}",
        "- Risk findings: "
        + ", ".join(f"{risks['by_severity'][s]} {s}" for s in SEVERITIES),
        "",
        "## Structure",
        "",
    ]
    out += _table(
        ["Top level entry", "Files", "Lines", "Bytes"],
        [[e["name"], e["files"], e["lines"], e["bytes"]] for e in structure["top_level"]],
    )
    out += ["## Language mix", ""]
    out += _table(
        ["Language", "Files", "Lines", "Share of lines"],
        [[e["language"], e["files"], e["lines"], f"{e['percent_of_lines']}%"]
         for e in report["languages"]],
    )
    out += ["## Largest files", ""]
    out += _table(
        ["Path", "Bytes", "Lines", "Language"],
        [[f["path"], f["bytes"], f["lines"], f["language"]] for f in report["largest_files"]],
    )
    out += ["## Dependency manifests", ""]
    if not report["manifests"]:
        out += ["No dependency manifests found.", ""]
    for manifest in report["manifests"]:
        out += [
            f"### {manifest['path']} ({manifest['kind']})",
            "",
            f"{manifest['count']} dependencies, {manifest['unpinned']} not pinned to an exact version."
            + (f" Error: {manifest['error']}." if manifest["error"] else ""),
            "",
        ]
        if manifest["dependencies"]:
            out += _table(
                ["Name", "Spec", "Scope", "Pinned"],
                [[d["name"], d["spec"] or "(any)", d["scope"], "yes" if d["pinned"] else "no"]
                 for d in manifest["dependencies"][:max_rows]],
            )
    out += ["## TODO density", ""]
    tags = ", ".join(f"{tag}: {count}" for tag, count in todos["by_tag"].items()) or "none"
    out += [f"{todos['total']} markers across {todos['code_lines']} lines of code. By tag: {tags}.", ""]
    if todos["files"]:
        out += _table(
            ["Path", "Markers", "Lines", "Per 1000 lines"],
            [[f["path"], f["count"], f["lines"], f["per_kloc"]] for f in todos["files"][:max_rows]],
        )
    out += ["## Likely dead files", ""]
    if report["dead_files"]:
        out += _table(
            ["Path", "Language", "Lines", "Reason"],
            [[d["path"], d["language"], d["lines"], d["reason"]] for d in report["dead_files"]],
        )
    else:
        out += ["None found.", ""]
    out += ["## Risky patterns", ""]
    if risks["findings"]:
        out += _table(
            ["Severity", "Rule", "Location", "Excerpt"],
            [[f["severity"], f["rule"], f"{f['path']}:{f['line']}", f"`{f['excerpt']}`"]
             for f in risks["findings"][:max_rows]],
        )
        if risks["total"] > max_rows:
            out += [f"Showing {max_rows} of {risks['total']} findings. See the JSON report for all.", ""]
    else:
        out += ["None found.", ""]
    return "\n".join(out).rstrip("\n") + "\n"

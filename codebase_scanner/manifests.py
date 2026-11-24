"""Summarise dependency manifests: requirements files, pyproject.toml, package.json, go.mod."""

from __future__ import annotations

import json
import posixpath
import re
import tomllib

_REQ_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(?:\[[^\]]*\])?\s*(.*)$")
_NPM_EXACT_RE = re.compile(r"^=?v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.+-]+)?$")
_GO_REQ_RE = re.compile(r"^\s*(?:require\s+)?([\w./~-]+\.[\w./~-]+)\s+(v[\w.+-]+)")


def _dep(name: str, spec: str, scope: str, pinned: bool) -> dict:
    return {"name": name, "spec": spec, "scope": scope, "pinned": pinned}


def _parse_requirement(line: str, scope: str) -> dict | None:
    line = line.split("#", 1)[0].split(";", 1)[0].strip()
    if not line or line.startswith("-"):
        return None
    match = _REQ_RE.match(line)
    if not match:
        return None
    spec = match.group(2).strip()
    # "==1.*" and "==1.2,<2" style specs are ranges, not exact pins.
    pinned = spec.startswith("==") and "*" not in spec and "," not in spec
    return _dep(match.group(1), spec, scope, pinned)


def parse_requirements(text: str) -> list[dict]:
    deps = (_parse_requirement(line, "runtime") for line in text.splitlines())
    return [d for d in deps if d]


def parse_pyproject(text: str) -> list[dict]:
    project = tomllib.loads(text).get("project", {})
    deps = [_parse_requirement(line, "runtime") for line in project.get("dependencies", [])]
    for group, lines in sorted(project.get("optional-dependencies", {}).items()):
        deps.extend(_parse_requirement(line, f"optional:{group}") for line in lines)
    return [d for d in deps if d]


def parse_package_json(text: str) -> list[dict]:
    data = json.loads(text)
    deps = []
    for key, scope in (("dependencies", "runtime"), ("devDependencies", "dev")):
        for name, spec in sorted((data.get(key) or {}).items()):
            spec = str(spec)
            deps.append(_dep(name, spec, scope, bool(_NPM_EXACT_RE.match(spec.strip()))))
    return deps


def parse_go_mod(text: str) -> list[dict]:
    deps = []
    for line in text.splitlines():
        if line.startswith(("module ", "go ")):
            continue
        match = _GO_REQ_RE.match(line)
        if match:
            deps.append(_dep(match.group(1), match.group(2), "runtime", True))
    return deps


def _parser_for(filename: str):
    if filename == "package.json":
        return "npm", parse_package_json
    if filename == "pyproject.toml":
        return "pyproject", parse_pyproject
    if filename == "go.mod":
        return "go", parse_go_mod
    if filename.startswith("requirements") and filename.endswith(".txt"):
        return "pip", parse_requirements
    return None


def summarize_manifests(files) -> list[dict]:
    """One entry per manifest found, with its dependencies and an unpinned count."""
    results = []
    for info in files:
        found = _parser_for(posixpath.basename(info.path))
        if not found or info.text is None:
            continue
        kind, parser = found
        entry = {"path": info.path, "kind": kind, "dependencies": [], "error": None}
        try:
            entry["dependencies"] = parser(info.text)
        except (ValueError, AttributeError, TypeError) as exc:
            entry["error"] = f"could not parse: {type(exc).__name__}"
        entry["count"] = len(entry["dependencies"])
        entry["unpinned"] = sum(1 for d in entry["dependencies"] if not d["pinned"])
        results.append(entry)
    return results

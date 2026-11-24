"""Find Python and JavaScript/TypeScript files that nothing else in the repo imports.

The check is static and deliberately conservative: when an import could refer to
more than one file, every candidate is treated as used. Entry points, tests and
package markers are never reported.
"""

from __future__ import annotations

import ast
import posixpath
import re

PY_ENTRY_NAMES = frozenset(
    {"__init__.py", "__main__.py", "main.py", "setup.py", "conftest.py", "manage.py",
     "wsgi.py", "asgi.py", "noxfile.py", "fabfile.py"}
)
JS_EXTENSIONS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx")
TEST_DIRS = frozenset({"tests", "test", "__tests__", "spec"})
_MAIN_GUARD_RE = re.compile(r"""__name__\s*==\s*['"]__main__['"]""")
_JS_IMPORT_RE = re.compile(
    r"""(?:\bfrom\s+|\bimport\s+|\brequire\(\s*|\bimport\(\s*)['"]([^'"\n]+)['"]"""
)


def _is_test(path: str) -> bool:
    parts = path.split("/")
    name = parts[-1]
    stem = name.split(".")[0]
    return (
        any(p in TEST_DIRS for p in parts[:-1])
        or stem.startswith("test_")
        or stem.endswith("_test")
        or ".test." in name
        or ".spec." in name
    )


def _module_parts(path: str) -> list[str]:
    parts = path[: -len(".py")].split("/")
    return parts[:-1] if parts[-1] == "__init__" else parts


def python_imports(path: str, text: str) -> set[str]:
    """Dotted module names a Python file may import, relative imports resolved."""
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError):
        return set()
    package = path.split("/")[:-1]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base: list[str] = []
            if node.level:
                keep = len(package) - (node.level - 1)
                if keep < 0:
                    continue
                base = package[:keep]
            module = base + (node.module.split(".") if node.module else [])
            if module:
                names.add(".".join(module))
            names.update(".".join(module + [alias.name]) for alias in node.names)
    return names


def js_imports(path: str, text: str, known: set[str]) -> set[str]:
    """Repo files a JS/TS file imports through relative specifiers."""
    found: set[str] = set()
    for spec in _JS_IMPORT_RE.findall(text):
        if not spec.startswith("."):
            continue
        base = posixpath.normpath(posixpath.join(posixpath.dirname(path), spec))
        candidates = [base]
        candidates += [base + ext for ext in JS_EXTENSIONS]
        candidates += [posixpath.join(base, "index" + ext) for ext in JS_EXTENSIONS]
        found.update(c for c in candidates if c in known)
    return found


def _package_json_entries(files, js_paths: set[str]) -> set[str]:
    """JS files named anywhere in a package.json (main, bin, scripts and so on)."""
    entries: set[str] = set()
    for info in files:
        if posixpath.basename(info.path) != "package.json" or info.text is None:
            continue
        root = posixpath.dirname(info.path)
        for path in js_paths:
            rel = posixpath.relpath(path, root or ".")
            if not rel.startswith("..") and rel in info.text:
                entries.add(path)
    return entries


def find_dead_files(files) -> list[dict]:
    py = {f.path: f for f in files if f.path.endswith(".py") and f.text is not None}
    js = {f.path: f for f in files if f.path.endswith(JS_EXTENSIONS) and f.text is not None}

    # Index every dotted suffix so "src/pkg/mod.py" answers to "pkg.mod" and "mod".
    index: dict[str, set[str]] = {}
    for path in py:
        parts = _module_parts(path)
        for i in range(len(parts)):
            index.setdefault(".".join(parts[i:]), set()).add(path)

    imported: set[str] = set()
    for path, info in py.items():
        for name in python_imports(path, info.text):
            imported.update(index.get(name, set()) - {path})
    js_paths = set(js)
    for path, info in js.items():
        imported.update(js_imports(path, info.text, js_paths) - {path})

    entries = _package_json_entries(files, js_paths)
    dead = []
    for path, info in sorted({**py, **js}.items()):
        name = posixpath.basename(path)
        if path in imported or path in entries or _is_test(path):
            continue
        if path in py and (name in PY_ENTRY_NAMES or _MAIN_GUARD_RE.search(info.text)):
            continue
        if path in js and (name.split(".")[0] == "index" or ".config." in name):
            continue
        dead.append(
            {"path": path, "language": info.language, "lines": info.lines,
             "reason": "never imported by another file in the repository"}
        )
    return dead

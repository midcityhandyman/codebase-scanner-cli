"""Unit checks for the individual analyzers, built on small temporary repos."""

from codebase_scanner.deadfiles import find_dead_files, js_imports, python_imports
from codebase_scanner.manifests import (
    parse_go_mod,
    parse_pyproject,
    parse_requirements,
    summarize_manifests,
)
from codebase_scanner.report import build_report
from codebase_scanner.risks import scan_risks
from codebase_scanner.walker import walk


def make_repo(root, files: dict):
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8", newline="\n")
    return root


def test_walk_skips_vendored_dirs_and_flags_binary(tmp_path):
    make_repo(tmp_path, {
        "src/a.py": "x = 1\ny = 2",
        "node_modules/lib/index.js": "module.exports = 1;\n",
        ".git/config": "[core]\n",
        "logo.bin": b"\x00\x01\x02",
        "big.txt": "a" * 500,
    })
    files = {f.path: f for f in walk(tmp_path, max_file_bytes=100)}
    assert set(files) == {"src/a.py", "logo.bin", "big.txt"}
    assert files["src/a.py"].lines == 2
    assert files["logo.bin"].binary and files["logo.bin"].text is None
    assert files["big.txt"].text is None and not files["big.txt"].binary


def test_parse_requirements_handles_comments_extras_and_options():
    deps = parse_requirements(
        "# comment\n-r base.txt\nrequests[socks]>=2.31  # http\nflask==3.0.0\n"
        "tomli; python_version < '3.11'\n\n"
    )
    assert [(d["name"], d["spec"], d["pinned"]) for d in deps] == [
        ("requests", ">=2.31", False), ("flask", "==3.0.0", True), ("tomli", "", False),
    ]


def test_parse_pyproject_and_go_mod():
    deps = parse_pyproject(
        '[project]\nname = "demo"\ndependencies = ["httpx>=0.27"]\n'
        '[project.optional-dependencies]\ndev = ["pytest==8.2.0"]\n'
    )
    assert [(d["name"], d["scope"], d["pinned"]) for d in deps] == [
        ("httpx", "runtime", False), ("pytest", "optional:dev", True),
    ]
    go = parse_go_mod(
        "module example.com/demo\n\ngo 1.22\n\nrequire (\n\texample.com/lib v1.4.0\n)\n"
    )
    assert go == [{"name": "example.com/lib", "spec": "v1.4.0", "scope": "runtime", "pinned": True}]


def test_broken_manifest_is_reported_not_raised(tmp_path):
    make_repo(tmp_path, {"package.json": "{not json"})
    (manifest,) = summarize_manifests(walk(tmp_path))
    assert manifest["count"] == 0
    assert manifest["error"].startswith("could not parse")


def test_python_relative_imports_resolve_against_the_package():
    source = "from . import config\nfrom ..core.db import connect\nimport os.path\n"
    names = python_imports("pkg/api/views.py", source)
    assert {"pkg.api.config", "pkg.core.db", "pkg.core.db.connect", "os.path"} <= names
    assert python_imports("broken.py", "def (:\n") == set()


def test_js_imports_resolve_extensions_and_index_files():
    known = {"web/a.js", "web/lib/index.ts", "web/b.tsx"}
    source = (
        "import a from './a';\nimport './lib';\nconst b = require('./b.tsx');\n"
        "import React from 'react';\n"
    )
    assert js_imports("web/main.js", source, known) == known


def test_dead_file_rules(tmp_path):
    make_repo(tmp_path, {
        "src/pkg/__init__.py": "",
        "src/pkg/used.py": "VALUE = 1\n",
        "src/pkg/orphan.py": "VALUE = 2\n",
        "src/pkg/script.py": "if __name__ == '__main__':\n    print('run')\n",
        "src/pkg/app.py": "from pkg.used import VALUE\n",
        "tests/test_app.py": "import pkg.app\n",
        "ui/tool.js": "export const x = 1;\n",
        "ui/unused.ts": "export const y = 2;\n",
        "ui/vite.config.js": "export default {};\n",
        "ui/package.json": '{"bin": {"tool": "./tool.js"}}',
    })
    dead = [d["path"] for d in find_dead_files(walk(tmp_path))]
    assert dead == ["src/pkg/orphan.py", "ui/unused.ts"]


def test_placeholders_and_suppressed_lines_are_not_flagged(tmp_path):
    make_repo(tmp_path, {
        "settings.py": (
            'API_KEY = "your_api_key_here"\n'
            'PASSWORD = "${DB_PASSWORD}"\n'
            'SECRET = os.environ["SECRET"]\n'
            'TOKEN = "abcd1234efgh5678"  # scanner:ignore\n'
            'REAL_TOKEN = "abcd1234efgh5678"\n'
        ),
    })
    findings = scan_risks(walk(tmp_path))["findings"]
    assert [(f["rule"], f["line"]) for f in findings] == [("hardcoded-credential", 5)]
    assert findings[0]["excerpt"] == 'REAL_TOKEN = "abcd********"'


def test_other_risk_rules(tmp_path):
    make_repo(tmp_path, {
        "id_rsa.txt": "-----BEGIN OPENSSH PRIVATE KEY-----\n",
        "client.py": (
            "import pickle, yaml, requests\n"
            "requests.get(url, verify=False)\n"
            "pickle.loads(blob)\n"
            "yaml.load(text)\n"
            "yaml.load(text, Loader=yaml.SafeLoader)\n"
            "model.eval()\n"
        ),
        "page.js": "const run = new Function(code);\n",
    })
    found = {(f["rule"], f["path"], f["line"]) for f in scan_risks(walk(tmp_path))["findings"]}
    assert found == {
        ("private-key-block", "id_rsa.txt", 1),
        ("tls-verify-disabled", "client.py", 2),
        ("unsafe-deserialization", "client.py", 3),
        ("unsafe-deserialization", "client.py", 4),
        ("js-eval", "page.js", 1),
    }


def test_empty_directory_produces_an_empty_report(tmp_path):
    report = build_report(tmp_path)
    assert report["totals"]["files"] == 0
    assert report["todos"]["per_kloc"] == 0.0
    assert report["dead_files"] == [] and report["risks"]["total"] == 0

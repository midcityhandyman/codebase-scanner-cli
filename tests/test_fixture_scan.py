"""End to end checks: run the scanner on the bundled fixture repository."""

import json
from pathlib import Path

import pytest

from codebase_scanner.cli import main
from codebase_scanner.report import build_report, to_json, to_markdown

FIXTURE = Path(__file__).parent / "fixtures" / "sample_repo"
FAKE_SECRETS = (
    "fixture-not-a-real-password-123",
    "AKIAFAKEFIXTURE00000",
    "fixture-token-0000-not-real",
)


@pytest.fixture(scope="module")
def report():
    return build_report(FIXTURE)


def test_totals_and_structure(report):
    assert report["root"] == "sample_repo"
    assert report["totals"]["files"] == 15
    assert report["totals"]["binary_files"] == 0
    assert report["structure"]["max_depth"] == 1
    names = {entry["name"]: entry["files"] for entry in report["structure"]["top_level"]}
    assert names == {
        "app/": 6, "web/": 3, "(root files)": 3, "data/": 1, "scripts/": 1, "tests/": 1,
    }


def test_language_mix(report):
    by_language = {entry["language"]: entry for entry in report["languages"]}
    assert by_language["Python"]["files"] == 7
    assert by_language["JavaScript"]["files"] == 3
    assert by_language["Shell"]["files"] == 1
    assert round(sum(e["percent_of_lines"] for e in report["languages"])) == 100
    lines = [entry["lines"] for entry in report["languages"]]
    assert lines == sorted(lines, reverse=True)


def test_largest_files(report):
    largest = report["largest_files"]
    assert largest[0]["path"] == "data/price_list.csv"
    assert largest[0]["lines"] == 121
    sizes = [entry["bytes"] for entry in largest]
    assert sizes == sorted(sizes, reverse=True)
    assert len(build_report(FIXTURE, top_n=3)["largest_files"]) == 3


def test_manifest_summary(report):
    manifests = {m["path"]: m for m in report["manifests"]}
    assert set(manifests) == {"package.json", "requirements.txt"}
    pip = manifests["requirements.txt"]
    assert (pip["kind"], pip["count"], pip["unpinned"]) == ("pip", 3, 2)
    npm = manifests["package.json"]
    assert (npm["kind"], npm["count"], npm["unpinned"]) == ("npm", 3, 2)
    scopes = {d["name"]: d["scope"] for d in npm["dependencies"]}
    assert scopes == {"express": "runtime", "left-pad": "runtime", "jest": "dev"}


def test_todo_density(report):
    todos = report["todos"]
    assert todos["total"] == 6
    assert todos["by_tag"] == {"FIXME": 1, "HACK": 1, "TODO": 4}
    assert todos["files"][0] == {
        "path": "app/billing.py", "count": 2, "lines": 11, "per_kloc": 181.8,
    }
    assert todos["per_kloc"] == round(1000 * 6 / todos["code_lines"], 1)


def test_dead_files(report):
    assert [d["path"] for d in report["dead_files"]] == [
        "app/legacy_report.py",
        "web/old_widget.js",
    ]


def test_risky_patterns(report):
    risks = report["risks"]
    found = {(f["rule"], f["path"]) for f in risks["findings"]}
    assert found == {
        ("aws-access-key-id", "app/config.py"),
        ("hardcoded-credential", "app/config.py"),
        ("hardcoded-credential", "web/api.js"),
        ("python-eval-exec", "app/legacy_report.py"),
        ("subprocess-shell-true", "app/legacy_report.py"),
        ("js-inner-html", "web/old_widget.js"),
        ("debug-enabled", "app/config.py"),
    }
    assert risks["by_severity"] == {"high": 3, "medium": 2, "low": 2}
    assert risks["findings"][0]["severity"] == "high"
    password = next(f for f in risks["findings"] if "DB_PASSWORD" in f["excerpt"])
    assert password["line"] == 6


def test_secret_values_never_appear_in_output(report):
    markdown, as_json = to_markdown(report), to_json(report)
    for secret in FAKE_SECRETS:
        assert secret not in markdown
        assert secret not in as_json
    assert "AKIA********" in markdown


def test_markdown_has_every_section(report):
    markdown = to_markdown(report)
    for heading in (
        "# Codebase scan: sample_repo", "## Structure", "## Language mix",
        "## Largest files", "## Dependency manifests", "## TODO density",
        "## Likely dead files", "## Risky patterns",
    ):
        assert heading in markdown
    assert "| app/legacy_report.py | Python |" in markdown


def test_scan_is_deterministic():
    assert to_json(build_report(FIXTURE)) == to_json(build_report(FIXTURE))


def test_cli_prints_markdown_and_writes_both_files(tmp_path, capsys):
    assert main([str(FIXTURE), "--out", str(tmp_path)]) == 0
    assert capsys.readouterr().out.startswith("# Codebase scan: sample_repo")
    written = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert written == build_report(FIXTURE)
    assert (tmp_path / "report.md").read_text(encoding="utf-8").startswith("# Codebase scan")


def test_cli_json_format(capsys):
    assert main([str(FIXTURE), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["tool"]["name"] == "codebase-scanner"


def test_cli_fail_on_and_bad_path(tmp_path, capsys):
    assert main([str(FIXTURE), "--quiet", "--fail-on", "high"]) == 2
    (tmp_path / "clean.py").write_text("print('hello')\n", encoding="utf-8")
    assert main([str(tmp_path), "--quiet", "--fail-on", "low"]) == 0
    assert main([str(tmp_path / "missing"), "--quiet"]) == 1
    assert "not a directory" in capsys.readouterr().err

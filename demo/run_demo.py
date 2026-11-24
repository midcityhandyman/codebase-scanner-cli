"""Offline demo: scan the bundled fixture repo and show both output formats.

Run from the repository root:

    python demo/run_demo.py > demo/output.txt
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from codebase_scanner.report import build_report, to_markdown  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "sample_repo"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    report = build_report(FIXTURE)
    print("$ codebase-scanner tests/fixtures/sample_repo")
    print()
    print(to_markdown(report))
    print("$ codebase-scanner tests/fixtures/sample_repo --format json  (risks section only)")
    print()
    print(json.dumps({"risks": report["risks"]}, indent=2))
    print()
    print("$ codebase-scanner tests/fixtures/sample_repo --quiet --fail-on high; echo $?")
    print()
    print(2 if report["risks"]["by_severity"]["high"] else 0)


if __name__ == "__main__":
    main()

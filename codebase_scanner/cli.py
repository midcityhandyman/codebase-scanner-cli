"""Command line entry point."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .report import build_report, to_json, to_markdown
from .risks import SEVERITIES
from .walker import DEFAULT_MAX_FILE_BYTES


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="codebase-scanner",
        description="Scan a repository and report structure, language mix, largest files, "
        "dependency manifests, TODO density, likely dead files and risky patterns.",
    )
    parser.add_argument("path", nargs="?", default=".", help="repository to scan (default: .)")
    parser.add_argument("--format", choices=("markdown", "json"), default="markdown",
                        help="what to print to stdout (default: markdown)")
    parser.add_argument("--out", metavar="DIR",
                        help="also write report.md and report.json into DIR")
    parser.add_argument("--top", type=int, default=_env_int("CODEBASE_SCANNER_TOP_N", 10),
                        help="how many largest files to list (default: 10)")
    parser.add_argument("--max-file-bytes", type=int,
                        default=_env_int("CODEBASE_SCANNER_MAX_FILE_BYTES", DEFAULT_MAX_FILE_BYTES),
                        help="files larger than this are sized but not read")
    parser.add_argument("--fail-on", choices=SEVERITIES + ("none",), default="none",
                        help="exit with status 2 if a finding at or above this severity exists")
    parser.add_argument("--quiet", action="store_true", help="print nothing to stdout")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        report = build_report(args.path, top_n=args.top, max_file_bytes=args.max_file_bytes)
    except NotADirectoryError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    markdown, as_json = to_markdown(report), to_json(report)
    if args.out:
        out_dir = Path(args.out)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "report.md").write_text(markdown, encoding="utf-8", newline="\n")
        (out_dir / "report.json").write_text(as_json, encoding="utf-8", newline="\n")
    if not args.quiet:
        sys.stdout.write(as_json if args.format == "json" else markdown)

    if args.fail_on != "none":
        threshold = SEVERITIES.index(args.fail_on)
        counts = report["risks"]["by_severity"]
        if any(counts[s] for s in SEVERITIES[: threshold + 1]):
            return 2
    return 0

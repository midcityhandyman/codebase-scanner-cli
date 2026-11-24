"""Walk a repository once and load every text file into memory."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .languages import detect_language

IGNORED_DIRS = frozenset(
    {
        ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__",
        "dist", "build", "target", ".mypy_cache", ".pytest_cache", ".ruff_cache",
        ".tox", ".idea", ".vscode", "coverage", ".next",
    }
)
DEFAULT_MAX_FILE_BYTES = 1_000_000


@dataclass
class FileInfo:
    path: str  # posix path relative to the scan root
    size: int
    language: str
    lines: int = 0
    binary: bool = False
    text: str | None = None  # None for binary files and files over the size cap


def count_lines(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def walk(root: Path, max_file_bytes: int = DEFAULT_MAX_FILE_BYTES) -> list[FileInfo]:
    """Return every file under root, sorted by path, skipping vendored and cache dirs."""
    files: list[FileInfo] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            d for d in dirnames if d not in IGNORED_DIRS and not d.endswith(".egg-info")
        )
        for name in sorted(filenames):
            full = Path(dirpath) / name
            if full.is_symlink():
                continue
            try:
                size = full.stat().st_size
            except OSError:
                continue
            info = FileInfo(full.relative_to(root).as_posix(), size, detect_language(name))
            if size <= max_file_bytes:
                try:
                    raw = full.read_bytes()
                except OSError:
                    raw = b""
                if b"\0" in raw[:8192]:
                    info.binary = True
                else:
                    # utf-8-sig drops a leading byte order mark, which would
                    # otherwise make ast.parse reject the file.
                    info.text = raw.decode("utf-8-sig", errors="replace")
                    info.lines = count_lines(info.text)
            files.append(info)
    files.sort(key=lambda f: f.path)
    return files

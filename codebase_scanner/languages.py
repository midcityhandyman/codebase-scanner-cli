"""Map file names to languages and summarise the language mix."""

from __future__ import annotations

import os

EXTENSIONS = {
    ".py": "Python",
    ".js": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".h": "C",
    ".cpp": "C++",
    ".cs": "C#",
    ".sh": "Shell",
    ".ps1": "PowerShell",
    ".sql": "SQL",
    ".html": "HTML",
    ".css": "CSS",
    ".md": "Markdown",
    ".json": "JSON",
    ".yml": "YAML",
    ".yaml": "YAML",
    ".toml": "TOML",
    ".csv": "CSV",
    ".txt": "Text",
}

FILENAMES = {"Dockerfile": "Dockerfile", "Makefile": "Makefile"}

# Languages whose files count as source code for TODO density and risk rules.
CODE_LANGUAGES = frozenset(
    {
        "Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Ruby", "PHP",
        "C", "C++", "C#", "Shell", "PowerShell", "SQL", "Dockerfile", "Makefile",
    }
)


def detect_language(filename: str) -> str:
    if filename in FILENAMES:
        return FILENAMES[filename]
    ext = os.path.splitext(filename)[1].lower()
    return EXTENSIONS.get(ext, "Other")


def language_mix(files) -> list[dict]:
    """Per language file, line and byte counts, largest share of lines first."""
    buckets: dict[str, dict] = {}
    for info in files:
        bucket = buckets.setdefault(
            info.language, {"language": info.language, "files": 0, "lines": 0, "bytes": 0}
        )
        bucket["files"] += 1
        bucket["lines"] += info.lines
        bucket["bytes"] += info.size
    total_lines = sum(b["lines"] for b in buckets.values()) or 1
    for bucket in buckets.values():
        bucket["percent_of_lines"] = round(100.0 * bucket["lines"] / total_lines, 1)
    return sorted(buckets.values(), key=lambda b: (-b["lines"], b["language"]))

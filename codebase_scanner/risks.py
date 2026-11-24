"""Regex rules for risky patterns: hard coded secrets and unsafe calls.

Matched secret values are redacted before they reach any report, so a report
can be shared without leaking the thing it warns about.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .languages import CODE_LANGUAGES

SEVERITIES = ("high", "medium", "low")
SUPPRESS_MARKER = "scanner:ignore"
MAX_LINE_LENGTH = 1000  # skip minified or generated lines
_SCANNED_EXTRA = frozenset({"JSON", "YAML", "TOML", "Text", "Other"})
_PLACEHOLDER_RE = re.compile(
    r"(?i)^(\$\{|<|%\(|\{\{)|changeme|change_me|placeholder|example|your[_-]|dummy|^x+$|^\*+$"
)
_PY = frozenset({"Python"})
_JS = frozenset({"JavaScript", "TypeScript"})


@dataclass(frozen=True)
class Rule:
    id: str
    severity: str
    description: str
    pattern: re.Pattern
    languages: frozenset | None = None  # None means every scanned file
    secret_group: int | None = None  # regex group holding a value to redact


RULES = (
    Rule("aws-access-key-id", "high", "AWS access key id in source",
         re.compile(r"\b((?:AKIA|ASIA)[0-9A-Z]{16})\b"), None, 1),
    Rule("private-key-block", "high", "Private key material in source",
         re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----")),
    Rule("github-token", "high", "GitHub personal access token in source",
         re.compile(r"\b(gh[pousr]_[A-Za-z0-9]{36,})\b"), None, 1),
    Rule("hardcoded-credential", "high", "Credential assigned from a string literal",
         re.compile(
             r"""(?i)(?:password|passwd|pwd|secret|api[_-]?key|access[_-]?key|token)\w*["']?"""
             r"""\s*[:=]\s*["']([^"'\s]{8,})["']"""
         ), None, 1),
    Rule("python-eval-exec", "medium", "eval or exec on dynamic input",
         re.compile(r"(?<![\w.])(?:eval|exec)\("), _PY),
    Rule("subprocess-shell-true", "medium", "Subprocess call with shell=True",
         re.compile(r"shell\s*=\s*True"), _PY),
    Rule("unsafe-deserialization", "medium", "pickle or unsafe yaml load",
         re.compile(r"\bpickle\.loads?\(|\byaml\.load\((?![^)\n]*Loader)"), _PY),
    Rule("tls-verify-disabled", "medium", "TLS certificate verification disabled",
         re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false")),
    Rule("js-eval", "medium", "eval or Function constructor on dynamic input",
         re.compile(r"(?<![\w.])eval\(|new Function\("), _JS),
    Rule("js-inner-html", "low", "innerHTML assignment (possible XSS)",
         re.compile(r"\.innerHTML\s*\+?="), _JS),
    Rule("debug-enabled", "low", "Debug mode switched on in source",
         re.compile(r"\bDEBUG\s*=\s*True\b|debug\s*=\s*True\b"), _PY),
)


def redact(value: str) -> str:
    return value[:4] + "*" * 8


def _excerpt(line: str, match: re.Match, rule: Rule) -> str:
    if rule.secret_group is not None:
        start, end = match.span(rule.secret_group)
        line = line[:start] + redact(match.group(rule.secret_group)) + line[end:]
    return line.strip()[:120]


def scan_risks(files) -> dict:
    findings = []
    for info in files:
        if info.text is None:
            continue
        if info.language not in CODE_LANGUAGES and info.language not in _SCANNED_EXTRA:
            continue
        for number, line in enumerate(info.text.splitlines(), start=1):
            if len(line) > MAX_LINE_LENGTH or SUPPRESS_MARKER in line:
                continue
            specific_secret = False  # a named key format already explains this line
            for rule in RULES:
                if rule.languages is not None and info.language not in rule.languages:
                    continue
                match = rule.pattern.search(line)
                if not match:
                    continue
                if rule.id == "hardcoded-credential":
                    if specific_secret or _PLACEHOLDER_RE.search(match.group(1)):
                        continue
                elif rule.secret_group is not None:
                    specific_secret = True
                findings.append(
                    {"rule": rule.id, "severity": rule.severity,
                     "description": rule.description, "path": info.path,
                     "line": number, "excerpt": _excerpt(line, match, rule)}
                )
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["path"], f["line"], f["rule"]))
    by_severity = {s: sum(1 for f in findings if f["severity"] == s) for s in SEVERITIES}
    return {"total": len(findings), "by_severity": by_severity, "findings": findings}

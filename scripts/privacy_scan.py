#!/usr/bin/env python3
"""Fail when a release tree contains likely private paths, IDs, secrets, or images."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TEXT_SUFFIXES = {
    ".css",
    ".html",
    ".js",
    ".json",
    ".md",
    ".mjs",
    ".py",
    ".txt",
    ".yaml",
    ".yml",
}
IMAGE_SUFFIXES = {".gif", ".heic", ".jpeg", ".jpg", ".png", ".webp"}
SKIP_DIRS = {".git", "__pycache__", "node_modules"}


def forbidden_patterns() -> list[tuple[str, re.Pattern[str]]]:
    literal_values = {
        "macOS home path": "/" + "Users" + "/",
        "Windows home path": "C:" + "\\\\Users\\\\",
        "private workspace path": "Desktop" + "/GOBE",
    }
    patterns = [(name, re.compile(re.escape(value), re.IGNORECASE)) for name, value in literal_values.items()]
    patterns.extend(
        [
            ("ChatGPT conversation URL", re.compile(r"chatgpt\.com/c/[0-9a-f]{8}-[0-9a-f-]{20,}", re.I)),
            ("UUID-like identifier", re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b", re.I)),
            ("GitHub token", re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b")),
            ("API key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
            ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
            ("session token", re.compile(r"(?:session[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][^'\"]{12,}", re.I)),
        ]
    )
    return patterns


def iter_files(root: Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts):
            continue
        yield path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=".")
    args = parser.parse_args()
    root = Path(args.root).expanduser().resolve()
    self_path = Path(__file__).resolve()
    findings: list[str] = []
    patterns = forbidden_patterns()

    for path in iter_files(root):
        relative = path.relative_to(root)
        if path.suffix.lower() in IMAGE_SUFFIXES:
            findings.append(f"bundled image asset: {relative}")
        if path == self_path or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            findings.append(f"non-UTF-8 text file: {relative}")
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            for label, pattern in patterns:
                if pattern.search(line):
                    findings.append(f"{label}: {relative}:{line_number}")

    suspicious_names = ("manifest", "cleanup-receipt", "thread-cleanup", "cookies")
    for path in iter_files(root):
        lower = path.name.lower()
        if any(marker in lower for marker in suspicious_names):
            findings.append(f"runtime artifact name: {path.relative_to(root)}")

    if findings:
        print("Privacy scan failed:")
        for finding in sorted(set(findings)):
            print(f"- {finding}")
        return 1

    print(f"Privacy scan passed: {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

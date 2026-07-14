#!/usr/bin/env python3
"""Recursively list upload-ready reference images and remove exact duplicates."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
IGNORED_DIRS = {"originals", "__pycache__"}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Reference image directory")
    args = parser.parse_args()

    root = args.root.expanduser().resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    images: list[dict[str, str]] = []
    duplicates: list[dict[str, str]] = []
    seen: dict[str, str] = {}

    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name.startswith("."):
            continue
        if any(part in IGNORED_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue

        sha256 = digest(path)
        absolute_path = str(path.resolve())
        if sha256 in seen:
            duplicates.append({"path": absolute_path, "same_as": seen[sha256]})
            continue
        seen[sha256] = absolute_path
        images.append({"path": absolute_path, "sha256": sha256})

    print(
        json.dumps(
            {
                "root": str(root),
                "count": len(images),
                "images": images,
                "duplicates_skipped": duplicates,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if images else 2


if __name__ == "__main__":
    raise SystemExit(main())

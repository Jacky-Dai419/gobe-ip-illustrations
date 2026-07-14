#!/usr/bin/env python3
"""Run one GOBE IP illustration batch through logged-in ChatGPT Web."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_BROWSER_SCRIPT = Path.home() / ".codex/skills/gobe-chatgpt-chrome-image/scripts/chatgpt_chrome_image.py"
SUPPORTED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}


def parse_args() -> argparse.Namespace:
    skill_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Upload the IP reference group to logged-in ChatGPT Web, submit one batch, and download the results."
    )
    parser.add_argument("--prompt-file", required=True, type=Path)
    parser.add_argument("--plan-file", required=True, type=Path)
    parser.add_argument(
        "--reference-dir",
        action="append",
        type=Path,
        default=[],
        help="Reference directory; defaults to this Skill's references/ip. Repeat as needed.",
    )
    parser.add_argument("--reference-image", action="append", type=Path, default=[])
    parser.add_argument("--style-reference-dir", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--prefix", default="gobe-ip-illustrations")
    parser.add_argument("--timeout", type=int, default=3600)
    parser.add_argument("--settle-seconds", type=int, default=20)
    parser.add_argument("--upload-wait", type=int, default=8)
    parser.add_argument("--current-chat", action="store_true")
    parser.add_argument("--wechat-cover", action="store_true")
    parser.add_argument(
        "--keep-thread",
        action="store_true",
        help="Keep the ChatGPT task. By default it is permanently deleted after successful download.",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.set_defaults(skill_dir=skill_dir)
    return parser.parse_args()


def default_output_dir(skill_dir: Path, plan_file: Path) -> Path:
    plan = json.loads(plan_file.expanduser().resolve().read_text(encoding="utf-8"))
    slug = str(plan.get("demo") or "illustration-batch").strip() or "illustration-batch"
    return skill_dir / "runs" / f"{slug}-{datetime.now().strftime('%Y%m%d-%H%M%S')}"


def browser_script() -> Path:
    configured = os.environ.get("GOBE_CHATGPT_CHROME_IMAGE_SCRIPT")
    if configured:
        return Path(configured).expanduser().resolve()

    sibling = (
        Path(__file__).resolve().parents[2]
        / "gobe-chatgpt-chrome-image"
        / "scripts"
        / "chatgpt_chrome_image.py"
    )
    for candidate in (sibling, DEFAULT_BROWSER_SCRIPT):
        if candidate.is_file():
            return candidate.resolve()
    return DEFAULT_BROWSER_SCRIPT.resolve()


def has_identity_reference(directories: list[Path], files: list[Path]) -> bool:
    for file in files:
        path = file.expanduser().resolve()
        if path.is_file() and path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
            return True
    for directory in directories:
        root = directory.expanduser().resolve()
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            relative_parts = path.relative_to(root).parts[:-1]
            if "originals" in relative_parts:
                continue
            if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES:
                return True
    return False


def main() -> int:
    args = parse_args()
    atomic = browser_script()
    if not atomic.is_file():
        raise SystemExit(
            "Browser image Skill is not installed. Install the sibling gobe-chatgpt-chrome-image Skill "
            "or set GOBE_CHATGPT_CHROME_IMAGE_SCRIPT to its scripts/chatgpt_chrome_image.py."
        )

    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else default_output_dir(args.skill_dir, args.plan_file).resolve()
    )
    identity_references = args.reference_dir or [args.skill_dir / "references" / "ip"]
    if not has_identity_reference(identity_references, args.reference_image):
        raise SystemExit(
            "No compatible IP reference image was found. Add at least one PNG, JPG, JPEG, or WEBP "
            "to references/ip/source or pass --reference-image before running the batch."
        )
    references = [*identity_references, *args.style_reference_dir]

    command = [
        sys.executable,
        str(atomic),
        "run",
        "--prompt-file",
        str(args.prompt_file.expanduser().resolve()),
        "--plan-file",
        str(args.plan_file.expanduser().resolve()),
        "--output-dir",
        str(output_dir),
        "--prefix",
        args.prefix,
        "--limit",
        "10",
        "--timeout",
        str(args.timeout),
        "--settle-seconds",
        str(args.settle_seconds),
        "--upload-wait",
        str(args.upload_wait),
    ]
    for directory in references:
        command.extend(["--reference-dir", str(directory.expanduser().resolve())])
    for image in args.reference_image:
        command.extend(["--reference-image", str(image.expanduser().resolve())])
    if args.current_chat:
        command.append("--current-chat")
    if args.wechat_cover:
        command.append("--wechat-cover")
    if not args.keep_thread:
        command.append("--delete-chatgpt-thread")
    if args.dry_run:
        command.append("--dry-run")
    if args.json:
        command.append("--json")

    result = subprocess.run(command, check=False)
    return int(result.returncode)


if __name__ == "__main__":
    raise SystemExit(main())

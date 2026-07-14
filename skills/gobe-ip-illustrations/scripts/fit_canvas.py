#!/usr/bin/env python3

import argparse
from pathlib import Path

from PIL import Image, ImageColor, ImageOps


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fit an image to an exact canvas without stretching it."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--width", required=True, type=int)
    parser.add_argument("--height", required=True, type=int)
    parser.add_argument("--mode", choices=("contain", "cover"), default="contain")
    parser.add_argument("--background", default="#ffffff")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.width <= 0 or args.height <= 0:
        raise SystemExit("width and height must be positive")
    if not args.input.is_file():
        raise SystemExit(f"input file not found: {args.input}")

    background = ImageColor.getrgb(args.background)
    with Image.open(args.input) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        if args.mode == "cover":
            result = ImageOps.fit(
                source,
                (args.width, args.height),
                method=Image.Resampling.LANCZOS,
            )
        else:
            fitted = ImageOps.contain(
                source,
                (args.width, args.height),
                method=Image.Resampling.LANCZOS,
            )
            result = Image.new("RGB", (args.width, args.height), background)
            x = (args.width - fitted.width) // 2
            y = (args.height - fitted.height) // 2
            result.paste(fitted, (x, y))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    result.save(args.output, format="PNG", optimize=True)
    print(args.output.resolve())


if __name__ == "__main__":
    main()

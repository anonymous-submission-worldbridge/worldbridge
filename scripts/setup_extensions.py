#!/usr/bin/env python3
"""Apply the preserved local Infinigen changes to this checkout's dependency."""
import argparse
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Copy overlays into ./infinigen; default only checks prerequisites",
    )
    args = parser.parse_args()
    target = ROOT / "infinigen"
    if not (target / "infinigen/__init__.py").is_file():
        parser.error(
            "Install the Infinigen source checkout at ./infinigen first; see README.md"
        )
    if target.resolve().parent != ROOT.resolve():
        parser.error(
            "The dependency must be a real directory inside this checkout, not an external symlink"
        )
    files = sorted(p for p in (ROOT / "extensions/infinigen").rglob("*") if p.is_file())
    for source in files:
        relative = source.relative_to(ROOT / "extensions/infinigen")
        destination = target / relative
        if not destination.resolve().is_relative_to(target.resolve()):
            parser.error(
                f"Overlay destination escapes dependency directory: {relative}"
            )
        if args.apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
    print(
        f'{"Applied" if args.apply else "Ready to apply"} {len(files)} local Infinigen files'
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

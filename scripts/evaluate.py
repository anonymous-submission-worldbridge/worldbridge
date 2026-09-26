#!/usr/bin/env python3
"""Validate a generated urban descriptor using the original WorldBridge rules."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from worldbridge.urban.core import validate_descriptor


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Urban descriptor JSON from infer.py")
    args = parser.parse_args()
    try:
        errors = validate_descriptor(json.loads(args.input.read_text()))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        parser.error(str(exc))
    print(json.dumps({"valid": not errors, "errors": errors}, ensure_ascii=False))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())

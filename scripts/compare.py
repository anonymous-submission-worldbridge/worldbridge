#!/usr/bin/env python3
"""Dispatch to independent baseline CLIs without changing their arguments."""
import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from baselines.registry import ADAPTERS, adapter_path
from worldbridge.paths import ROOT, runtime_environment


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--method", choices=ADAPTERS, required=True)
    parser.add_argument(
        "arguments",
        nargs=argparse.REMAINDER,
        help="Arguments after -- go to the original adapter",
    )
    args = parser.parse_args()
    forwarded = args.arguments[1:] if args.arguments[:1] == ["--"] else args.arguments
    return subprocess.run(
        [sys.executable, str(adapter_path(args.method)), *forwarded],
        cwd=ROOT,
        env=runtime_environment(),
        check=False,
    ).returncode


if __name__ == "__main__":
    raise SystemExit(main())

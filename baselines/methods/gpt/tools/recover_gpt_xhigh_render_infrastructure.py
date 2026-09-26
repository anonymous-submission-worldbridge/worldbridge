#!/usr/bin/env python3
"""Resume one exhausted formal render through the disclosed /tmp sandbox mapping."""
from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import argparse
import fcntl
import json
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import baselines.methods.gpt.run_xhigh_matrix as matrix
import baselines.methods.gpt.tools.run_gpt_xhigh_accelerated as accelerated


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument("--gpu", type=int, required=True)
    args = parser.parse_args()

    matrix.verify_formal_lock()
    specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    spec = next((row for row in specs if row["spec_id"] == args.spec_id), None)
    if spec is None:
        raise ValueError("Unknown frozen spec")
    run = (
        accelerated.DATA_ROOT
        / args.domain
        / matrix.METHOD
        / args.spec_id
        / f"seed_{args.seed}"
    )
    manifest = json.loads((run / "run_manifest.json").read_text())
    if manifest.get("failure_class") != "infrastructure" or not manifest.get(
        "build_success"
    ):
        raise RuntimeError("Recovery target is not a built infrastructure failure")
    if len(manifest.get("render_attempts", [])) >= 3:
        raise RuntimeError("Frozen three-attempt render allowance is exhausted")

    accelerated.SANDBOX_RUN.mkdir(parents=True, exist_ok=True)
    if accelerated.SANDBOX_RUN.is_symlink() or any(accelerated.SANDBOX_RUN.iterdir()):
        raise RuntimeError("Blender sandbox mount point must be empty")
    guard_path = ROOT / "results/gpt6_astra_xhigh/matrix.lock"
    with guard_path.open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        matrix.run_process = accelerated.operational_run_process
        result = accelerated.operational_task(
            spec, args.seed, accelerated.DATA_ROOT, args.gpu, "render"
        )
    if not result.get("render_success"):
        raise RuntimeError("Infrastructure recovery did not produce a valid render")
    print(
        json.dumps(
            {
                "status": "recovered",
                "domain": args.domain,
                "spec_id": args.spec_id,
                "seed": args.seed,
                "gpu": args.gpu,
                "render_attempts": len(result.get("render_attempts", [])),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit the frozen Infinigen Indoors Table-2 matrix without changing outputs."""

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
import json
from collections import defaultdict
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
SPECS = BASELINES / "protocol/generation/indoor_specs.jsonl"

PROTOCOL_SHA256 = "46990b34f92a2400e616d22ede1cb49a7e0fb1cb218368e9f67693f9202adeda"
ADAPTER_SHA256 = "5a7fb2c79c4c64333532908526f17a6551c1cf89f74421e0217582f4e4b56ed5"
RENDERER_SHA256 = "24debbb209c54722a1ef72eac31501ec5e5fa9f50d577412cd78445ae42b91cb"


def load_specs() -> list[str]:
    with SPECS.open(encoding="utf-8") as handle:
        return [json.loads(line)["spec_id"] for line in handle if line.strip()]


def is_formal_generate(attempt: dict) -> bool:
    return (
        attempt.get("phase") == "generate"
        and attempt.get("protocol_sha256") == PROTOCOL_SHA256
        and attempt.get("adapter_sha256") == ADAPTER_SHA256
    )


def is_formal_render(attempt: dict) -> bool:
    return (
        attempt.get("phase") == "render"
        and attempt.get("protocol_sha256") == PROTOCOL_SHA256
        and attempt.get("adapter_sha256") == ADAPTER_SHA256
        and attempt.get("renderer_sha256") == RENDERER_SHA256
    )


def attempt_has_traceback(run_dir: Path, attempt: dict) -> bool:
    log = attempt.get("log")
    if not log:
        return False
    try:
        return "Traceback (most recent call last):" in (run_dir / log).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False


def classify(run_dir: Path) -> str:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return "not_started"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return "started_or_active"

    attempts = manifest.get("attempts", [])
    formal_generate = [item for item in attempts if is_formal_generate(item)]
    formal_render = [item for item in attempts if is_formal_render(item)]
    good_generate = any(item.get("success") is True for item in formal_generate)
    good_render = any(item.get("success") is True for item in formal_render)

    if (run_dir / "SUCCESS").exists() and good_generate and good_render:
        return "formal_success"

    if formal_render:
        last = formal_render[-1]
        if (
            good_generate
            and last.get("success") is False
            and last.get("timed_out") is False
            and last.get("exit_code") == 0
            and not attempt_has_traceback(run_dir, last)
        ):
            return "quality_failure"
        if good_generate and last.get("success") is False:
            return "infrastructure_candidate"

    if formal_generate:
        last = formal_generate[-1]
        if last.get("success") is False:
            return "infrastructure_candidate"
        if last.get("success") is True and not formal_render:
            return "started_or_active"

    if (run_dir / "SUCCESS").exists() or (run_dir / "GENERATION_SUCCESS").exists():
        return "stale_pilot"
    return "started_or_active"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--json", action="store_true", help="Print machine-readable output"
    )
    args = parser.parse_args()

    groups: dict[str, list[str]] = defaultdict(list)
    for spec_id in load_specs():
        for seed in range(4):
            run_id = f"{spec_id}/seed_{seed}"
            groups[classify(DATA_ROOT / run_id)].append(run_id)

    order = [
        "formal_success",
        "quality_failure",
        "infrastructure_candidate",
        "stale_pilot",
        "started_or_active",
        "not_started",
    ]
    result = {
        "total": sum(len(groups[key]) for key in order),
        "counts": {key: len(groups[key]) for key in order},
        "runs": {key: groups[key] for key in order},
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"total: {result['total']}")
        for key in order:
            print(f"{key}: {len(groups[key])}")
            for run_id in groups[key]:
                print(f"  {run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

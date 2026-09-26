#!/usr/bin/env python3
"""Run the frozen Medium Urban WorldScore evaluator on disjoint GPU lanes."""
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
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import subprocess
import sys


BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE), str((BASE / "methods"))]
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.run_medium_metrics import check_consistency_records


METHOD = "gpt6_astra_medium"
DOMAIN = "urban"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def verify_lock() -> dict:
    lock = json.loads(
        (
            (BASE / "methods/gpt/protocol/generation/gpt6_astra_medium.lock.json")
        ).read_text()
    )
    for relative, expected in lock["files_sha256"].items():
        if digest(BASE / relative) != expected:
            raise RuntimeError("Frozen Medium source changed: " + relative)
    for relative, expected in lock.get("evaluation_amendments_sha256", {}).items():
        if digest(BASE / relative) != expected:
            raise RuntimeError("Medium evaluation amendment changed: " + relative)
    return lock


def run_lane(root: Path, lane_index: int, gpu: int, specs: list[dict]) -> dict:
    lane = root / f"lane_{lane_index:02d}_gpu_{gpu}"
    lane.mkdir(parents=True, exist_ok=False)
    spec_file = lane / "specs.jsonl"
    spec_file.write_text(
        "".join(json.dumps(spec, ensure_ascii=False) + "\n" for spec in specs),
        encoding="utf-8",
    )
    output = lane / "consistency_per_scene.jsonl"
    command = [
        str(BASE / "envs/worldscore/bin/python"),
        str((BASE / "evaluation/visual/eval_worldscore_gpt_high_frozen.py")),
        "--data-root",
        str(BASE / "data/table2"),
        "--spec-file",
        str(spec_file),
        "--method",
        METHOD,
        "--domain",
        DOMAIN,
        "--gpu",
        str(gpu),
        "--output",
        str(output),
    ]
    environment = dict(os.environ)
    environment.pop("CUDA_VISIBLE_DEVICES", None)
    environment.update(
        PYTHONPATH=str(BASE / "work/metaurban/worldscore_abi"),
        TORCH_HOME=str(BASE / "cache/torch"),
        HF_HOME=str(BASE / "cache/huggingface"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        XDG_CACHE_HOME=str(BASE / "cache/xdg_metrics"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        TMPDIR=str(BASE / "tmp"),
    )
    with (lane / "worldscore.log").open("w") as log:
        completed = subprocess.run(
            command,
            cwd=BASE.parent,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode:
        raise RuntimeError(
            f"WorldScore lane {lane_index} failed with {completed.returncode}"
        )
    rows = load_jsonl(output)
    expected = {(spec["spec_id"], seed) for spec in specs for seed in range(4)}
    actual = {(row["spec_id"], row["logical_seed"]) for row in rows}
    if len(rows) != len(expected) or actual != expected:
        raise RuntimeError(f"Incomplete WorldScore lane {lane_index}")
    return {
        "lane": lane_index,
        "gpu": gpu,
        "spec_ids": [spec["spec_id"] for spec in specs],
        "command": command,
        "output": str(output.relative_to(BASE)),
        "output_sha256": digest(output),
        "records": len(rows),
        "exit_code": completed.returncode,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 2, 3])
    args = parser.parse_args()
    if len(args.gpus) != len(set(args.gpus)) or not args.gpus:
        raise ValueError("GPU lanes must be unique and nonempty")
    lock = verify_lock()
    specs = load_jsonl((BASE / "protocol/generation/urban_specs.jsonl"))
    lanes = [specs[index :: len(args.gpus)] for index in range(len(args.gpus))]
    root = BASE / "results/gpt6_astra_medium/formal/urban/worldscore_parallel_20260913"
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "started_at_utc": utc(),
        "method": METHOD,
        "domain": DOMAIN,
        "strategy": "disjoint spec shards using the unchanged frozen High WorldScore evaluator",
        "evaluator_sha256": lock["files_sha256"][
            "evaluation/visual/eval_worldscore_gpt_high_frozen.py"
        ],
        "lanes": [],
    }
    write_json(root / "execution.json", report)
    with ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = {
            pool.submit(run_lane, root, index, gpu, lane_specs): index
            for index, (gpu, lane_specs) in enumerate(zip(args.gpus, lanes))
        }
        for future in as_completed(futures):
            result = future.result()
            report["lanes"].append(result)
            report["lanes"].sort(key=lambda row: row["lane"])
            write_json(root / "execution.json", report)
            print(
                f"MEDIUM_WORLDSCORE_LANE_DONE lane={result['lane']} gpu={result['gpu']}",
                flush=True,
            )

    by_key: dict[tuple[str, int], dict] = {}
    for lane in report["lanes"]:
        for row in load_jsonl(BASE / lane["output"]):
            key = (row["spec_id"], row["logical_seed"])
            if key in by_key:
                raise RuntimeError("Duplicate WorldScore record: " + repr(key))
            by_key[key] = row
    expected = [(spec["spec_id"], seed) for spec in specs for seed in range(4)]
    if set(by_key) != set(expected) or len(by_key) != 100:
        raise RuntimeError("Parallel WorldScore merge is incomplete")
    rows = [by_key[key] for key in expected]
    if any(row.get("method") != METHOD or row.get("domain") != DOMAIN for row in rows):
        raise RuntimeError("Foreign WorldScore record")
    check_consistency_records(rows, BASE / "data/table2", DOMAIN)
    output = BASE / "results/gpt6_astra_medium/formal/urban/consistency_per_scene.jsonl"
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    temporary.replace(output)
    report.update(
        ended_at_utc=utc(),
        status="complete",
        merged_output=str(output.relative_to(BASE)),
        merged_sha256=digest(output),
        records=len(rows),
        successful_records=sum(bool(row.get("success")) for row in rows),
    )
    write_json(root / "execution.json", report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("status", "records", "successful_records", "merged_sha256")
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

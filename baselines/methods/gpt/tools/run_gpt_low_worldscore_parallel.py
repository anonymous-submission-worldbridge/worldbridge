#!/usr/bin/env python3
"""Resume Low Urban WorldScore on disjoint GPU lanes without repeating completed specs."""
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
from baselines.methods.gpt.adapter_low import digest
from baselines.methods.gpt.adapter_low import utc
from baselines.methods.gpt.adapter_low import write_json
from baselines.methods.gpt.run_low_metrics import check_consistency_records
from baselines.methods.gpt.run_low_metrics import verify_evaluation_lock


METHOD = "gpt6_astra_low"
DOMAIN = "urban"


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def metric_path(spec_id: str, seed: int) -> Path:
    return (
        BASE
        / "data/table2"
        / DOMAIN
        / METHOD
        / spec_id
        / f"seed_{seed}"
        / "metrics/consistency_3d.json"
    )


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
    parser.add_argument("--gpus", type=int, nargs="+", default=[4, 5])
    args = parser.parse_args()
    if len(args.gpus) != len(set(args.gpus)) or not args.gpus:
        raise ValueError("GPU lanes must be unique and nonempty")
    verify_evaluation_lock()
    specs = load_jsonl((BASE / "protocol/generation/urban_specs.jsonl"))
    complete_specs = []
    pending_specs = []
    existing_records = []
    for spec in specs:
        paths = [metric_path(spec["spec_id"], seed) for seed in range(4)]
        present = [path.exists() for path in paths]
        if all(present):
            complete_specs.append(spec["spec_id"])
            existing_records.extend(json.loads(path.read_text()) for path in paths)
        elif any(present):
            raise RuntimeError(
                "Partial completed spec would require duplicate scoring: "
                + spec["spec_id"]
            )
        else:
            pending_specs.append(spec)
    lanes = [pending_specs[index :: len(args.gpus)] for index in range(len(args.gpus))]
    root = BASE / "results/gpt6_astra_low/formal/urban/worldscore_parallel_20260915"
    root.mkdir(parents=True, exist_ok=False)
    report = {
        "started_at_utc": utc(),
        "method": METHOD,
        "domain": DOMAIN,
        "strategy": "resume complete specs and score remaining disjoint spec shards with the unchanged frozen High WorldScore evaluator",
        "completed_specs_reused": complete_specs,
        "completed_records_reused": len(existing_records),
        "lanes": [],
    }
    write_json(root / "execution.json", report)
    with ThreadPoolExecutor(max_workers=len(args.gpus)) as pool:
        futures = {
            pool.submit(run_lane, root, index, gpu, lane_specs): index
            for index, (gpu, lane_specs) in enumerate(zip(args.gpus, lanes))
            if lane_specs
        }
        for future in as_completed(futures):
            result = future.result()
            report["lanes"].append(result)
            report["lanes"].sort(key=lambda row: row["lane"])
            write_json(root / "execution.json", report)
            print(
                f"LOW_WORLDSCORE_LANE_DONE lane={result['lane']} gpu={result['gpu']}",
                flush=True,
            )

    rows = []
    for spec in specs:
        for seed in range(4):
            path = metric_path(spec["spec_id"], seed)
            if not path.exists():
                raise RuntimeError(
                    "Missing WorldScore artifact after merge: " + str(path)
                )
            rows.append(json.loads(path.read_text()))
    check_consistency_records(rows, BASE / "data/table2", DOMAIN, specs, list(range(4)))
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    result_root = BASE / "results/gpt6_astra_low/formal/urban"
    for name in ("consistency_raw.jsonl", "consistency_per_scene.jsonl"):
        output = result_root / name
        temporary = output.with_suffix(output.suffix + ".tmp")
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(output)
    report.update(
        ended_at_utc=utc(),
        status="complete",
        merged_output=str(
            (result_root / "consistency_per_scene.jsonl").relative_to(BASE)
        ),
        merged_sha256=digest(result_root / "consistency_per_scene.jsonl"),
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

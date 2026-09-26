#!/usr/bin/env python3
"""Run shared frozen Table-2 metrics for Gemini 3.1 Pro terminal matrices."""
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
import math
import os
from pathlib import Path
import subprocess
import sys
import time


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gemini.adapter import confined
from baselines.methods.gemini.adapter import digest
from baselines.methods.gemini.adapter import utc
from baselines.methods.gemini.adapter import write_json


def verify_lock() -> None:
    lock_path = ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
    if not lock_path.exists():
        raise RuntimeError(
            "Formal metrics require methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
        )
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen evaluation source changed: " + relative)


def wait_gpu(gpu: int, required_mib: int) -> None:
    while True:
        result = subprocess.run(
            [
                "nvidia-smi",
                f"--id={gpu}",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        free = int(result.stdout.strip())
        if free >= required_mib:
            return
        print(
            f"METRIC_WAIT gpu={gpu} free_mib={free} required_free_mib={required_mib}",
            flush=True,
        )
        time.sleep(15)


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def filter_scene_rows(
    path: Path, output: Path, wanted: set[tuple[str, int]]
) -> list[dict]:
    rows = [
        row
        for row in read_jsonl(path)
        if (row.get("spec_id"), row.get("logical_seed")) in wanted
    ]
    keys = {(row["spec_id"], row["logical_seed"]) for row in rows}
    if len(rows) != len(wanted) or keys != wanted:
        raise RuntimeError(
            "Metric output is incomplete or contains duplicate slots: " + str(path)
        )
    output.write_text("".join(json.dumps(row) + "\n" for row in rows))
    return rows


def check_consistency(rows: list[dict], data_root: Path, domain: str) -> None:
    for row in rows:
        if not math.isfinite(float(row["consistency_3d"])):
            raise RuntimeError("Non-finite WorldScore result")
        if row.get("success"):
            continue
        run = (
            data_root / domain / METHOD / row["spec_id"] / f"seed_{row['logical_seed']}"
        )
        manifest = json.loads((run / "run_manifest.json").read_text())
        if (
            row.get("failure_reason") == "missing_or_invalid_render"
            and manifest.get("failure_class") == "quality"
        ):
            continue
        if row.get(
            "failure_reason"
        ) == "droid_slam_failed" and "returned no valid reprojection errors" in row.get(
            "failure_detail", ""
        ):
            continue
        raise RuntimeError(
            "WorldScore failure requires triage before ITT aggregation: " + str(run)
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--gpu", type=int, default=1)
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=["iqa", "semantics", "consistency", "diversity", "annotations"],
        default=["iqa", "semantics", "consistency", "diversity", "annotations"],
    )
    args = parser.parse_args()
    default_root = ROOT / ("data/gemini_3_1_pro_pilot" if args.pilot else "data/table2")
    data_root = confined(args.data_root or default_root)
    if args.pilot and data_root != ROOT / "data/gemini_3_1_pro_pilot":
        raise ValueError("Pilot metrics require the dedicated pilot root")
    if not args.pilot:
        verify_lock()

    all_specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    specs = [
        spec for spec in all_specs if not args.pilot or spec["spec_index"] % 5 == 0
    ]
    seeds = [0, 1] if args.pilot else list(range(4))
    wanted = {(spec["spec_id"], seed) for spec in specs for seed in seeds}
    for spec_id, seed in sorted(wanted):
        run = data_root / args.domain / METHOD / spec_id / f"seed_{seed}"
        manifest_path = run / "run_manifest.json"
        if not manifest_path.exists():
            raise RuntimeError("Refusing to score unstarted run: " + str(run))
        manifest = json.loads(manifest_path.read_text())
        if (
            not (run / "SUCCESS").exists()
            and manifest.get("failure_class") != "quality"
        ):
            raise RuntimeError("Run is not terminal: " + str(run))

    output = (
        ROOT
        / "results/gemini_3_1_pro"
        / ("pilot" if args.pilot else "formal")
        / args.domain
    )
    output.mkdir(parents=True, exist_ok=True)
    source_spec_file = ROOT / f"protocol/generation/{args.domain}_specs.jsonl"
    spec_file = source_spec_file
    if args.pilot:
        spec_file = output / "pilot_specs.jsonl"
        spec_file.write_text("".join(json.dumps(spec) + "\n" for spec in specs))

    environment = dict(os.environ)
    environment.update(
        CUDA_VISIBLE_DEVICES=str(args.gpu),
        TORCH_HOME=str(ROOT / "cache/torch"),
        HF_HOME=str(ROOT / "cache/huggingface"),
        HF_HUB_OFFLINE="1",
        TRANSFORMERS_OFFLINE="1",
        XDG_CACHE_HOME=str(ROOT / "cache/xdg_metrics"),
        PYTHONDONTWRITEBYTECODE="1",
        PYTHONUNBUFFERED="1",
        TMPDIR=str(ROOT / "tmp"),
    )
    python = str(ROOT / "envs/worldscore/bin/python")
    common = [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(spec_file),
        "--method",
        METHOD,
        "--domain",
        args.domain,
    ]
    commands = {
        "iqa": [
            python,
            str((ROOT / "evaluation/visual/eval_iqa.py")),
            *common,
            "--device",
            "cuda",
            "--output",
            str(output / "iqa_raw.jsonl"),
        ],
        "semantics": [
            python,
            str((ROOT / "evaluation/visual/generate_semantics.py")),
            *common,
            "--device",
            "cuda",
            "--batch-size",
            "8",
            "--metadata-output",
            str(output / "semantic_model.json"),
        ],
        "consistency": [
            python,
            str((ROOT / "evaluation/visual/eval_worldscore_gpt_high_frozen.py")),
            *common,
            "--gpu",
            str(args.gpu),
            "--output",
            str(output / "consistency_raw.jsonl"),
        ],
        "diversity": [
            python,
            str((ROOT / "evaluation/visual/eval_diversity.py")),
            *common,
            "--device",
            "cuda",
            "--output",
            str(output / "diversity_per_spec.jsonl"),
        ],
        "annotations": [
            sys.executable,
            str(
                (ROOT / "methods/gpt/tools/make_annotation_package_gpt_high_frozen.py")
            ),
            *common,
            "--output",
            str(ROOT / "annotations/gemini_3_1_pro" / args.domain),
        ],
    }
    report = {
        "started_at_utc": utc(),
        "pilot": args.pilot,
        "data_root": str(data_root),
        "stages": [],
    }
    requirements = {
        "iqa": 18432,
        "semantics": 4096,
        "consistency": 8192,
        "diversity": 4096,
    }
    for stage in args.stages:
        if args.pilot and stage == "annotations":
            continue
        annotation_root = ROOT / "annotations/gemini_3_1_pro" / args.domain
        if stage == "annotations" and annotation_root.exists():
            raise RuntimeError(
                "Annotation package already exists; refusing to overwrite ratings"
            )
        if stage != "annotations":
            wait_gpu(args.gpu, requirements[stage])
        stage_environment = dict(environment)
        if stage == "consistency":
            stage_environment.pop("CUDA_VISIBLE_DEVICES", None)
            stage_environment["PYTHONPATH"] = str(
                ROOT / "work/metaurban/worldscore_abi"
            )
        log_path = output / f"{stage}.log"
        print(f"METRIC_START {stage} {args.domain} gpu={args.gpu}", flush=True)
        with log_path.open("w") as log:
            completed = subprocess.run(
                commands[stage],
                cwd=ROOT.parent,
                env=stage_environment,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        report["stages"].append(
            {
                "stage": stage,
                "exit_code": completed.returncode,
                "command": commands[stage],
                "ended_at_utc": utc(),
            }
        )
        write_json(output / "execution.json", report)
        if completed.returncode:
            print(log_path.read_text()[-4500:], flush=True)
            raise RuntimeError(f"{stage} failed; see {output}")
        if stage == "iqa":
            filter_scene_rows(
                output / "iqa_raw.jsonl", output / "iqa_per_scene.jsonl", wanted
            )
        elif stage == "consistency":
            rows = filter_scene_rows(
                output / "consistency_raw.jsonl",
                output / "consistency_per_scene.jsonl",
                wanted,
            )
            check_consistency(rows, data_root, args.domain)
        print(f"METRIC_DONE {stage} {args.domain}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

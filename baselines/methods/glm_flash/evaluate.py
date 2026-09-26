#!/usr/bin/env python3
"""Run the shared frozen Table-2 metrics for GLM-5.3 Flash."""
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
METHOD = "glm53_flash"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.glm_flash.adapter import confined
from baselines.methods.glm_flash.adapter import digest
from baselines.methods.glm_flash.adapter import utc
from baselines.methods.glm_flash.adapter import write_json


def verify_formal_lock():
    lock_path = ROOT / "methods/glm_flash/protocol/generation/glm53_flash.lock.json"
    if not lock_path.exists():
        raise RuntimeError(
            "Formal metrics require methods/glm_flash/protocol/generation/glm53_flash.lock.json"
        )
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen source changed: " + relative)


def check_consistency_records(rows, data_root, domain, selected_specs, seeds):
    expected = {(spec["spec_id"], seed) for spec in selected_specs for seed in seeds}
    actual = {(row["spec_id"], row["logical_seed"]) for row in rows}
    if actual != expected or len(rows) != len(expected):
        raise RuntimeError("Incomplete or foreign WorldScore records")
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
        raise RuntimeError("WorldScore failure requires triage: " + str(run))


def wait_gpu(gpu, required):
    while True:
        completed = subprocess.run(
            [
                "nvidia-smi",
                "-i",
                str(gpu),
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if int(completed.stdout.strip()) >= required:
            return
        print(f"METRIC_WAIT gpu={gpu} required_free_mib={required}", flush=True)
        time.sleep(15)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--data-root", type=Path)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=["iqa", "semantics", "consistency", "diversity", "annotations"],
        default=["iqa", "semantics", "consistency", "diversity", "annotations"],
    )
    args = parser.parse_args()
    data_root = confined(
        args.data_root
        or ROOT / ("data/glm53_flash_pilot" if args.pilot else "data/table2")
    )
    if args.pilot and data_root != ROOT / "data/glm53_flash_pilot":
        raise ValueError("Pilot metrics require the dedicated pilot root")
    if not args.pilot:
        verify_formal_lock()
    all_specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    selected_specs = [
        spec for spec in all_specs if not args.pilot or spec["spec_index"] % 5 == 0
    ]
    seeds = [0, 1] if args.pilot else list(range(4))
    for spec in selected_specs:
        for seed in seeds:
            run = data_root / args.domain / METHOD / spec["spec_id"] / f"seed_{seed}"
            if not (run / "run_manifest.json").exists():
                raise RuntimeError("Refusing to score unstarted run: " + str(run))
            manifest = json.loads((run / "run_manifest.json").read_text())
            if (
                not (run / "SUCCESS").exists()
                and manifest.get("failure_class") != "quality"
            ):
                raise RuntimeError("Run is not terminal: " + str(run))

    output = (
        ROOT
        / "results/glm53_flash"
        / ("pilot" if args.pilot else "formal")
        / args.domain
    )
    output.mkdir(parents=True, exist_ok=True)
    selector_file = ROOT / f"protocol/generation/{args.domain}_specs.jsonl"
    if args.pilot:
        selector_file = output / "pilot_specs.jsonl"
        selector_file.write_text(
            "".join(json.dumps(spec) + "\n" for spec in selected_specs)
        )
    environment = dict(os.environ)
    for secret in ("GLM53_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY"):
        environment.pop(secret, None)
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
        str(selector_file),
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
            str(ROOT / "annotations/glm53_flash" / args.domain),
        ],
    }
    report = {
        "started_at_utc": utc(),
        "pilot": args.pilot,
        "data_root": str(data_root),
        "stages": [],
    }
    for stage in args.stages:
        if args.pilot and stage == "annotations":
            continue
        annotation_dir = ROOT / "annotations/glm53_flash" / args.domain
        if stage == "annotations" and annotation_dir.exists():
            raise RuntimeError("Annotation package already exists; refusing overwrite")
        if stage != "annotations":
            wait_gpu(
                args.gpu,
                {
                    "iqa": 18432,
                    "semantics": 4096,
                    "consistency": 8192,
                    "diversity": 4096,
                }[stage],
            )
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
        if stage in {"iqa", "consistency"}:
            raw_name = "iqa_raw.jsonl" if stage == "iqa" else "consistency_raw.jsonl"
            final_name = (
                "iqa_per_scene.jsonl"
                if stage == "iqa"
                else "consistency_per_scene.jsonl"
            )
            rows = [
                json.loads(line)
                for line in (output / raw_name).read_text().splitlines()
                if line
            ]
            wanted = {
                (spec["spec_id"], seed) for spec in selected_specs for seed in seeds
            }
            rows = [
                row for row in rows if (row["spec_id"], row["logical_seed"]) in wanted
            ]
            (output / final_name).write_text(
                "".join(json.dumps(row) + "\n" for row in rows)
            )
            if stage == "consistency":
                check_consistency_records(
                    rows, data_root, args.domain, selected_specs, seeds
                )
        print(f"METRIC_DONE {stage} {args.domain}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

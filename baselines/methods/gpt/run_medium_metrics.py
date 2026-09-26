#!/usr/bin/env python3
"""Run the frozen Table-2 metrics only for GPT-6 Astra Medium."""
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
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import confined
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json

METHOD = "gpt6_astra_medium"
CONFIG = ROOT / "methods/gpt/protocol/generation/gpt6_astra_medium.json"
LOCK = ROOT / "methods/gpt/protocol/generation/gpt6_astra_medium.lock.json"


def verify_lock() -> dict:
    lock = json.loads(LOCK.read_text())
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen Medium evaluation source changed: " + relative)
    return lock


def check_consistency_records(rows: list[dict], data_root: Path, domain: str) -> None:
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
            "WorldScore failure requires triage: "
            + str(run)
            + " "
            + str(row.get("failure_reason"))
        )


def validate_matrix(
    data_root: Path, domain: str, specs: list[dict], seeds: list[int], lock: dict | None
) -> None:
    for spec in specs:
        for seed in seeds:
            run = data_root / domain / METHOD / spec["spec_id"] / f"seed_{seed}"
            manifest_path = run / "run_manifest.json"
            if not manifest_path.exists():
                raise RuntimeError(
                    "Refusing to score unstarted Medium run: " + str(run)
                )
            manifest = json.loads(manifest_path.read_text())
            success = (run / "SUCCESS").exists()
            if not success and manifest.get("failure_class") != "quality":
                raise RuntimeError("Medium run is not terminal: " + str(run))
            if success != bool(manifest.get("render_success")):
                raise RuntimeError(
                    "SUCCESS marker disagrees with manifest: " + str(run)
                )
            if (
                manifest.get("method") != METHOD
                or manifest.get("reasoning_effort_requested") != "medium"
            ):
                raise RuntimeError("Medium identity mismatch: " + str(run))
            if lock:
                identity = manifest.get("identity", {})
                for key, relative in (
                    (
                        "protocol_sha256",
                        "methods/gpt/protocol/generation/gpt6_astra_medium.json",
                    ),
                    ("adapter_sha256", "methods/gpt/adapter_medium.py"),
                    (
                        "prompt_template_sha256",
                        "methods/gpt/protocol/generation/gpt6_astra_prompt.txt",
                    ),
                ):
                    if identity.get(key) != lock["files_sha256"][relative]:
                        raise RuntimeError(
                            "Medium run uses stale frozen inputs: " + str(run)
                        )
                if manifest.get("generation_success") and digest(
                    run / "scene/generated.py"
                ) != manifest.get("generated_code_sha256"):
                    raise RuntimeError("Medium generated code changed: " + str(run))
                if (
                    manifest.get("build_success")
                    and manifest.get("renderer_sha256")
                    != lock["files_sha256"]["methods/gpt/tools/blender_render_gpt.py"]
                ):
                    raise RuntimeError(
                        "Medium run uses stale shared renderer: " + str(run)
                    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/table2")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--smoke-spec-id")
    parser.add_argument("--seed", type=int, choices=range(4), default=0)
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=("iqa", "semantics", "consistency", "diversity", "annotations"),
        default=["iqa", "semantics", "consistency", "diversity", "annotations"],
    )
    args = parser.parse_args()
    data_root = confined(args.data_root)
    formal = data_root == ROOT / "data/table2" and args.smoke_spec_id is None
    lock = verify_lock() if formal else None
    spec_file = ROOT / f"protocol/generation/{args.domain}_specs.jsonl"
    specs = [json.loads(line) for line in spec_file.read_text().splitlines() if line]
    if args.smoke_spec_id:
        specs = [spec for spec in specs if spec["spec_id"] == args.smoke_spec_id]
        if not specs:
            raise ValueError("Unknown smoke spec")
    selected_seeds = [args.seed] if args.smoke_spec_id else list(range(4))
    validate_matrix(data_root, args.domain, specs, selected_seeds, lock)
    output = (
        ROOT
        / "results/gpt6_astra_medium"
        / ("smoke" if args.smoke_spec_id else "formal")
        / args.domain
    )
    if args.smoke_spec_id:
        output = output / f"{args.smoke_spec_id}_seed_{args.seed}"
    output.mkdir(parents=True, exist_ok=True)
    annotation_output = ROOT / "annotations/gpt6_astra_medium" / args.domain
    env = dict(os.environ)
    env.update(
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
    selector = (
        ["--spec-id", args.smoke_spec_id, "--seed", str(args.seed)]
        if args.smoke_spec_id
        else []
    )
    commands = {
        "iqa": [
            python,
            str((ROOT / "evaluation/visual/eval_iqa.py")),
            *common,
            *selector,
            "--device",
            "cuda",
            "--output",
            str(output / "iqa_per_scene.jsonl"),
        ],
        "semantics": [
            python,
            str((ROOT / "evaluation/visual/generate_semantics.py")),
            *common,
            *selector,
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
            *selector,
            "--gpu",
            str(args.gpu),
            "--output",
            str(output / "consistency_per_scene.jsonl"),
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
            str(annotation_output),
        ],
    }
    report = {
        "started_at_utc": utc(),
        "method": METHOD,
        "reasoning_effort": "medium",
        "stages": [],
        "metrics_lock_sha256": digest((ROOT / "protocol/generation/metrics.lock.json")),
        "formal": formal,
        "data_root": str(data_root),
    }
    for stage in args.stages:
        if args.smoke_spec_id and stage in {"diversity", "annotations"}:
            continue
        if stage == "annotations" and annotation_output.exists():
            raise RuntimeError(
                "Medium annotation package exists; refusing to overwrite ratings"
            )
        if stage != "annotations":
            required = {
                "iqa": 18432,
                "semantics": 4096,
                "consistency": 8192,
                "diversity": 4096,
            }[stage]
            while True:
                resource = subprocess.run(
                    [
                        "nvidia-smi",
                        f"--id={args.gpu}",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                if int(resource.stdout.strip()) >= required:
                    break
                print(
                    f"MEDIUM_METRIC_WAIT stage={stage} gpu={args.gpu} required_free_mib={required}",
                    flush=True,
                )
                time.sleep(15)
        stage_env = dict(env)
        if stage == "consistency":
            stage_env.pop("CUDA_VISIBLE_DEVICES", None)
            stage_env["PYTHONPATH"] = str(ROOT / "work/metaurban/worldscore_abi")
        command = commands[stage]
        print(f"MEDIUM_METRIC_START {stage} {args.domain} gpu={args.gpu}", flush=True)
        with (output / f"{stage}.log").open("w") as log:
            completed = subprocess.run(
                command,
                cwd=ROOT.parent,
                env=stage_env,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        report["stages"].append(
            {
                "stage": stage,
                "exit_code": completed.returncode,
                "command": command,
                "ended_at_utc": utc(),
            }
        )
        write_json(output / "execution.json", report)
        if completed.returncode:
            print((output / f"{stage}.log").read_text()[-4500:], flush=True)
            raise RuntimeError(f"Medium {stage} failed; see {output}")
        if stage == "consistency":
            rows = [
                json.loads(line)
                for line in (output / "consistency_per_scene.jsonl")
                .read_text()
                .splitlines()
                if line
            ]
            expected = {
                (spec["spec_id"], seed) for spec in specs for seed in selected_seeds
            }
            actual = {
                (row["spec_id"], row["logical_seed"])
                for row in rows
                if row.get("method") == METHOD and row.get("domain") == args.domain
            }
            if len(rows) != len(expected) or actual != expected:
                raise RuntimeError("Incomplete or foreign Medium WorldScore records")
            check_consistency_records(rows, data_root, args.domain)
        print(f"MEDIUM_METRIC_DONE {stage} {args.domain}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

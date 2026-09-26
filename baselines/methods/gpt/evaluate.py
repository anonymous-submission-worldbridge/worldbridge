#!/usr/bin/env python3
"""Run existing frozen metrics only for completed Astra experiment matrices."""

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
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import digest


def check_consistency_records(rows, data_root, domain):
    for row in rows:
        if not math.isfinite(float(row["consistency_3d"])):
            raise RuntimeError("Non-finite WorldScore result")
        if row.get("success"):
            continue
        run = (
            data_root
            / domain
            / "gpt6_astra"
            / row["spec_id"]
            / f'seed_{row["logical_seed"]}'
        )
        manifest = json.loads((run / "run_manifest.json").read_text())
        reason = row.get("failure_reason")
        if (
            reason == "missing_or_invalid_render"
            and manifest.get("failure_class") == "quality"
        ):
            continue
        if (
            reason == "droid_slam_failed"
            and "returned no valid reprojection errors" in row.get("failure_detail", "")
        ):
            continue
        raise RuntimeError(
            "WorldScore failure requires infrastructure/algorithm triage before ITT aggregation: "
            + str(run)
            + " "
            + str(reason)
            + " "
            + row.get("failure_detail", "")
        )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"])
    parser.add_argument("--pilot-validation", action="store_true")
    parser.add_argument("--gpus", nargs="+", type=int, default=[0, 1, 2, 3])
    parser.add_argument("--data-root", type=Path, default=ROOT / "data/table2")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--smoke-spec-id")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--stages",
        nargs="+",
        choices=["iqa", "semantics", "consistency", "diversity", "annotations"],
        default=["iqa", "semantics", "consistency", "diversity", "annotations"],
    )
    args = parser.parse_args()
    if args.pilot_validation:
        sys.path.insert(0, str(ROOT / "tools"))
        from baselines.methods.gpt.tools.validate_gpt_pilot_metrics import (
            validate_completed,
        )

        return validate_completed(args.gpus)
    if args.domain is None:
        parser.error("--domain is required unless --pilot-validation is used")
    data_root = confined(args.data_root)
    formal = data_root == ROOT / "data/table2"
    if formal:
        lock = json.loads(
            (
                (ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json")
            ).read_text()
        )
        for relative, expected in lock["files_sha256"].items():
            if digest(ROOT / relative) != expected:
                raise RuntimeError("Frozen evaluation source changed: " + relative)
    spec_file = ROOT / f"protocol/generation/{args.domain}_specs.jsonl"
    specs = [json.loads(l) for l in spec_file.read_text().splitlines() if l]
    selected = [s for s in specs if args.smoke_spec_id in (None, s["spec_id"])]
    if not selected:
        raise ValueError("No matching specification")
    for spec in selected:
        for seed in [args.seed] if args.smoke_spec_id else range(4):
            run = (
                data_root
                / args.domain
                / "gpt6_astra"
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            if not (run / "run_manifest.json").exists():
                raise RuntimeError(
                    "Refusing to assign ITT values to unstarted run: " + str(run)
                )
            m = json.loads((run / "run_manifest.json").read_text())
            if not (run / "SUCCESS").exists() and m.get("failure_class") != "quality":
                raise RuntimeError(
                    "Run is not terminal; resolve infrastructure/access before scoring: "
                    + str(run)
                )
            if (run / "SUCCESS").exists() and not m.get("render_success"):
                raise RuntimeError(
                    "SUCCESS marker disagrees with manifest: " + str(run)
                )
            if formal:
                identity = m.get("identity", {})
                for key, relative in [
                    (
                        "protocol_sha256",
                        "methods/gpt/protocol/generation/gpt6_astra.json",
                    ),
                    ("adapter_sha256", "methods/gpt/adapter.py"),
                    (
                        "prompt_template_sha256",
                        "methods/gpt/protocol/generation/gpt6_astra_prompt.txt",
                    ),
                ]:
                    if identity.get(key) != lock["files_sha256"][relative]:
                        raise RuntimeError(
                            "Run uses stale generation inputs: " + str(run)
                        )
                if m.get("generation_success") and digest(
                    run / "scene/generated.py"
                ) != m.get("generated_code_sha256"):
                    raise RuntimeError(
                        "Generated code changed after generation: " + str(run)
                    )
                if (
                    m.get("build_success")
                    and m.get("renderer_sha256")
                    != lock["files_sha256"]["methods/gpt/tools/blender_render_gpt.py"]
                ):
                    raise RuntimeError("Run uses stale renderer: " + str(run))
    output = (
        ROOT
        / "results/gpt6_astra"
        / ("smoke" if args.smoke_spec_id else "formal")
        / args.domain
    )
    if args.smoke_spec_id:
        output = output / f"{args.smoke_spec_id}_seed_{args.seed}"
    output.mkdir(parents=True, exist_ok=True)
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
        "gpt6_astra",
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
            str((ROOT / "evaluation/visual/eval_worldscore.py")),
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
            str(ROOT / "tools/make_annotation_package.py"),
            *common,
            "--output",
            str(ROOT / "annotations/gpt6_astra" / args.domain),
        ],
    }
    report = {
        "started_at_utc": utc(),
        "stages": [],
        "metrics_lock_sha256": digest((ROOT / "protocol/generation/metrics.lock.json")),
        "formal": formal and not bool(args.smoke_spec_id),
        "data_root": str(data_root),
    }
    for stage in args.stages:
        if args.smoke_spec_id and stage in {"diversity", "annotations"}:
            continue
        if (
            stage == "annotations"
            and (ROOT / "annotations/gpt6_astra" / args.domain).exists()
        ):
            raise RuntimeError(
                "Annotation package already exists; refusing to overwrite possible real ratings"
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
                    f"METRIC_WAIT stage={stage} gpu={args.gpu} required_free_mib={required}",
                    flush=True,
                )
                time.sleep(15)
        stage_env = dict(env)
        if stage == "consistency":
            stage_env.pop("CUDA_VISIBLE_DEVICES", None)
            stage_env["PYTHONPATH"] = str(ROOT / "work/metaurban/worldscore_abi")
        command = commands[stage]
        print(f"METRIC_START {stage} {args.domain} gpu={args.gpu}", flush=True)
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
            raise RuntimeError(f"{stage} failed; see {output}")
        if stage == "consistency":
            rows = [
                json.loads(line)
                for line in (output / "consistency_per_scene.jsonl")
                .read_text()
                .splitlines()
                if line
            ]
            expected = {
                (s["spec_id"], seed)
                for s in selected
                for seed in ([args.seed] if args.smoke_spec_id else range(4))
            }
            actual = {
                (r["spec_id"], r["logical_seed"])
                for r in rows
                if r.get("method") == "gpt6_astra" and r.get("domain") == args.domain
            }
            if len(rows) != len(expected) or actual != expected:
                raise RuntimeError("Incomplete or foreign WorldScore records")
            check_consistency_records(rows, data_root, args.domain)
        print(f"METRIC_DONE {stage} {args.domain}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

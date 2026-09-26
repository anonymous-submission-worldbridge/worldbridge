#!/usr/bin/env python3
"""Precompute one frozen MajutsuCity layout pair for pipeline overlap."""

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
import hashlib
import importlib.util
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE = BASELINES / "work/majutsucity_l40s/source"
LAUNCHER = BASELINES / "methods/majutsucity/adapter_l40s.py"
CONFIG = (
    BASELINES / "methods/majutsucity/protocol/generation/majutsucity.paths.local.yaml"
)
PROXY_VARIABLES = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_launcher():
    spec = importlib.util.spec_from_file_location("majutsucity_l40s_launcher", LAUNCHER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load MajutsuCity launcher: {LAUNCHER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.adapter


def load_pipeline():
    scripts = SOURCE / "scripts"
    sys.path.insert(0, str(scripts))
    import run_pipeline  # type: ignore[import-not-found]

    return run_pipeline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-id")
    parser.add_argument("--seed", type=int, choices=range(4))
    parser.add_argument(
        "--task",
        action="append",
        default=[],
        metavar="SPEC_ID:SEED",
        help="Run several layout slots sequentially on the same physical GPU.",
    )
    parser.add_argument("--gpu", type=int, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.task:
        if args.spec_id is not None or args.seed is not None or args.dry_run:
            parser.error(
                "--task cannot be combined with --spec-id, --seed, or --dry-run"
            )
        for task in args.task:
            try:
                spec_id, seed_text = task.rsplit(":", 1)
                seed = int(seed_text)
            except (ValueError, TypeError) as error:
                raise ValueError(f"Invalid --task value: {task!r}") from error
            if not spec_id or seed not in range(4):
                raise ValueError(f"Invalid --task value: {task!r}")
            subprocess.run(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--spec-id",
                    spec_id,
                    "--seed",
                    str(seed),
                    "--gpu",
                    str(args.gpu),
                ],
                check=True,
            )
        return 0
    if args.spec_id is None or args.seed is None:
        parser.error("--spec-id and --seed are required unless --task is used")

    adapter = load_launcher()
    pipeline = load_pipeline()
    spec = adapter.load_spec(args.spec_id)
    destination, plan_path = adapter.prepare_run("formal", spec, args.seed)
    case_name = adapter.native_case_name("formal", spec, args.seed)
    case_dir = adapter.native_case_dir("formal", spec, args.seed)
    input_dir = case_dir / "inputs"
    layout_path = input_dir / "layout.png"
    depth_path = input_dir / "depth.png"
    record_path = destination / "layout_precompute.json"

    if layout_path.is_file() and depth_path.is_file() and not args.dry_run:
        adapter.atomic_json(
            record_path,
            {
                "status": "reused",
                "spec_id": args.spec_id,
                "logical_seed": args.seed,
                "method_seed": adapter.method_seed(spec, args.seed),
                "physical_gpu": args.gpu,
                "layout": str(layout_path),
                "layout_sha256": sha256(layout_path),
                "depth": str(depth_path),
                "depth_sha256": sha256(depth_path),
                "finished_at": utc_now(),
            },
        )
        print(f"MAJUTSU_LAYOUT_REUSE {args.spec_id} seed={args.seed}", flush=True)
        return 0

    pipeline_args = argparse.Namespace(
        style=adapter.STYLE,
        case_name=case_name,
        layout_path=None,
        depth_path=None,
        generate_layout=True,
        layout_prompt=None,
        height_prompt=None,
        scene_prompt=None,
        scene_plan=plan_path,
        seed=adapter.method_seed(spec, args.seed),
        overwrite=False,
        dry_run=args.dry_run,
    )
    config = pipeline.load_yaml(CONFIG)
    environment = pipeline.runtime_environment(config)
    for variable in PROXY_VARIABLES:
        environment.pop(variable, None)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(args.gpu),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    (
        pipeline_args.resolved_scene_plan,
        pipeline_args.scene_plan_path_resolved,
        pipeline_args.scene_plan_source,
    ) = pipeline.resolve_scene_plan(pipeline_args, config)
    if pipeline_args.layout_prompt is None:
        pipeline_args.layout_prompt = pipeline_args.resolved_scene_plan.layout

    started_at = utc_now()
    generated_layout, generated_depth = pipeline.generate_layout_pair(
        pipeline_args, config, environment
    )
    if args.dry_run:
        print(
            f"MAJUTSU_LAYOUT_DRY_RUN {args.spec_id} seed={args.seed} gpu={args.gpu}",
            flush=True,
        )
        return 0
    missing = [
        path for path in (generated_layout, generated_depth) if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Layout precompute did not produce: " + ", ".join(map(str, missing))
        )
    adapter.atomic_json(
        record_path,
        {
            "status": "completed",
            "execution_policy": "overlap_original_frozen_layout_stage_v1",
            "spec_id": args.spec_id,
            "logical_seed": args.seed,
            "method_seed": adapter.method_seed(spec, args.seed),
            "physical_gpu": args.gpu,
            "scene_plan": str(plan_path),
            "layout": str(generated_layout),
            "layout_sha256": sha256(generated_layout),
            "depth": str(generated_depth),
            "depth_sha256": sha256(generated_depth),
            "started_at": started_at,
            "finished_at": utc_now(),
        },
    )
    print(
        f"MAJUTSU_LAYOUT_OK {args.spec_id} seed={args.seed} gpu={args.gpu}", flush=True
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

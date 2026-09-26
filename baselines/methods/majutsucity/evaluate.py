#!/usr/bin/env python3
"""Run the frozen Table-2 metric stack for MajutsuCity Urban."""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import argparse
import os
import subprocess
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
REPO = BASELINES.parent
DATA_ROOT = BASELINES / "data/table2"
SPEC_FILE = BASELINES / "protocol/generation/urban_specs.jsonl"
RESULTS = BASELINES / "results/majutsucity/urban"
ANNOTATIONS = BASELINES / "annotations/majutsucity/urban"
IQA_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
WORLDSCORE_PYTHON = BASELINES / "envs/worldscore/bin/python"
UTILITY_PYTHON = BASELINES / "envs/majutsucity/bin/python"
WORLDSCORE_ABI_ROOT = BASELINES / "work/metaurban/worldscore_abi"


def run(command: list[str], environment: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=REPO,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    print(
        completed.stdout,
        end="" if completed.stdout.endswith("\n") else "\n",
        flush=True,
    )
    if completed.returncode:
        raise RuntimeError(
            f"Command failed ({completed.returncode}): {' '.join(command)}"
        )


def gpu_environment(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "TORCH_HOME": str(BASELINES / "cache/torch"),
            "HF_HOME": str(BASELINES / "cache/huggingface"),
            "HF_HUB_OFFLINE": "1",
            "XDG_CACHE_HOME": str(BASELINES / "cache/xdg_metrics"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def worldscore_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONPATH"] = os.pathsep.join(
        part
        for part in (str(WORLDSCORE_ABI_ROOT), environment.get("PYTHONPATH"))
        if part
    )
    environment["TORCH_HOME"] = str(BASELINES / "cache/torch")
    environment["XDG_CACHE_HOME"] = str(BASELINES / "cache/xdg_metrics")
    environment["PYTHONUNBUFFERED"] = "1"
    return environment


def common(data_root: Path) -> list[str]:
    return [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_FILE),
        "--method",
        "majutsucity",
        "--domain",
        "urban",
    ]


def automated(data_root: Path, gpu: int) -> None:
    RESULTS.mkdir(parents=True, exist_ok=True)
    environment = gpu_environment(gpu)
    run(
        [
            str(IQA_PYTHON),
            str((BASELINES / "evaluation/visual/generate_semantics.py")),
            *common(data_root),
            "--device",
            "cuda",
            "--batch-size",
            "8",
            "--metadata-output",
            str(RESULTS / "semantic_model.json"),
        ],
        environment,
    )
    run(
        [
            str(IQA_PYTHON),
            str((BASELINES / "evaluation/visual/eval_iqa.py")),
            *common(data_root),
            "--device",
            "cuda",
            "--output",
            str(RESULTS / "iqa_per_scene.jsonl"),
        ],
        environment,
    )
    run(
        [
            str(WORLDSCORE_PYTHON),
            str((BASELINES / "evaluation/visual/eval_worldscore.py")),
            *common(data_root),
            "--gpu",
            str(gpu),
            "--output",
            str(RESULTS / "consistency_per_scene.jsonl"),
        ],
        worldscore_environment(),
    )
    run(
        [
            str(IQA_PYTHON),
            str((BASELINES / "evaluation/visual/eval_diversity.py")),
            *common(data_root),
            "--device",
            "cuda",
            "--output",
            str(RESULTS / "diversity_per_spec.jsonl"),
        ],
        environment,
    )


def package(data_root: Path) -> None:
    run(
        [
            str(UTILITY_PYTHON),
            str(BASELINES / "tools/make_annotation_package.py"),
            *common(data_root),
            "--output",
            str(ANNOTATIONS),
        ]
    )


def aggregate(data_root: Path) -> None:
    run(
        [
            str(UTILITY_PYTHON),
            str((BASELINES / "evaluation/visual/import_human_ratings.py")),
            "--package",
            str(ANNOTATIONS),
            "--output",
            str(RESULTS / "human_per_scene.jsonl"),
        ]
    )
    run(
        [
            str(UTILITY_PYTHON),
            str((BASELINES / "evaluation/visual/aggregate_generation.py")),
            "--protocol",
            str(
                (BASELINES / "methods/majutsucity/protocol/generation/majutsucity.yaml")
            ),
            "--spec-file",
            str(SPEC_FILE),
            "--data-root",
            str(data_root),
            "--results-root",
            str(RESULTS),
            "--method",
            "majutsucity",
            "--domain",
            "urban",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("automated", "package", "aggregate", "all"), required=True
    )
    parser.add_argument("--gpu", type=int, default=4)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    data_root.relative_to(BASELINES.resolve())
    if args.phase in {"automated", "all"}:
        automated(data_root, args.gpu)
    if args.phase in {"package", "all"}:
        package(data_root)
    if args.phase == "aggregate":
        aggregate(data_root)
    if args.phase == "all":
        print(
            "MAJUTSUCITY_METRICS_PAUSED blind ratings are required before aggregation"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

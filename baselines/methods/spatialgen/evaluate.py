#!/usr/bin/env python3
"""Run Table-2 automated metrics and blind-rating handoff for SpatialGen."""

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


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
RESULT_ROOT = BASELINES_ROOT / "results/spatialgen/indoor"
PACKAGE_ROOT = BASELINES_ROOT / "annotations/spatialgen/indoor"
IQA_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
WORLDSCORE_PYTHON = BASELINES_ROOT / "envs/worldscore/bin/python"
UTILITY_PYTHON = BASELINES_ROOT / "envs/spatialgen/bin/python"
WORLDSCORE_ABI_ROOT = BASELINES_ROOT / "work/metaurban/worldscore_abi"
WORLDSCORE_ABI_FILES = (
    WORLDSCORE_ABI_ROOT / "droid_backends.cpython-39-x86_64-linux-gnu.so",
    WORLDSCORE_ABI_ROOT / "lietorch_backends.cpython-39-x86_64-linux-gnu.so",
)


def run(command: list[str], environment: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
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


def metric_environment(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "TORCH_HOME": str(BASELINES_ROOT / "cache/torch"),
            "HF_HOME": str(BASELINES_ROOT / "cache/huggingface"),
            "HF_HUB_OFFLINE": "1",
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/xdg_metrics"),
            "PYTHONUNBUFFERED": "1",
        }
    )
    return environment


def worldscore_environment() -> dict[str, str]:
    missing = [str(path) for path in WORLDSCORE_ABI_FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing reusable WorldScore ABI artifacts: {missing}")
    environment = dict(os.environ)
    existing_pythonpath = environment.get("PYTHONPATH")
    environment.update(
        {
            "TORCH_HOME": str(BASELINES_ROOT / "cache/torch"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/xdg_metrics"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(
                part for part in (str(WORLDSCORE_ABI_ROOT), existing_pythonpath) if part
            ),
        }
    )
    return environment


def automated(gpu: int, data_root: Path, result_root: Path) -> None:
    result_root.mkdir(parents=True, exist_ok=True)
    common = [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_FILE),
        "--method",
        "spatialgen",
        "--domain",
        "indoor",
    ]
    environment = metric_environment(gpu)
    run(
        [
            str(IQA_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/generate_semantics.py")),
            *common,
            "--device",
            "cuda",
            "--batch-size",
            "8",
            "--metadata-output",
            str(result_root / "semantic_model.json"),
        ],
        environment,
    )
    run(
        [
            str(IQA_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_iqa.py")),
            *common,
            "--device",
            "cuda",
            "--output",
            str(result_root / "iqa_per_scene.jsonl"),
        ],
        environment,
    )
    run(
        [
            str(WORLDSCORE_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_worldscore.py")),
            *common,
            "--gpu",
            str(gpu),
            "--output",
            str(result_root / "consistency_per_scene.jsonl"),
        ],
        worldscore_environment(),
    )
    run(
        [
            str(IQA_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_diversity.py")),
            *common,
            "--device",
            "cuda",
            "--output",
            str(result_root / "diversity_per_spec.jsonl"),
        ],
        environment,
    )


def package(data_root: Path, package_root: Path) -> None:
    run(
        [
            str(UTILITY_PYTHON),
            str(BASELINES_ROOT / "tools/make_annotation_package.py"),
            "--data-root",
            str(data_root),
            "--spec-file",
            str(SPEC_FILE),
            "--method",
            "spatialgen",
            "--domain",
            "indoor",
            "--output",
            str(package_root),
        ]
    )


def aggregate(data_root: Path, result_root: Path, package_root: Path) -> None:
    run(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/import_human_ratings.py")),
            "--package",
            str(package_root),
            "--output",
            str(result_root / "human_per_scene.jsonl"),
        ]
    )
    run(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/aggregate_generation.py")),
            "--protocol",
            str(
                (
                    BASELINES_ROOT
                    / "methods/spatialgen/protocol/generation/spatialgen_protocol.yaml"
                )
            ),
            "--spec-file",
            str(SPEC_FILE),
            "--data-root",
            str(data_root),
            "--results-root",
            str(result_root),
            "--method",
            "spatialgen",
            "--domain",
            "indoor",
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("automated", "package", "aggregate", "all"), required=True
    )
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--result-root", type=Path, default=RESULT_ROOT)
    parser.add_argument("--package-root", type=Path, default=PACKAGE_ROOT)
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    result_root = args.result_root.resolve()
    package_root = args.package_root.resolve()
    for label, path in (
        ("data-root", data_root),
        ("result-root", result_root),
        ("package-root", package_root),
    ):
        try:
            path.relative_to(BASELINES_ROOT.resolve())
        except ValueError as error:
            raise ValueError(f"{label} must remain below baselines/") from error
    if args.phase in {"automated", "all"}:
        automated(args.gpu, data_root, result_root)
    if args.phase in {"package", "all"}:
        package(data_root, package_root)
    if args.phase == "aggregate":
        aggregate(data_root, result_root, package_root)
    if args.phase == "all":
        print(
            "SPATIALGEN_METRICS_PAUSED annotation package is ready; obtain three "
            "independent blind ratings, then run --phase aggregate",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run frozen Table-2 metrics and annotation packaging for SynCity 3000."""

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
IQA_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
WORLDSCORE_PYTHON = BASELINES_ROOT / "envs/worldscore/bin/python"
UTILITY_PYTHON = BASELINES_ROOT / "environments/worldgen/bin/python"
WORLDSCORE_ABI_ROOT = BASELINES_ROOT / "work/metaurban/worldscore_abi"
SEMANTIC_ROOT = BASELINES_ROOT / "work/syncity3k/semantic_pred"
METRIC_ARTIFACT_ROOT = BASELINES_ROOT / "work/syncity3k/metric_artifacts"
WORLDSCORE_ABI_FILES = (
    WORLDSCORE_ABI_ROOT / "droid_backends.cpython-39-x86_64-linux-gnu.so",
    WORLDSCORE_ABI_ROOT / "lietorch_backends.cpython-39-x86_64-linux-gnu.so",
)
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}


def run_command(command: list[str], environment: dict[str, str] | None = None) -> None:
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
    if completed.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
        )


def metric_environment(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "TORCH_HOME": str(BASELINES_ROOT / "cache/torch"),
            "HF_HOME": str(BASELINES_ROOT / "cache/huggingface"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
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


def automated_domain(domain: str, gpu: int, data_root: Path) -> None:
    result_root = BASELINES_ROOT / "results/syncity3k" / domain
    result_root.mkdir(parents=True, exist_ok=True)
    common = [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_FILES[domain]),
        "--method",
        "syncity3k",
        "--domain",
        domain,
    ]
    environment = metric_environment(gpu)
    run_command(
        [
            str(IQA_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/generate_semantics.py")),
            *common,
            "--device",
            "cuda",
            "--batch-size",
            "8",
            "--semantic-root",
            str(SEMANTIC_ROOT),
            "--metadata-output",
            str(result_root / "semantic_model.json"),
        ],
        environment,
    )
    run_command(
        [
            str(IQA_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_iqa.py")),
            *common,
            "--device",
            "cuda",
            "--artifact-root",
            str(METRIC_ARTIFACT_ROOT),
            "--output",
            str(result_root / "iqa_per_scene.jsonl"),
        ],
        environment,
    )
    run_command(
        [
            str(WORLDSCORE_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_worldscore.py")),
            *common,
            "--gpu",
            str(gpu),
            "--artifact-root",
            str(METRIC_ARTIFACT_ROOT),
            "--output",
            str(result_root / "consistency_per_scene.jsonl"),
        ],
        worldscore_environment(),
    )
    run_command(
        [
            str(IQA_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_diversity.py")),
            *common,
            "--device",
            "cuda",
            "--semantic-root",
            str(SEMANTIC_ROOT),
            "--output",
            str(result_root / "diversity_per_spec.jsonl"),
        ],
        environment,
    )


def make_package(domain: str, data_root: Path) -> None:
    output = BASELINES_ROOT / "annotations/syncity3k" / domain
    run_command(
        [
            str(UTILITY_PYTHON),
            str(BASELINES_ROOT / "tools/make_annotation_package.py"),
            "--data-root",
            str(data_root),
            "--spec-file",
            str(SPEC_FILES[domain]),
            "--method",
            "syncity3k",
            "--domain",
            domain,
            "--output",
            str(output),
            "--media-workers",
            "4",
            "--reuse-existing-media",
        ]
    )


def aggregate(domain: str, data_root: Path, rating_source: str) -> None:
    result_root = BASELINES_ROOT / "results/syncity3k" / domain
    package = BASELINES_ROOT / "annotations/syncity3k" / domain
    command = [
        str(UTILITY_PYTHON),
        str((BASELINES_ROOT / "evaluation/visual/import_human_ratings.py")),
        "--package",
        str(package),
        "--output",
        str(result_root / "human_per_scene.jsonl"),
    ]
    if rating_source:
        command.extend(["--rating-source", rating_source])
    run_command(command)
    run_command(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/aggregate_generation.py")),
            "--protocol",
            str(
                (
                    BASELINES_ROOT
                    / "methods/syncity/protocol/generation/syncity3k_protocol.yaml"
                )
            ),
            "--spec-file",
            str(SPEC_FILES[domain]),
            "--data-root",
            str(data_root),
            "--results-root",
            str(result_root),
            "--method",
            "syncity3k",
            "--domain",
            domain,
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("automated", "package", "aggregate", "all"), required=True
    )
    parser.add_argument("--domain", choices=tuple(SPEC_FILES), required=True)
    parser.add_argument("--gpu", type=int, default=1)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--rating-source", default="")
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    try:
        data_root.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("data-root must remain below baselines/") from exc
    if args.phase in {"automated", "all"}:
        automated_domain(args.domain, args.gpu, data_root)
    if args.phase in {"package", "all"}:
        make_package(args.domain, data_root)
    if args.phase == "aggregate":
        aggregate(args.domain, data_root, args.rating_source)
    if args.phase == "all":
        print(
            "SYNCITY3K_METRICS_PAUSED annotation package ready; fill three-rater "
            "ratings before --phase aggregate",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

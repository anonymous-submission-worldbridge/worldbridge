#!/usr/bin/env python3
"""Run automated Table-2 metrics and prepare blind ratings for WorldGen."""

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
import concurrent.futures
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
    result_root = BASELINES_ROOT / "results/worldgen" / domain
    result_root.mkdir(parents=True, exist_ok=True)
    common = [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_FILES[domain]),
        "--method",
        "worldgen",
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
            "--output",
            str(result_root / "iqa_per_scene.jsonl"),
        ],
        environment,
    )
    # eval_worldscore creates one fresh process per scene and maps this physical
    # GPU itself, so do not remap CUDA_VISIBLE_DEVICES in the outer environment.
    run_command(
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
    run_command(
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


def make_annotation_package(domain: str, data_root: Path) -> None:
    output = BASELINES_ROOT / "annotations/worldgen" / domain
    run_command(
        [
            str(UTILITY_PYTHON),
            str(BASELINES_ROOT / "tools/make_annotation_package.py"),
            "--data-root",
            str(data_root),
            "--spec-file",
            str(SPEC_FILES[domain]),
            "--method",
            "worldgen",
            "--domain",
            domain,
            "--output",
            str(output),
        ]
    )


def import_and_aggregate(domain: str, data_root: Path) -> None:
    result_root = BASELINES_ROOT / "results/worldgen" / domain
    package = BASELINES_ROOT / "annotations/worldgen" / domain
    human_output = result_root / "human_per_scene.jsonl"
    run_command(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/import_human_ratings.py")),
            "--package",
            str(package),
            "--output",
            str(human_output),
        ]
    )
    run_command(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/aggregate_generation.py")),
            "--protocol",
            str(
                (
                    BASELINES_ROOT
                    / "methods/worldgen/protocol/generation/worldgen_protocol.yaml"
                )
            ),
            "--spec-file",
            str(SPEC_FILES[domain]),
            "--data-root",
            str(data_root),
            "--results-root",
            str(result_root),
            "--method",
            "worldgen",
            "--domain",
            domain,
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase", choices=("automated", "package", "aggregate", "all"), required=True
    )
    parser.add_argument(
        "--domains", choices=tuple(SPEC_FILES), nargs="+", default=list(SPEC_FILES)
    )
    parser.add_argument("--gpus", type=int, nargs="+", default=[0, 1])
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    args = parser.parse_args()
    if len(args.gpus) < len(args.domains):
        raise ValueError("Provide at least one GPU per concurrently evaluated domain")
    if not set(args.gpus).issubset({0, 1}):
        raise ValueError("WorldGen evaluation is restricted to physical GPUs 0 and 1")
    data_root = args.data_root.resolve()
    try:
        data_root.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError("data-root must remain below baselines/") from exc

    if args.phase in {"automated", "all"}:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(args.domains)
        ) as executor:
            futures = [
                executor.submit(automated_domain, domain, args.gpus[index], data_root)
                for index, domain in enumerate(args.domains)
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
    if args.phase in {"package", "all"}:
        for domain in args.domains:
            make_annotation_package(domain, data_root)
    if args.phase == "aggregate":
        for domain in args.domains:
            import_and_aggregate(domain, data_root)
    if args.phase == "all":
        print(
            "WORLDGEN_METRICS_PAUSED annotation packages are ready; obtain three "
            "independent blind ratings before running --phase aggregate",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Resume HY-World 2.0 Table-2 renders, metrics, and blind-rating artifacts."""

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
import importlib.util
import json
import math
import os
import subprocess
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
DATA_ROOT = BASELINES_ROOT / "hyworld2_runtime/data/table2"
IQA_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
WORLDSCORE_PYTHON = BASELINES_ROOT / "envs/worldscore/bin/python"
UTILITY_PYTHON = BASELINES_ROOT / "environments/worldgen/bin/python"
HY_PYTHON = Path(
    os.environ.get("HYWORLD2_PYTHON", BASELINES_ROOT / "envs/hyworld2/bin/python")
)
RENDERER = BASELINES_ROOT / "methods/hyworld/tools/render_hyworld_generation.py"
WORLDSCORE_ABI_ROOT = BASELINES_ROOT / "work/metaurban/worldscore_abi"
WORLDSCORE_ABI_FILES = (
    WORLDSCORE_ABI_ROOT / "droid_backends.cpython-39-x86_64-linux-gnu.so",
    WORLDSCORE_ABI_ROOT / "lietorch_backends.cpython-39-x86_64-linux-gnu.so",
)
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}


def load_adapter():
    path = BASELINES_ROOT / "methods/hyworld/adapter.py"
    spec = importlib.util.spec_from_file_location("hyworld2_eval_adapter", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_adapter()


def run_command(
    command: list[str],
    environment: dict[str, str] | None = None,
    accepted_codes: set[int] = {0},
) -> int:
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
    if completed.returncode not in accepted_codes:
        raise RuntimeError(
            f"Command failed with exit code {completed.returncode}: {' '.join(command)}"
        )
    return completed.returncode


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


def render_environment(gpu: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.update(HY.runtime_environment())
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    local_cache = Path(
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime/cache")
    )
    local_tmp = Path(
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime/tmp")
    )
    local_cache.mkdir(parents=True, exist_ok=True)
    local_tmp.mkdir(parents=True, exist_ok=True)
    for key, relative in {
        "TORCH_HOME": "torch",
        "TORCH_EXTENSIONS_DIR": "torch_extensions",
        "TORCHINDUCTOR_CACHE_DIR": "torchinductor",
        "TRITON_CACHE_DIR": "triton",
        "CUDA_CACHE_PATH": "cuda",
        "XDG_CACHE_HOME": "xdg",
        "PYTHONPYCACHEPREFIX": "pycache",
        "MPLCONFIGDIR": "matplotlib",
    }.items():
        cache_path = local_cache / relative
        cache_path.mkdir(parents=True, exist_ok=True)
        environment[key] = str(cache_path)
    environment["TMPDIR"] = str(local_tmp)
    local_python_lib = _wb_expand_paths(
        "${WORLDBRIDGE_CACHE}/hyworld2_python_uid2002/lib"
    )
    existing_ld = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = (
        f"{local_python_lib}:{existing_ld}" if existing_ld else local_python_lib
    )
    return environment


def worldscore_environment() -> dict[str, str]:
    missing = [str(path) for path in WORLDSCORE_ABI_FILES if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"Missing reusable WorldScore ABI artifacts: {missing}")
    environment = dict(os.environ)
    existing = environment.get("PYTHONPATH")
    environment.update(
        {
            "TORCH_HOME": str(BASELINES_ROOT / "cache/torch"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/xdg_metrics"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": os.pathsep.join(
                part for part in (str(WORLDSCORE_ABI_ROOT), existing) if part
            ),
        }
    )
    return environment


def run_dirs(domain: str, data_root: Path) -> list[Path]:
    runs = []
    for spec in HY.load_specs(domain):
        for seed in range(4):
            runs.append(
                data_root / domain / "hyworld2" / spec["spec_id"] / f"seed_{seed}"
            )
    return runs


def require_finalized_matrix(domain: str, data_root: Path) -> None:
    """Do not turn unstarted or interrupted jobs into ITT failures."""
    pending = []
    for run in run_dirs(domain, data_root):
        manifest = run / "run_manifest.json"
        terminal = any(
            (run / marker).is_file()
            for marker in (
                "SUCCESS",
                "RENDER_QUALITY_FAILURE",
                "GENERATION_FAILURE",
            )
        )
        if not manifest.is_file() or not terminal:
            pending.append(str(run.relative_to(data_root)))
    if pending:
        raise RuntimeError(
            f"{domain}: {len(pending)}/100 runs are not finalized; "
            f"refusing premature ITT metrics/ratings. First pending: {pending[:3]}"
        )


def render_queue(queue: list[Path], gpu: int) -> dict[str, int]:
    counts = {
        "success": 0,
        "quality_failure": 0,
        "infrastructure_failure": 0,
        "skipped": 0,
    }
    environment = render_environment(gpu)
    for run_dir in queue:
        if (run_dir / "SUCCESS").is_file():
            counts["skipped"] += 1
            continue
        if not any((run_dir / "scene/gs/ply").glob("point_cloud_*.ply")):
            counts["skipped"] += 1
            continue
        try:
            code = run_command(
                [str(HY_PYTHON), str(RENDERER), "--run-dir", str(run_dir)],
                environment,
                accepted_codes={0, 2},
            )
            counts["success" if code == 0 else "quality_failure"] += 1
        except Exception as exc:
            counts["infrastructure_failure"] += 1
            print(
                f"HYWORLD2_RENDER_INFRASTRUCTURE_FAILURE run={run_dir} error={exc!r}",
                flush=True,
            )
    return counts


def render_domains(domains: list[str], gpus: list[int], data_root: Path) -> None:
    pending = [run for domain in domains for run in run_dirs(domain, data_root)]
    queues = [pending[index :: len(gpus)] for index in range(len(gpus))]
    aggregate = {
        "success": 0,
        "quality_failure": 0,
        "infrastructure_failure": 0,
        "skipped": 0,
    }
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as executor:
        futures = [
            executor.submit(render_queue, queue, gpu)
            for queue, gpu in zip(queues, gpus)
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            for key, value in result.items():
                aggregate[key] += value
    print(f"HYWORLD2_RENDER_MATRIX_COMPLETE {aggregate}", flush=True)


def automated_domain(domain: str, gpu: int, data_root: Path) -> None:
    result_root = BASELINES_ROOT / "results/hyworld2" / domain
    result_root.mkdir(parents=True, exist_ok=True)
    common = [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_FILES[domain]),
        "--method",
        "hyworld2",
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


def sanity_scene(
    domain: str, spec_id: str, seed: int, gpu: int, data_root: Path
) -> None:
    """Exercise real Pilot renders without creating a partial formal ITT table."""
    if spec_id not in {
        spec["spec_id"] for spec in HY.load_specs(domain)
    } or seed not in range(4):
        raise ValueError("Sanity check requires a frozen spec and logical seed")
    run = data_root / domain / "hyworld2" / spec_id / f"seed_{seed}"
    if not (run / "SUCCESS").is_file():
        raise RuntimeError(f"Sanity check requires a validator-valid scene: {run}")
    if (
        len(list((run / "renders/anchors").glob("rgb_*.png"))) != 8
        or len(list((run / "renders/sequence").glob("rgb_*.png"))) != 50
    ):
        raise RuntimeError("Sanity check requires all 8 anchors and 50 sequence frames")
    output = (
        BASELINES_ROOT
        / "results/hyworld2/pilot_sanity"
        / domain
        / spec_id
        / f"seed_{seed}"
    )
    output.mkdir(parents=True, exist_ok=True)
    common = [
        "--data-root",
        str(data_root),
        "--spec-file",
        str(SPEC_FILES[domain]),
        "--method",
        "hyworld2",
        "--domain",
        domain,
        "--spec-id",
        spec_id,
        "--seed",
        str(seed),
    ]
    environment = metric_environment(gpu)
    iqa = []
    for repeat in (1, 2):
        destination = output / f"iqa_repeat_{repeat}.jsonl"
        run_command(
            [
                str(IQA_PYTHON),
                str((BASELINES_ROOT / "evaluation/visual/eval_iqa.py")),
                *common,
                "--device",
                "cuda",
                "--output",
                str(destination),
            ],
            environment,
        )
        rows = [
            json.loads(line) for line in destination.read_text().splitlines() if line
        ]
        if (
            len(rows) != 1
            or not rows[0].get("success")
            or len(rows[0].get("views", [])) != 8
        ):
            raise RuntimeError(
                "IQA sanity check did not evaluate all eight actual anchors"
            )
        iqa.append(rows[0])
    differences = {
        key: max(abs(a[key] - b[key]) for a, b in zip(iqa[0]["views"], iqa[1]["views"]))
        for key in ("qalign", "clipiqa_plus")
    }
    if any(
        not math.isfinite(v[key])
        for row in iqa
        for v in row["views"]
        for key in differences
    ) or any(value > 1e-4 for value in differences.values()):
        raise RuntimeError(f"IQA repeatability needs investigation: {differences}")
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
            str(output / "semantic_model.json"),
        ],
        environment,
    )
    destination = output / "worldscore.jsonl"
    run_command(
        [
            str(WORLDSCORE_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/eval_worldscore.py")),
            *common,
            "--gpu",
            str(gpu),
            "--output",
            str(destination),
        ],
        worldscore_environment(),
    )
    rows = [json.loads(line) for line in destination.read_text().splitlines() if line]
    if (
        len(rows) != 1
        or not rows[0].get("success")
        or not math.isfinite(rows[0]["consistency_3d"])
    ):
        raise RuntimeError(
            "WorldScore did not complete real 3D consistency inference; inspect its log"
        )
    report = {
        "table2_eligible": False,
        "scope": "single_scene_metric_sanity_only",
        "domain": domain,
        "spec_id": spec_id,
        "logical_seed": seed,
        "iqa_max_per_view_repeat_difference": differences,
        "iqa_repeat_tolerance": 1e-4,
        "iqa": iqa,
        "worldscore": rows[0],
        "remaining_pilot_checks": [
            "full_5x2_output_contract",
            "same_seed_generation_reproduction",
            "changed_seed_content",
            "visual_trajectory_and_semantics_review",
            "diversity_gpu_inference",
            "anonymous_ai_rating_package",
        ],
    }
    (output / "sanity.json").write_text(json.dumps(report, indent=2) + "\n")
    print(
        f"HYWORLD2_METRIC_SANITY_OK table2_eligible=false report={output / 'sanity.json'}",
        flush=True,
    )


def make_annotation_package(domain: str, data_root: Path) -> None:
    output = BASELINES_ROOT / "annotations/hyworld2" / domain
    run_command(
        [
            str(UTILITY_PYTHON),
            str(BASELINES_ROOT / "tools/make_annotation_package.py"),
            "--data-root",
            str(data_root),
            "--spec-file",
            str(SPEC_FILES[domain]),
            "--method",
            "hyworld2",
            "--domain",
            domain,
            "--output",
            str(output),
            "--reuse-existing-media",
        ]
    )


def import_and_aggregate(domain: str, data_root: Path) -> None:
    result_root = BASELINES_ROOT / "results/hyworld2" / domain
    package = BASELINES_ROOT / "annotations/hyworld2" / domain
    run_command(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/import_human_ratings.py")),
            "--package",
            str(package),
            "--output",
            str(result_root / "human_per_scene.jsonl"),
            "--rating-source",
            "ai_proxy_qwen3_vl_8b_three_pass",
        ]
    )
    run_command(
        [
            str(UTILITY_PYTHON),
            str((BASELINES_ROOT / "evaluation/visual/aggregate_generation.py")),
            "--protocol",
            str((BASELINES_ROOT / "methods/hyworld/protocol/generation/hyworld2.yaml")),
            "--spec-file",
            str(SPEC_FILES[domain]),
            "--data-root",
            str(data_root),
            "--results-root",
            str(result_root),
            "--method",
            "hyworld2",
            "--domain",
            domain,
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--phase",
        choices=("sanity", "render", "automated", "package", "ai-proxy", "aggregate"),
        required=True,
    )
    parser.add_argument(
        "--domains", choices=tuple(SPEC_FILES), nargs="+", default=list(SPEC_FILES)
    )
    parser.add_argument("--gpus", type=int, nargs="+", default=[0])
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument(
        "--spec-id", help="One existing validator-valid scene, for --phase sanity only"
    )
    parser.add_argument(
        "--seed", type=int, help="Logical seed, for --phase sanity only"
    )
    args = parser.parse_args()
    if not args.gpus or len(set(args.gpus)) != len(args.gpus):
        raise ValueError("Provide one or more unique physical GPU ids")
    if not set(args.gpus).issubset(set(range(8))):
        raise ValueError("GPU ids must be in 0..7")
    data_root = require_below_baselines(args.data_root)
    if args.phase == "sanity":
        if len(args.domains) != 1 or args.spec_id is None or args.seed is None:
            raise ValueError("Sanity check requires one domain, --spec-id and --seed")
        sanity_scene(args.domains[0], args.spec_id, args.seed, args.gpus[0], data_root)
        return 0
    if args.spec_id is not None or args.seed is not None:
        raise ValueError("Scene filters are only supported for --phase sanity")
    if args.phase != "render":
        for domain in args.domains:
            require_finalized_matrix(domain, data_root)
    if args.phase == "render":
        render_domains(args.domains, args.gpus, data_root)
    elif args.phase == "automated":
        if len(args.gpus) < len(args.domains):
            raise ValueError("Automated metrics require one GPU per concurrent domain")
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(args.domains)
        ) as executor:
            futures = [
                executor.submit(automated_domain, domain, args.gpus[index], data_root)
                for index, domain in enumerate(args.domains)
            ]
            for future in concurrent.futures.as_completed(futures):
                future.result()
    elif args.phase == "package":
        for domain in args.domains:
            make_annotation_package(domain, data_root)
    elif args.phase == "ai-proxy":
        for domain in args.domains:
            run_command(
                [
                    str(HY_PYTHON),
                    str(
                        (
                            BASELINES_ROOT
                            / "methods/hyworld/tools/score_hyworld_ai_proxy.py"
                        )
                    ),
                    "--package",
                    str(BASELINES_ROOT / "annotations/hyworld2" / domain),
                    "--gpu",
                    str(args.gpus[0]),
                ]
            )
    else:
        for domain in args.domains:
            import_and_aggregate(domain, data_root)
    return 0


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Path must remain below {BASELINES_ROOT}: {resolved}"
        ) from exc
    return resolved


if __name__ == "__main__":
    raise SystemExit(main())

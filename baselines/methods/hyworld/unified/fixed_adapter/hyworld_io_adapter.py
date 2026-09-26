#!/usr/bin/env python3
"""Evaluate frozen HY-World 2.0 pairs plus the fixed Table-4 IO adapter.

The native HY-World artifacts are immutable inputs. Geometry/navigation logic
is imported from the already frozen WorldGen fixed-IO-adapter evaluator so both
system rows use the same synthetic shell, portal, Recast and metric semantics.
"""

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
import csv
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.worldgen.unified.fixed_adapter import (
    worldgen_io_adapter as common,
)


BASELINES = REPO / "baselines"
PACKAGE_ROOT = BASELINES / "methods/hyworld/unified/fixed_adapter"
PROTOCOL_DIR = BASELINES / "methods/hyworld/protocol/unified/fixed_adapter"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
PROMPT_PATH = PROTOCOL_DIR / "spatial_aqs_prompt.txt"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
SPEC_PATH = BASELINES / "protocol/unified/specs.jsonl"
SOURCE_PROTOCOL = BASELINES / "methods/hyworld/protocol/unified/native/hyworld2.yaml"
SOURCE_LOCK = (
    BASELINES
    / "methods/hyworld/protocol/unified/native/hyworld2_native_method.lock.json"
)
SOURCE_SUMMARY = BASELINES / "results/table4/hyworld2/formal/summary.json"
SOURCE_PER_RUN = BASELINES / "results/table4/hyworld2/formal/per_run.jsonl"
SOURCE_AUDIT = BASELINES / "results/table4/hyworld2/formal/matrix_audit.json"
SOURCE_PRIVATE_MAP = (
    BASELINES / "annotations/table4/hyworld2/formal/PRIVATE_blind_map.json"
)
SOURCE_EVIDENCE_PROVENANCE = (
    BASELINES / "annotations/table4/hyworld2/formal/EVIDENCE_PROVENANCE.json"
)
MODEL_MANIFEST = BASELINES / "hyworld2_runtime/manifests/qwen3_vl_8b_modelscope.json"
QWEN_ROOT = Path(_wb_expand_paths("${WORLDBRIDGE_MODELS}/Qwen/Qwen3-VL-8B-Instruct"))
VLLM_PYTHON = BASELINES / "envs/hyworld2-vllm-runtime/bin/python"
VLLM_PACKAGE = (
    VLLM_PYTHON.parent.parent / "lib/python3.11/site-packages/vllm/__init__.py"
)
COMMON_RUNNER = (
    BASELINES / "methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py"
)
BLIND_SALT = "worldbridge-table4-hyworld2-fixed-io-adapter-v1"
ORIGINAL_BUILD_ONE = common.build_one
METRICS = common.METRICS


def load_protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def relative_path(path: Path) -> str:
    """Keep links lexically below the repository while hashing their targets."""
    return str(path.absolute().relative_to(REPO.absolute()))


def configure_common() -> None:
    """Route the frozen shared evaluator to this method-specific protocol."""
    common.PROTOCOL_DIR = PROTOCOL_DIR
    common.PROTOCOL_PATH = PROTOCOL_PATH
    common.PROMPT_PATH = PROMPT_PATH
    common.LOCK_PATH = LOCK_PATH
    common.SOURCE_LOCK = SOURCE_LOCK
    common.SOURCE_SUMMARY = SOURCE_SUMMARY
    common.SOURCE_AUDIT = SOURCE_AUDIT
    common.MODEL_MANIFEST = MODEL_MANIFEST
    common.QWEN_ROOT = QWEN_ROOT
    common.BLIND_SALT = BLIND_SALT
    common.__file__ = str(Path(__file__).resolve())
    common.rel = relative_path
    common.specs_and_seeds = specs_and_seeds
    common.trial_paths = trial_paths
    common.mesh_floor_scale = fixed_native_reference_scale


def all_specs() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in SPEC_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def specs_and_seeds(trial: str) -> tuple[list[dict[str, Any]], list[int]]:
    protocol = load_protocol()
    if trial not in {"pilot", "formal"}:
        raise ValueError(f"Unsupported trial: {trial}")
    cfg = protocol[trial]
    specs = all_specs()
    if cfg["spec_indices"] != "all":
        selected = {int(value) for value in cfg["spec_indices"]}
        specs = [row for row in specs if int(row["spec_index"]) in selected]
    seeds = [int(value) for value in cfg["seeds"]]
    expected = int(cfg["planned_pairs"])
    if len(specs) * len(seeds) != expected:
        raise RuntimeError(
            f"Protocol matrix mismatch for {trial}: {len(specs)}x{len(seeds)} != {expected}"
        )
    return specs, seeds


def _under_baselines(relative: str) -> Path:
    value = BASELINES / relative.removeprefix("baselines/")
    common.require_below_baselines(value)
    return value


def actual_source_data(trial: str) -> Path:
    protocol = load_protocol()
    return _under_baselines(protocol[f"source_{trial}_data"])


def trial_paths(trial: str) -> tuple[Path, Path, Path, Path, Path, Path]:
    protocol = load_protocol()
    paths = protocol["paths"]
    if trial == "formal":
        return (
            _under_baselines(paths["formal_source_view"]),
            _under_baselines(protocol["source_formal_annotations"]),
            _under_baselines(protocol["source_formal_results"]),
            _under_baselines(paths["formal_data"]),
            _under_baselines(paths["formal_annotations"]),
            _under_baselines(paths["formal_results"]),
        )
    if trial == "pilot":
        return (
            _under_baselines(paths["pilot_source_view"]),
            _under_baselines(protocol["source_pilot_annotations"]),
            _under_baselines(protocol["source_pilot_results"]),
            _under_baselines(paths["pilot_data"]),
            _under_baselines(paths["pilot_annotations"]),
            _under_baselines(paths["pilot_results"]),
        )
    raise ValueError(f"Unsupported trial: {trial}")


def source_pair_success(pair: Path) -> bool:
    return all((pair / side / "SUCCESS").is_file() for side in ("exterior", "interior"))


def source_side_state(pair: Path, side: str) -> str:
    if (pair / side / "SUCCESS").is_file():
        return "success"
    if (pair / side / "RENDER_QUALITY_FAILURE").is_file():
        return "render_quality_failure"
    return "incomplete"


def ensure_symlink(link: Path, target: Path) -> None:
    target = target.resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    if link.is_symlink() and link.resolve() == target:
        return
    if link.exists() or link.is_symlink():
        link.unlink()
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(target)


def stage_source_pair(
    actual_pair: Path, view_pair: Path, spec: dict[str, Any], seed: int, trial: str
) -> bool:
    """Create a small immutable compatibility view without copying HY geometry."""
    original_manifest = actual_pair / "manifest.json"
    if not original_manifest.is_file():
        raise FileNotFoundError(original_manifest)
    success = source_pair_success(actual_pair)
    source_view = {
        "schema_version": "table4-hyworld2-fixed-io-source-view-v1",
        "method": "hyworld2",
        "trial": trial,
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "pair_success": success,
        "pair_success_rule": load_protocol()["adapter"]["source_pair_success_rule"],
        "side_states": {
            side: source_side_state(actual_pair, side)
            for side in ("exterior", "interior")
        },
        "original_pair_manifest": common.rel(original_manifest),
        "original_pair_manifest_sha256": common.sha256_file(original_manifest),
        "source_summary": common.rel(
            SOURCE_SUMMARY
            if trial == "formal"
            else trial_paths(trial)[2] / "summary.json"
        ),
    }
    common.atomic_json(view_pair / "manifest.json", source_view)
    marker = view_pair / "SUCCESS"
    if success:
        common.atomic_text(
            marker, "both frozen HY-World side success markers validated\n"
        )
        for side in ("exterior", "interior"):
            source_cloud = actual_pair / side / "scene/gs/ply/point_cloud_49.ply"
            ensure_symlink(view_pair / "native" / side / "scene/mesh.ply", source_cloud)
    else:
        marker.unlink(missing_ok=True)
    return success


def fixed_native_reference_scale(
    mesh_path: Path, nominal_camera_height: float
) -> dict[str, Any]:
    """Metadata-only fixed transform; the source cloud never enters metrics."""
    return {
        "calibration_rule": "fixed identity metadata transform; no per-sample fitting",
        "meters_per_native_unit": 1.0,
        "nominal_camera_height_m": nominal_camera_height,
        "floor_sample_count": 0,
        "native_geometry_used_for_metrics": False,
        "source_point_cloud_sha256": common.sha256_file(mesh_path),
    }


def build_trial(trial: str) -> dict[str, Any]:
    configure_common()
    if trial == "formal":
        common.verify_lock()
    source_view_root, _, _, output_root, _, _ = trial_paths(trial)
    actual_root = actual_source_data(trial)
    specs, seeds = specs_and_seeds(trial)
    protocol = load_protocol()
    successes = 0
    for spec in specs:
        for seed in seeds:
            actual_pair = common.run_dir(actual_root, spec["spec_id"], seed)
            view_pair = common.run_dir(source_view_root, spec["spec_id"], seed)
            stage_source_pair(actual_pair, view_pair, spec, seed, trial)
            output_pair = common.run_dir(output_root, spec["spec_id"], seed)
            success = ORIGINAL_BUILD_ONE(
                view_pair, output_pair, spec, seed, trial, protocol
            )
            manifest_path = output_pair / "manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest.update(
                {
                    "source_method": "hyworld2",
                    "source_native_pair": common.rel(actual_pair),
                    "source_pair_success_rule": protocol["adapter"][
                        "source_pair_success_rule"
                    ],
                    "adapter_attribution": "synthetic fixed IO adapter; not native HY-World geometry or navigation",
                }
            )
            if not success:
                manifest["failure_reason"] = "source_hyworld2_pair_failure"
            common.atomic_json(manifest_path, manifest)
            if success:
                common.atomic_text(
                    output_pair / "SUCCESS",
                    "HY-World 2.0 plus fixed IO adapter output contract complete\n",
                )
            successes += int(success)
            print(
                f"TABLE4_HYWORLD2_IO_BUILD spec={spec['spec_id']} seed={seed} success={success}",
                flush=True,
            )
    result = {
        "trial": trial,
        "planned_pairs": len(specs) * len(seeds),
        "successful_pairs": successes,
        "output_root": common.rel(output_root),
        "source_method": "hyworld2",
    }
    print(
        f"TABLE4_HYWORLD2_IO_BUILD_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def package_is_valid(trial: str) -> bool:
    _, source_annotations, _, output_data, annotations, _ = trial_paths(trial)
    manifest_path = annotations / "package_manifest.json"
    items_path = annotations / "items.jsonl"
    private_path = annotations / "PRIVATE_blind_map.json"
    if not all(path.is_file() for path in (manifest_path, items_path, private_path)):
        return False
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    specs, seeds = specs_and_seeds(trial)
    success_count = sum(
        (common.run_dir(output_data, spec["spec_id"], seed) / "SUCCESS").is_file()
        for spec in specs
        for seed in seeds
    )
    expected = {
        "method": "hyworld2_fixed_io_adapter",
        "planned_pairs": len(specs) * len(seeds),
        "successful_pairs": success_count,
        "protocol_sha256": common.sha256_file(PROTOCOL_PATH),
        "adapter_sha256": common.sha256_file(Path(__file__)),
        "source_private_map_sha256": common.sha256_file(
            source_annotations / "PRIVATE_blind_map.json"
        ),
    }
    if any(manifest.get(key) != value for key, value in expected.items()):
        return False
    items = [
        json.loads(line)
        for line in items_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(items) != success_count:
        return False
    return all(
        (annotations / row["montage"]).is_file()
        and common.sha256_file(annotations / row["montage"]) == row["montage_sha256"]
        for row in items
    )


def make_spatial_package(trial: str) -> dict[str, Any]:
    configure_common()
    if package_is_valid(trial):
        manifest = json.loads(
            (trial_paths(trial)[4] / "package_manifest.json").read_text(
                encoding="utf-8"
            )
        )
        print(
            f"TABLE4_HYWORLD2_IO_PACKAGE_REUSED {json.dumps(manifest, sort_keys=True)}",
            flush=True,
        )
        return manifest
    result = common.make_spatial_package(trial)
    _, source_annotations, _, _, annotations, _ = trial_paths(trial)
    private_path = annotations / "PRIVATE_blind_map.json"
    private = json.loads(private_path.read_text(encoding="utf-8"))
    for row in private["items"]:
        row["method"] = "hyworld2_fixed_io_adapter"
        row["source_method"] = "hyworld2"
    common.atomic_json(private_path, private)
    result.update(
        {
            "method": "hyworld2_fixed_io_adapter",
            "display_name": load_protocol()["display_name"],
            "protocol_sha256": common.sha256_file(PROTOCOL_PATH),
            "adapter_sha256": common.sha256_file(Path(__file__)),
            "source_private_map_sha256": common.sha256_file(
                source_annotations / "PRIVATE_blind_map.json"
            ),
            "private_map_sha256": common.sha256_file(private_path),
        }
    )
    common.atomic_json(annotations / "package_manifest.json", result)
    print(
        f"TABLE4_HYWORLD2_IO_PACKAGE_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def score_spatial(trial: str, port: int, workers: int) -> dict[str, Any]:
    configure_common()
    result = common.score_spatial_package(trial, port, workers)
    annotations = trial_paths(trial)[4]
    result.update(
        {
            "method": "hyworld2_fixed_io_adapter",
            "display_name": load_protocol()["display_name"],
            "source_method": "hyworld2",
            "functional_visual_scores_reused_from": common.rel(
                SOURCE_SUMMARY
                if trial == "formal"
                else trial_paths(trial)[2] / "summary.json"
            ),
            "prompt_sha256": common.sha256_file(PROMPT_PATH),
            "protocol_sha256": common.sha256_file(PROTOCOL_PATH),
            "adapter_sha256": common.sha256_file(Path(__file__)),
            "temperature": load_protocol()["spatial_aqs"]["temperature"],
            "top_p": load_protocol()["spatial_aqs"]["top_p"],
            "limitations": "Spatial AQS judges the disclosed synthetic-adapter system; it is not native HY-World spatial ability and is not an independent human rating.",
        }
    )
    common.atomic_json(annotations / "SPATIAL_AQS_VLM_PROVENANCE.json", result)
    return result


def gpu_free_mib(gpu: int) -> int:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free",
            "--format=csv,noheader,nounits",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    values = {}
    for line in completed.stdout.splitlines():
        index, free = (part.strip() for part in line.split(",", 1))
        values[int(index)] = int(free)
    if gpu not in values:
        raise RuntimeError(f"GPU {gpu} is not visible: {values}")
    return values[gpu]


def validate_vllm(port: int) -> None:
    if not common.request_json(
        port,
        {
            "model": "Qwen/Qwen3-VL-8B-Instruct",
            "messages": [{"role": "user", "content": 'Return JSON: {\\"ok\\": true}'}],
            "temperature": 0,
            "max_tokens": 16,
        },
    ):
        raise RuntimeError("Local VLM validation returned an empty payload")


def start_vllm(gpu: int, port: int, external: bool) -> tuple[Any | None, Path | None]:
    from baselines.methods.hyworld import run as matrix

    matrix.QWEN_ROOT = QWEN_ROOT
    matrix.VLLM_PYTHON = VLLM_PYTHON
    matrix.VLLM_PACKAGE = VLLM_PACKAGE
    if external:
        if not matrix.llm_health(port):
            raise RuntimeError(f"No healthy local VLM at port {port}")
        validate_vllm(port)
        return None, None
    free_mib = gpu_free_mib(gpu)
    if free_mib < 45000:
        raise RuntimeError(
            f"GPU {gpu} has insufficient remaining memory for Qwen3-VL-8B: {free_mib} MiB"
        )
    process, log = matrix.start_vllm(gpu, port, 16384, 900)
    validate_vllm(port)
    return process, log


def stop_vllm(process: Any | None) -> None:
    if process is None:
        return
    from baselines.methods.hyworld import run as matrix

    matrix.stop_process_group(process)


def aggregate(trial: str) -> dict[str, Any]:
    configure_common()
    common.aggregate(trial)
    results = trial_paths(trial)[5]
    per_run_path = results / "per_run.jsonl"
    rows = [
        json.loads(line)
        for line in per_run_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    failures = []
    for row in rows:
        if row["system_success"]:
            row["functional_visual_rating_source"] = "reused_frozen_hyworld2_aqs"
        else:
            row["failure_reason"] = "source_hyworld2_pair_failure"
            failures.append(
                {
                    "spec_id": row["spec_id"],
                    "logical_seed": row["logical_seed"],
                    "reason": row["failure_reason"],
                }
            )
    common.atomic_text(
        per_run_path,
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
    )
    with (results / "failures.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["spec_id", "logical_seed", "reason"]
        )
        writer.writeheader()
        writer.writerows(failures)
    summary_path = results / "summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary.update(
        {
            "aqs_source": "Functional/Visual reused from frozen HY-World Qwen3-VL evaluation; Spatial newly evaluated with the same fixed-adapter Qwen3-VL rubric in three seeded passes; human_raters=0",
            "adapter_attribution": "Shape/portal/navigation results belong to the deterministic synthetic adapter system, not native HY-World.",
            "source_summary_sha256": common.sha256_file(
                SOURCE_SUMMARY
                if trial == "formal"
                else trial_paths(trial)[2] / "summary.json"
            ),
            "source_per_run_sha256": common.sha256_file(
                SOURCE_PER_RUN
                if trial == "formal"
                else trial_paths(trial)[2] / "per_run.jsonl"
            ),
        }
    )
    common.atomic_json(summary_path, summary)
    print(
        f"TABLE4_HYWORLD2_IO_AGGREGATE_COMPLETE {json.dumps(summary, sort_keys=True)}",
        flush=True,
    )
    return summary


def audit(trial: str) -> dict[str, Any]:
    configure_common()
    result = common.audit(trial)
    result.update(
        {
            "method": "hyworld2_fixed_io_adapter",
            "display_name": load_protocol()["display_name"],
            "source_method": "hyworld2",
            "source_pair_success_rule": load_protocol()["adapter"][
                "source_pair_success_rule"
            ],
            "native_geometry_modified": False,
        }
    )
    common.atomic_json(trial_paths(trial)[5] / "audit.json", result)
    return result


def freeze() -> dict[str, Any]:
    configure_common()
    lock = common.freeze()
    extra_files = [
        COMMON_RUNNER,
        SOURCE_PROTOCOL,
        SPEC_PATH,
        SOURCE_PER_RUN,
        SOURCE_PRIVATE_MAP,
        SOURCE_EVIDENCE_PROVENANCE,
    ]
    for path in extra_files:
        lock["files"][common.rel(path)] = common.sha256_file(path)
    lock["source_method"] = "hyworld2"
    lock["source_outputs_regenerated"] = False
    common.atomic_json(LOCK_PATH, lock)
    common.verify_lock()
    print(
        f"TABLE4_HYWORLD2_IO_FREEZE_COMPLETE {json.dumps(lock, sort_keys=True)}",
        flush=True,
    )
    return lock


def run_all(gpu: int, port: int, workers: int, external_vllm: bool) -> dict[str, Any]:
    configure_common()
    process = None
    log = None
    try:
        if not LOCK_PATH.is_file():
            build_trial("pilot")
            make_spatial_package("pilot")
            process, log = start_vllm(gpu, port, external_vllm)
            score_spatial("pilot", port, workers)
            aggregate("pilot")
            pilot_audit = audit("pilot")
            if not pilot_audit["passed"]:
                raise RuntimeError(f"Pilot audit failed: {pilot_audit['issues']}")
            freeze()
        else:
            common.verify_lock()
        build_trial("formal")
        make_spatial_package("formal")
        if process is None:
            process, log = start_vllm(gpu, port, external_vllm)
        score_spatial("formal", port, workers)
        summary = aggregate("formal")
        formal_audit = audit("formal")
        if not formal_audit["passed"]:
            raise RuntimeError(f"Formal audit failed: {formal_audit['issues']}")
        result = {
            "summary": summary,
            "audit": formal_audit,
            "vllm_log": str(log) if log else "external",
        }
        print(
            f"TABLE4_HYWORLD2_IO_RUN_ALL_COMPLETE {json.dumps(result, sort_keys=True)}",
            flush=True,
        )
        return result
    finally:
        stop_vllm(process)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "package", "aggregate", "audit"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score = subparsers.add_parser("score-spatial")
    score.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score.add_argument("--gpu", type=int, default=5)
    score.add_argument("--port", type=int, default=18084)
    score.add_argument("--request-workers", type=int, default=4)
    score.add_argument("--external-vllm", action="store_true")
    run = subparsers.add_parser("run-all")
    run.add_argument("--gpu", type=int, default=5)
    run.add_argument("--port", type=int, default=18084)
    run.add_argument("--request-workers", type=int, default=4)
    run.add_argument("--external-vllm", action="store_true")
    subparsers.add_parser("freeze")
    subparsers.add_parser("verify-lock")
    args = parser.parse_args()
    configure_common()
    if args.command == "build":
        build_trial(args.trial)
    elif args.command == "package":
        make_spatial_package(args.trial)
    elif args.command == "score-spatial":
        process = None
        try:
            process, _ = start_vllm(args.gpu, args.port, args.external_vllm)
            score_spatial(args.trial, args.port, args.request_workers)
        finally:
            stop_vllm(process)
    elif args.command == "aggregate":
        aggregate(args.trial)
    elif args.command == "audit":
        result = audit(args.trial)
        raise SystemExit(0 if result["passed"] else 1)
    elif args.command == "freeze":
        freeze()
    elif args.command == "verify-lock":
        common.verify_lock()
        print("TABLE4_HYWORLD2_IO_ADAPTER_LOCK_OK")
    elif args.command == "run-all":
        run_all(args.gpu, args.port, args.request_workers, args.external_vllm)


if __name__ == "__main__":
    main()

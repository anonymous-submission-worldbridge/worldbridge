#!/usr/bin/env python3
"""Run, aggregate and audit SynCity 3000's Table-3 surface-only matrix."""

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
import json
import math
import multiprocessing as mp
import os
import random
import shutil
import subprocess
import sys
import time
import traceback
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from PIL import Image, ImageDraw


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
PACKAGE_ROOT = BASELINES / "methods/syncity/geometry"
PROTOCOL_PATH = PACKAGE_ROOT / "protocol.yaml"
METHOD_LOCK_PATH = PACKAGE_ROOT / "method.lock.json"
METRICS_LOCK_PATH = PACKAGE_ROOT / "metrics.lock.json"
EXTRACTOR = PACKAGE_ROOT / "extract_surface.py"
PYTHON310 = BASELINES / "envs/syncity-3k/bin/python"
PYTHON310_SITE = BASELINES / "envs/syncity-3k/lib/python3.10/site-packages"
TABLE2_ROOT = BASELINES / "data/table2"
DATA_ROOT = BASELINES / "data/table3_syncity3k"
RESULTS_ROOT = PACKAGE_ROOT / "results"
REFERENCE_ROOT = PACKAGE_ROOT / "cache/reference"
RECAST_RUNTIME = BASELINES / "methods/worldgen/geometry/runtime/recast_glibc231_clean2"
COMMON_NAVMESH = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"

sys.path.insert(0, str(RECAST_RUNTIME))
sys.path.insert(0, str(REPO_ROOT))
# Reuse the already-installed pure-Python plyfile package at low priority.
# torch/gsplat remain isolated in the Python 3.10 extraction subprocess.
sys.path.append(str(PYTHON310_SITE))
from baselines.methods.worldgen.geometry import (
    worldgen_geometry as common,
)  # noqa: E402

common.REFERENCE_CACHE = REFERENCE_ROOT


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_text(path: Path, value: str) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def load_protocol() -> dict[str, Any]:
    return yaml.safe_load(PROTOCOL_PATH.read_text(encoding="utf-8"))


def load_specs(
    domain: str, protocol: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    protocol = protocol or load_protocol()
    path = REPO_ROOT / protocol["specs"][domain]
    rows = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 25 or [row["spec_index"] for row in rows] != list(range(25)):
        raise RuntimeError(f"Expected 25 ordered {domain} specs in {path}")
    return rows


def expected_tasks(
    phase: str, domains: list[str]
) -> list[tuple[str, dict[str, Any], int]]:
    protocol = load_protocol()
    pilot_specs = set(int(value) for value in protocol["pilot_spec_indices"])
    seeds = protocol["pilot_seeds"] if phase == "pilot" else protocol["seeds"]
    return [
        (domain, spec, int(seed))
        for domain in domains
        for spec in load_specs(domain, protocol)
        if phase == "formal" or int(spec["spec_index"]) in pilot_specs
        for seed in seeds
    ]


def output_run(domain: str, spec_id: str, seed: int) -> Path:
    return DATA_ROOT / domain / "syncity3k" / spec_id / f"seed_{seed}"


def source_run(domain: str, spec_id: str, seed: int) -> Path:
    return TABLE2_ROOT / domain / "syncity3k" / spec_id / f"seed_{seed}"


def relative_link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink():
        if destination.resolve() == source.resolve():
            return
        destination.unlink()
    elif destination.exists():
        raise RuntimeError(
            f"Refusing to replace non-symlink raw artifact: {destination}"
        )
    destination.symlink_to(os.path.relpath(source, destination.parent))


def implementation_hashes() -> dict[str, str]:
    return {
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "method_lock_sha256": sha256_file(METHOD_LOCK_PATH),
        "evaluator_sha256": sha256_file(Path(__file__)),
        "extractor_sha256": sha256_file(EXTRACTOR),
        "common_navmesh_sha256": sha256_file(COMMON_NAVMESH),
    }


def is_current(run_dir: Path) -> bool:
    manifest_path = run_dir / "run_manifest.json"
    metric_path = run_dir / "metrics/navigability.json"
    marker = run_dir / "EVALUATION_SUCCESS"
    if not all(path.is_file() for path in (manifest_path, metric_path, marker)):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if any(
            manifest.get(key) != value for key, value in implementation_hashes().items()
        ):
            return False
        if manifest.get("metric_sha256") != sha256_file(metric_path):
            return False
        source = Path(manifest["source_run"])
        source_manifest = source / "run_manifest.json"
        if not source_manifest.is_file():
            return False
        stat = source_manifest.stat()
        if (
            manifest.get("source_manifest_size") != stat.st_size
            or manifest.get("source_manifest_mtime_ns") != stat.st_mtime_ns
        ):
            return False
        if manifest.get("geometry_extracted"):
            collision = run_dir / "scene/canonical/collision.ply"
            return collision.is_file() and manifest.get(
                "collision_sha256"
            ) == sha256_file(collision)
        return True
    except Exception:
        return False


def structural_na(spec: dict[str, Any], seed: int) -> dict[str, Any]:
    return {
        "method": "syncity3k",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "collision_rate": None,
        "floating_rate": None,
        "oob_rate": None,
        "support_validity": None,
        "valid_scene": None,
        "reason": "N/A-I",
        "detail": "The final scene-scale Gaussian has no recoverable native object instances, roles, colliders, or support edges.",
    }


def failed_navigation(
    spec: dict[str, Any],
    seed: int,
    failure: dict[str, Any],
    source_manifest: dict[str, Any],
    geometry: bool,
    scale: bool,
) -> dict[str, Any]:
    return {
        "method": "syncity3k",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "empty_reference_area_m2": 0.0,
        "final_navmesh_area_m2": 0.0,
        "raw_navigable_area_ratio": 0.0,
        "navigable_area_ratio": 0.0,
        "largest_component_area_m2": 0.0,
        "raw_connected_area_ratio": 0.0,
        "connected_area_ratio": 0.0,
        "component_count": 0,
        "registered_spawn": None,
        "final_spawn_projection": None,
        "spawn_check_passed": False,
        "navmesh_success": False,
        "mesh_extraction_success": geometry,
        "scale_calibration_success": scale,
        "table2_generation_success": bool(source_manifest.get("generation_success")),
        "table2_render_success": bool(source_manifest.get("render_success")),
        "native_navmesh_used": False,
        "failures": [failure],
    }


def worker_environment(gpu: int) -> dict[str, str]:
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
            "HF_HOME": str(BASELINES / "checkpoints/syncity3k/huggingface"),
            "HF_HUB_CACHE": str(BASELINES / "checkpoints/syncity3k/huggingface/hub"),
            "TORCH_HOME": str(BASELINES / "checkpoints/syncity3k/torch"),
            "XDG_CACHE_HOME": str(BASELINES / "cache/syncity3k/xdg"),
            "TORCH_EXTENSIONS_DIR": str(BASELINES / "cache/syncity3k/torch_extensions"),
            "WARP_CACHE_PATH": str(BASELINES / "cache/syncity3k/warp"),
            "TMPDIR": str(BASELINES / "tmp/syncity3k"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
            "PYTHONUNBUFFERED": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "PYTHONPATH": os.pathsep.join(
                [str(REPO_ROOT), str(BASELINES / "vendor/syncity-3k")]
            ),
        }
    )
    return environment


def cached_source_hash(raw: Path, previous: dict[str, Any]) -> str:
    stat = raw.stat()
    if (
        previous.get("source_gaussian_sha256")
        and previous.get("source_gaussian_size") == stat.st_size
        and previous.get("source_gaussian_mtime_ns") == stat.st_mtime_ns
    ):
        return str(previous["source_gaussian_sha256"])
    return sha256_file(raw)


def run_one(domain: str, spec: dict[str, Any], seed: int, gpu: int) -> dict[str, Any]:
    run_dir = output_run(domain, spec["spec_id"], seed)
    run_dir.mkdir(parents=True, exist_ok=True)
    if is_current(run_dir):
        metric = json.loads(
            (run_dir / "metrics/navigability.json").read_text(encoding="utf-8")
        )
        return {
            "domain": domain,
            "spec_id": spec["spec_id"],
            "seed": seed,
            "gpu": gpu,
            "status": "resumed_current",
            "navmesh_success": bool(metric["navmesh_success"]),
        }
    previous = (
        json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
        if (run_dir / "run_manifest.json").is_file()
        else {}
    )
    started, started_at = time.monotonic(), utc_now()
    source = source_run(domain, spec["spec_id"], seed)
    source_manifest: dict[str, Any] = {}
    geometry_extracted = False
    scale_calibrated = False
    manifest: dict[str, Any] = {
        **implementation_hashes(),
        "protocol_id": load_protocol()["protocol_id"],
        "method": "syncity3k",
        "display_name": "SynCity 3000",
        "domain": domain,
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "track": "surface_only",
        "source_run": str(source.resolve()),
        "reuse_table2": True,
        "regenerated": False,
        "downloaded": False,
        "native_navmesh_used": False,
        "gpu": gpu,
        "started_at_utc": started_at,
    }
    for child in (
        "input",
        "scene/raw",
        "scene/canonical",
        "navigation",
        "metrics",
        "logs",
    ):
        (run_dir / child).mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    boundary = common.reference_definition(spec, load_protocol())
    atomic_json(run_dir / "input/boundaries.json", boundary)
    atomic_json(run_dir / "metrics/structural.json", structural_na(spec, seed))
    try:
        source_manifest_path = source / "run_manifest.json"
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        stat_manifest = source_manifest_path.stat()
        manifest["source_manifest_size"] = stat_manifest.st_size
        manifest["source_manifest_mtime_ns"] = stat_manifest.st_mtime_ns
        manifest["source_table2_manifest_sha256"] = sha256_file(source_manifest_path)
        if (
            not source_manifest.get("generation_success")
            or not (source / "GENERATION_SUCCESS").exists()
        ):
            raise RuntimeError("table2_generation_method_failure")
        raw = source / "scene/scene_color_adjusted.ply"
        if not raw.is_file():
            raise FileNotFoundError(raw)
        native_input = json.loads(
            (source / "input/native_input.json").read_text(encoding="utf-8")
        )
        if int(native_input.get("scene_size", -1)) != int(
            load_protocol()["scale_calibration"]["native_scene_grid_units"]
        ):
            raise RuntimeError(
                "Table 2 native scene grid differs from frozen Table 3 scale anchor"
            )
        atomic_json(run_dir / "input/native_input.json", native_input)
        relative_link(raw, run_dir / "scene/raw/scene_color_adjusted.ply")
        raw_hash = cached_source_hash(raw, previous)
        raw_stat = raw.stat()
        manifest.update(
            {
                "source_gaussian": str(raw.resolve()),
                "source_gaussian_sha256": raw_hash,
                "source_gaussian_size": raw_stat.st_size,
                "source_gaussian_mtime_ns": raw_stat.st_mtime_ns,
                "table2_generation_success": True,
                "table2_render_success": bool(source_manifest.get("render_success")),
            }
        )
        command = [
            str(PYTHON310),
            str(EXTRACTOR),
            "--raw",
            str(raw),
            "--spec",
            str(run_dir / "input/spec.json"),
            "--boundaries",
            str(run_dir / "input/boundaries.json"),
            "--output-dir",
            str(run_dir / "scene/canonical"),
            "--source-sha256",
            raw_hash,
        ]
        log_path = run_dir / "logs/extract_surface.log"
        with log_path.open("w", encoding="utf-8") as handle:
            completed = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=worker_environment(gpu),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
                timeout=1800,
                check=False,
            )
        if completed.returncode != 0:
            detail = log_path.read_text(encoding="utf-8", errors="replace")[-8000:]
            raise RuntimeError(
                f"surface_extractor_exit_{completed.returncode}: {detail}"
            )
        extraction_path = run_dir / "scene/canonical/extraction.json"
        extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
        collision = run_dir / "scene/canonical/collision.ply"
        if extraction.get("source_gaussian_sha256") != raw_hash or extraction.get(
            "collision_sha256"
        ) != sha256_file(collision):
            raise RuntimeError("Surface extraction provenance/hash validation failed")
        geometry_extracted = True
        scale_calibrated = True
        reference_dir = common.ensure_reference_cache(boundary, load_protocol())
        ref_vertices, ref_faces, reference_meta = common.load_reference(reference_dir)
        relative_link(
            reference_dir / "reference.ply",
            run_dir / "scene/canonical/empty_reference.ply",
        )
        common.save_navmesh(
            run_dir / "navigation/empty_reference.navmesh", ref_vertices, ref_faces
        )
        final_vertices, final_faces, final_meta = common.build(
            collision, common.recast_config(load_protocol()), 0.0
        )
        common.save_navmesh(
            run_dir / "navigation/final.navmesh", final_vertices, final_faces
        )
        common.write_ply(
            run_dir / "navigation/final.navmesh.ply", final_vertices, final_faces
        )
        final_area = float(common.triangle_areas(final_vertices, final_faces).sum())
        reference_area = float(reference_meta["reference_area_m2"])
        components, component_areas = common.connected_components(
            final_vertices, final_faces
        )
        largest = component_areas[0] if component_areas else 0.0
        registered = reference_meta["registered_spawn"]
        final_spawn = (
            common.spawn_projection(
                tuple(registered["point_m"]), final_vertices, final_faces
            )
            if registered.get("projected")
            else {"projected": False, "horizontal_distance_m": None}
        )
        minimum_fraction = float(
            load_protocol()["success"]["minimum_reference_area_fraction"]
        )
        navmesh_success = bool(
            final_meta.get("builder_returned")
            and reference_area > 0.0
            and np.isfinite(final_area)
            and final_area >= minimum_fraction * reference_area
            and final_spawn.get("projected")
        )
        raw_navigable = (
            100.0 * min(1.0, max(0.0, final_area / reference_area))
            if reference_area > 0.0
            else 0.0
        )
        raw_connected = 100.0 * largest / final_area if final_area > 0.0 else 0.0
        atomic_json(
            run_dir / "navigation/components.json",
            {
                "component_count": len(components),
                "component_areas_m2": component_areas,
                "components": components,
            },
        )
        common.draw_debug(
            run_dir / "navigation/debug_topdown.png",
            boundary,
            ref_vertices,
            ref_faces,
            final_vertices,
            final_faces,
            components,
        )
        metric = {
            "method": "syncity3k",
            "domain": domain,
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "track": "surface_only",
            "empty_reference_area_m2": reference_area,
            "final_navmesh_area_m2": final_area,
            "raw_navigable_area_ratio": raw_navigable,
            "navigable_area_ratio": raw_navigable if navmesh_success else 0.0,
            "largest_component_area_m2": largest,
            "raw_connected_area_ratio": raw_connected,
            "connected_area_ratio": raw_connected if navmesh_success else 0.0,
            "component_count": len(components),
            "registered_spawn": registered,
            "final_spawn_projection": final_spawn,
            "spawn_check_passed": bool(final_spawn.get("projected")),
            "navmesh_success": navmesh_success,
            "mesh_extraction_success": True,
            "scale_calibration_success": True,
            "table2_generation_success": True,
            "table2_render_success": bool(source_manifest.get("render_success")),
            "scale_calibration": extraction["scale_calibration"],
            "surface_extraction": extraction,
            "reference_key": reference_meta["key"],
            "reference_recast": reference_meta["recast"],
            "final_recast": final_meta,
            "native_navmesh_used": False,
            "failures": []
            if navmesh_success
            else [
                {
                    "type": "navmesh_success_predicate_failure",
                    "message": "area and/or spawn predicate failed; all three main navigation metrics use ITT zero",
                }
            ],
        }
        manifest.update(
            {
                "collision_sha256": sha256_file(collision),
                "extraction_sha256": sha256_file(extraction_path),
                "scale_calibration": extraction["scale_calibration"],
                "surface_extraction": {
                    key: extraction[key]
                    for key in (
                        "algorithm",
                        "gaussian_count",
                        "selected_cameras",
                        "mesh_vertices",
                        "mesh_faces",
                    )
                },
                "reference_key": reference_meta["key"],
            }
        )
    except Exception as error:
        failure = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        atomic_text(run_dir / "logs/evaluation_error.log", failure["traceback"])
        metric = failed_navigation(
            spec, seed, failure, source_manifest, geometry_extracted, scale_calibrated
        )
    metric_path = run_dir / "metrics/navigability.json"
    atomic_json(metric_path, metric)
    atomic_text(
        run_dir / "EVALUATION_SUCCESS",
        "SynCity 3000 Table-3 measurement completed under ITT\n",
    )
    manifest.update(
        {
            "table2_generation_success": bool(
                source_manifest.get("generation_success")
            ),
            "table2_render_success": bool(source_manifest.get("render_success")),
            "geometry_extracted": geometry_extracted,
            "scale_calibrated": scale_calibrated,
            "navmesh_success": bool(metric["navmesh_success"]),
            "evaluation_completed": True,
            "failure_count": len(metric["failures"]),
            "metric_sha256": sha256_file(metric_path),
            "ended_at_utc": utc_now(),
            "wall_time_s": time.monotonic() - started,
            "cuda_visible_devices": str(gpu),
        }
    )
    atomic_json(run_dir / "run_manifest.json", manifest)
    return {
        "domain": domain,
        "spec_id": spec["spec_id"],
        "seed": seed,
        "gpu": gpu,
        "status": "complete",
        "geometry_extracted": geometry_extracted,
        "scale_calibrated": scale_calibrated,
        "navmesh_success": bool(metric["navmesh_success"]),
        "navigable_area_ratio": float(metric["navigable_area_ratio"]),
        "connected_area_ratio": float(metric["connected_area_ratio"]),
        "failure_type": metric["failures"][0]["type"] if metric["failures"] else None,
        "wall_time_s": manifest["wall_time_s"],
    }


def configure_worker(gpu: int) -> None:
    os.environ.update(worker_environment(gpu))
    work = (PACKAGE_ROOT / "work") / f"gpu_{gpu}"
    work.mkdir(parents=True, exist_ok=True)


def matrix_worker(
    gpu: int, tasks: list[tuple[str, dict[str, Any], int]], phase: str
) -> None:
    configure_worker(gpu)
    rows = []
    for domain, spec, seed in tasks:
        try:
            row = run_one(domain, spec, seed, gpu)
        except Exception as error:
            row = {
                "domain": domain,
                "spec_id": spec["spec_id"],
                "seed": seed,
                "gpu": gpu,
                "infrastructure_error": f"{type(error).__name__}: {error}",
            }
        rows.append(row)
        print("SYNCITY3K_TABLE3_ITEM " + json.dumps(row, sort_keys=True), flush=True)
    atomic_text(
        RESULTS_ROOT / f"matrix_{phase}_gpu_{gpu}.jsonl",
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
    )


def run_matrix(phase: str, domains: list[str], gpus: list[int]) -> int:
    RESULTS_ROOT.mkdir(parents=True, exist_ok=True)
    tasks = expected_tasks(phase, domains)
    pending = [
        task
        for task in tasks
        if not is_current(output_run(task[0], task[1]["spec_id"], task[2]))
    ]
    print(
        json.dumps(
            {
                "phase": phase,
                "expected": len(tasks),
                "already_current": len(tasks) - len(pending),
                "pending": len(pending),
                "gpus": gpus,
            },
            sort_keys=True,
        ),
        flush=True,
    )
    assignments = [pending[index :: len(gpus)] for index in range(len(gpus))]
    context = mp.get_context("spawn")
    processes = []
    for gpu, assignment in zip(gpus, assignments):
        if not assignment:
            continue
        process = context.Process(
            target=matrix_worker,
            args=(gpu, assignment, phase),
            name=f"syncity3k-table3-gpu-{gpu}",
        )
        process.start()
        processes.append(process)
    failures = []
    for process in processes:
        process.join()
        if process.exitcode != 0:
            failures.append({"name": process.name, "exitcode": process.exitcode})
    records = []
    for gpu in gpus:
        path = RESULTS_ROOT / f"matrix_{phase}_gpu_{gpu}.jsonl"
        if path.is_file():
            records.extend(
                json.loads(line)
                for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            )
    atomic_json(
        RESULTS_ROOT / f"matrix_{phase}.json",
        {
            "phase": phase,
            "expected": len(tasks),
            "records": records,
            "worker_failures": failures,
        },
    )
    return 1 if failures or any("infrastructure_error" in row for row in records) else 0


def inventory() -> dict[str, Any]:
    rows = []
    for domain, spec, seed in expected_tasks("formal", ["indoor", "urban"]):
        source = source_run(domain, spec["spec_id"], seed)
        manifest_path = source / "run_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {}
        )
        raw = source / "scene/scene_color_adjusted.ply"
        rows.append(
            {
                "domain": domain,
                "spec_id": spec["spec_id"],
                "logical_seed": seed,
                "manifest": manifest_path.is_file(),
                "generation_success": bool(manifest.get("generation_success")),
                "render_success": bool(manifest.get("render_success")),
                "raw_gaussian": raw.is_file(),
                "raw_gaussian_bytes": raw.stat().st_size if raw.is_file() else 0,
                "reusable_raw": bool(manifest.get("generation_success"))
                and raw.is_file(),
                "failure_reason": manifest.get("failure_reason"),
            }
        )
    payload = {
        "created_at_utc": utc_now(),
        "method": "syncity3k",
        "planned_runs": len(rows),
        "reusable_raw": sum(row["reusable_raw"] for row in rows),
        "generation_failures": sum(not row["generation_success"] for row in rows),
        "render_success": sum(row["render_success"] for row in rows),
        "total_raw_bytes": sum(row["raw_gaussian_bytes"] for row in rows),
        "regeneration_performed": False,
        "downloads_performed": False,
        "rows": rows,
    }
    payload["complete"] = (
        payload["planned_runs"]
        == payload["reusable_raw"] + payload["generation_failures"]
        == 200
    )
    atomic_json((RESULTS_ROOT / "reuse_inventory.json"), payload)
    print(
        json.dumps(
            {
                key: payload[key]
                for key in (
                    "planned_runs",
                    "reusable_raw",
                    "generation_failures",
                    "render_success",
                    "total_raw_bytes",
                    "complete",
                )
            },
            indent=2,
        )
    )
    return payload


def create_lock() -> dict[str, Any]:
    import recast

    payload = {
        "created_at_utc": utc_now(),
        "protocol_id": load_protocol()["protocol_id"],
        "files": {
            str(path.relative_to(REPO_ROOT)): sha256_file(path)
            for path in (
                PROTOCOL_PATH,
                METHOD_LOCK_PATH,
                EXTRACTOR,
                Path(__file__),
                COMMON_NAVMESH,
                Path(recast.__file__).resolve(),
            )
        },
        "runtime": {
            "driver_python": sys.version.split()[0],
            "extractor_python": "3.10.20",
            "gsplat": "1.5.3",
            "recast_version": str(recast.RecastNavMesh().get_version()),
        },
        "native_navmesh_scored": False,
        "components_connected": False,
        "largest_component_only": False,
    }
    atomic_json(METRICS_LOCK_PATH, payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def bootstrap(values: np.ndarray, repeats: int, seed: int) -> list[float]:
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(values), size=(repeats, len(values)))
    return [
        float(value)
        for value in np.quantile(values[indices].mean(axis=1), [0.025, 0.975])
    ]


def aggregate() -> dict[str, Any]:
    protocol = load_protocol()
    full_domains, csv_rows = {}, []
    for domain_index, domain in enumerate(protocol["domains"]):
        scene_rows, failures = [], Counter()
        specs = load_specs(domain, protocol)
        for spec in specs:
            for seed in protocol["seeds"]:
                path = (
                    output_run(domain, spec["spec_id"], int(seed))
                    / "metrics/navigability.json"
                )
                if not path.is_file():
                    raise RuntimeError(f"Missing formal metric: {path}")
                row = json.loads(path.read_text(encoding="utf-8"))
                scene_rows.append(row)
                for failure in row.get("failures", []):
                    failures[failure.get("type", "unknown")] += 1
        spec_rows = []
        for spec in specs:
            members = [row for row in scene_rows if row["spec_id"] == spec["spec_id"]]
            spec_rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "spec_index": spec["spec_index"],
                    "navigable_area_ratio": float(
                        np.mean([row["navigable_area_ratio"] for row in members])
                    ),
                    "connected_area_ratio": float(
                        np.mean([row["connected_area_ratio"] for row in members])
                    ),
                    "navmesh_success_rate": 100.0
                    * float(np.mean([row["navmesh_success"] for row in members])),
                }
            )
        metrics = {}
        for offset, name in enumerate(
            ("navigable_area_ratio", "connected_area_ratio", "navmesh_success_rate")
        ):
            values = np.asarray([row[name] for row in spec_rows], dtype=float)
            metrics[name] = {
                "mean": float(values.mean()),
                "ci95": bootstrap(
                    values,
                    int(protocol["aggregation"]["bootstrap_repeats"]),
                    int(protocol["aggregation"]["bootstrap_seed"])
                    + 100 * domain_index
                    + offset,
                ),
            }
        summary = {
            "method": "syncity3k",
            "display_name": "SynCity 3000",
            "domain": domain,
            "track": "surface_only",
            "collision_rate": "N/A-I",
            "floating_rate": "N/A-I",
            "oob_rate": "N/A-I",
            "support_validity": "N/A-I",
            "navigable_area_ratio": metrics["navigable_area_ratio"]["mean"],
            "connected_area_ratio": metrics["connected_area_ratio"]["mean"],
            "navmesh_success_rate": metrics["navmesh_success_rate"]["mean"],
            "valid_scene_rate": "N/A-I",
            "planned_runs": 100,
            "evaluated_runs": len(scene_rows),
            "raw_geometry_coverage": sum(
                row.get("table2_generation_success", False) for row in scene_rows
            )
            / 100.0,
            "geometry_coverage": sum(
                row.get("mesh_extraction_success", False) for row in scene_rows
            )
            / 100.0,
            "scale_calibration_coverage": sum(
                row.get("scale_calibration_success", False) for row in scene_rows
            )
            / 100.0,
            "instance_coverage": 0.0,
        }
        full_domains[domain] = {
            "summary": summary,
            "metrics": metrics,
            "failure_breakdown": dict(failures),
            "spec_rows": spec_rows,
            "scene_rows": scene_rows,
        }
        csv_rows.append(summary)
    result = {
        "protocol_id": protocol["protocol_id"],
        **implementation_hashes(),
        "metrics_lock_sha256": sha256_file(METRICS_LOCK_PATH),
        "aggregated_at_utc": utc_now(),
        "failure_policy": "intention_to_treat",
        "aggregation_order": protocol["aggregation"]["order"],
        "bootstrap_repeats": protocol["aggregation"]["bootstrap_repeats"],
        "domains": full_domains,
    }
    atomic_json((RESULTS_ROOT / "table3_full.json"), result)
    columns = list(csv_rows[0])
    lines = [",".join(columns)]
    for row in csv_rows:
        lines.append(
            ",".join(
                f"{row[column]:.10g}"
                if isinstance(row[column], float)
                else str(row[column])
                for column in columns
            )
        )
    atomic_text((RESULTS_ROOT / "table3.csv"), "\n".join(lines) + "\n")
    print(
        json.dumps(
            {domain: full_domains[domain]["summary"] for domain in protocol["domains"]},
            indent=2,
            sort_keys=True,
        )
    )
    return result


def create_montage(tasks: list[tuple[str, dict[str, Any], int]], output: Path) -> None:
    tile_width, tile_height = 240, 268
    tiles = []
    for domain, spec, seed in tasks:
        source = (
            output_run(domain, spec["spec_id"], seed) / "navigation/debug_topdown.png"
        )
        tile = Image.new("RGB", (tile_width, tile_height), "white")
        draw = ImageDraw.Draw(tile)
        if source.is_file():
            image = Image.open(source).convert("RGB")
            image.thumbnail((tile_width, tile_width))
            tile.paste(image, ((tile_width - image.width) // 2, 0))
        else:
            draw.rectangle((8, 8, tile_width - 8, tile_width - 8), outline="red")
        draw.text((5, 244), f"{domain} {spec['spec_id']} s{seed}", fill="black")
        tiles.append(tile)
    columns = 4
    montage = Image.new(
        "RGB",
        (columns * tile_width, math.ceil(len(tiles) / columns) * tile_height),
        "white",
    )
    for index, tile in enumerate(tiles):
        montage.paste(
            tile, ((index % columns) * tile_width, (index // columns) * tile_height)
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    montage.save(output)


def audit(phase: str) -> dict[str, Any]:
    tasks = expected_tasks(phase, ["indoor", "urban"])
    problems, counts = [], Counter()
    hashes = implementation_hashes()
    successful = []
    for domain, spec, seed in tasks:
        run_dir = output_run(domain, spec["spec_id"], seed)
        metric_path, manifest_path = (
            run_dir / "metrics/navigability.json",
            run_dir / "run_manifest.json",
        )
        counts["planned"] += 1
        if not metric_path.is_file() or not manifest_path.is_file():
            problems.append(f"missing result: {run_dir}")
            continue
        try:
            metric = json.loads(metric_path.read_text(encoding="utf-8"))
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            structural = json.loads(
                (run_dir / "metrics/structural.json").read_text(encoding="utf-8")
            )
            counts["evaluated"] += 1
            counts["geometry"] += int(bool(metric["mesh_extraction_success"]))
            counts["scale"] += int(bool(metric["scale_calibration_success"]))
            counts["nav_success"] += int(bool(metric["navmesh_success"]))
            counts["table2_generation_success"] += int(
                bool(metric["table2_generation_success"])
            )
            if metric["mesh_extraction_success"]:
                successful.append(run_dir)
            for name in ("navigable_area_ratio", "connected_area_ratio"):
                value = float(metric[name])
                if not math.isfinite(value) or not 0.0 <= value <= 100.0:
                    problems.append(f"invalid {name}: {run_dir}: {value}")
            if not metric["navmesh_success"] and any(
                float(metric[name]) != 0.0
                for name in ("navigable_area_ratio", "connected_area_ratio")
            ):
                problems.append(f"ITT zero violation: {run_dir}")
            if structural.get("reason") != "N/A-I" or any(
                structural.get(name) is not None
                for name in (
                    "collision_rate",
                    "floating_rate",
                    "oob_rate",
                    "support_validity",
                    "valid_scene",
                )
            ):
                problems.append(f"structural N/A-I violation: {run_dir}")
            if (
                metric.get("native_navmesh_used") is not False
                or manifest.get("native_navmesh_used") is not False
            ):
                problems.append(f"native NavMesh flag violation: {run_dir}")
            if any(manifest.get(key) != value for key, value in hashes.items()):
                problems.append(f"implementation hash mismatch: {run_dir}")
            if manifest.get("metric_sha256") != sha256_file(metric_path):
                problems.append(f"metric hash mismatch: {run_dir}")
            if not (run_dir / "EVALUATION_SUCCESS").is_file():
                problems.append(f"missing terminal marker: {run_dir}")
        except Exception as error:
            problems.append(f"audit exception {run_dir}: {error}")
    spotcheck_rows = []
    if phase == "formal" and successful:
        selected = random.Random(20260914).sample(successful, min(10, len(successful)))
        for run_dir in selected:
            manifest = json.loads(
                (run_dir / "run_manifest.json").read_text(encoding="utf-8")
            )
            actual = sha256_file(Path(manifest["source_gaussian"]))
            passed = actual == manifest["source_gaussian_sha256"]
            spotcheck_rows.append(
                {
                    "run_dir": str(run_dir),
                    "expected": manifest["source_gaussian_sha256"],
                    "actual": actual,
                    "passed": passed,
                }
            )
            if not passed:
                problems.append(f"raw spotcheck hash mismatch: {run_dir}")
        atomic_json(
            (RESULTS_ROOT / "spotcheck.json"),
            {
                "seed": 20260914,
                "sample_count": len(spotcheck_rows),
                "rows": spotcheck_rows,
                "passed": all(row["passed"] for row in spotcheck_rows),
            },
        )
    if phase == "pilot":
        create_montage(tasks, (RESULTS_ROOT / "pilot_montage.png"))
    payload = {
        "created_at_utc": utc_now(),
        "phase": phase,
        "expected": len(tasks),
        "counts": dict(counts),
        "problem_count": len(problems),
        "problems": problems,
        "spotcheck_count": len(spotcheck_rows),
        "native_navmesh_used": False,
        "passed": not problems
        and counts["planned"] == counts["evaluated"] == len(tasks),
    }
    atomic_json(RESULTS_ROOT / f"audit_{phase}.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    subparsers.add_parser("lock")
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    run_parser.add_argument(
        "--domains", nargs="+", choices=("indoor", "urban"), default=["indoor", "urban"]
    )
    run_parser.add_argument("--gpus", nargs="+", type=int, required=True)
    subparsers.add_parser("aggregate")
    audit_parser = subparsers.add_parser("audit")
    audit_parser.add_argument("--phase", choices=("pilot", "formal"), default="formal")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.command == "inventory":
        return 0 if inventory()["complete"] else 1
    if args.command == "lock":
        create_lock()
        return 0
    if args.command == "run":
        return run_matrix(args.phase, args.domains, args.gpus)
    if args.command == "aggregate":
        aggregate()
        return 0
    if args.command == "audit":
        return 0 if audit(args.phase)["passed"] else 1
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

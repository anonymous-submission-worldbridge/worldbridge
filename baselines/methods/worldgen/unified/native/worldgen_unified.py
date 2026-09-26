#!/usr/bin/env python3
"""Run and audit the WorldGen (ZiYang-xie) Table 4 independent track."""

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
import base64
import concurrent.futures
import csv
import hashlib
import importlib.util
import io
import json
import math
import os
import random
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
REPO = BASELINES.parent
PROTOCOL_DIR = BASELINES / "methods/worldgen/protocol/unified/native"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
SPEC_PATH = PROTOCOL_DIR / "specs.jsonl"
LOCK_PATH = PROTOCOL_DIR / "worldgen_method.lock.json"
WORLDGEN_RESULTS = BASELINES / "results/table4_worldgen"
TABLE2_LOCK_PATH = BASELINES / "protocol/generation/methods.lock.json"
TABLE2_ADAPTER_PATH = BASELINES / "methods/worldgen/adapter.py"
TABLE2_RENDERER_PATH = (
    BASELINES / "methods/worldgen/tools/render_worldgen_generation.py"
)
WORLDGEN_SOURCE = BASELINES / "sources/WorldGen/src"
PYTHON = BASELINES / "environments/worldgen/bin/python"
MODEL_MANIFEST = BASELINES / "hyworld2_runtime/manifests/qwen3_vl_8b_modelscope.json"
QWEN_ROOT = BASELINES / "hyworld2_runtime/checkpoints/Qwen3-VL-8B-Instruct"
BLIND_SALT = "worldbridge-table4-worldgen-v1-frozen-before-aqs"
SIDES = ("exterior", "interior")
SIDE_DOMAIN = {"exterior": "urban", "interior": "indoor"}
SIDE_PROMPT_KEY = {"exterior": "exterior_prompt_en", "interior": "interior_prompt_en"}
NATIVE_NA_METRICS = (
    "spatial_aqs",
    "shape_iou",
    "entrance_alignment",
    "entrance_passability",
    "transition_collision",
    "io_connectivity_rate",
    "cross_boundary_reachability",
)
REQUIRED_SPEC_KEYS = {
    "spec_id",
    "spec_index",
    "function",
    "visual_theme",
    "world_prompt_en",
    "exterior_prompt_en",
    "interior_prompt_en",
    "target_building",
    "interior_program",
    "visual_inheritance",
    "entrance",
    "outdoor_anchor_rules",
    "indoor_goal_rules",
    "functional_questions",
    "visual_questions",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must remain below {BASELINES}: {resolved}") from exc
    return resolved


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    )
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_text(path: Path, text: str) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(
        f".{path.name}.{os.getpid()}.{threading.get_ident()}.{time.time_ns()}.tmp"
    )
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def load_protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def load_specs() -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in SPEC_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def validate_specs() -> dict[str, Any]:
    protocol = load_protocol()
    specs = load_specs()
    errors: list[str] = []
    if len(specs) != 25:
        errors.append(f"spec_count={len(specs)} expected=25")
    if [row.get("spec_index") for row in specs] != list(range(25)):
        errors.append("spec_index must be exactly 0..24 in file order")
    ids = [row.get("spec_id") for row in specs]
    if len(set(ids)) != len(ids):
        errors.append("duplicate spec_id")
    expected = {
        (function, theme)
        for function in protocol["functions"]
        for theme in protocol["visual_themes"]
    }
    actual = {(row.get("function"), row.get("visual_theme")) for row in specs}
    if actual != expected:
        errors.append(
            f"cross_product_mismatch missing={sorted(expected-actual)} extra={sorted(actual-expected)}"
        )
    for row in specs:
        sid = str(row.get("spec_id", ""))
        missing = REQUIRED_SPEC_KEYS - set(row)
        if missing:
            errors.append(f"{sid}: missing keys {sorted(missing)}")
        if not re.fullmatch(r"[a-z0-9_]+", sid):
            errors.append(f"{sid}: unsafe spec_id")
        for key in ("world_prompt_en", "exterior_prompt_en", "interior_prompt_en"):
            if len(str(row.get(key, "")).split()) < 8:
                errors.append(f"{sid}: {key} is too short")
        for key in ("functional_questions", "visual_questions"):
            if len(row.get(key, [])) != 4:
                errors.append(f"{sid}: {key} must contain four frozen questions")
        program = row.get("interior_program", {})
        if (
            len(program.get("required_zones", [])) < 4
            or len(program.get("required_objects", [])) < 3
        ):
            errors.append(f"{sid}: incomplete interior program")
        if len(row.get("visual_inheritance", [])) < 3:
            errors.append(f"{sid}: incomplete visual inheritance facts")
    result = {
        "validated_at_utc": utc_now(),
        "passed": not errors,
        "errors": errors,
        "spec_count": len(specs),
        "cross_product_count": len(actual),
        "spec_sha256": sha256_file(SPEC_PATH),
        "protocol_version": protocol["protocol_version"],
    }
    output = WORLDGEN_RESULTS / "spec_validation.json"
    atomic_json(output, result)
    return result


def trial_paths(trial: str) -> tuple[Path, Path, Path]:
    protocol = load_protocol()
    paths = protocol["paths"]
    if trial == "formal":
        keys = ("formal_data", "formal_annotations", "formal_results")
    elif trial == "pilot":
        keys = ("pilot_data", "pilot_annotations", "pilot_results")
    else:
        raise ValueError(trial)
    resolved = tuple(require_below_baselines(REPO / paths[key]) for key in keys)
    return resolved  # type: ignore[return-value]


def trial_specs_and_seeds(trial: str) -> tuple[list[dict[str, Any]], list[int]]:
    protocol = load_protocol()
    specs = load_specs()
    config = protocol[trial]
    indices = config["spec_indices"]
    if indices != "all":
        wanted = set(indices)
        specs = [row for row in specs if row["spec_index"] in wanted]
    return specs, [int(seed) for seed in config["seeds"]]


def pair_dir(data_root: Path, spec_id: str, seed: int) -> Path:
    if not re.fullmatch(r"[a-z0-9_]+", spec_id) or seed not in (0, 1, 2, 3):
        raise ValueError(f"Unsafe pair identity: {spec_id} seed={seed}")
    return require_below_baselines(data_root / spec_id / f"seed_{seed}")


def side_dir(data_root: Path, spec_id: str, seed: int, side: str) -> Path:
    if side not in SIDES:
        raise ValueError(side)
    return pair_dir(data_root, spec_id, seed) / "native" / side


def load_table2_adapter() -> Any:
    spec = importlib.util.spec_from_file_location(
        "worldgen_table2_adapter_frozen", TABLE2_ADAPTER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen Table 2 WorldGen adapter")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_table2_renderer() -> Any:
    spec = importlib.util.spec_from_file_location(
        "worldgen_table2_renderer_frozen", TABLE2_RENDERER_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load frozen Table 2 WorldGen renderer")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def compiled_native_input(spec: dict[str, Any], seed: int, side: str) -> dict[str, Any]:
    protocol = load_protocol()
    generation = protocol["generation"]
    return {
        "method": "worldgen",
        "implementation": "ZiYang-xie/WorldGen",
        "table": 4,
        "track": "matched_text_independent",
        "side": side,
        "domain": SIDE_DOMAIN[side],
        "mode": "t2s",
        "prompt": spec[SIDE_PROMPT_KEY[side]],
        "logical_seed": seed,
        "method_seed": seed,
        "resolution": generation["resolution"][0],
        "panorama_height": generation["resolution"][1],
        "panorama_width": generation["resolution"][0],
        "num_inference_steps": generation["inference_steps"],
        "guidance_scale": generation["guidance_scale"],
        "blend_extend": generation["blend_extend"],
        "prompt_prefix": "A high quality 360 panorama photo of",
        "prompt_suffix": "HDR, RAW, 360 consistent, omnidirectional",
        "return_type": "gaussian_splat+official_triangle_mesh",
        "return_mesh": True,
        "use_sharp": generation["use_sharp"],
        "inpaint_bg": generation["inpaint_bg"],
        "low_vram": generation["low_vram"],
        "depth_model": "haodongli/DA-2",
        "depth_max_distance": 20.0,
        "native_shared_world_frame": False,
        "notes": [
            "The two sides are independent text-to-scene calls with matched specification text.",
            "The upstream public panorama wrapper hard-codes seed 42; the frozen Table 2 adapter calls gen_pano_image directly with the logical seed.",
            "One DA-2 prediction is exported both as the Table 2-compatible Gaussian splat and the official WorldGen panorama triangle mesh.",
            "No transform, portal, building identity, or geometry is synthesized between the two native outputs.",
        ],
    }


def compile_pair(data_root: Path, spec: dict[str, Any], seed: int, trial: str) -> Path:
    run = pair_dir(data_root, spec["spec_id"], seed)
    input_dir = run / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    existing_spec = input_dir / "pair_spec.json"
    generated_any_side = any(
        (
            side_dir(data_root, spec["spec_id"], seed, side) / "scene/panorama.png"
        ).is_file()
        for side in SIDES
    )
    if generated_any_side and existing_spec.is_file():
        if json.loads(existing_spec.read_text(encoding="utf-8")) != spec:
            raise RuntimeError(
                f"Refusing to change a pair spec after native generation: {existing_spec}"
            )
    atomic_json(input_dir / "pair_spec.json", spec)
    table2_lock = json.loads(TABLE2_LOCK_PATH.read_text(encoding="utf-8"))["worldgen"]
    for side in SIDES:
        native = side_dir(data_root, spec["spec_id"], seed, side)
        (native / "input").mkdir(parents=True, exist_ok=True)
        native_input = compiled_native_input(spec, seed, side)
        existing_native_input = native / "input/native_input.json"
        if (
            native / "scene/panorama.png"
        ).is_file() and existing_native_input.is_file():
            if (
                json.loads(existing_native_input.read_text(encoding="utf-8"))
                != native_input
            ):
                raise RuntimeError(
                    f"Refusing to change native input after panorama generation: {existing_native_input}"
                )
        atomic_json(native / "input/spec.json", spec)
        atomic_json(native / "input/native_input.json", native_input)
        manifest_path = native / "run_manifest.json"
        old = json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
        manifest = {
            "method": "worldgen",
            "implementation": "ZiYang-xie/WorldGen",
            "table": 4,
            "trial": trial,
            "track": "matched_text_independent",
            "domain": SIDE_DOMAIN[side],
            "side": side,
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "method_seed": seed,
            "method_commit": table2_lock["commit"],
            "submodules": table2_lock["submodules"],
            "worldgen_lora_revision": table2_lock["weights"][
                "LeoXie/WorldGen:text2scene_lora"
            ]["revision"],
            "spec_file": rel(SPEC_PATH),
            "spec_sha256": sha256_file(SPEC_PATH),
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "native_input": "input/native_input.json",
            "native_input_sha256": sha256_file(native / "input/native_input.json"),
            "output_type": "gaussian_splat+official_triangle_mesh",
            "native_shared_world_frame": False,
            "generation_success": (native / "GENERATION_SUCCESS").is_file(),
            "render_success": (native / "SUCCESS").is_file(),
            "table4_evidence_success": (native / "TABLE4_SUCCESS").is_file(),
            "attempts": old.get("attempts", []),
            "failure_reason": old.get("failure_reason"),
            "failure_detail": old.get("failure_detail", ""),
        }
        atomic_json(manifest_path, manifest)
    refresh_pair(data_root, spec, seed, trial)
    return run


def refresh_pair(
    data_root: Path, spec: dict[str, Any], seed: int, trial: str
) -> dict[str, Any]:
    run = pair_dir(data_root, spec["spec_id"], seed)
    native_status: dict[str, Any] = {}
    for side in SIDES:
        native = side_dir(data_root, spec["spec_id"], seed, side)
        native_status[side] = {
            "panorama": (native / "scene/panorama.png").is_file(),
            "gaussian_splat": (native / "scene/splat.ply").is_file(),
            "official_triangle_mesh": (native / "scene/mesh.ply").is_file(),
            "generation_success": (native / "GENERATION_SUCCESS").is_file(),
            "table2_render_success": (native / "SUCCESS").is_file(),
            "render_success": (native / "TABLE4_SUCCESS").is_file(),
        }
    success = all(native_status[side]["render_success"] for side in SIDES)
    marker = run / "SUCCESS"
    if success:
        atomic_text(marker, "WorldGen Table 4 independent pair output contract valid\n")
    else:
        marker.unlink(missing_ok=True)
    manifest = {
        "method": "worldgen",
        "display_name": "WorldGen (ZiYang-xie)",
        "table": 4,
        "trial": trial,
        "track": "matched_text_independent",
        "pair_id": f"{spec['spec_id']}__seed_{seed}",
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "pair_unit": {
            "world_id": None,
            "target_building_id": None,
            "interior_id": None,
            "entrance_id": None,
            "ground_floor_id": None,
            "native_shared_world_frame": False,
            "reason": "WorldGen generates the exterior and interior in two independent native calls and exposes no building-to-interior identity or common portal.",
        },
        "native_status": native_status,
        "generation_success": all(
            native_status[side]["generation_success"] for side in SIDES
        ),
        "render_success": success,
        "human_postprocessing": False,
        "metric_applicability": {
            "functional_aqs": "numeric",
            "visual_aqs": "numeric",
            **{metric: "N/A-U" for metric in NATIVE_NA_METRICS},
        },
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "spec_sha256": sha256_file(SPEC_PATH),
        "updated_at_utc": utc_now(),
    }
    atomic_json(run / "manifest.json", manifest)
    return manifest


def compile_trial(trial: str) -> dict[str, Any]:
    validation = validate_specs()
    if not validation["passed"]:
        raise RuntimeError(f"Spec validation failed: {validation['errors']}")
    data_root, _, _ = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    for spec in specs:
        for seed in seeds:
            compile_pair(data_root, spec, seed, trial)
    result = {
        "trial": trial,
        "pairs": len(specs) * len(seeds),
        "native_calls": len(specs) * len(seeds) * 2,
        "data_root": rel(data_root),
    }
    print(
        f"TABLE4_WORLDGEN_COMPILE_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def load_worker_tasks(path: Path) -> list[dict[str, Any]]:
    require_below_baselines(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Worker task list must be a JSON list")
    return payload


def reconstruct_splat_and_mesh(
    adapter: Any, model: Any, native: Path, force: bool
) -> str:
    panorama = native / "scene/panorama.png"
    splat_path = native / "scene/splat.ply"
    mesh_path = native / "scene/mesh.ply"
    marker = native / "GENERATION_SUCCESS"
    if marker.exists() and splat_path.exists() and mesh_path.exists() and not force:
        return "skipped_existing_splat_and_mesh"
    if not panorama.exists():
        raise FileNotFoundError(f"Missing panorama: {panorama}")
    started_at = adapter.utc_now()
    started = time.monotonic()
    try:
        import numpy as np
        import open3d as o3d
        from worldgen.pano_depth import pred_pano_depth
        from worldgen.utils.general_utils import convert_rgbd2mesh_panorama
        from worldgen.utils.splat_utils import convert_rgbd_to_gs

        with Image.open(panorama) as handle:
            predictions = pred_pano_depth(model, handle.convert("RGB"))
        splat = convert_rgbd_to_gs(
            predictions["rgb"], predictions["distance"], predictions["rays"]
        )
        original_scales = np.asarray(splat.scales)
        degenerate = ~np.isfinite(original_scales) | (original_scales <= 0.0)
        fixed_count = int(degenerate.sum())
        splat.scales = np.maximum(
            np.abs(np.nan_to_num(original_scales, nan=0.0, posinf=0.0, neginf=0.0)),
            1e-8,
        )
        splat_path.parent.mkdir(parents=True, exist_ok=True)
        splat.save(str(splat_path))
        mesh = convert_rgbd2mesh_panorama(
            predictions["rgb"] / 255.0,
            predictions["distance"],
            predictions["rays"],
        )
        wrote = o3d.io.write_triangle_mesh(
            str(mesh_path),
            mesh,
            write_ascii=False,
            compressed=False,
            print_progress=False,
        )
        if not wrote:
            raise RuntimeError(f"Open3D refused to write {mesh_path}")
        if splat_path.stat().st_size < 1024 or mesh_path.stat().st_size < 1024:
            raise RuntimeError("WorldGen geometry output is unexpectedly small")
        marker.write_text(
            "WorldGen splat and official mesh reconstruction complete\n",
            encoding="utf-8",
        )
        adapter._record_attempt(native, "reconstruct", started_at, started, True)
        manifest_path = native / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["serialization_sanitization"] = {
            "rule": "replace non-finite/non-positive splat scale by max(abs(scale), 1e-8)",
            "fixed_scalar_count": fixed_count,
            "total_scalar_count": int(original_scales.size),
        }
        manifest["geometry"] = {
            "gaussian_splat": "scene/splat.ply",
            "gaussian_splat_bytes": splat_path.stat().st_size,
            "official_triangle_mesh": "scene/mesh.ply",
            "official_triangle_mesh_bytes": mesh_path.stat().st_size,
            "mesh_vertices": len(mesh.vertices),
            "mesh_triangles": len(mesh.triangles),
            "shared_with_other_side": False,
        }
        atomic_json(manifest_path, manifest)
        return "reconstruction_complete_splat_and_mesh"
    except Exception:
        marker.unlink(missing_ok=True)
        detail = traceback.format_exc()
        adapter._record_attempt(
            native, "reconstruct", started_at, started, False, detail
        )
        raise


def validate_table4_side(native: Path, side: str) -> dict[str, Any]:
    """Validate only the four preregistered Table 4 AQS views for one side."""
    import numpy as np

    protocol = load_protocol()
    selected = protocol["render"]["aqs_anchor_indices_per_side"][side]
    anchors = sorted((native / "renders/anchors").glob("rgb_*.png"))
    errors: list[str] = []
    image_stats: list[dict[str, Any]] = []
    if len(anchors) != protocol["render"]["anchors_per_side"]:
        errors.append(
            f"anchor_count={len(anchors)} expected={protocol['render']['anchors_per_side']}"
        )
    for index in selected:
        if index >= len(anchors):
            errors.append(f"missing selected anchor index {index}")
            continue
        path = anchors[index]
        with Image.open(path) as handle:
            pixels = np.asarray(handle.convert("RGB"), dtype=np.float32) / 255.0
        mean_value = float(pixels.mean())
        std_value = float(pixels.std())
        dark_fraction = float((pixels.mean(axis=2) < 0.02).mean())
        image_stats.append(
            {
                "anchor_index": index,
                "path": str(path.relative_to(native)),
                "mean": mean_value,
                "std": std_value,
                "dark_pixel_fraction": dark_fraction,
            }
        )
        if not 0.01 <= mean_value <= 0.99:
            errors.append(f"anchor_{index}: mean={mean_value:.6f} outside [0.01,0.99]")
        if std_value < 0.01:
            errors.append(f"anchor_{index}: std={std_value:.6f} below 0.01")
    for name in ("GENERATION_SUCCESS", "scene/splat.ply", "scene/mesh.ply"):
        if not (native / name).is_file():
            errors.append(f"missing native geometry artifact {name}")
    result = {
        "valid": not errors,
        "side": side,
        "selected_anchor_indices": selected,
        "selected_anchor_count": len(image_stats),
        "errors": errors,
        "image_stats": image_stats,
        "scope": "Table 4 AQS evidence only; Table 2's 50-frame success is reported separately",
    }
    atomic_json(native / "renders/table4_validation.json", result)
    marker = native / "TABLE4_SUCCESS"
    if result["valid"]:
        atomic_text(
            marker, "WorldGen Table 4 side evidence and native geometry valid\n"
        )
    else:
        marker.unlink(missing_ok=True)
    manifest_path = native / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["table4_evidence_success"] = result["valid"]
    manifest["table4_validation"] = "renders/table4_validation.json"
    atomic_json(manifest_path, manifest)
    return result


def worker(phase: str, task_list: Path, data_root: Path, force: bool) -> int:
    data_root = require_below_baselines(data_root)
    tasks = load_worker_tasks(task_list)
    specs = {row["spec_id"]: row for row in load_specs()}
    source = str(WORLDGEN_SOURCE)
    if source in sys.path:
        sys.path.remove(source)
    sys.path.insert(0, source)
    adapter = load_table2_adapter()
    renderer = None
    model = None
    if phase == "panorama":
        import torch
        from worldgen.pano_gen import build_pano_gen_model

        model = build_pano_gen_model(device=torch.device("cuda"), low_vram=False)
    elif phase == "reconstruct":
        import torch
        from worldgen.pano_depth import build_depth_model

        model = build_depth_model(torch.device("cuda"))
    elif phase == "render":
        renderer = load_table2_renderer()
    else:
        raise ValueError(phase)
    failures = 0
    for task in tasks:
        spec = specs[task["spec_id"]]
        seed = int(task["seed"])
        side = task["side"]
        native = side_dir(data_root, spec["spec_id"], seed, side)
        try:
            if phase == "panorama":
                status = adapter.run_panorama_task(model, native, force)
            elif phase == "reconstruct":
                status = reconstruct_splat_and_mesh(adapter, model, native, force)
            else:
                validation = renderer.render_table2(native, force)
                table4_validation = validate_table4_side(native, side)
                status = (
                    f"table4_render_valid_table2_valid={validation['valid']}"
                    if table4_validation["valid"]
                    else "table4_render_invalid"
                )
                if not table4_validation["valid"]:
                    failures += 1
            print(
                f"TABLE4_WORLDGEN_ITEM_OK phase={phase} spec={spec['spec_id']} "
                f"seed={seed} side={side} status={status}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            print(
                f"TABLE4_WORLDGEN_ITEM_FAILED phase={phase} spec={spec['spec_id']} "
                f"seed={seed} side={side} error={type(exc).__name__}:{exc}",
                flush=True,
            )
        try:
            import torch

            torch.cuda.empty_cache()
        except ImportError:
            pass
    print(
        f"TABLE4_WORLDGEN_WORKER_COMPLETE phase={phase} tasks={len(tasks)} failures={failures}",
        flush=True,
    )
    return 1 if failures else 0


def gpu_state() -> dict[int, dict[str, int]]:
    completed = subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"nvidia-smi failed: {completed.stderr.strip()}")
    result: dict[int, dict[str, int]] = {}
    for line in completed.stdout.splitlines():
        index, free, utilization = [int(value.strip()) for value in line.split(",")]
        result[index] = {"free_mib": free, "utilization": utilization}
    return result


def worker_environment(gpu: int) -> dict[str, str]:
    protocol = load_protocol()
    environment = dict(os.environ)
    cuda_home = "/usr/local/cuda-12.8"
    environment.update(
        {
            "CUDA_VISIBLE_DEVICES": str(gpu),
            "HF_HOME": str(BASELINES / "checkpoints/WorldGen/huggingface"),
            "HF_HUB_CACHE": str(BASELINES / "checkpoints/WorldGen/huggingface/hub"),
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "TORCH_HOME": str(BASELINES / "checkpoints/WorldGen/torch"),
            "XDG_CACHE_HOME": str(BASELINES / "cache/worldgen"),
            # Reuse the extension cache that rendered the frozen Table 2
            # WorldGen matrix on this host's L40S cards.  The legacy
            # ``torch_extensions_a6000`` directory is an incomplete sm_86
            # build and concurrent imports race while rebuilding it.
            "TORCH_EXTENSIONS_DIR": str(BASELINES / "cache/worldgen/torch_extensions"),
            "CUDA_HOME": cuda_home,
            "PATH": f"{PYTHON.parent}:{cuda_home}/bin:{environment.get('PATH', '')}",
            "TORCH_CUDA_ARCH_LIST": protocol["resources"]["cuda_arch_list"],
            "MAX_JOBS": "8",
            "TMPDIR": str(BASELINES / "tmp/worldgen_table4"),
            "PYTHONUNBUFFERED": "1",
            "TOKENIZERS_PARALLELISM": "false",
        }
    )
    Path(environment["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    return environment


def all_native_tasks(trial: str) -> list[dict[str, Any]]:
    specs, seeds = trial_specs_and_seeds(trial)
    return [
        {"spec_id": spec["spec_id"], "seed": seed, "side": side}
        for spec in specs
        for seed in seeds
        for side in SIDES
    ]


def phase_complete(native: Path, phase: str) -> bool:
    if phase == "panorama":
        return (native / "scene/panorama.png").is_file()
    if phase == "reconstruct":
        return all(
            (native / name).is_file()
            for name in ("GENERATION_SUCCESS", "scene/splat.ply", "scene/mesh.ply")
        )
    if phase == "render":
        return (native / "TABLE4_SUCCESS").is_file()
    raise ValueError(phase)


def count_phase_complete(trial: str, phase: str) -> int:
    data_root, _, _ = trial_paths(trial)
    return sum(
        phase_complete(
            side_dir(data_root, row["spec_id"], int(row["seed"]), row["side"]), phase
        )
        for row in all_native_tasks(trial)
    )


def verify_formal_lock() -> None:
    protocol = load_protocol()
    if protocol["status"] != "formal_frozen":
        raise RuntimeError(
            "Formal execution requires protocol status formal_frozen after the pilot"
        )
    if not LOCK_PATH.is_file():
        raise RuntimeError(f"Missing frozen method lock: {LOCK_PATH}")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    for key, path in {
        "protocol_sha256": PROTOCOL_PATH,
        "spec_sha256": SPEC_PATH,
        "runner_sha256": Path(__file__),
        "table2_adapter_sha256": TABLE2_ADAPTER_PATH,
        "table2_renderer_sha256": TABLE2_RENDERER_PATH,
        "qwen_model_manifest_sha256": MODEL_MANIFEST,
        "capability_audit_sha256": WORLDGEN_RESULTS / "capability_audit.json",
        "table2_anchor_calibration_sha256": WORLDGEN_RESULTS
        / "table2_anchor_calibration.json",
        "preflight_sha256": WORLDGEN_RESULTS / "preflight.json",
    }.items():
        actual = sha256_file(path)
        if lock.get(key) != actual:
            raise RuntimeError(
                f"Frozen lock mismatch for {key}: {actual} != {lock.get(key)}"
            )


def run_phase(
    trial: str, phase: str, gpus: list[int], workers: int, force: bool
) -> int:
    if phase == "compile":
        compile_trial(trial)
        return 0
    compile_trial(trial)
    if trial == "formal":
        verify_formal_lock()
    protocol = load_protocol()
    allowed = set(protocol["resources"]["allowed_physical_gpus"])
    if workers < 1 or workers > len(gpus) or not set(gpus).issubset(allowed):
        raise ValueError(
            f"Invalid worker/GPU selection workers={workers} gpus={gpus} allowed={sorted(allowed)}"
        )
    data_root, _, _ = trial_paths(trial)
    all_tasks = all_native_tasks(trial)
    tasks = [
        row
        for row in all_tasks
        if force
        or not phase_complete(
            side_dir(data_root, row["spec_id"], int(row["seed"]), row["side"]),
            phase,
        )
    ]
    if not tasks:
        print(
            f"TABLE4_WORLDGEN_PHASE_COMPLETE trial={trial} phase={phase} "
            f"complete={len(all_tasks)}/{len(all_tasks)} worker_failures=[] skipped_all_existing=true",
            flush=True,
        )
        return 0
    selected = gpus[:workers]
    state = gpu_state()
    minimum = int(protocol["resources"]["minimum_free_memory_mib"])
    maximum_util = int(protocol["resources"]["maximum_start_utilization_percent"])
    busy = {
        gpu: state.get(gpu)
        for gpu in selected
        if gpu not in state
        or state[gpu]["free_mib"] < minimum
        or state[gpu]["utilization"] > maximum_util
    }
    if busy:
        print(
            f"TABLE4_WORLDGEN_GPU_GATE_BUSY {json.dumps(busy, sort_keys=True)}",
            flush=True,
        )
        return 75
    queues = {gpu: [] for gpu in selected}
    for index, task in enumerate(tasks):
        queues[selected[index % len(selected)]].append(task)
    task_dir = BASELINES / "work/table4_worldgen/tasklists"
    log_dir = BASELINES / "logs/table4_worldgen" / trial / phase
    task_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)
    processes: list[tuple[int, subprocess.Popen[str], Any, Path]] = []
    for gpu in selected:
        task_path = task_dir / f"{trial}_{phase}_gpu{gpu}.json"
        atomic_json(task_path, queues[gpu])
        command = [
            str(PYTHON),
            str(Path(__file__).resolve()),
            "worker",
            "--phase",
            phase,
            "--task-list",
            str(task_path),
            "--data-root",
            str(data_root),
        ]
        if force:
            command.append("--force")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        log_path = log_dir / f"gpu{gpu}_{stamp}.log"
        log = log_path.open("w", encoding="utf-8")
        log.write(f"COMMAND {json.dumps(command)}\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=REPO,
            env=worker_environment(gpu),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        processes.append((gpu, process, log, log_path))
        print(
            f"TABLE4_WORLDGEN_WORKER_STARTED phase={phase} gpu={gpu} pid={process.pid} log={rel(log_path)}",
            flush=True,
        )
    last_report = 0.0
    try:
        while any(process.poll() is None for _, process, _, _ in processes):
            now = time.monotonic()
            if now - last_report >= 30:
                complete = count_phase_complete(trial, phase)
                print(
                    f"TABLE4_WORLDGEN_PROGRESS trial={trial} phase={phase} complete={complete}/{len(all_tasks)}",
                    flush=True,
                )
                last_report = now
            time.sleep(5)
    except BaseException:
        for _, process, _, _ in processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGINT)
        raise
    finally:
        for _, _, log, _ in processes:
            log.close()
    failures = []
    for gpu, process, _, log_path in processes:
        code = process.wait()
        if code:
            failures.append({"gpu": gpu, "exit_code": code, "log": rel(log_path)})
    specs = {row["spec_id"]: row for row in load_specs()}
    trial_specs, seeds = trial_specs_and_seeds(trial)
    for spec in trial_specs:
        for seed in seeds:
            refresh_pair(data_root, specs[spec["spec_id"]], seed, trial)
    complete = count_phase_complete(trial, phase)
    print(
        f"TABLE4_WORLDGEN_PHASE_COMPLETE trial={trial} phase={phase} "
        f"complete={complete}/{len(all_tasks)} pending_submitted={len(tasks)} "
        f"worker_failures={json.dumps(failures)}",
        flush=True,
    )
    return 1 if failures else 0


def wait_and_run_phase(
    trial: str,
    phase: str,
    candidate_gpus: list[int],
    workers: int,
    force: bool,
    poll_seconds: int,
    stable_samples: int,
    timeout_seconds: int,
) -> int:
    """Wait for genuinely idle GPUs, then atomically re-check and run a phase."""
    if phase == "compile":
        return run_phase(trial, phase, candidate_gpus, workers, force)
    data_root, _, _ = trial_paths(trial)
    if not force and all(
        phase_complete(
            side_dir(data_root, row["spec_id"], int(row["seed"]), row["side"]),
            phase,
        )
        for row in all_native_tasks(trial)
    ):
        return run_phase(trial, phase, candidate_gpus, workers, force)
    protocol = load_protocol()
    minimum = int(protocol["resources"]["minimum_free_memory_mib"])
    maximum_util = int(protocol["resources"]["maximum_start_utilization_percent"])
    allowed = set(protocol["resources"]["allowed_physical_gpus"])
    if workers < 1 or workers > len(candidate_gpus):
        raise ValueError(
            "workers must be positive and no larger than the candidate list"
        )
    if not set(candidate_gpus).issubset(allowed):
        raise ValueError(f"Candidate GPUs must be a subset of {sorted(allowed)}")
    if poll_seconds < 5 or stable_samples < 1 or timeout_seconds < poll_seconds:
        raise ValueError("Invalid wait parameters")
    streak = {gpu: 0 for gpu in candidate_gpus}
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        state = gpu_state()
        for gpu in candidate_gpus:
            row = state.get(gpu)
            idle = bool(
                row is not None
                and row["free_mib"] >= minimum
                and row["utilization"] <= maximum_util
            )
            streak[gpu] = streak[gpu] + 1 if idle else 0
        stable = [gpu for gpu in candidate_gpus if streak[gpu] >= stable_samples]
        print(
            f"TABLE4_WORLDGEN_WAIT trial={trial} phase={phase} "
            f"stable={stable} required={workers} state={json.dumps(state, sort_keys=True)}",
            flush=True,
        )
        if len(stable) >= workers:
            selected = sorted(
                stable,
                key=lambda gpu: (
                    -state[gpu]["free_mib"],
                    state[gpu]["utilization"],
                    gpu,
                ),
            )[:workers]
            code = run_phase(trial, phase, selected, workers, force)
            if code != 75:
                return code
            for gpu in selected:
                streak[gpu] = 0
        time.sleep(poll_seconds)
    print(
        f"TABLE4_WORLDGEN_WAIT_TIMEOUT trial={trial} phase={phase} "
        f"timeout_seconds={timeout_seconds}",
        flush=True,
    )
    return 75


def blind_id(spec_id: str, seed: int) -> str:
    payload = f"{BLIND_SALT}|{spec_id}|{seed}".encode()
    return "P-" + hashlib.sha256(payload).hexdigest()[:12].upper()


def montage_font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
        )
    except OSError:
        return ImageFont.load_default()


def make_pair_montage(
    exterior: list[Path], interior: list[Path], output: Path, item_id: str
) -> None:
    if len(exterior) != 4 or len(interior) != 4:
        raise ValueError("AQS montage requires exactly four views per side")
    tile_w, tile_h, header_h, label_w = 480, 270, 50, 110
    canvas = Image.new("RGB", (label_w + tile_w * 4, header_h + tile_h * 2), "white")
    draw = ImageDraw.Draw(canvas)
    font = montage_font(22)
    small = montage_font(18)
    draw.text(
        (14, 10), f"Anonymous indoor-outdoor pair {item_id}", fill="black", font=font
    )
    for row_index, (label, images) in enumerate(
        (("Exterior", exterior), ("Interior", interior))
    ):
        y0 = header_h + row_index * tile_h
        draw.text((8, y0 + tile_h // 2 - 12), label, fill="black", font=small)
        for col, path in enumerate(images):
            with Image.open(path) as source:
                tile = source.convert("RGB")
                tile.thumbnail((tile_w, tile_h), Image.Resampling.LANCZOS)
                background = Image.new("RGB", (tile_w, tile_h), (24, 24, 24))
                background.paste(
                    tile, ((tile_w - tile.width) // 2, (tile_h - tile.height) // 2)
                )
            x0 = label_w + col * tile_w
            canvas.paste(background, (x0, y0))
            draw.rectangle((x0 + 6, y0 + 5, x0 + 38, y0 + 32), fill="black")
            draw.text((x0 + 13, y0 + 6), str(col + 1), fill="white", font=small)
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92, subsampling=0)


def make_package(trial: str) -> dict[str, Any]:
    data_root, annotation_root, _ = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    protocol = load_protocol()
    indices = protocol["render"]["aqs_anchor_indices_per_side"]
    annotation_root.mkdir(parents=True, exist_ok=True)
    items: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            run = pair_dir(data_root, spec["spec_id"], seed)
            item_id = blind_id(spec["spec_id"], seed)
            success = (run / "SUCCESS").is_file()
            private.append(
                {
                    "blind_id": item_id,
                    "method": "worldgen",
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "success": success,
                    "run_dir": rel(run),
                }
            )
            if not success:
                continue
            chosen: dict[str, list[Path]] = {}
            for side in SIDES:
                anchors = sorted(
                    (
                        side_dir(data_root, spec["spec_id"], seed, side)
                        / "renders/anchors"
                    ).glob("rgb_*.png")
                )
                if len(anchors) != 8:
                    raise RuntimeError(
                        f"Expected 8 {side} anchors for {spec['spec_id']} seed={seed}"
                    )
                chosen[side] = [anchors[index] for index in indices[side]]
            montage = annotation_root / "montages" / f"{item_id}.jpg"
            make_pair_montage(chosen["exterior"], chosen["interior"], montage, item_id)
            items.append(
                {
                    "blind_id": item_id,
                    "function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "target_building": spec["target_building"],
                    "interior_program": spec["interior_program"],
                    "visual_inheritance": spec["visual_inheritance"],
                    "functional_questions": spec["functional_questions"],
                    "visual_questions": spec["visual_questions"],
                    "montage": rel(montage),
                    "montage_sha256": sha256_file(montage),
                }
            )
    atomic_json(
        annotation_root / "PRIVATE_blind_map.json",
        {
            "warning": "Do not expose this method/run mapping to a scorer.",
            "blind_salt_sha256": hashlib.sha256(BLIND_SALT.encode()).hexdigest(),
            "items": private,
        },
    )
    atomic_text(
        annotation_root / "items.jsonl",
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in items
        ),
    )
    manifest = {
        "created_at_utc": utc_now(),
        "trial": trial,
        "planned_pairs": len(private),
        "successful_pairs": len(items),
        "failed_pairs": len(private) - len(items),
        "method_blinded": True,
        "views_per_pair": {"exterior": 4, "interior": 4},
        "items_sha256": sha256_file(annotation_root / "items.jsonl"),
        "private_map_sha256": sha256_file(annotation_root / "PRIVATE_blind_map.json"),
    }
    atomic_json(annotation_root / "package_manifest.json", manifest)
    print(
        f"TABLE4_WORLDGEN_PACKAGE_COMPLETE {json.dumps(manifest, sort_keys=True)}",
        flush=True,
    )
    return manifest


def calibrate_evidence_anchors() -> dict[str, Any]:
    """Audit frozen Table 2 renders to choose informative fixed AQS anchors."""
    import numpy as np

    domains: dict[str, Any] = {}
    for domain in ("urban", "indoor"):
        root = BASELINES / "data/table2" / domain / "worldgen"
        values: dict[int, list[tuple[float, float, float]]] = {
            index: [] for index in range(8)
        }
        run_count = 0
        for run in sorted(root.glob("*/seed_*")):
            anchors = sorted((run / "renders/anchors").glob("rgb_*.png"))
            if len(anchors) != 8:
                continue
            run_count += 1
            for index, path in enumerate(anchors):
                with Image.open(path) as handle:
                    pixels = np.asarray(handle.convert("RGB"), dtype=np.float32) / 255.0
                values[index].append(
                    (
                        float(pixels.mean()),
                        float((pixels.mean(axis=2) < 0.02).mean()),
                        float(pixels.std()),
                    )
                )
        domains[domain] = {
            "audited_runs": run_count,
            "anchors": {
                str(index): {
                    "count": len(rows),
                    "median_image_mean": float(np.median(np.asarray(rows)[:, 0])),
                    "median_dark_pixel_fraction": float(
                        np.median(np.asarray(rows)[:, 1])
                    ),
                    "median_image_std": float(np.median(np.asarray(rows)[:, 2])),
                    "mean_validator_fraction": float(
                        (np.asarray(rows)[:, 0] >= 0.01).mean()
                    ),
                }
                for index, rows in values.items()
            },
        }
    result = {
        "audited_at_utc": utc_now(),
        "source": "frozen WorldGen Table 2 8-anchor renders; no Table 4 output inspected",
        "domains": domains,
        "selected_indices": {"exterior": [4, 5, 6, 7], "interior": [0, 2, 5, 7]},
        "selection_rule": (
            "Exterior uses the last four preregistered urban anchors because the frozen "
            "single-panorama camera path approaches the capture center and Table 2 anchors "
            "0-3 have substantially more black unseen-region pixels. Interior spans the "
            "full bidirectional path because all eight Table 2 anchors are informative."
        ),
        "table4_eligible_scores": False,
    }
    output = WORLDGEN_RESULTS / "table2_anchor_calibration.json"
    atomic_json(output, result)
    print(
        f"TABLE4_WORLDGEN_ANCHOR_CALIBRATION_COMPLETE output={rel(output)}", flush=True
    )
    return result


def capability_audit() -> dict[str, Any]:
    """Record the native interface evidence behind the independent-track decision."""
    source_root = BASELINES / "sources/WorldGen"
    api_path = source_root / "src/worldgen/worldgen.py"
    api_text = api_path.read_text(encoding="utf-8")
    python_files = sorted((source_root / "src/worldgen").rglob("*.py"))
    combined = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in python_files
    )
    searched_symbols = {
        symbol: combined.lower().count(symbol)
        for symbol in (
            "building_id",
            "interior_id",
            "entrance_id",
            "portal",
            "shared_world_frame",
            "common_coordinate",
        )
    }
    table2_lock = json.loads(TABLE2_LOCK_PATH.read_text(encoding="utf-8"))["worldgen"]
    result = {
        "audited_at_utc": utc_now(),
        "method": "WorldGen (ZiYang-xie)",
        "source": rel(source_root),
        "source_commit": table2_lock["commit"],
        "native_api": {
            "text_or_image_to_single_panorama_scene": (
                "generate_world accepts one prompt/image and returns one scene"
            ),
            "gaussian_splat_supported": "return_mesh: bool = False" in api_text,
            "official_triangle_mesh_supported": (
                "if return_mesh:" in api_text and "self.depth2mesh" in api_text
            ),
            "searched_cross_domain_symbols": searched_symbols,
        },
        "native_shared_world_frame": False,
        "native_building_to_interior_identity": False,
        "native_shared_portal": False,
        "track": "matched_text_independent",
        "numeric_metrics": ["functional_aqs", "visual_aqs"],
        "not_applicable": {metric: "N/A-U" for metric in NATIVE_NA_METRICS},
        "decision": (
            "The frozen public API creates one panorama-derived scene per invocation. "
            "It has no native call or metadata contract linking an exterior building to "
            "an interior, no shared transform, and no shared portal. Two matched prompts "
            "therefore remain independent outputs even though each has exportable geometry."
        ),
        "source_files_scanned": len(python_files),
        "api_sha256": sha256_file(api_path),
    }
    output = WORLDGEN_RESULTS / "capability_audit.json"
    atomic_json(output, result)
    print(f"TABLE4_WORLDGEN_CAPABILITY_AUDIT_COMPLETE output={rel(output)}", flush=True)
    return result


def preflight() -> dict[str, Any]:
    """Verify all reused local WorldGen/Qwen resources without downloading."""
    method = json.loads(TABLE2_LOCK_PATH.read_text(encoding="utf-8"))["worldgen"]
    hub = BASELINES / "checkpoints/WorldGen/huggingface/hub"
    lora = (
        hub
        / "models--LeoXie--WorldGen/snapshots"
        / method["weights"]["LeoXie/WorldGen:text2scene_lora"]["revision"]
        / "models--WorldGen-Flux-Lora/worldgen_text2scene.safetensors"
    )
    da2 = (
        hub
        / "models--haodongli--DA-2/snapshots"
        / method["weights"]["haodongli/DA-2"]["revision"]
        / "model.safetensors"
    )
    flux = (
        hub
        / "models--black-forest-labs--FLUX.1-dev/snapshots"
        / method["weights"]["black-forest-labs/FLUX.1-dev"]["revision"]
    )
    resources: dict[str, Any] = {}
    for name, path, expected_size in (
        (
            "worldgen_text2scene_lora",
            lora,
            method["weights"]["LeoXie/WorldGen:text2scene_lora"]["size_bytes"],
        ),
        ("da2", da2, method["weights"]["haodongli/DA-2"]["size_bytes"]),
    ):
        resources[name] = {
            "path": rel(path),
            "exists": path.is_file(),
            "size_bytes": path.stat().st_size if path.is_file() else None,
            "expected_size_bytes": expected_size,
            "size_matches": path.is_file() and path.stat().st_size == expected_size,
            "sha256_previously_verified": method["weights"][
                "LeoXie/WorldGen:text2scene_lora"
                if name.startswith("worldgen")
                else "haodongli/DA-2"
            ]["sha256"],
        }
    flux_core = method["weights"]["black-forest-labs/FLUX.1-dev"]["core_weights"]
    resources["flux_core"] = {
        "snapshot": rel(flux),
        "expected_files": len(flux_core),
        "present_files": sum((flux / name).is_file() for name in flux_core),
        "all_present": all((flux / name).is_file() for name in flux_core),
        "sha256_previously_verified": flux_core,
    }
    qwen_manifest = json.loads(MODEL_MANIFEST.read_text(encoding="utf-8"))
    qwen_files = [QWEN_ROOT / row["path"] for row in qwen_manifest["files"]]
    resources["qwen3_vl_8b"] = {
        "path": rel(QWEN_ROOT),
        "expected_files": qwen_manifest["file_count"],
        "present_files": sum(path.is_file() for path in qwen_files),
        "expected_total_bytes": qwen_manifest["total_bytes"],
        "present_total_bytes": sum(
            path.stat().st_size for path in qwen_files if path.is_file()
        ),
        "manifest_sha256": sha256_file(MODEL_MANIFEST),
    }
    freeze = BASELINES / "methods/worldgen/environment/worldgen-pip-freeze.txt"
    checks = {
        "source_directory": (BASELINES / "sources/WorldGen/src/worldgen").is_dir(),
        "python_environment": PYTHON.is_file(),
        "pip_freeze_matches_table2_lock": freeze.is_file()
        and sha256_file(freeze) == method["pip_freeze_sha256"],
        "table2_adapter_matches_lock": sha256_file(TABLE2_ADAPTER_PATH)
        == method["adapter_sha256"],
        "table2_renderer_matches_lock": sha256_file(TABLE2_RENDERER_PATH)
        == method["renderer_sha256"],
        "lora_size_matches": resources["worldgen_text2scene_lora"]["size_matches"],
        "da2_size_matches": resources["da2"]["size_matches"],
        "flux_core_present": resources["flux_core"]["all_present"],
        "qwen_complete": (
            resources["qwen3_vl_8b"]["present_files"] == qwen_manifest["file_count"]
            and resources["qwen3_vl_8b"]["present_total_bytes"]
            == qwen_manifest["total_bytes"]
        ),
    }
    try:
        gpu = gpu_state()
        gpu_error = None
    except Exception as exc:
        gpu, gpu_error = {}, repr(exc)
    result = {
        "checked_at_utc": utc_now(),
        "passed": all(checks.values()),
        "checks": checks,
        "resources": resources,
        "source_commit": method["commit"],
        "gpu_state": gpu,
        "gpu_query_error": gpu_error,
        "downloads_performed": False,
        "downloads_required": False,
        "reuse": [
            "WorldGen source and compatibility patch",
            "WorldGen Python environment and pip freeze",
            "FLUX.1-dev, WorldGen LoRA, and DA-2 weights",
            "Table 2 gsplat renderer",
            "local Qwen3-VL-8B-Instruct snapshot",
            "Table 2 render evidence for fixed anchor calibration",
        ],
    }
    output = WORLDGEN_RESULTS / "preflight.json"
    atomic_json(output, result)
    print(
        f"TABLE4_WORLDGEN_PREFLIGHT_COMPLETE passed={result['passed']} output={rel(output)}",
        flush=True,
    )
    return result


def aqs_prompt(item: dict[str, Any]) -> str:
    return """You are scoring one anonymous indoor-outdoor generation pair using Absolute Quantitative Scoring (AQS). The top row contains four EXTERIOR views of the designated street-facing target building and its context. The bottom row contains four INTERIOR views generated for that building specification. Score only visible evidence and the frozen specification below. Do not reward standalone image quality, and do not infer hidden content.

Functional AQS (1-10): Does the interior match the target exterior building's semantic use? Judge required functional zones/large objects, usable organization, and dominant contradictions.
Visual AQS (1-10): Does the interior inherit the target building and district's visual identity? Judge compatible style, materials, colors, period/detail language, atmosphere, and contradictions.

Shared anchors: 1-2 obvious contradiction or unjudgeable; 3-4 weak/generic correspondence with many missing requirements; 5-6 partial correspondence with visible inconsistencies; 7-8 most evidence agrees with minor problems; 9-10 explicit, complete, nearly contradiction-free correspondence (use 10 sparingly).

Return one JSON object with exactly these keys: functional_aqs, visual_aqs, functional_evidence, visual_evidence. Scores must be integers from 1 to 10. Evidence values must be concise non-empty strings describing visible support and problems.

Frozen specification:
""" + json.dumps(
        {
            "function": item["function"],
            "visual_theme": item["visual_theme"],
            "target_building": item["target_building"],
            "interior_program": item["interior_program"],
            "visual_inheritance": item["visual_inheritance"],
            "functional_questions": item["functional_questions"],
            "visual_questions": item["visual_questions"],
        },
        ensure_ascii=False,
    )


def request_json(port: int, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=600) as response:
        return json.load(response)


def parse_aqs(raw: dict[str, Any]) -> dict[str, Any]:
    content = raw["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("VLM response content is not text")
    stripped = content.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    parsed = json.loads(stripped)
    expected = {
        "functional_aqs",
        "visual_aqs",
        "functional_evidence",
        "visual_evidence",
    }
    if set(parsed) != expected:
        raise ValueError(f"Unexpected AQS keys: {sorted(parsed)}")
    for key in ("functional_aqs", "visual_aqs"):
        if type(parsed[key]) is not int or not 1 <= parsed[key] <= 10:
            raise ValueError(f"{key} must be an integer 1..10")
    for key in ("functional_evidence", "visual_evidence"):
        if not isinstance(parsed[key], str) or not parsed[key].strip():
            raise ValueError(f"{key} must be non-empty text")
    return parsed


def score_package(trial: str, port: int, request_workers: int) -> dict[str, Any]:
    _, annotation_root, _ = trial_paths(trial)
    items = [
        json.loads(line)
        for line in (annotation_root / "items.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    protocol = load_protocol()
    model_manifest_hash = sha256_file(MODEL_MANIFEST)
    seeds = protocol["aqs"]["seeds"]

    def score_one(item: dict[str, Any]) -> int:
        image_bytes = (REPO / item["montage"]).read_bytes()
        if hashlib.sha256(image_bytes).hexdigest() != item["montage_sha256"]:
            raise RuntimeError(f"Montage changed for {item['blind_id']}")
        prompt = aqs_prompt(item)
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,"
                + base64.b64encode(image_bytes).decode()
            },
        }
        for pass_index, seed in enumerate(seeds, 1):
            settings = {
                "model": protocol["aqs"]["model"],
                "temperature": protocol["aqs"]["temperature"],
                "top_p": protocol["aqs"]["top_p"],
                "seed": seed,
                "max_tokens": 1536,
                "response_format": {"type": "json_object"},
            }
            signature = hashlib.sha256(
                json.dumps(
                    {
                        "settings": settings,
                        "prompt": prompt,
                        "image_sha256": item["montage_sha256"],
                        "model_manifest_sha256": model_manifest_hash,
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            output = (
                annotation_root
                / "aqs_raw"
                / item["blind_id"]
                / f"pass_{pass_index:02d}.json"
            )
            if output.is_file():
                record = json.loads(output.read_text(encoding="utf-8"))
                if record.get("input_signature") != signature:
                    raise RuntimeError(f"Refusing changed cached AQS input: {output}")
                parse_aqs(record["raw_response"])
                continue
            last_error: Exception | None = None
            for attempt in range(1, 4):
                try:
                    payload = {
                        **settings,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    image_content,
                                ],
                            }
                        ],
                    }
                    raw = request_json(port, payload)
                    parsed = parse_aqs(raw)
                    atomic_json(
                        output,
                        {
                            "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
                            "human_raters": 0,
                            "pass_index": pass_index,
                            "seed": seed,
                            "input_signature": signature,
                            "image_sha256": item["montage_sha256"],
                            "model_manifest_sha256": model_manifest_hash,
                            "settings": settings,
                            "prompt": prompt,
                            "parsed": parsed,
                            "raw_response": raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    print(
                        f"TABLE4_WORLDGEN_AQS_RETRY item={item['blind_id']} pass={pass_index} "
                        f"attempt={attempt}/3 error={exc!r}",
                        flush=True,
                    )
            else:
                raise RuntimeError(
                    f"AQS failed for {item['blind_id']} pass={pass_index}: {last_error!r}"
                )
        print(f"TABLE4_WORLDGEN_AQS_ITEM_COMPLETE item={item['blind_id']}", flush=True)
        return 1

    if request_workers < 1:
        raise ValueError("request_workers must be positive")
    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=request_workers) as executor:
        for value in executor.map(
            score_one, sorted(items, key=lambda row: row["blind_id"])
        ):
            completed += value
    provenance = {
        "scored_at_utc": utc_now(),
        "trial": trial,
        "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
        "human_raters": 0,
        "independent_human_ratings": False,
        "model": protocol["aqs"]["model"],
        "model_manifest_sha256": model_manifest_hash,
        "passes_per_pair": len(seeds),
        "seeds": seeds,
        "scored_successful_pairs": completed,
        "visual_input": "anonymous montage with four exterior and four interior views",
        "limitations": "Local VLM proxy scores, not human ratings and not directly comparable to HoloWorld's reported GPT-5.5 values.",
    }
    atomic_json(annotation_root / "AQS_VLM_PROVENANCE.json", provenance)
    return provenance


def start_and_score(
    trial: str, gpu: int, port: int, request_workers: int, external_vllm: bool
) -> dict[str, Any]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    matrix.QWEN_ROOT = QWEN_ROOT
    # The shared ``baselines/.vtmp`` directory was created by a different UID
    # on the resumed host.  Only redirect vLLM's short Unix-socket TMPDIR;
    # model, runtime, logs, and evaluator code remain the frozen local assets.
    # Keep the absolute path below ZeroMQ's 107-byte Unix-socket limit.
    matrix.BASELINES_ROOT = BASELINES / ".w"
    process = None
    try:
        if external_vllm:
            if not matrix.llm_health(port):
                raise RuntimeError(f"No healthy local VLM at port {port}")
        else:
            state = gpu_state().get(gpu)
            if state is None or state["free_mib"] < 30000 or state["utilization"] > 10:
                raise RuntimeError(f"VLM GPU {gpu} is not idle enough: {state}")
            process, _ = matrix.start_vllm(gpu, port, 16384, 900)
        return score_package(trial, port, request_workers)
    finally:
        if process is not None:
            matrix.stop_process_group(process)


def mean(values: Iterable[float]) -> float:
    values = list(values)
    if not values:
        raise ValueError("Cannot average an empty sequence")
    return sum(values) / len(values)


def macro_average(rows: list[dict[str, Any]], metric: str) -> float:
    by_spec: dict[str, list[float]] = {}
    for row in rows:
        by_spec.setdefault(row["spec_id"], []).append(float(row[metric]))
    return mean(mean(values) for values in by_spec.values())


def cluster_bootstrap(
    rows: list[dict[str, Any]], metric: str, repeats: int, seed: int
) -> tuple[float, float]:
    import numpy as np

    by_spec: dict[str, list[float]] = {}
    for row in rows:
        by_spec.setdefault(row["spec_id"], []).append(float(row[metric]))
    values = [mean(by_spec[key]) for key in sorted(by_spec)]
    generator = random.Random(seed)
    draws = [
        mean(values[generator.randrange(len(values))] for _ in values)
        for _ in range(repeats)
    ]
    return float(np.quantile(draws, 0.025)), float(np.quantile(draws, 0.975))


def aggregate(trial: str) -> dict[str, Any]:
    data_root, annotation_root, results_root = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    protocol = load_protocol()
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            run = pair_dir(data_root, spec["spec_id"], seed)
            success = (run / "SUCCESS").is_file()
            item_id = blind_id(spec["spec_id"], seed)
            if success:
                parsed = []
                for pass_index in range(1, protocol["aqs"]["passes"] + 1):
                    path = (
                        annotation_root
                        / "aqs_raw"
                        / item_id
                        / f"pass_{pass_index:02d}.json"
                    )
                    if not path.is_file():
                        raise RuntimeError(f"Missing AQS score: {path}")
                    record = json.loads(path.read_text(encoding="utf-8"))
                    parsed.append(parse_aqs(record["raw_response"]))
                functional = mean(row["functional_aqs"] for row in parsed)
                visual = mean(row["visual_aqs"] for row in parsed)
                failure_reason = None
            else:
                functional = float(protocol["aqs"]["failure_value"])
                visual = float(protocol["aqs"]["failure_value"])
                manifest = json.loads(
                    (run / "manifest.json").read_text(encoding="utf-8")
                )
                failure_reason = "pair_generation_or_render_failure"
                failures.append(
                    {
                        "spec_id": spec["spec_id"],
                        "logical_seed": seed,
                        "reason": failure_reason,
                        "native_status": json.dumps(
                            manifest["native_status"], sort_keys=True
                        ),
                    }
                )
            rows.append(
                {
                    "method": "worldgen",
                    "display_name": "WorldGen (ZiYang-xie)",
                    "track": "matched_text_independent",
                    "spec_id": spec["spec_id"],
                    "spec_index": spec["spec_index"],
                    "function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "logical_seed": seed,
                    "pair_success": success,
                    "functional_aqs": functional,
                    "visual_aqs": visual,
                    **{metric: "N/A-U" for metric in NATIVE_NA_METRICS},
                    "failure_reason": failure_reason,
                    "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass"
                    if success
                    else "itt_failure_value",
                    "human_raters": 0,
                }
            )
    repeats = int(protocol["aggregation"]["bootstrap_repeats"])
    bootstrap_seed = int(protocol["aggregation"]["bootstrap_seed"])
    metrics: dict[str, Any] = {}
    for metric in ("functional_aqs", "visual_aqs"):
        metrics[metric] = {
            "mean": macro_average(rows, metric),
            "ci95": list(cluster_bootstrap(rows, metric, repeats, bootstrap_seed)),
            "coverage": 1.0,
        }
    summary = {
        "aggregated_at_utc": utc_now(),
        "trial": trial,
        "method": "worldgen",
        "display_name": "WorldGen (ZiYang-xie)",
        "track": "matched_text_independent",
        "planned_pairs": len(rows),
        "successful_pairs": sum(row["pair_success"] for row in rows),
        "success_rate": mean(1.0 if row["pair_success"] else 0.0 for row in rows),
        "aggregation_order": protocol["aggregation"]["order"],
        "bootstrap_repeats": repeats,
        "bootstrap_seed": bootstrap_seed,
        "metrics": metrics,
        "not_applicable": {metric: "N/A-U" for metric in NATIVE_NA_METRICS},
        "aqs_source": "local Qwen3-VL-8B-Instruct, three seeded VLM passes; human_raters=0",
        "comparability_note": "Not directly comparable to HoloWorld's reported GPT-5.5 values because the evaluator and sample set differ.",
    }
    results_root.mkdir(parents=True, exist_ok=True)
    atomic_text(
        results_root / "per_run.jsonl",
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
    )
    atomic_json(results_root / "summary.json", summary)
    with (results_root / "summary.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fields = [
            "method",
            "track",
            "functional_aqs",
            "visual_aqs",
            *NATIVE_NA_METRICS,
            "planned_pairs",
            "successful_pairs",
            "success_rate",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerow(
            {
                "method": "WorldGen (ZiYang-xie)",
                "track": "matched_text_independent",
                "functional_aqs": f"{metrics['functional_aqs']['mean']:.2f}",
                "visual_aqs": f"{metrics['visual_aqs']['mean']:.2f}",
                **{metric: "N/A-U" for metric in NATIVE_NA_METRICS},
                "planned_pairs": len(rows),
                "successful_pairs": summary["successful_pairs"],
                "success_rate": f"{summary['success_rate']:.6f}",
            }
        )
    with (results_root / "failures.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fields = ["spec_id", "logical_seed", "reason", "native_status"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(failures)
    print(
        f"TABLE4_WORLDGEN_AGGREGATE_COMPLETE {json.dumps(summary, sort_keys=True)}",
        flush=True,
    )
    return summary


def freeze_after_pilot() -> dict[str, Any]:
    _, _, pilot_results = trial_paths("pilot")
    audit_path = pilot_results / "audit.json"
    summary_path = pilot_results / "summary.json"
    if not audit_path.is_file() or not json.loads(
        audit_path.read_text(encoding="utf-8")
    ).get("passed"):
        raise RuntimeError("A passing pilot audit is required before freezing")
    if not summary_path.is_file():
        raise RuntimeError("Pilot AQS aggregation is required before freezing")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if summary.get("planned_pairs") != 10:
        raise RuntimeError("Pilot must contain exactly 10 planned pairs")
    protocol = load_protocol()
    protocol["status"] = "formal_frozen"
    protocol["frozen_after_pilot_at_utc"] = utc_now()
    atomic_json(PROTOCOL_PATH, protocol)
    table2_lock = json.loads(TABLE2_LOCK_PATH.read_text(encoding="utf-8"))["worldgen"]
    lock = {
        "method": "worldgen",
        "display_name": "WorldGen (ZiYang-xie)",
        "track": "matched_text_independent",
        "source_commit": table2_lock["commit"],
        "submodules": table2_lock["submodules"],
        "weights": table2_lock["weights"],
        "python_environment": table2_lock["python_environment"],
        "pip_freeze_sha256": table2_lock["pip_freeze_sha256"],
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "spec_sha256": sha256_file(SPEC_PATH),
        "runner_sha256": sha256_file(Path(__file__)),
        "table2_adapter_sha256": sha256_file(TABLE2_ADAPTER_PATH),
        "table2_renderer_sha256": sha256_file(TABLE2_RENDERER_PATH),
        "qwen_model_manifest_sha256": sha256_file(MODEL_MANIFEST),
        "capability_audit_sha256": sha256_file(
            WORLDGEN_RESULTS / "capability_audit.json"
        ),
        "table2_anchor_calibration_sha256": sha256_file(
            WORLDGEN_RESULTS / "table2_anchor_calibration.json"
        ),
        "preflight_sha256": sha256_file(WORLDGEN_RESULTS / "preflight.json"),
        "qwen_model_total_bytes": json.loads(
            MODEL_MANIFEST.read_text(encoding="utf-8")
        )["total_bytes"],
        "input_track": "matched_text_independent",
        "output_representation": "gaussian_splat+official_triangle_mesh",
        "shared_world_frame": False,
        "door_open_state_supported": False,
        "geometry_and_navigation_metrics": "N/A-U",
        "pilot_summary_sha256": sha256_file(summary_path),
        "pilot_audit_sha256": sha256_file(audit_path),
        "frozen_at_utc": utc_now(),
    }
    atomic_json(LOCK_PATH, lock)
    verify_formal_lock()
    print(f"TABLE4_WORLDGEN_FREEZE_COMPLETE lock={rel(LOCK_PATH)}", flush=True)
    return lock


def audit(trial: str) -> dict[str, Any]:
    data_root, annotation_root, results_root = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    issues: list[str] = []
    rows: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            run = pair_dir(data_root, spec["spec_id"], seed)
            manifest_path = run / "manifest.json"
            if not manifest_path.is_file():
                issues.append(f"missing manifest: {rel(run)}")
                continue
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            success = (run / "SUCCESS").is_file()
            for side in SIDES:
                native = side_dir(data_root, spec["spec_id"], seed, side)
                for name in ("run_manifest.json", "input/native_input.json"):
                    if not (native / name).is_file():
                        issues.append(f"missing {name}: {rel(native)}")
                if manifest["native_status"][side]["generation_success"]:
                    for name in (
                        "scene/panorama.png",
                        "scene/splat.ply",
                        "scene/mesh.ply",
                        "GENERATION_SUCCESS",
                    ):
                        if not (native / name).is_file():
                            issues.append(
                                f"generation marker drift {name}: {rel(native)}"
                            )
                if manifest["native_status"][side]["render_success"]:
                    if len(list((native / "renders/anchors").glob("rgb_*.png"))) != 8:
                        issues.append(f"anchor count drift: {rel(native)}")
                    if len(list((native / "renders/sequence").glob("rgb_*.png"))) != 50:
                        issues.append(f"sequence count drift: {rel(native)}")
                    if not (native / "renders/table4_validation.json").is_file():
                        issues.append(f"missing Table 4 side validation: {rel(native)}")
            if success != all(
                manifest["native_status"][side]["render_success"] for side in SIDES
            ):
                issues.append(f"pair success marker drift: {rel(run)}")
            rows.append({"spec_id": spec["spec_id"], "seed": seed, "success": success})
    expected = load_protocol()[trial]["planned_pairs"]
    if len(rows) != expected:
        issues.append(f"planned row count {len(rows)} != {expected}")
    package_manifest = annotation_root / "package_manifest.json"
    if package_manifest.is_file():
        package = json.loads(package_manifest.read_text(encoding="utf-8"))
        if package["planned_pairs"] != expected:
            issues.append("annotation package planned count drift")
    summary_path = results_root / "summary.json"
    if summary_path.is_file():
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if summary["planned_pairs"] != expected:
            issues.append("summary planned count drift")
        if summary["successful_pairs"] != sum(row["success"] for row in rows):
            issues.append("summary success count drift")
    elif trial == "pilot":
        issues.append("pilot summary is required before freeze")
    result = {
        "audited_at_utc": utc_now(),
        "trial": trial,
        "passed": not issues,
        "issues": issues,
        "counts": {
            "planned_pairs": expected,
            "manifest_pairs": len(rows),
            "successful_pairs": sum(row["success"] for row in rows),
            "failed_pairs": sum(not row["success"] for row in rows),
        },
        "capability_decision": {
            "track": "matched_text_independent",
            "numeric_metrics": ["functional_aqs", "visual_aqs"],
            "N/A-U_metrics": list(NATIVE_NA_METRICS),
        },
    }
    atomic_json(results_root / "audit.json", result)
    print(
        f"TABLE4_WORLDGEN_AUDIT_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    sub.add_parser("calibrate-evidence")
    sub.add_parser("capability-audit")
    sub.add_parser("preflight")
    compile_parser = sub.add_parser("compile")
    compile_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    run_parser = sub.add_parser("run")
    run_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    run_parser.add_argument(
        "--phase",
        choices=("compile", "panorama", "reconstruct", "render"),
        required=True,
    )
    run_parser.add_argument("--gpus", type=int, nargs="+", default=[0])
    run_parser.add_argument("--workers", type=int, default=1)
    run_parser.add_argument("--force", action="store_true")
    wait_parser = sub.add_parser("wait-run")
    wait_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    wait_parser.add_argument(
        "--phase", choices=("panorama", "reconstruct", "render"), required=True
    )
    wait_parser.add_argument(
        "--candidate-gpus", type=int, nargs="+", default=[0, 1, 2, 3, 4, 5]
    )
    wait_parser.add_argument("--workers", type=int, default=1)
    wait_parser.add_argument("--poll-seconds", type=int, default=30)
    wait_parser.add_argument("--stable-samples", type=int, default=3)
    wait_parser.add_argument("--timeout-seconds", type=int, default=86400)
    wait_parser.add_argument("--force", action="store_true")
    worker_parser = sub.add_parser("worker")
    worker_parser.add_argument(
        "--phase", choices=("panorama", "reconstruct", "render"), required=True
    )
    worker_parser.add_argument("--task-list", type=Path, required=True)
    worker_parser.add_argument("--data-root", type=Path, required=True)
    worker_parser.add_argument("--force", action="store_true")
    package_parser = sub.add_parser("package")
    package_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score_parser = sub.add_parser("score")
    score_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score_parser.add_argument("--gpu", type=int, default=0)
    score_parser.add_argument("--port", type=int, default=18084)
    score_parser.add_argument("--request-workers", type=int, default=4)
    score_parser.add_argument("--external-vllm", action="store_true")
    aggregate_parser = sub.add_parser("aggregate")
    aggregate_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    audit_parser = sub.add_parser("audit")
    audit_parser.add_argument("--trial", choices=("pilot", "formal"), required=True)
    sub.add_parser("freeze")
    args = parser.parse_args()
    if args.command == "validate":
        result = validate_specs()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["passed"] else 2
    if args.command == "calibrate-evidence":
        calibrate_evidence_anchors()
        return 0
    if args.command == "capability-audit":
        capability_audit()
        return 0
    if args.command == "preflight":
        result = preflight()
        return 0 if result["passed"] else 2
    if args.command == "compile":
        compile_trial(args.trial)
        return 0
    if args.command == "run":
        return run_phase(args.trial, args.phase, args.gpus, args.workers, args.force)
    if args.command == "wait-run":
        return wait_and_run_phase(
            args.trial,
            args.phase,
            args.candidate_gpus,
            args.workers,
            args.force,
            args.poll_seconds,
            args.stable_samples,
            args.timeout_seconds,
        )
    if args.command == "worker":
        return worker(args.phase, args.task_list, args.data_root, args.force)
    if args.command == "package":
        make_package(args.trial)
        return 0
    if args.command == "score":
        start_and_score(
            args.trial, args.gpu, args.port, args.request_workers, args.external_vllm
        )
        return 0
    if args.command == "aggregate":
        aggregate(args.trial)
        return 0
    if args.command == "audit":
        result = audit(args.trial)
        return 0 if result["passed"] else 2
    if args.command == "freeze":
        freeze_after_pilot()
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

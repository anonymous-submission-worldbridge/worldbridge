#!/usr/bin/env python3
"""Build a provenance-safe, high-quality HY-World 2.0 paired demo package.

HY-World 2.0 produces independent indoor and urban 3D Gaussian scenes.  This
builder deliberately preserves that limitation: every demo contains two real
native HY-World scenes, but never claims a shared coordinate frame or a portal
between them.
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
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageFilter


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
SOURCE_ROOT = BASELINES / "sources/HY-World-2.0"
DATA_ROOT = BASELINES / "hyworld2_runtime/data/table2"
WORK_ROOT = BASELINES / "work/hyworld2_connect2_native"
CANDIDATE = WORK_ROOT / "candidate"
PYTHON = BASELINES / "envs/hyworld2/bin/python"
RENDER_HELPERS = BASELINES / "methods/hyworld/tools/render_hyworld_generation.py"
METHOD_COMMIT = "df9988efb87bfc0f4947eb3889411cf957478b06"
TRAIN_STEPS = 2000
PLY_STEP = 1999


PAIRS: tuple[dict[str, Any], ...] = (
    {
        "name": "scene_01_ornate_living_and_dense_commercial",
        "indoor": ("indoor_living_room_04", 1),
        "outdoor": ("urban_commercial_irregular_09", 0),
    },
    {
        "name": "scene_02_dining_salon_and_brick_crossroads",
        "indoor": ("indoor_dining_room_03", 0),
        "outdoor": ("urban_commercial_four_way_05", 0),
    },
    {
        "name": "scene_03_balcony_living_and_open_cafe_street",
        "indoor": ("indoor_living_room_03", 1),
        "outdoor": ("urban_mixed_use_main_side_12", 0),
    },
    {
        "name": "scene_04_island_kitchen_and_small_town_main_street",
        "indoor": ("indoor_kitchen_02", 0),
        "outdoor": ("urban_commercial_main_side_07", 1),
    },
    {
        "name": "scene_05_compact_kitchen_and_mixed_use_crossroads",
        "indoor": ("indoor_kitchen_04", 0),
        "outdoor": ("urban_mixed_use_four_way_10", 2),
    },
    {
        "name": "scene_06_window_dining_and_commercial_t_junction",
        "indoor": ("indoor_dining_room_02", 3),
        "outdoor": ("urban_commercial_t_junction_06", 0),
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def source_run(domain: str, spec_id: str, seed: int) -> Path:
    return DATA_ROOT / domain / "hyworld2" / spec_id / f"seed_{seed}"


def selected_sides() -> list[tuple[str, str, str, int]]:
    rows: list[tuple[str, str, str, int]] = []
    for pair in PAIRS:
        for side, domain in (("indoor", "indoor"), ("outdoor", "urban")):
            spec_id, seed = pair[side]
            rows.append((pair["name"], side, spec_id, seed))
    return rows


def target_side(pair_name: str, side: str) -> Path:
    return CANDIDATE / pair_name / side


def training_complete(model_dir: Path) -> bool:
    return (
        (model_dir / f"ply/point_cloud_{PLY_STEP}.ply").is_file()
        and (model_dir / f"ckpts/ckpt_{PLY_STEP}_rank0.pt").is_file()
        and (model_dir / "ply/position_meta_info.json").is_file()
    )


def prepare_training_command(run: Path, model_dir: Path) -> list[str]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    command = matrix.HY.gs_train_command(run)
    command[command.index("--data_dir") + 1] = str(run / "scene/native/gs_data")
    command[command.index("--result_dir") + 1] = str(model_dir)
    command[command.index("--max_steps") + 1] = str(TRAIN_STEPS)
    command[command.index("--save_steps") + 1] = str(TRAIN_STEPS)
    command[command.index("--eval_steps") + 1] = "999999"
    command[command.index("--ply_steps") + 1] = str(TRAIN_STEPS)
    for flag, value in (
        ("--strategy.refine-start-iter", "200"),
        ("--strategy.refine-stop-iter", "1000"),
        ("--strategy.refine-every", "133"),
        ("--strategy.refine-scale2d-stop-iter", "1000"),
    ):
        command[command.index(flag) + 1] = value
    if "--disable-viewer" not in command:
        command.append("--disable-viewer")
    for flag in ("--convert_to_spz",):
        if flag in command:
            index = command.index(flag)
            del command[index : index + (2 if flag == "--eval_steps" else 1)]
    for flag in (
        "--use_mask_gaussian",
        "--mask_export_stochastic",
        "--no-mask-export-anchor-protection",
        "--export_mesh",
    ):
        if flag in command:
            command.remove(flag)
    command.extend(["--lpips_lambda1", "0", "--lpips_lambda2", "0"])
    return command


def runtime_environment(gpu: int) -> dict[str, str]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    environment = matrix.runtime_environment([gpu], "gs_training")
    runtime_cache = Path(
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime/cache")
    )
    runtime_tmp = Path(
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_local_uid2002/runtime/tmp")
    )
    runtime_cache.mkdir(parents=True, exist_ok=True)
    runtime_tmp.mkdir(parents=True, exist_ok=True)
    environment["TORCH_EXTENSIONS_DIR"] = str(
        BASELINES / "hyworld2_runtime/cache/torch_extensions"
    )
    for key, relative in {
        "TORCH_HOME": "torch",
        "TORCHINDUCTOR_CACHE_DIR": "torchinductor",
        "TRITON_CACHE_DIR": "triton",
        "CUDA_CACHE_PATH": "cuda",
        "XDG_CACHE_HOME": "xdg",
        "PYTHONPYCACHEPREFIX": "pycache",
        "MPLCONFIGDIR": "matplotlib",
    }.items():
        path = runtime_cache / relative
        path.mkdir(parents=True, exist_ok=True)
        environment[key] = str(path)
    environment["TMPDIR"] = str(runtime_tmp)
    local_lib = _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_python_uid2002/lib")
    inherited = environment.get("LD_LIBRARY_PATH", "")
    environment["LD_LIBRARY_PATH"] = (
        f"{local_lib}:{inherited}" if inherited else local_lib
    )
    environment["PYTHONUNBUFFERED"] = "1"
    environment["HF_HUB_OFFLINE"] = "1"
    environment["TRANSFORMERS_OFFLINE"] = "1"
    return environment


def check_sources() -> None:
    failures = []
    for pair_name, side, spec_id, seed in selected_sides():
        domain = "indoor" if side == "indoor" else "urban"
        run = source_run(domain, spec_id, seed)
        required = (
            run / "input/native_input.json",
            run / "run_manifest.json",
            run / "scene/native/panorama.png",
            run / "scene/native/gs_data/images",
            run / "scene/native/render_results",
        )
        missing = [str(path) for path in required if not path.exists()]
        if missing:
            failures.append({"pair": pair_name, "side": side, "missing": missing})
    if failures:
        raise FileNotFoundError(json.dumps(failures, indent=2))


def train_all(gpu: int) -> None:
    check_sources()
    CANDIDATE.mkdir(parents=True, exist_ok=True)
    environment = runtime_environment(gpu)
    for index, (pair_name, side, spec_id, seed) in enumerate(selected_sides(), start=1):
        domain = "indoor" if side == "indoor" else "urban"
        run = source_run(domain, spec_id, seed)
        side_dir = target_side(pair_name, side)
        model_dir = side_dir / "model"
        if training_complete(model_dir):
            print(f"TRAIN_SKIP {index}/12 {pair_name}/{side}", flush=True)
            continue
        if model_dir.exists():
            shutil.rmtree(model_dir)
        model_dir.mkdir(parents=True)
        log_path = side_dir / "training.log"
        command = prepare_training_command(run, model_dir)
        print(
            f"TRAIN_START {index}/12 gpu={gpu} {pair_name}/{side} "
            f"source={spec_id}/seed_{seed}",
            flush=True,
        )
        started = time.monotonic()
        with log_path.open("w", encoding="utf-8") as log:
            log.write(
                json.dumps({"command": command, "started_at_utc": utc_now()}) + "\n"
            )
            log.flush()
            result = subprocess.run(
                command,
                cwd=SOURCE_ROOT / "hyworld2/worldgen",
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        if result.returncode != 0 or not training_complete(model_dir):
            raise RuntimeError(
                f"Training failed for {pair_name}/{side}; see {log_path}"
            )
        print(
            f"TRAIN_DONE {index}/12 {pair_name}/{side} wall_s={time.monotonic() - started:.1f}",
            flush=True,
        )


def load_helpers():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "hyworld2_render_helpers", RENDER_HELPERS
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {RENDER_HELPERS}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def intrinsic(width: int, height: int, horizontal_fov_degrees: float) -> np.ndarray:
    focal = width / (2.0 * math.tan(math.radians(horizontal_fov_degrees) / 2.0))
    return np.asarray(
        [[focal, 0.0, width / 2.0], [0.0, focal, height / 2.0], [0.0, 0.0, 1.0]],
        dtype=np.float32,
    )


def brighten(image: np.ndarray) -> np.ndarray:
    values = image.astype(np.float32) / 255.0
    luminance = (
        0.2126 * values[..., 0] + 0.7152 * values[..., 1] + 0.0722 * values[..., 2]
    )
    mean_luminance = float(luminance.mean())
    gain = float(np.clip(0.60 / max(mean_luminance, 1e-3), 1.0, 1.35))
    values = np.clip(values * gain, 0.0, 1.0)
    values = np.power(values, 0.90)
    return np.clip(values * 255.0 + 0.5, 0, 255).astype(np.uint8)


def save_render(image: np.ndarray, output: Path) -> None:
    """Apply a deliberately mild display-space sharpening and save quickly."""
    rendered = Image.fromarray(image).filter(
        ImageFilter.UnsharpMask(radius=1.1, percent=35, threshold=3)
    )
    rendered.save(output, compress_level=3)


def render_one(
    arrays: dict[str, Any],
    c2w: np.ndarray,
    width: int,
    height: int,
    fov: float,
) -> np.ndarray:
    import torch
    from gsplat.rendering import rasterization

    c2w_tensor = torch.from_numpy(c2w).to(device="cuda", dtype=torch.float32)
    k_tensor = torch.from_numpy(intrinsic(width, height, fov)).to(
        device="cuda", dtype=torch.float32
    )
    # HY-World's patched gsplat uses packed projection by default, for which
    # the background has shape [channels] rather than [camera, channels].
    background = torch.tensor([0.82, 0.84, 0.87], device="cuda", dtype=torch.float32)
    with torch.inference_mode():
        rendered, _, _ = rasterization(
            means=arrays["means"],
            quats=arrays["quats"],
            scales=arrays["scales"],
            opacities=arrays["opacities"],
            colors=arrays["colors"],
            viewmats=torch.linalg.inv(c2w_tensor)[None],
            Ks=k_tensor[None],
            width=width,
            height=height,
            sh_degree=arrays["sh_degree"],
            render_mode="RGB",
            near_plane=0.01,
            far_plane=1000.0,
            radius_clip=0.0,
            backgrounds=background,
        )
    image = rendered[0, ..., :3].clamp(0.0, 1.0).mul(255).byte().cpu().numpy()
    return brighten(image)


def compatible_model_files(model_dir: Path) -> tuple[int, Path, Path]:
    candidates = []
    for ply in (model_dir / "ply").glob("point_cloud_*.ply"):
        match = re.fullmatch(r"point_cloud_(\d+)\.ply", ply.name)
        if not match:
            continue
        step = int(match.group(1))
        checkpoints = sorted((model_dir / "ckpts").glob(f"ckpt_{step}_rank*.pt"))
        if checkpoints:
            checkpoint = next(
                (path for path in checkpoints if path.name.endswith("rank0.pt")),
                checkpoints[0],
            )
            candidates.append((step, ply, checkpoint))
    if not candidates:
        raise FileNotFoundError(f"No compatible PLY/checkpoint pair in {model_dir}")
    return max(candidates, key=lambda row: row[0])


def load_training_camera_bank(
    run: Path, transform: np.ndarray, helpers: Any
) -> tuple[list[dict[str, Any]], np.ndarray]:
    """Select level, fully observed cameras from the actual GS training set.

    HY-World's navigation proposals can intersect generated geometry.  The
    panorama training cameras are collision-free by construction and use a
    native 120-degree horizontal field of view, which is also substantially
    farther-looking than the earlier 72--100 degree delivery.
    """
    gs_data = run / "scene/native/gs_data"
    payload = json.loads((gs_data / "cameras.json").read_text(encoding="utf-8"))
    bank: list[dict[str, Any]] = []
    for name, camera in payload.items():
        image_path = gs_data / "images" / f"{name}.png"
        if not name.startswith("panorama_") or not image_path.is_file():
            continue
        w2c = np.asarray(camera.get("extrinsic"), dtype=np.float64)
        k = np.asarray(camera.get("intrinsic"), dtype=np.float64)
        if w2c.shape != (4, 4) or k.shape != (3, 3):
            continue
        c2w = np.linalg.inv(w2c)
        # OpenCV camera: +z points forward and +y points down.  Retain the
        # horizontal ring only, avoiding tilted ceiling/floor compositions.
        forward_z = float(c2w[2, 2])
        down_z = float(c2w[2, 1])
        if abs(forward_z) > 0.05 or down_z > -0.98:
            continue
        with Image.open(image_path) as source_image:
            source_width, source_height = source_image.size
        horizontal_fov = math.degrees(
            2.0 * math.atan(source_width / (2.0 * float(k[0, 0])))
        )
        yaw = math.atan2(float(c2w[1, 2]), float(c2w[0, 2]))
        bank.append(
            {
                "name": name,
                "native_c2w": c2w,
                "yaw": yaw,
                "source_image": image_path,
                "source_resolution": [source_width, source_height],
                "source_horizontal_fov_degrees": horizontal_fov,
            }
        )
    bank.sort(key=lambda row: row["yaw"])
    if len(bank) < 8:
        raise ValueError(
            f"Need at least 8 level panorama training cameras in {gs_data}"
        )
    # The native icosphere has nine level views at 40-degree intervals.  Keep
    # eight evenly distributed headings and reserve a small overlap at closure.
    chosen_indices = np.linspace(0, len(bank) - 1, 8).round().astype(int)
    selected = [bank[int(index)] for index in chosen_indices]
    transformed = helpers.transform_cameras(
        transform, np.stack([row["native_c2w"] for row in selected])
    )
    for row, camera in zip(selected, transformed):
        row["c2w"] = camera

    # Build a closed, collision-free 360-degree panoramic video at the same
    # observed camera centre.  Every segment lies between training headings.
    loop = np.concatenate([transformed, transformed[:1]], axis=0)
    video_cameras = helpers.resample_cameras(loop, 120)
    return selected, video_cameras


def load_render_state(run: Path, model_dir: Path):
    import torch

    helpers = load_helpers()
    step, ply, checkpoint = compatible_model_files(model_dir)
    try:
        checkpoint_payload = torch.load(
            checkpoint, map_location="cpu", weights_only=False, mmap=True
        )
    except TypeError:
        checkpoint_payload = torch.load(
            checkpoint, map_location="cpu", weights_only=False
        )
    transform = checkpoint_payload.get("transform")
    if hasattr(transform, "detach"):
        transform = transform.detach().cpu().numpy()
    transform = np.asarray(transform, dtype=np.float64)
    if transform.shape != (4, 4) or not np.isfinite(transform).all():
        raise ValueError(f"Invalid training similarity transform in {checkpoint}")
    training_cameras, video_cameras = load_training_camera_bank(run, transform, helpers)
    splat_np = helpers.load_splat(ply)
    arrays = {
        name: torch.from_numpy(value).to(device="cuda", dtype=torch.float32)
        for name, value in splat_np.items()
        if isinstance(value, np.ndarray)
    }
    arrays["sh_degree"] = splat_np["sh_degree"]
    return (
        helpers,
        step,
        ply,
        checkpoint,
        training_cameras,
        transform,
        video_cameras,
        arrays,
    )


def ensure_alias(source: Path, alias: Path) -> None:
    if alias.exists():
        return
    try:
        os.link(source, alias)
    except OSError:
        shutil.copy2(source, alias)


def render_side(pair_name: str, side: str, gpu: int) -> None:
    import torch

    row = next(pair for pair in PAIRS if pair["name"] == pair_name)
    spec_id, seed = row[side]
    domain = "indoor" if side == "indoor" else "urban"
    run = source_run(domain, spec_id, seed)
    side_dir = target_side(pair_name, side)
    model_dir = side_dir / "model"
    if not training_complete(model_dir):
        raise FileNotFoundError(f"Training is incomplete: {model_dir}")
    print(f"RENDER_LOAD gpu={gpu} {pair_name}/{side}", flush=True)
    (
        helpers,
        step,
        ply,
        checkpoint,
        training_cameras,
        transform,
        video_cameras,
        arrays,
    ) = load_render_state(run, model_dir)

    images_root = side_dir / "images"
    if images_root.exists():
        shutil.rmtree(images_root)
    view_names = (
        "alpha",
        "bravo",
        "charlie",
        "delta",
        "echo",
        "foxtrot",
        "golf",
        "hotel",
    )
    view_profiles = (("wide", 100.0), ("far", 112.0), ("native_ultrawide", 120.0))
    image_records = []
    for profile, fov in view_profiles:
        output_dir = images_root / profile
        output_dir.mkdir(parents=True, exist_ok=True)
        for view_name, camera_info in zip(view_names, training_cameras):
            output = output_dir / f"{view_name}.png"
            image = render_one(arrays, camera_info["c2w"], 1600, 900, fov)
            save_render(image, output)
            image_records.append(
                {
                    "path": str(output.relative_to(side_dir)),
                    "source_training_camera": camera_info["name"],
                    "source_horizontal_fov_degrees": camera_info[
                        "source_horizontal_fov_degrees"
                    ],
                    "horizontal_fov_degrees": fov,
                    "distance_profile": profile,
                    "sha256": sha256_file(output),
                }
            )

    video_dir = side_dir / "video"
    video_dir.mkdir(parents=True, exist_ok=True)
    video = video_dir / "walkthrough.mp4"
    with tempfile.TemporaryDirectory(
        prefix=f"hyworld2_{side}_", dir="/tmp"
    ) as temporary:
        frames = Path(temporary)
        for index, camera in enumerate(video_cameras):
            image = render_one(arrays, camera, 960, 540, 116.0)
            save_render(image, frames / f"frame_{index:04d}.png")
        subprocess.run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-framerate",
                "15",
                "-i",
                str(frames / "frame_%04d.png"),
                "-c:v",
                "libx264",
                "-preset",
                "slow",
                "-crf",
                "18",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(video),
            ],
            check=True,
        )

    panorama = side_dir / "source_panorama.png"
    shutil.copy2(run / "scene/native/panorama.png", panorama)
    native_input = json.loads(
        (run / "input/native_input.json").read_text(encoding="utf-8")
    )
    source_manifest = json.loads(
        (run / "run_manifest.json").read_text(encoding="utf-8")
    )
    scene_ply = model_dir / "scene.ply"
    training_checkpoint = model_dir / "training_checkpoint.pt"
    ensure_alias(ply, scene_ply)
    ensure_alias(checkpoint, training_checkpoint)
    camera_positions = video_cameras[:, :3, 3]
    path_length = float(np.linalg.norm(np.diff(camera_positions, axis=0), axis=1).sum())
    displacement = float(np.linalg.norm(camera_positions[-1] - camera_positions[0]))
    manifest = {
        "schema_version": "hyworld2-connect2-native-v2",
        "created_at_utc": utc_now(),
        "method": "HY-World 2.0",
        "method_commit": METHOD_COMMIT,
        "domain": domain,
        "side": side,
        "spec_id": spec_id,
        "logical_seed": seed,
        "method_seed": native_input.get("method_seed"),
        "prompt": native_input.get("prompt_en", native_input.get("prompt")),
        "source_run": str(run.relative_to(REPO_ROOT)),
        "source_generation_success": source_manifest.get("generation_success"),
        "representation": "3D Gaussian Splatting",
        "training_steps_requested": TRAIN_STEPS,
        "training_final_step": step,
        "gaussian_count": int(len(arrays["means"])),
        "native_shared_world_frame": False,
        "native_unified_indoor_outdoor": False,
        "portal_connectivity_claimed": False,
        "model": {
            "ply": str(scene_ply.relative_to(side_dir)),
            "ply_sha256": sha256_file(scene_ply),
            "checkpoint": str(training_checkpoint.relative_to(side_dir)),
            "checkpoint_sha256": sha256_file(training_checkpoint),
            "position_meta": "model/ply/position_meta_info.json",
        },
        "source_evidence": {
            "panorama": str(panorama.relative_to(side_dir)),
            "panorama_sha256": sha256_file(panorama),
        },
        "rendering": {
            "renderer": "gsplat 1.5.3",
            "resolution_images": [1600, 900],
            "image_count": len(image_records),
            "images": image_records,
            "video": str(video.relative_to(side_dir)),
            "video_sha256": sha256_file(video),
            "video_resolution": [960, 540],
            "video_frames": len(video_cameras),
            "video_fps": 15,
            "video_horizontal_fov_degrees": 116.0,
            "brightness_policy": "adaptive gain <=1.35 followed by gamma 0.90",
            "display_sharpening": "Pillow UnsharpMask radius=1.1 percent=35 threshold=3",
            "background_rgb_linear": [0.82, 0.84, 0.87],
            "camera_policy": "gs_data_training_horizontal_v1",
            "trajectory_source": "gs_data/cameras.json",
            "trajectory_type": "closed panoramic sweep between level training cameras",
            "selected_training_cameras": [row["name"] for row in training_cameras],
            "trajectory_path_length_normalized": path_length,
            "trajectory_displacement_normalized": displacement,
            "training_similarity_transform": transform.tolist(),
        },
    }
    atomic_json(side_dir / "manifest.json", manifest)
    del arrays
    torch.cuda.empty_cache()
    print(
        f"RENDER_DONE {pair_name}/{side} gaussians={manifest['gaussian_count']} "
        f"images={len(image_records)}",
        flush=True,
    )


def render_all(gpu: int) -> None:
    environment = runtime_environment(gpu)
    for index, (pair_name, side, _, _) in enumerate(selected_sides(), start=1):
        manifest = target_side(pair_name, side) / "manifest.json"
        if manifest.is_file():
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            images = list((target_side(pair_name, side) / "images").rglob("*.png"))
            video = target_side(pair_name, side) / "video/walkthrough.mp4"
            if (
                payload.get("rendering", {}).get("camera_policy")
                == "gs_data_training_horizontal_v1"
                and payload.get("rendering", {}).get("image_count") == 24
                and len(images) == 24
                and video.is_file()
            ):
                print(f"RENDER_SKIP {index}/12 {pair_name}/{side}", flush=True)
                continue
        print(f"RENDER_START {index}/12 {pair_name}/{side}", flush=True)
        result = subprocess.run(
            [
                str(PYTHON),
                str(Path(__file__).resolve()),
                "render-one",
                "--pair",
                pair_name,
                "--side",
                side,
                "--gpu",
                str(gpu),
            ],
            cwd=REPO_ROOT,
            env=environment,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Render failed for {pair_name}/{side}")


def read_gaussian_vertex_count(path: Path) -> int:
    from plyfile import PlyData

    return int(PlyData.read(str(path))["vertex"].count)


def probe_video(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)["streams"][0]


def package() -> None:
    scene_records = []
    for pair in PAIRS:
        pair_dir = CANDIDATE / pair["name"]
        sides = {}
        for side in ("indoor", "outdoor"):
            side_dir = pair_dir / side
            manifest_path = side_dir / "manifest.json"
            if not manifest_path.is_file():
                raise FileNotFoundError(manifest_path)
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("method") != "HY-World 2.0":
                raise ValueError(f"Wrong method provenance: {manifest_path}")
            if manifest.get("training_steps_requested") != TRAIN_STEPS:
                raise ValueError(f"Wrong training budget: {manifest_path}")
            if manifest.get("training_final_step") != PLY_STEP:
                raise ValueError(f"Wrong final training step: {manifest_path}")
            if (
                manifest.get("rendering", {}).get("camera_policy")
                != "gs_data_training_horizontal_v1"
            ):
                raise ValueError(f"Wrong camera policy: {manifest_path}")
            scene_ply = side_dir / manifest["model"]["ply"]
            if read_gaussian_vertex_count(scene_ply) != manifest["gaussian_count"]:
                raise ValueError(f"Gaussian count mismatch: {scene_ply}")
            if sha256_file(scene_ply) != manifest["model"]["ply_sha256"]:
                raise ValueError(f"PLY checksum mismatch: {scene_ply}")
            images = sorted((side_dir / "images").rglob("*.png"))
            if len(images) != 24:
                raise ValueError(
                    f"Expected 24 images below {side_dir}, found {len(images)}"
                )
            for image_path in images:
                with Image.open(image_path) as handle:
                    handle.load()
                    if handle.size != (1600, 900) or handle.mode != "RGB":
                        raise ValueError(
                            f"Invalid image {image_path}: {handle.size} {handle.mode}"
                        )
            video = side_dir / "video/walkthrough.mp4"
            probe = probe_video(video)
            if int(probe["width"]) != 960 or int(probe["height"]) != 540:
                raise ValueError(f"Invalid video resolution: {video}: {probe}")
            if int(probe.get("nb_frames", 0)) != 120:
                raise ValueError(f"Invalid video frame count: {video}: {probe}")
            if sha256_file(video) != manifest["rendering"]["video_sha256"]:
                raise ValueError(f"Video checksum mismatch: {video}")
            sides[side] = {
                "spec_id": manifest["spec_id"],
                "logical_seed": manifest["logical_seed"],
                "gaussian_count": manifest["gaussian_count"],
                "image_count": len(images),
                "video": str(video.relative_to(CANDIDATE)),
                "video_probe": probe,
                "manifest": str(manifest_path.relative_to(CANDIDATE)),
            }
        pair_manifest = {
            "schema_version": "hyworld2-connect2-native-pair-v2",
            "method": "HY-World 2.0",
            "pair_name": pair["name"],
            "pairing_semantics": "independent native indoor and urban scenes selected as a visual pair",
            "native_shared_world_frame": False,
            "native_unified_indoor_outdoor": False,
            "portal_connectivity_claimed": False,
            "sides": sides,
        }
        atomic_json(pair_dir / "manifest.json", pair_manifest)
        scene_records.append(pair_manifest)

    delivery = {
        "schema_version": "hyworld2-connect2-native-delivery-v2",
        "created_at_utc": utc_now(),
        "method": "HY-World 2.0",
        "method_commit": METHOD_COMMIT,
        "scene_pair_count": len(PAIRS),
        "real_3d_representation": "3D Gaussian Splatting PLY plus training checkpoint",
        "total_native_3d_scenes": len(PAIRS) * 2,
        "images_per_side": 24,
        "videos_per_side": 1,
        "native_shared_world_frame": False,
        "native_unified_indoor_outdoor": False,
        "portal_connectivity_claimed": False,
        "provenance_note_zh": (
            "This delivery includes the original generation and retraining of a 3D Gaussian scene using HY-World 2.0."
            "Visual pairing of indoor and outdoor coordinates as separate coordinate systems, without pretending to be connected worlds within the same coordinate system."
        ),
        "scenes": scene_records,
    }
    atomic_json(CANDIDATE / "delivery_manifest.json", delivery)
    readme = """# HY-World 2.0 native high-quality indoor/outdoor pairing results

This directory contains 6 sets of demonstrations, each featuring a real HY-World 2.0 native indoor 3D Gaussian.
Scene and an original outdoor 3D Gaussian scene. All scenes are from existing HY-World 2.0 run results.
Do heavy training for 2000 steps; no use of GPT-Astra's Blender scene or geometry assets.

Important boundary: Official HY-World 2.0 currently does not generate an indoor-outdoor joint world within the same coordinate system. Therefore here is
\"Native dual-scenario pairing display of 'Inside-Outside', without claiming that both sides are geometrically connected, nor disguising the synthetic door hole as an actual one.\"
HY-World 2.0 outputs. This limit writes to the root directory, each group, and each side of the manifest simultaneously.

Each side contains:

- `model/scene.ply`: Realistic 3D Gaussian Splatting scenes that can be loaded directly;
- `model/training_checkpoint.pt`: camera transformation and training status;
- `images/{wide,far,native_ultrawide}/`: 24 independent 1600×900 images, no stitching, no numbered watermarks;
- `video/walkthrough.mp4`: 120 frames, 960×540, 15 fps safe wide-angle surround video;
- `source_panorama.png`: HY-World 2.0 original panoramic evidence;
- `manifest.json`: source, seed, hash, Gaussian count, and camera trajectory.

`wide/far/native_ultrawide` uses 100°/112°/120° horizontal field of view angles to provide different perspectives for near and distant views;
The camera uses only the horizontal poses covered by the 3DGS training set to avoid entering walls or furniture. All images have been restricted.
Adaptive brightening (gain up to 1.35 with gamma set to 0.90) without adding text or numbering within the image.
"""
    (CANDIDATE / "README.md").write_text(readme, encoding="utf-8")

    checksums = []
    for path in sorted(CANDIDATE.rglob("*")):
        if not path.is_file() or path.name == "SHA256SUMS":
            continue
        checksums.append(f"{sha256_file(path)}  {path.relative_to(CANDIDATE)}")
    (CANDIDATE / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    print(
        f"PACKAGE_DONE candidate={CANDIDATE} scenes={len(PAIRS)} files={len(checksums)}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("train", "render", "package", "all"):
        child = subparsers.add_parser(action)
        child.add_argument("--gpu", type=int, default=1)
    render_one_parser = subparsers.add_parser("render-one")
    render_one_parser.add_argument(
        "--pair", required=True, choices=[row["name"] for row in PAIRS]
    )
    render_one_parser.add_argument(
        "--side", required=True, choices=("indoor", "outdoor")
    )
    render_one_parser.add_argument("--gpu", type=int, default=1)
    args = parser.parse_args()

    if args.action == "train":
        train_all(args.gpu)
    elif args.action == "render":
        render_all(args.gpu)
    elif args.action == "package":
        package()
    elif args.action == "render-one":
        render_side(args.pair, args.side, args.gpu)
    elif args.action == "all":
        train_all(args.gpu)
        render_all(args.gpu)
        package()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

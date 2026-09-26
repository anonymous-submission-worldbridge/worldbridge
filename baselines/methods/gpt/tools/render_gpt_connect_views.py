#!/usr/bin/env python3
"""Render supplemental near/mid/far bidirectional connectivity views."""
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
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
OUTPUT = (BASELINES / "annotations/gpt6_astra/connect").resolve()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def configure_cycles(seed: int) -> dict:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.seed = seed + 1000
    scene.cycles.use_denoising = True
    scene.cycles.samples = 128
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.025
    preferences = bpy.context.preferences.addons["cycles"].preferences
    selected = None
    selected_devices: list[str] = []
    for backend in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = backend
            preferences.get_devices()
        except Exception:
            continue
        devices = [device for device in preferences.devices if device.type == backend]
        if not devices:
            continue
        for device in preferences.devices:
            device.use = device.type == backend
        selected = backend
        selected_devices = [device.name for device in devices if device.use]
        break
    if selected is None:
        raise RuntimeError("No CUDA/OptiX Cycles device is available")
    try:
        scene.cycles.denoiser = "OPTIX"
    except Exception:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.view_settings.view_transform = "AgX"
    for look in ("AgX - Medium High Contrast", "Medium High Contrast", "None"):
        try:
            scene.view_settings.look = look
            break
        except (TypeError, ValueError):
            continue
    scene.view_settings.exposure = 0.10
    scene.view_settings.gamma = 1.0
    return {"engine": "Cycles", "device_backend": selected, "devices": selected_devices}


def point_camera(
    camera: bpy.types.Object,
    position: tuple[float, float, float],
    target: tuple[float, float, float],
    horizontal_fov_degrees: float,
) -> None:
    camera.data.sensor_width = 36.0
    camera.data.lens = 36.0 / (
        2.0 * math.tan(math.radians(horizontal_fov_degrees) / 2.0)
    )
    camera.data.clip_start = 0.05
    camera.data.clip_end = 200.0
    camera.location = position
    direction = Vector(target) - Vector(position)
    camera.rotation_mode = "QUATERNION"
    camera.rotation_quaternion = direction.to_track_quat("-Z", "Y")
    bpy.context.view_layer.update()


VIEWS = [
    # Interior looking outward: mostly farther than the original connection view,
    # with centered, corner, oblique, high, low, mid, and threshold positions.
    (
        "indoor_to_outdoor",
        "far_center_high_wide",
        (0.0, 7.15, 2.30),
        (0.0, -5.4, 1.25),
        76.0,
        "far",
    ),
    (
        "indoor_to_outdoor",
        "far_center_eye_level",
        (0.0, 6.75, 1.66),
        (0.0, -6.2, 1.22),
        66.0,
        "far",
    ),
    (
        "indoor_to_outdoor",
        "far_left_corner",
        (-4.20, 5.55, 2.05),
        (0.0, -5.1, 1.22),
        70.0,
        "far",
    ),
    (
        "indoor_to_outdoor",
        "far_right_corner",
        (4.20, 5.55, 2.05),
        (0.0, -5.1, 1.22),
        70.0,
        "far",
    ),
    (
        "indoor_to_outdoor",
        "mid_center_high",
        (0.0, 4.15, 2.45),
        (0.0, -7.0, 1.18),
        74.0,
        "mid",
    ),
    (
        "indoor_to_outdoor",
        "mid_center_low",
        (0.0, 3.75, 1.35),
        (0.0, -7.0, 1.10),
        64.0,
        "mid",
    ),
    (
        "indoor_to_outdoor",
        "mid_left_oblique",
        (-3.55, 3.65, 1.82),
        (0.0, -5.8, 1.20),
        72.0,
        "mid",
    ),
    (
        "indoor_to_outdoor",
        "mid_right_oblique",
        (3.55, 3.65, 1.82),
        (0.0, -5.8, 1.20),
        72.0,
        "mid",
    ),
    (
        "indoor_to_outdoor",
        "near_left_threshold",
        (-2.10, 1.35, 1.62),
        (0.0, -8.7, 1.16),
        78.0,
        "near",
    ),
    (
        "indoor_to_outdoor",
        "near_right_threshold",
        (2.10, 1.35, 1.62),
        (0.0, -8.7, 1.16),
        78.0,
        "near",
    ),
    # Exterior looking inward: wide establishing views from the edge of the
    # scene, diagonal facade views, eye-level approaches, and threshold views.
    (
        "outdoor_to_indoor",
        "far_center_high_wide",
        (0.0, -17.10, 3.05),
        (0.0, 0.6, 1.28),
        76.0,
        "far",
    ),
    (
        "outdoor_to_indoor",
        "far_center_eye_level",
        (0.0, -16.20, 1.68),
        (0.0, 1.5, 1.24),
        66.0,
        "far",
    ),
    (
        "outdoor_to_indoor",
        "far_left_establishing",
        (-11.25, -15.80, 3.00),
        (0.0, -3.7, 1.32),
        72.0,
        "far",
    ),
    (
        "outdoor_to_indoor",
        "far_right_establishing",
        (11.25, -15.80, 3.00),
        (0.0, -3.7, 1.32),
        72.0,
        "far",
    ),
    (
        "outdoor_to_indoor",
        "mid_center_approach",
        (0.0, -11.70, 1.78),
        (0.0, 1.1, 1.24),
        68.0,
        "mid",
    ),
    (
        "outdoor_to_indoor",
        "mid_left_oblique",
        (-8.20, -11.60, 2.35),
        (0.0, -2.2, 1.30),
        70.0,
        "mid",
    ),
    (
        "outdoor_to_indoor",
        "mid_right_oblique",
        (8.20, -11.60, 2.35),
        (0.0, -2.2, 1.30),
        70.0,
        "mid",
    ),
    (
        "outdoor_to_indoor",
        "near_center_low",
        (0.0, -8.10, 1.38),
        (0.0, 2.0, 1.16),
        64.0,
        "near",
    ),
    (
        "outdoor_to_indoor",
        "near_left_facade",
        (-5.15, -8.25, 1.88),
        (0.0, 0.6, 1.24),
        74.0,
        "near",
    ),
    (
        "outdoor_to_indoor",
        "near_right_facade",
        (5.15, -8.25, 1.88),
        (0.0, 0.6, 1.24),
        74.0,
        "near",
    ),
]


# A few far viewpoints need scene-aware clearance.  The lodge has a deep
# fireplace/chimney on its rear centreline and sculptural mountain meshes near
# the generic far-left/far-right exterior positions.
SCENE_VIEW_OVERRIDES = {
    "demo_06_alpine_lodge_terrace": {
        ("indoor_to_outdoor", "far_center_high_wide"): (
            "indoor_to_outdoor",
            "far_center_high_wide",
            (0.0, 6.65, 2.38),
            (0.0, -5.4, 1.25),
            76.0,
            "far",
        ),
        ("outdoor_to_indoor", "far_left_establishing"): (
            "outdoor_to_indoor",
            "far_left_establishing",
            (-10.20, -12.50, 2.85),
            (0.0, -3.7, 1.32),
            72.0,
            "far",
        ),
        ("outdoor_to_indoor", "far_right_establishing"): (
            "outdoor_to_indoor",
            "far_right_establishing",
            (10.20, -12.50, 2.85),
            (0.0, -3.7, 1.32),
            72.0,
            "far",
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    if not run.is_relative_to(OUTPUT):
        raise ValueError("Run directory escapes the connect-demo output root")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("render_success") or not manifest.get(
        "connectivity_audit", {}
    ).get("passed"):
        raise RuntimeError("Base render or connectivity audit is incomplete")
    scene_path = run / manifest["scene_file"]
    if Path(bpy.data.filepath).resolve() != scene_path.resolve():
        raise RuntimeError("Blender did not open the expected scene file")
    if sha256(scene_path) != manifest.get("scene_sha256"):
        raise RuntimeError("Scene file hash mismatch")
    camera = bpy.context.scene.camera or bpy.data.objects.get("ConnectDemoCamera")
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("Scene camera is unavailable")
    backend = configure_cycles(int(manifest["logical_seed"]))
    existing = {
        record["path"]: record for record in manifest.get("supplemental_stills", [])
    }
    records = []
    try:
        overrides = SCENE_VIEW_OVERRIDES.get(run.name, {})
        for index, base_view in enumerate(VIEWS, start=1):
            direction, role, position, target, fov, distance_band = overrides.get(
                (base_view[0], base_view[1]), base_view
            )
            relative = f"images/{direction}/{role}.png"
            path = run / relative
            old = existing.get(relative)
            configuration_matches = old and all(
                (
                    old.get("direction") == direction,
                    old.get("role") == role,
                    old.get("distance_band") == distance_band,
                    old.get("camera_xyz_m") == list(position),
                    old.get("target_xyz_m") == list(target),
                    old.get("horizontal_fov_degrees") == fov,
                )
            )
            if (
                configuration_matches
                and path.is_file()
                and old.get("sha256") == sha256(path)
            ):
                records.append(old)
                print(
                    f"CONNECT_VIEW_REUSED {run.name} {index}/{len(VIEWS)} {direction}/{role}",
                    flush=True,
                )
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            point_camera(camera, position, target, fov)
            bpy.context.scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            record = {
                "path": relative,
                "direction": direction,
                "role": role,
                "distance_band": distance_band,
                "camera_xyz_m": list(position),
                "target_xyz_m": list(target),
                "horizontal_fov_degrees": fov,
                "resolution": [1280, 720],
                "samples": 128,
                "sha256": sha256(path),
                "bytes": path.stat().st_size,
            }
            records.append(record)
            manifest["supplemental_stills"] = records
            manifest["supplemental_render_success"] = False
            write_json(manifest_path, manifest)
            print(
                f"CONNECT_VIEW_COMPLETE {run.name} {index}/{len(VIEWS)} {direction}/{role}",
                flush=True,
            )
        manifest["supplemental_stills"] = records
        manifest["supplemental_render_success"] = True
        manifest["supplemental_render_completed_at_utc"] = now()
        manifest["supplemental_render_backend"] = backend
        manifest.setdefault("outputs_sha256", {}).update(
            {record["path"]: record["sha256"] for record in records}
        )
        manifest.pop("supplemental_render_failure", None)
        manifest.pop("supplemental_render_failed_at_utc", None)
        write_json(manifest_path, manifest)
        print(f"CONNECT_VIEWS_RENDER_COMPLETE {run.name} backend={backend}", flush=True)
        return 0
    except Exception as error:
        manifest["supplemental_stills"] = records
        manifest["supplemental_render_success"] = False
        manifest["supplemental_render_failure"] = f"{type(error).__name__}: {error}"
        manifest["supplemental_render_failed_at_utc"] = now()
        write_json(manifest_path, manifest)
        raise


if __name__ == "__main__":
    raise SystemExit(main())

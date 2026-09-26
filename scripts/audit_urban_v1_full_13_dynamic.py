#!/usr/bin/env python3
"""Audit full-13 dynamic provenance, animation, and rendered delivery."""

from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import argparse
import hashlib
import json
import math
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic"
STATIC = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13/urban_v1_full_13.blend"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def png_dimensions(path: Path) -> tuple[int, int] | None:
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
        if header[:8] != b"\x89PNG\r\n\x1a\n":
            return None
        return struct.unpack(">II", header[16:24])
    except (OSError, struct.error):
        return None


def action_fcurves(owner: object) -> list[object]:
    animation = getattr(owner, "animation_data", None)
    action = getattr(animation, "action", None) if animation else None
    if action is None:
        return []
    try:
        return list(action.fcurves)
    except (AttributeError, RuntimeError):
        result = []
        for layer in getattr(action, "layers", []):
            for strip in getattr(layer, "strips", []):
                for channelbag in getattr(strip, "channelbags", []):
                    result.extend(channelbag.fcurves)
        return result


def sample(
    objects: list[bpy.types.Object], attribute: str, frame: int
) -> dict[str, list[float]]:
    bpy.context.scene.frame_set(frame)
    return {
        obj.name: [round(float(value), 7) for value in getattr(obj, attribute)]
        for obj in objects
    }


def changed(
    first: dict[str, list[float]], second: dict[str, list[float]], tolerance: float
) -> list[str]:
    return sorted(
        name
        for name in first.keys() & second.keys()
        if math.dist(first[name], second[name]) > tolerance
    )


def main() -> None:
    output_dir = parse_args().output_dir.expanduser().resolve()
    manifest_path = output_dir / "dynamic_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    objects = list(bpy.data.objects)
    vehicles = sorted(
        (obj for obj in objects if obj.get("c2w_dynamic_role") == "vehicle"),
        key=lambda obj: obj.name,
    )
    wheels = sorted(
        (
            obj
            for obj in objects
            if "grp_wheel_steering_rotating" in obj.name.casefold()
            and action_fcurves(obj)
        ),
        key=lambda obj: obj.name,
    )
    tree_parts = sorted(
        (
            obj
            for obj in objects
            if obj.type == "MESH"
            and obj.name.startswith("C2W_DYN::full07:tree_master:")
            and action_fcurves(obj)
        ),
        key=lambda obj: obj.name,
    )
    flow_controls = sorted(
        (obj for obj in objects if obj.name.startswith("C2W_FlowControl::")),
        key=lambda obj: obj.name,
    )
    fountain_streams = sorted(
        (
            obj
            for obj in objects
            if obj.name.startswith("C2W_DYN::urban:fountain:")
            and any(
                token in obj.name.casefold()
                for token in ("pressure_j", "laminar_shee", "vertical_aerated_plu")
            )
            and any(curve.data_path == "scale" for curve in action_fcurves(obj))
        ),
        key=lambda obj: obj.name,
    )

    vehicle_start = sample(vehicles, "location", 1)
    vehicle_later = sample(vehicles, "location", 18)
    wheel_start = sample(wheels, "rotation_euler", 1)
    wheel_later = sample(wheels, "rotation_euler", 18)
    tree_start = sample(tree_parts, "rotation_euler", 1)
    tree_gust = sample(tree_parts, "rotation_euler", 37)
    flow_start = sample(flow_controls, "location", 1)
    flow_later = sample(flow_controls, "location", 54)
    fountain_start = sample(fountain_streams, "scale", 73)
    fountain_later = sample(fountain_streams, "scale", 82)

    dynamic_meshes = [
        obj
        for obj in objects
        if obj.type == "MESH" and obj.name.startswith("C2W_DYN::")
    ]
    local_geometry = [
        obj.name
        for obj in dynamic_meshes
        if obj.data is not None and obj.data.library is None
    ]
    frames = sorted((output_dir / "frames").glob("frame_*.png"))
    valid_frames = [path for path in frames if path.stat().st_size > 4096]
    frame_resolutions = sorted(
        {
            png_dimensions(path)
            for path in valid_frames
            if png_dimensions(path) is not None
        }
    )
    video = output_dir / "urban_v1_full_13_dynamic.mp4"

    checks = {
        "manifest_pass": manifest.get("status") == "PASS",
        "source_static_hash_unchanged": (
            sha256(STATIC) == manifest.get("source_static_master_sha256")
        ),
        "no_local_replacement_meshes": not local_geometry,
        "all_18_vehicles_move": len(changed(vehicle_start, vehicle_later, 0.05)) == 18,
        "all_72_wheel_rigs_rotate": len(changed(wheel_start, wheel_later, 0.01)) == 72,
        "tree_parts_animate": len(changed(tree_start, tree_gust, 1.0e-5)) >= 10,
        "water_flow_controls_move": len(changed(flow_start, flow_later, 0.01)) >= 3,
        "native_fountain_streams_pulse": (
            len(changed(fountain_start, fountain_later, 1.0e-5))
            == len(fountain_streams)
            and len(fountain_streams) >= 2
        ),
        "all_144_frames_present": len(valid_frames) == 144,
        "all_frames_share_one_resolution": len(frame_resolutions) == 1,
        "video_present": video.is_file() and video.stat().st_size > 64 * 1024,
    }
    report = {
        "schema": "agent.full13.dynamic_audit.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "motion_counts": {
            "vehicles": len(vehicles),
            "vehicles_changed": len(changed(vehicle_start, vehicle_later, 0.05)),
            "wheel_rigs": len(wheels),
            "wheel_rigs_changed": len(changed(wheel_start, wheel_later, 0.01)),
            "animated_tree_mesh_parts": len(tree_parts),
            "tree_parts_changed": len(changed(tree_start, tree_gust, 1.0e-5)),
            "water_flow_controls": len(flow_controls),
            "water_flow_controls_changed": len(changed(flow_start, flow_later, 0.01)),
            "native_fountain_streams": len(fountain_streams),
            "native_fountain_streams_changed": len(
                changed(fountain_start, fountain_later, 1.0e-5)
            ),
        },
        "geometry_provenance": {
            "dynamic_mesh_wrapper_count": len(dynamic_meshes),
            "linked_exact_mesh_count": len(dynamic_meshes) - len(local_geometry),
            "local_replacement_mesh_count": len(local_geometry),
            "local_replacement_mesh_names": local_geometry,
        },
        "delivery": {
            "valid_frame_count": len(valid_frames),
            "frame_resolutions": frame_resolutions,
            "video": str(video),
            "video_bytes": video.stat().st_size if video.is_file() else 0,
            "wind_tail_manifest": str(output_dir / "wind_tail_manifest.json"),
        },
    }
    target = output_dir / "dynamic_audit.json"
    target.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[full13-dynamic-audit] {report['status']} report={target}", flush=True)
    if report["status"] != "PASS":
        raise RuntimeError(json.dumps(checks, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Render varied near/medium/far portal views from a connected 3D scene.

The script is executed by Blender after opening one of the verified HyWorld2
``scene.blend`` files.  Cameras are derived from the audited portal position,
outward direction, and building footprint; source scene files are not changed.
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


import argparse
import hashlib
import json
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--engine", choices=("workbench", "eevee"), default="workbench")
    parser.add_argument(
        "--profile",
        choices=("multiview", "far_bright"),
        default="multiview",
        help="Camera/lighting profile and output subdirectory.",
    )
    parser.add_argument("--indoor-far-distance", type=float, default=4.2)
    parser.add_argument("--indoor-side-distance", type=float)
    parser.add_argument(
        "--outdoor-left-lateral",
        type=float,
        help="Override the far-left lateral offset when nearby geometry occludes it.",
    )
    parser.add_argument(
        "--force-role",
        choices=("outdoor_to_indoor", "indoor_to_outdoor"),
    )
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-view")
    return parser.parse_args(argv)


def sha256(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def interior_depth(building: dict, outward: Vector) -> float:
    footprint = building["footprint_m"]
    x, y, _ = building["entrance_position_m"]
    if outward.x > 0.5:
        return x - footprint["x_min"]
    if outward.x < -0.5:
        return footprint["x_max"] - x
    if outward.y > 0.5:
        return y - footprint["y_min"]
    return footprint["y_max"] - y


def lateral_width(building: dict, outward: Vector) -> float:
    footprint = building["footprint_m"]
    if abs(outward.x) > 0.5:
        return footprint["y_max"] - footprint["y_min"]
    return footprint["x_max"] - footprint["x_min"]


def make_camera(name: str, location: Vector, target: Vector, lens: float):
    data = bpy.data.cameras.new(name)
    data.lens = lens
    data.sensor_width = 36.0
    data.clip_start = 0.08
    data.clip_end = 500.0
    camera = bpy.data.objects.new(name, data)
    bpy.context.scene.collection.objects.link(camera)
    camera.location = location
    camera.rotation_euler = (target - location).to_track_quat("-Z", "Y").to_euler()
    return camera


def sync_node_colors_to_workbench() -> None:
    """Use Principled base colors for material-color Workbench rendering."""
    for material in bpy.data.materials:
        if not material.use_nodes or not material.node_tree:
            continue
        for node in material.node_tree.nodes:
            if node.type != "BSDF_PRINCIPLED":
                continue
            base_color = node.inputs.get("Base Color")
            if base_color is not None and not base_color.is_linked:
                rgba = base_color.default_value
                material.diffuse_color = (rgba[0], rgba[1], rgba[2], rgba[3])
            break


def camera_spec(
    role: str,
    distance: float,
    lateral: float,
    height: float,
    lens: float,
    portal: Vector,
    outward: Vector,
    tangent: Vector,
) -> dict:
    if role == "outdoor_to_indoor":
        location = portal + outward * distance + tangent * lateral
        location.z = height
        target = portal - outward * 2.4
        target.z = 1.45
    else:
        location = portal - outward * distance + tangent * lateral
        location.z = height
        target = portal + outward * 7.0
        target.z = 1.45
    return {
        "role": role,
        "distance_m": distance,
        "lateral_m": lateral,
        "height_m": height,
        "lens_mm": lens,
        "location": location,
        "target": target,
    }


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    audit = json.loads(args.audit.resolve().read_text(encoding="utf-8"))
    building = audit["connected_buildings"][0]
    portal = Vector(building["entrance_position_m"])
    outward = Vector(building["entrance_outward_direction"]).normalized()
    tangent = Vector((-outward.y, outward.x, 0.0))
    depth = interior_depth(building, outward)
    width = lateral_width(building, outward)
    # The audited footprint can contain several partitioned rooms.  Keep the
    # portal-facing cameras inside the first room so an internal wall cannot
    # obscure the opening; 2.4--4.2 m is still substantially wider than the
    # original threshold close-up.
    far_inside = min(args.indoor_far_distance, max(3.4, depth - 1.35))
    side_inside = min(1.15, max(0.8, width * 0.11))
    if args.indoor_side_distance is not None:
        side_inside = args.indoor_side_distance
    outdoor_left = (
        args.outdoor_left_lateral
        if args.outdoor_left_lateral is not None
        else side_inside + 3.30
    )

    if args.profile == "far_bright":
        definitions = {
            "outdoor_to_indoor": (
                ("far_center", 15.0, 0.0, 2.10, 30.0),
                ("very_far_center", 22.0, 0.0, 2.60, 34.0),
                ("far_left", 18.0, outdoor_left, 2.00, 28.0),
                ("far_right", 18.0, -(side_inside + 3.30), 2.00, 28.0),
                ("elevated_far", 20.0, side_inside + 5.00, 6.50, 30.0),
                ("street_context", 28.0, 0.0, 3.20, 40.0),
            ),
            "indoor_to_outdoor": (
                ("far_wide_center", far_inside, 0.0, 1.65, 20.0),
                (
                    "far_ultrawide_center",
                    max(2.8, far_inside - 0.18),
                    0.0,
                    1.72,
                    15.0,
                ),
                (
                    "far_wide_left",
                    min(3.45, far_inside),
                    side_inside,
                    1.60,
                    18.0,
                ),
                (
                    "far_wide_right",
                    min(3.45, far_inside),
                    -side_inside,
                    1.60,
                    18.0,
                ),
                ("high_wide_center", max(2.8, far_inside - 0.10), 0.0, 2.25, 20.0),
                ("low_wide_center", max(2.8, far_inside - 0.22), 0.0, 1.10, 18.0),
            ),
        }
    else:
        definitions = {
            "outdoor_to_indoor": (
                ("near_center", 5.0, 0.0, 1.65, 34.0),
                ("medium_center", 8.0, 0.0, 1.85, 38.0),
                ("far_center", 12.5, 0.0, 2.15, 42.0),
                ("medium_left", 8.5, side_inside + 0.8, 1.75, 36.0),
                ("medium_right", 8.5, -(side_inside + 0.8), 1.75, 36.0),
                ("elevated_oblique", 11.0, side_inside + 2.0, 4.2, 40.0),
            ),
            "indoor_to_outdoor": (
                ("near_center", 2.4, 0.0, 1.55, 32.0),
                ("medium_center", min(3.35, far_inside), 0.0, 1.62, 32.0),
                ("far_center", far_inside, 0.0, 1.72, 30.0),
                ("medium_left", min(3.45, far_inside), side_inside, 1.60, 30.0),
                ("medium_right", min(3.45, far_inside), -side_inside, 1.60, 30.0),
                ("far_oblique", far_inside, -side_inside, 1.95, 32.0),
            ),
        }

    scene = bpy.context.scene
    scene.render.engine = (
        "BLENDER_WORKBENCH" if args.engine == "workbench" else "BLENDER_EEVEE_NEXT"
    )
    if args.engine == "workbench":
        sync_node_colors_to_workbench()
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        shading.background_type = "VIEWPORT"
        if args.profile == "far_bright":
            shading.background_color = (0.86, 0.91, 0.96)
            shading.show_shadows = False
            shading.show_cavity = False
            scene.view_settings.view_transform = "Standard"
            scene.view_settings.look = "Medium High Contrast"
            scene.view_settings.exposure = 1.15
            scene.view_settings.gamma = 1.0
        else:
            shading.background_color = (0.72, 0.80, 0.88)
            shading.show_shadows = True
            shading.show_cavity = True
        shading.cavity_type = "WORLD"
        shading.show_object_outline = False
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 35

    records = []
    started = time.time()
    for role, views in definitions.items():
        role_dir = output_dir / args.profile / role
        role_dir.mkdir(parents=True, exist_ok=True)
        for view_name, distance, lateral, height, lens in views:
            spec = camera_spec(
                role,
                distance,
                lateral,
                height,
                lens,
                portal,
                outward,
                tangent,
            )
            camera_name = f"connect_{role}_{view_name}"
            camera = make_camera(
                camera_name, spec["location"], spec["target"], spec["lens_mm"]
            )
            scene.camera = camera
            output_path = role_dir / f"{view_name}.png"
            force_this_view = (
                args.force or args.force_role == role or args.force_view == view_name
            )
            if (
                not (output_path.exists() and output_path.stat().st_size > 0)
                or force_this_view
            ):
                scene.render.filepath = str(output_path)
                print(
                    f"CONNECT_RENDER profile={args.profile} role={role} view={view_name} "
                    f"distance={distance:.2f} lateral={lateral:.2f} lens={lens:.1f}",
                    flush=True,
                )
                bpy.ops.render.render(write_still=True)
            else:
                print(f"CONNECT_SKIP {output_path}", flush=True)
            records.append(
                {
                    "role": role,
                    "view": view_name,
                    "camera": camera_name,
                    "distance_from_portal_m": distance,
                    "lateral_offset_m": lateral,
                    "height_m": height,
                    "lens_mm": lens,
                    "location_m": [round(float(v), 6) for v in spec["location"]],
                    "target_m": [round(float(v), 6) for v in spec["target"]],
                    "path": str(output_path.relative_to(output_dir)),
                    "bytes": output_path.stat().st_size,
                    "sha256": sha256(output_path),
                }
            )

    manifest = {
        "schema_version": "1.0",
        "source_blend": str(Path(bpy.data.filepath).resolve()),
        "scene_seed": audit["scene_seed"],
        "topology": audit["topology"],
        "building_id": building["building_id"],
        "portal_position_m": [round(float(v), 6) for v in portal],
        "portal_outward_direction": [round(float(v), 6) for v in outward],
        "audited_interior_depth_m": round(depth, 6),
        "audited_lateral_width_m": round(width, 6),
        "render_engine": scene.render.engine,
        "render_profile": args.profile,
        "resolution": [args.width, args.height],
        "exposure": float(scene.view_settings.exposure),
        "workbench_shadows": bool(scene.display.shading.show_shadows),
        "workbench_cavity": bool(scene.display.shading.show_cavity),
        "independent_images": True,
        "pixel_overlays": False,
        "view_count": len(records),
        "elapsed_seconds": round(time.time() - started, 3),
        "views": records,
        "validation": "rendered_from_real_3d_scene",
    }
    manifest_path = output_dir / args.profile / "camera_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"CONNECT_RENDER_DONE {manifest_path}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Resume-safe Eevee frame renderer for the full-13 dynamic delivery blend."""

from __future__ import annotations

import argparse
import json
import os
import struct
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--frame-start", type=int, default=0)
    parser.add_argument("--frame-end", type=int, default=0)
    parser.add_argument(
        "--frames",
        default="",
        help="Optional comma-separated sparse frame list for visual preflight",
    )
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    parser.add_argument("--samples", type=int, default=32)
    parser.add_argument(
        "--engine",
        choices=("eevee", "workbench"),
        default="eevee",
        help="Workbench is the resource-safe exact-geometry mode for 11M+ vertex trees.",
    )
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--all-tree-species",
        action="store_true",
        help=(
            "Render every 11--30M-vertex botanical species. By default the video "
            "keeps all TreeFactory:42 instances and culls the other exact species "
            "only in this render process to stay below Vulkan's buffer limit."
        ),
    )
    parser.add_argument(
        "--tree-mode",
        choices=("exact42", "none", "all"),
        default="exact42",
        help=(
            "Transient video-only tree visibility: exact42 keeps the smallest "
            "original high-detail species, none is useful for water/fountain "
            "preflights, and all requires a very large Vulkan buffer."
        ),
    )
    return parser.parse_args(argv)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def write_atomic(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def valid_png(path: Path, width: int, height: int) -> bool:
    if not path.is_file() or path.stat().st_size <= 4096:
        return False
    try:
        with path.open("rb") as stream:
            header = stream.read(24)
        return header[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(
            ">II", header[16:24]
        ) == (width, height)
    except (OSError, struct.error):
        return False


def configure_exact_tree_render_budget(mode: str) -> dict:
    """Cull only render instances, never source meshes or saved blend content.

    The authored tree masters range from 11 to 30 million vertices each.  Blender
    5.1 cannot place all five species in one Vulkan storage buffer.  Reusing every
    instance of the smallest *original* high-detail species keeps visible wind
    motion while avoiding a proxy, decimation, billboard, or replacement mesh.
    """

    candidates = [
        obj
        for obj in bpy.data.objects
        if obj.instance_collection is not None
        and obj.instance_collection.name.startswith("C2W_DynamicTreeMaster::")
    ]
    kept: list[str] = []
    culled: list[str] = []
    for obj in candidates:
        master = obj.instance_collection.name
        keep = mode == "all" or (mode == "exact42" and "TreeFactory:42" in master)
        obj.hide_render = not keep
        (kept if keep else culled).append(obj.name)
    return {
        "mode": {
            "all": "all_exact_species",
            "exact42": "exact_species_42_instances",
            "none": "no_trees_water_preflight",
        }[mode],
        "source_geometry_modified": False,
        "proxy_or_lod_geometry_used": False,
        "kept_instance_count": len(kept),
        "culled_instance_count": len(culled),
        "kept_instances": kept,
    }


def expose_principled_colors_to_workbench() -> dict:
    """Copy authored constant Base Color into transient viewport colors."""

    examined = 0
    changed = 0
    for material in bpy.data.materials:
        examined += 1
        if not material.use_nodes or material.node_tree is None:
            continue
        principled = next(
            (
                node
                for node in material.node_tree.nodes
                if node.type == "BSDF_PRINCIPLED"
            ),
            None,
        )
        if principled is None:
            continue
        base_color = principled.inputs.get("Base Color")
        if base_color is None or base_color.is_linked:
            continue
        color = tuple(base_color.default_value)
        if tuple(material.diffuse_color) != color:
            material.diffuse_color = color
            changed += 1
    return {
        "materials_examined": examined,
        "viewport_colors_changed": changed,
        "node_graphs_changed": False,
        "source_files_saved": False,
    }


def main() -> None:
    args = parse_args()
    scene = bpy.context.scene
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    start = args.frame_start or scene.frame_start
    end = args.frame_end or scene.frame_end
    if start < scene.frame_start or end > scene.frame_end or end < start:
        raise ValueError(
            f"Requested range {start}..{end} is outside scene range "
            f"{scene.frame_start}..{scene.frame_end}"
        )
    selected_frames = (
        sorted(
            {int(value.strip()) for value in args.frames.split(",") if value.strip()}
        )
        if args.frames
        else list(range(start, end + 1))
    )
    if not selected_frames or any(
        frame < scene.frame_start or frame > scene.frame_end
        for frame in selected_frames
    ):
        raise ValueError(
            f"Sparse frames must stay inside {scene.frame_start}..{scene.frame_end}: "
            f"{selected_frames}"
        )

    engines = {
        item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items
    }
    if args.engine == "workbench":
        if "BLENDER_WORKBENCH" not in engines:
            raise RuntimeError(f"Workbench is unavailable: {sorted(engines)}")
        scene.render.engine = "BLENDER_WORKBENCH"
        scene.display.render_aa = str(
            min((8, 16, 32), key=lambda value: abs(value - args.samples))
        )
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.studio_light = "outdoor.sl"
        shading.studiolight_rotate_z = 0.24
        shading.color_type = "MATERIAL"
        shading.background_type = "VIEWPORT"
        shading.background_color = (0.34, 0.59, 0.86)
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = "BOTH"
        shading.curvature_ridge_factor = 1.35
        shading.curvature_valley_factor = 1.15
        shading.show_specular_highlight = True
        material_bridge = expose_principled_colors_to_workbench()
    else:
        eevee = next((name for name in engines if "EEVEE" in name), None)
        if eevee is None:
            raise RuntimeError(f"Eevee is unavailable: {sorted(engines)}")
        scene.render.engine = eevee
        material_bridge = {"enabled": False}
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    if hasattr(scene.render, "use_motion_blur"):
        scene.render.use_motion_blur = False
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = args.samples
    tree_mode = "all" if args.all_tree_species else args.tree_mode
    tree_render_budget = configure_exact_tree_render_budget(tree_mode)

    manifest_path = output_dir / "render_progress.json"
    completed: list[int] = []
    skipped: list[int] = []
    frame_times: dict[str, float] = {}
    started = time.monotonic()
    payload = {
        "schema": "agent.full13.dynamic_render.v1",
        "status": "RUNNING",
        "created_utc": utc_now(),
        "blend": bpy.data.filepath,
        "frame_start": start,
        "frame_end": end,
        "requested_frames": selected_frames,
        "resolution": [args.resolution_x, args.resolution_y],
        "samples": args.samples,
        "engine": scene.render.engine,
        "workbench_material_bridge": material_bridge,
        "tree_render_budget": tree_render_budget,
        "completed": completed,
        "skipped_existing": skipped,
        "frame_seconds": frame_times,
    }
    write_atomic(manifest_path, payload)

    for frame in selected_frames:
        target = output_dir / f"frame_{frame:04d}.png"
        if (
            valid_png(target, args.resolution_x, args.resolution_y)
            and not args.overwrite
        ):
            skipped.append(frame)
            print(f"[full13-dynamic-render] skip existing frame={frame}", flush=True)
            continue
        scene.frame_set(frame)
        scene.render.filepath = str(target)
        frame_started = time.monotonic()
        bpy.ops.render.render(write_still=True)
        elapsed = time.monotonic() - frame_started
        if not valid_png(target, args.resolution_x, args.resolution_y):
            raise RuntimeError(f"Frame {frame} did not produce a valid PNG: {target}")
        completed.append(frame)
        frame_times[str(frame)] = round(elapsed, 3)
        payload["updated_utc"] = utc_now()
        payload["elapsed_seconds"] = round(time.monotonic() - started, 3)
        write_atomic(manifest_path, payload)
        print(
            f"[full13-dynamic-render] frame={frame}/{end} seconds={elapsed:.2f}",
            flush=True,
        )

    missing = [
        frame
        for frame in selected_frames
        if not valid_png(
            output_dir / f"frame_{frame:04d}.png", args.resolution_x, args.resolution_y
        )
    ]
    payload["status"] = "PASS" if not missing else "FAIL"
    payload["missing"] = missing
    payload["finished_utc"] = utc_now()
    payload["elapsed_seconds"] = round(time.monotonic() - started, 3)
    write_atomic(manifest_path, payload)
    if missing:
        raise RuntimeError(f"Missing or invalid rendered frames: {missing}")
    print(f"[full13-dynamic-render] PASS frames={start}..{end}", flush=True)


if __name__ == "__main__":
    main()

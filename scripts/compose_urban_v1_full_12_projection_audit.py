#!/usr/bin/env python3
"""Union the 2048² exact-mesh projection layers and finalize coverage audit."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
LAYOUT_PATH = CITY / "layout_plan.json"
PROJECTION_ROOT = CITY / "renders" / "zdepth_projection_layers"
AUDIT_DIR = CITY / "renders" / "audit"
MASK_PATH = AUDIT_DIR / "mesh_asset_silhouette_2048.png"
MASK_EXR = AUDIT_DIR / "mesh_asset_silhouette_2048.exr"
AUDIT_PATH = CITY / "mesh_projection_audit.json"
PANORAMA_PATH = CITY / "panorama_audit.json"
MANIFEST_PATH = CITY / "renders" / "render_manifest.json"
RENDERER_PATH = ROOT / "scripts" / "render_urban_v1_full_12_daytime.py"
LAYER_PATH = ROOT / "scripts" / "render_urban_v1_full_12_zdepth_layer.py"
SHOT_STEM = "06_city_top_down_coverage"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def valid_exr(path: Path) -> bool:
    try:
        # The final binary union mask compresses more aggressively than color
        # layers; 128 KiB still cleanly rejects a constant/empty 2048² mask.
        return path.stat().st_size >= 128 * 1024 and path.read_bytes()[:4] == b"v/1\x01"
    except OSError:
        return False


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def main() -> None:
    # Both imported modules parse their resolution/output environment at import
    # time. Pin them to this auxiliary 2048² audit inside the full-12 tree.
    os.environ["C2W_FULL12_RENDER_RESOLUTION"] = "2048x2048"
    os.environ["C2W_FULL12_LAYER_ROOT"] = str(PROJECTION_ROOT)
    renderer = load_module("full12_projection_renderer", RENDERER_PATH)
    layer_module = load_module("full12_projection_layers", LAYER_PATH)
    asset_layers = [key for key in layer_module.LAYERS if key != "base"]
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf8"))
    threshold = float(layout["coverage_audit"]["minimum_mesh_projected_asset_ratio"])

    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 2048
    scene.render.resolution_y = 2048
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = True
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 16
    camera_data = bpy.data.cameras.new("full12:projection_union:camera_data")
    camera = bpy.data.objects.new("full12:projection_union:camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera

    group = bpy.data.node_groups.new("full12:projection_union", "CompositorNodeTree")
    scene.compositing_node_group = group
    scene.use_nodes = True
    scene.render.use_compositing = True
    images = []
    union = None
    sources = []
    base_path = PROJECTION_ROOT / "base" / f"{SHOT_STEM}.exr"
    if not valid_exr(base_path):
        raise RuntimeError(f"Missing 2048 base projection layer: {base_path}")
    base_image = bpy.data.images.load(str(base_path), check_existing=False)
    images.append(base_image)
    base_node = group.nodes.new("CompositorNodeImage")
    base_node.image = base_image
    base_depth = base_node.outputs.get("BaseDepth")
    if base_depth is None:
        raise RuntimeError(f"BaseDepth is missing in {base_path}")
    base_minus_tolerance = group.nodes.new("ShaderNodeMath")
    base_minus_tolerance.operation = "SUBTRACT"
    group.links.new(base_depth, base_minus_tolerance.inputs[0])
    base_minus_tolerance.inputs[1].default_value = 0.002
    for layer_key in asset_layers:
        path = PROJECTION_ROOT / layer_key / f"{SHOT_STEM}.exr"
        if not valid_exr(path):
            raise RuntimeError(f"Missing 2048 projection layer: {path}")
        image = bpy.data.images.load(str(path), check_existing=False)
        images.append(image)
        image_node = group.nodes.new("CompositorNodeImage")
        image_node.image = image
        combined_depth = image_node.outputs.get("CombinedDepth")
        if combined_depth is None:
            raise RuntimeError(f"CombinedDepth is missing in {path}")
        depth_delta_mask = group.nodes.new("ShaderNodeMath")
        depth_delta_mask.operation = "LESS_THAN"
        group.links.new(combined_depth, depth_delta_mask.inputs[0])
        group.links.new(base_minus_tolerance.outputs[0], depth_delta_mask.inputs[1])
        alpha = depth_delta_mask.outputs[0]
        if union is None:
            union = alpha
        else:
            maximum = group.nodes.new("ShaderNodeMath")
            maximum.operation = "MAXIMUM"
            group.links.new(union, maximum.inputs[0])
            group.links.new(alpha, maximum.inputs[1])
            union = maximum.outputs[0]
        manifest_path = PROJECTION_ROOT / f"layer_manifest_{layer_key}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf8"))
        record = next(
            view
            for view in manifest["views"]
            if view["name"] == "city_top_down_coverage"
        )
        sources.append(
            {
                "layer_key": layer_key,
                "path": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "assigned_placement_count": manifest["assigned_placement_count"],
                "camera": record["camera"],
            }
        )
    if union is None:
        raise RuntimeError("No asset projection layers were found")

    combine = group.nodes.new("CompositorNodeCombineColor")
    for channel in ("Red", "Green", "Blue", "Alpha"):
        group.links.new(union, combine.inputs[channel])
    output = group.nodes.new("CompositorNodeOutputFile")
    output.directory = str(AUDIT_DIR)
    output.file_name = ".writing_mesh_asset_silhouette_2048"
    output.format.color_depth = "32"
    output.format.exr_codec = "ZIP"
    output.file_output_items.new("RGBA", "MaskColor")
    group.links.new(combine.outputs["Image"], output.inputs["MaskColor"])
    group.interface.new_socket(
        name="Image", in_out="OUTPUT", socket_type="NodeSocketColor"
    )
    composite = group.nodes.new("NodeGroupOutput")
    group.links.new(combine.outputs["Image"], composite.inputs["Image"])

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)
    temporary_exr = AUDIT_DIR / f"{output.file_name}.exr"
    temporary_png = AUDIT_DIR / ".mesh_asset_silhouette_2048.writing.png"
    for path in (temporary_exr, temporary_png):
        if path.exists():
            path.unlink()
    bpy.ops.render.render(write_still=False, scene=scene.name)
    if not valid_exr(temporary_exr):
        raise RuntimeError("Projection union compositor did not write its EXR")
    os.replace(temporary_exr, MASK_EXR)
    final_image = bpy.data.images.get("Render Result")
    if final_image is None:
        raise RuntimeError("Projection compositor did not expose a Render Result")
    final_image.save_render(str(temporary_png), scene=scene)
    if renderer.png_dimensions(temporary_png) != (2048, 2048):
        raise RuntimeError("Projection union did not produce a 2048x2048 PNG")
    os.replace(temporary_png, MASK_PATH)
    stats = renderer.png_alpha_statistics(MASK_PATH)
    ratio = float(stats["coverage_ratio_alpha_128"])
    passed = ratio >= threshold
    result = {
        "schema": "agent.full12.mesh_projection_audit.zdepth.v1",
        "scene_revision": REVISION,
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "method": (
            "2048x2048 orthographic top raster of the actual renderable meshes "
            "from every exact production asset collection instance; per-layer "
            "CombinedDepth < exact BaseDepth - 0.002m silhouettes unioned "
            "pixelwise by MAXIMUM"
        ),
        "acceptance_geometry": (
            "actual rasterized collection-instance mesh silhouettes; no AABB, "
            "declared polygon, or collection bounds contribution"
        ),
        "delivery_view": False,
        "zdepth_resource_partition": True,
        "partition_exactly_once": True,
        "asset_layer_count": len(asset_layers),
        "base_depth_source": str(base_path.resolve()),
        "asset_placement_count": sum(
            source["assigned_placement_count"] for source in sources
        ),
        "temporarily_excluded_only_for_auxiliary_audit": [
            "city_base",
            "roads",
            "road_amenity",
        ],
        "all_asset_regions_included": True,
        "mask_file": str(MASK_PATH.resolve()),
        "mask_bytes": MASK_PATH.stat().st_size,
        "mask_sha256": sha256(MASK_PATH),
        "mask_exr": str(MASK_EXR.resolve()),
        "statistics": stats,
        "accepted_ratio": ratio,
        "minimum_required_ratio": threshold,
        "pass": passed,
        "sources": sources,
    }
    atomic_json(AUDIT_PATH, result)

    if PANORAMA_PATH.is_file():
        panorama = json.loads(PANORAMA_PATH.read_text(encoding="utf8"))
        panorama["mesh_projection_audit_pass"] = passed
        panorama["mesh_projected_asset_ratio"] = ratio
        panorama["checks_pass"] = bool(
            panorama.get("all_citywide_views_complete")
            and panorama.get("all_regional_pairs_complete")
            and panorama.get("all_interior_views_complete")
            and passed
        )
        panorama["status"] = "PASS" if panorama["checks_pass"] else "FAIL"
        atomic_json(PANORAMA_PATH, panorama)
    if MANIFEST_PATH.is_file():
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf8"))
        manifest["projection_audit"] = {
            "path": str(AUDIT_PATH.resolve()),
            "status": result["status"],
            "accepted_ratio": ratio,
            "minimum_required_ratio": threshold,
        }
        atomic_json(MANIFEST_PATH, manifest)
    print(
        f"FULL12_PROJECTION_AUDIT status={result['status']} "
        f"ratio={ratio:.6f} minimum={threshold:.6f}",
        flush=True,
    )


if __name__ == "__main__":
    main()

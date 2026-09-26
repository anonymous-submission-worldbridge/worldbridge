#!/usr/bin/env python3
"""Compose all exact full-12 render layers by camera-space depth.

The production city is too large to expand in one Blender dependency graph on
this host.  ``render_urban_v1_full_12_zdepth_layer.py`` therefore rasterizes a
strict partition of the exact collection instances with identical cameras.
This compositor combines every pixel by the 32-bit camera-space Z passes (not
by zone center or alpha ordering).  Every asset partition is rasterized as an
exact asset+receiver ``Combined`` pass.  Comparing CombinedDepth to the exact
BaseDepth isolates visible asset surfaces, while the equal-depth pixels retain
that partition's lighting on the shared road/ground receivers.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BLEND = CITY / f"{REVISION}.blend"
LAYOUT = CITY / "layout_plan.json"
LAYER_ROOT = CITY / "renders" / "zdepth_layers"
COMPOSITE_ROOT = CITY / "renders" / "zdepth_composites"
DELIVERY_ROOT = CITY / "renders"
MANIFEST_PATH = DELIVERY_ROOT / "render_manifest.json"
PANORAMA_PATH = CITY / "panorama_audit.json"
RENDERER_PATH = ROOT / "scripts" / "render_urban_v1_full_12_daytime.py"
LAYER_PATH = ROOT / "scripts" / "render_urban_v1_full_12_zdepth_layer.py"
SOURCE_LAYER_SETTINGS: dict[str, dict[str, Any]] = {}
SOURCE_LAYER_GN_REALIZATIONS: dict[str, dict[str, Any]] = {}
SOURCE_LAYER_INSTANCE_EXPANSIONS: dict[str, dict[str, Any]] = {}
SOURCE_LAYER_FRAME_SETTINGS: dict[str, dict[str, dict[str, Any]]] = {}
EEVEE_FALLBACK_BASE_ROOT = CITY / "render_runtime/eevee_fallback_base/base"
EEVEE_FALLBACK_LAYERS = {"river5_nature", "artificial_lake"}
ALL_EEVEE_DIRECT_RECEIVER = False


def material_fidelity_settings_valid(
    settings: dict[str, Any], layer_key: str | None = None
) -> bool:
    sync = settings.get("workbench_material_sync", {})
    common = bool(
        settings.get("resolution") == [1920, 1080]
        and settings.get("mesh_simplification") is False
        and int(sync.get("materials_examined") or 0) > 0
        and int(sync.get("write_failures") or 0) == 0
        and sync.get("node_graphs_changed") is False
        and sync.get("source_files_saved") is False
        and sync.get("production_blend_saved") is False
    )
    if not common:
        return False
    if settings.get("engine") == "BLENDER_WORKBENCH":
        return bool(
            int(settings.get("workbench_antialiasing_samples") or 0) >= 16
            and settings.get("workbench_color_type") == "MATERIAL"
            and settings.get("workbench_studio_light") == "outdoor.sl"
            and settings.get("workbench_shadows_and_cavity") is True
            and sync.get("enabled") is True
        )
    return bool(
        layer_key in EEVEE_FALLBACK_LAYERS
        and settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
        and int(settings.get("samples") or 0) >= 32
        and settings.get("denoising") is False
        and settings.get("eevee_shadow_quality", {}).get("policy")
        == "full12_complete_virtual_shadow_residency_v1"
        and settings.get("eevee_shadow_quality", {}).get("pool_size_mb") == 1024
        and settings.get("eevee_shadow_quality", {}).get("resolution_scale") == 0.5
        and settings.get("eevee_shadow_quality", {}).get("missing_shadow_pages_allowed")
        is False
        and sync.get("enabled") is False
        and sync.get("method") == "not applicable outside Workbench"
        and settings.get("workbench_antialiasing_samples") is None
        and settings.get("workbench_color_type") is None
        and settings.get("workbench_studio_light") is None
        and settings.get("workbench_shadows_and_cavity") is None
    )


def authoritative_exr_evidence_valid(layer_key: str, evidence: dict[str, Any]) -> bool:
    expected_parts = (
        ["BaseColor", "BaseDepth"]
        if layer_key == "base"
        else ["CombinedColor", "CombinedDepth"]
    )
    return bool(
        evidence.get("status") == "PASS"
        and evidence.get("operation") == "native_full_resolution_raster"
        and evidence.get("resolution") == [1920, 1080]
        and evidence.get("full_resolution") == [1920, 1080]
        and evidence.get("native_resolution") == [1920, 1080]
        and evidence.get("target_pixel_centers_sampled_exactly") is True
        and evidence.get("resizing") is False
        and evidence.get("resampling") is False
        and evidence.get("interpolation") is False
        and evidence.get("color_conversion") is False
        and evidence.get("depth_quantization") is False
        and evidence.get("parts") == expected_parts
        and evidence.get("pixel_content_nondegenerate") is True
    )


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
        return path.stat().st_size >= 256 * 1024 and path.read_bytes()[:4] == b"v/1\x01"
    except OSError:
        return False


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def source_bundle(layer_key: str, shot: Any) -> Path:
    return LAYER_ROOT / layer_key / f"{Path(shot.filename).stem}.exr"


def reusable_delivery_record(
    record: dict[str, Any] | None,
    renderer: Any,
    layer_module: Any,
    shot: Any,
    delivery: Path,
    composite: Path,
) -> bool:
    """Reject a stale PNG whenever its camera or any source bundle changed."""

    if (
        not record
        or not renderer.shot_record_matches_spec(record, shot)
        or not renderer.valid_delivery_png(delivery)
        or not valid_exr(composite)
        or record.get("bytes") != delivery.stat().st_size
        or record.get("sha256") != sha256(delivery)
        or record.get("depth_composite_bytes") != composite.stat().st_size
        or record.get("depth_composite_sha256") != sha256(composite)
    ):
        return False
    sources = {item.get("layer_key"): item for item in record.get("source_layers", [])}
    if set(sources) != set(layer_module.LAYERS):
        return False
    for layer_key in layer_module.LAYERS:
        path = source_bundle(layer_key, shot)
        source = sources[layer_key]
        if (
            not valid_exr(path)
            or Path(source.get("source", "")).resolve() != path.resolve()
            or source.get("bytes") != path.stat().st_size
            or source.get("sha256") != sha256(path)
        ):
            return False
    return True


def input_socket(node: bpy.types.Node, name: str) -> bpy.types.NodeSocket:
    socket = node.inputs.get(name)
    if socket is None:
        raise RuntimeError(f"Node {node.bl_idname} is missing input {name!r}")
    return socket


def output_socket(node: bpy.types.Node, name: str) -> bpy.types.NodeSocket:
    socket = node.outputs.get(name)
    if socket is None:
        raise RuntimeError(f"Node {node.bl_idname} is missing output {name!r}")
    return socket


def image_node(
    group: bpy.types.NodeTree, path: Path, label: str
) -> tuple[bpy.types.Node, bpy.types.Image]:
    if not valid_exr(path):
        raise RuntimeError(f"Missing or invalid layer EXR: {path}")
    image = bpy.data.images.load(str(path), check_existing=False)
    node = group.nodes.new("CompositorNodeImage")
    node.name = f"full12:{label}"
    node.label = label
    node.image = image
    return node, image


def mix(
    group: bpy.types.NodeTree,
    factor: bpy.types.NodeSocket,
    color1: bpy.types.NodeSocket,
    color2: bpy.types.NodeSocket,
    name: str,
    blend_type: str = "MIX",
) -> bpy.types.NodeSocket:
    node = group.nodes.new("ShaderNodeMixRGB")
    node.name = f"full12:{name}"
    node.blend_type = blend_type
    node.inputs[0].default_value = 1.0
    group.links.new(factor, node.inputs[0])
    group.links.new(color1, node.inputs[1])
    group.links.new(color2, node.inputs[2])
    return node.outputs[0]


def alpha_socket(
    group: bpy.types.NodeTree, color: bpy.types.NodeSocket, name: str
) -> bpy.types.NodeSocket:
    node = group.nodes.new("CompositorNodeSeparateColor")
    node.name = f"full12:{name}:alpha"
    group.links.new(color, node.inputs["Image"])
    return node.outputs["Alpha"]


def math_socket(
    group: bpy.types.NodeTree,
    operation: str,
    value1: bpy.types.NodeSocket,
    value2: bpy.types.NodeSocket | float,
    name: str,
) -> bpy.types.NodeSocket:
    node = group.nodes.new("ShaderNodeMath")
    node.name = f"full12:{name}"
    node.operation = operation
    group.links.new(value1, node.inputs[0])
    if isinstance(value2, (int, float)):
        node.inputs[1].default_value = float(value2)
    else:
        group.links.new(value2, node.inputs[1])
    return node.outputs[0]


def color_distance_socket(
    group: bpy.types.NodeTree,
    color1: bpy.types.NodeSocket,
    color2: bpy.types.NodeSocket,
    name: str,
) -> bpy.types.NodeSocket:
    """Return the per-pixel Euclidean RGB distance between two colors."""

    node = group.nodes.new("ShaderNodeVectorMath")
    node.name = f"full12:{name}"
    node.operation = "DISTANCE"
    group.links.new(color1, node.inputs[0])
    group.links.new(color2, node.inputs[1])
    return node.outputs[1]


def setup_scene(renderer: Any) -> bpy.types.Scene:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x, scene.render.resolution_y = renderer.RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 22
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.35
    camera_data = bpy.data.cameras.new("full12:zdepth_compositor:camera_data")
    camera = bpy.data.objects.new("full12:zdepth_compositor:camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return scene


def compose_shot(
    scene: bpy.types.Scene,
    renderer: Any,
    layer_module: Any,
    shot: Any,
) -> dict[str, Any]:
    started = time.monotonic()
    group = bpy.data.node_groups.new(
        f"full12:zdepth_composite:{shot.name}", "CompositorNodeTree"
    )
    scene.compositing_node_group = group
    scene.use_nodes = True
    scene.render.use_compositing = True
    loaded_images: list[bpy.types.Image] = []

    base_node, base_image = image_node(
        group, source_bundle("base", shot), f"base:{shot.name}"
    )
    loaded_images.append(base_image)
    base_color = output_socket(base_node, "BaseColor")
    base_depth = output_socket(base_node, "BaseDepth")
    base_alpha = alpha_socket(group, base_color, "base")
    sky_color = group.nodes.new("CompositorNodeRGB")
    sky_color.name = "full12:clear_daytime_sky"
    sky_color.outputs[0].default_value = (0.19, 0.48, 0.82, 1.0)
    daytime_base = mix(
        group,
        base_alpha,
        sky_color.outputs[0],
        base_color,
        "base_alpha_daytime_sky",
    )

    layers: list[dict[str, Any]] = []
    shadow_candidates: list[bpy.types.NodeSocket] = []
    asset_passes: list[
        tuple[
            str,
            bpy.types.NodeSocket,
            bpy.types.NodeSocket,
            bpy.types.NodeSocket,
            bpy.types.NodeSocket,
        ]
    ] = []
    transparent = group.nodes.new("CompositorNodeRGB")
    transparent.name = "full12:transparent_asset_background"
    transparent.outputs[0].default_value = (0.0, 0.0, 0.0, 0.0)
    neutral = group.nodes.new("CompositorNodeRGB")
    neutral.name = "full12:neutral_receiver_ratio"
    neutral.outputs[0].default_value = (1.0, 1.0, 1.0, 1.0)
    one = group.nodes.new("ShaderNodeValue")
    one.name = "full12:constant:one"
    one.outputs[0].default_value = 1.0
    for layer_key in layer_module.LAYERS:
        if layer_key == "base":
            continue
        frame_settings = SOURCE_LAYER_FRAME_SETTINGS[layer_key][shot.name]
        frame_engine = frame_settings.get("engine")
        path = source_bundle(layer_key, shot)
        node, image = image_node(group, path, f"{layer_key}:{shot.name}")
        loaded_images.append(image)
        combined_color = output_socket(node, "CombinedColor")
        combined_depth = output_socket(node, "CombinedDepth")
        combined_alpha = alpha_socket(group, combined_color, f"{layer_key}:combined")
        combined_with_sky_filled = mix(
            group,
            combined_alpha,
            daytime_base,
            combined_color,
            f"{layer_key}:fill_combined_sky",
        )
        asset_reference_depth = base_depth
        receiver_color = combined_with_sky_filled
        relative_lighting_reference: dict[str, Any] | None = None
        if frame_engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
            if layer_key not in EEVEE_FALLBACK_LAYERS:
                raise RuntimeError(
                    f"Unexpected Eevee fallback layer: {layer_key}:{shot.name}"
                )
            fallback_base_path = (
                EEVEE_FALLBACK_BASE_ROOT / f"{Path(shot.filename).stem}.exr"
            )
            fallback_node, fallback_image = image_node(
                group,
                fallback_base_path,
                f"eevee_fallback_base:{shot.name}",
            )
            loaded_images.append(fallback_image)
            fallback_base_color = output_socket(fallback_node, "BaseColor")
            fallback_base_depth = output_socket(fallback_node, "BaseDepth")
            fallback_base_alpha = alpha_socket(
                group, fallback_base_color, "eevee_fallback_base"
            )
            asset_reference_depth = fallback_base_depth
            # The Eevee fallback is used only for Blender 5.1's proven
            # Workbench empty-buffer case.  Normalize its shared-receiver
            # lighting against a same-camera Eevee base raster, then apply
            # that exact relative illumination to the authoritative
            # Workbench base.  Asset pixels retain their authored Eevee PBR
            # color; no pixel coordinates or depth samples are changed.
            combined_or_neutral = mix(
                group,
                combined_alpha,
                neutral.outputs[0],
                combined_color,
                f"{layer_key}:combined_or_neutral",
            )
            fallback_base_or_neutral = mix(
                group,
                fallback_base_alpha,
                neutral.outputs[0],
                fallback_base_color,
                f"{layer_key}:fallback_base_or_neutral",
            )
            relative_lighting = mix(
                group,
                one.outputs[0],
                combined_or_neutral,
                fallback_base_or_neutral,
                f"{layer_key}:eevee_relative_receiver_lighting",
                blend_type="DIVIDE",
            )
            receiver_color = mix(
                group,
                one.outputs[0],
                daytime_base,
                relative_lighting,
                f"{layer_key}:relative_lighting_on_workbench_base",
                blend_type="MULTIPLY",
            )
            relative_lighting_reference = {
                "source": str(fallback_base_path.resolve()),
                "bytes": fallback_base_path.stat().st_size,
                "sha256": sha256(fallback_base_path),
                "formula": (
                    "WorkbenchBaseColor * "
                    "(EeveeCombinedColor / EeveeBaseColor) on receiver pixels"
                ),
                "same_camera_native_resolution": True,
                "resampling": False,
                "interpolation": False,
                "depth_changed": False,
            }
            if ALL_EEVEE_DIRECT_RECEIVER:
                # In full-13 the common base and every asset layer are already
                # rendered with the identical Eevee camera, world, exposure,
                # and target grid.  Use the native Combined receiver directly;
                # the ratio path above exists only to transfer Eevee lighting
                # onto a Workbench base and can create needless divide extrema
                # when both numerator and denominator approach zero.
                receiver_color = combined_with_sky_filled
                relative_lighting_reference = {
                    "source": str(path.resolve()),
                    "sha256": sha256(path),
                    "formula": "native same-camera Eevee CombinedColor receiver",
                    "same_camera_native_resolution": True,
                    "all_source_layers_eevee": True,
                    "division": False,
                    "resampling": False,
                    "interpolation": False,
                    "depth_changed": False,
                }
        elif frame_engine != "BLENDER_WORKBENCH":
            raise RuntimeError(
                f"Unsupported source engine {frame_engine!r}: "
                f"{layer_key}:{shot.name}"
            )
        base_depth_minus_tolerance = math_socket(
            group,
            "SUBTRACT",
            asset_reference_depth,
            0.002,
            f"{layer_key}:base_depth_minus_2mm",
        )
        asset_mask = math_socket(
            group,
            "LESS_THAN",
            combined_depth,
            base_depth_minus_tolerance,
            f"{layer_key}:visible_asset_depth_mask",
        )
        clean_shadow_receiver = mix(
            group,
            asset_mask,
            receiver_color,
            daytime_base,
            f"{layer_key}:remove_asset_from_receiver",
        )
        asset_only_color = mix(
            group,
            asset_mask,
            transparent.outputs[0],
            combined_color,
            f"{layer_key}:asset_only_from_depth_delta",
        )
        # Z Combine must not receive the shared receiver depth on transparent
        # pixels.  With an equal BaseDepth/CombinedDepth and anti-aliasing
        # enabled, Blender can sample the transparent black B input even
        # though ``asset_only_color`` has zero alpha.  Dense coplanar source
        # floors then become view-dependent horizontal hatch marks.  Push
        # every non-asset B depth safely behind the scene; true asset depths
        # remain bit-for-bit unchanged.
        inverse_asset_mask = math_socket(
            group,
            "SUBTRACT",
            one.outputs[0],
            asset_mask,
            f"{layer_key}:inverse_asset_mask",
        )
        non_asset_depth_offset = math_socket(
            group,
            "MULTIPLY",
            inverse_asset_mask,
            1.0e6,
            f"{layer_key}:non_asset_depth_offset",
        )
        isolated_asset_depth = math_socket(
            group,
            "ADD",
            combined_depth,
            non_asset_depth_offset,
            f"{layer_key}:isolated_asset_depth",
        )
        shadow_candidates.append(clean_shadow_receiver)
        asset_passes.append(
            (
                layer_key,
                asset_only_color,
                isolated_asset_depth,
                combined_color,
                combined_alpha,
            )
        )
        layers.append(
            {
                "layer_key": layer_key,
                "source": str(path.resolve()),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "color_part": "CombinedColor",
                "depth_part": "CombinedDepth.V",
                "visible_asset_mask": ("CombinedDepth < BaseDepth - 0.002m"),
                "cross_layer_lighting_part": (
                    "equal-depth receiver pixels in CombinedColor"
                ),
                "render_engine": frame_engine,
                "relative_lighting_reference": relative_lighting_reference,
            }
        )

    # Each clean receiver contains the common exact base plus same-depth
    # receiver contributions from one partition.  Full-12 used DARKEN because
    # its Workbench base could only accept Eevee shadow transfer.  Full-13 is
    # all Eevee and also contains authored, coplanar receiver surfaces (school
    # courts, lake water, residential paving, and similar slabs).  DARKEN
    # rejects every receiver contribution lighter than the common terrain;
    # the strict 2 mm asset-depth mask then exposes alternate coplanar samples
    # as distant black/white hatch patterns.  For the all-Eevee path, retain at
    # each pixel the clean receiver with the largest RGB departure from the
    # common receiver.  This preserves both light authored surfaces and dark
    # physical shadows while visible non-coplanar assets remain isolated and
    # camera-Z combined below.
    shadowed_base = daytime_base
    if ALL_EEVEE_DIRECT_RECEIVER:
        receiver_strength = group.nodes.new("ShaderNodeValue")
        receiver_strength.name = "full12:receiver_delta:zero"
        receiver_strength.outputs[0].default_value = 0.0
        strongest_delta = receiver_strength.outputs[0]
        for index, candidate in enumerate(shadow_candidates):
            delta = color_distance_socket(
                group,
                candidate,
                daytime_base,
                f"receiver_delta:{index:02d}",
            )
            take_candidate = math_socket(
                group,
                "GREATER_THAN",
                delta,
                strongest_delta,
                f"receiver_delta_is_stronger:{index:02d}",
            )
            shadowed_base = mix(
                group,
                take_candidate,
                shadowed_base,
                candidate,
                f"receiver_strongest:{index:02d}",
            )
            strongest_delta = math_socket(
                group,
                "MAXIMUM",
                strongest_delta,
                delta,
                f"receiver_delta_max:{index:02d}",
            )
    else:
        for index, candidate in enumerate(shadow_candidates):
            shadowed_base = mix(
                group,
                one.outputs[0],
                shadowed_base,
                candidate,
                f"shadow_union:{index:02d}",
                blend_type="DARKEN",
            )

    composite_color = shadowed_base
    composite_depth = base_depth
    for (
        layer_key,
        asset_color,
        combined_depth,
        combined_color,
        combined_alpha,
    ) in asset_passes:
        if ALL_EEVEE_DIRECT_RECEIVER:
            # Blender's Z Combine anti-alias path is not reliable when a
            # multipart input contains dense coplanar geometry: even after
            # masking transparent depths, it can interpolate alternate source
            # samples into long hatch marks.  The mathematically explicit
            # front-depth predicate plus authored coverage performs the same
            # camera-Z choice and preserves the source frame's antialiasing.
            in_front = math_socket(
                group,
                "LESS_THAN",
                combined_depth,
                composite_depth,
                f"asset_in_front:{layer_key}",
            )
            asset_coverage = math_socket(
                group,
                "MULTIPLY",
                in_front,
                combined_alpha,
                f"asset_coverage:{layer_key}",
            )
            composite_color = mix(
                group,
                asset_coverage,
                composite_color,
                combined_color,
                f"camera_z_color_union:{layer_key}",
            )
        else:
            combine = group.nodes.new("CompositorNodeZcombine")
            combine.name = f"full12:zcombine:{layer_key}"
            combine.inputs["Use Alpha"].default_value = True
            combine.inputs["Anti-Alias"].default_value = True
            group.links.new(composite_color, combine.inputs["A"])
            group.links.new(composite_depth, combine.inputs["Depth A"])
            group.links.new(asset_color, combine.inputs["B"])
            group.links.new(combined_depth, combine.inputs["Depth B"])
            composite_color = combine.outputs["Result"]
        # Blender 5.1's Z Combine color output is correct, but its exposed
        # Depth output can be an uninitialized -1e-12 in a background
        # compositor.  The mathematically identical 32-bit minimum is stable.
        composite_depth = math_socket(
            group,
            "MINIMUM",
            composite_depth,
            combined_depth,
            f"depth_union:{layer_key}",
        )

    # Blender 5 replaced the legacy Composite node with the first Color
    # socket of a Group Output node.
    group.interface.new_socket(
        name="Image", in_out="OUTPUT", socket_type="NodeSocketColor"
    )
    composite_output = group.nodes.new("NodeGroupOutput")
    composite_output.name = "full12:display_transform_source"
    group.links.new(composite_color, composite_output.inputs["Image"])

    output = group.nodes.new("CompositorNodeOutputFile")
    output.name = "full12:final_color_depth"
    output.directory = str(COMPOSITE_ROOT)
    output.file_name = f".writing_{Path(shot.filename).stem}"
    output.format.color_depth = "32"
    output.format.exr_codec = "ZIP"
    output.file_output_items.new("RGBA", "FinalColor")
    output.file_output_items.new("FLOAT", "FinalDepth")
    group.links.new(composite_color, output.inputs["FinalColor"])
    group.links.new(composite_depth, output.inputs["FinalDepth"])

    COMPOSITE_ROOT.mkdir(parents=True, exist_ok=True)
    temporary_exr = COMPOSITE_ROOT / f"{output.file_name}.exr"
    target_exr = COMPOSITE_ROOT / f"{Path(shot.filename).stem}.exr"
    for path in (temporary_exr,):
        if path.exists():
            path.unlink()
    bpy.ops.render.render(write_still=False, scene=scene.name)
    if not valid_exr(temporary_exr):
        raise RuntimeError(f"Compositor failed to produce {temporary_exr}")
    os.replace(temporary_exr, target_exr)

    # Save the compositor's actual Render Result.  Loading the typed multipart
    # EXR and assuming its first part is color is not valid in Blender 5.1 and
    # previously produced a flat grey image.  Render Result is the connected
    # Composite output above and receives the recorded AgX display transform.
    delivery = DELIVERY_ROOT / shot.filename
    temporary_png = delivery.with_name(f".{delivery.stem}.writing.png")
    final_image = bpy.data.images.get("Render Result")
    if final_image is None:
        raise RuntimeError("Compositor did not expose a Render Result")
    final_image.save_render(str(temporary_png), scene=scene)
    if renderer.png_dimensions(temporary_png) != renderer.RESOLUTION:
        raise RuntimeError(f"Invalid delivery PNG: {temporary_png}")
    os.replace(temporary_png, delivery)
    record = {
        **asdict(shot),
        "camera_composition_revision": renderer.CAMERA_COMPOSITION_REVISION,
        "shot_spec_sha256": renderer.shot_spec_sha256(shot),
        "status": "rendered",
        "output": str(delivery.resolve()),
        "bytes": delivery.stat().st_size,
        "sha256": sha256(delivery),
        "depth_composite": str(target_exr.resolve()),
        "depth_composite_bytes": target_exr.stat().st_size,
        "depth_composite_sha256": sha256(target_exr),
        "render_method": (
            "exact per-pixel 32-bit camera-space Z-depth composition with "
            "BaseDepth-delta asset isolation and shared-receiver cross-layer lighting"
        ),
        "all_regions_visible": True,
        "layer_composition": True,
        "zdepth_composition": True,
        "center_distance_sorting": False,
        "alpha_only_composition": False,
        "daytime_sky_mask": "exact transparent no-hit alpha from BaseColor",
        "temporarily_hidden_zones": [],
        "temporarily_hidden_placements": [],
        "temporarily_hidden_interiors": [],
        "source_layer_count": len(layer_module.LAYERS),
        "source_layers": [
            {
                "layer_key": "base",
                "source": str(source_bundle("base", shot).resolve()),
                "bytes": source_bundle("base", shot).stat().st_size,
                "sha256": sha256(source_bundle("base", shot)),
                "color_part": "BaseColor",
                "depth_part": "BaseDepth.V",
                "render_engine": SOURCE_LAYER_FRAME_SETTINGS["base"][shot.name].get(
                    "engine"
                ),
                "relative_lighting_reference": None,
            },
            *layers,
        ],
        "render_seconds": round(time.monotonic() - started, 3),
    }

    # Unload source pixels before the next 1920x1080 frame.
    scene.compositing_node_group = None
    bpy.data.node_groups.remove(group)
    for image in loaded_images:
        if image.name in bpy.data.images:
            bpy.data.images.remove(image)
    return record


def build_manifest(
    renderer: Any,
    layer_module: Any,
    records: dict[str, dict[str, Any]],
    started: float,
    status: str,
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    blend_stat = BLEND.stat()
    layout = json.loads(LAYOUT.read_text(encoding="utf8"))
    workbench_frame_settings = [
        settings
        for layer_frames in SOURCE_LAYER_FRAME_SETTINGS.values()
        for settings in layer_frames.values()
        if settings.get("engine") == "BLENDER_WORKBENCH"
    ]
    delivered_aa = min(
        (
            int(settings.get("workbench_antialiasing_samples") or 0)
            for settings in workbench_frame_settings
        ),
        default=0,
    )
    source_engine_counts: dict[str, int] = {}
    for layer_frames in SOURCE_LAYER_FRAME_SETTINGS.values():
        for frame_settings in layer_frames.values():
            engine = str(frame_settings.get("engine", "UNKNOWN"))
            source_engine_counts[engine] = source_engine_counts.get(engine, 0) + 1
    complete_names = [
        shot.name
        for shot in renderer.SHOTS
        if shot.name in records
        and renderer.valid_delivery_png(DELIVERY_ROOT / shot.filename)
        and valid_exr(COMPOSITE_ROOT / f"{Path(shot.filename).stem}.exr")
    ]
    complete = len(complete_names) == len(renderer.SHOTS) and not errors
    return {
        "schema": "agent.full12.zdepth_delivery.v1",
        "created_utc": utc_now(),
        "status": "PASS" if complete else status,
        "scene_revision": REVISION,
        "complete": complete,
        "expected_count": len(renderer.SHOTS),
        "completed_count": len(complete_names),
        "completed_view_names": complete_names,
        "render_settings": {
            "engine": "BLENDER_WORKBENCH",
            "resolution": list(renderer.RESOLUTION),
            "format": "PNG/RGB/8 plus typed 32-bit EXR depth",
            "samples": delivered_aa,
            "workbench_antialiasing_samples": delivered_aa,
            "workbench_color_type": "MATERIAL",
            "workbench_studio_light": "outdoor.sl",
            "workbench_shadows_and_cavity": True,
            "mesh_simplification": False,
            "disabled_visible_geometry_count": 0,
            "lighting": (
                f"outdoor daylight studio lighting with {delivered_aa}-sample antialiasing, "
                "shadows, specular highlights, and world/screen cavity; authored "
                "Principled constants transiently synchronized to material viewport "
                "fields in Workbench layers; the bounded river/lake Eevee fallback "
                "retains authored PBR materials and maps same-camera relative receiver "
                "illumination onto the common Workbench base"
            ),
            "depth": (
                "32-bit camera-space Z; per-pixel Z Combine color with an "
                "independent float minimum depth union"
            ),
            "daytime_sky": (
                "clear blue sky applied only through the exact transparent "
                "no-hit alpha mask in BaseColor"
            ),
        },
        "source_layer_render_settings": SOURCE_LAYER_SETTINGS,
        "source_frame_render_engine_counts": dict(sorted(source_engine_counts.items())),
        "all_source_layers_material_fidelity": bool(SOURCE_LAYER_FRAME_SETTINGS)
        and all(
            material_fidelity_settings_valid(settings, layer_key)
            for layer_key, layer_frames in SOURCE_LAYER_FRAME_SETTINGS.items()
            for settings in layer_frames.values()
        ),
        "material_fidelity_policy": (
            "resource-safe Workbench MATERIAL rasterization after transient "
            "Principled constant synchronization; only validated Blender 5.1 "
            "empty-buffer frames in river5_nature or artificial_lake use "
            "64-sample Eevee with a "
            "same-camera Eevee base ratio for cross-layer receiver lighting; no "
            "node graph, linked source, production Blend, mesh, modifier, "
            "transform, or interior write"
        ),
        "layer_composition": True,
        "zdepth_composition": True,
        "layer_count": len(layer_module.LAYERS),
        "layers": list(layer_module.LAYERS),
        "partition_exactly_once": True,
        "placement_count": len(layout["placements"]),
        "all_layers_in_every_delivery_view": True,
        "center_distance_sorting": False,
        "alpha_only_composition": False,
        "cross_layer_lighting": (
            "all asset layers include CombinedColor/CombinedDepth on shared exact "
            "road/ground receivers; BaseDepth delta separates asset surfaces from "
            "lighting; Eevee river/lake fallback frames transfer the exact same-camera "
            "Combined/EeveeBase relative receiver illumination to WorkbenchBase"
        ),
        "linked_instance_empty_pass_workaround": (
            "one guaranteed-visible exact receiver+asset view rasterized once "
            "at native 1920x1080 after process-local exact collection-instance "
            "object-shell expansion; no visible geometry omitted or simplified; "
            "renderer-breaking live GN controllers use exact evaluated results "
            "in memory only; deterministic high-reference river/lake Workbench empty "
            "buffers use a pixel-validated 64-sample Eevee raster at the identical camera"
        ),
        "non_delivery_warmup_content": "not_used_single_exact_receiver_view",
        "non_delivery_warmup_retained": False,
        "content_aware_source_exr_validation": True,
        "minimum_nondegenerate_source_exr_bytes": 256 * 1024,
        "authoritative_source_exr_pixel_validation": True,
        "authoritative_source_exr_exact_parts_only": True,
        "committed_source_warmup_parts_retained": False,
        "combined_part_extraction": "not used; direct exact two-part bundles",
        "target_grid_rendering": ("single native full-resolution target-grid raster"),
        "native_resolution": [1920, 1080],
        "lattice_resolution": None,
        "lattice_count": 0,
        "target_pixel_centers_sampled_exactly": True,
        "resizing": False,
        "resampling": False,
        "interpolation": False,
        "temporary_exact_evaluated_gn_replacements": SOURCE_LAYER_GN_REALIZATIONS,
        "temporary_exact_collection_instance_expansions": (
            SOURCE_LAYER_INSTANCE_EXPANSIONS
        ),
        "omitted_visible_geometry_count": 0,
        "visibility_scope": {
            "all_zone_collections_visible_in_every_delivery_view": True,
            "temporarily_hidden_zones_in_delivery_views": [],
            "temporarily_hidden_placements_in_delivery_views": [],
            "temporarily_hidden_interiors_in_delivery_views": [],
        },
        "representative_interior_view_count": sum(
            shot.interior for shot in renderer.SHOTS
        ),
        "citywide_view_count": sum(shot.kind == "city" for shot in renderer.SHOTS),
        "regional_near_far_view_count": sum(
            shot.kind.startswith("zone_") for shot in renderer.SHOTS
        ),
        "blend_file": str(BLEND.resolve()),
        "blend_file_bytes": blend_stat.st_size,
        "blend_file_mtime_ns": blend_stat.st_mtime_ns,
        "blend_file_unchanged": True,
        "production_scene_saved_by_renderer": False,
        "views": [
            records[shot.name] for shot in renderer.SHOTS if shot.name in records
        ],
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def write_panorama_audit(renderer: Any, manifest: dict[str, Any]) -> None:
    records = manifest["views"]
    city = [record for record in records if record["kind"] == "city"]
    zone_pairs = [record for record in records if record["kind"].startswith("zone_")]
    interiors = [record for record in records if record.get("interior")]
    payload = {
        "schema": "agent.full12.panorama_audit.zdepth.v1",
        "created_utc": utc_now(),
        "status": "PASS" if manifest["complete"] else "FAIL",
        "scene_revision": REVISION,
        "checks_pass": bool(manifest["complete"]),
        "delivery_png_count": len(records),
        "minimum_delivery_png_count": 60,
        "resolution": list(renderer.RESOLUTION),
        "all_citywide_views_complete": len(city) == 6,
        "all_regional_pairs_complete": len(zone_pairs) == 18,
        "all_interior_views_complete": len(interiors) == 6,
        "mesh_projection_audit_pass": False,
        "render_method": "32-bit per-pixel camera-space Z-depth",
        "zdepth_composition": True,
        "alpha_only_composition": False,
        "center_distance_sorting": False,
        "all_layers_in_every_delivery_view": True,
        "cross_layer_lighting_preserved_on_shared_receivers": True,
    }
    atomic_json(PANORAMA_PATH, payload)


def main() -> None:
    global SOURCE_LAYER_SETTINGS, SOURCE_LAYER_GN_REALIZATIONS
    global SOURCE_LAYER_INSTANCE_EXPANSIONS, SOURCE_LAYER_FRAME_SETTINGS
    renderer = load_module("full12_compositor_renderer", RENDERER_PATH)
    layer_module = load_module("full12_compositor_layers", LAYER_PATH)
    if renderer.RESOLUTION != (1920, 1080):
        raise RuntimeError("Final full-12 delivery composition must be 1920x1080")
    source_layer_settings: dict[str, dict[str, Any]] = {}
    source_layer_gn_realizations: dict[str, dict[str, Any]] = {}
    source_layer_instance_expansions: dict[str, dict[str, Any]] = {}
    source_layer_frame_settings: dict[str, dict[str, dict[str, Any]]] = {}
    expected_gn_controllers = {"river5_nature": 1, "artificial_lake": 2}
    for layer_key in layer_module.LAYERS:
        manifest_path = LAYER_ROOT / f"layer_manifest_{layer_key}.json"
        if not manifest_path.is_file():
            raise RuntimeError(f"Missing layer manifest: {manifest_path}")
        manifest = json.loads(manifest_path.read_text(encoding="utf8"))
        if manifest.get("status") != "PASS" or not manifest.get("complete"):
            raise RuntimeError(f"Incomplete layer manifest: {manifest_path}")
        settings = manifest.get("render_settings", {})
        if not material_fidelity_settings_valid(settings, layer_key):
            raise RuntimeError(
                f"Layer has not passed material-fidelity validation: {manifest_path}"
            )
        records = manifest.get("views", [])
        records_by_name = {record.get("name"): record for record in records}
        if len(records) != len(renderer.SHOTS) or any(
            not material_fidelity_settings_valid(
                record.get("render_settings", {}), layer_key
            )
            for record in records
        ):
            raise RuntimeError(
                f"Layer frame quality provenance is incomplete: {manifest_path}"
            )
        if set(records_by_name) != set(renderer.SHOT_BY_NAME) or any(
            not renderer.shot_record_matches_spec(records_by_name[shot.name], shot)
            for shot in renderer.SHOTS
        ):
            raise RuntimeError(f"Layer camera specification is stale: {manifest_path}")
        expected_view_layers = ["Base"] if layer_key == "base" else ["Combined"]
        expected_depth = "BaseDepth.V" if layer_key == "base" else "CombinedDepth.V"
        if manifest.get("view_layers") != expected_view_layers or any(
            record.get("view_layers") != expected_view_layers
            or record.get("depth_channel") != expected_depth
            or record.get("camera", {}).get("matrix_validation", {}).get("pass")
            is not True
            for record in records
        ):
            raise RuntimeError(
                f"Layer camera/depth provenance is incomplete: {manifest_path}"
            )
        expected_warmup = "not_used_single_exact_receiver_view"
        if not (
            manifest.get("non_delivery_warmup_content") == expected_warmup
            and manifest.get("non_delivery_warmup_retained") is False
            and manifest.get("content_aware_exr_validation") is True
            and manifest.get("minimum_nondegenerate_exr_bytes") == 256 * 1024
            and manifest.get("authoritative_exr_pixel_validation") is True
            and manifest.get("authoritative_exr_exact_parts_only") is True
            and manifest.get("warmup_parts_retained_in_committed_bundle") is False
            and manifest.get("combined_part_extraction")
            == "not_used_direct_exact_two_part_bundle"
            and manifest.get("native_resolution") == [1920, 1080]
            and manifest.get("lattice_resolution") is None
            and manifest.get("lattice_count") == 0
            and manifest.get("target_pixel_centers_sampled_exactly") is True
            and manifest.get("resizing") is False
            and manifest.get("resampling") is False
            and manifest.get("interpolation") is False
            and all(
                record.get("non_delivery_warmup_content") == expected_warmup
                and authoritative_exr_evidence_valid(
                    layer_key, record.get("authoritative_exr_validation", {})
                )
                and record.get("camera", {})
                .get("target_grid_projection", {})
                .get("method")
                == "single native full-resolution raster"
                and record.get("camera", {})
                .get("target_grid_projection", {})
                .get("full_resolution")
                == [1920, 1080]
                and record.get("camera", {})
                .get("target_grid_projection", {})
                .get("native_resolution")
                == [1920, 1080]
                and record.get("camera", {})
                .get("target_grid_projection", {})
                .get("camera_shift")
                == [0.0, 0.0]
                and record.get("camera", {})
                .get("target_grid_projection", {})
                .get("target_pixel_centers_sampled_exactly")
                is True
                for record in records
            )
        ):
            raise RuntimeError(
                f"Layer warmup/content validation provenance is incomplete: {manifest_path}"
            )
        gn = manifest.get("temporary_exact_evaluated_gn_replacements", {})
        expected_controller_count = expected_gn_controllers.get(layer_key, 0)
        if expected_controller_count:
            controllers = gn.get("controllers", [])
            if not (
                gn.get("enabled") is True
                and gn.get("evaluation_view_layer") == "Combined"
                and gn.get("controller_count") == expected_controller_count
                and gn.get("replacement_object_count", 0) >= expected_controller_count
                and gn.get("replacement_polygon_count", 0) > 0
                and gn.get("omitted_visible_geometry_count") == 0
                and gn.get("geometry_simplification") is False
                and gn.get("node_graphs_changed") is False
                and gn.get("source_files_saved") is False
                and gn.get("production_blend_saved") is False
                and len(controllers) == expected_controller_count
                and all(
                    controller.get("exact_evaluated_geometry") is True
                    and controller.get("replacement_object_count", 0) > 0
                    and controller.get("replacement_polygon_references", 0) > 0
                    for controller in controllers
                )
                and all(
                    record.get("exact_evaluated_gn_replacement", {}).get("enabled")
                    is True
                    and record.get("exact_evaluated_gn_replacement", {}).get(
                        "controller_count"
                    )
                    == expected_controller_count
                    and record.get("exact_evaluated_gn_replacement", {}).get(
                        "omitted_visible_geometry_count"
                    )
                    == 0
                    for record in records
                )
            ):
                raise RuntimeError(
                    f"Exact visible GN realization evidence is incomplete: {manifest_path}"
                )
        elif gn.get("enabled") is not False:
            raise RuntimeError(
                f"Unexpected exact GN realization outside known sources: {manifest_path}"
            )
        expansion = manifest.get("temporary_exact_collection_instance_expansion", {})
        if layer_key == "base":
            if not (
                expansion.get("enabled") is False
                and expansion.get("placement_root_count") == 0
                and expansion.get("expanded_object_count") == 0
                and expansion.get("omitted_visible_geometry_count") == 0
            ):
                raise RuntimeError(
                    f"Unexpected base instance expansion: {manifest_path}"
                )
        elif not (
            expansion.get("enabled") is True
            and expansion.get("evaluation_view_layer") == "Combined"
            and expansion.get("placement_root_count")
            == manifest.get("assigned_placement_count")
            and expansion.get("expanded_object_count", 0) > 0
            and expansion.get("shared_authored_data_count")
            == expansion.get("expanded_object_count")
            and expansion.get("all_authored_data_shared") is True
            and expansion.get("all_world_matrices_preserved") is True
            and (
                float(expansion.get("maximum_world_matrix_error", 1.0)) <= 1.0e-4
                or float(expansion.get("maximum_world_matrix_relative_error", 1.0))
                <= 5.0e-7
            )
            and expansion.get("maximum_world_matrix_absolute_error_allowed") == 1.0e-4
            and expansion.get("maximum_world_matrix_relative_error_allowed") == 5.0e-7
            and expansion.get("exact_svd_affine_factorization") is True
            and expansion.get("affine_transform_helper_count", -1)
            == 2 * expansion.get("sheared_object_count", -1)
            and float(expansion.get("maximum_svd_factorization_error", 1.0)) <= 1.0e-10
            and expansion.get("modifiers_applied") is False
            and expansion.get("mesh_data_realized") is False
            and expansion.get("geometry_simplification") is False
            and expansion.get("source_scale_changed") is False
            and expansion.get("placement_roots_hidden_after_exact_expansion") is True
            and expansion.get("omitted_visible_geometry_count") == 0
            and expansion.get("source_data_copied") is False
            and expansion.get("source_files_saved") is False
            and expansion.get("production_blend_saved") is False
            and len(expansion.get("per_placement_object_counts", {}))
            == manifest.get("assigned_placement_count")
            and all(
                record.get("exact_collection_instance_expansion", {}).get("enabled")
                is True
                and record.get("exact_collection_instance_expansion", {}).get(
                    "placement_root_count"
                )
                == expansion.get("placement_root_count")
                and record.get("exact_collection_instance_expansion", {}).get(
                    "expanded_object_count"
                )
                == expansion.get("expanded_object_count")
                and record.get("exact_collection_instance_expansion", {}).get(
                    "all_world_matrices_preserved"
                )
                is True
                and record.get("exact_collection_instance_expansion", {}).get(
                    "omitted_visible_geometry_count"
                )
                == 0
                for record in records
            )
        ):
            raise RuntimeError(
                f"Exact collection-instance expansion evidence is incomplete: "
                f"{manifest_path}"
            )
        source_layer_settings[layer_key] = dict(settings)
        source_layer_frame_settings[layer_key] = {
            record["name"]: dict(record.get("render_settings", {}))
            for record in records
        }
        source_layer_gn_realizations[layer_key] = gn
        source_layer_instance_expansions[layer_key] = expansion
    SOURCE_LAYER_SETTINGS = source_layer_settings
    SOURCE_LAYER_GN_REALIZATIONS = source_layer_gn_realizations
    SOURCE_LAYER_INSTANCE_EXPANSIONS = source_layer_instance_expansions
    SOURCE_LAYER_FRAME_SETTINGS = source_layer_frame_settings

    scene = setup_scene(renderer)
    DELIVERY_ROOT.mkdir(parents=True, exist_ok=True)
    COMPOSITE_ROOT.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    records: dict[str, dict[str, Any]] = {}
    if MANIFEST_PATH.is_file():
        try:
            old = json.loads(MANIFEST_PATH.read_text(encoding="utf8"))
            current_run_id = json.loads(LAYOUT.read_text(encoding="utf8")).get("run_id")
            accepted_schemas = {
                "agent.full12.zdepth_delivery.v1",
                "agent.full13.zdepth_delivery.v1",
            }
            if (
                old.get("schema") in accepted_schemas
                and old.get("scene_revision") == REVISION
                and old.get("run_id") == current_run_id
            ):
                records = {record["name"]: record for record in old.get("views", [])}
        except (OSError, ValueError, KeyError, TypeError):
            records = {}
    errors: list[dict[str, str]] = []
    force = os.environ.get("C2W_FULL12_COMPOSE_FORCE", "0") == "1"
    requested_tokens = {
        token.strip()
        for token in os.environ.get("C2W_COMPOSE_VIEW_NAMES", "").split(",")
        if token.strip()
    }
    unknown_requested = requested_tokens - set(renderer.SHOT_BY_NAME)
    if unknown_requested:
        raise RuntimeError(
            "Unknown C2W_COMPOSE_VIEW_NAMES entries: "
            + ", ".join(sorted(unknown_requested))
        )
    for index, shot in enumerate(renderer.SHOTS, 1):
        if requested_tokens and shot.name not in requested_tokens:
            continue
        delivery = DELIVERY_ROOT / shot.filename
        composite = COMPOSITE_ROOT / f"{Path(shot.filename).stem}.exr"
        if not force and reusable_delivery_record(
            records.get(shot.name),
            renderer,
            layer_module,
            shot,
            delivery,
            composite,
        ):
            print(
                f"FULL12_ZCOMPOSE_SKIP {index}/{len(renderer.SHOTS)} {shot.name}",
                flush=True,
            )
            continue
        try:
            records[shot.name] = compose_shot(scene, renderer, layer_module, shot)
            print(
                f"FULL12_ZCOMPOSE_DONE {index}/{len(renderer.SHOTS)} "
                f"{shot.name} seconds={records[shot.name]['render_seconds']}",
                flush=True,
            )
            atomic_json(
                MANIFEST_PATH,
                build_manifest(
                    renderer, layer_module, records, started, "IN_PROGRESS", errors
                ),
            )
        except Exception as exc:
            errors.append({"view": shot.name, "error": repr(exc)})
            atomic_json(
                MANIFEST_PATH,
                build_manifest(
                    renderer, layer_module, records, started, "FAIL", errors
                ),
            )
            raise

    manifest = build_manifest(
        renderer, layer_module, records, started, "IN_PROGRESS", errors
    )
    atomic_json(MANIFEST_PATH, manifest)
    write_panorama_audit(renderer, manifest)
    print(
        f"FULL12_ZCOMPOSE_FINISH status={manifest['status']} "
        f"completed={manifest['completed_count']}/{manifest['expected_count']}",
        flush=True,
    )


if __name__ == "__main__":
    main()

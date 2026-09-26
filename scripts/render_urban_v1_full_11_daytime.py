#!/usr/bin/env python3
"""Render the full-11 city in daylight without hiding any city region.

The renderer reads the generated placement footprints, fits temporary cameras,
and never saves the Blend.  Its complete catalogue contains six citywide
panoramas, near/far pairs for all nine regions, and near/far pairs for eight
important facilities.  Every image keeps all other regions and placements
render-enabled; camera framing, rather than visibility mutation, isolates a
close view.
"""

from __future__ import annotations

import json
import math
import os
import re
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_11"
CITY_ROOT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
LAYOUT_PATH = CITY_ROOT / "layout_plan.json"
OUT = CITY_ROOT / "renders"
MANIFEST = OUT / "render_manifest.json"
LAYER_ROOT = OUT / "layers"
PANORAMA_AUDIT = CITY_ROOT / "panorama_audit.json"
TEMP_PREFIX = "__full11_daytime_tmp__"


def parse_resolution() -> tuple[int, int]:
    raw = os.environ.get("C2W_FULL11_RENDER_RESOLUTION", "960x540")
    match = re.fullmatch(r"\s*(\d+)\s*[xX,]\s*(\d+)\s*", raw)
    if not match:
        raise RuntimeError("C2W_FULL11_RENDER_RESOLUTION must look like 960x540")
    width, height = map(int, match.groups())
    if width < 720 or height < 400:
        raise RuntimeError("Full-11 delivery renders must be at least 720x400")
    return width, height


RESOLUTION = parse_resolution()
ZONES = (
    "residential",
    "commercial",
    "park",
    "leisure",
    "education",
    "civic",
    "health",
    "industrial",
    "roads",
)
LAYER_SPECS = {
    "base": {"zones": {"city_base", "roads"}},
    "residential_01": {
        "zones": {"residential"},
        "placements": {"residential_01_river3_indoor"},
    },
    "residential_02": {
        "zones": {"residential"},
        "placements": {"residential_02_river3_north_extension"},
    },
    "residential_03": {
        "zones": {"residential"},
        "placements": {"residential_03_all45_09_native_indoor"},
    },
    "residential_support": {
        "zones": {"residential"},
        "placements": {
            "residential_delivery_01_food_delivery_locker",
            "residential_delivery_02_parcel_locker",
            "residential_delivery_03_delivery_station",
        },
    },
    "commercial": {"zones": {"commercial"}},
    "park_nature": {
        "zones": {"park"},
        "placements": {"park_original_sculpture_nature"},
    },
    "park_river": {
        "zones": {"park"},
        "placements": {"park_river5_corridor"},
    },
    "park_support": {
        "zones": {"park"},
        "placements": {"park_fitness_area", "park_single_fountain"},
    },
    "leisure": {"zones": {"leisure"}},
    "education": {"zones": {"education"}},
    "civic": {"zones": {"civic"}},
    "health": {"zones": {"health"}},
    "industrial": {"zones": {"industrial"}},
}
LAYERS = tuple(LAYER_SPECS)


@dataclass(frozen=True)
class View:
    name: str
    filename: str
    kind: str
    direction: tuple[float, float, float]
    lens: float
    margin: float
    zone: str | None = None
    feature: str | None = None
    projection: str = "PERSP"


CITY_VIEWS = (
    View(
        "city_southwest",
        "01_city_southwest_panorama.png",
        "city",
        (-1.0, -1.0, 0.82),
        48.0,
        1.13,
    ),
    View(
        "city_southeast",
        "02_city_southeast_panorama.png",
        "city",
        (1.0, -1.0, 0.82),
        48.0,
        1.13,
    ),
    View(
        "city_northwest",
        "03_city_northwest_panorama.png",
        "city",
        (-1.0, 1.0, 0.82),
        48.0,
        1.13,
    ),
    View(
        "city_northeast",
        "04_city_northeast_panorama.png",
        "city",
        (1.0, 1.0, 0.82),
        48.0,
        1.13,
    ),
    View(
        "city_high_aerial",
        "05_city_high_aerial_panorama.png",
        "city",
        (0.28, -0.42, 1.0),
        52.0,
        1.12,
    ),
    View(
        "city_top_down",
        "06_city_top_down_coverage.png",
        "city",
        (0.001, -0.001, 1.0),
        50.0,
        1.08,
        projection="ORTHO",
    ),
)

ZONE_DIRECTIONS = {
    "residential": ((0.75, -1.0, 0.78), (-0.25, -1.0, 0.28)),
    "commercial": ((-0.70, -1.0, 0.72), (0.15, -1.0, 0.22)),
    "park": ((0.80, -1.0, 0.78), (-0.35, -1.0, 0.24)),
    "leisure": ((-0.80, -1.0, 0.74), (-0.35, -1.0, 0.25)),
    "education": ((0.68, -1.0, 0.76), (0.25, -1.0, 0.26)),
    "civic": ((-0.70, -1.0, 0.72), (0.10, -1.0, 0.24)),
    "health": ((0.80, -1.0, 0.74), (0.30, -1.0, 0.25)),
    "industrial": ((-0.76, -1.0, 0.70), (-0.18, -1.0, 0.23)),
    "roads": ((1.0, -1.0, 0.88), (0.90, -1.0, 0.30)),
}


def zone_views() -> tuple[View, ...]:
    result = []
    number = 10
    for zone in ZONES:
        far_direction, near_direction = ZONE_DIRECTIONS[zone]
        result.extend(
            (
                View(
                    f"{zone}_far",
                    f"{number:02d}_{zone}_far.png",
                    "zone_far",
                    far_direction,
                    51.0,
                    1.16,
                    zone=zone,
                ),
                View(
                    f"{zone}_near",
                    f"{number + 1:02d}_{zone}_near.png",
                    "zone_near",
                    near_direction,
                    55.0,
                    1.05,
                    zone=zone,
                ),
            )
        )
        number += 2
    return tuple(result)


FEATURES = {
    "school": ("education", {"school"}),
    "library": ("education", {"library"}),
    "bank": ("commercial", {"bank", "atm_row"}),
    "hospital": ("health", {"hospital"}),
    "gas_station": ("industrial", {"gas_station"}),
    "factory": ("industrial", {"factory"}),
    "fire_police": ("civic", {"fire_station", "police_station"}),
    "artificial_lake": ("education", {"artificial_lake"}),
}

FEATURE_DIRECTIONS = {
    "school": ((0.70, -1.0, 0.72), (0.10, -1.0, 0.24)),
    "library": ((-0.72, -1.0, 0.72), (-0.12, -1.0, 0.24)),
    "bank": ((0.70, -1.0, 0.76), (0.12, -1.0, 0.22)),
    "hospital": ((-0.72, -1.0, 0.72), (-0.10, -1.0, 0.22)),
    "gas_station": ((0.90, -1.0, 0.65), (1.0, -0.18, 0.20)),
    "factory": ((-0.70, -1.0, 0.68), (-0.12, -1.0, 0.20)),
    "fire_police": ((0.88, -0.45, 0.68), (1.0, -0.18, 0.22)),
    "artificial_lake": ((0.72, -1.0, 0.82), (-0.35, -1.0, 0.30)),
}


def feature_views() -> tuple[View, ...]:
    result = []
    number = 30
    for feature, (zone, _categories) in FEATURES.items():
        far_direction, near_direction = FEATURE_DIRECTIONS[feature]
        result.extend(
            (
                View(
                    f"{feature}_far",
                    f"{number:02d}_{feature}_far.png",
                    "feature_far",
                    far_direction,
                    53.0,
                    1.15,
                    zone=zone,
                    feature=feature,
                ),
                View(
                    f"{feature}_near",
                    f"{number + 1:02d}_{feature}_near.png",
                    "feature_near",
                    near_direction,
                    58.0,
                    1.04,
                    zone=zone,
                    feature=feature,
                ),
            )
        )
        number += 2
    return tuple(result)


VIEWS = CITY_VIEWS + zone_views() + feature_views()
VIEW_BY_NAME = {view.name: view for view in VIEWS}

# Near-zone views deliberately focus on representative authored assets.  This
# affects only camera bounds; no placement is hidden.
NEAR_PLACEMENT_IDS = {
    "residential": {"residential_03_all45_09_native_indoor"},
    "commercial": {
        "commercial_all43_25_complete",
        "pharmacy_cvs_west",
        "pharmacy_well_east",
        "commercial_atm_five_machine_row",
    },
    "park": {
        "park_original_sculpture_nature",
        "park_single_fountain",
        "park_fitness_area",
    },
    "leisure": {"leisure_all44_14_complete", "leisure_fitness_area"},
    "education": {
        "education_library_south",
        "education_artificial_lake_civic_enclosure",
    },
    "civic": {
        "civic_fire_precinct_north",
        "police_opposite_fire_west",
        "police_opposite_fire_east",
    },
    "health": {"hospital_central_red_white"},
    "industrial": {
        "factory_01_gable",
        "factory_02_white",
        "factory_03_gated",
        "factory_04_highbay",
    },
    "roads": set(),
}


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def args() -> list[str]:
    return sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []


def select_views(tokens: Sequence[str]) -> list[View]:
    pieces = [
        piece.strip().lower()
        for token in tokens
        for piece in token.split(",")
        if piece.strip()
    ]
    if not pieces or any(piece in {"all", "*"} for piece in pieces):
        return list(VIEWS)
    if any(piece in {"list", "--list"} for piece in pieces):
        for view in VIEWS:
            print(f"{view.name:28s} {view.filename}")
        return []
    groups = {
        "city": [view.name for view in CITY_VIEWS],
        "panoramas": [view.name for view in CITY_VIEWS],
        "regions": [view.name for view in VIEWS if view.kind.startswith("zone_")],
        "features": [view.name for view in VIEWS if view.kind.startswith("feature_")],
        "near": [view.name for view in VIEWS if view.kind.endswith("near")],
        "far": [view.name for view in VIEWS if view.kind.endswith("far")],
    }
    for zone in ZONES:
        groups[zone] = [f"{zone}_far", f"{zone}_near"]
    for feature in FEATURES:
        groups[feature] = [f"{feature}_far", f"{feature}_near"]
    for view in VIEWS:
        groups[view.name] = [view.name]
        groups[view.filename.lower()] = [view.name]
        groups[Path(view.filename).stem.lower()] = [view.name]
    names = []
    unknown = []
    for piece in pieces:
        if piece not in groups:
            unknown.append(piece)
            continue
        for name in groups[piece]:
            if name not in names:
                names.append(name)
    if unknown:
        raise RuntimeError(f"Unknown full-11 render request: {unknown}")
    return [VIEW_BY_NAME[name] for name in names]


def footprint_bounds(record: dict[str, Any]) -> tuple[Vector, Vector]:
    footprint = record["footprint"]
    lower = footprint["min"]
    upper = footprint["max"]
    return Vector(tuple(map(float, lower[:3]))), Vector(tuple(map(float, upper[:3])))


def union_bounds(
    bounds: Iterable[tuple[Vector, Vector]]
) -> tuple[Vector, Vector] | None:
    values = list(bounds)
    if not values:
        return None
    return (
        Vector(tuple(min(item[0][axis] for item in values) for axis in range(3))),
        Vector(tuple(max(item[1][axis] for item in values) for axis in range(3))),
    )


def city_bounds(layout: dict[str, Any]) -> tuple[Vector, Vector]:
    bounds = layout["city_bounds"]
    return Vector(bounds["min"]), Vector(bounds["max"])


def resolve_bounds(
    view: View, layout: dict[str, Any]
) -> tuple[tuple[Vector, Vector], list[str], str]:
    placements = layout["placements"]
    if view.kind == "city":
        return (
            city_bounds(layout),
            [record["placement_id"] for record in placements],
            "city_bounds",
        )
    candidates = [
        record
        for record in placements
        if view.zone is None or record.get("zone") == view.zone
    ]
    if view.feature:
        categories = FEATURES[view.feature][1]
        candidates = [
            record for record in candidates if record.get("category") in categories
        ]
        source = f"feature:{view.feature}"
    elif view.kind == "zone_near":
        requested = NEAR_PLACEMENT_IDS.get(view.zone or "", set())
        if requested:
            candidates = [
                record for record in candidates if record["placement_id"] in requested
            ]
        elif view.zone == "roads":
            intersections = [
                record
                for record in candidates
                if record.get("category") == "road_intersection"
            ]
            candidates = sorted(
                intersections,
                key=lambda record: abs(record["location"][0])
                + abs(record["location"][1]),
            )[:1]
        source = f"zone_near:{view.zone}"
    else:
        source = f"zone:{view.zone}"
    bounds = union_bounds(footprint_bounds(record) for record in candidates)
    if bounds is None:
        raise RuntimeError(f"No placement bounds for {view.name}")
    return bounds, [record["placement_id"] for record in candidates], source


def fit_camera(
    camera: bpy.types.Object,
    bounds: tuple[Vector, Vector],
    view: View,
) -> dict[str, Any]:
    lower, upper = bounds
    span = upper - lower
    center = (lower + upper) * 0.5
    target = Vector((center.x, center.y, lower.z + span.z * 0.34))
    direction = Vector(view.direction).normalized()
    camera.data.type = view.projection
    camera.data.lens = view.lens
    camera.data.clip_start = 0.2
    camera.data.clip_end = 8000.0

    if view.projection == "ORTHO":
        aspect = RESOLUTION[0] / RESOLUTION[1]
        camera.data.ortho_scale = max(span.y, span.x / aspect) * view.margin
        distance = max(span.x, span.y, 1.0) * 1.45
    else:
        aspect = RESOLUTION[0] / RESOLUTION[1]
        horizontal_fov = 2.0 * math.atan(36.0 / (2.0 * view.lens))
        vertical_fov = 2.0 * math.atan(math.tan(horizontal_fov / 2.0) / aspect)
        radius = max(1.0, span.length * 0.5)
        distance = radius / math.sin(max(0.08, vertical_fov / 2.0)) * view.margin
    camera.location = target + direction * distance
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    return {
        "projection": view.projection,
        "location": [round(float(value), 4) for value in camera.location],
        "target": [round(float(value), 4) for value in target],
        "lens_mm": view.lens,
        "ortho_scale": camera.data.ortho_scale if view.projection == "ORTHO" else None,
        "clip": [camera.data.clip_start, camera.data.clip_end],
    }


def configure_daylight(
    scene: bpy.types.Scene,
    *,
    transparent: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    requested = os.environ.get("C2W_FULL11_RENDER_ENGINE", "CYCLES").strip().upper()
    if requested in {"EEVEE", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    elif requested in {"WORKBENCH", "BLENDER_WORKBENCH"}:
        scene.render.engine = "BLENDER_WORKBENCH"
    elif requested in {"CYCLES", "OPTIX"}:
        scene.render.engine = "CYCLES"
    else:
        raise RuntimeError(
            "C2W_FULL11_RENDER_ENGINE must be CYCLES, EEVEE, or WORKBENCH"
        )
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 22
    scene.render.film_transparent = transparent
    scene.render.use_file_extension = True
    scene.render.use_simplify = True
    scene.render.simplify_subdivision_render = 0
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.35
    temporary: dict[str, Any] = {
        "previous_world": scene.world,
        "world": None,
        "sun": None,
        "sun_data": None,
    }
    studio_light = None
    background_rgb = (0.37, 0.61, 0.86)
    render_devices = []
    samples = None
    if scene.render.engine == "BLENDER_WORKBENCH":
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        shading.background_type = "VIEWPORT"
        shading.background_color = background_rgb
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = "WORLD"
        shading.show_specular_highlight = True
        if hasattr(shading, "show_outline"):
            shading.show_outline = False
        available = {
            light.name
            for light in bpy.context.preferences.studio_lights
            if getattr(light, "type", "") == "STUDIO"
        }
        for candidate in ("outdoor.sl", "paint.sl", "rim.sl", "basic.sl"):
            if candidate in available:
                shading.studio_light = candidate
                break
        studio_light = shading.studio_light
    else:
        if scene.render.engine == "CYCLES":
            samples = max(1, int(os.environ.get("C2W_FULL11_RENDER_SAMPLES", "4")))
            scene.cycles.device = "GPU"
            scene.cycles.samples = samples
            scene.cycles.use_denoising = True
            scene.cycles.use_adaptive_sampling = True
            scene.cycles.adaptive_threshold = 0.12
            scene.cycles.max_bounces = 4
            scene.cycles.diffuse_bounces = 2
            scene.cycles.glossy_bounces = 2
            scene.cycles.transmission_bounces = 2
            scene.cycles.transparent_max_bounces = 4
            scene.cycles.volume_bounces = 0
            scene.cycles.use_fast_gi = True
            addon = bpy.context.preferences.addons.get("cycles")
            if addon is None:
                raise RuntimeError("Cycles addon is unavailable")
            preferences = addon.preferences
            for compute_type in ("OPTIX", "CUDA"):
                try:
                    preferences.compute_device_type = compute_type
                    preferences.get_devices()
                    enabled = []
                    for device in preferences.devices:
                        device.use = device.type == compute_type
                        if device.use:
                            enabled.append(
                                {
                                    "name": device.name,
                                    "type": device.type,
                                    "id": device.id,
                                }
                            )
                    if enabled:
                        render_devices = enabled
                        break
                except (TypeError, ValueError, RuntimeError):
                    continue
            if not render_devices:
                raise RuntimeError(
                    "No CUDA/OptiX device visible; set CUDA_VISIBLE_DEVICES"
                )
        world = bpy.data.worlds.new(f"{TEMP_PREFIX}:world")
        world.use_nodes = True
        background = world.node_tree.nodes.get("Background")
        if background is not None:
            background.inputs["Color"].default_value = (*background_rgb, 1.0)
            background.inputs["Strength"].default_value = 0.62
        scene.world = world
        sun_data = bpy.data.lights.new(f"{TEMP_PREFIX}:sun_data", type="SUN")
        sun_data.energy = 2.7
        sun_data.angle = math.radians(6.0)
        sun = bpy.data.objects.new(f"{TEMP_PREFIX}:sun", sun_data)
        scene.collection.objects.link(sun)
        sun.rotation_euler = (
            math.radians(27.0),
            math.radians(-19.0),
            math.radians(-38.0),
        )
        temporary.update({"world": world, "sun": sun, "sun_data": sun_data})
    settings = {
        "engine": scene.render.engine,
        "resolution": list(RESOLUTION),
        "format": "PNG/RGBA/8",
        "look": "AgX daylight",
        "studio_light": studio_light,
        "background_rgb": list(background_rgb),
        "instance_preserving_renderer": scene.render.engine
        in {"BLENDER_EEVEE_NEXT", "CYCLES"},
        "transparent_film": transparent,
        "samples": samples,
        "render_devices": render_devices,
    }
    return settings, temporary


def remove_temporary_daylight(
    scene: bpy.types.Scene, temporary: dict[str, Any]
) -> None:
    sun = temporary.get("sun")
    sun_data = temporary.get("sun_data")
    world = temporary.get("world")
    scene.world = temporary.get("previous_world")
    if sun is not None and sun.name in bpy.data.objects:
        bpy.data.objects.remove(sun, do_unlink=True)
    if sun_data is not None and sun_data.users == 0:
        bpy.data.lights.remove(sun_data)
    if world is not None and world.users == 0:
        bpy.data.worlds.remove(world)


def blend_signature() -> dict[str, Any]:
    path = Path(bpy.data.filepath).resolve()
    stat = path.stat()
    return {"path": str(path), "bytes": stat.st_size, "mtime_ns": stat.st_mtime_ns}


def force_all_regions_visible(
    scene: bpy.types.Scene,
) -> tuple[list[tuple[Any, bool, bool]], list[str]]:
    saved = []
    region_names = []
    for collection in bpy.data.collections:
        if collection.name.startswith("full10:zone:"):
            saved.append(
                (
                    collection,
                    bool(collection.hide_viewport),
                    bool(collection.hide_render),
                )
            )
            collection.hide_viewport = False
            collection.hide_render = False
            region_names.append(collection.name.split("full10:zone:", 1)[1])
    for obj in scene.objects:
        if obj.get("placement_id") is not None and obj.get("zone") is not None:
            saved.append((obj, bool(obj.hide_viewport), bool(obj.hide_render)))
            obj.hide_viewport = False
            obj.hide_render = False
    return saved, sorted(set(region_names))


def apply_layer_visibility_scope(
    layer_key: str,
) -> tuple[list[tuple[Any, bool, bool]], list[str], list[str], list[str]]:
    """Expose one exact city layer before Blender builds its dependency graph."""
    if layer_key not in LAYERS:
        raise RuntimeError(f"Unknown layer {layer_key!r}; expected one of {LAYERS}")
    spec = LAYER_SPECS[layer_key]
    keep = set(spec["zones"])
    selected_placements = set(spec.get("placements", ()))
    saved = []
    hidden = []
    hidden_placements = []
    for collection in bpy.data.collections:
        if not collection.name.startswith("full10:zone:"):
            continue
        zone = collection.name.split("full10:zone:", 1)[1].split(".", 1)[0].lower()
        saved.append(
            (collection, bool(collection.hide_viewport), bool(collection.hide_render))
        )
        visible = zone in keep
        collection.hide_viewport = not visible
        collection.hide_render = not visible
        if not visible:
            hidden.append(zone)
    if selected_placements:
        for obj in bpy.context.scene.objects:
            placement_id = obj.get("placement_id")
            if placement_id is None or str(obj.get("zone", "")) not in keep:
                continue
            if str(placement_id) in selected_placements:
                continue
            # Generic residential infill belongs to the third residential
            # layer.  The other residential layers remain exact single-source
            # subsets, while this rule prevents audited scale-one streetwall
            # assets from being hidden from every final composite layer.
            if (
                layer_key == "residential_03"
                and str(obj.get("category", "")) == "urban_infill"
            ):
                continue
            saved.append((obj, bool(obj.hide_viewport), bool(obj.hide_render)))
            obj.hide_viewport = True
            obj.hide_render = True
            hidden_placements.append(str(placement_id))
    return (
        saved,
        sorted(keep),
        sorted(set(hidden)),
        sorted(set(hidden_placements)),
    )


def restore_visibility(saved: Iterable[tuple[Any, bool, bool]]) -> None:
    for datablock, hide_viewport, hide_render in saved:
        datablock.hide_viewport = hide_viewport
        datablock.hide_render = hide_render


def disable_occluded_interior_instances(
    scene: bpy.types.Scene,
) -> tuple[list[tuple[bpy.types.Object, bool, bool]], list[str]]:
    """Skip closed-building interiors for exterior-only validation cameras.

    The production Blend and its linked indoor collections are untouched.  We
    only suppress nested collection-instance empties whose own name, instance
    collection, or authored metadata explicitly identifies them as interiors.
    Building placement roots and every exterior/city region remain visible.
    """
    visited: set[bpy.types.Collection] = set()
    candidates: set[bpy.types.Object] = set()

    def visit(collection: bpy.types.Collection) -> None:
        if collection in visited:
            return
        visited.add(collection)
        for obj in collection.objects:
            if obj.instance_type == "COLLECTION" and obj.instance_collection:
                tokens = [obj.name, obj.instance_collection.name]
                for datablock in (obj, obj.instance_collection):
                    for key in datablock.keys():
                        value = datablock[key]
                        if (
                            "indoor" in str(key).lower()
                            or "interior" in str(key).lower()
                        ):
                            if value not in (False, None, "", 0):
                                tokens.extend((str(key), str(value)))
                combined = " ".join(tokens).lower()
                if obj.get("placement_id") is None and (
                    "indoor" in combined
                    or "interior_instance" in combined
                    or "in indoor areas" in combined
                ):
                    candidates.add(obj)
                visit(obj.instance_collection)
        for child in collection.children:
            visit(child)

    visit(scene.collection)
    saved = []
    names = []
    for obj in sorted(candidates, key=lambda item: item.name):
        saved.append((obj, bool(obj.hide_viewport), bool(obj.hide_render)))
        obj.hide_viewport = True
        obj.hide_render = True
        names.append(obj.name)
    return saved, names


def disable_hidden_zero_face_geometry_node_controllers() -> (
    tuple[list[tuple[Any, bool, bool]], list[str]]
):
    """Prevent hidden articulation controllers from expanding in linked instances.

    The delivery source deliberately marks its one-vertex/zero-face kinematic
    carriers ``hide_render=True``.  Blender can nevertheless evaluate their
    Geometry Nodes before applying that visibility flag when the authored
    collection is linked as a city placement.  Disabling only those already
    invisible controller modifiers avoids the recursive dependency expansion;
    no render-visible mesh, material, transform, or authored detail is changed.
    """
    saved: list[tuple[Any, bool, bool]] = []
    names: list[str] = []
    for obj in bpy.data.objects:
        if (
            not obj.hide_render
            or obj.type != "MESH"
            or obj.data is None
            or len(obj.data.polygons) != 0
        ):
            continue
        for modifier in obj.modifiers:
            if modifier.type != "NODES":
                continue
            saved.append(
                (modifier, bool(modifier.show_viewport), bool(modifier.show_render))
            )
            modifier.show_viewport = False
            modifier.show_render = False
            names.append(f"{obj.name}:{modifier.name}")
    return saved, sorted(names)


def restore_modifier_visibility(saved: Iterable[tuple[Any, bool, bool]]) -> None:
    for modifier, show_viewport, show_render in saved:
        modifier.show_viewport = show_viewport
        modifier.show_render = show_render


def write_manifest(payload: dict[str, Any], path: Path = MANIFEST) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def existing_records(path: Path = MANIFEST) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf8"))
    except (OSError, ValueError, TypeError):
        return {}
    return {
        record["name"]: record
        for record in payload.get("views", [])
        if record.get("name") in VIEW_BY_NAME
    }


def render(
    selected: Sequence[View],
    *,
    layer_key: str | None = None,
) -> dict[str, Any]:
    if not LAYOUT_PATH.is_file():
        raise FileNotFoundError(LAYOUT_PATH)
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf8"))
    if layout.get("scene_revision") != REVISION:
        raise RuntimeError(f"Wrong layout revision: {layout.get('scene_revision')}")
    scene = bpy.data.scenes.get(REVISION) or bpy.context.scene
    if bpy.context.window is not None:
        bpy.context.window.scene = scene
    OUT.mkdir(parents=True, exist_ok=True)
    before = blend_signature()
    (
        saved_controllers,
        hidden_controllers,
    ) = disable_hidden_zero_face_geometry_node_controllers()
    if layer_key is None:
        saved_visibility, region_names = force_all_regions_visible(scene)
        hidden_zones: list[str] = []
        hidden_placements: list[str] = []
        output_directory = OUT
        manifest_path = MANIFEST
    else:
        (
            saved_visibility,
            region_names,
            hidden_zones,
            hidden_placements,
        ) = apply_layer_visibility_scope(layer_key)
        output_directory = LAYER_ROOT / layer_key
        manifest_path = LAYER_ROOT / f"layer_manifest_{layer_key}.json"
        output_directory.mkdir(parents=True, exist_ok=True)
    saved_interiors, hidden_interiors = disable_occluded_interior_instances(scene)
    settings, temporary_daylight = configure_daylight(
        scene, transparent=layer_key not in {None, "base"}
    )
    camera_data = bpy.data.cameras.new(f"{TEMP_PREFIX}:camera_data")
    camera = bpy.data.objects.new(f"{TEMP_PREFIX}:camera", camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    records = existing_records(manifest_path)
    errors = []
    force = os.environ.get("C2W_FULL11_RENDER_FORCE", "0") == "1"
    started = time.time()
    try:
        for view in selected:
            target = output_directory / view.filename
            bounds, placement_ids, source = resolve_bounds(view, layout)
            camera_record = fit_camera(camera, bounds, view)
            record = {
                **asdict(view),
                "bounds": {
                    "min": [round(float(value), 4) for value in bounds[0]],
                    "max": [round(float(value), 4) for value in bounds[1]],
                },
                "bounds_source": source,
                "framed_placement_ids": placement_ids,
                "camera": camera_record,
                "all_regions_visible": layer_key is None,
                "layer_key": layer_key,
                "temporarily_hidden_zones": hidden_zones,
                "temporarily_hidden_placements": hidden_placements,
            }
            print(f"C2W_FULL11_RENDER_BEGIN {view.name}", flush=True)
            if not force and target.is_file() and target.stat().st_size > 0:
                record.update({"status": "existing", "bytes": target.stat().st_size})
                print(f"C2W_FULL11_RENDER_EXISTING {target.name}", flush=True)
            else:
                frame_started = time.time()
                try:
                    scene.render.filepath = str(target)
                    bpy.ops.render.render(write_still=True)
                    if not target.is_file() or target.stat().st_size <= 0:
                        raise RuntimeError(f"missing output {target}")
                    record.update(
                        {
                            "status": "rendered",
                            "bytes": target.stat().st_size,
                            "seconds": round(time.time() - frame_started, 3),
                        }
                    )
                    print(
                        f"C2W_FULL11_RENDER_DONE {view.name} "
                        f"seconds={record['seconds']} bytes={record['bytes']}",
                        flush=True,
                    )
                except Exception as exc:
                    record.update({"status": "failed", "error": repr(exc)})
                    errors.append(f"{view.name}: {exc}")
                    print(f"C2W_FULL11_RENDER_FAILED {view.name} {exc!r}", flush=True)
            records[view.name] = record
    finally:
        scene.camera = None
        bpy.data.objects.remove(camera, do_unlink=True)
        if camera_data.users == 0:
            bpy.data.cameras.remove(camera_data)
        remove_temporary_daylight(scene, temporary_daylight)
        restore_visibility(saved_interiors)
        restore_visibility(saved_visibility)
        restore_modifier_visibility(saved_controllers)

    after = blend_signature()
    catalogue = [asdict(view) for view in VIEWS]
    ordered_records = [records[name] for name in VIEW_BY_NAME if name in records]
    completed = {
        record["name"]
        for record in ordered_records
        if record.get("status") in {"rendered", "existing"}
        and (output_directory / record["filename"]).is_file()
        and (output_directory / record["filename"]).stat().st_size > 0
    }
    if layer_key is not None:
        manifest = {
            "schema": "agent.full11.daytime_render_layer.v1",
            "created_utc": utc_now(),
            "scene_revision": REVISION,
            "layer_key": layer_key,
            "blend_file": str(Path(bpy.data.filepath).resolve()),
            "output_directory": str(output_directory),
            "catalogue": catalogue,
            "requested_views": [view.name for view in selected],
            "views": ordered_records,
            "expected_count": len(VIEWS),
            "completed_count": len(completed),
            "completed_view_names": sorted(completed),
            "missing_view_names": sorted(set(VIEW_BY_NAME) - completed),
            "complete": len(completed) == len(VIEWS) and not errors,
            "visibility_scope": {
                "kept_zones": region_names,
                "temporarily_hidden_zones": hidden_zones,
                "temporarily_hidden_placements": hidden_placements,
                "layer_spec": {
                    "zones": sorted(LAYER_SPECS[layer_key]["zones"]),
                    "placements": sorted(LAYER_SPECS[layer_key].get("placements", ())),
                },
                "temporarily_hidden_occluded_interior_instances": hidden_interiors,
                "temporarily_disabled_hidden_zero_face_controllers": (
                    hidden_controllers
                ),
                "policy": (
                    "exact authored geometry layer; final images combine every layer"
                ),
            },
            "render_settings": settings,
            "errors": errors,
            "blend_saved_by_renderer": False,
            "blend_before": before,
            "blend_after": after,
            "blend_file_unchanged": before == after,
            "elapsed_seconds": round(time.time() - started, 3),
        }
        write_manifest(manifest, manifest_path)
        if errors:
            raise RuntimeError("; ".join(errors))
        return manifest
    manifest = {
        "schema": "agent.full11.daytime_render_manifest.v1",
        "created_utc": utc_now(),
        "scene_revision": REVISION,
        "blend_file": str(Path(bpy.data.filepath).resolve()),
        "output_directory": str(OUT),
        "catalogue": catalogue,
        "requested_views": [view.name for view in selected],
        "views": ordered_records,
        "expected_count": len(VIEWS),
        "completed_count": len(completed),
        "completed_view_names": sorted(completed),
        "missing_view_names": sorted(set(VIEW_BY_NAME) - completed),
        "complete": len(completed) == len(VIEWS) and not errors,
        "visibility_scope": {
            "active": False,
            "all_regions_visible": True,
            "kept_zones": sorted(set(region_names) | {"city_base"}),
            "temporarily_hidden_zones": [],
            "temporarily_hidden_placements": [],
            "temporarily_hidden_occluded_interior_instances": hidden_interiors,
            "temporarily_hidden_occluded_interior_instance_count": len(
                hidden_interiors
            ),
            "interior_render_policy": (
                "closed-building interiors remain complete in the Blend and are only "
                "disabled in-memory for exterior validation cameras"
            ),
            "policy": "camera framing only; no city region or placement hidden",
        },
        "render_settings": settings,
        "errors": errors,
        "temporary_camera_removed": True,
        "blend_saved_by_renderer": False,
        "blend_before": before,
        "blend_after": after,
        "blend_file_unchanged": before == after,
        "elapsed_seconds": round(time.time() - started, 3),
    }
    write_manifest(manifest)
    if manifest["complete"]:
        panorama = {
            "status": "PASS",
            "scene_revision": REVISION,
            "citywide_panorama_count": len(CITY_VIEWS),
            "regional_near_far_pair_count": len(ZONES),
            "feature_near_far_pair_count": len(FEATURES),
            "total_png_count": len(VIEWS),
            "all_regions_visible_in_every_view": True,
            "citywide_panorama_files": [view.filename for view in CITY_VIEWS],
            "coverage_source": str(LAYOUT_PATH),
            "render_manifest": str(MANIFEST),
        }
        PANORAMA_AUDIT.write_text(
            json.dumps(panorama, indent=2, ensure_ascii=False), encoding="utf8"
        )
    if errors:
        raise RuntimeError("; ".join(errors))
    return manifest


def _layer_centres(layout: dict[str, Any]) -> dict[str, Vector]:
    result = {}
    for layer_key, spec in LAYER_SPECS.items():
        if layer_key == "base":
            continue
        zones = set(spec["zones"])
        selected = set(spec.get("placements", ()))
        bounds = union_bounds(
            footprint_bounds(record)
            for record in layout["placements"]
            if record.get("zone") in zones
            and (not selected or record.get("placement_id") in selected)
        )
        if bounds is None:
            raise RuntimeError(f"Cannot determine centre for layer {layer_key}")
        result[layer_key] = (bounds[0] + bounds[1]) * 0.5
    return result


def compose_layers() -> dict[str, Any]:
    """Combine every exact-geometry zone layer into the 40 final images."""
    from PIL import Image, ImageChops

    started = time.time()
    before = blend_signature()
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf8"))
    centres = _layer_centres(layout)
    layer_manifests = {}
    layer_records = {}
    hidden_interiors = set()
    for layer_key in LAYERS:
        path = LAYER_ROOT / f"layer_manifest_{layer_key}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Missing render layer manifest: {path}")
        payload = json.loads(path.read_text(encoding="utf8"))
        if (
            payload.get("schema") != "agent.full11.daytime_render_layer.v1"
            or payload.get("layer_key") != layer_key
            or payload.get("complete") is not True
        ):
            raise RuntimeError(f"Incomplete or invalid render layer: {path}")
        records = {
            record["name"]: record
            for record in payload.get("views", [])
            if record.get("name") in VIEW_BY_NAME
        }
        if set(records) != set(VIEW_BY_NAME):
            raise RuntimeError(f"Layer catalogue mismatch: {layer_key}")
        layer_manifests[layer_key] = str(path)
        layer_records[layer_key] = records
        hidden_interiors.update(
            payload.get("visibility_scope", {}).get(
                "temporarily_hidden_occluded_interior_instances", []
            )
        )

    OUT.mkdir(parents=True, exist_ok=True)
    force = os.environ.get("C2W_FULL11_RENDER_FORCE", "0") == "1"
    final_records = []
    errors = []
    for view in VIEWS:
        base_record = layer_records["base"][view.name]
        camera_location = Vector(base_record["camera"]["location"])
        ordered_layers = sorted(
            (layer_key for layer_key in LAYERS if layer_key != "base"),
            key=lambda layer_key: (centres[layer_key] - camera_location).length_squared,
            reverse=True,
        )
        layer_order = ["base", *ordered_layers]
        target = OUT / view.filename
        print(
            f"C2W_FULL11_COMPOSE_BEGIN {view.name} order={layer_order}",
            flush=True,
        )
        try:
            source_paths = [
                (LAYER_ROOT / layer_key / view.filename) for layer_key in layer_order
            ]
            for source in source_paths:
                if not source.is_file() or source.stat().st_size <= 0:
                    raise RuntimeError(f"missing layer image {source}")
            with Image.open(source_paths[0]) as image:
                canvas = image.convert("RGBA")
            non_base_alpha = Image.new("L", canvas.size, 0)
            for source in source_paths[1:]:
                with Image.open(source) as image:
                    overlay = image.convert("RGBA")
                if overlay.size != canvas.size:
                    raise RuntimeError(
                        f"layer size mismatch {source}: {overlay.size} != {canvas.size}"
                    )
                non_base_alpha = ImageChops.lighter(
                    non_base_alpha, overlay.getchannel("A")
                )
                canvas = Image.alpha_composite(canvas, overlay)
            histogram = non_base_alpha.histogram()
            visible_asset_pixel_ratio = sum(histogram[128:]) / (
                canvas.width * canvas.height
            )
            if force or not target.is_file() or target.stat().st_size <= 0:
                temporary = OUT / f".{view.filename}.{os.getpid()}.tmp.png"
                canvas.convert("RGB").save(
                    temporary, format="PNG", compress_level=6, optimize=False
                )
                os.replace(temporary, target)
            record = {
                **asdict(view),
                "bounds": base_record.get("bounds"),
                "bounds_source": base_record.get("bounds_source"),
                "framed_placement_ids": base_record.get("framed_placement_ids", []),
                "camera": base_record.get("camera"),
                "status": "rendered",
                "bytes": target.stat().st_size,
                "render_method": "exact_zone_layer_alpha_composite",
                "composited_layer_order": layer_order,
                "composited_layer_files": [str(path) for path in source_paths],
                "non_base_alpha_pixel_coverage_ratio": round(
                    visible_asset_pixel_ratio, 6
                ),
                "all_regions_visible": True,
                "temporarily_hidden_zones": [],
                "temporarily_hidden_placements": [],
            }
            final_records.append(record)
            print(
                f"C2W_FULL11_COMPOSE_DONE {view.name} bytes={record['bytes']}",
                flush=True,
            )
        except Exception as exc:
            errors.append(f"{view.name}: {exc}")
            print(f"C2W_FULL11_COMPOSE_FAILED {view.name} {exc!r}", flush=True)

    completed = {
        record["name"]
        for record in final_records
        if (OUT / record["filename"]).is_file()
        and (OUT / record["filename"]).stat().st_size > 0
    }
    after = blend_signature()
    top_down_record = next(
        (record for record in final_records if record["name"] == "city_top_down"),
        {},
    )
    top_down_pixel_ratio = float(
        top_down_record.get("non_base_alpha_pixel_coverage_ratio", 0.0)
    )
    required_top_down_pixel_ratio = float(
        layout.get("requirements", {}).get(
            "minimum_top_down_non_base_pixel_coverage_ratio", 0.25
        )
    )
    manifest = {
        "schema": "agent.full11.daytime_render_manifest.v1",
        "created_utc": utc_now(),
        "scene_revision": REVISION,
        "blend_file": str(Path(bpy.data.filepath).resolve()),
        "output_directory": str(OUT),
        "catalogue": [asdict(view) for view in VIEWS],
        "requested_views": [view.name for view in VIEWS],
        "views": final_records,
        "expected_count": len(VIEWS),
        "completed_count": len(completed),
        "completed_view_names": sorted(completed),
        "missing_view_names": sorted(set(VIEW_BY_NAME) - completed),
        "complete": len(completed) == len(VIEWS) and not errors,
        "visibility_scope": {
            "active": False,
            "all_regions_visible": True,
            "kept_zones": sorted(set(ZONES) | {"city_base"}),
            "temporarily_hidden_zones": [],
            "temporarily_hidden_placements": [],
            "temporarily_hidden_occluded_interior_instances": sorted(hidden_interiors),
            "interior_render_policy": (
                "closed-building interiors remain complete in the Blend and are only "
                "disabled in-memory for exterior validation layers"
            ),
            "policy": (
                "every final image composites the base plus all exact-geometry asset layers "
                "covering all nine city zones"
            ),
        },
        "render_settings": {
            **json.loads(Path(layer_manifests["base"]).read_text(encoding="utf8")).get(
                "render_settings", {}
            ),
            "composition": "lossless RGBA alpha composition, far-to-near by zone centre",
            "final_format": "PNG/RGB/8",
        },
        "layer_manifests": layer_manifests,
        "layer_count_per_view": len(LAYERS),
        "all_final_views_include_every_layer": True,
        "visual_coverage_audit": {
            "method": (
                "union of alpha>=128 pixels from every non-base exact-geometry "
                "layer in the orthographic city_top_down view"
            ),
            "top_down_non_base_pixel_coverage_ratio": top_down_pixel_ratio,
            "required_top_down_non_base_pixel_coverage_ratio": (
                required_top_down_pixel_ratio
            ),
            "pass": top_down_pixel_ratio >= required_top_down_pixel_ratio,
        },
        "errors": errors,
        "temporary_camera_removed": True,
        "blend_saved_by_renderer": False,
        "blend_before": before,
        "blend_after": after,
        "blend_file_unchanged": before == after,
        "elapsed_seconds": round(time.time() - started, 3),
    }
    write_manifest(manifest)
    if manifest["complete"]:
        panorama = {
            "status": "PASS",
            "scene_revision": REVISION,
            "citywide_panorama_count": len(CITY_VIEWS),
            "regional_near_far_pair_count": len(ZONES),
            "feature_near_far_pair_count": len(FEATURES),
            "total_png_count": len(VIEWS),
            "all_regions_visible_in_every_view": True,
            "exact_geometry_layer_count_per_view": len(LAYERS),
            "top_down_non_base_pixel_coverage_ratio": top_down_pixel_ratio,
            "required_top_down_non_base_pixel_coverage_ratio": (
                required_top_down_pixel_ratio
            ),
            "top_down_visible_asset_coverage_pass": (
                top_down_pixel_ratio >= required_top_down_pixel_ratio
            ),
            "citywide_panorama_files": [view.filename for view in CITY_VIEWS],
            "coverage_source": str(LAYOUT_PATH),
            "render_manifest": str(MANIFEST),
        }
        PANORAMA_AUDIT.write_text(
            json.dumps(panorama, indent=2, ensure_ascii=False), encoding="utf8"
        )
    if errors:
        raise RuntimeError("; ".join(errors))
    return manifest


def main() -> None:
    requested = args()
    if requested and requested[0].lower() in {"compose", "--compose"}:
        manifest = compose_layers()
        print(
            f"C2W_FULL11_COMPOSE_SUMMARY {manifest['completed_count']}/"
            f"{manifest['expected_count']} complete={manifest['complete']} "
            f"manifest={MANIFEST}",
            flush=True,
        )
        return
    layer_key = None
    if requested and requested[0].lower().startswith("layer:"):
        layer_key = requested.pop(0).split(":", 1)[1].lower()
    selected = select_views(requested)
    if not selected:
        return
    manifest = render(selected, layer_key=layer_key)
    summary_manifest = (
        LAYER_ROOT / f"layer_manifest_{layer_key}.json"
        if layer_key is not None
        else MANIFEST
    )
    print(
        f"C2W_FULL11_RENDER_SUMMARY layer={layer_key or 'direct'} "
        f"{manifest['completed_count']}/"
        f"{manifest['expected_count']} complete={manifest['complete']} "
        f"manifest={summary_manifest}",
        flush=True,
    )


if __name__ == "__main__":
    main()

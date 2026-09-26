"""Daytime batch renderer for the final ``urban_v1_full_10`` Blend.

The final Blend must already be open.  This script never loads or saves a
Blend; it creates temporary cameras/daylight state in memory, renders into the
``renders`` child directory, restores the scene, and atomically replaces its
manifest.  It reuses the production renderer's collection-instance discovery
and camera fitting logic.

Examples::

    blender --disable-depsgraph-on-file-load \
      -b ${WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_10/urban_v1_full_10.blend \
      --python scripts/render_urban_v1_full_10_daytime.py -- commercial

    # Exact views, a mixed batch, or the complete catalogue:
    ... -- commercial_near
    ... -- education_far park_near civic
    ... -- city
    ... -- all

``commercial`` expands to its near and far views.  Other zone names behave the
same way.  ``city``, ``regions``, ``near``, and ``far`` are batch aliases.  Set
``C2W_DAYTIME_ENGINE=EEVEE`` for Eevee; bounded Workbench is the default.
"""
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


import json
import math
import os
import re
import sys
import time
import fcntl
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import bpy
from mathutils import Vector


SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
import render_urban_v1_full_10 as base


CITY_ROOT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/" "outdoor_full_demo/urban_v1_full_10"
)
OUT = CITY_ROOT / "renders"
MANIFEST_SUFFIX = re.sub(
    r"[^A-Za-z0-9_.-]+",
    "_",
    os.environ.get("C2W_DAY_MANIFEST_SUFFIX", "").strip(),
).strip("._-")
MANIFEST = OUT / (
    f"render_manifest_{MANIFEST_SUFFIX}.json"
    if MANIFEST_SUFFIX
    else "render_manifest.json"
)
RESOLUTION = base.RESOLUTION
TEMP_PREFIX = "__full10_daytime_tmp__"
ZONES = tuple(base.CORE_ZONES)


@dataclass(frozen=True)
class ViewSpec:
    name: str
    filename: str
    kind: str
    zone: str | None
    direction: tuple[float, float, float]
    lens: float
    margin: float
    feature: str | None = None


CITY_VIEWS = (
    ViewSpec(
        "city_southwest",
        "01_city_southwest.png",
        "city",
        None,
        (-1.0, -1.0, 1.08),
        43.0,
        1.17,
    ),
    ViewSpec(
        "city_southeast",
        "02_city_southeast.png",
        "city",
        None,
        (1.0, -1.0, 1.08),
        43.0,
        1.17,
    ),
    ViewSpec(
        "city_northwest",
        "03_city_northwest.png",
        "city",
        None,
        (-1.0, 1.0, 1.08),
        43.0,
        1.17,
    ),
    ViewSpec(
        "city_northeast",
        "04_city_northeast.png",
        "city",
        None,
        (1.0, 1.0, 1.08),
        43.0,
        1.17,
    ),
    ViewSpec(
        "city_high_aerial",
        "05_city_high_aerial.png",
        "city",
        None,
        (0.12, -0.18, 1.0),
        47.0,
        1.20,
    ),
)

ZONE_DIRECTIONS = {
    "residential": ((0.65, -1.0, 0.90), (-0.25, -1.0, 0.40)),
    "commercial": ((-0.55, -1.0, 0.88), (0.20, 1.0, 0.26)),
    "park": ((0.80, -1.0, 0.96), (-0.45, -1.0, 0.28)),
    "leisure": ((-0.70, -1.0, 0.91), (-0.45, -1.0, 0.39)),
    "education": ((0.55, -1.0, 0.90), (0.12, -1.0, 0.39)),
    "civic": ((-0.55, -1.0, 0.88), (-0.10, -1.0, 0.37)),
    "health": ((0.62, -1.0, 0.91), (0.35, -1.0, 0.40)),
    "industrial": ((-0.72, -1.0, 0.88), (-0.30, -1.0, 0.37)),
    "roads": ((1.0, -1.0, 1.16), (0.82, -1.0, 0.56)),
}

EXPLICIT_NEAR_TARGETS = {
    "commercial_near": (0.0, 0.0, 4.5),
    "park_near": (125.0, 338.0, 3.0),
}

PREFERRED_NEAR_CATEGORIES = {
    "residential": ("residential", "delivery"),
    "commercial": ("commercial", "pharmacy", "bank", "atm"),
    "park": ("park", "fountain", "sculpture", "river"),
    "leisure": ("leisure", "fitness"),
    "education": ("school", "library"),
    "civic": ("fire_station", "police_station", "bank"),
    "health": ("hospital",),
    "industrial": ("factory", "gas_station"),
    "roads": ("intersection", "road"),
}


def _zone_views() -> tuple[ViewSpec, ...]:
    result: list[ViewSpec] = []
    number = 10
    for zone in ZONES:
        far_direction, near_direction = ZONE_DIRECTIONS[zone]
        result.append(
            ViewSpec(
                f"{zone}_far",
                f"{number:02d}_{zone}_far.png",
                "far",
                zone,
                far_direction,
                48.0,
                1.16,
            )
        )
        result.append(
            ViewSpec(
                f"{zone}_near",
                f"{number + 1:02d}_{zone}_near.png",
                "near",
                zone,
                near_direction,
                54.0,
                1.08,
            )
        )
        number += 2
    return tuple(result)


FEATURE_DEFINITIONS = (
    ("school", "education", ("school",)),
    ("library", "education", ("library",)),
    ("bank", "commercial", ("bank", "atm")),
    ("hospital", "health", ("hospital",)),
    ("gas_station", "industrial", ("gas_station",)),
    ("factory", "industrial", ("factory",)),
    ("fire_police", "civic", ("fire_station", "police_station")),
)
FEATURE_CATEGORIES = {
    name: categories for name, _zone, categories in FEATURE_DEFINITIONS
}
FEATURE_DIRECTIONS = {
    "school": ((0.55, -1.0, 0.88), (0.10, -1.0, 0.36)),
    "library": ((-0.55, -1.0, 0.88), (-0.15, -1.0, 0.36)),
    "bank": ((0.60, -1.0, 0.88), (0.15, -1.0, 0.36)),
    "hospital": ((-0.58, -1.0, 0.88), (-0.10, -1.0, 0.36)),
    "gas_station": ((0.85, -1.0, 0.86), (1.0, -0.12, 0.40)),
    "factory": ((-0.62, -1.0, 0.86), (-0.15, -1.0, 0.34)),
    "fire_police": ((0.90, -0.45, 0.86), (1.0, -0.12, 0.40)),
}


def _feature_views() -> tuple[ViewSpec, ...]:
    result: list[ViewSpec] = []
    number = 28
    for feature, zone, _categories in FEATURE_DEFINITIONS:
        far_direction, near_direction = FEATURE_DIRECTIONS[feature]
        result.extend(
            (
                ViewSpec(
                    f"{feature}_far",
                    f"{number:02d}_{feature}_far.png",
                    "feature_far",
                    zone,
                    far_direction,
                    50.0,
                    1.15,
                    feature,
                ),
                ViewSpec(
                    f"{feature}_near",
                    f"{number + 1:02d}_{feature}_near.png",
                    "feature_near",
                    zone,
                    near_direction,
                    56.0,
                    1.08,
                    feature,
                ),
            )
        )
        number += 2
    return tuple(result)


VIEW_SPECS = CITY_VIEWS + _zone_views() + _feature_views()
VIEW_BY_NAME = {view.name: view for view in VIEW_SPECS}


def _utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _script_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _expand_requests(args: Sequence[str]) -> tuple[list[ViewSpec], str]:
    tokens: list[str] = []
    for arg in args:
        tokens.extend(
            piece.strip().lower() for piece in arg.split(",") if piece.strip()
        )
    if any(token in {"list", "--list", "help", "--help"} for token in tokens):
        return [], "list"
    if any(token in {"verify", "--verify"} for token in tokens):
        return [], "verify"
    if not tokens or any(token in {"all", "*"} for token in tokens):
        return list(VIEW_SPECS), "render"

    aliases: dict[str, list[str]] = {
        "city": [view.name for view in CITY_VIEWS],
        "overview": [view.name for view in CITY_VIEWS],
        "panoramas": [view.name for view in CITY_VIEWS],
        "regions": [view.name for view in VIEW_SPECS if view.zone is not None],
        "zones": [view.name for view in VIEW_SPECS if view.zone is not None],
        "near": [view.name for view in VIEW_SPECS if view.kind.endswith("near")],
        "far": [view.name for view in VIEW_SPECS if view.kind.endswith("far")],
        "features": [view.name for view in VIEW_SPECS if view.feature is not None],
    }
    for zone in ZONES:
        aliases[zone] = [f"{zone}_far", f"{zone}_near"]
        aliases[f"zone:{zone}"] = aliases[zone]
    for feature, _zone, _categories in FEATURE_DEFINITIONS:
        aliases[feature] = [f"{feature}_far", f"{feature}_near"]
        aliases[f"feature:{feature}"] = aliases[feature]
    for view in VIEW_SPECS:
        aliases[view.name] = [view.name]
        aliases[view.filename.lower()] = [view.name]
        aliases[Path(view.filename).stem.lower()] = [view.name]

    names: list[str] = []
    unknown: list[str] = []
    for token in tokens:
        expanded = aliases.get(token)
        if expanded is None:
            unknown.append(token)
            continue
        for name in expanded:
            if name not in names:
                names.append(name)
    if unknown:
        raise RuntimeError(
            f"Unknown daytime view/group {unknown}; use '-- list' for the catalogue"
        )
    return [VIEW_BY_NAME[name] for name in names], "render"


def _print_catalogue() -> None:
    print(
        "[Full10Daytime] groups: all, city, regions, features, near, far, verify, "
        + ", ".join(ZONES)
    )
    for view in VIEW_SPECS:
        print(
            f"[Full10Daytime] view={view.name} file={view.filename} "
            f"kind={view.kind} zone={view.zone or 'all'} "
            f"feature={view.feature or '-'}"
        )


def _active_zones(views: Sequence[ViewSpec]) -> set[str] | None:
    if any(view.kind == "city" for view in views):
        return None
    return {"city_base", "roads"} | {
        view.zone for view in views if view.zone is not None
    }


def _feature_filters(views: Sequence[ViewSpec]) -> dict[str, set[str]]:
    """Return zones where only selected feature placements should stay visible."""
    full_zone_views = {
        view.zone for view in views if view.feature is None and view.zone is not None
    }
    filters: dict[str, set[str]] = {}
    for view in views:
        if view.feature is None or view.zone in full_zone_views or view.zone is None:
            continue
        filters.setdefault(view.zone, set()).add(view.feature)
    return filters


def _placement_zone(obj: bpy.types.Object) -> str:
    zone = str(obj.get("zone", "")).strip().lower()
    if zone:
        return zone
    for collection in obj.users_collection:
        if collection.name.startswith("full10:zone:"):
            return collection.name.split("full10:zone:", 1)[1].split(".", 1)[0].lower()
    return ""


def _placement_matches_features(obj: bpy.types.Object, features: set[str]) -> bool:
    category = str(obj.get("category", "")).strip().lower()
    text = " ".join(
        str(obj.get(key, "")).lower()
        for key in ("placement_id", "category", "source_collection", "source_path")
    )
    text = f"{obj.name.lower()} {text}"
    for feature in features:
        categories = FEATURE_CATEGORIES[feature]
        if category in categories or any(token in text for token in categories):
            return True
    return False


def _apply_placement_visibility_scope(
    filters: dict[str, set[str]],
) -> tuple[list[tuple[bpy.types.Object, bool, bool]], list[str]]:
    saved: list[tuple[bpy.types.Object, bool, bool]] = []
    hidden: list[str] = []
    if not filters:
        return saved, hidden
    for obj in bpy.context.scene.objects:
        if not (
            obj.name.startswith("full10:placement:")
            or (obj.get("placement_id") is not None and obj.get("zone") is not None)
        ):
            continue
        features = filters.get(_placement_zone(obj))
        if not features or _placement_matches_features(obj, features):
            continue
        saved.append((obj, bool(obj.hide_viewport), bool(obj.hide_render)))
        obj.hide_viewport = True
        obj.hide_render = True
        hidden.append(str(obj.get("placement_id", obj.name)))
    return saved, sorted(hidden)


def _restore_placement_visibility(
    saved: Sequence[tuple[bpy.types.Object, bool, bool]],
) -> None:
    for obj, hide_viewport, hide_render in saved:
        obj.hide_viewport = hide_viewport
        obj.hide_render = hide_render


class DaytimeDiscovery(base.SceneDiscovery):
    """Base discovery which omits temporarily hidden placement instances."""

    def discover_placements(self) -> None:
        candidates: list[tuple[bpy.types.Object, str]] = []
        for obj in bpy.context.scene.objects:
            if obj.hide_render or obj.hide_viewport:
                continue
            if not (
                obj.name.startswith("full10:placement:")
                or (obj.get("placement_id") is not None and obj.get("zone") is not None)
            ):
                continue
            zone = _placement_zone(obj)
            if self.active_zones is not None and zone not in self.active_zones:
                continue
            candidates.append((obj, zone))
        candidates.sort(
            key=lambda item: (item[1], str(item[0].get("placement_id", item[0].name)))
        )
        for obj, zone in candidates:
            record = {
                "name": obj.name,
                "placement_id": str(
                    obj.get("placement_id", obj.name.removeprefix("full10:placement:"))
                ),
                "category": str(obj.get("category", "")),
                "zone": zone,
                "source_path": str(obj.get("source_path", "")),
                "source_collection": str(obj.get("source_collection", "")),
                "footprint": base._plain(obj.get("footprint")),
                "bounds": self.instance_bounds(obj),
            }
            record["search_text"] = self._placement_text(record)
            self.placements.append(record)


def _bounds_area(bounds: base.Bounds) -> float:
    span = bounds[1] - bounds[0]
    return max(0.0, float(span.x)) * max(0.0, float(span.y))


def _pad_bounds(
    bounds: base.Bounds, ratio: float = 0.14, minimum: float = 3.0
) -> base.Bounds:
    lower, upper = bounds
    span = upper - lower
    pad_x = max(minimum, float(span.x) * ratio)
    pad_y = max(minimum, float(span.y) * ratio)
    pad_z = max(1.0, float(span.z) * 0.08)
    return (
        Vector((lower.x - pad_x, lower.y - pad_y, max(-5.0, lower.z - 0.2))),
        Vector((upper.x + pad_x, upper.y + pad_y, upper.z + pad_z)),
    )


def _inset_bounds(bounds: base.Bounds, xy_factor: float) -> base.Bounds:
    lower, upper = bounds
    center = (lower + upper) * 0.5
    half = (upper - lower) * 0.5
    half.x = max(8.0, half.x * xy_factor)
    half.y = max(8.0, half.y * xy_factor)
    return Vector((center.x - half.x, center.y - half.y, lower.z)), Vector(
        (center.x + half.x, center.y + half.y, upper.z)
    )


def _near_bounds(
    discovery: base.SceneDiscovery,
    zone: str,
) -> tuple[base.Bounds | None, list[str], str]:
    records = [
        record
        for record in discovery.placements
        if record["zone"] == zone and record["bounds"] is not None
    ]
    for category in PREFERRED_NEAR_CATEGORIES[zone]:
        matches = [
            record
            for record in records
            if str(record.get("category", "")).strip().lower() == category
        ]
        if matches:
            chosen = max(matches, key=lambda record: _bounds_area(record["bounds"]))
            return (
                _pad_bounds(chosen["bounds"]),
                [chosen["placement_id"]],
                f"largest preferred placement category={category}",
            )
    if records:
        chosen = max(records, key=lambda record: _bounds_area(record["bounds"]))
        return (
            _pad_bounds(chosen["bounds"]),
            [chosen["placement_id"]],
            "largest zone placement fallback",
        )
    zone_bounds = discovery.zone_bounds.get(zone)
    if zone_bounds is not None:
        factor = 0.38 if zone == "roads" else 0.58
        return _inset_bounds(zone_bounds, factor), [], "central zone crop fallback"
    return None, [], "no renderable zone bounds"


def _feature_records(
    discovery: base.SceneDiscovery,
    feature: str,
) -> list[dict[str, Any]]:
    categories = FEATURE_CATEGORIES[feature]
    records = []
    for record in discovery.placements:
        if record["bounds"] is None:
            continue
        category = str(record.get("category", "")).strip().lower()
        text = str(record.get("search_text", "")).lower()
        if category in categories or any(token in text for token in categories):
            records.append(record)
    return records


def _feature_bounds(
    discovery: base.SceneDiscovery,
    feature: str,
    near: bool,
) -> tuple[base.Bounds | None, list[str], str]:
    records = _feature_records(discovery, feature)
    if not records:
        return None, [], f"no placements matched feature={feature}"
    if near:
        grouped = records
        description = f"all placements in feature={feature}"
        if feature == "gas_station":
            grouped = [
                record for record in records if "gas_east_" in record["placement_id"]
            ]
            description = "east north/south gas-station pair"
        elif feature == "hospital":
            grouped = [
                record for record in records if "central" in record["placement_id"]
            ]
            description = "central hospital placement"
        if feature in {"fire_police", "gas_station", "factory", "bank", "hospital"}:
            grouped = grouped or records
            grouped_bounds = base._union_bounds(record["bounds"] for record in grouped)
            return (
                _pad_bounds(grouped_bounds, ratio=0.10, minimum=4.0),
                [record["placement_id"] for record in grouped],
                description,
            )
        chosen = max(records, key=lambda record: _bounds_area(record["bounds"]))
        return (
            _pad_bounds(chosen["bounds"], ratio=0.16, minimum=4.0),
            [chosen["placement_id"]],
            f"largest placement in feature={feature}",
        )
    return (
        base._union_bounds(record["bounds"] for record in records),
        [record["placement_id"] for record in records],
        f"all visible placements in feature={feature}",
    )


def _resolve_bounds(
    view: ViewSpec,
    discovery: base.SceneDiscovery,
) -> tuple[base.Bounds | None, list[str], str]:
    if view.kind == "city":
        return discovery.view_bounds("overview")
    if view.kind == "far":
        return discovery.view_bounds(f"zone:{view.zone}")
    if view.kind == "near" and view.zone is not None:
        return _near_bounds(discovery, view.zone)
    if view.kind == "feature_far" and view.feature is not None:
        return _feature_bounds(discovery, view.feature, near=False)
    if view.kind == "feature_near" and view.feature is not None:
        return _feature_bounds(discovery, view.feature, near=True)
    raise RuntimeError(f"Unsupported view specification: {view}")


def _fit_view_camera(
    camera: bpy.types.Object,
    bounds: base.Bounds,
    view: ViewSpec,
) -> dict[str, Any]:
    info = base._fit_camera(
        camera,
        bounds,
        view.direction,
        view.lens,
        view.margin,
    )
    explicit = EXPLICIT_NEAR_TARGETS.get(view.name)
    if explicit is None:
        return info
    previous_target = Vector(info["target"])
    target = Vector(explicit)
    # Retain the bounds-derived distance with a small allowance for shifting
    # the optical centre to the authored entrance/landmark ROI.
    distance = max(1.0, (camera.location - previous_target).length) * 1.12
    backward = Vector(view.direction).normalized()
    camera.location = target + backward * distance
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    info["target"] = base._round_vector(target)
    info["camera_location"] = base._round_vector(camera.location)
    info["explicit_target"] = True
    return info


def _choose_engine(scene: bpy.types.Scene) -> str:
    requested = (
        os.environ.get(
            "C2W_DAYTIME_ENGINE",
            os.environ.get("C2W_RENDER_ENGINE", "WORKBENCH"),
        )
        .strip()
        .upper()
    )
    if requested in {"WORKBENCH", "BLENDER_WORKBENCH"}:
        candidates = ("BLENDER_WORKBENCH",)
    elif requested in {"EEVEE", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        candidates = ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")
    else:
        raise RuntimeError("C2W_DAYTIME_ENGINE must be WORKBENCH or EEVEE")
    for candidate in candidates:
        try:
            scene.render.engine = candidate
            return candidate
        except (TypeError, ValueError):
            continue
    raise RuntimeError(f"No requested engine is available: {candidates}")


def _capture_day_state(scene: bpy.types.Scene) -> dict[str, Any]:
    shading = scene.display.shading
    state = {
        "base": base._capture_settings(scene),
        "world": scene.world,
        "color_depth": scene.render.image_settings.color_depth,
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
        "gamma": scene.view_settings.gamma,
    }
    for attribute in (
        "studio_light",
        "background_color",
        "cavity_type",
        "show_outline",
        "curvature_ridge_factor",
        "curvature_valley_factor",
    ):
        if hasattr(shading, attribute):
            state[f"shading:{attribute}"] = getattr(shading, attribute)
    return state


def _restore_day_state(scene: bpy.types.Scene, state: dict[str, Any]) -> None:
    base._restore_settings(scene, state["base"])
    scene.world = state["world"]
    scene.render.image_settings.color_depth = state["color_depth"]
    for attribute in ("view_transform", "look", "exposure", "gamma"):
        try:
            setattr(scene.view_settings, attribute, state[attribute])
        except (TypeError, ValueError):
            pass
    shading = scene.display.shading
    for key, value in state.items():
        if not key.startswith("shading:"):
            continue
        attribute = key.split(":", 1)[1]
        if hasattr(shading, attribute):
            try:
                setattr(shading, attribute, value)
            except (TypeError, ValueError):
                pass


def _set_if_available(owner: Any, attribute: str, value: Any) -> None:
    if hasattr(owner, attribute):
        try:
            setattr(owner, attribute, value)
        except (TypeError, ValueError):
            pass


def _configure_daytime(
    scene: bpy.types.Scene,
    temporary_collection: bpy.types.Collection,
) -> tuple[dict[str, Any], bpy.types.World | None]:
    engine = _choose_engine(scene)
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 25
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    _set_if_available(scene.view_settings, "view_transform", "AgX")
    _set_if_available(scene.view_settings, "look", "AgX - Medium High Contrast")
    scene.view_settings.exposure = 0.25
    scene.view_settings.gamma = 1.0

    temporary_world: bpy.types.World | None = None
    if engine == "BLENDER_WORKBENCH":
        shading = scene.display.shading
        _set_if_available(shading, "light", "STUDIO")
        _set_if_available(shading, "color_type", "MATERIAL")
        _set_if_available(shading, "background_type", "VIEWPORT")
        _set_if_available(shading, "background_color", (0.36, 0.56, 0.78))
        _set_if_available(shading, "show_shadows", True)
        _set_if_available(shading, "show_cavity", True)
        _set_if_available(shading, "cavity_type", "WORLD")
        _set_if_available(shading, "show_specular_highlight", True)
        _set_if_available(shading, "show_outline", False)
        _set_if_available(shading, "curvature_ridge_factor", 1.25)
        _set_if_available(shading, "curvature_valley_factor", 0.85)
        available_studios = {
            light.name
            for light in bpy.context.preferences.studio_lights
            if getattr(light, "type", "") == "STUDIO"
        }
        for candidate in ("outdoor.sl", "paint.sl", "rim.sl", "basic.sl"):
            if candidate in available_studios:
                _set_if_available(shading, "studio_light", candidate)
                break
    else:
        temporary_world = bpy.data.worlds.new(f"{TEMP_PREFIX}:world")
        temporary_world.use_nodes = True
        background = temporary_world.node_tree.nodes.get("Background")
        if background is not None:
            background.inputs["Color"].default_value = (0.38, 0.62, 0.94, 1.0)
            background.inputs["Strength"].default_value = 0.72
        scene.world = temporary_world

        sun_data = bpy.data.lights.new(f"{TEMP_PREFIX}:sun:data", type="SUN")
        sun_data.energy = 2.5
        sun_data.angle = math.radians(7.0)
        sun = bpy.data.objects.new(f"{TEMP_PREFIX}:sun", sun_data)
        temporary_collection.objects.link(sun)
        sun.rotation_euler = (
            math.radians(28.0),
            math.radians(-18.0),
            math.radians(-38.0),
        )
    return (
        {
            "engine": engine,
            "resolution": list(RESOLUTION),
            "format": "PNG/RGB/8",
            "look": "AgX daytime",
            "workbench_studio": getattr(scene.display.shading, "studio_light", None),
        },
        temporary_world,
    )


def _remove_temporary_data(
    collection: bpy.types.Collection | None,
    world: bpy.types.World | None,
) -> None:
    if collection is not None:
        for obj in list(collection.objects):
            data = obj.data
            object_type = obj.type
            bpy.data.objects.remove(obj, do_unlink=True)
            if data is not None and data.users == 0:
                if object_type == "CAMERA":
                    bpy.data.cameras.remove(data)
                elif object_type == "LIGHT":
                    bpy.data.lights.remove(data)
        bpy.data.collections.remove(collection, do_unlink=True)
    if world is not None and world.users == 0:
        bpy.data.worlds.remove(world)


def _file_signature() -> dict[str, Any] | None:
    if not bpy.data.filepath:
        return None
    path = Path(bpy.data.filepath)
    if not path.is_file():
        return {"path": str(path), "exists": False}
    stat = path.stat()
    return {
        "path": str(path),
        "exists": True,
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


@contextmanager
def _exclusive_lock(name: str):
    lock_directory = OUT / ".locks"
    lock_directory.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    lock_path = lock_directory / f"{safe_name}.lock"
    with lock_path.open("a+", encoding="utf8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _merge_manifest(
    existing: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    merged = dict(current)
    order = {view.name: index for index, view in enumerate(VIEW_SPECS)}
    views_by_name = {
        record.get("name"): record
        for record in existing.get("views", [])
        if record.get("name") in order
    }
    views_by_name.update(
        {
            record["name"]: record
            for record in current.get("views", [])
            if record.get("name") in order
        }
    )
    merged["views"] = sorted(
        views_by_name.values(), key=lambda record: order[record["name"]]
    )

    zones = dict(existing.get("zones", {}))
    for zone, record in current.get("zones", {}).items():
        if record.get("bounds") is not None or zone not in zones:
            zones[zone] = record
    merged["zones"] = zones

    placements = {
        record.get("placement_id"): record
        for record in existing.get("placements", [])
        if record.get("placement_id")
    }
    placements.update(
        {
            record.get("placement_id"): record
            for record in current.get("placements", [])
            if record.get("placement_id")
        }
    )
    merged["placements"] = sorted(
        placements.values(), key=lambda record: str(record.get("placement_id", ""))
    )

    history = list(existing.get("batch_history", []))[-99:]
    history.append(
        {
            "created_utc": current.get("created_utc"),
            "requested_views": current.get("requested_views", []),
            "errors": current.get("errors", []),
            "manifest_suffix": MANIFEST_SUFFIX or None,
        }
    )
    merged["batch_history"] = history
    merged["completed_view_names"] = [
        record["name"]
        for record in merged["views"]
        if record.get("status") in {"rendered", "existing"}
        and (OUT / record["filename"]).is_file()
        and (OUT / record["filename"]).stat().st_size > 0
    ]
    return merged


def _atomic_manifest(
    payload: dict[str, Any],
    path: Path = MANIFEST,
    merge_existing: bool = True,
) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    with _exclusive_lock(f"manifest_{path.name}"):
        if merge_existing and path.is_file():
            try:
                existing = json.loads(path.read_text(encoding="utf8"))
                if existing.get("schema") == payload.get("schema"):
                    payload = _merge_manifest(existing, payload)
            except (OSError, ValueError, TypeError):
                pass
        temporary = path.parent / f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp"
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
        )
        os.replace(temporary, path)


def _verify_manifest() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    prior_records: dict[str, dict[str, Any]] = {}
    source_manifests: list[str] = []
    for path in sorted(OUT.glob("render_manifest*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf8"))
        except (OSError, ValueError, TypeError):
            continue
        source_manifests.append(path.name)
        for record in payload.get("views", []):
            if record.get("name") in VIEW_BY_NAME:
                prior_records[record["name"]] = record

    records: list[dict[str, Any]] = []
    missing: list[str] = []
    for view in VIEW_SPECS:
        target = OUT / view.filename
        record = dict(prior_records.get(view.name, {}))
        record.update(
            {
                "name": view.name,
                "filename": view.filename,
                "kind": view.kind,
                "zone": view.zone,
                "feature": view.feature,
            }
        )
        if target.is_file() and target.stat().st_size > 0:
            record["status"] = "existing"
            record["bytes"] = target.stat().st_size
        else:
            record["status"] = "missing"
            record.pop("bytes", None)
            missing.append(view.name)
        records.append(record)

    catalogue = [
        {
            "name": view.name,
            "filename": view.filename,
            "kind": view.kind,
            "zone": view.zone,
            "feature": view.feature,
        }
        for view in VIEW_SPECS
    ]
    payload = {
        "schema": "agent.full10.daytime_render_manifest.v1",
        "created_utc": _utc_now(),
        "mode": "verify",
        "output_directory": str(OUT),
        "catalogue": catalogue,
        "views": records,
        "source_manifests": source_manifests,
        "expected_count": len(VIEW_SPECS),
        "existing_count": len(VIEW_SPECS) - len(missing),
        "missing_view_names": missing,
        "complete": not missing,
        "blend_file": _file_signature(),
        "blend_saved_by_renderer": False,
    }
    canonical = OUT / "render_manifest.json"
    _atomic_manifest(payload, path=canonical, merge_existing=False)
    print(
        f"[Full10Daytime] verify existing={len(VIEW_SPECS) - len(missing)}/"
        f"{len(VIEW_SPECS)} missing={missing} manifest={canonical}",
        flush=True,
    )


def _run(
    views: Sequence[ViewSpec],
    active_zones: set[str] | None,
    hidden_zones: Sequence[str],
    hidden_placements: Sequence[str],
    blend_before: dict[str, Any] | None,
    started: float,
) -> list[str]:
    print(
        f"[Full10Daytime] stage=discovery_begin "
        f"zones={sorted(active_zones) if active_zones is not None else 'all'}",
        flush=True,
    )
    discovery = DaytimeDiscovery(active_zones)
    discovery.discover()
    print(
        f"[Full10Daytime] stage=discovery_complete placements={len(discovery.placements)}",
        flush=True,
    )

    records: list[dict[str, Any]] = []
    for view in views:
        bounds, placement_ids, source = _resolve_bounds(view, discovery)
        records.append(
            {
                "name": view.name,
                "filename": view.filename,
                "kind": view.kind,
                "zone": view.zone,
                "feature": view.feature,
                "bounds": base._serialise_bounds(bounds),
                "bounds_source": source,
                "placement_ids": placement_ids,
                "status": "pending",
                "_bounds": bounds,
                "_view": view,
            }
        )

    scene = bpy.context.scene
    state = _capture_day_state(scene)
    temporary_collection: bpy.types.Collection | None = None
    temporary_world: bpy.types.World | None = None
    settings: dict[str, Any] = {}
    errors: list[str] = []
    try:
        old_collection = bpy.data.collections.get(f"{TEMP_PREFIX}:collection")
        if old_collection is not None:
            _remove_temporary_data(old_collection, None)
        temporary_collection = bpy.data.collections.new(f"{TEMP_PREFIX}:collection")
        scene.collection.children.link(temporary_collection)
        settings, temporary_world = _configure_daytime(scene, temporary_collection)
        print(
            f"[Full10Daytime] stage=render_config engine={settings['engine']} "
            f"resolution={RESOLUTION[0]}x{RESOLUTION[1]}",
            flush=True,
        )

        force = os.environ.get("C2W_DAYTIME_FORCE", "0") == "1"
        for record in records:
            bounds = record["_bounds"]
            view: ViewSpec = record["_view"]
            if bounds is None:
                record["status"] = "unavailable"
                errors.append(f"{view.name}: no renderable asset bounds")
                continue

            camera_data = bpy.data.cameras.new(f"{TEMP_PREFIX}:{view.name}:data")
            camera = bpy.data.objects.new(f"{TEMP_PREFIX}:{view.name}", camera_data)
            temporary_collection.objects.link(camera)
            record["camera"] = _fit_view_camera(camera, bounds, view)
            target = OUT / view.filename
            print(f"[Full10Daytime] stage=view_begin name={view.name}", flush=True)
            # Disjoint batches naturally write different files.  This lock also
            # makes an accidental duplicate view safe: the second worker
            # rechecks the PNG after the first worker releases it.
            with _exclusive_lock(f"view_{view.name}"):
                if not force and target.is_file() and target.stat().st_size > 0:
                    record["status"] = "existing"
                    record["bytes"] = target.stat().st_size
                    print(f"[Full10Daytime] existing={view.filename}", flush=True)
                    continue

                frame_started = time.time()
                try:
                    scene.camera = camera
                    scene.render.filepath = str(target)
                    bpy.ops.render.render(write_still=True)
                    if not target.is_file() or target.stat().st_size <= 0:
                        raise RuntimeError(f"render output missing or empty: {target}")
                    record["status"] = "rendered"
                    record["bytes"] = target.stat().st_size
                    record["seconds"] = round(time.time() - frame_started, 2)
                    print(
                        f"[Full10Daytime] rendered={view.filename} "
                        f"seconds={record['seconds']} bytes={record['bytes']}",
                        flush=True,
                    )
                except Exception as exc:
                    record["status"] = "failed"
                    record["error"] = repr(exc)
                    errors.append(f"{view.name}: {exc}")
                    print(
                        f"[Full10Daytime] failed={view.name} error={exc!r}",
                        flush=True,
                    )
    finally:
        for record in records:
            record.pop("_bounds", None)
            record.pop("_view", None)
        _restore_day_state(scene, state)
        _remove_temporary_data(temporary_collection, temporary_world)
        blend_after = _file_signature()
        catalogue = [
            {
                "name": view.name,
                "filename": view.filename,
                "kind": view.kind,
                "zone": view.zone,
                "feature": view.feature,
            }
            for view in VIEW_SPECS
        ]
        zone_summary = {
            zone: {
                "bounds": base._serialise_bounds(discovery.zone_bounds.get(zone)),
                "placement_ids": discovery.zone_placement_ids.get(zone, []),
            }
            for zone in ZONES
        }
        manifest = {
            "schema": "agent.full10.daytime_render_manifest.v1",
            "created_utc": _utc_now(),
            "output_directory": str(OUT),
            "requested_views": [view.name for view in views],
            "catalogue": catalogue,
            "visibility_scope": {
                "active": active_zones is not None,
                "kept_zones": (
                    sorted(active_zones)
                    if active_zones is not None
                    else list(ZONES) + ["city_base"]
                ),
                "temporarily_hidden_zones": list(hidden_zones),
                "temporarily_hidden_placements": list(hidden_placements),
            },
            "render_settings": settings,
            "zones": zone_summary,
            "placements": discovery.serialisable_placements(),
            "views": records,
            "errors": errors,
            "temporary_data_removed": True,
            "blend_saved_by_renderer": False,
            "blend_before": blend_before,
            "blend_after": blend_after,
            "blend_file_unchanged": blend_before == blend_after,
            "elapsed_seconds": round(time.time() - started, 2),
        }
        _atomic_manifest(manifest)
        print(
            f"[Full10Daytime] stage=cleanup temporary_data_removed=true "
            f"blend_unchanged={blend_before == blend_after}",
            flush=True,
        )
    return errors


def main() -> None:
    views, mode = _expand_requests(_script_args())
    if mode == "list":
        _print_catalogue()
        return
    if mode == "verify":
        _verify_manifest()
        return
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    blend_before = _file_signature()
    active_zones = _active_zones(views)
    saved_visibility, hidden_zones = base._apply_zone_visibility_scope(active_zones)
    feature_filters = _feature_filters(views)
    saved_placement_visibility, hidden_placements = _apply_placement_visibility_scope(
        feature_filters
    )
    print(
        f"[Full10Daytime] stage=zone_scope views={[view.name for view in views]} "
        f"keep={sorted(active_zones) if active_zones is not None else 'all'} "
        f"hidden_zones={hidden_zones} hidden_placements={len(hidden_placements)}",
        flush=True,
    )
    errors: list[str] = []
    try:
        update_started = time.time()
        print("[Full10Daytime] stage=depsgraph_update_begin", flush=True)
        bpy.context.view_layer.update()
        print(
            f"[Full10Daytime] stage=depsgraph_update_complete "
            f"seconds={time.time() - update_started:.2f}",
            flush=True,
        )
        errors = _run(
            views,
            active_zones,
            hidden_zones,
            hidden_placements,
            blend_before,
            started,
        )
    finally:
        _restore_placement_visibility(saved_placement_visibility)
        base._restore_zone_visibility(saved_visibility)
        print("[Full10Daytime] stage=zone_visibility_restored", flush=True)
    if errors:
        raise RuntimeError(
            "Daytime rendering completed with errors: " + "; ".join(errors)
        )
    rendered = sum(
        (OUT / view.filename).is_file() and (OUT / view.filename).stat().st_size > 0
        for view in views
    )
    print(
        f"[Full10Daytime] complete available_outputs={rendered}/{len(views)} "
        f"manifest={MANIFEST}",
        flush=True,
    )


if __name__ == "__main__":
    main()

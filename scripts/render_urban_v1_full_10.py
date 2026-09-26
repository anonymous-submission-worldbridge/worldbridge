"""Render read-only validation views for ``urban_v1_full_10``.

Open the final Blend first; this script deliberately does not load or save a
Blend file.  It discovers the generated ``full10:zone:*`` collections and
``full10:placement:*`` empties, derives cameras from their real world-space
bounds, renders missing PNGs, writes ``render_manifest.json``, and removes its
temporary cameras before exiting.

Examples::

    blender -b urban_v1_full_10.blend --python \
        scripts/render_urban_v1_full_10.py
    blender -b urban_v1_full_10.blend --python \
        scripts/render_urban_v1_full_10.py -- overview commercial park
    blender --disable-depsgraph-on-file-load -b urban_v1_full_10.blend \
        --python scripts/render_urban_v1_full_10.py -- commercial

Names after ``--`` may be view names, PNG filenames, or comma-separated lists.
The default engine is Workbench for predictable bounded-memory rendering.  Set
``C2W_RENDER_ENGINE=EEVEE`` to request Eevee instead.  A request that omits
``overview`` temporarily hides unrelated full10 zone roots before the first
depsgraph update, enabling bounded single-zone renders of the linked city.
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
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import bpy
from mathutils import Matrix, Vector


OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/" "outdoor_full_demo/urban_v1_full_10"
)
MANIFEST = OUT / "render_manifest.json"
TEMP_PREFIX = "__full10_render_tmp__"
RESOLUTION = (1280, 720)

# Validation/presentation geometry embedded in a few source Blends is not part
# of the placed city asset.  Normal parcel slabs and city terrain are retained.
NON_ASSET_NAME_TOKENS = (
    "validation",
    "calibration",
    "infinite_ground",
    "regional_ground",
    "municipal_ground",
    "presentation_context",
    "shadow_stage",
    "reference_backdrop",
    "reference_floor",
    "context_ground",
    "library4:site:ground",
)
GEOMETRY_TYPES = {"MESH", "CURVE", "SURFACE", "FONT", "META", "VOLUME"}

CORE_ZONES = (
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

# Twelve default outputs: one whole-city view and eleven asset-derived regional
# views.  This exceeds the requested overview + eight-region validation set.
VIEW_DEFINITIONS = (
    ("overview", "01_overview.png", "overview", (1.0, -1.0, 1.05), 50.0),
    (
        "residential",
        "02_residential.png",
        "zone:residential",
        (-0.25, -1.0, 0.72),
        52.0,
    ),
    ("commercial", "03_commercial.png", "zone:commercial", (0.25, -1.0, 0.68), 52.0),
    ("park", "04_park.png", "zone:park", (0.75, -1.0, 0.82), 52.0),
    ("leisure", "05_leisure.png", "zone:leisure", (-0.55, -1.0, 0.76), 52.0),
    ("education", "06_education.png", "zone:education", (0.20, -1.0, 0.70), 52.0),
    ("civic", "07_civic.png", "zone:civic", (-0.25, -1.0, 0.72), 52.0),
    ("health", "08_health.png", "zone:health", (0.45, -1.0, 0.74), 52.0),
    ("industrial", "09_industrial.png", "zone:industrial", (-0.35, -1.0, 0.70), 52.0),
    ("roads", "10_roads.png", "zone:roads", (1.0, -1.0, 1.20), 48.0),
    (
        "school_library",
        "11_school_library.png",
        "tokens:school,library",
        (0.10, -1.0, 0.66),
        54.0,
    ),
    (
        "emergency_services",
        "12_emergency_services.png",
        "tokens:fire,police",
        (-0.10, -1.0, 0.65),
        54.0,
    ),
)

VIEW_ZONE_HINTS = {
    "residential": {"residential"},
    "commercial": {"commercial"},
    "park": {"park"},
    "leisure": {"leisure"},
    "education": {"education"},
    "civic": {"civic"},
    "health": {"health"},
    "industrial": {"industrial"},
    "roads": {"roads"},
    "school_library": {"education"},
    "emergency_services": {"civic"},
}

ZONE_KEYWORDS = {
    "residential": ("residential", "housing", "apartment"),
    "commercial": ("commercial", "restaurant", "convenience", "pharmacy", "bar", "atm"),
    "park": ("park", "river", "fountain", "sculpture"),
    "leisure": (
        "leisure",
        "gymnasium",
        "athletics",
        "basketball",
        "playground",
        "fitness",
    ),
    "education": ("education", "school", "library"),
    "civic": ("civic", "bank", "police", "fire_station", "fire station"),
    "health": ("health", "hospital"),
    "industrial": ("industrial", "factory", "gas_station", "gas station", "gass"),
    "roads": ("roads", "road:", "street", "crosswalk", "traffic"),
}


Bounds = tuple[Vector, Vector]


def _now_utc() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def _plain(value: Any, depth: int = 0) -> Any:
    """Convert Blender ID properties to values accepted by json.dumps."""
    if depth > 8:
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping) or hasattr(value, "keys"):
        try:
            return {str(key): _plain(value[key], depth + 1) for key in value.keys()}
        except Exception:
            return str(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        try:
            return [_plain(item, depth + 1) for item in value]
        except Exception:
            return str(value)
    if hasattr(value, "to_list"):
        try:
            return [_plain(item, depth + 1) for item in value.to_list()]
        except Exception:
            pass
    return str(value)


def _finite_vector(value: Vector) -> bool:
    return all(math.isfinite(float(component)) for component in value)


def _bounds_from_points(points: Iterable[Vector]) -> Bounds | None:
    minimum = Vector((math.inf, math.inf, math.inf))
    maximum = Vector((-math.inf, -math.inf, -math.inf))
    count = 0
    for point in points:
        if not _finite_vector(point):
            continue
        for axis in range(3):
            minimum[axis] = min(minimum[axis], point[axis])
            maximum[axis] = max(maximum[axis], point[axis])
        count += 1
    if not count or not _finite_vector(minimum) or not _finite_vector(maximum):
        return None
    return minimum, maximum


def _union_bounds(items: Iterable[Bounds | None]) -> Bounds | None:
    points: list[Vector] = []
    for bounds in items:
        if bounds is not None:
            points.extend(bounds)
    return _bounds_from_points(points)


def _bounds_corners(bounds: Bounds) -> list[Vector]:
    minimum, maximum = bounds
    return [
        Vector((x, y, z))
        for x in (minimum.x, maximum.x)
        for y in (minimum.y, maximum.y)
        for z in (minimum.z, maximum.z)
    ]


def _transform_bounds(bounds: Bounds | None, matrix: Matrix) -> Bounds | None:
    if bounds is None:
        return None
    return _bounds_from_points(matrix @ corner for corner in _bounds_corners(bounds))


def _round_vector(vector: Vector) -> list[float]:
    return [round(float(value), 4) for value in vector]


def _serialise_bounds(bounds: Bounds | None) -> list[list[float]] | None:
    if bounds is None:
        return None
    return [_round_vector(bounds[0]), _round_vector(bounds[1])]


def _ignored_name(name: str) -> bool:
    lowered = name.lower()
    return any(token in lowered for token in NON_ASSET_NAME_TOKENS)


def _object_geometry_bounds(
    obj: bpy.types.Object, matrix: Matrix | None = None
) -> Bounds | None:
    if obj.type not in GEOMETRY_TYPES or obj.hide_render or _ignored_name(obj.name):
        return None
    try:
        corners = obj.bound_box
    except Exception:
        return None
    if not corners:
        return None
    transform = matrix if matrix is not None else obj.matrix_world
    return _bounds_from_points(transform @ Vector(corner) for corner in corners)


class SceneDiscovery:
    """Bounds/metadata cache for the already-open full10 scene."""

    def __init__(self, active_zones: set[str] | None = None) -> None:
        self.active_zones = None if active_zones is None else set(active_zones)
        self.collection_bounds_cache: dict[int, Bounds | None] = {}
        self.placements: list[dict[str, Any]] = []
        self.zone_bounds: dict[str, Bounds | None] = {}
        self.zone_placement_ids: dict[str, list[str]] = {}

    def collection_local_bounds(
        self,
        collection: bpy.types.Collection,
        stack: set[int] | None = None,
    ) -> Bounds | None:
        """Return collection bounds in the coordinates stored by its objects."""
        pointer = collection.as_pointer()
        if pointer in self.collection_bounds_cache:
            return self.collection_bounds_cache[pointer]
        stack = set() if stack is None else set(stack)
        if pointer in stack or collection.hide_render or _ignored_name(collection.name):
            return None
        stack.add(pointer)

        candidates: list[Bounds | None] = []
        # Walk direct objects and children separately so a hidden-render child
        # collection cannot pollute the bounds even when its objects themselves
        # have hide_render=False.  Collection instances are expanded below.
        for obj in collection.objects:
            if obj.hide_render or _ignored_name(obj.name):
                continue
            candidates.append(_object_geometry_bounds(obj, obj.matrix_world))
            if (
                obj.instance_type == "COLLECTION"
                and obj.instance_collection is not None
            ):
                nested = self.collection_local_bounds(obj.instance_collection, stack)
                offset = Matrix.Translation(
                    -Vector(obj.instance_collection.instance_offset)
                )
                candidates.append(_transform_bounds(nested, obj.matrix_world @ offset))
        for child_collection in collection.children:
            candidates.append(self.collection_local_bounds(child_collection, stack))

        result = _union_bounds(candidates)
        self.collection_bounds_cache[pointer] = result
        return result

    def instance_bounds(self, obj: bpy.types.Object) -> Bounds | None:
        candidates: list[Bounds | None] = [_object_geometry_bounds(obj)]
        if obj.instance_type == "COLLECTION" and obj.instance_collection is not None:
            local = self.collection_local_bounds(obj.instance_collection)
            offset = Matrix.Translation(
                -Vector(obj.instance_collection.instance_offset)
            )
            candidates.append(_transform_bounds(local, obj.matrix_world @ offset))

        # A placement may instead parent appended objects under an empty.
        pending = list(obj.children)
        seen: set[int] = set()
        while pending:
            child = pending.pop()
            pointer = child.as_pointer()
            if pointer in seen:
                continue
            seen.add(pointer)
            candidates.append(_object_geometry_bounds(child))
            if (
                child.instance_type == "COLLECTION"
                and child.instance_collection is not None
            ):
                local = self.collection_local_bounds(child.instance_collection)
                offset = Matrix.Translation(
                    -Vector(child.instance_collection.instance_offset)
                )
                candidates.append(_transform_bounds(local, child.matrix_world @ offset))
            pending.extend(child.children)
        return _union_bounds(candidates)

    @staticmethod
    def _placement_text(record: dict[str, Any]) -> str:
        fields = (
            record.get("name", ""),
            record.get("placement_id", ""),
            record.get("category", ""),
            record.get("zone", ""),
            record.get("source_path", ""),
            record.get("source_collection", ""),
        )
        return " ".join(str(value).lower() for value in fields)

    def discover_placements(self) -> None:
        candidates = []
        for obj in bpy.context.scene.objects:
            if not (
                obj.name.startswith("full10:placement:")
                or (obj.get("placement_id") is not None and obj.get("zone") is not None)
            ):
                continue
            zone = str(obj.get("zone", "")).strip().lower()
            if not zone:
                for collection in obj.users_collection:
                    if collection.name.startswith("full10:zone:"):
                        zone = (
                            collection.name.split("full10:zone:", 1)[1]
                            .split(".", 1)[0]
                            .lower()
                        )
                        break
            if self.active_zones is not None and zone not in self.active_zones:
                continue
            candidates.append((obj, zone))
        candidates.sort(
            key=lambda item: (item[1], str(item[0].get("placement_id", item[0].name)))
        )
        for obj, inferred_zone in candidates:
            zone = str(obj.get("zone", inferred_zone)).strip().lower() or inferred_zone
            placement_id = str(
                obj.get("placement_id", obj.name.removeprefix("full10:placement:"))
            )
            bounds = self.instance_bounds(obj)
            record = {
                "name": obj.name,
                "placement_id": placement_id,
                "category": str(obj.get("category", "")),
                "zone": zone,
                "source_path": str(obj.get("source_path", "")),
                "source_collection": str(obj.get("source_collection", "")),
                "footprint": _plain(obj.get("footprint")),
                "bounds": bounds,
            }
            record["search_text"] = self._placement_text(record)
            self.placements.append(record)

    def _zone_collection_bounds(self, zone: str) -> Bounds | None:
        collection = bpy.data.collections.get(f"full10:zone:{zone}")
        if collection is None or collection.hide_render:
            return None
        return self.collection_local_bounds(collection)

    def _keyword_fallback_bounds(self, zone: str) -> Bounds | None:
        keywords = ZONE_KEYWORDS[zone]
        candidates: list[Bounds | None] = []
        for obj in bpy.context.scene.objects:
            collection_names = " ".join(
                collection.name for collection in obj.users_collection
            )
            text = f"{obj.name} {collection_names}".lower()
            if not any(keyword in text for keyword in keywords):
                continue
            candidates.append(_object_geometry_bounds(obj))
            if (
                obj.instance_type == "COLLECTION"
                and obj.instance_collection is not None
            ):
                local = self.collection_local_bounds(obj.instance_collection)
                offset = Matrix.Translation(
                    -Vector(obj.instance_collection.instance_offset)
                )
                candidates.append(_transform_bounds(local, obj.matrix_world @ offset))
        return _union_bounds(candidates)

    def discover_zones(self) -> None:
        for zone in CORE_ZONES:
            if self.active_zones is not None and zone not in self.active_zones:
                self.zone_placement_ids[zone] = []
                self.zone_bounds[zone] = None
                continue
            records = [record for record in self.placements if record["zone"] == zone]
            self.zone_placement_ids[zone] = [
                record["placement_id"] for record in records
            ]
            bounds = _union_bounds(record["bounds"] for record in records)
            bounds = _union_bounds((bounds, self._zone_collection_bounds(zone)))
            if bounds is None:
                bounds = self._keyword_fallback_bounds(zone)
            self.zone_bounds[zone] = bounds

    def discover(self) -> None:
        self.discover_placements()
        self.discover_zones()
        zone_collections = [
            collection.name
            for collection in bpy.data.collections
            if collection.name.startswith("full10:zone:")
        ]
        if not self.placements and not zone_collections:
            raise RuntimeError(
                "The open Blend has no full10:placement:* objects or full10:zone:* collections; "
                "open the final urban_v1_full_10 Blend before running this script."
            )

    def token_bounds(self, tokens: Sequence[str]) -> tuple[Bounds | None, list[str]]:
        lowered = tuple(token.lower() for token in tokens)
        records = [
            record
            for record in self.placements
            if any(token in record["search_text"] for token in lowered)
        ]
        return (
            _union_bounds(record["bounds"] for record in records),
            [record["placement_id"] for record in records],
        )

    def view_bounds(self, selector: str) -> tuple[Bounds | None, list[str], str]:
        if selector == "overview":
            bounds = _union_bounds(self.zone_bounds[zone] for zone in CORE_ZONES)
            placement_ids = [record["placement_id"] for record in self.placements]
            return bounds, placement_ids, "all discovered city zones"
        if selector.startswith("zone:"):
            zone = selector.split(":", 1)[1]
            return (
                self.zone_bounds.get(zone),
                self.zone_placement_ids.get(zone, []),
                f"full10:zone:{zone}",
            )
        if selector.startswith("tokens:"):
            tokens = [token.strip() for token in selector.split(":", 1)[1].split(",")]
            bounds, placement_ids = self.token_bounds(tokens)
            # The two detail views remain useful with an older/incomplete
            # metadata build by falling back to their owning zone.
            if bounds is None and set(tokens) == {"school", "library"}:
                return (
                    self.zone_bounds.get("education"),
                    self.zone_placement_ids.get("education", []),
                    "education-zone fallback",
                )
            if bounds is None and set(tokens) == {"fire", "police"}:
                return (
                    self.zone_bounds.get("civic"),
                    self.zone_placement_ids.get("civic", []),
                    "civic-zone fallback",
                )
            return (
                bounds,
                placement_ids,
                f"placement metadata tokens: {', '.join(tokens)}",
            )
        raise ValueError(f"Unknown view selector: {selector}")

    def serialisable_placements(self) -> list[dict[str, Any]]:
        result = []
        for record in self.placements:
            result.append(
                {
                    key: (_serialise_bounds(value) if key == "bounds" else value)
                    for key, value in record.items()
                    if key != "search_text"
                }
            )
        return result


def _select_engine() -> str:
    requested = os.environ.get("C2W_RENDER_ENGINE", "BLENDER_WORKBENCH").strip().upper()
    if requested in {"WORKBENCH", "BLENDER_WORKBENCH"}:
        candidates = ("BLENDER_WORKBENCH",)
    elif requested in {"EEVEE", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        candidates = ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE")
    else:
        raise RuntimeError(
            "C2W_RENDER_ENGINE must be WORKBENCH/BLENDER_WORKBENCH or "
            "EEVEE/BLENDER_EEVEE_NEXT"
        )
    for engine in candidates:
        try:
            bpy.context.scene.render.engine = engine
            return engine
        except (TypeError, ValueError):
            continue
    raise RuntimeError(
        f"None of the requested render engines are available: {candidates}"
    )


def _capture_settings(scene: bpy.types.Scene) -> dict[str, Any]:
    shading = scene.display.shading
    return {
        "camera": scene.camera,
        "engine": scene.render.engine,
        "filepath": scene.render.filepath,
        "resolution_x": scene.render.resolution_x,
        "resolution_y": scene.render.resolution_y,
        "resolution_percentage": scene.render.resolution_percentage,
        "file_format": scene.render.image_settings.file_format,
        "color_mode": scene.render.image_settings.color_mode,
        "compression": scene.render.image_settings.compression,
        "film_transparent": scene.render.film_transparent,
        "use_file_extension": scene.render.use_file_extension,
        "shading_light": getattr(shading, "light", None),
        "shading_color_type": getattr(shading, "color_type", None),
        "shading_background_type": getattr(shading, "background_type", None),
        "shading_show_shadows": getattr(shading, "show_shadows", None),
        "shading_show_cavity": getattr(shading, "show_cavity", None),
        "shading_show_specular": getattr(shading, "show_specular_highlight", None),
    }


def _restore_settings(scene: bpy.types.Scene, saved: dict[str, Any]) -> None:
    scene.camera = saved["camera"]
    scene.render.engine = saved["engine"]
    scene.render.filepath = saved["filepath"]
    scene.render.resolution_x = saved["resolution_x"]
    scene.render.resolution_y = saved["resolution_y"]
    scene.render.resolution_percentage = saved["resolution_percentage"]
    scene.render.image_settings.file_format = saved["file_format"]
    scene.render.image_settings.color_mode = saved["color_mode"]
    scene.render.image_settings.compression = saved["compression"]
    scene.render.film_transparent = saved["film_transparent"]
    scene.render.use_file_extension = saved["use_file_extension"]
    shading = scene.display.shading
    for key, attribute in (
        ("shading_light", "light"),
        ("shading_color_type", "color_type"),
        ("shading_background_type", "background_type"),
        ("shading_show_shadows", "show_shadows"),
        ("shading_show_cavity", "show_cavity"),
        ("shading_show_specular", "show_specular_highlight"),
    ):
        if saved[key] is not None and hasattr(shading, attribute):
            try:
                setattr(shading, attribute, saved[key])
            except (TypeError, ValueError):
                pass


def _configure_render(scene: bpy.types.Scene) -> dict[str, Any]:
    engine = _select_engine()
    scene.render.resolution_x, scene.render.resolution_y = RESOLUTION
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.compression = 30
    scene.render.film_transparent = False
    scene.render.use_file_extension = True

    if engine == "BLENDER_WORKBENCH":
        shading = scene.display.shading
        for attribute, value in (
            ("light", "STUDIO"),
            ("color_type", "MATERIAL"),
            ("background_type", "WORLD"),
            ("show_shadows", True),
            ("show_cavity", True),
            ("show_specular_highlight", True),
        ):
            if hasattr(shading, attribute):
                try:
                    setattr(shading, attribute, value)
                except (TypeError, ValueError):
                    pass
    else:
        # Property names differ across Eevee generations.  Apply whichever
        # bounded sample control is available and otherwise keep Blender's
        # version-appropriate default.
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            for attribute in ("taa_render_samples", "taa_samples"):
                if hasattr(eevee, attribute):
                    try:
                        setattr(eevee, attribute, 16)
                    except (TypeError, ValueError):
                        pass
                    break
    return {"engine": engine, "resolution": list(RESOLUTION), "format": "PNG/RGB"}


def _fit_camera(
    camera: bpy.types.Object,
    bounds: Bounds,
    view_direction: Sequence[float],
    lens: float,
    margin: float,
) -> dict[str, Any]:
    minimum, maximum = bounds
    target = (minimum + maximum) * 0.5
    # Keep flat roads/grounds from producing a target exactly on the surface.
    if maximum.z - minimum.z < 1.0:
        target.z = maximum.z + 0.5

    backward = Vector(view_direction).normalized()  # target -> camera
    camera.rotation_euler = (-backward).to_track_quat("-Z", "Y").to_euler()
    data = camera.data
    data.type = "PERSP"
    data.lens = lens
    data.sensor_fit = "HORIZONTAL"
    data.sensor_width = 36.0

    aspect = RESOLUTION[0] / RESOLUTION[1]
    half_angle_x = math.atan((data.sensor_width * 0.5) / data.lens)
    half_angle_y = math.atan((data.sensor_width * 0.5 / aspect) / data.lens)
    tan_x = math.tan(half_angle_x)
    tan_y = math.tan(half_angle_y)
    inverse_rotation = camera.rotation_euler.to_matrix().inverted()

    required = 1.0
    for corner in _bounds_corners(bounds):
        local = inverse_rotation @ (corner - target)
        required = max(
            required,
            local.z + abs(local.x) / tan_x,
            local.z + abs(local.y) / tan_y,
        )
    spans = maximum - minimum
    distance = required * margin + max(2.0, max(spans) * 0.025)
    camera.location = target + backward * distance
    data.clip_start = max(0.05, distance / 10000.0)
    data.clip_end = max(1000.0, distance + spans.length * 4.0 + 100.0)
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    return {
        "target": _round_vector(target),
        "camera_location": _round_vector(camera.location),
        "lens_mm": round(float(lens), 3),
        "clip": [round(float(data.clip_start), 4), round(float(data.clip_end), 3)],
    }


def _normalise_requested(args: Sequence[str]) -> list[str]:
    names = [definition[0] for definition in VIEW_DEFINITIONS]
    aliases: dict[str, str] = {}
    for name, filename, _selector, _direction, _lens in VIEW_DEFINITIONS:
        for alias in (name, filename, Path(filename).stem, f"render_{name}"):
            aliases[alias.lower()] = name

    tokens: list[str] = []
    for arg in args:
        tokens.extend(piece.strip() for piece in arg.split(",") if piece.strip())
    if not tokens or any(token.lower() in {"all", "*"} for token in tokens):
        return names
    selected: list[str] = []
    unknown: list[str] = []
    for token in tokens:
        canonical = aliases.get(token.lower())
        if canonical is None:
            unknown.append(token)
        elif canonical not in selected:
            selected.append(canonical)
    if unknown:
        raise RuntimeError(
            f"Unknown full10 view name(s) {unknown}; available names: {names}"
        )
    return selected


def _script_args() -> list[str]:
    if "--" not in sys.argv:
        return []
    return sys.argv[sys.argv.index("--") + 1 :]


def _requested_zone_scope(selected_names: Sequence[str]) -> set[str] | None:
    """Return the minimal zone set, or None when the overview needs all zones."""
    if "overview" in selected_names:
        return None
    keep = {"roads", "city_base"}
    for name in selected_names:
        keep.update(VIEW_ZONE_HINTS.get(name, ()))
    return keep


def _apply_zone_visibility_scope(
    keep_zones: set[str] | None,
) -> tuple[list[tuple[bpy.types.Collection, bool, bool]], list[str]]:
    """Hide unrelated zone roots before Blender builds its first depsgraph."""
    if keep_zones is None:
        return [], []
    saved: list[tuple[bpy.types.Collection, bool, bool]] = []
    hidden: list[str] = []
    for collection in bpy.data.collections:
        if not collection.name.startswith("full10:zone:"):
            continue
        zone = collection.name.split("full10:zone:", 1)[1].split(".", 1)[0].lower()
        saved.append(
            (collection, bool(collection.hide_viewport), bool(collection.hide_render))
        )
        if zone not in keep_zones:
            collection.hide_viewport = True
            collection.hide_render = True
            hidden.append(zone)
    return saved, sorted(set(hidden))


def _restore_zone_visibility(
    saved: Sequence[tuple[bpy.types.Collection, bool, bool]],
) -> None:
    for collection, hide_viewport, hide_render in saved:
        collection.hide_viewport = hide_viewport
        collection.hide_render = hide_render


def _remove_temporary_collection(collection: bpy.types.Collection | None) -> None:
    if collection is None:
        return
    for obj in list(collection.objects):
        data = obj.data if obj.type == "CAMERA" else None
        bpy.data.objects.remove(obj, do_unlink=True)
        if data is not None and data.users == 0:
            bpy.data.cameras.remove(data)
    if collection.users == 0:
        bpy.data.collections.remove(collection)
    else:
        # do_unlink removes the scene link while also handling an interrupted
        # prior run whose temporary collection survived only in memory.
        bpy.data.collections.remove(collection, do_unlink=True)


def _write_manifest(payload: dict[str, Any]) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    temporary = MANIFEST.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    temporary.replace(MANIFEST)


def _render_selected(
    selected_names: Sequence[str],
    active_zones: set[str] | None,
    hidden_zones: Sequence[str],
    started: float,
) -> None:
    print(
        f"[Full10Render] stage=discovery_begin "
        f"active_zones={sorted(active_zones) if active_zones is not None else 'all'}",
        flush=True,
    )
    discovery = SceneDiscovery(active_zones)
    discovery.discover()

    view_records: list[dict[str, Any]] = []
    available_regions = 0
    for name, filename, selector, direction, lens in VIEW_DEFINITIONS:
        bounds, placement_ids, source = discovery.view_bounds(selector)
        if name in selected_names and name != "overview" and bounds is not None:
            available_regions += 1
        view_records.append(
            {
                "name": name,
                "filename": filename,
                "selector": selector,
                "bounds_source": source,
                "bounds": _serialise_bounds(bounds),
                "placement_ids": placement_ids,
                "_bounds_value": bounds,
                "_direction": direction,
                "_lens": lens,
                "status": "pending" if name in selected_names else "not_requested",
            }
        )
    requested_available = sum(
        record["name"] in selected_names and record["bounds"] is not None
        for record in view_records
    )
    print(
        f"[Full10Render] stage=discovery_complete placements={len(discovery.placements)} "
        f"requested_available={requested_available}/{len(selected_names)}",
        flush=True,
    )

    scene = bpy.context.scene
    saved_settings = _capture_settings(scene)
    temporary_collection: bpy.types.Collection | None = None
    render_settings: dict[str, Any] = {}
    errors: list[str] = []
    try:
        render_settings = _configure_render(scene)
        print(
            f"[Full10Render] stage=render_config engine={render_settings['engine']} "
            f"resolution={RESOLUTION[0]}x{RESOLUTION[1]}",
            flush=True,
        )
        existing = bpy.data.collections.get(f"{TEMP_PREFIX}:cameras")
        if existing is not None:
            _remove_temporary_collection(existing)
        temporary_collection = bpy.data.collections.new(f"{TEMP_PREFIX}:cameras")
        scene.collection.children.link(temporary_collection)

        for record in view_records:
            bounds = record.pop("_bounds_value")
            direction = record.pop("_direction")
            lens = record.pop("_lens")
            if bounds is None:
                record["status"] = "unavailable"
                if record["name"] in selected_names:
                    errors.append(f"{record['name']}: no real asset bounds")
                continue

            target = OUT / record["filename"]
            if record["name"] not in selected_names:
                if target.is_file() and target.stat().st_size > 0:
                    record["status"] = "existing_not_requested"
                    record["bytes"] = target.stat().st_size
                continue

            camera_data = bpy.data.cameras.new(f"{TEMP_PREFIX}:{record['name']}:data")
            camera = bpy.data.objects.new(
                f"{TEMP_PREFIX}:{record['name']}", camera_data
            )
            temporary_collection.objects.link(camera)
            record["camera"] = _fit_camera(
                camera,
                bounds,
                direction,
                lens,
                1.16 if record["name"] == "overview" else 1.10,
            )

            print(f"[Full10Render] stage=view_begin name={record['name']}", flush=True)
            if target.is_file() and target.stat().st_size > 0:
                record["status"] = "existing"
                record["bytes"] = target.stat().st_size
                print(f"[Full10Render] existing={record['filename']}", flush=True)
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
                    f"[Full10Render] rendered={record['filename']} "
                    f"seconds={record['seconds']} bytes={record['bytes']}",
                    flush=True,
                )
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = repr(exc)
                errors.append(f"{record['name']}: {exc}")
                print(
                    f"[Full10Render] failed={record['name']} error={exc!r}", flush=True
                )
    finally:
        # Build the manifest before clearing helper keys/cameras, then restore
        # every scene setting touched by this read-only render stage.
        for record in view_records:
            record.pop("_bounds_value", None)
            record.pop("_direction", None)
            record.pop("_lens", None)
        _restore_settings(scene, saved_settings)
        _remove_temporary_collection(temporary_collection)
        print(
            "[Full10Render] stage=render_cleanup temporary_cameras_removed=true",
            flush=True,
        )

        zone_summary = {
            zone: {
                "bounds": _serialise_bounds(discovery.zone_bounds[zone]),
                "placement_ids": discovery.zone_placement_ids[zone],
            }
            for zone in CORE_ZONES
        }
        manifest = {
            "schema": "agent.full10.render_manifest.v1",
            "created_utc": _now_utc(),
            "blend_file": bpy.data.filepath,
            "scene_revision": _plain(scene.get("c2w_revision")),
            "output_directory": str(OUT),
            "render_settings": render_settings,
            "requested_views": selected_names,
            "visibility_scope": {
                "active": active_zones is not None,
                "kept_zones": (
                    sorted(active_zones)
                    if active_zones is not None
                    else list(CORE_ZONES) + ["city_base"]
                ),
                "temporarily_hidden_zones": list(hidden_zones),
            },
            "temporary_cameras_removed": True,
            "blend_saved_by_renderer": False,
            "available_regional_views": available_regions,
            "placement_count": len(discovery.placements),
            "zones": zone_summary,
            "placements": discovery.serialisable_placements(),
            "views": view_records,
            "errors": errors,
            "elapsed_seconds": round(time.time() - started, 2),
        }
        _write_manifest(manifest)

    if errors:
        raise RuntimeError(
            "Full10 rendering completed with errors: " + "; ".join(errors)
        )
    rendered = sum(record["status"] == "rendered" for record in view_records)
    skipped = sum(
        record["status"] in {"existing", "existing_not_requested"}
        for record in view_records
    )
    print(
        f"[Full10Render] complete rendered={rendered} existing={skipped} "
        f"manifest={MANIFEST}",
        flush=True,
    )


def main() -> None:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    selected_names = _normalise_requested(_script_args())
    active_zones = _requested_zone_scope(selected_names)
    saved_visibility, hidden_zones = _apply_zone_visibility_scope(active_zones)
    print(
        f"[Full10Render] stage=zone_scope selected={list(selected_names)} "
        f"keep={sorted(active_zones) if active_zones is not None else 'all'} "
        f"hidden={hidden_zones}",
        flush=True,
    )
    try:
        # With --disable-depsgraph-on-file-load this is deliberately the first
        # depsgraph update: unrelated zone roots are already hidden, so Blender
        # evaluates only requested assets plus roads/city_base.  Placement
        # matrix_world values are reliable from this point onward.
        update_started = time.time()
        print("[Full10Render] stage=depsgraph_update_begin", flush=True)
        bpy.context.view_layer.update()
        print(
            f"[Full10Render] stage=depsgraph_update_complete "
            f"seconds={time.time() - update_started:.2f}",
            flush=True,
        )
        _render_selected(selected_names, active_zones, hidden_zones, started)
    finally:
        _restore_zone_visibility(saved_visibility)
        print("[Full10Render] stage=zone_visibility_restored", flush=True)


if __name__ == "__main__":
    main()

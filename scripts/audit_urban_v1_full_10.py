"""Strict read-only completion audit for ``urban_v1_full_10``.

Usage (Blender 4.5 is preferred)::

    ${BLENDER_BIN} -b /path/to/urban_v1_full_10.blend \
        --python scripts/audit_urban_v1_full_10.py --python-exit-code 1

The loaded Blend is never saved or edited.  The only files touched are
``strict_completion_audit.json`` and the ``SUCCESS`` sentinel next to the
opened Blend.  A stale SUCCESS is removed before auditing and is recreated
only when every strict check passes.

The preferred contract is one top-level collection-instance EMPTY per placed
asset.  Each placement carries these ID properties:

``placement_id, category, asset_type, zone, source_path, source_collection,
variant, footprint``.

``footprint`` is a JSON world-space AABB (``[xmin, ymin, xmax, ymax]``) or a
polygon.  The same records may be supplied in ``layout_plan.json`` and/or a
Blender Text datablock called ``GENERATION_MANIFEST``.  The parser accepts a
few older spelling variants, but provenance is deliberately required on the
actual placement EMPTY rather than only in the manifest.
"""
from __future__ import annotations

import ast
import itertools
import json
import math
import os
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import bpy


REVISION = "urban_v1_full_10"
REPO_ROOT = Path(__file__).resolve().parents[1]
FALLBACK_OUT = REPO_ROOT / "infinigen" / "outputs" / "outdoor_full_demo" / REVISION

EXPECTED_EXACT_COUNTS = {
    "residential": 3,
    "delivery": 3,
    "commercial": 1,
    "pharmacy": 2,
    "atm": 5,
    "park": 1,
    "river": 1,
    "sculpture": 1,
    "fountain": 1,
    "fitness": 2,
    "leisure": 1,
    "school": 1,
    "library": 1,
    "bank": 4,
    "hospital": 2,
    "gas_station": 3,
    "factory": 4,
    "fire_station": 2,
    "police_station": 3,
}

SOURCE_TOKENS = {
    "delivery": ("urban_v3_delivery6",),
    "commercial": ("urban_v3_all43_25",),
    "pharmacy": ("urban_v3_pharmacy5",),
    "atm": ("urban_v3_atm4",),
    "park": ("urban_v1_full_07-river5",),
    "river": ("urban_v1_full_07-river5",),
    "sculpture": ("urban_v1_full_07-river5",),
    "fountain": ("urban_v3_fountain3",),
    "fitness": ("urban_v3_fitness5",),
    "leisure": ("urban_v3_all44_14",),
    "school": ("urban_v3_school5",),
    "library": ("urban_v3_library4",),
    "bank": ("urban_v3_all46_5",),
    "hospital": ("urban_v3_hospital4",),
    "gas_station": ("urban_v3_gass4",),
    "factory": ("urban_v3_factory3",),
    "fire_station": ("urban_v3_fire5",),
    "police_station": ("urban_v3_police3",),
    "road": ("urban_v1_full_07-river5",),
    "intersection": ("urban_v1_full_07-river5",),
}

DELIVERY_SUBTYPES = {
    "parcel_locker",
    "food_locker",
    "delivery_station",
}

PLACEMENT_PROPERTY_ALIASES = {
    "placement_id": ("placement_id", "c2w_placement_id", "full10_placement_id"),
    "category": ("category", "placement_category", "c2w_category"),
    "asset_type": ("asset_type", "placement_type", "kind", "role"),
    "zone": ("zone", "district", "site", "area"),
    "source_path": (
        "source_path",
        "c2w_source_path",
        "source_blend",
        "source_file",
        "reference_path",
    ),
    "source_collection": (
        "source_collection",
        "c2w_source_collection",
        "source_collection_name",
        "reference_collection",
    ),
    "variant": ("variant", "asset_variant", "building_variant"),
    "footprint": ("footprint", "world_footprint", "footprint_world", "bounds"),
}


def _audit_scene() -> bpy.types.Scene:
    """Select the authored scene even when a library-written Blend opens with a UI fallback scene."""
    return bpy.data.scenes.get(REVISION) or bpy.context.scene


def _progress(message: str) -> None:
    print(f"C2W_AUDIT_STAGE {message}", flush=True)


def _output_dir() -> Path:
    override = os.environ.get("C2W_FULL10_OUTPUT")
    if override:
        return Path(override).expanduser().resolve()
    if bpy.data.filepath:
        return Path(bpy.data.filepath).resolve().parent
    return FALLBACK_OUT


def _jsonable(value: Any) -> Any:
    """Convert Blender IDProperty containers to ordinary JSON values."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, Mapping) or hasattr(value, "keys"):
        try:
            return {str(key): _jsonable(value[key]) for key in value.keys()}
        except (KeyError, TypeError, AttributeError):
            pass
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_jsonable(item) for item in value]
    try:
        return [_jsonable(item) for item in value]
    except TypeError:
        return str(value)


def _parse_structured(value: Any) -> Any:
    value = _jsonable(value)
    if not isinstance(value, str):
        return value
    stripped = value.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        try:
            return ast.literal_eval(stripped)
        except (SyntaxError, ValueError):
            return value


def _deep_merge(left: Any, right: Any) -> Any:
    if left == right:
        return left
    if isinstance(left, dict) and isinstance(right, dict):
        merged = dict(left)
        for key, value in right.items():
            merged[key] = _deep_merge(merged[key], value) if key in merged else value
        return merged
    if isinstance(left, list) and isinstance(right, list):
        # Placement arrays are reconciled later by placement_id.  Keeping both
        # here lets us detect conflicting or duplicate declarations.
        return left + right
    return right


def _load_manifest(out_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    merged: dict[str, Any] = {}
    sources: list[dict[str, Any]] = []

    for filename in (
        "layout_plan.json",
        "GENERATION_MANIFEST.json",
        "generation_manifest.json",
    ):
        path = out_dir / filename
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf8"))
        except Exception as exc:  # the malformed source is reported, not hidden
            sources.append({"kind": "file", "name": str(path), "error": repr(exc)})
            continue
        if isinstance(payload, dict):
            merged = _deep_merge(merged, payload)
            sources.append({"kind": "file", "name": str(path), "valid": True})
        else:
            sources.append({"kind": "file", "name": str(path), "valid": False})

    wanted_text_names = {
        "generation_manifest",
        "generation_manifest.json",
        "layout_plan",
        "layout_plan.json",
    }
    for text_block in bpy.data.texts:
        if text_block.name.lower() not in wanted_text_names:
            continue
        try:
            payload = json.loads(text_block.as_string())
        except Exception as exc:
            sources.append(
                {"kind": "text", "name": text_block.name, "error": repr(exc)}
            )
            continue
        if isinstance(payload, dict):
            merged = _deep_merge(merged, payload)
            sources.append({"kind": "text", "name": text_block.name, "valid": True})
        else:
            sources.append({"kind": "text", "name": text_block.name, "valid": False})

    scene = _audit_scene()
    for key in ("GENERATION_MANIFEST", "generation_manifest", "layout_plan"):
        if key not in scene:
            continue
        payload = _parse_structured(scene[key])
        if isinstance(payload, dict):
            merged = _deep_merge(merged, payload)
            sources.append({"kind": "scene_property", "name": key, "valid": True})
        else:
            sources.append({"kind": "scene_property", "name": key, "valid": False})

    return merged, sources


def _first(mapping: Mapping[str, Any], keys: Iterable[str], default: Any = None) -> Any:
    lower = {str(key).lower(): key for key in mapping.keys()}
    for key in keys:
        actual = lower.get(key.lower())
        if actual is not None:
            value = mapping[actual]
            if value is not None and value != "":
                return _parse_structured(value)
    return default


def _manifest_placements(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("placements", [])
    if isinstance(raw, Mapping):
        records = []
        for placement_id, value in raw.items():
            if not isinstance(value, Mapping):
                continue
            record = dict(_jsonable(value))
            record.setdefault("placement_id", str(placement_id))
            records.append(record)
        return records
    if isinstance(raw, list):
        return [dict(_jsonable(item)) for item in raw if isinstance(item, Mapping)]
    return []


def _object_property(obj: bpy.types.Object, canonical: str) -> Any:
    for key in PLACEMENT_PROPERTY_ALIASES[canonical]:
        if key in obj:
            return _parse_structured(obj[key])
    return None


def _is_placement_object(obj: bpy.types.Object) -> bool:
    if obj.type != "EMPTY":
        return False
    if _object_property(obj, "placement_id"):
        return True
    if bool(obj.get("is_placement") or obj.get("c2w_is_placement")):
        return True
    lowered = obj.name.lower()
    return (
        ("placement" in lowered or lowered.startswith("full10:"))
        and _object_property(obj, "source_path") is not None
        and _object_property(obj, "source_collection") is not None
    )


def _vector2(value: Any) -> tuple[float, float] | None:
    value = _parse_structured(value)
    if isinstance(value, Mapping):
        x = _first(value, ("x", "center_x", "cx", "min_x"))
        y = _first(value, ("y", "center_y", "cy", "min_y"))
        if isinstance(x, (int, float)) and isinstance(y, (int, float)):
            return float(x), float(y)
    if (
        isinstance(value, Sequence)
        and not isinstance(value, (str, bytes))
        and len(value) >= 2
    ):
        if isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
            return float(value[0]), float(value[1])
    return None


def _polygon_from_footprint(value: Any) -> list[tuple[float, float]] | None:
    value = _parse_structured(value)
    if value is None:
        return None
    if isinstance(value, Mapping):
        for key in ("polygon", "points", "vertices", "corners", "footprint"):
            if key in value:
                polygon = _polygon_from_footprint(value[key])
                if polygon:
                    return polygon
        for key in ("bounds", "aabb", "bbox", "world_aabb"):
            if key in value:
                polygon = _polygon_from_footprint(value[key])
                if polygon:
                    return polygon
        xmin = _first(value, ("xmin", "min_x", "left"))
        ymin = _first(value, ("ymin", "min_y", "bottom"))
        xmax = _first(value, ("xmax", "max_x", "right"))
        ymax = _first(value, ("ymax", "max_y", "top"))
        if all(isinstance(item, (int, float)) for item in (xmin, ymin, xmax, ymax)):
            return _rect_polygon(float(xmin), float(ymin), float(xmax), float(ymax))
        low = _vector2(_first(value, ("min", "minimum", "lower")))
        high = _vector2(_first(value, ("max", "maximum", "upper")))
        if low and high:
            return _rect_polygon(low[0], low[1], high[0], high[1])
        center = _vector2(_first(value, ("center", "location", "position")))
        size = _vector2(_first(value, ("size", "dimensions", "extent")))
        if center and size:
            return _rect_polygon(
                center[0] - size[0] / 2,
                center[1] - size[1] / 2,
                center[0] + size[0] / 2,
                center[1] + size[1] / 2,
            )
        return None
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return None
    if len(value) >= 3 and all(_vector2(item) is not None for item in value):
        return [_vector2(item) for item in value]  # type: ignore[list-item]
    if len(value) == 2 and all(_vector2(item) is not None for item in value):
        low = _vector2(value[0])
        high = _vector2(value[1])
        assert low is not None and high is not None
        return _rect_polygon(low[0], low[1], high[0], high[1])
    if len(value) >= 4 and all(isinstance(item, (int, float)) for item in value[:4]):
        # Standard GIS/graphics ordering: xmin, ymin, xmax, ymax.
        xmin, ymin, xmax, ymax = map(float, value[:4])
        return _rect_polygon(xmin, ymin, xmax, ymax)
    return None


def _rect_polygon(
    xmin: float, ymin: float, xmax: float, ymax: float
) -> list[tuple[float, float]] | None:
    if not all(math.isfinite(item) for item in (xmin, ymin, xmax, ymax)):
        return None
    if xmax <= xmin or ymax <= ymin:
        return None
    return [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]


def _polygon_bounds(
    polygon: Sequence[tuple[float, float]]
) -> tuple[float, float, float, float]:
    xs = [point[0] for point in polygon]
    ys = [point[1] for point in polygon]
    return min(xs), min(ys), max(xs), max(ys)


def _polygon_area(polygon: Sequence[tuple[float, float]]) -> float:
    return (
        abs(
            sum(
                polygon[index][0] * polygon[(index + 1) % len(polygon)][1]
                - polygon[(index + 1) % len(polygon)][0] * polygon[index][1]
                for index in range(len(polygon))
            )
        )
        / 2.0
    )


def _cross(
    a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]
) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _strict_segments_cross(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
    d: tuple[float, float],
    tolerance: float = 1e-7,
) -> bool:
    ab_c = _cross(a, b, c)
    ab_d = _cross(a, b, d)
    cd_a = _cross(c, d, a)
    cd_b = _cross(c, d, b)
    return ab_c * ab_d < -tolerance and cd_a * cd_b < -tolerance


def _point_strictly_inside(
    point: tuple[float, float], polygon: Sequence[tuple[float, float]]
) -> bool:
    inside = False
    x, y = point
    for index, a in enumerate(polygon):
        b = polygon[(index + 1) % len(polygon)]
        if abs(_cross(a, b, point)) <= 1e-7 and (
            min(a[0], b[0]) - 1e-7 <= x <= max(a[0], b[0]) + 1e-7
            and min(a[1], b[1]) - 1e-7 <= y <= max(a[1], b[1]) + 1e-7
        ):
            return False
        if (a[1] > y) != (b[1] > y):
            crossing_x = (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]
            if x < crossing_x:
                inside = not inside
    return inside


def _polygons_have_hard_overlap(
    first: Sequence[tuple[float, float]],
    second: Sequence[tuple[float, float]],
) -> bool:
    a = _polygon_bounds(first)
    b = _polygon_bounds(second)
    if min(a[2], b[2]) - max(a[0], b[0]) <= 1e-5:
        return False
    if min(a[3], b[3]) - max(a[1], b[1]) <= 1e-5:
        return False
    for index, start in enumerate(first):
        end = first[(index + 1) % len(first)]
        for other_index, other_start in enumerate(second):
            other_end = second[(other_index + 1) % len(second)]
            if _strict_segments_cross(start, end, other_start, other_end):
                return True
    return _point_strictly_inside(first[0], second) or _point_strictly_inside(
        second[0], first
    )


def _normal_text(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _delivery_subtype(text: str) -> str | None:
    if any(
        token in text
        for token in (
            "food_locker",
            "food_delivery_locker",
            "takeout_locker",
            "meal_locker",
            "waimai",
            "delivery cabinet",
        )
    ):
        return "food_locker"
    if any(
        token in text
        for token in (
            "parcel_locker",
            "express_locker",
            "courier_locker",
            "package_locker",
            "delivery box",
        )
    ):
        return "parcel_locker"
    if any(
        token in text
        for token in (
            "delivery_station",
            "express_station",
            "courier_station",
            "parcel_station",
            "post station",
        )
    ):
        return "delivery_station"
    return None


def _canonical_category(
    category: Any, asset_type: Any, placement_id: Any, object_name: Any
) -> str:
    category_text = _normal_text(category)
    asset_text = _normal_text(asset_type)
    identity_text = "_".join((_normal_text(placement_id), _normal_text(object_name)))
    explicit = "_".join((category_text, asset_text))
    all_text = "_".join((explicit, identity_text))

    if "park_sculpture" in explicit or "sculpture_nature" in explicit:
        return "park"

    subtype = _delivery_subtype(all_text)
    if subtype:
        return "delivery"

    aliases = (
        ("police_station", ("police", "police", "police")),
        ("fire_station", ("fire_station", "fire_department", "firehouse", "fire department")),
        (
            "gas_station",
            ("gas_station", "fuel_station", "petrol_station", "gass", "Go! Go! Go!"),
        ),
        ("pharmacy", ("pharmacy", "drugstore", "chemist", "pharmacy")),
        ("intersection", ("intersection", "crossroads", "junction", "intersection")),
        ("fountain", ("fountain", "fountain")),
        ("fitness", ("fitness", "exercise_area", "outdoor_gym", "Exercise")),
        ("hospital", ("hospital", "medical_center", "hospital")),
        ("factory", ("factory", "industrial_plant", "factory")),
        ("library", ("library", "library")),
        ("school", ("school", "campus", "school")),
        ("sculpture", ("sculpture", "statue", "monument", "sculpture")),
        ("residential", ("residential", "housing", "residence", "housing")),
        ("commercial", ("commercial", "retail_district", "shopping", "Business")),
        ("leisure", ("leisure", "recreation", "sports_precinct", "gymnasium", "recreation")),
        ("river", ("river", "waterway", "river")),
        ("park", ("park", "park")),
        ("bank", ("bank", "bank")),
        ("atm", ("atm", "cash_machine", "cashpoint")),
        ("road", ("road", "street_network", "roads", "Roads")),
        ("delivery", ("delivery", "courier", "express", "delivery service", "delivery order")),
    )
    # Explicit metadata wins over incidental words in placement names.
    for haystack in (explicit, all_text):
        for canonical, tokens in aliases:
            if any(token in haystack for token in tokens):
                return canonical
    return category_text or asset_text or "unclassified"


def _collection_tree(root: bpy.types.Collection) -> list[bpy.types.Collection]:
    result: list[bpy.types.Collection] = []
    visited: set[bpy.types.Collection] = set()

    def visit(collection: bpy.types.Collection) -> None:
        if collection in visited:
            return
        visited.add(collection)
        result.append(collection)
        for child in collection.children:
            visit(child)
        for obj in collection.objects:
            if obj.instance_type == "COLLECTION" and obj.instance_collection:
                visit(obj.instance_collection)

    visit(root)
    return result


def _instance_semantic_counts(obj: bpy.types.Object) -> dict[str, Any]:
    if obj.instance_type != "COLLECTION" or not obj.instance_collection:
        return {
            "atm_machine_count": 0,
            "fire_station_building_count": 0,
            "sculpture_count": 0,
        }
    collections = _collection_tree(obj.instance_collection)
    collection_names = [collection.name for collection in collections]
    objects = {member for collection in collections for member in collection.objects}

    atm_unit_names = sorted(
        {
            name
            for name in collection_names
            if any(
                token in _normal_text(name)
                for token in (
                    "atm_01a",
                    "atm_01b",
                    "atm_02",
                    "atm_03",
                    "atm_04",
                )
            )
            and "five_reference_atms" not in _normal_text(name)
        }
    )
    fire_station_names = sorted(
        {
            name
            for name in collection_names
            if any(
                token in _normal_text(name)
                for token in (
                    "station_civic_headquarters",
                    "station_industrial_annex",
                )
            )
        }
    )
    sculpture_names = sorted(
        {
            member.name
            for member in objects
            if member.instance_type == "COLLECTION"
            and any(
                token in _normal_text(member.name)
                for token in (
                    "public_art",
                    "sculpture",
                    "statue",
                    "monument",
                )
            )
        }
    )
    return {
        "atm_machine_count": len(atm_unit_names),
        "atm_unit_collections": atm_unit_names,
        "fire_station_building_count": len(fire_station_names),
        "fire_station_collections": fire_station_names,
        "sculpture_count": len(sculpture_names),
        "sculpture_objects": sculpture_names,
    }


def _record_from_object(
    obj: bpy.types.Object, plan: Mapping[str, Any] | None
) -> dict[str, Any]:
    plan = plan or {}
    placement_id = (
        _object_property(obj, "placement_id")
        or _first(plan, ("placement_id", "id"))
        or obj.name
    )
    category = _object_property(obj, "category") or _first(plan, ("category",))
    asset_type = _object_property(obj, "asset_type") or _first(
        plan, ("asset_type", "kind", "type", "role")
    )
    source_path = _object_property(obj, "source_path")
    source_collection = _object_property(obj, "source_collection")
    # Placements are deliberately unparented.  When Blender is launched with
    # --disable-depsgraph-on-file-load, matrix_world is an unevaluated identity
    # even though the persistent local transform is correct.  Read the stored
    # transform directly for these roots; fall back to matrix_world for parents.
    if obj.parent is None:
        world_location = obj.location
        world_scale = obj.scale
        yaw_deg = math.degrees(obj.rotation_euler.to_matrix().to_euler("XYZ").z) % 360.0
    else:
        world_location = obj.matrix_world.translation
        world_scale = obj.matrix_world.to_scale()
        yaw_deg = math.degrees(obj.matrix_world.to_euler("XYZ").z) % 360.0
    footprint_value = _object_property(obj, "footprint")
    if footprint_value is None:
        footprint_value = _first(
            plan, ("footprint", "world_footprint", "bounds", "aabb")
        )
    footprint = _polygon_from_footprint(footprint_value)
    if footprint:
        footprint_center = (
            sum(point[0] for point in footprint) / len(footprint),
            sum(point[1] for point in footprint) / len(footprint),
        )
    else:
        footprint_center = (float(world_location.x), float(world_location.y))
    semantic_content = _instance_semantic_counts(obj)
    metadata_keys = (
        "machine_count",
        "arrangement",
        "station_building_count",
        "contains_sculpture",
        "fountain_count",
        "station_count",
        "urban_role",
        "relation_role",
        "low_building_row",
        "bank_count_index",
        "collision_class",
        "traffic_clear",
        "crosswalk_orientation",
        "residential_area_index",
        "native_indoor_instance_count",
        "source_object_count",
        "interior_policy",
        "entry_direction_world",
        "front_direction_world",
        "entry_direction_local",
        "front_direction_local",
    )
    semantic_metadata = {
        key: _first(plan, (key,), obj.get(key))
        for key in metadata_keys
        if _first(plan, (key,), obj.get(key)) is not None
    }
    combined = {
        "placement_id": str(placement_id),
        "object_name": obj.name,
        "category_raw": category,
        "asset_type": asset_type,
        "category": _canonical_category(category, asset_type, placement_id, obj.name),
        "delivery_subtype": _delivery_subtype(
            "_".join(
                map(
                    _normal_text,
                    (
                        category,
                        asset_type,
                        placement_id,
                        obj.name,
                    ),
                )
            )
        ),
        "zone": _object_property(obj, "zone")
        or _first(plan, ("zone", "district", "site", "area")),
        "variant": _object_property(obj, "variant")
        or _first(plan, ("variant", "asset_variant")),
        "source_path": source_path,
        "source_collection": source_collection,
        "manifest_source_path": _first(plan, PLACEMENT_PROPERTY_ALIASES["source_path"]),
        "manifest_source_collection": _first(
            plan, PLACEMENT_PROPERTY_ALIASES["source_collection"]
        ),
        # The placement origin is deliberately translated by -source_center;
        # the footprint centroid is the stable world-space asset anchor.
        "position": [footprint_center[0], footprint_center[1], float(world_location.z)],
        "matrix_world_translation": [
            float(world_location.x),
            float(world_location.y),
            float(world_location.z),
        ],
        "yaw_degrees": yaw_deg,
        "local_scale": [float(value) for value in obj.scale],
        "world_scale": [float(value) for value in world_scale],
        "footprint": [[float(x), float(y)] for x, y in footprint]
        if footprint
        else None,
        "footprint_area": _polygon_area(footprint) if footprint else None,
        "collection_instance": bool(
            obj.instance_type == "COLLECTION" and obj.instance_collection
        ),
        "instance_collection": obj.instance_collection.name
        if obj.instance_collection
        else None,
        "users_collection": sorted(
            collection.name for collection in obj.users_collection
        ),
        "parent_id": _first(plan, ("parent_id", "host_id", "container_id")),
        "allow_overlap_with": _first(
            plan, ("allow_overlap_with", "overlap_exceptions"), []
        ),
        "collision_class": _first(
            plan, ("collision_class",), obj.get("collision_class", "asset")
        ),
        "semantic_metadata": semantic_metadata,
        "semantic_content": semantic_content,
    }
    return combined


def _record_from_missing_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    placement_id = _first(plan, ("placement_id", "id", "name"), "<missing-id>")
    category = _first(plan, ("category",))
    asset_type = _first(plan, ("asset_type", "kind", "type", "role"))
    footprint = _polygon_from_footprint(_first(plan, ("footprint", "bounds", "aabb")))
    position = _vector2(_first(plan, ("position", "location", "center")))
    return {
        "placement_id": str(placement_id),
        "object_name": None,
        "category_raw": category,
        "asset_type": asset_type,
        "category": _canonical_category(category, asset_type, placement_id, ""),
        "delivery_subtype": _delivery_subtype(
            "_".join(map(_normal_text, (category, asset_type, placement_id)))
        ),
        "zone": _first(plan, ("zone", "district", "site", "area")),
        "variant": _first(plan, ("variant", "asset_variant")),
        "source_path": None,
        "source_collection": None,
        "manifest_source_path": _first(plan, PLACEMENT_PROPERTY_ALIASES["source_path"]),
        "manifest_source_collection": _first(
            plan, PLACEMENT_PROPERTY_ALIASES["source_collection"]
        ),
        "position": [position[0], position[1], 0.0] if position else None,
        "matrix_world_translation": None,
        "yaw_degrees": _first(plan, ("yaw_degrees", "yaw_deg", "heading_degrees")),
        "local_scale": None,
        "world_scale": None,
        "footprint": [[float(x), float(y)] for x, y in footprint]
        if footprint
        else None,
        "footprint_area": _polygon_area(footprint) if footprint else None,
        "collection_instance": False,
        "instance_collection": None,
        "users_collection": [],
        "parent_id": _first(plan, ("parent_id", "host_id", "container_id")),
        "allow_overlap_with": _first(
            plan, ("allow_overlap_with", "overlap_exceptions"), []
        ),
        "collision_class": _first(plan, ("collision_class",), "asset"),
        "semantic_metadata": {},
        "semantic_content": {},
    }


def _collect_records(
    manifest: Mapping[str, Any]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    plans = _manifest_placements(manifest)
    plan_by_id: dict[str, dict[str, Any]] = {}
    duplicate_plan_ids: list[str] = []
    for plan in plans:
        placement_id = str(_first(plan, ("placement_id", "id", "name"), ""))
        if not placement_id:
            duplicate_plan_ids.append("<missing-id>")
            continue
        if placement_id in plan_by_id:
            duplicate_plan_ids.append(placement_id)
        else:
            plan_by_id[placement_id] = plan

    placement_objects = [
        obj for obj in _audit_scene().objects if _is_placement_object(obj)
    ]
    object_by_id: dict[str, bpy.types.Object] = {}
    duplicate_object_ids: list[str] = []
    for obj in placement_objects:
        placement_id = str(_object_property(obj, "placement_id") or obj.name)
        if placement_id in object_by_id:
            duplicate_object_ids.append(placement_id)
        else:
            object_by_id[placement_id] = obj

    records = [
        _record_from_object(obj, plan_by_id.get(placement_id))
        for placement_id, obj in sorted(object_by_id.items())
    ]
    missing_objects = sorted(set(plan_by_id) - set(object_by_id))
    records.extend(
        _record_from_missing_plan(plan_by_id[key]) for key in missing_objects
    )
    unmanifested_objects = sorted(set(object_by_id) - set(plan_by_id))
    reconciliation = {
        "manifest_placement_count": len(plans),
        "unique_manifest_placement_count": len(plan_by_id),
        "scene_placement_empty_count": len(placement_objects),
        "unique_scene_placement_count": len(object_by_id),
        "duplicate_manifest_ids": sorted(duplicate_plan_ids),
        "duplicate_scene_ids": sorted(duplicate_object_ids),
        "missing_scene_objects": missing_objects,
        "unmanifested_scene_objects": unmanifested_objects,
    }
    return records, reconciliation


def _resolve_source_path(value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    cleaned = value.strip().split("#", 1)[0].split("::", 1)[0]
    if cleaned.startswith(("generated:", "embedded:", "bpy:")):
        return None
    path = Path(cleaned).expanduser()
    candidates = (
        [path] if path.is_absolute() else [REPO_ROOT / path, FALLBACK_OUT / path]
    )
    return next(
        (candidate.resolve() for candidate in candidates if candidate.exists()), None
    )


def _source_collection_traceable(record: Mapping[str, Any]) -> bool:
    expected = _normal_text(record.get("source_collection"))
    actual_name = record.get("instance_collection")
    if not expected or not actual_name:
        return False
    actual = bpy.data.collections.get(str(actual_name))
    if actual is None:
        return False
    actual_normal = _normal_text(actual.name).removesuffix("_001")
    expected_base = expected.removesuffix("_001")
    if expected_base in actual_normal or actual_normal in expected_base:
        return True
    for key in PLACEMENT_PROPERTY_ALIASES["source_collection"]:
        if key in actual and _normal_text(actual[key]) == expected:
            return True
    linked_datablocks: list[Any] = []
    for collection in _collection_tree(actual):
        linked_datablocks.append(collection)
        linked_datablocks.extend(collection.objects)
    resolved_source = _resolve_source_path(record.get("source_path"))
    if resolved_source and any(
        datablock.library is not None
        and Path(bpy.path.abspath(datablock.library.filepath)).resolve()
        == resolved_source
        for datablock in linked_datablocks
    ):
        return True
    # A faithfully appended collection can be prefixed for namespace safety;
    # carrying the same source_path on the collection preserves the chain.
    expected_path = _normal_text(record.get("source_path"))
    return any(
        key in actual and _normal_text(actual[key]) == expected_path
        for key in PLACEMENT_PROPERTY_ALIASES["source_path"]
    )


def _reachable_render_objects() -> set[bpy.types.Object]:
    objects: set[bpy.types.Object] = set()
    visited: set[bpy.types.Collection] = set()

    def visit(collection: bpy.types.Collection) -> None:
        if collection in visited:
            return
        visited.add(collection)
        for obj in collection.objects:
            if obj.hide_render:
                continue
            objects.add(obj)
            if obj.instance_type == "COLLECTION" and obj.instance_collection:
                visit(obj.instance_collection)
        for child in collection.children:
            visit(child)

    visit(_audit_scene().collection)
    return objects


def _indoor_instances(objects: Iterable[bpy.types.Object]) -> list[dict[str, Any]]:
    matches = []
    for obj in objects:
        if (
            obj.type != "EMPTY"
            or obj.instance_type != "COLLECTION"
            or not obj.instance_collection
        ):
            continue
        tokens = [obj.name, obj.instance_collection.name]
        for datablock in (obj, obj.instance_collection):
            for key in datablock.keys():
                value = datablock[key]
                if "indoor" in str(key).lower() or "interior" in str(key).lower():
                    if value not in (False, None, "", 0):
                        tokens.extend((str(key), str(value)))
        combined = " ".join(tokens).lower()
        if "indoor" in combined or "interior_instance" in combined or "in indoor areas" in combined:
            matches.append(
                {
                    "object": obj.name,
                    "collection": obj.instance_collection.name,
                }
            )
    unique = {(item["object"], item["collection"]): item for item in matches}
    return [unique[key] for key in sorted(unique)]


def _mesh_is_authored(obj: bpy.types.Object) -> bool:
    if obj.type != "MESH" or not obj.data:
        return True
    procedural_host = bool(
        any(
            modifier.type == "NODES" and modifier.show_render
            for modifier in obj.modifiers
        )
        or obj.get("c2w_direct_infinigen_asset")
        or obj.get("native_infinigen_asset")
    )
    if not obj.data.vertices:
        return procedural_host
    corners = obj.bound_box
    extents = [
        max(float(corner[axis]) for corner in corners)
        - min(float(corner[axis]) for corner in corners)
        for axis in range(3)
    ]
    return sum(extent > 1e-7 for extent in extents) >= 2 or procedural_host


def _distance(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    a = first["position"]
    b = second["position"]
    return math.hypot(float(a[0]) - float(b[0]), float(a[1]) - float(b[1]))


def _distance_to_point(record: Mapping[str, Any], point: tuple[float, float]) -> float:
    position = record["position"]
    return math.hypot(float(position[0]) - point[0], float(position[1]) - point[1])


def _angular_difference(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _opposition_error(first: Mapping[str, Any], second: Mapping[str, Any]) -> float:
    return abs(
        180.0
        - _angular_difference(float(first["yaw_degrees"]), float(second["yaw_degrees"]))
    )


def _line_metrics(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if len(records) < 2:
        return {"valid": False, "reason": "fewer than two points"}
    endpoints = max(
        itertools.combinations(records, 2), key=lambda pair: _distance(pair[0], pair[1])
    )
    ax, ay = map(float, endpoints[0]["position"][:2])
    bx, by = map(float, endpoints[1]["position"][:2])
    span = math.hypot(bx - ax, by - ay)
    if span <= 1e-7:
        return {"valid": False, "reason": "all points coincide", "span_m": span}
    ux, uy = (bx - ax) / span, (by - ay) / span
    projections = []
    deviations = []
    for record in records:
        px, py = map(float, record["position"][:2])
        projections.append((px - ax) * ux + (py - ay) * uy)
        deviations.append(abs((px - ax) * uy - (py - ay) * ux))
    projections.sort()
    gaps = [
        projections[index + 1] - projections[index]
        for index in range(len(projections) - 1)
    ]
    yaws = [float(record["yaw_degrees"]) for record in records]
    return {
        "valid": True,
        "span_m": span,
        "max_perpendicular_deviation_m": max(deviations),
        "min_adjacent_gap_m": min(gaps, default=0.0),
        "max_adjacent_gap_m": max(gaps, default=0.0),
        "max_pairwise_yaw_difference_deg": max(
            (
                _angular_difference(first, second)
                for first, second in itertools.combinations(yaws, 2)
            ),
            default=0.0,
        ),
        "endpoint_ids": [endpoints[0]["placement_id"], endpoints[1]["placement_id"]],
    }


def _by_category(records: Iterable[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("object_name"):
            grouped[record["category"]].append(record)
            if (
                record["category"] == "park"
                and int(record.get("semantic_content", {}).get("sculpture_count", 0))
                > 0
            ):
                grouped["sculpture"].append(record)
    return grouped


def _relations(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = manifest.get("relationships", [])
    if isinstance(raw, list):
        return [dict(_jsonable(value)) for value in raw if isinstance(value, Mapping)]
    if isinstance(raw, Mapping):
        results = []
        for name, value in raw.items():
            if isinstance(value, Mapping):
                relation = dict(_jsonable(value))
                relation.setdefault("relationship_id", str(name))
                relation.setdefault("type", str(name))
                results.append(relation)
            elif isinstance(value, list):
                results.append(
                    {
                        "relationship_id": str(name),
                        "type": str(name),
                        "members": _jsonable(value),
                    }
                )
        return results
    return []


def _relation_ids(relation: Mapping[str, Any]) -> set[str]:
    values: list[Any] = []
    for key in ("members", "placements", "objects", "placement_ids", "pair"):
        value = relation.get(key)
        if isinstance(value, (list, tuple)):
            values.extend(value)
    for key in ("a", "b", "from", "to", "first", "second", "subject", "object"):
        if key in relation:
            value = relation[key]
            if isinstance(value, (list, tuple)):
                values.extend(value)
            else:
                values.append(value)
    ids = set()
    for value in values:
        if isinstance(value, Mapping):
            value = _first(value, ("placement_id", "id", "name"))
        if value not in (None, ""):
            ids.add(str(value))
    return ids


def _declares_across_road(
    relationships: Sequence[Mapping[str, Any]],
    first_id: str,
    second_id: str,
) -> bool:
    wanted = {str(first_id), str(second_id)}
    for relation in relationships:
        relation_type = _normal_text(
            _first(relation, ("type", "relation", "kind", "relationship_id", "id"))
        )
        if not any(
            token in relation_type for token in ("opposite", "across_road", "facing")
        ):
            continue
        if wanted <= _relation_ids(relation):
            return True
    return False


def _road_polygons(manifest: Mapping[str, Any]) -> list[list[tuple[float, float]]]:
    network = manifest.get("road_network", {})
    if not isinstance(network, Mapping):
        return []
    values: list[Any] = []
    for key in (
        "drivable_polygons",
        "road_polygons",
        "corridors",
        "clear_zones",
        "carriageways",
        "lanes",
    ):
        candidate = network.get(key)
        if isinstance(candidate, list):
            values.extend(candidate)
        elif candidate is not None:
            values.append(candidate)
    polygons = []
    for value in values:
        polygon = _polygon_from_footprint(value)
        if polygon:
            polygons.append(polygon)
    horizontal_y = network.get("horizontal_y")
    vertical_x = network.get("vertical_x")
    grid_x = network.get("grid_x")
    grid_y = network.get("grid_y")
    half_width = network.get("half_width_with_sidewalk_m")
    module_length = network.get("module_length_m")
    if (
        isinstance(horizontal_y, list)
        and isinstance(vertical_x, list)
        and isinstance(grid_x, list)
        and isinstance(grid_y, list)
        and isinstance(half_width, (int, float))
        and isinstance(module_length, (int, float))
        and grid_x
        and grid_y
    ):
        xmin = min(map(float, grid_x)) - float(module_length) / 2.0
        xmax = max(map(float, grid_x)) + float(module_length) / 2.0
        ymin = min(map(float, grid_y)) - float(module_length) / 2.0
        ymax = max(map(float, grid_y)) + float(module_length) / 2.0
        for coordinate in horizontal_y:
            polygon = _rect_polygon(
                xmin,
                float(coordinate) - float(half_width),
                xmax,
                float(coordinate) + float(half_width),
            )
            if polygon:
                polygons.append(polygon)
        for coordinate in vertical_x:
            polygon = _rect_polygon(
                float(coordinate) - float(half_width),
                ymin,
                float(coordinate) + float(half_width),
                ymax,
            )
            if polygon:
                polygons.append(polygon)
    return polygons


def _segment_touches_polygon(
    start: tuple[float, float],
    end: tuple[float, float],
    polygon: Sequence[tuple[float, float]],
) -> bool:
    if _point_strictly_inside(start, polygon) or _point_strictly_inside(end, polygon):
        return True
    for index, first in enumerate(polygon):
        second = polygon[(index + 1) % len(polygon)]
        if _strict_segments_cross(start, end, first, second):
            return True
    return False


def _midpoint_on_road(
    first: Mapping[str, Any],
    second: Mapping[str, Any],
    road_polygons: Sequence[Sequence[tuple[float, float]]],
    relationships: Sequence[Mapping[str, Any]],
) -> bool:
    midpoint = (
        (float(first["position"][0]) + float(second["position"][0])) / 2.0,
        (float(first["position"][1]) + float(second["position"][1])) / 2.0,
    )
    if road_polygons and any(
        _point_strictly_inside(midpoint, polygon) for polygon in road_polygons
    ):
        return True
    segment_start = (float(first["position"][0]), float(first["position"][1]))
    segment_end = (float(second["position"][0]), float(second["position"][1]))
    if road_polygons and any(
        _segment_touches_polygon(segment_start, segment_end, polygon)
        for polygon in road_polygons
    ):
        return True
    return _declares_across_road(
        relationships,
        str(first["placement_id"]),
        str(second["placement_id"]),
    )


def _intentional_container_overlap(
    first: Mapping[str, Any], second: Mapping[str, Any]
) -> bool:
    first_id = str(first["placement_id"])
    second_id = str(second["placement_id"])
    for record, other_id in ((first, second_id), (second, first_id)):
        declared = record.get("allow_overlap_with")
        if isinstance(declared, str):
            declared = [declared]
        if isinstance(declared, Sequence) and other_id in {
            str(value) for value in declared
        }:
            return True
        if str(record.get("parent_id") or "") == other_id:
            return True

    categories = {str(first["category"]), str(second["category"])}
    container_pairs = (
        ({"park", "river"}),
        ({"park", "sculpture"}),
        ({"park", "fountain"}),
        ({"park", "fitness"}),
        ({"leisure", "fitness"}),
        ({"residential", "delivery"}),
        ({"commercial", "pharmacy"}),
        ({"commercial", "atm"}),
    )
    return categories in container_pairs


def _footprint_collisions(
    records: Sequence[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    collisions = []
    exemptions = []
    physical = [
        record
        for record in records
        if record.get("footprint")
        and record.get("object_name")
        and _normal_text(record.get("collision_class")) == "asset"
    ]
    for first, second in itertools.combinations(physical, 2):
        if first["category"] in {"road", "intersection"} or second["category"] in {
            "road",
            "intersection",
        }:
            continue
        if not _polygons_have_hard_overlap(first["footprint"], second["footprint"]):
            continue
        item = {
            "first": first["placement_id"],
            "first_category": first["category"],
            "second": second["placement_id"],
            "second_category": second["category"],
        }
        if _intentional_container_overlap(first, second):
            exemptions.append(item)
        else:
            collisions.append(item)
    return collisions, exemptions


def _road_obstructions(
    records: Sequence[dict[str, Any]],
    road_polygons: Sequence[Sequence[tuple[float, float]]],
) -> list[dict[str, Any]]:
    if not road_polygons:
        return []
    obstructions = []
    exempt = {
        "road",
        "intersection",
        "river",
    }
    for record in records:
        if (
            record.get("category") in exempt
            or _normal_text(record.get("collision_class")) != "asset"
            or not record.get("footprint")
            or not record.get("object_name")
        ):
            continue
        if any(
            _polygons_have_hard_overlap(record["footprint"], polygon)
            for polygon in road_polygons
        ):
            obstructions.append(
                {
                    "placement_id": record["placement_id"],
                    "category": record["category"],
                }
            )
    return obstructions


def _road_evidence(
    objects: Iterable[bpy.types.Object], manifest: Mapping[str, Any]
) -> dict[str, Any]:
    evidence: dict[str, list[str]] = defaultdict(list)
    for obj in objects:
        name = obj.name.lower()
        library_path = obj.library.filepath.lower() if obj.library else ""
        props = " ".join(
            f"{str(key).lower()}={str(obj[key]).lower()}" for key in obj.keys()
        )
        text = f"{name} {props} {library_path}"
        if obj.type == "MESH" and (
            name in {"road", "road_n", "road_s", "road_e", "road_w", "isect"}
            or any(
                token in text
                for token in (
                    "road_surface",
                    "carriageway",
                    "asphalt_road",
                    "street_surface",
                    "road_mesh",
                )
            )
        ):
            evidence["road_surfaces"].append(obj.name)
        if any(
            token in text
            for token in (
                "marking_type",
                "centerline",
                "lane_mark",
                "line_style",
                "road_dash",
                "direction_arrow",
                "dash_ns_",
                "dash_ew_",
                "cl_ns",
                "cl_ew",
                "arr_n_",
                "arr_s_",
                "arr_e_",
                "arr_w_",
                "xwk_",
            )
        ):
            evidence["lane_markings"].append(obj.name)
        if any(
            token in text
            for token in ("zebra_crosswalk", "crosswalk", "pedestrian_crossing", "xwk_")
        ):
            evidence["crosswalks"].append(obj.name)
        if any(
            token in text
            for token in ("traffic_light", "traffic_signal", "signal_head")
        ):
            evidence["traffic_lights"].append(obj.name)
        if any(
            token in text
            for token in (
                "streetlight",
                "street_light",
                "street_lamp",
                "lamp_post",
                "lamppost",
            )
        ):
            evidence["streetlights"].append(obj.name)
        if any(
            token in text
            for token in (
                "vehicle_role",
                "vehicle_type",
                "/vehicles/",
                " sedan",
                "suv",
                " car_",
                "vehicle_",
                "bus_",
                "truck_",
                "van_",
                "vn1_",
                "vs1_",
                "vn2_",
                "vs2_",
            )
        ):
            evidence["vehicles"].append(obj.name)
        if any(token in text for token in ("intersection", "crossroads", "junction")):
            evidence["intersections"].append(obj.name)

    network = manifest.get("road_network", {})
    network = network if isinstance(network, Mapping) else {}
    requirements = manifest.get("requirements", {})
    requirements = requirements if isinstance(requirements, Mapping) else {}
    explicit_crosswalk_valid = bool(
        network.get("crosswalk_orientation_valid") is True
        or requirements.get("road_crosswalks_source_orientation_preserved") is True
    )
    tagged_crosswalks = [
        obj
        for obj in objects
        if any(
            key in obj
            for key in (
                "c2w_crossing_axis",
                "crossing_axis",
                "c2w_connects_road_sides",
                "crosswalk_orientation",
            )
        )
    ]
    tagged_crosswalk_valid = bool(tagged_crosswalks) and all(
        str(
            obj.get(
                "c2w_crossing_axis",
                obj.get("crossing_axis", obj.get("crosswalk_orientation", "")),
            )
        ).lower()
        in {
            "north_south",
            "east_west",
            "north-south",
            "east-west",
            "x",
            "y",
            "source_exact_ns",
            "source_exact_ew",
            "source_exact_both",
        }
        and obj.get("c2w_connects_road_sides", obj.get("connects_road_sides", True))
        is not False
        and obj.get("direction_valid", True) is not False
        for obj in tagged_crosswalks
    )
    return {
        "counts": {key: len(set(values)) for key, values in sorted(evidence.items())},
        "sample_names": {
            key: sorted(set(values))[:20] for key, values in sorted(evidence.items())
        },
        "tagged_crosswalk_count": len(tagged_crosswalks),
        "crosswalk_orientation_valid": tagged_crosswalk_valid
        or explicit_crosswalk_valid,
        "manifest_obstruction_free": bool(
            network.get("obstruction_free") is True
            or requirements.get("road_obstructions") == "vehicles_only"
        ),
    }


def _city_center(
    manifest: Mapping[str, Any], grouped: Mapping[str, list[dict[str, Any]]]
) -> tuple[float, float]:
    candidates = [manifest.get("city_center")]
    network = manifest.get("road_network", {})
    if isinstance(network, Mapping):
        candidates.append(network.get("city_center"))
    for candidate in candidates:
        point = _vector2(candidate)
        if point:
            return point
    city_bounds = manifest.get("city_bounds")
    if isinstance(city_bounds, Mapping):
        low = _vector2(city_bounds.get("min"))
        high = _vector2(city_bounds.get("max"))
        if low and high:
            return ((low[0] + high[0]) / 2.0, (low[1] + high[1]) / 2.0)
    intersections = grouped.get("intersection", [])
    if intersections:
        return (
            sum(float(record["position"][0]) for record in intersections)
            / len(intersections),
            sum(float(record["position"][1]) for record in intersections)
            / len(intersections),
        )
    return (0.0, 0.0)


def _zone_has(record: Mapping[str, Any], tokens: Iterable[str]) -> bool:
    text = _normal_text(record.get("zone"))
    return any(token in text for token in tokens)


def _best_fire_police_assignment(
    fire: Sequence[dict[str, Any]],
    police: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    station_count = sum(
        int(record.get("semantic_content", {}).get("fire_station_building_count", 0))
        for record in fire
    )
    if station_count != 2 or len(fire) not in {1, 2} or len(police) != 3:
        return {"valid": False, "pairs": [], "unpaired_police": None}
    best = None
    fire_sides = list(fire) if len(fire) == 2 else [fire[0], fire[0]]
    for selected in itertools.permutations(police, 2):
        metrics = [
            {
                "fire": fire_sides[index]["placement_id"],
                "police": selected[index]["placement_id"],
                "distance_m": _distance(fire_sides[index], selected[index]),
                "opposition_error_deg": _opposition_error(
                    fire_sides[index], selected[index]
                ),
            }
            for index in range(2)
        ]
        score = sum(
            item["distance_m"] + 3.0 * item["opposition_error_deg"] for item in metrics
        )
        if best is None or score < best[0]:
            remaining = next(record for record in police if record not in selected)
            best = (score, metrics, remaining)
    assert best is not None
    return {
        "valid": all(
            8.0 <= item["distance_m"] <= 180.0 and item["opposition_error_deg"] <= 35.0
            for item in best[1]
        ),
        "pairs": best[1],
        "unpaired_police": best[2]["placement_id"],
    }


def _source_checks(
    grouped: Mapping[str, list[dict[str, Any]]]
) -> tuple[dict[str, bool], dict[str, Any]]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    for category, tokens in SOURCE_TOKENS.items():
        records = grouped.get(category, [])
        mismatches = [
            record["placement_id"]
            for record in records
            if not any(
                _normal_text(token) in _normal_text(record.get("source_path"))
                for token in tokens
            )
        ]
        checks[f"source_lineage_{category}"] = bool(records) and not mismatches
        details[category] = {"required_tokens": list(tokens), "mismatches": mismatches}

    residential = grouped.get("residential", [])
    residential_paths = [
        _normal_text(record.get("source_path")) for record in residential
    ]
    river3_style = sum(
        (
            "urban_v1_full_07_river3" in path
            or (
                "urban_v1_full_07_river5" in path
                and "river3" in _normal_text(record.get("variant"))
            )
        )
        for path, record in zip(residential_paths, residential)
    )
    residential_distribution = {
        "river3_two_preserved_regions": river3_style,
        "urban_v3_all45_09": sum(
            "urban_v3_all45_09" in path for path in residential_paths
        ),
    }
    checks["source_lineage_residential_2_plus_1"] = residential_distribution == {
        "river3_two_preserved_regions": 2,
        "urban_v3_all45_09": 1,
    }
    details["residential"] = residential_distribution
    return checks, details


def _relationship_checks(
    grouped: Mapping[str, list[dict[str, Any]]],
    manifest: Mapping[str, Any],
) -> tuple[dict[str, bool], dict[str, Any]]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}
    relationships = _relations(manifest)
    road_polygons = _road_polygons(manifest)
    center = _city_center(manifest, grouped)

    pharmacies = grouped.get("pharmacy", [])
    pharmacy_distance = _distance(*pharmacies) if len(pharmacies) == 2 else None
    checks["two_pharmacies_are_separated"] = (
        pharmacy_distance is not None and pharmacy_distance >= 12.0
    )
    details["pharmacy_separation_m"] = pharmacy_distance

    atms = grouped.get("atm", [])
    atm_record = atms[0] if len(atms) == 1 else None
    atm_content_count = (
        int(atm_record.get("semantic_content", {}).get("atm_machine_count", 0))
        if atm_record
        else 0
    )
    atm_declared_count = (
        int(atm_record.get("semantic_metadata", {}).get("machine_count", 0))
        if atm_record
        else 0
    )
    atm_arrangement = (
        _normal_text(atm_record.get("semantic_metadata", {}).get("arrangement"))
        if atm_record
        else ""
    )
    atm_bounds = (
        _polygon_bounds(atm_record["footprint"])
        if atm_record and atm_record.get("footprint")
        else None
    )
    atm_aspect_ratio = (
        max(atm_bounds[2] - atm_bounds[0], atm_bounds[3] - atm_bounds[1])
        / min(atm_bounds[2] - atm_bounds[0], atm_bounds[3] - atm_bounds[1])
        if atm_bounds
        and min(atm_bounds[2] - atm_bounds[0], atm_bounds[3] - atm_bounds[1]) > 1e-7
        else 0.0
    )
    checks["five_atms_form_one_clear_row"] = bool(
        len(atms) == 1
        and atm_content_count == 5
        and atm_declared_count == 5
        and atm_arrangement in {"single_row", "one_row", "row"}
        and atm_aspect_ratio >= 4.0
    )
    details["atm_row"] = {
        "placement_count": len(atms),
        "linked_unit_collection_count": atm_content_count,
        "declared_machine_count": atm_declared_count,
        "arrangement": atm_arrangement,
        "footprint_aspect_ratio": atm_aspect_ratio,
        "linked_unit_collections": (
            atm_record.get("semantic_content", {}).get("atm_unit_collections", [])
            if atm_record
            else []
        ),
    }

    school = grouped.get("school", [])
    library = grouped.get("library", [])
    if len(school) == len(library) == 1:
        school_library_distance = _distance(school[0], library[0])
        school_library_opposition = _opposition_error(school[0], library[0])
        school_library_road = _midpoint_on_road(
            school[0], library[0], road_polygons, relationships
        )
    else:
        school_library_distance = None
        school_library_opposition = None
        school_library_road = False
    checks["school_and_library_opposite_across_road"] = bool(
        school_library_distance is not None
        and 10.0 <= school_library_distance <= 220.0
        and school_library_opposition is not None
        and school_library_opposition <= 35.0
        and school_library_road
    )
    details["school_library"] = {
        "distance_m": school_library_distance,
        "opposition_error_deg": school_library_opposition,
        "road_between": school_library_road,
    }

    commercial = grouped.get("commercial", [])
    banks = grouped.get("bank", [])
    bank_commercial_distance = min(
        (_distance(bank, shop) for bank in banks for shop in commercial),
        default=None,
    )
    central_bank_radius = max(
        (_distance_to_point(bank, center) for bank in banks), default=math.inf
    )
    low_banks = [
        record
        for record in banks
        if any(
            token
            in _normal_text(record.get("variant"))
            + "_"
            + _normal_text(record.get("asset_type"))
            for token in ("low", "short", "small", "short")
        )
        or record.get("semantic_metadata", {}).get("low_building_row") is True
    ]
    best_bank_line = None
    candidates = (
        [tuple(low_banks)]
        if len(low_banks) == 3
        else list(itertools.combinations(banks, 3))
    )
    for candidate in candidates:
        metrics = _line_metrics(candidate)
        if not metrics.get("valid"):
            continue
        score = metrics["max_perpendicular_deviation_m"]
        if best_bank_line is None or score < best_bank_line[0]:
            best_bank_line = (
                score,
                metrics,
                [record["placement_id"] for record in candidate],
            )
    bank_line_details = best_bank_line[1] if best_bank_line else {"valid": False}
    if best_bank_line:
        bank_line_details = dict(bank_line_details)
        bank_line_details["placement_ids"] = best_bank_line[2]
    checks["bank_precinct_beside_commercial_and_central"] = bool(
        len(banks) == 4
        and bank_commercial_distance is not None
        and bank_commercial_distance <= 160.0
        and central_bank_radius <= 280.0
    )
    checks["three_low_bank_buildings_form_row"] = bool(
        len(low_banks) == 3
        and bank_line_details.get("valid")
        and bank_line_details.get("span_m", 0.0) >= 12.0
        and bank_line_details.get("max_perpendicular_deviation_m", math.inf) <= 1.5
        and bank_line_details.get("min_adjacent_gap_m", 0.0) >= 4.0
    )
    details["banks"] = {
        "nearest_commercial_distance_m": bank_commercial_distance,
        "furthest_city_center_distance_m": central_bank_radius,
        "low_variant_ids": [record["placement_id"] for record in low_banks],
        "three_building_row": bank_line_details,
    }

    hospitals = grouped.get("hospital", [])
    hospital_distance = _distance(*hospitals) if len(hospitals) == 2 else None
    hospital_variants = {_normal_text(record.get("variant")) for record in hospitals}
    center_hospitals = [
        record
        for record in hospitals
        if (
            _zone_has(record, ("center", "central", "downtown", "core", "Central City"))
            or any(
                token
                in _normal_text(record.get("semantic_metadata", {}).get("urban_role"))
                for token in (
                    "center",
                    "central",
                    "downtown",
                    "core",
                    "Central City",
                )
            )
        )
    ]
    suburb_hospitals = [
        record
        for record in hospitals
        if (
            _zone_has(record, ("suburb", "outskirt", "periphery", "edge", "outskirts"))
            or any(
                token
                in _normal_text(record.get("semantic_metadata", {}).get("urban_role"))
                for token in (
                    "suburb",
                    "outskirt",
                    "periphery",
                    "edge",
                    "outskirts",
                )
            )
        )
    ]
    checks["two_hospitals_are_different_and_citywide_separated"] = bool(
        len(hospitals) == 2
        and hospital_distance is not None
        and hospital_distance >= 100.0
        and len(hospital_variants) == 2
        and "" not in hospital_variants
        and len(center_hospitals) == 1
        and len(suburb_hospitals) == 1
    )
    details["hospitals"] = {
        "distance_m": hospital_distance,
        "variants": sorted(hospital_variants),
        "central_ids": [record["placement_id"] for record in center_hospitals],
        "suburban_ids": [record["placement_id"] for record in suburb_hospitals],
    }

    gas = grouped.get("gas_station", [])
    gas_pair = None
    if len(gas) == 3:
        candidates = []
        for first, second in itertools.combinations(gas, 2):
            distance = _distance(first, second)
            opposition = _opposition_error(first, second)
            road_between = _midpoint_on_road(
                first, second, road_polygons, relationships
            )
            declared = _declares_across_road(
                relationships, first["placement_id"], second["placement_id"]
            )
            score = (
                opposition * 4.0 + abs(distance - 45.0) - (1000.0 if declared else 0.0)
            )
            candidates.append(
                (score, first, second, distance, opposition, road_between, declared)
            )
        gas_pair = min(candidates, key=lambda item: item[0])
    if gas_pair:
        pair_midpoint = (
            (float(gas_pair[1]["position"][0]) + float(gas_pair[2]["position"][0]))
            / 2.0,
            (float(gas_pair[1]["position"][1]) + float(gas_pair[2]["position"][1]))
            / 2.0,
        )
        third_gas = next(record for record in gas if record not in gas_pair[1:3])
        third_distance = _distance_to_point(third_gas, pair_midpoint)
        gas_details = {
            "opposite_pair": [gas_pair[1]["placement_id"], gas_pair[2]["placement_id"]],
            "pair_distance_m": gas_pair[3],
            "opposition_error_deg": gas_pair[4],
            "road_between": gas_pair[5],
            "relationship_declared": gas_pair[6],
            "third_id": third_gas["placement_id"],
            "third_distance_from_pair_midpoint_m": third_distance,
        }
        gas_valid = (
            12.0 <= gas_pair[3] <= 120.0
            and gas_pair[4] <= 35.0
            and gas_pair[5]
            and third_distance >= 100.0
            and all(
                _zone_has(
                    record,
                    ("suburb", "outskirt", "periphery", "edge", "industrial", "outskirts"),
                )
                and _distance_to_point(record, center) >= 300.0
                for record in gas
            )
        )
    else:
        gas_details = {"opposite_pair": None}
        gas_valid = False
    checks["three_suburban_gas_stations_with_opposite_pair"] = bool(gas_valid)
    details["gas_stations"] = gas_details

    fire = grouped.get("fire_station", [])
    police = grouped.get("police_station", [])
    assignment = _best_fire_police_assignment(fire, police)
    paired_ids = {
        value
        for pair in assignment.get("pairs", [])
        for value in (pair["fire"], pair["police"])
    }
    pair_roads = []
    lookup = {record["placement_id"]: record for record in fire + police}
    for pair in assignment.get("pairs", []):
        pair_roads.append(
            _midpoint_on_road(
                lookup[pair["fire"]],
                lookup[pair["police"]],
                road_polygons,
                relationships,
            )
        )
    unpaired = next(
        (
            record
            for record in police
            if record["placement_id"] == assignment.get("unpaired_police")
        ),
        None,
    )
    police_library_distance = (
        _distance(unpaired, library[0])
        if unpaired is not None and len(library) == 1
        else None
    )
    outward_service_records = fire + [
        record for record in police if record["placement_id"] in paired_ids
    ]
    outward_service_zone = all(
        (
            _zone_has(
                record, ("outer", "mid", "edge", "periphery", "civic", "center periphery", "a bit further")
            )
            and 180.0 <= _distance_to_point(record, center) <= 650.0
        )
        for record in outward_service_records
    )
    checks["two_fire_police_pairs_opposite_across_roads"] = bool(
        assignment.get("valid")
        and len(pair_roads) == 2
        and all(pair_roads)
        and outward_service_zone
    )
    checks["third_police_station_near_library"] = bool(
        police_library_distance is not None and police_library_distance <= 180.0
    )
    assignment["road_between_each_pair"] = pair_roads
    assignment["outward_service_zone_labels_valid"] = outward_service_zone
    assignment["unpaired_police_library_distance_m"] = police_library_distance
    details["fire_police"] = assignment

    factories = grouped.get("factory", [])
    factory_radii = [_distance_to_point(record, center) for record in factories]
    checks["four_factories_remote_from_city_center"] = bool(
        len(factories) == 4 and min(factory_radii, default=0.0) >= 150.0
    )
    details["factories"] = {
        "city_center": list(center),
        "city_center_distances_m": factory_radii,
    }

    fitness = grouped.get("fitness", [])
    fitness_zones = [_normal_text(record.get("zone")) for record in fitness]
    checks["fitness_areas_cover_park_and_leisure"] = bool(
        len(fitness) == 2
        and sum("park" in zone or "park" in zone for zone in fitness_zones) == 1
        and sum(
            any(token in zone for token in ("leisure", "recreation", "sports", "recreation"))
            for zone in fitness_zones
        )
        == 1
    )
    details["fitness_zones"] = fitness_zones

    park = grouped.get("park", [])
    for category in ("river", "sculpture", "fountain"):
        features = grouped.get(category, [])
        feature_distance = (
            _distance(park[0], features[0]) if len(park) == len(features) == 1 else None
        )
        checks[f"park_{category}_spatially_integrated"] = (
            feature_distance is not None and feature_distance <= 180.0
        )
        details[f"park_{category}_distance_m"] = feature_distance

    details["relationship_manifest_entries"] = len(relationships)
    details["road_polygon_count"] = len(road_polygons)
    return checks, details


def _blend_signature() -> dict[str, Any]:
    filepath = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    file_stat = filepath.stat() if filepath and filepath.is_file() else None
    return {
        "filepath": str(filepath) if filepath else "",
        "file_size": file_stat.st_size if file_stat else None,
        "file_mtime_ns": file_stat.st_mtime_ns if file_stat else None,
        "objects": len(bpy.data.objects),
        "collections": len(bpy.data.collections),
        "meshes": len(bpy.data.meshes),
        "materials": len(bpy.data.materials),
        "is_dirty": bool(getattr(bpy.data, "is_dirty", False)),
    }


def main() -> None:
    _progress(f"scene={_audit_scene().name} scenes={len(bpy.data.scenes)}")
    out_dir = _output_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / "strict_completion_audit.json"
    success_path = out_dir / "SUCCESS"
    if success_path.exists():
        success_path.unlink()

    before = _blend_signature()
    _progress("load_manifest")
    manifest, manifest_sources = _load_manifest(out_dir)
    _progress("collect_placement_records")
    records, reconciliation = _collect_records(manifest)
    grouped = _by_category(records)
    placement_counts = {
        category: len(grouped.get(category, []))
        for category in sorted(set(EXPECTED_EXACT_COUNTS) | set(grouped))
    }
    counts = dict(placement_counts)
    counts["atm"] = sum(
        int(record.get("semantic_content", {}).get("atm_machine_count", 0))
        for record in grouped.get("atm", [])
    )
    counts["fire_station"] = sum(
        int(record.get("semantic_content", {}).get("fire_station_building_count", 0))
        for record in grouped.get("fire_station", [])
    )
    counts["sculpture"] = sum(
        int(record.get("semantic_content", {}).get("sculpture_count", 0))
        for record in grouped.get("park", [])
    )
    _progress("collect_reachable_objects")
    reachable = _reachable_render_objects()
    _progress(f"reachable_objects={len(reachable)}")
    indoors = _indoor_instances(reachable)

    metadata_missing = {
        record["placement_id"]: [
            key for key in ("source_path", "source_collection") if not record.get(key)
        ]
        for record in records
        if record.get("object_name")
        and (not record.get("source_path") or not record.get("source_collection"))
    }
    nonexistent_source_paths = [
        record["placement_id"]
        for record in records
        if record.get("object_name")
        and _resolve_source_path(record.get("source_path")) is None
    ]
    _progress("trace_source_collections")
    untraceable_source_collections = [
        record["placement_id"]
        for record in records
        if record.get("object_name") and not _source_collection_traceable(record)
    ]
    non_collection_instances = [
        record["placement_id"]
        for record in records
        if record.get("object_name") and not record.get("collection_instance")
    ]
    invalid_scales = [
        {
            "placement_id": record["placement_id"],
            "local_scale": record["local_scale"],
            "world_scale": record["world_scale"],
        }
        for record in records
        if record.get("object_name")
        and (
            any(abs(float(value) - 1.0) > 1e-4 for value in record["local_scale"])
            or any(abs(float(value) - 1.0) > 1e-4 for value in record["world_scale"])
        )
    ]
    missing_footprints = [
        record["placement_id"]
        for record in records
        if record.get("object_name") and not record.get("footprint")
    ]
    _progress("footprints_sources_relationships")
    footprint_collisions, collision_exemptions = _footprint_collisions(records)

    source_checks, source_details = _source_checks(grouped)
    relationship_checks, relationship_details = _relationship_checks(grouped, manifest)
    road_polygons = _road_polygons(manifest)
    road_obstructions = _road_obstructions(records, road_polygons)
    road_evidence = _road_evidence(reachable, manifest)
    road_counts = road_evidence["counts"]

    delivery_records = grouped.get("delivery", [])
    delivery_subtypes = Counter(
        record.get("delivery_subtype") for record in delivery_records
    )

    _progress("geometry_quality_scan")
    forbidden_tokens = (
        "toy",
        "placeholder",
        "proxy",
        "dummy",
        "lowpoly",
        "low_poly",
        "primitive_car",
    )
    forbidden_objects = sorted(
        obj.name
        for obj in reachable
        if any(token in obj.name.lower() for token in forbidden_tokens)
    )
    collapsed_meshes = sorted(
        obj.name for obj in reachable if not _mesh_is_authored(obj)
    )
    _progress(
        f"geometry_quality_done collapsed={len(collapsed_meshes)} forbidden={len(forbidden_objects)}"
    )

    declared_collections = manifest.get("key_collections", [])
    if isinstance(declared_collections, Mapping):
        declared_collections = list(declared_collections.values())
    if not isinstance(declared_collections, list):
        declared_collections = []
    declared_collections = [
        str(value) for value in declared_collections if isinstance(value, str)
    ]
    missing_declared_collections = [
        name for name in declared_collections if bpy.data.collections.get(name) is None
    ]
    full10_roots = sorted(
        collection.name
        for collection in bpy.data.collections
        if "full10" in collection.name.lower()
        or REVISION in collection.name.lower()
        or collection.get("c2w_revision") == REVISION
    )
    placement_collections = sorted(
        {
            collection_name
            for record in records
            if record.get("object_name")
            for collection_name in record.get("users_collection", [])
        }
    )

    scene_revision = (
        _audit_scene().get("c2w_revision")
        or _audit_scene().get("scene_revision")
        or manifest.get("revision")
        or manifest.get("scene_revision")
    )
    manifest_revision = manifest.get("revision") or manifest.get("scene_revision")

    inferred_key_collections = [
        f"full10:zone:{zone}"
        for zone in (
            "city_base",
            "residential",
            "park",
            "commercial",
            "education",
            "civic",
            "leisure",
            "health",
            "industrial",
            "roads",
        )
    ]
    inferred_key_collections_valid = all(
        bpy.data.collections.get(name) is not None for name in inferred_key_collections
    )
    requirements = manifest.get("requirements", {})
    requirements = requirements if isinstance(requirements, Mapping) else {}
    required_contract = {
        "residential_area_count": 3,
        "all45_09_native_indoor_instances": 6,
        "delivery_facility_count": 3,
        "pharmacy_count": 2,
        "atm_machine_count": 5,
        "fountain_count": 1,
        "fitness_area_count": 2,
        "bank_building_count": 4,
        "hospital_count": 2,
        "gas_station_count": 3,
        "factory_count": 4,
        "fire_station_building_count": 2,
        "police_station_count": 3,
    }
    generation_checks = manifest.get("generation_checks", {})
    generation_checks = (
        generation_checks if isinstance(generation_checks, Mapping) else {}
    )
    zones = manifest.get("zones", {})
    zones = zones if isinstance(zones, Mapping) else {}
    park_zone_polygon = _polygon_from_footprint(zones.get("park_irregular_polygon"))
    leisure_zone_polygon = _polygon_from_footprint(zones.get("leisure_south_polygon"))

    checks: dict[str, bool] = {
        "correct_scene_revision": scene_revision == REVISION
        and manifest_revision in (None, REVISION),
        "manifest_available_and_valid": bool(
            manifest and any(source.get("valid") for source in manifest_sources)
        ),
        "manifest_scene_placements_reconcile": bool(
            reconciliation["manifest_placement_count"] > 0
            and not reconciliation["duplicate_manifest_ids"]
            and not reconciliation["duplicate_scene_ids"]
            and not reconciliation["missing_scene_objects"]
            and not reconciliation["unmanifested_scene_objects"]
            and reconciliation["unique_manifest_placement_count"]
            == reconciliation["unique_scene_placement_count"]
        ),
        "full10_root_and_placement_collections_present": bool(
            full10_roots and placement_collections
        ),
        "declared_or_standard_key_collections_present": bool(
            (declared_collections and not missing_declared_collections)
            or inferred_key_collections_valid
        ),
        "all_placements_are_collection_instance_empties": bool(
            records and not non_collection_instances
        ),
        "all_placements_have_source_metadata": bool(records and not metadata_missing),
        "all_source_paths_exist": bool(records and not nonexistent_source_paths),
        "all_source_collections_traceable": bool(
            records and not untraceable_source_collections
        ),
        "all_placement_scales_are_exactly_one": bool(records and not invalid_scales),
        "all_placements_have_world_footprints": bool(
            records and not missing_footprints
        ),
        "planned_footprints_have_no_hard_collisions": not footprint_collisions,
        "at_least_six_reachable_indoor_instances": len(indoors) >= 6,
        "no_toy_proxy_placeholder_or_collapsed_geometry": not forbidden_objects
        and not collapsed_meshes,
        "delivery_has_exactly_three_distinct_requested_types": (
            len(delivery_records) == 3
            and set(delivery_subtypes) == DELIVERY_SUBTYPES
            and all(count == 1 for count in delivery_subtypes.values())
        ),
        "manifest_fixed_requirements_match_brief": bool(
            all(
                requirements.get(key) == value
                for key, value in required_contract.items()
            )
            and requirements.get("hospital_variants_different") is True
        ),
        "generator_reports_no_asset_or_road_collisions": bool(
            generation_checks.get("asset_aabb_overlap_pairs") == []
            and generation_checks.get("asset_road_intrusions") == []
            and generation_checks.get("all_placement_scales_one") is True
            and generation_checks.get("source_files_exist") is True
        ),
        "park_and_leisure_use_irregular_planned_zones": bool(
            park_zone_polygon
            and len(park_zone_polygon) >= 6
            and leisure_zone_polygon
            and len(leisure_zone_polygon) >= 5
        ),
        "road_and_intersection_placements_present": bool(
            grouped.get("road") and grouped.get("intersection")
        ),
        "road_surface_geometry_present": road_counts.get("road_surfaces", 0) >= 1,
        "lane_markings_present": road_counts.get("lane_markings", 0) >= 8,
        "crosswalks_present_and_oriented_correctly": bool(
            road_counts.get("crosswalks", 0) >= 1
            and road_evidence["crosswalk_orientation_valid"]
        ),
        "traffic_lights_present": road_counts.get("traffic_lights", 0) >= 4,
        "streetlights_present": road_counts.get("streetlights", 0) >= 4,
        "road_vehicles_present": road_counts.get("vehicles", 0) >= 1,
        "roadways_and_entrances_unobstructed": bool(
            not road_obstructions
            and (bool(road_polygons) or road_evidence["manifest_obstruction_free"])
        ),
    }
    for category, expected in EXPECTED_EXACT_COUNTS.items():
        checks[f"exact_count_{category}_{expected}"] = (
            counts.get(category, 0) == expected
        )
    checks.update(source_checks)
    checks.update(relationship_checks)

    after = _blend_signature()
    checks["blend_not_modified_by_audit"] = before == after
    failed = sorted(name for name, valid in checks.items() if not valid)

    inventory = []
    for record in sorted(records, key=lambda item: str(item["placement_id"])):
        inventory.append(
            {
                key: record.get(key)
                for key in (
                    "placement_id",
                    "object_name",
                    "category",
                    "category_raw",
                    "asset_type",
                    "delivery_subtype",
                    "zone",
                    "variant",
                    "source_path",
                    "source_collection",
                    "instance_collection",
                    "collection_instance",
                    "position",
                    "yaw_degrees",
                    "matrix_world_translation",
                    "local_scale",
                    "world_scale",
                    "footprint",
                    "footprint_area",
                    "collision_class",
                    "semantic_metadata",
                    "semantic_content",
                )
            }
        )

    result = {
        "valid": not failed,
        "revision": REVISION,
        "audit_mode": "strict read-only generated-scene inspection; Blend never saved or edited",
        "blend_path": bpy.data.filepath,
        "output_directory": str(out_dir),
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            **counts,
            "placement_counts_by_category": placement_counts,
            "reachable_render_objects": len(reachable),
            "indoor_collection_instances": len(indoors),
            "placement_empties": reconciliation["scene_placement_empty_count"],
            "road_evidence": road_counts,
        },
        "manifest": {
            "sources": manifest_sources,
            "revision": manifest_revision,
            "placement_reconciliation": reconciliation,
        },
        "collections": {
            "full10_roots": full10_roots,
            "placement_collections": placement_collections,
            "declared_key_collections": declared_collections,
            "missing_declared_key_collections": missing_declared_collections,
        },
        "placement_inventory": inventory,
        "metadata": {
            "missing": metadata_missing,
            "nonexistent_source_paths": nonexistent_source_paths,
            "untraceable_source_collections": untraceable_source_collections,
            "non_collection_instances": non_collection_instances,
            "invalid_scales": invalid_scales,
        },
        "source_lineage": source_details,
        "delivery_subtype_counts": {
            str(key): value
            for key, value in sorted(
                delivery_subtypes.items(), key=lambda item: str(item[0])
            )
        },
        "footprints": {
            "missing": missing_footprints,
            "hard_collisions": footprint_collisions,
            "intentional_container_exemptions": collision_exemptions,
        },
        "relationships": relationship_details,
        "road_network": {
            **road_evidence,
            "parsed_road_polygon_count": len(road_polygons),
            "obstructions": road_obstructions,
        },
        "indoor_instances": indoors,
        "quality": {
            "forbidden_named_objects": forbidden_objects,
            "collapsed_meshes": collapsed_meshes,
        },
        "read_only_proof": {
            "before": before,
            "after": after,
            "unchanged": before == after,
        },
    }
    _progress(f"write_report failed_checks={len(failed)}")
    report_path.write_text(
        json.dumps(_jsonable(result), indent=2, ensure_ascii=False, allow_nan=False),
        encoding="utf8",
    )

    if failed:
        raise RuntimeError(
            f"{REVISION} strict completion audit failed ({len(failed)} checks): "
            + ", ".join(failed)
        )
    success_path.write_text("SUCCESS\n", encoding="utf8")
    print(f"{REVISION} strict completion audit: SUCCESS")


if __name__ == "__main__":
    main()

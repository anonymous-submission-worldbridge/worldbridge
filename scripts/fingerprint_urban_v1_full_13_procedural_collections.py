#!/usr/bin/env python3
"""Content-fingerprint the active collections in a full-13 procedural pack.

This reads actual Blender data blocks (meshes, transforms, modifiers,
materials, curves and nested collection instances), not container bytes.  It
is used when a dependency-only ``.blend`` is reserialized and therefore gets
a different file SHA even though its active modeled content is unchanged.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import sys
from array import array
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import bpy


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
ACTIVE = (
    "full13:master:compact_irregular_ground",
    "full13_proc:apartment_west_civic_01",
    "full13_proc:apartment_west_civic_02",
    "full13_proc:apartment_west_civic_03",
    "full13_proc:apartment_west_civic_04",
    "full13_proc:apartment_east_mixed_01",
    "full13_proc:apartment_east_mixed_02",
    "full13_proc:apartment_southeast_01",
    "full13_proc:apartment_southeast_02",
    "full13_proc:apartment_northwest_edge_01",
    "full13_proc:apartment_northwest_edge_02",
    "full13_proc:apartment_north_civic_01",
    "full13_proc:apartment_north_civic_02",
    "full13:master:continuous_pedestrian_activity",
    "full13:master:complete_entrance_connector_network",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def token(digest: Any, value: Any) -> None:
    if value is None:
        payload = b"null"
    elif isinstance(value, bool):
        payload = b"true" if value else b"false"
    elif isinstance(value, int):
        payload = str(value).encode("ascii")
    elif isinstance(value, float):
        payload = struct.pack("!d", value)
    elif isinstance(value, str):
        payload = value.encode("utf8")
    elif isinstance(value, (tuple, list)):
        token(digest, len(value))
        for item in value:
            token(digest, item)
        return
    else:
        payload = repr(value).encode("utf8")
    digest.update(struct.pack("!I", len(payload)))
    digest.update(payload)


def rna_scalars(value: Any) -> list[tuple[str, Any]]:
    result = []
    non_content = {
        "rna_type",
        "name",
        "name_full",
        "id_type",
        "session_uid",
        "users",
        "use_fake_user",
        "use_extra_user",
        "is_embedded_data",
        "is_linked_packed",
        "is_missing",
        "is_runtime_data",
        "is_editable",
        "tag",
        "is_library_indirect",
        "execution_time",
        "persistent_uid",
        "show_expanded",
        "is_active",
    }
    for prop in value.bl_rna.properties:
        name = prop.identifier
        if name in non_content or prop.type in {"POINTER", "COLLECTION"}:
            continue
        try:
            item = getattr(value, name)
        except (AttributeError, TypeError):
            continue
        if getattr(prop, "is_array", False):
            try:
                item = tuple(item)
            except TypeError:
                continue
        if isinstance(item, (str, bool, int, float, tuple, list)):
            result.append((name, item))
    return result


material_cache: dict[int, str] = {}
mesh_cache: dict[int, str] = {}
curve_cache: dict[int, str] = {}
collection_cache: dict[int, str] = {}


def material_hash(material: bpy.types.Material | None) -> str:
    if material is None:
        return "NONE"
    key = material.as_pointer()
    if key in material_cache:
        return material_cache[key]
    digest = hashlib.sha256()
    token(digest, material.name)
    token(digest, tuple(material.diffuse_color))
    token(digest, rna_scalars(material))
    tree = material.node_tree
    if tree is not None:
        for node in sorted(tree.nodes, key=lambda item: (item.bl_idname, item.name)):
            token(digest, (node.bl_idname, node.name, node.label, rna_scalars(node)))
            if hasattr(node, "color_ramp"):
                ramp = node.color_ramp
                token(
                    digest,
                    (ramp.color_mode, ramp.hue_interpolation, ramp.interpolation),
                )
                for element in ramp.elements:
                    token(digest, (element.position, tuple(element.color)))
            for socket in node.inputs:
                if socket.is_linked or not hasattr(socket, "default_value"):
                    continue
                try:
                    default = socket.default_value
                    if hasattr(default, "__len__") and not isinstance(default, str):
                        default = tuple(default)
                    token(digest, (socket.name, default))
                except (TypeError, ValueError):
                    pass
        for link in sorted(
            tree.links,
            key=lambda item: (
                item.from_node.name,
                item.from_socket.name,
                item.to_node.name,
                item.to_socket.name,
            ),
        ):
            token(
                digest,
                (
                    link.from_node.name,
                    link.from_socket.name,
                    link.to_node.name,
                    link.to_socket.name,
                ),
            )
    value = digest.hexdigest()
    material_cache[key] = value
    return value


def mesh_hash(mesh: bpy.types.Mesh) -> str:
    key = mesh.as_pointer()
    if key in mesh_cache:
        return mesh_cache[key]
    digest = hashlib.sha256()
    # Primitive mesh datablock names (for example Cube.1842) depend on how
    # many unrelated objects were authored earlier in the Blender process;
    # object identity is hashed separately, so that session ordering token is
    # intentionally excluded from renderable content.
    specifications = (
        (mesh.vertices, "co", "f", 3),
        (mesh.edges, "vertices", "i", 2),
        (mesh.loops, "vertex_index", "i", 1),
        (mesh.polygons, "loop_start", "i", 1),
        (mesh.polygons, "loop_total", "i", 1),
        (mesh.polygons, "material_index", "i", 1),
    )
    for values, attribute, typecode, width in specifications:
        data = array(typecode, [0]) * (len(values) * width)
        if data:
            values.foreach_get(attribute, data)
        token(digest, (attribute, len(values), width))
        digest.update(data.tobytes())
    for layer in mesh.uv_layers:
        data = array("f", [0]) * (len(layer.data) * 2)
        if data:
            layer.data.foreach_get("uv", data)
        token(digest, ("uv", layer.name, len(layer.data)))
        digest.update(data.tobytes())
    token(digest, [material_hash(material) for material in mesh.materials])
    value = digest.hexdigest()
    mesh_cache[key] = value
    return value


def curve_hash(curve: bpy.types.Curve) -> str:
    key = curve.as_pointer()
    if key in curve_cache:
        return curve_cache[key]
    digest = hashlib.sha256()
    curve_type = curve.__class__.__name__
    token(digest, (curve_type, rna_scalars(curve)))
    if curve_type == "TextCurve":
        token(digest, curve.body)
    for spline in getattr(curve, "splines", ()):
        token(digest, (spline.type, rna_scalars(spline)))
        for point in spline.points:
            token(digest, tuple(point.co))
        for point in spline.bezier_points:
            token(
                digest,
                (
                    tuple(point.co),
                    tuple(point.handle_left),
                    tuple(point.handle_right),
                    point.handle_left_type,
                    point.handle_right_type,
                ),
            )
    token(digest, [material_hash(material) for material in curve.materials])
    value = digest.hexdigest()
    curve_cache[key] = value
    return value


def object_hash(obj: bpy.types.Object, stack: set[int]) -> str:
    digest = hashlib.sha256()
    token(digest, (obj.name, obj.type, obj.rotation_mode, obj.hide_render))
    token(digest, tuple(value for row in obj.matrix_local for value in row))
    token(digest, obj.parent.name if obj.parent else None)
    token(digest, obj.parent_type)
    if obj.type == "MESH" and obj.data is not None:
        token(digest, mesh_hash(obj.data))
    elif obj.type in {"CURVE", "FONT"} and obj.data is not None:
        token(digest, curve_hash(obj.data))
    elif obj.data is not None:
        token(
            digest, (obj.data.name, obj.data.__class__.__name__, rna_scalars(obj.data))
        )
    for modifier in obj.modifiers:
        token(digest, (modifier.name, modifier.type, rna_scalars(modifier)))
    token(digest, [material_hash(slot.material) for slot in obj.material_slots])
    if obj.instance_collection is not None:
        token(digest, collection_hash(obj.instance_collection, stack))
    return digest.hexdigest()


def collection_hash(
    collection: bpy.types.Collection, stack: set[int] | None = None
) -> str:
    key = collection.as_pointer()
    if key in collection_cache:
        return collection_cache[key]
    if stack is None:
        stack = set()
    if key in stack:
        return f"CYCLE:{collection.name}"
    stack = set(stack)
    stack.add(key)
    digest = hashlib.sha256()
    token(digest, collection.name)
    for obj in sorted(collection.objects, key=lambda item: item.name):
        token(digest, object_hash(obj, stack))
    for child in sorted(collection.children, key=lambda item: item.name):
        token(digest, collection_hash(child, stack))
    value = digest.hexdigest()
    collection_cache[key] = value
    return value


def main() -> None:
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    if len(args) != 1:
        raise RuntimeError("Usage: blender -b PACK --python SCRIPT -- OUTPUT.json")
    output = Path(args[0]).resolve()
    if not output.is_relative_to(CITY.resolve()):
        raise RuntimeError("Fingerprint output must remain inside full-13")
    source = Path(bpy.data.filepath).resolve()
    records = {}
    for name in ACTIVE:
        collection = bpy.data.collections.get(name)
        if collection is None:
            raise RuntimeError(f"Missing active procedural collection: {name}")
        objects = list(collection.all_objects)
        records[name] = {
            "content_sha256": collection_hash(collection),
            "recursive_object_count": len(objects),
            "mesh_object_count": sum(obj.type == "MESH" for obj in objects),
            "font_object_count": sum(obj.type == "FONT" for obj in objects),
            "instance_collection_count": sum(
                obj.instance_collection is not None for obj in objects
            ),
            "object_content_sha256": {
                obj.name: object_hash(obj, set())
                for obj in sorted(objects, key=lambda item: item.name)
            },
        }
    payload = {
        "schema": "agent.full13.procedural_collection_content_fingerprint.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS",
        "source_blend": str(source),
        "source_blend_bytes": source.stat().st_size,
        "source_blend_sha256": sha256(source),
        "active_collection_count": len(records),
        "collections": records,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".writing.json")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf8")
    temporary.replace(output)
    print(
        f"FULL13_PROCEDURAL_CONTENT_FINGERPRINT_PASS collections={len(records)} "
        f"source={source.name}",
        flush=True,
    )


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        import traceback

        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)

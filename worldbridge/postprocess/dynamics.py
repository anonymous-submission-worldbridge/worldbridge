"""Apply deterministic, opt-in dynamics to an existing WorldBridge scene.

Run through Blender, for example::

    blender --background --python worldbridge/postprocess/dynamics.py -- \
      --input scene.blend --output scene_dynamic.blend \
      --config configs/dynamics/default.json --render

The input file is never overwritten.  This complements the LLM-driven
``generate.py`` with a repeatable path for common urban dynamics.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import bmesh
import bpy
from mathutils import Vector

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from worldbridge.postprocess.dynamics_schema import load_config

TAG = "c2w_dynamic_generated"


def _cli_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(
        description="Add reusable dynamics to a Blender scene"
    )
    parser.add_argument("--input", required=True, help="Existing static .blend scene")
    parser.add_argument("--output", required=True, help="New dynamic .blend scene")
    parser.add_argument("--config", default="", help="Optional version-1 dynamics JSON")
    parser.add_argument(
        "--render", action="store_true", help="Render the configured MP4"
    )
    parser.add_argument("--video", default="", help="Override render.video_path")
    return parser.parse_args(argv)


def _absolute(path: str) -> Path:
    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = REPO_ROOT / candidate
    return candidate.resolve()


def _text(value: Any) -> str:
    return str(value or "").casefold()


def _matches(value: str, patterns: Iterable[str]) -> bool:
    folded = _text(value)
    return any(_text(pattern) in folded for pattern in patterns if pattern)


def _matches_vehicle(value: str, patterns: Iterable[str]) -> bool:
    """Match short vehicle names as tokens so ``car`` does not match carnivore."""

    folded = _text(value)
    tokens = set(re.findall(r"[a-z0-9]+", folded))
    for pattern in patterns:
        candidate = _text(pattern)
        if not candidate:
            continue
        if candidate in {"car", "bus", "van"}:
            if candidate in tokens:
                return True
        elif candidate in folded:
            return True
    return False


def _object_semantics(obj: bpy.types.Object) -> str:
    fields = [obj.name]
    for key in (
        "c2w_dynamic_role",
        "c2w_role",
        "c2w_asset_id",
        "c2w_river_role",
        "asset_category",
        "semantic_role",
    ):
        fields.append(obj.get(key, ""))
    if obj.instance_collection is not None:
        fields.extend(
            [
                obj.instance_collection.name,
                obj.instance_collection.get("c2w_asset_id", ""),
                obj.instance_collection.get("c2w_dynamic_role", ""),
            ]
        )
    return " ".join(map(str, fields))


def _named_collections(names: Iterable[str]) -> list[bpy.types.Collection]:
    tokens = [_text(name) for name in names if name]
    return [
        collection
        for collection in bpy.data.collections
        if any(token in collection.name.casefold() for token in tokens)
    ]


def _objects_from_collections(names: Iterable[str]) -> list[bpy.types.Object]:
    objects: list[bpy.types.Object] = []
    for collection in _named_collections(names):
        objects.extend(list(collection.all_objects))
    return objects


def _dedupe_objects(objects: Iterable[bpy.types.Object]) -> list[bpy.types.Object]:
    result: list[bpy.types.Object] = []
    seen: set[int] = set()
    for obj in objects:
        pointer = obj.as_pointer()
        if pointer and pointer not in seen:
            seen.add(pointer)
            result.append(obj)
    return result


def _has_user_animation(owner: Any) -> bool:
    animation = getattr(owner, "animation_data", None)
    action = getattr(animation, "action", None) if animation else None
    return bool(action and not action.get(TAG, False))


def _tag_action(owner: Any, effect: str) -> None:
    animation = getattr(owner, "animation_data", None)
    action = getattr(animation, "action", None) if animation else None
    if action is not None:
        action[TAG] = True
        action["c2w_dynamic_effect"] = effect
        action.name = f"C2W_Dynamics_{effect}_{getattr(owner, 'name', 'data')}"


def _finish_curves(owner: Any, *, cyclic: bool, interpolation: str = "LINEAR") -> None:
    animation = getattr(owner, "animation_data", None)
    action = getattr(animation, "action", None) if animation else None
    if action is None:
        return
    try:
        curves = list(action.fcurves)
    except (AttributeError, RuntimeError):
        # Blender 5 stores curves in layered action channel bags and removed
        # the legacy Action.fcurves compatibility property.
        curves = []
        for layer in getattr(action, "layers", []):
            for strip in getattr(layer, "strips", []):
                for channelbag in getattr(strip, "channelbags", []):
                    curves.extend(list(channelbag.fcurves))
    for curve in curves:
        for keyframe in curve.keyframe_points:
            keyframe.interpolation = interpolation
        if cyclic and not any(
            modifier.type == "CYCLES" for modifier in curve.modifiers
        ):
            curve.modifiers.new("CYCLES")


def _set_scene_timeline(config: dict[str, Any]) -> None:
    scene = bpy.context.scene
    timeline = config["timeline"]
    scene.frame_start = timeline["frame_start"]
    scene.frame_end = timeline["frame_end"]
    scene.render.fps = timeline["fps"]
    scene.frame_set(scene.frame_start)
    scene["c2w_dynamics_config_version"] = config["version"]


def _descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    result: list[bpy.types.Object] = []
    stack = list(root.children)
    while stack:
        child = stack.pop()
        result.append(child)
        stack.extend(list(child.children))
    return result


def _create_motion_root(
    name: str,
    parts: list[bpy.types.Object],
    role: str,
    *,
    forward_axis: str = "",
) -> bpy.types.Object | None:
    """Parent loose semantic parts to one Empty without changing world transforms."""

    existing = bpy.data.objects.get(name)
    if existing is not None:
        return existing
    if not parts or any(
        part.parent is not None or _has_user_animation(part) for part in parts
    ):
        return None
    x = sum(part.matrix_world.translation.x for part in parts) / len(parts)
    y = sum(part.matrix_world.translation.y for part in parts) / len(parts)
    try:
        z = min(
            (part.matrix_world @ Vector(corner)).z
            for part in parts
            for corner in part.bound_box
        )
    except (AttributeError, ValueError):
        z = min(part.matrix_world.translation.z for part in parts)
    root = bpy.data.objects.new(name, None)
    root.location = (x, y, z)
    root[TAG] = True
    root["c2w_dynamic_role"] = role
    if forward_axis:
        root["c2w_forward_axis"] = forward_axis
    target_collection = (
        parts[0].users_collection[0] if parts[0].users_collection else None
    )
    (target_collection or bpy.context.scene.collection).objects.link(root)
    # A newly linked object's matrix_world can remain the identity until the
    # dependency graph is evaluated, even though root.location is populated.
    # Update once before deriving the shared parent inverse.
    bpy.context.view_layer.update()
    root_inverse = root.matrix_world.inverted_safe()
    for part in parts:
        # Keep the part's current world transform while making the new Empty
        # its motion space.  Assigning matrix_world after parenting is not
        # sufficient in Blender 5: the child's original object-space location
        # can be evaluated on top of the parent's translation.  An explicit
        # parent inverse anchors the rest pose and makes subsequent root
        # keyframes apply only their intended delta.
        part.parent = root
        part.matrix_parent_inverse = root_inverse
    return root


def _semantic_vehicle_roots() -> list[bpy.types.Object]:
    groups: dict[str, list[bpy.types.Object]] = {}
    suffix = re.compile(r"_(?:body|cabin|wheel[^_]*)$", re.IGNORECASE)
    for obj in bpy.data.objects:
        if _text(obj.get("actor_type")) != "vehicle" or obj.parent is not None:
            continue
        base = suffix.sub("", obj.name)
        groups.setdefault(base, []).append(obj)
    roots = []
    for base, parts in groups.items():
        root = _create_motion_root(
            f"{base}_C2W_ROOT", parts, "vehicle", forward_axis="Y"
        )
        if root is not None:
            roots.append(root)
    return roots


def _loose_tree_roots(settings: dict[str, Any]) -> list[bpy.types.Object]:
    groups: dict[str, list[bpy.types.Object]] = {}
    suffix = re.compile(r"_(?:trunk|canopy|leaves?|foliage)$", re.IGNORECASE)
    for obj in bpy.data.objects:
        if obj.parent is not None or not _matches(obj.name, settings["name_patterns"]):
            continue
        base = suffix.sub("", obj.name)
        if base != obj.name:
            groups.setdefault(base, []).append(obj)
    roots = []
    for base, parts in groups.items():
        if len(parts) < 2:
            continue
        root = _create_motion_root(f"{base}_C2W_ROOT", parts, "tree")
        if root is not None:
            roots.append(root)
    return roots


def _vehicle_roots(settings: dict[str, Any]) -> list[bpy.types.Object]:
    candidates: list[bpy.types.Object] = _semantic_vehicle_roots()
    for name in settings["object_names"]:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            candidates.append(obj)

    pool = _objects_from_collections(settings["collection_names"])
    pool.extend(list(bpy.data.objects))
    for obj in pool:
        semantics = _object_semantics(obj)
        explicit_role = _text(obj.get("c2w_dynamic_role")) == "vehicle"
        root_like = obj.parent is None and (
            obj.type == "EMPTY" or "grp_root" in obj.name.casefold()
        )
        if explicit_role or (
            root_like and _matches_vehicle(semantics, settings["name_patterns"])
        ):
            candidates.append(obj)
    return _dedupe_objects(candidates)[: settings["max_objects"]]


def _forward_axis(obj: bpy.types.Object, requested: str) -> str:
    requested = requested.upper()
    if requested != "AUTO":
        return requested
    tagged = str(obj.get("c2w_forward_axis", "")).upper()
    if tagged in {"X", "Y", "-X", "-Y"}:
        return tagged
    if (
        "grp_root" in obj.name.casefold()
        or "openx" in _object_semantics(obj).casefold()
    ):
        return "X"
    return "Y"


def _axis_vector(axis: str) -> Vector:
    return {
        "X": Vector((1.0, 0.0, 0.0)),
        "Y": Vector((0.0, 1.0, 0.0)),
        "-X": Vector((-1.0, 0.0, 0.0)),
        "-Y": Vector((0.0, -1.0, 0.0)),
    }[axis]


def _wheel_axis_index(wheel: bpy.types.Object) -> int:
    try:
        points = [Vector(corner) for corner in wheel.bound_box]
        extents = [
            max(point[index] for point in points)
            - min(point[index] for point in points)
            for index in range(3)
        ]
        return extents.index(min(extents))
    except (AttributeError, ValueError):
        return 1


def _animate_wheels(
    root: bpy.types.Object,
    distance: float,
    start: int,
    end: int,
    radius: float,
    cyclic: bool,
) -> int:
    wheels = [
        obj
        for obj in _descendants(root)
        if _matches(obj.name, ("wheel", "tire", "tyre"))
        and not _has_user_animation(obj)
    ]
    angle = distance / max(radius, 0.001)
    for wheel in wheels:
        wheel.rotation_mode = "XYZ"
        axis = _wheel_axis_index(wheel)
        base = wheel.rotation_euler[axis]
        wheel.rotation_euler[axis] = base
        wheel.keyframe_insert("rotation_euler", index=axis, frame=start)
        wheel.rotation_euler[axis] = base - angle
        wheel.keyframe_insert("rotation_euler", index=axis, frame=end)
        _tag_action(wheel, "vehicle_wheel")
        _finish_curves(wheel, cyclic=cyclic)
    return len(wheels)


def _animate_route(
    obj: bpy.types.Object,
    points: list[list[float]],
    axis: str,
    start: int,
    end: int,
    cyclic: bool,
) -> float:
    normalized = [
        Vector((*point, obj.location.z) if len(point) == 2 else point)
        for point in points
    ]
    total = 0.0
    for index, point in enumerate(normalized):
        frame = start + (end - start) * index / (len(normalized) - 1)
        obj.location = point
        if index < len(normalized) - 1:
            delta = normalized[index + 1] - point
        else:
            delta = point - normalized[index - 1]
        if delta.xy.length > 1e-6:
            heading = math.atan2(delta.y, delta.x)
            axis_angle = {
                "X": 0.0,
                "Y": math.pi / 2,
                "-X": math.pi,
                "-Y": -math.pi / 2,
            }[axis]
            obj.rotation_mode = "XYZ"
            obj.rotation_euler.z = heading - axis_angle
        obj.keyframe_insert("location", frame=frame)
        obj.keyframe_insert("rotation_euler", frame=frame)
        if index:
            total += (point - normalized[index - 1]).length
    _tag_action(obj, "vehicle_route")
    _finish_curves(obj, cyclic=cyclic)
    return total


def add_vehicle_motion(config: dict[str, Any], report: dict[str, Any]) -> None:
    settings = config["effects"]["vehicles"]
    if not settings["enabled"]:
        report["vehicles"] = {"enabled": False, "animated": 0}
        return
    timeline = config["timeline"]
    start, end = timeline["frame_start"], timeline["frame_end"] + 1
    cyclic = timeline["loop"]
    animated: set[str] = set()
    skipped: list[str] = []
    wheel_count = 0
    # Discover first: this also groups loose semantic body/cabin meshes into
    # stable motion roots required by explicitly configured routes.
    discovered_roots = _vehicle_roots(settings)

    for route in settings["routes"]:
        obj = bpy.data.objects.get(route["object"])
        if obj is None:
            skipped.append(f"missing route object: {route['object']}")
            continue
        if _has_user_animation(obj):
            skipped.append(f"preserved existing animation: {obj.name}")
            continue
        axis = _forward_axis(obj, route.get("forward_axis", settings["forward_axis"]))
        distance = _animate_route(obj, route["points"], axis, start, end, cyclic)
        obj["c2w_dynamic_role"] = "vehicle"
        animated.add(obj.name)
        if settings["wheel_spin"]:
            wheel_count += _animate_wheels(
                obj, distance, start, end, settings["wheel_radius_m"], cyclic
            )

    for obj in discovered_roots:
        if obj.name in animated:
            continue
        if _has_user_animation(obj):
            skipped.append(f"preserved existing animation: {obj.name}")
            continue
        axis = _forward_axis(obj, settings["forward_axis"])
        direction = obj.rotation_euler.to_matrix() @ _axis_vector(axis)
        direction.z = 0.0
        if direction.length < 1e-6:
            direction = Vector((1.0, 0.0, 0.0))
        direction.normalize()
        origin = obj.location.copy()
        obj.location = origin
        obj.keyframe_insert("location", frame=start)
        obj.location = origin + direction * settings["distance_m"]
        obj.keyframe_insert("location", frame=end)
        _tag_action(obj, "vehicle")
        _finish_curves(obj, cyclic=cyclic)
        obj["c2w_dynamic_role"] = "vehicle"
        animated.add(obj.name)
        if settings["wheel_spin"]:
            wheel_count += _animate_wheels(
                obj,
                settings["distance_m"],
                start,
                end,
                settings["wheel_radius_m"],
                cyclic,
            )

    report["vehicles"] = {
        "enabled": True,
        "animated": len(animated),
        "objects": sorted(animated),
        "animated_wheels": wheel_count,
        "skipped": skipped,
    }


def _tree_roots(settings: dict[str, Any]) -> list[bpy.types.Object]:
    candidates: list[bpy.types.Object] = _loose_tree_roots(settings)
    for name in settings["object_names"]:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            candidates.append(obj)

    pool = _objects_from_collections(settings["collection_names"])
    pool.extend(
        obj for obj in bpy.data.objects if _text(obj.get("c2w_dynamic_role")) == "tree"
    )
    for obj in pool:
        semantics = _object_semantics(obj)
        explicit_role = _text(obj.get("c2w_dynamic_role")) in {"tree", "vegetation"}
        root_like = obj.parent is None and (
            obj.type == "EMPTY" or _matches(semantics, settings["name_patterns"])
        )
        if explicit_role or root_like:
            candidates.append(obj)
    return _dedupe_objects(candidates)[: settings["max_objects"]]


def add_wind_motion(config: dict[str, Any], report: dict[str, Any]) -> None:
    settings = config["effects"]["wind"]
    if not settings["enabled"]:
        report["wind"] = {"enabled": False, "animated": 0}
        return
    start = config["timeline"]["frame_start"]
    period = int(settings["period_frames"])
    cyclic = config["timeline"]["loop"]
    amplitude = math.radians(settings["angle_degrees"])
    animated: list[str] = []
    skipped: list[str] = []

    for obj in _tree_roots(settings):
        if _has_user_animation(obj):
            skipped.append(f"preserved existing animation: {obj.name}")
            continue
        obj.rotation_mode = "XYZ"
        base = obj.rotation_euler.copy()
        seed = sum((index + 1) * ord(char) for index, char in enumerate(obj.name))
        phase = seed % period
        direction = -1.0 if seed % 2 else 1.0
        frames = [start - phase + period * index / 4 for index in range(5)]
        values = [0.0, 1.0, 0.0, -1.0, 0.0]
        for frame, value in zip(frames, values):
            obj.rotation_euler.x = base.x + value * amplitude * 0.55
            obj.rotation_euler.y = base.y + value * amplitude * direction
            obj.keyframe_insert("rotation_euler", frame=frame)
        _tag_action(obj, "wind")
        _finish_curves(obj, cyclic=cyclic, interpolation="BEZIER")
        obj["c2w_dynamic_role"] = "tree"
        animated.append(obj.name)

    report["wind"] = {
        "enabled": True,
        "animated": len(animated),
        "objects": sorted(animated),
        "skipped": skipped,
    }


def _water_objects(settings: dict[str, Any]) -> list[bpy.types.Object]:
    candidates: list[bpy.types.Object] = []
    for name in settings["object_names"]:
        obj = bpy.data.objects.get(name)
        if obj is not None:
            candidates.append(obj)
    candidates.extend(_objects_from_collections(settings["collection_names"]))
    for obj in bpy.data.objects:
        semantics = _object_semantics(obj)
        material_names = " ".join(
            slot.material.name
            for slot in obj.material_slots
            if slot.material is not None
        )
        if _matches(semantics, settings["name_patterns"]) or _matches(
            material_names, settings["material_patterns"]
        ):
            candidates.append(obj)
    return _dedupe_objects(candidates)


def _socket(node: bpy.types.Node, name: str) -> Any:
    try:
        return node.inputs.get(name)
    except AttributeError:
        return None


def _keyframe_socket(socket: Any, start: int, end: int, amount: float) -> bool:
    if socket is None or not hasattr(socket, "default_value"):
        return False
    try:
        initial = float(socket.default_value)
        socket.default_value = initial
        socket.keyframe_insert("default_value", frame=start)
        socket.default_value = initial + amount
        socket.keyframe_insert("default_value", frame=end)
        return True
    except (TypeError, ValueError, RuntimeError):
        return False


def _animate_water_material(
    material: bpy.types.Material,
    settings: dict[str, Any],
    start: int,
    end: int,
    cyclic: bool,
) -> bool:
    material.use_nodes = True
    tree = material.node_tree
    if tree is None or _has_user_animation(tree):
        return False
    nodes, links = tree.nodes, tree.links
    animated = False

    for node in nodes:
        if node.bl_idname == "ShaderNodeTexNoise":
            try:
                node.noise_dimensions = "4D"
            except (AttributeError, TypeError):
                pass
            animated |= _keyframe_socket(
                _socket(node, "W"), start, end, settings["speed"]
            )
        elif node.bl_idname == "ShaderNodeTexWave":
            animated |= _keyframe_socket(
                _socket(node, "Phase Offset"), start, end, settings["speed"] * math.tau
            )

    if not animated:
        bsdf = next(
            (node for node in nodes if node.bl_idname == "ShaderNodeBsdfPrincipled"),
            None,
        )
        if bsdf is None:
            return False
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.name = "C2W_Dynamics_WaterCoordinates"
        noise = nodes.new("ShaderNodeTexNoise")
        noise.name = "C2W_Dynamics_FlowNoise"
        noise.noise_dimensions = "4D"
        scale = _socket(noise, "Scale")
        if scale is not None:
            scale.default_value = settings["wave_scale"]
        detail = _socket(noise, "Detail")
        if detail is not None:
            detail.default_value = 5.0
        bump = nodes.new("ShaderNodeBump")
        bump.name = "C2W_Dynamics_WaterBump"
        strength = _socket(bump, "Strength")
        distance = _socket(bump, "Distance")
        if strength is not None:
            strength.default_value = settings["wave_strength"]
        if distance is not None:
            distance.default_value = 0.12
        links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        normal = _socket(bsdf, "Normal")
        if normal is not None:
            existing = normal.links[0] if normal.is_linked and normal.links else None
            if existing is not None:
                upstream = existing.from_socket
                links.remove(existing)
                links.new(upstream, bump.inputs["Normal"])
            links.new(bump.outputs["Normal"], normal)
        animated = _keyframe_socket(_socket(noise, "W"), start, end, settings["speed"])

    if animated:
        material[TAG] = True
        _tag_action(tree, "river")
        _finish_curves(tree, cyclic=cyclic)
    return animated


def add_river_motion(config: dict[str, Any], report: dict[str, Any]) -> None:
    settings = config["effects"]["river"]
    if not settings["enabled"]:
        report["river"] = {"enabled": False, "animated_materials": 0}
        return
    start = config["timeline"]["frame_start"]
    end = config["timeline"]["frame_end"] + 1
    cyclic = config["timeline"]["loop"]
    copied: dict[int, bpy.types.Material] = {}
    animated: list[str] = []
    skipped: list[str] = []

    for obj in _water_objects(settings):
        object_match = _matches(_object_semantics(obj), settings["name_patterns"])
        for slot in obj.material_slots:
            original = slot.material
            if original is None:
                continue
            if not object_match and not _matches(
                original.name, settings["material_patterns"]
            ):
                continue
            pointer = original.as_pointer()
            material = copied.get(pointer)
            if material is None:
                material = original.copy()
                material.name = f"{original.name}__C2W_DYNAMIC"
                copied[pointer] = material
                if len(copied) > settings["max_materials"]:
                    skipped.append("material limit reached")
                    break
                if _animate_water_material(material, settings, start, end, cyclic):
                    animated.append(material.name)
                else:
                    skipped.append(f"could not animate material: {original.name}")
            slot.material = material

    report["river"] = {
        "enabled": True,
        "animated_materials": len(animated),
        "materials": sorted(set(animated)),
        "skipped": skipped,
    }


def _fountain_center(settings: dict[str, Any]) -> Vector | None:
    if settings.get("center") is not None:
        return Vector(settings["center"])
    exact = set(settings["object_names"])
    matches: list[Vector] = []
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for instance in depsgraph.object_instances:
        obj = instance.object
        if obj is None:
            continue
        semantics = _object_semantics(obj)
        if (
            obj.name in exact
            or _text(obj.get("c2w_dynamic_role")) == "fountain"
            or _matches(semantics, settings["name_patterns"])
        ):
            matches.append(instance.matrix_world.translation.copy())
    if not matches:
        return None
    # Pool/rim origins are normally the lowest matching points.  Selecting the
    # lowest match also avoids averaging together separate fountains.
    return min(matches, key=lambda point: point.z)


def _fountain_material() -> bpy.types.Material:
    material = bpy.data.materials.new("C2W_Dynamics_FountainWater")
    material.use_nodes = True
    material.diffuse_color = (0.18, 0.52, 0.82, 0.72)
    bsdf = next(
        node
        for node in material.node_tree.nodes
        if node.bl_idname == "ShaderNodeBsdfPrincipled"
    )
    for name, value in (
        ("Base Color", (0.08, 0.34, 0.68, 1.0)),
        ("Roughness", 0.08),
        ("Metallic", 0.0),
        ("Transmission Weight", 0.35),
        ("Alpha", 0.78),
    ):
        socket = _socket(bsdf, name)
        if socket is not None:
            socket.default_value = value
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    elif hasattr(material, "blend_method"):
        material.blend_method = "BLEND"
    material[TAG] = True
    return material


def _droplet_mesh(radius: float, material: bpy.types.Material) -> bpy.types.Mesh:
    mesh = bpy.data.meshes.new("C2W_Dynamics_DropletMesh")
    editable = bmesh.new()
    bmesh.ops.create_icosphere(editable, subdivisions=1, radius=radius)
    editable.to_mesh(mesh)
    editable.free()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    mesh.materials.append(material)
    mesh[TAG] = True
    return mesh


def add_fountain_motion(config: dict[str, Any], report: dict[str, Any]) -> None:
    settings = config["effects"]["fountain"]
    if not settings["enabled"]:
        report["fountain"] = {"enabled": False, "animated_droplets": 0}
        return
    center = _fountain_center(settings)
    if center is None:
        report["fountain"] = {
            "enabled": True,
            "animated_droplets": 0,
            "skipped": ["no fountain target found; set effects.fountain.center"],
        }
        return

    collection = bpy.data.collections.new("C2W_Dynamics_Fountain")
    collection[TAG] = True
    bpy.context.scene.collection.children.link(collection)
    material = _fountain_material()
    mesh = _droplet_mesh(settings["droplet_radius_m"], material)
    start = config["timeline"]["frame_start"]
    period = int(settings["period_frames"])
    cyclic = config["timeline"]["loop"]
    base = center + Vector((0.0, 0.0, settings["base_height_m"]))
    count = 0

    for jet in range(int(settings["jet_count"])):
        angle = math.tau * jet / settings["jet_count"]
        direction = Vector((math.cos(angle), math.sin(angle), 0.0))
        for index in range(int(settings["droplets_per_jet"])):
            phase = period * (
                index / settings["droplets_per_jet"] + jet / settings["jet_count"]
            )
            frame0 = start - phase
            droplet = bpy.data.objects.new(
                f"C2W_FountainDrop_{jet:02d}_{index:02d}", mesh
            )
            droplet[TAG] = True
            droplet["c2w_dynamic_role"] = "fountain_droplet"
            collection.objects.link(droplet)
            keys = (
                (frame0, base, 0.65),
                (
                    frame0 + period * 0.50,
                    base
                    + direction * settings["jet_radius_m"] * 0.48
                    + Vector((0.0, 0.0, settings["jet_height_m"])),
                    1.0,
                ),
                (
                    frame0 + period,
                    base
                    + direction * settings["jet_radius_m"]
                    + Vector((0.0, 0.0, -0.25)),
                    0.72,
                ),
            )
            for frame, location, scale in keys:
                droplet.location = location
                droplet.scale = (scale, scale, scale * 1.6)
                droplet.keyframe_insert("location", frame=frame)
                droplet.keyframe_insert("scale", frame=frame)
            _tag_action(droplet, "fountain")
            _finish_curves(droplet, cyclic=cyclic, interpolation="BEZIER")
            count += 1

    report["fountain"] = {
        "enabled": True,
        "animated_droplets": count,
        "center": [round(value, 4) for value in center],
    }


def _look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )


def configure_camera(
    config: dict[str, Any], report: dict[str, Any]
) -> bpy.types.Object | None:
    settings = config["camera"]
    scene = bpy.context.scene
    if settings["mode"] == "existing":
        camera = (
            bpy.data.objects.get(settings["name"]) if settings["name"] else scene.camera
        )
        if camera is None:
            camera = next(
                (obj for obj in bpy.data.objects if obj.type == "CAMERA"), None
            )
        if camera is not None:
            scene.camera = camera
            report["camera"] = {"mode": "existing", "object": camera.name}
        else:
            report["camera"] = {"mode": "existing", "object": None}
        return camera

    target = Vector(settings["target"])
    data = bpy.data.cameras.new("C2W_Dynamics_OrbitCameraData")
    data.lens = settings["lens_mm"]
    camera = bpy.data.objects.new("C2W_Dynamics_OrbitCamera", data)
    camera[TAG] = True
    bpy.context.scene.collection.objects.link(camera)
    start = config["timeline"]["frame_start"]
    end = config["timeline"]["frame_end"] + 1
    for index in range(5):
        ratio = index / 4
        degrees = (
            settings["start_degrees"]
            + (settings["end_degrees"] - settings["start_degrees"]) * ratio
        )
        angle = math.radians(degrees)
        camera.location = target + Vector(
            (
                math.cos(angle) * settings["radius"],
                math.sin(angle) * settings["radius"],
                settings["height"],
            )
        )
        _look_at(camera, target)
        frame = start + (end - start) * ratio
        camera.keyframe_insert("location", frame=frame)
        camera.keyframe_insert("rotation_euler", frame=frame)
    _tag_action(camera, "camera")
    _finish_curves(camera, cyclic=config["timeline"]["loop"], interpolation="BEZIER")
    scene.camera = camera
    report["camera"] = {"mode": "orbit", "object": camera.name}
    return camera


def _available_render_engines(scene: bpy.types.Scene) -> set[str]:
    try:
        return {
            item.identifier
            for item in scene.render.bl_rna.properties["engine"].enum_items
        }
    except (KeyError, AttributeError):
        return {scene.render.engine}


def configure_render(
    config: dict[str, Any], video_override: str = ""
) -> tuple[Path, Path | None]:
    scene = bpy.context.scene
    settings = config["render"]
    requested_engine = settings.get("engine")
    engines = _available_render_engines(scene)
    if requested_engine == "AUTO_EEVEE":
        requested_engine = next(
            (name for name in engines if "EEVEE" in name), scene.render.engine
        )
    elif requested_engine not in engines and requested_engine in {
        "BLENDER_EEVEE",
        "BLENDER_EEVEE_NEXT",
    }:
        requested_engine = next(
            (name for name in engines if "EEVEE" in name), scene.render.engine
        )
    if requested_engine:
        try:
            scene.render.engine = requested_engine
        except TypeError:
            print(f"[dynamics] WARNING: render engine unavailable: {requested_engine}")
    scene.render.resolution_x = settings["resolution_x"]
    scene.render.resolution_y = settings["resolution_y"]
    scene.render.resolution_percentage = settings["resolution_percentage"]
    scene.render.film_transparent = settings["transparent"]
    if "EEVEE" in scene.render.engine and hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = settings["samples"]
    elif scene.render.engine == "CYCLES":
        scene.cycles.samples = settings["samples"]
    video = _absolute(video_override or settings["video_path"])
    video.parent.mkdir(parents=True, exist_ok=True)
    try:
        scene.render.image_settings.file_format = "FFMPEG"
    except TypeError:
        # Some Blender packages expose FFmpeg in RNA but compile movie output
        # out of the active render engine.  Render PNG frames and encode with
        # the system ffmpeg binary in that case.
        frame_dir = video.parent / f"{video.stem}_frames"
        frame_dir.mkdir(parents=True, exist_ok=True)
        scene.render.image_settings.file_format = "PNG"
        scene.render.filepath = str(frame_dir / "frame_")
        return video, frame_dir
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.audio_codec = "AAC"
    scene.render.filepath = str(video)
    return video, None


def _encode_external_video(
    video: Path, frame_dir: Path, config: dict[str, Any]
) -> None:
    timeline = config["timeline"]
    command = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(timeline["fps"]),
        "-start_number",
        str(timeline["frame_start"]),
        "-i",
        str(frame_dir / "frame_%04d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(video),
    ]
    print(
        "[dynamics] Blender movie output unavailable; encoding PNG frames with ffmpeg"
    )
    subprocess.run(command, check=True)
    if not config["render"]["keep_frames"]:
        for frame in range(timeline["frame_start"], timeline["frame_end"] + 1):
            generated = frame_dir / f"frame_{frame:04d}.png"
            if generated.exists():
                generated.unlink()
        try:
            frame_dir.rmdir()
        except OSError:
            pass


def _save_report(path: Path, report: dict[str, Any]) -> Path:
    report_path = path.with_suffix(".dynamics.json")
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return report_path


def main() -> None:
    args = _cli_args()
    input_path = _absolute(args.input)
    output_path = _absolute(args.output)
    if input_path == output_path:
        raise ValueError(
            "Refusing to overwrite the static input scene; choose a different --output"
        )
    if not input_path.is_file():
        raise FileNotFoundError(f"Input scene does not exist: {input_path}")
    config = load_config(_absolute(args.config) if args.config else None)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[dynamics] Opening static scene: {input_path}")
    bpy.ops.wm.open_mainfile(filepath=str(input_path))
    _set_scene_timeline(config)
    report: dict[str, Any] = {
        "input": str(input_path),
        "output": str(output_path),
        "config_version": config["version"],
        "timeline": config["timeline"],
        "effects": {},
    }

    print("[dynamics] Animating vehicles")
    add_vehicle_motion(config, report["effects"])
    print("[dynamics] Animating vegetation wind")
    add_wind_motion(config, report["effects"])
    print("[dynamics] Animating river/water materials")
    add_river_motion(config, report["effects"])
    print("[dynamics] Building fountain droplets")
    add_fountain_motion(config, report["effects"])
    camera = configure_camera(config, report)
    video_path, frame_dir = configure_render(config, args.video)
    report["video"] = str(video_path)
    report["render_backend"] = "external_ffmpeg" if frame_dir else "blender_ffmpeg"
    report["render_requested"] = bool(args.render)

    bpy.context.scene.frame_set(config["timeline"]["frame_start"])
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
    report_path = _save_report(output_path, report)
    print(f"[dynamics] Dynamic scene saved: {output_path}")
    print(f"[dynamics] Discovery report saved: {report_path}")

    if args.render:
        if camera is None:
            raise RuntimeError(
                "Cannot render video: no camera was found; use camera.mode='orbit'"
            )
        print(f"[dynamics] Rendering video: {video_path}")
        bpy.ops.render.render(animation=True)
        if frame_dir is not None:
            _encode_external_video(video_path, frame_dir, config)
        bpy.ops.wm.save_as_mainfile(filepath=str(output_path))
        print(f"[dynamics] Video rendered: {video_path}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build the non-destructive dynamic delivery scene for ``urban_v1_full_13``.

This pass deliberately starts from the certified, resource-safe direct scene
pack rather than opening the 82-placement production master.  The master pulls
every multi-gigabyte library into one Blender process and is not a viable
animation/render unit.  Geometry is never substituted: local object wrappers
reuse the exact linked meshes and only the wrappers, materials and modifiers
needed for animation are made local.

Run with Blender::

    blender --background --factory-startup \
      --python scripts/build_urban_v1_full_13_dynamic.py -- \
      --output-dir infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic
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


import argparse
import hashlib
import json
import math
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
STATIC_DIR = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
STATIC_MASTER = STATIC_DIR / "urban_v1_full_13.blend"
BASE_PACK = STATIC_DIR / "render_dependency_packs/base.blend"
PARK_PACK = STATIC_DIR / "render_dependency_packs/direct_park_lake.blend"
SOURCE_PACK = BASE_PACK
DEFAULT_OUTPUT_DIR = STATIC_DIR.parent / "urban_v1_full_13-dynamic"
TAG = "c2w_full13_dynamic"
START_FRAME = 1
END_FRAME = 144
FPS = 24

TREE_COLLECTION_PREFIX = "full02:MASTER:TreeFactory:"
TREE_OBJECT_PATTERNS = (
    "pk_tr",
    "riparian_botanical_tree",
    "high_detail_park_tree",
)
FLUID_NAME_PATTERNS = (
    "water",
    "hydraulic",
    "agitated",
    "spill",
    "droplet",
    "mist",
    "jet",
    "spray",
    "foam",
    "ripple",
    "plume",
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--source-pack", type=Path, default=SOURCE_PACK)
    parser.add_argument("--frame-end", type=int, default=END_FRAME)
    parser.add_argument("--fps", type=int, default=FPS)
    return parser.parse_args(argv)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def keyframe(owner: Any, data_path: str, frame: float, *, index: int = -1) -> None:
    if index >= 0:
        owner.keyframe_insert(data_path=data_path, index=index, frame=frame)
    else:
        owner.keyframe_insert(data_path=data_path, frame=frame)


def action_fcurves(owner: Any) -> list[Any]:
    animation = getattr(owner, "animation_data", None)
    action = getattr(animation, "action", None) if animation else None
    if action is None:
        return []
    try:
        return list(action.fcurves)
    except (AttributeError, RuntimeError):
        result = []
        for layer in getattr(action, "layers", []):
            for strip in getattr(layer, "strips", []):
                for channelbag in getattr(strip, "channelbags", []):
                    result.extend(channelbag.fcurves)
        return result


def finish_animation(owner: Any, *, linear: bool, cyclic: bool = False) -> None:
    for curve in action_fcurves(owner):
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR" if linear else "BEZIER"
        if cyclic and not any(mod.type == "CYCLES" for mod in curve.modifiers):
            curve.modifiers.new("CYCLES")


def scene_placement(placement_id: str) -> bpy.types.Object | None:
    return next(
        (
            obj
            for obj in bpy.context.scene.objects
            if obj.get("placement_id") == placement_id
        ),
        None,
    )


def prune_static_placements() -> dict[str, Any]:
    """Keep only certified placements that can enter one of the four shots.

    The removed roots remain available in the unchanged static master and its
    other certified render packs.  Removing them from this delivery scene is a
    render-set operation, not a geometry substitution.
    """

    keep = {
        "compact_irregular_city_ground",
        "full13_physical_continuous_road_substrate",
        "full13_road_main_m272.5_0",
        "full13_road_main_m163.5_0",
        "full13_road_main_m54.5_0",
        "full13_road_main_54.5_0",
        "full13_road_main_163.5_0",
        "full13_road_main_272.5_0",
        "full13_road_link_m54.5_m109",
        "full13_road_east_272p5_m109",
        "full13_road_east_272p5_109",
        "full13_single_road_activity_module",
    }
    removed = []
    for obj in list(bpy.context.scene.objects):
        placement_id = obj.get("placement_id")
        if placement_id and placement_id not in keep:
            removed.append(str(placement_id))
            bpy.data.objects.remove(obj, do_unlink=True)
    return {"kept": sorted(keep), "removed": sorted(removed)}


def animate_render_visibility(
    obj: bpy.types.Object,
    global_start: int,
    global_end: int,
    visible_start: int,
    visible_end: int,
) -> None:
    """Use constant visibility cuts so off-shot heavy assets are not evaluated."""

    frames = {global_start, global_end, visible_start, visible_end}
    if visible_start > global_start:
        frames.add(visible_start - 1)
    if visible_end < global_end:
        frames.add(visible_end + 1)
    for frame in sorted(frames):
        obj.hide_render = not (visible_start <= frame <= visible_end)
        keyframe(obj, "hide_render", frame)
    for curve in action_fcurves(obj):
        if curve.data_path != "hide_render":
            continue
        for point in curve.keyframe_points:
            point.interpolation = "CONSTANT"


def create_placement(
    placement_id: str,
    collection: bpy.types.Collection,
    location: Iterable[float],
    *,
    category: str,
    source_collection: str,
) -> bpy.types.Object:
    existing = scene_placement(placement_id)
    if existing is not None:
        existing.instance_collection = collection
        existing.instance_type = "COLLECTION"
        existing[TAG] = True
        return existing
    root = bpy.data.objects.new(f"C2W_DynamicPlacement:{placement_id}", None)
    bpy.context.scene.collection.objects.link(root)
    root.instance_type = "COLLECTION"
    root.instance_collection = collection
    root.location = tuple(location)
    root["placement_id"] = placement_id
    root["category"] = category
    root["source_collection"] = source_collection
    root["reuse_policy"] = "exact_linked_geometry_local_animation_wrappers"
    root[TAG] = True
    return root


def append_collection(path: Path, name: str) -> bpy.types.Collection:
    existing = bpy.data.collections.get(name)
    if existing is not None:
        return existing
    with bpy.data.libraries.load(str(path), link=True) as (data_from, data_to):
        if name not in data_from.collections:
            raise KeyError(f"Collection {name!r} is not present in {path}")
        data_to.collections = [name]
    collection = data_to.collections[0]
    if collection is None:
        raise RuntimeError(f"Failed to link {name!r} from {path}")
    return collection


def copy_collection_objects(
    source: bpy.types.Collection, name: str
) -> tuple[bpy.types.Collection, dict[bpy.types.Object, bpy.types.Object]]:
    """Create local object wrappers while retaining exact linked data blocks."""

    target = bpy.data.collections.new(name)
    target[TAG] = True
    originals = list(source.all_objects)
    mapping: dict[bpy.types.Object, bpy.types.Object] = {}
    for original in originals:
        duplicate = original.copy()
        duplicate.name = f"C2W_DYN::{original.name}"
        duplicate[TAG] = True
        try:
            duplicate.animation_data_clear()
        except RuntimeError:
            pass
        target.objects.link(duplicate)
        mapping[original] = duplicate

    for original, duplicate in mapping.items():
        duplicate.parent = mapping.get(original.parent)
        duplicate.matrix_parent_inverse = original.matrix_parent_inverse.copy()
        duplicate.matrix_basis = original.matrix_basis.copy()
    return target, mapping


def local_material_slot(
    obj: bpy.types.Object,
    index: int,
    material: bpy.types.Material,
) -> bool:
    try:
        slot = obj.material_slots[index]
        slot.link = "OBJECT"
        slot.material = material
        return True
    except (AttributeError, IndexError, RuntimeError):
        return False


def socket(node: bpy.types.Node, name: str) -> Any:
    try:
        return node.inputs.get(name)
    except AttributeError:
        return None


def keyframe_socket(sock: Any, frames: list[int], values: list[Any]) -> bool:
    if sock is None or not hasattr(sock, "default_value"):
        return False
    try:
        for frame, value in zip(frames, values):
            sock.default_value = value
            sock.keyframe_insert("default_value", frame=frame)
        return True
    except (TypeError, ValueError, RuntimeError):
        return False


def animate_fluid_material(
    original: bpy.types.Material,
    start: int,
    end: int,
    *,
    directional: bool,
) -> bpy.types.Material:
    material = original.copy()
    material.name = f"{original.name}__C2W_FULL13_DYNAMIC"
    material[TAG] = True
    if not material.use_nodes or material.node_tree is None:
        return material

    quarter = start + (end - start) // 4
    half = start + (end - start) // 2
    three_quarter = start + 3 * (end - start) // 4
    loop_frames = [start, quarter, half, three_quarter, end + 1]
    for index, node in enumerate(material.node_tree.nodes):
        if node.bl_idname == "ShaderNodeTexWave":
            phase = socket(node, "Phase Offset")
            initial = float(phase.default_value) if phase is not None else 0.0
            turns = 2.0 if directional else 1.0
            keyframe_socket(
                phase,
                [start, end + 1],
                [initial, initial + math.tau * turns],
            )
        elif node.bl_idname == "ShaderNodeTexNoise":
            try:
                node.noise_dimensions = "4D"
            except (AttributeError, TypeError):
                pass
            w_value = socket(node, "W")
            initial = float(w_value.default_value) if w_value is not None else 0.0
            amplitude = 0.78 + 0.17 * (index % 3)
            keyframe_socket(
                w_value,
                loop_frames,
                [
                    initial,
                    initial + amplitude,
                    initial + 2 * amplitude,
                    initial + 3 * amplitude,
                    initial + 4 * amplitude,
                ],
            )
    finish_animation(material.node_tree, linear=True, cyclic=False)
    return material


def add_flow_displace(
    obj: bpy.types.Object,
    flow_control: bpy.types.Object,
    *,
    strength: float,
    texture_scale: float,
    label: str,
) -> bool:
    if obj.type != "MESH" or obj.data is None or len(obj.data.vertices) < 24:
        return False
    texture = bpy.data.textures.new(f"C2W_{label}_{obj.name[:36]}", type="CLOUDS")
    texture.noise_scale = texture_scale
    texture.noise_depth = 2
    modifier = obj.modifiers.new(f"C2W_{label}_MicroDisplacement", "DISPLACE")
    modifier.texture = texture
    modifier.texture_coords = "OBJECT"
    modifier.texture_coords_object = flow_control
    modifier.direction = "NORMAL"
    modifier.mid_level = 0.5
    modifier.strength = strength
    return True


def create_flow_control(
    collection: bpy.types.Collection,
    name: str,
    start: int,
    end: int,
    travel: tuple[float, float, float],
) -> bpy.types.Object:
    control = bpy.data.objects.new(name, None)
    collection.objects.link(control)
    control[TAG] = True
    control.hide_render = True
    control.location = (0.0, 0.0, 0.0)
    keyframe(control, "location", start)
    control.location = travel
    keyframe(control, "location", end + 1)
    finish_animation(control, linear=True)
    return control


class TreeAnimator:
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end
        self.cache: dict[int, bpy.types.Collection] = {}
        self.created: list[str] = []

    def dynamic_master(self, source: bpy.types.Collection) -> bpy.types.Collection:
        pointer = source.as_pointer()
        if pointer in self.cache:
            return self.cache[pointer]
        target, mapping = copy_collection_objects(
            source, f"C2W_DynamicTreeMaster::{source.name}"
        )
        seed = sum((index + 1) * ord(char) for index, char in enumerate(source.name))
        phase_sign = -1.0 if seed % 2 else 1.0
        frames = [
            self.start,
            self.start + (self.end - self.start) // 4,
            self.start + (self.end - self.start) // 2,
            self.start + 3 * (self.end - self.start) // 4,
            self.end + 1,
        ]
        values = [0.0, 1.0, 0.0, -1.0, 0.0]
        for original, duplicate in mapping.items():
            if duplicate.type != "MESH":
                continue
            folded = original.name.casefold()
            is_leaf = (
                "leaf" in folded
                or "canopy" in folded
                or any(
                    slot.material and "leaf" in slot.material.name.casefold()
                    for slot in duplicate.material_slots
                )
            )
            # The exact botanical canopies contain 11--30 million vertices per
            # species.  A per-vertex SimpleDeform/Displace modifier would make
            # Eevee materialise hundreds of millions of temporary vertices.
            # Animate the authored trunk and merged canopy transforms instead:
            # this retains every source vertex/material and gives the canopy a
            # slightly larger, independently phased response than the trunk.
            duplicate.rotation_mode = "XYZ"
            base_rotation = duplicate.rotation_euler.copy()
            base_scale = duplicate.scale.copy()
            amplitude = math.radians(1.15 if is_leaf else 0.26)
            for frame, value in zip(frames, values):
                duplicate.rotation_euler = base_rotation.copy()
                duplicate.rotation_euler.x += value * amplitude * phase_sign
                duplicate.rotation_euler.y += value * amplitude * 0.42
                if is_leaf:
                    duplicate.rotation_euler.z += value * math.radians(0.22)
                    flutter = 1.0 + value * 0.0018
                    duplicate.scale = (
                        base_scale.x * flutter,
                        base_scale.y / flutter,
                        base_scale.z,
                    )
                keyframe(duplicate, "rotation_euler", frame)
                if is_leaf:
                    keyframe(duplicate, "scale", frame)
            finish_animation(duplicate, linear=False)
            if is_leaf:
                finish_animation(duplicate, linear=False)
        self.cache[pointer] = target
        self.created.append(target.name)
        return target

    def replace_tree_instances(
        self, mapping: dict[bpy.types.Object, bpy.types.Object]
    ) -> int:
        count = 0
        for original, duplicate in mapping.items():
            collection = original.instance_collection
            if collection is None:
                continue
            folded = original.name.casefold()
            if not (
                collection.name.startswith(TREE_COLLECTION_PREFIX)
                or any(pattern in folded for pattern in TREE_OBJECT_PATTERNS)
            ):
                continue
            duplicate.instance_collection = self.dynamic_master(collection)
            duplicate["c2w_dynamic_role"] = "wind_tree_instance"
            count += 1
        return count


def animate_vehicle_root(
    root: bpy.types.Object,
    ordinal: int,
    start: int,
    end: int,
) -> tuple[float, int]:
    heading = Vector(
        (math.cos(root.rotation_euler.z), math.sin(root.rotation_euler.z), 0.0)
    )
    axis = 0 if abs(heading.x) >= abs(heading.y) else 1
    sign = 1.0 if heading[axis] >= 0.0 else -1.0
    route_min, route_max = -67.0, 67.0
    origin = root.location.copy()
    route_start = origin.copy()
    route_end = origin.copy()
    route_start[axis] = route_min if sign > 0 else route_max
    route_end[axis] = route_max if sign > 0 else route_min
    # One traversal spans two clips.  The visible 36-frame traffic shot therefore
    # covers about 16.75 m at 40.2 km/h instead of making a city car sprint from
    # one end of the 134 m route to the other in six seconds.
    duration = 2 * (end - start + 1)
    phase = (ordinal % 6) * duration / 6.0
    first = start - phase
    last = end + 1 - phase
    root.location = route_start
    keyframe(root, "location", first)
    root.location = route_end
    keyframe(root, "location", last)
    finish_animation(root, linear=True, cyclic=True)
    root["c2w_dynamic_role"] = "vehicle"
    root["c2w_vehicle_speed_mps"] = round(
        (route_end - route_start).length / (duration / FPS), 3
    )

    distance = (route_end - route_start).length
    wheel_count = 0
    for child in root.children_recursive:
        if "grp_wheel_steering_rotating" not in child.name.casefold():
            continue
        child.rotation_mode = "XYZ"
        base = child.rotation_euler.y
        child.rotation_euler.y = base
        keyframe(child, "rotation_euler", first, index=1)
        child.rotation_euler.y = base - sign * distance / 0.37
        keyframe(child, "rotation_euler", last, index=1)
        finish_animation(child, linear=True, cyclic=True)
        wheel_count += 1
    return distance, wheel_count


def dynamicize_traffic(
    tree_animator: TreeAnimator,
    start: int,
    end: int,
) -> dict[str, Any]:
    del tree_animator  # Kept in the signature to make effect orchestration explicit.
    placement = scene_placement("full13_single_road_activity_module")
    if placement is None or placement.instance_collection is None:
        raise RuntimeError("The certified road activity placement is missing")
    target, mapping = copy_collection_objects(
        placement.instance_collection, "C2W_DynamicRoadActivity"
    )
    placement.instance_collection = target
    placement[TAG] = True
    roots = sorted(
        (
            duplicate
            for original, duplicate in mapping.items()
            if original.parent is None
            and re.fullmatch(r"v[nsew]\d+_Grp_Root", original.name, re.IGNORECASE)
        ),
        key=lambda obj: obj.name,
    )
    distance = 0.0
    wheel_count = 0
    for ordinal, root in enumerate(roots):
        travelled, wheels = animate_vehicle_root(root, ordinal, start, end)
        distance += travelled
        wheel_count += wheels
    return {
        "vehicle_count": len(roots),
        "animated_wheel_rig_count": wheel_count,
        "aggregate_route_length_m": round(distance, 3),
        "asset_source": "exact OpenX vehicle hierarchies already authored in full_13",
    }


def dynamicize_water_collection(
    placement: bpy.types.Object,
    source: bpy.types.Collection,
    name: str,
    tree_animator: TreeAnimator,
    start: int,
    end: int,
    *,
    directional: bool,
    fountain: bool = False,
) -> dict[str, Any]:
    target, mapping = copy_collection_objects(source, name)
    placement.instance_collection = target
    placement[TAG] = True
    tree_count = tree_animator.replace_tree_instances(mapping)
    flow = create_flow_control(
        target,
        f"C2W_FlowControl::{name}",
        start,
        end,
        (0.0, 10.0 if directional else 3.0, 1.2 if fountain else 0.0),
    )
    material_cache: dict[int, bpy.types.Material] = {}
    material_names: set[str] = set()
    displaced = 0
    pulsing = 0
    for original, duplicate in mapping.items():
        folded = original.name.casefold()
        is_fluid_object = any(pattern in folded for pattern in FLUID_NAME_PATTERNS)
        for index, slot in enumerate(original.material_slots):
            original_material = slot.material
            if original_material is None:
                continue
            material_folded = original_material.name.casefold()
            if not is_fluid_object and not any(
                pattern in material_folded for pattern in ("water", "spray", "foam")
            ):
                continue
            pointer = original_material.as_pointer()
            dynamic_material = material_cache.get(pointer)
            if dynamic_material is None:
                dynamic_material = animate_fluid_material(
                    original_material, start, end, directional=directional
                )
                material_cache[pointer] = dynamic_material
                material_names.add(dynamic_material.name)
            local_material_slot(duplicate, index, dynamic_material)

        if not is_fluid_object or duplicate.type != "MESH":
            continue
        strength = 0.028 if fountain else (0.052 if directional else 0.026)
        texture_scale = 0.13 if fountain else (0.85 if directional else 1.35)
        if add_flow_displace(
            duplicate,
            flow,
            strength=strength,
            texture_scale=texture_scale,
            label="FountainFlow" if fountain else "WaterFlow",
        ):
            displaced += 1
        if fountain and any(
            token in folded
            for token in ("pressure_j", "laminar_shee", "vertical_aerated_plu")
        ):
            base = duplicate.scale.copy()
            period = 36
            phase = (sum(ord(char) for char in original.name) % period) / period
            for index, value in enumerate((0.985, 1.025, 0.992, 1.018, 0.985)):
                frame = start - phase * period + index * period / 4
                duplicate.scale = (base.x, base.y, base.z * value)
                keyframe(duplicate, "scale", frame)
            finish_animation(duplicate, linear=False, cyclic=True)
            pulsing += 1
    return {
        "local_exact_object_wrappers": len(mapping),
        "animated_materials": sorted(material_names),
        "geometry_displace_objects": displaced,
        "tree_instances": tree_count,
        "pressure_stream_objects": pulsing,
    }


def look_at(camera: bpy.types.Object, target: Vector) -> None:
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )


def build_camera(scene: bpy.types.Scene, start: int, end: int) -> dict[str, Any]:
    camera_data = bpy.data.cameras.new("C2W_Full13_DynamicCameraData")
    camera_data.lens = 46.0
    camera_data.sensor_width = 36.0
    camera_data.clip_start = 0.1
    camera_data.clip_end = 3000.0
    camera = bpy.data.objects.new("C2W_Full13_DynamicCamera", camera_data)
    scene.collection.objects.link(camera)
    camera[TAG] = True
    scene.camera = camera

    duration = end - start + 1
    shot_length = duration // 4
    shots = [
        {
            "name": "traffic",
            "start": start,
            "end": start + shot_length - 1,
            "from": (334.0, -58.0, 13.5),
            "to": (326.0, -51.0, 11.0),
            "target_from": (272.5, 0.0, 1.1),
            "target_to": (274.0, 4.0, 1.1),
            "lens": 48.0,
        },
        {
            "name": "river_and_wind",
            "start": start + shot_length,
            "end": start + 2 * shot_length - 1,
            "from": (-249.0, -151.0, 25.0),
            "to": (-255.0, -142.0, 21.0),
            "target_from": (-286.0, -72.0, 2.3),
            "target_to": (-289.0, -62.0, 2.6),
            "lens": 42.0,
        },
        {
            "name": "native_fountain",
            "start": start + 2 * shot_length,
            "end": start + 3 * shot_length - 1,
            "from": (-231.0499, -122.9002, 6.6147),
            "to": (-232.4, -119.8, 6.05),
            "target_from": (-240.0, -105.0, 1.6027),
            "target_to": (-240.0, -105.0, 1.95),
            "lens": 58.0,
        },
        {
            "name": "lake_and_wind",
            "start": start + 3 * shot_length,
            "end": end,
            "from": (-135.0, -125.0, 33.0),
            "to": (-151.0, -119.0, 29.0),
            "target_from": (-135.0, -70.0, 0.0),
            "target_to": (-133.0, -68.0, 1.0),
            "lens": 38.0,
        },
    ]
    for shot in shots:
        for frame, location, target in (
            (shot["start"], shot["from"], shot["target_from"]),
            (shot["end"], shot["to"], shot["target_to"]),
        ):
            camera.location = location
            camera.data.lens = shot["lens"]
            look_at(camera, Vector(target))
            keyframe(camera, "location", frame)
            keyframe(camera, "rotation_euler", frame)
            keyframe(camera.data, "lens", frame)
    finish_animation(camera, linear=False)
    finish_animation(camera.data, linear=True)
    return {"object": camera.name, "shots": shots}


def configure_daylight(scene: bpy.types.Scene) -> None:
    world = bpy.data.worlds.new("C2W_Full13_DynamicWorld")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "MULTIPLE_SCATTERING"
    except TypeError:
        sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42.0)
    sky.sun_rotation = math.radians(218.0)
    sky.air_density = 1.0
    if hasattr(sky, "dust_density"):
        sky.dust_density = 0.32
    background.inputs["Strength"].default_value = 0.38
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.world = world

    light_data = bpy.data.lights.new("C2W_Full13_DynamicSunData", "SUN")
    light_data.energy = 2.15
    light_data.angle = math.radians(1.2)
    light = bpy.data.objects.new("C2W_Full13_DynamicSun", light_data)
    light.rotation_euler = (
        math.radians(48.0),
        math.radians(-14.0),
        math.radians(218.0),
    )
    scene.collection.objects.link(light)
    light[TAG] = True


def configure_render(
    scene: bpy.types.Scene, output_dir: Path, start: int, end: int, fps: int
) -> None:
    engines = {
        item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items
    }
    eevee = next((name for name in engines if "EEVEE" in name), None)
    if eevee is None:
        raise RuntimeError(
            f"Eevee is unavailable; installed engines: {sorted(engines)}"
        )
    scene.render.engine = eevee
    scene.frame_start = start
    scene.frame_end = end
    scene.render.fps = fps
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(output_dir / "frames/frame_")
    scene.render.use_file_extension = True
    if hasattr(scene.render, "use_motion_blur"):
        # Four hard camera cuts share one timeline. Global motion blur samples
        # across those discontinuities and smears the first frame of each shot.
        # Keep cuts clean; wheel rotation and vehicle translation remain explicit.
        scene.render.use_motion_blur = False
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = 32
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.10


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "frames").mkdir(parents=True, exist_ok=True)
    output_blend = output_dir / "urban_v1_full_13_dynamic.blend"
    manifest_path = output_dir / "dynamic_manifest.json"
    if args.frame_end <= START_FRAME:
        raise ValueError("--frame-end must be greater than frame 1")
    if args.fps <= 0:
        raise ValueError("--fps must be positive")

    print(
        f"[full13-dynamic] Opening certified source pack: {args.source_pack}",
        flush=True,
    )
    bpy.ops.wm.open_mainfile(filepath=str(args.source_pack.resolve()))
    scene = bpy.context.scene
    render_set = prune_static_placements()
    tree_animator = TreeAnimator(START_FRAME, args.frame_end)
    report: dict[str, Any] = {
        "schema": "agent.full13.dynamic.v1",
        "created_utc": utc_now(),
        "status": "BUILDING",
        "source_static_master": str(STATIC_MASTER),
        "source_static_master_sha256": sha256(STATIC_MASTER),
        "source_render_pack": str(args.source_pack.resolve()),
        "source_render_pack_sha256": sha256(args.source_pack.resolve()),
        "output_blend": str(output_blend),
        "timeline": {
            "frame_start": START_FRAME,
            "frame_end": args.frame_end,
            "fps": args.fps,
        },
        "quality_policy": {
            "toy_or_placeholder_geometry_allowed": False,
            "geometry_policy": "exact authored full_13 and OpenX meshes; local animation wrappers only",
            "static_generation_modified": False,
            "source_blends_modified": False,
        },
        "resource_safe_render_set": render_set,
        "effects": {},
    }

    print("[full13-dynamic] Localizing exact vehicle hierarchy wrappers", flush=True)
    report["effects"]["traffic"] = dynamicize_traffic(
        tree_animator, START_FRAME, args.frame_end
    )

    print("[full13-dynamic] Building animated river and riparian trees", flush=True)
    river_wrapper_name = "full10:master:river5_corridor"
    river_source = append_collection(PARK_PACK, river_wrapper_name)
    river_root = create_placement(
        "park_river5_corridor",
        river_source,
        (-379.1245, -110.5505, 0.0),
        category="river_corridor",
        source_collection=river_wrapper_name,
    )
    report["effects"]["river"] = dynamicize_water_collection(
        river_root,
        river_source,
        "C2W_DynamicRiver5Corridor",
        tree_animator,
        START_FRAME,
        args.frame_end,
        directional=True,
    )

    print("[full13-dynamic] Building wind-enabled sculpture park", flush=True)
    park_wrapper_name = "full10:master:park_sculpture_nature"
    park_source = append_collection(PARK_PACK, park_wrapper_name)
    park_root = create_placement(
        "park_original_sculpture_nature",
        park_source,
        (-266.35, -75.376, 0.0),
        category="park_sculpture_nature",
        source_collection=park_wrapper_name,
    )
    park_dynamic, park_mapping = copy_collection_objects(
        park_source, "C2W_DynamicSculpturePark"
    )
    park_root.instance_collection = park_dynamic
    park_tree_count = tree_animator.replace_tree_instances(park_mapping)
    report["effects"]["park_wind"] = {
        "tree_instances": park_tree_count,
        "local_exact_object_wrappers": len(park_mapping),
    }

    print(
        "[full13-dynamic] Localizing the native 170-object fountain asset", flush=True
    )
    fountain_wrapper_name = "full10:master:fountain3_royal_quatrefoil_single"
    fountain_source = append_collection(PARK_PACK, fountain_wrapper_name)
    fountain_root = create_placement(
        "park_single_fountain",
        fountain_source,
        (-229.2, -105.0, 0.0),
        category="fountain",
        source_collection=fountain_wrapper_name,
    )
    report["effects"]["fountain"] = dynamicize_water_collection(
        fountain_root,
        fountain_source,
        "C2W_DynamicRoyalQuatrefoilFountain",
        tree_animator,
        START_FRAME,
        args.frame_end,
        directional=False,
        fountain=True,
    )

    print("[full13-dynamic] Dynamicizing exact lake water and its 26 trees", flush=True)
    lake_wrapper_name = "full10:master:artificial_lake3_complete_city_context"
    lake_source = append_collection(PARK_PACK, lake_wrapper_name)
    lake_root = create_placement(
        "education_artificial_lake_civic_enclosure",
        lake_source,
        (-135.0, -70.0, 0.0),
        category="artificial_lake",
        source_collection=lake_wrapper_name,
    )
    report["effects"]["lake"] = dynamicize_water_collection(
        lake_root,
        lake_source,
        "C2W_DynamicArtificialLake",
        tree_animator,
        START_FRAME,
        args.frame_end,
        directional=False,
    )
    report["effects"]["wind_summary"] = {
        "animated_tree_instances": sum(
            report["effects"][name].get("tree_instances", 0)
            for name in ("river", "park_wind", "lake")
        ),
        "animated_tree_master_variants": len(tree_animator.created),
        "tree_master_collections": tree_animator.created,
        "method": (
            "low-amplitude authored trunk sway plus independent merged-canopy "
            "rotation/scale flutter; exact high-detail meshes retained"
        ),
    }

    shot_length = (args.frame_end - START_FRAME + 1) // 4
    animate_render_visibility(
        scene_placement("full13_single_road_activity_module"),
        START_FRAME,
        args.frame_end,
        START_FRAME,
        START_FRAME + shot_length - 1,
    )
    for root in (river_root, park_root):
        animate_render_visibility(
            root,
            START_FRAME,
            args.frame_end,
            START_FRAME + shot_length,
            START_FRAME + 2 * shot_length - 1,
        )
    animate_render_visibility(
        fountain_root,
        START_FRAME,
        args.frame_end,
        START_FRAME + 2 * shot_length,
        START_FRAME + 3 * shot_length - 1,
    )
    animate_render_visibility(
        lake_root,
        START_FRAME,
        args.frame_end,
        START_FRAME + 3 * shot_length,
        args.frame_end,
    )

    configure_daylight(scene)
    report["camera"] = build_camera(scene, START_FRAME, args.frame_end)
    configure_render(scene, output_dir, START_FRAME, args.frame_end, args.fps)
    scene["c2w_dynamic_schema"] = report["schema"]
    scene["c2w_dynamic_source_revision"] = "urban_v1_full_13"
    scene["c2w_dynamic_source_master_sha256"] = report["source_static_master_sha256"]
    scene["c2w_dynamic_no_toy_geometry"] = True
    scene.frame_set(START_FRAME)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(output_blend))
    report["status"] = "PASS"
    report["output_blend_sha256"] = sha256(output_blend)
    manifest_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[full13-dynamic] PASS blend={output_blend}", flush=True)
    print(f"[full13-dynamic] manifest={manifest_path}", flush=True)


if __name__ == "__main__":
    main()

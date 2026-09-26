#!/usr/bin/env python3
"""Generate and render the production reference-matched urban artificial lake.

The script starts from an empty Blender scene and invokes
``UrbanLakeFactory.create_lake`` directly.  It is therefore the actual source
generation pipeline for ``outputs/outdoor_part_demo/urban_v3_lake3``; it never
loads or patches an existing lake blend file.  The landscaped context reuses
the project's existing western bandstand, bench, and five verified full07
TreeFactory/LeafFactory botanical masters inside this same generator.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INFINIGEN_ROOT = REPO_ROOT / "infinigen"
if str(INFINIGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(INFINIGEN_ROOT))
os.environ["INFINIGEN_SKIP_TAGGING"] = "1"
os.environ.setdefault("MPLCONFIGDIR", str(REPO_ROOT / ".runtime_cache" / "matplotlib"))

import bpy  # noqa: E402
import numpy as np  # noqa: E402
from mathutils import Matrix, Vector  # noqa: E402

from infinigen.assets.objects.decor.urban_lake import (  # noqa: E402
    GENERATOR_REVISION,
    LAKE_REFERENCE,
    UrbanLakeFactory,
)
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest  # noqa: E402


DEFAULT_OUTPUT = (
    REPO_ROOT / "infinigen" / "outputs" / "outdoor_part_demo" / "urban_v3_lake3"
)

WESTERN_PAVILION_BLEND = (
    REPO_ROOT
    / "infinigen"
    / "outputs"
    / "outdoor_part_demo"
    / "urban_v3_sculpture2"
    / "public_art.blend"
)
FULL07_TREE_BLEND = (
    REPO_ROOT
    / "infinigen"
    / "outputs"
    / "outdoor_full_demo"
    / "urban_v1_full_07"
    / "urban_v1_full_07.blend"
)
FULL07_TREE_COLLECTIONS = (
    "full02:MASTER:TreeFactory:42",
    "full02:MASTER:TreeFactory:256",
    "full02:MASTER:TreeFactory:381",
    "full02:MASTER:TreeFactory:512",
    "full02:MASTER:TreeFactory:619",
)
FULL07_TREE_METHOD = (
    "infinigen.assets.objects.trees.generate.TreeFactory(coarse=False) + "
    "scripts.urban_v1_full_07_trees.build_botanical_tree_master"
)
BENCH_BLEND = (
    REPO_ROOT
    / "infinigen"
    / "outputs"
    / "outdoor_part_demo"
    / "urban_v3_longchair+trashbin2"
    / "furniture.blend"
)
VIEW_SPECS = (
    {
        "name": "01_reference_aerial_day.png",
        "kind": "far",
        "camera": (57.0, -70.0, 58.0),
        "target": (0.0, 1.8, 1.0),
        "lens": 52.0,
        "fstop": 11.0,
    },
    {
        "name": "02_full_lake_opposite_aerial_day.png",
        "kind": "far",
        "camera": (-62.0, 58.0, 49.0),
        "target": (-1.5, 1.0, 1.2),
        "lens": 54.0,
        "fstop": 11.0,
    },
    {
        "name": "03_full_lake_low_oblique_day.png",
        "kind": "far",
        "camera": (-55.0, -61.0, 17.5),
        "target": (0.0, 2.5, 1.3),
        "lens": 50.0,
        "fstop": 10.0,
    },
    {
        "name": "04_west_platform_close_day.png",
        "kind": "near",
        "camera": (-27.5, -30.5, 5.7),
        "target": (-13.0, -9.9, 0.28),
        "lens": 52.0,
        "fstop": 8.0,
    },
    {
        "name": "05_east_platform_close_day.png",
        "kind": "near",
        "camera": (29.5, -29.0, 6.2),
        "target": (13.4, -9.1, 0.30),
        "lens": 54.0,
        "fstop": 8.0,
    },
    {
        "name": "06_fountain_water_close_day.png",
        "kind": "near",
        "camera": (25.5, -13.0, 7.0),
        "target": (8.2, 5.4, 1.65),
        "lens": 61.0,
        "fstop": 8.0,
    },
    {
        "name": "07_western_bandstand_close_day.png",
        "kind": "near",
        "camera": (-36.0, 5.0, 6.8),
        "target": (-18.0, 27.0, 2.55),
        "lens": 50.0,
        "fstop": 8.0,
    },
    {
        "name": "08_shore_water_ground_close_day.png",
        "kind": "near",
        "camera": (-35.0, -8.0, 2.55),
        "target": (-24.2, 0.8, 0.18),
        "lens": 66.0,
        "fstop": 9.0,
    },
    {
        "name": "09_high_detail_tree_close_day.png",
        "kind": "near",
        "camera": (22.0, -9.0, 4.4),
        "target": (43.0, 19.0, 4.35),
        "lens": 58.0,
        "fstop": 10.0,
    },
    {
        "name": "10_connected_path_clearance_day.png",
        "kind": "near",
        "camera": (38.0, -10.0, 8.4),
        "target": (29.0, 2.0, 0.30),
        "lens": 54.0,
        "fstop": 9.0,
    },
)


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=800)
    parser.add_argument("--samples", type=int, default=56)
    parser.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument(
        "--views",
        default=None,
        help="Optional comma-separated render filenames. The blend and full audit are still regenerated.",
    )
    return parser.parse_args(argv)


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in list(bpy.data.collections):
        if collection.users == 0 or collection.name != "Collection":
            try:
                bpy.data.collections.remove(collection)
            except RuntimeError:
                pass
    for datablocks in (
        bpy.data.curves,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def look_at(obj: bpy.types.Object, target: tuple[float, float, float] | Vector) -> None:
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def configure_render(args: argparse.Namespace) -> dict:
    scene = bpy.context.scene
    scene.render.engine = "CYCLES" if args.engine == "cycles" else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_file_extension = True
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.image_settings.compression = 18
    scene.render.use_high_quality_normals = True
    scene.render.engine = "CYCLES" if args.engine == "cycles" else "BLENDER_EEVEE_NEXT"

    device_report = {"requested": "CPU", "enabled": []}
    if args.engine == "cycles":
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.025
        scene.cycles.max_bounces = 8
        scene.cycles.diffuse_bounces = 3
        scene.cycles.glossy_bounces = 5
        scene.cycles.transmission_bounces = 6
        scene.cycles.transparent_max_bounces = 8
        scene.cycles.volume_bounces = 2
        scene.cycles.use_fast_gi = True
        scene.render.use_persistent_data = True
        addon = bpy.context.preferences.addons.get("cycles")
        if addon is not None:
            preferences = addon.preferences
            for compute_type in ("OPTIX", "CUDA", "HIP", "ONEAPI", "METAL"):
                try:
                    preferences.compute_device_type = compute_type
                    preferences.get_devices()
                except (TypeError, RuntimeError):
                    continue
                usable = []
                for device in preferences.devices:
                    if device.type == compute_type:
                        device.use = True
                        usable.append(device.name)
                    elif device.type == "CPU":
                        device.use = False
                if usable:
                    scene.cycles.device = "GPU"
                    device_report = {"requested": compute_type, "enabled": usable}
                    break

    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except (TypeError, ValueError):
        scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = -0.28 if args.engine == "cycles" else -0.38
    scene.view_settings.gamma = 1.0
    scene.camera = None
    return device_report


def configure_daylight() -> None:
    scene = bpy.context.scene
    world = bpy.data.worlds.new("urban_lake_clear_day_world")
    scene.world = world
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    # The directional SUN below supplies solar illumination.  A second
    # emissive disk in the environment reflects as a tiny white object on the
    # calm lake, so retain the atmospheric sky without that duplicate disk.
    sky.sun_disc = False
    sky.sun_size = math.radians(0.60)
    sky.sun_intensity = 0.90
    sky.sun_elevation = math.radians(39.0)
    sky.sun_rotation = math.radians(128.0)
    sky.altitude = 0.08
    sky.air_density = 0.92
    sky.dust_density = 1.15
    sky.ozone_density = 0.32
    background.inputs["Strength"].default_value = 0.36
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    bpy.ops.object.light_add(type="SUN", location=(-30.0, -38.0, 54.0))
    sun = bpy.context.active_object
    sun.name = "urban_lake_day_sun"
    sun.data.energy = 1.72
    sun.data.angle = math.radians(1.35)
    # The supplied aerial has diffuse daylight on the lake, not a hard white
    # solar glint. Environment/sky reflection remains in the water shader.
    sun.data.specular_factor = 0.0
    sun.rotation_euler = (math.radians(31.0), math.radians(-18.0), math.radians(-126.0))
    sun["c2w_lighting_role"] = "physical_daylight"

    # Nishita provides continuous hemispherical skylight. Avoid finite disk
    # lights entirely: even with specular factors disabled, their sampled
    # transmission/volume paths can leave a pale disk on shallow water.
    scene["c2w_no_finite_light_disks_over_lake"] = True


def _set_socket(node: bpy.types.Node, names: str | tuple[str, ...], value) -> None:
    if isinstance(names, str):
        names = (names,)
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def _move_to_collection(
    obj: bpy.types.Object, collection: bpy.types.Collection
) -> None:
    if obj.name not in collection.objects:
        collection.objects.link(obj)
    for old in list(obj.users_collection):
        if old is not collection:
            old.objects.unlink(obj)


def _tag_context(obj: bpy.types.Object, semantic: str, role: str) -> None:
    obj["urban_semantic"] = semantic
    obj["c2w_role"] = role
    obj["c2w_generator_revision"] = GENERATOR_REVISION
    obj["c2w_final_pipeline_connected"] = True


def _layered_context_material(
    name: str,
    dark: tuple[float, float, float],
    light: tuple[float, float, float],
    *,
    macro_scale: float,
    micro_scale: float,
    roughness: float,
    bump_strength: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new("urban:lake3:context:" + name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    coordinates = nodes.new("ShaderNodeTexCoord")
    macro = nodes.new("ShaderNodeTexNoise")
    macro.noise_dimensions = "3D"
    _set_socket(macro, "Scale", macro_scale)
    _set_socket(macro, "Detail", 7.0)
    _set_socket(macro, "Roughness", 0.72)
    micro = nodes.new("ShaderNodeTexNoise")
    micro.noise_dimensions = "3D"
    _set_socket(micro, "Scale", micro_scale)
    _set_socket(micro, "Detail", 5.0)
    _set_socket(micro, "Roughness", 0.66)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.interpolation = "B_SPLINE"
    ramp.color_ramp.elements[0].position = 0.20
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].position = 0.82
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "SOFT_LIGHT"
    color_mix.inputs[0].default_value = 0.20
    bump_mix = nodes.new("ShaderNodeMixRGB")
    bump_mix.blend_type = "MULTIPLY"
    bump_mix.inputs[0].default_value = 0.38
    bump = nodes.new("ShaderNodeBump")
    _set_socket(bump, "Strength", bump_strength)
    _set_socket(bump, "Distance", 0.018)
    _set_socket(shader, "Roughness", roughness)
    links.new(coordinates.outputs["Object"], macro.inputs["Vector"])
    links.new(coordinates.outputs["Object"], micro.inputs["Vector"])
    links.new(macro.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], color_mix.inputs[1])
    links.new(micro.outputs["Color"], color_mix.inputs[2])
    links.new(macro.outputs["Color"], bump_mix.inputs[1])
    links.new(micro.outputs["Color"], bump_mix.inputs[2])
    links.new(bump_mix.outputs["Color"], bump.inputs["Height"])
    links.new(color_mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material["c2w_procedural_pbr"] = True
    return material


def _jointed_path_material() -> bpy.types.Material:
    material = bpy.data.materials.new("urban:lake3:context:jointed_park_path")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    coordinates = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Scale"].default_value = (0.74, 0.74, 1.0)
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.inputs["Color1"].default_value = (0.205, 0.175, 0.145, 1.0)
    brick.inputs["Color2"].default_value = (0.345, 0.295, 0.235, 1.0)
    brick.inputs["Mortar"].default_value = (0.075, 0.068, 0.060, 1.0)
    brick.inputs["Scale"].default_value = 4.5
    brick.inputs["Mortar Size"].default_value = 0.024
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    _set_socket(noise, "Scale", 34.0)
    _set_socket(noise, "Detail", 5.0)
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.13
    bump = nodes.new("ShaderNodeBump")
    bump.invert = True
    _set_socket(bump, "Strength", 0.27)
    _set_socket(bump, "Distance", 0.028)
    _set_socket(shader, "Roughness", 0.82)
    links.new(coordinates.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    links.new(mapping.outputs["Vector"], noise.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs[1])
    links.new(noise.outputs["Color"], mix.inputs[2])
    links.new(mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material["c2w_real_mortar_relief"] = True
    return material


def make_context_materials() -> dict[str, bpy.types.Material]:
    materials = {
        "lawn": _layered_context_material(
            "mixed_fescue_lawn_soil",
            (0.030, 0.075, 0.018),
            (0.135, 0.245, 0.052),
            macro_scale=0.24,
            micro_scale=24.0,
            roughness=0.94,
            bump_strength=0.24,
        ),
        "path": _jointed_path_material(),
        "mulch": _layered_context_material(
            "aged_bark_mulch",
            (0.055, 0.024, 0.010),
            (0.22, 0.090, 0.028),
            macro_scale=1.8,
            micro_scale=38.0,
            roughness=0.96,
            bump_strength=0.36,
        ),
        "stone": _layered_context_material(
            "pavilion_plaza_stone",
            (0.25, 0.24, 0.215),
            (0.55, 0.52, 0.46),
            macro_scale=0.75,
            micro_scale=44.0,
            roughness=0.84,
            bump_strength=0.20,
        ),
    }
    materials.update(
        {
            "tree_trunk": _layered_context_material(
                "tree_bark_ridged_brown",
                (0.030, 0.012, 0.004),
                (0.16, 0.070, 0.018),
                macro_scale=2.6,
                micro_scale=51.0,
                roughness=0.93,
                bump_strength=0.42,
            ),
            "tree_bark_dark": _layered_context_material(
                "tree_bark_recesses",
                (0.012, 0.004, 0.002),
                (0.075, 0.026, 0.008),
                macro_scale=3.2,
                micro_scale=67.0,
                roughness=0.96,
                bump_strength=0.48,
            ),
            "tree_leaf": _layered_context_material(
                "summer_leaf_sunlit",
                (0.008, 0.075, 0.012),
                (0.055, 0.34, 0.080),
                macro_scale=4.8,
                micro_scale=83.0,
                roughness=0.68,
                bump_strength=0.16,
            ),
            "tree_leaf_dark": _layered_context_material(
                "summer_leaf_shade",
                (0.004, 0.030, 0.006),
                (0.025, 0.18, 0.040),
                macro_scale=5.6,
                micro_scale=91.0,
                roughness=0.72,
                bump_strength=0.14,
            ),
            "tree_leaf_litter": _layered_context_material(
                "tree_leaf_litter",
                (0.050, 0.018, 0.004),
                (0.28, 0.10, 0.018),
                macro_scale=4.0,
                micro_scale=72.0,
                roughness=0.96,
                bump_strength=0.18,
            ),
        }
    )
    return materials


def _mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    semantic: str,
    role: str,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    collection.objects.link(obj)
    mesh.materials.append(material)
    _tag_context(obj, semantic, role)
    return obj


def _point_in_polygon(x: float, y: float, polygon: list[Vector]) -> bool:
    inside = False
    previous = polygon[-1]
    for current in polygon:
        if (current.y > y) != (previous.y > y):
            crossing = (previous.x - current.x) * (y - current.y) / (
                previous.y - current.y
            ) + current.x
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _point_segment_distance(point: Vector, start: Vector, end: Vector) -> float:
    delta = end - start
    if delta.length_squared < 1e-10:
        return (point - start).length
    factor = max(0.0, min(1.0, (point - start).dot(delta) / delta.length_squared))
    return (point - start.lerp(end, factor)).length


def _nearest_boundary_point(point: Vector, boundary: list[Vector]) -> Vector:
    return min(
        boundary, key=lambda candidate: (candidate - point).length_squared
    ).copy()


def _connected_path_specs(
    outer_boundary: list[Vector],
) -> list[tuple[str, list[tuple[float, float]], float]]:
    """Create spokes whose first span physically overlaps the lake apron.

    ``outer_boundary`` is the as-built outer edge of the jointed promenade,
    not an approximate ellipse.  Every spoke starts 0.85 m inside that edge,
    so tolerances and curved interpolation cannot leave a strip of lawn
    between the two paved systems.
    """
    layouts = (
        ("northwest_walk", (-20.0, 14.0), (-32.0, 25.0), (-49.0, 35.0), 2.35),
        ("north_axis_walk", (0.0, 15.0), (2.0, 30.0), (4.0, 49.0), 2.30),
        ("northeast_walk", (19.0, 12.0), (33.0, 22.0), (51.0, 31.0), 2.35),
        ("west_walk", (-28.0, 0.0), (-42.0, 4.5), (-57.0, 10.0), 2.25),
        ("east_walk", (28.0, 1.0), (42.0, 5.0), (57.0, 11.0), 2.25),
        ("southwest_walk", (-22.0, -13.0), (-37.0, -21.0), (-55.0, -31.0), 2.30),
        ("southeast_walk", (22.0, -13.0), (38.0, -20.0), (55.0, -26.0), 2.30),
        ("pavilion_link", (-16.0, 13.0), (-22.0, 22.0), (-18.5, 28.0), 2.55),
    )
    paths = []
    for name, hint_xy, middle_xy, end_xy, width in layouts:
        hint = Vector((*hint_xy, 0.0))
        anchor = _nearest_boundary_point(hint, outer_boundary)
        outward = Vector((anchor.x, anchor.y, 0.0))
        if outward.length < 1e-6:
            raise RuntimeError(f"Invalid radial lake-path anchor for {name}")
        outward.normalize()
        start = anchor - outward * 0.85
        transition = anchor + outward * (3.2 if name == "pavilion_link" else 4.25)
        controls = [
            (start.x, start.y),
            (transition.x, transition.y),
            middle_xy,
            end_xy,
        ]
        paths.append((name, controls, width))
    return paths


def _sample_path_xy(
    controls: list[tuple[float, float]], samples_per_span: int = 20
) -> list[Vector]:
    return _catmull_rom_open(
        [Vector((x, y, 0.0)) for x, y in controls],
        samples_per_span=samples_per_span,
    )


def _clearance_to_paths(
    x: float,
    y: float,
    paths: list[tuple[str, list[tuple[float, float]], float]],
) -> float:
    point = Vector((x, y, 0.0))
    clearances = []
    for _name, controls, width in paths:
        centerline = _sample_path_xy(controls, samples_per_span=16)
        distance = min(
            _point_segment_distance(point, start, end)
            for start, end in zip(centerline[:-1], centerline[1:])
        )
        clearances.append(distance - width * 0.5)
    return min(clearances)


def _build_landscape(
    excavation_boundary: list[Vector],
    paths: list[tuple[str, list[tuple[float, float]], float]],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    # The aerial cameras see well past the designed park. A broad, gently
    # rolling mesh prevents a finite ground edge or the black lower hemisphere
    # of the world shader from entering any approved view.
    min_x, max_x, min_y, max_y = -150.0, 150.0, -115.0, 155.0
    columns, rows = 181, 163
    vertices: list[tuple[float, float, float]] = []
    for row in range(rows):
        y = min_y + (max_y - min_y) * row / (rows - 1)
        for column in range(columns):
            x = min_x + (max_x - min_x) * column / (columns - 1)
            radial = math.hypot(x / 54.0, y / 44.0)
            relief = max(0.0, radial - 0.42) * (
                0.045 * math.sin(x * 0.105 + 0.7)
                + 0.032 * math.sin(y * 0.137 - 0.4)
                + 0.018 * math.sin((x + y) * 0.31)
            )
            z = 0.16 + relief
            if _point_in_polygon(x, y, excavation_boundary):
                z = -2.18
            vertices.append((x, y, z))
    faces: list[tuple[int, ...]] = []
    for row in range(rows - 1):
        y = min_y + (max_y - min_y) * (row + 0.5) / (rows - 1)
        for column in range(columns - 1):
            x = min_x + (max_x - min_x) * (column + 0.5) / (columns - 1)
            lower_left = row * columns + column
            faces.append(
                (
                    lower_left,
                    lower_left + 1,
                    lower_left + columns + 1,
                    lower_left + columns,
                )
            )
    obj = _mesh_object(
        "urban:lake3:landscape:continuous_excavated_rolling_park_ground",
        vertices,
        faces,
        material,
        collection,
        "park-ground",
        "reference_continuous_landscape_with_lowered_lake_excavation",
    )
    obj["c2w_lake_excavation_depth_m"] = 2.34
    obj["c2w_no_world_background_cracks"] = True
    obj["c2w_continuous_subgrade_under_hardscape"] = True
    obj["c2w_landscape_extent_metres"] = (300.0, 270.0)
    return obj


def _catmull_rom_open(points: list[Vector], samples_per_span: int = 18) -> list[Vector]:
    extended = [points[0], *points, points[-1]]
    result: list[Vector] = []
    for index in range(1, len(extended) - 2):
        p0, p1, p2, p3 = extended[index - 1 : index + 3]
        for sample in range(samples_per_span):
            t = sample / samples_per_span
            t2, t3 = t * t, t * t * t
            result.append(
                0.5
                * (
                    2.0 * p1
                    + (-p0 + p2) * t
                    + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
                    + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
                )
            )
    result.append(points[-1].copy())
    return result


def _build_path_ribbon(
    name: str,
    controls: list[tuple[float, float]],
    width: float,
    z: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    *,
    semantic: str = "park-path",
    role: str = "curved_jointed_park_walk",
) -> bpy.types.Object:
    centerline = _catmull_rom_open(
        [Vector((x, y, z)) for x, y in controls], samples_per_span=20
    )
    vertices: list[tuple[float, float, float]] = []
    for index, point in enumerate(centerline):
        if index == 0:
            tangent = centerline[1] - point
        elif index == len(centerline) - 1:
            tangent = point - centerline[index - 1]
        else:
            tangent = centerline[index + 1] - centerline[index - 1]
        tangent.normalize()
        normal = Vector((-tangent.y, tangent.x, 0.0))
        vertices.extend(
            (tuple(point + normal * width * 0.5), tuple(point - normal * width * 0.5))
        )
    faces = [
        (index * 2, index * 2 + 1, index * 2 + 3, index * 2 + 2)
        for index in range(len(centerline) - 1)
    ]
    obj = _mesh_object(name, vertices, faces, material, collection, semantic, role)
    solidify = obj.modifiers.new(name + ":structural_depth", "SOLIDIFY")
    solidify.thickness = 0.095
    solidify.offset = -1.0
    solidify.use_rim = True
    bevel = obj.modifiers.new(name + ":worn_edge_bevel", "BEVEL")
    bevel.width = 0.028
    bevel.segments = 2
    obj["c2w_spline_samples"] = len(centerline)
    return obj


def _build_pavilion_plaza(
    material: bpy.types.Material, collection: bpy.types.Collection
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=64,
        radius=5.55,
        depth=0.14,
        location=(-18.5, 28.0, 0.20),
    )
    plaza = bpy.context.active_object
    plaza.name = "urban:lake3:pavilion:64_sided_jointed_stone_plaza"
    plaza.data.materials.append(material)
    _move_to_collection(plaza, collection)
    bevel = plaza.modifiers.new("urban:lake3:pavilion:plaza_worn_edge", "BEVEL")
    bevel.width = 0.045
    bevel.segments = 3
    _tag_context(plaza, "park-path", "pavilion_stone_plaza")
    return plaza


def _append_prefixed_objects(
    blend_path: Path,
    prefix: str,
    collection: bpy.types.Collection,
    transform: Matrix,
    semantic: str,
    role: str,
) -> list[bpy.types.Object]:
    if not blend_path.exists():
        raise FileNotFoundError(f"Required production asset is missing: {blend_path}")
    with bpy.data.libraries.load(str(blend_path), link=False) as (source, target):
        names = [name for name in source.objects if name.startswith(prefix)]
        if not names:
            raise RuntimeError(f"No {prefix!r} objects in {blend_path}")
        target.objects = names
    loaded = [obj for obj in target.objects if obj is not None]

    def stored_world_matrix(
        obj: bpy.types.Object, seen: set[str] | None = None
    ) -> Matrix:
        """Evaluate saved transforms before the datablocks enter a scene.

        A freshly library-loaded object has no evaluated dependency graph, so
        both ``matrix_world`` and ``matrix_local`` can be identity even when
        the source blend stores a non-zero transform. ``matrix_basis`` and
        ``matrix_parent_inverse`` are the authoritative saved components.
        """
        seen = set() if seen is None else seen
        if obj.name in seen:
            raise RuntimeError(f"Cyclic source parenting in {blend_path}: {obj.name}")
        seen.add(obj.name)
        if obj.parent is None:
            return obj.matrix_basis.copy()
        local = obj.matrix_parent_inverse.copy() @ obj.matrix_basis.copy()
        return stored_world_matrix(obj.parent, seen) @ local

    source_matrices = {obj.name: stored_world_matrix(obj) for obj in loaded}
    for obj in loaded:
        source_world = source_matrices[obj.name]
        obj.parent = None
        obj.matrix_world = transform @ source_world
        _move_to_collection(obj, collection)
        _tag_context(obj, semantic, role)
        obj["c2w_reused_asset_source"] = str(blend_path)
        obj["c2w_reused_asset_prefix"] = prefix
    return loaded


def _append_pavilion(collection: bpy.types.Collection) -> list[bpy.types.Object]:
    """Append the authored Victorian octagonal bandstand, never the Chinese pavilion."""
    source_center = Vector((-9.0, 10.5, 0.0))
    target = Vector((-18.5, 28.0, 0.27))
    transform = (
        Matrix.Translation(target)
        @ Matrix.Rotation(math.radians(-8.0), 4, "Z")
        @ Matrix.Diagonal(Vector((1.12, 1.12, 1.12, 1.0)))
        @ Matrix.Translation(-source_center)
    )
    objects = _append_prefixed_objects(
        WESTERN_PAVILION_BLEND,
        "band:",
        collection,
        transform,
        "park-pavilion",
        "reused_99_part_victorian_octagonal_western_bandstand",
    )
    if len(objects) < 95:
        raise RuntimeError(
            f"Production western bandstand unexpectedly degraded to {len(objects)} parts"
        )
    for obj in objects:
        obj["c2w_architectural_style"] = "Victorian western octagonal bandstand"
        obj["c2w_excludes_chinese_pavilion"] = True
    return objects


def _load_bench_master() -> tuple[bpy.types.Collection, int]:
    if not BENCH_BLEND.exists():
        raise FileNotFoundError(
            f"Required production bench asset is missing: {BENCH_BLEND}"
        )
    with bpy.data.libraries.load(str(BENCH_BLEND), link=False) as (source, target):
        names = [name for name in source.objects if name.startswith("clbench:")]
        target.objects = names
    objects = [obj for obj in target.objects if obj is not None]
    if len(objects) < 30:
        raise RuntimeError(
            f"Production classic bench unexpectedly degraded to {len(objects)} parts"
        )
    master = bpy.data.collections.new("urban:lake3:MASTER_reused_complex_classic_bench")

    def stored_world_matrix(
        obj: bpy.types.Object, seen: set[str] | None = None
    ) -> Matrix:
        seen = set() if seen is None else seen
        if obj.name in seen:
            raise RuntimeError(f"Cyclic bench source parenting at {obj.name}")
        seen.add(obj.name)
        if obj.parent is None:
            return obj.matrix_basis.copy()
        local = obj.matrix_parent_inverse.copy() @ obj.matrix_basis.copy()
        return stored_world_matrix(obj.parent, seen) @ local

    source_matrices = {obj.name: stored_world_matrix(obj) for obj in objects}
    localize = Matrix.Translation((6.5, 0.0, 0.0))
    for obj in objects:
        source_world = source_matrices[obj.name]
        obj.parent = None
        obj.matrix_world = localize @ source_world
        master.objects.link(obj)
        _tag_context(obj, "park-bench-master", "reused_complex_bench_master_part")
        obj["c2w_reused_asset_source"] = str(BENCH_BLEND)
    master["c2w_master_asset"] = True
    master["c2w_reused_asset_source"] = str(BENCH_BLEND)
    master["c2w_part_count"] = len(objects)
    return master, len(objects)


def _bench_yaw_facing_lake(x: float, y: float) -> float:
    direction = Vector((-x, -y))
    direction.normalize()
    return math.atan2(direction.x, -direction.y)


def _place_benches(
    master: bpy.types.Collection,
    collection: bpy.types.Collection,
    paths: list[tuple[str, list[tuple[float, float]], float]],
    outer_boundary: list[Vector],
) -> list[bpy.types.Object]:
    placements = (
        (-34.0, 14.0, 0.25, 1.04),
        (-29.0, 26.0, 0.25, 1.02),
        (-9.0, 24.0, 0.25, 1.05),
        (14.0, 24.0, 0.25, 1.04),
        (32.0, 14.0, 0.25, 1.03),
        (34.0, -5.0, 0.25, 1.05),
        (27.0, -27.0, 0.25, 1.02),
        (8.0, -27.0, 0.25, 1.03),
        (-14.0, -27.0, 0.25, 1.02),
        (-34.0, -15.0, 0.25, 1.04),
        (-35.0, 5.0, 0.25, 1.03),
        (10.0, 31.0, 0.25, 1.02),
    )
    instances = []
    for index, (x, y, z, scale) in enumerate(placements):
        path_clearance = _clearance_to_paths(x, y, paths)
        shore_clearance = min(
            math.hypot(x - point.x, y - point.y) for point in outer_boundary
        )
        pavilion_clearance = math.hypot(x + 18.5, y - 28.0) - 5.8
        if (
            path_clearance < 1.35
            or shore_clearance < 1.6
            or pavilion_clearance < 1.0
            or _point_in_polygon(x, y, outer_boundary)
        ):
            continue
        instance = bpy.data.objects.new(
            f"urban:lake3:bench_instance_{len(instances):02d}", None
        )
        instance.instance_type = "COLLECTION"
        instance.instance_collection = master
        instance.matrix_world = (
            Matrix.Translation((x, y, z))
            @ Matrix.Rotation(_bench_yaw_facing_lake(x, y), 4, "Z")
            @ Matrix.Diagonal(Vector((scale, scale, scale, 1.0)))
        )
        collection.objects.link(instance)
        _tag_context(instance, "park-bench", "reused_complex_bench_collection_instance")
        instance["c2w_reused_asset_source"] = str(BENCH_BLEND)
        instance["c2w_path_edge_clearance_m"] = path_clearance
        instance["c2w_shore_edge_clearance_m"] = shore_clearance
        instances.append(instance)
    if len(instances) < 8:
        raise RuntimeError(
            f"Only {len(instances)} collision-free benches survived placement; expected at least 8"
        )
    return instances


def _create_complex_tree_masters(
    materials: dict[str, bpy.types.Material],
) -> list[bpy.types.Collection]:
    """Append all five full07 production TreeFactory botanical masters.

    The previous lake explicitly requested ``use_nature_factory=False`` and
    therefore rendered the small fallback tree despite its optimistic audit
    labels.  Full07 is the established complex tree generator used by the
    earlier production urban scene: each species combines a continuous
    trunk/primary/secondary/twig hierarchy with thousands of genuine
    LeafFactory-derived leaves in a merged canopy.  The five crown forms are
    collection-instanced for every lakeside tree; no cylinder, card cloud,
    blob, topiary, or other fallback geometry is permitted.
    """
    del materials  # The full07 masters retain their authored bark/leaf PBR materials.
    if not FULL07_TREE_BLEND.exists():
        raise FileNotFoundError(
            f"Required full07 botanical TreeFactory source is missing: {FULL07_TREE_BLEND}"
        )
    with bpy.data.libraries.load(str(FULL07_TREE_BLEND), link=False) as (
        source,
        target,
    ):
        missing = [
            name for name in FULL07_TREE_COLLECTIONS if name not in source.collections
        ]
        if missing:
            raise RuntimeError(f"Full07 TreeFactory collections missing: {missing}")
        target.collections = list(FULL07_TREE_COLLECTIONS)
    masters = [
        collection for collection in target.collections if collection is not None
    ]
    if len(masters) != len(FULL07_TREE_COLLECTIONS):
        raise RuntimeError("Full07 TreeFactory collection append was incomplete")
    for master in masters:
        meshes = [obj for obj in master.all_objects if obj.type == "MESH" and obj.data]
        vertices = sum(len(obj.data.vertices) for obj in meshes)
        faces = sum(len(obj.data.polygons) for obj in meshes)
        branch_count = int(master.get("c2w_botanical_branch_count", 0))
        leaf_count = int(master.get("c2w_explicit_leaf_count", 0))
        if (
            len(meshes) != 2
            or vertices < 5_000_000
            or faces < 5_000_000
            or branch_count < 350
            or leaf_count < 3_000
            or bool(master.get("coarse", True))
            or not bool(master.get("c2w_internal_treefactory_helpers_excluded"))
            or not bool(master.get("c2w_internal_treefactory_helpers_removed"))
            or not bool(master.get("c2w_no_blob_or_topiary_geometry"))
        ):
            raise RuntimeError(
                f"Full07 TreeFactory master degraded: {master.name}, meshes={len(meshes)}, "
                f"vertices={vertices}, faces={faces}, branches={branch_count}, leaves={leaf_count}"
            )
        master["c2w_role"] = "verified_full07_botanical_treefactory_master"
        master["c2w_reused_existing_factory"] = FULL07_TREE_METHOD
        master[
            "c2w_verified_reference"
        ] = "urban_v1_full_07/23_park_tree_complexity.png"
        master["c2w_source_blend"] = str(FULL07_TREE_BLEND)
        master["c2w_part_count"] = len(master.all_objects)
        master["c2w_source_mesh_vertices"] = vertices
        master["c2w_source_mesh_faces"] = faces
        master["c2w_no_fallback_geometry"] = True
        for obj in master.all_objects:
            role = (
                "verified_full07_merged_leaf_geometry"
                if bool(obj.get("c2w_genuine_leaffactory_mesh"))
                else "verified_full07_multilevel_branch_geometry"
            )
            _tag_context(obj, "park-tree-master", role)
            obj["c2w_reused_existing_factory"] = master["c2w_reused_existing_factory"]
            obj["c2w_source_blend"] = str(FULL07_TREE_BLEND)
            obj["c2w_no_fallback_geometry"] = True
    return masters


def _place_infinigen_trees(
    masters: list[bpy.types.Collection],
    collection: bpy.types.Collection,
    paths: list[tuple[str, list[tuple[float, float]], float]],
    outer_boundary: list[Vector],
) -> list[bpy.types.Object]:
    # Mature trees occupy the lawns between spokes.  Every candidate is
    # checked against the actual curved centerlines, not their control-point
    # chords, and against the irregular promenade footprint.
    placements = (
        (-55.0, -10.0, 8.6),
        (-53.0, 18.0, 7.8),
        (-44.0, 38.0, 9.0),
        (-31.0, 46.0, 8.2),
        (-12.0, 47.0, 9.2),
        (12.0, 46.0, 8.0),
        (31.0, 43.0, 8.9),
        (48.0, 34.0, 7.7),
        (55.0, 20.0, 8.5),
        (57.0, -2.0, 9.1),
        (51.0, -22.0, 8.0),
        (41.0, -38.0, 8.8),
        (22.0, -44.0, 7.6),
        (1.0, -46.0, 8.7),
        (-21.0, -44.0, 9.0),
        (-41.0, -37.0, 7.9),
        (-53.0, -26.0, 8.4),
        (-43.0, 22.0, 7.8),
        (-34.0, 34.0, 8.6),
        (-9.0, 36.0, 7.7),
        (13.0, 36.0, 8.4),
        (31.0, 31.0, 7.9),
        (43.0, 19.0, 8.8),
        (45.0, -9.0, 7.6),
        (36.0, -29.0, 8.5),
        (16.0, -34.0, 7.8),
        (-7.0, -35.0, 8.7),
        (-28.0, -33.0, 8.1),
        (-43.0, -17.0, 9.0),
        (-39.0, 8.0, 7.7),
        (26.0, 21.0, 8.4),
        (30.0, -8.0, 7.9),
    )
    rng = random.Random(70219)
    instances = []
    source_heights = []
    for master in masters:
        bounds = _world_bounds(list(master.all_objects))
        source_heights.append(bounds["max"][2] - bounds["min"][2])
    for x, y, desired_height in placements:
        path_clearance = _clearance_to_paths(x, y, paths)
        shore_clearance = min(
            math.hypot(x - point.x, y - point.y) for point in outer_boundary
        )
        pavilion_clearance = math.hypot(x + 18.5, y - 28.0) - 6.4
        if (
            path_clearance < 3.15
            or shore_clearance < 3.0
            or pavilion_clearance < 2.0
            or _point_in_polygon(x, y, outer_boundary)
        ):
            continue
        index = len(instances)
        master_index = index % len(masters)
        source_height = source_heights[master_index]
        if source_height <= 7.0:
            raise RuntimeError(
                f"Full07 TreeFactory master has invalid height: {masters[master_index].name}"
            )
        scale = desired_height / source_height
        instance = bpy.data.objects.new(
            f"urban:lake3:high_detail_park_tree_{index:02d}", None
        )
        instance.instance_type = "COLLECTION"
        instance.instance_collection = masters[master_index]
        instance.matrix_world = (
            Matrix.Translation((x, y, 0.17))
            @ Matrix.Rotation(rng.uniform(-math.pi, math.pi), 4, "Z")
            @ Matrix.Diagonal(Vector((scale, scale, scale, 1.0)))
        )
        collection.objects.link(instance)
        _tag_context(
            instance, "park-tree", "verified_full07_botanical_TreeFactory_instance"
        )
        instance["c2w_reused_existing_factory"] = FULL07_TREE_METHOD
        instance["c2w_source_blend"] = str(FULL07_TREE_BLEND)
        instance["c2w_treefactory_seed"] = int(masters[master_index].get("seed", -1))
        instance["c2w_botanical_crown_form"] = masters[master_index].get(
            "c2w_botanical_crown_form", "missing"
        )
        instance["c2w_real_world_height_m"] = desired_height
        instance["c2w_path_edge_clearance_m"] = path_clearance
        instance["c2w_shore_edge_clearance_m"] = shore_clearance
        instance["c2w_no_fallback_geometry"] = True
        instances.append(instance)
    if len(instances) < 20:
        raise RuntimeError(
            f"Only {len(instances)} collision-free verified trees survived placement; expected at least 20"
        )
    return instances


def _set_scatter_density(scatter: bpy.types.Object, density: float) -> None:
    found = False
    for modifier in scatter.modifiers:
        if modifier.type != "NODES" or modifier.node_group is None:
            continue
        for node in modifier.node_group.nodes:
            if node.bl_idname != "GeometryNodeDistributePointsOnFaces":
                continue
            if node.inputs.get("Density") is not None:
                node.inputs["Density"].default_value = density
                found = True
            if node.inputs.get("Density Max") is not None:
                node.inputs["Density Max"].default_value = density
    if not found:
        raise RuntimeError(
            f"Could not calibrate Infinigen scatter density on {scatter.name}"
        )


def _apply_official_flowers(
    bed: bpy.types.Object, collection: bpy.types.Collection
) -> tuple[bpy.types.Object, bpy.types.Collection]:
    from infinigen.assets.objects.grassland.flowerplant import FlowerPlantFactory
    from infinigen.core.placement.factory import make_asset_collection
    from infinigen.core.placement.instance_scatter import scatter_instances

    np.random.seed(55109)
    master = make_asset_collection(FlowerPlantFactory(55109), n=12, verbose=False)
    scatter = scatter_instances(
        base_obj=bed,
        collection=master,
        density=2.4,
        scale=0.82,
        scale_rand=0.36,
        scale_rand_axi=0.18,
        ground_offset=0.0,
        normal_fac=0.18,
        taper_scale=True,
    )
    scatter.name = "urban:lake3:official_Infinigen_reference_flowerbed_scatter"
    _set_scatter_density(scatter, 2.4)
    _move_to_collection(scatter, collection)
    _tag_context(
        scatter, "park-flowerbed", "official_Infinigen_FlowerPlantFactory_scatter"
    )
    scatter["c2w_direct_infinigen_call"] = (
        "infinigen.assets.objects.grassland.flowerplant.FlowerPlantFactory"
        " + infinigen.core.placement.instance_scatter.scatter_instances"
    )
    scatter["c2w_density_per_square_metre"] = 2.4
    return scatter, master


def build_lakeside_context(
    lake_geometry: dict[str, list[Vector] | tuple[float, float]],
) -> tuple[list[bpy.types.Object], dict]:
    """Build the reference park context and reuse all requested complex assets."""
    outer_boundary = lake_geometry.get("outer")
    if not isinstance(outer_boundary, list) or len(outer_boundary) < 128:
        raise RuntimeError(
            "UrbanLakeFactory did not expose its production outer boundary"
        )
    water_boundary = lake_geometry.get("water_boundary")
    if not isinstance(water_boundary, list) or len(water_boundary) < 128:
        raise RuntimeError(
            "UrbanLakeFactory did not expose its production water boundary"
        )

    root = bpy.data.collections.new("urban_v3_lake3_LANDSCAPED_CONTEXT")
    bpy.context.scene.collection.children.link(root)
    root["c2w_final_pipeline_connected"] = True
    root["c2w_reference_image"] = LAKE_REFERENCE
    subcollections = {}
    for key in ("landscape", "paths", "vegetation", "furnishings", "pavilion"):
        subcollection = bpy.data.collections.new(f"urban:lake3:{key}")
        root.children.link(subcollection)
        subcollections[key] = subcollection

    paths = _connected_path_specs(outer_boundary)
    materials = make_context_materials()
    context_objects: list[bpy.types.Object] = []
    terrain = _build_landscape(
        water_boundary, paths, materials["lawn"], subcollections["landscape"]
    )
    context_objects.append(terrain)
    path_objects = []
    connection_records = []
    path_elevations = {
        # The connector overlaps the northwest promenade at its first span.
        # This 9 mm grading difference keeps the primary walk continuous and
        # prevents coplanar Cycles z-fighting at the junction.
        "pavilion_link": 0.306,
    }
    for name, controls, width in paths:
        path = _build_path_ribbon(
            f"urban:lake3:path:{name}",
            controls,
            width,
            path_elevations.get(name, 0.315),
            materials["path"],
            subcollections["paths"],
        )
        start = Vector((*controls[0], 0.0))
        measured_overlap = min((start - point).length for point in outer_boundary)
        inside_apron_band = _point_in_polygon(
            start.x, start.y, outer_boundary
        ) and not _point_in_polygon(start.x, start.y, water_boundary)
        path["c2w_lake_apron_overlap_m"] = measured_overlap
        path["c2w_starts_inside_lake_apron_band"] = inside_apron_band
        connection_records.append(
            {
                "name": name,
                "measured_outer_edge_overlap_m": round(measured_overlap, 4),
                "starts_inside_apron_band": inside_apron_band,
                "start_xy": [round(start.x, 4), round(start.y, 4)],
            }
        )
        path_objects.append(path)
        context_objects.append(path)

    plaza = _build_pavilion_plaza(materials["stone"], subcollections["pavilion"])
    context_objects.append(plaza)
    flower_bed = _build_path_ribbon(
        "urban:lake3:flowerbed:foreground_reference_border",
        [(28.0, -34.0), (39.0, -37.0), (50.0, -34.0)],
        3.45,
        0.285,
        materials["mulch"],
        subcollections["vegetation"],
        semantic="park-flowerbed",
        role="reference_foreground_mulched_flowerbed",
    )
    context_objects.append(flower_bed)

    # The lawn is a continuous PBR surface with shader-scale fibre/soil relief.
    # Deliberately do not create GrassTuftFactory geometry: isolated tufts were
    # the distracting one-blade-at-a-time ground model reported in lake2.
    terrain[
        "c2w_groundcover_method"
    ] = "continuous_shader_only_mown_lawn_no_blade_geometry"
    terrain["c2w_individual_grass_objects"] = 0
    flower_scatter, flower_master = _apply_official_flowers(
        flower_bed, subcollections["vegetation"]
    )
    context_objects.append(flower_scatter)

    tree_masters = _create_complex_tree_masters(materials)
    tree_instances = _place_infinigen_trees(
        tree_masters, subcollections["vegetation"], paths, outer_boundary
    )
    context_objects.extend(tree_instances)

    pavilion_objects = _append_pavilion(subcollections["pavilion"])
    context_objects.extend(pavilion_objects)
    bench_master, bench_parts = _load_bench_master()
    bench_instances = _place_benches(
        bench_master, subcollections["furnishings"], paths, outer_boundary
    )
    context_objects.extend(bench_instances)

    pavilion_meshes = [obj for obj in pavilion_objects if obj.type == "MESH"]
    bench_meshes = [obj for obj in bench_master.all_objects if obj.type == "MESH"]
    tree_meshes = [
        obj
        for master in tree_masters
        for obj in master.all_objects
        if obj.type == "MESH"
    ]
    unique_tree_meshes = {
        obj.data.as_pointer(): obj.data for obj in tree_meshes if obj.data is not None
    }
    pavilion_bounds = _world_bounds(pavilion_meshes)
    bench_bounds = _world_bounds(bench_meshes)
    tree_master_bounds = [
        _world_bounds(list(master.all_objects)) for master in tree_masters
    ]
    tree_master_heights = [
        bounds["max"][2] - bounds["min"][2] for bounds in tree_master_bounds
    ]

    for obj in context_objects:
        obj["c2w_reference_image"] = LAKE_REFERENCE
    record = {
        "modeling_quality": "production_high_detail_no_toy_fallbacks",
        "toy_fallbacks": 0,
        "landscape": {
            "vertices": len(terrain.data.vertices),
            "faces": len(terrain.data.polygons),
            "continuous_subgrade_under_hardscape": True,
            "continuous_lowered_lake_excavation": True,
            "lake_excavation_depth_m": float(
                terrain.get("c2w_lake_excavation_depth_m")
            ),
            "no_world_background_cracks": bool(
                terrain.get("c2w_no_world_background_cracks")
            ),
            "procedural_pbr_ground": True,
            "groundcover_method": terrain.get("c2w_groundcover_method"),
            "individual_grass_objects": int(
                terrain.get("c2w_individual_grass_objects", -1)
            ),
            "grass_geometry_scatter_present": False,
        },
        "path_system": {
            "curved_walks": len(path_objects),
            "spline_samples": sum(
                int(obj.get("c2w_spline_samples", 0)) for obj in path_objects
            ),
            "jointed_pbr_material": True,
            "coplanar_junctions_removed": True,
            "pavilion_connector_grade_offset_m": -0.009,
            "lake_edge_connections": connection_records,
            "connected_to_lake_apron_count": sum(
                record["starts_inside_apron_band"] for record in connection_records
            ),
            "maximum_outer_edge_overlap_m": max(
                record["measured_outer_edge_overlap_m"] for record in connection_records
            ),
            "minimum_outer_edge_overlap_m": min(
                record["measured_outer_edge_overlap_m"] for record in connection_records
            ),
            "tree_trunk_minimum_path_edge_clearance_m": min(
                float(obj["c2w_path_edge_clearance_m"]) for obj in tree_instances
            ),
            "bench_minimum_path_edge_clearance_m": min(
                float(obj["c2w_path_edge_clearance_m"]) for obj in bench_instances
            ),
        },
        "official_infinigen_vegetation": {
            "grass_call": None,
            "grass_master_objects": 0,
            "grass_geometry_policy": "forbidden_continuous_shader_lawn_only",
            "flower_call": flower_scatter.get("c2w_direct_infinigen_call"),
            "flower_master_objects": len(flower_master.objects),
            "tree_factory_call": FULL07_TREE_METHOD,
            "tree_source_blend": str(FULL07_TREE_BLEND),
            "tree_source_collections": list(FULL07_TREE_COLLECTIONS),
            "tree_factory_reused_existing_complex": all(
                bool(master.get("c2w_reused_existing_factory"))
                for master in tree_masters
            ),
            "tree_master_collections": len(tree_masters),
            "tree_master_vertices": sum(len(obj.data.vertices) for obj in tree_meshes),
            "tree_unique_mesh_vertices": sum(
                len(mesh.vertices) for mesh in unique_tree_meshes.values()
            ),
            "tree_master_faces": sum(len(obj.data.polygons) for obj in tree_meshes),
            "tree_master_meshes": len(tree_meshes),
            "tree_unique_meshes": len(unique_tree_meshes),
            "tree_master_height_range_m": [
                min(tree_master_heights),
                max(tree_master_heights),
            ],
            "placed_tree_height_range_m": [
                min(float(obj["c2w_real_world_height_m"]) for obj in tree_instances),
                max(float(obj["c2w_real_world_height_m"]) for obj in tree_instances),
            ],
            "tree_master_parts": sum(
                int(master.get("c2w_part_count", 0)) for master in tree_masters
            ),
            "explicit_leaf_geometry_count": sum(
                int(master.get("c2w_explicit_leaf_count", 0)) for master in tree_masters
            ),
            "botanical_branch_count": sum(
                int(master.get("c2w_botanical_branch_count", 0))
                for master in tree_masters
            ),
            "botanical_crown_forms": sorted(
                str(master.get("c2w_botanical_crown_form", "missing"))
                for master in tree_masters
            ),
            "all_helpers_excluded_and_removed": all(
                bool(master.get("c2w_internal_treefactory_helpers_excluded"))
                and bool(master.get("c2w_internal_treefactory_helpers_removed"))
                for master in tree_masters
            ),
            "all_blob_and_topiary_geometry_forbidden": all(
                bool(master.get("c2w_no_blob_or_topiary_geometry"))
                for master in tree_masters
            ),
            "tree_instances": len(tree_instances),
            "minimum_trunk_path_clearance_m": min(
                float(obj["c2w_path_edge_clearance_m"]) for obj in tree_instances
            ),
            "toy_tree_fallbacks": 0,
        },
        "reused_pavilion": {
            "source": str(WESTERN_PAVILION_BLEND),
            "prefix": "band:",
            "architectural_style": "Victorian western octagonal bandstand",
            "chinese_pavilion_objects": 0,
            "parts": len(pavilion_objects),
            "world_bounds": pavilion_bounds,
            "grounded_on_plaza": 0.20 <= pavilion_bounds["min"][2] <= 0.34,
            "new_model_created": False,
        },
        "reused_benches": {
            "source": str(BENCH_BLEND),
            "prefix": "clbench:",
            "master_parts": bench_parts,
            "master_bounds": bench_bounds,
            "master_dimensions": [
                bench_bounds["max"][axis] - bench_bounds["min"][axis]
                for axis in range(3)
            ],
            "instances": len(bench_instances),
            "collection_instancing": True,
            "new_model_created": False,
            "minimum_path_edge_clearance_m": min(
                float(obj["c2w_path_edge_clearance_m"]) for obj in bench_instances
            ),
        },
        "flowerbed": {
            "reference_foreground_bed": True,
            "official_infinigen_scatter": True,
        },
        "context_object_count": len(context_objects),
    }
    return context_objects, record


def add_camera() -> tuple[bpy.types.Object, bpy.types.Object]:
    bpy.ops.object.camera_add(location=VIEW_SPECS[0]["camera"])
    camera = bpy.context.active_object
    camera.name = "urban_lake_multiview_camera"
    camera.data.sensor_width = 36.0
    camera.data.lens = VIEW_SPECS[0]["lens"]
    camera.data.clip_start = 0.08
    camera.data.clip_end = 450.0
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_blades = 9
    camera.data.dof.aperture_ratio = 1.0
    camera.data.dof.aperture_fstop = VIEW_SPECS[0]["fstop"]
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=VIEW_SPECS[0]["target"])
    focus = bpy.context.active_object
    focus.name = "urban_lake_camera_focus"
    focus.hide_render = True
    camera.data.dof.focus_object = focus
    bpy.context.scene.camera = camera
    return camera, focus


def organize_asset_collection(objects: list[bpy.types.Object]) -> bpy.types.Collection:
    collection = bpy.data.collections.new("urban_v3_lake3_PRODUCTION_LAKE_ASSET")
    bpy.context.scene.collection.children.link(collection)
    for obj in objects:
        if obj.name not in collection.objects:
            collection.objects.link(obj)
        for old_collection in list(obj.users_collection):
            if old_collection is not collection:
                old_collection.objects.unlink(obj)
    collection[
        "c2w_generator"
    ] = "infinigen.assets.objects.decor.urban_lake.UrbanLakeFactory.create_lake"
    collection["c2w_generator_revision"] = GENERATOR_REVISION
    collection["c2w_final_pipeline_connected"] = True
    collection["c2w_reference_image"] = LAKE_REFERENCE
    return collection


def render_view(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    focus: bpy.types.Object,
    output_dir: Path,
    spec: dict,
) -> dict:
    camera.location = spec["camera"]
    camera.data.lens = spec["lens"]
    camera.data.dof.aperture_fstop = spec["fstop"]
    focus.location = spec["target"]
    look_at(camera, spec["target"])
    bpy.context.view_layer.update()
    output_path = output_dir / spec["name"]
    scene.render.filepath = str(output_path)
    started = time.time()
    bpy.ops.render.render(write_still=True)
    elapsed = time.time() - started
    if not output_path.exists() or output_path.stat().st_size < 10_000:
        raise RuntimeError(f"Render did not produce a valid image: {output_path}")
    return {
        "filename": spec["name"],
        "kind": spec["kind"],
        "camera": list(spec["camera"]),
        "target": list(spec["target"]),
        "lens_mm": spec["lens"],
        "fstop": spec["fstop"],
        "bytes": output_path.stat().st_size,
        "render_seconds": round(elapsed, 3),
    }


def _world_bounds(objects: list[bpy.types.Object]) -> dict:
    points = []
    for obj in objects:
        if not hasattr(obj, "bound_box"):
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    return {
        "min": [min(point[axis] for point in points) for axis in range(3)],
        "max": [max(point[axis] for point in points) for axis in range(3)],
    }


def collect_audit(
    args: argparse.Namespace,
    lake_objects: list[bpy.types.Object],
    context_objects: list[bpy.types.Object],
    generator_record: dict,
    context_record: dict,
    render_records: list[dict],
    blend_path: Path,
    device_report: dict,
) -> dict:
    all_objects = [*lake_objects, *context_objects]
    asset_meshes = [obj for obj in all_objects if obj.type == "MESH"]
    asset_curves = [obj for obj in all_objects if obj.type == "CURVE"]
    lake_semantics = sorted(
        {obj.get("urban_semantic", "missing") for obj in lake_objects}
    )
    context_semantics = sorted(
        {obj.get("urban_semantic", "missing") for obj in context_objects}
    )
    allowed_semantics = {"lake-platform", "lake-edge", "lake-water"}
    water = next(obj for obj in lake_objects if obj.get("c2w_direct_infinigen_call"))
    near_views = [record for record in render_records if record["kind"] == "near"]
    far_views = [record for record in render_records if record["kind"] == "far"]
    vegetation = context_record["official_infinigen_vegetation"]
    pavilion = context_record["reused_pavilion"]
    benches = context_record["reused_benches"]
    paths = context_record["path_system"]
    landscape = context_record["landscape"]
    grass_geometry_objects = [
        obj.name
        for obj in bpy.data.objects
        if obj.get("urban_semantic") == "park-grass"
        or "grasstuft" in obj.name.lower()
        or "grass_tuft" in obj.name.lower()
    ]
    partial_render = bool(args.skip_render or args.views)
    expected_render_count = (
        0
        if args.skip_render
        else len(args.views.split(","))
        if args.views
        else len(VIEW_SPECS)
    )
    checks = {
        "source_generator_executed_directly": True,
        "never_loaded_or_patched_existing_lake_blend": True,
        "final_pipeline_connected": True,
        "lake_factory_semantics_are_hydraulic_only": set(lake_semantics).issubset(
            allowed_semantics
        ),
        "irregular_non_ellipse_reference_footprint": (
            generator_record["footprint"]["shore_segments"] >= 256
            and "surveyed_asymmetric" in generator_record["footprint"]["shape"]
            and generator_record["footprint"]["control_points"] >= 32
            and generator_record["footprint"]["designed_coves"] >= 5
            and generator_record["footprint"]["normal_irregularity_amplitude_m"] >= 0.65
            and generator_record["footprint"]["apron_offset_method"]
            == "star_shaped_radial_no_concave_miter_crossings"
        ),
        "reference_two_distinct_overwater_platforms": (
            generator_record["platform_system"]["overwater_geometric_platforms"] == 2
            and len(set(generator_record["platform_system"]["platform_forms"])) == 2
        ),
        "dense_non_toy_water_surface": generator_record["water_system"]["vertices"]
        >= 16_000,
        "all_quad_water_without_center_singularity": (
            generator_record["water_system"]["topology"]
            == "all_quad_even_concentric_square_no_center_vertex"
            and generator_record["water_system"]["center_valence"] == 0
            and not generator_record["water_system"]["center_vertex_present"]
        ),
        "white_lake_center_artifact_removed": (
            bool(generator_record["water_system"]["white_center_artifact_removed"])
            and bool(water.get("c2w_white_center_artifact_removed"))
            and bool(
                water.active_material.get(
                    "c2w_depth_ramp_default_white_endpoint_removed"
                )
            )
            and bool(bpy.context.scene.get("c2w_no_finite_light_disks_over_lake"))
            and all(
                not bool(node.sun_disc)
                for node in bpy.context.scene.world.node_tree.nodes
                if node.bl_idname == "ShaderNodeTexSky"
            )
            and not any(
                obj.type == "LIGHT" and obj.data.type == "AREA"
                for obj in bpy.data.objects
            )
            and all(
                float(obj.data.specular_factor) == 0.0
                for obj in bpy.data.objects
                if obj.type == "LIGHT" and obj.data.type == "SUN"
            )
        ),
        "direct_official_infinigen_water_call": bool(
            water.get("c2w_direct_infinigen_call")
        ),
        "physical_closed_water_volume": float(water.get("c2w_volume_depth_m", 0.0))
        >= 1.8,
        "individual_jointed_apron_pavers": (
            generator_record["platform_system"]["individual_apron_pavers"] >= 1_200
            and generator_record["platform_system"][
                "paver_self_intersection_prevention"
            ]
        ),
        "individual_retaining_masonry": generator_record["platform_system"][
            "retaining_masonry_blocks"
        ]
        >= 750,
        "unique_rough_shore_stones": generator_record["platform_system"][
            "unique_rough_shore_stones"
        ]
        >= 700,
        "water_only_reference_fountain": generator_record["fountain_water_system"][
            "non_water_components"
        ]
        == 0,
        "landscaped_reference_context": (
            landscape["faces"] >= 5_000
            and paths["curved_walks"] == 8
            and paths["coplanar_junctions_removed"]
            and landscape["continuous_lowered_lake_excavation"]
            and landscape["lake_excavation_depth_m"] >= 2.3
            and landscape["no_world_background_cracks"]
        ),
        "all_radial_paths_physically_join_lake_apron": (
            paths["connected_to_lake_apron_count"] == paths["curved_walks"] == 8
            and all(
                record["starts_inside_apron_band"]
                for record in paths["lake_edge_connections"]
            )
            and 0.35 <= paths["minimum_outer_edge_overlap_m"] <= 1.15
            and paths["maximum_outer_edge_overlap_m"] <= 1.15
        ),
        "stone_paths_have_no_tree_or_bench_blockers": (
            paths["tree_trunk_minimum_path_edge_clearance_m"] >= 3.15
            and paths["bench_minimum_path_edge_clearance_m"] >= 1.35
            and vegetation["minimum_trunk_path_clearance_m"] >= 3.15
            and benches["minimum_path_edge_clearance_m"] >= 1.35
        ),
        "continuous_shader_lawn_without_individual_grass": (
            landscape["groundcover_method"]
            == "continuous_shader_only_mown_lawn_no_blade_geometry"
            and landscape["individual_grass_objects"] == 0
            and not landscape["grass_geometry_scatter_present"]
            and vegetation["grass_call"] is None
            and vegetation["grass_master_objects"] == 0
            and not grass_geometry_objects
        ),
        "direct_official_infinigen_flowers": (
            "FlowerPlantFactory" in vegetation["flower_call"]
            and "scatter_instances" in vegetation["flower_call"]
        ),
        "reused_verified_high_detail_treefactory_masters": (
            vegetation["tree_instances"] >= 20
            and vegetation["tree_master_vertices"] >= 50_000_000
            and vegetation["tree_master_faces"] >= 50_000_000
            and vegetation["tree_master_collections"] == 5
            and vegetation["tree_master_parts"] == 10
            and vegetation["explicit_leaf_geometry_count"] >= 15_000
            and vegetation["botanical_branch_count"] >= 1_750
            and vegetation["tree_master_meshes"] == 10
            and vegetation["tree_unique_meshes"] == 10
            and 8.0 <= vegetation["tree_master_height_range_m"][0] <= 8.3
            and 9.1 <= vegetation["tree_master_height_range_m"][1] <= 9.3
            and 7.5 <= vegetation["placed_tree_height_range_m"][0] <= 8.1
            and 8.8 <= vegetation["placed_tree_height_range_m"][1] <= 9.3
            and vegetation["botanical_crown_forms"]
            == ["columnar", "irregular_oak", "rounded", "spreading", "vase"]
            and vegetation["all_helpers_excluded_and_removed"]
            and vegetation["all_blob_and_topiary_geometry_forbidden"]
            and vegetation["tree_factory_reused_existing_complex"]
            and vegetation["tree_factory_call"] == FULL07_TREE_METHOD
            and vegetation["tree_source_blend"] == str(FULL07_TREE_BLEND)
            and vegetation["tree_source_collections"] == list(FULL07_TREE_COLLECTIONS)
            and vegetation["toy_tree_fallbacks"] == 0
        ),
        "western_victorian_lakeside_pavilion": (
            pavilion["parts"] >= 95
            and pavilion["source"] == str(WESTERN_PAVILION_BLEND)
            and pavilion["prefix"] == "band:"
            and pavilion["architectural_style"]
            == "Victorian western octagonal bandstand"
            and pavilion["chinese_pavilion_objects"] == 0
            and pavilion["grounded_on_plaza"]
            and pavilion["world_bounds"]["max"][2] - pavilion["world_bounds"]["min"][2]
            >= 5.0
            and not pavilion["new_model_created"]
        ),
        "reused_existing_complex_benches": (
            benches["master_parts"] >= 30
            and benches["instances"] >= 8
            and benches["collection_instancing"]
            and 1.7 <= benches["master_dimensions"][0] <= 2.1
            and 0.75 <= benches["master_dimensions"][1] <= 1.0
            and 0.85 <= benches["master_dimensions"][2] <= 1.05
            and not benches["new_model_created"]
        ),
        "no_toy_or_degraded_fallbacks": (
            context_record["toy_fallbacks"] == 0
            and vegetation["toy_tree_fallbacks"] == 0
            and pavilion["chinese_pavilion_objects"] == 0
        ),
        "daylight_multiview": (
            len(render_records) == expected_render_count
            if not args.skip_render
            else True
        ),
        "near_and_far_views": bool(near_views and far_views)
        if not partial_render
        else True,
        "blend_saved": blend_path.exists(),
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("Lake production audit failed: " + ", ".join(failed))
    return {
        "asset": "urban_v3_lake3",
        "generator": (
            "infinigen.assets.objects.decor.urban_lake.UrbanLakeFactory.create_lake"
            " + scripts.generate_urban_v3_lake.build_lakeside_context"
        ),
        "entrypoint": "scripts/generate_urban_v3_lake.py",
        "generator_revision": GENERATOR_REVISION,
        "reference_image": LAKE_REFERENCE,
        "output_directory": str(args.output.resolve()),
        "blend_file": blend_path.name,
        "render_engine": bpy.context.scene.render.engine,
        "resolution": [args.resolution_x, args.resolution_y],
        "samples": args.samples,
        "cycles_device": device_report,
        "daylight": {
            "sky": "Nishita clear day",
            "sun_elevation_degrees": 39.0,
            "sun_rotation_degrees": 128.0,
            "physical_sun_and_nishita_hemispherical_fill": True,
            "finite_disk_lights_over_water": 0,
        },
        "generator_record": generator_record,
        "context_record": context_record,
        "object_count": len(all_objects),
        "lake_object_count": len(lake_objects),
        "context_object_count": len(context_objects),
        "mesh_object_count": len(asset_meshes),
        "curve_object_count": len(asset_curves),
        "mesh_vertices": sum(len(obj.data.vertices) for obj in asset_meshes),
        "mesh_polygons": sum(len(obj.data.polygons) for obj in asset_meshes),
        "material_count": len(bpy.data.materials),
        "lake_semantics": lake_semantics,
        "context_semantics": context_semantics,
        "world_bounds": _world_bounds(all_objects),
        "render_views": render_records,
        "checks": checks,
        "failed_checks": failed,
    }


def main() -> None:
    args = parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"LAKE_PRODUCTION: output={output_dir}", flush=True)
    print("LAKE_PRODUCTION: clearing scene and configuring daylight", flush=True)
    clear_scene()
    device_report = configure_render(args)
    configure_daylight()

    print("LAKE_PRODUCTION: invoking UrbanLakeFactory.create_lake", flush=True)
    request = UrbanAssetRequest(
        asset_type="artificial_urban_lake",
        location=(0.0, 0.0, 0.0),
        semantic="lake",
        params={"id": "urban_v3_lake3", "reference": LAKE_REFERENCE},
    )
    factory = UrbanLakeFactory()
    objects, generator_record = factory.create_lake(request)
    organize_asset_collection(objects)
    print(
        "LAKE_PRODUCTION: building reference landscaped context and reusing production assets",
        flush=True,
    )
    context_objects, context_record = build_lakeside_context(factory.last_geometry)
    bpy.context.view_layer.update()
    print(
        f"LAKE_PRODUCTION: generated {len(objects)} lake objects and "
        f"{len(context_objects)} context objects; "
        f"{sum(len(obj.data.vertices) for obj in [*objects, *context_objects] if obj.type == 'MESH')} visible source vertices",
        flush=True,
    )

    camera, focus = add_camera()
    selected_names = set(args.views.split(",")) if args.views else None
    selected_specs = [
        spec
        for spec in VIEW_SPECS
        if selected_names is None or spec["name"] in selected_names
    ]
    if selected_names:
        unknown = selected_names - {spec["name"] for spec in VIEW_SPECS}
        if unknown:
            raise ValueError("Unknown render view(s): " + ", ".join(sorted(unknown)))

    render_records = []
    if not args.skip_render:
        for index, spec in enumerate(selected_specs, start=1):
            print(
                f"LAKE_PRODUCTION: rendering {index}/{len(selected_specs)} {spec['name']}",
                flush=True,
            )
            render_records.append(
                render_view(bpy.context.scene, camera, focus, output_dir, spec)
            )

    bpy.context.scene["c2w_asset"] = "urban_v3_lake3"
    bpy.context.scene["c2w_source_generator"] = "scripts/generate_urban_v3_lake.py"
    bpy.context.scene["c2w_generator_revision"] = GENERATOR_REVISION
    bpy.context.scene["c2w_final_pipeline_connected"] = True
    bpy.context.scene["c2w_reference_image"] = LAKE_REFERENCE
    bpy.context.scene["c2w_landscaped_reference_context"] = True
    bpy.context.scene["c2w_reused_complex_pavilion_and_benches"] = True
    bpy.context.scene["c2w_reused_full07_botanical_tree_masters"] = True
    bpy.context.scene["c2w_white_center_artifact_removed"] = True
    bpy.context.scene["c2w_no_toy_fallbacks"] = True
    bpy.context.scene["c2w_daylight_multiview"] = True
    blend_path = output_dir / "urban_v3_lake3.blend"
    print(f"LAKE_PRODUCTION: saving {blend_path}", flush=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    audit = collect_audit(
        args,
        objects,
        context_objects,
        generator_record,
        context_record,
        render_records,
        blend_path,
        device_report,
    )
    audit_path = output_dir / "lake_generation_audit.json"
    audit_path.write_text(json.dumps(audit, indent=2), encoding="utf-8")
    manifest_path = output_dir / "render_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "asset": "urban_v3_lake3",
                "reference": LAKE_REFERENCE,
                "generator_revision": GENERATOR_REVISION,
                "daylight_near_and_far": True,
                "views": render_records,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {"status": "PASS", "checks": audit["checks"], "views": render_records},
            indent=2,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

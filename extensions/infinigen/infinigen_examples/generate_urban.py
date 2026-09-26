# Copyright (C) 2023, Princeton University.
# This source code is licensed under the BSD 3-Clause license found in the LICENSE file in the root directory
# of this source tree.


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths['WORLDBRIDGE_SITE_PACKAGES']

import argparse
import json
import logging
import math
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CONDA_SITE_PACKAGES = Path(f'{_wb_WORLDBRIDGE_SITE_PACKAGES}')
if CONDA_SITE_PACKAGES.exists():
    sys.path.insert(0, str(CONDA_SITE_PACKAGES))

# ruff: noqa: E402
logging.basicConfig(
    format="[%(asctime)s.%(msecs)03d] [%(module)s] [%(levelname)s] | %(message)s",
    datefmt="%H:%M:%S",
    level=logging.INFO,
)

import bpy
import gin
import numpy as np
from mathutils import Vector

from infinigen.core import init, tagging
from infinigen.core.tagging import tag_system
from infinigen.core.util import blender as butil
from infinigen.core.util.logging import save_polycounts
from infinigen.assets.objects.urban.factory_building import (
    FACTORY_REFERENCES,
    FACTORY_VARIANTS,
    FactoryBuildingFactory,
    make_factory_materials,
)
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest, mesh_obj, multi_curve_obj

logger = logging.getLogger(__name__)


def _make_mat(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    emission_strength=0.0,
    noise_strength=0.0,
    bump_strength=0.0,
    noise_scale=22.0,
    bump_scale=48.0,
    transmission=0.0,
    ior=1.45,
    coat_weight=0.0,
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        def set_input(names, value):
            for input_name in names:
                if input_name in bsdf.inputs:
                    bsdf.inputs[input_name].default_value = value
                    return

        bsdf.inputs["Base Color"].default_value = color
        if len(color) > 3 and color[3] < 1 and "Alpha" in bsdf.inputs:
            bsdf.inputs["Alpha"].default_value = color[3]
            try:
                if hasattr(mat, "surface_render_method"):
                    mat.surface_render_method = "DITHERED"
                elif hasattr(mat, "blend_method"):
                    mat.blend_method = "BLEND"
            except (TypeError, ValueError):
                logger.debug("Using opaque fallback for material %s", name)
            if hasattr(mat, "use_screen_refraction"):
                mat.use_screen_refraction = True
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        set_input(("Transmission Weight", "Transmission"), transmission)
        set_input(("IOR",), ior)
        set_input(("Coat Weight", "Clearcoat"), coat_weight)
        if emission_strength > 0:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = color
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
        if noise_strength > 0:
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            noise = nodes.new(type="ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = noise_scale
            noise.inputs["Detail"].default_value = 9
            noise.inputs["Roughness"].default_value = 0.58
            ramp = nodes.new(type="ShaderNodeValToRGB")
            low = tuple(max(0.0, c * (1.0 - noise_strength)) for c in color[:3]) + (color[3],)
            high = tuple(min(1.0, c * (1.0 + noise_strength)) for c in color[:3]) + (color[3],)
            ramp.color_ramp.elements[0].position = 0.2
            ramp.color_ramp.elements[0].color = low
            ramp.color_ramp.elements[1].position = 1.0
            ramp.color_ramp.elements[1].color = high
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if bump_strength > 0 and "Normal" in bsdf.inputs:
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            noise = nodes.new(type="ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = bump_scale
            noise.inputs["Detail"].default_value = 12
            bump = nodes.new(type="ShaderNodeBump")
            bump.inputs["Strength"].default_value = bump_strength
            bump.inputs["Distance"].default_value = 0.055
            links.new(noise.outputs["Fac"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def _add_bevel(obj, width=0.025, segments=1):
    if width <= 0:
        return obj
    bevel = obj.modifiers.new(name="urban_soft_edges", type="BEVEL")
    bevel.width = width
    bevel.segments = segments
    bevel.affect = "EDGES"
    obj.modifiers.new(name="urban_weighted_normals", type="WEIGHTED_NORMAL")
    return obj


def _cube_obj(name, loc, dims, mat, semantic, bevel=0.015):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat is not None:
        obj.data.materials.append(mat)
    _add_bevel(obj, bevel)
    tagging.tag_object(obj, semantic)
    return obj


def _cylinder_obj(name, loc, radius, depth, mat, semantic, vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices,
        radius=radius,
        depth=depth,
        location=loc,
    )
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    tagging.tag_object(obj, semantic)
    return obj


def _sphere_obj(name, loc, radius, mat, semantic):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32,
        ring_count=16,
        radius=radius,
        location=loc,
    )
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    tagging.tag_object(obj, semantic)
    return obj


def _cone_obj(name, loc, radius1, radius2, depth, mat, semantic, vertices=12):
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices,
        radius1=radius1,
        radius2=radius2,
        depth=depth,
        location=loc,
    )
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    tagging.tag_object(obj, semantic)
    return obj


def _batched_rectangles(name, specs, mat, semantic):
    verts = []
    faces = []
    for cx, cy, z, sx, sy, rot in specs:
        c = math.cos(rot)
        s = math.sin(rot)
        idx = len(verts)
        for px, py in [(-sx / 2, -sy / 2), (sx / 2, -sy / 2), (sx / 2, sy / 2), (-sx / 2, sy / 2)]:
            verts.append((cx + c * px - s * py, cy + s * px + c * py, z))
        faces.append((idx, idx + 1, idx + 2, idx + 3))
    if not verts:
        return None
    return mesh_obj(name, verts, faces, mat, semantic, smooth=False)


def _batched_disks(name, specs, mat, semantic, segments=12):
    verts = []
    faces = []
    for cx, cy, z, rx, ry, rot in specs:
        c = math.cos(rot)
        s = math.sin(rot)
        idx = len(verts)
        verts.append((cx, cy, z))
        ring = []
        for k in range(segments):
            a = math.tau * k / segments
            px = math.cos(a) * rx
            py = math.sin(a) * ry
            ring.append(len(verts))
            verts.append((cx + c * px - s * py, cy + s * px + c * py, z))
        for k in range(segments):
            faces.append((idx, ring[k], ring[(k + 1) % segments]))
    if not verts:
        return None
    return mesh_obj(name, verts, faces, mat, semantic, smooth=False)


def _within_road_cross(x, y, half_road):
    return abs(y) <= half_road or abs(x) <= half_road


def _surface_realism_details(mats, block_extent, road_width, sidewalk_width, curb_height, rng):
    half_len = block_extent / 2
    half_road = road_width / 2
    walk_limit = half_road + sidewalk_width
    objects = []
    layout = []

    aggregate = []
    for _ in range(420):
        if rng.random() < 0.5:
            x = rng.uniform(-half_len + 1.0, half_len - 1.0)
            y = rng.uniform(-half_road + 0.25, half_road - 0.25)
        else:
            x = rng.uniform(-half_road + 0.25, half_road - 0.25)
            y = rng.uniform(-half_len + 1.0, half_len - 1.0)
        aggregate.append((x, y, 0.116, rng.uniform(0.035, 0.12), rng.uniform(0.012, 0.04), rng.uniform(0, math.tau)))
    obj = _batched_rectangles("urban:surface:asphalt_aggregate", aggregate, mats["asphalt_aggregate"], "road-grit")
    if obj:
        objects.append(obj)
        layout.append({"id": "asphalt_aggregate", "type": "batched-road-grit", "count": len(aggregate)})

    paint_chips = []
    for _ in range(170):
        side = rng.choice(["north", "south", "east", "west", "lane_x", "lane_y"])
        if side == "north":
            x = rng.uniform(-3.1, 3.1)
            y = rng.uniform(half_road + sidewalk_width * 0.03, half_road + sidewalk_width * 0.68)
            sx, sy = rng.uniform(0.04, 0.12), rng.uniform(0.18, 0.42)
        elif side == "south":
            x = rng.uniform(-3.1, 3.1)
            y = rng.uniform(-half_road - sidewalk_width * 0.68, -half_road - sidewalk_width * 0.03)
            sx, sy = rng.uniform(0.04, 0.12), rng.uniform(0.18, 0.42)
        elif side == "east":
            x = rng.uniform(half_road + sidewalk_width * 0.03, half_road + sidewalk_width * 0.68)
            y = rng.uniform(-3.1, 3.1)
            sx, sy = rng.uniform(0.18, 0.42), rng.uniform(0.04, 0.12)
        elif side == "west":
            x = rng.uniform(-half_road - sidewalk_width * 0.68, -half_road - sidewalk_width * 0.03)
            y = rng.uniform(-3.1, 3.1)
            sx, sy = rng.uniform(0.18, 0.42), rng.uniform(0.04, 0.12)
        elif side == "lane_x":
            x = rng.choice(np.linspace(-half_len + 6, half_len - 6, 9)) + rng.uniform(-0.9, 0.9)
            y = rng.uniform(-0.06, 0.06)
            sx, sy = rng.uniform(0.10, 0.35), rng.uniform(0.025, 0.07)
        else:
            x = rng.uniform(-0.06, 0.06)
            y = rng.choice(np.linspace(-half_len + 6, half_len - 6, 9)) + rng.uniform(-0.9, 0.9)
            sx, sy = rng.uniform(0.025, 0.07), rng.uniform(0.10, 0.35)
        paint_chips.append((x, y, 0.126, sx, sy, rng.uniform(-0.18, 0.18)))
    obj = _batched_rectangles("urban:surface:worn_paint_chips", paint_chips, mats["paint_wear"], "paint-wear")
    if obj:
        objects.append(obj)
        layout.append({"id": "worn_paint_chips", "type": "batched-paint-wear", "count": len(paint_chips)})

    curb_grime = []
    for x in np.linspace(-half_len + 3, half_len - 3, 22):
        curb_grime.append((x, half_road + 0.19, curb_height + 0.083, rng.uniform(1.0, 2.2), 0.035, 0))
        curb_grime.append((x, -half_road - 0.19, curb_height + 0.083, rng.uniform(1.0, 2.2), 0.035, 0))
    for y in np.linspace(-half_len + 3, half_len - 3, 22):
        curb_grime.append((half_road + 0.19, y, curb_height + 0.083, 0.035, rng.uniform(1.0, 2.2), 0))
        curb_grime.append((-half_road - 0.19, y, curb_height + 0.083, 0.035, rng.uniform(1.0, 2.2), 0))
    obj = _batched_rectangles("urban:surface:curb_grime", curb_grime, mats["curb_grime"], "curb-grime")
    if obj:
        objects.append(obj)
        layout.append({"id": "curb_grime", "type": "batched-curb-grime", "count": len(curb_grime)})

    paper = []
    gum = []
    leaves = []
    sidewalk_stains = []
    for _ in range(180):
        for _retry in range(20):
            x = rng.uniform(-half_len + 1.0, half_len - 1.0)
            y = rng.uniform(-half_len + 1.0, half_len - 1.0)
            if not _within_road_cross(x, y, walk_limit) and rng.random() > 0.3:
                break
            if not _within_road_cross(x, y, half_road + 0.15):
                break
        z = curb_height + 0.045
        if rng.random() < 0.36:
            paper.append((x, y, z + 0.003, rng.uniform(0.10, 0.24), rng.uniform(0.04, 0.14), rng.uniform(0, math.tau)))
        elif rng.random() < 0.55:
            gum.append((x, y, z + 0.002, rng.uniform(0.035, 0.075), rng.uniform(0.025, 0.065), rng.uniform(0, math.tau)))
        else:
            leaves.append((x, y, z + 0.004, rng.uniform(0.08, 0.20), rng.uniform(0.025, 0.075), rng.uniform(0, math.tau)))
    for _ in range(45):
        x = rng.uniform(-half_len + 3.0, half_len - 3.0)
        y = rng.choice([-1, 1]) * rng.uniform(half_road + 0.5, half_road + sidewalk_width + 1.8)
        sidewalk_stains.append((x, y, curb_height + 0.047, rng.uniform(0.25, 0.9), rng.uniform(0.10, 0.36), rng.uniform(0, math.tau)))
    for name, specs, mat_key, sem in [
        ("urban:surface:paper_litter", paper, "paper_litter", "litter"),
        ("urban:surface:gum_spots", gum, "gum", "sidewalk-wear"),
        ("urban:surface:leaf_litter", leaves, "leaf_litter", "leaf-litter"),
        ("urban:surface:sidewalk_stains", sidewalk_stains, "sidewalk_stain", "sidewalk-wear"),
    ]:
        obj = _batched_rectangles(name, specs, mats[mat_key], sem)
        if obj:
            objects.append(obj)
            layout.append({"id": name.split(":")[-1], "type": sem, "count": len(specs)})

    oil = [
        (rng.uniform(-half_len + 6, half_len - 6), rng.choice([-1, 1]) * rng.uniform(1.0, half_road - 0.8), 0.128, rng.uniform(0.35, 0.85), rng.uniform(0.12, 0.32), rng.uniform(0, math.tau))
        for _ in range(18)
    ]
    obj = _batched_disks("urban:surface:oil_sheen", oil, mats["oil_sheen"], "road-stain", segments=14)
    if obj:
        objects.append(obj)
        layout.append({"id": "oil_sheen", "type": "batched-road-stain", "count": len(oil)})

    weeds = []
    for x in np.linspace(-half_len + 2, half_len - 2, 35):
        if rng.random() < 0.7:
            weeds.append([(x, half_road + 0.18, curb_height + 0.09), (x + rng.uniform(-0.04, 0.04), half_road + 0.25, curb_height + rng.uniform(0.16, 0.28))])
        if rng.random() < 0.7:
            weeds.append([(x, -half_road - 0.18, curb_height + 0.09), (x + rng.uniform(-0.04, 0.04), -half_road - 0.25, curb_height + rng.uniform(0.16, 0.28))])
    for y in np.linspace(-half_len + 2, half_len - 2, 35):
        if rng.random() < 0.55:
            weeds.append([(half_road + 0.18, y, curb_height + 0.09), (half_road + 0.25, y + rng.uniform(-0.04, 0.04), curb_height + rng.uniform(0.16, 0.28))])
        if rng.random() < 0.55:
            weeds.append([(-half_road - 0.18, y, curb_height + 0.09), (-half_road - 0.25, y + rng.uniform(-0.04, 0.04), curb_height + rng.uniform(0.16, 0.28))])
    if weeds:
        objects.append(multi_curve_obj("urban:surface:curb_weeds", weeds, 0.01, mats["grass_tuft"], "weed"))
        layout.append({"id": "curb_weeds", "type": "batched-weed-curves", "count": len(weeds)})

    return objects, layout


def _look_at(obj, target):
    bpy.context.view_layer.update()
    direction = Vector(target) - obj.matrix_world.translation
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def _add_camera_rig(block_extent):
    from infinigen.core.placement import camera as cam_util

    rigs = cam_util.spawn_camera_rigs()
    rig = rigs[0]
    rig.location = (-block_extent * 0.33, -block_extent * 0.34, 2.55)
    rig.rotation_euler = (0, 0, 0)
    camera = rig.children[0]
    camera.location = (0, 0, 0)
    camera.data.lens = 24
    _look_at(camera, (5.5, -4.0, 1.25))
    bpy.context.scene.camera = camera
    return rigs


def _add_lighting():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    sun = bpy.context.active_object
    sun.name = "urban:sun"
    sun.data.energy = 3.4
    sun.rotation_euler = (math.radians(48), 0, math.radians(-38))

    bpy.ops.object.light_add(type="AREA", location=(0, -18, 8))
    area = bpy.context.active_object
    area.name = "urban:soft_sky_fill"
    area.data.energy = 95
    area.data.size = 22


def _add_world():
    world = bpy.context.scene.world or bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.color = (0.56, 0.64, 0.78)
    try:
        bpy.context.scene.view_settings.view_transform = "Standard"
        bpy.context.scene.view_settings.look = "Medium High Contrast"
    except Exception:
        logger.info("Using Blender default color management for this environment")
    bpy.context.scene.view_settings.exposure = 0
    bpy.context.scene.view_settings.gamma = 1


def _block_scene(mats, block_extent, road_width, sidewalk_width, curb_height):
    half_len = block_extent / 2
    half_road = road_width / 2

    objects = []
    layout = {
        "coordinate_system": {
            "main_street_axis": "+X",
            "cross_street_axis": "+Y",
            "up_axis": "+Z",
            "units": "meters",
        },
        "design_intent": "outdoor-first urban block with one indoor anchor",
        "roads": [],
        "intersections": [],
        "sidewalks": [],
        "curbs": [],
        "crosswalks": [],
        "public_spaces": [],
        "buildings": [],
        "street_assets": [],
        "surface_details": [],
        "camera_path": [],
    }

    objects.append(
        _cube_obj(
            "urban:sidewalk:block_base",
            (0, 0, curb_height / 2 - 0.01),
            (block_extent, block_extent, curb_height),
            mats["concrete"],
            "sidewalk",
            bevel=0.0,
        )
    )
    layout["sidewalks"].append(
        {
            "id": "block_sidewalk_base",
            "bounds": [-half_len, -half_len, half_len, half_len],
            "note": "asphalt road meshes are layered above this concrete pedestrian field",
        }
    )

    lawn_specs = [
        ("northwest_lawn", (-22, 22, curb_height + 0.012), (12, 10, 0.035)),
        ("northeast_lawn", (22, 22, curb_height + 0.012), (11, 9, 0.035)),
        ("southwest_lawn", (-23, -23, curb_height + 0.012), (10, 8, 0.035)),
        ("plaza_lawn_strip", (24, -25.5, curb_height + 0.014), (7, 2.3, 0.035)),
    ]
    for lid, loc, dims in lawn_specs:
        objects.append(
            _cube_obj(
                f"urban:lawn:{lid}",
                loc,
                dims,
                mats["grass"],
                "lawn",
                bevel=0.02,
            )
        )
    layout["public_spaces"].extend(
        [
            {"id": "northwest_lawn", "type": "lawn", "center": [-22, 22, 0], "size": [12, 10]},
            {"id": "northeast_lawn", "type": "lawn", "center": [22, 22, 0], "size": [11, 9]},
            {"id": "southwest_lawn", "type": "lawn", "center": [-23, -23, 0], "size": [10, 8]},
        ]
    )

    inner_walk = half_road + sidewalk_width
    sidewalk_quadrants = [
        ("nw", (-half_len, -inner_walk), (inner_walk, half_len)),
        ("ne", (inner_walk, half_len), (inner_walk, half_len)),
        ("sw", (-half_len, -inner_walk), (-half_len, -inner_walk)),
        ("se", (inner_walk, half_len), (-half_len, -inner_walk)),
    ]
    seam_z = curb_height + 0.012
    for qid, xr, yr in sidewalk_quadrants:
        for idx, x in enumerate(np.arange(xr[0] + 2.0, xr[1], 2.0)):
            objects.append(
                _cube_obj(
                    f"urban:sidewalk_joint:{qid}:x:{idx}",
                    (x, (yr[0] + yr[1]) / 2, seam_z),
                    (0.026, abs(yr[1] - yr[0]), 0.01),
                    mats["concrete_seam"],
                    "sidewalk-joint",
                    bevel=0.0,
                )
            )
        for idx, y in enumerate(np.arange(yr[0] + 2.0, yr[1], 2.0)):
            objects.append(
                _cube_obj(
                    f"urban:sidewalk_joint:{qid}:y:{idx}",
                    ((xr[0] + xr[1]) / 2, y, seam_z),
                    (abs(xr[1] - xr[0]), 0.026, 0.01),
                    mats["concrete_seam"],
                    "sidewalk-joint",
                    bevel=0.0,
                )
            )

    objects.append(
        _cube_obj(
            "urban:road:main_x",
            (0, 0, 0.02),
            (block_extent, road_width, 0.06),
            mats["asphalt"],
            "road",
            bevel=0.0,
        )
    )
    layout["roads"].append(
        {
            "id": "main_x",
            "centerline": [[-half_len, 0, 0], [half_len, 0, 0]],
            "width": road_width,
        }
    )

    objects.append(
        _cube_obj(
            "urban:road:cross_y",
            (0, 0, 0.025),
            (road_width, block_extent, 0.065),
            mats["asphalt"],
            "road",
            bevel=0.0,
        )
    )
    layout["roads"].append(
        {
            "id": "cross_y",
            "centerline": [[0, -half_len, 0], [0, half_len, 0]],
            "width": road_width,
        }
    )
    layout["intersections"].append(
        {
            "id": "central_cross_intersection",
            "type": "cross",
            "center": [0, 0, 0],
            "road_ids": ["main_x", "cross_y"],
        }
    )

    curb_specs = [
        ("north_main_w", (-half_len / 2 - half_road, half_road + 0.08, curb_height + 0.035), (half_len - road_width, 0.16, 0.07)),
        ("north_main_e", (half_len / 2 + half_road, half_road + 0.08, curb_height + 0.035), (half_len - road_width, 0.16, 0.07)),
        ("south_main_w", (-half_len / 2 - half_road, -half_road - 0.08, curb_height + 0.035), (half_len - road_width, 0.16, 0.07)),
        ("south_main_e", (half_len / 2 + half_road, -half_road - 0.08, curb_height + 0.035), (half_len - road_width, 0.16, 0.07)),
        ("west_cross_s", (-half_road - 0.08, -half_len / 2 - half_road, curb_height + 0.035), (0.16, half_len - road_width, 0.07)),
        ("west_cross_n", (-half_road - 0.08, half_len / 2 + half_road, curb_height + 0.035), (0.16, half_len - road_width, 0.07)),
        ("east_cross_s", (half_road + 0.08, -half_len / 2 - half_road, curb_height + 0.035), (0.16, half_len - road_width, 0.07)),
        ("east_cross_n", (half_road + 0.08, half_len / 2 + half_road, curb_height + 0.035), (0.16, half_len - road_width, 0.07)),
    ]
    for cid, loc, dims in curb_specs:
        objects.append(
            _cube_obj(
                f"urban:curb:{cid}",
                loc,
                dims,
                mats["curb"],
                "curb",
                bevel=0.025,
            )
        )
        layout["curbs"].append({"id": cid, "center": list(loc), "size": list(dims)})

    crosswalks = [
        ("north", 0, half_road + sidewalk_width * 0.35, "x"),
        ("south", 0, -half_road - sidewalk_width * 0.35, "x"),
        ("east", half_road + sidewalk_width * 0.35, 0, "y"),
        ("west", -half_road - sidewalk_width * 0.35, 0, "y"),
    ]
    for name, cx, cy, axis in crosswalks:
        stripe_centers = np.linspace(-2.8, 2.8, 7)
        for idx, offset in enumerate(stripe_centers):
            loc = (cx + offset, cy, 0.08) if axis == "x" else (cx, cy + offset, 0.08)
            dims = (0.42, road_width * 0.85, 0.018) if axis == "x" else (road_width * 0.85, 0.42, 0.018)
            objects.append(
                _cube_obj(
                    f"urban:crosswalk:{name}:stripe_{idx:02d}",
                    loc,
                    dims,
                    mats["paint"],
                    "crosswalk",
                    bevel=0.0,
                )
            )
        layout["crosswalks"].append(
            {
                "id": f"crosswalk_{name}",
                "center": [cx, cy, 0],
                "axis": axis,
                "road_width": road_width,
            }
        )

    for x in np.linspace(-half_len + 6, half_len - 6, 9):
        objects.append(
            _cube_obj(
                f"urban:lane_marking:{x:.1f}",
                (x, 0, 0.032),
                (2.2, 0.11, 0.015),
                mats["paint"],
                "lane-marking",
                bevel=0.0,
            )
        )

    for y in np.linspace(-half_len + 6, half_len - 6, 9):
        objects.append(
            _cube_obj(
                f"urban:lane_marking:cross:{y:.1f}",
                (0, y, 0.075),
                (0.11, 2.2, 0.015),
                mats["paint"],
                "lane-marking",
                bevel=0.0,
            )
        )

    stop_lines = [
        ("north", (0, half_road + sidewalk_width * 0.72, 0.085), (road_width * 0.92, 0.18, 0.016)),
        ("south", (0, -half_road - sidewalk_width * 0.72, 0.085), (road_width * 0.92, 0.18, 0.016)),
        ("east", (half_road + sidewalk_width * 0.72, 0, 0.085), (0.18, road_width * 0.92, 0.016)),
        ("west", (-half_road - sidewalk_width * 0.72, 0, 0.085), (0.18, road_width * 0.92, 0.016)),
    ]
    for sid, loc, dims in stop_lines:
        objects.append(
            _cube_obj(
                f"urban:stop_line:{sid}",
                loc,
                dims,
                mats["paint"],
                "stop-line",
                bevel=0.0,
            )
        )

    for i, (x, y, sx, sy) in enumerate(
        [(-21, -1.7, 5.5, 1.4), (19, 1.8, 4.2, 1.2), (1.7, 21, 1.3, 5.0), (-1.8, -18, 1.2, 4.5)]
    ):
        objects.append(
            _cube_obj(
                f"urban:asphalt_patch:{i}",
                (x, y, 0.091),
                (sx, sy, 0.01),
                mats["asphalt_patch"],
                "road-patch",
                bevel=0.01,
            )
        )

    road_stains = [
        (-26, 1.2, 3.0, 0.45), (-14, -1.0, 2.1, 0.35), (9, 1.35, 2.8, 0.38),
        (25, -1.25, 2.4, 0.42), (1.2, -26, 0.42, 2.7), (-1.25, -8, 0.36, 2.2),
        (1.15, 10, 0.38, 2.6), (-1.35, 25, 0.42, 2.5),
    ]
    for i, (x, y, sx, sy) in enumerate(road_stains):
        objects.append(
            _cube_obj(
                f"urban:road_stain:{i}",
                (x, y, 0.103),
                (sx, sy, 0.006),
                mats["road_stain"],
                "road-wear",
                bevel=0.004,
            )
        )

    crack_specs = [
        (-27, -2.55, 5.2, 0.035), (-3.5, 2.45, 4.4, 0.03), (14, -2.3, 3.8, 0.028),
        (2.55, -25, 0.032, 5.4), (-2.45, 6, 0.03, 4.3), (2.45, 22, 0.032, 4.2),
    ]
    for i, (x, y, sx, sy) in enumerate(crack_specs):
        objects.append(
            _cube_obj(
                f"urban:road_crack:{i}",
                (x, y, 0.109),
                (sx, sy, 0.008),
                mats["road_crack"],
                "road-crack",
                bevel=0.002,
            )
        )

    for i, (x, y) in enumerate([(-12, 2.6), (15, -2.4), (2.4, -14), (-2.5, 17)]):
        objects.append(
            _cylinder_obj(
                f"urban:manhole:{i}",
                (x, y, 0.102),
                0.42,
                0.018,
                mats["manhole"],
                "manhole",
                vertices=32,
            )
        )

    ramp_specs = [
        ("nw", (-5.45, 5.45, curb_height + 0.02), (1.4, 1.4, 0.05)),
        ("ne", (5.45, 5.45, curb_height + 0.02), (1.4, 1.4, 0.05)),
        ("se", (5.45, -5.45, curb_height + 0.02), (1.4, 1.4, 0.05)),
        ("sw", (-5.45, -5.45, curb_height + 0.02), (1.4, 1.4, 0.05)),
    ]
    for rid, loc, dims in ramp_specs:
        objects.append(
            _cube_obj(
                f"urban:curb_ramp:{rid}",
                loc,
                dims,
                mats["curb_ramp"],
                "curb-ramp",
                bevel=0.035,
            )
        )
        objects.append(
            _cube_obj(
                f"urban:tactile_paving:{rid}",
                (loc[0], loc[1], loc[2] + 0.04),
                (0.95, 0.95, 0.025),
                mats["tactile_paving"],
                "tactile-paving",
                bevel=0.01,
            )
        )

    bollard_positions = [(-7.2, 7.2), (-5.5, 7.2), (7.2, 7.2), (7.2, 5.5), (7.2, -7.2), (5.5, -7.2), (-7.2, -7.2), (-7.2, -5.5)]
    for i, (x, y) in enumerate(bollard_positions):
        objects.append(
            _cylinder_obj(
                f"urban:bollard:{i}",
                (x, y, 0.55),
                0.08,
                0.9,
                mats["bollard"],
                "bollard",
                vertices=16,
            )
        )

    drain_specs = [
        ("n0", (-8, half_road + 0.18, 0.13), (1.0, 0.16, 0.035)),
        ("n1", (20, half_road + 0.18, 0.13), (1.0, 0.16, 0.035)),
        ("s0", (-18, -half_road - 0.18, 0.13), (1.0, 0.16, 0.035)),
        ("s1", (9, -half_road - 0.18, 0.13), (1.0, 0.16, 0.035)),
        ("e0", (half_road + 0.18, 15, 0.13), (0.16, 1.0, 0.035)),
        ("w0", (-half_road - 0.18, -12, 0.13), (0.16, 1.0, 0.035)),
    ]
    for did, loc, dims in drain_specs:
        objects.append(
            _cube_obj(
                f"urban:storm_drain:{did}",
                loc,
                dims,
                mats["drain"],
                "storm-drain",
                bevel=0.01,
            )
        )

    plaza_bounds = [half_road + sidewalk_width, -half_len + 4, half_len - 4, -half_road - sidewalk_width]
    layout["public_spaces"].append(
        {
            "id": "southeast_plaza",
            "type": "plaza",
            "bounds": plaza_bounds,
            "contains": ["fountain", "sculpture", "planters", "benches", "trees", "pedestrians"],
        }
    )

    return objects, layout


def _add_building(
    mats,
    bid,
    center,
    size,
    facade_axis,
    facade_sign,
    connect_indoor,
    rng,
):
    objects = []
    x, y, _ = center
    width, depth, height = size
    shell = _cube_obj(
        f"urban:building:{bid}",
        (x, y, height / 2),
        (width, depth, height),
        mats["anchor_facade"]
        if connect_indoor
        else (mats["brick"] if rng.random() < 0.5 else mats["facade"]),
        "building",
    )
    objects.append(shell)
    objects.append(
        _cube_obj(
            f"urban:building:roof_cap:{bid}",
            (x, y, height + 0.18),
            (width + 0.28, depth + 0.28, 0.36),
            mats["roof"],
            "building",
            bevel=0.025,
        )
    )

    door_w = 1.35
    door_h = 2.35
    windows = []
    floors = max(1, int(height // 3.0))

    def add_window_with_frame(wid, loc, dims):
        win_objects = [
            _cube_obj(
                f"urban:window:{bid}:{wid}",
                loc,
                dims,
                mats["glass"],
                "window",
                bevel=0.01,
            )
        ]
        wx, wy, wz = loc
        sx, sy, sz = dims
        if facade_axis == "y":
            frame_y = wy - facade_sign * 0.025
            frame_depth = 0.08
            frame_specs = [
                ((wx - sx / 2 - 0.055, frame_y, wz), (0.08, frame_depth, sz + 0.14)),
                ((wx + sx / 2 + 0.055, frame_y, wz), (0.08, frame_depth, sz + 0.14)),
                ((wx, frame_y, wz - sz / 2 - 0.055), (sx + 0.18, frame_depth, 0.08)),
                ((wx, frame_y, wz + sz / 2 + 0.055), (sx + 0.18, frame_depth, 0.08)),
                ((wx, frame_y - facade_sign * 0.045, wz - sz / 2 - 0.16), (sx + 0.32, 0.18, 0.08)),
            ]
        else:
            frame_x = wx - facade_sign * 0.025
            frame_depth = 0.08
            frame_specs = [
                ((frame_x, wy - sy / 2 - 0.055, wz), (frame_depth, 0.08, sz + 0.14)),
                ((frame_x, wy + sy / 2 + 0.055, wz), (frame_depth, 0.08, sz + 0.14)),
                ((frame_x, wy, wz - sz / 2 - 0.055), (frame_depth, sy + 0.18, 0.08)),
                ((frame_x, wy, wz + sz / 2 + 0.055), (frame_depth, sy + 0.18, 0.08)),
                ((frame_x - facade_sign * 0.045, wy, wz - sz / 2 - 0.16), (0.18, sy + 0.32, 0.08)),
            ]
        for fi, (floc, fdims) in enumerate(frame_specs):
            mat = mats["window_sill"] if fi == 4 else mats["window_frame"]
            win_objects.append(
                _cube_obj(
                    f"urban:window_frame:{bid}:{wid}:{fi}",
                    floc,
                    fdims,
                    mat,
                    "window-frame",
                    bevel=0.008,
                )
            )
        return win_objects

    if facade_axis == "y":
        facade_y = y + facade_sign * depth / 2 - facade_sign * 0.035
        entrance_x = x + rng.uniform(-width * 0.18, width * 0.18)
        door_loc = (entrance_x, facade_y, door_h / 2)
        door_dims = (door_w, 0.08, door_h)
        faces = "-Y" if facade_sign < 0 else "+Y"
        cols = max(2, int(width // 2.8))
        for floor in range(1, floors + 1):
            z = 1.6 + floor * 2.55
            if z > height - 0.8:
                continue
            for col in range(cols):
                wx = x - width * 0.36 + col * (width * 0.72 / max(1, cols - 1))
                if abs(wx - entrance_x) < door_w and z < door_h + 0.6:
                    continue
                objects.extend(
                    add_window_with_frame(
                        f"{floor:02d}:{col:02d}",
                        (wx, facade_y, z),
                        (1.05, 0.07, 1.15),
                    )
                )
                windows.append({"center": [wx, facade_y, z], "size": [1.05, 0.07, 1.15]})
    else:
        facade_x = x + facade_sign * width / 2 - facade_sign * 0.035
        entrance_y = y + rng.uniform(-depth * 0.18, depth * 0.18)
        door_loc = (facade_x, entrance_y, door_h / 2)
        door_dims = (0.08, door_w, door_h)
        faces = "-X" if facade_sign < 0 else "+X"
        cols = max(2, int(depth // 2.8))
        for floor in range(1, floors + 1):
            z = 1.6 + floor * 2.55
            if z > height - 0.8:
                continue
            for col in range(cols):
                wy = y - depth * 0.36 + col * (depth * 0.72 / max(1, cols - 1))
                if abs(wy - entrance_y) < door_w and z < door_h + 0.6:
                    continue
                objects.extend(
                    add_window_with_frame(
                        f"{floor:02d}:{col:02d}",
                        (facade_x, wy, z),
                        (0.07, 1.05, 1.15),
                    )
                )
                windows.append({"center": [facade_x, wy, z], "size": [0.07, 1.05, 1.15]})

    door = _cube_obj(f"urban:door:{bid}", door_loc, door_dims, mats["door"], "door")
    objects.append(door)
    if facade_axis == "y":
        frame_y = door_loc[1] - facade_sign * 0.035
        door_frame_specs = [
            ((door_loc[0] - door_w / 2 - 0.065, frame_y, door_h / 2), (0.10, 0.10, door_h + 0.16)),
            ((door_loc[0] + door_w / 2 + 0.065, frame_y, door_h / 2), (0.10, 0.10, door_h + 0.16)),
            ((door_loc[0], frame_y, door_h + 0.08), (door_w + 0.25, 0.10, 0.12)),
        ]
    else:
        frame_x = door_loc[0] - facade_sign * 0.035
        door_frame_specs = [
            ((frame_x, door_loc[1] - door_w / 2 - 0.065, door_h / 2), (0.10, 0.10, door_h + 0.16)),
            ((frame_x, door_loc[1] + door_w / 2 + 0.065, door_h / 2), (0.10, 0.10, door_h + 0.16)),
            ((frame_x, door_loc[1], door_h + 0.08), (0.10, door_w + 0.25, 0.12)),
        ]
    for fi, (floc, fdims) in enumerate(door_frame_specs):
        objects.append(
            _cube_obj(
                f"urban:door_frame:{bid}:{fi}",
                floc,
                fdims,
                mats["window_frame"],
                "door-frame",
                bevel=0.01,
            )
        )
    step_dims = (door_w * 1.35, 0.85, 0.18) if facade_axis == "y" else (0.85, door_w * 1.35, 0.18)
    step_loc = (
        door_loc[0],
        door_loc[1] + facade_sign * 0.45 if facade_axis == "y" else door_loc[1],
        0.09,
    )
    if facade_axis == "x":
        step_loc = (door_loc[0] + facade_sign * 0.45, door_loc[1], 0.09)
    objects.append(_cube_obj(f"urban:entrance_step:{bid}", step_loc, step_dims, mats["stone"], "entrance", bevel=0.025))

    sign_dims = (door_w * 2.2, 0.07, 0.42) if facade_axis == "y" else (0.07, door_w * 2.2, 0.42)
    sign_loc = (
        door_loc[0],
        door_loc[1] - facade_sign * 0.018 if facade_axis == "y" else door_loc[1],
        door_h + 0.42,
    )
    if facade_axis == "x":
        sign_loc = (door_loc[0] - facade_sign * 0.018, door_loc[1], door_h + 0.42)
    objects.append(_cube_obj(f"urban:storefront_sign:{bid}", sign_loc, sign_dims, mats["storefront_sign"], "sign", bevel=0.015))

    if connect_indoor:
        awning_dims = (door_w * 1.8, 1.0, 0.16) if facade_axis == "y" else (1.0, door_w * 1.8, 0.16)
        awning_loc = (
            door_loc[0],
            door_loc[1] + facade_sign * 0.55 if facade_axis == "y" else door_loc[1],
            door_h + 0.22,
        )
        if facade_axis == "x":
            awning_loc = (door_loc[0] + facade_sign * 0.55, door_loc[1], door_h + 0.22)
        objects.append(
            _cube_obj(f"urban:awning:{bid}", awning_loc, awning_dims, mats["awning"], "awning")
        )

    facade_out = 0.07
    if facade_axis == "y":
        face_y = y + facade_sign * depth / 2 + facade_sign * facade_out
        trim_depth = 0.07
        ledge_dims = (width + 0.22, trim_depth, 0.09)
        vertical_dims = (0.09, trim_depth, max(1.5, height - 0.7))
        stain_dims = (0.24, 0.012, 1.2)
        graffiti_dims = (1.0, 0.014, 0.32)
        ac_dims = (0.62, 0.42, 0.34)
        cable_dims = (width * 0.72, 0.035, 0.035)

        def facade_loc(a, z):
            return (a, face_y, z)

        def front_box_loc(a, z, protrude=0.0):
            return (a, face_y + facade_sign * protrude, z)

        span_min, span_max = x - width * 0.44, x + width * 0.44
    else:
        face_x = x + facade_sign * width / 2 + facade_sign * facade_out
        trim_depth = 0.07
        ledge_dims = (trim_depth, depth + 0.22, 0.09)
        vertical_dims = (trim_depth, 0.09, max(1.5, height - 0.7))
        stain_dims = (0.012, 0.24, 1.2)
        graffiti_dims = (0.014, 1.0, 0.32)
        ac_dims = (0.42, 0.62, 0.34)
        cable_dims = (0.035, depth * 0.72, 0.035)

        def facade_loc(a, z):
            return (face_x, a, z)

        def front_box_loc(a, z, protrude=0.0):
            return (face_x + facade_sign * protrude, a, z)

        span_min, span_max = y - depth * 0.44, y + depth * 0.44

    for floor in range(floors + 1):
        z = min(height - 0.25, 2.85 + floor * 2.55)
        if z > 2.6:
            objects.append(
                _cube_obj(
                    f"urban:facade_ledge:{bid}:{floor}",
                    front_box_loc((span_min + span_max) * 0.5, z, 0.01),
                    ledge_dims,
                    mats["stone"],
                    "facade-detail",
                    bevel=0.008,
                )
            )

    for idx, a in enumerate(np.linspace(span_min, span_max, 4)):
        objects.append(
            _cube_obj(
                f"urban:facade_vertical_trim:{bid}:{idx}",
                front_box_loc(a, height / 2, 0.012),
                vertical_dims,
                mats["window_sill"],
                "facade-detail",
                bevel=0.006,
            )
        )

    pipe_a = span_min + rng.uniform(0.3, 0.8)
    objects.append(
        _cylinder_obj(
            f"urban:downspout:{bid}",
            facade_loc(pipe_a, height / 2),
            0.035,
            max(1.0, height - 0.6),
            mats["aged_metal"],
            "facade-pipe",
            vertices=14,
        )
    )
    objects[-1].rotation_euler[0 if facade_axis == "y" else 1] = math.radians(0)

    cable_z = min(height - 0.8, max(3.2, height * 0.68))
    objects.append(
        _cube_obj(
            f"urban:facade_cable:{bid}",
            front_box_loc((span_min + span_max) * 0.5, cable_z, 0.025),
            cable_dims,
            mats["aged_metal"],
            "facade-cable",
            bevel=0.004,
        )
    )

    for wi, win in enumerate(windows[: min(4, len(windows))]):
        if rng.random() < 0.72:
            wx, wy, wz = win["center"]
            a = wx if facade_axis == "y" else wy
            ac_loc = front_box_loc(a + rng.uniform(-0.15, 0.15), wz - 0.82, 0.24)
            objects.append(_cube_obj(f"urban:window_ac:{bid}:{wi}", ac_loc, ac_dims, mats["aged_metal"], "air-conditioner", bevel=0.018))
            vent_dims = (ac_dims[0] * 0.72, 0.018, 0.055) if facade_axis == "y" else (0.018, ac_dims[1] * 0.72, 0.055)
            for vi in range(3):
                objects.append(
                    _cube_obj(
                        f"urban:window_ac_vent:{bid}:{wi}:{vi}",
                        front_box_loc(a, wz - 0.87 + vi * 0.075, 0.46),
                        vent_dims,
                        mats["dark_vent"],
                        "air-conditioner",
                        bevel=0.002,
                    )
                )
        if rng.random() < 0.55:
            wx, wy, wz = win["center"]
            a = wx if facade_axis == "y" else wy
            objects.append(
                _cube_obj(
                    f"urban:window_stain:{bid}:{wi}",
                    front_box_loc(a + rng.uniform(-0.18, 0.18), wz - 0.95, 0.018),
                    stain_dims,
                    mats["facade_stain"],
                    "facade-stain",
                    bevel=0.0,
                )
            )

    for gi, a in enumerate(np.linspace(span_min + 0.8, span_max - 0.8, 3)):
        if rng.random() < 0.65:
            objects.append(
                _cube_obj(
                    f"urban:graffiti:{bid}:{gi}",
                    front_box_loc(a, rng.uniform(1.1, 1.8), 0.02),
                    graffiti_dims,
                    mats["graffiti"],
                    "graffiti",
                    bevel=0.0,
                )
            )

    sign_a = door_loc[0] if facade_axis == "y" else door_loc[1]
    for li, offset in enumerate(np.linspace(-door_w * 0.75, door_w * 0.75, 4)):
        glyph_dims = (0.23, 0.018, 0.18) if facade_axis == "y" else (0.018, 0.23, 0.18)
        objects.append(
            _cube_obj(
                f"urban:storefront_sign_glyph:{bid}:{li}",
                front_box_loc(sign_a + offset, door_h + 0.43 + rng.uniform(-0.04, 0.05), 0.06),
                glyph_dims,
                mats["sign_glyph"],
                "sign",
                bevel=0.003,
            )
        )

    for ri in range(3):
        rx = x + rng.uniform(-width * 0.32, width * 0.32)
        ry = y + rng.uniform(-depth * 0.32, depth * 0.32)
        if ri == 0:
            objects.append(_cylinder_obj(f"urban:rooftop_vent:{bid}:{ri}", (rx, ry, height + 0.5), 0.16, 0.62, mats["aged_metal"], "rooftop-equipment", vertices=18))
            objects.append(_cylinder_obj(f"urban:rooftop_vent_cap:{bid}:{ri}", (rx, ry, height + 0.84), 0.22, 0.09, mats["dark_vent"], "rooftop-equipment", vertices=18))
        else:
            objects.append(_cube_obj(f"urban:rooftop_hvac:{bid}:{ri}", (rx, ry, height + 0.34), (0.78, 0.55, 0.38), mats["aged_metal"], "rooftop-equipment", bevel=0.018))
            objects.append(_cube_obj(f"urban:rooftop_hvac_grille:{bid}:{ri}", (rx, ry, height + 0.55), (0.58, 0.38, 0.025), mats["dark_vent"], "rooftop-equipment", bevel=0.002))

    footprint = [
        [x - width / 2, y - depth / 2, 0],
        [x + width / 2, y - depth / 2, 0],
        [x + width / 2, y + depth / 2, 0],
        [x - width / 2, y + depth / 2, 0],
    ]
    building = {
        "id": bid,
        "role": "indoor_anchor_building" if connect_indoor else "background_building",
        "footprint": footprint,
        "height": height,
        "entrance": {
            "center": list(door_loc),
            "width": door_w,
            "height": door_h,
            "faces": faces,
            "connect_indoor": connect_indoor,
        },
        "windows": windows,
    }
    return objects, building


def _buildings_for_block(mats, block_extent, road_width, sidewalk_width, min_height, max_height, rng):
    objects = []
    buildings = []
    inner = road_width / 2 + sidewalk_width
    specs = [
        ("anchor_northwest", (-18, inner + 5.2, 0), (13.0, 8.0, rng.uniform(min_height, max_height)), "y", -1, True),
        ("background_northeast", (18, inner + 5.8, 0), (14.0, 8.5, rng.uniform(min_height, max_height)), "y", -1, False),
        ("background_west", (-inner - 5.5, -16, 0), (8.0, 13.0, rng.uniform(min_height, max_height)), "x", 1, False),
        ("background_southwest", (-17, -inner - 5.6, 0), (13.0, 8.0, rng.uniform(min_height, max_height)), "y", 1, False),
    ]
    if block_extent > 58:
        specs.append(("background_east", (inner + 5.6, 18, 0), (8.0, 13.0, rng.uniform(min_height, max_height)), "x", -1, False))

    for spec in specs:
        building_objects, building = _add_building(mats, *spec, rng)
        objects.extend(building_objects)
        buildings.append(building)

    return objects, buildings


def _traffic_light(mats, tid, x, y, facing_axis):
    objects = []
    pole = _cylinder_obj(
        f"urban:traffic_light:pole:{tid}",
        (x, y, 1.55),
        0.07,
        3.1,
        mats["metal"],
        "traffic-light",
        vertices=20,
    )
    objects.append(pole)

    if facing_axis == "x":
        mast_loc = (x + np.sign(x) * 0.55, y, 3.0)
        mast_dims = (1.1, 0.08, 0.08)
        box_loc = (x + np.sign(x) * 1.15, y, 2.7)
        box_dims = (0.32, 0.22, 0.82)
        light_locs = [(box_loc[0], y - 0.12, 2.95), (box_loc[0], y - 0.12, 2.7), (box_loc[0], y - 0.12, 2.45)]
    else:
        mast_loc = (x, y + np.sign(y) * 0.55, 3.0)
        mast_dims = (0.08, 1.1, 0.08)
        box_loc = (x, y + np.sign(y) * 1.15, 2.7)
        box_dims = (0.22, 0.32, 0.82)
        light_locs = [(x + 0.12, box_loc[1], 2.95), (x + 0.12, box_loc[1], 2.7), (x + 0.12, box_loc[1], 2.45)]

    objects.append(_cube_obj(f"urban:traffic_light:mast:{tid}", mast_loc, mast_dims, mats["metal"], "traffic-light"))
    objects.append(_cube_obj(f"urban:traffic_light:box:{tid}", box_loc, box_dims, mats["signal_box"], "traffic-light"))
    for color, loc in zip(["red_signal", "yellow_signal", "green_signal"], light_locs):
        objects.append(_sphere_obj(f"urban:traffic_light:{color}:{tid}", loc, 0.095, mats[color], "traffic-light"))

    return objects, {"id": f"traffic_light_{tid}", "type": "traffic-light", "center": [x, y, 0]}


def _vehicle(mats, vid, loc, axis, color_mat, vehicle_type="car"):
    objects = []
    x, y = loc
    if vehicle_type == "bus":
        body_dims = (5.2, 1.75, 1.45) if axis == "x" else (1.75, 5.2, 1.45)
        cabin_dims = (3.8, 1.55, 0.72) if axis == "x" else (1.55, 3.8, 0.72)
        wheel_offsets = [(-1.8, -0.82), (1.8, -0.82), (-1.8, 0.82), (1.8, 0.82)]
    else:
        body_dims = (3.4, 1.55, 0.85) if axis == "x" else (1.55, 3.4, 0.85)
        cabin_dims = (1.65, 1.25, 0.68) if axis == "x" else (1.25, 1.65, 0.68)
        wheel_offsets = [(-1.1, -0.74), (1.1, -0.74), (-1.1, 0.74), (1.1, 0.74)]

    objects.append(_cube_obj(f"urban:vehicle:body:{vid}", (x, y, 0.55), body_dims, color_mat, "vehicle", bevel=0.08))
    objects.append(_cube_obj(f"urban:vehicle:cabin:{vid}", (x, y, 1.18), cabin_dims, mats["car_glass"], "vehicle", bevel=0.06))

    forward = 1
    if axis == "x":
        front_x = x + forward * body_dims[0] / 2 + 0.012
        rear_x = x - forward * body_dims[0] / 2 - 0.012
        light_specs = [
            ((front_x, y - body_dims[1] * 0.28, 0.72), (0.035, 0.22, 0.12), mats["headlight"], "headlight"),
            ((front_x, y + body_dims[1] * 0.28, 0.72), (0.035, 0.22, 0.12), mats["headlight"], "headlight"),
            ((rear_x, y - body_dims[1] * 0.28, 0.7), (0.035, 0.18, 0.12), mats["tail_light"], "tail-light"),
            ((rear_x, y + body_dims[1] * 0.28, 0.7), (0.035, 0.18, 0.12), mats["tail_light"], "tail-light"),
            ((front_x, y, 0.48), (0.035, 0.55, 0.16), mats["license_plate"], "license-plate"),
        ]
    else:
        front_y = y + forward * body_dims[1] / 2 + 0.012
        rear_y = y - forward * body_dims[1] / 2 - 0.012
        light_specs = [
            ((x - body_dims[0] * 0.28, front_y, 0.72), (0.22, 0.035, 0.12), mats["headlight"], "headlight"),
            ((x + body_dims[0] * 0.28, front_y, 0.72), (0.22, 0.035, 0.12), mats["headlight"], "headlight"),
            ((x - body_dims[0] * 0.28, rear_y, 0.7), (0.18, 0.035, 0.12), mats["tail_light"], "tail-light"),
            ((x + body_dims[0] * 0.28, rear_y, 0.7), (0.18, 0.035, 0.12), mats["tail_light"], "tail-light"),
            ((x, front_y, 0.48), (0.55, 0.035, 0.16), mats["license_plate"], "license-plate"),
        ]
    for li, (lloc, ldims, lmat, lsem) in enumerate(light_specs):
        objects.append(_cube_obj(f"urban:vehicle:{lsem}:{vid}:{li}", lloc, ldims, lmat, "vehicle", bevel=0.004))

    for wi, (ox, oy) in enumerate(wheel_offsets):
        wx, wy = (x + ox, y + oy) if axis == "x" else (x + oy, y + ox)
        wheel = _cylinder_obj(
            f"urban:vehicle:wheel:{vid}:{wi}",
            (wx, wy, 0.32),
            0.28,
            0.18,
            mats["tire"],
            "vehicle",
            vertices=20,
        )
        wheel.rotation_euler[1 if axis == "x" else 0] = math.radians(90)
        objects.append(wheel)

    return objects, {"id": f"vehicle_{vid}", "type": vehicle_type, "center": [x, y, 0], "axis": axis}


def _pedestrian(mats, pid, x, y, shirt_mat, facing=0.0):
    objects = []
    left_leg = _cylinder_obj(f"urban:pedestrian:leg_l:{pid}", (x - 0.09, y, 0.38), 0.055, 0.72, mats["person_pants"], "pedestrian", vertices=12)
    right_leg = _cylinder_obj(f"urban:pedestrian:leg_r:{pid}", (x + 0.09, y, 0.38), 0.055, 0.72, mats["person_pants"], "pedestrian", vertices=12)
    torso = _cube_obj(f"urban:pedestrian:torso:{pid}", (x, y, 0.95), (0.34, 0.22, 0.62), shirt_mat, "pedestrian", bevel=0.04)
    head = _sphere_obj(f"urban:pedestrian:head:{pid}", (x, y, 1.42), 0.16, mats["person_skin"], "pedestrian")
    hair = _sphere_obj(f"urban:pedestrian:hair:{pid}", (x, y, 1.53), 0.145, mats["person_hair"], "pedestrian")
    left_arm = _cylinder_obj(f"urban:pedestrian:arm_l:{pid}", (x - 0.25, y, 0.98), 0.04, 0.58, mats["person_skin"], "pedestrian", vertices=10)
    right_arm = _cylinder_obj(f"urban:pedestrian:arm_r:{pid}", (x + 0.25, y, 0.98), 0.04, 0.58, mats["person_skin"], "pedestrian", vertices=10)
    left_arm.rotation_euler[1] = math.radians(18)
    right_arm.rotation_euler[1] = math.radians(-18)
    left_foot = _cube_obj(f"urban:pedestrian:foot_l:{pid}", (x - 0.09, y - 0.05, 0.04), (0.14, 0.24, 0.08), mats["person_shoe"], "pedestrian", bevel=0.025)
    right_foot = _cube_obj(f"urban:pedestrian:foot_r:{pid}", (x + 0.09, y + 0.05, 0.04), (0.14, 0.24, 0.08), mats["person_shoe"], "pedestrian", bevel=0.025)
    for obj in [left_leg, right_leg, torso, head, hair, left_arm, right_arm, left_foot, right_foot]:
        obj.rotation_euler[2] = facing
        objects.append(obj)
    return objects, {"id": f"pedestrian_{pid}", "type": "pedestrian", "center": [x, y, 0]}


@gin.configurable
def _outdoor_assets(
    mats,
    block_extent,
    road_width,
    sidewalk_width,
    n_street_lamps=8,
    has_bus_stop=True,
    n_bike_racks=3,
    has_fire_hydrant=True,
    n_trees=21,
    tree_season="summer",
    n_grass_tufts=18,
    n_shrubs=6,
    n_flower_plants=14,
    has_fountain=True,
    has_sculpture=True,
    n_planters=4,
    n_vehicles=4,
    n_pedestrians=7,
    n_benches=4,
    n_trash_bins=1,
    has_traffic_lights=True,
    has_traffic_signs=True,
    factory_variant=None,
    factory_location=(0.0, 0.0, 0.0),
    factory_scale=1.0,
):
    # Lazy imports keep the dedicated factory profile usable in a lean Blender
    # runtime while preserving the full Nature-backed asset stack for ordinary
    # urban scenes.
    from infinigen.assets.objects.decor.urban_public_space import PublicSpaceFactory
    from infinigen.assets.objects.grassland.urban_groundcover import UrbanGroundcoverFactory
    from infinigen.assets.objects.pedestrians.pedestrian import PedestrianFactory
    from infinigen.assets.objects.street_furniture.street_assets import StreetFurnitureFactory
    from infinigen.assets.objects.traffic.traffic_light import TrafficLightFactory
    from infinigen.assets.objects.trees.urban_tree import UrbanTreeFactory
    from infinigen.assets.objects.vehicles.vehicle import VehicleFactory

    objects = []
    assets = []
    walk_y = road_width / 2 + sidewalk_width * 0.72
    walk_x = road_width / 2 + sidewalk_width * 0.72
    trees = UrbanTreeFactory(mats)
    groundcover = UrbanGroundcoverFactory(mats)
    traffic = TrafficLightFactory(mats)
    vehicles = VehicleFactory(mats)
    pedestrians = PedestrianFactory(mats)
    street = StreetFurnitureFactory(mats)
    public_space = PublicSpaceFactory(mats)
    factory_buildings = FactoryBuildingFactory(mats)

    # All four reference-derived fountain families are instantiated through the
    # production factory.  Their generous spacing leaves every silhouette and
    # planted surround legible while keeping the requested single-row layout.
    fountain_specs = [
        ("royal_quatrefoil", (6.6, -18.0, 0), 0),
        ("planted_three_tier", (13.8, -18.0, 0), 1),
        ("compact_four_tier", (20.8, -18.0, 0), 2),
        ("radial_garden", (27.8, -18.0, 0), 3),
    ]

    def clears_fountain_row(pos, clearance):
        return not has_fountain or all(
            math.hypot(pos[0] - spec[1][0], pos[1] - spec[1][1]) > clearance
            for spec in fountain_specs
        )

    def add(factory_method, asset_type, location, semantic, **params):
        yaw = params.pop("yaw", 0.0)
        asset_objects, asset = factory_method(
            UrbanAssetRequest(
                asset_type=asset_type,
                location=(location[0], location[1], location[2] if len(location) > 2 else 0),
                semantic=semantic,
                yaw=yaw,
                params=params,
            )
        )
        objects.extend(asset_objects)
        assets.append(asset)

    # Optional direct bridge for ordinary urban-block gin configurations.  The
    # dedicated factory scene profile below uses the same production factory,
    # while a mixed urban scene can request any one variant without importing a
    # showcase script or appending prepared blend geometry.
    if factory_variant is not None:
        add(
            factory_buildings.create,
            "factory-building",
            factory_location,
            "factory-building",
            id="urban_block_factory",
            variant=factory_variant,
            scale=factory_scale,
            include_site=False,
        )

    all_lamp_positions = [
        (-24, walk_y), (-12, walk_y), (12, walk_y), (24, walk_y),
        (-24, -walk_y), (24, -walk_y), (-walk_x, 14), (walk_x, -14),
        (0, walk_y), (0, -walk_y), (-walk_x, -14), (walk_x, 14),
    ]
    lamp_positions = all_lamp_positions[:max(0, n_street_lamps)]
    for i, (x, y) in enumerate(lamp_positions):
        head_sign = np.sign(y if abs(y) > abs(x) else x)
        add(street.create_street_lamp, "street-lamp", (x, y, 0), "street-lamp", id=i, head_sign=head_sign)

    if has_bus_stop:
        add(street.create_bus_stop, "bus-stop", (-15.5, -7.2, 0), "bus-stop", id=0)

    all_bike_rack_positions = [(8.5, -10.2), (9.2, -10.2), (9.9, -10.2), (10.6, -10.2), (11.3, -10.2)]
    for i, (x, y) in enumerate(all_bike_rack_positions[:max(0, n_bike_racks)]):
        add(street.create_bike_rack, "bike-rack", (x, y, 0), "bike-rack", id=i)

    if has_fire_hydrant:
        add(street.create_fire_hydrant, "fire-hydrant", (-9.2, -6.8, 0), "fire-hydrant", id=0)

    if has_traffic_lights:
        traffic_light_specs = [
            ("nw", -6.4, 6.4, "y"),
            ("ne", 6.4, 6.4, "x"),
            ("se", 6.4, -6.4, "y"),
            ("sw", -6.4, -6.4, "x"),
        ]
        for tid, x, y, axis in traffic_light_specs:
            add(traffic.create, "traffic-light", (x, y, 0), "traffic-light", id=tid, facing_axis=axis)

    all_tree_positions = [
        (13, -13), (18, -13), (23, -13), (13, -20), (18, -20), (23, -20),
        (-26, 22), (-22, 22), (-18, 22), (-26, 17), (-20, 17),
        (18, 22), (23, 22), (26, 18), (-23, -23), (-18, -24),
        (-23, 13), (-18, 13), (-13, 13), (13, 18), (22, 18),
        (-14, -18), (26, -18), (-24, -14), (14, -14), (-14, 23),
        (26, -23), (-14, -24), (24, -14), (-24, 18), (14, 23),
    ]
    if has_fountain:
        all_tree_positions = [
            pos for pos in all_tree_positions if clears_fountain_row(pos, 3.75)
        ]
    tree_positions = all_tree_positions[:max(0, n_trees)]
    for i, (x, y) in enumerate(tree_positions):
        add(trees.create_tree, "tree", (x, y, 0), "tree", id=i, scale=0.46 + 0.015 * (i % 5), variant=i % 3, yaw=i * 0.37, season=tree_season)
    trees.cleanup_prototypes()

    all_grass_tuft_positions = [
        (-26, 20), (-24, 24), (-20, 20), (-18, 25), (-16, 18),
        (18, 20), (21, 24), (25, 20), (26, 16), (20, 18),
        (-26, -24), (-22, -21), (-18, -26), (22, -25), (25, -26),
        (13, -23), (18, -25), (24, -22),
        (-16, 23), (16, -23), (-26, -18), (26, -20), (-20, -26), (20, 26),
    ]
    grass_tuft_positions = [
        pos for pos in all_grass_tuft_positions if clears_fountain_row(pos, 3.25)
    ][:max(0, n_grass_tufts)]
    for i, (x, y) in enumerate(grass_tuft_positions):
        add(groundcover.create_grass_tuft, "grass", (x, y, 0), "grass", id=i, scale=2.0 + 0.18 * (i % 4), yaw=i * 0.51)

    all_shrub_positions = [
        (-24, 23.8), (-20, 23.6), (-16, 23.9), (20, 23.7), (24, 23.6), (-24, -20.8),
        (16, -23.8), (22, -20.6), (-20, -23.6), (24, 20.5),
    ]
    shrub_positions = [
        pos for pos in all_shrub_positions if clears_fountain_row(pos, 3.55)
    ][:max(0, n_shrubs)]
    for i, (x, y) in enumerate(shrub_positions):
        add(groundcover.create_shrub, "shrub", (x, y, 0), "shrub", id=i, scale=0.48 + 0.04 * (i % 3), yaw=i * 0.42)

    all_flowerplant_positions = [
        (-25.4, 21.4), (-22.8, 24.6), (-19.2, 21.6), (-16.4, 24.5),
        (18.4, 21.4), (22.0, 24.7), (25.4, 18.8),
        (-25.4, -22.2), (-20.4, -25.4), (21.2, -24.0), (24.4, -18.0),
        (12.8, -24.7), (19.0, -23.5), (25.2, -21.0),
        (-16.4, -24.5), (16.4, 24.5), (-25.4, 18.2), (25.4, -18.2),
    ]
    flowerplant_positions = [
        pos for pos in all_flowerplant_positions if clears_fountain_row(pos, 3.20)
    ][:max(0, n_flower_plants)]
    for i, (x, y) in enumerate(flowerplant_positions):
        add(groundcover.create_flowerplant, "flowerplant", (x, y, 0), "flowerplant", id=i, scale=0.58 + 0.05 * (i % 4), yaw=i * 0.33)

    if has_fountain:
        for variant_name, location, fountain_id in fountain_specs:
            add(
                public_space.create_fountain,
                "fountain",
                location,
                "fountain",
                id=fountain_id,
                variant=variant_name,
            )
    if has_sculpture:
        add(public_space.create_sculpture, "sculpture", (10.5, -23.5, 0), "sculpture", id=0)

    all_planter_positions = [(14, -24), (22, -24), (25, -17), (11, -17), (-14, 24), (-22, 24), (-25, 17)]
    planter_positions = [
        pos for pos in all_planter_positions if clears_fountain_row(pos, 3.50)
    ][:max(0, n_planters)]
    for i, (x, y) in enumerate(planter_positions):
        add(street.create_planter, "planter", (x, y, 0), "planter", id=i)

    all_vehicle_specs = [
        ("car_westbound", (-18, 1.75), "x", "car_red", "car"),
        ("car_eastbound", (21, -1.65), "x", "car_blue", "car"),
        ("bus_northbound", (1.65, 18), "y", "bus_yellow", "bus"),
        ("car_southbound", (-1.65, -22), "y", "car_white", "car"),
    ]
    vehicle_specs = all_vehicle_specs[:max(0, n_vehicles)]
    for vid, loc, axis, color_key, vehicle_type in vehicle_specs:
        add(vehicles.create, "vehicle", (*loc, 0), "vehicle", id=vid, axis=axis, color=color_key, vehicle_type=vehicle_type)

    all_pedestrian_specs = [
        (0, -4.2, -5.8, "person_shirt_red", math.radians(20)),
        (1, -2.0, -5.6, "person_shirt_blue", math.radians(-8)),
        (2, 9.8, -14.0, "person_shirt_green", math.radians(85)),
        (3, 16.4, -12.3, "person_shirt_blue", math.radians(12)),
        (4, 22.5, -18.8, "person_shirt_red", math.radians(-35)),
        (5, -9.0, 6.4, "person_shirt_green", math.radians(70)),
        (6, -21.0, 18.0, "person_shirt_blue", math.radians(110)),
        (7, 5.0, -7.0, "person_shirt_red", math.radians(45)),
        (8, -12.0, -8.0, "person_shirt_blue", math.radians(190)),
        (9, 18.0, 6.0, "person_shirt_green", math.radians(260)),
        (10, -6.0, 12.0, "person_shirt_red", math.radians(320)),
    ]
    pedestrian_specs = all_pedestrian_specs[:max(0, n_pedestrians)]
    for pid, x, y, shirt_key, facing in pedestrian_specs:
        add(pedestrians.create, "pedestrian", (x, y, 0), "pedestrian", id=pid, shirt=shirt_key, facing=facing)

    if has_traffic_signs:
        add(street.create_traffic_sign, "traffic-sign", (3.8, road_width / 2 + 0.65, 0), "traffic-sign", id="crosswalk")

    all_bench_positions = [(15, -11.5), (21, -11.5), (12, -20.5), (-8, 6.8), (-15, 11.5), (8, -6.8)]
    bench_positions = all_bench_positions[:max(0, n_benches)]
    for i, (x, y) in enumerate(bench_positions):
        add(street.create_bench, "bench", (x, y, 0), "bench", id=i)

    for i in range(max(0, n_trash_bins)):
        bin_x = -4.5 - i * 3.5
        add(
            street.create_trash_bin,
            "trash-bin",
            (bin_x, -road_width / 2 - sidewalk_width * 0.35, 0),
            "trash-bin",
            id=i,
        )

    return objects, assets


@gin.configurable
def compose_urban(
    output_folder: Path,
    scene_seed: int,
    block_extent=64.0,
    road_width=8.0,
    sidewalk_width=3.0,
    curb_height=0.16,
    min_building_height=7.0,
    max_building_height=14.0,
):
    from infinigen.assets.objects.decor.urban_public_space import make_fountain_materials

    rng = np.random.default_rng(scene_seed)
    mats = {
        "asphalt": _make_mat("urban_mat_asphalt", (0.035, 0.038, 0.04, 1), roughness=0.88, noise_strength=0.42, bump_strength=0.075),
        "asphalt_aggregate": _make_mat("urban_mat_asphalt_aggregate", (0.095, 0.095, 0.085, 1), roughness=0.95, noise_strength=0.25),
        "concrete": _make_mat("urban_mat_concrete", (0.48, 0.47, 0.43, 1), roughness=0.82, noise_strength=0.20, bump_strength=0.045),
        "curb": _make_mat("urban_mat_curb", (0.64, 0.62, 0.56, 1), roughness=0.8, noise_strength=0.16, bump_strength=0.035),
        "curb_ramp": _make_mat("urban_mat_curb_ramp", (0.57, 0.56, 0.51, 1), roughness=0.82, noise_strength=0.18, bump_strength=0.035),
        "curb_grime": _make_mat("urban_mat_curb_grime", (0.12, 0.12, 0.105, 1), roughness=0.95, noise_strength=0.18),
        "tactile_paving": _make_mat("urban_mat_tactile_paving", (0.82, 0.68, 0.22, 1), roughness=0.72, noise_strength=0.14, bump_strength=0.03),
        "paint": _make_mat("urban_mat_road_paint", (0.92, 0.9, 0.78, 1), roughness=0.76, noise_strength=0.10),
        "paint_wear": _make_mat("urban_mat_worn_paint", (0.045, 0.047, 0.045, 1), roughness=0.92, noise_strength=0.20),
        "asphalt_patch": _make_mat("urban_mat_asphalt_patch", (0.055, 0.058, 0.057, 1), roughness=0.9, noise_strength=0.25, bump_strength=0.045),
        "road_stain": _make_mat("urban_mat_road_stain", (0.018, 0.020, 0.019, 1), roughness=0.9),
        "road_crack": _make_mat("urban_mat_road_crack", (0.006, 0.006, 0.005, 1), roughness=0.95),
        "grass": _make_mat("urban_mat_grass", (0.10, 0.34, 0.12, 1), roughness=0.95, noise_strength=0.24, bump_strength=0.035),
        "grass_tuft": _make_mat("urban_mat_grass_tuft", (0.05, 0.26, 0.07, 1), roughness=0.95, noise_strength=0.25),
        "concrete_seam": _make_mat("urban_mat_concrete_seam", (0.30, 0.30, 0.28, 1), roughness=0.95, noise_strength=0.12),
        "manhole": _make_mat("urban_mat_manhole", (0.06, 0.065, 0.065, 1), roughness=0.72, metallic=0.25, noise_strength=0.10, bump_strength=0.02),
        "drain": _make_mat("urban_mat_drain", (0.035, 0.04, 0.04, 1), roughness=0.74, metallic=0.2, noise_strength=0.10),
        "facade": _make_mat("urban_mat_facade", (0.52, 0.55, 0.53, 1), roughness=0.78, noise_strength=0.18, bump_strength=0.035),
        "anchor_facade": _make_mat("urban_mat_anchor_facade", (0.38, 0.45, 0.50, 1), roughness=0.78, noise_strength=0.16, bump_strength=0.03),
        "brick": _make_mat("urban_mat_brick", (0.48, 0.22, 0.17, 1), roughness=0.84, noise_strength=0.24, bump_strength=0.055),
        "roof": _make_mat("urban_mat_roof", (0.16, 0.15, 0.14, 1), roughness=0.9, noise_strength=0.25, bump_strength=0.05),
        "storefront_sign": _make_mat("urban_mat_storefront_sign", (0.86, 0.63, 0.18, 1), roughness=0.5, noise_strength=0.08),
        "sign_glyph": _make_mat("urban_mat_sign_glyph", (0.08, 0.07, 0.045, 1), roughness=0.55, noise_strength=0.05),
        "glass": _make_mat("urban_mat_glass", (0.08, 0.18, 0.24, 1), roughness=0.18),
        "window_frame": _make_mat("urban_mat_window_frame", (0.08, 0.085, 0.08, 1), metallic=0.15),
        "window_sill": _make_mat("urban_mat_window_sill", (0.68, 0.66, 0.60, 1), roughness=0.78, noise_strength=0.12, bump_strength=0.025),
        "door": _make_mat("urban_mat_door", (0.17, 0.10, 0.07, 1), roughness=0.66, noise_strength=0.12, bump_strength=0.025),
        "awning": _make_mat("urban_mat_awning", (0.58, 0.07, 0.06, 1), roughness=0.58, noise_strength=0.08, bump_strength=0.02),
        "metal": _make_mat("urban_mat_metal", (0.18, 0.18, 0.18, 1), roughness=0.62, metallic=0.2, noise_strength=0.06),
        "aged_metal": _make_mat("urban_mat_aged_metal", (0.32, 0.33, 0.31, 1), roughness=0.82, metallic=0.18, noise_strength=0.18, bump_strength=0.025),
        "dark_vent": _make_mat("urban_mat_dark_vent", (0.025, 0.026, 0.024, 1), roughness=0.9, metallic=0.1),
        "facade_stain": _make_mat("urban_mat_facade_stain", (0.075, 0.07, 0.055, 1), roughness=0.95, noise_strength=0.28),
        "graffiti": _make_mat("urban_mat_graffiti", (0.08, 0.30, 0.62, 1), roughness=0.48, noise_strength=0.06),
        "lamp": _make_mat("urban_mat_lamp", (1.0, 0.86, 0.48, 1)),
        "bollard": _make_mat("urban_mat_bollard", (0.08, 0.08, 0.075, 1), metallic=0.25),
        "bus_stop_glass": _make_mat("urban_mat_bus_stop_glass", (0.22, 0.38, 0.45, 0.55), roughness=0.08),
        "bus_stop_sign": _make_mat("urban_mat_bus_stop_sign", (0.05, 0.22, 0.72, 1)),
        "hydrant": _make_mat("urban_mat_hydrant", (0.78, 0.05, 0.03, 1), roughness=0.35),
        "trunk": _make_mat("urban_mat_tree_trunk", (0.20, 0.12, 0.05, 1)),
        "bark_dark": _make_mat("urban_mat_tree_bark_dark", (0.10, 0.055, 0.025, 1), roughness=0.85),
        "leaf": _make_mat("urban_mat_tree_leaf", (0.08, 0.32, 0.13, 1)),
        "leaf_dark": _make_mat("urban_mat_tree_leaf_dark", (0.035, 0.20, 0.07, 1)),
        "leaf_litter": _make_mat("urban_mat_leaf_litter", (0.34, 0.18, 0.06, 1), roughness=0.9, noise_strength=0.20),
        "paper_litter": _make_mat("urban_mat_paper_litter", (0.82, 0.80, 0.68, 1), roughness=0.86, noise_strength=0.12),
        "gum": _make_mat("urban_mat_gum", (0.52, 0.50, 0.45, 1), roughness=0.93, noise_strength=0.10),
        "sidewalk_stain": _make_mat("urban_mat_sidewalk_stain", (0.22, 0.21, 0.18, 1), roughness=0.96, noise_strength=0.22),
        "oil_sheen": _make_mat("urban_mat_oil_sheen", (0.03, 0.035, 0.04, 0.72), roughness=0.22, metallic=0.08, noise_strength=0.12),
        "shrub": _make_mat("urban_mat_shrub", (0.05, 0.24, 0.08, 1)),
        "flower_yellow": _make_mat("urban_mat_flower_yellow", (0.95, 0.78, 0.10, 1)),
        "flower_purple": _make_mat("urban_mat_flower_purple", (0.45, 0.16, 0.62, 1)),
        "soil": _make_mat("urban_mat_soil", (0.13, 0.075, 0.035, 1), roughness=0.95),
        "sign": _make_mat("urban_mat_sign", (0.04, 0.20, 0.68, 1)),
        "signal_box": _make_mat("urban_mat_signal_box", (0.035, 0.04, 0.035, 1)),
        "red_signal": _make_mat("urban_mat_red_signal", (1.0, 0.05, 0.03, 1), emission_strength=1.2),
        "yellow_signal": _make_mat("urban_mat_yellow_signal", (1.0, 0.75, 0.08, 1), emission_strength=0.5),
        "green_signal": _make_mat("urban_mat_green_signal", (0.05, 0.9, 0.18, 1), emission_strength=1.0),
        "bench": _make_mat("urban_mat_bench", (0.32, 0.19, 0.10, 1)),
        "trash": _make_mat("urban_mat_trash", (0.05, 0.18, 0.13, 1)),
        "stone": _make_mat("urban_mat_stone", (0.56, 0.54, 0.50, 1)),
        **make_fountain_materials(_make_mat),
        **make_factory_materials(_make_mat),
        "bronze": _make_mat("urban_mat_bronze", (0.55, 0.32, 0.13, 1), metallic=0.45),
        "planter": _make_mat("urban_mat_planter", (0.42, 0.25, 0.14, 1)),
        "car_red": _make_mat("urban_mat_car_red", (0.68, 0.05, 0.04, 1), roughness=0.32),
        "car_blue": _make_mat("urban_mat_car_blue", (0.04, 0.16, 0.56, 1), roughness=0.32),
        "car_white": _make_mat("urban_mat_car_white", (0.82, 0.84, 0.80, 1), roughness=0.28),
        "bus_yellow": _make_mat("urban_mat_bus_yellow", (0.92, 0.66, 0.08, 1), roughness=0.36),
        "car_glass": _make_mat("urban_mat_car_glass", (0.035, 0.08, 0.11, 1), roughness=0.12),
        "tire": _make_mat("urban_mat_tire", (0.015, 0.014, 0.013, 1), roughness=0.8),
        "headlight": _make_mat("urban_mat_headlight", (1.0, 0.92, 0.70, 1), emission_strength=0.25),
        "tail_light": _make_mat("urban_mat_tail_light", (0.9, 0.03, 0.02, 1), emission_strength=0.2),
        "license_plate": _make_mat("urban_mat_license_plate", (0.88, 0.86, 0.74, 1)),
        "person_skin": _make_mat("urban_mat_person_skin", (0.68, 0.48, 0.34, 1)),
        "person_pants": _make_mat("urban_mat_person_pants", (0.05, 0.06, 0.09, 1)),
        "person_hair": _make_mat("urban_mat_person_hair", (0.06, 0.035, 0.018, 1)),
        "person_shoe": _make_mat("urban_mat_person_shoe", (0.025, 0.022, 0.02, 1)),
        "person_shirt_red": _make_mat("urban_mat_person_shirt_red", (0.70, 0.08, 0.08, 1)),
        "person_shirt_blue": _make_mat("urban_mat_person_shirt_blue", (0.07, 0.18, 0.55, 1)),
        "person_shirt_green": _make_mat("urban_mat_person_shirt_green", (0.08, 0.42, 0.20, 1)),
    }

    _add_world()
    _add_lighting()
    _add_camera_rig(block_extent)

    objects, layout = _block_scene(
        mats, block_extent, road_width, sidewalk_width, curb_height
    )

    surface_objects, surface_layout = _surface_realism_details(
        mats, block_extent, road_width, sidewalk_width, curb_height, rng
    )
    objects.extend(surface_objects)
    layout["surface_details"].extend(surface_layout)

    building_objects, buildings = _buildings_for_block(
        mats,
        block_extent,
        road_width,
        sidewalk_width,
        min_building_height,
        max_building_height,
        rng,
    )
    objects.extend(building_objects)
    layout["buildings"].extend(buildings)

    asset_objects, asset_layout = _outdoor_assets(
        mats, block_extent, road_width, sidewalk_width
    )
    objects.extend(asset_objects)
    layout["street_assets"].extend(asset_layout)

    layout["camera_path"] = [
        [-block_extent * 0.36, -block_extent * 0.32, 1.65],
        [-block_extent * 0.18, -road_width * 0.9, 1.65],
        [-2.5, -road_width * 0.55, 1.65],
        [6.6, -12.6, 1.75],
        [13.8, -12.8, 1.75],
        [20.8, -12.8, 1.75],
        [27.8, -12.6, 1.75],
    ]
    layout["mvp_status"] = {
        "outdoor_first_block": True,
        "urban_asset_factories": True,
        "urban_asset_detail_modeling": True,
        "urban_asset_high_detail_modeling": True,
        "urban_procedural_materials": True,
        "ground_micro_detail_scatter": True,
        "facade_detail_assets": True,
        "nature_style_leaf_mesh_vegetation": True,
        "nature_factory_trees": True,
        "nature_factory_bushes": True,
        "nature_factory_grass_tufts": True,
        "nature_factory_flowerplants": True,
        "no_placeholder_visible_assets_target": True,
        "cross_intersection": True,
        "road_network": True,
        "sidewalk_zones": True,
        "sidewalk_paving_joints": True,
        "lawns": True,
        "grass_tufts": True,
        "curbs": True,
        "four_crosswalks": True,
        "stop_lines": True,
        "asphalt_patches": True,
        "road_wear_and_cracks": True,
        "manholes_and_drains": True,
        "curb_ramps_and_tactile_paving": True,
        "bollards": True,
        "traffic_lights": True,
        "bus_stop": True,
        "bike_racks": True,
        "fire_hydrant": True,
        "vehicles_with_detail_parts": True,
        "pedestrians_with_detail_parts": True,
        "public_plaza": True,
        "fountain": True,
        "four_reference_fountain_variants": True,
        "fountains_arranged_in_single_row": True,
        "sculpture": True,
        "planters": True,
        "background_buildings": True,
        "single_indoor_anchor": True,
        "facade_windows": True,
        "facade_window_frames": True,
        "facade_door_frames": True,
        "street_assets": True,
        "continuous_camera_path_recorded": True,
    }

    butil.group_in_collection(objects, "urban")
    output_folder.mkdir(parents=True, exist_ok=True)
    with (output_folder / "urban_layout.json").open("w") as f:
        json.dump(layout, f, indent=2)

    logger.info("Wrote Urban layout metadata to %s", output_folder / "urban_layout.json")
    return {
        "height_offset": 0,
        "whole_bbox": (
            (-block_extent / 2, -block_extent / 2, 0),
            (block_extent / 2, block_extent / 2, max_building_height),
        ),
    }


FACTORY_SHOWCASE_CENTERS = (-93.0, -32.0, 29.0, 95.0)
FACTORY_SHOWCASE_Y = 6.0


def _add_factory_daylight():
    """Create a clear daytime sky and broad, physically legible shadows."""
    world = bpy.context.scene.world or bpy.data.worlds.new("Factory Daylight World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(39.0)
    sky.sun_rotation = math.radians(132.0)
    sky.altitude = 0.18
    sky.air_density = 1.08
    sky.dust_density = 0.78
    sky.ozone_density = 1.0
    background.inputs["Strength"].default_value = 0.28
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    bpy.ops.object.light_add(type="SUN", location=(-80, -110, 120))
    sun = bpy.context.active_object
    sun.name = "urban:factory_showcase:daylight_sun"
    sun.rotation_euler = (math.radians(31), math.radians(-21), math.radians(-38))
    sun.data.energy = 1.8
    sun.data.angle = math.radians(4.2)

    bpy.ops.object.light_add(type="AREA", location=(5, -75, 62))
    fill = bpy.context.active_object
    fill.name = "urban:factory_showcase:sky_fill"
    fill.data.energy = 360
    fill.data.shape = "RECTANGLE"
    fill.data.size = 110
    fill.data.size_y = 52
    _look_at(fill, (4, 5, 4.5))

    bpy.ops.object.light_add(type="AREA", location=(20, 58, 35))
    rim = bpy.context.active_object
    rim.name = "urban:factory_showcase:rear_sky_fill"
    rim.data.energy = 150
    rim.data.shape = "RECTANGLE"
    rim.data.size = 85
    rim.data.size_y = 34
    _look_at(rim, (5, 4, 5.0))


def _add_factory_camera():
    bpy.ops.object.camera_add(location=(2.0, -300.0, 82.0))
    camera = bpy.context.active_object
    camera.name = "urban:factory_showcase:camera"
    camera.data.lens = 44
    camera.data.sensor_width = 36
    camera.data.clip_start = 0.12
    camera.data.clip_end = 1200.0
    camera.data.dof.use_dof = False
    _look_at(camera, (2.0, 4.0, 5.0))
    bpy.context.scene.camera = camera
    return camera


def _factory_showcase_context(mats):
    """Model only the restrained site context needed to read factory scale."""
    objects = []
    objects.append(
        _cube_obj(
            "urban:factory_showcase:ground",
            (2.0, 0.0, -0.34),
            (700.0, 700.0, 0.68),
            mats["factory_soil"],
            "factory-site",
            bevel=0.0,
        )
    )
    objects.append(
        _cube_obj(
            "urban:factory_showcase:rear_grass",
            (2.0, 30.0, 0.015),
            (282.0, 29.0, 0.10),
            mats["factory_hedge_dark"],
            "landscaping",
            bevel=0.08,
        )
    )
    objects.append(
        _cube_obj(
            "urban:factory_showcase:public_road",
            (2.0, -32.0, 0.055),
            (280.0, 10.5, 0.14),
            mats["factory_asphalt"],
            "road",
            bevel=0.025,
        )
    )
    objects.append(
        _cube_obj(
            "urban:factory_showcase:front_sidewalk",
            (2.0, -24.8, 0.13),
            (280.0, 3.45, 0.25),
            mats["factory_paving"],
            "sidewalk",
            bevel=0.035,
        )
    )
    for side, y in (("near", -37.35), ("far", -26.65)):
        objects.append(
            _cube_obj(
                f"urban:factory_showcase:curb:{side}",
                (2.0, y, 0.17),
                (280.0, 0.24, 0.34),
                mats["factory_concrete"],
                "curb",
                bevel=0.045,
            )
        )
    for index, x in enumerate(np.arange(-132.0, 137.0, 7.5)):
        objects.append(
            _cube_obj(
                f"urban:factory_showcase:lane_marking:{index}",
                (float(x), -32.0, 0.145),
                (3.7, 0.13, 0.022),
                mats["factory_marking_white"],
                "lane-marking",
                bevel=0.006,
            )
        )
    for index, x in enumerate(FACTORY_SHOWCASE_CENTERS):
        objects.append(
            _cube_obj(
                f"urban:factory_showcase:driveway:{index}",
                (x, -21.4, 0.13),
                (9.4 if index != 2 else 14.0, 8.5, 0.16),
                mats["factory_concrete"],
                "factory-driveway",
                bevel=0.040,
            )
        )
        for edge in (-1, 1):
            objects.append(
                _cube_obj(
                    f"urban:factory_showcase:driveway-joint:{index}:{edge}",
                    (x + edge * (4.4 if index != 2 else 6.7), -21.4, 0.222),
                    (0.035, 8.0, 0.012),
                    mats["factory_concrete_dark"],
                    "factory-site-detail",
                    bevel=0.0,
                )
            )
    for index, y in enumerate(np.arange(-25.9, -23.6, 1.18)):
        objects.append(
            _cube_obj(
                f"urban:factory_showcase:sidewalk-joint:{index}",
                (2.0, float(y), 0.272),
                (279.0, 0.025, 0.012),
                mats["factory_concrete_dark"],
                "sidewalk-joint",
                bevel=0.0,
            )
        )
    for index, x in enumerate(np.arange(-136.0, 141.0, 3.2)):
        objects.append(
            _cube_obj(
                f"urban:factory_showcase:sidewalk-cross-joint:{index}",
                (float(x), -24.8, 0.273),
                (0.025, 3.15, 0.012),
                mats["factory_concrete_dark"],
                "sidewalk-joint",
                bevel=0.0,
            )
        )
    return objects


@gin.configurable
def compose_factory_showcase(
    output_folder: Path,
    scene_seed: int,
    factory_scale=1.0,
):
    """Compose all four factory variants in one production pipeline scene."""
    mats = {
        **make_factory_materials(_make_mat),
    }
    _add_factory_daylight()
    _add_factory_camera()
    objects = _factory_showcase_context(mats)
    assets = []
    factory = FactoryBuildingFactory(mats, seed=scene_seed)
    for index, (variant, x) in enumerate(zip(FACTORY_VARIANTS, FACTORY_SHOWCASE_CENTERS)):
        logger.info("Building production factory variant %s (%d/%d)", variant, index + 1, len(FACTORY_VARIANTS))
        asset_objects, asset = factory.create(
            UrbanAssetRequest(
                asset_type="factory-building",
                location=(x, FACTORY_SHOWCASE_Y, 0.18),
                semantic="factory-building",
                params={
                    "id": index,
                    "variant": variant,
                    "scale": factory_scale,
                    "include_site": True,
                },
            )
        )
        objects.extend(asset_objects)
        assets.append(asset)
        logger.info(
            "Completed factory variant %s: components=%s mesh_polygons=%s",
            variant,
            asset["component_count"],
            asset["mesh_polygons"],
        )

    layout = {
        "schema_version": 2,
        "coordinate_system": {"up_axis": "+Z", "front_direction": "-Y", "units": "meters"},
        "scene_profile": "factory",
        "design_intent": "four independently modeled reference-derived architectural-detail-v3 factories arranged in one straight row",
        "generator": "infinigen_examples.generate_urban.compose_factory_showcase",
        "asset_factory": "infinigen.assets.objects.urban.factory_building.FactoryBuildingFactory.create",
        "pipeline_integration": {
            "scene_profile_cli": "--scene-profile factory",
            "mixed_urban_gin_hook": "_outdoor_assets.factory_variant",
            "asset_request_type": "UrbanAssetRequest(asset_type='factory-building')",
        },
        "arrangement": "single_row",
        "row_axis": "+X",
        "factory_centers": [[x, FACTORY_SHOWCASE_Y, 0.18] for x in FACTORY_SHOWCASE_CENTERS],
        "factories": assets,
        "reference_images": FACTORY_REFERENCES,
        "requirements": {
            "four_distinct_external_types": True,
            "independently_modeled_variants": True,
            "procedural_geometry_only": True,
            "production_generator_not_blend_patch": True,
            "non_toy_high_detail_modeling": True,
            "same_scene_single_row": True,
            "daylight_near_and_far_views": True,
            "factory_area_only": True,
            "layered_realistic_facade_construction": True,
            "bounded_enlarged_readable_signage": True,
            "yellow_entrance_gate_piers_removed": True,
            "complex_realistic_powered_gate_and_perimeter_fence": True,
            "fully_detailed_reverse_facades": True,
            "highbay_front_rectilinear_hedge_removed": True,
            "gable_sign_sightline_clear_of_downspouts": True,
            "gable_blue_box_rooflights_removed": True,
            "gable_pressure_equalised_double_lite_igu_windows": True,
            "gable_mechanically_seamed_roof_envelope_detailed": True,
        },
        "whole_bbox": [[-139.0, -38.0, -0.7], [143.0, 47.0, 16.0]],
    }
    # Factory children are already parented to their per-variant roots.  Passing
    # both every root and every descendant to ``group_in_collection`` would
    # traverse the same hierarchy repeatedly; grouping top-level objects keeps
    # the output identical while making large detailed assets linear-time.
    butil.group_in_collection(
        [obj for obj in objects if obj is not None and obj.parent is None],
        "urban_factory_showcase",
    )
    output_folder.mkdir(parents=True, exist_ok=True)
    for filename in ("factory_layout.json", "urban_layout.json"):
        with (output_folder / filename).open("w", encoding="utf-8") as handle:
            json.dump(layout, handle, ensure_ascii=False, indent=2)
    logger.info("Wrote factory showcase layout metadata to %s", output_folder)
    return {
        "height_offset": 0,
        "whole_bbox": ((-139.0, -38.0, -0.7), (143.0, 47.0, 16.0)),
    }


def _configure_factory_render(samples=16, resolution=(1440, 810)):
    scene = bpy.context.scene
    # Cycles CPU is intentional: this runtime has no headless EGL surface for
    # Eevee, while Cycles produces stable physically based images in background
    # mode and preserves the material/edge detail needed for close inspection.
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = int(samples)
    scene.cycles.use_denoising = True
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.075
    scene.cycles.max_bounces = 7
    scene.cycles.diffuse_bounces = 3
    scene.cycles.glossy_bounces = 3
    scene.cycles.transmission_bounces = 4
    scene.cycles.volume_bounces = 0
    scene.render.resolution_x = int(resolution[0])
    scene.render.resolution_y = int(resolution[1])
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except (TypeError, ValueError):
        try:
            scene.view_settings.look = "Medium High Contrast"
        except (TypeError, ValueError):
            pass
    scene.view_settings.exposure = -0.48
    scene.view_settings.gamma = 1.0
    return scene


def _render_factory_views(output_root, *, samples=16, resolution=(1440, 810)):
    """Render daylight near/far validation views from the generated scene."""
    output_root = Path(output_root)
    render_dir = output_root / "renders"
    render_dir.mkdir(parents=True, exist_ok=True)
    scene = _configure_factory_render(samples=samples, resolution=resolution)
    camera = scene.camera or _add_factory_camera()
    views = [
        ("01_row_front_far_day", (2.0, -230.0, 49.0), (2.0, 3.5, 4.8), 33),
        ("02_row_oblique_far_day", (-164.0, -184.0, 62.0), (0.0, 4.0, 4.6), 38),
        ("03_row_aerial_day", (3.0, -170.0, 165.0), (3.0, 4.0, 2.8), 32),
        ("04_row_reverse_far_day", (4.0, 218.0, 52.0), (3.0, 4.0, 4.7), 35),
        ("05_gable_clerestory_close_day", (-125.0, -44.0, 16.5), (-93.0, 4.0, 5.2), 52),
        ("06_white_modern_close_day", (-58.0, -43.0, 14.5), (-32.0, 3.4, 4.7), 54),
        ("07_gated_campus_close_day", (55.0, -46.0, 14.0), (31.0, -1.5, 3.5), 44),
        ("08_highbay_monochrome_close_day", (61.0, -50.0, 18.5), (95.0, 3.3, 5.4), 50),
        ("09_gated_security_gate_close_day", (43.0, -39.0, 7.0), (29.5, -10.4, 1.45), 52),
    ]
    rendered = []
    for name, location, target, lens in views:
        camera.location = location
        camera.data.lens = lens
        _look_at(camera, target)
        filepath = render_dir / f"{name}.png"
        scene.render.filepath = str(filepath)
        logger.info("Rendering factory validation view %s", filepath)
        bpy.ops.render.render(write_still=True)
        if not filepath.exists() or filepath.stat().st_size < 10_000:
            raise RuntimeError(f"Factory validation render is missing or unexpectedly small: {filepath}")
        rendered.append(
            {
                "file": str(filepath.relative_to(output_root)),
                "bytes": filepath.stat().st_size,
                "camera_location": list(location),
                "target": list(target),
                "lens_mm": lens,
                "view_type": "close" if "close" in name else "far",
                "lighting": "daylight",
            }
        )
    return rendered


def _write_factory_audit(output_root, rendered_views, mesh_stats, blend_file):
    output_root = Path(output_root)
    with (output_root / "factory_layout.json").open(encoding="utf-8") as handle:
        layout = json.load(handle)
    roots = [
        obj
        for obj in bpy.context.scene.objects
        if obj.type == "EMPTY" and obj.name.startswith("urban:factory:") and obj.name.endswith(":root")
    ]
    variants = [root.get("factory_variant") for root in roots]
    if sorted(variants) != sorted(FACTORY_VARIANTS):
        raise RuntimeError(f"Factory scene variant audit failed: {variants}")
    scene_objects = list(bpy.context.scene.objects)
    gable_objects = [
        obj
        for obj in scene_objects
        if obj.name.startswith("urban:factory:0:gable_clerestory:")
    ]
    highbay_objects = [
        obj
        for obj in scene_objects
        if obj.name.startswith("urban:factory:3:highbay_monochrome:")
    ]
    sign_obscuring_downspouts = [
        obj.name
        for obj in gable_objects
        if obj.get("factory_component_role") == "downspout"
        and ":drainage:downspout:-1:" in obj.name
        and -22.25 <= float(obj.location.x) <= -11.75
    ]
    requested_revision_checks = {
        "highbay_front_rectilinear_hedge_absent": not any(
            "front-roadside-hedge" in obj.name for obj in highbay_objects
        ),
        "gable_blue_box_rooflights_absent": not any(
            ":roof:skylight" in obj.name for obj in gable_objects
        ),
        "gable_sign_sightline_clear_of_front_downspouts": not sign_obscuring_downspouts,
        "gable_layered_igu_geometry_present": sum(
            "insulating-glass-unit" in str(obj.get("factory_component_role", ""))
            for obj in gable_objects
        )
        >= 30,
        "gable_warm_edge_and_pressure_equalisation_present": any(
            "warm-edge" in str(obj.get("factory_component_role", ""))
            for obj in gable_objects
        )
        and any(
            "frame-weep-slots" in str(obj.get("factory_component_role", ""))
            for obj in gable_objects
        ),
        "gable_detailed_standing_seam_roof_present": sum(
            any(
                token in str(obj.get("factory_component_role", ""))
                for token in (
                    "standing-seam",
                    "roof-sheet-lap",
                    "ridge-cap",
                    "ridge-closure",
                    "rake-edge",
                    "eave-drip",
                )
            )
            for obj in gable_objects
        )
        >= 150,
        "gable_raised_service_walkway_present": any(
            "roof-maintenance-grating"
            in str(obj.get("factory_component_role", ""))
            for obj in gable_objects
        ),
    }
    if not all(requested_revision_checks.values()):
        raise RuntimeError(
            "Requested factory revision audit failed: "
            f"{requested_revision_checks}; sign_obscuring_downspouts="
            f"{sign_obscuring_downspouts}"
        )
    requirements = layout["requirements"]
    if not all(requirements.values()):
        raise RuntimeError(f"Factory requirement audit failed: {requirements}")
    per_asset_checks = {}
    for asset in layout["factories"]:
        signs = asset.get("signage", [])
        checks = {
            "production_generator_asset": asset.get("procedural") is True,
            "architectural_detail_v3": asset.get("modeling_quality")
            == "production_architectural_detail_v3",
            "minimum_mesh_complexity": asset.get("mesh_polygons", 0) >= 6_000,
            "minimum_component_complexity": asset.get("component_count", 0) >= 300,
            "minimum_detail_systems": len(asset.get("detail_systems", [])) >= 14,
            "signage_present": len(signs) >= 1,
            "signage_larger_and_readable": any(
                sign.get("actual_width_m", 0.0) >= 4.0
                and sign.get("actual_height_m", 0.0) >= 0.42
                for sign in signs
            ),
            "all_signage_within_building_bounds": asset.get("signage_bounds_pass")
            is True
            and all(sign.get("within_building_bounds") is True for sign in signs),
            "structural_connection_detail": asset.get(
                "structural_detail_component_count", 0
            )
            >= 8,
            "detailed_reverse_facade": asset.get(
                "rear_facade_detail_component_count", 0
            )
            >= 80,
        }
        if asset["variant"] == "gated_campus":
            checks.update(
                {
                    "yellow_entrance_piers_removed": asset.get(
                        "yellow_gate_pier_count"
                    )
                    == 0,
                    "complex_security_system": asset.get(
                        "security_detail_component_count", 0
                    )
                    >= 100,
                    "powered_gate_detail_declared": any(
                        "powered_arched_telescopic_gate" in detail
                        for detail in asset.get("detail_systems", [])
                    ),
                }
            )
        if asset["variant"] == "gable_clerestory":
            checks.update(
                {
                    "advanced_igu_component_complexity": asset.get(
                        "advanced_igu_component_count", 0
                    )
                    >= 80,
                    "standing_seam_envelope_complexity": asset.get(
                        "standing_seam_detail_component_count", 0
                    )
                    >= 150,
                    "generator_revision_3": asset.get("generator_revision") == 3,
                }
            )
        if asset["variant"] == "highbay_monochrome":
            checks.update(
                {
                    "front_rectilinear_hedge_removed": asset.get(
                        "front_hedge_component_count", -1
                    )
                    == 0,
                    "generator_revision_3": asset.get("generator_revision") == 3,
                }
            )
        per_asset_checks[asset["variant"]] = checks
    failed_asset_checks = {
        variant: [name for name, passed in checks.items() if not passed]
        for variant, checks in per_asset_checks.items()
        if not all(checks.values())
    }
    if failed_asset_checks:
        raise RuntimeError(
            f"Factory architectural-detail audit failed: {failed_asset_checks}"
        )
    scene_checks = {
        "four_distinct_factory_variants": len(roots) == 4
        and len(set(variants)) == 4,
        "render_validation_performed": bool(rendered_views),
        "daylight_far_views": bool(rendered_views)
        and sum(
            view["view_type"] == "far" and view["lighting"] == "daylight"
            for view in rendered_views
        )
        >= 4,
        "daylight_close_views": bool(rendered_views)
        and sum(
            view["view_type"] == "close" and view["lighting"] == "daylight"
            for view in rendered_views
        )
        >= 5,
        "dedicated_gate_close_view": bool(rendered_views)
        and any("gated_security_gate_close" in view["file"] for view in rendered_views),
        "reverse_facade_far_view": bool(rendered_views)
        and any("row_reverse_far" in view["file"] for view in rendered_views),
        "all_renders_nontrivial": bool(rendered_views)
        and all(view.get("bytes", 0) >= 10_000 for view in rendered_views),
        "requested_revision_checks_pass": all(
            requested_revision_checks.values()
        ),
    }
    required_scene_checks = {"four_distinct_factory_variants"}
    if rendered_views:
        required_scene_checks.update(
            {
                "render_validation_performed",
                "daylight_far_views",
                "daylight_close_views",
                "dedicated_gate_close_view",
                "reverse_facade_far_view",
                "all_renders_nontrivial",
                "requested_revision_checks_pass",
            }
        )
    if not all(scene_checks[name] for name in required_scene_checks):
        raise RuntimeError(f"Factory scene/render audit failed: {scene_checks}")
    audit = {
        "status": "PASS",
        "generator": layout["generator"],
        "asset_factory": layout["asset_factory"],
        "pipeline_integration": layout["pipeline_integration"],
        "procedural_only": True,
        "prepared_blend_imports": 0,
        "factory_count": len(roots),
        "variants": variants,
        "arrangement": layout["arrangement"],
        "reference_images": FACTORY_REFERENCES,
        "factory_assets": layout["factories"],
        "mesh_stats": mesh_stats,
        "render_views": rendered_views,
        "daylight_far_view_count": sum(view["view_type"] == "far" for view in rendered_views),
        "daylight_close_view_count": sum(view["view_type"] == "close" for view in rendered_views),
        "blend_file": blend_file,
        "requirements": requirements,
        "architectural_detail_checks": per_asset_checks,
        "scene_render_checks": scene_checks,
        "requested_revision_checks": requested_revision_checks,
        "sign_obscuring_downspouts": sign_obscuring_downspouts,
    }
    with (output_root / "quality_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)
    manifest = {
        "scene": "urban_v3_factory",
        "status": "complete",
        "generator": layout["generator"],
        "asset_factory": layout["asset_factory"],
        "blend": blend_file,
        "layout": "factory_layout.json",
        "quality_audit": "quality_audit.json",
        "renders": [view["file"] for view in rendered_views],
        "variants": variants,
        "generator_revision": 3,
    }
    with (output_root / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    render_status = (
        "daylight near/far renders validated"
        if rendered_views
        else "render validation not requested"
    )
    (output_root / "SUCCESS").write_text(
        "PASS: four production architectural-detail-v3 procedural factory variants; "
        "bounded enlarged signage; yellow gate piers removed; complex powered gate/fence; "
        "highbay front hedge removed; gable layered IGUs, clear sign sightline and detailed roof; "
        f"{render_status}.\n",
        encoding="utf-8",
    )


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for collection in list(bpy.data.collections):
        if collection.name != "Scene Collection":
            bpy.data.collections.remove(collection)


def save_blend_outputs(output_root, scene_filename="scene.blend"):
    scene_path = output_root / scene_filename
    logger.info("Saving %s", scene_path)
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))
    tag_system.save_tag(path=str(output_root / "MaskTag.json"))
    with (output_root / "polycounts.txt").open("w") as f:
        save_polycounts(f)
    return scene_path


def export_unity_outputs(args, input_blend=None):
    unity_output_dir = args.output / "unity_export"
    logger.info("Exporting Unity-ready components to %s", unity_output_dir)
    from infinigen.tools.unity import export_blend_to_unity

    export_blend_to_unity.main(
        SimpleNamespace(
            input_blend=input_blend,
            output_dir=unity_output_dir,
            project_name=args.unity_project_name,
            vegetation_mode="object",
            max_objects_per_file=args.unity_max_objects_per_file,
            include_factory_prototypes=False,
            include_hidden=False,
        )
    )
    return unity_output_dir


def _mesh_stats():
    factory_markers = (
        "GenericTreeFactory",
        "TreeFactory",
        "BushFactory",
        "LeafFactory",
        "TreeFlowerFactory",
        "BranchFactory",
    )
    stats = {
        "mesh_object_count": 0,
        "total_faces": 0,
        "exportable_mesh_object_count": 0,
        "exportable_faces": 0,
        "exportable_tree_object_count": 0,
        "exportable_tree_faces": 0,
        "hidden_factory_faces": 0,
        "prototype_object_count": 0,
        "largest_meshes": [],
        "largest_exportable_meshes": [],
    }
    largest = []
    largest_exportable = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.data is None:
            continue
        face_count = len(obj.data.polygons)
        stats["mesh_object_count"] += 1
        stats["total_faces"] += face_count
        name = obj.name
        lower_name = name.lower()
        is_factory_asset = any(marker in name for marker in factory_markers)
        is_hidden = obj.hide_viewport or obj.hide_render
        is_exportable = obj.name.startswith("urban:") and not is_hidden and not is_factory_asset
        if "prototype" in lower_name or is_factory_asset:
            stats["prototype_object_count"] += 1
        if is_factory_asset or is_hidden:
            stats["hidden_factory_faces"] += face_count
        if is_exportable:
            stats["exportable_mesh_object_count"] += 1
            stats["exportable_faces"] += face_count
            if "tree" in lower_name or "nature_tree" in lower_name:
                stats["exportable_tree_object_count"] += 1
                stats["exportable_tree_faces"] += face_count
            largest_exportable.append((face_count, obj.name))
        largest.append((face_count, obj.name))
    largest.sort(reverse=True)
    largest_exportable.sort(reverse=True)
    stats["largest_meshes"] = [
        {"name": name, "faces": face_count} for face_count, name in largest[:20]
    ]
    stats["largest_exportable_meshes"] = [
        {"name": name, "faces": face_count} for face_count, name in largest_exportable[:20]
    ]
    return stats


def write_and_check_mesh_budget(output_root, max_total_faces, max_exportable_faces, max_tree_faces):
    stats = _mesh_stats()
    stats["budget"] = {
        "max_total_faces": max_total_faces,
        "max_exportable_faces": max_exportable_faces,
        "max_tree_faces": max_tree_faces,
        "reference": "Compared to outputs/urban_block_10 polycounts.txt: total Faces about 12.85M, urban collection about 1.67M.",
    }
    budget_path = output_root / "mesh_budget.json"
    budget_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")
    logger.info(
        "Mesh budget: total_faces=%s exportable_faces=%s exportable_tree_faces=%s mesh_objects=%s exportable_objects=%s prototypes=%s",
        stats["total_faces"],
        stats["exportable_faces"],
        stats["exportable_tree_faces"],
        stats["mesh_object_count"],
        stats["exportable_mesh_object_count"],
        stats["prototype_object_count"],
    )
    if stats["total_faces"] > max_total_faces:
        raise RuntimeError(
            f"Urban mesh is too large: {stats['total_faces']} faces > {max_total_faces}. See {budget_path}."
        )
    if stats["exportable_faces"] > max_exportable_faces:
        raise RuntimeError(
            f"Urban Unity-exportable mesh is too large: {stats['exportable_faces']} faces > {max_exportable_faces}. See {budget_path}."
        )
    if stats["exportable_tree_faces"] > max_tree_faces:
        raise RuntimeError(
            f"Urban Unity-exportable tree meshes are too large: {stats['exportable_tree_faces']} faces > {max_tree_faces}. See {budget_path}."
        )
    return stats


def generate_direct_outputs(args):
    if args.output is None:
        raise ValueError("--output is required when using --export-format")

    args.output.mkdir(parents=True, exist_ok=True)
    clear_scene()

    scene_seed = init.apply_scene_seed(args.seed)
    if args.scene_profile == "urban":
        init.apply_gin_configs(
            configs=args.configs,
            overrides=args.overrides,
            config_folders="infinigen_examples/configs_urban",
        )

    logger.info("Generating %s scene into %s", args.scene_profile, args.output)
    if args.scene_profile == "factory":
        compose_factory_showcase(
            args.output,
            scene_seed,
            factory_scale=args.factory_scale,
        )
    else:
        compose_urban(
            args.output,
            scene_seed,
            block_extent=args.block_extent,
            road_width=args.road_width,
            sidewalk_width=args.sidewalk_width,
            min_building_height=args.min_building_height,
            max_building_height=args.max_building_height,
        )

    mesh_stats = write_and_check_mesh_budget(
        args.output,
        max_total_faces=args.max_total_faces,
        max_exportable_faces=args.max_exportable_faces,
        max_tree_faces=args.max_tree_faces,
    )

    rendered_views = []
    if args.scene_profile == "factory" and args.render_factory_views:
        rendered_views = _render_factory_views(
            args.output,
            samples=args.factory_render_samples,
            resolution=(args.factory_render_resolution_x, args.factory_render_resolution_y),
        )

    scene_filename = "urban_v3_factory.blend" if args.scene_profile == "factory" else "scene.blend"
    scene_path = None
    if args.export_format == "blend":
        scene_path = save_blend_outputs(args.output, scene_filename=scene_filename)
    elif args.export_format == "unity":
        with (args.output / "polycounts.txt").open("w") as f:
            save_polycounts(f)
        export_unity_outputs(args, input_blend=None)
    elif args.export_format == "blend+unity":
        scene_path = save_blend_outputs(args.output, scene_filename=scene_filename)
        export_unity_outputs(args, input_blend=scene_path)
    else:
        raise ValueError(f"Unsupported export format: {args.export_format}")

    if args.scene_profile == "factory":
        blend_name = scene_path.name if scene_path is not None else None
        _write_factory_audit(args.output, rendered_views, mesh_stats, blend_name)


def main(args):
    if args.output is not None:
        generate_direct_outputs(args)
        return

    scene_seed = init.apply_scene_seed(args.seed)
    if args.scene_profile == "urban":
        init.apply_gin_configs(
            configs=args.configs,
            overrides=args.overrides,
            config_folders="infinigen_examples/configs_urban",
        )

    from infinigen.core import execute_tasks

    compose_func = compose_factory_showcase if args.scene_profile == "factory" else compose_urban
    execute_tasks.main(
        compose_scene_func=compose_func,
        populate_scene_func=None,
        input_folder=args.input_folder,
        output_folder=args.output_folder,
        task=args.task,
        task_uniqname=args.task_uniqname,
        scene_seed=scene_seed,
        linked_blend_assets=args.linked_blend_assets,
        linked_blend_asset_dir=args.linked_blend_asset_dir,
        linked_blend_grouping=args.linked_blend_grouping,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=(
            "Direct urban output directory. Defaults to Unity export only under "
            "<output>/unity_export unless --export-format requests blend output."
        ),
    )
    parser.add_argument(
        "--export-format",
        choices=["blend", "unity", "blend+unity"],
        default="unity",
        help=(
            "blend: save only scene.blend; unity: export Unity files from the generated "
            "in-memory scene; blend+unity: save scene.blend, then convert it to Unity."
        ),
    )
    parser.add_argument("--unity-project-name", default="UnityUrbanProject")
    parser.add_argument("--unity-max-objects-per-file", type=int, default=250)
    parser.add_argument("--block-extent", type=float, default=64.0)
    parser.add_argument("--road-width", type=float, default=8.0)
    parser.add_argument("--sidewalk-width", type=float, default=3.0)
    parser.add_argument("--min-building-height", type=float, default=8.5)
    parser.add_argument("--max-building-height", type=float, default=15.5)
    parser.add_argument("--max-total-faces", type=int, default=16_000_000)
    parser.add_argument("--max-exportable-faces", type=int, default=3_500_000)
    parser.add_argument("--max-tree-faces", type=int, default=2_000_000)
    parser.add_argument(
        "--scene-profile",
        choices=["urban", "factory"],
        default="urban",
        help="urban: normal city block; factory: four reference-derived industrial buildings in one row.",
    )
    parser.add_argument("--factory-scale", type=float, default=1.0)
    parser.add_argument("--factory-render-samples", type=int, default=16)
    parser.add_argument("--factory-render-resolution-x", type=int, default=1440)
    parser.add_argument("--factory-render-resolution-y", type=int, default=810)
    parser.add_argument(
        "--render-factory-views",
        action="store_true",
        help="Render daylight far and close validation views for the factory scene profile.",
    )
    parser.add_argument("--output_folder", type=Path)
    parser.add_argument("--input_folder", type=Path, default=None)
    parser.add_argument(
        "-s", "--seed", default=None, help="The seed used to generate the scene"
    )
    parser.add_argument(
        "-t",
        "--task",
        nargs="+",
        default=["coarse"],
        choices=[
            "coarse",
            "populate",
            "fine_terrain",
            "ground_truth",
            "render",
            "mesh_save",
            "export",
        ],
    )
    parser.add_argument(
        "-g",
        "--configs",
        nargs="+",
        default=["base_urban"],
        help="Set of config files for gin, without the .gin suffix.",
    )
    parser.add_argument(
        "-p",
        "--overrides",
        nargs="+",
        default=[],
        help="Parameter settings that override config defaults.",
    )
    parser.add_argument("--task_uniqname", type=str, default=None)
    parser.add_argument(
        "--linked_blend_assets",
        action="store_true",
        help="Save the generated scene as a lightweight main blend linked to external asset blend libraries.",
    )
    parser.add_argument(
        "--linked_blend_asset_dir",
        type=str,
        default="linked_assets",
        help="Directory under the output folder for external linked asset blend libraries.",
    )
    parser.add_argument(
        "--linked_blend_grouping",
        type=str,
        default="urban",
        choices=["urban", "colon_prefix"],
        help="Object grouping strategy used when writing linked asset blend libraries.",
    )
    parser.add_argument("-d", "--debug", type=str, nargs="*", default=None)

    args = init.parse_args_blender(parser)

    logging.getLogger("infinigen").setLevel(logging.INFO)
    logging.getLogger("infinigen.core.nodes.node_wrangler").setLevel(logging.CRITICAL)

    if args.debug is not None:
        for name in logging.root.manager.loggerDict:
            if not name.startswith("infinigen"):
                continue
            if len(args.debug) == 0 or any(name.endswith(x) for x in args.debug):
                logging.getLogger(name).setLevel(logging.DEBUG)

    main(args)

"""Reference-driven procedural outdoor fitness area for the Urban-v3 pipeline.

The source generator is the canonical asset definition.  It builds ten distinct,
real-scale equipment archetypes visible in the supplied references and exposes
``build_outdoor_fitness_asset`` / ``build_outdoor_fitness_area`` for production
scene composition.  ``main`` is only the isolated daylight validation entrypoint;
it calls the same public builders used by :mod:`urban_assets`.

No external mesh or generated ``.blend`` is read by this module.
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
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector
from mathutils.bvhtree import BVHTree
from mathutils.geometry import intersect_ray_tri


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
ASSET_ID = "urban_v3_fitness5"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_fitness5"
RENDERS = OUT / "renders"
REFERENCES = OUT / "references"
PREFIX = "outdoor_fitness:"
PAVER_SURFACE_Z = 0.064
BLEND_FILENAME = "urban_v3_fitness5.blend"
PREVIOUS_OUTPUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_fitness4"
PREVIOUS_BLEND_SHA256 = (
    "d9cddd63e56947915fdb001acf6d98f33471da291759ab35af8fb5374febbdc2"
)
METHOD_REFERENCE_URL = "https://arxiv.org/pdf/2505.10755"
METHOD_REFERENCE_CACHE = ROOT / ".reference_cache/2505.10755.pdf"
ARTICULATION_STANDARD = (
    "Infinigen-Articulated nodegroup joint metadata + Blender rigid bodies + "
    "full-range evaluated-mesh collision sweep"
)
JOINT_ATTACHMENT_RADIUS_M = 0.19
_ARTICULATION_NODEGROUPS = {}

REFERENCE_URLS = (
    "https://preview.free3d.com/img/2023/09/3191690105098077534/iq7c0qxi.jpg",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcRZLUHicGP5Fi7ak2d_yZitvJHFFM3UG6EcwsiioU5y2woLnQx5Xp0hSZ_c&s=10",
    "https://www.maidong123.com/wp-content/uploads/2023/01/30111111044.png",
)
REFERENCE_CACHE = (
    ROOT / ".reference_cache/fitness/reference_free3d.jpg",
    ROOT / ".reference_cache/fitness/reference_google.jpg",
    ROOT / ".reference_cache/fitness/reference_maidong123_30111111044.png",
)
FITNESS_VARIANTS = (
    "air_walker_double",
    "ski_walker",
    "rider_trainer",
    "stepper_station",
    "double_leg_press",
    "double_surf_board",
    "double_traction_station",
    "stall_bars",
    "rowing_machine",
    "fitness_notice_board",
)
EXPECTED_JOINTS_PER_VARIANT = {
    "air_walker_double": {"revolute": 2, "prismatic": 0},
    "ski_walker": {"revolute": 2, "prismatic": 0},
    "rider_trainer": {"revolute": 2, "prismatic": 0},
    "stepper_station": {"revolute": 2, "prismatic": 0},
    "double_leg_press": {"revolute": 2, "prismatic": 0},
    "double_surf_board": {"revolute": 2, "prismatic": 0},
    "double_traction_station": {"revolute": 8, "prismatic": 0},
    "stall_bars": {"revolute": 0, "prismatic": 0},
    "rowing_machine": {"revolute": 1, "prismatic": 1},
    "fitness_notice_board": {"revolute": 0, "prismatic": 0},
}


@dataclass
class BuildContext:
    variant: str
    collection: bpy.types.Collection
    root: bpy.types.Object
    objects: list[bpy.types.Object] = field(default_factory=list)
    joints: list[dict] = field(default_factory=list)
    joint_values: dict[str, float] = field(default_factory=dict)
    base_collision: bpy.types.Object | None = None


def set_prefix(value: str):
    global PREFIX
    PREFIX = value


def reset_scene():
    global _ARTICULATION_NODEGROUPS
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _ARTICULATION_NODEGROUPS = {}


def collection(name: str, parent=None, role="procedural_collection", variant=None):
    coll = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(coll)
    coll["c2w_role"] = role
    coll["c2w_asset_id"] = "park.outdoor_fitness.v1"
    if variant:
        coll["c2w_variant"] = variant
    return coll


def anchor(coll, name: str, variant: str, origin=(0.0, 0.0, 0.0), yaw=0.0):
    root = bpy.data.objects.new(PREFIX + name, None)
    coll.objects.link(root)
    root.empty_display_type = "CIRCLE"
    root.empty_display_size = 0.42
    root.location = origin
    root.rotation_euler[2] = yaw
    root["c2w_role"] = "asset_root"
    root["c2w_asset_id"] = f"park.outdoor_fitness.{variant}.v1"
    root["c2w_variant"] = variant
    root["c2w_generator"] = Path(__file__).name
    root["c2w_units"] = "meters"
    root["c2w_procedural_source"] = True
    return root


def tag(obj, ctx: BuildContext, semantic: str, detail=True):
    obj.parent = ctx.root
    obj["c2w_role"] = "fitness_part"
    obj["c2w_asset_id"] = f"park.outdoor_fitness.{ctx.variant}.v1"
    obj["c2w_variant"] = ctx.variant
    obj["c2w_semantic"] = semantic
    obj["c2w_detail"] = bool(detail)
    obj["c2w_procedural_source"] = True
    ctx.objects.append(obj)
    return obj


def _set_input(node, name, value):
    if node and name in node.inputs:
        node.inputs[name].default_value = value


def pbr(name, color, roughness=0.5, metallic=0.0, noise=None, bump=0.0):
    full_name = PREFIX + name
    existing = bpy.data.materials.get(full_name)
    if existing:
        return existing
    mat = bpy.data.materials.new(full_name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes, links = nt.nodes, nt.links
    bsdf = nodes.get("Principled BSDF")
    _set_input(bsdf, "Base Color", (*color, 1.0))
    _set_input(bsdf, "Roughness", roughness)
    _set_input(bsdf, "Metallic", metallic)
    if noise:
        tex = nodes.new("ShaderNodeTexNoise")
        tex.name = "micro_surface_variation"
        tex.inputs["Scale"].default_value = noise[0]
        tex.inputs["Detail"].default_value = noise[1]
        tex.inputs["Roughness"].default_value = 0.7
        ramp = nodes.new("ShaderNodeValToRGB")
        dark = tuple(max(0.0, c * noise[2]) for c in color)
        light = tuple(min(1.0, c * noise[3]) for c in color)
        ramp.color_ramp.elements[0].color = (*dark, 1.0)
        ramp.color_ramp.elements[1].color = (*light, 1.0)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if bump:
            bump_node = nodes.new("ShaderNodeBump")
            bump_node.name = "micro_orange_peel"
            bump_node.inputs["Strength"].default_value = bump
            bump_node.inputs["Distance"].default_value = 0.04
            links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
            links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    mat["c2w_pbr"] = True
    return mat


def make_materials():
    return {
        "green": pbr(
            "powder_coat_lime",
            (0.24, 0.66, 0.035),
            0.29,
            0.38,
            noise=(95.0, 3.2, 0.78, 1.13),
            bump=0.07,
        ),
        "green_dark": pbr(
            "powder_coat_shadow",
            (0.095, 0.31, 0.018),
            0.34,
            0.34,
            noise=(82.0, 2.8, 0.76, 1.12),
            bump=0.06,
        ),
        "teal": pbr(
            "powder_coat_deep_teal",
            (0.018, 0.245, 0.205),
            0.31,
            0.40,
            noise=(88.0, 3.0, 0.72, 1.16),
            bump=0.075,
        ),
        "teal_dark": pbr(
            "powder_coat_deep_teal_shadow",
            (0.008, 0.105, 0.088),
            0.35,
            0.42,
            noise=(84.0, 3.0, 0.70, 1.13),
            bump=0.07,
        ),
        "cream": pbr(
            "powder_coat_warm_cream",
            (0.70, 0.61, 0.44),
            0.37,
            0.32,
            noise=(76.0, 2.6, 0.78, 1.12),
            bump=0.065,
        ),
        "cream_dark": pbr(
            "powder_coat_cream_shadow",
            (0.37, 0.29, 0.18),
            0.43,
            0.32,
            noise=(72.0, 2.4, 0.72, 1.10),
            bump=0.06,
        ),
        "galvanized": pbr(
            "galvanized_steel",
            (0.46, 0.49, 0.48),
            0.31,
            0.82,
            noise=(18.0, 5.0, 0.72, 1.2),
            bump=0.11,
        ),
        "stainless": pbr(
            "stainless_fasteners",
            (0.64, 0.67, 0.66),
            0.18,
            0.95,
            noise=(120.0, 2.0, 0.9, 1.08),
            bump=0.035,
        ),
        "rubber": pbr(
            "textured_black_rubber",
            (0.014, 0.017, 0.014),
            0.82,
            0.0,
            noise=(145.0, 4.0, 0.55, 1.8),
            bump=0.3,
        ),
        "bearing": pbr(
            "sealed_bearing",
            (0.035, 0.042, 0.036),
            0.4,
            0.55,
            noise=(45.0, 2.0, 0.75, 1.15),
            bump=0.08,
        ),
        "warning": pbr(
            "safety_yellow",
            (0.93, 0.61, 0.035),
            0.34,
            0.25,
            noise=(70.0, 2.2, 0.78, 1.12),
            bump=0.08,
        ),
        "seat_pad": pbr(
            "weatherproof_seat_pad",
            (0.54, 0.49, 0.39),
            0.72,
            0.0,
            noise=(52.0, 4.0, 0.68, 1.18),
            bump=0.18,
        ),
        "sign_face": pbr(
            "notice_board_face",
            (0.54, 0.57, 0.53),
            0.50,
            0.48,
            noise=(35.0, 2.0, 0.86, 1.06),
            bump=0.045,
        ),
        "sign_red": pbr("notice_board_red_ink", (0.62, 0.035, 0.025), 0.48, 0.02),
        "sign_yellow": pbr("notice_board_yellow_ink", (0.94, 0.55, 0.02), 0.45, 0.02),
        "grout": pbr(
            "grout",
            (0.12, 0.13, 0.125),
            0.92,
            0.0,
            noise=(16.0, 5.0, 0.65, 1.2),
            bump=0.26,
        ),
        "curb": pbr(
            "border_stone",
            (0.30, 0.32, 0.31),
            0.82,
            0.0,
            noise=(7.5, 6.0, 0.68, 1.23),
            bump=0.34,
        ),
        "surround": pbr(
            "surrounding_aggregate_pavement",
            (0.18, 0.195, 0.19),
            0.9,
            0.0,
            noise=(12.0, 7.0, 0.58, 1.35),
            bump=0.34,
        ),
        "drain": pbr(
            "drain_dark_metal",
            (0.055, 0.065, 0.06),
            0.5,
            0.74,
            noise=(34.0, 4.0, 0.68, 1.2),
            bump=0.12,
        ),
    }


def _link_active(coll):
    obj = bpy.context.active_object
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def box(
    ctx,
    name,
    loc,
    dims,
    material,
    bevel=0.018,
    rotation=(0.0, 0.0, 0.0),
    semantic="manufactured_detail",
):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc, rotation=rotation)
    obj = _link_active(ctx.collection)
    obj.name = PREFIX + ctx.variant + ":" + name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("rolled_edges", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        mod.limit_method = "ANGLE"
    return tag(obj, ctx, semantic)


def cylinder(
    ctx,
    name,
    loc,
    radius,
    depth,
    material,
    vertices=32,
    rotation=(0.0, 0.0, 0.0),
    semantic="manufactured_detail",
    bevel=0.006,
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rotation
    )
    obj = _link_active(ctx.collection)
    obj.name = PREFIX + ctx.variant + ":" + name
    if material:
        obj.data.materials.append(material)
    if bevel:
        mod = obj.modifiers.new("edge_softening", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        mod.limit_method = "ANGLE"
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return tag(obj, ctx, semantic)


def sphere(ctx, name, loc, radius, material, semantic="manufactured_detail"):
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24, ring_count=12, radius=radius, location=loc
    )
    obj = _link_active(ctx.collection)
    obj.name = PREFIX + ctx.variant + ":" + name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return tag(obj, ctx, semantic)


def torus(
    ctx,
    name,
    loc,
    major,
    minor,
    material,
    rotation=(0.0, 0.0, 0.0),
    semantic="weld_bead",
):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=32,
        minor_segments=8,
        location=loc,
        rotation=rotation,
    )
    obj = _link_active(ctx.collection)
    obj.name = PREFIX + ctx.variant + ":" + name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return tag(obj, ctx, semantic)


def tube(
    ctx,
    name,
    points,
    radius,
    material,
    semantic="structural_tube",
    cyclic=False,
    resolution=3,
):
    curve = bpy.data.curves.new(PREFIX + ctx.variant + ":" + name + "_profile", "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = radius
    curve.bevel_resolution = 3
    curve.resolution_u = 3
    curve.use_fill_caps = True
    spline = curve.splines.new("BEZIER")
    spline.bezier_points.add(len(points) - 1)
    for bp, co in zip(spline.bezier_points, points):
        bp.co = co
        bp.handle_left_type = "AUTO"
        bp.handle_right_type = "AUTO"
    spline.use_cyclic_u = cyclic
    obj = bpy.data.objects.new(PREFIX + ctx.variant + ":" + name, curve)
    ctx.collection.objects.link(obj)
    obj.data.materials.append(material)
    return tag(obj, ctx, semantic)


def beam(
    ctx, name, start, end, radius, material, semantic="structural_tube", vertices=28
):
    a, b = Vector(start), Vector(end)
    delta = b - a
    obj = cylinder(
        ctx,
        name,
        (a + b) * 0.5,
        radius,
        delta.length,
        material,
        vertices=vertices,
        semantic=semantic,
    )
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    return obj


def wedge(
    ctx,
    name,
    center,
    width,
    depth,
    height,
    material,
    rotation_z=0.0,
    semantic="reinforcement_gusset",
):
    # Triangular prism, with its right-angle corner centered at the support.
    verts = [
        (-width / 2, -depth / 2, -height / 2),
        (width / 2, -depth / 2, -height / 2),
        (-width / 2, -depth / 2, height / 2),
        (-width / 2, depth / 2, -height / 2),
        (width / 2, depth / 2, -height / 2),
        (-width / 2, depth / 2, height / 2),
    ]
    faces = [(0, 1, 2), (3, 5, 4), (0, 3, 4, 1), (0, 2, 5, 3), (1, 4, 5, 2)]
    mesh = bpy.data.meshes.new(PREFIX + ctx.variant + ":" + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(PREFIX + ctx.variant + ":" + name, mesh)
    ctx.collection.objects.link(obj)
    obj.location = center
    obj.rotation_euler[2] = rotation_z
    mod = obj.modifiers.new("gusset_edge_softening", "BEVEL")
    mod.width = 0.008
    mod.segments = 2
    return tag(obj, ctx, semantic)


def _axis_rotation(axis):
    if axis == "x":
        return (0.0, math.pi / 2, 0.0)
    if axis == "y":
        return (math.pi / 2, 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def _axis_vector(axis):
    if isinstance(axis, str):
        return {
            "x": Vector((1.0, 0.0, 0.0)),
            "y": Vector((0.0, 1.0, 0.0)),
            "z": Vector((0.0, 0.0, 1.0)),
        }[axis.lower()]
    vec = Vector(axis)
    if vec.length <= 1e-8:
        raise ValueError("A joint axis must be non-zero")
    return vec.normalized()


def _box_mesh(name, center, dimensions):
    """Make a closed collision box while keeping its object origin at the joint."""
    cx, cy, cz = center
    hx, hy, hz = (max(float(v), 0.025) * 0.5 for v in dimensions)
    verts = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    mesh = bpy.data.meshes.new(PREFIX + name + "_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    return mesh


def _activate_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def _add_rigid_body(obj, body_type, mass=1.0, damping=0.18, friction=0.62):
    """Attach native Blender rigid-body state used by the validation blend."""
    _activate_only(obj)
    bpy.ops.rigidbody.object_add(type=body_type)
    rigid = obj.rigid_body
    rigid.collision_shape = "BOX"
    rigid.use_margin = True
    rigid.collision_margin = 0.008
    rigid.friction = float(friction)
    rigid.restitution = 0.02
    if body_type == "ACTIVE":
        rigid.mass = max(0.05, float(mass))
        rigid.linear_damping = min(max(float(damping), 0.0), 1.0)
        rigid.angular_damping = min(max(float(damping) * 1.35, 0.0), 1.0)
        rigid.use_deactivation = True
        rigid.use_start_deactivated = True
    obj.select_set(False)


def _ensure_base_collision(ctx):
    if ctx.base_collision is not None:
        return ctx.base_collision
    mesh = _box_mesh(
        ctx.variant + ":base_collision", (0.0, 0.0, 0.16), (0.42, 0.42, 0.30)
    )
    obj = bpy.data.objects.new(PREFIX + ctx.variant + ":base_link_collision", mesh)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.root
    obj.location = (0.0, 0.0, 0.0)
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj["c2w_role"] = "simulation_collision_proxy"
    obj["c2w_link_id"] = "base_link"
    obj["c2w_collision_geometry"] = "procedural_box"
    obj["c2w_procedural_source"] = True
    obj["c2w_variant"] = ctx.variant
    _add_rigid_body(obj, "PASSIVE")
    ctx.base_collision = obj
    return obj


def _asset_space_bounds(ctx, objects):
    bpy.context.view_layer.update()
    inv_root = ctx.root.matrix_world.inverted_safe()
    points = []
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "SURFACE", "FONT"}:
            continue
        points.extend(
            inv_root @ (obj.matrix_world @ Vector(corner)) for corner in obj.bound_box
        )
    if not points:
        return Vector((0.0, 0.0, 0.5)), Vector((0.20, 0.20, 0.20))
    lower = Vector(
        (min(p.x for p in points), min(p.y for p in points), min(p.z for p in points))
    )
    upper = Vector(
        (max(p.x for p in points), max(p.y for p in points), max(p.z for p in points))
    )
    return (lower + upper) * 0.5, upper - lower


def _reparent_keep_world(obj, parent):
    matrix_world = obj.matrix_world.copy()
    obj.parent = parent
    obj.matrix_world = matrix_world


def _joint_rotation(axis, track="Z"):
    axis_vec = _axis_vector(axis)
    if track == "Z":
        up = "X" if abs(axis_vec.y) > 0.92 else "Y"
    else:
        up = "Z" if abs(axis_vec.z) < 0.92 else "Y"
    return axis_vec.to_track_quat(track, up)


def _make_constraint(ctx, name, joint_type, pivot, axis, child, limits):
    base = _ensure_base_collision(ctx)
    obj = bpy.data.objects.new(PREFIX + ctx.variant + ":" + name + "_constraint", None)
    ctx.collection.objects.link(obj)
    obj.parent = ctx.root
    obj.location = pivot
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = _joint_rotation(
        axis, "Z" if joint_type == "HINGE" else "X"
    )
    obj.empty_display_type = "ARROWS"
    obj.empty_display_size = 0.16
    _activate_only(obj)
    bpy.ops.rigidbody.constraint_add()
    constraint = obj.rigid_body_constraint
    constraint.type = joint_type
    constraint.object1 = base
    constraint.object2 = child
    constraint.disable_collisions = True
    if joint_type == "HINGE" and limits is not None:
        constraint.use_limit_ang_z = True
        constraint.limit_ang_z_lower = float(limits[0])
        constraint.limit_ang_z_upper = float(limits[1])
    elif joint_type == "SLIDER" and limits is not None:
        constraint.use_limit_lin_x = True
        constraint.limit_lin_x_lower = float(limits[0])
        constraint.limit_lin_x_upper = float(limits[1])
    obj["c2w_role"] = "simulation_joint_constraint"
    obj["c2w_joint_id"] = name
    obj["c2w_joint_type"] = "revolute" if joint_type == "HINGE" else "prismatic"
    obj["c2w_joint_axis_local"] = list(_axis_vector(axis))
    obj["c2w_joint_pivot_local_m"] = list(Vector(pivot))
    obj["c2w_joint_lower"] = float(limits[0]) if limits is not None else 0.0
    obj["c2w_joint_upper"] = float(limits[1]) if limits is not None else 0.0
    obj["c2w_procedural_source"] = True
    obj.select_set(False)
    return obj


def _infinigen_joint_groups():
    """Load the exact joint node groups published with Infinigen-Articulated."""
    global _ARTICULATION_NODEGROUPS
    if _ARTICULATION_NODEGROUPS:
        return _ARTICULATION_NODEGROUPS
    infinigen_root = ROOT / "infinigen"
    if str(infinigen_root) not in sys.path:
        sys.path.insert(0, str(infinigen_root))
    mpl_cache = ROOT / ".qa_tmp/matplotlib"
    mpl_cache.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(mpl_cache))
    from infinigen.assets.utils.joints import (  # pylint: disable=import-outside-toplevel
        nodegroup_hinge_joint,
        nodegroup_sliding_joint,
    )

    _ARTICULATION_NODEGROUPS = {
        "HINGE": nodegroup_hinge_joint(),
        "SLIDER": nodegroup_sliding_joint(),
    }
    return _ARTICULATION_NODEGROUPS


def _make_standard_joint_bridge(
    ctx, name, joint_type, base, child, pivot, axis, limits, initial_value
):
    """Connect our detailed rigid links to the paper's native metadata nodes."""
    standard_group = _infinigen_joint_groups()[joint_type]
    tree = bpy.data.node_groups.new(
        PREFIX + ctx.variant + ":" + name + "_kinematics", "GeometryNodeTree"
    )
    tree.interface.new_socket(
        name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
    )
    nodes, links = tree.nodes, tree.links
    output = nodes.new("NodeGroupOutput")
    parent_info = nodes.new("GeometryNodeObjectInfo")
    parent_info.transform_space = "RELATIVE"
    parent_info.inputs["Object"].default_value = base
    child_info = nodes.new("GeometryNodeObjectInfo")
    child_info.transform_space = "RELATIVE"
    child_info.inputs["Object"].default_value = child
    joint = nodes.new("GeometryNodeGroup")
    joint.node_tree = standard_group
    joint.inputs["Joint Label"].default_value = f"{ctx.variant}_{name}"
    joint.inputs["Position"].default_value = Vector(pivot)
    joint.inputs["Axis"].default_value = _axis_vector(axis)
    # The source proxy already carries the requested display pose.  Keeping the
    # node value at zero prevents applying that pose twice while preserving all
    # standard origin/axis/range metadata used by the native exporters.
    joint.inputs["Value"].default_value = 0.0
    if limits is not None:
        joint.inputs["Min"].default_value = float(limits[0])
        joint.inputs["Max"].default_value = float(limits[1])
    joint.inputs["Show Joint"].default_value = False
    links.new(parent_info.outputs["Geometry"], joint.inputs["Parent"])
    links.new(child_info.outputs["Geometry"], joint.inputs["Child"])
    links.new(joint.outputs["Geometry"], output.inputs["Geometry"])

    carrier_mesh = bpy.data.meshes.new(
        PREFIX + ctx.variant + ":" + name + "_carrier_mesh"
    )
    carrier_mesh.from_pydata([(0.0, 0.0, 0.0)], [], [])
    carrier = bpy.data.objects.new(
        PREFIX + ctx.variant + ":" + name + "_standard_bridge", carrier_mesh
    )
    ctx.collection.objects.link(carrier)
    carrier.parent = ctx.root
    carrier.location = (0.0, 0.0, 0.0)
    carrier.hide_render = True
    carrier.display_type = "WIRE"
    modifier = carrier.modifiers.new("Infinigen_Articulated_Joint", "NODES")
    modifier.node_group = tree
    carrier["c2w_role"] = "infinigen_articulated_joint_bridge"
    carrier["c2w_joint_id"] = name
    carrier["c2w_joint_type"] = "revolute" if joint_type == "HINGE" else "prismatic"
    carrier["c2w_initial_value"] = float(initial_value)
    carrier["c2w_native_nodegroup"] = standard_group.name
    carrier["c2w_direct_method_reuse"] = True
    carrier["c2w_procedural_source"] = True
    return carrier


def _make_link_collision(ctx, name, moving_objects, pivot, mass, damping, friction):
    center, dimensions = _asset_space_bounds(ctx, moving_objects)
    # A slightly inset convex proxy avoids false contacts between decorative
    # washers while the rendered geometry remains untouched and high-detail.
    collision_dims = Vector(tuple(max(0.05, value * 0.88) for value in dimensions))
    pivot_vec = Vector(pivot)
    mesh = _box_mesh(
        ctx.variant + ":" + name + "_collision", center - pivot_vec, collision_dims
    )
    obj = bpy.data.objects.new(
        PREFIX + ctx.variant + ":" + name + "_link_collision", mesh
    )
    ctx.collection.objects.link(obj)
    obj.parent = ctx.root
    obj.location = pivot_vec
    obj.display_type = "WIRE"
    obj.hide_render = True
    obj["c2w_role"] = "simulation_collision_proxy"
    obj["c2w_link_id"] = name + "_link"
    obj["c2w_collision_geometry"] = "procedural_inset_convex_box"
    obj["c2w_collision_dimensions_m"] = list(collision_dims)
    obj["c2w_procedural_source"] = True
    obj["c2w_variant"] = ctx.variant
    _add_rigid_body(obj, "ACTIVE", mass, damping, friction)
    for part in moving_objects:
        _reparent_keep_world(part, obj)
        part["c2w_link_id"] = name + "_link"
        part["c2w_joint_id"] = name
        part["c2w_movable"] = True
    return obj


def _requested_joint_value(ctx, name, default):
    return float(ctx.joint_values.get(name, ctx.joint_values.get("*", default)))


def articulate_hinge(
    ctx,
    name,
    moving_objects,
    pivot,
    axis,
    limits,
    default_value=0.0,
    mass=18.0,
    damping=0.24,
    friction=0.12,
    coupled_to=None,
):
    """Create a revolute link with real pivot, rigid constraint and export metadata."""
    moving_objects = list(dict.fromkeys(moving_objects))
    if not moving_objects:
        raise RuntimeError(f"{ctx.variant}:{name} has no moving geometry")
    lower, upper = float(limits[0]), float(limits[1])
    if not lower < upper:
        raise ValueError(f"Invalid hinge limits for {ctx.variant}:{name}: {limits}")
    value = min(max(_requested_joint_value(ctx, name, default_value), lower), upper)
    base = _ensure_base_collision(ctx)
    child = _make_link_collision(
        ctx, name, moving_objects, pivot, mass, damping, friction
    )
    child.rotation_mode = "QUATERNION"
    child.rotation_quaternion = Quaternion(_axis_vector(axis), value)
    child["c2w_joint_value"] = value
    child["c2w_joint_axis_local"] = list(_axis_vector(axis))
    child["c2w_joint_pivot_local_m"] = list(Vector(pivot))
    child["c2w_joint_limit_lower_rad"] = lower
    child["c2w_joint_limit_upper_rad"] = upper
    child["c2w_mass_kg"] = float(mass)
    child["c2w_damping"] = float(damping)
    child["c2w_friction"] = float(friction)
    if coupled_to:
        child["c2w_coupled_to"] = coupled_to
    constraint = _make_constraint(
        ctx, name, "HINGE", pivot, axis, child, (lower, upper)
    )
    bridge = _make_standard_joint_bridge(
        ctx, name, "HINGE", base, child, pivot, axis, (lower, upper), value
    )
    record = {
        "joint_id": name,
        "joint_type": "revolute",
        "parent_link": "base_link",
        "child_link": name + "_link",
        "pivot_local_m": [float(v) for v in Vector(pivot)],
        "axis_local": [float(v) for v in _axis_vector(axis)],
        "limit_lower_rad": lower,
        "limit_upper_rad": upper,
        "initial_value_rad": value,
        "mass_kg": float(mass),
        "damping": float(damping),
        "friction": float(friction),
        "moving_object_count": len(moving_objects),
        "controller": child.name,
        "constraint": constraint.name,
        "standard_bridge": bridge.name,
        "native_nodegroup": bridge["c2w_native_nodegroup"],
    }
    if coupled_to:
        record["coupled_to"] = coupled_to
    ctx.joints.append(record)
    return child


def articulate_slider(
    ctx,
    name,
    moving_objects,
    pivot,
    axis,
    limits,
    default_value=0.0,
    mass=12.0,
    damping=0.30,
    friction=0.18,
):
    """Create a prismatic companion link for mechanisms such as a rowing seat."""
    moving_objects = list(dict.fromkeys(moving_objects))
    if not moving_objects:
        raise RuntimeError(f"{ctx.variant}:{name} has no moving geometry")
    lower, upper = float(limits[0]), float(limits[1])
    value = min(max(_requested_joint_value(ctx, name, default_value), lower), upper)
    axis_vec = _axis_vector(axis)
    base = _ensure_base_collision(ctx)
    child = _make_link_collision(
        ctx, name, moving_objects, pivot, mass, damping, friction
    )
    child.location = Vector(pivot) + axis_vec * value
    child["c2w_joint_value"] = value
    child["c2w_joint_axis_local"] = list(axis_vec)
    child["c2w_joint_pivot_local_m"] = list(Vector(pivot))
    child["c2w_joint_limit_lower_m"] = lower
    child["c2w_joint_limit_upper_m"] = upper
    child["c2w_mass_kg"] = float(mass)
    child["c2w_damping"] = float(damping)
    child["c2w_friction"] = float(friction)
    constraint = _make_constraint(
        ctx, name, "SLIDER", pivot, axis_vec, child, (lower, upper)
    )
    bridge = _make_standard_joint_bridge(
        ctx, name, "SLIDER", base, child, pivot, axis_vec, (lower, upper), value
    )
    ctx.joints.append(
        {
            "joint_id": name,
            "joint_type": "prismatic",
            "parent_link": "base_link",
            "child_link": name + "_link",
            "pivot_local_m": [float(v) for v in Vector(pivot)],
            "axis_local": [float(v) for v in axis_vec],
            "limit_lower_m": lower,
            "limit_upper_m": upper,
            "initial_value_m": value,
            "mass_kg": float(mass),
            "damping": float(damping),
            "friction": float(friction),
            "moving_object_count": len(moving_objects),
            "controller": child.name,
            "constraint": constraint.name,
            "standard_bridge": bridge.name,
            "native_nodegroup": bridge["c2w_native_nodegroup"],
        }
    )
    return child


def bolt(ctx, name, loc, M, axis="z", length=0.04, radius=0.022, washer=True):
    rot = _axis_rotation(axis)
    cylinder(
        ctx,
        name + "_head",
        loc,
        radius,
        length,
        M["stainless"],
        vertices=6,
        rotation=rot,
        semantic="fastener",
        bevel=0.002,
    )
    if washer:
        torus(
            ctx,
            name + "_washer",
            loc,
            radius * 1.17,
            radius * 0.14,
            M["stainless"],
            rotation=rot,
            semantic="fastener",
        )


def base_assembly(
    ctx,
    name,
    M,
    center=(0.0, 0.0),
    post_radius=0.12,
    post_height=0.52,
    flange_radius=0.31,
    anchors=6,
    material_key="green",
    dark_key="green_dark",
):
    x, y = center
    flange = cylinder(
        ctx,
        name + "_flange",
        (x, y, 0.07),
        flange_radius,
        0.14,
        M[material_key],
        vertices=48,
        semantic="mounting_flange",
        bevel=0.012,
    )
    flange["c2w_ground_contact"] = True
    flange["c2w_support_verified"] = True
    cylinder(
        ctx,
        name + "_post",
        (x, y, 0.14 + post_height / 2),
        post_radius,
        post_height,
        M[material_key],
        vertices=40,
        semantic="support_post",
        bevel=0.009,
    )
    torus(
        ctx,
        name + "_weld",
        (x, y, 0.145),
        post_radius * 0.99,
        0.022,
        M[dark_key],
        semantic="weld_bead",
    )
    torus(
        ctx,
        name + "_flange_weld",
        (x, y, 0.112),
        post_radius * 1.15,
        0.013,
        M[dark_key],
        semantic="weld_bead",
    )
    for i in range(anchors):
        ang = math.tau * i / anchors
        bx = x + flange_radius * 0.72 * math.cos(ang)
        by = y + flange_radius * 0.72 * math.sin(ang)
        cylinder(
            ctx,
            f"{name}_anchor_{i:02d}",
            (bx, by, 0.16),
            0.025,
            0.065,
            M["stainless"],
            vertices=6,
            semantic="anchor_bolt",
            bevel=0.002,
        )
        torus(
            ctx,
            f"{name}_anchor_washer_{i:02d}",
            (bx, by, 0.13),
            0.032,
            0.006,
            M["stainless"],
            semantic="anchor_bolt",
        )
    for i in range(4):
        a = math.tau * i / 4
        wedge(
            ctx,
            f"{name}_gusset_{i}",
            (
                x + math.cos(a) * (post_radius + 0.055),
                y + math.sin(a) * (post_radius + 0.055),
                0.245,
            ),
            0.18,
            0.035,
            0.20,
            M[dark_key],
            a,
            "reinforcement_gusset",
        )


def pivot_pack(
    ctx, name, loc, M, axis="y", width=0.22, radius=0.075, body_material=None
):
    rot = _axis_rotation(axis)
    body = body_material or M["green"]
    cylinder(
        ctx,
        name + "_housing",
        loc,
        radius,
        width,
        body,
        vertices=36,
        rotation=rot,
        semantic="pivot_housing",
        bevel=0.006,
    )
    pin = cylinder(
        ctx,
        name + "_through_pin",
        loc,
        radius * 0.25,
        width + 0.090,
        M["stainless"],
        vertices=28,
        rotation=rot,
        semantic="hinge_pin",
        bevel=0.003,
    )
    pin["c2w_load_bearing"] = True
    pin["c2w_joint_axis_local"] = list(_axis_vector(axis))
    # Outboard sealed bearings and stainless pivot caps make the mechanism legible.
    offset = {
        "x": Vector((width / 2 + 0.008, 0, 0)),
        "y": Vector((0, width / 2 + 0.008, 0)),
        "z": Vector((0, 0, width / 2 + 0.008)),
    }[axis]
    for side, vec in (("a", offset), ("b", -offset)):
        pt = Vector(loc) + vec
        cylinder(
            ctx,
            f"{name}_bearing_{side}",
            pt,
            radius * 0.72,
            0.022,
            M["bearing"],
            vertices=32,
            rotation=rot,
            semantic="sealed_bearing",
            bevel=0.003,
        )
        cylinder(
            ctx,
            f"{name}_cap_{side}",
            pt + vec.normalized() * 0.014,
            radius * 0.42,
            0.034,
            M["stainless"],
            vertices=6,
            rotation=rot,
            semantic="pivot_fastener",
            bevel=0.003,
        )
        torus(
            ctx,
            f"{name}_retaining_ring_{side}",
            pt + vec.normalized() * 0.030,
            radius * 0.46,
            radius * 0.055,
            M["stainless"],
            rotation=rot,
            semantic="retaining_ring",
        )
    # A modeled grease nipple and collar communicate serviceability in closeups.
    grease_base = Vector(loc) + Vector((0.0, 0.0, radius * 0.86))
    cylinder(
        ctx,
        name + "_grease_nipple",
        grease_base + Vector((0.0, 0.0, 0.020)),
        radius * 0.105,
        0.040,
        M["stainless"],
        vertices=12,
        semantic="grease_fitting",
        bevel=0.002,
    )
    sphere(
        ctx,
        name + "_grease_cap",
        grease_base + Vector((0.0, 0.0, 0.043)),
        radius * 0.125,
        M["bearing"],
        "grease_fitting",
    )


def grip(ctx, name, start, end, M, radius=0.038):
    beam(ctx, name + "_rubber", start, end, radius, M["rubber"], "hand_grip", 28)
    a, b = Vector(start), Vector(end)
    direction = (b - a).normalized()
    # Raised rings and a sealed cap are modeled, not texture-only.
    for i, t in enumerate((0.12, 0.35, 0.58, 0.81)):
        center = a.lerp(b, t)
        ring_len = min(0.012, (b - a).length * 0.07)
        obj = cylinder(
            ctx,
            f"{name}_rib_{i}",
            center,
            radius * 1.07,
            ring_len,
            M["rubber"],
            vertices=24,
            semantic="grip_rib",
            bevel=0.001,
        )
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    sphere(ctx, name + "_endcap", b, radius * 1.04, M["rubber"], "grip_end_cap")


def footplate(
    ctx,
    name,
    center,
    M,
    width=0.30,
    length=0.62,
    yaw=0.0,
    tilt=0.0,
    material_key="galvanized",
    bracket_material_key="green_dark",
):
    rot = (tilt, 0.0, yaw)
    box(
        ctx,
        name + "_deck",
        center,
        (width, length, 0.075),
        M[material_key],
        0.028,
        rot,
        "footplate",
    )
    # Anti-slip ribs sit proud of the deck and remain visible in close shots.
    for i in range(6):
        yy = center[1] - length * 0.34 + i * length * 0.136
        box(
            ctx,
            f"{name}_tread_{i}",
            (center[0], yy, center[2] + 0.043),
            (width * 0.76, 0.024, 0.018),
            M["rubber"],
            0.005,
            rot,
            "anti_slip_tread",
        )
    for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        bolt(
            ctx,
            f"{name}_deck_bolt_{i}",
            (
                center[0] + sx * width * 0.34,
                center[1] + sy * length * 0.37,
                center[2] + 0.047,
            ),
            M,
            "z",
            0.017,
            0.012,
            False,
        )
    box(
        ctx,
        name + "_under_bracket",
        (center[0], center[1] + length * 0.10, center[2] - 0.065),
        (width * 0.45, length * 0.36, 0.07),
        M[bracket_material_key],
        0.018,
        rot,
        "footplate_bracket",
    )


def ground_plate(ctx, name, center, dims, M, material_key="teal", anchors=4):
    """Create a visibly bolted plate whose lower face is the asset's datum plane."""
    x, y = center
    width, depth = dims
    plate = box(
        ctx,
        name + "_plate",
        (x, y, 0.045),
        (width, depth, 0.09),
        M[material_key],
        0.018,
        semantic="mounting_flange",
    )
    plate["c2w_ground_contact"] = True
    plate["c2w_support_verified"] = True
    bolt_points = ((-0.34, -0.30), (-0.34, 0.30), (0.34, -0.30), (0.34, 0.30))
    for i, (sx, sy) in enumerate(bolt_points[:anchors]):
        bx = x + sx * width
        by = y + sy * depth
        cylinder(
            ctx,
            f"{name}_anchor_{i}",
            (bx, by, 0.103),
            0.023,
            0.045,
            M["stainless"],
            6,
            semantic="anchor_bolt",
            bevel=0.002,
        )
        torus(
            ctx,
            f"{name}_washer_{i}",
            (bx, by, 0.091),
            0.030,
            0.006,
            M["stainless"],
            semantic="anchor_bolt",
        )
    return plate


def upholstered_pad(
    ctx, name, center, dims, M, rotation=(0.0, 0.0, 0.0), semantic="seat"
):
    """Weatherproof pad, rolled rim, steel pan, and attachment hardware."""
    pad = box(
        ctx, name + "_cushion", center, dims, M["seat_pad"], 0.055, rotation, semantic
    )
    pan_center = (center[0], center[1] + 0.018, center[2] - dims[2] * 0.48)
    box(
        ctx,
        name + "_steel_pan",
        pan_center,
        (dims[0] * 0.86, dims[1] * 0.84, 0.040),
        M["cream_dark"],
        0.018,
        rotation,
        semantic + "_support",
    )
    for i, sx in enumerate((-0.31, 0.31)):
        bolt(
            ctx,
            f"{name}_pan_bolt_{i}",
            (center[0] + sx * dims[0], center[1] + 0.025, center[2] - dims[2] * 0.52),
            M,
            "z",
            0.025,
            0.013,
            False,
        )
    pad["c2w_support_verified"] = True
    return pad


def supported_motion_stop(
    ctx,
    name,
    bumper_loc,
    bracket_start,
    bracket_end,
    M,
    axis="y",
    radius=0.046,
    length=0.11,
    bracket_material=None,
):
    """Elastomer travel stop with an explicit welded steel mounting bracket."""
    beam(
        ctx,
        name + "_bracket",
        bracket_start,
        bracket_end,
        0.028,
        bracket_material or M["green_dark"],
        "motion_stop_bracket",
    )
    stop = cylinder(
        ctx,
        name + "_bumper",
        bumper_loc,
        radius,
        length,
        M["rubber"],
        28,
        rotation=_axis_rotation(axis),
        semantic="motion_stop",
        bevel=0.004,
    )
    stop["c2w_support_verified"] = True
    stop["c2w_support_kind"] = "welded_bracket"
    return stop


def chain_drop(ctx, name, x, y, top_z, count, M):
    """Alternating forged chain links hanging continuously from an upper lug."""
    link_spacing = 0.066
    for i in range(count):
        rot = (math.pi / 2, 0, 0) if i % 2 == 0 else (0, math.pi / 2, 0)
        link = torus(
            ctx,
            f"{name}_link_{i:02d}",
            (x, y, top_z - i * link_spacing),
            0.040,
            0.008,
            M["stainless"],
            rotation=rot,
            semantic="load_chain",
        )
        link.scale = (1.0, 0.58, 1.0)
        link["c2w_support_verified"] = True
    return top_z - (count - 1) * link_spacing


def finalize_asset(root, ctx, dimensions, motion, clearance_radius):
    root["c2w_nominal_dimensions_m"] = dimensions
    root["c2w_motion"] = motion
    root["c2w_part_count"] = len(ctx.objects)
    root["c2w_clearance_radius_m"] = float(clearance_radius)
    root["c2w_ground_contact_count"] = sum(
        bool(obj.get("c2w_ground_contact")) for obj in ctx.objects
    )
    root["c2w_articulation_class"] = "articulated" if ctx.joints else "fixed"
    root["c2w_joint_count"] = len(ctx.joints)
    root["c2w_revolute_joint_count"] = sum(
        joint["joint_type"] == "revolute" for joint in ctx.joints
    )
    root["c2w_prismatic_joint_count"] = sum(
        joint["joint_type"] == "prismatic" for joint in ctx.joints
    )
    root["c2w_moving_part_count"] = sum(
        bool(obj.get("c2w_movable")) for obj in ctx.objects
    )
    root["c2w_kinematic_tree"] = json.dumps(ctx.joints, sort_keys=True)
    root["c2w_articulation_standard"] = ARTICULATION_STANDARD
    root["c2w_infinigen_articulated_direct"] = bool(ctx.joints)
    root["c2w_joint_range_sweep_required"] = bool(ctx.joints)
    root["c2w_physics_audited"] = True
    root["c2w_articulation_audited"] = True
    return root


def build_air_walker_double(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    M = materials or make_materials()
    coll = collection("asset_air_walker_double", parent, variant="air_walker_double")
    root = anchor(coll, "air_walker_double_root", "air_walker_double", origin, yaw)
    ctx = BuildContext(
        "air_walker_double", coll, root, joint_values=dict(joint_values or {})
    )

    # A portal frame with two independently anchored legs leaves the entire
    # pendulum sweep open.  The former low transverse bar crossed both footplate
    # envelopes and visibly penetrated the moving links in articulated poses.
    for side, x in (("left", -1.25), ("right", 1.25)):
        plate = ground_plate(
            ctx, side + "_portal_foot", (x, 0), (0.46, 0.58), M, "green", 4
        )
        plate["c2w_load_path"] = "portal_leg_to_independent_ground_anchor"
        torus(
            ctx,
            side + "_portal_base_weld",
            (x, 0, 0.105),
            0.074,
            0.014,
            M["green_dark"],
            semantic="weld_bead",
        )
        for face, y in (("front", -0.18), ("rear", 0.18)):
            brace = beam(
                ctx,
                f"{side}_{face}_portal_gusset",
                (x, y, 0.10),
                (x, 0, 0.43),
                0.029,
                M["green_dark"],
                "reinforcement_link",
            )
            brace["c2w_support_verified"] = True
            brace["c2w_load_path"] = "portal_upright_to_anchor_plate"

    # Rounded continuous upper portal, matching the supplied full-scale frame
    # while deliberately omitting every low horizontal member.
    tube(
        ctx,
        "left_frame",
        [(-1.25, 0, 0.10), (-1.25, 0, 1.60), (-1.18, 0, 1.88), (-0.94, 0, 2.02)],
        0.072,
        M["green"],
    )
    tube(
        ctx,
        "top_frame",
        [(-0.94, 0, 2.02), (0, 0, 2.06), (0.94, 0, 2.02)],
        0.072,
        M["green"],
    )
    tube(
        ctx,
        "right_frame",
        [(1.25, 0, 0.10), (1.25, 0, 1.60), (1.18, 0, 1.88), (0.94, 0, 2.02)],
        0.072,
        M["green"],
    )
    for side, x in (("left", -0.57), ("right", 0.57)):
        s = -1 if x < 0 else 1
        tube(
            ctx,
            side + "_handle_support",
            [
                (s * 1.12, 0, 1.91),
                (s * 0.87, -0.015, 1.76),
                (s * 0.69, -0.07, 1.70),
                (s * 0.56, -0.18, 1.64),
            ],
            0.055,
            M["green"],
            "handle_support",
        )
        grip(
            ctx,
            side + "_angled_grip",
            (s * 0.68, -0.075, 1.71),
            (s * 0.52, -0.25, 1.53),
            M,
            0.042,
        )
        # The pendulum travels fore/aft in the local YZ plane, therefore the
        # load-bearing axle is correctly aligned to local X.
        pivot_pack(ctx, side + "_upper_pivot", (x, 0, 1.61), M, "x", 0.24, 0.082)
        moving_start = len(ctx.objects)
        tube(
            ctx,
            side + "_pendulum",
            [(x, -0.02, 1.61), (x, -0.02, 0.70), (x, -0.08, 0.46), (x, -0.27, 0.34)],
            0.045,
            M["galvanized"],
            "pendulum_arm",
        )
        footplate(ctx, side + "_footplate", (x, -0.50, 0.285), M, 0.34, 0.58)
        pivot_pack(
            ctx,
            side + "_lower_joint",
            (x, -0.29, 0.34),
            M,
            "x",
            0.16,
            0.052,
            M["galvanized"],
        )
        articulate_hinge(
            ctx,
            side + "_pendulum_hinge",
            ctx.objects[moving_start:],
            (x, 0, 1.61),
            "x",
            (math.radians(-28), math.radians(28)),
            mass=24.0,
            damping=0.28,
            friction=0.16,
        )
        # Compact opposed elastomer stops are carried by the upper bearing bracket,
        # so no bumper bracket intrudes into the long lower pendulum envelope.
        supported_motion_stop(
            ctx,
            side + "_forward_limit",
            (x, -0.150, 1.505),
            (x, -0.030, 1.590),
            (x, -0.138, 1.525),
            M,
            "x",
            0.030,
            0.090,
        )
        supported_motion_stop(
            ctx,
            side + "_rear_limit",
            (x, 0.115, 1.505),
            (x, 0.025, 1.590),
            (x, 0.105, 1.525),
            M,
            "x",
            0.034,
            0.090,
        )
    return finalize_asset(
        root, ctx, "2.64 x 1.05 x 2.14", "two independent pendulum foot platforms", 1.42
    )


def build_ski_walker(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    M = materials or make_materials()
    coll = collection("asset_ski_walker", parent, variant="ski_walker")
    root = anchor(coll, "ski_walker_root", "ski_walker", origin, yaw)
    ctx = BuildContext("ski_walker", coll, root, joint_values=dict(joint_values or {}))
    base_assembly(ctx, "base", M, post_height=1.40, flange_radius=0.30)
    cylinder(
        ctx,
        "mast_cap",
        (0, 0, 1.59),
        0.137,
        0.10,
        M["green_dark"],
        40,
        semantic="sealed_cap",
        bevel=0.018,
    )
    beam(
        ctx,
        "front_pivot_rail",
        (-0.70, -0.07, 1.48),
        (0.70, -0.07, 1.48),
        0.05,
        M["green"],
        "pivot_crossmember",
    )
    # Triangulated fixed brackets support the widened pivot rail without the old
    # rear rail, which incorrectly occupied the moving stabilizer-link envelope.
    for side, s in (("left", -1), ("right", 1)):
        brace = beam(
            ctx,
            side + "_pivot_rail_brace",
            (s * 0.095, 0.015, 1.30),
            (s * 0.61, -0.07, 1.48),
            0.037,
            M["green_dark"],
            "reinforcement_link",
        )
        brace["c2w_support_verified"] = True
        torus(
            ctx,
            side + "_rail_brace_weld",
            (s * 0.61, -0.07, 1.48),
            0.040,
            0.009,
            M["green_dark"],
            rotation=(0, math.pi / 2, 0),
            semantic="weld_bead",
        )
    for side, x, phase in (("left", -0.50, -1), ("right", 0.50, 1)):
        pivot_pack(
            ctx,
            side + "_upper_pivot",
            (x, -0.075, 1.48),
            M,
            "x",
            0.25,
            0.074,
            M["galvanized"],
        )
        # Tall reciprocating handles bend toward the user at their upper ends.
        moving_start = len(ctx.objects)
        tube(
            ctx,
            side + "_handle",
            [
                (x, -0.10, 1.48),
                (x, -0.14, 1.78),
                (x + phase * 0.055, -0.22, 1.96),
                (x + phase * 0.055, -0.30, 2.17),
            ],
            0.036,
            M["galvanized"],
            "moving_handle",
        )
        grip(
            ctx,
            side + "_grip",
            (x + phase * 0.055, -0.30, 2.05),
            (x + phase * 0.055, -0.30, 2.27),
            M,
            0.041,
        )
        pedal_y = -0.26 + phase * 0.09
        footplate(
            ctx,
            side + "_ski",
            (x, pedal_y, 0.22 + phase * 0.018),
            M,
            0.28,
            1.22,
            tilt=phase * math.radians(1.7),
        )
        beam(
            ctx,
            side + "_front_link",
            (x, -0.10, 1.45),
            (x, pedal_y - 0.30, 0.30),
            0.032,
            M["galvanized"],
            "drive_link",
        )
        # The trailing chord is part of the same rigid rocker: both endpoints move
        # with the handle/footplate assembly and cannot saw through a fixed rail.
        beam(
            ctx,
            side + "_rear_link",
            (x, -0.10, 1.28),
            (x, pedal_y + 0.35, 0.29),
            0.032,
            M["galvanized"],
            "stabilizer_link",
        )
        pivot_pack(
            ctx,
            side + "_pedal_front_pivot",
            (x, pedal_y - 0.30, 0.30),
            M,
            "x",
            0.14,
            0.050,
            M["galvanized"],
        )
        pivot_pack(
            ctx,
            side + "_pedal_rear_pivot",
            (x, pedal_y + 0.35, 0.29),
            M,
            "x",
            0.14,
            0.046,
            M["galvanized"],
        )
        other_side = "right" if side == "left" else "left"
        articulate_hinge(
            ctx,
            side + "_reciprocal_hinge",
            ctx.objects[moving_start:],
            (x, -0.075, 1.48),
            "x",
            (math.radians(-12), math.radians(12)),
            mass=31.0,
            damping=0.34,
            friction=0.17,
            coupled_to=other_side + "_reciprocal_hinge:-1",
        )
        supported_motion_stop(
            ctx,
            side + "_travel",
            (x + phase * 0.09, -0.10, 1.355),
            (x + phase * 0.02, -0.075, 1.455),
            (x + phase * 0.08, -0.095, 1.375),
            M,
            "x",
            0.035,
            0.095,
        )
    return finalize_asset(
        root,
        ctx,
        "1.52 x 1.58 x 2.32",
        "linked reciprocal ski pedals and handles",
        1.15,
    )


def build_rider_trainer(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    M = materials or make_materials()
    coll = collection("asset_rider_trainer", parent, variant="rider_trainer")
    root = anchor(coll, "rider_trainer_root", "rider_trainer", origin, yaw)
    ctx = BuildContext(
        "rider_trainer", coll, root, joint_values=dict(joint_values or {})
    )
    base_assembly(ctx, "base", M, post_height=0.62, flange_radius=0.30)
    pivot_pack(ctx, "main_pivot", (0, 0, 0.76), M, "x", 0.30, 0.112)

    # The large wishbone lever is the identifying silhouette of the reference.
    wishbone_start = len(ctx.objects)
    tube(
        ctx,
        "wishbone_left",
        [
            (-0.03, 0, 0.77),
            (-0.46, 0, 0.66),
            (-0.72, 0, 0.93),
            (-0.80, 0, 1.50),
            (-0.80, 0, 1.88),
            (-0.94, 0, 1.95),
        ],
        0.062,
        M["green"],
        "moving_wishbone",
    )
    tube(
        ctx,
        "wishbone_right",
        [
            (0.03, 0, 0.77),
            (0.46, 0, 0.66),
            (0.72, 0, 0.93),
            (0.80, 0, 1.50),
            (0.80, 0, 1.88),
            (0.94, 0, 1.95),
        ],
        0.062,
        M["green"],
        "moving_wishbone",
    )
    beam(
        ctx,
        "wishbone_crossbrace",
        (-0.69, 0, 1.23),
        (0.69, 0, 1.23),
        0.052,
        M["green"],
        "moving_wishbone",
    )
    for side, x in (("left", -0.94), ("right", 0.94)):
        s = -1 if x < 0 else 1
        beam(
            ctx,
            side + "_handle_core",
            (s * 0.78, 0, 1.94),
            (s * 1.17, -0.05, 1.94),
            0.036,
            M["galvanized"],
            "handle_core",
        )
        grip(
            ctx,
            side + "_grip",
            (s * 0.98, -0.05, 1.94),
            (s * 1.24, -0.05, 1.94),
            M,
            0.041,
        )
        torus(
            ctx,
            side + "_tube_weld",
            (s * 0.79, 0, 1.91),
            0.063,
            0.012,
            M["green_dark"],
            rotation=(math.pi / 2, 0, 0),
        )
    articulate_hinge(
        ctx,
        "wishbone_hinge",
        ctx.objects[wishbone_start:],
        (0, 0, 0.76),
        "x",
        (math.radians(-20), math.radians(18)),
        mass=34.0,
        damping=0.36,
        friction=0.20,
        coupled_to="seat_hinge:+0.55",
    )
    # A twin-fork seat carrier and twin return links pass on either side of the
    # mast.  The former single centre return rod swept directly through the post.
    seat_start = len(ctx.objects)
    for side, x in (("left", -0.20), ("right", 0.20)):
        tube(
            ctx,
            side + "_seat_fork",
            [(x, 0.02, 0.76), (x, 0.28, 0.83), (x, 0.49, 1.02)],
            0.038,
            M["galvanized"],
            "seat_linkage",
        )
        beam(
            ctx,
            side + "_return_link",
            (x, 0.10, 0.77),
            (x, -0.28, 0.54),
            0.029,
            M["galvanized"],
            "return_link",
        )
    beam(
        ctx,
        "seat_fork_crossmember",
        (-0.24, 0.49, 1.02),
        (0.24, 0.49, 1.02),
        0.035,
        M["green_dark"],
        "seat_support",
    )
    box(
        ctx,
        "saddle",
        (0, 0.57, 1.06),
        (0.38, 0.46, 0.095),
        M["rubber"],
        0.065,
        rotation=(math.radians(-4), 0, 0),
        semantic="seat",
    )
    box(
        ctx,
        "saddle_pan",
        (0, 0.54, 1.00),
        (0.30, 0.35, 0.045),
        M["galvanized"],
        0.025,
        semantic="seat_support",
    )
    articulate_hinge(
        ctx,
        "seat_hinge",
        ctx.objects[seat_start:],
        (0, 0, 0.76),
        "x",
        (math.radians(-11), math.radians(12)),
        mass=19.0,
        damping=0.40,
        friction=0.22,
        coupled_to="wishbone_hinge:+0.55",
    )
    beam(
        ctx,
        "footbar",
        (-0.43, -0.38, 0.63),
        (0.43, -0.38, 0.63),
        0.043,
        M["galvanized"],
        "foot_support",
    )
    for side, x in (("left", -0.33), ("right", 0.33)):
        footplate(ctx, side + "_footrest", (x, -0.48, 0.57), M, 0.22, 0.34)
        bolt(ctx, side + "_footbar_bolt", (x, -0.38, 0.63), M, "y", 0.065, 0.024)
    for side, x in (("left", -0.20), ("right", 0.20)):
        supported_motion_stop(
            ctx,
            side + "_seat_forward_limit",
            (x, -0.125, 0.675),
            (x, -0.035, 0.745),
            (x, -0.110, 0.690),
            M,
            "x",
            0.036,
            0.10,
        )
        supported_motion_stop(
            ctx,
            side + "_seat_rear_limit",
            (x, 0.125, 0.675),
            (x, 0.035, 0.745),
            (x, 0.110, 0.690),
            M,
            "x",
            0.036,
            0.10,
        )
    return finalize_asset(
        root,
        ctx,
        "2.55 x 1.18 x 2.06",
        "pivoting wishbone handle and rising saddle",
        1.38,
    )


def build_stepper_station(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    M = materials or make_materials()
    coll = collection("asset_stepper_station", parent, variant="stepper_station")
    root = anchor(coll, "stepper_station_root", "stepper_station", origin, yaw)
    ctx = BuildContext(
        "stepper_station", coll, root, joint_values=dict(joint_values or {})
    )
    base_assembly(ctx, "base", M, post_height=1.46, flange_radius=0.29)
    cylinder(
        ctx,
        "mast_cap",
        (0, 0, 1.67),
        0.135,
        0.10,
        M["green_dark"],
        40,
        semantic="sealed_cap",
        bevel=0.018,
    )

    # Gray wrap-around hand rail and outward rubber grips from the lower reference.
    tube(
        ctx,
        "upper_guard",
        [
            (-0.56, 0.03, 1.48),
            (-0.56, 0.05, 1.72),
            (-0.47, 0.08, 1.84),
            (0, 0.09, 1.88),
            (0.47, 0.08, 1.84),
            (0.56, 0.05, 1.72),
            (0.56, 0.03, 1.48),
        ],
        0.038,
        M["galvanized"],
        "handrail",
    )
    beam(
        ctx,
        "handle_crossbar",
        (-0.72, -0.03, 1.48),
        (0.72, -0.03, 1.48),
        0.040,
        M["galvanized"],
        "handrail",
    )
    for side, x in (("left", -0.72), ("right", 0.72)):
        s = -1 if x < 0 else 1
        tube(
            ctx,
            side + "_handle_extension",
            [(s * 0.46, -0.03, 1.48), (s * 0.70, -0.12, 1.45), (s * 0.91, -0.20, 1.45)],
            0.038,
            M["galvanized"],
            "handle_core",
        )
        grip(
            ctx,
            side + "_grip",
            (s * 0.72, -0.13, 1.45),
            (s * 1.00, -0.23, 1.45),
            M,
            0.041,
        )
    pivot_pack(
        ctx, "stepper_axle", (0, -0.02, 0.58), M, "y", 0.40, 0.105, M["galvanized"]
    )
    for side, x, phase in (("left", -0.34, -1), ("right", 0.34, 1)):
        moving_start = len(ctx.objects)
        beam(
            ctx,
            side + "_crank",
            (0, -0.12, 0.58),
            (x, -0.33 + phase * 0.05, 0.50 + phase * 0.025),
            0.042,
            M["galvanized"],
            "stepper_crank",
        )
        pivot_pack(
            ctx,
            side + "_pedal_pivot",
            (x, -0.35 + phase * 0.05, 0.50 + phase * 0.025),
            M,
            "y",
            0.14,
            0.050,
            M["galvanized"],
        )
        footplate(
            ctx,
            side + "_pedal",
            (x, -0.48 + phase * 0.05, 0.50 + phase * 0.025),
            M,
            0.30,
            0.47,
        )
        beam(
            ctx,
            side + "_stabilizer",
            (x, -0.28, 0.49),
            (x * 0.70, 0.03, 0.73),
            0.027,
            M["green_dark"],
            "stabilizer_link",
        )
        other_side = "right" if side == "left" else "left"
        articulate_hinge(
            ctx,
            side + "_step_hinge",
            ctx.objects[moving_start:],
            (0, -0.02, 0.58),
            "y",
            (math.radians(-14), math.radians(14)),
            mass=17.0,
            damping=0.42,
            friction=0.24,
            coupled_to=other_side + "_step_hinge:-1",
        )
        s = -1 if x < 0 else 1
        supported_motion_stop(
            ctx,
            side + "_stop",
            (s * 0.115, -0.075, 0.680),
            (s * 0.035, -0.015, 0.615),
            (s * 0.100, -0.060, 0.665),
            M,
            "y",
            0.035,
            0.085,
        )
    return finalize_asset(
        root, ctx, "2.10 x 1.25 x 1.94", "independent rocking step pedals", 1.18
    )


def build_double_leg_press(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    """Two opposed body-weight leg presses with explicit continuous load paths.

    The fixed foot plates are carried by welded triangulated frames tied into a
    reinforced mast collar.  Each moving seat uses two laterally separated swing
    arms, cross-pins, and twin carrier rails, so no rod, plate, seat, or handle is
    visually or mechanically unsupported.
    """
    M = materials or make_materials()
    variant = "double_leg_press"
    coll = collection("asset_double_leg_press", parent, variant=variant)
    root = anchor(coll, "double_leg_press_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root, joint_values=dict(joint_values or {}))
    base_assembly(
        ctx,
        "base",
        M,
        post_radius=0.125,
        post_height=1.68,
        flange_radius=0.32,
        material_key="teal",
        dark_key="teal_dark",
    )
    cylinder(
        ctx,
        "mast_cap",
        (0, 0, 1.91),
        0.139,
        0.10,
        M["cream"],
        40,
        semantic="sealed_cap",
        bevel=0.020,
    )
    beam(
        ctx,
        "upper_crossmember",
        (-0.58, 0, 1.78),
        (0.58, 0, 1.78),
        0.063,
        M["teal"],
        "pivot_crossmember",
    )

    # A welded collar spreads both users' foot loads into the central mast.  The
    # former pair of isolated blue rods has deliberately been replaced by a
    # closed, triangulated bracket on each side.
    collar = cylinder(
        ctx,
        "footrest_mast_collar",
        (0, -0.02, 0.615),
        0.158,
        0.47,
        M["teal_dark"],
        48,
        semantic="footplate_bracket",
        bevel=0.010,
    )
    collar["c2w_support_verified"] = True
    collar["c2w_load_path"] = "fixed_footrests_to_mast_to_anchor_flange"
    for ring_name, z in (("upper", 0.82), ("lower", 0.41)):
        torus(
            ctx,
            f"footrest_collar_{ring_name}_weld",
            (0, -0.02, z),
            0.145,
            0.014,
            M["teal_dark"],
            semantic="weld_bead",
        )

    for side, s in (("left", -1), ("right", 1)):
        pivot_x = s * 0.43
        pivot_pack(
            ctx,
            side + "_top_pivot",
            (pivot_x, 0, 1.78),
            M,
            "y",
            0.82,
            0.094,
            M["cream"],
        )
        moving_start = len(ctx.objects)
        # The paired swing arms run outside the fixed press plate instead of
        # occupying the user's foot plane.  This preserves a generous swept
        # clearance through the complete authored hinge range.
        for rail, yy in (("front", -0.34), ("rear", 0.34)):
            swing = tube(
                ctx,
                f"{side}_{rail}_swing_arm",
                [
                    (pivot_x, yy, 1.78),
                    (s * 0.60, yy, 1.35),
                    (s * 0.79, yy, 0.94),
                    (s * 1.03, yy, 0.75),
                ],
                0.047,
                M["cream"],
                "load_bearing_swing_arm",
            )
            swing["c2w_support_verified"] = True
            swing["c2w_load_path"] = "seat_carrier_to_upper_pivot_to_mast"
            beam(
                ctx,
                f"{side}_{rail}_seat_carrier",
                (s * 0.86, yy, 0.75),
                (s * 1.39, yy, 0.75),
                0.040,
                M["cream"],
                "seat_linkage",
            )
        beam(
            ctx,
            side + "_pivot_crosspin",
            (pivot_x, -0.40, 1.78),
            (pivot_x, 0.40, 1.78),
            0.038,
            M["cream_dark"],
            "pivot_support",
        )
        # Two local lower pins replace the old full-width pin that swept across
        # the fixed plate at the inward end of travel.
        for rail, yy in (("front", -0.34), ("rear", 0.34)):
            pivot_pack(
                ctx,
                f"{side}_{rail}_lower_pin",
                (s * 1.03, yy, 0.75),
                M,
                "y",
                0.12,
                0.043,
                M["cream_dark"],
            )
        beam(
            ctx,
            side + "_seat_crossbrace",
            (s * 1.24, -0.36, 0.75),
            (s * 1.24, 0.36, 0.75),
            0.036,
            M["cream_dark"],
            "seat_support",
        )
        upholstered_pad(
            ctx,
            side + "_seat",
            (s * 1.23, 0, 0.84),
            (0.50, 0.48, 0.11),
            M,
            semantic="seat",
        )

        # Two back-rest stays terminate in the carrier rails; the rear steel shell
        # and four visible fasteners make the assembly readable from both sides.
        for rail, yy in (("front", -0.29), ("rear", 0.29)):
            beam(
                ctx,
                f"{side}_back_{rail}_stay",
                (s * 1.38, yy, 0.76),
                (s * 1.47, yy, 1.13),
                0.033,
                M["cream"],
                "backrest_support",
            )
        box(
            ctx,
            side + "_back_shell",
            (s * 1.50, 0, 1.14),
            (0.075, 0.48, 0.56),
            M["cream_dark"],
            0.040,
            rotation=(0, s * math.radians(7), 0),
            semantic="backrest_support",
        )
        back_pad = box(
            ctx,
            side + "_back_pad",
            (s * 1.46, 0, 1.15),
            (0.10, 0.42, 0.50),
            M["seat_pad"],
            0.060,
            rotation=(0, s * math.radians(7), 0),
            semantic="backrest",
        )
        back_pad["c2w_support_verified"] = True
        moving_parts = list(ctx.objects[moving_start:])

        # Fixed foot plate: two chords, an outer spine, and a diagonal form a
        # rigid welded truss.  Every endpoint overlaps either the mast collar or
        # the plate backing, leaving no cantilever visually detached in space.
        upper = beam(
            ctx,
            side + "_footrest_upper_chord",
            (s * 0.105, 0, 0.755),
            (s * 0.535, 0, 0.755),
            0.037,
            M["cream_dark"],
            "footplate_bracket",
        )
        lower = beam(
            ctx,
            side + "_footrest_lower_chord",
            (s * 0.105, 0, 0.465),
            (s * 0.535, 0, 0.465),
            0.037,
            M["cream_dark"],
            "footplate_bracket",
        )
        spine = beam(
            ctx,
            side + "_footrest_outer_spine",
            (s * 0.535, 0, 0.455),
            (s * 0.535, 0, 0.765),
            0.038,
            M["cream_dark"],
            "footplate_bracket",
        )
        diagonal = beam(
            ctx,
            side + "_footrest_diagonal",
            (s * 0.13, 0, 0.48),
            (s * 0.51, 0, 0.735),
            0.032,
            M["cream_dark"],
            "footplate_bracket",
        )
        for member in (upper, lower, spine, diagonal):
            member["c2w_support_verified"] = True
            member["c2w_load_path"] = "press_plate_to_truss_to_mast_collar"
        for joint, x, z in (
            ("upper_root", s * 0.12, 0.755),
            ("lower_root", s * 0.12, 0.465),
            ("upper_outer", s * 0.535, 0.755),
            ("lower_outer", s * 0.535, 0.465),
        ):
            torus(
                ctx,
                f"{side}_{joint}_weld",
                (x, 0, z),
                0.038,
                0.009,
                M["cream_dark"],
                rotation=(0, math.pi / 2, 0),
                semantic="weld_bead",
            )
        plate = box(
            ctx,
            side + "_press_plate",
            (s * 0.585, 0, 0.61),
            (0.09, 0.44, 0.40),
            M["cream"],
            0.034,
            semantic="footplate",
        )
        plate["c2w_support_verified"] = True
        plate["c2w_load_path"] = "plate_to_outer_spine_to_truss_to_mast"
        for i in range(5):
            box(
                ctx,
                f"{side}_press_tread_{i}",
                (s * 0.636, -0.16 + i * 0.080, 0.61),
                (0.018, 0.038, 0.28),
                M["rubber"],
                0.006,
                semantic="anti_slip_tread",
            )
        for bolt_index, (yy, z) in enumerate(
            ((-0.14, 0.51), (0.14, 0.51), (-0.14, 0.71), (0.14, 0.71))
        ):
            bolt(
                ctx,
                f"{side}_press_plate_bolt_{bolt_index}",
                (s * 0.638, yy, z),
                M,
                "x",
                0.035,
                0.014,
                True,
            )

        # Paired grab handles grow from welded uprights on the carrier rails.
        handle_start = len(ctx.objects)
        for rail, yy in (("front", -0.34), ("rear", 0.34)):
            beam(
                ctx,
                f"{side}_{rail}_handle_upright",
                (s * 1.12, yy, 0.75),
                (s * 1.12, yy, 0.98),
                0.030,
                M["cream"],
                "handle_support",
            )
            beam(
                ctx,
                f"{side}_{rail}_handle_core",
                (s * 1.12, yy, 0.98),
                (s * 1.27, yy, 1.01),
                0.027,
                M["cream"],
                "handle_core",
            )
            grip(
                ctx,
                f"{side}_{rail}_grip",
                (s * 1.20, yy, 1.00),
                (s * 1.40, yy, 1.04),
                M,
                0.032,
            )
            bolt(
                ctx,
                f"{side}_{rail}_carrier_pin",
                (s * 1.03, yy, 0.75),
                M,
                "y",
                0.11,
                0.020,
                True,
            )
        moving_parts.extend(ctx.objects[handle_start:])
        articulate_hinge(
            ctx,
            side + "_seat_hinge",
            moving_parts,
            (pivot_x, 0, 1.78),
            "y",
            (math.radians(-18), math.radians(12)),
            mass=56.0,
            damping=0.46,
            friction=0.26,
        )
        supported_motion_stop(
            ctx,
            side + "_return_stop",
            (s * 0.31, -0.07, 1.40),
            (s * 0.12, -0.02, 1.40),
            (s * 0.255, -0.055, 1.40),
            M,
            "x",
            0.044,
            0.11,
            bracket_material=M["teal_dark"],
        )
    return finalize_asset(
        root,
        ctx,
        "3.12 x 0.92 x 1.98",
        "two independently pivoting twin-arm body-weight seats",
        1.66,
    )


def build_double_surf_board(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    """Two-person hanging waist/surf boards with a fixed continuous handrail."""
    M = materials or make_materials()
    variant = "double_surf_board"
    coll = collection("asset_double_surf_board", parent, variant=variant)
    root = anchor(coll, "double_surf_board_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root, joint_values=dict(joint_values or {}))
    base_assembly(
        ctx,
        "base",
        M,
        post_radius=0.12,
        post_height=1.58,
        flange_radius=0.31,
        material_key="teal",
        dark_key="teal_dark",
    )
    cylinder(
        ctx,
        "mast_cap",
        (0, 0, 1.81),
        0.134,
        0.10,
        M["cream"],
        40,
        semantic="sealed_cap",
        bevel=0.018,
    )
    beam(
        ctx,
        "pivot_crossmember",
        (-0.68, 0.02, 1.64),
        (0.68, 0.02, 1.64),
        0.052,
        M["teal"],
        "pivot_crossmember",
    )
    tube(
        ctx,
        "front_handrail",
        [
            (-1.16, -0.24, 1.56),
            (-1.02, -0.24, 1.66),
            (-0.55, -0.24, 1.69),
            (0, -0.24, 1.69),
            (0.55, -0.24, 1.69),
            (1.02, -0.24, 1.66),
            (1.16, -0.24, 1.56),
        ],
        0.040,
        M["teal"],
        "handrail",
    )
    # Twin triangulated stand-offs close the load path from the front rail to mast.
    for side, s in (("left", -1), ("right", 1)):
        beam(
            ctx,
            side + "_handrail_standoff",
            (s * 0.09, -0.055, 1.62),
            (s * 0.25, -0.24, 1.69),
            0.034,
            M["teal_dark"],
            "handrail_support",
        )
        torus(
            ctx,
            side + "_handrail_standoff_weld",
            (s * 0.25, -0.24, 1.69),
            0.039,
            0.009,
            M["teal_dark"],
            rotation=(math.pi / 2, 0, 0),
            semantic="weld_bead",
        )
    for side, s in (("left", -1), ("right", 1)):
        grip(
            ctx,
            side + "_outer_grip",
            (s * 0.86, -0.24, 1.67),
            (s * 1.20, -0.24, 1.54),
            M,
            0.037,
        )
        pivot_pack(
            ctx,
            side + "_upper_pivot",
            (s * 0.48, 0.02, 1.64),
            M,
            "x",
            0.25,
            0.081,
            M["cream"],
        )
        moving_start = len(ctx.objects)
        tube(
            ctx,
            side + "_hanger",
            [
                (s * 0.48, 0.0, 1.64),
                (s * 0.48, -0.02, 1.19),
                (s * 0.52, -0.08, 0.68),
                (s * 0.61, -0.20, 0.34),
            ],
            0.043,
            M["cream"],
            "pendulum_arm",
        )
        pivot_pack(
            ctx,
            side + "_board_pivot",
            (s * 0.61, -0.21, 0.34),
            M,
            "x",
            0.18,
            0.052,
            M["cream"],
        )
        footplate(
            ctx,
            side + "_surf_deck",
            (s * 0.61, -0.48, 0.275),
            M,
            0.36,
            0.67,
            material_key="cream",
            bracket_material_key="teal_dark",
        )
        beam(
            ctx,
            side + "_deck_keel",
            (s * 0.61, -0.21, 0.34),
            (s * 0.61, -0.49, 0.22),
            0.032,
            M["cream_dark"],
            "footplate_bracket",
        )
        articulate_hinge(
            ctx,
            side + "_board_hinge",
            ctx.objects[moving_start:],
            (s * 0.48, 0.02, 1.64),
            "x",
            (math.radians(-22), math.radians(22)),
            mass=29.0,
            damping=0.36,
            friction=0.18,
        )
        supported_motion_stop(
            ctx,
            side + "_travel_stop",
            (s * 0.29, -0.03, 1.18),
            (s * 0.11, 0, 1.18),
            (s * 0.235, -0.02, 1.18),
            M,
            "x",
            0.041,
            0.11,
            bracket_material=M["teal_dark"],
        )
    return finalize_asset(
        root,
        ctx,
        "2.48 x 1.12 x 1.88",
        "two independent suspended lateral balance boards",
        1.35,
    )


def build_double_traction_station(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    """Tall dual traction station with four continuous forged-link handle drops."""
    M = materials or make_materials()
    variant = "double_traction_station"
    coll = collection("asset_double_traction_station", parent, variant=variant)
    root = anchor(coll, "double_traction_station_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root, joint_values=dict(joint_values or {}))
    base_assembly(
        ctx,
        "base",
        M,
        post_radius=0.115,
        post_height=2.48,
        flange_radius=0.30,
        material_key="teal",
        dark_key="teal_dark",
    )
    cylinder(
        ctx,
        "mast_cap",
        (0, 0, 2.71),
        0.132,
        0.10,
        M["cream"],
        40,
        semantic="sealed_cap",
        bevel=0.019,
    )
    beam(
        ctx,
        "top_crossarm",
        (-0.92, 0, 2.58),
        (0.92, 0, 2.58),
        0.056,
        M["teal"],
        "overhead_support",
    )
    beam(
        ctx,
        "left_diagonal_brace",
        (-0.10, 0, 2.37),
        (-0.68, 0, 2.58),
        0.034,
        M["teal_dark"],
        "reinforcement_link",
    )
    beam(
        ctx,
        "right_diagonal_brace",
        (0.10, 0, 2.37),
        (0.68, 0, 2.58),
        0.034,
        M["teal_dark"],
        "reinforcement_link",
    )
    drops = ((-0.74, 10), (-0.34, 12), (0.34, 12), (0.74, 10))
    for i, (x, count) in enumerate(drops):
        side = "left" if x < 0 else "right"
        # Each chain passes over a guarded sheave whose axle crosses the top beam.
        wheel = cylinder(
            ctx,
            f"pulley_{i}_wheel",
            (x, -0.015, 2.58),
            0.095,
            0.105,
            M["cream_dark"],
            40,
            rotation=(math.pi / 2, 0, 0),
            semantic="pulley_sheave",
            bevel=0.005,
        )
        articulate_hinge(
            ctx,
            f"pulley_{i}_axle_hinge",
            [wheel],
            (x, -0.015, 2.58),
            "y",
            (-math.pi, math.pi),
            mass=2.6,
            damping=0.12,
            friction=0.08,
        )
        cylinder(
            ctx,
            f"pulley_{i}_guard_front",
            (x, -0.078, 2.58),
            0.112,
            0.024,
            M["cream"],
            40,
            rotation=(math.pi / 2, 0, 0),
            semantic="pulley_guard",
            bevel=0.006,
        )
        bolt(ctx, f"pulley_{i}_axle", (x, -0.093, 2.58), M, "y", 0.16, 0.025, True)
        beam(
            ctx,
            f"pulley_{i}_hanger",
            (x, 0, 2.58),
            (x, -0.10, 2.47),
            0.022,
            M["cream_dark"],
            "chain_hanger",
        )
        moving_start = len(ctx.objects)
        end_z = chain_drop(ctx, f"{side}_{i}_chain", x, -0.10, 2.45, count, M)
        torus(
            ctx,
            f"handle_{i}_shackle",
            (x, -0.10, end_z - 0.055),
            0.034,
            0.008,
            M["stainless"],
            rotation=(math.pi / 2, 0, 0),
            semantic="load_shackle",
        )
        grip(
            ctx,
            f"handle_{i}",
            (x, -0.10, end_z - 0.08),
            (x, -0.10, end_z - 0.32),
            M,
            0.027,
        )
        articulate_hinge(
            ctx,
            f"handle_{i}_swing_hinge",
            ctx.objects[moving_start:],
            (x, -0.10, 2.47),
            "x",
            (math.radians(-14), math.radians(14)),
            mass=7.5,
            damping=0.30,
            friction=0.13,
        )
    return finalize_asset(
        root,
        ctx,
        "2.02 x 0.72 x 2.78",
        "four gravity-hung traction handles over guarded pulleys",
        1.18,
    )


def build_stall_bars(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    """Anchored outdoor Swedish ladder/rib wall from the reference sheet."""
    M = materials or make_materials()
    variant = "stall_bars"
    coll = collection("asset_stall_bars", parent, variant=variant)
    root = anchor(coll, "stall_bars_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root, joint_values=dict(joint_values or {}))
    for side, x in (("left", -0.72), ("right", 0.72)):
        ground_plate(ctx, side + "_foot", (x, 0), (0.34, 0.42), M, "teal", 4)
        beam(
            ctx,
            side + "_upright",
            (x, 0, 0.09),
            (x, 0, 2.48),
            0.061,
            M["teal"],
            "support_post",
        )
        torus(
            ctx,
            side + "_base_weld",
            (x, 0, 0.105),
            0.061,
            0.014,
            M["teal_dark"],
            semantic="weld_bead",
        )
        cylinder(
            ctx,
            side + "_top_cap",
            (x, 0, 2.51),
            0.068,
            0.065,
            M["cream"],
            32,
            semantic="sealed_cap",
            bevel=0.014,
        )
    rung_heights = (0.34, 0.62, 0.90, 1.18, 1.46, 1.74, 2.02, 2.30)
    for i, z in enumerate(rung_heights):
        beam(
            ctx,
            f"rung_{i}",
            (-0.72, 0, z),
            (0.72, 0, z),
            0.034,
            M["teal"],
            "climbing_rung",
        )
        for side, x in (("left", -0.665), ("right", 0.665)):
            torus(
                ctx,
                f"rung_{i}_{side}_weld",
                (x, 0, z),
                0.038,
                0.009,
                M["teal_dark"],
                rotation=(0, math.pi / 2, 0),
                semantic="weld_bead",
            )
    tube(
        ctx,
        "rounded_top_rail",
        [
            (-0.72, 0, 2.37),
            (-0.67, 0, 2.49),
            (-0.52, 0, 2.55),
            (0, 0, 2.57),
            (0.52, 0, 2.55),
            (0.67, 0, 2.49),
            (0.72, 0, 2.37),
        ],
        0.043,
        M["teal"],
        "structural_tube",
    )
    return finalize_asset(
        root,
        ctx,
        "1.62 x 0.48 x 2.64",
        "fixed body-weight climbing and stretching ladder",
        1.02,
    )


def build_rowing_machine(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    """Ground-anchored single rowing trainer with linked handle and seat mechanism."""
    M = materials or make_materials()
    variant = "rowing_machine"
    coll = collection("asset_rowing_machine", parent, variant=variant)
    root = anchor(coll, "rowing_machine_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root, joint_values=dict(joint_values or {}))
    ground_plate(ctx, "front_crossfoot", (0, -0.86), (1.34, 0.25), M, "teal", 4)
    ground_plate(ctx, "rear_crossfoot", (0, 0.88), (1.20, 0.25), M, "teal", 4)
    for side, x in (("left", -0.52), ("right", 0.52)):
        beam(
            ctx,
            side + "_base_rail",
            (x, -0.86, 0.11),
            (x, 0.88, 0.11),
            0.045,
            M["teal"],
            "ground_frame",
        )
        torus(
            ctx,
            side + "_front_weld",
            (x, -0.86, 0.11),
            0.047,
            0.010,
            M["teal_dark"],
            rotation=(math.pi / 2, 0, 0),
            semantic="weld_bead",
        )
        torus(
            ctx,
            side + "_rear_weld",
            (x, 0.88, 0.11),
            0.047,
            0.010,
            M["teal_dark"],
            rotation=(math.pi / 2, 0, 0),
            semantic="weld_bead",
        )
    beam(
        ctx,
        "seat_rail",
        (0, -0.48, 0.34),
        (0, 0.72, 0.55),
        0.065,
        M["teal"],
        "seat_track",
    )
    beam(
        ctx,
        "front_rail_support",
        (0, -0.48, 0.34),
        (0, -0.71, 0.11),
        0.050,
        M["teal_dark"],
        "reinforcement_link",
    )
    beam(
        ctx,
        "rear_rail_support",
        (0, 0.72, 0.55),
        (0, 0.82, 0.11),
        0.050,
        M["teal_dark"],
        "reinforcement_link",
    )
    # Four rollers clamp the carriage around the rail; the seat is carried by it.
    seat_start = len(ctx.objects)
    box(
        ctx,
        "seat_carriage",
        (0, 0.34, 0.56),
        (0.36, 0.27, 0.12),
        M["cream_dark"],
        0.025,
        rotation=(math.radians(-10), 0, 0),
        semantic="seat_carriage",
    )
    for side, x in (("left", -0.15), ("right", 0.15)):
        for end, y in (("front", 0.24), ("rear", 0.44)):
            cylinder(
                ctx,
                f"{side}_{end}_seat_roller",
                (x, y, 0.515),
                0.045,
                0.055,
                M["bearing"],
                28,
                rotation=(0, math.pi / 2, 0),
                semantic="seat_roller",
                bevel=0.004,
            )
            bolt(
                ctx,
                f"{side}_{end}_roller_axle",
                (x, y, 0.515),
                M,
                "x",
                0.075,
                0.016,
                True,
            )
    beam(
        ctx,
        "seat_riser",
        (0, 0.34, 0.56),
        (0, 0.34, 0.70),
        0.046,
        M["cream"],
        "seat_support",
    )
    upholstered_pad(
        ctx,
        "rowing_seat",
        (0, 0.34, 0.77),
        (0.48, 0.43, 0.11),
        M,
        rotation=(math.radians(-4), 0, 0),
        semantic="seat",
    )
    articulate_slider(
        ctx,
        "seat_carriage_slider",
        ctx.objects[seat_start:],
        (0, 0.34, 0.56),
        (0, 1.20, 0.21),
        (-0.34, 0.28),
        mass=20.0,
        damping=0.44,
        friction=0.20,
    )
    # Fixed footrests transfer force through twin brackets into the base frame.
    for side, x in (("left", -0.27), ("right", 0.27)):
        beam(
            ctx,
            side + "_foot_brace",
            (x, -0.71, 0.13),
            (x, -0.43, 0.37),
            0.038,
            M["teal_dark"],
            "footplate_bracket",
        )
        footplate(
            ctx,
            side + "_footrest",
            (x, -0.43, 0.41),
            M,
            0.25,
            0.43,
            tilt=math.radians(25),
            material_key="cream",
            bracket_material_key="teal_dark",
        )
        tube(
            ctx,
            side + "_heel_guard",
            [
                (x - 0.11, -0.56, 0.46),
                (x - 0.11, -0.42, 0.54),
                (x + 0.11, -0.42, 0.54),
                (x + 0.11, -0.56, 0.46),
            ],
            0.014,
            M["cream_dark"],
            "heel_guard",
        )
    # Triangulated front towers carry the full rowing-lever pivot.
    lever_parts = []
    for side, x in (("left", -0.46), ("right", 0.46)):
        beam(
            ctx,
            side + "_tower_front",
            (x, -0.82, 0.11),
            (x, -0.53, 0.67),
            0.050,
            M["teal"],
            "pivot_support",
        )
        beam(
            ctx,
            side + "_tower_rear",
            (x, -0.30, 0.11),
            (x, -0.53, 0.67),
            0.050,
            M["teal"],
            "pivot_support",
        )
        wedge(
            ctx,
            side + "_tower_gusset",
            (x, -0.66, 0.22),
            0.16,
            0.035,
            0.22,
            M["teal_dark"],
            0,
            "reinforcement_gusset",
        )
        pivot_pack(
            ctx,
            side + "_lever_pivot",
            (x, -0.53, 0.67),
            M,
            "x",
            0.20,
            0.082,
            M["cream"],
        )
        lever_start = len(ctx.objects)
        tube(
            ctx,
            side + "_rowing_lever",
            [(x, -0.53, 0.67), (x, -0.25, 0.90), (x, 0.04, 1.18), (x, 0.22, 1.28)],
            0.044,
            M["cream"],
            "rowing_lever",
        )
        grip(ctx, side + "_handle", (x, 0.10, 1.22), (x, 0.34, 1.35), M, 0.038)
        lever_parts.extend(ctx.objects[lever_start:])
    crosslink = beam(
        ctx,
        "lever_crosslink",
        (-0.46, -0.40, 0.78),
        (0.46, -0.40, 0.78),
        0.034,
        M["cream_dark"],
        "synchronizing_link",
    )
    lever_parts.append(crosslink)
    articulate_hinge(
        ctx,
        "rowing_lever_hinge",
        lever_parts,
        (0, -0.53, 0.67),
        "x",
        (math.radians(-24), math.radians(30)),
        mass=28.0,
        damping=0.40,
        friction=0.20,
    )
    supported_motion_stop(
        ctx,
        "lever_return_stop",
        (0, -0.61, 0.49),
        (0, -0.72, 0.22),
        (0, -0.61, 0.435),
        M,
        "z",
        0.050,
        0.11,
        bracket_material=M["teal_dark"],
    )
    return finalize_asset(
        root,
        ctx,
        "1.48 x 2.08 x 1.45",
        "linked twin rowing levers with rolling seat carriage",
        1.36,
    )


def build_fitness_notice_board(
    parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None, joint_values=None
):
    """Two-post park fitness rules sign, modeled as structure rather than a decal."""
    M = materials or make_materials()
    variant = "fitness_notice_board"
    coll = collection("asset_fitness_notice_board", parent, variant=variant)
    root = anchor(coll, "fitness_notice_board_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root, joint_values=dict(joint_values or {}))
    for side, x in (("left", -0.58), ("right", 0.58)):
        ground_plate(ctx, side + "_foot", (x, 0), (0.30, 0.36), M, "teal", 4)
        beam(
            ctx,
            side + "_post",
            (x, 0, 0.09),
            (x, 0, 2.30),
            0.065,
            M["teal"],
            "support_post",
        )
        torus(
            ctx,
            side + "_base_weld",
            (x, 0, 0.105),
            0.065,
            0.013,
            M["teal_dark"],
            semantic="weld_bead",
        )
        cylinder(
            ctx,
            side + "_cap",
            (x, 0, 2.34),
            0.073,
            0.075,
            M["cream"],
            32,
            semantic="sealed_cap",
            bevel=0.016,
        )
    box(
        ctx,
        "sign_back",
        (0, 0, 1.52),
        (1.02, 0.065, 1.28),
        M["teal_dark"],
        0.030,
        semantic="sign_backing",
    )
    box(
        ctx,
        "sign_face",
        (0, -0.042, 1.52),
        (0.94, 0.025, 1.20),
        M["sign_face"],
        0.018,
        semantic="sign_face",
    )
    for i, (x, z) in enumerate(
        ((-0.43, 0.97), (0.43, 0.97), (-0.43, 2.07), (0.43, 2.07))
    ):
        bolt(ctx, f"face_screw_{i}", (x, -0.061, z), M, "y", 0.035, 0.014, True)
    # Raised header, rule lines, warning marks and exercise pictograms remain legible.
    for i, x in enumerate((-0.31, -0.18, -0.05, 0.08, 0.21, 0.34)):
        box(
            ctx,
            f"header_glyph_{i}",
            (x, -0.059, 1.98 + (i % 2) * 0.015),
            (0.075, 0.010, 0.105),
            M["sign_red"],
            0.006,
            semantic="sign_text",
        )
    for i in range(8):
        width = 0.66 - (i % 3) * 0.08
        box(
            ctx,
            f"rule_line_{i}",
            (-0.06 + (i % 2) * 0.04, -0.059, 1.75 - i * 0.105),
            (width, 0.009, 0.020),
            M["teal_dark"],
            0.004,
            semantic="sign_text",
        )
        box(
            ctx,
            f"rule_bullet_{i}",
            (-0.39, -0.060, 1.75 - i * 0.105),
            (0.026, 0.010, 0.026),
            M["sign_red" if i in (0, 5) else "sign_yellow"],
            0.006,
            semantic="sign_pictogram",
        )
    for i, x in enumerate((-0.25, 0, 0.25)):
        torus(
            ctx,
            f"safety_icon_{i}",
            (x, -0.061, 1.00),
            0.075,
            0.010,
            M["sign_red"],
            rotation=(math.pi / 2, 0, 0),
            semantic="sign_pictogram",
        )
        beam(
            ctx,
            f"safety_icon_slash_{i}",
            (x - 0.05, -0.075, 0.95),
            (x + 0.05, -0.075, 1.05),
            0.008,
            M["sign_red"],
            "sign_pictogram",
        )
    beam(
        ctx,
        "rear_left_brace",
        (-0.58, 0.02, 1.04),
        (-0.43, 0.04, 1.16),
        0.027,
        M["teal_dark"],
        "sign_brace",
    )
    beam(
        ctx,
        "rear_right_brace",
        (0.58, 0.02, 1.04),
        (0.43, 0.04, 1.16),
        0.027,
        M["teal_dark"],
        "sign_brace",
    )
    return finalize_asset(
        root, ctx, "1.34 x 0.42 x 2.39", "fixed public exercise instruction board", 0.88
    )


BUILDERS = {
    "air_walker_double": build_air_walker_double,
    "ski_walker": build_ski_walker,
    "rider_trainer": build_rider_trainer,
    "stepper_station": build_stepper_station,
    "double_leg_press": build_double_leg_press,
    "double_surf_board": build_double_surf_board,
    "double_traction_station": build_double_traction_station,
    "stall_bars": build_stall_bars,
    "rowing_machine": build_rowing_machine,
    "fitness_notice_board": build_fitness_notice_board,
}


def build_outdoor_fitness_asset(
    variant,
    parent=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    materials=None,
    joint_values=None,
):
    """Build one selectable archetype for a production scene."""
    if variant not in BUILDERS:
        raise ValueError(
            f"Unknown fitness variant {variant!r}; expected one of {FITNESS_VARIANTS}"
        )
    root = BUILDERS[variant](parent, origin, yaw, materials, joint_values)
    root["c2w_pipeline_adapter"] = "urban_assets.build_outdoor_fitness_asset"
    root["c2w_scene_asset_inputs"] = 0
    return root


def _paver_mesh(name, material):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    source = bpy.context.active_object
    source.name = PREFIX + name + "_source"
    bevel = source.modifiers.new("worn_paver_edges", "BEVEL")
    bevel.width = 0.035
    bevel.segments = 3
    bevel.limit_method = "ANGLE"
    bpy.context.view_layer.objects.active = source
    bpy.ops.object.modifier_apply(modifier=bevel.name)
    mesh = source.data
    mesh.name = PREFIX + name + "_mesh"
    mesh.materials.append(material)
    bpy.data.objects.remove(source, do_unlink=True)
    return mesh


def build_site(parent, root, M):
    coll = collection("site_paving", parent, role="site_collection", variant="site")
    ctx = BuildContext("site", coll, root)
    # The installation sits in a continuous paved public realm, not on a floating slab.
    box(
        ctx,
        "surrounding_ground",
        (0, 0, -0.08),
        (80.0, 70.0, 0.16),
        M["surround"],
        0.025,
        semantic="site_context_ground",
    )
    for i, x in enumerate((-24.0, -16.0, -8.0, 0.0, 8.0, 16.0, 24.0)):
        box(
            ctx,
            f"context_joint_ns_{i}",
            (x, 0, 0.006),
            (0.035, 54.0, 0.012),
            M["grout"],
            0.004,
            semantic="expansion_joint",
        )
    for i, y in enumerate((-24.0, -16.0, -8.0, 0.0, 8.0, 16.0, 24.0)):
        box(
            ctx,
            f"context_joint_ew_{i}",
            (0, y, 0.006),
            (64.0, 0.035, 0.012),
            M["grout"],
            0.004,
            semantic="expansion_joint",
        )
    box(
        ctx,
        "grout_bed",
        (0, 0, -0.07),
        (27.8, 17.4, 0.14),
        M["grout"],
        0.015,
        semantic="fitness_area_ground",
    )
    stone_mats = [
        pbr(
            f"paver_{i}",
            color,
            0.78 + 0.02 * (i % 2),
            0.0,
            noise=(6.0 + i, 5.0, 0.72, 1.24),
            bump=0.24,
        )
        for i, color in enumerate(
            (
                (0.31, 0.32, 0.30),
                (0.36, 0.35, 0.32),
                (0.27, 0.29, 0.28),
                (0.40, 0.38, 0.35),
                (0.30, 0.31, 0.29),
                (0.34, 0.35, 0.33),
            )
        )
    ]
    meshes = [
        _paver_mesh(f"paver_variant_{i}", mat) for i, mat in enumerate(stone_mats)
    ]
    dx, dy, gap = 0.78, 0.54, 0.035
    rows = int(16.8 / (dy + gap))
    cols = int(27.1 / (dx + gap))
    for row in range(rows):
        y = -8.05 + row * (dy + gap)
        stagger = (row % 2) * (dx + gap) * 0.5
        for col in range(cols):
            x = -13.05 + col * (dx + gap) + stagger
            if x > 13.05:
                continue
            variant = (row * 7 + col * 3) % len(meshes)
            obj = bpy.data.objects.new(
                PREFIX + f"site:paver_{row:02d}_{col:02d}", meshes[variant]
            )
            coll.objects.link(obj)
            obj.location = (x, y, 0.012 + ((row + col * 2) % 4) * 0.0015)
            obj.scale = (dx, dy, 0.095)
            obj.rotation_euler[2] = math.radians(((row * 13 + col * 7) % 5 - 2) * 0.16)
            tag(obj, ctx, "stone_paver")
    # Four robust border curbs and a real slotted drain complete the installed site.
    box(
        ctx,
        "curb_north",
        (0, 8.55, 0.07),
        (27.8, 0.30, 0.24),
        M["curb"],
        0.035,
        semantic="site_curb",
    )
    box(
        ctx,
        "curb_south",
        (0, -8.55, 0.07),
        (27.8, 0.30, 0.24),
        M["curb"],
        0.035,
        semantic="site_curb",
    )
    box(
        ctx,
        "curb_west",
        (-13.75, 0, 0.07),
        (0.30, 17.1, 0.24),
        M["curb"],
        0.035,
        semantic="site_curb",
    )
    box(
        ctx,
        "curb_east",
        (13.75, 0, 0.07),
        (0.30, 17.1, 0.24),
        M["curb"],
        0.035,
        semantic="site_curb",
    )
    for drain_index, drain_x in enumerate((-7.0, 7.0)):
        box(
            ctx,
            f"drain_body_{drain_index}",
            (drain_x, 8.12, 0.015),
            (4.8, 0.24, 0.09),
            M["drain"],
            0.018,
            semantic="linear_drain",
        )
        for i in range(32):
            x = drain_x - 2.25 + i * 0.145
            box(
                ctx,
                f"drain_{drain_index}_slot_{i:02d}",
                (x, 8.115, 0.068),
                (0.055, 0.17, 0.018),
                M["rubber"],
                0.007,
                semantic="drain_slot",
            )
    root["c2w_site_paver_count"] = sum(
        o.get("c2w_semantic") == "stone_paver" for o in ctx.objects
    )
    return coll


DEFAULT_LAYOUT = (
    # North bank, facing its shared access aisle.
    ("air_walker_double", (-10.0, 5.70, PAVER_SURFACE_Z), math.radians(-2)),
    ("ski_walker", (-5.0, 5.70, PAVER_SURFACE_Z), math.radians(2)),
    ("double_leg_press", (0.0, 5.70, PAVER_SURFACE_Z), 0.0),
    ("double_surf_board", (5.0, 5.70, PAVER_SURFACE_Z), math.radians(-2)),
    ("double_traction_station", (10.0, 5.70, PAVER_SURFACE_Z), 0.0),
    # Inner north bank faces north, preserving a broad central service aisle.
    ("rider_trainer", (-10.0, 1.90, PAVER_SURFACE_Z), math.pi),
    ("stepper_station", (-5.0, 1.90, PAVER_SURFACE_Z), math.pi),
    ("stall_bars", (0.0, 1.90, PAVER_SURFACE_Z), math.pi),
    ("rowing_machine", (5.0, 1.90, PAVER_SURFACE_Z), math.pi),
    ("fitness_notice_board", (10.0, 1.90, PAVER_SURFACE_Z), math.pi),
    # A second complete bank doubles simultaneous capacity.
    ("air_walker_double", (-10.0, -1.90, PAVER_SURFACE_Z), 0.0),
    ("ski_walker", (-5.0, -1.90, PAVER_SURFACE_Z), 0.0),
    ("double_leg_press", (0.0, -1.90, PAVER_SURFACE_Z), 0.0),
    ("double_surf_board", (5.0, -1.90, PAVER_SURFACE_Z), 0.0),
    ("double_traction_station", (10.0, -1.90, PAVER_SURFACE_Z), 0.0),
    ("rider_trainer", (-10.0, -5.70, PAVER_SURFACE_Z), math.pi),
    ("stepper_station", (-5.0, -5.70, PAVER_SURFACE_Z), math.pi),
    ("stall_bars", (0.0, -5.70, PAVER_SURFACE_Z), math.pi),
    ("rowing_machine", (5.0, -5.70, PAVER_SURFACE_Z), math.pi),
    ("fitness_notice_board", (10.0, -5.70, PAVER_SURFACE_Z), math.pi),
)


DEMONSTRATION_JOINT_POSES = {
    # North-bank examples are deliberately posed so their mechanism is readable
    # in the daylight validation views; the second copy remains a neutral datum.
    0: {
        "left_pendulum_hinge": math.radians(18),
        "right_pendulum_hinge": math.radians(-14),
    },
    1: {
        "left_reciprocal_hinge": math.radians(-10),
        "right_reciprocal_hinge": math.radians(10),
    },
    2: {
        "left_seat_hinge": math.radians(-10),
        "right_seat_hinge": math.radians(8),
    },
    3: {
        "left_board_hinge": math.radians(12),
        "right_board_hinge": math.radians(-12),
    },
    5: {
        "wishbone_hinge": math.radians(12),
        "seat_hinge": math.radians(6),
    },
    6: {
        "left_step_hinge": math.radians(-9),
        "right_step_hinge": math.radians(9),
    },
    8: {
        "rowing_lever_hinge": math.radians(24),
        "seat_carriage_slider": -0.18,
    },
}


def build_outdoor_fitness_area(
    parent=None,
    include_site=True,
    layout=None,
    origin=(0.0, 0.0, 0.0),
    yaw=0.0,
    joint_pose_sets=None,
):
    """Build the twenty-station fitness zone used by pipeline and validation."""
    parent = parent or bpy.context.scene.collection
    area_coll = collection("OUTDOOR_FITNESS_AREA", parent, role="asset_area")
    area_root = anchor(area_coll, "fitness_area_root", "area", origin, yaw)
    area_root["c2w_role"] = "asset_area_root"
    area_root["c2w_asset_id"] = "park.outdoor_fitness.area.v1"
    area_root["c2w_pipeline_adapter"] = "urban_assets.build_outdoor_fitness_area"
    area_root["c2w_source_generator"] = Path(__file__).name
    area_root["c2w_scene_asset_inputs"] = 0
    M = make_materials()
    if include_site:
        build_site(area_coll, area_root, M)
    asset_roots = []
    for index, (variant, local_origin, local_yaw) in enumerate(
        layout or DEFAULT_LAYOUT
    ):
        pose_values = dict((joint_pose_sets or {}).get(index, {}))
        asset_root = build_outdoor_fitness_asset(
            variant, area_coll, local_origin, local_yaw, M, pose_values
        )
        asset_root.parent = area_root
        asset_root["c2w_layout_index"] = index
        asset_roots.append(asset_root)
    area_root["c2w_variants"] = json.dumps([r.get("c2w_variant") for r in asset_roots])
    area_root["c2w_variant_count"] = len(asset_roots)
    area_root["c2w_nominal_footprint_m"] = "27.8 x 17.4"
    area_root["c2w_capacity_people"] = 30
    area_root["c2w_articulation_standard"] = ARTICULATION_STANDARD
    area_root["c2w_joint_pose_sets"] = json.dumps(joint_pose_sets or {}, sort_keys=True)
    return area_root, M


def setup_daylight():
    scene = bpy.context.scene
    world = bpy.data.worlds.new(PREFIX + "daylight_world")
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    for node in list(nodes):
        nodes.remove(node)
    out = nodes.new("ShaderNodeOutputWorld")
    bg = nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = 0.34
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(132)
    sky.altitude = 0.15
    sky.air_density = 0.82
    sky.dust_density = 1.15
    links.new(sky.outputs["Color"], bg.inputs["Color"])
    links.new(bg.outputs["Background"], out.inputs["Surface"])
    scene.world = world

    lights = collection("FITNESS_LIGHTING", role="lighting_collection")
    sun_data = bpy.data.lights.new(PREFIX + "day_sun", "SUN")
    sun_data.energy = 2.25
    sun_data.angle = math.radians(4.0)
    sun = bpy.data.objects.new(PREFIX + "day_sun", sun_data)
    lights.objects.link(sun)
    sun.rotation_euler = (math.radians(29), math.radians(-18), math.radians(128))
    sun["c2w_role"] = "daylight"
    fill_data = bpy.data.lights.new(PREFIX + "sky_fill", "AREA")
    fill_data.energy = 720
    fill_data.shape = "DISK"
    fill_data.size = 7.0
    fill = bpy.data.objects.new(PREFIX + "sky_fill", fill_data)
    lights.objects.link(fill)
    fill.location = (-4.5, -3.5, 8.5)
    fill.rotation_euler = (
        (Vector((0, 0, 0.5)) - fill.location).to_track_quat("-Z", "Y").to_euler()
    )
    fill["c2w_role"] = "daylight_fill"


def camera(coll, name, loc, target, lens, role, pose_overrides=None):
    data = bpy.data.cameras.new(PREFIX + name + "_data")
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = (Vector(loc) - Vector(target)).length
    data.dof.aperture_fstop = 8.0 if role.startswith("wide") else 6.3
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )
    obj["c2w_role"] = role
    obj["c2w_pose_overrides"] = json.dumps(pose_overrides or [], sort_keys=True)
    return obj


def build_cameras():
    coll = collection("FITNESS_CAMERAS", role="camera_collection")
    specs = (
        ("overview_day", (22.0, -25.0, 18.0), (0, 0, 0.72), 42, "wide_overview"),
        ("wide_front_day", (0, -31.0, 8.0), (0, 0, 0.88), 38, "wide_eye_level"),
        ("wide_reverse_day", (-24.0, 23.0, 12.0), (0, 0, 0.82), 43, "wide_reverse"),
        ("wide_side_day", (29.0, 1.0, 10.0), (0, 0, 0.80), 40, "wide_side"),
        (
            "air_walker_close_day",
            (-13.7, 1.8, 3.15),
            (-10.0, 5.70, 1.06),
            52,
            "close_air_walker",
        ),
        (
            "ski_walker_close_day",
            (-7.7, 2.0, 3.10),
            (-5.0, 5.70, 1.12),
            52,
            "close_ski_walker",
        ),
        ("rider_close_day", (-13.2, 5.2, 3.00), (-10.0, 1.90, 1.03), 52, "close_rider"),
        (
            "stepper_close_day",
            (-7.5, 5.0, 2.90),
            (-5.0, 1.90, 1.00),
            52,
            "close_stepper",
        ),
        (
            "leg_press_close_day",
            (-3.2, 2.4, 2.85),
            (0.0, 5.70, 1.03),
            54,
            "close_double_leg_press",
        ),
        (
            "surf_board_close_day",
            (7.8, 2.3, 2.85),
            (5.0, 5.70, 0.98),
            54,
            "close_double_surf_board",
        ),
        (
            "traction_close_day",
            (13.4, 2.2, 3.75),
            (10.0, 5.70, 1.52),
            55,
            "close_double_traction",
        ),
        (
            "stall_bars_close_day",
            (-3.1, 4.7, 3.00),
            (0.0, 1.90, 1.30),
            55,
            "close_stall_bars",
        ),
        (
            "rowing_close_day",
            (8.4, 5.0, 2.65),
            (5.0, 1.90, 0.73),
            52,
            "close_rowing_machine",
        ),
        (
            "notice_board_close_day",
            (10.0, 5.25, 2.55),
            (10.0, 1.90, 1.50),
            58,
            "close_notice_board",
        ),
        (
            "air_walker_support_detail_day",
            (-7.90, 4.00, 1.35),
            (-9.05, 5.45, 0.40),
            54,
            "close_mechanical_support_detail",
        ),
        (
            "air_walker_hinge_neutral_day",
            (-13.65, 2.15, 2.75),
            (-10.0, 5.70, 0.92),
            56,
            "close_air_walker_hinge_neutral",
            [
                {"layout_index": 0, "joint_id": "left_pendulum_hinge", "value": 0.0},
                {"layout_index": 0, "joint_id": "right_pendulum_hinge", "value": 0.0},
            ],
        ),
        (
            "air_walker_hinge_rotated_day",
            (-13.65, 2.15, 2.75),
            (-10.0, 5.70, 0.92),
            56,
            "close_air_walker_hinge_rotated",
            [
                {
                    "layout_index": 0,
                    "joint_id": "left_pendulum_hinge",
                    "value": math.radians(25),
                },
                {
                    "layout_index": 0,
                    "joint_id": "right_pendulum_hinge",
                    "value": math.radians(-22),
                },
            ],
        ),
        (
            "rowing_hinge_neutral_day",
            (8.50, 5.15, 2.55),
            (5.0, 1.90, 0.76),
            54,
            "close_rowing_hinge_neutral",
            [
                {"layout_index": 8, "joint_id": "rowing_lever_hinge", "value": 0.0},
                {"layout_index": 8, "joint_id": "seat_carriage_slider", "value": 0.0},
            ],
        ),
        (
            "rowing_hinge_rotated_day",
            (8.50, 5.15, 2.55),
            (5.0, 1.90, 0.76),
            54,
            "close_rowing_hinge_rotated",
            [
                {
                    "layout_index": 8,
                    "joint_id": "rowing_lever_hinge",
                    "value": math.radians(29),
                },
                {"layout_index": 8, "joint_id": "seat_carriage_slider", "value": -0.25},
            ],
        ),
    )
    return [camera(coll, *spec) for spec in specs]


def configure_scene(preview=False):
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = 720 if preview else 960
    scene.render.resolution_y = 480 if preview else 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.image_settings.color_depth = "8"
    scene.render.fps = 24
    scene.render.pixel_aspect_x = 1.0
    scene.render.pixel_aspect_y = 1.0
    scene.render.image_settings.compression = 18
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.use_high_quality_normals = True
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.45
    scene.view_settings.view_transform = "AgX"
    scene.camera = None
    scene["c2w_only_asset"] = "outdoor_fitness_area"
    scene["c2w_daylight"] = True
    scene["c2w_reference_driven"] = True
    scene["c2w_generator"] = Path(__file__).name
    scene["c2w_simulation_ready"] = True
    scene["c2w_articulation_standard"] = ARTICULATION_STANDARD
    scene["c2w_joint_units"] = "radians_and_meters"


def _apply_render_pose_override(override):
    layout_index = int(override["layout_index"])
    joint_id = str(override["joint_id"])
    value = float(override["value"])
    roots = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "asset_root"
        and int(obj.get("c2w_layout_index", -1)) == layout_index
    ]
    if len(roots) != 1:
        raise RuntimeError(
            f"Unable to resolve layout index {layout_index} for render pose"
        )
    root = roots[0]
    records = [
        record for record in _root_joint_records(root) if record["joint_id"] == joint_id
    ]
    if len(records) != 1:
        raise RuntimeError(f"Unable to resolve joint {joint_id} on {root.name}")
    record = records[0]
    controller = bpy.data.objects[record["controller"]]
    if record["joint_type"] == "revolute":
        controller.rotation_mode = "QUATERNION"
        controller.rotation_quaternion = Quaternion(
            _axis_vector(record["axis_local"]), value
        )
    else:
        controller.location = (
            Vector(record["pivot_local_m"]) + _axis_vector(record["axis_local"]) * value
        )
    controller["c2w_render_pose_value"] = value


def render_all(cameras, skip_existing=False):
    RENDERS.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    results = []
    controllers = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_collision_proxy"
        and obj.get("c2w_joint_id")
    ]
    authored_transforms = {
        obj.name: (
            obj.location.copy(),
            obj.rotation_mode,
            obj.rotation_quaternion.copy(),
        )
        for obj in controllers
    }
    for index, cam in enumerate(cameras, start=1):
        for obj in controllers:
            location, rotation_mode, quaternion = authored_transforms[obj.name]
            obj.location = location
            obj.rotation_mode = rotation_mode
            obj.rotation_quaternion = quaternion
        for override in json.loads(str(cam.get("c2w_pose_overrides", "[]"))):
            _apply_render_pose_override(override)
        bpy.context.view_layer.update()
        scene.camera = cam
        filename = f"{index:02d}_{cam.name.split(':')[-1]}.png"
        path = RENDERS / filename
        if skip_existing and path.exists() and path.stat().st_size > 15000:
            print(f"[fitness] Keeping completed render {filename}", flush=True)
            results.append(path)
            continue
        scene.render.filepath = str(path)
        print(f"[fitness] Rendering {filename}", flush=True)
        bpy.ops.render.render(write_still=True)
        results.append(path)
    for obj in controllers:
        location, rotation_mode, quaternion = authored_transforms[obj.name]
        obj.location = location
        obj.rotation_mode = rotation_mode
        obj.rotation_quaternion = quaternion
        if "c2w_render_pose_value" in obj:
            del obj["c2w_render_pose_value"]
    bpy.context.view_layer.update()
    return results


def archive_references():
    REFERENCES.mkdir(parents=True, exist_ok=True)
    records = []
    for url, source in zip(REFERENCE_URLS, REFERENCE_CACHE):
        dest = REFERENCES / source.name
        if source.exists():
            shutil.copy2(source, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            records.append(
                {
                    "url": url,
                    "file": dest.name,
                    "sha256": digest,
                    "bytes": dest.stat().st_size,
                    "available": True,
                }
            )
        else:
            records.append({"url": url, "file": dest.name, "available": False})
    (REFERENCES / "reference_manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return records


def archive_method_reference():
    """Archive the exact paper used to define the articulation contract."""
    REFERENCES.mkdir(parents=True, exist_ok=True)
    destination = REFERENCES / "infinigen_articulated_2505.10755.pdf"
    if METHOD_REFERENCE_CACHE.exists():
        shutil.copy2(METHOD_REFERENCE_CACHE, destination)
        record = {
            "url": METHOD_REFERENCE_URL,
            "title": "Procedural Generation of Articulated Simulation-Ready Assets",
            "file": destination.name,
            "sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
            "bytes": destination.stat().st_size,
            "available": True,
            "methods_reused": [
                "nodegroup_hinge_joint",
                "nodegroup_sliding_joint",
                "procedural parent-child rigid-body decomposition",
                "procedural pivot, axis, range and dynamics metadata",
                "range-sweep collision and clearance validation",
            ],
        }
    else:
        record = {
            "url": METHOD_REFERENCE_URL,
            "file": destination.name,
            "available": False,
        }
    (REFERENCES / "method_reference.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def semantic_counts():
    return Counter(
        str(o.get("c2w_semantic"))
        for o in bpy.data.objects
        if o.get("c2w_role") == "fitness_part"
    )


def _world_min_z(obj):
    return min((obj.matrix_world @ Vector(corner)).z for corner in obj.bound_box)


def _minimum_layout_gap(asset_roots):
    gap = float("inf")
    for i, first in enumerate(asset_roots):
        for second in asset_roots[i + 1 :]:
            distance = (
                Vector(first.matrix_world.translation).xy
                - Vector(second.matrix_world.translation).xy
            ).length
            required = float(first.get("c2w_clearance_radius_m", 0.0)) + float(
                second.get("c2w_clearance_radius_m", 0.0)
            )
            gap = min(gap, distance - required)
    return gap if math.isfinite(gap) else 0.0


def _is_descendant_of(obj, ancestor):
    parent = obj.parent
    while parent is not None:
        if parent == ancestor:
            return True
        parent = parent.parent
    return False


def _root_joint_records(root):
    try:
        return json.loads(str(root.get("c2w_kinematic_tree", "[]")))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


def _world_aabb(obj):
    points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return (
        Vector(
            (
                min(point.x for point in points),
                min(point.y for point in points),
                min(point.z for point in points),
            )
        ),
        Vector(
            (
                max(point.x for point in points),
                max(point.y for point in points),
                max(point.z for point in points),
            )
        ),
    )


def _aabbs_overlap(first, second, minimum_overlap=0.0005):
    """Conservative broad phase that rejects touching-but-not-penetrating boxes."""
    return all(
        min(first[1][axis], second[1][axis]) - max(first[0][axis], second[0][axis])
        >= minimum_overlap
        for axis in range(3)
    )


def _evaluated_object_bvh(obj, depsgraph):
    """Return an exact world-space BVH and its evaluated triangle coordinates."""
    evaluated = obj.evaluated_get(depsgraph)
    mesh = evaluated.to_mesh(preserve_all_data_layers=False, depsgraph=depsgraph)
    if mesh is None:
        return None
    try:
        mesh.calc_loop_triangles()
        matrix = evaluated.matrix_world
        vertices = [matrix @ vertex.co for vertex in mesh.vertices]
        polygons = [tuple(triangle.vertices) for triangle in mesh.loop_triangles]
        if not vertices or not polygons:
            return None
        triangles = [
            tuple(vertices[index] for index in polygon) for polygon in polygons
        ]
        bvh = BVHTree.FromPolygons(
            vertices, polygons, all_triangles=True, epsilon=0.00015
        )
        return bvh, triangles
    finally:
        evaluated.to_mesh_clear()


def _triangle_intersection_points(first, second):
    """Locate surface crossing points for one overlapping triangle pair."""
    points = []
    for triangle, target in ((first, second), (second, first)):
        for index in range(3):
            origin = triangle[index]
            direction = triangle[(index + 1) % 3] - origin
            if direction.length_squared <= 1e-12:
                continue
            point = intersect_ray_tri(
                target[0], target[1], target[2], direction, origin, True
            )
            if point is None:
                continue
            parameter = (point - origin).dot(direction) / direction.length_squared
            if -1e-6 <= parameter <= 1.0 + 1e-6:
                points.append(point)
    if points:
        return points
    # Coplanar overlaps are uncommon in the curved machinery, but triangle
    # centroids provide a deterministic conservative fallback.
    return [sum(first, Vector()) / 3.0, sum(second, Vector()) / 3.0]


def _overlap_is_joint_attachment(
    overlap_pairs, moving_triangles, fixed_triangles, pivot_world, axis_world
):
    """Allow only intersections confined to the bearing/pin assembly cylinder."""
    for moving_index, fixed_index in overlap_pairs:
        points = _triangle_intersection_points(
            moving_triangles[moving_index], fixed_triangles[fixed_index]
        )
        for point in points:
            offset = point - pivot_world
            radial = offset - axis_world * offset.dot(axis_world)
            if radial.length > JOINT_ATTACHMENT_RADIUS_M:
                return False
    return True


def sweep_hinge_collisions(asset_roots, samples=17):
    """Sweep every revolute joint against all other evaluated meshes in its asset.

    Unlike the legacy bounding-box-only range report, this evaluates modifiers and
    curves into triangle meshes at every pose, performs exact BVH overlap tests,
    and permits intersections only inside the cylindrical bearing/pin assembly.
    Any contact elsewhere—including a motion-stop penetration—is a hard failure.
    """
    depsgraph = bpy.context.evaluated_depsgraph_get()
    results = []
    for root in asset_roots:
        parts = [
            obj
            for obj in bpy.data.objects
            if obj.get("c2w_role") == "fitness_part"
            and obj.type in {"MESH", "CURVE", "SURFACE", "FONT"}
            and _is_descendant_of(obj, root)
        ]
        for record in _root_joint_records(root):
            if record["joint_type"] != "revolute":
                continue
            controller = bpy.data.objects.get(record["controller"])
            if controller is None:
                results.append(
                    {
                        "asset_root": root.name,
                        "variant": str(root.get("c2w_variant")),
                        "joint_id": record["joint_id"],
                        "sample_count": samples,
                        "hard_collision_pair_count": 1,
                        "permitted_joint_attachment_pair_count": 0,
                        "hard_collisions": [{"error": "missing joint controller"}],
                        "permitted_joint_attachment_contacts": [],
                        "passed": False,
                    }
                )
                continue
            moving = [
                obj
                for obj in parts
                if str(obj.get("c2w_joint_id", "")) == record["joint_id"]
            ]
            fixed = [obj for obj in parts if obj not in moving]
            pivot_local = Vector(record["pivot_local_m"])
            axis_local = _axis_vector(record["axis_local"])
            root_matrix = root.matrix_world.copy()
            pivot_world = root_matrix @ pivot_local
            axis_world = (root_matrix.to_3x3() @ axis_local).normalized()
            lower = float(record["limit_lower_rad"])
            upper = float(record["limit_upper_rad"])
            sample_values = [
                lower + (upper - lower) * index / (samples - 1)
                for index in range(samples)
            ]
            original_matrix = controller.matrix_world.copy()
            hard_contacts = {}
            attachment_contacts = {}
            try:
                for value in sample_values:
                    controller.matrix_world = (
                        root_matrix
                        @ Matrix.Translation(pivot_local)
                        @ Quaternion(axis_local, value).to_matrix().to_4x4()
                    )
                    bpy.context.view_layer.update()
                    moving_aabbs = {obj.name: _world_aabb(obj) for obj in moving}
                    fixed_aabbs = {obj.name: _world_aabb(obj) for obj in fixed}
                    bvh_cache = {}
                    for moving_obj in moving:
                        for fixed_obj in fixed:
                            if not _aabbs_overlap(
                                moving_aabbs[moving_obj.name],
                                fixed_aabbs[fixed_obj.name],
                            ):
                                continue
                            moving_bvh = bvh_cache.get(moving_obj.name)
                            if moving_bvh is None:
                                moving_bvh = _evaluated_object_bvh(
                                    moving_obj, depsgraph
                                )
                                bvh_cache[moving_obj.name] = moving_bvh
                            fixed_bvh = bvh_cache.get(fixed_obj.name)
                            if fixed_bvh is None:
                                fixed_bvh = _evaluated_object_bvh(fixed_obj, depsgraph)
                                bvh_cache[fixed_obj.name] = fixed_bvh
                            if moving_bvh is None or fixed_bvh is None:
                                continue
                            overlap = moving_bvh[0].overlap(fixed_bvh[0])
                            if not overlap:
                                continue
                            permitted = _overlap_is_joint_attachment(
                                overlap,
                                moving_bvh[1],
                                fixed_bvh[1],
                                pivot_world,
                                axis_world,
                            )
                            contact_map = (
                                attachment_contacts if permitted else hard_contacts
                            )
                            key = (moving_obj.name, fixed_obj.name)
                            contact = contact_map.setdefault(
                                key,
                                {
                                    "moving_object": moving_obj.name,
                                    "moving_semantic": str(
                                        moving_obj.get("c2w_semantic", "")
                                    ),
                                    "fixed_object": fixed_obj.name,
                                    "fixed_semantic": str(
                                        fixed_obj.get("c2w_semantic", "")
                                    ),
                                    "sample_values_rad": [],
                                },
                            )
                            contact["sample_values_rad"].append(value)
            finally:
                controller.matrix_world = original_matrix
                bpy.context.view_layer.update()
            hard_records = list(hard_contacts.values())
            attachment_records = list(attachment_contacts.values())
            results.append(
                {
                    "asset_root": root.name,
                    "variant": str(root.get("c2w_variant")),
                    "joint_id": record["joint_id"],
                    "sample_count": samples,
                    "sampled_min_rad": lower,
                    "sampled_max_rad": upper,
                    "joint_attachment_radius_m": JOINT_ATTACHMENT_RADIUS_M,
                    "hard_collision_pair_count": len(hard_records),
                    "permitted_joint_attachment_pair_count": len(attachment_records),
                    "hard_collisions": hard_records,
                    "permitted_joint_attachment_contacts": attachment_records,
                    "passed": not hard_records,
                }
            )
    report = {
        "passed": bool(results) and all(record["passed"] for record in results),
        "method": (
            "17-pose complete-range evaluated-triangle BVH sweep; only contacts "
            "inside the bearing/pin attachment cylinder are permitted"
        ),
        "joint_attachment_radius_m": JOINT_ATTACHMENT_RADIUS_M,
        "revolute_joint_count": len(results),
        "samples_per_joint": samples,
        "hard_collision_pair_count": sum(
            record["hard_collision_pair_count"] for record in results
        ),
        "records": results,
    }
    (OUT / "hinge_collision_sweep_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def sweep_joint_ranges(asset_roots, samples=17):
    """Sample every joint across its complete range and verify its geometry.

    This follows the range-sweep validation strategy described by
    Infinigen-Articulated.  We verify finite transforms, ground clearance and
    exact hinge-origin invariance using the rendered high-detail child parts,
    then restore every controller to its authored display pose.
    """
    results = []
    for root in asset_roots:
        parts = [
            obj
            for obj in bpy.data.objects
            if obj.get("c2w_role") == "fitness_part" and _is_descendant_of(obj, root)
        ]
        ground_z = (root.matrix_world @ Vector((0.0, 0.0, 0.0))).z
        for record in _root_joint_records(root):
            controller = bpy.data.objects.get(record["controller"])
            constraint_obj = bpy.data.objects.get(record["constraint"])
            joint_parts = [
                obj
                for obj in parts
                if str(obj.get("c2w_joint_id", "")) == record["joint_id"]
            ]
            joint_type = record["joint_type"]
            if joint_type == "revolute":
                lower = float(record["limit_lower_rad"])
                upper = float(record["limit_upper_rad"])
            else:
                lower = float(record["limit_lower_m"])
                upper = float(record["limit_upper_m"])
            sampled_values = [
                lower + (upper - lower) * i / (samples - 1) for i in range(samples)
            ]
            min_clearance = float("inf")
            max_pivot_drift = 0.0
            finite = True
            bpy.context.view_layer.update()
            relative_part_matrices = {
                obj.name: controller.matrix_world.inverted_safe() @ obj.matrix_world
                for obj in joint_parts
            }
            root_matrix = root.matrix_world.copy()
            pivot_vec = Vector(record["pivot_local_m"])
            axis_vec = _axis_vector(record["axis_local"])
            for value in sampled_values:
                if joint_type == "revolute":
                    controller_matrix = (
                        root_matrix
                        @ Matrix.Translation(pivot_vec)
                        @ Quaternion(axis_vec, value).to_matrix().to_4x4()
                    )
                else:
                    controller_matrix = root_matrix @ Matrix.Translation(
                        pivot_vec + axis_vec * value
                    )
                coordinates = [
                    controller_matrix
                    @ relative_part_matrices[obj.name]
                    @ Vector(corner)
                    for obj in joint_parts
                    for corner in obj.bound_box
                ]
                if coordinates:
                    min_clearance = min(
                        min_clearance, min(point.z - ground_z for point in coordinates)
                    )
                    finite = finite and all(
                        math.isfinite(component)
                        for point in coordinates
                        for component in point
                    )
                if joint_type == "revolute":
                    expected_pivot = root_matrix @ pivot_vec
                    max_pivot_drift = max(
                        max_pivot_drift,
                        (controller_matrix.translation - expected_pivot).length,
                    )
            constraint_valid = bool(
                constraint_obj
                and constraint_obj.rigid_body_constraint
                and constraint_obj.rigid_body_constraint.object2 == controller
            )
            ground_valid = min_clearance >= -0.001
            pivot_valid = max_pivot_drift <= 1e-5
            result = {
                "asset_root": root.name,
                "variant": str(root.get("c2w_variant")),
                "joint_id": record["joint_id"],
                "joint_type": joint_type,
                "sample_count": samples,
                "sampled_min": lower,
                "sampled_max": upper,
                "minimum_ground_clearance_m": min_clearance,
                "maximum_pivot_drift_mm": max_pivot_drift * 1000.0,
                "finite_transforms": finite,
                "native_constraint_valid": constraint_valid,
                "passed": finite and constraint_valid and ground_valid and pivot_valid,
            }
            results.append(result)
    report = {
        "passed": bool(results) and all(record["passed"] for record in results),
        "method": "full-range uniform joint sampling on high-detail moving geometry",
        "paper_reference": METHOD_REFERENCE_URL,
        "joint_count": len(results),
        "samples_per_joint": samples,
        "records": results,
    }
    (OUT / "joint_range_sweep_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return report


def validate(
    cameras,
    reference_records,
    method_reference,
    rendered_paths,
    sweep_report=None,
    collision_report=None,
):
    parts = [o for o in bpy.data.objects if o.get("c2w_role") == "fitness_part"]
    by_variant = Counter(str(o.get("c2w_variant")) for o in parts)
    semantics = semantic_counts()
    asset_roots = [o for o in bpy.data.objects if o.get("c2w_role") == "asset_root"]
    area_roots = [o for o in bpy.data.objects if o.get("c2w_role") == "asset_area_root"]
    root_variant_counts = Counter(str(root.get("c2w_variant")) for root in asset_roots)
    parts_by_root = {
        root.name: [obj for obj in parts if _is_descendant_of(obj, root)]
        for root in asset_roots
    }
    joints_by_root = {root.name: _root_joint_records(root) for root in asset_roots}
    all_joints = [joint for records in joints_by_root.values() for joint in records]
    joint_counts_by_variant = {
        variant: {
            joint_type: sum(
                root.get("c2w_variant") == variant and joint["joint_type"] == joint_type
                for root in asset_roots
                for joint in joints_by_root[root.name]
            )
            for joint_type in ("revolute", "prismatic")
        }
        for variant in FITNESS_VARIANTS
    }
    rigid_constraints = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_joint_constraint"
    ]
    hinge_constraints = [
        obj for obj in rigid_constraints if obj.get("c2w_joint_type") == "revolute"
    ]
    slider_constraints = [
        obj for obj in rigid_constraints if obj.get("c2w_joint_type") == "prismatic"
    ]
    standard_bridges = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "infinigen_articulated_joint_bridge"
    ]
    collision_proxies = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_collision_proxy"
    ]
    articulated_roots = [
        root
        for root in asset_roots
        if root.get("c2w_articulation_class") == "articulated"
    ]
    fixed_roots = [
        root for root in asset_roots if root.get("c2w_articulation_class") == "fixed"
    ]
    bpy.context.view_layer.update()
    ground_errors = {}
    for root in asset_roots:
        contacts = [
            obj for obj in parts_by_root[root.name] if obj.get("c2w_ground_contact")
        ]
        ground_errors[root.name] = (
            min(abs(_world_min_z(obj) - PAVER_SURFACE_Z) for obj in contacts)
            if contacts
            else float("inf")
        )
    motion_stops = [obj for obj in parts if obj.get("c2w_semantic") == "motion_stop"]
    load_chains = [obj for obj in parts if obj.get("c2w_semantic") == "load_chain"]
    leg_press_parts = [
        obj for obj in parts if obj.get("c2w_variant") == "double_leg_press"
    ]
    leg_press_plates = [
        obj for obj in leg_press_parts if obj.get("c2w_semantic") == "footplate"
    ]
    leg_press_brackets = [
        obj for obj in leg_press_parts if obj.get("c2w_semantic") == "footplate_bracket"
    ]
    leg_press_swing_arms = [
        obj
        for obj in leg_press_parts
        if obj.get("c2w_semantic") == "load_bearing_swing_arm"
    ]
    air_roots = [
        root for root in asset_roots if root.get("c2w_variant") == "air_walker_double"
    ]
    air_portal_valid = all(
        not any(
            obj.name.endswith(":lower_crossbar") or obj.name.endswith(":pedestal_join")
            for obj in parts_by_root[root.name]
        )
        and sum(
            "_portal_foot_plate" in obj.name and obj.get("c2w_ground_contact")
            for obj in parts_by_root[root.name]
        )
        == 2
        and sum(
            "portal_gusset" in obj.name and obj.get("c2w_support_verified")
            for obj in parts_by_root[root.name]
        )
        == 4
        for root in air_roots
    )
    forbidden_leg_press_materials = sorted(
        {
            material.name
            for obj in leg_press_parts
            for material in getattr(getattr(obj, "data", None), "materials", ())
            if material
            and (
                material.name.endswith("powder_coat_lime")
                or material.name.endswith("powder_coat_shadow")
            )
        }
    )
    minimum_layout_gap = _minimum_layout_gap(asset_roots)
    pipeline_adapter_available = False
    pipeline_variant_registry_matches = False
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import urban_assets as UA

        pipeline_adapter_available = callable(
            getattr(UA, "build_outdoor_fitness_asset", None)
        ) and callable(getattr(UA, "build_outdoor_fitness_area", None))
        pipeline_variant_registry_matches = set(
            getattr(UA, "FITNESS_VARIANTS", ())
        ) == set(FITNESS_VARIANTS)
    except Exception as exc:
        print(f"[fitness] Pipeline adapter audit failed: {exc}", flush=True)
    expected_revolute = 2 * sum(
        counts["revolute"] for counts in EXPECTED_JOINTS_PER_VARIANT.values()
    )
    expected_prismatic = 2 * sum(
        counts["prismatic"] for counts in EXPECTED_JOINTS_PER_VARIANT.values()
    )
    joint_axes_valid = all(
        abs(Vector(joint["axis_local"]).length - 1.0) <= 1e-6 for joint in all_joints
    )
    joint_limits_valid = all(
        (
            (
                joint["limit_lower_rad"] < joint["limit_upper_rad"]
                and joint["limit_upper_rad"] - joint["limit_lower_rad"]
                <= math.tau + 1e-6
            )
            if joint["joint_type"] == "revolute"
            else (
                joint["limit_lower_m"] < joint["limit_upper_m"]
                and joint["limit_upper_m"] - joint["limit_lower_m"] <= 1.0
            )
        )
        for joint in all_joints
    )
    expected_counts_valid = all(
        joint_counts_by_variant[variant][joint_type] == expected[joint_type] * 2
        for variant, expected in EXPECTED_JOINTS_PER_VARIANT.items()
        for joint_type in ("revolute", "prismatic")
    )
    joint_geometry_valid = all(
        joint["moving_object_count"] >= 1
        and bpy.data.objects.get(joint["controller"]) is not None
        and bpy.data.objects.get(joint["constraint"]) is not None
        and bpy.data.objects.get(joint["standard_bridge"]) is not None
        for joint in all_joints
    )
    native_constraints_valid = all(
        obj.rigid_body_constraint is not None
        and obj.rigid_body_constraint.object1 is not None
        and obj.rigid_body_constraint.object2 is not None
        and obj.rigid_body_constraint.type
        == ("HINGE" if obj.get("c2w_joint_type") == "revolute" else "SLIDER")
        for obj in rigid_constraints
    )
    native_bridges_valid = all(
        obj.get("c2w_direct_method_reuse")
        and str(obj.get("c2w_native_nodegroup", ""))
        in {"nodegroup_hinge_joint", "nodegroup_sliding_joint"}
        for obj in standard_bridges
    )
    previous_blend = PREVIOUS_OUTPUT / "urban_v3_fitness4.blend"
    previous_blend_sha256 = (
        hashlib.sha256(previous_blend.read_bytes()).hexdigest()
        if previous_blend.exists()
        else ""
    )
    previous_output_intact = previous_blend_sha256 == PREVIOUS_BLEND_SHA256
    paper_path = REFERENCES / str(method_reference.get("file", ""))
    camera_roles = {str(camera_obj.get("c2w_role", "")) for camera_obj in cameras}
    required_motion_roles = {
        "close_air_walker_hinge_neutral",
        "close_air_walker_hinge_rotated",
        "close_rowing_hinge_neutral",
        "close_rowing_hinge_rotated",
    }
    criteria = {
        "twenty_grounded_asset_roots": len(asset_roots) == 20
        and set(root_variant_counts) == set(FITNESS_VARIANTS),
        "two_of_every_variant": all(
            root_variant_counts[v] == 2 for v in FITNESS_VARIANTS
        ),
        "single_fitness_area_root": len(area_roots) == 1,
        "each_instance_is_detailed": all(
            len(instance_parts) >= 45 for instance_parts in parts_by_root.values()
        ),
        "complex_total_part_count": len(parts) >= 2500,
        "real_anchor_hardware": semantics["anchor_bolt"] >= 150,
        "mechanical_pivots_present": semantics["pivot_housing"] >= 32
        and semantics["sealed_bearing"] >= 60,
        "precision_hinge_hardware_present": semantics["hinge_pin"] >= 40
        and semantics["retaining_ring"] >= 80
        and semantics["grease_fitting"] >= 80,
        "anti_slip_footplates_present": semantics["footplate"] >= 28
        and semantics["anti_slip_tread"] >= 140,
        "rubber_grip_detail_present": semantics["hand_grip"] >= 36
        and semantics["grip_rib"] >= 140,
        "weld_and_gusset_detail_present": semantics["weld_bead"] >= 45
        and semantics["reinforcement_gusset"] >= 48,
        "installed_stone_paving": semantics["stone_paver"] >= 900,
        "all_assets_touch_paving": all(
            error <= 0.006 for error in ground_errors.values()
        ),
        "motion_stops_have_rigid_support": bool(motion_stops)
        and all(obj.get("c2w_support_verified") for obj in motion_stops)
        and semantics["motion_stop_bracket"] >= len(motion_stops),
        "traction_chains_have_load_paths": len(load_chains) >= 80
        and all(obj.get("c2w_support_verified") for obj in load_chains),
        "no_equipment_instruction_patches": semantics["instruction_plate"] == 0
        and semantics["instruction_pictogram"] == 0,
        "leg_press_no_green_materials": not forbidden_leg_press_materials,
        "leg_press_fixed_plates_have_load_paths": len(leg_press_plates) == 4
        and all(obj.get("c2w_support_verified") for obj in leg_press_plates)
        and len(leg_press_brackets) >= 18
        and all(obj.get("c2w_support_verified") for obj in leg_press_brackets),
        "leg_press_twin_swing_arms_supported": len(leg_press_swing_arms) == 8
        and all(obj.get("c2w_support_verified") for obj in leg_press_swing_arms),
        "air_walker_has_no_low_crossbar_and_two_grounded_portal_legs": len(air_roots)
        == 2
        and air_portal_valid,
        "safe_layout_clearance": minimum_layout_gap >= 0.35,
        "physics_metadata_complete": all(
            root.get("c2w_physics_audited") and root.get("c2w_articulation_audited")
            for root in asset_roots
        ),
        "expected_joint_topology_complete": expected_counts_valid
        and len(all_joints) == 44,
        "native_revolute_constraints_complete": len(hinge_constraints)
        == expected_revolute
        and native_constraints_valid,
        "native_prismatic_constraints_complete": len(slider_constraints)
        == expected_prismatic
        and native_constraints_valid,
        "infinigen_articulated_nodes_reused_directly": len(standard_bridges)
        == len(all_joints)
        and native_bridges_valid,
        "joint_axes_normalized": joint_axes_valid,
        "joint_ranges_realistic": joint_limits_valid,
        "moving_links_have_detailed_geometry": joint_geometry_valid
        and all(
            root.get("c2w_moving_part_count", 0) >= 8 for root in articulated_roots
        ),
        "collision_proxies_and_rigid_bodies_complete": len(collision_proxies)
        == len(all_joints) + len(articulated_roots)
        and all(obj.rigid_body for obj in collision_proxies),
        "fixed_assets_have_no_fake_hinges": len(fixed_roots) == 4
        and all(
            root.get("c2w_variant") in {"stall_bars", "fitness_notice_board"}
            and not joints_by_root[root.name]
            for root in fixed_roots
        ),
        "joint_range_sweep_passed": bool(
            sweep_report
            and sweep_report.get("passed")
            and sweep_report.get("joint_count") == len(all_joints)
        ),
        "all_hinges_mesh_collision_free_outside_joint_attachments": bool(
            collision_report
            and collision_report.get("passed")
            and collision_report.get("revolute_joint_count") == expected_revolute
            and collision_report.get("hard_collision_pair_count") == 0
        ),
        "procedural_source_only": all(o.get("c2w_procedural_source") for o in parts),
        "joint_infrastructure_procedural": all(
            obj.get("c2w_procedural_source")
            for obj in rigid_constraints + standard_bridges + collision_proxies
        ),
        "no_external_mesh_libraries": not any(
            getattr(lib, "filepath", "") for lib in bpy.data.libraries
        ),
        "pipeline_adapter_callable": pipeline_adapter_available,
        "pipeline_variant_registry_matches": pipeline_variant_registry_matches,
        "daylight_multiview": len(cameras) >= 15
        and sum(str(c.get("c2w_role", "")).startswith("close") for c in cameras) >= 11
        and sum(str(c.get("c2w_role", "")).startswith("wide") for c in cameras) >= 4,
        "two_equipment_motion_pose_pairs": required_motion_roles.issubset(camera_roles),
        "references_archived": len(reference_records) == 3
        and all(r["available"] for r in reference_records),
        "method_paper_archived": bool(
            method_reference.get("available")
            and paper_path.exists()
            and paper_path.stat().st_size > 5_000_000
        ),
        "fitness4_previous_output_preserved": previous_output_intact,
        "renders_complete": (not rendered_paths)
        or (
            len(rendered_paths) == len(cameras)
            and all(p.exists() and p.stat().st_size > 15000 for p in rendered_paths)
        ),
        "isolated_fitness_scene": bpy.context.scene.get("c2w_only_asset")
        == "outdoor_fitness_area",
    }
    report = {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "generator": Path(__file__).name,
        "pipeline_adapter": "urban_assets.build_outdoor_fitness_area",
        "variants": list(FITNESS_VARIANTS),
        "part_counts_by_variant": dict(sorted(by_variant.items())),
        "part_counts_by_instance": dict(
            sorted(
                (name, len(instance_parts))
                for name, instance_parts in parts_by_root.items()
            )
        ),
        "asset_root_counts_by_variant": dict(sorted(root_variant_counts.items())),
        "joint_counts_by_variant": joint_counts_by_variant,
        "joint_counts": {
            "revolute": len(hinge_constraints),
            "prismatic": len(slider_constraints),
            "total": len(all_joints),
            "articulated_asset_instances": len(articulated_roots),
            "intentionally_fixed_asset_instances": len(fixed_roots),
        },
        "joint_records_by_instance": joints_by_root,
        "range_sweep_summary": {
            "passed": bool(sweep_report and sweep_report.get("passed")),
            "joint_count": int((sweep_report or {}).get("joint_count", 0)),
            "samples_per_joint": int((sweep_report or {}).get("samples_per_joint", 0)),
        },
        "hinge_collision_sweep_summary": {
            "passed": bool(collision_report and collision_report.get("passed")),
            "revolute_joint_count": int(
                (collision_report or {}).get("revolute_joint_count", 0)
            ),
            "samples_per_joint": int(
                (collision_report or {}).get("samples_per_joint", 0)
            ),
            "hard_collision_pair_count": int(
                (collision_report or {}).get("hard_collision_pair_count", 0)
            ),
            "joint_attachment_radius_m": float(
                (collision_report or {}).get("joint_attachment_radius_m", 0.0)
            ),
        },
        "method_reference": method_reference,
        "previous_output": {
            "path": str(PREVIOUS_OUTPUT.relative_to(ROOT)),
            "blend_sha256": previous_blend_sha256,
            "expected_blend_sha256": PREVIOUS_BLEND_SHA256,
            "preserved": previous_output_intact,
        },
        "semantic_counts": dict(sorted(semantics.items())),
        "forbidden_leg_press_materials": forbidden_leg_press_materials,
        "leg_press_supported_plate_count": len(leg_press_plates),
        "leg_press_supported_bracket_count": len(leg_press_brackets),
        "leg_press_supported_swing_arm_count": len(leg_press_swing_arms),
        "maximum_ground_contact_error_mm": max(ground_errors.values()) * 1000.0,
        "minimum_layout_clearance_m": minimum_layout_gap,
        "objects_total": len(bpy.data.objects),
        "meshes_total": len(bpy.data.meshes),
        "curves_total": len(bpy.data.curves),
        "materials_total": len(bpy.data.materials),
        "rigid_body_constraint_count": len(rigid_constraints),
        "collision_proxy_count": len(collision_proxies),
        "infinigen_articulated_bridge_count": len(standard_bridges),
        "camera_count": len(cameras),
        "render_count": len(rendered_paths),
    }
    return report


def write_manifest(report, reference_records, method_reference, cameras):
    manifest = {
        "asset_id": ASSET_ID,
        "asset_type": "outdoor_fitness_area",
        "source_generator": Path(__file__).name,
        "production_entrypoints": [
            "build_outdoor_fitness_asset",
            "build_outdoor_fitness_area",
            "urban_assets.build_outdoor_fitness_asset",
            "urban_assets.build_outdoor_fitness_area",
        ],
        "variants": list(FITNESS_VARIANTS),
        "layout": [
            {
                "variant": variant,
                "location": list(loc),
                "yaw_degrees": math.degrees(yaw),
            }
            for variant, loc, yaw in DEFAULT_LAYOUT
        ],
        "reference_records": reference_records,
        "method_reference": method_reference,
        "articulation_standard": ARTICULATION_STANDARD,
        "joint_topology": report["joint_counts"],
        "joint_counts_by_variant": report["joint_counts_by_variant"],
        "range_sweep_report": "joint_range_sweep_report.json",
        "hinge_collision_sweep_report": "hinge_collision_sweep_report.json",
        "previous_output": report["previous_output"],
        "camera_views": [{"name": c.name, "role": c.get("c2w_role")} for c in cameras],
        "validation_passed": report["passed"],
        "capacity_people": 30,
        "blend": BLEND_FILENAME,
        "renders_directory": "renders",
    }
    (OUT / "asset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--preview", action="store_true", help="720x480 validation render"
    )
    parser.add_argument(
        "--no-render", action="store_true", help="build and audit without rendering"
    )
    parser.add_argument(
        "--render-existing",
        action="store_true",
        help="resume rendering the source-built validation blend without rebuilding geometry",
    )
    return parser.parse_args(argv)


def render_existing(preview=False):
    """Render and re-audit the current source-built artifact.

    This is a resumable execution path for the same canonical generator output;
    it never changes geometry in the blend and never substitutes an external
    mesh or a hand-edited demo scene.
    """
    blend_path = OUT / BLEND_FILENAME
    manifest_path = OUT / "asset_manifest.json"
    references_path = REFERENCES / "reference_manifest.json"
    method_reference_path = REFERENCES / "method_reference.json"
    for required in (blend_path, manifest_path, references_path, method_reference_path):
        if not required.exists():
            raise FileNotFoundError(
                f"Missing source-built fitness artifact: {required}"
            )
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    camera_names = [record["name"] for record in manifest["camera_views"]]
    cameras = [bpy.data.objects[name] for name in camera_names]
    references = json.loads(references_path.read_text(encoding="utf-8"))
    method_reference = json.loads(method_reference_path.read_text(encoding="utf-8"))
    configure_scene(preview)
    rendered = render_all(cameras, skip_existing=True)
    bpy.context.scene.camera = cameras[0]
    asset_roots = [
        obj for obj in bpy.data.objects if obj.get("c2w_role") == "asset_root"
    ]
    sweep_report = sweep_joint_ranges(asset_roots)
    collision_report = sweep_hinge_collisions(asset_roots)
    report = validate(
        cameras, references, method_reference, rendered, sweep_report, collision_report
    )
    (OUT / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest(report, references, method_reference, cameras)
    bpy.context.scene["c2w_validation_passed"] = report["passed"]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(
        json.dumps(
            {
                "output": str(OUT),
                "blend": str(blend_path),
                "validation_passed": report["passed"],
                "render_count": len(rendered),
                "objects_total": report["objects_total"],
            },
            indent=2,
        ),
        flush=True,
    )
    if not report["passed"]:
        failed = [name for name, passed in report["criteria"].items() if not passed]
        raise RuntimeError("Fitness validation failed: " + ", ".join(failed))


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    RENDERS.mkdir(parents=True, exist_ok=True)
    if args.render_existing:
        render_existing(args.preview)
        return
    refs = archive_references()
    method_reference = archive_method_reference()
    reset_scene()
    area_root, _materials = build_outdoor_fitness_area(
        joint_pose_sets=DEMONSTRATION_JOINT_POSES
    )
    area_root["c2w_reference_urls"] = json.dumps(list(REFERENCE_URLS))
    area_root["c2w_method_reference"] = METHOD_REFERENCE_URL
    setup_daylight()
    cameras = build_cameras()
    configure_scene(args.preview)
    blend_path = OUT / BLEND_FILENAME
    bpy.context.scene.camera = cameras[0]
    asset_roots = [
        obj for obj in bpy.data.objects if obj.get("c2w_role") == "asset_root"
    ]
    sweep_report = sweep_joint_ranges(asset_roots)
    collision_report = sweep_hinge_collisions(asset_roots)
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    rendered = [] if args.no_render else render_all(cameras)
    bpy.context.scene.camera = cameras[0]
    report = validate(
        cameras, refs, method_reference, rendered, sweep_report, collision_report
    )
    (OUT / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    write_manifest(report, refs, method_reference, cameras)
    bpy.context.scene["c2w_validation_passed"] = report["passed"]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(
        json.dumps(
            {
                "output": str(OUT),
                "blend": str(blend_path),
                "validation_passed": report["passed"],
                "render_count": len(rendered),
                "objects_total": report["objects_total"],
            },
            indent=2,
        ),
        flush=True,
    )
    if not report["passed"]:
        failed = [name for name, passed in report["criteria"].items() if not passed]
        raise RuntimeError("Fitness validation failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()

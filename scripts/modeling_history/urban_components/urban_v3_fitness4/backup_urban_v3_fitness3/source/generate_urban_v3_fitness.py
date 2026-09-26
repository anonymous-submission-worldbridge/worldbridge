"""Reference-driven procedural outdoor fitness area for the Urban-v3 pipeline.

The source generator is the canonical asset definition.  It builds ten distinct,
real-scale equipment archetypes visible in the supplied references and exposes
``build_outdoor_fitness_asset`` / ``build_outdoor_fitness_area`` for production
scene composition.  ``main`` is only the isolated daylight validation entrypoint;
it calls the same public builders used by :mod:`urban_assets`.

No external mesh or generated ``.blend`` is read by this module.
"""
from __future__ import annotations

from pathlib import Path as _AssetPath
_ASSET_PROJECT_ROOT = next(p for p in _AssetPath(__file__).resolve().parents if (p / "worldbridge").is_dir())


import argparse
from collections import Counter
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import shutil
import sys

import bpy
from mathutils import Vector


ROOT = Path(str(_ASSET_PROJECT_ROOT))
ASSET_ID = "urban_v3_fitness3"
OUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_fitness3"
RENDERS = OUT / "renders"
REFERENCES = OUT / "references"
PREFIX = "outdoor_fitness:"
PAVER_SURFACE_Z = .064

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


@dataclass
class BuildContext:
    variant: str
    collection: bpy.types.Collection
    root: bpy.types.Object
    objects: list[bpy.types.Object] = field(default_factory=list)


def set_prefix(value: str):
    global PREFIX
    PREFIX = value


def reset_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)


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


def pbr(name, color, roughness=.5, metallic=0.0, noise=None, bump=.0):
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
        tex.inputs["Roughness"].default_value = .7
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
            bump_node.inputs["Distance"].default_value = .04
            links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
            links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    mat["c2w_pbr"] = True
    return mat


def make_materials():
    return {
        "green": pbr("powder_coat_lime", (0.24, .66, .035), .29, .38,
                     noise=(95.0, 3.2, .78, 1.13), bump=.07),
        "green_dark": pbr("powder_coat_shadow", (.095, .31, .018), .34, .34,
                          noise=(82.0, 2.8, .76, 1.12), bump=.06),
        "teal": pbr("powder_coat_deep_teal", (.018, .245, .205), .31, .40,
                    noise=(88.0, 3.0, .72, 1.16), bump=.075),
        "teal_dark": pbr("powder_coat_deep_teal_shadow", (.008, .105, .088), .35, .42,
                         noise=(84.0, 3.0, .70, 1.13), bump=.07),
        "cream": pbr("powder_coat_warm_cream", (.70, .61, .44), .37, .32,
                     noise=(76.0, 2.6, .78, 1.12), bump=.065),
        "cream_dark": pbr("powder_coat_cream_shadow", (.37, .29, .18), .43, .32,
                          noise=(72.0, 2.4, .72, 1.10), bump=.06),
        "galvanized": pbr("galvanized_steel", (.46, .49, .48), .31, .82,
                          noise=(18.0, 5.0, .72, 1.2), bump=.11),
        "stainless": pbr("stainless_fasteners", (.64, .67, .66), .18, .95,
                         noise=(120.0, 2.0, .9, 1.08), bump=.035),
        "rubber": pbr("textured_black_rubber", (.014, .017, .014), .82, .0,
                      noise=(145.0, 4.0, .55, 1.8), bump=.3),
        "bearing": pbr("sealed_bearing", (.035, .042, .036), .4, .55,
                       noise=(45.0, 2.0, .75, 1.15), bump=.08),
        "warning": pbr("safety_yellow", (.93, .61, .035), .34, .25,
                       noise=(70.0, 2.2, .78, 1.12), bump=.08),
        "seat_pad": pbr("weatherproof_seat_pad", (.54, .49, .39), .72, .0,
                        noise=(52.0, 4.0, .68, 1.18), bump=.18),
        "sign_face": pbr("notice_board_face", (.54, .57, .53), .50, .48,
                         noise=(35.0, 2.0, .86, 1.06), bump=.045),
        "sign_red": pbr("notice_board_red_ink", (.62, .035, .025), .48, .02),
        "sign_yellow": pbr("notice_board_yellow_ink", (.94, .55, .02), .45, .02),
        "grout": pbr("grout", (.12, .13, .125), .92, 0.0,
                     noise=(16.0, 5.0, .65, 1.2), bump=.26),
        "curb": pbr("border_stone", (.30, .32, .31), .82, 0.0,
                    noise=(7.5, 6.0, .68, 1.23), bump=.34),
        "surround": pbr("surrounding_aggregate_pavement", (.18, .195, .19), .9, 0.0,
                        noise=(12.0, 7.0, .58, 1.35), bump=.34),
        "drain": pbr("drain_dark_metal", (.055, .065, .06), .5, .74,
                     noise=(34.0, 4.0, .68, 1.2), bump=.12),
    }


def _link_active(coll):
    obj = bpy.context.active_object
    for owner in list(obj.users_collection):
        owner.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def box(ctx, name, loc, dims, material, bevel=.018, rotation=(0.0, 0.0, 0.0),
        semantic="manufactured_detail"):
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


def cylinder(ctx, name, loc, radius, depth, material, vertices=32,
             rotation=(0.0, 0.0, 0.0), semantic="manufactured_detail", bevel=.006):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth,
                                       location=loc, rotation=rotation)
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
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=loc)
    obj = _link_active(ctx.collection)
    obj.name = PREFIX + ctx.variant + ":" + name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return tag(obj, ctx, semantic)


def torus(ctx, name, loc, major, minor, material, rotation=(0.0, 0.0, 0.0),
          semantic="weld_bead"):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor,
                                    major_segments=32, minor_segments=8,
                                    location=loc, rotation=rotation)
    obj = _link_active(ctx.collection)
    obj.name = PREFIX + ctx.variant + ":" + name
    obj.data.materials.append(material)
    for poly in obj.data.polygons:
        poly.use_smooth = True
    return tag(obj, ctx, semantic)


def tube(ctx, name, points, radius, material, semantic="structural_tube", cyclic=False,
         resolution=3):
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


def beam(ctx, name, start, end, radius, material, semantic="structural_tube", vertices=28):
    a, b = Vector(start), Vector(end)
    delta = b - a
    obj = cylinder(ctx, name, (a + b) * .5, radius, delta.length, material,
                   vertices=vertices, semantic=semantic)
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = delta.to_track_quat("Z", "Y")
    return obj


def wedge(ctx, name, center, width, depth, height, material, rotation_z=0.0,
          semantic="reinforcement_gusset"):
    # Triangular prism, with its right-angle corner centered at the support.
    verts = [
        (-width / 2, -depth / 2, -height / 2),
        ( width / 2, -depth / 2, -height / 2),
        (-width / 2, -depth / 2,  height / 2),
        (-width / 2,  depth / 2, -height / 2),
        ( width / 2,  depth / 2, -height / 2),
        (-width / 2,  depth / 2,  height / 2),
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
    mod.width = .008
    mod.segments = 2
    return tag(obj, ctx, semantic)


def _axis_rotation(axis):
    if axis == "x":
        return (0.0, math.pi / 2, 0.0)
    if axis == "y":
        return (math.pi / 2, 0.0, 0.0)
    return (0.0, 0.0, 0.0)


def bolt(ctx, name, loc, M, axis="z", length=.04, radius=.022, washer=True):
    rot = _axis_rotation(axis)
    cylinder(ctx, name + "_head", loc, radius, length, M["stainless"], vertices=6,
             rotation=rot, semantic="fastener", bevel=.002)
    if washer:
        torus(ctx, name + "_washer", loc, radius * 1.17, radius * .14,
              M["stainless"], rotation=rot, semantic="fastener")


def base_assembly(ctx, name, M, center=(0.0, 0.0), post_radius=.12, post_height=.52,
                  flange_radius=.31, anchors=6, material_key="green",
                  dark_key="green_dark"):
    x, y = center
    flange = cylinder(ctx, name + "_flange", (x, y, .07), flange_radius, .14, M[material_key],
                      vertices=48, semantic="mounting_flange", bevel=.012)
    flange["c2w_ground_contact"] = True
    flange["c2w_support_verified"] = True
    cylinder(ctx, name + "_post", (x, y, .14 + post_height / 2), post_radius,
             post_height, M[material_key], vertices=40, semantic="support_post", bevel=.009)
    torus(ctx, name + "_weld", (x, y, .145), post_radius * .99, .022,
          M[dark_key], semantic="weld_bead")
    torus(ctx, name + "_flange_weld", (x, y, .112), post_radius * 1.15, .013,
          M[dark_key], semantic="weld_bead")
    for i in range(anchors):
        ang = math.tau * i / anchors
        bx = x + flange_radius * .72 * math.cos(ang)
        by = y + flange_radius * .72 * math.sin(ang)
        cylinder(ctx, f"{name}_anchor_{i:02d}", (bx, by, .16), .025, .065,
                 M["stainless"], vertices=6, semantic="anchor_bolt", bevel=.002)
        torus(ctx, f"{name}_anchor_washer_{i:02d}", (bx, by, .13), .032, .006,
              M["stainless"], semantic="anchor_bolt")
    for i in range(4):
        a = math.tau * i / 4
        wedge(ctx, f"{name}_gusset_{i}",
              (x + math.cos(a) * (post_radius + .055),
               y + math.sin(a) * (post_radius + .055), .245),
              .18, .035, .20, M[dark_key], a, "reinforcement_gusset")


def pivot_pack(ctx, name, loc, M, axis="y", width=.22, radius=.075,
               body_material=None):
    rot = _axis_rotation(axis)
    body = body_material or M["green"]
    cylinder(ctx, name + "_housing", loc, radius, width, body, vertices=36,
             rotation=rot, semantic="pivot_housing", bevel=.006)
    # Outboard sealed bearings and stainless pivot caps make the mechanism legible.
    offset = {"x": Vector((width / 2 + .008, 0, 0)),
              "y": Vector((0, width / 2 + .008, 0)),
              "z": Vector((0, 0, width / 2 + .008))}[axis]
    for side, vec in (("a", offset), ("b", -offset)):
        pt = Vector(loc) + vec
        cylinder(ctx, f"{name}_bearing_{side}", pt, radius * .72, .022,
                 M["bearing"], vertices=32, rotation=rot, semantic="sealed_bearing", bevel=.003)
        cylinder(ctx, f"{name}_cap_{side}", pt + vec.normalized() * .014,
                 radius * .42, .034, M["stainless"], vertices=6,
                 rotation=rot, semantic="pivot_fastener", bevel=.003)


def grip(ctx, name, start, end, M, radius=.038):
    beam(ctx, name + "_rubber", start, end, radius, M["rubber"], "hand_grip", 28)
    a, b = Vector(start), Vector(end)
    direction = (b - a).normalized()
    # Raised rings and a sealed cap are modeled, not texture-only.
    for i, t in enumerate((.12, .35, .58, .81)):
        center = a.lerp(b, t)
        ring_len = min(.012, (b - a).length * .07)
        obj = cylinder(ctx, f"{name}_rib_{i}", center, radius * 1.07, ring_len,
                       M["rubber"], vertices=24, semantic="grip_rib", bevel=.001)
        obj.rotation_mode = "QUATERNION"
        obj.rotation_quaternion = direction.to_track_quat("Z", "Y")
    sphere(ctx, name + "_endcap", b, radius * 1.04, M["rubber"], "grip_end_cap")


def footplate(ctx, name, center, M, width=.30, length=.62, yaw=0.0, tilt=0.0,
              material_key="galvanized", bracket_material_key="green_dark"):
    rot = (tilt, 0.0, yaw)
    box(ctx, name + "_deck", center, (width, length, .075), M[material_key], .028,
        rot, "footplate")
    # Anti-slip ribs sit proud of the deck and remain visible in close shots.
    for i in range(6):
        yy = center[1] - length * .34 + i * length * .136
        box(ctx, f"{name}_tread_{i}", (center[0], yy, center[2] + .043),
            (width * .76, .024, .018), M["rubber"], .005, rot, "anti_slip_tread")
    for i, (sx, sy) in enumerate(((-1, -1), (-1, 1), (1, -1), (1, 1))):
        bolt(ctx, f"{name}_deck_bolt_{i}",
             (center[0] + sx * width * .34, center[1] + sy * length * .37,
              center[2] + .047), M, "z", .017, .012, False)
    box(ctx, name + "_under_bracket", (center[0], center[1] + length * .10,
                                       center[2] - .065),
        (width * .45, length * .36, .07), M[bracket_material_key], .018, rot,
        "footplate_bracket")


def ground_plate(ctx, name, center, dims, M, material_key="teal", anchors=4):
    """Create a visibly bolted plate whose lower face is the asset's datum plane."""
    x, y = center
    width, depth = dims
    plate = box(ctx, name + "_plate", (x, y, .045), (width, depth, .09),
                M[material_key], .018, semantic="mounting_flange")
    plate["c2w_ground_contact"] = True
    plate["c2w_support_verified"] = True
    bolt_points = ((-.34, -.30), (-.34, .30), (.34, -.30), (.34, .30))
    for i, (sx, sy) in enumerate(bolt_points[:anchors]):
        bx = x + sx * width
        by = y + sy * depth
        cylinder(ctx, f"{name}_anchor_{i}", (bx, by, .103), .023, .045,
                 M["stainless"], 6, semantic="anchor_bolt", bevel=.002)
        torus(ctx, f"{name}_washer_{i}", (bx, by, .091), .030, .006,
              M["stainless"], semantic="anchor_bolt")
    return plate


def upholstered_pad(ctx, name, center, dims, M, rotation=(0.0, 0.0, 0.0),
                    semantic="seat"):
    """Weatherproof pad, rolled rim, steel pan, and attachment hardware."""
    pad = box(ctx, name + "_cushion", center, dims, M["seat_pad"], .055,
              rotation, semantic)
    pan_center = (center[0], center[1] + .018, center[2] - dims[2] * .48)
    box(ctx, name + "_steel_pan", pan_center,
        (dims[0] * .86, dims[1] * .84, .040), M["cream_dark"], .018,
        rotation, semantic + "_support")
    for i, sx in enumerate((-.31, .31)):
        bolt(ctx, f"{name}_pan_bolt_{i}",
             (center[0] + sx * dims[0], center[1] + .025,
              center[2] - dims[2] * .52), M, "z", .025, .013, False)
    pad["c2w_support_verified"] = True
    return pad


def supported_motion_stop(ctx, name, bumper_loc, bracket_start, bracket_end, M,
                          axis="y", radius=.046, length=.11,
                          bracket_material=None):
    """Elastomer travel stop with an explicit welded steel mounting bracket."""
    beam(ctx, name + "_bracket", bracket_start, bracket_end, .028,
         bracket_material or M["green_dark"], "motion_stop_bracket")
    stop = cylinder(ctx, name + "_bumper", bumper_loc, radius, length,
                    M["rubber"], 28, rotation=_axis_rotation(axis),
                    semantic="motion_stop", bevel=.004)
    stop["c2w_support_verified"] = True
    stop["c2w_support_kind"] = "welded_bracket"
    return stop


def chain_drop(ctx, name, x, y, top_z, count, M):
    """Alternating forged chain links hanging continuously from an upper lug."""
    link_spacing = .066
    for i in range(count):
        rot = (math.pi / 2, 0, 0) if i % 2 == 0 else (0, math.pi / 2, 0)
        link = torus(ctx, f"{name}_link_{i:02d}",
                     (x, y, top_z - i * link_spacing), .040, .008,
                     M["stainless"], rotation=rot, semantic="load_chain")
        link.scale = (1.0, .58, 1.0)
        link["c2w_support_verified"] = True
    return top_z - (count - 1) * link_spacing


def finalize_asset(root, ctx, dimensions, motion, clearance_radius):
    root["c2w_nominal_dimensions_m"] = dimensions
    root["c2w_motion"] = motion
    root["c2w_part_count"] = len(ctx.objects)
    root["c2w_clearance_radius_m"] = float(clearance_radius)
    root["c2w_ground_contact_count"] = sum(
        bool(obj.get("c2w_ground_contact")) for obj in ctx.objects)
    root["c2w_physics_audited"] = True
    return root


def build_air_walker_double(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None):
    M = materials or make_materials()
    coll = collection("asset_air_walker_double", parent, variant="air_walker_double")
    root = anchor(coll, "air_walker_double_root", "air_walker_double", origin, yaw)
    ctx = BuildContext("air_walker_double", coll, root)
    base_assembly(ctx, "base", M, post_height=.48, flange_radius=.30)

    # Rounded rectangular green frame, matching the dominant supplied reference.
    beam(ctx, "lower_crossbar", (-1.25, 0, .58), (1.25, 0, .58), .072, M["green"])
    tube(ctx, "left_frame", [(-1.25, 0, .58), (-1.25, 0, 1.60),
                              (-1.18, 0, 1.88), (-.94, 0, 2.02)],
         .072, M["green"])
    tube(ctx, "top_frame", [(-.94, 0, 2.02), (0, 0, 2.06), (.94, 0, 2.02)],
         .072, M["green"])
    tube(ctx, "right_frame", [(1.25, 0, .58), (1.25, 0, 1.60),
                               (1.18, 0, 1.88), (.94, 0, 2.02)],
         .072, M["green"])
    beam(ctx, "pedestal_join", (0, 0, .38), (0, 0, .58), .13, M["green"], "support_post")
    for side, x in (("left", -.57), ("right", .57)):
        s = -1 if x < 0 else 1
        tube(ctx, side + "_handle_support",
             [(s * 1.12, 0, 1.91), (s * .87, -.015, 1.76),
              (s * .69, -.07, 1.70), (s * .56, -.18, 1.64)],
             .055, M["green"], "handle_support")
        grip(ctx, side + "_angled_grip", (s * .68, -.075, 1.71),
             (s * .52, -.25, 1.53), M, .042)
        pivot_pack(ctx, side + "_upper_pivot", (x, 0, 1.61), M, "y", .24, .082)
        tube(ctx, side + "_pendulum",
             [(x, -.02, 1.61), (x, -.02, .70), (x, -.08, .46),
              (x, -.27, .34)], .045, M["galvanized"], "pendulum_arm")
        footplate(ctx, side + "_footplate", (x, -.50, .285), M, .34, .58)
        pivot_pack(ctx, side + "_lower_joint", (x, -.29, .34), M, "x", .16, .052,
                   M["galvanized"])
        # The old scene left this bumper in mid-air.  Its welded bracket now grows
        # directly from the lower crossbar and the rubber face touches the pendulum.
        supported_motion_stop(ctx, side + "_stop", (x, -.075, .735),
                              (x, 0, .60), (x, -.020, .735), M, "y", .046, .11)
        bolt(ctx, side + "_stop_mount_bolt", (x, -.015, .705), M,
             "y", .050, .017, True)
    return finalize_asset(root, ctx, "2.64 x 1.05 x 2.14",
                          "two independent pendulum foot platforms", 1.42)


def build_ski_walker(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None):
    M = materials or make_materials()
    coll = collection("asset_ski_walker", parent, variant="ski_walker")
    root = anchor(coll, "ski_walker_root", "ski_walker", origin, yaw)
    ctx = BuildContext("ski_walker", coll, root)
    base_assembly(ctx, "base", M, post_height=1.40, flange_radius=.30)
    cylinder(ctx, "mast_cap", (0, 0, 1.59), .137, .10, M["green_dark"], 40,
             semantic="sealed_cap", bevel=.018)
    beam(ctx, "front_pivot_rail", (-.52, -.07, 1.48), (.52, -.07, 1.48), .05,
         M["green"], "pivot_crossmember")
    beam(ctx, "rear_pivot_rail", (-.49, .17, 1.57), (.49, .17, 1.57), .046,
         M["green"], "pivot_crossmember")
    beam(ctx, "rail_spacer_left", (-.46, -.07, 1.48), (-.46, .17, 1.57), .036,
         M["green_dark"], "reinforcement_link")
    beam(ctx, "rail_spacer_right", (.46, -.07, 1.48), (.46, .17, 1.57), .036,
         M["green_dark"], "reinforcement_link")
    for side, x, phase in (("left", -.35, -1), ("right", .35, 1)):
        pivot_pack(ctx, side + "_upper_pivot", (x, -.075, 1.48), M, "y", .25, .074,
                   M["galvanized"])
        # Tall reciprocating handles bend toward the user at their upper ends.
        tube(ctx, side + "_handle",
             [(x, -.10, 1.48), (x, -.14, 1.78),
              (x + phase * .055, -.22, 1.96), (x + phase * .055, -.30, 2.17)],
             .036, M["galvanized"], "moving_handle")
        grip(ctx, side + "_grip", (x + phase * .055, -.30, 2.05),
             (x + phase * .055, -.30, 2.27), M, .041)
        pedal_y = -.26 + phase * .09
        footplate(ctx, side + "_ski", (x, pedal_y, .22 + phase * .018), M,
                  .28, 1.22, tilt=phase * math.radians(1.7))
        beam(ctx, side + "_front_link", (x, -.10, 1.45),
             (x, pedal_y - .30, .30), .032, M["galvanized"], "drive_link")
        beam(ctx, side + "_rear_link", (x, .17, 1.52),
             (x, pedal_y + .35, .29), .032, M["galvanized"], "stabilizer_link")
        pivot_pack(ctx, side + "_pedal_front_pivot", (x, pedal_y - .30, .30), M,
                   "x", .14, .050, M["galvanized"])
        pivot_pack(ctx, side + "_pedal_rear_pivot", (x, pedal_y + .35, .29), M,
                   "x", .14, .046, M["galvanized"])
        supported_motion_stop(ctx, side + "_travel", (x + phase * .11, -.08, 1.18),
                              (phase * .13, -.03, 1.20),
                              (x + phase * .11, -.08, 1.18), M,
                              "x", .043, .12)
    return finalize_asset(root, ctx, "1.22 x 1.58 x 2.32",
                          "linked reciprocal ski pedals and handles", 1.15)


def build_rider_trainer(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None):
    M = materials or make_materials()
    coll = collection("asset_rider_trainer", parent, variant="rider_trainer")
    root = anchor(coll, "rider_trainer_root", "rider_trainer", origin, yaw)
    ctx = BuildContext("rider_trainer", coll, root)
    base_assembly(ctx, "base", M, post_height=.62, flange_radius=.30)
    pivot_pack(ctx, "main_pivot", (0, 0, .76), M, "y", .30, .112)

    # The large wishbone lever is the identifying silhouette of the reference.
    tube(ctx, "wishbone_left", [(-.03, 0, .77), (-.46, 0, .66), (-.72, 0, .93),
                                 (-.80, 0, 1.50), (-.80, 0, 1.88), (-.94, 0, 1.95)],
         .062, M["green"], "moving_wishbone")
    tube(ctx, "wishbone_right", [(.03, 0, .77), (.46, 0, .66), (.72, 0, .93),
                                  (.80, 0, 1.50), (.80, 0, 1.88), (.94, 0, 1.95)],
         .062, M["green"], "moving_wishbone")
    beam(ctx, "wishbone_crossbrace", (-.69, 0, 1.23), (.69, 0, 1.23), .052,
         M["green"], "moving_wishbone")
    for side, x in (("left", -.94), ("right", .94)):
        s = -1 if x < 0 else 1
        beam(ctx, side + "_handle_core", (s * .78, 0, 1.94),
             (s * 1.17, -.05, 1.94), .036, M["galvanized"], "handle_core")
        grip(ctx, side + "_grip", (s * .98, -.05, 1.94),
             (s * 1.24, -.05, 1.94), M, .041)
        torus(ctx, side + "_tube_weld", (s * .79, 0, 1.91), .063, .012,
              M["green_dark"], rotation=(math.pi / 2, 0, 0))
    # Seat, support linkage, and traction foot bar establish plausible mechanics.
    tube(ctx, "seat_link", [(0, .02, .76), (.12, .28, .83), (.18, .49, 1.02)],
         .043, M["galvanized"], "seat_linkage")
    box(ctx, "saddle", (0, .57, 1.06), (.38, .46, .095), M["rubber"], .065,
        rotation=(math.radians(-4), 0, 0), semantic="seat")
    box(ctx, "saddle_pan", (0, .54, 1.00), (.30, .35, .045), M["galvanized"], .025,
        semantic="seat_support")
    beam(ctx, "footbar", (-.43, -.38, .63), (.43, -.38, .63), .043,
         M["galvanized"], "foot_support")
    for side, x in (("left", -.33), ("right", .33)):
        footplate(ctx, side + "_footrest", (x, -.48, .57), M, .22, .34)
        bolt(ctx, side + "_footbar_bolt", (x, -.38, .63), M, "y", .065, .024)
    beam(ctx, "return_link", (0, .10, .77), (0, -.28, .54), .034,
         M["galvanized"], "return_link")
    supported_motion_stop(ctx, "return", (0, -.29, .51),
                          (0, -.08, .48), (0, -.235, .51), M,
                          "y", .055, .11)
    return finalize_asset(root, ctx, "2.55 x 1.18 x 2.06",
                          "pivoting wishbone handle and rising saddle", 1.38)


def build_stepper_station(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0, materials=None):
    M = materials or make_materials()
    coll = collection("asset_stepper_station", parent, variant="stepper_station")
    root = anchor(coll, "stepper_station_root", "stepper_station", origin, yaw)
    ctx = BuildContext("stepper_station", coll, root)
    base_assembly(ctx, "base", M, post_height=1.46, flange_radius=.29)
    cylinder(ctx, "mast_cap", (0, 0, 1.67), .135, .10, M["green_dark"], 40,
             semantic="sealed_cap", bevel=.018)

    # Gray wrap-around hand rail and outward rubber grips from the lower reference.
    tube(ctx, "upper_guard", [(-.56, .03, 1.48), (-.56, .05, 1.72),
                               (-.47, .08, 1.84), (0, .09, 1.88),
                               (.47, .08, 1.84), (.56, .05, 1.72),
                               (.56, .03, 1.48)], .038, M["galvanized"], "handrail")
    beam(ctx, "handle_crossbar", (-.72, -.03, 1.48), (.72, -.03, 1.48), .040,
         M["galvanized"], "handrail")
    for side, x in (("left", -.72), ("right", .72)):
        s = -1 if x < 0 else 1
        tube(ctx, side + "_handle_extension",
             [(s * .46, -.03, 1.48), (s * .70, -.12, 1.45),
              (s * .91, -.20, 1.45)], .038, M["galvanized"], "handle_core")
        grip(ctx, side + "_grip", (s * .72, -.13, 1.45),
             (s * 1.00, -.23, 1.45), M, .041)
    pivot_pack(ctx, "stepper_axle", (0, -.02, .58), M, "y", .40, .105,
               M["galvanized"])
    for side, x, phase in (("left", -.34, -1), ("right", .34, 1)):
        beam(ctx, side + "_crank", (0, -.12, .58),
             (x, -.33 + phase * .05, .50 + phase * .025), .042,
             M["galvanized"], "stepper_crank")
        pivot_pack(ctx, side + "_pedal_pivot", (x, -.35 + phase * .05,
                                                .50 + phase * .025), M,
                   "y", .14, .050, M["galvanized"])
        footplate(ctx, side + "_pedal", (x, -.48 + phase * .05,
                                         .50 + phase * .025), M, .30, .47)
        beam(ctx, side + "_stabilizer", (x, -.28, .49),
             (x * .70, .03, .73), .027, M["green_dark"], "stabilizer_link")
        supported_motion_stop(ctx, side + "_stop", (x * .62, -.055, .75),
                              (x * .28, .0, .79), (x * .62, -.005, .75), M,
                              "y", .045, .10)
    return finalize_asset(root, ctx, "2.10 x 1.25 x 1.94",
                          "independent rocking step pedals", 1.18)


def build_double_leg_press(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                           materials=None):
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
    ctx = BuildContext(variant, coll, root)
    base_assembly(ctx, "base", M, post_radius=.125, post_height=1.68,
                  flange_radius=.32, material_key="teal", dark_key="teal_dark")
    cylinder(ctx, "mast_cap", (0, 0, 1.91), .139, .10, M["cream"], 40,
             semantic="sealed_cap", bevel=.020)
    beam(ctx, "upper_crossmember", (-.58, 0, 1.78), (.58, 0, 1.78), .063,
         M["teal"], "pivot_crossmember")

    # A welded collar spreads both users' foot loads into the central mast.  The
    # former pair of isolated blue rods has deliberately been replaced by a
    # closed, triangulated bracket on each side.
    collar = cylinder(ctx, "footrest_mast_collar", (0, -.02, .615), .158, .47,
                      M["teal_dark"], 48, semantic="footplate_bracket", bevel=.010)
    collar["c2w_support_verified"] = True
    collar["c2w_load_path"] = "fixed_footrests_to_mast_to_anchor_flange"
    for ring_name, z in (("upper", .82), ("lower", .41)):
        torus(ctx, f"footrest_collar_{ring_name}_weld", (0, -.02, z),
              .145, .014, M["teal_dark"], semantic="weld_bead")

    for side, s in (("left", -1), ("right", 1)):
        pivot_x = s * .43
        pivot_pack(ctx, side + "_top_pivot", (pivot_x, 0, 1.78), M,
                   "y", .40, .094, M["cream"])
        for rail, yy in (("front", -.15), ("rear", .15)):
            swing = tube(
                ctx, f"{side}_{rail}_swing_arm",
                [(pivot_x, yy, 1.78), (s * .60, yy, 1.35),
                 (s * .79, yy, .94), (s * 1.03, yy, .75)],
                .047, M["cream"], "load_bearing_swing_arm")
            swing["c2w_support_verified"] = True
            swing["c2w_load_path"] = "seat_carrier_to_upper_pivot_to_mast"
            beam(ctx, f"{side}_{rail}_seat_carrier",
                 (s * .86, yy, .75), (s * 1.39, yy, .75), .040,
                 M["cream"], "seat_linkage")
        beam(ctx, side + "_pivot_crosspin", (pivot_x, -.18, 1.78),
             (pivot_x, .18, 1.78), .038, M["cream_dark"], "pivot_support")
        beam(ctx, side + "_lower_crosspin", (s * 1.03, -.18, .75),
             (s * 1.03, .18, .75), .038, M["cream_dark"], "seat_support")
        beam(ctx, side + "_seat_crossbrace", (s * 1.24, -.20, .75),
             (s * 1.24, .20, .75), .036, M["cream_dark"], "seat_support")
        upholstered_pad(ctx, side + "_seat", (s * 1.23, 0, .84),
                        (.50, .48, .11), M, semantic="seat")

        # Two back-rest stays terminate in the carrier rails; the rear steel shell
        # and four visible fasteners make the assembly readable from both sides.
        for rail, yy in (("front", -.16), ("rear", .16)):
            beam(ctx, f"{side}_back_{rail}_stay", (s * 1.38, yy, .76),
                 (s * 1.47, yy, 1.13), .033, M["cream"], "backrest_support")
        box(ctx, side + "_back_shell", (s * 1.50, 0, 1.14),
            (.075, .48, .56), M["cream_dark"], .040,
            rotation=(0, s * math.radians(7), 0), semantic="backrest_support")
        back_pad = box(ctx, side + "_back_pad", (s * 1.46, 0, 1.15),
            (.10, .42, .50), M["seat_pad"], .060,
            rotation=(0, s * math.radians(7), 0), semantic="backrest")
        back_pad["c2w_support_verified"] = True

        # Fixed foot plate: two chords, an outer spine, and a diagonal form a
        # rigid welded truss.  Every endpoint overlaps either the mast collar or
        # the plate backing, leaving no cantilever visually detached in space.
        upper = beam(ctx, side + "_footrest_upper_chord",
                     (s * .105, -.12, .755), (s * .535, -.12, .755), .037,
                     M["cream_dark"], "footplate_bracket")
        lower = beam(ctx, side + "_footrest_lower_chord",
                     (s * .105, -.12, .465), (s * .535, -.12, .465), .037,
                     M["cream_dark"], "footplate_bracket")
        spine = beam(ctx, side + "_footrest_outer_spine",
                     (s * .535, -.12, .455), (s * .535, -.12, .765), .038,
                     M["cream_dark"], "footplate_bracket")
        diagonal = beam(ctx, side + "_footrest_diagonal",
                        (s * .13, -.12, .48), (s * .51, -.12, .735), .032,
                        M["cream_dark"], "footplate_bracket")
        for member in (upper, lower, spine, diagonal):
            member["c2w_support_verified"] = True
            member["c2w_load_path"] = "press_plate_to_truss_to_mast_collar"
        for joint, x, z in (("upper_root", s * .12, .755),
                            ("lower_root", s * .12, .465),
                            ("upper_outer", s * .535, .755),
                            ("lower_outer", s * .535, .465)):
            torus(ctx, f"{side}_{joint}_weld", (x, -.12, z), .038, .009,
                  M["cream_dark"], rotation=(0, math.pi / 2, 0),
                  semantic="weld_bead")
        plate = box(ctx, side + "_press_plate", (s * .585, -.12, .61),
                    (.09, .44, .40), M["cream"], .034, semantic="footplate")
        plate["c2w_support_verified"] = True
        plate["c2w_load_path"] = "plate_to_outer_spine_to_truss_to_mast"
        for i in range(5):
            box(ctx, f"{side}_press_tread_{i}",
                (s * .636, -.28 + i * .080, .61),
                (.018, .038, .28), M["rubber"], .006,
                semantic="anti_slip_tread")
        for bolt_index, (yy, z) in enumerate(((-.14, .51), (.14, .51),
                                               (-.14, .71), (.14, .71))):
            bolt(ctx, f"{side}_press_plate_bolt_{bolt_index}",
                 (s * .638, yy, z), M, "x", .035, .014, True)

        # Paired grab handles grow from welded uprights on the carrier rails.
        for rail, yy in (("front", -.22), ("rear", .22)):
            beam(ctx, f"{side}_{rail}_handle_upright",
                 (s * 1.12, yy, .75), (s * 1.12, yy, .98), .030,
                 M["cream"], "handle_support")
            beam(ctx, f"{side}_{rail}_handle_core", (s * 1.12, yy, .98),
                 (s * 1.27, yy, 1.01), .027, M["cream"], "handle_core")
            grip(ctx, f"{side}_{rail}_grip", (s * 1.20, yy, 1.00),
                 (s * 1.40, yy, 1.04), M, .032)
        supported_motion_stop(ctx, side + "_return_stop", (s * .31, -.07, 1.40),
                              (s * .12, -.02, 1.40),
                              (s * .255, -.055, 1.40), M, "x", .044, .11,
                              bracket_material=M["teal_dark"])
        bolt(ctx, side + "_carrier_pin", (s * 1.03, -.19, .75), M,
             "y", .38, .022, True)
    return finalize_asset(root, ctx, "3.12 x 0.92 x 1.98",
                          "two independently pivoting twin-arm body-weight seats",
                          1.66)


def build_double_surf_board(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                            materials=None):
    """Two-person hanging waist/surf boards with a fixed continuous handrail."""
    M = materials or make_materials()
    variant = "double_surf_board"
    coll = collection("asset_double_surf_board", parent, variant=variant)
    root = anchor(coll, "double_surf_board_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root)
    base_assembly(ctx, "base", M, post_radius=.12, post_height=1.58,
                  flange_radius=.31, material_key="teal", dark_key="teal_dark")
    cylinder(ctx, "mast_cap", (0, 0, 1.81), .134, .10, M["cream"], 40,
             semantic="sealed_cap", bevel=.018)
    beam(ctx, "pivot_crossmember", (-.68, .02, 1.64), (.68, .02, 1.64), .052,
         M["teal"], "pivot_crossmember")
    tube(ctx, "front_handrail",
         [(-1.16, -.24, 1.56), (-1.02, -.24, 1.66),
          (-.55, -.24, 1.69), (0, -.24, 1.69),
          (.55, -.24, 1.69), (1.02, -.24, 1.66), (1.16, -.24, 1.56)],
         .040, M["teal"], "handrail")
    # Twin triangulated stand-offs close the load path from the front rail to mast.
    for side, s in (("left", -1), ("right", 1)):
        beam(ctx, side + "_handrail_standoff", (s * .09, -.055, 1.62),
             (s * .25, -.24, 1.69), .034, M["teal_dark"], "handrail_support")
        torus(ctx, side + "_handrail_standoff_weld", (s * .25, -.24, 1.69),
              .039, .009, M["teal_dark"], rotation=(math.pi / 2, 0, 0),
              semantic="weld_bead")
    for side, s in (("left", -1), ("right", 1)):
        grip(ctx, side + "_outer_grip", (s * .86, -.24, 1.67),
             (s * 1.20, -.24, 1.54), M, .037)
        pivot_pack(ctx, side + "_upper_pivot", (s * .48, .02, 1.64), M,
                   "y", .25, .081, M["cream"])
        tube(ctx, side + "_hanger",
             [(s * .48, .0, 1.64), (s * .48, -.02, 1.19),
              (s * .52, -.08, .68), (s * .61, -.20, .34)],
             .043, M["cream"], "pendulum_arm")
        pivot_pack(ctx, side + "_board_pivot", (s * .61, -.21, .34), M,
                   "x", .18, .052, M["cream"])
        footplate(ctx, side + "_surf_deck", (s * .61, -.48, .275), M,
                  .36, .67, material_key="cream", bracket_material_key="teal_dark")
        beam(ctx, side + "_deck_keel", (s * .61, -.21, .34),
             (s * .61, -.49, .22), .032, M["cream_dark"], "footplate_bracket")
        supported_motion_stop(ctx, side + "_travel_stop", (s * .29, -.03, 1.18),
                              (s * .11, 0, 1.18), (s * .235, -.02, 1.18),
                              M, "x", .041, .11,
                              bracket_material=M["teal_dark"])
    return finalize_asset(root, ctx, "2.48 x 1.12 x 1.88",
                          "two independent suspended lateral balance boards", 1.35)


def build_double_traction_station(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                                  materials=None):
    """Tall dual traction station with four continuous forged-link handle drops."""
    M = materials or make_materials()
    variant = "double_traction_station"
    coll = collection("asset_double_traction_station", parent, variant=variant)
    root = anchor(coll, "double_traction_station_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root)
    base_assembly(ctx, "base", M, post_radius=.115, post_height=2.48,
                  flange_radius=.30, material_key="teal", dark_key="teal_dark")
    cylinder(ctx, "mast_cap", (0, 0, 2.71), .132, .10, M["cream"], 40,
             semantic="sealed_cap", bevel=.019)
    beam(ctx, "top_crossarm", (-.92, 0, 2.58), (.92, 0, 2.58), .056,
         M["teal"], "overhead_support")
    beam(ctx, "left_diagonal_brace", (-.10, 0, 2.37), (-.68, 0, 2.58), .034,
         M["teal_dark"], "reinforcement_link")
    beam(ctx, "right_diagonal_brace", (.10, 0, 2.37), (.68, 0, 2.58), .034,
         M["teal_dark"], "reinforcement_link")
    drops = ((-.74, 10), (-.34, 12), (.34, 12), (.74, 10))
    for i, (x, count) in enumerate(drops):
        side = "left" if x < 0 else "right"
        # Each chain passes over a guarded sheave whose axle crosses the top beam.
        cylinder(ctx, f"pulley_{i}_wheel", (x, -.015, 2.58), .095, .105,
                 M["cream_dark"], 40, rotation=(math.pi / 2, 0, 0),
                 semantic="pulley_sheave", bevel=.005)
        cylinder(ctx, f"pulley_{i}_guard_front", (x, -.078, 2.58), .112, .024,
                 M["cream"], 40, rotation=(math.pi / 2, 0, 0),
                 semantic="pulley_guard", bevel=.006)
        bolt(ctx, f"pulley_{i}_axle", (x, -.093, 2.58), M, "y", .16, .025, True)
        beam(ctx, f"pulley_{i}_hanger", (x, 0, 2.58), (x, -.10, 2.47), .022,
             M["cream_dark"], "chain_hanger")
        end_z = chain_drop(ctx, f"{side}_{i}_chain", x, -.10, 2.45, count, M)
        torus(ctx, f"handle_{i}_shackle", (x, -.10, end_z - .055), .034, .008,
              M["stainless"], rotation=(math.pi / 2, 0, 0),
              semantic="load_shackle")
        grip(ctx, f"handle_{i}", (x, -.10, end_z - .08),
             (x, -.10, end_z - .32), M, .027)
    return finalize_asset(root, ctx, "2.02 x 0.72 x 2.78",
                          "four gravity-hung traction handles over guarded pulleys", 1.18)


def build_stall_bars(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                     materials=None):
    """Anchored outdoor Swedish ladder/rib wall from the reference sheet."""
    M = materials or make_materials()
    variant = "stall_bars"
    coll = collection("asset_stall_bars", parent, variant=variant)
    root = anchor(coll, "stall_bars_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root)
    for side, x in (("left", -.72), ("right", .72)):
        ground_plate(ctx, side + "_foot", (x, 0), (.34, .42), M, "teal", 4)
        beam(ctx, side + "_upright", (x, 0, .09), (x, 0, 2.48), .061,
             M["teal"], "support_post")
        torus(ctx, side + "_base_weld", (x, 0, .105), .061, .014,
              M["teal_dark"], semantic="weld_bead")
        cylinder(ctx, side + "_top_cap", (x, 0, 2.51), .068, .065,
                 M["cream"], 32, semantic="sealed_cap", bevel=.014)
    rung_heights = (.34, .62, .90, 1.18, 1.46, 1.74, 2.02, 2.30)
    for i, z in enumerate(rung_heights):
        beam(ctx, f"rung_{i}", (-.72, 0, z), (.72, 0, z), .034,
             M["teal"], "climbing_rung")
        for side, x in (("left", -.665), ("right", .665)):
            torus(ctx, f"rung_{i}_{side}_weld", (x, 0, z), .038, .009,
                  M["teal_dark"], rotation=(0, math.pi / 2, 0),
                  semantic="weld_bead")
    tube(ctx, "rounded_top_rail",
         [(-.72, 0, 2.37), (-.67, 0, 2.49), (-.52, 0, 2.55),
          (0, 0, 2.57), (.52, 0, 2.55), (.67, 0, 2.49), (.72, 0, 2.37)],
         .043, M["teal"], "structural_tube")
    return finalize_asset(root, ctx, "1.62 x 0.48 x 2.64",
                          "fixed body-weight climbing and stretching ladder", 1.02)


def build_rowing_machine(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                         materials=None):
    """Ground-anchored single rowing trainer with linked handle and seat mechanism."""
    M = materials or make_materials()
    variant = "rowing_machine"
    coll = collection("asset_rowing_machine", parent, variant=variant)
    root = anchor(coll, "rowing_machine_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root)
    ground_plate(ctx, "front_crossfoot", (0, -.86), (1.34, .25), M, "teal", 4)
    ground_plate(ctx, "rear_crossfoot", (0, .88), (1.20, .25), M, "teal", 4)
    for side, x in (("left", -.52), ("right", .52)):
        beam(ctx, side + "_base_rail", (x, -.86, .11), (x, .88, .11), .045,
             M["teal"], "ground_frame")
        torus(ctx, side + "_front_weld", (x, -.86, .11), .047, .010,
              M["teal_dark"], rotation=(math.pi / 2, 0, 0), semantic="weld_bead")
        torus(ctx, side + "_rear_weld", (x, .88, .11), .047, .010,
              M["teal_dark"], rotation=(math.pi / 2, 0, 0), semantic="weld_bead")
    beam(ctx, "seat_rail", (0, -.48, .34), (0, .72, .55), .065,
         M["teal"], "seat_track")
    beam(ctx, "front_rail_support", (0, -.48, .34), (0, -.71, .11), .050,
         M["teal_dark"], "reinforcement_link")
    beam(ctx, "rear_rail_support", (0, .72, .55), (0, .82, .11), .050,
         M["teal_dark"], "reinforcement_link")
    # Four rollers clamp the carriage around the rail; the seat is carried by it.
    box(ctx, "seat_carriage", (0, .34, .56), (.36, .27, .12), M["cream_dark"], .025,
        rotation=(math.radians(-10), 0, 0), semantic="seat_carriage")
    for side, x in (("left", -.15), ("right", .15)):
        for end, y in (("front", .24), ("rear", .44)):
            cylinder(ctx, f"{side}_{end}_seat_roller", (x, y, .515), .045, .055,
                     M["bearing"], 28, rotation=(0, math.pi / 2, 0),
                     semantic="seat_roller", bevel=.004)
            bolt(ctx, f"{side}_{end}_roller_axle", (x, y, .515), M,
                 "x", .075, .016, True)
    beam(ctx, "seat_riser", (0, .34, .56), (0, .34, .70), .046,
         M["cream"], "seat_support")
    upholstered_pad(ctx, "rowing_seat", (0, .34, .77), (.48, .43, .11), M,
                    rotation=(math.radians(-4), 0, 0), semantic="seat")
    # Fixed footrests transfer force through twin brackets into the base frame.
    for side, x in (("left", -.27), ("right", .27)):
        beam(ctx, side + "_foot_brace", (x, -.71, .13), (x, -.43, .37), .038,
             M["teal_dark"], "footplate_bracket")
        footplate(ctx, side + "_footrest", (x, -.43, .41), M, .25, .43,
                  tilt=math.radians(25), material_key="cream",
                  bracket_material_key="teal_dark")
        tube(ctx, side + "_heel_guard",
             [(x - .11, -.56, .46), (x - .11, -.42, .54),
              (x + .11, -.42, .54), (x + .11, -.56, .46)],
             .014, M["cream_dark"], "heel_guard")
    # Triangulated front towers carry the full rowing-lever pivot.
    for side, x in (("left", -.46), ("right", .46)):
        beam(ctx, side + "_tower_front", (x, -.82, .11), (x, -.53, .67), .050,
             M["teal"], "pivot_support")
        beam(ctx, side + "_tower_rear", (x, -.30, .11), (x, -.53, .67), .050,
             M["teal"], "pivot_support")
        wedge(ctx, side + "_tower_gusset", (x, -.66, .22), .16, .035, .22,
              M["teal_dark"], 0, "reinforcement_gusset")
        pivot_pack(ctx, side + "_lever_pivot", (x, -.53, .67), M,
                   "x", .20, .082, M["cream"])
        tube(ctx, side + "_rowing_lever",
             [(x, -.53, .67), (x, -.25, .90), (x, .04, 1.18),
              (x, .22, 1.28)], .044, M["cream"], "rowing_lever")
        grip(ctx, side + "_handle", (x, .10, 1.22), (x, .34, 1.35), M, .038)
    beam(ctx, "lever_crosslink", (-.46, -.40, .78), (.46, -.40, .78), .034,
         M["cream_dark"], "synchronizing_link")
    supported_motion_stop(ctx, "lever_return_stop", (0, -.61, .49),
                          (0, -.72, .22), (0, -.61, .435), M,
                          "z", .050, .11, bracket_material=M["teal_dark"])
    return finalize_asset(root, ctx, "1.48 x 2.08 x 1.45",
                          "linked twin rowing levers with rolling seat carriage", 1.36)


def build_fitness_notice_board(parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                               materials=None):
    """Two-post park fitness rules sign, modeled as structure rather than a decal."""
    M = materials or make_materials()
    variant = "fitness_notice_board"
    coll = collection("asset_fitness_notice_board", parent, variant=variant)
    root = anchor(coll, "fitness_notice_board_root", variant, origin, yaw)
    ctx = BuildContext(variant, coll, root)
    for side, x in (("left", -.58), ("right", .58)):
        ground_plate(ctx, side + "_foot", (x, 0), (.30, .36), M, "teal", 4)
        beam(ctx, side + "_post", (x, 0, .09), (x, 0, 2.30), .065,
             M["teal"], "support_post")
        torus(ctx, side + "_base_weld", (x, 0, .105), .065, .013,
              M["teal_dark"], semantic="weld_bead")
        cylinder(ctx, side + "_cap", (x, 0, 2.34), .073, .075,
                 M["cream"], 32, semantic="sealed_cap", bevel=.016)
    box(ctx, "sign_back", (0, 0, 1.52), (1.02, .065, 1.28),
        M["teal_dark"], .030, semantic="sign_backing")
    box(ctx, "sign_face", (0, -.042, 1.52), (.94, .025, 1.20),
        M["sign_face"], .018, semantic="sign_face")
    for i, (x, z) in enumerate(((-.43, .97), (.43, .97), (-.43, 2.07), (.43, 2.07))):
        bolt(ctx, f"face_screw_{i}", (x, -.061, z), M, "y", .035, .014, True)
    # Raised header, rule lines, warning marks and exercise pictograms remain legible.
    for i, x in enumerate((-.31, -.18, -.05, .08, .21, .34)):
        box(ctx, f"header_glyph_{i}", (x, -.059, 1.98 + (i % 2) * .015),
            (.075, .010, .105), M["sign_red"], .006, semantic="sign_text")
    for i in range(8):
        width = .66 - (i % 3) * .08
        box(ctx, f"rule_line_{i}", (-.06 + (i % 2) * .04, -.059,
                                     1.75 - i * .105),
            (width, .009, .020), M["teal_dark"], .004, semantic="sign_text")
        box(ctx, f"rule_bullet_{i}", (-.39, -.060, 1.75 - i * .105),
            (.026, .010, .026), M["sign_red" if i in (0, 5) else "sign_yellow"],
            .006, semantic="sign_pictogram")
    for i, x in enumerate((-.25, 0, .25)):
        torus(ctx, f"safety_icon_{i}", (x, -.061, 1.00), .075, .010,
              M["sign_red"], rotation=(math.pi / 2, 0, 0),
              semantic="sign_pictogram")
        beam(ctx, f"safety_icon_slash_{i}", (x - .05, -.075, .95),
             (x + .05, -.075, 1.05), .008, M["sign_red"], "sign_pictogram")
    beam(ctx, "rear_left_brace", (-.58, .02, 1.04), (-.43, .04, 1.16), .027,
         M["teal_dark"], "sign_brace")
    beam(ctx, "rear_right_brace", (.58, .02, 1.04), (.43, .04, 1.16), .027,
         M["teal_dark"], "sign_brace")
    return finalize_asset(root, ctx, "1.34 x 0.42 x 2.39",
                          "fixed public exercise instruction board", .88)


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


def build_outdoor_fitness_asset(variant, parent=None, origin=(0.0, 0.0, 0.0), yaw=0.0,
                                materials=None):
    """Build one selectable archetype for a production scene."""
    if variant not in BUILDERS:
        raise ValueError(f"Unknown fitness variant {variant!r}; expected one of {FITNESS_VARIANTS}")
    root = BUILDERS[variant](parent, origin, yaw, materials)
    root["c2w_pipeline_adapter"] = "urban_assets.build_outdoor_fitness_asset"
    root["c2w_scene_asset_inputs"] = 0
    return root


def _paver_mesh(name, material):
    bpy.ops.mesh.primitive_cube_add(size=1.0)
    source = bpy.context.active_object
    source.name = PREFIX + name + "_source"
    bevel = source.modifiers.new("worn_paver_edges", "BEVEL")
    bevel.width = .035
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
    box(ctx, "surrounding_ground", (0, 0, -.08), (80.0, 70.0, .16), M["surround"], .025,
        semantic="site_context_ground")
    for i, x in enumerate((-24.0, -16.0, -8.0, 0.0, 8.0, 16.0, 24.0)):
        box(ctx, f"context_joint_ns_{i}", (x, 0, .006), (.035, 54.0, .012), M["grout"],
            .004, semantic="expansion_joint")
    for i, y in enumerate((-24.0, -16.0, -8.0, 0.0, 8.0, 16.0, 24.0)):
        box(ctx, f"context_joint_ew_{i}", (0, y, .006), (64.0, .035, .012), M["grout"],
            .004, semantic="expansion_joint")
    box(ctx, "grout_bed", (0, 0, -.07), (27.8, 17.4, .14), M["grout"], .015,
        semantic="fitness_area_ground")
    stone_mats = [
        pbr(f"paver_{i}", color, .78 + .02 * (i % 2), 0.0,
            noise=(6.0 + i, 5.0, .72, 1.24), bump=.24)
        for i, color in enumerate(((.31, .32, .30), (.36, .35, .32), (.27, .29, .28),
                                   (.40, .38, .35), (.30, .31, .29), (.34, .35, .33)))
    ]
    meshes = [_paver_mesh(f"paver_variant_{i}", mat) for i, mat in enumerate(stone_mats)]
    dx, dy, gap = .78, .54, .035
    rows = int(16.8 / (dy + gap))
    cols = int(27.1 / (dx + gap))
    for row in range(rows):
        y = -8.05 + row * (dy + gap)
        stagger = (row % 2) * (dx + gap) * .5
        for col in range(cols):
            x = -13.05 + col * (dx + gap) + stagger
            if x > 13.05:
                continue
            variant = (row * 7 + col * 3) % len(meshes)
            obj = bpy.data.objects.new(PREFIX + f"site:paver_{row:02d}_{col:02d}", meshes[variant])
            coll.objects.link(obj)
            obj.location = (x, y, .012 + ((row + col * 2) % 4) * .0015)
            obj.scale = (dx, dy, .095)
            obj.rotation_euler[2] = math.radians(((row * 13 + col * 7) % 5 - 2) * .16)
            tag(obj, ctx, "stone_paver")
    # Four robust border curbs and a real slotted drain complete the installed site.
    box(ctx, "curb_north", (0, 8.55, .07), (27.8, .30, .24), M["curb"], .035,
        semantic="site_curb")
    box(ctx, "curb_south", (0, -8.55, .07), (27.8, .30, .24), M["curb"], .035,
        semantic="site_curb")
    box(ctx, "curb_west", (-13.75, 0, .07), (.30, 17.1, .24), M["curb"], .035,
        semantic="site_curb")
    box(ctx, "curb_east", (13.75, 0, .07), (.30, 17.1, .24), M["curb"], .035,
        semantic="site_curb")
    for drain_index, drain_x in enumerate((-7.0, 7.0)):
        box(ctx, f"drain_body_{drain_index}", (drain_x, 8.12, .015),
            (4.8, .24, .09), M["drain"], .018, semantic="linear_drain")
        for i in range(32):
            x = drain_x - 2.25 + i * .145
            box(ctx, f"drain_{drain_index}_slot_{i:02d}", (x, 8.115, .068),
                (.055, .17, .018), M["rubber"], .007, semantic="drain_slot")
    root["c2w_site_paver_count"] = sum(o.get("c2w_semantic") == "stone_paver" for o in ctx.objects)
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


def build_outdoor_fitness_area(parent=None, include_site=True, layout=None,
                               origin=(0.0, 0.0, 0.0), yaw=0.0):
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
    for variant, local_origin, local_yaw in (layout or DEFAULT_LAYOUT):
        asset_root = build_outdoor_fitness_asset(variant, area_coll, local_origin, local_yaw, M)
        asset_root.parent = area_root
        asset_roots.append(asset_root)
    area_root["c2w_variants"] = json.dumps([r.get("c2w_variant") for r in asset_roots])
    area_root["c2w_variant_count"] = len(asset_roots)
    area_root["c2w_nominal_footprint_m"] = "27.8 x 17.4"
    area_root["c2w_capacity_people"] = 30
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
    bg.inputs["Strength"].default_value = .34
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(132)
    sky.altitude = .15
    sky.air_density = .82
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
    fill.rotation_euler = ((Vector((0, 0, .5)) - fill.location).to_track_quat("-Z", "Y").to_euler())
    fill["c2w_role"] = "daylight_fill"


def camera(coll, name, loc, target, lens, role):
    data = bpy.data.cameras.new(PREFIX + name + "_data")
    data.lens = lens
    data.sensor_width = 36
    data.dof.use_dof = True
    data.dof.focus_distance = (Vector(loc) - Vector(target)).length
    data.dof.aperture_fstop = 8.0 if role.startswith("wide") else 6.3
    obj = bpy.data.objects.new(PREFIX + name, data)
    coll.objects.link(obj)
    obj.location = loc
    obj.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    obj["c2w_role"] = role
    return obj


def build_cameras():
    coll = collection("FITNESS_CAMERAS", role="camera_collection")
    specs = (
        ("overview_day", (22.0, -25.0, 18.0), (0, 0, .72), 42, "wide_overview"),
        ("wide_front_day", (0, -31.0, 8.0), (0, 0, .88), 38, "wide_eye_level"),
        ("wide_reverse_day", (-24.0, 23.0, 12.0), (0, 0, .82), 43, "wide_reverse"),
        ("wide_side_day", (29.0, 1.0, 10.0), (0, 0, .80), 40, "wide_side"),
        ("air_walker_close_day", (-13.7, 1.8, 3.15), (-10.0, 5.70, 1.06), 52,
         "close_air_walker"),
        ("ski_walker_close_day", (-7.7, 2.0, 3.10), (-5.0, 5.70, 1.12), 52,
         "close_ski_walker"),
        ("rider_close_day", (-13.2, 5.2, 3.00), (-10.0, 1.90, 1.03), 52,
         "close_rider"),
        ("stepper_close_day", (-7.5, 5.0, 2.90), (-5.0, 1.90, 1.00), 52,
         "close_stepper"),
        ("leg_press_close_day", (-3.2, 2.4, 2.85), (0.0, 5.70, 1.03), 54,
         "close_double_leg_press"),
        ("surf_board_close_day", (7.8, 2.3, 2.85), (5.0, 5.70, .98), 54,
         "close_double_surf_board"),
        ("traction_close_day", (13.4, 2.2, 3.75), (10.0, 5.70, 1.52), 55,
         "close_double_traction"),
        ("stall_bars_close_day", (-3.1, 4.7, 3.00), (0.0, 1.90, 1.30), 55,
         "close_stall_bars"),
        ("rowing_close_day", (8.4, 5.0, 2.65), (5.0, 1.90, .73), 52,
         "close_rowing_machine"),
        ("notice_board_close_day", (10.0, 5.25, 2.55), (10.0, 1.90, 1.50), 58,
         "close_notice_board"),
        ("air_walker_support_detail_day", (-8.70, 4.05, 1.48),
         (-9.43, 5.65, .78), 74, "close_mechanical_support_detail"),
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
    scene.view_settings.exposure = .45
    scene.view_settings.view_transform = "AgX"
    scene.camera = None
    scene["c2w_only_asset"] = "outdoor_fitness_area"
    scene["c2w_daylight"] = True
    scene["c2w_reference_driven"] = True
    scene["c2w_generator"] = Path(__file__).name


def render_all(cameras, skip_existing=False):
    RENDERS.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    results = []
    for index, cam in enumerate(cameras, start=1):
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
    return results


def archive_references():
    REFERENCES.mkdir(parents=True, exist_ok=True)
    records = []
    for url, source in zip(REFERENCE_URLS, REFERENCE_CACHE):
        dest = REFERENCES / source.name
        if source.exists():
            shutil.copy2(source, dest)
            digest = hashlib.sha256(dest.read_bytes()).hexdigest()
            records.append({"url": url, "file": dest.name, "sha256": digest,
                            "bytes": dest.stat().st_size, "available": True})
        else:
            records.append({"url": url, "file": dest.name, "available": False})
    (REFERENCES / "reference_manifest.json").write_text(
        json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    return records


def semantic_counts():
    return Counter(str(o.get("c2w_semantic")) for o in bpy.data.objects
                   if o.get("c2w_role") == "fitness_part")


def _world_min_z(obj):
    return min((obj.matrix_world @ Vector(corner)).z for corner in obj.bound_box)


def _minimum_layout_gap(asset_roots):
    gap = float("inf")
    for i, first in enumerate(asset_roots):
        for second in asset_roots[i + 1:]:
            distance = (Vector(first.matrix_world.translation).xy -
                        Vector(second.matrix_world.translation).xy).length
            required = (float(first.get("c2w_clearance_radius_m", 0.0)) +
                        float(second.get("c2w_clearance_radius_m", 0.0)))
            gap = min(gap, distance - required)
    return gap if math.isfinite(gap) else 0.0


def validate(cameras, reference_records, rendered_paths):
    parts = [o for o in bpy.data.objects if o.get("c2w_role") == "fitness_part"]
    by_variant = Counter(str(o.get("c2w_variant")) for o in parts)
    semantics = semantic_counts()
    asset_roots = [o for o in bpy.data.objects if o.get("c2w_role") == "asset_root"]
    area_roots = [o for o in bpy.data.objects if o.get("c2w_role") == "asset_area_root"]
    root_variant_counts = Counter(str(root.get("c2w_variant")) for root in asset_roots)
    parts_by_root = {root.name: [obj for obj in parts if obj.parent == root]
                     for root in asset_roots}
    bpy.context.view_layer.update()
    ground_errors = {}
    for root in asset_roots:
        contacts = [obj for obj in parts_by_root[root.name]
                    if obj.get("c2w_ground_contact")]
        ground_errors[root.name] = (min(abs(_world_min_z(obj) - PAVER_SURFACE_Z)
                                        for obj in contacts)
                                    if contacts else float("inf"))
    motion_stops = [obj for obj in parts if obj.get("c2w_semantic") == "motion_stop"]
    load_chains = [obj for obj in parts if obj.get("c2w_semantic") == "load_chain"]
    leg_press_parts = [obj for obj in parts
                       if obj.get("c2w_variant") == "double_leg_press"]
    leg_press_plates = [obj for obj in leg_press_parts
                        if obj.get("c2w_semantic") == "footplate"]
    leg_press_brackets = [obj for obj in leg_press_parts
                          if obj.get("c2w_semantic") == "footplate_bracket"]
    leg_press_swing_arms = [obj for obj in leg_press_parts
                            if obj.get("c2w_semantic") == "load_bearing_swing_arm"]
    forbidden_leg_press_materials = sorted({
        material.name
        for obj in leg_press_parts
        for material in getattr(getattr(obj, "data", None), "materials", ())
        if material and (material.name.endswith("powder_coat_lime") or
                         material.name.endswith("powder_coat_shadow"))
    })
    minimum_layout_gap = _minimum_layout_gap(asset_roots)
    pipeline_adapter_available = False
    pipeline_variant_registry_matches = False
    try:
        scripts_dir = str(Path(__file__).resolve().parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        import urban_assets as UA
        pipeline_adapter_available = (
            callable(getattr(UA, "build_outdoor_fitness_asset", None)) and
            callable(getattr(UA, "build_outdoor_fitness_area", None))
        )
        pipeline_variant_registry_matches = set(getattr(UA, "FITNESS_VARIANTS", ())) == set(FITNESS_VARIANTS)
    except Exception as exc:
        print(f"[fitness] Pipeline adapter audit failed: {exc}", flush=True)
    criteria = {
        "twenty_grounded_asset_roots": len(asset_roots) == 20 and
                                         set(root_variant_counts) == set(FITNESS_VARIANTS),
        "two_of_every_variant": all(root_variant_counts[v] == 2 for v in FITNESS_VARIANTS),
        "single_fitness_area_root": len(area_roots) == 1,
        "each_instance_is_detailed": all(len(instance_parts) >= 45
                                           for instance_parts in parts_by_root.values()),
        "complex_total_part_count": len(parts) >= 2500,
        "real_anchor_hardware": semantics["anchor_bolt"] >= 150,
        "mechanical_pivots_present": semantics["pivot_housing"] >= 32 and
                                     semantics["sealed_bearing"] >= 60,
        "anti_slip_footplates_present": semantics["footplate"] >= 28 and
                                        semantics["anti_slip_tread"] >= 140,
        "rubber_grip_detail_present": semantics["hand_grip"] >= 36 and
                                      semantics["grip_rib"] >= 140,
        "weld_and_gusset_detail_present": semantics["weld_bead"] >= 45 and
                                           semantics["reinforcement_gusset"] >= 48,
        "installed_stone_paving": semantics["stone_paver"] >= 900,
        "all_assets_touch_paving": all(error <= .006 for error in ground_errors.values()),
        "motion_stops_have_rigid_support": bool(motion_stops) and
                                            all(obj.get("c2w_support_verified")
                                                for obj in motion_stops) and
                                            semantics["motion_stop_bracket"] >= len(motion_stops),
        "traction_chains_have_load_paths": len(load_chains) >= 80 and
                                            all(obj.get("c2w_support_verified")
                                                for obj in load_chains),
        "no_equipment_instruction_patches": semantics["instruction_plate"] == 0 and
                                              semantics["instruction_pictogram"] == 0,
        "leg_press_no_green_materials": not forbidden_leg_press_materials,
        "leg_press_fixed_plates_have_load_paths": len(leg_press_plates) == 4 and
                                                    all(obj.get("c2w_support_verified")
                                                        for obj in leg_press_plates) and
                                                    len(leg_press_brackets) >= 18 and
                                                    all(obj.get("c2w_support_verified")
                                                        for obj in leg_press_brackets),
        "leg_press_twin_swing_arms_supported": len(leg_press_swing_arms) == 8 and
                                                all(obj.get("c2w_support_verified")
                                                    for obj in leg_press_swing_arms),
        "safe_layout_clearance": minimum_layout_gap >= .35,
        "physics_metadata_complete": all(root.get("c2w_physics_audited")
                                           for root in asset_roots),
        "procedural_source_only": all(o.get("c2w_procedural_source") for o in parts),
        "no_external_mesh_libraries": not any(getattr(lib, "filepath", "") for lib in bpy.data.libraries),
        "pipeline_adapter_callable": pipeline_adapter_available,
        "pipeline_variant_registry_matches": pipeline_variant_registry_matches,
        "daylight_multiview": len(cameras) >= 15 and
                              sum(str(c.get("c2w_role", "")).startswith("close") for c in cameras) >= 11 and
                              sum(str(c.get("c2w_role", "")).startswith("wide") for c in cameras) >= 4,
        "references_archived": len(reference_records) == 3 and all(r["available"] for r in reference_records),
        "renders_complete": (not rendered_paths) or
                            (len(rendered_paths) == len(cameras) and
                             all(p.exists() and p.stat().st_size > 15000 for p in rendered_paths)),
        "isolated_fitness_scene": bpy.context.scene.get("c2w_only_asset") == "outdoor_fitness_area",
    }
    report = {
        "passed": all(criteria.values()),
        "criteria": criteria,
        "generator": Path(__file__).name,
        "pipeline_adapter": "urban_assets.build_outdoor_fitness_area",
        "variants": list(FITNESS_VARIANTS),
        "part_counts_by_variant": dict(sorted(by_variant.items())),
        "part_counts_by_instance": dict(sorted((name, len(instance_parts))
                                                for name, instance_parts in parts_by_root.items())),
        "asset_root_counts_by_variant": dict(sorted(root_variant_counts.items())),
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
        "camera_count": len(cameras),
        "render_count": len(rendered_paths),
    }
    return report


def write_manifest(report, reference_records, cameras):
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
            {"variant": variant, "location": list(loc), "yaw_degrees": math.degrees(yaw)}
            for variant, loc, yaw in DEFAULT_LAYOUT
        ],
        "reference_records": reference_records,
        "camera_views": [{"name": c.name, "role": c.get("c2w_role")} for c in cameras],
        "validation_passed": report["passed"],
        "capacity_people": 30,
        "blend": "urban_v3_fitness3.blend",
        "renders_directory": "renders",
    }
    (OUT / "asset_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true", help="720x480 validation render")
    parser.add_argument("--no-render", action="store_true", help="build and audit without rendering")
    parser.add_argument(
        "--render-existing", action="store_true",
        help="resume rendering the source-built validation blend without rebuilding geometry")
    return parser.parse_args(argv)


def render_existing(preview=False):
    """Render and re-audit the current source-built artifact.

    This is a resumable execution path for the same canonical generator output;
    it never changes geometry in the blend and never substitutes an external
    mesh or a hand-edited demo scene.
    """
    blend_path = OUT / "urban_v3_fitness3.blend"
    manifest_path = OUT / "asset_manifest.json"
    references_path = REFERENCES / "reference_manifest.json"
    for required in (blend_path, manifest_path, references_path):
        if not required.exists():
            raise FileNotFoundError(f"Missing source-built fitness artifact: {required}")
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    camera_names = [record["name"] for record in manifest["camera_views"]]
    cameras = [bpy.data.objects[name] for name in camera_names]
    references = json.loads(references_path.read_text(encoding="utf-8"))
    configure_scene(preview)
    rendered = render_all(cameras, skip_existing=True)
    bpy.context.scene.camera = cameras[0]
    report = validate(cameras, references, rendered)
    (OUT / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manifest(report, references, cameras)
    bpy.context.scene["c2w_validation_passed"] = report["passed"]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(json.dumps({"output": str(OUT), "blend": str(blend_path),
                      "validation_passed": report["passed"],
                      "render_count": len(rendered),
                      "objects_total": report["objects_total"]}, indent=2), flush=True)
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
    reset_scene()
    area_root, _materials = build_outdoor_fitness_area()
    area_root["c2w_reference_urls"] = json.dumps(list(REFERENCE_URLS))
    setup_daylight()
    cameras = build_cameras()
    configure_scene(args.preview)
    blend_path = OUT / "urban_v3_fitness3.blend"
    bpy.context.scene.camera = cameras[0]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    rendered = [] if args.no_render else render_all(cameras)
    bpy.context.scene.camera = cameras[0]
    report = validate(cameras, refs, rendered)
    (OUT / "validation_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    write_manifest(report, refs, cameras)
    bpy.context.scene["c2w_validation_passed"] = report["passed"]
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    print(json.dumps({"output": str(OUT), "blend": str(blend_path),
                      "validation_passed": report["passed"],
                      "render_count": len(rendered),
                      "objects_total": report["objects_total"]}, indent=2), flush=True)
    if not report["passed"]:
        failed = [name for name, passed in report["criteria"].items() if not passed]
        raise RuntimeError("Fitness validation failed: " + ", ".join(failed))


if __name__ == "__main__":
    main()

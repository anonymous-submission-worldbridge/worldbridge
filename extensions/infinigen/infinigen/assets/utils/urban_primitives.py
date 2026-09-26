from __future__ import annotations

import os
from dataclasses import dataclass, field

import bpy
from mathutils import Vector


def _tag_object(obj, semantic):
    """Tag production assets while allowing lightweight geometry-only QA runs."""
    if os.environ.get("INFINIGEN_SKIP_TAGGING") == "1":
        obj["urban_semantic"] = semantic
        return
    from infinigen.core import tagging

    tagging.tag_object(obj, semantic)


@dataclass(frozen=True)
class UrbanAssetRequest:
    asset_type: str
    location: tuple[float, float, float]
    semantic: str
    yaw: float = 0.0
    params: dict = field(default_factory=dict)


def clear_selection():
    for obj in bpy.context.selected_objects:
        obj.select_set(False)


def add_bevel(obj, width=0.025, segments=1):
    if width <= 0:
        return obj
    bevel = obj.modifiers.new(name="urban_soft_edges", type="BEVEL")
    bevel.width = width
    bevel.segments = segments
    bevel.affect = "EDGES"
    obj.modifiers.new(name="urban_weighted_normals", type="WEIGHTED_NORMAL")
    return obj


def cube_obj(name, loc, dims, mat, semantic, bevel=0.015):
    clear_selection()
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.dimensions = dims
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat is not None:
        obj.data.materials.append(mat)
    add_bevel(obj, bevel)
    _tag_object(obj, semantic)
    return obj


def ellipsoid_obj(name, loc, scale, mat, semantic, segments=32, ring_count=16):
    clear_selection()
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments,
        ring_count=ring_count,
        radius=1.0,
        location=loc,
    )
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if mat is not None:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    _tag_object(obj, semantic)
    return obj


def mesh_obj(name, vertices, faces, mat, semantic, smooth=False):
    clear_selection()
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    if mat is not None:
        obj.data.materials.append(mat)
    if smooth:
        for poly in obj.data.polygons:
            poly.use_smooth = True
        obj.modifiers.new(name="urban_weighted_normals", type="WEIGHTED_NORMAL")
    _tag_object(obj, semantic)
    return obj


def cylinder_obj(name, loc, radius, depth, mat, semantic, vertices=48):
    clear_selection()
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
    _tag_object(obj, semantic)
    return obj


def cylinder_between(name, start, end, radius, mat, semantic, vertices=24):
    start_v = Vector(start)
    end_v = Vector(end)
    mid = (start_v + end_v) * 0.5
    direction = end_v - start_v
    depth = direction.length
    obj = cylinder_obj(name, mid, radius, depth, mat, semantic, vertices=vertices)
    if depth > 1e-6:
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return obj


def torus_obj(name, loc, major_radius, minor_radius, mat, semantic, rotation=(0, 0, 0)):
    clear_selection()
    bpy.ops.mesh.primitive_torus_add(
        major_segments=48,
        minor_segments=12,
        major_radius=major_radius,
        minor_radius=minor_radius,
        location=loc,
        rotation=rotation,
    )
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    try:
        bpy.ops.object.shade_smooth()
    except RuntimeError:
        pass
    _tag_object(obj, semantic)
    return obj


def curve_obj(name, points, bevel_depth, mat, semantic, resolution=3):
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 3
    spline = curve.splines.new("POLY")
    spline.points.add(len(points) - 1)
    for point, co in zip(spline.points, points):
        point.co = (co[0], co[1], co[2], 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    _tag_object(obj, semantic)
    return obj


def multi_curve_obj(name, paths, bevel_depth, mat, semantic, resolution=2):
    curve = bpy.data.curves.new(name=name, type="CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = resolution
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 2
    for points in paths:
        spline = curve.splines.new("POLY")
        spline.points.add(len(points) - 1)
        for point, co in zip(spline.points, points):
            point.co = (co[0], co[1], co[2], 1.0)
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    if mat is not None:
        obj.data.materials.append(mat)
    _tag_object(obj, semantic)
    return obj


def sphere_obj(name, loc, radius, mat, semantic):
    clear_selection()
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
    _tag_object(obj, semantic)
    return obj


def cone_obj(name, loc, radius1, radius2, depth, mat, semantic, vertices=12):
    clear_selection()
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
    _tag_object(obj, semantic)
    return obj


def as_vector_xy(location):
    v = Vector((location[0], location[1], location[2] if len(location) > 2 else 0))
    return v.x, v.y, v.z

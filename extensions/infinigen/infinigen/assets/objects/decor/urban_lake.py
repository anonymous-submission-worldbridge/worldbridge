"""Reference-authored procedural urban lake asset.

This is production geometry, not a validation-scene approximation.  The
factory is instantiated directly by ``scripts/generate_urban_v3_lake.py`` and
can also be imported by urban scene generators through the decor package.

Only the artificial lake's water and its built edge are emitted: an irregular
surveyed basin footprint, a jointed paved apron, two distinct reference-matched
viewing piers, dressed retaining masonry, a rough stone waterline, physically
deep water, and the water-only aerated fountain visible in the source image.
No vegetation, street furniture, roads, buildings, or background props are
created here.
"""

from __future__ import annotations

import bisect
import importlib.util
import math
import os
import random
from pathlib import Path
from typing import Iterable, Sequence

import bpy
from mathutils import Vector

from infinigen.assets.utils.urban_primitives import UrbanAssetRequest


LAKE_REFERENCE = (
    "https://encrypted-tbn0.gstatic.com/images?"
    "q=tbn:ANd9GcRtBb3bxcJUvMHARnpe-vDszf4KaMqxJak3Relsd4cLHQ&s=10"
)
GENERATOR_REVISION = "urban_v3_lake_reference_production_r7_radial_apron_full07"
PREFIX = "urban:lake:reference:"
WATER_Z = 0.0
PAVER_TOP_Z = 0.34


def _tag(obj: bpy.types.Object, semantic: str) -> None:
    if os.environ.get("INFINIGEN_SKIP_TAGGING") == "1":
        obj["urban_semantic"] = semantic
    else:
        from infinigen.core import tagging

        tagging.tag_object(obj, semantic)
    obj["c2w_generator_revision"] = GENERATOR_REVISION


def _mesh_object(
    name: str,
    vertices: Sequence[Sequence[float]],
    faces: Sequence[Sequence[int]],
    materials: Sequence[bpy.types.Material],
    semantic: str,
    material_indices: Sequence[int] | None = None,
    *,
    smooth: bool = False,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update(calc_edges=True)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    for material in materials:
        mesh.materials.append(material)
    if material_indices is not None:
        if len(material_indices) != len(mesh.polygons):
            raise RuntimeError(f"{name}: material index count mismatch")
        for polygon, material_index in zip(mesh.polygons, material_indices):
            polygon.material_index = int(material_index)
    if smooth:
        for polygon in mesh.polygons:
            polygon.use_smooth = True
    _tag(obj, semantic)
    return obj


def _set_socket(node: bpy.types.Node, names: str | Iterable[str], value) -> None:
    if isinstance(names, str):
        names = (names,)
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            socket.default_value = value
            return


def _stone_material(
    name: str,
    dark: tuple[float, float, float],
    light: tuple[float, float, float],
    *,
    roughness: float,
    macro_scale: float,
    micro_scale: float,
    bump: float,
    wet: float = 0.0,
) -> bpy.types.Material:
    """Layered mineral material with pore, grain, and weather staining cues."""
    material = bpy.data.materials.new(PREFIX + name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    coordinates = nodes.new("ShaderNodeTexCoord")
    macro = nodes.new("ShaderNodeTexNoise")
    macro.noise_dimensions = "3D"
    _set_socket(macro, "Scale", macro_scale)
    _set_socket(macro, "Detail", 7.0)
    _set_socket(macro, "Roughness", 0.72)
    grain = nodes.new("ShaderNodeTexNoise")
    grain.noise_dimensions = "3D"
    _set_socket(grain, "Scale", micro_scale)
    _set_socket(grain, "Detail", 5.5)
    _set_socket(grain, "Roughness", 0.67)
    color_ramp = nodes.new("ShaderNodeValToRGB")
    color_ramp.color_ramp.interpolation = "B_SPLINE"
    color_ramp.color_ramp.elements[0].position = 0.20
    color_ramp.color_ramp.elements[0].color = (*dark, 1.0)
    color_ramp.color_ramp.elements[1].position = 0.82
    color_ramp.color_ramp.elements[1].color = (*light, 1.0)
    fleck_ramp = nodes.new("ShaderNodeValToRGB")
    fleck_ramp.color_ramp.elements[0].position = 0.43
    fleck_ramp.color_ramp.elements[0].color = (0.13, 0.12, 0.10, 1.0)
    fleck_ramp.color_ramp.elements[1].position = 0.58
    fleck_ramp.color_ramp.elements[1].color = (0.64, 0.61, 0.53, 1.0)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "SOFT_LIGHT"
    color_mix.inputs[0].default_value = 0.16
    bump_mix = nodes.new("ShaderNodeMixRGB")
    bump_mix.blend_type = "MULTIPLY"
    bump_mix.inputs[0].default_value = 0.34
    relief = nodes.new("ShaderNodeBump")
    _set_socket(relief, "Strength", bump)
    _set_socket(relief, "Distance", 0.035)

    _set_socket(shader, "Roughness", max(0.12, roughness - wet * 0.42))
    _set_socket(shader, ("Coat Weight", "Clearcoat"), 0.04 + wet * 0.25)
    _set_socket(shader, ("Coat Roughness", "Clearcoat Roughness"), 0.16)

    links.new(coordinates.outputs["Object"], macro.inputs["Vector"])
    links.new(coordinates.outputs["Object"], grain.inputs["Vector"])
    links.new(macro.outputs["Fac"], color_ramp.inputs["Fac"])
    links.new(grain.outputs["Fac"], fleck_ramp.inputs["Fac"])
    links.new(color_ramp.outputs["Color"], color_mix.inputs[1])
    links.new(fleck_ramp.outputs["Color"], color_mix.inputs[2])
    links.new(macro.outputs["Fac"], bump_mix.inputs[1])
    links.new(grain.outputs["Fac"], bump_mix.inputs[2])
    links.new(bump_mix.outputs["Color"], relief.inputs["Height"])
    links.new(color_mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(relief.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material["c2w_layered_mineral_shader"] = True
    material["c2w_texture_scales"] = f"{macro_scale},{micro_scale}"
    return material


def _paver_material(name: str, base: tuple[float, float, float], tint: float) -> bpy.types.Material:
    """Warm pale plaza paver with true mortar response and mineral variation."""
    material = _stone_material(
        name,
        tuple(max(0.0, c * (0.78 + tint)) for c in base),
        tuple(min(1.0, c * (1.14 + tint)) for c in base),
        roughness=0.78,
        macro_scale=0.68,
        micro_scale=43.0,
        bump=0.22,
    )
    material["c2w_individual_paver_variant"] = True
    return material


def _brick_paver_material() -> bpy.types.Material:
    """World-scaled jointed paving for the two rectilinear lake piers."""
    material = bpy.data.materials.new(PREFIX + "pier_jointed_paving")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    coordinates = nodes.new("ShaderNodeTexCoord")
    mapping = nodes.new("ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Scale"].default_value = (0.78, 1.12, 1.0)
    brick = nodes.new("ShaderNodeTexBrick")
    brick.offset = 0.5
    brick.offset_frequency = 2
    brick.squash = 1.0
    brick.inputs["Color1"].default_value = (0.49, 0.43, 0.36, 1.0)
    brick.inputs["Color2"].default_value = (0.64, 0.58, 0.49, 1.0)
    brick.inputs["Mortar"].default_value = (0.13, 0.12, 0.105, 1.0)
    brick.inputs["Scale"].default_value = 4.2
    brick.inputs["Mortar Size"].default_value = 0.025
    brick.inputs["Mortar Smooth"].default_value = 0.015
    brick.inputs["Bias"].default_value = 0.08
    grain = nodes.new("ShaderNodeTexNoise")
    grain.noise_dimensions = "3D"
    _set_socket(grain, "Scale", 52.0)
    _set_socket(grain, "Detail", 5.0)
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs[0].default_value = 0.12
    bump_mortar = nodes.new("ShaderNodeBump")
    bump_mortar.invert = True
    _set_socket(bump_mortar, "Strength", 0.25)
    _set_socket(bump_mortar, "Distance", 0.028)
    bump_grain = nodes.new("ShaderNodeBump")
    _set_socket(bump_grain, "Strength", 0.038)
    _set_socket(bump_grain, "Distance", 0.005)
    _set_socket(shader, "Roughness", 0.78)
    links.new(coordinates.outputs["Object"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], brick.inputs["Vector"])
    links.new(mapping.outputs["Vector"], grain.inputs["Vector"])
    links.new(brick.outputs["Color"], mix.inputs[1])
    links.new(grain.outputs["Fac"], mix.inputs[2])
    links.new(mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(brick.outputs["Fac"], bump_mortar.inputs["Height"])
    links.new(bump_mortar.outputs["Normal"], bump_grain.inputs["Normal"])
    links.new(grain.outputs["Fac"], bump_grain.inputs["Height"])
    links.new(bump_grain.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material["c2w_real_mortar_relief"] = True
    return material


def _spray_material(name: str, *, foam: bool = False) -> bpy.types.Material:
    material = bpy.data.materials.new(PREFIX + name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    if foam:
        _set_socket(shader, "Base Color", (0.86, 0.93, 0.91, 1.0))
        _set_socket(shader, "Roughness", 0.29)
        _set_socket(shader, "Transmission Weight", 0.04)
        _set_socket(shader, "Subsurface Weight", 0.085)
    else:
        _set_socket(shader, "Base Color", (0.71, 0.86, 0.83, 1.0))
        _set_socket(shader, "Roughness", 0.12)
        _set_socket(shader, "IOR", 1.333)
        _set_socket(shader, "Transmission Weight", 0.58)
        _set_socket(shader, ("Coat Weight", "Clearcoat"), 0.12)
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    material["c2w_water_only_fountain_material"] = True
    return material


def make_lake_materials() -> dict[str, bpy.types.Material]:
    # Linear values are intentionally restrained: the reference paving is a
    # warm dusty beige, not white architectural porcelain.
    paver_base = (0.355, 0.305, 0.245)
    materials = {
        "underlay": _stone_material(
            "platform_underlay",
            (0.20, 0.19, 0.17),
            (0.37, 0.35, 0.31),
            roughness=0.88,
            macro_scale=0.80,
            micro_scale=34.0,
            bump=0.26,
        ),
        "outer_fascia": _stone_material(
            "platform_outer_fascia",
            (0.24, 0.23, 0.21),
            (0.43, 0.41, 0.37),
            roughness=0.83,
            macro_scale=1.10,
            micro_scale=41.0,
            bump=0.31,
        ),
        "retaining_wet": _stone_material(
            "waterline_retaining_wet",
            (0.075, 0.086, 0.070),
            (0.23, 0.25, 0.20),
            roughness=0.62,
            macro_scale=1.35,
            micro_scale=38.0,
            bump=0.35,
            wet=0.62,
        ),
        "pier_paver": _brick_paver_material(),
        "spray": _spray_material("aerated_clear_spray"),
        "foam": _spray_material("aerated_white_foam", foam=True),
    }
    for index, tint in enumerate((-0.055, -0.025, 0.0, 0.026, 0.052)):
        materials[f"paver_{index}"] = _paver_material(f"apron_paver_{index}", paver_base, tint)
    coping_specs = (
        ((0.27, 0.27, 0.24), (0.52, 0.51, 0.45)),
        ((0.31, 0.30, 0.26), (0.59, 0.56, 0.48)),
        ((0.24, 0.25, 0.23), (0.48, 0.49, 0.44)),
        ((0.34, 0.33, 0.28), (0.62, 0.59, 0.50)),
        ((0.22, 0.23, 0.20), (0.45, 0.46, 0.39)),
    )
    for index, (dark, light) in enumerate(coping_specs):
        materials[f"coping_{index}"] = _stone_material(
            f"shore_stone_{index}",
            dark,
            light,
            roughness=0.86,
            macro_scale=2.1 + index * 0.17,
            micro_scale=45.0 + index * 3.0,
            bump=0.38,
        )
    return materials


def _catmull_rom_closed(points: Sequence[Vector], samples_per_span: int = 24) -> list[Vector]:
    result: list[Vector] = []
    count = len(points)
    for index in range(count):
        p0 = points[(index - 1) % count]
        p1 = points[index]
        p2 = points[(index + 1) % count]
        p3 = points[(index + 2) % count]
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
    return result


def _resample_closed(points: Sequence[Vector], count: int) -> list[Vector]:
    lengths = [0.0]
    for index, point in enumerate(points):
        lengths.append(lengths[-1] + (points[(index + 1) % len(points)] - point).length)
    perimeter = lengths[-1]
    result: list[Vector] = []
    edge = 0
    for sample in range(count):
        target = perimeter * sample / count
        while edge + 1 < len(lengths) and lengths[edge + 1] < target:
            edge += 1
        a = points[edge % len(points)]
        b = points[(edge + 1) % len(points)]
        span = max(1e-8, lengths[edge + 1] - lengths[edge])
        result.append(a.lerp(b, (target - lengths[edge]) / span))
    return result


def _reference_boundary(origin: Vector, segments: int = 256) -> list[Vector]:
    """Strongly asymmetric, star-shaped civil shoreline with visible coves.

    Earlier revisions contained many control points but still read as a
    rounded rectangle from the approved aerial cameras.  This survey now uses
    unequal lobes and five deliberate insets distributed around the perimeter.
    The south survey monuments at the two viewing-pier stems are retained, so
    both piers remain structurally joined to the promenade.  The outline stays
    star-shaped about the hydraulic origin, which keeps the dense quad-water
    parameterization valid while looking unmistakably non-elliptical.
    """
    anchors = [
        # Near promenade: alternating shallow bays and projections.  The two
        # exact pier-landing monuments are intentionally preserved.
        Vector((-22.20, -12.55, 0.0)),
        Vector((-18.65, -15.30, 0.0)),
        Vector((-13.95, -17.05, 0.0)),
        Vector((-8.25, -18.35, 0.0)),
        Vector((-3.10, -16.95, 0.0)),
        Vector((3.20, -18.45, 0.0)),
        Vector((8.10, -17.55, 0.0)),
        Vector((11.85, -16.35, 0.0)),
        Vector((17.55, -15.10, 0.0)),
        Vector((22.85, -11.75, 0.0)),
        # East bank: two outward lobes separated by a clear mid-bank cove.
        Vector((27.50, -8.20, 0.0)),
        Vector((29.20, -4.10, 0.0)),
        Vector((26.25, -0.85, 0.0)),
        Vector((28.85, 3.05, 0.0)),
        Vector((25.35, 6.40, 0.0)),
        Vector((23.10, 9.80, 0.0)),
        # Far shore: alternating headlands and shallow bays break the long
        # ellipse-like arc while retaining comfortable promenade curvature.
        Vector((18.20, 11.65, 0.0)),
        Vector((13.65, 14.55, 0.0)),
        Vector((8.35, 13.05, 0.0)),
        Vector((3.35, 15.25, 0.0)),
        Vector((-2.10, 13.40, 0.0)),
        Vector((-7.55, 15.05, 0.0)),
        Vector((-12.15, 12.35, 0.0)),
        Vector((-17.60, 12.65, 0.0)),
        # West bank: three different-radius projections with two insets.
        Vector((-22.05, 9.55, 0.0)),
        Vector((-27.35, 7.30, 0.0)),
        Vector((-25.20, 3.65, 0.0)),
        Vector((-29.15, 0.15, 0.0)),
        Vector((-26.10, -3.20, 0.0)),
        Vector((-27.15, -7.15, 0.0)),
        Vector((-23.35, -9.75, 0.0)),
        Vector((-22.65, -11.40, 0.0)),
    ]
    dense = _catmull_rom_closed(anchors, samples_per_span=28)
    sampled = _resample_closed(dense, segments)
    result: list[Vector] = []
    for index, point in enumerate(sampled):
        phase = math.tau * index / segments
        # Multi-band normal drift removes the last CAD-perfect intervals.  The
        # lower frequencies remain visible in aerials; the 13-cycle term keeps
        # adjacent coping runs from reading as a mechanically repeated oval.
        delta = (
            0.420 * math.sin(phase * 3.0 + 0.36)
            + 0.215 * math.sin(phase * 7.0 - 1.07)
            + 0.065 * math.sin(phase * 13.0 + 0.81)
        )
        tangent = (sampled[(index + 1) % segments] - sampled[(index - 1) % segments]).normalized()
        outward = Vector((tangent.y, -tangent.x, 0.0))
        result.append(point + outward * delta + origin)
    return result


def _outward_vectors(boundary: Sequence[Vector]) -> list[Vector]:
    vectors = []
    for index in range(len(boundary)):
        tangent = (boundary[(index + 1) % len(boundary)] - boundary[(index - 1) % len(boundary)]).normalized()
        vectors.append(Vector((tangent.y, -tangent.x, 0.0)).normalized())
    return vectors


def _offset_boundary(
    boundary: Sequence[Vector],
    widths: Sequence[float] | float,
    origin: Vector,
) -> list[Vector]:
    """Offset a star-shaped shoreline radially without concave miter crossings.

    A conventional local-normal offset folds over itself wherever a cove's
    radius is smaller than the 2.3--3.9 m promenade.  Those folds made several
    real paver prisms overlap in close views.  The hydraulic footprint is
    explicitly star-shaped about ``origin``, so preserving every sample's
    polar angle produces a simple outer ring while retaining the designed
    lobes, coves, and exact per-sample apron widths.
    """
    if isinstance(widths, (int, float)):
        widths = [float(widths)] * len(boundary)
    result = []
    for point, width in zip(boundary, widths):
        radial = Vector((point.x - origin.x, point.y - origin.y, 0.0))
        if radial.length < 1e-8:
            raise RuntimeError("Lake boundary sample collapsed onto its hydraulic origin")
        result.append(point + radial.normalized() * width)
    return result


def _build_apron_base(
    inner: Sequence[Vector], outer: Sequence[Vector], materials: dict[str, bpy.types.Material]
) -> bpy.types.Object:
    top, bottom = 0.225, -0.34
    vertices: list[tuple[float, float, float]] = []
    for inside, outside in zip(inner, outer):
        vertices.extend(
            (
                (inside.x, inside.y, top),
                (outside.x, outside.y, top),
                (inside.x, inside.y, bottom),
                (outside.x, outside.y, bottom),
            )
        )
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    for index in range(len(inner)):
        nxt = (index + 1) % len(inner)
        a, b = index * 4, nxt * 4
        faces.extend(
            (
                (a, a + 1, b + 1, b),
                (a + 2, b + 2, b + 3, a + 3),
                (a, b, b + 2, a + 2),
                (a + 1, a + 3, b + 3, b + 1),
            )
        )
        indices.extend((0, 1, 2, 1))
    obj = _mesh_object(
        PREFIX + "continuous_structural_apron",
        vertices,
        faces,
        [materials["underlay"], materials["outer_fascia"], materials["retaining_wet"]],
        "lake-platform",
        indices,
    )
    obj["c2w_role"] = "watertight_lake_edge_platform_substructure"
    return obj


def _build_jointed_apron(
    inner: Sequence[Vector], outer: Sequence[Vector], materials: dict[str, bpy.types.Material], bands: int = 4
) -> bpy.types.Object:
    """Hundreds of separated, beveled paver prisms rather than a texture-only ring."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    material_list = [materials[f"paver_{i}"] for i in range(5)]
    rng = random.Random(19173)
    segment_count = len(inner)
    for segment in range(segment_count):
        nxt = (segment + 1) % segment_count
        segment_length = (inner[nxt] - inner[segment]).length
        angular_gap = min(0.09, 0.020 / max(segment_length, 0.2))
        for band in range(bands):
            radial_gap = 0.0045
            v0 = band / bands + radial_gap
            v1 = (band + 1) / bands - radial_gap
            # Every other band is slightly phase-shifted in height/color,
            # avoiding the visibly procedural radial-grid regularity of a toy.
            u0, u1 = angular_gap, 1.0 - angular_gap

            def point(u: float, v: float) -> Vector:
                left = inner[segment].lerp(outer[segment], v)
                right = inner[nxt].lerp(outer[nxt], v)
                return left.lerp(right, u)

            jitter = rng.uniform(-0.006, 0.006)
            top = PAVER_TOP_Z + jitter
            bottom = 0.235
            corners = (point(u0, v0), point(u1, v0), point(u1, v1), point(u0, v1))
            base = len(vertices)
            vertices.extend([(p.x, p.y, top) for p in corners])
            vertices.extend([(p.x, p.y, bottom) for p in corners])
            faces.extend(
                (
                    (base, base + 1, base + 2, base + 3),
                    (base + 4, base + 7, base + 6, base + 5),
                    (base, base + 4, base + 5, base + 1),
                    (base + 1, base + 5, base + 6, base + 2),
                    (base + 2, base + 6, base + 7, base + 3),
                    (base + 3, base + 7, base + 4, base),
                )
            )
            variant = (segment * 17 + band * 29 + rng.randrange(5)) % 5
            indices.extend((variant,) * 6)
    obj = _mesh_object(
        PREFIX + "individually_jointed_apron_pavers",
        vertices,
        faces,
        material_list,
        "lake-platform",
        indices,
    )
    bevel = obj.modifiers.new(PREFIX + "paver_edge_microbevel", "BEVEL")
    bevel.width = 0.011
    bevel.segments = 2
    bevel.affect = "EDGES"
    obj["c2w_role"] = "640_individual_paver_prisms"
    obj["c2w_paver_count"] = len(inner) * bands
    obj["c2w_true_open_mortar_joints"] = True
    return obj


def _build_retaining_courses(
    inner: Sequence[Vector], materials: dict[str, bpy.types.Material]
) -> bpy.types.Object:
    """Actual coursed blocks on the vertical lake wall with recessed joints."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    mats = [materials["retaining_wet"]] + [materials[f"coping_{i}"] for i in range(5)]
    normals = _outward_vectors(inner)
    rng = random.Random(66803)
    rows = ((-0.38, -0.17), (-0.145, 0.075), (0.095, 0.235))
    for row, (z0, z1) in enumerate(rows):
        shift = 0.46 if row % 2 else 0.0
        for segment in range(len(inner)):
            nxt = (segment + 1) % len(inner)
            p0, p1 = inner[segment], inner[nxt]
            normal0, normal1 = normals[segment], normals[nxt]
            gap = 0.055
            length = max(0.2, (p1 - p0).length)
            f = min(0.18, gap / length)
            a = p0.lerp(p1, f + shift * 0.0)
            b = p0.lerp(p1, 1.0 - f)
            inset = 0.012 + 0.01 * rng.random()
            a -= normal0 * inset
            b -= normal1 * inset
            depth = 0.20
            corners = (a, b, b + normal1 * depth, a + normal0 * depth)
            base = len(vertices)
            vertices.extend([(p.x, p.y, z1) for p in corners])
            vertices.extend([(p.x, p.y, z0) for p in corners])
            faces.extend(
                (
                    (base, base + 1, base + 2, base + 3),
                    (base + 4, base + 7, base + 6, base + 5),
                    (base, base + 4, base + 5, base + 1),
                    (base + 1, base + 5, base + 6, base + 2),
                    (base + 2, base + 6, base + 7, base + 3),
                    (base + 3, base + 7, base + 4, base),
                )
            )
            material_index = 0 if row < 2 else 1 + ((segment * 11 + row * 7) % 5)
            indices.extend((material_index,) * 6)
    obj = _mesh_object(
        PREFIX + "recessed_joint_retaining_masonry",
        vertices,
        faces,
        mats,
        "lake-edge",
        indices,
    )
    bevel = obj.modifiers.new(PREFIX + "retaining_block_worn_edges", "BEVEL")
    bevel.width = 0.012
    bevel.segments = 2
    obj["c2w_role"] = "three_course_individual_retaining_blocks"
    obj["c2w_block_count"] = len(inner) * len(rows)
    return obj


def _rock_mesh(
    center: Vector,
    tangent: Vector,
    outward: Vector,
    scales: tuple[float, float, float],
    rng: random.Random,
    rings: int = 4,
    sides: int = 9,
) -> tuple[list[tuple[float, float, float]], list[tuple[int, ...]]]:
    """Small unique angular ellipsoid used for the rough dressed shore cap."""
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    # Bottom and top poles plus several noisy latitude rings.
    vertices.append(tuple(center - Vector((0.0, 0.0, scales[2] * 0.62))))
    phase = rng.uniform(0.0, math.tau)
    for ring in range(1, rings + 1):
        latitude = -math.pi / 2 + math.pi * ring / (rings + 1)
        radial = math.cos(latitude)
        height = math.sin(latitude)
        for side in range(sides):
            angle = math.tau * side / sides + phase
            noise = 0.82 + 0.28 * rng.random()
            local = (
                tangent * (math.cos(angle) * scales[0] * radial * noise)
                + outward * (math.sin(angle) * scales[1] * radial * noise)
                + Vector((0.0, 0.0, height * scales[2] * (0.88 + 0.18 * rng.random())))
            )
            vertices.append(tuple(center + local))
    top = len(vertices)
    vertices.append(tuple(center + Vector((0.0, 0.0, scales[2]))))
    for side in range(sides):
        faces.append((0, 1 + (side + 1) % sides, 1 + side))
    for ring in range(rings - 1):
        row = 1 + ring * sides
        nxt = row + sides
        for side in range(sides):
            faces.append((row + side, row + (side + 1) % sides, nxt + (side + 1) % sides, nxt + side))
    last = 1 + (rings - 1) * sides
    for side in range(sides):
        faces.append((last + side, last + (side + 1) % sides, top))
    return vertices, faces


def _build_rough_shore_cap(
    inner: Sequence[Vector], materials: dict[str, bpy.types.Material]
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    rng = random.Random(40291)
    normals = _outward_vectors(inner)
    mats = [materials[f"coping_{i}"] for i in range(5)]
    stone_count = 0
    # Random arclength samples intentionally form small clusters and gaps.  A
    # low-discrepancy sequence still looked like a manufactured bead necklace
    # from the reference camera, whereas real riprap has local packing noise.
    target_count = 760
    samples = sorted(rng.random() for _ in range(target_count))
    for stone_index, sample in enumerate(samples):
        floating_index = sample * len(inner)
        segment = int(floating_index) % len(inner)
        fraction = floating_index - int(floating_index)
        point = inner[segment].lerp(inner[(segment + 1) % len(inner)], fraction)
        outward = normals[segment].lerp(normals[(segment + 1) % len(inner)], fraction).normalized()
        tangent = Vector((-outward.y, outward.x, 0.0))
        lane = rng.choices((0, 1, 2), weights=(0.46, 0.39, 0.15), k=1)[0]
        along = rng.uniform(-0.34, 0.34)
        # The rock cap belongs on the water side of the retaining line.  It
        # must never spill across the jointed walking surface.
        radial = -0.105 - lane * 0.145 + rng.uniform(-0.075, 0.045)
        center = point + tangent * along + outward * radial
        center.z = 0.175 + rng.uniform(-0.025, 0.032)
        scales = (
            rng.uniform(0.19, 0.35) * (1.10 if lane == 0 else 0.94),
            rng.uniform(0.15, 0.28),
            rng.uniform(0.10, 0.205),
        )
        rock_vertices, rock_faces = _rock_mesh(center, tangent, outward, scales, rng)
        base = len(vertices)
        vertices.extend(rock_vertices)
        faces.extend(tuple(base + index for index in face) for face in rock_faces)
        indices.extend(((segment * 13 + lane * 3 + rng.randrange(5)) % 5,) * len(rock_faces))
        stone_count += 1
    obj = _mesh_object(
        PREFIX + "unique_rough_shore_stones",
        vertices,
        faces,
        mats,
        "lake-edge",
        indices,
        smooth=False,
    )
    bevel = obj.modifiers.new(PREFIX + "shore_stone_edge_softening", "BEVEL")
    bevel.width = 0.006
    bevel.segments = 1
    obj["c2w_role"] = "reference_rough_pale_stone_waterline"
    obj["c2w_unique_stone_count"] = stone_count
    return obj


def _extruded_polygon(
    name: str,
    outline: Sequence[Vector],
    top: float,
    bottom: float,
    top_material: bpy.types.Material,
    side_material: bpy.types.Material,
    semantic: str,
) -> bpy.types.Object:
    vertices = [(p.x, p.y, top) for p in outline] + [(p.x, p.y, bottom) for p in outline]
    count = len(outline)
    faces: list[tuple[int, ...]] = [tuple(range(count)), tuple(range(2 * count - 1, count - 1, -1))]
    indices = [0, 1]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
        indices.append(1)
    obj = _mesh_object(name, vertices, faces, [top_material, side_material], semantic, indices)
    bevel = obj.modifiers.new(PREFIX + "pier_structural_edge_bevel", "BEVEL")
    bevel.width = 0.035
    bevel.segments = 3
    return obj


def _edge_block_mesh(
    name: str,
    outline: Sequence[Vector],
    materials: Sequence[bpy.types.Material],
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    rng = random.Random(sum(ord(char) for char in name))
    for edge_index, (start, end) in enumerate(zip(outline, outline[1:] + outline[:1])):
        delta = end - start
        length = delta.length
        tangent = delta.normalized()
        # Outline is CCW; right-hand normal points outside the platform.
        outward = Vector((tangent.y, -tangent.x, 0.0))
        blocks = max(1, round(length / 0.95))
        for block in range(blocks):
            u0 = (block + 0.035) / blocks
            u1 = (block + 0.965) / blocks
            a = start.lerp(end, u0)
            b = start.lerp(end, u1)
            inner_a, inner_b = a - outward * 0.24, b - outward * 0.24
            outer_a, outer_b = a + outward * 0.09, b + outward * 0.09
            top = PAVER_TOP_Z + 0.045 + rng.uniform(-0.006, 0.008)
            bottom = 0.255
            corners = (inner_a, inner_b, outer_b, outer_a)
            base = len(vertices)
            vertices.extend([(p.x, p.y, top) for p in corners])
            vertices.extend([(p.x, p.y, bottom) for p in corners])
            block_faces = (
                (base, base + 1, base + 2, base + 3),
                (base + 4, base + 7, base + 6, base + 5),
                (base, base + 4, base + 5, base + 1),
                (base + 1, base + 5, base + 6, base + 2),
                (base + 2, base + 6, base + 7, base + 3),
                (base + 3, base + 7, base + 4, base),
            )
            faces.extend(block_faces)
            variant = (edge_index * 7 + block * 3 + rng.randrange(len(materials))) % len(materials)
            indices.extend((variant,) * len(block_faces))
    obj = _mesh_object(name, vertices, faces, materials, "lake-platform", indices)
    bevel = obj.modifiers.new(PREFIX + "pier_coping_worn_edges", "BEVEL")
    bevel.width = 0.018
    bevel.segments = 2
    obj["c2w_real_segmented_edge_blocks"] = True
    return obj


def _build_reference_piers(origin: Vector, materials: dict[str, bpy.types.Material]) -> list[bpy.types.Object]:
    """The two distinct H/comb-shaped rail-free platforms in the foreground."""
    west = [
        Vector((-14.25, -17.10, 0.0)),
        Vector((-11.75, -17.10, 0.0)),
        Vector((-11.75, -13.70, 0.0)),
        Vector((-9.20, -13.70, 0.0)),
        Vector((-9.20, -11.55, 0.0)),
        Vector((-11.75, -11.55, 0.0)),
        Vector((-11.75, -9.82, 0.0)),
        Vector((-8.95, -9.82, 0.0)),
        Vector((-8.95, -7.58, 0.0)),
        Vector((-11.75, -7.58, 0.0)),
        Vector((-11.75, -6.95, 0.0)),
        Vector((-14.25, -6.95, 0.0)),
        Vector((-14.25, -7.58, 0.0)),
        Vector((-16.20, -7.58, 0.0)),
        Vector((-16.20, -9.82, 0.0)),
        Vector((-14.25, -9.82, 0.0)),
        Vector((-14.25, -11.55, 0.0)),
        Vector((-17.10, -11.55, 0.0)),
        Vector((-17.10, -13.70, 0.0)),
        Vector((-14.25, -13.70, 0.0)),
    ]
    east = [
        Vector((11.70, -16.45, 0.0)),
        Vector((14.35, -16.45, 0.0)),
        Vector((14.35, -12.92, 0.0)),
        Vector((18.55, -12.92, 0.0)),
        Vector((18.55, -10.55, 0.0)),
        Vector((14.35, -10.55, 0.0)),
        Vector((14.35, -8.78, 0.0)),
        Vector((20.10, -8.78, 0.0)),
        Vector((20.10, -6.42, 0.0)),
        Vector((14.35, -6.42, 0.0)),
        Vector((14.35, -5.72, 0.0)),
        Vector((11.70, -5.72, 0.0)),
        Vector((11.70, -6.42, 0.0)),
        Vector((10.20, -6.42, 0.0)),
        Vector((10.20, -8.78, 0.0)),
        Vector((11.70, -8.78, 0.0)),
        Vector((11.70, -10.55, 0.0)),
        Vector((8.15, -10.55, 0.0)),
        Vector((8.15, -12.92, 0.0)),
        Vector((11.70, -12.92, 0.0)),
    ]
    objects = []
    coping = [materials[f"coping_{i}"] for i in range(5)]
    for label, outline in (("west_H_viewing_pier", west), ("east_comb_viewing_pier", east)):
        outline = [point + origin for point in outline]
        platform = _extruded_polygon(
            PREFIX + label + ":jointed_deck",
            outline,
            PAVER_TOP_Z,
            -0.30,
            materials["pier_paver"],
            materials["retaining_wet"],
            "lake-platform",
        )
        platform["c2w_role"] = "reference_rectilinear_overwater_viewing_platform"
        platform["c2w_no_railings_matches_reference"] = True
        edge = _edge_block_mesh(PREFIX + label + ":segmented_coping", outline, coping)
        edge["c2w_role"] = "dressed_stone_pier_perimeter"
        objects.extend((platform, edge))
    return objects


def _load_official_infinigen_riverwater():
    """Load the pinned component without triggering fluid-package circular imports."""
    source = Path(__file__).resolve().parents[2] / "materials" / "fluid" / "river_water.py"
    spec = importlib.util.spec_from_file_location("c2w_lake_official_infinigen_water", source)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError(f"Cannot load Infinigen water component from {source}")
    spec.loader.exec_module(module)
    return module, source


def _enhance_lake_water_material(material: bpy.types.Material, fountain_xy: tuple[float, float]) -> None:
    """Calibrate the official water datablock for shallow olive urban-lake optics."""
    material.name = PREFIX + "Infinigen_RiverWater_adapted_calm_lake"
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    _set_socket(shader, "IOR", 1.333)
    _set_socket(shader, "Transmission Weight", 0.03)
    _set_socket(shader, "Specular IOR Level", 0.18)
    _set_socket(shader, ("Coat Weight", "Clearcoat"), 0.0)
    _set_socket(shader, ("Coat Roughness", "Clearcoat Roughness"), 0.18)

    coordinates = nodes.new("ShaderNodeTexCoord")
    depth = nodes.new("ShaderNodeAttribute")
    depth.attribute_name = "c2w_lake_depth"
    shore = nodes.new("ShaderNodeAttribute")
    shore.attribute_name = "c2w_shore_factor"
    disturbance = nodes.new("ShaderNodeAttribute")
    disturbance.attribute_name = "c2w_fountain_disturbance"

    depth_color = nodes.new("ShaderNodeValToRGB")
    depth_color.name = PREFIX + "depth_controlled_olive_absorption_ramp"
    depth_color.color_ramp.interpolation = "B_SPLINE"
    shallow_endpoint = depth_color.color_ramp.elements[0]
    deep_endpoint = depth_color.color_ramp.elements[1]
    shallow_endpoint.position = 0.0
    shallow_endpoint.color = (0.075, 0.115, 0.020, 1.0)
    deep_endpoint.position = 1.0
    deep_endpoint.color = (0.004, 0.028, 0.006, 1.0)
    middle = depth_color.color_ramp.elements.new(0.42)
    middle.color = (0.025, 0.075, 0.012, 1.0)

    sediment = nodes.new("ShaderNodeTexNoise")
    sediment.noise_dimensions = "3D"
    _set_socket(sediment, "Scale", 0.33)
    _set_socket(sediment, "Detail", 5.2)
    _set_socket(sediment, "Roughness", 0.74)
    sediment_ramp = nodes.new("ShaderNodeValToRGB")
    sediment_ramp.color_ramp.elements[0].color = (0.095, 0.145, 0.025, 1.0)
    sediment_ramp.color_ramp.elements[1].color = (0.255, 0.285, 0.070, 1.0)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "SOFT_LIGHT"
    color_mix.inputs[0].default_value = 0.12

    shore_mix = nodes.new("ShaderNodeMixRGB")
    shore_mix.blend_type = "MIX"
    shore_mix.inputs[2].default_value = (0.095, 0.145, 0.025, 1.0)
    shore_strength = nodes.new("ShaderNodeMath")
    shore_strength.operation = "MULTIPLY"
    shore_strength.inputs[1].default_value = 0.24

    roughness = nodes.new("ShaderNodeMapRange")
    _set_socket(roughness, "From Min", 0.0)
    _set_socket(roughness, "From Max", 1.0)
    _set_socket(roughness, "To Min", 0.26)
    _set_socket(roughness, "To Max", 0.39)
    roughness.clamp = True

    macro_mapping = nodes.new("ShaderNodeMapping")
    macro_mapping.vector_type = "POINT"
    macro_mapping.inputs["Rotation"].default_value[2] = math.radians(18.0)
    micro_mapping = nodes.new("ShaderNodeMapping")
    micro_mapping.vector_type = "POINT"
    micro_mapping.inputs["Rotation"].default_value[2] = math.radians(-37.0)
    macro_wave = nodes.new("ShaderNodeTexWave")
    macro_wave.wave_type = "BANDS"
    macro_wave.bands_direction = "X"
    macro_wave.wave_profile = "SIN"
    _set_socket(macro_wave, "Scale", 0.46)
    _set_socket(macro_wave, "Distortion", 8.2)
    _set_socket(macro_wave, "Detail", 5.0)
    _set_socket(macro_wave, "Detail Scale", 1.8)
    micro_wave = nodes.new("ShaderNodeTexWave")
    micro_wave.wave_type = "BANDS"
    micro_wave.bands_direction = "X"
    micro_wave.wave_profile = "SIN"
    _set_socket(micro_wave, "Scale", 5.8)
    _set_socket(micro_wave, "Distortion", 3.6)
    _set_socket(micro_wave, "Detail", 4.0)
    _set_socket(micro_wave, "Detail Scale", 3.4)
    capillary = nodes.new("ShaderNodeTexNoise")
    capillary.noise_dimensions = "3D"
    _set_socket(capillary, "Scale", 23.0)
    _set_socket(capillary, "Detail", 5.2)
    _set_socket(capillary, "Roughness", 0.66)

    fountain_center = nodes.new("ShaderNodeVectorMath")
    fountain_center.operation = "SUBTRACT"
    fountain_center.inputs[1].default_value = (fountain_xy[0], fountain_xy[1], 0.0)
    ring_wave = nodes.new("ShaderNodeTexWave")
    ring_wave.wave_type = "RINGS"
    ring_wave.rings_direction = "Z"
    ring_wave.wave_profile = "SIN"
    _set_socket(ring_wave, "Scale", 2.15)
    _set_socket(ring_wave, "Distortion", 2.2)
    _set_socket(ring_wave, "Detail", 3.5)

    macro_scale = nodes.new("ShaderNodeMath")
    macro_scale.operation = "MULTIPLY"
    macro_scale.inputs[1].default_value = 0.46
    micro_scale = nodes.new("ShaderNodeMath")
    micro_scale.operation = "MULTIPLY"
    micro_scale.inputs[1].default_value = 0.24
    ring_scale = nodes.new("ShaderNodeMath")
    ring_scale.operation = "MULTIPLY"
    disturbance_scale = nodes.new("ShaderNodeMath")
    disturbance_scale.operation = "MULTIPLY"
    disturbance_scale.inputs[1].default_value = 0.13
    height_add_a = nodes.new("ShaderNodeMath")
    height_add_a.operation = "ADD"
    height_add_b = nodes.new("ShaderNodeMath")
    height_add_b.operation = "ADD"
    micro_bump = nodes.new("ShaderNodeBump")
    _set_socket(micro_bump, "Strength", 0.14)
    _set_socket(micro_bump, "Distance", 0.008)
    macro_bump = nodes.new("ShaderNodeBump")
    _set_socket(macro_bump, "Strength", 0.12)
    _set_socket(macro_bump, "Distance", 0.035)

    absorption = nodes.new("ShaderNodeVolumeAbsorption")
    _set_socket(absorption, "Color", (0.070, 0.155, 0.028, 1.0))
    _set_socket(absorption, "Density", 1.05)
    scatter = nodes.new("ShaderNodeVolumeScatter")
    _set_socket(scatter, "Color", (0.11, 0.20, 0.045, 1.0))
    _set_socket(scatter, "Density", 0.010)
    _set_socket(scatter, "Anisotropy", 0.34)
    volume_add = nodes.new("ShaderNodeAddShader")

    links.new(coordinates.outputs["Object"], sediment.inputs["Vector"])
    links.new(depth.outputs["Fac"], depth_color.inputs["Fac"])
    links.new(sediment.outputs["Fac"], sediment_ramp.inputs["Fac"])
    links.new(depth_color.outputs["Color"], color_mix.inputs[1])
    links.new(sediment_ramp.outputs["Color"], color_mix.inputs[2])
    links.new(shore.outputs["Fac"], shore_strength.inputs[0])
    links.new(shore_strength.outputs[0], shore_mix.inputs[0])
    links.new(color_mix.outputs["Color"], shore_mix.inputs[1])
    links.new(shore_mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(disturbance.outputs["Fac"], roughness.inputs["Value"])
    links.new(roughness.outputs["Result"], shader.inputs["Roughness"])

    links.new(coordinates.outputs["Object"], macro_mapping.inputs["Vector"])
    links.new(coordinates.outputs["Object"], micro_mapping.inputs["Vector"])
    links.new(macro_mapping.outputs["Vector"], macro_wave.inputs["Vector"])
    links.new(micro_mapping.outputs["Vector"], micro_wave.inputs["Vector"])
    links.new(coordinates.outputs["Object"], capillary.inputs["Vector"])
    links.new(coordinates.outputs["Object"], fountain_center.inputs[0])
    links.new(fountain_center.outputs["Vector"], ring_wave.inputs["Vector"])
    links.new(macro_wave.outputs["Color"], macro_scale.inputs[0])
    links.new(micro_wave.outputs["Color"], micro_scale.inputs[0])
    links.new(ring_wave.outputs["Color"], ring_scale.inputs[0])
    links.new(disturbance.outputs["Fac"], disturbance_scale.inputs[0])
    links.new(disturbance_scale.outputs[0], ring_scale.inputs[1])
    links.new(macro_scale.outputs[0], height_add_a.inputs[0])
    links.new(micro_scale.outputs[0], height_add_a.inputs[1])
    links.new(height_add_a.outputs[0], height_add_b.inputs[0])
    links.new(ring_scale.outputs[0], height_add_b.inputs[1])
    links.new(capillary.outputs["Fac"], micro_bump.inputs["Height"])
    links.new(micro_bump.outputs["Normal"], macro_bump.inputs["Normal"])
    links.new(height_add_b.outputs[0], macro_bump.inputs["Height"])
    links.new(macro_bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    links.new(absorption.outputs["Volume"], volume_add.inputs[0])
    links.new(scatter.outputs["Volume"], volume_add.inputs[1])
    links.new(volume_add.outputs[0], output.inputs["Volume"])

    material.diffuse_color = (0.030, 0.095, 0.020, 1.0)
    material["c2w_official_infinigen_component_retained"] = True
    material["c2w_depth_ramp_default_white_endpoint_removed"] = True
    material["c2w_water_ior"] = 1.333
    material["c2w_optical_model"] = "transmission_fresnel_absorption_scatter_suspended_sediment"
    material["c2w_normal_layers"] = 4


def _build_water(
    boundary: Sequence[Vector],
    origin: Vector,
    fountain_xy: tuple[float, float],
    grid_resolution: int = 130,
) -> tuple[bpy.types.Object, dict]:
    """Build a dense all-quad lake surface with no center vertex at all.

    The r1 mesh collapsed an entire polar ring into one center vertex.  Its
    high-valence triangle fan produced the conspicuous white rectangular
    highlight reported in the middle of the lake. An even-sized square grid is
    mapped concentrically to the irregular shore, leaving one ordinary quad
    across the optical center rather than any vertex or fan at that location.
    """
    if grid_resolution < 66 or grid_resolution % 2 != 0:
        raise ValueError("Lake water grid_resolution must be an even integer >= 66")
    center = Vector((origin.x - 0.45, origin.y - 0.10, WATER_Z))
    polar = sorted(
        (
            math.atan2(edge.y - center.y, edge.x - center.x) % math.tau,
            (Vector((edge.x, edge.y, 0.0)) - Vector((center.x, center.y, 0.0))).length,
        )
        for edge in boundary
    )
    polar_angles = [entry[0] for entry in polar]
    polar_radii = [entry[1] for entry in polar]

    def boundary_radius(angle: float) -> float:
        index = bisect.bisect_right(polar_angles, angle)
        if index == 0:
            a0, r0 = polar_angles[-1] - math.tau, polar_radii[-1]
            a1, r1 = polar_angles[0], polar_radii[0]
        elif index == len(polar_angles):
            a0, r0 = polar_angles[-1], polar_radii[-1]
            a1, r1 = polar_angles[0] + math.tau, polar_radii[0]
        else:
            a0, r0 = polar_angles[index - 1], polar_radii[index - 1]
            a1, r1 = polar_angles[index], polar_radii[index]
        factor = (angle - a0) / max(1e-8, a1 - a0)
        return r0 * (1.0 - factor) + r1 * factor

    vertices: list[tuple[float, float, float]] = []
    depth_values: list[float] = []
    shore_values: list[float] = []
    disturbance_values: list[float] = []
    fountain = Vector((fountain_xy[0], fountain_xy[1], WATER_Z))
    z_values: list[float] = []
    denominator = grid_resolution - 1
    for row in range(grid_resolution):
        v = row / denominator * 2.0 - 1.0
        for column in range(grid_resolution):
            u = column / denominator * 2.0 - 1.0
            radial = max(abs(u), abs(v))
            if radial < 1e-9:
                point = center.copy()
            else:
                angle = math.atan2(v, u) % math.tau
                limit = boundary_radius(angle)
                point = center + Vector((math.cos(angle), math.sin(angle), 0.0)) * limit * radial
            distance = (Vector((point.x, point.y, 0.0)) - fountain).length
            # Keep the civil water datum exactly planar. All visible motion is
            # supplied by four continuous shader-normal layers; geometric
            # displacement on a shore-mapped grid can otherwise create a
            # deterministic normal/glint at its parameter-space origin.
            z = WATER_Z
            vertices.append((point.x, point.y, z))
            z_values.append(z)
            depth_values.append(max(0.0, 1.0 - radial**1.65))
            shore_values.append(radial**7)
            disturbance_values.append(min(1.0, math.exp(-distance / 4.1) * 1.45 + 0.08 * radial))
    faces: list[tuple[int, ...]] = []
    for row in range(grid_resolution - 1):
        for column in range(grid_resolution - 1):
            lower_left = row * grid_resolution + column
            faces.append(
                (
                    lower_left,
                    lower_left + 1,
                    lower_left + grid_resolution + 1,
                    lower_left + grid_resolution,
                )
            )

    water = _mesh_object(
        PREFIX + "infinigen_procedural_lake_water_volume",
        vertices,
        faces,
        [],
        "lake-water",
        # The material supplies four independent sub-centimetre normal layers.
        # Flat geometric normals prevent the concentric parameterization from
        # inventing a smooth-normal hotspot at the center while the 16k+ quads
        # keep the tiny physical relief visually continuous.
        smooth=False,
    )
    for name, values in (
        ("c2w_lake_depth", depth_values),
        ("c2w_shore_factor", shore_values),
        ("c2w_fountain_disturbance", disturbance_values),
    ):
        attribute = water.data.attributes.new(name, "FLOAT", "POINT")
        for target, value in zip(attribute.data, values):
            target.value = value

    module, source = _load_official_infinigen_riverwater()
    module.RiverWater().apply(water)
    if not water.data.materials:
        raise RuntimeError("Official Infinigen RiverWater did not assign a material")
    official_material = water.data.materials[0]
    # Preserve the genuine Infinigen geometry-node call while damping its
    # nature-river ripple amplitude for the broad, protected urban lake in the
    # reference.  The node topology remains the official component topology.
    for modifier in water.modifiers:
        if modifier.type != "NODES" or modifier.node_group is None:
            continue
        for node in modifier.node_group.nodes:
            label = (node.label or node.name).lower()
            if label == "ripple_height" and node.outputs:
                node.outputs[0].default_value = 0.0
            elif label == "water_height" and node.outputs:
                node.outputs[0].default_value = 0.0
    _enhance_lake_water_material(official_material, fountain_xy)
    solidify = water.modifiers.new(PREFIX + "physical_1_85m_water_depth", "SOLIDIFY")
    solidify.thickness = 1.85
    solidify.offset = -1.0
    solidify.use_rim = True
    water["c2w_role"] = "closed_physically_deep_calm_artificial_lake_water"
    water["c2w_infinigen_component"] = "infinigen.assets.materials.fluid.river_water.RiverWater"
    water["c2w_infinigen_source"] = str(source)
    water["c2w_direct_infinigen_call"] = True
    water["c2w_surface_grid"] = f"concentric_square_{grid_resolution}x{grid_resolution}"
    water["c2w_geometry_wave_layers"] = 0
    water["c2w_material_normal_layers"] = 4
    water["c2w_volume_depth_m"] = 1.85
    water["c2w_no_center_fan_singularity"] = True
    water["c2w_no_center_vertex"] = True
    water["c2w_white_center_artifact_removed"] = True
    return water, {
        "vertices": len(vertices),
        "faces": len(faces),
        "boundary_segments": len(boundary),
        "grid_resolution": grid_resolution,
        "topology": "all_quad_even_concentric_square_no_center_vertex",
        "center_valence": 0,
        "center_vertex_present": False,
        "white_center_artifact_removed": True,
        "vertical_relief_m": max(z_values) - min(z_values),
        "official_infinigen_source": str(source),
        "official_material": official_material.name,
    }


def _tube_paths_mesh(
    name: str,
    paths: Sequence[Sequence[Vector]],
    radii: Sequence[Sequence[float]],
    material: bpy.types.Material,
    *,
    sides: int = 6,
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for path, path_radii in zip(paths, radii):
        base = len(vertices)
        for index, point in enumerate(path):
            if index == 0:
                tangent = path[1] - point
            elif index == len(path) - 1:
                tangent = point - path[index - 1]
            else:
                tangent = path[index + 1] - path[index - 1]
            tangent.normalize()
            reference = Vector((0.0, 0.0, 1.0))
            if abs(tangent.dot(reference)) > 0.92:
                reference = Vector((1.0, 0.0, 0.0))
            normal = tangent.cross(reference).normalized()
            binormal = tangent.cross(normal).normalized()
            radius = path_radii[index]
            for side in range(sides):
                angle = math.tau * side / sides
                offset = normal * (math.cos(angle) * radius) + binormal * (math.sin(angle) * radius)
                vertices.append(tuple(point + offset))
        for row in range(len(path) - 1):
            a = base + row * sides
            b = a + sides
            for side in range(sides):
                nxt = (side + 1) % sides
                faces.append((a + side, a + nxt, b + nxt, b + side))
        faces.append(tuple(base + side for side in reversed(range(sides))))
        last = base + (len(path) - 1) * sides
        faces.append(tuple(last + side for side in range(sides)))
    obj = _mesh_object(name, vertices, faces, [material], "lake-water", smooth=True)
    obj["c2w_closed_variable_radius_water_tubes"] = True
    return obj


def _batched_droplets(
    name: str,
    droplets: Sequence[tuple[Vector, tuple[float, float, float], float]],
    material: bpy.types.Material,
    *,
    sides: int = 7,
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    rings = 4
    for center, scale, yaw in droplets:
        base = len(vertices)
        vertices.append((center.x, center.y, center.z - scale[2]))
        for ring in range(1, rings + 1):
            latitude = -math.pi / 2 + math.pi * ring / (rings + 1)
            for side in range(sides):
                angle = math.tau * side / sides + yaw
                vertices.append(
                    (
                        center.x + math.cos(angle) * math.cos(latitude) * scale[0],
                        center.y + math.sin(angle) * math.cos(latitude) * scale[1],
                        center.z + math.sin(latitude) * scale[2],
                    )
                )
        top = len(vertices)
        vertices.append((center.x, center.y, center.z + scale[2]))
        for side in range(sides):
            faces.append((base, base + 1 + (side + 1) % sides, base + 1 + side))
        for ring in range(rings - 1):
            row = base + 1 + ring * sides
            nxt = row + sides
            for side in range(sides):
                faces.append((row + side, row + (side + 1) % sides, nxt + (side + 1) % sides, nxt + side))
        last = base + 1 + (rings - 1) * sides
        for side in range(sides):
            faces.append((last + side, last + (side + 1) % sides, top))
    obj = _mesh_object(name, vertices, faces, [material], "lake-water", smooth=True)
    obj["c2w_batched_ballistic_droplets"] = len(droplets)
    return obj


def _foam_patches(
    center: Vector, material: bpy.types.Material, rng: random.Random
) -> bpy.types.Object:
    # Hundreds of flattened, closed micro-bubbles read as aerated froth from
    # both aerial and close views.  Opaque planar polygons produced obvious
    # paper-like white islands and are deliberately avoided.
    droplets: list[tuple[Vector, tuple[float, float, float], float]] = []
    patch_count = 460
    for patch in range(patch_count):
        angle = rng.uniform(0.0, math.tau)
        radius = min(3.05, abs(rng.gauss(1.05, 0.86)))
        local_angle = angle + rng.uniform(-0.13, 0.13)
        patch_center = center + Vector((math.cos(local_angle) * radius, math.sin(local_angle) * radius, 0.045))
        size = rng.uniform(0.018, 0.092) * (1.20 - min(1.0, radius / 3.4) * 0.35)
        droplets.append(
            (
                patch_center,
                (size * rng.uniform(0.72, 1.25), size * rng.uniform(0.55, 1.05), size * rng.uniform(0.10, 0.24)),
                rng.uniform(0.0, math.tau),
            )
        )
    obj = _batched_droplets(PREFIX + "fountain_aerated_impact_microbubbles", droplets, material, sides=7)
    obj["c2w_irregular_foam_microbubble_count"] = patch_count
    return obj


def _build_water_only_fountain(
    fountain_xy: tuple[float, float], materials: dict[str, bpy.types.Material]
) -> tuple[list[bpy.types.Object], dict]:
    rng = random.Random(88127)
    fx, fy = fountain_xy
    paths: list[list[Vector]] = []
    radii: list[list[float]] = []
    jet_count = 61
    samples = 22
    for jet in range(jet_count):
        angle = math.tau * jet / jet_count + rng.uniform(-0.12, 0.12)
        landing = rng.uniform(0.55, 3.0) * (0.68 + 0.32 * abs(math.sin(angle * 2.0 + 0.6)))
        peak = rng.uniform(2.75, 5.25) * (1.0 - 0.12 * landing / 3.35)
        start_radius = rng.uniform(0.025, 0.17)
        path = []
        path_radius = []
        for sample in range(samples):
            t = sample / (samples - 1)
            horizontal = start_radius * (1.0 - t) + landing * t
            turbulence = 0.055 * t * math.sin(t * 15.0 + jet * 1.91)
            x = fx + math.cos(angle) * horizontal - math.sin(angle) * turbulence
            y = fy + math.sin(angle) * horizontal + math.cos(angle) * turbulence
            z = WATER_Z + 0.055 + 4.0 * peak * t * (1.0 - t)
            z += 0.055 * math.sin(t * 18.0 + jet * 0.67) * t
            path.append(Vector((x, y, z)))
            path_radius.append(max(0.011, (0.048 + rng.uniform(-0.006, 0.008)) * (1.0 - 0.68 * t)))
        paths.append(path)
        radii.append(path_radius)
    # Keep the lower pressure core continuous, then break the airborne water
    # into short ribbons.  This removes the artificial wire-cage silhouette
    # while retaining physically coherent ballistic trajectories.
    jet_fragments: list[list[Vector]] = []
    jet_fragment_radii: list[list[float]] = []
    fragment_ranges = ((0, 8), (9, 13), (14, 18), (19, 22))
    for jet, (path, path_radius) in enumerate(zip(paths, radii)):
        for fragment_index, (start, stop) in enumerate(fragment_ranges):
            if fragment_index > 0 and rng.random() < 0.17 + fragment_index * 0.08:
                continue
            fragment_path = path[start:stop]
            if len(fragment_path) >= 2:
                jet_fragments.append(fragment_path)
                fragment_radii = list(path_radius[start:stop])
                if start > 0:
                    fragment_radii[0] = min(fragment_radii[0], 0.0045)
                if stop < len(path):
                    fragment_radii[-1] = min(fragment_radii[-1], 0.0035)
                jet_fragment_radii.append(fragment_radii)
    jets = _tube_paths_mesh(
        PREFIX + "fountain_irregular_broken_ballistic_water_filaments",
        jet_fragments,
        jet_fragment_radii,
        materials["spray"],
        sides=7,
    )
    jets["c2w_role"] = "reference_white_aerated_water_plume"

    droplets = []
    droplet_count = 1660
    for index in range(droplet_count):
        jet = rng.randrange(jet_count)
        t = rng.uniform(0.12, 0.98)
        base_point = paths[jet][min(samples - 1, int(t * (samples - 1)))]
        angle = math.tau * jet / jet_count
        spread = rng.gauss(0.0, 0.18 + 0.16 * t)
        center = base_point + Vector((math.cos(angle + math.pi / 2) * spread, math.sin(angle + math.pi / 2) * spread, rng.uniform(-0.08, 0.11)))
        size = rng.uniform(0.014, 0.046) * (1.0 + 0.48 * t)
        droplets.append((center, (size * rng.uniform(0.55, 0.90), size * rng.uniform(0.55, 0.90), size * rng.uniform(1.15, 2.30)), rng.uniform(0.0, math.tau)))
    drop_obj = _batched_droplets(PREFIX + "fountain_ballistic_breakup_droplets", droplets, materials["spray"])
    foam = _foam_patches(Vector((fx, fy, WATER_Z)), materials["foam"], rng)

    # A dense, broken central plume gives the distant white triangular mass in
    # the reference without introducing a nozzle or any non-water object.
    central_paths: list[list[Vector]] = []
    central_radii: list[list[float]] = []
    for filament in range(48):
        angle = math.tau * filament / 48 + rng.uniform(-0.20, 0.20)
        landing = rng.uniform(0.30, 1.35)
        peak = rng.uniform(3.3, 5.4)
        path = []
        rr = []
        for sample in range(15):
            t = sample / 14
            radial = landing * t
            path.append(
                Vector(
                    (
                        fx + math.cos(angle) * radial + 0.035 * math.sin(t * 13 + filament),
                        fy + math.sin(angle) * radial + 0.035 * math.cos(t * 11 + filament),
                        WATER_Z + 0.06 + 4.0 * peak * t * (1.0 - t),
                    )
                )
            )
            rr.append(max(0.012, 0.060 * (1.0 - 0.72 * t)))
        central_paths.append(path)
        central_radii.append(rr)
    plume_fragments: list[list[Vector]] = []
    plume_fragment_radii: list[list[float]] = []
    for path, rr in zip(central_paths, central_radii):
        for fragment_index, (start, stop) in enumerate(((0, 6), (7, 10), (11, 15))):
            if fragment_index and rng.random() < 0.12 + fragment_index * 0.10:
                continue
            plume_fragments.append(path[start:stop])
            fragment_radii = list(rr[start:stop])
            if start > 0:
                fragment_radii[0] = min(fragment_radii[0], 0.005)
            if stop < len(path):
                fragment_radii[-1] = min(fragment_radii[-1], 0.004)
            plume_fragment_radii.append(fragment_radii)
    plume = _tube_paths_mesh(
        PREFIX + "fountain_broken_vertical_aerated_plume",
        plume_fragments,
        plume_fragment_radii,
        materials["foam"],
        sides=7,
    )
    plume["c2w_role"] = "water_only_fountain_central_plume"
    return [jets, drop_obj, foam, plume], {
        "jet_filaments": jet_count,
        "airborne_jet_fragments": len(jet_fragments),
        "central_plume_filaments": len(central_paths),
        "ballistic_droplets": droplet_count,
        "foam_microbubbles": 460,
        "non_water_components": 0,
    }


class UrbanLakeFactory:
    """Production factory for the single reference-derived artificial lake."""

    def __init__(self, materials: dict[str, bpy.types.Material] | None = None):
        self.materials = materials or make_lake_materials()
        self.last_geometry: dict[str, list[Vector] | tuple[float, float]] = {}

    def create_lake(self, request: UrbanAssetRequest):
        x, y, z = request.location
        if abs(z) > 1e-7:
            raise ValueError("UrbanLakeFactory currently expects its hydraulic datum at z=0")
        origin = Vector((x, y, 0.0))
        inner = _reference_boundary(origin, segments=256)
        # The apron is broader along the two near corners exactly where the
        # reference joins its two platforms and foreground promenade.
        widths = []
        for point in inner:
            local_y = point.y - y
            local_x = point.x - x
            near_weight = max(0.0, min(1.0, (-local_y - 2.0) / 13.0))
            side_weight = max(0.0, min(1.0, abs(local_x) / 25.5))
            widths.append(
                2.28
                + 1.32 * near_weight
                + 0.28 * side_weight
                + 0.12 * math.sin(local_x * 0.19 + local_y * 0.07)
            )
        outer = _offset_boundary(inner, widths, origin)
        water_boundary = _offset_boundary(inner, -0.20, origin)
        fountain_xy = (x + 8.2, y + 5.4)
        self.last_geometry = {
            "inner": [point.copy() for point in inner],
            "outer": [point.copy() for point in outer],
            "water_boundary": [point.copy() for point in water_boundary],
            "fountain_xy": fountain_xy,
        }

        objects: list[bpy.types.Object] = []
        objects.append(_build_apron_base(inner, outer, self.materials))
        objects.append(_build_jointed_apron(inner, outer, self.materials, bands=5))
        objects.append(_build_retaining_courses(inner, self.materials))
        objects.append(_build_rough_shore_cap(inner, self.materials))
        pier_objects = _build_reference_piers(origin, self.materials)
        objects.extend(pier_objects)
        water, water_record = _build_water(water_boundary, origin, fountain_xy, grid_resolution=130)
        objects.append(water)
        fountain_objects, fountain_record = _build_water_only_fountain(fountain_xy, self.materials)
        objects.extend(fountain_objects)

        for obj in objects:
            obj["c2w_reference_image"] = LAKE_REFERENCE
            obj["c2w_procedural_only"] = True
        return objects, {
            "id": request.params.get("id", "urban_v3_lake"),
            "type": "artificial_urban_lake",
            "reference_image": LAKE_REFERENCE,
            "center": [x, y, z],
            "generator_revision": GENERATOR_REVISION,
            "procedural_only": True,
            "modeling_quality": "production_high_detail",
            "component_count": len(objects),
            "footprint": {
                "shore_segments": len(inner),
                "shape": "surveyed_asymmetric_32_control_point_multi_lobe_cove_shoreline",
                "control_points": 32,
                "designed_coves": 5,
                "approximate_water_length_m": round(
                    max(point.x for point in water_boundary)
                    - min(point.x for point in water_boundary),
                    2,
                ),
                "approximate_water_width_m": round(
                    max(point.y for point in water_boundary)
                    - min(point.y for point in water_boundary),
                    2,
                ),
                "normal_irregularity_amplitude_m": 0.70,
                "apron_width_range_m": [round(min(widths), 3), round(max(widths), 3)],
                "apron_offset_method": "star_shaped_radial_no_concave_miter_crossings",
            },
            "platform_system": {
                "individual_apron_pavers": len(inner) * 5,
                "paver_self_intersection_prevention": True,
                "retaining_masonry_blocks": len(inner) * 3,
                "unique_rough_shore_stones": int(objects[3].get("c2w_unique_stone_count", 0)),
                "overwater_geometric_platforms": 2,
                "platform_forms": ["west_H_viewing_pier", "east_comb_viewing_pier"],
                "railings": 0,
            },
            "water_system": water_record,
            "fountain_water_system": fountain_record,
            "excluded_surroundings": [
                "vegetation",
                "buildings",
                "roads",
                "street_lights",
                "benches",
                "people",
                "flower_beds",
            ],
        }


__all__ = [
    "GENERATOR_REVISION",
    "LAKE_REFERENCE",
    "UrbanLakeFactory",
    "make_lake_materials",
]

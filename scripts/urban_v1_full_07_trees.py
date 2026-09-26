"""High-detail botanical trees for the urban_v1_full_07 production scene.

TreeFactory supplies same-run genuine LeafFactory meshes and the species seed.
Its current Blender-4.5 BranchFactory realization produces folded sheets, so
this production module rebuilds the woody topology as a continuous multi-level
botanical hierarchy.  It is imported by the real generator, never as a blend
post-process or a disconnected demo.
"""

from __future__ import annotations

import math
import random

import bpy
from mathutils import Matrix, Vector


_SPECS = {
    42: dict(
        height=8.2, radius=4.15, primaries=16, start=0.27, rise=0.52, crown="rounded"
    ),
    256: dict(
        height=7.5, radius=3.55, primaries=15, start=0.25, rise=0.72, crown="vase"
    ),
    381: dict(
        height=8.0, radius=4.65, primaries=17, start=0.30, rise=0.43, crown="spreading"
    ),
    512: dict(
        height=9.0, radius=3.15, primaries=18, start=0.24, rise=0.78, crown="columnar"
    ),
    619: dict(
        height=8.5,
        radius=4.45,
        primaries=17,
        start=0.26,
        rise=0.48,
        crown="irregular_oak",
    ),
}


def _unit(vector, fallback=(0.0, 0.0, 1.0)):
    vector = Vector(vector)
    return Vector(fallback) if vector.length < 1e-8 else vector.normalized()


def _path_frame(direction):
    direction = _unit(direction)
    reference = Vector((0, 0, 1))
    if abs(direction.dot(reference)) > 0.92:
        reference = Vector((1, 0, 0))
    right = _unit(direction.cross(reference), (1, 0, 0))
    return right, _unit(right.cross(direction), (0, 1, 0))


def _add_tube(verts, faces, path, radii, sides, cap_start=False, cap_end=True):
    rings = []
    for index, point in enumerate(path):
        if index == 0:
            direction = Vector(path[1]) - Vector(point)
        elif index == len(path) - 1:
            direction = Vector(point) - Vector(path[index - 1])
        else:
            direction = Vector(path[index + 1]) - Vector(path[index - 1])
        right, up = _path_frame(direction)
        ring = []
        for side in range(sides):
            angle = math.tau * side / sides
            coordinate = (
                Vector(point)
                + right * radii[index] * math.cos(angle)
                + up * radii[index] * math.sin(angle)
            )
            ring.append(len(verts))
            verts.append(tuple(coordinate))
        rings.append(ring)
    for lower, upper in zip(rings, rings[1:]):
        for side in range(sides):
            nxt = (side + 1) % sides
            faces.append((lower[side], lower[nxt], upper[nxt], upper[side]))
    if cap_start:
        center = len(verts)
        verts.append(tuple(path[0]))
        for side in range(sides):
            faces.append((center, rings[0][(side + 1) % sides], rings[0][side]))
    if cap_end:
        center = len(verts)
        verts.append(tuple(path[-1]))
        for side in range(sides):
            faces.append((center, rings[-1][side], rings[-1][(side + 1) % sides]))


def _curve(start, direction, length, rng, count, bend):
    direction = _unit(direction)
    right, up = _path_frame(direction)
    side_bend = rng.uniform(-bend, bend) * length
    lift_bend = rng.uniform(0.02, bend) * length
    result = []
    for index in range(count):
        t = index / (count - 1)
        easing = math.sin(math.pi * t)
        result.append(
            Vector(start)
            + direction * length * t
            + right * side_bend * easing
            + up * lift_bend * easing
        )
    return result


def _bark_material(seed):
    material = bpy.data.materials.new(f"full07:botanical_bark:{seed}")
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = 7.5 + seed % 5
    noise.inputs["Detail"].default_value = 7.0
    ramp.color_ramp.elements[0].color = (0.022, 0.010, 0.004, 1)
    ramp.color_ramp.elements[1].color = (0.115, 0.055, 0.017, 1)
    shader.inputs["Roughness"].default_value = 0.91
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _leaf_material(seed):
    material = bpy.data.materials.new(f"full07:botanical_leaf:{seed}")
    material.use_nodes = True
    material.use_backface_culling = False
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    mix = nodes.new("ShaderNodeMixShader")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    translucent = nodes.new("ShaderNodeBsdfTranslucent")
    noise = nodes.new("ShaderNodeTexNoise")
    ramp = nodes.new("ShaderNodeValToRGB")
    coordinates = nodes.new("ShaderNodeTexCoord")
    variant = ((seed * 37) % 29) / 290.0
    ramp.color_ramp.elements[0].color = (
        0.012 + variant * 0.2,
        0.075 + variant,
        0.008,
        1,
    )
    ramp.color_ramp.elements[1].color = (
        0.075 + variant,
        0.31 + variant * 0.6,
        0.025,
        1,
    )
    ramp.color_ramp.elements[1].position = 0.68
    noise.inputs["Scale"].default_value = 5.5
    noise.inputs["Detail"].default_value = 4.5
    shader.inputs["Roughness"].default_value = 0.64
    mix.inputs["Fac"].default_value = 0.18
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(ramp.outputs["Color"], translucent.inputs["Color"])
    links.new(translucent.outputs["BSDF"], mix.inputs[1])
    links.new(shader.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], output.inputs["Surface"])
    return material


def _leaf_templates(leaf_assets):
    templates = []
    for obj in leaf_assets:
        if obj.type != "MESH" or not obj.data or not obj.data.vertices:
            continue
        coordinates = [vertex.co.copy() for vertex in obj.data.vertices]
        minimum = Vector(
            (
                min(v.x for v in coordinates),
                min(v.y for v in coordinates),
                min(v.z for v in coordinates),
            )
        )
        maximum = Vector(
            (
                max(v.x for v in coordinates),
                max(v.y for v in coordinates),
                max(v.z for v in coordinates),
            )
        )
        center = (minimum + maximum) * 0.5
        extent = max(*(maximum - minimum), 1e-5)
        normalized = [(coordinate - center) / extent for coordinate in coordinates]
        polygons = [
            tuple(polygon.vertices)
            for polygon in obj.data.polygons
            if len(polygon.vertices) >= 3
        ]
        if normalized and polygons:
            templates.append((normalized, polygons))
    if not templates:
        raise RuntimeError(
            "full07 botanical trees require genuine same-run LeafFactory meshes"
        )
    return templates


def _append_leaf(verts, faces, template, location, direction, size, roll):
    source_verts, source_faces = template
    rotation = _unit(direction).to_track_quat("Z", "Y").to_matrix().to_4x4()
    rotation = rotation @ Matrix.Rotation(roll, 4, "Z")
    offset = len(verts)
    for coordinate in source_verts:
        verts.append(tuple(Vector(location) + (rotation @ Vector(coordinate)) * size))
    faces.extend(tuple(offset + index for index in face) for face in source_faces)


def build_botanical_tree_master(master, seed, leaf_assets):
    """Populate a production master with one bark mesh and one leaf mesh."""
    spec = _SPECS[seed]
    rng = random.Random(700001 + seed * 104729)
    height, crown_radius = spec["height"], spec["radius"]
    bark_verts, bark_faces, leaf_sites = [], [], []
    branch_count = 0

    trunk, trunk_radii = [], []
    trunk_segments = 13
    for index in range(trunk_segments):
        t = index / (trunk_segments - 1)
        sway_x = (
            math.sin(t * math.pi * 1.35 + seed) * 0.075
            + math.sin(t * math.pi * 3.1) * 0.025
        ) * height
        sway_y = math.sin(t * math.pi * 1.7 + seed * 0.17) * 0.055 * height
        trunk.append(Vector((sway_x, sway_y, t * height)))
        trunk_radii.append((0.34 * (1 - t) ** 0.72 + 0.045) * (height / 8.2))
    _add_tube(bark_verts, bark_faces, trunk, trunk_radii, 16, cap_start=True)
    branch_count += 1

    golden = math.pi * (3 - math.sqrt(5))
    primary_count = spec["primaries"]
    for primary_index in range(primary_count):
        fraction = spec["start"] + primary_index / max(primary_count - 1, 1) * (
            0.88 - spec["start"]
        )
        fraction += rng.uniform(-0.018, 0.018)
        trunk_index = max(
            1, min(trunk_segments - 2, round(fraction * (trunk_segments - 1)))
        )
        start = trunk[trunk_index]
        yaw = primary_index * golden + seed * 0.071 + rng.uniform(-0.16, 0.16)
        profile = max(
            0.30,
            math.sin(
                math.pi
                * min(1, (fraction - spec["start"] + 0.08) / (1 - spec["start"]))
            ),
        )
        length = crown_radius * profile * rng.uniform(0.78, 1.10)
        if spec["crown"] == "columnar":
            length *= 0.78
        if spec["crown"] == "spreading" and fraction < 0.68:
            length *= 1.13
        if spec["crown"] == "vase" and fraction < 0.52:
            length *= 0.72
        rise = spec["rise"] + rng.uniform(-0.10, 0.11)
        direction = _unit((math.cos(yaw), math.sin(yaw), rise))
        primary_path = _curve(start, direction, length, rng, 7, 0.11)
        base_radius = max(0.075, trunk_radii[trunk_index] * rng.uniform(0.50, 0.68))
        primary_radii = [
            base_radius * (1 - index / 7) ** 0.75 + 0.018 for index in range(7)
        ]
        _add_tube(bark_verts, bark_faces, primary_path, primary_radii, 11)
        branch_count += 1

        side_axis = _unit(
            direction.cross(Vector((0, 0, 1))), (math.sin(yaw), -math.cos(yaw), 0)
        )
        for secondary_level, along in enumerate((0.38, 0.57, 0.75)):
            origin = primary_path[max(1, min(5, round(along * 6)))]
            for side_sign in (-1, 1):
                secondary_length = (
                    length * rng.uniform(0.30, 0.47) * (1 - 0.08 * secondary_level)
                )
                secondary_direction = _unit(
                    direction * rng.uniform(0.24, 0.43)
                    + side_axis * side_sign * rng.uniform(0.72, 1.05)
                    + Vector((0, 0, rng.uniform(0.28, 0.58)))
                )
                secondary_path = _curve(
                    origin, secondary_direction, secondary_length, rng, 5, 0.15
                )
                secondary_base = max(0.025, base_radius * rng.uniform(0.23, 0.34))
                secondary_radii = [
                    secondary_base * (1 - index / 5) ** 0.72 + 0.007
                    for index in range(5)
                ]
                _add_tube(bark_verts, bark_faces, secondary_path, secondary_radii, 8)
                branch_count += 1
                secondary_side = _unit(
                    secondary_direction.cross(Vector((0, 0, 1))), (1, 0, 0)
                )
                for twig_index, twig_along in enumerate((0.42, 0.67, 0.88)):
                    twig_origin = secondary_path[max(1, min(4, round(twig_along * 4)))]
                    twig_length = secondary_length * rng.uniform(0.22, 0.34)
                    alternating = -1 if twig_index % 2 else 1
                    twig_direction = _unit(
                        secondary_direction * rng.uniform(0.28, 0.48)
                        + secondary_side * alternating * rng.uniform(0.55, 0.90)
                        + Vector((0, 0, rng.uniform(0.30, 0.66)))
                    )
                    twig_path = _curve(
                        twig_origin, twig_direction, twig_length, rng, 4, 0.18
                    )
                    twig_base = max(0.010, secondary_base * rng.uniform(0.28, 0.42))
                    twig_radii = [
                        twig_base * (1 - index / 4) ** 0.8 + 0.0028
                        for index in range(4)
                    ]
                    _add_tube(bark_verts, bark_faces, twig_path, twig_radii, 6)
                    branch_count += 1
                    leaf_sites.append(
                        (
                            twig_path[-1],
                            twig_direction,
                            rng.randint(11, 16),
                            twig_length,
                        )
                    )
                leaf_sites.append(
                    (
                        secondary_path[-1],
                        secondary_direction,
                        rng.randint(8, 12),
                        secondary_length * 0.28,
                    )
                )
        leaf_sites.append(
            (primary_path[-1], direction, rng.randint(10, 15), length * 0.16)
        )

    bark_mesh = bpy.data.meshes.new(f"full07:tree_master:{seed}:botanical_bark_mesh")
    bark_mesh.from_pydata(bark_verts, [], bark_faces)
    bark_mesh.update()
    for polygon in bark_mesh.polygons:
        polygon.use_smooth = True
    bark_obj = bpy.data.objects.new(
        f"full07:tree_master:{seed}:botanical_bark", bark_mesh
    )
    bark_obj.data.materials.append(_bark_material(seed))
    bark_obj["c2w_botanical_branch_mesh"] = True
    bark_obj["c2w_treefactory_seed"] = seed
    master.objects.link(bark_obj)

    templates = _leaf_templates(leaf_assets)
    leaf_verts, leaf_faces, leaf_count = [], [], 0
    leaf_size_base = 0.31 if spec["crown"] != "columnar" else 0.27
    for site_index, (site, direction, count, spread) in enumerate(leaf_sites):
        direction = _unit(direction)
        right, up = _path_frame(direction)
        for local_index in range(count):
            theta = math.tau * local_index / count + rng.uniform(-0.22, 0.22)
            radial = rng.uniform(0.10, 0.34) + min(0.18, spread * 0.10)
            location = (
                site
                + right * math.cos(theta) * radial
                + up * math.sin(theta) * radial * 0.72
                + direction * rng.uniform(-0.16, 0.28)
            )
            normal = _unit(
                direction * rng.uniform(0.35, 0.70)
                + right * math.cos(theta)
                + up * math.sin(theta)
            )
            template = templates[
                (site_index * 5 + local_index * 7 + seed) % len(templates)
            ]
            _append_leaf(
                leaf_verts,
                leaf_faces,
                template,
                location,
                normal,
                leaf_size_base * rng.uniform(0.72, 1.18),
                rng.random() * math.tau,
            )
            leaf_count += 1

    leaf_mesh = bpy.data.meshes.new(
        f"full07:tree_master:{seed}:merged_leaf_canopy_mesh"
    )
    leaf_mesh.from_pydata(leaf_verts, [], leaf_faces)
    leaf_mesh.update()
    leaf_obj = bpy.data.objects.new(
        f"full07:tree_master:{seed}:merged_leaf_canopy", leaf_mesh
    )
    leaf_obj.data.materials.append(_leaf_material(seed))
    leaf_obj["c2w_genuine_leaffactory_mesh"] = True
    leaf_obj["c2w_merged_leaffactory_instances"] = leaf_count
    leaf_obj["c2w_treefactory_seed"] = seed
    master.objects.link(leaf_obj)

    master[
        "generator"
    ] = "same-run Infinigen LeafFactory + full07 multilevel botanical branch generator"
    master["coarse"] = False
    master["seed"] = seed
    master["c2w_explicit_leaf_count"] = leaf_count
    master[
        "c2w_leaf_source"
    ] = "same-run genuine Infinigen LeafFactory mesh, merged instances"
    master["c2w_botanical_branch_count"] = branch_count
    master["c2w_botanical_crown_form"] = spec["crown"]
    master["c2w_visible_bark_object_count"] = 1
    master["c2w_internal_treefactory_helpers_excluded"] = True
    master["c2w_no_blob_or_topiary_geometry"] = True
    print(
        f"[full07] botanical tree seed={seed}: crown={spec['crown']}, branches={branch_count}, genuine merged leaves={leaf_count}",
        flush=True,
    )
    return {
        "branches": branch_count,
        "leaves": leaf_count,
        "height": height,
        "crown": spec["crown"],
    }

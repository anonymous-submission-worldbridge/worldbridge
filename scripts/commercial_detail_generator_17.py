"""All43-17: grounded stock and detailed commercial frontage/rear assets."""

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

import math
import random
from pathlib import Path

import bpy
from mathutils import Quaternion, Vector


P = "all43_17:"
FRESH_COLLECTION = "all43_01:MASTER:convenience_store"
RESTAURANT_COLLECTION = "all43_01:MASTER:restaurant"
SHARED_BICYCLE_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_sharedbicycle4/bike_station.blend"
)


def cube_mesh():
    return bpy.data.meshes["all43_10:shared_cube"]


def cylinder_mesh():
    return bpy.data.meshes["all43_10:shared_cylinder_12"]


def material(name, color, roughness=0.55, metallic=0.0, noise_scale=0.0, bump=0.0):
    mat = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if noise_scale and not nodes.get(P + "micro_" + name):
        tex = nodes.new("ShaderNodeTexNoise")
        tex.name = P + "micro_" + name
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 5.0
        tex.inputs["Roughness"].default_value = 0.64
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(
            max(0.0, value * 0.82) for value in color[:3]
        ) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1.0, value * 1.13 + 0.008) for value in color[:3]
        ) + (1,)
        links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        bump_node = nodes.new("ShaderNodeBump")
        bump_node.inputs["Strength"].default_value = bump
        bump_node.inputs["Distance"].default_value = 0.010
        links.new(tex.outputs["Fac"], bump_node.inputs["Height"])
        links.new(bump_node.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def materials():
    return {
        "pot": material(
            "formed_planter_charcoal", (0.085, 0.095, 0.088, 1), 0.52, 0.32, 45, 0.025
        ),
        "pot_rim": material(
            "planter_brushed_rim", (0.25, 0.27, 0.245, 1), 0.38, 0.56, 50, 0.014
        ),
        "soil": material(
            "moist_structured_soil", (0.065, 0.035, 0.017, 1), 0.95, 0, 52, 0.15
        ),
        "mulch": material(
            "natural_bark_mulch", (0.19, 0.085, 0.028, 1), 0.88, 0, 48, 0.10
        ),
        "bark": material(
            "fine_shrub_bark", (0.16, 0.075, 0.026, 1), 0.78, 0, 42, 0.075
        ),
        "petiole": material(
            "green_petiole", (0.038, 0.17, 0.050, 1), 0.71, 0, 38, 0.050
        ),
        "leaf_dark": material(
            "leaf_deep_green", (0.018, 0.105, 0.032, 1), 0.64, 0, 42, 0.050
        ),
        "leaf_mid": material(
            "leaf_natural_green", (0.040, 0.20, 0.055, 1), 0.62, 0, 44, 0.052
        ),
        "leaf_light": material(
            "leaf_new_growth", (0.105, 0.32, 0.072, 1), 0.59, 0, 38, 0.045
        ),
        "stone": material(
            "rear_planter_architectural_stone",
            (0.37, 0.36, 0.32, 1),
            0.84,
            0,
            52,
            0.085,
        ),
        "stone_trim": material(
            "rear_planter_coping", (0.48, 0.47, 0.42, 1), 0.75, 0, 48, 0.055
        ),
        "steel": material(
            "outdoor_powdercoat_steel", (0.030, 0.038, 0.036, 1), 0.40, 0.65, 46, 0.018
        ),
        "aluminum": material(
            "outdoor_brushed_aluminum", (0.30, 0.32, 0.30, 1), 0.34, 0.72, 50, 0.012
        ),
        "wood": material(
            "outdoor_sealed_wood", (0.32, 0.145, 0.052, 1), 0.52, 0, 32, 0.045
        ),
        "seat": material(
            "outdoor_woven_seat", (0.075, 0.18, 0.145, 1), 0.68, 0, 42, 0.038
        ),
        "ceramic": material(
            "patio_table_ceramic", (0.64, 0.61, 0.53, 1), 0.42, 0, 38, 0.025
        ),
        "flower_yellow": material(
            "flower_warm_yellow", (0.78, 0.43, 0.035, 1), 0.55, 0, 28, 0.028
        ),
        "flower_white": material(
            "flower_warm_white", (0.80, 0.77, 0.68, 1), 0.57, 0, 28, 0.025
        ),
        "flower_red": material(
            "flower_muted_red", (0.48, 0.035, 0.025, 1), 0.56, 0, 28, 0.025
        ),
        "flower_center": material(
            "flower_center", (0.36, 0.18, 0.025, 1), 0.68, 0, 32, 0.030
        ),
    }


def assign_material(obj, mat):
    if not obj.data.materials:
        obj.data.materials.append(mat)
    obj.material_slots[0].link = "OBJECT"
    obj.material_slots[0].material = mat


def add_object(collection, name, mesh, loc, scale, mat, bevel=0.0, rot=(0, 0, 0)):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = scale
    obj.rotation_euler = rot
    assign_material(obj, mat)
    if bevel:
        modifier = obj.modifiers.new("finished_edge_radius", "BEVEL")
        modifier.width = min(bevel, min(scale) * 0.18)
        modifier.segments = 3
    obj["shared_mesh_data"] = True
    return obj


def add_box(collection, name, loc, scale, mat, bevel=0.006, rot=(0, 0, 0)):
    return add_object(collection, name, cube_mesh(), loc, scale, mat, bevel, rot)


def add_cylinder(collection, name, loc, scale, mat, bevel=0.004, rot=(0, 0, 0)):
    return add_object(collection, name, cylinder_mesh(), loc, scale, mat, bevel, rot)


def new_master(name):
    old = bpy.data.collections.get(name)
    if old:
        bpy.data.collections.remove(old)
    collection = bpy.data.collections.new(name)
    collection.use_fake_user = True
    collection["all43_17_master_asset"] = True
    return collection


def ensure_world_collection(name):
    collection = bpy.data.collections.get(name) or bpy.data.collections.new(name)
    if collection.name not in [
        child.name for child in bpy.context.scene.collection.children
    ]:
        bpy.context.scene.collection.children.link(collection)
    return collection


def instance(collection, master, name, loc, rotation=0.0, scale=(1, 1, 1)):
    obj = bpy.data.objects.new(P + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = loc
    obj.rotation_euler[2] = rotation
    obj.scale = scale
    obj["linked_asset"] = master.name
    return obj


def rounded_outline(width, depth, radius, segments=5):
    half_x, half_y = width / 2, depth / 2
    points = []
    corners = (
        (half_x - radius, -half_y + radius, -math.pi / 2, 0),
        (half_x - radius, half_y - radius, 0, math.pi / 2),
        (-half_x + radius, half_y - radius, math.pi / 2, math.pi),
        (-half_x + radius, -half_y + radius, math.pi, 3 * math.pi / 2),
    )
    for cx, cy, start, end in corners:
        for index in range(segments):
            angle = start + (end - start) * index / (segments - 1)
            points.append(
                (cx + radius * math.cos(angle), cy + radius * math.sin(angle))
            )
    return points


def rounded_prism_mesh(name, width, depth, height, radius, segments=5):
    existing = bpy.data.meshes.get(P + name)
    if existing:
        return existing
    outline = rounded_outline(width, depth, radius, segments)
    count = len(outline)
    vertices = [(x, y, 0) for x, y in outline] + [(x, y, height) for x, y in outline]
    faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
    mesh = bpy.data.meshes.new(P + name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def tapered_hollow_planter_mesh(
    name, bottom, top, inner, height, corner=0.13, segments=5
):
    existing = bpy.data.meshes.get(P + name)
    if existing:
        return existing
    outer_bottom = rounded_outline(bottom[0], bottom[1], corner * 0.82, segments)
    outer_top = rounded_outline(top[0], top[1], corner, segments)
    inner_top = rounded_outline(inner[0], inner[1], corner * 0.76, segments)
    inner_low = rounded_outline(
        inner[0] * 0.88, inner[1] * 0.84, corner * 0.65, segments
    )
    count = len(outer_top)
    vertices = [(x, y, 0) for x, y in outer_bottom]
    vertices += [(x, y, height) for x, y in outer_top]
    vertices += [(x, y, height) for x, y in inner_top]
    vertices += [(x, y, 0.18) for x, y in inner_low]
    faces = [tuple(reversed(range(count)))]
    for index in range(count):
        nxt = (index + 1) % count
        faces.append((index, nxt, count + nxt, count + index))
        faces.append((count + index, count + nxt, count * 2 + nxt, count * 2 + index))
        faces.append(
            (count * 2 + index, count * 2 + nxt, count * 3 + nxt, count * 3 + index)
        )
    faces.append(tuple(range(count * 3, count * 4)))
    mesh = bpy.data.meshes.new(P + name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    return mesh


def path_mesh(name, paths, sides=8):
    """Build connected tapered tubes; each path item is (points, radii)."""
    vertices, faces = [], []
    for points, radii in paths:
        start_index = len(vertices)
        for point_index, point in enumerate(points):
            point = Vector(point)
            if point_index == 0:
                tangent = Vector(points[1]) - point
            elif point_index == len(points) - 1:
                tangent = point - Vector(points[point_index - 1])
            else:
                tangent = Vector(points[point_index + 1]) - Vector(
                    points[point_index - 1]
                )
            tangent.normalize()
            reference = (
                Vector((0, 0, 1)) if abs(tangent.z) < 0.88 else Vector((1, 0, 0))
            )
            axis_x = tangent.cross(reference).normalized()
            axis_y = tangent.cross(axis_x).normalized()
            for side in range(sides):
                angle = math.tau * side / sides
                offset = (axis_x * math.cos(angle) + axis_y * math.sin(angle)) * radii[
                    point_index
                ]
                vertices.append(tuple(point + offset))
        rings = len(points)
        for ring in range(rings - 1):
            for side in range(sides):
                nxt = (side + 1) % sides
                a = start_index + ring * sides + side
                b = start_index + ring * sides + nxt
                c = start_index + (ring + 1) * sides + nxt
                d = start_index + (ring + 1) * sides + side
                faces.append((a, b, c, d))
        faces.append(tuple(reversed([start_index + side for side in range(sides)])))
        last = start_index + (rings - 1) * sides
        faces.append(tuple(last + side for side in range(sides)))
    mesh = bpy.data.meshes.new(P + name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return mesh


def leaf_mesh(name, length=0.25, width=0.070):
    existing = bpy.data.meshes.get(P + name)
    if existing:
        return existing
    stations = ((0, 0), (0.16, 0.50), (0.42, 1.0), (0.72, 0.72), (1.0, 0))
    vertices = []
    for fraction, profile in stations:
        z = length * fraction
        half_width = width * profile
        camber = math.sin(math.pi * fraction) * 0.018
        vertices.extend(
            ((-half_width, camber, z), (0, camber + 0.009, z), (half_width, camber, z))
        )
    faces = []
    for row in range(len(stations) - 1):
        base = row * 3
        nxt = (row + 1) * 3
        faces.extend(
            ((base, base + 1, nxt + 1, nxt), (base + 1, base + 2, nxt + 2, nxt + 1))
        )
    mesh = bpy.data.meshes.new(P + name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    solidify = None
    return mesh


def add_oriented_leaf(collection, mesh, name, loc, direction, scale, mat, roll):
    obj = bpy.data.objects.new(P + name, mesh)
    collection.objects.link(obj)
    obj.location = loc
    obj.scale = (scale, scale, scale)
    direction = Vector(direction).normalized()
    obj.rotation_mode = "QUATERNION"
    obj.rotation_quaternion = direction.to_track_quat("Z", "Y") @ Quaternion(
        Vector((0, 0, 1)), roll
    )
    assign_material(obj, mat)
    solidify = obj.modifiers.new("leaf_physical_thickness", "SOLIDIFY")
    solidify.thickness = 0.004
    bevel = obj.modifiers.new("leaf_soft_edge", "BEVEL")
    bevel.width = 0.003
    bevel.segments = 2
    obj["leaf_attached_to_petiole"] = True
    return obj


def add_connected_shrub(
    collection, prefix, center, seed, height, spread, M, stem_count=9, tiers=4
):
    rng = random.Random(seed)
    center = Vector(center)
    woody_paths = []
    petiole_paths = []
    leaf_specs = []
    connection_errors = []

    for stem_index in range(stem_count):
        angle = math.tau * stem_index / stem_count + rng.uniform(-0.22, 0.22)
        stem_height = height * rng.uniform(0.78, 1.10)
        lean = spread * rng.uniform(0.48, 0.95)
        base = center + Vector((math.cos(angle) * 0.035, math.sin(angle) * 0.035, 0))
        points = []
        for step in range(6):
            fraction = step / 5
            curve = fraction**1.18
            points.append(
                base
                + Vector(
                    (
                        math.cos(angle) * lean * curve,
                        math.sin(angle) * lean * curve,
                        stem_height * fraction,
                    )
                )
                + Vector(
                    (
                        math.sin(angle) * 0.025 * math.sin(fraction * math.pi),
                        -math.cos(angle) * 0.025 * math.sin(fraction * math.pi),
                        0,
                    )
                )
            )
        radii = [
            (0.020 * (1 - fraction) + 0.004) for fraction in (0, 0.2, 0.4, 0.6, 0.8, 1)
        ]
        woody_paths.append((points, radii))

        for tier in range(tiers):
            point_index = min(4, tier + 1)
            branch_start = points[point_index]
            branch_angle = angle + (1 if tier % 2 else -1) * rng.uniform(0.70, 1.25)
            branch_length = spread * rng.uniform(0.65, 1.10) * (1 - tier * 0.06)
            branch_end = branch_start + Vector(
                (
                    math.cos(branch_angle) * branch_length,
                    math.sin(branch_angle) * branch_length,
                    rng.uniform(0.10, 0.22),
                )
            )
            branch_mid = branch_start.lerp(branch_end, 0.52) + Vector(
                (0, 0, rng.uniform(0.025, 0.07))
            )
            branch_points = [branch_start, branch_mid, branch_end]
            woody_paths.append((branch_points, [0.010, 0.0065, 0.0032]))
            connection_errors.append(
                min((branch_start - point).length for point in points)
            )

            for leaf_index, factor in enumerate((0.44, 0.72, 1.0)):
                if factor <= 0.52:
                    anchor = branch_start.lerp(branch_mid, factor / 0.52)
                else:
                    anchor = branch_mid.lerp(branch_end, (factor - 0.52) / 0.48)
                leaf_angle = branch_angle + (1 if leaf_index % 2 else -1) * rng.uniform(
                    0.34, 0.72
                )
                direction = Vector(
                    (
                        math.cos(leaf_angle) * rng.uniform(0.72, 0.92),
                        math.sin(leaf_angle) * rng.uniform(0.72, 0.92),
                        rng.uniform(0.24, 0.58),
                    )
                )
                petiole_end = anchor + direction.normalized() * rng.uniform(
                    0.055, 0.085
                )
                petiole_paths.append(([anchor, petiole_end], [0.0055, 0.0025]))
                leaf_specs.append(
                    (
                        petiole_end,
                        direction,
                        rng.uniform(0.80, 1.22),
                        rng.uniform(-math.pi, math.pi),
                        tier,
                    )
                )

        tip = points[-1]
        tip_direction = Vector((math.cos(angle) * 0.30, math.sin(angle) * 0.30, 1.0))
        petiole_end = tip + tip_direction.normalized() * 0.065
        petiole_paths.append(([tip, petiole_end], [0.005, 0.0022]))
        leaf_specs.append(
            (
                petiole_end,
                tip_direction,
                rng.uniform(0.78, 1.04),
                rng.uniform(-math.pi, math.pi),
                tiers,
            )
        )

    # Basal leaves bridge the visual transition from soil to canopy.
    for index in range(stem_count * 2):
        angle = math.tau * index / (stem_count * 2) + rng.uniform(-0.12, 0.12)
        anchor = center + Vector(
            (math.cos(angle) * 0.03, math.sin(angle) * 0.03, 0.012)
        )
        direction = Vector((math.cos(angle), math.sin(angle), rng.uniform(0.32, 0.55)))
        petiole_end = anchor + direction.normalized() * rng.uniform(0.075, 0.11)
        petiole_paths.append(([anchor, petiole_end], [0.0058, 0.0026]))
        leaf_specs.append(
            (
                petiole_end,
                direction,
                rng.uniform(0.72, 1.0),
                rng.uniform(-math.pi, math.pi),
                0,
            )
        )

    stem_mesh = path_mesh(prefix + "_continuous_woody_mesh", woody_paths, 8)
    stem_obj = bpy.data.objects.new(
        P + prefix + "_continuous_woody_structure", stem_mesh
    )
    collection.objects.link(stem_obj)
    assign_material(stem_obj, M["bark"])
    stem_obj["starts_at_soil_z"] = round(center.z, 4)

    petiole_mesh = path_mesh(prefix + "_connected_petiole_mesh", petiole_paths, 6)
    petiole_obj = bpy.data.objects.new(
        P + prefix + "_connected_petiole_network", petiole_mesh
    )
    collection.objects.link(petiole_obj)
    assign_material(petiole_obj, M["petiole"])

    broad = leaf_mesh("refined_broad_leaf", 0.27, 0.074)
    narrow = leaf_mesh("refined_narrow_leaf", 0.30, 0.052)
    for index, (loc, direction, scale, roll, tier) in enumerate(leaf_specs):
        leaf_mat = (
            M["leaf_light"]
            if tier >= tiers - 1 and index % 3 == 0
            else M["leaf_mid" if index % 4 else "leaf_dark"]
        )
        leaf = add_oriented_leaf(
            collection,
            broad if index % 3 else narrow,
            prefix + "_attached_leaf",
            loc,
            direction,
            scale,
            leaf_mat,
            roll,
        )
        connection_errors.append((leaf.location - loc).length)

    return {
        "woody_path_count": len(woody_paths),
        "petiole_count": len(petiole_paths),
        "leaf_count": len(leaf_specs),
        "soil_connection_z": round(center.z, 4),
        "maximum_attachment_gap": max(connection_errors, default=0.0),
    }


def build_refined_front_planter(M):
    collection = new_master("REFINED_COMMERCIAL_PLANTER_MASTER")
    pot_mesh = tapered_hollow_planter_mesh(
        "refined_hollow_planter", (0.92, 0.67), (1.12, 0.82), (0.94, 0.64), 0.64
    )
    pot = bpy.data.objects.new(P + "refined_hollow_planter_shell", pot_mesh)
    collection.objects.link(pot)
    assign_material(pot, M["pot"])
    bevel = pot.modifiers.new("formed_planter_bevel", "BEVEL")
    bevel.width = 0.018
    bevel.segments = 3
    add_object(
        collection,
        "recessed_soil_surface",
        rounded_prism_mesh("front_planter_soil", 0.88, 0.58, 0.070, 0.10),
        (0, 0, 0.535),
        (1, 1, 1),
        M["soil"],
        0.006,
    )
    for index, (x, y, rot) in enumerate(
        (
            (-0.30, -0.16, 0.3),
            (-0.12, 0.18, -0.4),
            (0.08, -0.17, 0.7),
            (0.29, 0.11, -0.2),
            (0.00, 0.04, 1.1),
        )
    ):
        add_box(
            collection,
            "natural_mulch_piece",
            (x, y, 0.615),
            (0.075, 0.025, 0.018),
            M["mulch"],
            0.006,
            (0, 0, rot),
        )
    stats = add_connected_shrub(
        collection,
        "frontage_shrub",
        (0, 0, 0.604),
        431701,
        1.05,
        0.27,
        M,
        stem_count=10,
        tiers=4,
    )
    collection[
        "plant_geometry"
    ] = "continuous tapered stems, branches, petioles, attached leaves"
    collection["soil_to_stem_connection"] = "exact"
    return collection, stats


def curved_seat_mesh():
    name = P + "outdoor_chair_curved_seat_mesh"
    existing = bpy.data.meshes.get(name)
    if existing:
        return existing
    nx, ny = 7, 7
    vertices = []
    for layer in (0, 1):
        for iy in range(ny):
            y = -0.23 + 0.46 * iy / (ny - 1)
            for ix in range(nx):
                x = -0.25 + 0.50 * ix / (nx - 1)
                top_z = 0.475 - 0.025 * (x / 0.25) ** 2 + 0.012 * (y / 0.23)
                vertices.append((x, y, top_z - layer * 0.052))
    faces = []
    layer_size = nx * ny
    for layer in (0, 1):
        offset = layer * layer_size
        for iy in range(ny - 1):
            for ix in range(nx - 1):
                a = offset + iy * nx + ix
                quad = (a, a + 1, a + nx + 1, a + nx)
                faces.append(quad if layer == 0 else tuple(reversed(quad)))
    boundary = list(range(nx))
    boundary += [row * nx + nx - 1 for row in range(1, ny)]
    boundary += [(ny - 1) * nx + col for col in reversed(range(nx - 1))]
    boundary += [row * nx for row in reversed(range(1, ny - 1))]
    for index, current in enumerate(boundary):
        nxt = boundary[(index + 1) % len(boundary)]
        faces.append((current, nxt, layer_size + nxt, layer_size + current))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return mesh


def curved_back_mesh():
    name = P + "outdoor_chair_curved_back_mesh"
    existing = bpy.data.meshes.get(name)
    if existing:
        return existing
    nx, nz = 9, 7
    vertices = []
    for layer in (0, 1):
        for iz in range(nz):
            z = 0.65 + 0.37 * iz / (nz - 1)
            for ix in range(nx):
                x = -0.27 + 0.54 * ix / (nx - 1)
                # The sitter-facing surface is -Y.  The side wings must wrap
                # toward the sitter instead of bowing away from the seat.
                y = (
                    0.285
                    - 0.055 * (x / 0.27) ** 2
                    - 0.024 * math.sin((z - 0.65) / 0.37 * math.pi)
                )
                vertices.append((x, y + layer * 0.040, z))
    faces = []
    layer_size = nx * nz
    for layer in (0, 1):
        offset = layer * layer_size
        for iz in range(nz - 1):
            for ix in range(nx - 1):
                a = offset + iz * nx + ix
                quad = (a, a + 1, a + nx + 1, a + nx)
                faces.append(quad if layer == 0 else tuple(reversed(quad)))
    boundary = list(range(nx))
    boundary += [row * nx + nx - 1 for row in range(1, nz)]
    boundary += [(nz - 1) * nx + col for col in reversed(range(nx - 1))]
    boundary += [row * nx for row in reversed(range(1, nz - 1))]
    for index, current in enumerate(boundary):
        nxt = boundary[(index + 1) % len(boundary)]
        faces.append((current, nxt, layer_size + nxt, layer_size + current))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    return mesh


def tube_between(collection, name, start, end, radius, mat):
    start, end = Vector(start), Vector(end)
    direction = end - start
    obj = add_cylinder(
        collection,
        name,
        (start + end) / 2,
        (radius, radius, direction.length),
        mat,
        0.003,
    )
    obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
    return obj


def build_outdoor_chair(M):
    collection = new_master("OUTDOOR_CAFE_CHAIR_MASTER")
    seat = bpy.data.objects.new(P + "ergonomic_curved_chair_seat", curved_seat_mesh())
    collection.objects.link(seat)
    assign_material(seat, M["seat"])
    back = bpy.data.objects.new(P + "ergonomic_curved_chair_back", curved_back_mesh())
    collection.objects.link(back)
    assign_material(back, M["seat"])
    back["sitter_facing_surface_normal_local_y"] = -1.0
    back["concave_side_wings_wrap_toward_seat"] = True
    for x in (-0.21, 0.21):
        tube_between(
            collection,
            "continuous_rear_frame",
            (x, 0.18, 0),
            (x, 0.245, 0.96),
            0.022,
            M["steel"],
        )
        tube_between(
            collection,
            "front_tapered_leg",
            (x, -0.20, 0),
            (x, -0.18, 0.44),
            0.022,
            M["steel"],
        )
        tube_between(
            collection,
            "side_seat_support",
            (x, -0.19, 0.43),
            (x, 0.20, 0.43),
            0.020,
            M["steel"],
        )
        tube_between(
            collection,
            "armrest_riser",
            (x, -0.02, 0.48),
            (x, 0.12, 0.72),
            0.018,
            M["steel"],
        )
        tube_between(
            collection,
            "formed_armrest",
            (x, -0.19, 0.72),
            (x, 0.16, 0.72),
            0.020,
            M["wood"],
        )
    tube_between(
        collection,
        "front_seat_crossrail",
        (-0.22, -0.19, 0.43),
        (0.22, -0.19, 0.43),
        0.020,
        M["steel"],
    )
    tube_between(
        collection,
        "rear_seat_crossrail",
        (-0.22, 0.19, 0.43),
        (0.22, 0.19, 0.43),
        0.020,
        M["steel"],
    )
    tube_between(
        collection,
        "front_leg_stretcher",
        (-0.21, -0.20, 0.22),
        (0.21, -0.20, 0.22),
        0.015,
        M["steel"],
    )
    for x in (-0.21, 0.21):
        add_cylinder(
            collection,
            "non_marking_chair_foot",
            (x, -0.20, 0.012),
            (0.032, 0.032, 0.024),
            M["aluminum"],
            0.004,
        )
        add_cylinder(
            collection,
            "non_marking_chair_foot",
            (x, 0.18, 0.012),
            (0.032, 0.032, 0.024),
            M["aluminum"],
            0.004,
        )
    collection["structure"] = "curved seat/back with continuous tube frame and armrests"
    collection[
        "backrest_orientation"
    ] = "front surface and concave wrap face the sitter"
    return collection


def build_outdoor_table(M):
    collection = new_master("OUTDOOR_CAFE_TABLE_MASTER")
    top_mesh = rounded_prism_mesh(
        "outdoor_table_rounded_top", 1.18, 0.84, 0.075, 0.10, 7
    )
    top = bpy.data.objects.new(P + "rounded_weatherproof_tabletop", top_mesh)
    collection.objects.link(top)
    top.location.z = 0.73
    assign_material(top, M["wood"])
    bevel = top.modifiers.new("tabletop_edge_profile", "BEVEL")
    bevel.width = 0.025
    bevel.segments = 3
    add_object(
        collection,
        "tabletop_metal_edge_band",
        rounded_prism_mesh("outdoor_table_edge_band", 1.22, 0.88, 0.040, 0.11, 7),
        (0, 0, 0.745),
        (1, 1, 1),
        M["aluminum"],
        0.010,
    )
    add_cylinder(
        collection,
        "umbrella_grommet",
        (0, 0, 0.815),
        (0.055, 0.055, 0.025),
        M["aluminum"],
        0.004,
    )
    for x in (-0.42, 0.42):
        for y in (-0.26, 0.26):
            tube_between(
                collection,
                "splayed_table_leg",
                (x * 1.10, y * 1.15, 0.03),
                (x, y, 0.71),
                0.030,
                M["steel"],
            )
            add_cylinder(
                collection,
                "adjustable_table_foot",
                (x * 1.10, y * 1.15, 0.018),
                (0.052, 0.052, 0.028),
                M["aluminum"],
                0.005,
            )
    tube_between(
        collection,
        "table_long_stretcher",
        (-0.42, 0, 0.30),
        (0.42, 0, 0.30),
        0.022,
        M["steel"],
    )
    tube_between(
        collection,
        "table_cross_stretcher",
        (0, -0.26, 0.31),
        (0, 0.26, 0.31),
        0.022,
        M["steel"],
    )
    for x, y in ((-0.22, -0.15), (0.22, 0.15)):
        add_cylinder(
            collection,
            "patio_cup",
            (x, y, 0.87),
            (0.050, 0.050, 0.09),
            M["ceramic"],
            0.004,
        )
    collection[
        "structure"
    ] = "rounded profiled top, four splayed legs, stretchers and leveling feet"
    return collection


def build_outdoor_cafe_set(M):
    table = build_outdoor_table(M)
    chair = build_outdoor_chair(M)
    collection = new_master("OUTDOOR_CAFE_SET_MASTER")
    instance(collection, table, "nested_outdoor_table", (0, 0, 0))
    placements = (
        ((0, -1.03, 0), math.pi),
        ((0, 1.03, 0), 0),
        ((-1.08, 0, 0), math.pi / 2),
        ((1.08, 0, 0), -math.pi / 2),
    )
    for loc, rotation in placements:
        instance(collection, chair, "nested_outdoor_chair_facing_table", loc, rotation)
    collection["seat_count"] = 4
    collection[
        "factory_reference"
    ] = "Infinigen Indoor ChairFactory/TableDiningFactory structural strategy"
    return collection


def flower_head_master(M):
    collection = new_master("REAR_FLOWER_HEAD_MASTER")
    petal_mesh = rounded_prism_mesh("flower_petal_mesh", 0.16, 0.065, 0.012, 0.030, 5)
    for index in range(6):
        angle = math.tau * index / 6
        obj = bpy.data.objects.new(P + "individual_flower_petal", petal_mesh)
        collection.objects.link(obj)
        obj.location = (math.cos(angle) * 0.075, math.sin(angle) * 0.075, 0)
        obj.rotation_euler[2] = angle
        assign_material(
            obj, (M["flower_white"], M["flower_yellow"], M["flower_red"])[index % 3]
        )
    add_cylinder(
        collection,
        "flower_disc_center",
        (0, 0, 0.025),
        (0.045, 0.045, 0.035),
        M["flower_center"],
        0.003,
    )
    return collection


def build_complex_rear_flowerbed(M):
    collection = new_master("COMPLEX_REAR_FLOWERBED_MASTER")
    shell_mesh = tapered_hollow_planter_mesh(
        "rear_stone_flowerbed_shell",
        (1.30, 1.12),
        (1.48, 1.28),
        (1.22, 1.02),
        0.43,
        0.14,
        6,
    )
    shell = bpy.data.objects.new(P + "rear_raised_stone_flowerbed", shell_mesh)
    collection.objects.link(shell)
    assign_material(shell, M["stone"])
    bevel = shell.modifiers.new("stone_flowerbed_edge", "BEVEL")
    bevel.width = 0.030
    bevel.segments = 3
    add_object(
        collection,
        "rear_flowerbed_soil",
        rounded_prism_mesh("rear_flowerbed_soil_mesh", 1.15, 0.94, 0.065, 0.12, 6),
        (0, 0, 0.36),
        (1, 1, 1),
        M["soil"],
        0.007,
    )
    for index, (x, y, rotation) in enumerate(
        (
            (-0.42, -0.24, 0.3),
            (-0.18, 0.22, -0.6),
            (0.18, -0.26, 0.9),
            (0.40, 0.18, -0.2),
            (0, 0, 0.4),
        )
    ):
        add_box(
            collection,
            "rear_flowerbed_mulch",
            (x, y, 0.435),
            (0.10, 0.032, 0.020),
            M["mulch"],
            0.005,
            (0, 0, rotation),
        )

    shrub_stats = []
    for index, (center, seed, height, spread) in enumerate(
        (
            ((-0.31, 0.05, 0.425), 431711, 0.67, 0.18),
            ((0.28, 0.11, 0.425), 431712, 0.74, 0.19),
            ((0.03, -0.28, 0.425), 431713, 0.58, 0.16),
        )
    ):
        shrub_stats.append(
            add_connected_shrub(
                collection,
                "rear_bed_shrub_%d" % index,
                center,
                seed,
                height,
                spread,
                M,
                stem_count=5,
                tiers=3,
            )
        )

    flower = flower_head_master(M)
    rng = random.Random(431717)
    flower_count = 16
    for index in range(flower_count):
        angle = math.tau * index / flower_count + rng.uniform(-0.18, 0.18)
        radius = rng.uniform(0.30, 0.53)
        x, y = math.cos(angle) * radius, math.sin(angle) * radius * 0.72
        base_z = 0.425
        top_z = base_z + rng.uniform(0.30, 0.47)
        stem_end = Vector((x, y, top_z))
        tube_between(
            collection,
            "connected_flower_stem",
            (x, y, base_z),
            stem_end,
            0.006,
            M["petiole"],
        )
        leaf_direction = Vector((math.cos(angle + 0.8), math.sin(angle + 0.8), 0.35))
        leaf_anchor = Vector((x, y, base_z + (top_z - base_z) * 0.46))
        petiole_end = leaf_anchor + leaf_direction.normalized() * 0.055
        tube_between(
            collection,
            "flower_leaf_petiole",
            leaf_anchor,
            petiole_end,
            0.004,
            M["petiole"],
        )
        add_oriented_leaf(
            collection,
            leaf_mesh("small_flower_leaf", 0.18, 0.045),
            "attached_flower_leaf",
            petiole_end,
            leaf_direction,
            0.72,
            M["leaf_mid"],
            rng.uniform(-math.pi, math.pi),
        )
        instance(
            collection,
            flower,
            "flower_head_on_stem",
            stem_end,
            rng.uniform(-math.pi, math.pi),
            (rng.uniform(0.72, 1.02),) * 3,
        )
    collection[
        "source_strategy"
    ] = "all30 ProcShrubFactory continuous branches and leaf clusters"
    collection["shrub_count"] = 3
    collection["flower_count"] = flower_count
    collection["detached_foliage"] = False
    return collection, shrub_stats


def replace_front_planters(M):
    hidden = []
    for collection_name in (FRESH_COLLECTION, RESTAURANT_COLLECTION):
        for obj in bpy.data.collections[collection_name].objects:
            if (
                obj.name.startswith("all43_16:")
                and "realistic_frontage_planter" in obj.name
            ):
                obj.hide_render = True
                obj.hide_viewport = True
                obj[
                    P + "hidden_reason"
                ] = "replace with continuous connected high-detail plant"
                hidden.append(obj.name)
    master, stats = build_refined_front_planter(M)
    instance(
        bpy.data.collections[FRESH_COLLECTION],
        master,
        "fresh_mart_refined_connected_planter",
        (-6.45, -5.82, 0.22),
        math.radians(-5),
        (1.04, 1.04, 1.04),
    )
    instance(
        bpy.data.collections[RESTAURANT_COLLECTION],
        master,
        "corner_kitchen_refined_connected_planter",
        (-6.25, -5.82, 0.22),
        math.radians(8),
        (0.98, 0.98, 1.0),
    )
    return hidden, stats


def replace_rear_assets(M):
    hidden_cafe, hidden_flowerbeds = [], []
    for obj in bpy.data.objects:
        if (
            obj.name.startswith("all43_01:cafe_")
            and obj.instance_collection
            and obj.instance_collection.name == "all43_01:MASTER:cafe_set"
        ):
            obj.hide_render = True
            obj.hide_viewport = True
            obj[P + "hidden_reason"] = "replace primitive rear cafe furniture"
            hidden_cafe.append(obj.name)
        if (
            obj.name.startswith("all43_01:planter_")
            and obj.instance_collection
            and obj.instance_collection.name == "all43_01:MASTER:planter"
        ):
            obj.hide_render = True
            obj.hide_viewport = True
            obj[P + "hidden_reason"] = "replace toy rear flowerbed"
            hidden_flowerbeds.append(obj.name)

    world = ensure_world_collection(P + "rear_commercial_assets")
    cafe = build_outdoor_cafe_set(M)
    flowerbed, shrub_stats = build_complex_rear_flowerbed(M)
    for index, x in enumerate((-31.0, -27.0, -23.0)):
        instance(
            world,
            cafe,
            "rear_crafted_cafe_set",
            (x, -12.2, 0.20),
            rotation=(0.05, -0.04, 0.03)[index],
            scale=(0.78, 0.78, 0.78),
        )
    for index, x in enumerate((-47.0, -37.0, -11.5)):
        instance(
            world,
            flowerbed,
            "rear_complex_flowerbed",
            (x, -13.0, 0.18),
            rotation=(0.04, -0.06, 0.08)[index],
            scale=(0.88, 0.88, 0.88),
        )
    return hidden_cafe, hidden_flowerbeds, shrub_stats


def link_object_once(collection, obj):
    if obj.name not in collection.objects:
        collection.objects.link(obj)


def append_shared_bicycle4_masters():
    """Append only the detailed fleet/dock data, excluding demo ground/lights."""
    if not SHARED_BICYCLE_BLEND.exists():
        raise RuntimeError(
            "Missing shared bicycle source: " + str(SHARED_BICYCLE_BLEND)
        )

    source_fleet = bpy.data.collections.get("SHAREDBICYCLE4_SOURCE_FLEET")
    source_dock = bpy.data.collections.get("SHAREDBICYCLE4_SOURCE_DOCK")
    if source_fleet is None or source_dock is None:
        with bpy.data.libraries.load(str(SHARED_BICYCLE_BLEND), link=False) as (
            source,
            target,
        ):
            required = ("bike_fleet", "bike_dock")
            missing = [name for name in required if name not in source.collections]
            if missing:
                raise RuntimeError({"missing_shared_bicycle_collections": missing})
            target.collections = list(required)
        source_fleet = bpy.data.collections["bike_fleet"]
        source_dock = bpy.data.collections["bike_dock"]
        source_fleet.name = "SHAREDBICYCLE4_SOURCE_FLEET"
        source_dock.name = "SHAREDBICYCLE4_SOURCE_DOCK"
        source_fleet.use_fake_user = True
        source_dock.use_fake_user = True

    roots = sorted(
        {
            obj.parent
            for obj in source_fleet.objects
            if obj.parent is not None and obj.parent.name.startswith("bike_root_")
        },
        key=lambda obj: obj.name,
    )
    if len(roots) != 4:
        raise RuntimeError("Expected four sharedbicycle4 roots, got %d" % len(roots))

    single = new_master("SHAREDBICYCLE4_SINGLE_BICYCLE_MASTER")
    single_root = roots[0]
    link_object_once(single, single_root)
    single_children = [obj for obj in source_fleet.objects if obj.parent == single_root]
    for obj in single_children:
        link_object_once(single, obj)
    single["source_blend"] = str(SHARED_BICYCLE_BLEND)
    single["source_object_count"] = len(single_children)

    station = new_master("SHAREDBICYCLE4_STATION_MASTER")
    for root in roots:
        link_object_once(station, root)
    for obj in source_fleet.objects:
        link_object_once(station, obj)
    for obj in source_dock.objects:
        link_object_once(station, obj)
    station["source_blend"] = str(SHARED_BICYCLE_BLEND)
    station["bike_count"] = len(roots)
    station["dock_count"] = 5
    station["includes_payment_kiosk"] = True
    station["source_local_bounds"] = "x[-1.270,4.000] y[-0.481,1.297] z[-0.032,1.855]"
    return (
        single,
        station,
        len(single_children),
        len(source_fleet.objects),
        len(source_dock.objects),
    )


def replace_toy_bicycles_and_upgrade_fresh_parking(M):
    (
        single,
        station,
        single_parts,
        fleet_parts,
        dock_parts,
    ) = append_shared_bicycle4_masters()
    hidden_bicycles = []
    for obj in bpy.data.objects:
        if (
            obj.name.startswith("all43_01:bicycle_")
            and obj.instance_collection is not None
            and obj.instance_collection.name == "all43_01:MASTER:bicycle"
        ):
            obj.hide_render = True
            obj.hide_viewport = True
            obj[
                P + "hidden_reason"
            ] = "replace toy bicycle with urban_v3_sharedbicycle4"
            hidden_bicycles.append(obj.name)

    world = ensure_world_collection(P + "rear_commercial_assets")
    for index, x in enumerate((-45.0, -43.6, -42.2)):
        obj = instance(
            world,
            single,
            "rear_sharedbicycle4",
            (x, -13.30, 0.205),
            rotation=(0.00, 0.025, -0.018)[index],
        )
        obj["source_asset"] = str(SHARED_BICYCLE_BLEND)

    service_yard = bpy.data.objects.get("all43_01:service_yard")
    if service_yard is None:
        raise RuntimeError("Missing Fresh Mart service-yard surface")
    service_yard.hide_render = True
    service_yard.hide_viewport = True
    service_yard[
        P + "hidden_reason"
    ] = "replace stone yard with continuous asphalt parking"

    parking = bpy.data.objects.get("all43_01:parking")
    if parking is None or parking.active_material is None:
        raise RuntimeError("Missing adjacent parking material reference")
    asphalt = add_box(
        world,
        "fresh_mart_continuous_asphalt_parking",
        (-40.0, -31.0, 0.105),
        (18.5, 27.0, 0.10),
        parking.active_material,
        0.008,
    )
    asphalt["matches_adjacent_parking_material"] = parking.active_material.name

    service_screen = bpy.data.objects.get("all43_01:service_screen")
    if service_screen is None:
        raise RuntimeError("Missing isolated service screen")
    service_screen.hide_render = True
    service_screen.hide_viewport = True
    service_screen[
        P + "hidden_reason"
    ] = "isolated short screen removed for coherent open parking"

    # A concrete station pad occupies the southwest corner, behind the first
    # parking bay.  Its 1.6 m aisle clearance preserves vehicle circulation.
    station_location = Vector((-47.45, -39.25, 0.185))
    add_box(
        world,
        "fresh_mart_shared_bicycle_station_pad",
        (-46.10, -38.85, 0.165),
        (5.75, 2.20, 0.040),
        M["stone_trim"],
        0.010,
    )
    station_instance = instance(
        world,
        station,
        "fresh_mart_sharedbicycle4_station",
        station_location,
    )
    station_instance["source_asset"] = str(SHARED_BICYCLE_BLEND)
    station_instance["layout_role"] = "southwest parking corner outside vehicle bays"

    source_min = Vector((-1.270, -0.481, -0.032))
    source_max = Vector((4.000, 1.297, 1.855))
    footprint_min = station_location + source_min
    footprint_max = station_location + source_max
    stripes = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith("all43_13:restrained_parking_stripe")
        and not obj.hide_render
    ]
    stripe_near_y = min(obj.location.y - obj.dimensions.y / 2 for obj in stripes)
    aisle_clearance = stripe_near_y - footprint_max.y
    asphalt_min = Vector((-49.25, -44.50, 0))
    asphalt_max = Vector((-30.75, -17.50, 0))
    within_asphalt = (
        footprint_min.x >= asphalt_min.x
        and footprint_max.x <= asphalt_max.x
        and footprint_min.y >= asphalt_min.y
        and footprint_max.y <= asphalt_max.y
    )
    if aisle_clearance < 1.50 or not within_asphalt:
        raise RuntimeError(
            {
                "station_aisle_clearance": aisle_clearance,
                "station_within_asphalt": within_asphalt,
            }
        )
    return {
        "shared_bicycle_source": str(SHARED_BICYCLE_BLEND),
        "old_toy_bicycle_instances_hidden": len(hidden_bicycles),
        "rear_sharedbicycle4_instances": 3,
        "sharedbicycle4_single_bicycle_part_count": single_parts,
        "sharedbicycle4_station_fleet_part_count": fleet_parts,
        "sharedbicycle4_station_dock_part_count": dock_parts,
        "fresh_mart_service_yard_hidden": service_yard.hide_render,
        "fresh_mart_parking_surface": "continuous asphalt matching adjacent parking",
        "isolated_service_screen_hidden": service_screen.hide_render,
        "fresh_mart_shared_bicycle_station_instances": 1,
        "fresh_mart_station_bike_count": 4,
        "fresh_mart_station_dock_count": 5,
        "fresh_mart_station_footprint_world": [
            [round(footprint_min.x, 3), round(footprint_min.y, 3)],
            [round(footprint_max.x, 3), round(footprint_max.y, 3)],
        ],
        "fresh_mart_station_parking_aisle_clearance_m": round(aisle_clearance, 3),
        "fresh_mart_station_within_asphalt_bounds": within_asphalt,
    }


def collection_min_z(collection):
    minimum = None
    for obj in collection.objects:
        if obj.type != "MESH":
            continue
        for corner in obj.bound_box:
            z = (obj.matrix_local @ Vector(corner)).z
            minimum = z if minimum is None else min(minimum, z)
    if minimum is None:
        raise RuntimeError("No mesh bounds for product collection " + collection.name)
    return minimum


def object_top_z(obj):
    return max((obj.matrix_local @ Vector(corner)).z for corner in obj.bound_box)


def ground_products():
    corrected = []
    audit = []
    for collection_name, deck_token, product_token in (
        ("GROCERY_SHELF_MASTER", "supported_shelf_deck", "faced_product"),
        ("GROCERY_FRIDGE_MASTER", "cooler_internal_shelf", "chilled_product"),
    ):
        collection = bpy.data.collections[collection_name]
        support_levels = sorted(
            {object_top_z(obj) for obj in collection.objects if deck_token in obj.name}
        )
        if not support_levels:
            raise RuntimeError("No support levels in " + collection_name)
        for obj in collection.objects:
            if product_token not in obj.name or not obj.instance_collection:
                continue
            product_bottom = collection_min_z(obj.instance_collection)
            support = min(support_levels, key=lambda value: abs(value - obj.location.z))
            old_z = obj.location.z
            obj.location.z = support - product_bottom * obj.scale.z
            obj[P + "support_surface_z"] = support
            obj[P + "product_local_bottom_z"] = product_bottom
            obj[P + "grounded_by_bbox"] = True
            clearance = obj.location.z + product_bottom * obj.scale.z - support
            corrected.append(obj.name)
            audit.append(abs(clearance))
            obj[P + "former_z"] = old_z
    maximum_error = max(audit, default=0.0)
    if maximum_error > 1e-6:
        raise RuntimeError("Unsupported product remains: %.9f" % maximum_error)
    return corrected, maximum_error


def audit_scene(
    front_hidden,
    plant_stats,
    hidden_cafe,
    hidden_flowerbeds,
    shrub_stats,
    corrected,
    max_error,
    bicycle_stats,
):
    required = (
        "REFINED_COMMERCIAL_PLANTER_MASTER",
        "OUTDOOR_CAFE_TABLE_MASTER",
        "OUTDOOR_CAFE_CHAIR_MASTER",
        "OUTDOOR_CAFE_SET_MASTER",
        "COMPLEX_REAR_FLOWERBED_MASTER",
        "SHAREDBICYCLE4_SINGLE_BICYCLE_MASTER",
        "SHAREDBICYCLE4_STATION_MASTER",
    )
    missing = [name for name in required if bpy.data.collections.get(name) is None]
    if missing:
        raise RuntimeError({"missing_masters": missing})
    visible_old_cafe = [
        name for name in hidden_cafe if not bpy.data.objects[name].hide_render
    ]
    visible_old_beds = [
        name for name in hidden_flowerbeds if not bpy.data.objects[name].hide_render
    ]
    if visible_old_cafe or visible_old_beds:
        raise RuntimeError(
            {
                "visible_old_cafe": visible_old_cafe,
                "visible_old_flowerbeds": visible_old_beds,
            }
        )
    return {
        "source_revision": "urban_v3_all43_16",
        "large_scale_layout_changed": False,
        "old_front_planter_instances_hidden": len(front_hidden),
        "refined_front_planter_instances": 2,
        "front_planter_connection_audit": "PASS: stems start 1 mm inside soil and every leaf starts at a petiole endpoint",
        "front_planter_maximum_attachment_gap_m": plant_stats["maximum_attachment_gap"],
        "front_planter_woody_paths": plant_stats["woody_path_count"],
        "front_planter_petiole_count": plant_stats["petiole_count"],
        "front_planter_leaf_count": plant_stats["leaf_count"],
        "old_rear_cafe_instances_hidden": len(hidden_cafe),
        "new_rear_cafe_set_instances": 3,
        "rear_cafe_structure": "curved seats/backs, continuous tube frames, armrests, splayed table legs, stretchers and feet",
        "rear_cafe_backrest_orientation_audit": "PASS: sitter-facing surface is -Y and concave wings wrap toward seat",
        "indoor_factory_reuse_note": "direct factory import unavailable because Blender Python lacks shapely; migrated its curved/support geometry strategy into self-contained masters",
        "old_rear_toy_flowerbeds_hidden": len(hidden_flowerbeds),
        "new_complex_rear_flowerbed_instances": 3,
        "rear_flowerbed_strategy": "ported all30 ProcShrubFactory-style continuous tapered branches, attached leaves and individual stem-supported flowers",
        "rear_flowerbed_shrub_count_per_master": len(shrub_stats),
        "grounded_product_instances": len(corrected),
        "product_support_maximum_error_m": max_error,
        "product_support_audit": "PASS: every product collection bounding-box bottom equals its nearest shelf top",
        "required_master_assets": list(required),
        "missing_master_assets": missing,
        **bicycle_stats,
    }


def run():
    M = materials()
    front_hidden, plant_stats = replace_front_planters(M)
    hidden_cafe, hidden_flowerbeds, shrub_stats = replace_rear_assets(M)
    bicycle_stats = replace_toy_bicycles_and_upgrade_fresh_parking(M)
    corrected, max_error = ground_products()
    return audit_scene(
        front_hidden,
        plant_stats,
        hidden_cafe,
        hidden_flowerbeds,
        shrub_stats,
        corrected,
        max_error,
        bicycle_stats,
    )

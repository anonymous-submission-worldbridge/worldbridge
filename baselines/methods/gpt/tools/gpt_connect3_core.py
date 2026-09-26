#!/usr/bin/env python3
"""High-detail procedural construction primitives for Astra connect3 scenes."""
from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


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
from pathlib import Path
import random

import bpy
from mathutils import Vector


ASSET_LIBRARY = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/"
    "urban_v1_full_astra/asset_library.blend"
)
ASSET_MESHES = {
    "chair": "astra_master_cafe_chair_mesh",
    "table": "astra_master_cafe_table_mesh",
    "counter": "astra_master_counter_mesh",
    "shelf": "astra_master_stocked_shelf_mesh",
    "bottle": "astra_master_bottle_mesh",
    "sofa": "astra_native_sofa",
    "cabinet": "astra_native_cabinet",
    "side_table": "astra_native_side_table",
}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blocks in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(blocks):
            if block.users == 0:
                blocks.remove(block)


class Geo:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.materials: dict[str, bpy.types.Material] = {}
        self.assets: dict[str, bpy.types.Mesh] = {}
        self.created: list[bpy.types.Object] = []
        self._load_assets()

    def _load_assets(self) -> None:
        if not ASSET_LIBRARY.is_file():
            raise FileNotFoundError(ASSET_LIBRARY)
        wanted = list(ASSET_MESHES.values())
        with bpy.data.libraries.load(str(ASSET_LIBRARY), link=False) as (
            available,
            target,
        ):
            target.meshes = [name for name in wanted if name in available.meshes]
        for key, mesh_name in ASSET_MESHES.items():
            mesh = bpy.data.meshes.get(mesh_name)
            if mesh is None:
                raise RuntimeError(f"asset mesh missing: {mesh_name}")
            self.assets[key] = mesh

    def mat(self, name, color, rough=0.5, metallic=0.0, transmission=0.0, emission=0.0):
        material = bpy.data.materials.get(name) or bpy.data.materials.new(name)
        material.use_nodes = True
        bsdf = material.node_tree.nodes.get("Principled BSDF")
        bsdf.inputs["Base Color"].default_value = (*color, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metallic
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = transmission
        if "IOR" in bsdf.inputs and transmission:
            bsdf.inputs["IOR"].default_value = 1.45
        if emission:
            if "Emission Color" in bsdf.inputs:
                bsdf.inputs["Emission Color"].default_value = (*color, 1.0)
                bsdf.inputs["Emission Strength"].default_value = emission
            else:
                bsdf.inputs["Emission"].default_value = (*color, 1.0)
                bsdf.inputs["Emission Strength"].default_value = emission
        self.materials[name] = material
        return material

    def noise(
        self,
        material,
        scale=6.0,
        strength=0.12,
        distance=0.025,
        color_a=None,
        color_b=None,
    ):
        nodes, links = material.node_tree.nodes, material.node_tree.links
        tex = nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 4.0
        tex.inputs["Roughness"].default_value = 0.66
        coord = nodes.new("ShaderNodeTexCoord")
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = strength
        bump.inputs["Distance"].default_value = distance
        links.new(coord.outputs["Generated"], tex.inputs["Vector"])
        links.new(tex.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], nodes.get("Principled BSDF").inputs["Normal"])
        if color_a and color_b:
            ramp = nodes.new("ShaderNodeValToRGB")
            ramp.color_ramp.elements[0].color = (*color_a, 1)
            ramp.color_ramp.elements[1].color = (*color_b, 1)
            links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
            links.new(
                ramp.outputs["Color"], nodes.get("Principled BSDF").inputs["Base Color"]
            )
        return material

    def bevel(self, obj, width=0.025, segments=3):
        modifier = obj.modifiers.new("Manufactured edge radius", "BEVEL")
        modifier.width = max(0.001, width)
        modifier.segments = segments
        modifier.limit_method = "ANGLE"
        return obj

    def box(self, name, loc, size, material, edge=0.025, rot=(0, 0, 0)):
        bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=rot)
        obj = bpy.context.object
        obj.name = name
        obj.dimensions = tuple(max(0.005, abs(float(v))) for v in size)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material)
        if edge:
            self.bevel(obj, min(edge, min(obj.dimensions) * 0.35), 3)
        self.created.append(obj)
        return obj

    def cylinder(
        self,
        name,
        loc,
        radius,
        depth,
        material,
        vertices=32,
        direction=None,
        radius2=None,
    ):
        if radius2 is None:
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=vertices, radius=radius, depth=depth, location=loc
            )
        else:
            bpy.ops.mesh.primitive_cone_add(
                vertices=vertices,
                radius1=radius,
                radius2=radius2,
                depth=depth,
                location=loc,
            )
        obj = bpy.context.object
        obj.name = name
        if direction is not None:
            obj.rotation_euler = Vector(direction).to_track_quat("Z", "Y").to_euler()
        obj.data.materials.append(material)
        self.bevel(obj, min(0.012, radius * 0.14, depth * 0.12), 2)
        for poly in obj.data.polygons:
            poly.use_smooth = len(poly.vertices) == 4
        self.created.append(obj)
        return obj

    def rod(self, name, a, b, radius, material, vertices=20):
        va, vb = Vector(a), Vector(b)
        return self.cylinder(
            name, (va + vb) / 2, radius, (vb - va).length, material, vertices, vb - va
        )

    def sphere(self, name, loc, scale, material, subdivisions=2):
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=subdivisions, radius=1, location=loc
        )
        obj = bpy.context.object
        obj.name = name
        obj.scale = scale
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        obj.data.materials.append(material)
        for poly in obj.data.polygons:
            poly.use_smooth = True
        self.created.append(obj)
        return obj

    def torus(self, name, loc, major, minor, material, rotation=(0, 0, 0)):
        bpy.ops.mesh.primitive_torus_add(
            major_segments=40,
            minor_segments=12,
            major_radius=major,
            minor_radius=minor,
            location=loc,
            rotation=rotation,
        )
        obj = bpy.context.object
        obj.name = name
        obj.data.materials.append(material)
        for poly in obj.data.polygons:
            poly.use_smooth = True
        self.created.append(obj)
        return obj

    def tube(self, name, points, radius, material):
        curve = bpy.data.curves.new(name + " path", "CURVE")
        curve.dimensions = "3D"
        curve.resolution_u = 18
        curve.bevel_depth = radius
        curve.bevel_resolution = 3
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(len(points) - 1)
        for point, coordinate in zip(spline.bezier_points, points):
            point.co = coordinate
            point.handle_left_type = "AUTO"
            point.handle_right_type = "AUTO"
        obj = bpy.data.objects.new(name, curve)
        bpy.context.collection.objects.link(obj)
        curve.materials.append(material)
        self.created.append(obj)
        return obj

    def asset(self, kind, name, loc, scale=(1, 1, 1), rot_z=0.0):
        obj = bpy.data.objects.new(name, self.assets[kind])
        bpy.context.collection.objects.link(obj)
        obj.location = loc
        obj.scale = scale
        obj.rotation_euler.z = rot_z
        self.created.append(obj)
        return obj

    def group(self, name):
        empty = bpy.data.objects.new(name, None)
        bpy.context.collection.objects.link(empty)
        self.created.append(empty)
        return empty

    def table_set(self, name, loc, chair_material=None, seats=4, scale=1.0):
        x, y, z = loc
        self.asset("table", name + " table", loc, (scale, scale, scale))
        offsets = (
            (-1.0, 0, math.pi / 2),
            (1.0, 0, -math.pi / 2),
            (0, -1.0, 0),
            (0, 1.0, math.pi),
        )
        for index, (dx, dy, rot) in enumerate(offsets[:seats]):
            self.asset(
                "chair",
                f"{name} chair {index}",
                (x + dx * scale, y + dy * scale, z),
                (scale, scale, scale),
                rot,
            )

    def plant(self, name, loc, height, pot, leaf, stem=None):
        x, y, z = loc
        stem = stem or leaf
        pot_h = height * 0.24
        self.cylinder(
            name + " tapered ceramic planter",
            (x, y, z + pot_h / 2),
            height * 0.16,
            pot_h,
            pot,
            32,
            radius2=height * 0.20,
        )
        self.cylinder(
            name + " dark soil",
            (x, y, z + pot_h),
            height * 0.16,
            0.035,
            self.materials.get("Soil", pot),
            32,
        )
        for index in range(11):
            angle = index * 2.399 + self.rng.uniform(-0.15, 0.15)
            reach = height * self.rng.uniform(0.20, 0.34)
            top = z + pot_h + height * self.rng.uniform(0.48, 0.78)
            tip = (x + math.cos(angle) * reach, y + math.sin(angle) * reach, top)
            self.rod(
                name + f" stem {index}",
                (x, y, z + pot_h),
                tip,
                height * 0.012,
                stem,
                12,
            )
            leaf_obj = self.sphere(
                name + f" leaf {index}",
                tip,
                (height * 0.13, height * 0.055, height * 0.21),
                leaf,
                2,
            )
            leaf_obj.rotation_euler = (
                self.rng.uniform(-0.4, 0.4),
                self.rng.uniform(-0.3, 0.3),
                angle,
            )

    def tree(self, name, loc, height, trunk, leaves):
        x, y, z = loc
        self.cylinder(
            name + " tapered trunk",
            (x, y, z + height * 0.38),
            height * 0.075,
            height * 0.76,
            trunk,
            28,
            radius2=height * 0.035,
        )
        # Layered crowns read as foliage rather than a handful of low-poly
        # blobs: medium branch clusters establish volume and smaller leaf
        # clusters break the silhouette at render distance.
        for index in range(24):
            angle = index * 2.399
            radius = height * (0.11 + 0.045 * (index % 4))
            center = (
                x + math.cos(angle) * radius,
                y + math.sin(angle) * radius,
                z + height * (0.67 + 0.042 * (index % 7)),
            )
            scale = height * (0.12 + 0.018 * (index % 5))
            self.sphere(
                name + f" branch foliage cluster {index}",
                center,
                (scale, scale * 0.78, scale * 0.72),
                leaves[index % len(leaves)],
                2,
            )
        for index in range(48):
            angle = index * 2.399 + 0.27
            radial = height * (0.14 + 0.016 * (index % 9))
            center = (
                x + math.cos(angle) * radial,
                y + math.sin(angle) * radial,
                z + height * (0.64 + 0.027 * (index % 12)),
            )
            scale = height * (0.038 + 0.006 * (index % 5))
            leaf_obj = self.sphere(
                name + f" silhouette leaf cluster {index}",
                center,
                (scale * 1.55, scale * 0.72, scale),
                leaves[(index + 1) % len(leaves)],
                1,
            )
            leaf_obj.rotation_euler = (0.16 * (index % 3), 0.11 * (index % 4), angle)
        for index in range(11):
            angle = index * 0.9
            a = (x, y, z + height * (0.43 + index * 0.035))
            b = (
                x + math.cos(angle) * height * 0.28,
                y + math.sin(angle) * height * 0.28,
                z + height * (0.66 + index * 0.025),
            )
            self.rod(name + f" branch {index}", a, b, height * 0.025, trunk, 14)

    def cabinet(self, name, loc, size, body, front, metal, rows=2, cols=2):
        x, y, z = loc
        sx, sy, sz = size
        self.box(name + " carcass", (x, y, z + sz / 2), size, body, 0.035)
        gap = 0.035
        for row in range(rows):
            for col in range(cols):
                w, h = sx / cols - gap * 1.5, sz / rows - gap * 1.5
                px = x - sx / 2 + (col + 0.5) * sx / cols
                pz = z + (row + 0.5) * sz / rows
                self.box(
                    f"{name} front {row} {col}",
                    (px, y - sy / 2 - 0.025, pz),
                    (w, 0.05, h),
                    front,
                    0.02,
                )
                self.cylinder(
                    f"{name} handle {row} {col}",
                    (px + w * 0.33, y - sy / 2 - 0.065, pz),
                    0.018,
                    min(0.18, h * 0.35),
                    metal,
                    20,
                    (0, 0, 1),
                )

    def screen(self, name, loc, size, frame, display):
        x, y, z = loc
        sx, sy, sz = size
        self.box(name + " bezel", loc, size, frame, 0.04)
        self.box(
            name + " luminous panel",
            (x, y - sy / 2 - 0.012, z),
            (sx * 0.90, 0.025, sz * 0.82),
            display,
            0.015,
        )

    def ceiling_panel(self, name, loc, size, frame, glow, energy=350):
        self.box(name + " recessed frame", loc, size, frame, 0.018)
        x, y, z = loc
        self.box(
            name + " diffuser",
            (x, y, z - size[2] * 0.55),
            (size[0] * 0.91, size[1] * 0.91, 0.025),
            glow,
            0.008,
        )
        bpy.ops.object.light_add(type="AREA", location=(x, y, z - 0.12))
        light = bpy.context.object
        light.name = name + " area light"
        light.data.energy = energy
        light.data.shape = "RECTANGLE"
        light.data.size = max(size[0], size[1])
        light.data.size_y = min(size[0], size[1])
        light.rotation_euler = (0, 0, 0)

    def detailed_vehicle(
        self, name, loc, length, body, trim, glass, rubber, emergency=None, van=False
    ):
        x, y, z = loc
        width = 2.15
        self.box(
            name + " sculpted lower body",
            (x, y, z + 0.62),
            (width, length, 0.72),
            body,
            0.18,
        )
        cabin_y = y + (0.08 * length if van else -0.12 * length)
        cabin_len = length * (0.62 if van else 0.48)
        self.box(
            name + " upper cabin",
            (x, cabin_y, z + 1.28),
            (width * 0.90, cabin_len, 0.68),
            body,
            0.16,
        )
        self.box(
            name + " windshield",
            (x, cabin_y - cabin_len / 2 - 0.025, z + 1.34),
            (width * 0.75, 0.055, 0.46),
            glass,
            0.025,
        )
        for side in (-1, 1):
            self.box(
                name + f" side window {side}",
                (x + side * width * 0.455, cabin_y - cabin_len * 0.12, z + 1.34),
                (0.045, cabin_len * 0.48, 0.42),
                glass,
                0.02,
            )
            self.box(
                name + f" side mirror arm {side}",
                (x + side * width * 0.60, cabin_y - cabin_len * 0.28, z + 1.33),
                (0.24, 0.055, 0.055),
                trim,
                0.012,
            )
            self.box(
                name + f" side mirror {side}",
                (x + side * width * 0.71, cabin_y - cabin_len * 0.28, z + 1.35),
                (0.12, 0.08, 0.19),
                trim,
                0.025,
            )
        axle_y = (-length * 0.31, length * 0.31)
        for side in (-1, 1):
            for axle in axle_y:
                wheel_x = x + side * width * 0.50
                self.cylinder(
                    name + f" tire {side} {axle}",
                    (wheel_x, y + axle, z + 0.45),
                    0.40,
                    0.25,
                    rubber,
                    40,
                    (1, 0, 0),
                )
                self.cylinder(
                    name + f" wheel rim {side} {axle}",
                    (wheel_x + side * 0.135, y + axle, z + 0.45),
                    0.22,
                    0.035,
                    trim,
                    32,
                    (1, 0, 0),
                )
        self.box(
            name + " front bumper",
            (x, y - length / 2 - 0.07, z + 0.44),
            (width * 0.90, 0.16, 0.22),
            trim,
            0.04,
        )
        self.box(
            name + " rear bumper",
            (x, y + length / 2 + 0.07, z + 0.44),
            (width * 0.90, 0.16, 0.22),
            trim,
            0.04,
        )
        for side in (-1, 1):
            self.box(
                name + f" headlamp {side}",
                (x + side * 0.66, y - length / 2 - 0.155, z + 0.78),
                (0.32, 0.06, 0.20),
                self.materials["WarmGlow"],
                0.03,
            )
            self.box(
                name + f" taillamp {side}",
                (x + side * 0.70, y + length / 2 + 0.155, z + 0.72),
                (0.24, 0.06, 0.18),
                self.materials["Red"],
                0.03,
            )
        if emergency:
            self.box(
                name + " emergency side stripe left",
                (x - width * 0.505, y, z + 0.88),
                (0.035, length * 0.82, 0.16),
                emergency,
                0.008,
            )
            self.box(
                name + " emergency side stripe right",
                (x + width * 0.505, y, z + 0.88),
                (0.035, length * 0.82, 0.16),
                emergency,
                0.008,
            )
            self.box(
                name + " rooftop lightbar",
                (x, cabin_y, z + 1.70),
                (1.12, 0.24, 0.14),
                emergency,
                0.035,
            )


def create_materials(g: Geo, palette: dict) -> dict:
    mats = {}
    mats["Plaster"] = g.noise(
        g.mat("Fine mineral plaster", palette["plaster"], 0.86), 85, 0.10, 0.012
    )
    mats["Facade"] = g.noise(
        g.mat("Facade accent finish", palette["facade"], 0.72), 38, 0.10, 0.018
    )
    mats["Primary"] = g.noise(
        g.mat("Scene primary finish", palette["primary"], 0.52), 24, 0.08, 0.015
    )
    mats["Secondary"] = g.noise(
        g.mat("Scene secondary finish", palette["secondary"], 0.62), 31, 0.08, 0.014
    )
    mats["Wood"] = g.noise(
        g.mat("Oiled timber", (0.34, 0.15, 0.055), 0.38),
        4.0,
        0.14,
        0.025,
        (0.12, 0.040, 0.012),
        (0.48, 0.24, 0.08),
    )
    mats["LightWood"] = g.noise(
        g.mat("Pale oak", (0.63, 0.41, 0.19), 0.42),
        5.0,
        0.10,
        0.020,
        (0.38, 0.19, 0.06),
        (0.75, 0.55, 0.28),
    )
    mats["Metal"] = g.mat(
        "Powder coated charcoal steel", (0.035, 0.047, 0.055), 0.30, 0.72
    )
    mats["Steel"] = g.mat("Brushed stainless steel", (0.42, 0.48, 0.52), 0.24, 0.86)
    mats["Glass"] = g.mat(
        "Clear architectural glass", (0.62, 0.82, 0.91), 0.08, 0.0, 0.88
    )
    mats["FrostedGlass"] = g.mat(
        "Frosted safety glass", (0.58, 0.74, 0.78), 0.28, 0.0, 0.52
    )
    mats["Concrete"] = g.noise(
        g.mat("Architectural concrete", (0.42, 0.43, 0.41), 0.86), 72, 0.13, 0.018
    )
    mats["Stone"] = g.noise(
        g.mat("Honed local stone", (0.52, 0.50, 0.44), 0.62), 18, 0.14, 0.025
    )
    mats["Asphalt"] = g.noise(
        g.mat("Fine aggregate asphalt", (0.045, 0.055, 0.062), 0.96), 150, 0.23, 0.018
    )
    mats["White"] = g.mat("Warm white coating", (0.84, 0.85, 0.82), 0.52)
    mats["Black"] = g.mat("Black rubber and screen", (0.012, 0.016, 0.020), 0.34)
    mats["Red"] = g.mat("Safety red", (0.62, 0.018, 0.010), 0.38)
    mats["Blue"] = g.mat("Civic blue", (0.018, 0.16, 0.52), 0.38)
    mats["Yellow"] = g.mat("Safety yellow", (0.95, 0.48, 0.015), 0.40)
    mats["Green"] = g.mat("Deep botanical leaf", (0.045, 0.22, 0.060), 0.82)
    mats["Leaf2"] = g.mat("Fresh botanical leaf", (0.12, 0.39, 0.10), 0.78)
    mats["Leaf3"] = g.mat("Olive botanical leaf", (0.23, 0.34, 0.10), 0.82)
    mats["Bark"] = g.noise(
        g.mat("Rough tree bark", (0.16, 0.075, 0.028), 0.96), 24, 0.24, 0.035
    )
    mats["Soil"] = g.mat("Dark potting soil", (0.045, 0.022, 0.009), 1.0)
    mats["Fabric"] = g.noise(
        g.mat("Woven upholstery", palette["fabric"], 0.88), 110, 0.11, 0.012
    )
    mats["WarmGlow"] = g.mat(
        "Warm luminaire diffuser", (1.0, 0.62, 0.24), 0.20, 0.0, 0.0, 4.5
    )
    mats["CoolGlow"] = g.mat(
        "Cool display diffuser", (0.52, 0.78, 1.0), 0.18, 0.0, 0.0, 3.0
    )
    mats["Water"] = g.mat("Clear blue water", (0.025, 0.20, 0.32), 0.08, 0.05, 0.52)
    # Geometry helpers refer to these semantic aliases when adding details
    # (for example vehicle lamps), while Blender materials retain their
    # descriptive datablock names for inspection in the delivered .blend.
    g.materials.update(mats)
    return mats


def build_shell(g: Geo, m: dict, style="flat", floor="wood") -> None:
    # Real thickness shell with a 3.4 m clear, permanently open portal.
    g.box("Structural slab", (0, 4.85, -0.16), (14.2, 10.2, 0.32), m["Concrete"], 0.02)
    floor_mat = m["LightWood"] if floor == "wood" else m["Stone"]
    if floor == "wood":
        for row in range(17):
            y = 0.30 + row * 0.57
            offset = 0.55 if row % 2 else 0
            for col in range(7):
                x = -6.6 + col * 2.2 + offset
                g.box(
                    f"Interior oak plank {row} {col}",
                    (x, y, 0.012),
                    (2.14, 0.54, 0.024),
                    floor_mat,
                    0.004,
                )
    else:
        for ix in range(14):
            for iy in range(10):
                g.box(
                    f"Interior stone tile {ix} {iy}",
                    (-6.5 + ix, 0.5 + iy, 0.012),
                    (0.985, 0.985, 0.024),
                    floor_mat,
                    0.003,
                )
    g.box(
        "Rear structural wall", (0, 9.90, 2.10), (14.2, 0.28, 4.20), m["Plaster"], 0.025
    )
    g.box(
        "West structural wall",
        (-7.0, 4.95, 2.10),
        (0.28, 10.2, 4.20),
        m["Plaster"],
        0.025,
    )
    g.box(
        "East structural wall",
        (7.0, 4.95, 2.10),
        (0.28, 10.2, 4.20),
        m["Plaster"],
        0.025,
    )
    g.box("Insulated ceiling", (0, 4.95, 4.22), (14.2, 10.2, 0.22), m["White"], 0.02)
    # Glazed facade with real openings rather than glass applied over a wall.
    for side in (-1, 1):
        g.box(
            f"Facade outer pier {side}",
            (side * 6.83, 0, 2.10),
            (0.34, 0.34, 4.20),
            m["Facade"],
            0.025,
        )
        g.box(
            f"Facade door pier {side}",
            (side * 1.82, 0, 1.70),
            (0.24, 0.34, 3.40),
            m["Facade"],
            0.022,
        )
        g.box(
            f"Facade sill {side}",
            (side * 4.33, 0, 0.32),
            (4.70, 0.34, 0.64),
            m["Facade"],
            0.025,
        )
        g.box(
            f"Facade window header {side}",
            (side * 4.33, 0, 3.73),
            (4.70, 0.34, 0.94),
            m["Facade"],
            0.025,
        )
        g.box(
            f"Facade glazing {side}",
            (side * 4.33, -0.03, 2.00),
            (4.46, 0.055, 2.72),
            m["Glass"],
            0.006,
        )
        for mullion in (-1.47, 0, 1.47):
            g.box(
                f"Window mullion {side} {mullion}",
                (side * 4.33 + mullion, -0.08, 2.00),
                (0.065, 0.10, 2.78),
                m["Metal"],
                0.008,
            )
        g.box(
            f"Window sill trim {side}",
            (side * 4.33, -0.10, 0.66),
            (4.62, 0.13, 0.10),
            m["Steel"],
            0.012,
        )
        g.box(
            f"Window head trim {side}",
            (side * 4.33, -0.10, 3.38),
            (4.62, 0.13, 0.10),
            m["Steel"],
            0.012,
        )
    g.box("Portal head", (0, 0, 3.72), (3.40, 0.34, 0.96), m["Facade"], 0.025)
    g.box(
        "Portal left jamb", (-1.70, -0.06, 1.58), (0.12, 0.24, 3.16), m["Metal"], 0.016
    )
    g.box(
        "Portal right jamb", (1.70, -0.06, 1.58), (0.12, 0.24, 3.16), m["Metal"], 0.016
    )
    g.box("Portal top jamb", (0, -0.06, 3.12), (3.52, 0.24, 0.12), m["Metal"], 0.016)
    g.box(
        "Flush stone threshold",
        (0, -0.02, 0.018),
        (3.30, 0.70, 0.036),
        m["Stone"],
        0.006,
    )
    # Distinct roof silhouettes.
    if style == "pitched":
        g.box(
            "Pitched roof west plane",
            (-3.5, 4.9, 4.72),
            (7.6, 10.8, 0.24),
            m["Metal"],
            0.025,
            (0, math.radians(-8), 0),
        )
        g.box(
            "Pitched roof east plane",
            (3.5, 4.9, 4.72),
            (7.6, 10.8, 0.24),
            m["Metal"],
            0.025,
            (0, math.radians(8), 0),
        )
    elif style == "industrial":
        for x in (-5.3, -2.7, -0.1, 2.5, 5.1):
            g.box(
                f"Sawtooth roof blade {x}",
                (x, 4.9, 4.65),
                (2.35, 10.6, 0.20),
                m["Metal"],
                0.018,
                (0, math.radians(-11), 0),
            )
    else:
        g.box("Flat roof cap", (0, 4.9, 4.45), (14.5, 10.5, 0.30), m["Metal"], 0.035)
        g.box("Front parapet", (0, -0.05, 4.75), (14.5, 0.34, 0.62), m["Facade"], 0.025)
    # Exterior paving, drainage and road edge.
    g.box(
        "Exterior pavement substrate",
        (0, -8.0, -0.12),
        (25.0, 16.0, 0.24),
        m["Concrete"],
        0.01,
    )
    for row in range(16):
        y = -0.48 - row * 0.96
        offset = 0.62 if row % 2 else 0
        for col in range(18):
            x = -11.4 + col * 1.30 + offset
            g.box(
                f"Exterior paver {row} {col}",
                (x, y, 0.014),
                (1.25, 0.91, 0.028),
                m["Stone"],
                0.004,
            )
    g.box("Street asphalt", (0, -17.2, -0.15), (28.0, 3.0, 0.14), m["Asphalt"], 0.008)
    for i in range(14):
        g.box(
            f"Curb block {i}",
            (-13 + i * 2.0, -15.68, -0.02),
            (1.92, 0.28, 0.18),
            m["Concrete"],
            0.018,
        )
    for x in (-9, -3, 3, 9):
        g.box(
            f"Storm drain {x}",
            (x, -15.55, 0.025),
            (1.0, 0.34, 0.035),
            m["Metal"],
            0.008,
        )
        for bar in range(10):
            g.box(
                f"Storm drain bar {x} {bar}",
                (x - 0.42 + bar * 0.094, -15.55, 0.052),
                (0.025, 0.30, 0.025),
                m["Steel"],
                0.003,
            )


def add_architectural_details(g: Geo, m: dict, canopy="slatted") -> None:
    # Baseboards, wall reveals, acoustic ceiling rails and entry canopy.
    g.box("Rear baseboard", (0, 9.72, 0.14), (13.7, 0.08, 0.28), m["Wood"], 0.012)
    for side in (-1, 1):
        g.box(
            f"Side baseboard {side}",
            (side * 6.82, 4.9, 0.14),
            (0.08, 9.5, 0.28),
            m["Wood"],
            0.012,
        )
        g.box(
            f"Facade side sconce back {side}",
            (side * 2.35, -0.20, 2.45),
            (0.22, 0.08, 0.48),
            m["Metal"],
            0.025,
        )
        g.box(
            f"Facade side sconce glow {side}",
            (side * 2.35, -0.25, 2.45),
            (0.13, 0.06, 0.30),
            m["WarmGlow"],
            0.02,
        )
    for x in (-5.2, -2.6, 0, 2.6, 5.2):
        g.box(
            f"Ceiling acoustic rail {x}",
            (x, 4.9, 4.02),
            (0.09, 9.5, 0.12),
            m["Metal"],
            0.01,
        )
    for row, y in enumerate((2.0, 5.0, 8.0)):
        for col, x in enumerate((-4.5, -1.5, 1.5, 4.5)):
            g.ceiling_panel(
                f"Ceiling luminaire {row} {col}",
                (x, y, 4.03),
                (1.15, 0.48, 0.10),
                m["Metal"],
                m["WarmGlow"],
                220,
            )
    # A layered identity feature gives the long bidirectional sightline a
    # designed focal point while staying entirely on the rear wall and outside
    # the audited walking corridor.
    g.box(
        "Rear identity panel frame",
        (0, 9.70, 2.30),
        (3.05, 0.10, 1.52),
        m["Metal"],
        0.022,
    )
    g.box(
        "Rear identity panel inset",
        (0, 9.63, 2.30),
        (2.80, 0.035, 1.28),
        m["Primary"],
        0.010,
    )
    for index, x in enumerate((-0.92, -0.46, 0, 0.46, 0.92)):
        g.box(
            f"Rear identity relief fin {index}",
            (x, 9.58, 2.30),
            (0.13, 0.055, 0.88 + 0.12 * (index % 3)),
            m["Secondary"],
            0.012,
            (0, 0, math.radians((index - 2) * 7)),
        )
    if canopy == "slatted":
        g.box(
            "Entrance canopy frame",
            (0, -1.35, 3.65),
            (8.8, 2.7, 0.16),
            m["Metal"],
            0.025,
        )
        for x in range(-40, 41, 5):
            g.box(
                f"Canopy timber slat {x}",
                (x / 10, -1.35, 3.54),
                (0.16, 2.45, 0.12),
                m["LightWood"],
                0.018,
            )
    elif canopy == "glass":
        g.box(
            "Glass entrance canopy",
            (0, -1.45, 3.65),
            (8.4, 2.9, 0.12),
            m["Glass"],
            0.012,
        )
        for x in (-4.0, -2.0, 0, 2.0, 4.0):
            g.box(
                f"Canopy steel rib {x}",
                (x, -1.45, 3.68),
                (0.08, 2.9, 0.13),
                m["Metal"],
                0.012,
            )
    else:
        g.box(
            "Solid entrance canopy",
            (0, -1.35, 3.72),
            (9.0, 2.8, 0.28),
            m["Facade"],
            0.045,
        )
        g.box(
            "Canopy fascia band",
            (0, -2.70, 3.70),
            (9.0, 0.15, 0.36),
            m["Primary"],
            0.018,
        )


def add_context(g: Geo, m: dict, trees=True) -> None:
    # Small-scale context only: two side masses, furniture and landscaping.
    for side in (-1, 1):
        x = side * 10.2
        g.box(
            f"Neighbor volume {side}",
            (x, -7.8, 2.6),
            (5.3, 7.2, 5.2),
            m["Concrete"],
            0.055,
        )
        g.box(
            f"Neighbor facade inset {side}",
            (x - side * 2.66, -7.8, 2.5),
            (0.08, 5.8, 4.2),
            m["Facade"],
            0.01,
        )
        for row in range(2):
            for col in range(2):
                g.box(
                    f"Neighbor window {side} {row} {col}",
                    (x - side * 2.72, -9.5 + col * 3.0, 1.55 + row * 1.9),
                    (0.05, 1.65, 1.25),
                    m["Glass"],
                    0.006,
                )
        # Detailed planter boxes outside the center aisle.
        g.box(
            f"Street planter {side}",
            (side * 5.8, -6.0, 0.42),
            (2.2, 1.1, 0.84),
            m["Concrete"],
            0.06,
        )
        g.box(
            f"Street planter soil {side}",
            (side * 5.8, -6.0, 0.84),
            (1.95, 0.85, 0.08),
            m["Soil"],
            0.02,
        )
        for j in range(5):
            g.sphere(
                f"Street planter shrub {side} {j}",
                (side * 5.8 - 0.75 + j * 0.38, -6.0, 1.05 + 0.10 * (j % 2)),
                (0.32, 0.28, 0.42),
                m["Leaf2"],
                2,
            )
        # Bench with slatted seat and back.
        for j in range(5):
            g.box(
                f"Street bench seat slat {side} {j}",
                (side * 4.5, -10.6 + j * 0.13, 0.54),
                (2.2, 0.10, 0.10),
                m["LightWood"],
                0.018,
            )
        for j in range(4):
            g.box(
                f"Street bench back slat {side} {j}",
                (side * 4.5, -10.30, 0.78 + j * 0.15),
                (2.2, 0.09, 0.10),
                m["LightWood"],
                0.018,
            )
        for sx in (-0.88, 0.88):
            g.box(
                f"Street bench leg {side} {sx}",
                (side * 4.5 + sx, -10.55, 0.28),
                (0.10, 0.55, 0.55),
                m["Metal"],
                0.018,
            )
    for x in (-7.5, 7.5):
        for y in (-3.5, -12.8):
            g.cylinder(
                f"Street lamp base {x} {y}", (x, y, 0.10), 0.20, 0.20, m["Metal"], 32
            )
            g.cylinder(
                f"Street lamp pole {x} {y}", (x, y, 1.85), 0.065, 3.5, m["Metal"], 24
            )
            g.box(
                f"Street lamp cap {x} {y}",
                (x, y, 3.58),
                (0.62, 0.62, 0.12),
                m["Metal"],
                0.035,
            )
            g.sphere(
                f"Street lamp globe {x} {y}",
                (x, y, 3.43),
                (0.28, 0.28, 0.32),
                m["WarmGlow"],
                2,
            )
    if trees:
        leaves = [m["Green"], m["Leaf2"], m["Leaf3"]]
        for x, y, height in (
            (-8.8, -3.3, 4.8),
            (8.7, -3.8, 5.2),
            (-8.6, -12.4, 5.5),
            (8.8, -12.7, 4.9),
        ):
            g.tree(f"Street tree {x} {y}", (x, y, 0), height, m["Bark"], leaves)


def add_world_and_lights(g: Geo, m: dict) -> bpy.types.Object:
    world = (
        bpy.data.worlds.new("Connect3 daylight world")
        if not bpy.data.worlds
        else bpy.data.worlds[0]
    )
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.20, 0.28, 0.39, 1.0)
    background.inputs["Strength"].default_value = 0.55
    bpy.ops.object.light_add(type="SUN", location=(8, -10, 14))
    sun = bpy.context.object
    sun.name = "Soft late afternoon sun"
    sun.rotation_euler = (math.radians(26), math.radians(-18), math.radians(-34))
    sun.data.energy = 2.4
    sun.data.angle = math.radians(9)
    for name, loc, target, energy, size, color in (
        ("Interior key", (-4, 4, 3.5), (0, 5, 1.0), 1000, 4.5, (1.0, 0.78, 0.58)),
        ("Interior fill", (4, 7, 3.4), (0, 5, 1.1), 850, 4.0, (0.72, 0.84, 1.0)),
        ("Portal bounce", (0, -2.0, 4.5), (0, 2.5, 1.0), 1250, 5.0, (0.72, 0.84, 1.0)),
        ("Exterior fill", (-6, -8, 8), (0, -6, 0.8), 1100, 7.0, (0.78, 0.88, 1.0)),
    ):
        bpy.ops.object.light_add(type="AREA", location=loc)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        light.rotation_euler = (
            (Vector(target) - light.location).to_track_quat("-Z", "Y").to_euler()
        )
    camera_data = bpy.data.cameras.new("Connect3Camera")
    camera = bpy.data.objects.new("Connect3Camera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.data.sensor_width = 36
    camera.data.lens = 30
    camera.data.clip_start = 0.05
    camera.data.clip_end = 200
    camera.data.dof.use_dof = False
    return camera


def audit_connection() -> dict:
    blockers = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH":
            continue
        corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        low = Vector(
            (
                min(v.x for v in corners),
                min(v.y for v in corners),
                min(v.z for v in corners),
            )
        )
        high = Vector(
            (
                max(v.x for v in corners),
                max(v.y for v in corners),
                max(v.z for v in corners),
            )
        )
        # Ignore flush floor/paving pieces; only waist-height and taller items
        # can obstruct the center route used by both traversal directions.
        if (
            low.x < 0.88
            and high.x > -0.88
            and low.y < 8.6
            and high.y > -12.2
            and low.z < 2.35
            and high.z > 0.18
        ):
            blockers.append(obj.name)
    return {
        "passed": not blockers,
        "route_x_half_width_m": 0.88,
        "route_y_bounds_m": [-12.2, 8.6],
        "door_clear_width_m": 3.40,
        "flush_threshold": True,
        "blockers": blockers,
    }

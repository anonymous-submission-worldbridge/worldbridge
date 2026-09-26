#!/usr/bin/env python3
"""Render the higher-detail ordinary residential/retail GLM connect2 scenes."""

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


import math
from pathlib import Path
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.render_glm_flash_connect as base


OUTPUT = base.BASELINES / "annotations/glm53_flash/connect2"
SCENES = (
    "apartment_living_room",
    "suburban_kitchen_dining",
    "townhouse_entry_lounge",
    "neighborhood_bakery",
    "corner_convenience_store",
    "small_clothing_boutique",
)


class DetailedSceneAPI(base.SceneAPI):
    """Primitive-only API with detailed semantic assemblies and procedural finishes."""

    def mat(self, name, color_rgb, metallic=0.0, roughness=0.5, emission=0.0):
        material_name = super().mat(name, color_rgb, metallic, roughness, emission)
        material = self.materials[material_name]
        nodes = material.node_tree.nodes
        links = material.node_tree.links
        bsdf = nodes.get("Principled BSDF")
        lowered = str(name).lower()
        if "glass" in lowered or float(emission) > 0.0:
            if "glass" in lowered and "Transmission Weight" in bsdf.inputs:
                bsdf.inputs["Transmission Weight"].default_value = 0.72
                bsdf.inputs["Roughness"].default_value = 0.12
                if "IOR" in bsdf.inputs:
                    bsdf.inputs["IOR"].default_value = 1.45
            return material_name

        # Subtle generated-coordinate texture makes large surfaces read as
        # plaster, timber, fabric or stone without external images.
        texcoord = nodes.new("ShaderNodeTexCoord")
        texcoord.name = "WB2_TextureCoordinates"
        noise = nodes.new("ShaderNodeTexNoise")
        noise.name = "WB2_MicroVariation"
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.name = "WB2_ColorVariation"
        bump = nodes.new("ShaderNodeBump")
        bump.name = "WB2_MicroBump"
        scale = (
            22.0
            if any(word in lowered for word in ("fabric", "cloth", "rug", "uphol"))
            else 5.0
        )
        if any(
            word in lowered for word in ("wood", "oak", "walnut", "timber", "birch")
        ):
            scale = 3.2
        noise.inputs["Scale"].default_value = scale
        noise.inputs["Detail"].default_value = 3.0
        noise.inputs["Roughness"].default_value = 0.62
        color = tuple(float(value) for value in color_rgb[:3])
        dark = tuple(max(0.0, channel * 0.82) for channel in color)
        light = tuple(min(1.0, channel * 1.10 + 0.015) for channel in color)
        ramp.color_ramp.elements[0].position = 0.28
        ramp.color_ramp.elements[0].color = (*dark, 1.0)
        ramp.color_ramp.elements[1].position = 0.76
        ramp.color_ramp.elements[1].color = (*light, 1.0)
        bump.inputs["Strength"].default_value = 0.055 if "wall" in lowered else 0.10
        bump.inputs["Distance"].default_value = 0.045
        links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
        if "Coat Weight" in bsdf.inputs and float(roughness) < 0.4:
            bsdf.inputs["Coat Weight"].default_value = 0.16
        return material_name

    def cylinder(self, name, location_xyz, radius, depth, material, vertices=16):
        obj = super().cylinder(name, location_xyz, radius, depth, material, vertices)
        lowered = str(name).lower()
        if "curtain" in lowered and "rod" in lowered:
            obj.rotation_euler[1] = math.radians(90)
        return obj

    def box(
        self, name, location_xyz, scale_xyz, material, bevel=0.04, *extra_materials
    ):
        # GLM occasionally expresses an obvious cabinet-like box with body,
        # front and handle materials. Preserve that intent as a detailed
        # cabinet assembly instead of dropping the extra material arguments.
        if isinstance(bevel, str):
            x, y, center_z = (float(value) for value in location_xyz)
            sx, sy, sz = (max(0.01, abs(float(value))) for value in scale_xyz)
            handle = extra_materials[0] if extra_materials else bevel
            self.cabinet(
                name, (x, y, center_z - sz / 2), (sx, sy, sz), material, bevel, handle
            )
            return None
        return super().box(name, location_xyz, scale_xyz, material, bevel)

    def rug(self, name, location_xyz, size_xy, material):
        coordinates = tuple(float(value) for value in location_xyz)
        if len(coordinates) == 2:
            coordinates = (*coordinates, 0.0)
        return super().rug(name, coordinates, size_xy, material)

    def cabinet(
        self,
        name,
        location_xyz,
        size_xyz,
        body_material,
        front_material,
        handle_material,
    ):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.18, abs(float(value))) for value in size_xyz)
        frame = min(0.08, sx * 0.05)
        self.box(
            name + "_carcass",
            (x, y + 0.03, z + sz / 2),
            (sx, sy, sz),
            body_material,
            0.025,
        )
        self.box(
            name + "_toe_kick",
            (x, y - sy / 2 - 0.012, z + 0.06),
            (sx * 0.92, 0.035, 0.12),
            handle_material,
            0.01,
        )
        doors = max(1, min(4, round(sx / 0.65)))
        door_width = sx / doors
        for index in range(doors):
            dx = x - sx / 2 + door_width * (index + 0.5)
            self.box(
                f"{name}_door_{index}",
                (dx, y - sy / 2 - 0.025, z + sz / 2),
                (door_width - frame, 0.045, sz - frame * 1.7),
                front_material,
                0.018,
            )
            handle_x = dx + door_width * (0.25 if index % 2 == 0 else -0.25)
            self.cylinder(
                f"{name}_handle_{index}",
                (handle_x, y - sy / 2 - 0.065, z + sz * 0.62),
                0.018,
                min(0.18, sz * 0.22),
                handle_material,
                24,
            )

    def counter(
        self,
        name,
        location_xyz,
        size_xyz,
        body_material,
        top_material,
        front_material,
        handle_material,
    ):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.25, abs(float(value))) for value in size_xyz)
        self.cabinet(
            name + "_base",
            (x, y, z),
            (sx, sy, max(0.2, sz - 0.07)),
            body_material,
            front_material,
            handle_material,
        )
        self.box(
            name + "_worktop",
            (x, y, z + sz - 0.035),
            (sx + 0.08, sy + 0.08, 0.07),
            top_material,
            0.035,
        )
        self.box(
            name + "_front_rail",
            (x, y - sy / 2 - 0.055, z + sz * 0.78),
            (sx * 0.90, 0.035, 0.055),
            handle_material,
            0.012,
        )

    def appliance(
        self,
        name,
        location_xyz,
        size_xyz,
        body_material,
        face_material,
        accent_material,
    ):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.20, abs(float(value))) for value in size_xyz)
        self.box(name + "_body", (x, y, z + sz / 2), (sx, sy, sz), body_material, 0.055)
        self.box(
            name + "_face",
            (x, y - sy / 2 - 0.018, z + sz * 0.49),
            (sx * 0.88, 0.04, sz * 0.78),
            face_material,
            0.025,
        )
        self.box(
            name + "_control",
            (x, y - sy / 2 - 0.045, z + sz * 0.88),
            (sx * 0.76, 0.035, sz * 0.10),
            accent_material,
            0.012,
        )
        self.cylinder(
            name + "_handle",
            (x, y - sy / 2 - 0.085, z + sz * 0.70),
            0.025,
            sx * 0.68,
            accent_material,
            32,
        )
        self.cylinder(
            name + "_dial_left",
            (x - sx * 0.22, y - sy / 2 - 0.075, z + sz * 0.88),
            0.035,
            0.025,
            accent_material,
            32,
        )
        self.cylinder(
            name + "_dial_right",
            (x + sx * 0.22, y - sy / 2 - 0.075, z + sz * 0.88),
            0.035,
            0.025,
            accent_material,
            32,
        )

    def window(self, name, location_xyz, size_xyz, frame_material, glass_material):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.15, abs(float(value))) for value in size_xyz)
        frame = min(0.11, min(sx, sz) * 0.10)
        self.box(
            name + "_glass",
            (x, y, z),
            (sx - frame * 1.7, sy, sz - frame * 1.7),
            glass_material,
            0.01,
        )
        self.box(
            name + "_top",
            (x, y, z + sz / 2),
            (sx + frame, sy + 0.05, frame),
            frame_material,
            0.02,
        )
        self.box(
            name + "_bottom",
            (x, y, z - sz / 2),
            (sx + frame, sy + 0.05, frame),
            frame_material,
            0.02,
        )
        self.box(
            name + "_left",
            (x - sx / 2, y, z),
            (frame, sy + 0.05, sz),
            frame_material,
            0.02,
        )
        self.box(
            name + "_right",
            (x + sx / 2, y, z),
            (frame, sy + 0.05, sz),
            frame_material,
            0.02,
        )
        self.box(
            name + "_mullion",
            (x, y - sy * 0.55, z),
            (frame * 0.65, sy * 0.35, sz - frame),
            frame_material,
            0.012,
        )

    def plant(self, name, location_xyz, height, pot_material, leaf_material):
        x, y, z = (float(value) for value in location_xyz)
        height = max(0.32, float(height))
        pot_h = min(0.38, height * 0.32)
        self.cylinder(
            name + "_pot", (x, y, z + pot_h / 2), pot_h * 0.40, pot_h, pot_material, 32
        )
        self.cylinder(
            name + "_soil", (x, y, z + pot_h), pot_h * 0.34, 0.025, "Harness_Soil", 32
        )
        stem_h = height - pot_h
        for index, (dx, dy, lean) in enumerate(
            (
                (-0.10, 0.00, 0.72),
                (0.10, 0.02, 0.82),
                (0.0, -0.08, 1.0),
                (-0.06, 0.08, 0.90),
                (0.13, -0.06, 0.66),
            )
        ):
            self.cylinder(
                f"{name}_stem_{index}",
                (x + dx * height, y + dy * height, z + pot_h + stem_h * lean / 2),
                0.012,
                stem_h * lean,
                "Harness_Stem",
                16,
            )
            self.sphere(
                f"{name}_leaf_{index}",
                (
                    x + dx * height * 1.5,
                    y + dy * height * 1.5,
                    z + pot_h + stem_h * lean,
                ),
                (height * 0.17, height * 0.09, height * 0.22),
                leaf_material,
                24,
            )

    def ceiling_light(
        self, name, location_xyz, radius, fixture_material, glow_material, energy=250
    ):
        x, y, z = (float(value) for value in location_xyz)
        radius = max(0.05, float(radius))
        self.cylinder(name + "_trim", (x, y, z), radius, 0.065, fixture_material, 32)
        self.cylinder(
            name + "_diffuser",
            (x, y, z - 0.045),
            radius * 0.76,
            0.035,
            glow_material,
            32,
        )
        bpy.ops.object.light_add(type="POINT", location=(x, y, z - 0.12))
        light = bpy.context.object
        light.name = name + "_light"
        light.data.energy = max(12.0, min(180.0, float(energy) * 0.36))
        light.data.color = (1.0, 0.82, 0.64)
        light.data.shadow_soft_size = max(0.25, radius * 4.0)
        light.data.use_shadow = False

    def display_unit(
        self,
        name,
        location_xyz,
        size_xyz,
        frame_material,
        product_material,
        accent_material,
    ):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.35, abs(float(value))) for value in size_xyz)
        self.box(
            name + "_back",
            (x, y + sy * 0.42, z + sz / 2),
            (sx, sy * 0.10, sz),
            frame_material,
            0.025,
        )
        self.box(
            name + "_plinth", (x, y, z + 0.09), (sx, sy, 0.18), frame_material, 0.035
        )
        levels = max(3, min(6, round(sz / 0.48)))
        columns = max(4, min(9, round(sx / 0.30)))
        for level in range(levels):
            shelf_z = z + 0.20 + level * (sz - 0.28) / levels
            self.box(
                f"{name}_shelf_{level}",
                (x, y, shelf_z),
                (sx, sy, 0.055),
                frame_material,
                0.018,
            )
            self.box(
                f"{name}_price_rail_{level}",
                (x, y - sy / 2 - 0.018, shelf_z + 0.045),
                (sx * 0.94, 0.035, 0.075),
                accent_material,
                0.01,
            )
            for column in range(columns):
                px = x - sx * 0.42 + column * sx * 0.84 / max(1, columns - 1)
                ph = (sz / levels) * (0.34 + 0.09 * ((level + column) % 3))
                self.box(
                    f"{name}_product_{level}_{column}",
                    (px, y - sy * 0.16, shelf_z + 0.03 + ph / 2),
                    (sx / columns * 0.62, sy * 0.42, ph),
                    product_material if (level + column) % 3 else accent_material,
                    0.02,
                )

    def clothes_rack(
        self,
        name,
        location_xyz,
        width,
        height,
        frame_material,
        garment_material,
        accent_material,
    ):
        coordinates = tuple(float(value) for value in location_xyz)
        if len(coordinates) == 2:
            coordinates = (*coordinates, 0.0)
        x, y, z = coordinates
        width, height = max(0.8, float(width)), max(1.2, float(height))
        self.cylinder(
            name + "_left",
            (x - width / 2, y, z + height / 2),
            0.035,
            height,
            frame_material,
            24,
        )
        self.cylinder(
            name + "_right",
            (x + width / 2, y, z + height / 2),
            0.035,
            height,
            frame_material,
            24,
        )
        rail = self.cylinder(
            name + "_rail", (x, y, z + height), 0.04, width, frame_material, 32
        )
        rail.rotation_euler[1] = math.radians(90)
        count = max(7, min(14, round(width / 0.18)))
        for index in range(count):
            gx = x - width * 0.43 + index * width * 0.86 / max(1, count - 1)
            material = garment_material if index % 3 else accent_material
            self.box(
                f"{name}_garment_{index}",
                (gx, y, z + height * 0.64),
                (
                    width / count * 0.72,
                    0.14 + 0.025 * (index % 2),
                    height * (0.54 + 0.05 * (index % 3)),
                ),
                material,
                0.035,
            )
            self.cylinder(
                f"{name}_hanger_{index}",
                (gx, y, z + height * 0.93),
                0.012,
                0.16,
                frame_material,
                16,
            )


def ensure_core(api: DetailedSceneAPI, scene_id: str) -> None:
    api.mat("Harness_OakFloor", (0.52, 0.34, 0.18), roughness=0.48)
    api.mat("Harness_WarmWall", (0.88, 0.85, 0.78), roughness=0.86)
    api.mat("Harness_Ceiling", (0.94, 0.93, 0.89), roughness=0.88)
    api.mat("Harness_DarkTrim", (0.075, 0.068, 0.060), metallic=0.15, roughness=0.33)
    api.mat("Harness_Paving", (0.43, 0.45, 0.43), roughness=0.90)
    api.mat("Harness_Stone", (0.55, 0.54, 0.49), roughness=0.82)
    api.mat("Harness_Glass", (0.48, 0.68, 0.75), roughness=0.10)
    api.mat("Harness_Glow", (1.0, 0.74, 0.43), roughness=0.24, emission=2.2)
    api.mat("Harness_Soil", (0.10, 0.055, 0.025), roughness=1.0)
    api.mat("Harness_Stem", (0.12, 0.25, 0.06), roughness=0.82)
    api.mat("Harness_Leaf", (0.12, 0.36, 0.09), roughness=0.76)
    api.mat("Harness_Baseboard", (0.16, 0.13, 0.10), roughness=0.42)
    api.mat("Harness_Joint", (0.12, 0.08, 0.045), roughness=0.62)
    api.mat("Harness_Outlet", (0.78, 0.77, 0.72), roughness=0.48)

    # Conventional room shell, kept open at the full-width entrance.
    api.box(
        "Harness_InteriorFloor",
        (0, -4.5, -0.09),
        (12.2, 9.2, 0.18),
        "Harness_OakFloor",
        0.015,
    )
    api.box(
        "Harness_Ceiling", (0, -4.5, 3.67), (12.2, 9.2, 0.14), "Harness_Ceiling", 0.015
    )
    api.box(
        "Harness_BackWall",
        (0, -9.0, 1.80),
        (12.2, 0.16, 3.65),
        "Harness_WarmWall",
        0.015,
    )
    api.box(
        "Harness_LeftWall",
        (-6.0, -4.5, 1.80),
        (0.16, 9.2, 3.65),
        "Harness_WarmWall",
        0.015,
    )
    api.box(
        "Harness_RightWall",
        (6.0, -4.5, 1.80),
        (0.16, 9.2, 3.65),
        "Harness_WarmWall",
        0.015,
    )
    api.box(
        "Harness_FacadeLeft",
        (-3.65, 0.0, 1.80),
        (4.90, 0.22, 3.65),
        "Harness_WarmWall",
        0.025,
    )
    api.box(
        "Harness_FacadeRight",
        (3.65, 0.0, 1.80),
        (4.90, 0.22, 3.65),
        "Harness_WarmWall",
        0.025,
    )
    api.box(
        "Harness_FacadeHeader",
        (0, 0.0, 3.26),
        (2.40, 0.22, 0.72),
        "Harness_WarmWall",
        0.025,
    )
    api.box(
        "Harness_DoorFrameLeft",
        (-1.16, -0.03, 1.45),
        (0.10, 0.28, 2.90),
        "Harness_DarkTrim",
        0.018,
    )
    api.box(
        "Harness_DoorFrameRight",
        (1.16, -0.03, 1.45),
        (0.10, 0.28, 2.90),
        "Harness_DarkTrim",
        0.018,
    )
    api.box(
        "Harness_DoorFrameTop",
        (0, -0.03, 2.88),
        (2.42, 0.28, 0.10),
        "Harness_DarkTrim",
        0.018,
    )
    api.box(
        "Harness_Threshold",
        (0, 0.0, 0.012),
        (2.18, 0.62, 0.024),
        "Harness_Stone",
        0.008,
    )
    api.box(
        "Harness_ExteriorGround",
        (0, 10.0, -0.12),
        (30.0, 20.0, 0.22),
        "Harness_Paving",
        0.008,
    )
    api.box(
        "Harness_SidelightLeft",
        (-1.55, -0.08, 1.46),
        (0.64, 0.055, 2.62),
        "Harness_Glass",
        0.008,
    )
    api.box(
        "Harness_SidelightRight",
        (1.55, -0.08, 1.46),
        (0.64, 0.055, 2.62),
        "Harness_Glass",
        0.008,
    )


def add_refinement_pass(api: DetailedSceneAPI, scene_id: str) -> None:
    # Fine interior construction details provide scale in every view.
    api.box(
        "Harness_BaseboardBack",
        (0, -8.86, 0.115),
        (11.72, 0.055, 0.23),
        "Harness_Baseboard",
        0.016,
    )
    api.box(
        "Harness_BaseboardLeft",
        (-5.86, -4.5, 0.115),
        (0.055, 8.72, 0.23),
        "Harness_Baseboard",
        0.016,
    )
    api.box(
        "Harness_BaseboardRight",
        (5.86, -4.5, 0.115),
        (0.055, 8.72, 0.23),
        "Harness_Baseboard",
        0.016,
    )
    api.box(
        "Harness_CorniceBack",
        (0, -8.84, 3.47),
        (11.72, 0.07, 0.10),
        "Harness_Baseboard",
        0.018,
    )
    api.box(
        "Harness_CorniceLeft",
        (-5.84, -4.5, 3.47),
        (0.07, 8.72, 0.10),
        "Harness_Baseboard",
        0.018,
    )
    api.box(
        "Harness_CorniceRight",
        (5.84, -4.5, 3.47),
        (0.07, 8.72, 0.10),
        "Harness_Baseboard",
        0.018,
    )
    for index, y in enumerate((-8.32, -7.22, -6.12, -5.02, -3.92, -2.82, -1.72, -0.62)):
        api.box(
            f"Harness_FloorJoint_{index}",
            (0, y, 0.008),
            (11.64, 0.014, 0.009),
            "Harness_Joint",
            0.002,
        )
    for index, x in enumerate((-4.65, -3.10, -1.55, 1.55, 3.10, 4.65)):
        api.box(
            f"Harness_FloorJointLong_{index}",
            (x, -4.52, 0.009),
            (0.012, 8.63, 0.010),
            "Harness_Joint",
            0.002,
        )
    for side, x in (("left", -5.84), ("right", 5.84)):
        for index, y in enumerate((-7.4, -4.7, -2.0)):
            api.box(
                f"Harness_Outlet_{side}_{index}",
                (x, y, 0.38),
                (0.035, 0.16, 0.12),
                "Harness_Outlet",
                0.012,
            )
            api.box(
                f"Harness_OutletSlot_{side}_{index}",
                (x * 1.0005, y, 0.38),
                (0.020, 0.055, 0.018),
                "Harness_DarkTrim",
                0.004,
            )
    for row, y in enumerate((-2.0, -4.7, -7.4)):
        for column, x in enumerate((-3.9, -1.35, 1.35, 3.9)):
            api.ceiling_light(
                f"Harness_Downlight_{row}_{column}",
                (x, y, 3.53),
                0.095,
                "Harness_DarkTrim",
                "Harness_Glow",
                135,
            )
    for index, y in enumerate((1.4, 2.8, 4.2, 5.6, 7.0, 8.4, 9.8, 11.2, 12.6)):
        api.box(
            f"Harness_PaverJoint_{index}",
            (0, y, 0.006),
            (12.0, 0.018, 0.009),
            "Harness_Stone",
            0.002,
        )
    for side, x in (("left", -2.30), ("right", 2.30)):
        api.box(
            f"Harness_EntrySconce_{side}",
            (x, 0.14, 2.32),
            (0.19, 0.10, 0.34),
            "Harness_DarkTrim",
            0.025,
        )
        api.sphere(
            f"Harness_EntryGlow_{side}",
            (x, 0.22, 2.32),
            (0.10, 0.08, 0.15),
            "Harness_Glow",
            24,
        )

    # A few scene-specific architectural cues are deterministic; semantic
    # furnishing and layout still come from the GLM-generated blueprint.
    if scene_id == "apartment_living_room":
        api.box(
            "Harness_CurtainRail",
            (0, -0.26, 3.12),
            (4.65, 0.055, 0.055),
            "Harness_DarkTrim",
            0.012,
        )
        for x in (-2.12, 2.12):
            api.box(
                f"Harness_Curtain_{x}",
                (x, -0.30, 1.62),
                (0.38, 0.08, 2.82),
                "Harness_WarmWall",
                0.07,
            )
    elif scene_id == "suburban_kitchen_dining":
        for row in range(4):
            api.box(
                f"Harness_BacksplashLine_{row}",
                (0, -8.80, 1.10 + row * 0.22),
                (7.7, 0.018, 0.012),
                "Harness_Joint",
                0.002,
            )
    elif scene_id == "townhouse_entry_lounge":
        for index, z in enumerate(
            (0.26, 0.50, 0.74, 0.98, 1.22, 1.46, 1.70, 1.94, 2.18)
        ):
            api.box(
                f"Harness_StairTread_{index}",
                (-4.85, -8.3 + index * 0.27, z),
                (1.65, 0.48, 0.16),
                "Harness_OakFloor",
                0.02,
            )
    else:
        api.box(
            "Harness_RetailTrackLeft",
            (-2.65, -4.7, 3.46),
            (0.08, 7.2, 0.08),
            "Harness_DarkTrim",
            0.012,
        )
        api.box(
            "Harness_RetailTrackRight",
            (2.65, -4.7, 3.46),
            (0.08, 7.2, 0.08),
            "Harness_DarkTrim",
            0.012,
        )


def enforce_open_connection() -> dict[str, object]:
    """Remove only geometry that seals the portal; preserve furniture assemblies."""
    removed = []
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH" or obj.name.startswith("Harness_"):
            continue
        low, high = base.world_bbox(obj)
        blocks_door = (
            low.x < 1.08
            and high.x > -1.08
            and low.y < 0.20
            and high.y > -0.20
            and low.z < 2.70
            and high.z > 0.14
        )
        if blocks_door:
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return {"removed_door_blockers": removed, "moved_corridor_blockers": []}


def add_camera_and_lighting(scene_id: str):
    world = (
        bpy.data.worlds.new("Connect2World")
        if not bpy.data.worlds
        else bpy.data.worlds[0]
    )
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.27, 0.35, 0.46, 1.0)
    background.inputs["Strength"].default_value = 0.30

    bpy.ops.object.light_add(type="SUN", location=(6, -5, 13))
    sun = bpy.context.object
    sun.name = "DaylightSun"
    sun.rotation_euler = (math.radians(28), math.radians(-16), math.radians(32))
    sun.data.energy = 1.35
    sun.data.angle = math.radians(10)

    lights = (
        (
            "InteriorKey",
            (-3.6, -4.0, 2.95),
            410,
            4.0,
            (1.0, 0.82, 0.68),
            (0.0, -5.2, 1.0),
        ),
        (
            "InteriorFill",
            (3.6, -5.8, 2.85),
            360,
            3.8,
            (0.78, 0.88, 1.0),
            (0.0, -5.0, 1.0),
        ),
        (
            "InteriorRear",
            (0.0, -8.0, 2.85),
            280,
            3.0,
            (1.0, 0.86, 0.72),
            (0.0, -5.0, 1.0),
        ),
        ("DoorBounce", (0.0, 1.8, 3.7), 470, 4.8, (0.78, 0.88, 1.0), (0.0, -2.2, 1.1)),
        (
            "ExteriorFill",
            (-5.5, 9.0, 8.5),
            520,
            7.0,
            (0.84, 0.91, 1.0),
            (0.0, 7.0, 0.8),
        ),
    )
    for name, location, energy, size, color, target in lights:
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        light.rotation_euler = (
            (Vector(target) - light.location).to_track_quat("-Z", "Y").to_euler()
        )

    camera_data = bpy.data.cameras.new("ConnectedCamera")
    camera = bpy.data.objects.new("ConnectedCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.data.lens = 30
    camera.data.sensor_width = 36
    camera.data.dof.use_dof = False
    bpy.context.scene.view_settings.look = "AgX - Medium High Contrast"
    bpy.context.scene.view_settings.exposure = -0.12
    return camera


def render_stills(scene_root: Path, camera) -> list[dict[str, object]]:
    image_root = scene_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    inside_far = (0.0, -8.25, 1.72)
    if scene_root.name == "neighborhood_bakery":
        # The rear-center deck oven occupies the generic camera point. This
        # offset remains a long diagonal view and crosses the same doorway.
        inside_far = (1.25, -7.55, 1.72)
    views = (
        ("indoor_overview", (0.0, -1.20, 2.22), (0.0, -6.15, 1.15), 25),
        ("indoor_detail", (-4.75, -6.70, 1.72), (1.75, -5.00, 1.05), 36),
        ("indoor_entry_wide", (4.85, -7.65, 2.42), (0.0, -0.10, 1.38), 25),
        ("inside_to_outside_far", inside_far, (0.0, 6.2, 1.22), 28),
        ("inside_to_outside_mid", (-0.65, -5.55, 1.67), (0.15, 6.8, 1.20), 30),
        ("inside_to_outside_left", (-4.60, -6.65, 1.86), (0.45, 4.8, 1.18), 29),
        ("inside_to_outside_right", (4.60, -6.65, 1.86), (-0.45, 4.8, 1.18), 29),
        ("inside_to_outside_high", (0.0, -8.0, 3.12), (0.0, 5.8, 1.08), 31),
        ("outdoor_overview", (8.4, 17.0, 6.4), (0.0, 6.4, 1.0), 30),
        ("outdoor_detail", (-7.6, 8.8, 1.75), (0.8, 4.5, 1.02), 37),
        ("outdoor_entry_wide", (-5.8, 12.8, 2.70), (0.0, 0.05, 1.42), 27),
        ("outside_to_inside_far", (0.0, 17.2, 2.18), (0.0, -5.5, 1.20), 31),
        ("outside_to_inside_mid", (0.70, 9.4, 1.72), (-0.10, -5.2, 1.18), 30),
        ("outside_to_inside_left", (-5.4, 13.4, 3.4), (0.35, -4.3, 1.16), 30),
        ("outside_to_inside_right", (5.4, 13.4, 3.4), (-0.35, -4.3, 1.16), 30),
        ("outside_to_inside_high", (0.0, 16.0, 6.2), (0.0, -3.8, 1.02), 34),
    )
    if tuple(role for role, *_ in views) != base.IMAGE_ROLES:
        raise RuntimeError("internal still-role ordering mismatch")
    base.configure_render(*base.STILL_SIZE, samples=48)
    records = []
    for role, location, target, lens in views:
        base.look_at(camera, location, target, lens)
        destination = image_root / f"{role}.png"
        bpy.context.scene.render.filepath = str(destination)
        bpy.context.scene.frame_set(1)
        bpy.ops.render.render(write_still=True)
        if not destination.is_file() or destination.stat().st_size < 20_000:
            raise RuntimeError(f"invalid still render: {destination}")
        records.append(
            {
                "role": role,
                "path": str(destination.relative_to(scene_root)),
                "width": base.STILL_SIZE[0],
                "height": base.STILL_SIZE[1],
                "bytes": destination.stat().st_size,
                "sha256": base.sha256(destination),
                "camera_location": list(location),
                "camera_target": list(target),
                "lens_mm": lens,
            }
        )
        print(f"GLM53_CONNECT2_IMAGE scene={scene_root.name} role={role}", flush=True)
    return records


base.DEFAULT_OUTPUT = OUTPUT
base.SCENE_IDS = SCENES
base.SceneAPI = DetailedSceneAPI
base.ensure_core = ensure_core
base.add_refinement_pass = add_refinement_pass
base.enforce_open_connection = enforce_open_connection
base.add_camera_and_lighting = add_camera_and_lighting
base.render_stills = render_stills


if __name__ == "__main__":
    raise SystemExit(base.main())

#!/usr/bin/env python3
"""Build and render one GLM-5.3 Flash connected scene inside Blender."""

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


import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import time

import bpy
from mathutils import Vector


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_OUTPUT = BASELINES / "annotations/glm53_flash/connect"
SCENE_IDS = (
    "courtyard_cafe",
    "garden_villa",
    "bookshop_arcade",
    "coastal_bungalow",
    "mountain_lodge",
    "gallery_plaza",
)
STILL_SIZE = (1280, 720)
VIDEO_SIZE = (960, 540)
FPS = 24
VIDEO_FRAMES = 120
IMAGE_ROLES = (
    "indoor_overview",
    "indoor_detail",
    "indoor_entry_wide",
    "inside_to_outside_far",
    "inside_to_outside_mid",
    "inside_to_outside_left",
    "inside_to_outside_right",
    "inside_to_outside_high",
    "outdoor_overview",
    "outdoor_detail",
    "outdoor_entry_wide",
    "outside_to_inside_far",
    "outside_to_inside_mid",
    "outside_to_inside_left",
    "outside_to_inside_right",
    "outside_to_inside_high",
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def confined(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


class SceneAPI:
    def __init__(self) -> None:
        self.materials: dict[str, bpy.types.Material] = {}
        self.created: list[bpy.types.Object] = []

    def mat(self, name, color_rgb, metallic=0.0, roughness=0.5, emission=0.0):
        safe_name = str(name)
        color = tuple(float(value) for value in color_rgb[:3])
        material = bpy.data.materials.get(safe_name) or bpy.data.materials.new(
            safe_name
        )
        material.diffuse_color = (*color, 1.0)
        material.use_nodes = True
        node = material.node_tree.nodes.get("Principled BSDF")
        node.inputs["Base Color"].default_value = (*color, 1.0)
        node.inputs["Metallic"].default_value = max(0.0, min(1.0, float(metallic)))
        node.inputs["Roughness"].default_value = max(0.05, min(1.0, float(roughness)))
        if "glass" in safe_name.lower() and "Transmission Weight" in node.inputs:
            node.inputs["Transmission Weight"].default_value = 0.32
        if float(emission) > 0.0:
            if "Emission Color" in node.inputs:
                node.inputs["Emission Color"].default_value = (*color, 1.0)
                node.inputs["Emission Strength"].default_value = float(emission)
            elif "Emission" in node.inputs:
                node.inputs["Emission"].default_value = (*color, 1.0)
                node.inputs["Emission Strength"].default_value = float(emission)
        self.materials[safe_name] = material
        return safe_name

    def _material(self, material):
        if isinstance(material, bpy.types.Material):
            return material
        name = str(material)
        if name not in self.materials:
            self.mat(name, (0.5, 0.5, 0.5))
        return self.materials[name]

    def _finish(self, obj, name, material, bevel=0.0):
        obj.name = str(name)
        if obj.data and hasattr(obj.data, "materials"):
            obj.data.materials.append(self._material(material))
        if bevel and obj.type == "MESH":
            modifier = obj.modifiers.new("Soft edges", "BEVEL")
            modifier.width = min(float(bevel), 0.25)
            modifier.segments = 3
        self.created.append(obj)
        return obj

    def box(self, name, location_xyz, scale_xyz, material, bevel=0.04):
        dimensions = [max(0.01, abs(float(value))) for value in scale_xyz]
        bpy.ops.mesh.primitive_cube_add(
            location=tuple(float(value) for value in location_xyz)
        )
        obj = bpy.context.object
        obj.dimensions = dimensions
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        return self._finish(obj, name, material, bevel)

    def cylinder(self, name, location_xyz, radius, depth, material, vertices=16):
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=max(24, min(64, int(vertices))),
            radius=max(0.01, abs(float(radius))),
            depth=max(0.01, abs(float(depth))),
            location=tuple(float(value) for value in location_xyz),
        )
        obj = bpy.context.object
        lowered = str(name).lower()
        if "wheel" in lowered or "rail" in lowered:
            obj.rotation_euler[1] = math.radians(90)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        return self._finish(obj, name, material, 0.025)

    def sphere(self, name, location_xyz, scale_xyz, material, segments=20):
        bpy.ops.mesh.primitive_ico_sphere_add(
            subdivisions=3,
            radius=1.0,
            location=tuple(float(value) for value in location_xyz),
        )
        obj = bpy.context.object
        obj.scale = tuple(max(0.01, abs(float(value))) for value in scale_xyz)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        return self._finish(obj, name, material, 0.0)

    def arch(self, name, location_xyz, width, height, depth, material):
        x, y, z = (float(value) for value in location_xyz)
        width, height, depth = float(width), float(height), float(depth)
        post = max(0.14, width * 0.12)
        self.box(
            name + "_left",
            (x - width / 2 + post / 2, y, z + height / 2),
            (post, depth, height),
            material,
        )
        self.box(
            name + "_right",
            (x + width / 2 - post / 2, y, z + height / 2),
            (post, depth, height),
            material,
        )
        self.box(
            name + "_top", (x, y, z + height - post / 2), (width, depth, post), material
        )

    def table(self, name, location_xyz, size_xyz, top_material, leg_material):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.15, abs(float(value))) for value in size_xyz)
        top_t = min(0.12, sz * 0.2)
        self.box(
            name + "_top",
            (x, y, z + sz - top_t / 2),
            (sx, sy, top_t),
            top_material,
            0.05,
        )
        self.box(
            name + "_apron_front",
            (x, y - sy * 0.40, z + sz - top_t - 0.10),
            (sx * 0.82, 0.06, 0.18),
            leg_material,
            0.025,
        )
        self.box(
            name + "_apron_back",
            (x, y + sy * 0.40, z + sz - top_t - 0.10),
            (sx * 0.82, 0.06, 0.18),
            leg_material,
            0.025,
        )
        for ix in (-1, 1):
            for iy in (-1, 1):
                self.box(
                    f"{name}_leg_{ix}_{iy}",
                    (x + ix * sx * 0.39, y + iy * sy * 0.36, z + (sz - top_t) / 2),
                    (0.09, 0.09, sz - top_t),
                    leg_material,
                    0.02,
                )

    def chair(self, name, location_xyz, yaw_degrees, material, accent_material):
        x, y, z = (float(value) for value in location_xyz)
        yaw = math.radians(float(yaw_degrees))
        parent = bpy.data.objects.new(name + "_group", None)
        bpy.context.collection.objects.link(parent)
        parent.location = (x, y, z)
        parent.rotation_euler[2] = yaw
        parts = [
            ("seat", (0, 0, 0.48), (0.55, 0.55, 0.11), accent_material),
            ("back_top", (0, 0.245, 1.15), (0.55, 0.10, 0.16), material),
            ("back_left", (-0.22, 0.245, 0.87), (0.07, 0.08, 0.48), material),
            ("back_right", (0.22, 0.245, 0.87), (0.07, 0.08, 0.48), material),
            ("back_slat", (0, 0.245, 0.88), (0.09, 0.07, 0.42), accent_material),
        ]
        for ix in (-1, 1):
            for iy in (-1, 1):
                parts.append(
                    (
                        f"leg_{ix}_{iy}",
                        (ix * 0.21, iy * 0.20, 0.23),
                        (0.07, 0.07, 0.46),
                        material,
                    )
                )
        for suffix, location, dimensions, mat in parts:
            obj = self.box(name + "_" + suffix, location, dimensions, mat, 0.025)
            obj.parent = parent
        for ix in (-1, 1):
            rail = self.box(
                name + f"_side_rail_{ix}",
                (ix * 0.21, 0, 0.30),
                (0.045, 0.40, 0.05),
                material,
                0.015,
            )
            rail.parent = parent
        self.created.append(parent)

    def sofa(
        self,
        name,
        location_xyz,
        yaw_degrees,
        size_xyz=None,
        material=None,
        accent_material=None,
    ):
        # GLM occasionally groups yaw and dimensions into one tuple.  Preserve
        # the generated source verbatim while accepting that unambiguous form.
        if (
            accent_material is None
            and isinstance(yaw_degrees, (tuple, list))
            and len(yaw_degrees) == 2
        ):
            accent_material = material
            material = size_xyz
            yaw_degrees, size_xyz = yaw_degrees
        # Another unambiguous omission is (location, dimensions, material,
        # frame_material, accent_material), where only yaw is absent.
        if (
            isinstance(yaw_degrees, (tuple, list))
            and len(yaw_degrees) == 3
            and isinstance(size_xyz, str)
        ):
            dimensions = yaw_degrees
            yaw_degrees = 0.0
            size_xyz, material = dimensions, size_xyz
        if size_xyz is None or material is None or accent_material is None:
            raise ValueError(f"invalid sofa arguments for {name}")
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.3, abs(float(value))) for value in size_xyz)
        parent = bpy.data.objects.new(name + "_group", None)
        bpy.context.collection.objects.link(parent)
        parent.location = (x, y, z)
        parent.rotation_euler[2] = math.radians(float(yaw_degrees))
        pieces = [
            ("base", (0, 0, sz * 0.28), (sx, sy, sz * 0.25), material),
            ("back", (0, sy * 0.38, sz * 0.78), (sx, sy * 0.20, sz * 0.70), material),
            ("arm_l", (-sx * 0.46, 0, sz * 0.58), (sx * 0.10, sy, sz * 0.55), material),
            ("arm_r", (sx * 0.46, 0, sz * 0.58), (sx * 0.10, sy, sz * 0.55), material),
        ]
        cushion_count = max(2, min(4, round(sx / 0.72)))
        cushion_width = sx * 0.80 / cushion_count
        for index in range(cushion_count):
            cx = -sx * 0.40 + cushion_width * (index + 0.5)
            pieces.append(
                (
                    f"seat_cushion_{index}",
                    (cx, -sy * 0.05, sz * 0.53),
                    (cushion_width * 0.92, sy * 0.70, sz * 0.20),
                    accent_material,
                )
            )
            pieces.append(
                (
                    f"back_cushion_{index}",
                    (cx, sy * 0.27, sz * 0.80),
                    (cushion_width * 0.90, sy * 0.16, sz * 0.48),
                    accent_material,
                )
            )
        for index, foot_x in enumerate((-sx * 0.40, sx * 0.40)):
            pieces.append(
                (
                    f"front_foot_{index}",
                    (foot_x, -sy * 0.35, sz * 0.10),
                    (0.10, 0.10, sz * 0.20),
                    material,
                )
            )
        for suffix, location, dimensions, mat in pieces:
            obj = self.box(name + "_" + suffix, location, dimensions, mat, 0.08)
            obj.parent = parent
        self.created.append(parent)

    def shelf(self, name, location_xyz, size_xyz, frame_material, item_material):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.3, abs(float(value))) for value in size_xyz)
        thickness = min(0.12, sx * 0.06)
        self.box(
            name + "_side_l",
            (x - sx / 2, y, z + sz / 2),
            (thickness, sy, sz),
            frame_material,
        )
        self.box(
            name + "_side_r",
            (x + sx / 2, y, z + sz / 2),
            (thickness, sy, sz),
            frame_material,
        )
        levels = max(3, min(6, int(sz / 0.55)))
        for level in range(levels + 1):
            shelf_z = z + level * sz / levels
            self.box(
                f"{name}_shelf_{level}",
                (x, y, shelf_z),
                (sx, sy, thickness),
                frame_material,
            )
        for level in range(levels):
            for index in range(6):
                width = sx * (0.065 + 0.012 * ((level + index) % 3))
                height = sz / levels * (0.55 + 0.07 * ((2 * level + index) % 4))
                item_x = x - sx * 0.38 + index * sx * 0.15
                item_z = z + level * sz / levels + thickness / 2 + height / 2
                item = self.box(
                    f"{name}_item_{level}_{index}",
                    (item_x, y - sy * 0.29, item_z),
                    (width, sy * 0.38, height),
                    item_material,
                    0.012,
                )
                item.rotation_euler[1] = math.radians(
                    (-4, 0, 3, -2)[(level + index) % 4]
                )

    def tree(
        self,
        name,
        location_xyz,
        trunk_height,
        crown_radius,
        trunk_material,
        leaf_material,
    ):
        x, y, z = (float(value) for value in location_xyz)
        height = max(1.2, float(trunk_height))
        radius = max(0.4, float(crown_radius))
        self.cylinder(
            name + "_trunk",
            (x, y, z + height / 2),
            radius * 0.13,
            height,
            trunk_material,
            32,
        )
        for index, offset in enumerate(
            (
                (0, 0, 0.05),
                (-0.50, 0.08, -0.12),
                (0.48, 0.14, -0.07),
                (0.08, -0.38, 0.20),
                (-0.26, -0.34, 0.12),
                (0.28, 0.39, 0.16),
                (0.02, 0.12, 0.44),
            )
        ):
            self.sphere(
                f"{name}_crown_{index}",
                (
                    x + offset[0] * radius,
                    y + offset[1] * radius,
                    z + height + radius * (0.42 + offset[2]),
                ),
                (radius, radius * 0.82, radius * 0.88),
                leaf_material,
                32,
            )

    def lamp(self, name, location_xyz, height, pole_material, light_material):
        x, y, z = (float(value) for value in location_xyz)
        height = max(1.2, float(height))
        self.cylinder(name + "_base", (x, y, z + 0.08), 0.16, 0.16, pole_material, 32)
        self.cylinder(
            name + "_pole", (x, y, z + height / 2), 0.055, height, pole_material, 32
        )
        self.cylinder(
            name + "_cap", (x, y, z + height - 0.10), 0.25, 0.08, pole_material, 32
        )
        self.sphere(
            name + "_globe", (x, y, z + height), (0.20, 0.20, 0.20), light_material, 32
        )

    def art(self, name, location_xyz, scale_xyz, material, frame_material):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.02, abs(float(value))) for value in scale_xyz)
        self.box(
            name + "_frame",
            (x, y, z),
            (sx + 0.14, sy + 0.06, sz + 0.14),
            frame_material,
            0.02,
        )
        self.box(name + "_panel", (x, y - sy * 0.55, z), (sx, sy, sz), material, 0.01)

    def rug(self, name, location_xyz, size_xy, material):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy = (max(0.1, abs(float(value))) for value in size_xy)
        self.box(name, (x, y, z + 0.025), (sx, sy, 0.05), material, 0.03)
        border = min(0.08, min(sx, sy) * 0.08)
        self.box(
            name + "_border_front",
            (x, y - sy / 2 + border / 2, z + 0.053),
            (sx * 0.96, border, 0.012),
            material,
            0.01,
        )
        self.box(
            name + "_border_back",
            (x, y + sy / 2 - border / 2, z + 0.053),
            (sx * 0.96, border, 0.012),
            material,
            0.01,
        )
        self.box(
            name + "_border_left",
            (x - sx / 2 + border / 2, y, z + 0.053),
            (border, sy * 0.82, 0.012),
            material,
            0.01,
        )
        self.box(
            name + "_border_right",
            (x + sx / 2 - border / 2, y, z + 0.053),
            (border, sy * 0.82, 0.012),
            material,
            0.01,
        )

    def road(self, name, location_xyz, size_xyz, road_material, line_material):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(0.02, abs(float(value))) for value in size_xyz)
        self.box(name + "_surface", (x, y, z), (sx, sy, sz), road_material, 0.01)
        if sx >= sy:
            for ix in range(-4, 5, 2):
                self.box(
                    f"{name}_line_{ix}",
                    (x + ix * sx / 10, y, z + sz / 2 + 0.012),
                    (sx / 12, 0.08, 0.025),
                    line_material,
                    0.005,
                )
        else:
            for iy in range(-4, 5, 2):
                self.box(
                    f"{name}_line_{iy}",
                    (x, y + iy * sy / 10, z + sz / 2 + 0.012),
                    (0.08, sy / 12, 0.025),
                    line_material,
                    0.005,
                )


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for data in (bpy.data.meshes, bpy.data.curves, bpy.data.cameras, bpy.data.lights):
        for block in list(data):
            if block.users == 0:
                data.remove(block)


def ensure_core(api: SceneAPI, scene_id: str) -> None:
    api.mat("Harness_InteriorFloor", (0.30, 0.21, 0.14), roughness=0.56)
    api.mat("Harness_Wall", (0.82, 0.77, 0.67), roughness=0.82)
    api.mat("Harness_Trim", (0.12, 0.10, 0.08), metallic=0.15, roughness=0.36)
    api.mat("Harness_ExteriorGround", (0.24, 0.28, 0.25), roughness=0.92)
    api.mat("Harness_Stone", (0.40, 0.42, 0.39), roughness=0.86)
    api.mat("Harness_Glass", (0.30, 0.55, 0.64), metallic=0.05, roughness=0.18)
    api.mat("Harness_WarmLight", (1.0, 0.55, 0.20), roughness=0.3, emission=3.0)
    # Fixed architecture guarantees a real room and a real open portal.  It is
    # deliberately neutral; GLM-generated code supplies semantic contents.
    api.box(
        "Harness_InteriorFloor",
        (0, -4.5, -0.10),
        (12.2, 9.2, 0.20),
        "Harness_InteriorFloor",
        0.02,
    )
    api.box("Harness_Ceiling", (0, -4.5, 3.65), (12.2, 9.2, 0.16), "Harness_Wall", 0.02)
    api.box(
        "Harness_BackWall", (0, -9.0, 1.78), (12.2, 0.18, 3.65), "Harness_Wall", 0.02
    )
    api.box(
        "Harness_LeftWall", (-6.0, -4.5, 1.78), (0.18, 9.2, 3.65), "Harness_Wall", 0.02
    )
    api.box(
        "Harness_RightWall", (6.0, -4.5, 1.78), (0.18, 9.2, 3.65), "Harness_Wall", 0.02
    )
    api.box(
        "Harness_FacadeLeft",
        (-3.65, 0.0, 1.78),
        (4.9, 0.24, 3.65),
        "Harness_Wall",
        0.03,
    )
    api.box(
        "Harness_FacadeRight",
        (3.65, 0.0, 1.78),
        (4.9, 0.24, 3.65),
        "Harness_Wall",
        0.03,
    )
    api.box(
        "Harness_FacadeHeader", (0, 0.0, 3.24), (2.4, 0.24, 0.72), "Harness_Wall", 0.03
    )
    api.box(
        "Harness_DoorFrameLeft",
        (-1.16, -0.03, 1.46),
        (0.10, 0.30, 2.92),
        "Harness_Trim",
        0.02,
    )
    api.box(
        "Harness_DoorFrameRight",
        (1.16, -0.03, 1.46),
        (0.10, 0.30, 2.92),
        "Harness_Trim",
        0.02,
    )
    api.box(
        "Harness_DoorFrameTop",
        (0, -0.03, 2.88),
        (2.42, 0.30, 0.10),
        "Harness_Trim",
        0.02,
    )
    api.box(
        "Harness_ExteriorGround",
        (0, 10.0, -0.13),
        (30, 20, 0.24),
        "Harness_ExteriorGround",
        0.01,
    )
    api.box(
        "Harness_Threshold", (0, 0.0, 0.015), (2.18, 0.70, 0.03), "Harness_Stone", 0.01
    )
    # A shallow canopy and transparent side lights frame the connection while
    # leaving the full walking aperture open.
    api.box("Harness_Canopy", (0, 0.75, 3.10), (4.4, 1.65, 0.16), "Harness_Trim", 0.04)
    api.box(
        "Harness_SidelightLeft",
        (-1.55, -0.08, 1.45),
        (0.65, 0.06, 2.65),
        "Harness_Glass",
        0.01,
    )
    api.box(
        "Harness_SidelightRight",
        (1.55, -0.08, 1.45),
        (0.65, 0.06, 2.65),
        "Harness_Glass",
        0.01,
    )
    for ix in (-4.8, -2.8, 2.8, 4.8):
        api.cylinder(
            f"Harness_CeilingLamp_{ix}",
            (ix, -4.5, 3.47),
            0.13,
            0.18,
            "Harness_WarmLight",
            20,
        )


def add_refinement_pass(api: SceneAPI, scene_id: str) -> None:
    """Add neutral finish details without changing GLM's scene semantics."""
    api.mat("Harness_Baseboard", (0.17, 0.13, 0.10), metallic=0.08, roughness=0.38)
    api.mat("Harness_Inlay", (0.08, 0.065, 0.05), metallic=0.04, roughness=0.44)
    api.mat("Harness_Brass", (0.52, 0.32, 0.10), metallic=0.76, roughness=0.25)
    api.mat("Harness_RecessedLight", (1.0, 0.82, 0.58), roughness=0.22, emission=4.5)
    api.mat("Harness_PaverLine", (0.52, 0.52, 0.48), roughness=0.92)

    # Baseboards, cornices and wall battens make the room read as finished
    # architecture instead of a handful of large primitive planes.
    api.box(
        "Harness_BaseboardBack",
        (0, -8.86, 0.13),
        (11.72, 0.055, 0.26),
        "Harness_Baseboard",
        0.018,
    )
    api.box(
        "Harness_BaseboardLeft",
        (-5.86, -4.5, 0.13),
        (0.055, 8.72, 0.26),
        "Harness_Baseboard",
        0.018,
    )
    api.box(
        "Harness_BaseboardRight",
        (5.86, -4.5, 0.13),
        (0.055, 8.72, 0.26),
        "Harness_Baseboard",
        0.018,
    )
    api.box(
        "Harness_CorniceBack",
        (0, -8.84, 3.42),
        (11.72, 0.09, 0.16),
        "Harness_Baseboard",
        0.025,
    )
    api.box(
        "Harness_CorniceLeft",
        (-5.84, -4.5, 3.42),
        (0.09, 8.72, 0.16),
        "Harness_Baseboard",
        0.025,
    )
    api.box(
        "Harness_CorniceRight",
        (5.84, -4.5, 3.42),
        (0.09, 8.72, 0.16),
        "Harness_Baseboard",
        0.025,
    )
    for index, x in enumerate((-4.35, -2.20, 2.20, 4.35)):
        api.box(
            f"Harness_BackWallBatten_{index}",
            (x, -8.82, 1.82),
            (0.055, 0.06, 2.92),
            "Harness_Baseboard",
            0.014,
        )

    # Fine floor joints remain almost flush, so they add scale without
    # becoming obstacles along the physical indoor/outdoor route.
    for index, y in enumerate((-8.20, -7.05, -5.90, -4.75, -3.60, -2.45, -1.30)):
        api.box(
            f"Harness_FloorJoint_{index}",
            (0, y, 0.012),
            (11.64, 0.018, 0.012),
            "Harness_Inlay",
            0.003,
        )
    for index, x in enumerate((-4.70, -3.15, -1.58, 1.58, 3.15, 4.70)):
        api.box(
            f"Harness_FloorJointLong_{index}",
            (x, -4.55, 0.013),
            (0.015, 8.60, 0.013),
            "Harness_Inlay",
            0.003,
        )

    # Entrance hardware, recessed luminaires and subtle exterior paver joints.
    for side, x in (("Left", -1.16), ("Right", 1.16)):
        for z in (0.36, 1.42, 2.47):
            api.cylinder(
                f"Harness_FramePin{side}_{z}",
                (x, -0.205, z),
                0.026,
                0.025,
                "Harness_Brass",
                32,
            )
    for row, y in enumerate((-2.0, -5.0, -7.8)):
        for column, x in enumerate((-3.9, -1.35, 1.35, 3.9)):
            api.cylinder(
                f"Harness_Downlight_{row}_{column}",
                (x, y, 3.54),
                0.085,
                0.035,
                "Harness_RecessedLight",
                32,
            )
    for index, y in enumerate((1.70, 3.45, 5.20, 6.95, 8.70, 10.45, 12.20)):
        api.box(
            f"Harness_PaverJoint_{index}",
            (0, y, 0.012),
            (12.0, 0.024, 0.012),
            "Harness_PaverLine",
            0.002,
        )
    for side, x in (("Left", -2.35), ("Right", 2.35)):
        api.cylinder(
            f"Harness_EntrySconceBase{side}",
            (x, 0.16, 2.35),
            0.15,
            0.07,
            "Harness_Baseboard",
            32,
        )
        api.sphere(
            f"Harness_EntrySconceGlow{side}",
            (x, 0.23, 2.35),
            (0.13, 0.10, 0.13),
            "Harness_RecessedLight",
            32,
        )


def world_bbox(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    low = Vector(
        (
            min(point.x for point in corners),
            min(point.y for point in corners),
            min(point.z for point in corners),
        )
    )
    high = Vector(
        (
            max(point.x for point in corners),
            max(point.y for point in corners),
            max(point.z for point in corners),
        )
    )
    return low, high


def enforce_open_connection() -> dict[str, object]:
    removed = []
    moved = []
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH" or obj.name.startswith("Harness_"):
            continue
        low, high = world_bbox(obj)
        # Remove generated geometry that physically seals the shared doorway.
        blocks_door = (
            low.x < 1.08
            and high.x > -1.08
            and low.y < 0.22
            and high.y > -0.22
            and low.z < 2.70
            and high.z > 0.16
        )
        if blocks_door:
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        # Keep a clear human-scale corridor on both sides of the portal.
        blocks_path = (
            low.x < 0.62
            and high.x > -0.62
            and low.y < 3.8
            and high.y > -8.0
            and low.z < 2.25
            and high.z > 0.16
        )
        if blocks_path:
            shift = 1.35 - low.x if obj.location.x >= 0 else -1.35 - high.x
            obj.location.x += shift
            moved.append(obj.name)
    return {"removed_door_blockers": removed, "moved_corridor_blockers": moved}


def add_camera_and_lighting(scene_id: str) -> bpy.types.Object:
    world = (
        bpy.data.worlds.new("ConnectedWorld")
        if not bpy.data.worlds
        else bpy.data.worlds[0]
    )
    bpy.context.scene.world = world
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.16, 0.21, 0.29, 1.0)
    background.inputs["Strength"].default_value = 0.72

    bpy.ops.object.light_add(type="SUN", location=(3, -4, 12))
    sun = bpy.context.object
    sun.name = "Sun"
    sun.rotation_euler = (math.radians(28), math.radians(-18), math.radians(28))
    sun.data.energy = 2.7
    sun.data.angle = math.radians(12)

    interior_energy = 1850 if scene_id == "bookshop_arcade" else 1250
    for name, location, energy, size, color in (
        # Keep the interior softbox below the generated ceiling so it actually
        # illuminates enclosed rooms, including the dark bookshop palette.
        ("InteriorFill", (0, -4.6, 2.78), interior_energy, 4.6, (1.0, 0.78, 0.58)),
        ("InteriorFrontFill", (-3.5, -2.0, 2.70), 1150, 3.2, (1.0, 0.86, 0.70)),
        ("InteriorRearFill", (3.2, -7.0, 2.72), 1100, 3.2, (0.82, 0.90, 1.0)),
        ("DoorSoftbox", (0, 1.5, 3.8), 1450, 4.5, (0.72, 0.86, 1.0)),
        ("ExteriorFill", (-4, 8, 7), 1250, 7.0, (0.78, 0.88, 1.0)),
        ("ExteriorRim", (6, 14, 6), 900, 6.0, (1.0, 0.88, 0.72)),
    ):
        bpy.ops.object.light_add(type="AREA", location=location)
        light = bpy.context.object
        light.name = name
        light.data.energy = energy
        light.data.shape = "DISK"
        light.data.size = size
        light.data.color = color
        direction = (
            Vector((0, -3 if location[1] > 0 else location[1], 0.85)) - light.location
        )
        light.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()

    if scene_id == "bookshop_arcade":
        # The arcade is a genuine covered outdoor volume, so an under-roof
        # softbox is required instead of relying on light blocked by its roof.
        bpy.ops.object.light_add(type="AREA", location=(0, 8.5, 3.55))
        arcade_fill = bpy.context.object
        arcade_fill.name = "ArcadeUnderRoofFill"
        arcade_fill.data.energy = 1550
        arcade_fill.data.shape = "DISK"
        arcade_fill.data.size = 5.0
        arcade_fill.data.color = (0.82, 0.90, 1.0)
        arcade_fill.rotation_euler = (
            (Vector((0, 3.5, 1.0)) - arcade_fill.location)
            .to_track_quat("-Z", "Y")
            .to_euler()
        )

    camera_data = bpy.data.cameras.new("ConnectedCamera")
    camera = bpy.data.objects.new("ConnectedCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    bpy.context.scene.camera = camera
    camera.data.lens = 31
    camera.data.sensor_width = 36
    camera.data.dof.use_dof = False
    bpy.context.scene.view_settings.look = "AgX - Medium High Contrast"
    bpy.context.scene.view_settings.exposure = (
        0.72 if scene_id == "bookshop_arcade" else 0.55
    )
    return camera


def look_at(camera: bpy.types.Object, location, target, lens=31.0) -> None:
    camera.location = tuple(float(value) for value in location)
    direction = Vector(tuple(float(value) for value in target)) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = float(lens)


def configure_render(width: int, height: int, samples: int = 24) -> None:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 72
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_file_extension = True
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 8
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.resolution_percentage = 100
    if hasattr(scene, "eevee"):
        scene.eevee.taa_render_samples = samples


def render_stills(
    scene_root: Path, camera: bpy.types.Object
) -> list[dict[str, object]]:
    image_root = scene_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    for existing in image_root.glob("*.png"):
        if existing.stem not in IMAGE_ROLES:
            existing.unlink()
    # Sixteen deliberately separated views cover long, medium, oblique and
    # elevated sightlines in both directions through the same open doorway.
    # Bookshop side views stay in its clear central aisle; the other scenes
    # use wider room corners to reveal more of their layouts.
    if scene_root.name == "bookshop_arcade":
        indoor_overview = (0.0, -1.15, 2.18)
        indoor_overview_target = (0.0, -6.40, 1.06)
        indoor_detail = (0.0, -4.0, 1.58)
        indoor_detail_target = (0.0, -8.55, 1.35)
        left_inside = (-1.75, -6.3, 1.90)
        right_inside = (1.75, -6.3, 1.90)
        outdoor_detail = (-2.0, 8.8, 1.78)
        outdoor_overview = (5.2, 18.0, 6.6)
        outdoor_overview_target = (0.0, 11.2, 1.15)
        outdoor_overview_lens = 28
        outside_high = (0.0, 15.6, 3.35)
    else:
        # The center rear aisle is deliberately kept clear by the connection
        # pass and gives a useful overview from the entry toward the room.
        indoor_overview = (0.0, -1.05, 2.22)
        indoor_overview_target = (0.0, -6.40, 1.08)
        indoor_detail = (4.65, -6.75, 1.78)
        indoor_detail_target = (-1.55, -4.05, 1.02)
        left_inside = (-3.65, -6.20, 2.00)
        right_inside = (3.65, -6.20, 2.00)
        outdoor_detail = (-8.2, 8.8, 1.88)
        outdoor_overview = (0.0, 17.0, 7.50)
        outdoor_overview_target = (0.0, 4.20, 1.12)
        outdoor_overview_lens = 34
        outside_high = (0.0, 15.6, 6.35)
    views = (
        ("indoor_overview", indoor_overview, indoor_overview_target, 24),
        (
            "indoor_detail",
            indoor_detail,
            indoor_detail_target,
            42 if scene_root.name == "bookshop_arcade" else 38,
        ),
        ("indoor_entry_wide", (0.0, -8.25, 2.30), (0.0, -0.15, 1.42), 25),
        ("inside_to_outside_far", (0.0, -8.15, 1.82), (0.0, 5.30, 1.30), 29),
        ("inside_to_outside_mid", (-0.70, -5.20, 1.70), (0.15, 5.90, 1.24), 31),
        ("inside_to_outside_left", left_inside, (0.45, 3.80, 1.24), 30),
        ("inside_to_outside_right", right_inside, (-0.45, 3.80, 1.24), 30),
        ("inside_to_outside_high", (0.0, -7.70, 3.08), (0.0, 5.00, 1.18), 32),
        (
            "outdoor_overview",
            outdoor_overview,
            outdoor_overview_target,
            outdoor_overview_lens,
        ),
        ("outdoor_detail", outdoor_detail, (1.0, 4.90, 1.10), 38),
        ("outdoor_entry_wide", (0.0, 12.6, 2.75), (0.0, 0.05, 1.45), 26),
        ("outside_to_inside_far", (0.0, 14.5, 2.25), (0.0, -5.20, 1.24), 31),
        ("outside_to_inside_mid", (0.75, 8.80, 1.75), (-0.10, -4.80, 1.22), 31),
        # Raised lateral views cross above foreground furniture and keep their
        # sightlines in the clear center gap between exterior tree rows.
        ("outside_to_inside_left", (-1.80, 13.80, 4.20), (0.28, -3.20, 1.20), 32),
        ("outside_to_inside_right", (1.80, 13.80, 4.20), (-0.28, -3.20, 1.20), 32),
        ("outside_to_inside_high", outside_high, (0.0, -2.80, 1.02), 35),
    )
    if tuple(role for role, *_ in views) != IMAGE_ROLES:
        raise RuntimeError("internal still-role ordering mismatch")
    configure_render(*STILL_SIZE, samples=48)
    records = []
    for role, location, target, lens in views:
        look_at(camera, location, target, lens)
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
                "width": STILL_SIZE[0],
                "height": STILL_SIZE[1],
                "bytes": destination.stat().st_size,
                "sha256": sha256(destination),
                "camera_location": list(location),
                "camera_target": list(target),
                "lens_mm": lens,
            }
        )
        print(f"GLM53_CONNECT_IMAGE scene={scene_root.name} role={role}", flush=True)
    return records


def render_video(
    scene_root: Path, camera: bpy.types.Object, frames: int
) -> list[dict[str, object]]:
    scene = bpy.context.scene
    video_root = scene_root / "videos"
    video_root.mkdir(parents=True, exist_ok=True)
    forward = video_root / "inside_to_outside.mp4"
    reverse = video_root / "outside_to_inside.mp4"
    for path in (forward, reverse):
        path.unlink(missing_ok=True)
    camera.animation_data_clear()
    keyframes = (
        (1, (-0.15, -7.7, 1.63), (0.0, -2.5, 1.35), 31),
        (35, (0.28, -3.2, 1.61), (0.0, 1.4, 1.30), 30),
        (62, (-0.05, -0.65, 1.60), (0.0, 4.5, 1.25), 29),
        (85, (0.12, 3.0, 1.63), (0.0, 8.0, 1.20), 31),
        (frames, (1.8, 10.5, 1.72), (0.0, 14.0, 1.25), 34),
    )
    for frame, location, target, lens in keyframes:
        actual_frame = min(frames, frame)
        look_at(camera, location, target, lens)
        camera.keyframe_insert(data_path="location", frame=actual_frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=actual_frame)
        camera.data.keyframe_insert(data_path="lens", frame=actual_frame)
    if camera.animation_data and camera.animation_data.action:
        for curve in camera.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
    configure_render(*VIDEO_SIZE, samples=24)
    scene.frame_start = 1
    scene.frame_end = frames
    scene.render.fps = FPS
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(forward)
    print(
        f"GLM53_CONNECT_VIDEO_START scene={scene_root.name} frames={frames}", flush=True
    )
    bpy.ops.render.render(animation=True)
    # Depending on Blender build, an extra extension can be appended.
    candidates = (forward, forward.with_suffix(".mp4.mp4"))
    actual_forward = next((path for path in candidates if path.is_file()), None)
    if actual_forward is None:
        raise RuntimeError("Blender did not create the forward video")
    if actual_forward != forward:
        actual_forward.replace(forward)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(forward),
            "-vf",
            "reverse",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(reverse),
        ],
        check=True,
    )
    records = []
    for role, path in (("inside_to_outside", forward), ("outside_to_inside", reverse)):
        if not path.is_file() or path.stat().st_size < 50_000:
            raise RuntimeError(f"invalid video: {path}")
        records.append(
            {
                "role": role,
                "path": str(path.relative_to(scene_root)),
                "width": VIDEO_SIZE[0],
                "height": VIDEO_SIZE[1],
                "fps": FPS,
                "frames": frames,
                "duration_seconds": frames / FPS,
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    print(f"GLM53_CONNECT_VIDEO_COMPLETE scene={scene_root.name}", flush=True)
    return records


def export_assets(scene_root: Path) -> dict[str, object]:
    scene_dir = scene_root / "scene"
    scene_dir.mkdir(parents=True, exist_ok=True)
    blend = scene_dir / "scene.blend"
    glb = scene_dir / "scene.glb"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend), compress=True)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH":
            obj.select_set(True)
    bpy.ops.export_scene.gltf(
        filepath=str(glb),
        export_format="GLB",
        use_selection=True,
        export_apply=True,
        export_cameras=False,
        export_lights=False,
    )
    if blend.stat().st_size < 100_000 or glb.stat().st_size < 50_000:
        raise RuntimeError("3D exports are unexpectedly small")
    return {
        "blend": {
            "path": "scene/scene.blend",
            "bytes": blend.stat().st_size,
            "sha256": sha256(blend),
        },
        "glb": {
            "path": "scene/scene.glb",
            "bytes": glb.stat().st_size,
            "sha256": sha256(glb),
        },
    }


def load_generated(path: Path, scene_id: str):
    module_spec = importlib.util.spec_from_file_location(
        f"glm53_connect_{scene_id}", path
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    if not hasattr(module, "build_scene") or not isinstance(
        getattr(module, "SCENE_SPEC", None), dict
    ):
        raise RuntimeError("generated module lacks build_scene or SCENE_SPEC")
    if module.SCENE_SPEC.get("scene_id") != scene_id:
        raise RuntimeError("generated scene id mismatch")
    return module


def main() -> int:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--scene-id", required=True, choices=SCENE_IDS)
    parser.add_argument("--video-frames", type=int, default=VIDEO_FRAMES)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(arguments)
    if args.video_frames < 24:
        parser.error("--video-frames must be at least 24")
    output = confined(args.output)
    scene_root = output / args.scene_id
    generated = scene_root / "source/generated.py"
    generation_manifest = scene_root / "generation_manifest.json"
    render_manifest = scene_root / "manifest.json"
    expected = [
        scene_root / "scene/scene.blend",
        scene_root / "scene/scene.glb",
        *(scene_root / "images" / f"{name}.png" for name in IMAGE_ROLES),
        scene_root / "videos/inside_to_outside.mp4",
        scene_root / "videos/outside_to_inside.mp4",
    ]
    if (
        not args.force
        and render_manifest.is_file()
        and all(path.is_file() and path.stat().st_size > 0 for path in expected)
    ):
        old = json.loads(render_manifest.read_text(encoding="utf-8"))
        if old.get("render_success") and old.get("video_frames") == args.video_frames:
            print(f"GLM53_CONNECT_RENDER_REUSE scene={args.scene_id}", flush=True)
            return 0
    if not generated.is_file() or not generation_manifest.is_file():
        raise FileNotFoundError(f"missing GLM generation output for {args.scene_id}")
    started_at = utc()
    started = time.monotonic()
    print(f"GLM53_CONNECT_BUILD_START scene={args.scene_id}", flush=True)
    clear_scene()
    api = SceneAPI()
    ensure_core(api, args.scene_id)
    generated_module = load_generated(generated, args.scene_id)
    generated_module.build_scene(api)
    add_refinement_pass(api, args.scene_id)
    connection_adjustments = enforce_open_connection()
    camera = add_camera_and_lighting(args.scene_id)
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    vertex_count = sum(len(obj.data.vertices) for obj in mesh_objects)
    if len(mesh_objects) < 55 or vertex_count < 450:
        raise RuntimeError(
            f"scene is too sparse: meshes={len(mesh_objects)} vertices={vertex_count}"
        )
    assets = export_assets(scene_root)
    images = render_stills(scene_root, camera)
    videos = render_video(scene_root, camera, args.video_frames)
    generation = json.loads(generation_manifest.read_text(encoding="utf-8"))
    manifest = {
        "schema_version": 2,
        "method": "glm53_flash",
        "model": "glm-5.3-flash",
        "provider": "glm-coding-plan",
        "scene_id": args.scene_id,
        "created_at_utc": started_at,
        "completed_at_utc": utc(),
        "render_success": True,
        "true_shared_coordinate_3d_scene": True,
        "native_geometry": True,
        "image_policy": "16 individual unlabelled PNG files; descriptive filenames, no montage and no embedded numbering",
        "refinement": {
            "level": "detailed",
            "rounded_bevel_segments": 3,
            "smooth_curved_geometry": True,
            "architectural_finish_pass": True,
            "furniture_detail_pass": True,
            "lighting_pass": "bright balanced interior/exterior",
            "still_view_count": len(IMAGE_ROLES),
            "connection_view_count": 12,
        },
        "connectivity": {
            "shared_coordinate_frame": True,
            "open_doorway_center_xyz": [0.0, 0.0, 1.4],
            "clear_width_m": 2.2,
            "flush_threshold": True,
            "inside_to_outside_camera_crosses_doorway": True,
            "outside_to_inside_is_reverse_of_same_physical_path": True,
            **connection_adjustments,
        },
        "generation": {
            "generated_code": "source/generated.py",
            "generated_code_sha256": sha256(generated),
            "prompt_sha256": generation["prompt_sha256"],
            "model_requested": generation["model_requested"],
            "billing_route": generation["billing_route"],
        },
        "geometry": {
            "mesh_object_count": len(mesh_objects),
            "vertex_count": vertex_count,
            "material_count": len(bpy.data.materials),
            "interior_bounds_approx_m": [[-6, -9, 0], [6, 0, 3.65]],
            "exterior_bounds_approx_m": [[-15, 0, 0], [15, 20, 12]],
        },
        "assets": assets,
        "images": images,
        "videos": videos,
        "still_resolution": list(STILL_SIZE),
        "video_resolution": list(VIDEO_SIZE),
        "video_fps": FPS,
        "video_frames": args.video_frames,
        "wall_time_seconds": round(time.monotonic() - started, 3),
        "blender_version": bpy.app.version_string,
        "renderer": "BLENDER_EEVEE_NEXT",
    }
    atomic_json(render_manifest, manifest)
    print(f"GLM53_CONNECT_SCENE_COMPLETE scene={args.scene_id}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

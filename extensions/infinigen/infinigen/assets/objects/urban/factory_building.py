"""Reference-driven, production-quality procedural factory buildings.

The four variants in this module deliberately model different industrial
architectural systems rather than recolouring one generic warehouse shell:

* ``gable_clerestory`` -- long beige corrugated workshop with a pitched roof,
  clerestory ribbon and repeated lower windows.
* ``white_modern`` -- crisp white panel-clad factory with a flat parapet,
  horizontal glazing and a tall glazed entrance.
* ``gated_campus`` -- a low grey/blue multi-volume plant behind a masonry wall,
  security gate and guard house.
* ``highbay_monochrome`` -- black-and-white high-bay hall with a pronounced
  structural grid, two-level glazing and a dark gabled end wall.

All visible geometry is generated from code.  The class consumes the same
``UrbanAssetRequest`` used by the other production urban factories and returns
both Blender objects and serialisable layout metadata.
"""

from __future__ import annotations

import math
import random
from collections.abc import Iterable

import bpy
from mathutils import Vector

from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    add_bevel,
    ellipsoid_obj,
    mesh_obj,
)


FACTORY_VARIANTS = (
    "gable_clerestory",
    "white_modern",
    "gated_campus",
    "highbay_monochrome",
)

FACTORY_REFERENCES = {
    "gable_clerestory": (
        "https://encrypted-tbn0.gstatic.com/images?"
        "q=tbn:ANd9GcR35fEUWx2_fjUZdDc1TOkQwFAHDSgDtmGMIy5sIyWgMDhbwaZuZxEByxw&s=10"
    ),
    "white_modern": (
        "https://encrypted-tbn0.gstatic.com/images?"
        "q=tbn:ANd9GcQt5yx5o4UnGVzzWh7zYfuKLWujPLT18jQm3gZLAzdvdw&s=10"
    ),
    "gated_campus": "https://assets.699pic.com/public/web/images/401/934/332.jpg!list.3d.v1",
    "highbay_monochrome": "https://img.redocn.com/sheji/20191231/3Dchangfangmoxing_10772323.jpg",
}


FACTORY_DIMENSIONS = {
    "gable_clerestory": (54.0, 20.0, 11.25),
    "white_modern": (48.0, 20.0, 10.45),
    "gated_campus": (54.0, 32.0, 7.35),
    "highbay_monochrome": (58.0, 22.0, 12.45),
}


def _chain_bump(material, texture_output, strength, distance):
    """Attach a bump source without discarding an existing material normal."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None or "Normal" not in bsdf.inputs:
        return
    existing = None
    if bsdf.inputs["Normal"].is_linked:
        existing = bsdf.inputs["Normal"].links[0].from_socket
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = strength
    bump.inputs["Distance"].default_value = distance
    links.new(texture_output, bump.inputs["Height"])
    if existing is not None:
        links.new(existing, bump.inputs["Normal"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])


def _add_rolled_panel_detail(material, scale=36.0, strength=0.18, distance=0.035):
    """Add fine rolled-steel waviness to panel materials."""
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    texcoord = nodes.new("ShaderNodeTexCoord")
    wave = nodes.new("ShaderNodeTexWave")
    wave.wave_type = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value = scale
    wave.inputs["Distortion"].default_value = 1.25
    wave.inputs["Detail"].default_value = 4.0
    links.new(texcoord.outputs["Generated"], wave.inputs["Vector"])
    _chain_bump(material, wave.outputs["Color"], strength, distance)


def _add_brushed_metal_detail(material):
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    texcoord = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = 115.0
    noise.inputs["Detail"].default_value = 2.5
    noise.inputs["Roughness"].default_value = 0.32
    links.new(texcoord.outputs["Generated"], noise.inputs["Vector"])
    _chain_bump(material, noise.outputs["Fac"], 0.10, 0.012)


def make_factory_materials(make_mat):
    """Return the production material family used by the factory generator."""
    specs = {
        "factory_beige_panel": ((0.18, 0.165, 0.125, 1), dict(roughness=0.66, metallic=0.10, noise_strength=0.15, bump_strength=0.042, noise_scale=28, bump_scale=72)),
        "factory_beige_panel_light": ((0.29, 0.26, 0.195, 1), dict(roughness=0.63, metallic=0.09, noise_strength=0.11, bump_strength=0.032, noise_scale=31, bump_scale=78)),
        "factory_white_panel": ((0.44, 0.46, 0.45, 1), dict(roughness=0.50, metallic=0.07, noise_strength=0.065, bump_strength=0.024, noise_scale=35, bump_scale=84, coat_weight=0.05)),
        "factory_white_trim": ((0.63, 0.65, 0.62, 1), dict(roughness=0.39, metallic=0.08, noise_strength=0.035, coat_weight=0.07)),
        "factory_gray_panel": ((0.14, 0.17, 0.18, 1), dict(roughness=0.61, metallic=0.09, noise_strength=0.12, bump_strength=0.034, noise_scale=30, bump_scale=76)),
        "factory_charcoal_panel": ((0.075, 0.083, 0.086, 1), dict(roughness=0.51, metallic=0.16, noise_strength=0.10, bump_strength=0.032, noise_scale=32, bump_scale=80)),
        "factory_dark_trim": ((0.026, 0.030, 0.032, 1), dict(roughness=0.42, metallic=0.28, noise_strength=0.055, coat_weight=0.04)),
        "factory_roof_zinc": ((0.22, 0.235, 0.235, 1), dict(roughness=0.58, metallic=0.34, noise_strength=0.14, bump_strength=0.032, noise_scale=24, bump_scale=94)),
        "factory_roof_dark": ((0.10, 0.115, 0.12, 1), dict(roughness=0.57, metallic=0.24, noise_strength=0.10, bump_strength=0.030, noise_scale=27, bump_scale=91)),
        "factory_glass_blue": ((0.055, 0.15, 0.20, 0.82), dict(roughness=0.095, metallic=0.05, noise_strength=0.035, transmission=0.12, ior=1.46, coat_weight=0.28)),
        "factory_glass_dark": ((0.020, 0.052, 0.066, 0.90), dict(roughness=0.075, metallic=0.08, noise_strength=0.025, transmission=0.08, ior=1.46, coat_weight=0.30)),
        "factory_glass_reflection": ((0.20, 0.42, 0.54, 0.34), dict(roughness=0.055, transmission=0.38, ior=1.46, coat_weight=0.34)),
        # Neutral, physically layered lites used by the revised gable factory.
        # The dark inner lite and spacer cavity stop the windows reading as flat
        # cyan cards, while the clearer outer lite retains real sky reflections.
        "factory_glass_igu_outer": ((0.025, 0.050, 0.055, 0.66), dict(roughness=0.035, metallic=0.0, noise_strength=0.018, transmission=0.52, ior=1.52, coat_weight=0.38)),
        "factory_glass_igu_inner": ((0.012, 0.024, 0.026, 0.88), dict(roughness=0.13, metallic=0.0, noise_strength=0.025, transmission=0.20, ior=1.52, coat_weight=0.18)),
        "factory_glass_igu_spacer": ((0.075, 0.080, 0.075, 1.0), dict(roughness=0.36, metallic=0.58, noise_strength=0.035)),
        "factory_galvanized": ((0.22, 0.245, 0.245, 1), dict(roughness=0.47, metallic=0.48, noise_strength=0.13, bump_strength=0.024, noise_scale=55, bump_scale=120)),
        "factory_door_gray": ((0.17, 0.195, 0.195, 1), dict(roughness=0.59, metallic=0.16, noise_strength=0.11, bump_strength=0.030, noise_scale=34, bump_scale=83)),
        "factory_safety_blue": ((0.015, 0.24, 0.64, 1), dict(roughness=0.38, metallic=0.12, noise_strength=0.045, coat_weight=0.10)),
        "factory_safety_yellow": ((0.94, 0.56, 0.025, 1), dict(roughness=0.43, metallic=0.05, noise_strength=0.06, coat_weight=0.08)),
        "factory_warning_red": ((0.66, 0.035, 0.025, 1), dict(roughness=0.42, noise_strength=0.045)),
        "factory_shadow": ((0.010, 0.014, 0.016, 1), dict(roughness=0.78, metallic=0.05, noise_strength=0.035)),
        "factory_sealant": ((0.018, 0.022, 0.023, 1), dict(roughness=0.70, noise_strength=0.035)),
        "factory_aluminum": ((0.31, 0.34, 0.34, 1), dict(roughness=0.34, metallic=0.62, noise_strength=0.075, coat_weight=0.06)),
        "factory_stainless": ((0.44, 0.47, 0.46, 1), dict(roughness=0.25, metallic=0.78, noise_strength=0.045, coat_weight=0.10)),
        "factory_sign_blue": ((0.010, 0.075, 0.145, 1), dict(roughness=0.35, metallic=0.18, noise_strength=0.045, coat_weight=0.12)),
        "factory_sign_charcoal": ((0.025, 0.032, 0.035, 1), dict(roughness=0.42, metallic=0.24, noise_strength=0.055, coat_weight=0.08)),
        "factory_mortar": ((0.19, 0.185, 0.165, 1), dict(roughness=0.94, noise_strength=0.20, bump_strength=0.075, noise_scale=35, bump_scale=95)),
        "factory_rust": ((0.17, 0.045, 0.012, 1), dict(roughness=0.91, metallic=0.18, noise_strength=0.25, bump_strength=0.055, noise_scale=42, bump_scale=110)),
        "factory_concrete": ((0.21, 0.205, 0.185, 1), dict(roughness=0.86, noise_strength=0.22, bump_strength=0.085, noise_scale=24, bump_scale=78)),
        "factory_concrete_dark": ((0.13, 0.135, 0.125, 1), dict(roughness=0.91, noise_strength=0.25, bump_strength=0.075, noise_scale=29, bump_scale=82)),
        "factory_masonry_tan": ((0.27, 0.16, 0.07, 1), dict(roughness=0.87, noise_strength=0.25, bump_strength=0.095, noise_scale=26, bump_scale=70)),
        "factory_asphalt": ((0.045, 0.050, 0.052, 1), dict(roughness=0.91, noise_strength=0.31, bump_strength=0.090, noise_scale=44, bump_scale=128)),
        "factory_paving": ((0.18, 0.175, 0.16, 1), dict(roughness=0.89, noise_strength=0.20, bump_strength=0.062, noise_scale=27, bump_scale=86)),
        "factory_marking_white": ((0.55, 0.54, 0.47, 1), dict(roughness=0.72, noise_strength=0.09, bump_strength=0.016, noise_scale=33)),
        "factory_hedge_dark": ((0.010, 0.052, 0.014, 1), dict(roughness=0.93, noise_strength=0.27, bump_strength=0.052, noise_scale=38, bump_scale=92)),
        "factory_hedge_mid": ((0.020, 0.105, 0.028, 1), dict(roughness=0.91, noise_strength=0.23, bump_strength=0.041, noise_scale=31, bump_scale=86)),
        "factory_hedge_light": ((0.045, 0.18, 0.040, 1), dict(roughness=0.89, noise_strength=0.20, bump_strength=0.034, noise_scale=35, bump_scale=90)),
        "factory_soil": ((0.055, 0.028, 0.012, 1), dict(roughness=0.97, noise_strength=0.32, bump_strength=0.11, noise_scale=36, bump_scale=94)),
        "factory_lamp": ((1.0, 0.77, 0.36, 1), dict(roughness=0.16, emission_strength=0.8)),
        "factory_sign_white": ((0.72, 0.70, 0.62, 1), dict(roughness=0.47, noise_strength=0.045)),
    }
    materials = {
        key: make_mat(f"urban_mat_{key}", color, **settings)
        for key, (color, settings) in specs.items()
    }
    for key in (
        "factory_beige_panel",
        "factory_beige_panel_light",
        "factory_white_panel",
        "factory_gray_panel",
        "factory_charcoal_panel",
    ):
        _add_rolled_panel_detail(materials[key])
    for key in ("factory_roof_zinc", "factory_roof_dark", "factory_galvanized"):
        _add_brushed_metal_detail(materials[key])
    return materials


class FactoryBuildingFactory:
    """Build four independently modelled full-scale industrial buildings."""

    def __init__(self, mats, seed=20260831):
        self.mats = mats
        self.seed = int(seed)
        self.objects = []
        self.root = None
        self.prefix = "urban:factory"
        self.rng = random.Random(self.seed)
        self.signage_records = []

    def _m(self, key, fallback="factory_galvanized"):
        return self.mats.get(key, self.mats[fallback])

    def _attach(self, obj, role=None):
        obj.parent = self.root
        obj["factory_procedural"] = True
        if role:
            obj["factory_component_role"] = role
        self.objects.append(obj)
        if len(self.objects) % 100 == 0:
            print(f"[factory-generator] {self.root.get('factory_variant')} components={len(self.objects) - 1}", flush=True)
        return obj

    def _box(self, name, loc, dims, mat, semantic="factory-building", bevel=0.025, role=None):
        # The data API avoids an operator plus transform-apply for every small
        # facade part.  At factory scale that is thousands of dependency-graph
        # rebuilds, while this produces the exact same six-faced solid and
        # keeps every detail as a normal tagged pipeline object.
        sx, sy, sz = (value * 0.5 for value in dims)
        vertices = [
            (-sx, -sy, -sz),
            (sx, -sy, -sz),
            (sx, sy, -sz),
            (-sx, sy, -sz),
            (-sx, -sy, sz),
            (sx, -sy, sz),
            (sx, sy, sz),
            (-sx, sy, sz),
        ]
        faces = [
            (0, 3, 2, 1),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        obj = mesh_obj(f"{self.prefix}:{name}", vertices, faces, mat, semantic)
        obj.location = loc
        add_bevel(obj, bevel, segments=1)
        return self._attach(obj, role)

    def _cylinder(self, name, loc, radius, depth, mat, semantic="factory-equipment", vertices=24, role=None):
        count = max(6, int(vertices))
        half = depth * 0.5
        ring = [
            (radius * math.cos(math.tau * index / count), radius * math.sin(math.tau * index / count))
            for index in range(count)
        ]
        points = [(x, y, -half) for x, y in ring] + [(x, y, half) for x, y in ring]
        faces = [tuple(reversed(range(count))), tuple(range(count, count * 2))]
        faces.extend(
            (
                index,
                (index + 1) % count,
                count + (index + 1) % count,
                count + index,
            )
            for index in range(count)
        )
        obj = mesh_obj(f"{self.prefix}:{name}", points, faces, mat, semantic)
        obj.location = loc
        for polygon in obj.data.polygons[2:]:
            polygon.use_smooth = True
        return self._attach(obj, role)

    def _between(self, name, start, end, radius, mat, semantic="factory-equipment", vertices=16, role=None):
        start_v = Vector(start)
        end_v = Vector(end)
        direction = end_v - start_v
        obj = self._cylinder(name, (start_v + end_v) * 0.5, radius, direction.length, mat, semantic, vertices, role)
        if direction.length > 1e-6:
            obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
        return obj

    def _rect_between(self, name, start, end, section, mat, semantic="factory-structure", role=None, bevel=0.008):
        """Create a square/rectangular hollow-section member between two points."""
        start_v = Vector(start)
        end_v = Vector(end)
        direction = end_v - start_v
        if direction.length <= 1e-6:
            return None
        if isinstance(section, (int, float)):
            section = (float(section), float(section))
        obj = self._box(
            name,
            (start_v + end_v) * 0.5,
            (float(section[0]), float(section[1]), direction.length),
            mat,
            semantic,
            bevel,
            role,
        )
        obj.rotation_euler = direction.to_track_quat("Z", "Y").to_euler()
        return obj

    def _ellipsoid(self, name, loc, scale, mat, semantic="landscaping", segments=16, rings=8, role=None):
        return self._attach(
            ellipsoid_obj(
                f"{self.prefix}:{name}",
                loc,
                scale,
                mat,
                semantic,
                segments=segments,
                ring_count=rings,
            ),
            role,
        )

    def _mesh(self, name, vertices, faces, mat, semantic="factory-building", smooth=False, role=None):
        return self._attach(
            mesh_obj(f"{self.prefix}:{name}", vertices, faces, mat, semantic, smooth=smooth),
            role,
        )

    def _batch_boxes(self, name, specs, mat, semantic="factory-detail", role=None):
        """Merge many tiny rectangular details into one efficiently rendered mesh."""
        vertices = []
        faces = []
        for loc, dims in specs:
            cx, cy, cz = loc
            sx, sy, sz = (value * 0.5 for value in dims)
            base = len(vertices)
            vertices.extend(
                [
                    (cx - sx, cy - sy, cz - sz),
                    (cx + sx, cy - sy, cz - sz),
                    (cx + sx, cy + sy, cz - sz),
                    (cx - sx, cy + sy, cz - sz),
                    (cx - sx, cy - sy, cz + sz),
                    (cx + sx, cy - sy, cz + sz),
                    (cx + sx, cy + sy, cz + sz),
                    (cx - sx, cy + sy, cz + sz),
                ]
            )
            faces.extend(
                [
                    (base, base + 3, base + 2, base + 1),
                    (base + 4, base + 5, base + 6, base + 7),
                    (base, base + 1, base + 5, base + 4),
                    (base + 1, base + 2, base + 6, base + 5),
                    (base + 2, base + 3, base + 7, base + 6),
                    (base + 3, base, base + 4, base + 7),
                ]
            )
        if not vertices:
            return None
        return self._mesh(name, vertices, faces, mat, semantic, role=role)

    def _wall_box(self, side, wall, u, z, span, height, depth, mat, name, *, offset=0.0, bevel=0.01, semantic="factory-detail", role=None):
        outward = -1.0 if side in {"front", "left"} else 1.0
        coord = wall + outward * offset
        if side in {"front", "back"}:
            loc = (u, coord, z)
            dims = (span, depth, height)
        else:
            loc = (coord, u, z)
            dims = (depth, span, height)
        return self._box(name, loc, dims, mat, semantic, bevel, role)

    def _text(
        self,
        name,
        body,
        loc,
        size,
        mat,
        *,
        align="CENTER",
        extrude=0.035,
        side="front",
        max_width=None,
        max_height=None,
    ):
        curve = bpy.data.curves.new(f"{self.prefix}:{name}:curve", type="FONT")
        curve.body = body
        curve.align_x = align
        curve.align_y = "CENTER"
        curve.size = size
        curve.extrude = extrude
        curve.bevel_depth = min(0.012, extrude * 0.24)
        curve.bevel_resolution = 2
        obj = bpy.data.objects.new(f"{self.prefix}:{name}", curve)
        bpy.context.collection.objects.link(obj)
        obj.location = loc
        rotations = {
            "front": (math.radians(90), 0, 0),
            "back": (math.radians(-90), 0, 0),
            "left": (math.radians(90), 0, math.radians(-90)),
            "right": (math.radians(90), 0, math.radians(90)),
        }
        obj.rotation_euler = rotations[side]
        if mat is not None:
            curve.materials.append(mat)
        self._attach(obj, "signage")
        bpy.context.view_layer.update()
        # Blender reports ``Object.dimensions`` in the object's local axes.
        # Font glyph width/height are therefore always local X/Y even after the
        # object is rotated onto a front or side facade; local Z is extrusion.
        actual_width = float(obj.dimensions.x)
        actual_height = float(obj.dimensions.y)
        fit = 1.0
        if max_width and actual_width > max_width:
            fit = min(fit, float(max_width) / actual_width)
        if max_height and actual_height > max_height:
            fit = min(fit, float(max_height) / actual_height)
        if fit < 0.999:
            curve.size *= fit
            bpy.context.view_layer.update()
            actual_width = float(obj.dimensions.x)
            actual_height = float(obj.dimensions.y)
        within_bounds = (
            (max_width is None or actual_width <= float(max_width) + 1e-3)
            and (max_height is None or actual_height <= float(max_height) + 1e-3)
        )
        obj["factory_sign_actual_width_m"] = actual_width
        obj["factory_sign_actual_height_m"] = actual_height
        obj["factory_sign_within_bounds"] = within_bounds
        self.signage_records.append(
            {
                "name": name,
                "text": body,
                "side": side,
                "actual_width_m": round(actual_width, 4),
                "actual_height_m": round(actual_height, 4),
                "max_width_m": None if max_width is None else float(max_width),
                "max_height_m": None if max_height is None else float(max_height),
                "within_building_bounds": bool(within_bounds),
            }
        )
        return obj

    def _facade_sign(
        self,
        name,
        body,
        side,
        wall,
        u,
        z,
        panel_width,
        panel_height,
        *,
        font_size,
        panel_mat=None,
        text_mat=None,
    ):
        """Model a bounded, framed tray sign with stand-offs and raised letters."""
        panel_mat = panel_mat or self._m("factory_sign_charcoal")
        text_mat = text_mat or self._m("factory_sign_white")
        self._wall_box(
            side,
            wall,
            u,
            z,
            panel_width,
            panel_height,
            0.13,
            self._m("factory_shadow"),
            f"{name}:mounting-shadow",
            offset=0.32,
            bevel=0.018,
            semantic="factory-sign",
            role="sign-shadow-gap",
        )
        self._wall_box(
            side,
            wall,
            u,
            z,
            panel_width - 0.10,
            panel_height - 0.10,
            0.15,
            panel_mat,
            f"{name}:tray",
            offset=0.40,
            bevel=0.035,
            semantic="factory-sign",
            role="folded-sign-tray",
        )
        border = 0.055
        for label, du, dz, bw, bh in (
            ("left", -panel_width * 0.5 + border, 0.0, border, panel_height - 0.13),
            ("right", panel_width * 0.5 - border, 0.0, border, panel_height - 0.13),
            ("bottom", 0.0, -panel_height * 0.5 + border, panel_width - 0.13, border),
            ("top", 0.0, panel_height * 0.5 - border, panel_width - 0.13, border),
        ):
            self._wall_box(
                side,
                wall,
                u + du,
                z + dz,
                bw,
                bh,
                0.045,
                self._m("factory_aluminum"),
                f"{name}:frame:{label}",
                offset=0.49,
                bevel=0.009,
                semantic="factory-sign",
                role="sign-aluminum-frame",
            )
        outward = -1.0 if side in {"front", "left"} else 1.0
        face_coord = wall + outward * 0.54
        loc = (u, face_coord, z) if side in {"front", "back"} else (face_coord, u, z)
        text_obj = self._text(
            f"{name}:letters",
            body,
            loc,
            font_size,
            text_mat,
            extrude=0.050,
            side=side,
            max_width=panel_width - 0.48,
            max_height=panel_height - 0.28,
        )
        for index, (du, dz) in enumerate(
            (
                (-panel_width * 0.42, -panel_height * 0.34),
                (panel_width * 0.42, -panel_height * 0.34),
                (-panel_width * 0.42, panel_height * 0.34),
                (panel_width * 0.42, panel_height * 0.34),
            )
        ):
            self._wall_box(
                side,
                wall,
                u + du,
                z + dz,
                0.075,
                0.075,
                0.055,
                self._m("factory_stainless"),
                f"{name}:fastener:{index}",
                offset=0.545,
                bevel=0.012,
                semantic="factory-sign",
                role="sign-face-fastener",
            )
        return text_obj

    def _root_for_request(self, request, variant, fid):
        root = bpy.data.objects.new(f"urban:factory:{fid}:{variant}:root", None)
        bpy.context.collection.objects.link(root)
        root.empty_display_type = "CUBE"
        root.empty_display_size = 2.0
        root.location = request.location
        root.rotation_euler[2] = request.yaw
        root["urban_semantic"] = request.semantic
        root["factory_variant"] = variant
        root["factory_reference"] = FACTORY_REFERENCES[variant]
        root["factory_procedural"] = True
        root["factory_modeling_quality"] = "production_architectural_detail_v3"
        self.root = root
        self.objects = [root]
        self.prefix = f"urban:factory:{fid}:{variant}"
        self.rng = random.Random(self.seed + sum(ord(ch) for ch in str(fid)) + 997 * FACTORY_VARIANTS.index(variant))
        self.signage_records = []

    def _gable_end(self, name, x, depth, eave, ridge, mat, thickness=0.12):
        side = -1 if x < 0 else 1
        outer = x + side * thickness * 0.5
        inner = x - side * thickness * 0.5
        vertices = [
            (outer, -depth * 0.5, eave),
            (outer, depth * 0.5, eave),
            (outer, 0.0, ridge),
            (inner, -depth * 0.5, eave),
            (inner, depth * 0.5, eave),
            (inner, 0.0, ridge),
        ]
        faces = [
            (0, 1, 2),
            (5, 4, 3),
            (0, 3, 4, 1),
            (1, 4, 5, 2),
            (2, 5, 3, 0),
        ]
        return self._mesh(name, vertices, faces, mat, role="solid-insulated-gable-cladding")

    def _roof_slope(self, name, width, depth, eave, ridge, side, mat, overhang=0.55, thickness=0.16):
        # ``side`` is the signed eave direction.  Keeping the sign here is
        # important: negating it placed both roof slabs on the rear pitch and
        # left the street-facing half open despite the correctly mirrored
        # standing seams.
        y0 = side * (depth * 0.5 + overhang)
        y1 = 0.0
        z0 = eave
        z1 = ridge
        x0 = -width * 0.5 - overhang
        x1 = width * 0.5 + overhang
        top = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z1), (x0, y1, z1)]
        bottom = [(x, y, z - thickness) for x, y, z in top]
        vertices = top + bottom
        faces = [
            (0, 1, 2, 3),
            (7, 6, 5, 4),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (3, 7, 4, 0),
        ]
        return self._mesh(name, vertices, faces, mat, role="standing-seam-roof")

    def _roof_ribs(self, name, width, depth, eave, ridge, spacing, mat):
        slope = math.hypot(depth * 0.5, ridge - eave)
        angle = math.atan2(ridge - eave, depth * 0.5)
        for index, x in enumerate(self._frange(-width * 0.5 + 0.35, width * 0.5 - 0.2, spacing)):
            for side in (-1, 1):
                rib = self._box(
                    f"{name}:{index}:{'front' if side < 0 else 'back'}",
                    (x, side * depth * 0.25, (eave + ridge) * 0.5 + 0.055),
                    (0.040, slope + 0.55, 0.055),
                    mat,
                    "factory-roof-detail",
                    0.006,
                    "standing-seam-rib",
                )
                rib.rotation_euler[0] = -side * angle

    def _architectural_standing_seam_roof(
        self,
        name,
        width,
        depth,
        eave,
        ridge,
        spacing,
        mat,
    ):
        """Detail a complete mechanically seamed industrial roof envelope.

        The assembly includes two-part raised seams, intermittent seam clips,
        transverse sheet laps, formed ridge wings and closures, rake flashing,
        eave drip aprons, closure blocks and visible gasketed fasteners.  This
        replaces the former blue box skylights on the gable factory.
        """
        slope = math.hypot(depth * 0.5, ridge - eave)
        angle = math.atan2(ridge - eave, depth * 0.5)
        seam_x = self._frange(
            -width * 0.5 + 0.35,
            width * 0.5 - 0.20,
            spacing,
        )
        clip_mat = self._m("factory_stainless")
        seal_mat = self._m("factory_sealant")

        for side in (-1, 1):
            for index, x in enumerate(seam_x):
                base = self._box(
                    f"{name}:seam-base:{side}:{index}",
                    (x, side * depth * 0.25, (eave + ridge) * 0.5 + 0.035),
                    (0.105, slope + 0.62, 0.035),
                    mat,
                    "factory-roof-detail",
                    0.005,
                    "standing-seam-folded-base",
                )
                base.rotation_euler[0] = -side * angle
                cap = self._box(
                    f"{name}:double-lock-cap:{side}:{index}",
                    (x, side * depth * 0.25, (eave + ridge) * 0.5 + 0.095),
                    (0.042, slope + 0.66, 0.105),
                    self._m("factory_galvanized"),
                    "factory-roof-detail",
                    0.006,
                    "mechanically-double-locked-standing-seam-cap",
                )
                cap.rotation_euler[0] = -side * angle

                # Clips are intentionally modelled only at representative
                # visible intervals; every seam remains continuous geometry.
                if index % 4 == 1:
                    for clip_index, fraction in enumerate((0.18, 0.47, 0.76)):
                        y = side * depth * 0.5 * (1.0 - fraction)
                        z = eave + (ridge - eave) * fraction + 0.125
                        clip = self._box(
                            f"{name}:seam-clip:{side}:{index}:{clip_index}",
                            (x, y, z),
                            (0.19, 0.24, 0.050),
                            clip_mat,
                            "factory-roof-fastener",
                            0.006,
                            "concealed-standing-seam-retention-clip",
                        )
                        clip.rotation_euler[0] = -side * angle

            # Transverse sheet laps add realistic fabrication scale and break
            # the otherwise perfectly uninterrupted roof planes.
            for lap_index, fraction in enumerate((0.24, 0.49, 0.74)):
                y = side * depth * 0.5 * (1.0 - fraction)
                z = eave + (ridge - eave) * fraction + 0.050
                lap = self._box(
                    f"{name}:sheet-lap:{side}:{lap_index}",
                    (0.0, y, z),
                    (width + 0.35, 0.052, 0.030),
                    self._m("factory_aluminum"),
                    "factory-roof-detail",
                    0.004,
                    "sealed-transverse-roof-sheet-lap",
                )
                lap.rotation_euler[0] = -side * angle

            eave_y = side * (depth * 0.5 + 0.57)
            self._box(
                f"{name}:eave-drip-apron:{side}",
                (0.0, eave_y, eave - 0.105),
                (width + 1.18, 0.24, 0.20),
                mat,
                "factory-roof-detail",
                0.010,
                "hemmed-formed-metal-eave-drip-apron",
            )
            closures = []
            for x in seam_x[:-1]:
                cx = x + spacing * 0.5
                closures.append(
                    ((cx, side * (depth * 0.5 + 0.43), eave - 0.015), (spacing - 0.12, 0.075, 0.065))
                )
            self._batch_boxes(
                f"{name}:profiled-eave-closures:{side}",
                closures,
                seal_mat,
                "factory-roof-detail",
                "profiled-foam-eave-closure-strips",
            )

        # Folded ridge cap wings replace the former pipe-like cap.  Separate
        # fastener rows and compressible closures expose the actual build-up.
        for side in (-1, 1):
            ridge_wing = self._box(
                f"{name}:folded-ridge-wing:{side}",
                (0.0, side * 0.27, ridge + 0.045),
                (width + 1.18, 0.68, 0.075),
                self._m("factory_galvanized"),
                "factory-roof-detail",
                0.008,
                "folded-ventilated-ridge-cap-wing",
            )
            ridge_wing.rotation_euler[0] = -side * angle
            self._box(
                f"{name}:ridge-closure:{side}",
                (0.0, side * 0.39, ridge - 0.035),
                (width + 0.72, 0.105, 0.075),
                seal_mat,
                "factory-roof-detail",
                0.006,
                "continuous-vented-ridge-closure",
            )

        ridge_fasteners = []
        for x in self._frange(-width * 0.5 + 0.55, width * 0.5 - 0.45, spacing):
            for side in (-1, 1):
                ridge_fasteners.append(((x, side * 0.31, ridge + 0.155), (0.060, 0.060, 0.045)))
        self._batch_boxes(
            f"{name}:ridge-cap-fasteners",
            ridge_fasteners,
            clip_mat,
            "factory-roof-fastener",
            "gasketed-ridge-cap-fasteners",
        )

        for edge_index, x in enumerate((-width * 0.5 - 0.57, width * 0.5 + 0.57)):
            for side in (-1, 1):
                self._rect_between(
                    f"{name}:rake-flashing:{edge_index}:{side}",
                    (x, side * (depth * 0.5 + 0.56), eave - 0.06),
                    (x, 0.0, ridge + 0.12),
                    (0.12, 0.16),
                    self._m("factory_galvanized"),
                    "factory-roof-detail",
                    "folded-rake-edge-flashing",
                    bevel=0.008,
                )

    def _roof_service_walkway(self, name, start_x, end_x, y, z):
        """Raised galvanized maintenance grating with rails and support shoes."""
        length = abs(end_x - start_x)
        center_x = (start_x + end_x) * 0.5
        self._box(
            f"{name}:side-rail-front",
            (center_x, y - 0.44, z),
            (length, 0.075, 0.095),
            self._m("factory_galvanized"),
            "factory-roof-access",
            0.008,
            "roof-walkway-side-rail",
        )
        self._box(
            f"{name}:side-rail-back",
            (center_x, y + 0.44, z),
            (length, 0.075, 0.095),
            self._m("factory_galvanized"),
            "factory-roof-access",
            0.008,
            "roof-walkway-side-rail",
        )
        treads = []
        for x in self._frange(min(start_x, end_x) + 0.08, max(start_x, end_x) - 0.04, 0.22):
            treads.append(((x, y, z + 0.035), (0.055, 0.82, 0.045)))
        self._batch_boxes(
            f"{name}:open-bar-grating",
            treads,
            self._m("factory_aluminum"),
            "factory-roof-access",
            "open-bar-roof-maintenance-grating",
        )
        shoes = []
        for x in self._frange(min(start_x, end_x) + 0.55, max(start_x, end_x) - 0.35, 1.55):
            for yy in (y - 0.35, y + 0.35):
                shoes.append(((x, yy, z - 0.105), (0.24, 0.18, 0.16)))
        self._batch_boxes(
            f"{name}:support-shoes",
            shoes,
            self._m("factory_dark_trim"),
            "factory-roof-access",
            "non-penetrating-roof-walkway-support-shoes",
        )

    @staticmethod
    def _frange(start, stop, step):
        values = []
        value = start
        while value <= stop + 1e-6:
            values.append(value)
            value += step
        return values

    def _panel_ribs(self, name, side, wall, span, height, mat, *, spacing=0.48, z0=0.45, offset=0.065, center_u=0.0):
        specs = []
        for u in self._frange(center_u - span * 0.5 + spacing * 0.5, center_u + span * 0.5 - spacing * 0.25, spacing):
            outward = -1 if side in {"front", "left"} else 1
            if side in {"front", "back"}:
                specs.append(((u, wall + outward * offset, z0 + height * 0.5), (0.032, 0.052, height)))
            else:
                specs.append(((wall + outward * offset, u, z0 + height * 0.5), (0.052, 0.032, height)))
        self._batch_boxes(name, specs, mat, "factory-cladding-detail", "corrugated-panel-ribs")

    def _panel_joints(self, name, side, wall, span, levels, mat, offset=0.072, center_u=0.0):
        specs = []
        outward = -1 if side in {"front", "left"} else 1
        for z in levels:
            if side in {"front", "back"}:
                specs.append(((center_u, wall + outward * offset, z), (span, 0.030, 0.026)))
            else:
                specs.append(((wall + outward * offset, center_u, z), (0.030, span, 0.026)))
        self._batch_boxes(name, specs, mat, "factory-cladding-detail", "panel-horizontal-joints")

    def _framed_window(self, name, side, wall, u, z, width, height, *, mullions=1, transoms=0, canopy=False, frame_mat=None, glass_mat=None):
        frame_mat = frame_mat or self._m("factory_galvanized")
        glass_mat = glass_mat or self._m("factory_glass_blue")
        self._wall_box(side, wall, u, z, width + 0.34, height + 0.32, 0.085, self._m("factory_shadow"), f"{name}:reveal", offset=0.047, bevel=0.008, role="deep-window-reveal")
        self._wall_box(side, wall, u, z, width, height, 0.070, glass_mat, f"{name}:glass", offset=0.095, bevel=0.006, semantic="window", role="industrial-glazing")
        bar = 0.070
        for label, du, dz, bw, bh in (
            ("left", -width * 0.5 - bar * 0.45, 0, bar, height + 0.18),
            ("right", width * 0.5 + bar * 0.45, 0, bar, height + 0.18),
            ("bottom", 0, -height * 0.5 - bar * 0.45, width + 0.20, bar),
            ("top", 0, height * 0.5 + bar * 0.45, width + 0.20, bar),
        ):
            self._wall_box(side, wall, u + du, z + dz, bw, bh, 0.105, frame_mat, f"{name}:frame:{label}", offset=0.135, bevel=0.008, semantic="window-frame", role="window-frame")
        for index in range(mullions):
            du = width * ((index + 1) / (mullions + 1) - 0.5)
            self._wall_box(side, wall, u + du, z, 0.050, height, 0.108, frame_mat, f"{name}:mullion:{index}", offset=0.138, bevel=0.005, semantic="window-frame", role="window-mullion")
        for index in range(transoms):
            dz = height * ((index + 1) / (transoms + 1) - 0.5)
            self._wall_box(side, wall, u, z + dz, width, 0.050, 0.108, frame_mat, f"{name}:transom:{index}", offset=0.138, bevel=0.005, semantic="window-frame", role="window-transom")
        # Projecting sill, head flashing and compressible perimeter gasket make
        # the glazing read as a properly installed facade assembly rather than
        # a blue card sitting on the wall.
        self._wall_box(side, wall, u, z - height * 0.5 - 0.105, width + 0.42, 0.11, 0.25, frame_mat, f"{name}:sill", offset=0.185, bevel=0.010, semantic="window-flashing", role="formed-metal-window-sill")
        self._wall_box(side, wall, u, z + height * 0.5 + 0.115, width + 0.46, 0.105, 0.28, frame_mat, f"{name}:head-flashing", offset=0.190, bevel=0.010, semantic="window-flashing", role="drip-edge-head-flashing")
        gasket = 0.026
        for label, du, dz, bw, bh in (
            ("left", -width * 0.5 + gasket * 0.5, 0.0, gasket, height - 0.04),
            ("right", width * 0.5 - gasket * 0.5, 0.0, gasket, height - 0.04),
            ("bottom", 0.0, -height * 0.5 + gasket * 0.5, width - 0.04, gasket),
            ("top", 0.0, height * 0.5 - gasket * 0.5, width - 0.04, gasket),
        ):
            self._wall_box(side, wall, u + du, z + dz, bw, bh, 0.022, self._m("factory_sealant"), f"{name}:gasket:{label}", offset=0.202, bevel=0.003, semantic="window-frame", role="glazing-perimeter-gasket")
        self._window_reflection(name, side, wall, u, z, width, height)
        if canopy:
            self._canopy(f"{name}:canopy", side, wall, u, z + height * 0.5 + 0.45, width + 0.85, 1.15, frame_mat)

    def _deep_igu_window(
        self,
        name,
        side,
        wall,
        u,
        z,
        width,
        height,
        *,
        mullions=1,
        transoms=0,
        frame_mat=None,
    ):
        """Build a drained, pressure-equalised industrial IGU window.

        Each opening has a dark wall cavity, folded reveal liners, separate
        inner and outer glass lites, warm-edge spacers, captured glazing beads,
        thermal breaks, pressure caps, sloped sill flashing, weep slots and
        exposed frame fasteners.  Pane geometry is individually partitioned so
        reflections break naturally at every mullion instead of spanning one
        flat coloured rectangle.
        """
        frame_mat = frame_mat or self._m("factory_aluminum")
        outer_glass = self._m("factory_glass_igu_outer")
        inner_glass = self._m("factory_glass_igu_inner")
        spacer_mat = self._m("factory_glass_igu_spacer")
        sealant = self._m("factory_sealant")
        outward = -1.0 if side in {"front", "left"} else 1.0

        # Recess and four folded liners give the opening real construction
        # depth even though the reusable factory shell remains watertight.
        self._wall_box(
            side,
            wall,
            u,
            z,
            width + 0.50,
            height + 0.48,
            0.13,
            self._m("factory_shadow"),
            f"{name}:rough-opening-cavity",
            offset=0.052,
            bevel=0.010,
            semantic="window-reveal",
            role="deep-window-rough-opening-cavity",
        )
        liner = 0.16
        for label, du, dz, span, rise in (
            ("left", -width * 0.5 - liner * 0.5, 0.0, liner, height + 0.28),
            ("right", width * 0.5 + liner * 0.5, 0.0, liner, height + 0.28),
            ("bottom", 0.0, -height * 0.5 - liner * 0.5, width + 0.30, liner),
            ("top", 0.0, height * 0.5 + liner * 0.5, width + 0.30, liner),
        ):
            self._wall_box(
                side,
                wall,
                u + du,
                z + dz,
                span,
                rise,
                0.31,
                self._m("factory_dark_trim"),
                f"{name}:folded-reveal-liner:{label}",
                offset=0.115,
                bevel=0.009,
                semantic="window-reveal",
                role="folded-metal-window-reveal-liner",
            )

        columns = max(1, int(mullions) + 1)
        rows = max(1, int(transoms) + 1)
        mullion_face = 0.105
        transom_face = 0.095
        pane_gap_x = mullion_face + 0.055
        pane_gap_z = transom_face + 0.050
        pane_width = (width - (columns - 1) * pane_gap_x) / columns
        pane_height = (height - (rows - 1) * pane_gap_z) / rows
        pane_width = max(0.18, pane_width)
        pane_height = max(0.18, pane_height)

        inner_specs = []
        outer_specs = []
        spacer_specs = []
        bead_specs = []
        glass_centers = []
        for row in range(rows):
            cz = z - height * 0.5 + pane_height * 0.5 + row * (pane_height + pane_gap_z)
            for column in range(columns):
                cu = u - width * 0.5 + pane_width * 0.5 + column * (pane_width + pane_gap_x)
                glass_centers.append((cu, cz))
                if side in {"front", "back"}:
                    inner_specs.append(((cu, wall + outward * 0.125, cz), (pane_width, 0.030, pane_height)))
                    outer_specs.append(((cu, wall + outward * 0.190, cz), (pane_width, 0.040, pane_height)))
                else:
                    inner_specs.append(((wall + outward * 0.125, cu, cz), (0.030, pane_width, pane_height)))
                    outer_specs.append(((wall + outward * 0.190, cu, cz), (0.040, pane_width, pane_height)))

                # A closed warm-edge spacer and an exterior captured bead are
                # modelled around every lite, not painted into the glass shader.
                for label, du, dz, bw, bh in (
                    ("left", -pane_width * 0.5 + 0.025, 0.0, 0.050, pane_height - 0.04),
                    ("right", pane_width * 0.5 - 0.025, 0.0, 0.050, pane_height - 0.04),
                    ("bottom", 0.0, -pane_height * 0.5 + 0.025, pane_width - 0.04, 0.050),
                    ("top", 0.0, pane_height * 0.5 - 0.025, pane_width - 0.04, 0.050),
                ):
                    _ = label
                    if side in {"front", "back"}:
                        spacer_specs.append(((cu + du, wall + outward * 0.158, cz + dz), (bw, 0.025, bh)))
                        bead_specs.append(((cu + du, wall + outward * 0.225, cz + dz), (bw, 0.048, bh)))
                    else:
                        spacer_specs.append(((wall + outward * 0.158, cu + du, cz + dz), (0.025, bw, bh)))
                        bead_specs.append(((wall + outward * 0.225, cu + du, cz + dz), (0.048, bw, bh)))

        self._batch_boxes(
            f"{name}:inner-lites",
            inner_specs,
            inner_glass,
            "window-glass",
            "insulating-glass-unit-inner-lites",
        )
        self._batch_boxes(
            f"{name}:outer-lites",
            outer_specs,
            outer_glass,
            "window-glass",
            "insulating-glass-unit-outer-lites",
        )
        self._batch_boxes(
            f"{name}:warm-edge-spacers",
            spacer_specs,
            spacer_mat,
            "window-frame",
            "warm-edge-insulating-glass-spacers",
        )
        self._batch_boxes(
            f"{name}:captured-glazing-beads",
            bead_specs,
            frame_mat,
            "window-frame",
            "captured-exterior-glazing-beads",
        )

        # Extruded perimeter members, then separate snap-on pressure caps and
        # black thermal breaks over each mullion/transom centreline.
        frame_face = 0.13
        for label, du, dz, span, rise in (
            ("left", -width * 0.5 - frame_face * 0.5, 0.0, frame_face, height + 0.30),
            ("right", width * 0.5 + frame_face * 0.5, 0.0, frame_face, height + 0.30),
            ("bottom", 0.0, -height * 0.5 - frame_face * 0.5, width + 0.32, frame_face),
            ("top", 0.0, height * 0.5 + frame_face * 0.5, width + 0.32, frame_face),
        ):
            self._wall_box(
                side,
                wall,
                u + du,
                z + dz,
                span,
                rise,
                0.19,
                frame_mat,
                f"{name}:perimeter-extrusion:{label}",
                offset=0.215,
                bevel=0.009,
                semantic="window-frame",
                role="thermally-broken-aluminum-perimeter-extrusion",
            )
        for index in range(columns - 1):
            du = -width * 0.5 + pane_width + pane_gap_x * 0.5 + index * (pane_width + pane_gap_x)
            self._wall_box(
                side,
                wall,
                u + du,
                z,
                mullion_face,
                height,
                0.205,
                frame_mat,
                f"{name}:structural-mullion:{index}",
                offset=0.218,
                bevel=0.007,
                semantic="window-frame",
                role="extruded-aluminum-structural-mullion",
            )
            self._wall_box(
                side,
                wall,
                u + du,
                z,
                0.026,
                height - 0.08,
                0.032,
                sealant,
                f"{name}:mullion-thermal-break:{index}",
                offset=0.329,
                bevel=0.003,
                semantic="window-frame",
                role="mullion-polyamide-thermal-break",
            )
        for index in range(rows - 1):
            dz = -height * 0.5 + pane_height + pane_gap_z * 0.5 + index * (pane_height + pane_gap_z)
            self._wall_box(
                side,
                wall,
                u,
                z + dz,
                width,
                transom_face,
                0.205,
                frame_mat,
                f"{name}:structural-transom:{index}",
                offset=0.218,
                bevel=0.007,
                semantic="window-frame",
                role="extruded-aluminum-structural-transom",
            )
            self._wall_box(
                side,
                wall,
                u,
                z + dz,
                width - 0.08,
                0.026,
                0.032,
                sealant,
                f"{name}:transom-thermal-break:{index}",
                offset=0.329,
                bevel=0.003,
                semantic="window-frame",
                role="transom-polyamide-thermal-break",
            )

        sill = self._wall_box(
            side,
            wall,
            u,
            z - height * 0.5 - 0.155,
            width + 0.58,
            0.13,
            0.43,
            frame_mat,
            f"{name}:drained-sloped-sill-pan",
            offset=0.285,
            bevel=0.010,
            semantic="window-flashing",
            role="drained-sloped-window-sill-pan",
        )
        if side in {"front", "back"}:
            sill.rotation_euler[0] = outward * math.radians(5.0)
        else:
            sill.rotation_euler[1] = -outward * math.radians(5.0)
        self._wall_box(
            side,
            wall,
            u,
            z + height * 0.5 + 0.16,
            width + 0.62,
            0.12,
            0.38,
            frame_mat,
            f"{name}:head-drip-flashing",
            offset=0.275,
            bevel=0.009,
            semantic="window-flashing",
            role="folded-head-flashing-with-drip-hem",
        )

        weeps = []
        fasteners = []
        for index in range(columns):
            cu, _cz = glass_centers[index]
            if side in {"front", "back"}:
                weeps.append(((cu, wall + outward * 0.516, z - height * 0.5 - 0.115), (0.14, 0.026, 0.022)))
            else:
                weeps.append(((wall + outward * 0.516, cu, z - height * 0.5 - 0.115), (0.026, 0.14, 0.022)))
        for du, dz in (
            (-width * 0.5 - 0.065, -height * 0.5 - 0.06),
            (width * 0.5 + 0.065, -height * 0.5 - 0.06),
            (-width * 0.5 - 0.065, height * 0.5 + 0.06),
            (width * 0.5 + 0.065, height * 0.5 + 0.06),
        ):
            if side in {"front", "back"}:
                fasteners.append(((u + du, wall + outward * 0.335, z + dz), (0.060, 0.035, 0.060)))
            else:
                fasteners.append(((wall + outward * 0.335, u + du, z + dz), (0.035, 0.060, 0.060)))
        self._batch_boxes(
            f"{name}:pressure-equalisation-weeps",
            weeps,
            sealant,
            "window-drainage",
            "pressure-equalised-frame-weep-slots",
        )
        self._batch_boxes(
            f"{name}:perimeter-fasteners",
            fasteners,
            self._m("factory_stainless"),
            "window-frame",
            "stainless-window-frame-fasteners",
        )

    def _window_reflection(self, name, side, wall, u, z, width, height):
        for index, dz in enumerate((-0.22, 0.24)):
            self._wall_box(
                side,
                wall,
                u - width * 0.10 + index * width * 0.20,
                z + dz * height,
                width * 0.62,
                0.035,
                0.016,
                self._m("factory_glass_reflection"),
                f"{name}:reflection:{index}",
                offset=0.174,
                bevel=0.0,
                semantic="window-highlight",
                role="glazing-reflection",
            )

    def _ribbon_window(self, name, side, wall, u, z, width, height, modules, *, frame_mat=None, glass_mat=None):
        self._framed_window(
            name,
            side,
            wall,
            u,
            z,
            width,
            height,
            mullions=max(1, modules - 1),
            transoms=0,
            frame_mat=frame_mat,
            glass_mat=glass_mat,
        )

    def _canopy(self, name, side, wall, u, z, width, projection, mat):
        outward = -1 if side in {"front", "left"} else 1
        if side in {"front", "back"}:
            canopy = self._box(name, (u, wall + outward * (projection * 0.5 + 0.16), z), (width, projection, 0.16), mat, "factory-canopy", 0.018, "entrance-canopy")
            for index, du in enumerate((-width * 0.38, width * 0.38)):
                self._between(f"{name}:brace:{index}", (u + du, wall + outward * 0.18, z - 0.04), (u + du, wall + outward * (projection * 0.82), z - 0.46), 0.032, self._m("factory_dark_trim"), "factory-canopy", 12, "canopy-brace")
        else:
            canopy = self._box(name, (wall + outward * (projection * 0.5 + 0.16), u, z), (projection, width, 0.16), mat, "factory-canopy", 0.018, "entrance-canopy")
            for index, du in enumerate((-width * 0.38, width * 0.38)):
                self._between(f"{name}:brace:{index}", (wall + outward * 0.18, u + du, z - 0.04), (wall + outward * (projection * 0.82), u + du, z - 0.46), 0.032, self._m("factory_dark_trim"), "factory-canopy", 12, "canopy-brace")
        return canopy

    def _personnel_door(self, name, side, wall, u, z=1.15, *, width=1.15, height=2.30, mat=None, canopy=False):
        mat = mat or self._m("factory_door_gray")
        self._wall_box(side, wall, u, z, width + 0.30, height + 0.20, 0.11, self._m("factory_dark_trim"), f"{name}:reveal", offset=0.075, bevel=0.014, semantic="door-frame", role="door-reveal")
        self._wall_box(side, wall, u, z, width, height, 0.10, mat, f"{name}:leaf", offset=0.145, bevel=0.016, semantic="door", role="personnel-door")
        self._wall_box(side, wall, u, z + 0.36, width * 0.48, height * 0.28, 0.026, self._m("factory_glass_dark"), f"{name}:vision-panel", offset=0.205, bevel=0.006, semantic="window", role="door-vision-panel")
        self._wall_box(side, wall, u, z - height * 0.5 + 0.16, width - 0.10, 0.28, 0.026, self._m("factory_stainless"), f"{name}:kick-plate", offset=0.212, bevel=0.005, semantic="door-hardware", role="stainless-door-kick-plate")
        self._wall_box(side, wall, u, z - height * 0.5 - 0.035, width + 0.22, 0.075, 0.30, self._m("factory_concrete_dark"), f"{name}:threshold", offset=0.19, bevel=0.008, semantic="door-hardware", role="raised-door-threshold")
        outward = -1 if side in {"front", "left"} else 1
        if side in {"front", "back"}:
            handle = self._cylinder(f"{name}:handle", (u + width * 0.30, wall + outward * 0.225, z - 0.12), 0.025, 0.15, self._m("factory_galvanized"), "door-hardware", 14, "lever-handle")
            handle.rotation_euler[0] = math.radians(90)
        else:
            handle = self._cylinder(f"{name}:handle", (wall + outward * 0.225, u + width * 0.30, z - 0.12), 0.025, 0.15, self._m("factory_galvanized"), "door-hardware", 14, "lever-handle")
            handle.rotation_euler[1] = math.radians(90)
        # Surface closer and articulated arm.
        self._wall_box(side, wall, u + width * 0.18, z + height * 0.5 - 0.16, width * 0.28, 0.105, 0.055, self._m("factory_dark_trim"), f"{name}:closer", offset=0.220, bevel=0.010, semantic="door-hardware", role="hydraulic-door-closer")
        closer_y = wall + outward * 0.255
        if side in {"front", "back"}:
            self._between(f"{name}:closer-arm", (u + width * 0.18, closer_y, z + height * 0.5 - 0.12), (u - width * 0.18, closer_y, z + height * 0.5 + 0.03), 0.014, self._m("factory_stainless"), "door-hardware", 10, "door-closer-arm")
        else:
            self._between(f"{name}:closer-arm", (closer_y, u + width * 0.18, z + height * 0.5 - 0.12), (closer_y, u - width * 0.18, z + height * 0.5 + 0.03), 0.014, self._m("factory_stainless"), "door-hardware", 10, "door-closer-arm")
        if canopy:
            self._canopy(f"{name}:canopy", side, wall, u, z + height * 0.5 + 0.42, width + 1.05, 1.15, self._m("factory_galvanized"))
        self._wall_light(f"{name}:light", side, wall, u + width * 0.72, z + height * 0.46)

    def _roller_door(self, name, side, wall, u, *, width=4.2, height=4.4, z0=0.35, mat=None, blue_header=False, dock=False):
        mat = mat or self._m("factory_door_gray")
        z = z0 + height * 0.5
        self._wall_box(side, wall, u, z, width + 0.48, height + 0.42, 0.14, self._m("factory_dark_trim"), f"{name}:reveal", offset=0.085, bevel=0.018, semantic="loading-door", role="loading-door-reveal")
        self._wall_box(side, wall, u, z, width, height, 0.115, mat, f"{name}:curtain", offset=0.165, bevel=0.012, semantic="loading-door", role="sectional-overhead-door")
        slats = []
        for index, zz in enumerate(self._frange(z0 + 0.22, z0 + height - 0.12, 0.34)):
            outward = -1 if side in {"front", "left"} else 1
            if side in {"front", "back"}:
                slats.append(((u, wall + outward * 0.238, zz), (width - 0.12, 0.030, 0.035)))
            else:
                slats.append(((wall + outward * 0.238, u, zz), (0.030, width - 0.12, 0.035)))
        self._batch_boxes(f"{name}:slats", slats, self._m("factory_galvanized"), "loading-door-detail", "door-horizontal-slats")
        for du in (-width * 0.5 - 0.16, width * 0.5 + 0.16):
            self._wall_box(side, wall, u + du, z, 0.13, height + 0.35, 0.19, self._m("factory_galvanized"), f"{name}:track:{du:+.2f}", offset=0.24, bevel=0.006, semantic="loading-door-detail", role="door-track")
        self._wall_box(side, wall, u, z0 + height + 0.22, width + 0.62, 0.36, 0.33, self._m("factory_galvanized"), f"{name}:coil-hood", offset=0.225, bevel=0.055, semantic="loading-door-detail", role="sectional-door-coil-hood")
        self._wall_box(side, wall, u, z0 + 0.055, width - 0.08, 0.095, 0.17, self._m("factory_sealant"), f"{name}:bottom-seal", offset=0.250, bevel=0.016, semantic="loading-door-detail", role="compressible-door-bottom-seal")
        self._wall_box(side, wall, u + width * 0.32, z0 + 0.72, 0.23, 0.32, 0.060, self._m("factory_stainless"), f"{name}:lock-box", offset=0.275, bevel=0.015, semantic="loading-door-detail", role="roller-door-lock-box")
        track_brackets = []
        outward = -1 if side in {"front", "left"} else 1
        for du in (-width * 0.5 - 0.16, width * 0.5 + 0.16):
            for zz in self._frange(z0 + 0.35, z0 + height - 0.15, 0.62):
                if side in {"front", "back"}:
                    track_brackets.append(((u + du, wall + outward * 0.348, zz), (0.22, 0.055, 0.075)))
                else:
                    track_brackets.append(((wall + outward * 0.348, u + du, zz), (0.055, 0.22, 0.075)))
        self._batch_boxes(f"{name}:track-brackets", track_brackets, self._m("factory_dark_trim"), "loading-door-detail", "bolted-door-track-brackets")
        if blue_header:
            self._wall_box(side, wall, u, z0 + height + 0.36, width + 0.80, 0.34, 0.24, self._m("factory_safety_blue"), f"{name}:blue-header", offset=0.28, bevel=0.014, semantic="factory-accent", role="blue-door-header")
        if dock:
            outward = -1 if side in {"front", "left"} else 1
            if side in {"front", "back"}:
                self._box(f"{name}:dock", (u, wall + outward * 1.25, 0.46), (width + 1.15, 2.20, 0.82), self._m("factory_concrete_dark"), "loading-dock", 0.035, "raised-loading-dock")
                self._box(f"{name}:dock-leveler", (u, wall + outward * 1.38, 0.895), (width - 0.55, 1.52, 0.085), self._m("factory_aluminum"), "loading-dock", 0.018, "serrated-dock-leveler")
                for du in (-width * 0.40, width * 0.40):
                    self._box(f"{name}:bumper:{du:+.2f}", (u + du, wall + outward * 0.34, 0.62), (0.30, 0.24, 0.55), self._m("factory_dark_trim"), "loading-dock", 0.025, "rubber-dock-bumper")
            else:
                self._box(f"{name}:dock", (wall + outward * 1.25, u, 0.46), (2.20, width + 1.15, 0.82), self._m("factory_concrete_dark"), "loading-dock", 0.035, "raised-loading-dock")
        self._wall_light(f"{name}:light", side, wall, u, z0 + height + 0.60)

    def _wall_light(self, name, side, wall, u, z):
        self._wall_box(side, wall, u, z, 0.34, 0.19, 0.22, self._m("factory_dark_trim"), f"{name}:housing", offset=0.24, bevel=0.022, semantic="factory-light", role="wall-pack-light")
        self._wall_box(side, wall, u, z - 0.035, 0.24, 0.11, 0.025, self._m("factory_lamp"), f"{name}:lens", offset=0.365, bevel=0.018, semantic="factory-light", role="wall-pack-lens")

    def _parapet(self, name, width, depth, z, mat):
        self._box(f"{name}:front", (0, -depth * 0.5, z), (width + 0.35, 0.32, 0.62), mat, "factory-roof", 0.022, "parapet")
        self._box(f"{name}:back", (0, depth * 0.5, z), (width + 0.35, 0.32, 0.62), mat, "factory-roof", 0.022, "parapet")
        self._box(f"{name}:left", (-width * 0.5, 0, z), (0.32, depth, 0.62), mat, "factory-roof", 0.022, "parapet")
        self._box(f"{name}:right", (width * 0.5, 0, z), (0.32, depth, 0.62), mat, "factory-roof", 0.022, "parapet")
        coping = self._m("factory_galvanized")
        self._box(f"{name}:coping-front", (0, -depth * 0.5 - 0.02, z + 0.33), (width + 0.52, 0.40, 0.09), coping, "factory-roof-detail", 0.016, "metal-coping")
        self._box(f"{name}:coping-back", (0, depth * 0.5 + 0.02, z + 0.33), (width + 0.52, 0.40, 0.09), coping, "factory-roof-detail", 0.016, "metal-coping")
        self._box(f"{name}:coping-left", (-width * 0.5 - 0.02, 0, z + 0.33), (0.40, depth, 0.09), coping, "factory-roof-detail", 0.016, "metal-coping")
        self._box(f"{name}:coping-right", (width * 0.5 + 0.02, 0, z + 0.33), (0.40, depth, 0.09), coping, "factory-roof-detail", 0.016, "metal-coping")

    def _rooftop_hvac(self, name, loc, scale=1.0, mat=None):
        mat = mat or self._m("factory_galvanized")
        x, y, z = loc
        self._box(f"{name}:curb", (x, y, z + 0.10 * scale), (2.0 * scale, 1.45 * scale, 0.20 * scale), self._m("factory_dark_trim"), "rooftop-equipment", 0.018, "hvac-roof-curb")
        self._box(f"{name}:cabinet", (x, y, z + 0.70 * scale), (1.82 * scale, 1.28 * scale, 1.06 * scale), mat, "rooftop-equipment", 0.045, "packaged-hvac-unit")
        for index, offset in enumerate((-0.32, -0.10, 0.12, 0.34)):
            self._box(f"{name}:louver:{index}", (x - 0.92 * scale, y + offset * scale, z + 0.73 * scale), (0.035 * scale, 0.12 * scale, 0.54 * scale), self._m("factory_dark_trim"), "rooftop-equipment", 0.004, "hvac-louver")
        fan = self._cylinder(f"{name}:fan", (x + 0.26 * scale, y, z + 1.25 * scale), 0.36 * scale, 0.085 * scale, self._m("factory_dark_trim"), "rooftop-equipment", 28, "hvac-condenser-fan")
        fan.rotation_euler[2] = self.rng.uniform(0, math.tau)
        for index in range(6):
            angle = index * math.tau / 6
            self._between(f"{name}:fan-blade:{index}", (x + 0.26 * scale, y, z + 1.30 * scale), (x + 0.26 * scale + math.cos(angle) * 0.28 * scale, y + math.sin(angle) * 0.28 * scale, z + 1.30 * scale), 0.026 * scale, self._m("factory_galvanized"), "rooftop-equipment", 8, "fan-blade")

    def _roof_vent(self, name, loc, height=1.10, radius=0.18):
        x, y, z = loc
        self._cylinder(f"{name}:stack", (x, y, z + height * 0.45), radius, height * 0.90, self._m("factory_galvanized"), "rooftop-equipment", 20, "vent-stack")
        self._cylinder(f"{name}:collar", (x, y, z + 0.09), radius * 1.65, 0.18, self._m("factory_dark_trim"), "rooftop-equipment", 24, "vent-flashing")
        self._cylinder(f"{name}:cap", (x, y, z + height), radius * 1.36, 0.10, self._m("factory_dark_trim"), "rooftop-equipment", 24, "vent-rain-cap")

    def _gutter_and_downspouts(
        self,
        name,
        width,
        depth,
        eave,
        mat,
        *,
        count=5,
        front_exclusions=(),
    ):
        for side in (-1, 1):
            gutter = self._cylinder(f"{name}:gutter:{side}", (0, side * (depth * 0.5 + 0.53), eave - 0.05), 0.085, width + 1.05, mat, "factory-drainage", 18, "half-round-gutter")
            gutter.rotation_euler[1] = math.radians(90)
            for index, x in enumerate(self._frange(-width * 0.5 + 1.5, width * 0.5 - 1.0, max(1.0, (width - 2.5) / max(1, count - 1)))):
                if side < 0 and any(low <= x <= high for low, high in front_exclusions):
                    continue
                self._cylinder(f"{name}:downspout:{side}:{index}", (x, side * (depth * 0.5 + 0.56), eave * 0.5), 0.055, eave - 0.38, mat, "factory-drainage", 14, "downspout")
                self._between(f"{name}:downspout-elbow:{side}:{index}", (x, side * (depth * 0.5 + 0.56), 0.28), (x, side * (depth * 0.5 + 0.90), 0.13), 0.055, mat, "factory-drainage", 14, "downspout-elbow")

    def _bollards(self, name, positions, *, height=1.00, radius=0.09, mat=None):
        mat = mat or self._m("factory_safety_yellow")
        for index, (x, y) in enumerate(positions):
            self._cylinder(f"{name}:{index}", (x, y, height * 0.5), radius, height, mat, "safety-bollard", 20, "safety-bollard")
            self._cylinder(f"{name}:cap:{index}", (x, y, height), radius * 1.02, 0.055, self._m("factory_dark_trim"), "safety-bollard", 20, "bollard-cap")

    def _site_pad(self, name, width, depth, *, front_extension=10.0, mat=None):
        mat = mat or self._m("factory_concrete")
        self._box(f"site:{name}:subbase", (0, -front_extension * 0.5, -0.12), (width + 5.0, depth + front_extension + 4.0, 0.24), self._m("factory_concrete_dark"), "factory-site", 0.06, "compacted-site-subbase")
        self._box(f"site:{name}:paving", (0, -front_extension * 0.5, 0.015), (width + 4.4, depth + front_extension + 3.4, 0.12), mat, "factory-site", 0.04, "industrial-yard-paving")
        seams = []
        total_depth = depth + front_extension + 3.0
        for x in self._frange(-width * 0.5 - 1.5, width * 0.5 + 1.5, 4.0):
            seams.append(((x, -front_extension * 0.5, 0.085), (0.024, total_depth, 0.010)))
        for y in self._frange(-depth * 0.5 - front_extension + 1.0, depth * 0.5 + 1.0, 4.0):
            seams.append(((0, y, 0.086), (width + 3.6, 0.024, 0.010)))
        self._batch_boxes(f"site:{name}:expansion-joints", seams, self._m("factory_concrete_dark"), "factory-site-detail", "concrete-expansion-joints")

    def _hedge(self, name, start, end, width=0.75, height=0.80):
        start_v = Vector((*start,))
        end_v = Vector((*end,))
        direction = end_v - start_v
        length = max(0.01, direction.length)
        tangent = direction.normalized()
        normal = Vector((-tangent.y, tangent.x, 0))
        segments = max(8, int(length / 0.46))
        vertices = []
        section_tops = []
        for index in range(segments + 1):
            t = index / segments
            center = start_v.lerp(end_v, t)
            wobble = normal * (0.025 * math.sin(index * 1.93) + self.rng.uniform(-0.012, 0.012))
            center += wobble
            half_width = width * (0.48 + self.rng.uniform(-0.025, 0.025))
            top = height + self.rng.uniform(-0.035, 0.035)
            section_tops.append(top)
            left = center - normal * half_width
            right = center + normal * half_width
            vertices.extend(
                [
                    (left.x, left.y, 0.075),
                    (right.x, right.y, 0.075),
                    (right.x, right.y, top),
                    (left.x, left.y, top),
                ]
            )
        faces = []
        for index in range(segments):
            a = index * 4
            b = (index + 1) * 4
            faces.extend(
                [
                    (a, b, b + 1, a + 1),
                    (a + 1, b + 1, b + 2, a + 2),
                    (a + 2, b + 2, b + 3, a + 3),
                    (a + 3, b + 3, b, a),
                ]
            )
        faces.extend([(0, 1, 2, 3), (segments * 4 + 3, segments * 4 + 2, segments * 4 + 1, segments * 4)])
        self._mesh(f"landscape:{name}:clipped-core", vertices, faces, self._m("factory_hedge_dark"), "hedge", smooth=False, role="professionally-clipped-hedge-core")

        for index in range(1, segments, max(2, int(1.4 / max(length / segments, 0.01)))):
            center = start_v.lerp(end_v, index / segments)
            self._between(
                f"landscape:{name}:branch:{index}",
                (center.x, center.y, 0.08),
                (center.x + normal.x * 0.08, center.y + normal.y * 0.08, section_tops[index] * 0.72),
                0.018,
                self._m("factory_rust"),
                "hedge-branch",
                8,
                "woody-hedge-branch",
            )

        leaf_specs = [[], []]
        for index in range(max(120, int(length * 38))):
            t = self.rng.random()
            center = start_v.lerp(end_v, t)
            section_index = min(segments, int(t * segments))
            surface = self.rng.random()
            if surface < 0.58:
                lateral = (-1 if self.rng.random() < 0.5 else 1) * width * self.rng.uniform(0.45, 0.56)
                z = self.rng.uniform(0.10, section_tops[section_index])
            else:
                lateral = self.rng.uniform(-width * 0.52, width * 0.52)
                z = section_tops[section_index] + self.rng.uniform(-0.025, 0.075)
            px = center.x + normal.x * lateral
            py = center.y + normal.y * lateral
            size = self.rng.uniform(0.038, 0.082)
            angle = self.rng.uniform(0, math.tau)
            tilt = self.rng.uniform(0.015, 0.070)
            base = len(leaf_specs[index % 2])
            _ = base
            leaf_specs[index % 2].append((px, py, z, size, angle, tilt))
        for bucket, specs in enumerate(leaf_specs):
            verts = []
            quads = []
            for px, py, pz, size, angle, tilt in specs:
                tangent_leaf = Vector((math.cos(angle), math.sin(angle), tilt)).normalized()
                cross = Vector((-math.sin(angle), math.cos(angle), 0.18)).normalized()
                base = len(verts)
                verts.extend(
                    [
                        tuple(Vector((px, py, pz)) - tangent_leaf * size),
                        tuple(Vector((px, py, pz)) + cross * size * 0.42),
                        tuple(Vector((px, py, pz)) + tangent_leaf * size),
                        tuple(Vector((px, py, pz)) - cross * size * 0.42),
                    ]
                )
                quads.append((base, base + 1, base + 2, base + 3))
            self._mesh(f"landscape:{name}:leaves:{bucket}", verts, quads, self._m("factory_hedge_mid" if bucket == 0 else "factory_hedge_light"), "hedge-leaf", smooth=False, role="individual-hedge-leaves")

    def _masonry_wall(self, name, start_x, end_x, y, *, height=2.70, thickness=0.48):
        """Detailed plastered masonry boundary wall with courses and pilasters."""
        center_x = (start_x + end_x) * 0.5
        length = abs(end_x - start_x)
        self._box(f"{name}:core", (center_x, y, height * 0.5), (length, thickness, height), self._m("factory_masonry_tan"), "factory-boundary", 0.022, "reinforced-masonry-security-wall")
        self._box(f"{name}:base-course", (center_x, y, 0.18), (length + 0.06, thickness + 0.08, 0.36), self._m("factory_concrete_dark"), "factory-boundary", 0.014, "masonry-wall-concrete-base")
        self._box(f"{name}:coping", (center_x, y, height + 0.08), (length + 0.18, thickness + 0.18, 0.16), self._m("factory_aluminum"), "factory-boundary", 0.018, "sloped-metal-wall-coping")
        joints = []
        for z in self._frange(0.52, height - 0.20, 0.42):
            joints.extend(
                [
                    ((center_x, y - thickness * 0.5 - 0.012, z), (length - 0.12, 0.020, 0.025)),
                    ((center_x, y + thickness * 0.5 + 0.012, z), (length - 0.12, 0.020, 0.025)),
                ]
            )
        course = 0
        for z in self._frange(0.73, height - 0.24, 0.84):
            offset = 0.62 if course % 2 else 0.0
            x = min(start_x, end_x) + 1.20 + offset
            while x < max(start_x, end_x) - 0.50:
                joints.extend(
                    [
                        ((x, y - thickness * 0.5 - 0.014, z), (0.025, 0.022, 0.37)),
                        ((x, y + thickness * 0.5 + 0.014, z), (0.025, 0.022, 0.37)),
                    ]
                )
                x += 1.24
            course += 1
        self._batch_boxes(f"{name}:mortar-joints", joints, self._m("factory_mortar"), "factory-boundary-detail", "masonry-control-and-mortar-joints")
        pilaster_specs = []
        count = max(2, int(length / 4.2))
        for index in range(count + 1):
            x = min(start_x, end_x) + length * index / count
            pilaster_specs.append(((x, y, height * 0.5 + 0.03), (0.52, thickness + 0.20, height + 0.06)))
        self._batch_boxes(f"{name}:pilasters", pilaster_specs, self._m("factory_masonry_tan"), "factory-boundary", "masonry-wall-pilasters")
        cap_specs = [((loc[0], y, height + 0.15), (0.66, thickness + 0.34, 0.14)) for loc, _dims in pilaster_specs]
        self._batch_boxes(f"{name}:pilaster-caps", cap_specs, self._m("factory_aluminum"), "factory-boundary-detail", "pilaster-weather-caps")

    def _security_fence(self, name, start, end, *, height=2.10, spacing=0.18, mat=None):
        mat = mat or self._m("factory_dark_trim")
        start_v = Vector((*start,))
        end_v = Vector((*end,))
        direction = end_v - start_v
        length = direction.length
        if length <= 1e-6:
            return
        tangent = direction.normalized()
        picket_count = max(3, int(math.ceil(length / spacing)))
        pickets = []
        spear_positions = []
        for index in range(picket_count + 1):
            p = start_v.lerp(end_v, index / picket_count)
            pickets.append(((p.x, p.y, height * 0.5), (0.036, 0.036, height)))
            spear_positions.append(p)
        self._batch_boxes(f"{name}:pickets", pickets, mat, "security-fence", "dense-square-security-pickets")

        post_count = max(1, int(math.ceil(length / 2.35)))
        posts = []
        bases = []
        caps = []
        for index in range(post_count + 1):
            p = start_v.lerp(end_v, index / post_count)
            posts.append(((p.x, p.y, (height + 0.22) * 0.5), (0.115, 0.115, height + 0.22)))
            bases.append(((p.x, p.y, 0.055), (0.28, 0.28, 0.11)))
            caps.append(((p.x, p.y, height + 0.23), (0.16, 0.16, 0.08)))
        self._batch_boxes(f"{name}:posts", posts, self._m("factory_galvanized"), "security-fence", "galvanized-square-fence-posts")
        self._batch_boxes(f"{name}:post-bases", bases, self._m("factory_dark_trim"), "security-fence-detail", "bolted-fence-post-baseplates")
        self._batch_boxes(f"{name}:post-caps", caps, self._m("factory_stainless"), "security-fence-detail", "weatherproof-fence-post-caps")
        for rail_index, z in enumerate((0.34, height - 0.32)):
            self._rect_between(f"{name}:rail:{rail_index}", (start_v.x, start_v.y, z), (end_v.x, end_v.y, z), (0.070, 0.055), mat, "security-fence", "rectangular-fence-horizontal-rail", bevel=0.006)

        spear_verts = []
        spear_faces = []
        half = 0.045
        for p in spear_positions:
            base = len(spear_verts)
            spear_verts.extend(
                [
                    (p.x - half, p.y - half, height),
                    (p.x + half, p.y - half, height),
                    (p.x + half, p.y + half, height),
                    (p.x - half, p.y + half, height),
                    (p.x, p.y, height + 0.15),
                ]
            )
            spear_faces.extend(
                [
                    (base, base + 1, base + 4),
                    (base + 1, base + 2, base + 4),
                    (base + 2, base + 3, base + 4),
                    (base + 3, base, base + 4),
                    (base + 3, base + 2, base + 1, base),
                ]
            )
        self._mesh(f"{name}:anti-climb-spears", spear_verts, spear_faces, mat, "security-fence-detail", role="formed-anti-climb-spearheads")

        for index in (0, post_count):
            p = start_v.lerp(end_v, index / post_count)
            inset = p + tangent * (0.72 if index == 0 else -0.72)
            self._rect_between(f"{name}:end-brace:{index}", (p.x, p.y, 0.28), (inset.x, inset.y, height - 0.36), (0.055, 0.045), self._m("factory_galvanized"), "security-fence-detail", "fence-end-diagonal-brace", bevel=0.006)

    def _accordion_gate(self, name, center_x, y, width, height=2.18):
        """Full-width powered telescopic gate with arched frames and running gear."""
        left = center_x - width * 0.5
        right = center_x + width * 0.5
        panels = max(10, int(math.ceil(width / 1.05)))
        step = width / panels
        gate_mat = self._m("factory_dark_trim")
        self._box(f"{name}:ground-track", (center_x, y, 0.035), (width + 1.2, 0.095, 0.070), self._m("factory_stainless"), "security-gate-detail", 0.008, "stainless-retractable-gate-track")
        track_fasteners = [((left - 0.35 + index * 0.72, y, 0.080), (0.075, 0.075, 0.035)) for index in range(int((width + 0.7) / 0.72) + 1)]
        self._batch_boxes(f"{name}:track-fasteners", track_fasteners, self._m("factory_dark_trim"), "security-gate-detail", "gate-track-anchor-bolts")
        self._rect_between(f"{name}:bottom", (left, y, 0.22), (right, y, 0.22), (0.075, 0.070), gate_mat, "security-gate", "gate-bottom-box-rail", bevel=0.008)
        self._rect_between(f"{name}:mid", (left, y, height * 0.56), (right, y, height * 0.56), (0.060, 0.055), gate_mat, "security-gate", "gate-mid-box-rail", bevel=0.006)
        for index in range(panels + 1):
            x = left + index * step
            self._box(f"{name}:post:{index}", (x, y, height * 0.5), (0.065, 0.065, height), gate_mat, "security-gate", 0.008, "telescopic-gate-upright")
            self._box(f"{name}:post-collar:{index}", (x, y, height * 0.56), (0.105, 0.095, 0.13), self._m("factory_stainless"), "security-gate-detail", 0.010, "gate-upright-slide-collar")
            if index < panels:
                self._rect_between(f"{name}:brace-up:{index}", (x, y - 0.025, 0.28), (x + step, y - 0.025, height * 0.56 - 0.05), (0.032, 0.025), self._m("factory_galvanized"), "security-gate", "double-scissor-gate-brace", bevel=0.004)
                self._rect_between(f"{name}:brace-down:{index}", (x, y + 0.025, height * 0.56 - 0.05), (x + step, y + 0.025, 0.28), (0.032, 0.025), self._m("factory_galvanized"), "security-gate", "double-scissor-gate-brace", bevel=0.004)
                arch_base = height * 0.72
                arch_peak = height + 0.13
                arch_points = [
                    (x, y, arch_base),
                    (x + step * 0.25, y, arch_base + (arch_peak - arch_base) * 0.72),
                    (x + step * 0.50, y, arch_peak),
                    (x + step * 0.75, y, arch_base + (arch_peak - arch_base) * 0.72),
                    (x + step, y, arch_base),
                ]
                for arc_index in range(len(arch_points) - 1):
                    self._between(f"{name}:arched-crown:{index}:{arc_index}", arch_points[arc_index], arch_points[arc_index + 1], 0.023, self._m("factory_galvanized"), "security-gate-detail", 10, "formed-arched-gate-crown")
            if index % 2 == 0 or index in {0, panels}:
                self._box(f"{name}:caster-fork-left:{index}", (x - 0.055, y, 0.115), (0.032, 0.16, 0.22), gate_mat, "security-gate-detail", 0.006, "gate-caster-fork")
                self._box(f"{name}:caster-fork-right:{index}", (x + 0.055, y, 0.115), (0.032, 0.16, 0.22), gate_mat, "security-gate-detail", 0.006, "gate-caster-fork")
                wheel = self._cylinder(f"{name}:wheel:{index}", (x, y, 0.09), 0.095, 0.105, self._m("factory_shadow"), "security-gate-detail", 18, "rubber-bearing-gate-caster")
                wheel.rotation_euler[0] = math.radians(90)
                hub = self._cylinder(f"{name}:wheel-hub:{index}", (x, y - 0.06, 0.09), 0.030, 0.13, self._m("factory_stainless"), "security-gate-detail", 16, "gate-caster-bearing-hub")
                hub.rotation_euler[0] = math.radians(90)

        # Slender steel guide posts replace the two oversized yellow entrance
        # piers from the previous result.
        for label, x in (("left", left - 0.22), ("right", right + 0.22)):
            self._box(f"{name}:guide-post:{label}", (x, y, (height + 0.34) * 0.5), (0.16, 0.22, height + 0.34), self._m("factory_dark_trim"), "security-gate-detail", 0.012, "slender-steel-gate-guide-post")
            self._box(f"{name}:guide-base:{label}", (x, y, 0.065), (0.42, 0.46, 0.13), self._m("factory_stainless"), "security-gate-detail", 0.012, "gate-guide-baseplate")
            self._box(f"{name}:guide-cap:{label}", (x, y, height + 0.38), (0.22, 0.28, 0.10), self._m("factory_stainless"), "security-gate-detail", 0.014, "gate-guide-weather-cap")

        drive_x = right + 0.85
        self._box(f"{name}:drive:plinth", (drive_x, y + 0.05, 0.10), (0.92, 0.70, 0.20), self._m("factory_concrete_dark"), "security-gate-equipment", 0.028, "gate-drive-concrete-plinth")
        self._box(f"{name}:drive:cabinet", (drive_x, y + 0.05, 0.72), (0.72, 0.54, 1.04), self._m("factory_galvanized"), "security-gate-equipment", 0.050, "powered-gate-drive-cabinet")
        self._box(f"{name}:drive:door", (drive_x, y - 0.235, 0.72), (0.58, 0.035, 0.84), self._m("factory_aluminum"), "security-gate-equipment", 0.018, "gate-drive-service-door")
        for index, z in enumerate((0.50, 0.62, 0.74, 0.86)):
            self._box(f"{name}:drive:louver:{index}", (drive_x, y - 0.265, z), (0.38, 0.035, 0.035), self._m("factory_dark_trim"), "security-gate-equipment", 0.005, "gate-drive-ventilation-louver")
        stop = self._cylinder(f"{name}:drive:emergency-stop", (drive_x + 0.20, y - 0.31, 1.02), 0.065, 0.055, self._m("factory_warning_red"), "security-gate-equipment", 20, "gate-emergency-stop")
        stop.rotation_euler[0] = math.radians(90)

    def _flat_roof(self, name, center, dims, mat=None):
        x, y, z = center
        width, depth, thickness = dims
        self._box(name, (x, y, z), dims, mat or self._m("factory_roof_zinc"), "factory-roof", 0.028, "insulated-flat-roof")
        # Closely spaced roofing laps catch long grazing highlights without
        # requiring a displacement-heavy roof mesh.
        laps = []
        for lx in self._frange(x - width * 0.5 + 0.55, x + width * 0.5 - 0.35, 1.10):
            laps.append(((lx, y, z + thickness * 0.52), (0.035, depth - 0.30, 0.035)))
        self._batch_boxes(f"{name}:membrane-laps", laps, self._m("factory_galvanized"), "factory-roof-detail", "roof-membrane-laps")

    def _panel_grid(self, name, side, wall, span, height, *, x_spacing, z_spacing, mat, offset=0.080, center_u=0.0):
        outward = -1 if side in {"front", "left"} else 1
        specs = []
        for u in self._frange(center_u - span * 0.5 + x_spacing, center_u + span * 0.5 - 0.01, x_spacing):
            if side in {"front", "back"}:
                specs.append(((u, wall + outward * offset, height * 0.5), (0.028, 0.030, height - 0.20)))
            else:
                specs.append(((wall + outward * offset, u, height * 0.5), (0.030, 0.028, height - 0.20)))
        for z in self._frange(z_spacing, height - 0.05, z_spacing):
            if side in {"front", "back"}:
                specs.append(((center_u, wall + outward * offset, z), (span - 0.10, 0.030, 0.028)))
            else:
                specs.append(((wall + outward * offset, center_u, z), (0.030, span - 0.10, 0.028)))
        self._batch_boxes(name, specs, mat, "factory-cladding-detail", "architectural-panel-grid")

    def _facade_fastener_grid(
        self,
        name,
        side,
        wall,
        u_values,
        z_values,
        *,
        offset=0.19,
        mat=None,
    ):
        """Add visible gasketed fasteners at panel-grid intersections."""
        mat = mat or self._m("factory_stainless")
        outward = -1 if side in {"front", "left"} else 1
        specs = []
        for u in u_values:
            for z in z_values:
                if side in {"front", "back"}:
                    specs.append(((u, wall + outward * offset, z), (0.055, 0.032, 0.055)))
                else:
                    specs.append(((wall + outward * offset, u, z), (0.032, 0.055, 0.055)))
        self._batch_boxes(name, specs, mat, "factory-cladding-detail", "gasketed-panel-fasteners")

    def _facade_steel_column(self, name, side, wall, u, height, *, width=0.34, mat=None):
        """Expressed facade column with flange, web, base plate and brackets."""
        mat = mat or self._m("factory_galvanized")
        self._wall_box(side, wall, u, height * 0.5, width, height - 0.22, 0.12, mat, f"{name}:front-flange", offset=0.24, bevel=0.012, semantic="factory-structure", role="steel-column-front-flange")
        self._wall_box(side, wall, u, height * 0.5, width * 0.34, height - 0.16, 0.34, self._m("factory_dark_trim"), f"{name}:web", offset=0.20, bevel=0.008, semantic="factory-structure", role="steel-column-web")
        self._wall_box(side, wall, u, 0.18, width + 0.32, 0.20, 0.42, self._m("factory_stainless"), f"{name}:base-plate", offset=0.25, bevel=0.012, semantic="factory-structure", role="bolted-column-baseplate")
        self._wall_box(side, wall, u, height - 0.18, width + 0.22, 0.24, 0.30, mat, f"{name}:head-plate", offset=0.26, bevel=0.010, semantic="factory-structure", role="column-head-connection-plate")
        for index, (du, dz) in enumerate(((-width * 0.56, 0.18), (width * 0.56, 0.18), (-width * 0.56, 0.31), (width * 0.56, 0.31))):
            self._wall_box(side, wall, u + du, dz, 0.070, 0.070, 0.055, self._m("factory_shadow"), f"{name}:anchor:{index}", offset=0.49, bevel=0.012, semantic="factory-structure", role="column-anchor-bolt-head")
        for index, du in enumerate((-width * 0.48, width * 0.48)):
            self._wall_box(side, wall, u + du, height - 0.52, 0.095, 0.48, 0.23, mat, f"{name}:head-bracket:{index}", offset=0.29, bevel=0.008, semantic="factory-structure", role="column-head-gusset-bracket")

    def _service_conduit(self, name, side, wall, u, z0, z1, *, branch=1.45):
        """Exterior electrical conduit run with clamps and weatherproof box."""
        outward = -1 if side in {"front", "left"} else 1
        coord = wall + outward * 0.31
        if side in {"front", "back"}:
            self._cylinder(f"{name}:vertical", (u, coord, (z0 + z1) * 0.5), 0.035, z1 - z0, self._m("factory_aluminum"), "factory-utility", 14, "rigid-metal-electrical-conduit")
            self._between(f"{name}:horizontal", (u, coord, z1), (u + branch, coord, z1), 0.035, self._m("factory_aluminum"), "factory-utility", 14, "rigid-metal-electrical-conduit")
        else:
            self._cylinder(f"{name}:vertical", (coord, u, (z0 + z1) * 0.5), 0.035, z1 - z0, self._m("factory_aluminum"), "factory-utility", 14, "rigid-metal-electrical-conduit")
            self._between(f"{name}:horizontal", (coord, u, z1), (coord, u + branch, z1), 0.035, self._m("factory_aluminum"), "factory-utility", 14, "rigid-metal-electrical-conduit")
        for index, z in enumerate(self._frange(z0 + 0.25, z1 - 0.12, 0.62)):
            self._wall_box(side, wall, u, z, 0.14, 0.055, 0.075, self._m("factory_dark_trim"), f"{name}:clamp:{index}", offset=0.335, bevel=0.006, semantic="factory-utility", role="conduit-wall-clamp")
        self._wall_box(side, wall, u, z0 + 0.36, 0.42, 0.52, 0.18, self._m("factory_galvanized"), f"{name}:junction-box", offset=0.22, bevel=0.025, semantic="factory-utility", role="weatherproof-electrical-junction-box")
        self._wall_box(side, wall, u, z0 + 0.36, 0.30, 0.40, 0.025, self._m("factory_aluminum"), f"{name}:junction-cover", offset=0.42, bevel=0.015, semantic="factory-utility", role="junction-box-gasketed-cover")

    def _flat_skylight(self, name, loc, dims):
        """Curb-mounted industrial skylight with separated glazing and cap rails."""
        x, y, z = loc
        width, depth = dims
        self._box(f"{name}:curb", (x, y, z + 0.11), (width + 0.30, depth + 0.30, 0.22), self._m("factory_dark_trim"), "factory-roof-equipment", 0.018, "insulated-skylight-curb")
        self._box(f"{name}:glazing", (x, y, z + 0.26), (width, depth, 0.095), self._m("factory_glass_dark"), "factory-roof-equipment", 0.022, "laminated-industrial-skylight")
        for label, lx, ly, sx, sy in (
            ("front", x, y - depth * 0.5, width + 0.18, 0.07),
            ("back", x, y + depth * 0.5, width + 0.18, 0.07),
            ("left", x - width * 0.5, y, 0.07, depth + 0.18),
            ("right", x + width * 0.5, y, 0.07, depth + 0.18),
        ):
            self._box(f"{name}:cap-rail:{label}", (lx, ly, z + 0.33), (sx, sy, 0.075), self._m("factory_aluminum"), "factory-roof-detail", 0.010, "skylight-pressure-cap-rail")

    def _industrial_louver(self, name, side, wall, u, z, width, height):
        self._wall_box(side, wall, u, z, width + 0.18, height + 0.18, 0.10, self._m("factory_dark_trim"), f"{name}:reveal", offset=0.10, bevel=0.010, semantic="factory-vent", role="louver-reveal")
        slats = []
        outward = -1 if side in {"front", "left"} else 1
        for index, zz in enumerate(self._frange(z - height * 0.5 + 0.10, z + height * 0.5 - 0.05, 0.15)):
            if side in {"front", "back"}:
                slats.append(((u, wall + outward * 0.18, zz), (width, 0.10, 0.055)))
            else:
                slats.append(((wall + outward * 0.18, u, zz), (0.10, width, 0.055)))
        self._batch_boxes(f"{name}:slats", slats, self._m("factory_galvanized"), "factory-vent", "weather-louver-blades")

    def _fire_ladder(self, name, x, y, z0, z1, *, side="front"):
        outward_axis = (0, -1, 0) if side == "front" else (-1, 0, 0)
        if side == "front":
            self._between(f"{name}:rail-left", (x - 0.33, y, z0), (x - 0.33, y, z1), 0.030, self._m("factory_galvanized"), "factory-access", 10, "fixed-ladder-rail")
            self._between(f"{name}:rail-right", (x + 0.33, y, z0), (x + 0.33, y, z1), 0.030, self._m("factory_galvanized"), "factory-access", 10, "fixed-ladder-rail")
            for index, z in enumerate(self._frange(z0 + 0.22, z1 - 0.15, 0.30)):
                self._between(f"{name}:rung:{index}", (x - 0.33, y, z), (x + 0.33, y, z), 0.024, self._m("factory_galvanized"), "factory-access", 10, "fixed-ladder-rung")
        else:
            self._between(f"{name}:rail-left", (x, y - 0.33, z0), (x, y - 0.33, z1), 0.030, self._m("factory_galvanized"), "factory-access", 10, "fixed-ladder-rail")
            self._between(f"{name}:rail-right", (x, y + 0.33, z0), (x, y + 0.33, z1), 0.030, self._m("factory_galvanized"), "factory-access", 10, "fixed-ladder-rail")
            for index, z in enumerate(self._frange(z0 + 0.22, z1 - 0.15, 0.30)):
                self._between(f"{name}:rung:{index}", (x, y - 0.33, z), (x, y + 0.33, z), 0.024, self._m("factory_galvanized"), "factory-access", 10, "fixed-ladder-rung")
        _ = outward_axis

    def _build_gable_clerestory(self):
        width, depth, ridge = FACTORY_DIMENSIONS["gable_clerestory"]
        eave = 8.60
        front = -depth * 0.5
        back = depth * 0.5
        left = -width * 0.5
        right = width * 0.5
        if self.include_site:
            self._site_pad("gable-clerestory", width, depth, front_extension=10.5)

        self._box("shell:foundation-plinth", (0, 0, 0.34), (width + 0.30, depth + 0.30, 0.68), self._m("factory_concrete_dark"), "factory-foundation", 0.035, "reinforced-concrete-plinth")
        self._box("shell:corrugated-hall", (0, 0, eave * 0.5 + 0.28), (width, depth, eave - 0.56), self._m("factory_beige_panel"), "factory-building", 0.030, "steel-frame-workshop-shell")
        for side, wall, span in (("front", front, width), ("back", back, width), ("left", left, depth), ("right", right, depth)):
            self._panel_ribs(f"cladding:ribs:{side}", side, wall, span, eave - 0.78, self._m("factory_beige_panel_light"), spacing=0.46, z0=0.50)
            self._panel_joints(f"cladding:joints:{side}", side, wall, span, (2.25, 4.35, 6.45, 8.22), self._m("factory_galvanized"))
            self._facade_fastener_grid(
                f"cladding:fasteners:{side}",
                side,
                wall,
                self._frange(-span * 0.5 + 0.55, span * 0.5 - 0.45, 2.30),
                (0.78, 2.25, 4.35, 6.45, 8.18),
                offset=0.205,
            )
        self._wall_box("front", front, 0, 0.83, width - 0.28, 0.92, 0.18, self._m("factory_concrete"), "front:precast-wainscot", offset=0.14, bevel=0.012, semantic="factory-foundation", role="precast-concrete-wainscot")
        self._wall_box("back", back, 0, 0.83, width - 0.28, 0.92, 0.18, self._m("factory_concrete"), "back:precast-wainscot", offset=0.14, bevel=0.012, semantic="factory-foundation", role="precast-concrete-wainscot")
        self._wall_box("front", front, 0, eave - 0.22, width + 0.30, 0.38, 0.31, self._m("factory_aluminum"), "front:eave-fascia", offset=0.19, bevel=0.012, semantic="factory-roof-detail", role="deep-formed-eave-fascia")
        self._wall_box("back", back, 0, eave - 0.22, width + 0.30, 0.38, 0.31, self._m("factory_aluminum"), "back:eave-fascia", offset=0.19, bevel=0.012, semantic="factory-roof-detail", role="deep-formed-eave-fascia")
        for side, wall, span in (("front", front, width), ("back", back, width)):
            for index, u in enumerate((-span * 0.5 + 0.18, span * 0.5 - 0.18)):
                self._facade_steel_column(f"{side}:corner-column:{index}", side, wall, u, eave - 0.18, width=0.28, mat=self._m("factory_aluminum"))
        self._gable_end("shell:gable-left", left, depth, eave, ridge, self._m("factory_beige_panel"))
        self._gable_end("shell:gable-right", right, depth, eave, ridge, self._m("factory_beige_panel"))
        self._roof_slope("roof:front-slope", width, depth, eave, ridge, -1, self._m("factory_roof_zinc"))
        self._roof_slope("roof:back-slope", width, depth, eave, ridge, 1, self._m("factory_roof_zinc"))
        self._architectural_standing_seam_roof(
            "roof:architectural-envelope",
            width,
            depth,
            eave,
            ridge,
            1.18,
            self._m("factory_roof_zinc"),
        )
        walkway_y = -2.15
        walkway_z = (
            ridge
            - (ridge - eave) * (abs(walkway_y) / (depth * 0.5))
            + 0.16
        )
        self._roof_service_walkway(
            "roof:mechanical-service-walkway",
            6.5,
            20.5,
            walkway_y,
            walkway_z,
        )
        # The sign occupies local X [-21.8, -12.2].  Routing the front gutter
        # outlet away from that interval removes the pipe/column that obscured
        # the raised lettering while preserving five functional front drops.
        self._gutter_and_downspouts(
            "drainage",
            width,
            depth,
            eave,
            self._m("factory_galvanized"),
            count=6,
            front_exclusions=((-22.25, -11.75),),
        )

        # Reference-defining clerestory: two long strips with visible mullions,
        # separated by a shallow service/entrance projection.
        self._deep_igu_window(
            "front:clerestory-west",
            "front",
            front,
            -12.4,
            6.68,
            25.8,
            1.25,
            mullions=11,
            frame_mat=self._m("factory_aluminum"),
        )
        self._deep_igu_window(
            "front:clerestory-east",
            "front",
            front,
            16.0,
            6.68,
            19.2,
            1.25,
            mullions=8,
            frame_mat=self._m("factory_aluminum"),
        )
        self._box("front:central-projection", (3.9, front - 0.38, 3.75), (4.2, 0.75, 7.5), self._m("factory_beige_panel_light"), "factory-building", 0.018, "service-core-projection")
        self._panel_ribs("front:central-projection-ribs", "front", front - 0.76, 4.2, 6.7, self._m("factory_galvanized"), spacing=0.42, z0=0.42, offset=0.035)

        lower_positions = (-23.5, -19.2, -14.9, -10.6, -6.3, -1.8, 8.2, 12.5, 16.8, 21.1, 24.4)
        for index, x in enumerate(lower_positions):
            self._deep_igu_window(
                f"front:lower-window:{index}",
                "front",
                front,
                x,
                3.10,
                2.35 if index not in {0, 10} else 1.85,
                1.72,
                mullions=2,
                frame_mat=self._m("factory_aluminum"),
            )
        self._personnel_door("front:main-personnel-entry", "front", front - 0.76, 3.9, z=1.20, width=1.25, height=2.40, mat=self._m("factory_door_gray"), canopy=True)
        self._personnel_door("front:secondary-door", "front", front, -3.8, z=1.15, width=1.10, height=2.30, canopy=False)
        self._box("front:recess-shadow-band", (3.9, front - 0.795, 5.62), (3.65, 0.035, 0.17), self._m("factory_dark_trim"), "factory-facade-detail", 0.005, "projection-shadow-line")
        self._wall_box("front", front, -12.2, 5.66, 28.8, 0.18, 0.26, self._m("factory_dark_trim"), "front:clerestory-sill-rail", offset=0.20, bevel=0.008, semantic="factory-facade-detail", role="continuous-clerestory-shadow-rail")
        self._facade_sign(
            "front:identity-sign",
            "PRECISION WORKS",
            "front",
            front,
            -17.0,
            7.82,
            9.6,
            1.08,
            font_size=0.76,
            panel_mat=self._m("factory_sign_charcoal"),
        )
        self._service_conduit("front:electrical-service", "front", front, 0.1, 0.55, 4.95, branch=1.55)

        # Fully serviced rear elevation: clerestory glazing, receiving doors,
        # deep window assemblies and utilities prevent the reverse view from
        # degenerating into an undecorated warehouse box.
        self._deep_igu_window(
            "back:clerestory",
            "back",
            back,
            0.0,
            6.68,
            45.0,
            1.18,
            mullions=19,
            frame_mat=self._m("factory_aluminum"),
        )
        for index, x in enumerate((-15.0, 0.0, 15.0)):
            self._roller_door(f"back:receiving-door:{index}", "back", back, x, width=4.35, height=4.35, z0=0.36, mat=self._m("factory_door_gray"), dock=False)
            self._canopy(f"back:receiving-weatherhood:{index}", "back", back, x, 5.05, 5.10, 1.30, self._m("factory_aluminum"))
        for index, x in enumerate((-23.2, -7.7, 7.7, 23.2)):
            self._deep_igu_window(
                f"back:service-window:{index}",
                "back",
                back,
                x,
                3.00,
                2.30,
                1.62,
                mullions=2,
                frame_mat=self._m("factory_aluminum"),
            )
        self._industrial_louver("back:plant-louver", "back", back, 24.0, 5.30, 2.55, 1.05)
        self._service_conduit("back:utility-riser", "back", back, -25.2, 0.52, 5.10, branch=1.35)
        self._wall_box("back", back, 0.0, 5.70, width - 0.55, 0.18, 0.24, self._m("factory_dark_trim"), "back:clerestory-sill-rail", offset=0.20, bevel=0.008, semantic="factory-facade-detail", role="continuous-clerestory-shadow-rail")

        for index, y in enumerate((-6.8, -3.0, 1.0, 5.0)):
            self._deep_igu_window(
                f"left:end-window:{index}",
                "left",
                left,
                y,
                3.05,
                2.30,
                1.60,
                mullions=2,
                frame_mat=self._m("factory_aluminum"),
            )
        self._roller_door("left:receiving-door", "left", left, 6.8, width=4.4, height=4.5, z0=0.34, dock=False)
        self._canopy("left:receiving-door-weatherhood", "left", left, 6.8, 5.20, 5.25, 1.50, self._m("factory_aluminum"))
        self._industrial_louver("left:gable-louver", "left", left, 0.0, 9.15, 3.2, 1.05)
        self._fire_ladder("back:roof-access-ladder", right + 0.18, 6.8, 0.35, eave - 0.30, side="side")

        for index, x in enumerate((-18.0, -5.5, 8.5, 21.0)):
            roof_z = ridge - (ridge - eave) * 0.28
            self._roof_vent(f"roof:vent:{index}", (x, 2.8, roof_z), height=0.92 + 0.08 * (index % 2), radius=0.17)
        self._rooftop_hvac("roof:makeup-air-unit", (13.2, -1.0, ridge - 0.42), scale=0.82)
        self._bollards("front:entry-bollards", ((2.75, front - 1.40), (5.05, front - 1.40)), height=0.92, radius=0.075)

    def _build_white_modern(self):
        width, depth, height = FACTORY_DIMENSIONS["white_modern"]
        front = -depth * 0.5
        back = depth * 0.5
        left = -width * 0.5
        right = width * 0.5
        if self.include_site:
            self._site_pad("white-modern", width, depth, front_extension=11.0, mat=self._m("factory_asphalt"))

        self._box("shell:foundation", (0, 0, 0.30), (width + 0.32, depth + 0.32, 0.60), self._m("factory_concrete"), "factory-foundation", 0.040, "architectural-concrete-plinth")
        self._box("shell:white-panel-volume", (0, 0, height * 0.5), (width, depth, height), self._m("factory_white_panel"), "factory-building", 0.045, "insulated-panel-factory-shell")
        self._panel_grid("cladding:grid:front", "front", front, width, height, x_spacing=3.0, z_spacing=1.42, mat=self._m("factory_galvanized"))
        self._panel_grid("cladding:grid:back", "back", back, width, height, x_spacing=3.0, z_spacing=1.42, mat=self._m("factory_galvanized"))
        self._panel_grid("cladding:grid:left", "left", left, depth, height, x_spacing=2.5, z_spacing=1.42, mat=self._m("factory_galvanized"))
        self._panel_grid("cladding:grid:right", "right", right, depth, height, x_spacing=2.5, z_spacing=1.42, mat=self._m("factory_galvanized"))
        self._facade_fastener_grid("cladding:fasteners:front", "front", front, self._frange(-22.5, 22.5, 3.0), self._frange(1.42, height - 0.30, 1.42), offset=0.205)
        self._facade_fastener_grid("cladding:fasteners:back", "back", back, self._frange(-22.5, 22.5, 3.0), self._frange(1.42, height - 0.30, 1.42), offset=0.205)
        self._wall_box("front", front, 0, 0.68, width - 0.40, 0.58, 0.20, self._m("factory_concrete"), "front:architectural-base-course", offset=0.17, bevel=0.012, semantic="factory-foundation", role="recessed-precast-base-course")
        for z, label in ((4.75, "mid"), (8.05, "upper")):
            self._wall_box("front", front, 0, z, width - 0.50, 0.15, 0.24, self._m("factory_aluminum"), f"front:datum-rail:{label}", offset=0.20, bevel=0.008, semantic="factory-facade-detail", role="continuous-aluminum-datum-rail")
        for index, x in enumerate((-23.78, 23.78)):
            self._facade_steel_column(f"front:corner-return:{index}", "front", front, x, height - 0.15, width=0.30, mat=self._m("factory_white_trim"))
        self._flat_roof("roof:flat-membrane", (0, 0, height + 0.12), (width - 0.45, depth - 0.45, 0.24), self._m("factory_roof_zinc"))
        self._parapet("roof:parapet", width, depth, height + 0.32, self._m("factory_white_trim"))
        for index, (x, y) in enumerate(((-13.5, -2.8), (-3.8, 3.2), (7.2, -3.0), (17.0, 3.0))):
            self._flat_skylight(f"roof:skylight:{index}", (x, y, height + 0.31), (2.6, 1.45))

        # A tall glazed blade marks the principal entrance, exactly as in the
        # modern white reference.  It is built from separate inset panes,
        # mullions and a projecting canopy instead of a single blue rectangle.
        self._box("front:entrance-recess", (-17.6, front - 0.08, 3.85), (5.4, 0.22, 7.3), self._m("factory_dark_trim"), "factory-entrance", 0.020, "double-height-entrance-recess")
        for index, x in enumerate((-20.48, -14.72)):
            self._wall_box("front", front, x, 4.15, 0.34, 8.10, 0.58, self._m("factory_white_trim"), f"front:entrance-portal-column:{index}", offset=0.40, bevel=0.018, semantic="factory-entrance", role="deep-entrance-portal-column")
        self._wall_box("front", front, -17.60, 8.18, 6.10, 0.34, 0.58, self._m("factory_white_trim"), "front:entrance-portal-head", offset=0.40, bevel=0.018, semantic="factory-entrance", role="deep-entrance-portal-lintel")
        for index, x in enumerate((-19.2, -17.6, -16.0)):
            self._framed_window(f"front:entrance-glass:{index}", "front", front - 0.22, x, 3.90, 1.34, 6.65, mullions=0, transoms=3, frame_mat=self._m("factory_white_trim"), glass_mat=self._m("factory_glass_dark"))
        self._personnel_door("front:glazed-main-door", "front", front - 0.34, -17.6, z=1.20, width=1.35, height=2.40, mat=self._m("factory_glass_dark"), canopy=True)
        self._canopy("front:main-entrance-canopy", "front", front - 0.18, -17.6, 3.35, 5.35, 2.35, self._m("factory_aluminum"))
        for index, x in enumerate((-19.45, -15.75)):
            self._cylinder(f"front:main-canopy-column:{index}", (x, front - 2.23, 1.62), 0.075, 3.18, self._m("factory_stainless"), "factory-entrance", 20, "stainless-canopy-column")
            self._cylinder(f"front:main-canopy-base:{index}", (x, front - 2.23, 0.08), 0.18, 0.16, self._m("factory_dark_trim"), "factory-entrance", 20, "canopy-column-baseplate")

        self._ribbon_window("front:upper-ribbon", "front", front, 5.6, 6.65, 32.0, 1.28, 16, frame_mat=self._m("factory_galvanized"), glass_mat=self._m("factory_glass_blue"))
        self._ribbon_window("front:lower-office-ribbon", "front", front, 7.0, 2.65, 14.4, 1.55, 7, frame_mat=self._m("factory_white_trim"), glass_mat=self._m("factory_glass_dark"))
        self._personnel_door("front:office-door", "front", front, -9.6, z=1.15, width=1.15, height=2.30, mat=self._m("factory_white_trim"), canopy=True)
        self._personnel_door("front:service-door", "front", front, 19.6, z=1.15, width=1.12, height=2.30, mat=self._m("factory_white_trim"), canopy=True)
        self._facade_sign(
            "front:identity-sign",
            "AEROTEC MANUFACTURING",
            "front",
            front,
            7.4,
            8.86,
            13.4,
            1.30,
            font_size=0.82,
            panel_mat=self._m("factory_sign_blue"),
        )
        self._service_conduit("front:service-conduit", "front", front, 22.4, 0.50, 4.20, branch=-1.45)

        self._ribbon_window("left:side-ribbon", "left", left, 0.7, 6.55, 15.7, 1.18, 8, frame_mat=self._m("factory_galvanized"), glass_mat=self._m("factory_glass_blue"))
        self._wall_box("back", back, 0, 0.68, width - 0.40, 0.58, 0.20, self._m("factory_concrete"), "back:architectural-base-course", offset=0.17, bevel=0.012, semantic="factory-foundation", role="recessed-precast-base-course")
        for z, label in ((4.75, "mid"), (8.05, "upper")):
            self._wall_box("back", back, 0, z, width - 0.50, 0.15, 0.24, self._m("factory_aluminum"), f"back:datum-rail:{label}", offset=0.20, bevel=0.008, semantic="factory-facade-detail", role="continuous-aluminum-datum-rail")
        for index, x in enumerate((-23.78, -12.2, 0.8, 23.78)):
            self._facade_steel_column(f"back:facade-column:{index}", "back", back, x, height - 0.15, width=0.28, mat=self._m("factory_white_trim"))
        self._ribbon_window("back:upper-office-ribbon", "back", back, 9.2, 7.05, 26.0, 1.28, 13, frame_mat=self._m("factory_galvanized"), glass_mat=self._m("factory_glass_dark"))
        self._roller_door("back:loading-bay-a", "back", back, -9.0, width=4.5, height=4.35, dock=True)
        self._roller_door("back:loading-bay-b", "back", back, -2.5, width=4.5, height=4.35, dock=True)
        self._roller_door("back:loading-bay-c", "back", back, 4.0, width=4.5, height=4.35, dock=True)
        for index, x in enumerate((10.0, 15.5, 21.0)):
            self._framed_window(f"back:logistics-window:{index}", "back", back, x, 2.70, 3.30, 1.60, mullions=2, frame_mat=self._m("factory_white_trim"), glass_mat=self._m("factory_glass_blue"))
        self._personnel_door("back:logistics-door", "back", back, -14.7, z=1.17, width=1.15, height=2.34, mat=self._m("factory_white_trim"), canopy=True)
        self._industrial_louver("back:plant-louver", "back", back, -18.3, 6.05, 3.20, 1.32)
        self._service_conduit("back:loading-service", "back", back, -20.8, 0.52, 4.65, branch=1.35)
        self._industrial_louver("right:plant-louver-a", "right", right, -2.8, 5.8, 2.8, 1.3)
        self._industrial_louver("right:plant-louver-b", "right", right, 2.0, 5.8, 2.8, 1.3)

        for index, loc in enumerate(((-8.0, 2.4, height + 0.28), (5.6, 2.0, height + 0.28), (15.0, -2.6, height + 0.28))):
            self._rooftop_hvac(f"roof:hvac:{index}", loc, scale=0.78 + 0.08 * (index % 2))
        for index, x in enumerate((-21.0, -11.0, 13.0, 22.0)):
            self._cylinder(f"drainage:scupper:{index}", (x, front - 0.26, height - 0.10), 0.055, 0.42, self._m("factory_galvanized"), "factory-drainage", 14, "parapet-scupper")
            self.objects[-1].rotation_euler[0] = math.radians(90)
            self._cylinder(f"drainage:downspout:{index}", (x, front - 0.30, height * 0.48), 0.052, height - 0.78, self._m("factory_galvanized"), "factory-drainage", 14, "rectangular-downspout")

        self._hedge("front-foundation-hedge", (-22.8, front - 2.2, 0), (22.8, front - 2.2, 0), width=0.80, height=0.72)
        self._box("landscape:entry-walk", (-17.6, front - 4.6, 0.13), (4.6, 5.4, 0.16), self._m("factory_paving"), "factory-walkway", 0.055, "entrance-paving")
        self._bollards("front:service-bollards", ((18.65, front - 1.20), (20.55, front - 1.20)), height=0.86, radius=0.070, mat=self._m("factory_galvanized"))

    def _build_gated_campus(self):
        width, depth, height = FACTORY_DIMENSIONS["gated_campus"]
        front_site = -depth * 0.5
        if self.include_site:
            self._site_pad("gated-campus", width, depth, front_extension=4.5, mat=self._m("factory_concrete"))

        # Independent volumes reproduce the layered industrial-campus reading
        # of the reference: workshop, office wing, connector and gatehouse.
        hall_w, hall_d, hall_h = 37.0, 17.0, 6.70
        hall_x, hall_y = -7.5, 2.4
        hall_front = hall_y - hall_d * 0.5
        self._box("hall:foundation", (hall_x, hall_y, 0.30), (hall_w + 0.30, hall_d + 0.30, 0.60), self._m("factory_concrete_dark"), "factory-foundation", 0.035, "workshop-foundation")
        self._box("hall:shell", (hall_x, hall_y, hall_h * 0.5), (hall_w, hall_d, hall_h), self._m("factory_gray_panel"), "factory-building", 0.030, "low-industrial-hall")
        self._panel_ribs("hall:front-ribs", "front", hall_front, hall_w, hall_h - 0.42, self._m("factory_galvanized"), spacing=0.62, z0=0.32, center_u=hall_x)
        self._panel_joints("hall:front-joints", "front", hall_front, hall_w, (1.45, 2.90, 4.35, 5.80), self._m("factory_dark_trim"), center_u=hall_x)
        self._facade_fastener_grid("hall:front-fasteners", "front", hall_front, self._frange(hall_x - hall_w * 0.5 + 0.62, hall_x + hall_w * 0.5 - 0.25, 1.86), (1.45, 2.90, 4.35, 5.80), offset=0.205)
        self._wall_box("front", hall_front, hall_x, 0.72, hall_w - 0.30, 0.62, 0.20, self._m("factory_concrete"), "hall:front-wainscot", offset=0.17, bevel=0.012, semantic="factory-foundation", role="impact-resistant-concrete-wainscot")
        for index, x in enumerate((-25.75, -18.0, -11.0, -4.0, 2.15, 10.75)):
            self._facade_steel_column(f"hall:front-column:{index}", "front", hall_front, x, hall_h - 0.16, width=0.25, mat=self._m("factory_aluminum"))
        self._wall_box("front", hall_front, hall_x, hall_h - 0.18, hall_w + 0.20, 0.34, 0.30, self._m("factory_aluminum"), "hall:front-eave-fascia", offset=0.20, bevel=0.012, semantic="factory-roof-detail", role="continuous-hall-eave-fascia")
        self._flat_roof("hall:roof", (hall_x, hall_y, hall_h + 0.14), (hall_w - 0.28, hall_d - 0.28, 0.28), self._m("factory_roof_zinc"))
        # Shifted parapet pieces are placed explicitly because this volume is
        # not centred on the asset origin.
        for label, loc, dims in (
            ("front", (hall_x, hall_front, hall_h + 0.38), (hall_w + 0.25, 0.30, 0.68)),
            ("back", (hall_x, hall_y + hall_d * 0.5, hall_h + 0.38), (hall_w + 0.25, 0.30, 0.68)),
            ("left", (hall_x - hall_w * 0.5, hall_y, hall_h + 0.38), (0.30, hall_d, 0.68)),
            ("right", (hall_x + hall_w * 0.5, hall_y, hall_h + 0.38), (0.30, hall_d, 0.68)),
        ):
            self._box(f"hall:parapet:{label}", loc, dims, self._m("factory_gray_panel"), "factory-roof", 0.018, "workshop-parapet")

        for index, x in enumerate((-21.5, -14.5, -7.5, -0.5)):
            self._roller_door(f"hall:blue-bay:{index}", "front", hall_front, x, width=4.65, height=4.35, z0=0.32, mat=self._m("factory_door_gray"), blue_header=True, dock=False)
        self._personnel_door("hall:service-entry", "front", hall_front, 7.0, z=1.14, width=1.12, height=2.28, mat=self._m("factory_safety_blue"), canopy=True)
        for index, x in enumerate((4.0, 8.6)):
            self._framed_window(f"hall:office-window:{index}", "front", hall_front, x, 3.15, 2.50, 1.55, mullions=2, frame_mat=self._m("factory_safety_blue"), glass_mat=self._m("factory_glass_dark"))
        self._service_conduit("hall:bay-service-conduit", "front", hall_front, 10.2, 0.55, 4.90, branch=-1.10)

        hall_back = hall_y + hall_d * 0.5
        self._panel_ribs("hall:back-ribs", "back", hall_back, hall_w, hall_h - 0.42, self._m("factory_galvanized"), spacing=0.62, z0=0.32, center_u=hall_x)
        self._panel_joints("hall:back-joints", "back", hall_back, hall_w, (1.45, 2.90, 4.35, 5.80), self._m("factory_dark_trim"), center_u=hall_x)
        self._facade_fastener_grid("hall:back-fasteners", "back", hall_back, self._frange(hall_x - hall_w * 0.5 + 0.62, hall_x + hall_w * 0.5 - 0.25, 1.86), (1.45, 2.90, 4.35, 5.80), offset=0.205)
        self._wall_box("back", hall_back, hall_x, 0.72, hall_w - 0.30, 0.62, 0.20, self._m("factory_concrete"), "hall:back-wainscot", offset=0.17, bevel=0.012, semantic="factory-foundation", role="impact-resistant-concrete-wainscot")
        for index, x in enumerate((-25.75, -18.0, -10.0, -2.0, 5.0, 10.75)):
            self._facade_steel_column(f"hall:back-column:{index}", "back", hall_back, x, hall_h - 0.16, width=0.25, mat=self._m("factory_aluminum"))
        for index, x in enumerate((-19.0, -10.0)):
            self._roller_door(f"hall:back-loading-bay:{index}", "back", hall_back, x, width=4.55, height=4.30, z0=0.32, mat=self._m("factory_door_gray"), blue_header=True, dock=False)
            self._canopy(f"hall:back-loading-hood:{index}", "back", hall_back, x, 5.00, 5.15, 1.22, self._m("factory_aluminum"))
        for index, x in enumerate((-3.0, 2.4, 7.5)):
            self._framed_window(f"hall:back-window:{index}", "back", hall_back, x, 3.05, 3.10, 1.58, mullions=2, frame_mat=self._m("factory_safety_blue"), glass_mat=self._m("factory_glass_dark"))
        self._personnel_door("hall:back-personnel-door", "back", hall_back, -23.5, z=1.15, width=1.10, height=2.30, mat=self._m("factory_safety_blue"), canopy=True)
        self._industrial_louver("hall:back-high-louver", "back", hall_back, -4.0, 5.55, 3.0, 1.0)
        self._service_conduit("hall:back-service-conduit", "back", hall_back, 10.0, 0.54, 5.02, branch=-1.15)
        self._wall_box("back", hall_back, hall_x, hall_h - 0.18, hall_w + 0.20, 0.34, 0.30, self._m("factory_aluminum"), "hall:back-eave-fascia", offset=0.20, bevel=0.012, semantic="factory-roof-detail", role="continuous-hall-eave-fascia")

        office_x, office_y = 18.0, 1.0
        office_w, office_d, office_h = 15.0, 13.5, 5.55
        office_front = office_y - office_d * 0.5
        self._box("office:foundation", (office_x, office_y, 0.28), (office_w + 0.30, office_d + 0.30, 0.56), self._m("factory_concrete_dark"), "factory-foundation", 0.035, "office-foundation")
        self._box("office:shell", (office_x, office_y, office_h * 0.5), (office_w, office_d, office_h), self._m("factory_gray_panel"), "factory-building", 0.032, "plant-office-wing")
        self._panel_grid("office:panel-grid", "front", office_front, office_w, office_h, x_spacing=2.5, z_spacing=1.35, mat=self._m("factory_dark_trim"), center_u=office_x)
        self._facade_fastener_grid("office:panel-fasteners", "front", office_front, self._frange(office_x - office_w * 0.5 + 1.25, office_x + office_w * 0.5 - 0.50, 2.5), self._frange(1.35, office_h - 0.30, 1.35), offset=0.205)
        self._wall_box("front", office_front, office_x, 0.64, office_w - 0.25, 0.52, 0.18, self._m("factory_concrete"), "office:front-base-course", offset=0.17, bevel=0.010, semantic="factory-foundation", role="office-precast-base-course")
        self._flat_roof("office:roof", (office_x, office_y, office_h + 0.13), (office_w - 0.25, office_d - 0.25, 0.26), self._m("factory_roof_zinc"))
        self._flat_skylight("hall:roof-skylight:a", (-15.0, 2.7, hall_h + 0.32), (2.5, 1.35))
        self._flat_skylight("hall:roof-skylight:b", (-2.0, 2.7, hall_h + 0.32), (2.5, 1.35))
        self._flat_skylight("office:roof-skylight", (18.0, 1.0, office_h + 0.30), (2.1, 1.20))
        for index, x in enumerate((13.4, 18.0, 22.6)):
            self._framed_window(f"office:front-window:{index}", "front", office_front, x, 2.72, 3.20, 1.65, mullions=2, frame_mat=self._m("factory_safety_blue"), glass_mat=self._m("factory_glass_dark"))
        self._personnel_door("office:front-door", "front", office_front, 25.0, z=1.18, width=1.18, height=2.35, mat=self._m("factory_safety_blue"), canopy=True)
        self._industrial_louver("office:right-louver", "right", office_x + office_w * 0.5, 2.8, 3.7, 2.5, 1.25)
        office_back = office_y + office_d * 0.5
        self._panel_grid("office:back-panel-grid", "back", office_back, office_w, office_h, x_spacing=2.5, z_spacing=1.35, mat=self._m("factory_dark_trim"), center_u=office_x)
        self._facade_fastener_grid("office:back-fasteners", "back", office_back, self._frange(office_x - office_w * 0.5 + 1.25, office_x + office_w * 0.5 - 0.50, 2.5), self._frange(1.35, office_h - 0.30, 1.35), offset=0.205)
        self._wall_box("back", office_back, office_x, 0.64, office_w - 0.25, 0.52, 0.18, self._m("factory_concrete"), "office:back-base-course", offset=0.17, bevel=0.010, semantic="factory-foundation", role="office-precast-base-course")
        for index, x in enumerate((13.0, 18.0, 22.6)):
            self._framed_window(f"office:back-window:{index}", "back", office_back, x, 2.72, 3.10, 1.62, mullions=2, frame_mat=self._m("factory_safety_blue"), glass_mat=self._m("factory_glass_dark"))
        self._personnel_door("office:back-door", "back", office_back, 24.8, z=1.17, width=1.10, height=2.34, mat=self._m("factory_safety_blue"), canopy=True)
        self._industrial_louver("office:back-louver", "back", office_back, 18.0, 4.62, 3.2, 0.86)
        self._facade_sign(
            "office:identity-sign",
            "NORTHLINE PLANT 03",
            "front",
            office_front,
            18.0,
            4.76,
            11.7,
            1.02,
            font_size=0.70,
            panel_mat=self._m("factory_sign_blue"),
        )

        # Detailed masonry boundary walls and a powered full-width telescopic
        # gate reproduce the reference without the two oversized yellow piers.
        gate_y = front_site - 0.15
        self._masonry_wall("boundary:left-wall", -27.0, -10.0, gate_y, height=2.70, thickness=0.48)
        self._masonry_wall("boundary:right-wall", 11.0, 27.0, gate_y, height=2.70, thickness=0.48)

        guard_x, guard_y = -4.6, -11.8
        self._box("guardhouse:base", (guard_x, guard_y, 0.22), (7.6, 5.4, 0.44), self._m("factory_concrete_dark"), "guardhouse", 0.035, "guardhouse-foundation")
        self._box("guardhouse:shell", (guard_x, guard_y, 1.85), (7.2, 5.0, 3.35), self._m("factory_gray_panel"), "guardhouse", 0.040, "security-guardhouse")
        self._box("guardhouse:roof", (guard_x, guard_y, 3.72), (8.1, 5.85, 0.30), self._m("factory_roof_zinc"), "guardhouse", 0.030, "guardhouse-overhang-roof")
        self._wall_box("front", guard_y - 2.5, guard_x, 0.58, 6.75, 0.42, 0.16, self._m("factory_concrete"), "guardhouse:front-base-course", offset=0.15, bevel=0.010, semantic="guardhouse", role="guardhouse-precast-base-course")
        for index, x in enumerate((guard_x - 3.48, guard_x + 3.48)):
            self._facade_steel_column(f"guardhouse:corner-trim:{index}", "front", guard_y - 2.5, x, 3.32, width=0.20, mat=self._m("factory_aluminum"))
        self._wall_box("front", guard_y - 2.5, guard_x, 3.43, 7.45, 0.22, 0.34, self._m("factory_aluminum"), "guardhouse:roof-fascia", offset=0.22, bevel=0.012, semantic="guardhouse", role="guardhouse-formed-roof-fascia")
        self._ribbon_window("guardhouse:front-glazing", "front", guard_y - 2.5, guard_x - 0.40, 2.15, 4.80, 1.35, 4, frame_mat=self._m("factory_safety_blue"), glass_mat=self._m("factory_glass_dark"))
        self._personnel_door("guardhouse:door", "front", guard_y - 2.5, guard_x + 2.55, z=1.15, width=1.05, height=2.30, mat=self._m("factory_safety_blue"), canopy=True)
        self._facade_sign(
            "guardhouse:gate-sign",
            "PLANT 03",
            "front",
            guard_y - 2.5,
            guard_x - 0.30,
            3.14,
            4.75,
            0.72,
            font_size=0.54,
            panel_mat=self._m("factory_sign_charcoal"),
        )
        self._accordion_gate("security:accordion-gate", 0.5, gate_y - 0.18, 19.7, height=2.18)

        self._security_fence("security:left-side-fence", (-27.0, gate_y + 0.2, 0), (-27.0, 12.5, 0), height=2.20)
        self._security_fence("security:right-side-fence", (27.0, gate_y + 0.2, 0), (27.0, 12.5, 0), height=2.20)
        self._security_fence("security:rear-fence", (-27.0, 12.5, 0), (27.0, 12.5, 0), height=2.20)
        self._bollards("security:gate-bollards", ((-9.55, gate_y - 1.0), (10.55, gate_y - 1.0)), height=1.05, radius=0.075, mat=self._m("factory_stainless"))

        for index, loc in enumerate(((-16.0, 4.8, hall_h + 0.28), (-3.0, 4.0, hall_h + 0.28), (18.0, 2.0, office_h + 0.27))):
            self._rooftop_hvac(f"roof:hvac:{index}", loc, scale=0.72)
        for index, x in enumerate((-22.0, -7.5, 6.0)):
            self._roof_vent(f"roof:extract:{index}", (x, 5.0, hall_h + 0.30), height=1.15, radius=0.20)
        self._hedge("boundary-office-hedge", (12.0, gate_y + 1.45, 0), (25.5, gate_y + 1.45, 0), width=0.70, height=0.66)

    def _build_highbay_monochrome(self):
        width, depth, ridge = FACTORY_DIMENSIONS["highbay_monochrome"]
        eave = 9.85
        front = -depth * 0.5
        back = depth * 0.5
        left = -width * 0.5
        right = width * 0.5
        if self.include_site:
            self._site_pad("highbay-monochrome", width, depth, front_extension=12.0, mat=self._m("factory_asphalt"))

        self._box("shell:foundation", (0, 0, 0.36), (width + 0.38, depth + 0.38, 0.72), self._m("factory_concrete_dark"), "factory-foundation", 0.042, "highbay-concrete-plinth")
        self._box("shell:white-lower-hall", (0, 0, eave * 0.5 + 0.25), (width, depth, eave - 0.50), self._m("factory_white_panel"), "factory-building", 0.030, "highbay-steel-hall")
        self._panel_ribs("front:lower-cladding-ribs", "front", front, width, eave - 0.74, self._m("factory_white_trim"), spacing=0.72, z0=0.48)
        self._panel_joints("front:lower-cladding-joints", "front", front, width, (1.82, 3.58, 5.34, 6.62, 8.20), self._m("factory_galvanized"), offset=0.094)
        self._facade_fastener_grid("front:cladding-fasteners", "front", front, self._frange(-28.2, 28.2, 1.44), (1.82, 3.58, 5.34, 6.62, 8.20), offset=0.205)
        self._panel_ribs("back:lower-cladding-ribs", "back", back, width, eave - 0.74, self._m("factory_white_trim"), spacing=0.72, z0=0.48)
        self._panel_joints("back:lower-cladding-joints", "back", back, width, (1.82, 3.58, 5.34, 6.62, 8.20), self._m("factory_galvanized"), offset=0.094)
        self._facade_fastener_grid("back:cladding-fasteners", "back", back, self._frange(-28.2, 28.2, 1.44), (1.82, 3.58, 5.34, 6.62, 8.20), offset=0.205)
        self._wall_box("front", front, 0, 8.40, width, 2.90, 0.16, self._m("factory_charcoal_panel"), "front:dark-upper-band", offset=0.10, bevel=0.012, semantic="factory-building", role="charcoal-clerestory-band")
        self._wall_box("back", back, 0, 8.40, width, 2.90, 0.16, self._m("factory_charcoal_panel"), "back:dark-upper-band", offset=0.10, bevel=0.012, semantic="factory-building", role="charcoal-clerestory-band")
        self._gable_end("shell:dark-gable-left", left, depth, eave, ridge, self._m("factory_charcoal_panel"), thickness=0.18)
        self._gable_end("shell:dark-gable-right", right, depth, eave, ridge, self._m("factory_charcoal_panel"), thickness=0.18)
        self._wall_box("left", left, 0, eave * 0.5, depth, eave, 0.18, self._m("factory_charcoal_panel"), "left:dark-end-wall", offset=0.10, bevel=0.015, semantic="factory-building", role="dark-gabled-end-wall")

        self._roof_slope("roof:front-slope", width, depth, eave, ridge, -1, self._m("factory_roof_dark"), overhang=0.48)
        self._roof_slope("roof:back-slope", width, depth, eave, ridge, 1, self._m("factory_roof_dark"), overhang=0.48)
        self._roof_ribs("roof:standing-seam", width, depth, eave, ridge, 1.25, self._m("factory_galvanized"))
        roof_angle = math.atan2(ridge - eave, depth * 0.5)
        for side in (-1, 1):
            for index, x in enumerate((-18.0, -6.0, 6.0, 18.0)):
                y = side * 5.3
                z = ridge - (ridge - eave) * (abs(y) / (depth * 0.5)) + 0.10
                curb = self._box(f"roof:daylight-strip-curb:{side}:{index}", (x, y, z - 0.05), (3.7, 3.0, 0.10), self._m("factory_shadow"), "factory-roof-detail", 0.010, "highbay-rooflight-curb")
                curb.rotation_euler[0] = -side * roof_angle
                pane = self._box(f"roof:daylight-strip:{side}:{index}", (x, y, z + 0.035), (3.45, 2.74, 0.080), self._m("factory_glass_dark"), "factory-roof-equipment", 0.016, "highbay-translucent-daylight-panel")
                pane.rotation_euler[0] = -side * roof_angle
        ridge_cap = self._cylinder("roof:ridge-cap", (0, 0, ridge + 0.02), 0.105, width + 0.95, self._m("factory_galvanized"), "factory-roof-detail", 22, "formed-ridge-cap")
        ridge_cap.rotation_euler[1] = math.radians(90)

        bays = 16
        bay_step = width / bays
        bay_centers = [-width * 0.5 + bay_step * (index + 0.5) for index in range(bays)]
        column_positions = [-width * 0.5 + bay_step * index for index in range(bays + 1)]
        for index, x in enumerate(column_positions):
            self._facade_steel_column(f"front:structural-column:{index}", "front", front, x, 9.48, width=0.34, mat=self._m("factory_white_trim"))
            self._wall_box("front", front, x, 6.02, 0.72, 0.26, 0.42, self._m("factory_dark_trim"), f"front:column-spandrel-bracket:{index}", offset=0.31, bevel=0.010, semantic="factory-structure", role="bolted-spandrel-seat-bracket")
            self._facade_steel_column(f"back:structural-column:{index}", "back", back, x, 9.48, width=0.34, mat=self._m("factory_white_trim"))
            self._wall_box("back", back, x, 6.02, 0.72, 0.26, 0.42, self._m("factory_dark_trim"), f"back:column-spandrel-bracket:{index}", offset=0.31, bevel=0.010, semantic="factory-structure", role="bolted-spandrel-seat-bracket")

        door_bays = {2, 9, 13}
        for index, x in enumerate(bay_centers):
            self._framed_window(f"front:upper-window:{index}", "front", front, x, 7.35, bay_step * 0.62, 1.05, mullions=1, frame_mat=self._m("factory_dark_trim"), glass_mat=self._m("factory_glass_dark"))
            if index in door_bays:
                self._roller_door(f"front:loading-door:{index}", "front", front, x, width=bay_step * 0.72, height=3.55, z0=0.36, mat=self._m("factory_door_gray"), dock=False)
                self._bollards(f"front:door-bollards:{index}", ((x - bay_step * 0.39, front - 0.80), (x + bay_step * 0.39, front - 0.80)), height=0.88, radius=0.070, mat=self._m("factory_galvanized"))
                self._canopy(f"front:loading-door-hood:{index}", "front", front, x, 4.52, bay_step * 0.86, 1.05, self._m("factory_aluminum"))
            else:
                self._framed_window(f"front:lower-window:{index}", "front", front, x, 2.35, bay_step * 0.64, 1.55, mullions=2, frame_mat=self._m("factory_galvanized"), glass_mat=self._m("factory_glass_blue"))
            self._wall_light(f"front:bay-light:{index}", "front", front, x, 5.65)

        rear_door_bays = {1, 6, 12}
        for index, x in enumerate(bay_centers):
            self._framed_window(f"back:upper-window:{index}", "back", back, x, 7.35, bay_step * 0.62, 1.05, mullions=1, frame_mat=self._m("factory_dark_trim"), glass_mat=self._m("factory_glass_dark"))
            if index in rear_door_bays:
                self._roller_door(f"back:loading-door:{index}", "back", back, x, width=bay_step * 0.72, height=3.55, z0=0.36, mat=self._m("factory_door_gray"), dock=False)
                self._bollards(f"back:door-bollards:{index}", ((x - bay_step * 0.39, back + 0.80), (x + bay_step * 0.39, back + 0.80)), height=0.88, radius=0.070, mat=self._m("factory_galvanized"))
                self._canopy(f"back:loading-door-hood:{index}", "back", back, x, 4.52, bay_step * 0.86, 1.05, self._m("factory_aluminum"))
            else:
                self._framed_window(f"back:lower-window:{index}", "back", back, x, 2.35, bay_step * 0.64, 1.55, mullions=2, frame_mat=self._m("factory_galvanized"), glass_mat=self._m("factory_glass_blue"))
            self._wall_light(f"back:bay-light:{index}", "back", back, x, 5.65)

        # Strong horizontal rails and base panels keep the long elevation from
        # reading as a row of disconnected window cards.
        self._wall_box("front", front, 0, 5.95, width - 0.45, 0.26, 0.24, self._m("factory_dark_trim"), "front:continuous-shadow-rail", offset=0.20, bevel=0.010, semantic="factory-facade-detail", role="continuous-spandrel-rail")
        self._wall_box("front", front, 0, 0.72, width - 0.45, 0.52, 0.20, self._m("factory_concrete"), "front:continuous-base-course", offset=0.18, bevel=0.012, semantic="factory-foundation", role="continuous-base-course")
        self._wall_box("front", front, 0, eave - 0.18, width + 0.24, 0.34, 0.32, self._m("factory_dark_trim"), "front:deep-eave-fascia", offset=0.22, bevel=0.012, semantic="factory-roof-detail", role="highbay-deep-eave-fascia")
        self._wall_box("back", back, 0, 5.95, width - 0.45, 0.26, 0.24, self._m("factory_dark_trim"), "back:continuous-shadow-rail", offset=0.20, bevel=0.010, semantic="factory-facade-detail", role="continuous-spandrel-rail")
        self._wall_box("back", back, 0, 0.72, width - 0.45, 0.52, 0.20, self._m("factory_concrete"), "back:continuous-base-course", offset=0.18, bevel=0.012, semantic="factory-foundation", role="continuous-base-course")
        self._wall_box("back", back, 0, eave - 0.18, width + 0.24, 0.34, 0.32, self._m("factory_dark_trim"), "back:deep-eave-fascia", offset=0.22, bevel=0.012, semantic="factory-roof-detail", role="highbay-deep-eave-fascia")
        self._facade_sign(
            "front:identity-sign",
            "HORIZON INDUSTRIES",
            "front",
            front,
            -17.0,
            8.88,
            14.0,
            1.20,
            font_size=0.84,
            panel_mat=self._m("factory_sign_charcoal"),
        )
        self._service_conduit("front:utility-riser-west", "front", front, -26.0, 0.52, 4.95, branch=1.25)
        self._service_conduit("front:utility-riser-east", "front", front, 26.0, 0.52, 4.95, branch=-1.25)
        self._service_conduit("back:utility-riser-west", "back", back, -26.0, 0.52, 4.95, branch=1.25)
        self._service_conduit("back:utility-riser-east", "back", back, 26.0, 0.52, 4.95, branch=-1.25)

        for index, y in enumerate((-7.5, -3.5, 0.5, 4.5, 8.0)):
            self._framed_window(f"left:end-window:{index}", "left", left - 0.18, y, 3.0, 2.45, 1.55, mullions=2, frame_mat=self._m("factory_galvanized"), glass_mat=self._m("factory_glass_blue"))
        self._roller_door("left:large-receiving-door", "left", left - 0.18, 7.4, width=4.9, height=4.85, z0=0.36, mat=self._m("factory_door_gray"), dock=False)
        self._industrial_louver("left:high-louver-a", "left", left - 0.18, -4.5, 7.6, 3.0, 1.20)
        self._industrial_louver("left:high-louver-b", "left", left - 0.18, 4.0, 7.6, 3.0, 1.20)
        self._facade_sign(
            "left:bay-sign",
            "BAY H8",
            "left",
            left - 0.18,
            -7.1,
            8.65,
            4.8,
            1.20,
            font_size=0.86,
            panel_mat=self._m("factory_sign_charcoal"),
        )

        self._gutter_and_downspouts("drainage", width, depth, eave, self._m("factory_galvanized"), count=7)
        for index, x in enumerate((-21.0, -11.0, 0.0, 11.0, 21.0)):
            self._roof_vent(f"roof:extractor:{index}", (x, 2.6, ridge - 0.60), height=1.08, radius=0.19)
        self._rooftop_hvac("roof:main-air-handler", (15.8, -1.0, ridge - 0.50), scale=0.92)
        self._fire_ladder("back:access-ladder", right + 0.18, 7.4, 0.38, eave - 0.25, side="side")

        self._box("site:front-service-road", (0, front - 8.2, 0.13), (width + 5.0, 7.1, 0.12), self._m("factory_asphalt"), "road", 0.045, "factory-frontage-road")
        for index, x in enumerate(self._frange(-25.0, 25.0, 7.5)):
            self._box(f"site:road-centre-mark:{index}", (x, front - 9.8, 0.205), (3.6, 0.12, 0.022), self._m("factory_marking_white"), "lane-marking", 0.006, "broken-lane-marking")

    def create(self, request: UrbanAssetRequest):
        """Create one independently modelled factory variant."""
        fid = request.params.get("id", "0")
        variant = request.params.get("variant", 0)
        if isinstance(variant, str):
            if variant not in FACTORY_VARIANTS:
                raise ValueError(f"Unknown factory variant {variant!r}; expected one of {FACTORY_VARIANTS}")
            variant_name = variant
        else:
            variant_name = FACTORY_VARIANTS[int(variant) % len(FACTORY_VARIANTS)]
        self.include_site = bool(request.params.get("include_site", True))
        self._root_for_request(request, variant_name, fid)
        scale = float(request.params.get("scale", 1.0))
        self.root.scale = (scale, scale, scale)

        builders = {
            "gable_clerestory": self._build_gable_clerestory,
            "white_modern": self._build_white_modern,
            "gated_campus": self._build_gated_campus,
            "highbay_monochrome": self._build_highbay_monochrome,
        }
        builders[variant_name]()

        dims = tuple(value * scale for value in FACTORY_DIMENSIONS[variant_name])
        mesh_objects = [obj for obj in self.objects if obj.type == "MESH"]
        mesh_vertices = sum(len(obj.data.vertices) for obj in mesh_objects)
        mesh_polygons = sum(len(obj.data.polygons) for obj in mesh_objects)
        component_roles = [str(obj.get("factory_component_role", "")) for obj in self.objects]
        yellow_gate_pier_count = sum(role == "safety-yellow-gate-pier" for role in component_roles)
        security_detail_component_count = sum(
            any(token in role for token in ("gate", "fence", "masonry", "pilaster"))
            for role in component_roles
        )
        structural_detail_component_count = sum(
            any(token in role for token in ("column", "flange", "web", "bracket", "baseplate", "anchor-bolt"))
            for role in component_roles
        )
        rear_facade_detail_component_count = sum(
            ":back" in obj.name for obj in self.objects
        )
        advanced_igu_component_count = sum(
            any(
                token in role
                for token in (
                    "insulating-glass-unit",
                    "warm-edge",
                    "glazing-beads",
                    "thermal-break",
                    "window-sill-pan",
                    "frame-weep-slots",
                )
            )
            for role in component_roles
        )
        standing_seam_detail_component_count = sum(
            any(
                token in role
                for token in (
                    "standing-seam",
                    "roof-sheet-lap",
                    "ridge-cap",
                    "ridge-closure",
                    "rake-edge",
                    "eave-drip",
                    "roof-maintenance-grating",
                )
            )
            for role in component_roles
        )
        front_hedge_component_count = sum(
            "front-roadside-hedge" in obj.name for obj in self.objects
        )
        signage_bounds_pass = bool(self.signage_records) and all(
            sign["within_building_bounds"] for sign in self.signage_records
        )
        common_detail = [
            "real_scale_architectural_shell",
            "modeled_panel_joints_and_corrugation",
            "deep_glazing_reveals_frames_mullions_gaskets_sills_and_head_flashings",
            "doors_tracks_coil_hoods_seals_closers_kickplates_canopies_and_lights",
            "roof_seams_flashings_drains_and_detailed_mechanical_equipment",
            "weathered_procedural_pbr_materials",
            "modeled_site_paving_joints_and_safety_hardware",
            "expressed_structural_columns_webs_flanges_brackets_baseplates_and_anchors",
            "modeled_facade_fasteners_service_conduits_and_weatherproof_junction_boxes",
            "bounded_framed_three_dimensional_identity_signage",
            "layered_precast_wainscots_datum_rails_fascias_and_shadow_gaps",
            "fully_detailed_front_and_rear_facades_for_all_view_directions",
        ]
        variant_detail = {
            "gable_clerestory": ["solid_pitched_standing_seam_roof_and_gable_assemblies", "split_clerestory_ribbons_with_continuous_shadow_rail", "double_lite_pressure_equalised_igu_windows_with_warm_edge_spacers_thermal_breaks_and_drained_sills", "mechanically_double_locked_roof_seams_clips_sheet_laps_ridge_closures_rake_flashings_and_eave_aprons", "raised_open_bar_mechanical_service_walkway", "blue_box_rooflights_removed", "sign_obscuring_front_downspout_rerouted", "gable_end_receiving_bay_with_large_weatherhood"],
            "white_modern": ["deep_double_height_glazed_entrance_portal", "column_supported_main_entrance_canopy", "flat_parapet_roof_with_curb_mounted_skylights", "fastened_architectural_panel_grid", "clipped_individual_leaf_hedge"],
            "gated_campus": ["independent_detailed_hall_office_and_guardhouse_volumes", "coursed_masonry_security_walls_with_coping_and_pilasters", "full_width_powered_arched_telescopic_gate_with_track_castors_and_drive", "slender_non_yellow_steel_gate_guides", "dense_full_perimeter_anti_climb_picket_fence"],
            "highbay_monochrome": ["expressed_sixteen_bay_connected_structural_grid", "two_level_deep_industrial_glazing", "fastened_dark_clerestory_band_and_solid_gable", "pitched_highbay_daylight_roof_panels", "loading_doors_with_coil_hoods_weather_canopies_and_hardware", "unobstructed_frontage_road_without_rectilinear_hedge"],
        }[variant_name]
        self.root["factory_component_count"] = len(self.objects) - 1
        self.root["factory_mesh_vertices"] = mesh_vertices
        self.root["factory_mesh_polygons"] = mesh_polygons
        self.root["factory_signage_bounds_pass"] = signage_bounds_pass
        self.root["factory_yellow_gate_pier_count"] = yellow_gate_pier_count
        self.root["factory_generator_revision"] = 3
        return self.objects, {
            "id": f"factory_{fid}",
            "type": "factory-building",
            "variant": variant_name,
            "center": list(request.location),
            "yaw": request.yaw,
            "scale": scale,
            "dimensions_m": list(dims),
            "component_count": len(self.objects) - 1,
            "mesh_object_count": len(mesh_objects),
            "mesh_vertices": mesh_vertices,
            "mesh_polygons": mesh_polygons,
            "procedural": True,
            "modeling_quality": "production_architectural_detail_v3",
            "reference_image": FACTORY_REFERENCES[variant_name],
            "detail_systems": common_detail + variant_detail,
            "signage": list(self.signage_records),
            "signage_bounds_pass": signage_bounds_pass,
            "yellow_gate_pier_count": yellow_gate_pier_count,
            "security_detail_component_count": security_detail_component_count,
            "structural_detail_component_count": structural_detail_component_count,
            "rear_facade_detail_component_count": rear_facade_detail_component_count,
            "advanced_igu_component_count": advanced_igu_component_count,
            "standing_seam_detail_component_count": standing_seam_detail_component_count,
            "front_hedge_component_count": front_hedge_component_count,
            "generator_revision": 3,
            "pipeline_asset_request": {
                "asset_type": request.asset_type,
                "semantic": request.semantic,
            },
        }

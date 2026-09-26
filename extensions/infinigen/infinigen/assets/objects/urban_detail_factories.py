"""High-detail procedural urban factories layered on top of the base urban scene."""

from __future__ import annotations

import math
from dataclasses import dataclass

import bpy
import numpy as np

from infinigen.assets.utils.urban_primitives import (
    cube_obj,
    cylinder_between,
    cylinder_obj,
    ellipsoid_obj,
    multi_curve_obj,
    torus_obj,
)


def ensure_mat(name, color, roughness=0.65, metallic=0.0, emission_strength=0.0):
    mat = bpy.data.materials.get(name)
    if mat is not None:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission_strength and "Emission Color" in bsdf.inputs:
            bsdf.inputs["Emission Color"].default_value = color
            bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat


def material_pack():
    return {
        "tar": ensure_mat("urban_detail_mat_tar_sealant", (0.004, 0.004, 0.004, 1), roughness=0.92),
        "asphalt_pebble": ensure_mat("urban_detail_mat_asphalt_pebble", (0.11, 0.105, 0.095, 1), roughness=0.96),
        "dust": ensure_mat("urban_detail_mat_road_dust", (0.34, 0.32, 0.27, 1), roughness=0.98),
        "curb_chip": ensure_mat("urban_detail_mat_curb_chip", (0.78, 0.75, 0.67, 1), roughness=0.9),
        "reflector": ensure_mat("urban_detail_mat_lane_reflector", (1.0, 0.82, 0.32, 1), roughness=0.28, emission_strength=0.08),
        "rubber": ensure_mat("urban_detail_mat_tire_rubber", (0.006, 0.006, 0.005, 1), roughness=0.86),
        "chrome": ensure_mat("urban_detail_mat_chrome_trim", (0.62, 0.64, 0.62, 1), roughness=0.34, metallic=0.55),
        "glass_highlight": ensure_mat("urban_detail_mat_glass_highlight", (0.52, 0.78, 0.92, 0.72), roughness=0.12),
        "brick_variation": ensure_mat("urban_detail_mat_brick_variation", (0.58, 0.25, 0.19, 1), roughness=0.86),
        "mortar": ensure_mat("urban_detail_mat_mortar", (0.68, 0.64, 0.58, 1), roughness=0.94),
        "black_metal": ensure_mat("urban_detail_mat_black_metal", (0.025, 0.026, 0.024, 1), roughness=0.62, metallic=0.35),
        "poster": ensure_mat("urban_detail_mat_poster", (0.78, 0.68, 0.46, 1), roughness=0.72),
        "sticker_blue": ensure_mat("urban_detail_mat_sticker_blue", (0.04, 0.18, 0.72, 1), roughness=0.5),
        "paint_white": ensure_mat("urban_detail_mat_old_white_paint", (0.88, 0.86, 0.76, 1), roughness=0.82),
        "lamp_glow": ensure_mat("urban_detail_mat_warm_lamp_glow", (1.0, 0.78, 0.38, 1), roughness=0.2, emission_strength=0.55),
    }


@dataclass(frozen=True)
class UrbanDetailContext:
    block_extent: float = 64.0
    road_width: float = 8.0
    sidewalk_width: float = 3.0
    seed: int = 2026


class RoadFactory:
    """Road surface details: aggregate, tar seams, reflectors, curb wear."""

    def __init__(self, mats, ctx: UrbanDetailContext):
        self.mats = mats
        self.ctx = ctx
        self.rng = np.random.default_rng(ctx.seed + 11)

    def create(self):
        objs = []
        half = self.ctx.block_extent / 2
        half_road = self.ctx.road_width / 2

        for i in range(170):
            on_x_road = self.rng.random() < 0.5
            if on_x_road:
                x = self.rng.uniform(-half + 4, half - 4)
                y = self.rng.uniform(-half_road + 0.45, half_road - 0.45)
            else:
                x = self.rng.uniform(-half_road + 0.45, half_road - 0.45)
                y = self.rng.uniform(-half + 4, half - 4)
            sx = self.rng.uniform(0.035, 0.16)
            sy = self.rng.uniform(0.018, 0.09)
            obj = cube_obj(
                f"urban_detail:road:aggregate:{i:03d}",
                (x, y, 0.106 + self.rng.uniform(0, 0.006)),
                (sx, sy, 0.006),
                self.mats["asphalt_pebble"] if i % 3 else self.mats["dust"],
                "road-micro-detail",
                bevel=0.002,
            )
            obj.rotation_euler[2] = self.rng.uniform(0, math.tau)
            objs.append(obj)

        tar_paths = []
        for i in range(18):
            horizontal = i % 2 == 0
            base = self.rng.uniform(-half_road * 0.75, half_road * 0.75)
            start = self.rng.uniform(-half + 6, half - 14)
            length = self.rng.uniform(4.5, 11.0)
            points = []
            for j in range(7):
                t = j / 6
                wiggle = math.sin(t * math.tau * self.rng.uniform(0.7, 1.4) + i) * self.rng.uniform(0.06, 0.18)
                if horizontal:
                    points.append((start + length * t, base + wiggle, 0.128))
                else:
                    points.append((base + wiggle, start + length * t, 0.128))
            tar_paths.append(points)
        objs.append(multi_curve_obj("urban_detail:road:tar_snakes", tar_paths, 0.018, self.mats["tar"], "road-crack", resolution=2))

        for i, x in enumerate(np.linspace(-26, 26, 9)):
            for y in (-1.95, 1.95):
                objs.append(
                    cube_obj(
                        f"urban_detail:road:lane_reflector:x:{i}:{y}",
                        (float(x), y, 0.145),
                        (0.18, 0.075, 0.028),
                        self.mats["reflector"],
                        "lane-reflector",
                        bevel=0.018,
                    )
                )
        for i, y in enumerate(np.linspace(-26, 26, 9)):
            for x in (-1.95, 1.95):
                objs.append(
                    cube_obj(
                        f"urban_detail:road:lane_reflector:y:{i}:{x}",
                        (x, float(y), 0.145),
                        (0.075, 0.18, 0.028),
                        self.mats["reflector"],
                        "lane-reflector",
                        bevel=0.018,
                    )
                )

        chip_spots = [(-7.2, 7.2), (7.2, 7.2), (7.2, -7.2), (-7.2, -7.2), (-29, 4.2), (29, -4.0), (4.3, 29), (-4.5, -29)]
        for i, (x, y) in enumerate(chip_spots):
            objs.append(
                cube_obj(
                    f"urban_detail:curb:exposed_chip:{i}",
                    (x, y, 0.245),
                    (self.rng.uniform(0.28, 0.62), self.rng.uniform(0.05, 0.13), 0.022),
                    self.mats["curb_chip"],
                    "curb-wear",
                    bevel=0.01,
                )
            )
            objs[-1].rotation_euler[2] = self.rng.uniform(0, math.tau)
        return objs


class VehicleDetailFactory:
    """Adds close-up vehicle trim, tread, glass highlights, and tiny labels."""

    VEHICLES = [
        ("car_westbound", -18, 1.75, "x", 3.7, 1.62),
        ("car_eastbound", 21, -1.65, "x", 3.7, 1.62),
        ("car_southbound", -1.65, -22, "y", 3.7, 1.62),
        ("bus_northbound", 1.65, 18, "y", 5.6, 1.86),
    ]

    def __init__(self, mats, ctx: UrbanDetailContext):
        self.mats = mats
        self.ctx = ctx

    def _loc(self, x, y, fwd, lat, z, axis):
        return (x + fwd, y + lat, z) if axis == "x" else (x + lat, y + fwd, z)

    def _dims(self, fwd, lat, z, axis):
        return (fwd, lat, z) if axis == "x" else (lat, fwd, z)

    def create(self):
        objs = []
        for vid, x, y, axis, length, width in self.VEHICLES:
            is_bus = "bus" in vid
            side_lat = width * 0.56
            for side, lat in (("l", -side_lat), ("r", side_lat)):
                objs.append(cube_obj(f"urban_detail:vehicle:chrome_belt:{vid}:{side}", self._loc(x, y, 0, lat, 0.92, axis), self._dims(length * 0.78, 0.018, 0.035, axis), self.mats["chrome"], "vehicle-trim", bevel=0.004))
                objs.append(cube_obj(f"urban_detail:vehicle:lower_shadow:{vid}:{side}", self._loc(x, y, 0, lat * 1.01, 0.30, axis), self._dims(length * 0.88, 0.026, 0.06, axis), self.mats["rubber"], "vehicle-trim", bevel=0.004))
            for fwd in (-length * 0.32, length * 0.32):
                for lat in (-width * 0.48, width * 0.48):
                    wheel = self._loc(x, y, fwd, lat, 0.34, axis)
                    for k, ang in enumerate(np.linspace(0, math.tau, 10, endpoint=False)):
                        if axis == "x":
                            p0 = (wheel[0] + math.cos(ang) * 0.14, wheel[1], wheel[2] + math.sin(ang) * 0.14)
                            p1 = (wheel[0] + math.cos(ang) * 0.31, wheel[1], wheel[2] + math.sin(ang) * 0.31)
                        else:
                            p0 = (wheel[0], wheel[1] + math.cos(ang) * 0.14, wheel[2] + math.sin(ang) * 0.14)
                            p1 = (wheel[0], wheel[1] + math.cos(ang) * 0.31, wheel[2] + math.sin(ang) * 0.31)
                        objs.append(cylinder_between(f"urban_detail:vehicle:tire_groove:{vid}:{fwd:.1f}:{lat:.1f}:{k}", p0, p1, 0.006, self.mats["rubber"], "vehicle-tire-detail", vertices=6))
            if not is_bus:
                objs.append(cube_obj(f"urban_detail:vehicle:windshield_highlight:{vid}", self._loc(x, y, 0.08, 0, 1.34, axis), self._dims(0.72, 0.86, 0.018, axis), self.mats["glass_highlight"], "vehicle-glass-highlight", bevel=0.008))
                objs.append(cube_obj(f"urban_detail:vehicle:rear_window_highlight:{vid}", self._loc(x, y, -0.92, 0, 1.22, axis), self._dims(0.45, 0.78, 0.018, axis), self.mats["glass_highlight"], "vehicle-glass-highlight", bevel=0.008))
            else:
                for i, fwd in enumerate([-1.8, -0.8, 0.2, 1.2]):
                    objs.append(cube_obj(f"urban_detail:vehicle:bus_window_highlight:{vid}:{i}", self._loc(x, y, fwd, -width * 0.545, 1.34, axis), self._dims(0.42, 0.018, 0.045, axis), self.mats["glass_highlight"], "vehicle-glass-highlight", bevel=0.003))
                objs.append(cube_obj(f"urban_detail:vehicle:bus_route_leds:{vid}", self._loc(x, y, length / 2 + 0.065, 0, 1.66, axis), self._dims(0.014, 0.34, 0.055, axis), self.mats["lamp_glow"], "vehicle-route-display", bevel=0.002))
        return objs


class StreetFurnitureDetailFactory:
    """Adds bolts, cables, lamp glow, sign decals, and street-level clutter."""

    def __init__(self, mats, ctx: UrbanDetailContext):
        self.mats = mats
        self.ctx = ctx

    def create(self):
        objs = []
        lamp_positions = [(-24, 6.16), (-12, 6.16), (12, 6.16), (24, 6.16), (-24, -6.16), (24, -6.16), (-6.16, 14), (6.16, -14)]
        for i, (x, y) in enumerate(lamp_positions):
            objs.append(ellipsoid_obj(f"urban_detail:street_lamp:glow:{i}", (x, y - math.copysign(0.72, y if abs(y) > abs(x) else x), 3.17), (0.16, 0.16, 0.07), self.mats["lamp_glow"], "street-lamp-glow", segments=20))
            objs.append(cylinder_obj(f"urban_detail:street_lamp:access_panel:{i}", (x, y, 0.82), 0.058, 0.015, self.mats["black_metal"], "street-lamp-detail", vertices=12))
        for i, x in enumerate([-16.8, -15.5, -14.2]):
            objs.append(cylinder_between(f"urban_detail:bus_stop:roof_drain:{i}", (x, -7.86, 2.18), (x, -7.86, 0.28), 0.014, self.mats["black_metal"], "bus-stop-detail", vertices=8))
        for i, (x, y) in enumerate([(-9.4, -6.95), (8.7, -10.55), (9.6, -10.55), (15.0, -11.85), (21.0, -11.85)]):
            objs.append(cube_obj(f"urban_detail:street_clutter:paper:{i}", (x, y, 0.185), (0.32, 0.18, 0.006), self.mats["poster"], "street-litter", bevel=0.002))
            objs[-1].rotation_euler[2] = 0.4 * i
        for i, (x, y) in enumerate([(3.8, 4.65), (-15.5, -7.31), (18.0, -17.0)]):
            objs.append(cube_obj(f"urban_detail:decal:blue_sticker:{i}", (x, y, 1.82 if i == 0 else 1.25), (0.24, 0.012, 0.16), self.mats["sticker_blue"], "decal", bevel=0.002))
        return objs


class FacadeDetailFactory:
    """Adds mortar courses, fire escapes, balconies, posters, and facade depth."""

    BUILDINGS = [
        ("anchor_northwest", -18, 12.2, 13.0, 8.0, "y", -1),
        ("background_northeast", 18, 12.8, 14.0, 8.5, "y", -1),
        ("background_west", -12.5, -16, 8.0, 13.0, "x", 1),
        ("background_southwest", -17, -12.6, 13.0, 8.0, "y", 1),
        ("background_east", 12.6, 18, 8.0, 13.0, "x", -1),
    ]

    def __init__(self, mats, ctx: UrbanDetailContext):
        self.mats = mats
        self.ctx = ctx

    def _front(self, x, y, width, depth, axis, sign, a, z, out=0.09):
        if axis == "y":
            return (a, y + sign * depth / 2 + sign * out, z)
        return (x + sign * width / 2 + sign * out, a, z)

    def _dims(self, axis, width, depth, sx, sz, thin=0.026):
        return (sx, thin, sz) if axis == "y" else (thin, sx, sz)

    def create(self):
        objs = []
        for bid, x, y, width, depth, axis, sign in self.BUILDINGS:
            building = bpy.data.objects.get(f"urban:building:{bid}")
            if building is None:
                continue
            height = building.dimensions.z
            span = width if axis == "y" else depth
            span_min = (x if axis == "y" else y) - span * 0.44
            span_max = (x if axis == "y" else y) + span * 0.44
            for floor, z in enumerate(np.arange(2.65, max(2.7, height - 0.4), 0.38)):
                if floor % 2:
                    continue
                objs.append(cube_obj(f"urban_detail:facade:mortar_course:{bid}:{floor}", self._front(x, y, width, depth, axis, sign, (span_min + span_max) / 2, float(z)), self._dims(axis, width, depth, span * 0.86, 0.018, thin=0.018), self.mats["mortar"], "facade-mortar", bevel=0.0))
            for i, a in enumerate(np.linspace(span_min + 0.6, span_max - 0.6, 7)):
                objs.append(cube_obj(f"urban_detail:facade:brick_variation:{bid}:{i}", self._front(x, y, width, depth, axis, sign, float(a), 1.25 + (i % 4) * 1.1, 0.102), self._dims(axis, width, depth, 0.46, 0.18, thin=0.018), self.mats["brick_variation"], "facade-brick-variation", bevel=0.0))
            escape_z = min(height - 1.2, 5.2)
            rail_span = min(3.2, span * 0.42)
            rail_a = (span_min + span_max) * 0.5
            objs.append(cube_obj(f"urban_detail:facade:fire_escape_platform:{bid}", self._front(x, y, width, depth, axis, sign, rail_a, escape_z - 0.58, 0.55), self._dims(axis, width, depth, rail_span, 0.06, thin=0.72), self.mats["black_metal"], "fire-escape", bevel=0.01))
            for j, off in enumerate(np.linspace(-rail_span / 2, rail_span / 2, 6)):
                p0 = self._front(x, y, width, depth, axis, sign, rail_a + off, escape_z - 0.45, 0.72)
                p1 = self._front(x, y, width, depth, axis, sign, rail_a + off, escape_z + 0.35, 0.72)
                objs.append(cylinder_between(f"urban_detail:facade:fire_escape_baluster:{bid}:{j}", p0, p1, 0.012, self.mats["black_metal"], "fire-escape", vertices=6))
            for p, z in enumerate([1.35, 1.72]):
                objs.append(cube_obj(f"urban_detail:facade:poster:{bid}:{p}", self._front(x, y, width, depth, axis, sign, span_min + 0.95 + p * 0.55, z, 0.12), self._dims(axis, width, depth, 0.42, 0.54, thin=0.015), self.mats["poster" if p == 0 else "sticker_blue"], "poster", bevel=0.002))
        return objs


def apply_urban_detail_factories(block_extent=64.0, road_width=8.0, sidewalk_width=3.0, seed=2026):
    mats = material_pack()
    ctx = UrbanDetailContext(block_extent=block_extent, road_width=road_width, sidewalk_width=sidewalk_width, seed=seed)
    objs = []
    for factory in (
        RoadFactory(mats, ctx),
        VehicleDetailFactory(mats, ctx),
        StreetFurnitureDetailFactory(mats, ctx),
        FacadeDetailFactory(mats, ctx),
    ):
        objs.extend(factory.create())
    return objs

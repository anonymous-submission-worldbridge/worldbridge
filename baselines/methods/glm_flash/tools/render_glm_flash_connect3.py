#!/usr/bin/env python3
"""Render dense connect3 scenes with broader indoor/outdoor visual coverage."""

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


import json
import math
from pathlib import Path
import subprocess
import sys

import bpy

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.render_glm_flash_connect as base
import baselines.methods.glm_flash.tools.render_glm_flash_connect2 as c2


OUTPUT = base.BASELINES / "annotations/glm53_flash/connect3"
SCENES = (
    "rowhouse_living_dining",
    "apartment_kitchen_balcony",
    "suburban_family_room",
    "duplex_home_office_lounge",
    "neighborhood_pharmacy",
    "local_grocery_market",
    "casual_family_restaurant",
    "hardware_home_store",
)
RESIDENTIAL = set(SCENES[:4])

IMAGE_ROLES = (
    "indoor_overview",
    "indoor_overview_rear",
    "indoor_detail_left",
    "indoor_detail_right",
    "inside_to_outside_rear_center",
    "inside_to_outside_rear_left",
    "inside_to_outside_rear_right",
    "inside_to_outside_mid_center",
    "inside_to_outside_mid_left",
    "inside_to_outside_mid_right",
    "inside_to_outside_high",
    "inside_to_outside_entry_oblique",
    "outdoor_overview_high",
    "outdoor_streetscape_left",
    "outdoor_streetscape_right",
    "outdoor_entry_context",
    "outside_to_inside_street_center",
    "outside_to_inside_street_left",
    "outside_to_inside_street_right",
    "outside_to_inside_context_high",
    "outside_to_inside_mid_center",
    "outside_to_inside_mid_left",
    "outside_to_inside_mid_right",
    "outside_to_inside_entry_oblique",
)


class DenseSceneAPI(c2.DetailedSceneAPI):
    def _parent_new_objects(self, name, location_xyz, before):
        parent = bpy.data.objects.new(name, None)
        bpy.context.scene.collection.objects.link(parent)
        parent.location = tuple(float(value) for value in location_xyz)
        for obj in tuple(bpy.context.scene.objects):
            if obj in before or obj == parent:
                continue
            world_matrix = obj.matrix_world.copy()
            obj.parent = parent
            obj.matrix_world = world_matrix
        self.created.append(parent)
        return parent

    def tree(
        self,
        name,
        location_xyz,
        trunk_height,
        crown_radius,
        trunk_material,
        leaf_material,
    ):
        before = set(bpy.context.scene.objects)
        super().tree(
            name,
            location_xyz,
            trunk_height,
            crown_radius,
            trunk_material,
            leaf_material,
        )
        return self._parent_new_objects(name, location_xyz, before)

    def lamp(self, name, location_xyz, height, pole_material, light_material):
        before = set(bpy.context.scene.objects)
        super().lamp(name, location_xyz, height, pole_material, light_material)
        return self._parent_new_objects(name, location_xyz, before)

    def building(
        self,
        name,
        location_xyz,
        size_xyz,
        facade_material,
        trim_material,
        glass_material,
    ):
        x, y, z = (float(value) for value in location_xyz)
        sx, sy, sz = (max(1.0, abs(float(value))) for value in size_xyz)
        self.box(
            name + "_mass", (x, y, z + sz / 2), (sx, sy, sz), facade_material, 0.06
        )
        front_y = y - sy / 2 - 0.025
        self.box(
            name + "_ground_course",
            (x, front_y, z + 0.24),
            (sx * 0.98, 0.07, 0.46),
            trim_material,
            0.018,
        )
        self.box(
            name + "_cornice",
            (x, front_y, z + sz - 0.10),
            (sx + 0.20, 0.16, 0.20),
            trim_material,
            0.035,
        )
        floor_count = 2
        columns = 2
        for floor in range(floor_count):
            wz = z + 1.45 + floor * (sz - 1.9) / max(1, floor_count - 1)
            for column in range(columns):
                wx = x - sx * 0.34 + column * sx * 0.68 / max(1, columns - 1)
                ww = min(1.25, sx / columns * 0.55)
                window_name = f"{name}_window_{floor}_{column}"
                self.box(
                    window_name + "_trim",
                    (wx, front_y - 0.01, wz),
                    (ww + 0.14, 0.07, 1.34),
                    trim_material,
                    0.018,
                )
                self.box(
                    window_name + "_glass",
                    (wx, front_y - 0.055, wz),
                    (ww, 0.025, 1.16),
                    glass_material,
                    0.008,
                )
                self.box(
                    window_name + "_mullion",
                    (wx, front_y - 0.078, wz),
                    (0.045, 0.022, 1.13),
                    trim_material,
                    0.006,
                )
        self.box(
            name + "_door",
            (x, front_y - 0.045, z + 1.05),
            (0.92, 0.08, 2.10),
            trim_material,
            0.025,
        )
        self.box(
            name + "_door_glass",
            (x, front_y - 0.092, z + 1.30),
            (0.62, 0.025, 1.30),
            glass_material,
            0.008,
        )
        self.box(
            name + "_awning",
            (x, front_y - 0.48, z + 2.48),
            (sx * 0.56, 0.92, 0.12),
            trim_material,
            0.025,
        )

        # Cameras looking back toward the connected room see the north/rear
        # faces of the neighboring buildings.  Detail those faces as real
        # facades too, rather than exposing plain building masses.
        rear_y = y + sy / 2 + 0.025
        self.box(
            name + "_rear_ground_course",
            (x, rear_y, z + 0.24),
            (sx * 0.98, 0.07, 0.46),
            trim_material,
            0.018,
        )
        self.box(
            name + "_rear_cornice",
            (x, rear_y, z + sz - 0.10),
            (sx + 0.20, 0.16, 0.20),
            trim_material,
            0.035,
        )
        for floor in range(floor_count):
            wz = z + 1.45 + floor * (sz - 1.9) / max(1, floor_count - 1)
            for column in range(columns):
                wx = x - sx * 0.34 + column * sx * 0.68 / max(1, columns - 1)
                ww = min(1.25, sx / columns * 0.55)
                window_name = f"{name}_rear_window_{floor}_{column}"
                self.box(
                    window_name + "_trim",
                    (wx, rear_y + 0.01, wz),
                    (ww + 0.14, 0.07, 1.34),
                    trim_material,
                    0.018,
                )
                self.box(
                    window_name + "_glass",
                    (wx, rear_y + 0.055, wz),
                    (ww, 0.025, 1.16),
                    glass_material,
                    0.008,
                )
                self.box(
                    window_name + "_mullion",
                    (wx, rear_y + 0.078, wz),
                    (0.045, 0.022, 1.13),
                    trim_material,
                    0.006,
                )
        self.box(
            name + "_rear_door",
            (x, rear_y + 0.045, z + 1.05),
            (0.92, 0.08, 2.10),
            trim_material,
            0.025,
        )
        self.box(
            name + "_rear_door_glass",
            (x, rear_y + 0.092, z + 1.30),
            (0.62, 0.025, 1.30),
            glass_material,
            0.008,
        )
        self.box(
            name + "_rear_awning",
            (x, rear_y + 0.48, z + 2.48),
            (sx * 0.56, 0.92, 0.12),
            trim_material,
            0.025,
        )

    def display_unit(
        self,
        name,
        location_xyz,
        size_xyz,
        frame_material,
        product_material,
        accent_material,
    ):
        """Detailed retail fixture with correctly placed individual products."""
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

    def parked_car(
        self,
        name,
        location_xyz,
        yaw_degrees,
        body_material,
        trim_material,
        glass_material=None,
    ):
        if glass_material is None:
            # Tolerate GLM's compact variant:
            # parked_car(name, (x, y, yaw), body, trim, glass).
            x, y, embedded_yaw = (float(value) for value in location_xyz)
            location_xyz = (x, y, 0.0)
            yaw_degrees, body_material, trim_material, glass_material = (
                embedded_yaw,
                yaw_degrees,
                body_material,
                trim_material,
            )
        x, y, z = (float(value) for value in location_xyz)
        parent = bpy.data.objects.new(name + "_group", None)
        bpy.context.collection.objects.link(parent)
        parent.location = (x, y, z)
        parent.rotation_euler[2] = math.radians(float(yaw_degrees))
        parts = (
            ("lower_body", (0, 0, 0.48), (3.7, 1.62, 0.58), body_material, 0.18),
            ("hood", (1.18, 0, 0.82), (1.15, 1.52, 0.28), body_material, 0.15),
            ("cabin", (-0.35, 0, 1.05), (1.75, 1.42, 0.68), body_material, 0.20),
            (
                "windshield",
                (0.30, -0.72, 1.13),
                (0.92, 0.035, 0.50),
                glass_material,
                0.02,
            ),
            (
                "rear_window",
                (-1.05, -0.72, 1.10),
                (0.48, 0.035, 0.42),
                glass_material,
                0.02,
            ),
            ("front_bumper", (1.87, 0, 0.42), (0.12, 1.48, 0.20), trim_material, 0.04),
            ("rear_bumper", (-1.87, 0, 0.42), (0.12, 1.48, 0.20), trim_material, 0.04),
        )
        for suffix, location, size, material, bevel in parts:
            obj = self.box(name + "_" + suffix, location, size, material, bevel)
            if obj is not None:
                obj.parent = parent
        for axle_x in (-1.15, 1.15):
            for side_y in (-0.80, 0.80):
                wheel = self.cylinder(
                    f"{name}_wheel_{axle_x}_{side_y}",
                    (axle_x, side_y, 0.36),
                    0.32,
                    0.18,
                    trim_material,
                    32,
                )
                wheel.parent = parent
        self.created.append(parent)


def ensure_core(api: DenseSceneAPI, scene_id: str) -> None:
    c2.ensure_core(api, scene_id)
    # Give the connected room a believable two-storey residential/mixed-use
    # street frontage.  The occupied ground-floor room remains unchanged and
    # physically open; this mass sits entirely above its ceiling.
    api.box(
        "Harness_UpperFloorMass",
        (0, -4.50, 5.18),
        (12.20, 9.20, 3.02),
        "Harness_WarmWall",
        0.025,
    )
    api.box(
        "Harness_MainFacadePlinthLeft",
        (-3.65, 0.16, 0.30),
        (4.90, 0.12, 0.52),
        "Harness_Stone",
        0.018,
    )
    api.box(
        "Harness_MainFacadePlinthRight",
        (3.65, 0.16, 0.30),
        (4.90, 0.12, 0.52),
        "Harness_Stone",
        0.018,
    )
    api.box(
        "Harness_MainFacadeCornice",
        (0, 0.18, 6.64),
        (12.35, 0.26, 0.24),
        "Harness_DarkTrim",
        0.035,
    )
    api.box(
        "Harness_EntryCanopy",
        (0, 0.62, 3.08),
        (3.25, 1.10, 0.14),
        "Harness_DarkTrim",
        0.035,
    )
    for index, x in enumerate((-4.45, -1.75, 1.75, 4.45)):
        api.window(
            f"Harness_UpperFacadeWindow_{index}",
            (x, 0.19, 4.88),
            (1.35, 0.06, 1.52),
            "Harness_DarkTrim",
            "Harness_Glass",
        )
    for side, x in (("Left", -3.72), ("Right", 3.72)):
        api.window(
            f"Harness_GroundFacadeWindow_{side}",
            (x, 0.19, 1.82),
            (1.62, 0.06, 1.58),
            "Harness_DarkTrim",
            "Harness_Glass",
        )


def add_dense_context(api: DenseSceneAPI, scene_id: str) -> None:
    api.mat("Context_WarmBrick", (0.45, 0.20, 0.13), roughness=0.86)
    api.mat("Context_PaleStucco", (0.68, 0.66, 0.59), roughness=0.88)
    api.mat("Context_MutedBlue", (0.27, 0.36, 0.44), roughness=0.80)
    api.mat("Context_DarkTrim", (0.055, 0.060, 0.065), metallic=0.18, roughness=0.34)
    api.mat("Context_Glass", (0.28, 0.48, 0.58), roughness=0.12)
    api.mat("Context_Asphalt", (0.11, 0.12, 0.13), roughness=0.94)
    api.mat("Context_RoadLine", (0.78, 0.72, 0.48), roughness=0.70)
    api.mat("Context_Sidewalk", (0.48, 0.48, 0.45), roughness=0.92)
    api.mat("Context_CarBlue", (0.10, 0.24, 0.37), metallic=0.42, roughness=0.30)
    api.mat("Context_CarRust", (0.52, 0.16, 0.08), metallic=0.30, roughness=0.35)
    api.mat("Context_Trunk", (0.25, 0.12, 0.055), roughness=0.88)
    api.mat("Context_Leaf", (0.10, 0.30, 0.075), roughness=0.82)

    api.box(
        "Context_FrontSidewalk",
        (0, 5.0, 0.015),
        (36.0, 9.8, 0.11),
        "Context_Sidewalk",
        0.008,
    )
    api.road(
        "Context_NeighborhoodRoad",
        (0, 14.2, -0.015),
        (36.0, 7.0, 0.12),
        "Context_Asphalt",
        "Context_RoadLine",
    )
    api.box(
        "Context_FarSidewalk",
        (0, 20.1, 0.02),
        (36.0, 4.7, 0.13),
        "Context_Sidewalk",
        0.008,
    )

    buildings = (
        (
            "Context_Block_LeftNear",
            (-8.9, 4.8, 0),
            (5.6, 7.6, 7.2),
            "Context_WarmBrick",
        ),
        (
            "Context_Block_RightNear",
            (8.9, 4.8, 0),
            (5.6, 7.6, 7.6),
            "Context_PaleStucco",
        ),
        (
            "Context_Block_LeftMid",
            (-12.0, 14.0, 0),
            (6.0, 7.2, 8.8),
            "Context_MutedBlue",
        ),
        (
            "Context_Block_RightMid",
            (12.0, 14.0, 0),
            (6.0, 7.2, 8.2),
            "Context_WarmBrick",
        ),
        (
            "Context_Block_FarLeft",
            (-8.0, 23.0, 0),
            (7.2, 3.8, 8.4),
            "Context_PaleStucco",
        ),
        (
            "Context_Block_FarCenter",
            (0.0, 23.2, 0),
            (7.2, 3.8, 9.2),
            "Context_MutedBlue",
        ),
        (
            "Context_Block_FarRight",
            (8.0, 23.0, 0),
            (7.2, 3.8, 7.8),
            "Context_WarmBrick",
        ),
    )
    for name, location, size, material in buildings:
        api.building(
            name, location, size, material, "Context_DarkTrim", "Context_Glass"
        )

    # Keep the context trees close to the flanking building fronts.  At
    # x=+/-6.5 the y=12.5 row sat too close to the long-view cameras and its
    # crown could fill half of a frame despite leaving the physical path clear.
    for side, x in (("Left", -8.6), ("Right", 8.6)):
        for index, y in enumerate((3.0, 8.0, 12.5, 18.6)):
            api.tree(
                f"Context_Tree_{side}_{index}",
                (x, y, 0),
                2.4 + 0.2 * (index % 2),
                1.25,
                "Context_Trunk",
                "Context_Leaf",
            )
        for index, y in enumerate((5.4, 10.5, 18.2)):
            api.lamp(
                f"Context_StreetLamp_{side}_{index}",
                (x * 0.90, y, 0),
                3.2,
                "Context_DarkTrim",
                "Harness_Glow",
            )
    api.parked_car(
        "Context_ParkedCar_Left",
        (-4.3, 15.0, 0),
        0,
        "Context_CarBlue",
        "Context_DarkTrim",
        "Context_Glass",
    )
    api.parked_car(
        "Context_ParkedCar_Right",
        (4.4, 17.2, 0),
        180,
        "Context_CarRust",
        "Context_DarkTrim",
        "Context_Glass",
    )
    for side, x in (("Left", -7.0), ("Right", 7.0)):
        api.box(
            f"Context_BenchSeat_{side}",
            (x, 7.2, 0.48),
            (1.65, 0.48, 0.12),
            "Harness_OakFloor",
            0.04,
        )
        api.box(
            f"Context_BenchBack_{side}",
            (x, 7.43, 0.86),
            (1.65, 0.10, 0.66),
            "Harness_OakFloor",
            0.04,
        )
        for leg_x in (-0.60, 0.60):
            api.box(
                f"Context_BenchLeg_{side}_{leg_x}",
                (x + leg_x, 7.2, 0.23),
                (0.09, 0.38, 0.46),
                "Context_DarkTrim",
                0.02,
            )


def add_refinement_pass(api: DenseSceneAPI, scene_id: str) -> None:
    if scene_id == "apartment_kitchen_balcony":
        proxy = "suburban_kitchen_dining"
    elif scene_id in RESIDENTIAL:
        proxy = "apartment_living_room"
    else:
        proxy = "corner_convenience_store"
    c2.add_refinement_pass(api, proxy)
    add_dense_context(api, scene_id)


def enforce_open_connection() -> dict[str, object]:
    connection = c2.enforce_open_connection()
    roots = {}
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH" or obj.name.startswith(("Harness_", "Context_")):
            continue
        low, high = base.world_bbox(obj)
        crosses_entry_route = (
            low.x < 0.72
            and high.x > -0.72
            and low.y < 4.80
            and high.y > 0.24
            and low.z < 2.20
            and high.z > 0.10
        )
        if not crosses_entry_route:
            continue
        root = obj
        while root.parent is not None:
            root = root.parent
        roots[root.name] = root
    moved = []
    for index, root in enumerate(roots.values()):
        direction = -1.0 if index % 2 == 0 else 1.0
        root.location.x += direction * 2.85
        moved.append(root.name)

    # Keep a wider *visual* corridor through the foreground streetscape.  The
    # narrower pass above guarantees physical traversal through the doorway;
    # this second pass prevents a tree crown, planter or lamp generated near
    # the road centre from dominating the long indoor/outdoor sight lines.
    # Context_* objects are already deliberately placed on the flanks, so only
    # scene-authored exterior props are adjusted here.
    sight_roots = {}
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH" or obj.name.startswith(("Harness_", "Context_")):
            continue
        low, high = base.world_bbox(obj)
        crosses_sight_corridor = (
            low.x < 3.20
            and high.x > -3.20
            and low.y < 16.0
            and high.y > 4.50
            and low.z < 8.0
            and high.z > 0.10
        )
        if not crosses_sight_corridor:
            continue
        root = obj
        while root.parent is not None:
            root = root.parent
        movable_name = root.name.lower()
        if not any(
            token in movable_name
            for token in (
                "tree",
                "planter",
                "plant",
                "lamp",
                "car",
                "bench",
                "bike",
                "bicycle",
                "bollard",
                "sign",
            )
        ):
            continue
        if root.name not in roots:
            sight_roots[root.name] = root
    for index, root in enumerate(sight_roots.values()):
        if root.location.x < -0.05:
            direction = -1.0
        elif root.location.x > 0.05:
            direction = 1.0
        else:
            direction = -1.0 if index % 2 == 0 else 1.0
        # A prop authored exactly on the centreline needs a larger shift than
        # one already close to a flank: at long focal distances even a tree at
        # x=4 m can still occupy half of a 28 mm frame.
        shift = 7.50 if abs(float(root.location.x)) <= 1.0 else 4.25
        root.location.x += direction * shift
        moved.append(root.name)
    connection["moved_corridor_blockers"] = moved
    return connection


def add_camera_and_lighting(scene_id: str):
    camera = c2.add_camera_and_lighting(scene_id)
    bpy.context.scene.view_settings.exposure = 0.15
    background = bpy.context.scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Strength"].default_value = 0.42
    sun = bpy.data.objects.get("DaylightSun")
    if sun is not None:
        sun.data.energy = 1.65
    exterior_fill = bpy.data.objects.get("ExteriorFill")
    if exterior_fill is not None:
        exterior_fill.data.energy = 680
    return camera


def render_stills(scene_root: Path, camera) -> list[dict[str, object]]:
    image_root = scene_root / "images"
    image_root.mkdir(parents=True, exist_ok=True)
    views = (
        ("indoor_overview", (0.0, -1.20, 2.22), (0.0, -6.20, 1.14), 24),
        ("indoor_overview_rear", (-4.75, -7.65, 2.18), (1.20, -4.20, 1.05), 25),
        ("indoor_detail_left", (4.75, -6.80, 1.72), (-2.20, -5.00, 1.00), 35),
        ("indoor_detail_right", (-4.75, -5.10, 1.72), (2.40, -6.40, 1.02), 35),
        ("inside_to_outside_rear_center", (0.0, -8.05, 1.78), (0.0, 8.0, 1.20), 24),
        ("inside_to_outside_rear_left", (-4.75, -7.45, 1.86), (0.35, 7.5, 1.18), 25),
        ("inside_to_outside_rear_right", (4.75, -7.45, 1.86), (-0.35, 7.5, 1.18), 25),
        ("inside_to_outside_mid_center", (0.0, -5.45, 1.70), (0.0, 8.5, 1.17), 27),
        ("inside_to_outside_mid_left", (-4.45, -4.85, 1.80), (0.30, 7.3, 1.15), 27),
        ("inside_to_outside_mid_right", (4.45, -4.85, 1.80), (-0.30, 7.3, 1.15), 27),
        ("inside_to_outside_high", (0.0, -7.80, 3.08), (0.0, 7.7, 1.02), 29),
        (
            "inside_to_outside_entry_oblique",
            (-2.40, -3.60, 2.05),
            (0.40, 6.0, 1.20),
            27,
        ),
        ("outdoor_overview_high", (0.0, 13.0, 7.2), (0.0, 4.2, 1.15), 27),
        ("outdoor_streetscape_left", (-1.6, 12.5, 2.65), (-1.0, 4.5, 1.20), 28),
        ("outdoor_streetscape_right", (1.6, 12.5, 2.65), (1.0, 4.5, 1.20), 28),
        ("outdoor_entry_context", (2.4, 9.5, 3.15), (0.0, 0.8, 1.42), 26),
        ("outside_to_inside_street_center", (0.0, 14.0, 2.45), (0.0, -5.4, 1.18), 28),
        ("outside_to_inside_street_left", (-1.6, 12.5, 2.70), (0.30, -5.1, 1.16), 28),
        ("outside_to_inside_street_right", (1.6, 12.5, 2.70), (-0.30, -5.1, 1.16), 28),
        ("outside_to_inside_context_high", (-3.0, 12.0, 6.3), (0.0, -3.8, 1.05), 31),
        ("outside_to_inside_mid_center", (0.0, 10.5, 1.82), (0.0, -5.4, 1.18), 28),
        ("outside_to_inside_mid_left", (-3.0, 10.8, 2.80), (0.30, -4.8, 1.14), 28),
        ("outside_to_inside_mid_right", (3.0, 10.8, 2.80), (-0.30, -4.8, 1.14), 28),
        ("outside_to_inside_entry_oblique", (0.0, 7.2, 1.92), (-1.0, -4.4, 1.16), 30),
    )
    if tuple(role for role, *_ in views) != IMAGE_ROLES:
        raise RuntimeError("internal connect3 still-role ordering mismatch")
    base.configure_render(*base.STILL_SIZE, samples=48)
    records = []
    for role, location, target, lens in views:
        offsets = (
            (0.0, 0.0, 0.0),
            (-1.5, 0.0, 0.0),
            (1.5, 0.0, 0.0),
            (-3.0, 0.0, 0.0),
            (3.0, 0.0, 0.0),
            (0.0, -1.5, 0.0),
            (0.0, 1.5, 0.0),
            (0.0, 0.0, 1.5),
        )
        safe_location = None
        for offset in offsets:
            candidate = tuple(
                float(value) + float(delta) for value, delta in zip(location, offset)
            )
            blocked = False
            for obj in bpy.context.scene.objects:
                if obj.type != "MESH":
                    continue
                low, high = base.world_bbox(obj)
                margin = 0.12
                if (
                    low.x - margin <= candidate[0] <= high.x + margin
                    and low.y - margin <= candidate[1] <= high.y + margin
                    and low.z - margin <= candidate[2] <= high.z + margin
                ):
                    blocked = True
                    break
            if not blocked:
                safe_location = candidate
                break
        if safe_location is None:
            raise RuntimeError(
                f"no collision-free camera candidate for {scene_root.name}/{role}"
            )
        base.look_at(camera, safe_location, target, lens)
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
                "camera_location": list(safe_location),
                "camera_target": list(target),
                "lens_mm": lens,
            }
        )
        print(f"GLM53_CONNECT3_IMAGE scene={scene_root.name} role={role}", flush=True)
    return records


def render_video(scene_root: Path, camera, frames: int) -> list[dict[str, object]]:
    """Render a compact complete traversal with proportionally spaced keys."""
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
        (max(2, round(frames * 0.28)), (0.28, -3.2, 1.61), (0.0, 1.4, 1.30), 30),
        (max(3, round(frames * 0.52)), (-0.05, -0.65, 1.60), (0.0, 4.5, 1.25), 29),
        (max(4, round(frames * 0.74)), (0.12, 3.0, 1.63), (0.0, 8.0, 1.20), 31),
        (frames, (1.8, 10.5, 1.72), (0.0, 14.0, 1.25), 34),
    )
    for frame, location, target, lens in keyframes:
        base.look_at(camera, location, target, lens)
        camera.keyframe_insert(data_path="location", frame=frame)
        camera.keyframe_insert(data_path="rotation_euler", frame=frame)
        camera.data.keyframe_insert(data_path="lens", frame=frame)
    if camera.animation_data and camera.animation_data.action:
        for curve in camera.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "BEZIER"
    base.configure_render(*base.VIDEO_SIZE, samples=16)
    scene.frame_start = 1
    scene.frame_end = frames
    scene.render.fps = base.FPS
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(forward)
    print(
        f"GLM53_CONNECT3_VIDEO_START scene={scene_root.name} frames={frames}",
        flush=True,
    )
    bpy.ops.render.render(animation=True)
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
                "width": base.VIDEO_SIZE[0],
                "height": base.VIDEO_SIZE[1],
                "fps": base.FPS,
                "frames": frames,
                "duration_seconds": frames / base.FPS,
                "bytes": path.stat().st_size,
                "sha256": base.sha256(path),
            }
        )
    print(f"GLM53_CONNECT3_VIDEO_COMPLETE scene={scene_root.name}", flush=True)
    return records


def main() -> int:
    result = base.main()
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    scene_id = arguments[arguments.index("--scene-id") + 1]
    output = (
        Path(arguments[arguments.index("--output") + 1])
        if "--output" in arguments
        else OUTPUT
    )
    manifest_path = output / scene_id / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[
        "image_policy"
    ] = "24 individual unlabelled PNG files; no montage, border, or embedded numbering"
    manifest["refinement"].update(
        {
            "level": "high-density",
            "still_view_count": 24,
            "connection_view_count": 16,
            "dense_surrounding_buildings": True,
            "empty_exterior_horizon_avoided": True,
        }
    )
    manifest["connectivity"].update(
        {
            "indoor_views_include_interior_overview_and_exterior_depth": True,
            "outdoor_views_include_streetscape_context_and_interior_depth": True,
        }
    )
    base.atomic_json(manifest_path, manifest)
    return result


base.DEFAULT_OUTPUT = OUTPUT
base.SCENE_IDS = SCENES
base.IMAGE_ROLES = IMAGE_ROLES
base.SceneAPI = DenseSceneAPI
base.ensure_core = ensure_core
base.add_refinement_pass = add_refinement_pass
base.enforce_open_connection = enforce_open_connection
base.add_camera_and_lighting = add_camera_and_lighting
base.render_stills = render_stills
base.render_video = render_video


if __name__ == "__main__":
    raise SystemExit(main())

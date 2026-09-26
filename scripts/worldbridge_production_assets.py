"""Production asset adapter used by the canonical WorldBridge Blender backend.

The descriptor remains responsible for planning and collision-free placement.
This module only realizes those approved placements with the detailed,
source-generated WorldBridge asset families.  Every asset is created in the
current Blender process; no saved scene or cached scene asset is read.
"""

from __future__ import annotations

import importlib.util
import math
from pathlib import Path
import random
import re
import traceback
from typing import Any

import bpy
from mathutils import Vector


ROOT = Path(__file__).resolve().parents[1]
# Two deliberately different full07 botanical masters provide rounded and
# columnar street-tree families.  Planned trees instance these dense masters;
# they never duplicate meshes or fall back to lightweight crowns.  Bounding
# the master library also keeps peak memory independent of planned tree count.
TREE_SEEDS = (42, 512)


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load production source module {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _objects_created(before: set[Any]) -> list[Any]:
    return [obj for obj in bpy.data.objects if obj not in before]


def _descends_from(obj: Any, possible_parent: Any) -> bool:
    current = obj.parent
    while current is not None:
        if current == possible_parent:
            return True
        current = current.parent
    return False


def _world_bounds(objects: list[Any]) -> tuple[Vector, Vector]:
    points = []
    for obj in objects:
        if obj.type not in {"MESH", "CURVE", "FONT", "SURFACE", "META"}:
            continue
        points.extend(obj.matrix_world @ Vector(corner) for corner in obj.bound_box)
    if not points:
        raise RuntimeError("production asset has no renderable bounds")
    return (
        Vector(
            (
                min(p.x for p in points),
                min(p.y for p in points),
                min(p.z for p in points),
            )
        ),
        Vector(
            (
                max(p.x for p in points),
                max(p.y for p in points),
                max(p.z for p in points),
            )
        ),
    )


def _request(spec, params=None):
    from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

    return UrbanAssetRequest(
        asset_type=spec.kind,
        location=spec.position,
        semantic=spec.semantic,
        yaw=math.radians(spec.yaw_deg),
        params={"id": spec.id, **(params or {})},
    )


class ProductionAssetSystem:
    """Stateful high-detail builders shared by every planned placement."""

    def __init__(self, world, mats: dict[str, Any]):
        self.world = world
        self.mats = mats
        self.tree_masters: dict[int, Any] = {}
        self._building_source = None
        self._building_materials = None
        self._building_assets = None
        self._building_root = None
        self.asset_records: list[dict[str, Any]] = []
        self._upgrade_materials()

    def _upgrade_materials(self) -> None:
        """Add the same mapped PBR variation used by the production city."""
        profiles = {
            "asphalt": ((0.025, 0.028, 0.030, 1), (0.11, 0.105, 0.095, 1), 19.0, 0.22),
            "concrete": ((0.42, 0.41, 0.38, 1), (0.69, 0.67, 0.61, 1), 13.0, 0.12),
            "residential_ground": (
                (0.10, 0.19, 0.055, 1),
                (0.28, 0.38, 0.13, 1),
                8.0,
                0.18,
            ),
            "park_ground": ((0.055, 0.17, 0.035, 1), (0.20, 0.34, 0.085, 1), 7.0, 0.22),
            "commercial_ground": (
                (0.42, 0.40, 0.35, 1),
                (0.73, 0.69, 0.60, 1),
                18.0,
                0.10,
            ),
            "leisure_ground": (
                (0.36, 0.37, 0.35, 1),
                (0.61, 0.60, 0.55, 1),
                15.0,
                0.11,
            ),
            "stone": ((0.28, 0.27, 0.24, 1), (0.62, 0.59, 0.52, 1), 9.0, 0.14),
            "trunk": ((0.028, 0.013, 0.006, 1), (0.18, 0.085, 0.025, 1), 8.0, 0.25),
        }
        for key, (dark, light, scale, strength) in profiles.items():
            mat = self.mats.get(key)
            if mat is None or not mat.use_nodes:
                continue
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            bsdf = nodes.get("Principled BSDF")
            if bsdf is None:
                continue
            noise = nodes.get("C2W Production Surface Noise") or nodes.new(
                "ShaderNodeTexNoise"
            )
            noise.name = "C2W Production Surface Noise"
            noise.noise_dimensions = "3D"
            noise.inputs["Scale"].default_value = scale
            noise.inputs["Detail"].default_value = 6.0
            ramp = nodes.get("C2W Production Color Map") or nodes.new(
                "ShaderNodeValToRGB"
            )
            ramp.name = "C2W Production Color Map"
            ramp.color_ramp.elements[0].color = dark
            ramp.color_ramp.elements[1].color = light
            bump = nodes.get("C2W Production Bump") or nodes.new("ShaderNodeBump")
            bump.name = "C2W Production Bump"
            bump.inputs["Strength"].default_value = strength
            bump.inputs["Distance"].default_value = 0.025
            for socket in (bsdf.inputs["Base Color"], bsdf.inputs["Normal"]):
                for link in list(socket.links):
                    links.remove(link)
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
            links.new(noise.outputs["Fac"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    def configure_lighting(self) -> None:
        """Bright physical daylight matching the reference production renders."""
        scene = bpy.context.scene
        scene.view_settings.look = "AgX - Medium High Contrast"
        scene.view_settings.exposure = -0.35
        world = bpy.data.worlds.get("World") or bpy.data.worlds.new("World")
        scene.world = world
        world.use_nodes = True
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        nodes.clear()
        output = nodes.new("ShaderNodeOutputWorld")
        background = nodes.new("ShaderNodeBackground")
        sky = nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(38)
        sky.sun_rotation = math.radians(218)
        sky.air_density = 1.0
        sky.dust_density = 0.35
        background.inputs["Strength"].default_value = 0.34
        links.new(sky.outputs["Color"], background.inputs["Color"])
        links.new(background.outputs["Background"], output.inputs["Surface"])
        for obj in list(bpy.data.objects):
            if obj.type == "LIGHT" and obj.name.startswith("worldbridge_"):
                bpy.data.objects.remove(obj, do_unlink=True)
        bpy.ops.object.light_add(type="SUN", location=(0, 0, 45))
        sun = bpy.context.object
        sun.name = "c2w_production_sun"
        sun.data.energy = 2.05
        sun.data.angle = math.radians(1.2)
        sun.rotation_euler = (math.radians(48), math.radians(-14), math.radians(218))
        bpy.ops.object.light_add(type="AREA", location=(-18, -24, 30))
        fill = bpy.context.object
        fill.name = "c2w_production_sky_fill"
        fill.data.energy = 420
        fill.data.shape = "DISK"
        fill.data.size = 28

    # ------------------------------------------------------------------
    # Buildings: all45_02 facade/roof/balcony system, driven by descriptors.
    # ------------------------------------------------------------------

    def _ensure_building_system(self):
        if self._building_source is not None:
            return
        source = _load_module(
            "c2w_worldbridge_all45_02",
            ROOT / "scripts" / "generate_urban_v3_all45_02.py",
        )
        source.ROOT = ROOT
        source.PREFIX = "wb_prod:"
        source.RNG = random.Random(self.world.scene_seed * 1009 + 45)
        source.G.ROOT = ROOT
        source.G.PREFIX = source.PREFIX
        source.G.RNG = source.RNG
        materials = source.make_materials()
        source.G.MATS = materials
        # Only structural masters are built.  Vegetation comes exclusively
        # from the full07 TreeFactory/LeafFactory production system below.
        assets = {
            "win_living": source.make_window_master(
                "living_floor_to_ceiling", 3.45, 2.22, materials, 3
            ),
            "win_bed": source.make_window_master(
                "bedroom_double", 1.72, 1.42, materials, 2, curtain=True
            ),
            "win_narrow": source.make_window_master(
                "narrow_vertical", 0.72, 1.82, materials, 1, awning=True
            ),
            "win_utility": source.make_window_master(
                "utility_awning", 0.92, 0.72, materials, 1, awning=True
            ),
            "sliding_door": source.make_window_master(
                "balcony_sliding_door", 2.45, 2.20, materials, 2, curtain=True
            ),
            "door_a": source.make_door_master("recessed_sidelight", materials, True),
            "door_b": source.make_door_master("side_shifted", materials, False),
            "balcony_metal": source.make_balcony_master(
                "metal_vertical", "metal", materials
            ),
            "balcony_solid": source.make_balcony_master(
                "partial_solid", "solid", materials
            ),
            "balcony_glass": source.make_balcony_master(
                "glass_metal", "glass", materials
            ),
            "hvac": source.make_hvac_master(materials),
            "ac": source.make_ac_master(materials),
            "mailbox": source.make_mailbox_master(materials),
        }
        root = source.G.make_collection("WorldBridgeProductionBuildings")
        root["c2w_source_generator"] = "generate_urban_v3_all45_02.py"
        root["c2w_scene_asset_inputs"] = 0
        self._building_source = source
        self._building_materials = materials
        self._building_assets = assets
        self._building_root = root

    @staticmethod
    def _frontage_yaw(frontage: str) -> float:
        return {
            "south": 0.0,
            "east": math.pi / 2,
            "north": math.pi,
            "west": -math.pi / 2,
        }[frontage]

    def _commercial_frontage(self, spec, origin, yaw, width, depth, collection) -> None:
        source = self._building_source
        materials = self._building_materials
        front = -depth / 2
        name = spec.id
        source.G.local_box(
            f"{name}_retail_portal",
            origin,
            yaw,
            (0, front - 0.22, 1.55),
            (width * 0.90, 0.28, 3.0),
            materials["panel_dark"],
            collection,
            bevel=0.018,
            segments=3,
        )
        bay_count = max(2, min(5, int(width // 2.2)))
        bay_width = width * 0.82 / bay_count
        for index in range(bay_count):
            lx = -width * 0.41 + bay_width * (index + 0.5)
            source.G.local_box(
                f"{name}_storefront_glass_{index}",
                origin,
                yaw,
                (lx, front - 0.40, 1.42),
                (bay_width - 0.14, 0.055, 2.45),
                materials["glass_clear"],
                collection,
                bevel=0.007,
            )
            for side in (-1, 1):
                source.G.local_box(
                    f"{name}_storefront_mullion_{index}_{side}",
                    origin,
                    yaw,
                    (lx + side * (bay_width - 0.12) / 2, front - 0.44, 1.42),
                    (0.055, 0.08, 2.58),
                    materials["metal"],
                    collection,
                    bevel=0.004,
                )
        source.G.local_box(
            f"{name}_continuous_canopy",
            origin,
            yaw,
            (0, front - 1.02, 2.86),
            (width * 0.94, 1.62, 0.20),
            materials["panel_dark"],
            collection,
            bevel=0.025,
            segments=3,
        )
        source.G.local_box(
            f"{name}_sign_band",
            origin,
            yaw,
            (0, front - 0.48, 3.34),
            (width * 0.72, 0.13, 0.58),
            materials["sign"],
            collection,
            bevel=0.035,
            segments=3,
        )
        source.add_text_label(
            f"{name}_shop_name",
            ("MARKET", "CAFE", "STUDIO")[spec.seed % 3],
            source.G.transform_point(origin, yaw, (0, front - 0.57, 3.35)),
            min(0.44, width / 24),
            materials["warm_light"],
            collection,
            rot=(math.pi / 2, 0, yaw),
        )

    def _secondary_facades(self, spec, origin, yaw, width, depth, collection) -> None:
        """Populate every visible elevation with mapped, recessed window assemblies.

        The all45 apartment generator already provides a very dense principal
        elevation.  WorldBridge can rotate a building toward any frontage, so
        the other three elevations are just as likely to face a planned road or
        camera.  These are genuine all45 window collections (glass, frames,
        mullions, sill, curtains and awning hardware), not facade decals.
        """
        source = self._building_source
        assets = self._building_assets
        materials = self._building_materials
        name = spec.id
        floor_height = 3.03
        side_rows = (-depth * 0.28, 0.0, depth * 0.28)
        for floor in range(spec.floors):
            z = floor_height * floor + 1.54
            for side_index, side in enumerate((-1, 1)):
                side_yaw = yaw + side * math.pi / 2
                x = side * (width / 2 + 0.23)
                for bay_index, local_y in enumerate(side_rows):
                    key = ("win_bed", "win_narrow", "win_utility")[
                        (floor + bay_index + side_index) % 3
                    ]
                    scale = (
                        (0.78, 0.78, 0.86) if key == "win_bed" else (0.82, 0.82, 0.88)
                    )
                    source.G.local_box(
                        f"{name}_side_reveal_{side_index}_{floor}_{bay_index}",
                        origin,
                        yaw,
                        (x - side * 0.10, local_y, z),
                        (0.16, min(2.15, depth * 0.18), 2.34),
                        materials["panel_dark"],
                        collection,
                        bevel=0.008,
                    )
                    source.G.collection_instance(
                        assets[key],
                        f"{name}_side_{key}_{side_index}_{floor}_{bay_index}",
                        source.G.transform_point(origin, yaw, (x, local_y, z)),
                        collection,
                        side_yaw,
                        scale,
                    )

            # The rear stair core has its own narrow window in all45; paired
            # bedroom/service windows complete the rest of that elevation.
            for rear_index, local_x in enumerate(
                (-width * 0.20, width * 0.12, width * 0.34)
            ):
                key = "win_bed" if (floor + rear_index) % 2 == 0 else "win_utility"
                source.G.local_box(
                    f"{name}_rear_reveal_{floor}_{rear_index}",
                    origin,
                    yaw,
                    (local_x, depth / 2 + 0.10, z),
                    (2.12, 0.16, 2.34),
                    materials["panel_dark"],
                    collection,
                    bevel=0.008,
                )
                source.G.collection_instance(
                    assets[key],
                    f"{name}_rear_{key}_{floor}_{rear_index}",
                    source.G.transform_point(
                        origin, yaw, (local_x, depth / 2 + 0.23, z)
                    ),
                    collection,
                    yaw + math.pi,
                    (0.78, 0.78, 0.86),
                )

    def build_building(self, spec) -> list[Any]:
        self._ensure_building_system()
        before = set(bpy.data.objects)
        frontage = spec.entrance.metadata.get("frontage", "south")
        yaw = self._frontage_yaw(frontage)
        if frontage in {"east", "west"}:
            width, depth = spec.bounds.depth, spec.bounds.width
        else:
            width, depth = spec.bounds.width, spec.bounds.depth
        origin = (*spec.bounds.center, 0.0)
        collection = self._building_source.add_apartment(
            spec.id,
            origin,
            yaw,
            width,
            depth,
            spec.floors,
            spec.seed % 3,
            self._building_materials,
            self._building_assets,
            self._building_root,
        )
        self._secondary_facades(spec, origin, yaw, width, depth, collection)
        if spec.use == "commercial":
            self._commercial_frontage(spec, origin, yaw, width, depth, collection)
        collection["c2w_asset_quality"] = "all45_02_production_detail"
        collection["c2w_descriptor_building_id"] = spec.id
        collection["c2w_scene_asset_inputs"] = 0
        created = _objects_created(before)
        if len(created) < 45:
            raise RuntimeError(
                f"building {spec.id} degraded: expected a production facade hierarchy, got {len(created)} objects"
            )
        self.asset_records.append(
            {
                "id": spec.id,
                "kind": "building",
                "source": "all45_02",
                "parts": len(created),
            }
        )
        return created

    # ------------------------------------------------------------------
    # Vegetation: the exact full07 same-run TreeFactory/LeafFactory method.
    # ------------------------------------------------------------------

    @staticmethod
    def _leaf_assets(tree_root) -> list[Any]:
        match = re.search(r"TreeFactory\((\d+)\)", tree_root.name)
        tree_id = match.group(1) if match else ""
        assets = [
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH" and obj.data and obj.name.startswith("LeafFactory")
        ]
        exact = [obj for obj in assets if tree_id and f"({tree_id})" in obj.name]
        broadleaf = [obj for obj in assets if "Broadleaf" in obj.name]
        return sorted(exact or broadleaf or assets, key=lambda obj: obj.name)

    def _tree_master(self, seed: int):
        if seed in self.tree_masters:
            return self.tree_masters[seed]
        # Load the terrain package before material_assignments.  Infinigen's
        # water material imports terrain.assets; entering through the material
        # registry first leaves fluid.Water temporarily undefined.
        try:
            import infinigen.terrain  # noqa: F401
            from infinigen.assets.objects.trees.generate import TreeFactory
        except Exception:
            traceback.print_exc()
            raise
        from infinigen.core.util.math import FixedSeed
        from urban_v1_full_07_trees import build_botanical_tree_master

        before = set(bpy.data.objects)
        with FixedSeed(seed):
            factory = TreeFactory(
                seed=seed, season="summer", coarse=False, fruit_chance=0.0
            )
            spawned = factory.spawn_asset(
                0,
                loc=(0, 0, 0),
                rot=(0, 0, 0),
                distance=60,
                face_size=0.08,
            )
        helpers = _objects_created(before)
        if spawned not in helpers:
            helpers.append(spawned)
        leaf_assets = self._leaf_assets(spawned)
        if not leaf_assets:
            raise RuntimeError(
                f"TreeFactory {seed} supplied no genuine LeafFactory meshes"
            )
        master = bpy.data.collections.new(
            f"wb_prod:MASTER:full07_botanical_tree:{seed}"
        )
        build_botanical_tree_master(master, seed, leaf_assets)
        helper_meshes = {
            obj.data for obj in helpers if obj and obj.type == "MESH" and obj.data
        }
        for obj in helpers:
            if obj and obj.name in bpy.data.objects:
                bpy.data.objects.remove(obj, do_unlink=True)
        for mesh in helper_meshes:
            if mesh.users == 0:
                bpy.data.meshes.remove(mesh)
        master["c2w_source_generator"] = "urban_v1_full_07_trees.py"
        master["c2w_scene_asset_inputs"] = 0
        self.tree_masters[seed] = master
        return master

    def place_tree(self, spec) -> list[Any]:
        seed = TREE_SEEDS[
            sum((i + 1) * ord(ch) for i, ch in enumerate(spec.id)) % len(TREE_SEEDS)
        ]
        master = self._tree_master(seed)
        source_height = max(
            (obj.matrix_world @ Vector(corner)).z
            for obj in master.all_objects
            if obj.type == "MESH" and obj.data
            for corner in obj.bound_box
        )
        if source_height <= 0:
            raise RuntimeError(f"tree master {seed} has invalid height")
        desired_height = max(4.8, float(spec.dimensions[2]))
        scale = desired_height / source_height
        instance = bpy.data.objects.new(f"wb_prod:{spec.id}:full07_tree", None)
        bpy.context.scene.collection.objects.link(instance)
        instance.instance_type = "COLLECTION"
        instance.instance_collection = master
        instance.location = (spec.position[0], spec.position[1], 0.0)
        instance.rotation_euler[2] = math.radians(spec.yaw_deg) + seed * 0.017
        instance.scale = (scale, scale, scale)
        instance["c2w_asset_quality"] = "full07_botanical_tree"
        instance["c2w_treefactory_seed"] = seed
        instance["c2w_real_world_height_m"] = desired_height
        instance["c2w_scene_asset_inputs"] = 0
        self.asset_records.append(
            {
                "id": spec.id,
                "kind": "tree",
                "source": "urban_v1_full_07",
                "parts": len(master.all_objects),
            }
        )
        return [instance]

    # ------------------------------------------------------------------
    # Genuine Infinigen indoor factories, normalized to descriptor bounds.
    # ------------------------------------------------------------------

    @staticmethod
    def _furniture_factory(kind: str, seed: int):
        if kind == "sofa":
            from infinigen.assets.objects.seating.sofa import SofaFactory

            return SofaFactory(seed)
        if kind == "bed":
            from infinigen.assets.objects.seating.bed import BedFactory

            return BedFactory(seed)
        if kind == "dining_table":
            from infinigen.assets.objects.tables.dining_table import TableDiningFactory

            return TableDiningFactory(seed)
        if kind == "coffee_table":
            from infinigen.assets.objects.tables.dining_table import CoffeeTableFactory

            return CoffeeTableFactory(seed)
        if kind == "chair":
            from infinigen.assets.objects.seating.chairs.chair import ChairFactory

            return ChairFactory(seed)
        if kind == "desk":
            from infinigen.assets.objects.shelves.simple_desk import SimpleDeskFactory

            return SimpleDeskFactory(seed)
        if kind == "wardrobe":
            from infinigen.assets.objects.shelves.cabinet import CabinetFactory

            return CabinetFactory(seed)
        if kind == "kitchen_counter":
            from infinigen.assets.objects.shelves.kitchen_cabinet import (
                KitchenCabinetFactory,
            )

            return KitchenCabinetFactory(seed)
        if kind == "toilet":
            from infinigen.assets.objects.bathroom.toilet import ToiletFactory

            return ToiletFactory(seed)
        if kind == "sink":
            from infinigen.assets.objects.bathroom.bathroom_sink import (
                StandingSinkFactory,
            )

            return StandingSinkFactory(seed)
        raise RuntimeError(f"no production Infinigen furniture factory for {kind!r}")

    def place_furniture(self, spec) -> list[Any]:
        seed = sum((i + 11) * ord(ch) for i, ch in enumerate(spec.id)) % 2_000_000_000
        factory = self._furniture_factory(spec.kind, seed)
        before = set(bpy.data.objects)
        root = factory.spawn_asset(
            0, loc=(0, 0, 0), rot=(0, 0, 0), distance=8, vis_distance=24
        )
        created = _objects_created(before)
        if root not in created:
            created.append(root)
        roots = [obj for obj in created if obj.parent not in created]
        container = bpy.data.objects.new(f"wb_prod:{spec.id}:infinigen_furniture", None)
        bpy.context.scene.collection.objects.link(container)
        for obj in roots:
            matrix = obj.matrix_world.copy()
            obj.parent = container
            obj.matrix_world = matrix
        minimum, maximum = _world_bounds(created)
        dimensions = maximum - minimum
        if min(dimensions) <= 1e-5:
            raise RuntimeError(
                f"furniture {spec.id} has degenerate factory bounds {tuple(dimensions)}"
            )
        center_xy = Vector(
            ((minimum.x + maximum.x) / 2, (minimum.y + maximum.y) / 2, minimum.z)
        )
        for obj in roots:
            obj.location -= center_xy
        target = Vector(spec.dimensions)
        container.scale = (
            target.x / dimensions.x,
            target.y / dimensions.y,
            target.z / dimensions.z,
        )
        container.location = (spec.position[0], spec.position[1], 0.0)
        container.rotation_euler[2] = math.radians(spec.yaw_deg)
        container["c2w_asset_quality"] = "native_infinigen_furniture_factory"
        container["c2w_factory"] = factory.__class__.__name__
        container["c2w_scene_asset_inputs"] = 0
        result = [container, *created]
        self.asset_records.append(
            {
                "id": spec.id,
                "kind": spec.kind,
                "source": f"Infinigen {factory.__class__.__name__}",
                "parts": len(result),
            }
        )
        return result

    # ------------------------------------------------------------------
    # Native urban factories plus production close-detail augmentation.
    # ------------------------------------------------------------------

    def place_pedestrian(self, spec) -> list[Any]:
        from infinigen.assets.objects.pedestrians.pedestrian import PedestrianFactory
        from infinigen.assets.utils.urban_primitives import (
            cube_obj,
            cylinder_between,
            ellipsoid_obj,
            sphere_obj,
        )

        before = set(bpy.data.objects)
        pid = sum(ord(ch) for ch in spec.id)
        shirt = "person_shirt_blue" if pid % 2 else "person_shirt_red"
        PedestrianFactory(self.mats).create(
            _request(
                spec, {"id": pid, "shirt": shirt, "facing": math.radians(spec.yaw_deg)}
            )
        )
        x, y, _ = spec.position
        # Facial planes, ears, collar, garment construction, belt and footwear
        # turn the base anatomical silhouette into a readable production extra.
        details = [
            ellipsoid_obj(
                f"wb_prod:{spec.id}:ear_l",
                (x - 0.132, y, 1.46),
                (0.025, 0.018, 0.043),
                self.mats["person_skin"],
                "pedestrian",
                segments=14,
            ),
            ellipsoid_obj(
                f"wb_prod:{spec.id}:ear_r",
                (x + 0.132, y, 1.46),
                (0.025, 0.018, 0.043),
                self.mats["person_skin"],
                "pedestrian",
                segments=14,
            ),
            ellipsoid_obj(
                f"wb_prod:{spec.id}:nose",
                (x, y - 0.116, 1.46),
                (0.025, 0.032, 0.038),
                self.mats["person_skin"],
                "pedestrian",
                segments=14,
            ),
            sphere_obj(
                f"wb_prod:{spec.id}:eye_l",
                (x - 0.047, y - 0.112, 1.495),
                0.015,
                self.mats["person_shoe"],
                "pedestrian",
            ),
            sphere_obj(
                f"wb_prod:{spec.id}:eye_r",
                (x + 0.047, y - 0.112, 1.495),
                0.015,
                self.mats["person_shoe"],
                "pedestrian",
            ),
            cube_obj(
                f"wb_prod:{spec.id}:mouth",
                (x, y - 0.126, 1.405),
                (0.055, 0.010, 0.012),
                self.mats["person_shirt_red"],
                "pedestrian",
                bevel=0.004,
            ),
            cube_obj(
                f"wb_prod:{spec.id}:collar_l",
                (x - 0.065, y - 0.115, 1.245),
                (0.10, 0.025, 0.10),
                self.mats[shirt],
                "pedestrian",
                bevel=0.012,
            ),
            cube_obj(
                f"wb_prod:{spec.id}:collar_r",
                (x + 0.065, y - 0.115, 1.245),
                (0.10, 0.025, 0.10),
                self.mats[shirt],
                "pedestrian",
                bevel=0.012,
            ),
            cube_obj(
                f"wb_prod:{spec.id}:belt",
                (x, y, 0.735),
                (0.31, 0.19, 0.045),
                self.mats["person_shoe"],
                "pedestrian",
                bevel=0.012,
            ),
            cube_obj(
                f"wb_prod:{spec.id}:shoe_sole_l",
                (x - 0.10, y - 0.05, 0.022),
                (0.14, 0.27, 0.028),
                self.mats["person_shoe"],
                "pedestrian",
                bevel=0.016,
            ),
            cube_obj(
                f"wb_prod:{spec.id}:shoe_sole_r",
                (x + 0.10, y + 0.05, 0.022),
                (0.14, 0.27, 0.028),
                self.mats["person_shoe"],
                "pedestrian",
                bevel=0.016,
            ),
        ]
        for side, sx in (("l", -0.10), ("r", 0.10)):
            for index in range(3):
                details.append(
                    cube_obj(
                        f"wb_prod:{spec.id}:shoelace_{side}_{index}",
                        (x + sx, y - 0.105 + index * 0.035, 0.073),
                        (0.085, 0.012, 0.010),
                        self.mats["license_plate"],
                        "pedestrian",
                        bevel=0.003,
                    )
                )
        for side, sx in (("l", -0.25), ("r", 0.25)):
            for finger in range(4):
                details.append(
                    cylinder_between(
                        f"wb_prod:{spec.id}:finger_{side}_{finger}",
                        (x + sx + (finger - 1.5) * 0.012, y - 0.085, 0.80),
                        (x + sx + (finger - 1.5) * 0.012, y - 0.105, 0.745),
                        0.006,
                        self.mats["person_skin"],
                        "pedestrian",
                        vertices=8,
                    )
                )
        created = _objects_created(before)
        if len(created) < 30:
            raise RuntimeError(f"pedestrian {spec.id} degraded to {len(created)} parts")
        self.asset_records.append(
            {
                "id": spec.id,
                "kind": "pedestrian",
                "source": "Infinigen PedestrianFactory + production anatomy pass",
                "parts": len(created),
            }
        )
        return created

    def record_factory_asset(
        self, spec, objects: list[Any], source: str, minimum_parts: int
    ) -> None:
        if len(objects) < minimum_parts:
            raise RuntimeError(
                f"{spec.kind} {spec.id} degraded: {len(objects)} parts from {source}, expected >= {minimum_parts}"
            )
        self.asset_records.append(
            {
                "id": spec.id,
                "kind": spec.kind,
                "source": source,
                "parts": len(objects),
            }
        )

    def audit(self) -> dict[str, Any]:
        counts: dict[str, int] = {}
        for record in self.asset_records:
            counts[record["kind"]] = counts.get(record["kind"], 0) + 1
        return {
            "passed": True,
            "scene_asset_inputs": 0,
            "toy_fallbacks": 0,
            "asset_count": len(self.asset_records),
            "asset_kinds": counts,
            "assets": self.asset_records,
            "tree_master_count": len(self.tree_masters),
            "tree_sources": [
                master.get("c2w_source_generator")
                for master in self.tree_masters.values()
            ],
            "building_source": "generate_urban_v3_all45_02.py",
        }

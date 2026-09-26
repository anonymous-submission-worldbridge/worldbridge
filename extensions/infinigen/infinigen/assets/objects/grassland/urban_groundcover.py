import math
import logging

import bpy

from infinigen.assets.objects.grassland.flowerplant import FlowerPlantFactory
from infinigen.assets.objects.grassland.grass_tuft import GrassTuftFactory
from infinigen.assets.objects.trees.generate import BushFactory
from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    curve_obj,
    cone_obj,
    cube_obj,
    ellipsoid_obj,
    mesh_obj,
    multi_curve_obj,
)
from infinigen.core.tagging import tag_object
from infinigen.core.util.math import FixedSeed

logger = logging.getLogger(__name__)


def _seed_from_id(value, salt=0):
    text = str(value)
    return (salt + sum((idx + 1) * ord(ch) for idx, ch in enumerate(text))) % 2_000_000_000


def _place_nature_asset(obj, name, location, scale, semantic, yaw=0.0):
    obj.name = name
    obj.location = location
    obj.rotation_euler[2] += yaw
    obj.scale *= scale
    tag_object(obj, semantic)
    return obj


def _enforce_nature_face_budget(obj, max_faces, label):
    if max_faces is None:
        return
    max_faces = int(max_faces)
    roots = obj if isinstance(obj, (list, tuple, set)) else [obj]
    meshes = []
    seen = set()

    def collect(current):
        if current in seen:
            return
        seen.add(current)
        if current.type == "MESH" and current.data is not None:
            meshes.append(current)
        for child in current.children:
            collect(child)

    for root in roots:
        collect(root)
    total_faces = sum(len(mesh.data.polygons) for mesh in meshes)
    if total_faces <= max_faces:
        return

    ratio = max(0.001, min(1.0, max_faces / max(total_faces, 1)))
    logger.info(
        "Decimating %s hierarchy from %d to about %d faces for urban preview budget",
        label,
        total_faces,
        max_faces,
    )
    for mesh in meshes:
        if len(mesh.data.polygons) < 128:
            continue
        try:
            modifier = mesh.modifiers.new("UrbanNatureFaceBudget", "DECIMATE")
            modifier.ratio = ratio
            bpy.ops.object.select_all(action="DESELECT")
            mesh.select_set(True)
            bpy.context.view_layer.objects.active = mesh
            bpy.ops.object.modifier_apply(modifier=modifier.name)
        except Exception as exc:
            logger.warning("Could not apply urban nature face budget to %s: %s", mesh.name, exc)


def _is_descendant(obj, root):
    current = obj.parent
    while current is not None:
        if current == root:
            return True
        current = current.parent
    return False


def _parent_loose_spawned_objects(root, spawned_objects):
    for obj in spawned_objects:
        if obj == root or _is_descendant(obj, root):
            continue
        matrix_world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = matrix_world


class UrbanGroundcoverFactory:
    def __init__(self, mats):
        self.mats = mats

    def _leaf_cluster(self, name, center, count, radius, height, mat_a, mat_b, semantic):
        x, y, z = center
        vertices = []
        faces = []
        veins = []
        seed = sum(ord(c) for c in name)
        for i in range(count):
            a = (i * 2.399 + seed * 0.01) % math.tau
            r = radius * (0.25 + 0.75 * (((i * 41 + seed) % 100) / 100.0))
            cx = x + math.cos(a) * r
            cy = y + math.sin(a) * r * 0.82
            cz = z + height * (((i * 29 + seed) % 100) / 100.0)
            length = 0.18 + 0.18 * (((i * 17 + seed) % 100) / 100.0)
            width = 0.055 + 0.07 * (((i * 23 + seed) % 100) / 100.0)
            yaw = a + 0.35 * math.sin(i)
            pitch = -0.12 + 0.45 * (((i * 13 + seed) % 100) / 100.0)
            forward = (math.cos(yaw) * math.cos(pitch), math.sin(yaw) * math.cos(pitch), math.sin(pitch))
            side = (-math.sin(yaw), math.cos(yaw), 0.07 * math.sin(i * 0.7))
            idx = len(vertices)
            local = [
                (-0.45, 0.00, 0.00),
                (-0.16, -0.45, 0.03),
                (0.25, -0.32, -0.02),
                (0.52, 0.00, 0.02),
                (0.25, 0.32, -0.02),
                (-0.16, 0.45, 0.03),
                (0.02, 0.00, 0.07),
            ]
            world = []
            for lx, ly, lz in local:
                world.append(
                    (
                        cx + forward[0] * lx * length + side[0] * ly * width,
                        cy + forward[1] * lx * length + side[1] * ly * width,
                        cz + forward[2] * lx * length + side[2] * ly * width + lz * 0.08,
                    )
                )
            vertices.extend(world)
            faces.extend(
                [
                    (idx, idx + 1, idx + 6),
                    (idx + 1, idx + 2, idx + 6),
                    (idx + 2, idx + 3, idx + 6),
                    (idx + 3, idx + 4, idx + 6),
                    (idx + 4, idx + 5, idx + 6),
                    (idx + 5, idx, idx + 6),
                ]
            )
            if i % 3 == 0:
                veins.append([world[0], world[6], world[3]])
        mat = mat_a if seed % 2 else mat_b
        objs = [mesh_obj(name, vertices, faces, mat, semantic, smooth=True)]
        if veins:
            objs.append(multi_curve_obj(f"{name}:veins", veins, 0.002, mat_b, semantic, resolution=1))
        return objs

    def create_shrub(self, request: UrbanAssetRequest):
        sid = request.params.get("id", "0")
        x, y, _ = request.location
        if request.params.get("use_nature_factory", True):
            seed = _seed_from_id(sid, salt=911)
            try:
                old_n_leaf, old_n_twig = BushFactory.n_leaf, BushFactory.n_twig
                BushFactory.n_leaf = int(request.params.get("n_leaf", 2))
                BushFactory.n_twig = int(request.params.get("n_twig", 2))
                try:
                    with FixedSeed(seed):
                        bush = BushFactory(seed, coarse=False).spawn_asset(
                            int(seed % 100000),
                            loc=(x, y, 0.0),
                            rot=(0.0, 0.0, request.yaw),
                            distance=20,
                            vis_distance=20,
                        )
                finally:
                    BushFactory.n_leaf, BushFactory.n_twig = old_n_leaf, old_n_twig
                _enforce_nature_face_budget(
                    bush,
                    request.params.get("max_faces", 20000),
                    f"urban shrub {sid}",
                )
                _place_nature_asset(
                    bush,
                    f"urban:nature_bush:{sid}",
                    (x, y, 0.0),
                    request.params.get("scale", 0.62),
                    "shrub",
                    yaw=0.0,
                )
                return [bush], {
                    "id": f"shrub_{sid}",
                    "type": "nature-bush",
                    "center": [x, y, 0],
                    "source_factory": "infinigen.assets.objects.trees.generate.BushFactory",
                }
            except Exception as exc:
                logger.warning("Nature BushFactory failed for urban shrub %s; using fallback mesh shrub: %s", sid, exc)

        objs = []
        twig_paths = []
        for i in range(18):
            a = i * math.tau / 18
            stem_top = (x + math.cos(a) * 0.46, y + math.sin(a) * 0.35, 0.28 + 0.36 * ((i * 19) % 100) / 100.0)
            twig_paths.append([(x, y, 0.18), stem_top])
            if i % 5 == 0:
                objs.append(
                    ellipsoid_obj(
                        f"urban:shrub:flower:{sid}:{i}",
                        (stem_top[0], stem_top[1], stem_top[2] + 0.05),
                        (0.055, 0.055, 0.035),
                        self.mats.get("flower_yellow", self.mats["lamp"]),
                        "flower",
                        segments=10,
                        ring_count=6,
                    )
                )
        objs.append(multi_curve_obj(f"urban:shrub:twigs:{sid}", twig_paths, 0.012, self.mats["trunk"], "shrub", resolution=1))
        objs.extend(
            self._leaf_cluster(
                f"urban:shrub:leaf_cards:{sid}",
                (x, y, 0.23),
                95,
                0.52,
                0.52,
                self.mats["shrub"],
                self.mats["leaf_dark"],
                "shrub-leaf",
            )
        )
        return objs, {"id": f"shrub_{sid}", "type": "shrub", "center": [x, y, 0]}

    def create_grass_tuft(self, request: UrbanAssetRequest):
        gid = request.params.get("id", "0")
        x, y, _ = request.location
        if request.params.get("use_nature_factory", True):
            seed = _seed_from_id(gid, salt=313)
            try:
                factory = GrassTuftFactory(seed)
                with FixedSeed(seed):
                    grass = factory.create_asset()
                factory.finalize_assets([grass])
                _place_nature_asset(
                    grass,
                    f"urban:nature_grass_tuft:{gid}",
                    (x, y, 0.03),
                    request.params.get("scale", 2.35),
                    "grass",
                    yaw=request.yaw,
                )
                return [grass], {
                    "id": f"grass_tuft_{gid}",
                    "type": "nature-grass-tuft",
                    "center": [x, y, 0],
                    "source_factory": "infinigen.assets.objects.grassland.grass_tuft.GrassTuftFactory",
                }
            except Exception as exc:
                logger.warning("Nature GrassTuftFactory failed for urban grass %s; using fallback mesh grass: %s", gid, exc)

        objs = []
        seed = sum(ord(c) for c in str(gid))
        vertices = []
        faces = []
        for i in range(34):
            angle = (i * 2.399 + seed * 0.017) % 6.28318
            radius = 0.04 + 0.12 * ((i * 37 + seed) % 100) / 100.0
            bx = x + radius * math.cos(angle)
            by = y + radius * math.sin(angle)
            height = 0.22 + 0.22 * ((i * 23 + seed) % 100) / 100.0
            lean = 0.11 + 0.08 * ((i * 17 + seed) % 100) / 100.0
            tip = (bx + lean * math.cos(angle), by + lean * math.sin(angle), height)
            mid = ((bx + tip[0]) * 0.5, (by + tip[1]) * 0.5, height * 0.55)
            width_base = 0.028
            width_mid = 0.018
            side = (-math.sin(angle), math.cos(angle), 0)
            base = (bx, by, 0.03)
            idx = len(vertices)
            vertices.extend(
                [
                    (base[0] + side[0] * width_base, base[1] + side[1] * width_base, base[2]),
                    (base[0] - side[0] * width_base, base[1] - side[1] * width_base, base[2]),
                    (mid[0] + side[0] * width_mid, mid[1] + side[1] * width_mid, mid[2]),
                    (mid[0] - side[0] * width_mid, mid[1] - side[1] * width_mid, mid[2]),
                    tip,
                ]
            )
            faces.extend([(idx, idx + 1, idx + 3, idx + 2), (idx + 2, idx + 3, idx + 4)])
        objs.append(mesh_obj(f"urban:grass_blades:{gid}", vertices, faces, self.mats["grass_tuft"], "grass", smooth=False))
        seed_paths = []
        seed_tips = []
        for i in range(4):
            a = i * math.tau / 4 + seed * 0.01
            stem_base = (x + math.cos(a) * 0.07, y + math.sin(a) * 0.07, 0.04)
            stem_tip = (x + math.cos(a) * 0.18, y + math.sin(a) * 0.18, 0.36 + 0.03 * i)
            seed_paths.append([stem_base, stem_tip])
            seed_tips.append(stem_tip)
        objs.append(multi_curve_obj(f"urban:grass_seed_stems:{gid}", seed_paths, 0.006, self.mats["grass_tuft"], "grass", resolution=1))
        for i, stem_tip in enumerate(seed_tips):
            objs.append(cone_obj(f"urban:grass_seed_head:{gid}:{i}", stem_tip, 0.032, 0.008, 0.12, self.mats["leaf_dark"], "grass", vertices=7))
        if int(gid) % 3 == 0:
            objs.append(cube_obj(f"urban:grass_litter_leaf:{gid}", (x + 0.12, y - 0.05, 0.025), (0.24, 0.045, 0.015), self.mats.get("leaf_litter", self.mats["trunk"]), "leaf-litter", bevel=0.012))
        return objs, {"id": f"grass_tuft_{gid}", "type": "grass", "center": [x, y, 0]}

    def create_flowerplant(self, request: UrbanAssetRequest):
        fid = request.params.get("id", "0")
        x, y, _ = request.location
        seed = _seed_from_id(fid, salt=719)
        try:
            factory = FlowerPlantFactory(seed, coarse=False)
            with FixedSeed(seed):
                flowerplant = factory.create_asset()
            _enforce_nature_face_budget(
                flowerplant,
                request.params.get("max_faces", 8000),
                f"urban flowerplant {fid}",
            )
            _place_nature_asset(
                flowerplant,
                f"urban:nature_flowerplant:{fid}",
                (x, y, 0.05),
                request.params.get("scale", 0.95),
                "flowerplant",
                yaw=request.yaw,
            )
            return [flowerplant], {
                "id": f"flowerplant_{fid}",
                "type": "nature-flowerplant",
                "center": [x, y, 0],
                "source_factory": "infinigen.assets.objects.grassland.flowerplant.FlowerPlantFactory",
            }
        except Exception as exc:
            logger.warning("Nature FlowerPlantFactory failed for urban flowerplant %s; using fallback shrub flowers: %s", fid, exc)
            objs = []
            for i in range(5):
                angle = i * math.tau / 5
                objs.append(
                    ellipsoid_obj(
                        f"urban:fallback_flowerplant:flower:{fid}:{i}",
                        (x + math.cos(angle) * 0.18, y + math.sin(angle) * 0.18, 0.32),
                        (0.055, 0.055, 0.035),
                        self.mats.get("flower_yellow", self.mats["lamp"]),
                        "flowerplant",
                        segments=10,
                        ring_count=6,
                    )
                )
            objs.extend(self._leaf_cluster(f"urban:fallback_flowerplant:leaf_cards:{fid}", (x, y, 0.08), 34, 0.25, 0.30, self.mats["shrub"], self.mats["leaf_dark"], "flowerplant"))
            return objs, {"id": f"flowerplant_{fid}", "type": "fallback-flowerplant", "center": [x, y, 0]}

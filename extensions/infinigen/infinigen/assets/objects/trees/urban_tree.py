import math
import logging
import random

import bpy

from infinigen.assets.objects.trees.generate import TreeFactory
from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    cube_obj,
    cylinder_between,
    cylinder_obj,
    mesh_obj,
    multi_curve_obj,
)
from infinigen.core.tagging import tag_object
from infinigen.core.util import blender as butil
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


def _leaf_mesh(name, leaf_specs, leaf_mat, vein_mat, semantic):
    verts = []
    faces = []
    vein_paths = []
    for spec in leaf_specs:
        cx, cy, cz = spec["center"]
        length = spec["length"]
        width = spec["width"]
        yaw = spec["yaw"]
        pitch = spec["pitch"]
        roll = spec["roll"]
        curve = spec["curve"]
        c_yaw = math.cos(yaw)
        s_yaw = math.sin(yaw)
        forward = (c_yaw * math.cos(pitch), s_yaw * math.cos(pitch), math.sin(pitch))
        side = (-s_yaw * math.cos(roll), c_yaw * math.cos(roll), math.sin(roll) * 0.18)
        up = (
            side[1] * forward[2] - side[2] * forward[1],
            side[2] * forward[0] - side[0] * forward[2],
            side[0] * forward[1] - side[1] * forward[0],
        )

        local = [
            (-0.48, 0.00, 0.00),
            (-0.22, -0.50, 0.05),
            (0.18, -0.42, -0.02),
            (0.50, -0.12, 0.03),
            (0.55, 0.00, 0.00),
            (0.50, 0.12, -0.03),
            (0.18, 0.42, 0.02),
            (-0.22, 0.50, -0.05),
            (0.02, 0.00, 0.08),
        ]
        idx = len(verts)
        world = []
        for lx, ly, lz in local:
            bend = curve * (1.0 - abs(lx)) * 0.08
            px = cx + forward[0] * lx * length + side[0] * ly * width + up[0] * (lz + bend)
            py = cy + forward[1] * lx * length + side[1] * ly * width + up[1] * (lz + bend)
            pz = cz + forward[2] * lx * length + side[2] * ly * width + up[2] * (lz + bend)
            world.append((px, py, pz))
        verts.extend(world)
        faces.extend(
            [
                (idx, idx + 1, idx + 8),
                (idx + 1, idx + 2, idx + 8),
                (idx + 2, idx + 3, idx + 8),
                (idx + 3, idx + 4, idx + 8),
                (idx + 4, idx + 5, idx + 8),
                (idx + 5, idx + 6, idx + 8),
                (idx + 6, idx + 7, idx + 8),
                (idx + 7, idx, idx + 8),
            ]
        )
        vein_paths.append([world[0], world[8], world[4]])
        if spec.get("side_veins", True):
            vein_paths.extend(
                [
                    [world[8], world[2]],
                    [world[8], world[6]],
                    [world[8], world[3]],
                    [world[8], world[5]],
                ]
            )
    objs = []
    if verts:
        objs.append(mesh_obj(name, verts, faces, leaf_mat, semantic, smooth=True))
    if vein_paths:
        objs.append(multi_curve_obj(f"{name}:veins", vein_paths, 0.0025, vein_mat, semantic, resolution=1))
    return objs


class UrbanTreeFactory:
    def __init__(self, mats):
        self.mats = mats
        self._nature_prototypes = {}

    def _set_hidden_recursive(self, obj, hidden):
        obj.hide_viewport = hidden
        obj.hide_render = hidden
        for child in obj.children:
            self._set_hidden_recursive(child, hidden)

    def _clone_recursive(self, obj, name):
        clone = butil.deep_clone_obj(obj, keep_modifiers=True, keep_materials=True)
        clone.name = name
        clone.hide_viewport = False
        clone.hide_render = False
        for child in obj.children:
            child_clone = self._clone_recursive(child, f"{name}:{child.name}")
            child_clone.parent = clone
            child_clone.location = child.location.copy()
            child_clone.rotation_euler = child.rotation_euler.copy()
            child_clone.scale = child.scale.copy()
        return clone

    def _nature_tree_prototype(self, variant, seed, request):
        if variant not in self._nature_prototypes:
            old_n_leaf, old_n_twig = TreeFactory.n_leaf, TreeFactory.n_twig
            TreeFactory.n_leaf = int(request.params.get("n_leaf", 4))
            TreeFactory.n_twig = int(request.params.get("n_twig", 1))
            try:
                with FixedSeed(seed):
                    prototype = TreeFactory(
                        seed,
                        season=request.params.get("season", "summer"),
                        fruit_chance=request.params.get("fruit_chance", 0.0),
                        coarse=False,
                    ).spawn_asset(
                        int(seed % 100000),
                        loc=(-900.0 - variant * 12.0, -900.0, 0.0),
                        rot=(0.0, 0.0, 0.0),
                        distance=request.params.get("distance", 35),
                        vis_distance=request.params.get("vis_distance", 35),
                    )
            finally:
                TreeFactory.n_leaf, TreeFactory.n_twig = old_n_leaf, old_n_twig
            self._enforce_tree_face_budget(
                prototype,
                request.params.get("max_faces", 55000),
            )
            prototype.name = f"urban:nature_tree_prototype:{variant}"
            self._set_hidden_recursive(prototype, True)
            self._nature_prototypes[variant] = prototype
        return self._nature_prototypes[variant]

    def _is_descendant(self, obj, root):
        current = obj.parent
        while current is not None:
            if current == root:
                return True
            current = current.parent
        return False

    def _parent_loose_spawned_objects(self, root, spawned_objects):
        for obj in spawned_objects:
            if obj == root or self._is_descendant(obj, root):
                continue
            matrix_world = obj.matrix_world.copy()
            obj.parent = root
            obj.matrix_world = matrix_world

    def _enforce_tree_face_budget(self, roots, max_faces):
        if max_faces is None:
            return
        max_faces = int(max_faces)
        if not isinstance(roots, (list, tuple, set)):
            roots = [roots]
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
            "Decimating %d-object tree hierarchy from %d to about %d faces for urban preview budget",
            len(seen),
            total_faces,
            max_faces,
        )
        for mesh in meshes:
            face_count = len(mesh.data.polygons)
            if face_count < 128:
                continue
            try:
                modifier = mesh.modifiers.new("UrbanTreeFaceBudget", "DECIMATE")
                modifier.ratio = ratio
                bpy.ops.object.select_all(action="DESELECT")
                mesh.select_set(True)
                bpy.context.view_layer.objects.active = mesh
                bpy.ops.object.modifier_apply(modifier=modifier.name)
            except Exception as exc:
                logger.warning("Could not apply urban tree face budget to %s: %s", mesh.name, exc)

    def cleanup_prototypes(self):
        for prototype in list(self._nature_prototypes.values()):
            self._remove_recursive(prototype)
        self._nature_prototypes.clear()

    def _remove_recursive(self, obj):
        for child in list(obj.children):
            self._remove_recursive(child)
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    def create_tree(self, request: UrbanAssetRequest):
        tid = request.params.get("id", "0")
        x, y, _ = request.location
        if request.params.get("use_nature_factory", True):
            seed = _seed_from_id(tid, salt=1201)
            try:
                variant = int(request.params.get("variant", seed % 3))
                prototype_seed = _seed_from_id(variant, salt=8421)
                prototype = self._nature_tree_prototype(variant, prototype_seed, request)
                tree = self._clone_recursive(prototype, f"urban:nature_tree:{tid}")
                _place_nature_asset(
                    tree,
                    f"urban:nature_tree:{tid}",
                    (x, y, 0.0),
                    request.params.get("scale", 0.48 + 0.04 * (seed % 5)),
                    "tree",
                    yaw=request.yaw + (seed % 31) * 0.07,
                )
                objs = [tree]
                for i in range(4):
                    a = i * math.tau / 4 + math.pi / 4
                    objs.append(
                        cube_obj(
                            f"urban:nature_tree:tree_pit_stone:{tid}:{i}",
                            (x + math.cos(a) * 0.48, y + math.sin(a) * 0.48, 0.055),
                            (0.48, 0.10, 0.11) if abs(math.cos(a)) > abs(math.sin(a)) else (0.10, 0.48, 0.11),
                            self.mats["curb"],
                            "tree-pit",
                            bevel=0.025,
                        )
                    )
                return objs, {
                    "id": f"tree_{tid}",
                    "type": "nature-tree",
                    "center": [x, y, 0],
                    "source_factory": "infinigen.assets.objects.trees.generate.TreeFactory",
                }
            except Exception as exc:
                logger.warning("Nature TreeFactory failed for urban tree %s; using fallback leaf mesh tree: %s", tid, exc)

        rng = random.Random(str(tid))
        height = rng.uniform(3.4, 4.4)
        lean_x = rng.uniform(-0.18, 0.18)
        lean_y = rng.uniform(-0.18, 0.18)
        trunk_top = (x + lean_x, y + lean_y, height * 0.62)
        objs = [
            cylinder_obj(f"urban:tree:root_flare:{tid}", (x, y, 0.16), 0.34, 0.30, self.mats["trunk"], "tree", vertices=28),
            cylinder_between(f"urban:tree:trunk:{tid}", (x, y, 0.18), trunk_top, 0.17, self.mats["trunk"], "tree", vertices=24),
        ]
        root_paths = []
        for i in range(6):
            a = i * math.tau / 6 + rng.uniform(-0.15, 0.15)
            root_end = (x + math.cos(a) * rng.uniform(0.38, 0.62), y + math.sin(a) * rng.uniform(0.38, 0.62), 0.05)
            root_mid = ((x + root_end[0]) * 0.5, (y + root_end[1]) * 0.5, 0.10)
            root_paths.append([(x, y, 0.13), root_mid, root_end])
        objs.append(multi_curve_obj(f"urban:tree:surface_roots:{tid}", root_paths, 0.032, self.mats["trunk"], "tree", resolution=2))
        for i, z in enumerate([0.45, 0.92, 1.38]):
            objs.append(
                cylinder_obj(
                    f"urban:tree:bark_band:{tid}:{i}",
                    (x + lean_x * z / max(height, 1), y + lean_y * z / max(height, 1), z),
                    0.17 - i * 0.018,
                    0.026,
                    self.mats.get("bark_dark", self.mats["trunk"]),
                    "tree",
                    vertices=24,
                )
            )

        branch_ends = []
        twig_paths = []
        branch_paths = []
        for i in range(11):
            angle = i * math.tau / 11 + rng.uniform(-0.22, 0.22)
            length = rng.uniform(0.85, 1.65)
            z = rng.uniform(height * 0.48, height * 0.77)
            start = (
                x + lean_x * rng.uniform(0.45, 0.95),
                y + lean_y * rng.uniform(0.45, 0.95),
                z,
            )
            end = (
                start[0] + math.cos(angle) * length,
                start[1] + math.sin(angle) * length,
                z + rng.uniform(0.20, 0.58),
            )
            branch_ends.append(end)
            branch_paths.append([start, end])
            objs.append(
                cylinder_between(
                    f"urban:tree:branch:{tid}:{i}",
                    start,
                    end,
                    rng.uniform(0.045, 0.075),
                    self.mats["trunk"],
                    "tree",
                    vertices=14,
                )
            )
            for j in range(4):
                twig_angle = angle + rng.uniform(-0.7, 0.7)
                twig_start = (
                    start[0] * 0.35 + end[0] * 0.65,
                    start[1] * 0.35 + end[1] * 0.65,
                    start[2] * 0.35 + end[2] * 0.65,
                )
                twig_end = (
                    twig_start[0] + math.cos(twig_angle) * rng.uniform(0.32, 0.52),
                    twig_start[1] + math.sin(twig_angle) * rng.uniform(0.32, 0.52),
                    twig_start[2] + rng.uniform(0.08, 0.26),
                )
                twig_paths.append([twig_start, twig_end])
        objs.append(multi_curve_obj(f"urban:tree:twigs:{tid}", twig_paths, 0.018, self.mats["trunk"], "tree", resolution=1))

        crown_centers = [(x + lean_x, y + lean_y, height * 0.86), *branch_ends]
        sun_leaves = []
        shade_leaves = []
        for i in range(190):
            center = rng.choice(crown_centers)
            a = rng.uniform(0, math.tau)
            r = rng.uniform(0.08, 0.72)
            loc = (
                center[0] + math.cos(a) * r + rng.uniform(-0.10, 0.10),
                center[1] + math.sin(a) * r + rng.uniform(-0.10, 0.10),
                center[2] + rng.uniform(-0.42, 0.38),
            )
            leaf_spec = {
                "center": loc,
                "length": rng.uniform(0.22, 0.42),
                "width": rng.uniform(0.08, 0.16),
                "yaw": a + rng.uniform(-0.7, 0.7),
                "pitch": rng.uniform(-0.42, 0.35),
                "roll": rng.uniform(-0.65, 0.65),
                "curve": rng.uniform(-1.0, 1.0),
                "side_veins": i % 4 == 0,
            }
            if loc[2] > height * 0.78 and rng.random() < 0.65:
                sun_leaves.append(leaf_spec)
            else:
                shade_leaves.append(leaf_spec)
        objs.extend(_leaf_mesh(f"urban:tree:leaf_cards_sun:{tid}", sun_leaves, self.mats["leaf"], self.mats["leaf_dark"], "tree-leaf"))
        objs.extend(_leaf_mesh(f"urban:tree:leaf_cards_shade:{tid}", shade_leaves, self.mats["leaf_dark"], self.mats["leaf"], "tree-leaf"))

        loose_leaf_specs = []
        for i in range(18):
            a = rng.uniform(0, math.tau)
            loose_leaf_specs.append(
                {
                    "center": (x + math.cos(a) * rng.uniform(0.35, 0.75), y + math.sin(a) * rng.uniform(0.35, 0.75), 0.035),
                    "length": rng.uniform(0.16, 0.26),
                    "width": rng.uniform(0.05, 0.09),
                    "yaw": a + rng.uniform(-0.5, 0.5),
                    "pitch": rng.uniform(-0.03, 0.03),
                    "roll": rng.uniform(-0.2, 0.2),
                    "curve": rng.uniform(-0.4, 0.4),
                    "side_veins": False,
                }
            )
        objs.extend(_leaf_mesh(f"urban:tree:fallen_leaves:{tid}", loose_leaf_specs, self.mats.get("leaf_litter", self.mats["leaf_dark"]), self.mats["leaf_dark"], "leaf-litter"))
        for i in range(4):
            a = i * math.tau / 4 + math.pi / 4
            objs.append(
                cube_obj(
                    f"urban:tree:tree_pit_stone:{tid}:{i}",
                    (x + math.cos(a) * 0.48, y + math.sin(a) * 0.48, 0.055),
                    (0.48, 0.10, 0.11) if abs(math.cos(a)) > abs(math.sin(a)) else (0.10, 0.48, 0.11),
                    self.mats["curb"],
                    "tree-pit",
                    bevel=0.025,
                )
            )
        return objs, {"id": f"tree_{tid}", "type": "tree", "center": [x, y, 0]}

"""Reuse authored WorldBridge details and real Infinigen furniture geometry."""
from __future__ import annotations
import hashlib
import json
import math
import sys
from pathlib import Path
import bpy
from mathutils import Matrix, Vector

from .plan import ROOT, OUT
from .geometry import Batch, collection

sys.path.insert(0, str(ROOT / "scripts"))


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(4 * 1024 * 1024), b""):
            digest.update(b)
    return digest.hexdigest()


def simple_material(name, color, rough=0.6, metal=0, alpha=1):
    m = bpy.data.materials.new("astra:" + name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, alpha)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    p.inputs["Alpha"].default_value = alpha
    if alpha < 1:
        m.surface_render_method = "DITHERED"
    m.diffuse_color = (*color, alpha)
    return m


class AssetLibrary:
    def __init__(self):
        self.records = []
        self.meshes = {}
        self.native_bounds = {}
        import generate_urban_v3_all45_02 as source

        source.ROOT = ROOT
        source.G.ROOT = ROOT
        source.PREFIX = "astra_source:"
        source.G.PREFIX = source.PREFIX
        self.source = source
        self.materials = source.make_materials()
        m = self.materials
        for key, color in [
            ("brick_red", (0.32, 0.115, 0.065)),
            ("brick_ochre", (0.46, 0.28, 0.12)),
            ("plaster_sage", (0.31, 0.41, 0.34)),
            ("plaster_cream", (0.68, 0.62, 0.49)),
            ("plaster_blue", (0.24, 0.34, 0.38)),
            ("brick_dark", (0.14, 0.16, 0.17)),
        ]:
            if key.startswith("brick"):
                m[key] = source.G.brick_material(
                    key,
                    color,
                    tuple(c * 0.74 for c in color),
                    (0.23, 0.22, 0.20),
                    scale=1.9,
                )
            else:
                m[key] = source.remap_material(
                    key, tuple(c * 0.83 for c in color), color, bump=0.10, scale=22
                )
        m["white"] = simple_material("street_paint", (0.85, 0.83, 0.74), 0.8)
        m["yellow"] = simple_material("yellow_paint", (0.95, 0.60, 0.06), 0.7)
        m["tile"] = simple_material("bathroom_porcelain", (0.72, 0.75, 0.70), 0.28)
        m["water"] = simple_material("water", (0.035, 0.18, 0.21), 0.12, 0.25)
        m["glazing"] = simple_material(
            "architectural_glazing", (0.54, 0.68, 0.72), 0.12, 0.12, 0.16
        )
        m["bronze"] = simple_material("bronze", (0.29, 0.17, 0.075), 0.28, 0.72)
        self.records.append(
            {
                "kind": "facade_roof_materials",
                "source": str(Path(source.__file__).resolve()),
                "sha256": file_hash(Path(source.__file__)),
                "method": "existing production factory functions",
            }
        )
        for name, coll in [
            ("hvac", source.make_hvac_master(m)),
            ("ac", source.make_ac_master(m)),
            ("mailbox", source.make_mailbox_master(m)),
        ]:
            self.meshes[name] = self.collapse_collection(coll, name)

    def collapse_collection(self, coll, name):
        # Temporarily link masters so Blender evaluates their authored bevels.
        if coll.name not in bpy.context.scene.collection.children:
            bpy.context.scene.collection.children.link(coll)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        batch = Batch("astra_master_" + name)
        for obj in coll.all_objects:
            if obj.type != "MESH":
                continue
            ev = obj.evaluated_get(deps)
            mesh = ev.to_mesh()
            batch.mesh(
                mesh, obj.matrix_world, [slot.material for slot in obj.material_slots]
            )
            ev.to_mesh_clear()
        staging = collection("astra_temporary_" + name)
        combined = batch.finish(staging)
        mesh = combined.data
        mesh.use_fake_user = True
        # Keep dependency-graph source IDs alive for the lifetime of this extraction
        # process. The saved library includes only explicitly selected meshes.
        self.records.append(
            {
                "kind": name,
                "source_collection": coll.name,
                "vertices": len(mesh.vertices),
                "faces": len(mesh.polygons),
                "method": "evaluated original master, merged without decimation",
            }
        )
        return mesh

    def native_furniture(self):
        inventory = json.loads((OUT / "source_inventory.json").read_text())
        info = inventory["native_indoor"]
        path = Path(info["path"])
        families = {
            "sofa": "SofaFactory",
            "bed": "BedFactory",
            "chair": "ChairFactory",
            "cabinet": "SingleCabinetFactory",
            "kitchen": "KitchenCabinetFactory",
            "toilet": "ToiletFactory",
            "sink": "StandingSinkFactory",
            "side_table": "SideTableFactory",
        }
        candidates = {
            key: [
                n
                for n in info["objects"]
                if n.startswith(prefix) and ".spawn_asset(" in n
            ]
            for key, prefix in families.items()
        }
        # Children include mattresses, pillows and fitted upholstery. Preserve complete hierarchies.
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            dst.objects = list(src.objects)
        staging = collection("astra_native_import")
        loaded = {obj.name: obj for obj in dst.objects if obj is not None}
        for obj in loaded.values():
            staging.objects.link(obj)
        bpy.context.view_layer.update()
        deps = bpy.context.evaluated_depsgraph_get()
        selected = {}
        for key, names in candidates.items():
            for name in names:
                candidate = loaded[name]
                dims = candidate.dimensions
                if key == "bed" and max(dims) > 3.2:
                    continue
                if key == "chair" and max(dims) > 1.4:
                    continue
                selected[key] = name
                break
        for key, name in selected.items():
            obj = loaded[name]
            hierarchy = [obj, *obj.children_recursive]
            batch = Batch("astra_native_" + key)
            yaw = obj.matrix_world.to_euler().z
            for part in hierarchy:
                if part.type != "MESH" or part.hide_render:
                    continue
                ev = part.evaluated_get(deps)
                evaluated = ev.to_mesh()
                batch.mesh(
                    evaluated,
                    Matrix.Rotation(-yaw, 4, "Z") @ part.matrix_world,
                    [slot.material for slot in part.material_slots],
                )
                ev.to_mesh_clear()
            combined = batch.finish(staging)
            if combined is None:
                raise RuntimeError("Empty hierarchy: " + name)
            mesh = combined.data
            if not mesh.vertices:
                raise RuntimeError("Empty native furniture: " + name)
            low = Vector([min(v.co[i] for v in mesh.vertices) for i in range(3)])
            high = Vector([max(v.co[i] for v in mesh.vertices) for i in range(3)])
            mesh.transform(
                Matrix.Translation(
                    Vector((-(low.x + high.x) / 2, -(low.y + high.y) / 2, -low.z))
                )
            )
            mesh.name = "astra_native_" + key
            mesh.use_fake_user = True
            self.meshes[key] = mesh
            self.native_bounds[key] = list(high - low)
            self.records.append(
                {
                    "kind": key,
                    "source": str(path),
                    "source_object": name,
                    "source_bytes": path.stat().st_size,
                    "vertices": len(mesh.vertices),
                    "faces": len(mesh.polygons),
                    "dimensions_m": list(high - low),
                    "method": "original evaluated Infinigen mesh, normalized pivot, no decimation",
                }
            )
            self.records[-1]["source_hierarchy"] = [p.name for p in hierarchy]
        bpy.context.view_layer.objects.active = None
        # Keep the evaluated source hierarchy alive until process exit. Some legacy
        # geometry-node dependencies crash Blender 4.5 when invalidated after extraction.
        # Only the explicit mesh/material set is written into the reusable library.
        self.native_hash_source = path
        print("NATIVE_FURNITURE", self.native_bounds, flush=True)

    def commercial(self):
        import commercial_complete_interior_generator_11_object2 as source

        print("COMMERCIAL_PRIMITIVES", flush=True)
        # Existing production source expects shared primitives with these datablock names.
        if not bpy.data.meshes.get("all43_10:shared_cube"):
            batch = Batch("commercial_cube")
            batch.box("cube", (0, 0, 0), (2, 2, 2), self.materials["white"])
            obj = batch.finish(collection("commercial_primitives"))
            obj.data.name = "all43_10:shared_cube"
            obj.data.use_fake_user = True
        if not bpy.data.meshes.get("all43_10:shared_cylinder_12"):
            batch = Batch("commercial_cylinder")
            batch.cylinder((0, 0, 0), 1, 2, self.materials["white"], 16)
            obj = batch.finish(collection("commercial_primitives"))
            obj.data.name = "all43_10:shared_cylinder_12"
            obj.data.use_fake_user = True
        # Products use an authored pouch primitive; copy the complete shared cube as a folded box package.
        # Do not call the pouch generator, whose source mesh is not in this library.
        mats = source.materials()
        print("COMMERCIAL_FACTORIES", flush=True)
        for key, coll in [
            ("cafe_table", source.square_table(mats, 0)),
            ("cafe_chair", source.backed_chair(mats)),
            ("counter", source.grounded_counter(mats)),
        ]:
            mesh = self.collapse_collection(coll, key)
            print("COMMERCIAL_COLLAPSED", key, flush=True)
            mesh.transform(Matrix.Translation((0, 0, -0.1)))
            self.meshes[key] = mesh
        if "chair" not in self.meshes:
            self.meshes["chair"] = self.meshes["cafe_chair"]
            self.records.append(
                {
                    "kind": "chair",
                    "method": "dimension-invalid native chair rejected; original complete restaurant chair factory used",
                }
            )
        # Source shelf factory accepts a set of exact bottle/jar masters; create those via its production recipe.
        bottle = source.master("astra_bottle")
        cyl = source.cyl
        for n, p, s, key in [
            ("body", (0, 0, 0.18), (0.075, 0.075, 0.18), "glass"),
            ("shoulder", (0, 0, 0.36), (0.062, 0.062, 0.055), "glass"),
            ("neck", (0, 0, 0.435), (0.034, 0.034, 0.045), "glass"),
            ("cap", (0, 0, 0.49), (0.043, 0.043, 0.018), "green"),
            ("label", (0, 0, 0.18), (0.079, 0.079, 0.075), "paper"),
        ]:
            source.add(bottle, n, cyl(), p, s, mats[key])
        self.meshes["bottle"] = self.collapse_collection(bottle, "bottle")
        # Flatten nested merchandise instances explicitly; the shelf structure itself remains the source factory output.
        shelf = source.complete_shelf(mats, 0, [bottle])
        for obj in list(shelf.objects):
            if obj.instance_collection is bottle:
                replacement = bpy.data.objects.new(
                    obj.name + "_mesh", self.meshes["bottle"]
                )
                shelf.objects.link(replacement)
                replacement.matrix_world = Matrix.LocRotScale(
                    obj.location, obj.rotation_euler.to_quaternion(), obj.scale
                )
                bpy.data.objects.remove(obj, do_unlink=True)
        self.meshes["shelf"] = self.collapse_collection(shelf, "stocked_shelf")
        self.meshes["shelf"].transform(Matrix.Translation((0, 0, -0.1)))
        self.records.append(
            {
                "kind": "retail_and_cafe",
                "source": str(Path(source.__file__).resolve()),
                "sha256": file_hash(Path(source.__file__)),
                "method": "existing complete shelf/table/chair/counter production factories",
            }
        )

    def botanical_trees(self):
        inventory = json.loads((OUT / "source_inventory.json").read_text())
        info = inventory["botanical_city"]
        path = Path(info["path"])
        names = [
            n
            for n in info["objects"]
            if "tree_master:42:" in n or "tree_master:512:" in n
        ]
        names = [n for n in names if "bark" in n or "canopy" in n or "branch" in n]
        if not names:
            raise RuntimeError("No authored botanical masters in full07")
        with bpy.data.libraries.load(str(path), link=False) as (src, dst):
            dst.objects = names
        for seed in (42, 512):
            selected = [
                o
                for o in dst.objects
                if o is not None
                and f"tree_master:{seed}:" in o.name
                and o.type == "MESH"
            ]
            if len(selected) < 2:
                raise RuntimeError("Incomplete botanical tree " + str(seed))
            coll = collection("astra_source_tree_" + str(seed))
            for obj in selected:
                coll.objects.link(obj)
            self.meshes["tree_" + str(seed)] = self.collapse_collection(
                coll, "tree_" + str(seed)
            )
            self.records.append(
                {
                    "kind": "botanical_tree",
                    "seed": seed,
                    "source": str(path),
                    "source_objects": [o.name for o in selected],
                    "method": "exact full07 bark and merged LeafFactory canopy",
                }
            )

    def save(self):
        # Source file identity is checked once, and referenced by every native asset record.
        if hasattr(self, "native_hash_source"):
            digest = file_hash(self.native_hash_source)
            for record in self.records:
                if record.get("source") == str(self.native_hash_source):
                    record["source_sha256"] = digest
        (OUT / "asset_registry.json").write_text(
            json.dumps({"assets": self.records}, indent=2), encoding="utf8"
        )
        bpy.data.libraries.write(
            str(OUT / "asset_library.blend"),
            set(self.meshes.values()) | set(self.materials.values()),
            fake_user=True,
            compress=True,
        )

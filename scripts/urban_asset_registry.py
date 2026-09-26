"""Master/instance data model and Blender registry for the urban pipeline."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json

import bpy
from mathutils import Euler, Matrix, Vector


def stable_id(value) -> str:
    payload = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


@dataclass(frozen=True)
class AssetSpec:
    asset_id: str
    kind: str
    builder: str | None = None
    source: str | None = None
    selector: dict = field(default_factory=dict)
    variant: dict = field(default_factory=dict)
    version: int = 1


@dataclass(frozen=True)
class InstanceSpec:
    instance_id: str
    asset_id: str
    target_collection: str
    transform: dict = field(default_factory=dict)
    material_variant: str | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class MasterHandle:
    asset_id: str
    collection: bpy.types.Collection | None = None
    object: bpy.types.Object | None = None
    signature: str = ""


class MasterAssetRegistry:
    def __init__(self, scene=None, run_id="urban_pipeline"):
        self.scene = scene or bpy.context.scene
        self.run_id = run_id
        self.handles: dict[str, MasterHandle] = {}
        self.root = bpy.data.collections.get("C2W_MASTERS")
        if self.root is None:
            self.root = bpy.data.collections.new("C2W_MASTERS")
            self.root["c2w_role"] = "master_root"
        self.instances_root = bpy.data.collections.get("C2W_INSTANCES")
        if self.instances_root is None:
            self.instances_root = bpy.data.collections.new("C2W_INSTANCES")
            self.scene.collection.children.link(self.instances_root)

    def register_collection(self, spec: AssetSpec, collection) -> MasterHandle:
        signature = stable_id({"spec": spec.__dict__})
        old = self.handles.get(spec.asset_id)
        if old:
            if old.signature != signature:
                raise ValueError(f"Conflicting AssetSpec for {spec.asset_id}")
            return old
        collection["c2w_role"] = "master"
        collection["c2w_asset_id"] = spec.asset_id
        for obj in collection.all_objects:
            obj["c2w_role"] = "master"
            obj["c2w_asset_id"] = spec.asset_id
        handle = MasterHandle(spec.asset_id, collection=collection, signature=signature)
        self.handles[spec.asset_id] = handle
        return handle

    def register_object(self, spec: AssetSpec, obj) -> MasterHandle:
        signature = stable_id({"spec": spec.__dict__})
        old = self.handles.get(spec.asset_id)
        if old:
            if old.signature != signature:
                raise ValueError(f"Conflicting AssetSpec for {spec.asset_id}")
            return old
        obj["c2w_role"] = "master"
        obj["c2w_asset_id"] = spec.asset_id
        handle = MasterHandle(spec.asset_id, object=obj, signature=signature)
        self.handles[spec.asset_id] = handle
        return handle

    def ensure_master(self, spec: AssetSpec, builder=None) -> MasterHandle:
        if spec.asset_id in self.handles:
            return self.handles[spec.asset_id]
        if builder is None:
            raise KeyError(f"No builder supplied for {spec.asset_id}")
        datablock = builder(spec)
        if isinstance(datablock, bpy.types.Collection):
            return self.register_collection(spec, datablock)
        return self.register_object(spec, datablock)

    def _target(self, name):
        coll = bpy.data.collections.get(name)
        if coll is None:
            coll = bpy.data.collections.new(name)
            self.instances_root.children.link(coll)
        return coll

    @staticmethod
    def _matrix(transform):
        loc = Vector(transform.get("location", (0, 0, 0)))
        rot = Euler(transform.get("rotation_euler", (0, 0, 0))).to_matrix().to_4x4()
        scale = Matrix.Diagonal(Vector((*transform.get("scale", (1, 1, 1)), 1)))
        return Matrix.Translation(loc) @ rot @ scale

    def instantiate(self, spec: InstanceSpec):
        handle = self.handles[spec.asset_id]
        if handle.collection:
            obj = bpy.data.objects.new(spec.instance_id, None)
            obj.instance_type = "COLLECTION"
            obj.instance_collection = handle.collection
        else:
            obj = bpy.data.objects.new(spec.instance_id, handle.object.data)
        self._target(spec.target_collection).objects.link(obj)
        obj.matrix_world = self._matrix(spec.transform)
        obj["c2w_role"] = "instance"
        obj["c2w_asset_id"] = spec.asset_id
        obj["c2w_instance_id"] = spec.instance_id
        obj["c2w_run_id"] = self.run_id
        obj["c2w_schema_version"] = 2
        return obj

    def instantiate_many(self, specs):
        return [self.instantiate(spec) for spec in specs]

    def make_unique(self, instance_obj, reason):
        if instance_obj.data:
            instance_obj.data = instance_obj.data.copy()
        instance_obj["c2w_role"] = "unique"
        instance_obj["c2w_unique_reason"] = reason
        return instance_obj

    def remove_generated_instances(self, run_id=None):
        target = run_id or self.run_id
        for obj in list(bpy.data.objects):
            if (
                obj.get("c2w_role") in {"instance", "unique"}
                and obj.get("c2w_run_id") == target
            ):
                bpy.data.objects.remove(obj, do_unlink=True)

    def stats(self):
        return {
            "objects_total": len(bpy.data.objects),
            "master_objects": sum(
                o.get("c2w_role") == "master" for o in bpy.data.objects
            ),
            "instance_objects": sum(
                o.get("c2w_role") == "instance" for o in bpy.data.objects
            ),
            "unique_meshes": len(bpy.data.meshes),
            "materials": len(bpy.data.materials),
        }

    def validate(self):
        bad = []
        for obj in bpy.data.objects:
            if obj.get("c2w_role") == "instance" and not obj.get("c2w_asset_id"):
                bad.append(obj.name)
        return {"passed": not bad, "instances_without_asset_id": bad, **self.stats()}

"""Run with Blender: blender --background --python scripts/test_urban_instancing.py."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bpy
import urban_assets as UA
from urban_asset_registry import AssetSpec, InstanceSpec, MasterAssetRegistry

bpy.ops.wm.read_factory_settings(use_empty=True)
UA.reset_scene()
UA.build_all_materials()
test_coll = UA.new_coll("TestInstances")

a = UA._box("window_a", 0, 0, 0, 1, 0.1, 2, UA.M["window"], test_coll)
b = UA._box("window_b", 3, 0, 0, 1, 0.1, 2, UA.M["window"], test_coll)
assert a.data is b.data, "primitive boxes did not share Mesh Data"

registry = MasterAssetRegistry(run_id="test-run")
master_coll = bpy.data.collections.new("TEST_MASTER_COLLECTION")
master_obj = UA._box("master_part", 0, 0, 0, 1, 1, 1, UA.M["wall"], master_coll)
spec = AssetSpec("test.multi", "procedural_collection", builder="test")
registry.register_collection(spec, master_coll)
instances = registry.instantiate_many(
    [
        InstanceSpec("test.000", "test.multi", "TestPlaced", {"location": [0, 0, 0]}),
        InstanceSpec("test.001", "test.multi", "TestPlaced", {"location": [4, 0, 0]}),
    ]
)
assert instances[0].instance_collection is instances[1].instance_collection
assert instances[0].instance_collection is master_coll

user_obj = bpy.data.objects.new("USER_OBJECT_MUST_SURVIVE", None)
bpy.context.scene.collection.objects.link(user_obj)
registry.remove_generated_instances("test-run")
assert bpy.data.objects.get("USER_OBJECT_MUST_SURVIVE") is user_obj
assert bpy.data.collections.get("TEST_MASTER_COLLECTION") is master_coll
assert not any(o.get("c2w_run_id") == "test-run" for o in bpy.data.objects)

print("C2W_INSTANCE_TEST_PASSED")

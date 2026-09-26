"""Cut existing site ground with the actual water footprint, preserving connected banks."""
import bpy, sys, json, os
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
k = sys.argv[-1]
d = O / k
m = json.loads((d / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
if k == "waterside_dining":
    import runpy

    runpy.run_path(str(R / "scripts/fix_connect3_river_ground.py"), run_name="__main__")
    raise SystemExit(0)
if m.get("water_ground_connected"):
    raise SystemExit(0)
c = bpy.data.collections["Connected_streets_and_landscape"]
g = next(o for o in c.objects if "continuous_ground" in o.name)
water = next(
    o
    for o in c.objects
    if o.instance_collection
    and o.instance_collection.name in {"ASSET_lake", "ASSET_river"}
)
lake = water.instance_collection.name == "ASSET_lake"
src = next(
    o
    for o in water.instance_collection.all_objects
    if ("lake_water_volume" if lake else "river_water_surface") in o.name
)
g.location.y = 0
g.dimensions.y = 2000
bpy.context.view_layer.update()
g.data = g.data.copy()
bpy.ops.object.select_all(action="DESELECT")
g.select_set(True)
bpy.context.view_layer.objects.active = g
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
cut = src.copy()
cut.data = src.data.copy()
cut.parent = None
cut.constraints.clear()
c.objects.link(cut)
cut.matrix_world = water.matrix_world @ src.matrix_world
if lake:
    cut.location.z += 1
    cut.scale.z *= 3
else:
    cut.location.z += 1.5
    solid = cut.modifiers.new("Temporary footprint volume", "SOLIDIFY")
    solid.thickness = 6
    solid.offset = -1
bpy.context.view_layer.update()
mod = g.modifiers.new("Actual existing water footprint", "BOOLEAN")
mod.operation = "DIFFERENCE"
mod.solver = "EXACT"
mod.object = cut
bpy.context.view_layer.objects.active = g
bpy.ops.object.modifier_apply(modifier=mod.name)
bpy.data.objects.remove(cut, do_unlink=True)
assert len(g.data.vertices) > 8, "Ground boolean removed terrain"
m[
    "water_ground_connected"
] = "Existing ground retained around full source water footprint; opening cut with existing water geometry"
g["ground_opening_source"] = src.name
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
print("WATER_GROUND_CONNECTED", k, len(g.data.vertices), flush=True)

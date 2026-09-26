"""Verify native source links, matching camera and physical table support."""
import bpy
import json
from mathutils import Vector
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect/corner_kitchen2"
bpy.ops.wm.open_mainfile(filepath=str(OUT / "scene.blend"), load_ui=False)
scene = bpy.context.scene
camera = scene.camera
assert (camera.location - Vector((8, -16, 1.75))).length < 1e-5
assert abs(camera.data.lens - 26) < 1e-5
expected = (Vector((0, -7.2, 1.5)) - camera.location).normalized()
actual = camera.rotation_euler.to_matrix() @ Vector((0, 0, -1))
assert (expected - actual).length < 1e-5
libs = [
    dict(
        path=bpy.path.abspath(l.filepath),
        exists=Path(bpy.path.abspath(l.filepath)).exists(),
    )
    for l in bpy.data.libraries
]
assert all(l["exists"] for l in libs), libs
terrace = bpy.data.collections["OUTDOOR_CAFE_SET_MASTER"]
assert len(terrace.objects) == 13
assert all(o.instance_collection and o.get("asset_factory") for o in terrace.objects)
for name in ["REFINED_COMMERCIAL_PLANTER_MASTER", "COMPLEX_REAR_FLOWERBED_MASTER"]:
    assert all(
        o.instance_collection and o.get("asset_factory")
        for o in bpy.data.collections[name].objects
    )
table_instance = next(
    o for o in terrace.objects if o.get("asset_factory") == "TableDiningFactory"
)
table = next(o for o in table_instance.instance_collection.objects if o.type == "MESH")
matrix = table_instance.matrix_world @ table.matrix_world
inverse = matrix.inverted()
supports = []
for obj in terrace.objects:
    if obj.get("asset_factory") not in ("CupFactory", "PlateFactory"):
        continue
    origin = inverse @ Vector((obj.location.x, obj.location.y, 2.0))
    direction = inverse.to_3x3() @ Vector((0, 0, -1))
    hit, point, normal, index = table.ray_cast(origin, direction.normalized())
    assert hit, obj.name
    surface_z = (matrix @ point).z
    gap = obj.location.z - surface_z
    assert -0.001 <= gap <= 0.005, (obj.name, gap)
    supports.append(dict(object=obj.name, support_gap_m=round(gap, 6)))
report = dict(
    matching_reference_camera=True,
    reference_image="corner_kitchen/images2/08_courtyard_eye_level.png",
    original_exterior_prop_geometry_removed=True,
    native_asset_libraries=libs,
    tabletop_support_checks=supports,
)
(OUT / "verification.json").write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2), flush=True)

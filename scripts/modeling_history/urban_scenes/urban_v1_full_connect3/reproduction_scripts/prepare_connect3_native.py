import bpy, json, sys
from pathlib import Path
from mathutils import Matrix, Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as A

O = A.O
D = A.A
source = R / "infinigen/outputs/indoor_outdoor_villa_demo2/coarse/scene.blend"
bpy.ops.wm.read_factory_settings(use_empty=True)
with bpy.data.libraries.load(str(source), link=False) as (a, b):
    b.objects = [
        n
        for f, count in [
            ("ChairFactory", 6),
            ("CeilingLightFactory", 3),
            ("WallArtFactory", 2),
            ("TableDiningFactory", 1),
            ("PlantContainerFactory", 4),
            ("FloorLampFactory", 2),
        ]
        for n in sorted(
            x for x in a.objects if x.startswith(f + "(") and ".spawn_asset(" in x
        )[:count]
    ]
counts = {}
cols = []
report = {}
for ob in b.objects:
    f = ob.name.split("(")[0]
    i = counts.get(f, 0)
    counts[f] = i + 1
    key = f + "_" + str(i)
    c = bpy.data.collections.new("NATIVE3_" + key)
    bpy.context.scene.collection.children.link(c)
    c.objects.link(ob)
    ob.parent = None
    ob.matrix_world = Matrix.Identity(4)
    ob.hide_render = False
    ob.hide_viewport = False
    bpy.context.view_layer.update()
    pts = [ob.matrix_world @ Vector(v) for v in ob.bound_box]
    lo = Vector([min(p[k] for p in pts) for k in range(3)])
    hi = Vector([max(p[k] for p in pts) for k in range(3)])
    ob.location = (-0.5 * (lo.x + hi.x), -0.5 * (lo.y + hi.y), -lo.z)
    ob["asset_source_blend"] = str(source)
    ob["source_object"] = ob.name
    report[key] = {"dimensions": list(hi - lo), "source_object": ob.name}
    cols.append(c)
bpy.data.libraries.write(
    str(D / "native_variants.blend"),
    set(cols),
    path_remap="RELATIVE_ALL",
    compress=True,
)
(D / "native_variants.json").write_text(json.dumps(report, indent=2))
# Pavement and ground are authored architectural components, including modifiers.
bpy.ops.wm.read_factory_settings(use_empty=True)
src = A.P / "urban_v3_all43_25/urban_v3_all43_25.blend"
with bpy.data.libraries.load(str(src), link=False) as (a, b):
    names = [
        "all43_24:cafe_frontage_paver_field",
        "all43_20:relocated_rear_parking_asphalt",
    ]
    names += [next(n for n in a.objects if n.startswith("all43_24:") and "joint" in n)]
    b.objects = names
cols = set()
for key, ob in zip(["paving", "asphalt", "joint"], b.objects):
    c = bpy.data.collections.new("ASSET_" + key)
    c.objects.link(ob)
    ob.parent = None
    ob["source_object"] = ob.name
    cols.add(c)
bpy.data.libraries.write(
    str(D / "site_components.blend"), cols, path_remap="RELATIVE_ALL", compress=True
)
# A second complete botanical form from the user's existing asset library.
A.external("tree619", "urban_v3_lake3", ["full02:MASTER:TreeFactory:619"])
print("NATIVE_VARIANTS_READY", flush=True)

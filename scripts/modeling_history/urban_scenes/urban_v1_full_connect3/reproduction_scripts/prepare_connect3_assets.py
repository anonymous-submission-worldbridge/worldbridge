"""Extract immutable, attributed full-detail asset assemblies; no proxy geometry."""
import bpy, sys, json, math, os
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
P = R / "infinigen/outputs/outdoor_part_demo"
A = O / "shared_assets"


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def metadata(c):
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    lo = Vector((1e9,) * 3)
    hi = -lo
    verts = 0
    count = 0
    for i in deps.object_instances:
        ob = i.object
        if ob.type not in {"MESH", "CURVE", "FONT"} or ob.hide_render:
            continue
        for v in ob.bound_box:
            p = i.matrix_world @ Vector(v)
            for k in range(3):
                lo[k] = min(lo[k], p[k])
                hi[k] = max(hi[k], p[k])
        if ob.type == "MESH":
            verts += len(ob.data.vertices)
            count += 1
    return {
        "bounds": [list(lo), list(hi)],
        "dimensions": list(hi - lo),
        "mesh_instances": count,
        "evaluated_vertices": verts,
    }


def save(key, c, source, normalize=True):
    meta = metadata(c)
    if normalize:
        lo, hi = map(Vector, meta["bounds"])
        shift = Vector((-(lo.x + hi.x) / 2, -lo.y, -lo.z))
        for ob in c.objects:
            ob.location += shift
        meta = metadata(c)
    meta.update(key=key, collection="ASSET_" + key, source=str(source))
    c.name = "ASSET_" + key
    c["source_blend"] = str(source)
    c["quality"] = "full_authored_geometry"
    for lib in bpy.data.libraries:
        lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
    bpy.data.libraries.write(
        str(A / (key + ".blend")), {c}, path_remap="RELATIVE_ALL", compress=True
    )
    (A / (key + ".json")).write_text(json.dumps(meta, indent=2))
    print("ASSET_READY", key, meta, flush=True)


def external(key, folder, names):
    reset()
    source = next((P / folder).glob("*.blend"))
    with bpy.data.libraries.load(str(source), link=False) as (a, b):
        b.collections = [n for n in a.collections if n in names]
    assert len(b.collections) == len(names), (key, names)
    c = bpy.data.collections.new("temp")
    bpy.context.scene.collection.children.link(c)
    for src in b.collections:
        bpy.context.scene.collection.children.link(src)
    bpy.context.view_layer.update()
    srcobjects = {ob for src in b.collections for ob in src.all_objects}
    deps = bpy.context.evaluated_depsgraph_get()
    poses = {ob: ob.evaluated_get(deps).matrix_world.copy() for ob in srcobjects}
    for ob in srcobjects:
        if ob.hide_render or ob.type in {"CAMERA", "LIGHT"}:
            continue
        mw = poses[ob]
        n = ob.copy()
        n.parent = None
        n.constraints.clear()
        n.animation_data_clear()
        c.objects.link(n)
        n.matrix_world = mw
        n["source_object"] = ob.name
    for src in b.collections:
        bpy.context.scene.collection.children.unlink(src)
    save(key, c, source)


def core(key):
    source = O / "source_snapshots" / key / "scene.blend"
    bpy.ops.wm.open_mainfile(filepath=str(source), load_ui=False)
    c = bpy.data.collections["Architecture_and_furnished_interior"]
    for child in list(bpy.context.scene.collection.children):
        if child != c:
            bpy.context.scene.collection.children.unlink(child)
    # Correct pathological grid seams left by scaling authored beveled floor tiles.
    for ob in c.objects:
        if "modeled_floor_finish" in ob.name:
            for mod in ob.modifiers:
                if mod.type == "BEVEL":
                    mod.width = 0.0005
                    mod.segments = 2
    save(key, c, source, normalize=False)


if __name__ == "__main__":
    for key in ["restaurant", "cafe", "market", "hospital", "pharmacy", "library"]:
        if not (A / (key + ".blend")).exists():
            core(key)
    items = [
        ("school", "urban_v3_school5", ["school:ACADEMIC_MID_EAST"]),
        ("gym", "urban_v3_school5", ["school:GYMNASIUM"]),
        ("police", "urban_v3_police3", ["police:POLICE_C_BLUE_PORTAL_CMU"]),
        ("fire", "urban_v3_fire7", ["fire_region_v7:STATION_INDUSTRIAL_ANNEX"]),
        ("delivery", "urban_v3_delivery6", ["delivery:DELIVERY_STATION"]),
        ("parcel", "urban_v3_delivery6", ["delivery:PARCEL_LOCKER"]),
        ("food_locker", "urban_v3_delivery6", ["delivery:FOOD_DELIVERY_LOCKER"]),
        ("atm", "urban_v3_atm4", ["urban_v3_atm4:ATM_01A_SILVER_FREESTANDING"]),
        ("gas", "urban_v3_gass4", ["gas_station:BLUE_ORANGE"]),
        (
            "house",
            "urban_v3_all41_house_small_a",
            ["unique_assets", "assets", "skirting"],
        ),
        ("fitness", "urban_v3_fitness5", ["outdoor_fitness:asset_rowing_machine"]),
        (
            "fitness_walk",
            "urban_v3_fitness5",
            ["outdoor_fitness:asset_air_walker_double"],
        ),
        ("bank", "urban_v3_all46_5", ["all46_2:BANK_04_BRONZE_FRAME_BRANCH"]),
    ]
    # Resolve bank namespace from the saved generator, rather than guessing it.
    folder = P / "urban_v3_all46_5"
    f = next(folder.glob("*.blend"))
    with bpy.data.libraries.load(str(f), link=True) as (a, b):
        bank = next(
            n for n in a.collections if n.endswith("BANK_04_BRONZE_FRAME_BRANCH")
        )
    items[-1] = ("bank", "urban_v3_all46_5", [bank])
    for key, folder, names in items:
        if not (A / (key + ".blend")).exists():
            external(key, folder, names)
    if not (A / "townhouse.blend").exists():
        external("townhouse", "urban_v3_all45_09", ["all45_09:detached_townhouse_01"])
    # Independent authored shop, furniture, vehicle and planting masters.
    masters = {
        "bar": "HAWTHORN_STREET_BAR_MASTER",
        "fastfood": "MCDONALDS_ROADSIDE_RESTAURANT_MASTER",
        "corner_store": "CORNER_711_MIXED_USE_MASTER",
        "cafe_set": "OUTDOOR_CAFE_SET_MASTER",
        "flowerbed": "COMPLEX_REAR_FLOWERBED_MASTER",
        "bike": "SHAREDBICYCLE4_SINGLE_BICYCLE_MASTER",
        "streetlight": "all43_01:MASTER:streetlight",
        "bin": "all43_01:MASTER:trash_bin",
        "car": "all43_02:MASTER:audi_q7",
        "pastry": "all43_24:MASTER:PASTRY_PLATE",
        "carton": "all43_11_object3:MASTER:folded_carton",
        "can": "all43_11_object3:MASTER:ring_pull_can",
    }
    for key, name in masters.items():
        if not (A / (key + ".blend")).exists():
            external(key, "urban_v3_all43_25", [name])
    reset()
    f = next((P / "urban_v3_factory3").glob("*.blend"))
    with bpy.data.libraries.load(str(f), link=False) as (a, b):
        b.collections = ["urban_factory_showcase"]
    c = b.collections[0]
    bpy.context.scene.collection.children.link(c)
    bpy.context.view_layer.update()
    (O / "factory_objects.json").write_text(
        json.dumps(
            [
                {
                    "name": o.name,
                    "type": o.type,
                    "location": list(o.matrix_world.translation),
                    "dimensions": list(o.dimensions),
                }
                for o in c.all_objects
            ],
            indent=1,
        )
    )
    print("PREPARATION_COMPLETE", flush=True)

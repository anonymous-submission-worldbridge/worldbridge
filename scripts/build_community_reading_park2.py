"""Replace exterior furniture only; preserve source camera definitions verbatim."""
import bpy, json, math, sys, copy
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
SRC = BASE / "community_reading_park"
OUT = BASE / "community_reading_park2"
meta = json.loads((OUT / "assets/native_furniture.json").read_text())
lookup = {r["role"]: r for r in meta}
bpy.ops.wm.open_mainfile(filepath=str(SRC / "scene.blend"), load_ui=False)
# Absolute paths before saving under the new directory; existing libraries remain read-only.
for lib in bpy.data.libraries:
    if not lib.parent:
        lib.filepath = bpy.path.abspath(lib.filepath)
with bpy.data.libraries.load(
    str(OUT / "assets/native_furniture.blend"), link=False
) as (a, b):
    b.collections = [r["collection"] for r in meta]
assets = {r["role"]: bpy.data.collections[r["collection"]] for r in meta}
placements = []


def put(c, role, name, loc, angle=0):
    o = bpy.data.objects.new("park2:" + name, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = assets[role]
    o.location = loc
    o.rotation_euler.z = angle
    o["asset_factory"] = lookup[role]["factory"]
    o["factory_seed"] = lookup[role]["seed"]
    o["native_role"] = role
    placements.append(
        dict(name=o.name, role=role, location=list(loc), rotation_z=angle)
    )
    return o


setting = bpy.data.collections.new("PARK2_NATIVE_OUTDOOR_SETTING")
cy = 1.355
top = lookup["table"]["dimensions"][2]
put(setting, "table", "table", (0, cy, 0))
for i, (x, y) in enumerate([(0, -0.87), (0, 0.87), (-1.12, 0), (1.12, 0)]):
    put(setting, "chair", f"chair_{i}", (x, cy + y, 0), math.atan2(-y, -x))
# Four place settings, all supported by the real factory tabletop.
for i, (x, y, angle) in enumerate(
    [
        (-0.50, 0, 0),
        (0.50, 0, math.pi),
        (0, -0.29, math.pi / 2),
        (0, 0.29, -math.pi / 2),
    ]
):
    put(setting, "plate", f"plate_{i}", (x, cy + y, top + 0.001), angle)
    dx, dy = math.cos(angle), math.sin(angle)
    sx, sy = -dy, dx
    put(
        setting,
        "cup",
        f"cup_{i}",
        (x + 0.15 * dx + 0.17 * sx, cy + y + 0.15 * dy + 0.17 * sy, top + 0.001),
        angle,
    )
    put(
        setting,
        "fork",
        f"fork_{i}",
        (x - 0.16 * sx, cy + y - 0.16 * sy, top + 0.001),
        angle,
    )
    put(
        setting,
        "spoon",
        f"spoon_{i}",
        (x + 0.16 * sx, cy + y + 0.16 * sy, top + 0.001),
        angle,
    )
bench = bpy.data.collections.new("PARK2_NATIVE_BENCH_SETTING")
bm = json.loads((BASE / "shared_assets/bench.json").read_text())
lo, hi = map(Vector, bm["bounds"])
put(bench, "bench", "bench", ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
replaced = []
for o in list(bpy.data.objects):
    if o.library or not o.instance_collection:
        continue
    old = o.instance_collection.name
    if old not in {"ASSET_cafe_set", "ASSET_bench"}:
        continue
    before = dict(
        name=o.name,
        old_collection=old,
        matrix_world=[list(row) for row in o.matrix_world],
    )
    o.instance_collection = setting if old == "ASSET_cafe_set" else bench
    before["new_collection"] = o.instance_collection.name
    replaced.append(before)
assert sum(r["old_collection"] == "ASSET_cafe_set" for r in replaced) == 5
assert sum(r["old_collection"] == "ASSET_bench" for r in replaced) == 10
m = json.loads((SRC / "scene_manifest.json").read_text())
original_shots = copy.deepcopy(m["shots"])
m["scene"] = "community_reading_park2"
m["source_scene"] = "community_reading_park"
m[
    "furniture_revision"
] = "Fresh full-resolution native Infinigen factories; ChairFactory width-parameterized benches"
assert m["shots"] == original_shots
(OUT / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.view_layer.update()
# Verify evaluated native geometry has finite coordinates, and feet sit on the paving.
dg = bpy.context.evaluated_depsgraph_get()
native_bounds = []
for inst in dg.object_instances:
    ob = inst.object
    if not ob.get("native_role") or ob.type != "MESH":
        continue
    pts = [inst.matrix_world @ Vector(v) for v in ob.bound_box]
    lower = [min(p[k] for p in pts) for k in range(3)]
    upper = [max(p[k] for p in pts) for k in range(3)]
    assert all(math.isfinite(v) for v in lower + upper)
    if ob["native_role"] in {"table", "chair", "bench"}:
        assert abs(lower[2] - 0.14) < 0.005, (ob.name, lower)
    native_bounds.append(dict(role=ob["native_role"], bounds=[lower, upper]))
from collections import Counter

counts = dict(Counter(r["role"] for r in native_bounds))
assert counts == dict(
    table=5, chair=20, bench=10, cup=20, plate=20, fork=20, spoon=20
), counts
report = dict(
    source_blend=str(SRC / "scene.blend"),
    native_assets=meta,
    replacements=replaced,
    placements=placements,
    visible_native_counts=counts,
    evaluated_native_bounds=native_bounds,
    cameras_unchanged=True,
    camera_count=len(original_shots),
    grounding_passed=True,
)
(OUT / "asset_replacement_manifest.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene.blend"), compress=True)
print("PARK2_BUILD_COMPLETE", counts, flush=True)

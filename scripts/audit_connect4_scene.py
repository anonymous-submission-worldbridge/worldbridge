"""Geometric gates for full models, both entry directions and camera poses."""
import bpy, json, sys, math, hashlib
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import A, O

key = sys.argv[-1]
d = O / key
m = json.loads((d / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
s = bpy.context.scene
dg = bpy.context.evaluated_depsgraph_get()
issues = []
entries = []
cameras = []
for b in m["buildings"]:
    if not b["enterable"]:
        continue
    a = json.loads((A / (b["asset"] + ".json")).read_text())
    T = Matrix(b["matrix"])
    direction = T.to_3x3() @ Vector((0, 1, 0))
    hits = []
    for x in [-0.35, 0, 0.35]:
        for h in [0.35, 0.65, 1.0, 1.4, 1.7, 1.95]:
            p = T @ Vector((x, -6.5, a["floor_z"] + h))
            hit, loc, n, i, ob, mat = s.ray_cast(
                dg, p, direction, distance=6.5 + a["inside_y"]
            )
            if hit:
                hits.append(dict(x=x, height=h, object=ob.name, point=list(loc)))
    entry = dict(
        asset=b["asset"],
        position=b["position"],
        tested_width_m=0.70,
        inside_distance_m=a["inside_y"],
        clear=not hits,
        hits=hits,
    )
    entries.append(entry)
    if hits:
        issues.append({"entry": entry})
for name, shot in m["shots"].items():
    p = Vector(shot["position"])
    v = (Vector(shot["target"]) - p).normalized()
    hit, loc, n, i, ob, mat = s.ray_cast(dg, p, v, distance=0.32)
    item = dict(shot=name, near_clear=not hit, object=ob.name if hit else None)
    cameras.append(item)
    if hit:
        issues.append(item)
missing = []
for lib in bpy.data.libraries:
    if not Path(bpy.path.abspath(lib.filepath)).exists():
        missing.append(lib.filepath)
for im in bpy.data.images:
    if (
        im.source == "FILE"
        and im.filepath
        and not im.packed_file
        and not Path(bpy.path.abspath(im.filepath, library=im.library)).exists()
    ):
        missing.append(im.filepath)
if missing:
    issues.append(dict(missing_dependencies=missing))
overlaps = []
for i, b in enumerate(m["buildings"]):
    for other in m["buildings"][:i]:
        if all(
            min(b["bounds"][1][k], other["bounds"][1][k])
            - max(b["bounds"][0][k], other["bounds"][0][k])
            > 0.01
            for k in [0, 1]
        ):
            overlaps.append([b["asset"], other["asset"]])
if overlaps:
    issues.append(dict(building_overlaps=overlaps))
hit, *_ = s.ray_cast(
    dg, Vector((0, 0.8, m["floor_z"] + 2)), Vector((0, 0, -1)), distance=4
)
if not hit:
    issues.append(dict(missing_primary_floor=True))
report = dict(
    scene=key,
    passed=not issues,
    entries=entries,
    cameras=cameras,
    missing_dependencies=missing,
    building_overlaps=overlaps,
    raycast_positive_control=hit,
    issues=issues,
    blend_bytes=(d / "scene.blend").stat().st_size,
    scope="Measured 0.7m entry prisms via sampled rays, camera near rays, building bounding boxes and file dependencies; visual review remains separate",
)
(d / "geometry_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
print("GEOMETRY_AUDIT", key, report["passed"], json.dumps(issues), flush=True)
if issues:
    raise SystemExit(1)

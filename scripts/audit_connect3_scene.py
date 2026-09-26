"""Check camera positions, physical doorway traversal and dependencies."""
import bpy, sys, json, math
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
k = sys.argv[-1]
d = O / k
m = json.loads((d / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
s = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()
issues = []
checks = []
for name, shot in m["shots"].items():
    p = Vector(shot["position"])
    v = (Vector(shot["target"]) - p).normalized()
    hit, pos, n, idx, ob, mat = s.ray_cast(deps, p, v, distance=0.3)
    check = {"shot": name, "near_clear": not hit, "object": ob.name if hit else None}
    checks.append(check)
    if hit:
        issues.append(check)
route = []
for x in [-0.24, 0, 0.24]:
    for z in [0.35, 0.8, 1.2, 1.6, 1.9]:
        hit, pos, n, idx, ob, mat = s.ray_cast(
            deps,
            Vector((x, -6.2, m["floor_z"] + z)),
            Vector((0, 1, 0)),
            distance=6.2 + m["video_inside_y"],
        )
        if hit:
            route.append({"x": x, "height": z, "object": ob.name, "point": list(pos)})
missing = []
for lib in bpy.data.libraries:
    if not Path(bpy.path.abspath(lib.filepath)).exists():
        missing.append(lib.filepath)
for im in bpy.data.images:
    if (
        im.source == "FILE"
        and not im.packed_file
        and im.filepath
        and not Path(bpy.path.abspath(im.filepath, library=im.library)).exists()
    ):
        missing.append(im.filepath)
# Positive-control floor ray ensures the primary asset participates in ray tests.
hit, *_ = s.ray_cast(deps, Vector((0, 0.8, 3)), Vector((0, 0, -1)), distance=5)
report = {
    "scene": k,
    "building_count": m["building_count"],
    "camera_checks": checks,
    "camera_issues": issues,
    "doorway_corridor": {"width_m": 0.48, "clear": not route, "hits": route},
    "missing_dependencies": missing,
    "raycast_positive_control": hit,
    "passed": not issues and not route and not missing and hit,
}
(d / "geometry_audit.json").write_text(json.dumps(report, indent=2))
print("CONNECT3_AUDIT", json.dumps(report), flush=True)
if not report["passed"]:
    raise RuntimeError("Geometry validation failed")

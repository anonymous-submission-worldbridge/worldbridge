"""Check real camera/portal clearance and saved scene dependencies."""
import bpy, json, sys, math
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
key = sys.argv[-1]
dest = O / key
m = json.loads((dest / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
scene = bpy.context.scene
deps = bpy.context.evaluated_depsgraph_get()
issues = []
checks = []
for name, shot in m["shots"].items():
    p = Vector(shot["position"])
    direction = (Vector(shot["target"]) - p).normalized()
    hit, loc, n, idx, obj, matrix = scene.ray_cast(deps, p, direction, distance=0.35)
    checks.append(
        {"shot": name, "near_clear": not hit, "hit": obj.name if hit else None}
    )
    if hit:
        issues.append(checks[-1])
route = []
for x in [-0.24, 0, 0.24]:
    for h in [0.35, 0.8, 1.2, 1.6, 1.9]:
        hit, loc, n, idx, obj, matrix = scene.ray_cast(
            deps,
            Vector((x, -6.2, m["floor_z"] + h)),
            Vector((0, 1, 0)),
            distance=6.2 + m.get("video_inside_y", 1.1),
        )
        if hit:
            route.append({"x": x, "height": h, "object": obj.name, "point": list(loc)})
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
report = {
    "scene": key,
    "camera_checks": checks,
    "camera_issues": issues,
    "video_swept_corridor": {
        "width_m": 0.48,
        "length_m": 6.2 + m.get("video_inside_y", 1.1),
        "heights_m": [0.35, 0.8, 1.2, 1.6, 1.9],
        "clear": not route,
        "hits": route,
    },
    "missing_dependencies": missing,
    "passed": not issues and not route and not missing,
}
(dest / "geometry_audit.json").write_text(json.dumps(report, indent=2))
print("AUDIT", json.dumps(report), flush=True)

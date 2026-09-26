"""Geometric and dependency checks on saved deliverable scenes (Blender)."""
import json
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"
reports = []
for manifest_path in sorted(OUT.glob("*/scene_manifest.json")):
    manifest = json.loads(manifest_path.read_text())
    bpy.ops.wm.open_mainfile(
        filepath=str(manifest_path.parent / "scene.blend"), load_ui=False
    )
    scene = bpy.context.scene
    deps = bpy.context.evaluated_depsgraph_get()
    hits = []
    for dx in (-0.20, 0, 0.20):
        for z in (0.65, 1.1, 1.6, 1.85, 2.05):
            origin = Vector((manifest["door_x"] + dx, manifest["front_y"] - 2.15, z))
            hit, loc, normal, idx, obj, matrix = scene.ray_cast(
                deps, origin, Vector((0, 1, 0)), distance=3.50
            )
            if hit:
                hits.append(
                    {
                        "x_offset": dx,
                        "height_m": z,
                        "object": obj.name,
                        "location": list(loc),
                    }
                )
    missing = []
    for lib in bpy.data.libraries:
        if not Path(bpy.path.abspath(lib.filepath)).exists():
            missing.append(lib.filepath)
    for image in bpy.data.images:
        if (
            image.source == "FILE"
            and not image.packed_file
            and image.filepath
            and not Path(
                bpy.path.abspath(image.filepath, library=image.library)
            ).exists()
        ):
            missing.append(image.filepath)
    short_hits = []
    for name, shot in manifest["shots"].items():
        origin = Vector(shot["position"])
        direction = (Vector(shot["target"]) - origin).normalized()
        hit, loc, normal, idx, obj, matrix = scene.ray_cast(
            deps, origin, direction, distance=0.25
        )
        if hit:
            short_hits.append({"shot": name, "object": obj.name, "location": list(loc)})
    report = {
        "scene": manifest["scene"],
        "portal_ray_grid": {
            "rays": 15,
            "width_m": 0.4,
            "height_range_m": [0.65, 2.05],
            "path_length_m": 3.5,
            "hits": hits,
            "pass": not hits,
        },
        "missing_dependencies": missing,
        "camera_near_obstructions": short_hits,
        "pass": not (hits or missing or short_hits),
    }
    (manifest_path.parent / "geometry_audit.json").write_text(
        json.dumps(report, indent=2)
    )
    reports.append(report)
    print("CONNECT_AUDIT " + json.dumps(report), flush=True)
(OUT / "geometry_audit.json").write_text(
    json.dumps({"scenes": reports, "pass": all(r["pass"] for r in reports)}, indent=2)
)

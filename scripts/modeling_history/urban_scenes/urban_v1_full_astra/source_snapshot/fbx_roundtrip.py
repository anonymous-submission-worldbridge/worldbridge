"""Read exported FBX back in Blender; validate geometry scale, door pivot and hull names.

This catches exporter corruption but is NOT a substitute for Unreal calibration.
"""
import json, sys, math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT


def run():
    data = json.loads((OUT / "ue5/scene_manifest.json").read_text())
    checks = []
    errors = []
    wanted = [
        "SM_SM_AstraCalibration_mesh",
        "SM_building_000_structure_mesh",
        "SM_building_000_glass_mesh",
        "SM_door_1_1_2_35",
        "SM_door_1_5_2_55",
        "SM_astra_native_bed",
        "SM_astra_master_stocked_shelf_mesh",
        "SM_astra_road_surface_mesh",
        "SM_astra_pedestrian_surface_mesh",
    ]
    # Use an empty scene so the native city remains untouched and name collisions cannot mask errors.
    scene = bpy.data.scenes.new("FBX_ROUNDTRIP")
    bpy.context.window.scene = scene
    for rec in data["meshes"]:
        if rec["id"] not in wanted:
            continue
        before = set(bpy.data.objects)
        bpy.ops.import_scene.fbx(
            filepath=str(OUT / "ue5" / rec["file"]),
            use_manual_orientation=True,
            axis_forward="Y",
            axis_up="Z",
            use_custom_normals=False,
        )
        added = [o for o in bpy.data.objects if o not in before and o.type == "MESH"]
        render = [o for o in added if not o.name.startswith("UCX_")]
        hulls = [o for o in added if o.name.startswith("UCX_")]
        points = [o.matrix_world @ Vector(p) for o in render for p in o.bound_box]
        actual = [
            [min(p[i] for p in points) * 100 for i in range(3)],
            [max(p[i] for p in points) * 100 for i in range(3)],
        ]
        delta = max(
            abs(actual[i][j] - rec["expected_bounds_cm"][i][j])
            for i in range(2)
            for j in range(3)
        )
        ok = delta < 0.1 and len(hulls) == rec["collision_hulls"]
        if not ok:
            errors.append(rec["id"])
        checks.append(
            {
                "asset": rec["id"],
                "status": "PASS" if ok else "FAIL",
                "bounds_max_error_cm": delta,
                "actual_bounds_cm": actual,
                "hulls": len(hulls),
                "expected_hulls": rec["collision_hulls"],
            }
        )
        for o in added:
            me = o.data
            bpy.data.objects.remove(o, do_unlink=True)
            if me.users == 0:
                bpy.data.meshes.remove(me)
    (OUT / "ue5/fbx_roundtrip_audit.json").write_text(
        json.dumps(
            {
                "status": "PASS" if not errors else "FAIL",
                "errors": errors,
                "checks": checks,
                "scope": "Representative FBX re-import in Blender 4.5.4. UE import and C++ build NOT RUN.",
            },
            indent=2,
        )
    )
    print("FBX_ROUNDTRIP_COMPLETE", len(checks), "failures", errors, flush=True)


if __name__ == "__main__":
    run()

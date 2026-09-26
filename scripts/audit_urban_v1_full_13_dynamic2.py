#!/usr/bin/env python3
"""Audit saved animations, not merely object names or declared speeds."""
import json
import sys
from pathlib import Path
import numpy as np
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic import action_fcurves, sha256
from build_urban_v1_full_13_dynamic2 import STATIC, FPS, END, G


def main():
    path = Path(bpy.data.filepath)
    report = json.loads((path.parent / "dynamic2_manifest.json").read_text())
    scene = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
    checks = {}
    details = []
    checks["unchanged_static_master"] = (
        sha256(STATIC / "urban_v1_full_13.blend") == report["source_master_sha256"]
    )
    checks["all_82_placements_preserved"] = (
        len([o for o in scene.objects if o.get("placement_id")])
        == report["source_placement_count"]
        == 82
    )
    checks["saved_blend_matches_manifest"] = (
        sha256(path) == report["output_blend_sha256"]
    )
    checks["continuous_collision_audit_passed"] = (
        report["traffic_audit"]["status"] == "PASS"
        and not report["traffic_audit"]["conflicts"]
    )
    speeds = []
    wheel_errors = []
    for car in report["vehicles"]:
        obj = bpy.data.objects[car["object"]]
        curves = {
            f.array_index: f for f in action_fcurves(obj) if f.data_path == "location"
        }
        if set(curves) != {0, 1, 2}:
            raise AssertionError("Missing translation channels: " + obj.name)
        points = np.array(
            [[curves[i].evaluate(f) for i in range(3)] for f in range(1, END + 1)]
        )
        velocity = np.diff(points, axis=0) * FPS
        expected = np.array(car["velocity"])
        err = float(np.abs(velocity - expected).max())
        speed = np.linalg.norm(velocity, axis=1)
        speeds.append(err < 0.001)
        details.append(
            {
                "vehicle": obj.name,
                "min_speed_mps": float(speed.min()),
                "max_speed_mps": float(speed.max()),
                "max_velocity_error": err,
            }
        )
        if any(len(f.modifiers) for f in curves.values()):
            raise AssertionError("Unexpected cyclic motion: " + obj.name)
        for wheel in car.get("wheel_measurements", []):
            curve = next(
                f
                for f in action_fcurves(bpy.data.objects[wheel["object"]])
                if f.data_path == "rotation_euler" and f.array_index == 1
            )
            omega = (curve.evaluate(END) - curve.evaluate(1)) / ((END - 1) / FPS)
            contact = expected + np.cross(
                np.array(wheel["axle_world"]) * omega,
                np.array([0, 0, -wheel["radius_m"]]),
            )
            wheel_errors.append(float(np.linalg.norm(contact)))
    checks["18_actual_constant_speed_trajectories"] = len(speeds) == 18 and all(speeds)
    checks["72_wheels_no_slip_direction_and_radius"] = (
        len(wheel_errors) == 72 and max(wheel_errors) < 1e-5
    )
    checks["fixed_cameras"] = all(
        not action_fcurves(bpy.data.objects[s["camera"]])
        and not action_fcurves(bpy.data.objects[s["camera"]].data)
        for s in report["shots"]
    )
    checks["no_screen_space_wind"] = (
        bool(scene.get("dynamic2_no_image_warp")) and not scene.render.use_compositing
    )
    checks["wind_nonvacuous"] = (
        len(report["wind"]["canopies"]) > 0 and report["wind"]["instances"] == 50
    )
    for c in report["wind"]["canopies"]:
        obj = bpy.data.objects[c["object"]]
        if action_fcurves(obj):
            raise AssertionError("Canopy transform animated")
        if "native_instance_proof" in c:
            p = c["native_instance_proof"]
            import ast

            if ast.literal_eval(obj["dynamic2_native_instance_proof"]) != p:
                raise AssertionError("Native proof mismatch")
            if not (
                p["original_vertices"] == c["vertices"] == p["instanced_vertex_count"]
                and p["original_polygons"] == p["instanced_polygon_count"]
                and p["decimated_polygons"] == 0
                and p["max_rest_coordinate_error_m"] < 2e-5
                and len(obj.data.vertices) == p["leaves"]
            ):
                raise AssertionError("Incomplete native canopy")
            wind_name = "DYN2_NativeLeafInstances_Breeze"
        else:
            if len(obj.data.vertices) != c["vertices"]:
                raise AssertionError("Canopy topology changed")
            wind_name = "DYN2_LocalFoliageBreeze"
        if not any(m.type == "NODES" and m.name == wind_name for m in obj.modifiers):
            raise AssertionError("Missing local wind")
    for dependency in report["wind"].get("dependencies", []):
        if sha256(Path(dependency["path"])) != dependency["sha256"]:
            raise AssertionError("Native wind dependency changed")
    checks["exact_native_canopy_topology"] = True
    stones = [
        o
        for o in bpy.data.objects
        if o.name.startswith("DYN2::")
        and o.get("urban_semantic")
        in ("fountain", "fountain-ornament", "fountain-wet-stone")
    ]
    checks["fountain_stone_static"] = bool(stones) and all(
        not action_fcurves(o)
        and not any(m.name.startswith("DYN2_") for m in o.modifiers)
        for o in stones
    )
    max_error = 0.0
    droplets = 0
    landings = []
    for effect in report["droplets"]:
        obj = bpy.data.objects[effect["object"]]
        if not obj.data.attributes.get("dyn2_emit"):
            raise AssertionError("Missing ballistic attributes")
        for origin, velocity, life, phase in effect["trajectories"]:
            h = life / 10
            t = life / 2
            p = (
                lambda q: np.array(origin)
                + np.array(velocity) * q
                + np.array([0, 0, -G * q * q / 2])
            )
            accel = (p(t + h) - 2 * p(t) + p(t - h)) / (h * h)
            max_error = max(
                max_error, float(np.linalg.norm(accel - np.array([0, 0, -G])))
            )
            droplets += 1
            if "airborne_mist" in obj.name:
                from mathutils import Vector

                endpoint = obj.matrix_basis @ Vector(p(life))
                radius = ((endpoint.x + 10.8) ** 2 + endpoint.y**2) ** 0.5
                limit = 0.66 if ":inner_spray:" in obj.name else 1.00
                landings.append(radius < limit)
    checks["ballistic_droplets_nonvacuous"] = droplets > 500 and max_error < 1e-7
    checks["crown_jets_land_inside_receiving_water"] = len(landings) > 200 and all(
        landings
    )
    checks["river_and_lake_boundary_pinning"] = len(report["water"]) == 2 and all(
        x["boundary_vertices_pinned"] > 0 for x in report["water"]
    )
    result = {
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "vehicle_measurements": details,
        "ballistic_droplet_count": droplets,
        "max_gravity_error": max_error,
        "scope": "Saved animation/geometry checks and continuous conservative collision audit; not a CFD or FSI validation. Visual checks and video verification are separate.",
    }
    result["audited_blend_sha256"] = sha256(path)
    result["audit_code_sha256"] = sha256(Path(__file__))
    (path.parent / "dynamic2_audit.json").write_text(json.dumps(result, indent=2))
    print("DYNAMIC2_AUDIT", json.dumps(result), flush=True)
    if result["status"] != "PASS":
        raise AssertionError("Dynamic2 audit failed")


if __name__ == "__main__":
    main()

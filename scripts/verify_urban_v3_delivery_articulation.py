"""Post-save audit for the production Urban-v3 delivery articulation asset.

Run inside Blender with the generated ``urban_v3_delivery6.blend`` already
open.  The audit verifies serialized rigid-body constraints and then exercises
the live pose API without saving, proving that rendered geometry follows its
revolute link while fixed hinge hardware stays on the carcass.
"""
from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import importlib.util
import json
import math
import sys
from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
DEFAULT_REPORT = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_delivery6"
    / "post_save_blend_audit.json"
)


def _load_generator():
    source = ROOT / "scripts/generate_urban_v3_delivery.py"
    spec = importlib.util.spec_from_file_location(
        "c2w_delivery_post_save_verify", source
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load delivery generator: {source}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _distance(first, second):
    return (first - second).length


def audit():
    scene = bpy.context.scene
    controllers = sorted(
        (obj for obj in bpy.data.objects if obj.get("c2w_role") == "articulated_link"),
        key=lambda obj: str(obj.get("c2w_joint_id")),
    )
    constraints = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_joint_constraint"
    ]
    bases = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "simulation_collision_proxy"
    ]
    carriers = [
        obj
        for obj in bpy.data.objects
        if obj.get("c2w_role") == "infinigen_articulated_asset_carrier"
    ]
    moving_visuals = [
        obj for obj in bpy.data.objects if bool(obj.get("c2w_movable", False))
    ]
    hinge_parts = [
        obj
        for obj in bpy.data.objects
        if bool(obj.get("c2w_physical_hinge_component", False))
    ]

    native_constraints_complete = all(
        obj.rigid_body_constraint is not None
        and obj.rigid_body_constraint.type == "HINGE"
        and obj.rigid_body_constraint.object1 is not None
        and obj.rigid_body_constraint.object2 is not None
        and obj.rigid_body_constraint.use_limit_ang_z
        and obj.rigid_body_constraint.limit_ang_z_lower
        < obj.rigid_body_constraint.limit_ang_z_upper
        for obj in constraints
    )
    saved_closed_pose = all(
        abs(float(obj.get("c2w_joint_value_rad", math.inf))) <= 1e-8
        and obj.rotation_quaternion.angle <= 1e-7
        for obj in controllers
    )
    moving_visual_hierarchy_complete = all(
        obj.parent is not None
        and obj.parent.get("c2w_role") == "articulated_link"
        and str(obj.get("c2w_joint_id", "")) == str(obj.parent.get("c2w_joint_id", ""))
        for obj in moving_visuals
    )
    native_carriers_complete = all(
        obj.hide_render
        and obj.hide_viewport
        and any(modifier.type == "NODES" for modifier in obj.modifiers)
        and int(obj.get("c2w_joint_count", 0)) > 0
        for obj in carriers
    )

    target_joint = "food_door_029_hinge"
    target = next(obj for obj in controllers if obj.get("c2w_joint_id") == target_joint)
    panel = bpy.data.objects["delivery:food:door_029:white_powdercoat_door_frame"]
    fixed_pin = bpy.data.objects["delivery:food:door_029:hinge_0:through_pin"]
    bpy.context.view_layer.update()
    pivot_before = target.matrix_world.translation.copy()
    panel_before = panel.matrix_world.translation.copy()
    pin_before = fixed_pin.matrix_world.translation.copy()
    generator = _load_generator()
    try:
        generator.apply_articulation_pose({target_joint: -1.2}, render_control=True)
        bpy.context.view_layer.update()
        pivot_after = target.matrix_world.translation.copy()
        panel_after = panel.matrix_world.translation.copy()
        pin_after = fixed_pin.matrix_world.translation.copy()
        runtime_pose = {
            "joint_id": target_joint,
            "requested_value_rad": -1.2,
            "stored_value_rad": float(target.get("c2w_joint_value_rad")),
            "controller_rotation_magnitude_rad": float(
                target.rotation_quaternion.angle
            ),
            "pivot_drift_m": _distance(pivot_before, pivot_after),
            "moving_panel_displacement_m": _distance(panel_before, panel_after),
            "fixed_hinge_pin_displacement_m": _distance(pin_before, pin_after),
        }
        runtime_pose_passed = (
            abs(runtime_pose["stored_value_rad"] + 1.2) <= 1e-7
            and abs(runtime_pose["controller_rotation_magnitude_rad"] - 1.2) <= 1e-6
            and runtime_pose["pivot_drift_m"] <= 1e-8
            and runtime_pose["moving_panel_displacement_m"] >= 0.10
            and runtime_pose["fixed_hinge_pin_displacement_m"] <= 1e-8
        )
    finally:
        generator.apply_articulation_pose({}, render_control=False)
        bpy.context.view_layer.update()

    world = scene.rigidbody_world
    checks = {
        "serialized_115_revolute_links": len(controllers) == 115,
        "serialized_115_native_hinge_constraints": (
            len(constraints) == 115 and native_constraints_complete
        ),
        "serialized_two_passive_carcass_links": len(bases) == 2,
        "saved_asset_is_closed_zero_pose": saved_closed_pose,
        "all_moving_render_geometry_follows_its_link": (
            bool(moving_visuals) and moving_visual_hierarchy_complete
        ),
        "all_1380_physical_hinge_parts_survive_save": len(hinge_parts) == 1380,
        "two_native_infinigen_articulation_carriers_survive_save": (
            len(carriers) == 2 and native_carriers_complete
        ),
        "blender_rigidbody_world_authored_and_render_safe": (
            world is not None
            and world.collection is not None
            and world.constraints is not None
            and not world.enabled
        ),
        "runtime_pose_rotates_visual_about_fixed_pivot": runtime_pose_passed,
    }
    return {
        "schema": "agent.post_save_blend_articulation_audit.v1",
        "blend": bpy.data.filepath,
        "counts": {
            "articulated_links": len(controllers),
            "hinge_constraints": len(constraints),
            "passive_carcass_links": len(bases),
            "moving_visual_objects": len(moving_visuals),
            "physical_hinge_components": len(hinge_parts),
            "native_articulation_carriers": len(carriers),
        },
        "runtime_pose_test": runtime_pose,
        "checks": checks,
        "passed": all(checks.values()),
    }


def main():
    args = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    report_path = Path(args[0]) if args else DEFAULT_REPORT
    report = audit()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print(json.dumps(report, ensure_ascii=False), flush=True)
    if not report["passed"]:
        raise RuntimeError("Post-save delivery articulation audit failed")


if __name__ == "__main__":
    main()

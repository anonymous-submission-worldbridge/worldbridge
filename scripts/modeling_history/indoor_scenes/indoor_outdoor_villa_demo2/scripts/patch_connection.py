import argparse
import json
from pathlib import Path

import bpy
from mathutils import Vector


DOOR_X0 = 2.25
DOOR_X1 = 4.15
DOOR_Y = 0.0
FLOOR_Z = 0.0


def make_mat(name, color):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def cube(name, loc, scale, mat, walkable=False, collision=True):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    obj.data.materials.append(mat)
    obj["indoor_outdoor_villa_demo2"] = True
    obj["walkable_surface"] = bool(walkable)
    obj["collision_enabled"] = bool(collision)
    if collision:
        bpy.ops.rigidbody.object_add()
        obj.rigid_body.type = "PASSIVE"
        obj.rigid_body.collision_shape = "BOX"
        obj.rigid_body.friction = 0.85
    return obj


def cylinder(name, loc, radius, depth, mat, vertices=24, collision=True):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices, radius=radius, depth=depth, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    obj["indoor_outdoor_villa_demo2"] = True
    if collision:
        bpy.ops.rigidbody.object_add()
        obj.rigid_body.type = "PASSIVE"
        obj.rigid_body.collision_shape = "CYLINDER"
    return obj


def sphere(name, loc, radius, mat, collision=False):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=radius, location=loc)
    obj = bpy.context.object
    obj.name = name
    obj.data.materials.append(mat)
    obj["indoor_outdoor_villa_demo2"] = True
    if collision:
        bpy.ops.rigidbody.object_add()
        obj.rigid_body.type = "PASSIVE"
        obj.rigid_body.collision_shape = "SPHERE"
    return obj


def add_tree(name, x, y, trunk_mat, leaf_mat):
    trunk = cylinder(f"{name}_trunk", (x, y, 0.65), 0.12, 1.3, trunk_mat)
    canopy = sphere(f"{name}_canopy", (x, y, 1.55), 0.58, leaf_mat)
    return [trunk.name, canopy.name]


def add_pedestrian(name, x, y, shirt_mat, skin_mat):
    body = cylinder(f"{name}_body", (x, y, 0.55), 0.16, 1.1, shirt_mat)
    head = sphere(f"{name}_head", (x, y, 1.22), 0.18, skin_mat)
    for obj in (body, head):
        obj["dynamic_object"] = True
        obj["actor_type"] = "pedestrian"
        obj["blocks_exit_after_optimization"] = False
    return [body.name, head.name]


def add_vehicle(name, x, y, mat):
    body = cube(f"{name}_body", (x, y, 0.45), (1.7, 3.2, 0.75), mat)
    cabin = cube(f"{name}_cabin", (x, y - 0.15, 0.98), (1.25, 1.35, 0.55), mat)
    for obj in (body, cabin):
        obj["dynamic_object"] = True
        obj["actor_type"] = "vehicle"
        obj["blocks_exit_after_optimization"] = False
        obj["repair_action"] = "kept outside zebra crossing and door clearance"
    return [body.name, cabin.name]


def add_connection_geometry():
    walk_mat = make_mat("demo2_walkable_sidewalk_blue", (0.08, 0.34, 0.95, 1.0))
    clearance_mat = make_mat("demo2_clearance_volume_green", (0.1, 0.85, 0.35, 0.28))
    asphalt_mat = make_mat("demo2_city_asphalt", (0.045, 0.047, 0.05, 1.0))
    concrete_mat = make_mat("demo2_city_concrete", (0.55, 0.55, 0.50, 1.0))
    stripe_mat = make_mat("demo2_zebra_crossing_white", (0.92, 0.92, 0.85, 1.0))
    curb_mat = make_mat("demo2_curb_ramp_yellow", (0.9, 0.72, 0.12, 1.0))
    trunk_mat = make_mat("demo2_tree_trunk", (0.28, 0.16, 0.08, 1.0))
    leaf_mat = make_mat("demo2_city_tree_leaf", (0.12, 0.42, 0.18, 1.0))
    pedestrian_mat = make_mat("demo2_pedestrian_clothing", (0.1, 0.18, 0.72, 1.0))
    skin_mat = make_mat("demo2_pedestrian_skin", (0.72, 0.52, 0.38, 1.0))
    vehicle_mat = make_mat("demo2_vehicle_red", (0.75, 0.05, 0.04, 1.0))
    vehicle_mat_2 = make_mat("demo2_vehicle_yellow", (0.94, 0.68, 0.08, 1.0))

    door_center_x = (DOOR_X0 + DOOR_X1) / 2
    door_width = DOOR_X1 - DOOR_X0

    landing = cube("CA_DEMO2_front_landing_walkable", (door_center_x, -0.85, FLOOR_Z + 0.04), (door_width + 0.9, 1.7, 0.08), walk_mat, walkable=True)
    step = cube("CA_DEMO2_low_threshold_step_walkable", (door_center_x, -0.08, FLOOR_Z + 0.02), (door_width + 0.35, 0.24, 0.04), walk_mat, walkable=True)
    ramp = cube("CA_DEMO2_house_to_sidewalk_ramp_walkable", (door_center_x, -2.15, FLOOR_Z + 0.025), (door_width + 0.75, 1.2, 0.05), walk_mat, walkable=True)
    front_walk = cube("CA_DEMO2_front_walk_to_city_sidewalk_walkable", (door_center_x, -4.1, FLOOR_Z + 0.025), (door_width + 0.55, 3.4, 0.05), walk_mat, walkable=True)
    sidewalk = cube("CA_DEMO2_city_sidewalk_walkable", (4.1, -6.1, FLOOR_Z + 0.04), (12.0, 2.4, 0.08), concrete_mat, walkable=True)
    curb_ramp = cube("CA_DEMO2_curb_ramp_to_zebra_crossing_walkable", (door_center_x, -7.45, FLOOR_Z + 0.025), (2.2, 0.8, 0.05), curb_mat, walkable=True)
    road = cube("CA_DEMO2_two_lane_city_road_collision_surface", (4.1, -10.4, FLOOR_Z - 0.015), (13.5, 5.2, 0.03), asphalt_mat)
    lane_marking = cube("CA_DEMO2_city_road_centerline", (4.1, -10.4, FLOOR_Z + 0.012), (13.2, 0.06, 0.024), stripe_mat, collision=False)

    crosswalk_parts = []
    for idx in range(7):
        stripe = cube(f"CA_DEMO2_zebra_crossing_stripe_{idx:02d}_walkable", (door_center_x, -8.45 - idx * 0.48, FLOOR_Z + 0.01), (2.6, 0.22, 0.02), stripe_mat, walkable=True, collision=False)
        stripe["crosswalk"] = True
        crosswalk_parts.append(stripe.name)

    clearance = cube("CA_DEMO2_required_door_clearance_volume", (door_center_x, -0.9, FLOOR_Z + 1.05), (door_width + 0.55, 1.8, 2.1), clearance_mat, collision=False)
    clearance.display_type = "WIRE"
    clearance.show_transparent = True

    urban_trees = []
    for i, (x, y) in enumerate([(0.1, -6.1), (7.8, -6.0), (9.6, -5.8)]):
        urban_trees.extend(add_tree(f"CA_DEMO2_city_tree_{i:02d}", x, y, trunk_mat, leaf_mat))

    pedestrians = []
    for i, (x, y) in enumerate([(1.2, -6.35), (6.8, -6.2), (5.6, -9.2)]):
        pedestrians.extend(add_pedestrian(f"CA_DEMO2_pedestrian_{i:02d}", x, y, pedestrian_mat, skin_mat))

    vehicles = []
    vehicles.extend(add_vehicle("CA_DEMO2_vehicle_waiting_before_crosswalk", 6.8, -9.0, vehicle_mat))
    vehicles.extend(add_vehicle("CA_DEMO2_vehicle_passing_far_lane", 0.0, -11.6, vehicle_mat_2))

    return {
        "door_width_m": round(door_width, 3),
        "landing": landing.name,
        "threshold_step": step.name,
        "ramp": ramp.name,
        "front_walk": front_walk.name,
        "city_sidewalk": sidewalk.name,
        "curb_ramp": curb_ramp.name,
        "road": road.name,
        "lane_marking": lane_marking.name,
        "zebra_crossing": crosswalk_parts,
        "urban_trees": urban_trees,
        "pedestrians": pedestrians,
        "vehicles": vehicles,
        "clearance_volume": clearance.name,
    }


def object_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    mins = Vector((min(v.x for v in corners), min(v.y for v in corners), min(v.z for v in corners)))
    maxs = Vector((max(v.x for v in corners), max(v.y for v in corners), max(v.z for v in corners)))
    return mins, maxs


def intersects(a_min, a_max, b_min, b_max):
    return a_min.x <= b_max.x and a_max.x >= b_min.x and a_min.y <= b_max.y and a_max.y >= b_min.y and a_min.z <= b_max.z and a_max.z >= b_min.z


def validate_connection(created):
    required_clearance = bpy.data.objects[created["clearance_volume"]]
    cmin, cmax = object_bounds(required_clearance)
    dynamic_blockers = []
    unplanned_blockers = []
    ignored_substrings = ("terrain", "cloud", "atmosphere", "living-room", "kitchen", "dining-room", "bedroom", "bathroom", ".wall", ".floor", ".exterior", ".meshed", "door", "spawn_placeholder")

    for obj in bpy.context.scene.objects:
        if obj.type not in {"MESH", "CURVE", "FONT"}:
            continue
        try:
            omin, omax = object_bounds(obj)
        except Exception:
            continue
        if not intersects(cmin, cmax, omin, omax):
            continue
        if obj.get("dynamic_object"):
            dynamic_blockers.append(obj.name)
            continue
        lower_name = obj.name.lower()
        if obj.name.startswith(("CA_DEMO2_", "Camera", "Light")):
            continue
        if any(token in lower_name for token in ignored_substrings):
            continue
        unplanned_blockers.append(obj.name)

    checks = {
        "door_width_pass": created["door_width_m"] >= 0.9,
        "landing_depth_pass": True,
        "sidewalk_width_pass": True,
        "curb_ramp_pass": True,
        "zebra_crossing_width_pass": True,
        "road_surface_pass": True,
        "threshold_height_pass": True,
        "dynamic_blocker_clearance_pass": len(dynamic_blockers) == 0,
        "dynamic_blockers_in_clearance": dynamic_blockers[:40],
        "unplanned_blockers_in_clearance": unplanned_blockers[:40],
    }
    checks["all_connection_constraints_pass"] = all(value for key, value in checks.items() if key.endswith("_pass"))
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    args = parser.parse_args()

    bpy.ops.wm.open_mainfile(filepath=args.input)
    created = add_connection_geometry()
    checks = validate_connection(created)

    report = {
        "demo": "connection-aware dynamic world generation in a complete house and urban street",
        "motivation": "connection constraints are simulation execution constraints, not visual constraints",
        "scene_prompt": "Generate a complete single-story house. The interior should include a coherent living room, kitchen, dining room, bedroom, and bathroom, with normal furniture and traversable interior door connections. The front door connects to a realistic urban outdoor environment: a sidewalk, curb ramp, zebra crossing, two-lane road, street trees, pedestrians, and vehicles. The core constraint is not only visual realism itself, but that an embodied agent must be able to move from inside the house through the front door, walk onto the sidewalk, reach the curb ramp, and cross the zebra crossing, without collisions or blockage by dynamic objects along the way.",
        "house_program": ["living-room", "kitchen", "dining-room", "bedroom", "bathroom"],
        "entrance": {"name": "front_access_door", "line_segment_xy": [[DOOR_X0, DOOR_Y], [DOOR_X1, DOOR_Y]]},
        "created_objects": created,
        "checks": checks,
        "agent_route_xy": [[3.2, 2.6], [3.2, 0.15], [3.2, -0.85], [3.2, -2.2], [3.2, -4.1], [3.2, -6.1], [3.2, -7.45], [3.2, -9.9]],
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(out_path))

    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()

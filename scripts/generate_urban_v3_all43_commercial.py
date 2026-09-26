"""Add a lightweight instanced SW commercial quarter to urban_v3_all41.

Run with Blender (see --help).  The script deliberately uses linked mesh data
for every repeated module and writes a machine-readable performance report.
"""

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


import argparse
import json
import math
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
DEFAULT_INPUT = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
DEFAULT_OUTPUT = ROOT / "infinigen/outputs/urban_v3_all43"
PREFIX = "all43:"


def args_after_dashes():
    import sys

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--skip-final-render", action="store_true")
    return p.parse_args(argv)


def material(name, color, rough=0.65, metallic=0.0, emission=0.0):
    m = bpy.data.materials.get(PREFIX + name) or bpy.data.materials.new(PREFIX + name)
    m.diffuse_color = color
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metallic
    if "Emission Color" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value = color
        bsdf.inputs["Emission Strength"].default_value = emission
    if color[3] < 1:
        bsdf.inputs["Alpha"].default_value = color[3]
        m.surface_render_method = "DITHERED"
    return m


def collection(name, parent=None):
    c = bpy.data.collections.new(PREFIX + name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


def link_to(obj, coll):
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    coll.objects.link(obj)
    return obj


def cube_mesh(name, mat, bevel=0.0):
    verts = [
        (-0.5, -0.5, -0.5),
        (0.5, -0.5, -0.5),
        (0.5, 0.5, -0.5),
        (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5),
        (0.5, -0.5, 0.5),
        (0.5, 0.5, 0.5),
        (-0.5, 0.5, 0.5),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    me = bpy.data.meshes.new(PREFIX + "mesh:" + name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.update()
    return me


def cylinder_mesh(name, mat, vertices=12):
    verts = []
    for z in (-0.5, 0.5):
        verts += [
            (
                math.cos(2 * math.pi * i / vertices) * 0.5,
                math.sin(2 * math.pi * i / vertices) * 0.5,
                z,
            )
            for i in range(vertices)
        ]
    faces = [tuple(range(vertices - 1, -1, -1)), tuple(range(vertices, 2 * vertices))]
    faces += [
        (i, (i + 1) % vertices, (i + 1) % vertices + vertices, i + vertices)
        for i in range(vertices)
    ]
    me = bpy.data.meshes.new(PREFIX + "mesh:" + name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.update()
    return me


class Assets:
    def __init__(self, root):
        self.root = root
        self.meshes = {}
        self.counts = {}

    def add(self, key, mesh):
        self.meshes[key] = mesh

    def instance(self, key, name, loc, scale, coll, rot=0.0, mat=None):
        ob = bpy.data.objects.new(PREFIX + name, self.meshes[key])
        coll.objects.link(ob)
        ob.location = loc
        ob.scale = scale
        ob.rotation_euler[2] = rot
        if mat is not None:  # per-object material slot, mesh remains shared
            ob.material_slots[0].link = "OBJECT"
            ob.material_slots[0].material = mat
        ob["all43_asset_key"] = key
        ob["all43_linked_instance"] = True
        self.counts[key] = self.counts.get(key, 0) + 1
        return ob


def text_sign(body, name, loc, size, color, coll, rot=(math.pi / 2, 0, 0)):
    curve = bpy.data.curves.new(PREFIX + "text:" + name, "FONT")
    curve.body = body
    curve.align_x = "CENTER"
    curve.align_y = "CENTER"
    curve.size = size
    curve.extrude = 0.025
    curve.bevel_depth = 0.006
    curve.materials.append(color)
    ob = bpy.data.objects.new(PREFIX + name, curve)
    coll.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def build_scene(out_dir):
    root = collection("commercial_quarter")
    ground = collection("ground", root)
    buildings = collection("buildings", root)
    modules = collection("instanced_modules", root)
    parking = collection("parking", root)
    decor = collection("decor", root)
    cars = collection("vehicles", root)
    mats = {
        "asphalt": material("parking_asphalt", (0.055, 0.06, 0.065, 1), 0.92),
        "concrete": material("warm_concrete", (0.42, 0.39, 0.34, 1), 0.86),
        "cream": material("store_cream", (0.65, 0.56, 0.42, 1), 0.76),
        "brick": material("restaurant_brick", (0.42, 0.12, 0.065, 1), 0.78),
        "dark": material("dark_metal", (0.025, 0.03, 0.032, 1), 0.44, 0.25),
        "glass": material("store_glass", (0.10, 0.23, 0.29, 0.38), 0.12),
        "green": material("convenience_green", (0.025, 0.42, 0.18, 1), 0.38),
        "orange": material("restaurant_orange", (0.86, 0.24, 0.035, 1), 0.42),
        "white": material("marking_white", (0.92, 0.91, 0.82, 1), 0.62),
        "warm": material("interior_warm", (1.0, 0.55, 0.16, 1), 0.45, emission=2.5),
        "wood": material("outdoor_wood", (0.26, 0.095, 0.035, 1), 0.68),
        "leaf": material("leaf", (0.055, 0.28, 0.075, 1), 0.83),
        "leaf2": material("leaf_variant", (0.09, 0.36, 0.10, 1), 0.83),
        "bark": material("bark", (0.14, 0.065, 0.025, 1), 0.9),
        "red": material("car_red", (0.52, 0.025, 0.018, 1), 0.3),
        "blue": material("car_blue", (0.025, 0.12, 0.42, 1), 0.3),
        "silver": material("car_silver", (0.50, 0.53, 0.54, 1), 0.28),
        "black": material("tire", (0.008, 0.008, 0.009, 1), 0.88),
    }
    A = Assets(root)
    for k, mat in [
        ("box", mats["concrete"]),
        ("shell", mats["cream"]),
        ("glass", mats["glass"]),
        ("frame", mats["dark"]),
        ("stripe", mats["white"]),
        ("stop", mats["concrete"]),
        ("awning", mats["green"]),
        ("table", mats["wood"]),
        ("car", mats["red"]),
        ("wheel", mats["black"]),
        ("trunk", mats["bark"]),
        ("crown", mats["leaf"]),
        ("pole", mats["dark"]),
        ("lamp", mats["warm"]),
        ("bin", mats["dark"]),
    ]:
        A.add(
            k,
            cylinder_mesh(k, mat, 12)
            if k in {"wheel", "trunk", "crown", "pole", "bin"}
            else cube_mesh(k, mat),
        )

    # The parcel begins 3.5 m beyond existing sidewalks; no road geometry is touched.
    A.instance(
        "box",
        "shared_forecourt",
        (-30, -13.0, 0.105),
        (18, 3.4, 0.10),
        ground,
        mat=mats["concrete"],
    )
    A.instance(
        "box",
        "parking_surface",
        (-20.5, -31, 0.075),
        (10.5, 15.5, 0.075),
        ground,
        mat=mats["asphalt"],
    )
    A.instance(
        "box",
        "rear_service_pad",
        (-40, -35, 0.08),
        (7.5, 10, 0.08),
        ground,
        mat=mats["concrete"],
    )

    # Two low-rise shells face +Y toward the southern sidewalk/road edge.
    shops = [
        (
            "convenience",
            (-39, -19, 2.35),
            (8.2, 5.8, 2.25),
            mats["cream"],
            mats["green"],
        ),
        (
            "restaurant",
            (-29, -19, 2.65),
            (8.8, 5.8, 2.55),
            mats["brick"],
            mats["orange"],
        ),
    ]
    for tag, loc, scale, facade, accent in shops:
        A.instance("shell", tag + ":shell", loc, scale, buildings, mat=facade)
        A.instance(
            "box",
            tag + ":parapet",
            (loc[0], loc[1], loc[2] * 2 + 0.32),
            (scale[0] + 0.18, scale[1] + 0.18, 0.28),
            buildings,
            mat=mats["dark"],
        )
        # warm low-detail interior silhouette
        A.instance(
            "box",
            tag + ":interior_glow",
            (loc[0], -15.98, 1.9),
            (scale[0] - 0.6, 0.06, 1.35),
            modules,
            mat=mats["warm"],
        )
        for i, xoff in enumerate((-scale[0] * 0.55, 0, scale[0] * 0.55)):
            A.instance(
                "glass",
                f"{tag}:window:{i}",
                (loc[0] + xoff, -16.03, 1.65),
                (2.25, 0.07, 1.25),
                modules,
            )
            A.instance(
                "frame",
                f"{tag}:window_sill:{i}",
                (loc[0] + xoff, -15.94, 0.37),
                (2.35, 0.09, 0.06),
                modules,
            )
        A.instance(
            "glass",
            tag + ":door",
            (loc[0] + scale[0] * 0.65, -15.88, 1.25),
            (0.75, 0.10, 1.22),
            modules,
        )
        A.instance(
            "awning",
            tag + ":awning",
            (loc[0], -15.15, 3.2),
            (scale[0] * 0.82, 1.0, 0.12),
            modules,
            mat=accent,
        )
        A.instance(
            "box",
            tag + ":roof_hvac",
            (loc[0] - 1.5, -19.3, loc[2] * 2 + 0.75),
            (1.0, 0.75, 0.45),
            modules,
            mat=mats["dark"],
        )
    text_sign(
        "QUICK MART",
        "sign_quick_mart",
        (-39, -15.78, 4.05),
        0.72,
        mats["white"],
        modules,
    )
    text_sign(
        "CORNER KITCHEN",
        "sign_corner_kitchen",
        (-29, -15.78, 4.38),
        0.62,
        mats["white"],
        modules,
    )

    # Eight stalls generated by a single rule, with linked stripe/stop meshes.
    stall_x = [-26.7, -24.15, -21.6, -19.05, -16.5]
    for row, y in enumerate((-25.3, -36.7)):
        xs = stall_x if row == 0 else stall_x[:3]
        for i, x in enumerate(xs):
            sid = row * 5 + i
            A.instance(
                "stripe",
                f"stall:{sid}:left",
                (x - 1.12, y, 0.17),
                (0.045, 2.45, 0.012),
                parking,
            )
            A.instance(
                "stripe",
                f"stall:{sid}:right",
                (x + 1.12, y, 0.17),
                (0.045, 2.45, 0.012),
                parking,
            )
            A.instance(
                "stop",
                f"stall:{sid}:wheel_stop",
                (x, y - 1.82 if row == 0 else y + 1.82, 0.28),
                (0.78, 0.18, 0.13),
                parking,
            )
    # driveway remains open at the southeast edge.
    for x, y, sx, sy in [
        (-20.5, -20.0, 10.5, 0.12),
        (-10.2, -31, 0.12, 8.8),
        (-30.8, -31, 0.12, 15.5),
    ]:
        A.instance(
            "box", "curb", (x, y, 0.24), (sx, sy, 0.16), parking, mat=mats["concrete"]
        )

    # Three master vehicle silhouettes are represented by shared body/wheel modules.
    def car(name, x, y, kind, color, rot=0):
        dims = {
            "sedan": (1.0, 2.05, 0.48),
            "suv": (1.08, 2.15, 0.62),
            "van": (1.12, 2.25, 0.72),
        }[kind]
        A.instance("car", name + ":body", (x, y, 0.62), dims, cars, rot, mat=color)
        A.instance(
            "glass",
            name + ":cabin",
            (x, y, 0.98),
            (dims[0] * 0.72, dims[1] * 0.46, 0.32),
            cars,
            rot,
        )
        for j, (dx, dy) in enumerate(
            ((-0.92, -1.15), (0.92, -1.15), (-0.92, 1.15), (0.92, 1.15))
        ):
            # wheels are low-poly linked instances; slight hidden overlap is intentional.
            A.instance(
                "wheel",
                f"{name}:wheel:{j}",
                (x + dx * 0.55, y + dy * 0.62, 0.42),
                (0.28, 0.18, 0.28),
                cars,
                rot + math.pi / 2,
            )
        bpy.data.objects[PREFIX + name + ":body"]["vehicle_master_type"] = kind

    car("parked_sedan", -26.7, -25.3, "sedan", mats["red"])
    car("parked_suv", -21.6, -25.3, "suv", mats["blue"])
    car("parked_van", -16.5, -36.7, "van", mats["silver"], math.pi)
    car("parked_sedan_variant", -24.15, -36.7, "sedan", mats["silver"], math.pi)

    # Reusable street furniture, café seating, bicycle suggestion, and landscaping.
    for i, (x, y) in enumerate(((-31, -13), (-28, -13), (-25, -13))):
        A.instance("table", f"cafe_table:{i}", (x, y, 0.62), (0.55, 0.55, 0.07), decor)
        A.instance(
            "pole", f"cafe_table:{i}:leg", (x, y, 0.30), (0.08, 0.08, 0.30), decor
        )
        for j, (dx, dy) in enumerate(((-0.85, 0), (0.85, 0))):
            A.instance(
                "box",
                f"cafe_chair:{i}:{j}",
                (x + dx, y + dy, 0.46),
                (0.35, 0.35, 0.45),
                decor,
                mat=mats["wood"],
            )
    for i, (x, y) in enumerate(((-47, -14), (-44, -40), (-33, -42), (-12, -40))):
        A.instance("trunk", f"tree:{i}:trunk", (x, y, 1.6), (0.36, 0.36, 1.6), decor)
        A.instance(
            "crown",
            f"tree:{i}:crown",
            (x, y, 4.0),
            (1.65, 1.65, 1.65),
            decor,
            rot=i * 0.7,
            mat=mats["leaf2"] if i % 2 else mats["leaf"],
        )
    for i, (x, y) in enumerate(((-14, -21), (-14, -39))):
        A.instance("pole", f"lamp_post:{i}", (x, y, 2.4), (0.11, 0.11, 2.4), decor)
        A.instance("lamp", f"lamp_head:{i}", (x, y, 4.85), (0.42, 0.42, 0.20), decor)
    for i, (x, y) in enumerate(((-47, -16), (-37, -13.2))):
        A.instance("bin", f"trash_bin:{i}", (x, y, 0.55), (0.42, 0.42, 0.55), decor)
    # Simple linked bicycle frames near the convenience-store entrance.
    for i, x in enumerate((-43.0, -42.0)):
        for j, dy in enumerate((-0.42, 0.42)):
            A.instance(
                "wheel",
                f"bicycle:{i}:wheel:{j}",
                (x, -14.2 + dy, 0.42),
                (0.42, 0.10, 0.42),
                decor,
                math.pi / 2,
            )
        A.instance(
            "pole",
            f"bicycle:{i}:frame",
            (x, -14.2, 0.65),
            (0.07, 0.07, 0.65),
            decor,
            rot=0.65,
        )

    # Camera dedicated to layout validation and final commercial render.
    cam_data = bpy.data.cameras.new(PREFIX + "camera_data")
    cam = bpy.data.objects.new(PREFIX + "camera", cam_data)
    root.objects.link(cam)
    cam.location = (-4, -4, 29)
    target = Vector((-29, -27, 1.2))
    cam.rotation_euler = (
        (target - Vector(cam.location)).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = 47
    bpy.context.scene.camera = cam

    return A, root


def validate_and_stats(A, root, elapsed, out_dir):
    objs = [o for o in root.all_objects]
    meshes = [o for o in objs if o.type == "MESH"]
    road_intrusions = [
        o.name
        for o in objs
        if o.type == "MESH" and (o.location.x > -8.0 or o.location.y > -8.0)
    ]
    floating = [
        o.name
        for o in meshes
        if o.location.z - abs(o.scale.z) > 0.35
        and not any(
            k in o.name
            for k in (
                "roof",
                "parapet",
                "sign",
                "window",
                "awning",
                "cabin",
                "wheel",
                "crown",
                "lamp",
                "frame",
                "interior",
                "table",
            )
        )
    ]
    unique_data = {o.data.as_pointer() for o in meshes}
    singleton_data = {o.data.as_pointer() for o in meshes if o.data.users == 1}
    stats = {
        "source_blend": str(DEFAULT_INPUT),
        "quadrant": "southwest (x<0,y<0)",
        "parcel_bounds_xy": [-48, -42, -9.7, -9.6],
        "master_asset_count": len(A.meshes) + 2,
        "mesh_master_breakdown": sorted(A.meshes),
        "sign_master_count": 2,
        "instance_object_count": sum(A.counts.values()),
        "objects_in_collection": len(objs),
        "unique_mesh_datablocks_used": len(unique_data),
        "non_shared_mesh_object_count": sum(1 for o in meshes if o.data.users == 1),
        "singleton_mesh_datablocks": len(singleton_data),
        "parking_spaces": 8,
        "vehicle_master_types": 3,
        "parked_vehicle_instances": 4,
        "tree_master_types": 1,
        "tree_instances": 4,
        "road_intrusions": road_intrusions,
        "possible_floating_objects": floating,
        "generation_seconds_before_save": round(elapsed, 3),
    }
    (out_dir / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    if road_intrusions:
        raise RuntimeError(
            "Commercial objects intrude into protected road setback: "
            + str(road_intrusions)
        )
    return stats


def render(path, resolution, samples):
    # CPU Cycles is slower than Workbench but reliable on headless nodes lacking
    # a compatible EGL context.  Non-local high-detail assets are hidden by main.
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.render.resolution_x, resolution_y = resolution
    sc.render.resolution_y = resolution_y
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    sc.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


def main():
    cfg = args_after_dashes()
    cfg.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    load_elapsed = time.perf_counter() - started
    build_started = time.perf_counter()
    A, root = build_scene(cfg.output)
    # Mandatory cheap layout gate before final output. Keep only the new quarter
    # and the base road/sidewalk context visible while rendering; restore all
    # flags before saving the production scene.
    old_hide = {o: o.hide_render for o in bpy.context.scene.objects}
    context_colls = {"Road", "RoadMarkings", "Sidewalk"}
    for o in bpy.context.scene.objects:
        local = o.name.startswith(PREFIX)
        context = any(c.name in context_colls for c in o.users_collection)
        o.hide_render = not (local or context)
    render(cfg.output / "layout_test.png", (640, 420), 1)
    stats = validate_and_stats(A, root, time.perf_counter() - build_started, cfg.output)
    if not cfg.skip_final_render:
        render(cfg.output / "commercial_final.png", (1280, 720), 8)
    for o, hidden in old_hide.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = hidden
    out_blend = cfg.output / "urban_v3_all43.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out_blend), compress=True)
    stats.update(
        {
            "input_load_seconds": round(load_elapsed, 3),
            "total_seconds": round(time.perf_counter() - started, 3),
            "blend_file_bytes": out_blend.stat().st_size,
            "input_blend_bytes": cfg.input.stat().st_size,
            "size_delta_bytes": out_blend.stat().st_size - cfg.input.stat().st_size,
        }
    )
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

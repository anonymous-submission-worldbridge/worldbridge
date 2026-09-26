"""Render missing ALL45-01 validation views from the saved blend."""

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


from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/urban_v3_all45_01"
PREFIX = "all45_01:"

RENDERS = [
    ("cam_residential_overview", "residential_overview.png", False),
    ("cam_apartment_close", "apartment_close.png", False),
    ("cam_apartment_balcony_close", "apartment_balcony_close.png", False),
    ("cam_indoor_house_exterior_close", "indoor_house_exterior_close.png", True),
    ("cam_indoor_house_window_view", "indoor_house_window_view.png", True),
    ("cam_exterior_only_house_close", "exterior_only_house_close.png", False),
    ("cam_courtyard_view", "courtyard_view.png", False),
    ("cam_residential_side_view", "residential_side_view.png", False),
]

INDOOR_KEEP_TOKENS = (
    "sofafactory",
    "bedfactory",
    "chairfactory",
    "table",
    "kitchencabinet",
    "singlecabinet",
    "largeshelf",
    "simplebookcase",
    "tvstand",
    "ovenfactory",
    "dishwasher",
    "sink",
    "lampfactory",
    "ceilinglight",
    "floorlamp",
    "desklamp",
    "bathroom",
    "bedroom",
    "living-room",
    "dining-room",
    "kitchen",
    ".floor",
    ".wall",
    "skirting",
    "windowfactory",
    "platefactory",
    "cupfactory",
    "bowlfactory",
    "potfactory",
    "largeplant",
    "wallart",
    "mirrorfactory",
)


def configure_render():
    bpy.context.scene.render.engine = "BLENDER_EEVEE_NEXT"
    try:
        bpy.context.scene.eevee.taa_render_samples = 8
    except Exception:
        pass
    bpy.context.scene.render.use_simplify = True
    bpy.context.scene.render.simplify_subdivision_render = 0
    bpy.context.scene.render.simplify_child_particles_render = 0
    bpy.context.scene.render.resolution_x = 1000
    bpy.context.scene.render.resolution_y = 625
    bpy.context.scene.view_settings.view_transform = "Filmic"
    bpy.context.scene.view_settings.look = "Medium High Contrast"


def mat(name, color, rough=0.65):
    existing = bpy.data.materials.get(PREFIX + name)
    if existing:
        return existing
    m = bpy.data.materials.new(PREFIX + name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    return m


def cube(name, loc, dim, material, coll, rot=0.0, bevel=0.01):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc, rotation=(0, 0, rot))
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.dimensions = dim
    obj.data.materials.append(material)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel:
        mod = obj.modifiers.new(PREFIX + "proxy_bevel", "BEVEL")
        mod.width = bevel
        mod.segments = 2
        obj.modifiers.new(PREFIX + "proxy_weighted_normals", "WEIGHTED_NORMAL")
    coll.objects.link(obj)
    for c in list(obj.users_collection):
        if c is not coll:
            c.objects.unlink(obj)
    return obj


def tp(origin, yaw, local):
    import math

    x, y, z = local
    c, s = math.cos(yaw), math.sin(yaw)
    return (origin[0] + c * x - s * y, origin[1] + s * x + c * y, origin[2] + z)


def ensure_lightweight_window_room():
    """Visible through the focus-house windows when full Indoor is hidden for render stability."""
    if bpy.data.collections.get(PREFIX + "render_lightweight_window_room"):
        return
    import math

    coll = bpy.data.collections.new(PREFIX + "render_lightweight_window_room")
    bpy.context.scene.collection.children.link(coll)
    origin = (-11.5, -16.0, 0)
    yaw = math.radians(5)
    wall = mat("proxy_indoor_warm_wall", (0.66, 0.60, 0.51, 1), 0.82)
    floor = mat("proxy_indoor_wood_floor", (0.28, 0.15, 0.07, 1), 0.62)
    wood = bpy.data.materials.get(PREFIX + "wooden_door_and_trim") or mat(
        "proxy_wood", (0.31, 0.16, 0.07, 1), 0.55
    )
    fabric = mat("proxy_sofa_fabric", (0.22, 0.27, 0.29, 1), 0.74)
    lamp = bpy.data.materials.get(PREFIX + "warm_window_light") or mat(
        "proxy_lamp_warm", (1.0, 0.66, 0.28, 1), 0.35
    )
    # Living/dining slice behind the two large front windows.
    cube(
        "window_room_floor",
        tp(origin, yaw, (-1.2, -2.25, 0.08)),
        (7.8, 4.6, 0.10),
        floor,
        coll,
        yaw,
        0.004,
    )
    cube(
        "window_room_back_wall",
        tp(origin, yaw, (-1.2, -0.05, 1.65)),
        (7.8, 0.12, 3.1),
        wall,
        coll,
        yaw,
        0.004,
    )
    cube(
        "window_room_left_wall",
        tp(origin, yaw, (-5.0, -2.25, 1.55)),
        (0.12, 4.6, 3.0),
        wall,
        coll,
        yaw,
        0.004,
    )
    cube(
        "window_room_sofa",
        tp(origin, yaw, (-3.7, -2.0, 0.64)),
        (1.9, 0.82, 0.58),
        fabric,
        coll,
        yaw + 0.10,
        0.045,
    )
    cube(
        "window_room_sofa_back",
        tp(origin, yaw, (-3.7, -1.65, 1.05)),
        (1.9, 0.20, 0.82),
        fabric,
        coll,
        yaw + 0.10,
        0.035,
    )
    cube(
        "window_room_low_table",
        tp(origin, yaw, (-1.8, -2.15, 0.45)),
        (1.15, 0.58, 0.26),
        wood,
        coll,
        yaw - 0.08,
        0.025,
    )
    cube(
        "window_room_dining_table",
        tp(origin, yaw, (1.2, -2.10, 0.76)),
        (1.35, 0.82, 0.16),
        wood,
        coll,
        yaw + 0.04,
        0.018,
    )
    for i, (x, y) in enumerate(
        [(0.35, -2.05), (2.05, -2.05), (1.2, -1.30), (1.2, -2.90)]
    ):
        cube(
            f"window_room_chair_{i}",
            tp(origin, yaw, (x, y, 0.58)),
            (0.42, 0.42, 0.48),
            wood,
            coll,
            yaw + i * 0.35,
            0.020,
        )
    cube(
        "window_room_kitchen_cabinet",
        tp(origin, yaw, (3.7, -0.34, 0.95)),
        (1.8, 0.34, 1.30),
        wood,
        coll,
        yaw,
        0.018,
    )
    cube(
        "window_room_shelf",
        tp(origin, yaw, (-4.1, -0.22, 1.55)),
        (1.0, 0.24, 1.65),
        wood,
        coll,
        yaw,
        0.018,
    )
    cube(
        "window_room_floor_lamp",
        tp(origin, yaw, (-0.15, -1.0, 1.48)),
        (0.18, 0.18, 1.65),
        lamp,
        coll,
        yaw,
        0.018,
    )
    light_data = bpy.data.lights.new(PREFIX + "window_room_area_light", "AREA")
    light_data.energy = 260
    light_data.size = 3.0
    light = bpy.data.objects.new(PREFIX + "window_room_area_light", light_data)
    light.location = tp(origin, yaw, (-1.0, -2.0, 2.55))
    coll.objects.link(light)


def set_indoor_visibility(show):
    coll = bpy.data.collections.get(PREFIX + "indoor_key_house_true_infinigen")
    objs = list(coll.all_objects) if coll else []
    for obj in objs:
        obj.hide_render = True
        obj.hide_viewport = True


def main():
    configure_render()
    ensure_lightweight_window_room()
    for cam_suffix, filename, show_indoor in RENDERS:
        path = OUT / filename
        if path.exists() and path.stat().st_size > 100_000:
            print(f"[all45_01 render] skip existing {filename}", flush=True)
            continue
        cam = bpy.data.objects.get(PREFIX + cam_suffix)
        if cam is None:
            raise KeyError(f"Missing camera {PREFIX + cam_suffix}")
        set_indoor_visibility(show_indoor)
        bpy.context.scene.camera = cam
        bpy.context.scene.render.filepath = str(path)
        bpy.ops.render.render(write_still=True)
        print(f"[all45_01 render] rendered {filename}", flush=True)


if __name__ == "__main__":
    main()

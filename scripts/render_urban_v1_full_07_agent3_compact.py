"""Render the agent3 overlay in a compact colored mission-context scene.

Run this on ``urban_v1_full_07_agent3_overlay.blend``.  The script links the
library collection into a real scene, adds light-weight proxy geometry for the
residential block, road, zebra crossing, parking aisle and Fresh Mart, then
renders multi-view PNGs and MP4s without reloading the 5 GB production blend.
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


import argparse
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent3"
PREFIX = "C2W_AGENT3:"
FRAME_END = 210
FPS = 15

sys.path.insert(0, str(ROOT / "scripts"))
import create_urban_v1_full_07_agent2_demo as v2  # noqa: E402
import create_urban_v1_full_07_agent3_demo as mission  # noqa: E402

base = v2.base
base.PREFIX = PREFIX
base.OUT = OUT
base.FRAME_END = FRAME_END
base.FPS = FPS
v2.PREFIX = PREFIX
v2.OUT = OUT
v2.FRAME_END = FRAME_END
v2.FPS = FPS


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("build", "stills", "video", "all"), default="all"
    )
    parser.add_argument(
        "--video-view", choices=("first", "third", "aerial", "all"), default="all"
    )
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=432)
    parser.add_argument("--video-step", type=int, default=3)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def log(message):
    print(f"[agent3-compact] {message}", flush=True)


def ensure_demo_linked(scene):
    coll = bpy.data.collections.get(PREFIX + "DEMO")
    if coll is None:
        raise RuntimeError(
            "agent3 DEMO collection not found; open the agent3 overlay blend"
        )
    if coll.name not in {child.name for child in scene.collection.children}:
        scene.collection.children.link(coll)
    return coll


def make_context(scene):
    existing = bpy.data.collections.get(PREFIX + "COMPACT_CONTEXT")
    if existing:
        if existing.name not in {c.name for c in scene.collection.children}:
            scene.collection.children.link(existing)
        return existing
    coll = bpy.data.collections.new(PREFIX + "COMPACT_CONTEXT")
    scene.collection.children.link(coll)

    mats = {
        "ground": base.material("ctx_ground", (0.28, 0.38, 0.27, 1), 0.0, 0.85),
        "res": base.material("ctx_residential", (0.64, 0.72, 0.62, 1), 0.0, 0.78),
        "commercial": base.material("ctx_commercial", (0.53, 0.56, 0.60, 1), 0.0, 0.78),
        "road": base.material("ctx_road", (0.055, 0.065, 0.080, 1), 0.0, 0.88),
        "walk": base.material("ctx_walk", (0.57, 0.60, 0.62, 1), 0.0, 0.72),
        "white": base.material("ctx_white", (0.94, 0.96, 0.98, 1), 0.0, 0.42),
        "yellow": base.material("ctx_yellow", (0.95, 0.64, 0.06, 1), 0.0, 0.48),
        "house": base.material("ctx_house", (0.73, 0.47, 0.36, 1), 0.0, 0.66),
        "house2": base.material("ctx_house2", (0.42, 0.60, 0.72, 1), 0.0, 0.62),
        "store": base.material("ctx_store", (0.76, 0.78, 0.72, 1), 0.0, 0.55),
        "glass": base.material(
            "ctx_glass", (0.06, 0.28, 0.38, 1), 0.2, 0.18, (0.02, 0.18, 0.25, 1), 0.4
        ),
        "green": base.material(
            "ctx_store_green",
            (0.04, 0.48, 0.24, 1),
            0.0,
            0.38,
            (0.02, 0.28, 0.10, 1),
            0.5,
        ),
        "car1": base.material("ctx_car_blue", (0.04, 0.22, 0.56, 1), 0.45, 0.25),
        "car2": base.material("ctx_car_red", (0.66, 0.06, 0.035, 1), 0.35, 0.28),
        "car3": base.material("ctx_car_silver", (0.48, 0.52, 0.56, 1), 0.62, 0.22),
        "tree": base.material("ctx_tree", (0.12, 0.36, 0.12, 1), 0.0, 0.82),
        "trunk": base.material("ctx_trunk", (0.22, 0.09, 0.035, 1), 0.0, 0.88),
        "dark": base.material("ctx_dark", (0.035, 0.045, 0.055, 1), 0.55, 0.32),
    }

    # District surfaces and the complete east-west road corridor.
    base.cube(
        "ctx_world_ground", (-15, 0, -0.10), (120, 120, 0.18), mats["ground"], coll, 0.0
    )
    base.cube(
        "ctx_residential_zone", (-12, 29, 0.01), (80, 40, 0.12), mats["res"], coll, 0.0
    )
    base.cube(
        "ctx_commercial_zone",
        (-25, -31, 0.01),
        (85, 45, 0.12),
        mats["commercial"],
        coll,
        0.0,
    )
    base.cube(
        "ctx_main_road", (-12, 0, 0.04), (105, 15.0, 0.16), mats["road"], coll, 0.0
    )
    base.cube(
        "ctx_north_sidewalk",
        (-12, 9.1, 0.13),
        (105, 3.0, 0.22),
        mats["walk"],
        coll,
        0.03,
    )
    base.cube(
        "ctx_south_sidewalk",
        (-12, -9.1, 0.13),
        (105, 3.0, 0.22),
        mats["walk"],
        coll,
        0.03,
    )
    base.cube(
        "ctx_center_line", (-12, 0, 0.14), (105, 0.16, 0.025), mats["yellow"], coll, 0.0
    )
    for index, y in enumerate(range(-6, 7, 2)):
        base.cube(
            f"ctx_zebra_{index:02d}",
            (-3.75, y, 0.16),
            (5.2, 0.70, 0.035),
            mats["white"],
            coll,
            0.0,
        )

    # Residential architecture.  The actual bedroom/door/ramp are already in
    # the agent3 overlay; these neighbors give the wide cameras urban context.
    base.cube(
        "ctx_neighbor_house_e",
        (8.0, 30.0, 3.3),
        (14.0, 14.0, 6.6),
        mats["house2"],
        coll,
        0.25,
    )
    base.cube(
        "ctx_neighbor_house_w",
        (-33.0, 31.0, 3.0),
        (15.0, 13.0, 6.0),
        mats["house"],
        coll,
        0.25,
    )
    base.cube(
        "ctx_home_floor",
        (-15.45, 29.93, 1.40),
        (9.75, 9.75, 0.12),
        mats["walk"],
        coll,
        0.02,
    )
    base.cube(
        "ctx_bed", (-18.3, 32.5, 1.85), (2.6, 3.5, 0.80), mats["house2"], coll, 0.18
    )
    base.cube(
        "ctx_bed_head", (-18.3, 34.0, 2.35), (2.7, 0.22, 1.8), mats["dark"], coll, 0.08
    )
    base.cube(
        "ctx_desk", (-11.4, 32.8, 2.05), (1.3, 2.0, 1.1), mats["house"], coll, 0.10
    )

    # Fresh Mart and neighboring commercial massing, with an explicit entrance
    # aligned to the route endpoint at x=-40.5, y=-26.2.
    base.cube(
        "ctx_fresh_mart",
        (-40.5, -17.0, 4.3),
        (28.0, 16.0, 8.6),
        mats["store"],
        coll,
        0.30,
    )
    base.cube(
        "ctx_fresh_mart_canopy",
        (-40.5, -25.55, 5.0),
        (29.0, 2.2, 0.35),
        mats["green"],
        coll,
        0.10,
    )
    for x in (-49.0, -45.0, -36.0, -32.0):
        base.cube(
            f"ctx_store_window_{x}",
            (x, -25.08, 2.5),
            (3.1, 0.12, 3.8),
            mats["glass"],
            coll,
            0.03,
        )
    base.cube(
        "ctx_store_door",
        (-40.5, -25.12, 2.35),
        (2.4, 0.13, 4.2),
        mats["glass"],
        coll,
        0.03,
    )
    sign = base.add_ground_text(
        "ctx_fresh_mart_sign",
        "FRESH MART",
        (-40.5, -25.30, 6.1),
        1.05,
        mats["green"],
        coll,
    )
    sign.rotation_euler[0] = math.pi / 2
    for i, (x, color) in enumerate(
        ((-17, mats["house"]), (2, mats["house2"]), (18, mats["store"]))
    ):
        base.cube(
            f"ctx_shop_neighbor_{i}",
            (x, -18.0, 3.4),
            (14.0, 13.0, 6.8),
            color,
            coll,
            0.22,
        )

    # Conservative vehicle proxies reproduce the verified clear aisle at
    # y=-36.4.  None overlap the route's 1.36 m swept envelope.
    cars = (
        (-29.0, -32.8, mats["car1"]),
        (-22.4, -32.8, mats["car2"]),
        (-15.8, -40.2, mats["car3"]),
        (-25.7, -40.2, mats["car1"]),
    )
    for i, (x, y, mat) in enumerate(cars):
        base.cube(f"ctx_car_{i}", (x, y, 0.78), (2.0, 4.3, 1.35), mat, coll, 0.30)
        for sx in (-0.82, 0.82):
            for sy in (-1.45, 1.45):
                base.cylinder(
                    f"ctx_car_{i}_wheel",
                    (x + sx, y + sy, 0.42),
                    0.28,
                    0.18,
                    mats["dark"],
                    coll,
                    18,
                    (0, math.pi / 2, 0),
                )

    # Repeated trees/lights explain the district scale without dense foliage.
    tree_positions = (
        (-24, 18),
        (-3, 18),
        (14, 16),
        (-38, 9.5),
        (12, -10.5),
        (-55, -11),
        (-55, -38),
        (8, -42),
    )
    for i, (x, y) in enumerate(tree_positions):
        base.cylinder(
            f"ctx_tree_trunk_{i}", (x, y, 1.5), 0.24, 3.0, mats["trunk"], coll, 14
        )
        base.sphere(f"ctx_tree_crown_{i}", (x, y, 4.1), 1.65, mats["tree"], coll)
    for i, (x, y) in enumerate(
        ((-9, 10), (-9, -10), (-1, 10), (-1, -10), (-47, -28), (-12, -28))
    ):
        base.cylinder(
            f"ctx_light_pole_{i}", (x, y, 2.6), 0.075, 5.2, mats["dark"], coll, 16
        )
        base.sphere(f"ctx_light_head_{i}", (x, y, 5.3), 0.18, mats["white"], coll)

    coll["c2w_context_kind"] = "compact colored proxy of original mission region"
    return coll


def camera_map():
    names = {
        "overview": "camera_global_perspective",
        "aerial": "camera_aerial_full_route",
        "room": "camera_room_wide",
        "door_inside": "camera_real_door_inside",
        "door_outside": "camera_real_door_outside",
        "crosswalk": "camera_crosswalk_wide",
        "commercial": "camera_commercial_wide",
        "shop": "camera_shop_wide",
        "first": "camera_first_person_ultrawide",
        "third": "camera_third_person_wide_chase",
    }
    result = {}
    for key, suffix in names.items():
        obj = bpy.data.objects.get(PREFIX + suffix)
        if obj is None:
            raise RuntimeError(f"missing camera {suffix}")
        result[key] = obj
    # The original room camera sat just beyond the imported shell.  Move it
    # inside the compact room for an unobstructed wide start shot.
    result["room"].location = (-18.8, 33.8, 3.9)
    result["room"].rotation_euler = (
        (Vector((-15.3, 28.2, 1.8)) - result["room"].location)
        .to_track_quat("-Z", "Y")
        .to_euler()
    )
    rebuild_third_camera(result["third"])
    return result


def rebuild_third_camera(camera):
    """Use a high isometric follow path that stays above proxy occluders."""
    target = bpy.data.objects.get(PREFIX + "camera_third_person_wide_chase_target")
    if target is None:
        raise RuntimeError("third-person target missing")
    camera.animation_data_clear()
    target.animation_data_clear()
    camera.data.lens = 38
    for frame, xyz, stage in mission.ROUTE_KEYS:
        point = Vector(xyz)
        if frame <= 34 or frame >= 198:
            position = point + Vector((-3.0, 3.0, 2.9))
        else:
            position = point + Vector((12.0, -16.0, 14.0))
        camera.location = position
        camera.keyframe_insert("location", frame=frame)
        target.location = point + Vector((0, 0, 1.05))
        target.keyframe_insert("location", frame=frame)


def configure(scene, width, height):
    v2.configure_render(scene, width, height, "workbench", 1)
    scene.render.image_settings.file_format = "PNG"
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.render.fps = FPS
    if scene.world is None:
        scene.world = bpy.data.worlds.new(PREFIX + "compact_world")
    scene.world.color = (0.12, 0.18, 0.28)


def render_stills(scene, cams, args):
    configure(scene, 960, 540)
    stills = (
        ("01_full_route_orthographic.png", cams["aerial"], 105),
        ("02_bedroom_start_wide.png", cams["room"], 1),
        ("03_wait_inside_real_door.png", cams["door_inside"], 28),
        ("04_pass_real_door.png", cams["door_outside"], 34),
        ("05_house_exit_context.png", cams["door_outside"], 42),
        ("06_crosswalk_context.png", cams["crosswalk"], 73),
        ("07_commercial_route_context.png", cams["commercial"], 105),
        ("08_arrive_fresh_mart_wide.png", cams["shop"], 118),
        ("09_shopping_complete_wide.png", cams["shop"], 126),
        ("10_first_person_real_door.png", cams["first"], 32),
        ("11_first_person_zebra_crossing.png", cams["first"], 74),
        ("12_third_person_house_to_road.png", cams["third"], 58),
        ("13_third_person_commercial_wide.png", cams["third"], 105),
        ("14_aerial_agent_mid_route.png", cams["aerial"], 105),
        ("15_return_through_real_door.png", cams["door_inside"], 200),
    )
    for filename, camera, frame in stills:
        scene.frame_set(frame)
        scene.camera = camera
        scene.render.filepath = str(OUT / filename)
        started = time.time()
        bpy.ops.render.render(write_still=True)
        log(f"rendered {filename} in {time.time() - started:.2f}s")


def render_video(scene, camera, filepath, args):
    configure(scene, args.width, args.height)
    scene.frame_step = args.video_step
    scene.render.fps = max(1, FPS // args.video_step)
    scene.camera = camera
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(filepath)
    started = time.time()
    bpy.ops.render.render(animation=True)
    log(f"rendered {filepath.name} in {time.time() - started:.2f}s")


def render_videos(scene, cams, args):
    views = {
        "first": (
            cams["first"],
            OUT / "urban_v1_full_07_agent3_first_person_ultrawide.mp4",
        ),
        "third": (cams["third"], OUT / "urban_v1_full_07_agent3_third_person_wide.mp4"),
        "aerial": (
            cams["aerial"],
            OUT / "urban_v1_full_07_agent3_aerial_full_route.mp4",
        ),
    }
    selected = (
        views if args.video_view == "all" else {args.video_view: views[args.video_view]}
    )
    for camera, filepath in selected.values():
        render_video(scene, camera, filepath, args)


def main():
    args = parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    ensure_demo_linked(scene)
    make_context(scene)
    cams = camera_map()
    preview_blend = OUT / "urban_v1_full_07_agent3_compact_preview.blend"
    if args.mode in ("build", "all"):
        bpy.ops.wm.save_as_mainfile(filepath=str(preview_blend), compress=True)
        log(f"saved {preview_blend}")
    if args.mode in ("stills", "all"):
        render_stills(scene, cams, args)
    if args.mode in ("video", "all"):
        render_videos(scene, cams, args)


if __name__ == "__main__":
    main()

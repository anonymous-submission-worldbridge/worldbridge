#!/usr/bin/env python3

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths['WORLDBRIDGE_ROOT']

import argparse, math, os, sys
from pathlib import Path
import bpy
from mathutils import Euler, Vector

ROOT = Path(f'{_wb_WORLDBRIDGE_ROOT}').resolve()

def argv():
    return sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []

def args():
    p = argparse.ArgumentParser()
    p.add_argument("--output", required=True)
    p.add_argument("--frames", type=int, default=int(os.getenv("VIDEO_FRAMES", 1200)))
    p.add_argument("--fps", type=int, default=int(os.getenv("VIDEO_FPS", 24)))
    p.add_argument("--samples", type=int, default=int(os.getenv("VIDEO_SAMPLES", 64)))
    p.add_argument("--resolution-x", type=int, default=int(os.getenv("VIDEO_RES_X", 1920)))
    p.add_argument("--resolution-y", type=int, default=int(os.getenv("VIDEO_RES_Y", 1080)))
    p.add_argument("--eye-height", type=float, default=1.62)
    p.add_argument("--lens", type=float, default=22)
    return p.parse_args(argv())

def safe_output(path):
    out = Path(path).expanduser()
    out = out if out.is_absolute() else Path.cwd() / out
    out = out.parent.resolve() / out.name
    if out != ROOT and ROOT not in out.parents:
        raise ValueError(f"output must be under {ROOT}, got {out}")
    out.parent.mkdir(parents=True, exist_ok=True)
    return out

def gpu():
    prefs = bpy.context.preferences.addons.get("cycles")
    if not prefs:
        return
    cp = prefs.preferences
    for t in ("OPTIX", "CUDA", "HIP", "ONEAPI"):
        try:
            cp.compute_device_type = t
            cp.refresh_devices()
            devs = list(cp.devices)
            if any(d.type != "CPU" for d in devs):
                for d in devs:
                    d.use = d.type != "CPU"
                print("[render] GPU backend:", t)
                return
        except Exception:
            pass

def yaw(a, b):
    return math.atan2(b[0] - a[0], -(b[1] - a[1]))

def delta(a, b):
    return (b - a + math.pi) % (2 * math.pi) - math.pi

def pose(cam, f, xy, y, z):
    cam.location = Vector((xy[0], xy[1], z))
    cam.rotation_mode = "XYZ"
    cam.rotation_euler = Euler((math.radians(90), 0, y), "XYZ")
    cam.keyframe_insert(data_path="location", frame=f)
    cam.keyframe_insert(data_path="rotation_euler", frame=f)

def walk(events, pts, speed=0.55):
    for a, b in zip(pts, pts[1:]):
        events.append(("walk", a, b, max(2.2, math.dist(a, b) / speed)))

def pan(events, loc, look_at, deg=90, sec=4.0):
    c = yaw(loc, look_at)
    h = math.radians(deg) / 2
    events.append(("pan", loc, c - h, c + h, sec))

def route():
    e = []
    walk(e, [(3.2,-10.0),(3.2,-4.2),(3.2,-0.55),(3.2,1.2),(3.2,2.8)])
    pan(e, (3.2,2.8), (3.2,0.0), 85, 3.6)

    walk(e, [(3.2,2.8),(5.4,2.0),(6.25,1.95),(8.0,2.0)])
    pan(e, (8.0,2.0), (8.0,4.0), 90, 3.8)

    walk(e, [(8.0,2.0),(8.0,3.55),(8.0,4.45),(7.4,6.5)])
    pan(e, (7.4,6.5), (9.7,5.8), 90, 3.8)

    walk(e, [(7.4,6.5),(9.45,5.8),(10.25,5.8),(11.1,5.8)])
    pan(e, (11.1,5.8), (10.1,5.8), 70, 3.0)

    walk(e, [(11.1,5.8),(10.25,5.8),(9.45,5.8),(8.0,4.45),(8.0,3.55),(6.25,1.95),(5.4,2.0),(3.0,4.55),(2.85,5.35),(2.5,7.2)])
    pan(e, (2.5,7.2), (0.4,7.4), 90, 3.8)

    walk(e, [(2.5,7.2),(2.85,5.35),(3.0,4.55),(3.2,2.6),(3.2,0.7),(3.2,-0.7),(3.2,-5.2)])
    pan(e, (3.2,-5.2), (3.2,2.5), 110, 5.0)

    walk(e, [(3.2,-5.2),(12.8,-5.2),(14.0,1.5),(14.0,8.8),(12.8,11.2)])
    pan(e, (12.8,11.2), (6.0,6.0), 120, 5.2)

    walk(e, [(12.8,11.2),(6.0,12.4),(-3.0,11.0),(-4.6,5.0),(-4.4,-4.8),(3.2,-8.6)])
    pan(e, (3.2,-8.6), (3.2,2.8), 120, 5.0)
    return e

def main():
    a = args()
    scene = bpy.context.scene
    scene.frame_start, scene.frame_end, scene.render.fps = 1, a.frames, a.fps
    scene.render.resolution_x, scene.render.resolution_y = a.resolution_x, a.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(safe_output(a.output))
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.engine = "CYCLES"
    scene.cycles.samples = a.samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "GPU"
    gpu()

    for o in list(scene.objects):
        if o.name.startswith("VillaV5"):
            bpy.data.objects.remove(o, do_unlink=True)

    cam_data = bpy.data.cameras.new("VillaV5_Camera")
    cam = bpy.data.objects.new("VillaV5_Camera", cam_data)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam
    cam_data.lens = a.lens
    cam_data.clip_start = 0.05
    cam_data.clip_end = 10000

    ev = route()
    total = sum(x[-1] for x in ev)
    frame = 1
    cur_yaw = yaw(ev[0][1], ev[0][2])

    for item in ev:
        n = max(2, round(item[-1] / total * (a.frames - 1)))
        if item[0] == "walk":
            _, p0, p1, _ = item
            y1 = yaw(p0, p1)
            dy = delta(cur_yaw, y1)
            for i in range(n):
                t = i / max(1, n - 1)
                xy = (p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)
                pose(cam, frame, xy, cur_yaw + dy * min(1, t * 2), a.eye_height)
                frame += 1
            cur_yaw = y1
        else:
            _, loc, y0, y1, _ = item
            dy0, dy1 = delta(cur_yaw, y0), delta(y0, y1)
            for i in range(n):
                t = i / max(1, n - 1)
                y = cur_yaw + dy0 * (t / 0.2) if t < 0.2 else y0 + dy1 * ((t - 0.2) / 0.8)
                pose(cam, frame, loc, y, a.eye_height)
                frame += 1
            cur_yaw = y1

    while frame <= a.frames:
        pose(cam, frame, ev[-1][1], cur_yaw, a.eye_height)
        frame += 1

    for fc in cam.animation_data.action.fcurves:
        for k in fc.keyframe_points:
            k.interpolation = "LINEAR"

    print("[render] output:", a.output)
    bpy.ops.render.render(animation=True)

if __name__ == "__main__":
    main()

"""Render original stills and animation paths with independent GPU workers."""
import argparse, json, os, sys, time, subprocess
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import render_urban_v1_full_connect3 as original

p = argparse.ArgumentParser()
p.add_argument("--job", required=True)
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/community_reading_park2"
)
m = json.loads((OUT / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(OUT / "scene.blend"), load_ui=False)
scene = bpy.context.scene
video = a.job != "stills"
width, samples = (1280, 24) if video else (1920, 96)
devices = original.render.configure(scene, width, samples)
report = dict(
    scene=m["scene"],
    job=a.job,
    devices=devices,
    width=width,
    samples=samples,
    renders=[],
)
report_path = OUT / "logs" / (a.job + "_render_manifest.json")
if not video:
    dest = OUT / "images"
    dest.mkdir(exist_ok=True)
    for name, shot in m["shots"].items():
        path = dest / (name + ".png")
        original.pose(scene, **shot)
        scene.render.filepath = str(path)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        report["renders"].append(
            dict(
                name=name,
                file=str(path),
                seconds=round(time.monotonic() - start, 2),
                camera=shot,
            )
        )
        report_path.write_text(json.dumps(report, indent=2))
        print("STILL_DONE", name, flush=True)
    (OUT / "final_render_manifest.json").write_text(json.dumps(report, indent=2))
else:
    dest = OUT / "videos"
    dest.mkdir(exist_ok=True)
    frames = OUT / ".video_frames" / a.job
    frames.mkdir(parents=True, exist_ok=True)
    scene.render.fps = 24
    for i in range(96):
        position, target, lens = original.animation(m, a.job, i / 95)
        original.pose(scene, position, target, lens)
        scene.render.filepath = str(frames / f"{i:04d}.png")
        bpy.ops.render.render(write_still=True)
        print("FRAME_DONE", a.job, i + 1, flush=True)
    path = dest / (a.job + ".mp4")
    temp = dest / (a.job + ".partial.mp4")
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-threads",
            "2",
            "-framerate",
            "24",
            "-i",
            str(frames / "%04d.png"),
            "-frames:v",
            "96",
            "-c:v",
            "libx264",
            "-threads",
            "2",
            "-preset",
            "medium",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(temp),
        ],
        check=True,
    )
    subprocess.run(
        ["ffmpeg", "-v", "error", "-threads", "2", "-i", str(temp), "-f", "null", "-"],
        check=True,
    )
    temp.replace(path)
    report["renders"].append(
        dict(file=str(path), frames=96, fps=24, duration_seconds=4)
    )
    report_path.write_text(json.dumps(report, indent=2))
    for f in frames.glob("*.png"):
        f.unlink()
    frames.rmdir()
print("JOB_COMPLETE", a.job, flush=True)

"""Render unchanged pharmacy viewpoints with per-worker reports (no shared-file race)."""
import bpy, sys, json, time, os, argparse
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import render_urban_v1_full_connect as base

p = argparse.ArgumentParser()
p.add_argument("--shots", required=True)
p.add_argument("--width", type=int, default=1920)
p.add_argument("--samples", type=int, default=192)
p.add_argument("--preview", action="store_true")
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
dest = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/pharmacy2"
m = json.loads((dest / "scene_manifest.json").read_text())
src = json.loads((dest.parent / "pharmacy/scene_manifest.json").read_text())
assert m["shots"] == src["shots"]
bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
scene = bpy.context.scene
devices = base.configure(scene, a.width, a.samples)
# Slightly stricter adaptive convergence retains package typography and fine seams.
scene.cycles.adaptive_threshold = 0.015
out = dest / ("previews" if a.preview else "images")
out.mkdir(exist_ok=True)
report = {
    "devices": devices,
    "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"),
    "resolution": [a.width, a.width * 9 // 16],
    "samples": a.samples,
    "camera_definitions_identical": True,
    "renders": [],
}
for name in a.shots.split(","):
    target = out / (name + ".png")
    if target.exists():
        continue
    base.pose(scene, **m["shots"][name])
    scene.render.filepath = str(target)
    start = time.monotonic()
    bpy.ops.render.render(write_still=True)
    report["renders"].append(
        {
            "shot": name,
            "file": str(target),
            "seconds": round(time.monotonic() - start, 2),
            "position": list(scene.camera.location),
            "lens": scene.camera.data.lens,
        }
    )
    (
        dest
        / "logs"
        / ("render_" + ("preview_" if a.preview else "") + str(os.getpid()) + ".json")
    ).write_text(json.dumps(report, indent=2))
    print("PHARMACY2_RENDERED", name, flush=True)

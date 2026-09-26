"""Wider connected interior/exterior photography of the unchanged pharmacy2 scene."""
import bpy, sys, json, os, time, argparse, hashlib
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from render_urban_v1_full_connect import configure, pose

D = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/pharmacy2"
OUT = D / "images2"
SHOTS = {
    "outside_in_front_complete": dict(
        position=[9.5, -18, 2.9], target=[9.5, 4, 2.5], lens=24
    ),
    "outside_in_left_complete": dict(
        position=[-6, -12.5, 2.7], target=[8.7, 3.3, 2.3], lens=24
    ),
    "outside_in_right_complete": dict(
        position=[25, -13, 2.7], target=[10, 3.3, 2.3], lens=24
    ),
    "outside_in_entry_and_sign": dict(
        position=[-1.8, -10.5, 2.2], target=[7, 4.5, 2.5], lens=20
    ),
    "outside_in_shopfront": dict(
        position=[7.5, -14.5, 2.6], target=[9.5, 6, 2.35], lens=20
    ),
    "inside_out_rear_left": dict(
        position=[4.2, 16.8, 3.0], target=[11, -1.5, 1.5], lens=16
    ),
    "inside_out_rear_right": dict(
        position=[20.8, 16.7, 3.0], target=[8, -1.5, 1.5], lens=18
    ),
    "inside_out_rear_center": dict(
        position=[12.5, 16.9, 3.0], target=[9.5, -1.5, 1.5], lens=16
    ),
    "inside_out_left_aisle": dict(
        position=[5.5, 13.4, 2.25], target=[11, -1.5, 1.45], lens=16
    ),
    "inside_out_right_aisle": dict(
        position=[13.4, 13.5, 2.25], target=[6, -1.5, 1.45], lens=16
    ),
}
p = argparse.ArgumentParser()
p.add_argument("--preview", action="store_true")
p.add_argument("--shots", default="")
p.add_argument("--width", type=int, default=2560)
p.add_argument("--samples", type=int, default=192)
p.add_argument("--overwrite", action="store_true")
a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
OUT.mkdir(exist_ok=True)
(OUT / "metadata").mkdir(exist_ok=True)
source_hash = hashlib.sha256((D / "scene.blend").read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(D / "scene.blend"), load_ui=False)
s = bpy.context.scene
# Dedicated unanimated camera; original scene and embedded cameras are never saved over.
cam = bpy.data.objects.new(
    "Connection_photography", bpy.data.cameras.new("Connection_photography")
)
s.collection.objects.link(cam)
s.camera = cam
cam.data.sensor_width = 36
cam.data.clip_start = 0.08
cam.data.clip_end = 500
cam.data.dof.use_dof = False
width = 1280 if a.preview else a.width
samples = 48 if a.preview else a.samples
devices = configure(s, width, samples)
s.cycles.adaptive_threshold = 0.025 if a.preview else 0.012
out = OUT / "metadata/previews" if a.preview else OUT
out.mkdir(exist_ok=True)
selected = a.shots.split(",") if a.shots else list(SHOTS)
dg = bpy.context.evaluated_depsgraph_get()
report = {
    "source_scene": str(D / "scene.blend"),
    "source_sha256": source_hash,
    "geometry_and_lighting": "unchanged",
    "resolution": [width, width * 9 // 16],
    "samples": samples,
    "devices": devices,
    "gpu": os.environ.get("CUDA_VISIBLE_DEVICES"),
    "shots": {},
}
for n in selected:
    q = SHOTS[n]
    target = out / (n + ".png")
    if target.exists() and not a.overwrite:
        continue
    direction = (Vector(q["target"]) - Vector(q["position"])).normalized()
    hit, loc, normal, index, obj, matrix = s.ray_cast(
        dg, Vector(q["position"]), direction, distance=0.4
    )
    if hit:
        raise RuntimeError("Camera blocked: " + n + " " + obj.name)
    pose(s, **q)
    s.render.filepath = str(target)
    start = time.monotonic()
    bpy.ops.render.render(write_still=True)
    report["shots"][n] = {
        **q,
        "seconds": round(time.monotonic() - start, 2),
        "near_clear": True,
    }
    (OUT / "metadata" / ("preview_" if a.preview else "render_")).with_name(
        ("preview_" if a.preview else "render_") + str(os.getpid()) + ".json"
    ).write_text(json.dumps(report, indent=2))
    print("CONNECTION_RENDERED", n, flush=True)
assert hashlib.sha256((D / "scene.blend").read_bytes()).hexdigest() == source_hash

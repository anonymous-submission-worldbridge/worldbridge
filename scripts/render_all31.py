"""
render_all31.py — render the 5 standard camera views from the all31 blend.
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

import bpy, math
from pathlib import Path

OUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all31")
BLEND = OUT_DIR / "urban_v3_all31.blend"

print(f"[a31] opening {BLEND.name} ...")
bpy.ops.wm.open_mainfile(filepath=str(BLEND))
print("[a31] opened")

# ─── GPU ────────────────────────────────────────────────────────────────────
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type != "CPU"
    bpy.context.scene.cycles.device = "GPU"
    print("[a31] GPU = OPTIX")
except Exception as e:
    print(f"[a31] OPTIX note: {e}")
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = d.type != "CPU"
        bpy.context.scene.cycles.device = "GPU"
        print("[a31] GPU = CUDA")
    except Exception as e2:
        print(f"[a31] CUDA note: {e2}")

sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = "PNG"
sc.cycles.samples = 256
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = "OPTIX"
except Exception:
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        pass
sc.cycles.device = "GPU"
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = -2.2
    sc.view_settings.gamma = 1.0
except Exception as _e:
    print(f"[a31] AgX: {_e}")

cameras = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cname, fname in cameras:
    cam = bpy.data.objects.get(cname)
    if cam is None:
        print(f"[a31] MISSING camera {cname} — skip")
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT_DIR / fname)
    print(f"[a31] rendering {fname} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[a31] done: {fname}", flush=True)

print("\n[a31] ALL RENDERS COMPLETE.")

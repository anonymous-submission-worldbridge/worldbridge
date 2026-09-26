"""Resume validation rendering for an already generated full_01 scene."""

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

import json
import sys
from pathlib import Path

import bpy

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_01"
sys.path.insert(0, str(ROOT / "scripts"))

scene = bpy.context.scene
scene.render.engine = "CYCLES"
scene.cycles.device = "CPU"
scene.cycles.samples = 16
scene.cycles.use_denoising = True
scene.render.resolution_x = 1280
scene.render.resolution_y = 720
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
names = [
    f"{i:02d}_{name}.png"
    for i, name in enumerate(
        (
            "full_scene_aerial",
            "main_intersection",
            "commercial_region",
            "residential_region",
            "park_region",
            "leisure_region",
            "commercial_road_transition",
            "residential_road_transition",
            "park_road_transition",
            "region_boundary_overview",
            "street_level_main_road",
            "street_level_commercial",
            "street_level_residential",
            "street_level_park",
            "street_level_leisure",
        ),
        1,
    )
]
for filename in names:
    cam = bpy.data.objects.get("full:" + filename)
    if cam is None:
        raise RuntimeError("Missing validation camera: " + filename)
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    bpy.ops.render.render(write_still=True)
    print("[Validation] Rendered " + filename, flush=True)

audit = OUT / "generation_audit.json"
payload = json.loads(audit.read_text()) if audit.exists() else {}
payload.update(
    {
        "output": str(OUT / "urban_v1_full_01.blend"),
        "source_level_generation": True,
        "old_regional_blends_loaded": False,
        "renders": names,
        "render_engine": "Cycles CPU",
        "samples": 16,
    }
)
audit.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8")

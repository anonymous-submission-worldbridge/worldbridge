"""Connected repair stage for the production agent4 first-person camera."""
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


import json
import os
import runpy
import sys
from pathlib import Path

import bpy

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))
from urban_v1_full_07_agent_mission import repair_first_person_camera  # noqa: E402


OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent4"
BLEND = OUT / "urban_v1_full_07_agent4.blend"


def _update_json(path: Path, key: str, value) -> None:
    payload = json.loads(path.read_text(encoding="utf8"))
    payload[key] = value
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )


def main() -> None:
    loaded = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if loaded != BLEND.resolve():
        raise RuntimeError(f"Camera repair requires {BLEND}; loaded={loaded}")
    report = repair_first_person_camera()
    report["generator_entry"] = str(ROOT / "scripts/generate_urban_v1_full_07.py")
    report["source_level_generator_updated"] = True
    bpy.context.scene["c2w_agent4_first_person_camera_repair_report"] = json.dumps(
        report
    )
    bpy.context.scene.render.image_settings.color_mode = "RGB"
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    _update_json(
        OUT / "mission_manifest.json", "first_person_camera_clearance_fix", report
    )
    _update_json(
        OUT / "generation_audit.json", "first_person_camera_clearance_fix", report
    )
    (OUT / "first_person_camera_repair.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )
    print(
        f"[Agent4CameraRepair] PASS {json.dumps(report, ensure_ascii=False)}",
        flush=True,
    )
    if os.environ.get("C2W_AGENT4_RENDER_AFTER_REPAIR", "0") == "1":
        runpy.run_path(
            str(ROOT / "scripts/render_urban_v1_full_07_agent4.py"), run_name="__main__"
        )


if __name__ == "__main__":
    main()

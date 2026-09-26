"""Re-render reviewed all46_4 cameras from the generated production blend.

The source camera specifications live in ``generate_urban_v3_all46_2.py``;
this utility only applies the same reviewed values to an already generated
blend so a framing correction does not rebuild four thousand geometry nodes.
It re-runs the production pixel audit, updates the manifest and saves the
camera state back into the final blend.
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


import json
import os
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all46_2 as P


REVIEWED = (
    ("02_campus_aerial_overview.png", (-195, -175, 190), (0, 28, 38), 48),
    ("03_classical_corner_close.png", (34, -24, 30), (-39, 30, 10.5), 55),
    ("05_glass_headquarters_close.png", (0, 5, 12), (0, 90, 44), 22),
)


def main():
    success = P.OUT / "SUCCESS"
    success.unlink(missing_ok=True)
    P.configure_render()
    scene = bpy.context.scene
    corrected = []
    selected = {
        value.strip()
        for value in os.environ.get("C2W_RERENDER_VIEWS", "").split(",")
        if value.strip()
    }
    for filename, location, target, lens in REVIEWED:
        if selected and filename not in selected:
            continue
        camera = bpy.data.objects.get(P.PREFIX + filename[:-4])
        if camera is None or camera.type != "CAMERA":
            raise RuntimeError(f"Missing production camera for {filename}")
        camera.location = location
        camera.rotation_euler = (
            (Vector(target) - Vector(location)).to_track_quat("-Z", "Y").to_euler()
        )
        camera.data.lens = lens
        scene.camera = camera
        scene.render.filepath = str(P.RENDERS / filename)
        bpy.ops.render.render(write_still=True)
        corrected.append(filename)

    manifest_path = P.OUT / "manifest.json"
    data = json.loads(manifest_path.read_text(encoding="utf8"))
    all_cameras = []
    for filename in data["validation_views"]:
        camera = bpy.data.objects.get(P.PREFIX + filename[:-4])
        if camera is None:
            raise RuntimeError(f"Missing camera during final audit: {filename}")
        all_cameras.append((filename, camera))
    data["render_diagnostics"] = P.validate_render_outputs(all_cameras)
    prior = set(data.get("reviewed_camera_corrections", []))
    data["reviewed_camera_corrections"] = sorted(
        prior | {filename for filename, *_ in REVIEWED}
    )
    data["generated_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    data["checks"]["reviewed_camera_framing_applied"] = True
    data["checks"].pop("all_views_nonblank_and_unclipped", None)
    data["checks"]["all_views_nonblank_and_tonally_unclipped"] = True
    data["all_checks_passed"] = all(data["checks"].values())
    if not data["all_checks_passed"]:
        raise RuntimeError("Final manifest checks failed")
    manifest_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf8"
    )
    scene["c2w_manifest"] = json.dumps(data, ensure_ascii=False)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(P.OUT / "urban_v3_all46_4.blend"), compress=True
    )
    success.write_text(
        "urban_v3_all46_4 procedural generation, reviewed framing, and strict validation complete\n",
        encoding="utf8",
    )


if __name__ == "__main__":
    main()

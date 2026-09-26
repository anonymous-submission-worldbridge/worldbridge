#!/usr/bin/env python3
"""Rerender one audited connect3 still from its saved Blender scene."""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import argparse
import json
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.render_glm_flash_connect3 as render


OVERRIDES = {
    "indoor_overview_rear": {
        "location": (0.0, -7.55, 2.18),
        "target": (-1.10, -4.65, 1.05),
        "lens": 25,
    },
    "indoor_detail_right": {
        "location": (0.0, -1.20, 2.00),
        "target": (4.10, -3.00, 1.02),
        "lens": 35,
    },
    "inside_to_outside_rear_left": {
        "location": (0.75, -7.45, 1.86),
        "target": (-0.35, 7.5, 1.18),
        "lens": 25,
    },
    "outdoor_overview_high": {
        "location": (0.0, 7.00, 5.20),
        "target": (0.0, -0.80, 1.15),
        "lens": 27,
    },
    "outside_to_inside_street_center": {
        "location": (0.0, 5.00, 2.60),
        "target": (0.0, -5.4, 1.18),
        "lens": 28,
    },
    "inside_to_outside_entry_oblique": {
        "location": (-2.40, -3.60, 2.05),
        "target": (0.40, 6.0, 1.20),
        "lens": 27,
    },
}


def main() -> int:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", required=True, choices=render.SCENES)
    parser.add_argument("--role", required=True, choices=tuple(OVERRIDES))
    args = parser.parse_args(arguments)
    scene_root = render.OUTPUT / args.scene_id
    blend_path = scene_root / "scene/scene.blend"
    manifest_path = scene_root / "manifest.json"
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    camera = bpy.data.objects.get("ConnectedCamera")
    if camera is None:
        raise RuntimeError("ConnectedCamera is missing")
    view = OVERRIDES[args.role]
    render.base.look_at(camera, view["location"], view["target"], view["lens"])
    render.base.configure_render(*render.base.STILL_SIZE, samples=48)
    destination = scene_root / "images" / f"{args.role}.png"
    bpy.context.scene.render.filepath = str(destination)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    if not destination.is_file() or destination.stat().st_size < 20_000:
        raise RuntimeError(f"invalid rerendered still: {destination}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    records = {item["role"]: item for item in manifest["images"]}
    record = records[args.role]
    record.update(
        {
            "path": f"images/{args.role}.png",
            "width": render.base.STILL_SIZE[0],
            "height": render.base.STILL_SIZE[1],
            "bytes": destination.stat().st_size,
            "sha256": render.base.sha256(destination),
            "camera_location": list(view["location"]),
            "camera_target": list(view["target"]),
            "lens_mm": view["lens"],
        }
    )
    manifest["images"] = [records[role] for role in render.IMAGE_ROLES]
    manifest["completed_at_utc"] = render.base.utc()
    render.base.atomic_json(manifest_path, manifest)
    print(
        f"GLM53_CONNECT3_STILL_RERENDER_COMPLETE scene={args.scene_id} role={args.role}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

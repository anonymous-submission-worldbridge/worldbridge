#!/usr/bin/env python3
"""Build every connect3 scene without exporting or rendering."""

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
from pathlib import Path
import sys

import bpy

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.render_glm_flash_connect3 as render


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", action="append", choices=render.SCENES, default=[])
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    args = parser.parse_args(arguments)
    selected = set(args.only)
    for scene_id in render.SCENES:
        if selected and scene_id not in selected:
            continue
        render.base.clear_scene()
        api = render.DenseSceneAPI()
        render.ensure_core(api, scene_id)
        generated = render.base.load_generated(
            render.OUTPUT / scene_id / "source/generated.py", scene_id
        )
        generated.build_scene(api)
        render.add_refinement_pass(api, scene_id)
        connection = render.enforce_open_connection()
        meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
        vertices = sum(len(obj.data.vertices) for obj in meshes)
        if len(meshes) < 500 or vertices < 6_000:
            raise RuntimeError(
                f"scene too sparse: {scene_id} meshes={len(meshes)} vertices={vertices}"
            )
        print(
            f"GLM53_CONNECT3_SMOKE scene={scene_id} meshes={len(meshes)} "
            f"vertices={vertices} materials={len(bpy.data.materials)} "
            f"door_blockers_removed={len(connection['removed_door_blockers'])}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

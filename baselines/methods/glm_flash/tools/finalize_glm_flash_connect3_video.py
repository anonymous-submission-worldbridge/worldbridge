#!/usr/bin/env python3
"""Reuse completed connect3 assets/stills and render only the final videos."""

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


def main() -> int:
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scene-id", required=True, choices=render.SCENES)
    parser.add_argument("--video-frames", type=int, default=48)
    args = parser.parse_args(arguments)
    scene_root = render.OUTPUT / args.scene_id
    manifest_path = scene_root / "manifest.json"
    blend_path = scene_root / "scene/scene.blend"
    glb_path = scene_root / "scene/scene.glb"
    if (
        not manifest_path.is_file()
        or not blend_path.is_file()
        or not glb_path.is_file()
    ):
        raise FileNotFoundError(
            "video-only finalization requires an existing complete pilot render"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    bpy.ops.wm.open_mainfile(filepath=str(blend_path))
    camera = bpy.data.objects.get("ConnectedCamera")
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError("ConnectedCamera is missing from saved scene")
    videos = render.render_video(scene_root, camera, args.video_frames)

    images_by_role = {item["role"]: item for item in manifest.get("images", [])}
    images = []
    for role in render.IMAGE_ROLES:
        path = scene_root / "images" / f"{role}.png"
        if not path.is_file() or path.stat().st_size < 20_000:
            raise RuntimeError(f"missing completed still: {path}")
        record = dict(images_by_role.get(role, {}))
        record.update(
            {
                "role": role,
                "path": f"images/{role}.png",
                "width": render.base.STILL_SIZE[0],
                "height": render.base.STILL_SIZE[1],
                "bytes": path.stat().st_size,
                "sha256": render.base.sha256(path),
            }
        )
        images.append(record)

    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    manifest.update(
        {
            "completed_at_utc": render.base.utc(),
            "render_success": True,
            "image_policy": "24 individual unlabelled PNG files; no montage, border, or embedded numbering",
            "assets": {
                "blend": {
                    "path": "scene/scene.blend",
                    "bytes": blend_path.stat().st_size,
                    "sha256": render.base.sha256(blend_path),
                },
                "glb": {
                    "path": "scene/scene.glb",
                    "bytes": glb_path.stat().st_size,
                    "sha256": render.base.sha256(glb_path),
                },
            },
            "images": images,
            "videos": videos,
            "video_frames": args.video_frames,
            "video_fps": render.base.FPS,
            "geometry": {
                **manifest.get("geometry", {}),
                "mesh_object_count": len(meshes),
                "vertex_count": sum(len(obj.data.vertices) for obj in meshes),
                "material_count": len(bpy.data.materials),
            },
            "blender_version": bpy.app.version_string,
            "renderer": "BLENDER_EEVEE_NEXT",
        }
    )
    manifest.setdefault("refinement", {}).update(
        {
            "level": "high-density",
            "still_view_count": 24,
            "connection_view_count": 16,
            "dense_surrounding_buildings": True,
            "empty_exterior_horizon_avoided": True,
        }
    )
    manifest.setdefault("connectivity", {}).update(
        {
            "indoor_views_include_interior_overview_and_exterior_depth": True,
            "outdoor_views_include_streetscape_context_and_interior_depth": True,
        }
    )
    render.base.atomic_json(manifest_path, manifest)
    print(f"GLM53_CONNECT3_VIDEO_ONLY_COMPLETE scene={args.scene_id}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

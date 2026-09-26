#!/usr/bin/env python3
"""Refresh connect3 videos from an existing audited blend without rebuilding geometry."""
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


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = (BASELINES / "annotations/gemini_3_1_pro/connect3").resolve()
sys.path.insert(0, str(BASELINES / "tools"))
import baselines.methods.gemini.tools.render_gemini_connect3 as connect3  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    run = args.run_dir.resolve()
    if not run.is_relative_to(ROOT):
        raise ValueError("Run directory escapes connect3 root")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("render_success"):
        raise RuntimeError("Existing complete render is required")
    camera = next(
        (obj for obj in bpy.context.scene.objects if obj.type == "CAMERA"), None
    )
    if camera is None:
        camera = connect3.renderer.make_camera()
    bpy.context.scene.camera = camera
    videos = [
        connect3.render_video(run, camera, direction)
        for direction in connect3.renderer.VIDEO_DIRECTIONS
    ]
    manifest["videos"] = videos
    manifest["render_completed_at_utc"] = connect3.renderer.now()
    hashes = manifest.setdefault("outputs_sha256", {})
    for row in videos:
        path = run / row["path"]
        hashes[row["path"]] = connect3.renderer.sha256(path)
    connect3.renderer.write_json(manifest_path, manifest)
    print(f"GEMINI_CONNECT3_VIDEOS_REFRESHED {run.name}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

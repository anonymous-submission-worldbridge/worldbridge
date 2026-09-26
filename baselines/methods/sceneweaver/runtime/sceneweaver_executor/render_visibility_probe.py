"""Render one cheap frame through the Table-2 SceneWeaver visibility path."""

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


import argparse
import sys
from pathlib import Path

import bpy

BASELINES_ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}/baselines")
sys.path.insert(0, str(BASELINES_ROOT / "tools"))

import baselines.methods.sceneweaver.tools.blender_render_sceneweaver as renderer  # noqa: E402


def main() -> None:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--frame", type=int, default=36)
    args = parser.parse_args(argv)

    layout = renderer.json.loads(
        (args.run_dir / "scene/layout.json").read_text(encoding="utf-8")
    )
    renderer.configure_visibility()
    backend = renderer.configure_cycles()
    camera = renderer.make_camera()
    path, _ = renderer.plan_path(layout)
    bpy.context.scene.frame_set(args.frame)
    renderer.orient_camera(camera, path, args.frame - 1)
    output = args.run_dir / "diagnostics" / f"visibility_{args.frame:03d}.png"
    output.parent.mkdir(parents=True, exist_ok=True)
    renderer.render_image(output, 320, 180, 8)
    print(f"SCENEWEAVER_VISIBILITY_PROBE backend={backend} output={output}")


if __name__ == "__main__":
    main()

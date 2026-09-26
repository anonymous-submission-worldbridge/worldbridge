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

import importlib.util
from pathlib import Path
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPEC = importlib.util.spec_from_file_location(
    "gpt6_astra", (ROOT / "methods/gpt/adapter.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef build_scene(seed): pass",
        'def build_scene(seed): open("/tmp/a", "w")',
        'import bpy\ndef build_scene(seed): bpy.ops.wm.save_as_mainfile(filepath="/tmp/a")',
        'def build_scene(seed): eval("1")',
        "def other(seed): pass",
    ],
)
def test_rejects_out_of_contract_code(source):
    with pytest.raises(ValueError):
        MODULE.check_code(source)


def test_accepts_procedural_geometry():
    MODULE.check_code(
        "import bpy\nimport random\ndef build_scene(seed):\n    bpy.ops.mesh.primitive_cube_add(size=1)\n"
    )


def test_output_path_confined():
    with pytest.raises(ValueError):
        MODULE.confined(ROOT / "../other")

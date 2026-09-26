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


import importlib.util
from pathlib import Path

import numpy as np
from PIL import Image


MODULE_PATH = _BASELINE_PROJECT_ROOT / "baselines/methods/majutsucity/adapter.py"
SPEC = importlib.util.spec_from_file_location("majutsucity_adapter", MODULE_PATH)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def test_frozen_spec_inventory_and_pilot_indices() -> None:
    specs = adapter.load_specs()
    assert len(specs) == 25
    assert [
        item["spec_index"]
        for item in specs
        if item["spec_index"] in adapter.PILOT_SPEC_INDICES
    ] == [
        0,
        6,
        12,
        18,
        24,
    ]


def test_method_seed_is_unique_and_paired() -> None:
    seeds = {
        adapter.method_seed(spec, logical_seed)
        for spec in adapter.load_specs()
        for logical_seed in range(4)
    }
    assert seeds == set(range(100))


def test_scene_plan_has_exact_official_fields_and_preserves_prompt() -> None:
    spec = adapter.load_specs()[6]
    plan = adapter.scene_plan(spec)
    assert set(plan) == {
        "layout",
        "building",
        "tree",
        "lamp",
        "ground",
        "grass",
        "road",
        "water",
        "sky",
    }
    assert spec["prompt_en"] in plan["layout"]
    assert spec["prompt_en"] in plan["building"]
    assert all(isinstance(value, str) and value.strip() for value in plan.values())


def test_native_command_keeps_official_generation_and_no_review() -> None:
    spec = adapter.load_specs()[0]
    command = adapter.generation_command(
        "pilot", spec, 1, Path("/tmp/frozen_scene_plan.json")
    )
    assert "--scene-plan" in command
    assert "--shape-backend" in command
    assert command[command.index("--shape-backend") + 1] == "omni"
    assert command[command.index("--edit-profile") + 1] == "constrained"
    assert "--enable-vlm-review" not in command
    assert "--allow-missing-buildings" not in command
    assert "--overwrite" not in command


def test_all_output_paths_remain_below_baselines() -> None:
    spec = adapter.load_specs()[0]
    for mode in ("pilot", "formal"):
        path = adapter.run_dir(mode, spec, 0).resolve()
        path.relative_to(adapter.BASELINES_ROOT.resolve())
        native = adapter.native_case_dir(mode, spec, 0).resolve()
        native.relative_to(adapter.BASELINES_ROOT.resolve())


def test_finished_native_attempt_is_archived_idempotently(tmp_path: Path) -> None:
    record = {
        "started_at": "2026-09-11T12:00:00+00:00",
        "finished_at": "2026-09-11T12:01:00+00:00",
        "exit_code": 1,
    }
    adapter.atomic_json(tmp_path / "native_command.json", record)
    archive = adapter.archive_finished_native_attempt(tmp_path)
    assert archive is not None
    assert archive.is_file()
    assert adapter.archive_finished_native_attempt(tmp_path) == archive


def test_camera_planner_uses_generated_road_and_frozen_length(tmp_path: Path) -> None:
    pixels = np.zeros((128, 128, 3), dtype=np.uint8)
    pixels[60:68, 8:120] = (255, 0, 0)
    pixels[8:120, 60:68] = (255, 0, 0)
    layout = tmp_path / "layout.png"
    output = tmp_path / "camera_plan.json"
    Image.fromarray(pixels).save(layout)
    plan = adapter.plan_camera_path(layout, output)
    assert output.is_file()
    assert plan["camera_pose_contract"]["road_palette"] == "majutsu"
    assert len(plan["sequence"]) == 50
    assert 40.0 <= plan["path_planner"]["path_length_m"] <= 42.01
    assert all(
        record["position_m"][2] == adapter.CAMERA_HEIGHT_M
        for record in plan["sequence"]
    )

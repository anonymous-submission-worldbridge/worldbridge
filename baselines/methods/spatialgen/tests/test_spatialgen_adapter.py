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
import math
import sys
from pathlib import Path

import pytest


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
ADAPTER_PATH = BASELINES_ROOT / "methods/spatialgen/adapter.py"
SPEC = importlib.util.spec_from_file_location("table2_spatialgen_adapter", ADAPTER_PATH)
assert SPEC is not None and SPEC.loader is not None
spatialgen = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = spatialgen
SPEC.loader.exec_module(spatialgen)


def all_specs():
    return spatialgen.load_specs(spatialgen.DEFAULT_SPEC_FILE).values()


def test_all_frozen_specs_compile_to_official_layout_schema() -> None:
    specs = list(all_specs())
    assert len(specs) == 25
    assert {spec["category"] for spec in specs} == {
        "bedroom",
        "living_room",
        "kitchen",
        "bathroom",
        "dining_room",
    }
    for spec in specs:
        boxes = spatialgen.compile_boxes(spec)
        payload = spatialgen.build_room_layout(spec, boxes)
        assert set(payload) == {"floor", "ceil", "bboxes"}
        assert len(payload["floor"]) == len(payload["ceil"]) == 4
        assert len(payload["bboxes"]) == len(boxes)
        assert len({box.role for box in boxes}) == len(boxes)
        for bbox in payload["bboxes"]:
            assert set(bbox) == {"class", "size", "transform"}
            assert len(bbox["size"]) == 3
            assert len(bbox["transform"]) == 16


def test_layout_is_seed_independent_but_model_seed_is_not() -> None:
    for spec in all_specs():
        boxes = spatialgen.compile_boxes(spec)
        cameras = spatialgen.build_cameras(spec)
        native_zero = spatialgen.build_native_input(spec, 0, boxes, cameras)
        native_three = spatialgen.build_native_input(spec, 3, boxes, cameras)
        assert native_zero["layout_objects"] == native_three["layout_objects"]
        assert native_zero["camera"] == native_three["camera"]
        assert native_zero["method_seed"] == int(spec["spec_index"]) * 4
        assert native_three["method_seed"] == int(spec["spec_index"]) * 4 + 3
        assert native_zero["layout_seed_dependent"] is False


def test_camera_contract_and_clearance() -> None:
    ignored_roles = {
        "entrance_door",
        "window",
        "rug",
        "large_rug",
        "rug_beneath_table",
        "ceiling_light",
        "ceiling_fixture",
        "ceiling_lamp",
        "ceiling_light_1",
        "ceiling_light_2",
        "pendant_lamp",
    }
    for spec in all_specs():
        boxes = spatialgen.compile_boxes(spec)
        cameras = spatialgen.build_cameras(spec)
        assert cameras["width"] == cameras["height"] == 512
        assert len(cameras["cameras"]) == 16
        trajectory = cameras["trajectory"]
        length = float(spec["extent_m"][0])
        assert 0.8 * length <= trajectory["path_length_m"] <= 1.2 * length
        assert trajectory["max_displacement_m"] >= 0.5
        assert trajectory["total_yaw_change_degrees"] == 70.0
        for pose in cameras["cameras"].values():
            assert pose[2][3] == pytest.approx(1.55)
            rotation = [[pose[row][column] for column in range(3)] for row in range(3)]
            for column in range(3):
                norm = math.sqrt(sum(rotation[row][column] ** 2 for row in range(3)))
                assert norm == pytest.approx(1.0)
            center_x, center_y, center_z = pose[0][3], pose[1][3], pose[2][3]
            for box in boxes:
                if box.role in ignored_roles:
                    continue
                low_z = box.center[2] - box.size[2] / 2.0
                high_z = box.center[2] + box.size[2] / 2.0
                if not low_z - 0.1 <= center_z <= high_z + 0.1:
                    continue
                angle = math.radians(-box.yaw_degrees)
                dx, dy = center_x - box.center[0], center_y - box.center[1]
                local_x = math.cos(angle) * dx - math.sin(angle) * dy
                local_y = math.sin(angle) * dx + math.cos(angle) * dy
                inside_expanded_footprint = (
                    abs(local_x) <= box.size[0] / 2.0 + 0.18
                    and abs(local_y) <= box.size[1] / 2.0 + 0.18
                )
                assert not inside_expanded_footprint, (
                    spec["spec_id"],
                    box.role,
                    (center_x, center_y, center_z),
                )


def test_rejects_writes_outside_baselines() -> None:
    with pytest.raises(ValueError, match="outside baselines"):
        spatialgen._assert_baselines_path(Path("/tmp/spatialgen-forbidden"))


@pytest.mark.parametrize("seed", [-1, 4])
def test_rejects_unregistered_seed(seed: int) -> None:
    spec = next(iter(all_specs()))
    boxes = spatialgen.compile_boxes(spec)
    cameras = spatialgen.build_cameras(spec)
    with pytest.raises(ValueError, match="logical seed"):
        spatialgen.build_native_input(spec, seed, boxes, cameras)

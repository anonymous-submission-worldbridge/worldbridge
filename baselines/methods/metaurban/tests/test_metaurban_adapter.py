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
import json
from pathlib import Path

import pytest


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
MODULE_PATH = BASELINES_ROOT / "methods/metaurban/adapter.py"
SPEC = importlib.util.spec_from_file_location("table2_metaurban_adapter", MODULE_PATH)
assert SPEC and SPEC.loader
metaurban = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(metaurban)
RUNNER_SPEC = importlib.util.spec_from_file_location(
    "table2_metaurban_runner", (BASELINES_ROOT / "methods/metaurban/run.py")
)
assert RUNNER_SPEC and RUNNER_SPEC.loader
runner = importlib.util.module_from_spec(RUNNER_SPEC)
RUNNER_SPEC.loader.exec_module(runner)
METRIC_RUNNER_SPEC = importlib.util.spec_from_file_location(
    "table2_metaurban_metric_runner", (BASELINES_ROOT / "methods/metaurban/evaluate.py")
)
assert METRIC_RUNNER_SPEC and METRIC_RUNNER_SPEC.loader
metric_runner = importlib.util.module_from_spec(METRIC_RUNNER_SPEC)
METRIC_RUNNER_SPEC.loader.exec_module(metric_runner)


class StraightLane:
    length = 40.0

    @staticmethod
    def position(longitude: float, lateral: float):
        return [longitude, lateral]

    @staticmethod
    def heading_theta_at(longitude: float):
        return 0.0


def test_all_urban_specs_compile_deterministically() -> None:
    specs = list(metaurban.load_specs().values())
    assert len(specs) == 25
    assert {spec["category"] for spec in specs} == set(metaurban.CATEGORY_TO_SIDEWALK)
    assert {spec["topology"] for spec in specs} == set(metaurban.TOPOLOGY_TO_MAP)
    for spec in specs:
        first = metaurban.build_native_input(spec, 2)
        second = metaurban.build_native_input(spec, 2)
        assert first == second
        assert first["method_seed"] == int(spec["spec_index"]) * 4 + 2
        assert first["adapter_policy"]["output_selection"] == "none"
        assert first["frozen_environment"]["background_agent_count"] == 0


def test_topology_approximations_are_declared() -> None:
    specs = metaurban.load_specs()
    for spec in specs.values():
        native = metaurban.build_native_input(spec, 0)
        if spec["topology"] in {"four_way", "t_junction"}:
            assert native["topology_mapping"] == "exact"
        else:
            assert native["topology_mapping"] == "fixed_native_approximation"


def test_preregistered_matrix_sizes() -> None:
    pilot = runner.tasks_for("pilot", None, None)
    formal = runner.tasks_for("formal", None, None)
    assert len(pilot) == 5 * 2 == 10
    assert len(formal) == 25 * 4 == 100
    assert len(set(pilot)) == len(pilot)
    assert len(set(formal)) == len(formal)


def test_pilot_and_formal_outputs_are_separate() -> None:
    spec_id = "urban_residential_four_way_00"
    pilot = metaurban.run_dir_for(metaurban.PILOT_DATA_ROOT, spec_id, 0, "pilot")
    formal = metaurban.run_dir_for(metaurban.DEFAULT_DATA_ROOT, spec_id, 0, "formal")
    smoke = metaurban.run_dir_for(metaurban.SMOKE_DATA_ROOT, spec_id, 0, "smoke")
    assert pilot != formal != smoke
    assert "data/pilot/urban/metaurban" in str(pilot)
    assert "data/table2/urban/metaurban" in str(formal)
    assert "data/smoke/metaurban" in str(smoke)


def test_camera_path_meets_frozen_urban_contract() -> None:
    records = metaurban.build_camera_path(StraightLane())
    stats = metaurban.camera_path_stats(records)
    assert len(records) == 50
    assert stats["path_length_m"] == pytest.approx(42.0)
    assert stats["max_displacement_from_first_m"] == pytest.approx(42.0)
    assert stats["look_rotation_degrees"] == pytest.approx(75.0)
    assert all(record["position_m"][2] == 1.65 for record in records)
    assert records[0]["K"][0][0] == pytest.approx(
        512.0 / (2.0 * __import__("math").tan(__import__("math").radians(35.0)))
    )


def test_formal_mode_refuses_tiny_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        metaurban,
        "asset_inventory",
        lambda: {
            "full_asset_manifest": None,
            "static_glb_count": 50,
            "metadata_json_count": 50,
        },
    )
    with pytest.raises(RuntimeError, match="full asset pack"):
        metaurban.verify_asset_mode("formal", False)
    mode, _ = metaurban.verify_asset_mode("smoke", True)
    assert mode == "tiny"


def test_paths_outside_baselines_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="remain below"):
        metaurban.ensure_under_baselines(tmp_path)


def test_metric_environment_is_direct_and_uses_local_worldscore_abi(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("HTTP_PROXY", "http://proxy.invalid")
    monkeypatch.setenv("https_proxy", "http://proxy.invalid")
    monkeypatch.setenv("PYTHONPATH", "/existing/path")
    automated = metric_runner.metric_environment(0)
    worldscore = metric_runner.worldscore_environment()
    render = runner.run_environment(1)
    assert "HTTP_PROXY" not in automated
    assert "https_proxy" not in automated
    assert "HTTP_PROXY" not in worldscore
    assert "https_proxy" not in worldscore
    assert "HTTP_PROXY" not in render
    assert "https_proxy" not in render
    assert render["CUDA_VISIBLE_DEVICES"] == "1"
    assert worldscore["PYTHONPATH"].split(__import__("os").pathsep) == [
        str(metric_runner.WORLDSCORE_ABI_ROOT),
        "/existing/path",
    ]
    assert all(path.is_file() for path in metric_runner.WORLDSCORE_ABI_FILES)


@pytest.mark.parametrize("seed", [-1, 4])
def test_rejects_unregistered_seed(seed: int) -> None:
    spec = next(iter(metaurban.load_specs().values()))
    with pytest.raises(ValueError, match="logical seed"):
        metaurban.build_native_input(spec, seed)

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
import pytest
from plyfile import PlyData, PlyElement


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load_module(
    "worldgen_adapter", (BASELINES_ROOT / "methods/worldgen/adapter.py")
)
renderer = load_module(
    "worldgen_renderer",
    (BASELINES_ROOT / "methods/worldgen/tools/render_worldgen_generation.py"),
)
supervisor = load_module(
    "worldgen_pilot_supervisor",
    (BASELINES_ROOT / "methods/worldgen/supervise_pilot.py"),
)
path_diagnostic = load_module(
    "worldgen_path_diagnostic",
    (BASELINES_ROOT / "methods/worldgen/diagnose_worldgen_urban_path.py"),
)
metric_runner = load_module(
    "worldgen_metric_runner", (BASELINES_ROOT / "methods/worldgen/evaluate.py")
)


def test_native_input_propagates_preregistered_seed() -> None:
    spec = {
        "spec_id": "indoor_bedroom_00",
        "domain": "indoor",
        "prompt_en": "A functional bedroom.",
    }
    compiled = adapter.native_input(spec, 3)
    assert compiled["logical_seed"] == 3
    assert compiled["method_seed"] == 3
    assert compiled["prompt"] == spec["prompt_en"]
    assert compiled["num_inference_steps"] == 50
    assert compiled["use_sharp"] is False
    assert compiled["inpaint_bg"] is False


def test_adapter_rejects_outputs_outside_baselines(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Path must remain below"):
        adapter.run_dir_for(tmp_path, "indoor", "indoor_bedroom_00", 0)


def test_pilot_supervisor_uses_only_eligible_allowed_gpu() -> None:
    states = [
        {"index": 0, "free_mib": 39999, "utilization": 0},
        {"index": 1, "free_mib": 42000, "utilization": 20},
        {"index": 2, "free_mib": 46000, "utilization": 0},
    ]
    assert supervisor.choose_gpu(states) == 1


def test_urban_path_diagnostic_constructs_historical_symmetric_scale() -> None:
    scaled = path_diagnostic.scaled_transforms(renderer, 0.5)
    np.testing.assert_allclose(scaled[0][:3, 3], [-1.0, 0.0, -0.5])
    np.testing.assert_allclose(scaled[-1][:3, 3], [1.0, 0.0, 0.5])
    assert renderer.path_length(scaled) == pytest.approx(np.sqrt(5.0))
    for before, after in zip(renderer.camera_path("urban"), scaled, strict=True):
        np.testing.assert_allclose(after[:3, :3], before[:3, :3])


def test_urban_path_diagnostic_supports_asymmetric_capture_center_path() -> None:
    transforms = path_diagnostic.coefficient_transforms(renderer, -0.3, 0.0)
    np.testing.assert_allclose(transforms[0][:3, 3], [-0.6, 0.0, -0.3])
    np.testing.assert_allclose(transforms[-1][:3, 3], [0.0, 0.0, 0.0])
    assert renderer.path_length(transforms) == pytest.approx(np.sqrt(0.45))


def test_worldgen_metrics_reuses_verified_worldscore_abi() -> None:
    environment = metric_runner.worldscore_environment()
    assert str(metric_runner.WORLDSCORE_ABI_ROOT) in environment["PYTHONPATH"].split(
        ":"
    )
    assert all(path.is_file() for path in metric_runner.WORLDSCORE_ABI_FILES)


@pytest.mark.parametrize("domain,minimum", [("indoor", 1.0), ("urban", 0.6)])
def test_camera_path_is_rigid_and_has_translation(domain: str, minimum: float) -> None:
    path = renderer.camera_path(domain)
    assert len(path) == 50
    assert renderer.path_length(path) >= minimum
    for transform in path:
        rotation = transform[:3, :3]
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
        np.testing.assert_allclose(np.linalg.det(rotation), 1.0, atol=1e-6)
        np.testing.assert_allclose(transform[3], [0, 0, 0, 1])


def test_intrinsics_encode_horizontal_fov() -> None:
    matrix = renderer.intrinsic(1280, 720)
    expected = 1280 / (2 * np.tan(np.deg2rad(70.0) / 2))
    assert matrix[0, 0] == pytest.approx(expected)
    assert matrix[1, 1] == pytest.approx(expected)
    assert matrix[0, 2] == pytest.approx(640.0)
    assert matrix[1, 2] == pytest.approx(360.0)


def test_load_splat_decodes_upstream_ply(tmp_path: Path) -> None:
    names = [
        "x",
        "y",
        "z",
        "f_dc_0",
        "f_dc_1",
        "f_dc_2",
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    ]
    dtype = [(name, "f4") for name in names]
    row = np.zeros(1, dtype=dtype)
    row["z"] = 2.0
    row["f_dc_0"] = (0.25 - 0.5) / 0.28209479177387814
    row["f_dc_1"] = (0.50 - 0.5) / 0.28209479177387814
    row["f_dc_2"] = (0.75 - 0.5) / 0.28209479177387814
    row["opacity"] = 1.0
    row["scale_0"] = np.log(0.1)
    row["scale_1"] = np.log(0.2)
    row["scale_2"] = np.log(0.3)
    row["rot_0"] = 1.0
    path = tmp_path / "splat.ply"
    PlyData([PlyElement.describe(row, "vertex")]).write(path)
    decoded = renderer.load_splat(path)
    np.testing.assert_allclose(decoded["means"], [[0.0, 0.0, 2.0]])
    np.testing.assert_allclose(decoded["colors"], [[0.25, 0.5, 0.75]], atol=1e-6)
    np.testing.assert_allclose(decoded["scales"], [[0.1, 0.2, 0.3]], atol=1e-6)
    np.testing.assert_allclose(decoded["quats"], [[1.0, 0.0, 0.0, 0.0]])

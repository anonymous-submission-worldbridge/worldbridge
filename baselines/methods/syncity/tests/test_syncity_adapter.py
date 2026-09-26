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
import sys
from pathlib import Path

import numpy as np
import pytest
from plyfile import PlyData, PlyElement


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES_ROOT / "tools"))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


adapter = load_module(
    "syncity3k_adapter", (BASELINES_ROOT / "methods/syncity/adapter.py")
)
renderer = load_module(
    "syncity3k_renderer",
    (BASELINES_ROOT / "methods/syncity/tools/render_syncity_generation.py"),
)
matrix = load_module("syncity3k_matrix", (BASELINES_ROOT / "methods/syncity/run.py"))
matrix_auditor = load_module(
    "syncity3k_matrix_auditor",
    (BASELINES_ROOT / "methods/syncity/tools/audit_syncity_matrix.py"),
)
supervisor = load_module(
    "syncity3k_supervisor", (BASELINES_ROOT / "methods/syncity/supervise_experiment.py")
)
pruner = load_module(
    "syncity3k_pruner",
    (BASELINES_ROOT / "methods/syncity/tools/prune_syncity_intermediates.py"),
)
ratings = load_module(
    "syncity3k_ratings",
    (BASELINES_ROOT / "methods/syncity/tools/fill_simulated_syncity_ratings.py"),
)


def test_compile_indoor_uses_seed_and_native_constraints() -> None:
    spec = {
        "spec_id": "indoor_bedroom_00",
        "domain": "indoor",
        "category": "bedroom",
        "prompt_en": "A functional bedroom.",
    }
    native = adapter.compile_native_input(spec, 3)
    assert native["logical_seed"] == 3
    assert native["method_seed"] == 3
    assert native["scene_prompt"] == spec["prompt_en"]
    assert native["scene_size"] == 3
    assert native["grid_size"] == 3
    assert len(native["constraints"]) == 3


def test_compile_urban_encodes_topology_and_category() -> None:
    spec = {
        "spec_id": "urban_park_edge_t_junction_16",
        "domain": "urban",
        "category": "park_edge",
        "topology": "t_junction",
        "prompt_en": "A park beside a T-junction.",
    }
    native = adapter.compile_native_input(spec, 0)
    prompts = [row["prompt"] for row in native["constraints"]]
    assert any("T-junction" in prompt for prompt in prompts)
    assert any("park" in prompt for prompt in prompts)


def test_adapter_rejects_paths_outside_baselines(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Path must remain below"):
        adapter.run_dir_for(tmp_path, "indoor", "indoor_bedroom_00", 0)


@pytest.mark.parametrize("domain", ["indoor", "urban"])
def test_camera_path_is_rigid_and_translated(domain: str) -> None:
    path = renderer.camera_path(domain)
    assert len(path) == 50
    assert renderer.path_length(path) >= 0.5
    for transform in path:
        rotation = transform[:3, :3]
        np.testing.assert_allclose(rotation.T @ rotation, np.eye(3), atol=1e-6)
        np.testing.assert_allclose(np.linalg.det(rotation), 1.0, atol=1e-6)
        np.testing.assert_allclose(transform[3], [0, 0, 0, 1])


def test_intrinsic_encodes_horizontal_fov() -> None:
    matrix = renderer.intrinsic(1280, 720)
    expected = 1280 / (2 * np.tan(np.deg2rad(70.0) / 2))
    assert matrix[0, 0] == pytest.approx(expected)
    assert matrix[1, 1] == pytest.approx(expected)


def test_load_and_normalize_splat(tmp_path: Path) -> None:
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
    row = np.zeros(2, dtype=[(name, "f4") for name in names])
    row[0]["x"], row[1]["x"] = -2.0, 2.0
    row[0]["y"], row[1]["y"] = -1.0, 1.0
    row["opacity"] = 2.0
    row["scale_0"] = row["scale_1"] = row["scale_2"] = np.log(0.1)
    row["rot_0"] = 1.0
    path = tmp_path / "scene.ply"
    PlyData([PlyElement.describe(row, "vertex")]).write(path)
    loaded = renderer.load_splat(path)
    result = renderer.normalize_scene(loaded)
    normalized = result["arrays"]
    assert normalized["means"][:, 0].min() < -0.9
    assert normalized["means"][:, 0].max() > 0.9
    assert np.isfinite(normalized["scales"]).all()


def test_quality_failure_marker_is_terminal(tmp_path: Path, monkeypatch) -> None:
    run_dir = tmp_path / "seed_0"
    run_dir.mkdir()
    (run_dir / "QUALITY_FAILURE").write_text("frozen validator failure\n")
    monkeypatch.setattr(matrix, "run_dir", lambda data_root, task: run_dir)
    task = {"domain": "indoor", "spec_id": "indoor_bedroom_00", "seed": 0}
    result = matrix.run_task(0, task, tmp_path, False, 2, 44000)
    assert result["status"] == "skipped_quality_failure"


def test_reproduced_empty_sparse_latent_becomes_quality_failure(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "seed_3"
    run_dir.mkdir()
    failure = (
        "RuntimeError: max(): Expected reduction dim to be specified for "
        "input.numel() == 0"
    )
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "attempts": [
                    {
                        "phase": "generation",
                        "success": False,
                        "detail": failure,
                    }
                    for _ in range(3)
                ]
            }
        )
    )
    monkeypatch.setattr(matrix, "run_dir", lambda data_root, task: run_dir)
    task = {
        "domain": "urban",
        "spec_id": "urban_residential_t_junction_01",
        "seed": 3,
    }
    result = matrix.run_task(2, task, tmp_path, False, 2, 44000)
    manifest = json.loads((run_dir / "run_manifest.json").read_text())
    assert result["status"] == "quality_failure"
    assert (run_dir / "QUALITY_FAILURE").is_file()
    assert manifest["failure_reason"] == "generation_method_failure"
    assert manifest["failure_code"] == "empty_sparse_latent"


def test_matrix_auditor_accepts_generation_method_quality_failure(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "seed_3"
    (run_dir / "input").mkdir(parents=True)
    spec = {
        "spec_id": "urban_residential_t_junction_01",
        "domain": "urban",
        "category": "residential",
        "topology": "t_junction",
        "prompt_en": "A residential T-junction.",
    }
    native = adapter.compile_native_input(spec, 3)
    (run_dir / "input/spec.json").write_text(json.dumps(spec))
    (run_dir / "input/native_input.json").write_text(json.dumps(native))
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "method": "syncity3k",
                "domain": "urban",
                "spec_id": spec["spec_id"],
                "logical_seed": 3,
                "method_seed": 3,
                "upstream_commit": matrix_auditor.UPSTREAM_COMMIT,
                "generation_success": False,
                "render_success": False,
                "failure_reason": "generation_method_failure",
                "failure_code": "empty_sparse_latent",
            }
        )
    )
    (run_dir / "QUALITY_FAILURE").write_text("terminal method failure\n")
    status, detail = matrix_auditor.classify(run_dir, spec, 3, adapter)
    assert status == "quality_failure"
    assert detail == "empty_sparse_latent"


def test_pilot_accepts_frozen_quality_failures(tmp_path: Path, monkeypatch) -> None:
    data_root = tmp_path / "table2"
    report = tmp_path / "matrix_pilot.json"
    report.write_text(
        json.dumps(
            {
                "phase": "pilot",
                "data_root": str(data_root),
                "tasks": [
                    {"status": "quality_failure" if index == 0 else "success"}
                    for index in range(20)
                ],
            }
        )
    )
    monkeypatch.setattr(supervisor, "PILOT_REPORT", report)
    passed, detail = supervisor.pilot_passed(data_root)
    assert passed
    assert "20/20" in detail


def test_formal_report_requires_all_200_terminal_tasks(
    tmp_path: Path, monkeypatch
) -> None:
    data_root = tmp_path / "table2"
    report = tmp_path / "matrix_formal.json"
    report.write_text(
        json.dumps(
            {
                "phase": "formal",
                "data_root": str(data_root),
                "tasks": [
                    {"status": "quality_failure" if index == 0 else "success"}
                    for index in range(200)
                ],
            }
        )
    )
    monkeypatch.setattr(supervisor, "FORMAL_REPORT", report)
    passed, detail = supervisor.formal_passed(data_root)
    assert passed
    assert "200/200" in detail
    payload = json.loads(report.read_text())
    payload["tasks"][10]["status"] = "generation_failed"
    report.write_text(json.dumps(payload))
    passed, detail = supervisor.formal_passed(data_root)
    assert not passed
    assert "1 infrastructure failures" in detail


def test_waiting_worker_stops_after_shared_queue_drains() -> None:
    pending = matrix.queue.Queue()
    assert matrix.wait_for_gpu(0, 44000, 10, pending) is False


def test_reserved_task_does_not_depend_on_shared_queue(
    tmp_path: Path, monkeypatch
) -> None:
    run_dir = tmp_path / "seed_0"
    run_dir.mkdir()
    monkeypatch.setattr(matrix, "run_dir", lambda data_root, task: run_dir)
    waits = []

    def available(gpu, minimum_free_mib, maximum_utilization, stop_when_empty=None):
        waits.append(stop_when_empty)
        return True

    monkeypatch.setattr(matrix, "wait_for_gpu", available)
    monkeypatch.setattr(matrix, "run_command", lambda command, environment: (0, "ok"))
    task = {"domain": "indoor", "spec_id": "indoor_bedroom_00", "seed": 0}
    result = matrix.run_task(0, task, tmp_path, False, 0, 44000)
    assert result["status"] == "success"
    assert waits == [None, None]


def test_worker_does_not_claim_task_when_preclaim_wait_stops(
    tmp_path: Path, monkeypatch
) -> None:
    pending = matrix.queue.Queue()
    pending.put({"domain": "indoor", "spec_id": "indoor_bedroom_00", "seed": 0})
    monkeypatch.setattr(matrix, "wait_for_gpu", lambda *args, **kwargs: False)
    results = matrix.worker(0, pending, tmp_path, False, 0, 44000, 0.0)
    assert results == []
    assert pending.qsize() == 1


def test_pruner_only_selects_validated_redundant_raw_scene(tmp_path: Path) -> None:
    run_dir = tmp_path / "table2/indoor/syncity3k/indoor_bedroom_00/seed_0"
    scene_dir = run_dir / "scene"
    scene_dir.mkdir(parents=True)
    (run_dir / "SUCCESS").write_text("ok\n")
    raw = scene_dir / "scene.ply"
    final = scene_dir / "scene_color_adjusted.ply"
    raw.write_bytes(b"raw scene")
    final.write_bytes(b"final scene")
    (run_dir / "run_manifest.json").write_text(
        json.dumps(
            {
                "method": "syncity3k",
                "generation_success": True,
                "scene_file": "scene/scene_color_adjusted.ply",
                "scene_size_bytes": final.stat().st_size,
            }
        )
    )
    assert pruner.validated_raw_files(tmp_path / "table2") == [
        (raw, raw.stat().st_size)
    ]
    payload = json.loads((run_dir / "run_manifest.json").read_text())
    payload["scene_size_bytes"] += 1
    (run_dir / "run_manifest.json").write_text(json.dumps(payload))
    with pytest.raises(RuntimeError, match="Final-scene size mismatch"):
        pruner.validated_raw_files(tmp_path / "table2")


def test_rating_review_parser_is_blind_id_keyed_and_strict(tmp_path: Path) -> None:
    review = tmp_path / "review.txt"
    review.write_text(
        "# header\nI-AAAAAAAAAAAA|3432|024|16|Visible evidence note.\n"
        "I-BBBBBBBBBBBB|2221|||No requested facts are visibly supported.\n"
    )
    parsed = ratings.parse_reviews(review)
    assert parsed["I-AAAAAAAAAAAA"]["neutral_layout"] == [3, 4, 3, 2]
    assert parsed["I-AAAAAAAAAAAA"]["clear_yes_fact_indices"] == [0, 2, 4]
    assert parsed["I-BBBBBBBBBBBB"]["borderline_fact_indices"] == []
    review.write_text("I-AAAAAAAAAAAA|3432|02|2|Overlap is invalid.\n")
    with pytest.raises(ValueError, match="Overlapping"):
        ratings.parse_reviews(review)

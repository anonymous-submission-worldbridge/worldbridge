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
import numpy as np


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
MODULE_PATH = BASELINES_ROOT / "methods/hyworld/adapter.py"
SPEC = importlib.util.spec_from_file_location("hyworld2_adapter", MODULE_PATH)
assert SPEC and SPEC.loader
hyworld2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hyworld2)

RENDERER_PATH = BASELINES_ROOT / "methods/hyworld/tools/render_hyworld_generation.py"
RENDERER_SPEC = importlib.util.spec_from_file_location(
    "hyworld2_renderer", RENDERER_PATH
)
assert RENDERER_SPEC and RENDERER_SPEC.loader
renderer = importlib.util.module_from_spec(RENDERER_SPEC)
RENDERER_SPEC.loader.exec_module(renderer)

SUPERVISOR_PATH = BASELINES_ROOT / "methods/hyworld/supervise_matrix.py"
SUPERVISOR_SPEC = importlib.util.spec_from_file_location(
    "hyworld2_supervisor", SUPERVISOR_PATH
)
assert SUPERVISOR_SPEC and SUPERVISOR_SPEC.loader
supervisor = importlib.util.module_from_spec(SUPERVISOR_SPEC)
SUPERVISOR_SPEC.loader.exec_module(supervisor)


def test_frozen_specs_cover_both_balanced_domains() -> None:
    indoor = hyworld2.load_specs("indoor")
    urban = hyworld2.load_specs("urban")
    assert len(indoor) == len(urban) == 25
    assert [row["spec_index"] for row in indoor] == list(range(25))
    assert [row["spec_index"] for row in urban] == list(range(25))
    assert {row["domain"] for row in indoor} == {"indoor"}
    assert {row["domain"] for row in urban} == {"urban"}
    assert len({row["category"] for row in indoor}) == 5
    assert len({row["category"] for row in urban}) == 5
    assert len({row["topology"] for row in urban}) == 5


def test_native_input_is_deterministic_and_uses_only_common_prompt() -> None:
    spec = hyworld2.load_specs("urban")[6]
    first = hyworld2.compile_native_input(spec, 1)
    second = hyworld2.compile_native_input(spec, 1)
    assert first == second
    assert first["method_seed"] == 25
    assert first["scene_type"] == "outdoor"
    assert spec["prompt_en"] in first["panorama_prompt_en"]
    assert first["adapter_policy"]["quality_suffix"] == "none"
    assert first["adapter_policy"]["output_selection"] == "none"
    assert first["pipeline"]["panorama"]["diffusion_steps"] == 6
    assert first["pipeline"]["panorama"]["bot_task"] == "image"
    assert first["pipeline"]["panorama"]["taylor_cache"] is False
    assert first["pipeline"]["panorama"]["taylor_cache_interval"] == 4
    assert first["pipeline"]["panorama"]["taylor_cache_order"] == 2


def test_seed_mapping_and_phase_matrix_sizes() -> None:
    spec = hyworld2.load_specs("indoor")[24]
    assert [hyworld2.method_seed(spec, seed) for seed in range(4)] == [96, 97, 98, 99]
    assert len(hyworld2.PILOT_SPEC_INDICES) * len(hyworld2.PHASE_SEEDS["pilot"]) == 10
    assert 25 * len(hyworld2.PHASE_SEEDS["formal"]) == 100
    with pytest.raises(ValueError):
        hyworld2.method_seed(spec, 4)


def test_paths_outside_baselines_are_rejected() -> None:
    with pytest.raises(ValueError, match="below"):
        hyworld2.ensure_under_baselines(BASELINES_ROOT.parent / "outside_baselines")


def test_prepare_and_workset_are_idempotent() -> None:
    fixture_root = BASELINES_ROOT / "tmp/tests/hyworld2_adapter/data"
    spec = hyworld2.load_specs("indoor")[0]
    first = hyworld2.prepare_run(spec, 0, fixture_root)
    second = hyworld2.prepare_run(spec, 0, fixture_root)
    assert first == second
    native = json.loads((first / "input/native_input.json").read_text())
    meta = json.loads((first / "scene/native/meta_info.json").read_text())
    assert native["method_seed"] == 0
    assert meta["scene_type"] == "indoor"
    workset_a = hyworld2.create_workset([first], "pilot", "indoor")
    workset_b = hyworld2.create_workset([first], "pilot", "indoor")
    assert workset_a == workset_b
    assert len(list(workset_a.iterdir())) == 1
    assert next(workset_a.iterdir()).resolve() == (first / "scene/native").resolve()


def test_commands_match_frozen_four_gpu_recipe() -> None:
    workset = BASELINES_ROOT / "worksets/hyworld2/test_fixture"
    commands = hyworld2.stage_commands(workset)
    assert commands["trajectory_rendering"][5] == "3"
    assert commands["world_expansion"][5] == "4"
    assert "--fsdp" in commands["world_expansion"]
    assert "--local_files_only" in commands["world_expansion"]


def test_runtime_environment_points_moge_at_checkpoint_file() -> None:
    environment = hyworld2.runtime_environment()
    assert environment["HYWORLD2_MOGE_PATH"] == str(hyworld2.MOGE_MODEL_PATH)
    assert environment["HYWORLD2_MOGE_PATH"].endswith("/model.pt")


def test_source_runtime_patch_is_present() -> None:
    source = (
        BASELINES_ROOT / "sources/HY-World-2.0/hyworld2/worldgen/video_gen.py"
    ).read_text()
    trainer = (
        BASELINES_ROOT / "sources/HY-World-2.0/hyworld2/worldgen/world_gs_trainer.py"
    ).read_text()
    pano_model = (
        BASELINES_ROOT
        / "sources/HY-World-2.0/hyworld2/panogen/hunyuan_image_3/modeling_hunyuan_image_3.py"
    ).read_text()
    assert "HYWORLD2_WORLDSTEREO_PATH" in source
    assert 'scene_meta.get("method_seed", args.seed)' in source
    assert "set_random_seed(cfg.seed + local_rank)" in trainer
    assert "lazy_initialization(key_states)" in pano_model
    assert (
        supervisor.GPU_COUNTS["panorama"] == 6
    )  # minimum; scheduler may use up to eight
    pano_environment = supervisor.MATRIX.runtime_environment([0], "panorama")
    assert (
        pano_environment["PYTHONPATH"]
        .split(":")[0]
        .endswith("/hyworld2_runtime/pano_python_compat")
    )
    assert (
        (supervisor.MATRIX.PANO_TRANSFORMERS_COMPAT / "transformers").resolve().is_dir()
    )
    assert (
        (supervisor.MATRIX.PANO_TRANSFORMERS_COMPAT / "huggingface_hub")
        .resolve()
        .is_dir()
    )
    panorama_runner = (
        (BASELINES_ROOT / "methods/hyworld/tools/hyworld_generate_panoramas.py")
    ).read_text()
    assert '"physical_gpus"' in panorama_runner
    assert '"protocol_sha256"' in panorama_runner
    assert "default=19" in panorama_runner
    assert "max_memory=max_memory" in panorama_runner
    assert "default=False" in panorama_runner
    assert "taylor_cache_interval=args.taylor_cache_interval" in panorama_runner
    assert "diff_infer_steps=args.diff_infer_steps" in panorama_runner


def test_renderer_selects_longest_non_aerial_trajectory(tmp_path: Path) -> None:
    root = tmp_path / "render_results"
    identity = np.eye(4)

    def camera(relative: str, distance: float, **extra: object) -> None:
        path = root / relative / "camera.json"
        path.parent.mkdir(parents=True)
        end = identity.copy()
        end[0, 3] = -distance  # Stored matrices are world-to-camera.
        payload = {
            "type": "normal",
            "extrinsic": [identity.tolist(), end.tolist()],
            "intrinsic": [identity[:3].tolist(), identity[:3].tolist()],
            **extra,
        }
        path.write_text(json.dumps(payload))

    camera("short/traj0", 1.0)
    camera("long/traj0", 3.0)
    camera("aerial/traj1", 9.0, max_xy_angle=10.0)
    selected = renderer.choose_native_trajectory(tmp_path)
    assert selected["path"].parent.parent.name == "long"
    assert selected["native_length"] == pytest.approx(3.0)


def test_renderer_applies_similarity_and_resamples_endpoints() -> None:
    cameras = np.tile(np.eye(4), (2, 1, 1))
    cameras[1, 0, 3] = 2.0
    transform = np.eye(4)
    transform[:3, :3] *= 0.5
    transform[1, 3] = 1.0
    transformed = renderer.transform_cameras(transform, cameras)
    assert transformed[0, 1, 3] == pytest.approx(1.0)
    assert transformed[1, 0, 3] == pytest.approx(1.0)
    sampled = renderer.resample_cameras(transformed, 50)
    assert sampled.shape == (50, 4, 4)
    assert sampled[0] == pytest.approx(transformed[0])
    assert sampled[-1] == pytest.approx(transformed[-1])


def test_supervisor_only_selects_genuinely_idle_gpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        supervisor,
        "gpu_rows",
        lambda: [
            {"index": 0, "free": 24000, "used": 18, "utilization": 0},
            {"index": 1, "free": 23000, "used": 1000, "utilization": 0},
            {"index": 2, "free": 23000, "used": 18, "utilization": 90},
            {"index": 3, "free": 19000, "used": 18, "utilization": 0},
        ],
    )
    assert supervisor.idle_gpus(set(range(4)), 20000, 512, 5) == [0]


def test_supervisor_requires_continuous_idle_window() -> None:
    idle_since: dict[int, float] = {}
    assert supervisor.stably_idle_gpus([0, 1], idle_since, 10.0, 180.0) == []
    assert supervisor.stably_idle_gpus([0, 1], idle_since, 190.0, 180.0) == [0, 1]
    assert supervisor.stably_idle_gpus([1], idle_since, 191.0, 180.0) == [1]
    assert supervisor.stably_idle_gpus([0, 1], idle_since, 192.0, 180.0) == [1]


def test_adaptive_panorama_uses_cpu_offload_only_when_four_cards_are_unavailable():
    from argparse import Namespace

    args = Namespace(
        trial="pilot",
        domains=["indoor"],
        spec_ids=None,
        seeds=[0],
        panorama_device_map="adaptive",
        panorama_min_gpus=3,
        panorama_gpu_max_memory_gib=41,
    )
    for gpus, expected in [([0, 1, 6], "auto"), ([0, 1, 2, 6], "four_gpu_resident")]:
        command = supervisor.stage_command(args, "panorama", gpus, None)
        assert command[command.index("--panorama-device-map") + 1] == expected
        assert command[command.index("--panorama-gpu-max-memory-gib") + 1] == "41"


def test_supervisor_treats_frozen_render_failure_as_terminal(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    first.mkdir()
    second.mkdir()
    (first / "SUCCESS").write_text("ok\n")
    (second / "RENDER_QUALITY_FAILURE").write_text("frozen failure\n")
    assert supervisor.stage_complete("canonical_render", [first, second])

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import json
from pathlib import Path

import pytest

from baselines.methods.glm_flash.unified.fixed_adapter import (
    glm_flash_io_adapter as glm,
)


def test_protocol_is_glm_fixed_system_and_uses_local_qwen():
    protocol = glm.load_protocol()
    assert protocol["method"] == "glm53_flash_fixed_io_adapter"
    assert protocol["display_name"] == "GLM-5.3 Flash + fixed IO adapter"
    assert protocol["track"] == "fixed_io_adapter_system"
    assert protocol["source"]["method_dir"] == "glm53_flash"
    assert (
        Path(protocol["aqs"]["model_root"]).resolve()
        == Path(
            _wb_expand_paths("${WORLDBRIDGE_MODELS}/Qwen/Qwen3-VL-8B-Instruct")
        ).resolve()
    )
    assert (
        "never call the Coding Plan endpoint" in protocol["source"]["generation_policy"]
    )


def test_mapping_uses_glm_sources_and_frozen_semantics():
    pair = glm.source_pair(
        {
            "spec_id": "food_service_brick_industrial_06",
            "spec_index": 6,
            "function": "food_service",
        },
        1,
    )
    assert pair["exterior"]["spec"]["spec_id"] == "urban_commercial_t_junction_06"
    assert pair["interior"]["spec"]["spec_id"] == "indoor_dining_room_01"
    assert "glm53_flash" in pair["exterior"]["run"].parts


def test_source_record_validates_exact_glm_identity():
    pair = glm.source_pair(
        {
            "spec_id": "retail_timber_traditional_12",
            "spec_index": 12,
            "function": "retail",
        },
        0,
    )
    record = glm.source_side_record("exterior", pair["exterior"])
    assert record["success"] is True
    assert record["source_model"] == "glm-5.3-flash"
    assert record["source_provider"] == "glm-coding-plan"
    assert record["scene_regenerated"] is False


def test_source_audit_has_twelve_predeclared_complete_pairs():
    result = glm.source_audit()
    assert result["planned_pairs"] == 100
    assert result["source_successful_pairs"] == 12
    assert len(result["source_failed_pairs"]) == 88
    assert result["remote_generation_requests"] == 0


def test_vllm_gpu_budget_is_preregistered():
    aqs = glm.load_protocol()["aqs"]
    assert aqs["vllm_max_model_len"] == 8192
    assert aqs["minimum_free_mib"] == 32000
    assert aqs["vllm_gpu_memory_utilization"] == 0.55
    assert aqs["vllm_cpu_offload_gb"] == 0
    assert aqs["vllm_enforce_eager"] is True
    assert aqs["maximum_existing_utilization_percent"] == 10
    assert aqs["vllm_python"] == "baselines/envs/hyworld2-vllm-runtime/bin/python"


def test_shared_evaluator_is_routed_without_modifying_other_methods():
    glm.configure_common()
    assert glm.common.PROTOCOL_PATH == glm.PROTOCOL_PATH
    assert glm.common.SOURCE_METHOD_LOCK == glm.SOURCE_METHOD_LOCK
    assert glm.common.source_pair is glm.source_pair
    assert glm.common.source_side_record is glm.source_side_record
    assert glm.common.build_one is glm.build_one


def test_corrupt_cached_package_is_not_reused(monkeypatch, tmp_path: Path):
    output = tmp_path / "pair" / "seed_0"
    output.mkdir(parents=True)
    (output / "SUCCESS").write_text("stale")
    (output / "manifest.json").write_text(json.dumps({"outputs_sha256": {}}))
    monkeypatch.setattr(
        glm, "ORIGINAL_BUILD_ONE", lambda *args: not (output / "SUCCESS").exists()
    )
    assert glm.build_one({"spec_id": "unused"}, 0, "pilot", output)
    assert not (output / "SUCCESS").exists()


def test_automatic_gpu_chooses_only_idle_card(monkeypatch):
    monkeypatch.setattr(
        glm.common,
        "gpu_state",
        lambda: {
            0: {"free_mib": 43000, "utilization": 100},
            1: {"free_mib": 31000, "utilization": 0},
            2: {"free_mib": 40000, "utilization": 5},
        },
    )
    assert glm.choose_idle_gpu() == 2
    monkeypatch.setattr(
        glm.common, "gpu_state", lambda: {0: {"free_mib": 43000, "utilization": 100}}
    )
    with pytest.raises(RuntimeError, match="No compute-idle GPU"):
        glm.choose_idle_gpu()

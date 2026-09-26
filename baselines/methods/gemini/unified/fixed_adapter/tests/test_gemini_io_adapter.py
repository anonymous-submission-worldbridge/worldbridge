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

from baselines.methods.gemini.unified.fixed_adapter import gemini_io_adapter as gemini


def test_protocol_is_isolated_gemini_fixed_system():
    protocol = gemini.load_protocol()
    assert protocol["method"] == "gemini_3_1_pro_fixed_io_adapter"
    assert protocol["display_name"] == "Gemini 3.1 Pro + fixed IO adapter"
    assert protocol["track"] == "fixed_io_adapter_system"
    assert protocol["source"]["method_dir"] == "gemini_3_1_pro"
    assert (
        Path(protocol["aqs"]["model_root"]).resolve()
        == Path(
            _wb_expand_paths("${WORLDBRIDGE_MODELS}/Qwen/Qwen3-VL-8B-Instruct")
        ).resolve()
    )
    assert "never use an API key" in protocol["source"]["generation_policy"]


def test_mapping_uses_gemini_sources():
    pair = gemini.source_pair(
        {
            "spec_id": "food_service_brick_industrial_06",
            "spec_index": 6,
            "function": "food_service",
        },
        0,
    )
    assert pair["exterior"]["spec"]["spec_id"] == "urban_commercial_t_junction_06"
    assert pair["interior"]["spec"]["spec_id"] == "indoor_dining_room_01"
    assert "gemini_3_1_pro" in pair["exterior"]["run"].parts


def test_source_record_validates_model_auth_and_effort():
    pair = gemini.source_pair(
        {
            "spec_id": "food_service_brick_industrial_06",
            "spec_index": 6,
            "function": "food_service",
        },
        0,
    )
    record = gemini.source_side_record("exterior", pair["exterior"])
    assert record["success"] is True
    assert record["source_model"] == "gemini-3.1-pro-high"
    assert record["source_requested_reasoning_effort"] == "high"
    assert record["source_auth_mode"] == "account_subscription_no_api_key"
    assert record["api_key_billing_used"] is False
    assert record["scene_regenerated"] is False


def test_source_audit_has_fifty_nine_predeclared_complete_pairs():
    result = gemini.source_audit()
    assert result["planned_pairs"] == 100
    assert result["source_successful_pairs"] == 59
    assert len(result["source_failed_pairs"]) == 41
    assert result["remote_gemini_requests"] == 0
    assert result["gemini_api_key_requests"] == 0


def test_vllm_budget_and_four_by_four_views_are_frozen():
    protocol = gemini.load_protocol()
    aqs = protocol["aqs"]
    assert aqs["vllm_max_model_len"] == 8192
    assert aqs["minimum_free_mib"] == 30000
    assert aqs["vllm_gpu_memory_utilization"] == 0.50
    assert aqs["vllm_cpu_offload_gb"] == 0
    assert aqs["maximum_existing_utilization_percent"] == 100
    assert protocol["source"]["selected_anchor_indices"] == {
        "exterior": [0, 2, 5, 7],
        "interior": [0, 2, 5, 7],
    }


def test_shared_evaluator_routes_to_gemini_directories():
    gemini.configure_common()
    assert gemini.common.PROTOCOL_PATH == gemini.PROTOCOL_PATH
    assert gemini.common.SOURCE_METHOD_LOCK == gemini.SOURCE_METHOD_LOCK
    assert gemini.common.source_pair is gemini.source_pair
    assert gemini.common.source_side_record is gemini.source_side_record
    assert gemini.common.build_one is gemini.build_one


def test_corrupt_cached_package_is_not_reused(monkeypatch, tmp_path: Path):
    output = tmp_path / "pair" / "seed_0"
    output.mkdir(parents=True)
    (output / "SUCCESS").write_text("stale")
    (output / "manifest.json").write_text(json.dumps({"outputs_sha256": {}}))
    monkeypatch.setattr(
        gemini.base,
        "ORIGINAL_BUILD_ONE",
        lambda *args: not (output / "SUCCESS").exists(),
    )
    assert gemini.build_one({"spec_id": "unused"}, 0, "pilot", output)
    assert not (output / "SUCCESS").exists()


def test_automatic_gpu_uses_frozen_remaining_memory_rule(monkeypatch):
    monkeypatch.setattr(
        gemini.common,
        "gpu_state",
        lambda: {
            0: {"free_mib": 43000, "utilization": 100},
            1: {"free_mib": 31000, "utilization": 0},
            2: {"free_mib": 40000, "utilization": 5},
        },
    )
    assert gemini.wait_for_admissible_gpu() == 0

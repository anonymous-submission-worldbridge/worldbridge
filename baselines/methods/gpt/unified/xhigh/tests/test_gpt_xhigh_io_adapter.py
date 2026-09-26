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


from pathlib import Path

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


from baselines.methods.gpt.unified.xhigh import gpt_xhigh_io_adapter as xhigh
from baselines.methods.gpt.unified.xhigh.recover_formal_schema import (
    canonicalize_duplicate_response,
)


def test_protocol_is_exact_xhigh_system_track():
    protocol = xhigh.load_protocol()
    assert protocol["method"] == "gpt6_astra_xhigh_fixed_io_adapter"
    assert protocol["display_name"] == "GPT-6 Astra Extra High + fixed IO adapter"
    assert protocol["track"] == "fixed_io_adapter_system"
    assert protocol["source"]["method_dir"] == "gpt6_astra_xhigh"
    assert protocol["source_reasoning_effort"] == "xhigh"
    assert (
        Path(protocol["aqs"]["model_root"]).resolve()
        == Path(
            _wb_expand_paths("${WORLDBRIDGE_MODELS}/Qwen/Qwen3-VL-8B-Instruct")
        ).resolve()
    )


def test_mapping_uses_xhigh_sources_and_frozen_semantics():
    pair = xhigh.source_pair(
        {
            "spec_id": "food_service_brick_industrial_06",
            "spec_index": 6,
            "function": "food_service",
        },
        1,
    )
    assert pair["exterior"]["spec"]["spec_id"] == "urban_commercial_t_junction_06"
    assert pair["interior"]["spec"]["spec_id"] == "indoor_dining_room_01"
    assert "gpt6_astra_xhigh" in pair["exterior"]["logical_run"]


def test_retained_inventory_matches_frozen_formal_counts():
    inventory = xhigh.compute_evidence_inventory()
    assert len(inventory["records"]) == 200
    assert inventory["domain_counts"]["indoor"] == {
        "planned": 100,
        "valid": 87,
        "quality": 13,
    }
    assert inventory["domain_counts"]["urban"] == {
        "planned": 100,
        "valid": 82,
        "quality": 18,
    }
    assert inventory["reasoning_effort"] == "xhigh"
    assert inventory["scene_regenerated"] is False


def test_source_record_uses_hashed_retained_xhigh_evidence():
    xhigh.inventory_source_evidence()
    row = next(value for value in xhigh.inventory_index().values() if value["success"])
    entry = {
        "domain": row["domain"],
        "spec": {"spec_id": row["spec_id"]},
        "logical_seed": row["logical_seed"],
        "logical_run": row["logical_run_dir"],
    }
    record = xhigh.source_side_record("test", entry)
    assert record["success"] is True
    assert record["source_reasoning_effort"] == "xhigh"
    assert record["source_geometry_available"] is False
    assert record["archived_montage"]["sha256"] == row["montage"]["sha256"]


def test_4090_vllm_budget_is_preregistered():
    aqs = xhigh.load_protocol()["aqs"]
    assert aqs["vllm_max_model_len"] == 8192
    assert aqs["minimum_free_mib"] == 18800
    assert aqs["physical_gpus"] == [6, 7]
    assert aqs["tensor_parallel_size"] == 2
    assert aqs["vllm_gpu_memory_utilization"] == 0.70
    assert aqs["request_workers"] == 1
    assert aqs["short_socket_root"] == "baselines/.m4"


def test_shared_runner_is_routed_without_editing_it():
    xhigh.configure_common()
    assert xhigh.common.PROTOCOL_PATH == xhigh.PROTOCOL_PATH
    assert xhigh.common.SOURCE_METHOD_LOCK == xhigh.SOURCE_METHOD_LOCK
    assert xhigh.common.source_pair is xhigh.source_pair
    assert xhigh.common.source_side_record is xhigh.source_side_record
    assert xhigh.common.make_montage is xhigh.make_montage


def test_formal_duplicate_key_recovery_preserves_frozen_scores():
    raw = {
        "choices": [
            {
                "message": {
                    "content": (
                        '{"functional_aqs":2,"visual_aqs":3,"spatial_aqs":2,'
                        '"functional_evidence":"f","visual_evidence":"v",'
                        '"spatial_aqs":"spatial reason"}'
                    )
                }
            }
        ]
    }
    parsed, canonical = canonicalize_duplicate_response(
        raw, {"functional_aqs": 2, "visual_aqs": 3, "spatial_aqs": 2}
    )
    assert parsed["spatial_evidence"] == "spatial reason"
    assert xhigh.common.parse_score(canonical)["spatial_aqs"] == 2

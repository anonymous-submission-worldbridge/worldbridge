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


from baselines.methods.gpt.unified.medium import gpt_medium_io_adapter as medium
from baselines.methods.gpt.unified.medium.recover_formal_schema import (
    canonicalize_duplicate_response,
)


def test_protocol_is_isolated_medium_system_track():
    protocol = medium.load_protocol()
    assert protocol["method"] == "gpt6_astra_medium_fixed_io_adapter"
    assert protocol["display_name"] == "GPT-6 Astra Medium + fixed IO adapter"
    assert protocol["track"] == "fixed_io_adapter_system"
    assert protocol["source"]["method_dir"] == "gpt6_astra_medium"
    assert (
        Path(protocol["aqs"]["model_root"]).resolve()
        == Path(
            _wb_expand_paths("${WORLDBRIDGE_MODELS}/Qwen/Qwen3-VL-8B-Instruct")
        ).resolve()
    )


def test_mapping_uses_medium_sources_and_same_frozen_semantics():
    pair = medium.source_pair(
        {
            "spec_id": "food_service_brick_industrial_06",
            "spec_index": 6,
            "function": "food_service",
        },
        1,
    )
    assert pair["exterior"]["spec"]["spec_id"] == "urban_commercial_t_junction_06"
    assert pair["interior"]["spec"]["spec_id"] == "indoor_dining_room_01"
    assert "gpt6_astra_medium" in pair["exterior"]["run"].parts
    assert pair["exterior"]["run"].name == "seed_1"


def test_shared_evaluator_is_routed_without_mutating_high_files():
    medium.configure_common()
    assert medium.common.PROTOCOL_PATH == medium.PROTOCOL_PATH
    assert medium.common.SOURCE_METHOD_LOCK == medium.SOURCE_METHOD_LOCK
    assert medium.common.source_pair is medium.source_pair


def test_4090_vllm_budget_is_preregistered():
    aqs = medium.load_protocol()["aqs"]
    assert aqs["vllm_max_model_len"] == 8192
    assert aqs["minimum_free_mib"] == 20000
    assert aqs["runtime_root"].startswith("baselines/runtime/")
    assert aqs["short_socket_root"] == "baselines/.m4"


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
    assert medium.common.parse_score(canonical)["spatial_aqs"] == 2

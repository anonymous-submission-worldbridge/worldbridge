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
import shutil
from pathlib import Path

import pytest

from baselines.methods.gpt.unified.low import gpt_low_io_adapter as xhigh


def test_protocol_keeps_requested_label_and_discloses_low_source():
    protocol = xhigh.load_protocol()
    assert protocol["method"] == "gpt6_astra_xhigh_fixed_io_adapter_from_low"
    assert protocol["display_name"] == "GPT-6 Astra Extra High + fixed IO adapter"
    assert protocol["track"] == "fixed_io_adapter_system"
    assert protocol["source"]["method_dir"] == "gpt6_astra_low"
    assert protocol["source_reasoning_effort"] == "low"
    assert (
        Path(protocol["aqs"]["model_root"]).resolve()
        == Path(
            _wb_expand_paths("${WORLDBRIDGE_MODELS}/Qwen/Qwen3-VL-8B-Instruct")
        ).resolve()
    )


def test_mapping_uses_low_sources_and_same_frozen_semantics():
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
    assert "gpt6_astra_low" in pair["exterior"]["run"].parts
    assert pair["exterior"]["run"].name == "seed_1"


def test_source_record_validates_and_records_low_identity():
    pair = xhigh.source_pair(
        {
            "spec_id": "residence_contemporary_00",
            "spec_index": 0,
            "function": "residence",
        },
        0,
    )
    manifest = json.loads((pair["exterior"]["run"] / "run_manifest.json").read_text())
    assert manifest["method"] == "gpt6_astra_low"
    record = xhigh.source_side_record("exterior", pair["exterior"])
    assert record["success"] is True
    assert record["source_reasoning_effort"] == "low"
    assert record["scene_regenerated"] is False


def test_idle_a6000_vllm_budget_is_preregistered():
    aqs = xhigh.load_protocol()["aqs"]
    assert aqs["vllm_max_model_len"] == 8192
    assert aqs["minimum_free_mib"] == 32000
    assert aqs["vllm_gpu_memory_utilization"] == 0.55
    assert aqs["vllm_cpu_offload_gb"] == 0
    assert aqs["vllm_enforce_eager"] is True
    assert aqs["maximum_existing_utilization_percent"] == 10
    assert (
        Path(shutil.which(aqs["vllm_python"]) or aqs["vllm_python"]).resolve()
        == Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}")).resolve()
    )
    assert aqs["runtime_root"].startswith("baselines/runtime/")
    assert aqs["short_socket_root"] == "baselines/.x4"


def test_shared_evaluator_is_routed_without_editing_other_method_files():
    xhigh.configure_common()
    assert xhigh.common.PROTOCOL_PATH == xhigh.PROTOCOL_PATH
    assert xhigh.common.SOURCE_METHOD_LOCK == xhigh.SOURCE_METHOD_LOCK
    assert xhigh.common.source_pair is xhigh.source_pair
    assert xhigh.common.source_side_record is xhigh.source_side_record
    assert xhigh.common.build_one is xhigh.build_one


def test_corrupt_cached_package_is_not_reused(monkeypatch, tmp_path: Path):
    output = tmp_path / "pair" / "seed_0"
    output.mkdir(parents=True)
    (output / "SUCCESS").write_text("stale")
    (output / "manifest.json").write_text(json.dumps({"outputs_sha256": {}}))
    monkeypatch.setattr(
        xhigh, "ORIGINAL_BUILD_ONE", lambda *args: not (output / "SUCCESS").exists()
    )
    assert xhigh.build_one({"spec_id": "unused"}, 0, "pilot", output)
    assert not (output / "SUCCESS").exists()


def test_automatic_gpu_chooses_only_idle_card(monkeypatch):
    monkeypatch.setattr(
        xhigh.common,
        "gpu_state",
        lambda: {
            0: {"free_mib": 43000, "utilization": 100},
            4: {"free_mib": 31000, "utilization": 0},
            5: {"free_mib": 40000, "utilization": 5},
        },
    )
    assert xhigh.choose_idle_gpu() == 5
    monkeypatch.setattr(
        xhigh.common,
        "gpu_state",
        lambda: {
            0: {"free_mib": 43000, "utilization": 100},
        },
    )
    with pytest.raises(RuntimeError, match="No compute-idle GPU"):
        xhigh.choose_idle_gpu()

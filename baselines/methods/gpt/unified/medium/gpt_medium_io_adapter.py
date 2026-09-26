#!/usr/bin/env python3
"""Resumable Table-4 evaluation for GPT-6 Astra Medium plus a fixed IO adapter.

The validated GPT-6 Astra fixed-adapter implementation is reused byte-for-byte.
This wrapper isolates the Medium protocol, sources, blind IDs, outputs and lock,
and lowers only the local VLM context reservation to fit a 24 GiB RTX 4090.
"""

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


import json
import sys
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.gpt.unified.high import gpt_io_adapter as common


BASELINES = REPO / "baselines"
PACKAGE_ROOT = BASELINES / "methods/gpt/unified/medium"
PROTOCOL_DIR = BASELINES / "methods/gpt/protocol/unified/medium"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
BASE_PROTOCOL_PATH = BASELINES / "methods/gpt/protocol/unified/high/protocol.yaml"
PROMPT_PATH = BASELINES / "methods/gpt/protocol/unified/high/aqs_prompt.txt"
SOURCE_METHOD_LOCK = BASELINES / "results/gpt6_astra_medium/method.lock.json"
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_gpt6_astra_io_adapter/model_weight_audit.json"
)
SHARED_RUNNER = BASELINES / "methods/gpt/unified/high/gpt_io_adapter.py"
GEOMETRY_RUNNER = (
    BASELINES / "methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py"
)
BLIND_SALT = "worldbridge-table4-gpt6-astra-medium-fixed-io-adapter-v1"
ORIGINAL_FREEZE = common.freeze


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_protocol() -> dict[str, Any]:
    base = json.loads(BASE_PROTOCOL_PATH.read_text(encoding="utf-8"))
    override = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    return deep_merge(base, override)


def source_pair(spec: dict[str, Any], seed: int) -> dict[str, Any]:
    protocol = load_protocol()
    source = protocol["source"]
    ordinal = int(spec["spec_index"]) % 5
    function = spec["function"]
    urban = common.category_variant(
        common.jsonl(common.URBAN_SPECS),
        source["urban_category_by_function"][function],
        ordinal,
    )
    indoor = common.category_variant(
        common.jsonl(common.INDOOR_SPECS),
        source["indoor_category_by_function"][function],
        ordinal,
    )
    root = REPO / source["data_root"]
    method_dir = source["method_dir"]
    return {
        "exterior": {
            "spec": urban,
            "run": root / "urban" / method_dir / urban["spec_id"] / f"seed_{seed}",
        },
        "interior": {
            "spec": indoor,
            "run": root / "indoor" / method_dir / indoor["spec_id"] / f"seed_{seed}",
        },
    }


def start_and_score(
    trial: str, gpu: int, port: int, workers: int, external: bool
) -> dict[str, Any]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    protocol = load_protocol()
    runtime_root = REPO / protocol["aqs"]["runtime_root"]
    matrix.RUNTIME_ROOT = runtime_root
    matrix.BASELINES_ROOT = REPO / protocol["aqs"]["short_socket_root"]
    matrix.QWEN_ROOT = Path(protocol["aqs"]["model_root"])
    process = None
    try:
        if external:
            if not matrix.llm_health(port):
                raise RuntimeError(f"No healthy local VLM at port {port}")
        else:
            state = common.gpu_state().get(gpu)
            minimum = int(protocol["aqs"]["minimum_free_mib"])
            if (
                state is None
                or state["free_mib"] < minimum
                or state["utilization"] > 10
            ):
                raise RuntimeError(f"GPU {gpu} is not idle enough for VLM: {state}")
            process, _ = matrix.start_vllm(
                gpu,
                port,
                int(protocol["aqs"]["vllm_max_model_len"]),
                int(protocol["aqs"]["vllm_startup_timeout_s"]),
            )
        return common.score_package(trial, port, workers)
    finally:
        if process is not None:
            matrix.stop_process_group(process)


def freeze() -> dict[str, Any]:
    result = ORIGINAL_FREEZE()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    for path in (SHARED_RUNNER, BASE_PROTOCOL_PATH, GEOMETRY_RUNNER):
        lock["files"][common.rel(path)] = common.sha256_file(path)
    lock["source_model"] = "gpt-6-astra"
    lock["source_reasoning_effort"] = "medium"
    lock["source_table2_method_lock_sha256"] = common.sha256_file(SOURCE_METHOD_LOCK)
    lock["shared_fixed_adapter_implementation"] = common.rel(SHARED_RUNNER)
    common.atomic_json(LOCK_PATH, lock)
    common.verify_lock()
    return result


def configure_common() -> None:
    common.PROTOCOL_DIR = PROTOCOL_DIR
    common.PROTOCOL_PATH = PROTOCOL_PATH
    common.PROMPT_PATH = PROMPT_PATH
    common.LOCK_PATH = LOCK_PATH
    common.SOURCE_METHOD_LOCK = SOURCE_METHOD_LOCK
    common.MODEL_WEIGHT_AUDIT = MODEL_WEIGHT_AUDIT
    common.BLIND_SALT = BLIND_SALT
    common.__file__ = str(Path(__file__).resolve())
    common.load_protocol = load_protocol
    common.source_pair = source_pair
    common.start_and_score = start_and_score
    common.freeze = freeze


def main() -> int:
    configure_common()
    return common.main()


if __name__ == "__main__":
    raise SystemExit(main())

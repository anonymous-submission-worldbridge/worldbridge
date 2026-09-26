#!/usr/bin/env python3
"""Resumable Table-4 evaluation for Gemini 3.1 Pro + fixed IO adapter.

Only frozen Table-2 Gemini outputs are consumed. Gemini/Antigravity is never
invoked: geometry and navigation use the shared fixed adapter, while all AQS
requests go to the already-installed local Qwen3-VL checkpoint.
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
import time
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.glm_flash.unified.fixed_adapter import (
    glm_flash_io_adapter as base,
)


common = base.common
BASELINES = REPO / "baselines"
PROTOCOL_DIR = BASELINES / "methods/gemini/protocol/unified/fixed_adapter"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
BASE_PROTOCOL_PATH = BASELINES / "methods/gpt/protocol/unified/high/protocol.yaml"
PROMPT_PATH = BASELINES / "methods/gpt/protocol/unified/high/aqs_prompt.txt"
SOURCE_METHOD_LOCK = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro.lock.json"
)
SOURCE_FORMAL_AUDIT = BASELINES / "results/gemini_3_1_pro/formal_audit.json"
SOURCE_FINAL_AUDIT = BASELINES / "results/gemini_3_1_pro/final_audit.json"
SOURCE_PROTOCOL = BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro.json"
SOURCE_CLIENT_AMENDMENT = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_client_recovery_amendment_20260918.json"
)
SOURCE_RATING_AMENDMENT = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_rating_amendment_20260919.json"
)
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_gpt6_astra_io_adapter/model_weight_audit.json"
)
SHARED_RUNNER = BASELINES / "methods/gpt/unified/high/gpt_io_adapter.py"
GEOMETRY_RUNNER = (
    BASELINES / "methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py"
)
BLIND_SALT = "worldbridge-table4-gemini-3-1-pro-fixed-io-adapter-v1"
ORIGINAL_AGGREGATE = common.aggregate


def load_protocol() -> dict[str, Any]:
    base_protocol = json.loads(BASE_PROTOCOL_PATH.read_text(encoding="utf-8"))
    override = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    return base.deep_merge(base_protocol, override)


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


def source_side_record(side: str, entry: dict[str, Any]) -> dict[str, Any]:
    record = base.ORIGINAL_SOURCE_SIDE_RECORD(side, entry)
    record.update(
        {
            "source_model": "gemini-3.1-pro-high",
            "source_provider": "Google AI Pro account subscription",
            "source_transport": "Antigravity CLI account authentication",
            "source_requested_reasoning_effort": "high",
            "source_auth_mode": "account_subscription_no_api_key",
            "api_key_billing_used": False,
            "scene_regenerated": False,
        }
    )
    manifest_path = entry["run"] / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        source_protocol = json.loads(SOURCE_PROTOCOL.read_text(encoding="utf-8"))
        legacy = source_protocol["legacy_run_identity"]
        if manifest.get("method") != "gemini_3_1_pro":
            raise RuntimeError(f"Foreign Table-2 source method: {manifest_path}")
        if (
            manifest.get("identity", {}).get("protocol_sha256")
            != legacy["protocol_sha256"]
        ):
            raise RuntimeError(
                f"Stale Table-2 Gemini protocol identity: {manifest_path}"
            )
        if manifest.get("model_requested") != "gemini-3.1-pro-high":
            raise RuntimeError(f"Unexpected requested Gemini model: {manifest_path}")
        returned = manifest.get("model_returned")
        if returned not in {None, "gemini-3.1-pro-high"}:
            raise RuntimeError(f"Unexpected returned Gemini model: {manifest_path}")
        if (
            manifest.get("auth_mode")
            != "google_ai_pro_account_via_antigravity_no_api_key"
        ):
            raise RuntimeError(
                f"Gemini source was not account-subscription authenticated: {manifest_path}"
            )
        if sorted(manifest.get("api_key_environment_cleared", [])) != [
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
        ]:
            raise RuntimeError(
                f"Gemini API-key environment was not cleared: {manifest_path}"
            )
        if record["success"]:
            if not (
                manifest.get("generation_success")
                and manifest.get("build_success")
                and manifest.get("render_success")
            ):
                raise RuntimeError(
                    f"SUCCESS disagrees with frozen Gemini terminal state: {manifest_path}"
                )
            attempts = manifest.get("attempts", [])
            if not any(
                attempt.get("model") == "gemini-3.1-pro-high"
                and attempt.get("reasoning_effort") == "high"
                and attempt.get("auth_mode") == "account_subscription_no_api_key"
                for attempt in attempts
            ):
                raise RuntimeError(
                    f"Missing exact Gemini model/effort/auth evidence: {manifest_path}"
                )
    return record


def source_audit() -> dict[str, Any]:
    """Read-only verification of the frozen Gemini Table-2 sources and mapping."""
    source_lock = json.loads(SOURCE_METHOD_LOCK.read_text(encoding="utf-8"))
    expected_identity = (
        "gemini_3_1_pro",
        "gemini-3.1-pro-high",
        "antigravity_cli_google_ai_pro_account",
        "account_subscription_no_api_key",
        True,
    )
    actual_identity = (
        source_lock.get("method"),
        source_lock.get("model"),
        source_lock.get("transport"),
        source_lock.get("auth_mode"),
        source_lock.get("api_key_billing_forbidden"),
    )
    if actual_identity != expected_identity:
        raise RuntimeError(
            f"The source lock is not Gemini 3.1 Pro subscription-only: {actual_identity}"
        )

    formal = json.loads(SOURCE_FORMAL_AUDIT.read_text(encoding="utf-8"))
    if not formal.get("passed") or (
        formal.get("expected"),
        formal.get("terminal"),
        formal.get("success"),
        formal.get("quality_failure"),
    ) != (200, 200, 154, 46):
        raise RuntimeError("The completed Gemini Table-2 formal audit has changed")
    final = json.loads(SOURCE_FINAL_AUDIT.read_text(encoding="utf-8"))
    if (
        final.get("status") != "full_chain_passed"
        or final.get("method") != "gemini_3_1_pro"
        or final.get("model") != "gemini-3.1-pro-high"
        or final.get("api_key_billing_used") is not False
        or final.get("formal_lock_sha256") != common.sha256_file(SOURCE_METHOD_LOCK)
    ):
        raise RuntimeError("The Gemini Table-2 final chain audit is not passing")

    specs, seeds = common.trial_specs_and_seeds("formal")
    success = 0
    failed: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            pair = source_pair(spec, seed)
            refs = {
                side: source_side_record(side, entry) for side, entry in pair.items()
            }
            complete = all(ref["success"] for ref in refs.values())
            success += int(complete)
            if not complete:
                failed.append(
                    {
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "source_specs": {
                            side: ref["spec_id"] for side, ref in refs.items()
                        },
                    }
                )
    if success != 59:
        raise RuntimeError(
            f"Frozen semantic mapping changed: expected 59 successful pairs, got {success}"
        )
    result = {
        "source_method": "gemini_3_1_pro",
        "source_model": "gemini-3.1-pro-high",
        "source_reasoning_effort": "high",
        "source_auth_mode": "account_subscription_no_api_key",
        "planned_pairs": len(specs) * len(seeds),
        "source_successful_pairs": success,
        "source_failed_pairs": failed,
        "source_formal_audit_sha256": common.sha256_file(SOURCE_FORMAL_AUDIT),
        "source_final_audit_sha256": common.sha256_file(SOURCE_FINAL_AUDIT),
        "source_method_lock_sha256": common.sha256_file(SOURCE_METHOD_LOCK),
        "scene_regenerated": False,
        "remote_gemini_requests": 0,
        "gemini_api_key_requests": 0,
        "coding_plan_charges": 0,
    }
    print(
        f"GEMINI_3_1_PRO_TABLE4_SOURCE_AUDIT {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def build_one(spec: dict[str, Any], seed: int, trial: str, output: Path) -> bool:
    """Invalidate only corrupt cached packages before the shared resume check."""
    manifest_path = output / "manifest.json"
    marker = output / "SUCCESS"
    if marker.is_file():
        if not manifest_path.is_file():
            marker.unlink()
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not manifest.get("outputs_sha256") or common.verify_output_hashes(
                manifest
            ):
                marker.unlink()
    return base.ORIGINAL_BUILD_ONE(spec, seed, trial, output)


def aggregate(trial: str) -> dict[str, Any]:
    result = ORIGINAL_AGGREGATE(trial)
    result["comparability_note"] = (
        "The fixed adapter and local VLM proxy are disclosed system components; values are not "
        "native unified-world Gemini scores and are not directly comparable to HoloWorld reported GPT scores."
    )
    _, _, results = common.trial_paths(trial)
    common.atomic_json(results / "summary.json", result)
    return result


def freeze() -> dict[str, Any]:
    result = base.ORIGINAL_FREEZE()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    for path in (
        SHARED_RUNNER,
        BASE_PROTOCOL_PATH,
        GEOMETRY_RUNNER,
        SOURCE_PROTOCOL,
        SOURCE_FORMAL_AUDIT,
        SOURCE_FINAL_AUDIT,
        SOURCE_CLIENT_AMENDMENT,
        SOURCE_RATING_AMENDMENT,
    ):
        lock["files"][common.rel(path)] = common.sha256_file(path)
    lock.update(
        {
            "source_model": "gemini-3.1-pro-high",
            "source_reasoning_effort": "high",
            "source_provider": "Google AI Pro account subscription",
            "source_transport": "Antigravity CLI account authentication",
            "source_auth_mode": "account_subscription_no_api_key",
            "source_table2_method_lock_sha256": common.sha256_file(SOURCE_METHOD_LOCK),
            "source_table2_formal_audit_sha256": common.sha256_file(
                SOURCE_FORMAL_AUDIT
            ),
            "source_table2_final_audit_sha256": common.sha256_file(SOURCE_FINAL_AUDIT),
            "shared_fixed_adapter_implementation": common.rel(SHARED_RUNNER),
            "scene_regenerated": False,
            "remote_gemini_requests": 0,
            "gemini_api_key_requests": 0,
            "coding_plan_charges": 0,
            "gpu_scheduling": load_protocol()["aqs"]["gpu_scheduling_note"],
            "vllm_python": load_protocol()["aqs"]["vllm_python"],
        }
    )
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
    common.source_side_record = source_side_record
    common.build_one = build_one
    common.start_and_score = base.start_and_score
    common.aggregate = aggregate
    common.freeze = freeze
    base.load_protocol = load_protocol


def wait_for_admissible_gpu() -> int:
    """Wait without loading weights until the frozen memory-sharing rule passes."""
    while True:
        try:
            states = common.gpu_state()
            aqs = load_protocol()["aqs"]
            minimum = int(aqs["minimum_free_mib"])
            maximum_utilization = int(aqs["maximum_existing_utilization_percent"])
            candidates = [
                (state["free_mib"], -gpu)
                for gpu, state in states.items()
                if state["free_mib"] >= minimum
                and state["utilization"] <= maximum_utilization
            ]
            if candidates:
                _, neg_gpu = max(candidates)
                selected = -neg_gpu
                print(
                    f"GEMINI_3_1_PRO_TABLE4_GPU_SELECTED gpu={selected} states={states}",
                    flush=True,
                )
                return selected
            error = f"No GPU satisfies free>={minimum} MiB and utilization<={maximum_utilization}%: {states}"
        except Exception as exc:
            error = repr(exc)
        print(f"GEMINI_3_1_PRO_TABLE4_WAITING_FOR_GPU error={error}", flush=True)
        time.sleep(30)


def main() -> int:
    configure_common()
    if len(sys.argv) == 2 and sys.argv[1] == "source-audit":
        source_audit()
        return 0
    if len(sys.argv) > 2 and sys.argv[1] == "score" and "--gpu" in sys.argv:
        gpu_position = sys.argv.index("--gpu") + 1
        if gpu_position < len(sys.argv) and sys.argv[gpu_position] == "auto":
            sys.argv[gpu_position] = str(wait_for_admissible_gpu())
    return common.main()


if __name__ == "__main__":
    raise SystemExit(main())

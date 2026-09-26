#!/usr/bin/env python3
"""Resumable Table-4 evaluation for GLM-5.3 (Low) + fixed IO adapter.

Only frozen Table-2 GLM-5.3 outputs are consumed.  The Coding Plan endpoint is
never called: geometry/navigation use the shared fixed adapter and all AQS
requests go to the already installed local Qwen3-VL checkpoint.
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

from baselines.methods.glm_flash.unified.fixed_adapter import (
    glm_flash_io_adapter as base,
)


common = base.common
BASELINES = REPO / "baselines"
PROTOCOL_DIR = BASELINES / "methods/glm/protocol/unified/fixed_adapter"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
BASE_PROTOCOL_PATH = BASELINES / "methods/gpt/protocol/unified/high/protocol.yaml"
PROMPT_PATH = BASELINES / "methods/gpt/protocol/unified/high/aqs_prompt.txt"
SOURCE_METHOD_LOCK = BASELINES / "methods/glm/protocol/generation/glm_5_3.lock.json"
SOURCE_FORMAL_AUDIT = BASELINES / "results/glm_5_3/formal_audit.json"
SOURCE_CHAIN_AUDITS = (
    BASELINES / "results/glm_5_3/chain_audit_indoor.json",
    BASELINES / "results/glm_5_3/chain_audit_urban.json",
)
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_gpt6_astra_io_adapter/model_weight_audit.json"
)
SHARED_RUNNER = BASELINES / "methods/gpt/unified/high/gpt_io_adapter.py"
GEOMETRY_RUNNER = (
    BASELINES / "methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py"
)
BLIND_SALT = "worldbridge-table4-glm-5-3-low-fixed-io-adapter-v1"
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
            "source_model": "glm-5.3",
            "source_provider": "glm-coding-plan",
            "source_transport": "opencode_openai_compatible_glm_coding_plan",
            "source_requested_thinking": {"type": "enabled"},
            "source_requested_reasoning_effort": "low",
            "scene_regenerated": False,
        }
    )
    manifest_path = entry["run"] / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("method") != "glm_5_3":
            raise RuntimeError(f"Foreign Table-2 source method: {manifest_path}")
        source_lock = json.loads(SOURCE_METHOD_LOCK.read_text(encoding="utf-8"))
        expected_protocol = source_lock["files_sha256"][
            "methods/glm/protocol/generation/glm_5_3.json"
        ]
        if manifest.get("identity", {}).get("protocol_sha256") != expected_protocol:
            raise RuntimeError(f"Stale Table-2 GLM protocol identity: {manifest_path}")
        if record["success"]:
            if not (
                manifest.get("generation_success")
                and manifest.get("build_success")
                and manifest.get("render_success")
            ):
                raise RuntimeError(
                    f"SUCCESS disagrees with frozen GLM terminal state: {manifest_path}"
                )
            attempts = [
                attempt
                for attempt in manifest.get("attempts", [])
                if attempt.get("model_evidence")
            ]
            if not any(
                attempt["model_evidence"].get("providerID") == "glm-coding-plan"
                and attempt["model_evidence"].get("modelID") == "glm-5.3"
                and attempt.get("reasoning_effort") == "low"
                for attempt in attempts
            ):
                raise RuntimeError(
                    f"Missing exact GLM provider/model/effort evidence: {manifest_path}"
                )
    return record


def source_audit() -> dict[str, Any]:
    """Read-only verification of the frozen Table-2 sources and pair mapping."""
    source_lock = json.loads(SOURCE_METHOD_LOCK.read_text(encoding="utf-8"))
    if (
        source_lock.get("method"),
        source_lock.get("model"),
        source_lock.get("reasoning_effort"),
    ) != ("glm_5_3", "glm-5.3", "low"):
        raise RuntimeError("The source method lock is not GLM-5.3 Low")
    formal = json.loads(SOURCE_FORMAL_AUDIT.read_text(encoding="utf-8"))
    if (formal.get("expected"), formal.get("counts")) != (
        200,
        {"quality": 139, "valid": 61},
    ):
        raise RuntimeError("The completed GLM-5.3 Table-2 formal audit has changed")
    chains = [
        json.loads(path.read_text(encoding="utf-8")) for path in SOURCE_CHAIN_AUDITS
    ]
    if {chain.get("domain") for chain in chains} != {"indoor", "urban"}:
        raise RuntimeError("The GLM-5.3 Table-2 domain audit set is incomplete")
    if any(
        chain.get("status") != "full_chain_passed"
        or chain.get("method") != "glm_5_3"
        or chain.get("model") != "glm-5.3"
        or chain.get("reasoning_effort") != "low"
        for chain in chains
    ):
        raise RuntimeError("A GLM-5.3 Table-2 domain chain audit is not passing")
    if sum(int(chain["valid_runs"]) for chain in chains) != 61:
        raise RuntimeError("GLM-5.3 Table-2 valid-run totals disagree")

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
    if success != 8:
        raise RuntimeError(
            f"Frozen semantic mapping changed: expected 8 successful pairs, got {success}"
        )
    result = {
        "source_method": "glm_5_3",
        "source_model": "glm-5.3",
        "source_reasoning_effort": "low",
        "planned_pairs": len(specs) * len(seeds),
        "source_successful_pairs": success,
        "source_failed_pairs": failed,
        "source_formal_audit_sha256": common.sha256_file(SOURCE_FORMAL_AUDIT),
        "source_chain_audits_sha256": {
            common.rel(path): common.sha256_file(path) for path in SOURCE_CHAIN_AUDITS
        },
        "scene_regenerated": False,
        "remote_generation_requests": 0,
    }
    print(
        f"GLM_5_3_TABLE4_SOURCE_AUDIT {json.dumps(result, sort_keys=True)}", flush=True
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
    """Use the shared arithmetic while recording method-correct provenance."""
    result = ORIGINAL_AGGREGATE(trial)
    result["comparability_note"] = (
        "The fixed adapter and local VLM proxy are disclosed system components; "
        "values are not native unified-world GLM-5.3 scores and are not directly "
        "comparable to HoloWorld reported GPT scores."
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
        SOURCE_FORMAL_AUDIT,
        *SOURCE_CHAIN_AUDITS,
    ):
        lock["files"][common.rel(path)] = common.sha256_file(path)
    lock.update(
        {
            "source_model": "glm-5.3",
            "source_reasoning_effort": "low",
            "source_provider": "glm-coding-plan",
            "source_transport": "opencode_openai_compatible_glm_coding_plan",
            "source_table2_method_lock_sha256": common.sha256_file(SOURCE_METHOD_LOCK),
            "source_table2_formal_audit_sha256": common.sha256_file(
                SOURCE_FORMAL_AUDIT
            ),
            "source_table2_chain_audits_sha256": {
                common.rel(path): common.sha256_file(path)
                for path in SOURCE_CHAIN_AUDITS
            },
            "shared_fixed_adapter_implementation": common.rel(SHARED_RUNNER),
            "remote_generation_requests": 0,
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


def main() -> int:
    configure_common()
    if len(sys.argv) == 2 and sys.argv[1] == "source-audit":
        source_audit()
        return 0
    if len(sys.argv) > 2 and sys.argv[1] == "score" and "--gpu" in sys.argv:
        gpu_position = sys.argv.index("--gpu") + 1
        if gpu_position < len(sys.argv) and sys.argv[gpu_position] == "auto":
            sys.argv[gpu_position] = str(base.choose_idle_gpu())
    return common.main()


if __name__ == "__main__":
    raise SystemExit(main())

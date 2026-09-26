#!/usr/bin/env python3
"""Resumable Table-4 evaluation for syncity-3k plus a fixed IO adapter."""

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


import argparse
import copy
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
sys.path.insert(0, str(REPO))

from baselines.methods.gpt.unified.high import gpt_io_adapter as common  # noqa: E402


PROTOCOL_DIR = BASELINES / "methods/syncity/protocol/unified/fixed_adapter"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
PROMPT_PATH = PROTOCOL_DIR / "aqs_prompt.txt"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
BASE_PROTOCOL_PATH = BASELINES / "methods/gpt/protocol/unified/high/protocol.yaml"
COMMON_RUNNER = BASELINES / "methods/gpt/unified/high/gpt_io_adapter.py"
TABLE4_SPECS = BASELINES / "protocol/unified/specs.jsonl"
INDOOR_SPECS = BASELINES / "protocol/generation/indoor_specs.jsonl"
URBAN_SPECS = BASELINES / "protocol/generation/urban_specs.jsonl"
SOURCE_METHOD_LOCK = BASELINES / "protocol/generation/methods.lock.json"
SOURCE_MATRIX_AUDIT = BASELINES / "results/syncity3k/matrix_audit.json"
SOURCE_INDOOR_SUMMARY = BASELINES / "results/syncity3k/indoor/table2_full.json"
SOURCE_URBAN_SUMMARY = BASELINES / "results/syncity3k/urban/table2_full.json"
SOURCE_PROTOCOL = (
    BASELINES / "methods/syncity/protocol/generation/syncity3k_protocol.yaml"
)
MODEL_MANIFEST = BASELINES / "hyworld2_runtime/manifests/qwen3_vl_8b_modelscope.json"
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_syncity3k_io_adapter/model_weight_audit.json"
)
WEIGHT_AUDITOR = BASELINES / "tools/audit_weight_manifest.py"
NAVMESH_EVALUATOR = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"
RECAST_BINARY = (
    BASELINES
    / "methods/worldgen/geometry/runtime/recast_glibc231_clean2/recast.cpython-311-x86_64-linux-gnu.so"
)
BLIND_SALT = "worldbridge-table4-syncity3k-fixed-io-adapter-v1"

METRICS = common.METRICS
_AUDIT_INDEX: dict[tuple[str, str, int], str] | None = None
_SOURCE_CACHE: dict[str, dict[str, Any]] = {}


def _deep_update(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key == "inherits":
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_update(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_protocol() -> dict[str, Any]:
    value = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    inherited = value.get("inherits")
    if not inherited:
        return value
    base = json.loads((REPO / inherited).read_text(encoding="utf-8"))
    return _deep_update(base, value)


def _matrix_audit_index() -> dict[tuple[str, str, int], str]:
    global _AUDIT_INDEX
    if _AUDIT_INDEX is None:
        audit = json.loads(SOURCE_MATRIX_AUDIT.read_text(encoding="utf-8"))
        if audit.get("complete") is not True or int(audit.get("expected", -1)) != 200:
            raise RuntimeError("Frozen syncity-3k Table-2 matrix audit is not complete")
        _AUDIT_INDEX = {
            (str(row["domain"]), str(row["spec_id"]), int(row["logical_seed"])): str(
                row["status"]
            )
            for row in audit["runs"]
        }
    return _AUDIT_INDEX


def source_pair(spec: dict[str, Any], seed: int) -> dict[str, Any]:
    protocol = load_protocol()
    source = protocol["source"]
    ordinal = int(spec["spec_index"]) % 5
    function = spec["function"]
    urban = common.category_variant(
        common.jsonl(URBAN_SPECS),
        source["urban_category_by_function"][function],
        ordinal,
    )
    indoor = common.category_variant(
        common.jsonl(INDOOR_SPECS),
        source["indoor_category_by_function"][function],
        ordinal,
    )
    root = REPO / source["data_root"]
    return {
        "exterior": {
            "domain": "urban",
            "spec": urban,
            "run": root / "urban/syncity3k" / urban["spec_id"] / f"seed_{seed}",
        },
        "interior": {
            "domain": "indoor",
            "spec": indoor,
            "run": root / "indoor/syncity3k" / indoor["spec_id"] / f"seed_{seed}",
        },
    }


def source_side_record(side: str, entry: dict[str, Any]) -> dict[str, Any]:
    run = entry["run"]
    cache_key = f"{side}|{run.resolve()}"
    if cache_key in _SOURCE_CACHE:
        return copy.deepcopy(_SOURCE_CACHE[cache_key])
    protocol = load_protocol()
    spec_id = str(entry["spec"]["spec_id"])
    seed = int(run.name.removeprefix("seed_"))
    domain = str(entry["domain"])
    status = _matrix_audit_index().get((domain, spec_id, seed), "missing")
    required = [
        run / value
        for value in protocol["source"]["required_files_per_successful_side"]
    ]
    missing = [common.rel(path) for path in required if not path.is_file()]
    manifest_path = run / "run_manifest.json"
    manifest = (
        json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest_path.is_file()
        else {}
    )
    scene = run / "scene/scene_color_adjusted.ply"
    scene_size = scene.stat().st_size if scene.is_file() else None
    manifest_valid = bool(
        manifest.get("method") == "syncity3k"
        and manifest.get("domain") == domain
        and manifest.get("spec_id") == spec_id
        and int(manifest.get("logical_seed", -1)) == seed
        and manifest.get("generation_success") is True
        and manifest.get("render_success") is True
        and manifest.get("scene_file") == "scene/scene_color_adjusted.ply"
        and scene_size == int(manifest.get("scene_size_bytes", -1))
    )
    success = (
        status == "formal_success"
        and (run / "SUCCESS").is_file()
        and not missing
        and manifest_valid
    )
    record: dict[str, Any] = {
        "side": side,
        "domain": domain,
        "spec_id": spec_id,
        "logical_seed": seed,
        "run": common.rel(run),
        "success": success,
        "matrix_audit_status": status,
        "missing_required": missing,
        "manifest_valid": manifest_valid,
        "run_manifest": {
            "path": common.rel(manifest_path),
            "sha256": common.sha256_file(manifest_path),
        }
        if manifest_path.is_file()
        else None,
    }
    if success:
        record["scene_ply"] = {
            "path": common.rel(scene),
            "size_bytes": scene_size,
            "size_verified_against_run_manifest": True,
            "immutable": True,
            "used_for_adapter_metrics": False,
        }
        record["anchors"] = [
            {
                "index": index,
                "path": common.rel(run / f"renders/anchors/rgb_{index:03d}.png"),
                "sha256": common.sha256_file(
                    run / f"renders/anchors/rgb_{index:03d}.png"
                ),
            }
            for index in range(8)
        ]
    _SOURCE_CACHE[cache_key] = copy.deepcopy(record)
    return record


def configure_common() -> None:
    common.PROTOCOL_DIR = PROTOCOL_DIR
    common.PROTOCOL_PATH = PROTOCOL_PATH
    common.PROMPT_PATH = PROMPT_PATH
    common.LOCK_PATH = LOCK_PATH
    common.TABLE4_SPECS = TABLE4_SPECS
    common.INDOOR_SPECS = INDOOR_SPECS
    common.URBAN_SPECS = URBAN_SPECS
    common.SOURCE_METHOD_LOCK = SOURCE_METHOD_LOCK
    common.MODEL_WEIGHT_AUDIT = MODEL_WEIGHT_AUDIT
    common.NAVMESH_EVALUATOR = NAVMESH_EVALUATOR
    common.RECAST_BINARY = RECAST_BINARY
    common.BLIND_SALT = BLIND_SALT
    common.__file__ = str(Path(__file__).resolve())
    common.load_protocol = load_protocol
    common.source_pair = source_pair
    common.source_side_record = source_side_record


def build_trial(trial: str) -> dict[str, Any]:
    configure_common()
    if trial == "formal":
        common.verify_lock()
    data_root, _, _ = common.trial_paths(trial)
    specs, seeds = common.trial_specs_and_seeds(trial)
    successes = 0
    for spec in specs:
        for seed in seeds:
            output = common.safe_run_dir(data_root, spec["spec_id"], seed)
            success = common.build_one(spec, seed, trial, output)
            if success:
                common.atomic_text(
                    output / "SUCCESS",
                    "syncity-3k plus fixed IO adapter output contract complete\n",
                )
            successes += int(success)
            print(
                f"SYNCITY3K_TABLE4_BUILD spec={spec['spec_id']} seed={seed} success={success}",
                flush=True,
            )
    result = {
        "trial": trial,
        "planned_pairs": len(specs) * len(seeds),
        "successful_pairs": successes,
        "output_root": common.rel(data_root),
    }
    print(
        f"SYNCITY3K_TABLE4_BUILD_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def audit_weights() -> dict[str, Any]:
    protocol = load_protocol()
    command = [
        sys.executable,
        str(WEIGHT_AUDITOR),
        "--manifest",
        str(REPO / protocol["aqs"]["model_manifest"]),
        "--root",
        str(Path(protocol["aqs"]["model_root"])),
        "--ignore",
        ".gitattributes",
        "configuration.json",
        "--output",
        str(MODEL_WEIGHT_AUDIT),
    ]
    subprocess.run(command, check=True)
    return json.loads(MODEL_WEIGHT_AUDIT.read_text(encoding="utf-8"))


def package_trial(trial: str) -> dict[str, Any]:
    configure_common()
    return common.package_trial(trial)


def score_trial(
    trial: str, gpu: int, port: int, workers: int, external: bool
) -> dict[str, Any]:
    configure_common()
    # A migrated uid-private .vtmp directory may be read-only. Keep this
    # experiment's ZeroMQ sockets in its own short, writable baselines path.
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    matrix.BASELINES_ROOT = BASELINES / "s4"
    result = common.start_and_score(trial, gpu, port, workers, external)
    _, annotations, _ = common.trial_paths(trial)
    provenance_path = annotations / "AQS_PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    provenance.update(
        {
            "method": "syncity3k_fixed_io_adapter",
            "display_name": "syncity-3k + fixed IO adapter",
            "source_method": "syncity3k",
            "source_outputs_regenerated": False,
        }
    )
    common.atomic_json(provenance_path, provenance)
    return result


def aggregate(trial: str) -> dict[str, Any]:
    configure_common()
    summary = common.aggregate(trial)
    _, _, results = common.trial_paths(trial)
    summary.update(
        {
            "aqs_source": "local Qwen3-VL-8B-Instruct, three seeded VLM passes on reused syncity-3k evidence; human_raters=0",
            "comparability_note": "The fixed adapter and local VLM proxy are disclosed system components; values are not native unified-world syncity-3k scores and are not directly comparable to HoloWorld reported GPT scores.",
            "adapter_attribution": "Shape/portal/navigation results belong to the deterministic synthetic adapter system, not native syncity-3k geometry or navigation.",
            "source_matrix_audit_sha256": common.sha256_file(SOURCE_MATRIX_AUDIT),
            "source_indoor_summary_sha256": common.sha256_file(SOURCE_INDOOR_SUMMARY),
            "source_urban_summary_sha256": common.sha256_file(SOURCE_URBAN_SUMMARY),
        }
    )
    common.atomic_json(results / "summary.json", summary)
    return summary


def audit(trial: str) -> dict[str, Any]:
    configure_common()
    result = common.audit(trial)
    result.update(
        {
            "method": "syncity3k_fixed_io_adapter",
            "display_name": "syncity-3k + fixed IO adapter",
            "source_method": "syncity3k",
            "source_matrix_audit_sha256": common.sha256_file(SOURCE_MATRIX_AUDIT),
            "source_indoor_summary_sha256": common.sha256_file(SOURCE_INDOOR_SUMMARY),
            "source_urban_summary_sha256": common.sha256_file(SOURCE_URBAN_SUMMARY),
            "native_geometry_modified": False,
        }
    )
    common.atomic_json(common.trial_paths(trial)[2] / "audit.json", result)
    return result


def freeze() -> dict[str, Any]:
    configure_common()
    lock = common.freeze()
    for path in (
        COMMON_RUNNER,
        BASE_PROTOCOL_PATH,
        SOURCE_MATRIX_AUDIT,
        SOURCE_INDOOR_SUMMARY,
        SOURCE_URBAN_SUMMARY,
        SOURCE_PROTOCOL,
        WEIGHT_AUDITOR,
    ):
        lock["files"][common.rel(path)] = common.sha256_file(path)
    lock.update(
        {
            "source_method": "syncity3k",
            "source_outputs_regenerated": False,
            "large_files_downloaded": False,
        }
    )
    common.atomic_json(LOCK_PATH, lock)
    common.verify_lock()
    print(
        f"SYNCITY3K_TABLE4_FREEZE_COMPLETE {json.dumps(lock, sort_keys=True)}",
        flush=True,
    )
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "package", "aggregate", "audit"):
        child = commands.add_parser(command)
        child.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score = commands.add_parser("score")
    score.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score.add_argument("--gpu", type=int, default=3)
    score.add_argument("--port", type=int, default=18114)
    score.add_argument("--request-workers", type=int, default=4)
    score.add_argument("--external-vllm", action="store_true")
    commands.add_parser("audit-weights")
    commands.add_parser("freeze")
    commands.add_parser("verify-lock")
    args = parser.parse_args()
    configure_common()
    if args.command == "build":
        build_trial(args.trial)
    elif args.command == "package":
        package_trial(args.trial)
    elif args.command == "score":
        score_trial(
            args.trial, args.gpu, args.port, args.request_workers, args.external_vllm
        )
    elif args.command == "aggregate":
        aggregate(args.trial)
    elif args.command == "audit":
        return 0 if audit(args.trial)["passed"] else 1
    elif args.command == "audit-weights":
        audit_weights()
    elif args.command == "freeze":
        freeze()
    elif args.command == "verify-lock":
        common.verify_lock()
        print("SYNCITY3K_TABLE4_LOCK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

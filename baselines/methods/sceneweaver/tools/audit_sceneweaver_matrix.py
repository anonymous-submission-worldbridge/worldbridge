#!/usr/bin/env python3
"""Audit SceneWeaver Table-2 outputs and their frozen provenance."""

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
import hashlib
import json
import math
from collections import Counter
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
MIXED_PROTOCOL = (
    BASELINES / "methods/sceneweaver/protocol/generation/sceneweaver_mixed_codex.json"
)
CURRENT_FILES = {
    "adapter_sha256": (BASELINES / "methods/sceneweaver/adapter_compat.py"),
    "renderer_sha256": (
        BASELINES / "methods/sceneweaver/tools/blender_render_sceneweaver.py"
    ),
}
PATCHED_FILES = {
    "baselines/methods/sceneweaver/runtime/sceneweaver_pipeline/main.py": (
        (BASELINES / "methods/sceneweaver/runtime/sceneweaver_pipeline/main.py")
    ),
    "baselines/methods/sceneweaver/runtime/sceneweaver_executor/generate_indoors_compat.py": (
        (
            BASELINES
            / "methods/sceneweaver/runtime/sceneweaver_executor/generate_indoors_compat.py"
        )
    ),
    "baselines/methods/sceneweaver/runtime/sceneweaver_executor_resume_compat.py": (
        (
            BASELINES
            / "methods/sceneweaver/runtime/sceneweaver_executor_resume_compat.py"
        )
    ),
    "baselines/runtime/sceneweaver_executor_launcher": (
        BASELINES / "runtime/sceneweaver_executor_launcher"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_specs(path: Path, pilot: bool) -> list[dict]:
    specs = [json.loads(line) for line in path.read_text().splitlines() if line]
    if not pilot:
        return specs
    first_by_category = {}
    for spec in specs:
        first_by_category.setdefault(spec["category"], spec)
    return list(first_by_category.values())


def require(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def audit_success(run_dir: Path, errors: list[str]) -> None:
    validation_path = run_dir / "renders/validation.json"
    require(validation_path.is_file(), "missing renders/validation.json", errors)
    if not validation_path.is_file():
        return
    validation = json.loads(validation_path.read_text())
    require(validation.get("valid") is True, "render validation is not valid", errors)
    require(validation.get("anchor_count") == 8, "anchor count is not 8", errors)
    require(validation.get("sequence_count") == 50, "sequence count is not 50", errors)
    anchors = sorted(
        path.name for path in (run_dir / "renders/anchors").glob("rgb_*.png")
    )
    sequence = sorted(
        path.name for path in (run_dir / "renders/sequence").glob("rgb_*.png")
    )
    require(
        anchors == [f"rgb_{index:03d}.png" for index in range(8)],
        "anchor names are not rgb_000..007",
        errors,
    )
    require(
        sequence == [f"rgb_{index:03d}.png" for index in range(1, 51)],
        "sequence names are not rgb_001..050",
        errors,
    )

    cameras_path = run_dir / "renders/sequence/cameras.json"
    require(cameras_path.is_file(), "missing sequence cameras.json", errors)
    if not cameras_path.is_file():
        return
    cameras = json.loads(cameras_path.read_text())
    records = cameras.get("sequence", [])
    require(len(records) == 50, "cameras.json sequence length is not 50", errors)
    invalid_k_indices = []
    for index, record in enumerate(records):
        intrinsic = record.get("K")
        valid_k = (
            isinstance(intrinsic, list)
            and len(intrinsic) == 3
            and all(isinstance(row, list) and len(row) == 3 for row in intrinsic)
            and all(math.isfinite(float(value)) for row in intrinsic for value in row)
        )
        if not valid_k:
            invalid_k_indices.append(index)
    require(
        not invalid_k_indices,
        f"invalid camera K at sequence indices {invalid_k_indices}",
        errors,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--mixed-protocol", type=Path, default=MIXED_PROTOCOL)
    parser.add_argument("--seeds", type=int, nargs="+", default=[0, 1, 2, 3])
    parser.add_argument("--pilot", action="store_true")
    parser.add_argument("--require-all-success", action="store_true")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if any(seed not in range(4) for seed in args.seeds):
        parser.error("seeds must be selected from 0,1,2,3")
    specs = load_specs(args.spec_file, args.pilot)
    current = {name: sha256(path) for name, path in CURRENT_FILES.items()}
    patched = {name: sha256(path) for name, path in PATCHED_FILES.items()}
    mixed = json.loads(args.mixed_protocol.read_text(encoding="utf-8"))
    accepted = mixed.get("accepted_implementation_sha256", {})
    accepted_current = {
        name: set(accepted.get(name, [digest])) for name, digest in current.items()
    }
    accepted_patched = {
        name: set(accepted.get("patched_source_sha256", {}).get(name, [digest]))
        for name, digest in patched.items()
    }
    records = []
    failure_reasons = Counter()
    for spec in specs:
        for seed in args.seeds:
            run_dir = (
                args.data_root / "indoor/sceneweaver" / spec["spec_id"] / f"seed_{seed}"
            )
            errors: list[str] = []
            manifest_path = run_dir / "run_manifest.json"
            require(manifest_path.is_file(), "missing run_manifest.json", errors)
            manifest = (
                json.loads(manifest_path.read_text()) if manifest_path.is_file() else {}
            )
            require(manifest.get("method") == "sceneweaver", "wrong method", errors)
            require(manifest.get("domain") == "indoor", "wrong domain", errors)
            require(manifest.get("spec_id") == spec["spec_id"], "wrong spec_id", errors)
            require(manifest.get("logical_seed") == seed, "wrong logical_seed", errors)
            require(
                manifest.get("method_seed") == int(spec["spec_index"]) * 4 + seed,
                "wrong method_seed",
                errors,
            )
            require(
                manifest.get("adapter_sha256") in accepted_current["adapter_sha256"],
                "unregistered adapter hash",
                errors,
            )
            require(
                manifest.get("renderer_sha256") in accepted_current["renderer_sha256"],
                "unregistered renderer hash",
                errors,
            )
            source_hashes = manifest.get("patched_source_sha256", {})
            for name in patched:
                require(
                    source_hashes.get(name) in accepted_patched[name],
                    f"unregistered patched source hash: {name}",
                    errors,
                )

            success = (run_dir / "SUCCESS").is_file()
            if success:
                require(
                    manifest.get("generation_success") is True,
                    "SUCCESS without generation_success",
                    errors,
                )
                require(
                    manifest.get("render_success") is True,
                    "SUCCESS without render_success",
                    errors,
                )
                audit_success(run_dir, errors)
            else:
                reason = str(
                    manifest.get("failure_reason") or "missing_terminal_status"
                )
                marker_by_reason = {
                    "planner_attempt_budget_exhausted": "PLANNER_BUDGET_EXHAUSTED",
                    "render_validation_failed_terminal": "RENDER_VALIDATION_FAILED",
                }
                marker = marker_by_reason.get(reason)
                require(
                    marker is not None,
                    f"nonterminal failure_reason: {reason}",
                    errors,
                )
                if marker is not None:
                    require(
                        (run_dir / marker).is_file(),
                        f"missing terminal marker: {marker}",
                        errors,
                    )
                failure_reasons[reason] += 1
                if args.require_all_success:
                    errors.append("required SUCCESS marker is missing")
            records.append(
                {
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "success": success,
                    "valid": not errors,
                    "errors": errors,
                    "run_dir": str(run_dir),
                }
            )

    payload = {
        "expected": len(records),
        "success": sum(record["success"] for record in records),
        "valid": sum(record["valid"] for record in records),
        "failure_reasons": dict(sorted(failure_reasons.items())),
        "mixed_protocol": str(args.mixed_protocol),
        "mixed_protocol_sha256": sha256(args.mixed_protocol),
        "records": records,
    }
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
        temporary.replace(args.output)
    print(
        f"SCENEWEAVER_AUDIT expected={payload['expected']} success={payload['success']} "
        f"valid={payload['valid']} failures={len(records) - payload['valid']}"
    )
    for record in records:
        for error in record["errors"]:
            print(
                f"AUDIT_ERROR {record['spec_id']} seed={record['logical_seed']} {error}"
            )
    return 0 if payload["valid"] == payload["expected"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

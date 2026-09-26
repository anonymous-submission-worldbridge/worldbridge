#!/usr/bin/env python3
"""Audit all 200 SynCity 3000 Table-2 runs without generating scenes."""

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
import importlib.util
import json
from collections import Counter
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES_ROOT / "data/table2"
DEFAULT_OUTPUT = BASELINES_ROOT / "results/syncity3k/matrix_audit.json"
UPSTREAM_COMMIT = "b4052154217a13cdbdec28ef77ae77581d90afff"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}


def load_adapter():
    path = BASELINES_ROOT / "methods/syncity/adapter.py"
    spec = importlib.util.spec_from_file_location("syncity3k_audit_adapter", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot import adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_specs(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def classify(
    run_dir: Path, spec: dict[str, Any], seed: int, adapter
) -> tuple[str, str]:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return "not_started", "missing manifest"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        native = json.loads(
            (run_dir / "input/native_input.json").read_text(encoding="utf-8")
        )
        stored_spec = json.loads(
            (run_dir / "input/spec.json").read_text(encoding="utf-8")
        )
    except Exception as error:
        return "infrastructure_failure", f"invalid provenance JSON: {error}"
    identity = {
        "method": "syncity3k",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "method_seed": seed,
        "upstream_commit": UPSTREAM_COMMIT,
    }
    mismatches = [
        key for key, expected in identity.items() if manifest.get(key) != expected
    ]
    if stored_spec != spec:
        mismatches.append("stored_spec")
    if native != adapter.compile_native_input(spec, seed):
        mismatches.append("native_input")
    if mismatches:
        return "stale_or_nonformal", f"identity mismatch: {sorted(mismatches)}"

    if (
        (run_dir / "QUALITY_FAILURE").is_file()
        and manifest.get("failure_reason") == "generation_method_failure"
        and manifest.get("generation_success") is False
        and manifest.get("render_success") is False
        and manifest.get("failure_code")
    ):
        return "quality_failure", str(manifest["failure_code"])

    scene = run_dir / "scene/scene_color_adjusted.ply"
    anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
    sequence = sorted((run_dir / "renders/sequence").glob("rgb_*.png"))
    cameras = run_dir / "renders/sequence/cameras.json"
    validation_path = run_dir / "renders/validation.json"
    if (
        not manifest.get("generation_success")
        or not scene.is_file()
        or scene.stat().st_size == 0
    ):
        return "infrastructure_failure", str(
            manifest.get("failure_reason") or "generation incomplete"
        )
    if len(anchors) != 8 or len(sequence) != 50 or not cameras.is_file():
        return "infrastructure_failure", (
            f"output incomplete: anchors={len(anchors)} sequence={len(sequence)} "
            f"cameras={cameras.is_file()}"
        )
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except Exception as error:
        return "infrastructure_failure", f"invalid validation JSON: {error}"
    if (
        manifest.get("render_success")
        and validation.get("valid")
        and (run_dir / "SUCCESS").is_file()
    ):
        return "formal_success", ""
    if manifest.get(
        "failure_reason"
    ) == "render_validator_failure" and not validation.get("valid"):
        return "quality_failure", "; ".join(validation.get("errors", [])[:5])
    return "infrastructure_failure", str(
        manifest.get("failure_reason") or "render incomplete"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    output = args.json_output.resolve()
    data_root.relative_to(BASELINES_ROOT.resolve())
    output.relative_to(BASELINES_ROOT.resolve())
    adapter = load_adapter()
    rows: list[dict[str, Any]] = []
    for domain, spec_file in SPEC_FILES.items():
        for spec in load_specs(spec_file):
            for seed in range(4):
                run_dir = (
                    data_root / domain / "syncity3k" / spec["spec_id"] / f"seed_{seed}"
                )
                status, detail = classify(run_dir, spec, seed, adapter)
                rows.append(
                    {
                        "domain": domain,
                        "spec_id": spec["spec_id"],
                        "logical_seed": seed,
                        "status": status,
                        "detail": detail,
                        "run_dir": str(run_dir),
                    }
                )
    counts = Counter(row["status"] for row in rows)
    terminal = counts.get("formal_success", 0) + counts.get("quality_failure", 0)
    payload = {
        "method": "syncity3k",
        "expected": 200,
        "counts": dict(sorted(counts.items())),
        "complete": terminal == 200,
        "runs": rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    temporary.replace(output)
    print(
        json.dumps(
            {key: payload[key] for key in ("expected", "counts", "complete")},
            sort_keys=True,
        )
    )
    return 0 if payload["complete"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

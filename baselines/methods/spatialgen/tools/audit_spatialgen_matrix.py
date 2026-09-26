#!/usr/bin/env python3
"""Read-only provenance and completion audit for the SpatialGen 100-run matrix."""

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
from collections import Counter
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DEFAULT_OUTPUT = BASELINES_ROOT / "results/spatialgen/matrix_audit.json"
SOURCE_PATHS = {
    "adapter_sha256": (BASELINES_ROOT / "methods/spatialgen/adapter.py"),
    "prepare_script_sha256": (
        BASELINES_ROOT / "methods/spatialgen/tools/prepare_spatialgen_inputs.py"
    ),
    "reference_script_sha256": (
        BASELINES_ROOT / "methods/spatialgen/tools/spatialgen_generate_reference.py"
    ),
    "renderer_sha256": (
        BASELINES_ROOT / "methods/spatialgen/tools/render_spatialgen_generation.py"
    ),
    "base_protocol_sha256": (BASELINES_ROOT / "protocol/generation/protocol.yaml"),
    "spatialgen_protocol_sha256": (
        BASELINES_ROOT
        / "methods/spatialgen/protocol/generation/spatialgen_protocol.yaml"
    ),
    "spatialgen_inference_sha256": BASELINES_ROOT
    / "vendor/SpatialGen/src/inference_sd.py",
    "spatialgen_unet_loader_sha256": BASELINES_ROOT
    / "vendor/SpatialGen/diffusers_spatialgen/models/unets/unet_mvmm2d_condition.py",
    "sparseradegs_train_sha256": BASELINES_ROOT
    / "vendor/SpatialGen/src/recons/Sparse-RaDeGS/train.py",
    "sparseradegs_loss_sha256": BASELINES_ROOT
    / "vendor/SpatialGen/src/recons/Sparse-RaDeGS/utils/loss_utils.py",
    "sparseradegs_render_sha256": BASELINES_ROOT
    / "vendor/SpatialGen/src/recons/Sparse-RaDeGS/render.py",
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_specs(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def attempt_is_current(attempt: dict, expected: dict[str, str]) -> bool:
    return all(attempt.get(key) == value for key, value in expected.items())


def attempt_has_traceback(run_dir: Path, attempt: dict) -> bool:
    log = attempt.get("log")
    if not log:
        return False
    try:
        return "Traceback (most recent call last):" in (run_dir / log).read_text(
            encoding="utf-8", errors="replace"
        )
    except OSError:
        return False


def classify(run_dir: Path, expected: dict[str, str]) -> tuple[str, str]:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return "not_started", "missing manifest"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        return "started_or_active", f"invalid manifest: {error}"

    attempts = manifest.get("attempts", [])
    generate = [
        item
        for item in attempts
        if item.get("phase") == "generate" and attempt_is_current(item, expected)
    ]
    render = [
        item
        for item in attempts
        if item.get("phase") == "render" and attempt_is_current(item, expected)
    ]
    good_generate = any(item.get("success") is True for item in generate)
    good_render = any(item.get("success") is True for item in render)

    validation_path = run_dir / "renders/validation.json"
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        validation = {}
    if (
        (run_dir / "SUCCESS").exists()
        and good_generate
        and good_render
        and validation.get("valid") is True
    ):
        return "formal_success", ""

    if render:
        last = render[-1]
        if (
            good_generate
            and last.get("success") is False
            and last.get("timed_out") is False
            and last.get("exit_code") == 0
            and not attempt_has_traceback(run_dir, last)
        ):
            return "quality_failure", "frozen render validator rejected output"
        if last.get("success") is False:
            return "infrastructure_candidate", "render failed"
    if generate:
        last = generate[-1]
        if last.get("success") is False:
            return "infrastructure_candidate", "generation or reconstruction failed"
        if last.get("success") is True:
            return "started_or_active", "generation complete; render missing"
    if (run_dir / "SUCCESS").exists() or (run_dir / "GENERATION_SUCCESS").exists():
        return "stale_or_nonformal", "success markers lack current provenance"
    return "started_or_active", str(
        manifest.get("failure_reason") or "no terminal attempt"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--pilot",
        action="store_true",
        help="Audit the first frozen spec per room category and seeds 0,1.",
    )
    args = parser.parse_args()
    for label, path in (
        ("data-root", args.data_root),
        ("json-output", args.json_output),
    ):
        try:
            path.resolve().relative_to(BASELINES_ROOT.resolve())
        except ValueError as error:
            raise ValueError(f"{label} must remain below baselines/") from error

    expected = {key: sha256_file(path) for key, path in SOURCE_PATHS.items()}
    specs = load_specs(args.spec_file)
    seeds = range(4)
    if args.pilot:
        first_by_category: dict[str, dict] = {}
        for spec in specs:
            first_by_category.setdefault(spec["category"], spec)
        specs = list(first_by_category.values())
        seeds = range(2)

    rows = []
    for spec in specs:
        spec_id = spec["spec_id"]
        for seed in seeds:
            run_dir = args.data_root / "indoor/spatialgen" / spec_id / f"seed_{seed}"
            status, detail = classify(run_dir, expected)
            rows.append(
                {
                    "spec_id": spec_id,
                    "logical_seed": seed,
                    "status": status,
                    "detail": detail,
                    "run_dir": str(run_dir),
                }
            )
    counts = Counter(row["status"] for row in rows)
    terminal = counts.get("formal_success", 0) + counts.get("quality_failure", 0)
    payload = {
        "method": "spatialgen",
        "domain": "indoor",
        "expected": len(rows),
        "current_provenance": expected,
        "counts": dict(sorted(counts.items())),
        "complete": terminal == len(rows),
        "runs": rows,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.json_output.with_suffix(args.json_output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.json_output)
    print(
        json.dumps(
            {key: payload[key] for key in ("expected", "counts", "complete")},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

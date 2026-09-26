#!/usr/bin/env python3
"""Collect existing Infinigen WorldScore records into an auditable ITT checkpoint.

This utility never evaluates a scene and never writes into a run directory.  A
formally successful run contributes its existing, provenance-checked score;
every other protocol slot contributes the preregistered ITT lower bound of 0.
Use a checkpoint-named output while generation retries are still active.
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


import argparse
import importlib.util
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


BASELINES = Path(__file__).resolve().parents[1]
DATA_ROOT = BASELINES / "data/table2/indoor/infinigen_indoors"
SPEC_FILE = BASELINES / "protocol/generation/indoor_specs.jsonl"
DEFAULT_OUTPUT = BASELINES / "results/consistency_per_scene.checkpoint_88.jsonl"


def load_module(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


WORLD_SCORE = load_module(
    "table2_eval_worldscore", (BASELINES / "evaluation/visual/eval_worldscore.py")
)
AUDIT = load_module(
    "table2_audit_infinigen",
    (BASELINES / "methods/infinigen/tools/audit_infinigen_matrix.py"),
)


def load_spec_ids(path: Path) -> list[str]:
    return [
        json.loads(line)["spec_id"]
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def valid_measured_record(
    path: Path, run_dir: Path, spec_id: str, logical_seed: int
) -> dict[str, Any] | None:
    if not (run_dir / "SUCCESS").exists() or not path.exists():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    score = record.get("consistency_3d")
    valid = (
        record.get("method") == "infinigen_indoors"
        and record.get("domain") == "indoor"
        and record.get("spec_id") == spec_id
        and record.get("logical_seed") == logical_seed
        and record.get("metric") == "worldscore_static_3d_consistency"
        and record.get("worldscore_commit") == WORLD_SCORE.WORLD_SCORE_COMMIT
        and record.get("droid_slam_commit") == WORLD_SCORE.DROID_SLAM_COMMIT
        and record.get("checkpoint_sha256") == WORLD_SCORE.CHECKPOINT_SHA256
        and record.get("success") is True
        and isinstance(score, (int, float))
        and math.isfinite(float(score))
        and 0.0 <= float(score) <= 100.0
    )
    return record if valid else None


def infrastructure_attempts(run_dir: Path) -> list[dict[str, Any]]:
    manifest_path = run_dir / "run_manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    return [
        row for row in manifest.get("attempts", []) if AUDIT.is_formal_generate(row)
    ]


def terminal_infrastructure_failure(run_dir: Path) -> bool:
    attempts = infrastructure_attempts(run_dir)
    return len(attempts) >= 2 and attempts[-1].get("success") is False


def itt_failure(
    spec_id: str, seed: int, classification: str, final: bool = False
) -> dict[str, Any]:
    reason_by_class = {
        "quality_failure": "render_quality_failure",
        "infrastructure_candidate": (
            "generation_infrastructure_failure"
            if final
            else "infrastructure_not_terminal_checkpoint"
        ),
        "started_or_active": "run_not_terminal_checkpoint",
        "not_started": "run_not_started_checkpoint",
        "stale_pilot": "nonformal_output_checkpoint",
    }
    reason = reason_by_class.get(classification, "missing_valid_worldscore_record")
    return WORLD_SCORE.failure_record(
        spec_id,
        seed,
        reason,
        detail=f"matrix_audit_classification={classification}",
    )


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--final",
        action="store_true",
        help="Require every matrix slot and every successful metric to be terminal.",
    )
    args = parser.parse_args()

    records: list[dict[str, Any]] = []
    classifications: Counter[str] = Counter()
    measured_scores: list[float] = []
    scores_by_spec: dict[str, list[float]] = defaultdict(list)
    spec_ids = load_spec_ids(args.spec_file)
    for spec_id in spec_ids:
        for seed in range(4):
            run_dir = args.data_root / spec_id / f"seed_{seed}"
            classification = AUDIT.classify(run_dir)
            classifications[classification] += 1
            record = valid_measured_record(
                run_dir / "metrics/consistency_3d.json", run_dir, spec_id, seed
            )
            if record is None:
                if args.final:
                    if classification == "formal_success":
                        raise RuntimeError(
                            f"Final collection rejected successful run without valid metric: "
                            f"{spec_id}/seed_{seed}"
                        )
                    terminal = classification == "quality_failure" or (
                        classification == "infrastructure_candidate"
                        and terminal_infrastructure_failure(run_dir)
                    )
                    if not terminal:
                        raise RuntimeError(
                            f"Final collection rejected nonterminal run: {spec_id}/seed_{seed} "
                            f"classification={classification}"
                        )
                record = itt_failure(spec_id, seed, classification, args.final)
                record["checkpoint_assignment"] = "itt_zero"
            else:
                measured_scores.append(float(record["consistency_3d"]))
                record = dict(record)
                record["checkpoint_assignment"] = "measured"
            score = float(record["consistency_3d"])
            scores_by_spec[spec_id].append(score)
            records.append(record)

    expected = len(spec_ids) * 4
    if len(records) != expected or any(
        len(scores_by_spec[key]) != 4 for key in spec_ids
    ):
        raise RuntimeError("Checkpoint does not contain exactly four seeds per spec")
    spec_means = {key: sum(values) / 4.0 for key, values in scores_by_spec.items()}
    summary = {
        "status": "final" if args.final else "checkpoint_not_final",
        "method": "infinigen_indoors",
        "domain": "indoor",
        "expected_records": expected,
        "record_count": len(records),
        "measured_record_count": len(measured_scores),
        "itt_zero_record_count": expected - len(measured_scores),
        "matrix_classifications": dict(sorted(classifications.items())),
        "conditional_measured_mean": (
            sum(measured_scores) / len(measured_scores) if measured_scores else None
        ),
        "itt_checkpoint_macro_mean": sum(spec_means.values()) / len(spec_ids),
        "per_spec_itt_checkpoint_mean": spec_means,
        "warning": (
            None
            if args.final
            else (
                "Intermediate checkpoint only. Recollect after all infrastructure retries "
                "are terminal before writing the Table-2 value."
            )
        ),
    }
    atomic_text(
        args.output,
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n"
            for row in records
        ),
    )
    summary_path = args.output.with_suffix(".summary.json")
    atomic_text(
        summary_path,
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    print(
        "WORLDSCORE_CHECKPOINT_COMPLETE "
        f"records={len(records)} measured={len(measured_scores)} "
        f"itt_zero={expected - len(measured_scores)} "
        f"mean={summary['itt_checkpoint_macro_mean']:.6f} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

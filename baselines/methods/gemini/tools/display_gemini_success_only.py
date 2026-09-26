#!/usr/bin/env python3
"""Compute the supplementary successful-scene view for Gemini 3.1 Pro."""
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
from pathlib import Path
import statistics


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
SCENE_SOURCES = (
    ("iqa_per_scene.jsonl", ("qalign", "clipiqa_plus")),
    ("human_per_scene.jsonl", ("layout_plausibility", "prompt_alignment")),
    ("consistency_per_scene.jsonl", ("consistency_3d",)),
)
PRECISION = (".2f", ".3f", ".1f", ".1f", ".1f", ".3f", ".3f")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def identity(row: dict) -> tuple[str, int]:
    return row["spec_id"], int(row["logical_seed"])


def write_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    args = parser.parse_args()
    folder = ROOT / "results" / METHOD / "formal" / args.domain
    expected = {
        (json.loads(line)["spec_id"], seed)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
        for seed in range(4)
    }
    values: list[float] = []
    sources: dict[str, str] = {}
    generation_success: set[tuple[str, int]] | None = None
    for filename, metrics in SCENE_SOURCES:
        path = folder / filename
        rows = records(path)
        if len(rows) != 100 or {identity(row) for row in rows} != expected:
            raise RuntimeError("Missing or duplicate formal scene: " + filename)
        successful = {identity(row) for row in rows if row.get("success")}
        if generation_success is None:
            generation_success = successful
        elif (
            filename != "consistency_per_scene.jsonl"
            and successful != generation_success
        ):
            raise RuntimeError("Inconsistent successful-scene identity: " + filename)
        elif filename == "consistency_per_scene.jsonl" and not successful.issubset(
            generation_success
        ):
            raise RuntimeError(
                "Consistency success is not a subset of generated scenes"
            )
        for metric in metrics:
            selected = [float(row[metric]) for row in rows if row.get("success")]
            values.append(statistics.mean(selected) if selected else 0.0)
        sources[filename] = digest(path)
    diversity_path = folder / "diversity_per_spec.jsonl"
    specs = records(diversity_path)
    if len(specs) != 25 or len({row["spec_id"] for row in specs}) != 25:
        raise RuntimeError("Missing or duplicate diversity spec")
    valid = [row for row in specs if int(row["valid_pair_count"]) > 0]
    for metric in ("appearance_diversity_valid", "layout_diversity_valid"):
        values.append(
            statistics.mean(float(row[metric]) for row in valid) if valid else 0.0
        )
    sources[diversity_path.name] = digest(diversity_path)
    display = [format(value, precision) for value, precision in zip(values, PRECISION)]
    report = {
        "method": METHOD,
        "domain": args.domain,
        "metric_successful_runs": len(generation_success or set()),
        "valid_diversity_specs": len(valid),
        "metric_values": dict(
            zip(
                (metric for _, metrics in SCENE_SOURCES for metric in metrics),
                values[:5],
            )
        ),
        "diversity_values": dict(
            zip(
                ("appearance_diversity_valid", "layout_diversity_valid"),
                values[5:],
            )
        ),
        "display": display,
        "formal_sources_sha256": sources,
    }
    output = folder / "table2_success_only.json"
    write_json(output, report)
    print(
        f"| Gemini 3.1 Pro ({args.domain.title()}) | "
        f"{len(generation_success or set())} | {len(valid)} | "
        + " | ".join(display)
        + " |"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Audit final SynCity matrices, metrics, proxy provenance and Table-2 rows."""

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


import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
MATRIX_AUDIT = BASELINES_ROOT / "results/syncity3k/matrix_audit.json"
OUTPUT = BASELINES_ROOT / "results/syncity3k/final_audit.json"
DOCUMENT = BASELINES_ROOT / "Comparison Experiment - Table 2.md"
DOMAINS = ("indoor", "urban")
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}
DISPLAY_LABELS = {
    "indoor": "SynCity 3000 (Indoor)",
    "urban": "SynCity 3000 (Urban)",
}
METRIC_COLUMNS = (
    "qalign",
    "clipiqa_plus",
    "layout_plausibility",
    "prompt_alignment",
    "consistency_3d",
    "appearance_diversity_itt",
    "layout_diversity_itt",
)
EXPECTED_RECORDS = {
    "iqa_per_scene.jsonl": 100,
    "human_per_scene.jsonl": 100,
    "consistency_per_scene.jsonl": 100,
    "diversity_per_spec.jsonl": 25,
}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def check(condition: bool, message: str, errors: list[str]) -> None:
    if not condition:
        errors.append(message)


def audit_domain(domain: str, document: str, errors: list[str]) -> dict[str, Any]:
    result_root = BASELINES_ROOT / "results/syncity3k" / domain
    package = BASELINES_ROOT / "annotations/syncity3k" / domain
    specs = read_jsonl(SPEC_FILES[domain])
    spec_ids = {row["spec_id"] for row in specs}
    check(len(spec_ids) == 25, f"{domain}: expected 25 unique specs", errors)

    private_path = package / "PRIVATE_blind_map.json"
    items_path = package / "items.csv"
    provenance_path = package / "SYNTHETIC_RATING_PROVENANCE.json"
    for path in (private_path, items_path, provenance_path):
        check(path.is_file(), f"{domain}: missing {path}", errors)
    if errors and not all(
        path.is_file() for path in (private_path, items_path, provenance_path)
    ):
        return {"status": "missing_package"}
    private = json.loads(private_path.read_text(encoding="utf-8"))["items"]
    with items_path.open(newline="", encoding="utf-8") as handle:
        items = list(csv.DictReader(handle))
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    successes = sum(bool(row.get("success")) for row in private)
    check(len(private) == 100, f"{domain}: private map is not 100 slots", errors)
    check(len(items) == successes, f"{domain}: public success subset mismatch", errors)
    check(
        provenance.get("human_raters") == 0
        and provenance.get("independent_human_ratings") is False,
        f"{domain}: subjective provenance does not explicitly say zero humans",
        errors,
    )
    check(
        provenance.get("import_rating_source") == "synthetic_proxy_three_profiles",
        f"{domain}: incorrect subjective rating source",
        errors,
    )
    check(
        len(provenance.get("decisions", [])) == successes,
        f"{domain}: one reviewed decision is required per successful scene",
        errors,
    )
    for name, expected_hash in provenance.get("outputs_sha256", {}).items():
        path = package / name
        check(
            path.is_file() and digest(path) == expected_hash,
            f"{domain}: rating output hash mismatch for {name}",
            errors,
        )

    file_stats = {}
    for name, expected_count in EXPECTED_RECORDS.items():
        path = result_root / name
        check(path.is_file(), f"{domain}: missing {name}", errors)
        if not path.is_file():
            continue
        rows = read_jsonl(path)
        selected = [
            row
            for row in rows
            if row.get("method") == "syncity3k" and row.get("domain") == domain
        ]
        check(
            len(selected) == expected_count,
            f"{domain}: {name} has {len(selected)}/{expected_count} selected rows",
            errors,
        )
        if name == "diversity_per_spec.jsonl":
            keys = {row.get("spec_id") for row in selected}
        else:
            keys = {
                (row.get("spec_id"), int(row.get("logical_seed", -1)))
                for row in selected
            }
        check(
            len(keys) == expected_count, f"{domain}: duplicate keys in {name}", errors
        )
        file_stats[name] = {
            "selected_records": len(selected),
            "sha256": digest(path),
        }
        if name == "human_per_scene.jsonl":
            check(
                all(
                    row.get("rating_source") == "synthetic_proxy_three_profiles"
                    for row in selected
                ),
                f"{domain}: human_per_scene contains a misleading source label",
                errors,
            )

    csv_path = result_root / "table2.csv"
    full_path = result_root / "table2_full.json"
    check(csv_path.is_file(), f"{domain}: missing table2.csv", errors)
    check(full_path.is_file(), f"{domain}: missing table2_full.json", errors)
    if not csv_path.is_file() or not full_path.is_file():
        return {
            "status": "missing_aggregate",
            "successes": successes,
            "quality_or_failed_slots": 100 - successes,
            "files": file_stats,
        }
    with csv_path.open(newline="", encoding="utf-8") as handle:
        table_rows = list(csv.DictReader(handle))
    check(len(table_rows) == 1, f"{domain}: table2.csv must contain one row", errors)
    row = table_rows[0]
    check(row.get("method") == "syncity3k", f"{domain}: wrong method in CSV", errors)
    check(row.get("domain") == domain, f"{domain}: wrong domain in CSV", errors)
    check(
        all(row.get(metric, "").strip() for metric in METRIC_COLUMNS),
        f"{domain}: aggregate metric is pending",
        errors,
    )
    full = json.loads(full_path.read_text(encoding="utf-8"))
    check(
        all(
            full.get("metrics", {}).get(metric, {}).get("status") == "complete"
            for metric in METRIC_COLUMNS
        ),
        f"{domain}: full aggregate is incomplete",
        errors,
    )
    values = [row[metric] for metric in METRIC_COLUMNS]
    markdown_row = f"| {DISPLAY_LABELS[domain]} | " + " | ".join(values) + " |"
    check(
        document.count(markdown_row) == 1,
        f"{domain}: exact aggregate row is not present exactly once in Table 2",
        errors,
    )
    return {
        "status": "complete",
        "successes": successes,
        "quality_or_failed_slots": 100 - successes,
        "render_success_rate": row.get("render_success_rate"),
        "table2_values": dict(zip(METRIC_COLUMNS, values)),
        "expected_markdown_row": markdown_row,
        "files": {
            **file_stats,
            "table2.csv": {"sha256": digest(csv_path)},
            "table2_full.json": {"sha256": digest(full_path)},
            "rating_provenance": {"sha256": digest(provenance_path)},
        },
    }


def main() -> int:
    errors: list[str] = []
    document = DOCUMENT.read_text(encoding="utf-8")
    check(MATRIX_AUDIT.is_file(), "Missing final matrix audit", errors)
    matrix: dict[str, Any] = {}
    if MATRIX_AUDIT.is_file():
        matrix = json.loads(MATRIX_AUDIT.read_text(encoding="utf-8"))
        counts = Counter(matrix.get("counts", {}))
        terminal = int(counts.get("formal_success", 0)) + int(
            counts.get("quality_failure", 0)
        )
        check(matrix.get("expected") == 200, "Matrix expected count is not 200", errors)
        check(matrix.get("complete") is True, "Matrix audit is not complete", errors)
        check(terminal == 200, f"Matrix has {terminal}/200 terminal slots", errors)
        check(
            not set(counts) - {"formal_success", "quality_failure"},
            f"Matrix contains nonterminal statuses: {dict(counts)}",
            errors,
        )
    domains = {domain: audit_domain(domain, document, errors) for domain in DOMAINS}
    payload = {
        "method": "syncity3k",
        "complete": not errors,
        "matrix_counts": matrix.get("counts", {}),
        "domains": domains,
        "document_sha256": digest(DOCUMENT),
        "errors": errors,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print(
        json.dumps(
            {"complete": payload["complete"], "error_count": len(errors)},
            sort_keys=True,
        )
    )
    if errors:
        for error in errors:
            print(f"- {error}")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

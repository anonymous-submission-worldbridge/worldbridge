#!/usr/bin/env python3
"""Deterministically recover the one retained malformed formal AQS response."""

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


import copy
import json
import sys
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.gpt.unified.medium import gpt_medium_io_adapter as medium


BASELINES = REPO / "baselines"
ANNOTATIONS = BASELINES / "annotations/table4_gpt6_astra_medium_io_adapter"
RESULTS = BASELINES / "results/table4_gpt6_astra_medium_io_adapter"
AMENDMENT = medium.PROTOCOL_DIR / "formal_schema_recovery_amendment_20260913.json"
LOCK_PATH = medium.LOCK_PATH


def canonicalize_duplicate_response(
    raw: dict[str, Any], frozen: dict[str, int]
) -> tuple[dict[str, Any], dict[str, Any]]:
    parsed = medium.common.recover_duplicate_key_evidence(raw)
    scores = {
        key: parsed[key] for key in ("functional_aqs", "visual_aqs", "spatial_aqs")
    }
    if scores != frozen:
        raise RuntimeError(
            f"Recovered scores changed: expected={frozen} actual={scores}"
        )
    canonical = copy.deepcopy(raw)
    canonical["choices"][0]["message"]["content"] = json.dumps(parsed, sort_keys=True)
    medium.common.parse_score(canonical)
    return parsed, canonical


def main() -> int:
    medium.configure_common()
    medium.common.verify_lock()
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    blind_id = amendment["applies_to"]["blind_id"]
    pass_index = int(amendment["applies_to"]["pass_index"])
    final_path = ANNOTATIONS / "raw" / blind_id / f"pass_{pass_index:02d}.json"
    items = {
        row["blind_id"]: row for row in medium.common.jsonl(ANNOTATIONS / "items.jsonl")
    }
    item = items[blind_id]
    protocol = medium.load_protocol()
    recovered_record = None
    if final_path.is_file():
        current = json.loads(final_path.read_text(encoding="utf-8"))
        medium.common.parse_score(current["raw_response"])
        recovered_record = current
    else:
        pattern = f"pass_{pass_index:02d}_schema_repair_*.json"
        for source in sorted((ANNOTATIONS / "raw_attempts" / blind_id).glob(pattern)):
            envelope = json.loads(source.read_text(encoding="utf-8"))
            frozen = {
                key: int(value) for key, value in envelope["frozen_scores"].items()
            }
            try:
                parsed, canonical = canonicalize_duplicate_response(
                    envelope["raw_response"], frozen
                )
            except Exception:
                continue
            config = protocol["aqs"]
            settings = {
                "model": config["model"],
                "temperature": config["temperature"],
                "top_p": config["top_p"],
                "seed": config["seeds"][pass_index - 1],
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }
            recovered_record = {
                "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
                "human_raters": 0,
                "pass_index": pass_index,
                "input_signature": envelope["input_signature"],
                "settings": settings,
                "schema_repair": True,
                "schema_repair_mode": "deterministic_duplicate_key_relabel_from_preregistered_schema_repair_response",
                "schema_repair_source_attempt": int(envelope["attempt"]),
                "schema_repair_source_path": medium.common.rel(source),
                "schema_repair_source_sha256": medium.common.sha256_file(source),
                "frozen_scores_from_initial_response": frozen,
                "image_sha256": item["montage_sha256"],
                "model_manifest_sha256": medium.common.sha256_file(
                    REPO / config["model_manifest"]
                ),
                "parsed": parsed,
                "initial_raw_response": envelope["raw_response"],
                "raw_response": canonical,
                "created_at_utc": medium.common.utc_now(),
            }
            medium.common.atomic_json(final_path, recovered_record)
            break
    if recovered_record is None:
        raise RuntimeError("No preregistered schema-repair response could be recovered")

    report = {
        "recovered_at_utc": medium.common.utc_now(),
        "blind_id": blind_id,
        "pass_index": pass_index,
        "recovery_mode": recovered_record["schema_repair_mode"],
        "source_attempt": recovered_record["schema_repair_source_attempt"],
        "source_sha256": recovered_record["schema_repair_source_sha256"],
        "frozen_scores": recovered_record["frozen_scores_from_initial_response"],
        "canonical_scores": {
            key: recovered_record["parsed"][key]
            for key in ("functional_aqs", "visual_aqs", "spatial_aqs")
        },
        "new_vlm_request_used": False,
        "scientific_configuration_changed": False,
        "amendment_sha256": medium.common.sha256_file(AMENDMENT),
        "output_path": medium.common.rel(final_path),
        "output_sha256": medium.common.sha256_file(final_path),
    }
    medium.common.atomic_json(RESULTS / "formal_schema_recovery.json", report)

    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    for path in (Path(__file__), AMENDMENT):
        lock["files"][medium.common.rel(path)] = medium.common.sha256_file(path)
    lock.setdefault("formal_amendments", []).append(
        {
            "amendment": medium.common.rel(AMENDMENT),
            "sha256": medium.common.sha256_file(AMENDMENT),
            "scientific_configuration_changed": False,
        }
    )
    lock["formal_amendments"] = list(
        {entry["amendment"]: entry for entry in lock["formal_amendments"]}.values()
    )
    medium.common.atomic_json(LOCK_PATH, lock)
    medium.common.verify_lock()
    print(
        "GPT6_ASTRA_MEDIUM_TABLE4_SCHEMA_RECOVERY_COMPLETE "
        + json.dumps(report, sort_keys=True)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

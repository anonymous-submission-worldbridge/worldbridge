#!/usr/bin/env python3
"""Evidence-only recovery of a frozen Qwen response from one repair response.

This is a documented post-pilot amendment. It never changes a score, prompt,
seed or source scene; it never calls a VLM. Only the first *same-response*
repair containing all six fields, with a string mislabeled as a duplicate
score key, may be relabeled. Every original attempt remains unmodified.
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


import hashlib
import json
import sys
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.gpt.unified.high import gpt_io_adapter as common
from baselines.methods.gpt.unified.low import gpt_low_io_adapter as method


SCORE_KEYS = ("functional_aqs", "visual_aqs", "spatial_aqs")
SOURCE_NOTE = (
    "Post-pilot evidence-only recovery: within the FIRST saved schema-repair "
    "Qwen response, relabel a nonempty string-valued duplicate spatial_aqs "
    "to spatial_evidence. The three numeric scores must match ALL three "
    "original attempts and ALL three saved repair attempts; no VLM call "
    "or cross-response stitching is allowed."
)


def recover_one(
    initial: list[dict[str, Any]], repairs: list[dict[str, Any]]
) -> tuple[dict[str, Any], dict[str, int]]:
    """Refuse any ambiguity or score drift before relabeling one saved reply."""
    if len(initial) != 3 or len(repairs) != 3:
        raise ValueError(
            "Exactly three original and three repair responses are required"
        )
    scores = common.parse_partial_score(initial[0])
    if any(common.parse_partial_score(raw) != scores for raw in initial[1:]):
        raise ValueError("The original Qwen attempts disagree on numeric scores")
    if any(common.parse_partial_score(raw) != scores for raw in repairs):
        raise ValueError("A schema-repair response changed frozen numeric scores")
    recovered = common.recover_duplicate_key_evidence(repairs[0])
    if {key: recovered[key] for key in SCORE_KEYS} != scores:
        raise ValueError("Recovered numeric scores disagree with the initial answer")
    canonical = json.loads(json.dumps(repairs[0]))
    canonical["choices"][0]["message"]["content"] = json.dumps(
        recovered, sort_keys=True
    )
    if common.parse_score(canonical) != recovered:
        raise ValueError("Relabeled same-response evidence is not parseable")
    return canonical, scores


def main() -> int:
    method.configure_common()
    common.verify_lock()
    _, annotations, results = common.trial_paths("formal")
    protocol = method.load_protocol()
    if protocol["status"] != "formal_frozen":
        raise RuntimeError(
            "Only a frozen formal protocol may use this recovery amendment"
        )
    config = protocol["aqs"]
    model_hash = common.sha256_file(REPO / config["model_manifest"])
    journal_path = results / "formal_schema_recovery.json"
    records = (
        json.loads(journal_path.read_text(encoding="utf-8"))["recoveries"]
        if journal_path.is_file()
        else []
    )
    previous = {
        (record["blind_id"], record["pass_index"]): record for record in records
    }
    for record in records:
        for relative, expected in record["sources_sha256"].items():
            source_path = REPO / relative
            if not source_path.is_file() or common.sha256_file(source_path) != expected:
                raise RuntimeError(
                    f"Altered original Qwen source response: {source_path}"
                )
    for item in common.jsonl(annotations / "items.jsonl"):
        blind_id = item["blind_id"]
        image_path = REPO / item["montage"]
        if common.sha256_file(image_path) != item["montage_sha256"]:
            raise RuntimeError(f"Changed Qwen image evidence: {image_path}")
        prompt = common.score_prompt(item)
        for pass_index, seed in enumerate(config["seeds"], 1):
            settings = {
                "model": config["model"],
                "temperature": config["temperature"],
                "top_p": config["top_p"],
                "seed": seed,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }
            signature = common.sha256_json(
                {
                    "settings": settings,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "image_sha256": item["montage_sha256"],
                    "model_manifest_sha256": model_hash,
                }
            )
            output = annotations / "raw" / blind_id / f"pass_{pass_index:02d}.json"
            prior = previous.get((blind_id, pass_index))
            if output.is_file():
                cached = json.loads(output.read_text(encoding="utf-8"))
                if cached.get("input_signature") != signature:
                    raise RuntimeError(f"Changed cached rating signature: {output}")
                common.parse_score(cached["raw_response"])
                if prior and common.sha256_file(output) != prior["canonical_sha256"]:
                    raise RuntimeError(f"Corrupt recovered Qwen rating: {output}")
                if (
                    cached.get("schema_repair_mode")
                    == "first_saved_repair_duplicate_key_relabel"
                    and not prior
                ):
                    raise RuntimeError(f"Unjournaled Qwen schema recovery: {output}")
                continue
            source = annotations / "raw_attempts" / blind_id
            initial_paths = [
                source / f"pass_{pass_index:02d}_attempt_{attempt:02d}.json"
                for attempt in (1, 2, 3)
            ]
            repair_paths = [
                source / f"pass_{pass_index:02d}_schema_repair_{attempt:02d}.json"
                for attempt in (1, 2, 3)
            ]
            if not all(path.is_file() for path in initial_paths + repair_paths):
                continue  # This pass has not exhausted the preregistered recovery attempts.
            saved = [
                json.loads(path.read_text(encoding="utf-8"))
                for path in initial_paths + repair_paths
            ]
            if any(row.get("input_signature") != signature for row in saved):
                raise RuntimeError(
                    f"Incompatible saved Qwen source signature: {blind_id} pass={pass_index}"
                )
            initial_raw = [row["raw_response"] for row in saved[:3]]
            repair_raw = [row["raw_response"] for row in saved[3:]]
            frozen = common.parse_partial_score(initial_raw[0])
            if any(row.get("frozen_scores") != frozen for row in saved[3:]):
                raise RuntimeError(
                    f"Repair request did not freeze the original scores: {blind_id} pass={pass_index}"
                )
            canonical, scores = recover_one(initial_raw, repair_raw)
            hashes = {
                common.rel(path): common.sha256_file(path)
                for path in initial_paths + repair_paths
            }
            common.atomic_json(
                output,
                {
                    "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
                    "human_raters": 0,
                    "pass_index": pass_index,
                    "input_signature": signature,
                    "settings": settings,
                    "image_sha256": item["montage_sha256"],
                    "model_manifest_sha256": model_hash,
                    "schema_repair": True,
                    "schema_repair_mode": "first_saved_repair_duplicate_key_relabel",
                    "schema_repair_settings": {
                        **settings,
                        "temperature": 0,
                        "top_p": 1,
                    },
                    "frozen_scores_from_initial_response": scores,
                    "source_raw_attempts_sha256": hashes,
                    "original_initial_raw_response": initial_raw[0],
                    "original_first_repair_raw_response": repair_raw[0],
                    "parsed": common.parse_score(canonical),
                    "raw_response": canonical,
                    "created_at_utc": common.utc_now(),
                },
            )
            record = {
                "blind_id": blind_id,
                "pass_index": pass_index,
                "source_method": "gpt6_astra_low",
                "source_reasoning_effort": "low",
                "frozen_scores": scores,
                "input_signature": signature,
                "sources_sha256": hashes,
                "canonical_sha256": common.sha256_file(output),
            }
            records.append(record)
            previous[(blind_id, pass_index)] = record
            common.atomic_json(
                journal_path,
                {
                    "amendment": SOURCE_NOTE,
                    "no_vlm_requests": True,
                    "scores_unchanged": True,
                    "recoveries": sorted(
                        records, key=lambda row: (row["blind_id"], row["pass_index"])
                    ),
                },
            )
            print(
                f"GPT6_ASTRA_TABLE4_EVIDENCE_ONLY_RECOVERY item={blind_id} pass={pass_index} frozen_scores={scores}",
                flush=True,
            )
    print(
        f"GPT6_ASTRA_TABLE4_RECOVERY_AUDIT count={len(records)} journal={journal_path}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

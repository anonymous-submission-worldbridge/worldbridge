#!/usr/bin/env python3
"""Build anonymous Table-4 evidence, score it locally, and aggregate ITT AQS."""

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
import base64
import csv
import hashlib
import importlib.util
import io
import json
import random
import statistics
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
TABLE4_ROOT = _BASELINE_PROJECT_ROOT / "baselines/methods/hyworld/unified/native"
PROTOCOL_ROOT = BASELINES_ROOT / "protocol/unified"
RESULT_ROOT = BASELINES_ROOT / "results/table4/hyworld2"
ANNOTATION_ROOT = BASELINES_ROOT / "annotations/table4/hyworld2"
MODEL = "Qwen/Qwen3-VL-8B-Instruct"
RATING_SOURCE = "aqs_vlm_qwen3_vl_8b_three_pass"
PASS_SEEDS = (102, 203, 304)
SELECTED_ANCHORS = (0, 2, 5, 7)
BLIND_SALT = "table4-v1-hyworld2-frozen-before-generation"


def load_adapter():
    path = TABLE4_ROOT / "adapters/hyworld.py"
    spec = importlib.util.spec_from_file_location("table4_aqs_adapter", path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_adapter()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        "".join(
            json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
        ),
        encoding="utf-8",
    )
    temporary.replace(path)


def atomic_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def experiment_root(phase: str) -> Path:
    return HY.PILOT_DATA_ROOT if phase == "pilot" else HY.DATA_ROOT


def expected_pairs(phase: str) -> list[tuple[dict[str, Any], int, Path]]:
    indices = set(HY.PILOT_SPEC_INDICES if phase == "pilot" else range(25))
    seeds = HY.PHASE_SEEDS[phase]
    root = experiment_root(phase)
    return [
        (spec, seed, HY.pair_root(root, spec["spec_id"], seed))
        for spec in HY.load_pair_specs()
        if spec["spec_index"] in indices
        for seed in seeds
    ]


def blind_id(spec_id: str, seed: int, phase: str) -> str:
    payload = f"{BLIND_SALT}|{phase}|{spec_id}|{seed}".encode("utf-8")
    return "P-" + hashlib.sha256(payload).hexdigest()[:12].upper()


def side_state(side_root: Path) -> str:
    if (side_root / "SUCCESS").is_file():
        return "success"
    if (side_root / "RENDER_QUALITY_FAILURE").is_file():
        return "render_quality_failure"
    manifest = side_root / "run_manifest.json"
    if manifest.is_file():
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        reason = payload.get("failure_reason")
        if reason:
            return str(reason)
    return "incomplete"


def matrix_audit(phase: str, require_terminal: bool = False) -> dict[str, Any]:
    rows = []
    for spec, seed, root in expected_pairs(phase):
        states = {side: side_state(root / side) for side in ("exterior", "interior")}
        pair_success = all(value == "success" for value in states.values())
        terminal = all(value != "incomplete" for value in states.values())
        rows.append(
            {
                "pair_id": f"{spec['spec_id']}__seed_{seed}",
                "spec_id": spec["spec_id"],
                "logical_seed": seed,
                "sides": states,
                "pair_success": pair_success,
                "terminal": terminal,
            }
        )
    report = {
        "schema_version": "table4-hyworld2-matrix-audit-v1",
        "phase": phase,
        "expected_pairs": len(rows),
        "expected_side_runs": 2 * len(rows),
        "terminal_pairs": sum(row["terminal"] for row in rows),
        "successful_pairs": sum(row["pair_success"] for row in rows),
        "successful_side_runs": sum(
            value == "success" for row in rows for value in row["sides"].values()
        ),
        "audited_at_utc": utc_now(),
        "rows": rows,
    }
    output = RESULT_ROOT / phase / "matrix_audit.json"
    atomic_json(output, report)
    if require_terminal and report["terminal_pairs"] != report["expected_pairs"]:
        raise RuntimeError(
            f"Table 4 {phase} matrix is not terminal: "
            f"{report['terminal_pairs']}/{report['expected_pairs']} pairs"
        )
    return report


def _font(size: int):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
        )
    except OSError:
        return ImageFont.load_default()


def make_pair_montage(pair_root: Path, output: Path, item_id: str) -> str:
    selected: list[tuple[str, Path]] = []
    for side in ("exterior", "interior"):
        anchors = sorted((pair_root / side / "renders/anchors").glob("rgb_*.png"))
        if len(anchors) != 8:
            raise ValueError(
                f"Expected 8 {side} anchors under {pair_root}, found {len(anchors)}"
            )
        selected.extend((side, anchors[index]) for index in SELECTED_ANCHORS)
    tile_width, tile_height = 480, 270
    header_height, row_label_height = 48, 34
    canvas = Image.new(
        "RGB",
        (tile_width * 4, header_height + 2 * (row_label_height + tile_height)),
        "white",
    )
    draw = ImageDraw.Draw(canvas)
    draw.text((16, 10), f"Anonymous pair {item_id}", fill="black", font=_font(24))
    for row, side in enumerate(("EXTERIOR", "INTERIOR")):
        y = header_height + row * (row_label_height + tile_height)
        draw.rectangle(
            (0, y, tile_width * 4, y + row_label_height), fill=(235, 235, 235)
        )
        draw.text((16, y + 4), side, fill="black", font=_font(20))
    for index, (side, path) in enumerate(selected):
        row, col = divmod(index, 4)
        with Image.open(path) as source:
            tile = source.convert("RGB")
            tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            background = Image.new("RGB", (tile_width, tile_height), (30, 30, 30))
            background.paste(
                tile, ((tile_width - tile.width) // 2, (tile_height - tile.height) // 2)
            )
        x = col * tile_width
        y = header_height + row * (row_label_height + tile_height) + row_label_height
        canvas.paste(background, (x, y))
        draw.rectangle((x + 6, y + 5, x + 48, y + 34), fill="black")
        draw.text((x + 13, y + 6), str(col + 1), fill="white", font=_font(18))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jpg.tmp")
    canvas.save(temporary, format="JPEG", quality=92, subsampling=0)
    temporary.replace(output)
    return sha256_file(output)


def build_evidence(phase: str, require_terminal: bool = True) -> dict[str, Any]:
    audit = matrix_audit(phase, require_terminal=require_terminal)
    audit_by_id = {row["pair_id"]: row for row in audit["rows"]}
    package = ANNOTATION_ROOT / phase
    private_rows = []
    public_rows = []
    for spec, seed, root in expected_pairs(phase):
        pair_id = f"{spec['spec_id']}__seed_{seed}"
        state = audit_by_id[pair_id]
        item_id = blind_id(spec["spec_id"], seed, phase)
        montage = package / "montages" / f"{item_id}.jpg"
        montage_hash = None
        if state["pair_success"]:
            montage_hash = make_pair_montage(root, montage, item_id)
            public_rows.append(
                {
                    "blind_id": item_id,
                    "target_function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "required_zones_json": json.dumps(
                        spec["interior_program"]["required_zones"], ensure_ascii=False
                    ),
                    "required_objects_json": json.dumps(
                        spec["interior_program"]["required_objects"], ensure_ascii=False
                    ),
                    "visual_inheritance_json": json.dumps(
                        spec["visual_inheritance"], ensure_ascii=False
                    ),
                    "montage": str(montage.relative_to(package)),
                    "montage_sha256": montage_hash,
                }
            )
        private_rows.append(
            {
                "blind_id": item_id,
                "pair_id": pair_id,
                "spec_id": spec["spec_id"],
                "logical_seed": seed,
                "pair_root": str(root),
                "pair_success": state["pair_success"],
                "side_states": state["sides"],
                "montage_sha256": montage_hash,
            }
        )
    package.mkdir(parents=True, exist_ok=True)
    atomic_json(package / "PRIVATE_blind_map.json", {"items": private_rows})
    fields = [
        "blind_id",
        "target_function",
        "visual_theme",
        "required_zones_json",
        "required_objects_json",
        "visual_inheritance_json",
        "montage",
        "montage_sha256",
    ]
    atomic_csv(package / "items.csv", fields, public_rows)
    provenance = {
        "schema_version": "table4-aqs-evidence-v1",
        "phase": phase,
        "planned_pairs": len(private_rows),
        "scorable_pairs": len(public_rows),
        "method_blinded": True,
        "selected_anchor_indices_per_side": list(SELECTED_ANCHORS),
        "views_per_pair": 8,
        "layout": "top row exterior; bottom row interior",
        "created_at_utc": utc_now(),
    }
    atomic_json(package / "EVIDENCE_PROVENANCE.json", provenance)
    return provenance


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def validate_score(data: dict[str, Any]) -> None:
    required = {
        "functional_aqs",
        "visual_aqs",
        "functional_evidence",
        "visual_evidence",
    }
    if set(data) != required:
        raise ValueError(f"AQS response keys differ from frozen schema: {sorted(data)}")
    for key in ("functional_aqs", "visual_aqs"):
        if type(data[key]) is not int or not 1 <= data[key] <= 10:
            raise ValueError(f"{key} must be an integer in 1..10")
    for key in ("functional_evidence", "visual_evidence"):
        if not isinstance(data[key], str) or not data[key].strip():
            raise ValueError(f"{key} must be non-empty")


def request_score(port: int, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=600) as response:
        return json.load(response)


def score_evidence(phase: str, port: int) -> dict[str, Any]:
    matrix_audit(phase, require_terminal=True)
    package = ANNOTATION_ROOT / phase
    items = _read_csv(package / "items.csv")
    private = json.loads(
        (package / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    if len(private) != (10 if phase == "pilot" else 100):
        raise ValueError("Anonymous package does not cover the planned matrix")
    prompt_template = (
        (
            PROTOCOL_ROOT
            / "../../methods/hyworld/protocol/unified/native/hyworld2_aqs_prompt.txt"
        )
    ).read_text(encoding="utf-8")
    prompt_hash = sha256_bytes(prompt_template.encode("utf-8"))
    model_manifest = (
        BASELINES_ROOT / "hyworld2_runtime/manifests/qwen3_vl_8b_modelscope.json"
    )
    model_manifest_hash = sha256_file(model_manifest)
    completed = 0
    for item in sorted(items, key=lambda row: row["blind_id"]):
        item_id = item["blind_id"]
        image_path = package / item["montage"]
        image_bytes = image_path.read_bytes()
        if sha256_bytes(image_bytes) != item["montage_sha256"]:
            raise RuntimeError(f"Evidence hash changed: {image_path}")
        context = {
            "target_function": item["target_function"],
            "required_interior_zones": json.loads(item["required_zones_json"]),
            "required_large_objects": json.loads(item["required_objects_json"]),
            "visual_theme": item["visual_theme"],
            "visual_inheritance_facts": json.loads(item["visual_inheritance_json"]),
        }
        prompt = (
            prompt_template
            + "\nFrozen pair specification:\n"
            + json.dumps(context, ensure_ascii=False, sort_keys=True)
        )
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,"
                + base64.b64encode(image_bytes).decode("ascii")
            },
        }
        for pass_index, seed in enumerate(PASS_SEEDS, 1):
            settings = {
                "model": MODEL,
                "temperature": 0,
                "top_p": 1,
                "seed": seed,
                "max_tokens": 1024,
                "response_format": {"type": "json_object"},
            }
            signature = sha256_bytes(
                json.dumps(
                    {
                        "settings": settings,
                        "prompt_sha256": prompt_hash,
                        "context": context,
                        "image_sha256": item["montage_sha256"],
                        "model_manifest_sha256": model_manifest_hash,
                    },
                    sort_keys=True,
                ).encode("utf-8")
            )
            output = package / "raw" / item_id / f"pass_{pass_index:02d}.json"
            if output.is_file():
                record = json.loads(output.read_text(encoding="utf-8"))
                if record.get("input_signature") != signature:
                    raise RuntimeError(f"Refusing to reuse changed AQS input: {output}")
                validate_score(record["parsed"])
                continue
            payload = {
                **settings,
                "messages": [
                    {
                        "role": "user",
                        "content": [{"type": "text", "text": prompt}, image_content],
                    }
                ],
            }
            errors = []
            for attempt in range(1, 4):
                raw = request_score(port, payload)
                attempt_path = (
                    output.parent
                    / "attempts"
                    / f"pass_{pass_index:02d}_{attempt:02d}.json"
                )
                atomic_json(
                    attempt_path,
                    {
                        "input_signature": signature,
                        "attempt": attempt,
                        "created_at_utc": utc_now(),
                        "raw_response": raw,
                    },
                )
                try:
                    parsed = json.loads(raw["choices"][0]["message"]["content"])
                    validate_score(parsed)
                except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                    errors.append(repr(exc))
                    continue
                atomic_json(
                    output,
                    {
                        "rating_source": RATING_SOURCE,
                        "human_raters": 0,
                        "pass_index": pass_index,
                        "input_signature": signature,
                        "settings": settings,
                        "prompt_sha256": prompt_hash,
                        "context": context,
                        "image_sha256": item["montage_sha256"],
                        "model_manifest_sha256": model_manifest_hash,
                        "created_at_utc": utc_now(),
                        "parsed": parsed,
                        "raw_response": raw,
                    },
                )
                break
            else:
                raise RuntimeError(
                    f"Three schema-parse attempts failed for {item_id}: {errors}"
                )
        completed += 1
        print(f"TABLE4_AQS_SCORED {completed}/{len(items)} item={item_id}", flush=True)
    provenance = {
        "schema_version": "table4-aqs-vlm-provenance-v1",
        "phase": phase,
        "rating_source": RATING_SOURCE,
        "model": MODEL,
        "model_manifest_sha256": model_manifest_hash,
        "prompt_sha256": prompt_hash,
        "temperature": 0,
        "pass_seeds": list(PASS_SEEDS),
        "passes_per_pair": 3,
        "scored_pairs": len(items),
        "human_raters": 0,
        "independent_human_ratings": False,
        "limitations": "Three deterministic calls of one local VLM are not independent human ratings.",
        "completed_at_utc": utc_now(),
    }
    atomic_json(package / "AQS_PROVENANCE.json", provenance)
    return provenance


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    fraction = position - low
    return ordered[low] * (1 - fraction) + ordered[high] * fraction


def aggregate(phase: str) -> dict[str, Any]:
    audit = matrix_audit(phase, require_terminal=True)
    package = ANNOTATION_ROOT / phase
    provenance_path = package / "AQS_PROVENANCE.json"
    if not provenance_path.is_file():
        raise RuntimeError("Run the frozen AQS scorer before aggregation")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    if (
        provenance.get("rating_source") != RATING_SOURCE
        or provenance.get("human_raters") != 0
    ):
        raise ValueError("Unexpected AQS source provenance")
    audit_by_id = {row["pair_id"]: row for row in audit["rows"]}
    rows: list[dict[str, Any]] = []
    for spec, seed, root in expected_pairs(phase):
        pair_id = f"{spec['spec_id']}__seed_{seed}"
        state = audit_by_id[pair_id]
        item_id = blind_id(spec["spec_id"], seed, phase)
        if state["pair_success"]:
            scores = []
            for pass_index in range(1, 4):
                path = package / "raw" / item_id / f"pass_{pass_index:02d}.json"
                if not path.is_file():
                    raise RuntimeError(f"Missing AQS response: {path}")
                record = json.loads(path.read_text(encoding="utf-8"))
                validate_score(record["parsed"])
                scores.append(record["parsed"])
            functional = statistics.fmean(score["functional_aqs"] for score in scores)
            visual = statistics.fmean(score["visual_aqs"] for score in scores)
            source = "measured"
        else:
            functional = visual = 1.0
            source = "itt_failure_value"
            scores = []
        row = {
            "method": "hyworld2",
            "track": "matched_text_independent",
            "pair_id": pair_id,
            "spec_id": spec["spec_id"],
            "spec_index": spec["spec_index"],
            "logical_seed": seed,
            "function": spec["function"],
            "style": spec["visual_theme"],
            "pair_success": state["pair_success"],
            "side_states": state["sides"],
            "functional_aqs": functional,
            "visual_aqs": visual,
            "aqs_source": source,
            "spatial_aqs": None,
            "shape_iou": None,
            "entrance_alignment": None,
            "entrance_passability": None,
            "transition_collision": None,
            "io_connectivity_rate": None,
            "cross_boundary_reachability": None,
            "not_applicable_reason": "N/A-U: native method does not produce a unified paired indoor-outdoor world",
        }
        atomic_json(root / "metrics/per_run.json", row)
        rows.append(row)
    seeds_by_spec: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        seeds_by_spec.setdefault(row["spec_id"], []).append(row)
    spec_means = {
        spec_id: {
            metric: statistics.fmean(row[metric] for row in spec_rows)
            for metric in ("functional_aqs", "visual_aqs")
        }
        for spec_id, spec_rows in seeds_by_spec.items()
    }
    means = {
        metric: statistics.fmean(values[metric] for values in spec_means.values())
        for metric in ("functional_aqs", "visual_aqs")
    }
    rng = random.Random(20260909)
    spec_ids = sorted(spec_means)
    bootstrap = {metric: [] for metric in means}
    for _ in range(10_000):
        sample = [rng.choice(spec_ids) for _ in spec_ids]
        for metric in means:
            bootstrap[metric].append(
                statistics.fmean(spec_means[item][metric] for item in sample)
            )
    metrics = {
        metric: {
            "mean": means[metric],
            "ci95": [
                percentile(bootstrap[metric], 0.025),
                percentile(bootstrap[metric], 0.975),
            ],
            "display": f"{means[metric]:.2f}",
        }
        for metric in means
    }
    summary = {
        "schema_version": "table4-hyworld2-summary-v1",
        "phase": phase,
        "method": "HY-World 2.0",
        "track": "matched_text_independent",
        "planned_pairs": len(rows),
        "successful_pairs": sum(row["pair_success"] for row in rows),
        "pair_success_rate": sum(row["pair_success"] for row in rows) / len(rows),
        "aqs_coverage": sum(row["pair_success"] for row in rows) / len(rows),
        "estimand": "ITT; failed pairs receive AQS=1",
        "metrics": metrics,
        "not_applicable": {
            "spatial_aqs": "N/A-U",
            "shape_iou": "N/A-U",
            "entrance_alignment": "N/A-U",
            "entrance_passability": "N/A-U",
            "transition_collision": "N/A-U",
            "io_connectivity_rate": "N/A-U",
            "cross_boundary_reachability": "N/A-U",
        },
        "bootstrap": {"unit": "spec_id", "replicates": 10_000, "seed": 20260909},
        "rating_source": RATING_SOURCE,
        "human_raters": 0,
        "created_at_utc": utc_now(),
    }
    output_root = RESULT_ROOT / phase
    atomic_jsonl(output_root / "per_run.jsonl", rows)
    atomic_json(output_root / "summary.json", summary)
    atomic_csv(
        output_root / "summary.csv",
        [
            "method",
            "functional_aqs",
            "visual_aqs",
            "spatial_aqs",
            "shape_iou",
            "entrance_alignment",
            "entrance_passability",
            "transition_collision",
            "io_connectivity_rate",
            "cross_boundary_reachability",
            "planned_pairs",
            "successful_pairs",
            "aqs_coverage",
        ],
        [
            {
                "method": "HY-World 2.0",
                "functional_aqs": metrics["functional_aqs"]["display"],
                "visual_aqs": metrics["visual_aqs"]["display"],
                "spatial_aqs": "N/A-U",
                "shape_iou": "N/A-U",
                "entrance_alignment": "N/A-U",
                "entrance_passability": "N/A-U",
                "transition_collision": "N/A-U",
                "io_connectivity_rate": "N/A-U",
                "cross_boundary_reachability": "N/A-U",
                "planned_pairs": len(rows),
                "successful_pairs": sum(row["pair_success"] for row in rows),
                "aqs_coverage": f"{summary['aqs_coverage']:.4f}",
            }
        ],
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("audit", "evidence", "aggregate"):
        child = subparsers.add_parser(action)
        child.add_argument("--phase", choices=("pilot", "formal"), required=True)
    score = subparsers.add_parser("score")
    score.add_argument("--phase", choices=("pilot", "formal"), required=True)
    score.add_argument("--port", type=int, default=18082)
    args = parser.parse_args()
    if args.action == "audit":
        payload = matrix_audit(args.phase)
    elif args.action == "evidence":
        payload = build_evidence(args.phase)
    elif args.action == "score":
        payload = score_evidence(args.phase, args.port)
    else:
        payload = aggregate(args.phase)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

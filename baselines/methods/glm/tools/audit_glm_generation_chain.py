#!/usr/bin/env python3
"""Audit GLM-5.3 Low formal artifacts from frozen inputs to Table 2."""
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
import csv
import hashlib
import itertools
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
from PIL import Image


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str((ROOT / "methods"))]
from baselines.methods.glm.adapter import digest
from baselines.methods.glm.adapter import utc
from baselines.methods.glm.adapter import write_json
from baselines.methods.glm.evaluate import check_consistency

METHOD = "glm_5_3"
MODEL = "glm-5.3"
PROVIDER = "glm-coding-plan"
PRECISION = {
    "qalign": 2,
    "clipiqa_plus": 3,
    "layout_plausibility": 1,
    "prompt_alignment": 1,
    "consistency_3d": 1,
    "appearance_diversity_itt": 3,
    "layout_diversity_itt": 3,
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def close(left: float, right: float) -> bool:
    return (
        math.isfinite(float(left))
        and math.isfinite(float(right))
        and abs(float(left) - float(right)) <= 1e-10
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    args = parser.parse_args()
    domain = args.domain
    lock = json.loads(
        ((ROOT / "methods/glm/protocol/generation/glm_5_3.lock.json")).read_text()
    )
    require(
        lock["method"] == METHOD
        and lock["model"] == MODEL
        and lock["reasoning_effort"] == "low",
        "Wrong formal lock identity",
    )
    for relative, expected_hash in lock["files_sha256"].items():
        require(
            digest(ROOT / relative) == expected_hash,
            "Frozen source changed: " + relative,
        )

    specs = jsonl(ROOT / f"protocol/generation/{domain}_specs.jsonl")
    expected = {(spec["spec_id"], seed) for spec in specs for seed in range(4)}
    data_root = ROOT / "data/table2" / domain / METHOD
    result_root = ROOT / "results/glm_5_3/formal" / domain
    full = json.loads((result_root / "table2_full.json").read_text())
    require(full["method"] == METHOD and full["domain"] == domain, "Foreign summary")

    indexed: dict[str, dict[tuple[str, int], dict]] = {}
    source_hashes: dict[str, str] = {}
    for name, filename in {
        "iqa": "iqa_per_scene.jsonl",
        "consistency": "consistency_per_scene.jsonl",
        "human": "human_per_scene.jsonl",
    }.items():
        path = result_root / filename
        rows = jsonl(path)
        keys = {(row["spec_id"], row["logical_seed"]) for row in rows}
        require(
            len(rows) == 100 and keys == expected, "Incomplete or duplicate " + name
        )
        require(
            all(row["method"] == METHOD and row["domain"] == domain for row in rows),
            "Foreign " + name + " record",
        )
        indexed[name] = {(row["spec_id"], row["logical_seed"]): row for row in rows}
        source_hashes[filename] = digest(path)
    check_consistency(
        list(indexed["consistency"].values()), ROOT / "data/table2", domain
    )

    diversity_path = result_root / "diversity_per_spec.jsonl"
    diversity_rows = jsonl(diversity_path)
    diversity = {row["spec_id"]: row for row in diversity_rows}
    require(
        len(diversity_rows) == 25 and set(diversity) == {s["spec_id"] for s in specs},
        "Wrong diversity coverage",
    )
    source_hashes[diversity_path.name] = digest(diversity_path)

    sampled = set(random.Random(20260917).sample(sorted(expected), 5))
    samples, valid_count = [], 0
    for spec in specs:
        valid_seeds = []
        for seed in range(4):
            key = (spec["spec_id"], seed)
            run = data_root / spec["spec_id"] / f"seed_{seed}"
            manifest_path = run / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            success = (run / "SUCCESS").exists()
            require(
                success == bool(manifest.get("render_success")),
                "SUCCESS mismatch: " + str(run),
            )
            require(
                success or manifest.get("failure_class") == "quality",
                "Unresolved run: " + str(run),
            )
            require(manifest.get("method") == METHOD, "Wrong run method")
            require(manifest.get("model_requested") == MODEL, "Wrong requested model")
            identity = manifest["identity"]
            require(
                identity["spec_sha256"]
                == hashlib.sha256(
                    json.dumps(spec, sort_keys=True).encode()
                ).hexdigest(),
                "Wrong spec identity",
            )
            for field, relative in (
                ("protocol_sha256", "methods/glm/protocol/generation/glm_5_3.json"),
                ("adapter_sha256", "methods/glm/adapter.py"),
                (
                    "prompt_template_sha256",
                    "methods/glm/protocol/generation/glm_5_3_prompt.txt",
                ),
                (
                    "output_schema_sha256",
                    "methods/glm/protocol/generation/glm_5_3_output.schema.json",
                ),
                (
                    "opencode_config_sha256",
                    "methods/glm_flash/runtime/glm53_opencode/opencode.json",
                ),
            ):
                require(
                    identity[field] == lock["files_sha256"][relative],
                    "Stale generation identity",
                )
            native = json.loads((run / "input/native_input.json").read_text())
            require(
                native["model"] == MODEL
                and native["cli_model"] == f"{PROVIDER}/{MODEL}"
                and native["thinking_mode"] == "enabled"
                and native["reasoning_effort"] == "low",
                "Wrong native model controls",
            )
            if manifest.get("generation_success"):
                require(
                    manifest.get("model_returned") == MODEL
                    and manifest.get("provider_returned") == PROVIDER,
                    "Wrong returned model identity",
                )
                successful_attempts = [
                    a for a in manifest["attempts"] if a.get("model_evidence")
                ]
                require(
                    len(successful_attempts) == 1,
                    "Expected one evidenced successful attempt",
                )
                evidence = successful_attempts[0]["model_evidence"]
                require(
                    evidence["providerID"] == PROVIDER and evidence["modelID"] == MODEL,
                    "Wrong OpenCode model evidence",
                )
                require(
                    successful_attempts[0].get("reasoning_effort") == "low",
                    "Wrong effort evidence",
                )
                generated = run / "scene/generated.py"
                require(
                    digest(generated) == manifest["generated_code_sha256"],
                    "Generated code drift",
                )

            iqa, consistency, human = (
                indexed["iqa"][key],
                indexed["consistency"][key],
                indexed["human"][key],
            )
            require(
                human.get("rating_source") == "synthetic_proxy_three_profiles",
                "Wrong rating source",
            )
            require(human.get("success") == success, "Subjective success mismatch")
            require(
                iqa == json.loads((run / "metrics/iqa.json").read_text()),
                "IQA source mismatch",
            )
            require(
                consistency
                == json.loads((run / "metrics/consistency_3d.json").read_text()),
                "Consistency source mismatch",
            )
            if success:
                valid_count += 1
                valid_seeds.append(seed)
                require(
                    iqa.get("success") and len(iqa.get("views", [])) == 8,
                    "Incomplete IQA",
                )
                for metric in ("qalign", "clipiqa_plus"):
                    require(
                        close(iqa[metric], sum(v[metric] for v in iqa["views"]) / 8),
                        "IQA averaging mismatch",
                    )
                require(
                    human.get("rater_count") == 3,
                    "Successful proxy row needs three profiles",
                )
                validation = json.loads((run / "validation.json").read_text())
                require(
                    validation.get("valid") and len(validation.get("images", [])) == 58,
                    "Invalid render validation",
                )
                for kind, count, resolution in (
                    ("anchors", 8, (1280, 720)),
                    ("sequence", 50, (512, 512)),
                ):
                    images = sorted((run / "renders" / kind).glob("rgb_*.png"))
                    require(len(images) == count, "Wrong render count")
                    for image_path in images:
                        with Image.open(image_path) as image:
                            require(image.size == resolution, "Wrong render resolution")
                            image.verify()
            else:
                require(
                    not iqa.get("success")
                    and iqa["qalign"] == 1
                    and iqa["clipiqa_plus"] == 0,
                    "Wrong failed IQA lower bound",
                )
                require(
                    not consistency.get("success")
                    and consistency["consistency_3d"] == 0,
                    "Wrong failed consistency lower bound",
                )
                require(
                    human["layout_plausibility"]
                    == human["prompt_alignment"]
                    == human["rater_count"]
                    == 0,
                    "Wrong failed subjective lower bound",
                )

            if key in sampled:
                paths = [
                    manifest_path,
                    run / "input/spec.json",
                    run / "input/native_input.json",
                    run / "metrics/iqa.json",
                    run / "metrics/consistency_3d.json",
                ]
                if manifest.get("generation_success"):
                    paths.append(run / "scene/generated.py")
                if success:
                    paths.extend(
                        [
                            run / "SUCCESS",
                            run / "validation.json",
                            run / "scene/scene.blend",
                        ]
                    )
                    paths.extend(sorted((run / "renders/anchors").glob("rgb_*.png")))
                    paths.extend(sorted((run / "renders/sequence").glob("rgb_*.png")))
                samples.append(
                    {
                        "spec_id": spec["spec_id"],
                        "logical_seed": seed,
                        "success": success,
                        "files_sha256": {
                            str(path.relative_to(ROOT)): digest(path) for path in paths
                        },
                    }
                )

        record = diversity[spec["spec_id"]]
        require(
            record["method"] == METHOD and record["domain"] == domain,
            "Foreign diversity row",
        )
        require(record["valid_seeds"] == valid_seeds, "Diversity valid-seed mismatch")
        pairs = list(itertools.combinations(valid_seeds, 2))
        require(
            [tuple(pair["seeds"]) for pair in record["pairs"]] == pairs,
            "Diversity pair mismatch",
        )
        penalty = (len(valid_seeds) / 4) ** 2
        require(close(record["itt_penalty"], penalty), "Diversity ITT penalty mismatch")
        for raw_name, metric in (
            ("appearance", "appearance_diversity_itt"),
            ("layout", "layout_diversity_itt"),
        ):
            raw_mean = (
                sum(pair[raw_name] for pair in record["pairs"]) / len(pairs)
                if pairs
                else 0
            )
            require(close(record[metric], raw_mean * penalty), "Diversity ITT mismatch")

    display_rows = list(csv.DictReader((result_root / "table2.csv").open()))
    require(len(display_rows) == 1, "Wrong display row count")
    display = display_rows[0]
    require(
        display["method"] == METHOD and display["domain"] == domain,
        "Foreign display row",
    )
    for metric, precision in PRECISION.items():
        values = []
        for spec in specs:
            spec_id = spec["spec_id"]
            if metric in ("qalign", "clipiqa_plus"):
                values.append(
                    sum(indexed["iqa"][(spec_id, seed)][metric] for seed in range(4))
                    / 4
                )
            elif metric == "consistency_3d":
                values.append(
                    sum(
                        indexed["consistency"][(spec_id, seed)][metric]
                        for seed in range(4)
                    )
                    / 4
                )
            elif metric in ("layout_plausibility", "prompt_alignment"):
                values.append(
                    sum(indexed["human"][(spec_id, seed)][metric] for seed in range(4))
                    / 4
                )
            else:
                values.append(diversity[spec_id][metric])
        array = np.asarray(values)
        summary = full["metrics"][metric]
        require(
            summary["status"] == "complete" and close(summary["mean"], array.mean()),
            "Final mean mismatch: " + metric,
        )
        indices = np.random.default_rng(20260827).integers(0, 25, size=(10000, 25))
        ci = np.quantile(array[indices].mean(axis=1), (0.025, 0.975))
        require(
            all(close(left, right) for left, right in zip(summary["ci95"], ci)),
            "Bootstrap mismatch: " + metric,
        )
        require(
            display[metric] == f"{summary['mean']:.{precision}f}",
            "Display rounding mismatch: " + metric,
        )
    require(
        full["bootstrap"] == {"unit": "spec_id", "replicates": 10000, "seed": 20260827},
        "Bootstrap drift",
    )
    require(
        full["run_audit"]["render_success_count"] == valid_count, "Valid-count mismatch"
    )
    require(
        display["render_success_rate"] == f"{valid_count / 100:.4f}",
        "Success-rate mismatch",
    )

    provenance_path = (
        ROOT / "annotations/glm_5_3" / domain / "SYNTHETIC_RATING_PROVENANCE.json"
    )
    provenance = json.loads(provenance_path.read_text())
    require(
        provenance.get("human_raters") == 0
        and provenance.get("independent_human_ratings") is False,
        "False human-rating provenance",
    )
    source_hashes.update(
        {
            name: digest(result_root / name)
            for name in ("table2_full.json", "table2.csv")
        }
    )
    report = {
        "verified_at_utc": utc(),
        "status": "full_chain_passed",
        "method": METHOD,
        "model": MODEL,
        "reasoning_effort": "low",
        "domain": domain,
        "expected_runs": 100,
        "valid_runs": valid_count,
        "quality_failures": 100 - valid_count,
        "sample_seed": 20260917,
        "sample_count": len(samples),
        "samples": samples,
        "summary_sources_sha256": source_hashes,
        "provenance_sha256": digest(provenance_path),
        "display_row": display,
        "real_human_raters": 0,
    }
    output = ROOT / "results/glm_5_3" / f"chain_audit_{domain}.json"
    write_json(output, report)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "samples"}, indent=2
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

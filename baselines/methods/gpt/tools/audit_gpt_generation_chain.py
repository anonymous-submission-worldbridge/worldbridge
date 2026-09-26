"""Audit completed automatic columns and a fixed 5% raw-to-table sample.

This report does not generate or substitute human ratings and never changes the
frozen experiment sources, renders, or metric values.
"""

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
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.evaluate import check_consistency_records

PRECISION = {
    "qalign": 2,
    "clipiqa_plus": 3,
    "consistency_3d": 1,
    "appearance_diversity_itt": 3,
    "layout_diversity_itt": 3,
}


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def close(a, b):
    return (
        math.isfinite(float(a))
        and math.isfinite(float(b))
        and abs(float(a) - float(b)) <= 1e-10
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    args = parser.parse_args()
    domain = args.domain
    lock = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json")).read_text()
    )
    for path, expected in lock["files_sha256"].items():
        require(digest(ROOT / path) == expected, "Frozen source drift: " + path)
    specs = jsonl(ROOT / ("protocol/" + domain + "_specs.jsonl"))
    expected = {(s["spec_id"], seed) for s in specs for seed in range(4)}
    result_root = ROOT / "results/gpt6_astra/formal" / domain
    full = json.loads((result_root / "table2_full.json").read_text())
    require(
        full["method"] == "gpt6_astra" and full["domain"] == domain,
        "Foreign final summary",
    )
    sources, indexed = {}, {}
    for name, filename in [
        ("iqa", "iqa_per_scene.jsonl"),
        ("consistency", "consistency_per_scene.jsonl"),
    ]:
        path = result_root / filename
        rows = jsonl(path)
        actual = {(r["spec_id"], r["logical_seed"]) for r in rows}
        require(
            len(rows) == 100 and actual == expected,
            "Missing or duplicate " + name + " records",
        )
        require(
            all(r["method"] == "gpt6_astra" and r["domain"] == domain for r in rows),
            "Foreign metric records",
        )
        indexed[name] = {(r["spec_id"], r["logical_seed"]): r for r in rows}
        sources[filename] = digest(path)
    check_consistency_records(
        list(indexed["consistency"].values()), ROOT / "data/table2", domain
    )
    diversity_rows = jsonl(result_root / "diversity_per_spec.jsonl")
    require(
        len(diversity_rows) == 25
        and {r["spec_id"] for r in diversity_rows} == {s["spec_id"] for s in specs},
        "Bad diversity matrix",
    )
    diversity = {r["spec_id"]: r for r in diversity_rows}
    sources["diversity_per_spec.jsonl"] = digest(
        result_root / "diversity_per_spec.jsonl"
    )
    sampled = set(random.Random(20260909).sample(sorted(expected), 5))
    samples, valid_count = [], 0
    for spec in specs:
        sid = spec["spec_id"]
        valid_seeds = []
        for seed in range(4):
            key = (sid, seed)
            run = (
                ROOT
                / "data/table2"
                / domain
                / "gpt6_astra"
                / sid
                / ("seed_" + str(seed))
            )
            m = json.loads((run / "run_manifest.json").read_text())
            success = (run / "SUCCESS").exists()
            require(
                success == bool(m.get("render_success")),
                "SUCCESS/manifest disagreement: " + str(run),
            )
            require(
                success or m.get("failure_class") == "quality",
                "Unresolved non-quality run",
            )
            require(m["model_requested"] == "gpt-6-astra", "Wrong requested model")
            require(
                m["identity"]["spec_sha256"]
                == hashlib.sha256(
                    json.dumps(spec, sort_keys=True).encode()
                ).hexdigest(),
                "Wrong spec identity",
            )
            for field, source in [
                ("protocol_sha256", "methods/gpt/protocol/generation/gpt6_astra.json"),
                ("adapter_sha256", "methods/gpt/adapter.py"),
                (
                    "prompt_template_sha256",
                    "methods/gpt/protocol/generation/gpt6_astra_prompt.txt",
                ),
            ]:
                require(
                    m["identity"][field] == lock["files_sha256"][source],
                    "Stale generation identity",
                )
            q, c = indexed["iqa"][key], indexed["consistency"][key]
            require(
                q == json.loads((run / "metrics/iqa.json").read_text()),
                "Per-run IQA differs from JSONL",
            )
            require(
                c == json.loads((run / "metrics/consistency_3d.json").read_text()),
                "Per-run consistency differs from JSONL",
            )
            if success:
                valid_count += 1
                valid_seeds.append(seed)
                require(q["success"] and len(q["views"]) == 8, "Incomplete IQA views")
                require(
                    [v["view_index"] for v in q["views"]] == list(range(8)),
                    "IQA view index mismatch",
                )
                for metric in ("qalign", "clipiqa_plus"):
                    require(
                        close(q[metric], sum(v[metric] for v in q["views"]) / 8),
                        "IQA averaging mismatch",
                    )
                if c["success"]:
                    raw, low, high = (
                        c["raw_reprojection_error"],
                        c["empirical_min"],
                        c["empirical_max"],
                    )
                    require(
                        close(
                            c["consistency_3d"],
                            100 * (1 - (min(high, max(low, raw)) - low) / (high - low)),
                        ),
                        "WorldScore normalization mismatch",
                    )
            else:
                require(
                    not q["success"]
                    and q["qalign"] == 1
                    and q["clipiqa_plus"] == 0
                    and not q["views"],
                    "Wrong quality-failure IQA bounds",
                )
                require(
                    not c["success"] and c["consistency_3d"] == 0,
                    "Wrong quality-failure consistency bound",
                )
            if key not in sampled:
                continue
            evidence = {
                "spec_id": sid,
                "logical_seed": seed,
                "success": success,
                "failure_reason": m.get("failure_reason"),
                "files_sha256": {},
            }
            paths = [
                run / "run_manifest.json",
                run / "input/spec.json",
                run / "input/native_input.json",
                run / "metrics/iqa.json",
                run / "metrics/consistency_3d.json",
            ]
            for attempt in m["attempts"]:
                folder = run / ("logs/generation_%02d" % attempt["index"])
                paths.extend(
                    p
                    for p in (
                        folder / "events.jsonl",
                        folder / "stderr.log",
                        folder / "response.json",
                    )
                    if p.exists()
                )
            if m.get("generation_success"):
                code = run / "scene/generated.py"
                require(
                    digest(code) == m["generated_code_sha256"], "Generated code changed"
                )
                response = json.loads(
                    (
                        run
                        / (
                            "logs/generation_%02d/response.json"
                            % m["attempts"][-1]["index"]
                        )
                    ).read_text()
                )
                require(
                    code.read_text() == response["code"] + "\n",
                    "Raw response/code mismatch",
                )
                paths.append(code)
            if success:
                require(
                    m["renderer_sha256"]
                    == lock["files_sha256"]["methods/gpt/tools/blender_render_gpt.py"],
                    "Stale renderer",
                )
                validation = json.loads((run / "validation.json").read_text())
                require(
                    validation["valid"] and len(validation["images"]) == 58,
                    "Incomplete render validation",
                )
                for kind, count, resolution in [
                    ("anchors", 8, (1280, 720)),
                    ("sequence", 50, (512, 512)),
                ]:
                    images = sorted((run / "renders" / kind).glob("rgb_*.png"))
                    require(len(images) == count, "Wrong RGB count")
                    for path in images:
                        with Image.open(path) as image:
                            require(image.size == resolution, "Wrong RGB resolution")
                            image.verify()
                    paths.extend(images)
                require(
                    {v["image"] for v in q["views"]}
                    == {"renders/anchors/rgb_%03d.png" % n for n in range(8)},
                    "Wrong IQA input paths",
                )
                semantics = sorted(
                    (run / "renders/semantic_pred").glob("semantic_*.png")
                )
                require(len(semantics) == 8, "Incomplete semantic inputs")
                paths.extend(semantics)
                paths.extend(
                    [
                        run / "SUCCESS",
                        run / "validation.json",
                        run / "scene/scene.blend",
                        run / "renders/sequence/cameras.json",
                        run / "logs/worldscore.log",
                    ]
                )
            evidence["files_sha256"] = {
                str(p.relative_to(ROOT)): digest(p) for p in paths
            }
            samples.append(evidence)
        d = diversity[sid]
        require(
            d["method"] == "gpt6_astra" and d["domain"] == domain,
            "Foreign diversity record",
        )
        require(
            d["valid_seeds"] == valid_seeds, "Diversity uses wrong successful seeds"
        )
        pairs = list(itertools.combinations(valid_seeds, 2))
        require(
            [tuple(p["seeds"]) for p in d["pairs"]] == pairs
            and d["valid_pair_count"] == len(pairs),
            "Wrong diversity pair set",
        )
        penalty = (len(valid_seeds) / 4) ** 2
        require(close(d["itt_penalty"], penalty), "Wrong ITT diversity penalty")
        for kind, metric in [
            ("appearance", "appearance_diversity_itt"),
            ("layout", "layout_diversity_itt"),
        ]:
            mean = sum(p[kind] for p in d["pairs"]) / len(pairs) if pairs else 0
            require(close(d[metric], mean * penalty), "Diversity pair/ITT mismatch")
    csv_rows = list(csv.DictReader((result_root / "table2.csv").open()))
    require(len(csv_rows) == 1, "Wrong CSV row count")
    csv_row = csv_rows[0]
    require(
        csv_row["method"] == "gpt6_astra" and csv_row["domain"] == domain,
        "Foreign CSV row",
    )
    for metric, precision in PRECISION.items():
        values = []
        for spec in specs:
            sid = spec["spec_id"]
            if metric in ("qalign", "clipiqa_plus", "consistency_3d"):
                source = "consistency" if metric == "consistency_3d" else "iqa"
                values.append(
                    sum(indexed[source][(sid, seed)][metric] for seed in range(4)) / 4
                )
            else:
                values.append(diversity[sid][metric])
        array = np.asarray(values)
        require(np.isfinite(array).all(), "Non-finite summary input")
        summary = full["metrics"][metric]
        require(
            summary["status"] == "complete" and close(summary["mean"], array.mean()),
            "Final mean mismatch",
        )
        require(
            full["bootstrap"]
            == {"unit": "spec_id", "replicates": 10000, "seed": 20260827},
            "Bootstrap settings changed",
        )
        indices = np.random.default_rng(20260827).integers(0, 25, size=(10000, 25))
        ci = np.quantile(array[indices].mean(axis=1), [0.025, 0.975])
        require(
            all(close(a, b) for a, b in zip(summary["ci95"], ci)),
            "Bootstrap CI mismatch",
        )
        require(
            csv_row[metric] == format(summary["mean"], "." + str(precision) + "f"),
            "Displayed CSV rounding mismatch",
        )
    require(
        full["run_audit"]["render_success_count"] == valid_count,
        "Summary success count mismatch",
    )
    require(
        csv_row["render_success_rate"] == format(valid_count / 100, ".4f"),
        "CSV success rate mismatch",
    )
    sources.update(
        {
            name: digest(result_root / name)
            for name in ("table2_full.json", "table2.csv")
        }
    )
    report = {
        "verified_at_utc": utc(),
        "domain": domain,
        "method": "gpt6_astra",
        "status": "automatic_chain_passed",
        "expected_runs": 100,
        "valid_runs": valid_count,
        "sample_seed": 20260909,
        "sample_fraction": 0.05,
        "sample_count": len(samples),
        "samples": samples,
        "summary_sources_sha256": sources,
        "display_row": csv_row,
        "human_metrics": {
            k: full["metrics"][k]["status"]
            for k in ("layout_plausibility", "prompt_alignment")
        },
        "note": "Automatic numerical/provenance audit only; not real human rating evidence.",
    }
    write_json(
        ROOT / "results/gpt6_astra" / ("chain_audit_" + domain + ".json"), report
    )
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "samples"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()

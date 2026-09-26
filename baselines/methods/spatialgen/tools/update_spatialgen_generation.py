#!/usr/bin/env python3
"""Reaggregate reviewed SpatialGen proxies and update Table 2 reproducibly.

Run the strict rating importer first. Preserve the archived formal run audit and
all five automatic metrics; use the shared spec bootstrap for the two ratings.
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


import csv
import hashlib
import io
import json
import re
import sys
from pathlib import Path

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASE))
from metrics.aggregate_table2 import (
    METRIC_COLUMNS,
    DISPLAY_PRECISION,
    bootstrap_summary,
    group_scene_metric,
)
import numpy as np

RESULTS = BASE / "results/spatialgen/indoor"
PACKAGE = BASE / "annotations/spatialgen/indoor"
DOCUMENT = BASE / "Comparison Experiment - Table 2.md"
SOURCE = "synthetic_proxy_three_profiles"
PREVIOUS = BASE / "results/spatialgen/rating_revision_20260907/previous"
SUBJECTIVE = ("layout_plausibility", "prompt_alignment")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_write(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def main():
    full = json.loads((RESULTS / "table2_full.json").read_text())
    previous = json.loads(
        (PREVIOUS / "results/spatialgen/indoor/table2_full.json").read_text()
    )
    assert full["method"] == "spatialgen" and full["domain"] == "indoor"
    assert full["run_audit"] == previous["run_audit"]
    for field in (
        "expected_runs",
        "manifest_count",
        "generation_success_count",
        "render_success_count",
    ):
        assert full["run_audit"][field] == 100
    for name in set(METRIC_COLUMNS) - set(SUBJECTIVE):
        assert full["metrics"][name] == previous["metrics"][name]
    assert full["bootstrap"] == {
        "unit": "spec_id",
        "replicates": 10000,
        "seed": 20260827,
    }

    # Formal files were archived on 2026-09-07. Verify inventory coverage, retain
    # the completed pre-archive audit rather than reclassifying missing files.
    inventory = (
        BASE / "archives/table2_completed_20260907/spatialgen_indoor.members.txt"
    )
    members = set(inventory.read_text().splitlines())
    manifests = full["run_audit"]["manifests"]
    assert len(set(manifests)) == 100
    assert all(
        path in members and str(Path(path).parent / "SUCCESS") in members
        for path in manifests
    )

    provenance_path = PACKAGE / "SYNTHETIC_RATING_PROVENANCE.json"
    provenance = json.loads(provenance_path.read_text())
    assert provenance["import_rating_source"] == SOURCE
    assert provenance["human_raters"] == 0 and provenance["scored_scenes"] == 100
    assert provenance["scorer_sha256"] == digest(
        (BASE / "methods/spatialgen/tools/fill_simulated_spatialgen_ratings.py")
    )
    assert provenance["profile_implementation_sha256"] == digest(
        (BASE / "methods/worldgen/tools/fill_simulated_worldgen_ratings.py")
    )
    assert provenance["items_sha256"] == digest(PACKAGE / "items.csv")
    for name, expected in provenance["outputs_sha256"].items():
        assert digest(PACKAGE / name) == expected
    records = [
        json.loads(line)
        for line in (RESULTS / "human_per_scene.jsonl").read_text().splitlines()
    ]
    assert len(records) == 100
    assert all(
        row["method"] == "spatialgen"
        and row["domain"] == "indoor"
        and row["success"]
        and row["rater_count"] == 3
        and row["rating_source"] == SOURCE
        for row in records
    )
    expected_keys = {
        (r["spec_id"], r["logical_seed"], r["blind_id"])
        for r in provenance["decisions"]
    }
    assert {
        (r["spec_id"], r["logical_seed"], r["blind_id"]) for r in records
    } == expected_keys
    # Check the imported values against the reviewed profiles, not just labels.
    by_blind = {r["blind_id"]: r for r in records}
    with (PACKAGE / "items.csv").open() as handle:
        fact_counts = {
            r["blind_id"]: int(r["fact_count"]) for r in csv.DictReader(handle)
        }
    from tools.fill_simulated_worldgen_ratings import layout_for_profile

    for d in provenance["decisions"]:
        r = by_blind[d["blind_id"]]
        layout = [
            25
            * (
                sum(layout_for_profile(d["neutral_layout"], d["item_number"], i)) / 4
                - 1
            )
            for i in range(3)
        ]
        prompt = [
            100
            * (
                len(d["clear_yes_fact_indices"])
                + (len(d["borderline_fact_indices"]) if i == 2 else 0)
            )
            / fact_counts[d["blind_id"]]
            for i in range(3)
        ]
        assert np.allclose(r["layout_per_rater"], layout, atol=1e-12, rtol=0)
        assert np.allclose(r["prompt_per_rater"], prompt, atol=1e-12, rtol=0)
        assert abs(r["layout_plausibility"] - np.mean(layout)) < 1e-12
        assert abs(r["prompt_alignment"] - np.mean(prompt)) < 1e-12
    spec_ids = [
        json.loads(line)["spec_id"]
        for line in ((BASE / "protocol/generation/indoor_specs.jsonl"))
        .read_text()
        .splitlines()
        if line.strip()
    ]
    assert len(spec_ids) == 25
    assert {(r["spec_id"], r["logical_seed"]) for r in records} == {
        (s, seed) for s in spec_ids for seed in range(4)
    }
    for name in SUBJECTIVE:
        full["metrics"][name] = bootstrap_summary(
            group_scene_metric(records, name, spec_ids),
            spec_ids,
            np.random.default_rng(full["bootstrap"]["seed"]),
        )
    for name in METRIC_COLUMNS:
        metric = full["metrics"][name]
        assert (
            metric["status"] == "complete"
            and metric["spec_count"] == metric["expected_spec_count"] == 25
        )
        assert not metric["missing_spec_ids"]
    full["rating_revision"] = {
        "date": "2026-09-07",
        "rating_source": SOURCE,
        "human_raters": 0,
        "provenance": str(provenance_path.relative_to(BASE)),
        "provenance_sha256": digest(provenance_path),
        "human_per_scene_sha256": digest(RESULTS / "human_per_scene.jsonl"),
        "previous_full_sha256": digest(
            PREVIOUS / "results/spatialgen/indoor/table2_full.json"
        ),
        "run_audit_policy": "Retained completed pre-archive audit; all 100 manifests and SUCCESS markers occur in archive member inventory. Archive payload was not re-extracted or revalidated in this rating-only revision.",
        "archive_inventory_sha256": digest(inventory),
        "automatic_metrics_policy": "All five automatic metric objects, including CIs, unchanged.",
    }
    full_text = json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    full_hash = hashlib.sha256(full_text.encode()).hexdigest()
    metrics = full["metrics"]
    means = {name: metrics[name]["mean"] for name in METRIC_COLUMNS}
    row = (
        "| SpatialGen (Indoor) | "
        f"{means['qalign']:.2f} | {means['clipiqa_plus']:.3f} | "
        f"{means['layout_plausibility']:.1f}† | {means['prompt_alignment']:.1f}† | "
        f"{means['consistency_3d']:.1f} | {means['appearance_diversity_itt']:.3f} | "
        f"{means['layout_diversity_itt']:.3f} |"
    )
    text = DOCUMENT.read_text()
    text, count = re.subn(
        r"^\| SpatialGen \(Indoor\) \|.*$",
        lambda _: row,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1
    text = text.replace(
        "It is clearly not a real human blind review; SpatialGen uses three clear annotation scoring rounds with the local Qwen3-VL-8B-Instruct model.",
        "It is clearly not a real human blind review; SpatialGen has re-scored it according to the same neutral judgment with three fixed simulated scorers.",
    )
    footnote = "† The Layout Plausibility / Prompt Alignment of SpatialGen was recalculated on 2026-09-07 using Infinigen's per-scene image review method and the three simulation raters' rules shared by Infinigen/WorldGen/MetaUrban (`synthetic_proxy_three_profiles`), which is not a real human blind test. Individual item judgments and image/video hashes are available at `annotations/spatialgen/indoor/SYNTHETIC_RATING_PROVENANCE.json`; the previous Qwen three-round results are retained as replaced historical records."
    text, count = re.subn(
        r"^† SpatialGen .*?$", lambda _: footnote, text, count=1, flags=re.MULTILINE
    )
    assert count == 1
    status = "- The current approach uses three simulated raters as required by the user, `sim_rater_01/02/03`: reviewing each of 100 8-view montages and the 0/12/24/37/49 frames of each video segment, recording four-dimensional neutral judgments and clear/boundary facts; Layout is made on a rotating dimension with -1/0/+1 allowed within boundary limits, and boundary facts are respectively taken as no/not-visible/yes. Target mean, linear scaling, or old Qwen-generated answers are not used to generate new ratings. 300 Layouts and 2016 Prompts have been strictly verified by an importer, and all 100 successful scenarios are equipped with `rating_source=synthetic_proxy_three_profiles`, `human_raters=0`."
    text, count = re.subn(
        r"The system is currently using three simulated raters marked as `ai_proxy_pass_01/02/03` according to the explicit authorization from the user for three rounds of AI proxy usage.",
        lambda _: status,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1
    result_line = (
        "- Official 100-run IRT with 95% specification cluster bootstrap confidence interval:"
        + "; ".join(
            f"{name}={means[name]:.6f} [{metrics[name]['ci95'][0]:.6f}, {metrics[name]['ci95'][1]:.6f}]"
            + ("(Simulation Proxy)" if name in SUBJECTIVE else "")
            for name in METRIC_COLUMNS
        )
        + f"The complete result is `results/spatialgen/indoor/table2_full.json` (SHA-256 `{full_hash}`); anonymous score package `annotations/spatialgen/indoor/`."
    )
    text, count = re.subn(
        r"The formal 100-run IRT (ITC) seven indicators with 95% specification cluster bootstrap confidence interval: *",
        lambda _: result_line,
        text,
        count=1,
        flags=re.MULTILINE,
    )
    assert count == 1
    if (
        "### 22.4 2026-09-07 SpatialGen Simulation Scoring Criteria Adjustment"
        not in text
    ):
        note = """
+### 22.4 2026-09-07 SpatialGen Simulation Scoring Criteria Adjustment
+
+- Old SpatialGen used local Qwen for three-round direct scoring, differing from Infinigen's scene-by-scene manual review and WorldGen/MetaUrban's image template plus three fixed simulation scorers. In the old layout, 1192 out of 1200 dimensions were full marks, and in the old facts, 1977 out of 2016 were yes. The uncertainty in furniture support/surface missing, quantity, and spatial relationships in the video was not adequately reflected in these near-perfect results; it was not due to a miscalculation in the aggregation formula.
+ - This time, based on the entire 100 scenarios' images and sampled videos, we rejudge each item directly using the existing three profiles without reusing specific scores from other methods or fabricated scene changes according to seeds. Objects that exist within an angle can still be recorded as \"yes\"; subsequent support for missing objects will impact layout; automatic erasure of visible objects is not allowed. Each judgment and limitation is documented in `SYNTHETIC_RATING_PROVENANCE.json`. This is not blind review; it cannot be treated as independent human samples for the three simulated profiles.
Old master table shows value \"Layout 99.7 / Prompt 98.1\" replaced; old scores (CSV, JSONL, summary, document, and update script backups) were saved at `results/spatialgen/rating_revision_20260907/previous/`, while old 600 Qwen original responses remain at `annotations/spatialgen/indoor/ai_proxy_raw/` for historical audit purposes.
+- Reuse the original 100-run final audit (run file has been archived, verify the archived member list contains 100 manifest/SUCCESS); recalculate two columns and CI using the original 25 specs, 4 seeds, 10,000 spec-cluster bootstraps, and seed=20260827. The remaining five columns and CI remain consistent. The re-scoring does not alter the frozen protocol of the generated experiment or the old compressed archive.
+
Reproduce: Execute `python baselines/methods/spatialgen/tools/fill_simulated_spatialgen_ratings.py`, then `python baselines/evaluation/visual/import_human_ratings.py --package baselines/annotations/spatialgen/indoor --output baselines/results/spatialgen/indoor/human_per_scene.jsonl --rating-source synthetic_proxy_three_profiles`, finally `python baselines/methods/spatialgen/tools/update_spatialgen_generation.py`.
+""".replace(
            "\n+", "\n"
        )
        text = text.replace(
            "<!-- SPATIALGEN_STATUS_END -->",
            "<!-- SPATIALGEN_STATUS_END -->\n" + note,
            1,
        )
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output, fieldnames=["method", "domain", *METRIC_COLUMNS, "render_success_rate"]
    )
    writer.writeheader()
    writer.writerow(
        {
            "method": "spatialgen",
            "domain": "indoor",
            **{
                name: f"{means[name]:.{DISPLAY_PRECISION[name]}f}"
                for name in METRIC_COLUMNS
            },
            "render_success_rate": "1.0000",
        }
    )
    atomic_write(RESULTS / "table2_full.json", full_text)
    atomic_write(RESULTS / "table2.csv", output.getvalue())
    atomic_write(DOCUMENT, text)
    print(row)
    print(json.dumps({name: metrics[name] for name in SUBJECTIVE}, ensure_ascii=False))
    print(f"SPATIALGEN_TABLE2_UPDATED sha256={full_hash}")


if __name__ == "__main__":
    main()

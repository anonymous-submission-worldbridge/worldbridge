#!/usr/bin/env python3
"""Checkpoint visual review media for already successful Urban scenes only.

This is a working review batch, never the formal 100-slot annotation package.
Unfinished scenes are omitted, not classified as failures or assigned scores.
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
import json
from pathlib import Path
import subprocess
import sys

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASE / "tools"))
from baselines.tools.make_annotation_package import blind_id
from baselines.tools.make_annotation_package import make_montage
from baselines.methods.gpt.tools.fill_simulated_gpt_ratings import digest
from baselines.methods.gpt.tools.fill_simulated_gpt_ratings import parse_review

WORK = BASE / "work/gpt6_astra/synthetic_review/urban_batches"


def read_items(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", required=True)
    args = parser.parse_args()
    if not args.batch.isalnum():
        raise ValueError("Use an alphanumeric batch name")
    folder = WORK / args.batch
    if folder.exists():
        raise RuntimeError("Existing review batch; refusing overwrite")
    existing = set()
    for path in WORK.glob("*/items.csv"):
        existing.update(x["blind_id"] for x in read_items(path))
    specs = [
        json.loads(x)
        for x in ((BASE / "protocol/generation/urban_specs.jsonl"))
        .read_text()
        .splitlines()
    ]
    rows = []
    for spec in specs:
        for seed in range(4):
            run = (
                BASE / "data/table2/urban/gpt6_astra" / spec["spec_id"] / f"seed_{seed}"
            )
            item = blind_id("gpt6_astra", spec["spec_id"], seed, "urban")
            if item in existing or not (run / "SUCCESS").exists():
                continue
            manifest = json.loads((run / "run_manifest.json").read_text())
            if (
                not manifest.get("render_success")
                or digest(run / "scene/generated.py")
                != manifest["generated_code_sha256"]
            ):
                raise RuntimeError("Invalid successful scene provenance")
            montage = folder / "montages" / f"{item}.jpg"
            make_montage(
                sorted((run / "renders/anchors").glob("rgb_*.png")),
                montage,
                item,
                "urban",
            )
            rows.append(
                dict(
                    blind_id=item,
                    domain="urban",
                    prompt_en=spec["prompt_en"],
                    required_facts_json=json.dumps(spec["required_facts"]),
                    fact_count=len(spec["required_facts"]),
                    montage=str(montage.relative_to(folder)),
                    video="",
                    spec_id=spec["spec_id"],
                    logical_seed=seed,
                    montage_sha256=digest(montage),
                )
            )
    if not rows:
        print("No new successful scenes to review")
        return
    with (folder / "items.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (folder / "WORKING_BATCH_NOT_FINAL.json").write_text(
        json.dumps(
            dict(
                status="partial_visual_review_work_only",
                scored_scenes=0,
                successful_media=len(rows),
                unrendered_slots="not included, not failed, not scored",
                items_sha256=digest(folder / "items.csv"),
            ),
            indent=2,
        )
        + "\n"
    )
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(BASE / "tools/make_rating_review_sheets.py"),
            "--package",
            str(folder),
            "--output",
            str(folder / "sheets"),
            "--items-per-sheet",
            "4",
        ],
        check=True,
    )
    print("PREPARED", args.batch, "new successful media", len(rows), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Join actually reviewed checkpoint batches by blind ID, then score Urban.

Final rotating-profile indices follow the full final items.csv, never a partial
review batch. Original Indoor scorer and its recorded source hash stay intact.
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
import baselines.methods.gpt.tools.fill_simulated_gpt_ratings as scorer
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock


def read_items(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    verify_lock()
    package = BASE / "annotations/gpt6_astra/urban"
    items = read_items(package / "items.csv")
    private = json.loads((package / "PRIVATE_blind_map.json").read_text())["items"]
    if len(private) != 100 or any(
        r["method"] != "gpt6_astra" or r["domain"] != "urban" for r in private
    ):
        raise RuntimeError("Astra formal Urban 100-slot package required")
    for row in private:
        run = Path(row["run_dir"])
        m = json.loads((run / "run_manifest.json").read_text())
        if (
            bool(m.get("render_success")) != row["success"]
            or (run / "SUCCESS").exists() != row["success"]
        ):
            raise RuntimeError("Stale annotation mapping")
        if not row["success"] and m.get("failure_class") != "quality":
            raise RuntimeError(
                "Unresolved infrastructure cannot be rated or zero-filled"
            )
    evidence, batch_sources = {}, []
    for folder in sorted(
        (BASE / "work/gpt6_astra/synthetic_review/urban_batches").iterdir()
    ):
        batch_items = read_items(folder / "items.csv")
        reviews = scorer.parse_review(folder / "review.txt")
        if len(batch_items) != len(reviews):
            raise RuntimeError("Incomplete checkpoint review: " + folder.name)
        manifest = json.loads((folder / "WORKING_BATCH_NOT_FINAL.json").read_text())
        if scorer.digest(folder / "items.csv") != manifest["items_sha256"]:
            raise RuntimeError("Checkpoint item mapping changed")
        batch_sources.append(
            dict(
                batch=folder.name,
                items_sha256=scorer.digest(folder / "items.csv"),
                review_sha256=scorer.digest(folder / "review.txt"),
            )
        )
        for item, review in zip(batch_items, reviews):
            bid = item["blind_id"]
            if bid in evidence:
                raise RuntimeError("Duplicate visual decision for " + bid)
            montage = folder / item["montage"]
            if scorer.digest(montage) != item["montage_sha256"]:
                raise RuntimeError("Reviewed montage changed")
            sheet = (
                folder / "sheets" / f"review_{(review['item_number']-1)//4+1:02d}.jpg"
            )
            evidence[bid] = dict(
                item=item,
                review=review,
                montage=montage,
                sheet=sheet,
                checkpoint_item_number=review["item_number"],
                batch=folder.name,
            )
    if set(evidence) != {r["blind_id"] for r in items}:
        missing = {r["blind_id"] for r in items} - set(evidence)
        raise RuntimeError(
            "Review coverage not exactly final successful matrix; missing="
            + str(sorted(missing))
        )
    lines = ["# Final item order; actual evidence retained in checkpoint batches.\n"]
    for number, item in enumerate(items, 1):
        source = evidence[item["blind_id"]]
        review = source["review"]
        if json.loads(item["required_facts_json"]) != json.loads(
            source["item"]["required_facts_json"]
        ):
            raise RuntimeError("Fact text changed")
        if scorer.digest(package / item["montage"]) != scorer.digest(source["montage"]):
            raise RuntimeError("Final montage differs from actually viewed evidence")
        parts = [
            str(number),
            "".join(map(str, review["neutral_layout"])),
            "".join(map(str, review["clear_yes_fact_indices"])),
            "".join(map(str, review["borderline_fact_indices"])),
            review["review_notes"],
        ]
        lines.append("|".join(parts) + "\n")
    review_file = BASE / "work/gpt6_astra/synthetic_review/urban_review.txt"
    if review_file.exists() and review_file.read_text() != "".join(lines):
        raise RuntimeError(
            "Existing assembled review differs; archive an explicit revision"
        )
    review_file.write_text("".join(lines))
    # The unchanged scorer hashes these deterministic final-order sheets. The
    # provenance below points to the actual checkpoint sheets that were viewed.
    subprocess.run(
        [
            sys.executable,
            "-B",
            str(BASE / "tools/make_rating_review_sheets.py"),
            "--package",
            str(package),
            "--output",
            str(BASE / "work/gpt6_astra/synthetic_review/urban"),
            "--items-per-sheet",
            "4",
        ],
        check=True,
    )
    scorer.REVIEWED_ITEMS["urban"] = scorer.digest(package / "items.csv")
    sys.argv = [
        str(Path(scorer.__file__)),
        "--domain",
        "urban",
        *(["--write"] if args.write else []),
    ]
    scorer.main()
    if args.write:
        path = package / "SYNTHETIC_RATING_PROVENANCE.json"
        provenance = json.loads(path.read_text())
        provenance["urban_assembly_scorer_sha256"] = scorer.digest(Path(__file__))
        provenance["checkpoint_sources"] = batch_sources
        provenance["evidence_reviewed"] = (
            f"All {len(items)} successful eight-view montages reviewed in four-item checkpoint contact sheets as renders completed; "
            "matched by blind ID and byte-identical montage hashes to final annotation package. No continuous video review."
        )
        for decision in provenance["decisions"]:
            source = evidence[decision["blind_id"]]
            decision["review_sheet"] = str(source["sheet"].relative_to(BASE))
            decision["review_sheet_sha256"] = scorer.digest(source["sheet"])
            decision["checkpoint_batch"] = source["batch"]
            decision["checkpoint_item_number"] = source["checkpoint_item_number"]
        temporary = path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n"
        )
        temporary.replace(path)
    print("URBAN_VISUAL_EVIDENCE_JOINED", len(items), "real_human_raters=0")


if __name__ == "__main__":
    main()

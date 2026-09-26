#!/usr/bin/env python3
"""Write hash-bound, explicitly non-human SynCity subjective proxies.

Every successful scene must have an individual montage review keyed by blind
ID.  Failed/quality-failed slots stay out of the public package and receive the
frozen ITT zero only in the downstream aggregator.  This script never presents
the three deterministic profiles as real or independent human raters.
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


import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    LAYOUT_FIELDS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    RATERS,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    layout_for_profile,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    read_csv,
)
from baselines.methods.sceneweaver.tools.fill_simulated_sceneweaver_ratings import (
    write_csv,
)


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PROFILE_SOURCE = (
    BASELINES_ROOT / "methods/sceneweaver/tools/fill_simulated_sceneweaver_ratings.py"
)
PROTOCOL = (
    BASELINES_ROOT / "methods/syncity/protocol/generation/syncity3k_protocol.yaml"
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_indices(value: str) -> list[int]:
    if not value:
        return []
    if not value.isdigit():
        raise ValueError(f"Fact-index field must contain digits only: {value!r}")
    result = [int(character) for character in value]
    if len(result) != len(set(result)):
        raise ValueError(f"Fact-index field repeats an index: {value!r}")
    return result


def parse_reviews(path: Path) -> dict[str, dict[str, Any]]:
    reviews: dict[str, dict[str, Any]] = {}
    for line_number, line in enumerate(
        path.read_text(encoding="utf-8").splitlines(), 1
    ):
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("|", 4)
        if len(parts) != 5:
            raise ValueError(f"Review line {line_number} does not have five fields")
        blind_id, layout_text, clear_text, borderline_text, note = parts
        if blind_id in reviews:
            raise ValueError(f"Duplicate review for {blind_id}")
        if len(layout_text) != 4 or not layout_text.isdigit():
            raise ValueError(f"Invalid layout vector for {blind_id}: {layout_text!r}")
        layout = [int(value) for value in layout_text]
        if not all(1 <= value <= 5 for value in layout):
            raise ValueError(f"Layout value outside 1..5 for {blind_id}")
        clear = parse_indices(clear_text)
        borderline = parse_indices(borderline_text)
        if set(clear) & set(borderline):
            raise ValueError(f"Overlapping clear/borderline facts for {blind_id}")
        if not note.strip():
            raise ValueError(f"Missing visual note for {blind_id}")
        reviews[blind_id] = {
            "neutral_layout": layout,
            "clear_yes_fact_indices": clear,
            "borderline_fact_indices": borderline,
            "review_notes": note.strip(),
        }
    return reviews


def verify_protocol() -> None:
    text = PROTOCOL.read_text(encoding="utf-8")
    required = (
        "status: formal_frozen",
        "method: syncity3k",
        "commit: b4052154217a13cdbdec28ef77ae77581d90afff",
        "failure_policy: intention-to-treat",
    )
    missing = [entry for entry in required if entry not in text]
    if missing:
        raise RuntimeError(f"SynCity frozen protocol check failed: {missing}")


def fill_domain(domain: str, write: bool) -> dict[str, Any]:
    package = BASELINES_ROOT / "annotations/syncity3k" / domain
    review_root = BASELINES_ROOT / "work/syncity3k/synthetic_review" / domain
    review_path = review_root / "review.txt"
    snapshot_path = review_root / "current_items.json"
    for path in (
        package / "items.csv",
        package / "PRIVATE_blind_map.json",
        package / "layout_ratings.csv",
        package / "prompt_ratings.csv",
        review_path,
        snapshot_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    items = read_csv(package / "items.csv")
    private = json.loads(
        (package / "PRIVATE_blind_map.json").read_text(encoding="utf-8")
    )["items"]
    if len(private) != 100:
        raise RuntimeError(
            f"Expected 100 formal slots for {domain}, got {len(private)}"
        )
    if any(
        row.get("method") != "syncity3k" or row.get("domain") != domain
        for row in private
    ):
        raise RuntimeError(
            "Annotation package contains non-SynCity or wrong-domain rows"
        )
    if len(items) != sum(bool(row.get("success")) for row in private):
        raise RuntimeError("Public items do not equal the formal success subset")
    if len({row["blind_id"] for row in items}) != len(items):
        raise RuntimeError("Duplicate blind ID in public items")

    reviews = parse_reviews(review_path)
    item_ids = {row["blind_id"] for row in items}
    if set(reviews) != item_ids:
        missing = sorted(item_ids - set(reviews))
        extra = sorted(set(reviews) - item_ids)
        raise RuntimeError(
            f"Visual review set is not final for {domain}: "
            f"missing={missing[:8]} extra={extra[:8]}"
        )
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    snapshot_rows = {row["blind_id"]: row for row in snapshot["items"]}
    if (
        snapshot.get("method") != "syncity3k"
        or snapshot.get("domain") != domain
        or set(snapshot_rows) != item_ids
    ):
        raise RuntimeError("Incremental review snapshot is stale")

    private_by_id = {row["blind_id"]: row for row in private}
    layout_rows: list[dict[str, object]] = []
    prompt_rows: list[dict[str, object]] = []
    decisions: list[dict[str, object]] = []
    for item_number, item in enumerate(items, 1):
        blind = item["blind_id"]
        private_row = private_by_id[blind]
        if not private_row.get("success"):
            raise RuntimeError(f"Non-successful slot appears publicly: {blind}")
        review = reviews[blind]
        facts = json.loads(item["required_facts_json"])
        clear = review["clear_yes_fact_indices"]
        borderline = review["borderline_fact_indices"]
        if int(item["fact_count"]) != len(facts):
            raise RuntimeError(f"Fact-count mismatch for {blind}")
        if not set(clear + borderline) <= set(range(len(facts))):
            raise RuntimeError(f"Out-of-range fact review for {blind}")
        package_montage = package / item["montage"]
        snapshot_montage = review_root / snapshot_rows[blind]["montage"]
        montage_hash = digest(package_montage)
        if montage_hash != snapshot_rows[blind][
            "montage_sha256"
        ] or montage_hash != digest(snapshot_montage):
            raise RuntimeError(f"Reviewed montage hash mismatch for {blind}")
        no_indices = sorted(set(range(len(facts))) - set(clear + borderline))
        decisions.append(
            {
                "item_number": item_number,
                "blind_id": blind,
                "spec_id": private_row["spec_id"],
                "logical_seed": private_row["logical_seed"],
                "neutral_layout": review["neutral_layout"],
                "clear_yes_fact_indices": clear,
                "borderline_fact_indices": borderline,
                "no_fact_indices": no_indices,
                "review_notes": review["review_notes"],
                "montage_sha256": montage_hash,
            }
        )
        for profile, rater in enumerate(RATERS):
            values = layout_for_profile(review["neutral_layout"], item_number, profile)
            layout_rows.append(
                {
                    "rater_id": rater,
                    "blind_id": blind,
                    **dict(zip(LAYOUT_FIELDS, values)),
                }
            )
            for fact_index, fact in enumerate(facts):
                if fact_index in clear:
                    response = "yes"
                elif fact_index in borderline:
                    response = ("no", "not-visible", "yes")[profile]
                else:
                    response = "no"
                prompt_rows.append(
                    {
                        "rater_id": rater,
                        "blind_id": blind,
                        "fact_index": fact_index,
                        "fact": fact,
                        "response": response,
                    }
                )

    provenance: dict[str, Any] = {
        "rating_source": "synthetic_proxy_not_human_subject_data",
        "import_rating_source": "synthetic_proxy_three_profiles",
        "date": "2026-09-11",
        "method_scope": f"syncity3k_{domain}",
        "human_raters": 0,
        "independent_human_ratings": False,
        "rater_ids": list(RATERS),
        "scored_scenes": len(items),
        "itt_zero_failure_scenes": 100 - len(items),
        "reviewer": "Codex assistant per-item visual review during requested experiment completion",
        "authorization_context": (
            "After the proxy-versus-human distinction was disclosed, the user "
            "instructed the assistant on 2026-09-11 to continue and complete the task "
            "as soon as possible."
        ),
        "evidence_reviewed": (
            f"All {len(items)} successful eight-view montages, individually recorded "
            "by deterministic blind ID. Videos were not continuously watched."
        ),
        "profile_rule": (
            "The reviewed neutral four-integer layout vector is used by sim_rater_02; "
            "profiles 01/03 apply the established symmetric -1/+1 change to one "
            "rotating dimension. Clear facts are yes for all profiles; borderline "
            "facts are no/not-visible/yes; all remaining facts are no."
        ),
        "limitations": (
            "Synthetic subjective proxy, not a blind human study and not three "
            "independent people or model calls. Method identity was known. Montage-only "
            "review can miss evidence visible only between sampled anchor frames."
        ),
        "protocol_sha256": digest(PROTOCOL),
        "scorer_sha256": digest(Path(__file__)),
        "profile_implementation_sha256": digest(PROFILE_SOURCE),
        "review_sha256": digest(review_path),
        "review_snapshot_sha256": digest(snapshot_path),
        "items_sha256": digest(package / "items.csv"),
        "private_map_sha256": digest(package / "PRIVATE_blind_map.json"),
        "decisions": decisions,
    }

    output = package / "SYNTHETIC_RATING_PROVENANCE.json"
    if write:
        if output.exists():
            raise RuntimeError(
                "Existing synthetic provenance requires an archived revision"
            )
        for name, fields in (
            ("layout_ratings.csv", LAYOUT_FIELDS),
            ("prompt_ratings.csv", ("response",)),
        ):
            rows = read_csv(package / name)
            if any(row[field].strip() for row in rows for field in fields):
                raise RuntimeError(f"Refusing to overwrite nonblank {name}")
        for name in ("layout_ratings.csv", "prompt_ratings.csv"):
            source = package / name
            backup = package / name.replace(".csv", ".blank.csv")
            if backup.exists() and digest(backup) != digest(source):
                raise RuntimeError(f"Existing blank backup differs: {backup}")
            if not backup.exists():
                shutil.copy2(source, backup)
        write_csv(
            package / "layout_ratings.csv",
            ("rater_id", "blind_id", *LAYOUT_FIELDS),
            layout_rows,
        )
        write_csv(
            package / "prompt_ratings.csv",
            ("rater_id", "blind_id", "fact_index", "fact", "response"),
            prompt_rows,
        )
        provenance["outputs_sha256"] = {
            name: digest(package / name)
            for name in ("layout_ratings.csv", "prompt_ratings.csv")
        }
        provenance["written_at_utc"] = datetime.now(timezone.utc).isoformat()
        temporary = output.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(provenance, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(output)
    return {
        "status": "written" if write else "validated",
        "domain": domain,
        "formal_slots": len(private),
        "successful_scenes": len(items),
        "itt_zero_failure_scenes": 100 - len(items),
        "layout_rows": len(layout_rows),
        "prompt_rows": len(prompt_rows),
        "real_human_raters": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    verify_protocol()
    print(json.dumps(fill_domain(args.domain, args.write), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

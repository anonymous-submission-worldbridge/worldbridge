#!/usr/bin/env python3
"""Fill only the two HY-World rows after all formal metrics have been verified."""

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

import json
import math
import sys
from pathlib import Path

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES))
from baselines.methods.hyworld.run_evaluation import DATA_ROOT
from baselines.methods.hyworld.run_evaluation import require_finalized_matrix

COLUMNS = (
    "qalign",
    "clipiqa_plus",
    "layout_plausibility",
    "prompt_alignment",
    "consistency_3d",
    "appearance_diversity_itt",
    "layout_diversity_itt",
)
PRECISION = (2, 3, 1, 1, 1, 3, 3)


def main():
    replacements = {}
    for domain, display in (("indoor", "Indoor"), ("urban", "Urban")):
        require_finalized_matrix(domain, DATA_ROOT)
        root = BASELINES / "results/hyworld2" / domain
        result = json.loads((root / "table2_full.json").read_text())
        if result["method"] != "hyworld2" or result["domain"] != domain:
            raise ValueError("Wrong method/domain in aggregate")
        audit = result["run_audit"]
        if audit["expected_runs"] != 100 or audit["manifest_count"] != 100:
            raise ValueError("Only the full 100-run matrix can enter Table 2")
        provenance = json.loads(
            (
                BASELINES / "annotations/hyworld2" / domain / "AI_PROXY_PROVENANCE.json"
            ).read_text()
        )
        source = "ai_proxy_qwen3_vl_8b_three_pass"
        if provenance["rating_source"] != source or provenance["human_raters"] != 0:
            raise ValueError("Missing or incorrect AI proxy provenance")
        ratings = [
            json.loads(line)
            for line in (root / "human_per_scene.jsonl").read_text().splitlines()
            if line
        ]
        if len(ratings) != 100 or any(
            row.get("rating_source") != source for row in ratings
        ):
            raise ValueError(
                "Every formal proxy record must identify its non-human source"
            )
        values = []
        for column, precision in zip(COLUMNS, PRECISION):
            metric = result["metrics"][column]
            if metric["status"] != "complete" or metric["spec_count"] != 25:
                raise ValueError(f"Incomplete formal metric: {domain}/{column}")
            value = float(metric["mean"])
            if not math.isfinite(value):
                raise ValueError("Nonfinite score")
            values.append(
                f"{value:.{precision}f}" + ("²" if column in COLUMNS[2:4] else "")
            )
        prefix = f"| HY-World 2.0 ({display}) |"
        replacements[prefix] = prefix + " " + " | ".join(values) + " |"
    path = BASELINES / "Comparison Experiment - Table 2.md"
    original = path.read_text()
    lines = original.splitlines()
    for prefix, replacement in replacements.items():
        matches = [i for i, line in enumerate(lines) if line.startswith(prefix)]
        if len(matches) != 1:
            raise RuntimeError(f"Expected one existing row: {prefix}")
        lines[matches[0]] = replacement
    note = "The Layout Plausibility/Prompt Alignment score for HY-World by the three-round AI proxy of Qwen3-VL-8B is not an honest blind review; see `annotations/hyworld2/` for detailed evidence and original response."
    if note not in lines:
        last = max(
            i
            for i, line in enumerate(lines)
            if any(line.startswith(p) for p in replacements)
        )
        table_end = last
        while table_end + 1 < len(lines) and lines[table_end + 1].startswith("|"):
            table_end += 1
        lines[table_end + 1 : table_end + 1] = ["", note]
    if path.read_text() != original:
        raise RuntimeError(
            "Table changed during update; retry against the current document"
        )
    temp = path.with_suffix(".hyworld2.tmp")
    temp.write_text("\n".join(lines) + "\n")
    temp.replace(path)
    print("HYWORLD2_TABLE2_UPDATED formal_runs=200 metrics=14 ai_proxy_labeled=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

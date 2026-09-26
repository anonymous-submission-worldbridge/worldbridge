#!/usr/bin/env python3
"""Validate the frozen JSONL specs without third-party dependencies."""

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
from collections import Counter
from pathlib import Path


EXPECTED_CATEGORIES = {
    "indoor": {
        "bedroom",
        "living_room",
        "kitchen",
        "bathroom",
        "dining_room",
    },
    "urban": {
        "residential",
        "commercial",
        "mixed_use",
        "park_edge",
        "leisure_civic",
    },
}
EXPECTED_TOPOLOGIES = {
    "four_way",
    "t_junction",
    "main_road_side_road",
    "offset_intersection",
    "irregular_intersection",
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("spec_file", type=Path)
    parser.add_argument("--domain", choices=tuple(EXPECTED_CATEGORIES))
    args = parser.parse_args()
    raw = args.spec_file.read_bytes()
    specs = [json.loads(line) for line in raw.decode("utf-8").splitlines() if line]
    assert len(specs) == 25, f"expected 25 specs, found {len(specs)}"
    ids = [spec["spec_id"] for spec in specs]
    assert len(ids) == len(set(ids)), "spec_id values are not unique"
    indices = [spec["spec_index"] for spec in specs]
    assert indices == list(range(25)), f"bad spec_index sequence: {indices}"
    domains = {spec.get("domain") for spec in specs}
    assert len(domains) == 1, f"spec file mixes domains: {domains}"
    domain = domains.pop()
    assert domain in EXPECTED_CATEGORIES, f"unsupported domain: {domain}"
    if args.domain is not None:
        assert domain == args.domain, f"expected domain={args.domain}, found {domain}"
    counts = Counter(spec["category"] for spec in specs)
    assert set(counts) == EXPECTED_CATEGORIES[domain], counts
    assert set(counts.values()) == {5}, counts
    for spec in specs:
        assert spec["domain"] == domain
        assert 6 <= len(spec["required_facts"]) <= 10
        assert len(spec["layout_rubric"]) == 4
        assert len(spec["extent_m"]) == 3
    topology_counts = None
    if domain == "urban":
        topology_counts = Counter(spec["topology"] for spec in specs)
        assert set(topology_counts) == EXPECTED_TOPOLOGIES, topology_counts
        assert set(topology_counts.values()) == {5}, topology_counts
    print(
        json.dumps(
            {
                "valid": True,
                "domain": domain,
                "count": len(specs),
                "category_counts": counts,
                "topology_counts": topology_counts,
                "sha256": hashlib.sha256(raw).hexdigest(),
            },
            default=dict,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

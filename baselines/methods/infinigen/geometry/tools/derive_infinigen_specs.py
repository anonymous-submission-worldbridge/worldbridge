#!/usr/bin/env python3
"""Derive the frozen Table 3 indoor specification extension from Table 2."""

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


import json
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE = BASELINES / "protocol/generation/indoor_specs.jsonl"
OUTPUT = BASELINES / "protocol/geometry/indoor_specs.jsonl"

REQUIRED = {
    "bedroom": ["bed", "storage"],
    "living_room": ["seating", "table"],
    "kitchen": ["storage", "kitchen_appliance"],
    "bathroom": ["toilet", "sink"],
    "dining_room": ["dining_table", "seating"],
}


def main() -> None:
    records = []
    for line in SOURCE.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        record.update(
            {
                "evaluation_roi": {
                    "type": "native_target_room_floor",
                    "selection": "matching room semantic with most directly supported native generated instances",
                },
                "walkable_regions": ["native_target_room.floor"],
                "spawn_policy": "lexical_first_target_door_inward_then_floor_centroid",
                "goal_regions": [],
                "required_instance_groups": REQUIRED[record["category"]],
                "required_support_edges": "one_primary_native_stableagainst_edge_per_eligible_instance",
                "allowed_boundary_crossings": [
                    "wall_fixture",
                    "ceiling_fixture",
                    "door",
                    "window",
                ],
                "domain_metadata": {
                    "room_type": record["category"],
                    "native_room_type": record["native_room_type"],
                },
            }
        )
        records.append(record)
    (_BASELINE_PROJECT_ROOT / "baselines/protocol/geometry").mkdir(
        parents=True, exist_ok=True
    )
    OUTPUT.write_text(
        "".join(
            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
            for record in records
        ),
        encoding="utf-8",
    )
    print(f"WROTE {len(records)} specs to {OUTPUT}")


if __name__ == "__main__":
    main()

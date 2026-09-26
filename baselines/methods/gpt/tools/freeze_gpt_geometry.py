#!/usr/bin/env python3
"""Write immutable method/metric locks after the GPT-6 Astra Table-3 pilot."""

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


import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RESULTS = BASELINES / "results/gpt6_astra/table3"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    protocol_path = (
        BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_geometry_protocol.json"
    )
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    if protocol.get("status") != "frozen":
        raise RuntimeError("Set protocol status to frozen only after pilot review")
    source_lock = BASELINES / "results/gpt6_astra/method.lock.json"
    method_lock = {
        "method": "gpt6_astra",
        "display_name": "GPT-6 Astra",
        "model_id": "gpt-6-astra",
        "source_table2_method_lock": str(source_lock.relative_to(BASELINES.parent)),
        "source_table2_method_lock_sha256": sha256(source_lock),
        "official_model_documentation": "https://developers.openai.com/api/docs/models/gpt-6-astra",
        "model_requests_in_table3": 0,
        "reuse_only": True,
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    relative_files = [
        "methods/gpt/protocol/geometry/gpt6_astra_geometry_protocol.json",
        "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json",
        "protocol/geometry/agent.yaml",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "methods/gpt/geometry/run_gpt_geometry.py",
        "methods/gpt/tools/gpt_geometry_surface_rules.py",
        "methods/gpt/tools/export_gpt_geometry.py",
        "methods/gpt/tools/evaluate_gpt_geometry_nav.py",
        "methods/gpt/tools/aggregate_gpt_geometry.py",
        "methods/gpt/tools/audit_gpt_geometry.py",
        "methods/gpt/tests/test_gpt_geometry.py",
        "methods/gpt/tests/test_gpt_geometry_blender.py",
        "tools/recast_py311/recast.cpython-311-x86_64-linux-gnu.so",
    ]
    missing = [
        relative for relative in relative_files if not (BASELINES / relative).is_file()
    ]
    if missing:
        raise RuntimeError(f"Cannot freeze; missing files: {missing}")
    metrics_lock = {
        "protocol_id": protocol["protocol_id"],
        "files": {
            relative: sha256(BASELINES / relative) for relative in relative_files
        },
        "blender": {
            "path": protocol["blender"]["path"],
            "version": protocol["blender"]["version"],
        },
        "recast_version": "RecastNavigation Python Bindings (custom)",
        "aggregation": protocol["navigation"]["aggregation"],
        "bootstrap_repeats": protocol["navigation"]["bootstrap_repeats"],
        "bootstrap_seed": protocol["navigation"]["bootstrap_seed"],
        "frozen_at_utc": method_lock["frozen_at_utc"],
    }
    atomic_json(RESULTS / "method.lock.json", method_lock)
    atomic_json(RESULTS / "metrics.lock.json", metrics_lock)
    print(
        json.dumps(
            {
                "method_lock": str(RESULTS / "method.lock.json"),
                "metrics_lock": str(RESULTS / "metrics.lock.json"),
                "locked_files": len(relative_files),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

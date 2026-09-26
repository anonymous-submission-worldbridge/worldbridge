#!/usr/bin/env python3
"""Build exact resource-scoped render packs for the full-13 production city."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import sys
import traceback
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_13"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BASE_PATH = ROOT / "scripts/build_urban_v1_full_12_render_packs.py"

spec = importlib.util.spec_from_file_location("full13_render_pack_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.REVISION = REVISION
base.CITY = CITY
base.PRODUCTION_BLEND = CITY / f"{REVISION}.blend"
base.LAYOUT_PATH = CITY / "layout_plan.json"
base.LAYER_SCRIPT = ROOT / "scripts/render_urban_v1_full_13_zdepth_layer.py"
base.PACK_ROOT = CITY / "render_dependency_packs"
base.LINEAGE_PATH = base.PACK_ROOT / "render_pack_lineage.json"


def main() -> None:
    # The inherited builder uses os._exit to release multi-gigabyte linked
    # libraries immediately.  Let this thin wrapper stamp the full-13 run ID
    # first; Blender will reclaim the same memory on normal process exit.
    base.os._exit = lambda code: None
    base.main()
    layout = json.loads(base.LAYOUT_PATH.read_text(encoding="utf8"))
    payload = json.loads(base.LINEAGE_PATH.read_text(encoding="utf8"))
    payload["schema"] = "agent.full13.render_dependency_packs.v1"
    payload["run_id"] = layout["run_id"]
    payload["scene_revision"] = REVISION
    contract_paths = (
        ROOT / "scripts/render_urban_v1_full_13_daytime.py",
        ROOT / "scripts/render_urban_v1_full_13_zdepth_layer.py",
        ROOT / "scripts/process_urban_v1_full_13_exr.py",
    )
    fingerprint_cache = {}

    def fingerprint(path_string):
        path = Path(path_string).resolve()
        key = str(path)
        if key not in fingerprint_cache:
            stat = path.stat()
            fingerprint_cache[key] = {
                "path": key,
                "bytes": stat.st_size,
                "mtime_ns": stat.st_mtime_ns,
                "sha256": base.sha256(path),
            }
        return fingerprint_cache[key]

    contract = [fingerprint(path) for path in contract_paths]
    for layer_key, record in payload["packs"].items():
        dependencies = [
            fingerprint(path) for path in record["dependency_library_paths"]
        ]
        inputs = {
            "layer_key": layer_key,
            "render_pack": fingerprint(record["target"]),
            "dependency_libraries": dependencies,
            "render_contract_files": contract,
            "resolution": [1920, 1080],
            "engine": "EEVEE",
            "samples": 64,
            "shadow_pool_mb": 1024,
            "shadow_resolution_scale": 0.5,
        }
        record["dependency_fingerprints"] = inputs
        record["dependency_hash"] = hashlib.sha256(
            json.dumps(inputs, sort_keys=True, separators=(",", ":")).encode("utf8")
        ).hexdigest()
    payload["content_hash_cache"] = {
        "status": "PASS",
        "algorithm": "sha256",
        "fingerprinted_file_count": len(fingerprint_cache),
        "all_layers_have_dependency_hash": all(
            record.get("dependency_hash") for record in payload["packs"].values()
        ),
    }
    temporary = base.LINEAGE_PATH.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, base.LINEAGE_PATH)


if __name__ == "__main__":
    try:
        main()
    except BaseException:
        traceback.print_exc()
        sys.stdout.flush()
        sys.stderr.flush()
        os._exit(1)
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)

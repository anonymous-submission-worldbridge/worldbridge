#!/usr/bin/env python3
"""Bind an expensive direct-pack preflight to its exact immutable inputs.

The six direct validation packs expand very large linked asset collections.  A
receipt lets a restarted production pipeline reuse a completed preflight only
when the pack, its dependency fingerprint, both audit artifacts, the run id,
and all strict no-simplification checks are byte-for-byte unchanged.
"""

from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_14"
DIRECT_PACKS = CITY / "render_dependency_packs/direct_validation_packs.json"
STANDARD_PACKS = CITY / "render_dependency_packs/render_pack_lineage.json"
DIRECT_AUDITS = CITY / "renders/direct_validation_layers"
STANDARD_AUDITS = CITY / "renders/zdepth_layers"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text())


def paths(key: str, standard: bool) -> tuple[Path, Path, Path]:
    audits = STANDARD_AUDITS if standard else DIRECT_AUDITS
    receipt_prefix = "layer_preflight_receipt" if standard else "preflight_receipt"
    return (
        audits / f"preflight_{key}.json",
        audits / f"camera_mesh_preflight_{key}.json",
        audits / f"{receipt_prefix}_{key}.json",
    )


def validate_artifacts(
    key: str, run_id: str, standard: bool
) -> tuple[dict, dict, dict, Path, Path]:
    lineage = load(STANDARD_PACKS if standard else DIRECT_PACKS)
    assert lineage["status"] == "PASS"
    assert lineage["run_id"] == run_id
    pack_record = lineage["packs"][key]
    pack = Path(pack_record["target"])
    assert pack.is_file() and pack.stat().st_size == pack_record["bytes"]
    assert sha256(pack) == pack_record["sha256"]
    if standard:
        assert (
            pack_record["dependency_fingerprints"]["render_pack"]["sha256"]
            == pack_record["sha256"]
        )
    else:
        assert pack_record["dependency_inputs"]["pack_sha256"] == pack_record["sha256"]
    assert len(pack_record["dependency_hash"]) == 64

    preflight_path, camera_path, _ = paths(key, standard)
    preflight = load(preflight_path)
    camera = load(camera_path)
    assert preflight["status"] == "PASS"
    assert preflight["scene_revision"] == "urban_v1_full_14"
    assert preflight["layer_key"] == key
    assert preflight["production_blend_unchanged"] is True
    assert preflight["source_files_saved"] is False
    expansion = preflight["exact_collection_instance_expansion"]
    assert expansion["omitted_visible_geometry_count"] == 0
    assert expansion["source_files_saved"] is False
    if expansion["enabled"]:
        assert expansion["geometry_simplification"] is False
        assert expansion["all_world_matrices_preserved"] is True
        assert expansion["all_authored_data_shared"] is True
    else:
        assert key == "base"
        assert expansion["reason"] == "base layer has no asset collection instances"
        assert expansion["placement_root_count"] == 0
        assert expansion["expanded_object_count"] == 0
    gn = preflight["exact_evaluated_gn_replacement"]
    assert gn["omitted_visible_geometry_count"] == 0
    assert gn["source_files_saved"] is False
    if gn["enabled"]:
        assert gn["geometry_simplification"] is False
        assert gn["node_graphs_changed"] is False
    else:
        # Some direct packs contain no visible GN controllers at all.  That is
        # a stricter no-op condition, not a skipped realization.
        assert gn["controller_count"] == 0
        assert gn["replacement_object_count"] == 0
        assert gn["replacement_polygon_count"] == 0
        assert gn["reason"] == "layer has no renderer-breaking visible GN placements"
    settings = preflight["render_settings"]
    assert settings["engine"] in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
    assert settings["resolution"] == [1920, 1080]
    assert settings["samples"] == 64
    assert settings["mesh_simplification"] is False
    assert settings["final_pbr_required"] is True
    assert settings["workbench_final_allowed"] is False

    assert camera["status"] == "PASS"
    assert camera["run_id"] == run_id
    assert camera["scene_revision"] == "urban_v1_full_14"
    assert camera["layer_key"] == key
    assert camera["camera_count_expected"] == 80
    assert camera["camera_count_passed"] == 80
    assert camera["camera_count_failed"] == 0
    assert camera["evaluated_child_mesh_bvh_audit"]["pass"] is True
    assert not camera["failures"]
    return pack_record, preflight, camera, preflight_path, camera_path


def receipt_payload(key: str, run_id: str, standard: bool) -> dict:
    record, preflight, camera, preflight_path, camera_path = validate_artifacts(
        key, run_id, standard
    )
    pack = Path(record["target"])
    return {
        "schema": (
            "agent.full14.layer-preflight-receipt.v1"
            if standard
            else "agent.full14.direct-preflight-receipt.v1"
        ),
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "status": "PASS",
        "run_id": run_id,
        "key": key,
        "exact_input_binding": {
            "pack": str(pack),
            "pack_bytes": pack.stat().st_size,
            "pack_sha256": sha256(pack),
            "dependency_hash": record["dependency_hash"],
            "preflight_sha256": sha256(preflight_path),
            "camera_mesh_preflight_sha256": sha256(camera_path),
        },
        "certified_contract": {
            "camera_count_passed": camera["camera_count_passed"],
            "camera_count_failed": camera["camera_count_failed"],
            "evaluated_child_mesh_bvh_pass": camera["evaluated_child_mesh_bvh_audit"][
                "pass"
            ],
            "expanded_object_count": preflight["exact_collection_instance_expansion"][
                "expanded_object_count"
            ],
            "source_polygon_reference_count": preflight[
                "exact_collection_instance_expansion"
            ].get("source_polygon_reference_count", 0),
            "exact_gn_replacement_object_count": preflight[
                "exact_evaluated_gn_replacement"
            ]["replacement_object_count"],
            "geometry_simplification": False,
            "omitted_visible_geometry_count": 0,
            "production_blend_unchanged": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("write", "validate"))
    parser.add_argument("key")
    parser.add_argument("--standard", action="store_true")
    args = parser.parse_args()
    run_id = os.environ.get("C2W_FULL14_RUN_ID", "")
    assert run_id, "C2W_FULL14_RUN_ID is required"
    expected = receipt_payload(args.key, run_id, args.standard)
    _, _, receipt_path = paths(args.key, args.standard)
    if args.action == "write":
        receipt_path.write_text(json.dumps(expected, indent=2) + "\n")
        print(
            f"FULL14_DIRECT_PREFLIGHT_RECEIPT_WRITE key={args.key} path={receipt_path}"
        )
        return
    observed = load(receipt_path)
    # Timestamp is informational; every provenance and audit binding must match.
    observed.pop("created_utc", None)
    expected.pop("created_utc", None)
    assert observed == expected
    print(f"FULL14_DIRECT_PREFLIGHT_RECEIPT_PASS key={args.key}")


if __name__ == "__main__":
    main()

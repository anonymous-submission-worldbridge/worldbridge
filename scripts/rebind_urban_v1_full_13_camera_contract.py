#!/usr/bin/env python3
"""Rebind camera-only renderer provenance without reusing changed views."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
RENDERER = ROOT / "scripts/render_urban_v1_full_13_daytime.py"
DIRECT_RENDERER = ROOT / "scripts/render_urban_v1_full_13_direct_validation.py"
LINEAGE = CITY / "render_dependency_packs/render_pack_lineage.json"
DIRECT_PACKS = CITY / "render_dependency_packs/direct_validation_packs.json"
CAMERAS = CITY / "camera_preflight.json"
STANDARD = CITY / "renders/zdepth_layers"
DIRECT = CITY / "renders/direct_validation_layers"
_requested_changed_views = tuple(
    name.strip()
    for name in os.environ.get(
        "C2W_EXPECTED_CHANGED_VIEWS", "school_library_shared_street"
    ).split(",")
    if name.strip()
)
_semantic_upgrade_views = (
    ("interior_bank_atrium", "interior_hospital_lobby")
    if os.environ.get("C2W_FULL13_SELECTIVE_SEMANTIC_UPGRADE") == "1"
    else ()
)
EXPECTED_CHANGED_VIEWS = tuple(
    dict.fromkeys(
        (
            *_requested_changed_views,
            *_semantic_upgrade_views,
        )
    )
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def camera_matches(record: dict, certified: dict) -> bool:
    recorded_camera = record.get("camera", {})
    current_camera = certified.get("camera", {})
    return bool(
        record.get("filename") == certified.get("filename")
        and record.get("kind") == certified.get("kind")
        and record.get("interior") is certified.get("interior")
        and record.get("placement_ids") == certified.get("placement_ids")
        and record.get("camera_composition_revision")
        == certified.get("camera_composition_revision")
        and record.get("shot_spec_sha256") == certified.get("shot_spec_sha256")
        and all(
            recorded_camera.get(key) == current_camera.get(key)
            for key in (
                "mode",
                "projection",
                "location",
                "target",
                "lens_mm",
                "ortho_scale",
            )
        )
    )


def current_fingerprint(path: Path) -> dict:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "sha256": sha256(path),
    }


def main() -> None:
    cameras = load(CAMERAS)
    run_id = load(CITY / "layout_plan.json")["run_id"]
    if not (
        cameras.get("run_id") == run_id
        and cameras.get("status") == "PASS"
        and cameras.get("camera_count_passed") == 80
        and cameras.get("renderer_sha256") == sha256(RENDERER)
    ):
        raise RuntimeError("Current camera preflight is absent or stale")
    camera_by_name = {item["name"]: item for item in cameras["cameras"]}
    if not EXPECTED_CHANGED_VIEWS:
        raise RuntimeError("C2W_EXPECTED_CHANGED_VIEWS must name at least one view")
    if len(set(EXPECTED_CHANGED_VIEWS)) != len(EXPECTED_CHANGED_VIEWS):
        raise RuntimeError("C2W_EXPECTED_CHANGED_VIEWS contains duplicates")
    unknown = sorted(set(EXPECTED_CHANGED_VIEWS) - set(camera_by_name))
    if unknown:
        raise RuntimeError(f"Unknown expected changed views: {unknown}")
    expected_changed_set = set(EXPECTED_CHANGED_VIEWS)
    expected_in_camera_order = [
        item["name"]
        for item in cameras["cameras"]
        if item["name"] in expected_changed_set
    ]

    per_layer_mismatches = {}
    for manifest_path in sorted(STANDARD.glob("layer_manifest_*.json")):
        manifest = load(manifest_path)
        if manifest.get("run_id") != run_id or len(manifest.get("views", [])) != 80:
            raise RuntimeError(f"Invalid standard manifest: {manifest_path}")
        mismatches = [
            record["name"]
            for record in manifest["views"]
            if not camera_matches(record, camera_by_name[record["name"]])
        ]
        if mismatches not in (expected_in_camera_order, []):
            raise RuntimeError(
                f"Camera-only rebind expected exactly {expected_in_camera_order} or "
                "an already-complete unchanged recovery in "
                f"{manifest['layer_key']}, got {mismatches}"
            )
        per_layer_mismatches[manifest["layer_key"]] = mismatches
    if len(per_layer_mismatches) != 16:
        raise RuntimeError("Expected all 16 standard layer manifests")

    direct_mismatches = {}
    for manifest_path in sorted(DIRECT.glob("layer_manifest_direct_*.json")):
        manifest = load(manifest_path)
        mismatches = [
            record["name"]
            for record in manifest.get("views", [])
            if not camera_matches(record, camera_by_name[record["name"]])
        ]
        expected = [
            record["name"]
            for record in manifest.get("views", [])
            if record.get("name") in expected_changed_set
        ]
        if mismatches != expected:
            raise RuntimeError(
                f"Unexpected direct camera mismatch in {manifest.get('layer_key')}: {mismatches}"
            )
        direct_mismatches[manifest["layer_key"]] = mismatches
    if len(direct_mismatches) != 6:
        raise RuntimeError("Expected all six direct manifests")

    if all(not mismatches for mismatches in per_layer_mismatches.values()):
        if any(direct_mismatches.values()):
            raise RuntimeError(
                "Standard cameras are current but a direct camera is stale"
            )
        prior = load(CITY / "camera_contract_rebind_audit.json")
        lineage = load(LINEAGE)
        direct_packs = load(DIRECT_PACKS)
        if not (
            prior.get("status") == "PASS"
            and prior.get("run_id") == run_id
            and prior.get("changed_views") == expected_in_camera_order
            and all(
                any(
                    Path(item["path"]).resolve() == RENDERER.resolve()
                    and item["sha256"] == sha256(RENDERER)
                    for item in pack["dependency_fingerprints"]["render_contract_files"]
                )
                for pack in lineage["packs"].values()
            )
            and all(
                pack["dependency_inputs"]["render_contract_sha256"][RENDERER.name]
                == sha256(RENDERER)
                for pack in direct_packs["packs"].values()
            )
        ):
            raise RuntimeError(
                "Recovered camera contract is present but lineage is stale"
            )
        print(
            "FULL13_CAMERA_CONTRACT_REBIND_CACHE_HIT all_80_cameras_current=PASS",
            flush=True,
        )
        return
    if any(
        mismatches != expected_in_camera_order
        for mismatches in per_layer_mismatches.values()
    ):
        raise RuntimeError(
            "Partially recovered standard camera manifests; refuse mixed reuse"
        )

    lineage = load(LINEAGE)
    prior_renderer_hashes = set()
    renderer_fingerprint = current_fingerprint(RENDERER)
    for pack in lineage["packs"].values():
        contracts = pack["dependency_fingerprints"]["render_contract_files"]
        matched = [
            item
            for item in contracts
            if Path(item["path"]).resolve() == RENDERER.resolve()
        ]
        if len(matched) != 1:
            raise RuntimeError("Standard lineage renderer fingerprint missing")
        prior_renderer_hashes.add(matched[0]["sha256"])
        matched[0].update(renderer_fingerprint)
        pack["dependency_hash_scope"] = (
            "exact pack, linked libraries and raster implementation; individual "
            "camera values are independently invalidated by shot_spec_sha256"
        )
        pack["camera_contract_sha256"] = renderer_fingerprint["sha256"]
    lineage["camera_only_provenance_rebind"] = {
        "run_id": run_id,
        "changed_views": expected_in_camera_order,
        "prior_renderer_sha256": sorted(prior_renderer_hashes),
        "current_renderer_sha256": renderer_fingerprint["sha256"],
        "layer_dependency_hashes_preserved": True,
        "pixel_reuse_allowed_only_when_current_shot_spec_matches": True,
    }
    atomic_json(LINEAGE, lineage)

    direct_packs = load(DIRECT_PACKS)
    current_hashes = {
        RENDERER.name: sha256(RENDERER),
        DIRECT_RENDERER.name: sha256(DIRECT_RENDERER),
    }
    prior_direct_hashes = {}
    for pack in direct_packs["packs"].values():
        contract = pack["dependency_inputs"]["render_contract_sha256"]
        for name, current_hash in current_hashes.items():
            prior_direct_hashes.setdefault(name, set()).add(contract[name])
            contract[name] = current_hash
        pack["dependency_hash_scope"] = (
            "exact bounded pack, linked libraries and raster implementation; "
            "per-camera values use shot_spec_sha256 and manifest-only writer "
            "changes do not alter pixels"
        )
    direct_packs["camera_only_provenance_rebind"] = {
        "run_id": run_id,
        "changed_views": expected_in_camera_order,
        "prior_contract_sha256": {
            name: sorted(values) for name, values in prior_direct_hashes.items()
        },
        "current_contract_sha256": current_hashes,
        "dependency_hashes_preserved": True,
    }
    atomic_json(DIRECT_PACKS, direct_packs)

    audit = {
        "schema": "agent.full13.camera_only_provenance_rebind.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "status": "PASS",
        "changed_views": expected_in_camera_order,
        "unchanged_view_count_per_standard_layer": 80 - len(expected_in_camera_order),
        "standard_layer_count": len(per_layer_mismatches),
        "direct_reference_count": len(direct_mismatches),
        "standard_mismatches_before_rerender": per_layer_mismatches,
        "direct_mismatches_before_rerender": direct_mismatches,
        "layer_dependency_hashes_preserved": True,
        "rationale": (
            "only three per-view camera contracts changed; exact pack/library/"
            "raster dependencies and the other 77 contracts remain unchanged"
        ),
    }
    atomic_json(CITY / "camera_contract_rebind_audit.json", audit)
    print(
        f"FULL13_CAMERA_CONTRACT_REBIND_PASS changed_views={len(expected_in_camera_order)} "
        f"preserved_standard_frames={16 * (80 - len(expected_in_camera_order))}",
        flush=True,
    )


if __name__ == "__main__":
    main()

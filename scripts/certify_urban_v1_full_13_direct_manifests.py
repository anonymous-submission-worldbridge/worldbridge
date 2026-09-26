#!/usr/bin/env python3
"""Certify the six one-camera Full-13 direct-reference manifests."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from urban_v1_full_13_direct_specs import DIRECT_VALIDATIONS


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
DIRECT = CITY / "renders/direct_validation_layers"
STANDARD = CITY / "renders/zdepth_layers"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict) -> None:
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, path)


def main() -> None:
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    packs = json.loads(
        (CITY / "render_dependency_packs/direct_validation_packs.json").read_text(
            encoding="utf8"
        )
    )
    run_id = layout["run_id"]
    results = []
    for key, spec in DIRECT_VALIDATIONS.items():
        shot = spec["shot"]
        manifest_path = DIRECT / f"layer_manifest_{key}.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf8"))
        views = [
            record for record in manifest.get("views", []) if record.get("name") == shot
        ]
        if len(views) != 1:
            raise RuntimeError(f"{key} must contain exactly one {shot!r} record")
        record = views[0]
        standard_manifest = json.loads(
            (STANDARD / f"layer_manifest_{spec['layers'][0]}.json").read_text(
                encoding="utf8"
            )
        )
        standard_record = next(
            item for item in standard_manifest["views"] if item["name"] == shot
        )
        bundle = Path(record["outputs"]["bundle"])
        expected_dependency = packs["packs"][key]["dependency_hash"]
        checks = {
            "same_run": manifest.get("run_id") == run_id,
            "exact_contracted_shot": record.get("name") == shot,
            "current_camera_contract": record.get("shot_spec_sha256")
            == standard_record.get("shot_spec_sha256"),
            "dependency_hash": manifest.get("render_dependency_hash")
            == expected_dependency
            == record.get("render_dependency_hash"),
            "bundle_exists": bundle.is_file(),
            "bundle_sha256": bundle.is_file()
            and sha256(bundle) == record.get("sha256", {}).get("bundle"),
            "native_resolution": record.get("render_settings", {}).get("resolution")
            == [1920, 1080],
            "pbr_eevee": record.get("render_settings", {}).get("engine")
            in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"},
            "authoritative_exr": record.get("authoritative_exr_validation", {}).get(
                "status"
            )
            == "PASS",
        }
        if not all(checks.values()):
            raise RuntimeError(
                f"Direct manifest certification failed for {key}: {checks}"
            )
        manifest["views"] = views
        manifest["requested_view_names"] = [shot]
        manifest["completed_view_names"] = [shot]
        manifest["completed_count"] = 1
        manifest["expected_count"] = 1
        manifest["complete"] = True
        manifest["status"] = "PASS"
        manifest["direct_validation_contract"] = {
            "type": "bounded_multi_layer_single_camera_reference",
            "key": key,
            "shot": shot,
            "source_layers": list(spec["layers"]),
            "expected_count": 1,
        }
        manifest["certified_utc"] = (
            datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        )
        manifest["certification_checks"] = checks
        atomic_json(manifest_path, manifest)
        results.append({"key": key, "shot": shot, "status": "PASS", "checks": checks})
        print(f"FULL13_DIRECT_MANIFEST_CERTIFIED key={key} shot={shot}", flush=True)

    audit = {
        "schema": "agent.full13.direct_manifest_certification.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "status": "PASS",
        "reference_count": len(results),
        "results": results,
    }
    atomic_json(CITY / "direct_manifest_certification_audit.json", audit)


if __name__ == "__main__":
    main()

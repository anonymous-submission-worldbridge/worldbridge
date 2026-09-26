#!/usr/bin/env python3
"""Audit and rebind full-13 frames after an exact Blender pack reserialization.

Blender does not byte-serialize dependency-only ``.blend`` packs
deterministically.  Repacking the unchanged production scene can therefore
change the pack SHA (and the conservative dependency hash) even though the
selected placements, transforms, linked libraries, renderer, and pixels are
unchanged.  This gate permits reuse only after the newly serialized packs pass
the exact 80-camera/child-mesh/BVH preflights and every existing frame passes
its original byte, SHA, PBR, camera, and native-EXR contract.
"""

from __future__ import annotations

import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import OpenEXR


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
LAYER_ROOT = CITY / "renders/zdepth_layers"
AUDIT = CITY / "layer_provenance_rebind_audit.json"
LAYERS = (
    "river5_nature",
    "river3_residential",
    "artificial_lake",
    "all45_unique_buildings",
    "education_buildings",
    "commercial_services",
    "industrial",
    "public_safety",
    "residential_delivery",
    "all44_leisure",
    "park_leisure_support",
    "health",
    "full13_unique_urban_fabric",
    "full13_semantic_interiors",
    "full13_public_realm",
    "base",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"Expected JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + f".{os.getpid()}.writing")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, path)


def exr_resolution(path: Path) -> list[int]:
    exr = OpenEXR.File(str(path))
    if not exr.parts:
        raise RuntimeError(f"EXR has no parts: {path}")
    sizes = set()
    for item in exr.parts:
        box = item.header["dataWindow"]
        minimum, maximum = box
        sizes.add(
            (
                int(maximum[0] - minimum[0] + 1),
                int(maximum[1] - minimum[1] + 1),
            )
        )
    if sizes != {(1920, 1080)}:
        raise RuntimeError(f"Wrong EXR part resolution {sorted(sizes)}: {path}")
    return [1920, 1080]


def main() -> None:
    run_id = os.environ.get("C2W_FULL13_RUN_ID", "").strip()
    if not run_id:
        raise RuntimeError("C2W_FULL13_RUN_ID is required")
    generation = load(CITY / "generation_audit.json")
    layout = load(CITY / "layout_plan.json")
    cameras = load(CITY / "camera_preflight.json")
    lineage = load(CITY / "render_dependency_packs/render_pack_lineage.json")
    if not (
        generation.get("status") == "PASS"
        and generation.get("run_id") == run_id
        and layout.get("run_id") == run_id
        and cameras.get("status") == "PASS"
        and cameras.get("run_id") == run_id
        and cameras.get("camera_count_passed") == 80
        and lineage.get("status") == "PASS"
        and lineage.get("run_id") == run_id
        and lineage.get("pack_count") == 16
        and set(lineage.get("packs", {})) == set(LAYERS)
    ):
        raise RuntimeError(
            "Run, generation, camera, or render-pack lineage gate failed"
        )

    production_sha = generation["production_blend_sha256"]
    camera_names = [item["name"] for item in cameras["cameras"]]
    if len(camera_names) != 80 or len(set(camera_names)) != 80:
        raise RuntimeError("Expected 80 unique certified cameras")

    prepared: list[tuple[Path, dict[str, Any], str, str, str]] = []
    files: list[tuple[Path, int, str]] = []
    layer_audits = []
    for layer in LAYERS:
        pack = lineage["packs"][layer]
        current_dependency = str(pack.get("dependency_hash", ""))
        pack_path = Path(pack["target"])
        if not (
            len(current_dependency) == 64
            and pack_path.is_file()
            and pack.get("operation")
            == "dependency-only exact collection-instance repack"
            and all(
                pack.get(key) == 0
                for key in (
                    "mesh_changes",
                    "material_changes",
                    "modifier_changes",
                    "interior_changes",
                    "transform_changes",
                    "source_scale_changes",
                )
            )
            and pack.get("serialized_transform_validation") == "PASS"
            and sha256(pack_path)
            == pack["dependency_fingerprints"]["render_pack"]["sha256"]
        ):
            raise RuntimeError(f"Current exact render pack gate failed: {layer}")
        for fingerprint in pack["dependency_fingerprints"]["dependency_libraries"]:
            if sha256(Path(fingerprint["path"])) != fingerprint["sha256"]:
                raise RuntimeError(
                    f"Dependency library changed: {layer}:{fingerprint['path']}"
                )
        for fingerprint in pack["dependency_fingerprints"]["render_contract_files"]:
            if sha256(Path(fingerprint["path"])) != fingerprint["sha256"]:
                raise RuntimeError(
                    f"Render contract changed: {layer}:{fingerprint['path']}"
                )

        preflight = load(LAYER_ROOT / f"preflight_{layer}.json")
        mesh_preflight = load(LAYER_ROOT / f"camera_mesh_preflight_{layer}.json")
        if not (
            preflight.get("status") == "PASS"
            and preflight.get("scene_revision") == "urban_v1_full_13"
            and preflight.get("production_blend_unchanged") is True
            and preflight.get("production_blend_before", {}).get("sha256")
            == production_sha
            and preflight.get("production_blend_after", {}).get("sha256")
            == production_sha
            and mesh_preflight.get("status") == "PASS"
            and mesh_preflight.get("run_id") == run_id
            and mesh_preflight.get("camera_count_passed") == 80
            and mesh_preflight.get("camera_count_failed") == 0
            and mesh_preflight.get("evaluated_child_mesh_bvh_audit", {}).get("pass")
            is True
        ):
            raise RuntimeError(f"Current exact preflight gate failed: {layer}")

        manifest_path = LAYER_ROOT / f"layer_manifest_{layer}.json"
        manifest = load(manifest_path)
        views = manifest.get("views", [])
        prior_dependencies = {record.get("render_dependency_hash") for record in views}
        prior_dependency = str(manifest.get("render_dependency_hash", ""))
        if not (
            manifest.get("run_id") == run_id
            and manifest.get("scene_revision") == "urban_v1_full_13"
            and manifest.get("status") == "PASS"
            and manifest.get("complete") is True
            and manifest.get("completed_count") == 80
            and manifest.get("expected_count") == 80
            and manifest.get("production_blend_unchanged") is True
            and manifest.get("production_blend_before", {}).get("sha256")
            == production_sha
            and manifest.get("production_blend_after", {}).get("sha256")
            == production_sha
            and len(prior_dependency) == 64
            and prior_dependencies == {prior_dependency}
            and len(views) == 80
            and [record.get("name") for record in views] == camera_names
        ):
            raise RuntimeError(f"Prior layer manifest gate failed: {layer}")

        frame_digest = hashlib.sha256()
        camera_by_name = {item["name"]: item for item in cameras["cameras"]}
        for record in views:
            settings = record.get("render_settings", {})
            validation = record.get("authoritative_exr_validation", {})
            bundle = Path(record.get("outputs", {}).get("bundle", ""))
            expected_bytes = int(record.get("bytes", {}).get("bundle", -1))
            expected_sha = str(record.get("sha256", {}).get("bundle", ""))
            certified_camera = camera_by_name.get(record.get("name"), {})
            recorded_camera = record.get("camera", {})
            current_camera = certified_camera.get("camera", {})
            camera_contract_matches = (
                record.get("filename") == certified_camera.get("filename")
                and record.get("kind") == certified_camera.get("kind")
                and record.get("interior") is certified_camera.get("interior")
                and record.get("placement_ids") == certified_camera.get("placement_ids")
                and record.get("camera_composition_revision")
                == certified_camera.get("camera_composition_revision")
                and record.get("shot_spec_sha256")
                == certified_camera.get("shot_spec_sha256")
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
            if not (
                record.get("status") == "rendered"
                and record.get("layer_key") == layer
                and settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
                and settings.get("resolution") == [1920, 1080]
                and settings.get("samples") == 64
                and settings.get("final_pbr_required") is True
                and settings.get("workbench_final_allowed") is False
                and settings.get("mesh_simplification") is False
                and validation.get("status") == "PASS"
                and validation.get("resolution") == [1920, 1080]
                and validation.get("pixel_content_nondegenerate") is True
                and validation.get("target_pixel_centers_sampled_exactly") is True
                and all(
                    validation.get(key) is False
                    for key in (
                        "resizing",
                        "resampling",
                        "interpolation",
                    )
                )
                and record.get("camera", {}).get("matrix_validation", {}).get("pass")
                is True
                and bundle.is_file()
                and bundle.stat().st_size == expected_bytes
                and len(expected_sha) == 64
                and camera_contract_matches
            ):
                raise RuntimeError(
                    f"Prior native frame contract failed: {layer}:{record.get('name')}"
                )
            files.append((bundle, expected_bytes, expected_sha))
            frame_digest.update(record["name"].encode("utf8"))
            frame_digest.update(expected_sha.encode("ascii"))

        prior_manifest_sha = sha256(manifest_path)
        manifest["render_dependency_hash"] = current_dependency
        for record in views:
            record["render_dependency_hash"] = current_dependency
        manifest["dependency_rebinding"] = {
            "schema": "agent.full13.non_raster_provenance_rebind.v1",
            "run_id": run_id,
            "reason": "exact dependency-only Blender pack reserialization changed container bytes",
            "pixel_content_changed": False,
            "geometry_changed": False,
            "materials_changed": False,
            "modifiers_changed": False,
            "transforms_changed": False,
            "source_scale_changed": False,
            "render_contract_changed": False,
            "prior_dependency_hash": prior_dependency,
            "current_dependency_hash": current_dependency,
            "production_blend_sha256": production_sha,
            "current_pack_sha256": pack["dependency_fingerprints"]["render_pack"][
                "sha256"
            ],
            "serialized_transform_sha256": pack["serialized_transform_sha256"],
            "current_exact_preflight_status": "PASS",
            "current_80_camera_mesh_preflight_status": "PASS",
            "all_80_original_frame_sha256_verified": True,
            "all_80_native_exr_resolutions_verified": True,
            "frame_set_digest": frame_digest.hexdigest(),
        }
        prepared.append(
            (
                manifest_path,
                manifest,
                prior_manifest_sha,
                prior_dependency,
                current_dependency,
            )
        )
        layer_audits.append(
            {
                "layer": layer,
                "prior_dependency_hash": prior_dependency,
                "current_dependency_hash": current_dependency,
                "frame_count": 80,
                "frame_set_digest": frame_digest.hexdigest(),
                "current_pack_sha256": pack["dependency_fingerprints"]["render_pack"][
                    "sha256"
                ],
                "serialized_transform_sha256": pack["serialized_transform_sha256"],
                "exact_preflight": "PASS",
                "camera_mesh_preflight": "PASS",
            }
        )

    # Hash and parse all source bundles before changing any manifest.
    def verify(item: tuple[Path, int, str]) -> tuple[str, list[int]]:
        path, expected_bytes, expected_sha = item
        if path.stat().st_size != expected_bytes or sha256(path) != expected_sha:
            raise RuntimeError(f"Frame changed during provenance audit: {path}")
        return str(path.resolve()), exr_resolution(path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        verified = list(executor.map(verify, files))
    if len(verified) != 1280 or any(size != [1920, 1080] for _, size in verified):
        raise RuntimeError("Expected 1280 native 1920x1080 EXR bundles")

    for manifest_path, manifest, _, _, _ in prepared:
        atomic_json(manifest_path, manifest)

    payload = {
        "schema": "agent.full13.layer_provenance_rebind_audit.v1",
        "created_utc": utc_now(),
        "run_id": run_id,
        "status": "PASS",
        "reason": "exact dependency-only Blender pack reserialization changed container bytes",
        "pixel_content_changed": False,
        "production_blend_sha256": production_sha,
        "layer_count": 16,
        "frame_count": 1280,
        "all_source_frame_sha256_verified": True,
        "all_source_frames_native_1920x1080_exr": True,
        "all_current_exact_preflights_pass": True,
        "all_current_80_camera_mesh_preflights_pass": True,
        "all_pack_mesh_material_modifier_transform_change_counts_zero": True,
        "layers": layer_audits,
        "manifests": [
            {
                "path": str(path.resolve()),
                "prior_sha256": prior_sha,
                "current_sha256": sha256(path),
                "prior_dependency_hash": prior_dependency,
                "current_dependency_hash": current_dependency,
            }
            for path, _, prior_sha, prior_dependency, current_dependency in prepared
        ],
    }
    atomic_json(AUDIT, payload)
    print(
        "FULL13_LAYER_PROVENANCE_REBIND_PASS layers=16 frames=1280 pixel_content_changed=false"
    )


if __name__ == "__main__":
    main()

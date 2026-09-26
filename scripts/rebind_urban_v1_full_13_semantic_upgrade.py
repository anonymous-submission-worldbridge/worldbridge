#!/usr/bin/env python3
"""Selectively rebind unchanged full-13 layers after the semantic-room split.

Only ``full13_semantic_interiors`` and ``full13_public_realm`` are
geometrically invalidated.  The latter is rerendered because the Infinigen
pedestrian factory legitimately varies organic body meshes across builds.
The other 14 layers may retain frames after current 80-camera/BVH preflights and an
exact Blender-data content fingerprint prove that every active collection in
the reserialized general procedural pack is unchanged.  Camera-edited views
remain invalid because their old shot specifications are deliberately not
rewritten here.
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
PRIOR = CITY / "render_runtime/semantic_upgrade_r3/prior"
LAYER_ROOT = CITY / "renders/zdepth_layers"
CHANGED_LAYERS = {"full13_semantic_interiors", "full13_public_realm"}
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
_requested_changed_views = tuple(
    name.strip()
    for name in os.environ.get(
        "C2W_EXPECTED_CHANGED_VIEWS",
        "hospital_outskirts_atrium_near,police_library_near,"
        "artificial_lake_pavilion_near,atm_row_front,"
        "interior_residential_native,interior_commercial_bar",
    ).split(",")
    if name.strip()
)
CHANGED_VIEWS = tuple(
    dict.fromkeys(
        (
            *_requested_changed_views,
            "interior_bank_atrium",
            "interior_hospital_lobby",
        )
    )
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


def atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, path)


def camera_matches(record: dict[str, Any], camera: dict[str, Any]) -> bool:
    recorded = record.get("camera", {})
    certified = camera.get("camera", {})
    return bool(
        record.get("filename") == camera.get("filename")
        and record.get("kind") == camera.get("kind")
        and record.get("interior") is camera.get("interior")
        and record.get("placement_ids") == camera.get("placement_ids")
        and record.get("camera_composition_revision")
        == camera.get("camera_composition_revision")
        and record.get("shot_spec_sha256") == camera.get("shot_spec_sha256")
        and all(
            recorded.get(key) == certified.get(key)
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


def exr_resolution(path: Path) -> list[int]:
    image = OpenEXR.File(str(path))
    sizes = set()
    for part in image.parts:
        minimum, maximum = part.header["dataWindow"]
        sizes.add(
            (
                int(maximum[0] - minimum[0] + 1),
                int(maximum[1] - minimum[1] + 1),
            )
        )
    if sizes != {(1920, 1080)}:
        raise RuntimeError(f"Wrong EXR resolution {sizes}: {path}")
    return [1920, 1080]


def canonical_semantic(record: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(record))
    for key in (
        "source_key",
        "source_path",
        "recursive_object_count",
        "source_recursive_object_count",
        "source_mesh_object_count",
        "source_mesh_polygon_count",
        "minimum_production_part_count",
    ):
        result.pop(key, None)
    metadata = result.get("metadata", {})
    metadata.pop("recursive_object_count", None)
    metadata.pop("minimum_production_part_count", None)
    return result


def validate_layout_change(
    prior: dict[str, Any], current: dict[str, Any]
) -> dict[str, Any]:
    old = {item["placement_id"]: item for item in prior["placements"]}
    new = {item["placement_id"]: item for item in current["placements"]}
    if set(old) != set(new) or len(old) != 80:
        raise RuntimeError("Semantic split changed the 80-placement identity set")
    semantic = {
        "full13_semantic_interior_school_cafeteria",
        "full13_semantic_interior_library_reading_room",
        "full13_semantic_interior_bank_atrium",
        "full13_semantic_interior_hospital_lobby",
    }
    changed = {name for name in old if old[name] != new[name]}
    if changed != semantic:
        raise RuntimeError(f"Unexpected placement records changed: {sorted(changed)}")
    for name in semantic:
        if canonical_semantic(old[name]) != canonical_semantic(new[name]):
            raise RuntimeError(f"Semantic placement transform/bounds changed: {name}")
        if new[name].get("source_key") != "full13_semantic_public_interiors":
            raise RuntimeError(
                f"Semantic placement not routed to new production pack: {name}"
            )
    return {
        "placement_count": len(new),
        "changed_placement_ids": sorted(changed),
        "unchanged_placement_record_count": len(new) - len(changed),
        "semantic_transforms_and_bounds_preserved": True,
    }


def validate_collection_equivalence() -> dict[str, Any]:
    old = load(PRIOR / "procedural_collection_fingerprints.json")
    new = load(
        CITY
        / "render_runtime/semantic_upgrade_r3/current_procedural_collection_fingerprints.json"
    )
    if not (
        old.get("status") == new.get("status") == "PASS"
        and old.get("active_collection_count")
        == new.get("active_collection_count")
        == 15
        and set(old.get("collections", {})) == set(new.get("collections", {}))
    ):
        raise RuntimeError("Procedural collection fingerprint set is invalid")
    mismatches = []
    for name in old["collections"]:
        before = old["collections"][name]
        after = new["collections"][name]
        if before != after:
            mismatches.append({"collection": name, "prior": before, "current": after})
    changed_names = {item["collection"] for item in mismatches}
    expected_changes = {"full13:master:continuous_pedestrian_activity"}
    if changed_names != expected_changes:
        raise RuntimeError(
            f"Unexpected active procedural collection changes: {mismatches[:3]}"
        )
    return {
        "status": "PASS",
        "active_collection_count": 15,
        "unaffected_collection_count": 14,
        "changed_collection_count": 1,
        "changed_collections": sorted(changed_names),
        "prior_pack_sha256": old["source_blend_sha256"],
        "current_pack_sha256": new["source_blend_sha256"],
        "container_sha_changed": old["source_blend_sha256"]
        != new["source_blend_sha256"],
        "unaffected_blender_data_content_identical": True,
        "changed_collection_routed_to_full_rerender": True,
        "scope": "meshes, transforms, modifiers, materials, curves, nested collection instances",
    }


def main() -> None:
    run_id = os.environ.get("C2W_FULL13_RUN_ID", "").strip()
    if not run_id or len(CHANGED_VIEWS) != 8 or len(set(CHANGED_VIEWS)) != 8:
        raise RuntimeError("Run ID and exactly eight changed camera views are required")
    generation = load(CITY / "generation_audit.json")
    prior_generation = load(PRIOR / "generation_audit.json")
    layout = load(CITY / "layout_plan.json")
    prior_layout = load(PRIOR / "layout_plan.json")
    cameras = load(CITY / "camera_preflight.json")
    prior_cameras = load(PRIOR / "camera_preflight.json")
    lineage = load(CITY / "render_dependency_packs/render_pack_lineage.json")
    prior_lineage = load(PRIOR / "render_pack_lineage.json")
    semantic_pack = load(CITY / "asset_packs/full13_semantic_public_interiors.json")
    if not (
        generation.get("run_id")
        == layout.get("run_id")
        == cameras.get("run_id")
        == lineage.get("run_id")
        == semantic_pack.get("run_id")
        == run_id
        and generation.get("status")
        == cameras.get("status")
        == lineage.get("status")
        == semantic_pack.get("status")
        == "PASS"
        and cameras.get("camera_count_passed") == 80
        and lineage.get("pack_count") == 16
        and generation.get("semantic_pack_sha256") == semantic_pack.get("sha256")
        and sha256(Path(semantic_pack["pack"])) == semantic_pack["sha256"]
    ):
        raise RuntimeError(
            "Current generation/camera/lineage/semantic pack gate failed"
        )
    if (
        generation["production_blend_sha256"]
        == prior_generation["production_blend_sha256"]
    ):
        raise RuntimeError(
            "Expected the production Blend to change for the semantic upgrade"
        )
    layout_change = validate_layout_change(prior_layout, layout)
    collection_equivalence = validate_collection_equivalence()

    current_camera = {item["name"]: item for item in cameras["cameras"]}
    old_camera = {item["name"]: item for item in prior_cameras["cameras"]}
    if set(current_camera) != set(old_camera) or len(current_camera) != 80:
        raise RuntimeError("Prior/current camera identity set differs")
    actual_camera_changes = {
        name for name in current_camera if current_camera[name] != old_camera[name]
    }
    if actual_camera_changes != set(CHANGED_VIEWS):
        raise RuntimeError(
            f"Expected camera changes {sorted(CHANGED_VIEWS)}, got {sorted(actual_camera_changes)}"
        )

    files: list[tuple[Path, int, str]] = []
    prepared: list[tuple[Path, dict[str, Any]]] = []
    layers = []
    for layer in LAYERS:
        current_pack = lineage["packs"][layer]
        prior_pack = prior_lineage["packs"][layer]
        if layer in CHANGED_LAYERS:
            if (
                layer == "full13_semantic_interiors"
                and str(Path(semantic_pack["pack"]).resolve())
                not in current_pack["dependency_library_paths"]
            ):
                raise RuntimeError(
                    "Changed semantic layer does not depend on the new pack"
                )
            layers.append(
                {"layer": layer, "action": "FULL_RERENDER_80", "rebound_frames": 0}
            )
            continue
        if (
            str(Path(semantic_pack["pack"]).resolve())
            in current_pack["dependency_library_paths"]
        ):
            raise RuntimeError(
                f"New semantic pack leaked into unchanged layer: {layer}"
            )
        if not (
            current_pack.get("placement_ids") == prior_pack.get("placement_ids")
            and current_pack.get("serialized_transform_sha256")
            == prior_pack.get("serialized_transform_sha256")
            and current_pack.get("serialized_transform_validation") == "PASS"
            and all(
                current_pack.get(key) == 0
                for key in (
                    "mesh_changes",
                    "material_changes",
                    "modifier_changes",
                    "interior_changes",
                    "transform_changes",
                    "source_scale_changes",
                )
            )
        ):
            raise RuntimeError(f"Unchanged layer structure differs: {layer}")
        preflight = load(LAYER_ROOT / f"preflight_{layer}.json")
        mesh_preflight = load(LAYER_ROOT / f"camera_mesh_preflight_{layer}.json")
        production_sha = generation["production_blend_sha256"]
        if not (
            preflight.get("status") == mesh_preflight.get("status") == "PASS"
            and preflight.get("production_blend_before", {}).get("sha256")
            == production_sha
            and preflight.get("production_blend_after", {}).get("sha256")
            == production_sha
            and mesh_preflight.get("run_id") == run_id
            and mesh_preflight.get("camera_count_passed") == 80
            and mesh_preflight.get("camera_count_failed") == 0
            and mesh_preflight.get("evaluated_child_mesh_bvh_audit", {}).get("pass")
            is True
        ):
            raise RuntimeError(f"Current exact preflight failed: {layer}")

        manifest_path = LAYER_ROOT / f"layer_manifest_{layer}.json"
        manifest = load(manifest_path)
        views = manifest.get("views", [])
        prior_dependency = manifest.get("render_dependency_hash")
        current_dependency = current_pack.get("dependency_hash")
        if not (
            manifest.get("run_id") == run_id
            and manifest.get("status") == "PASS"
            and manifest.get("complete") is True
            and manifest.get("completed_count") == manifest.get("expected_count") == 80
            and len(views) == 80
            and isinstance(prior_dependency, str)
            and len(prior_dependency) == 64
            and isinstance(current_dependency, str)
            and len(current_dependency) == 64
            and {item.get("render_dependency_hash") for item in views}
            == {prior_dependency}
        ):
            raise RuntimeError(f"Prior manifest contract failed: {layer}")
        for record in views:
            name = record.get("name")
            reference_camera = (
                old_camera[name] if name in CHANGED_VIEWS else current_camera[name]
            )
            settings = record.get("render_settings", {})
            validation = record.get("authoritative_exr_validation", {})
            bundle = Path(record.get("outputs", {}).get("bundle", ""))
            expected_bytes = int(record.get("bytes", {}).get("bundle", -1))
            expected_sha = str(record.get("sha256", {}).get("bundle", ""))
            if not (
                camera_matches(record, reference_camera)
                and record.get("status") == "rendered"
                and record.get("layer_key") == layer
                and settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
                and settings.get("resolution") == [1920, 1080]
                and settings.get("samples") == 64
                and settings.get("mesh_simplification") is False
                and validation.get("status") == "PASS"
                and validation.get("resolution") == [1920, 1080]
                and validation.get("pixel_content_nondegenerate") is True
                and bundle.is_file()
                and bundle.stat().st_size == expected_bytes
                and len(expected_sha) == 64
            ):
                raise RuntimeError(f"Prior frame contract failed: {layer}:{name}")
            files.append((bundle, expected_bytes, expected_sha))
            record["render_dependency_hash"] = current_dependency
        manifest["render_dependency_hash"] = current_dependency
        manifest["semantic_upgrade_dependency_rebind"] = {
            "run_id": run_id,
            "status": "PASS",
            "changed_geometry_layers": sorted(CHANGED_LAYERS),
            "this_layer_geometry_changed": False,
            "prior_dependency_hash": prior_dependency,
            "current_dependency_hash": current_dependency,
            "current_80_camera_mesh_preflight": "PASS",
            "procedural_collection_content_equivalence": "PASS",
            "changed_camera_views_left_invalid_for_rerender": list(CHANGED_VIEWS),
        }
        prepared.append((manifest_path, manifest))
        layers.append(
            {
                "layer": layer,
                "action": "REBINDED_UNCHANGED_CONTENT",
                "rebound_frames": 80,
                "camera_invalidated_frames": len(CHANGED_VIEWS),
            }
        )

    def verify(item: tuple[Path, int, str]) -> None:
        path, size, expected = item
        if path.stat().st_size != size or sha256(path) != expected:
            raise RuntimeError(f"Frame byte/SHA changed: {path}")
        exr_resolution(path)

    with ThreadPoolExecutor(max_workers=12) as executor:
        list(executor.map(verify, files))
    for path, manifest in prepared:
        atomic(path, manifest)

    audit = {
        "schema": "agent.full13.selective_semantic_upgrade_rebind.v1",
        "created_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "run_id": run_id,
        "status": "PASS",
        "prior_production_blend_sha256": prior_generation["production_blend_sha256"],
        "current_production_blend_sha256": generation["production_blend_sha256"],
        "layout_change": layout_change,
        "procedural_collection_equivalence": collection_equivalence,
        "changed_geometry_layers": sorted(CHANGED_LAYERS),
        "unchanged_geometry_layer_count": 14,
        "unchanged_frame_sha256_verified": len(files),
        "changed_camera_views": list(CHANGED_VIEWS),
        "camera_frames_deliberately_left_invalid": 14 * len(CHANGED_VIEWS),
        "full_layer_frames_deliberately_left_invalid": 2 * 80,
        "layers": layers,
    }
    atomic(CITY / "layer_provenance_rebind_audit.json", audit)
    print(
        f"FULL13_SELECTIVE_SEMANTIC_REBIND_PASS unchanged_files={len(files)} "
        f"pending_full_layers=160 pending_camera={14 * len(CHANGED_VIEWS)}",
        flush=True,
    )


if __name__ == "__main__":
    main()

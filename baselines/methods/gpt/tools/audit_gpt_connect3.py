#!/usr/bin/env python3
"""Integrity and visual sanity audit for the delivered connect3 suite."""
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


from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageStat


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gpt6_astra/connect3"
SCENES = (
    "residential_neighborhood",
    "neighborhood_school",
    "public_library",
    "community_sports_hall",
    "retail_pharmacy",
    "police_station",
    "fire_station",
    "community_hospital",
    "light_factory",
    "delivery_service_hub",
    "community_bank_atm",
    "gas_station_store",
    "riverside_lake_park",
)
EXPECTED_CATEGORIES = {
    "residential area",
    "school",
    "library",
    "gymnasium",
    "shop",
    "pharmacy",
    "police department",
    "fire department",
    "hospital",
    "factory",
    "post office",
    "delivery box",
    "delivery cabinet",
    "bank",
    "ATM",
    "gas station",
    "park",
    "by the lake",
    "Small river",
}


def sha256(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def probe(path: Path):
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_streams",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    streams = json.loads(completed.stdout)["streams"]
    if len(streams) != 1:
        raise RuntimeError(f"unexpected video streams: {path}")
    return streams[0]


def main():
    failures = []
    scenes = []
    category_union = set()
    image_hashes = set()
    totals = {"scenes": 0, "images": 0, "videos": 0, "blend_files": 0, "bytes": 0}
    for scene_id in SCENES:
        root = ROOT / scene_id
        manifest_path = root / "manifest.json"
        if not manifest_path.is_file():
            failures.append(f"{scene_id}: missing manifest")
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        errors = []
        if not manifest.get("build_success") or not manifest.get("render_success"):
            errors.append("success flag false")
        if (
            manifest.get("model_requested") != "gpt-6-astra"
            or manifest.get("reasoning_effort_requested") != "high"
        ):
            errors.append("model/reasoning mismatch")
        if not manifest.get("true_shared_coordinate_3d_scene") or not manifest.get(
            "native_geometry"
        ):
            errors.append("true 3D flags false")
        connectivity = manifest.get("connectivity", {})
        if not connectivity.get("passed") or connectivity.get("blockers"):
            errors.append("connectivity audit failed")
        geometry = manifest.get("geometry", {})
        if (
            geometry.get("mesh_object_count", 0) < 1000
            or geometry.get("vertices_including_linked_instances", 0) < 30_000
        ):
            errors.append("geometry detail floor failed")
        scene_file = root / manifest.get("scene_file", "")
        if not scene_file.is_file() or sha256(scene_file) != manifest.get(
            "scene_sha256"
        ):
            errors.append("scene hash mismatch")
        else:
            totals["blend_files"] += 1
            totals["bytes"] += scene_file.stat().st_size
        records = manifest.get("images", [])
        if len(records) != 24:
            errors.append(f"image record count {len(records)}")
        role_counts = {
            "indoor": 0,
            "outdoor": 0,
            "inside_to_outside": 0,
            "outside_to_inside": 0,
        }
        luminance = []
        local_hashes = set()
        for record in records:
            role = record.get("role", "")
            for prefix in role_counts:
                if role.startswith(prefix):
                    role_counts[prefix] += 1
                    break
            path = root / record.get("file", "")
            if not path.is_file():
                errors.append(f"missing image {path.name}")
                continue
            digest = sha256(path)
            if digest != record.get("sha256"):
                errors.append(f"image hash mismatch {path.name}")
            with Image.open(path) as image:
                if image.size != (1280, 720):
                    errors.append(f"image resolution {path.name}: {image.size}")
                small = image.convert("L").resize((64, 36))
                stat = ImageStat.Stat(small)
                mean, deviation = stat.mean[0], stat.stddev[0]
                luminance.append(
                    {
                        "file": path.name,
                        "mean": round(mean, 3),
                        "stddev": round(deviation, 3),
                    }
                )
                if mean < 5 or mean > 250 or deviation < 5:
                    errors.append(
                        f"visual sanity failed {path.name}: mean={mean:.2f} std={deviation:.2f}"
                    )
            if digest in local_hashes:
                errors.append(f"duplicate image hash {path.name}")
            local_hashes.add(digest)
            image_hashes.add(digest)
            totals["bytes"] += path.stat().st_size
        if role_counts != {
            "indoor": 5,
            "outdoor": 5,
            "inside_to_outside": 7,
            "outside_to_inside": 7,
        }:
            errors.append(f"view role counts {role_counts}")
        video_records = manifest.get("videos", [])
        if len(video_records) != 2:
            errors.append(f"video record count {len(video_records)}")
        video_probes = []
        for record in video_records:
            path = root / record.get("file", "")
            if not path.is_file():
                errors.append(f"missing video {path.name}")
                continue
            if sha256(path) != record.get("sha256"):
                errors.append(f"video hash mismatch {path.name}")
            info = probe(path)
            summary = {
                "file": path.name,
                "codec": info.get("codec_name"),
                "width": int(info.get("width", 0)),
                "height": int(info.get("height", 0)),
                "fps": info.get("r_frame_rate"),
                "frames": int(info.get("nb_frames", 0)),
                "duration": float(info.get("duration", 0)),
            }
            video_probes.append(summary)
            if (
                summary["codec"],
                summary["width"],
                summary["height"],
                summary["fps"],
                summary["frames"],
            ) != ("h264", 960, 540, "12/1", 48):
                errors.append(f"video probe failed {path.name}: {summary}")
            totals["bytes"] += path.stat().st_size
        categories = manifest.get("categories_zh", [])
        category_union.update(categories)
        totals["scenes"] += 1
        totals["images"] += len(records)
        totals["videos"] += len(video_records)
        scenes.append(
            {
                "scene_id": scene_id,
                "title_zh": manifest.get("title_zh"),
                "categories_zh": categories,
                "geometry": geometry,
                "connectivity": connectivity,
                "render": manifest.get("render"),
                "image_role_counts": role_counts,
                "image_luminance": luminance,
                "video_probes": video_probes,
                "passed": not errors,
                "errors": errors,
            }
        )
        failures.extend(f"{scene_id}: {error}" for error in errors)
    if category_union != EXPECTED_CATEGORIES:
        failures.append(f"category coverage differs: got={sorted(category_union)}")
    if (
        totals["scenes"] != 13
        or totals["images"] != 312
        or totals["videos"] != 26
        or totals["blend_files"] != 13
    ):
        failures.append(f"delivery totals invalid: {totals}")
    if len(image_hashes) != 312:
        failures.append(f"global unique image hashes={len(image_hashes)}")
    report = {
        "schema_version": 1,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": not failures,
        "failures": failures,
        "expected_categories_zh": sorted(EXPECTED_CATEGORIES),
        "observed_categories_zh": sorted(category_union),
        "totals": totals,
        "scenes": scenes,
    }
    (ROOT / "audit_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    delivery = {
        "schema_version": 1,
        "method": "gpt6_astra",
        "model_requested": "gpt-6-astra",
        "reasoning_effort_requested": "high",
        "quality_revision": "connect3",
        "audit_passed": not failures,
        "totals": totals,
        "categories_zh": sorted(category_union),
        "scene_ids": list(SCENES),
        "independent_images": True,
        "image_overlays": False,
        "true_shared_coordinate_3d_scenes": True,
        "external_downloads": False,
        "audit_report": "audit_report.json",
    }
    (ROOT / "delivery_manifest.json").write_text(
        json.dumps(delivery, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"passed": not failures, "totals": totals, "failures": failures},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not failures else 2


if __name__ == "__main__":
    raise SystemExit(main())

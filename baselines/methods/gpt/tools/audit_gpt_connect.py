#!/usr/bin/env python3
"""Validate and summarize the GPT-6 Astra high connected-demo package."""
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
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

from PIL import Image, ImageStat


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gpt6_astra/connect"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    errors: list[str] = []
    scenes: list[dict] = []
    files: dict[str, dict] = {}
    for run in sorted(ROOT.glob("demo_*")):
        manifest_path = run / "manifest.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("method") != "gpt6_astra"
            or manifest.get("model_requested") != "gpt-6-astra"
        ):
            errors.append(f"{run.name}: wrong method/model")
        if manifest.get("reasoning_effort_requested") != "high":
            errors.append(f"{run.name}: wrong reasoning effort")
        for key in (
            "generation_success",
            "build_success",
            "render_success",
            "supplemental_render_success",
        ):
            if manifest.get(key) is not True:
                errors.append(f"{run.name}: {key} is not true")
        if manifest.get("connectivity_audit", {}).get("passed") is not True:
            errors.append(f"{run.name}: connectivity audit did not pass")

        blend = run / manifest.get("scene_file", "")
        if not blend.is_file():
            errors.append(f"{run.name}: missing blend")
        else:
            if sha256(blend) != manifest.get("scene_sha256"):
                errors.append(f"{run.name}: blend hash mismatch")
            files[str(blend.relative_to(ROOT))] = {
                "kind": "blend",
                "bytes": blend.stat().st_size,
                "sha256": sha256(blend),
            }

        still_roles = []
        for record in manifest.get("stills", []):
            path = run / record["path"]
            still_roles.append(record["role"])
            if not path.is_file():
                errors.append(f"{run.name}: missing {record['path']}")
                continue
            digest = sha256(path)
            if digest != record.get("sha256") or digest != manifest.get(
                "outputs_sha256", {}
            ).get(record["path"]):
                errors.append(f"{run.name}: image hash mismatch {record['path']}")
            with Image.open(path) as image:
                size = list(image.size)
                stat = ImageStat.Stat(image.convert("RGB"))
                mean = round(sum(stat.mean) / 3.0, 4)
                stddev = round(sum(stat.stddev) / 3.0, 4)
            if size != [1280, 720] or not (5.0 < mean < 250.0 and stddev > 5.0):
                errors.append(f"{run.name}: invalid image {record['path']}")
            files[str(path.relative_to(ROOT))] = {
                "kind": "image",
                "collection": "base",
                "role": record["role"],
                "bytes": path.stat().st_size,
                "sha256": digest,
                "resolution": size,
                "mean_rgb": mean,
                "mean_channel_stddev": stddev,
            }

        supplemental_records = manifest.get("supplemental_stills", [])
        supplemental_paths = []
        supplemental_directions = []
        supplemental_bands: dict[str, Counter] = {}
        for record in supplemental_records:
            path = run / record["path"]
            supplemental_paths.append(record["path"])
            direction = record.get("direction")
            supplemental_directions.append(direction)
            supplemental_bands.setdefault(direction, Counter())[
                record.get("distance_band")
            ] += 1
            if not path.is_file():
                errors.append(f"{run.name}: missing {record['path']}")
                continue
            digest = sha256(path)
            if digest != record.get("sha256") or digest != manifest.get(
                "outputs_sha256", {}
            ).get(record["path"]):
                errors.append(
                    f"{run.name}: supplemental image hash mismatch {record['path']}"
                )
            with Image.open(path) as image:
                size = list(image.size)
                stat = ImageStat.Stat(image.convert("RGB"))
                mean = round(sum(stat.mean) / 3.0, 4)
                stddev = round(sum(stat.stddev) / 3.0, 4)
            if size != [1280, 720] or not (5.0 < mean < 250.0 and stddev > 5.0):
                errors.append(
                    f"{run.name}: invalid supplemental image {record['path']}"
                )
            files[str(path.relative_to(ROOT))] = {
                "kind": "image",
                "collection": "supplemental",
                "direction": direction,
                "role": record.get("role"),
                "distance_band": record.get("distance_band"),
                "horizontal_fov_degrees": record.get("horizontal_fov_degrees"),
                "bytes": path.stat().st_size,
                "sha256": digest,
                "resolution": size,
                "mean_rgb": mean,
                "mean_channel_stddev": stddev,
            }

        video_roles = []
        for record in manifest.get("videos", []):
            path = run / record["path"]
            video_roles.append(record["role"])
            if not path.is_file():
                errors.append(f"{run.name}: missing {record['path']}")
                continue
            digest = sha256(path)
            if digest != record.get("sha256") or digest != manifest.get(
                "outputs_sha256", {}
            ).get(record["path"]):
                errors.append(f"{run.name}: video hash mismatch {record['path']}")
            probe = json.loads(
                subprocess.check_output(
                    [
                        "/usr/bin/ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "stream=codec_name,width,height,avg_frame_rate,nb_frames:format=duration",
                        "-of",
                        "json",
                        str(path),
                    ],
                    text=True,
                )
            )
            stream = probe["streams"][0]
            expected = ("h264", 1280, 720, "24/1", "120")
            observed = (
                stream.get("codec_name"),
                stream.get("width"),
                stream.get("height"),
                stream.get("avg_frame_rate"),
                stream.get("nb_frames"),
            )
            if observed != expected:
                errors.append(f"{run.name}: invalid video {record['path']}: {observed}")
            files[str(path.relative_to(ROOT))] = {
                "kind": "video",
                "role": record["role"],
                "bytes": path.stat().st_size,
                "sha256": digest,
                "codec": stream.get("codec_name"),
                "resolution": [stream.get("width"), stream.get("height")],
                "fps": stream.get("avg_frame_rate"),
                "frames": int(stream.get("nb_frames", 0)),
                "duration_seconds": float(probe["format"]["duration"]),
            }

        if len(still_roles) != 8 or len(set(still_roles)) != 8:
            errors.append(f"{run.name}: expected 8 unique still roles")
        if len(supplemental_paths) != 20 or len(set(supplemental_paths)) != 20:
            errors.append(f"{run.name}: expected 20 unique supplemental still paths")
        if Counter(supplemental_directions) != Counter(
            {"indoor_to_outdoor": 10, "outdoor_to_indoor": 10}
        ):
            errors.append(f"{run.name}: wrong supplemental direction counts")
        expected_bands = {
            "indoor_to_outdoor": Counter({"far": 4, "mid": 4, "near": 2}),
            "outdoor_to_indoor": Counter({"far": 4, "mid": 3, "near": 3}),
        }
        for direction, expected in expected_bands.items():
            if supplemental_bands.get(direction, Counter()) != expected:
                errors.append(f"{run.name}: wrong distance bands for {direction}")
        if video_roles != ["indoor_to_outdoor", "outdoor_to_indoor"]:
            errors.append(f"{run.name}: wrong video roles/order")
        if list(run.glob(".render_frames*")):
            errors.append(f"{run.name}: temporary render frames remain")
        geometry = manifest.get("geometry", {})
        scenes.append(
            {
                "demo_id": run.name,
                "title": manifest.get("title"),
                "logical_seed": manifest.get("logical_seed"),
                "generated_code_sha256": manifest.get("generated_code_sha256"),
                "scene_sha256": manifest.get("scene_sha256"),
                "visible_mesh_objects": geometry.get("visible_mesh_objects"),
                "vertices": geometry.get("vertices"),
                "polygons": geometry.get("polygons"),
                "materials": geometry.get("materials"),
                "connectivity_passed": True,
                "still_roles": still_roles,
                "supplemental_still_count": len(supplemental_paths),
                "supplemental_direction_counts": dict(Counter(supplemental_directions)),
                "supplemental_distance_bands": {
                    direction: dict(counts)
                    for direction, counts in supplemental_bands.items()
                },
                "video_roles": video_roles,
            }
        )

    if len(scenes) != 6:
        errors.append(f"expected 6 scenes, found {len(scenes)}")
    image_count = sum(1 for row in files.values() if row["kind"] == "image")
    base_image_count = sum(
        1
        for row in files.values()
        if row["kind"] == "image" and row.get("collection") == "base"
    )
    supplemental_image_count = sum(
        1
        for row in files.values()
        if row["kind"] == "image" and row.get("collection") == "supplemental"
    )
    video_count = sum(1 for row in files.values() if row["kind"] == "video")
    blend_count = sum(1 for row in files.values() if row["kind"] == "blend")
    if (
        image_count,
        base_image_count,
        supplemental_image_count,
        video_count,
        blend_count,
    ) != (168, 48, 120, 12, 6):
        errors.append(
            f"wrong artifact counts: images={image_count}, videos={video_count}, blends={blend_count}"
        )
    report = {
        "passed": not errors,
        "audited_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "gpt6_astra",
        "model": "gpt-6-astra",
        "reasoning_effort": "high",
        "render_engine": "Cycles",
        "render_device": "OptiX GPU",
        "counts": {
            "scenes": len(scenes),
            "images": image_count,
            "base_images": base_image_count,
            "supplemental_images": supplemental_image_count,
            "videos": video_count,
            "blend_files": blend_count,
        },
        "total_final_artifact_bytes": sum(row["bytes"] for row in files.values()),
        "errors": errors,
        "scenes": scenes,
        "files": dict(sorted(files.items())),
        "tool_sha256": {
            "generator": sha256(
                (BASELINES / "methods/gpt/tools/generate_gpt_connect_demos.py")
            ),
            "renderer": sha256(
                (BASELINES / "methods/gpt/tools/render_gpt_connect_demo.py")
            ),
            "batch_renderer": sha256(
                (BASELINES / "methods/gpt/tools/render_gpt_connect_batch.py")
            ),
            "supplemental_renderer": sha256(
                (BASELINES / "methods/gpt/tools/render_gpt_connect_views.py")
            ),
            "supplemental_batch_renderer": sha256(
                (BASELINES / "methods/gpt/tools/render_gpt_connect_views_batch.py")
            ),
            "auditor": sha256(Path(__file__)),
        },
    }
    write_json(ROOT / "delivery_manifest.json", report)
    print(
        json.dumps(
            {
                key: report[key]
                for key in ("passed", "counts", "total_final_artifact_bytes", "errors")
            },
            indent=2,
        )
    )
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

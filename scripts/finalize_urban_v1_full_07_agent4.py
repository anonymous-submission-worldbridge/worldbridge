"""Validate and register the completed agent4 image/video delivery."""
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


import json
import struct
import subprocess
from pathlib import Path


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07_agent4"
STILLS = [
    "00_complete_route_oblique.png",
    "01_complete_route_orthographic.png",
    "02_bedroom_start_wide.png",
    "03_wait_inside_real_front_door.png",
    "04_pass_real_front_door.png",
    "05_descend_supported_front_stair.png",
    "06_residential_route_context.png",
    "07_crosswalk_context.png",
    "08_commercial_route_context.png",
    "09_arrive_fresh_mart_wide.png",
    "10_first_person_real_door.png",
    "11_first_person_zebra_crossing.png",
    "12_first_person_fresh_mart_arrival.png",
    "13_third_person_residential_wide.png",
    "14_third_person_crosswalk_wide.png",
    "15_third_person_commercial_wide.png",
]
VIDEOS = [
    "urban_v1_full_07_agent4_first_person_ultrawide.mp4",
    "urban_v1_full_07_agent4_third_person_wide.mp4",
]


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf8"))


def _write_json(path: Path, payload) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf8"
    )


def _png_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if header[:8] != b"\x89PNG\r\n\x1a\n":
        raise RuntimeError(f"Invalid PNG signature: {path}")
    return struct.unpack(">II", header[16:24])


def _video_probe(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,avg_frame_rate,nb_frames,duration",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    duration = stream.get("duration") or payload["format"].get("duration")
    return {
        "file": path.name,
        "bytes": path.stat().st_size,
        "codec": stream["codec_name"],
        "width": int(stream["width"]),
        "height": int(stream["height"]),
        "frame_rate": stream["avg_frame_rate"],
        "frame_count": int(stream["nb_frames"]),
        "duration_seconds": round(float(duration), 3),
    }


def main() -> None:
    reports = [_read_json(OUT / f"render_job_gpu{device}.json") for device in (2, 5)]
    for report in reports:
        if report["scene_object_count"] < 6100 or report["proxy_or_compact_scene"]:
            raise RuntimeError(f"Incomplete/proxy render report: {report}")

    stills = []
    for name in STILLS:
        path = OUT / name
        width, height = _png_dimensions(path)
        if path.stat().st_size < 100_000 or (width, height) != (960, 540):
            raise RuntimeError(
                f"Invalid still deliverable: {path}, {width}x{height}, {path.stat().st_size}B"
            )
        stills.append(
            {
                "file": name,
                "bytes": path.stat().st_size,
                "width": width,
                "height": height,
            }
        )

    videos = [_video_probe(OUT / name) for name in VIDEOS]
    for item in videos:
        if (
            item["codec"] != "h264"
            or (item["width"], item["height"]) != (640, 360)
            or item["frame_count"] != 50
            or abs(item["duration_seconds"] - 10.0) > 0.05
            or item["bytes"] < 100_000
        ):
            raise RuntimeError(f"Invalid video deliverable: {item}")

    contact_sheet_path = OUT / "contact_sheet_16_views.jpg"
    if not contact_sheet_path.is_file() or contact_sheet_path.stat().st_size < 100_000:
        raise RuntimeError("Missing or invalid 16-view contact sheet")
    contact_sheet = {
        "file": contact_sheet_path.name,
        "bytes": contact_sheet_path.stat().st_size,
        "layout": "4x4 overview of all production stills",
    }

    collision = _read_json(OUT / "collision_audit.json")
    if not collision["passed"] or collision["violations"] or collision["door_blockers"]:
        raise RuntimeError("Collision audit does not pass")

    blend = OUT / "urban_v1_full_07_agent4.blend"
    summary = {
        "status": "PASS",
        "complete_non_proxy_scene": True,
        "complete_scene_blend": str(blend),
        "complete_scene_blend_bytes": blend.stat().st_size,
        "generator_entry": str(ROOT / "scripts/generate_urban_v1_full_07.py"),
        "render_engine": "Cycles/OptiX",
        "authorized_gpus_used": [2, 5],
        "scene_object_count": min(item["scene_object_count"] for item in reports),
        "still_count": len(stills),
        "video_count": len(videos),
        "stills": stills,
        "videos": videos,
        "contact_sheet": contact_sheet,
        "collision_audit": collision,
        "render_reports": [f"render_job_gpu{device}.json" for device in (2, 5)],
    }
    _write_json(OUT / "delivery_summary.json", summary)

    audit_path = OUT / "generation_audit.json"
    audit = _read_json(audit_path)
    audit["renders"] = stills + videos
    audit["render_files_complete"] = True
    audit["agent4_render_delivery"] = summary
    _write_json(audit_path, audit)

    manifest_path = OUT / "mission_manifest.json"
    manifest = _read_json(manifest_path)
    manifest["completed_render_delivery"] = summary
    _write_json(manifest_path, manifest)
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()

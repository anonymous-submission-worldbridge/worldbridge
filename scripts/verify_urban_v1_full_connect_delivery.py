"""Verify every expected image/video and summarize the actual deliverable."""
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"
SCENES = [
    "fresh_mart",
    "corner_kitchen",
    "lemon_coffee",
    "mcdonalds",
    "copper_tap",
    "hawthorn",
]
STILLS = [
    "exterior",
    "courtyard",
    "interior",
    "inside_to_outside",
    "outside_to_inside",
    "detail",
]
VIDEOS = ["exterior", "interior", "inside_to_outside", "outside_to_inside"]
errors = []
reports = []
for name in SCENES:
    directory = OUT / name
    report = {"scene": name, "images": [], "videos": []}
    geometry = json.loads((directory / "geometry_audit.json").read_text())
    if not geometry["pass"]:
        errors.append(name + ": geometry audit failed")
    if not (directory / "scene.blend").exists():
        errors.append(name + ": missing blend")
    for view in STILLS:
        path = directory / "images" / (view + ".png")
        if not path.exists():
            errors.append(str(path) + ": missing")
            continue
        with Image.open(path) as im:
            im.load()
            size = im.size
            stat = ImageStat.Stat(im.convert("RGB").resize((160, 90)))
            variation = max(stat.stddev)
        if size != (1920, 1080) or variation < 8:
            errors.append(str(path) + ": invalid image dimensions or blank image")
        report["images"].append(
            {"file": str(path.relative_to(OUT)), "size": size, "stddev": variation}
        )
    for view in VIDEOS:
        path = directory / "videos" / (view + ".mp4")
        if not path.exists():
            errors.append(str(path) + ": missing")
            continue
        probe = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-show_streams",
                    "-of",
                    "json",
                    str(path),
                ]
            )
        )
        stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
        frames = int(stream["nb_read_frames"])
        if (
            (stream["width"], stream["height"]) != (1280, 720)
            or frames != 72
            or stream["r_frame_rate"] != "24/1"
        ):
            errors.append(str(path) + ": unexpected video format")
        subprocess.run(
            ["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True
        )
        checksum = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                str(path),
                "-vf",
                r"select=eq(n\,0)+eq(n\,36)+eq(n\,71)",
                "-vsync",
                "0",
                "-f",
                "framemd5",
                "-",
            ]
        ).decode()
        hashes = [
            line.rsplit(",", 1)[-1].strip()
            for line in checksum.splitlines()
            if line and not line.startswith("#")
        ]
        if len(set(hashes)) != 3:
            errors.append(str(path) + ": camera motion not verified")
        report["videos"].append(
            {
                "file": str(path.relative_to(OUT)),
                "resolution": [stream["width"], stream["height"]],
                "frames": frames,
                "fps": 24,
                "duration_seconds": float(stream["duration"]),
                "distinct_sampled_frames": len(set(hashes)),
            }
        )
    reports.append(report)
result = {
    "complete": not errors,
    "errors": errors,
    "scene_count": len(reports),
    "image_count": sum(len(r["images"]) for r in reports),
    "video_count": sum(len(r["videos"]) for r in reports),
    "scene_files": 6,
    "no_downloads": True,
    "render_engine": "Cycles OptiX",
    "image_overlays": False,
    "image_collages": False,
    "total_bytes": sum(p.stat().st_size for p in OUT.rglob("*") if p.is_file()),
    "scenes": reports,
}
(OUT / "delivery_manifest.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2)
)
print(
    json.dumps(
        {k: v for k, v in result.items() if k != "scenes"}, ensure_ascii=False, indent=2
    )
)
raise SystemExit(0 if result["complete"] else 1)

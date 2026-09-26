"""Validate the complete delivery against the original view inventory."""
from pathlib import Path
import json, subprocess, hashlib
from PIL import Image, ImageStat

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
SRC = BASE / "community_reading_park"
OUT = BASE / "community_reading_park2"
a = json.loads((SRC / "scene_manifest.json").read_text())
b = json.loads((OUT / "scene_manifest.json").read_text())
assert a["shots"] == b["shots"]
expected = {p.name for p in (SRC / "images").glob("*.png")}
actual = {p.name for p in (OUT / "images").glob("*.png")}
assert expected == actual == {n + ".png" for n in a["shots"]}
report = dict(
    passed=True, cameras_unchanged=True, image_count=len(actual), images=[], videos=[]
)
for name in sorted(actual):
    p = OUT / "images" / name
    with Image.open(p) as im:
        im.load()
        assert im.size == (1920, 1080)
        assert max(ImageStat.Stat(im.convert("RGB")).stddev) > 5
    report["images"].append(
        dict(
            file="images/" + name,
            bytes=p.stat().st_size,
            sha256=hashlib.sha256(p.read_bytes()).hexdigest(),
        )
    )
expected = {p.name for p in (SRC / "videos").glob("*.mp4")}
actual = {p.name for p in (OUT / "videos").glob("*.mp4")}
assert expected == actual
for name in sorted(actual):
    p = OUT / "videos" / name
    result = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,nb_frames,r_frame_rate,duration",
                "-of",
                "json",
                str(p),
            ],
            text=True,
        )
    )["streams"][0]
    assert (
        result["width"],
        result["height"],
        int(result["nb_frames"]),
        result["r_frame_rate"],
    ) == (1280, 720, 96, "24/1")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-threads", "2", "-i", str(p), "-f", "null", "-"],
        check=True,
    )
    report["videos"].append(dict(file="videos/" + name, **result))
assets = json.loads((OUT / "asset_replacement_manifest.json").read_text())
assert assets["grounding_passed"]
report["visible_native_counts"] = assets["visible_native_counts"]
report["grounding_passed"] = True
report["source_blend_sha256"] = hashlib.sha256(
    (SRC / "scene.blend").read_bytes()
).hexdigest()
report["output_blend_sha256"] = hashlib.sha256(
    (OUT / "scene.blend").read_bytes()
).hexdigest()
(OUT / "delivery_validation.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)
print(
    json.dumps(
        dict(
            passed=True,
            images=len(report["images"]),
            videos=len(report["videos"]),
            counts=report["visible_native_counts"],
        )
    )
)

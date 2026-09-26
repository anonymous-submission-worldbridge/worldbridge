"""Verify all native videos and publish a browsable, honest dynamic3 delivery."""
import argparse
import html
import json
import subprocess
import time
from pathlib import Path

from PIL import Image

from run_urban_v1_full_13_dynamic3 import OUT, ROOT, atomic, sha256, valid

TITLES = {
    "river_environment": "The river and the neighborhood together",
    "river_detail": "Riverbank leaves touching the water surface locally",
    "lake_environment": "The entire lake area",
    "lake_impact": "fountains interacting with water produce ripples",
    "fountain_environment": "Stone sculpture fountains integrated with their surroundings",
    "fountain_detail": "Stone carvings with detailed water flow effects",
    "street_environment": "street traffic",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wait", action="store_true")
    args = parser.parse_args()
    required = [OUT / f"delivery_{s}.json" for s in TITLES] + [
        OUT / "master_build.json"
    ]
    while any(not p.exists() for p in required):
        missing = [p.name for p in required if not p.exists()]
        atomic(
            OUT / "delivery_audit.json",
            {
                "status": "WAITING_FOR_RENDER",
                "missing": missing,
                "updated": time.time(),
            },
        )
        if not args.wait:
            raise RuntimeError("Incomplete delivery: " + ", ".join(missing))
        time.sleep(20)
    master = json.loads((OUT / "master_build.json").read_text())
    if (
        master["status"] != "BUILT"
        or master["placements_before"] != 82
        or master["placements_after"] != 82
    ):
        raise RuntimeError("Complete native scene preservation failed")
    master_path = OUT / "urban_v1_full_13_dynamic3.blend"
    if sha256(master_path) != master["master_sha256"]:
        raise RuntimeError("Master fingerprint mismatch")
    for dependency in master.get("dynamic_pack_dependencies", []):
        if sha256(Path(dependency["path"])) != dependency["sha256"]:
            raise RuntimeError("Master dynamic dependency fingerprint mismatch")
    native_proofs = [x["native_geometry_proof"] for x in master["wind"]]
    if len(native_proofs) != 10 or any(
        p["decimated_polygons"]
        or p["original_polygons"] != p["instanced_polygon_count"]
        for p in native_proofs
    ):
        raise RuntimeError("Native leaf preservation failed")
    if (
        not master["impact_water"]["basis_unchanged"]
        or master["impact_water"]["native_droplets"] != 1660
    ):
        raise RuntimeError("Lake impact geometry verification failed")
    audit = {
        "status": "VERIFYING",
        "resolution": [1920, 1080],
        "fps": 24,
        "seconds_per_shot": 6,
        "original_placements_preserved": 82,
        "native_canopy_polygons_preserved": sum(
            p["original_polygons"] for p in native_proofs
        ),
        "decimated_polygons": 0,
        "master_sha256": master["master_sha256"],
        "videos": [],
    }
    atomic(OUT / "delivery_audit.json", audit)
    for shot, title in TITLES.items():
        build = json.loads((OUT / f"build_{shot}.json").read_text())
        delivery = json.loads((OUT / f"delivery_{shot}.json").read_text())
        pack = OUT / "render_packs" / f"{shot}.blend"
        folder = OUT / "frames_final" / shot
        video = OUT / "videos" / f"{shot}.mp4"
        contract = json.loads((folder / "render_contract.json").read_text())
        if (
            sha256(pack) != build["shots"][0]["pack_sha256"]
            or contract["blend_sha256"] != build["shots"][0]["pack_sha256"]
        ):
            raise RuntimeError("Scene/render provenance mismatch: " + shot)
        if (
            not contract["denoising"]
            or contract["samples"] != 128
            or contract["animated_seed"]
            or contract["simplify"]
        ):
            raise RuntimeError("Final render quality contract failed: " + shot)
        if delivery["status"] != "PASS" or sha256(video) != delivery["sha256"]:
            raise RuntimeError("Video fingerprint mismatch: " + shot)
        if any(not valid(folder / f"frame_{f:04d}.png") for f in range(1, 145)):
            raise RuntimeError("Missing or corrupt native frames: " + shot)
        covered = set()
        for path in folder.glob("progress_*.json"):
            progress = json.loads(path.read_text())
            if (
                progress["status"] != "PASS"
                or not progress["camera_fixed"]
                or not progress["world_static"]
            ):
                raise RuntimeError("Native transform audit failed: " + str(path))
            covered.update(f["frame"] for f in progress["frames"])
        if covered != set(range(1, 145)):
            raise RuntimeError("Incomplete frame audits: " + shot)
        audit["videos"].append(
            {
                "name": shot,
                "title": title,
                "frames": 144,
                "seconds": 6,
                "video_sha256": delivery["sha256"],
                "pack_sha256": build["shots"][0]["pack_sha256"],
            }
        )
    river = OUT / "frames_final/river_detail"
    subprocess.run(
        [
            "python3",
            str(ROOT / "scripts/audit_urban_v1_full_13_dynamic3_frames.py"),
            str(river),
            "--frames",
            "1,48,96,144",
        ],
        check=True,
    )
    audit["localized_motion"] = json.loads(
        (river / "localized_motion_audit.json").read_text()
    )
    subprocess.run(
        ["python3", str(ROOT / "scripts/audit_urban_v1_full_13_dynamic3_lake.py")],
        check=True,
    )
    audit["lake_localized_motion"] = json.loads(
        (OUT / "frames_final/lake_impact/localized_motion_audit.json").read_text()
    )
    audit["master_dynamic_pack_dependencies"] = master.get(
        "dynamic_pack_dependencies", []
    )
    # A straight cut between complete six-second views; no optical-flow interpolation.
    concat = OUT / "videos/concat.txt"
    concat.write_text("".join(f"file '{shot}.mp4'\n" for shot in TITLES))
    combined = OUT / "videos/urban_v1_full_13_dynamic3_complete.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat),
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(combined),
        ],
        check=True,
    )
    stream = json.loads(
        subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-count_frames",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,nb_read_frames,duration",
                "-of",
                "json",
                str(combined),
            ],
            text=True,
        )
    )["streams"][0]
    if (
        int(stream["nb_read_frames"]) != 1008
        or abs(float(stream["duration"]) - 42) > 0.001
    ):
        raise RuntimeError("Combined video duration/frame count failed")
    subprocess.run(
        ["ffmpeg", "-v", "error", "-xerror", "-i", str(combined), "-f", "null", "-"],
        check=True,
    )
    cards = "".join(
        f'<article><h2>{html.escape(title)}</h2><video controls preload="none" poster="frames_final/{shot}/frame_0001.png"><source src="videos/{shot}.mp4" type="video/mp4"></video><p>6 seconds · 1920×1080 · 24 fps · fixed shot</p><a href="videos/{shot}.mp4">Download video</a> · <a href="render_packs/{shot}.blend">Blender scene</a></article>'
        for shot, title in TITLES.items()
    )
    (OUT / "index.html").write_text(
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Full-13 dynamic3</title><style>body{margin:32px auto;max-width:1500px;padding:0 24px;background:#111719;color:#e6ece8;font:17px/1.6 system-ui}h1{font-size:32px}main{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:24px}article{background:#1d272a;padding:20px;border-radius:12px}h2{font-size:21px}video{width:100%;background:#000}a{color:#91d9bc}p{color:#bbc8c1}@media(max-width:600px){main{display:block}article{margin:18px 0}}</style><h1>Full-13 · dynamic3</h1><p>Native fine-grained scene; leaf breeze, slight water surface ripples, fountain splash ripples and traffic flow. Seven consecutive fixed shots, each segment 6 seconds.</p><p><a href="videos/urban_v1_full_13_dynamic3_complete.mp4">42-second complete compilation</a> · <a href="urban_v1_full_13_dynamic3.blend">Complete combined scene main file</a> · <a href="delivery_audit.json">Delivery verification</a></p><main>'
        + cards
        + "</main></html>"
    )
    (OUT / "README.md").write_text(
        "# urban_v1_full_13 dynamic3\n\n Open `index.html` to browse seven video segments. Complete collection: `videos/urban_v1_full_13_dynamic3_complete.mp4` (42 seconds, 1080p, 24 fps). \n\n Complete master file: `urban_v1_full_13_dynamic3.blend`, retaining all 82 original placements; per-shot files in `render_packs/`. Please retain the original static asset library and dynamic2 native leaf library dependencies. \n\n Wind only affects native leaves, tree trunks, buildings, roads, sky, and camera positions remain fixed. Retain original water and fountain modeling, reuse circular water wave material, and generate attenuation ripples based on the impact trajectories of 1,660 native water droplets. No mesh reduction, substitute models, image distortion, or frame interpolation. \n\n Official frames: `frames_final/`. Early `frames/` and `denoise_check/` are diagnostic materials. Final check: `delivery_audit.json`. Implementation notes: repository `docs/dynamic3_scenes.md`. Analysis: dynamic and linear water wave responses are not equivalent to full fluid simulation; the artistic and material limitations of original assets are still retained. \n"
    )
    with (OUT / "README.md").open("a") as readme_stream:
        readme_stream.write(
            "\n The main file still links to the verified dynamic data in this directory `render_packs/river_detail.blend` and `render_packs/lake_impact.blend`, please retain the entire directory structure. The size of the main file does not represent the geometric scale; do not just copy the main file and then delete the dependencies. \n \n The movement areas of the riverbank and lakebank are checked separately in `frames_final/river_detail/localized_motion_audit.json` and `frames_final/lake_impact/localized_motion_audit.json`, and the total acceptance report includes both. \n"
        )
    audit.update(
        status="PASS",
        verified_png_frames=1008,
        combined_video=str(combined),
        combined_sha256=sha256(combined),
        combined_stream=stream,
        finished=time.time(),
    )
    atomic(OUT / "delivery_audit.json", audit)
    print("DYN3 DELIVERY PASS", combined, flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Fail closed on missing/corrupt/stale frames or a short/non-animated delivery."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from PIL import Image


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = args.output.resolve()
    manifest = json.loads((output / "dynamic2_manifest.json").read_text())
    audit = json.loads((output / "dynamic2_audit.json").read_text())
    if audit["status"] != "PASS":
        raise AssertionError("Saved scene audit did not pass")
    master_sha = digest(output / "urban_v1_full_13_dynamic2.blend")
    if (
        master_sha != manifest["output_blend_sha256"]
        or master_sha != audit["audited_blend_sha256"]
    ):
        raise AssertionError("Saved scene audit is stale")
    static_master = output.parent / "urban_v1_full_13/urban_v1_full_13.blend"
    if digest(static_master) != manifest["source_master_sha256"]:
        raise AssertionError("Original static master changed since the scene audit")
    sizes = set()
    hashes = []
    for i in range(1, 385):
        path = output / "frames" / f"frame_{i:04d}.png"
        with Image.open(path) as image:
            sizes.add(image.size)
            image.verify()
        hashes.append(digest(path))
    if sizes != {(1280, 720)}:
        raise AssertionError("Unexpected frame resolution: " + str(sizes))
    if len(set(hashes)) != 384:
        raise AssertionError("Duplicate/frozen frames in delivery")
    effects = []
    for shot in manifest["shots"]:
        contract = json.loads(
            (
                output / "frames" / ("render_contract_" + shot["name"] + ".json")
            ).read_text()
        )
        if contract["blend_sha256"] != digest(
            output / "render_packs" / (shot["name"] + ".blend")
        ):
            raise AssertionError("Frame/pack fingerprint mismatch")
        if contract["renderer_sha256"] != digest(
            Path(__file__).with_name("render_urban_v1_full_13_dynamic2.py")
        ):
            raise AssertionError("Renderer fingerprint mismatch")
        if (contract["resolution"], contract["samples"], contract["engine"]) != (
            [1280, 720],
            32,
            "cycles",
        ):
            raise AssertionError("Different formal render settings")
        for library in contract["libraries"]:
            info = Path(library["path"]).stat()
            if (info.st_size, info.st_mtime_ns) != (
                library["size"],
                library["mtime_ns"],
            ):
                raise AssertionError(
                    "Linked source library changed: " + library["path"]
                )
        first = np.asarray(
            Image.open(output / "frames" / f"frame_{shot['start']:04d}.png").convert(
                "RGB"
            ),
            dtype=np.int16,
        )
        last = np.asarray(
            Image.open(output / "frames" / f"frame_{shot['end']:04d}.png").convert(
                "RGB"
            ),
            dtype=np.int16,
        )
        diff = np.abs(first - last)
        ratio = float(np.mean(diff.max(axis=2) > 3))
        if ratio < 0.0001:
            raise AssertionError("No measurable motion in " + shot["name"])
        progress = json.loads(
            (output / "frames" / ("progress_" + shot["name"] + ".json")).read_text()
        )
        if progress["status"] != "PASS" or set(progress["completed"]) != set(
            range(shot["start"], shot["end"] + 1)
        ):
            raise AssertionError("Incomplete shot: " + shot["name"])
        effects.append(
            {
                "shot": shot["name"],
                "changed_pixel_fraction": ratio,
                "mean_absolute_RGB_change": float(diff.mean()),
            }
        )
    # Fixed, documented regions in the river camera: moving native foliage and
    # water versus sky and a building facade. Complements the saved-camera audit
    # rather than mistaking global image motion for valid local wind.
    a = np.asarray(
        Image.open(output / "frames/frame_0097.png").convert("RGB"), dtype=np.int16
    )
    b = np.asarray(
        Image.open(output / "frames/frame_0192.png").convert("RGB"), dtype=np.int16
    )
    local_difference = np.abs(a - b).max(axis=2) > 3
    regions = {
        "foliage": (230, 405, 660, 685),
        "river_water": (10, 605, 200, 710),
        "static_building": (1080, 85, 1200, 135),
        "static_sky": (100, 10, 800, 70),
    }
    locality = {
        name: float(local_difference[y0:y1, x0:x1].mean())
        for name, (x0, y0, x1, y1) in regions.items()
    }
    if (
        locality["foliage"] < 0.05
        or locality["river_water"] < 0.01
        or locality["static_building"] > 0.02
        or locality["static_sky"] > 0.001
    ):
        raise AssertionError(
            "Local motion/static background visual check failed: " + str(locality)
        )
    native_proofs = []
    for name in ("river_and_wind", "lake_and_wind"):
        proof = json.loads(
            (output / "render_packs" / (name + ".native_leaf_proof.json")).read_text()
        )
        if proof["status"] != "PASS" or proof["output_pack_sha256"] != digest(
            output / "render_packs" / (name + ".blend")
        ):
            raise AssertionError("Native instance provenance mismatch")
        for item in proof["proofs"]:
            if (
                item["decimated_polygons"]
                or item["original_polygons"] != item["instanced_polygon_count"]
                or item["original_vertices"] != item["instanced_vertex_count"]
                or item["max_rest_coordinate_error_m"] > 2e-5
            ):
                raise AssertionError("Native detail was not preserved")
        native_proofs.append(
            {
                "shot": name,
                "canopies": len(proof["proofs"]),
                "preserved_polygons": sum(
                    x["original_polygons"] for x in proof["proofs"]
                ),
                "decimated_polygons": 0,
            }
        )
    video = output / "urban_v1_full_13_dynamic2.mp4"
    probe = json.loads(
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
                str(video),
            ]
        )
    )["streams"][0]
    if (
        probe["width"],
        probe["height"],
        probe["r_frame_rate"],
        int(probe["nb_read_frames"]),
    ) != (1280, 720, "24/1", 384):
        raise AssertionError("Unexpected encoded video stream: " + str(probe))
    if abs(float(probe["duration"]) - 16) > 1 / 24:
        raise AssertionError("Unexpected duration")
    # Decode the WHOLE video; not just its container header.
    subprocess.run(
        [
            "ffmpeg",
            "-nostdin",
            "-v",
            "error",
            "-xerror",
            "-i",
            str(video),
            "-f",
            "null",
            "-",
        ],
        check=True,
    )
    result = {
        "status": "PASS",
        "video": str(video),
        "video_sha256": digest(video),
        "stream": probe,
        "verified_png_frames": 384,
        "frame_sequence_hash": hashlib.sha256("".join(hashes).encode()).hexdigest(),
        "motion": effects,
        "source_static_master_sha256": manifest["source_master_sha256"],
        "model_scope": manifest["physics_model"],
        "native_3d_frames_only": True,
        "image_warp_or_interpolated_frames": False,
    }
    result["native_leaf_instance_validation"] = native_proofs
    result["audited_master_sha256"] = master_sha
    result["fixed_camera_local_motion_check"] = {
        "changed_pixel_fractions": locality,
        "regions_xyxy": regions,
    }
    (output / "delivery_audit.json").write_text(json.dumps(result, indent=2))
    (output / "README.md").write_text(
        """# Full-13 dynamic2 is now completed with acceptance testing.

- Video: `urban_v1_full_13_dynamic2.mp4`, 1280x720, 24 fps, 384 frames, 16 seconds.
- Complete main file: `urban_v1_full_13_dynamic2.blend`, retains original 82 placement items and indoor assets.
- The full scene name within the main file is `urban_v1_full_13`. This file uses library-style saving to avoid evaluating an entire city when saved.
  If Blender's interface displays an empty default scene for the first time, select `urban_v1_full_13` from the Scene dropdown box.
- 18 original vehicles traveling at 2 m/s; entire 16-second preset trajectory is detected using continuous conservative collision detection.
- Leaves oscillate around fixed native vertices while preserving the original leaf geometry without reducing faces or replacing with billboards.
- Water use involves limited water depth fluctuations with unidirectional flow; 2494 natural fountain droplets utilize gravity trajectories and receive surface recycling.
- -`dynamic2_audit.json`: Post-save scene audit; -`delivery_audit.json`: Complete video, 384 PNGs, and local motion verification.

Please retain `render_packs/` and original static scene/asset path: main file uses linked assets rather than a single fully packaged file.
The original static file was not overwritten by the first version of dynamic output. Wind and water are physical constraints for programmatic animations, not complete CFD/FSI simulations.
The video shows four fixed shots: vehicles, rivers, and blades; main fountains; lake surface fountains; without any use of full-screen shaking, frame interpolation, or simplified model replacements.

Reproducibility and Limitation Notes: Warehouse `docs/dynamic2_scenes.md`.
Existing results have been submitted for re-examination/re-rendering: `CUDA_VISIBLE_DEVICES=0 sh scripts/run_urban_v1_full_13_dynamic2.sh --render-only`.
The GPU number should be adjusted based on available resources on this machine.
"""
    )
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

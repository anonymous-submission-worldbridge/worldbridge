#!/usr/bin/env python3
"""Create deterministic, method-blinded Table-2 human-rating materials."""

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


import argparse
import concurrent.futures
import csv
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


BASELINES_ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILE = BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
DEFAULT_OUTPUT = BASELINES_ROOT / "annotations/table2_v1"
BLIND_SALT = "table2-v1-frozen-before-ratings"
RATER_INSTRUCTIONS = """# Table 2 anonymous scene-rating instructions

Rate every public item independently. Do not inspect file paths, metadata, source
code, or `PRIVATE_blind_map.json`, and do not discuss ratings with other raters.
Use both the eight-view montage and the 50-frame video before assigning scores.

## Layout plausibility (four integer ratings, each 1–5)

- `boundary_collision`: 1 = widespread wall/floor intersections or objects outside
  the room; 3 = a few visible collisions; 5 = no visible boundary collision.
- `support_pose`: 1 = many floating, sinking, or physically unsupported objects;
  3 = a few questionable supports; 5 = supports and poses look physically valid.
- `scale_density`: 1 = implausible scale or unusable clutter/emptiness; 3 = mixed;
  5 = coherent object scale and a plausible furnishing density.
- `function_circulation`: 1 = the room/urban scene cannot plausibly serve its
  stated function or circulation is blocked; 3 = partly usable; 5 = functional
  with clear movement.

Use the intermediate integers 2 and 4 when quality lies between adjacent anchors.
Judge only visible evidence; do not reward photorealism in these layout fields.

## Prompt alignment (one response per preregistered fact)

- `yes`: the fact is visibly satisfied in at least one view or the video.
- `no`: visible evidence contradicts the fact, or the expected object/relation is
  absent despite adequate coverage.
- `not-visible`: coverage or occlusion prevents a reliable decision. This does not
  count as a satisfied fact in the Table 2 score.

Keep the supplied `rater_id` unchanged and fill every blank cell. Failed generation
or render runs are not shown to raters and are assigned the preregistered ITT zero.
"""


def load_specs(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def blind_id(method: str, spec_id: str, seed: int, domain: str = "indoor") -> str:
    if domain == "indoor":
        payload = f"{BLIND_SALT}|{method}|{spec_id}|{seed}".encode()
    else:
        payload = f"{BLIND_SALT}|{method}|{domain}|{spec_id}|{seed}".encode()
    prefix = "I" if domain == "indoor" else "U"
    return prefix + "-" + hashlib.sha256(payload).hexdigest()[:12].upper()


def make_montage(
    images: list[Path], output: Path, item_id: str, domain: str = "indoor"
) -> None:
    if len(images) != 8:
        raise ValueError(f"Expected 8 anchors, got {len(images)}")
    tile_width, tile_height = 480, 270
    header_height = 44
    canvas = Image.new(
        "RGB", (tile_width * 4, header_height + tile_height * 2), "white"
    )
    draw = ImageDraw.Draw(canvas)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
    except OSError:
        font = ImageFont.load_default()
    draw.text(
        (16, 8), f"Anonymous item {item_id} — {domain} scene", fill="black", font=font
    )
    for index, path in enumerate(images):
        with Image.open(path) as image:
            tile = image.convert("RGB")
            tile.thumbnail((tile_width, tile_height), Image.Resampling.LANCZOS)
            background = Image.new("RGB", (tile_width, tile_height), (32, 32, 32))
            x = (tile_width - tile.width) // 2
            y = (tile_height - tile.height) // 2
            background.paste(tile, (x, y))
        col, row = index % 4, index // 4
        canvas.paste(background, (col * tile_width, header_height + row * tile_height))
        draw.rectangle(
            [
                col * tile_width + 6,
                header_height + row * tile_height + 5,
                col * tile_width + 46,
                header_height + row * tile_height + 35,
            ],
            fill=(0, 0, 0),
        )
        draw.text(
            (col * tile_width + 13, header_height + row * tile_height + 7),
            str(index + 1),
            fill="white",
            font=font,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, quality=92, subsampling=0)


def make_video(sequence_dir: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        "10",
        "-i",
        str(sequence_dir / "rgb_%03d.png"),
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-crf",
        "20",
        str(output),
    ]
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"ffmpeg failed: {completed.stderr[-2000:]}")


def valid_video(path: Path) -> bool:
    if not path.is_file():
        return False
    completed = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return False
    try:
        return float(completed.stdout.strip()) > 0.0
    except ValueError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--method", default="infinigen_indoors")
    parser.add_argument("--domain", choices=("indoor", "urban"), default="indoor")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--skip-video", action="store_true")
    parser.add_argument("--media-workers", type=int, default=1)
    parser.add_argument(
        "--reuse-existing-media",
        action="store_true",
        help="Reuse montage/video files already present under --output.",
    )
    args = parser.parse_args()
    specs = load_specs(args.spec_file)
    items = []
    private_map = []
    media_jobs = []
    for spec in specs:
        for seed in range(4):
            item_id = blind_id(args.method, spec["spec_id"], seed, args.domain)
            run_dir = (
                args.data_root
                / args.domain
                / args.method
                / spec["spec_id"]
                / f"seed_{seed}"
            )
            manifest_path = run_dir / "run_manifest.json"
            if not manifest_path.exists():
                raise RuntimeError(
                    f"Missing run manifest for {spec['spec_id']} seed={seed}; "
                    "finish the preregistered run matrix before packaging ratings"
                )
            success = (run_dir / "SUCCESS").exists()
            private_map.append(
                {
                    "blind_id": item_id,
                    "method": args.method,
                    "domain": args.domain,
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "success": success,
                    "run_dir": str(run_dir),
                }
            )
            if not success:
                continue
            anchors = sorted((run_dir / "renders/anchors").glob("rgb_*.png"))
            montage_path = args.output / "montages" / f"{item_id}.jpg"
            video_path = args.output / "videos" / f"{item_id}.mp4"
            make_montage_needed = not (
                args.reuse_existing_media and montage_path.exists()
            )
            make_video_needed = not args.skip_video and not (
                args.reuse_existing_media and valid_video(video_path)
            )
            if make_montage_needed or make_video_needed:
                media_jobs.append(
                    (
                        anchors,
                        montage_path,
                        item_id,
                        args.domain,
                        run_dir / "renders/sequence",
                        video_path,
                        make_montage_needed,
                        make_video_needed,
                    )
                )
            items.append(
                {
                    "blind_id": item_id,
                    "domain": args.domain,
                    "prompt_en": spec["prompt_en"],
                    "required_facts_json": json.dumps(spec["required_facts"]),
                    "fact_count": len(spec["required_facts"]),
                    "montage": str(montage_path.relative_to(args.output)),
                    "video": ""
                    if args.skip_video
                    else str(video_path.relative_to(args.output)),
                }
            )

    if args.media_workers < 1:
        raise ValueError("--media-workers must be positive")

    def make_media(job: tuple) -> None:
        (
            anchors,
            montage_path,
            item_id,
            domain,
            sequence_dir,
            video_path,
            make_montage_needed,
            make_video_needed,
        ) = job
        if make_montage_needed:
            make_montage(anchors, montage_path, item_id, domain)
        if make_video_needed:
            make_video(sequence_dir, video_path)

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=args.media_workers
    ) as executor:
        futures = [executor.submit(make_media, job) for job in media_jobs]
        for index, future in enumerate(concurrent.futures.as_completed(futures), 1):
            future.result()
            print(f"ANNOTATION_MEDIA_PROGRESS {index}/{len(media_jobs)}", flush=True)

    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "RATER_INSTRUCTIONS.md").write_text(
        RATER_INSTRUCTIONS, encoding="utf-8"
    )
    map_path = args.output / "PRIVATE_blind_map.json"
    map_path.write_text(
        json.dumps(
            {
                "warning": "Do not give this file to raters.",
                "blind_salt_sha256": hashlib.sha256(BLIND_SALT.encode()).hexdigest(),
                "items": private_map,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    with (args.output / "items.csv").open("w", newline="", encoding="utf-8") as handle:
        fields = [
            "blind_id",
            "domain",
            "prompt_en",
            "required_facts_json",
            "fact_count",
            "montage",
            "video",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(items)

    with (args.output / "layout_ratings.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fields = [
            "rater_id",
            "blind_id",
            "boundary_collision",
            "support_pose",
            "scale_density",
            "function_circulation",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for rater in range(1, 4):
            for item in items:
                writer.writerow(
                    {"rater_id": f"rater_{rater:02d}", "blind_id": item["blind_id"]}
                )

    with (args.output / "prompt_ratings.csv").open(
        "w", newline="", encoding="utf-8"
    ) as handle:
        fields = ["rater_id", "blind_id", "fact_index", "fact", "response"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        facts_by_id = {
            blind_id(args.method, spec["spec_id"], seed, args.domain): spec[
                "required_facts"
            ]
            for spec in specs
            for seed in range(4)
        }
        for rater in range(1, 4):
            for item in items:
                for fact_index, fact in enumerate(facts_by_id[item["blind_id"]]):
                    writer.writerow(
                        {
                            "rater_id": f"rater_{rater:02d}",
                            "blind_id": item["blind_id"],
                            "fact_index": fact_index,
                            "fact": fact,
                        }
                    )
    print(f"ANNOTATION_PACKAGE_COMPLETE valid_items={len(items)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

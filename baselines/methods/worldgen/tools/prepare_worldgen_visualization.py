#!/usr/bin/env python3
"""Prepare unlabelled WorldGen stills and indoor-to-outdoor demo videos.

The script intentionally reuses completed WorldGen artifacts.  Indoor stills
are copied losslessly from the eight native anchor renders.  Urban stills are
rendered as rectilinear views of the clean generated panorama because the
single-panorama Gaussian reconstruction is not view complete.  The six full
demos pair matched Table-4 panoramas and add a clearly documented visual
portal transition; they do not claim a native shared 3D coordinate frame.
"""

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
import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np
from PIL import Image, ImageFilter


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
ANNOTATION_ROOT = BASELINES / "annotations/worldgen"
TABLE2_ROOT = BASELINES / "data/table2"
TABLE4_ROOT = BASELINES / "data/table4_worldgen"

WIDTH = 1280
HEIGHT = 720
FPS = 30
DURATION_SECONDS = 8


@dataclass(frozen=True)
class Table2Selection:
    blind_id: str
    run_dir: Path


@dataclass(frozen=True)
class FullSelection:
    scene_id: str
    spec_id: str
    seed: int


INDOOR_SELECTIONS = (
    Table2Selection(
        "I-1B18AD31C1F7",
        TABLE2_ROOT / "indoor/worldgen/indoor_dining_room_01/seed_1",
    ),
    Table2Selection(
        "I-FA9662442027",
        TABLE2_ROOT / "indoor/worldgen/indoor_kitchen_04/seed_3",
    ),
    Table2Selection(
        "I-F3B172EC630E",
        TABLE2_ROOT / "indoor/worldgen/indoor_living_room_00/seed_0",
    ),
)

URBAN_SELECTIONS = (
    Table2Selection(
        "U-1F3DF1A14BB1",
        TABLE2_ROOT / "urban/worldgen/urban_commercial_four_way_05/seed_3",
    ),
    Table2Selection(
        "U-BD35BD152BB4",
        TABLE2_ROOT / "urban/worldgen/urban_residential_four_way_00/seed_1",
    ),
    Table2Selection(
        "U-66187967A738",
        TABLE2_ROOT / "urban/worldgen/urban_commercial_main_side_07/seed_2",
    ),
)

FULL_SELECTIONS = (
    FullSelection("scene_01_residence_contemporary", "residence_contemporary_00", 0),
    FullSelection("scene_02_food_service_tropical", "food_service_tropical_08", 0),
    FullSelection("scene_03_retail_brick_industrial", "retail_brick_industrial_11", 0),
    FullSelection(
        "scene_04_office_timber_traditional", "office_timber_traditional_17", 0
    ),
    FullSelection(
        "scene_05_civic_futuristic",
        "civic_community_futuristic_stylized_24",
        0,
    ),
    FullSelection("scene_06_residence_tropical", "residence_tropical_03", 0),
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json(path: Path, payload: object) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


class PanoramaProjector:
    """Rectilinear renderer for an equirectangular panorama."""

    def __init__(
        self, panorama: Path, width: int = WIDTH, height: int = HEIGHT
    ) -> None:
        pixels = cv2.imread(str(panorama), cv2.IMREAD_COLOR)
        if pixels is None:
            raise FileNotFoundError(f"Cannot read panorama: {panorama}")
        self.panorama_path = panorama
        self.panorama = pixels
        self.output_width = width
        self.output_height = height
        self.pano_height, self.pano_width = pixels.shape[:2]
        yy, xx = np.mgrid[0:height, 0:width].astype(np.float32)
        self.pixel_x = xx
        self.pixel_y = yy

    def render(
        self, yaw_degrees: float, horizontal_fov_degrees: float = 90.0
    ) -> np.ndarray:
        f = self.output_width / (
            2.0 * math.tan(math.radians(horizontal_fov_degrees) / 2.0)
        )
        x = (self.pixel_x - self.output_width / 2.0) / f
        y = (self.pixel_y - self.output_height / 2.0) / f
        z = np.ones_like(x)

        yaw = math.radians(yaw_degrees)
        cos_yaw = math.cos(yaw)
        sin_yaw = math.sin(yaw)
        world_x = cos_yaw * x + sin_yaw * z
        world_z = -sin_yaw * x + cos_yaw * z
        norm = np.sqrt(world_x * world_x + y * y + world_z * world_z)
        longitude = np.arctan2(world_x, world_z)
        latitude = np.arcsin(np.clip(y / norm, -1.0, 1.0))

        map_x = ((longitude / (2.0 * math.pi) + 0.5) * self.pano_width).astype(
            np.float32
        )
        map_y = ((latitude / math.pi + 0.5) * self.pano_height).astype(np.float32)
        return cv2.remap(
            self.panorama,
            map_x,
            map_y,
            interpolation=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_WRAP,
        )


def save_rgb(path: Path, bgr: np.ndarray) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(path), bgr, [cv2.IMWRITE_PNG_COMPRESSION, 6]):
        raise RuntimeError(f"Failed to write image: {path}")


def smoothstep(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def portal_composite(
    indoor_bgr: np.ndarray, outdoor_bgr: np.ndarray, progress: float
) -> np.ndarray:
    """Reveal the exterior through an expanding, softly edged doorway shape."""

    progress = smoothstep(progress)
    width = indoor_bgr.shape[1]
    height = indoor_bgr.shape[0]
    door_width = int(width * min(1.12, 0.05 + 1.12 * progress))
    door_height = int(height * min(1.12, 0.62 + 0.58 * progress))
    x0 = (width - door_width) // 2
    y0 = (height - door_height) // 2
    x1 = x0 + door_width
    y1 = y0 + door_height

    mask = Image.new("L", (width, height), 0)
    # Pillow's rounded_rectangle handles coordinates outside the canvas, which
    # lets the final reveal reach every corner without a special cut.
    from PIL import ImageDraw

    ImageDraw.Draw(mask).rounded_rectangle(
        (x0, y0, x1, y1),
        radius=max(10, int(28 * (1.0 - progress))),
        fill=int(255 * min(1.0, progress * 4.0)),
    )
    mask = mask.filter(
        ImageFilter.GaussianBlur(radius=max(2, int(14 * (1.0 - progress))))
    )
    indoor = Image.fromarray(cv2.cvtColor(indoor_bgr, cv2.COLOR_BGR2RGB))
    outdoor = Image.fromarray(cv2.cvtColor(outdoor_bgr, cv2.COLOR_BGR2RGB))
    composed = Image.composite(outdoor, indoor, mask)
    return cv2.cvtColor(np.asarray(composed), cv2.COLOR_RGB2BGR)


def available_encoder(prefer_nvenc: bool) -> str:
    if not prefer_nvenc:
        return "libx264"
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-encoders"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return "h264_nvenc" if "h264_nvenc" in result.stdout else "libx264"


def video_command(
    output: Path, encoder: str, gpu: int
) -> tuple[list[str], dict[str, str]]:
    common = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "bgr24",
        "-video_size",
        f"{WIDTH}x{HEIGHT}",
        "-framerate",
        str(FPS),
        "-i",
        "pipe:0",
        "-an",
    ]
    env = dict(os.environ)
    if encoder == "h264_nvenc":
        env["CUDA_VISIBLE_DEVICES"] = str(gpu)
        codec = [
            "-c:v",
            "h264_nvenc",
            "-gpu",
            "0",
            "-preset",
            "p6",
            "-tune",
            "hq",
            "-rc",
            "vbr",
            "-cq",
            "18",
            "-b:v",
            "0",
        ]
    else:
        codec = ["-c:v", "libx264", "-preset", "medium", "-crf", "18"]
    return (
        common
        + codec
        + ["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)],
        env,
    )


def render_connected_video(
    interior_panorama: Path,
    exterior_panorama: Path,
    output: Path,
    encoder: str,
    gpu: int,
) -> None:
    require_below_baselines(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    interior = PanoramaProjector(interior_panorama)
    exterior = PanoramaProjector(exterior_panorama)
    command, env = video_command(output, encoder, gpu)
    process = subprocess.Popen(command, stdin=subprocess.PIPE, env=env)
    assert process.stdin is not None
    frame_count = FPS * DURATION_SECONDS
    try:
        for index in range(frame_count):
            t = index / (frame_count - 1)
            if t < 0.40:
                local = smoothstep(t / 0.40)
                frame = interior.render(-42.0 + 60.0 * local, 92.0 - 14.0 * local)
            elif t < 0.65:
                local = (t - 0.40) / 0.25
                indoor_frame = interior.render(18.0 + 8.0 * local, 78.0 - 10.0 * local)
                outdoor_frame = exterior.render(
                    -30.0 + 10.0 * local, 78.0 + 8.0 * local
                )
                frame = portal_composite(indoor_frame, outdoor_frame, local)
            else:
                local = smoothstep((t - 0.65) / 0.35)
                frame = exterior.render(-20.0 + 62.0 * local, 86.0 + 6.0 * local)
            process.stdin.write(np.ascontiguousarray(frame).tobytes())
    finally:
        process.stdin.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}: {output}")


def validate_image(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        width, height = image.size
    return {
        "path": relative(path),
        "width": width,
        "height": height,
        "sha256": sha256_file(path),
    }


def validate_video(path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,r_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    payload = json.loads(result.stdout)["streams"][0]
    payload["path"] = relative(path)
    payload["sha256"] = sha256_file(path)
    return payload


def require_files(paths: Iterable[Path]) -> None:
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required artifacts:\n" + "\n".join(missing))


def prepare_indoor() -> dict[str, object]:
    output_root = ANNOTATION_ROOT / "indoor/images"
    items = []
    for selection in INDOOR_SELECTIONS:
        anchors = sorted((selection.run_dir / "renders/anchors").glob("rgb_*.png"))
        if len(anchors) != 8:
            raise RuntimeError(
                f"Expected 8 anchors in {selection.run_dir}, found {len(anchors)}"
            )
        destination = output_root / selection.blind_id
        destination.mkdir(parents=True, exist_ok=True)
        images = []
        for index, source in enumerate(anchors, start=1):
            target = destination / f"view_{index:02d}.png"
            shutil.copy2(source, target)
            images.append(validate_image(target))
        items.append(
            {
                "id": selection.blind_id,
                "source_run": relative(selection.run_dir),
                "source_kind": "native_worldgen_anchor",
                "images": images,
            }
        )
    manifest = {
        "created_at_utc": utc_now(),
        "method": "worldgen",
        "domain": "indoor",
        "processing": "lossless file copy of the eight unlabelled native anchor PNGs",
        "items": items,
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def prepare_urban() -> dict[str, object]:
    output_root = ANNOTATION_ROOT / "urban/images"
    yaws = (-157.5, -112.5, -67.5, -22.5, 22.5, 67.5, 112.5, 157.5)
    items = []
    for selection in URBAN_SELECTIONS:
        panorama = selection.run_dir / "scene/panorama.png"
        require_files([panorama])
        projector = PanoramaProjector(panorama)
        destination = output_root / selection.blind_id
        destination.mkdir(parents=True, exist_ok=True)
        images = []
        for index, yaw in enumerate(yaws, start=1):
            target = destination / f"view_{index:02d}.png"
            save_rgb(target, projector.render(yaw, 90.0))
            record = validate_image(target)
            record["yaw_degrees"] = yaw
            images.append(record)
        items.append(
            {
                "id": selection.blind_id,
                "source_run": relative(selection.run_dir),
                "source_panorama": relative(panorama),
                "source_panorama_sha256": sha256_file(panorama),
                "rendering": "rectilinear projection from the generated equirectangular panorama",
                "images": images,
            }
        )
    manifest = {
        "created_at_utc": utc_now(),
        "method": "worldgen",
        "domain": "urban",
        "diagnosis": {
            "source_panorama_distorted": False,
            "artifact_stage": "single-panorama depth reconstruction and novel-view Gaussian-splat rendering",
            "artifact_types": [
                "disocclusion holes",
                "stretched splats at depth discontinuities",
                "black renderer background in uncovered regions",
            ],
            "action": "normal rectilinear projection from the clean generated panorama",
        },
        "items": items,
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def load_spec(spec_id: str) -> dict[str, object]:
    specs_path = BASELINES / "methods/worldgen/protocol/unified/native/specs.jsonl"
    for line in specs_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["spec_id"] == spec_id:
            return row
    raise KeyError(spec_id)


def prepare_full(prefer_nvenc: bool, gpu: int) -> dict[str, object]:
    output_root = ANNOTATION_ROOT / "full"
    output_root.mkdir(parents=True, exist_ok=True)
    encoder = available_encoder(prefer_nvenc)
    scenes = []
    image_views = (
        ("indoor_left.png", "interior", -45.0),
        ("indoor_center.png", "interior", 0.0),
        ("indoor_right.png", "interior", 45.0),
        ("outdoor_left.png", "exterior", -45.0),
        ("outdoor_center.png", "exterior", 0.0),
        ("outdoor_right.png", "exterior", 45.0),
    )
    for selection in FULL_SELECTIONS:
        pair = TABLE4_ROOT / selection.spec_id / f"seed_{selection.seed}"
        interior_panorama = pair / "native/interior/scene/panorama.png"
        exterior_panorama = pair / "native/exterior/scene/panorama.png"
        require_files([pair / "SUCCESS", interior_panorama, exterior_panorama])
        scene_root = output_root / selection.scene_id
        images_root = scene_root / "images"
        video_path = scene_root / "video/indoor_to_outdoor.mp4"
        projectors = {
            "interior": PanoramaProjector(interior_panorama),
            "exterior": PanoramaProjector(exterior_panorama),
        }
        image_records = []
        for filename, side, yaw in image_views:
            path = images_root / filename
            save_rgb(path, projectors[side].render(yaw, 90.0))
            record = validate_image(path)
            record.update({"side": side, "yaw_degrees": yaw})
            image_records.append(record)
        render_connected_video(
            interior_panorama,
            exterior_panorama,
            video_path,
            encoder,
            gpu,
        )
        spec = load_spec(selection.spec_id)
        scene_manifest = {
            "created_at_utc": utc_now(),
            "scene_id": selection.scene_id,
            "spec_id": selection.spec_id,
            "logical_seed": selection.seed,
            "function": spec["function"],
            "visual_theme": spec["visual_theme"],
            "source_pair": relative(pair),
            "source_panoramas": {
                "interior": relative(interior_panorama),
                "exterior": relative(exterior_panorama),
            },
            "connectivity": {
                "type": "visual_portal_transition",
                "native_shared_3d_frame": False,
                "note": (
                    "The matched WorldGen outputs are independent panoramas. The video adds an "
                    "auditable doorway-style visual transition and does not claim a native shared portal."
                ),
            },
            "images": image_records,
            "video": validate_video(video_path),
            "video_encoder": encoder,
            "video_encoder_gpu": gpu if encoder == "h264_nvenc" else None,
        }
        write_json(scene_root / "manifest.json", scene_manifest)
        scenes.append(scene_manifest)
    manifest = {
        "created_at_utc": utc_now(),
        "method": "worldgen",
        "scene_count": len(scenes),
        "resolution": [WIDTH, HEIGHT],
        "fps": FPS,
        "duration_seconds": DURATION_SECONDS,
        "images_have_overlays": False,
        "native_shared_3d_frame": False,
        "connectivity_representation": "documented visual portal transition",
        "scenes": scenes,
    }
    write_json(output_root / "manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--section",
        choices=("all", "indoor", "urban", "full"),
        default="all",
    )
    parser.add_argument("--gpu", type=int, default=1, help="Physical GPU used by NVENC")
    parser.add_argument(
        "--cpu-encode", action="store_true", help="Use libx264 instead of NVENC"
    )
    args = parser.parse_args()

    result: dict[str, object] = {}
    if args.section in ("all", "indoor"):
        result["indoor"] = prepare_indoor()
    if args.section in ("all", "urban"):
        result["urban"] = prepare_urban()
    if args.section in ("all", "full"):
        result["full"] = prepare_full(not args.cpu_encode, args.gpu)
    print(
        json.dumps(
            {
                "completed_at_utc": utc_now(),
                "sections": list(result),
                "annotation_root": relative(ANNOTATION_ROOT),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

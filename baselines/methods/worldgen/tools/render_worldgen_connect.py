#!/usr/bin/env python3
"""Render six connected indoor/outdoor WorldGen mesh demonstrations.

The source assets are official WorldGen triangle meshes.  Valid pre-existing
meshes under ``baselines/annotations/worldgen/full`` are reused, while any
visually rejected scene can provide a local replacement mesh under the output
tree.  Every still and every video frame is rasterized from one mesh; no
panorama projection, image stitching, cross-fade, or 2D transition is used.
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
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import numpy as np


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
TOOLS = BASELINES / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

from baselines.methods.worldgen.tools.worldgen_mesh_visualization import (
    MeshRasterRenderer,
)
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import link_mesh
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import relative
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import (
    require_below_baselines,
)
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import save_image
from baselines.methods.worldgen.tools.worldgen_mesh_visualization import sha256_file


SOURCE_ROOT = BASELINES / "annotations/worldgen/full"
OUTPUT_ROOT = BASELINES / "annotations/worldgen/connect"
TASKS_PATH = (
    BASELINES / "methods/worldgen/protocol/generation/worldgen_mesh_demo_scenes.json"
)
WIDTH = 1280
HEIGHT = 720


SCENE_EXTERIOR_YAWS = {
    "scene_01_residence_contemporary": 0.0,
    "scene_02_food_service_tropical": 0.0,
    "scene_03_retail_brick_industrial": -90.0,
    "scene_04_office_timber_traditional": 90.0,
    "scene_05_civic_futuristic": 0.0,
    "scene_06_residence_tropical": 0.0,
}
BASE_STILL_CAMERA_COUNT = 8
CONNECTION_DISTANCE_SPECS = (
    ("near", 0.30, 86.0),
    ("medium", 0.65, 98.0),
    ("far", 1.00, 112.0),
)
CONNECTION_VIEW_COUNT = len(CONNECTION_DISTANCE_SPECS) * 3 * 2
SHARED_CONTEXT_VIEW_COUNT = 4
STILL_CAMERA_COUNT = (
    BASE_STILL_CAMERA_COUNT + CONNECTION_VIEW_COUNT + SHARED_CONTEXT_VIEW_COUNT
)
VIDEO_CAMERA_COUNT = 4

# A depth-derived panorama mesh is a single triangle shell around its source
# camera, not a watertight building model.  Keep translated cameras inside the
# measured inscribed radius of each final mesh.  The wide far-view lenses add
# context without moving outside the shell and creating stretched triangles.
SCENE_CONNECTION_FAR_DISTANCES = {
    "scene_01_residence_contemporary": 0.55,
    "scene_02_food_service_tropical": 0.38,
    "scene_03_retail_brick_industrial": 0.30,
    "scene_04_office_timber_traditional": 0.38,
    "scene_05_civic_futuristic": 0.12,
    "scene_06_residence_tropical": 0.30,
}

# The native panorama seam makes one side of some thresholds cleaner than the
# other.  These signs select the side that actually keeps recognizable source
# and destination environments in frame.  -1 is the local left camera and +1
# is the local right camera.
SCENE_SHARED_OUTBOUND_HAND = {
    "scene_01_residence_contemporary": -1.0,
    "scene_02_food_service_tropical": 1.0,
    "scene_05_civic_futuristic": 1.0,
    "scene_06_residence_tropical": -1.0,
}
SCENE_SHARED_INBOUND_HANDS = {
    "scene_01_residence_contemporary": (-1.0, 1.0),
    "scene_02_food_service_tropical": (-1.0, -1.0),
    "scene_05_civic_futuristic": (-1.0, 1.0),
    "scene_06_residence_tropical": (-1.0, 1.0),
}


def rotate_position(
    position: tuple[float, float, float], yaw_degrees: float
) -> tuple[float, float, float]:
    """Rotate a base +Z-exterior camera position around the native Y axis."""
    angle = np.radians(yaw_degrees)
    x, y, z = position
    return (
        float(np.cos(angle) * x + np.sin(angle) * z),
        y,
        float(-np.sin(angle) * x + np.cos(angle) * z),
    )


def scene_still_cameras(scene_id: str) -> tuple[dict[str, Any], ...]:
    exterior_yaw = SCENE_EXTERIOR_YAWS[scene_id]
    interior_yaw = exterior_yaw + 180.0
    seam_at_interior_center = exterior_yaw == 0.0
    if seam_at_interior_center:
        interior_views = ((120.0, 88.0), (100.0, 84.0), (260.0, 84.0))
        outdoor_to_indoor_position = (-0.06, 0.0, 0.06)
        outdoor_to_indoor_yaw = 135.0
        outdoor_to_indoor_fov = 80.0
    else:
        interior_views = (
            (interior_yaw, 92.0),
            (interior_yaw - 32.0, 86.0),
            (interior_yaw + 32.0, 86.0),
        )
        outdoor_to_indoor_position = rotate_position((0.0, 0.0, 0.06), exterior_yaw)
        outdoor_to_indoor_yaw = interior_yaw
        outdoor_to_indoor_fov = 88.0
    inside = rotate_position((0.0, 0.0, -0.04), exterior_yaw)
    outside = rotate_position((0.0, 0.0, 0.04), exterior_yaw)
    base_cameras = (
        {
            "name": "interior_overview",
            "region": "indoor",
            "position": inside,
            "yaw": interior_views[0][0],
            "horizontal_fov": interior_views[0][1],
            "description": "Interior hemisphere viewed from just inside the threshold.",
        },
        {
            "name": "interior_left",
            "region": "indoor",
            "position": inside,
            "yaw": interior_views[1][0],
            "horizontal_fov": interior_views[1][1],
            "description": "Left side of the connected interior.",
        },
        {
            "name": "interior_right",
            "region": "indoor",
            "position": inside,
            "yaw": interior_views[2][0],
            "horizontal_fov": interior_views[2][1],
            "description": "Right side of the connected interior.",
        },
        {
            "name": "exterior_overview",
            "region": "outdoor",
            "position": outside,
            "yaw": exterior_yaw,
            "horizontal_fov": 96.0,
            "description": "Exterior hemisphere viewed from just outside the threshold.",
        },
        {
            "name": "exterior_left",
            "region": "outdoor",
            "position": outside,
            "yaw": exterior_yaw - 35.0,
            "horizontal_fov": 90.0,
            "description": "Left side of the connected exterior.",
        },
        {
            "name": "exterior_right",
            "region": "outdoor",
            "position": outside,
            "yaw": exterior_yaw + 35.0,
            "horizontal_fov": 90.0,
            "description": "Right side of the connected exterior.",
        },
        {
            "name": "indoor_to_outdoor",
            "region": "connection",
            "position": rotate_position((0.0, 0.0, -0.06), exterior_yaw),
            "yaw": exterior_yaw,
            "horizontal_fov": 92.0,
            "description": "The real mesh threshold viewed from indoors toward outdoors.",
        },
        {
            "name": "outdoor_to_indoor",
            "region": "connection",
            "position": outdoor_to_indoor_position,
            "yaw": outdoor_to_indoor_yaw,
            "horizontal_fov": outdoor_to_indoor_fov,
            "description": "The same mesh threshold viewed from outdoors toward indoors.",
        },
    )
    assert len(base_cameras) == BASE_STILL_CAMERA_COUNT

    # The initial demo used only one camera 0.06 scene units from each side of
    # the threshold.  Add a distance/angle grid so the connection is also
    # visible with substantially more architectural context.  Positions and
    # view directions are rotated together for scenes whose exterior is not
    # aligned with native +Z.
    extra_cameras: list[dict[str, Any]] = []
    far_distance = SCENE_CONNECTION_FAR_DISTANCES[scene_id]
    for distance_name, distance_ratio, horizontal_fov in CONNECTION_DISTANCE_SPECS:
        distance = far_distance * distance_ratio
        lateral = 0.24 * distance
        outbound_views = (
            ("left_oblique", -lateral, 24.0),
            ("centered", 0.0, 0.0),
            ("right_oblique", lateral, -24.0),
        )
        for view_name, lateral_offset, yaw_offset in outbound_views:
            extra_cameras.append(
                {
                    "name": f"indoor_to_outdoor_{distance_name}_{view_name}",
                    "region": "connection",
                    "connection_direction": "indoor_to_outdoor",
                    "distance_label": distance_name,
                    "camera_distance_native": distance,
                    "view_angle": view_name,
                    "position": rotate_position(
                        (lateral_offset, 0.0, -distance), exterior_yaw
                    ),
                    "yaw": exterior_yaw + yaw_offset,
                    "horizontal_fov": horizontal_fov,
                    "description": (
                        f"{distance_name.capitalize()} {view_name.replace('_', ' ')} "
                        "3D view from indoors toward the connected exterior."
                    ),
                }
            )

        if seam_at_interior_center:
            # The native equirectangular mesh has its unstitched rear boundary
            # at 180 degrees.  Look into the interior from both sides of that
            # boundary instead of hiding it with a 2D repair.
            inbound_views = (
                ("left_oblique", -lateral, 118.0, 104.0),
                ("left_center", -0.35 * lateral, 138.0, 82.0),
                ("right_oblique", lateral, 228.0, 94.0),
            )
        else:
            inbound_views = (
                ("left_oblique", -lateral, interior_yaw - 26.0, horizontal_fov),
                ("centered", 0.0, interior_yaw, horizontal_fov),
                ("right_oblique", lateral, interior_yaw + 26.0, horizontal_fov),
            )
        for view_name, lateral_offset, view_yaw, maximum_fov in inbound_views:
            inbound_fov = min(horizontal_fov, maximum_fov)
            extra_cameras.append(
                {
                    "name": f"outdoor_to_indoor_{distance_name}_{view_name}",
                    "region": "connection",
                    "connection_direction": "outdoor_to_indoor",
                    "distance_label": distance_name,
                    "camera_distance_native": distance,
                    "view_angle": view_name,
                    "position": rotate_position(
                        (lateral_offset, 0.0, distance), exterior_yaw
                    ),
                    "yaw": view_yaw,
                    "horizontal_fov": inbound_fov,
                    "description": (
                        f"{distance_name.capitalize()} {view_name.replace('_', ' ')} "
                        "3D view from outdoors toward the connected interior."
                    ),
                }
            )

    # Four shared-context compositions.  They are deliberately not centered
    # on the door frame: each camera is translated to one side and looks
    # obliquely across the opening.  The destination environment occupies most
    # of the frame while a recognizable part of the source environment stays
    # visible at an edge.  Deep vestibules in the two rotated scenes need a
    # wider tangential view to include the actual room and street/courtyard at
    # once; the other scenes use a less distorted roughly one-third/two-thirds
    # composition.
    context_distance = far_distance * 0.90
    context_lateral = context_distance * 0.22
    if seam_at_interior_center:
        outbound_hand = SCENE_SHARED_OUTBOUND_HAND[scene_id]
        inbound_hands = SCENE_SHARED_INBOUND_HANDS[scene_id]
        outbound_offsets = (
            (20.0, 26.0)
            if scene_id == "scene_01_residence_contemporary"
            else (30.0, 38.0)
        )
        shared_context_specs = (
            (
                "indoor_to_outdoor_shared_left",
                "indoor_to_outdoor",
                (outbound_hand * context_lateral, 0.0, -context_distance),
                exterior_yaw - outbound_hand * outbound_offsets[0],
                118.0,
                "Indoor-origin oblique view: exterior is the main subject and a recognizable indoor edge remains visible.",
            ),
            (
                "indoor_to_outdoor_shared_right",
                "indoor_to_outdoor",
                (outbound_hand * context_distance * 0.45, 0.0, -context_distance),
                exterior_yaw - outbound_hand * outbound_offsets[1],
                124.0,
                "Laterally shifted indoor-origin view: exterior remains dominant while indoor architecture or furniture stays in frame.",
            ),
            (
                "outdoor_to_indoor_shared_left",
                "outdoor_to_indoor",
                (inbound_hands[0] * context_lateral, 0.0, context_distance),
                interior_yaw + inbound_hands[0] * 60.0,
                118.0,
                "Outdoor-origin oblique view: interior is the main subject and recognizable exterior foreground remains visible.",
            ),
            (
                "outdoor_to_indoor_shared_right",
                "outdoor_to_indoor",
                (
                    inbound_hands[1]
                    * context_distance
                    * (0.45 if inbound_hands[0] == inbound_hands[1] else 0.22),
                    0.0,
                    context_distance,
                ),
                interior_yaw
                + inbound_hands[1]
                * (68.0 if inbound_hands[0] == inbound_hands[1] else 60.0),
                124.0 if inbound_hands[0] == inbound_hands[1] else 118.0,
                "Second outdoor-origin oblique view with interior and exterior context simultaneously visible.",
            ),
        )
    else:
        # Complementary tangential views keep the threshold away from being
        # the sole central subject and expose both sides of the deep vestibule.
        hands = (-1.0, 1.0)
        lateral_ratios = (0.22, 0.22)
        shared_context_specs = tuple(
            (
                f"indoor_to_outdoor_shared_{label}",
                "indoor_to_outdoor",
                (hand * context_distance * ratio, 0.0, -context_distance),
                exterior_yaw - hand * 80.0,
                160.0,
                "Indoor-origin tangential view retaining both the actual interior room and exterior scene across the deep vestibule.",
            )
            for label, hand, ratio in zip(("left", "right"), hands, lateral_ratios)
        ) + tuple(
            (
                f"outdoor_to_indoor_shared_{label}",
                "outdoor_to_indoor",
                (hand * context_distance * ratio, 0.0, context_distance),
                interior_yaw + hand * 80.0,
                160.0,
                "Outdoor-origin tangential view retaining both the exterior scene and actual interior room across the deep vestibule.",
            )
            for label, hand, ratio in zip(("left", "right"), hands, lateral_ratios)
        )
    for (
        name,
        direction,
        position,
        view_yaw,
        view_fov,
        description,
    ) in shared_context_specs:
        extra_cameras.append(
            {
                "name": name,
                "region": "connection",
                "connection_direction": direction,
                "distance_label": "threshold_context",
                "camera_distance_native": context_distance,
                "view_angle": "shared_left"
                if name.endswith("left")
                else "shared_right",
                "both_indoor_and_outdoor_visible": True,
                "threshold_composition": "off_center_oblique_shared_context",
                "position": rotate_position(position, exterior_yaw),
                "yaw": view_yaw,
                "horizontal_fov": view_fov,
                "description": description,
            }
        )

    cameras = base_cameras + tuple(extra_cameras)
    assert len(cameras) == STILL_CAMERA_COUNT
    return cameras


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, payload: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def unresolved_relative(path: Path) -> str:
    """Return a repository-relative path without resolving a deliberate symlink."""
    return str(path.absolute().relative_to(REPO.absolute()))


def load_tasks() -> list[dict[str, Any]]:
    tasks = json.loads(TASKS_PATH.read_text(encoding="utf-8"))
    if not isinstance(tasks, list) or len(tasks) != 6:
        raise ValueError(f"Expected exactly six WorldGen demo tasks in {TASKS_PATH}")
    return tasks


def choose_encoder(requested: str) -> str:
    if requested != "auto":
        return requested
    probe = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-f",
            "lavfi",
            "-i",
            "color=size=320x240:rate=1",
            "-frames:v",
            "1",
            "-c:v",
            "h264_nvenc",
            "-gpu",
            "0",
            "-f",
            "null",
            "-",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return "h264_nvenc" if probe.returncode == 0 else "libx264"


def probe_video(path: Path) -> dict[str, Any]:
    probe = subprocess.run(
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
    record = json.loads(probe.stdout)["streams"][0]
    record.update({"path": relative(path), "sha256": sha256_file(path)})
    return record


def encode_video(
    renderer: MeshRasterRenderer,
    output: Path,
    fps: int,
    duration: int,
    encoder: str,
    camera: Callable[[float], tuple[np.ndarray, float, float]],
) -> dict[str, Any]:
    require_below_baselines(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.stem}.part{output.suffix}")
    frames = fps * duration
    command = [
        "ffmpeg",
        "-v",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pixel_format",
        "rgb24",
        "-video_size",
        f"{WIDTH}x{HEIGHT}",
        "-framerate",
        str(fps),
        "-i",
        "pipe:0",
        "-an",
        "-c:v",
        encoder,
    ]
    if encoder == "h264_nvenc":
        command.extend(
            [
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
        )
    else:
        command.extend(["-preset", "medium", "-crf", "18"])
    command.extend(["-pix_fmt", "yuv420p", "-movflags", "+faststart", str(temporary)])

    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(frames):
            fraction = index / max(1, frames - 1)
            position, yaw, horizontal_fov = camera(fraction)
            rgb = renderer.render(position, yaw, horizontal_fov)
            process.stdin.write(np.ascontiguousarray(rgb).tobytes())
    except BaseException:
        process.stdin.close()
        process.wait()
        temporary.unlink(missing_ok=True)
        raise
    process.stdin.close()
    return_code = process.wait()
    if return_code != 0:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}: {output}")
    temporary.replace(output)
    record = probe_video(output)
    record["encoder"] = encoder
    return record


def smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def indoor_camera(fraction: float) -> tuple[np.ndarray, float, float]:
    smooth = smoothstep(fraction)
    # Keep WorldGen's 180-degree panorama join outside the camera frustum.
    yaw = 100.0 + 35.0 * smooth
    position = np.asarray(
        [0.015 * np.sin(fraction * np.pi), 0.0, -0.04], dtype=np.float32
    )
    return position, yaw, 80.0


def outdoor_camera(fraction: float) -> tuple[np.ndarray, float, float]:
    smooth = smoothstep(fraction)
    yaw = -45.0 + 90.0 * smooth
    position = np.asarray(
        [-0.015 * np.sin(fraction * np.pi), 0.0, 0.04], dtype=np.float32
    )
    return position, yaw, 92.0


def indoor_to_outdoor_camera(fraction: float) -> tuple[np.ndarray, float, float]:
    smooth = smoothstep(fraction)
    position = np.asarray(
        [-0.02 + 0.04 * smooth, 0.0, -0.07 + 0.14 * smooth], dtype=np.float32
    )
    yaw = -14.0 + 28.0 * smooth
    return position, yaw, 88.0


def outdoor_to_indoor_camera(fraction: float) -> tuple[np.ndarray, float, float]:
    smooth = smoothstep(fraction)
    # Traverse the threshold diagonally so the rear panorama join stays just
    # beyond the right edge while the camera still points into the interior.
    position = np.asarray(
        [-0.07 + 0.14 * smooth, 0.0, 0.07 - 0.14 * smooth], dtype=np.float32
    )
    yaw = 128.0 + 14.0 * smooth
    return position, yaw, 74.0


def scene_video_cameras(
    scene_id: str,
) -> tuple[tuple[str, str, Callable[[float], tuple[np.ndarray, float, float]]], ...]:
    exterior_yaw = SCENE_EXTERIOR_YAWS[scene_id]
    if exterior_yaw == 0.0:
        cameras = (
            (
                "indoor",
                "A mesh-rendered look around the interior hemisphere.",
                indoor_camera,
            ),
            (
                "outdoor",
                "A mesh-rendered look around the exterior hemisphere.",
                outdoor_camera,
            ),
            (
                "indoor_to_outdoor",
                "A continuous 3D camera move from indoors through the threshold toward outdoors.",
                indoor_to_outdoor_camera,
            ),
            (
                "outdoor_to_indoor",
                "A continuous 3D camera move from outdoors through the same threshold toward indoors.",
                outdoor_to_indoor_camera,
            ),
        )
        return cameras

    interior_yaw = exterior_yaw + 180.0

    def rotate_result(
        position: tuple[float, float, float], yaw: float, horizontal_fov: float
    ) -> tuple[np.ndarray, float, float]:
        return (
            np.asarray(rotate_position(position, exterior_yaw), dtype=np.float32),
            yaw + exterior_yaw,
            horizontal_fov,
        )

    def generic_indoor(fraction: float) -> tuple[np.ndarray, float, float]:
        smooth = smoothstep(fraction)
        return rotate_result(
            (0.015 * np.sin(fraction * np.pi), 0.0, -0.04),
            155.0 + 50.0 * smooth,
            88.0,
        )

    def generic_outdoor(fraction: float) -> tuple[np.ndarray, float, float]:
        smooth = smoothstep(fraction)
        return rotate_result(
            (-0.015 * np.sin(fraction * np.pi), 0.0, 0.04),
            -45.0 + 90.0 * smooth,
            92.0,
        )

    def generic_indoor_to_outdoor(fraction: float) -> tuple[np.ndarray, float, float]:
        smooth = smoothstep(fraction)
        return rotate_result(
            (-0.02 + 0.04 * smooth, 0.0, -0.07 + 0.14 * smooth),
            -14.0 + 28.0 * smooth,
            88.0,
        )

    def generic_outdoor_to_indoor(fraction: float) -> tuple[np.ndarray, float, float]:
        smooth = smoothstep(fraction)
        return rotate_result(
            (0.02 - 0.04 * smooth, 0.0, 0.07 - 0.14 * smooth),
            166.0 + 28.0 * smooth,
            88.0,
        )

    cameras = (
        (
            "indoor",
            "A mesh-rendered look around the interior hemisphere.",
            generic_indoor,
        ),
        (
            "outdoor",
            "A mesh-rendered look around the exterior hemisphere.",
            generic_outdoor,
        ),
        (
            "indoor_to_outdoor",
            "A continuous 3D camera move from indoors through the threshold toward outdoors.",
            generic_indoor_to_outdoor,
        ),
        (
            "outdoor_to_indoor",
            "A continuous 3D camera move from outdoors through the same threshold toward indoors.",
            generic_outdoor_to_indoor,
        ),
    )
    assert len(cameras) == VIDEO_CAMERA_COUNT
    assert abs((interior_yaw - exterior_yaw) - 180.0) < 1e-6
    return cameras


def render_scene(
    task: dict[str, Any], fps: int, duration: int, encoder: str
) -> dict[str, Any]:
    scene_id = task["scene_id"]
    output = require_below_baselines(OUTPUT_ROOT / scene_id)
    local_mesh = output / "native/scene/mesh.ply"
    if local_mesh.is_file():
        mesh_path = local_mesh
        source_manifest_path = local_mesh.with_name("mesh_manifest.json")
        mesh_info = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        candidate_path = output / "native/input/native_input.json"
        candidate = json.loads(candidate_path.read_text(encoding="utf-8"))
        prompt = candidate["prompt"]
        seed = candidate["seed"]
        generation_skipped = False
        generation_note = "Weak pre-existing sample was replaced after visual audit; this panorama and mesh were newly generated."
    else:
        source_root = SOURCE_ROOT / scene_id
        source_manifest_path = source_root / "manifest.json"
        source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
        mesh_info = source_manifest["mesh"]
        mesh_path = source_root / "native/scene/mesh.ply"
        prompt = task["prompt"]
        seed = task["seed"]
        generation_skipped = True
        generation_note = "Existing official WorldGen triangle mesh passed existence and SHA-256 checks."
    if not mesh_path.is_file():
        raise FileNotFoundError(mesh_path)
    mesh_digest = sha256_file(mesh_path)
    if mesh_digest != mesh_info["mesh_sha256"]:
        raise RuntimeError(f"Source mesh checksum mismatch: {mesh_path}")

    renderer = MeshRasterRenderer(mesh_path, width=WIDTH, height=HEIGHT)
    images: list[dict[str, Any]] = []
    still_cameras = scene_still_cameras(scene_id)
    for camera in still_cameras:
        position = np.asarray(camera["position"], dtype=np.float32)
        rgb = renderer.render(position, camera["yaw"], camera["horizontal_fov"])
        record = save_image(output / "images" / f"{camera['name']}.png", rgb)
        record.update(
            {
                "name": camera["name"],
                "region": camera["region"],
                "description": camera["description"],
                "camera_position_native": position.tolist(),
                "yaw_degrees": camera["yaw"],
                "horizontal_fov_degrees": camera["horizontal_fov"],
            }
        )
        for key in (
            "connection_direction",
            "distance_label",
            "camera_distance_native",
            "view_angle",
            "both_indoor_and_outdoor_visible",
            "threshold_composition",
        ):
            if key in camera:
                record[key] = camera[key]
        images.append(record)

    videos: list[dict[str, Any]] = []
    video_cameras = scene_video_cameras(scene_id)
    for name, description, camera_function in video_cameras:
        record = encode_video(
            renderer,
            output / "videos" / f"{name}.mp4",
            fps,
            duration,
            encoder,
            camera_function,
        )
        record.update({"name": name, "description": description})
        videos.append(record)

    link_mesh(mesh_path, output / "mesh.ply")
    manifest = {
        "created_at_utc": utc_now(),
        "scene_id": scene_id,
        "method": "worldgen",
        "prompt": prompt,
        "seed": seed,
        "source_manifest": relative(source_manifest_path),
        "generation_skipped": generation_skipped,
        "generation_note": generation_note,
        "generation_contract": "one panorama -> one official triangle mesh -> mesh-rasterized images and videos",
        "connectivity": {
            "type": "one physically connected threshold scene",
            "single_mesh": True,
            "indoor_and_outdoor_same_mesh": True,
            "indoor_to_outdoor_rendered": True,
            "outdoor_to_indoor_rendered": True,
            "crossfade_used": False,
            "panorama_projection_used": False,
            "image_stitching_used": False,
        },
        "mesh": {
            "path": unresolved_relative(output / "mesh.ply"),
            "source_path": relative(mesh_path),
            "sha256": mesh_digest,
            "vertices": mesh_info["vertices"],
            "triangles": mesh_info["triangles"],
            "vertex_colors": mesh_info["vertex_colors"],
            "bounds_min": mesh_info["bounds_min"],
            "bounds_max": mesh_info["bounds_max"],
        },
        "renderer": "ModernGL/EGL triangle rasterizer with depth testing and interpolated mesh vertex colors",
        "render_device": {
            "gl_vendor": renderer.context.info.get("GL_VENDOR"),
            "gl_renderer": renderer.context.info.get("GL_RENDERER"),
            "gl_version": renderer.context.info.get("GL_VERSION"),
            "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        },
        "images_have_overlays": False,
        "images_are_separate_files": True,
        "images": images,
        "videos": videos,
    }
    atomic_json(output / "manifest.json", manifest)
    return manifest


def render_shared_context_only(task: dict[str, Any]) -> dict[str, Any]:
    """Overwrite only the four reviewed connection stills and refresh metadata."""
    scene_id = task["scene_id"]
    output = require_below_baselines(OUTPUT_ROOT / scene_id)
    manifest_path = output / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(
            f"Shared-context-only rendering requires an existing complete scene: {manifest_path}"
        )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    mesh_path = output / "mesh.ply"
    if not mesh_path.is_file():
        raise FileNotFoundError(mesh_path)

    renderer = MeshRasterRenderer(mesh_path, width=WIDTH, height=HEIGHT)
    replacement_records: dict[str, dict[str, Any]] = {}
    for camera in scene_still_cameras(scene_id):
        if not camera["name"].startswith(
            ("indoor_to_outdoor_shared_", "outdoor_to_indoor_shared_")
        ):
            continue
        position = np.asarray(camera["position"], dtype=np.float32)
        rgb = renderer.render(position, camera["yaw"], camera["horizontal_fov"])
        record = save_image(output / "images" / f"{camera['name']}.png", rgb)
        record.update(
            {
                "name": camera["name"],
                "region": camera["region"],
                "description": camera["description"],
                "camera_position_native": position.tolist(),
                "yaw_degrees": camera["yaw"],
                "horizontal_fov_degrees": camera["horizontal_fov"],
            }
        )
        for key in (
            "connection_direction",
            "distance_label",
            "camera_distance_native",
            "view_angle",
            "both_indoor_and_outdoor_visible",
            "threshold_composition",
        ):
            if key in camera:
                record[key] = camera[key]
        replacement_records[camera["name"]] = record

    if len(replacement_records) != SHARED_CONTEXT_VIEW_COUNT:
        raise RuntimeError(
            f"Expected {SHARED_CONTEXT_VIEW_COUNT} shared-context cameras for {scene_id}"
        )
    existing_names = {record["name"] for record in manifest["images"]}
    missing = set(replacement_records).difference(existing_names)
    if missing:
        raise RuntimeError(
            f"Existing manifest lacks shared-context records: {sorted(missing)}"
        )
    manifest["images"] = [
        replacement_records.get(record["name"], record) for record in manifest["images"]
    ]
    manifest["created_at_utc"] = utc_now()
    manifest["shared_context_revision"] = {
        "rendered_at_utc": utc_now(),
        "reason": "Off-center oblique views with recognizable indoor and outdoor scene content in every dedicated connection still.",
        "image_count": SHARED_CONTEXT_VIEW_COUNT,
        "image_stitching_used": False,
        "overlays_used": False,
    }
    manifest["render_device"] = {
        "gl_vendor": renderer.context.info.get("GL_VENDOR"),
        "gl_renderer": renderer.context.info.get("GL_RENDERER"),
        "gl_version": renderer.context.info.get("GL_VERSION"),
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
    }
    atomic_json(manifest_path, manifest)
    return manifest


def completed_manifest(
    task: dict[str, Any], fps: int, duration: int
) -> dict[str, Any] | None:
    """Return a valid completed scene manifest, otherwise request a fresh render."""
    manifest_path = OUTPUT_ROOT / task["scene_id"] / "manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if len(manifest["images"]) != STILL_CAMERA_COUNT:
            return None
        if len(manifest["videos"]) != VIDEO_CAMERA_COUNT:
            return None
        if any(
            int(video["nb_frames"]) != fps * duration for video in manifest["videos"]
        ):
            return None
        paths = [REPO / image["path"] for image in manifest["images"]]
        paths.extend(REPO / video["path"] for video in manifest["videos"])
        paths.append(OUTPUT_ROOT / task["scene_id"] / "mesh.ply")
        if not all(path.is_file() for path in paths):
            return None
        return manifest
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def aggregate(
    manifests: list[dict[str, Any]], encoder: str, fps: int, duration: int
) -> None:
    scenes = []
    for manifest in manifests:
        scenes.append(
            {
                "scene_id": manifest["scene_id"],
                "manifest": relative(
                    OUTPUT_ROOT / manifest["scene_id"] / "manifest.json"
                ),
                "mesh": manifest["mesh"],
                "image_count": len(manifest["images"]),
                "video_count": len(manifest["videos"]),
            }
        )
    newly_generated = sum(not manifest["generation_skipped"] for manifest in manifests)
    payload = {
        "created_at_utc": utc_now(),
        "method": "worldgen",
        "scene_count": len(scenes),
        "image_count": sum(item["image_count"] for item in scenes),
        "video_count": sum(item["video_count"] for item in scenes),
        "video_settings": {
            "fps": fps,
            "duration_seconds": duration,
            "encoder": encoder,
        },
        "image_view_grid": {
            "base_views_per_scene": BASE_STILL_CAMERA_COUNT,
            "connection_views_per_direction_per_scene": CONNECTION_VIEW_COUNT // 2,
            "connection_distance_labels": [row[0] for row in CONNECTION_DISTANCE_SPECS],
            "connection_angles_per_distance": 3,
            "shared_indoor_outdoor_context_views_per_scene": SHARED_CONTEXT_VIEW_COUNT,
            "shared_context_views_per_direction_per_scene": SHARED_CONTEXT_VIEW_COUNT
            // 2,
            "total_images_per_scene": STILL_CAMERA_COUNT,
            "distance_policy": "scene-adaptive safe translation plus progressively wider field of view",
        },
        "generation_summary": {
            "reused_existing_scenes": len(manifests) - newly_generated,
            "newly_generated_replacements": newly_generated,
            "reason": "Existing valid meshes were reused; weak samples found by visual audit were regenerated.",
        },
        "connectivity": {
            "single_mesh_per_scene": True,
            "bidirectional_threshold_views": True,
            "crossfade_used": False,
            "panorama_projection_used": False,
            "image_stitching_used": False,
        },
        "images_have_overlays": False,
        "images_are_separate_files": True,
        "scenes": scenes,
    }
    atomic_json(OUTPUT_ROOT / "manifest.json", payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--scene-id",
        action="append",
        help="Render only the selected scene (repeatable).",
    )
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--duration", type=int, default=6)
    parser.add_argument(
        "--encoder", choices=("auto", "h264_nvenc", "libx264"), default="auto"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-render scenes that already passed completion checks.",
    )
    parser.add_argument(
        "--shared-context-only",
        action="store_true",
        help="Overwrite only the four dedicated stills that show indoor and outdoor context together.",
    )
    args = parser.parse_args()
    if args.fps < 1 or args.duration < 1:
        parser.error("--fps and --duration must be positive")
    if args.force and args.shared_context_only:
        parser.error("--force and --shared-context-only are mutually exclusive")

    tasks = load_tasks()
    if args.scene_id:
        wanted = set(args.scene_id)
        tasks = [task for task in tasks if task["scene_id"] in wanted]
        missing = wanted.difference(task["scene_id"] for task in tasks)
        if missing:
            parser.error(f"Unknown scene ids: {sorted(missing)}")
    encoder = choose_encoder(args.encoder)
    print(f"ENCODER_SELECTED {encoder}", flush=True)
    manifests = []
    for task in tasks:
        if args.shared_context_only:
            print(f"SHARED_CONTEXT_RENDER_START scene={task['scene_id']}", flush=True)
            manifest = render_shared_context_only(task)
            manifests.append(manifest)
            print(
                f"SHARED_CONTEXT_RENDER_COMPLETE scene={task['scene_id']} images={SHARED_CONTEXT_VIEW_COUNT}",
                flush=True,
            )
            continue
        existing = (
            None if args.force else completed_manifest(task, args.fps, args.duration)
        )
        if existing is not None:
            manifests.append(existing)
            print(f"RENDER_SKIP_COMPLETE scene={task['scene_id']}", flush=True)
            continue
        print(f"RENDER_START scene={task['scene_id']}", flush=True)
        manifest = render_scene(task, args.fps, args.duration, encoder)
        manifests.append(manifest)
        print(
            f"RENDER_COMPLETE scene={task['scene_id']} images={len(manifest['images'])} videos={len(manifest['videos'])}",
            flush=True,
        )
    if len(tasks) == 6:
        aggregate(manifests, encoder, args.fps, args.duration)
        print(f"CONNECT_MANIFEST_WRITTEN scenes={len(manifests)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

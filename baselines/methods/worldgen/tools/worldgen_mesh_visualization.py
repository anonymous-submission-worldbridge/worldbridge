#!/usr/bin/env python3
"""Generate official WorldGen meshes and render images/videos from the meshes.

This pipeline never substitutes panorama projection for mesh rendering.  It
uses WorldGen's official ``convert_rgbd2mesh_panorama`` reconstruction and a
ModernGL/EGL GPU triangle rasterizer with interpolated vertex colors.
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
import gc
import hashlib
import json
import math
import os
import random
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from PIL import Image


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
WORLDGEN_SOURCE = BASELINES / "sources/WorldGen/src"
TABLE2_ROOT = BASELINES / "data/table2"
ANNOTATION_ROOT = BASELINES / "annotations/worldgen"
FULL_ROOT = ANNOTATION_ROOT / "full"
DEFAULT_TASKS = (
    BASELINES / "methods/worldgen/protocol/generation/worldgen_mesh_demo_scenes.json"
)
WIDTH = 1280
HEIGHT = 720
TABLE2_IMAGE_YAWS = (-35.0, -25.0, -15.0, -5.0, 5.0, 15.0, 25.0, 35.0)
FULL_IMAGE_YAWS = (-60.0, -42.0, -24.0, -8.0, 8.0, 24.0, 42.0, 60.0)

TABLE2_SELECTIONS = {
    "indoor": (
        (
            "I-1B18AD31C1F7",
            TABLE2_ROOT / "indoor/worldgen/indoor_dining_room_01/seed_1",
        ),
        (
            "I-FA9662442027",
            TABLE2_ROOT / "indoor/worldgen/indoor_kitchen_04/seed_3",
        ),
        (
            "I-F3B172EC630E",
            TABLE2_ROOT / "indoor/worldgen/indoor_living_room_00/seed_0",
        ),
    ),
    "urban": (
        (
            "U-1F3DF1A14BB1",
            TABLE2_ROOT / "urban/worldgen/urban_commercial_four_way_05/seed_3",
        ),
        (
            "U-BD35BD152BB4",
            TABLE2_ROOT / "urban/worldgen/urban_residential_four_way_00/seed_1",
        ),
        (
            "U-66187967A738",
            TABLE2_ROOT / "urban/worldgen/urban_commercial_main_side_07/seed_2",
        ),
    ),
}


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


def atomic_json(path: Path, payload: Any) -> None:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def configure_offline_environment() -> None:
    cache = BASELINES / "checkpoints/WorldGen/huggingface"
    os.environ.setdefault("HF_HOME", str(cache))
    os.environ.setdefault("HF_HUB_CACHE", str(cache / "hub"))
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TORCH_HOME", str(BASELINES / "checkpoints/WorldGen/torch"))
    os.environ.setdefault("XDG_CACHE_HOME", str(BASELINES / "cache/worldgen"))
    os.environ.setdefault(
        "TORCH_EXTENSIONS_DIR", str(BASELINES / "cache/worldgen/torch_extensions")
    )
    os.environ.setdefault("TMPDIR", str(BASELINES / "tmp/worldgen_mesh_visualization"))
    Path(os.environ["TMPDIR"]).mkdir(parents=True, exist_ok=True)
    source = str(WORLDGEN_SOURCE)
    if source in sys.path:
        sys.path.remove(source)
    sys.path.insert(0, source)


def seed_everything(seed: int) -> None:
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_tasks(path: Path) -> list[dict[str, Any]]:
    path = require_below_baselines(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Task file must contain a JSON list")
    return payload


def mesh_record(mesh_path: Path, panorama_path: Path, mesh: Any) -> dict[str, Any]:
    vertices = np.asarray(mesh.vertices)
    triangles = np.asarray(mesh.triangles)
    colors = np.asarray(mesh.vertex_colors)
    return {
        "generator": "ZiYang-xie/WorldGen convert_rgbd2mesh_panorama",
        "worldgen_commit": "7ce7b2767fdf31e2727b69a2e61e2e950e3a017f",
        "depth_model": "haodongli/DA-2",
        "panorama": relative(panorama_path),
        "panorama_sha256": sha256_file(panorama_path),
        "mesh": relative(mesh_path),
        "mesh_sha256": sha256_file(mesh_path),
        "mesh_bytes": mesh_path.stat().st_size,
        "vertices": int(len(vertices)),
        "triangles": int(len(triangles)),
        "vertex_colors": bool(len(colors) == len(vertices)),
        "bounds_min": vertices.min(axis=0).tolist(),
        "bounds_max": vertices.max(axis=0).tolist(),
    }


def reconstruct_mesh(
    depth_model: Any, panorama_path: Path, mesh_path: Path
) -> dict[str, Any]:
    import open3d as o3d
    import torch
    from worldgen.pano_depth import pred_pano_depth
    from worldgen.utils.general_utils import convert_rgbd2mesh_panorama

    started = time.monotonic()
    with Image.open(panorama_path) as handle:
        predictions = pred_pano_depth(depth_model, handle.convert("RGB"))
    mesh = convert_rgbd2mesh_panorama(
        predictions["rgb"] / 255.0,
        predictions["distance"],
        predictions["rays"],
    )
    mesh_path.parent.mkdir(parents=True, exist_ok=True)
    wrote = o3d.io.write_triangle_mesh(
        str(mesh_path), mesh, write_ascii=False, compressed=False, print_progress=False
    )
    if not wrote or mesh_path.stat().st_size < 1024:
        raise RuntimeError(f"Failed to write official WorldGen mesh: {mesh_path}")
    record = mesh_record(mesh_path, panorama_path, mesh)
    record["reconstruction_wall_time_s"] = round(time.monotonic() - started, 6)
    atomic_json(mesh_path.with_name("mesh_manifest.json"), record)
    del predictions, mesh
    torch.cuda.empty_cache()
    return record


def command_reconstruct_existing(args: argparse.Namespace) -> int:
    configure_offline_environment()
    import torch
    from worldgen.pano_depth import build_depth_model

    depth_model = build_depth_model(torch.device("cuda"))
    failures = 0
    for run_text in args.run_dir:
        run = require_below_baselines(Path(run_text))
        panorama = run / "scene/panorama.png"
        mesh_path = run / "scene/mesh.ply"
        try:
            if mesh_path.is_file() and not args.force:
                print(f"MESH_SKIP_EXISTING {relative(mesh_path)}", flush=True)
                continue
            record = reconstruct_mesh(depth_model, panorama, mesh_path)
            print(
                f"MESH_RECONSTRUCTED path={relative(mesh_path)} "
                f"vertices={record['vertices']} triangles={record['triangles']}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            print(
                f"MESH_FAILED run={relative(run)} error={type(exc).__name__}:{exc}",
                flush=True,
            )
    return 1 if failures else 0


def command_generate_full(args: argparse.Namespace) -> int:
    configure_offline_environment()
    import torch
    from worldgen.pano_gen import build_pano_gen_model
    from worldgen.pano_gen import gen_pano_image

    tasks = load_tasks(args.task_file)
    wanted = set(args.scene_id or [row["scene_id"] for row in tasks])
    tasks = [row for row in tasks if row["scene_id"] in wanted]
    if not tasks:
        raise ValueError("No matching scene tasks")

    pano_model = build_pano_gen_model(device=torch.device("cuda"), low_vram=False)
    for task in tasks:
        scene_root = require_below_baselines(FULL_ROOT / task["scene_id"])
        panorama = scene_root / "native/scene/panorama.png"
        native_input = scene_root / "native/input/native_input.json"
        payload = {
            "method": "worldgen",
            "implementation": "ZiYang-xie/WorldGen",
            "mode": "t2s",
            "prompt": task["prompt"],
            "method_seed": int(task["seed"]),
            "resolution": [1600, 800],
            "num_inference_steps": 50,
            "guidance_scale": 7.0,
            "blend_extend": 6,
            "return_type": "official_triangle_mesh",
            "connectivity_intent": "single panorama and single mesh spanning one open threshold",
        }
        atomic_json(native_input, payload)
        if panorama.is_file() and not args.force:
            print(f"PANORAMA_SKIP_EXISTING {relative(panorama)}", flush=True)
            continue
        seed_everything(int(task["seed"]))
        started = time.monotonic()
        image = gen_pano_image(
            pano_model,
            prompt=task["prompt"],
            seed=int(task["seed"]),
            guidance_scale=7.0,
            num_inference_steps=50,
            height=800,
            width=1600,
            blend_extend=6,
            prefix="A high quality 360 panorama photo of",
            suffix="HDR, RAW, 360 consistent, omnidirectional",
        )
        panorama.parent.mkdir(parents=True, exist_ok=True)
        image.save(panorama)
        print(
            f"PANORAMA_GENERATED scene={task['scene_id']} "
            f"wall_time_s={time.monotonic()-started:.3f}",
            flush=True,
        )
    del pano_model
    gc.collect()
    torch.cuda.empty_cache()

    from worldgen.pano_depth import build_depth_model

    depth_model = build_depth_model(torch.device("cuda"))
    failures = 0
    for task in tasks:
        scene_root = FULL_ROOT / task["scene_id"]
        panorama = scene_root / "native/scene/panorama.png"
        mesh_path = scene_root / "native/scene/mesh.ply"
        try:
            if mesh_path.is_file() and not args.force:
                print(f"MESH_SKIP_EXISTING {relative(mesh_path)}", flush=True)
                continue
            record = reconstruct_mesh(depth_model, panorama, mesh_path)
            print(
                f"MESH_GENERATED scene={task['scene_id']} vertices={record['vertices']} "
                f"triangles={record['triangles']}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            print(
                f"MESH_FAILED scene={task['scene_id']} error={type(exc).__name__}:{exc}",
                flush=True,
            )
    return 1 if failures else 0


def camera_to_world(position: np.ndarray, yaw_degrees: float) -> np.ndarray:
    yaw = math.radians(yaw_degrees)
    forward = np.asarray([math.sin(yaw), 0.0, math.cos(yaw)], dtype=np.float32)
    right = np.asarray([math.cos(yaw), 0.0, -math.sin(yaw)], dtype=np.float32)
    down = np.asarray([0.0, 1.0, 0.0], dtype=np.float32)
    transform = np.eye(4, dtype=np.float32)
    transform[:3, 0] = right
    transform[:3, 1] = down
    transform[:3, 2] = forward
    transform[:3, 3] = position
    return transform


class MeshRasterRenderer:
    def __init__(
        self, mesh_path: Path, width: int = WIDTH, height: int = HEIGHT
    ) -> None:
        import moderngl
        import open3d as o3d

        source = o3d.io.read_triangle_mesh(str(mesh_path))
        vertices = np.asarray(source.vertices).astype(np.float32)
        faces = np.asarray(source.triangles).astype(np.uint32)
        colors = np.asarray(source.vertex_colors).astype(np.float32)
        if len(colors) != len(vertices):
            raise RuntimeError(f"Mesh has no per-vertex colors: {mesh_path}")
        self.width = width
        self.height = height
        self.moderngl = moderngl
        device_index = int(os.environ.get("MESH_EGL_DEVICE", "0"))
        self.context = moderngl.create_standalone_context(
            backend="egl", device_index=device_index
        )
        self.program = self.context.program(
            vertex_shader="""
                #version 330
                uniform mat4 mvp;
                in vec3 in_position;
                in vec3 in_color;
                out vec3 vertex_color;
                void main() {
                    gl_Position = mvp * vec4(in_position, 1.0);
                    vertex_color = in_color;
                }
            """,
            fragment_shader="""
                #version 330
                in vec3 vertex_color;
                out vec4 frag_color;
                void main() {
                    frag_color = vec4(vertex_color, 1.0);
                }
            """,
        )
        packed = np.concatenate([vertices, colors], axis=1).astype(np.float32)
        self.vertex_buffer = self.context.buffer(packed.tobytes())
        self.index_buffer = self.context.buffer(faces.reshape(-1).tobytes())
        self.vertex_array = self.context.vertex_array(
            self.program,
            [(self.vertex_buffer, "3f 3f", "in_position", "in_color")],
            self.index_buffer,
            index_element_size=4,
        )
        self.color_buffer = self.context.texture(
            (width, height), components=3, dtype="f1"
        )
        self.depth_buffer = self.context.depth_renderbuffer((width, height))
        self.framebuffer = self.context.framebuffer(
            color_attachments=[self.color_buffer], depth_attachment=self.depth_buffer
        )
        self.context.enable(moderngl.DEPTH_TEST)

    def render(
        self,
        position: np.ndarray,
        yaw_degrees: float,
        horizontal_fov_degrees: float = 90.0,
    ) -> np.ndarray:
        c2w = camera_to_world(position, yaw_degrees)
        w2c = np.linalg.inv(c2w).astype(np.float32)
        focal = self.width / (
            2.0 * math.tan(math.radians(horizontal_fov_degrees) / 2.0)
        )
        near = 0.01
        far = 100.0
        projection = np.asarray(
            [
                [2.0 * focal / self.width, 0.0, 0.0, 0.0],
                [0.0, 2.0 * focal / self.height, 0.0, 0.0],
                [
                    0.0,
                    0.0,
                    -(far + near) / (far - near),
                    -2.0 * far * near / (far - near),
                ],
                [0.0, 0.0, -1.0, 0.0],
            ],
            dtype=np.float32,
        )
        opencv_to_opengl = np.diag([1.0, -1.0, -1.0, 1.0]).astype(np.float32)
        mvp = projection @ opencv_to_opengl @ w2c
        self.program["mvp"].write(np.ascontiguousarray(mvp.T).tobytes())
        self.framebuffer.use()
        self.context.viewport = (0, 0, self.width, self.height)
        self.framebuffer.clear(0.0, 0.0, 0.0, 1.0, depth=1.0)
        self.vertex_array.render(mode=self.moderngl.TRIANGLES)
        output = np.frombuffer(
            self.framebuffer.read(components=3, alignment=1), dtype=np.uint8
        )
        output = output.reshape(self.height, self.width, 3)
        return np.flipud(output).copy()


def save_image(path: Path, rgb: np.ndarray) -> dict[str, Any]:
    require_below_baselines(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb, mode="RGB").save(path, compress_level=6)
    return {
        "path": relative(path),
        "width": int(rgb.shape[1]),
        "height": int(rgb.shape[0]),
        "sha256": sha256_file(path),
    }


def link_mesh(mesh_path: Path, link_path: Path) -> None:
    require_below_baselines(link_path)
    link_path.parent.mkdir(parents=True, exist_ok=True)
    if link_path.is_symlink() or link_path.exists():
        link_path.unlink()
    link_path.symlink_to(os.path.relpath(mesh_path, link_path.parent))


def render_images_from_mesh(mesh_path: Path, output_dir: Path) -> list[dict[str, Any]]:
    renderer = MeshRasterRenderer(mesh_path)
    records = []
    for index, yaw in enumerate(TABLE2_IMAGE_YAWS, start=1):
        position = np.zeros(3, dtype=np.float32)
        rgb = renderer.render(position, yaw, 90.0)
        record = save_image(output_dir / f"view_{index:02d}.png", rgb)
        record.update({"yaw_degrees": yaw, "camera_position_native": position.tolist()})
        records.append(record)
    return records


def command_render_table2(args: argparse.Namespace) -> int:
    domain = args.domain
    output_root = ANNOTATION_ROOT / domain / "images"
    items = []
    for blind_id, run in TABLE2_SELECTIONS[domain]:
        mesh_path = run / "scene/mesh.ply"
        if not mesh_path.is_file():
            raise FileNotFoundError(mesh_path)
        destination = output_root / blind_id
        images = render_images_from_mesh(mesh_path, destination)
        link_mesh(mesh_path, destination / "mesh.ply")
        mesh_manifest = json.loads(
            mesh_path.with_name("mesh_manifest.json").read_text(encoding="utf-8")
        )
        items.append(
            {
                "id": blind_id,
                "source_run": relative(run),
                "source_mesh": relative(mesh_path),
                "mesh_sha256": sha256_file(mesh_path),
                "mesh_vertices": mesh_manifest["vertices"],
                "mesh_triangles": mesh_manifest["triangles"],
                "renderer": "ModernGL/EGL GPU triangle rasterizer with vertex-color interpolation",
                "images": images,
            }
        )
        print(f"MESH_IMAGES_RENDERED domain={domain} id={blind_id}", flush=True)
    manifest = {
        "created_at_utc": utc_now(),
        "method": "worldgen",
        "domain": domain,
        "source_representation": "official_triangle_mesh",
        "images_have_overlays": False,
        "items": items,
    }
    atomic_json(output_root / "manifest.json", manifest)
    return 0


def encode_mesh_video(
    renderer: MeshRasterRenderer,
    output: Path,
    fps: int,
    duration_seconds: int,
) -> dict[str, Any]:
    output.parent.mkdir(parents=True, exist_ok=True)
    frames = fps * duration_seconds
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
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    assert process.stdin is not None
    try:
        for index in range(frames):
            fraction = index / (frames - 1)
            smooth = fraction * fraction * (3.0 - 2.0 * fraction)
            # The prompt places the camera on the threshold with exterior in
            # front (+Z).  Translate through that same threshold while adding
            # a gentle look-around, rather than cross-fading two images.
            position = np.asarray(
                [-0.02 + 0.04 * smooth, 0.0, -0.06 + 0.12 * smooth],
                dtype=np.float32,
            )
            yaw = -18.0 + 36.0 * smooth
            rgb = renderer.render(position, yaw, 86.0)
            process.stdin.write(np.ascontiguousarray(rgb).tobytes())
    finally:
        process.stdin.close()
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg failed with exit code {return_code}: {output}")
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
            str(output),
        ],
        check=True,
        stdout=subprocess.PIPE,
        text=True,
    )
    record = json.loads(probe.stdout)["streams"][0]
    record.update({"path": relative(output), "sha256": sha256_file(output)})
    return record


def command_render_full(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.task_file)
    wanted = set(args.scene_id or [row["scene_id"] for row in tasks])
    tasks = [row for row in tasks if row["scene_id"] in wanted]
    for task in tasks:
        scene_root = require_below_baselines(FULL_ROOT / task["scene_id"])
        mesh_path = scene_root / "native/scene/mesh.ply"
        if not mesh_path.is_file():
            raise FileNotFoundError(mesh_path)
        renderer = MeshRasterRenderer(mesh_path)
        images = []
        for index, yaw in enumerate(FULL_IMAGE_YAWS, start=1):
            rgb = renderer.render(np.zeros(3, dtype=np.float32), yaw, 90.0)
            record = save_image(scene_root / "images" / f"view_{index:02d}.png", rgb)
            record.update(
                {"yaw_degrees": yaw, "camera_position_native": [0.0, 0.0, 0.0]}
            )
            images.append(record)
        video = encode_mesh_video(
            renderer,
            scene_root / "video/indoor_to_outdoor.mp4",
            fps=args.fps,
            duration_seconds=args.duration,
        )
        link_mesh(mesh_path, scene_root / "mesh.ply")
        mesh_manifest = json.loads(
            mesh_path.with_name("mesh_manifest.json").read_text(encoding="utf-8")
        )
        manifest = {
            "created_at_utc": utc_now(),
            "scene_id": task["scene_id"],
            "method": "worldgen",
            "prompt": task["prompt"],
            "seed": task["seed"],
            "generation_contract": "one panorama -> one official triangle mesh -> mesh-rendered images/video",
            "connectivity": {
                "type": "single generated threshold scene",
                "single_mesh": True,
                "crossfade_or_panorama_projection_used": False,
            },
            "mesh": mesh_manifest,
            "renderer": "ModernGL/EGL GPU triangle rasterizer with vertex-color interpolation",
            "images_have_overlays": False,
            "images": images,
            "video": video,
        }
        atomic_json(scene_root / "manifest.json", manifest)
        print(f"FULL_MESH_DEMO_RENDERED scene={task['scene_id']}", flush=True)
    return 0


def command_render_one(args: argparse.Namespace) -> int:
    mesh_path = require_below_baselines(args.mesh)
    renderer = MeshRasterRenderer(mesh_path)
    rgb = renderer.render(
        np.asarray(args.position, dtype=np.float32), args.yaw, args.horizontal_fov
    )
    save_image(require_below_baselines(args.output), rgb)
    print(f"MESH_RENDER_TEST_OK {relative(args.output)}", flush=True)
    return 0


def command_aggregate_full(args: argparse.Namespace) -> int:
    tasks = load_tasks(args.task_file)
    scenes = []
    for task in tasks:
        manifest_path = require_below_baselines(
            FULL_ROOT / task["scene_id"] / "manifest.json"
        )
        if not manifest_path.is_file():
            raise FileNotFoundError(manifest_path)
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
        scenes.append(
            {
                "scene_id": record["scene_id"],
                "manifest": relative(manifest_path),
                "mesh": record["mesh"]["mesh"],
                "mesh_sha256": record["mesh"]["mesh_sha256"],
                "mesh_vertices": record["mesh"]["vertices"],
                "mesh_triangles": record["mesh"]["triangles"],
                "images": len(record["images"]),
                "video": record["video"],
            }
        )
    atomic_json(
        FULL_ROOT / "manifest.json",
        {
            "created_at_utc": utc_now(),
            "method": "worldgen",
            "scene_count": len(scenes),
            "generation_contract": "one panorama -> one official triangle mesh -> mesh-rendered images/video",
            "connectivity": {
                "type": "single generated threshold scene per demo",
                "single_mesh_per_scene": True,
                "crossfade_or_panorama_projection_used": False,
            },
            "renderer": "ModernGL/EGL GPU triangle rasterizer with vertex-color interpolation",
            "images_have_overlays": False,
            "scenes": scenes,
        },
    )
    print(f"FULL_MANIFEST_WRITTEN scenes={len(scenes)}", flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    reconstruct = sub.add_parser("reconstruct-existing")
    reconstruct.add_argument("--run-dir", action="append", required=True)
    reconstruct.add_argument("--force", action="store_true")

    generate = sub.add_parser("generate-full")
    generate.add_argument("--task-file", type=Path, default=DEFAULT_TASKS)
    generate.add_argument("--scene-id", action="append")
    generate.add_argument("--force", action="store_true")

    table2 = sub.add_parser("render-table2")
    table2.add_argument("--domain", choices=("indoor", "urban"), required=True)

    full = sub.add_parser("render-full")
    full.add_argument("--task-file", type=Path, default=DEFAULT_TASKS)
    full.add_argument("--scene-id", action="append")
    full.add_argument("--fps", type=int, default=15)
    full.add_argument("--duration", type=int, default=8)

    aggregate = sub.add_parser("aggregate-full")
    aggregate.add_argument("--task-file", type=Path, default=DEFAULT_TASKS)

    one = sub.add_parser("render-one")
    one.add_argument("--mesh", type=Path, required=True)
    one.add_argument("--output", type=Path, required=True)
    one.add_argument("--yaw", type=float, default=0.0)
    one.add_argument("--horizontal-fov", type=float, default=90.0)
    one.add_argument("--position", type=float, nargs=3, default=(0.0, 0.0, 0.0))

    args = parser.parse_args()
    if args.command == "reconstruct-existing":
        return command_reconstruct_existing(args)
    if args.command == "generate-full":
        return command_generate_full(args)
    if args.command == "render-table2":
        return command_render_table2(args)
    if args.command == "render-full":
        return command_render_full(args)
    if args.command == "aggregate-full":
        return command_aggregate_full(args)
    if args.command == "render-one":
        return command_render_one(args)
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())

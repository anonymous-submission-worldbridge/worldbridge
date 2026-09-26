#!/usr/bin/env python3
"""Render a compiled Table-2 layout into SpatialGen's native input folders.

This intentionally mirrors SpatialGen's published PyTorch3D wireframe
preprocessor.  It additionally writes the layout-depth, semantic, depth and
placeholder RGB files required by the upstream ExampleDataset loader.  The
placeholder target RGB frames are never used as generation targets; frame 0
is replaced by the FLUX reference stage before multi-view inference.
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
import sys
from pathlib import Path
from typing import Any

import numpy as np
import torch
import trimesh
from PIL import Image
from pytorch3d.renderer import MeshRasterizer, RasterizationSettings
from pytorch3d.structures import Meshes
from pytorch3d.utils.camera_conversions import cameras_from_opencv_projection


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
SPATIALGEN_ROOT = BASELINES_ROOT / "vendor/SpatialGen"
WIRE_FRAME_PATH = SPATIALGEN_ROOT / "assets/wireframe.ply"
sys.path.insert(0, str(SPATIALGEN_ROOT))

from src.utils.flux_utils import parse_layout_data  # noqa: E402


def assert_baselines_path(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Refusing to write outside baselines/: {resolved}") from exc
    return resolved


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def render_native_inputs(run_dir: Path, device_name: str) -> dict[str, Any]:
    run_dir = assert_baselines_path(run_dir)
    spec_path = run_dir / "input/spec.json"
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    scene_dir = run_dir / "input/dataset" / spec["spec_id"]
    layout_path = scene_dir / "room_layout.json"
    cameras_path = scene_dir / "cameras.json"
    layout_data = json.loads(layout_path.read_text(encoding="utf-8"))
    camera_data = json.loads(cameras_path.read_text(encoding="utf-8"))

    device = torch.device(device_name)
    wireframe = trimesh.load_mesh(WIRE_FRAME_PATH)
    meshes, colors = parse_layout_data(layout_data, wireframe)
    vertices = [
        torch.as_tensor(mesh.vertices, dtype=torch.float32, device=device)
        for mesh in meshes
    ]
    faces = [
        torch.as_tensor(mesh.faces, dtype=torch.int32, device=device) for mesh in meshes
    ]
    mesh_batch = Meshes(verts=vertices, faces=faces)
    rasterizer = MeshRasterizer(
        raster_settings=RasterizationSettings(
            image_size=(int(camera_data["height"]), int(camera_data["width"])),
            blur_radius=1e-5,
            faces_per_pixel=1,
            perspective_correct=True,
            clip_barycentric_coords=True,
            z_clip_value=1e-5,
        )
    ).to(device)
    intrinsic = torch.as_tensor(
        np.asarray(camera_data["intrinsic"], dtype=np.float32)[None],
        device=device,
    )
    image_size = torch.tensor(
        [[camera_data["height"], camera_data["width"]]],
        dtype=torch.float32,
        device=device,
    )

    output_dirs = {
        name: scene_dir / name
        for name in (
            "rgb",
            "depth",
            "semantic",
            "layout_semantic",
            "layout_depth",
            "condition",
        )
    }
    for directory in output_dirs.values():
        directory.mkdir(parents=True, exist_ok=True)

    # The combined mesh is an auditable visualization of the exact layout
    # passed to the native preprocessor; it is not a replacement 3D output.
    layout_mesh_path = run_dir / "input/layout_bbox.ply"
    trimesh.util.concatenate(meshes).export(layout_mesh_path)

    frame_records: list[dict[str, Any]] = []
    camera_keys = sorted(camera_data["cameras"], key=lambda key: int(key))
    for camera_key in camera_keys:
        c2w = np.asarray(camera_data["cameras"][camera_key], dtype=np.float32)
        w2c = torch.as_tensor(np.linalg.inv(c2w)[None], device=device)
        camera = cameras_from_opencv_projection(
            w2c[..., :3, :3],
            w2c[..., :3, 3],
            camera_matrix=intrinsic,
            image_size=image_size,
        ).to(device)
        fragments = rasterizer(mesh_batch, cameras=camera)
        depth_per_mesh = fragments.zbuf[..., 0]
        depth_per_mesh[depth_per_mesh == -1.0] = torch.inf

        nearest_depth, nearest_mesh = torch.min(depth_per_mesh, dim=0)
        visible_mesh_ids = torch.unique(nearest_mesh[torch.isfinite(nearest_depth)])
        near_layout = torch.argmin(depth_per_mesh[:3], dim=0)
        semantic_mesh = torch.full_like(near_layout, -1)
        for mesh_id in visible_mesh_ids:
            mesh_id_int = int(mesh_id.item())
            if mesh_id_int < 3:
                semantic_mesh[near_layout == mesh_id_int] = mesh_id_int

        if depth_per_mesh.shape[0] > 3:
            near_object_depth, near_object = torch.min(depth_per_mesh[3:], dim=0)
            near_object = near_object + 3
            near_object[~torch.isfinite(near_object_depth)] = -1
            # Match the official FLUX preprocessor: visible object wireframes
            # are overlaid after room surfaces to retain layout structure.
            for mesh_id in visible_mesh_ids:
                mesh_id_int = int(mesh_id.item())
                if mesh_id_int >= 3:
                    semantic_mesh[near_object == mesh_id_int] = mesh_id_int

        semantic = torch.zeros(
            (*semantic_mesh.shape, 3), dtype=torch.uint8, device=device
        )
        selected_depth = torch.zeros_like(nearest_depth)
        for mesh_id in visible_mesh_ids:
            mesh_id_int = int(mesh_id.item())
            selected = semantic_mesh == mesh_id_int
            semantic[selected] = torch.tensor(
                colors[mesh_id_int], dtype=torch.uint8, device=device
            )
            selected_depth[selected] = depth_per_mesh[mesh_id_int][selected]
        selected_depth[~torch.isfinite(selected_depth)] = 0.0

        semantic_image = Image.fromarray(semantic.cpu().numpy(), mode="RGB")
        depth_mm = (
            selected_depth.clamp(0.0, 65.535)
            .mul(1000.0)
            .round()
            .to(torch.uint16)
            .cpu()
            .numpy()
        )
        depth_image = Image.fromarray(depth_mm, mode="I;16")
        frame_name = f"frame_{camera_key}"
        semantic_image.save(output_dirs["condition"] / f"{frame_name}.jpg")
        semantic_image.save(output_dirs["layout_semantic"] / f"{frame_name}.jpg")
        semantic_image.save(output_dirs["semantic"] / f"{frame_name}.jpg")
        depth_image.save(output_dirs["layout_depth"] / f"{frame_name}.png")
        depth_image.save(output_dirs["depth"] / f"{frame_name}.png")
        Image.new(
            "RGB",
            (int(camera_data["width"]), int(camera_data["height"])),
            color=(127, 127, 127),
        ).save(output_dirs["rgb"] / f"{frame_name}.jpg")
        valid_depth = selected_depth[selected_depth > 0]
        frame_records.append(
            {
                "camera_key": int(camera_key),
                "semantic_colors": int(
                    torch.unique(semantic.reshape(-1, 3), dim=0).shape[0]
                ),
                "valid_depth_fraction": float(
                    (selected_depth > 0).float().mean().item()
                ),
                "min_depth_m": float(valid_depth.min().item())
                if valid_depth.numel()
                else None,
                "max_depth_m": float(valid_depth.max().item())
                if valid_depth.numel()
                else None,
            }
        )

    payload = {
        "tool": "baselines/methods/spatialgen/tools/prepare_spatialgen_inputs.py",
        "spatialgen_commit": "677c1168b359b00ae4a64a58783bc71048aabcdd",
        "spec_id": spec["spec_id"],
        "device": str(device),
        "frame_count": len(frame_records),
        "room_layout_sha256": sha256_file(layout_path),
        "cameras_sha256": sha256_file(cameras_path),
        "wireframe_sha256": sha256_file(WIRE_FRAME_PATH),
        "rgb_placeholder_value": 127,
        "depth_encoding": "uint16 millimetres; zero is invalid",
        "frames": frame_records,
    }
    atomic_json(run_dir / "input/preparation.json", payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args()
    payload = render_native_inputs(args.run_dir, args.device)
    print(
        f"SPATIALGEN_INPUTS_PREPARED spec={payload['spec_id']} "
        f"frames={payload['frame_count']} device={payload['device']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

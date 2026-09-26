#!/usr/bin/env python3
"""Render a trained SpatialGen Gaussian under the frozen Table-2 cameras."""

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
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import torch
from PIL import Image
from scipy.spatial.transform import Rotation, Slerp


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
RADEGS_ROOT = BASELINES_ROOT / "vendor/SpatialGen/src/recons/Sparse-RaDeGS"
sys.path.insert(0, str(RADEGS_ROOT))

from gaussian_renderer import render  # noqa: E402
from scene.cameras import Camera  # noqa: E402
from scene.gaussian_model import GaussianModel  # noqa: E402


SEQUENCE_FRAMES = 50
ANCHOR_INDICES = (0, 7, 14, 21, 28, 35, 42, 49)
HORIZONTAL_FOV_DEGREES = 70.0
CAMERA_HEIGHT_M = 1.55


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


def interpolate_cameras(cameras: dict[str, Any], count: int) -> list[np.ndarray]:
    keys = sorted(cameras, key=lambda key: int(key))
    poses = [np.asarray(cameras[key], dtype=np.float64).reshape(4, 4) for key in keys]
    key_times = np.arange(len(poses), dtype=np.float64)
    output_times = np.linspace(0.0, float(len(poses) - 1), count)
    rotations = Slerp(
        key_times, Rotation.from_matrix(np.stack([pose[:3, :3] for pose in poses]))
    )(output_times).as_matrix()
    centers = np.stack([pose[:3, 3] for pose in poses])
    interpolated_centers = np.stack(
        [np.interp(output_times, key_times, centers[:, axis]) for axis in range(3)],
        axis=1,
    )
    output: list[np.ndarray] = []
    for rotation, center in zip(rotations, interpolated_centers):
        pose = np.eye(4, dtype=np.float64)
        pose[:3, :3] = rotation
        pose[:3, 3] = center
        output.append(pose)
    return output


def metric_to_normalized_pose(
    metric_pose: np.ndarray, reference_metric_pose: np.ndarray, scene_scale: float
) -> np.ndarray:
    relative = np.linalg.inv(reference_metric_pose) @ metric_pose
    normalized = relative.copy()
    normalized[:3, 3] *= scene_scale
    return normalized


def vertical_fov(horizontal_fov: float, width: int, height: int) -> float:
    return 2.0 * math.atan(math.tan(horizontal_fov / 2.0) * height / width)


def build_camera(c2w: np.ndarray, width: int, height: int, uid: int) -> Camera:
    w2c = np.linalg.inv(c2w)
    fov_x = math.radians(HORIZONTAL_FOV_DEGREES)
    fov_y = vertical_fov(fov_x, width, height)
    return Camera(
        colmap_id=uid,
        R=c2w[:3, :3],
        T=w2c[:3, 3],
        FoVx=fov_x,
        FoVy=fov_y,
        image=torch.zeros((3, height, width), dtype=torch.float32),
        depth=torch.zeros((height, width), dtype=torch.float32),
        gt_alpha_mask=None,
        image_name=str(uid),
        uid=uid,
        warp_mask=None,
        K=None,
        src_R=None,
        src_T=None,
        src_uid=uid,
        semantic_feature=torch.zeros((3, height, width), dtype=torch.float32),
    )


def save_tensor_png(tensor: torch.Tensor, path: Path) -> None:
    assert_baselines_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    array = (
        tensor.detach()
        .float()
        .clamp(0.0, 1.0)
        .permute(1, 2, 0)
        .mul(255.0)
        .round()
        .to(torch.uint8)
        .cpu()
        .numpy()
    )
    temporary = path.with_suffix(path.suffix + ".tmp")
    Image.fromarray(array, mode="RGB").save(temporary, format="PNG")
    temporary.replace(path)


def camera_record(
    index: int, metric_c2w: np.ndarray, width: int, height: int
) -> dict[str, Any]:
    blender_c2w = metric_c2w.copy()
    blender_c2w[:3, 1:3] *= -1.0
    fov_x = math.radians(HORIZONTAL_FOV_DEGREES)
    focal_x = 0.5 * width / math.tan(fov_x / 2.0)
    focal_y = focal_x
    intrinsic = [
        [focal_x, 0.0, width / 2.0],
        [0.0, focal_y, height / 2.0],
        [0.0, 0.0, 1.0],
    ]
    return {
        "frame_index": index,
        "camera_to_world_opencv": metric_c2w.tolist(),
        "camera_to_world_blender": blender_c2w.tolist(),
        "width": width,
        "height": height,
        "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
        # ``K`` is the canonical Table-2 field consumed by eval_worldscore.py;
        # retain ``intrinsic`` as an explicit alias for native-format audits.
        "K": intrinsic,
        "intrinsic": intrinsic,
        "near_m": 0.01,
        "far_m": 100.0,
    }


def locate_native_artifacts(run_dir: Path) -> tuple[Path, Path]:
    native_root = run_dir / "scene/native"
    inference_results = sorted(native_root.glob("**/inference_results.npz"))
    gaussian_files = sorted(
        native_root.glob("**/point_cloud/iteration_7000/point_cloud.ply")
    )
    if len(inference_results) != 1:
        raise RuntimeError(
            f"Expected exactly one inference_results.npz under {native_root}, got {len(inference_results)}"
        )
    if len(gaussian_files) != 1:
        raise RuntimeError(
            f"Expected exactly one iteration-7000 Gaussian under {native_root}, got {len(gaussian_files)}"
        )
    return inference_results[0], gaussian_files[0]


@torch.no_grad()
def render_table2(run_dir: Path) -> dict[str, Any]:
    run_dir = assert_baselines_path(run_dir)
    inference_path, gaussian_path = locate_native_artifacts(run_dir)
    spec = json.loads((run_dir / "input/spec.json").read_text(encoding="utf-8"))
    camera_data = json.loads(
        (run_dir / "input/dataset" / spec["spec_id"] / "cameras.json").read_text(
            encoding="utf-8"
        )
    )
    with np.load(inference_path, allow_pickle=True) as archive:
        if len(archive.files) != 1:
            raise RuntimeError(f"Unexpected rooms in {inference_path}: {archive.files}")
        results = archive[archive.files[0]][()]
    reference_metric_pose = np.asarray(
        results["input_poses_metric"][0], dtype=np.float64
    )
    scene_scale = float(np.asarray(results["scene_scale"]).reshape(-1)[0])
    native_poses = np.concatenate(
        [np.asarray(results["input_poses"]), np.asarray(results["target_poses"])],
        axis=0,
    )
    native_metric_poses = np.concatenate(
        [
            np.asarray(results["input_poses_metric"]),
            np.asarray(results["target_poses_metric"]),
        ],
        axis=0,
    )
    compiled_poses = [
        np.asarray(camera_data["cameras"][key], dtype=np.float64)
        for key in sorted(camera_data["cameras"], key=lambda key: int(key))
    ]
    mapped_compiled = np.stack(
        [
            metric_to_normalized_pose(pose, reference_metric_pose, scene_scale)
            for pose in compiled_poses
        ]
    )
    # ExampleDataset reads frame names lexicographically (0, 1, 10, ...,
    # 15, 2, ...), whereas the compiled camera contract is numeric.  Recover
    # that permutation from the metric poses before validating the mapping.
    native_to_compiled_order = []
    metric_match_errors = []
    for native_metric_pose in native_metric_poses:
        errors = np.max(
            np.abs(np.stack(compiled_poses) - native_metric_pose), axis=(1, 2)
        )
        matched_index = int(np.argmin(errors))
        native_to_compiled_order.append(matched_index)
        metric_match_errors.append(float(errors[matched_index]))
    if sorted(native_to_compiled_order) != list(range(len(compiled_poses))):
        raise RuntimeError(
            "SpatialGen metric poses do not form a permutation of compiled cameras: "
            f"order={native_to_compiled_order}"
        )
    metric_pose_match_max_abs_error = max(metric_match_errors)
    pose_mapping_max_abs_error = float(
        np.max(np.abs(mapped_compiled[native_to_compiled_order] - native_poses))
    )
    if pose_mapping_max_abs_error > 2e-4:
        raise RuntimeError(
            "Metric-to-native pose mapping disagrees with SpatialGen inference: "
            f"max_abs_error={pose_mapping_max_abs_error}"
        )

    metric_poses = interpolate_cameras(camera_data["cameras"], SEQUENCE_FRAMES)
    normalized_poses = [
        metric_to_normalized_pose(pose, reference_metric_pose, scene_scale)
        for pose in metric_poses
    ]
    gaussian = GaussianModel(3)
    gaussian.load_ply(str(gaussian_path))
    pipe = SimpleNamespace(
        debug=False, convert_SHs_python=False, compute_cov3D_python=False
    )
    background = torch.zeros(3, dtype=torch.float32, device="cuda")

    sequence_dir = run_dir / "renders/sequence"
    anchors_dir = run_dir / "renders/anchors"
    # Keep SpatialGen's native semantic feature render only as an auxiliary
    # diagnostic.  The canonical ``renders/semantic_pred`` directory is
    # populated later by the same fixed ADE20K SegFormer used for every method.
    native_semantic_dir = run_dir / "renders/aux/native_semantic"
    for index, normalized_pose in enumerate(normalized_poses):
        camera = build_camera(normalized_pose, 512, 512, index)
        output = render(camera, gaussian, pipe, background)
        save_tensor_png(output["render"], sequence_dir / f"rgb_{index:03d}.png")
        del output, camera

    for anchor_index, sequence_index in enumerate(ANCHOR_INDICES):
        camera = build_camera(normalized_poses[sequence_index], 1280, 720, anchor_index)
        output = render(camera, gaussian, pipe, background)
        save_tensor_png(output["render"], anchors_dir / f"rgb_{anchor_index:03d}.png")
        save_tensor_png(
            output["feature_map"],
            native_semantic_dir / f"semantic_{anchor_index:03d}.png",
        )
        del output, camera

    sequence_records = [
        camera_record(index, pose, 512, 512) for index, pose in enumerate(metric_poses)
    ]
    camera_payload = {
        "coordinate_system": "metric z-up world; OpenCV c2w is authoritative",
        "camera_pose_contract": {
            "camera_height_m": CAMERA_HEIGHT_M,
            "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
            "near_m": 0.01,
            "far_m": 100.0,
        },
        "sequence": sequence_records,
        "anchors": [sequence_records[index] for index in ANCHOR_INDICES],
    }
    atomic_json(sequence_dir / "cameras.json", camera_payload)

    canonical_scene = run_dir / "scene/scene.ply"
    if canonical_scene.is_symlink() or canonical_scene.exists():
        canonical_scene.unlink()
    canonical_scene.symlink_to(gaussian_path.relative_to(canonical_scene.parent))
    payload = {
        "tool": "baselines/methods/spatialgen/tools/render_spatialgen_generation.py",
        "spec_id": spec["spec_id"],
        "inference_results": str(inference_path.relative_to(run_dir)),
        "gaussian": str(gaussian_path.relative_to(run_dir)),
        "gaussian_sha256": sha256_file(gaussian_path),
        "scene_scale": scene_scale,
        "native_to_compiled_camera_order": native_to_compiled_order,
        "metric_pose_match_max_abs_error": metric_pose_match_max_abs_error,
        "pose_mapping_max_abs_error": pose_mapping_max_abs_error,
        "sequence_frames": SEQUENCE_FRAMES,
        "sequence_resolution": [512, 512],
        "anchor_indices_zero_based": list(ANCHOR_INDICES),
        "anchor_resolution": [1280, 720],
        "horizontal_fov_degrees": HORIZONTAL_FOV_DEGREES,
    }
    atomic_json(run_dir / "renders/renderer.json", payload)
    torch.cuda.empty_cache()
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    payload = render_table2(args.run_dir)
    print(
        f"SPATIALGEN_TABLE2_RENDER_OK spec={payload['spec_id']} "
        f"frames={payload['sequence_frames']}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

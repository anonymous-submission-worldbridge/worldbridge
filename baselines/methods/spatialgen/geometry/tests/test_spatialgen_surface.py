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

import numpy as np

from baselines.methods.spatialgen.geometry.tools.reconstruct_spatialgen_surface import (
    calibrate_similarity,
)
from baselines.methods.spatialgen.geometry.tools.reconstruct_spatialgen_surface import (
    occupied_voxels_to_mesh,
)
from baselines.methods.spatialgen.geometry.tools.reconstruct_spatialgen_surface import (
    spawn_from_native_input,
)
from baselines.methods.spatialgen.geometry.tools.reconstruct_spatialgen_surface import (
    transform_points,
)
from baselines.methods.spatialgen.geometry.tools.reconstruct_spatialgen_surface import (
    voxelize_view_points,
)


def rotation_z(angle):
    cosine, sine = np.cos(angle), np.sin(angle)
    return np.asarray([[cosine, -sine, 0.0], [sine, cosine, 0.0], [0.0, 0.0, 1.0]])


def test_camera_similarity_recovers_meter_frame():
    rotations = [rotation_z(value) for value in (0.0, 0.23, 0.71, 1.34)]
    positions = np.asarray(
        [[0.0, 0.0, 0.0], [0.2, -0.1, 0.05], [0.7, 0.3, -0.2], [1.2, -0.4, 0.1]]
    )
    align = np.asarray([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    scale = 4.25
    translation = np.asarray([1.1, -2.3, 0.8])
    normalized = [
        {"rotation": rotation.tolist(), "position": position.tolist()}
        for rotation, position in zip(rotations, positions)
    ]
    # Store the compiled poses in an order different from the native cameras.
    order = [2, 0, 3, 1]
    compiled = {}
    for compiled_index, native_index in enumerate(order):
        pose = np.eye(4)
        pose[:3, :3] = align @ rotations[native_index]
        pose[:3, 3] = scale * (align @ positions[native_index]) + translation
        compiled[str(compiled_index)] = pose.tolist()

    result = calibrate_similarity(normalized, compiled)
    assert np.allclose(result["rotation"], align, atol=1e-10)
    assert np.isclose(result["scale"], scale)
    assert np.allclose(result["translation"], translation, atol=1e-10)
    assert result["position_rmse_m"] < 1e-10
    assert np.allclose(
        transform_points(positions, result), scale * (positions @ align.T) + translation
    )


def test_voxel_hits_are_counted_once_per_view_and_meshed_without_internal_face():
    views = [
        np.asarray([[0.1, 0.1, 0.1], [0.2, 0.1, 0.1], [1.1, 0.1, 0.1]]),
        np.asarray([[0.3, 0.1, 0.1], [1.2, 0.1, 0.1]]),
    ]
    occupied, stats = voxelize_view_points(
        views,
        lower=np.zeros(3),
        upper=np.asarray([2.0, 1.0, 1.0]),
        voxel_size=1.0,
        minimum_views=2,
    )
    assert occupied.shape == (2, 1, 1)
    assert occupied.all()
    assert stats["maximum_distinct_view_hits"] == 2
    vertices, faces = occupied_voxels_to_mesh(occupied, np.zeros(3), 1.0)
    assert vertices.shape == (12, 3)
    assert faces.shape == (20, 3)


def test_entrance_spawn_is_inset_toward_room_center():
    native = {
        "layout_objects": [{"role": "entrance_door", "center_m": [-2.0, -1.0, 1.0]}]
    }
    spawn, source = spawn_from_native_input(native, [6.0, 5.0, 3.0], 0.45)
    assert source == "entrance_door_inset"
    assert np.isclose(
        np.linalg.norm(np.asarray(spawn[:2]) - np.asarray([-2.0, -1.0])), 0.45
    )
    assert spawn[2] == 0.0

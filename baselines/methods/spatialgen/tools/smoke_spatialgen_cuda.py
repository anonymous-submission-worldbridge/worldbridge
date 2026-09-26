#!/usr/bin/env python3
"""Run minimal forward kernels for SpatialGen's two compiled CUDA extensions."""

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


import math
import sys
from pathlib import Path

import torch


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
RADEGS_ROOT = BASELINES_ROOT / "vendor/SpatialGen/src/recons/Sparse-RaDeGS"
sys.path.insert(0, str(RADEGS_ROOT))

from diff_gaussian_rasterization import (  # noqa: E402
    GaussianRasterizationSettings,
    GaussianRasterizer,
)
from simple_knn._C import distCUDA2  # noqa: E402
from utils.graphics_utils import getProjectionMatrix  # noqa: E402


def main() -> int:
    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable")
    device = torch.device("cuda:0")

    points = torch.tensor(
        [
            [-0.3, -0.2, 2.0],
            [0.3, -0.2, 2.0],
            [-0.3, 0.2, 2.0],
            [0.3, 0.2, 2.0],
        ],
        dtype=torch.float32,
        device=device,
    )
    distances = distCUDA2(points)
    if distances.shape != (4,) or not torch.isfinite(distances).all():
        raise RuntimeError(f"simple-knn returned invalid output: {distances}")

    fov = math.radians(70.0)
    view = torch.eye(4, dtype=torch.float32, device=device)
    projection = (
        getProjectionMatrix(znear=0.01, zfar=100.0, fovX=fov, fovY=fov)
        .transpose(0, 1)
        .to(device)
    )
    settings = GaussianRasterizationSettings(
        image_height=32,
        image_width=32,
        tanfovx=math.tan(fov / 2.0),
        tanfovy=math.tan(fov / 2.0),
        kernel_size=0.0,
        bg=torch.zeros(3, dtype=torch.float32, device=device),
        scale_modifier=1.0,
        viewmatrix=view,
        projmatrix=view @ projection,
        sh_degree=0,
        campos=torch.zeros(3, dtype=torch.float32, device=device),
        prefiltered=False,
        require_depth=True,
        require_coord=True,
        debug=False,
    )
    rasterizer = GaussianRasterizer(settings)
    rendered = rasterizer(
        means3D=points,
        means2D=torch.zeros_like(points),
        colors_precomp=torch.tensor(
            [[1.0, 0.0, 0.0]] * 4, dtype=torch.float32, device=device
        ),
        semantic_feature=torch.tensor(
            [[0.0, 1.0, 0.0]] * 4, dtype=torch.float32, device=device
        ),
        opacities=torch.full((4, 1), 0.8, dtype=torch.float32, device=device),
        scales=torch.full((4, 3), 0.08, dtype=torch.float32, device=device),
        rotations=torch.tensor(
            [[1.0, 0.0, 0.0, 0.0]] * 4, dtype=torch.float32, device=device
        ),
    )
    color, semantic, radii = rendered[0], rendered[1], rendered[2]
    torch.cuda.synchronize()
    if color.shape != (3, 32, 32) or semantic.shape != (3, 32, 32):
        raise RuntimeError(
            f"Rasterizer returned unexpected shapes: {color.shape}, {semantic.shape}"
        )
    if not torch.isfinite(color).all() or not torch.isfinite(semantic).all():
        raise RuntimeError("Rasterizer returned non-finite pixels")
    if not torch.any(radii > 0):
        raise RuntimeError("Rasterizer did not make any test Gaussian visible")
    print(
        "SPATIALGEN_CUDA_SMOKE_OK "
        f"gpu={torch.cuda.get_device_name(device)} "
        f"visible={int((radii > 0).sum().item())} "
        f"color_max={float(color.max().item()):.6f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

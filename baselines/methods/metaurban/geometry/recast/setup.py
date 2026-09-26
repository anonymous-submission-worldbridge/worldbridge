"""Build the existing HY-World/Recast sources against this host ABI."""

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


import os
from pathlib import Path

from pybind11.setup_helpers import Pybind11Extension, build_ext
from setuptools import setup


HERE = _BASELINE_PROJECT_ROOT / "baselines/methods/metaurban/geometry/recast"
BASELINES = HERE.parents[1]
NAVMESH = BASELINES / "sources/HY-World-2.0/hyworld2/worldgen/third_party/navmesh"
RECAST = (
    BASELINES / "sources/HY-World-2.0/hyworld2/worldgen/third_party/recastnavigation"
)

sources = [NAVMESH / "full_recast_bindings.cpp", NAVMESH / "navmesh_builder.cpp"]
sources += [
    RECAST / "Recast/Source" / name
    for name in (
        "Recast.cpp",
        "RecastAlloc.cpp",
        "RecastArea.cpp",
        "RecastAssert.cpp",
        "RecastContour.cpp",
        "RecastFilter.cpp",
        "RecastLayers.cpp",
        "RecastMesh.cpp",
        "RecastMeshDetail.cpp",
        "RecastRasterization.cpp",
        "RecastRegion.cpp",
    )
]
sources += [
    RECAST / "Detour/Source" / name
    for name in (
        "DetourAlloc.cpp",
        "DetourAssert.cpp",
        "DetourCommon.cpp",
        "DetourNavMesh.cpp",
        "DetourNavMeshBuilder.cpp",
        "DetourNavMeshQuery.cpp",
        "DetourNode.cpp",
    )
]

setup(
    name="worldbridge-table3-metaurban-recast",
    version="0.1.0",
    ext_modules=[
        Pybind11Extension(
            "recast",
            [os.fspath(path) for path in sources],
            include_dirs=[
                os.fspath(RECAST / "Recast/Include"),
                os.fspath(RECAST / "Detour/Include"),
                os.fspath(NAVMESH),
            ],
            define_macros=[("RC_MAX_VERTS_PER_POLY", "6")],
            cxx_std=11,
            extra_compile_args=["-O3"],
        )
    ],
    cmdclass={"build_ext": build_ext},
    zip_safe=False,
)

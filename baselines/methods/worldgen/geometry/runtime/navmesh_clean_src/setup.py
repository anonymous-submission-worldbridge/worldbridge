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

from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension, build_ext
import os
import sys

# Prefer RECAST_PATH to support temporary directories used by pip
# Otherwise use the original relative path; ensure it is valid before installation
recast_path = os.environ.get("RECAST_PATH", "../../third_party/recastnavigation")
# Resolve an absolute path so pip working-directory changes do not break it
recast_path = os.path.abspath(recast_path)

# Validate the path
if not os.path.exists(recast_path):
    print(f"\033[31mError: RecastNavigation path does not exist: {recast_path}\033[0m")
    print("To resolve this:")
    print("  1. Place recastnavigation at:../../third_party/recastnavigation")
    print(
        "  2. Or set its location with an environment variable:export RECAST_PATH=/path/to/recastnavigation"
    )
    raise SystemExit(1)

# -------------------------- 2. Build source configuration (unchanged except for absolute paths) --------------------------
sources = [
    "full_recast_bindings.cpp",
    "navmesh_builder.cpp",
    # Recast sources (absolute paths are more reliable during pip installation)
    os.path.join(recast_path, "Recast/Source/Recast.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastAlloc.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastArea.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastAssert.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastContour.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastFilter.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastLayers.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastMesh.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastMeshDetail.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastRasterization.cpp"),
    os.path.join(recast_path, "Recast/Source/RecastRegion.cpp"),
    # Detour sources
    os.path.join(recast_path, "Detour/Source/DetourAlloc.cpp"),
    os.path.join(recast_path, "Detour/Source/DetourAssert.cpp"),
    os.path.join(recast_path, "Detour/Source/DetourCommon.cpp"),
    os.path.join(recast_path, "Detour/Source/DetourNavMesh.cpp"),
    os.path.join(recast_path, "Detour/Source/DetourNavMeshBuilder.cpp"),
    os.path.join(recast_path, "Detour/Source/DetourNavMeshQuery.cpp"),
    os.path.join(recast_path, "Detour/Source/DetourNode.cpp"),
]

# -------------------------- 3. Extension configuration with cross-platform compilation --------------------------
ext_modules = [
    Pybind11Extension(
        "recast",  # Package name used by import recast
        sources,
        include_dirs=[
            os.path.join(recast_path, "Recast/Include"),
            os.path.join(recast_path, "Detour/Include"),
            os.path.abspath(
                "."
            ),  # Absolute current directory to avoid pip temporary-directory issues
        ],
        define_macros=[
            ("RC_MAX_VERTS_PER_POLY", "6"),
        ],
        cxx_std=11,  # Recast requires C++11; specify it to avoid compilation errors
        # Optional platform-specific optimization; global imports are unaffected
        extra_compile_args=["-O3"] if not sys.platform.startswith("win") else ["/O2"],
    ),
]

# -------------------------- Standard pip installation configuration --------------------------
setup(
    name="recast",  # Package name used by pip install
    version="0.1.0",  # Version
    author="ewrfcas&zhenyangliu",
    description="Pybind11 bindings for RecastNavigation",
    ext_modules=ext_modules,
    cmdclass={"build_ext": build_ext},  # Required for pybind11 compilation
    zip_safe=False,  # Native extensions cannot be zip-safe; this must be False
    python_requires=">=3.6",  # Specify compatible Python versions to avoid version conflicts
)

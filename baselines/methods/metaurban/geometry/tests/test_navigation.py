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

import tempfile
import unittest
from pathlib import Path

import numpy as np
from shapely.geometry import box

from baselines.methods.metaurban.geometry.metrics.geometry import box_mesh
from baselines.methods.metaurban.geometry.metrics.geometry import footprint
from baselines.methods.metaurban.geometry.metrics.geometry import merge_meshes
from baselines.methods.metaurban.geometry.metrics.geometry import obb
from baselines.methods.metaurban.geometry.metrics.geometry import surface_mesh
from baselines.methods.metaurban.geometry.metrics.navigation import build_recast
from baselines.methods.metaurban.geometry.metrics.navigation import connected_components
from baselines.methods.metaurban.geometry.metrics.navigation import triangle_areas


class NavigationTests(unittest.TestCase):
    config = {
        "agent": {
            "height_m": 1.70,
            "radius_m": 0.30,
            "max_climb_m": 0.20,
            "max_slope_deg": 45.0,
        },
        "recast": {"cell_size_m": 0.05, "cell_height_m": 0.05},
    }

    def test_floor_and_obstacle_build(self):
        proxy = obb((3.0, 3.0), (1.0, 1.0, 2.0), 0.0)
        floor = surface_mesh(box(0, 0, 6, 6).difference(footprint(proxy)), z=0.0)[:2]
        obstacle = box_mesh(proxy)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "geometry.npz"
            vertices, faces = merge_meshes((floor, obstacle))
            np.savez_compressed(path, vertices=vertices, faces=faces)
            nav_vertices, nav_faces, metadata = build_recast(path, self.config)
        self.assertTrue(metadata["builder_returned"])
        self.assertGreater(len(nav_faces), 0)
        self.assertGreater(float(triangle_areas(nav_vertices, nav_faces).sum()), 20.0)
        self.assertEqual(len(connected_components(nav_vertices, nav_faces)), 1)

    def test_two_islands_are_not_connected_or_discarded(self):
        surface = surface_mesh(box(0, 0, 3, 3).union(box(6, 0, 8, 2)), z=0.0)[:2]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "two_islands.npz"
            np.savez_compressed(path, vertices=surface[0], faces=surface[1])
            nav_vertices, nav_faces, metadata = build_recast(path, self.config)
        components = connected_components(nav_vertices, nav_faces)
        self.assertTrue(metadata["builder_returned"])
        self.assertEqual(len(components), 2)
        self.assertGreater(components[0]["area_m2"], components[1]["area_m2"])


if __name__ == "__main__":
    unittest.main()

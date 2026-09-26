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
import unittest

import numpy as np
from shapely.geometry import Polygon

from baselines.methods.metaurban.geometry.metrics.geometry import footprint
from baselines.methods.metaurban.geometry.metrics.geometry import obb
from baselines.methods.metaurban.geometry.metrics.geometry import overlap_volume
from baselines.methods.metaurban.geometry.metrics.geometry import sat_overlap
from baselines.methods.metaurban.geometry.metrics.geometry import surface_mesh


class GeometryTests(unittest.TestCase):
    def test_separation_contact_and_penetration(self):
        origin = obb((0.0, 0.0), (2.0, 2.0, 2.0), 0.0)
        separated = obb((2.01, 0.0), (2.0, 2.0, 2.0), 0.0)
        touching = obb((2.0, 0.0), (2.0, 2.0, 2.0), 0.0)
        penetrating = obb((1.98, 0.0), (2.0, 2.0, 2.0), 0.0)
        self.assertFalse(sat_overlap(origin, separated)[0])
        self.assertEqual(sat_overlap(origin, touching), (True, 0.0))
        self.assertAlmostEqual(sat_overlap(origin, penetrating)[1], 0.02, places=7)
        self.assertAlmostEqual(overlap_volume(origin, penetrating), 0.08, places=7)

    def test_rotated_footprint_has_expected_area(self):
        proxy = obb((3.0, -4.0), (2.5, 1.2, 0.8), math.radians(37.0))
        self.assertAlmostEqual(footprint(proxy).area, 3.0, places=7)

    def test_surface_mesh_preserves_concave_polygon_with_hole(self):
        polygon = Polygon(
            [(0, 0), (5, 0), (5, 2), (3, 2), (3, 5), (0, 5)],
            holes=[[(1, 1), (2, 1), (2, 2), (1, 2)]],
        )
        vertices, faces, _ = surface_mesh(polygon)
        triangles = vertices[faces]
        area = (
            0.5
            * np.abs(
                np.cross(
                    triangles[:, 1, :2] - triangles[:, 0, :2],
                    triangles[:, 2, :2] - triangles[:, 0, :2],
                )
            ).sum()
        )
        self.assertAlmostEqual(float(area), polygon.area, places=6)


if __name__ == "__main__":
    unittest.main()

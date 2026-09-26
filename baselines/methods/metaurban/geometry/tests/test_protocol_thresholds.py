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

import unittest

from shapely.geometry import box

from baselines.methods.metaurban.geometry.common import PROTOCOL
from baselines.methods.metaurban.geometry.common import read_json
from baselines.methods.metaurban.geometry.metrics.geometry import footprint
from baselines.methods.metaurban.geometry.metrics.geometry import obb
from baselines.methods.metaurban.geometry.metrics.geometry import sat_overlap


class ProtocolThresholdTests(unittest.TestCase):
    def test_five_and_twenty_millimeter_penetration(self):
        threshold = read_json(PROTOCOL / "collision_exceptions.json")[
            "penetration_depth_m"
        ]
        anchor = obb((0, 0), (2, 2, 2), 0)
        five_mm = obb((1.995, 0), (2, 2, 2), 0)
        twenty_mm = obb((1.980, 0), (2, 2, 2), 0)
        self.assertLess(sat_overlap(anchor, five_mm)[1], threshold)
        self.assertGreater(sat_overlap(anchor, twenty_mm)[1], threshold)

    def test_support_gap_and_embedding_limits(self):
        support = read_json(PROTOCOL / "support_rules.json")
        self.assertFalse(0.01 > support["maximum_gap_m"])
        self.assertTrue(0.03 > support["maximum_gap_m"])
        self.assertFalse(-0.005 < -support["maximum_embedding_m"])
        self.assertTrue(-0.02 < -support["maximum_embedding_m"])

    def test_half_and_two_percent_oob(self):
        container = box(0, 0, 10, 10)
        for outside, expected in ((0.005, False), (0.02, True)):
            proxy = obb((9.5 + outside, 5), (1, 1, 1), 0)
            shape = footprint(proxy)
            fraction = shape.difference(container).area / shape.area
            self.assertAlmostEqual(fraction, outside, places=8)
            self.assertEqual(fraction > 0.01, expected)


if __name__ == "__main__":
    unittest.main()

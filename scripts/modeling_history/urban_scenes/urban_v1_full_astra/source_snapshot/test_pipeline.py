"""Regression tests include deliberately corrupted cities; no Blender needed."""
import copy, json, unittest
import numpy as np
from .plan import build_plan
from .audit import layout_audit
from .validate import flood, route


class PlanningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = build_plan()

    def test_repeatable(self):
        self.assertEqual(self.plan, build_plan())

    def test_complete_city_passes(self):
        result = layout_audit(self.plan)
        self.assertEqual(result["status"], "PASS", result["errors"])
        self.assertEqual(result["rooms"], 1020)
        self.assertGreater(result["frontage"]["length_weighted_ratio"], 0.80)

    def test_collision_is_rejected(self):
        p = copy.deepcopy(self.plan)
        p["buildings"][1]["footprint"] = p["buildings"][0]["footprint"]
        self.assertIn("building_overlaps", layout_audit(p)["errors"])

    def test_missing_upper_floor_is_rejected(self):
        p = copy.deepcopy(self.plan)
        p["rooms"] = [
            r
            for r in p["rooms"]
            if not (r["id"].startswith("building_000_") and r["floor"] == 1)
        ]
        self.assertIn("missing_interior_floors", layout_audit(p)["errors"])

    def test_disconnected_road_is_rejected(self):
        p = copy.deepcopy(self.plan)
        p["road_graph"]["nodes"]["isolated_test"] = [1000, 1000]
        self.assertIn("disconnected_roads", layout_audit(p)["errors"])

    def test_walk_does_not_cross_obstacles(self):
        mask = np.ones((5, 5), bool)
        mask[:, 2] = False
        prev = flood(mask, (1, 1))
        self.assertNotIn((1, 3), prev)
        self.assertIsNone(route(prev, (1, 3), np.arange(5), np.arange(5), 0))
        mask[3, 2] = True
        prev = flood(mask, (1, 1))
        self.assertIn((1, 3), prev)


if __name__ == "__main__":
    unittest.main()

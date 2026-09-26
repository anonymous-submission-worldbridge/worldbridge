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

from baselines.methods.metaurban.geometry.metrics.analyze_collision_sensitivity import (
    collision_sets,
)


CONFIG = {
    "ground_embedding_pair_endpoint": "native_pedestrian_surface",
    "tree_tree_semantics": ["Tree", "Tree"],
    "vegetation_like_semantics": ["Tree", "Vegetation", "Bonsai"],
    "tiers": [
        {"id": "all_collision_primary"},
        {"id": "exclude_ground_embedding"},
        {"id": "exclude_ground_and_tree_tree"},
        {"id": "hard_object_collision"},
    ],
}


def instance(instance_id: str, semantic: str) -> dict:
    return {
        "instance_id": instance_id,
        "semantic": semantic,
        "role": "placed_object",
        "include_collision": True,
    }


class CollisionSensitivityTests(unittest.TestCase):
    def setUp(self):
        self.instances = [
            instance("tree_1", "Tree"),
            instance("tree_2", "Tree"),
            instance("bin", "TrashCan"),
            instance("lamp", "Lamp_post"),
        ]

    def test_cumulative_pair_filters(self):
        structural = {
            "pairs": [
                {"a": "bin", "b": "native_pedestrian_surface", "significant": True},
                {"a": "tree_1", "b": "tree_2", "significant": True},
                {"a": "tree_1", "b": "bin", "significant": True},
                {"a": "bin", "b": "lamp", "significant": True},
            ]
        }
        result = collision_sets(structural, self.instances, CONFIG)
        self.assertEqual(
            result["all_collision_primary"], {"tree_1", "tree_2", "bin", "lamp"}
        )
        self.assertEqual(
            result["exclude_ground_embedding"], {"tree_1", "tree_2", "bin", "lamp"}
        )
        self.assertEqual(
            result["exclude_ground_and_tree_tree"], {"tree_1", "bin", "lamp"}
        )
        self.assertEqual(result["hard_object_collision"], {"bin", "lamp"})

    def test_nonsignificant_pairs_are_ignored(self):
        structural = {"pairs": [{"a": "bin", "b": "lamp", "significant": False}]}
        result = collision_sets(structural, self.instances, CONFIG)
        self.assertTrue(all(not ids for ids in result.values()))


if __name__ == "__main__":
    unittest.main()

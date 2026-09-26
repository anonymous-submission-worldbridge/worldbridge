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

from baselines.methods.metaurban.geometry.metrics.aggregate import METRICS
from baselines.methods.metaurban.geometry.metrics.aggregate import aggregate


class AggregateTests(unittest.TestCase):
    def test_equal_weight_per_spec(self):
        records = []
        for spec_id, value in (("a", 0.0), ("b", 100.0)):
            for seed in range(4):
                records.append(
                    {"spec_id": spec_id, **{metric: value for metric in METRICS}}
                )
        result = aggregate(records, repeats=100, seed=11)
        self.assertEqual(result["spec_count"], 2)
        self.assertEqual(result["run_count"], 8)
        for metric in METRICS:
            self.assertEqual(result["metrics"][metric]["mean"], 50.0)


if __name__ == "__main__":
    unittest.main()

"""Fast regression tests without starting Blender or loading scene libraries."""
import ast
from pathlib import Path
import unittest
import numpy as np

source = Path(__file__).with_name("build_urban_v1_full_13_dynamic2.py").read_text()
tree = ast.parse(source)
functions = [
    n
    for n in tree.body
    if isinstance(n, ast.FunctionDef) and n.name in {"overlap", "swept_collision"}
]
namespace = {"np": np}
exec(
    compile(ast.Module(body=functions, type_ignores=[]), "<dynamics-math>", "exec"),
    namespace,
)
hit = namespace["swept_collision"]


class CollisionTests(unittest.TestCase):
    def setUp(self):
        self.box = np.array([[0.0, 0.0, 0.0], [4.0, 2.0, 2.0]])

    def test_tunnelling_between_frames(self):
        self.assertTrue(
            hit(self.box, [1000, 0, 0], self.box + [10, 0, 0], [0, 0, 0], 0.1)
        )

    def test_same_speed_separated(self):
        self.assertFalse(hit(self.box, [2, 0, 0], self.box + [12, 0, 0], [2, 0, 0], 16))

    def test_opposite_lanes(self):
        self.assertFalse(
            hit(self.box, [2, 0, 0], self.box + [12, 4.5, 0], [-2, 0, 0], 16)
        )

    def test_crossing_conflict(self):
        self.assertTrue(hit(self.box, [2, 0, 0], self.box + [6, -6, 0], [0, 2, 0], 4))

    def test_ground_contact_not_collision(self):
        self.assertFalse(
            hit(
                self.box,
                [2, 0, 0],
                np.array([[-100, -100, -1], [100, 100, 0]]),
                [0, 0, 0],
                16,
            )
        )

    def test_vertical_collision(self):
        self.assertTrue(
            hit(
                self.box,
                [2, 0, 0],
                np.array([[10, 0, -1], [12, 2, 0.2]]),
                [0, 0, 0],
                16,
            )
        )


if __name__ == "__main__":
    unittest.main()

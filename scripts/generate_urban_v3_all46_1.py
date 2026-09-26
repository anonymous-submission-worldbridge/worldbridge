"""Compatibility entry for the superseded all46_1 bank generator.

The production path intentionally resolves to the fully rebuilt all46_4
procedural generator so callers cannot accidentally regenerate the toy scene.
"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))

from generate_urban_v3_all46_2 import (  # noqa: F401
    build_bronze_branch,
    build_classical_corner,
    build_financial_campus,
    build_glass_headquarters,
    build_white_vertical,
    main,
)


if __name__ == "__main__":
    main()

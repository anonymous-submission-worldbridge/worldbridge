"""Synthetic geometry checks for the SceneWeaver Blender exporter."""

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


import sys
from pathlib import Path

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))
from baselines.methods.sceneweaver.geometry.tools import (
    export_sceneweaver_canonical as exporter,
)  # noqa: E402


def cube(name: str, location: tuple[float, float, float]):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    return obj


def proxy(obj):
    vertices, faces, metadata = exporter.proxy_geometry(obj, 20_000)
    tree = BVHTree.FromPolygons(
        [Vector(vertex) for vertex in vertices], faces, all_triangles=True, epsilon=0.0
    )
    return {"vertices": vertices, "faces": faces, **metadata}, tree


def main() -> None:
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    left, left_tree = proxy(cube("left", (0.0, 0.0, 0.5)))
    separate, separate_tree = proxy(cube("separate", (1.02, 0.0, 0.5)))
    shallow, shallow_tree = proxy(cube("shallow", (0.995, 2.0, 0.5)))
    shallow_peer, shallow_peer_tree = proxy(cube("shallow_peer", (0.0, 2.0, 0.5)))
    deep, deep_tree = proxy(cube("deep", (0.98, -2.0, 0.5)))
    deep_peer, deep_peer_tree = proxy(cube("deep_peer", (0.0, -2.0, 0.5)))

    assert not left_tree.overlap(separate_tree)
    assert exporter.aabb_overlap(left, separate)[0] < 0.0
    assert shallow_tree.overlap(shallow_peer_tree)
    assert 0.004 < min(exporter.aabb_overlap(shallow, shallow_peer)) < 0.006
    assert deep_tree.overlap(deep_peer_tree)
    assert 0.019 < min(exporter.aabb_overlap(deep, deep_peer)) < 0.021

    room = [(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]
    inside = [(1.0, 1.0), (2.0, 1.0), (2.0, 2.0), (1.0, 2.0)]
    two_percent_oob = [(3.98, 1.0), (4.98, 1.0), (4.98, 2.0), (3.98, 2.0)]
    assert (
        abs(exporter.polygon_area(exporter.convex_intersection(inside, room)) - 1.0)
        < 1e-8
    )
    assert (
        abs(
            exporter.polygon_area(exporter.convex_intersection(two_percent_oob, room))
            - 0.02
        )
        < 1e-8
    )

    support = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    child_good = [(0.2, 0.2), (0.8, 0.2), (0.8, 0.8), (0.2, 0.8)]
    child_edge = [(0.95, 0.2), (1.55, 0.2), (1.55, 0.8), (0.95, 0.8)]
    good_ratio = exporter.polygon_area(
        exporter.convex_intersection(child_good, support)
    ) / exporter.polygon_area(child_good)
    edge_ratio = exporter.polygon_area(
        exporter.convex_intersection(child_edge, support)
    ) / exporter.polygon_area(child_edge)
    assert good_ratio > 0.99
    assert 0.08 < edge_ratio < 0.09
    assert exporter.point_in_convex((0.5, 0.5), support)
    assert not exporter.point_in_convex((1.2, 0.5), support)
    print("SCENEWEAVER_TABLE3_BLENDER_FIXTURES_OK")


if __name__ == "__main__":
    main()

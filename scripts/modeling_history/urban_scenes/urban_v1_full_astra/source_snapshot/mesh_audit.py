"""Read actual saved mesh geometry; corroborate descriptor-based clearance checks."""
import json, math, sys
from pathlib import Path
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT
from shapely.geometry import Polygon, box


def run():
    plan = json.loads((OUT / "world_manifest.json").read_text())
    geom = json.loads((OUT / "geometry_manifest.json").read_text())
    paths = json.loads((OUT / "navigation_paths.json").read_text())
    errors = []
    checks = []
    source_missing = []
    for rec in json.loads((OUT / "asset_registry.json").read_text())["assets"]:
        if rec.get("source") and not Path(rec["source"]).exists():
            source_missing.append(rec["source"])
    if source_missing:
        errors.append("Missing source files")
    buildings = {b["id"]: b for b in plan["buildings"]}
    base = {b["id"]: b["base_matrix"] for b in geom["buildings"]}
    from mathutils import Matrix

    asset_materials = {}
    for f in geom["furniture"]:
        obj = bpy.data.objects.get(f["id"])
        if obj is None:
            errors.append("Missing furniture mesh " + f["id"])
            continue
        asset_materials[f["asset"]] = [
            m.name if m else None for m in obj.data.materials
        ]
        if not obj.data.materials or any(m is None for m in obj.data.materials):
            errors.append("Furniture missing material " + f["id"])
        bm = Matrix(base[f["building_id"]])
        m = bm.inverted() @ obj.matrix_world
        coords = [m @ Vector(p) for p in obj.bound_box]
        actual = Polygon([(p.x, p.y) for p in coords]).convex_hull
        planned = Polygon(f["footprint_local"])
        if actual.difference(planned.buffer(0.003)).area > 0.002:
            errors.append("Furniture mesh exceeds collision proxy " + f["id"])
        low = min(p.z for p in coords)
        if abs(low - f["local_position"][2]) > 0.01:
            errors.append("Floating/sunken furniture " + f["id"])
    ray_count = 0
    ground_polygons = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.get("astra_role") not in (
            "road",
            "sidewalk",
            "structure",
        ):
            continue
        mesh = obj.data
        mat = obj.matrix_world
        for face in mesh.polygons:
            if face.normal.z < 0.999:
                continue
            if not all(-0.005 <= mesh.vertices[i].co.z <= 0.20 for i in face.vertices):
                continue
            points = [mat @ mesh.vertices[i].co for i in face.vertices]
            poly = Polygon([(p.x, p.y) for p in points])
            if poly.is_valid and poly.area > 1e-8:
                ground_polygons.append(poly)
    from shapely.ops import unary_union

    boundary = Polygon(plan["boundary"])
    ground = unary_union(ground_polygons).intersection(boundary)
    uncovered = boundary.difference(ground).area
    if uncovered / boundary.area > 0.02:
        errors.append("Actual ground mesh coverage below 98%")
    for b in plan["buildings"]:
        bid = b["id"]
        obj = bpy.data.objects.get(bid + "_structure")
        if obj is None:
            errors.append("Missing structure " + bid)
            continue
        mesh = obj.data
        tree = BVHTree.FromPolygons(
            [v.co for v in mesh.vertices],
            [tuple(p.vertices) for p in mesh.polygons],
            all_triangles=False,
        )
        ground_fail = 0
        ceiling_fail = 0
        for p in paths["indoor"]:
            if p["building_id"] != bid:
                continue
            points = p["local"]
            for a, bb in zip(points, points[1:]):
                dist = math.dist(a, bb)
                count = max(1, math.ceil(dist / 0.4))
                for i in range(count + 1):
                    pos = Vector(a).lerp(Vector(bb), i / count)
                    ray_count += 2
                    hit = tree.ray_cast(
                        pos + Vector((0, 0, 0.20)), Vector((0, 0, -1)), 0.4
                    )
                    if hit[0] is None or abs(hit[0].z - pos.z) > 0.025:
                        ground_fail += 1
                    ceiling = tree.ray_cast(
                        pos + Vector((0, 0, 0.05)), Vector((0, 0, 1)), 1.80
                    )
                    if ceiling[0] is not None:
                        ceiling_fail += 1
        if ground_fail:
            errors.append(f"{bid}: {ground_fail} unsupported path samples")
        if ceiling_fail:
            errors.append(f"{bid}: {ceiling_fail} insufficient headroom path samples")
        stair_fail = 0
        stair_samples = 0
        for floor in range(b["floors"] - 1):
            z = 0.16 + 3.2 * floor
            d = b["depth"]
            locations = [
                (-1, d - 4.8 + (i + 0.5) * 0.31, z + (i + 1) * 0.16) for i in range(10)
            ]
            locations += [
                (1, d - 4.8 + (9 - i + 0.5) * 0.31, z + 1.6 + (i + 1) * 0.16)
                for i in range(10)
            ]
            locations += [(x, d - 1, z + 1.6) for x in (-1, 0, 1)]
            for p in locations:
                pos = Vector(p)
                stair_samples += 1
                ray_count += 2
                support = tree.ray_cast(
                    pos + Vector((0, 0, 0.05)), Vector((0, 0, -1)), 0.1
                )
                head = tree.ray_cast(pos + Vector((0, 0, 0.05)), Vector((0, 0, 1)), 1.8)
                if (
                    support[0] is None
                    or abs(support[0].z - pos.z) > 0.015
                    or head[0] is not None
                ):
                    stair_fail += 1
        if stair_fail:
            errors.append(f"{bid}: {stair_fail} stair support/headroom failures")
        checks.append(
            {
                "building_id": bid,
                "structure_vertices": len(mesh.vertices),
                "structure_faces": len(mesh.polygons),
                "ground_failures": ground_fail,
                "headroom_failures": ceiling_fail,
                "stair_samples": stair_samples,
                "stair_support_or_headroom_failures": stair_fail,
            }
        )
        print("MESH_AUDIT", bid, flush=True)
    counts = {}
    for obj in bpy.context.scene.objects:
        role = obj.get("astra_role", obj.type)
        counts[role] = counts.get(role, 0) + 1
    report = {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "source_missing": source_missing,
        "scene_plan_sha256": bpy.context.scene.get("plan_sha256"),
        "role_counts": counts,
        "building_checks": checks,
        "ground_and_headroom_rays": ray_count,
        "furniture_mesh_bounds_checked": len(geom["furniture"]),
        "native_materials_by_asset": asset_materials,
        "actual_city_ground_coverage": {
            "city_area_m2": boundary.area,
            "covered_area_m2": ground.area,
            "uncovered_area_m2": uncovered,
            "coverage_ratio": ground.area / boundary.area,
            "horizontal_surface_polygons": len(ground_polygons),
            "method": "Union of actual upward ground floor, sidewalk and road faces at z 0..0.20 m; soil underlay and outside context excluded",
        },
        "scope": "Actual Blender structure triangles and actual furniture bounding boxes. Offline proxy navigation is checked separately; UE5 physics NOT RUN.",
    }
    (OUT / "mesh_audit.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "building_checks"}, indent=2
        )
    )


if __name__ == "__main__":
    run()

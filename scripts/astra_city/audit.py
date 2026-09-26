"""Independent geometry acceptance, using polygon unions and every street edge."""
from __future__ import annotations
import json
import math
from collections import Counter
from pathlib import Path
import sys

from .plan import OUT, THRESHOLDS, polygons, lines
from shapely.geometry import Polygon, LineString, Point, shape
from shapely.ops import unary_union


def layout_audit(plan):
    errors = []
    boundary = Polygon(plan["boundary"])
    buildings = plan["buildings"]
    by_id = {b["id"]: b for b in buildings}
    footprints = {b["id"]: Polygon(b["footprint"]) for b in buildings}
    road = shape(plan["road_surface"])
    sidewalk = shape(plan["sidewalk_surface"])
    overlaps = []
    for i, a in enumerate(buildings):
        pa = footprints[a["id"]]
        if not boundary.covers(pa):
            errors.append("outside_city:" + a["id"])
        if pa.intersection(road).area > 1e-5:
            errors.append("building_on_road:" + a["id"])
        block = next(b for b in plan["blocks"] if b["id"] == a["block_id"])
        if not Polygon(block["polygon"]).buffer(1e-5).covers(pa):
            errors.append("outside_parcel:" + a["id"])
        for b in buildings[i + 1 :]:
            area = pa.intersection(footprints[b["id"]]).area
            if area > THRESHOLDS["building_overlap_m2"]:
                overlaps.append([a["id"], b["id"], area])
    if overlaps:
        errors.append("building_overlaps")
    block_reports = []
    frontage_reports = []
    for block in plan["blocks"]:
        poly = Polygon(block["polygon"])
        local = [footprints[bid] for bid in block["buildings"]]
        occupied = unary_union(local)
        cov = occupied.area / poly.area
        public = block["use"] == "public_park"
        block_reports.append(
            {
                "id": block["id"],
                "use": block["use"],
                "building_count": len(local),
                "parcel_area_m2": poly.area,
                "building_area_m2": occupied.area,
                "building_coverage": cov,
            }
        )
        if not public and cov < THRESHOLDS["minimum_block_building_coverage"]:
            errors.append("low_coverage:" + block["id"])
        if public:
            continue
        # Every non-park street boundary is sampled, including corners and short segments.
        coords = list(poly.exterior.coords)
        for ei, (a, b) in enumerate(zip(coords, coords[1:])):
            edge = LineString([a, b])
            length = edge.length
            if length < 0.1:
                continue
            nx, ny = -(b[1] - a[1]) / length, (b[0] - a[0]) / length
            n = max(1, math.ceil(length / 0.25))
            hits = 0
            gap = 0
            maxgap = 0
            for i in range(n):
                p = edge.interpolate((i + 0.5) * length / n)
                ray = LineString([(p.x, p.y), (p.x + nx * 3.0, p.y + ny * 3.0)])
                hit = any(ray.intersects(fp) for fp in local)
                if hit:
                    hits += 1
                    gap = 0
                else:
                    gap += length / n
                    maxgap = max(maxgap, gap)
            frontage_reports.append(
                {
                    "id": f"{block['id']}_edge_{ei}",
                    "length_m": length,
                    "covered_length_m": hits * length / n,
                    "ratio": hits / n,
                    "maximum_gap_m": maxgap,
                    "samples": n,
                }
            )
    total_length = sum(r["length_m"] for r in frontage_reports)
    covered = sum(r["covered_length_m"] for r in frontage_reports)
    ratio = covered / total_length
    if ratio < THRESHOLDS["minimum_street_frontage"]:
        errors.append("low_city_frontage")
    nodes = plan["road_graph"]["nodes"]
    adj = {n: set() for n in nodes}
    for edge in plan["road_graph"]["edges"]:
        adj[edge["from"]].add(edge["to"])
        adj[edge["to"]].add(edge["from"])
    visited = set()
    queue = [next(iter(nodes))] if nodes else []
    while queue:
        node = queue.pop()
        if node in visited:
            continue
        visited.add(node)
        queue.extend(adj[node] - visited)
    connected = bool(nodes) and len(visited) == len(nodes)
    if not connected:
        errors.append("disconnected_roads")
    room_counts = Counter((r["id"].split("_f")[0], r["floor"]) for r in plan["rooms"])
    missing = []
    for b in buildings:
        for floor in range(b["floors"]):
            if room_counts[(b["id"], floor)] < THRESHOLDS["minimum_rooms_per_floor"]:
                missing.append([b["id"], floor])
    if missing:
        errors.append("missing_interior_floors")
    if len(buildings) < THRESHOLDS["minimum_buildings"]:
        errors.append("too_few_buildings")
    built = unary_union(list(footprints.values()))
    blocks_union = unary_union([Polygon(b["polygon"]) for b in plan["blocks"]])
    park = unary_union(
        [Polygon(b["polygon"]) for b in plan["blocks"] if b["use"] == "public_park"]
    )
    outer_paving = boundary.difference(road.union(sidewalk).union(blocks_union))
    land_use = {
        "building_footprints": built.area,
        "roads": road.area,
        "sidewalks": sidewalk.difference(road).area,
        "public_park": park.area,
        "courtyards_and_passages": blocks_union.difference(built.union(park)).area,
        "outer_paved_verge": outer_paving.area,
    }
    ground_covered = (
        road.union(sidewalk)
        .union(blocks_union)
        .union(outer_paving)
        .intersection(boundary)
    )
    unexplained = boundary.difference(ground_covered).area
    if unexplained / boundary.area > THRESHOLDS["maximum_unexplained_area_ratio"]:
        errors.append("unexplained_city_ground")
    report = {
        "schema": "agent.astra.layout_audit.v1",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "plan_sha256": plan["plan_sha256"],
        "thresholds": THRESHOLDS,
        "city_area_m2": boundary.area,
        "buildings": len(buildings),
        "floors": sum(b["floors"] for b in buildings),
        "city_ground_coverage": {
            "land_use_m2": land_use,
            "building_coverage_of_city": built.area / boundary.area,
            "unexplained_area_m2": unexplained,
            "declared_ground_coverage_ratio": ground_covered.area / boundary.area,
            "note": "Context terrain outside the fixed city boundary is excluded. Actual rendered ground mesh coverage is checked in mesh_audit.json.",
        },
        "rooms": len(plan["rooms"]),
        "category_counts": dict(Counter(b["use"] for b in buildings)),
        "blocks": block_reports,
        "frontage": {
            "method": "all non-park block edges, 0.25 m perpendicular rays, 3 m setback",
            "total_length_m": total_length,
            "covered_length_m": covered,
            "length_weighted_ratio": ratio,
            "segments": frontage_reports,
        },
        "overlaps": overlaps,
        "missing_floors": missing,
        "road_graph": {
            "nodes": len(nodes),
            "edges": len(plan["road_graph"]["edges"]),
            "connected": connected,
            "road_surface_components": len(polygons(road)),
        },
        "validation_scope": "planning geometry; physical mesh, render and UE runtime checks are separate",
    }
    return report


def save_plan_view(plan, report):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Polygon as Patch

    colors = {
        "residential": "#c09876",
        "retail": "#c57853",
        "cafe": "#dcaa5c",
        "office": "#8eabb5",
        "pharmacy": "#9db39b",
        "library": "#ab97ad",
        "clinic": "#ccd2c2",
    }
    fig, ax = plt.subplots(figsize=(14, 12), facecolor="#faf7ef")
    ax.set_facecolor("#faf7ef")
    ax.add_patch(
        Patch(plan["boundary"], facecolor="#dad6ca", edgecolor="#726b60", lw=1.5)
    )
    for p in polygons(shape(plan["road_surface"])):
        ax.add_patch(Patch(p.exterior.coords, facecolor="#50595d", edgecolor="none"))
        for hole in p.interiors:
            ax.add_patch(Patch(hole.coords, facecolor="#dad6ca", edgecolor="none"))
    for b in plan["blocks"]:
        ax.add_patch(
            Patch(
                b["polygon"],
                facecolor="#8fbc83" if b["use"] == "public_park" else "#e5dfcc",
                edgecolor="#938e81",
                lw=0.5,
            )
        )
    for b in plan["buildings"]:
        ax.add_patch(
            Patch(
                b["footprint"], facecolor=colors[b["use"]], edgecolor="#645546", lw=0.5
            )
        )
        cx, cy = Polygon(b["footprint"]).centroid.coords[0]
        ax.text(
            cx,
            cy,
            b["id"].replace("building_", "") + f" / {b['floors']}F",
            ha="center",
            va="center",
            fontsize=5.6,
        )
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.set_xlabel("meters")
    ax.set_ylabel("meters")
    ax.set_title(
        f"ASTRA CITY | {len(plan['buildings'])} buildings | all floors modelled\n"
        f"Irregular continuous street blocks / frontage {report['frontage']['length_weighted_ratio']:.1%}",
        fontsize=16,
        pad=14,
    )
    fig.tight_layout()
    fig.savefig(OUT / "layout_plan.png", dpi=160)
    plt.close(fig)


if __name__ == "__main__":
    plan = json.loads((OUT / "world_manifest.json").read_text())
    report = layout_audit(plan)
    (OUT / "layout_audit.json").write_text(json.dumps(report, indent=2))
    save_plan_view(plan, report)
    print(
        json.dumps(
            {k: report[k] for k in ["status", "errors", "buildings", "floors", "rooms"]}
        )
    )
    print("frontage", report["frontage"]["length_weighted_ratio"])
    print(
        "block_coverage",
        [(b["id"], round(b["building_coverage"], 3)) for b in report["blocks"]],
    )

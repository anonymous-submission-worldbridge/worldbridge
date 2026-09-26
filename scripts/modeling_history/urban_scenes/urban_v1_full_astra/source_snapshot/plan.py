"""Deterministic polygonal city planning; no Blender or language model required.

Run through generate_urban_v1_full_astra.py. Geometry, not an LLM assertion,
determines parcel ownership, frontage, density and road connectivity.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_astra"
sys.path.insert(0, str(OUT / "runtime/python"))

from shapely.geometry import LineString, Point, Polygon, mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

SEED = 60905
AGENT = {
    "radius_m": 0.32,
    "height_m": 1.8,
    "step_height_m": 0.22,
    "max_slope_degrees": 35,
    "clearance_margin_m": 0.12,
}
THRESHOLDS = {
    "building_overlap_m2": 0.0001,
    "minimum_block_building_coverage": 0.50,
    "minimum_street_frontage": 0.80,
    "maximum_unexplained_area_ratio": 0.02,
    "minimum_buildings": 60,
    "minimum_rooms_per_floor": 4,
}


def polygons(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type == "Polygon":
        return [geometry]
    return [p for g in geometry.geoms for p in polygons(g)]


def lines(geometry):
    if geometry.is_empty:
        return []
    if geometry.geom_type in ("LineString", "LinearRing"):
        return [geometry]
    return [p for g in geometry.geoms for p in lines(g)]


def ring(poly):
    return [
        [round(x, 6), round(y, 6)] for x, y in orient(poly, sign=1).exterior.coords[:-1]
    ]


def world_point(building, x, y, z=0):
    a = math.radians(building["yaw_deg"])
    ox, oy = building["origin"]
    return [
        ox + math.cos(a) * x - math.sin(a) * y,
        oy + math.sin(a) * x + math.cos(a) * y,
        z,
    ]


def footprint(origin, angle, width, depth):
    c, s = math.cos(angle), math.sin(angle)
    return Polygon(
        [
            (origin[0] + c * x - s * y, origin[1] + s * x + c * y)
            for x, y in [
                (-width / 2, 0),
                (width / 2, 0),
                (width / 2, depth),
                (-width / 2, depth),
            ]
        ]
    )


def intervals_union(intervals):
    result = []
    for lo, hi in sorted(intervals):
        if result and lo <= result[-1][1] + 1e-6:
            result[-1][1] = max(hi, result[-1][1])
        else:
            result.append([lo, hi])
    return result


def floor_program(building):
    """Four occupied rooms, a through hall and an actual switchback stair per floor."""
    w, d = building["width"], building["depth"]
    mid = (d - 6.0) / 2
    corridor = 1.15
    rooms = []
    portals = []
    for floor in range(building["floors"]):
        fz = 0.16 + 3.2 * floor
        use = building["use"]
        if floor == 0 and use in {
            "retail",
            "cafe",
            "pharmacy",
            "library",
            "clinic",
            "office",
        }:
            kinds = {
                "retail": ["shop", "shop", "office", "bathroom"],
                "cafe": ["dining", "dining", "kitchen", "bathroom"],
                "pharmacy": ["shop", "shop", "office", "bathroom"],
                "library": ["library", "library", "office", "bathroom"],
                "clinic": ["office", "office", "bedroom", "bathroom"],
                "office": ["office", "office", "dining", "bathroom"],
            }[use]
        else:
            kinds = ["living", "bedroom", "kitchen", "bathroom"]
        for j, (side, start, end) in enumerate(
            [
                (-1, 0.28, mid - 0.05),
                (1, 0.28, mid - 0.05),
                (-1, mid + 0.19, d - 6.12),
                (1, mid + 0.19, d - 6.12),
            ]
        ):
            x0, x1 = (
                (-w / 2 + 0.28, -corridor - 0.18)
                if side < 0
                else (corridor + 0.18, w / 2 - 0.28)
            )
            cy = (start + end) / 2
            rid = f'{building["id"]}_f{floor}_r{j}'
            rooms.append(
                {
                    "id": rid,
                    "floor": floor,
                    "kind": kinds[j],
                    "local_bounds": [x0, start, x1, end],
                    "floor_z": fz,
                    "target_local": [(x0 + x1) / 2, cy, fz],
                    "floor_area_m2": (x1 - x0) * (end - start),
                }
            )
            portals.append(
                {
                    "id": f"{rid}_door",
                    "building_id": building["id"],
                    "floor": floor,
                    "kind": "room_door",
                    "local": [side * (corridor + 0.06), cy, fz],
                    "yaw_local_deg": 90,
                    "width_m": 1.1,
                    "height_m": 2.35,
                    "connects": [f'{building["id"]}_hall_{floor}', rid],
                    "default_state": "open",
                    "open_angle_deg": -side * 95,
                }
            )
        if floor == 0:
            portals.append(
                {
                    "id": f'{building["id"]}_entrance',
                    "building_id": building["id"],
                    "floor": 0,
                    "kind": "exterior_door",
                    "local": [0, 0, fz],
                    "yaw_local_deg": 0,
                    "width_m": 1.5,
                    "height_m": 2.55,
                    "connects": ["street", f'{building["id"]}_hall_0'],
                    "default_state": "open",
                    "open_angle_deg": -100,
                }
            )
    return rooms, portals


def build_plan():
    rng = random.Random(SEED)
    boundary = Polygon(
        [(-143, -105), (102, -119), (141, -78), (137, 92), (67, 124), (-131, 106)]
    )
    perimeter = boundary.buffer(-6, join_style=2)
    specs = [
        ("perimeter", list(perimeter.exterior.coords), 7.2),
        ("market_avenue", [(-165, -35), (0, -29), (160, -37)], 9.0),
        ("garden_street", [(-160, 40), (-30, 48), (160, 37)], 7.2),
        ("west_street", [(-58, -140), (-43, -28), (-53, 150)], 7.2),
        ("east_street", [(48, -145), (40, -31), (60, 155)], 7.2),
    ]
    centerlines = []
    roads = []
    for name, coords, width in specs:
        clipped = LineString(coords).intersection(perimeter)
        if name == "perimeter":
            clipped = LineString(perimeter.exterior.coords)
        for n, line in enumerate(lines(clipped)):
            centerlines.append(line)
            roads.append(
                {
                    "id": f"{name}_{n}",
                    "width": width,
                    "centerline": list(map(list, line.coords)),
                }
            )
    road_surface = unary_union(
        [
            LineString(r["centerline"]).buffer(
                r["width"] / 2, cap_style=2, join_style=2
            )
            for r in roads
        ]
    ).intersection(boundary)
    reserve = unary_union(
        [
            LineString(r["centerline"]).buffer(
                r["width"] / 2 + 3.2, cap_style=2, join_style=2
            )
            for r in roads
        ]
    )
    raw_blocks = sorted(
        polygons(perimeter.difference(reserve)),
        key=lambda p: (round(p.centroid.y / 35), p.centroid.x),
    )
    blocks, buildings, all_rooms, all_portals = [], [], [], []
    footprints = []
    for bi, raw in enumerate(raw_blocks):
        if raw.area < 180:
            continue
        poly = orient(raw.simplify(0.08, preserve_topology=True), sign=1)
        block_id = f"block_{bi:02d}"
        # One publicly accessible park is a declared land use fixed before any metric is measured.
        park = bi == len(raw_blocks) - 1
        block = {
            "id": block_id,
            "polygon": ring(poly),
            "area_m2": poly.area,
            "use": "public_park" if park else "mixed_use",
            "buildings": [],
            "frontages": [],
        }
        if park:
            blocks.append(block)
            continue
        occupied = []
        verts = list(poly.exterior.coords)
        edges = [
            (Point(a).distance(Point(b)), ei, a, b)
            for ei, (a, b) in enumerate(zip(verts, verts[1:]))
        ]
        for length, ei, a, b in sorted(edges, reverse=True):
            if length < 12:
                continue
            angle = math.atan2(b[1] - a[1], b[0] - a[0])
            t = (math.cos(angle), math.sin(angle))
            inward = (-t[1], t[0])
            frontage = {
                "id": f"{block_id}_edge_{ei}",
                "start": list(a),
                "end": list(b),
                "length_m": length,
                "building_ids": [],
            }
            # Search along each street edge. Rejection leaves an explicit gap, never a suppressed edge.
            cursor = 0.65
            while cursor < length - 10.0:
                chosen = None
                for width in (19.0, 17.0, 15.0, 13.0, 11.0):
                    if cursor + width > length - 0.55:
                        continue
                    origin = (
                        a[0] + t[0] * (cursor + width / 2) + inward[0] * 0.45,
                        a[1] + t[1] * (cursor + width / 2) + inward[1] * 0.45,
                    )
                    for depth in (21.0, 19.0, 17.0, 15.0, 13.0):
                        fp = footprint(origin, angle, width, depth)
                        if poly.buffer(0.00001).covers(fp) and not any(
                            fp.buffer(0.17, join_style=2).intersects(o)
                            for o in occupied
                        ):
                            chosen = (origin, width, depth, fp)
                            break
                    if chosen:
                        break
                if chosen is None:
                    cursor += 0.55
                    continue
                origin, width, depth, fp = chosen
                bid = f"building_{len(buildings):03d}"
                use = rng.choices(
                    [
                        "residential",
                        "retail",
                        "cafe",
                        "office",
                        "pharmacy",
                        "library",
                        "clinic",
                    ],
                    [48, 19, 10, 12, 4, 3, 4],
                )[0]
                floors = rng.choice([2, 3, 3, 4, 4, 5])
                building = {
                    "id": bid,
                    "block_id": block_id,
                    "use": use,
                    "origin": list(origin),
                    "yaw_deg": math.degrees(angle),
                    "width": width,
                    "depth": depth,
                    "floors": floors,
                    "floor_height_m": 3.2,
                    "style": rng.randrange(6),
                    "seed": rng.randrange(1000000),
                    "footprint": ring(fp),
                    "area_m2": fp.area,
                    "frontage_id": frontage["id"],
                    "frontage_interval": [cursor, cursor + width],
                    "interior_scope": "all_floors",
                }
                rooms, portals = floor_program(building)
                building["room_ids"] = [r["id"] for r in rooms]
                building["portal_ids"] = [p["id"] for p in portals]
                all_rooms.extend(rooms)
                all_portals.extend(portals)
                buildings.append(building)
                footprints.append(fp)
                occupied.append(fp)
                block["buildings"].append(bid)
                frontage["building_ids"].append(bid)
                cursor += width + 0.4
            block["frontages"].append(frontage)
        block["courtyards"] = [
            mapping(p) for p in polygons(poly.difference(unary_union(occupied)))
        ]
        blocks.append(block)
    noded = unary_union(centerlines)
    edges = []
    nodes = {}
    for line in lines(noded):
        coords = list(line.coords)
        for a, b in zip(coords, coords[1:]):
            keys = [f"{p[0]:.4f},{p[1]:.4f}" for p in (a, b)]
            for key, p in zip(keys, (a, b)):
                nodes[key] = list(p)
            edges.append(
                {
                    "from": keys[0],
                    "to": keys[1],
                    "length_m": Point(a).distance(Point(b)),
                }
            )
    plan = {
        "schema": "agent.astra.city.v1",
        "revision": "urban_v1_full_astra",
        "seed": SEED,
        "units": "meters",
        "coordinates": "right_handed_z_up",
        "agent": AGENT,
        "thresholds": THRESHOLDS,
        "boundary": ring(boundary),
        "city_area_m2": boundary.area,
        "roads": roads,
        "road_surface": mapping(road_surface),
        "sidewalk_surface": mapping(
            reserve.intersection(boundary).difference(road_surface)
        ),
        "blocks": blocks,
        "buildings": buildings,
        "rooms": all_rooms,
        "portals": all_portals,
        "road_graph": {"nodes": nodes, "edges": edges},
        "land_use_policy": "All residual block space is designed as paved accessible courtyards; one preselected park.",
        "production_entrypoint": "scripts/generate_urban_v1_full_astra.py",
    }
    plan["plan_sha256"] = hashlib.sha256(
        json.dumps(plan, sort_keys=True).encode()
    ).hexdigest()
    return plan


def save_plan(plan):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "world_manifest.json").write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf8"
    )


if __name__ == "__main__":
    result = build_plan()
    save_plan(result)
    print(
        json.dumps(
            {
                "blocks": len(result["blocks"]),
                "buildings": len(result["buildings"]),
                "rooms": len(result["rooms"]),
                "area": result["city_area_m2"],
            }
        )
    )

"""Independent geometric acceptance, using measured mesh bounds and capsule-clearance grids.

Run with the project's Python for planning checks, or Blender for mesh evidence.
This is intentionally NOT labelled an Unreal physics/navmesh acceptance test.
"""
from collections import Counter, deque
import json, math, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT, world_point
import numpy as np
from shapely.geometry import Polygon, Point, LineString, box, shape
from shapely.affinity import rotate, translate
from shapely.ops import unary_union
from shapely import contains_xy


def footprint(c):
    dx, dy, _ = c["dimensions"]
    x, y, _ = c["center"]
    return translate(
        rotate(
            box(-dx / 2, -dy / 2, dx / 2, dy / 2),
            c.get("yaw", 0),
            origin=(0, 0),
            use_radians=True,
        ),
        x,
        y,
    )


def flood(mask, start):
    h, w = mask.shape
    if not (0 <= start[0] < h and 0 <= start[1] < w and mask[start]):
        return {}
    prev = {start: None}
    queue = deque([start])
    while queue:
        y, x = queue.popleft()
        for q in ((y - 1, x), (y + 1, x), (y, x - 1), (y, x + 1)):
            if 0 <= q[0] < h and 0 <= q[1] < w and mask[q] and q not in prev:
                prev[q] = (y, x)
                queue.append(q)
    return prev


def route(prev, target, xs, ys, z):
    if target not in prev:
        return None
    cells = []
    q = target
    while q is not None:
        cells.append(q)
        q = prev[q]
    cells.reverse()
    # Keep corners, rather than silently cutting across buffered obstacles.
    keep = [cells[0]]
    for i in range(1, len(cells) - 1):
        a, b, c = cells[i - 1 : i + 2]
        if (b[0] - a[0], b[1] - a[1]) != (c[0] - b[0], c[1] - b[1]):
            keep.append(b)
    keep.append(cells[-1])
    return [[round(float(xs[x]), 4), round(float(ys[y]), 4), z] for y, x in keep]


def run():
    plan = json.loads((OUT / "world_manifest.json").read_text())
    geom = json.loads((OUT / "geometry_manifest.json").read_text())
    errors = []
    warnings = []
    paths = []
    building_checks = []
    clearance = plan["agent"]["radius_m"] + plan["agent"]["clearance_margin_m"]
    furniture_by_room = {}
    for f in geom["furniture"]:
        furniture_by_room.setdefault(f["room_id"], []).append(f)
    if plan["plan_sha256"] != geom["plan_sha256"]:
        errors.append("Plan/mesh revision mismatch")
    for b in plan["buildings"]:
        bid = b["id"]
        w, d = b["width"], b["depth"]
        cols = geom["colliders"][bid]
        floor_checks = []
        xs = np.arange(-w / 2 + 0.05, w / 2, 0.1)
        ys = np.arange(0.05, d - 4.8, 0.1)
        xx, yy = np.meshgrid(xs, ys)

        def cell(p):
            return (int(np.argmin(abs(ys - p[1]))), int(np.argmin(abs(xs - p[0]))))

        for floor in range(b["floors"]):
            z = 0.16 + floor * 3.2
            obstacles = [
                footprint(c)
                for c in cols
                if c["center"][2] + c["dimensions"][2] / 2 > z + 0.23
                and c["center"][2] - c["dimensions"][2] / 2 < z + 1.80
            ]
            solid = unary_union(obstacles).buffer(clearance, join_style=2)
            region = box(-w / 2, 0, w / 2, d - 4.8).buffer(-clearance)
            free = region.difference(solid)
            prev = flood(contains_xy(free, xx, yy), cell((0, 0.8)))
            rooms = [
                r
                for r in geom["rooms"]
                if r["building_id"] == bid and r["floor"] == floor
            ]
            reached = 0
            for r in rooms:
                rp = route(prev, cell(r["target_local"]), xs, ys, z)
                if rp is None:
                    errors.append("Unreachable room " + r["id"])
                else:
                    reached += 1
                    paths.append(
                        {
                            "room_id": r["id"],
                            "building_id": bid,
                            "floor": floor,
                            "local": rp,
                        }
                    )
                fs = furniture_by_room.get(r["id"], [])
                if not fs:
                    errors.append("Unfurnished room " + r["id"])
                for i, f in enumerate(fs):
                    if (
                        not box(*r["bounds"])
                        .buffer(0.001)
                        .covers(Polygon(f["footprint_local"]))
                    ):
                        errors.append("Furniture outside room " + f["id"])
                    if not 0.65 <= f["scale"] <= 1.001:
                        errors.append("Unrealistic uniform scale " + f["id"])
                    for other in fs[i + 1 :]:
                        if (
                            Polygon(f["footprint_local"])
                            .intersection(Polygon(other["footprint_local"]))
                            .area
                            > 1e-4
                        ):
                            errors.append(
                                "Furniture overlap " + f["id"] + " / " + other["id"]
                            )
            # Each flight must be reachable from the same floor as all rooms.
            stair_reached = cell((-1, d - 5.35)) in prev and cell((1, d - 5.35)) in prev
            if not stair_reached:
                errors.append(f"Stair approach disconnected {bid} floor {floor}")
            floor_checks.append(
                {
                    "floor": floor,
                    "rooms_reached": reached,
                    "rooms_expected": len(rooms),
                    "stair_approaches_connected": stair_reached,
                }
            )
        steps = [c for c in cols if c["name"] in ("stair_up", "stair_return")]
        expected = 20 * (b["floors"] - 1)
        if len(steps) != expected:
            errors.append("Incomplete staircase " + bid)
        building_checks.append(
            {
                "id": bid,
                "floors": floor_checks,
                "stair_treads": len(steps),
                "expected_treads": expected,
            }
        )
        print("NAV_CHECK", bid, flush=True)
    # Global walkability: real public ground, explicit crossings and obstacles.
    boundary = Polygon(plan["boundary"])
    occupied = unary_union([Polygon(b["footprint"]) for b in plan["buildings"]])
    crossings = []
    for c in geom["crosswalks"]:
        crossings.append(
            translate(
                rotate(
                    box(-1.3, -6, 1.3, 6),
                    c["road_yaw"],
                    origin=(0, 0),
                    use_radians=True,
                ),
                *c["center"],
            )
        )
    outdoor = boundary.difference(shape(plan["road_surface"])).union(
        unary_union(crossings).intersection(boundary)
    )
    props = unary_union([footprint(c) for c in geom.get("outdoor_colliders", [])])
    outdoor = outdoor.difference(occupied.union(props)).buffer(-clearance)
    x0, y0, x1, y1 = boundary.bounds
    xs = np.arange(x0, x1, 0.25)
    ys = np.arange(y0, y1, 0.25)
    xx, yy = np.meshgrid(xs, ys)

    def cell(p):
        return int(np.argmin(abs(ys - p[1]))), int(np.argmin(abs(xs - p[0])))

    mask = contains_xy(outdoor, xx, yy)
    entrances = [(b, world_point(b, 0, -1.25, 0.16)) for b in plan["buildings"]]
    prev = flood(mask, cell(entrances[0][1]))
    entrance_checks = []
    for b, p in entrances:
        ok = cell(p) in prev
        entrance_checks.append({"id": b["id"], "connected": ok})
        if not ok:
            errors.append("Public entrance disconnected " + b["id"])
    courtyard_checks = []
    from astra_city.plan import polygons

    for block in plan["blocks"]:
        if block["use"] == "public_park":
            areas = polygons(
                Polygon(block["polygon"]).difference(props).buffer(-clearance)
            )
        else:
            areas = polygons(
                Polygon(block["polygon"])
                .difference(occupied.union(props))
                .buffer(-clearance)
            )
        for i, area in enumerate(areas):
            if area.area < 20:
                continue
            p = area.representative_point()
            ok = cell((p.x, p.y)) in prev
            courtyard_checks.append(
                {"block": block["id"], "part": i, "area_m2": area.area, "connected": ok}
            )
            if not ok:
                errors.append(f'Courtyard/park disconnected {block["id"]} part {i}')
    street_path = route(prev, cell(entrances[-1][1]), xs, ys, 0.16)
    report = {
        "status": "PASS" if not errors else "FAIL",
        "method": "0.10 m indoor / 0.25 m outdoor grids; conservative measured furniture bounds; 0.44 m capsule radius including margin",
        "scope": "Offline geometric clearance only. Unreal CharacterMovement, cooked collision, lighting and performance NOT TESTED.",
        "errors": errors,
        "warnings": warnings,
        "rooms": len(geom["rooms"]),
        "room_paths_found": len(paths),
        "buildings": building_checks,
        "entrances": entrance_checks,
        "courtyards_and_park": courtyard_checks,
        "furniture_count": len(geom["furniture"]),
        "furniture_by_asset": dict(Counter(f["asset"] for f in geom["furniture"])),
        "minimum_furniture_scale": min(f["scale"] for f in geom["furniture"]),
        "stairs": {
            "rise_m": 0.16,
            "going_m": 0.31,
            "flight_width_m": 1.5,
            "headroom_m_nominal": 2.98,
        },
        "ue_runtime_status": "NOT_RUN",
    }
    (OUT / "navigation_paths.json").write_text(
        json.dumps({"indoor": paths, "street": street_path}, indent=2)
    )
    (OUT / "geometry_audit.json").write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {k: v for k, v in report.items() if k not in ("buildings", "entrances")},
            indent=2,
        )
    )
    return report


if __name__ == "__main__":
    run()

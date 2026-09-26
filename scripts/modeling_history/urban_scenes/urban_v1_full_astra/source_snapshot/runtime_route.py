"""Create a continuous, no-teleport UE runtime smoke-test through one complete building.

All 1020 rooms are checked offline; this runtime route separately traverses one
building's every room, every floor and both directions of each stair flight.
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT, world_point


def run():
    plan = json.loads((OUT / "world_manifest.json").read_text())
    paths = json.loads((OUT / "navigation_paths.json").read_text())
    b = plan["buildings"][0]
    bid = b["id"]
    d = b["depth"]
    points = []

    def add(p):
        w = world_point(b, *p)
        ue = [round(w[0] * 100, 3), round(-w[1] * 100, 3), round(w[2] * 100, 3)]
        if not points or points[-1] != ue:
            points.append(ue)

    add((0, -1.5, 0.16))
    add((0, 0.8, 0.16))
    ascent = []
    for floor in range(b["floors"]):
        z = 0.16 + floor * 3.2
        for path in paths["indoor"]:
            if path["building_id"] == bid and path["floor"] == floor:
                for p in path["local"]:
                    add(p)
                for p in reversed(path["local"]):
                    add(p)
        if floor == b["floors"] - 1:
            break
        flight = [(0, 0.8, z), (0, d - 5.35, z), (-1, d - 5.35, z)]
        flight.extend(
            (-1, d - 4.8 + (i + 0.5) * 0.31, z + (i + 1) * 0.16) for i in range(10)
        )
        flight.extend([(-1, d - 1.0, z + 1.6), (1, d - 1.0, z + 1.6)])
        flight.extend(
            (1, d - 4.8 + (9 - i + 0.5) * 0.31, z + 1.6 + (i + 1) * 0.16)
            for i in range(10)
        )
        flight.extend(
            [(1, d - 5.35, z + 3.2), (0, d - 5.35, z + 3.2), (0, 0.8, z + 3.2)]
        )
        ascent.append(flight)
        for p in flight:
            add(p)
    for flight in reversed(ascent):
        for p in reversed(flight):
            add(p)
    add((0, -1.5, 0.16))
    # Continue along the tested outdoor pedestrian network to a distant block.
    street = paths.get("street") or []
    for p in street:
        ue = [round(p[0] * 100, 3), round(-p[1] * 100, 3), round(p[2] * 100, 3)]
        if not points or points[-1] != ue:
            points.append(ue)
    result = {
        "scope": f'Continuous smoke route: {bid}, all {b["floors"]} floors/{b["floors"]*4} rooms, stairs up/down, then cross-city pedestrian route. Not a runtime test of all 1020 rooms.',
        "plan_sha256": plan["plan_sha256"],
        "status": "GENERATED_NOT_RUN",
        "points_cm": points,
    }
    out = OUT / "ue5/AstraCity/Content"
    out.mkdir(exist_ok=True)
    (out / "AuditRoute.json").write_text(json.dumps(result, indent=2))
    print("RUNTIME_ROUTE", len(points), "waypoints")


if __name__ == "__main__":
    run()

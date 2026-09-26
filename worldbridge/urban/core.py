"""Constrained urban planning and regional parameter sampling.

This module is Blender-independent by design: a future scene integrator samples
and validates a descriptor first, then passes each parcel descriptor to the
existing high-quality regional generators.  No generated mesh is patched.
"""
from __future__ import annotations

import hashlib
import json
import random
from dataclasses import asdict, dataclass
from typing import Any

ZONES = ("commercial", "residential", "park", "leisure")
TOPOLOGIES = ("four_way", "t_junction", "main_side", "offset", "irregular")


@dataclass(frozen=True)
class Parcel:
    id: str
    center: tuple[float, float]
    size: tuple[float, float]
    orientation_deg: float
    road_edges: tuple[str, ...]
    major_road_distance: float
    pedestrian_access: bool = True
    quiet_score: float = 0.5


def _rng(seed: int, namespace: str) -> random.Random:
    digest = hashlib.sha256(f"{seed}:{namespace}".encode()).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _weighted_permutation(
    items: list[str], weights: dict[str, float], rng: random.Random
) -> list[str]:
    remaining = list(items)
    result = []
    while remaining:
        vals = [max(1e-6, weights[x]) for x in remaining]
        pick = rng.choices(remaining, weights=vals, k=1)[0]
        result.append(pick)
        remaining.remove(pick)
    return result


def _roads_and_parcels(
    topology: str, rng: random.Random
) -> tuple[list[dict[str, Any]], list[Parcel]]:
    # Dimensions vary continuously; topology families only define connectivity.
    half = rng.uniform(43, 57)
    road = rng.uniform(7.0, 10.0)
    skew = rng.uniform(-7, 7)
    off = rng.uniform(7, 15)
    roads: list[dict[str, Any]] = []
    boxes: list[tuple[float, float, float, float, tuple[str, ...], float]] = []
    if topology == "four_way":
        roads = [
            {"axis": "x", "offset": 0, "width": road, "class": "major"},
            {"axis": "y", "offset": 0, "width": road * 0.82, "class": "major"},
        ]
        boxes = [
            (-half, -road / 2, road / 2, half, ("east", "south"), 0.1),
            (road / 2, half, road / 2, half, ("west", "south"), 0.1),
            (-half, -road / 2, -half, -road / 2, ("east", "north"), 0.1),
            (road / 2, half, -half, -road / 2, ("west", "north"), 0.1),
        ]
    elif topology == "t_junction":
        roads = [
            {"axis": "x", "offset": 0, "width": road, "class": "major"},
            {
                "axis": "y",
                "offset": skew,
                "width": road * 0.72,
                "class": "local",
                "range": [0, half],
            },
        ]
        boxes = [
            (-half, skew - road * 0.36, road / 2, half, ("south", "east"), 0.2),
            (skew + road * 0.36, half, road / 2, half, ("south", "west"), 0.2),
            (-half, -8, -half, -road / 2, ("north",), 0.3),
            (-6, half, -half, -road / 2, ("north",), 0.15),
        ]
    elif topology == "main_side":
        roads = [
            {"axis": "y", "offset": 0, "width": road, "class": "major"},
            {
                "axis": "x",
                "offset": off,
                "width": road * 0.62,
                "class": "local",
                "range": [-half, 0],
            },
        ]
        boxes = [
            (-half, -road / 2, off + road * 0.31, half, ("east", "south"), 0.15),
            (road / 2, half, off + road * 0.31, half, ("west", "south"), 0.15),
            (-half, -road / 2, -half, off - road * 0.31, ("east", "north"), 0.35),
            (road / 2, half, -half, off - road * 0.31, ("west", "north"), 0.35),
        ]
    elif topology == "offset":
        roads = [
            {"axis": "x", "offset": 0, "width": road, "class": "major"},
            {
                "axis": "y",
                "offset": -off / 2,
                "width": road * 0.68,
                "class": "local",
                "range": [-half, 0],
            },
            {
                "axis": "y",
                "offset": off / 2,
                "width": road * 0.68,
                "class": "local",
                "range": [0, half],
            },
        ]
        boxes = [
            (-half, -off / 2 - road * 0.34, road / 2, half, ("east", "south"), 0.2),
            (-off / 2 + road * 0.34, half, road / 2, half, ("west", "south"), 0.2),
            (-half, off / 2 - road * 0.34, -half, -road / 2, ("east", "north"), 0.25),
            (off / 2 + road * 0.34, half, -half, -road / 2, ("west", "north"), 0.25),
        ]
    else:
        roads = [
            {
                "axis": "x",
                "offset": skew * 0.35,
                "width": road,
                "class": "major",
                "angle_deg": rng.uniform(-8, 8),
            },
            {
                "axis": "y",
                "offset": skew,
                "width": road * 0.7,
                "class": "local",
                "angle_deg": rng.uniform(-6, 6),
            },
        ]
        boxes = [
            (
                -half,
                skew - road * 0.35,
                road / 2 + skew * 0.35,
                half,
                ("east", "south"),
                0.2,
            ),
            (
                skew + road * 0.35,
                half,
                road / 2 + skew * 0.35,
                half,
                ("west", "south"),
                0.2,
            ),
            (
                -half,
                skew - road * 0.35,
                -half,
                -road / 2 + skew * 0.35,
                ("east", "north"),
                0.3,
            ),
            (
                skew + road * 0.35,
                half,
                -half,
                -road / 2 + skew * 0.35,
                ("west", "north"),
                0.3,
            ),
        ]
    parcels = []
    for i, (x0, x1, y0, y1, edges, dist) in enumerate(boxes):
        inset = rng.uniform(2.5, 5.0)
        x0 += inset
        x1 -= inset
        y0 += inset
        y1 -= inset
        parcels.append(
            Parcel(
                f"block_{i+1}",
                ((x0 + x1) / 2, (y0 + y1) / 2),
                (x1 - x0, y1 - y0),
                rng.choice((0, 0, 0, 90)),
                edges,
                dist,
                True,
                rng.uniform(0.2, 0.9),
            )
        )
    return roads, parcels


def _assign_zones(parcels: list[Parcel], rng: random.Random) -> dict[str, str]:
    available = {p.id: p for p in parcels}
    assignment = {}
    preferences = {
        "commercial": lambda p: 4.0 * (1 - p.major_road_distance)
        + 0.3 * len(p.road_edges),
        "residential": lambda p: 2.8 * p.quiet_score + 1.2 * p.major_road_distance,
        "park": lambda p: 2.0 * float(p.pedestrian_access)
        + p.size[0] * p.size[1] / 2500,
        "leisure": lambda p: 2.0 * float(p.pedestrian_access) + 0.4 * len(p.road_edges),
    }
    zone_order = _weighted_permutation(
        list(ZONES),
        {"commercial": 2.2, "residential": 1.8, "park": 1.2, "leisure": 1.0},
        rng,
    )
    for zone in zone_order:
        ids = list(available)
        weights = {pid: max(0.05, preferences[zone](available[pid])) for pid in ids}
        pid = _weighted_permutation(ids, weights, rng)[0]
        assignment[pid] = zone
        available.pop(pid)
    return assignment


def _regional(seed: int, parcel: Parcel, zone: str) -> dict[str, Any]:
    r = _rng(seed, f"region:{parcel.id}:{zone}")
    area = parcel.size[0] * parcel.size[1]
    common = {
        "region_boundary": {"center": parcel.center, "size": parcel.size},
        "orientation_deg": parcel.orientation_deg,
        "road_facing_direction": parcel.road_edges[0],
        "seed": r.randrange(1, 2**31),
        "design_language": r.choice(
            ("contemporary_warm", "civic_modern", "brick_and_wood")
        ),
    }
    if zone == "commercial":
        common.update(
            profile=r.choice(("compact_street", "medium_density", "local_cluster")),
            building_count=r.randint(2, 5),
            density=round(r.uniform(0.42, 0.72), 3),
            floor_range=[r.randint(1, 2), r.randint(3, 5)],
            front_setback=round(r.uniform(2.0, 5.5), 2),
            spacing=round(r.uniform(1.8, 4.5), 2),
            storefront_variant=r.randrange(4),
        )
    elif zone == "residential":
        ratio = round(r.uniform(0.15, 0.85), 2)
        common.update(
            profile=(
                "apartment_dominant"
                if ratio > 0.62
                else "low_rise_dominant"
                if ratio < 0.38
                else "mixed"
            ),
            building_count=max(2, round(area / r.uniform(350, 650))),
            apartment_ratio=ratio,
            floor_range=[1, r.randint(3, 7)],
            lot_size=round(r.uniform(180, 420), 1),
            spacing=round(r.uniform(3.5, 8), 2),
            garden_ratio=round(r.uniform(0.16, 0.42), 2),
            architectural_variant=r.randrange(5),
        )
    elif zone == "park":
        common.update(
            profile=r.choice(
                ("open_lawn", "tree_dominant", "neighborhood", "path_oriented")
            ),
            path_layout=r.choice(("loop", "diagonal", "branching", "perimeter")),
            open_space_ratio=round(r.uniform(0.35, 0.72), 2),
            tree_density=round(r.uniform(0.018, 0.065), 3),
            shrub_density=round(r.uniform(0.02, 0.09), 3),
            seating_count=max(3, round(area / r.uniform(220, 430))),
            planting_layout=r.choice(("clusters", "edge_bands", "groves")),
        )
    else:
        acts = r.sample(
            ("basketball", "playground", "fitness", "skate", "plaza"), k=r.randint(2, 3)
        )
        common.update(
            profile=r.choice(("active_court", "family_recreation", "public_plaza")),
            activity_types=acts,
            activity_count=len(acts),
            activity_density=round(r.uniform(0.35, 0.7), 2),
            hardscape_ratio=round(r.uniform(0.4, 0.72), 2),
            vegetation_ratio=round(r.uniform(0.12, 0.38), 2),
            open_space_layout=r.choice(("central", "linear", "clustered")),
        )
    return common


def validate_descriptor(d: dict[str, Any]) -> list[str]:
    errors = []
    parcels = d["parcels"]
    if set(p["zone"] for p in parcels) != set(ZONES):
        errors.append("each required zone must occur exactly once")
    for p in parcels:
        if min(p["size"]) < 12:
            errors.append(f"{p['id']}: parcel too small")
        if not p["pedestrian_access"] and p["zone"] in ("park", "leisure"):
            errors.append(f"{p['id']}: public zone inaccessible")
        if p["zone"] == "commercial" and not p["road_edges"]:
            errors.append(f"{p['id']}: commercial has no frontage")
        cx, cy = p["center"]
        sx, sy = p["size"]
        if abs(cx) + sx / 2 > 65 or abs(cy) + sy / 2 > 65:
            errors.append(f"{p['id']}: outside planning extent")
    for i, a in enumerate(parcels):
        for b in parcels[i + 1 :]:
            if (
                abs(a["center"][0] - b["center"][0]) < (a["size"][0] + b["size"][0]) / 2
                and abs(a["center"][1] - b["center"][1])
                < (a["size"][1] + b["size"][1]) / 2
            ):
                errors.append(f"{a['id']}/{b['id']}: overlap")
    return errors


def generate_descriptor(
    seed: int, topology: str | None = None, max_attempts: int = 64
) -> dict[str, Any]:
    for attempt in range(max_attempts):
        r = _rng(seed + attempt, "planning")
        family = topology or r.choice(TOPOLOGIES)
        roads, ps = _roads_and_parcels(family, r)
        assigned = _assign_zones(ps, r)
        parcels = []
        for p in ps:
            item = asdict(p)
            item["zone"] = assigned[p.id]
            item["regional_config"] = _regional(seed, p, assigned[p.id])
            parcels.append(item)
        d = {
            "schema_version": "1.0",
            "scene_seed": seed,
            "sampling_attempt": attempt,
            "road_topology": family,
            "roads": roads,
            "parcels": parcels,
            "vegetation": {
                "species_palette": r.choice(
                    ("temperate_mixed", "urban_deciduous", "drought_tolerant")
                ),
                "global_density_scale": round(r.uniform(0.75, 1.25), 2),
            },
            "generator_interfaces": {
                "inputs": [
                    "region_boundary",
                    "region_center",
                    "orientation_deg",
                    "road_facing_direction",
                    "seed",
                    "regional_config",
                ],
                "legacy_sources": {
                    "commercial": "generate_urban_v3_all43_01.py + commercial_rebuild_generator_15.py",
                    "residential": "generate_urban_v3_all45_02.py",
                    "park": "generate_urban_v3_all40.py",
                    "leisure": "generate_urban_v3_all44_14.py",
                },
            },
        }
        errors = validate_descriptor(d)
        if not errors:
            d["validation"] = {"valid": True, "errors": []}
            d["fingerprint"] = hashlib.sha256(
                json.dumps(d, sort_keys=True).encode()
            ).hexdigest()[:16]
            return d
    raise RuntimeError(f"unable to sample valid plan after {max_attempts} attempts")

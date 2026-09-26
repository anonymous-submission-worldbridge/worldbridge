"""Source-level urban_v1_full_07 integration pass.

This module is called by the production full-scene generator while the clean
scene is still in memory.  It never opens or appends an old regional scene.
"""
from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import importlib.util
import math
import os
from pathlib import Path

import bpy

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
PREFIX = "full07_ext:"
FULL09 = os.environ.get("C2W_FULL_REVISION") == "urban_v1_full_09"
FULL08 = os.environ.get("C2W_FULL_REVISION") in {"urban_v1_full_08", "urban_v1_full_09"}
ADD_RIVER = os.environ.get("C2W_ADD_RIVER") == "1"


def _load_residential_source_module():
    path = ROOT / "scripts/generate_urban_v3_all45_02.py"
    spec = importlib.util.spec_from_file_location("full07_residential_source", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.ROOT = ROOT
    module.PREFIX = PREFIX
    module.G.ROOT = ROOT
    module.G.PREFIX = PREFIX
    return module


def _remove_residential_road_barrier() -> list[str]:
    """Remove the road-facing fence/plinth at x=-8.6, including its gate."""
    prefixes = ("a40_fence_front_", "a40_fence_gate_")
    targets = [
        obj
        for obj in bpy.data.objects
        if obj.name.startswith(prefixes) or obj.name.startswith("a40_fence_pier_-8.6_")
    ]
    names = sorted(obj.name for obj in targets)
    if targets:
        bpy.data.batch_remove(targets)
    return names


def _place_commercial_phonebooth() -> dict:
    import urban_assets as UA

    stale = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_phonebooth_role") or "phonebooth" in obj.name.lower()
    ]
    if stale:
        bpy.data.batch_remove(stale)
    coll = bpy.data.collections.new("Full07_Commercial_Shopping_Amenities")
    bpy.context.scene.collection.children.link(coll)
    placed = UA.place_phonebooth((-13.0, -26.5), coll, yaw=math.pi / 2)
    for obj in placed:
        obj["c2w_phonebooth_role"] = "commercial_shopping_zone"
        obj["c2w_phonebooth_off_road"] = True
    return {
        "removed_legacy_phonebooths": len(stale),
        "commercial_phonebooths": len(placed),
        "commercial_location": [-13.0, -26.5, 0.0],
    }


def _source_tree_masters() -> list[bpy.types.Collection]:
    masters = sorted(
        [
            c
            for c in bpy.data.collections
            if c.name.startswith("full02:MASTER:TreeFactory:")
        ],
        key=lambda c: c.name,
    )
    if len(masters) < 5:
        raise RuntimeError(
            f"full07 requires five source-generated TreeFactory masters, got {len(masters)}"
        )
    return masters[:5]


def _build_extended_residential_district() -> dict:
    import urban_assets as UA

    P = _load_residential_source_module()
    P.RNG.seed(4507)
    P.G.RNG.seed(4507)
    root = P.G.make_collection("full07_north_residential_extension")
    M = P.make_materials()
    P.G.MATS = M

    # Asset slots used by private-garden vegetation are deliberately inert;
    # the visible extension uses the five native TreeFactory masters generated
    # earlier in this same run.  Building facade assets remain fully detailed.
    old_tree, old_shrub = P.make_tree_master, P.make_shrub_master
    P.make_tree_master = lambda name, *args, **kwargs: bpy.data.collections.new(
        PREFIX + "UNUSED_TREE_SLOT_" + name
    )
    P.make_shrub_master = lambda name, *args, **kwargs: bpy.data.collections.new(
        PREFIX + "UNUSED_SHRUB_SLOT_" + name
    )
    try:
        A = P.make_assets(M)
    finally:
        P.make_tree_master, P.make_shrub_master = old_tree, old_shrub

    trees = _source_tree_masters()
    for i, master in enumerate(trees):
        A[f"tree_{i}"] = master
    A["tree_5"] = trees[0]

    road = P.G.make_collection("connected_community_street", root)
    P.G.box(
        "community_cross_street",
        (0, 65.5, -0.075),
        (118, 9.0, 0.18),
        M["asphalt"],
        road,
        bevel=0.06,
    )
    P.G.box(
        "north_arterial_connection",
        (0, 59.0, -0.07),
        (9.0, 13.0, 0.18),
        M["asphalt"],
        road,
        bevel=0.05,
    )
    P.G.box(
        "community_south_sidewalk",
        (0, 59.25, 0.055),
        (118, 3.5, 0.12),
        M["paving"],
        road,
        bevel=0.045,
    )
    P.G.box(
        "community_north_sidewalk",
        (0, 71.75, 0.055),
        (118, 3.5, 0.12),
        M["paving"],
        road,
        bevel=0.045,
    )
    marking = P.remap_material(
        "full07_road_marking", (0.72, 0.70, 0.61), (0.92, 0.90, 0.80), 0.66, 0.02, 8.0
    )
    for i, x in enumerate(range(-54, 55, 6)):
        P.G.box(
            f"community_center_dash_{i:02d}",
            (x, 65.5, 0.035),
            (3.1, 0.12, 0.018),
            marking,
            road,
            bevel=0.01,
        )
    crosswalk_center_y = 65.5 if FULL08 else 68.2
    crosswalk_span = 8.70 if FULL08 else 5.0
    crosswalks = []
    for i, x in enumerate((-3.2, -2.4, -1.6, -0.8, 0, 0.8, 1.6, 2.4, 3.2)):
        stripe = P.G.box(
            f"arterial_crosswalk_{i:02d}",
            (x, crosswalk_center_y, 0.045),
            (0.42, crosswalk_span, 0.02),
            marking,
            road,
            bevel=0.012,
        )
        stripe["c2w_marking_type"] = "zebra_crosswalk"
        stripe["c2w_crossing_axis"] = "north_south"
        stripe["c2w_connects_road_sides"] = FULL08
        stripe["c2w_cross_road_span_m"] = crosswalk_span
        crosswalks.append(stripe)
    for x in range(-52, 53, 13):
        UA.place_streetlight((x, 59.7), road, yaw=0, day=True)
        UA.place_streetlight((x, 71.3), road, yaw=math.pi, day=True)
    for x in (-43, -17, 17, 43):
        UA.place_bench_classic((x, 72.1), road, yaw=0)
    for x in (-30, 30):
        UA.place_bin_domed((x, 72.0), road)

    district = P.G.make_collection("all45_06_style_residential_district", root)
    M["extension_marble"] = P.remap_material(
        "full07_honed_calacatta_marble",
        (0.58, 0.57, 0.54),
        (0.92, 0.90, 0.84),
        0.28,
        0.42,
        2.4,
        0.10,
    )
    M["garden_paver"] = P.remap_material(
        "full07_warm_small_format_paver",
        (0.23, 0.20, 0.16),
        (0.52, 0.45, 0.34),
        0.76,
        0.18,
        13.0,
        0.02,
    )
    site = [(-58, 73.5), (58, 73.5), (58, 133), (-58, 133)]
    ground = P.G.poly_prism(
        "expanded_residential_marble_ground",
        site,
        -0.10,
        0.17,
        M["extension_marble"],
        district,
        bevel=0.08,
    )
    ground["c2w_extension_role"] = "second_residential_district_ground"

    designs = [
        dict(
            language="A",
            w=16.2,
            d=11.3,
            wall="stucco_cream",
            roof="hip",
            door="door_a",
            door_x=0.0,
            windows=[
                (-3.65, 1.55, "bed"),
                (6.1, 1.55, "living"),
                (-4.2, 4.74, "bed"),
                (0.15, 4.70, "living"),
                (5.0, 4.68, "bed"),
            ],
            terrace=5.55,
            balcony=0.2,
            balcony_kind="balcony_glass",
        ),
        dict(
            language="B",
            w=15.4,
            d=10.8,
            wall="stucco_white",
            roof="mixed",
            roof_warm=True,
            door="door_b",
            door_x=-3.7,
            windows=[
                (-5.1, 1.52, "bed"),
                (0.2, 1.55, "living"),
                (5.0, 1.75, "utility"),
                (-4.9, 4.70, "narrow"),
                (-0.1, 4.70, "bed"),
                (4.3, 4.70, "slide"),
            ],
            balcony=4.3,
            balcony_kind="balcony_metal",
        ),
        dict(
            language="C",
            w=14.8,
            d=10.4,
            wall="stucco_gray",
            roof="gable",
            door="door_a",
            door_x=0.65,
            windows=[
                (-4.6, 1.52, "living"),
                (4.6, 1.48, "bed"),
                (-4.2, 4.72, "bed"),
                (0.45, 4.70, "slide"),
                (5.0, 4.72, "narrow"),
            ],
            terrace=-4.1,
            balcony=0.45,
            balcony_kind="balcony_solid",
        ),
    ]
    house_specs = [
        ("north_house_a", (-36, 89, 0), math.radians(-3)),
        ("north_house_b", (0, 89, 0), math.radians(2)),
        ("north_house_c", (36, 89, 0), math.radians(4)),
    ]
    houses = []
    for (name, origin, yaw), design in zip(house_specs, designs):
        houses.append(P.add_house_exterior(name, design, origin, yaw, M, A, district))

    apartments = [
        P.add_apartment(
            "north_apartment_west",
            (-29, 119, 0),
            math.radians(-3),
            25.5,
            13.4,
            5,
            0,
            M,
            A,
            district,
        ),
        P.add_apartment(
            "north_apartment_east",
            (29, 119, 0),
            math.radians(4),
            27.0,
            13.8,
            5,
            1,
            M,
            A,
            district,
        ),
    ]

    paths = [
        ((-36, 73.6), (-36, 82.8), 1.7),
        ((0, 73.6), (0, 82.8), 1.7),
        ((36, 73.6), (36, 82.8), 1.7),
        ((-36, 103.0), (-29, 111.0), 1.45),
        ((0, 103.0), (0, 109.0), 1.45),
        ((36, 103.0), (29, 111.0), 1.45),
        ((-48, 104.5), (48, 104.5), 1.35),
        ((-29, 104.5), (-29, 111.0), 1.45),
        ((29, 104.5), (29, 111.0), 1.45),
    ]
    for i, (a, b, width) in enumerate(paths):
        ax, ay = a
        bx, by = b
        length = math.hypot(bx - ax, by - ay)
        P.G.box(
            f"connected_residential_path_{i:02d}",
            ((ax + bx) / 2, (ay + by) / 2, 0.09),
            (length, width, 0.10),
            M["garden_paver"],
            district,
            rot=math.atan2(by - ay, bx - ax),
            bevel=0.035,
            segments=2,
        )

    # Layered, stone-edged tree islands use the same five complex native tree
    # families as the rebuilt park, with no blob/sphere canopy substitutes.
    tree_sites = [
        (-51, 80, 0.72),
        (-18, 105, 0.82),
        (18, 105, 0.78),
        (51, 80, 0.74),
        (0, 129, 0.80),
    ]
    for i, (x, y, scale) in enumerate(tree_sites):
        outer = []
        inner = []
        for j in range(24):
            a = math.tau * j / 24
            outer.append((x + 2.55 * math.cos(a), y + 1.85 * math.sin(a)))
            inner.append((x + 2.28 * math.cos(a), y + 1.58 * math.sin(a)))
        P.G.poly_prism(
            f"tree_island_{i}_stone_edge",
            outer,
            0.07,
            0.14,
            M["stone"],
            district,
            bevel=0.035,
        )
        P.G.poly_prism(
            f"tree_island_{i}_mulch",
            inner,
            0.15,
            0.05,
            M["mulch"],
            district,
            bevel=0.025,
        )
        P.G.collection_instance(
            trees[i],
            f"tree_island_{i}_native_tree",
            (x, y, 0.19),
            district,
            i * 1.17,
            (scale,) * 3,
        )

    roadside_tree_x = (-50, -34, -18, 18, 34, 50)
    for i, x in enumerate(roadside_tree_x):
        P.G.cylinder(
            f"roadside_tree_pit_{i}",
            (x, 73.8, 0.12),
            1.05,
            0.13,
            M["mulch"],
            district,
            vertices=32,
            bevel=0.04,
        )
        P.G.collection_instance(
            trees[i % 5],
            f"roadside_native_tree_{i}",
            (x, 73.8, 0.18),
            district,
            i * 0.83,
            (0.68,) * 3,
        )

    for coll in houses + apartments:
        coll["c2w_asset_quality"] = "all45_06_style_high_detail_source_model"
    root[
        "c2w_source_reference"
    ] = "generate_urban_v3_all45_03.py logic; no reference blend loaded"
    return {
        "street_extension_length_m": 118.0,
        "new_road_objects": 2,
        "new_sidewalk_objects": 2,
        "new_streetlights": 18,
        "detached_houses": len(houses),
        "apartment_buildings": len(apartments),
        "connected_path_segments": len(paths),
        "native_tree_instances": len(tree_sites) + len(roadside_tree_x),
        "native_tree_master_count": len(trees),
        "source_reference": "urban_v3_all45_06 procedural residential logic",
        "reference_blends_loaded": [],
        "extended_road_crosswalk": {
            "stripe_count": len(crosswalks),
            "road_center_y": 65.5,
            "crosswalk_center_y": crosswalk_center_y,
            "cross_road_span_m": crosswalk_span,
            "crossing_axis": "north_south" if FULL08 else "legacy_partial",
            "connects_both_sidewalks": FULL08 and crosswalk_span >= 8.6,
        },
    }


def _supplement_crossroads_markings() -> dict:
    """Author complete solid/dashed center markings on all four approaches.

    The intersection box and zebra crossings remain clear.  A double solid
    yellow no-passing segment protects each approach nearest the junction; a
    single dashed yellow center line continues to the end of every road arm.
    """
    if not FULL08:
        return {}
    P = _load_residential_source_module()
    markings = bpy.data.collections.get("RoadMarkings")
    if markings is None:
        raise RuntimeError("full08 requires the generated RoadMarkings collection")
    mat = P.remap_material(
        "full08_centerline_traffic_yellow",
        (0.56, 0.39, 0.025),
        (0.93, 0.69, 0.08),
        0.54,
        0.018,
        12.0,
    )

    # The old uninterrupted lines passed through the conflict area.  Replace
    # only those four center-line objects; inherited arrows, stop bars, lane
    # separators and zebra crossings remain untouched.
    stale = [o for o in markings.objects if o.name.startswith(("cl_ns", "cl_ew"))]
    stale_names = sorted(o.name for o in stale)
    if stale:
        bpy.data.batch_remove(stale)

    created = []

    def line(name, loc, dims, arm, style):
        obj = P.G.box(name, loc, dims, mat, markings, bevel=0.006)
        obj["c2w_marking_type"] = "crossroads_centerline"
        obj["c2w_crossroads_arm"] = arm
        obj["c2w_line_style"] = style
        obj["c2w_intersection_clear"] = True
        created.append(obj)
        return obj

    # Four 7.0 m double-solid approach sections start beyond the 9.63 m
    # outer edge of the zebra crossings.  Paired 0.11 m lines use a standard
    # 0.18 m clear gap and remain fully on the asphalt.
    solid_near, solid_far = 10.05, 17.05
    solid_len = solid_far - solid_near
    for arm, sign in (("north", 1), ("south", -1)):
        center = sign * (solid_near + solid_far) / 2
        for offset in (-0.145, 0.145):
            line(
                f"full08_{arm}_double_solid_{offset:+.3f}",
                (offset, center, 0.040),
                (0.11, solid_len, 0.018),
                arm,
                "double_solid",
            )
    for arm, sign in (("east", 1), ("west", -1)):
        center = sign * (solid_near + solid_far) / 2
        for offset in (-0.145, 0.145):
            line(
                f"full08_{arm}_double_solid_{offset:+.3f}",
                (center, offset, 0.040),
                (solid_len, 0.11, 0.018),
                arm,
                "double_solid",
            )

    # 3 m dash / 3 m gap center lines continue from the protected approach
    # segment to all four road ends.  No dash enters the intersection/crosswalk.
    dash_length, gap, arm_end = 3.0, 3.0, 53.0
    dash_counts = {arm: 0 for arm in ("north", "south", "east", "west")}
    cursor = solid_far + 0.65
    while cursor + dash_length <= arm_end:
        center = cursor + dash_length / 2
        for arm, loc, dims in (
            ("north", (0, center, 0.040), (0.12, dash_length, 0.018)),
            ("south", (0, -center, 0.040), (0.12, dash_length, 0.018)),
            ("east", (center, 0, 0.040), (dash_length, 0.12, 0.018)),
            ("west", (-center, 0, 0.040), (dash_length, 0.12, 0.018)),
        ):
            line(
                f"full08_{arm}_center_dash_{dash_counts[arm]:02d}",
                loc,
                dims,
                arm,
                "dashed",
            )
            dash_counts[arm] += 1
        cursor += dash_length + gap

    solid_counts = {
        arm: sum(
            o.get("c2w_crossroads_arm") == arm
            and o.get("c2w_line_style") == "double_solid"
            for o in created
        )
        for arm in dash_counts
    }
    return {
        "replaced_uninterrupted_centerlines": stale_names,
        "solid_objects_by_arm": solid_counts,
        "dashed_objects_by_arm": dash_counts,
        "solid_approach_range_m": [solid_near, solid_far],
        "dashed_continuation_end_m": arm_end,
        "intersection_marking_exclusion_half_width_m": 9.63,
        "all_four_arms_have_solid_and_dashed": all(
            solid_counts[arm] == 2 and dash_counts[arm] >= 5 for arm in dash_counts
        ),
    }


def apply() -> dict:
    removed = _remove_residential_road_barrier()
    phone = _place_commercial_phonebooth()
    extension = _build_extended_residential_district()
    crossroads = _supplement_crossroads_markings()
    third_residential = {}
    if FULL09:
        import urban_v1_full_09_residential

        third_residential = urban_v1_full_09_residential.build()
    river = {}
    if ADD_RIVER:
        import urban_v1_full_07_river

        river = urban_v1_full_07_river.build_river_corridor()
    return {
        "removed_residential_road_barrier_objects": len(removed),
        "removed_residential_road_barrier_names": removed,
        "phonebooth": phone,
        "residential_extension": extension,
        "third_residential_district": third_residential,
        "crossroads_markings": crossroads,
        "river": river,
    }

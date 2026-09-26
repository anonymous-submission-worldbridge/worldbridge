#!/usr/bin/env python3
"""Assemble urban_v1_full_10 from the approved, already-modelled reference assets.

The integration layer deliberately creates no replacement building/facility geometry.
Every visible asset is a linked collection/object from one of the user-specified blends;
only scale-one collection instances are translated/rotated to form the city plan.
"""

from __future__ import annotations

import json
import math
import time
import traceback
from pathlib import Path

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_10"
BLEND_OUT = OUT / "urban_v1_full_10.blend"

SOURCES = {
    "river3": ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river3/urban_v1_full_07-river3.blend",
    "river5": ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river5/urban_v1_full_07-river5.blend",
    "all45_09": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all45_09/urban_v3_all45_09.blend",
    "delivery6": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_delivery6/urban_v3_delivery6.blend",
    "commercial25": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all43_25/urban_v3_all43_25.blend",
    "pharmacy5": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_pharmacy5/urban_v3_pharmacy5.blend",
    "atm4": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_atm4/urban_v3_atm4.blend",
    "fountain3": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_fountain3/urban_v3_fountain.blend",
    "fitness5": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_fitness5/urban_v3_fitness5.blend",
    "all44_14": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_14/urban_v3_all44_14.blend",
    "school5": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_school5/urban_v3_school5.blend",
    "library4": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_library4/urban_v3_library4.blend",
    "bank5": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all46_5/urban_v3_all46_5.blend",
    "hospital4": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_hospital4/urban_v3_hospital4.blend",
    "gas4": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_gass4/urban_v3_gass4.blend",
    "factory3": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_factory3/urban_v3_factory.blend",
    "fire5": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_fire5/urban_v3_fire5.blend",
    "police3": ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_police3/urban_v3_police3.blend",
}

PACKS = {
    "factory3": OUT / "asset_packs/factory3_clean_collections.blend",
    "school5": OUT / "asset_packs/school5_clean_collection.blend",
    "library4": OUT / "asset_packs/library4_clean_collection.blend",
}


def log(message: str) -> None:
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {message}"
    print(line, flush=True)
    with (OUT / "generation.log").open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def reset_scene() -> bpy.types.Scene:
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "urban_v1_full_10"
    scene.unit_settings.system = "METRIC"
    scene.unit_settings.scale_length = 1.0
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.display.shading.light = "STUDIO"
    scene.display.shading.show_shadows = True
    scene.display.shading.show_cavity = True
    scene.display.shading.cavity_type = "WORLD"
    scene.display.shading.color_type = "MATERIAL"
    if scene.world is None:
        scene.world = bpy.data.worlds.new("full10:world")
    scene.world.color = (0.045, 0.065, 0.09)
    bpy.context.preferences.filepaths.save_version = 0
    return scene


def link_collections(source: Path, names: list[str]) -> dict[str, bpy.types.Collection]:
    """Link exact collection datablocks and return them by their source names."""
    source = source.resolve()
    requested = tuple(names)
    with bpy.data.libraries.load(str(source), link=True, relative=False) as (
        data_from,
        data_to,
    ):
        available = set(data_from.collections)
        missing = [name for name in requested if name not in available]
        if missing:
            raise RuntimeError(f"Missing collections in {source}: {missing}")
        # The library loader replaces entries in the assigned list with loaded IDs.
        # Always pass a copy so the caller's semantic-name list remains strings.
        data_to.collections = list(requested)
    # Blender may return the linked IDs in library order rather than assignment order.
    result = {value.name: value for value in data_to.collections if value is not None}
    missing_after_load = [name for name in requested if name not in result]
    if missing_after_load:
        raise RuntimeError(
            f"Failed to link collections from {source}: {missing_after_load}"
        )
    return result


def link_objects_matching(source: Path, predicate) -> dict[str, bpy.types.Object]:
    """Link selected source objects without importing the source validation scene."""
    source = source.resolve()
    with bpy.data.libraries.load(str(source), link=True, relative=False) as (
        data_from,
        data_to,
    ):
        names = [name for name in data_from.objects if predicate(name)]
        if not names:
            raise RuntimeError(f"No objects selected from {source}")
        data_to.objects = names
    return {value.name: value for value in data_to.objects if value is not None}


def make_master(
    name: str,
    *,
    collections: list[bpy.types.Collection] | None = None,
    objects: list[bpy.types.Object] | None = None,
) -> bpy.types.Collection:
    master = bpy.data.collections.new(f"full10:master:{name}")
    for child in collections or []:
        if child.name not in {c.name for c in master.children}:
            master.children.link(child)
    for obj in objects or []:
        if obj.name not in {o.name for o in master.objects}:
            master.objects.link(obj)
    return master


def descendants(root: bpy.types.Object) -> list[bpy.types.Object]:
    result = []
    stack = [root]
    seen = set()
    while stack:
        obj = stack.pop()
        if obj.as_pointer() in seen:
            continue
        seen.add(obj.as_pointer())
        result.append(obj)
        stack.extend(obj.children)
    return result


def filtered_collection_master(
    name: str,
    source_collection: bpy.types.Collection,
    *,
    excluded_names: set[str],
) -> bpy.types.Collection:
    objects = [
        obj
        for obj in source_collection.all_objects
        if obj.name not in excluded_names
        and obj.type not in {"CAMERA", "LIGHT"}
        and not obj.hide_render
    ]
    if not objects:
        raise RuntimeError(f"Filtered master {name} is empty")
    return make_master(name, objects=objects)


def world_footprint(
    bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
    center: tuple[float, float],
    at: tuple[float, float, float],
    yaw: float,
) -> dict:
    (xmin, ymin, zmin), (xmax, ymax, zmax) = bounds
    cx, cy = center
    c, s = math.cos(yaw), math.sin(yaw)
    polygon = []
    for x, y in ((xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)):
        lx, ly = x - cx, y - cy
        polygon.append([at[0] + c * lx - s * ly, at[1] + s * lx + c * ly])
    wx = [point[0] for point in polygon]
    wy = [point[1] for point in polygon]
    return {
        "polygon": [[round(x, 4), round(y, 4)] for x, y in polygon],
        "min": [round(min(wx), 4), round(min(wy), 4), round(zmin + at[2], 4)],
        "max": [round(max(wx), 4), round(max(wy), 4), round(zmax + at[2], 4)],
    }


ZONES: dict[str, bpy.types.Collection] = {}
PLACEMENTS: list[dict] = []


def zone_collection(zone: str) -> bpy.types.Collection:
    if zone not in ZONES:
        collection = bpy.data.collections.new(f"full10:zone:{zone}")
        bpy.context.scene.collection.children.link(collection)
        ZONES[zone] = collection
    return ZONES[zone]


def place(
    master: bpy.types.Collection,
    placement_id: str,
    *,
    category: str,
    zone: str,
    source_key: str,
    source_collection: str,
    source_bounds: tuple[tuple[float, float, float], tuple[float, float, float]],
    source_center: tuple[float, float],
    at: tuple[float, float, float],
    yaw: float = 0.0,
    variant: str = "",
    collision_class: str = "asset",
    metadata: dict | None = None,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(f"full10:placement:{placement_id}", None)
    obj.empty_display_type = "CUBE"
    obj.empty_display_size = 1.0
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    # Link before assigning the world matrix.  Blender resets matrix_world to
    # identity when a previously unlinked Object first enters a Scene graph.
    zone_collection(zone).objects.link(obj)
    obj.matrix_world = (
        Matrix.Translation(at)
        @ Matrix.Rotation(yaw, 4, "Z")
        @ Matrix.Translation((-source_center[0], -source_center[1], 0.0))
    )
    footprint = world_footprint(source_bounds, source_center, at, yaw)
    record = {
        "placement_id": placement_id,
        "name": obj.name,
        "category": category,
        "asset_type": category,
        "zone": zone,
        "variant": variant,
        "source_key": source_key,
        "source_path": str(SOURCES[source_key].resolve()),
        "source_collection": source_collection,
        "source_bounds": {"min": list(source_bounds[0]), "max": list(source_bounds[1])},
        "source_center": list(source_center),
        "location": list(at),
        "yaw_radians": yaw,
        "scale": [1.0, 1.0, 1.0],
        "footprint": footprint,
        "collision_class": collision_class,
        "reuse_policy": "linked_exact_reference_scale_one_no_remodel",
    }
    if metadata:
        record.update(metadata)
    for key in (
        "placement_id",
        "category",
        "asset_type",
        "zone",
        "variant",
        "source_path",
        "source_collection",
        "collision_class",
        "reuse_policy",
    ):
        obj[key] = record[key]
    obj["footprint"] = json.dumps(footprint, ensure_ascii=False, sort_keys=True)
    obj["source_bounds"] = json.dumps(record["source_bounds"], sort_keys=True)
    obj["facing_yaw"] = float(yaw)
    if metadata:
        for key, value in metadata.items():
            if isinstance(value, (str, int, float, bool)):
                obj[key] = value
    PLACEMENTS.append(record)
    return obj


def aabb_overlap(a: dict, b: dict, clearance: float = 0.15) -> bool:
    amin, amax = a["min"], a["max"]
    bmin, bmax = b["min"], b["max"]
    return not (
        amax[0] <= bmin[0] + clearance
        or bmax[0] <= amin[0] + clearance
        or amax[1] <= bmin[1] + clearance
        or bmax[1] <= amin[1] + clearance
    )


def validate_sources() -> None:
    missing = [
        str(path)
        for path in list(SOURCES.values()) + list(PACKS.values())
        if not path.is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Required reference blends missing:\n" + "\n".join(missing)
        )


def build_city() -> dict:
    scene = reset_scene()
    for zone in (
        "city_base",
        "residential",
        "park",
        "commercial",
        "education",
        "civic",
        "leisure",
        "health",
        "industrial",
        "roads",
    ):
        zone_collection(zone)

    log(
        "Linking river3 residential areas and river5 park, river and exact road systems"
    )
    residential_names = [
        "Residential",
        "Residential_marble_quadrant",
        "House_large_indoor",
        "House_small_a_indoor",
        "House_small_b_indoor",
        "Residential_apartment_exterior",
        "full07_ext:full07_north_residential_extension",
    ]
    river_names = [
        "Park",
        "full07_river5:River_Corridor_Production",
        "Road",
        "Sidewalks",
        "RoadMarkings",
        "TrafficLights",
        "Lamps",
        "FlowerBeds",
        "Vehicles",
    ]
    residential_source = link_collections(SOURCES["river3"], residential_names)
    river = link_collections(SOURCES["river5"], river_names)

    residential_1 = make_master(
        "residential_01_river3_reference",
        collections=[residential_source[name] for name in residential_names[:6]],
    )
    residential_2 = make_master(
        "residential_02_river3_reference",
        collections=[
            residential_source["full07_ext:full07_north_residential_extension"]
        ],
    )
    park_master = make_master("park_sculpture_nature", collections=[river["Park"]])
    river_master = make_master(
        "river5_corridor",
        collections=[river["full07_river5:River_Corridor_Production"]],
    )

    place(
        residential_1,
        "residential_01_river3_indoor",
        category="residential_area",
        zone="residential",
        source_key="river3",
        source_collection="Residential_marble_quadrant + House_*_indoor + Residential_apartment_exterior + Residential",
        source_bounds=((-54.2, 10.5, -0.12), (-8.6, 54.5, 14.89)),
        source_center=(-31.4, 32.5),
        at=(50.0, 350.0, 0.0),
        variant="river3_first_residential_with_indoor_houses",
        metadata={
            "residential_area_index": 1,
            "interior_policy": "preserve_source_indoor_collections",
        },
    )
    place(
        residential_2,
        "residential_02_river3_north_extension",
        category="residential_area",
        zone="residential",
        source_key="river3",
        source_collection="full07_ext:full07_north_residential_extension",
        source_bounds=((-59.0, 52.5, -0.5), (59.0, 133.0, 16.605)),
        source_center=(0.0, 92.75),
        at=(80.0, 420.0, 0.0),
        variant="river3_north_residential_extension",
        metadata={"residential_area_index": 2, "interior_policy": "reference_exact"},
    )
    place(
        park_master,
        "park_original_sculpture_nature",
        category="park_sculpture_nature",
        zone="park",
        source_key="river5",
        source_collection="Park",
        source_bounds=((8.2, 6.252, -0.5), (54.5, 54.5, 8.752)),
        source_center=(31.35, 30.376),
        at=(125.0, 350.0, 0.0),
        variant="river5_sculpture_nature_benches_trees",
        metadata={
            "contains_sculpture": True,
            "original_sculpture_center_preserved": True,
        },
    )
    place(
        river_master,
        "park_river5_corridor",
        category="river_corridor",
        zone="park",
        source_key="river5",
        source_collection="full07_river5:River_Corridor_Production",
        source_bounds=((53.443, -64.624, -1.589), (84.806, 145.725, 9.825)),
        source_center=(69.1245, 40.5505),
        at=(164.0, 360.0, 0.0),
        variant="river5_production",
        collision_class="river",
        metadata={"preserve_bank_and_footbridge": True},
    )

    log(
        "Linking all45_09 as the third residential area, including its six native Indoor instances"
    )
    all45 = link_collections(
        SOURCES["all45_09"], ["all45_09:parameterized_residential_generator_45_09"]
    )
    all45_master = make_master(
        "residential_03_all45_09", collections=list(all45.values())
    )
    place(
        all45_master,
        "residential_03_all45_09_native_indoor",
        category="residential_area",
        zone="residential",
        source_key="all45_09",
        source_collection="all45_09:parameterized_residential_generator_45_09",
        source_bounds=((-75.0, -52.44, -1.31), (75.0, 60.48, 42.41)),
        source_center=(0.0, 4.02),
        at=(280.0, 410.0, 0.0),
        variant="all45_09_complete_final",
        metadata={
            "residential_area_index": 3,
            "native_indoor_instance_count": 6,
            "tower_count": 8,
            "lowrise_count": 3,
        },
    )

    log("Linking separated delivery facilities")
    delivery = link_collections(
        SOURCES["delivery6"],
        [
            "delivery:FOOD_DELIVERY_LOCKER",
            "delivery:PARCEL_LOCKER",
            "delivery:DELIVERY_STATION",
        ],
    )
    delivery_specs = [
        (
            "food_delivery_locker",
            "delivery:FOOD_DELIVERY_LOCKER",
            ((-15.839, -0.861, 0.0), (-9.761, 0.18, 2.71)),
            (-12.8, -0.3405),
            (190.0, 335.0, 0.0),
        ),
        (
            "parcel_locker",
            "delivery:PARCEL_LOCKER",
            ((-9.335, -0.99, 0.0), (2.935, 0.755, 2.89)),
            (-3.2, -0.1175),
            (190.0, 430.0, 0.0),
        ),
        (
            "delivery_station",
            "delivery:DELIVERY_STATION",
            ((5.27, -8.72, -0.2), (17.93, 0.175, 4.34)),
            (11.6, -4.2725),
            (280.0, 335.0, 0.0),
        ),
    ]
    for index, (category, collection_name, bounds, center, at) in enumerate(
        delivery_specs, 1
    ):
        master = make_master(category, collections=[delivery[collection_name]])
        place(
            master,
            f"residential_delivery_{index:02d}_{category}",
            category=category,
            zone="residential",
            source_key="delivery6",
            source_collection=collection_name,
            source_bounds=bounds,
            source_center=center,
            at=at,
            variant="delivery6_exact",
            metadata={"front_direction_local": "+Y", "entrance_keepout_m": 2.0},
        )

    log(
        "Linking exact commercial25 shop wall, two separated pharmacies and five-ATM row"
    )
    commercial_names = [
        "all43_17:rear_commercial_assets",
        "all43_19:corner_store_world",
        "all43_20:connected_commercial_world",
    ]
    commercial = link_collections(SOURCES["commercial25"], commercial_names)
    commercial_master = make_master(
        "commercial_all43_25",
        collections=[commercial[name] for name in commercial_names],
    )
    place(
        commercial_master,
        "commercial_all43_25_complete",
        category="commercial_district",
        zone="commercial",
        source_key="commercial25",
        source_collection=" + ".join(commercial_names),
        source_bounds=((-58.45, -44.5, 0.0), (-6.25, -6.25, 10.25)),
        source_center=(-32.35, -25.375),
        at=(0.0, 0.0, 0.0),
        variant="all43_25_inverse_l_complete",
        metadata={"party_wall_layout_preserved": True, "source_roads_excluded": True},
    )
    pharmacy_names = [
        "pharmacy5:PHARMACY_01_CVS_CLASSICAL",
        "pharmacy5:PHARMACY_02_WELL_HIGH_STREET",
    ]
    pharmacy = link_collections(SOURCES["pharmacy5"], pharmacy_names)
    pharmacy_specs = [
        (
            "pharmacy_cvs_west",
            pharmacy_names[0],
            ((-34.021, -19.675, -0.27), (-1.979, 1.67, 9.068)),
            (-18.0, -9.0025),
            (-105.0, -95.0, 0.0),
            "cvs_classical",
        ),
        (
            "pharmacy_well_east",
            pharmacy_names[1],
            ((3.375, -19.075, -0.27), (30.625, 1.345, 11.345)),
            (17.0, -8.865),
            (55.0, -95.0, 0.0),
            "well_high_street",
        ),
    ]
    for pid, cname, bounds, center, at, variant in pharmacy_specs:
        place(
            make_master(pid, collections=[pharmacy[cname]]),
            pid,
            category="pharmacy",
            zone="commercial",
            source_key="pharmacy5",
            source_collection=cname,
            source_bounds=bounds,
            source_center=center,
            at=at,
            variant=variant,
            metadata={"front_direction_local": "+Y", "interior_preserved": True},
        )
    atm = link_collections(SOURCES["atm4"], ["urban_v3_atm4:FIVE_REFERENCE_ATMS"])
    place(
        make_master("atm4_five_machine_row", collections=list(atm.values())),
        "commercial_atm_five_machine_row",
        category="atm_row",
        zone="commercial",
        source_key="atm4",
        source_collection="urban_v3_atm4:FIVE_REFERENCE_ATMS",
        source_bounds=((-3.931, -0.824, 0.0), (3.88, 0.43, 2.33)),
        source_center=(-0.0255, -0.197),
        at=(130.0, 22.0, 0.0),
        variant="five_reference_atms",
        metadata={
            "machine_count": 5,
            "arrangement": "single_row",
            "operation_keepout_m": 2.0,
        },
    )

    log(
        "Linking the original park fitness area, exactly one fountain, and leisure precinct"
    )
    fitness = link_collections(
        SOURCES["fitness5"], ["outdoor_fitness:OUTDOOR_FITNESS_AREA"]
    )
    fitness_master = make_master(
        "fitness5_complete_area", collections=list(fitness.values())
    )
    for pid, zone, at in (
        ("park_fitness_area", "park", (70.0, 285.0, 0.0)),
        ("leisure_fitness_area", "leisure", (130.0, -325.0, 0.0)),
    ):
        place(
            fitness_master,
            pid,
            category="fitness_area",
            zone=zone,
            source_key="fitness5",
            source_collection="outdoor_fitness:OUTDOOR_FITNESS_AREA",
            source_bounds=((-40.0, -35.0, -0.16), (40.0, 35.0, 2.824)),
            source_center=(0.0, 0.0),
            at=at,
            variant="fitness5_twenty_station_complete",
            metadata={"station_count": 20, "articulated_assets_preserved": True},
        )
    fountain_objects = link_objects_matching(
        SOURCES["fountain3"], lambda name: name.startswith("urban:fountain:0:")
    )
    fountain_master = make_master(
        "fountain3_royal_quatrefoil_single", objects=list(fountain_objects.values())
    )
    place(
        fountain_master,
        "park_single_fountain",
        category="fountain",
        zone="park",
        source_key="fountain3",
        source_collection="objects prefix urban:fountain:0:royal_quatrefoil",
        source_bounds=((-13.88, -3.08, 0.02), (-7.72, 3.08, 4.185)),
        source_center=(-10.8, 0.0),
        at=(125.0, 305.0, 0.0),
        variant="royal_quatrefoil",
        metadata={"fountain_count": 1, "source_object_count": len(fountain_objects)},
    )
    all44 = link_collections(SOURCES["all44_14"], ["all44_10:COURT_PLAYGROUND_REBUILD"])
    place(
        make_master("leisure_all44_14", collections=list(all44.values())),
        "leisure_all44_14_complete",
        category="leisure_precinct",
        zone="leisure",
        source_key="all44_14",
        source_collection="all44_10:COURT_PLAYGROUND_REBUILD",
        source_bounds=((8.44, -42.627, -3.739), (135.12, -3.047, 12.019)),
        source_center=(71.78, -22.837),
        at=(0.0, -315.0, 0.0),
        variant="basketball_playground_athletics_gym_all44_14",
        metadata={"entry_direction_local": "+Y", "internal_layout_preserved": True},
    )

    log("Linking school and library on opposite sides of one civic road")
    school_link = link_collections(
        PACKS["school5"], ["full10:clean:school5_complete_campus"]
    )
    school_master = school_link["full10:clean:school5_complete_campus"]
    place(
        school_master,
        "education_school_north",
        category="school",
        zone="education",
        source_key="school5",
        source_collection="school:RIVERSIDE_SCHOOL_CAMPUS (excluding school:site:regional_ground)",
        source_bounds=((-130.0, -110.0, -0.4), (130.0, 110.0, 21.21)),
        source_center=(0.0, 0.0),
        at=(-300.0, 290.0, 0.0),
        variant="school5_complete_campus",
        metadata={"entry_direction_world": "-Y", "internal_layout_preserved": True},
    )
    library_link = link_collections(
        PACKS["library4"], ["full10:clean:library4_pair_and_site"]
    )
    library_master = library_link["full10:clean:library4_pair_and_site"]
    place(
        library_master,
        "education_library_south",
        category="library",
        zone="education",
        source_key="library4",
        source_collection="library4:TWO_REFERENCE_LIBRARY_ROW (excluding library4:site:ground)",
        source_bounds=((-90.326, -47.5, -0.29), (88.943, 46.823, 31.401)),
        source_center=(-0.6915, -0.3385),
        at=(-300.0, 96.0, 0.0),
        yaw=math.pi,
        variant="library4_two_reference_library_row",
        metadata={
            "entry_direction_world": "+Y",
            "native_tree_instances_preserved": True,
        },
    )

    log("Linking four banks as a dense three-low-plus-headquarters central campus")
    bank_names = [
        "all46_5:BANK_01_CLASSICAL_CORNER",
        "all46_5:BANK_02_WHITE_VERTICAL",
        "all46_5:BANK_03_BLUE_GLASS_HEADQUARTERS",
        "all46_5:BANK_04_BRONZE_FRAME_BRANCH",
    ]
    banks = link_collections(SOURCES["bank5"], bank_names)
    bank_specs = [
        (
            "bank_low_01_classical",
            bank_names[0],
            ((-57.25, 15.982, -0.315), (-20.482, 43.75, 26.33)),
            (-38.866, 29.866),
            (80.0, 50.0, 0.0),
            "classical_corner",
            1,
        ),
        (
            "bank_low_02_white",
            bank_names[1],
            ((24.275, 16.29, -0.315), (55.725, 44.0, 43.772)),
            (40.0, 30.145),
            (125.0, 50.0, 0.0),
            "white_vertical",
            2,
        ),
        (
            "bank_hq_blue_glass",
            bank_names[2],
            ((-32.72, 63.2, -0.29), (34.22, 104.45, 94.925)),
            (0.75, 83.825),
            (130.0, 110.0, 0.0),
            "blue_glass_headquarters",
            4,
        ),
        (
            "bank_low_03_bronze",
            bank_names[3],
            ((-21.7, -44.9, -0.29), (22.03, -15.8, 23.273)),
            (0.165, -30.35),
            (185.0, 50.0, 0.0),
            "bronze_frame_branch",
            3,
        ),
    ]
    for pid, cname, bounds, center, at, variant, order in bank_specs:
        place(
            make_master(pid, collections=[banks[cname]]),
            pid,
            category="bank",
            zone="commercial",
            source_key="bank5",
            source_collection=cname,
            source_bounds=bounds,
            source_center=center,
            at=at,
            variant=variant,
            metadata={
                "bank_count_index": order,
                "low_building_row": order in {1, 2, 3},
            },
        )

    log("Linking two different hospitals, one central and one outer-city")
    hospital_names = [
        "hospital:HOSPITAL_A_TRADITIONAL_BRICK",
        "hospital:HOSPITAL_B_RED_WHITE_PUBLIC",
    ]
    hospitals = link_collections(SOURCES["hospital4"], hospital_names)
    hospital_specs = [
        (
            "hospital_central_red_white",
            hospital_names[1],
            ((-29.85, -15.65, 0.0), (29.383, 23.672, 27.3)),
            (-0.2335, 4.011),
            (270.0, 70.0, 0.0),
            0.0,
            "red_white_public",
            "city_center",
        ),
        (
            "hospital_outskirts_traditional",
            hospital_names[0],
            ((-91.58, -12.84, -0.03), (-52.42, 22.122, 22.0)),
            (-72.0, 4.641),
            (430.0, 300.0, 0.0),
            -math.pi / 2.0,
            "traditional_brick",
            "city_outskirts",
        ),
    ]
    for pid, cname, bounds, center, at, yaw, variant, urban_role in hospital_specs:
        place(
            make_master(pid, collections=[hospitals[cname]]),
            pid,
            category="hospital",
            zone="health",
            source_key="hospital4",
            source_collection=cname,
            source_bounds=bounds,
            source_center=center,
            at=at,
            yaw=yaw,
            variant=variant,
            metadata={"urban_role": urban_role, "emergency_keepout_m": 8.0},
        )

    log("Linking fire precinct and three separated police stations")
    fire_names = [
        "fire_region_v5:AMBULANCE_TYPE_I_AMBULANCE",
        "fire_region_v5:TRUCK_CLASSIC_PUMPER",
        "fire_region_v5:TRUCK_MODERN_LADDER_ENGINE",
        "fire_region_v5:TRUCK_RAPID_RESCUE",
        "fire_region_v5:STATION_CIVIC_HEADQUARTERS",
        "fire_region_v5:STATION_INDUSTRIAL_ANNEX",
    ]
    fire = link_collections(SOURCES["fire5"], fire_names)
    place(
        make_master(
            "fire5_precinct_without_validation_site",
            collections=[fire[name] for name in fire_names],
        ),
        "civic_fire_precinct_north",
        category="fire_station",
        zone="civic",
        source_key="fire5",
        source_collection=" + ".join(fire_names),
        source_bounds=((-69.2, 9.541, -0.265), (71.3, 49.03, 14.03)),
        source_center=(1.05, 29.2855),
        at=(-400.0, -120.0, 0.0),
        variant="fire5_two_station_four_emergency_vehicle_precinct",
        metadata={
            "station_building_count": 2,
            "emergency_vehicle_count": 4,
            "front_direction_world": "-Y",
            "apron_keepout_m": 13.0,
        },
    )
    police_names = [
        "police:POLICE_A_BLUE_WHITE_CIVIC",
        "police:POLICE_B_BRICK_TOWER_MUNICIPAL",
        "police:POLICE_C_BLUE_PORTAL_CMU",
    ]
    police = link_collections(SOURCES["police3"], police_names)
    police_specs = [
        (
            "police_opposite_fire_west",
            police_names[0],
            ((-86.52, -20.109, -0.05), (-38.48, 16.783, 22.0)),
            (-62.5, -1.663),
            (-440.0, -210.0, 0.0),
            math.pi,
            "blue_white_civic",
            "opposite_fire",
        ),
        (
            "police_opposite_fire_east",
            police_names[1],
            ((-28.8, -19.089, -0.05), (28.8, 14.727, 15.24)),
            (0.0, -2.181),
            (-350.0, -210.0, 0.0),
            math.pi,
            "brick_tower_municipal",
            "opposite_fire",
        ),
        (
            "police_near_library",
            police_names[2],
            ((33.0, -22.78, -0.05), (91.535, 15.387, 9.89)),
            (62.2675, -3.6965),
            (-165.0, 96.0, 0.0),
            0.0,
            "blue_portal_cmu",
            "near_library",
        ),
    ]
    for pid, cname, bounds, center, at, yaw, variant, relation_role in police_specs:
        place(
            make_master(pid, collections=[police[cname]]),
            pid,
            category="police_station",
            zone="civic" if relation_role == "opposite_fire" else "education",
            source_key="police3",
            source_collection=cname,
            source_bounds=bounds,
            source_center=center,
            at=at,
            yaw=yaw,
            variant=variant,
            metadata={
                "relation_role": relation_role,
                "front_direction_world": "+Y" if yaw == math.pi else "-Y",
            },
        )

    log("Linking three separated gas stations and four exact factory assets")
    gas_names = [
        "gas_station:NOBILE_WAVE",
        "gas_station:BLUE_ORANGE",
        "gas_station:RED_YELLOW",
    ]
    gas = link_collections(SOURCES["gas4"], gas_names)
    gas_specs = [
        (
            "gas_east_north",
            gas_names[0],
            ((-55.5, -14.8, -0.605), (-20.5, 16.4, 8.25)),
            (-38.0, 0.8),
            (330.0, -345.0, 0.0),
            0.0,
            "nobile_wave",
            "paired_north",
        ),
        (
            "gas_east_south",
            gas_names[1],
            ((-17.5, -14.8, -0.605), (17.5, 16.4, 7.975)),
            (0.0, 0.8),
            (330.0, -418.0, 0.0),
            math.pi,
            "blue_orange",
            "paired_south",
        ),
        (
            "gas_west_outskirts",
            gas_names[2],
            ((20.5, -14.8, -0.605), (55.5, 16.4, 7.66)),
            (38.0, 0.8),
            (-545.0, 250.0, 0.0),
            math.pi / 2.0,
            "red_yellow",
            "separate_west",
        ),
    ]
    for pid, cname, bounds, center, at, yaw, variant, relation_role in gas_specs:
        place(
            make_master(pid, collections=[gas[cname]]),
            pid,
            category="gas_station",
            zone="industrial",
            source_key="gas4",
            source_collection=cname,
            source_bounds=bounds,
            source_center=center,
            at=at,
            yaw=yaw,
            variant=variant,
            metadata={"relation_role": relation_role, "driveway_keepout_m": 6.0},
        )

    factory_roots = [
        "urban:factory:0:gable_clerestory:root",
        "urban:factory:1:white_modern:root",
        "urban:factory:2:gated_campus:root",
        "urban:factory:3:highbay_monochrome:root",
    ]
    factory_pack_names = [
        "full10:clean:factory_01_gable",
        "full10:clean:factory_02_white",
        "full10:clean:factory_03_gated",
        "full10:clean:factory_04_highbay",
    ]
    factory_collections = link_collections(PACKS["factory3"], factory_pack_names)
    factory_specs = [
        (
            "factory_01_gable",
            factory_roots[0],
            ((-122.5, -16.5, -0.06), (-63.5, 18.0, 12.097)),
            (-93.0, 0.75),
            (-430.0, -455.0, 0.0),
            "gable_clerestory",
        ),
        (
            "factory_02_white",
            factory_roots[1],
            ((-58.5, -17.0, -0.06), (-5.5, 18.35, 12.05)),
            (-32.0, 0.675),
            (-370.0, -455.0, 0.0),
            "white_modern",
        ),
        (
            "factory_03_gated",
            factory_roots[2],
            ((-0.5, -16.5, -0.06), (58.5, 24.0, 8.38)),
            (29.0, 3.75),
            (-305.0, -455.0, 0.0),
            "gated_campus",
        ),
        (
            "factory_04_highbay",
            factory_roots[3],
            ((63.5, -19.0, -0.06), (126.5, 19.0, 13.35)),
            (95.0, 0.0),
            (-235.0, -455.0, 0.0),
            "highbay_monochrome",
        ),
    ]
    for pack_name, (pid, root_name, bounds, center, at, variant) in zip(
        factory_pack_names, factory_specs
    ):
        place(
            factory_collections[pack_name],
            pid,
            category="factory",
            zone="industrial",
            source_key="factory3",
            source_collection=f"object hierarchy {root_name}",
            source_bounds=bounds,
            source_center=center,
            at=at,
            yaw=math.pi,
            variant=variant,
            metadata={
                "factory_row_index": len(
                    [p for p in PLACEMENTS if p["category"] == "factory"]
                )
                + 1,
                "loading_keepout_m": 8.0,
            },
        )

    log("Building linked, scale-one road modules from river5 geometry")
    roads = river["Road"]
    sidewalks = river["Sidewalks"]
    markings = river["RoadMarkings"]
    lamps = river["Lamps"]
    traffic_lights = river["TrafficLights"]

    corners = {"sw_cor_11", "sw_cor_1-1", "sw_cor_-11", "sw_cor_-1-1"}
    ew_sidewalk = [
        o
        for o in sidewalks.objects
        if o.name in corners
        or o.name.startswith(("sw_e_", "sw_w_", "kerb_e_", "kerb_w_"))
    ]
    ns_sidewalk = [
        o
        for o in sidewalks.objects
        if o.name in corners
        or o.name.startswith(("sw_n_", "sw_s_", "kerb_n_", "kerb_s_"))
    ]
    all_sidewalk = [
        o
        for o in sidewalks.objects
        if o.name != "gnd" and not o.name.startswith(("bike_pad", "drv_"))
    ]
    ew_marks = [
        o
        for o in markings.objects
        if "_ew" in o.name or o.name.startswith(("arr_e_", "arr_w_"))
    ]
    ns_marks = [
        o
        for o in markings.objects
        if "_ns" in o.name or o.name.startswith(("arr_n_", "arr_s_"))
    ]
    ew_lamps = [
        o for o in lamps.objects if abs(abs(o.matrix_world.translation.y) - 6.25) < 0.2
    ]
    ns_lamps = [
        o for o in lamps.objects if abs(abs(o.matrix_world.translation.x) - 6.25) < 0.2
    ]
    ew_master = make_master(
        "road_ew_109m",
        objects=[o for o in roads.objects if o.name in {"isect", "road_e", "road_w"}]
        + ew_sidewalk
        + ew_marks
        + ew_lamps,
    )
    ns_master = make_master(
        "road_ns_109m",
        objects=[o for o in roads.objects if o.name in {"isect", "road_n", "road_s"}]
        + ns_sidewalk
        + ns_marks
        + ns_lamps,
    )
    intersection_master = make_master(
        "road_intersection_complete",
        objects=list(roads.objects)
        + all_sidewalk
        + list(markings.objects)
        + list(lamps.objects)
        + list(traffic_lights.objects),
    )
    amenities_master = make_master(
        "roadside_flowerbeds_and_road_vehicles",
        collections=[river["FlowerBeds"], river["Vehicles"]],
    )
    ground_obj = next(obj for obj in sidewalks.objects if obj.name == "gnd")
    ground_master = make_master("river5_ground_tile_400m", objects=[ground_obj])
    for gy in (-400.0, 0.0, 400.0):
        for gx in (-400.0, 0.0, 400.0):
            place(
                ground_master,
                f"ground_tile_{int(gx)}_{int(gy)}",
                category="city_ground_tile",
                zone="city_base",
                source_key="river5",
                source_collection="Sidewalks/gnd",
                source_bounds=((-200.0, -200.0, -0.2), (200.0, 200.0, 0.0)),
                source_center=(0.0, 0.0),
                at=(gx, gy, -0.05),
                collision_class="base",
                metadata={"tile_size_m": 400},
            )

    grid_x = [-490.5, -381.5, -272.5, -163.5, -54.5, 54.5, 163.5, 272.5, 381.5]
    grid_y = [-381.5, -272.5, -163.5, -54.5, 54.5, 163.5, 272.5, 381.5]
    horizontal_y = {-381.5, -272.5, -163.5, -54.5, 163.5}
    vertical_x = {-490.5, 381.5}
    intersection_nodes = {(x, y) for x in vertical_x for y in horizontal_y}
    for y in sorted(horizontal_y):
        for x in grid_x:
            is_intersection = (x, y) in intersection_nodes
            master = intersection_master if is_intersection else ew_master
            category = "road_intersection" if is_intersection else "road_segment_ew"
            place(
                master,
                f"road_{'intersection' if is_intersection else 'ew'}_{x:g}_{y:g}".replace(
                    "-", "m"
                ).replace(
                    ".", "p"
                ),
                category=category,
                zone="roads",
                source_key="river5",
                source_collection="Road + Sidewalks + RoadMarkings + Lamps"
                + (" + TrafficLights" if is_intersection else ""),
                source_bounds=((-54.5, -10.5, 0.0), (54.5, 10.5, 8.0)),
                source_center=(0.0, 0.0),
                at=(x, y, 0.0),
                collision_class="road",
                metadata={
                    "crosswalk_orientation": "source_exact_ew"
                    if not is_intersection
                    else "source_exact_both",
                    "traffic_clear": True,
                },
            )
    for x in sorted(vertical_x):
        for y in grid_y:
            if (x, y) in intersection_nodes:
                continue
            place(
                ns_master,
                f"road_ns_{x:g}_{y:g}".replace("-", "m").replace(".", "p"),
                category="road_segment_ns",
                zone="roads",
                source_key="river5",
                source_collection="Road + Sidewalks + RoadMarkings + Lamps",
                source_bounds=((-10.5, -54.5, 0.0), (10.5, 54.5, 8.0)),
                source_center=(0.0, 0.0),
                at=(x, y, 0.0),
                collision_class="road",
                metadata={
                    "crosswalk_orientation": "source_exact_ns",
                    "traffic_clear": True,
                },
            )
    for index, (x, y) in enumerate(
        ((-490.5, 163.5), (381.5, -54.5), (381.5, 163.5)), 1
    ):
        place(
            amenities_master,
            f"road_amenities_{index:02d}",
            category="roadside_amenities",
            zone="roads",
            source_key="river5",
            source_collection="FlowerBeds + Vehicles",
            source_bounds=((-54.5, -54.5, 0.0), (54.5, 54.5, 2.3)),
            source_center=(0.0, 0.0),
            at=(x, y, 0.0),
            collision_class="road_amenity",
            metadata={"contains_only_roadside_flowerbeds_and_vehicles": True},
        )

    strict_assets = [p for p in PLACEMENTS if p["collision_class"] == "asset"]
    overlaps = []
    for index, first in enumerate(strict_assets):
        for second in strict_assets[index + 1 :]:
            if aabb_overlap(first["footprint"], second["footprint"]):
                overlaps.append([first["placement_id"], second["placement_id"]])
    if overlaps:
        raise RuntimeError(f"Planned strict asset footprints overlap: {overlaps}")

    road_corridors = {
        "horizontal_y": sorted(horizontal_y),
        "vertical_x": sorted(vertical_x),
        "half_width_with_sidewalk_m": 10.5,
        "module_length_m": 109.0,
        "grid_x": grid_x,
        "grid_y": grid_y,
    }
    road_intrusions = []
    for asset in strict_assets:
        amin, amax = asset["footprint"]["min"], asset["footprint"]["max"]
        for y in horizontal_y:
            if (
                amin[1] < y + 10.5
                and amax[1] > y - 10.5
                and amax[0] > -545.0
                and amin[0] < 436.0
            ):
                road_intrusions.append([asset["placement_id"], f"horizontal_y={y}"])
        for x in vertical_x:
            if (
                amin[0] < x + 10.5
                and amax[0] > x - 10.5
                and amax[1] > -436.0
                and amin[1] < 436.0
            ):
                road_intrusions.append([asset["placement_id"], f"vertical_x={x}"])
    if road_intrusions:
        raise RuntimeError(
            f"Asset footprint intrudes into road/sidewalk corridor: {road_intrusions}"
        )

    relationships = [
        {
            "id": "school_library_opposite",
            "a": "education_school_north",
            "b": "education_library_south",
            "shared_road_axis": {"orientation": "EW", "coordinate": 163.5},
            "a_side": "north",
            "b_side": "south",
            "entrances_face_each_other": True,
        },
        {
            "id": "fire_police_opposite",
            "a": "civic_fire_precinct_north",
            "b": ["police_opposite_fire_west", "police_opposite_fire_east"],
            "shared_road_axis": {"orientation": "EW", "coordinate": -163.5},
            "entrances_face_each_other": True,
        },
        {
            "id": "gas_pair_opposite",
            "a": "gas_east_north",
            "b": "gas_east_south",
            "shared_road_axis": {"orientation": "EW", "coordinate": -381.5},
            "entrances_face_each_other": True,
        },
        {
            "id": "third_police_near_library",
            "a": "police_near_library",
            "b": "education_library_south",
            "nearest_edge_clearance_m": 16.0,
        },
        {
            "id": "bank_next_to_commercial",
            "a": [
                "bank_low_01_classical",
                "bank_low_02_white",
                "bank_low_03_bronze",
                "bank_hq_blue_glass",
            ],
            "b": "commercial_all43_25_complete",
            "urban_role": "central_adjacent",
        },
    ]
    zones = {
        "park_irregular_polygon": [
            [25, 245],
            [136, 245],
            [151, 276],
            [151, 390],
            [92, 390],
            [88, 325],
            [25, 325],
        ],
        "residential_north_east_polygon": [
            [18, 322],
            [80, 322],
            [91, 372],
            [198, 372],
            [198, 346],
            [360, 346],
            [360, 472],
            [16, 472],
        ],
        "commercial_center_polygon": [
            [-135, -125],
            [78, -125],
            [90, -45],
            [315, -45],
            [315, 145],
            [78, 145],
            [45, 32],
            [-135, 32],
        ],
        "education_west_polygon": [[-438, 35], [-132, 35], [-132, 412], [-438, 412]],
        "civic_west_polygon": [[-477, -238], [-312, -238], [-312, -92], [-477, -92]],
        "leisure_south_polygon": [
            [-72, -370],
            [180, -370],
            [180, -286],
            [65, -276],
            [-72, -286],
        ],
        "industrial_outer_polygon": [
            [-570, -490],
            [-190, -490],
            [-190, -424],
            [295, -424],
            [295, -443],
            [385, -443],
            [385, -321],
            [295, -321],
            [295, -370],
            [-570, -370],
        ],
    }
    manifest = {
        "schema": "agent.urban_full_layout.v1",
        "scene_revision": "urban_v1_full_10",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "output_blend": str(BLEND_OUT.resolve()),
        "integration_policy": "link approved final reference assets; translate/yaw only; never remodel requested objects",
        "city_bounds": {"min": [-600.0, -600.0, -1.6], "max": [600.0, 600.0, 95.0]},
        "zones": zones,
        "placements": PLACEMENTS,
        "road_network": road_corridors,
        "relationships": relationships,
        "requirements": {
            "residential_area_count": 3,
            "all45_09_native_indoor_instances": 6,
            "delivery_facility_count": 3,
            "pharmacy_count": 2,
            "atm_machine_count": 5,
            "fountain_count": 1,
            "fitness_area_count": 2,
            "bank_building_count": 4,
            "hospital_count": 2,
            "hospital_variants_different": True,
            "gas_station_count": 3,
            "factory_count": 4,
            "fire_station_building_count": 2,
            "police_station_count": 3,
            "road_crosswalks_source_orientation_preserved": True,
            "road_obstructions": "vehicles_only",
        },
        "generation_checks": {
            "asset_aabb_overlap_pairs": overlaps,
            "asset_road_intrusions": road_intrusions,
            "all_placement_scales_one": all(
                p["scale"] == [1.0, 1.0, 1.0] for p in PLACEMENTS
            ),
            "source_files_exist": True,
        },
        "source_files": {key: str(path.resolve()) for key, path in SOURCES.items()},
        "clean_collection_packs": {
            key: str(path.resolve()) for key, path in PACKS.items()
        },
    }
    text = bpy.data.texts.new("GENERATION_MANIFEST")
    text.write(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True))
    scene["scene_revision"] = "urban_v1_full_10"
    scene["integration_policy"] = manifest["integration_policy"]
    scene["placement_count"] = len(PLACEMENTS)
    scene["strict_asset_overlap_count"] = len(overlaps)
    scene["asset_road_intrusion_count"] = len(road_intrusions)
    return manifest


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation.log").write_text("", encoding="utf-8")
    failure_marker = OUT / "GENERATION_FAILED.txt"
    if failure_marker.exists():
        failure_marker.unlink()
    for stale_name in (
        "strict_completion_audit.json",
        "SUCCESS",
        "render_manifest.json",
    ):
        stale_path = OUT / stale_name
        if stale_path.exists():
            stale_path.unlink()
    validate_sources()
    log("Starting urban_v1_full_10 exact-reference assembly")
    try:
        manifest = build_city()
        (OUT / "layout_plan.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        audit = {
            "status": "PASS",
            "scene_revision": manifest["scene_revision"],
            "placement_count": len(manifest["placements"]),
            "strict_asset_overlap_pairs": manifest["generation_checks"][
                "asset_aabb_overlap_pairs"
            ],
            "asset_road_intrusions": manifest["generation_checks"][
                "asset_road_intrusions"
            ],
            "source_count": len(manifest["source_files"]),
            "linked_library_count_before_save": len(bpy.data.libraries),
            "requirements": manifest["requirements"],
        }
        (OUT / "generation_audit.json").write_text(
            json.dumps(audit, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        log(
            f"Writing scene-reachable production blend with {len(PLACEMENTS)} placements and {len(bpy.data.libraries)} libraries"
        )
        temporary_blend = OUT / "urban_v1_full_10.writing.blend"
        if temporary_blend.exists():
            temporary_blend.unlink()
        # libraries.write serializes only IDs reachable from the production Scene
        # (plus the audit manifest), avoiding unused validation datablocks and UI state.
        bpy.data.libraries.write(
            str(temporary_blend),
            {bpy.context.scene, bpy.data.texts["GENERATION_MANIFEST"]},
            path_remap="ABSOLUTE",
            fake_user=True,
            compress=False,
        )
        if not temporary_blend.is_file() or temporary_blend.stat().st_size == 0:
            raise RuntimeError(
                "Production blend writer returned without a non-empty file"
            )
        temporary_blend.replace(BLEND_OUT)
        log(f"Saved {BLEND_OUT}")
    except Exception:
        failure = traceback.format_exc()
        log(f"FAILED\n{failure}")
        (OUT / "GENERATION_FAILED.txt").write_text(failure, encoding="utf-8")
        raise


if __name__ == "__main__":
    main()

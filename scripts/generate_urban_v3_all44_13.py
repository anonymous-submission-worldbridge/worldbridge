"""ALL44-13: integrated production leisure and sports precinct.

This source generator combines the complete ALL44-10 basketball/playground
zone, the ALL44-11 athletics ground, and the ALL44-12 civic gymnasium without
overlap.  The established east/west planning envelope is retained.  Extra
capacity is created only to the south: the gymnasium occupies the middle
campus band and the athletics ground is translated into a new southern band.
A fully constructed west-side pedestrian promenade links the retained leisure
zone, gymnasium forecourt, and the athletics ground's controlled entrance.

``add_service_building_details`` is the production hook consumed by
``generate_urban_v1_full_01.py``.  The focused entry opens ALL44-10 only as a
shared source-authored base and installs both later facilities from their real
generators; it never merges prebuilt demonstration Blend geometry.
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


import argparse
import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))

import generate_urban_v3_all44_10 as retained
import generate_urban_v3_all44_11 as athletics
import generate_urban_v3_all44_12 as gymnasium


INPUT = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_10/urban_v3_all44_10.blend"
)
OUTPUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_13"
PREFIX = "all44_13:"
SITE_NAME = PREFIX + "INTEGRATED_NORTH_SOUTH_SPORTS_CAMPUS"

# The original x envelope is unchanged.  Only the southern y boundary moves.
ORIGINAL_LEISURE_BOUNDS = (9.50, 54.40, -41.90, -9.50)
GYMNASIUM_BOUNDS = (
    gymnasium.STADIUM_CENTER.x - gymnasium.EAVE_RX,
    gymnasium.STADIUM_CENTER.x + gymnasium.EAVE_RX,
    gymnasium.STADIUM_CENTER.y - gymnasium.EAVE_RY,
    gymnasium.STADIUM_CENTER.y + gymnasium.EAVE_RY,
)
ATHLETICS_TRANSLATION = Vector((0.0, -23.20, 0.0))
ATHLETICS_CENTER = athletics.GROUND_CENTER + ATHLETICS_TRANSLATION
ATHLETICS_BOUNDS = (
    athletics.SITE_BOUNDS[0],
    athletics.SITE_BOUNDS[1],
    athletics.SITE_BOUNDS[2] + ATHLETICS_TRANSLATION.y,
    athletics.SITE_BOUNDS[3] + ATHLETICS_TRANSLATION.y,
)
EXPANDED_LEISURE_BOUNDS = (9.50, 54.40, -85.20, -9.50)

# Stable ALL44-10 regional interfaces remain available to the full-city build.
base = retained.base
remove_old_court_playground = retained.remove_old_court_playground
tune_retained_materials = retained.tune_retained_materials
create_shared_materials = retained.create_shared_materials
generate_real_turf = retained.generate_real_turf
generate_playground = retained.generate_playground
populate_playground_details = retained.populate_playground_details

_BOX_MESH_CACHE: dict[tuple, bpy.types.Mesh] = {}


def args():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--quality", choices=("test", "final"), default="final")
    parser.add_argument("--skip-save", action="store_true")
    return parser.parse_args(values)


def _material(name, color, roughness, metallic=0.0, noise=0.0):
    full_name = PREFIX + name
    existing = bpy.data.materials.get(full_name)
    if existing is not None:
        return existing
    material = bpy.data.materials.new(full_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if noise:
        texture = nodes.new("ShaderNodeTexNoise")
        texture.inputs["Scale"].default_value = 7.0
        texture.inputs["Detail"].default_value = 4.0
        texture.inputs["Roughness"].default_value = 0.72
        ramp = nodes.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (
            *(max(0.0, channel - noise) for channel in color),
            1.0,
        )
        ramp.color_ramp.elements[1].color = (
            *(min(1.0, channel + noise) for channel in color),
            1.0,
        )
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.16
        bump.inputs["Distance"].default_value = 0.035
        links.new(texture.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        links.new(texture.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return material


def campus_materials():
    return {
        "subbase": _material(
            "MAT_PROMENADE_COMPACTED_SUBBASE", (0.18, 0.17, 0.15), 0.96, noise=0.025
        ),
        "bedding": _material(
            "MAT_PROMENADE_BEDDING_AGGREGATE", (0.31, 0.27, 0.21), 0.98, noise=0.045
        ),
        "campus_surface": _material(
            "MAT_CAMPUS_RESIN_BOUND_MINERAL_AGGREGATE",
            (0.235, 0.215, 0.185),
            0.95,
            noise=0.052,
        ),
        "paver_a": _material(
            "MAT_PROMENADE_GRANITE_WARM", (0.48, 0.43, 0.36), 0.90, noise=0.055
        ),
        "paver_b": _material(
            "MAT_PROMENADE_GRANITE_COOL", (0.35, 0.37, 0.38), 0.88, noise=0.045
        ),
        "curb": _material(
            "MAT_PROMENADE_PRECAST_CURB", (0.46, 0.47, 0.45), 0.91, noise=0.025
        ),
        "drain": _material(
            "MAT_PROMENADE_DRAIN_BODY", (0.09, 0.095, 0.10), 0.70, metallic=0.30
        ),
        "steel": _material(
            "MAT_PROMENADE_STAINLESS_STEEL", (0.36, 0.38, 0.40), 0.32, metallic=0.82
        ),
        "tactile": _material(
            "MAT_PROMENADE_TACTILE_WARNING", (0.66, 0.47, 0.055), 0.83, noise=0.018
        ),
        "sign": _material(
            "MAT_PROMENADE_WAYFINDING_ENAMEL", (0.035, 0.16, 0.19), 0.54, metallic=0.20
        ),
        "letter": _material(
            "MAT_PROMENADE_SIGN_LETTERING", (0.82, 0.84, 0.78), 0.46, metallic=0.10
        ),
    }


def _box_mesh(dimensions, material):
    key = tuple(round(float(value), 5) for value in dimensions) + (material.name,)
    existing = _BOX_MESH_CACHE.get(key)
    if existing is not None:
        return existing
    x, y, z = (value / 2 for value in dimensions)
    vertices = [
        (-x, -y, -z),
        (x, -y, -z),
        (x, y, -z),
        (-x, y, -z),
        (-x, -y, z),
        (x, -y, z),
        (x, y, z),
        (-x, y, z),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new(PREFIX + "MESH:SHARED_BOX")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    _BOX_MESH_CACHE[key] = mesh
    return mesh


def _cube(name, location, dimensions, material, collection, bevel=0.0, rotation=0.0):
    obj = bpy.data.objects.new(PREFIX + name, _box_mesh(dimensions, material))
    collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler[2] = rotation
    if bevel:
        modifier = obj.modifiers.new("constructed_edge_chamfer", "BEVEL")
        modifier.width = min(bevel, min(dimensions) * 0.22)
        modifier.segments = 2
    return obj


def _instance(collection, master, name, location, rotation=0.0, scale=1.0):
    obj = bpy.data.objects.new(PREFIX + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = location
    obj.rotation_euler[2] = rotation
    obj.scale = (scale, scale, scale)
    obj["c2w_role"] = "verified production asset instance"
    obj["c2w_asset_id"] = master.name
    return obj


def clear_stale_revision():
    objects = [obj for obj in bpy.data.objects if obj.name.startswith(PREFIX)]
    if objects:
        bpy.data.batch_remove(objects)
    collections = [
        collection
        for collection in bpy.data.collections
        if collection.name.startswith(PREFIX)
    ]
    if collections:
        bpy.data.batch_remove(collections)
    for datablocks in (bpy.data.meshes, bpy.data.materials, bpy.data.curves):
        stale = [
            block
            for block in datablocks
            if block.name.startswith(PREFIX) and block.users == 0
        ]
        if stale:
            bpy.data.batch_remove(stale)
    _BOX_MESH_CACHE.clear()
    return len(objects)


def _translate_site(site, delta):
    """Translate authored site objects while leaving reusable masters local."""
    moved = 0
    for obj in list(site.objects):
        obj.location += delta
        moved += 1
    site["c2w_world_translation_m"] = list(delta)
    site["c2w_replanned_center"] = list(ATHLETICS_CENTER)
    site[
        "c2w_layout_policy"
    ] = "south-translated athletics band; east/west planning envelope unchanged"
    return moved


def _build_promenade(root, materials):
    site = bpy.data.collections.new(SITE_NAME)
    root.children.link(site)
    site["c2w_semantic_zone"] = "continuous accessible public sports-campus promenade"
    site["c2w_construction_system"] = (
        "compacted granular subbase, bedding aggregate, individually jointed granite pavers, "
        "precast edge restraints, slot drainage, tactile thresholds and production street furniture"
    )

    # Continuous civil ground construction removes exposed/undefined terrain
    # between the three program bands.  It is deliberately layered below all
    # building, track and promenade wearing surfaces rather than represented by
    # a zero-thickness colored plane.
    campus_x0, campus_x1 = 9.56, 54.34
    campus_y0, campus_y1 = -85.12, -41.76
    _cube(
        "south_extension_compacted_formation_layer",
        ((campus_x0 + campus_x1) / 2, (campus_y0 + campus_y1) / 2, 0.035),
        (campus_x1 - campus_x0, campus_y1 - campus_y0, 0.11),
        materials["subbase"],
        site,
        0.035,
    )
    _cube(
        "south_extension_permeable_aggregate_wearing_course",
        ((campus_x0 + campus_x1) / 2, (campus_y0 + campus_y1) / 2, 0.105),
        (campus_x1 - campus_x0 - 0.16, campus_y1 - campus_y0 - 0.16, 0.06),
        materials["campus_surface"],
        site,
        0.028,
    )

    # The 3.2 m route clears the gymnasium's west eave by 1.55 m and connects
    # its forecourt directly to the relocated athletics west entrance.
    x0, x1 = 20.40, 23.60
    y0, y1 = -64.65, -41.95
    _cube(
        "north_south_prom_end_subbase",
        ((x0 + x1) / 2, (y0 + y1) / 2, 0.09),
        (x1 - x0 + 0.34, y1 - y0 + 0.24, 0.18),
        materials["subbase"],
        site,
        0.025,
    )
    _cube(
        "north_south_prom_bedding_course",
        ((x0 + x1) / 2, (y0 + y1) / 2, 0.18),
        (x1 - x0 + 0.10, y1 - y0, 0.06),
        materials["bedding"],
        site,
        0.018,
    )

    columns, rows = 5, 38
    cell_x, cell_y = (x1 - x0) / columns, (y1 - y0) / rows
    paver_count = 0
    for row in range(rows):
        stagger = cell_x * 0.16 if row % 2 else 0.0
        for column in range(columns):
            px = x0 + (column + 0.5) * cell_x + stagger
            # Trim the stagger at the fixed edge instead of allowing a paver
            # to project into the required gymnasium clearance.
            px = min(px, x1 - cell_x * 0.48)
            material = (
                materials["paver_b"]
                if (row * 5 + column * 3) % 17 == 0
                else materials["paver_a"]
            )
            _cube(
                f"promenade_jointed_granite_paver_{row:02d}_{column:02d}",
                (px, y0 + (row + 0.5) * cell_y, 0.235),
                (cell_x - 0.028, cell_y - 0.030, 0.070),
                material,
                site,
                0.006,
            )
            paver_count += 1

    # A widened dog-leg arrival apron aligns the promenade to the athletics
    # ground's real 1.8 m west pedestrian gate at x=19.95.
    ax0, ax1, ay0, ay1 = 18.62, 23.60, -65.38, -64.65
    _cube(
        "athletics_gate_apron_subbase",
        ((ax0 + ax1) / 2, (ay0 + ay1) / 2, 0.09),
        (ax1 - ax0 + 0.24, ay1 - ay0 + 0.20, 0.18),
        materials["subbase"],
        site,
        0.025,
    )
    _cube(
        "athletics_gate_apron_bedding",
        ((ax0 + ax1) / 2, (ay0 + ay1) / 2, 0.18),
        (ax1 - ax0, ay1 - ay0, 0.06),
        materials["bedding"],
        site,
        0.012,
    )
    apron_columns, apron_rows = 8, 2
    apron_x, apron_y = (ax1 - ax0) / apron_columns, (ay1 - ay0) / apron_rows
    for row in range(apron_rows):
        for column in range(apron_columns):
            _cube(
                f"athletics_gate_apron_paver_{row:02d}_{column:02d}",
                (ax0 + (column + 0.5) * apron_x, ay0 + (row + 0.5) * apron_y, 0.235),
                (apron_x - 0.025, apron_y - 0.025, 0.070),
                materials["paver_b"]
                if (column + row) % 7 == 0
                else materials["paver_a"],
                site,
                0.006,
            )
            paver_count += 1

    # Durable edge restraints, continuous drainage, and real grate bars make
    # the route a built civil assembly rather than a colored ground strip.
    for side, x in (("west", x0 - 0.14), ("east", x1 + 0.14)):
        _cube(
            f"promenade_precast_edge_restraint_{side}",
            (x, (y0 + y1) / 2, 0.22),
            (0.18, y1 - y0 + 0.20, 0.28),
            materials["curb"],
            site,
            0.018,
        )
    drain_x = x1 + 0.34
    _cube(
        "promenade_slot_drain_channel",
        (drain_x, (y0 + y1) / 2, 0.205),
        (0.22, y1 - y0, 0.20),
        materials["drain"],
        site,
        0.015,
    )
    grate_count = 0
    for index in range(76):
        y = y0 + 0.18 + index * (y1 - y0 - 0.36) / 75
        _cube(
            f"promenade_drain_grate_bar_{index:02d}",
            (drain_x, y, 0.317),
            (0.18, 0.045, 0.024),
            materials["steel"],
            site,
            0.004,
        )
        grate_count += 1

    # Tactile warnings identify the athletics gate threshold.
    tactile_count = 0
    for row in range(2):
        for column in range(6):
            _cube(
                f"athletics_gate_tactile_paver_{row:02d}_{column:02d}",
                (18.95 + column * 0.39, -65.10 + row * 0.29, 0.282),
                (0.35, 0.25, 0.045),
                materials["tactile"],
                site,
                0.006,
            )
            tactile_count += 1

    # Reuse existing detailed public-realm masters.  No substitute poles,
    # cylinders, or low-detail vegetation are synthesized here.
    shared_instances = 0
    lamp = bpy.data.collections.get("all44_10:MASTER_LAMP")
    bench = bpy.data.collections.get("all44_10:MASTER_EDGE_BENCH")
    bin_master = bpy.data.collections.get("all44_10:MASTER_BIN")
    if lamp:
        for index, y in enumerate((-46.1, -53.6, -61.2)):
            _instance(
                site,
                lamp,
                f"promenade_area_light_{index:02d}",
                (20.78, y, 0.31),
                math.pi / 2,
            )
            shared_instances += 1
    if bench:
        for index, y in enumerate((-48.7, -58.2)):
            _instance(
                site,
                bench,
                f"promenade_rest_bench_{index:02d}",
                (21.72, y, 0.30),
                math.pi,
            )
            shared_instances += 1
    if bin_master:
        _instance(
            site,
            bin_master,
            "promenade_waste_and_recycling_bin",
            (20.72, -58.75, 0.30),
            math.pi / 2,
        )
        shared_instances += 1

    # A fabricated wayfinding pylon has a buried footing, twin steel posts,
    # folded enamel panel, raised direction bars, and protective top cap.
    _cube(
        "wayfinding_pylon_footing",
        (20.90, -43.15, 0.13),
        (0.72, 0.55, 0.26),
        materials["curb"],
        site,
        0.06,
    )
    for x in (20.72, 21.08):
        _cube(
            "wayfinding_pylon_steel_post",
            (x, -43.15, 1.34),
            (0.075, 0.075, 2.36),
            materials["steel"],
            site,
            0.012,
        )
    _cube(
        "wayfinding_pylon_folded_panel",
        (20.90, -43.15, 1.70),
        (0.82, 0.12, 1.35),
        materials["sign"],
        site,
        0.045,
    )
    for index, z in enumerate((1.46, 1.76, 2.06)):
        _cube(
            f"wayfinding_pylon_raised_direction_bar_{index:02d}",
            (20.90, -43.075, z),
            (0.56 - index * 0.06, 0.045, 0.065),
            materials["letter"],
            site,
            0.012,
        )
    _cube(
        "wayfinding_pylon_weather_cap",
        (20.90, -43.15, 2.43),
        (0.90, 0.18, 0.10),
        materials["steel"],
        site,
        0.025,
    )

    return site, {
        "promenade_modular_pavers": paver_count,
        "promenade_drain_grate_bars": grate_count,
        "athletics_gate_tactile_pavers": tactile_count,
        "shared_public_realm_asset_instances": shared_instances,
        "continuous_south_extension_ground_layers": 2,
    }


def _mesh_has_authored_extent(obj):
    if obj.type != "MESH" or not obj.data or not obj.data.vertices:
        return True
    extents = []
    for axis in range(3):
        values = [vertex.co[axis] for vertex in obj.data.vertices]
        extents.append(max(values) - min(values))
    # Thin pitch markings are intentionally planar manufactured surfacing;
    # only point/line collapse is forbidden.
    return sum(extent > 1e-6 for extent in extents) >= 2


def _audit(
    root, athletics_site, gymnasium_site, connector_site, connector_stats, moved_objects
):
    ground = bpy.data.objects.get(athletics.PREFIX + "community_athletics_ground")
    stadium = bpy.data.objects.get(gymnasium.PREFIX + "reference_oval_gymnasium")
    leisure_objects = list(root.all_objects)
    names = [obj.name.lower() for obj in leisure_objects]
    forbidden = [
        obj.name
        for obj in leisure_objects
        if any(
            token in obj.name.lower()
            for token in ("toy", "proxy", "placeholder", "dummy", "lowpoly", "low_poly")
        )
    ]
    collapsed = [
        obj.name
        for obj in leisure_objects
        if obj.name.startswith((athletics.PREFIX, gymnasium.PREFIX, PREFIX))
        and not _mesh_has_authored_extent(obj)
    ]
    actual_athletics_center = list(ground.location) if ground else []
    actual_stadium_center = list(stadium.location) if stadium else []
    checks = {
        "source_level_integration": True,
        "retained_basketball_court_objects": sum(
            "basketball" in name or "court_" in name for name in names
        ),
        "retained_playground_objects": sum(
            "playground" in name
            or "slide" in name
            or "swing" in name
            or "climbing" in name
            for name in names
        ),
        "athletics_ground_present": ground is not None,
        "athletics_ground_is_reusable_collection_instance": bool(
            ground
            and ground.instance_type == "COLLECTION"
            and ground.instance_collection
        ),
        "athletics_site_objects_translated": moved_objects,
        "athletics_center_world": actual_athletics_center,
        "gymnasium_present": stadium is not None,
        "gymnasium_is_reusable_collection_instance": bool(
            stadium
            and stadium.instance_type == "COLLECTION"
            and stadium.instance_collection
        ),
        "gymnasium_center_world": actual_stadium_center,
        "connector_collection_present": connector_site.name in bpy.data.collections,
        **connector_stats,
        "program_world_bounds": {
            "retained_northern_leisure": list(ORIGINAL_LEISURE_BOUNDS),
            "middle_gymnasium": [round(value, 3) for value in GYMNASIUM_BOUNDS],
            "southern_athletics": [round(value, 3) for value in ATHLETICS_BOUNDS],
            "integrated_leisure_envelope": list(EXPANDED_LEISURE_BOUNDS),
        },
        "layout_clearances_m": {
            "retained_zone_to_gymnasium": round(
                ORIGINAL_LEISURE_BOUNDS[2] - GYMNASIUM_BOUNDS[3], 3
            ),
            "gymnasium_to_athletics": round(
                GYMNASIUM_BOUNDS[2] - ATHLETICS_BOUNDS[3], 3
            ),
            "promenade_to_gymnasium_west_eave": round(GYMNASIUM_BOUNDS[0] - 23.60, 3),
            "athletics_to_expanded_south_limit": round(
                ATHLETICS_BOUNDS[2] - EXPANDED_LEISURE_BOUNDS[2], 3
            ),
            "athletics_to_west_limit": round(
                ATHLETICS_BOUNDS[0] - EXPANDED_LEISURE_BOUNDS[0], 3
            ),
            "athletics_to_east_limit": round(
                EXPANDED_LEISURE_BOUNDS[1] - ATHLETICS_BOUNDS[1], 3
            ),
        },
        "east_west_expansion_m": 0.0,
        "southward_expansion_m": round(
            ORIGINAL_LEISURE_BOUNDS[2] - EXPANDED_LEISURE_BOUNDS[2], 3
        ),
        "forbidden_degenerate_asset_names": forbidden,
        "collapsed_new_meshes": collapsed,
    }
    failures = []
    minimums = {
        "retained_basketball_court_objects": 20,
        # ALL44-10 stores the slide, swing, climbing frame and safety-surface
        # assemblies as collection instances; only their site-level objects
        # carry playground-related names in ``root.all_objects``.
        "retained_playground_objects": 8,
        "athletics_site_objects_translated": 100,
        "promenade_modular_pavers": 200,
        "promenade_drain_grate_bars": 70,
        "athletics_gate_tactile_pavers": 12,
        # The focused ALL44-10 Blend reliably retains the three detailed lamp
        # masters.  Benches/bins are reused when present, while the constructed
        # pylon, drainage and tactile systems remain mandatory regardless.
        "shared_public_realm_asset_instances": 3,
        "continuous_south_extension_ground_layers": 2,
    }
    for key, minimum in minimums.items():
        if checks[key] < minimum:
            failures.append(f"{key}={checks[key]} below required {minimum}")
    for key in (
        "athletics_ground_present",
        "athletics_ground_is_reusable_collection_instance",
        "gymnasium_present",
        "gymnasium_is_reusable_collection_instance",
        "connector_collection_present",
    ):
        if not checks[key]:
            failures.append(f"{key}=False")
    if ground and (ground.location - ATHLETICS_CENTER).length > 0.001:
        failures.append(
            f"athletics center mismatch: {list(ground.location)} != {list(ATHLETICS_CENTER)}"
        )
    if stadium and (stadium.location - gymnasium.STADIUM_CENTER).length > 0.001:
        failures.append(
            f"gymnasium center mismatch: {list(stadium.location)} != {list(gymnasium.STADIUM_CENTER)}"
        )
    if min(checks["layout_clearances_m"].values()) < 0.25:
        failures.append(f"unsafe planned clearance: {checks['layout_clearances_m']}")
    if forbidden:
        failures.append(f"forbidden degenerate asset names: {forbidden[:20]}")
    if collapsed:
        failures.append(f"collapsed new meshes: {collapsed[:20]}")
    if failures:
        raise RuntimeError(
            {
                "all44_13_integrated_leisure_quality_audit_failed": failures,
                "checks": checks,
            }
        )

    connector_site["c2w_quality_audit"] = json.dumps(checks, sort_keys=True)
    return {
        "pipeline_stage": "generate_urban_v3_all44_13.py",
        "campus_program": "basketball/playground + civic gymnasium + community athletics ground",
        "planning_policy": "retain east/west envelope; extend only south; separate programs with audited clearances",
        "circulation_system": "stadium forecourt connection plus west accessible promenade to athletics gate",
        "construction_policy": "real source-authored assemblies and reusable production masters; no toy, proxy, placeholder or collapsed assets",
        **checks,
    }


def install_integrated_leisure_precinct(root):
    """Install and replan the two production sports generators as one campus."""
    paused_modifiers = []
    for obj in bpy.context.scene.objects:
        for modifier in obj.modifiers:
            if modifier.type == "NODES" and modifier.show_viewport:
                modifier.show_viewport = False
                paused_modifiers.append(modifier)
    try:
        clear_stale_revision()
        athletics_site, athletics_audit = athletics.install_athletics_ground(root)
        moved_objects = _translate_site(athletics_site, ATHLETICS_TRANSLATION)
        gymnasium_site, gymnasium_audit = gymnasium.install_parametric_stadium(root)
        connector_site, connector_stats = _build_promenade(root, campus_materials())
        audit = _audit(
            root,
            athletics_site,
            gymnasium_site,
            connector_site,
            connector_stats,
            moved_objects,
        )
        audit["athletics_source_audit"] = athletics_audit
        audit["gymnasium_source_audit"] = gymnasium_audit
        audit["viewport_scatter_modifiers_paused_during_assembly"] = len(
            paused_modifiers
        )
        root["all44_13_integrated_leisure_audit"] = json.dumps(audit, sort_keys=True)
        root["all44_13_athletics_site"] = athletics_site.name
        root["all44_13_gymnasium_site"] = gymnasium_site.name
        return connector_site, audit
    finally:
        for modifier in paused_modifiers:
            modifier.show_viewport = True


def add_service_building_details(materials, root):
    """Production full-city hook for the complete integrated leisure region."""
    service_building = retained.add_service_building_details(materials, root)
    site, audit = install_integrated_leisure_precinct(root)
    root["all44_13_retained_service_building"] = service_building.name
    root["all44_13_integrated_leisure_audit"] = json.dumps(audit, sort_keys=True)
    return site


def _focused_render_visibility():
    old = {obj: obj.hide_render for obj in bpy.context.scene.objects}
    for obj in bpy.context.scene.objects:
        tree_dependency = any(
            collection.name.startswith("assets:TreeFactory")
            or collection.name.startswith("assets:GenericTreeFactory")
            for collection in obj.users_collection
        )
        keep = (
            obj.name.startswith(
                ("all44_04:", "all44_10:", athletics.PREFIX, gymnasium.PREFIX, PREFIX)
            )
            or obj.type == "LIGHT"
            or tree_dependency
        )
        obj.hide_render = not keep
    return old


def _restore_render_visibility(old):
    for obj, hidden in old.items():
        if obj.name in bpy.context.scene.objects:
            obj.hide_render = hidden


def render_outputs(config, camera):
    samples = 12 if config.quality == "final" else 3
    base.aim(camera, (-1.5, 3.0, 83.0), (31.5, -46.5, 2.1), 35)
    base.render(
        config.output / "integrated_leisure_precinct_overview.png", (1280, 720), samples
    )

    base.aim(camera, (2.0, -31.0, 64.0), (31.0, -64.0, 2.3), 43)
    base.render(
        config.output / "gymnasium_athletics_north_south_plan.png", (1280, 720), samples
    )

    base.aim(camera, (13.2, -38.0, 7.6), (21.6, -54.0, 1.1), 52)
    base.render(
        config.output / "sports_campus_west_promenade.png", (1280, 720), samples
    )

    if config.quality == "final":
        base.aim(camera, (6.8, -61.0, 19.0), (31.0, -75.3, 1.0), 50)
        base.render(
            config.output / "relocated_athletics_ground_detail.png", (1280, 720), 14
        )
        base.aim(camera, (14.0, -33.0, 14.0), (39.7, -53.0, 5.0), 52)
        base.render(config.output / "integrated_gymnasium_arrival.png", (1280, 720), 14)


def main():
    config = args()
    config.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(config.input), load_ui=False)
    root = bpy.data.collections.get("all44_10:COURT_PLAYGROUND_REBUILD")
    if root is None:
        raise RuntimeError(
            "ALL44-13 focused generation requires the ALL44-10 production leisure root"
        )

    held_modifiers = []
    for obj in bpy.context.scene.objects:
        for modifier in obj.modifiers:
            if modifier.type == "NODES" and modifier.show_viewport:
                modifier.show_viewport = False
                held_modifiers.append(modifier)
    _site, audit = install_integrated_leisure_precinct(root)
    audit["focused_viewport_modifiers_held_paused_until_save"] = len(held_modifiers)
    old_visibility = _focused_render_visibility()
    try:
        render_outputs(config, bpy.context.scene.camera)
    finally:
        _restore_render_visibility(old_visibility)
    if not config.skip_save:
        for modifier in held_modifiers:
            modifier.show_viewport = True

    blend_path = config.output / "urban_v3_all44_13.blend"
    bpy.context.scene["c2w_leisure_generator"] = "generate_urban_v3_all44_13.py"
    bpy.context.scene["c2w_leisure_revision"] = "urban_v3_all44_13"
    bpy.context.scene[
        "c2w_leisure_program"
    ] = "basketball, playground, civic gymnasium and athletics ground"
    bpy.context.scene[
        "c2w_layout_policy"
    ] = "south-only expansion with connected north-south campus"
    bpy.context.scene["c2w_source_level_generation"] = True
    if not config.skip_save:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    render_names = [
        "integrated_leisure_precinct_overview.png",
        "gymnasium_athletics_north_south_plan.png",
        "sports_campus_west_promenade.png",
    ]
    if config.quality == "final":
        render_names.extend(
            (
                "relocated_athletics_ground_detail.png",
                "integrated_gymnasium_arrival.png",
            )
        )
    stats = {
        "output": str(blend_path),
        "input": str(config.input),
        "quality": config.quality,
        "source_level_generator": True,
        "pipeline_interface": "add_service_building_details(materials, root)",
        "retained_all44_10_basketball_and_playground": True,
        "integrated_all44_11_athletics_generator": True,
        "integrated_all44_12_gymnasium_generator": True,
        "east_west_expansion_m": 0.0,
        "southward_expansion_m": audit["southward_expansion_m"],
        "render_outputs": render_names,
        "integrated_leisure_audit": audit,
        "skip_save": config.skip_save,
        "total_seconds": round(time.perf_counter() - started, 3),
        "blend_file_bytes": blend_path.stat().st_size
        if blend_path.exists() and not config.skip_save
        else None,
    }
    (config.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2, ensure_ascii=False),
        encoding="utf8",
    )
    print("ALL44_13_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

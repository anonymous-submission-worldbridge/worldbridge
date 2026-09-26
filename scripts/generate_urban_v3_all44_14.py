"""ALL44-14: east-west integrated production leisure and sports precinct.

This source generator keeps the complete ALL44-10 basketball/playground zone
and installs the real ALL44-11 athletics ground and ALL44-12 civic gymnasium
from their source generators.  Unlike ALL44-13, the established north/south
planning envelope is retained: the gymnasium and athletics ground are moved
east into two new campus bands.  A constructed L-shaped accessible route links
the retained court gate to an east-west promenade serving both new facilities.

``add_service_building_details`` is the production hook consumed by
``generate_urban_v1_full_01.py``.  The focused entry opens ALL44-10 only as a
shared source-authored base; no geometry is merged from later demonstration
Blend files.
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
import generate_urban_v3_all44_13 as construction


INPUT = (
    ROOT
    / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_10/urban_v3_all44_10.blend"
)
OUTPUT = ROOT / "infinigen/outputs/outdoor_part_demo/urban_v3_all44_14"
PREFIX = "all44_14:"
SITE_NAME = PREFIX + "INTEGRATED_EAST_WEST_SPORTS_CAMPUS"

# Preserve the complete original north/south envelope.  Capacity is added only
# on the open east side, avoiding the road and commercial parcel to the west.
ORIGINAL_LEISURE_BOUNDS = (9.50, 54.40, -41.90, -9.50)
GYMNASIUM_CENTER = Vector((73.70, -25.50, gymnasium.STADIUM_CENTER.z))
GYMNASIUM_TRANSLATION = GYMNASIUM_CENTER - gymnasium.STADIUM_CENTER
GYMNASIUM_BOUNDS = (
    GYMNASIUM_CENTER.x - gymnasium.EAVE_RX,
    GYMNASIUM_CENTER.x + gymnasium.EAVE_RX,
    GYMNASIUM_CENTER.y - gymnasium.EAVE_RY,
    GYMNASIUM_CENTER.y + gymnasium.EAVE_RY,
)
ATHLETICS_CENTER = Vector((112.70, -25.50, athletics.GROUND_CENTER.z))
ATHLETICS_TRANSLATION = ATHLETICS_CENTER - athletics.GROUND_CENTER
ATHLETICS_BOUNDS = (
    athletics.SITE_BOUNDS[0] + ATHLETICS_TRANSLATION.x,
    athletics.SITE_BOUNDS[1] + ATHLETICS_TRANSLATION.x,
    athletics.SITE_BOUNDS[2] + ATHLETICS_TRANSLATION.y,
    athletics.SITE_BOUNDS[3] + ATHLETICS_TRANSLATION.y,
)
EXPANDED_LEISURE_BOUNDS = (9.50, 135.20, -41.90, -9.50)

# Stable ALL44-10 regional interfaces remain available to the full-city build.
base = retained.base
remove_old_court_playground = retained.remove_old_court_playground
tune_retained_materials = retained.tune_retained_materials
create_shared_materials = retained.create_shared_materials
generate_real_turf = retained.generate_real_turf
generate_playground = retained.generate_playground
populate_playground_details = retained.populate_playground_details


def args():
    values = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--quality", choices=("test", "final"), default="final")
    parser.add_argument("--skip-save", action="store_true")
    return parser.parse_args(values)


def _configure_construction_helpers():
    """Reuse the audited ALL44-13 civil assembly helpers under this revision."""
    construction.PREFIX = PREFIX


def campus_materials():
    _configure_construction_helpers()
    return construction.campus_materials()


def _cube(*values, **keywords):
    _configure_construction_helpers()
    return construction._cube(*values, **keywords)


def _instance(*values, **keywords):
    _configure_construction_helpers()
    return construction._instance(*values, **keywords)


def clear_stale_revision():
    _configure_construction_helpers()
    return construction.clear_stale_revision()


def _set_geometry_nodes_viewport(modifiers, enabled):
    """Toggle dense scatter graphs while their source scene is not active.

    Blender otherwise evaluates the multi-gigabyte source dependency graph
    after every individual RNA assignment.  Switching to a temporary empty
    scene batches the invalidation, then the source scene evaluates once when
    it becomes active again.
    """
    if not modifiers:
        return
    source_scene = bpy.context.scene
    window = bpy.context.window
    toggle_scene = (
        bpy.data.scenes.new(PREFIX + "DEPENDENCY_TOGGLE_CONTEXT") if window else None
    )
    if window:
        window.scene = toggle_scene
    try:
        for modifier in modifiers:
            modifier.show_viewport = enabled
    finally:
        if window:
            window.scene = source_scene
            bpy.data.scenes.remove(toggle_scene)


def _pause_geometry_nodes_viewport():
    modifiers = [
        modifier
        for obj in bpy.context.scene.objects
        for modifier in obj.modifiers
        if modifier.type == "NODES" and modifier.show_viewport
    ]
    _set_geometry_nodes_viewport(modifiers, False)
    return modifiers


def _translate_site(site, delta, center, policy, exclusions=()):
    """Translate authored site objects while reusable masters remain local."""
    moved = 0
    retained_in_place = 0
    for obj in list(site.objects):
        if any(fragment in obj.name for fragment in exclusions):
            retained_in_place += 1
            continue
        obj.location += delta
        moved += 1
    site["c2w_world_translation_m"] = list(delta)
    site["c2w_replanned_center"] = list(center)
    site["c2w_layout_policy"] = policy
    site["c2w_original_connection_objects_retained_in_place"] = retained_in_place
    return moved, retained_in_place


def _paver_field(site, materials, name, bounds, columns, rows, axis):
    x0, x1, y0, y1 = bounds
    cell_x = (x1 - x0) / columns
    cell_y = (y1 - y0) / rows
    count = 0
    for row in range(rows):
        for column in range(columns):
            offset = (cell_x * 0.14 if row % 2 else 0.0) if axis == "east_west" else 0.0
            x = min(x0 + (column + 0.5) * cell_x + offset, x1 - cell_x * 0.48)
            y = y0 + (row + 0.5) * cell_y
            material = (
                materials["paver_b"]
                if (row * 7 + column * 3) % 19 == 0
                else materials["paver_a"]
            )
            _cube(
                f"{name}_jointed_granite_paver_{row:02d}_{column:02d}",
                (x, y, 0.235),
                (cell_x - 0.027, cell_y - 0.027, 0.070),
                material,
                site,
                0.006,
            )
            count += 1
    return count


def _built_route_segment(site, materials, name, bounds, columns, rows, axis):
    x0, x1, y0, y1 = bounds
    _cube(
        f"{name}_compacted_subbase",
        ((x0 + x1) / 2, (y0 + y1) / 2, 0.09),
        (x1 - x0 + 0.24, y1 - y0 + 0.24, 0.18),
        materials["subbase"],
        site,
        0.025,
    )
    _cube(
        f"{name}_bedding_course",
        ((x0 + x1) / 2, (y0 + y1) / 2, 0.18),
        (x1 - x0, y1 - y0, 0.06),
        materials["bedding"],
        site,
        0.018,
    )
    return _paver_field(site, materials, name, bounds, columns, rows, axis)


def _build_east_west_campus(root, materials):
    site = bpy.data.collections.new(SITE_NAME)
    root.children.link(site)
    site["c2w_semantic_zone"] = "continuous accessible east-west public sports campus"
    site["c2w_construction_system"] = (
        "compacted granular formation, permeable resin-bound aggregate, individually jointed granite "
        "pavers, precast edge restraints, slot drainage, tactile thresholds and production street furniture"
    )

    # A two-course civil platform joins the ALL44-10 constructed edge at
    # x=47.82 and continues through the east extension.  Starting at the legal
    # parcel limit (x=54.40) would leave a 6.58 m undefined strip beneath the
    # accessible L-link because the retained wearing surface ends earlier.
    # This is volumetric infill below all authored facility wearing surfaces.
    campus_x0, campus_x1 = 47.82, 135.12
    campus_y0, campus_y1 = -41.82, -9.58
    _cube(
        "east_extension_compacted_formation_layer",
        ((campus_x0 + campus_x1) / 2, (campus_y0 + campus_y1) / 2, 0.035),
        (campus_x1 - campus_x0, campus_y1 - campus_y0, 0.11),
        materials["subbase"],
        site,
        0.035,
    )
    _cube(
        "east_extension_permeable_aggregate_wearing_course",
        ((campus_x0 + campus_x1) / 2, (campus_y0 + campus_y1) / 2, 0.105),
        (campus_x1 - campus_x0 - 0.16, campus_y1 - campus_y0 - 0.16, 0.06),
        materials["campus_surface"],
        site,
        0.028,
    )

    # The L-shaped route starts at the retained court's real south gate, turns
    # north in the clear strip west of the gymnasium, then runs east along both
    # public forecourts to the athletics ground's west north-edge gate.
    paver_count = 0
    paver_count += _built_route_segment(
        site,
        materials,
        "court_gate_east_spur",
        (42.50, 56.70, -41.25, -38.65),
        22,
        4,
        "east_west",
    )
    paver_count += _built_route_segment(
        site,
        materials,
        "west_arrival_north_link",
        (55.35, 57.85, -39.95, -12.05),
        4,
        42,
        "north_south",
    )
    paver_count += _built_route_segment(
        site,
        materials,
        "east_west_civic_promenade",
        (56.55, 101.85, -14.30, -11.30),
        70,
        5,
        "east_west",
    )

    # Precast restraints define the main promenade without using a flat strip.
    for side, y in (("north", -11.16), ("south", -14.44)):
        _cube(
            f"east_west_promenade_precast_edge_restraint_{side}",
            (79.20, y, 0.22),
            (45.58, 0.18, 0.28),
            materials["curb"],
            site,
            0.018,
        )
    for side, x in (("west", 55.21), ("east", 57.99)):
        _cube(
            f"north_link_precast_edge_restraint_{side}",
            (x, -26.0, 0.22),
            (0.18, 27.98, 0.28),
            materials["curb"],
            site,
            0.018,
        )

    # A continuous slot drain follows the south edge of the long axis.  Each
    # grate bar is manufactured geometry rather than a texture or painted line.
    drain_y = -14.69
    _cube(
        "east_west_promenade_slot_drain_channel",
        (79.20, drain_y, 0.205),
        (45.30, 0.22, 0.20),
        materials["drain"],
        site,
        0.015,
    )
    grate_count = 0
    for index in range(112):
        x = 56.78 + index * (44.84 / 111)
        _cube(
            f"east_west_promenade_drain_grate_bar_{index:03d}",
            (x, drain_y, 0.317),
            (0.045, 0.18, 0.024),
            materials["steel"],
            site,
            0.004,
        )
        grate_count += 1

    # Tactile thresholds identify the retained-court and athletics entrances.
    tactile_count = 0
    for zone, x0, y0, transpose in (
        ("court_gate", 41.53, -39.05, False),
        ("athletics_gate", 99.72, -15.10, True),
    ):
        for row in range(2):
            for column in range(6):
                x = x0 + (row * 0.29 if transpose else column * 0.39)
                y = y0 + (column * 0.39 if transpose else row * 0.29)
                _cube(
                    f"{zone}_tactile_paver_{row:02d}_{column:02d}",
                    (x, y, 0.282),
                    (0.25 if transpose else 0.35, 0.35 if transpose else 0.25, 0.045),
                    materials["tactile"],
                    site,
                    0.006,
                )
                tactile_count += 1

    # Reuse verified detailed public-realm masters already authored by ALL44-10.
    shared_instances = 0
    lamp = bpy.data.collections.get("all44_10:MASTER_LAMP")
    bench = bpy.data.collections.get("all44_10:MASTER_EDGE_BENCH")
    bin_master = bpy.data.collections.get("all44_10:MASTER_BIN")
    if lamp:
        for index, x in enumerate((59.4, 72.8, 86.2, 99.2)):
            _instance(
                site,
                lamp,
                f"promenade_area_light_{index:02d}",
                (x, -12.02, 0.31),
                math.pi,
            )
            shared_instances += 1
    if bench:
        for index, x in enumerate((63.7, 83.4, 96.0)):
            _instance(
                site,
                bench,
                f"promenade_rest_bench_{index:02d}",
                (x, -12.25, 0.30),
                math.pi / 2,
            )
            shared_instances += 1
    if bin_master:
        for index, x in enumerate((64.5, 96.8)):
            _instance(
                site,
                bin_master,
                f"promenade_waste_and_recycling_bin_{index:02d}",
                (x, -12.02, 0.30),
                math.pi,
            )
            shared_instances += 1

    # The wayfinding element is a fabricated multi-part assembly with footing,
    # twin posts, folded enamel panel, raised direction bars and weather cap.
    _cube(
        "wayfinding_pylon_footing",
        (56.55, -11.90, 0.13),
        (0.72, 0.55, 0.26),
        materials["curb"],
        site,
        0.06,
    )
    for y in (-12.08, -11.72):
        _cube(
            "wayfinding_pylon_steel_post",
            (56.55, y, 1.34),
            (0.075, 0.075, 2.36),
            materials["steel"],
            site,
            0.012,
        )
    _cube(
        "wayfinding_pylon_folded_panel",
        (56.55, -11.90, 1.70),
        (0.12, 0.82, 1.35),
        materials["sign"],
        site,
        0.045,
    )
    for index, z in enumerate((1.46, 1.76, 2.06)):
        _cube(
            f"wayfinding_pylon_raised_direction_bar_{index:02d}",
            (56.475, -11.90, z),
            (0.045, 0.56 - index * 0.06, 0.065),
            materials["letter"],
            site,
            0.012,
        )
    _cube(
        "wayfinding_pylon_weather_cap",
        (56.55, -11.90, 2.43),
        (0.18, 0.90, 0.10),
        materials["steel"],
        site,
        0.025,
    )

    return site, {
        "promenade_modular_pavers": paver_count,
        "promenade_drain_grate_bars": grate_count,
        "entrance_tactile_pavers": tactile_count,
        "shared_public_realm_asset_instances": shared_instances,
        "continuous_east_extension_ground_layers": 2,
        "retained_edge_to_extension_infill_width_m": 6.58,
        "constructed_route_segments": 3,
    }


def _mesh_has_authored_extent(obj):
    if obj.type != "MESH" or not obj.data or not obj.data.vertices:
        return True
    extents = []
    for axis in range(3):
        values = [vertex.co[axis] for vertex in obj.data.vertices]
        extents.append(max(values) - min(values))
    return sum(extent > 1e-6 for extent in extents) >= 2


def _audit(
    root,
    athletics_site,
    gymnasium_site,
    connector_site,
    connector_stats,
    athletics_moved,
    gymnasium_moved,
    gym_connection_retained,
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
        "athletics_site_objects_translated": athletics_moved,
        "athletics_center_world": list(ground.location) if ground else [],
        "gymnasium_present": stadium is not None,
        "gymnasium_is_reusable_collection_instance": bool(
            stadium
            and stadium.instance_type == "COLLECTION"
            and stadium.instance_collection
        ),
        "gymnasium_site_objects_translated": gymnasium_moved,
        "gymnasium_original_court_connection_objects_retained": gym_connection_retained,
        "gymnasium_center_world": list(stadium.location) if stadium else [],
        "connector_collection_present": connector_site.name in bpy.data.collections,
        **connector_stats,
        "program_world_bounds": {
            "retained_western_leisure": list(ORIGINAL_LEISURE_BOUNDS),
            "central_gymnasium": [round(value, 3) for value in GYMNASIUM_BOUNDS],
            "eastern_athletics": [round(value, 3) for value in ATHLETICS_BOUNDS],
            "integrated_leisure_envelope": list(EXPANDED_LEISURE_BOUNDS),
        },
        "layout_clearances_m": {
            "retained_zone_to_gymnasium": round(
                GYMNASIUM_BOUNDS[0] - ORIGINAL_LEISURE_BOUNDS[1], 3
            ),
            "gymnasium_to_athletics": round(
                ATHLETICS_BOUNDS[0] - GYMNASIUM_BOUNDS[1], 3
            ),
            "gymnasium_to_original_south_limit": round(
                GYMNASIUM_BOUNDS[2] - ORIGINAL_LEISURE_BOUNDS[2], 3
            ),
            "gymnasium_to_original_north_limit": round(
                ORIGINAL_LEISURE_BOUNDS[3] - GYMNASIUM_BOUNDS[3], 3
            ),
            "athletics_to_original_south_limit": round(
                ATHLETICS_BOUNDS[2] - ORIGINAL_LEISURE_BOUNDS[2], 3
            ),
            "athletics_to_original_north_limit": round(
                ORIGINAL_LEISURE_BOUNDS[3] - ATHLETICS_BOUNDS[3], 3
            ),
            "athletics_to_expanded_east_limit": round(
                EXPANDED_LEISURE_BOUNDS[1] - ATHLETICS_BOUNDS[1], 3
            ),
        },
        "eastward_expansion_m": round(
            EXPANDED_LEISURE_BOUNDS[1] - ORIGINAL_LEISURE_BOUNDS[1], 3
        ),
        "westward_expansion_m": 0.0,
        "northward_expansion_m": 0.0,
        "southward_expansion_m": 0.0,
        "forbidden_degenerate_asset_names": forbidden,
        "collapsed_new_meshes": collapsed,
    }
    failures = []
    minimums = {
        "retained_basketball_court_objects": 20,
        "retained_playground_objects": 8,
        "athletics_site_objects_translated": 100,
        "gymnasium_site_objects_translated": 100,
        "gymnasium_original_court_connection_objects_retained": 20,
        "promenade_modular_pavers": 500,
        "promenade_drain_grate_bars": 100,
        "entrance_tactile_pavers": 24,
        "shared_public_realm_asset_instances": 4,
        "continuous_east_extension_ground_layers": 2,
        "retained_edge_to_extension_infill_width_m": 6.58,
        "constructed_route_segments": 3,
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
    if stadium and (stadium.location - GYMNASIUM_CENTER).length > 0.001:
        failures.append(
            f"gymnasium center mismatch: {list(stadium.location)} != {list(GYMNASIUM_CENTER)}"
        )
    if min(checks["layout_clearances_m"].values()) < 0.25:
        failures.append(f"unsafe planned clearance: {checks['layout_clearances_m']}")
    if any(
        checks[key] != 0.0
        for key in (
            "westward_expansion_m",
            "northward_expansion_m",
            "southward_expansion_m",
        )
    ):
        failures.append("expansion is not east-only")
    if forbidden:
        failures.append(f"forbidden degenerate asset names: {forbidden[:20]}")
    if collapsed:
        failures.append(f"collapsed new meshes: {collapsed[:20]}")
    if failures:
        raise RuntimeError(
            {
                "all44_14_integrated_leisure_quality_audit_failed": failures,
                "checks": checks,
            }
        )

    connector_site["c2w_quality_audit"] = json.dumps(checks, sort_keys=True)
    return {
        "pipeline_stage": "generate_urban_v3_all44_14.py",
        "campus_program": "basketball/playground + civic gymnasium + community athletics ground",
        "planning_policy": "retain north/south envelope; extend only east; separate programs with audited clearances",
        "circulation_system": "retained court gate, L-shaped accessible link and east-west civic promenade",
        "construction_policy": "real source-authored assemblies and reusable production masters; no toy, proxy, placeholder or collapsed assets",
        **checks,
    }


def install_integrated_leisure_precinct(root):
    """Install and replan the two production sports generators as one campus."""
    stage_started = time.perf_counter()
    paused_modifiers = []
    try:
        clear_stale_revision()
        print(
            f"ALL44_14_STAGE clear_stale {time.perf_counter() - stage_started:.3f}s",
            flush=True,
        )
        athletics_site, athletics_audit = athletics.install_athletics_ground(
            root, manage_viewport=False
        )
        print(
            f"ALL44_14_STAGE athletics_installed {time.perf_counter() - stage_started:.3f}s",
            flush=True,
        )
        athletics_moved, _ = _translate_site(
            athletics_site,
            ATHLETICS_TRANSLATION,
            ATHLETICS_CENTER,
            "east-translated athletics band; north/south planning envelope unchanged",
        )
        gymnasium_site, gymnasium_audit = gymnasium.install_parametric_stadium(
            root, manage_viewport=False
        )
        print(
            f"ALL44_14_STAGE gymnasium_installed {time.perf_counter() - stage_started:.3f}s",
            flush=True,
        )
        gymnasium_moved, gym_connection_retained = _translate_site(
            gymnasium_site,
            GYMNASIUM_TRANSLATION,
            GYMNASIUM_CENTER,
            "east-translated civic core; north/south planning envelope unchanged",
            exclusions=("court_to_stadium_passage", "court_passage_"),
        )
        connector_site, connector_stats = _build_east_west_campus(
            root, campus_materials()
        )
        print(
            f"ALL44_14_STAGE campus_connector_built {time.perf_counter() - stage_started:.3f}s",
            flush=True,
        )
        audit = _audit(
            root,
            athletics_site,
            gymnasium_site,
            connector_site,
            connector_stats,
            athletics_moved,
            gymnasium_moved,
            gym_connection_retained,
        )
        print(
            f"ALL44_14_STAGE integrated_audit_passed {time.perf_counter() - stage_started:.3f}s",
            flush=True,
        )
        audit["athletics_source_audit"] = athletics_audit
        audit["gymnasium_source_audit"] = gymnasium_audit
        audit["viewport_scatter_modifiers_paused_during_assembly"] = len(
            paused_modifiers
        )
        root["all44_14_integrated_leisure_audit"] = json.dumps(audit, sort_keys=True)
        root["all44_14_athletics_site"] = athletics_site.name
        root["all44_14_gymnasium_site"] = gymnasium_site.name
        return connector_site, audit
    finally:
        _set_geometry_nodes_viewport(paused_modifiers, True)


def add_service_building_details(materials, root):
    """Production full-city hook for the complete integrated leisure region."""
    service_building = retained.add_service_building_details(materials, root)
    site, audit = install_integrated_leisure_precinct(root)
    root["all44_14_retained_service_building"] = service_building.name
    root["all44_14_integrated_leisure_audit"] = json.dumps(audit, sort_keys=True)
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
    base.aim(camera, (25.0, 32.0, 108.0), (72.0, -25.5, 2.0), 39)
    base.render(
        config.output / "integrated_leisure_east_west_overview.png",
        (1280, 720),
        samples,
    )

    base.aim(camera, (72.0, -25.5, 112.0), (72.0, -25.5, 1.2), 36)
    base.render(config.output / "east_west_campus_plan.png", (1280, 720), samples)

    base.aim(camera, (48.0, -3.0, 13.5), (77.5, -13.2, 1.25), 53)
    base.render(config.output / "east_west_civic_promenade.png", (1280, 720), samples)

    if config.quality == "final":
        base.aim(camera, (91.0, -5.0, 20.0), (112.7, -25.5, 1.0), 50)
        base.render(
            config.output / "eastern_athletics_ground_detail.png", (1280, 720), 14
        )
        base.aim(camera, (54.0, -1.5, 15.0), (73.7, -17.0, 4.0), 52)
        base.render(config.output / "central_gymnasium_arrival.png", (1280, 720), 14)


def main():
    config = args()
    config.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(
        filepath=str(config.input), load_ui=False, use_scripts=False
    )
    root = bpy.data.collections.get("all44_10:COURT_PLAYGROUND_REBUILD")
    if root is None:
        raise RuntimeError(
            "ALL44-14 focused generation requires the ALL44-10 production leisure root"
        )

    held_modifiers = []
    _site, audit = install_integrated_leisure_precinct(root)
    print(
        f"ALL44_14_STAGE focused_install_complete {time.perf_counter() - started:.3f}s",
        flush=True,
    )
    audit["focused_viewport_modifiers_held_paused_until_save"] = len(held_modifiers)
    old_visibility = _focused_render_visibility()
    try:
        print("ALL44_14_STAGE renders_started", flush=True)
        render_outputs(config, bpy.context.scene.camera)
        print(
            f"ALL44_14_STAGE renders_complete {time.perf_counter() - started:.3f}s",
            flush=True,
        )
    finally:
        _restore_render_visibility(old_visibility)
    if not config.skip_save:
        _set_geometry_nodes_viewport(held_modifiers, True)

    blend_path = config.output / "urban_v3_all44_14.blend"
    bpy.context.scene["c2w_leisure_generator"] = "generate_urban_v3_all44_14.py"
    bpy.context.scene["c2w_leisure_revision"] = "urban_v3_all44_14"
    bpy.context.scene[
        "c2w_leisure_program"
    ] = "basketball, playground, civic gymnasium and athletics ground"
    bpy.context.scene[
        "c2w_layout_policy"
    ] = "east-only expansion with connected east-west campus"
    bpy.context.scene["c2w_source_level_generation"] = True
    if not config.skip_save:
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path), compress=True)

    render_names = [
        "integrated_leisure_east_west_overview.png",
        "east_west_campus_plan.png",
        "east_west_civic_promenade.png",
    ]
    if config.quality == "final":
        render_names.extend(
            ("eastern_athletics_ground_detail.png", "central_gymnasium_arrival.png")
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
        "eastward_expansion_m": audit["eastward_expansion_m"],
        "westward_expansion_m": audit["westward_expansion_m"],
        "northward_expansion_m": audit["northward_expansion_m"],
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
    print("ALL44_14_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

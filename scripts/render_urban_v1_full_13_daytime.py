#!/usr/bin/env python3
"""Full-13 camera contract and physical daylight renderer.

The resource-safe layer renderer imports this module, so direct and layered
renders share exactly the same 80 cameras, 1920x1080 raster, Nishita sky, sun,
color management, and Eevee PBR settings.
"""

from __future__ import annotations

import importlib.util
import math
import os
import sys
from dataclasses import replace
from pathlib import Path

import bpy


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_13"
CITY_ROOT = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
BASE_PATH = ROOT / "scripts/render_urban_v1_full_12_daytime.py"
os.environ.setdefault(
    "C2W_FULL12_RENDER_ENGINE", os.environ.get("C2W_FULL13_RENDER_ENGINE", "EEVEE")
)
os.environ.setdefault(
    "C2W_FULL12_RENDER_RESOLUTION",
    os.environ.get("C2W_FULL13_RENDER_RESOLUTION", "1920x1080"),
)
os.environ.setdefault(
    "C2W_FULL12_EEVEE_SAMPLES", os.environ.get("C2W_FULL13_EEVEE_SAMPLES", "64")
)
os.environ.setdefault("C2W_FULL12_EEVEE_SHADOW_POOL_MB", "1024")
os.environ.setdefault("C2W_FULL12_EEVEE_SHADOW_RESOLUTION_SCALE", "0.5")


spec = importlib.util.spec_from_file_location("full13_renderer_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.REVISION = REVISION
base.CITY_ROOT = CITY_ROOT
base.BLEND_PATH = CITY_ROOT / f"{REVISION}.blend"
base.LAYOUT_PATH = CITY_ROOT / "layout_plan.json"
base.OUT = CITY_ROOT / "renders"
base.MANIFEST = base.OUT / "render_manifest.json"
base.PANORAMA_AUDIT = CITY_ROOT / "panorama_audit.json"
base.PROJECTION_AUDIT = CITY_ROOT / "mesh_projection_audit.json"
base.AUDIT_DIR = base.OUT / "audit"
base.TEMP_PREFIX = "__full13_daytime_tmp__"
base.CAMERA_COMPOSITION_REVISION = "full13_semantic_visibility_v1"


def _replace_shot(name: str, **changes):
    for index, shot in enumerate(base.SHOTS):
        if shot.name == name:
            base.SHOTS[index] = replace(shot, **changes)
            return
    raise KeyError(name)


road_ids = (
    "full13_road_main_m54.5_0",
    "full13_road_east_residential_intersection",
    "full13_road_diagonal_connector_01",
    "full13_road_diagonal_connector_02",
)
base.ZONE_IDS["roads"] = road_ids
base.ZONE_NEAR["roads"] = road_ids[0]
for index, shot in enumerate(base.SHOTS):
    if shot.name in {"roads_far", "roads_near", "continuous_road_far"}:
        base.SHOTS[index] = replace(shot, placement_ids=road_ids)

# The inherited near-vertical (x=+0.001,y=-0.001) direction rotated the
# orthographic footprint by 45 degrees, wasting three quarters of the native
# frame on blue sky.  Align the genuine orthographic city camera with the
# developed street axes while retaining the full source city and surroundings.
_replace_shot(
    "city_top_down_coverage",
    direction=(0.0, 0.001, 1.0),
    margin=1.035,
    description="Axis-aligned, entire-city true orthographic rooftop coverage and connected street hierarchy",
)

# Explicit relationship and road cameras are in uncluttered carriageway/public
# space and aim at both named targets, never at a facade back or arbitrary AABB.
_replace_shot(
    "school_library_shared_street",
    placement_ids=("education_school_north", "education_library_south"),
    # Frame the actual facing entrances from within their common public
    # approach, rather than showing a distant superblock and pole forest.
    # School occupies x<=-65; library starts at x=-7; the road at x=-54.5
    # links both entrances, with its buildings around the target y=140.
    world_camera=(-54.5, 40.0, 11.0),
    world_target=(-54.5, 140.0, 5.0),
    lens=23.0,
    description="Human-scale shared-street approach resolving both school and library façades and entrances",
)
# Photograph the actual surveyed 58 x 33 m hydraulic shoreline, not the
# complete 130 x 110 m asset AABB that made the lake occupy only a few pixels
# in the old high overview.  Elevated shoreline, water, two approach piers
# and the built retaining edge stay visible at one genuine aerial viewpoint.
_replace_shot(
    "artificial_lake_high",
    anchor_id="education_artificial_lake_civic_enclosure",
    source_camera=(0.0, -55.0, 33.0),
    source_target=(0.0, 0.0, 0.0),
    lens=36.0,
    description="Elevated complete physical shoreline, deep PBR water and accessible piers in one photograph",
)
# The old 31 m / 38 mm cameras spread individual exercise machines over an
# eighty-metre square paved compound; each machine was reduced to a handful
# of pixels.  Keep enough actual surrounding equipment and circulation while
# resolving the articulated machine at useful real walking distance.
_replace_shot(
    "park_fitness_near",
    source_camera=(0.0, -24.0, 3.2),
    source_target=(0.0, 0.0, 1.25),
    lens=69.0,
    description="Close real walking-eye appraisal of assembled park exercise apparatus and safe circulation",
)
_replace_shot(
    "leisure_fitness_near",
    source_camera=(4.0, -24.0, 3.2),
    source_target=(4.0, 0.0, 1.25),
    lens=69.0,
    description="Close leisure exercise machinery, surrounding use clearance and tiled public realm",
)
_replace_shot(
    "road_intersection_street_level",
    placement_ids=(road_ids[0],),
    world_camera=(-105.0, -12.5, 4.0),
    world_target=(-54.5, 0.0, 0.9),
    lens=46.0,
)
_replace_shot(
    "crosswalk_oblique",
    placement_ids=(road_ids[0],),
    world_camera=(-102.0, -55.0, 22.0),
    world_target=(-54.5, 0.0, 0.2),
    lens=52.0,
)
_replace_shot(
    "diagonal_road_near",
    placement_ids=(
        "full13_road_diagonal_connector_01",
        "full13_road_diagonal_connector_02",
    ),
    world_camera=(160.0, 4.0, 42.0),
    world_target=(40.0, -56.0, 0.8),
    lens=46.0,
    description="Both exact diagonal modules, their central start and commercial-street termination",
)

# Pull previously failed target cameras into clear sidewalks or courtyards.
_replace_shot(
    "hospital_outskirts_atrium_near",
    source_camera=(-98.0, -62.0, 10.0),
    source_target=(-72.0, 2.0, 5.5),
    lens=42.0,
    description="Pulled-back public approach showing the complete glazed atrium, canopy, entrance apron, and brick hospital context",
)
_replace_shot(
    "police_library_near",
    placement_ids=("police_near_library", "education_library_south"),
    world_camera=(-120.0, 205.0, 25.0),
    world_target=(10.0, 225.0, 5.0),
    source_camera=None,
    source_target=None,
    anchor_id=None,
    lens=38.0,
    description="Southwest relationship view showing the police front and adjacent library west frontage across their shared public-space gap",
)
_replace_shot(
    "artificial_lake_pavilion_near",
    source_camera=(-34.0, 42.0, 7.5),
    source_target=(-4.0, 2.0, 1.0),
    lens=42.0,
    description="Lakeside pavilion in the foreground with its accessible path, continuous shore, and water surface visible together",
)
_replace_shot(
    "artificial_lake_shore_near",
    source_camera=(-35.0, -15.0, 2.2),
    source_target=(-18.0, 3.0, 0.25),
    lens=58.0,
)
_replace_shot(
    "park_sculpture_near",
    world_camera=(-236.35, -82.0, 6.0),
    world_target=(-236.35, -45.0, 1.8),
    source_camera=None,
    source_target=None,
    anchor_id=None,
    lens=50.0,
    description="Sculpture clearing from the unobstructed south approach outside the tree canopy",
)
_replace_shot(
    "residential_delivery_03_delivery_station_near",
    source_camera=(30.0, -18.0, 5.0),
    source_target=(11.6, -3.5, 1.8),
    lens=50.0,
)
_replace_shot(
    "atm_row_front",
    anchor_id="commercial_atm_five_machine_row",
    source_camera=(0.0, -12.4, 2.48),
    source_target=(0.0, 0.0, 1.11),
    world_camera=None,
    world_target=None,
    lens=52.0,
    description="Exact source-authored front view of five complete ATM interfaces, including screens, keypads, card slots, receipts, and housings",
)
_replace_shot(
    "interior_residential_native",
    source_camera=(-34.63, -22.69, 1.65),
    source_target=(-41.5, -23.4, 1.5),
    lens=35.0,
    description="Level 1.65 m eye-height native apartment view showing living, kitchen, sanitary fixtures, furniture, doors, and circulation",
)
_replace_shot(
    "interior_commercial_bar",
    source_camera=(-49.0, -3.0, 2.25),
    source_target=(-47.0, -10.5, 1.55),
    lens=52.0,
    description="Source-validated bar-room composition showing service counter, taps, stools, tables, seating, bottle wall, entrance, and floor",
)

# Four new public interiors use local coordinates in their generated room
# masters.  Camera eye heights are 1.6 m and show room envelope plus program.
_replace_shot(
    "interior_school_cafeteria_threshold",
    placement_ids=("full13_semantic_interior_school_cafeteria",),
    anchor_id="full13_semantic_interior_school_cafeteria",
    source_camera=(0.0, -11.2, 1.60),
    source_target=(0.0, 2.2, 1.25),
    world_camera=None,
    world_target=None,
    lens=22.0,
    interior=True,
    description="Daylit cafeteria with room boundaries, serving counter, tables and chairs",
)
_replace_shot(
    "interior_library_reading_room",
    placement_ids=("full13_semantic_interior_library_reading_room",),
    anchor_id="full13_semantic_interior_library_reading_room",
    source_camera=(0.0, -10.1, 1.60),
    source_target=(0.0, 2.2, 1.35),
    world_camera=None,
    world_target=None,
    lens=24.0,
    interior=True,
    description="Daylit reading room showing book walls, tables, chairs and entrance",
)
_replace_shot(
    "interior_bank_atrium",
    placement_ids=("full13_semantic_interior_bank_atrium",),
    anchor_id="full13_semantic_interior_bank_atrium",
    source_camera=(-7.5, -7.2, 1.60),
    source_target=(1.0, 3.4, 1.30),
    world_camera=None,
    world_target=None,
    lens=24.0,
    interior=True,
    description="Oblique bank atrium at eye height showing teller glazing, full counter, information island, queue rails, visitor seating, envelope, and entrance direction",
)
_replace_shot(
    "interior_hospital_lobby",
    placement_ids=("full13_semantic_interior_hospital_lobby",),
    anchor_id="full13_semantic_interior_hospital_lobby",
    # Avoid the planter at (-7.25,-8.7): the previous eye at x=-7 put its
    # leaf mesh against the near plane, masking a quarter of the lobby.
    source_camera=(-3.1, -10.2, 1.60),
    source_target=(1.0, 4.1, 1.30),
    world_camera=None,
    world_target=None,
    lens=25.0,
    interior=True,
    description="Oblique hospital lobby at eye height showing reception monitors, waiting groups, accessible circulation, wayfinding, room envelope, and entrance direction",
)

base.SHOT_BY_NAME = {shot.name: shot for shot in base.SHOTS}
if len(base.SHOTS) != 80 or len(base.SHOT_BY_NAME) != 80:
    raise RuntimeError("Full-13 must retain exactly 80 unique delivery views")


_base_configure_daylight = base.configure_daylight


def configure_daylight(scene: bpy.types.Scene):
    settings, daylight = _base_configure_daylight(scene)
    if scene.render.engine not in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        raise RuntimeError("Full-13 final rasterization requires Eevee PBR")
    world = scene.world
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    # Blender 5.1 exposes the physical Nishita successor as multiple-
    # scattering; older 4.x builds expose it under the NISHITA enum.
    try:
        sky.sky_type = "MULTIPLE_SCATTERING"
    except TypeError:
        sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42.0)
    sky.sun_rotation = math.radians(218.0)
    sky.air_density = 1.0
    # Blender 5.1's multiple-scattering sky removed the old Nishita
    # ``dust_density`` RNA property.  Keep the atmospheric tuning when the
    # runtime supports it, without silently abandoning the physical sky on
    # newer builds.
    if hasattr(sky, "dust_density"):
        sky.dust_density = 0.32
    background.inputs["Strength"].default_value = 0.38
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.10
    for obj in scene.objects:
        if obj.type == "LIGHT" and obj.name.endswith(":sun"):
            obj.data.energy = 2.15
            obj.data.angle = math.radians(1.2)
            obj.rotation_euler = (
                math.radians(48),
                math.radians(-14),
                math.radians(218),
            )
    settings["world_shader"] = "physical multiple-scattering daylight sky"
    settings["final_pbr_required"] = True
    settings["workbench_final_allowed"] = False
    daylight["sky_model"] = "MULTIPLE_SCATTERING_PHYSICAL"
    daylight["sun_elevation_deg"] = 42.0
    daylight["sun_angular_diameter_deg"] = 1.2
    return settings, daylight


base.configure_daylight = configure_daylight

_base_configure_camera = base.configure_camera
_mesh_bounds_cache = {}


def _render_mesh_bounds(camera):
    """Cache exact per-child mesh bounds for the active temporary layer."""
    scenes = camera.users_scene
    if not scenes:
        return []
    scene = scenes[0]
    key = scene.as_pointer()
    cached = _mesh_bounds_cache.get(key)
    object_count = len(scene.objects)
    if cached is not None and cached[0] == object_count:
        return cached[1]
    result = []
    for obj in scene.objects:
        if obj is camera or obj.type != "MESH" or obj.hide_render or obj.data is None:
            continue
        try:
            points = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
        except (ReferenceError, RuntimeError, TypeError):
            continue
        result.append(
            (
                obj.name,
                obj.get("source_placement_id"),
                (
                    min(point.x for point in points),
                    min(point.y for point in points),
                    min(point.z for point in points),
                    max(point.x for point in points),
                    max(point.y for point in points),
                    max(point.z for point in points),
                ),
            )
        )
    _mesh_bounds_cache[key] = (object_count, result)
    return result


def configure_camera(camera, shot, bounds, by_id):
    record = _base_configure_camera(camera, shot, bounds, by_id)
    if shot.projection == "ORTHO":
        # Blender interprets ortho_scale as the HORIZONTAL field width with
        # sensor_fit=HORIZONTAL.  The inherited fit routine sized it as the
        # vertical field height, clipping both rotated corners of this city's
        # top-down verification raster.  Scale the camera by the native
        # 1920:1080 aspect; camera location/target and every child remain
        # unchanged, while the entire final city becomes visible in view 06.
        aspect = base.RESOLUTION[0] / base.RESOLUTION[1]
        camera.data.ortho_scale *= aspect
        record["ortho_scale"] = round(float(camera.data.ortho_scale), 4)
        record["orthographic_native_horizontal_fit"] = True
    x, y, z = record["location"]
    collisions = []
    for placement_id, placement in by_id.items():
        # Collection envelopes can contain courtyards, lakes, roads, people
        # and other intentionally open space.  Declared targets and sparse
        # distributed layers are checked against exact child bounds below.
        if placement_id in shot.placement_ids or placement.get("collision_class") in {
            "base",
            "road",
            "road_amenity",
            "river",
            "public_realm",
        }:
            continue
        lower = placement["footprint"]["min"]
        upper = placement["footprint"]["max"]
        if (
            lower[0] + 0.05 < x < upper[0] - 0.05
            and lower[1] + 0.05 < y < upper[1] - 0.05
            and lower[2] + 0.05 < z < upper[2] - 0.05
        ):
            collisions.append(placement_id)
    record["camera_aabb_preflight"] = {
        "method": "solid non-target final-placement 3D bounds, followed by exact per-layer child-mesh bounds",
        "colliding_placement_ids": collisions,
        "pass": not collisions,
    }
    if collisions:
        raise RuntimeError(
            f"Camera {shot.name} lies inside final placement bounds: {collisions}"
        )

    mesh_collisions = []
    for object_name, placement_id, box in _render_mesh_bounds(camera):
        if shot.interior and placement_id in shot.placement_ids:
            continue
        epsilon = 0.015
        if (
            box[0] + epsilon < x < box[3] - epsilon
            and box[1] + epsilon < y < box[4] - epsilon
            and box[2] + epsilon < z < box[5] - epsilon
        ):
            mesh_collisions.append(
                {"object": object_name, "placement_id": placement_id}
            )
    record["camera_mesh_aabb_preflight"] = {
        "method": "exact expanded render-child world bounds for the current layer",
        "evaluated_mesh_count": len(_render_mesh_bounds(camera)),
        "collisions": mesh_collisions,
        "declared_interior_target_excluded": bool(shot.interior),
        "pass": not mesh_collisions,
    }
    if mesh_collisions:
        raise RuntimeError(
            f"Camera {shot.name} intersects renderable child mesh bounds: {mesh_collisions[:8]}"
        )
    return record


base.configure_camera = configure_camera

# Re-export the complete shared API expected by the layer renderer.
globals().update(
    {name: value for name, value in vars(base).items() if not name.startswith("__")}
)
configure_daylight = base.configure_daylight
configure_camera = base.configure_camera
SHOTS = base.SHOTS
SHOT_BY_NAME = base.SHOT_BY_NAME


if __name__ == "__main__":
    base.main()

#!/usr/bin/env python3
"""Render publication-oriented views of the existing FULL08 city scene.

The script is intentionally read-only with respect to the source Blend.  It
creates a temporary camera and daylight rig in memory, writes the requested
frames plus a manifest, and exits without saving the scene.

Environment variables:
    C2W_PAPER_MODE         preview or final (default: preview)
    C2W_PAPER_ENGINE       EEVEE, CYCLES, or WORKBENCH (default: EEVEE)
    C2W_PAPER_DEVICE       GPU or CPU for Cycles (default: GPU)
    C2W_PAPER_RESOLUTION   WIDTHxHEIGHT (defaults: 640x360 / 2400x1350)
    C2W_PAPER_SHOTS        comma-separated shot names (default: all)
    C2W_PAPER_OUT          output directory
    C2W_PAPER_SAMPLES      Eevee/Cycles sample budget
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


import json
import math
import os
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SCENE_DIR = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_08"
SOURCE_BLEND = SCENE_DIR / "urban_v1_full_08.blend"
TEMP_PREFIX = "__full08_paper__"


@dataclass(frozen=True)
class Shot:
    name: str
    camera: tuple[float, float, float]
    target: tuple[float, float, float]
    lens: float
    description: str


# These candidates stay inside the authored districts and use tighter lenses.
# The camera axes point toward built fabric so the unbuilt tan perimeter never
# becomes part of the composition.
SHOTS = (
    Shot(
        "01_central_crossroads_close",
        (43, -51, 23),
        (0, 3, 2.5),
        60,
        "Tight oblique of the main intersection, framed entirely by buildings, roads, and the park.",
    ),
    Shot(
        "02_main_boulevard_street",
        (-3, -44, 3.8),
        (2, 22, 3.0),
        55,
        "Pedestrian-height boulevard perspective enclosed by active frontage and the distant residential skyline.",
    ),
    Shot(
        "03_crossroads_opposite",
        (-39, 43, 18),
        (0, -1, 2.4),
        60,
        "Reverse intersection view toward the commercial and leisure districts.",
    ),
    Shot(
        "04_crosswalk_geometry",
        (20, -22, 10),
        (0, 0, 0.45),
        61,
        "Close elevated view of crossings, lane markings, traffic signals, and planted corners.",
    ),
    Shot(
        "05_commercial_frontage",
        (-30, -52, 9.5),
        (-30, -25.0, 2.2),
        48,
        "Tight frontal view of the paired Fresh Mart and Corner Kitchen storefronts.",
    ),
    Shot(
        "06_fresh_mart_front",
        (-40.0, -37.0, 4.6),
        (-40.0, -25.2, 2.2),
        58,
        "Architectural close view of the Fresh Mart facade and glazing.",
    ),
    Shot(
        "07_fresh_mart_interior",
        (-40.2, -32.0, 2.45),
        (-40.4, -20.4, 1.35),
        53,
        "Eye-level view through the storefront glazing into the furnished market interior.",
    ),
    Shot(
        "08_corner_kitchen_front",
        (-24.3, -37.0, 4.7),
        (-24.3, -25.2, 2.3),
        58,
        "Architectural close view of the Corner Kitchen facade and forecourt.",
    ),
    Shot(
        "09_corner_kitchen_dining",
        (-28.0, -32.0, 2.5),
        (-27.6, -21.2, 1.3),
        54,
        "Street-level view through the restaurant glazing toward dining furniture.",
    ),
    Shot(
        "10_storefront_glass_detail",
        (-36.3, -30.5, 2.35),
        (-36.6, -23.0, 1.5),
        62,
        "Compressed material study of storefront glass, frames, and interior shelving.",
    ),
    Shot(
        "11_retail_bicycle_station",
        (-50.8, -46.0, 3.4),
        (-46.1, -39.0, 0.7),
        55,
        "Close public-realm detail of the commercial bicycle station.",
    ),
    Shot(
        "12_rear_cafe_garden",
        (-31.0, -4.0, 3.5),
        (-31.0, -12.5, 1.1),
        55,
        "Rear cafe garden and planted edge viewed from the city-facing side.",
    ),
    Shot(
        "13_rear_shared_bicycles",
        (-44.0, -7.2, 2.25),
        (-43.6, -13.25, 0.70),
        58,
        "Close rear-court view of shared bicycles and landscape details.",
    ),
    Shot(
        "14_convenience_store_corner",
        (1.0, -3.5, 5.2),
        (-12.5, -14.0, 2.4),
        56,
        "Three-quarter convenience-store corner composition across the intersection.",
    ),
    Shot(
        "15_park_sculpture_reverse",
        (47, 38, 3.5),
        (31, 29, 1.6),
        58,
        "Low reverse view of the sculpture, paths, mature trees, and city edge.",
    ),
    Shot(
        "16_park_sculpture_diagonal",
        (50, 47, 4.3),
        (31, 29, 1.7),
        58,
        "Diagonal sculpture view framed by tree trunks and planted paths.",
    ),
    Shot(
        "17_park_plaza_elevated",
        (51, 48, 20),
        (31, 30, 1.6),
        63,
        "Tight elevated landscape composition with the entire frame inside the park and urban edge.",
    ),
    Shot(
        "18_park_path_city_edge",
        (50, 29, 2.8),
        (26, 27, 1.7),
        62,
        "Pedestrian-height path perspective aimed toward surrounding buildings.",
    ),
    Shot(
        "19_park_to_crossroads",
        (49, 45, 5.5),
        (5, 7, 2.4),
        64,
        "Long park-edge view terminating at the central crossroads.",
    ),
    Shot(
        "20_basketball_court_diagonal",
        (49, -39, 4.8),
        (31, -31, 1.0),
        55,
        "Low diagonal across the complete basketball court with city fabric behind.",
    ),
    Shot(
        "21_basketball_court_reverse",
        (15, -40, 5.0),
        (31, -31, 1.0),
        55,
        "Reverse court view using the playing surface and service building to fill the frame.",
    ),
    Shot(
        "22_basketball_court_graphic",
        (49, -42, 18),
        (31, -31, 0.8),
        66,
        "Tight graphic view of court markings, hoops, and perimeter fencing.",
    ),
    Shot(
        "23_playground_front",
        (4, -6, 12),
        (15.5, -17, 1.3),
        48,
        "Elevated close view of the complete playground and its safety surfacing.",
    ),
    Shot(
        "24_playground_side",
        (7.0, -24.4, 8.2),
        (15.7, -18.3, 1.25),
        52,
        "Side view of play structures, benches, paths, and planting.",
    ),
    Shot(
        "25_service_building_front",
        (21, -2, 4.5),
        (36.8, -11.4, 2.15),
        52,
        "Tight three-quarter view of the detailed recreation service building.",
    ),
    Shot(
        "26_north_house_west_wide",
        (-52, 68, 4.5),
        (-36, 89, 3.2),
        52,
        "Wide three-quarter view of the western detached house and garden approach.",
    ),
    Shot(
        "27_north_house_center_wide",
        (-15, 67, 5.0),
        (0, 89, 3.2),
        50,
        "Wide three-quarter view of the central detached house and connected path.",
    ),
    Shot(
        "28_north_house_east_wide",
        (52, 68, 4.5),
        (36, 89, 3.2),
        52,
        "Wide three-quarter view of the eastern detached house and garden approach.",
    ),
    Shot(
        "29_north_apartment_west_wide",
        (-52, 101, 8.0),
        (-29, 119, 9.0),
        50,
        "Wide three-quarter facade view of the western apartment building.",
    ),
    Shot(
        "30_north_apartment_east_wide",
        (52, 101, 8.0),
        (29, 119, 9.0),
        50,
        "Wide three-quarter facade view of the eastern apartment building.",
    ),
    Shot(
        "31_north_housing_street",
        (50, 60, 5.0),
        (0, 89, 5.0),
        62,
        "Inward streetscape view toward detached houses and apartment buildings.",
    ),
    Shot(
        "32_base_residential_oblique",
        (2, 5, 8),
        (-34, 31, 4.5),
        48,
        "Tight elevated residential view with houses and apartments layered together.",
    ),
    Shot(
        "33_base_residential_reverse",
        (-52, 52, 5.5),
        (-34, 31, 4.0),
        50,
        "Reverse neighborhood view across the residential courtyards toward the city.",
    ),
    Shot(
        "34_north_house_west",
        (-36, 73, 4.2),
        (-36, 89, 3.0),
        55,
        "Frontal architectural view of the western detached house and garden approach.",
    ),
    Shot(
        "35_north_house_center",
        (0, 73, 4.2),
        (0, 89, 3.0),
        55,
        "Frontal architectural view of the central detached house and garden approach.",
    ),
    Shot(
        "36_north_house_east",
        (36, 73, 4.2),
        (36, 89, 3.0),
        55,
        "Frontal architectural view of the eastern detached house and garden approach.",
    ),
    Shot(
        "37_north_apartment_west",
        (-8, 102, 8.5),
        (-29, 119, 10.0),
        58,
        "Compressed facade view of the western apartment building.",
    ),
    Shot(
        "38_north_apartment_east",
        (8, 102, 8.5),
        (29, 119, 10.0),
        58,
        "Compressed facade view of the eastern apartment building.",
    ),
    Shot(
        "39_base_residential_street",
        (0, 15, 4.0),
        (-30, 30, 4.5),
        50,
        "Low neighborhood view framed by the main road and residential frontage.",
    ),
    Shot(
        "40_north_crosswalk",
        (15, 56, 7.0),
        (0, 65.5, 0.55),
        58,
        "Low view of the connected zebra crossing with the central house beyond.",
    ),
    Shot(
        "41_extended_residential_oblique",
        (55, 55, 24),
        (0, 100, 5),
        58,
        "Tight district oblique filled by houses, apartments, trees, and connected paths.",
    ),
)


def parse_resolution(mode: str) -> tuple[int, int]:
    default = "640x360" if mode == "preview" else "2400x1350"
    raw = os.environ.get("C2W_PAPER_RESOLUTION", default)
    match = re.fullmatch(r"\s*(\d+)\s*[xX,]\s*(\d+)\s*", raw)
    if not match:
        raise RuntimeError("C2W_PAPER_RESOLUTION must look like 2400x1350")
    width, height = map(int, match.groups())
    if width < 320 or height < 180:
        raise RuntimeError("C2W_PAPER_RESOLUTION is unreasonably small")
    return width, height


def select_shots() -> list[Shot]:
    raw = os.environ.get("C2W_PAPER_SHOTS", "").strip()
    if not raw:
        return list(SHOTS)
    requested = {item.strip() for item in raw.split(",") if item.strip()}
    known = {shot.name for shot in SHOTS}
    unknown = requested - known
    if unknown:
        raise RuntimeError(f"Unknown paper shots: {sorted(unknown)}")
    return [shot for shot in SHOTS if shot.name in requested]


def set_engine(scene: bpy.types.Scene, requested: str) -> str:
    requested = requested.strip().upper()
    if requested in {"EEVEE", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        for identifier in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
            try:
                scene.render.engine = identifier
                return scene.render.engine
            except (TypeError, ValueError):
                continue
        raise RuntimeError("This Blender build does not expose Eevee")
    if requested in {"WORKBENCH", "BLENDER_WORKBENCH"}:
        scene.render.engine = "BLENDER_WORKBENCH"
        return scene.render.engine
    if requested == "CYCLES":
        scene.render.engine = "CYCLES"
        return scene.render.engine
    raise RuntimeError("C2W_PAPER_ENGINE must be EEVEE, CYCLES, or WORKBENCH")


def configure_color(scene: bpy.types.Scene) -> None:
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        scene.view_settings.view_transform = "Standard"
        scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = -0.15
    scene.view_settings.gamma = 1.0


def configure_render(scene: bpy.types.Scene, mode: str) -> dict:
    width, height = parse_resolution(mode)
    engine = set_engine(scene, os.environ.get("C2W_PAPER_ENGINE", "EEVEE"))
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 22
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    scene.render.use_simplify = False
    if hasattr(scene.render, "use_persistent_data"):
        scene.render.use_persistent_data = True
    configure_color(scene)

    samples = int(
        os.environ.get("C2W_PAPER_SAMPLES", "24" if mode == "preview" else "64")
    )
    render_devices = []
    if engine == "CYCLES":
        requested_device = os.environ.get("C2W_PAPER_DEVICE", "GPU").strip().upper()
        if requested_device not in {"GPU", "CPU"}:
            raise RuntimeError("C2W_PAPER_DEVICE must be GPU or CPU")
        if requested_device == "GPU":
            addon = bpy.context.preferences.addons.get("cycles")
            if addon is None:
                raise RuntimeError("Cycles addon is unavailable")
            preferences = addon.preferences
            for compute_type in ("OPTIX", "CUDA"):
                try:
                    preferences.compute_device_type = compute_type
                    preferences.get_devices()
                    enabled = []
                    for device in preferences.devices:
                        device.use = device.type == compute_type
                        if device.use:
                            enabled.append({"name": device.name, "type": device.type})
                    if enabled:
                        scene.cycles.device = "GPU"
                        render_devices = enabled
                        break
                except (TypeError, ValueError, RuntimeError):
                    continue
            if not render_devices:
                raise RuntimeError(
                    "C2W_PAPER_DEVICE=GPU but Cycles found no CUDA/OptiX device"
                )
        else:
            scene.cycles.device = "CPU"
            render_devices = [{"name": "CPU", "type": "CPU"}]
        scene.cycles.samples = samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.035
        scene.cycles.max_bounces = 5
        scene.cycles.diffuse_bounces = 2
        scene.cycles.glossy_bounces = 2
        scene.cycles.transmission_bounces = 3
    elif engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        eevee = getattr(scene, "eevee", None)
        if eevee is not None:
            for attribute in ("taa_render_samples", "taa_samples"):
                if hasattr(eevee, attribute):
                    setattr(eevee, attribute, samples)
            if hasattr(eevee, "use_raytracing"):
                eevee.use_raytracing = False
            if hasattr(eevee, "use_fast_gi"):
                eevee.use_fast_gi = True
    else:
        shading = scene.display.shading
        shading.light = "STUDIO"
        shading.color_type = "MATERIAL"
        shading.background_type = "VIEWPORT"
        shading.background_color = (0.16, 0.34, 0.62)
        shading.show_shadows = True
        shading.show_cavity = True
        shading.cavity_type = "BOTH"
        shading.curvature_ridge_factor = 1.25
        shading.curvature_valley_factor = 1.05
        shading.show_specular_highlight = True
        if hasattr(shading, "show_outline"):
            shading.show_outline = False
        if hasattr(scene.display, "render_aa"):
            scene.display.render_aa = "16"

    return {
        "mode": mode,
        "engine": engine,
        "resolution": [width, height],
        "samples": samples,
        "devices": render_devices,
        "view_transform": scene.view_settings.view_transform,
        "look": scene.view_settings.look,
        "exposure": scene.view_settings.exposure,
    }


def configure_daylight(scene: bpy.types.Scene) -> dict:
    # Disable only existing sun lamps to make the temporary rig deterministic;
    # authored area/point fixtures remain available for glazed interiors.
    disabled_suns = []
    for obj in scene.objects:
        if obj.type == "LIGHT" and obj.data.type == "SUN" and not obj.hide_render:
            obj.hide_render = True
            disabled_suns.append(obj.name)

    world = bpy.data.worlds.new(TEMP_PREFIX + "world")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(34.0)
    sky.sun_rotation = math.radians(132.0)
    sky.altitude = 0.15
    sky.air_density = 1.0
    sky.dust_density = 1.25
    sky.ozone_density = 1.0
    background.inputs["Strength"].default_value = 0.32
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.world = world

    sun_data = bpy.data.lights.new(TEMP_PREFIX + "sun_data", type="SUN")
    sun_data.energy = 2.35
    sun_data.angle = math.radians(4.0)
    sun_data.color = (1.0, 0.78, 0.61)
    sun = bpy.data.objects.new(TEMP_PREFIX + "sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (math.radians(31.0), math.radians(-22.0), math.radians(-38.0))
    return {
        "world": "Nishita clear daylight",
        "sun_energy": sun_data.energy,
        "sun_angle_degrees": 4.0,
        "disabled_existing_suns": disabled_suns,
    }


def make_camera(scene: bpy.types.Scene) -> bpy.types.Object:
    data = bpy.data.cameras.new(TEMP_PREFIX + "camera_data")
    data.type = "PERSP"
    data.sensor_width = 36.0
    data.clip_start = 0.15
    data.clip_end = 3000.0
    data.dof.use_dof = False
    camera = bpy.data.objects.new(TEMP_PREFIX + "camera", data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return camera


def place_camera(camera: bpy.types.Object, shot: Shot) -> None:
    camera.location = shot.camera
    camera.data.lens = shot.lens
    target = Vector(shot.target)
    camera.rotation_euler = (
        (target - camera.location).to_track_quat("-Z", "Y").to_euler()
    )


def blend_signature() -> dict:
    path = Path(bpy.data.filepath).resolve()
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
    }


def main() -> None:
    if Path(bpy.data.filepath).resolve() != SOURCE_BLEND.resolve():
        raise RuntimeError(f"Expected {SOURCE_BLEND}, opened {bpy.data.filepath}")
    if bpy.context.scene.get("c2w_revision") != "urban_v1_full_08":
        raise RuntimeError(
            f"Refusing non-FULL08 scene: {bpy.context.scene.get('c2w_revision')}"
        )

    mode = os.environ.get("C2W_PAPER_MODE", "preview").strip().lower()
    if mode not in {"preview", "final"}:
        raise RuntimeError("C2W_PAPER_MODE must be preview or final")
    default_out = (
        Path("/tmp/urban_v1_full_08_paper_preview")
        if mode == "preview"
        else SCENE_DIR / "render"
    )
    output_dir = Path(os.environ.get("C2W_PAPER_OUT", str(default_out))).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    shots = select_shots()
    if not shots:
        raise RuntimeError("No paper shots selected")

    source_before = blend_signature()
    settings = configure_render(bpy.context.scene, mode)
    daylight = configure_daylight(bpy.context.scene)
    camera = make_camera(bpy.context.scene)
    print(
        f"[Full08Paper] settings={json.dumps(settings, ensure_ascii=False)}", flush=True
    )
    print(f"[Full08Paper] output={output_dir} shots={len(shots)}", flush=True)

    frames = []
    for index, shot in enumerate(shots, 1):
        started = time.time()
        place_camera(camera, shot)
        target = output_dir / f"{shot.name}.png"
        bpy.context.scene.render.filepath = str(target)
        bpy.ops.render.render(write_still=True)
        if not target.is_file() or target.stat().st_size < 20_000:
            raise RuntimeError(f"Render output is missing or too small: {target}")
        record = {
            **asdict(shot),
            "filename": target.name,
            "bytes": target.stat().st_size,
            "seconds": round(time.time() - started, 2),
        }
        frames.append(record)
        print(
            f"[Full08Paper] frame={index}/{len(shots)} "
            f"name={shot.name} seconds={record['seconds']}",
            flush=True,
        )

    source_after = blend_signature()
    manifest = {
        "revision": "urban_v1_full_08",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source": source_before,
        "source_blend_unchanged": source_before == source_after,
        "settings": settings,
        "daylight": daylight,
        "frames": frames,
    }
    manifest_path = output_dir / "render_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8"
    )
    print(
        f"[Full08Paper] complete frames={len(frames)} manifest={manifest_path} "
        f"source_unchanged={manifest['source_blend_unchanged']}",
        flush=True,
    )


if __name__ == "__main__":
    main()

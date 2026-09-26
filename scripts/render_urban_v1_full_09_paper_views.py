#!/usr/bin/env python3
"""Render publication-oriented views of the existing FULL09 city scene.

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
SCENE_DIR = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_09"
SOURCE_BLEND = SCENE_DIR / "urban_v1_full_09.blend"
TEMP_PREFIX = "__full09_paper__"


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
        "03_cafe_frontage",
        (-37.65, 5.8, 4.7),
        (-37.65, -10.45, 2.82),
        47,
        "Frontal architectural view of the detailed cafe facade and public-realm furniture.",
    ),
    Shot(
        "04_commercial_corner",
        (-10.5, 3.0, 7.2),
        (-24.8, -9.5, 2.65),
        52,
        "Oblique commercial corner view with layered shopfronts and patio details.",
    ),
    Shot(
        "05_retail_block_connection",
        (-5.0, 7.0, 8.0),
        (-27.0, -14.0, 3.0),
        55,
        "Compressed view of the connected retail block and its street edge.",
    ),
    Shot(
        "06_park_sculpture_path",
        (16, 13, 3.2),
        (31, 29, 1.8),
        52,
        "Low park approach with paths and mature trees framing the central sculpture.",
    ),
    Shot(
        "07_park_plaza_detail",
        (47, 38, 3.5),
        (31, 29, 1.6),
        58,
        "Tight reverse landscape view across the planted plaza toward the built city edge.",
    ),
    Shot(
        "08_gymnasium_city_side",
        (15, -84, 7.0),
        (40, -53, 5.0),
        45,
        "Low three-quarter gymnasium view with the sports precinct filling the foreground.",
    ),
    Shot(
        "09_gymnasium_facade",
        (6, -34, 14),
        (39.7, -53, 5),
        60,
        "Tight elevated study of the oval roof and glazed entrance facade.",
    ),
    Shot(
        "10_athletics_field_graphic",
        (7, -60, 20),
        (31, -75.3, 1),
        66,
        "Graphic oblique of the running track and football pitch with no exterior ground visible.",
    ),
    Shot(
        "11_sports_campus_ground",
        (21, -82, 5.0),
        (39, -56, 3.0),
        55,
        "Ground-level sports-campus view using the playing surface as foreground and the gymnasium as backdrop.",
    ),
    Shot(
        "12_northern_residential_street",
        (-86, 126, 2.2),
        (-28, 170, 6.5),
        58,
        "Street-level architectural view of low-rise frontage layered against residential towers.",
    ),
    Shot(
        "13_residential_tower_avenue",
        (-66, 148, 5.0),
        (-25, 185, 12),
        58,
        "Compressed avenue perspective between the low-rise homes and residential towers.",
    ),
    Shot(
        "14_residential_courtyard",
        (20, 150, 18),
        (-22, 187, 9),
        58,
        "Mid-height courtyard composition enclosed by the northern housing blocks.",
    ),
    Shot(
        "15_river_to_park",
        (74, 2, 3.5),
        (40, 29, 3.0),
        58,
        "River-edge view aimed into the park so water, trees, and paths fill the frame.",
    ),
    Shot(
        "16_bridge_into_park",
        (75, 15, 3.3),
        (52, 27, 1.5),
        58,
        "Reverse footbridge view toward the planted park, avoiding the empty east bank.",
    ),
    Shot(
        "17_residential_facade_detail",
        (-72, 137, 8.0),
        (-36, 177, 10),
        62,
        "Tight facade study using repeated balconies, trees, and low-rise roofs as layers.",
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
    if bpy.context.scene.get("c2w_revision") != "urban_v1_full_09":
        raise RuntimeError(
            f"Refusing non-FULL09 scene: {bpy.context.scene.get('c2w_revision')}"
        )

    mode = os.environ.get("C2W_PAPER_MODE", "preview").strip().lower()
    if mode not in {"preview", "final"}:
        raise RuntimeError("C2W_PAPER_MODE must be preview or final")
    default_out = (
        Path("/tmp/urban_v1_full_09_paper_preview")
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
        f"[Full09Paper] settings={json.dumps(settings, ensure_ascii=False)}", flush=True
    )
    print(f"[Full09Paper] output={output_dir} shots={len(shots)}", flush=True)

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
            f"[Full09Paper] frame={index}/{len(shots)} "
            f"name={shot.name} seconds={record['seconds']}",
            flush=True,
        )

    source_after = blend_signature()
    manifest = {
        "revision": "urban_v1_full_09",
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
        f"[Full09Paper] complete frames={len(frames)} manifest={manifest_path} "
        f"source_unchanged={manifest['source_blend_unchanged']}",
        flush=True,
    )


if __name__ == "__main__":
    main()

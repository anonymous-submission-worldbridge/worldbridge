"""Connected renderer for the complete agent4 production scene.

Launch this only through ``generate_urban_v1_full_07.py`` with
``C2W_AGENT4_RENDER=1`` while the saved agent4 blend is open.  Every frame is
rendered from the full scene; this module never creates a compact/proxy scene
or hides geometry outside the route.
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


import hashlib
import json
import math
import os
import time
from pathlib import Path

import bpy


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo"
    / os.environ.get("C2W_OUTPUT_REVISION", "urban_v1_full_07_agent4")
)
BLEND = OUT / f"{OUT.name}.blend"
PREFIX = "full07_agent4:"
FRAME_END = 300


STILLS = (
    ("00_complete_route_oblique.png", "camera_route_oblique_overview", 220),
    ("01_complete_route_orthographic.png", "camera_complete_route_orthographic", 220),
    ("02_bedroom_start_wide.png", "camera_bedroom_wide", 1),
    ("03_wait_inside_real_front_door.png", "camera_front_door_inside_wide", 50),
    ("04_pass_real_front_door.png", "camera_front_door_exterior_context", 62),
    ("05_descend_supported_front_stair.png", "camera_front_door_exterior_context", 86),
    ("06_residential_route_context.png", "camera_route_oblique_overview", 140),
    ("07_crosswalk_context.png", "camera_west_crosswalk_context", 184),
    ("08_commercial_route_context.png", "camera_commercial_route_context", 260),
    ("09_arrive_fresh_mart_wide.png", "camera_fresh_mart_arrival_wide", 296),
    ("10_first_person_real_door.png", "camera_first_person_ultrawide", 58),
    ("11_first_person_zebra_crossing.png", "camera_first_person_ultrawide", 184),
    ("12_first_person_fresh_mart_arrival.png", "camera_first_person_ultrawide", 292),
    ("13_third_person_residential_wide.png", "camera_third_person_wide_chase", 140),
    ("14_third_person_crosswalk_wide.png", "camera_third_person_wide_chase", 184),
    ("15_third_person_commercial_wide.png", "camera_third_person_wide_chase", 260),
)


def _log(message: str) -> None:
    line = f"[Agent4CompleteSceneRender] {message}"
    print(line, flush=True)
    with (OUT / "render.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


def _semantic_viewport_color(material: bpy.types.Material):
    name = material.name.lower()
    semantic = (
        (
            ("grass", "lawn", "leaf", "foliage", "plant", "shrub", "tree"),
            (0.16, 0.40, 0.13, 1),
        ),
        (("flower", "petal"), (0.72, 0.18, 0.27, 1)),
        (("wood", "timber", "hardwood", "door"), (0.38, 0.17, 0.065, 1)),
        (("soil", "dirt", "earth"), (0.24, 0.12, 0.055, 1)),
        (("brick", "terracotta"), (0.52, 0.18, 0.08, 1)),
        (("road", "asphalt"), (0.065, 0.075, 0.095, 1)),
        (("glass", "window", "water"), (0.16, 0.42, 0.57, 1)),
        (("metal", "steel", "iron", "graphite"), (0.16, 0.21, 0.25, 1)),
        (("roof", "tile"), (0.30, 0.25, 0.21, 1)),
        (("plaster", "facade", "stucco"), (0.70, 0.66, 0.57, 1)),
        (("concrete", "stone", "marble", "cobble", "paving"), (0.47, 0.51, 0.53, 1)),
        (("route", "cyan"), (0.0, 0.34, 0.96, 1)),
        (("orange", "marker"), (0.95, 0.18, 0.025, 1)),
    )
    for tokens, color in semantic:
        if any(token in name for token in tokens):
            return color
    if material.use_nodes and material.node_tree:
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled and principled.inputs.get("Base Color"):
            value = tuple(principled.inputs["Base Color"].default_value)
            if max(value[:3]) - min(value[:3]) > 0.025 or max(value[:3]) < 0.60:
                return value
    palette = (
        (0.58, 0.65, 0.70, 1),
        (0.67, 0.55, 0.42, 1),
        (0.53, 0.63, 0.48, 1),
        (0.64, 0.51, 0.57, 1),
        (0.47, 0.56, 0.65, 1),
        (0.70, 0.64, 0.47, 1),
    )
    digest = hashlib.sha1(material.name.encode("utf8", "ignore")).digest()[0]
    return palette[digest % len(palette)]


def _sync_viewport_colors() -> int:
    changed = 0
    for material in bpy.data.materials:
        material.diffuse_color = _semantic_viewport_color(material)
        changed += 1
    return changed


def _configure_workbench(scene, width: int, height: int) -> None:
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.view_settings.exposure = 0.25
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass
    shading = scene.display.shading
    shading.light = "STUDIO"
    shading.studio_light = "outdoor.sl"
    shading.studiolight_rotate_z = math.radians(125)
    shading.color_type = "MATERIAL"
    shading.background_type = "VIEWPORT"
    shading.background_color = (0.63, 0.72, 0.82)
    shading.show_shadows = True
    shading.show_cavity = True
    shading.cavity_type = "WORLD"
    shading.show_specular_highlight = True
    _log(
        f"Configured full-geometry Workbench; synchronized_materials={_sync_viewport_colors()}"
    )


def _configure_cycles(scene, width: int, height: int, samples: int) -> None:
    """Configure a display-server-independent full-scene GPU render.

    Workbench needs an EGL/OpenGL context even in background mode and can hang on
    the render nodes.  Cycles/OptiX talks directly to the selected CUDA device,
    so it is both the production renderer and the reliable headless path here.
    """
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.use_file_extension = True
    scene.render.use_persistent_data = True
    scene.cycles.samples = samples
    scene.cycles.use_denoising = samples >= 2
    scene.cycles.use_adaptive_sampling = samples >= 4
    scene.cycles.adaptive_threshold = 0.18
    scene.cycles.device = "GPU"
    scene.view_settings.exposure = float(os.environ.get("C2W_AGENT4_EXPOSURE", "0.0"))
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        pass

    preferences = bpy.context.preferences.addons["cycles"].preferences
    backend = None
    backend_error = None
    for candidate in ("OPTIX", "CUDA"):
        try:
            preferences.compute_device_type = candidate
            preferences.get_devices()
            visible = []
            for device in preferences.devices:
                device.use = device.type == candidate
                if device.use:
                    visible.append(f"{device.name} ({device.type})")
            if visible:
                backend = candidate
                break
        except Exception as exc:  # Blender builds expose different backends.
            backend_error = repr(exc)
    if backend is None:
        raise RuntimeError(
            "No Cycles GPU device is visible; "
            f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}; "
            f"last_error={backend_error}"
        )
    _log(
        f"Configured full-geometry Cycles/{backend} {width}x{height}, "
        f"samples={samples}, devices={visible}"
    )


def _configure_render(scene, width: int, height: int, samples: int) -> None:
    engine = os.environ.get("C2W_AGENT4_RENDER_ENGINE", "cycles").lower()
    if engine == "cycles":
        _configure_cycles(scene, width, height, samples)
    elif engine == "workbench":
        _configure_workbench(scene, width, height)
    else:
        raise RuntimeError(f"Unsupported C2W_AGENT4_RENDER_ENGINE={engine!r}")


def _camera(suffix: str) -> bpy.types.Object:
    camera = bpy.data.objects.get(PREFIX + suffix)
    if camera is None or camera.type != "CAMERA":
        raise RuntimeError(f"agent4 production camera missing: {PREFIX + suffix}")
    return camera


def _render_stills(scene) -> list[dict]:
    width = int(os.environ.get("C2W_AGENT4_STILL_WIDTH", "960"))
    height = int(os.environ.get("C2W_AGENT4_STILL_HEIGHT", "540"))
    samples = int(os.environ.get("C2W_AGENT4_STILL_SAMPLES", "2"))
    _configure_render(scene, width, height, samples)
    scene.render.image_settings.file_format = "PNG"
    value = os.environ.get("C2W_AGENT4_STILL_INDICES", "all")
    indices = (
        range(len(STILLS))
        if value == "all"
        else [int(item) for item in value.split(",") if item]
    )
    outputs = []
    for index in indices:
        filename, camera_suffix, frame = STILLS[index]
        destination = OUT / filename
        scene.frame_set(frame)
        scene.camera = _camera(camera_suffix)
        scene.render.filepath = str(destination)
        started = time.time()
        bpy.ops.render.render(write_still=True)
        elapsed = time.time() - started
        outputs.append(
            {
                "index": index,
                "file": str(destination),
                "camera": scene.camera.name,
                "frame": frame,
                "bytes": destination.stat().st_size,
                "elapsed_seconds": round(elapsed, 2),
            }
        )
        _log(
            f"Rendered complete-scene still {index:02d}: {destination.name} ({elapsed:.1f}s)"
        )
    return outputs


def _render_video(scene, view: str) -> dict:
    width = int(os.environ.get("C2W_AGENT4_VIDEO_WIDTH", "640"))
    height = int(os.environ.get("C2W_AGENT4_VIDEO_HEIGHT", "360"))
    samples = int(os.environ.get("C2W_AGENT4_VIDEO_SAMPLES", "1"))
    frame_step = int(os.environ.get("C2W_AGENT4_VIDEO_FRAME_STEP", "6"))
    fps = int(os.environ.get("C2W_AGENT4_VIDEO_FPS", "5"))
    _configure_render(scene, width, height, samples)
    cameras = {
        "first": (
            "camera_first_person_ultrawide",
            OUT / f"{OUT.name}_first_person_ultrawide.mp4",
        ),
        "third": (
            "camera_third_person_wide_chase",
            OUT / f"{OUT.name}_third_person_wide.mp4",
        ),
    }
    camera_suffix, destination = cameras[view]
    scene.camera = _camera(camera_suffix)
    scene.frame_start = 1
    scene.frame_end = FRAME_END
    scene.frame_step = frame_step
    scene.render.fps = fps
    scene.render.fps_base = 1.0
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.audio_codec = "NONE"
    scene.render.filepath = str(destination)
    started = time.time()
    bpy.ops.render.render(animation=True)
    elapsed = time.time() - started
    _log(
        f"Rendered complete-scene {view}-person video: {destination.name} ({elapsed:.1f}s)"
    )
    return {
        "view": view,
        "file": str(destination),
        "camera": scene.camera.name,
        "source_frame_start": 1,
        "source_frame_end": FRAME_END,
        "source_frame_step": frame_step,
        "output_fps": fps,
        "output_frames": ((FRAME_END - 1) // frame_step) + 1,
        "duration_seconds": round((((FRAME_END - 1) // frame_step) + 1) / fps, 2),
        "bytes": destination.stat().st_size,
        "elapsed_seconds": round(elapsed, 2),
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    loaded = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if loaded != BLEND.resolve():
        raise RuntimeError(
            f"agent4 renderer requires complete output blend {BLEND}; loaded={loaded}"
        )
    scene = bpy.context.scene
    if (
        scene.get("c2w_revision") != OUT.name
        or not scene.get("c2w_agent4_complete_production_scene")
        or not scene.get("c2w_agent4_collision_audit_passed")
        or not scene.get("c2w_agent4_no_proxy_or_compact_scene")
    ):
        raise RuntimeError(
            "agent4 renderer refused an incomplete, unaudited, or proxy scene"
        )
    if len(scene.objects) < 6100:
        raise RuntimeError(
            f"agent4 complete-scene object-count gate failed: {len(scene.objects)}"
        )

    job = os.environ.get("C2W_AGENT4_RENDER_JOB", "all")
    started = time.time()
    payload = {
        "job": job,
        "complete_scene_blend": str(BLEND),
        "scene_object_count": len(scene.objects),
        "data_object_count": len(bpy.data.objects),
        "collection_count": len(bpy.data.collections),
        "proxy_or_compact_scene": False,
        "cuda_visible_devices": os.environ.get("CUDA_VISIBLE_DEVICES"),
        "outputs": [],
    }
    if job in {"stills", "stills_first", "stills_third", "all"}:
        payload["outputs"].extend(_render_stills(scene))
    if job in {"first", "stills_first", "all"}:
        payload["outputs"].append(_render_video(scene, "first"))
    if job in {"third", "stills_third", "all"}:
        payload["outputs"].append(_render_video(scene, "third"))
    payload["elapsed_seconds"] = round(time.time() - started, 2)
    suffix = os.environ.get("C2W_AGENT4_RENDER_REPORT", job)
    report = OUT / f"render_job_{suffix}.json"
    report.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf8"
    )
    _log(f"Render job complete: {job}; report={report}")


if __name__ == "__main__":
    main()

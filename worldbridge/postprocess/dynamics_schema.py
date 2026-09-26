"""Configuration helpers for the deterministic WorldBridge dynamics pass.

This module intentionally has no Blender dependency.  It is used by the
Blender entry point, documentation examples, and ordinary Python unit tests.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any, Mapping

DEFAULT_CONFIG: dict[str, Any] = {
    "version": 1,
    "timeline": {
        "frame_start": 1,
        "frame_end": 120,
        "fps": 24,
        "loop": True,
    },
    "render": {
        "engine": "AUTO_EEVEE",
        "resolution_x": 1280,
        "resolution_y": 720,
        "resolution_percentage": 100,
        "samples": 32,
        "transparent": False,
        "keep_frames": False,
        "video_path": "./output/dynamics/dynamic_scene.mp4",
    },
    "camera": {
        "name": "",
        "mode": "existing",
        "target": [0.0, 0.0, 0.0],
        "radius": 45.0,
        "height": 18.0,
        "start_degrees": -25.0,
        "end_degrees": 25.0,
        "lens_mm": 42.0,
    },
    "effects": {
        "vehicles": {
            "enabled": True,
            "collection_names": ["Vehicles", "Traffic"],
            "object_names": [],
            "name_patterns": ["vehicle", "car", "truck", "bus", "grp_root"],
            "distance_m": 35.0,
            "forward_axis": "AUTO",
            "wheel_spin": True,
            "wheel_radius_m": 0.34,
            "max_objects": 32,
            "routes": [],
        },
        "wind": {
            "enabled": True,
            "collection_names": ["Trees", "Vegetation"],
            "object_names": [],
            "name_patterns": ["tree", "leaf", "leaves", "canopy", "foliage"],
            "angle_degrees": 2.0,
            "period_frames": 48,
            "max_objects": 96,
        },
        "river": {
            "enabled": True,
            "collection_names": ["River", "Water", "WaterBodies"],
            "object_names": [],
            "name_patterns": ["river", "stream", "water_surface", "flowing_water"],
            "material_patterns": ["river", "stream", "water"],
            "speed": 0.65,
            "wave_scale": 2.8,
            "wave_strength": 0.16,
            "max_materials": 24,
        },
        "fountain": {
            "enabled": True,
            "object_names": [],
            "name_patterns": ["fountain", "fnt_pool", "fnt_top", "water_jet"],
            "center": None,
            "base_height_m": 0.45,
            "jet_height_m": 3.2,
            "jet_radius_m": 1.8,
            "jet_count": 6,
            "droplets_per_jet": 7,
            "period_frames": 30,
            "droplet_radius_m": 0.045,
        },
    },
}


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge dictionaries while replacing lists and scalars."""

    result = copy.deepcopy(dict(base))
    for key, value in override.items():
        if isinstance(value, Mapping) and isinstance(result.get(key), Mapping):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _positive_number(value: Any, field: str) -> None:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive number")


def _positive_integer(value: Any, field: str) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{field} must be a positive integer")


def validate_config(config: Mapping[str, Any]) -> None:
    """Raise ``ValueError`` when a normalized config is not executable."""

    if config.get("version") != 1:
        raise ValueError("Only dynamics config version 1 is supported")

    timeline = config["timeline"]
    start = timeline["frame_start"]
    end = timeline["frame_end"]
    if (
        not isinstance(start, int)
        or isinstance(start, bool)
        or not isinstance(end, int)
        or isinstance(end, bool)
        or end <= start
    ):
        raise ValueError(
            "timeline.frame_end must be an integer greater than frame_start"
        )
    _positive_integer(timeline["fps"], "timeline.fps")
    if not isinstance(timeline["loop"], bool):
        raise ValueError("timeline.loop must be true or false")

    render = config["render"]
    _positive_integer(render["resolution_x"], "render.resolution_x")
    _positive_integer(render["resolution_y"], "render.resolution_y")
    _positive_integer(render["resolution_percentage"], "render.resolution_percentage")
    _positive_integer(render["samples"], "render.samples")
    if not isinstance(render["transparent"], bool) or not isinstance(
        render["keep_frames"], bool
    ):
        raise ValueError(
            "render.transparent and render.keep_frames must be true or false"
        )

    camera = config["camera"]
    if camera["mode"] not in {"existing", "orbit"}:
        raise ValueError("camera.mode must be 'existing' or 'orbit'")
    if len(camera["target"]) != 3:
        raise ValueError("camera.target must contain exactly three numbers")

    effects = config["effects"]
    for name in ("vehicles", "wind", "river", "fountain"):
        if name not in effects or not isinstance(effects[name], Mapping):
            raise ValueError(f"effects.{name} must be an object")
        if not isinstance(effects[name].get("enabled"), bool):
            raise ValueError(f"effects.{name}.enabled must be true or false")

    vehicles = effects["vehicles"]
    if str(vehicles["forward_axis"]).upper() not in {"AUTO", "X", "Y", "-X", "-Y"}:
        raise ValueError("effects.vehicles.forward_axis must be AUTO, X, Y, -X, or -Y")
    _positive_number(vehicles["distance_m"], "effects.vehicles.distance_m")
    for index, route in enumerate(vehicles["routes"]):
        if not isinstance(route, Mapping) or not route.get("object"):
            raise ValueError(f"effects.vehicles.routes[{index}] needs an object name")
        points = route.get("points", [])
        if len(points) < 2 or any(len(point) not in {2, 3} for point in points):
            raise ValueError(
                f"effects.vehicles.routes[{index}].points needs at least two 2D/3D points"
            )

    _positive_integer(effects["wind"]["period_frames"], "effects.wind.period_frames")
    _positive_integer(
        effects["fountain"]["period_frames"], "effects.fountain.period_frames"
    )
    _positive_integer(
        effects["vehicles"]["max_objects"], "effects.vehicles.max_objects"
    )
    _positive_integer(effects["wind"]["max_objects"], "effects.wind.max_objects")
    _positive_integer(effects["river"]["max_materials"], "effects.river.max_materials")
    _positive_integer(effects["fountain"]["jet_count"], "effects.fountain.jet_count")
    _positive_integer(
        effects["fountain"]["droplets_per_jet"], "effects.fountain.droplets_per_jet"
    )
    center = effects["fountain"].get("center")
    if center is not None and len(center) != 3:
        raise ValueError("effects.fountain.center must be null or [x, y, z]")


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load, merge, and validate a dynamics configuration."""

    override: Mapping[str, Any] = {}
    if path:
        config_path = Path(path)
        with config_path.open("r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if not isinstance(loaded, Mapping):
            raise ValueError("Dynamics config root must be a JSON object")
        override = loaded
    config = _deep_merge(DEFAULT_CONFIG, override)
    validate_config(config)
    return config


__all__ = ["DEFAULT_CONFIG", "load_config", "validate_config"]

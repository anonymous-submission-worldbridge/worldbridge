"""Render one animated Blender scene with every visible NVIDIA GPU in Cycles."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import bpy


def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--frame-start", type=int, required=True)
    parser.add_argument("--frame-end", type=int, required=True)
    parser.add_argument("--resolution-x", type=int, default=1280)
    parser.add_argument("--resolution-y", type=int, default=720)
    parser.add_argument("--samples", type=int, default=16)
    parser.add_argument("--adaptive-threshold", type=float, default=0.08)
    return parser.parse_args(argv)


def configure_all_optix_devices() -> list[dict[str, str]]:
    preferences = bpy.context.preferences.addons["cycles"].preferences
    # On Blender 5.1 a fresh process can expose zero OptiX devices if OPTIX is
    # selected before the CUDA device table has been populated.  Warming the
    # CUDA backend first makes discovery deterministic; rendering still uses
    # only the OptiX entries selected below.
    preferences.compute_device_type = "CUDA"
    preferences.refresh_devices()
    # Materializing the collection is required; refresh_devices() alone is
    # lazy and leaves the subsequent OptiX query empty on some launches.
    list(preferences.devices)
    preferences.compute_device_type = "OPTIX"
    optix_devices = []
    # Device enumeration can briefly return an empty list while other CUDA
    # workloads on a shared machine are creating/destroying contexts.
    for attempt in range(1, 13):
        preferences.refresh_devices()
        optix_devices = [
            device for device in preferences.devices if device.type == "OPTIX"
        ]
        if len(optix_devices) == 8:
            break
        print(
            f"C2W_DEVICE_DISCOVERY_RETRY attempt={attempt} optix={len(optix_devices)}",
            flush=True,
        )
        time.sleep(5)
    enabled = []
    for device in preferences.devices:
        device.use = device.type == "OPTIX"
        if device.use:
            enabled.append({"name": device.name, "type": device.type, "id": device.id})
    if len(enabled) != 8:
        raise RuntimeError(f"Expected 8 OptiX GPUs, enabled {len(enabled)}: {enabled}")
    return enabled


def main() -> None:
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    enabled = configure_all_optix_devices()

    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = args.samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = args.adaptive_threshold
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    scene.cycles.max_bounces = 4
    scene.cycles.diffuse_bounces = 2
    scene.cycles.glossy_bounces = 2
    scene.cycles.transmission_bounces = 3
    scene.cycles.transparent_max_bounces = 4
    scene.cycles.volume_bounces = 1
    scene.render.use_persistent_data = True
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.filepath = str(output_dir / "frame_")
    scene.frame_start = args.frame_start
    scene.frame_end = args.frame_end

    print("C2W_ALL_GPUS=" + json.dumps(enabled), flush=True)
    print(
        f"C2W_RENDER frames={args.frame_start}..{args.frame_end} "
        f"resolution={args.resolution_x}x{args.resolution_y} samples={args.samples}",
        flush=True,
    )
    if args.frame_start == args.frame_end:
        scene.frame_set(args.frame_start)
        scene.render.filepath = str(output_dir / f"frame_{args.frame_start:04d}.png")
        bpy.ops.render.render(write_still=True)
    else:
        bpy.ops.render.render(animation=True)


if __name__ == "__main__":
    main()

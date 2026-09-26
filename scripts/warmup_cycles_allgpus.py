"""Prime Blender's CUDA/OptiX device table before loading a very large scene."""

import json

import bpy


preferences = bpy.context.preferences.addons["cycles"].preferences
preferences.compute_device_type = "CUDA"
preferences.refresh_devices()
list(preferences.devices)
preferences.compute_device_type = "OPTIX"
preferences.refresh_devices()
devices = [
    {"name": device.name, "type": device.type, "id": device.id}
    for device in preferences.devices
    if device.type == "OPTIX"
]
if len(devices) != 8:
    raise RuntimeError(
        f"Expected 8 OptiX GPUs during warmup, found {len(devices)}: {devices}"
    )
print("C2W_OPTIX_WARMUP=" + json.dumps(devices), flush=True)

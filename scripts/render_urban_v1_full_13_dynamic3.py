"""Render unwarped native 3D frames, deterministic sampling, and static-world audit."""
import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic import sha256


def atomic(path, data):
    temp = path.with_suffix(".writing.json")
    temp.write_text(json.dumps(data, indent=2))
    os.replace(temp, path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--frames", required=True)
    p.add_argument("--samples", type=int, default=128)
    p.add_argument("--width", type=int, default=1920)
    p.add_argument("--height", type=int, default=1080)
    p.add_argument("--audit-only", action="store_true")
    p.add_argument("--denoise", action="store_true")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    scene = next(s for s in bpy.data.scenes if s.get("dynamic3_manifest"))
    bpy.context.window.scene = scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = args.denoise
    if args.denoise:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
        scene.cycles.denoising_prefilter = "ACCURATE"
        if hasattr(scene.cycles, "denoising_quality"):
            scene.cycles.denoising_quality = "HIGH"
    scene.cycles.use_animated_seed = False
    scene.cycles.seed = 317
    scene.cycles.use_adaptive_sampling = False
    scene.render.use_persistent_data = True
    scene.render.use_simplify = False
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.use_motion_blur = False
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.image_settings.compression = 30
    frames = [int(f) for f in args.frames.split(",")]
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    blend = Path(bpy.data.filepath)
    contract = {
        "blend_sha256": sha256(blend),
        "renderer_sha256": sha256(Path(__file__)),
        "resolution": [args.width, args.height],
        "samples": args.samples,
        "engine": "CYCLES_OPTIX",
        "denoising": args.denoise,
        "animated_seed": False,
        "seed": 317,
        "simplify": False,
        "libraries": [
            {
                "path": bpy.path.abspath(lib.filepath),
                "size": Path(bpy.path.abspath(lib.filepath)).stat().st_size,
                "mtime_ns": Path(bpy.path.abspath(lib.filepath)).stat().st_mtime_ns,
            }
            for lib in bpy.data.libraries
        ],
    }
    contract["sha256"] = hashlib.sha256(
        json.dumps(contract, sort_keys=True).encode()
    ).hexdigest()
    cp = out / "render_contract.json"
    if cp.exists() and json.loads(cp.read_text()) != contract:
        if any(out.glob("frame_*.png")):
            raise RuntimeError("Render contract changed; use a fresh frames directory")
        # An aborted pre-render audit produced no image content to mix.
        cp.rename(out / ("render_contract_aborted_" + str(time.time_ns()) + ".json"))
    atomic(cp, contract)
    # Authored object transforms must remain stationary outside explicit traffic rigs.
    scene.frame_set(1)
    static = [
        o
        for o in bpy.data.objects
        if o.type not in ("CAMERA",) and not o.animation_data
    ]
    # Linked assets in different libraries may intentionally share a name.
    before = {o.as_pointer(): np.array(o.matrix_basis) for o in static}
    camera = np.array(scene.camera.matrix_basis)
    progress = {
        "status": "AUDITED" if args.audit_only else "RENDERING",
        "frames": [],
        "static_transform_objects": len(static),
        "camera_fixed": True,
        "world_static": not bool(scene.world.node_tree.animation_data),
    }
    if not progress["world_static"]:
        raise RuntimeError("Animated air/world is forbidden")
    if not args.audit_only:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        if not any(device.use for device in prefs.devices):
            raise RuntimeError("No OptiX device available")
        scene.cycles.device = "GPU"
    for frame in frames:
        begin = time.monotonic()
        scene.frame_set(frame)
        if not np.array_equal(camera, np.array(scene.camera.matrix_basis)):
            raise RuntimeError("Camera moved")
        changed = [
            o.name
            for o in static
            if not np.allclose(
                before[o.as_pointer()], np.array(o.matrix_basis), atol=2e-6, rtol=0
            )
        ]
        if changed:
            raise RuntimeError("Static object transform changed: " + repr(changed[:20]))
        if not args.audit_only:
            target = out / f"frame_{frame:04d}.png"
            if target.exists():
                raise RuntimeError(
                    "Frame already exists; coordinator must verify and skip it"
                )
            scene.render.filepath = str(target)
            bpy.ops.render.render(write_still=True)
        progress["frames"].append(
            {"frame": frame, "seconds": round(time.monotonic() - begin, 3)}
        )
        atomic(out / f"progress_{frames[0]:04d}.json", progress)
        print("DYN3 FRAME", frame, progress["frames"][-1]["seconds"], flush=True)
    progress["status"] = "PASS"
    atomic(out / f"progress_{frames[0]:04d}.json", progress)


if __name__ == "__main__":
    main()

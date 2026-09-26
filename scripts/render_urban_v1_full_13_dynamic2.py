#!/usr/bin/env python3
"""Native 3D renderer with fixed cameras, conservative frustum culling and provenance."""
import argparse
import hashlib
import json
import os
import struct
import sys
import time
from pathlib import Path

import bpy
from mathutils import Vector, Matrix

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic2 import STATIC, matrix
from build_urban_v1_full_13_dynamic import sha256


def atomic(path, data):
    temp = path.with_suffix(".writing.json")
    temp.write_text(json.dumps(data, indent=2))
    os.replace(temp, path)


def valid(path, w, h):
    if not path.is_file() or path.stat().st_size < 4096:
        return False
    with path.open("rb") as f:
        header = f.read(24)
    return header[:8] == b"\x89PNG\r\n\x1a\n" and struct.unpack(
        ">II", header[16:24]
    ) == (w, h)


def in_frustum(camera, box, margin=22.0):
    m = matrix(camera).inverted()
    pts = [
        m @ Vector((x, y, z))
        for x in (box["min"][0], box["max"][0])
        for y in (box["min"][1], box["max"][1])
        for z in (box["min"][2], box["max"][2])
    ]
    tx = camera.data.sensor_width / (2 * camera.data.lens)
    ty = tx * 9 / 16
    # A box is discarded only if ALL corners lie outside the SAME plane.
    # Twenty-two metres of padding retains offscreen casters/nearby context.
    planes = (
        lambda p: p.x + p.z * tx,
        lambda p: -p.x + p.z * tx,
        lambda p: p.y + p.z * ty,
        lambda p: -p.y + p.z * ty,
        lambda p: p.z,
    )
    return not any(all(test(v) > margin for v in pts) for test in planes)


def tree_visibility(roots, camera, scene):
    visible = {}
    labels = {}
    sun = next(o for o in scene.objects if o.type == "LIGHT")
    light_direction = matrix(sun).to_3x3() @ Vector((0, 0, -1))
    for root in roots:
        if not root.instance_collection:
            continue
        for tree in root.instance_collection.all_objects:
            coll = tree.instance_collection
            if not coll or not coll.name.startswith("DYN2::Wind::"):
                continue
            transform = (
                matrix(root) @ matrix(tree) @ Matrix.Translation(-coll.instance_offset)
            )
            points = [
                transform @ matrix(part) @ Vector(v)
                for part in coll.all_objects
                if part.type == "MESH"
                for v in part.bound_box
            ]
            # Retain offscreen trees if their sun shadow can enter the view.
            for point in list(points):
                if point.z > 0 and light_direction.z < -0.01:
                    points.append(
                        point + light_direction * (-point.z / light_direction.z)
                    )
            box = {
                "min": [min(p[i] for p in points) - 0.1 for i in range(3)],
                "max": [max(p[i] for p in points) + 0.1 for i in range(3)],
            }
            visible[tree] = visible.get(tree, False) or in_frustum(
                camera, box, margin=0.5
            )
    for tree, keep in visible.items():
        tree.hide_render = not keep
        tree.hide_viewport = not keep
        labels[tree.name] = keep
    return labels


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--frames", default="")
    p.add_argument(
        "--shot", choices=["traffic", "river_and_wind", "fountain", "lake_and_wind"]
    )
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--height", type=int, default=720)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--engine", choices=("cycles", "eevee"), default="cycles")
    p.add_argument(
        "--pack-only",
        action="store_true",
        help="Write exact per-shot dependency packs without evaluating/rendering geometry",
    )
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    blend = Path(bpy.data.filepath)
    manifest_path = next(
        p / "dynamic2_manifest.json"
        for p in (blend.parent, blend.parent.parent)
        if (p / "dynamic2_manifest.json").exists()
    )
    manifest = json.loads(manifest_path.read_text())
    if manifest["status"] != "BUILT" or manifest["traffic_audit"]["status"] != "PASS":
        raise RuntimeError("Build/audit did not pass")
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    deps = [
        {
            "path": lib.filepath,
            "size": Path(bpy.path.abspath(lib.filepath)).stat().st_size,
            "mtime_ns": Path(bpy.path.abspath(lib.filepath)).stat().st_mtime_ns,
        }
        for lib in bpy.data.libraries
    ]
    contract = {
        "blend_sha256": sha256(blend),
        "renderer_sha256": sha256(Path(__file__)),
        "resolution": [args.width, args.height],
        "samples": args.samples,
        "engine": args.engine,
        "libraries": deps,
    }
    digest = hashlib.sha256(json.dumps(contract, sort_keys=True).encode()).hexdigest()
    contract_file = output / ("render_contract_" + (args.shot or "all") + ".json")
    if (
        contract_file.exists()
        and json.loads(contract_file.read_text())["sha256"] != digest
    ):
        raise RuntimeError(
            "Different render contract: use a NEW output directory; never reuse stale frames"
        )
    atomic(contract_file, {"sha256": digest, **contract})
    full = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
    # A fresh render scene contains ONLY placement instances, cameras and lights.
    # Do not evaluate source-authoring collections/view layers of the full master.
    roots = [o for o in full.objects if o.get("placement_id")]
    scene = bpy.data.scenes.new("DYN2_NativeRenderScene")
    scene["dynamic2_manifest"] = "dynamic2_manifest.json"
    bpy.context.window.scene = scene
    scene.world = full.world
    scene.render.fps = 24
    scene.view_settings.view_transform = full.view_settings.view_transform
    scene.view_settings.look = full.view_settings.look
    scene.view_settings.exposure = full.view_settings.exposure
    for light in full.objects:
        if light.type == "LIGHT" and light.name.startswith("C2W_Full13_DynamicSun"):
            scene.collection.objects.link(light)
    scene.render.engine = "CYCLES" if args.engine == "cycles" else "BLENDER_EEVEE"
    if args.engine == "cycles" and not args.pack_only:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        for device in prefs.devices:
            device.use = device.type == "OPTIX"
        if not any(d.use for d in prefs.devices):
            raise RuntimeError("No OptiX GPU available; refusing a silent CPU fallback")
        scene.cycles.device = "GPU"
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.render.use_persistent_data = True
    scene.render.resolution_x = args.width
    scene.render.resolution_y = args.height
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_motion_blur = False
    scene.eevee.taa_render_samples = args.samples
    scene.eevee.shadow_pool_size = "1024"
    layout = {
        r["placement_id"]: r
        for r in json.loads((STATIC / "layout_plan.json").read_text())["placements"]
    }
    shots = [s for s in manifest["shots"] if not args.shot or s["name"] == args.shot]
    chosen = {int(f) for f in args.frames.split(",") if f} if args.frames else None
    if chosen is not None and any(
        not any(s["start"] <= f <= s["end"] for s in shots) for f in chosen
    ):
        raise ValueError("Requested frame is outside the selected shot(s)")
    progress = {
        "status": "RUNNING",
        "contract": digest,
        "completed": [],
        "shots": {},
        "seconds": {},
    }
    progresspath = output / ("progress_" + (args.shot or "all") + ".json")
    # Prevent inactive view layers in the full static master from also rendering.
    for layer in scene.view_layers:
        layer.use = layer == bpy.context.view_layer
    scene.use_nodes = False
    scene.render.use_compositing = False
    for shot in shots:
        camera = bpy.data.objects[shot["camera"]]
        scene.camera = camera
        for ob in list(scene.collection.objects):
            if ob.type != "LIGHT":
                scene.collection.objects.unlink(ob)
        scene.collection.objects.link(camera)
        selected = []
        culled = []
        for root in roots:
            record = layout.get(root["placement_id"], {})
            box = record.get("footprint")
            keep = True if not box else in_frustum(camera, box)
            if root["placement_id"] == "full13_single_road_activity_module":
                keep = shot["name"] == "traffic"
            root.hide_render = not keep
            root.hide_viewport = not keep
            if keep:
                scene.collection.objects.link(root)
            (selected if keep else culled).append(root["placement_id"])
        trees = tree_visibility(
            [r for r in roots if r["placement_id"] in selected], camera, scene
        )
        progress["shots"][shot["name"]] = {
            "kept": selected,
            "outside_frustum": culled,
            "tree_species_culling": False,
            "tree_instance_frustum_and_shadow_test": trees,
            "camera_fixed": True,
        }
        print(
            "DYNAMIC2 SHOT", shot["name"], "kept", len(selected), selected, flush=True
        )
        if args.pack_only:
            for root in [
                o for o in list(scene.collection.objects) if o.get("placement_id")
            ]:
                copy = root.copy()
                copy.name = "DYN2_RenderRoot::" + root["placement_id"]
                collection = bpy.data.collections.new(
                    "DYN2_RenderCollection::" + root["placement_id"]
                )
                collection.instance_offset = root.instance_collection.instance_offset
                for obj in root.instance_collection.all_objects:
                    if obj.name in trees and not trees[obj.name]:
                        continue
                    collection.objects.link(obj)
                copy.instance_collection = collection
                scene.collection.objects.unlink(root)
                scene.collection.objects.link(copy)
            pack = output / (shot["name"] + ".blend")
            bpy.data.libraries.write(
                str(pack), {scene}, path_remap="ABSOLUTE", fake_user=True
            )
            progress["shots"][shot["name"]]["pack_sha256"] = sha256(pack)
            atomic(progresspath, progress)
            continue
        for frame in range(shot["start"], shot["end"] + 1):
            if chosen is not None and frame not in chosen:
                continue
            path = output / f"frame_{frame:04d}.png"
            if valid(path, args.width, args.height):
                progress["completed"].append(frame)
                continue
            t = time.monotonic()
            scene.frame_set(frame)
            scene.camera = camera
            scene.render.filepath = str(path)
            bpy.ops.render.render(write_still=True)
            if not valid(path, args.width, args.height):
                raise RuntimeError("Invalid rendered PNG: " + str(path))
            progress["completed"].append(frame)
            progress["seconds"][str(frame)] = round(time.monotonic() - t, 3)
            atomic(progresspath, progress)
            print("DYNAMIC2 FRAME", frame, progress["seconds"][str(frame)], flush=True)
    progress["status"] = "PASS"
    atomic(progresspath, progress)


if __name__ == "__main__":
    main()

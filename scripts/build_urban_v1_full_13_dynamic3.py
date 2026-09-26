"""Preserve the full native scene; add restrained wind and impact-driven water.

Open dynamic2's complete master with --disable-depsgraph-on-file-load.
No mesh replacement, decimation, image warping, or atmosphere animation.
"""
import argparse
import ast
import hashlib
import json
import math
import sys
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_urban_v1_full_13_dynamic2 as d
from render_urban_v1_full_13_dynamic2 import in_frustum, tree_visibility

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic3"
FRAMES = 144
FPS = 24
SHOTS = [
    ("river_environment", (-256.0, -178.0, 47.0), (-310.0, -60.0, 0.0), 40.0),
    ("river_detail", (-291.0, -138.0, 8.0), (-309.0, -95.0, 2.4), 48.0),
    ("lake_environment", (-55.0, -166.0, 91.0), (-139.0, -66.0, 0.0), 42.0),
    ("lake_impact", (-120.0, -92.0, 13.0), (-128.0, -65.0, 1.5), 42.0),
    ("fountain_environment", (-232.0, -123.0, 4.5), (-240.0, -105.0, 1.7), 50.0),
    ("fountain_detail", (-232.8, -118.2, 10.0), (-240.0, -105.0, 1.4), 52.0),
    ("street_environment", (301.0, -30.0, 34.0), (272.5, 0.0, 0.0), 38.0),
]


def digest_mesh(mesh):
    """Fingerprint every native coordinate and polygon connectivity."""
    h = hashlib.sha256()
    for prop, collection, dtype, size in (
        ("co", mesh.vertices, np.float32, 3),
        ("vertex_index", mesh.loops, np.int32, 1),
        ("loop_total", mesh.polygons, np.int32, 1),
    ):
        a = np.empty(len(collection) * size, dtype=dtype)
        collection.foreach_get(prop, a)
        h.update(a.tobytes())
    return h.hexdigest()


def calm_leaves(report):
    for obj in bpy.data.objects:
        if obj.library or not obj.get("dynamic2_native_instance_proof"):
            continue
        for mod in obj.modifiers:
            if (
                mod.type != "NODES"
                or not mod.node_group
                or "NativeLeafInstances" not in mod.name
            ):
                continue
            mod.node_group = mod.node_group.copy()
            mod.node_group.name = "DYN3_AttachedLeafBreeze::" + obj.name
            changes = []
            for n in mod.node_group.nodes:
                if n.bl_idname != "ShaderNodeMath" or n.operation != "MULTIPLY":
                    continue
                for socket in n.inputs:
                    if not socket.is_linked and any(
                        abs(socket.default_value - a) < 1e-6 for a in (0.075, 0.055)
                    ):
                        previous = socket.default_value
                        socket.default_value *= 0.28
                        changes.append([previous, socket.default_value])
            if len(changes) != 2:
                raise RuntimeError("Unrecognized native wind group: " + obj.name)
            report.append(
                {
                    "object": obj.name,
                    "amplitudes_rad": changes,
                    "native_geometry_proof": ast.literal_eval(
                        obj["dynamic2_native_instance_proof"]
                    ),
                }
            )


def stabilize_water_material(obj, report):
    """Reuse original shading; only move normal waves, never sediment or rings' centers."""
    for index, slot in enumerate(obj.material_slots):
        if not slot.material or not slot.material.use_nodes:
            continue
        mat = slot.material.copy()
        mat.name = "DYN3::" + slot.material.name
        nt = mat.node_tree
        nt.animation_data_clear()
        reverted = 0
        for node in list(nt.nodes):
            # dynamic2 inserted animated ADD coordinates upstream of textures.
            if node.bl_idname != "ShaderNodeVectorMath" or node.operation != "ADD":
                continue
            if not node.inputs[0].is_linked or node.inputs[1].is_linked:
                continue
            targets = list(node.outputs[0].links)
            if targets and all(
                x.to_node.bl_idname
                in ("ShaderNodeTexWave", "ShaderNodeTexNoise", "ShaderNodeTexVoronoi")
                for x in targets
            ):
                source = node.inputs[0].links[0].from_socket
                for link in targets:
                    nt.links.new(source, link.to_socket)
                nt.nodes.remove(node)
                reverted += 1
        rings = 0
        for node in nt.nodes:
            if node.bl_idname == "ShaderNodeTexWave":
                phase = node.inputs.get("Phase Offset")
                if phase is not None:
                    # Blender wave phase is dimensionless. Fixed source, outward phase.
                    scale = node.inputs["Scale"].default_value
                    speed = 0.23 if node.wave_type == "RINGS" else 0.035
                    phase.driver_add(
                        "default_value"
                    ).driver.expression = f"-{scale*20*speed:.9f}*(frame-1)/24"
                if node.wave_type == "RINGS":
                    rings += 1
                    calibrate_lake_ring(nt, node)
        slot.link = "OBJECT"
        slot.material = mat
        if obj.get("dynamic2_role") == "lake_surface":
            calibrate_lake_optics(mat)
        report.append(
            {
                "object": obj.name,
                "material": mat.name,
                "reused_existing_ring_wave_nodes": rings,
                "removed_whole_texture_advection_nodes": reverted,
            }
        )


def calibrate_lake_ring(nt, node):
    """Reuse the existing Infinigen lake ring layer at a resolved gravity-wave scale."""
    node.inputs["Scale"].default_value = 0.55
    node.inputs["Distortion"].default_value = 0.55
    k = 20 * 0.55  # Blender Wave Texture's spatial angular-frequency multiplier.
    omega = math.sqrt((9.81 * k + 0.072 / 1000 * k**3) * math.tanh(k * 1.85))
    phase = node.inputs["Phase Offset"]
    phase.driver_remove("default_value")
    phase.driver_add("default_value").driver.expression = f"-{omega:.9f}*frame/24"
    for link in node.outputs["Color"].links:
        target = link.to_node
        if (
            target.bl_idname == "ShaderNodeMath"
            and target.operation == "MULTIPLY"
            and target.inputs[1].is_linked
        ):
            envelope = target.inputs[1].links[0].from_node
            if (
                envelope.bl_idname == "ShaderNodeMath"
                and envelope.operation == "MULTIPLY"
                and not envelope.inputs[1].is_linked
            ):
                envelope.inputs[1].default_value = 2.0


def calibrate_lake_optics(mat):
    """Resolve millimetric ripples in the original water shader, retaining its color/volume."""
    for node in mat.node_tree.nodes:
        if node.bl_idname == "ShaderNodeBsdfPrincipled":
            node.inputs["IOR"].default_value = 1.333
            node.inputs["Specular IOR Level"].default_value = 0.5
        elif node.bl_idname == "ShaderNodeMapRange":
            lo, hi = node.inputs.get("To Min"), node.inputs.get("To Max")
            if (
                lo
                and hi
                and abs(lo.default_value - 0.26) < 1e-5
                and abs(hi.default_value - 0.39) < 1e-5
            ):
                lo.default_value = 0.16
                hi.default_value = 0.24
        elif node.bl_idname == "ShaderNodeTexWave" and node.wave_type == "RINGS":
            calibrate_lake_ring(mat.node_tree, node)


def bake_lake_impacts(water, droplets, report):
    """All native drops drive damped expanding wave packets on the native grid.

    Each drop's first impact is at life-phase; negative-time impacts establish
    steady state. Two prior emissions are included to avoid lifetime seams.
    This is a linear gravity/capillary wave response, not a CFD solver.
    """
    mesh = water.data
    before = digest_mesh(mesh)
    xyz = np.empty(len(mesh.vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", xyz)
    xyz = xyz.reshape(-1, 3)
    starts = np.array([r[0] for r in droplets], dtype=np.float64)
    velocities = np.array([r[1] for r in droplets], dtype=np.float64)
    lives = np.array([r[2] for r in droplets], dtype=np.float64)
    phases = np.array([r[3] for r in droplets], dtype=np.float64)
    impacts = starts + velocities * lives[:, None]
    impacts[:, 2] -= 0.5 * 9.81 * lives * lives
    if np.max(np.abs(impacts[:, 2])) > 1e-5:
        raise RuntimeError("Lake drops do not land on z=0 water")
    centre = impacts[:, :2].mean(axis=0)
    active = np.linalg.norm(xyz[:, :2] - centre, axis=1) < 6.8
    distance = np.linalg.norm(
        xyz[active, None, :2] - impacts[None, :, :2], axis=2
    ).astype(np.float32)
    pinned = np.array(
        [v.value for v in mesh.attributes["dyn2_interior"].data], dtype=np.float32
    )
    water.shape_key_add(name="Basis", from_mix=False)
    water.data.shape_keys.use_relative = False
    max_height = 0.0
    wavelength = 0.72
    k = math.tau / wavelength
    omega = math.sqrt((9.81 * k + 0.072 / 1000 * k**3) * math.tanh(k * 1.85))
    speed = omega / k
    for frame in range(1, FRAMES + 1):
        time = frame / FPS  # Match GeometryNodeInputSceneTime used by native droplets.
        age = np.mod(time + phases, lives)
        displacement = np.zeros(distance.shape[0], dtype=np.float32)
        for previous in range(2):
            elapsed = age + previous * lives
            travel = distance - speed * elapsed[None, :]
            envelope = np.exp(-0.5 * (travel / 0.28) ** 2) * np.exp(
                -1.5 * elapsed[None, :]
            )
            # Impact has zero amplitude at t=0; envelope expands continuously.
            response = (
                np.sin(k * travel) * envelope * (1 - np.exp(-elapsed[None, :] / 0.045))
            )
            displacement += np.sum(response, axis=1) * 0.00065
        displacement *= pinned[active]
        # Smooth compression bounds dense overlapping impacts without hard clipping.
        displacement = 0.009 * np.tanh(displacement / 0.009)
        coordinates = xyz.copy()
        coordinates[active, 2] += displacement
        key = water.shape_key_add(name=f"Impact_{frame:04d}", from_mix=False)
        key.data.foreach_set("co", coordinates.ravel())
        key.interpolation = "KEY_LINEAR"
        water.data.shape_keys.eval_time = key.frame
        water.data.shape_keys.keyframe_insert("eval_time", frame=frame)
        max_height = max(max_height, float(np.max(np.abs(displacement))))
        if frame % 24 == 0:
            print("DYN3 IMPACT BAKE", frame, FRAMES, flush=True)
    d.old.finish_animation(water.data.shape_keys, linear=True)
    if digest_mesh(mesh) != before:
        raise RuntimeError("Baking changed the authored basis mesh")
    report.update(
        {
            "native_droplets": len(droplets),
            "basis_sha256": before,
            "basis_unchanged": True,
            "native_vertices": len(mesh.vertices),
            "native_polygons": len(mesh.polygons),
            "wave_phase_speed_mps": speed,
            "max_impact_displacement_m": max_height,
            "frames": FRAMES,
            "impact_bounds_local": [
                impacts.min(axis=0).tolist(),
                impacts.max(axis=0).tolist(),
            ],
        }
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=OUT)
    p.add_argument(
        "--shot",
        choices=[s[0] for s in SHOTS],
        help="Load only exact dependencies for one view from the full master",
    )
    p.add_argument(
        "--master-only",
        action="store_true",
        help="Save the complete 82-placement master without replacing any render pack",
    )
    args = p.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    packs = out / "render_packs"
    packs.mkdir(exist_ok=True)
    if args.shot and args.master_only:
        p.error("--shot and --master-only are mutually exclusive")
    manifest_target = out / (
        "master_build.json"
        if args.master_only
        else f"build_{args.shot}.json"
        if args.shot
        else "dynamic3_manifest.json"
    )
    if manifest_target.exists():
        raise RuntimeError(
            "Existing build: choose a new directory to preserve provenance"
        )
    source = (
        (OUT.with_name("urban_v1_full_13-dynamic2") / "urban_v1_full_13_dynamic2.blend")
        if args.shot
        else Path(bpy.data.filepath)
    )
    manifest = json.loads((source.parent / "dynamic2_manifest.json").read_text())
    if d.old.sha256(source) != manifest["output_blend_sha256"]:
        raise RuntimeError("Source master hash mismatch")
    layout = {
        r["placement_id"]: r
        for r in json.loads((d.STATIC / "layout_plan.json").read_text())["placements"]
    }
    if args.shot:
        _, position, target, lens = next(s for s in SHOTS if s[0] == args.shot)
        probe = bpy.data.objects.new(
            "FrustumProbe", bpy.data.cameras.new("FrustumProbe")
        )
        probe.location = position
        probe.data.lens = lens
        d.old.look_at(probe, Vector(target))
        selected_names = {
            r["name"]
            for r in layout.values()
            if not r.get("footprint") or in_frustum(probe, r["footprint"], margin=30.0)
        }
        bpy.data.objects.remove(probe)
        full = bpy.data.scenes.new("DYN3_ExactSourceDependencies")
        full["dynamic2_manifest"] = "dynamic2_manifest.json"
        with bpy.data.libraries.load(str(source), link=False) as (available, loaded):
            loaded.objects = [
                n
                for n in available.objects
                if n in selected_names or n.startswith("C2W_Full13_DynamicSun")
            ]
            loaded.worlds = [
                n for n in available.worlds if n.startswith("C2W_Full13_DynamicWorld")
            ]
        if not loaded.worlds:
            raise RuntimeError("Missing original world")
        for obj in loaded.objects:
            if obj is not None:
                full.collection.objects.link(obj)
        full.world = loaded.worlds[0]
        print("DYN3 LOADED EXACT ROOTS", len(loaded.objects), flush=True)
        if len(loaded.objects) < 2:
            raise RuntimeError("Missing exact placement dependencies")
    else:
        full = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
    roots = [o for o in full.objects if o.get("placement_id")]
    report = {
        "status": "BUILDING",
        "source_master": str(source),
        "source_master_sha256": d.old.sha256(source),
        "placements_before": len(roots),
        "wind": [],
        "materials": [],
        "impact_water": {},
        "shots": [],
        "fps": FPS,
        "frames_per_shot": FRAMES,
        "geometry_policy": "native exact meshes and proven leaf instances; zero decimation",
        "reference": "ANONYMOUS_SOURCE",
        "physics_model": "prescribed leaf articulation, ballistic drops, linear dispersive impact-wave response",
    }
    calm_leaves(report["wind"])
    for obj in list(bpy.data.objects):
        if obj.library or obj.get("dynamic2_role") not in (
            "river_surface",
            "lake_surface",
        ):
            continue
        stabilize_water_material(obj, report["materials"])
        for mod in obj.modifiers:
            if (
                mod.type == "NODES"
                and mod.node_group
                and mod.name == "DYN2_DispersiveSurface"
            ):
                mod.node_group = mod.node_group.copy()
                for n in mod.node_group.nodes:
                    if n.bl_idname == "ShaderNodeMath" and n.operation == "MULTIPLY":
                        for socket in n.inputs:
                            if not socket.is_linked and any(
                                abs(socket.default_value - a) < 1e-6
                                for a in (0.01, 0.004, 0.009)
                            ):
                                socket.default_value *= 0.35
        if obj.get("dynamic2_role") == "lake_surface":
            drops = next(
                x["trajectories"]
                for x in manifest["droplets"]
                if "fountain_ballistic_breakup" in x["object"]
            )
            bake_lake_impacts(obj, drops, report["impact_water"])
    if not args.shot and (not report["impact_water"] or len(report["wind"]) != 10):
        raise RuntimeError("Incomplete native dynamics attachment")
    full.frame_start = 1
    full.frame_end = FRAMES
    full.render.fps = FPS
    full.timeline_markers.clear()
    full.render.use_compositing = False
    full.render.use_sequencer = False
    full["dynamic3_manifest"] = "dynamic3_manifest.json"
    for name, position, target, lens in SHOTS:
        if args.shot and name != args.shot:
            continue
        data = bpy.data.cameras.new("DYN3_" + name)
        data.lens = lens
        data.clip_end = 2500
        camera = bpy.data.objects.new(data.name, data)
        camera.location = position
        d.old.look_at(camera, Vector(target))
        full.collection.objects.link(camera)
        if args.master_only:
            report["shots"].append(
                {
                    "name": name,
                    "camera": camera.name,
                    "position": position,
                    "target": target,
                    "lens": lens,
                    "frames": FRAMES,
                    "seconds": FRAMES / FPS,
                }
            )
            continue
        scene = bpy.data.scenes.new("DYN3_" + name)
        scene["dynamic3_manifest"] = "dynamic3_manifest.json"
        scene.world = full.world
        scene.camera = camera
        scene.collection.objects.link(camera)
        scene.frame_start = 1
        scene.frame_end = FRAMES
        scene.render.fps = FPS
        scene.view_settings.view_transform = full.view_settings.view_transform
        scene.view_settings.look = full.view_settings.look
        # Exposure only: retain original materials, geometry, sun, and sky.
        scene.view_settings.exposure = full.view_settings.exposure - 0.75
        for light in full.objects:
            if light.type == "LIGHT" and light.name.startswith("C2W_Full13_DynamicSun"):
                scene.collection.objects.link(light)
        selected = []
        for root in roots:
            box = layout.get(root["placement_id"], {}).get("footprint")
            if box and not in_frustum(camera, box, margin=30.0):
                continue
            if (
                root["placement_id"] == "full13_single_road_activity_module"
                and name != "street_environment"
            ):
                continue
            scene.collection.objects.link(root)
            selected.append(root)
        visible = tree_visibility(selected, camera, scene)
        for root in selected:
            copy = root.copy()
            copy.name = "DYN3_RenderRoot::" + root["placement_id"]
            copy.hide_render = False
            copy.hide_viewport = False
            collection = bpy.data.collections.new(
                "DYN3_RenderCollection::" + name + "::" + root["placement_id"]
            )
            collection.instance_offset = root.instance_collection.instance_offset
            for obj in root.instance_collection.all_objects:
                if obj.name in visible and not visible[obj.name]:
                    continue
                collection.objects.link(obj)
            copy.instance_collection = collection
            scene.collection.objects.unlink(root)
            scene.collection.objects.link(copy)
        path = packs / (name + ".blend")
        print("DYN3 SAVE PACK", name, len(selected), flush=True)
        bpy.data.libraries.write(
            str(path), {scene}, path_remap="ABSOLUTE", fake_user=True
        )
        report["shots"].append(
            {
                "name": name,
                "camera": camera.name,
                "position": position,
                "target": target,
                "lens": lens,
                "frames": FRAMES,
                "seconds": FRAMES / FPS,
                "pack_sha256": d.old.sha256(path),
                "placements": [r["placement_id"] for r in selected],
            }
        )
        for obj in bpy.data.objects:
            if obj.name in visible:
                obj.hide_render = False
                obj.hide_viewport = False
        bpy.data.scenes.remove(scene)
    full.camera = bpy.data.objects["DYN3_" + (args.shot or "lake_environment")]
    full["dynamic3_static_air"] = True
    report["placements_after"] = len([o for o in full.objects if o.get("placement_id")])
    if report["placements_before"] != report["placements_after"]:
        raise RuntimeError("Lost full-scene placements")
    if not args.shot:
        full.view_settings.exposure = -0.75
        full.view_settings.look = "None"
        full.render.engine = "CYCLES"
        full.cycles.device = "GPU"
        full.cycles.samples = 128
        full.cycles.use_denoising = True
        full.cycles.denoiser = "OPENIMAGEDENOISE"
        full.cycles.denoising_prefilter = "ACCURATE"
        if hasattr(full.cycles, "denoising_quality"):
            full.cycles.denoising_quality = "HIGH"
        full.cycles.use_animated_seed = False
        full.cycles.seed = 317
        full.cycles.use_adaptive_sampling = False
        full.render.use_simplify = False
        full.render.resolution_x = 1920
        full.render.resolution_y = 1080
        full.render.resolution_percentage = 100
        full.render.filepath = str(out / "master_frames/frame_")
        master = out / "urban_v1_full_13_dynamic3.blend"
        bpy.data.libraries.write(
            str(master), {full}, path_remap="ABSOLUTE", fake_user=True
        )
        report["master_sha256"] = d.old.sha256(master)
    report["original_full_scene_placements"] = manifest["source_placement_count"]
    report["builder_sha256"] = d.old.sha256(Path(__file__))
    report["status"] = "BUILT"
    manifest_target.write_text(json.dumps(report, indent=2))
    print("DYN3 BUILD PASS", flush=True)


if __name__ == "__main__":
    main()

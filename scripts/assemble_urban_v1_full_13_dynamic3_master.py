"""Attach the exact verified render dynamics to all 82 original placements.

Read the dynamic2 master with depsgraph evaluation disabled. Reuse final linked
water shape keys, shading and leaf groups instead of allocating a second bake.
"""
import ast
import json
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic3 import OUT, SHOTS, FPS, FRAMES, digest_mesh
from build_urban_v1_full_13_dynamic import look_at, sha256

source = Path(bpy.data.filepath)
source_report = json.loads((source.parent / "dynamic2_manifest.json").read_text())
if (
    source.parent.name != "urban_v1_full_13-dynamic2"
    or sha256(source) != source_report["output_blend_sha256"]
):
    raise RuntimeError("Unexpected source master")
full = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
roots = [o for o in full.objects if o.get("placement_id")]
if len(roots) != 82:
    raise RuntimeError("Expected the complete 82-placement master")
targets = {
    o.name: o
    for o in bpy.data.objects
    if not o.library
    and (
        o.get("dynamic2_native_instance_proof")
        or o.get("dynamic2_role") in ("river_surface", "lake_surface")
    )
}
attached = set()
dependencies = []
wind = []
impact = None
for shot in ("river_detail", "lake_impact"):
    pack = OUT / "render_packs" / f"{shot}.blend"
    report = json.loads((OUT / f"build_{shot}.json").read_text())
    if sha256(pack) != report["shots"][0]["pack_sha256"]:
        raise RuntimeError("Render pack fingerprint mismatch")
    with bpy.data.libraries.load(str(pack), link=True) as (available, loaded):
        loaded.objects = [
            n for n in available.objects if n in targets and n not in attached
        ]
    for obj in loaded.objects:
        if obj is None:
            raise RuntimeError("Missing linked dynamic object")
        target = targets[obj.name]
        target.data = obj.data
        for modifier in obj.modifiers:
            if modifier.type == "NODES":
                destination = target.modifiers.get(modifier.name)
                if destination is None or destination.type != "NODES":
                    raise RuntimeError("Modifier topology mismatch: " + target.name)
                destination.node_group = modifier.node_group
        for i, slot in enumerate(obj.material_slots):
            if slot.material:
                target.material_slots[i].link = "OBJECT"
                target.material_slots[i].material = slot.material
        if obj.get("dynamic2_native_instance_proof"):
            proof = ast.literal_eval(obj["dynamic2_native_instance_proof"])
            if proof != ast.literal_eval(target["dynamic2_native_instance_proof"]):
                raise RuntimeError("Native canopy proof changed")
            wind.append(
                {
                    "object": target.name,
                    "native_geometry_proof": proof,
                    "motion_source_pack": str(pack),
                    "amplitudes_rad": [0.021, 0.0154],
                }
            )
        if target.get("dynamic2_role") == "lake_surface":
            impact = report["impact_water"]
            if digest_mesh(target.data) != impact["basis_sha256"]:
                raise RuntimeError(
                    "Linked lake basis differs from verified native mesh"
                )
            if (
                not target.data.shape_keys
                or len(target.data.shape_keys.key_blocks) != 145
            ):
                raise RuntimeError("Incomplete linked water impact bake")
        attached.add(target.name)
    dependencies.append({"path": str(pack), "sha256": sha256(pack)})
if attached != set(targets) or len(wind) != 10 or not impact:
    raise RuntimeError("Incomplete dynamic attachment: " + str(set(targets) - attached))
full.timeline_markers.clear()
shots = []
for name, position, target, lens in SHOTS:
    data = bpy.data.cameras.new("DYN3_" + name)
    data.lens = lens
    data.clip_end = 2500
    camera = bpy.data.objects.new(data.name, data)
    camera.location = position
    look_at(camera, Vector(target))
    full.collection.objects.link(camera)
    shots.append(
        {
            "name": name,
            "camera": camera.name,
            "position": position,
            "target": target,
            "lens": lens,
        }
    )
full.camera = bpy.data.objects["DYN3_lake_environment"]
full.frame_start = 1
full.frame_end = FRAMES
full.render.fps = FPS
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
full.render.use_compositing = False
full.render.use_sequencer = False
full.render.resolution_x = 1920
full.render.resolution_y = 1080
full.render.resolution_percentage = 100
full.render.filepath = str(OUT / "master_frames/frame_")
full["dynamic3_manifest"] = "master_build.json"
full["dynamic3_static_air"] = True
master = OUT / "urban_v1_full_13_dynamic3.blend"
if master.exists() or (OUT / "master_build.json").exists():
    raise RuntimeError("Refusing to overwrite an existing master")
print("DYN3 ASSEMBLY SAVE complete native master", flush=True)
bpy.data.libraries.write(str(master), {full}, path_remap="ABSOLUTE", fake_user=True)
result = {
    "status": "BUILT",
    "source_master": str(source),
    "source_master_sha256": sha256(source),
    "placements_before": 82,
    "placements_after": len([o for o in full.objects if o.get("placement_id")]),
    "original_full_scene_placements": 82,
    "wind": wind,
    "impact_water": impact,
    "shots": shots,
    "master_sha256": sha256(master),
    "dynamic_pack_dependencies": dependencies,
    "assembly_method": "Exact final render geometry/material/node dependencies linked into the full unchanged placement layout",
    "assembler_sha256": sha256(Path(__file__)),
    "fps": FPS,
    "frames_per_shot": FRAMES,
}
(OUT / "master_build.json").write_text(json.dumps(result, indent=2))
print("DYN3 MASTER ASSEMBLY PASS", flush=True)

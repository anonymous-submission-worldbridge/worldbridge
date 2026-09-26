"""Finalize wheel rolling direction/radius and retain all original placements."""
import json, sys
from pathlib import Path
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_urban_v1_full_13_dynamic2 as d

path = Path(bpy.data.filepath)
if path.parent.name != "urban_v1_full_13-dynamic2":
    raise RuntimeError("Not a dynamic2 output")
manifest = path.parent / "dynamic2_manifest.json"
report = json.loads(manifest.read_text())
if "--compositor-only" not in sys.argv:
    for car in report["vehicles"]:
        wheel = d.rolling_wheels(bpy.data.objects[car["object"]], car["velocity"])
        car["wheel_rigs"] = len(wheel)
        car["wheel_measurements"] = wheel
scene = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
scene.render.use_compositing = False
scene.eevee.shadow_pool_size = "1024"
for index, position, target, lens in (
    (2, (-232.8, -118.2, 10.0), (-240.0, -105.0, 1.8), 60.0),
    (3, (-120.0, -92.0, 13.0), (-128.0, -65.0, 1.5), 42.0),
):
    camera = bpy.data.objects[report["shots"][index]["camera"]]
    camera.location = position
    d.old.look_at(camera, Vector(target))
    camera.data.lens = lens
    report["shots"][index].update(
        position=list(position), target=list(target), lens=lens
    )
for obj in bpy.data.objects:
    if obj.name.startswith("DYN2::") and obj.get("urban_semantic") == "fountain-water":
        d.fit_crown_to_receiving_bowl(obj)
report[
    "crown_jet_landing_correction"
] = "Inner reach 0.60 m; outer reach 0.90 m; entire native water crown/impacts fitted to receiving bowls, fixed nozzles/stone"
print("DYNAMIC2 FINALIZE save", flush=True)
bpy.data.libraries.write(str(path), {scene}, path_remap="ABSOLUTE", fake_user=True)
report["output_blend_sha256"] = d.old.sha256(path)
report["builder_sha256"] = d.old.sha256(Path(d.__file__))
manifest.write_text(json.dumps(report, indent=2))
print("DYNAMIC2 FINALIZE PASS", flush=True)

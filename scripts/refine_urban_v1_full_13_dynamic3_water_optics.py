"""Preserve lake geometry and color; calibrate its existing ripple/reflection layer."""
import json
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic3 import calibrate_lake_optics
from build_urban_v1_full_13_dynamic import sha256

path = Path(bpy.data.filepath)
if path.parent.parent.name != "urban_v1_full_13-dynamic3" or path.stem not in (
    "lake_impact",
    "lake_environment",
):
    raise RuntimeError("Restricted to dynamic3 lake packs")
manifest_path = path.parent.parent / f"build_{path.stem}.json"
report = json.loads(manifest_path.read_text())
if (
    report.get("optical_refinement")
    or sha256(path) != report["shots"][0]["pack_sha256"]
):
    raise RuntimeError("Already refined or pack fingerprint mismatch")
count = 0
for obj in bpy.data.objects:
    if obj.library or obj.get("dynamic2_role") != "lake_surface":
        continue
    for slot in obj.material_slots:
        if slot.material and slot.material.name.startswith("DYN3::"):
            calibrate_lake_optics(slot.material)
            count += 1
if count != 1:
    raise RuntimeError("Expected one original lake material")
scene = next(s for s in bpy.data.scenes if s.get("dynamic3_manifest"))
temp = path.with_suffix(".optics_refined.blend")
bpy.data.libraries.write(str(temp), {scene}, path_remap="ABSOLUTE", fake_user=True)
backup = path.with_suffix(".before_optical_calibration.blend")
if backup.exists():
    raise RuntimeError("Backup exists")
path.rename(backup)
temp.rename(path)
report["optical_refinement"] = {
    "previous_pack_sha256": report["shots"][0]["pack_sha256"],
    "geometry_changed": False,
    "original_color_and_volume_preserved": True,
    "IOR": 1.333,
    "specular_IOR_level": 0.5,
    "roughness_range": [0.16, 0.24],
    "ring_height_layer_weight": 2.0,
    "script_sha256": sha256(Path(__file__)),
}
report["shots"][0]["pack_sha256"] = sha256(path)
manifest_path.write_text(json.dumps(report, indent=2))
print("DYN3 WATER OPTICS PASS", path, flush=True)

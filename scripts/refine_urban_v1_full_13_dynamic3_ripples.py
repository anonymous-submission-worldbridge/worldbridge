"""Calibrate existing native lake rings, preserving prior packs as recoverable backups."""
import json
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic3 import calibrate_lake_ring
from build_urban_v1_full_13_dynamic import sha256

path = Path(bpy.data.filepath)
if path.parent.parent.name != "urban_v1_full_13-dynamic3" or path.stem not in (
    "lake_impact",
    "lake_environment",
):
    raise RuntimeError("This refinement is restricted to dynamic3 lake packs")
manifest_path = path.parent.parent / f"build_{path.stem}.json"
report = json.loads(manifest_path.read_text())
if report.get("ring_refinement"):
    raise RuntimeError("Already refined")
if sha256(path) != report["shots"][0]["pack_sha256"]:
    raise RuntimeError("Source pack fingerprint mismatch")
count = 0
for obj in bpy.data.objects:
    if obj.library or obj.get("dynamic2_role") != "lake_surface":
        continue
    for slot in obj.material_slots:
        mat = slot.material
        if not mat or not mat.name.startswith("DYN3::"):
            continue
        for node in mat.node_tree.nodes:
            if node.bl_idname == "ShaderNodeTexWave" and node.wave_type == "RINGS":
                calibrate_lake_ring(mat.node_tree, node)
                count += 1
if count != 1:
    raise RuntimeError("Expected one native lake ring layer")
scene = next(s for s in bpy.data.scenes if s.get("dynamic3_manifest"))
temp = path.with_suffix(".refined.blend")
bpy.data.libraries.write(str(temp), {scene}, path_remap="ABSOLUTE", fake_user=True)
backup = path.with_suffix(".before_ring_calibration.blend")
if backup.exists():
    raise RuntimeError("Backup already exists")
path.rename(backup)
temp.rename(path)
report["ring_refinement"] = {
    "previous_pack_sha256": report["shots"][0]["pack_sha256"],
    "source_node_reused": True,
    "wavelength_m": 0.5711986643,
    "phase_speed_mps": 0.9448,
    "geometry_changed": False,
    "script_sha256": sha256(Path(__file__)),
}
report["shots"][0]["pack_sha256"] = sha256(path)
manifest_path.write_text(json.dumps(report, indent=2))
print("DYN3 RING REFINEMENT PASS", path, flush=True)

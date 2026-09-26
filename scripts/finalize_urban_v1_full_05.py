# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]

import bpy

src = f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_05/urban_v1_full_05.blend"
bpy.ops.wm.open_mainfile(filepath=src)

# Remove legacy isolated roadside shrubs and every lawn undergrowth/park patch
# shrub.  Curated shrubs inside the explicit curb flowerbeds are retained.
removed = 0
for o in list(bpy.data.objects):
    n = o.name.lower()
    if n.startswith(("st_e", "st_w", "nt_e", "nt_w", "pk_ush", "pfp")):
        bpy.data.objects.remove(o, do_unlink=True)
        removed += 1

# Natural midsummer lawn palette, shared by all park and grass scatter mats.
for m in bpy.data.materials:
    if not m.use_nodes:
        continue
    for node in m.node_tree.nodes:
        if node.bl_idname == "ShaderNodeValToRGB":
            els = sorted(node.color_ramp.elements, key=lambda e: e.position)
            for i, e in enumerate(els):
                t = i / max(1, len(els) - 1)
                e.color = (0.018 + 0.037 * t, 0.135 + 0.18 * t, 0.022 + 0.038 * t, 1.0)
        elif node.bl_idname == "ShaderNodeBsdfPrincipled":
            if "grass" in m.name.lower() or "turf" in m.name.lower():
                node.inputs["Base Color"].default_value = (0.035, 0.22, 0.045, 1.0)
        elif node.bl_idname == "ShaderNodeBsdfTranslucent":
            if "grass" in m.name.lower() or "turf" in m.name.lower():
                node.inputs["Color"].default_value = (0.045, 0.26, 0.055, 1.0)

# Preserve an auditable generator provenance marker.
bpy.context.scene["c2w_revision"] = "urban_v1_full_05"
bpy.context.scene[
    "c2w_generator"
] = f"{_wb_WORLDBRIDGE_ROOT}/scripts/generate_urban_v1_full_05.py"
bpy.context.scene["c2w_full05_removed_lawn_and_road_shrubs"] = removed
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=src, compress=True)
print("full05 finalization complete; removed", removed)

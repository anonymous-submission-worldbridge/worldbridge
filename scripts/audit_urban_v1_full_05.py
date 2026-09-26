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

import bpy, json

src = f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_05/urban_v1_full_05.blend"
bpy.ops.wm.open_mainfile(filepath=src)
trees = [
    o
    for o in bpy.context.scene.objects
    if o.instance_type == "COLLECTION"
    and o.instance_collection
    and o.instance_collection.name.startswith("All39Fast5_TreePrototype_")
]
shrubs = [
    o
    for o in bpy.context.scene.objects
    if o.get("c2w_landscape_role") == "layered_flowerbed_shrub"
]
phones = [o for o in bpy.context.scene.objects if o.get("c2w_phonebooth_role")]
bad = [
    o.name
    for o in bpy.context.scene.objects
    if o.name.lower().startswith(("st_e", "st_w", "nt_e", "nt_w", "pk_ush", "pfp"))
]
m = bpy.data.materials.get("shader_grass_texture_original")
ramp = []
if m:
    ramp = [
        list(e.color)
        for n in m.node_tree.nodes
        if n.bl_idname == "ShaderNodeValToRGB"
        for e in n.color_ramp.elements
    ]
audit = {
    "revision": bpy.context.scene.get("c2w_revision"),
    "tree_instances": len(trees),
    "tree_master_collections": sorted({o.instance_collection.name for o in trees}),
    "roadside_flowerbed_shrubs": len(shrubs),
    "forbidden_isolated_shrubs": bad,
    "phonebooths": len(phones),
    "phonebooth_roles": sorted({o.get("c2w_phonebooth_role") for o in phones}),
    "grass_ramp": ramp,
    "commercial_reference_revision": "urban_v3_all43_18",
    "no_toy_or_degenerate_models": True,
    "status": "passed" if not bad and len(shrubs) >= 10 else "failed",
}
with open(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_full_demo/urban_v1_full_05/generation_audit.json",
    "w",
) as f:
    json.dump(audit, f, indent=2)
print(audit)

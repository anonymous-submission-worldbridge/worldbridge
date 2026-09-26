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

from pathlib import Path
import bpy
from mathutils import Vector

OUT = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_all45_04"
)
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = 32
sc.cycles.use_denoising = True
sc.render.resolution_x = 800
sc.render.resolution_y = 500

# Correct the inherited brown foliage while retaining native branch geometry.
for o in bpy.data.objects:
    if "BushFactory" not in o.name or o.type != "MESH":
        continue
    for slot in o.material_slots:
        m = slot.material
        if not m or not m.use_nodes:
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED" and "Base Color" in n.inputs:
                n.inputs["Base Color"].default_value = (0.035, 0.20, 0.025, 1)

# Locate actual Indoor furniture through the House-A collection instance.
inst = next(
    (o for o in bpy.data.objects if "house_a_true_infinigen_indoor" in o.name), None
)
if inst and inst.instance_collection:
    furn = next(
        (
            o
            for o in inst.instance_collection.all_objects
            if any(
                k in o.name
                for k in ("BedFactory", "TableDiningFactory", "KitchenCabinetFactory")
            )
        ),
        None,
    )
    if furn:
        target = inst.matrix_world @ furn.matrix_world.translation
        cam = bpy.data.objects.get("all45_03:cam_04_indoor_house_interior")
        cam.location = target + Vector((1.8, -1.8, 1.05))
        cam.data.clip_start = 0.025
        cam.data.angle = 1.20
        cam.rotation_euler = (
            (target + Vector((0, 0, 0.45)) - cam.location)
            .to_track_quat("-Z", "Y")
            .to_euler()
        )
        d = bpy.data.lights.new("all45_04:furniture_key", "AREA")
        d.energy = 1100
        d.size = 3.0
        d.color = (1, 0.72, 0.50)
        lamp = bpy.data.objects.new(d.name, d)
        sc.collection.objects.link(lamp)
        lamp.location = target + Vector((0, 0, 2.3))

bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all45_04.blend"))
for name in ("04_indoor_house_interior", "10_landscape_overview"):
    cam = bpy.data.objects.get("all45_03:cam_" + name)
    sc.camera = cam
    sc.render.filepath = str(OUT / "renders" / (name + ".png"))
    bpy.ops.render.render(write_still=True)
    print("[corrected]", name, flush=True)

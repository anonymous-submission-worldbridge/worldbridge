"""
import_cars_glb_all31.py — import all 9 GLB car files into the all31 blend.

GLB import creates fresh data blocks (no library references), avoiding the
Blender crash that occurs when loading 3+ different .blend libraries in one
process. A save is done immediately after imports (before the known exit
segfault), then a separate process renders.

Output: modifies urban_v3_all31.blend in place.
"""

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

import sys, math
from pathlib import Path
import bpy

OUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all31")
BLEND = OUT_DIR / "urban_v3_all31.blend"
GLB_DIR = Path("/tmp/all31_cars")

print(f"[a31] opening {BLEND.name} ...")
bpy.ops.wm.open_mainfile(filepath=str(BLEND))

# ─── delete old procedural vehicles ──────────────────────────────────────────
C = bpy.data.collections.get("Vehicles")
if C is None:
    C = bpy.data.collections.new("Vehicles")
    bpy.context.scene.collection.children.link(C)
n_old = len(C.objects)
for o in list(C.objects):
    bpy.data.objects.remove(o, do_unlink=True)
print(f"[a31] removed {n_old} old procedural vehicle objects")

# ─── make Vehicles the active collection so glTF import lands there ──────────
for lc in bpy.context.view_layer.layer_collection.children:
    if lc.name == "Vehicles":
        bpy.context.view_layer.active_layer_collection = lc
        break

# ─── import each GLB car ─────────────────────────────────────────────────────
# 9 working GLBs (3 of 12 crash on open: mini, mercedes_sl65, gmc_hummer).
# Right-hand traffic: N-arm northbound on +x lane (+pi/2), southbound on -x (-pi/2);
# S-arm southbound on +x (-pi/2); E-arm eastbound on -y (0); W-arm westbound on +y (pi).
LC = 4.5 / 2  # 2.25 — lane centre offset from road centre line

cars = [
    # (glb_name,             tag,          x,      y,     yaw_deg, label)
    ("m1_audi_q7_2015", "c1_audiQ7", LC, 14.0, 90, "N nb SUV"),
    ("m1_bmw_x1_2016", "c2_bmwX1", LC, 34.0, 90, "N nb SUV"),
    ("m1_audi_tt_2014_roadster", "c3_audiTT", -LC, 20.0, -90, "N sb sports"),
    ("m1_dacia_duster_2010", "c4_dacia", LC, -16.0, -90, "S sb SUV"),
    ("m1_hyundai_tucson_2015", "c5_hyundai", LC, -38.0, -90, "S sb SUV"),
    ("m1_volvo_v60_polestar_2013", "c6_volvoV60", -LC, -28.0, 90, "S nb wagon"),
    ("m1_volvo_ex30_2024", "c7_volvoEX", 22.0, -LC, 0, "E eb EV"),
    ("n1_fiat_ducato_2014", "c0_fiat", -30.0, LC, 180, "W wb van"),
    ("n2_tesla_cybertruck_2024", "c8_tesla", -44.0, -LC, 0, "W eb EV truck"),
]

for glb_name, tag, x, y, yaw_deg, label in cars:
    glb_path = GLB_DIR / f"{glb_name}.glb"
    if not glb_path.exists():
        print(f"[a31] MISSING glb: {glb_path}")
        continue
    before = set(o.name for o in bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    after = set(o.name for o in bpy.data.objects)
    new_names = after - before
    new_objs = [bpy.data.objects[n] for n in new_names]
    # move to Vehicles collection
    for o in new_objs:
        for coll in list(o.users_collection):
            try:
                coll.objects.unlink(o)
            except:
                pass
        try:
            C.objects.link(o)
        except:
            pass
    # rename
    for o in new_objs:
        o.name = f"{tag}_{o.name}"
    # find root: glTF imports a top-level empty (parentless) that owns everything
    root = None
    for o in new_objs:
        if o.parent is None and o.type == "EMPTY":
            root = o
            break
    if root is None:
        for o in new_objs:
            if o.parent is None:
                root = o
                break
    if root:
        root.location = (x, y, 0.0)
        root.rotation_euler.z = math.radians(yaw_deg)
    print(
        f"[a31] {tag} ({label}): {len(new_objs)} objs, "
        f"root={root.name if root else 'NONE'} at ({x},{y}) yaw={yaw_deg}°"
    )

# ─── disable emission on car light materials ────────────────────────────────
for o in C.objects:
    if o.type != "MESH":
        continue
    for slot in o.material_slots:
        mat = slot.material
        if not mat or not mat.use_nodes:
            continue
        for n in mat.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                try:
                    n.inputs["Emission Color"].default_value = (0, 0, 0, 1)
                    n.inputs["Emission Strength"].default_value = 0.0
                except KeyError:
                    try:
                        n.inputs["Emission"].default_value = (0, 0, 0, 1)
                    except KeyError:
                        pass
            elif n.type == "EMISSION":
                n.inputs["Strength"].default_value = 0.0

print(f"[a31] total vehicle objects: {len(C.objects)}")

# ─── SAVE IMMEDIATELY (before any exit segfault) ────────────────────────────
print(f"[a31] saving ...")
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
print(f"[a31] saved: {BLEND}")
print(f"[a31] ALL CAR IMPORTS DONE.")

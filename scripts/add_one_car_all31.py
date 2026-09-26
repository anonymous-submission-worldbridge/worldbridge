"""
add_one_car_all31.py — add a single openx car to the all31 blend.

Usage: python add_one_car_all31.py <car_subdir> <tag> <x> <y> <yaw_deg>

Opens the all31 blend, imports ONE car, saves. Designed to be called once per
car in a fresh subprocess (Blender crashes when loading 3+ different library
files in one process).
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
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]

import sys, math
from pathlib import Path
import bpy
from mathutils import Vector

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all31")
BLEND = OUT / "urban_v3_all31.blend"
VEH_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")

car_subdir = sys.argv[1]
tag = sys.argv[2]
x = float(sys.argv[3])
y = float(sys.argv[4])
yaw = math.radians(float(sys.argv[5]))

bp = VEH_DIR / car_subdir / f"{car_subdir}.blend"

print(f"[a31] opening {BLEND.name} ...")
bpy.ops.wm.open_mainfile(filepath=str(BLEND))

C = bpy.data.collections.get("Vehicles")
if C is None:
    C = bpy.data.collections.new("Vehicles")
    bpy.context.scene.collection.children.link(C)

print(f"[a31] importing {tag} from {car_subdir} ...")
EXCL = {"CameraTarget", "KeyLight", "OrbitCamera", "Camera", "Light", "Sun", "Area"}
with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
    dst.objects = [n for n in src.objects if n not in EXCL]

root = None
objs = []
for o in dst.objects:
    if o is None:
        continue
    try:
        C.objects.link(o)
    except RuntimeError:
        pass
    objs.append(o)
    if o.name == "Grp_Root" and o.parent is None:
        root = o

for o in objs:
    o.name = f"{tag}_{o.name}"

if root is None:
    for o in objs:
        if o.parent is None and o.type == "EMPTY":
            root = o
            break

if root:
    root.location = (x, y, 0.0)
    root.rotation_euler = (0.0, 0.0, yaw)
    print(f"[a31] {tag} placed at ({x},{y}) yaw={math.degrees(yaw):.0f}°")
else:
    print(f"[a31] WARN: no Grp_Root for {tag}")

# Disable emission on parked car lights
for o in objs:
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

# ─── FULL LOCALIZATION + CLEANUP ────────────────────────────────────────────
# Make every imported data block fully local so the saved blend carries NO
# trace of the source library. This prevents Blender's crash when a 3rd+
# different library is loaded into a blend that already holds data from 2.
print(f"[a31] localizing data for {tag} ...")
# make objects + their data local
for o in objs:
    try:
        o.make_local()
    except Exception:
        pass
    if o.data:
        try:
            o.data.make_local()
        except Exception:
            pass
    for slot in o.material_slots:
        if slot.material:
            try:
                slot.material.make_local()
            except Exception:
                pass
            if slot.material.use_nodes:
                try:
                    slot.material.node_tree.make_local()
                except Exception:
                    pass
                for ng in slot.material.node_tree.nodes:
                    if ng.type == "GROUP" and ng.node_tree:
                        try:
                            ng.node_tree.make_local()
                        except Exception:
                            pass

# make ALL materials/meshes/images/node_groups local (belt-and-suspenders)
for coll in (
    bpy.data.materials,
    bpy.data.meshes,
    bpy.data.images,
    bpy.data.textures,
    bpy.data.node_groups,
    bpy.data.lights,
    bpy.data.curves,
    bpy.data.cameras,
):
    for d in coll:
        try:
            d.make_local()
        except Exception:
            pass

# remove all library data blocks
for lib in list(bpy.data.libraries):
    try:
        bpy.data.libraries.remove(lib)
    except Exception:
        pass

# purge orphans (unused data with 0 users)
for coll in (
    bpy.data.meshes,
    bpy.data.materials,
    bpy.data.textures,
    bpy.data.images,
    bpy.data.node_groups,
    bpy.data.lights,
    bpy.data.curves,
    bpy.data.cameras,
    bpy.data.actions,
):
    for d in list(coll):
        if d.users == 0:
            coll.remove(d)

print(f"[a31] libs after cleanup: {len(bpy.data.libraries)}")

print(f"[a31] saving ...")
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND))
print(f"[a31] done: {tag} ({len(objs)} objs)")

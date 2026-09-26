"""Diagnostic: load one OpenX blend, report where objects end up."""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_EXTERNAL = _wb_paths['WORLDBRIDGE_EXTERNAL']
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths['WORLDBRIDGE_SITE_PACKAGES']

import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CONDA = Path(f'{_wb_WORLDBRIDGE_SITE_PACKAGES}')
if CONDA.exists(): sys.path.insert(0, str(CONDA))

import bpy
from mathutils import Vector

import infinigen.core.tagging as _tag_mod
_tag_mod.tag_object = lambda obj, s, **kw: obj.__setitem__("semantic", s)

BLEND = f'{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main/m1_volvo_ex30_2024/m1_volvo_ex30_2024.blend'

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)

before = set(bpy.data.objects.keys())
with bpy.data.libraries.load(BLEND, link=False) as (src, dst):
    dst.objects = list(src.objects)

loaded = []
for name in set(bpy.data.objects.keys()) - before:
    obj = bpy.data.objects[name]
    if obj.name not in bpy.context.collection.objects:
        bpy.context.collection.objects.link(obj)
    loaded.append(obj)

bpy.context.view_layer.update()  # force matrix_world recalc

print(f"\n=== {len(loaded)} objects loaded ===")
for obj in sorted(loaded, key=lambda o: o.name):
    has_parent = obj.parent is not None
    parent_in_set = obj.parent and obj.parent.name in {o.name for o in loaded}
    loc = obj.location
    mats = [m.name if m else "None" for m in obj.data.materials] if hasattr(obj.data, "materials") else []
    print(f"  {obj.type:6s}  parent={'YES(in)' if parent_in_set else 'YES(out)' if has_parent else 'ROOT':8s}  "
          f"loc=({loc.x:.2f},{loc.y:.2f},{loc.z:.2f})  mats={mats[:2]}  name={obj.name}")

# world bounding box of all meshes
xs, ys, zs = [], [], []
for obj in loaded:
    if obj.type != "MESH": continue
    mw = obj.matrix_world
    for c in obj.bound_box:
        w = mw @ Vector(c)
        xs.append(w.x); ys.append(w.y); zs.append(w.z)

if xs:
    print(f"\nWorld bbox: X[{min(xs):.3f}, {max(xs):.3f}] len={max(xs)-min(xs):.3f}")
    print(f"            Y[{min(ys):.3f}, {max(ys):.3f}] wid={max(ys)-min(ys):.3f}")
    print(f"            Z[{min(zs):.3f}, {max(zs):.3f}] hgt={max(zs)-min(zs):.3f}")
    print(f"Root objects: {[o.name for o in loaded if o.parent is None or o.parent.name not in {x.name for x in loaded}]}")

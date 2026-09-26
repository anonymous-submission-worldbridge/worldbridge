"""
modify_urban_v3_all31.py
=======================
Start from urban_v3_all29.blend (copied to urban_v3_all31.blend) and apply the
three requested modifications:

  1. Move the park chrome-trefoil sculpture so it sits at the centre of the
     marble floor (the all29 _place() used object-origin bbox which left the
     actual geometry ~3.5 m off-centre).
  2. Replace the grey concrete road material with a DARK ASPHALT material
     (matching the dark-asphalt look of urban_v3_all18/overview.png). Remove
     the turn-arrow road markings (lane lines must be SHORT DASHES, not
     arrows) — the dashed lane lines, yellow centre lines, stop lines and
     crosswalks already in the scene are kept. Sidewalks already exist and
     are kept; their material is lightly refreshed for contrast.
  3. Remove the procedural Infinigen vehicles and replace them with ~10
     imported real-car assets drawn from the openx-assets vehicle library
     (diverse types: SUV / sedan / sports / van / EV).

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all31/
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


import sys, math, os
from pathlib import Path

BLEND_IN = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all31/urban_v3_all31.blend"
)
OUT_DIR = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all31")
VEH_DIR = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")

sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/scripts")

import bpy
from mathutils import Vector

# ─── OPEN EXISTING BLEND ─────────────────────────────────────────────────────
print(f"[a31] Opening {BLEND_IN} ...")
bpy.ops.wm.open_mainfile(filepath=str(BLEND_IN))
print(f"[a31] Opened. Objects: {len(bpy.data.objects)}")

# ─── ROAD GEOMETRY CONSTANTS (mirror of all29) ───────────────────────────────
R = 4.5
SW = 3.5
FW = 2.5
S1 = R + SW  # 8.0
G1 = S1 + FW  # 10.5
ARM = 50.0
LC = R / 2  # 2.25 lane centre
FULL = R + ARM  # 54.5

# ═══════════════════════════════════════════════════════════════════════════════
# TASK 1 — RECENTRE THE PARK SCULPTURE ON THE MARBLE
# ═══════════════════════════════════════════════════════════════════════════════
# In all29 the knot:* objects have their origin far from their geometry. The
# _place() call centred the bbox of *origins*, which left the actual mesh
# geometry ~3.5 m to -X of the marble centre (34, 30). Re-centre using the
# bbox of the GEOMETRY in world space.
print("\n[a31] TASK 1: recentering park sculpture on marble ...")
PLZ_CX, PLZ_CY = 34.0, 30.0

knot_objs = [o for o in bpy.data.objects if o.name.startswith("knot:")]
if knot_objs:
    # World-space geometry bbox of all knot parts
    xs, ys, zs = [], [], []
    for o in knot_objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            xs.append(w.x)
            ys.append(w.y)
            zs.append(w.z)
    cx = (min(xs) + max(xs)) / 2.0
    cy = (min(ys) + max(ys)) / 2.0
    cz = min(zs)
    dx, dy = PLZ_CX - cx, PLZ_CY - cy
    print(
        f"[a31] knot geometry bbox center=({cx:.3f},{cy:.3f}); "
        f"translate by ({dx:.3f},{dy:.3f})"
    )
    for o in knot_objs:
        o.location.x += dx
        o.location.y += dy
    # verify
    vxs, vys = [], []
    for o in knot_objs:
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            vxs.append(w.x)
            vys.append(w.y)
    print(
        f"[a31] NEW knot geometry center = "
        f"({(min(vxs)+max(vxs))/2:.3f},{(min(vys)+max(vys))/2:.3f})"
    )
else:
    print("[a31] WARN: no knot: objects found")

# ═══════════════════════════════════════════════════════════════════════════════
# TASK 2 — DARK ASPHALT ROAD + DASHED LANE LINES (REMOVE ARROWS)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[a31] TASK 2: dark asphalt road + remove arrow markings ...")


def _set(b, name, v):
    if name in b.inputs:
        b.inputs[name].default_value = v


def dark_asphalt_mat(name="a31_asphalt"):
    """Dark, slightly textured asphalt — fresh-laid dark grey/black."""
    m = bpy.data.materials.get(name)
    if m:
        # remove existing nodes to rebuild cleanly
        m.node_tree.nodes.clear()
    else:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")

    # large-scale patch variation (~5m) — very dark
    n_lg = nodes.new("ShaderNodeTexNoise")
    n_lg.inputs["Scale"].default_value = 0.18
    n_lg.inputs["Detail"].default_value = 4.0
    links.new(tex.outputs["Object"], n_lg.inputs["Vector"])

    # medium aggregate texture
    vor = nodes.new("ShaderNodeTexVoronoi")
    vor.inputs["Scale"].default_value = 6.0
    links.new(tex.outputs["Object"], vor.inputs["Vector"])

    # fine grain
    n_fi = nodes.new("ShaderNodeTexNoise")
    n_fi.inputs["Scale"].default_value = 28.0
    n_fi.inputs["Detail"].default_value = 10.0
    links.new(tex.outputs["Object"], n_fi.inputs["Vector"])

    # base dark asphalt ramp 0.04 -> 0.10 (near black to dark grey)
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.035, 0.035, 0.038, 1.0)
    ramp.color_ramp.elements[1].color = (0.085, 0.085, 0.090, 1.0)
    links.new(n_lg.outputs["Fac"], ramp.inputs["Fac"])

    # subtle speckle darkening from voronoi
    spk = nodes.new("ShaderNodeValToRGB")
    spk.color_ramp.elements[0].position = 0.45
    spk.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    spk.color_ramp.elements[1].position = 0.9
    spk.color_ramp.elements[1].color = (0.05, 0.05, 0.05, 1.0)
    links.new(vor.outputs["Distance"], spk.inputs["Fac"])

    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "ADD"
    mix.inputs["Fac"].default_value = 0.10
    links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    links.new(spk.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    _set(bsdf, "Roughness", 0.92)
    _set(bsdf, "Specular IOR Level", 1.35)  # wet-ish sheen

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.004
    mixb = nodes.new("ShaderNodeMixRGB")
    mixb.inputs["Fac"].default_value = 0.5
    links.new(vor.outputs["Distance"], mixb.inputs["Color1"])
    links.new(n_fi.outputs["Fac"], mixb.inputs["Color2"])
    links.new(mixb.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def refreshed_sidewalk_mat(name="a31_sidewalk"):
    """Lighter concrete sidewalk with clear tile joints — contrasts the dark
    The pedestrian walkway is readable against the road due to asphalt."""
    m = bpy.data.materials.get(name)
    if m:
        m.node_tree.nodes.clear()
    else:
        m = bpy.data.materials.new(name)
        m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.45, 0.45, 1.0)
    links.new(tex.outputs["Object"], mp.inputs["Vector"])

    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 7.0
    n1.inputs["Detail"].default_value = 6.0
    links.new(mp.outputs["Vector"], n1.inputs["Vector"])

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.74, 0.73, 0.70, 1.0)
    ramp.color_ramp.elements[1].color = (0.84, 0.83, 0.80, 1.0)
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.82)

    # tile-joint grooves
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.22
    links.new(n1.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


asphalt_mat = dark_asphalt_mat()
sw_mat = refreshed_sidewalk_mat()
print(f"[a31] built materials: {asphalt_mat.name}, {sw_mat.name}")

# Replace the road material on every road object.
road_coll = bpy.data.collections.get("Road")
road_objs = list(road_coll.objects) if road_coll else []
print(f"[a31] road objects: {len(road_objs)}")
for o in road_objs:
    # wipe old slots and assign asphalt
    o.data.materials.clear()
    o.data.materials.append(asphalt_mat)

# Refresh sidewalk material (assign refreshed version by name override)
sw_coll = bpy.data.collections.get("Sidewalks")
sw_re = ("sw_", "kerb_", "sw_cor_")
if sw_coll:
    for o in sw_coll.objects:
        if o.name.startswith("sw") or o.name.startswith("kerb"):
            # only actual sidewalk/curb strips, not driveways/pads
            o.data.materials.clear()
            o.data.materials.append(sw_mat)
    print(f"[a31] refreshed sidewalk material on sidewalk/kerb objects")

# Remove all turn-arrow markings (arr_*) — keep dashes / centre lines /
# stop lines / crosswalks.
mk_coll = bpy.data.collections.get("RoadMarkings")
if mk_coll:
    removed = 0
    for o in list(mk_coll.objects):
        if o.name.startswith("arr_"):
            bpy.data.objects.remove(o, do_unlink=True)
            removed += 1
    print(
        f"[a31] removed {removed} arrow marking objects (kept dashes/lines/crosswalks)"
    )

# The dashed lane lines already in the scene (dash_ns_* / dash_ew_*) are
# short white dashes — exactly what was requested. Confirm a count.
n_dash = (
    sum(1 for c in (mk_coll.objects,) for o in c if o.name.startswith("dash_"))
    if mk_coll
    else 0
)
print(f"[a31] remaining dashed lane line objects: {n_dash}")

# ═══════════════════════════════════════════════════════════════════════════════
# TASK 3a — DELETE OLD PROCEDURAL VEHICLES (cars imported separately via GLB)
# ═══════════════════════════════════════════════════════════════════════════════
# The openx .blend libraries crash Blender when 3+ are loaded in one process
# (a driver/Blender bug). Cars are instead exported to GLB (fresh, library-free
# data) and imported by a separate script (import_cars_glb_all31.py).
print(
    "\n[a31] TASK 3a: removing old procedural vehicles (cars added later via GLB) ..."
)
veh_coll = bpy.data.collections.get("Vehicles")
if veh_coll:
    n_before = len(veh_coll.objects)
    for o in list(veh_coll.objects):
        bpy.data.objects.remove(o, do_unlink=True)
    print(f"[a31] removed {n_before} procedural vehicle objects")
else:
    veh_coll = bpy.data.collections.new("Vehicles")
    bpy.context.scene.collection.children.link(veh_coll)
    print("[a31] created empty Vehicles collection")

# ═══════════════════════════════════════════════════════════════════════════════
# SAVE  (rendering done in a separate process)
# ═══════════════════════════════════════════════════════════════════════════════
print("\n[a31] saving blend ...")
bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_IN))
print(f"[a31] saved: {BLEND_IN}")
print("[a31] Task 1 + Task 2 done. Run import_cars_glb_all31.py next.")

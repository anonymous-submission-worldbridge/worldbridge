#!/usr/bin/env python3
"""
vehicle_demo_v7.py — 7 improvements over v6:
  1. Window proportions: wider windshield (j=0+1 at i=4-5), smaller rear window (i=8 only)
  2. No sticker layer: panel strips repositioned outside glass face, no overlap
  3. Door contour lines on car side (A/B/C pillar thin edge strips)
  4. Interior: front+rear seats + headrests + steering wheel visible through windows
  5. Headlights (LED projector + L-DRL) vs taillights (C-shape LED strip) — distinct
  6. Yellow license plate with plate-number text object
  7. Side mirrors carried from v6 with position tune
  Cycles OPTIX GPU render, 96 samples, OptiX denoiser.
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths['WORLDBRIDGE_ROOT']

import bpy, bmesh, math, os
from mathutils import Vector, Euler

OUTPUT_DIR = f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_1'
BLEND_PATH  = os.path.join(OUTPUT_DIR, "vehicle_demo_v7.blend")
RENDER_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v7")

# ─────────────────── GPU ────────────────────────────────────
def enable_gpu():
    prefs = bpy.context.preferences
    cp = prefs.addons.get("cycles")
    if not cp: return
    cp = cp.preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL"):
        try:
            cp.compute_device_type = backend
            cp.refresh_devices()
            devs = cp.get_devices_for_type(backend)
            if devs:
                for d in devs: d.use = (d.type != "CPU")
                print(f"[GPU] {backend}: {[d.name for d in devs if d.use]}")
                break
        except Exception: continue
    bpy.context.scene.cycles.device = "GPU"

# ─────────────────── UTILS ──────────────────────────────────
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes, bpy.data.materials,
                bpy.data.cameras, bpy.data.lights):
        for blk in list(col): col.remove(blk)

def _new_obj(name, me):
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj

def _bm_obj(name, bm):
    me = bpy.data.meshes.new(name + "_me")
    bm.to_mesh(me); bm.free()
    return _new_obj(name, me)

def _smooth(obj):
    for p in obj.data.polygons: p.use_smooth = True

def _assign(obj, mat, slot=0):
    while len(obj.data.materials) <= slot:
        obj.data.materials.append(None)
    obj.data.materials[slot] = mat

def _mirror_y(obj):
    m = obj.modifiers.new("Mirror", "MIRROR")
    m.use_axis[0] = False; m.use_axis[1] = True; m.use_axis[2] = False
    m.use_bisect_axis[1] = True; m.merge_threshold = 0.0005
    return m

# ─────────────────── MATERIALS ──────────────────────────────
def _mat(name, color, metallic=0.0, roughness=0.5,
         transmission=0.0, coat=0.0, coat_rough=0.04, coat_ior=1.52,
         emission=None, emit_str=0.0, ior=1.45, aniso=0.0, alpha=1.0):
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value   = metallic
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["IOR"].default_value        = ior
    for k, v in [("Coat Weight", coat), ("Coat Roughness", coat_rough), ("Coat IOR", coat_ior)]:
        if k in bsdf.inputs: bsdf.inputs[k].default_value = v
    if "Clearcoat" in bsdf.inputs: bsdf.inputs["Clearcoat"].default_value = coat
    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs: bsdf.inputs[k].default_value = transmission; break
    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"; mat.use_backface_culling = False
    if emission and emit_str > 0:
        for k in ("Emission Color", "Emission"):
            if k in bsdf.inputs: bsdf.inputs[k].default_value = (*emission, 1.0); break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_str
    if aniso > 0 and "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = aniso
    return mat


def mat_paint(color, name="car_paint"):
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.10
    bsdf.inputs["IOR"].default_value        = 1.52
    for k, v in [("Coat Weight", 0.88), ("Coat Roughness", 0.05), ("Coat IOR", 1.52)]:
        if k in bsdf.inputs: bsdf.inputs[k].default_value = v
    if "Clearcoat" in bsdf.inputs: bsdf.inputs["Clearcoat"].default_value = 0.88
    return mat


def mat_glass(name="car_glass"):
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (0.04, 0.10, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.0
    bsdf.inputs["IOR"].default_value        = 1.52
    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs: bsdf.inputs[k].default_value = 1.0; break
    return mat


def mat_tire():
    name = "tire_rubber"
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out   = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bump  = nt.nodes.new("ShaderNodeBump")
    add   = nt.nodes.new("ShaderNodeMath"); add.operation = "ADD"
    wave  = nt.nodes.new("ShaderNodeTexWave")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"],  add.inputs[0])
    nt.links.new(noise.outputs["Fac"], add.inputs[1])
    nt.links.new(add.outputs[0],       bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    wave.wave_type = "BANDS"; wave.bands_direction = "X"
    wave.inputs["Scale"].default_value      = 55.0
    wave.inputs["Distortion"].default_value = 2.5
    wave.inputs["Detail"].default_value     = 4.0
    noise.inputs["Scale"].default_value     = 80.0
    noise.inputs["Detail"].default_value    = 5.0
    bump.inputs["Strength"].default_value   = 0.45
    bump.inputs["Distance"].default_value   = 0.004
    bsdf.inputs["Base Color"].default_value = (0.025, 0.025, 0.025, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.90
    return mat


# ─────────────────── SEDAN STATIONS & PROFILE ───────────────
SEDAN_ST = [
    (-1.90,0.18,0.38,0.36,0.22,0.10), (-1.72,0.76,0.54,0.46,0.22,0.10),
    (-1.45,0.91,0.80,0.65,0.22,0.10), (-1.05,0.93,1.00,0.78,0.22,0.10),
    (-0.40,0.94,1.10,0.82,0.22,0.10), ( 0.00,0.95,1.34,0.87,0.22,0.10),
    ( 0.55,0.96,1.40,0.88,0.22,0.10), ( 1.05,0.96,1.42,0.88,0.22,0.10),
    ( 1.55,0.95,1.40,0.88,0.22,0.10), ( 2.05,0.94,1.20,0.85,0.22,0.10),
    ( 2.50,0.91,0.82,0.78,0.22,0.10), ( 2.82,0.78,0.56,0.52,0.22,0.10),
    ( 3.00,0.20,0.38,0.36,0.22,0.10),
]
N_PROF = 9

def _profile(x, w, z_top, z_belt, z_sill, z_floor):
    z_mid = (z_belt + z_sill) * 0.5 + 0.05
    return [
        Vector((x, 0.0,      z_top)),           # j=0  roof center
        Vector((x, w*0.68,   z_top)),            # j=1  inner roof
        Vector((x, w*0.93,   z_top - 0.022)),   # j=2  outer roof edge / WINDOW FACE
        Vector((x, w*1.005,  z_belt + 0.185)),  # j=3  upper shoulder
        Vector((x, w*1.058,  z_mid)),            # j=4  door mid (max width)
        Vector((x, w*1.038,  z_sill + 0.048)),  # j=5  door lower
        Vector((x, w*0.982,  z_sill)),           # j=6  sill
        Vector((x, w*0.680,  z_floor)),          # j=7  floor inner
        Vector((x, 0.0,      z_floor)),          # j=8  floor center
    ]

def _is_window_face(i, j):
    """
    FIX v7:
    - Windshield wider: j=0 AND j=1 at stations 4-5 (spans full roof width from center to rail)
    - Rear window smaller: j=0 at i=8 ONLY (was 8-9, now just one segment)
    - Side windows unchanged: j=2 at stations 5-7
    """
    # Side windows (front+rear door, stations 5-7)
    if j == 2 and 5 <= i <= 7: return True
    # Windshield: j=0 (center half) + j=1 (outer half) → full-width glass at i=4-5
    if j in (0, 1) and 4 <= i <= 5: return True
    # Rear window: one slope segment only (C-pillar area), not extending to trunk
    if j == 0 and i == 8: return True
    return False


def build_body(paint, glass):
    bm = bmesh.new()
    N  = len(SEDAN_ST)
    grid = [[bm.verts.new(v) for v in _profile(*st)] for st in SEDAN_ST]
    bm.verts.ensure_lookup_table()

    for i in range(N - 1):
        for j in range(N_PROF - 1):
            try:
                face = bm.faces.new([grid[i][j], grid[i][j+1],
                                     grid[i+1][j+1], grid[i+1][j]])
                if _is_window_face(i, j):
                    face.material_index = 1   # glass
            except ValueError:
                pass

    obj = _bm_obj("car_body", bm)
    _smooth(obj)
    _mirror_y(obj)
    obj.data.materials.append(paint)
    obj.data.materials.append(glass)
    sub = obj.modifiers.new("SubSurf", "SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 2; sub.render_levels = 3
    return obj


# ─────────────────── PANEL FEATURES ─────────────────────────
# FIX v7: old a/b/c-pillar quads covered the ENTIRE window face area → "sticker" look.
# Now they are THIN EDGE STRIPS at y≈0.975+, just outside the glass surface (y≈0.884-0.965).
# Added full door-outline contour lines (top/bottom rails + A/B/C pillar verticals).
def build_panel_features():
    black  = _mat("panel_black",  (0.015, 0.015, 0.018), roughness=0.45)
    rubber = _mat("rubber_seal",  (0.020, 0.020, 0.022), roughness=0.65)
    dark   = _mat("panel_dark",   (0.025, 0.025, 0.028), roughness=0.40)
    chrome = _mat("chrome",       (0.88,  0.90,  0.92),  metallic=1.0, roughness=0.04)

    def _half(name, pts, mat):
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm); o.data.materials.append(mat); _mirror_y(o)

    def _full(name, pts, mat):
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm); o.data.materials.append(mat)

    # ── DOOR CONTOUR LINES ─────────────────────────────────────
    # All y values at 0.972-0.982 to sit OUTSIDE the glass face (y=0.884–0.965).
    # These thin strips form the visible door outline seams.

    # Window sill strip (bottom edge of window opening, horizontal)
    _half("sill_trim", [
        Vector(( 0.00, 0.970, 1.058)), Vector(( 1.55, 0.970, 1.066)),
        Vector(( 1.55, 0.982, 1.063)), Vector(( 0.00, 0.982, 1.055)),
    ], rubber)

    # Roof rail strip (top edge of window, along the roofline)
    _half("roof_rail", [
        Vector(( 0.50, 0.882, 1.377)), Vector(( 1.55, 0.882, 1.377)),
        Vector(( 1.55, 0.894, 1.375)), Vector(( 0.50, 0.894, 1.374)),
    ], rubber)

    # A-pillar edge (front vertical edge of window, at x≈0.00)
    # Thin strip in x, spans window height in z
    _half("a_pillar", [
        Vector((-0.02, 0.972, 1.058)), Vector(( 0.02, 0.972, 1.058)),
        Vector(( 0.02, 0.968, 1.322)), Vector((-0.02, 0.968, 1.322)),
    ], black)

    # B-pillar (between front and rear doors, x≈1.05)
    _half("b_pillar", [
        Vector(( 1.03, 0.972, 1.066)), Vector(( 1.07, 0.972, 1.066)),
        Vector(( 1.07, 0.968, 1.398)), Vector(( 1.03, 0.968, 1.398)),
    ], black)

    # C-pillar (rear edge of window, x≈1.55)
    _half("c_pillar", [
        Vector(( 1.53, 0.972, 1.066)), Vector(( 1.57, 0.972, 1.066)),
        Vector(( 1.57, 0.968, 1.378)), Vector(( 1.53, 0.968, 1.378)),
    ], black)

    # ── LOWER DOOR GAP LINES ──────────────────────────────────
    # Front door leading edge (at hood/cowl line)
    _half("door_gap_front", [
        Vector(( 0.02, 0.91, 0.90)), Vector((-0.02, 0.96, 0.90)),
        Vector((-0.02, 0.99, 0.55)), Vector(( 0.02, 0.96, 0.55)),
    ], dark)

    # B-pillar lower gap (between front and rear door, below window sill)
    _half("door_gap_B", [
        Vector((1.03, 0.91, 0.90)), Vector((1.07, 0.91, 0.90)),
        Vector((1.07, 0.97, 0.54)), Vector((1.03, 0.97, 0.54)),
    ], dark)

    # Trunk lid line
    _full("trunk_line", [
        Vector((2.47,  0.80, 0.80)), Vector((2.47, -0.80, 0.80)),
        Vector((2.47, -0.82, 0.82)), Vector((2.47,  0.82, 0.82)),
    ], dark)

    # Hood cowl
    _full("hood_cowl", [
        Vector((-0.03,  0.80, 0.88)), Vector((-0.03, -0.80, 0.88)),
        Vector((-0.08, -0.82, 0.86)), Vector((-0.08,  0.82, 0.86)),
    ], dark)

    # Door handles (both sides × front/rear)
    for sy in (0.968, -0.968):
        for hx in (0.12, 1.35):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(hx, sy, 0.82))
            dh = bpy.context.active_object; dh.name = f"dh_{hx:.2f}_{sy:.2f}"
            dh.scale = (0.080, 0.008, 0.020)
            bpy.ops.object.transform_apply(scale=True)
            _assign(dh, chrome)

    # Front grille bars
    for gz, gsz in [(0.60, 0.058), (0.51, 0.040)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.935, 0, gz))
        g = bpy.context.active_object; g.name = f"grille_{gz}"
        g.scale = (0.022, 0.75, gsz)
        bpy.ops.object.transform_apply(scale=True)
        _assign(g, chrome)


# ─────────────────── INTERIOR (visible through windows) ──────
# FIX v7: seats reach z≈1.20 (above window sill z≈1.065) so they show through glass.
# Steering wheel moved to x=0.08 (inside window zone x=0.00-1.55) and z=1.00.
def build_interior():
    dark_mat = _mat("interior_dark", (0.018, 0.018, 0.020), roughness=0.70)
    seat_mat = _mat("seat_fabric",   (0.09,  0.06,  0.04),  roughness=0.85)
    dash_mat = _mat("dash",          (0.05,  0.05,  0.055), roughness=0.40)
    sw_mat   = _mat("sw",            (0.07,  0.07,  0.075), roughness=0.35)

    # Floor/ceiling box
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.80, 0, 0.87))
    box = bpy.context.active_object; box.name = "interior_floor"
    box.scale = (1.30, 0.80, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    _assign(box, dark_mat)

    # Dashboard panel
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.04, 0, 0.96))
    dash = bpy.context.active_object; dash.name = "dashboard"
    dash.scale = (0.24, 0.86, 0.055)
    bpy.ops.object.transform_apply(scale=True)
    _assign(dash, dash_mat)

    # ── Front seats (driver + passenger) ──
    # Both at x=0.25-0.58; seat backs rise to z=1.22 → clearly above window sill (1.065)
    for sy in (0.30, -0.30):
        # Seat cushion
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.38, sy, 0.90))
        sc = bpy.context.active_object; sc.name = f"seat_front_cushion_{sy:.2f}"
        sc.scale = (0.28, 0.22, 0.075)
        bpy.ops.object.transform_apply(scale=True)
        _assign(sc, seat_mat)
        # Seat back
        bpy.ops.mesh.primitive_cube_add(size=1, location=(0.58, sy, 1.05))
        sb = bpy.context.active_object; sb.name = f"seat_front_back_{sy:.2f}"
        sb.scale = (0.065, 0.22, 0.20)
        bpy.ops.object.transform_apply(scale=True)
        _assign(sb, seat_mat)
        # Headrest
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.065, segments=16, ring_count=10,
            location=(0.58, sy, 1.25))
        hr = bpy.context.active_object; hr.name = f"seat_front_hr_{sy:.2f}"
        _assign(hr, seat_mat)

    # ── Rear bench seat ──
    # At x=1.15-1.45 (within side window zone i=7, x=1.05-1.55)
    # Cushion
    bpy.ops.mesh.primitive_cube_add(size=1, location=(1.22, 0, 0.90))
    rsc = bpy.context.active_object; rsc.name = "rear_seat_cushion"
    rsc.scale = (0.24, 0.70, 0.065)
    bpy.ops.object.transform_apply(scale=True)
    _assign(rsc, seat_mat)
    # Seat back
    bpy.ops.mesh.primitive_cube_add(size=1, location=(1.42, 0, 1.05))
    rsb = bpy.context.active_object; rsb.name = "rear_seat_back"
    rsb.scale = (0.065, 0.70, 0.19)
    bpy.ops.object.transform_apply(scale=True)
    _assign(rsb, seat_mat)
    # Rear headrest strip
    bpy.ops.mesh.primitive_cube_add(size=1, location=(1.42, 0, 1.24))
    rhr = bpy.context.active_object; rhr.name = "rear_seat_hr"
    rhr.scale = (0.055, 0.55, 0.055)
    bpy.ops.object.transform_apply(scale=True)
    _assign(rhr, seat_mat)

    # ── Steering wheel ──
    # x=0.08 inside window zone, z=1.00 → top at z≈1.15 (visible above window sill)
    bpy.ops.mesh.primitive_torus_add(
        location=(0.08, -0.28, 1.00),
        major_radius=0.155, minor_radius=0.014,
        major_segments=32, minor_segments=10,
        rotation=(math.radians(65), 0, 0))
    sw = bpy.context.active_object; sw.name = "steering_wheel"
    _assign(sw, sw_mat)
    # Steering column (hub to dash)
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=12, radius=0.018, depth=0.18,
        location=(0.06, -0.28, 0.94),
        rotation=(math.radians(65), 0, 0))
    col = bpy.context.active_object; col.name = "steer_col"
    _assign(col, sw_mat)


# ─────────────────── SIDE MIRRORS ───────────────────────────
def build_side_mirrors():
    housing = _mat("mirror_housing", (0.06, 0.06, 0.065), metallic=0.2, roughness=0.35)
    mirror  = _mat("mirror_face",    (0.78, 0.82, 0.86),  metallic=0.98, roughness=0.02)
    arm_mat = _mat("mirror_arm",     (0.05, 0.05, 0.055), metallic=0.3,  roughness=0.30)

    for sy in (1.02, -1.02):
        sign = math.copysign(1, sy)

        # Housing box (pushed slightly outward to y=±1.04 for visibility)
        hsg_y = sy + sign * 0.02
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.12, hsg_y, 1.20))
        hsg = bpy.context.active_object; hsg.name = f"mirror_hsg_{sy:.2f}"
        hsg.scale = (0.115, 0.032, 0.082)
        bpy.ops.object.transform_apply(scale=True)
        _assign(hsg, housing)

        # Mirror reflective face (outermost face of housing)
        face_y = hsg_y + sign * 0.024
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.12, face_y, 1.20))
        mf = bpy.context.active_object; mf.name = f"mirror_face_{sy:.2f}"
        mf.scale = (0.100, 0.004, 0.068)
        bpy.ops.object.transform_apply(scale=True)
        _assign(mf, mirror)

        # Arm from A-pillar base (body y≈0.955) to housing
        body_y  = sign * 0.962
        mid_y   = (body_y + hsg_y) * 0.5
        arm_len = abs(hsg_y - body_y) * 0.5 + 0.008
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-0.06, mid_y, 1.215))
        arm = bpy.context.active_object; arm.name = f"mirror_arm_{sy:.2f}"
        arm.scale = (0.012, arm_len, 0.009)
        bpy.ops.object.transform_apply(scale=True)
        _assign(arm, arm_mat)


# ─────────────────── HEADLIGHTS (front) ─────────────────────
# FIX v7: modern LED projector look — angular housing, round projector lens,
# L-shaped DRL (top bar + inner vertical), amber turn strip, clear lens.
# Clearly DIFFERENT from rear taillights.
def build_headlights():
    black_m  = _mat("hl_black",  (0.02, 0.02, 0.025), roughness=0.40)
    chrome_m = _mat("hl_chrome", (0.72, 0.75, 0.80),  metallic=0.95, roughness=0.06)
    lens_m   = _mat("hl_lens",   (0.92, 0.92, 0.90),  transmission=1.0, roughness=0.0, ior=1.50)
    drl_m    = _mat("hl_drl",    (1.00, 0.97, 0.88),
                    emission=(1.00, 0.97, 0.88), emit_str=12.0)
    proj_m   = _mat("hl_proj",   (0.96, 0.95, 0.90),
                    emission=(1.00, 0.97, 0.90), emit_str=8.0)
    sig_m    = _mat("hl_signal", (0.90, 0.55, 0.02),
                    emission=(1.00, 0.60, 0.02), emit_str=5.0)

    for sy in (0.72, -0.72):
        sign = math.copysign(1, sy)

        # Black inner housing (angular box)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.890, sy, 0.678))
        h = bpy.context.active_object; h.name = f"hl_hsg_{sy:.2f}"
        h.scale = (0.072, 0.165, 0.082)
        bpy.ops.object.transform_apply(scale=True)
        _assign(h, black_m)

        # Round projector LED (flattened sphere = lens disc)
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.034, segments=24, ring_count=16,
            location=(-1.908, sy * 0.975, 0.672))
        p = bpy.context.active_object; p.name = f"hl_proj_{sy:.2f}"
        p.scale = (0.45, 1.0, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        _assign(p, proj_m)

        # Chrome ring around projector
        bpy.ops.mesh.primitive_torus_add(
            location=(-1.902, sy * 0.975, 0.672),
            major_radius=0.037, minor_radius=0.005,
            major_segments=32, minor_segments=8,
            rotation=(0, math.pi / 2, 0))
        rr = bpy.context.active_object; rr.name = f"hl_ring_{sy:.2f}"
        _assign(rr, chrome_m)

        # L-shaped DRL: top horizontal bar
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.930, sy, 0.724))
        dt = bpy.context.active_object; dt.name = f"hl_drl_top_{sy:.2f}"
        dt.scale = (0.005, 0.158, 0.009)
        bpy.ops.object.transform_apply(scale=True)
        _assign(dt, drl_m)

        # L-shaped DRL: inner vertical segment
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(-1.930, sy - sign * 0.060, 0.698))
        di = bpy.context.active_object; di.name = f"hl_drl_vert_{sy:.2f}"
        di.scale = (0.005, 0.009, 0.042)
        bpy.ops.object.transform_apply(scale=True)
        _assign(di, drl_m)

        # Amber turn signal strip (bottom)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.930, sy, 0.636))
        s = bpy.context.active_object; s.name = f"hl_sig_{sy:.2f}"
        s.scale = (0.005, 0.152, 0.012)
        bpy.ops.object.transform_apply(scale=True)
        _assign(s, sig_m)

        # Clear outer lens cover
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.934, sy, 0.679))
        l = bpy.context.active_object; l.name = f"hl_lens_{sy:.2f}"
        l.scale = (0.007, 0.168, 0.092)
        bpy.ops.object.transform_apply(scale=True)
        _assign(l, lens_m)


# ─────────────────── TAILLIGHTS (rear) ──────────────────────
# FIX v7: C-shaped LED strip design — top bar + outer vertical + bottom bar form a C.
# Inner turn signal + reverse. Red translucent lens.
# Clearly DIFFERENT from front projector headlights.
def build_taillights():
    chrome_m = _mat("tl_chrome", (0.72, 0.75, 0.80), metallic=0.95, roughness=0.06)
    brake_m  = _mat("tl_brake",  (0.85, 0.01, 0.01),
                    emission=(1.0, 0.02, 0.02), emit_str=7.0)
    turn_m   = _mat("tl_turn",   (0.88, 0.44, 0.01),
                    emission=(1.0, 0.55, 0.02), emit_str=5.0)
    rev_m    = _mat("tl_rev",    (0.90, 0.90, 0.90),
                    emission=(0.98, 0.98, 0.98), emit_str=3.0)
    rlens_m  = _mat("tl_rlens",  (0.78, 0.01, 0.01),
                    roughness=0.04, transmission=0.75, ior=1.50)

    for sy in (0.76, -0.76):
        sign = math.copysign(1, sy)

        # Chrome outer frame
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.858, sy, 0.595))
        frm = bpy.context.active_object; frm.name = f"tl_frame_{sy:.2f}"
        frm.scale = (0.025, 0.215, 0.138)
        bpy.ops.object.transform_apply(scale=True)
        _assign(frm, chrome_m)

        # ── C-shaped LED: top horizontal bar ──
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.863, sy, 0.658))
        top = bpy.context.active_object; top.name = f"tl_c_top_{sy:.2f}"
        top.scale = (0.006, 0.198, 0.016)
        bpy.ops.object.transform_apply(scale=True)
        _assign(top, brake_m)

        # ── C-shaped LED: outer vertical bar ──
        outer_y = sy - sign * 0.092
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.863, outer_y, 0.620))
        ov = bpy.context.active_object; ov.name = f"tl_c_vert_{sy:.2f}"
        ov.scale = (0.006, 0.016, 0.080)
        bpy.ops.object.transform_apply(scale=True)
        _assign(ov, brake_m)

        # ── C-shaped LED: bottom horizontal bar ──
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.863, sy, 0.580))
        bot = bpy.context.active_object; bot.name = f"tl_c_bot_{sy:.2f}"
        bot.scale = (0.006, 0.198, 0.016)
        bpy.ops.object.transform_apply(scale=True)
        _assign(bot, brake_m)

        # Amber turn signal (inner vertical, opposite C open side)
        inner_y = sy + sign * 0.070
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.863, inner_y, 0.625))
        ts = bpy.context.active_object; ts.name = f"tl_turn_{sy:.2f}"
        ts.scale = (0.006, 0.016, 0.065)
        bpy.ops.object.transform_apply(scale=True)
        _assign(ts, turn_m)

        # Reverse light (white, small square below C)
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(2.863, sy - sign * 0.055, 0.538))
        rv = bpy.context.active_object; rv.name = f"tl_rev_{sy:.2f}"
        rv.scale = (0.006, 0.058, 0.018)
        bpy.ops.object.transform_apply(scale=True)
        _assign(rv, rev_m)

        # Red translucent lens cover
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.851, sy, 0.598))
        rl = bpy.context.active_object; rl.name = f"tl_rlens_{sy:.2f}"
        rl.scale = (0.009, 0.205, 0.132)
        bpy.ops.object.transform_apply(scale=True)
        _assign(rl, rlens_m)


# ─────────────────── LICENSE PLATES (yellow + text) ─────────
# FIX v7: yellow plate (Chinese commercial/truck standard) with embossed text.
# Text objects: rotation (pi/2, 0, ±pi/2) → face toward car front/rear.
def build_plates():
    plate_m = _mat("plate_yellow", (0.95, 0.78, 0.02), roughness=0.35)
    frame_m = _mat("plate_frame",  (0.05, 0.05, 0.055), metallic=0.6, roughness=0.30)
    text_m  = _mat("plate_text",   (0.02, 0.02, 0.025), roughness=0.55)
    light_m = _mat("plate_light",  (0.95, 0.95, 0.90),
                   emission=(0.98, 0.98, 0.92), emit_str=3.0)

    # (plate_x, text_x_offset, text_rot_z, rear_light_x)
    configs = [
        (-1.942, -0.010, -math.pi / 2, None),   # front plate
        ( 2.878,  0.010,  math.pi / 2, 2.862),  # rear plate + light
    ]
    for px, tx_off, rot_z, light_x in configs:
        # Yellow plate base
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.500))
        ob = bpy.context.active_object; ob.name = f"plate_{px:.2f}"
        ob.scale = (0.007, 0.270, 0.072)
        bpy.ops.object.transform_apply(scale=True)
        _assign(ob, plate_m)

        # Black metal frame
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.500))
        frm = bpy.context.active_object; frm.name = f"plate_frame_{px:.2f}"
        frm.scale = (0.009, 0.295, 0.096)
        bpy.ops.object.transform_apply(scale=True)
        _assign(frm, frame_m)

        # Plate number text object
        text_x = px + tx_off
        bpy.ops.object.text_add(location=(text_x, 0, 0.500))
        txt = bpy.context.active_object; txt.name = f"plate_txt_{px:.2f}"
        txt.data.body      = "Shanghai A 12345"   # Shanghai A - 12345
        txt.data.size      = 0.028
        txt.data.align_x   = "CENTER"
        txt.data.extrude   = 0.003
        txt.rotation_euler = (math.pi / 2, 0, rot_z)
        _assign(txt, text_m)

        # Rear plate illumination strip
        if light_x is not None:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(light_x, 0, 0.558))
            pl = bpy.context.active_object; pl.name = "plate_light_rear"
            pl.scale = (0.005, 0.240, 0.010)
            bpy.ops.object.transform_apply(scale=True)
            _assign(pl, light_m)


# ─────────────────── WHEELS ─────────────────────────────────
def build_wheel(x, y, R=0.33, W=0.22):
    side = math.copysign(1, y)
    D_F  =  side * W * 0.42
    D_B  = -side * W * 0.18

    N_SP = 5; N_RIM = 48
    R_RIM = R * 0.90; R_HUB = R * 0.13
    W_SP_O = R * 0.055; W_SP_I = R * 0.028

    T = R * 0.175
    bpy.ops.mesh.primitive_torus_add(
        location=(x, y, R), rotation=(math.radians(90), 0, 0),
        major_radius=R - T, minor_radius=T,
        major_segments=72, minor_segments=24)
    tire = bpy.context.active_object; tire.name = f"tire_{x:.2f}_{y:.2f}"
    _smooth(tire); _assign(tire, mat_tire())

    bm = bmesh.new()

    def _circ(n, r, wy):
        return [bm.verts.new(Vector((
            x + r * math.cos(2*math.pi*i/n), wy,
            R + r * math.sin(2*math.pi*i/n),
        ))) for i in range(n)]

    of_ = _circ(N_RIM, R_RIM, y + D_F)
    ob_ = _circ(N_RIM, R_RIM, y + D_B)
    for i in range(N_RIM):
        ni = (i+1) % N_RIM
        bm.faces.new([of_[i], ob_[i], ob_[ni], of_[ni]])
    bc = bm.verts.new(Vector((x, y + D_B, R)))
    for i in range(N_RIM):
        ni = (i+1) % N_RIM
        bm.faces.new([bc, ob_[i], ob_[ni]])

    for s in range(N_SP):
        ang = 2 * math.pi * s / N_SP
        ca, sa = math.cos(ang), math.sin(ang)
        px, pz = -sa, ca

        def _sv(r, hw, wy):
            return (bm.verts.new(Vector((x+r*ca+px*hw, wy, R+r*sa+pz*hw))),
                    bm.verts.new(Vector((x+r*ca-px*hw, wy, R+r*sa-pz*hw))))

        foL,foR = _sv(R_RIM*0.97, W_SP_O, y+D_F)
        fiL,fiR = _sv(R_HUB*1.05, W_SP_I, y+D_F)
        boL,boR = _sv(R_RIM*0.97, W_SP_O, y+D_B*0.55)
        biL,biR = _sv(R_HUB*1.05, W_SP_I, y+D_B*0.55)
        try:
            bm.faces.new([foL,foR,fiR,fiL]); bm.faces.new([boR,boL,biL,biR])
            bm.faces.new([foL,boL,boR,foR]); bm.faces.new([fiL,fiR,biR,biL])
            bm.faces.new([foL,fiL,biL,boL]); bm.faces.new([foR,boR,biR,fiR])
        except Exception: pass

    N_HUB = 16
    hf_ = _circ(N_HUB, R_HUB, y+D_F*0.92)
    hb_ = _circ(N_HUB, R_HUB, y+D_B)
    hcf = bm.verts.new(Vector((x, y+D_F*0.92, R)))
    hcb = bm.verts.new(Vector((x, y+D_B, R)))
    for i in range(N_HUB):
        ni = (i+1) % N_HUB
        bm.faces.new([hcf, hf_[i], hf_[ni]])
        bm.faces.new([hcb, hb_[ni], hb_[i]])
        bm.faces.new([hf_[i], hf_[ni], hb_[ni], hb_[i]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rim = _bm_obj(f"rim_{x:.2f}_{y:.2f}", bm)
    _smooth(rim)
    sub = rim.modifiers.new("SubSurf", "SUBSURF")
    sub.levels = 1; sub.render_levels = 2
    _assign(rim, _mat("rim_alloy", (0.82,0.85,0.90),
                      metallic=0.96, roughness=0.08, aniso=0.72))

    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=R*0.44, depth=0.018,
        location=(x, y, R), rotation=(math.radians(90), 0, 0))
    disc = bpy.context.active_object; disc.name = f"disc_{x:.2f}_{y:.2f}"
    _smooth(disc)
    _assign(disc, _mat("brake_disc", (0.26,0.26,0.27), metallic=0.75, roughness=0.52))

    cal_y = y - math.copysign(R*0.32, y)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, cal_y, R*0.62))
    cal = bpy.context.active_object; cal.name = f"cal_{x:.2f}_{y:.2f}"
    cal.scale = (0.18, 0.08, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    _assign(cal, _mat("caliper_red", (0.75, 0.02, 0.02), roughness=0.3))


# ─────────────────── WORLD / STUDIO ─────────────────────────
def setup_world():
    world = bpy.context.scene.world
    if not world: world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], out.inputs[0])
    sky.sky_type = "NISHITA"; sky.sun_elevation = math.radians(38)
    sky.sun_rotation = math.radians(145)
    try: sky.air_density = 1.0; sky.dust_density = 0.35
    except Exception: pass
    bg.inputs["Strength"].default_value = 0.50

def setup_studio():
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0.55, 0, 0))
    _assign(bpy.context.active_object,
            _mat("floor_dark", (0.26, 0.26, 0.28), roughness=0.20))

def setup_lighting():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object
    sun.data.energy = 4.0; sun.data.color = (1.0, 0.97, 0.88)
    sun.data.angle  = math.radians(0.5)
    sun.rotation_euler = Euler((math.radians(52), 0, math.radians(145)), "XYZ")

    bpy.ops.object.light_add(type="AREA", location=(6, 5, 4))
    fill = bpy.context.active_object
    fill.data.energy = 180; fill.data.size = 9; fill.data.color = (0.78, 0.88, 1.0)
    fill.rotation_euler = Euler((math.radians(28), 0, math.radians(148)), "XYZ")

    bpy.ops.object.light_add(type="AREA", location=(4, -3, 6))
    rim = bpy.context.active_object
    rim.data.energy = 250; rim.data.size = 4; rim.data.color = (1.0, 0.95, 0.82)
    rim.rotation_euler = Euler((math.radians(-18), 0, math.radians(165)), "XYZ")


# ─────────────────── CAMERA ─────────────────────────────────
def setup_camera():
    scene = bpy.context.scene
    scene.frame_start = 1; scene.frame_end = 150; scene.render.fps = 25

    cd = bpy.data.cameras.new("Camera"); cd.lens = 65
    cam = bpy.data.objects.new("Camera", cd)
    bpy.context.collection.objects.link(cam); scene.camera = cam

    tx, tz = 0.55, 0.82
    R_orb = 7.8; H_lo, H_hi = 1.10, 2.80

    for f in range(1, 151):
        t  = (f-1)/149.0; ts = t*t*(3-2*t)
        ang = math.radians(-105) + ts*math.radians(280)
        h   = H_lo + (H_hi-H_lo)*math.sin(math.pi*t)
        cx  = tx + R_orb*math.cos(ang)
        cy  = R_orb*math.sin(ang)
        cam.location = (cx, cy, h)
        d = Vector((tx-cx, -cy, tz-h)).normalized()
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)


# ─────────────────── RENDER ─────────────────────────────────
def setup_render():
    scene = bpy.context.scene
    scene.render.engine  = "CYCLES"
    scene.cycles.device  = "GPU"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    for dn in ("OPTIX", "OPENIMAGEDENOISE"):
        try: scene.cycles.denoiser = dn; break
        except Exception: pass
    scene.cycles.use_adaptive_sampling  = True
    scene.cycles.adaptive_threshold     = 0.005
    scene.cycles.adaptive_min_samples   = 32
    try:
        scene.cycles.transmission_bounces    = 8
        scene.cycles.transparent_max_bounces = 8
    except Exception: pass

    scene.render.resolution_x = 1920; scene.render.resolution_y = 1080
    scene.render.filepath = RENDER_PATH
    scene.render.image_settings.file_format  = "FFMPEG"
    scene.render.ffmpeg.format               = "MPEG4"
    scene.render.ffmpeg.codec                = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"

    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look           = "Low Contrast"
    scene.view_settings.exposure        = -0.25
    scene.display_settings.display_device = "sRGB"


# ─────────────────── MAIN ────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    enable_gpu()
    clear_scene()

    paint = mat_paint((0.01, 0.04, 0.55))
    glass = mat_glass()

    build_body(paint, glass)
    build_interior()
    build_panel_features()
    build_side_mirrors()
    build_headlights()
    build_taillights()
    build_plates()

    for wx, wy in [(-0.95,-0.97), (-0.95,0.97), (2.05,-0.97), (2.05,0.97)]:
        build_wheel(wx, wy)

    setup_world(); setup_studio(); setup_lighting()
    setup_camera(); setup_render()

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[save] {BLEND_PATH}")
    print("[render] Cycles OPTIX GPU …")
    bpy.ops.render.render(animation=True)
    print(f"[render] Done → {RENDER_PATH}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
vehicle_demo_v12.py — 4 fixes over v11:
  1. Windshield smaller: glass now i==4 only (cowl→A-pillar slope); removes the front roof strip
     that previously extended the glass 55cm past the A-pillar (i=5, station 5→6 was roof).
  2. Mirror inward: sy ±1.10 → ±1.06 (mirror housing ≈10cm outside body instead of 14.5cm).
  3. Headlights bigger+lower: scale (0.040,0.090,0.068)→(0.050,0.108,0.082), hz 0.620→0.580.
  4. Taillights inward: sy 0.76→0.60, all y-dims ×0.512 → outer extent y=0.710 < body 0.729 ✓.
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
BLEND_PATH  = os.path.join(OUTPUT_DIR, "vehicle_demo_v12.blend")
RENDER_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v12")

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
    (-1.90,0.18,0.38,0.36,0.22,0.10),  # 0  front tip
    (-1.72,0.76,0.54,0.46,0.22,0.10),  # 1  front bumper
    (-1.45,0.91,0.80,0.65,0.22,0.10),  # 2  hood/fender start
    (-1.05,0.93,0.92,0.78,0.22,0.10),  # 3  front fender peak  (z_top 1.00→0.92)
    (-0.40,0.94,0.90,0.72,0.22,0.10),  # 4  cowl/windshield base (z_top 1.10→0.90, z_belt 0.82→0.72)
    ( 0.00,0.95,1.34,0.72,0.22,0.10),  # 5  A-pillar foot       (z_belt 0.87→0.72)
    ( 0.55,0.96,1.40,0.72,0.22,0.10),  # 6  front roof          (z_belt 0.88→0.72)
    ( 1.05,0.96,1.42,0.72,0.22,0.10),  # 7  roof centre         (z_belt 0.88→0.72)
    ( 1.55,0.95,1.40,0.72,0.22,0.10),  # 8  C-pillar top        (z_belt 0.88→0.72)
    ( 2.05,0.94,1.20,0.74,0.22,0.10),  # 9  rear fender peak    (z_belt 0.85→0.74)
    ( 2.50,0.91,0.82,0.78,0.22,0.10),  # 10 trunk
    ( 2.82,0.78,0.56,0.52,0.22,0.10),  # 11 rear bumper
    ( 3.00,0.20,0.38,0.36,0.22,0.10),  # 12 tail tip
]
# With z_belt=0.72: window-bottom j=3 = 0.72+0.185 = 0.905 m
# Side-window height at st6: 1.40-0.905 = 0.495 m  (was 0.335 m, +48%)
# Windshield height: z_top_st5 - z_top_st4 = 1.34-0.90 = 0.44 m (was 0.24 m, +83%)
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
    # Windshield: cowl→A-pillar slope only (i==4, x=-0.40→0.00).
    # i=5 (x=0.00→0.55) is the front ROOF strip — must be paint not glass.
    if j in (0, 1) and i == 4: return True
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
# v8: z_belt=0.72 → window bottom j=3 = 0.905.  All seam z positions updated.
# Added: lower-body door seam verticals, horizontal character line, trunk outline.
def build_panel_features():
    """
    v9 FIX: All flat strips that didn't follow the body curve are REMOVED.
    Only window-frame edge strips (which are at the correct profile positions) are kept.
    Door gaps + character line + trunk are now in build_doors() using profile-conforming geometry.
    """
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

    # ── Trunk lid outline ──
    # These follow the rear body reasonably well since trunk is near-flat.
    _full("trunk_top_seam", [
        Vector((2.06, -0.80, 1.16)), Vector((2.06,  0.80, 1.16)),
        Vector((2.09,  0.80, 1.12)), Vector((2.09, -0.80, 1.12)),
    ], dark)
    _half("trunk_side_seam", [
        Vector((2.07, 0.78, 1.16)), Vector((2.74, 0.76, 0.64)),
        Vector((2.74, 0.79, 0.62)), Vector((2.07, 0.81, 1.14)),
    ], dark)
    _full("trunk_bot_seam", [
        Vector((2.72, -0.76, 0.64)), Vector((2.72,  0.76, 0.64)),
        Vector((2.76,  0.76, 0.60)), Vector((2.76, -0.76, 0.60)),
    ], dark)
    _full("trunk_lock", [
        Vector((2.73, -0.04, 0.70)), Vector((2.73,  0.04, 0.70)),
        Vector((2.76,  0.04, 0.58)), Vector((2.76, -0.04, 0.58)),
    ], chrome)

    # ── Hood cowl ──
    _full("hood_cowl", [
        Vector((-0.02,  0.80, 0.90)), Vector((-0.02, -0.80, 0.90)),
        Vector((-0.07, -0.82, 0.88)), Vector((-0.07,  0.82, 0.88)),
    ], dark)

    # ── Front bumper chrome bars ──
    # OLD flat cubes at x=-1.935 were OUTSIDE the body (body starts at x=-1.90 station 0)
    # → appeared as white floating planes.  Fix: chrome CYLINDERS at x=-1.878 (inside body),
    # z=0.30 & z=0.44 (below plate z=0.46-0.55), y=±0.22 (within body width at that x).
    # Cylinder cross-section = "silver protrusion" highlight, not a flat white rectangle.
    for gz, depth in [(0.44, 0.44), (0.30, 0.40)]:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=0.014, depth=depth,
            location=(-1.878, 0, gz),
            rotation=(math.pi / 2, 0, 0))   # horizontal bar across car width
        g = bpy.context.active_object; g.name = f"bumper_bar_{gz}"
        g.scale = (1.4, 1.0, 0.52)   # flatten oval: wider in X, shorter in Z
        bpy.ops.object.transform_apply(scale=True)
        _assign(g, chrome); _smooth(g)


# ─────────────────── DOORS (profile-conforming) ──────────────
# v9 FIX: door gap strips follow the actual body profile y values at each z height,
# so they lie ON the surface rather than floating as bars.
# With z_belt=0.72, z_sill=0.22 the profile at each station is:
#   j=3: y=w*1.005, z=0.905   (window bottom / shoulder)
#   j=4: y=w*1.058, z=0.520   (max-width belt line)
#   j=5: y=w*1.038, z=0.268   (lower door)
#   j=6: y=w*0.982, z=0.220   (sill)
def build_doors():
    # v11: door gap strips ultra-thin (dx=0.003 = 6mm) and zero offset so they sit
    # exactly on the body surface. char_line removed — it combined with the vertical
    # gaps to form a visible gray rectangle "frame" around each door panel.
    seam_m    = _mat("door_seam",    (0.010, 0.010, 0.012), roughness=0.90)
    handle_mat = _mat("door_handle", (0.84,  0.86,  0.90),  metallic=0.95, roughness=0.08)

    def _gap(name, pts):
        """Profile-conforming door seam: ultra-thin ribbon, ±dx in x, exactly on body."""
        bm = bmesh.new()
        dx = 0.003   # 6 mm total width — real door gap appearance
        n  = len(pts)
        lo = [bm.verts.new(Vector((x - dx, y, z))) for x, y, z in pts]
        hi = [bm.verts.new(Vector((x + dx, y, z))) for x, y, z in pts]
        for i in range(n - 1):
            bm.faces.new([lo[i], hi[i], hi[i+1], lo[i+1]])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm)
        o.data.materials.append(seam_m)
        _mirror_y(o)

    # OFF=0.0: strips sit exactly on the body surface (j=3/4/5/6 profile points)
    OFF = 0.0

    # A-pillar seam (x=0.00, w=0.95)
    _gap("door_gap_front", [
        (0.00, 0.955 + OFF, 0.905),
        (0.00, 1.005 + OFF, 0.520),
        (0.00, 0.986 + OFF, 0.268),
        (0.00, 0.933 + OFF, 0.220),
    ])

    # B-pillar seam at x=0.78 (equal door widths: front=0.78m, rear=0.77m)
    _gap("door_gap_B", [
        (0.78, 0.963 + OFF, 0.905),
        (0.78, 1.013 + OFF, 0.520),
        (0.78, 0.994 + OFF, 0.268),
        (0.78, 0.940 + OFF, 0.220),
    ])

    # C-pillar seam (x=1.55, w=0.95)
    _gap("door_gap_C", [
        (1.55, 0.955 + OFF, 0.905),
        (1.55, 1.005 + OFF, 0.520),
        (1.55, 0.986 + OFF, 0.268),
        (1.55, 0.933 + OFF, 0.220),
    ])
    # char_line removed — was forming gray frame outline around door panels

    # ── Door handles: horizontal pill (cylinder along X) ──
    # y ≈ 1.00 at z=0.72 (slightly outside door surface which is ≈0.984 there)
    for sy in (1.004, -1.004):
        for hx in (0.38, 1.30):
            bpy.ops.mesh.primitive_cylinder_add(
                vertices=20, radius=0.013, depth=0.096,
                location=(hx, sy, 0.72),
                rotation=(0, math.pi / 2, 0))   # axis along X
            dh = bpy.context.active_object; dh.name = f"handle_{hx:.2f}_{sy:.3f}"
            dh.scale = (1.0, 0.70, 0.58)
            bpy.ops.object.transform_apply(scale=True)
            _assign(dh, handle_mat)
            _smooth(dh)


# ─────────────────── INTERIOR (visible through windows) ──────
# v8: window-bottom z=0.905 (was 1.065) → seat cushions at z=0.90 now right at sill.
# Much more interior visible. Steering wheel top at z≈1.15 > 0.905 ✓
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
# v8: wedge-shaped bmesh housing (wider at back = mirror face, narrower at front),
# longer arm (body y≈0.962 → housing y≈1.12), amber turn LED on outer face.
# v9: smooth UV-sphere housing (aerodynamic teardrop), cylinder arm, disc mirror face.
def build_side_mirrors():
    housing_m = _mat("mirror_housing", (0.050, 0.050, 0.055), metallic=0.12, roughness=0.40)
    mirror_m  = _mat("mirror_face",    (0.82,  0.86,  0.90),  metallic=0.98, roughness=0.02)
    arm_m     = _mat("mirror_arm",     (0.040, 0.040, 0.045), metallic=0.15, roughness=0.38)
    sig_m     = _mat("mirror_sig",     (0.92,  0.55,  0.02),
                     emission=(1.0, 0.60, 0.02), emit_str=4.0)

    for sy in (1.06, -1.06):   # v12: inward from 1.10 → 1.06 (≈10cm outside body instead of 14.5cm)
        sign = math.copysign(1, sy)
        hx, hz = 0.02, 1.17   # A-pillar base (front door edge, x=0.00 station 5)

        # ── Housing: UV sphere scaled to aerodynamic teardrop/capsule ──
        # x = front-to-back depth (long), y = side thickness (thin), z = height
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=1.0, segments=32, ring_count=20,
            location=(hx, sy, hz))
        hsg = bpy.context.active_object; hsg.name = f"mirror_hsg_{sy:.2f}"
        hsg.scale = (0.074, 0.038, 0.054)
        bpy.ops.object.transform_apply(scale=True)
        _assign(hsg, housing_m); _smooth(hsg)

        # ── Mirror glass: flat oval disc on outer face ──
        face_y = sy + sign * 0.040
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=32, radius=0.048, depth=0.005,
            location=(hx, face_y, hz),
            rotation=(math.pi / 2, 0, 0))  # orient disc normal toward +Y/-Y
        mf = bpy.context.active_object; mf.name = f"mirror_face_{sy:.2f}"
        mf.scale = (1.30, 1.0, 0.82)    # oval: wider in x, shorter in z
        bpy.ops.object.transform_apply(scale=True)
        _assign(mf, mirror_m); _smooth(mf)

        # ── Amber turn indicator on outer-lower corner ──
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=16, radius=0.012, depth=0.006,
            location=(hx + 0.045, sy + sign * 0.032, hz - 0.030),
            rotation=(math.pi / 2, 0, 0))
        sig = bpy.context.active_object; sig.name = f"mirror_sig_{sy:.2f}"
        sig.scale = (1.8, 1.0, 0.5)
        bpy.ops.object.transform_apply(scale=True)
        _assign(sig, sig_m); _smooth(sig)

        # ── Arm: two cylinders bridging body surface (j=3 shoulder y≈±0.955) to housing ──
        body_y  = sign * 0.955
        hsg_inner_y = sy - sign * 0.038   # inner face of housing
        mid_y   = (body_y + hsg_inner_y) * 0.5
        arm_len = abs(hsg_inner_y - body_y) + 0.004
        # Upper arm
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=12, radius=0.009, depth=arm_len,
            location=(hx + 0.012, mid_y, hz + 0.010),
            rotation=(math.pi / 2, 0, 0))
        arm = bpy.context.active_object; arm.name = f"mirror_arm_{sy:.2f}"
        _assign(arm, arm_m); _smooth(arm)
        # Lower arm (slightly offset)
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=12, radius=0.007, depth=arm_len,
            location=(hx - 0.012, mid_y, hz - 0.014),
            rotation=(math.pi / 2, 0, 0))
        arm2 = bpy.context.active_object; arm2.name = f"mirror_arm2_{sy:.2f}"
        _assign(arm2, arm_m); _smooth(arm2)


# ─────────────────── HEADLIGHTS (front) ─────────────────────
# v9: smooth organic shapes — ellipsoidal housing, oval DRL torus (angel-eye),
# dual projector spheres with chrome torus bezels, oval turn cylinder.
def build_headlights():
    black_m  = _mat("hl_black",  (0.016, 0.016, 0.020), roughness=0.44)
    chrome_m = _mat("hl_chrome", (0.76,  0.79,  0.83),  metallic=0.96, roughness=0.05)
    lens_m   = _mat("hl_lens",   (0.88,  0.88,  0.86),  transmission=1.0, roughness=0.0, ior=1.50)
    drl_m    = _mat("hl_drl",    (1.00,  0.97,  0.88),
                    emission=(1.00, 0.97, 0.88), emit_str=14.0)
    proj_m   = _mat("hl_proj",   (0.95,  0.94,  0.88),
                    emission=(1.00, 0.97, 0.90), emit_str=9.0)
    sig_m    = _mat("hl_signal", (0.90,  0.55,  0.02),
                    emission=(1.00, 0.60, 0.02), emit_str=6.0)

    # v12: headlights slightly bigger (scale *1.2) and 4cm lower (hz=0.580).
    # x=-1.65 fender corner unchanged; body width 0.846 > sy=0.78 → still recessed. ✓
    for sy in (0.78, -0.78):
        sign = math.copysign(1, sy)
        hx, hz = -1.65, 0.580   # 4cm lower than v11 (0.620→0.580)

        # ── Dark housing bowl ──
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=1.0, segments=32, ring_count=20,
            location=(hx, sy, hz))
        hsg = bpy.context.active_object; hsg.name = f"hl_hsg_{sy:.2f}"
        hsg.scale = (0.050, 0.108, 0.082)   # bigger: 100mm deep, 216mm wide, 164mm tall
        bpy.ops.object.transform_apply(scale=True)
        _assign(hsg, black_m); _smooth(hsg)

        # ── Inner projector (low-beam) + chrome bezel ──
        inner_y = sy - sign * 0.034
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.030, segments=24, ring_count=16,
            location=(hx - 0.010, inner_y, hz + 0.005))
        pi_ = bpy.context.active_object; pi_.name = f"hl_proj_in_{sy:.2f}"
        pi_.scale = (0.42, 1.0, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        _assign(pi_, proj_m); _smooth(pi_)

        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.034, minor_radius=0.005,
            major_segments=32, minor_segments=10,
            location=(hx - 0.004, inner_y, hz + 0.005),
            rotation=(0, math.pi / 2, 0))
        _assign(bpy.context.active_object, chrome_m)

        # ── Outer projector (high-beam) ──
        outer_y = sy + sign * 0.040
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.024, segments=20, ring_count=14,
            location=(hx - 0.010, outer_y, hz + 0.012))
        po_ = bpy.context.active_object; po_.name = f"hl_proj_out_{sy:.2f}"
        po_.scale = (0.40, 1.0, 1.0)
        bpy.ops.object.transform_apply(scale=True)
        _assign(po_, proj_m); _smooth(po_)

        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.026, minor_radius=0.005,
            major_segments=28, minor_segments=10,
            location=(hx - 0.004, outer_y, hz + 0.012),
            rotation=(0, math.pi / 2, 0))
        _assign(bpy.context.active_object, chrome_m)

        # ── DRL oval ring (angel-eye) ──
        bpy.ops.mesh.primitive_torus_add(
            major_radius=0.064, minor_radius=0.006,
            major_segments=48, minor_segments=12,
            location=(hx - 0.020, sy, hz),
            rotation=(0, math.pi / 2, 0))
        drl = bpy.context.active_object; drl.name = f"hl_drl_{sy:.2f}"
        drl.scale = (1.0, 0.84, 0.70)
        bpy.ops.object.transform_apply(scale=True)
        _assign(drl, drl_m)

        # ── Amber turn signal ──
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=28, radius=0.052, depth=0.012,
            location=(hx - 0.022, sy, hz - 0.056),
            rotation=(0, math.pi / 2, 0))
        s = bpy.context.active_object; s.name = f"hl_sig_{sy:.2f}"
        s.scale = (1.0, 0.88, 0.30)
        bpy.ops.object.transform_apply(scale=True)
        _assign(s, sig_m); _smooth(s)

        # ── Clear outer lens ──
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=1.0, segments=32, ring_count=20,
            location=(hx - 0.046, sy, hz))
        l = bpy.context.active_object; l.name = f"hl_lens_{sy:.2f}"
        l.scale = (0.006, 0.110, 0.084)
        bpy.ops.object.transform_apply(scale=True)
        _assign(l, lens_m); _smooth(l)


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

    # v12: taillights moved inward sy 0.76→0.60 and y-dims ×0.512.
    # At x=2.848: body j4_y=0.729 → outer extent 0.60+0.110=0.710 < 0.729. ✓  (was 0.975)
    for sy in (0.60, -0.60):
        sign = math.copysign(1, sy)

        # Chrome outer frame
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.842, sy, 0.595))
        frm = bpy.context.active_object; frm.name = f"tl_frame_{sy:.2f}"
        frm.scale = (0.016, 0.110, 0.138)
        bpy.ops.object.transform_apply(scale=True)
        _assign(frm, chrome_m)

        # C-top bar
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.848, sy, 0.658))
        top = bpy.context.active_object; top.name = f"tl_c_top_{sy:.2f}"
        top.scale = (0.006, 0.100, 0.016)
        bpy.ops.object.transform_apply(scale=True)
        _assign(top, brake_m)

        # C-outer vertical
        outer_y = sy - sign * 0.052
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.848, outer_y, 0.620))
        ov = bpy.context.active_object; ov.name = f"tl_c_vert_{sy:.2f}"
        ov.scale = (0.006, 0.016, 0.080)
        bpy.ops.object.transform_apply(scale=True)
        _assign(ov, brake_m)

        # C-bottom bar
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.848, sy, 0.580))
        bot = bpy.context.active_object; bot.name = f"tl_c_bot_{sy:.2f}"
        bot.scale = (0.006, 0.100, 0.016)
        bpy.ops.object.transform_apply(scale=True)
        _assign(bot, brake_m)

        # Amber turn signal
        inner_y = sy + sign * 0.040
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.848, inner_y, 0.625))
        ts = bpy.context.active_object; ts.name = f"tl_turn_{sy:.2f}"
        ts.scale = (0.006, 0.016, 0.065)
        bpy.ops.object.transform_apply(scale=True)
        _assign(ts, turn_m)

        # Reverse light
        bpy.ops.mesh.primitive_cube_add(
            size=1, location=(2.848, sy - sign * 0.030, 0.538))
        rv = bpy.context.active_object; rv.name = f"tl_rev_{sy:.2f}"
        rv.scale = (0.006, 0.030, 0.018)
        bpy.ops.object.transform_apply(scale=True)
        _assign(rv, rev_m)

        # Red translucent lens
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.836, sy, 0.598))
        rl = bpy.context.active_object; rl.name = f"tl_rlens_{sy:.2f}"
        rl.scale = (0.007, 0.105, 0.132)
        bpy.ops.object.transform_apply(scale=True)
        _assign(rl, rlens_m)


# ─────────────────── LICENSE PLATES (yellow + text) ─────────
# FIX v7: yellow plate (Chinese commercial/truck standard) with embossed text.
# Text objects: rotation (pi/2, 0, ±pi/2) → face toward car front/rear.
def build_plates():
    plate_m = _mat("plate_yellow", (0.95, 0.78, 0.02), roughness=0.35)
    frame_m = _mat("plate_frame",  (0.04, 0.04, 0.045), metallic=0.0, roughness=0.60)
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
    build_doors()
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

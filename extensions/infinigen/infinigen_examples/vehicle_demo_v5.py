#!/usr/bin/env python3
"""
vehicle_demo_v5.py — fixes:
  1. Wheel chirality (D_F/D_B signed by wheel side → left/right symmetric)
  2. Tire tread bump texture (wave + noise)
  3. Glass: Cycles-correct (Transmission=1.0, no blend_method),
     repositioned to y=0.91 so it's outside the body shell
  4. Detailed headlights: housing + reflector + projector + DRL strip + lens
  5. Detailed taillights: chrome surround + LED array sections
  6. License plate: flush + frame + illumination
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
BLEND_PATH  = os.path.join(OUTPUT_DIR, "vehicle_demo_v5.blend")
RENDER_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v5b")

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
def _mat(name, color, metallic=0.0, roughness=0.5, alpha=1.0,
         transmission=0.0, coat=0.0, coat_rough=0.04, coat_ior=1.52,
         emission=None, emit_str=0.0, ior=1.45, aniso=0.0):
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
        mat.blend_method = "BLEND"
        mat.use_backface_culling = False
    if emission and emit_str > 0:
        for k in ("Emission Color", "Emission"):
            if k in bsdf.inputs: bsdf.inputs[k].default_value = (*emission, 1.0); break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_str
    if aniso > 0 and "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = aniso
    return mat


def mat_paint(name, color):
    """Solid car paint, no randomness."""
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


def mat_glass():
    """Cycles-correct glass: Transmission=1.0, tinted, no blend_method."""
    name = "car_glass"
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    # Dark green-tinted glass
    bsdf.inputs["Base Color"].default_value = (0.04, 0.10, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.0
    bsdf.inputs["IOR"].default_value        = 1.52
    # Full transmission → physically correct Cycles glass
    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs: bsdf.inputs[k].default_value = 1.0; break
    # No blend_method — Cycles handles it natively
    return mat


def mat_tire():
    """Rubber with tread bump (wave rings + noise grain)."""
    name = "tire_rubber"
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()

    out   = nt.nodes.new("ShaderNodeOutputMaterial"); out.location   = (700, 0)
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location  = (400, 0)
    bump  = nt.nodes.new("ShaderNodeBump");           bump.location  = (100, -150)
    add   = nt.nodes.new("ShaderNodeMath");           add.location   = (-200, -150)
    wave  = nt.nodes.new("ShaderNodeTexWave");        wave.location  = (-500, -50)
    noise = nt.nodes.new("ShaderNodeTexNoise");       noise.location = (-500, -250)
    coord = nt.nodes.new("ShaderNodeTexCoord");       coord.location = (-750, -150)

    add.operation = "ADD"
    nt.links.new(coord.outputs["Object"], wave.inputs["Vector"])
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(wave.outputs["Fac"],  add.inputs[0])
    nt.links.new(noise.outputs["Fac"], add.inputs[1])
    nt.links.new(add.outputs[0],       bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    nt.links.new(bsdf.outputs[0], out.inputs[0])

    # Coarse wave → tread groove rings around the tire
    wave.wave_type       = "BANDS"
    wave.bands_direction = "X"
    wave.inputs["Scale"].default_value       = 55.0
    wave.inputs["Distortion"].default_value  = 2.5
    wave.inputs["Detail"].default_value      = 4.0

    # Fine noise → rubber grain
    noise.inputs["Scale"].default_value     = 80.0
    noise.inputs["Detail"].default_value    = 5.0
    noise.inputs["Roughness"].default_value = 0.7

    bump.inputs["Strength"].default_value  = 0.45
    bump.inputs["Distance"].default_value  = 0.004

    bsdf.inputs["Base Color"].default_value = (0.025, 0.025, 0.025, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.90

    return mat


# ─────────────────── SEDAN BODY ─────────────────────────────
SEDAN_ST = [
    (-1.90, 0.18, 0.38, 0.36, 0.22, 0.10),
    (-1.72, 0.76, 0.54, 0.46, 0.22, 0.10),
    (-1.45, 0.91, 0.80, 0.65, 0.22, 0.10),
    (-1.05, 0.93, 1.00, 0.78, 0.22, 0.10),
    (-0.40, 0.94, 1.10, 0.82, 0.22, 0.10),
    ( 0.00, 0.95, 1.34, 0.87, 0.22, 0.10),
    ( 0.55, 0.96, 1.40, 0.88, 0.22, 0.10),
    ( 1.05, 0.96, 1.42, 0.88, 0.22, 0.10),
    ( 1.55, 0.95, 1.40, 0.88, 0.22, 0.10),
    ( 2.05, 0.94, 1.20, 0.85, 0.22, 0.10),
    ( 2.50, 0.91, 0.82, 0.78, 0.22, 0.10),
    ( 2.82, 0.78, 0.56, 0.52, 0.22, 0.10),
    ( 3.00, 0.20, 0.38, 0.36, 0.22, 0.10),
]
N_PROF = 9

def _profile(x, w, z_top, z_belt, z_sill, z_floor):
    z_mid = (z_belt + z_sill) * 0.5 + 0.05
    return [
        Vector((x, 0.0,      z_top)),
        Vector((x, w*0.68,   z_top)),
        Vector((x, w*0.93,   z_top - 0.022)),
        Vector((x, w*1.005,  z_belt + 0.185)),
        Vector((x, w*1.058,  z_mid)),
        Vector((x, w*1.038,  z_sill + 0.048)),
        Vector((x, w*0.982,  z_sill)),
        Vector((x, w*0.680,  z_floor)),
        Vector((x, 0.0,      z_floor)),
    ]

def build_body(paint):
    bm = bmesh.new()
    N  = len(SEDAN_ST)
    grid = [[bm.verts.new(v) for v in _profile(*st)] for st in SEDAN_ST]
    bm.verts.ensure_lookup_table()
    for i in range(N - 1):
        for j in range(N_PROF - 1):
            try:
                bm.faces.new([grid[i][j], grid[i][j+1],
                              grid[i+1][j+1], grid[i+1][j]])
            except ValueError: pass
    obj = _bm_obj("car_body", bm)
    _smooth(obj)
    _mirror_y(obj)
    sub = obj.modifiers.new("SubSurf", "SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 2; sub.render_levels = 4
    _assign(obj, paint)
    return obj


# ─────────────────── GLASS PANELS ───────────────────────────
# y=0.91 is just outside the body roof edge (~0.89) so Cycles rays reach the glass.
# Top capped at z=1.36 to avoid protrusion above roofline.
def build_glass():
    gm = mat_glass()

    def _pane(name, pts4):
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts4]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm)
        o.data.materials.append(gm)
        _mirror_y(o)

    # ── Windshield (front) ──
    _pane("windshield", [
        Vector((0.00, 0.00, 0.89)),   # bottom-center
        Vector((0.55, 0.00, 1.36)),   # top-center
        Vector((0.55, 0.91, 1.35)),   # top-outer
        Vector((0.00, 0.91, 0.89)),   # bottom-outer
    ])

    # ── Rear window ──
    _pane("rear_window", [
        Vector((2.05, 0.00, 0.88)),
        Vector((2.05, 0.91, 0.88)),
        Vector((1.55, 0.91, 1.35)),
        Vector((1.55, 0.00, 1.36)),
    ])

    # ── Front side window (A-pillar → B-pillar) ──
    _pane("front_side_win", [
        Vector((0.00, 0.91, 0.89)),   # front-bottom
        Vector((1.05, 0.91, 0.90)),   # rear-bottom
        Vector((1.05, 0.91, 1.36)),   # rear-top
        Vector((0.05, 0.91, 1.35)),   # front-top
    ])

    # ── Rear side window (B-pillar → C-pillar) ──
    _pane("rear_side_win", [
        Vector((1.05, 0.91, 0.90)),
        Vector((2.05, 0.91, 0.88)),
        Vector((2.05, 0.90, 1.08)),   # C-pillar slopes
        Vector((1.05, 0.91, 1.36)),
    ])


# ─────────────────── PANEL FEATURES ─────────────────────────
def build_panel_features():
    black  = _mat("panel_black",  (0.015, 0.015, 0.018), roughness=0.45)
    rubber = _mat("rubber_seal",  (0.020, 0.020, 0.022), roughness=0.65)
    dark   = _mat("panel_dark",   (0.025, 0.025, 0.028), roughness=0.40)
    chrome = _mat("chrome", (0.88, 0.90, 0.92), metallic=1.0, roughness=0.04)

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

    # A-pillar
    _half("a_pillar", [
        Vector((0.00, 0.91, 0.89)), Vector((0.00, 0.95, 0.89)),
        Vector((0.55, 0.94, 1.36)), Vector((0.55, 0.91, 1.36)),
    ], black)
    # B-pillar
    _half("b_pillar", [
        Vector((1.05, 0.91, 0.90)), Vector((1.05, 0.95, 0.90)),
        Vector((1.05, 0.94, 1.36)), Vector((1.05, 0.91, 1.36)),
    ], black)
    # C-pillar
    _half("c_pillar", [
        Vector((2.05, 0.91, 0.88)), Vector((2.05, 0.95, 0.88)),
        Vector((2.05, 0.93, 1.10)), Vector((2.05, 0.90, 1.08)),
    ], black)
    # Window sill belt-line strip
    _half("window_sill", [
        Vector((0.00, 0.91, 0.89)), Vector((2.05, 0.91, 0.88)),
        Vector((2.05, 0.96, 0.88)), Vector((0.00, 0.96, 0.89)),
    ], rubber)
    # Roof drip rail
    _half("roof_rail", [
        Vector((0.50, 0.908, 1.376)), Vector((1.55, 0.908, 1.382)),
        Vector((1.55, 0.918, 1.378)), Vector((0.50, 0.918, 1.372)),
    ], rubber)
    # Door gap – front door seam
    _half("door_gap_A", [
        Vector(( 0.02, 0.91, 0.89)), Vector((-0.02, 0.95, 0.89)),
        Vector((-0.02, 0.98, 0.55)), Vector(( 0.02, 0.96, 0.55)),
    ], dark)
    # Door gap – B-pillar seam
    _half("door_gap_B", [
        Vector((1.03, 0.91, 0.90)), Vector((1.07, 0.91, 0.90)),
        Vector((1.07, 0.97, 0.54)), Vector((1.03, 0.97, 0.54)),
    ], dark)
    # Trunk lid line
    _full("trunk_line", [
        Vector((2.47,  0.80, 0.80)), Vector((2.47, -0.80, 0.80)),
        Vector((2.47, -0.82, 0.82)), Vector((2.47,  0.82, 0.82)),
    ], dark)
    # Hood/cowl line
    _full("hood_cowl", [
        Vector((-0.03,  0.80, 0.88)), Vector((-0.03, -0.80, 0.88)),
        Vector((-0.08, -0.82, 0.86)), Vector((-0.08,  0.82, 0.86)),
    ], dark)

    # Door handles
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


# ─────────────────── HEADLIGHTS ─────────────────────────────
def build_headlights():
    chrome   = _mat("hl_chrome",   (0.72, 0.75, 0.80), metallic=0.96, roughness=0.06)
    lens_mat = _mat("hl_lens",     (0.92, 0.92, 0.90), roughness=0.0,
                    transmission=1.0, ior=1.50)
    drl_mat  = _mat("hl_drl",      (1.00, 0.97, 0.88),
                    emission=(1.00, 0.97, 0.88), emit_str=10.0)
    proj_mat = _mat("hl_proj",     (0.95, 0.95, 0.90),
                    emission=(1.00, 0.97, 0.90), emit_str=6.0)
    sig_mat  = _mat("hl_signal",   (0.90, 0.55, 0.02),
                    emission=(1.00, 0.60, 0.02), emit_str=4.0)

    for sy in (0.72, -0.72):
        sx = math.copysign(1, sy)   # +1 right, -1 left

        # Chrome housing (back of headlight unit)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.89, sy, 0.68))
        hsg = bpy.context.active_object; hsg.name = f"hl_hsg_{sy:.2f}"
        hsg.scale = (0.075, 0.155, 0.072)
        bpy.ops.object.transform_apply(scale=True)
        _assign(hsg, chrome)

        # Reflector inner bowl (half-sphere, chrome)
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.045, segments=16, ring_count=8,
            location=(-1.895, sy, 0.67))
        bowl = bpy.context.active_object; bowl.name = f"hl_bowl_{sy:.2f}"
        bowl.scale = (0.6, 1.0, 0.65)
        bpy.ops.object.transform_apply(scale=True)
        _assign(bowl, chrome)

        # Projector unit (small emissive sphere)
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=0.022, segments=12, ring_count=8,
            location=(-1.912, sy, 0.665))
        prj = bpy.context.active_object; prj.name = f"hl_proj_{sy:.2f}"
        _assign(prj, proj_mat)

        # DRL / LED strip (top bar)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.930, sy, 0.708))
        drl = bpy.context.active_object; drl.name = f"hl_drl_{sy:.2f}"
        drl.scale = (0.005, 0.148, 0.007)
        bpy.ops.object.transform_apply(scale=True)
        _assign(drl, drl_mat)

        # Turn signal (lower amber bar)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.930, sy, 0.640))
        sig = bpy.context.active_object; sig.name = f"hl_sig_{sy:.2f}"
        sig.scale = (0.005, 0.130, 0.008)
        bpy.ops.object.transform_apply(scale=True)
        _assign(sig, sig_mat)

        # Outer clear lens cover
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.935, sy, 0.675))
        lens = bpy.context.active_object; lens.name = f"hl_lens_{sy:.2f}"
        lens.scale = (0.006, 0.158, 0.075)
        bpy.ops.object.transform_apply(scale=True)
        _assign(lens, lens_mat)


# ─────────────────── TAILLIGHTS ─────────────────────────────
def build_taillights():
    chrome     = _mat("tl_chrome",  (0.72, 0.75, 0.80), metallic=0.95, roughness=0.06)
    brake_mat  = _mat("tl_brake",   (0.85, 0.01, 0.01),
                      emission=(1.0, 0.02, 0.02), emit_str=5.0)
    turn_mat   = _mat("tl_turn",    (0.88, 0.44, 0.01),
                      emission=(1.0, 0.55, 0.02), emit_str=4.0)
    rev_mat    = _mat("tl_rev",     (0.90, 0.90, 0.90),
                      emission=(0.98, 0.98, 0.98), emit_str=3.0)
    lens_r_mat = _mat("tl_lens_r",  (0.80, 0.02, 0.02), roughness=0.0,
                      transmission=0.8, ior=1.50)
    lens_a_mat = _mat("tl_lens_a",  (0.80, 0.45, 0.02), roughness=0.0,
                      transmission=0.8, ior=1.50)

    for sy in (0.76, -0.76):
        # Chrome surround frame
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.858, sy, 0.59))
        frm = bpy.context.active_object; frm.name = f"tl_frame_{sy:.2f}"
        frm.scale = (0.024, 0.215, 0.130)
        bpy.ops.object.transform_apply(scale=True)
        _assign(frm, chrome)

        # Brake section (top ~60%)
        for row in range(3):
            for col in range(4):
                bpy.ops.mesh.primitive_cube_add(size=1,
                    location=(2.862, sy - 0.07 + col*0.038, 0.64 - row*0.030))
                led = bpy.context.active_object
                led.name = f"tl_led_b_{sy:.2f}_{row}{col}"
                led.scale = (0.005, 0.014, 0.014)
                bpy.ops.object.transform_apply(scale=True)
                _assign(led, brake_mat)

        # Turn signal section (lower amber strip)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.862, sy, 0.535))
        ts = bpy.context.active_object; ts.name = f"tl_turn_{sy:.2f}"
        ts.scale = (0.006, 0.180, 0.022)
        bpy.ops.object.transform_apply(scale=True)
        _assign(ts, turn_mat)

        # Reverse light (small white)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.862, sy - 0.09, 0.510))
        rv = bpy.context.active_object; rv.name = f"tl_rev_{sy:.2f}"
        rv.scale = (0.006, 0.055, 0.016)
        bpy.ops.object.transform_apply(scale=True)
        _assign(rv, rev_mat)

        # Red outer lens (translucent cover)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(2.850, sy, 0.59))
        rl = bpy.context.active_object; rl.name = f"tl_rlens_{sy:.2f}"
        rl.scale = (0.007, 0.200, 0.125)
        bpy.ops.object.transform_apply(scale=True)
        _assign(rl, lens_r_mat)


# ─────────────────── LICENSE PLATES ─────────────────────────
def build_plates():
    plate_mat  = _mat("plate_white",  (0.92, 0.92, 0.94), roughness=0.4)
    frame_mat  = _mat("plate_frame",  (0.05, 0.05, 0.055), metallic=0.6, roughness=0.3)
    light_mat  = _mat("plate_light",  (0.95, 0.95, 0.90),
                      emission=(0.98, 0.98, 0.92), emit_str=3.0)

    for px, rz in [(-1.942, 0), (2.878, math.pi)]:
        # Plate
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.50))
        pl = bpy.context.active_object; pl.name = f"plate_{px:.2f}"
        pl.scale = (0.007, 0.270, 0.072)
        pl.rotation_euler.z = rz
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _assign(pl, plate_mat)

        # Frame border (slightly larger)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.50))
        fr = bpy.context.active_object; fr.name = f"plate_frame_{px:.2f}"
        fr.scale = (0.006, 0.295, 0.096)
        fr.rotation_euler.z = rz
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _assign(fr, frame_mat)

        # Plate illumination strip (above plate)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.555))
        pl_lt = bpy.context.active_object; pl_lt.name = f"plate_light_{px:.2f}"
        pl_lt.scale = (0.005, 0.24, 0.010)
        pl_lt.rotation_euler.z = rz
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _assign(pl_lt, light_mat)


# ─────────────────── INTERIOR ────────────────────────────────
def build_interior():
    bpy.ops.mesh.primitive_cube_add(size=1, location=(1.05, 0, 0.89))
    box = bpy.context.active_object; box.name = "interior_cavity"
    box.scale = (1.05, 0.86, 0.22)
    bpy.ops.object.transform_apply(scale=True)
    _assign(box, _mat("interior_dark", (0.02, 0.02, 0.022), roughness=0.7))

    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.08, 0, 0.94))
    dash = bpy.context.active_object; dash.name = "dashboard"
    dash.scale = (0.25, 0.88, 0.048)
    bpy.ops.object.transform_apply(scale=True)
    _assign(dash, _mat("dash_mat", (0.05, 0.05, 0.055), roughness=0.4))

    bpy.ops.mesh.primitive_torus_add(
        location=(-0.22, -0.26, 0.88), major_radius=0.17, minor_radius=0.016,
        major_segments=32, minor_segments=10,
        rotation=(math.radians(75), 0, 0))
    sw = bpy.context.active_object; sw.name = "steering_wheel"
    _assign(sw, _mat("sw_mat", (0.07, 0.07, 0.075), roughness=0.35))


# ─────────────────── WHEELS ─────────────────────────────────
def build_wheel(x, y, R=0.33, W=0.22):
    """
    5-spoke alloy rim in world-space XZ.
    D_F / D_B are signed by wheel side so left and right are symmetric.
    """
    side  = math.copysign(1, y)   # +1 right, -1 left
    D_F   =  side * W * 0.42      # outboard face (away from car centre)
    D_B   = -side * W * 0.18      # inboard  face

    N_SP  = 5
    N_RIM = 48
    R_RIM = R * 0.90
    R_HUB = R * 0.13
    W_SP_O = R * 0.055
    W_SP_I = R * 0.028

    parts = []

    # ── TIRE ──
    T = R * 0.175
    bpy.ops.mesh.primitive_torus_add(
        location=(x, y, R),
        rotation=(math.radians(90), 0, 0),
        major_radius=R - T, minor_radius=T,
        major_segments=72, minor_segments=24)
    tire = bpy.context.active_object; tire.name = f"tire_{x:.2f}_{y:.2f}"
    _smooth(tire)
    _assign(tire, mat_tire())
    parts.append(tire)

    # ── RIM ──
    bm = bmesh.new()

    def _circ(n, r, wy):
        return [bm.verts.new(Vector((
            x + r * math.cos(2*math.pi*i/n),
            wy,
            R + r * math.sin(2*math.pi*i/n),
        ))) for i in range(n)]

    of_ = _circ(N_RIM, R_RIM, y + D_F)
    ob_ = _circ(N_RIM, R_RIM, y + D_B)

    # Rim wall
    for i in range(N_RIM):
        ni = (i + 1) % N_RIM
        bm.faces.new([of_[i], ob_[i], ob_[ni], of_[ni]])

    # Solid back cap
    bc = bm.verts.new(Vector((x, y + D_B, R)))
    for i in range(N_RIM):
        ni = (i + 1) % N_RIM
        bm.faces.new([bc, ob_[i], ob_[ni]])

    # 5 box spokes
    for s in range(N_SP):
        ang = 2 * math.pi * s / N_SP
        ca, sa = math.cos(ang), math.sin(ang)
        px, pz = -sa, ca   # perp in XZ plane

        def _sv(r, hw, wy):
            return (
                bm.verts.new(Vector((x + r*ca + px*hw, wy, R + r*sa + pz*hw))),
                bm.verts.new(Vector((x + r*ca - px*hw, wy, R + r*sa - pz*hw))),
            )

        foL, foR = _sv(R_RIM * 0.97, W_SP_O, y + D_F)
        fiL, fiR = _sv(R_HUB * 1.05, W_SP_I, y + D_F)
        boL, boR = _sv(R_RIM * 0.97, W_SP_O, y + D_B * 0.55)
        biL, biR = _sv(R_HUB * 1.05, W_SP_I, y + D_B * 0.55)

        try:
            bm.faces.new([foL, foR, fiR, fiL])
            bm.faces.new([boR, boL, biL, biR])
            bm.faces.new([foL, boL, boR, foR])
            bm.faces.new([fiL, fiR, biR, biL])
            bm.faces.new([foL, fiL, biL, boL])
            bm.faces.new([foR, boR, biR, fiR])
        except Exception: pass

    # Hub cap
    N_HUB = 16
    hf_ = _circ(N_HUB, R_HUB, y + D_F * 0.92)
    hb_ = _circ(N_HUB, R_HUB, y + D_B)
    hcf = bm.verts.new(Vector((x, y + D_F * 0.92, R)))
    hcb = bm.verts.new(Vector((x, y + D_B, R)))
    for i in range(N_HUB):
        ni = (i + 1) % N_HUB
        bm.faces.new([hcf, hf_[i], hf_[ni]])
        bm.faces.new([hcb, hb_[ni], hb_[i]])
        bm.faces.new([hf_[i], hf_[ni], hb_[ni], hb_[i]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rim = _bm_obj(f"rim_{x:.2f}_{y:.2f}", bm)
    _smooth(rim)
    sub = rim.modifiers.new("SubSurf", "SUBSURF")
    sub.levels = 1; sub.render_levels = 2
    _assign(rim, _mat("rim_alloy", (0.82, 0.85, 0.90),
                      metallic=0.96, roughness=0.08, aniso=0.72))
    parts.append(rim)

    # Brake disc
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=R * 0.44, depth=0.018,
        location=(x, y, R), rotation=(math.radians(90), 0, 0))
    disc = bpy.context.active_object; disc.name = f"disc_{x:.2f}_{y:.2f}"
    _smooth(disc)
    _assign(disc, _mat("brake_disc", (0.26, 0.26, 0.27), metallic=0.75, roughness=0.52))
    parts.append(disc)

    # Red brake caliper (inboard side)
    cal_y = y - math.copysign(R * 0.32, y)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, cal_y, R * 0.62))
    cal = bpy.context.active_object; cal.name = f"caliper_{x:.2f}_{y:.2f}"
    cal.scale = (0.18, 0.08, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    _assign(cal, _mat("caliper_red", (0.75, 0.02, 0.02), roughness=0.3))
    parts.append(cal)

    return parts


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
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(38)
    sky.sun_rotation   = math.radians(145)
    try: sky.air_density = 1.0; sky.dust_density = 0.35
    except Exception: pass
    bg.inputs["Strength"].default_value = 0.50

def setup_studio():
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0.55, 0, 0))
    _assign(bpy.context.active_object,
            _mat("floor_dark", (0.26, 0.26, 0.28), roughness=0.20))

def setup_lighting():
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object; sun.name = "sun"
    sun.data.energy = 4.0; sun.data.color = (1.0, 0.97, 0.88)
    sun.data.angle  = math.radians(0.5)
    sun.rotation_euler = Euler((math.radians(52), 0, math.radians(145)), "XYZ")

    bpy.ops.object.light_add(type="AREA", location=(6, 5, 4))
    fill = bpy.context.active_object; fill.name = "fill"
    fill.data.energy = 180; fill.data.size = 9
    fill.data.color  = (0.78, 0.88, 1.0)
    fill.rotation_euler = Euler((math.radians(28), 0, math.radians(148)), "XYZ")

    bpy.ops.object.light_add(type="AREA", location=(4, -3, 6))
    rim = bpy.context.active_object; rim.name = "rim"
    rim.data.energy = 250; rim.data.size = 4
    rim.data.color  = (1.0, 0.95, 0.82)
    rim.rotation_euler = Euler((math.radians(-18), 0, math.radians(165)), "XYZ")


# ─────────────────── CAMERA ─────────────────────────────────
def setup_camera():
    scene = bpy.context.scene
    scene.frame_start = 1; scene.frame_end = 150; scene.render.fps = 25

    cd = bpy.data.cameras.new("Camera"); cd.lens = 65
    cam = bpy.data.objects.new("Camera", cd)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam

    tx, ty, tz = 0.55, 0.0, 0.82
    R_orb = 7.8; H_lo, H_hi = 1.10, 2.80

    for f in range(1, 151):
        t  = (f - 1) / 149.0
        ts = t * t * (3 - 2 * t)
        ang = math.radians(-105) + ts * math.radians(280)
        h   = H_lo + (H_hi - H_lo) * math.sin(math.pi * t)
        cx  = tx + R_orb * math.cos(ang)
        cy  = R_orb * math.sin(ang)
        cam.location = (cx, cy, h)
        d = Vector((tx - cx, ty - cy, tz - h)).normalized()
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)


# ─────────────────── RENDER ─────────────────────────────────
def setup_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    # OPTIX denoiser: RTX hardware, near-zero extra VRAM (OIDN-GPU needs several GB)
    for dn in ("OPTIX", "OPENIMAGEDENOISE"):
        try: scene.cycles.denoiser = dn; break
        except Exception: pass
    scene.cycles.use_adaptive_sampling  = True
    scene.cycles.adaptive_threshold     = 0.005
    scene.cycles.adaptive_min_samples   = 32

    # Limit transmission/transparency bounces to avoid VRAM blow-up on glass frames
    try:
        scene.cycles.transmission_bounces   = 8
        scene.cycles.transparent_max_bounces = 8
    except Exception: pass

    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.filepath     = RENDER_PATH
    scene.render.image_settings.file_format  = "FFMPEG"
    scene.render.ffmpeg.format               = "MPEG4"
    scene.render.ffmpeg.codec                = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"

    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look           = "Low Contrast"
    scene.view_settings.exposure        = -0.25
    scene.view_settings.gamma           = 1.0
    scene.display_settings.display_device = "sRGB"


# ─────────────────── MAIN ────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    enable_gpu()
    clear_scene()

    paint = mat_paint("paint_deep_blue", (0.01, 0.04, 0.55))

    build_body(paint)
    build_glass()
    build_interior()
    build_panel_features()
    build_headlights()
    build_taillights()
    build_plates()

    for wx, wy in [(-0.95, -0.97), (-0.95, 0.97), (2.05, -0.97), (2.05, 0.97)]:
        build_wheel(wx, wy, R=0.33, W=0.22)

    setup_world()
    setup_studio()
    setup_lighting()
    setup_camera()
    setup_render()

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[save] {BLEND_PATH}")
    print("[render] Cycles OPTIX …")
    bpy.ops.render.render(animation=True)
    print(f"[render] Done → {RENDER_PATH}")


if __name__ == "__main__":
    main()

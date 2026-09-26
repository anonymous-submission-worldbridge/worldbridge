#!/usr/bin/env python3
"""
vehicle_demo_v4.py — sports sedan with clean geometry:
  • Solid paint (no noise randomness)
  • Glass panels inside body profile (no roof protrusion)
  • 5-spoke rim built in world-space XZ (no isolated vertices)
  • A/B/C pillars, window surrounds, door gap lines, hood/trunk lines
  • Cycles OPTIX + Nishita sky
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
BLEND_PATH  = os.path.join(OUTPUT_DIR, "vehicle_demo_v4.blend")
RENDER_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v4")

# ─────────────────────────── GPU ────────────────────────────
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

# ─────────────────────────── UTILS ──────────────────────────
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

# ─────────────────────────── MATERIALS ──────────────────────
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
        mat.blend_method = "BLEND"; mat.use_backface_culling = False
    if emission and emit_str > 0:
        for k in ("Emission Color", "Emission"):
            if k in bsdf.inputs: bsdf.inputs[k].default_value = (*emission, 1.0); break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_str
    if aniso > 0 and "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = aniso
    return mat


def mat_paint(name, color):
    """Clean solid car paint: no noise, correct roughness for colour visibility."""
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.10   # enough to show colour
    bsdf.inputs["IOR"].default_value        = 1.52
    for k, v in [("Coat Weight", 0.88), ("Coat Roughness", 0.05), ("Coat IOR", 1.52)]:
        if k in bsdf.inputs: bsdf.inputs[k].default_value = v
    if "Clearcoat" in bsdf.inputs: bsdf.inputs["Clearcoat"].default_value = 0.88
    return mat


def mat_glass():
    name = "car_glass"
    if name in bpy.data.materials: return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (0.03, 0.10, 0.06, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.0
    bsdf.inputs["IOR"].default_value        = 1.52
    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs: bsdf.inputs[k].default_value = 0.95; break
    bsdf.inputs["Alpha"].default_value = 0.25
    mat.blend_method = "BLEND"; mat.use_backface_culling = False
    return mat


# ─────────────────────────── BODY ───────────────────────────
SEDAN_ST = [
    # x      w      z_top   z_belt  z_sill  z_floor
    (-1.90, 0.18,   0.38,   0.36,   0.22,   0.10),
    (-1.72, 0.76,   0.54,   0.46,   0.22,   0.10),
    (-1.45, 0.91,   0.80,   0.65,   0.22,   0.10),
    (-1.05, 0.93,   1.00,   0.78,   0.22,   0.10),
    (-0.40, 0.94,   1.10,   0.82,   0.22,   0.10),
    ( 0.00, 0.95,   1.34,   0.87,   0.22,   0.10),
    ( 0.55, 0.96,   1.40,   0.88,   0.22,   0.10),
    ( 1.05, 0.96,   1.42,   0.88,   0.22,   0.10),
    ( 1.55, 0.95,   1.40,   0.88,   0.22,   0.10),
    ( 2.05, 0.94,   1.20,   0.85,   0.22,   0.10),
    ( 2.50, 0.91,   0.82,   0.78,   0.22,   0.10),
    ( 2.82, 0.78,   0.56,   0.52,   0.22,   0.10),
    ( 3.00, 0.20,   0.38,   0.36,   0.22,   0.10),
]
N_PROF = 9


def _profile(x, w, z_top, z_belt, z_sill, z_floor):
    z_mid = (z_belt + z_sill) * 0.5 + 0.05
    return [
        Vector((x, 0.0,       z_top)),
        Vector((x, w*0.68,    z_top)),
        Vector((x, w*0.93,    z_top - 0.022)),
        Vector((x, w*1.005,   z_belt + 0.185)),
        Vector((x, w*1.058,   z_mid)),
        Vector((x, w*1.038,   z_sill + 0.048)),
        Vector((x, w*0.982,   z_sill)),
        Vector((x, w*0.680,   z_floor)),
        Vector((x, 0.0,       z_floor)),
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


# ─────────────────────────── GLASS ──────────────────────────
# All Y values ≤ 0.90 so they sit inside the body profile (roof edge ~0.893).
# The half-pane is mirrored; glass is double-sided.
def build_glass():
    gm  = mat_glass()

    def _pane(name, pts4):
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts4]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm)
        o.data.materials.append(gm)
        _mirror_y(o)

    # Windshield: bottom (x=0.00, z=0.88) → top (x=0.55, z=1.38)
    _pane("windshield", [
        Vector((0.00, 0.00, 0.88)),
        Vector((0.55, 0.00, 1.38)),
        Vector((0.55, 0.88, 1.37)),
        Vector((0.00, 0.87, 0.88)),
    ])

    # Rear window: C-pillar sloping back
    _pane("rear_window", [
        Vector((2.05, 0.00, 0.87)),
        Vector((2.05, 0.87, 0.87)),
        Vector((1.55, 0.88, 1.37)),
        Vector((1.55, 0.00, 1.38)),
    ])

    # Front side window (A-pillar to B-pillar)
    _pane("front_side_win", [
        Vector((0.00, 0.87, 0.88)),   # front-bottom
        Vector((1.05, 0.88, 0.89)),   # rear-bottom (B-pillar)
        Vector((1.05, 0.88, 1.40)),   # rear-top
        Vector((0.05, 0.87, 1.38)),   # front-top
    ])

    # Rear side window (B-pillar to C-pillar)
    _pane("rear_side_win", [
        Vector((1.05, 0.88, 0.89)),   # front-bottom
        Vector((2.05, 0.87, 0.87)),   # rear-bottom
        Vector((2.05, 0.86, 1.08)),   # rear-top (C-pillar lower)
        Vector((1.05, 0.88, 1.40)),   # front-top
    ])


# ─────────────────────────── PANEL FEATURES ─────────────────
def build_panel_features(paint):
    """A/B/C pillars, window surrounds, door gap lines, hood/trunk lines."""
    black  = _mat("panel_black",  (0.015, 0.015, 0.018), roughness=0.45)
    rubber = _mat("rubber_seal",  (0.02,  0.02,  0.022), roughness=0.65)
    dark   = _mat("panel_dark",   (0.025, 0.025, 0.028), roughness=0.40)

    def _strip_half(name, pts, mat):
        """Flat quad strip on the body surface (half, mirrored)."""
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm)
        o.data.materials.append(mat)
        _mirror_y(o)

    def _strip_sym(name, pts, mat):
        """Full-width symmetric strip (no mirror)."""
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm)
        o.data.materials.append(mat)

    # ── A-pillar (windshield edge to roof front, each side) ──
    _strip_half("a_pillar", [
        Vector((0.00,  0.87, 0.88)),   # bottom-inner
        Vector((0.00,  0.92, 0.88)),   # bottom-outer
        Vector((0.55,  0.92, 1.38)),   # top-outer
        Vector((0.55,  0.88, 1.38)),   # top-inner
    ], black)

    # ── B-pillar (between front & rear side windows) ──
    _strip_half("b_pillar", [
        Vector((1.05, 0.88, 0.89)),
        Vector((1.05, 0.93, 0.89)),
        Vector((1.05, 0.92, 1.40)),
        Vector((1.05, 0.88, 1.40)),
    ], black)

    # ── C-pillar (rear quarter) ──
    _strip_half("c_pillar", [
        Vector((2.05, 0.87, 0.87)),
        Vector((2.05, 0.93, 0.87)),
        Vector((2.05, 0.92, 1.10)),
        Vector((2.05, 0.86, 1.08)),
    ], black)

    # ── Window surround / rubber seal (belt line strip each side) ──
    _strip_half("window_sill_trim", [
        Vector((0.00, 0.87, 0.88)),
        Vector((2.05, 0.87, 0.87)),
        Vector((2.05, 0.93, 0.87)),
        Vector((0.00, 0.93, 0.88)),
    ], rubber)

    # ── Roof surround / drip rail (half) ──
    _strip_half("roof_rail", [
        Vector((0.45, 0.885, 1.385)),
        Vector((1.60, 0.885, 1.390)),
        Vector((1.60, 0.895, 1.385)),
        Vector((0.45, 0.895, 1.380)),
    ], rubber)

    # ── Door gap line — front door front edge (x ≈ 0.00, both sides) ──
    _strip_half("door_gap_front", [
        Vector((0.02, 0.88, 0.88)),
        Vector((-0.01, 0.93, 0.89)),
        Vector((-0.01, 0.96, 0.60)),
        Vector(( 0.02, 0.94, 0.60)),
    ], dark)

    # ── Door gap line — rear door / B-pillar seam ──
    _strip_half("door_gap_rear", [
        Vector((1.03, 0.88, 0.89)),
        Vector((1.07, 0.88, 0.89)),
        Vector((1.07, 0.95, 0.55)),
        Vector((1.03, 0.95, 0.55)),
    ], dark)

    # ── Trunk lid line (full-width) ──
    _strip_sym("trunk_line", [
        Vector((2.47,  0.80, 0.80)),
        Vector((2.47, -0.80, 0.80)),
        Vector((2.47, -0.82, 0.82)),
        Vector((2.47,  0.82, 0.82)),
    ], dark)

    # ── Hood rear edge / cowl (full-width at windshield base) ──
    _strip_sym("hood_rear", [
        Vector((-0.03,  0.80, 0.88)),
        Vector((-0.03, -0.80, 0.88)),
        Vector((-0.08, -0.82, 0.86)),
        Vector((-0.08,  0.82, 0.86)),
    ], dark)

    # ── Door handles (chrome cubes, each side) ──
    chrome = _mat("chrome", (0.88, 0.90, 0.92), metallic=1.0, roughness=0.04)
    for sy in (0.968, -0.968):
        for hx in (0.12, 1.35):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(hx, sy, 0.82))
            dh = bpy.context.active_object; dh.name = f"dh_{hx:.2f}_{sy:.2f}"
            dh.scale = (0.080, 0.008, 0.020)
            bpy.ops.object.transform_apply(scale=True)
            _assign(dh, chrome)

    # ── Front grille bars ──
    for gz, gscz in [(0.60, 0.058), (0.51, 0.042)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.935, 0, gz))
        g = bpy.context.active_object; g.name = f"grille_{gz:.2f}"
        g.scale = (0.022, 0.75, gscz)
        bpy.ops.object.transform_apply(scale=True)
        _assign(g, chrome)

    # ── License plates ──
    plate = _mat("plate_white", (0.90, 0.90, 0.92), roughness=0.5)
    for px, rz in [(-1.94, 0), (2.88, math.pi)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.50))
        pl = bpy.context.active_object; pl.name = f"plate_{px:.2f}"
        pl.scale = (0.008, 0.27, 0.072)
        pl.rotation_euler.z = rz
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _assign(pl, plate)


# ─────────────────────────── INTERIOR ───────────────────────
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


# ─────────────────────────── WHEELS ─────────────────────────
def build_wheel(x, y, R=0.33, W=0.22):
    """
    5-spoke alloy rim built directly in world-space XZ plane.
    No rotation applied to rim object → no coordinate confusion.
    No isolated vertices → no point artifacts.
    """
    N_RIM = 48
    N_SP  = 5
    R_RIM = R * 0.90     # outer spoke/rim attachment radius
    R_HUB = R * 0.13     # hub cap outer radius
    W_SP_O = R * 0.055   # half-spoke-width at outer end
    W_SP_I = R * 0.028   # half-spoke-width at inner end
    D_F   =  W * 0.42    # front face y-offset from wheel centre
    D_B   = -W * 0.18    # back  face y-offset

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
    _assign(tire, _mat("tire_rubber", (0.03, 0.03, 0.03), roughness=0.90))
    parts.append(tire)

    # ── RIM (built in world XZ, no rotation on the object) ──
    bm = bmesh.new()

    def _circ(n, r, wy):
        """N verts on circle of radius r in world XZ plane at y=wy."""
        return [bm.verts.new(Vector((
            x + r * math.cos(2*math.pi*i/n),
            wy,
            R + r * math.sin(2*math.pi*i/n),
        ))) for i in range(n)]

    # Outer rim ring (front & back circles)
    of_ = _circ(N_RIM, R_RIM, y + D_F)
    ob_ = _circ(N_RIM, R_RIM, y + D_B)

    # Rim wall quads
    for i in range(N_RIM):
        ni = (i + 1) % N_RIM
        bm.faces.new([of_[i], ob_[i], ob_[ni], of_[ni]])

    # Solid back cap
    bc = bm.verts.new(Vector((x, y + D_B, R)))
    for i in range(N_RIM):
        ni = (i + 1) % N_RIM
        bm.faces.new([bc, ob_[i], ob_[ni]])

    # 5 spokes — built in world XZ (spoke direction = cos/sin of ang)
    for s in range(N_SP):
        ang = 2 * math.pi * s / N_SP
        ca, sa = math.cos(ang), math.sin(ang)
        px, pz = -sa, ca   # perpendicular in XZ plane

        def _sv(r, hw, wy):
            """Two vertices symmetric about the spoke centre at radius r."""
            return (
                bm.verts.new(Vector((x + r*ca + px*hw, wy, R + r*sa + pz*hw))),
                bm.verts.new(Vector((x + r*ca - px*hw, wy, R + r*sa - pz*hw))),
            )

        foL, foR = _sv(R_RIM * 0.97, W_SP_O, y + D_F)
        fiL, fiR = _sv(R_HUB * 1.05, W_SP_I, y + D_F)
        boL, boR = _sv(R_RIM * 0.97, W_SP_O, y + D_B * 0.55)
        biL, biR = _sv(R_HUB * 1.05, W_SP_I, y + D_B * 0.55)

        try:
            bm.faces.new([foL, foR, fiR, fiL])           # front face
            bm.faces.new([boR, boL, biL, biR])           # back face
            bm.faces.new([foL, boL, boR, foR])           # outer edge
            bm.faces.new([fiL, fiR, biR, biL])           # inner edge
            bm.faces.new([foL, fiL, biL, boL])           # left side
            bm.faces.new([foR, boR, biR, fiR])           # right side
        except Exception:
            pass

    # Hub cap
    N_HUB = 16
    hf_ = _circ(N_HUB, R_HUB, y + D_F * 0.92)
    hb_ = _circ(N_HUB, R_HUB, y + D_B)
    hcf = bm.verts.new(Vector((x, y + D_F * 0.92, R)))
    hcb = bm.verts.new(Vector((x, y + D_B,         R)))
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

    # ── BRAKE DISC ──
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=R * 0.44, depth=0.018,
        location=(x, y, R), rotation=(math.radians(90), 0, 0))
    disc = bpy.context.active_object; disc.name = f"disc_{x:.2f}_{y:.2f}"
    _smooth(disc)
    _assign(disc, _mat("brake_disc", (0.26, 0.26, 0.27), metallic=0.75, roughness=0.52))
    parts.append(disc)

    # ── BRAKE CALIPER (red, toward car centre) ──
    cal_y = y - math.copysign(R * 0.32, y)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(x, cal_y, R * 0.62))
    cal = bpy.context.active_object; cal.name = f"caliper_{x:.2f}_{y:.2f}"
    cal.scale = (0.18, 0.08, 0.12)
    bpy.ops.object.transform_apply(scale=True)
    _assign(cal, _mat("caliper_red", (0.75, 0.02, 0.02), roughness=0.3))
    parts.append(cal)

    return parts


# ─────────────────────────── LIGHTS ─────────────────────────
def build_headlights():
    lens = _mat("hl_lens", (0.92, 0.92, 0.90), roughness=0.0,
                transmission=0.88, ior=1.52, alpha=0.12)
    drl  = _mat("hl_drl",  (1.0, 0.97, 0.88),
                emission=(1.0, 0.97, 0.88), emit_str=8.0)
    proj = _mat("hl_proj", (1.0, 0.96, 0.88),
                emission=(1.0, 0.97, 0.90), emit_str=5.0)
    for sy in (0.76, -0.76):
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.920, sy, 0.68))
        hl = bpy.context.active_object; hl.name = f"hl_{sy:.2f}"
        hl.scale = (0.058, 0.155, 0.058); bpy.ops.object.transform_apply(scale=True)
        _assign(hl, lens)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.935, sy, 0.70))
        dr = bpy.context.active_object; dr.name = f"drl_{sy:.2f}"
        dr.scale = (0.005, 0.148, 0.006); bpy.ops.object.transform_apply(scale=True)
        _assign(dr, drl)
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.030,
            location=(-1.905, sy, 0.67), segments=16, ring_count=10)
        pr = bpy.context.active_object; pr.name = f"proj_{sy:.2f}"
        pr.scale = (1.4, 1.0, 0.68); bpy.ops.object.transform_apply(scale=True)
        _assign(pr, proj)


def build_taillights():
    for sy in (0.78, -0.78):
        for mat_n, col, em, dz in [
            ("tl_brake", (0.88,0.01,0.01), (1.0,0.02,0.02), 0.00),
            ("tl_turn",  (0.88,0.44,0.01), (1.0,0.55,0.02),-0.060),
            ("tl_rev",   (0.90,0.90,0.90), (0.98,0.98,0.98),-0.115),
        ]:
            bpy.ops.mesh.primitive_cube_add(size=1,
                location=(2.855, sy, 0.60 + dz))
            tl = bpy.context.active_object; tl.name = f"{mat_n}_{sy:.2f}"
            tl.scale = (0.020, 0.21, 0.040); bpy.ops.object.transform_apply(scale=True)
            _assign(tl, _mat(mat_n, col, emission=em, emit_str=4.0, alpha=0.72))


# ─────────────────────────── WORLD / LIGHTING ───────────────
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
    bg.inputs["Strength"].default_value = 0.50   # subdued; sun does the main work


def setup_studio():
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0.55, 0, 0))
    fl = bpy.context.active_object; fl.name = "studio_floor"
    _assign(fl, _mat("floor_dark", (0.26, 0.26, 0.28), metallic=0.0, roughness=0.20))


def setup_lighting():
    # Sun matched to Nishita direction
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object; sun.name = "sun"
    sun.data.energy = 4.0; sun.data.color = (1.0, 0.97, 0.88)
    sun.data.angle  = math.radians(0.5)
    sun.rotation_euler = Euler((math.radians(52), 0, math.radians(145)), "XYZ")

    # Cool fill from opposite side
    bpy.ops.object.light_add(type="AREA", location=(6, 5, 4))
    fill = bpy.context.active_object; fill.name = "fill"
    fill.data.energy = 180; fill.data.size = 9
    fill.data.color  = (0.78, 0.88, 1.0)
    fill.rotation_euler = Euler((math.radians(28), 0, math.radians(148)), "XYZ")

    # Warm rim from rear-above (highlights roofline)
    bpy.ops.object.light_add(type="AREA", location=(4, -3, 6))
    rim = bpy.context.active_object; rim.name = "rim"
    rim.data.energy = 250; rim.data.size = 4
    rim.data.color  = (1.0, 0.95, 0.82)
    rim.rotation_euler = Euler((math.radians(-18), 0, math.radians(165)), "XYZ")


# ─────────────────────────── CAMERA ─────────────────────────
def setup_camera():
    scene = bpy.context.scene
    scene.frame_start = 1; scene.frame_end = 150; scene.render.fps = 25

    cd = bpy.data.cameras.new("Camera"); cd.lens = 65
    cam = bpy.data.objects.new("Camera", cd)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam

    tx, ty, tz = 0.55, 0.0, 0.82
    R_orb = 7.8
    H_lo, H_hi = 1.10, 2.80

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


# ─────────────────────────── RENDER ─────────────────────────
def setup_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    try:    scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        try: scene.cycles.denoiser = "OPTIX"
        except Exception: pass
    scene.cycles.use_adaptive_sampling   = True
    scene.cycles.adaptive_threshold      = 0.005
    scene.cycles.adaptive_min_samples    = 32

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


# ─────────────────────────── MAIN ───────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    enable_gpu()
    clear_scene()

    paint = mat_paint("paint_deep_blue", (0.01, 0.04, 0.55))

    build_body(paint)
    build_glass()
    build_interior()
    build_panel_features(paint)
    build_headlights()
    build_taillights()

    # Wheels: front axle x=-0.95, rear x=2.05; lateral y=±0.97
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

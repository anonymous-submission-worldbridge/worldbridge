#!/usr/bin/env python3
"""
vehicle_demo_v3.py — sports sedan, Cycles OPTIX + sky environment, 10-spoke wheels,
interior cavity, red brake calipers.  Quality eval — no road/buildings/trees.

Output: outputs/urban_v2_1/vehicle_demo_v3.blend + vehicle_demo_v3_0001-0150.mp4
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
from mathutils import Vector, Euler, Matrix

OUTPUT_DIR = f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_1'
BLEND_PATH  = os.path.join(OUTPUT_DIR, "vehicle_demo_v3.blend")
RENDER_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v3")

# ─────────────────────────── GPU ───────────────────────────
def enable_gpu():
    prefs = bpy.context.preferences
    cp = prefs.addons.get("cycles")
    if not cp:
        return
    cp = cp.preferences
    for backend in ("OPTIX", "CUDA", "HIP", "METAL"):
        try:
            cp.compute_device_type = backend
            cp.refresh_devices()
            devs = cp.get_devices_for_type(backend)
            if devs:
                for d in devs:
                    d.use = (d.type != "CPU")
                print(f"[GPU] {backend}: {[d.name for d in devs if d.use]}")
                break
        except Exception:
            continue
    bpy.context.scene.cycles.device = "GPU"

# ─────────────────────────── SCENE ──────────────────────────
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes, bpy.data.materials,
                bpy.data.cameras, bpy.data.lights, bpy.data.images):
        for blk in list(col):
            col.remove(blk)

def _new_obj(name, me):
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj

def _bm_obj(name, bm):
    me = bpy.data.meshes.new(name + "_me")
    bm.to_mesh(me); bm.free()
    return _new_obj(name, me)

def _smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True

def _assign(obj, mat, slot=0):
    while len(obj.data.materials) <= slot:
        obj.data.materials.append(None)
    obj.data.materials[slot] = mat

# ─────────────────────────── MATERIALS ──────────────────────
def _mat(name, color, metallic=0.0, roughness=0.5, alpha=1.0,
         transmission=0.0, coat=0.0, coat_rough=0.04, coat_ior=1.52,
         emission=None, emit_str=0.0, ior=1.45, aniso=0.0, aniso_rot=0.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (100, 0)
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
        if "Anisotropic Rotation" in bsdf.inputs:
            bsdf.inputs["Anisotropic Rotation"].default_value = aniso_rot
    return mat


def mat_paint(name, color):
    """Deep car paint: subtle metalflake + high clearcoat."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out   = nt.nodes.new("ShaderNodeOutputMaterial"); out.location   = (600, 0)
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location  = (300, 0)
    mix   = nt.nodes.new("ShaderNodeMixRGB");         mix.location   = (  0, 100)
    noise = nt.nodes.new("ShaderNodeTexNoise");       noise.location = (-350, 100)
    coord = nt.nodes.new("ShaderNodeTexCoord");       coord.location = (-600, 100)
    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],    mix.inputs["Fac"])
    nt.links.new(mix.outputs[0],          bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs[0],         out.inputs[0])
    noise.inputs["Scale"].default_value     = 1200.0
    noise.inputs["Detail"].default_value    = 16.0
    noise.inputs["Roughness"].default_value = 0.5
    mix.blend_type = "MIX"
    mix.inputs["Fac"].default_value  = 0.06
    mix.inputs[1].default_value      = (*color, 1.0)
    mix.inputs[2].default_value      = (1.0, 1.0, 1.0, 1.0)
    bsdf.inputs["Metallic"].default_value  = 0.05
    bsdf.inputs["Roughness"].default_value = 0.12   # shows base color; 0.025 = pure mirror
    bsdf.inputs["IOR"].default_value       = 1.52
    for k, v in [("Coat Weight", 0.85), ("Coat Roughness", 0.06), ("Coat IOR", 1.52)]:
        if k in bsdf.inputs: bsdf.inputs[k].default_value = v
    if "Clearcoat" in bsdf.inputs: bsdf.inputs["Clearcoat"].default_value = 0.85
    return mat


def mat_glass(name, tint=(0.03, 0.08, 0.05)):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.0
    bsdf.inputs["IOR"].default_value        = 1.52
    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs: bsdf.inputs[k].default_value = 0.96; break
    bsdf.inputs["Alpha"].default_value = 0.30
    mat.blend_method = "BLEND"; mat.use_backface_culling = False
    return mat


# ─────────────────────── SEDAN BODY ─────────────────────────
# Sports-sedan silhouette: long low hood, wide stance, fastback rear
# Stations: (x, half_width, z_top, z_belt, z_sill, z_floor)
SEDAN_ST = [
    (-1.90, 0.18, 0.38, 0.36, 0.22, 0.10),  #  0  front tip
    (-1.72, 0.76, 0.54, 0.46, 0.22, 0.10),  #  1  front bumper face
    (-1.45, 0.91, 0.80, 0.65, 0.22, 0.10),  #  2  hood / fender start
    (-1.05, 0.93, 1.00, 0.78, 0.22, 0.10),  #  3  front fender peak
    (-0.40, 0.94, 1.10, 0.82, 0.22, 0.10),  #  4  hood mid
    ( 0.00, 0.95, 1.34, 0.87, 0.22, 0.10),  #  5  A-pillar foot
    ( 0.55, 0.96, 1.40, 0.88, 0.22, 0.10),  #  6  front roof
    ( 1.05, 0.96, 1.42, 0.88, 0.22, 0.10),  #  7  roof center
    ( 1.55, 0.95, 1.40, 0.88, 0.22, 0.10),  #  8  rear roof / C-pillar top
    ( 2.05, 0.94, 1.20, 0.85, 0.22, 0.10),  #  9  rear fender peak / C-pillar
    ( 2.50, 0.91, 0.82, 0.78, 0.22, 0.10),  # 10  trunk / fastback
    ( 2.82, 0.78, 0.56, 0.52, 0.22, 0.10),  # 11  rear bumper face
    ( 3.00, 0.20, 0.38, 0.36, 0.22, 0.10),  # 12  tail tip
]
N_PROF = 9


def _profile(x, w, z_top, z_belt, z_sill, z_floor):
    z_mid = (z_belt + z_sill) * 0.5 + 0.05
    return [
        Vector((x, 0.0,        z_top)),              # 0 centerline top
        Vector((x, w * 0.68,   z_top)),              # 1 roof inner
        Vector((x, w * 0.93,   z_top - 0.022)),      # 2 roof edge / glass top
        Vector((x, w * 1.005,  z_belt + 0.185)),     # 3 upper shoulder
        Vector((x, w * 1.058,  z_mid)),              # 4 door max width
        Vector((x, w * 1.038,  z_sill + 0.048)),     # 5 sill top
        Vector((x, w * 0.982,  z_sill)),             # 6 sill bottom
        Vector((x, w * 0.680,  z_floor)),            # 7 underbody edge
        Vector((x, 0.0,        z_floor)),            # 8 centerline floor
    ]


def build_body(paint_mat):
    bm = bmesh.new()
    N = len(SEDAN_ST)
    grid = [[bm.verts.new(v) for v in _profile(*st)] for st in SEDAN_ST]
    bm.verts.ensure_lookup_table()

    # CCW from outside (+Y): front-top → front-bottom → rear-bottom → rear-top
    for i in range(N - 1):
        for j in range(N_PROF - 1):
            try:
                bm.faces.new([grid[i][j], grid[i][j+1],
                              grid[i+1][j+1], grid[i+1][j]])
            except ValueError:
                pass

    obj = _bm_obj("car_body", bm)
    _smooth(obj)

    mir = obj.modifiers.new("Mirror", "MIRROR")
    mir.use_axis[0] = False; mir.use_axis[1] = True; mir.use_axis[2] = False
    mir.use_bisect_axis[1] = True; mir.merge_threshold = 0.0005

    sub = obj.modifiers.new("SubSurf", "SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 2; sub.render_levels = 4

    _assign(obj, paint_mat)
    return obj


# ─────────────────── GLASS PANELS ───────────────────────────
def build_glass(glass_mat):
    def _half(name, pts4):
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts4]
        bm.faces.new(vs)
        # ensure normal faces outward (away from car interior)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_obj(name, bm)
        o.data.materials.append(glass_mat)
        mir = o.modifiers.new("Mirror", "MIRROR")
        mir.use_axis[1] = True; mir.merge_threshold = 0.0005
        return o

    # Windshield: A-pillar foot (x=0.00) to roof front (x=0.55)
    _half("windshield", [
        Vector((0.00, 0.00, 0.88)),  # bottom-center
        Vector((0.55, 0.00, 1.38)),  # top-center
        Vector((0.55, 0.92, 1.37)),  # top-outer
        Vector((0.00, 0.90, 0.88)),  # bottom-outer
    ])
    # Rear window: C-pillar (x=2.05) to roof rear (x=1.55)
    _half("rear_window", [
        Vector((2.05, 0.00, 0.87)),
        Vector((2.05, 0.90, 0.87)),
        Vector((1.55, 0.92, 1.37)),
        Vector((1.55, 0.00, 1.38)),
    ])
    # Front side window
    _half("front_side_win", [
        Vector((0.00, 0.95, 0.88)),
        Vector((1.05, 0.96, 0.89)),
        Vector((1.05, 0.95, 1.40)),
        Vector((0.05, 0.94, 1.38)),
    ])
    # Rear side window
    _half("rear_side_win", [
        Vector((1.05, 0.96, 0.89)),
        Vector((2.05, 0.94, 0.87)),
        Vector((2.05, 0.93, 1.08)),
        Vector((1.05, 0.95, 1.40)),
    ])


# ─────────────────── INTERIOR CAVITY ────────────────────────
def build_interior():
    """Dark interior box — visible through tinted glass."""
    bpy.ops.mesh.primitive_cube_add(size=1, location=(1.05, 0, 0.88))
    box = bpy.context.active_object; box.name = "interior_cavity"
    box.scale = (1.05, 0.88, 0.25)
    bpy.ops.object.transform_apply(scale=True)
    int_mat = _mat("interior_dark", (0.02, 0.02, 0.022), roughness=0.7)
    _assign(box, int_mat)

    # Dash top bar
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0.08, 0, 0.94))
    dash = bpy.context.active_object; dash.name = "dashboard"
    dash.scale = (0.25, 0.90, 0.05)
    bpy.ops.object.transform_apply(scale=True)
    _assign(dash, _mat("dash_mat", (0.05, 0.05, 0.055), roughness=0.4))

    # Steering wheel (torus)
    bpy.ops.mesh.primitive_torus_add(
        location=(-0.20, -0.25, 0.88),
        major_radius=0.18, minor_radius=0.018,
        major_segments=32, minor_segments=12,
        rotation=(math.radians(75), 0, 0)
    )
    sw = bpy.context.active_object; sw.name = "steering_wheel"
    _assign(sw, _mat("sw_mat", (0.08, 0.08, 0.08), roughness=0.35))


# ─────────────────── 10-SPOKE WHEEL ─────────────────────────
def build_wheel(x, y, R=0.33, W=0.24, mirror_x=False):
    """Sports 10-spoke alloy wheel with proper 3D spoke geometry,
    brake rotor, and red caliper."""
    sx = -1 if mirror_x else 1   # flip axle-depth for left wheels
    parts = []

    # ── TIRE ──
    T = R * 0.175
    bpy.ops.mesh.primitive_torus_add(
        location=(x, y, R),
        rotation=(math.radians(90), 0, 0),
        major_radius=R - T, minor_radius=T,
        major_segments=72, minor_segments=24)
    tire = bpy.context.active_object; tire.name = f"tire_{x:.2f}"
    _smooth(tire)
    _assign(tire, _mat("tire_rubber", (0.03, 0.03, 0.03), roughness=0.90))
    parts.append(tire)

    # ── ALLOY RIM (10-spoke) ──
    N_OUT = 60
    N_SP  = 10
    R_OUT = R * 0.94   # outer rim radius
    R_HUB = R * 0.12   # hub cap radius
    R_BR  = R * 0.48   # brake disc radius (where spokes end)
    W2    = W * 0.5    # half wheel width

    # spoke geometry: tapered with concave face
    W_SP_O = R * 0.065  # half-width at outer end
    W_SP_I = R * 0.028  # half-width at inner end
    D_F    = W2 * 0.82  # front face depth (x offset, wheel's local space)
    D_B    = -W2 * 0.28 # back face depth

    def rim_v(bm_r, r, n, depth):
        return [bm_r.verts.new(Vector((depth, r*math.cos(2*math.pi*i/n),
                                            r*math.sin(2*math.pi*i/n)))) for i in range(n)]

    bm = bmesh.new()

    # Outer rim ring – front and back circles
    of_ = rim_v(bm, R_OUT, N_OUT, D_F)
    ob_ = rim_v(bm, R_OUT, N_OUT, D_B)
    for i in range(N_OUT):
        ni = (i+1) % N_OUT
        bm.faces.new([of_[i], of_[ni], ob_[ni], ob_[i]])
    # Back face (annular fill – solid between hub and outer rim)
    bc_ = bm.verts.new(Vector((D_B, 0, 0)))
    for i in range(N_OUT):
        ni = (i+1) % N_OUT
        bm.faces.new([bc_, ob_[i], ob_[ni]])

    # 10 spokes (box geometry per spoke, front face + extruded sides)
    step = N_OUT // N_SP
    for s in range(N_SP):
        ang = 2*math.pi * s / N_SP
        ca, sa = math.cos(ang), math.sin(ang)
        pa, pb = -sa, ca           # perpendicular in YZ plane

        def sp(r, hw):
            cy = r*ca; cz = r*sa
            return (cy + pa*hw, cz + pb*hw), (cy - pa*hw, cz - pb*hw)

        o1a, o1b = sp(R_OUT * 0.91, W_SP_O)
        i1a, i1b = sp(R_BR  * 1.02, W_SP_I)

        # 8 verts: front-face (4) + back-face (4)
        vff = [bm.verts.new(Vector((D_F, *o1a))),
               bm.verts.new(Vector((D_F, *o1b))),
               bm.verts.new(Vector((D_F, *i1b))),
               bm.verts.new(Vector((D_F, *i1a)))]
        vbk = [bm.verts.new(Vector((D_B*0.5, *o1a))),
               bm.verts.new(Vector((D_B*0.5, *o1b))),
               bm.verts.new(Vector((D_B*0.5, *i1b))),
               bm.verts.new(Vector((D_B*0.5, *i1a)))]
        try:
            bm.faces.new(vff)            # front
            bm.faces.new(list(reversed(vbk)))  # back
            for j in range(4):
                nj = (j+1)%4
                bm.faces.new([vff[j], vbk[j], vbk[nj], vff[nj]])
        except Exception:
            pass

    # Hub cap
    hf_ = rim_v(bm, R_HUB, 20, D_F * 0.9)
    hb_ = rim_v(bm, R_HUB, 20, D_B * 0.5)
    hcf = bm.verts.new(Vector((D_F * 0.9, 0, 0)))
    hcb = bm.verts.new(Vector((D_B * 0.5, 0, 0)))
    for i in range(20):
        ni = (i+1) % 20
        bm.faces.new([hcf, hf_[i], hf_[ni]])
        bm.faces.new([hcb, hb_[ni], hb_[i]])
        bm.faces.new([hf_[i], hf_[ni], hb_[ni], hb_[i]])

    # 5 lug nuts
    for lu in range(5):
        ang = 2*math.pi * lu / 5 + math.pi/5
        ry = R_HUB * 1.8 * math.cos(ang)
        rz = R_HUB * 1.8 * math.sin(ang)
        for d in (D_F * 0.95, D_F * 0.85):
            bm.verts.new(Vector((d, ry, rz)))  # lug stub

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rim = _bm_obj(f"rim_{x:.2f}_{y:.2f}", bm)
    rim.location = (x, y, R)
    rim.rotation_euler = (math.radians(90), 0, 0)
    _smooth(rim)
    sub = rim.modifiers.new("SubSurf", "SUBSURF")
    sub.levels = 1; sub.render_levels = 2
    _assign(rim, _mat("rim_alloy", (0.82, 0.85, 0.90),
                      metallic=0.96, roughness=0.08, aniso=0.72, aniso_rot=0.0))
    parts.append(rim)

    # ── BRAKE DISC ──
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=48, radius=R * 0.46, depth=0.018,
        location=(x, y, R), rotation=(math.radians(90), 0, 0))
    disc = bpy.context.active_object; disc.name = f"disc_{x:.2f}"
    _smooth(disc)
    _assign(disc, _mat("brake_disc", (0.26, 0.26, 0.27), metallic=0.75, roughness=0.52))
    parts.append(disc)

    # ── BRAKE CALIPER (red, offset to one side) ──
    bpy.ops.mesh.primitive_cube_add(size=1,
        location=(x, y + sx * (R * 0.30), R * 0.68))
    cal = bpy.context.active_object; cal.name = f"caliper_{x:.2f}"
    cal.scale = (0.20, 0.095, 0.125)
    bpy.ops.object.transform_apply(scale=True)
    _assign(cal, _mat("caliper_red", (0.78, 0.02, 0.02), roughness=0.3))
    parts.append(cal)

    return parts


# ─────────────────── HEADLIGHTS ─────────────────────────────
def build_headlights():
    lens_mat = _mat("hl_lens",  (0.92, 0.92, 0.90), roughness=0.0,
                    transmission=0.88, ior=1.52, alpha=0.12)
    drl_mat  = _mat("hl_drl",   (1.0, 0.97, 0.88),
                    emission=(1.0, 0.97, 0.88), emit_str=8.0)
    for sy in (0.76, -0.76):
        # Main lens
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.92, sy, 0.68))
        hl = bpy.context.active_object; hl.name = f"hl_{sy:.2f}"
        hl.scale = (0.058, 0.16, 0.058)
        bpy.ops.object.transform_apply(scale=True)
        _assign(hl, lens_mat)
        # LED DRL strip
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.935, sy, 0.70))
        drl = bpy.context.active_object; drl.name = f"drl_{sy:.2f}"
        drl.scale = (0.005, 0.155, 0.006)
        bpy.ops.object.transform_apply(scale=True)
        _assign(drl, drl_mat)
        # Projector bowl
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.032,
            location=(-1.91, sy, 0.67), segments=16, ring_count=12)
        proj = bpy.context.active_object; proj.name = f"proj_{sy:.2f}"
        proj.scale = (1.4, 1.0, 0.65)
        bpy.ops.object.transform_apply(scale=True)
        _assign(proj, _mat("hl_proj", (1.0, 0.96, 0.88),
                           emission=(1.0, 0.97, 0.90), emit_str=5.0))


def build_taillights():
    for sy in (0.78, -0.78):
        for mat_name, color, emit, dz in [
            ("tl_brake", (0.88,0.01,0.01), (1.0,0.02,0.02), 0.00),
            ("tl_turn",  (0.88,0.44,0.01), (1.0,0.55,0.02), -0.06),
            ("tl_rev",   (0.90,0.90,0.90), (0.98,0.98,0.98), -0.12),
        ]:
            bpy.ops.mesh.primitive_cube_add(size=1,
                location=(2.85, sy, 0.60 + dz))
            tl = bpy.context.active_object; tl.name = f"{mat_name}_{sy:.2f}"
            tl.scale = (0.020, 0.22, 0.042)
            bpy.ops.object.transform_apply(scale=True)
            _assign(tl, _mat(mat_name, color, emission=emit, emit_str=4.0, alpha=0.75))


# ─────────────────── CHROME TRIM ────────────────────────────
def build_trim():
    chrome = _mat("chrome", (0.90, 0.90, 0.92), metallic=1.0, roughness=0.035)

    # Front grille
    for dz, sz in [(0.60, 0.055), (0.52, 0.040)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.935, 0, dz))
        g = bpy.context.active_object; g.name = f"grille_{dz:.2f}"
        g.scale = (0.022, 0.75, sz)
        bpy.ops.object.transform_apply(scale=True)
        _assign(g, chrome)

    # Side window trim (half, mirrored)
    for sx, sz, lx, ly, lz in [
        (0.12, 0.008, 1.025, 0.955, 1.40),  # roof rail
        (0.06, 0.012, 1.025, 0.960, 0.88),  # belt line
    ]:
        bm = bmesh.new()
        for xi in (-0.02, 0.55, 1.05, 1.55, 2.07):
            bm.verts.new(Vector((xi, ly, lz)))
        bm.verts.ensure_lookup_table()
        for i in range(4):
            bm.edges.new([bm.verts[i], bm.verts[i+1]])
        me = bpy.data.meshes.new("trim_me"); bm.to_mesh(me); bm.free()
        rail = _new_obj("trim_rail", me)
        rail.data.materials.append(chrome)
        mir = rail.modifiers.new("Mirror", "MIRROR")
        mir.use_axis[1] = True

    # Door handles ×4
    for sy in (0.965, -0.965):
        for hx in (0.10, 1.32):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(hx, sy, 0.82))
            dh = bpy.context.active_object; dh.name = f"dh_{hx:.2f}_{sy:.2f}"
            dh.scale = (0.078, 0.008, 0.020)
            bpy.ops.object.transform_apply(scale=True)
            _assign(dh, chrome)

    # License plates
    plate = _mat("plate_white", (0.92, 0.92, 0.94), roughness=0.5)
    for px, rz in [(-1.94, 0), (2.87, math.pi)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.50))
        pl = bpy.context.active_object; pl.name = f"plate_{px:.2f}"
        pl.scale = (0.008, 0.27, 0.072)
        pl.rotation_euler.z = rz
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _assign(pl, plate)


# ─────────────────── STUDIO + WORLD ─────────────────────────
def setup_world():
    """Nishita sky — gives blue sky reflections on metallic paint."""
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree; nt.nodes.clear()

    out = nt.nodes.new("ShaderNodeOutputWorld"); out.location = (400, 0)
    bg  = nt.nodes.new("ShaderNodeBackground"); bg.location  = (200, 0)
    sky = nt.nodes.new("ShaderNodeTexSky");     sky.location = (-100, 0)

    # Nishita sky uses render direction automatically — no vector input needed
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0],        out.inputs[0])

    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation   = math.radians(140)
    try:
        sky.air_density  = 1.0
        sky.dust_density = 0.4
    except Exception:
        pass
    bg.inputs["Strength"].default_value = 0.55   # was 2.5 → washed out everything white


def setup_studio():
    """Gloss dark studio floor — reflects the car underside."""
    bpy.ops.mesh.primitive_plane_add(size=40, location=(0.55, 0, 0))
    fl = bpy.context.active_object; fl.name = "studio_floor"
    # Slightly reflective dark gray
    floor_mat = _mat("floor_dark", (0.28, 0.28, 0.30),
                     metallic=0.0, roughness=0.18)
    _assign(fl, floor_mat)


# ─────────────────── LIGHTING ───────────────────────────────
def setup_lighting():
    """Sun light matched to sky texture + soft fill."""
    # Sun (matched to Nishita sky sun direction)
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 10))
    sun = bpy.context.active_object; sun.name = "sun"
    sun.data.energy = 4.0
    sun.data.color  = (1.00, 0.96, 0.86)
    sun.data.angle  = math.radians(0.5)
    sun.rotation_euler = Euler((
        math.radians(90 - 42),
        0,
        math.radians(140)
    ), "XYZ")

    # Soft fill from opposite side
    bpy.ops.object.light_add(type="AREA", location=(6, 5, 4))
    fill = bpy.context.active_object; fill.name = "fill"
    fill.data.energy = 200; fill.data.size = 8
    fill.data.color = (0.80, 0.88, 1.0)
    fill.rotation_euler = Euler((math.radians(30), 0, math.radians(145)), "XYZ")


# ─────────────────── CAMERA ─────────────────────────────────
def setup_camera():
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = 150
    scene.render.fps  = 25

    cd = bpy.data.cameras.new("Camera")
    cd.lens = 60
    cam = bpy.data.objects.new("Camera", cd)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam

    tx, ty, tz = 0.55, 0.0, 0.80   # target
    R_orb = 8.0
    H_lo, H_hi = 1.2, 3.0

    for f in range(1, 151):
        t  = (f - 1) / 149.0
        ts = t * t * (3 - 2 * t)
        ang = math.radians(-100) + ts * math.radians(280)
        h   = H_lo + (H_hi - H_lo) * math.sin(math.pi * t)
        cx  = tx + R_orb * math.cos(ang)
        cy  = R_orb * math.sin(ang)
        cam.location = (cx, cy, h)
        d = Vector((tx - cx, ty - cy, tz - h)).normalized()
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)


# ─────────────────── RENDER (CYCLES) ────────────────────────
def setup_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "GPU"
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    try:
        scene.cycles.denoiser = "OPENIMAGEDENOISE"
    except Exception:
        try:
            scene.cycles.denoiser = "OPTIX"
        except Exception:
            pass
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = 0.005
    scene.cycles.adaptive_min_samples = 32

    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.filepath      = RENDER_PATH

    scene.render.image_settings.file_format    = "FFMPEG"
    scene.render.ffmpeg.format                 = "MPEG4"
    scene.render.ffmpeg.codec                  = "H264"
    scene.render.ffmpeg.constant_rate_factor   = "MEDIUM"

    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look           = "Low Contrast"
    scene.view_settings.exposure        = -0.3   # bring down overall brightness
    scene.view_settings.gamma           = 1.0
    scene.display_settings.display_device = "sRGB"


# ─────────────────── ASSEMBLE ───────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    enable_gpu()
    clear_scene()

    paint = mat_paint("paint_deep_blue", (0.02, 0.06, 0.50))
    glass = mat_glass("car_glass",       (0.02, 0.06, 0.04))

    # Body + glass
    build_body(paint)
    build_glass(glass)
    build_interior()

    # Wheels: front axle x=-0.95, rear x=2.05; lateral y=±0.98
    for wx, wy, flip in [
        (-0.95, -0.98, False), (-0.95,  0.98, True),
        ( 2.05, -0.98, False), ( 2.05,  0.98, True),
    ]:
        build_wheel(wx, wy, R=0.33, W=0.24, mirror_x=flip)

    build_headlights()
    build_taillights()
    build_trim()

    setup_world()
    setup_studio()
    setup_lighting()
    setup_camera()
    setup_render()

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[save] {BLEND_PATH}")

    print("[render] Cycles + OPTIX starting …")
    bpy.ops.render.render(animation=True)
    print(f"[render] Done → {RENDER_PATH}")


if __name__ == "__main__":
    main()

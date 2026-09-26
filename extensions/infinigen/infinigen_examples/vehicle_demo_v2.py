#!/usr/bin/env python3
"""
vehicle_demo_v2.py — high-quality procedural sedan with SubSurf body, clearcoat paint,
studio lighting. No road/buildings/trees — vehicle quality evaluation only.

Output: /data/.../outputs/urban_v2_1/vehicle_demo_v2.blend + vehicle_demo_v2.mp4
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

import bpy
import bmesh
import math
import os
from mathutils import Vector, Euler

OUTPUT_DIR = f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v2_1'
BLEND_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v2.blend")
RENDER_PATH = os.path.join(OUTPUT_DIR, "vehicle_demo_v2")

# ============================================================
# GPU
# ============================================================
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


# ============================================================
# SCENE UTILS
# ============================================================
def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for blk in list(bpy.data.meshes):
        bpy.data.meshes.remove(blk)
    for blk in list(bpy.data.materials):
        bpy.data.materials.remove(blk)
    for blk in list(bpy.data.cameras):
        bpy.data.cameras.remove(blk)
    for blk in list(bpy.data.lights):
        bpy.data.lights.remove(blk)


def _new_obj(name, me):
    obj = bpy.data.objects.new(name, me)
    bpy.context.collection.objects.link(obj)
    return obj


def _bm_to_obj(name, bm):
    me = bpy.data.meshes.new(name + "_me")
    bm.to_mesh(me)
    bm.free()
    return _new_obj(name, me)


def _smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True


def _assign(obj, mat, slot=0):
    while len(obj.data.materials) <= slot:
        obj.data.materials.append(None)
    obj.data.materials[slot] = mat


# ============================================================
# MATERIALS
# ============================================================
def _mat_base(name, color, metallic=0.0, roughness=0.4, alpha=1.0,
               transmission=0.0, coat=0.0, coat_rough=0.04, coat_ior=1.52,
               emission=None, emit_str=0.0, ior=1.45, aniso=0.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial"); out.location  = (400, 0)
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location = (100, 0)
    nt.links.new(bsdf.outputs[0], out.inputs[0])

    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Metallic"].default_value   = metallic
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["IOR"].default_value        = ior

    for k, v in [("Coat Weight", coat), ("Coat Roughness", coat_rough), ("Coat IOR", coat_ior)]:
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    if "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = coat

    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = transmission; break

    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        mat.blend_method = "BLEND"
        mat.use_backface_culling = False

    if emission and emit_str > 0:
        for k in ("Emission Color", "Emission"):
            if k in bsdf.inputs:
                bsdf.inputs[k].default_value = (*emission, 1.0); break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_str

    if aniso > 0 and "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = aniso

    return mat


def mat_paint(name, color):
    """Car paint: metalflake noise + clearcoat."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()

    out   = nt.nodes.new("ShaderNodeOutputMaterial"); out.location   = (500, 0)
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled"); bsdf.location  = (200, 0)
    mix   = nt.nodes.new("ShaderNodeMixRGB");         mix.location   = (-100, 100)
    noise = nt.nodes.new("ShaderNodeTexNoise");       noise.location = (-400, 100)
    coord = nt.nodes.new("ShaderNodeTexCoord");       coord.location = (-650, 100)

    nt.links.new(coord.outputs["Object"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],    mix.inputs["Fac"])
    nt.links.new(mix.outputs[0],          bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs[0],         out.inputs[0])

    noise.inputs["Scale"].default_value     = 900.0
    noise.inputs["Detail"].default_value    = 14.0
    noise.inputs["Roughness"].default_value = 0.55
    mix.blend_type = "MIX"
    mix.inputs["Fac"].default_value    = 0.07
    mix.inputs[1].default_value        = (*color, 1.0)
    mix.inputs[2].default_value        = (1.0, 1.0, 1.0, 1.0)

    bsdf.inputs["Metallic"].default_value  = 0.12
    bsdf.inputs["Roughness"].default_value = 0.038
    bsdf.inputs["IOR"].default_value       = 1.52

    for k, v in [("Coat Weight", 0.94), ("Coat Roughness", 0.016), ("Coat IOR", 1.52)]:
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = v
    if "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = 0.94

    return mat


def mat_glass(name, tint=(0.04, 0.12, 0.07)):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    bsdf.inputs["Base Color"].default_value = (*tint, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.0
    bsdf.inputs["IOR"].default_value        = 1.52
    for k in ("Transmission Weight", "Transmission"):
        if k in bsdf.inputs:
            bsdf.inputs[k].default_value = 0.95; break
    bsdf.inputs["Alpha"].default_value = 0.18
    mat.blend_method = "BLEND"
    mat.use_backface_culling = False
    return mat


# ============================================================
# SEDAN BODY — cross-section loft + Mirror + SubSurf
# ============================================================

# Station format: (x, half_width, z_top, z_belt, z_sill, z_floor)
# Sedan: ~5.0m long, 1.85m wide, 1.50m tall
# Front at negative x, rear at positive x
SEDAN_ST = [
    (-1.90,  0.22,   0.46,   0.44,   0.27,   0.12),  # 0  front tip
    (-1.70,  0.76,   0.64,   0.54,   0.27,   0.12),  # 1  front bumper face
    (-1.35,  0.88,   0.96,   0.76,   0.27,   0.12),  # 2  hood / fender start
    (-0.70,  0.90,   1.34,   0.88,   0.27,   0.12),  # 3  front wheel arch peak
    (-0.10,  0.91,   1.46,   0.90,   0.27,   0.12),  # 4  A-pillar foot / dash
    ( 0.50,  0.92,   1.49,   0.91,   0.27,   0.12),  # 5  front roof / A-pillar top
    ( 1.00,  0.92,   1.50,   0.91,   0.27,   0.12),  # 6  roof center
    ( 1.50,  0.92,   1.49,   0.91,   0.27,   0.12),  # 7  rear roof / C-pillar top
    ( 2.05,  0.91,   1.34,   0.88,   0.27,   0.12),  # 8  rear wheel arch / C-pillar
    ( 2.55,  0.88,   0.90,   0.83,   0.27,   0.12),  # 9  trunk lid
    ( 2.90,  0.75,   0.63,   0.57,   0.27,   0.12),  # 10 rear bumper face
    ( 3.10,  0.26,   0.44,   0.42,   0.27,   0.12),  # 11 tail tip
]

N_PROF = 9   # vertices per half-profile (Y>=0 side)


def _profile(x, w, z_top, z_belt, z_sill, z_floor):
    """Return 9 Vector positions for one cross-section half (positive Y side)."""
    z_door_mid = (z_belt + z_sill) * 0.5 + 0.06
    return [
        Vector((x, 0.0,         z_top)),              # 0 roof/hood/trunk center
        Vector((x, w * 0.70,    z_top)),              # 1 roof inner
        Vector((x, w * 0.94,    z_top - 0.025)),      # 2 roof edge / glass top
        Vector((x, w * 1.005,   z_belt + 0.20)),      # 3 upper body / belt shoulder
        Vector((x, w * 1.055,   z_door_mid)),         # 4 door panel max width
        Vector((x, w * 1.035,   z_sill + 0.055)),     # 5 sill top
        Vector((x, w * 0.980,   z_sill)),             # 6 sill bottom
        Vector((x, w * 0.700,   z_floor)),            # 7 underbody edge
        Vector((x, 0.0,         z_floor)),            # 8 underbody center
    ]


def build_body(paint_mat):
    bm = bmesh.new()
    N = len(SEDAN_ST)

    # Build vertex grid [station][profile_idx]
    grid = []
    for st in SEDAN_ST:
        row = [bm.verts.new(v) for v in _profile(*st)]
        grid.append(row)
    bm.verts.ensure_lookup_table()

    # Quad faces: CCW from outside (+Y) → outward normals.
    # Winding: front-top → front-bottom → rear-bottom → rear-top
    for i in range(N - 1):
        for j in range(N_PROF - 1):
            try:
                bm.faces.new([grid[i][j], grid[i][j+1], grid[i+1][j+1], grid[i+1][j]])
            except ValueError:
                pass
    obj = _bm_to_obj("sedan_body", bm)
    _smooth(obj)

    # Mirror on Y (creates left side)
    mir = obj.modifiers.new("Mirror", "MIRROR")
    mir.use_axis[0] = False
    mir.use_axis[1] = True
    mir.use_axis[2] = False
    mir.use_bisect_axis[1] = True
    mir.merge_threshold = 0.0005

    # Subdivision surface — smooth the boxy cage
    sub = obj.modifiers.new("SubSurf", "SUBSURF")
    sub.subdivision_type = "CATMULL_CLARK"
    sub.levels = 2
    sub.render_levels = 4

    _assign(obj, paint_mat)
    return obj


# ============================================================
# GLASS PANELS (windshield, rear window, side windows)
# ============================================================
def build_glass_panels(glass_mat):
    objs = []

    def _glass_half(name, pts):
        """pts: list of 4 Vector → single quad half, then mirrored."""
        bm = bmesh.new()
        vs = [bm.verts.new(p) for p in pts]
        bm.faces.new(vs)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        o = _bm_to_obj(name, bm)
        mir = o.modifiers.new("Mirror", "MIRROR")
        mir.use_axis[1] = True
        mir.merge_threshold = 0.0005
        o.data.materials.append(glass_mat)
        return o

    # Windshield: from dash level (-0.10, z≈0.90) to roof front (0.50, z≈1.46)
    objs.append(_glass_half("windshield", [
        Vector((-0.10,  0.00,  0.91)),  # bottom-center
        Vector((-0.10,  0.86,  0.91)),  # bottom-outer
        Vector(( 0.50,  0.88,  1.46)),  # top-outer
        Vector(( 0.50,  0.00,  1.47)),  # top-center
    ]))

    # Rear window: C-pillar (2.05, z≈0.90) to rear roof (1.50, z≈1.46)
    objs.append(_glass_half("rear_window", [
        Vector(( 2.05,  0.87,  0.90)),
        Vector(( 2.05,  0.00,  0.90)),
        Vector(( 1.50,  0.00,  1.46)),
        Vector(( 1.50,  0.88,  1.46)),
    ]))

    # Front side window: A-pillar foot to B-pillar
    objs.append(_glass_half("front_side_window", [
        Vector((-0.10,  0.91,  0.91)),  # front-bottom
        Vector(( 1.00,  0.92,  0.91)),  # rear-bottom (B-pillar)
        Vector(( 1.00,  0.91,  1.47)),  # rear-top
        Vector((-0.05,  0.90,  1.47)),  # front-top
    ]))

    # Rear side window: B-pillar to C-pillar
    objs.append(_glass_half("rear_side_window", [
        Vector(( 1.00,  0.92,  0.91)),
        Vector(( 2.05,  0.91,  0.91)),
        Vector(( 2.05,  0.90,  1.14)),  # C-pillar slopes lower at rear
        Vector(( 1.00,  0.91,  1.47)),
    ]))

    return objs


# ============================================================
# WHEEL ASSEMBLY
# ============================================================
def build_wheel(x, y, R=0.32, W=0.22):
    """Complete wheel: tire torus + alloy rim + brake disc."""
    parts = []

    # ---- TIRE ----
    T_cross = 0.058
    bpy.ops.mesh.primitive_torus_add(
        align="WORLD",
        location=(x, y, R),
        rotation=(math.radians(90), 0, 0),  # stand it upright, axle along Y
        major_radius=R - T_cross,
        minor_radius=T_cross,
        major_segments=64,
        minor_segments=20,
    )
    tire = bpy.context.active_object
    tire.name = f"tire_{x:.2f}_{y:.2f}"
    _smooth(tire)
    _assign(tire, _mat_base("tire_rubber", (0.03, 0.03, 0.03), roughness=0.88))
    parts.append(tire)

    # ---- ALLOY RIM ----
    bm = bmesh.new()
    N_OUT = 48   # outer rim loop resolution
    N_HUB = 16   # hub loop resolution
    N_SP  = 5    # spoke count
    R_OUT = R * 0.96      # outer rim radius
    R_SP  = R * 0.50      # spoke inner radius
    R_HUB = R * 0.12      # hub cap radius
    W2    = W * 0.5       # half axle width

    def _circle(radius, n, depth):
        return [Vector((depth, radius * math.cos(2*math.pi*i/n),
                              radius * math.sin(2*math.pi*i/n))) for i in range(n)]

    # Outer rim loop (front and back)
    of = [bm.verts.new(v) for v in _circle(R_OUT, N_OUT, W2)]
    ob = [bm.verts.new(v) for v in _circle(R_OUT, N_OUT, -W2 * 0.3)]

    # Outer rim ring wall
    for i in range(N_OUT):
        ni = (i + 1) % N_OUT
        bm.faces.new([of[i], of[ni], ob[ni], ob[i]])

    # Back disk: fill ob ring
    bc = bm.verts.new(Vector((-W2 * 0.3, 0, 0)))
    for i in range(N_OUT):
        ni = (i + 1) % N_OUT
        bm.faces.new([bc, ob[i], ob[ni]])

    # Spoke face inner ring (attach spokes here)
    sf = [bm.verts.new(v) for v in _circle(R_SP, N_OUT, W2 * 0.82)]

    # 5 spoke quads (front face only, open design)
    step = N_OUT // N_SP
    for s in range(N_SP):
        a = s * step
        b = (a + int(step * 0.35)) % N_OUT
        c = (a + int(step * 0.65)) % N_OUT
        # Wide outer edge → narrow inner zone (1 vert inner each side)
        ia = (a + int(step * 0.05)) % N_OUT
        ib = (a + int(step * 0.95)) % N_OUT
        try:
            bm.faces.new([of[ia], of[b], sf[b], sf[ia]])
        except Exception:
            pass
        try:
            bm.faces.new([of[c], of[ib], sf[ib], sf[c]])
        except Exception:
            pass

    # Center hub (front disk)
    hf = [bm.verts.new(v) for v in _circle(R_HUB, N_HUB, W2 * 0.88)]
    hb = [bm.verts.new(v) for v in _circle(R_HUB, N_HUB, -W2 * 0.3)]
    hcf = bm.verts.new(Vector((W2 * 0.88, 0, 0)))
    hcb = bm.verts.new(Vector((-W2 * 0.3, 0, 0)))
    for i in range(N_HUB):
        ni = (i + 1) % N_HUB
        bm.faces.new([hcf, hf[i], hf[ni]])
        bm.faces.new([hcb, hb[ni], hb[i]])
        bm.faces.new([hf[i], hf[ni], hb[ni], hb[i]])

    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    rim = _bm_to_obj(f"rim_{x:.2f}_{y:.2f}", bm)
    rim.location = (x, y, R)
    rim.rotation_euler = (math.radians(90), 0, 0)
    _smooth(rim)
    _assign(rim, _mat_base("rim_alloy", (0.84, 0.86, 0.90),
                            metallic=0.94, roughness=0.10, aniso=0.65))
    parts.append(rim)

    # ---- BRAKE DISC ----
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=40,
        radius=R * 0.48,
        depth=0.014,
        location=(x, y, R),
        rotation=(math.radians(90), 0, 0),
    )
    disc = bpy.context.active_object
    disc.name = f"disc_{x:.2f}_{y:.2f}"
    _smooth(disc)
    _assign(disc, _mat_base("brake_disc", (0.28, 0.28, 0.28), metallic=0.72, roughness=0.58))
    parts.append(disc)

    return parts


# ============================================================
# HEAD / TAIL LIGHTS
# ============================================================
def build_headlights():
    objs = []
    lens_mat = _mat_base("headlight_lens", (0.95, 0.95, 0.92),
                          roughness=0.0, transmission=0.9, ior=1.52,
                          alpha=0.12)
    drl_mat  = _mat_base("drl_led", (1.0, 0.96, 0.86),
                          emission=(1.0, 0.97, 0.88), emit_str=6.0)
    proj_mat = _mat_base("hl_projector", (0.92, 0.92, 0.88),
                          emission=(0.95, 0.95, 0.90), emit_str=4.0)

    for sy in (0.72, -0.72):
        # Lens housing
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.895, sy, 0.73))
        hl = bpy.context.active_object; hl.name = f"hl_lens_{sy:.2f}"
        hl.scale = (0.055, 0.15, 0.055)
        bpy.ops.object.transform_apply(scale=True)
        _assign(hl, lens_mat)

        # DRL strip (thin emissive bar)
        bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.91, sy, 0.755))
        drl = bpy.context.active_object; drl.name = f"hl_drl_{sy:.2f}"
        drl.scale = (0.005, 0.14, 0.006)
        bpy.ops.object.transform_apply(scale=True)
        _assign(drl, drl_mat)

        # Projector ellipsoid
        bpy.ops.mesh.primitive_uv_sphere_add(radius=0.025, location=(-1.88, sy, 0.72))
        proj = bpy.context.active_object; proj.name = f"hl_proj_{sy:.2f}"
        proj.scale = (1.6, 1.0, 0.7)
        bpy.ops.object.transform_apply(scale=True)
        _assign(proj, proj_mat)

        objs.extend([hl, drl, proj])
    return objs


def build_taillights():
    objs = []
    brake_mat = _mat_base("tail_brake",  (0.88, 0.02, 0.02),
                           emission=(1.0, 0.02, 0.02), emit_str=3.5, alpha=0.7)
    turn_mat  = _mat_base("tail_turn",   (0.90, 0.45, 0.02),
                           emission=(1.0, 0.55, 0.02), emit_str=2.5, alpha=0.7)
    rev_mat   = _mat_base("tail_rev",    (0.92, 0.92, 0.92),
                           emission=(0.98, 0.98, 0.98), emit_str=2.0, alpha=0.7)

    for sy in (0.75, -0.75):
        for (mat, dz) in [(brake_mat, 0.0), (turn_mat, -0.055), (rev_mat, -0.110)]:
            bpy.ops.mesh.primitive_cube_add(size=1, location=(2.92, sy, 0.62 + dz))
            tl = bpy.context.active_object; tl.name = f"tl_{mat.name}_{sy:.2f}"
            tl.scale = (0.018, 0.20, 0.038)
            bpy.ops.object.transform_apply(scale=True)
            _assign(tl, mat)
            objs.append(tl)
    return objs


# ============================================================
# CHROME TRIM (window surround, door handles, grille)
# ============================================================
def build_trim():
    chrome = _mat_base("chrome", (0.92, 0.92, 0.92), metallic=1.0, roughness=0.04)
    objs   = []

    # Front grille bar
    bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.915, 0, 0.625))
    g = bpy.context.active_object; g.name = "grille_bar"
    g.scale = (0.025, 0.72, 0.065)
    bpy.ops.object.transform_apply(scale=True)
    _assign(g, chrome); objs.append(g)

    # Roof drip rail (half, mirrored)
    bm = bmesh.new()
    rail_pts = [(x, 0.935, 1.50) for x in (-0.10, 0.50, 1.00, 1.50, 2.05)]
    rv = [bm.verts.new(Vector(p)) for p in rail_pts]
    for i in range(len(rv)-1):
        bm.edges.new([rv[i], rv[i+1]])
    me = bpy.data.meshes.new("drip_rail_me")
    bm.to_mesh(me); bm.free()
    rail = _new_obj("drip_rail", me)
    rail.data.materials.append(chrome)
    mir = rail.modifiers.new("Mirror", "MIRROR")
    mir.use_axis[1] = True
    objs.append(rail)

    # Door handles ×2 sides ×2 doors
    for sy in (0.955, -0.955):
        for hx in (-0.18, 1.20):
            bpy.ops.mesh.primitive_cube_add(size=1, location=(hx, sy, 0.82))
            dh = bpy.context.active_object; dh.name = f"door_handle_{hx:.2f}_{sy:.2f}"
            dh.scale = (0.075, 0.008, 0.018)
            bpy.ops.object.transform_apply(scale=True)
            _assign(dh, chrome); objs.append(dh)

    return objs


# ============================================================
# LICENSE PLATES
# ============================================================
def build_plates():
    plate_mat = _mat_base("plate_white", (0.95, 0.95, 0.96), roughness=0.5)
    objs = []
    for (px, ry) in [(-1.92, 0), (3.07, math.pi)]:
        bpy.ops.mesh.primitive_cube_add(size=1, location=(px, 0, 0.52))
        pl = bpy.context.active_object; pl.name = f"plate_{px:.2f}"
        pl.scale = (0.008, 0.26, 0.068)
        pl.rotation_euler.z = ry
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        _assign(pl, plate_mat); objs.append(pl)
    return objs


# ============================================================
# STUDIO FLOOR + WORLD
# ============================================================
def setup_studio():
    # Neutral gray studio floor
    bpy.ops.mesh.primitive_plane_add(size=30, location=(0.6, 0, 0))
    fl = bpy.context.active_object; fl.name = "studio_floor"
    fl_mat = _mat_base("floor_gray", (0.50, 0.50, 0.52), roughness=0.65)
    _assign(fl, fl_mat)

    # World background
    world = bpy.context.scene.world
    if not world:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg  = nt.nodes.new("ShaderNodeBackground")
    nt.links.new(bg.outputs[0], out.inputs[0])
    bg.inputs["Color"].default_value    = (0.35, 0.35, 0.38, 1.0)
    bg.inputs["Strength"].default_value = 2.5


# ============================================================
# LIGHTING
# ============================================================
def setup_lighting():
    def area(name, loc, rot_deg, energy, size, color=(1,1,1)):
        bpy.ops.object.light_add(type="AREA", location=loc)
        l = bpy.context.active_object; l.name = name
        l.data.energy = energy
        l.data.size   = size
        l.data.color  = color
        l.rotation_euler = Euler(tuple(math.radians(r) for r in rot_deg), "XYZ")
        return l

    # Key — warm sun
    area("key_light",  (-5.0, -6.0, 7.0), ( 38, 0, -38), 1800, 5.0, (1.00, 0.96, 0.88))
    # Fill — cool sky bounce
    area("fill_light", ( 7.0,  5.0, 5.0), ( 22, 0, 142), 700,  8.0, (0.80, 0.88, 1.00))
    # Rim  — warm highlight from rear
    area("rim_light",  ( 5.0, -2.0, 6.5), (-15, 0, 158), 500,  4.0, (1.00, 0.94, 0.82))
    # Ground bounce — soft fill under car
    area("bounce",     ( 0.6,  0.0,-0.5), (-90, 0,   0), 200,  6.0, (0.85, 0.85, 0.90))


# ============================================================
# CAMERA ORBIT
# ============================================================
def setup_camera():
    scene = bpy.context.scene
    scene.frame_start = 1
    scene.frame_end   = 150
    scene.render.fps  = 25

    cam_d = bpy.data.cameras.new("Camera")
    cam_d.lens = 55
    cam = bpy.data.objects.new("Camera", cam_d)
    bpy.context.collection.objects.link(cam)
    scene.camera = cam

    tx, tz = 0.6, 0.75      # target point
    R_orb  = 8.5
    H_lo, H_hi = 1.4, 3.2

    for f in range(1, 151):
        t  = (f - 1) / 149.0
        ts = t * t * (3 - 2 * t)   # smooth-step
        ang = math.radians(-100) + ts * math.radians(280)
        h   = H_lo + (H_hi - H_lo) * math.sin(math.pi * t)
        cx  = tx + R_orb * math.cos(ang)
        cy  = R_orb * math.sin(ang)
        cam.location = (cx, cy, h)

        direction = Vector((tx - cx, 0 - cy, tz - h)).normalized()
        cam.rotation_euler = direction.to_track_quat('-Z', 'Y').to_euler()
        cam.keyframe_insert("location", frame=f)
        cam.keyframe_insert("rotation_euler", frame=f)


# ============================================================
# RENDER
# ============================================================
def setup_render():
    scene = bpy.context.scene
    scene.render.engine             = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples  = 128
    scene.eevee.use_gtao             = True
    scene.eevee.gtao_distance        = 0.4
    try:
        scene.eevee.use_bloom            = True
        scene.eevee.bloom_threshold      = 0.85
        scene.eevee.bloom_intensity      = 0.25
    except Exception:
        pass
    try:
        scene.eevee.use_ssr              = True
        scene.eevee.ssr_quality          = 0.5
    except Exception:
        pass

    scene.render.resolution_x       = 1920
    scene.render.resolution_y       = 1080
    scene.render.filepath           = RENDER_PATH
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format      = "MPEG4"
    scene.render.ffmpeg.codec       = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"

    scene.view_settings.view_transform = "Filmic"
    scene.view_settings.look           = "Medium High Contrast"
    scene.view_settings.exposure        = 0.35
    scene.view_settings.gamma           = 1.0

    scene.display_settings.display_device = "sRGB"


# ============================================================
# ASSEMBLE
# ============================================================
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    enable_gpu()
    clear_scene()

    # Materials
    paint   = mat_paint("paint_candy_red", (0.82, 0.04, 0.02))
    glass   = mat_glass("car_glass")

    # Body
    build_body(paint)

    # Glass panels
    build_glass_panels(glass)

    # Wheels  (front axle x=-0.70, rear axle x=2.05; lateral y=±0.97)
    for wx, wy, rear in [
        (-0.70, -0.97, False),
        (-0.70,  0.97, False),
        ( 2.05, -0.97, True),
        ( 2.05,  0.97, True),
    ]:
        build_wheel(wx, wy, R=0.32, W=0.22)

    # Lights & trim
    build_headlights()
    build_taillights()
    build_trim()
    build_plates()

    # Scene
    setup_studio()
    setup_lighting()
    setup_camera()
    setup_render()

    bpy.ops.wm.save_as_mainfile(filepath=BLEND_PATH)
    print(f"[save] {BLEND_PATH}")

    print("[render] Starting...")
    bpy.ops.render.render(animation=True)
    print(f"[render] Done → {RENDER_PATH}.mp4")


if __name__ == "__main__":
    main()

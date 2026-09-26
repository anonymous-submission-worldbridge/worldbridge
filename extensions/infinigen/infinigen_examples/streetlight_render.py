#!/usr/bin/env python3
"""
streetlight_render.py — photo-realistic procedural street light effect.

Builds a Chinese single-arm LED municipal street light from scratch using pure
bpy mesh/curve primitives + PBR Cycles materials.  No Infinigen gin required.

Components:
  ┌ concrete base (octagonal, 0.5 m, tapered)
  │ access door panel (junction box)
  ├ galvanized steel pole  (tapered Ø 165→76 mm, 9 m)
  ├ curved bracket arm     (swept tube Ø 50 mm, 1.6 m reach)
  │ arm clamp collar
  ├ LED road-light head    (650 × 220 × 105 mm aluminium die-cast)
  │   ├ housing body
  │   ├ top visor
  │   ├ flat polycarbonate lens
  │   ├ LED array back-plane (emission, 4000 K)
  │   └ mounting yoke
  └ IES-like area light (emission, 5000 lm equivalent)

Renders:
  streetlight_day.png       — full pole, low sun, daytime PBR
  streetlight_closeup.png   — lamp head close-up, 105 mm lens
  streetlight_night.png     — dusk/night, lamp on, ground illumination
  streetlight_orbit.mp4     — 150-frame orbit around lamp cluster

GPU: OPTIX → CUDA → HIP → METAL
Output: outputs/urban_v3_streetlight/
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
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths['WORLDBRIDGE_SITE_PACKAGES']


import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CONDA = Path(f'{_wb_WORLDBRIDGE_SITE_PACKAGES}')
if CONDA.exists():
    sys.path.insert(0, str(CONDA))

import bpy
import numpy as np
from mathutils import Vector, Matrix, Euler

# ── GPU ────────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
try:
    from infinigen.core.init import configure_cycles_devices
    configure_cycles_devices()
except Exception:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
print(f"[GPU] device = {bpy.context.scene.cycles.device}")

OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_streetlight')
OUT.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# Geometry utilities
# ══════════════════════════════════════════════════════════════════════════════

def _link(obj):
    if obj.name not in bpy.context.collection.objects:
        bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj

def _smooth(obj):
    for p in obj.data.polygons:
        p.use_smooth = True
    obj.data.update()
    return obj

def _apply_scale(obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(scale=True)
    return obj

def select_only(obj):
    bpy.ops.object.select_all(action="DESELECT")
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def _perp_frame(t):
    """Return (right, up) vectors perpendicular to tangent t."""
    t = Vector(t).normalized()
    ref = Vector((0, 0, 1)) if abs(t.z) < 0.9 else Vector((0, 1, 0))
    right = t.cross(ref).normalized()
    up = t.cross(right).normalized()
    return right, up

def make_swept_tube(path_pts, radius, n_sides=20, name="Tube", cap=True):
    """Sweep a circle of `radius` along `path_pts`, producing a smooth tube mesh."""
    verts, faces = [], []
    rings = []
    for i, pt in enumerate(path_pts):
        if i < len(path_pts) - 1:
            tang = Vector(path_pts[i+1]) - Vector(pt)
        else:
            tang = Vector(pt) - Vector(path_pts[i-1])
        right, up = _perp_frame(tang)
        start = len(verts)
        rings.append(start)
        for j in range(n_sides):
            a = j / n_sides * math.tau
            verts.append(tuple(Vector(pt) + right * (radius * math.cos(a))
                                           + up    * (radius * math.sin(a))))
    for k in range(len(rings) - 1):
        s0, s1 = rings[k], rings[k+1]
        for j in range(n_sides):
            jn = (j+1) % n_sides
            faces.append((s0+j, s0+jn, s1+jn, s1+j))
    if cap:
        # start cap
        faces.append(tuple(rings[0] + j for j in range(n_sides)))
        # end cap
        faces.append(tuple(reversed([rings[-1] + j for j in range(n_sides)])))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    _smooth(obj)
    return obj

def cubic_bezier_pts(p0, p1, p2, p3, n=32):
    """Evaluate n points along a cubic Bezier curve."""
    p0,p1,p2,p3 = np.array(p0), np.array(p1), np.array(p2), np.array(p3)
    ts = np.linspace(0, 1, n)
    pts = []
    for t in ts:
        mt = 1 - t
        pts.append(mt**3*p0 + 3*mt**2*t*p1 + 3*mt*t**2*p2 + t**3*p3)
    return [tuple(p) for p in pts]

def make_tapered_cylinder(name, r_bot, r_top, height, n_sides=32, smooth=True):
    """Tapered cylinder (frustum) as a mesh."""
    verts, faces = [], []
    for j in range(n_sides):
        a = j / n_sides * math.tau
        verts.append((r_bot*math.cos(a), r_bot*math.sin(a), 0.0))
    for j in range(n_sides):
        a = j / n_sides * math.tau
        verts.append((r_top*math.cos(a), r_top*math.sin(a), height))
    # side quads
    for j in range(n_sides):
        jn = (j+1) % n_sides
        faces.append((j, jn, n_sides+jn, n_sides+j))
    # caps
    faces.append(tuple(range(n_sides)))
    faces.append(tuple(reversed(range(n_sides, 2*n_sides))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    if smooth:
        _smooth(obj)
    return obj

def make_box(name, lx, ly, lz, cx=0, cy=0, cz=0):
    """Rectangular box centred at (cx,cy,cz)."""
    x1,x2 = cx-lx/2, cx+lx/2
    y1,y2 = cy-ly/2, cy+ly/2
    z1,z2 = cz-lz/2, cz+lz/2
    verts = [(x1,y1,z1),(x2,y1,z1),(x2,y2,z1),(x1,y2,z1),
             (x1,y1,z2),(x2,y1,z2),(x2,y2,z2),(x1,y2,z2)]
    faces = [(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    return obj

def make_octagon_prism(name, outer_r, height, bevel_top=0.04):
    """Octagonal prism for the base."""
    n = 8
    verts, faces = [], []
    for j in range(n):
        a = j/n*math.tau + math.pi/n
        verts.append((outer_r*math.cos(a), outer_r*math.sin(a), 0.0))
    # bevelled top
    br = outer_r - bevel_top
    for j in range(n):
        a = j/n*math.tau + math.pi/n
        verts.append((br*math.cos(a), br*math.sin(a), height - bevel_top))
    for j in range(n):
        a = j/n*math.tau + math.pi/n
        verts.append((br*math.cos(a), br*math.sin(a), height))
    # side quads (bottom to mid)
    for j in range(n):
        jn = (j+1)%n
        faces.append((j, jn, n+jn, n+j))
    # side quads (mid to top — chamfered)
    for j in range(n):
        jn = (j+1)%n
        faces.append((n+j, n+jn, 2*n+jn, 2*n+j))
    # bottom cap
    faces.append(tuple(range(n)))
    # top cap
    faces.append(tuple(reversed(range(2*n, 3*n))))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    _smooth(obj)
    return obj

# ══════════════════════════════════════════════════════════════════════════════
# PBR Materials
# ══════════════════════════════════════════════════════════════════════════════

def _clear_nodes(mat):
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat.node_tree

def _link_nodes(nt, a, b):
    nt.links.new(a, b)

def mat_galv_steel(name="GalvSteel"):
    """Galvanized steel — bright silver with subtle mottled surface."""
    mat = bpy.data.materials.new(name)
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    mp   = nt.nodes.new("ShaderNodeMapping")

    # Galvanized: bright silver-white, faint blue tint
    bsdf.inputs["Base Color"].default_value    = (0.82, 0.85, 0.87, 1.0)
    bsdf.inputs["Metallic"].default_value      = 0.95
    bsdf.inputs["Roughness"].default_value     = 0.18
    if "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value       = 0.25
        bsdf.inputs["Anisotropic Rotation"].default_value = 0.0
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.85

    # Noise for subtle roughness variation (galvanized speckle)
    noise.inputs["Scale"].default_value  = 80.0
    noise.inputs["Detail"].default_value = 4.0
    noise.inputs["Roughness"].default_value = 0.65
    ramp.color_ramp.elements[0].position = 0.4
    ramp.color_ramp.elements[0].color    = (0.12, 0.0, 0.0, 1.0)  # dark → less rough
    ramp.color_ramp.elements[1].position = 0.7
    ramp.color_ramp.elements[1].color    = (0.28, 0.0, 0.0, 1.0)  # bright → more rough

    mp.inputs["Scale"].default_value = (5.0, 5.0, 1.0)
    _link_nodes(nt, coord.outputs["UV"], mp.inputs["Vector"])
    _link_nodes(nt, mp.outputs["Vector"], noise.inputs["Vector"])
    _link_nodes(nt, noise.outputs["Fac"], ramp.inputs["Fac"])
    _link_nodes(nt, ramp.outputs["Color"], bsdf.inputs["Roughness"])
    _link_nodes(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_dark_aluminum(name="DarkAluminum"):
    """Powder-coated dark grey aluminium — lamp housing."""
    mat = bpy.data.materials.new(name)
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")

    bsdf.inputs["Base Color"].default_value = (0.072, 0.075, 0.078, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0   # powder coat = non-metallic top layer
    bsdf.inputs["Roughness"].default_value  = 0.72

    noise.inputs["Scale"].default_value   = 120.0
    noise.inputs["Detail"].default_value  = 8.0
    noise.inputs["Roughness"].default_value = 0.5
    bump.inputs["Strength"].default_value = 0.06
    bump.inputs["Distance"].default_value = 0.003

    _link_nodes(nt, coord.outputs["UV"], noise.inputs["Vector"])
    _link_nodes(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _link_nodes(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _link_nodes(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_polycarbonate_lens(name="PCLens"):
    """Clear polycarbonate — transparent with slight frost/diffuse."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.blend_method = "BLEND"
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")

    bsdf.inputs["Base Color"].default_value        = (0.88, 0.93, 0.97, 1.0)
    bsdf.inputs["Roughness"].default_value         = 0.08
    bsdf.inputs["IOR"].default_value               = 1.58
    if "Transmission Weight" in bsdf.inputs:
        bsdf.inputs["Transmission Weight"].default_value = 0.90
    elif "Transmission" in bsdf.inputs:
        bsdf.inputs["Transmission"].default_value = 0.90
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 0.85

    _link_nodes(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_led_emitter(name="LEDEmit", kelvin=4200, strength=12.0):
    """Warm-white LED array emitter."""
    # 4200 K ≈ cool-white / neutral white LED, typical Chinese street light
    # Convert blackbody-ish: 4200K → slightly warm white
    r, g, b = 1.0, 0.945, 0.82
    mat = bpy.data.materials.new(name)
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    mix  = nt.nodes.new("ShaderNodeMixShader")
    emit = nt.nodes.new("ShaderNodeEmission")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")

    emit.inputs["Color"].default_value    = (r, g, b, 1.0)
    emit.inputs["Strength"].default_value = strength
    bsdf.inputs["Base Color"].default_value = (0.9, 0.88, 0.80, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.5
    mix.inputs["Fac"].default_value = 0.85   # 85% emission, 15% diffuse

    _link_nodes(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _link_nodes(nt, emit.outputs["Emission"], mix.inputs[2])
    _link_nodes(nt, mix.outputs["Shader"], out.inputs["Surface"])
    return mat

def mat_led_housing_inner(name="LEDHouseInner"):
    """Inner white reflector of LED housing."""
    mat = bpy.data.materials.new(name)
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.92, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.6
    bsdf.inputs["Roughness"].default_value  = 0.25
    _link_nodes(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_concrete(name="Concrete"):
    """Concrete base material."""
    mat = bpy.data.materials.new(name)
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")

    noise.inputs["Scale"].default_value    = 12.0
    noise.inputs["Detail"].default_value   = 8.0
    noise.inputs["Roughness"].default_value = 0.65
    ramp.color_ramp.elements[0].color = (0.38, 0.36, 0.33, 1.0)
    ramp.color_ramp.elements[1].color = (0.58, 0.56, 0.52, 1.0)
    bump.inputs["Strength"].default_value = 0.35
    bump.inputs["Distance"].default_value = 0.008
    bsdf.inputs["Roughness"].default_value = 0.95

    _link_nodes(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _link_nodes(nt, noise.outputs["Fac"], ramp.inputs["Fac"])
    _link_nodes(nt, ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _link_nodes(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _link_nodes(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _link_nodes(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_asphalt(name="Asphalt"):
    mat = bpy.data.materials.new(name)
    nt = _clear_nodes(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value   = 5.0
    noise.inputs["Detail"].default_value  = 10.0
    ramp.color_ramp.elements[0].color = (0.024, 0.024, 0.026, 1.0)
    ramp.color_ramp.elements[1].color = (0.046, 0.046, 0.050, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.92
    _link_nodes(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _link_nodes(nt, noise.outputs["Fac"], ramp.inputs["Fac"])
    _link_nodes(nt, ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _link_nodes(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

# ══════════════════════════════════════════════════════════════════════════════
# Street light geometry
# ══════════════════════════════════════════════════════════════════════════════

# Dimensions (SI units, metres)
POLE_H       = 9.0      # above-ground height
POLE_R_BOT   = 0.0825   # 165 mm diameter
POLE_R_TOP   = 0.038    # 76 mm diameter
BASE_R       = 0.255    # octagonal base outer radius (≈ 510 mm across flats)
BASE_H       = 0.38     # base height
ARM_REACH    = 1.55     # horizontal arm reach (m)
ARM_RISE     = 0.38     # vertical rise from pole top to lamp centre
ARM_R        = 0.025    # arm tube outer radius (50 mm OD)
HEAD_L       = 0.660    # lamp head length (along road / x-axis)
HEAD_W       = 0.225    # lamp head width
HEAD_H       = 0.105    # lamp head body height
LENS_INSET   = 0.010    # lens sits 10 mm inside bottom of housing


def build_base(concrete_mat, steel_mat):
    """Octagonal concrete base + steel base ring."""
    base = make_octagon_prism("SL_Base", BASE_R, BASE_H)
    base.data.materials.append(concrete_mat)
    base.location = (0, 0, 0)

    # Small steel flange ring at top of base
    ring = make_tapered_cylinder("SL_BaseRing", 0.095, 0.092, 0.05, n_sides=32)
    ring.data.materials.append(steel_mat)
    ring.location = (0, 0, BASE_H)

    # Small inset panel for hand hole located at 1.4 meters from the pole face.
    panel = make_box("SL_HandHole", 0.13, 0.008, 0.18, cx=0, cy=POLE_R_BOT*0.98, cz=BASE_H+1.4)
    panel.data.materials.append(steel_mat)

    return base, ring, panel


def build_pole(steel_mat):
    """Tapered galvanized steel pole, smooth shading."""
    pole = make_tapered_cylinder(
        "SL_Pole", POLE_R_BOT, POLE_R_TOP, POLE_H, n_sides=32
    )
    pole.data.materials.append(steel_mat)
    pole.location = (0, 0, BASE_H)
    return pole


def build_arm(steel_mat):
    """
    Curved bracket arm: swept tube along a cubic Bezier path.
    Starts at pole top centre, curves up+outward, ends at lamp attachment.
    """
    z0 = BASE_H + POLE_H          # pole top
    z1 = z0 + ARM_RISE            # lamp Z centre

    # Bezier control points (x=0 plane, y=outward, z=up)
    p0 = (0.0,  0.0,         z0)
    p1 = (0.0,  0.05,        z0 + ARM_RISE*0.55)   # first handle: arc up
    p2 = (0.0,  ARM_REACH*0.65, z1 + 0.04)         # second handle: level out
    p3 = (0.0,  ARM_REACH,   z1)                    # lamp end

    path = cubic_bezier_pts(p0, p1, p2, p3, n=48)
    arm = make_swept_tube(path, ARM_R, n_sides=20, name="SL_Arm")
    arm.data.materials.append(steel_mat)

    # Arm clamp collar where arm meets pole
    collar = make_tapered_cylinder("SL_ArmClamp", 0.052, 0.050, 0.06, n_sides=24)
    collar.data.materials.append(steel_mat)
    collar.location = (0, 0, z0 - 0.03)

    return arm, collar


def build_lamp_head(dark_al_mat, pc_mat, led_mat, inner_mat, steel_mat):
    """
    LED road-light head consisting of:
      - main body (dark aluminium box with rounded top)
      - polycarbonate lens (flat, bottom face)
      - LED back-plane (emission surface behind lens)
      - mounting yoke (two steel brackets)
    """
    z0 = BASE_H + POLE_H + ARM_RISE
    # head centred at (0, ARM_REACH, z0), oriented with length along X (road direction)

    CX, CY, CZ = 0.0, ARM_REACH, z0

    # ── Housing body ──────────────────────────────────────────────────────────
    # Bottom of housing: CZ - HEAD_H/2
    # Top of housing: CZ + HEAD_H/2

    housing = make_box("SL_Housing",
                        HEAD_L, HEAD_W, HEAD_H,
                        cx=CX, cy=CY, cz=CZ + HEAD_H*0.05)
    housing.data.materials.append(dark_al_mat)

    # Slightly wider flange at bottom edge (light shelf)
    shelf = make_box("SL_HousingShelf",
                      HEAD_L + 0.020, HEAD_W + 0.014, 0.012,
                      cx=CX, cy=CY, cz=CZ - HEAD_H/2 - 0.004)
    shelf.data.materials.append(dark_al_mat)

    # Top visor strip (anti-glare panel) above housing
    visor = make_box("SL_Visor",
                      HEAD_L + 0.010, HEAD_W + 0.010, 0.012,
                      cx=CX, cy=CY, cz=CZ + HEAD_H/2 + 0.006)
    visor.data.materials.append(dark_al_mat)

    # ── Inner reflector cavity ────────────────────────────────────────────────
    # Slightly smaller inset — white reflector
    inner = make_box("SL_InnerReflector",
                      HEAD_L - 0.030, HEAD_W - 0.020, HEAD_H - 0.018,
                      cx=CX, cy=CY, cz=CZ + HEAD_H*0.1)
    inner.data.materials.append(inner_mat)

    # ── LED back-plane (emission) ─────────────────────────────────────────────
    # 4 LED arrays in 2 rows × 2 cols (typical road light layout)
    led_base = make_box("SL_LEDBackplane",
                         HEAD_L - 0.055, HEAD_W - 0.040, 0.005,
                         cx=CX, cy=CY, cz=CZ - HEAD_H/2 + LENS_INSET + 0.020)
    led_base.data.materials.append(led_mat)

    # ── LED module details (individual emitter squares) ────────────────────────
    # 5 × 2 grid of LED modules visible through lens
    n_cols, n_rows = 5, 2
    mod_lx = (HEAD_L - 0.08) / n_cols - 0.010
    mod_ly = (HEAD_W - 0.06) / n_rows - 0.006
    led_objs = [led_base]
    for col in range(n_cols):
        for row in range(n_rows):
            mx = CX - (HEAD_L-0.08)/2 + col*((HEAD_L-0.08)/n_cols) + mod_lx/2 + 0.004
            my = CY - (HEAD_W-0.06)/2 + row*((HEAD_W-0.06)/n_rows) + mod_ly/2 + 0.003
            mz = CZ - HEAD_H/2 + LENS_INSET + 0.023
            mod = make_box(f"SL_LEDMod_{col}_{row}",
                           mod_lx, mod_ly, 0.006,
                           cx=mx, cy=my, cz=mz)
            mod.data.materials.append(led_mat)
            led_objs.append(mod)

    # ── Polycarbonate lens (bottom cover) ─────────────────────────────────────
    lens = make_box("SL_Lens",
                     HEAD_L - 0.020, HEAD_W - 0.016, 0.008,
                     cx=CX, cy=CY, cz=CZ - HEAD_H/2 + LENS_INSET/2)
    lens.data.materials.append(pc_mat)

    # ── Mounting yoke (steel, 2 U-bracket plates) ─────────────────────────────
    for side in (-1, 1):
        yoke = make_box(f"SL_Yoke_{side}",
                         0.028, 0.200, 0.062,
                         cx=CX + side*0.18, cy=CY - 0.075, cz=CZ + 0.010)
        yoke.data.materials.append(steel_mat)

    # Yoke cross-bar
    yoke_bar = make_box("SL_YokeBar",
                          0.380, 0.028, 0.032,
                          cx=CX, cy=CY - ARM_R - 0.010, cz=CZ + 0.010)
    yoke_bar.data.materials.append(steel_mat)

    # Arm-end cap (where arm meets yoke)
    end_cap = make_tapered_cylinder("SL_ArmEnd", ARM_R+0.002, ARM_R, 0.030, n_sides=20)
    end_cap.data.materials.append(steel_mat)
    end_cap.location   = (0, ARM_REACH, z0 - 0.015)
    end_cap.rotation_euler = (math.pi/2, 0, 0)

    return housing, shelf, visor, inner, lens, led_objs, yoke_bar


def build_light_emitter():
    """Invisible area light inside lamp head that actually illuminates the scene."""
    z0 = BASE_H + POLE_H + ARM_RISE
    bpy.ops.object.light_add(type="AREA", location=(0, ARM_REACH, z0 - HEAD_H/2 - 0.05))
    light = bpy.context.active_object
    light.name = "SL_AreaLight"
    light.data.energy        = 4200      # lumens-ish (Blender W)
    light.data.color         = (1.0, 0.945, 0.82)    # 4200 K neutral-warm white
    light.data.size          = HEAD_L * 0.8
    light.data.size_y        = HEAD_W * 0.7
    light.data.spread        = math.radians(155)     # semi-diffuse downward spread
    light.rotation_euler     = (math.pi, 0, 0)       # shine downward
    light.data.shadow_soft_size = 0.5
    return light


def build_ground(asph_mat):
    """Large ground plane."""
    bpy.ops.mesh.primitive_plane_add(size=40.0, location=(0, 8, -0.01))
    g = bpy.context.active_object
    g.name = "Ground"
    g.data.materials.append(asph_mat)
    return g

# ══════════════════════════════════════════════════════════════════════════════
# Scene + lighting helpers
# ══════════════════════════════════════════════════════════════════════════════

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                bpy.data.lights, bpy.data.curves, bpy.data.collections):
        for blk in list(col):
            try: col.remove(blk)
            except: pass

def enable_denoiser():
    for d in ("OPTIX", "OPENIMAGEDENOISE"):
        try: bpy.context.scene.cycles.denoiser = d; return
        except: pass

def add_sky_world(elev=28, rot=155, strength=0.95):
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type      = "NISHITA"
    sky.sun_elevation = math.radians(elev)
    sky.sun_rotation  = math.radians(rot)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"],  bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def add_night_world():
    """Dark night sky with slight ambient."""
    world = bpy.data.worlds.new("World")
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value    = (0.004, 0.006, 0.012, 1.0)  # deep blue-black
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def add_sun(energy=4.0, elev=28, az=155):
    bpy.ops.object.light_add(type="SUN", location=(0, 0, 20))
    s = bpy.context.active_object
    s.data.energy = energy
    s.data.angle  = math.radians(0.53)
    s.rotation_euler = (math.radians(90 - elev), 0, math.radians(az))
    return s

def add_cam(loc, look_at, name="Cam", lens=50, sensor_w=36.0):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name
    cam.data.lens     = lens
    cam.data.sensor_width = sensor_w
    bpy.context.scene.camera = cam
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=look_at)
    tgt = bpy.context.active_object; tgt.name = name + "_tgt"
    tc = cam.constraints.new("TRACK_TO")
    tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
    return cam, tgt

def rm_cam(cam, tgt):
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

def setup_png(fp, samples=256, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.cycles.samples       = samples
    sc.cycles.use_denoising = True
    enable_denoiser()
    sc.render.resolution_x  = rx
    sc.render.resolution_y  = ry
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(fp)

def setup_video(fp, n=150, fps=25, samples=96, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.frame_start = 1; sc.frame_end = n; sc.render.fps = fps
    setup_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format = "FFMPEG"
    sc.render.ffmpeg.format = "MPEG4"; sc.render.ffmpeg.codec = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"

def orbit_anim(cam, cx, cy, radius, height, n=150):
    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("SLOrbit")
    for f in range(1, n+1):
        ang = (f-1)/n * math.tau
        cam.location = (cx + radius*math.cos(ang), cy + radius*math.sin(ang), height)
        cam.keyframe_insert("location", frame=f)

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def build_scene():
    """Build complete street light scene and return area light object."""
    # Materials
    steel_mat  = mat_galv_steel()
    dark_al    = mat_dark_aluminum()
    pc         = mat_polycarbonate_lens()
    led        = mat_led_emitter(strength=14.0)
    inner      = mat_led_housing_inner()
    concrete   = mat_concrete()
    asphalt    = mat_asphalt()

    # Geometry
    build_ground(asphalt)
    build_base(concrete, steel_mat)
    build_pole(steel_mat)
    build_arm(steel_mat)
    build_lamp_head(dark_al, pc, led, inner, steel_mat)
    area_light = build_light_emitter()
    return area_light


def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    try:
        configure_cycles_devices()
    except Exception:
        bpy.context.scene.cycles.device = "GPU"

    print("[SL] Building street light …")
    area_light = build_scene()

    lamp_z = BASE_H + POLE_H + ARM_RISE
    lamp_y = ARM_REACH
    pole_mid_z = BASE_H + POLE_H * 0.5

    # ── 1. Daytime full-pole view ─────────────────────────────────────────────
    print("\n[render] Day full-pole view …")
    area_light.hide_render = True   # lamp off in day render
    add_sky_world(elev=32, rot=150, strength=1.0)
    add_sun(energy=4.5, elev=32, az=150)

    cam, tgt = add_cam(
        loc=(-8.5, -8.0, pole_mid_z + 1.5),
        look_at=(0, lamp_y/2, pole_mid_z - 0.5),
        name="CamDay", lens=55
    )
    setup_png(OUT/"streetlight_day.png", samples=256)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'streetlight_day.png'}")
    rm_cam(cam, tgt)

    # ── 2. Lamp head close-up (daytime) ──────────────────────────────────────
    print("\n[render] Lamp head close-up …")
    cam, tgt = add_cam(
        loc=(-1.8, lamp_y - 1.8, lamp_z + 0.25),
        look_at=(0, lamp_y, lamp_z - 0.02),
        name="CamClose", lens=85
    )
    setup_png(OUT/"streetlight_closeup.png", samples=320, rx=1920, ry=1080)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'streetlight_closeup.png'}")
    rm_cam(cam, tgt)

    # ── 3. Night render — lamp on ─────────────────────────────────────────────
    print("\n[render] Night illumination …")
    # Remove sun, switch to night sky
    for obj in list(bpy.context.scene.objects):
        if obj.type == "LIGHT" and obj.data.type == "SUN":
            bpy.data.objects.remove(obj, do_unlink=True)
    for world in list(bpy.data.worlds):
        bpy.data.worlds.remove(world)
    add_night_world()
    area_light.hide_render = False   # lamp on
    area_light.data.energy = 4800

    # Slightly lifted camera to see ground illumination pool
    cam, tgt = add_cam(
        loc=(-10.0, -4.0, lamp_z * 0.65),
        look_at=(0, lamp_y + 2.5, 0.0),
        name="CamNight", lens=45
    )
    setup_png(OUT/"streetlight_night.png", samples=384, rx=1920, ry=1080)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'streetlight_night.png'}")
    rm_cam(cam, tgt)

    # ── 4. Orbit video — twilight ─────────────────────────────────────────────
    print("\n[render] Orbit video (twilight) …")
    for world in list(bpy.data.worlds):
        bpy.data.worlds.remove(world)
    add_sky_world(elev=5, rot=155, strength=0.55)   # golden-hour / dusk sky
    add_sun(energy=1.2, elev=5, az=155)

    area_light.data.energy = 3600
    area_light.hide_render = False

    N = 150
    orb_r = 12.0; orb_h = lamp_z * 0.72
    cam, tgt = add_cam(
        loc=(orb_r, 0, orb_h),
        look_at=(0, lamp_y * 0.5, lamp_z * 0.5),
        name="CamOrbit", lens=50
    )
    orbit_anim(cam, 0, lamp_y * 0.5, orb_r, orb_h, n=N)
    setup_video(OUT/"streetlight_orbit", n=N, samples=96)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'streetlight_orbit0001-0150.mp4'}")
    rm_cam(cam, tgt)

    # ── 5. Save .blend ─────────────────────────────────────────────────────────
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"streetlight.blend"))
    print(f"\n[blend] {OUT/'streetlight.blend'}")
    print(f"[done] {OUT}")


if __name__ == "__main__":
    main()

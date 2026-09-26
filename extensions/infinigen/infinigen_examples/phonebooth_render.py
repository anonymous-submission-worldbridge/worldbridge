#!/usr/bin/env python3
"""
phonebooth_render.py — photo-realistic procedural Chinese public phone booth (telephone booth)

Models a complete China Telecom (China Telecom) enclosed roadside phone booth from scratch:
  ┌── concrete base pad
  ├── aluminium alloy frame  (4 corner posts + horizontal rails)
  ├── tempered glass panels  (3-sided, slight green tint, fingerprint bump)
  ├── solid back panel       (powder-coated steel)
  ├── roof                   (aluminium flat panel + edge frame + overhang)
  ├── roof sign strip        (\"CHINA TELECOM\" represented as logo panels)
  ├── coin telephone unit    (handset cradle, keypad, coin slot, LCD, handset)
  ├── handset cord           (coiled, swept-tube bezier)
  └── interior LED strip     (ceiling light for night render)

PBR materials: brushed aluminium, powder-coat blue-gray, tempered glass,
               black ABS plastic, concrete, emissive LCD/signage.

GPU: OPTIX → CUDA → HIP → METAL
Output: outputs/urban_v3_phonebooth/
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
from mathutils import Vector

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

OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_phonebooth')
OUT.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# Booth dimensions (metres)
# ══════════════════════════════════════════════════════════════════════════════
BW      = 0.95   # booth width  (x)
BD      = 0.65   # booth depth  (y)
BH      = 2.10   # booth body height (z)
ROOF_H  = 0.10   # roof slab thickness
OVHG    = 0.045  # roof overhang per side
POST    = 0.048  # square post side
GLASS_T = 0.008  # glass pane thickness
PANEL_T = 0.012  # solid panel thickness
RAIL_T  = 0.028  # horizontal rail height
BASE_W  = 1.05   # concrete base width
BASE_D  = 0.75   # concrete base depth
BASE_H  = 0.055  # concrete base height
PANEL_H = 0.78   # solid panel zone from floor (below this = panel, above = glass)
MID_RAIL_Z = PANEL_H  # mid rail sits at panel/glass transition

# ══════════════════════════════════════════════════════════════════════════════
# Low-level geometry helpers
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

def _deselect():
    bpy.ops.object.select_all(action="DESELECT")

def make_box(name, lx, ly, lz, cx=0.0, cy=0.0, cz=0.0, smooth=False):
    x1, x2 = cx - lx/2, cx + lx/2
    y1, y2 = cy - ly/2, cy + ly/2
    z1, z2 = cz - lz/2, cz + lz/2
    verts = [(x1,y1,z1),(x2,y1,z1),(x2,y2,z1),(x1,y2,z1),
             (x1,y1,z2),(x2,y1,z2),(x2,y2,z2),(x1,y2,z2)]
    faces = [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    if smooth:
        _smooth(obj)
    return obj

def make_cylinder(name, radius, height, n=32, cx=0, cy=0, cz=0, smooth=True):
    verts, faces = [], []
    for j in range(n):
        a = j/n * math.tau
        verts.append((cx + radius*math.cos(a), cy + radius*math.sin(a), cz))
        verts.append((cx + radius*math.cos(a), cy + radius*math.sin(a), cz + height))
    faces.append(tuple(range(0, 2*n, 2)))   # bottom cap
    faces.append(tuple(reversed(range(1, 2*n, 2))))  # top cap
    for j in range(n):
        jn = (j+1) % n
        b, t, bn, tn = 2*j, 2*j+1, 2*jn, 2*jn+1
        faces.append((b, bn, tn, t))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    if smooth:
        _smooth(obj)
    return obj

def _perp_frame(t):
    t = Vector(t).normalized()
    ref = Vector((0,0,1)) if abs(t.z) < 0.9 else Vector((0,1,0))
    r = t.cross(ref).normalized()
    u = t.cross(r).normalized()
    return r, u

def swept_tube(pts, radius, n=12, name="Tube", cap=True):
    verts, faces, rings = [], [], []
    for i, pt in enumerate(pts):
        tang = (Vector(pts[i+1]) - Vector(pt)) if i < len(pts)-1 else (Vector(pt) - Vector(pts[i-1]))
        r, u = _perp_frame(tang)
        s = len(verts); rings.append(s)
        for j in range(n):
            a = j/n * math.tau
            verts.append(tuple(Vector(pt) + r*radius*math.cos(a) + u*radius*math.sin(a)))
    for k in range(len(rings)-1):
        s0, s1 = rings[k], rings[k+1]
        for j in range(n):
            jn = (j+1)%n
            faces.append((s0+j, s0+jn, s1+jn, s1+j))
    if cap:
        faces.append(tuple(rings[0]+j for j in range(n)))
        faces.append(tuple(reversed([rings[-1]+j for j in range(n)])))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    _smooth(obj)
    return obj

def bezier_cubic(p0, p1, p2, p3, n=24):
    p0,p1,p2,p3 = [np.array(p) for p in [p0,p1,p2,p3]]
    return [tuple((1-t)**3*p0 + 3*(1-t)**2*t*p1 + 3*(1-t)*t**2*p2 + t**3*p3)
            for t in np.linspace(0, 1, n)]

# ══════════════════════════════════════════════════════════════════════════════
# PBR Materials
# ══════════════════════════════════════════════════════════════════════════════

def _nt(mat):
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    return mat.node_tree

def _lnk(nt, a, b):
    nt.links.new(a, b)

def mat_aluminium_frame(name="AlFrame"):
    """Brushed aluminium frame — metallic, low roughness, slight anisotropy."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    mp   = nt.nodes.new("ShaderNodeMapping")

    bsdf.inputs["Base Color"].default_value = (0.70, 0.71, 0.73, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.96
    bsdf.inputs["Roughness"].default_value  = 0.20
    if "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value       = 0.45
        bsdf.inputs["Anisotropic Rotation"].default_value = 0.0
    noise.inputs["Scale"].default_value   = 100.0
    noise.inputs["Detail"].default_value  = 2.0
    noise.inputs["Roughness"].default_value = 0.55
    mp.inputs["Scale"].default_value = (8.0, 1.0, 1.0)  # directional brush
    _lnk(nt, coord.outputs["UV"], mp.inputs["Vector"])
    _lnk(nt, mp.outputs["Vector"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bsdf.inputs["Roughness"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_powder_coat_blue(name="PowderBlue"):
    """China Telecom blue powder-coated steel — solid panels, bottom section."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")

    # China Telecom blue: #0070CC → linear sRGB approx
    bsdf.inputs["Base Color"].default_value = (0.00, 0.18, 0.62, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.62
    noise.inputs["Scale"].default_value   = 80.0
    noise.inputs["Detail"].default_value  = 6.0
    noise.inputs["Roughness"].default_value = 0.5
    bump.inputs["Strength"].default_value = 0.04
    bump.inputs["Distance"].default_value = 0.002
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_powder_coat_gray(name="PowderGray"):
    """Light gray powder-coat — roof, back panel."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.55, 0.56, 0.57, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.70
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_tempered_glass(name="Glass", frost=0.0):
    """Tempered glass — slight green tint, fingerprint bump, high transmission."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out   = nt.nodes.new("ShaderNodeOutputMaterial")
    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    bump  = nt.nodes.new("ShaderNodeBump")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    coord = nt.nodes.new("ShaderNodeTexCoord")

    # Slight green tint of tempered glass
    glass.inputs["Color"].default_value     = (0.86, 0.96, 0.90, 1.0)
    glass.inputs["Roughness"].default_value = 0.02 + frost * 0.15
    glass.inputs["IOR"].default_value       = 1.52

    # Fingerprint/smudge bump
    noise.inputs["Scale"].default_value   = 40.0
    noise.inputs["Detail"].default_value  = 8.0
    noise.inputs["Roughness"].default_value = 0.8
    bump.inputs["Strength"].default_value = 0.03
    bump.inputs["Distance"].default_value = 0.001
    _lnk(nt, coord.outputs["UV"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], glass.inputs["Normal"])
    _lnk(nt, glass.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_black_plastic(name="BlackPlastic"):
    """Black ABS plastic — phone unit body."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.022, 0.022, 0.022, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.38
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = 0.55
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_button_gray(name="BtnGray"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.22, 0.22, 0.22, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.55
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_lcd_emissive(name="LCD"):
    """Glowing LCD display."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    mix  = nt.nodes.new("ShaderNodeMixShader")
    emit = nt.nodes.new("ShaderNodeEmission")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    emit.inputs["Color"].default_value    = (0.20, 0.85, 0.30, 1.0)  # green LCD
    emit.inputs["Strength"].default_value = 2.0
    bsdf.inputs["Base Color"].default_value = (0.05, 0.20, 0.05, 1.0)
    mix.inputs["Fac"].default_value = 0.75
    _lnk(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _lnk(nt, emit.outputs["Emission"], mix.inputs[2])
    _lnk(nt, mix.outputs["Shader"], out.inputs["Surface"])
    return mat

def mat_sign_blue(name="SignBlue"):
    """China Telecom logo panel — blue emission for visibility."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    mix  = nt.nodes.new("ShaderNodeMixShader")
    emit = nt.nodes.new("ShaderNodeEmission")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    emit.inputs["Color"].default_value    = (0.02, 0.28, 0.85, 1.0)
    emit.inputs["Strength"].default_value = 1.5
    bsdf.inputs["Base Color"].default_value = (0.00, 0.18, 0.62, 1.0)
    mix.inputs["Fac"].default_value = 0.4
    _lnk(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _lnk(nt, emit.outputs["Emission"], mix.inputs[2])
    _lnk(nt, mix.outputs["Shader"], out.inputs["Surface"])
    return mat

def mat_sign_white(name="SignWhite"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.92, 0.92, 0.92, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.55
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_rubber_black(name="Rubber"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.012, 0.012, 0.012, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.92
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_concrete(name="Concrete"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value    = 10.0
    noise.inputs["Detail"].default_value   = 8.0
    noise.inputs["Roughness"].default_value = 0.65
    ramp.color_ramp.elements[0].color = (0.38, 0.36, 0.34, 1.0)
    ramp.color_ramp.elements[1].color = (0.60, 0.58, 0.55, 1.0)
    bump.inputs["Strength"].default_value = 0.30
    bump.inputs["Distance"].default_value = 0.006
    bsdf.inputs["Roughness"].default_value = 0.95
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], ramp.inputs["Fac"])
    _lnk(nt, ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_interior_led(name="InteriorLED", strength=4.0):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value    = (1.0, 0.97, 0.90, 1.0)
    emit.inputs["Strength"].default_value = strength
    _lnk(nt, emit.outputs["Emission"], out.inputs["Surface"])
    return mat

def mat_sidewalk(name="Sidewalk"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value   = 4.0
    noise.inputs["Detail"].default_value  = 10.0
    ramp.color_ramp.elements[0].color = (0.45, 0.44, 0.42, 1.0)
    ramp.color_ramp.elements[1].color = (0.65, 0.63, 0.60, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.90
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], ramp.inputs["Fac"])
    _lnk(nt, ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

# ══════════════════════════════════════════════════════════════════════════════
# Booth construction
# ══════════════════════════════════════════════════════════════════════════════

def build_frame(al_mat):
    """4 corner posts + horizontal rails forming the structural frame."""
    objs = []
    # Booth goes x: [-BW/2, BW/2], y: [0, BD], z: [0, BH]
    # Front face: y=0, Back face: y=BD
    # Corner posts at x=±(BW/2-POST/2), y=POST/2 and y=BD-POST/2
    px = BW/2 - POST/2
    py_f = POST/2
    py_b = BD - POST/2

    post_positions = [
        (-px, py_f), ( px, py_f),   # front two posts
        (-px, py_b), ( px, py_b),   # back two posts
    ]
    for i, (x, y) in enumerate(post_positions):
        p = make_box(f"PB_Post_{i}", POST, POST, BH, cx=x, cy=y, cz=BH/2)
        p.data.materials.append(al_mat)
        objs.append(p)

    # Horizontal rails: top, bottom, and mid (at PANEL_H)
    rail_configs = [
        # name,   z-centre,      connects  x×y span
        ("Bot_F",  RAIL_T/2,     (-px, px, py_f)),   # front bottom
        ("Bot_B",  RAIL_T/2,     (-px, px, py_b)),
        ("Bot_L",  RAIL_T/2,     (py_f, py_b, -px)),  # will handle as y-rail
        ("Bot_R",  RAIL_T/2,     (py_f, py_b,  px)),
        ("Top_F",  BH-RAIL_T/2,  (-px, px, py_f)),
        ("Top_B",  BH-RAIL_T/2,  (-px, px, py_b)),
        ("Top_L",  BH-RAIL_T/2,  (py_f, py_b, -px)),
        ("Top_R",  BH-RAIL_T/2,  (py_f, py_b,  px)),
        ("Mid_F",  MID_RAIL_Z,   (-px, px, py_f)),
        ("Mid_B",  MID_RAIL_Z,   (-px, px, py_b)),
        ("Mid_L",  MID_RAIL_Z,   (py_f, py_b, -px)),
        ("Mid_R",  MID_RAIL_Z,   (py_f, py_b,  px)),
    ]
    for tag, zc, span in rail_configs:
        if tag.endswith("_F") or tag.endswith("_B"):
            xa, xb, yv = span
            r = make_box(f"PB_Rail_{tag}", xb-xa, POST, RAIL_T, cx=0, cy=yv, cz=zc)
        else:
            ya, yb, xv = span
            r = make_box(f"PB_Rail_{tag}", POST, yb-ya, RAIL_T, cx=xv, cy=(ya+yb)/2, cz=zc)
        r.data.materials.append(al_mat)
        objs.append(r)

    return objs


def build_glass_panels(glass_mat, al_mat):
    """Glass panes: left side full, right side full, front upper half."""
    objs = []
    gx = BW/2 - POST          # glass width (x) for side panels = depth region
    gy_glass = BH - MID_RAIL_Z - RAIL_T  # glass height zone (above mid rail)
    gy_panel = MID_RAIL_Z - RAIL_T       # panel height zone (below mid rail)

    # Left side glass (x=-BW/2, full height, both zones)
    # Upper zone (glass)
    lg_u = make_box("PB_Glass_L_U", GLASS_T, BD-POST*2, gy_glass,
                    cx=-BW/2+POST/2, cy=BD/2, cz=MID_RAIL_Z+RAIL_T/2+gy_glass/2)
    lg_u.data.materials.append(glass_mat)
    objs.append(lg_u)

    # Right side glass – upper zone
    rg_u = make_box("PB_Glass_R_U", GLASS_T, BD-POST*2, gy_glass,
                    cx=BW/2-POST/2, cy=BD/2, cz=MID_RAIL_Z+RAIL_T/2+gy_glass/2)
    rg_u.data.materials.append(glass_mat)
    objs.append(rg_u)

    # Front upper glass (between mid rail and top rail, front face y=0)
    fg_w = BW - POST*2   # full width minus posts
    fg_u = make_box("PB_Glass_F_U", fg_w, GLASS_T, gy_glass,
                    cx=0, cy=POST/2, cz=MID_RAIL_Z+RAIL_T/2+gy_glass/2)
    fg_u.data.materials.append(glass_mat)
    objs.append(fg_u)

    # Left/Right lower zones = powder-coat panels (handled below)
    return objs


def build_solid_panels(blue_mat, gray_mat):
    """Solid powder-coat panels: bottom front, both sides, full back."""
    objs = []
    gy_panel = MID_RAIL_Z - RAIL_T

    # Front lower solid panel (below mid rail)
    fp_l = make_box("PB_Panel_F_L", BW-POST*2, PANEL_T, gy_panel,
                    cx=0, cy=POST/2, cz=RAIL_T/2+gy_panel/2)
    fp_l.data.materials.append(blue_mat)
    objs.append(fp_l)

    # Left side lower panel
    lp_l = make_box("PB_Panel_L_L", PANEL_T, BD-POST*2, gy_panel,
                    cx=-BW/2+POST/2, cy=BD/2, cz=RAIL_T/2+gy_panel/2)
    lp_l.data.materials.append(blue_mat)
    objs.append(lp_l)

    # Right side lower panel
    rp_l = make_box("PB_Panel_R_L", PANEL_T, BD-POST*2, gy_panel,
                    cx=BW/2-POST/2, cy=BD/2, cz=RAIL_T/2+gy_panel/2)
    rp_l.data.materials.append(blue_mat)
    objs.append(rp_l)

    # Back panel — full height (no glass back for utility phone booth)
    bp = make_box("PB_BackPanel", BW-POST*2, PANEL_T, BH-RAIL_T,
                  cx=0, cy=BD-POST/2, cz=RAIL_T/2+(BH-RAIL_T)/2)
    bp.data.materials.append(gray_mat)
    objs.append(bp)

    # Left side upper panel behind the glass (interior side)
    # Actually let glass be transparent — no additional panels needed there
    return objs


def build_roof(al_mat, gray_mat, sign_blue_mat, sign_white_mat):
    """Flat aluminium roof with overhang + China Telecom sign strip."""
    objs = []

    # Roof slab (aluminum, gray underside)
    roof_w = BW + OVHG*2
    roof_d = BD + OVHG*2
    roof = make_box("PB_Roof", roof_w, roof_d, ROOF_H,
                    cx=0, cy=BD/2, cz=BH + ROOF_H/2)
    roof.data.materials.append(gray_mat)
    objs.append(roof)

    # Roof edge rail (aluminium frame running around perimeter)
    for side, (w, d, cx, cy) in enumerate([
        (roof_w, 0.025, 0.0,      -OVHG/2),          # front edge
        (roof_w, 0.025, 0.0,      BD+OVHG/2),         # back edge
        (0.025,  roof_d, -BW/2-OVHG/2, BD/2),         # left edge
        (0.025,  roof_d,  BW/2+OVHG/2, BD/2),         # right edge
    ]):
        e = make_box(f"PB_RoofEdge_{side}", w if w>0.025 else 0.025,
                     d if d>0.025 else 0.025, 0.032,
                     cx=cx, cy=cy, cz=BH+ROOF_H+0.016)
        e.data.materials.append(al_mat)
        objs.append(e)

    # ── Sign strip on top of roof ──────────────────────────────────────────────
    # Blue background strip running full width
    sign_bg = make_box("PB_SignBG", BW+OVHG*1.5, BD+OVHG*1.5, 0.005,
                       cx=0, cy=BD/2, cz=BH+ROOF_H+0.003)
    sign_bg.data.materials.append(sign_blue_mat)
    objs.append(sign_bg)

    # Sign housing box (raised box on top of roof, front face)
    sign_h = make_box("PB_SignBox", BW+OVHG, 0.12, 0.22,
                      cx=0, cy=0.06, cz=BH+ROOF_H+0.11)
    sign_h.data.materials.append(sign_blue_mat)
    objs.append(sign_h)

    # White face of sign
    sign_face = make_box("PB_SignFace", BW+OVHG-0.02, 0.006, 0.18,
                         cx=0, cy=0.002, cz=BH+ROOF_H+0.11)
    sign_face.data.materials.append(sign_white_mat)
    objs.append(sign_face)

    # "Blue stripe on white face indicating phone call"
    for i, bx in enumerate([-0.28, -0.12, 0.0, 0.12, 0.28]):
        bar = make_box(f"PB_SignBar_{i}", 0.06, 0.007, 0.05,
                       cx=bx, cy=0.0, cz=BH+ROOF_H+0.12)
        bar.data.materials.append(sign_blue_mat)
        objs.append(bar)

    return objs


def build_phone_unit(black_mat, btn_mat, lcd_mat, al_mat):
    """Interior coin phone unit mounted on back wall."""
    objs = []
    # Unit centred at x=0, mounted on back panel (y≈BD-PANEL_T), at ~1.3m height
    UX, UY, UZ = 0.0, BD - PANEL_T - 0.045, 1.30

    # Main body box
    body = make_box("PB_PhoneBody", 0.280, 0.080, 0.340, cx=UX, cy=UY, cz=UZ)
    body.data.materials.append(black_mat)
    objs.append(body)

    # Keypad zone (inset panel)
    kpad = make_box("PB_Keypad", 0.180, 0.015, 0.150, cx=UX, cy=UY-0.038, cz=UZ-0.06)
    kpad.data.materials.append(btn_mat)
    objs.append(kpad)

    # Individual buttons (4×3 grid)
    for row in range(4):
        for col in range(3):
            bx = UX - 0.055 + col * 0.055
            bz = UZ - 0.02 - row * 0.038
            btn = make_box(f"PB_Btn_{row}_{col}", 0.032, 0.010, 0.025,
                           cx=bx, cy=UY-0.042, cz=bz)
            btn.data.materials.append(btn_mat)
            objs.append(btn)

    # Coin slot slit
    slot = make_box("PB_CoinSlot", 0.060, 0.015, 0.008,
                    cx=UX+0.07, cy=UY-0.040, cz=UZ+0.13)
    slot.data.materials.append(al_mat)
    objs.append(slot)

    # Card slot
    cslot = make_box("PB_CardSlot", 0.055, 0.015, 0.006,
                     cx=UX+0.07, cy=UY-0.040, cz=UZ+0.09)
    cslot.data.materials.append(al_mat)
    objs.append(cslot)

    # LCD display panel (green emission)
    lcd = make_box("PB_LCD", 0.130, 0.010, 0.050,
                   cx=UX, cy=UY-0.039, cz=UZ+0.12)
    lcd.data.materials.append(lcd_mat)
    objs.append(lcd)

    # Handset cradle (two small hooks)
    for side in (-1, 1):
        hook = make_box(f"PB_Hook_{side}", 0.012, 0.035, 0.022,
                        cx=UX + side * 0.065, cy=UY-0.028, cz=UZ+0.155)
        hook.data.materials.append(black_mat)
        objs.append(hook)

    # Handset on cradle
    hs = make_box("PB_Handset", 0.170, 0.038, 0.040,
                  cx=UX, cy=UY-0.022, cz=UZ+0.165)
    hs.data.materials.append(black_mat)
    objs.append(hs)

    return objs, (UX, UY-0.055, UZ+0.165)   # return handset cord attachment point


def build_handset_cord(rubber_mat, attach_pt):
    """Coiled handset cord as a bezier swept tube."""
    ax, ay, az = attach_pt
    # Cord drops from handset cradle down to the side of the unit, with a loop
    p0 = (ax - 0.08, ay, az - 0.0)
    p1 = (ax - 0.12, ay - 0.05, az - 0.06)
    p2 = (ax - 0.10, ay - 0.06, az - 0.18)
    p3 = (ax - 0.06, ay - 0.04, az - 0.28)
    pts = bezier_cubic(p0, p1, p2, p3, n=20)
    cord = swept_tube(pts, 0.006, n=8, name="PB_Cord")
    cord.data.materials.append(rubber_mat)
    return cord


def build_interior_light(led_mat):
    """Interior LED strip at ceiling for illuminating phone area."""
    strip = make_box("PB_InteriorLED", BW*0.7, BD*0.6, 0.012,
                     cx=0, cy=BD/2, cz=BH-0.018)
    strip.data.materials.append(led_mat)
    return strip


def build_base(concrete_mat):
    base = make_box("PB_Base", BASE_W, BASE_D, BASE_H,
                    cx=0, cy=BD/2, cz=-BASE_H/2)
    base.data.materials.append(concrete_mat)
    return base


def build_ground(swalk_mat):
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0, 5, -BASE_H - 0.002))
    g = bpy.context.active_object; g.name = "Ground"
    g.data.materials.append(swalk_mat)
    return g

# ══════════════════════════════════════════════════════════════════════════════
# Area light (interior illumination)
# ══════════════════════════════════════════════════════════════════════════════

def build_interior_area_light():
    bpy.ops.object.light_add(type="AREA",
        location=(0, BD/2, BH - 0.05))
    light = bpy.context.active_object
    light.name = "PB_InteriorLight"
    light.data.energy  = 80.0
    light.data.color   = (1.0, 0.97, 0.90)
    light.data.size    = BW * 0.65
    light.data.size_y  = BD * 0.55
    light.data.spread  = math.radians(170)
    light.rotation_euler = (math.pi, 0, 0)   # shine downward
    return light

# ══════════════════════════════════════════════════════════════════════════════
# Scene / lighting helpers
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
    for d in ("OPTIX","OPENIMAGEDENOISE"):
        try: bpy.context.scene.cycles.denoiser=d; return
        except: pass

def add_sky(elev=30, rot=148, strength=1.0):
    world = bpy.data.worlds.new("World"); bpy.context.scene.world = world
    world.use_nodes = True; nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type="NISHITA"; sky.sun_elevation=math.radians(elev)
    sky.sun_rotation=math.radians(rot)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def add_night_world():
    world = bpy.data.worlds.new("World"); bpy.context.scene.world = world
    world.use_nodes = True; nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value    = (0.003, 0.005, 0.010, 1.0)
    bg.inputs["Strength"].default_value = 1.0
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def add_sun(energy=4.0, elev=30, az=148):
    bpy.ops.object.light_add(type="SUN", location=(0,0,20))
    s = bpy.context.active_object
    s.data.energy = energy; s.data.angle = math.radians(0.53)
    s.rotation_euler = (math.radians(90-elev), 0, math.radians(az))
    return s

def add_cam(loc, look_at, name="Cam", lens=50):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object; cam.name = name; cam.data.lens = lens
    bpy.context.scene.camera = cam
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=look_at)
    tgt = bpy.context.active_object; tgt.name = name+"_tgt"
    tc = cam.constraints.new("TRACK_TO")
    tc.target=tgt; tc.track_axis="TRACK_NEGATIVE_Z"; tc.up_axis="UP_Y"
    return cam, tgt

def rm_cam(cam, tgt):
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

def setup_png(fp, samples=256, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.cycles.samples=samples; sc.cycles.use_denoising=True; enable_denoiser()
    sc.render.resolution_x=rx; sc.render.resolution_y=ry
    sc.render.image_settings.file_format="PNG"; sc.render.filepath=str(fp)

def setup_video(fp, n=150, fps=25, samples=96, rx=1920, ry=1080):
    sc = bpy.context.scene; sc.frame_start=1; sc.frame_end=n; sc.render.fps=fps
    setup_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format="FFMPEG"
    sc.render.ffmpeg.format="MPEG4"; sc.render.ffmpeg.codec="H264"
    sc.render.ffmpeg.constant_rate_factor="HIGH"

def orbit_anim(cam, cx, cy, radius, height, n=150):
    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("PBOrbit")
    for f in range(1, n+1):
        ang = (f-1)/n*math.tau
        cam.location = (cx+radius*math.cos(ang), cy+radius*math.sin(ang), height)
        cam.keyframe_insert("location", frame=f)

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def build_complete_booth():
    """Create all booth components and return interior light."""
    al   = mat_aluminium_frame()
    blue = mat_powder_coat_blue()
    gray = mat_powder_coat_gray()
    glas = mat_tempered_glass(frost=0.0)
    blk  = mat_black_plastic()
    btn  = mat_button_gray()
    lcd  = mat_lcd_emissive()
    sb   = mat_sign_blue()
    sw   = mat_sign_white()
    rub  = mat_rubber_black()
    conc = mat_concrete()
    led  = mat_interior_led(strength=5.0)
    swlk = mat_sidewalk()

    build_ground(swlk)
    build_base(conc)
    build_frame(al)
    build_glass_panels(glas, al)
    build_solid_panels(blue, gray)
    build_roof(al, gray, sb, sw)
    phone_objs, cord_attach = build_phone_unit(blk, btn, lcd, al)
    build_handset_cord(rub, cord_attach)
    build_interior_light(led)
    area_light = build_interior_area_light()
    return area_light


def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    try:
        configure_cycles_devices()
    except Exception:
        bpy.context.scene.cycles.device = "GPU"

    # Allow glass/transparency rendering
    bpy.context.scene.cycles.max_bounces = 12
    bpy.context.scene.cycles.transmission_bounces = 8

    print("[PB] Building phone booth …")
    area_light = build_complete_booth()

    # Booth centroid for cameras
    BC_X, BC_Y, BC_Z = 0.0, BD/2, BH/2

    # ── 1. Day — three-quarter view ───────────────────────────────────────────
    print("\n[render] Day three-quarter view …")
    area_light.hide_render = True
    add_sky(elev=32, rot=145, strength=1.05)
    add_sun(energy=4.5, elev=32, az=145)

    cam, tgt = add_cam((-3.2, -2.8, 1.8), (0.0, BD/2, 1.1), "CamDay", lens=55)
    setup_png(OUT/"phonebooth_day.png", samples=288, rx=1920, ry=1080)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth_day.png'}")
    rm_cam(cam, tgt)

    # ── 2. Front view — showing interior through glass ────────────────────────
    print("\n[render] Front view (glass interior) …")
    cam, tgt = add_cam((0.0, -3.8, 1.35), (0.0, BD*0.4, 1.25), "CamFront", lens=70)
    setup_png(OUT/"phonebooth_front.png", samples=320, rx=1920, ry=1080)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth_front.png'}")
    rm_cam(cam, tgt)

    # ── 3. Close-up — phone unit + glass detail ───────────────────────────────
    print("\n[render] Phone unit close-up …")
    cam, tgt = add_cam((-1.2, -1.8, 1.32), (0.1, BD*0.5, 1.28), "CamClose", lens=90)
    setup_png(OUT/"phonebooth_closeup.png", samples=320, rx=1920, ry=1080)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth_closeup.png'}")
    rm_cam(cam, tgt)

    # ── 4. Night — interior glow ──────────────────────────────────────────────
    print("\n[render] Night interior glow …")
    for obj in list(bpy.context.scene.objects):
        if obj.type == "LIGHT" and obj.data.type == "SUN":
            bpy.data.objects.remove(obj, do_unlink=True)
    for w in list(bpy.data.worlds): bpy.data.worlds.remove(w)
    add_night_world()
    area_light.hide_render = False
    area_light.data.energy = 120.0

    cam, tgt = add_cam((-2.8, -2.5, 1.5), (0.0, BD/2, 0.9), "CamNight", lens=50)
    setup_png(OUT/"phonebooth_night.png", samples=384, rx=1920, ry=1080)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth_night.png'}")
    rm_cam(cam, tgt)

    # ── 5. Orbit video — dusk ─────────────────────────────────────────────────
    print("\n[render] Orbit video (dusk) …")
    for w in list(bpy.data.worlds): bpy.data.worlds.remove(w)
    add_sky(elev=6, rot=145, strength=0.55)
    add_sun(energy=1.0, elev=6, az=145)
    area_light.data.energy = 100.0

    N = 150
    cam, tgt = add_cam((5.0, BD/2, 2.2), (0.0, BD/2, 1.05), "CamOrbit", lens=55)
    orbit_anim(cam, 0, BD/2, 5.0, 2.2, n=N)
    setup_video(OUT/"phonebooth_orbit", n=N, samples=96)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'phonebooth_orbit0001-0150.mp4'}")
    rm_cam(cam, tgt)

    # ── 6. Save .blend ─────────────────────────────────────────────────────────
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"phonebooth.blend"))
    print(f"\n[blend] {OUT/'phonebooth.blend'}")
    print(f"[done] {OUT}")


if __name__ == "__main__":
    main()

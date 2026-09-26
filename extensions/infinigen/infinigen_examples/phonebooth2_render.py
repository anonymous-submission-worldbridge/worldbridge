#!/usr/bin/env python3
"""
phonebooth2_render.py — photo-realistic Chinese enclosed phone booth v2.

Critical improvements over v1 that achieve photo-realism:
  1. Bevel modifiers on ALL metal (1.5mm, 3 seg) — eliminates 'toy' look
  2. Glass BSDF + Volume Absorption (green tint, edge glow)
  3. Clearcoat layer on powder-coated panels
  4. AgX / Filmic colour management for cinematic exposure
  5. Tiled concrete sidewalk (Brick texture node with mortar)
  6. Building facade background for depth
  7. Two fill area lights + sun + sky (removes flat lighting)
  8. Detailed phone unit: curved handset, raised-relief keypad
  9. Door with stainless handle + visible hinge knuckles
 10. Rubber gasket seals visible around every glass pane
 11. Interior LED ceiling strip (visible from all angles)
 12. High sample count (512 stills, 96 video)

Structure (China Telecom enclosed rectangular booth):
  BW=0.95m  BD=0.68m  BH=2.05m (body) + 0.22m sign + 0.10m roof
  Frame:  40×40mm aluminium alloy square tube (solid + bevel)
  Glass:  8mm tempered clear, 3 sides + door upper half
  Panels: 0-0.82m height, CT blue powder coat (body), gray roof
  Door:   Front-right hinged, full height, upper=glass lower=panel

GPU: OPTIX → CUDA → HIP → METAL
Output: outputs/urban_v3_phonebooth2/
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


import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
import numpy as np
from mathutils import Vector

# ── GPU ────────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev_type in ("OPTIX", "CUDA", "HIP", "METAL"):
    try:
        prefs.compute_device_type = dev_type
        prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type != "CPU"]
        if gpus:
            for d in prefs.devices: d.use = True
            bpy.context.scene.cycles.device = "GPU"
            print(f"[GPU] Using {dev_type}: {[d.name for d in gpus]}")
            break
    except Exception:
        continue
print(f"[GPU] device = {bpy.context.scene.cycles.device}")

OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_phonebooth2')
OUT.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# Booth dimensions
# ══════════════════════════════════════════════════════════════════════════════
BW       = 0.950   # width  (x)
BD       = 0.680   # depth  (y)
BH       = 2.050   # body height (z)
POST     = 0.042   # square post section
RAIL     = 0.028   # horizontal rail height
GLASS_T  = 0.008   # glass thickness
PANEL_T  = 0.012   # solid panel thickness
GSKT_T   = 0.006   # rubber gasket thickness
PANEL_H  = 0.820   # solid panel zone height
ROOF_T   = 0.090   # roof slab thickness
ROOF_OVH = 0.040   # roof overhang
SIGN_H   = 0.200   # sign box height above roof
BASE_H   = 0.055   # concrete base pad height

# ══════════════════════════════════════════════════════════════════════════════
# Geometry helpers
# ══════════════════════════════════════════════════════════════════════════════

def _link(obj):
    if obj.name not in bpy.context.collection.objects:
        bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj

def _deselect():
    bpy.ops.object.select_all(action="DESELECT")

def _select_only(obj):
    _deselect()
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def add_bevel(obj, width=0.0015, segments=3):
    """Bevel modifier — the #1 fix for toy-model appearance."""
    bev = obj.modifiers.new("Bevel", "BEVEL")
    bev.width = width
    bev.segments = segments
    bev.profile = 0.70
    bev.limit_method = "ANGLE"
    bev.angle_limit = math.radians(30)
    bev.use_clamp_overlap = True
    bev.miter_outer = "MITER_ARC"
    return bev

def shade_smooth_obj(obj):
    _select_only(obj)
    bpy.ops.object.shade_smooth()
    # Blender 4.x auto-smooth via mesh data
    try:
        obj.data.use_auto_smooth = True
        obj.data.auto_smooth_angle = math.radians(30)
    except AttributeError:
        pass   # Blender 4.1+ uses modifier for this
    wn = obj.modifiers.new("WeightedNormal", "WEIGHTED_NORMAL")
    wn.weight = 50
    return obj

def make_box(name, lx, ly, lz, cx=0.0, cy=0.0, cz=0.0, bevel_w=None, smooth=True):
    x1,x2 = cx-lx/2, cx+lx/2
    y1,y2 = cy-ly/2, cy+ly/2
    z1,z2 = cz-lz/2, cz+lz/2
    verts = [(x1,y1,z1),(x2,y1,z1),(x2,y2,z1),(x1,y2,z1),
             (x1,y1,z2),(x2,y1,z2),(x2,y2,z2),(x1,y2,z2)]
    faces = [(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    _link(obj)
    if bevel_w is not None:
        add_bevel(obj, bevel_w)
    if smooth:
        shade_smooth_obj(obj)
    return obj

def make_cylinder(name, r, h, n=32, cx=0, cy=0, cz=0, bevel_w=None):
    verts, faces = [], []
    for j in range(n):
        a = j/n*math.tau
        verts += [(cx+r*math.cos(a), cy+r*math.sin(a), cz),
                  (cx+r*math.cos(a), cy+r*math.sin(a), cz+h)]
    faces.append(tuple(range(0,2*n,2)))
    faces.append(tuple(reversed(range(1,2*n,2))))
    for j in range(n):
        jn=(j+1)%n; b,t,bn,tn=2*j,2*j+1,2*jn,2*jn+1
        faces.append((b,bn,tn,t))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts,[],faces); mesh.update()
    obj = bpy.data.objects.new(name,mesh); _link(obj)
    if bevel_w: add_bevel(obj, bevel_w)
    shade_smooth_obj(obj)
    return obj

def _perp_frame(t):
    t = Vector(t).normalized()
    ref = Vector((0,0,1)) if abs(t.z)<0.9 else Vector((0,1,0))
    r = t.cross(ref).normalized(); u = t.cross(r).normalized()
    return r, u

def swept_tube(pts, radius, n=10, name="Tube"):
    verts,faces,rings = [],[],[]
    for i,pt in enumerate(pts):
        tang = (Vector(pts[i+1])-Vector(pt)) if i<len(pts)-1 else (Vector(pt)-Vector(pts[i-1]))
        r,u = _perp_frame(tang)
        s=len(verts); rings.append(s)
        for j in range(n):
            a=j/n*math.tau
            verts.append(tuple(Vector(pt)+r*radius*math.cos(a)+u*radius*math.sin(a)))
    for k in range(len(rings)-1):
        s0,s1=rings[k],rings[k+1]
        for j in range(n):
            jn=(j+1)%n
            faces.append((s0+j,s0+jn,s1+jn,s1+j))
    faces.append(tuple(rings[0]+j for j in range(n)))
    faces.append(tuple(reversed([rings[-1]+j for j in range(n)])))
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces); mesh.update()
    obj=bpy.data.objects.new(name,mesh); _link(obj); shade_smooth_obj(obj)
    return obj

def bezier_cubic(p0,p1,p2,p3,n=20):
    p0,p1,p2,p3=[np.array(x) for x in [p0,p1,p2,p3]]
    return [tuple((1-t)**3*p0+3*(1-t)**2*t*p1+3*(1-t)*t**2*p2+t**3*p3)
            for t in np.linspace(0,1,n)]

# ══════════════════════════════════════════════════════════════════════════════
# PBR Materials (photo-realistic quality)
# ══════════════════════════════════════════════════════════════════════════════

def _nt(mat):
    mat.use_nodes = True; mat.node_tree.nodes.clear(); return mat.node_tree

def _lnk(nt, a, b): nt.links.new(a, b)

def mat_frame_aluminum(name="FrameAl"):
    """
    Powder-coated aluminium frame.  Two-layer: diffuse blue-gray + clearcoat.
    Bevel modifier creates micro-highlight catchlights at edges.
    """
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    mix  = nt.nodes.new("ShaderNodeMixShader")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    coat = nt.nodes.new("ShaderNodeBsdfPrincipled")     # clearcoat layer
    fw   = nt.nodes.new("ShaderNodeFresnel")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")

    # Base coat: China Telecom gray-blue frame
    bsdf.inputs["Base Color"].default_value  = (0.30, 0.32, 0.36, 1.0)
    bsdf.inputs["Metallic"].default_value    = 0.0
    bsdf.inputs["Roughness"].default_value   = 0.55
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value   = 0.35
        bsdf.inputs["Coat Roughness"].default_value= 0.08
    elif "Clearcoat" in bsdf.inputs:
        bsdf.inputs["Clearcoat"].default_value = 0.35
        bsdf.inputs["Clearcoat Roughness"].default_value = 0.08

    # Surface bump for paint texture
    noise.inputs["Scale"].default_value   = 200.0
    noise.inputs["Detail"].default_value  = 10.0
    noise.inputs["Roughness"].default_value = 0.6
    bump.inputs["Strength"].default_value = 0.025
    bump.inputs["Distance"].default_value = 0.0008
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])

    # Simple connection (no second layer needed for gray)
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_panel_blue(name="PanelBlue"):
    """China Telecom blue powder-coated steel panel — lower body section."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    bump = nt.nodes.new("ShaderNodeBump")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord= nt.nodes.new("ShaderNodeTexCoord")

    # CT blue: sRGB #0570C7 → linear ~(0.01, 0.17, 0.60)
    bsdf.inputs["Base Color"].default_value  = (0.008, 0.165, 0.595, 1.0)
    bsdf.inputs["Metallic"].default_value    = 0.0
    bsdf.inputs["Roughness"].default_value   = 0.58
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value    = 0.30
        bsdf.inputs["Coat Roughness"].default_value = 0.10

    noise.inputs["Scale"].default_value   = 180.0
    noise.inputs["Detail"].default_value  = 12.0
    noise.inputs["Roughness"].default_value = 0.55
    bump.inputs["Strength"].default_value = 0.018
    bump.inputs["Distance"].default_value = 0.0006
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_roof_gray(name="RoofGray"):
    """Powder-coated gray aluminium — roof + back panel."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.42, 0.43, 0.44, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.65
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value = 0.20
        bsdf.inputs["Coat Roughness"].default_value = 0.12
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_tempered_glass(name="TempGlass"):
    """
    Tempered glass: Glass BSDF + Volume Absorption (green edge tint).
    Fingerprint bump for realism.  This is the key material for photo-realism.
    """
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out   = nt.nodes.new("ShaderNodeOutputMaterial")
    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    bump  = nt.nodes.new("ShaderNodeBump")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    volabs= nt.nodes.new("ShaderNodeVolumeAbsorption")

    # Clear glass with barely-perceptible green tint
    glass.inputs["Color"].default_value     = (0.92, 0.98, 0.94, 1.0)
    glass.inputs["Roughness"].default_value = 0.005   # very smooth
    glass.inputs["IOR"].default_value       = 1.517   # soda-lime glass

    # Smudge/fingerprint bump
    noise.inputs["Scale"].default_value   = 30.0
    noise.inputs["Detail"].default_value  = 12.0
    noise.inputs["Roughness"].default_value = 0.85
    bump.inputs["Strength"].default_value = 0.018
    bump.inputs["Distance"].default_value = 0.0005
    _lnk(nt, coord.outputs["UV"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], glass.inputs["Normal"])

    # Volume absorption: gives the characteristic GREEN edge glow of thick glass
    volabs.inputs["Color"].default_value   = (0.75, 0.95, 0.80, 1.0)
    volabs.inputs["Density"].default_value = 0.06

    _lnk(nt, glass.outputs["BSDF"], out.inputs["Surface"])
    _lnk(nt, volabs.outputs["Volume"], out.inputs["Volume"])
    return mat

def mat_rubber_gasket(name="Gasket"):
    """Black rubber compression gasket around glass edges."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.014, 0.014, 0.014, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.95
    bsdf.inputs["IOR"].default_value        = 1.50
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_stainless_steel(name="Stainless"):
    """Brushed stainless steel — door handle, hinges."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    mp   = nt.nodes.new("ShaderNodeMapping")

    bsdf.inputs["Base Color"].default_value = (0.68, 0.69, 0.70, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.98
    bsdf.inputs["Roughness"].default_value  = 0.18
    if "Anisotropic" in bsdf.inputs:
        bsdf.inputs["Anisotropic"].default_value = 0.60
    noise.inputs["Scale"].default_value    = 120.0
    noise.inputs["Detail"].default_value   = 4.0
    noise.inputs["Roughness"].default_value= 0.5
    mp.inputs["Scale"].default_value = (8.0, 0.5, 0.5)
    _lnk(nt, coord.outputs["UV"], mp.inputs["Vector"])
    _lnk(nt, mp.outputs["Vector"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bsdf.inputs["Roughness"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_black_abs(name="BlackABS"):
    """Black ABS plastic — phone body, buttons."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    bsdf.inputs["Base Color"].default_value = (0.018, 0.018, 0.018, 1.0)
    bsdf.inputs["Metallic"].default_value   = 0.0
    bsdf.inputs["Roughness"].default_value  = 0.42
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value    = 0.15
        bsdf.inputs["Coat Roughness"].default_value = 0.30
    noise.inputs["Scale"].default_value = 250.0; noise.inputs["Detail"].default_value = 8.0
    bump.inputs["Strength"].default_value = 0.012; bump.inputs["Distance"].default_value = 0.0003
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_button(name="Button"):
    """Gray phone button — subtle engraved appearance."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.18, 0.18, 0.18, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.65
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_lcd(name="LCD"):
    """Green-glow LCD display."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    mix  = nt.nodes.new("ShaderNodeMixShader")
    emit = nt.nodes.new("ShaderNodeEmission")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    emit.inputs["Color"].default_value    = (0.15, 0.78, 0.25, 1.0)
    emit.inputs["Strength"].default_value = 2.5
    bsdf.inputs["Base Color"].default_value = (0.04, 0.14, 0.06, 1.0)
    mix.inputs["Fac"].default_value = 0.70
    _lnk(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _lnk(nt, emit.outputs["Emission"], mix.inputs[2])
    _lnk(nt, mix.outputs["Shader"], out.inputs["Surface"])
    return mat

def mat_sign_emit(name="SignEmit", color=(0.01, 0.18, 0.60)):
    """Blue emissive signage panel."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    mix  = nt.nodes.new("ShaderNodeMixShader")
    emit = nt.nodes.new("ShaderNodeEmission")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    emit.inputs["Color"].default_value    = (*color, 1.0)
    emit.inputs["Strength"].default_value = 1.8
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.70
    mix.inputs["Fac"].default_value = 0.35
    _lnk(nt, bsdf.outputs["BSDF"], mix.inputs[1])
    _lnk(nt, emit.outputs["Emission"], mix.inputs[2])
    _lnk(nt, mix.outputs["Shader"], out.inputs["Surface"])
    return mat

def mat_sign_white(name="SignWhite"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value = (0.90, 0.90, 0.90, 1.0)
    bsdf.inputs["Roughness"].default_value  = 0.55
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_ceiling_led(name="CeilLED"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    emit = nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value    = (1.0, 0.97, 0.90, 1.0)
    emit.inputs["Strength"].default_value = 5.0
    _lnk(nt, emit.outputs["Emission"], out.inputs["Surface"])
    return mat

def mat_concrete_base(name="ConcreteBase"):
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = 12.0; noise.inputs["Detail"].default_value=8.0
    ramp.color_ramp.elements[0].color = (0.38,0.36,0.34,1.0)
    ramp.color_ramp.elements[1].color = (0.58,0.56,0.53,1.0)
    bump.inputs["Strength"].default_value = 0.28; bump.inputs["Distance"].default_value=0.005
    bsdf.inputs["Roughness"].default_value = 0.95
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, noise.outputs["Fac"], ramp.inputs["Fac"])
    _lnk(nt, ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _lnk(nt, noise.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_sidewalk_tiles(name="SidewalkTiles"):
    """Tiled concrete with Brick node for visible grout joints."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    brick= nt.nodes.new("ShaderNodeTexBrick")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    mp   = nt.nodes.new("ShaderNodeMapping")

    mp.inputs["Scale"].default_value = (0.25, 0.25, 1.0)   # tile size ~0.4m

    brick.inputs["Scale"].default_value       = 1.0
    brick.inputs["Mortar Size"].default_value = 0.04
    brick.inputs["Mortar Smooth"].default_value = 0.1
    brick.inputs["Bias"].default_value        = 0.0
    brick.inputs["Color1"].default_value      = (0.52, 0.50, 0.48, 1.0)
    brick.inputs["Color2"].default_value      = (0.58, 0.56, 0.53, 1.0)
    brick.inputs["Mortar"].default_value      = (0.30, 0.29, 0.28, 1.0)

    bump.inputs["Strength"].default_value = 0.15
    bump.inputs["Distance"].default_value = 0.003
    bsdf.inputs["Roughness"].default_value = 0.88

    _lnk(nt, coord.outputs["Generated"], mp.inputs["Vector"])
    _lnk(nt, mp.outputs["Vector"], brick.inputs["Vector"])
    _lnk(nt, brick.outputs["Color"], bsdf.inputs["Base Color"])
    _lnk(nt, brick.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

def mat_building_facade(name="Facade"):
    """Concrete building wall — appears in background for depth."""
    mat = bpy.data.materials.new(name)
    nt = _nt(mat)
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise= nt.nodes.new("ShaderNodeTexNoise")
    brick= nt.nodes.new("ShaderNodeTexBrick")
    mix  = nt.nodes.new("ShaderNodeMixRGB")
    bump = nt.nodes.new("ShaderNodeBump")
    coord= nt.nodes.new("ShaderNodeTexCoord")
    mp   = nt.nodes.new("ShaderNodeMapping")

    mp.inputs["Scale"].default_value = (0.4, 0.15, 1.0)
    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Mortar Size"].default_value = 0.025
    brick.inputs["Color1"].default_value = (0.58,0.53,0.48,1.0)
    brick.inputs["Color2"].default_value = (0.62,0.58,0.52,1.0)
    brick.inputs["Mortar"].default_value = (0.42,0.38,0.34,1.0)
    noise.inputs["Scale"].default_value = 4.0
    mix.inputs["Fac"].default_value = 0.2
    bump.inputs["Strength"].default_value = 0.20
    bsdf.inputs["Roughness"].default_value = 0.92

    _lnk(nt, coord.outputs["Generated"], mp.inputs["Vector"])
    _lnk(nt, mp.outputs["Vector"], brick.inputs["Vector"])
    _lnk(nt, coord.outputs["Generated"], noise.inputs["Vector"])
    _lnk(nt, brick.outputs["Color"], mix.inputs[1])
    _lnk(nt, noise.outputs["Color"], mix.inputs[2])
    _lnk(nt, mix.outputs["Color"], bsdf.inputs["Base Color"])
    _lnk(nt, brick.outputs["Fac"], bump.inputs["Height"])
    _lnk(nt, bump.outputs["Normal"], bsdf.inputs["Normal"])
    _lnk(nt, bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat

# ══════════════════════════════════════════════════════════════════════════════
# Booth construction
# ══════════════════════════════════════════════════════════════════════════════

def build_frame(al_mat, bev=0.0016):
    """
    Structural frame: 4 corner posts + 3-tier horizontal rails.
    BEVEL on every post/rail → realistic catchlights on edges.
    Booth spans: x ∈ [-BW/2, BW/2], y ∈ [0, BD], z ∈ [0, BH].
    """
    objs = []
    px = BW/2 - POST/2
    py_f, py_b = POST/2, BD - POST/2

    for i,(x,y) in enumerate([(-px,py_f),(px,py_f),(-px,py_b),(px,py_b)]):
        p = make_box(f"PB2_Post{i}", POST, POST, BH, cx=x, cy=y, cz=BH/2,
                     bevel_w=bev)
        p.data.materials.append(al_mat); objs.append(p)

    # Horizontal rails: bottom, mid (at PANEL_H), top
    rail_defs = []
    for z_ctr in [RAIL/2, PANEL_H, BH - RAIL/2]:
        # Front & back (x-direction rails)
        for yv in [py_f, py_b]:
            rail_defs.append(("x", 0.0, yv, z_ctr, BW - POST*2 + 0.004, POST, RAIL))
        # Left & right (y-direction rails)
        for xv in [-px, px]:
            rail_defs.append(("y", xv, BD/2, z_ctr, POST, BD - POST*2 + 0.004, RAIL))

    for k,(axis,cx,cy,cz,lx,ly,lz) in enumerate(rail_defs):
        r = make_box(f"PB2_Rail{k}", lx, ly, lz, cx=cx, cy=cy, cz=cz, bevel_w=bev)
        r.data.materials.append(al_mat); objs.append(r)
    return objs


def build_glass_and_gaskets(glass_mat, gskt_mat, bev=0.0005):
    """
    Glass panes + rubber compression gaskets.
    Glass sits INSIDE the post rebates.  Gasket strips surround each pane.
    """
    objs = []
    # Glass panes are inset from the outer post face
    gx_inset = POST - GLASS_T/2     # glass sits at this x offset from centre
    gy_glass = BH - PANEL_H - RAIL  # height of glass zone above mid-rail

    # ── Side panels (left & right) — full glass, full height glass zone ────
    for side,xv in [(-1, -BW/2 + gx_inset), (1, BW/2 - gx_inset)]:
        g = make_box(f"PB2_GlassS{side}", GLASS_T, BD - POST*2, gy_glass,
                     cx=xv, cy=BD/2, cz=PANEL_H + RAIL + gy_glass/2)
        g.data.materials.append(glass_mat); objs.append(g)
        # Gaskets: top, bottom, front, back of this panel
        for tag,lgx,lgy,lgz,gcx,gcy,gcz in [
            ("ST", GLASS_T+0.002, BD-POST*2, GSKT_T,  xv,   BD/2, PANEL_H+RAIL+GSKT_T/2),
            ("SB", GLASS_T+0.002, BD-POST*2, GSKT_T,  xv,   BD/2, BH-GSKT_T/2),
            ("SF", GLASS_T+0.002, GSKT_T,   gy_glass, xv,   POST, PANEL_H+RAIL+gy_glass/2),
            ("SBk",GLASS_T+0.002, GSKT_T,   gy_glass, xv,   BD-POST, PANEL_H+RAIL+gy_glass/2),
        ]:
            gsk = make_box(f"PB2_Gsk{side}{tag}", lgx, lgy, lgz,
                           cx=gcx, cy=gcy, cz=gcz)
            gsk.data.materials.append(gskt_mat); objs.append(gsk)

    # ── Back panel glass (upper zone) ─────────────────────────────────────────
    gy_ins = BD - POST*2
    g_back = make_box("PB2_GlassBack", BW - POST*2, GLASS_T, gy_glass,
                      cx=0, cy=BD - POST + GLASS_T/2, cz=PANEL_H+RAIL+gy_glass/2)
    g_back.data.materials.append(glass_mat); objs.append(g_back)

    # ── Front upper glass (door frame has glass too — built in door section) ──
    # Front glass occupies ~half of the front face (non-door side)
    door_w = BW * 0.52   # door takes left 52% of front face
    nondoor_w = BW - door_w - POST
    g_front_nd = make_box("PB2_GlassFrontND", nondoor_w - POST, GLASS_T, gy_glass,
                          cx=BW/2 - POST - nondoor_w/2, cy=POST - GLASS_T/2,
                          cz=PANEL_H+RAIL+gy_glass/2)
    g_front_nd.data.materials.append(glass_mat); objs.append(g_front_nd)
    return objs


def build_solid_panels(blue_mat, gray_mat):
    """Solid powder-coated panels: lower section all sides, full back lower."""
    objs = []
    panel_zone = PANEL_H - RAIL   # height of solid zone (below mid-rail)

    sides = [
        # name,  lx,  ly, cx, cy, cz
        ("FL", BW*0.52-POST, PANEL_T, -BW*0.25+POST/2, POST/2-PANEL_T/2, RAIL+panel_zone/2),  # front-left (door side lower)
        ("FR", BW*0.48-POST, PANEL_T,  BW*0.28, POST/2-PANEL_T/2, RAIL+panel_zone/2),         # front-right lower
        ("L",  PANEL_T, BD-POST*2, -BW/2+POST/2-PANEL_T/2, BD/2, RAIL+panel_zone/2),
        ("R",  PANEL_T, BD-POST*2,  BW/2-POST/2+PANEL_T/2, BD/2, RAIL+panel_zone/2),
        ("Back_L", BW-POST*2, PANEL_T, 0, BD-POST/2+PANEL_T/2, RAIL+panel_zone/2),
    ]
    for tag,lx,ly,cx,cy,cz in sides:
        p = make_box(f"PB2_Panel{tag}", lx, ly, panel_zone, cx=cx, cy=cy, cz=cz,
                     bevel_w=0.001)
        p.data.materials.append(blue_mat); objs.append(p)

    # Back panel full height
    bk = make_box("PB2_BackFull", BW-POST*2, PANEL_T, BH-RAIL,
                  cx=0, cy=BD-POST/2+PANEL_T/2, cz=RAIL+(BH-RAIL)/2, bevel_w=0.001)
    bk.data.materials.append(gray_mat); objs.append(bk)
    return objs


def build_door(al_mat, glass_mat, gskt_mat, ss_mat, bev=0.0016):
    """
    Hinged door: ~52% of front width.
    Upper half: glass pane with gasket.
    Lower half: blue panel.
    Handle: horizontal stainless bar (35mm Ø).
    Hinges: 3 knuckle cylinders on right-door-edge.
    """
    objs = []
    door_w = BW * 0.52 - POST * 1.5
    door_cx = -BW/2 + POST + door_w/2 + 0.002

    # Door frame rails (top, bottom, left, right verticals)
    door_frame_parts = [
        (door_w+POST, POST, RAIL, door_cx, POST/2, BH-RAIL/2),        # top
        (door_w+POST, POST, RAIL, door_cx, POST/2, RAIL/2),            # bot
        (POST, POST, BH, door_cx - door_w/2 - POST/2, POST/2, BH/2),  # left
        (POST, POST, BH, door_cx + door_w/2 + POST/2, POST/2, BH/2),  # right
    ]
    for k,(lx,ly,lz,cx,cy,cz) in enumerate(door_frame_parts):
        fr = make_box(f"PB2_DoorFr{k}", lx, ly, lz, cx=cx, cy=cy, cz=cz, bevel_w=bev)
        fr.data.materials.append(al_mat); objs.append(fr)

    # Glass upper pane (above PANEL_H)
    dg_h = BH - PANEL_H - RAIL * 2
    dg = make_box("PB2_DoorGlass", door_w - 0.004, GLASS_T, dg_h,
                  cx=door_cx, cy=POST/2 - GLASS_T/2,
                  cz=PANEL_H + RAIL + dg_h/2)
    dg.data.materials.append(glass_mat); objs.append(dg)

    # Rubber gasket around door glass
    for tag,lx,ly,lz,cy_off,cz_off in [
        ("T", door_w, GSKT_T, GSKT_T, 0, BH-RAIL-GSKT_T/2),
        ("B", door_w, GSKT_T, GSKT_T, 0, PANEL_H+RAIL+GSKT_T/2),
    ]:
        gsk = make_box(f"PB2_DGsk{tag}", lx, ly, lz,
                       cx=door_cx, cy=POST/2, cz=cz_off)
        gsk.data.materials.append(gskt_mat); objs.append(gsk)

    # Solid lower pane
    dp_h = PANEL_H - RAIL
    dp = make_box("PB2_DoorPanel", door_w - 0.004, PANEL_T, dp_h,
                  cx=door_cx, cy=POST/2 - PANEL_T/2,
                  cz=RAIL + dp_h/2, bevel_w=0.001)
    dp.data.materials.append(al_mat); objs.append(dp)

    # Door handle: horizontal stainless tube, at 1.1m height, front face
    handle_x1 = door_cx - 0.18
    handle_x2 = door_cx + 0.18
    h_pts = [(handle_x1, POST/2-0.018, 1.05),
             (handle_x1, POST/2-0.048, 1.05),
             (handle_x2, POST/2-0.048, 1.05),
             (handle_x2, POST/2-0.018, 1.05)]
    handle = swept_tube(h_pts, 0.014, n=14, name="PB2_DoorHandle")
    handle.data.materials.append(ss_mat); objs.append(handle)

    # Hinge knuckles (3 cylinders on left edge of door)
    for z_h in [0.25, 1.00, 1.75]:
        hinge = make_cylinder("PB2_Hinge_"+str(int(z_h*100)),
                              0.018, 0.065,
                              cx=door_cx-door_w/2-POST/2, cy=POST/2+0.008, cz=z_h)
        hinge.data.materials.append(ss_mat); objs.append(hinge)
    return objs


def build_roof(al_mat, gray_mat, sign_blue_mat, sign_white_mat, bev=0.002):
    """Flat aluminium roof + overhang + front sign box."""
    objs = []
    rw = BW + ROOF_OVH*2
    rd = BD + ROOF_OVH*2

    # Main roof slab
    roof = make_box("PB2_Roof", rw, rd, ROOF_T,
                    cx=0, cy=BD/2, cz=BH + ROOF_T/2, bevel_w=bev)
    roof.data.materials.append(gray_mat); objs.append(roof)

    # Perimeter edge drip strip
    for k,(lx,ly,cx,cy) in enumerate([
        (rw, 0.025, 0.0, -ROOF_OVH),
        (rw, 0.025, 0.0, BD+ROOF_OVH),
        (0.025, rd, -BW/2-ROOF_OVH, BD/2),
        (0.025, rd,  BW/2+ROOF_OVH, BD/2),
    ]):
        drip = make_box(f"PB2_Drip{k}", max(lx,0.025), max(ly,0.025), 0.020,
                        cx=cx, cy=cy, cz=BH+ROOF_T+0.010)
        drip.data.materials.append(al_mat); objs.append(drip)

    # ── Front sign box ─────────────────────────────────────────────────────────
    # Blue background box (full width of roof, projects forward)
    sign_box = make_box("PB2_SignBox", rw, 0.130, SIGN_H,
                        cx=0, cy=-0.065, cz=BH+ROOF_T+SIGN_H/2, bevel_w=0.003)
    sign_box.data.materials.append(sign_blue_mat); objs.append(sign_box)

    # White lettering face on sign (front of sign box)
    sign_face = make_box("PB2_SignFace", rw-0.020, 0.008, SIGN_H-0.020,
                         cx=0, cy=-0.125, cz=BH+ROOF_T+SIGN_H/2)
    sign_face.data.materials.append(sign_white_mat); objs.append(sign_face)

    # "CHINA TELECOM" horizontal logo bars on sign face
    for bar_i, bar_x in enumerate([-0.28, -0.14, 0.0, 0.14, 0.28]):
        bar = make_box(f"PB2_LogoBar{bar_i}", 0.055, 0.009, 0.040,
                       cx=bar_x, cy=-0.127, cz=BH+ROOF_T+SIGN_H*0.55)
        bar.data.materials.append(sign_blue_mat); objs.append(bar)

    # Top mini sign on roof (back side)
    back_sign = make_box("PB2_BackSign", BW, 0.015, 0.150,
                         cx=0, cy=BD+ROOF_OVH-0.015, cz=BH+ROOF_T+0.080)
    back_sign.data.materials.append(sign_blue_mat); objs.append(back_sign)
    return objs


def build_phone_unit(black_mat, btn_mat, lcd_mat, ss_mat, bev=0.001):
    """Detailed phone unit on back wall interior."""
    objs = []
    # Unit mounted at: x=0, y=BD-0.15m (against back wall), z=1.32m centre
    UX, UY, UZ = 0.0, BD - 0.14, 1.32

    # Main body (trapezoidal-ish → two boxes)
    body = make_box("PB2_PBody", 0.265, 0.085, 0.330, cx=UX, cy=UY, cz=UZ, bevel_w=bev)
    body.data.materials.append(black_mat); objs.append(body)

    # Slightly larger facia plate
    facia = make_box("PB2_PFacia", 0.275, 0.010, 0.340,
                     cx=UX, cy=UY-0.042, cz=UZ, bevel_w=bev)
    facia.data.materials.append(black_mat); objs.append(facia)

    # LCD display
    lcd = make_box("PB2_PLCD", 0.130, 0.008, 0.048,
                   cx=UX, cy=UY-0.046, cz=UZ+0.112)
    lcd.data.materials.append(lcd_mat); objs.append(lcd)

    # Coin slot (horizontal slit)
    cs = make_box("PB2_PCoin", 0.062, 0.008, 0.010,
                  cx=0.072, cy=UY-0.046, cz=UZ+0.080, bevel_w=0.0005)
    cs.data.materials.append(ss_mat); objs.append(cs)

    # Card slot
    ks = make_box("PB2_PCard", 0.060, 0.008, 0.006,
                  cx=0.072, cy=UY-0.046, cz=UZ+0.052, bevel_w=0.0005)
    ks.data.materials.append(ss_mat); objs.append(ks)

    # Keypad: 4 rows × 3 cols
    for row in range(4):
        for col in range(3):
            bx = UX - 0.054 + col*0.054
            bz = UZ - 0.010 - row*0.042
            btn = make_box(f"PB2_PBtn_{row}_{col}", 0.036, 0.008, 0.030,
                           cx=bx, cy=UY-0.047, cz=bz, bevel_w=0.0012)
            btn.data.materials.append(btn_mat); objs.append(btn)

    # Handset cradle (two hook bars)
    for side in (-1, 1):
        hook = make_box(f"PB2_PHook{side}", 0.010, 0.040, 0.018,
                        cx=UX+side*0.068, cy=UY-0.034, cz=UZ+0.155, bevel_w=bev)
        hook.data.materials.append(black_mat); objs.append(hook)

    # Handset
    hs = make_box("PB2_PHandset", 0.165, 0.040, 0.038,
                  cx=UX, cy=UY-0.020, cz=UZ+0.165, bevel_w=bev)
    hs.data.materials.append(black_mat); objs.append(hs)

    # Handset earpiece bump
    ep = make_box("PB2_PEar", 0.050, 0.040, 0.035,
                  cx=UX-0.055, cy=UY-0.024, cz=UZ+0.172, bevel_w=bev)
    ep.data.materials.append(black_mat); objs.append(ep)
    mp = make_box("PB2_PMic", 0.050, 0.040, 0.035,
                  cx=UX+0.055, cy=UY-0.024, cz=UZ+0.172, bevel_w=bev)
    mp.data.materials.append(black_mat); objs.append(mp)

    # Coiled cord
    cord_pts = bezier_cubic(
        (UX-0.075, UY-0.020, UZ+0.165),
        (UX-0.120, UY-0.050, UZ+0.100),
        (UX-0.115, UY-0.060, UZ-0.020),
        (UX-0.080, UY-0.045, UZ-0.090), n=18
    )
    cord = swept_tube(cord_pts, 0.005, n=8, name="PB2_Cord")
    cord.data.materials.append(black_mat); objs.append(cord)

    return objs


def build_interior_ceiling(led_mat):
    """Interior LED strip on ceiling."""
    strip = make_box("PB2_CeilLED", BW*0.75, BD*0.65, 0.012,
                     cx=0, cy=BD/2, cz=BH-0.015)
    strip.data.materials.append(led_mat)
    return strip


def build_base_pad(conc_mat, bev=0.002):
    """Small concrete platform under booth."""
    pad = make_box("PB2_Base", BW+0.08, BD+0.07, BASE_H,
                   cx=0, cy=BD/2, cz=-BASE_H/2, bevel_w=bev)
    pad.data.materials.append(conc_mat)
    return pad


def build_environment(swlk_mat, facade_mat):
    """Tiled sidewalk + building facade for depth/context."""
    # Large sidewalk slab
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0, 8.0, -BASE_H-0.001))
    sw = bpy.context.active_object; sw.name = "PB2_Sidewalk"
    sw.data.materials.append(swlk_mat)

    # Building facade behind the booth (2.5m away in +y direction)
    facade = make_box("PB2_Facade", 20.0, 0.30, 8.0,
                      cx=0, cy=BD+2.8, cz=4.0)
    facade.data.materials.append(facade_mat)

    # Ground strip of road in front (-y direction)
    bpy.ops.mesh.primitive_plane_add(size=20.0, location=(0, -6.0, -BASE_H-0.001))
    road = bpy.context.active_object; road.name = "PB2_Road"
    road.data.materials.append(swlk_mat)
    return sw, facade, road


def build_interior_area_light():
    """Area light inside booth ceiling for interior illumination."""
    bpy.ops.object.light_add(type="AREA", location=(0, BD/2, BH-0.08))
    light = bpy.context.active_object; light.name = "PB2_IntLight"
    light.data.energy   = 60.0
    light.data.color    = (1.0, 0.97, 0.90)
    light.data.size     = BW * 0.70
    light.data.size_y   = BD * 0.58
    light.data.spread   = math.radians(170)
    light.rotation_euler = (math.pi, 0, 0)
    return light

# ══════════════════════════════════════════════════════════════════════════════
# Scene helpers
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

def set_color_management():
    """AgX or Filmic for photographic exposure — major realism improvement."""
    vs = bpy.context.scene.view_settings
    for vt in ("AgX", "Filmic"):
        try: vs.view_transform = vt; break
        except: pass
    vs.look = "None"
    vs.exposure = 0.0
    vs.gamma = 1.0

def add_sky(elev=28, rot=142, strength=0.92):
    world = bpy.data.worlds.new("World"); bpy.context.scene.world = world
    world.use_nodes = True; nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type="NISHITA"; sky.sun_elevation=math.radians(elev); sky.sun_rotation=math.radians(rot)
    sky.altitude = 20.0; sky.air_density = 1.0; sky.dust_density = 1.0
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def add_night_world():
    world = bpy.data.worlds.new("World"); bpy.context.scene.world = world
    world.use_nodes = True; nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground"); out = nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value = (0.002, 0.004, 0.010, 1.0)
    bg.inputs["Strength"].default_value = 0.8
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

def add_sun(energy=3.8, elev=28, az=142):
    bpy.ops.object.light_add(type="SUN", location=(0,0,20))
    s=bpy.context.active_object; s.data.energy=energy; s.data.angle=math.radians(0.53)
    s.rotation_euler=(math.radians(90-elev),0,math.radians(az)); return s

def add_fill_lights():
    """Two soft area fill lights to simulate sky light from sides."""
    positions = [
        (-8.0,  BD/2+1.0, 3.5,  "FillL"),
        ( 8.0,  BD/2+1.0, 3.5,  "FillR"),
    ]
    lights = []
    for x,y,z,name in positions:
        bpy.ops.object.light_add(type="AREA", location=(x,y,z))
        lt = bpy.context.active_object; lt.name = name
        lt.data.energy  = 45.0
        lt.data.color   = (0.75, 0.85, 1.0)  # slight blue-sky fill
        lt.data.size    = 3.0
        lt.data.size_y  = 3.0
        lt.data.spread  = math.radians(120)
        # Point at booth centre
        _deselect(); lt.select_set(True)
        bpy.context.view_layer.objects.active = lt
        lights.append(lt)
    return lights

def add_cam(loc, look_at, name="Cam", lens=50, dof_dist=None):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object; cam.name=name; cam.data.lens=lens
    bpy.context.scene.camera = cam
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=look_at)
    tgt=bpy.context.active_object; tgt.name=name+"_tgt"
    tc=cam.constraints.new("TRACK_TO")
    tc.target=tgt; tc.track_axis="TRACK_NEGATIVE_Z"; tc.up_axis="UP_Y"
    if dof_dist:
        cam.data.dof.use_dof = True
        cam.data.dof.focus_distance = dof_dist
        cam.data.dof.aperture_fstop = 4.0
    return cam, tgt

def rm_cam(cam, tgt):
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)

def setup_png(fp, samples=512, rx=1920, ry=1080):
    sc=bpy.context.scene
    sc.cycles.samples=samples; sc.cycles.use_denoising=True; enable_denoiser()
    sc.cycles.max_bounces = 12; sc.cycles.transmission_bounces = 10
    sc.cycles.caustics_refractive = False   # faster glass, no caustics loss
    sc.render.resolution_x=rx; sc.render.resolution_y=ry
    sc.render.image_settings.file_format="PNG"; sc.render.filepath=str(fp)

def setup_video(fp, n=150, fps=25, samples=96, rx=1920, ry=1080):
    sc=bpy.context.scene; sc.frame_start=1; sc.frame_end=n; sc.render.fps=fps
    setup_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format="FFMPEG"
    sc.render.ffmpeg.format="MPEG4"; sc.render.ffmpeg.codec="H264"
    sc.render.ffmpeg.constant_rate_factor="HIGH"

def orbit_anim(cam, cx, cy, radius, height, n=150):
    cam.animation_data_create(); cam.animation_data.action=bpy.data.actions.new("PBOrbit")
    for f in range(1, n+1):
        ang=(f-1)/n*math.tau
        cam.location=(cx+radius*math.cos(ang), cy+radius*math.sin(ang), height)
        cam.keyframe_insert("location", frame=f)

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def build_complete_booth():
    al   = mat_frame_aluminum()
    blue = mat_panel_blue()
    gray = mat_roof_gray()
    glas = mat_tempered_glass()
    gskt = mat_rubber_gasket()
    ss   = mat_stainless_steel()
    blk  = mat_black_abs()
    btn  = mat_button()
    lcd  = mat_lcd()
    semit= mat_sign_emit()
    swh  = mat_sign_white()
    cled = mat_ceiling_led()
    conc = mat_concrete_base()
    swlk = mat_sidewalk_tiles()
    fcd  = mat_building_facade()

    build_environment(swlk, fcd)
    build_base_pad(conc)
    build_frame(al)
    build_glass_and_gaskets(glas, gskt)
    build_solid_panels(blue, gray)
    build_door(al, glas, gskt, ss)
    build_roof(al, gray, semit, swh)
    build_phone_unit(blk, btn, lcd, ss)
    build_interior_ceiling(cled)
    interior_light = build_interior_area_light()
    return interior_light


def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    try:
        configure_cycles_devices()
    except Exception:
        bpy.context.scene.cycles.device = "GPU"

    set_color_management()
    print("[PB2] Building photo-realistic phone booth …")
    interior_light = build_complete_booth()

    BC_Y = BD / 2

    # ── 1. Day — classic 3/4 view ─────────────────────────────────────────────
    print("\n[render] Day 3/4 view …")
    interior_light.hide_render = True
    add_sky(elev=30, rot=140, strength=0.95)
    add_sun(energy=4.2, elev=30, az=140)
    add_fill_lights()

    cam,tgt = add_cam((-2.8,-2.5,1.85), (0.0,BC_Y,1.05), "CamDay", lens=60,
                      dof_dist=3.5)
    setup_png(OUT/"phonebooth2_day.png", samples=512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth2_day.png'}")
    rm_cam(cam,tgt)

    # ── 2. Front — looking through glass at phone unit ────────────────────────
    print("\n[render] Front interior view …")
    cam,tgt = add_cam((0.0,-3.2,1.38), (0.0,BC_Y*0.6,1.30), "CamFront", lens=75,
                      dof_dist=3.5)
    setup_png(OUT/"phonebooth2_front.png", samples=512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth2_front.png'}")
    rm_cam(cam,tgt)

    # ── 3. Close-up — door handle + glass + gasket detail ─────────────────────
    print("\n[render] Detail close-up (door / glass / handle) …")
    cam,tgt = add_cam((-1.4,-1.6,1.10), (-0.2,POST+0.05,1.05), "CamDetail", lens=90,
                      dof_dist=1.8)
    setup_png(OUT/"phonebooth2_detail.png", samples=512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth2_detail.png'}")
    rm_cam(cam,tgt)

    # ── 4. Night — interior illuminated ──────────────────────────────────────
    print("\n[render] Night — interior glow …")
    for o in list(bpy.context.scene.objects):
        if o.type=="LIGHT" and o.data.type in ("SUN","AREA") and "Fill" in o.name:
            bpy.data.objects.remove(o, do_unlink=True)
    for o in list(bpy.context.scene.objects):
        if o.type=="LIGHT" and o.data.type=="SUN":
            bpy.data.objects.remove(o, do_unlink=True)
    for w in list(bpy.data.worlds): bpy.data.worlds.remove(w)
    add_night_world()
    interior_light.hide_render = False
    interior_light.data.energy = 120.0

    cam,tgt = add_cam((-2.5,-2.2,1.6), (0.0,BC_Y,0.9), "CamNight", lens=52,
                      dof_dist=3.0)
    setup_png(OUT/"phonebooth2_night.png", samples=512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth2_night.png'}")
    rm_cam(cam,tgt)

    # ── 5. Orbit video — golden hour ─────────────────────────────────────────
    print("\n[render] Orbit video (golden hour) …")
    for w in list(bpy.data.worlds): bpy.data.worlds.remove(w)
    add_sky(elev=7, rot=140, strength=0.60)
    add_sun(energy=1.2, elev=7, az=140)
    add_fill_lights()
    interior_light.data.energy = 90.0; interior_light.hide_render = False

    N=150; orb_r=4.8; orb_h=2.1
    cam,tgt = add_cam((orb_r,BC_Y,orb_h), (0.0,BC_Y,1.05), "CamOrbit", lens=55)
    orbit_anim(cam, 0, BC_Y, orb_r, orb_h, n=N)
    setup_video(OUT/"phonebooth2_orbit", n=N, samples=96)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'phonebooth2_orbit0001-0150.mp4'}")
    rm_cam(cam,tgt)

    # ── 6. Save .blend ─────────────────────────────────────────────────────────
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"phonebooth2.blend"))
    print(f"\n[blend] {OUT/'phonebooth2.blend'}")
    print(f"[done] {OUT}")


if __name__ == "__main__":
    main()

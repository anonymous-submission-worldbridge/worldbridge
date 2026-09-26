#!/usr/bin/env python3
"""
phonebooth3_render.py — Photo-realistic British Red K6 Telephone Box (1935).
Giles Gilbert Scott design: GPO Red paint, dome roof, multi-pane glass, crown finial.
GPU: OPTIX→CUDA. Output: outputs/urban_v3_phonebooth3/
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

import math, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy, numpy as np
from mathutils import Vector

# ── GPU ───────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
prefs = bpy.context.preferences.addons["cycles"].preferences
for dev_type in ("OPTIX","CUDA","HIP","METAL"):
    try:
        prefs.compute_device_type = dev_type; prefs.get_devices()
        gpus = [d for d in prefs.devices if d.type!="CPU"]
        if gpus:
            for d in prefs.devices: d.use=True
            bpy.context.scene.cycles.device="GPU"
            print(f"[GPU] {dev_type}: {[d.name for d in gpus[:4]]}")
            break
    except: continue
print(f"[GPU] device={bpy.context.scene.cycles.device}")

OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_phonebooth3')
OUT.mkdir(parents=True, exist_ok=True)

# ── K6 Dimensions ─────────────────────────────────────────────────────────────
BW      = 0.865   # body face width (x & y, square plan)
BH      = 1.960   # body height (above base plinth)
BASE_H  = 0.095   # plinth step height
BASE_OV = 0.028   # plinth overhang
CP      = 0.044   # corner post cross-section
RT      = 0.050   # top rail height
RB      = 0.065   # bottom rail height
BAR_W   = 0.016   # glazing bar width
GLASS_T = 0.005   # glass pane thickness
SIGN_H  = 0.065   # "TELEPHONE" panel height
CORN_H  = 0.060   # cornice band height
CORN_OV = 0.032   # cornice overhang beyond body
DOME_H  = 0.345   # dome rise height
CROWN_H = 0.095   # crown finial height

# Derived Z positions (all above ground = 0)
Z_BODY_BOT = BASE_H
Z_BODY_TOP = BASE_H + BH
Z_WIN_BOT  = Z_BODY_BOT + RB
Z_WIN_TOP  = Z_BODY_TOP - RT - SIGN_H   # below sign panel
Z_CORN_TOP = Z_BODY_TOP + CORN_H
Z_DOME_TOP = Z_CORN_TOP + DOME_H

# Window grid: 2 cols × 4 rows
WIN_COLS = 2
WIN_ROWS = 4
WIN_H = Z_WIN_TOP - Z_WIN_BOT                  # ~1.73m
PANE_H = (WIN_H - (WIN_ROWS-1)*BAR_W) / WIN_ROWS  # ~0.43m
WIN_W  = BW - 2*CP                             # ~0.777m
PANE_W = (WIN_W - (WIN_COLS-1)*BAR_W) / WIN_COLS  # ~0.38m

# ── Geometry helpers ──────────────────────────────────────────────────────────
def _link(obj):
    if obj.name not in bpy.context.collection.objects:
        bpy.context.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj

def _deselect():
    bpy.ops.object.select_all(action="DESELECT")

def _sel(obj):
    _deselect(); obj.select_set(True)
    bpy.context.view_layer.objects.active = obj

def _nt(mat):
    mat.use_nodes=True; mat.node_tree.nodes.clear(); return mat.node_tree

def _lnk(nt,a,b): nt.links.new(a,b)

def shade_smooth(obj):
    _sel(obj); bpy.ops.object.shade_smooth()
    try: obj.data.use_auto_smooth=True; obj.data.auto_smooth_angle=math.radians(32)
    except: pass
    return obj

def add_bevel(obj, width=0.002, segs=3):
    bev=obj.modifiers.new("Bevel","BEVEL")
    bev.width=width; bev.segments=segs; bev.profile=0.70
    bev.limit_method="ANGLE"; bev.angle_limit=math.radians(30)
    bev.use_clamp_overlap=True
    return bev

def make_box(name, lx, ly, lz, cx=0., cy=0., cz=0., bev=None, smooth=True):
    x1,x2=cx-lx/2,cx+lx/2; y1,y2=cy-ly/2,cy+ly/2; z1,z2=cz-lz/2,cz+lz/2
    v=[(x1,y1,z1),(x2,y1,z1),(x2,y2,z1),(x1,y2,z1),
       (x1,y1,z2),(x2,y1,z2),(x2,y2,z2),(x1,y2,z2)]
    f=[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(v,[],f); mesh.update()
    obj=bpy.data.objects.new(name,mesh); _link(obj)
    if bev is not None: add_bevel(obj,bev)
    if smooth: shade_smooth(obj)
    return obj

def make_cylinder(name, r, h, n=32, cx=0,cy=0,cz=0):
    verts=[]; faces=[]
    for j in range(n):
        a=j/n*math.tau
        verts+=[(cx+r*math.cos(a),cy+r*math.sin(a),cz),
                (cx+r*math.cos(a),cy+r*math.sin(a),cz+h)]
    faces.append(tuple(range(0,2*n,2)))
    faces.append(tuple(reversed(range(1,2*n,2))))
    for j in range(n):
        jn=(j+1)%n; b,t,bn,tn=2*j,2*j+1,2*jn,2*jn+1
        faces.append((b,bn,tn,t))
    mesh=bpy.data.meshes.new(name); mesh.from_pydata(verts,[],faces); mesh.update()
    obj=bpy.data.objects.new(name,mesh); _link(obj); shade_smooth(obj); return obj

# ── Materials ─────────────────────────────────────────────────────────────────

def mat_k6_red(name="K6Red"):
    """GPO Telephone Red: satin paint on cast iron. Roughness ~0.55, subtle bumps."""
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise=nt.nodes.new("ShaderNodeTexNoise")
    bump=nt.nodes.new("ShaderNodeBump")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    # GPO red: slightly orange-warm, not pure primary red
    bsdf.inputs["Base Color"].default_value=(0.620,0.010,0.006,1.0)
    bsdf.inputs["Metallic"].default_value=0.0
    bsdf.inputs["Roughness"].default_value=0.55
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value=0.22
        bsdf.inputs["Coat Roughness"].default_value=0.18
    # Cast iron + paint orange-peel texture
    noise.inputs["Scale"].default_value=90.0
    noise.inputs["Detail"].default_value=10.0
    noise.inputs["Roughness"].default_value=0.55
    bump.inputs["Strength"].default_value=0.028
    bump.inputs["Distance"].default_value=0.0007
    _lnk(nt,coord.outputs["Generated"],noise.inputs["Vector"])
    _lnk(nt,noise.outputs["Fac"],bump.inputs["Height"])
    _lnk(nt,bump.outputs["Normal"],bsdf.inputs["Normal"])
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_k6_glass(name="K6Glass"):
    """Clear glass panes — slight smudge bump, green edge tint."""
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    glass=nt.nodes.new("ShaderNodeBsdfGlass")
    noise=nt.nodes.new("ShaderNodeTexNoise")
    bump=nt.nodes.new("ShaderNodeBump")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    volabs=nt.nodes.new("ShaderNodeVolumeAbsorption")
    glass.inputs["Color"].default_value=(0.90,0.96,0.92,1.0)
    glass.inputs["Roughness"].default_value=0.008
    glass.inputs["IOR"].default_value=1.517
    noise.inputs["Scale"].default_value=18.0; noise.inputs["Detail"].default_value=10.0
    bump.inputs["Strength"].default_value=0.015; bump.inputs["Distance"].default_value=0.0005
    volabs.inputs["Color"].default_value=(0.78,0.95,0.82,1.0)
    volabs.inputs["Density"].default_value=0.05
    _lnk(nt,coord.outputs["UV"],noise.inputs["Vector"])
    _lnk(nt,noise.outputs["Fac"],bump.inputs["Height"])
    _lnk(nt,bump.outputs["Normal"],glass.inputs["Normal"])
    _lnk(nt,glass.outputs["BSDF"],out.inputs["Surface"])
    _lnk(nt,volabs.outputs["Volume"],out.inputs["Volume"])
    return mat

def mat_sign_white(name="SignWhite"):
    """White enamel sign panel — warm cream-white."""
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value=(0.92,0.88,0.82,1.0)
    bsdf.inputs["Roughness"].default_value=0.38
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value=0.30
        bsdf.inputs["Coat Roughness"].default_value=0.12
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_sign_text(name="SignText"):
    """Raised letter face on sign — dark red-black."""
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value=(0.050,0.002,0.002,1.0)
    bsdf.inputs["Roughness"].default_value=0.65
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_black_interior(name="BlackInt"):
    """Interior flat black paint."""
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value=(0.012,0.012,0.012,1.0)
    bsdf.inputs["Roughness"].default_value=0.90
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_bakelite(name="Bakelite"):
    """Black Bakelite phone handset."""
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.inputs["Base Color"].default_value=(0.018,0.014,0.014,1.0)
    bsdf.inputs["Roughness"].default_value=0.45
    if "Coat Weight" in bsdf.inputs:
        bsdf.inputs["Coat Weight"].default_value=0.35
        bsdf.inputs["Coat Roughness"].default_value=0.20
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_interior_led(name="IntLED"):
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    emit=nt.nodes.new("ShaderNodeEmission")
    emit.inputs["Color"].default_value=(1.0,0.96,0.88,1.0)
    emit.inputs["Strength"].default_value=6.0
    _lnk(nt,emit.outputs["Emission"],out.inputs["Surface"])
    return mat

def mat_granite_base(name="Granite"):
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise=nt.nodes.new("ShaderNodeTexNoise")
    ramp=nt.nodes.new("ShaderNodeValToRGB")
    bump=nt.nodes.new("ShaderNodeBump")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value=14.0; noise.inputs["Detail"].default_value=12.0
    ramp.color_ramp.elements[0].color=(0.28,0.26,0.25,1.0)
    ramp.color_ramp.elements[1].color=(0.50,0.48,0.46,1.0)
    bump.inputs["Strength"].default_value=0.18; bump.inputs["Distance"].default_value=0.003
    bsdf.inputs["Roughness"].default_value=0.82
    _lnk(nt,coord.outputs["Generated"],noise.inputs["Vector"])
    _lnk(nt,noise.outputs["Fac"],ramp.inputs["Fac"])
    _lnk(nt,ramp.outputs["Color"],bsdf.inputs["Base Color"])
    _lnk(nt,noise.outputs["Fac"],bump.inputs["Height"])
    _lnk(nt,bump.outputs["Normal"],bsdf.inputs["Normal"])
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_pavement(name="Pavement"):
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    brick=nt.nodes.new("ShaderNodeTexBrick")
    bump=nt.nodes.new("ShaderNodeBump")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    mp=nt.nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value=(0.30,0.30,1.0)
    brick.inputs["Scale"].default_value=1.0
    brick.inputs["Mortar Size"].default_value=0.04
    brick.inputs["Mortar Smooth"].default_value=0.1
    brick.inputs["Color1"].default_value=(0.48,0.46,0.42,1.0)
    brick.inputs["Color2"].default_value=(0.54,0.52,0.48,1.0)
    brick.inputs["Mortar"].default_value=(0.28,0.26,0.24,1.0)
    bump.inputs["Strength"].default_value=0.14; bump.inputs["Distance"].default_value=0.003
    bsdf.inputs["Roughness"].default_value=0.88
    _lnk(nt,coord.outputs["Generated"],mp.inputs["Vector"])
    _lnk(nt,mp.outputs["Vector"],brick.inputs["Vector"])
    _lnk(nt,brick.outputs["Color"],bsdf.inputs["Base Color"])
    _lnk(nt,brick.outputs["Fac"],bump.inputs["Height"])
    _lnk(nt,bump.outputs["Normal"],bsdf.inputs["Normal"])
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def mat_stone_facade(name="StoneFacade"):
    mat=bpy.data.materials.new(name); nt=_nt(mat)
    out=nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise=nt.nodes.new("ShaderNodeTexNoise")
    ramp=nt.nodes.new("ShaderNodeValToRGB")
    bump=nt.nodes.new("ShaderNodeBump")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value=6.0; noise.inputs["Detail"].default_value=10.0
    ramp.color_ramp.elements[0].color=(0.52,0.48,0.42,1.0)
    ramp.color_ramp.elements[1].color=(0.68,0.64,0.58,1.0)
    bump.inputs["Strength"].default_value=0.22; bump.inputs["Distance"].default_value=0.006
    bsdf.inputs["Roughness"].default_value=0.88
    _lnk(nt,coord.outputs["Generated"],noise.inputs["Vector"])
    _lnk(nt,noise.outputs["Fac"],ramp.inputs["Fac"])
    _lnk(nt,ramp.outputs["Color"],bsdf.inputs["Base Color"])
    _lnk(nt,noise.outputs["Fac"],bump.inputs["Height"])
    _lnk(nt,bump.outputs["Normal"],bsdf.inputs["Normal"])
    _lnk(nt,bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

# ── Booth construction ─────────────────────────────────────────────────────────

def build_base_plinth(granite_mat):
    """Stepped concrete/granite base."""
    pw = BW + 2*BASE_OV
    plinth = make_box("K6_Base", pw, pw, BASE_H, cx=0, cy=BW/2, cz=BASE_H/2, bev=0.004)
    plinth.data.materials.append(granite_mat)
    return plinth


def build_frame(red_mat, bev=0.002):
    """4 corner posts + top rails + bottom rails (all K6-red)."""
    objs=[]
    px = BW/2 - CP/2   # corner post centre x (±)
    py = CP/2           # front posts centre y
    pyb= BW - CP/2      # back posts centre y

    # Corner posts: z from body bottom to body top
    z_ctr = Z_BODY_BOT + BH/2
    for xi,yi in [(-px,py),(px,py),(px,pyb),(-px,pyb)]:
        p=make_box("K6_Post",CP,CP,BH,cx=xi,cy=yi,cz=z_ctr,bev=bev)
        p.data.materials.append(red_mat); objs.append(p)

    # Top rails (just below body top, running along each face)
    z_tr = Z_BODY_TOP - RT/2
    rail_len = BW - 2*CP + 0.005
    for tag,cx,cy,lx,ly in [
        ("FT", 0,     py,   rail_len, CP),
        ("BT", 0,     pyb,  rail_len, CP),
        ("LT",-px+CP/2, BW/2,CP,    rail_len),
        ("RT", px-CP/2, BW/2,CP,    rail_len),
    ]:
        r=make_box(f"K6_RailTop{tag}",lx,ly,RT,cx=cx,cy=cy,cz=z_tr,bev=bev)
        r.data.materials.append(red_mat); objs.append(r)

    # Bottom rails (just above body bottom)
    z_br = Z_BODY_BOT + RB/2
    for tag,cx,cy,lx,ly in [
        ("FB", 0,     py,   rail_len, CP),
        ("BB", 0,     pyb,  rail_len, CP),
        ("LB",-px+CP/2, BW/2,CP,    rail_len),
        ("RB", px-CP/2, BW/2,CP,    rail_len),
    ]:
        r=make_box(f"K6_RailBot{tag}",lx,ly,RB,cx=cx,cy=cy,cz=z_br,bev=bev)
        r.data.materials.append(red_mat); objs.append(r)
    return objs


def build_windows_one_face(tag, glass_cx, glass_cy, glass_plane,
                           win_cx, bar_dir,
                           red_mat, glass_mat, bev=0.0008):
    """
    Build the glass panes + glazing bars for ONE face.
    glass_plane: 'x' or 'y' — which axis the face is perpendicular to
    glass_cx/cy: centre position of the glass on that face
    win_cx: centre x of window opening (for bar placement)
    bar_dir: 'x' (front/back face) or 'y' (left/right face)
    """
    objs=[]
    # ── Glass panes (2 cols × 4 rows) ──
    for row in range(WIN_ROWS):
        for col in range(WIN_COLS):
            # pane centre Z
            pz = Z_WIN_BOT + (row+0.5)*PANE_H + row*BAR_W
            # pane centre along face (x or y)
            offset = -WIN_W/2 + (col+0.5)*PANE_W + col*BAR_W

            if glass_plane=='y':
                # front/back faces: x varies, y fixed
                gx = win_cx + offset
                gy = glass_cy
                pane=make_box(f"K6_Glass{tag}r{row}c{col}",
                              PANE_W, GLASS_T, PANE_H,
                              cx=gx, cy=gy, cz=pz, bev=None, smooth=False)
            else:
                # left/right faces: y varies, x fixed
                gy = BW/2 + offset
                gx = glass_cx
                pane=make_box(f"K6_Glass{tag}r{row}c{col}",
                              GLASS_T, PANE_W, PANE_H,
                              cx=gx, cy=gy, cz=pz, bev=None, smooth=False)
            pane.data.materials.append(glass_mat); objs.append(pane)

    # ── Horizontal glazing bars (WIN_ROWS-1 = 3 bars between rows) ──
    bar_z_list = [Z_WIN_BOT + (r+1)*PANE_H + (r+0.5)*BAR_W for r in range(WIN_ROWS-1)]
    bar_len = WIN_W - 0.002
    for i,bz in enumerate(bar_z_list):
        if glass_plane=='y':
            b=make_box(f"K6_HBar{tag}{i}",bar_len,CP*0.6,BAR_W,
                       cx=win_cx,cy=glass_cy,cz=bz,bev=bev)
        else:
            b=make_box(f"K6_HBar{tag}{i}",CP*0.6,bar_len,BAR_W,
                       cx=glass_cx,cy=BW/2,cz=bz,bev=bev)
        b.data.materials.append(red_mat); objs.append(b)

    # ── Central vertical glazing bar ──
    vbar_h = WIN_H + BAR_W*0.5
    vbar_z = (Z_WIN_BOT + Z_WIN_TOP) / 2
    if glass_plane=='y':
        vb=make_box(f"K6_VBar{tag}",BAR_W,CP*0.6,vbar_h,
                    cx=win_cx,cy=glass_cy,cz=vbar_z,bev=bev)
    else:
        vb=make_box(f"K6_VBar{tag}",CP*0.6,BAR_W,vbar_h,
                    cx=glass_cx,cy=BW/2,cz=vbar_z,bev=bev)
    vb.data.materials.append(red_mat); objs.append(vb)
    return objs


def build_all_windows(red_mat, glass_mat):
    objs=[]
    # Front face (y=0 side) — DOOR, skip window panes (door built separately)
    # Back face (y=BW)
    objs += build_windows_one_face("Back",
        glass_cx=0, glass_cy=BW - CP/2 + GLASS_T/2,
        glass_plane='y', win_cx=0, bar_dir='y',
        red_mat=red_mat, glass_mat=glass_mat)
    # Left face (x=-BW/2)
    objs += build_windows_one_face("Left",
        glass_cx=-BW/2 + CP/2 - GLASS_T/2, glass_cy=BW/2,
        glass_plane='x', win_cx=0, bar_dir='x',
        red_mat=red_mat, glass_mat=glass_mat)
    # Right face (x=BW/2)
    objs += build_windows_one_face("Right",
        glass_cx= BW/2 - CP/2 + GLASS_T/2, glass_cy=BW/2,
        glass_plane='x', win_cx=0, bar_dir='x',
        red_mat=red_mat, glass_mat=glass_mat)
    return objs


def build_door(red_mat, glass_mat, bev=0.002):
    """Front face door: glass panes + handle ring."""
    objs=[]
    # Door glass (2 cols × 4 rows, same as windows)
    # Glass sits at y = CP/2 - GLASS_T/2 (just behind front face of posts)
    gy = CP/2 - GLASS_T/2
    for row in range(WIN_ROWS):
        for col in range(WIN_COLS):
            pz = Z_WIN_BOT + (row+0.5)*PANE_H + row*BAR_W
            gx = -WIN_W/2 + (col+0.5)*PANE_W + col*BAR_W
            pane=make_box(f"K6_DoorGlass_{row}_{col}",
                          PANE_W, GLASS_T, PANE_H, cx=gx, cy=gy, cz=pz,
                          bev=None, smooth=False)
            pane.data.materials.append(glass_mat); objs.append(pane)

    # Horizontal glazing bars on door
    for i,bz in enumerate([Z_WIN_BOT + (r+1)*PANE_H + (r+0.5)*BAR_W for r in range(WIN_ROWS-1)]):
        b=make_box(f"K6_DoorHBar{i}",WIN_W-0.002,CP*0.6,BAR_W,cx=0,cy=gy,cz=bz,bev=bev)
        b.data.materials.append(red_mat); objs.append(b)

    # Central vertical bar
    vb=make_box("K6_DoorVBar",BAR_W,CP*0.6,WIN_H,cx=0,cy=gy,cz=(Z_WIN_BOT+Z_WIN_TOP)/2,bev=bev)
    vb.data.materials.append(red_mat); objs.append(vb)

    # Door handle: ring pull (D-shape using swept tube)
    import math as _m
    handle_z = Z_BODY_BOT + BH * 0.48
    # D-ring: flat ring of radius 0.04, at x=+BW/4, y=0 (front face)
    handle_x = BW * 0.28
    n_seg = 16
    ring_r = 0.042
    ring_pts = []
    for j in range(n_seg+1):
        a = -_m.pi/2 + j/n_seg * _m.pi  # semicircle on +x side
        ring_pts.append((handle_x + ring_r*_m.cos(a), CP/2 - 0.018, handle_z + ring_r*_m.sin(a)))
    # vertical bar connecting ends
    ring_pts_full = ring_pts

    ring_verts=[]; ring_faces=[]; ring_n=10
    def perp(t):
        tv=Vector(t).normalized()
        ref=Vector((0,0,1)) if abs(tv.z)<0.9 else Vector((1,0,0))
        r=tv.cross(ref).normalized(); u=tv.cross(r).normalized()
        return r,u
    rings=[]
    for i,pt in enumerate(ring_pts_full):
        tang=(Vector(ring_pts_full[i+1])-Vector(pt)) if i<len(ring_pts_full)-1 else (Vector(pt)-Vector(ring_pts_full[i-1]))
        r,u=perp(tang); s=len(ring_verts); rings.append(s)
        for j in range(ring_n):
            a=j/ring_n*_m.tau
            ring_verts.append(tuple(Vector(pt)+r*0.012*_m.cos(a)+u*0.012*_m.sin(a)))
    for k in range(len(rings)-1):
        s0,s1=rings[k],rings[k+1]
        for j in range(ring_n):
            jn=(j+1)%ring_n
            ring_faces.append((s0+j,s0+jn,s1+jn,s1+j))
    mesh=bpy.data.meshes.new("K6_Handle"); mesh.from_pydata(ring_verts,[],ring_faces); mesh.update()
    handle=bpy.data.objects.new("K6_Handle",mesh); _link(handle)
    shade_smooth(handle)
    handle.data.materials.append(red_mat); objs.append(handle)
    return objs


def build_sign_panels(red_mat, white_mat, text_mat, bev=0.0015):
    """TELEPHONE sign panel on all 4 faces + crown device."""
    objs=[]
    z_sign = Z_BODY_TOP - RT - SIGN_H/2
    panel_w = BW - 2*CP - 0.004

    # Front face sign (facing -y)
    for tag,cx,cy,lx,ly in [
        ("F",  0,      CP/2 - 0.005,           panel_w, 0.010),
        ("B",  0,      BW - CP/2 + 0.005,       panel_w, 0.010),
        ("L", -BW/2 + CP/2 - 0.005, BW/2,   0.010, panel_w),
        ("R",  BW/2 - CP/2 + 0.005, BW/2,   0.010, panel_w),
    ]:
        # White enamel sign panel
        sp=make_box(f"K6_Sign{tag}",lx,ly,SIGN_H,cx=cx,cy=cy,cz=z_sign,bev=bev)
        sp.data.materials.append(white_mat); objs.append(sp)

        # "TELEPHONE" text bar — dark raised letters suggestion
        tw = lx*0.70 if ly < lx else ly*0.70
        th = 0.010
        if ly < lx:  # front/back faces: text runs in x
            tb=make_box(f"K6_Text{tag}",tw,ly*1.2,th,cx=cx,cy=cy,cz=z_sign+0.004)
        else:  # side faces: text runs in y
            tb=make_box(f"K6_Text{tag}",lx*1.2,tw,th,cx=cx,cy=cy,cz=z_sign+0.004)
        tb.data.materials.append(text_mat); objs.append(tb)

    # Crown device on top of each sign (small ornamental bar + ball)
    z_crown_device = Z_BODY_TOP - RT/2
    for tag,cx,cy,lx,ly in [
        ("F",0,  CP/2-0.005,     panel_w*0.30, 0.009),
        ("B",0,  BW-CP/2+0.005, panel_w*0.30, 0.009),
        ("L",-BW/2+CP/2-0.005, BW/2, 0.009, panel_w*0.30),
        ("R", BW/2-CP/2+0.005, BW/2, 0.009, panel_w*0.30),
    ]:
        cr=make_box(f"K6_CrownD{tag}",lx,ly,0.018,cx=cx,cy=cy,cz=z_crown_device,bev=bev)
        cr.data.materials.append(red_mat); objs.append(cr)
    return objs


def build_cornice(red_mat, bev=0.003):
    """Overhanging ledge between body and dome."""
    objs=[]
    cw = BW + 2*CORN_OV
    z_cc = Z_BODY_TOP + CORN_H/2
    # Main cornice ring (one box for each side, slightly larger than body)
    cornice = make_box("K6_Cornice", cw, cw, CORN_H, cx=0, cy=BW/2, cz=z_cc, bev=bev)
    cornice.data.materials.append(red_mat); objs.append(cornice)
    return objs


def build_dome(red_mat):
    """
    Dome top: parametric mesh using superelliptic height profile.
    Creates a low barrel-vault that tapers to a flat top (K6 characteristic shape).
    """
    n_u, n_v = 28, 28
    cw = BW + 2*CORN_OV   # dome base width = cornice width
    h_base = Z_CORN_TOP
    h_peak = Z_DOME_TOP

    verts=[]; faces=[]
    for i in range(n_v+1):
        v = i/n_v  # 0=front-edge, 1=back-edge
        ny = 2*v - 1  # -1 to +1 (centred)
        for j in range(n_u+1):
            u = j/n_u
            nx = 2*u - 1  # -1 to +1 (centred)
            # Superelliptic radius: p=2 → circular, p=4 → squarish
            p = 3.0
            r = (abs(nx)**p + abs(ny)**p)**(1/p)
            r = min(r, 1.0)
            # Height: peak at centre, tapers to h_base at edges
            # Use smooth cosine falloff for the dome curve
            z = h_base + (h_peak - h_base) * (1 - r) * (0.5 + 0.5*math.cos(r*math.pi))

            x = nx * cw/2
            y = BW/2 + ny * cw/2
            verts.append((x, y, z))

    for i in range(n_v):
        for j in range(n_u):
            a=i*(n_u+1)+j; b=a+1; c=(i+1)*(n_u+1)+j+1; d=(i+1)*(n_u+1)+j
            faces.append((a,b,c,d))

    mesh=bpy.data.meshes.new("K6_Dome"); mesh.from_pydata(verts,[],faces); mesh.update()
    obj=bpy.data.objects.new("K6_Dome",mesh); _link(obj); shade_smooth(obj)

    # Solidify for 5mm aluminium shell thickness
    solid=obj.modifiers.new("Solidify","SOLIDIFY")
    solid.thickness=-0.006; solid.offset=1.0

    add_bevel(obj, width=0.003, segs=2)
    obj.data.materials.append(red_mat)
    return obj


def build_flat_top(red_mat, bev=0.003):
    """Small flat rectangular pad at dome apex (characteristic K6 feature)."""
    fw = BW * 0.22
    ft = make_box("K6_FlatTop", fw, fw, 0.025, cx=0, cy=BW/2, cz=Z_DOME_TOP+0.012, bev=bev)
    ft.data.materials.append(red_mat)
    return ft


def build_crown_finial(red_mat, bev=0.002):
    """
    Crown finial: base cylinder + 4 arched ribs + small sphere on top.
    Classic K6 crown device silhouette.
    """
    objs=[]
    z0 = Z_DOME_TOP + 0.025  # top of flat pad
    R  = 0.025   # crown base radius
    ch = CROWN_H

    # Base cylinder (thick octagonal)
    base=make_cylinder("K6_CrownBase", R, 0.032, n=8, cx=0, cy=BW/2, cz=z0)
    base.data.materials.append(red_mat); objs.append(base)

    # 4 curved arch ribs forming the crown shape
    for angle_deg in (0, 45, 90, 135):
        a = math.radians(angle_deg)
        rib_pts=[]
        for t in range(9):
            tt = t/8
            # Rib goes from base up in a curve, meeting at top
            ra = R * (1 - tt) * 0.8 + 0.004
            rz = z0 + 0.030 + tt * (ch - 0.030)
            rx = math.cos(a) * ra
            ry = math.sin(a) * ra
            rib_pts.append((rx, BW/2 + ry, rz))
        # Create tube for rib
        rib_verts=[]; rib_faces=[]; ring_n=8
        def perp2(t):
            tv=Vector(t).normalized()
            ref=Vector((0,0,1)) if abs(tv.z)<0.9 else Vector((0,1,0))
            r=tv.cross(ref).normalized(); u=tv.cross(r).normalized()
            return r,u
        rings=[]
        for i,pt in enumerate(rib_pts):
            tang=(Vector(rib_pts[i+1])-Vector(pt)) if i<len(rib_pts)-1 else (Vector(pt)-Vector(rib_pts[i-1]))
            r,u=perp2(tang); s=len(rib_verts); rings.append(s)
            for j in range(ring_n):
                aa=j/ring_n*math.tau
                rib_verts.append(tuple(Vector(pt)+r*0.008*math.cos(aa)+u*0.008*math.sin(aa)))
        for k in range(len(rings)-1):
            s0,s1=rings[k],rings[k+1]
            for j in range(ring_n):
                jn=(j+1)%ring_n
                rib_faces.append((s0+j,s0+jn,s1+jn,s1+j))
        rm=bpy.data.meshes.new(f"K6_Rib{angle_deg}")
        rm.from_pydata(rib_verts,[],rib_faces); rm.update()
        ro=bpy.data.objects.new(f"K6_Rib{angle_deg}",rm); _link(ro); shade_smooth(ro)
        ro.data.materials.append(red_mat); objs.append(ro)

    # Top sphere (orb)
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.022, location=(0, BW/2, z0+ch))
    orb=bpy.context.active_object; orb.name="K6_Orb"
    shade_smooth(orb); orb.data.materials.append(red_mat); objs.append(orb)
    return objs


def build_interior(black_mat, bak_mat, led_mat):
    """Visible interior: black back wall, bakelite phone, LED strip."""
    objs=[]
    # Interior back wall
    bwall=make_box("K6_IntWall", BW-2*CP-0.010, 0.006, BH-RT-RB-0.010,
                   cx=0, cy=BW-CP/2-0.004,
                   cz=Z_BODY_BOT+RB+(BH-RT-RB)/2)
    bwall.data.materials.append(black_mat); objs.append(bwall)

    # Interior floor
    ifloor=make_box("K6_IntFloor", BW-2*CP-0.010, BW-2*CP-0.010, 0.006,
                    cx=0, cy=BW/2, cz=Z_BODY_BOT+RB/2)
    ifloor.data.materials.append(black_mat); objs.append(ifloor)

    # Bakelite telephone body (against back wall)
    phone_z = Z_BODY_BOT + BH*0.55
    phone=make_box("K6_Phone", 0.200, 0.150, 0.120,
                   cx=0, cy=BW-CP-0.090, cz=phone_z, bev=0.012)
    phone.data.materials.append(bak_mat); objs.append(phone)

    # Handset on cradle
    hs=make_box("K6_Handset", 0.185, 0.050, 0.035,
                cx=0, cy=BW-CP-0.065, cz=phone_z+0.070, bev=0.010)
    hs.data.materials.append(bak_mat); objs.append(hs)

    # LED ceiling strip
    ls=make_box("K6_LedStrip", 0.400, 0.200, 0.010,
                cx=0, cy=BW/2, cz=Z_BODY_TOP-RT-0.008)
    ls.data.materials.append(led_mat); objs.append(ls)
    return objs


def build_interior_area_light():
    bpy.ops.object.light_add(type="AREA", location=(0, BW/2, Z_BODY_TOP-RT-0.10))
    lt=bpy.context.active_object; lt.name="K6_IntLight"
    lt.data.energy=55.0; lt.data.color=(1.0,0.94,0.82)
    lt.data.size=0.50; lt.data.size_y=0.40
    lt.data.spread=math.radians(165)
    lt.rotation_euler=(math.pi,0,0)
    return lt


def build_environment(pave_mat, stone_mat):
    bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0, 8.0, -0.002))
    sw=bpy.context.active_object; sw.name="K6_Pavement"
    sw.data.materials.append(pave_mat)
    facade=make_box("K6_Facade", 18.0, 0.28, 9.0, cx=0, cy=BW+3.5, cz=4.5)
    facade.data.materials.append(stone_mat)
    return sw, facade


# ── Scene / render helpers ─────────────────────────────────────────────────────

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes,bpy.data.materials,bpy.data.cameras,
                bpy.data.lights,bpy.data.curves):
        for blk in list(col):
            try: col.remove(blk)
            except: pass

def set_color_management():
    vs=bpy.context.scene.view_settings
    for vt in ("AgX","Filmic"):
        try: vs.view_transform=vt; break
        except: pass
    vs.look="None"; vs.exposure=0.0; vs.gamma=1.0

def add_sky(elev=32, rot=155, strength=0.92):
    world=bpy.data.worlds.new("World"); bpy.context.scene.world=world
    world.use_nodes=True; nt=world.node_tree; nt.nodes.clear()
    bg=nt.nodes.new("ShaderNodeBackground")
    sky=nt.nodes.new("ShaderNodeTexSky")
    out=nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type="NISHITA"; sky.sun_elevation=math.radians(elev)
    sky.sun_rotation=math.radians(rot); sky.altitude=40.0
    sky.air_density=1.0; sky.dust_density=0.8
    bg.inputs["Strength"].default_value=strength
    nt.links.new(sky.outputs["Color"],bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"],out.inputs["Surface"])

def add_night_world():
    world=bpy.data.worlds.new("World"); bpy.context.scene.world=world
    world.use_nodes=True; nt=world.node_tree; nt.nodes.clear()
    bg=nt.nodes.new("ShaderNodeBackground"); out=nt.nodes.new("ShaderNodeOutputWorld")
    bg.inputs["Color"].default_value=(0.002,0.005,0.012,1.0)
    bg.inputs["Strength"].default_value=0.6
    nt.links.new(bg.outputs["Background"],out.inputs["Surface"])

def add_sun(energy=4.5, elev=32, az=155):
    bpy.ops.object.light_add(type="SUN", location=(0,0,20))
    s=bpy.context.active_object; s.data.energy=energy
    s.data.angle=math.radians(0.53)
    s.rotation_euler=(math.radians(90-elev),0,math.radians(az))
    return s

def add_fills():
    for x,y,z,name in [(-7, BW/2+1, 4.0,"FillL"),(7, BW/2+1, 4.0,"FillR")]:
        bpy.ops.object.light_add(type="AREA", location=(x,y,z))
        lt=bpy.context.active_object; lt.name=name
        lt.data.energy=40.0; lt.data.color=(0.75,0.85,1.0)
        lt.data.size=3.5; lt.data.size_y=3.5

def add_cam(loc, target, name="Cam", lens=60, dof=None):
    bpy.ops.object.camera_add(location=loc)
    cam=bpy.context.active_object; cam.name=name; cam.data.lens=lens
    bpy.context.scene.camera=cam
    bpy.ops.object.empty_add(type="PLAIN_AXES",location=target)
    tgt=bpy.context.active_object; tgt.name=name+"_tgt"
    tc=cam.constraints.new("TRACK_TO")
    tc.target=tgt; tc.track_axis="TRACK_NEGATIVE_Z"; tc.up_axis="UP_Y"
    if dof:
        cam.data.dof.use_dof=True; cam.data.dof.focus_distance=dof
        cam.data.dof.aperture_fstop=4.5
    return cam,tgt

def rm_cam(cam,tgt):
    bpy.data.objects.remove(cam,do_unlink=True)
    bpy.data.objects.remove(tgt,do_unlink=True)

def enable_denoiser():
    for d in ("OPTIX","OPENIMAGEDENOISE"):
        try: bpy.context.scene.cycles.denoiser=d; return
        except: pass

def setup_png(fp, samples=512, rx=1920, ry=1080):
    sc=bpy.context.scene
    sc.cycles.samples=samples; sc.cycles.use_denoising=True
    enable_denoiser()
    sc.cycles.max_bounces=12; sc.cycles.transmission_bounces=10
    sc.cycles.caustics_refractive=False
    sc.render.resolution_x=rx; sc.render.resolution_y=ry
    sc.render.image_settings.file_format="PNG"
    sc.render.filepath=str(fp)

def setup_video(fp, n=150, fps=25, samples=96, rx=1920, ry=1080):
    sc=bpy.context.scene; sc.frame_start=1; sc.frame_end=n; sc.render.fps=fps
    setup_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format="FFMPEG"
    sc.render.ffmpeg.format="MPEG4"; sc.render.ffmpeg.codec="H264"
    sc.render.ffmpeg.constant_rate_factor="HIGH"

def orbit_anim(cam, cx, cy, r, h, n=150):
    cam.animation_data_create()
    cam.animation_data.action=bpy.data.actions.new("K6Orbit")
    for f in range(1,n+1):
        a=(f-1)/n*math.tau
        cam.location=(cx+r*math.cos(a), cy+r*math.sin(a), h)
        cam.keyframe_insert("location", frame=f)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    clear_scene()
    bpy.context.scene.render.engine="CYCLES"
    bpy.context.scene.cycles.device="GPU"
    set_color_management()

    print("[K6] Building materials …")
    red   = mat_k6_red()
    glass = mat_k6_glass()
    white = mat_sign_white()
    text  = mat_sign_text()
    black = mat_black_interior()
    bak   = mat_bakelite()
    led   = mat_interior_led()
    gran  = mat_granite_base()
    pave  = mat_pavement()
    stone = mat_stone_facade()

    print("[K6] Building booth …")
    build_base_plinth(gran)
    build_frame(red)
    build_all_windows(red, glass)
    build_door(red, glass)
    build_sign_panels(red, white, text)
    build_cornice(red)
    build_dome(red)
    build_flat_top(red)
    build_crown_finial(red)
    build_interior(black, bak, led)
    int_light = build_interior_area_light()
    build_environment(pave, stone)

    CX, CY = 0.0, BW/2

    # ── 1. Day classic 3/4 view ───────────────────────────────────────────────
    print("\n[render] Day 3/4 view …")
    int_light.hide_render=True
    add_sky(elev=35, rot=150); add_sun(energy=4.2, elev=35, az=150); add_fills()
    cam,tgt=add_cam((-2.5,-2.4,1.80),(0.0,BW/2,1.10),"CamDay",lens=58,dof=3.2)
    setup_png(OUT/"phonebooth3_day.png", 512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth3_day.png'}")
    rm_cam(cam,tgt)

    # ── 2. Front view — shows door + glass panes ──────────────────────────────
    print("\n[render] Front view …")
    cam,tgt=add_cam((0.0,-3.0,1.30),(0.0,BW/2*0.4,1.20),"CamFront",lens=75,dof=3.2)
    setup_png(OUT/"phonebooth3_front.png", 512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth3_front.png'}")
    rm_cam(cam,tgt)

    # ── 3. Crown + dome detail ────────────────────────────────────────────────
    print("\n[render] Crown/dome detail …")
    cam,tgt=add_cam((-1.8,-1.6,2.35),(0.0,BW/2,2.05),"CamDome",lens=85,dof=2.5)
    setup_png(OUT/"phonebooth3_dome.png", 512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth3_dome.png'}")
    rm_cam(cam,tgt)

    # ── 4. Night — interior glowing ───────────────────────────────────────────
    print("\n[render] Night interior glow …")
    for o in list(bpy.context.scene.objects):
        if o.type=="LIGHT" and o.name in ("FillL","FillR") or (o.type=="LIGHT" and o.data.type=="SUN"):
            bpy.data.objects.remove(o,do_unlink=True)
    for w in list(bpy.data.worlds): bpy.data.worlds.remove(w)
    add_night_world()
    int_light.hide_render=False; int_light.data.energy=110.0
    cam,tgt=add_cam((-2.2,-2.0,1.55),(0.0,BW/2,0.95),"CamNight",lens=55,dof=2.8)
    setup_png(OUT/"phonebooth3_night.png", 512)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'phonebooth3_night.png'}")
    rm_cam(cam,tgt)

    # ── 5. Orbit video ────────────────────────────────────────────────────────
    print("\n[render] Orbit video (150 frames) …")
    for w in list(bpy.data.worlds): bpy.data.worlds.remove(w)
    add_sky(elev=8, rot=150, strength=0.55); add_sun(energy=1.1, elev=8, az=150); add_fills()
    int_light.hide_render=False; int_light.data.energy=80.0
    N=150; OR=4.5; OH=1.95
    cam,tgt=add_cam((OR,CY,OH),(CX,CY,1.15),"CamOrbit",lens=55)
    orbit_anim(cam,CX,CY,OR,OH,n=N)
    setup_video(OUT/"phonebooth3_orbit", n=N, samples=96)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'phonebooth3_orbit0001-0150.mp4'}")
    rm_cam(cam,tgt)

    # ── 6. Save .blend ────────────────────────────────────────────────────────
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"phonebooth3.blend"))
    print(f"\n[blend] {OUT/'phonebooth3.blend'}")
    print(f"[done] {OUT}")


if __name__ == "__main__":
    main()

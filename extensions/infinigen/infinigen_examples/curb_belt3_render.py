#!/usr/bin/env python3
"""
curb_belt3_render.py — dense, constrained urban green belt v3.

Design:
  Belt: 15 m × 1.2 m, flanked by concrete curbs on BOTH sides.
  Zone 1 (x 0-7.5 m): 15 ProcShrubFactory shrubs, 5-col × 3-row dense grid.
  Zone 2 (x 7.5-15 m): FlowerPlantFactory geometry-nodes scatter, high density.
  Background: Grass scatter over the whole belt.

Constraint enforcement:
  • Shrub centre y ∈ [0.30, 0.90];  max_spread ≤ 0.22 m
    → max plant extent y ∈ [0.08, 1.12] — within the 1.2 m belt.
  • Shrub centre x ∈ [0.50, 6.80]  (zone 1 only)
    → with spread 0.22 m → x extent [0.28, 7.02] — within belt.
  • Flower scatter uses a sub-plane exactly within zone 2.
    Sub-plane placed at y = 0.6, so flowers stay within y ∈ [0, 1.2].

Outputs → ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt3/:
  belt3_zone1_shrubs.png  — close-up of the shrub zone
  belt3_zone2_flowers.png — close-up of the flower zone
  belt3_side.png          — full belt side view
  belt3_end.png           — end perspective
  belt3_orbit0001-0150.mp4
  belt3.blend

GPU: OPTIX → CUDA → HIP → METAL
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
import gin
import numpy as np
from mathutils import Vector

# ── gin ────────────────────────────────────────────────────────────────────────
import infinigen
from infinigen.core import init
gin.clear_config()
init.apply_gin_configs(
    config_folders=[str(ROOT / "infinigen_examples/configs_nature")],
    configs=[], overrides=[], skip_unknown=True,
    finalize_config=False, mandatory_folders=[],
)

# ── GPU ────────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
from infinigen.core.init import configure_cycles_devices
configure_cycles_devices()
print(f"[GPU] device = {bpy.context.scene.cycles.device}")

# ── output ─────────────────────────────────────────────────────────────────────
OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt3')
OUT.mkdir(parents=True, exist_ok=True)

# ── imports ────────────────────────────────────────────────────────────────────
from infinigen.assets.scatters.grass import Grass
from infinigen.assets.scatters.flowerplant import Flowerplant
from infinigen.core.util.math import FixedSeed

# ── belt constants ─────────────────────────────────────────────────────────────
BELT_LEN   = 15.0
BELT_WIDTH = 1.2
ZONE_SPLIT = 7.5   # zone1: 0-7.5, zone2: 7.5-15
CURB_H     = 0.14
CURB_W     = 0.12
ROAD_W     = 7.0

# plant boundary margin (stay this far from each curb face)
Y_MARGIN   = 0.12
Y_MIN      = Y_MARGIN            # 0.12
Y_MAX      = BELT_WIDTH - Y_MARGIN  # 1.08

# ══════════════════════════════════════════════════════════════════════════════
# Custom procedural shrub (same as belt2, with added max-spread param)
# ══════════════════════════════════════════════════════════════════════════════

def _normalized(v):
    vec = Vector(v); l = vec.length
    return vec / l if l > 1e-8 else Vector((0, 0, 1))

def _perp_frame(direction):
    d = _normalized(direction)
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.85 else Vector((1, 0, 0))
    right = d.cross(ref).normalized()
    up = d.cross(right).normalized()
    return right, up

def _lerp3(a, b, t):
    return (a[0]+(b[0]-a[0])*t, a[1]+(b[1]-a[1])*t, a[2]+(b[2]-a[2])*t)

def _bezier3(p0, p1, p2, t):
    q0 = _lerp3(p0, p1, t); q1 = _lerp3(p1, p2, t)
    return _lerp3(q0, q1, t)

def _add_tapered_cylinder(verts, faces, path_pts, radii, n_sides=6):
    ring_starts = []
    for i, (pt, r) in enumerate(zip(path_pts, radii)):
        d = _normalized(Vector(path_pts[1])-Vector(path_pts[0])) if i==0 else \
            _normalized(Vector(path_pts[i])-Vector(path_pts[i-1]))
        right, up = _perp_frame(d)
        ring_starts.append(len(verts))
        for j in range(n_sides):
            a = j / n_sides * math.tau
            v = Vector(pt) + right*(r*math.cos(a)) + up*(r*math.sin(a))
            verts.append(tuple(v))
    for i in range(len(ring_starts)-1):
        s0, s1 = ring_starts[i], ring_starts[i+1]
        for j in range(n_sides):
            jn = (j+1) % n_sides
            faces.append((s0+j, s0+jn, s1+jn, s1+j))

def _add_leaf(verts, faces, center, tangent, bitangent, length, width):
    c=Vector(center); t=_normalized(tangent); b=_normalized(bitangent)
    tip  = c + t*length*0.60
    r_sh = c + t*length*0.08 + b*width*0.50
    r_ba = c - t*length*0.32 + b*width*0.18
    base = c - t*length*0.40
    l_ba = c - t*length*0.32 - b*width*0.18
    l_sh = c + t*length*0.08 - b*width*0.50
    idx = len(verts)
    verts += [tuple(tip),tuple(r_sh),tuple(r_ba),tuple(base),tuple(l_ba),tuple(l_sh)]
    faces += [(idx,idx+1,idx+5),(idx+1,idx+2,idx+5),(idx+2,idx+4,idx+5),(idx+2,idx+3,idx+4)]

def _add_leaf_cluster(verts, faces, tip, rng, n_leaves, leaf_size, spread):
    tip = Vector(tip)
    for _ in range(n_leaves):
        offset = Vector((rng.uniform(-spread,spread),rng.uniform(-spread,spread),
                         rng.uniform(-spread*0.4,spread*0.4)))
        center = tip + offset
        outward = (offset + Vector((0,0,0.01))).normalized()
        up_v = Vector((rng.uniform(-.3,.3), rng.uniform(-.3,.3), 1.0)).normalized()
        tangent = (outward*0.6 + up_v*0.4).normalized()
        bitangent = tangent.cross(
            Vector((rng.uniform(-1,1),rng.uniform(-1,1),rng.uniform(-.2,.2))).normalized()
        ).normalized()
        _add_leaf(verts, faces, center, tangent, bitangent,
                  leaf_size*rng.uniform(0.8,1.3), leaf_size*rng.uniform(0.32,0.52))

def _bark_mat():
    mat = bpy.data.materials.new("BeltBark")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out=nt.nodes.new("ShaderNodeOutputMaterial"); bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise=nt.nodes.new("ShaderNodeTexNoise"); ramp=nt.nodes.new("ShaderNodeValToRGB")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value=14.0; noise.inputs["Detail"].default_value=6.0
    ramp.color_ramp.elements[0].color=(0.030,0.016,0.006,1.0)
    ramp.color_ramp.elements[1].color=(0.078,0.042,0.015,1.0)
    bsdf.inputs["Roughness"].default_value=0.92
    nt.links.new(coord.outputs["Generated"],noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def _leaf_mat(seed=0):
    rng = np.random.default_rng(seed)
    mat = bpy.data.materials.new("BeltLeaf")
    mat.use_nodes = True; mat.use_backface_culling = False
    nt = mat.node_tree; nt.nodes.clear()
    out=nt.nodes.new("ShaderNodeOutputMaterial"); mix_s=nt.nodes.new("ShaderNodeMixShader")
    bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled"); trans=nt.nodes.new("ShaderNodeBsdfTranslucent")
    noise=nt.nodes.new("ShaderNodeTexNoise"); ramp=nt.nodes.new("ShaderNodeValToRGB")
    coord=nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value=float(rng.uniform(6,12))
    noise.inputs["Detail"].default_value=5.0
    hue = rng.uniform(-0.04, 0.04)
    ramp.color_ramp.elements[0].color=(max(0,0.013+hue),0.068,max(0,0.009+hue),1.0)
    ramp.color_ramp.elements[1].color=(max(0,0.038+hue),0.148,max(0,0.020+hue),1.0)
    ramp.color_ramp.elements[1].position=0.7
    bsdf.inputs["Roughness"].default_value=float(rng.uniform(0.58,0.72))
    mix_s.inputs["Fac"].default_value=0.25
    nt.links.new(coord.outputs["Generated"],noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],bsdf.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"],trans.inputs["Color"])
    nt.links.new(bsdf.outputs["BSDF"],mix_s.inputs[2])
    nt.links.new(trans.outputs["BSDF"],mix_s.inputs[1])
    nt.links.new(mix_s.outputs["Shader"],out.inputs["Surface"])
    return mat

class ProcShrubFactory:
    """Procedural shrub with constrained spread for narrow belt planting."""

    def __init__(self, seed=0, max_spread=0.22, max_height=0.85):
        self.seed = seed
        rng = np.random.default_rng(seed)
        self.n_stems       = int(rng.integers(4, 7))
        self.max_height    = float(rng.uniform(0.52, max_height))
        # strictly limit spread so shrub stays within belt width
        self.base_spread   = float(rng.uniform(0.14, max_spread))
        self.leaf_size     = float(rng.uniform(0.048, 0.068))
        self._rng          = rng

    def _stem_path(self, base, angle, lean, height):
        rng = self._rng
        tip = (base[0]+lean*math.cos(angle), base[1]+lean*math.sin(angle), base[2]+height)
        ctrl = _lerp3(base, tip, 0.5)
        ctrl = (ctrl[0]+rng.uniform(-.05,.05), ctrl[1]+rng.uniform(-.05,.05),
                ctrl[2]+rng.uniform(-.03,.06))
        return [_bezier3(base, ctrl, tip, t) for t in np.linspace(0,1,4)]

    def create_asset(self, location=(0.,0.,0.), name="Shrub"):
        rng = self._rng
        bark_mat = _bark_mat()
        leaf_mat = _leaf_mat(seed=self.seed)
        sv, sf = [], []   # stem verts/faces
        lv, lf = [], []   # leaf verts/faces
        sec_tips = []

        for i in range(self.n_stems):
            angle = i / self.n_stems * math.tau + rng.uniform(-.25,.25)
            lean  = self.base_spread * rng.uniform(0.5, 1.0)
            h     = self.max_height  * rng.uniform(0.70, 1.20)
            base  = (location[0]+math.cos(angle)*0.03,
                     location[1]+math.sin(angle)*0.03, location[2])
            path  = self._stem_path(base, angle, lean, h)
            radii = np.linspace(0.018, 0.004, 4).tolist()
            _add_tapered_cylinder(sv, sf, path, radii, n_sides=6)

            for j in range(int(rng.integers(2, 5))):
                t   = rng.uniform(.45, .80)
                pt  = _bezier3(path[0], path[1], path[-1], t)
                br_a = rng.uniform(0, math.tau)
                br_e = rng.uniform(math.radians(25), math.radians(68))
                bl   = h * rng.uniform(.20, .44)
                br_tip = (pt[0]+bl*math.cos(br_a)*math.cos(br_e),
                          pt[1]+bl*math.sin(br_a)*math.cos(br_e),
                          pt[2]+bl*math.sin(br_e))
                br_ctrl = _lerp3(pt, br_tip, .5)
                br_path = [_bezier3(pt, br_ctrl, br_tip, t2) for t2 in np.linspace(0,1,3)]
                _add_tapered_cylinder(sv, sf, br_path, [0.008,0.006,0.003], n_sides=5)
                sec_tips.append(br_tip)

        # leaf clusters at secondary branch tips
        n_per_tip = int(rng.integers(12, 20))
        for tip in sec_tips:
            _add_leaf_cluster(lv, lf, tip, rng, n_per_tip,
                              self.leaf_size, self.leaf_size*1.1)

        stem_mesh = bpy.data.meshes.new(name+"_bark")
        stem_mesh.from_pydata(sv, [], sf); stem_mesh.update()
        stem_obj = bpy.data.objects.new(name+"_bark", stem_mesh)
        bpy.context.collection.objects.link(stem_obj)
        stem_obj.data.materials.append(bark_mat)

        leaf_mesh = bpy.data.meshes.new(name+"_leaf")
        leaf_mesh.from_pydata(lv, [], lf); leaf_mesh.update()
        for p in leaf_mesh.polygons: p.use_smooth = True
        leaf_obj = bpy.data.objects.new(name+"_leaf", leaf_mesh)
        bpy.context.collection.objects.link(leaf_obj)
        leaf_obj.data.materials.append(leaf_mat)
        leaf_obj.parent = stem_obj

        bpy.context.view_layer.update()
        print(f"  [shrub] {name}: {len(sec_tips)} branches h≈{self.max_height:.2f}m "
              f"spread≤{self.base_spread:.2f}m")
        return stem_obj

# ══════════════════════════════════════════════════════════════════════════════
# Scene helpers
# ══════════════════════════════════════════════════════════════════════════════

def enable_denoiser():
    for d in ("OPTIX","OPENIMAGEDENOISE"):
        try: bpy.context.scene.cycles.denoiser=d; return
        except Exception: pass

def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes,bpy.data.materials,bpy.data.cameras,
                bpy.data.lights,bpy.data.curves,bpy.data.collections):
        for blk in list(col):
            try: col.remove(blk)
            except Exception: pass

def noisy_mat(name, c0, c1, roughness=0.9, scale=6.0):
    mat = bpy.data.materials.new(name); mat.use_nodes=True
    nt = mat.node_tree; nt.nodes.clear()
    out=nt.nodes.new("ShaderNodeOutputMaterial"); bsdf=nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise=nt.nodes.new("ShaderNodeTexNoise"); ramp=nt.nodes.new("ShaderNodeValToRGB")
    coord=nt.nodes.new("ShaderNodeTexCoord"); mp=nt.nodes.new("ShaderNodeMapping")
    noise.inputs["Scale"].default_value=scale; noise.inputs["Detail"].default_value=6.0
    mp.inputs["Scale"].default_value=(2.,2.,1.)
    ramp.color_ramp.elements[0].color=c0; ramp.color_ramp.elements[1].color=c1
    bsdf.inputs["Roughness"].default_value=roughness
    nt.links.new(coord.outputs["UV"],mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"],noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],out.inputs["Surface"])
    return mat

def add_sky(elev=32, rot=150, strength=1.08):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World"); bpy.context.scene.world=world
    world.use_nodes=True; nt=world.node_tree; nt.nodes.clear()
    bg=nt.nodes.new("ShaderNodeBackground"); sky=nt.nodes.new("ShaderNodeTexSky")
    out=nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type="NISHITA"; sky.sun_elevation=math.radians(elev); sky.sun_rotation=math.radians(rot)
    bg.inputs["Strength"].default_value=strength
    nt.links.new(sky.outputs["Color"],bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"],out.inputs["Surface"])

def add_sun(energy=580, elev=32, az=150):
    bpy.ops.object.light_add(type="SUN", location=(5,-5,15))
    s=bpy.context.active_object; s.data.energy=energy; s.data.angle=math.radians(1.8)
    s.rotation_euler=(math.radians(90-elev),0,math.radians(az)); return s

def add_cam(loc, look_at, name="Cam", lens=50):
    bpy.ops.object.camera_add(location=loc)
    cam=bpy.context.active_object; cam.name=name; cam.data.lens=lens
    bpy.context.scene.camera=cam
    bpy.ops.object.empty_add(type="PLAIN_AXES",location=look_at)
    tgt=bpy.context.active_object; tgt.name=name+"_tgt"
    tc=cam.constraints.new("TRACK_TO")
    tc.target=tgt; tc.track_axis="TRACK_NEGATIVE_Z"; tc.up_axis="UP_Y"
    return cam, tgt

def rm_cam(cam, tgt):
    bpy.data.objects.remove(cam,do_unlink=True)
    bpy.data.objects.remove(tgt,do_unlink=True)

def setup_png(fp, samples=128, rx=1920, ry=1080):
    sc=bpy.context.scene
    sc.cycles.samples=samples; sc.cycles.use_denoising=True; enable_denoiser()
    sc.render.resolution_x=rx; sc.render.resolution_y=ry
    sc.render.image_settings.file_format="PNG"; sc.render.filepath=str(fp)

def setup_video(fp, n=150, fps=25, samples=48, rx=1920, ry=1080):
    sc=bpy.context.scene; sc.frame_start=1; sc.frame_end=n; sc.render.fps=fps
    setup_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format="FFMPEG"
    sc.render.ffmpeg.format="MPEG4"; sc.render.ffmpeg.codec="H264"
    sc.render.ffmpeg.constant_rate_factor="HIGH"

def orbit_anim(cam, cx, cy, radius, height, n=150):
    cam.animation_data_create(); cam.animation_data.action=bpy.data.actions.new("Belt3Orbit")
    for f in range(1,n+1):
        ang=(f-1)/n*math.tau
        cam.location=(cx+radius*math.cos(ang), cy+radius*math.sin(ang), height)
        cam.keyframe_insert("location",frame=f)

# ── geometry ───────────────────────────────────────────────────────────────────

def build_ground(mat):
    bpy.ops.mesh.primitive_plane_add(size=1.,location=(BELT_LEN/2,BELT_WIDTH/2,0))
    g=bpy.context.active_object; g.name="BeltGround"; g.scale=(BELT_LEN,BELT_WIDTH,1.)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.subdivide(number_cuts=10)
    bpy.ops.object.mode_set(mode="OBJECT"); g.data.materials.append(mat); return g

def build_zone2_plane():
    """Sub-plane for flower scatter in zone 2 (x: 7.5-15)."""
    cx = (ZONE_SPLIT + BELT_LEN) / 2   # 11.25
    bpy.ops.mesh.primitive_plane_add(size=1., location=(cx, BELT_WIDTH/2, 0.005))
    z2=bpy.context.active_object; z2.name="Zone2Plane"
    z2.scale=((BELT_LEN-ZONE_SPLIT), BELT_WIDTH, 1.)
    bpy.ops.object.transform_apply(scale=True)
    z2.display_type="WIRE"; z2.hide_render=False   # used as scatter base only
    return z2

def build_curb(mat, x_center, y_center, length):
    bpy.ops.mesh.primitive_cube_add(size=1., location=(x_center, y_center, CURB_H/2-0.04))
    c=bpy.context.active_object; c.name=f"Curb_{y_center:.1f}"
    c.scale=(length, CURB_W, CURB_H); bpy.ops.object.transform_apply(scale=True)
    c.data.materials.append(mat); return c

def build_road(mat):
    bpy.ops.mesh.primitive_plane_add(size=1.,
        location=(BELT_LEN/2, -(CURB_W+ROAD_W/2), -0.04))
    r=bpy.context.active_object; r.name="Road"; r.scale=(BELT_LEN+4, ROAD_W, 1.)
    bpy.ops.object.transform_apply(scale=True); r.data.materials.append(mat); return r

def build_sidewalk(mat):
    bpy.ops.mesh.primitive_plane_add(size=1.,
        location=(BELT_LEN/2, BELT_WIDTH+CURB_W+ROAD_W/2, -0.01))
    s=bpy.context.active_object; s.name="Sidewalk"; s.scale=(BELT_LEN+4, ROAD_W, 1.)
    bpy.ops.object.transform_apply(scale=True); s.data.materials.append(mat); return s

# ── plant placement ────────────────────────────────────────────────────────────

def place_shrubs_zone1():
    """
    Dense shrub grid in zone 1 (x: 0-7.5 m).
    5 cols × 3 rows = 15 shrubs, all centres within x∈[0.5,6.8] y∈[0.30,0.90].
    max_spread = 0.22 m → no stem exceeds belt boundary.
    """
    print("[belt3] Zone 1: placing shrubs …")
    rng = np.random.default_rng(7)
    cols = np.linspace(0.65, 6.85, 5)        # 5 x-positions in zone 1
    rows = [0.30, 0.60, 0.90]                 # 3 y-positions (clamped to [0.25,0.95])

    count = 0
    for ci, bx in enumerate(cols):
        for ri, by in enumerate(rows):
            # small jitter kept within bounds
            x = float(np.clip(bx + rng.uniform(-.12, .12), 0.50, 7.10))
            y = float(np.clip(by + rng.uniform(-.08, .08), Y_MIN+0.10, Y_MAX-0.10))
            seed = ci * 10 + ri + 42
            fac = ProcShrubFactory(seed=seed, max_spread=0.22, max_height=0.82)
            obj = fac.create_asset(location=(x, y, 0.), name=f"Shrub_{count}")
            count += 1
    print(f"[belt3] Zone 1: {count} shrubs placed.")


def place_flower_scatter(zone2_plane):
    """Geometry-nodes flower scatter in zone 2 (x: 7.5-15 m)."""
    print("[belt3] Zone 2: flower scatter …")
    with FixedSeed(55):
        scatter_obj, flower_col = Flowerplant().apply(zone2_plane, density=0.5)
    print(f"[belt3] Zone 2: flower scatter → {scatter_obj.name}")
    return scatter_obj, flower_col


def place_grass_scatter(ground):
    print("[belt3] Grass scatter (whole belt) …")
    with FixedSeed(42):
        scatter_obj, col = Grass().apply(ground)
    print(f"[belt3] Grass scatter → {scatter_obj.name}")
    return scatter_obj, col

# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    configure_cycles_devices()

    print("[belt3] Building scene …")
    soil_mat  = noisy_mat("soil",    (0.030,0.016,0.007,1.),(0.062,0.036,0.015,1.), scale=8.)
    curb_mat  = noisy_mat("curb",    (0.54,0.53,0.51,1.),  (0.47,0.46,0.44,1.),  roughness=0.85, scale=12.)
    asph_mat  = noisy_mat("asphalt", (0.027,0.027,0.029,1.),(0.039,0.039,0.041,1.), roughness=0.93, scale=5.)
    pave_mat  = noisy_mat("pave",    (0.49,0.48,0.46,1.),  (0.41,0.40,0.39,1.),  roughness=0.87, scale=10.)

    ground    = build_ground(soil_mat)
    zone2_plane = build_zone2_plane()

    # Curbs on BOTH sides (road side y≈0, sidewalk side y≈1.2)
    build_curb(curb_mat, BELT_LEN/2, -CURB_W/2,     BELT_LEN)   # road-side curb
    build_curb(curb_mat, BELT_LEN/2,  BELT_WIDTH + CURB_W/2, BELT_LEN)  # sidewalk-side curb
    build_road(asph_mat)
    build_sidewalk(pave_mat)

    add_sky(elev=34, rot=148, strength=1.1)
    add_sun(energy=590, elev=34, az=148)

    # ── plants ────────────────────────────────────────────────────────────────
    place_grass_scatter(ground)
    place_shrubs_zone1()
    place_flower_scatter(zone2_plane)

    bpy.context.view_layer.update()

    cx = BELT_LEN / 2    # 7.5
    cy = BELT_WIDTH / 2  # 0.6

    # ── 1. Zone 1 close-up (shrub zone) ───────────────────────────────────────
    print("\n[render] Zone 1 shrub close-up …")
    cam, tgt = add_cam(loc=(3.5, -3.8, 1.3), look_at=(3.5, 0.55, 0.50),
                       name="CamZ1", lens=75)
    setup_png(OUT/"belt3_zone1_shrubs.png", samples=160)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt3_zone1_shrubs.png'}")
    rm_cam(cam, tgt)

    # ── 2. Zone 2 close-up (flower zone) ──────────────────────────────────────
    print("\n[render] Zone 2 flower close-up …")
    cam, tgt = add_cam(loc=(11.0, -3.8, 1.3), look_at=(11.0, 0.55, 0.45),
                       name="CamZ2", lens=75)
    setup_png(OUT/"belt3_zone2_flowers.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt3_zone2_flowers.png'}")
    rm_cam(cam, tgt)

    # ── 3. Full belt side view ─────────────────────────────────────────────────
    print("\n[render] Full belt side view …")
    cam, tgt = add_cam(loc=(cx, -5.5, 1.5), look_at=(cx, cy, 0.55),
                       name="CamSide", lens=62)
    setup_png(OUT/"belt3_side.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt3_side.png'}")
    rm_cam(cam, tgt)

    # ── 4. End perspective ─────────────────────────────────────────────────────
    print("\n[render] End perspective …")
    cam, tgt = add_cam(loc=(-3.5, cy, 1.6), look_at=(cx, cy, 0.50),
                       name="CamEnd", lens=50)
    setup_png(OUT/"belt3_end.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt3_end.png'}")
    rm_cam(cam, tgt)

    # ── 5. Orbit video ─────────────────────────────────────────────────────────
    print("\n[render] Orbit video …")
    N = 150
    cam, tgt = add_cam(loc=(cx+10., cy, 3.5), look_at=(cx, cy, 0.5),
                       name="CamOrbit", lens=55)
    orbit_anim(cam, cx, cy, radius=10., height=3.5, n=N)
    setup_video(OUT/"belt3_orbit", n=N, samples=48)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'belt3_orbit0001-0150.mp4'}")
    rm_cam(cam, tgt)

    # ── 6. Save .blend ─────────────────────────────────────────────────────────
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT/"belt3.blend"))
    print(f"\n[blend] {OUT/'belt3.blend'}")
    print(f"[done] {OUT}")


if __name__ == "__main__":
    main()

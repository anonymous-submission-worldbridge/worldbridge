#!/usr/bin/env python3
"""
curb_belt2_render.py — roadside green belt with custom procedural shrub.

ProcShrubFactory design (not spherical, with realistic shrub structure)
  • 4-7 main stems growing from base at varying lean angles
  • each stem has 2-4 secondary branches (50-80 % up the stem)
  • leaf clusters (lance-shaped leaf cards) at every secondary branch tip
  • bark material on stems, translucent leaf material on leaf cards
  • overall silhouette: irregular, wider-than-tall, natural

Belt content:
  • Soil strip 15 m × 1.2 m  +  dense grass scatter
  • 5 custom shrubs (ProcShrubFactory)
  • 5 flower plants (FlowerPlantFactory / fallback)
  • Concrete curb + asphalt road + pavement slab

Outputs → ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt2/:
  belt2_shrub_preview.png   — individual shrub close-up
  belt2_side.png            — street-level side view
  belt2_end.png             — end-perspective looking down the belt
  belt2_top.png             — plan view
  belt2_orbit0001-0150.mp4  — orbit video
  belt2.blend

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
OUT = Path(f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt2')
OUT.mkdir(parents=True, exist_ok=True)

# ── belt imports ───────────────────────────────────────────────────────────────
from infinigen.assets.objects.grassland.urban_groundcover import UrbanGroundcoverFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest
from infinigen.assets.scatters.grass import Grass
from infinigen.core.util.math import FixedSeed

# ══════════════════════════════════════════════════════════════════════════════
# ProcShrubFactory — custom procedural shrub
# ══════════════════════════════════════════════════════════════════════════════

def _normalized(v):
    vec = Vector(v)
    l = vec.length
    return vec / l if l > 1e-8 else Vector((0, 0, 1))


def _perp_frame(direction):
    """Return (right, up) vectors perpendicular to `direction`."""
    d = _normalized(direction)
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.85 else Vector((1, 0, 0))
    right = d.cross(ref).normalized()
    up = d.cross(right).normalized()
    return right, up


def _lerp3(a, b, t):
    return (a[0] + (b[0]-a[0])*t, a[1] + (b[1]-a[1])*t, a[2] + (b[2]-a[2])*t)


def _bezier3(p0, p1, p2, t):
    """Quadratic Bézier."""
    q0 = _lerp3(p0, p1, t)
    q1 = _lerp3(p1, p2, t)
    return _lerp3(q0, q1, t)


def _add_tapered_cylinder(verts, faces, path_pts, radii, n_sides=6):
    """
    Extrude a tapered tube along `path_pts` with corresponding `radii`.
    `path_pts`: list of (x,y,z)  len >= 2
    `radii`   : list of float    same length as path_pts
    """
    assert len(path_pts) == len(radii) >= 2
    ring_starts = []  # index of first vertex in each ring

    for seg_i, (pt, r) in enumerate(zip(path_pts, radii)):
        if seg_i == 0:
            d = _normalized(Vector(path_pts[1]) - Vector(path_pts[0]))
        else:
            d = _normalized(Vector(path_pts[seg_i]) - Vector(path_pts[seg_i - 1]))
        right, up = _perp_frame(d)
        ring_starts.append(len(verts))
        for j in range(n_sides):
            a = j / n_sides * math.tau
            v = Vector(pt) + right * (r * math.cos(a)) + up * (r * math.sin(a))
            verts.append(tuple(v))

    # Quads between consecutive rings
    for i in range(len(ring_starts) - 1):
        s0 = ring_starts[i]
        s1 = ring_starts[i + 1]
        for j in range(n_sides):
            jn = (j + 1) % n_sides
            faces.append((s0 + j, s0 + jn, s1 + jn, s1 + j))


def _add_leaf(verts, faces, center, tangent, bitangent, length, width):
    """
    Lance-shaped leaf (6 vertices, 4 triangles).
    `tangent`   : points from leaf base to tip
    `bitangent` : across leaf width (perpendicular to tangent, in leaf plane)
    """
    c = Vector(center)
    t = _normalized(tangent)
    b = _normalized(bitangent)
    tip   = c + t * length * 0.60
    r_sh  = c + t * length * 0.08 + b * width * 0.50
    r_ba  = c - t * length * 0.32 + b * width * 0.18
    base  = c - t * length * 0.40
    l_ba  = c - t * length * 0.32 - b * width * 0.18
    l_sh  = c + t * length * 0.08 - b * width * 0.50

    idx = len(verts)
    verts += [tuple(tip), tuple(r_sh), tuple(r_ba),
              tuple(base), tuple(l_ba), tuple(l_sh)]
    # 4 triangles
    faces += [(idx,   idx+1, idx+5),
              (idx+1, idx+2, idx+5),
              (idx+2, idx+4, idx+5),
              (idx+2, idx+3, idx+4)]


def _add_leaf_cluster(verts, faces, tip, rng, n_leaves, leaf_size, spread=0.08):
    """Scatter `n_leaves` lance leaves around `tip`."""
    tip = Vector(tip)
    for _ in range(n_leaves):
        # Random position within a small sphere around the tip
        offset = Vector((rng.uniform(-spread, spread),
                         rng.uniform(-spread, spread),
                         rng.uniform(-spread * 0.5, spread * 0.5)))
        center = tip + offset

        # Leaf tangent: upward + outward
        outward = (offset + Vector((0, 0, 0.01))).normalized()
        up = Vector((rng.uniform(-0.3, 0.3),
                     rng.uniform(-0.3, 0.3), 1.0)).normalized()
        tangent   = (outward * 0.6 + up * 0.4).normalized()
        bitangent = tangent.cross(
            Vector((rng.uniform(-1, 1), rng.uniform(-1, 1),
                    rng.uniform(-0.3, 0.3))).normalized()
        ).normalized()

        _add_leaf(verts, faces, center, tangent, bitangent,
                  leaf_size * rng.uniform(0.8, 1.3),
                  leaf_size * rng.uniform(0.35, 0.55))


def make_bark_mat():
    mat = bpy.data.materials.new("ShrubBark")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out  = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp  = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value  = 14.0
    noise.inputs["Detail"].default_value = 6.0
    ramp.color_ramp.elements[0].color = (0.032, 0.017, 0.007, 1.0)
    ramp.color_ramp.elements[1].color = (0.080, 0.044, 0.016, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.92
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],       ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],      bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],       out.inputs["Surface"])
    return mat


def make_leaf_mat(seed=0):
    rng = np.random.default_rng(seed)
    mat = bpy.data.materials.new("ShrubLeaf")
    mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree; nt.nodes.clear()

    out   = nt.nodes.new("ShaderNodeOutputMaterial")
    mix_s = nt.nodes.new("ShaderNodeMixShader")
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled")
    trans = nt.nodes.new("ShaderNodeBsdfTranslucent")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp  = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")

    noise.inputs["Scale"].default_value  = float(rng.uniform(6, 12))
    noise.inputs["Detail"].default_value = 5.0

    # Two-tone green with slight hue shift per shrub instance
    hue = rng.uniform(-0.04, 0.04)
    c0 = (max(0, 0.014+hue), 0.072, max(0, 0.010+hue), 1.0)   # dark leaf
    c1 = (max(0, 0.040+hue), 0.150, max(0, 0.022+hue), 1.0)   # light leaf

    ramp.color_ramp.elements[0].color    = c0
    ramp.color_ramp.elements[1].color    = c1
    ramp.color_ramp.elements[1].position = 0.7

    bsdf.inputs["Roughness"].default_value = float(rng.uniform(0.60, 0.75))

    mix_s.inputs["Fac"].default_value = 0.25   # 25% translucent backlight

    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],       ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"],      bsdf.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"],      trans.inputs["Color"])
    nt.links.new(bsdf.outputs["BSDF"],       mix_s.inputs[2])
    nt.links.new(trans.outputs["BSDF"],      mix_s.inputs[1])
    nt.links.new(mix_s.outputs["Shader"],    out.inputs["Surface"])
    return mat


class ProcShrubFactory:
    """
    Procedural shrub: visible multi-stem woody structure + irregular leaf canopy.
    Returns a single Blender object with two material slots (bark, leaf).
    """

    def __init__(self, seed=0):
        self.seed  = seed
        self._rng  = np.random.default_rng(seed)

        rng = self._rng
        self.n_main_stems  = int(rng.integers(4, 8))
        self.max_height    = float(rng.uniform(0.65, 1.20))
        self.base_spread   = float(rng.uniform(0.30, 0.60))
        self.leaf_size     = float(rng.uniform(0.062, 0.095))
        self.n_sec_range   = (2, 5)   # secondary branches per main stem

    # ── internal geometry builders ────────────────────────────────────────────

    def _stem_path(self, base, lean_angle, lean_dist, height, n_pts=4):
        """Gentle S-curved stem path from base to tip."""
        rng = self._rng
        tip = (base[0] + lean_dist * math.cos(lean_angle),
               base[1] + lean_dist * math.sin(lean_angle),
               base[2] + height)
        ctrl = _lerp3(base, tip, 0.5)
        ctrl = (ctrl[0] + rng.uniform(-0.06, 0.06),
                ctrl[1] + rng.uniform(-0.06, 0.06),
                ctrl[2] + rng.uniform(-0.04, 0.08))
        return [_bezier3(base, ctrl, tip, t)
                for t in np.linspace(0, 1, n_pts)]

    def _build_stems_mesh(self, origin):
        """Return (verts, faces) for all stems (bark geometry)."""
        rng = self._rng
        verts, faces = [], []
        secondary_tips = []

        for i in range(self.n_main_stems):
            base_angle = i / self.n_main_stems * math.tau + rng.uniform(-0.25, 0.25)
            lean_d     = self.base_spread * rng.uniform(0.5, 1.0)
            height     = self.max_height * rng.uniform(0.70, 1.25)

            base = (origin[0] + math.cos(base_angle) * 0.04,
                    origin[1] + math.sin(base_angle) * 0.04,
                    origin[2])
            path  = self._stem_path(base, base_angle, lean_d, height)
            radii = np.linspace(0.022, 0.005, len(path)).tolist()
            _add_tapered_cylinder(verts, faces, path, radii, n_sides=6)

            # Secondary branches
            n_sec = int(rng.integers(*self.n_sec_range))
            for j in range(n_sec):
                t   = rng.uniform(0.45, 0.82)
                pt  = _bezier3(path[0], path[len(path)//2], path[-1], t)
                br_angle = rng.uniform(0, math.tau)
                br_elev  = rng.uniform(math.radians(20), math.radians(65))
                br_len   = height * rng.uniform(0.22, 0.46)
                br_tip   = (pt[0] + br_len * math.cos(br_angle) * math.cos(br_elev),
                            pt[1] + br_len * math.sin(br_angle) * math.cos(br_elev),
                            pt[2] + br_len * math.sin(br_elev))
                br_ctrl  = _lerp3(pt, br_tip, 0.5)
                br_path  = [_bezier3(pt, br_ctrl, br_tip, t2)
                            for t2 in np.linspace(0, 1, 3)]
                br_radii = [0.010, 0.007, 0.004]
                _add_tapered_cylinder(verts, faces, br_path, br_radii, n_sides=5)
                secondary_tips.append(br_tip)

        return verts, faces, secondary_tips

    def _build_leaves_mesh(self, secondary_tips):
        """Return (verts, faces) for all leaf cards."""
        rng = self._rng
        verts, faces = [], []
        n_leaves_per_tip = int(rng.integers(14, 22))
        for tip in secondary_tips:
            _add_leaf_cluster(verts, faces, tip, rng,
                              n_leaves=n_leaves_per_tip,
                              leaf_size=self.leaf_size,
                              spread=self.leaf_size * 1.2)
        return verts, faces

    # ── public API ────────────────────────────────────────────────────────────

    def create_asset(self, location=(0.0, 0.0, 0.0), name="ProcShrub"):
        bark_mat = make_bark_mat()
        leaf_mat = make_leaf_mat(seed=self.seed)

        # Stems mesh
        sv, sf, sec_tips = self._build_stems_mesh(location)
        stem_mesh = bpy.data.meshes.new(name + "_bark")
        stem_mesh.from_pydata(sv, [], sf)
        stem_mesh.update()
        stem_obj = bpy.data.objects.new(name + "_bark", stem_mesh)
        bpy.context.collection.objects.link(stem_obj)
        stem_obj.data.materials.append(bark_mat)

        # Leaves mesh
        lv, lf = self._build_leaves_mesh(sec_tips)
        leaf_mesh = bpy.data.meshes.new(name + "_leaf")
        leaf_mesh.from_pydata(lv, [], lf)
        leaf_mesh.update()
        # Smooth shading for leaves
        for poly in leaf_mesh.polygons:
            poly.use_smooth = True
        leaf_obj = bpy.data.objects.new(name + "_leaf", leaf_mesh)
        bpy.context.collection.objects.link(leaf_obj)
        leaf_obj.data.materials.append(leaf_mat)

        # Parent leaves to stem
        leaf_obj.parent = stem_obj

        bpy.context.view_layer.update()
        print(f"  [shrub] {name}: {len(sec_tips)} branches, "
              f"{len(lv)} leaf verts, stems height≈{self.max_height:.2f}m")
        return stem_obj   # leaf_obj follows as child


# ══════════════════════════════════════════════════════════════════════════════
# Scene / render helpers
# ══════════════════════════════════════════════════════════════════════════════

BELT_LEN   = 15.0
BELT_WIDTH = 1.2
CURB_H     = 0.14
CURB_W     = 0.15
ROAD_W     = 8.0


def enable_optix_denoiser():
    for d in ("OPTIX", "OPENIMAGEDENOISE"):
        try:
            bpy.context.scene.cycles.denoiser = d; return
        except Exception:
            pass


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for col in (bpy.data.meshes, bpy.data.materials,
                bpy.data.cameras, bpy.data.lights, bpy.data.curves,
                bpy.data.collections):
        for blk in list(col):
            try: col.remove(blk)
            except Exception: pass


def simple_mat(name, color, roughness=0.9):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value  = roughness
    return mat


def noisy_mat(name, c0, c1, roughness=0.9, scale=6.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    out   = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf  = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp  = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mp    = nt.nodes.new("ShaderNodeMapping")
    noise.inputs["Scale"].default_value  = scale
    noise.inputs["Detail"].default_value = 6.0
    mp.inputs["Scale"].default_value = (2.0, 2.0, 1.0)
    ramp.color_ramp.elements[0].color = c0
    ramp.color_ramp.elements[1].color = c1
    bsdf.inputs["Roughness"].default_value = roughness
    nt.links.new(coord.outputs["UV"],   mp.inputs["Vector"])
    nt.links.new(mp.outputs["Vector"],  noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"],  ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"],  out.inputs["Surface"])
    return mat


def add_sky_world(elev=32, rot=150, strength=1.05):
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree; nt.nodes.clear()
    bg  = nt.nodes.new("ShaderNodeBackground")
    sky = nt.nodes.new("ShaderNodeTexSky")
    out = nt.nodes.new("ShaderNodeOutputWorld")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(elev)
    sky.sun_rotation  = math.radians(rot)
    bg.inputs["Strength"].default_value = strength
    nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs["Background"], out.inputs["Surface"])


def add_sun(energy=580, elev=32, az=150):
    bpy.ops.object.light_add(type="SUN", location=(5, -5, 15))
    sun = bpy.context.active_object
    sun.data.energy = energy
    sun.data.angle  = math.radians(1.8)
    sun.rotation_euler = (math.radians(90 - elev), 0, math.radians(az))
    return sun


def add_cam(loc, look_at, name="Cam", lens=50):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object; cam.name = name; cam.data.lens = lens
    bpy.context.scene.camera = cam
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=look_at)
    tgt = bpy.context.active_object; tgt.name = name + "_tgt"
    tc = cam.constraints.new("TRACK_TO")
    tc.target = tgt; tc.track_axis = "TRACK_NEGATIVE_Z"; tc.up_axis = "UP_Y"
    return cam, tgt


def rm_cam(cam, tgt):
    bpy.data.objects.remove(cam, do_unlink=True)
    bpy.data.objects.remove(tgt, do_unlink=True)


def setup_png(fp, samples=128, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.cycles.samples = samples; sc.cycles.use_denoising = True
    enable_optix_denoiser()
    sc.render.resolution_x = rx; sc.render.resolution_y = ry
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(fp)


def setup_video(fp, n=150, fps=25, samples=48, rx=1920, ry=1080):
    sc = bpy.context.scene
    sc.frame_start = 1; sc.frame_end = n; sc.render.fps = fps
    setup_png(fp, samples, rx, ry)
    sc.render.image_settings.file_format  = "FFMPEG"
    sc.render.ffmpeg.format               = "MPEG4"
    sc.render.ffmpeg.codec                = "H264"
    sc.render.ffmpeg.constant_rate_factor = "HIGH"


def orbit_anim(cam, cx, cy, radius, height, n=150):
    cam.animation_data_create()
    cam.animation_data.action = bpy.data.actions.new("Belt2Orbit")
    for f in range(1, n + 1):
        ang = (f - 1) / n * math.tau
        cam.location = (cx + radius * math.cos(ang),
                        cy + radius * math.sin(ang), height)
        cam.keyframe_insert("location", frame=f)


# ── scene geometry ─────────────────────────────────────────────────────────────

def build_strip(soil_mat):
    bpy.ops.mesh.primitive_plane_add(size=1.0,
        location=(BELT_LEN / 2, BELT_WIDTH / 2, 0))
    g = bpy.context.active_object; g.name = "BeltGround"
    g.scale = (BELT_LEN, BELT_WIDTH, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.subdivide(number_cuts=8)
    bpy.ops.object.mode_set(mode="OBJECT")
    g.data.materials.append(soil_mat)
    return g


def build_curb(mat):
    bpy.ops.mesh.primitive_cube_add(size=1.0,
        location=(BELT_LEN/2, -CURB_W/2, CURB_H/2 - 0.04))
    c = bpy.context.active_object; c.name = "Curb"
    c.scale = (BELT_LEN, CURB_W, CURB_H)
    bpy.ops.object.transform_apply(scale=True)
    c.data.materials.append(mat); return c


def build_road(mat):
    bpy.ops.mesh.primitive_plane_add(size=1.0,
        location=(BELT_LEN/2, -(CURB_W + ROAD_W/2), -0.04))
    r = bpy.context.active_object; r.name = "Road"
    r.scale = (BELT_LEN + 4, ROAD_W, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    r.data.materials.append(mat); return r


def build_sidewalk(mat):
    bpy.ops.mesh.primitive_plane_add(size=1.0,
        location=(BELT_LEN/2, BELT_WIDTH + ROAD_W/2, -0.01))
    s = bpy.context.active_object; s.name = "Sidewalk"
    s.scale = (BELT_LEN + 4, ROAD_W, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    s.data.materials.append(mat); return s


# ── plant placement ────────────────────────────────────────────────────────────

def place_custom_shrubs():
    print("[belt2] Placing custom shrubs …")
    positions = np.linspace(1.5, BELT_LEN - 1.5, 5)
    for i, x in enumerate(positions):
        y = BELT_WIDTH * (0.35 + 0.30 * (i % 2))
        factory = ProcShrubFactory(seed=i * 17 + 3)
        obj = factory.create_asset(location=(x, y, 0.0),
                                   name=f"Shrub_{i}")
        obj.location = (x, y, 0.0)


def place_flower_plants():
    print("[belt2] Placing flower plants …")
    mats = {
        "shrub":        simple_mat("shrub_fb",    (0.04,0.14,0.03,1.0)),
        "leaf_dark":    simple_mat("leaf_fb",     (0.02,0.09,0.02,1.0)),
        "grass_tuft":   simple_mat("grass_fb",    (0.07,0.20,0.04,1.0)),
        "flower_yellow":simple_mat("flower_fb",   (0.82,0.72,0.08,1.0)),
        "lamp":         simple_mat("lamp_fb",     (0.90,0.88,0.80,1.0)),
        "trunk":        simple_mat("trunk_fb",    (0.12,0.08,0.04,1.0)),
        "leaf_litter":  simple_mat("litter_fb",   (0.18,0.12,0.04,1.0)),
    }
    factory = UrbanGroundcoverFactory(mats)
    xs = np.linspace(0.8, BELT_LEN - 0.8, 5)
    for i, x in enumerate(xs):
        y = BELT_WIDTH * (0.55 + 0.25 * math.sin(i * 2.1))
        req = UrbanAssetRequest(
            asset_type="flowerplant", location=(x, y, 0.0),
            semantic="flowerplant", yaw=i * 0.9,
            params={"id": str(30 + i), "scale": 0.7 + 0.1*(i%3),
                    "max_faces": 8000},
        )
        try:
            factory.create_flowerplant(req)
        except Exception as e:
            print(f"  flower {i} failed: {e}")


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    clear_scene()
    bpy.context.scene.render.engine = "CYCLES"
    configure_cycles_devices()

    # ── materials ─────────────────────────────────────────────────────────────
    soil_mat     = noisy_mat("soil",     (0.032,0.018,0.008,1.0),
                                         (0.065,0.038,0.016,1.0), scale=8.0)
    curb_mat     = noisy_mat("concrete", (0.55,0.54,0.52,1.0),
                                         (0.48,0.47,0.45,1.0), roughness=0.85, scale=12.0)
    asphalt_mat  = noisy_mat("asphalt",  (0.028,0.028,0.030,1.0),
                                         (0.040,0.040,0.042,1.0), roughness=0.92, scale=5.0)
    pavement_mat = noisy_mat("pavement", (0.50,0.49,0.47,1.0),
                                         (0.42,0.41,0.40,1.0), roughness=0.86, scale=10.0)

    # ── geometry ──────────────────────────────────────────────────────────────
    belt_ground = build_strip(soil_mat)
    build_curb(curb_mat)
    build_road(asphalt_mat)
    build_sidewalk(pavement_mat)

    add_sky_world(elev=32, rot=150, strength=1.1)
    add_sun(energy=580, elev=32, az=150)

    # ── plants ────────────────────────────────────────────────────────────────
    with FixedSeed(42):
        scatter_obj, _ = Grass().apply(belt_ground)
    print(f"[belt2] Grass scatter: {scatter_obj.name}")

    place_custom_shrubs()
    place_flower_plants()
    bpy.context.view_layer.update()

    cx = BELT_LEN / 2   # 7.5
    cy = BELT_WIDTH / 2 # 0.6

    # ── shrub close-up preview (rendered before full belt) ────────────────────
    print("\n[render] Shrub close-up preview …")
    cam, tgt = add_cam(loc=(3.0, -2.2, 1.1),
                       look_at=(3.0, 0.35, 0.55),
                       name="CamShrubPreview", lens=85)
    setup_png(OUT / "belt2_shrub_preview.png", samples=192)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt2_shrub_preview.png'}")
    rm_cam(cam, tgt)

    # ── side view ─────────────────────────────────────────────────────────────
    print("\n[render] Side view …")
    cam, tgt = add_cam(loc=(cx, -5.5, 1.4),
                       look_at=(cx, cy, 0.55),
                       name="CamSide", lens=65)
    setup_png(OUT / "belt2_side.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt2_side.png'}")
    rm_cam(cam, tgt)

    # ── end perspective ────────────────────────────────────────────────────────
    print("\n[render] End perspective …")
    cam, tgt = add_cam(loc=(-3.5, cy, 1.6),
                       look_at=(cx, cy, 0.45),
                       name="CamEnd", lens=50)
    setup_png(OUT / "belt2_end.png", samples=128)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt2_end.png'}")
    rm_cam(cam, tgt)

    # ── top view ──────────────────────────────────────────────────────────────
    print("\n[render] Top view …")
    cam, tgt = add_cam(loc=(cx, cy, 10.0),
                       look_at=(cx, cy, 0.0),
                       name="CamTop", lens=35)
    setup_png(OUT / "belt2_top.png", samples=96)
    bpy.context.scene.frame_set(1)
    bpy.ops.render.render(write_still=True)
    print(f"  → {OUT/'belt2_top.png'}")
    rm_cam(cam, tgt)

    # ── orbit video ───────────────────────────────────────────────────────────
    print("\n[render] Orbit video …")
    N = 150
    cam, tgt = add_cam(loc=(cx + 10.0, cy, 3.5),
                       look_at=(cx, cy, 0.5),
                       name="CamOrbit", lens=55)
    orbit_anim(cam, cx, cy, radius=10.0, height=3.5, n=N)
    setup_video(OUT / "belt2_orbit", n=N, samples=48)
    bpy.ops.render.render(animation=True)
    print(f"  → {OUT/'belt2_orbit0001-0150.mp4'}")
    rm_cam(cam, tgt)

    # ── blend ─────────────────────────────────────────────────────────────────
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "belt2.blend"))
    print(f"\n[blend] {OUT/'belt2.blend'}")
    print(f"[done] {OUT}")


if __name__ == "__main__":
    main()

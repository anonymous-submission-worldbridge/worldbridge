"""
generate_urban_v3_all10.py
==========================
4-quadrant crossroads — all9 zones + exact all8 trees + exact all4 road markings.

Fixes over all9:
  1. Trees  → exact _gen_park_tree() from all8
             (TreeFactory(seed=seed, season="summer", coarse=False, fruit_chance=0.0))
  2. Road   → M["road"] (dark UA asphalt from build_all_materials) + all4 exact markings:
             yellow double-solid centre at ±0.08, white dashes at ±2.25 across arm,
             8-stripe crosswalks at RW+0.6, stop lines at RW+2.0

Zone layout:
  NW — Residential : apartment block, marble ground, iron fence compound
  NE — Park        : lawn + all8 TreeFactory trees + pavilion + bandstand + fountain
  SE — Commercial  : marble ground, shops, bike station, kiosk, phone booth
  SW — Empty       : clean grass lawn

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all10/
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths["WORLDBRIDGE_SITE_PACKAGES"]


import sys, math
from pathlib import Path

REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
CONDA = Path(f"{_wb_WORLDBRIDGE_SITE_PACKAGES}")
sys.path.insert(0, str(REPO))
if CONDA.exists():
    sys.path.insert(0, str(CONDA))
sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/scripts")

import bpy
import numpy as np
from mathutils import Vector
import gin
import infinigen
from infinigen.core import init as _inf_init
from infinigen.core.util.math import FixedSeed

gin.clear_config()
_inf_init.apply_gin_configs(
    config_folders=[str(REPO / "infinigen_examples/configs_nature")],
    configs=[],
    overrides=[],
    skip_unknown=True,
    finalize_config=False,
    mandatory_folders=[],
)

import urban_assets as UA

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all10")
SC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_sculpture/public_art.blend"
)
OX_BASE = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")
OUT.mkdir(parents=True, exist_ok=True)

# ─── RESET + GPU ──────────────────────────────────────────────────────────────
UA.reset_scene()
bpy.context.scene.render.engine = "CYCLES"
for dtype in ("OPTIX", "CUDA", "HIP"):
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = dtype
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
        print(f"[all10] GPU: {dtype}")
        break
    except Exception as e:
        print(f"[all10] {dtype}: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# MATERIALS
# ═══════════════════════════════════════════════════════════════════════════════
def _set(b, k, v):
    if k in b.inputs:
        b.inputs[k].default_value = v


def _clear_new(name):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    for n in list(m.node_tree.nodes):
        m.node_tree.nodes.remove(n)
    return m


def sidewalk_mat(name="a10_sidewalk"):
    m = _clear_new(name)
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.4, 0.4, 1.0)
    links.new(tex.outputs["Object"], mp.inputs["Vector"])
    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 7.0
    n1.inputs["Detail"].default_value = 6.0
    links.new(mp.outputs["Vector"], n1.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.72, 0.71, 0.69, 1.0)
    ramp.color_ramp.elements[1].color = (0.82, 0.81, 0.79, 1.0)
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.83)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    links.new(n1.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def marble_mat(name="a10_marble"):
    m = _clear_new(name)
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.25, 0.25, 1.0)
    links.new(tex.outputs["Object"], mp.inputs["Vector"])
    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 1.8
    n1.inputs["Detail"].default_value = 12.0
    n1.inputs["Distortion"].default_value = 1.2
    n2 = nodes.new("ShaderNodeTexNoise")
    n2.inputs["Scale"].default_value = 5.5
    n2.inputs["Detail"].default_value = 8.0
    links.new(mp.outputs["Vector"], n1.inputs["Vector"])
    links.new(mp.outputs["Vector"], n2.inputs["Vector"])
    r1 = nodes.new("ShaderNodeValToRGB")
    r1.color_ramp.elements[0].color = (0.86, 0.84, 0.80, 1.0)
    r1.color_ramp.elements[1].color = (0.94, 0.92, 0.90, 1.0)
    r2 = nodes.new("ShaderNodeValToRGB")
    r2.color_ramp.elements[0].color = (0.58, 0.56, 0.53, 1.0)
    r2.color_ramp.elements[0].position = 0.0
    r2.color_ramp.elements[1].color = (0.92, 0.90, 0.88, 1.0)
    r2.color_ramp.elements[1].position = 0.28
    links.new(n1.outputs["Fac"], r1.inputs["Fac"])
    links.new(n2.outputs["Fac"], r2.inputs["Fac"])
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MULTIPLY"
    mix.inputs["Fac"].default_value = 0.18
    links.new(r1.outputs["Color"], mix.inputs["Color1"])
    links.new(r2.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.06)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def grass_mat(name="a10_grass"):
    m = _clear_new(name)
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 12.0
    n1.inputs["Detail"].default_value = 10.0
    links.new(tex.outputs["Object"], n1.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.035, 0.076, 0.020, 1.0)
    ramp.color_ramp.elements[1].color = (0.075, 0.14, 0.048, 1.0)
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.95)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def soil_mat(name="a10_soil"):
    m = _clear_new(name)
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 8.0
    n1.inputs["Detail"].default_value = 8.0
    links.new(tex.outputs["Object"], n1.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.21, 0.13, 0.07, 1.0)
    ramp.color_ramp.elements[1].color = (0.30, 0.20, 0.12, 1.0)
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.92)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


# ─── BUILD MATERIALS ─────────────────────────────────────────────────────────
# Fix 2: use UA's built-in road material (dark asphalt ~0.07-0.11 grey)
UA.build_all_materials()
M = UA.M
# Override zone-specific materials only
M["sidewalk"] = sidewalk_mat()
M["marble"] = marble_mat()
M["grass"] = grass_mat()
M["soil"] = soil_mat()
# Road markings reuse built-in stripe_w / stripe_y from build_all_materials()

M["greenstrip"] = grass_mat("a10_gs")
M["grass_park"] = grass_mat("a10_gp")
M["wall_apt"] = UA._noise_mat(
    "wall_apt", (0.80, 0.78, 0.74), (0.88, 0.86, 0.82), rough=0.65, scale=8
)
M["balc"] = UA._pbr("balc", (0.72, 0.70, 0.68), rough=0.72)
M["balc_rail"] = UA._pbr("brail", (0.80, 0.82, 0.85), rough=0.28, metal=0.88)
M["apt_glass"] = UA._glass("apt_glass", tint=(0.82, 0.90, 0.96))
M["apt_roof"] = UA._pbr("apt_roof", (0.36, 0.34, 0.33), rough=0.78)
M["shop_w"] = UA._noise_mat(
    "shop_w", (0.86, 0.80, 0.68), (0.76, 0.70, 0.58), rough=0.68, scale=7
)
M["shop_r"] = UA._noise_mat(
    "shop_r", (0.70, 0.24, 0.14), (0.60, 0.18, 0.10), rough=0.66, scale=7
)
M["shop_b"] = UA._noise_mat(
    "shop_b", (0.30, 0.44, 0.72), (0.22, 0.36, 0.62), rough=0.66, scale=7
)
M["awning_r"] = UA._pbr("awning_r", (0.72, 0.18, 0.10), rough=0.76)
M["awning_g"] = UA._pbr("awning_g", (0.18, 0.50, 0.20), rough=0.76)
M["awning_b"] = UA._pbr("awning_b", (0.16, 0.28, 0.70), rough=0.76)
M["fence_iron"] = UA._pbr("fence_iron", (0.08, 0.08, 0.10), rough=0.32, metal=0.88)
M["gate_post"] = UA._pbr("gate_post", (0.12, 0.12, 0.14), rough=0.28, metal=0.92)
M["stone_path"] = UA._noise_mat(
    "stone_path", (0.66, 0.62, 0.54), (0.56, 0.52, 0.44), rough=0.76, scale=10
)
M["park_stone"] = UA._noise_mat(
    "park_stone", (0.68, 0.66, 0.60), (0.58, 0.56, 0.50), rough=0.68, scale=9
)
M["water_blue"] = UA._pbr("water_blue", (0.08, 0.32, 0.72), rough=0.03)
M["pool_rim"] = UA._pbr("pool_rim", (0.70, 0.68, 0.64), rough=0.55)
M["sign_comm"] = UA._pbr("sign_comm", (0.65, 0.08, 0.08), rough=0.72)


# ═══════════════════════════════════════════════════════════════════════════════
# PROC SHRUB FACTORY (roadside low bushes)
# ═══════════════════════════════════════════════════════════════════════════════
def _nrm(v):
    vec = Vector(v)
    l = vec.length
    return vec / l if l > 1e-8 else Vector((0, 0, 1))


def _pfrm(d):
    d = _nrm(d)
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.85 else Vector((1, 0, 0))
    r = d.cross(ref).normalized()
    u = d.cross(r).normalized()
    return r, u


def _lerp3(a, b, t):
    return (
        a[0] + (b[0] - a[0]) * t,
        a[1] + (b[1] - a[1]) * t,
        a[2] + (b[2] - a[2]) * t,
    )


def _bez3(p0, p1, p2, t):
    q0 = _lerp3(p0, p1, t)
    q1 = _lerp3(p1, p2, t)
    return _lerp3(q0, q1, t)


def _tapcyl(verts, faces, pts, radii, ns=6):
    rs = []
    for i, (pt, r) in enumerate(zip(pts, radii)):
        d = (
            _nrm(Vector(pts[1]) - Vector(pts[0]))
            if i == 0
            else _nrm(Vector(pts[i]) - Vector(pts[i - 1]))
        )
        right, up = _pfrm(d)
        rs.append(len(verts))
        for j in range(ns):
            a = j / ns * math.tau
            v = Vector(pt) + right * (r * math.cos(a)) + up * (r * math.sin(a))
            verts.append(tuple(v))
    for i in range(len(rs) - 1):
        s0, s1 = rs[i], rs[i + 1]
        for j in range(ns):
            jn = (j + 1) % ns
            faces.append((s0 + j, s0 + jn, s1 + jn, s1 + j))


def _addleaf(verts, faces, c, t, b, ln, wd):
    c = Vector(c)
    t = _nrm(t)
    b = _nrm(b)
    tip = c + t * ln * 0.60
    rs = c + t * ln * 0.08 + b * wd * 0.50
    rb = c - t * ln * 0.32 + b * wd * 0.18
    base = c - t * ln * 0.40
    lb = c - t * ln * 0.32 - b * wd * 0.18
    ls = c + t * ln * 0.08 - b * wd * 0.50
    i = len(verts)
    verts += [tuple(tip), tuple(rs), tuple(rb), tuple(base), tuple(lb), tuple(ls)]
    faces += [
        (i, i + 1, i + 5),
        (i + 1, i + 2, i + 5),
        (i + 2, i + 4, i + 5),
        (i + 2, i + 3, i + 4),
    ]


def _leafcluster(verts, faces, tip, rng, n, ls, sp):
    tip = Vector(tip)
    for _ in range(n):
        off = Vector(
            (
                rng.uniform(-sp, sp),
                rng.uniform(-sp, sp),
                rng.uniform(-sp * 0.4, sp * 0.4),
            )
        )
        center = tip + off
        ow = (off + Vector((0, 0, 0.01))).normalized()
        uv = Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.0)).normalized()
        tg = (ow * 0.6 + uv * 0.4).normalized()
        bt = tg.cross(
            Vector(
                (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.2, 0.2))
            ).normalized()
        ).normalized()
        _addleaf(
            verts,
            faces,
            center,
            tg,
            bt,
            ls * rng.uniform(0.8, 1.3),
            ls * rng.uniform(0.32, 0.52),
        )


def _shrub_bark(seed):
    mat = bpy.data.materials.new(f"S10Bark{seed}")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = 14.0
    noise.inputs["Detail"].default_value = 6.0
    ramp.color_ramp.elements[0].color = (0.030, 0.016, 0.006, 1.0)
    ramp.color_ramp.elements[1].color = (0.078, 0.042, 0.015, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.92
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def _shrub_leaf(seed):
    rng = np.random.default_rng(seed)
    mat = bpy.data.materials.new(f"S10Leaf{seed}")
    mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mxs = nt.nodes.new("ShaderNodeMixShader")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    trans = nt.nodes.new("ShaderNodeBsdfTranslucent")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = float(rng.uniform(6, 12))
    noise.inputs["Detail"].default_value = 5.0
    h = rng.uniform(-0.03, 0.03)
    ramp.color_ramp.elements[0].color = (
        max(0, 0.013 + h),
        0.068,
        max(0, 0.009 + h),
        1.0,
    )
    ramp.color_ramp.elements[1].color = (
        max(0, 0.038 + h),
        0.148,
        max(0, 0.020 + h),
        1.0,
    )
    ramp.color_ramp.elements[1].position = 0.7
    bsdf.inputs["Roughness"].default_value = float(rng.uniform(0.58, 0.72))
    mxs.inputs["Fac"].default_value = 0.25
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"], trans.inputs["Color"])
    nt.links.new(bsdf.outputs["BSDF"], mxs.inputs[2])
    nt.links.new(trans.outputs["BSDF"], mxs.inputs[1])
    nt.links.new(mxs.outputs["Shader"], out.inputs["Surface"])
    return mat


class ProcShrub:
    def __init__(self, seed=0, max_h=0.85, max_sp=0.20):
        self.seed = seed
        rng = np.random.default_rng(seed)
        self.n_stems = int(rng.integers(4, 8))
        self.max_h = float(rng.uniform(0.60, max_h))
        self.sp = float(rng.uniform(0.10, max_sp))
        self.ls = float(rng.uniform(0.042, 0.065))
        self._rng = rng

    def _path(self, base, angle, lean, h):
        rng = self._rng
        tip = (
            base[0] + lean * math.cos(angle),
            base[1] + lean * math.sin(angle),
            base[2] + h,
        )
        ctrl = _lerp3(base, tip, 0.5)
        ctrl = (
            ctrl[0] + rng.uniform(-0.04, 0.04),
            ctrl[1] + rng.uniform(-0.04, 0.04),
            ctrl[2] + rng.uniform(-0.02, 0.05),
        )
        return [_bez3(base, ctrl, tip, t) for t in np.linspace(0, 1, 4)]

    def spawn(self, loc=(0.0, 0.0, 0.0), name="S", coll=None):
        rng = self._rng
        bm = _shrub_bark(self.seed)
        lm = _shrub_leaf(self.seed)
        sv, sf = [], []
        lv, lf = [], []
        tips = []
        for i in range(self.n_stems):
            ang = i / self.n_stems * math.tau + rng.uniform(-0.25, 0.25)
            lean = self.sp * rng.uniform(0.5, 1.0)
            h = self.max_h * rng.uniform(0.70, 1.20)
            base = (
                loc[0] + math.cos(ang) * 0.02,
                loc[1] + math.sin(ang) * 0.02,
                loc[2],
            )
            path = self._path(base, ang, lean, h)
            radii = np.linspace(0.014, 0.003, 4).tolist()
            _tapcyl(sv, sf, path, radii, 6)
            for _ in range(int(rng.integers(2, 4))):
                t = rng.uniform(0.45, 0.78)
                pt = _bez3(path[0], path[1], path[-1], t)
                ba = rng.uniform(0, math.tau)
                be = rng.uniform(math.radians(25), math.radians(65))
                bl = h * rng.uniform(0.18, 0.40)
                btp = (
                    pt[0] + bl * math.cos(ba) * math.cos(be),
                    pt[1] + bl * math.sin(ba) * math.cos(be),
                    pt[2] + bl * math.sin(be),
                )
                bc = _lerp3(pt, btp, 0.5)
                bp = [_bez3(pt, bc, btp, t2) for t2 in np.linspace(0, 1, 3)]
                _tapcyl(sv, sf, bp, [0.007, 0.005, 0.002], 5)
                tips.append(btp)
        for tip in tips:
            _leafcluster(
                lv, lf, tip, rng, int(rng.integers(10, 16)), self.ls, self.ls * 1.0
            )
        sm = bpy.data.meshes.new(name + "_b")
        sm.from_pydata(sv, [], sf)
        sm.update()
        so = bpy.data.objects.new(name + "_b", sm)
        bpy.context.collection.objects.link(so)
        so.data.materials.append(bm)
        lm2 = bpy.data.meshes.new(name + "_l")
        lm2.from_pydata(lv, [], lf)
        lm2.update()
        for p in lm2.polygons:
            p.use_smooth = True
        lo = bpy.data.objects.new(name + "_l", lm2)
        bpy.context.collection.objects.link(lo)
        lo.data.materials.append(lm)
        lo.parent = so
        bpy.context.view_layer.update()
        if coll:
            UA.to_coll(so, coll)
            UA.to_coll(lo, coll)
        return so


def _fb_ground(tag, cx, cy, dx, dy, C):
    UA._box(tag + "_g", cx, cy, 0.04, dx, dy, 0.08, M["greenstrip"], C)


def _fb_ns(tag, x_inner, side, y0, y1, C):
    if y1 <= y0:
        return
    fw2 = 2.5 / 2.0
    cx = x_inner + (fw2 if side == "e" else -fw2)
    cy = (y0 + y1) / 2.0
    dy = y1 - y0
    _fb_ground(tag, cx, cy, 2.5, dy, C)
    rng = np.random.default_rng(abs(hash(tag)) % 99991)
    n = max(1, int(dy / 2.8))
    for k in range(n):
        y = cy - dy / 2 + (k + 0.5) * dy / n + float(rng.uniform(-0.4, 0.4))
        x = cx + float(rng.uniform(-0.6, 0.6))
        ProcShrub(seed=(abs(hash(tag)) + k) % 99991, max_h=0.85, max_sp=0.18).spawn(
            loc=(x, y, 0.08), name=f"{tag}_s{k}", coll=C
        )


def _fb_ew(tag, y_inner, side, x0, x1, C):
    if x1 <= x0:
        return
    fw2 = 2.5 / 2.0
    cy = y_inner + (fw2 if side == "n" else -fw2)
    cx = (x0 + x1) / 2.0
    dx = x1 - x0
    _fb_ground(tag, cx, cy, dx, 2.5, C)
    rng = np.random.default_rng(abs(hash(tag)) % 99991)
    n = max(1, int(dx / 2.8))
    for k in range(n):
        x = cx - dx / 2 + (k + 0.5) * dx / n + float(rng.uniform(-0.4, 0.4))
        y = cy + float(rng.uniform(-0.6, 0.6))
        ProcShrub(seed=(abs(hash(tag)) + k) % 99991, max_h=0.85, max_sp=0.18).spawn(
            loc=(x, y, 0.08), name=f"{tag}_s{k}", coll=C
        )


# ═══════════════════════════════════════════════════════════════════════════════
# MULTI-MODEL VEHICLE PLACEMENT (openx — all share Grp_Root)
# ═══════════════════════════════════════════════════════════════════════════════
_VEH_EXCL = frozenset(
    {"CameraTarget", "KeyLight", "OrbitCamera", "Camera", "Light", "Sun", "Area"}
)


def place_car(tag, blend_path, at, C, yaw=0.0):
    bp = Path(blend_path)
    if not bp.exists():
        print(f"[car] MISSING: {bp}")
        return []
    with bpy.data.libraries.load(str(bp), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n not in _VEH_EXCL]
    root = None
    objs = []
    for o in dst.objects:
        if o is None:
            continue
        try:
            C.objects.link(o)
        except RuntimeError:
            pass
        objs.append(o)
        if o.name == "Grp_Root" and o.parent is None:
            root = o
    for o in objs:
        o.name = f"{tag}_{o.name}"
    if root is None:
        for o in objs:
            if o.parent is None and o.type == "EMPTY":
                root = o
                break
    if root:
        root.location.x = at[0]
        root.location.y = at[1]
        root.location.z = 0.0
        root.rotation_euler.z = yaw
    else:
        print(f"[car] WARNING: no Grp_Root in {Path(blend_path).name}")
    return objs


CARS = {
    "fiat": OX_BASE / "n1_fiat_ducato_2014/n1_fiat_ducato_2014.blend",
    "bmw": OX_BASE / "m1_bmw_x1_2016/m1_bmw_x1_2016.blend",
    "audi": OX_BASE / "m1_audi_q7_2015/m1_audi_q7_2015.blend",
    "volvo": OX_BASE / "m1_volvo_v60_polestar_2013/m1_volvo_v60_polestar_2013.blend",
    "mini": OX_BASE / "m1_mini_countryman_2016/m1_mini_countryman_2016.blend",
    "hyundai": OX_BASE / "m1_hyundai_tucson_2015/m1_hyundai_tucson_2015.blend",
    "dacia": OX_BASE / "m1_dacia_duster_2010/m1_dacia_duster_2010.blend",
    "gmc": OX_BASE / "n2_gmc_hummer_2021_pickup/n2_gmc_hummer_2021_pickup.blend",
}

# ═══════════════════════════════════════════════════════════════════════════════
# Fix 1: exact _gen_park_tree from all8
# ═══════════════════════════════════════════════════════════════════════════════
_TREE_SEEDS = [42, 137, 256, 381, 512, 619, 734, 851, 923, 1044]


def _gen_park_tree(tag, tx, ty, C, seed=42, scale=1.0):
    """Spawn a TreeFactory summer tree at (tx,ty) — exact copy of all8 code."""
    from infinigen.assets.objects.trees.generate import TreeFactory

    print(f"[all10] Generating tree {tag} at ({tx},{ty}) seed={seed} ...")
    try:
        with FixedSeed(seed):
            fac = TreeFactory(
                seed=seed, season="summer", coarse=False, fruit_chance=0.0
            )
            root = fac.spawn_asset(0, loc=(tx, ty, 0), rot=(0, 0, 0))
        if root:
            if scale != 1.0:
                root.scale = (scale, scale, scale)
            UA.to_coll(root, C)
            for o in list(bpy.data.objects):
                if o != root and root in [p for p in [o.parent] if p]:
                    UA.to_coll(o, C)
            print(f"[all10] Tree {tag} done (root={root.name})")
        return root
    except Exception as e:
        print(f"[all10] TreeFactory error for {tag}: {e}")
        UA.build_tree(tag, tx, ty, C, trunk_h=3.5, canopy_r=3.2)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# SCENE CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════
R = 4.5
SW = 3.5
FW = 2.5
S1 = R + SW
G1 = S1 + FW
ARM = 50.0
FULL = R + ARM
LC = R / 2

C_road = UA.new_coll("Road")
C_sw = UA.new_coll("Sidewalks")
C_fb = UA.new_coll("FlowerBeds")
C_mk = UA.new_coll("RoadMarkings")
C_tl = UA.new_coll("TrafficLights")
C_res = UA.new_coll("Residential")
C_park = UA.new_coll("Park")
C_com = UA.new_coll("Commercial")
C_empty = UA.new_coll("Empty")
C_furn = UA.new_coll("Furniture")
C_lamp = UA.new_coll("Lamps")
C_cars = UA.new_coll("Vehicles")
C_tree = UA.new_coll("Trees")


def _box(n, cx, cy, cz, dx, dy, dz, mat, coll, bev=0.0, rz=0.0):
    return UA._box(n, cx, cy, cz, dx, dy, dz, mat, coll, bev=bev, rz=rz)


def _cyl(n, cx, cy, cz, r, h, mat, coll, verts=24, rx=0.0, rz=0.0):
    return UA._cyl(n, cx, cy, cz, r, h, mat, coll, verts=verts, rx=rx, rz=rz)


def _sph(n, cx, cy, cz, r, mat, coll, segs=16, rings=12):
    return UA._sph(n, cx, cy, cz, r, mat, coll, segs=segs, rings=rings)


# ─── GROUND ──────────────────────────────────────────────────────────────────
_box("gnd", 0, 0, -0.10, 400, 400, 0.20, M["soil"], C_sw)

bpy.ops.mesh.primitive_grid_add(
    x_subdivisions=250,
    y_subdivisions=250,
    size=1.0,
    location=(G1 + ARM / 2, G1 + ARM / 2, 0.005),
)
park_gnd = bpy.context.active_object
park_gnd.name = "park_lawn_grid"
park_gnd.scale = (ARM, ARM, 1.0)
bpy.ops.object.transform_apply(scale=True)
park_gnd.data.materials.append(M["grass"])
UA.to_coll(park_gnd, C_park)

_box(
    "sw_lawn",
    -(G1 + ARM / 2),
    -(G1 + ARM / 2),
    0.005,
    ARM,
    ARM,
    0.01,
    M["grass"],
    C_empty,
)
_box(
    "w_lawn_n",
    -(G1 + ARM / 2),
    G1 + ARM / 4,
    0.005,
    ARM,
    ARM / 2 + G1,
    0.01,
    M["grass"],
    C_empty,
)
_box(
    "w_lawn_s",
    -(G1 + ARM / 2),
    -(G1 + ARM / 4),
    0.005,
    ARM,
    ARM / 2 + G1,
    0.01,
    M["grass"],
    C_empty,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ROAD + SIDEWALK + KERBS  (dark M["road"] — from build_all_materials)
# ═══════════════════════════════════════════════════════════════════════════════
_box("isect", 0, 0, -0.02, 2 * R, 2 * R, 0.04, M["road"], C_road)
for ys, t in [(+1, "n"), (-1, "s")]:
    yc = ys * (R + ARM / 2)
    _box(f"road_{t}", 0, yc, -0.02, 2 * R, ARM, 0.04, M["road"], C_road)
    _box(f"sw_{t}_e", S1 - SW / 2, yc, 0.06, SW, ARM, 0.12, M["sidewalk"], C_sw)
    _box(f"sw_{t}_w", -(S1 - SW / 2), yc, 0.06, SW, ARM, 0.12, M["sidewalk"], C_sw)
    _box(f"kb_{t}_e", R + 0.08, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)
    _box(f"kb_{t}_w", -R - 0.08, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)
for xs, t in [(+1, "e"), (-1, "w")]:
    xc = xs * (R + ARM / 2)
    _box(f"road_{t}", xc, 0, -0.02, ARM, 2 * R, 0.04, M["road"], C_road)
    _box(f"sw_{t}_n", xc, S1 - SW / 2, 0.06, ARM, SW, 0.12, M["sidewalk"], C_sw)
    _box(f"sw_{t}_s", xc, -(S1 - SW / 2), 0.06, ARM, SW, 0.12, M["sidewalk"], C_sw)
    _box(f"kb_{t}_n", xc, R + 0.08, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)
    _box(f"kb_{t}_s", xc, -R - 0.08, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)
for xs, ys in [(1, 1), (1, -1), (-1, 1), (-1, -1)]:
    _box(
        f"sw_cor{xs}{ys}",
        xs * (R + SW / 2),
        ys * (R + SW / 2),
        0.06,
        SW,
        SW,
        0.12,
        M["sidewalk"],
        C_sw,
    )

# ═══════════════════════════════════════════════════════════════════════════════
# Fix 2: ROAD MARKINGS — exact all4 style adapted to R=4.5, ARM=50
# Yellow double-solid centre lines + white lane dashes + crosswalks + stop lines
# ═══════════════════════════════════════════════════════════════════════════════
# Yellow double-solid centre lines (same offsets as all4: ±0.08, width 0.06)
for dx in (-0.08, 0.08):
    _box(
        f"cl_ns_{dx:.2f}", dx, 0, 0.003, 0.06, 2 * (R + ARM), 0.004, M["stripe_y"], C_mk
    )
    _box(
        f"cl_ew_{dx:.2f}", 0, dx, 0.003, 2 * (R + ARM), 0.06, 0.004, M["stripe_y"], C_mk
    )

# White lane dashes (same pattern as all4: sides ±2.25, 7 evenly spaced per half-arm)
# all4: yi in range(2,9), y0 = R + yi*(ARM/9) → adapted: same formula with R=4.5, ARM=50
for yi in range(2, 10):
    y0 = R + yi * (ARM / 10)
    for side in [LC, -LC]:  # ±2.25 m (lane centres)
        _box(
            f"dash_n{yi}_{side:.2f}",
            side,
            y0,
            0.003,
            0.12,
            1.8,
            0.004,
            M["stripe_w"],
            C_mk,
        )
        _box(
            f"dash_s{yi}_{side:.2f}",
            side,
            -y0,
            0.003,
            0.12,
            1.8,
            0.004,
            M["stripe_w"],
            C_mk,
        )
for xi in range(2, 10):
    x0 = R + xi * (ARM / 10)
    for side in [LC, -LC]:
        _box(
            f"dash_e{xi}_{side:.2f}",
            x0,
            side,
            0.003,
            1.8,
            0.12,
            0.004,
            M["stripe_w"],
            C_mk,
        )
        _box(
            f"dash_w{xi}_{side:.2f}",
            -x0,
            side,
            0.003,
            1.8,
            0.12,
            0.004,
            M["stripe_w"],
            C_mk,
        )

# Crosswalks — 8 stripes per arm (exact all4 dimensions, adapted to R=4.5)
for stripe in range(8):
    xf = -R + 0.5 + stripe * (2 * R - 1.0) / 8
    _box(f"xwk_s{stripe}", xf, -(R + 0.6), 0.004, 0.78, 2.2, 0.005, M["xwalk"], C_mk)
    _box(f"xwk_n{stripe}", xf, (R + 0.6), 0.004, 0.78, 2.2, 0.005, M["xwalk"], C_mk)
for stripe in range(8):
    yf = -R + 0.5 + stripe * (2 * R - 1.0) / 8
    _box(f"xwk_e{stripe}", (R + 0.6), yf, 0.004, 2.2, 0.78, 0.005, M["xwalk"], C_mk)
    _box(f"xwk_w{stripe}", -(R + 0.6), yf, 0.004, 2.2, 0.78, 0.005, M["xwalk"], C_mk)

# Stop lines (exact all4 position: RW+2.0 from centre)
for sign, sfx in [(1, "n"), (-1, "s")]:
    _box(
        f"stop_{sfx}",
        0,
        sign * (R + 2.0),
        0.004,
        2 * R,
        0.4,
        0.005,
        M["stripe_w"],
        C_mk,
    )
for sign, sfx in [(1, "e"), (-1, "w")]:
    _box(
        f"stop_{sfx}",
        sign * (R + 2.0),
        0,
        0.004,
        0.4,
        2 * R,
        0.005,
        M["stripe_w"],
        C_mk,
    )

# ─── TRAFFIC LIGHTS ──────────────────────────────────────────────────────────
UA.place_trafficlight((0.0, -(R + 2.6)), C_tl, yaw=0)
UA.place_trafficlight((0.0, (R + 2.6)), C_tl, yaw=math.pi)
UA.place_trafficlight((-(R + 2.6), 0.0), C_tl, yaw=-math.pi / 2)
UA.place_trafficlight(((R + 2.6), 0.0), C_tl, yaw=math.pi / 2)

# ─── FLOWER BEDS ─────────────────────────────────────────────────────────────
print("[all10] Building roadside flower beds ...")
_fb_ns("fb_ne1", S1, "e", R, 11.0, C_fb)
_fb_ns("fb_ne2", S1, "e", 15.5, R + ARM, C_fb)
_fb_ns("fb_nw1", -S1, "w", R, R + ARM, C_fb)
_fb_ns("fb_se1", S1, "e", -(R + ARM), -R, C_fb)
_fb_ns("fb_sw1", -S1, "w", -(R + ARM), -R, C_fb)
_fb_ew("fb_en1", S1, "n", R, 12.0, C_fb)
_fb_ew("fb_en2", S1, "n", 17.0, R + ARM, C_fb)
_fb_ew("fb_es1", -S1, "s", R, R + ARM, C_fb)
_fb_ew("fb_wn1", S1, "n", -(R + ARM), -R, C_fb)
_fb_ew("fb_ws1", -S1, "s", -(R + ARM), -R, C_fb)
print("[all10] Flower beds done.")

# ─── STREET LAMPS ────────────────────────────────────────────────────────────
for y in [8, 16, 24, 32, 40, 48]:
    UA.place_streetlight((S1 - SW / 2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-S1 + SW / 2, y), C_lamp, yaw=-math.pi / 2, day=True)
for y in [-8, -16, -24, -32, -40, -48]:
    UA.place_streetlight((S1 - SW / 2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-S1 + SW / 2, y), C_lamp, yaw=-math.pi / 2, day=True)
for x in [8, 16, 24, 32, 40, 48]:
    UA.place_streetlight((x, S1 - SW / 2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -S1 + SW / 2), C_lamp, yaw=0.0, day=True)
for x in [-8, -16, -24, -32, -40, -48]:
    UA.place_streetlight((x, S1 - SW / 2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -S1 + SW / 2), C_lamp, yaw=0.0, day=True)

UA.place_busstop((S1 - SW / 2, 13.0), C_furn, yaw=-math.pi / 2, scale=1.4)

# ═══════════════════════════════════════════════════════════════════════════════
# NW — RESIDENTIAL
# ═══════════════════════════════════════════════════════════════════════════════
print("[all10] Building residential zone ...")
CMP_E, CMP_W = -G1 - 1.5, -55.0
CMP_S, CMP_N = G1 + 1.5, 58.0
CMP_CX = (CMP_E + CMP_W) / 2
CMP_CY = (CMP_S + CMP_N) / 2
_box(
    "res_marble",
    CMP_CX,
    CMP_CY,
    0.01,
    abs(CMP_W - CMP_E),
    CMP_N - CMP_S,
    0.02,
    M["marble"],
    C_res,
)
FH = 1.6
GATE_W = 4.5
GHW = GATE_W / 2
CW = abs(CMP_W - CMP_E)
CD = CMP_N - CMP_S
_box("res_fn", CMP_CX, CMP_N, FH / 2, CW, 0.10, FH, M["fence_iron"], C_res)
_box("res_fe", CMP_E, CMP_CY, FH / 2, 0.10, CD, FH, M["fence_iron"], C_res)
_box("res_fw", CMP_W, CMP_CY, FH / 2, 0.10, CD, FH, M["fence_iron"], C_res)
for x0, x1, sfx in [(CMP_E, CMP_CX - GHW, "lo"), (CMP_CX + GHW, CMP_W, "hi")]:
    seg = abs(x1 - x0)
    if seg > 0.2:
        _box(
            f"res_fs_{sfx}",
            (x0 + x1) / 2,
            CMP_S,
            FH / 2,
            seg,
            0.10,
            FH,
            M["fence_iron"],
            C_res,
        )
for gx in [CMP_CX - GHW, CMP_CX + GHW]:
    _cyl(
        f"res_gp{gx:.0f}", gx, CMP_S, 0, 0.12, FH + 0.5, M["gate_post"], C_res, verts=8
    )
for px, py in [(CMP_E, CMP_N), (CMP_W, CMP_N), (CMP_E, CMP_S), (CMP_W, CMP_S)]:
    _cyl(
        f"res_cp{px:.0f}{py:.0f}",
        px,
        py,
        0,
        0.10,
        FH + 0.3,
        M["gate_post"],
        C_res,
        verts=8,
    )
_box(
    "res_ep",
    CMP_CX,
    (CMP_S + 27) / 2,
    0.03,
    GATE_W + 0.5,
    27 - CMP_S,
    0.04,
    M["stone_path"],
    C_res,
)

APT_CX = CMP_CX
APT_SY = 27.0
APT_W = 30.0
APT_D = 14.0
APT_FL = 6
APT_FH = 3.2
APT_H = APT_FL * APT_FH
APT_CY = APT_SY + APT_D / 2
_box(
    "apt_body",
    APT_CX,
    APT_CY,
    APT_H / 2,
    APT_W,
    APT_D,
    APT_H,
    M["wall_apt"],
    C_res,
    bev=0.02,
)
_box("apt_roof", APT_CX, APT_CY, APT_H + 0.10, APT_W, APT_D, 0.20, M["apt_roof"], C_res)
_box(
    "apt_prpt", APT_CX, APT_SY, APT_H + 0.42, APT_W + 0.10, 0.40, 0.85, M["balc"], C_res
)
N_COLS = 8
for fl in range(APT_FL):
    z_w = fl * APT_FH + APT_FH * 0.52
    for col in range(N_COLS):
        wx = APT_CX - APT_W / 2 + (col + 0.5) * APT_W / N_COLS
        if fl == 0 and abs(col - 3.5) < 1.1:
            continue
        _box(
            f"apt_w{fl}_{col}",
            wx,
            APT_SY - 0.06,
            z_w,
            APT_W / N_COLS * 0.58,
            0.12,
            APT_FH * 0.58,
            M["apt_glass"],
            C_res,
        )
_box(
    "apt_lobby",
    APT_CX,
    APT_SY - 0.06,
    APT_FH * 0.62,
    5.8,
    0.14,
    APT_FH * 1.24,
    M["apt_glass"],
    C_res,
)
_box(
    "apt_canopy",
    APT_CX,
    APT_SY - 1.8,
    APT_H * 0.20,
    8.0,
    3.6,
    0.18,
    M["apt_roof"],
    C_res,
)
N_BALC = 6
for fl in range(1, APT_FL):
    z_f = fl * APT_FH
    for b in range(N_BALC):
        bx = APT_CX - APT_W / 2 + (b + 0.5) * APT_W / N_BALC
        _box(
            f"apt_bs{fl}_{b}",
            bx,
            APT_SY - 1.0,
            z_f + 0.10,
            APT_W / N_BALC * 0.78,
            2.0,
            0.14,
            M["balc"],
            C_res,
        )
        _box(
            f"apt_br{fl}_{b}",
            bx,
            APT_SY - 1.95,
            z_f + 0.72,
            APT_W / N_BALC * 0.78,
            0.06,
            1.10,
            M["balc_rail"],
            C_res,
        )
for fl in range(APT_FL):
    z_w = fl * APT_FH + APT_FH * 0.52
    for row in range(3):
        wy = APT_SY + (row + 0.5 + 0.5) * APT_D / 4
        for xf, sfx in [(APT_CX - APT_W / 2, "w"), (APT_CX + APT_W / 2, "e")]:
            sign = -1 if sfx == "w" else 1
            _box(
                f"apt_sw{fl}_{row}_{sfx}",
                xf + sign * 0.06,
                wy,
                z_w,
                0.12,
                APT_D / 4 * 0.55,
                APT_FH * 0.55,
                M["apt_glass"],
                C_res,
            )
for i, (sx, sy, sd) in enumerate(
    [(-20, 20, 3), (-22, 45, 7), (-38, 20, 11), (-36, 48, 15), (-48, 32, 19)]
):
    ProcShrub(seed=sd, max_h=1.0, max_sp=0.20).spawn(
        loc=(sx, sy, 0.04), name=f"ysh{i}", coll=C_res
    )
print("[all10] Residential done.")

# ═══════════════════════════════════════════════════════════════════════════════
# NE — PARK
# ═══════════════════════════════════════════════════════════════════════════════
print("[all10] Building park zone ...")
PARK_X0, PARK_X1 = G1, G1 + ARM
PARK_Y0, PARK_Y1 = G1, G1 + ARM
PARK_CX = (PARK_X0 + PARK_X1) / 2
PARK_CY = (PARK_Y0 + PARK_Y1) / 2

try:
    from infinigen.assets.scatters.flowerplant import Flowerplant

    with FixedSeed(42):
        Flowerplant().apply(park_gnd, selection=None, density=0.6)
    print("[all10] Flowerplant scatter done")
except Exception as e:
    print(f"[all10] Flowerplant: {e}")

_cyl("pk_gp1", 14.0, G1 + 0.3, 0, 0.15, 2.6, M["gate_post"], C_park, verts=8)
_cyl("pk_gp2", 17.0, G1 + 0.3, 0, 0.15, 2.6, M["gate_post"], C_park, verts=8)
_box("pk_ep", 15.5, (S1 + G1) / 2, 0.04, 4.5, FW, 0.08, M["stone_path"], C_park)
_box(
    "ppth_ns",
    16.0,
    PARK_CY,
    0.05,
    2.5,
    PARK_Y1 - PARK_Y0,
    0.10,
    M["park_stone"],
    C_park,
)
_box(
    "ppth_ew",
    PARK_CX,
    28.0,
    0.05,
    PARK_X1 - PARK_X0,
    2.5,
    0.10,
    M["park_stone"],
    C_park,
)
_box(
    "ppth_s2",
    PARK_CX,
    20.0,
    0.05,
    PARK_X1 - PARK_X0,
    2.0,
    0.10,
    M["park_stone"],
    C_park,
)
bpy.ops.mesh.primitive_cylinder_add(
    vertices=32, radius=6.2, depth=0.10, location=(34, 32, 0.06)
)
plz = bpy.context.active_object
plz.name = "pk_plaza"
plz.data.materials.append(M["park_stone"])
UA.to_coll(plz, C_park)

pav_objs = UA._import_prefix(SC_BLEND, "pav:", C_park)
if pav_objs:
    UA._place(pav_objs, 34.0, 32.0)
    print(f"[all10] Pavilion: {len(pav_objs)} obj")
else:
    _cyl("pav_base", 34, 32, 0, 4.2, 0.35, M["park_stone"], C_park, verts=6)
    for i in range(6):
        a = i * math.pi / 3
        _cyl(
            f"pav_col{i}",
            34 + 2.6 * math.cos(a),
            32 + 2.6 * math.sin(a),
            0.35,
            0.18,
            3.4,
            M["park_stone"],
            C_park,
            verts=12,
        )
    bpy.ops.mesh.primitive_cone_add(
        radius1=3.8, radius2=0.25, depth=1.8, location=(34, 32, 5.15)
    )
    cn = bpy.context.active_object
    cn.name = "pav_cone"
    cn.data.materials.append(M["roof_tile"])
    UA.to_coll(cn, C_park)

band_objs = UA._import_prefix(SC_BLEND, "band:", C_park)
if band_objs:
    UA._place(band_objs, 22.0, 22.0)
    print(f"[all10] Bandstand: {len(band_objs)} obj")

_mat_ct = UA._pbr("ct_mat", (0.48, 0.22, 0.06), rough=0.72)
for i in range(3):
    ang = i * math.pi / 3
    ox, oy = 48 + math.cos(ang) * 1.2, 20 + math.sin(ang) * 1.2
    bpy.ops.mesh.primitive_torus_add(
        major_radius=1.5,
        minor_radius=0.18,
        location=(ox, oy, 1.8 + 0.3),
        rotation=(math.radians(60 + i * 30), 0, ang),
    )
    o = bpy.context.active_object
    o.name = f"ct_ring{i}"
    o.data.materials.append(_mat_ct)
    UA.to_coll(o, C_park)

_cyl("fnt_rim", 26, 20, 0.0, 2.5, 0.44, M["pool_rim"], C_park, verts=32)
_cyl("fnt_pool", 26, 20, 0.08, 2.2, 0.30, M["water_blue"], C_park, verts=32)
_cyl("fnt_col", 26, 20, 0.38, 0.14, 1.40, M["pool_rim"], C_park, verts=12)
_sph("fnt_top", 26, 20, 2.04 + 0.26, 0.26, M["water_blue"], C_park, segs=12, rings=8)

for tag, px, py, dx, dy in [
    ("pfb1", 45, 16, 5, 3),
    ("pfb2", 50, 42, 5, 3),
    ("pfb3", 20, 44, 4, 2.5),
]:
    _fb_ground(tag, px, py, dx, dy, C_park)
    rng2 = np.random.default_rng(abs(hash(tag)) % 99991)
    for k in range(6):
        sx = px + float(rng2.uniform(-dx / 2 + 0.4, dx / 2 - 0.4))
        sy = py + float(rng2.uniform(-dy / 2 + 0.3, dy / 2 - 0.3))
        ProcShrub(seed=(abs(hash(tag)) + k) % 99991, max_h=1.1, max_sp=0.22).spawn(
            loc=(sx, sy, 0.05), name=f"{tag}_s{k}", coll=C_park
        )

for bx2, by2, byw in [
    (18.5, 26.0, math.pi / 2),
    (26.0, 38.0, 0.0),
    (40.0, 24.0, math.pi / 2),
    (44.0, 40.0, 0.0),
    (16.0, 44.0, 0.0),
]:
    UA.place_bench_classic((bx2, by2), C_park, yaw=byw)
for bx2, by2 in [(22.0, 32.0), (38.0, 46.0), (48, 28)]:
    UA.place_bin_domed((bx2, by2), C_park)

# Fix 1: exact all8 TreeFactory trees
print("[all10] Placing park trees (TreeFactory — exact all8) ...")
park_trees = [
    (17, 17, 42, 1.1),
    (26, 44, 137, 1.0),
    (40, 15, 256, 1.1),
    (48, 42, 381, 1.0),
    (32, 46, 512, 1.0),
    (15, 38, 619, 1.2),
    (46, 26, 734, 1.1),
    (52, 16, 851, 1.0),
    (24, 16, 923, 0.9),
    (44, 32, 1044, 1.1),
]
for i, (tx, ty, seed, sc) in enumerate(park_trees):
    _gen_park_tree(f"pk_tr{i}", tx, ty, C_tree, seed=seed, scale=sc)
print("[all10] Park done.")

# ═══════════════════════════════════════════════════════════════════════════════
# SE — COMMERCIAL
# ═══════════════════════════════════════════════════════════════════════════════
print("[all10] Building commercial zone ...")
COM_X0, COM_X1 = G1, G1 + ARM
COM_Y0, COM_Y1 = -(G1 + ARM), -G1
_box(
    "com_marble",
    (COM_X0 + COM_X1) / 2,
    (COM_Y0 + COM_Y1) / 2,
    0.01,
    ARM,
    ARM,
    0.02,
    M["marble"],
    C_com,
)

SHOP_X = G1 + 10.0
SHOP_D = 14.0
SHOP_H = 5.0
SHOP_W = 14.0


def _shopW(tag, cx, cy, w, d, h, mat, aw_mat, C):
    _box(f"{tag}_b", cx, cy, h / 2, d, w, h, mat, C, bev=0.02)
    _box(
        f"{tag}_gl",
        cx - d / 2 + 0.08,
        cy,
        h * 0.38,
        0.10,
        w * 0.68,
        h * 0.52,
        M["apt_glass"],
        C,
    )
    _box(
        f"{tag}_aw",
        cx - d / 2 - 0.80,
        cy,
        h * 0.72,
        1.60,
        w * 0.82,
        0.12,
        aw_mat,
        C,
        rz=math.radians(-5),
    )
    _box(
        f"{tag}_sg",
        cx - d / 2 + 0.08,
        cy,
        h * 0.86,
        0.16,
        w * 0.72,
        0.50,
        M["sign_comm"],
        C,
    )
    _box(f"{tag}_dr", cx - d / 2 + 0.06, cy, 1.25, 0.12, 1.20, 2.50, M["door"], C)


_shopW("shA", SHOP_X, -17.0, SHOP_W, SHOP_D, SHOP_H, M["shop_w"], M["awning_r"], C_com)
_shopW("shB", SHOP_X, -32.0, SHOP_W, SHOP_D, SHOP_H, M["shop_r"], M["awning_g"], C_com)
_shopW("shC", SHOP_X, -47.0, SHOP_W, SHOP_D, SHOP_H, M["shop_b"], M["awning_b"], C_com)
for sy in [-17, -32, -47]:
    _box(f"com_path{sy}", G1 + 2.5, sy, 0.04, 5.0, 3.5, 0.05, M["stone_path"], C_com)
_box("bike_pad", G1 + 5.0, -21.0, 0.04, 10.0, 7.0, 0.05, M["stone_path"], C_com)
UA.place_bicycle_station((G1 + 5.0, -21.0), C_com, yaw=0)
UA.place_bench_classic((G1 + 2.0, -27.0), C_furn, yaw=math.pi / 2)
UA.place_bench_classic((G1 + 2.0, -42.0), C_furn, yaw=math.pi / 2)
UA.place_bin_domed((G1 + 2.0, -34.0), C_furn)
UA.place_phonebooth((G1 + 1.5, -14.0), C_com, yaw=-math.pi / 2)
UA.place_kiosk5((S1 - SW / 2, -38.0), C_com, yaw=-math.pi / 2, scale=0.85)
print("[all10] Commercial done.")

# ═══════════════════════════════════════════════════════════════════════════════
# VEHICLES
# yaw: 0=east(+X), π/2=north(+Y), π=west(-X), -π/2=south(-Y)
# ═══════════════════════════════════════════════════════════════════════════════
print("[all10] Placing vehicles ...")
place_car("vn1", CARS["bmw"], (LC, 20.0), C_cars, yaw=math.pi / 2)
place_car("vn2", CARS["volvo"], (LC, 34.0), C_cars, yaw=math.pi / 2)
place_car("vn3", CARS["audi"], (-LC, 27.0), C_cars, yaw=-math.pi / 2)
place_car("vs1", CARS["mini"], (LC, -18.0), C_cars, yaw=-math.pi / 2)
place_car("vs2", CARS["hyundai"], (-LC, -14.0), C_cars, yaw=math.pi / 2)
place_car("ve1", CARS["fiat"], (22.0, -LC), C_cars, yaw=0)
place_car("ve2", CARS["dacia"], (38.0, -LC), C_cars, yaw=0)
place_car("ve3", CARS["gmc"], (20.0, LC), C_cars, yaw=math.pi)
place_car("vw1", CARS["bmw"], (-26.0, LC), C_cars, yaw=math.pi)
place_car("vw2", CARS["volvo"], (-40.0, -LC), C_cars, yaw=0)
print("[all10] Vehicles placed.")

# ═══════════════════════════════════════════════════════════════════════════════
# LIGHTING
# ═══════════════════════════════════════════════════════════════════════════════
bpy.context.scene.world = bpy.data.worlds.new("sky_a10")
bpy.context.scene.world.use_nodes = True
wt = bpy.context.scene.world.node_tree
wt.nodes.clear()
bg = wt.nodes.new("ShaderNodeBackground")
sky = wt.nodes.new("ShaderNodeTexSky")
lp = wt.nodes.new("ShaderNodeLightPath")
mix = wt.nodes.new("ShaderNodeMixShader")
bg2 = wt.nodes.new("ShaderNodeBackground")
out = wt.nodes.new("ShaderNodeOutputWorld")
sky.sky_type = "NISHITA"
sky.sun_elevation = math.radians(40)
sky.sun_rotation = math.radians(210)
sky.altitude = 800.0
sky.air_density = 1.0
sky.dust_density = 0.4
bg.inputs["Strength"].default_value = 1.0
bg2.inputs["Strength"].default_value = 0.0
wt.links.new(sky.outputs["Color"], bg.inputs["Color"])
wt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
wt.links.new(bg.outputs["Background"], mix.inputs[1])
wt.links.new(bg2.outputs["Background"], mix.inputs[2])
wt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
bpy.ops.object.light_add(type="SUN", location=(20, -40, 60))
sun = bpy.context.active_object
sun.name = "Sun_a10"
sun.data.energy = 5.0
sun.data.angle = math.radians(0.5)
sun.rotation_euler[0] = math.radians(50)
sun.rotation_euler[2] = math.radians(210)

# ─── RENDER ──────────────────────────────────────────────────────────────────
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = "PNG"
sc.cycles.samples = 256
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = "OPTIX"
except:
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except:
        pass
sc.cycles.device = "GPU"
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = -2.2
    sc.view_settings.gamma = 1.0
except Exception as e:
    print(f"[all10] AgX: {e}")


def make_cam(name, loc, target, fov=58):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name
    cam.data.name = name
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov)
    dv = Vector(target) - Vector(loc)
    if dv.length > 0:
        cam.rotation_euler = dv.to_track_quat("-Z", "Y").to_euler()
    return cam


cam_ov = make_cam("cam_overview", (5, -75, 95), (0, 10, 0), 64)
cam_rs = make_cam("cam_residential", (15, 5, 28), (-30, 36, 8), 58)
cam_pk = make_cam("cam_park", (-12, 8, 22), (34, 38, 4), 64)
cam_cm = make_cam("cam_commercial", (5, -5, 20), (32, -30, 4), 60)
cam_ix = make_cam("cam_intersection", (-20, -22, 18), (0, 0, 0), 56)

bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_v3_all10.blend"))
print("[all10] Blend saved.")
for cam, fname in [
    (cam_ov, "overview.png"),
    (cam_rs, "residential.png"),
    (cam_pk, "park.png"),
    (cam_cm, "commercial.png"),
    (cam_ix, "intersection.png"),
]:
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all10] Rendering {fname} ...")
    bpy.ops.render.render(write_still=True)
    print(f"[all10] Done: {fname}")
print("[all10] All complete.")

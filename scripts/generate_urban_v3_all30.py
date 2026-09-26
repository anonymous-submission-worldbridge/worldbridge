"""
generate_urban_v3_all30.py
==========================
4-zone crossroads — based on all29. Changes vs all29:
  1. Park sculpture (chrome trefoil) re-centred on the marble disk (centre by the
     ribbon-loop bbox, not the origin bbox that was skewed toward the plinth).
  2. Road surface → dark ASPHALT (matches urban_v3_all18) instead of grey
     concrete; existing lane lines (yellow centre + white dashes + arrows +
     crosswalks + stop bars) and light concrete sidewalks are kept.
  3. Vehicles → 18 DIVERSE real imported models from openx assets (Fiat Ducato,
     BMW X1, Audi Q7/TT, Volvo V60/EX30, Mini, Hyundai Tucson, Dacia Duster, GMC
     Hummer, Tesla Cybertruck, Mercedes SL65) — NOT the simple procedural cars.
  Everything else unchanged from all29.

Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all30/
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


import sys, math, os, random, re
from pathlib import Path

# ─── PATH SETUP ───────────────────────────────────────────────────────────────
REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
CONDA = Path(f"{_wb_WORLDBRIDGE_SITE_PACKAGES}")
sys.path.insert(0, str(REPO))
if CONDA.exists():
    sys.path.insert(0, str(CONDA))
sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/scripts")

import bpy
import numpy as np
from mathutils import Vector, Matrix
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

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all30")
SC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_sculpture/public_art.blend"
)
OX_BASE = Path(
    f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main"
)  # real vehicle assets
FULL_REVISION = os.environ.get("C2W_FULL_REVISION", "")
FULL06_LANDSCAPE = FULL_REVISION in (
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
)
FULL07 = FULL_REVISION in ("urban_v1_full_07", "urban_v1_full_08")
LAYOUT_MODE = os.environ.get("C2W_URBAN_LAYOUT", "crossroads")
if LAYOUT_MODE not in {"crossroads", "linear_street", "t_junction"}:
    raise ValueError(
        f"Unsupported C2W_URBAN_LAYOUT={LAYOUT_MODE!r}; expected crossroads, "
        "linear_street, or t_junction"
    )
OUT.mkdir(parents=True, exist_ok=True)

# ─── SCENE RESET + GPU ────────────────────────────────────────────────────────
UA.reset_scene()
bpy.context.scene.render.engine = "CYCLES"
try:
    from infinigen.core.init import configure_cycles_devices

    configure_cycles_devices()
except Exception as _e:
    print(f"[all8] GPU note: {_e}")

try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
except Exception as _e:
    print(f"[all8] OPTIX: {_e}")
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
    except Exception as _e2:
        print(f"[all8] CUDA: {_e2}")

print(f"[all8] GPU device = {bpy.context.scene.cycles.device}")

# ═══════════════════════════════════════════════════════════════════════════════
# PROCEDURAL MATERIAL LIBRARY
# ═══════════════════════════════════════════════════════════════════════════════


def _set(b, name, v):
    if name in b.inputs:
        b.inputs[name].default_value = v


def _pbr2(name, color, roughness=0.6, metallic=0.0):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    _set(b, "Base Color", (*color, 1.0))
    _set(b, "Roughness", roughness)
    _set(b, "Metallic", metallic)
    return m


def concrete_road_mat(name="a8_concrete_road"):
    """Layered-noise concrete for road surface (grey, slightly textured)."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")

    n_lg = nodes.new("ShaderNodeTexNoise")  # poured sections ~3m
    n_lg.inputs["Scale"].default_value = 0.32
    n_lg.inputs["Detail"].default_value = 4.0
    links.new(tex.outputs["Object"], n_lg.inputs["Vector"])

    vor = nodes.new("ShaderNodeTexVoronoi")  # aggregate pitting
    vor.inputs["Scale"].default_value = 12.0
    links.new(tex.outputs["Object"], vor.inputs["Vector"])

    n_fi = nodes.new("ShaderNodeTexNoise")  # micro grain
    n_fi.inputs["Scale"].default_value = 22.0
    n_fi.inputs["Detail"].default_value = 12.0
    links.new(tex.outputs["Object"], n_fi.inputs["Vector"])

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.46, 0.45, 0.43, 1.0)
    ramp.color_ramp.elements[1].color = (0.58, 0.57, 0.55, 1.0)
    links.new(n_lg.outputs["Fac"], ramp.inputs["Fac"])

    spk = nodes.new("ShaderNodeValToRGB")
    spk.color_ramp.elements[0].position = 0.4
    spk.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    spk.color_ramp.elements[1].position = 0.85
    spk.color_ramp.elements[1].color = (0.08, 0.08, 0.07, 1.0)
    links.new(vor.outputs["Distance"], spk.inputs["Fac"])

    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "ADD"
    mix.inputs["Fac"].default_value = 0.12
    links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    links.new(spk.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    _set(bsdf, "Roughness", 0.90)

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.25
    bump.inputs["Distance"].default_value = 0.005
    mixb = nodes.new("ShaderNodeMixRGB")
    mixb.inputs["Fac"].default_value = 0.55
    links.new(vor.outputs["Distance"], mixb.inputs["Color1"])
    links.new(n_fi.outputs["Fac"], mixb.inputs["Color2"])
    links.new(mixb.outputs["Color"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def concrete_sidewalk_mat(name="a8_sidewalk"):
    """Lighter concrete with faint tile joints for sidewalks."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    mp = nodes.new("ShaderNodeMapping")
    mp.inputs["Scale"].default_value = (0.5, 0.5, 1.0)
    links.new(tex.outputs["Object"], mp.inputs["Vector"])

    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 8.0
    n1.inputs["Detail"].default_value = 6.0
    links.new(mp.outputs["Vector"], n1.inputs["Vector"])

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.72, 0.71, 0.69, 1.0)
    ramp.color_ramp.elements[1].color = (0.82, 0.81, 0.79, 1.0)
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.84)

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.15
    links.new(n1.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def grass_mat(name="a8_grass", colors=None):
    """Rich two-tone grass with an explicit palette for semantic lawns."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    n1 = nodes.new("ShaderNodeTexNoise")
    n1.inputs["Scale"].default_value = 12.0
    n1.inputs["Detail"].default_value = 10.0
    links.new(tex.outputs["Object"], n1.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    colors = colors or ((0.035, 0.075, 0.020, 1.0), (0.075, 0.14, 0.045, 1.0))
    ramp.color_ramp.elements[0].color = colors[0]
    ramp.color_ramp.elements[1].color = colors[1]
    links.new(n1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.95)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


def soil_mat(name="a8_soil"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
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


def paint_mat(name, color, wear=0.35):
    """Worn road paint — matches generate_urban_v3_road paint_material."""
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")
    noi = nodes.new("ShaderNodeTexNoise")
    noi.inputs["Scale"].default_value = 40.0
    noi.inputs["Detail"].default_value = 8.0
    links.new(tex.outputs["Object"], noi.inputs["Vector"])
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.5 - wear * 0.5
    ramp.color_ramp.elements[0].color = (
        color[0] * 0.35,
        color[1] * 0.35,
        color[2] * 0.35,
        1.0,
    )
    ramp.color_ramp.elements[1].position = 0.5 + wear * 0.5
    ramp.color_ramp.elements[1].color = (*color, 1.0)
    links.new(noi.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.62)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.05
    links.new(noi.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


# ─── BUILD MATERIAL DICT ─────────────────────────────────────────────────────
UA.build_all_materials()
M = UA.M


# all30: dark ASPHALT road (matches urban_v3_all18 look) instead of grey concrete.
def asphalt_road_mat(name="a30_asphalt"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nds, lks = nt.nodes, nt.links
    for n in list(nds):
        nds.remove(n)
    out = nds.new("ShaderNodeOutputMaterial")
    bsdf = nds.new("ShaderNodeBsdfPrincipled")
    tex = nds.new("ShaderNodeTexCoord")
    nz = nds.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 6.0
    nz.inputs["Detail"].default_value = 10.0
    lks.new(tex.outputs["Object"], nz.inputs["Vector"])
    ramp = nds.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.020, 0.020, 0.022, 1.0)  # near-black asphalt
    ramp.color_ramp.elements[1].color = (
        0.055,
        0.055,
        0.058,
        1.0,
    )  # worn lighter patches
    lks.new(nz.outputs["Fac"], ramp.inputs["Fac"])
    lks.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.80)
    fine = nds.new("ShaderNodeTexNoise")
    fine.inputs["Scale"].default_value = 45.0
    fine.inputs["Detail"].default_value = 10.0
    lks.new(tex.outputs["Object"], fine.inputs["Vector"])
    bump = nds.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    lks.new(fine.outputs["Fac"], bump.inputs["Height"])
    lks.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    lks.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


# Override road + sidewalk + greenstrip with procedural versions
M["road"] = asphalt_road_mat()
M["sidewalk"] = concrete_sidewalk_mat()
M["greenstrip"] = grass_mat("a8_greenstrip")
# The park is intentionally a healthy emerald lawn. Its palette is separate
# from every roadside planting bed, preventing a global material tweak from
# turning it back into the dry khaki surface seen in full_02.
M["grass_park"] = grass_mat(
    "a8_grass_park_pale_full06" if FULL06_LANDSCAPE else "a8_grass_park_emerald",
    # full06 deliberately uses a lighter, lower-saturation sage lawn.  Values
    # are authored here in the source generator, not patched into a saved blend.
    ((0.070, 0.155, 0.052, 1.0), (0.175, 0.335, 0.115, 1.0))
    if FULL06_LANDSCAPE
    else ((0.018, 0.135, 0.022, 1.0), (0.055, 0.315, 0.070, 1.0)),
)
M["soil"] = soil_mat()

# Road marking paints (from road2 style)
M["stripe_w"] = paint_mat("a8_sw", (0.72, 0.71, 0.67))
M["stripe_y"] = paint_mat("a8_sy", (0.66, 0.46, 0.03))
M["xwalk"] = paint_mat("a8_xw", (0.90, 0.88, 0.82), wear=0.25)

# Extra materials
M["wall_beige"] = UA._noise_mat(
    "wall_beige", (0.85, 0.80, 0.68), (0.75, 0.70, 0.58), rough=0.68, scale=7
)
M["wall_white"] = UA._noise_mat(
    "wall_white", (0.90, 0.88, 0.82), (0.82, 0.80, 0.74), rough=0.65, scale=8
)
M["wall_blue"] = UA._noise_mat(
    "wall_blue", (0.52, 0.62, 0.78), (0.44, 0.54, 0.68), rough=0.68, scale=8
)
M["wall_cream"] = UA._noise_mat(
    "wall_cream", (0.88, 0.84, 0.72), (0.80, 0.76, 0.64), rough=0.68, scale=9
)
M["stone_path"] = UA._noise_mat(
    "stone_path", (0.70, 0.66, 0.58), (0.60, 0.56, 0.48), rough=0.78, scale=11
)
M["park_stone"] = UA._noise_mat(
    "park_stone", (0.70, 0.68, 0.62), (0.60, 0.58, 0.52), rough=0.68, scale=9
)
M["park_path"] = (
    UA._noise_mat(
        "full06_park_path_warm_paver",
        (0.245, 0.175, 0.105),
        (0.385, 0.285, 0.175),
        rough=0.84,
        scale=13,
    )
    if FULL06_LANDSCAPE
    else M["stone_path"]
)
M["fence_iron"] = UA._pbr("fence_iron", (0.08, 0.08, 0.10), rough=0.32, metal=0.88)
M["gate_post"] = UA._pbr("gate_post", (0.12, 0.12, 0.14), rough=0.28, metal=0.92)
M["awning_r"] = UA._pbr("awning_r", (0.72, 0.18, 0.10), rough=0.76)
M["awning_g"] = UA._pbr("awning_g", (0.18, 0.50, 0.20), rough=0.76)
M["awning_b"] = UA._pbr("awning_b", (0.16, 0.28, 0.70), rough=0.76)
M["awning_y"] = UA._pbr("awning_y", (0.80, 0.64, 0.10), rough=0.76)
M["shop_beige"] = UA._noise_mat(
    "shop_beige", (0.82, 0.76, 0.64), (0.72, 0.66, 0.56), rough=0.70, scale=7
)
M["shop_red"] = UA._noise_mat(
    "shop_red", (0.68, 0.22, 0.12), (0.58, 0.18, 0.08), rough=0.66, scale=7
)
M["shop_blue"] = UA._noise_mat(
    "shop_blue", (0.30, 0.44, 0.70), (0.22, 0.36, 0.60), rough=0.66, scale=7
)
M["water_blue"] = UA._pbr("water_blue", (0.08, 0.32, 0.72), rough=0.03)
M["pool_rim"] = UA._pbr("pool_rim", (0.72, 0.70, 0.66), rough=0.55)
M["sign_comm"] = UA._pbr("sign_comm", (0.65, 0.08, 0.08), rough=0.72)

# ═══════════════════════════════════════════════════════════════════════════════
# PROCHRUBFACTORY — inline from curb_belt4_render.py
# ═══════════════════════════════════════════════════════════════════════════════


def _nrm(v):
    vec = Vector(v)
    l = vec.length
    return vec / l if l > 1e-8 else Vector((0, 0, 1))


def _pframe(direction):
    d = _nrm(direction)
    ref = Vector((0, 0, 1)) if abs(d.z) < 0.85 else Vector((1, 0, 0))
    right = d.cross(ref).normalized()
    up = d.cross(right).normalized()
    return right, up


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


def _add_tapcyl(verts, faces, path_pts, radii, n_sides=6):
    ring_starts = []
    for i, (pt, r) in enumerate(zip(path_pts, radii)):
        d = (
            _nrm(Vector(path_pts[1]) - Vector(path_pts[0]))
            if i == 0
            else _nrm(Vector(path_pts[i]) - Vector(path_pts[i - 1]))
        )
        right, up = _pframe(d)
        ring_starts.append(len(verts))
        for j in range(n_sides):
            a = j / n_sides * math.tau
            v = Vector(pt) + right * (r * math.cos(a)) + up * (r * math.sin(a))
            verts.append(tuple(v))
    for i in range(len(ring_starts) - 1):
        s0, s1 = ring_starts[i], ring_starts[i + 1]
        for j in range(n_sides):
            jn = (j + 1) % n_sides
            faces.append((s0 + j, s0 + jn, s1 + jn, s1 + j))


def _add_leaf(verts, faces, center, tangent, bitangent, length, width):
    c = Vector(center)
    t = _nrm(tangent)
    b = _nrm(bitangent)
    tip = c + t * length * 0.60
    r_sh = c + t * length * 0.08 + b * width * 0.50
    r_ba = c - t * length * 0.32 + b * width * 0.18
    base = c - t * length * 0.40
    l_ba = c - t * length * 0.32 - b * width * 0.18
    l_sh = c + t * length * 0.08 - b * width * 0.50
    idx = len(verts)
    verts += [
        tuple(tip),
        tuple(r_sh),
        tuple(r_ba),
        tuple(base),
        tuple(l_ba),
        tuple(l_sh),
    ]
    faces += [
        (idx, idx + 1, idx + 5),
        (idx + 1, idx + 2, idx + 5),
        (idx + 2, idx + 4, idx + 5),
        (idx + 2, idx + 3, idx + 4),
    ]


def _add_leaf_cluster(verts, faces, tip, rng, n_leaves, leaf_size, spread):
    tip = Vector(tip)
    for _ in range(n_leaves):
        offset = Vector(
            (
                rng.uniform(-spread, spread),
                rng.uniform(-spread, spread),
                rng.uniform(-spread * 0.4, spread * 0.4),
            )
        )
        center = tip + offset
        outward = (offset + Vector((0, 0, 0.01))).normalized()
        up_v = Vector(
            (rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 1.0)
        ).normalized()
        tangent = (outward * 0.6 + up_v * 0.4).normalized()
        bitangent = tangent.cross(
            Vector(
                (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.2, 0.2))
            ).normalized()
        ).normalized()
        _add_leaf(
            verts,
            faces,
            center,
            tangent,
            bitangent,
            leaf_size * rng.uniform(0.8, 1.3),
            leaf_size * rng.uniform(0.32, 0.52),
        )


def _bark_mat2(seed=0):
    mat = bpy.data.materials.new(f"B8Bark{seed}")
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


def _leaf_mat2(seed=0):
    rng = np.random.default_rng(seed)
    mat = bpy.data.materials.new(f"B8Leaf{seed}")
    mat.use_nodes = True
    mat.use_backface_culling = False
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    mix_s = nt.nodes.new("ShaderNodeMixShader")
    bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
    trans = nt.nodes.new("ShaderNodeBsdfTranslucent")
    noise = nt.nodes.new("ShaderNodeTexNoise")
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    coord = nt.nodes.new("ShaderNodeTexCoord")
    noise.inputs["Scale"].default_value = float(rng.uniform(6, 12))
    noise.inputs["Detail"].default_value = 5.0
    hue = rng.uniform(-0.03, 0.03)
    ramp.color_ramp.elements[0].color = (
        max(0, 0.013 + hue),
        0.068,
        max(0, 0.009 + hue),
        1.0,
    )
    ramp.color_ramp.elements[1].color = (
        max(0, 0.038 + hue),
        0.148,
        max(0, 0.020 + hue),
        1.0,
    )
    ramp.color_ramp.elements[1].position = 0.7
    bsdf.inputs["Roughness"].default_value = float(rng.uniform(0.58, 0.72))
    mix_s.inputs["Fac"].default_value = 0.25
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"], trans.inputs["Color"])
    nt.links.new(bsdf.outputs["BSDF"], mix_s.inputs[2])
    nt.links.new(trans.outputs["BSDF"], mix_s.inputs[1])
    nt.links.new(mix_s.outputs["Shader"], out.inputs["Surface"])
    return mat


class ProcShrubFactory:
    def __init__(self, seed=0, max_spread=0.22, max_height=1.1):
        self.seed = seed
        rng = np.random.default_rng(seed)
        self.n_stems = int(rng.integers(4, 8))
        self.max_height = float(rng.uniform(0.70, max_height))
        self.base_spread = float(rng.uniform(0.12, max_spread))
        self.leaf_size = float(rng.uniform(0.050, 0.078))
        self._rng = rng

    def _stem_path(self, base, angle, lean, height):
        rng = self._rng
        tip = (
            base[0] + lean * math.cos(angle),
            base[1] + lean * math.sin(angle),
            base[2] + height,
        )
        ctrl = _lerp3(base, tip, 0.5)
        ctrl = (
            ctrl[0] + rng.uniform(-0.05, 0.05),
            ctrl[1] + rng.uniform(-0.05, 0.05),
            ctrl[2] + rng.uniform(-0.03, 0.06),
        )
        return [_bez3(base, ctrl, tip, t) for t in np.linspace(0, 1, 4)]

    def create_asset(self, location=(0.0, 0.0, 0.0), name="Shrub", coll=None):
        rng = self._rng
        bark_mat = _bark_mat2(self.seed)
        leaf_mat = _leaf_mat2(self.seed)
        sv, sf = [], []
        lv, lf = [], []
        sec_tips = []
        for i in range(self.n_stems):
            angle = i / self.n_stems * math.tau + rng.uniform(-0.25, 0.25)
            lean = self.base_spread * rng.uniform(0.5, 1.0)
            h = self.max_height * rng.uniform(0.70, 1.20)
            base = (
                location[0] + math.cos(angle) * 0.03,
                location[1] + math.sin(angle) * 0.03,
                location[2],
            )
            path = self._stem_path(base, angle, lean, h)
            radii = np.linspace(0.018, 0.004, 4).tolist()
            _add_tapcyl(sv, sf, path, radii, n_sides=6)
            for j in range(int(rng.integers(2, 4))):
                t = rng.uniform(0.45, 0.80)
                pt = _bez3(path[0], path[1], path[-1], t)
                br_a = rng.uniform(0, math.tau)
                br_e = rng.uniform(math.radians(25), math.radians(68))
                bl = h * rng.uniform(0.20, 0.40)
                br_tip = (
                    pt[0] + bl * math.cos(br_a) * math.cos(br_e),
                    pt[1] + bl * math.sin(br_a) * math.cos(br_e),
                    pt[2] + bl * math.sin(br_e),
                )
                br_ctrl = _lerp3(pt, br_tip, 0.5)
                br_path = [
                    _bez3(pt, br_ctrl, br_tip, t2) for t2 in np.linspace(0, 1, 3)
                ]
                _add_tapcyl(sv, sf, br_path, [0.008, 0.006, 0.003], n_sides=5)
                sec_tips.append(br_tip)
        n_per_tip = int(rng.integers(12, 18))
        for tip in sec_tips:
            _add_leaf_cluster(
                lv, lf, tip, rng, n_per_tip, self.leaf_size, self.leaf_size * 1.1
            )
        stem_mesh = bpy.data.meshes.new(name + "_bark")
        stem_mesh.from_pydata(sv, [], sf)
        stem_mesh.update()
        stem_obj = bpy.data.objects.new(name + "_bark", stem_mesh)
        bpy.context.collection.objects.link(stem_obj)
        stem_obj.data.materials.append(bark_mat)
        leaf_mesh = bpy.data.meshes.new(name + "_leaf")
        leaf_mesh.from_pydata(lv, [], lf)
        leaf_mesh.update()
        for p in leaf_mesh.polygons:
            p.use_smooth = True
        leaf_obj = bpy.data.objects.new(name + "_leaf", leaf_mesh)
        bpy.context.collection.objects.link(leaf_obj)
        leaf_obj.data.materials.append(leaf_mat)
        leaf_obj.parent = stem_obj
        bpy.context.view_layer.update()
        if coll:
            UA.to_coll(stem_obj, coll)
            UA.to_coll(leaf_obj, coll)
        return stem_obj


def _place_shrubs_along(tag, cx, cy, length_x, length_y, coll, spacing=2.0, seed=0):
    """Place ProcShrubFactory shrubs in a rectangular flower bed."""
    import random as _r

    _r.seed(seed % 99991)
    rng_sp = np.random.default_rng(seed % 99991)
    # Place shrubs on a grid with random offset
    nx = max(1, int(length_x / spacing))
    ny = max(1, int(length_y / spacing))
    k = 0
    for i in range(nx):
        for j in range(ny):
            x = (
                cx
                - length_x / 2
                + (i + 0.5) * length_x / nx
                + rng_sp.uniform(-0.3, 0.3)
            )
            y = (
                cy
                - length_y / 2
                + (j + 0.5) * length_y / ny
                + rng_sp.uniform(-0.3, 0.3)
            )
            sh_seed = (seed * 1000 + k) % 99991
            sh = ProcShrubFactory(seed=sh_seed, max_spread=0.18, max_height=0.9)
            sh.create_asset(location=(x, y, 0.08), name=f"{tag}_sh{k}", coll=coll)
            k += 1


# Road-aligned beds are collected while the road generator lays them out.  In
# full06 this registry drives one dense, continuous Infinigen flower/grass
# surface, mirroring curb_belt4_render.py while avoiding isolated shrub clumps.
_FLOWERBED_RECTS = []

# ═══════════════════════════════════════════════════════════════════════════════
# SCENE CONSTANTS + COLLECTIONS
# ═══════════════════════════════════════════════════════════════════════════════
R = 4.5
SW = 3.5
FW = 2.5
S1 = R + SW  # 8.0
G1 = S1 + FW  # 10.5
ARM = 50.0
LC = R / 2  # 2.25
FULL = R + ARM  # 54.5

C_road = UA.new_coll("Road")
C_sw = UA.new_coll("Sidewalks")
C_fb = UA.new_coll("FlowerBeds")
C_mk = UA.new_coll("RoadMarkings")
C_tl = UA.new_coll("TrafficLights")
C_n = UA.new_coll("Residential")
C_e = UA.new_coll("Park")
C_s = UA.new_coll("Commercial")
C_w = UA.new_coll("WestArm")
C_furn = UA.new_coll("Furniture")
C_lamp = UA.new_coll("Lamps")
C_cars = UA.new_coll("Vehicles")
C_tree = UA.new_coll("Trees")


def _box(name, cx, cy, cz, dx, dy, dz, mat, coll, bev=0.0, rz=0.0):
    return UA._box(name, cx, cy, cz, dx, dy, dz, mat, coll, bev=bev, rz=rz)


def _cyl(name, cx, cy, cz, r, h, mat, coll, verts=24, rx=0.0, rz=0.0):
    return UA._cyl(name, cx, cy, cz, r, h, mat, coll, verts=verts, rx=rx, rz=rz)


def _sph(name, cx, cy, cz, r, mat, coll, segs=16, rings=12):
    return UA._sph(name, cx, cy, cz, r, mat, coll, segs=segs, rings=rings)


# ─── FLOWER BED HELPERS ──────────────────────────────────────────────────────
def _fb_ns(tag, x_inner, side, y0, y1, C):
    if y1 <= y0:
        return
    fw2 = FW / 2.0
    cx = x_inner + (fw2 if side == "e" else -fw2)
    cy = (y0 + y1) / 2.0
    dy = y1 - y0
    ground_mat = (
        M["soil"]
        if os.environ.get("C2W_FLOWERBED_LANDSCAPE") == "1"
        else M["greenstrip"]
    )
    bed = _box(f"{tag}_bed_soil", cx, cy, 0.055, FW, dy, 0.11, ground_mat, C, bev=0.035)
    bed["c2w_landscape_role"] = (
        "layered_flowerbed" if ground_mat == M["soil"] else "greenstrip"
    )
    bed["c2w_flowerbed_axis"] = "NS"
    bed["c2w_flowerbed_length"] = dy
    bed["c2w_flowerbed_width"] = FW
    bed["c2w_road_alignment"] = "parallel"
    _FLOWERBED_RECTS.append((tag, cx, cy, FW, dy, "NS"))
    if ground_mat == M["soil"]:
        _box(
            f"{tag}_edge_l",
            cx - FW / 2 + 0.045,
            cy,
            0.105,
            0.09,
            dy,
            0.12,
            M["park_stone"],
            C,
            bev=0.018,
        )
        _box(
            f"{tag}_edge_r",
            cx + FW / 2 - 0.045,
            cy,
            0.105,
            0.09,
            dy,
            0.12,
            M["park_stone"],
            C,
            bev=0.018,
        )
    if dy >= 1.5 and not FULL06_LANDSCAPE:
        _place_shrubs_along(
            tag, cx, cy, FW - 0.3, dy - 0.3, C, spacing=2.2, seed=abs(hash(tag)) % 99991
        )


def _fb_ew(tag, y_inner, side, x0, x1, C):
    if x1 <= x0:
        return
    fw2 = FW / 2.0
    cy = y_inner + (fw2 if side == "n" else -fw2)
    cx = (x0 + x1) / 2.0
    dx = x1 - x0
    ground_mat = (
        M["soil"]
        if os.environ.get("C2W_FLOWERBED_LANDSCAPE") == "1"
        else M["greenstrip"]
    )
    bed = _box(f"{tag}_bed_soil", cx, cy, 0.055, dx, FW, 0.11, ground_mat, C, bev=0.035)
    bed["c2w_landscape_role"] = (
        "layered_flowerbed" if ground_mat == M["soil"] else "greenstrip"
    )
    bed["c2w_flowerbed_axis"] = "EW"
    bed["c2w_flowerbed_length"] = dx
    bed["c2w_flowerbed_width"] = FW
    bed["c2w_road_alignment"] = "parallel"
    _FLOWERBED_RECTS.append((tag, cx, cy, dx, FW, "EW"))
    if ground_mat == M["soil"]:
        _box(
            f"{tag}_edge_b",
            cx,
            cy - FW / 2 + 0.045,
            0.105,
            dx,
            0.09,
            0.12,
            M["park_stone"],
            C,
            bev=0.018,
        )
        _box(
            f"{tag}_edge_t",
            cx,
            cy + FW / 2 - 0.045,
            0.105,
            dx,
            0.09,
            0.12,
            M["park_stone"],
            C,
            bev=0.018,
        )
    if dx >= 1.5 and not FULL06_LANDSCAPE:
        _place_shrubs_along(
            tag, cx, cy, dx - 0.3, FW - 0.3, C, spacing=2.2, seed=abs(hash(tag)) % 99991
        )


def _build_full06_belt4_flower_layer(C):
    """Build dense road-following flowerbeds with no standalone shrubs.

    Each rectangle is subdivided before scatter so density is spatially even;
    this is the key belt4 modelling detail that a one-face/toy strip misses.
    """
    if not FULL06_LANDSCAPE:
        return {"beds": 0, "surface_faces": 0, "scatter_layers": 0}
    verts, faces = [], []
    inset = 0.18
    for _tag, cx, cy, dx, dy, _axis in _FLOWERBED_RECTS:
        sx, sy = max(0.25, dx - 2 * inset), max(0.25, dy - 2 * inset)
        nx, ny = max(2, int(math.ceil(sx * 3.0))), max(2, int(math.ceil(sy * 3.0)))
        for ix in range(nx):
            x0 = cx - sx / 2 + sx * ix / nx
            x1 = cx - sx / 2 + sx * (ix + 1) / nx
            for iy in range(ny):
                y0 = cy - sy / 2 + sy * iy / ny
                y1 = cy - sy / 2 + sy * (iy + 1) / ny
                k = len(verts)
                verts.extend(
                    ((x0, y0, 0.116), (x1, y0, 0.116), (x1, y1, 0.116), (x0, y1, 0.116))
                )
                faces.append((k, k + 1, k + 2, k + 3))
    mesh = bpy.data.meshes.new("full06_road_flowerbed_scatter_surface_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    surface = bpy.data.objects.new("full06_road_flowerbed_scatter_surface", mesh)
    C.objects.link(surface)
    surface.data.materials.append(M["soil"])
    surface["c2w_landscape_role"] = "road_aligned_flowerbed_scatter_surface"
    surface["c2w_reference_model"] = "urban_v3_belt4"
    surface["c2w_surface_faces"] = len(faces)
    layers = []
    from infinigen.assets.scatters.flowerplant import Flowerplant
    from infinigen.assets.scatters.grass import Grass

    with FixedSeed(260621):
        flower_result = Flowerplant().apply(surface, selection=None, density=1.65)
    flower_obj = flower_result[0] if isinstance(flower_result, tuple) else flower_result
    if flower_obj is not None:
        flower_obj.name = "full06_road_flowerbed_flowers"
        flower_obj["c2w_landscape_role"] = "road_aligned_flowerbed_flowers"
        layers.append(flower_obj.name)
    with FixedSeed(260622):
        grass_result = Grass().apply(surface, density=7.0)
    grass_obj = grass_result[0] if isinstance(grass_result, tuple) else grass_result
    if grass_obj is not None:
        grass_obj.name = "full06_road_flowerbed_grass_understory"
        grass_obj["c2w_landscape_role"] = "road_aligned_flowerbed_grass"
        layers.append(grass_obj.name)
    bpy.context.scene["c2w_full06_flowerbed_rect_count"] = len(_FLOWERBED_RECTS)
    bpy.context.scene["c2w_full06_flowerbed_surface_faces"] = len(faces)
    bpy.context.scene["c2w_full06_flowerbed_scatter_layers"] = len(layers)
    print(
        f"[full06] belt4 flowerbeds: rects={len(_FLOWERBED_RECTS)}, "
        f"faces={len(faces)}, layers={layers}",
        flush=True,
    )
    return {
        "beds": len(_FLOWERBED_RECTS),
        "surface_faces": len(faces),
        "scatter_layers": len(layers),
    }


# ─── ROAD MARKING HELPERS ─────────────────────────────────────────────────────
def _crosswalk_ns(tag, arm_sign, C):
    CW_W, CW_G = 0.50, 0.28
    y_base = arm_sign * (R + 0.55)
    for k in range(6):
        y = y_base + arm_sign * k * (CW_W + CW_G)
        _box(f"xwk_{tag}{k}", 0, y, 0.025, 2 * R - 0.3, CW_W, 0.004, M["xwalk"], C_mk)


def _crosswalk_ew(tag, arm_sign, C):
    CW_W, CW_G = 0.50, 0.28
    x_base = arm_sign * (R + 0.55)
    for k in range(6):
        x = x_base + arm_sign * k * (CW_W + CW_G)
        _box(f"xwk_{tag}{k}", x, 0, 0.025, CW_W, 2 * R - 0.3, 0.004, M["xwalk"], C_mk)


def _turn_arrow(tag, cx, cy, yaw, C):
    mat = M["stripe_w"]
    dx = -math.sin(yaw)
    dy = math.cos(yaw)
    sh = _box(f"arr_{tag}_sh", cx, cy, 0.026, 0.22, 1.5, 0.004, mat, C)
    sh.rotation_euler.z = yaw
    tip_x = cx + dx * 0.75
    tip_y = cy + dy * 0.75
    for s in [1, -1]:
        w_yaw = yaw + s * math.radians(32)
        wd_x = -math.sin(w_yaw)
        wd_y = math.cos(w_yaw)
        wc_x = tip_x - wd_x * 0.27
        wc_y = tip_y - wd_y * 0.27
        wing = _box(f"arr_{tag}_w{s}", wc_x, wc_y, 0.026, 0.22, 0.55, 0.004, mat, C)
        wing.rotation_euler.z = w_yaw


# ─── IRON FENCE ───────────────────────────────────────────────────────────────
def _build_fence(tag, cx, cy, fw, fd, gate_side="w", gate_w=2.4, C=None, h=1.4):
    mat, post = M["fence_iron"], M["gate_post"]
    hw, hd = fw / 2.0, fd / 2.0
    gh = gate_w / 2.0
    for k, (px, py) in enumerate(
        [(cx + hw, cy + hd), (cx - hw, cy + hd), (cx + hw, cy - hd), (cx - hw, cy - hd)]
    ):
        _cyl(f"{tag}_cp{k}", px, py, 0, 0.09, h + 0.4, post, C, verts=8)
    _box(f"{tag}_fn", cx, cy + hd, h / 2, fw, 0.10, h, mat, C)
    _box(f"{tag}_fs", cx, cy - hd, h / 2, fw, 0.10, h, mat, C)
    if gate_side == "e":
        for py0, py1, sfx in [(cy - hd, cy - gh, "lo"), (cy + gh, cy + hd, "hi")]:
            seg = abs(py1 - py0)
            if seg > 0.1:
                _box(
                    f"{tag}_fe_{sfx}",
                    cx + hw,
                    (py0 + py1) / 2,
                    h / 2,
                    0.10,
                    seg,
                    h,
                    mat,
                    C,
                )
        _cyl(f"{tag}_egp1", cx + hw, cy - gh, 0, 0.11, h + 0.6, post, C, verts=8)
        _cyl(f"{tag}_egp2", cx + hw, cy + gh, 0, 0.11, h + 0.6, post, C, verts=8)
    else:
        _box(f"{tag}_fe", cx + hw, cy, h / 2, 0.10, fd, h, mat, C)
    if gate_side == "w":
        for py0, py1, sfx in [(cy - hd, cy - gh, "lo"), (cy + gh, cy + hd, "hi")]:
            seg = abs(py1 - py0)
            if seg > 0.1:
                _box(
                    f"{tag}_fw_{sfx}",
                    cx - hw,
                    (py0 + py1) / 2,
                    h / 2,
                    0.10,
                    seg,
                    h,
                    mat,
                    C,
                )
        _cyl(f"{tag}_wgp1", cx - hw, cy - gh, 0, 0.11, h + 0.6, post, C, verts=8)
        _cyl(f"{tag}_wgp2", cx - hw, cy + gh, 0, 0.11, h + 0.6, post, C, verts=8)
    else:
        _box(f"{tag}_fw", cx - hw, cy, h / 2, 0.10, fd, h, mat, C)


# ─── SHOP FACADES ─────────────────────────────────────────────────────────────
def _shop_w(tag, cx, cy, w, d, h, mat, aw_mat, C):
    _box(f"{tag}_body", cx, cy, h / 2, d, w, h, mat, C, bev=0.02)
    _box(
        f"{tag}_gl",
        cx - d / 2 + 0.06,
        cy,
        h * 0.38,
        0.10,
        w * 0.70,
        h * 0.54,
        M["window"],
        C,
    )
    _box(
        f"{tag}_aw",
        cx - d / 2 - 0.72,
        cy,
        h * 0.70,
        1.44,
        w * 0.84,
        0.10,
        aw_mat,
        C,
        rz=math.radians(-4),
    )
    _box(
        f"{tag}_sg",
        cx - d / 2 + 0.06,
        cy,
        h * 0.86,
        0.14,
        w * 0.72,
        0.46,
        M["sign_comm"],
        C,
    )
    _box(f"{tag}_door", cx - d / 2 + 0.05, cy, 1.2, 0.12, 1.1, 2.4, M["door"], C)


def _shop_e(tag, cx, cy, w, d, h, mat, aw_mat, C):
    _box(f"{tag}_body", cx, cy, h / 2, d, w, h, mat, C, bev=0.02)
    _box(
        f"{tag}_gl",
        cx + d / 2 - 0.06,
        cy,
        h * 0.38,
        0.10,
        w * 0.70,
        h * 0.54,
        M["window"],
        C,
    )
    _box(
        f"{tag}_aw",
        cx + d / 2 + 0.72,
        cy,
        h * 0.70,
        1.44,
        w * 0.84,
        0.10,
        aw_mat,
        C,
        rz=math.radians(4),
    )
    _box(
        f"{tag}_sg",
        cx + d / 2 - 0.06,
        cy,
        h * 0.86,
        0.14,
        w * 0.72,
        0.46,
        M["sign_comm"],
        C,
    )
    _box(f"{tag}_door", cx + d / 2 - 0.05, cy, 1.2, 0.12, 1.1, 2.4, M["door"], C)


def _water_feature(tag, cx, cy, r, C):
    _cyl(f"{tag}_rim", cx, cy, 0.0, r + 0.18, 0.42, M["pool_rim"], C, verts=32)
    _cyl(f"{tag}_pool", cx, cy, 0.06, r, 0.28, M["water_blue"], C, verts=32)
    _cyl(f"{tag}_col", cx, cy, 0.34, 0.12, 1.20, M["pool_rim"], C, verts=12)
    _sph(f"{tag}_top", cx, cy, 1.54 + 0.24, 0.24, M["water_blue"], C, segs=12, rings=8)


def _corten_ring(tag, cx, cy, r, C):
    mat = UA._pbr(f"{tag}_ct", (0.48, 0.22, 0.06), rough=0.72)
    for i in range(3):
        ang = i * math.pi / 3
        ox, oy = cx + math.cos(ang) * r * 0.35, cy + math.sin(ang) * r * 0.35
        bpy.ops.mesh.primitive_torus_add(
            major_radius=r,
            minor_radius=r * 0.12,
            location=(ox, oy, r + 0.3),
            rotation=(math.radians(60 + i * 30), 0, ang),
        )
        o = bpy.context.active_object
        o.name = f"{tag}_ring{i}"
        o.data.materials.append(mat)
        UA.to_coll(o, C)


def _plaza_circle(tag, cx, cy, r, C):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=32, radius=r, depth=0.10, location=(cx, cy, 0.06)
    )
    o = bpy.context.active_object
    o.name = f"{tag}_plaza"
    o.data.materials.append(M["park_stone"])
    UA.to_coll(o, C)


# ─── INFINIGEN TREE (TreeFactory inline) ─────────────────────────────────────
_TREE_SEEDS = [42, 137, 256, 381, 512, 619, 734, 851, 923, 1044]
_TREE_LIBRARY = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_all45_02/all45_02_treefactory_lods.blend"
)
_FAST5_LIBRARY = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/outdoor_part_demo/urban_v3_all39_fast5/urban_v3_all39_fast5.blend"
)
_TREE_MASTERS = []
_FAST5_SHRUB_MASTERS = []
_REAL_TREE_MASTERS = {}


def _full07_leaf_assets_for_tree(root):
    """Return genuine LeafFactory meshes generated with this TreeFactory root."""
    match = re.search(r"TreeFactory\((\d+)\)", root.name)
    tree_id = match.group(1) if match else ""
    assets = [
        obj
        for obj in bpy.data.objects
        if obj.type == "MESH" and obj.data and obj.name.startswith("LeafFactory")
    ]
    exact = [obj for obj in assets if tree_id and f"({tree_id})" in obj.name]
    broadleaf = [obj for obj in assets if "Broadleaf" in obj.name]
    return sorted(exact or broadleaf or assets, key=lambda obj: obj.name)


def _full07_local_bbox(mesh):
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    for vertex in mesh.vertices:
        co = vertex.co
        mn.x = min(mn.x, co.x)
        mn.y = min(mn.y, co.y)
        mn.z = min(mn.z, co.z)
        mx.x = max(mx.x, co.x)
        mx.y = max(mx.y, co.y)
        mx.z = max(mx.z, co.z)
    return mn, mx


def _full07_canopy_points(root, count, rng):
    """Sample the detailed branch crown, matching the supplied all41 canopy method."""
    mn, mx = _full07_local_bbox(root.data)
    dims = mx - mn
    height = max(dims.z, 0.01)
    center = Vector(((mn.x + mx.x) * 0.5, (mn.y + mx.y) * 0.5, 0.0))
    radius = max(dims.x, dims.y, 0.01) * 0.5
    vertices = root.data.vertices
    step = max(1, len(vertices) // 85000)
    candidates = []
    for vertex_index in range(0, len(vertices), step):
        co = vertices[vertex_index].co
        height_fraction = (co.z - mn.z) / height
        radial = math.hypot(co.x - center.x, co.y - center.y) / radius
        if height_fraction < 0.26 or (height_fraction < 0.46 and radial < 0.16):
            continue
        noise = 0.5 + 0.5 * math.sin((vertex_index + 1) * 12.9898 + count * 78.233)
        crown_shell = 1.0 - abs(min(radial, 1.55) - 0.82) * 0.28
        score = height_fraction * 0.52 + crown_shell * 0.50 + noise * 0.22
        candidates.append((score, co.copy(), height_fraction, radial))
    candidates.sort(key=lambda item: item[0], reverse=True)
    pool = candidates[: min(len(candidates), max(count * 8, count))]
    rng.shuffle(pool)
    return pool[:count]


def _add_full07_visible_leaf_canopy(root, master, seed):
    """Expose genuine LeafFactory meshes in TreeFactory collection instances.

    TreeFactory's original leaf-child node objects evaluate empty behind a
    collection instance in this pipeline.  The supplied all41 reference links
    genuine LeafFactory meshes explicitly over the detailed branch crown; this
    applies that source-level method to every same-run full07 mother tree.
    """
    assets = _full07_leaf_assets_for_tree(root)
    if not assets:
        raise RuntimeError(
            f"TreeFactory seed {seed} produced no LeafFactory mesh assets"
        )
    mn, mx = _full07_local_bbox(root.data)
    dims = mx - mn
    height = max(dims.z, 0.01)
    crown_width = max(dims.x, dims.y, 0.01)
    leaf_count = int(max(680, min(1680, 96.0 * (dims.x + dims.y) + 46.0 * height)))
    rng = random.Random(39017 + seed * 7919)
    points = _full07_canopy_points(root, leaf_count, rng)
    if len(points) < 680:
        raise RuntimeError(
            f"TreeFactory seed {seed} crown only supplied {len(points)} leaf sites"
        )
    center = Vector(((mn.x + mx.x) * 0.5, (mn.y + mx.y) * 0.5, 0.0))
    for leaf_index, (_, co, height_fraction, radial) in enumerate(points):
        source = assets[(leaf_index * 7 + seed * 3) % len(assets)]
        leaf = bpy.data.objects.new(
            f"full07:tree_master:{seed}:leaf:{leaf_index:04d}", source.data
        )
        outward = Vector((co.x - center.x, co.y - center.y, 0.0))
        if outward.length < 1e-4:
            yaw = rng.random() * math.tau
            outward = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        else:
            outward.normalize()
            yaw = math.atan2(outward.y, outward.x) - math.pi * 0.5
        shell = 0.55 + 0.55 * rng.random()
        jitter = Vector(
            (
                (rng.random() - 0.5) * 0.62 * crown_width * shell,
                (rng.random() - 0.5) * 0.62 * crown_width * shell,
                (rng.random() - 0.50) * 0.52 * height,
            )
        )
        if height_fraction < 0.64:
            jitter.z += 0.16 * height
        elif rng.random() < 0.42:
            jitter.z -= 0.10 * height
        leaf.location = co + outward * (0.05 + 0.46 * rng.random()) + jitter
        leaf.rotation_euler = (
            rng.uniform(-0.95, 0.95),
            rng.uniform(-0.45, 0.45),
            yaw + rng.uniform(-0.95, 0.95),
        )
        scale = rng.uniform(0.44, 0.94) * (0.92 + 0.24 * min(radial, 1.0))
        leaf.scale = (scale, scale, scale)
        leaf.hide_viewport = False
        leaf.hide_render = False
        leaf["c2w_genuine_leaffactory_mesh"] = True
        leaf["c2w_treefactory_seed"] = seed
        master.objects.link(leaf)
    master["c2w_explicit_leaf_count"] = len(points)
    master["c2w_leaf_source"] = "same-run Infinigen LeafFactory mesh"
    print(
        f"[full07] TreeFactory master seed={seed}: explicit genuine leaves={len(points)}",
        flush=True,
    )
    return len(points)


def _ensure_tree_masters():
    if _TREE_MASTERS:
        return _TREE_MASTERS
    if os.environ.get("C2W_TREE_LIBRARY_PROFILE") == "all39_fast5":
        if not _FAST5_LIBRARY.exists():
            raise FileNotFoundError(
                f"Verified all39_fast5 vegetation library missing: {_FAST5_LIBRARY}"
            )
        # Exact explicit-leaf mother trees used by the supplied park.png.
        # Rotation/scale provide placement variety while the full-detail bark
        # and linked leaf geometry stays shared between all scene instances.
        tree_names = ["All39Fast5_TreePrototype_07", "All39Fast5_TreePrototype_08"]
        shrub_names = [f"All39Fast5_ShrubPrototype_{i:02d}" for i in range(5)]
        with bpy.data.libraries.load(str(_FAST5_LIBRARY), link=False) as (src, dst):
            missing = [
                name for name in tree_names + shrub_names if name not in src.collections
            ]
            if missing:
                raise RuntimeError(
                    f"Verified all39_fast5 vegetation prototypes missing: {missing}"
                )
            dst.collections = tree_names + shrub_names
        loaded = {c.name: c for c in dst.collections if c is not None}
        _TREE_MASTERS.extend(loaded[name] for name in tree_names)
        _FAST5_SHRUB_MASTERS.extend(loaded[name] for name in shrub_names)
        for coll in _TREE_MASTERS:
            coll["c2w_verified_reference"] = "urban_v3_all39_fast5/park.png"
            coll["c2w_tree_geometry"] = "full-detail bark plus explicit linked leaves"
        for coll in _FAST5_SHRUB_MASTERS:
            coll["c2w_verified_reference"] = "urban_v3_belt4"
        print(
            f"[full03] Loaded verified all39_fast5 vegetation masters: "
            f"trees={len(_TREE_MASTERS)}, shrubs={len(_FAST5_SHRUB_MASTERS)}",
            flush=True,
        )
        return _TREE_MASTERS
    if not _TREE_LIBRARY.exists():
        return _TREE_MASTERS
    wanted = [
        f"all45_02:MASTER_generic_treefactory_{s}" for s in (42, 137, 256, 381, 512)
    ]
    with bpy.data.libraries.load(str(_TREE_LIBRARY), link=False) as (src, dst):
        dst.collections = [name for name in wanted if name in src.collections]
    _TREE_MASTERS.extend(c for c in dst.collections if c is not None)
    return _TREE_MASTERS


def _gen_park_tree(tag, tx, ty, C, seed=42, scale=1.0):
    """Spawn a TreeFactory summer tree at (tx,ty) and move its objects to C."""
    if os.environ.get("C2W_REAL_TREE_MASTER_INSTANCES") == "1":
        # Build a small palette of genuine coarse=False TreeFactory trees in
        # this run, then collection-instance them.  This preserves full branch
        # and leaf geometry without expanding that geometry once per placement.
        palette_size = max(
            3, min(len(_TREE_SEEDS), int(os.environ.get("C2W_TREE_PALETTE_SIZE", "3")))
        )
        # Seed 137 produces an unusually pathological crown realization at
        # production LOD.  Use only well-conditioned botanical seeds for every
        # source-generated production palette.
        palette = [42, 256, 381, 512, 619][:palette_size]
        canonical_seed = (
            palette[_TREE_SEEDS.index(seed) % len(palette)]
            if seed in _TREE_SEEDS
            else palette[seed % len(palette)]
        )
        master = _REAL_TREE_MASTERS.get(canonical_seed)
        if master is None:
            from infinigen.assets.objects.trees.generate import TreeFactory

            before = set(bpy.data.objects)
            print(
                f"[full02] Generating real TreeFactory master seed={canonical_seed} ..."
            )
            with FixedSeed(canonical_seed):
                fac = TreeFactory(
                    seed=canonical_seed, season="summer", coarse=False, fruit_chance=0.0
                )
                # A production-distance remesh retains the complete trunk,
                # branch, twig and leaf hierarchy without the pathological
                # near-microscopic tessellation used for macro dataset views.
                spawned = fac.spawn_asset(
                    0, loc=(0, 0, 0), rot=(0, 0, 0), distance=60, face_size=0.08
                )
            created = [o for o in bpy.data.objects if o not in before]
            if spawned and spawned not in created:
                created.append(spawned)
            if not created:
                raise RuntimeError(
                    f"TreeFactory master {canonical_seed} produced no objects"
                )
            master = bpy.data.collections.new(
                f"full02:MASTER:TreeFactory:{canonical_seed}"
            )
            master[
                "generator"
            ] = "Infinigen TreeFactory LeafFactory + full07 botanical reconstruction"
            master["coarse"] = False
            master["seed"] = canonical_seed
            root_mesh = (
                spawned if spawned and spawned.type == "MESH" and spawned.data else None
            )
            if root_mesh is None:
                root_mesh = next(
                    (
                        obj
                        for obj in created
                        if obj.type == "MESH"
                        and obj.data
                        and obj.name.startswith("TreeFactory(")
                    ),
                    None,
                )
            if root_mesh is None:
                raise RuntimeError(
                    f"TreeFactory master {canonical_seed} has no detailed crown mesh"
                )
            # The current Blender-4.5 BranchFactory output realizes as folded
            # branch sheets and the bare skin reads as a brown crown blob.
            # TreeFactory remains the same-run genuine LeafFactory source;
            # full07 rebuilds a continuous multi-level woody hierarchy around
            # those leaf meshes in the production generator itself.
            from urban_v1_full_07_trees import build_botanical_tree_master

            leaf_assets = _full07_leaf_assets_for_tree(root_mesh)
            build_botanical_tree_master(master, canonical_seed, leaf_assets)
            helper_meshes = {
                helper.data
                for helper in created
                if helper.type == "MESH" and helper.data
            }
            for helper in created:
                bpy.data.objects.remove(helper, do_unlink=True)
            for helper_mesh in helper_meshes:
                if helper_mesh.users == 0:
                    helper_mesh.use_fake_user = False
                    bpy.data.meshes.remove(helper_mesh)
            master["c2w_internal_treefactory_helpers_removed"] = True
            _REAL_TREE_MASTERS[canonical_seed] = master
        inst = bpy.data.objects.new(tag, None)
        C.objects.link(inst)
        inst.instance_type = "COLLECTION"
        inst.instance_collection = master
        inst.location = (tx, ty, 0)
        zs = [
            (obj.matrix_world @ Vector(corner)).z
            for obj in master.all_objects
            if obj.type == "MESH" and obj.data
            for corner in obj.bound_box
        ]
        source_height = max(zs) - min(zs) if zs else 0.0
        if source_height <= 0.0:
            raise RuntimeError(
                f"Source TreeFactory master has invalid height: {master.name}"
            )
        desired_height = source_height * scale
        if not 4.5 <= desired_height <= 9.0:
            desired_height = 6.4 * scale
        final_scale = desired_height / source_height
        inst.scale = (final_scale,) * 3
        inst.rotation_euler[2] = (seed * 0.61803398875) % (2 * math.pi)
        inst["c2w_treefactory_real_instance"] = True
        inst["treefactory_seed"] = canonical_seed
        inst["c2w_real_world_tree_height_m"] = round(desired_height, 3)
        return inst
    if os.environ.get("C2W_USE_TREE_MASTER_LIBRARY") == "1":
        masters = _ensure_tree_masters()
        if masters:
            root = bpy.data.objects.new(tag, None)
            C.objects.link(root)
            root.instance_type = "COLLECTION"
            root.instance_collection = masters[seed % len(masters)]
            chosen = root.instance_collection
            # The cached all45_02 collections retain full coarse=False branch
            # and leaf meshes but are authored in a normalized sub-metre asset
            # space.  Placing them at scale=1 was the reason full_05 read as
            # tiny shrubs.  Normalize genuine tree masters to a plausible
            # mature streetscape height; this never substitutes proxy geometry.
            if "generic_treefactory" in chosen.name.lower():
                zs = [
                    (obj.matrix_world @ Vector(corner)).z
                    for obj in chosen.all_objects
                    if obj.type == "MESH" and obj.data
                    for corner in obj.bound_box
                ]
                source_height = max(zs) - min(zs) if zs else 0.0
                if source_height <= 0.0:
                    raise RuntimeError(
                        f"TreeFactory master has invalid height: {chosen.name}"
                    )
                final_scale = (6.4 / source_height) * scale
            else:
                zs = [
                    (obj.matrix_world @ Vector(corner)).z
                    for obj in chosen.all_objects
                    if obj.type == "MESH" and obj.data
                    for corner in obj.bound_box
                ]
                source_height = max(zs) - min(zs) if zs else 0.0
                if source_height <= 0.0:
                    raise RuntimeError(
                        f"Verified tree master has invalid height: {chosen.name}"
                    )
                # Park placement historically used 0.8 for the old oversized
                # masters.  Keep these verified street trees in a believable
                # 5.2--8.0 m band instead of shrinking them back into shrubs.
                desired_height = max(5.2, min(8.0, source_height * scale))
                final_scale = desired_height / source_height
            root.location = (tx, ty, 0)
            root.scale = (final_scale,) * 3
            root["c2w_real_world_tree_height_m"] = round(source_height * final_scale, 3)
            root["c2w_tree_master_instance"] = True
            print(
                f"[all8] Tree {tag} instanced from {root.instance_collection.name}; "
                f"real-world height={root['c2w_real_world_tree_height_m']}m"
            )
            return root
    from infinigen.assets.objects.trees.generate import TreeFactory

    print(f"[all8] Generating tree {tag} at ({tx},{ty}) seed={seed} ...")
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
            print(f"[all8] Tree {tag} done (root={root.name})")
        return root
    except Exception as e:
        print(f"[all8] TreeFactory error for {tag}: {e}")
        if os.environ.get("C2W_FORBID_TOY_MODELS") == "1":
            raise RuntimeError(
                f"TreeFactory failed for {tag}; toy fallback is forbidden"
            ) from e
        UA.build_tree(tag, tx, ty, C, trunk_h=3.5, canopy_r=3.2)
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# GROUND PLANE (soil)
# ═══════════════════════════════════════════════════════════════════════════════
_box("gnd", 0, 0, -0.10, 400, 400, 0.20, M["soil"], C_sw)

# ═══════════════════════════════════════════════════════════════════════════════
# CROSSROADS ROAD + SIDEWALKS
# ═══════════════════════════════════════════════════════════════════════════════
if LAYOUT_MODE == "linear_street":
    # One uninterrupted north-south street, authored as one slab rather than a
    # crossroads with hidden arms.
    _box("road_linear_ns", 0, 0, 0.02, 2 * R, 2 * FULL, 0.04, M["road"], C_road)
    for side, x in (("e", S1 - SW / 2), ("w", -(S1 - SW / 2))):
        _box(f"sw_linear_{side}", x, 0, 0.03, SW, 2 * FULL, 0.04, M["sidewalk"], C_sw)
    for side, x in (("e", R + 0.08), ("w", -R - 0.08)):
        _box(f"kerb_linear_{side}", x, 0, 0.10, 0.16, 2 * FULL, 0.20, M["curb"], C_sw)
elif LAYOUT_MODE == "t_junction":
    # East-west through road with a south stem.  There is no north approach.
    _box("t_junction_center", 0, 0, 0.02, 2 * R, 2 * R, 0.04, M["road"], C_road)
    yc = -(R + ARM / 2)
    _box("road_s", 0, yc, 0.02, 2 * R, ARM, 0.04, M["road"], C_road)
    for side, x in (("e", S1 - SW / 2), ("w", -(S1 - SW / 2))):
        _box(f"sw_s_{side}", x, yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)
    for side, x in (("e", R + 0.08), ("w", -R - 0.08)):
        _box(f"kerb_s_{side}", x, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)
    for xs, t in ((+1, "e"), (-1, "w")):
        xc = xs * (R + ARM / 2)
        _box(f"road_{t}", xc, 0, 0.02, ARM, 2 * R, 0.04, M["road"], C_road)
        for side, y in (("n", S1 - SW / 2), ("s", -(S1 - SW / 2))):
            _box(f"sw_{t}_{side}", xc, y, 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)
        for side, y in (("n", R + 0.08), ("s", -R - 0.08)):
            _box(f"kerb_{t}_{side}", xc, y, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)
    _box("sw_t_n_cap", 0, S1 - SW / 2, 0.03, 2 * R, SW, 0.04, M["sidewalk"], C_sw)
    for xs in (+1, -1):
        _box(
            f"sw_t_s_corner_{xs}",
            xs * (R + SW / 2),
            -(R + SW / 2),
            0.03,
            SW,
            SW,
            0.04,
            M["sidewalk"],
            C_sw,
        )
else:
    _box("isect", 0, 0, 0.02, 2 * R, 2 * R, 0.04, M["road"], C_road)
    for ys, t in ((+1, "n"), (-1, "s")):
        yc = ys * (R + ARM / 2)
        _box(f"road_{t}", 0, yc, 0.02, 2 * R, ARM, 0.04, M["road"], C_road)
        _box(f"sw_{t}_e", S1 - SW / 2, yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)
        _box(f"sw_{t}_w", -(S1 - SW / 2), yc, 0.03, SW, ARM, 0.04, M["sidewalk"], C_sw)
        _box(f"kerb_{t}_e", R + 0.08, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)
        _box(f"kerb_{t}_w", -R - 0.08, yc, 0.10, 0.16, ARM, 0.20, M["curb"], C_sw)
    for xs, t in ((+1, "e"), (-1, "w")):
        xc = xs * (R + ARM / 2)
        _box(f"road_{t}", xc, 0, 0.02, ARM, 2 * R, 0.04, M["road"], C_road)
        _box(f"sw_{t}_n", xc, S1 - SW / 2, 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)
        _box(f"sw_{t}_s", xc, -(S1 - SW / 2), 0.03, ARM, SW, 0.04, M["sidewalk"], C_sw)
        _box(f"kerb_{t}_n", xc, R + 0.08, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)
        _box(f"kerb_{t}_s", xc, -R - 0.08, 0.10, ARM, 0.16, 0.20, M["curb"], C_sw)
    for xs, ys in ((1, 1), (1, -1), (-1, 1), (-1, -1)):
        _box(
            f"sw_cor_{xs}{ys}",
            xs * (R + SW / 2),
            ys * (R + SW / 2),
            0.03,
            SW,
            SW,
            0.04,
            M["sidewalk"],
            C_sw,
        )

# ═══════════════════════════════════════════════════════════════════════════════
# ROAD MARKINGS
# ═══════════════════════════════════════════════════════════════════════════════
if LAYOUT_MODE in {"crossroads", "linear_street"}:
    for dx in (-0.10, 0.10):
        _box(f"cl_ns{dx:.0f}", dx, 0, 0.025, 0.08, 2 * FULL, 0.004, M["stripe_y"], C_mk)
if LAYOUT_MODE in {"crossroads", "t_junction"}:
    for dy in (-0.10, 0.10):
        _box(f"cl_ew{dy:.0f}", 0, dy, 0.025, 2 * FULL, 0.08, 0.004, M["stripe_y"], C_mk)

DL, DG = 1.8, 1.8
for sgn in [+1, -1] if LAYOUT_MODE in {"crossroads", "linear_street"} else [-1]:
    for lx in [LC, -LC]:
        y, k = sgn * (R + 1.0), 0
        while abs(y) < FULL - 1.0:
            _box(
                f"dash_ns_{sgn:.0f}_{lx:.1f}_{k}",
                lx,
                y + sgn * DL / 2,
                0.025,
                0.10,
                DL,
                0.004,
                M["stripe_w"],
                C_mk,
            )
            y += sgn * (DL + DG)
            k += 1
for sgn in [+1, -1] if LAYOUT_MODE in {"crossroads", "t_junction"} else []:
    for ly in [LC, -LC]:
        x, k = sgn * (R + 1.0), 0
        while abs(x) < FULL - 1.0:
            _box(
                f"dash_ew_{sgn:.0f}_{ly:.1f}_{k}",
                x + sgn * DL / 2,
                ly,
                0.025,
                DL,
                0.10,
                0.004,
                M["stripe_w"],
                C_mk,
            )
            x += sgn * (DL + DG)
            k += 1

if LAYOUT_MODE == "crossroads":
    for y in ((R + 0.32), -(R + 0.32)):
        _box(f"stop_ns_{y:.1f}", 0, y, 0.025, 2 * R, 0.24, 0.004, M["stripe_w"], C_mk)
    for x in ((R + 0.32), -(R + 0.32)):
        _box(f"stop_ew_{x:.1f}", x, 0, 0.025, 0.24, 2 * R, 0.004, M["stripe_w"], C_mk)
    _crosswalk_ns("n", +1, C_mk)
    _crosswalk_ns("s", -1, C_mk)
    _crosswalk_ew("e", +1, C_mk)
    _crosswalk_ew("w", -1, C_mk)
elif LAYOUT_MODE == "t_junction":
    _box("stop_ns_s", 0, -(R + 0.32), 0.025, 2 * R, 0.24, 0.004, M["stripe_w"], C_mk)
    _crosswalk_ns("s", -1, C_mk)
    _crosswalk_ew("e", +1, C_mk)
    _crosswalk_ew("w", -1, C_mk)

if LAYOUT_MODE in {"crossroads", "linear_street"}:
    _turn_arrow("n_nb1", LC, 16.0, 0.0, C_mk)
    _turn_arrow("n_nb2", LC, 26.0, 0.0, C_mk)
    _turn_arrow("n_sb1", -LC, 16.0, math.pi, C_mk)
    _turn_arrow("n_sb2", -LC, 26.0, math.pi, C_mk)
_turn_arrow("s_sb1", LC, -16.0, 0.0, C_mk)
_turn_arrow("s_nb1", -LC, -16.0, math.pi, C_mk)
if LAYOUT_MODE in {"crossroads", "t_junction"}:
    _turn_arrow("e_eb1", 16.0, -LC, -math.pi / 2, C_mk)
    _turn_arrow("e_eb2", 26.0, -LC, -math.pi / 2, C_mk)
    _turn_arrow("e_wb1", 16.0, LC, math.pi / 2, C_mk)
    _turn_arrow("w_wb1", -16.0, LC, math.pi / 2, C_mk)
    _turn_arrow("w_eb1", -16.0, -LC, -math.pi / 2, C_mk)

# ═══════════════════════════════════════════════════════════════════════════════
# TRAFFIC LIGHTS
# ═══════════════════════════════════════════════════════════════════════════════
if LAYOUT_MODE in {"crossroads", "t_junction"}:
    UA.place_trafficlight((0.0, -(R + 2.6)), C_tl, yaw=0)
    UA.place_trafficlight((-(R + 2.6), 0.0), C_tl, yaw=-math.pi / 2)
    UA.place_trafficlight(((R + 2.6), 0.0), C_tl, yaw=math.pi / 2)
if LAYOUT_MODE == "crossroads":
    UA.place_trafficlight((0.0, (R + 2.6)), C_tl, yaw=math.pi)

# ═══════════════════════════════════════════════════════════════════════════════
# VEHICLES — all30: diverse REAL imported models (openx assets), NOT the simple
# procedural place_infinigen_car cars. Import before heavy vegetation passes to
# avoid Blender 4.2 library-load crashes after TreeFactory/scatter work.
# ═══════════════════════════════════════════════════════════════════════════════
print("[a30] Placing vehicles early (real openx models) ...")

try:
    import gc

    gc.collect()
    print("[a30] Pre-vehicle Python GC complete.")
except Exception as _e:
    print(f"[a30] Pre-vehicle cleanup skipped: {_e}")

_VEH_EXCL = frozenset(
    {"CameraTarget", "KeyLight", "OrbitCamera", "Camera", "Light", "Sun", "Area"}
)
_PRELOADED_CARS = {}


def place_car(tag, blend_path, at, C, yaw=0.0):
    bp = Path(blend_path)
    if not bp.exists():
        print(f"[car] MISSING: {bp}")
        return []
    loaded = _PRELOADED_CARS.pop(str(bp), None)
    if loaded is None:
        with bpy.data.libraries.load(str(bp), link=True) as (src, dst):
            dst.objects = [n for n in src.objects if n not in _VEH_EXCL]
        linked = [o for o in dst.objects if o is not None]
        remap = {}
        for src_obj in linked:
            remap[src_obj] = src_obj.copy()
        for src_obj, obj in remap.items():
            obj.parent = remap.get(src_obj.parent)
            obj.matrix_parent_inverse = src_obj.matrix_parent_inverse.copy()
        loaded = list(remap.values())
    else:
        print(f"[car] Using preloaded asset for {bp.name}")
    root = None
    objs = []
    for o in loaded:
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
        print(f"[car] WARNING: no Grp_Root in {bp.name}")
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
    "tesla": OX_BASE / "n2_tesla_cybertruck_2024/n2_tesla_cybertruck_2024.blend",
    # The original Mercedes SL65 asset segfaults Blender 4.2.0 in this scene, so
    # keep a real openx sports-roadster model at this slot.
    "merc": OX_BASE / "m1_audi_tt_2014_roadster/m1_audi_tt_2014_roadster.blend",
    "audi_tt": OX_BASE / "m1_audi_tt_2014_roadster/m1_audi_tt_2014_roadster.blend",
    "ex30": OX_BASE / "m1_volvo_ex30_2024/m1_volvo_ex30_2024.blend",
}

if os.environ.get("ALL41_SAFE_VEHICLES") == "1":
    print(
        "[a30] ALL41_SAFE_VEHICLES: replacing unstable vehicle assets with verified openx models."
    )
    CARS["gmc"] = CARS["audi"]
    CARS["mini"] = CARS["bmw"]

if LAYOUT_MODE in {"crossroads", "linear_street"}:
    place_car("vn1", CARS["bmw"], (LC, 20.0), C_cars, yaw=math.pi / 2)
    place_car("vn2", CARS["volvo"], (LC, 34.0), C_cars, yaw=math.pi / 2)
    place_car("vn3", CARS["audi"], (-LC, 27.0), C_cars, yaw=-math.pi / 2)
    # Avoid the Cybertruck asset here: its intentionally planar real-world
    # body reads as a low-detail proxy from validation-camera distances.
    place_car("vn4", CARS["bmw"], (-LC, 42.0), C_cars, yaw=-math.pi / 2)
    place_car("vn5", CARS["merc"], (LC, 47.0), C_cars, yaw=math.pi / 2)
place_car("vs1", CARS["mini"], (LC, -18.0), C_cars, yaw=-math.pi / 2)
place_car("vs2", CARS["hyundai"], (-LC, -14.0), C_cars, yaw=math.pi / 2)
place_car("vs3", CARS["audi"], (LC, -34.0), C_cars, yaw=-math.pi / 2)
place_car("vs4", CARS["audi_tt"], (-LC, -40.0), C_cars, yaw=math.pi / 2)
if LAYOUT_MODE in {"crossroads", "t_junction"}:
    place_car("ve1", CARS["fiat"], (22.0, -LC), C_cars, yaw=0)
    place_car("ve2", CARS["dacia"], (38.0, -LC), C_cars, yaw=0)
    place_car("ve3", CARS["gmc"], (20.0, LC), C_cars, yaw=math.pi)
    place_car("ve4", CARS["ex30"], (44.0, LC), C_cars, yaw=math.pi)
    place_car("ve5", CARS["hyundai"], (50.0, -LC), C_cars, yaw=0)
    place_car("vw1", CARS["bmw"], (-26.0, LC), C_cars, yaw=math.pi)
    place_car("vw2", CARS["volvo"], (-40.0, -LC), C_cars, yaw=0)
    place_car("vw3", CARS["dacia"], (-14.0, -LC), C_cars, yaw=0)
    place_car("vw4", CARS["mini"], (-48.0, LC), C_cars, yaw=math.pi)

print(f"[a30] Vehicles placed early for {LAYOUT_MODE} (real OpenX models only).")

# ═══════════════════════════════════════════════════════════════════════════════
# CURB FLOWER BEDS (ProcShrubFactory shrubs)
# ═══════════════════════════════════════════════════════════════════════════════
print("[all8] Building flower beds ...")
if LAYOUT_MODE in {"crossroads", "linear_street"}:
    # N arm E: gaps at bus/bike stops and house drives.
    _fb_ns("fb_ne1", S1, "e", R, 12.0, C_fb)
    _fb_ns("fb_ne2", S1, "e", 16.5, 19.0, C_fb)
    _fb_ns("fb_ne3", S1, "e", 23.0, 34.0, C_fb)
    _fb_ns("fb_ne4", S1, "e", 38.0, 48.0, C_fb)
    _fb_ns("fb_ne5", S1, "e", 52.0, R + ARM, C_fb)
    _fb_ns("fb_nw1", -S1, "w", R, 36.0, C_fb)
    _fb_ns("fb_nw2", -S1, "w", 40.0, R + ARM, C_fb)

# S arm E: gaps at shop entrances
_fb_ns("fb_se1", S1, "e", -(R + ARM), -46.0, C_fb)
_fb_ns("fb_se2", S1, "e", -42.0, -32.0, C_fb)
_fb_ns("fb_se3", S1, "e", -28.0, -18.0, C_fb)
_fb_ns("fb_se4", S1, "e", -14.0, -R, C_fb)

# S arm W
_fb_ns("fb_sw1", -S1, "w", -(R + ARM), -32.0, C_fb)
_fb_ns("fb_sw2", -S1, "w", -28.0, -18.0, C_fb)
_fb_ns("fb_sw3", -S1, "w", -14.0, -R, C_fb)

if LAYOUT_MODE in {"crossroads", "t_junction"}:
    # Through-road planting follows the east/west arms only when they exist.
    _fb_ew("fb_en1", S1, "n", R, 14.0, C_fb)
    _fb_ew("fb_en2", S1, "n", 18.0, R + ARM, C_fb)
    _fb_ew("fb_es", -S1, "s", R, R + ARM, C_fb)
    _fb_ew("fb_wn", S1, "n", -(R + ARM), -R, C_fb)
    _fb_ew("fb_ws", -S1, "s", -(R + ARM), -R, C_fb)

_build_full06_belt4_flower_layer(C_fb)

print("[all8] Flower beds done.")

# ═══════════════════════════════════════════════════════════════════════════════
# NORTH ARM — RESIDENTIAL ZONE
# ═══════════════════════════════════════════════════════════════════════════════
print("[all8] Building residential zone ...")

UA.place_busstop((S1 - SW / 2, 14.0), C_n, yaw=-math.pi / 2, scale=1.5)

_box("bike_pad", 14.5, 21.0, 0.03, 8.0, 6.5, 0.06, M["stone_path"], C_sw)
UA.place_bicycle_station((14.5, 21.0), C_n, yaw=0)

# all28: houses hA/hB/hC removed. all29: ALL fences removed too (_build_fence
# (Dropped calls) driveways were left untouched ("Other parts remained as they were") - vacant lots.
HA_CX, HA_CY, HA_FW, HA_FD = 24.0, 36.0, 23.0, 14.0
_box("drv_a_fb", 9.25, HA_CY, 0.03, FW, 2.5, 0.06, M["stone_path"], C_sw)
_box("drv_a_z", 11.5, HA_CY, 0.03, 2.5, 2.5, 0.06, M["stone_path"], C_sw)

HB_CX, HB_CY, HB_FW, HB_FD = 24.0, 50.0, 23.0, 14.0
_box("drv_b_fb", 9.25, HB_CY, 0.03, FW, 2.5, 0.06, M["stone_path"], C_sw)
_box("drv_b_z", 11.5, HB_CY, 0.03, 2.5, 2.5, 0.06, M["stone_path"], C_sw)

HC_CX, HC_CY, HC_FW, HC_FD = -24.0, 38.0, 23.0, 14.0
_box("drv_c_fb", -9.25, HC_CY, 0.03, FW, 2.5, 0.06, M["stone_path"], C_sw)
_box("drv_c_z", -11.5, HC_CY, 0.03, 2.5, 2.5, 0.06, M["stone_path"], C_sw)

# These legacy one-off yard shrubs spill into the park quadrant (the positive-X
# lots were removed years ago).  full06 forbids the entire isolated family;
# intentional vegetation remains as real trees and continuous flowerbeds.
if not FULL06_LANDSCAPE:
    for i, (sx, sy, sd) in enumerate(
        [(16, 30, 3), (18, 42, 7), (30, 30, 11), (30, 42, 15)]
    ):
        sh = ProcShrubFactory(seed=sd, max_spread=0.25, max_height=1.2)
        sh.create_asset(location=(sx, sy, 0.08), name=f"ysh_a{i}", coll=C_tree)
    for i, (sx, sy, sd) in enumerate(
        [(16, 44, 19), (18, 56, 23), (30, 44, 27), (30, 56, 31)]
    ):
        sh = ProcShrubFactory(seed=sd, max_spread=0.25, max_height=1.2)
        sh.create_asset(location=(sx, sy, 0.08), name=f"ysh_b{i}", coll=C_tree)
    for i, (sx, sy, sd) in enumerate(
        [(-16, 32, 35), (-30, 32, 39), (-16, 44, 43), (-30, 44, 47)]
    ):
        sh = ProcShrubFactory(seed=sd, max_spread=0.25, max_height=1.2)
        sh.create_asset(location=(sx, sy, 0.08), name=f"ysh_c{i}", coll=C_tree)

if os.environ.get("C2W_FULL_02") != "1" and os.environ.get("C2W_FULL_REVISION") not in (
    "urban_v1_full_03",
    "urban_v1_full_04",
    "urban_v1_full_05",
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
):
    # Legacy oversized shrubs used as street-tree stand-ins.
    for i, (ty, sd) in enumerate([(8, 51), (18, 55), (28, 59), (40, 63), (50, 67)]):
        she = ProcShrubFactory(seed=sd, max_spread=0.55, max_height=2.8)
        she.create_asset(location=(9.25, ty, 0.10), name=f"nt_e{i}", coll=C_tree)
        shw = ProcShrubFactory(seed=sd + 2, max_spread=0.55, max_height=2.8)
        shw.create_asset(location=(-9.25, ty, 0.10), name=f"nt_w{i}", coll=C_tree)

for y in [7, 15, 22, 30, 38, 46, 52]:
    UA.place_streetlight((S1 - SW / 2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-S1 + SW / 2, y), C_lamp, yaw=-math.pi / 2, day=True)

for y in [20, 42]:
    UA.place_bench_classic((S1 - SW * 0.8, y), C_furn, yaw=math.pi / 2)
    UA.place_bench_classic((-S1 + SW * 0.8, y), C_furn, yaw=-math.pi / 2)
for y in [28, 48]:
    UA.place_bin_domed((S1 - SW * 0.8, y), C_furn)
    UA.place_bin_domed((-S1 + SW * 0.8, y), C_furn)
# full07 relocates the only booth into the commercial shopping parcel during
# integration.  No telephone booth is authored beside or within the roadway.
if not FULL07:
    _phone_x = (
        -S1 - SW * 0.15
        if os.environ.get("C2W_FULL_REVISION") == "urban_v1_full_04"
        else -S1 + SW * 0.6
    )
    for _o in UA.place_phonebooth((_phone_x, 18.0), C_furn, yaw=math.pi / 2):
        _o["c2w_phonebooth_role"] = "roadside_sidewalk"

# ═══════════════════════════════════════════════════════════════════════════════
# EAST ARM — PARK ZONE
# ═══════════════════════════════════════════════════════════════════════════════
print("[all8] Building park zone ...")

PARK_X0, PARK_X1 = G1, 54.5 if os.environ.get("C2W_FULL_02") == "1" else 54.0
PARK_Y0, PARK_Y1 = G1, 54.5 if os.environ.get("C2W_FULL_02") == "1" else 44.5
PARK_CX = (PARK_X0 + PARK_X1) / 2
PARK_CY = (PARK_Y0 + PARK_Y1) / 2

# Park lawn — dense grid for scatter
bpy.ops.mesh.primitive_grid_add(
    x_subdivisions=300, y_subdivisions=270, size=1.0, location=(PARK_CX, PARK_CY, 0.015)
)
park_lawn_obj = bpy.context.active_object
park_lawn_obj.name = "park_lawn_grid"
park_lawn_obj.scale = (PARK_X1 - PARK_X0, PARK_Y1 - PARK_Y0, 1.0)
bpy.ops.object.transform_apply(scale=True)
park_lawn_obj.data.materials.append(M["grass_park"])
UA.to_coll(park_lawn_obj, C_e)

# all29: cut a circular hole in the lawn grid at the park centre so NO grass/
# flower scatter grows where the marble plaza will sit (marble fully covers the
# ground there). Done BEFORE scatter so the scatter modifier sees the hole.
import bmesh

PLZ_CX, PLZ_CY, PLZ_R = 34.0, 30.0, 5.0
_bm = bmesh.new()
_bm.from_mesh(park_lawn_obj.data)
_mw = park_lawn_obj.matrix_world
_del = []
for _f in _bm.faces:
    _w = _mw @ _f.calc_center_median()
    _plaza_hole = (_w.x - PLZ_CX) ** 2 + (_w.y - PLZ_CY) ** 2 < PLZ_R**2
    # full06 also removes the lawn faces below every park path before Grass
    # scatter.  This prevents blades from punching through the paving and
    # makes the paths read as intentional warm paving rather than white bars.
    _path_hole = FULL06_LANDSCAPE and (
        (14.72 <= _w.x <= 17.28)
        or (26.72 <= _w.y <= 29.28)
        or (G1 <= _w.x <= 38.0 and 18.97 <= _w.y <= 21.03)
    )
    if _plaza_hole or _path_hole:
        _del.append(_f)
bmesh.ops.delete(_bm, geom=_del, context="FACES")
_bm.to_mesh(park_lawn_obj.data)
_bm.free()
park_lawn_obj.data.update()
print(
    f"[a29] Cut {len(_del)} lawn faces for marble plaza at ({PLZ_CX},{PLZ_CY}) r={PLZ_R}"
)

park_s_obj = None
if os.environ.get("C2W_FULL_02") != "1" and os.environ.get("C2W_FULL_REVISION") not in (
    "urban_v1_full_03",
    "urban_v1_full_04",
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
):
    # Legacy south strip is not part of the park and overlapped the basketball court.
    SPARKS_Y0, SPARKS_Y1 = -30.0, -G1
    bpy.ops.mesh.primitive_grid_add(
        x_subdivisions=200,
        y_subdivisions=100,
        size=1.0,
        location=(PARK_CX, (SPARKS_Y0 + SPARKS_Y1) / 2, 0.015),
    )
    park_s_obj = bpy.context.active_object
    park_s_obj.name = "park_lawn_s_grid"
    park_s_obj.scale = (PARK_X1 - PARK_X0, SPARKS_Y1 - SPARKS_Y0, 1.0)
    bpy.ops.object.transform_apply(scale=True)
    park_s_obj.data.materials.append(M["grass_park"])
    UA.to_coll(park_s_obj, C_e)


# Apply infinigen Flowerplant + Grass scatter on BOTH park lawns.
# all27: denser than all8 (0.7/6.0, main only) and now also on the south strip.
def _scatter_lawn(obj, fp_seed, gr_seed, fp_density, gr_density):
    if os.environ.get("C2W_FULL_02") != "1":
        try:
            from infinigen.assets.scatters.flowerplant import Flowerplant

            with FixedSeed(fp_seed):
                Flowerplant().apply(obj, selection=None, density=fp_density)
            print(f"[a27] Flowerplant scatter -> {obj.name} (d={fp_density})")
        except Exception as _fe:
            print(f"[a27] Flowerplant note ({obj.name}): {_fe}")
    try:
        from infinigen.assets.scatters.grass import Grass

        with FixedSeed(gr_seed):
            Grass().apply(obj, density=gr_density)
        print(f"[a27] Grass scatter -> {obj.name} (d={gr_density})")
    except Exception as _ge:
        print(f"[a27] Grass note ({obj.name}): {_ge}")


_scatter_lawn(park_lawn_obj, 42, 137, fp_density=1.0, gr_density=8.0)
if park_s_obj is not None:
    _scatter_lawn(park_s_obj, 43, 138, fp_density=0.6, gr_density=5.0)

# Strict full03 keeps the physically detailed grass scatter, but retunes the
# inherited scatter shader from its dead/khaki palette to an emerald lawn.
# This is deliberately done in the generator after Grass().apply(), since the
# scatter asset material is created lazily by the Infinigen scatter pass.
if os.environ.get("C2W_FULL_REVISION") in (
    "urban_v1_full_03",
    "urban_v1_full_04",
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
):
    for _mat in bpy.data.materials:
        if _mat.name != "shader_grass_texture_original" or not _mat.use_nodes:
            continue
        _nt = _mat.node_tree
        _ramp_nodes = [n for n in _nt.nodes if n.bl_idname == "ShaderNodeValToRGB"]
        for _rn in _ramp_nodes:
            _els = sorted(_rn.color_ramp.elements, key=lambda e: e.position)
            for _i, _el in enumerate(_els):
                _t = _i / max(1, len(_els) - 1)
                _el.color = (
                    (0.060 + 0.105 * _t, 0.145 + 0.185 * _t, 0.045 + 0.075 * _t, 1.0)
                    if FULL06_LANDSCAPE
                    else (0.008 + 0.035 * _t, 0.18 + 0.30 * _t, 0.012 + 0.035 * _t, 1.0)
                )
        for _n in _nt.nodes:
            if _n.bl_idname == "ShaderNodeBsdfPrincipled":
                _n.inputs["Base Color"].default_value = (
                    (0.105, 0.245, 0.075, 1.0)
                    if FULL06_LANDSCAPE
                    else (0.02, 0.34, 0.025, 1.0)
                )
            elif _n.bl_idname == "ShaderNodeBsdfTranslucent":
                _n.inputs["Color"].default_value = (
                    (0.120, 0.275, 0.085, 1.0)
                    if FULL06_LANDSCAPE
                    else (0.03, 0.38, 0.03, 1.0)
                )
        print(
            "[a27] Retuned shader_grass_texture_original to "
            + ("pale sage palette" if FULL06_LANDSCAPE else "emerald palette")
        )

# Park entrance
_cyl("pk_gp1", 14.0, G1 + 0.3, 0, 0.14, 2.4, M["gate_post"], C_e, verts=8)
_cyl("pk_gp2", 18.0, G1 + 0.3, 0, 0.14, 2.4, M["gate_post"], C_e, verts=8)
_box("pk_ep", 16.0, (S1 + G1) / 2, 0.04, 4.2, FW, 0.08, M["park_path"], C_e)

# Internal park path network
_box(
    "ppth_ns",
    16.0,
    (PARK_Y0 + PARK_Y1) / 2,
    0.05,
    2.5,
    PARK_Y1 - PARK_Y0,
    0.10,
    M["park_path"],
    C_e,
)
_box(
    "ppth_ew",
    (PARK_X0 + PARK_X1) / 2,
    28.0,
    0.05,
    PARK_X1 - PARK_X0,
    2.5,
    0.10,
    M["park_path"],
    C_e,
)
_box("ppth_ew2", (G1 + 38) / 2, 20.0, 0.05, 38 - G1, 2.0, 0.10, M["park_path"], C_e)


# ═══ all29: MARBLE PLAZA + CHROME-TREFOIL SCULPTURE (park centre) ═════════════
# all28 had removed pavilion/sculpture/water. all29 adds a small marble floor
# patch (the lawn scatter was cut out above) carrying a chrome mirror-knot.
def marble_mat(name="a29_marble"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nds, lks = nt.nodes, nt.links
    for n in list(nds):
        nds.remove(n)
    out = nds.new("ShaderNodeOutputMaterial")
    bsdf = nds.new("ShaderNodeBsdfPrincipled")
    tex = nds.new("ShaderNodeTexCoord")
    nz = nds.new("ShaderNodeTexNoise")
    nz.inputs["Scale"].default_value = 2.5
    nz.inputs["Detail"].default_value = 8.0
    nz.inputs["Distortion"].default_value = 2.0
    lks.new(tex.outputs["Object"], nz.inputs["Vector"])
    wv = nds.new("ShaderNodeTexWave")
    wv.inputs["Scale"].default_value = 1.2
    wv.inputs["Distortion"].default_value = 12.0
    wv.inputs["Detail"].default_value = 3.0
    lks.new(tex.outputs["Object"], wv.inputs["Vector"])
    lks.new(nz.outputs["Fac"], wv.inputs["Phase Offset"])
    ramp = nds.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.35
    ramp.color_ramp.elements[0].color = (0.88, 0.87, 0.85, 1.0)  # white marble
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.40, 0.42, 0.46, 1.0)  # grey veining
    lks.new(wv.outputs["Color"], ramp.inputs["Fac"])
    lks.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    _set(bsdf, "Roughness", 0.14)
    bump = nds.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.04
    lks.new(wv.outputs["Color"], bump.inputs["Height"])
    lks.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    lks.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


M["marble"] = marble_mat()

# Marble floor disk (r 5.2 > hole 5.0 so it hides the cut edge), thin — a floor.
_cyl("plz_marble", PLZ_CX, PLZ_CY, 0.045, 5.2, 0.08, M["marble"], C_e, verts=64)
_cyl("plz_rim", PLZ_CX, PLZ_CY, 0.025, 5.5, 0.05, M["park_stone"], C_e, verts=64)


# Chrome mirror-knot (trefoil) sculpture from public_art.blend, on the marble.
# all30: centre the sculpture on the marble by the RIBBON loop's bbox (its
# geometric centre = the designed trefoil centre), not _place's origin bbox
# (which is skewed toward the off-centre plinth) → sculpture sits dead-centre.
def _center_sculpture(objs, tx, ty, tz_base):
    # depsgraph-inert: use matrix_basis (always current for unparented objects),
    # NO view_layer.update() — a full depsgraph poke here after appending the
    # curve-based knot could leave a dangling ref that segfaults later builds.
    def wbb(o):
        return [o.matrix_basis @ Vector(c) for c in o.bound_box]

    anchor = next((o for o in objs if o.name.endswith("ribbon")), objs[0])
    axs = wbb(anchor)
    acx = (min(v.x for v in axs) + max(v.x for v in axs)) / 2
    acy = (min(v.y for v in axs) + max(v.y for v in axs)) / 2
    zmin = min(v.z for o in objs for v in wbb(o))
    dx, dy, dz = tx - acx, ty - acy, tz_base - zmin
    for o in objs:
        o.location.x += dx
        o.location.y += dy
        o.location.z += dz


knot_objs = UA._import_prefix(SC_BLEND, "knot:", C_e)
if knot_objs:
    _center_sculpture(knot_objs, PLZ_CX, PLZ_CY, tz_base=0.085)  # marble top
    print(
        f"[a30] Chrome trefoil sculpture centred on marble ({len(knot_objs)} objects)"
    )
else:
    print("[a29] WARN: knot import failed — using fallback chrome torus")
    bpy.ops.mesh.primitive_torus_add(
        major_radius=1.2, minor_radius=0.30, location=(PLZ_CX, PLZ_CY, 1.7)
    )
    _k = bpy.context.active_object
    _k.name = "plz_knot_fb"
    _k.data.materials.append(
        UA._pbr("chrome_fb", (0.85, 0.86, 0.88), rough=0.05, metal=1.0)
    )
    UA.to_coll(_k, C_e)

for bx, by, byw in [
    (18.5, 26.0, math.pi / 2),
    (26.0, 36.0, 0.0),
    (40.0, 22.0, math.pi / 2),
    (42.0, 38.0, 0.0),
]:
    UA.place_bench_classic((bx, by), C_e, yaw=byw)
for bx, by in [(22.0, 32.0), (38.0, 44.0)]:
    UA.place_bin_domed((bx, by), C_e)

# ─────────────────────────────────────────────────────────────────────────────
# ENRICHED PARK VEGETATION  (all27 change vs all8 — "richer vegetation")
# ─────────────────────────────────────────────────────────────────────────────
print("[a27] Enriching park vegetation ...")

# Keep-out circles around fixed features (x, y, radius)
_PK_KEEPOUT = [
    (34.0, 30.0, 7.5),  # pavilion + stone plaza
    (26.0, 22.0, 4.0),  # water feature
    (44.0, 38.0, 3.0),  # corten sculpture ring
    (16.0, (S1 + G1) / 2, 3.0),  # entrance-path mouth
]
# Existing park furniture (benches + bins) — keep a little clearance
_PK_FURN = [
    (18.5, 26.0),
    (26.0, 36.0),
    (40.0, 22.0),
    (42.0, 38.0),
    (22.0, 32.0),
    (38.0, 44.0),
]


def _pk_on_path(x, y, m=0.0):
    if 14.75 - m < x < 17.25 + m:
        return True  # NS spine
    if 26.75 - m < y < 29.25 + m:
        return True  # EW spine
    if 10.5 < x < 38.0 and 19.0 - m < y < 21.0 + m:
        return True  # EW2 branch
    return False


def _pk_clear(x, y, margin=1.5):
    if not (PARK_X0 + 0.8 < x < PARK_X1 - 0.8):
        return False
    if not (PARK_Y0 + 0.8 < y < PARK_Y1 - 0.8):
        return False
    if _pk_on_path(x, y, m=margin * 0.6):
        return False
    for ox, oy, orr in _PK_KEEPOUT:
        if (x - ox) ** 2 + (y - oy) ** 2 < (orr + margin) ** 2:
            return False
    for ox, oy in _PK_FURN:
        if (x - ox) ** 2 + (y - oy) ** 2 < 1.4**2:
            return False
    return True


# --- (1) Canopy trees: TreeFactory on a jittered grid, collision-avoided ---
_urban_seed = int(os.environ.get("C2W_URBAN_SEED", "2027"))
_urban_variant = os.environ.get("C2W_URBAN_VARIANT", "baseline")
_rng_pk = np.random.default_rng(_urban_seed + 1026)
_tree_cand = []
for gx in np.arange(PARK_X0 + 3.0, PARK_X1 - 2.0, 6.5):
    for gy in np.arange(PARK_Y0 + 3.0, PARK_Y1 - 2.0, 6.5):
        jx = float(gx + _rng_pk.uniform(-1.6, 1.6))
        jy = float(gy + _rng_pk.uniform(-1.6, 1.6))
        if _pk_clear(jx, jy, margin=2.6):
            _tree_cand.append((jx, jy))
# Variant parameters are consumed here by the real TreeFactory placement pass.
_tree_spacing = 6.6 if _urban_variant == "demo1" else 5.6
_tree_cap = 11 if _urban_variant == "demo1" else 18
_pk_trees = []
for x, y in _tree_cand:
    if all((x - kx) ** 2 + (y - ky) ** 2 > _tree_spacing**2 for kx, ky in _pk_trees):
        _pk_trees.append((x, y))
    if len(_pk_trees) >= _tree_cap:
        break
print(f"[a27] Park canopy trees (TreeFactory): {len(_pk_trees)}")
for i, (tx, ty) in enumerate(_pk_trees):
    _gen_park_tree(f"pk_tr{i}", tx, ty, C_e, seed=_TREE_SEEDS[i % len(_TREE_SEEDS)])

# --- (2) Undergrowth: dense ProcShrubFactory clusters across the lawn ---
_rng_sh = np.random.default_rng(_urban_seed + 6761)
_n_ush = 0
for gx in np.arange(PARK_X0 + 2.0, PARK_X1 - 1.5, 3.0):
    for gy in np.arange(PARK_Y0 + 2.0, PARK_Y1 - 1.5, 3.0):
        if os.environ.get("C2W_FULL_REVISION") in (
            "urban_v1_full_03",
            "urban_v1_full_04",
            "urban_v1_full_05",
            "urban_v1_full_06",
            "urban_v1_full_07",
            "urban_v1_full_08",
        ):
            continue
        jx = float(gx + _rng_sh.uniform(-0.9, 0.9))
        jy = float(gy + _rng_sh.uniform(-0.9, 0.9))
        if not _pk_clear(jx, jy, margin=0.8):
            continue
        if any((jx - tx) ** 2 + (jy - ty) ** 2 < 1.6**2 for tx, ty in _pk_trees):
            continue
        _shrub_probability = 0.34 if _urban_variant == "demo1" else 0.68
        if _rng_sh.uniform() < _shrub_probability:
            sd = (91000 + _n_ush * 7) % 99991
            # ProcShrubFactory clamps height via uniform(0.70, max_height),
            # so max_height must stay >= 0.70.
            sh = ProcShrubFactory(
                seed=sd, max_spread=0.26, max_height=float(_rng_sh.uniform(0.85, 1.15))
            )
            sh.create_asset(
                location=(jx, jy, 0.08), name=f"pk_ush{_n_ush}", coll=C_tree
            )
            _n_ush += 1
print(f"[a27] Park undergrowth shrubs: {_n_ush}")


# --- (3) Dedicated flower / shrub patches (soil bed + tight shrubs) ---
def _park_flower_patch(tag, cx, cy, dx, dy, seed):
    _box(f"{tag}_bed", cx, cy, 0.035, dx, dy, 0.07, M["soil"], C_e)
    _place_shrubs_along(tag, cx, cy, dx - 0.3, dy - 0.3, C_tree, spacing=1.1, seed=seed)


if os.environ.get("C2W_FULL_02") != "1" and os.environ.get("C2W_FULL_REVISION") not in (
    "urban_v1_full_03",
    "urban_v1_full_04",
    "urban_v1_full_05",
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
):
    for tag, (cx, cy, dx, dy, sd) in {
        "pfp1": (13.0, 40.0, 3.4, 4.5, 3111),
        "pfp2": (50.0, 33.0, 4.0, 6.0, 3222),
        "pfp3": (30.0, 41.5, 7.0, 3.0, 3333),
        "pfp4": (48.0, 14.5, 5.0, 4.0, 3444),
        "pfp5": (13.0, 14.0, 3.4, 3.5, 3555),
    }.items():
        _park_flower_patch(tag, cx, cy, dx, dy, sd)
    print("[a27] Park flower patches placed.")
else:
    print("[full02] Park flower patches disabled; continuous lawn retained.")

if os.environ.get("C2W_FULL_02") != "1":
    for i, (tx, sd) in enumerate([(8, 71), (18, 75), (28, 79), (38, 83), (48, 87)]):
        she = ProcShrubFactory(seed=sd, max_spread=0.55, max_height=2.8)
        she.create_asset(location=(tx, 9.25, 0.10), name=f"et_n{i}", coll=C_tree)
        shw = ProcShrubFactory(seed=sd + 2, max_spread=0.55, max_height=2.8)
        shw.create_asset(location=(tx, -9.25, 0.10), name=f"et_s{i}", coll=C_tree)

for x in [7, 15, 22, 30, 38, 46, 52]:
    UA.place_streetlight((x, S1 - SW / 2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -S1 + SW / 2), C_lamp, yaw=0.0, day=True)

# ═══════════════════════════════════════════════════════════════════════════════
# SOUTH ARM — COMMERCIAL ZONE
# ═══════════════════════════════════════════════════════════════════════════════
print("[all8] Building commercial zone ...")
SHOP_D = 8.0
SHOP_H = 4.2
SHOP_W = 12.0
SH_CX_E = G1 + SHOP_D / 2
SH_CX_W = -G1 - SHOP_D / 2

# all28: all shop buildings (shA_e..shE_w) REMOVED per request. Kiosk, phone
# booth, benches, bins, street trees and lamps in the commercial zone stay.

UA.place_kiosk5((S1 - SW / 2, -24.0), C_s, yaw=-math.pi / 2, scale=0.9)
if not FULL07:
    _phone_x_s = (
        S1 + SW * 0.15
        if os.environ.get("C2W_FULL_REVISION") == "urban_v1_full_04"
        else S1 - SW * 0.6
    )
    for _o in UA.place_phonebooth((_phone_x_s, -38.0), C_s, yaw=-math.pi / 2):
        _o["c2w_phonebooth_role"] = "roadside_sidewalk"

for y in [-20.0, -36.0, -50.0]:
    UA.place_bench_classic((S1 - SW * 0.8, y), C_furn, yaw=math.pi / 2)
for y in [-26.0, -44.0]:
    UA.place_bench_classic((-S1 + SW * 0.8, y), C_furn, yaw=-math.pi / 2)
for y in [-22.0, -42.0]:
    UA.place_bin_domed((S1 - SW * 0.8, y), C_furn)
UA.place_bin_domed((-S1 + SW * 0.8, -30.0), C_furn)

if os.environ.get("C2W_FULL_REVISION") not in (
    "urban_v1_full_03",
    "urban_v1_full_04",
    "urban_v1_full_05",
    "urban_v1_full_06",
    "urban_v1_full_07",
    "urban_v1_full_08",
):
    for i, (ty, sd) in enumerate(
        [(-8, 91), (-20, 95), (-34, 99), (-46, 103), (-52, 107)]
    ):
        she = ProcShrubFactory(seed=sd, max_spread=0.55, max_height=2.8)
        she.create_asset(location=(9.25, ty, 0.10), name=f"st_e{i}", coll=C_tree)
        shw = ProcShrubFactory(seed=sd + 2, max_spread=0.55, max_height=2.8)
        shw.create_asset(location=(-9.25, ty, 0.10), name=f"st_w{i}", coll=C_tree)

for y in [-7, -15, -22, -30, -38, -46, -52]:
    UA.place_streetlight((S1 - SW / 2, y), C_lamp, yaw=math.pi / 2, day=True)
    UA.place_streetlight((-S1 + SW / 2, y), C_lamp, yaw=-math.pi / 2, day=True)

# ═══════════════════════════════════════════════════════════════════════════════
# WEST ARM — GREEN BELT
# ═══════════════════════════════════════════════════════════════════════════════
print("[all8] Building west arm ...")
_WLCX = -(R + ARM / 2)

# West lawn with grass material
bpy.ops.mesh.primitive_grid_add(
    x_subdivisions=200, y_subdivisions=200, size=1.0, location=(_WLCX, 28.0, 0.01)
)
wln_obj = bpy.context.active_object
wln_obj.name = "wst_lawn_n_grid"
wln_obj.scale = (ARM, 36.0, 1.0)
bpy.ops.object.transform_apply(scale=True)
wln_obj.data.materials.append(M["grass_park"])
UA.to_coll(wln_obj, C_w)

bpy.ops.mesh.primitive_grid_add(
    x_subdivisions=200, y_subdivisions=200, size=1.0, location=(_WLCX, -28.0, 0.01)
)
wls_obj = bpy.context.active_object
wls_obj.name = "wst_lawn_s_grid"
wls_obj.scale = (ARM, 36.0, 1.0)
bpy.ops.object.transform_apply(scale=True)
wls_obj.data.materials.append(M["grass_park"])
UA.to_coll(wls_obj, C_w)

if not FULL06_LANDSCAPE:
    for i, (tx, sd) in enumerate(
        [(-8, 111), (-18, 115), (-28, 119), (-38, 123), (-48, 127)]
    ):
        she = ProcShrubFactory(seed=sd, max_spread=0.55, max_height=2.8)
        she.create_asset(location=(tx, 9.25, 0.10), name=f"wt_n{i}", coll=C_tree)
        shw = ProcShrubFactory(seed=sd + 2, max_spread=0.55, max_height=2.8)
        shw.create_asset(location=(tx, -9.25, 0.10), name=f"wt_s{i}", coll=C_tree)

UA.place_bench_classic((-15.0, S1 - SW * 0.8), C_furn, yaw=0)
UA.place_bench_classic((-28.0, -S1 + SW * 0.8), C_furn, yaw=0)

for x in [-7, -15, -22, -30, -38, -46, -52]:
    UA.place_streetlight((x, S1 - SW / 2), C_lamp, yaw=math.pi, day=True)
    UA.place_streetlight((x, -S1 + SW / 2), C_lamp, yaw=0.0, day=True)


# ═══════════════════════════════════════════════════════════════════════════════
# PARAMETRIC ROAD TOPOLOGY
# ═══════════════════════════════════════════════════════════════════════════════
# Road-adjacent furniture is also topology-aware.  Regional buildings are not
# filtered here: only the streetscape objects whose supporting arm does not
# exist are suppressed.
def _in_removed_approach(obj):
    p = obj.matrix_world.translation
    if LAYOUT_MODE == "linear_street":
        return abs(p.x) > G1 and abs(p.y) < G1
    if LAYOUT_MODE == "t_junction":
        return abs(p.x) < G1 and p.y > G1
    return False


removed_streetscape = []
for _coll in (C_lamp, C_furn, C_tree, C_n):
    for _obj in _coll.objects:
        if _in_removed_approach(_obj):
            _obj.hide_render = True
            _obj.hide_viewport = True
            removed_streetscape.append(_obj.name)

visible_roads = sorted(o.name for o in C_road.objects if not o.hide_render)
expected_roads = {
    "linear_street": ["road_linear_ns"],
    "t_junction": ["road_e", "road_s", "road_w", "t_junction_center"],
    "crossroads": ["isect", "road_e", "road_n", "road_s", "road_w"],
}[LAYOUT_MODE]
if visible_roads != expected_roads:
    raise RuntimeError(
        f"Road topology construction failed for {LAYOUT_MODE}: "
        f"expected={expected_roads}, actual={visible_roads}"
    )
bpy.context.scene["c2w_layout_mode"] = LAYOUT_MODE
bpy.context.scene["c2w_visible_road_objects"] = ",".join(visible_roads)
bpy.context.scene["c2w_removed_streetscape_count"] = len(removed_streetscape)
print(
    f"[all30] Built physical topology={LAYOUT_MODE}; roads={visible_roads}; "
    f"removed unsupported streetscape objects={len(removed_streetscape)}",
    flush=True,
)

# ═══════════════════════════════════════════════════════════════════════════════
# LIGHTING — Nishita sky + split-sky trick + warm sun
# ═══════════════════════════════════════════════════════════════════════════════
bpy.context.scene.world = bpy.data.worlds.new("sky_a8")
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
sky.sun_elevation = math.radians(42)
sky.sun_rotation = math.radians(215)
sky.altitude = 1000.0
sky.air_density = 1.0
sky.dust_density = 0.5

bg.inputs["Strength"].default_value = 1.0
bg2.inputs["Strength"].default_value = 0.7

wt.links.new(sky.outputs["Color"], bg.inputs["Color"])
wt.links.new(sky.outputs["Color"], bg2.inputs["Color"])
wt.links.new(lp.outputs["Is Camera Ray"], mix.inputs["Fac"])
wt.links.new(bg.outputs["Background"], mix.inputs[1])
wt.links.new(bg2.outputs["Background"], mix.inputs[2])
wt.links.new(mix.outputs["Shader"], out.inputs["Surface"])

bpy.ops.object.light_add(type="SUN", location=(20, -40, 60))
sun = bpy.context.active_object
sun.name = "Sun_a8"
sun.data.energy = 5.0
sun.data.angle = math.radians(0.5)
sun.rotation_euler[0] = math.radians(48)
sun.rotation_euler[2] = math.radians(215)

# ═══════════════════════════════════════════════════════════════════════════════
# RENDER SETTINGS
# ═══════════════════════════════════════════════════════════════════════════════
sc = bpy.context.scene
sc.render.engine = "CYCLES"
sc.render.resolution_x = 1920
sc.render.resolution_y = 1080
sc.render.image_settings.file_format = "PNG"
sc.cycles.samples = 256
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = "OPTIX"
except Exception:
    try:
        sc.cycles.denoiser = "OPENIMAGEDENOISE"
    except:
        pass
sc.cycles.device = "GPU"

# AgX view transform for photo-real tone mapping
try:
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = -2.2
    sc.view_settings.gamma = 1.0
except Exception as _e:
    print(f"[all8] AgX: {_e}")


# ═══════════════════════════════════════════════════════════════════════════════
# CAMERAS
# ═══════════════════════════════════════════════════════════════════════════════
def make_camera(name, loc, target, fov_deg=58):
    bpy.ops.object.camera_add(location=loc)
    cam = bpy.context.active_object
    cam.name = name
    cam.data.name = name
    cam.data.lens_unit = "FOV"
    cam.data.angle = math.radians(fov_deg)
    dir_vec = Vector(target) - Vector(loc)
    if dir_vec.length > 0:
        rot_q = dir_vec.to_track_quat("-Z", "Y")
        cam.rotation_euler = rot_q.to_euler()
    return cam


cam_ov = make_camera("cam_overview", loc=(0, -80, 110), target=(0, 12, 0), fov_deg=62)
cam_rs = make_camera("cam_residential", loc=(-18, 8, 14), target=(2, 38, 0), fov_deg=60)
cam_pk = make_camera("cam_park", loc=(-12, 36, 22), target=(34, 28, 2), fov_deg=62)
cam_cm = make_camera(
    "cam_commercial", loc=(-18, -8, 14), target=(2, -32, 0), fov_deg=60
)
cam_ix = make_camera(
    "cam_intersection", loc=(-22, -22, 20), target=(0, 0, 0), fov_deg=58
)

# ═══════════════════════════════════════════════════════════════════════════════
# SAVE BLEND
# ═══════════════════════════════════════════════════════════════════════════════
blend_path = str(OUT / "urban_v3_all30.blend")
if os.environ.get("C2W_SKIP_INTERMEDIATE_SAVES") != "1":
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"[all8] Blend saved: {blend_path}")
else:
    print("[full02] Intermediate all30 save skipped; scene remains in memory.")

# ═══════════════════════════════════════════════════════════════════════════════
# RENDER ALL 5 CAMERAS
# ═══════════════════════════════════════════════════════════════════════════════
cameras = [
    (cam_ov, "overview.png"),
    (cam_rs, "residential.png"),
    (cam_pk, "park.png"),
    (cam_cm, "commercial.png"),
    (cam_ix, "intersection.png"),
]

if os.environ.get("C2W_SKIP_LEGACY_RENDERS") != "1":
    for cam, fname in cameras:
        sc.camera = cam
        sc.render.filepath = str(OUT / fname)
        print(f"[all8] Rendering {fname} ...")
        bpy.ops.render.render(write_still=True)
        print(f"[all8] Done: {fname}")

print(
    "[all8] Legacy renders skipped."
    if os.environ.get("C2W_SKIP_LEGACY_RENDERS") == "1"
    else "[all8] All renders complete."
)

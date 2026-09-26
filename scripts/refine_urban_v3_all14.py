"""
refine_urban_v3_all14.py
=========================
Refine urban_v3_all13 into urban_v3_all14.

Strict vegetation goals:
  - All tree positions use complex all8 TreeFactory meshes as linked instances.
  - Each tree instance has explicit procedural leaf geometry.
  - Roadside green belts / flowerbeds use belt4-style shrub meshes plus the
    high-density Infinigen Flowerplant / GrassTuft scatter already generated in all13.

Output:
  ${WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all14/
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


import math
import re
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

SRC_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all13/urban_v3_all13.blend"
)
BELT4_BLEND = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_belt4/belt4.blend"
)
OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all14")
OUT.mkdir(parents=True, exist_ok=True)

print("[all14] Opening all13 base blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print("[all14] Base loaded", flush=True)


def get_coll(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_to_coll(obj, coll):
    try:
        coll.objects.link(obj)
    except RuntimeError:
        pass
    return obj


def remove_object(obj):
    bpy.data.objects.remove(obj, do_unlink=True)


def strip_suffix(name):
    return re.sub(r"\.\d+$", "", name)


def remove_lightweight_vegetation():
    """Remove all13 lightweight shrubs/road trees before replacing them."""
    remove_prefixes = (
        "lrt_",  # all13 roadside ProcShrub tree replacements
        "fb_",  # all13 generated belt shrub stems/leaves
        "pfb",  # all13 generated park flowerbed shrubs
        "ysh",  # all13 residential yard shrubs
    )
    removed = 0
    for obj in list(bpy.data.objects):
        base = strip_suffix(obj.name)
        if not base.startswith(remove_prefixes):
            continue
        if base.endswith(("_b", "_l", "_bark", "_leaf", "_trunk", "_leaf0", "_leaf1")):
            remove_object(obj)
            removed += 1
    print(f"[all14] Removed lightweight shrub/tree objects: {removed}", flush=True)


def ensure_leaf_material():
    mat = bpy.data.materials.get("a14_tree_leaf_complex")
    if mat:
        return mat
    mat = bpy.data.materials.new("a14_tree_leaf_complex")
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
    noise.inputs["Scale"].default_value = 11.0
    noise.inputs["Detail"].default_value = 7.0
    ramp.color_ramp.elements[0].color = (0.030, 0.120, 0.018, 1.0)
    ramp.color_ramp.elements[1].color = (0.180, 0.360, 0.070, 1.0)
    ramp.color_ramp.elements[1].position = 0.78
    bsdf.inputs["Roughness"].default_value = 0.68
    mix_s.inputs["Fac"].default_value = 0.24
    nt.links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    nt.links.new(ramp.outputs["Color"], trans.inputs["Color"])
    nt.links.new(trans.outputs["BSDF"], mix_s.inputs[1])
    nt.links.new(bsdf.outputs["BSDF"], mix_s.inputs[2])
    nt.links.new(mix_s.outputs["Shader"], out.inputs["Surface"])
    return mat


def norm(v):
    vec = Vector(v)
    length = vec.length
    return vec / length if length > 1e-8 else Vector((0, 0, 1))


def add_leaf(verts, faces, center, tangent, bitangent, length, width):
    c = Vector(center)
    t = norm(tangent)
    b = norm(bitangent)
    tip = c + t * length * 0.60
    rs = c + t * length * 0.08 + b * width * 0.50
    rb = c - t * length * 0.32 + b * width * 0.18
    base = c - t * length * 0.40
    lb = c - t * length * 0.32 - b * width * 0.18
    ls = c + t * length * 0.08 - b * width * 0.50
    i = len(verts)
    verts.extend([tuple(tip), tuple(rs), tuple(rb), tuple(base), tuple(lb), tuple(ls)])
    faces.extend(
        [
            (i, i + 1, i + 5),
            (i + 1, i + 2, i + 5),
            (i + 2, i + 4, i + 5),
            (i + 2, i + 3, i + 4),
        ]
    )


def add_leaf_crown(tag, loc, dims, coll, seed=0):
    rng = np.random.default_rng(seed)
    mat = ensure_leaf_material()
    rx = max(0.9, dims[0] * 0.48)
    ry = max(0.9, dims[1] * 0.48)
    rz = max(0.8, dims[2] * 0.27)
    cx, cy = loc[0], loc[1]
    cz = loc[2] + dims[2] * 0.72
    verts, faces = [], []
    n_leaves = int(max(850, min(1700, rx * ry * rz * 145)))
    for _ in range(n_leaves):
        for _try in range(16):
            px, py, pz = rng.uniform(-1, 1, 3)
            if px * px + py * py + pz * pz <= 1.0:
                break
        center = Vector((cx + px * rx, cy + py * ry, cz + pz * rz))
        outward = norm((px / rx, py / ry, pz / rz + 0.22))
        tangent = norm(
            outward * 0.55
            + Vector((rng.uniform(-0.3, 0.3), rng.uniform(-0.3, 0.3), 0.78))
        )
        cross_src = norm(
            (rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-0.25, 0.25))
        )
        bitangent = tangent.cross(cross_src)
        if bitangent.length < 1e-5:
            bitangent = Vector((1, 0, 0))
        add_leaf(
            verts,
            faces,
            center,
            tangent,
            bitangent,
            rng.uniform(0.18, 0.38) * max(0.70, min(1.30, dims[2] / 7.0)),
            rng.uniform(0.065, 0.135) * max(0.70, min(1.30, dims[2] / 7.0)),
        )
    mesh = bpy.data.meshes.new(tag + "_leaf_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    for poly in mesh.polygons:
        poly.use_smooth = True
    obj = bpy.data.objects.new(tag + "_leaf_complex", mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(mat)
    link_to_coll(obj, coll)
    return obj


def all8_tree_templates():
    roots = [
        o
        for o in bpy.data.objects
        if o.name.startswith("all8veg_TreeFactory(")
        and "_explicit_leaf_cloud" not in o.name
        and o.type == "MESH"
    ]
    roots.sort(key=lambda o: o.name)
    if not roots:
        raise RuntimeError("No all8 TreeFactory roots found in the all13 base blend")
    print(f"[all14] All8 TreeFactory templates available: {len(roots)}", flush=True)
    return roots


def place_all8_tree(tag, template, loc, coll, scale=0.5, yaw=0.0, seed=0):
    obj = template.copy()
    obj.data = template.data
    obj.animation_data_clear()
    obj.name = tag + "_all8_tree"
    obj.location = loc
    obj.rotation_euler.z = yaw
    obj.scale = (scale, scale, scale)
    bpy.context.collection.objects.link(obj)
    link_to_coll(obj, coll)
    dims = (
        template.dimensions.x * scale,
        template.dimensions.y * scale,
        template.dimensions.z * scale,
    )
    add_leaf_crown(tag, loc, dims, coll, seed=seed)
    return obj


def road_and_yard_tree_positions():
    R = 4.5
    SW = 3.5
    FW = 2.5
    S1 = R + SW
    pts = []
    for i, y in enumerate([13, 22, 31, 40, 49, -13, -22, -31, -40, -49]):
        pts.append((f"lrt_e_{i}", (S1 + FW * 0.50, y, 0.10), 0.42))
        pts.append((f"lrt_w_{i}", (-S1 - FW * 0.50, y, 0.10), 0.42))
    for i, x in enumerate([13, 22, 31, 40, 49, -13, -22, -31, -40, -49]):
        pts.append((f"lrt_n_{i}", (x, S1 + FW * 0.50, 0.10), 0.42))
        pts.append((f"lrt_s_{i}", (x, -S1 - FW * 0.50, 0.10), 0.42))
    for i, loc in enumerate(
        [
            (-20, 20, 0.08),
            (-22, 45, 0.08),
            (-38, 20, 0.08),
            (-36, 48, 0.08),
            (-48, 32, 0.08),
        ]
    ):
        pts.append((f"res_complex_tree_{i}", loc, 0.36))
    return pts


def belt_rects():
    R = 4.5
    SW = 3.5
    FW = 2.5
    S1 = R + SW
    G1 = S1 + FW
    ARM = 50.0
    rects = []

    def ns(tag, x_inner, side, y0, y1):
        if y1 <= y0:
            return
        fw2 = FW / 2.0
        cx = x_inner + (fw2 if side == "e" else -fw2)
        cy = (y0 + y1) / 2.0
        rects.append((tag, cx, cy, FW, y1 - y0))

    def ew(tag, y_inner, side, x0, x1):
        if x1 <= x0:
            return
        fw2 = FW / 2.0
        cy = y_inner + (fw2 if side == "n" else -fw2)
        cx = (x0 + x1) / 2.0
        rects.append((tag, cx, cy, x1 - x0, FW))

    ns("fb_ne1", S1, "e", R, 11.0)
    ns("fb_ne2", S1, "e", 15.5, R + ARM)
    ns("fb_nw1", -S1, "w", R, R + ARM)
    ns("fb_se1", S1, "e", -(R + ARM), -R)
    ns("fb_sw1", -S1, "w", -(R + ARM), -R)
    ew("fb_en1", S1, "n", R, 12.0)
    ew("fb_en2", S1, "n", 17.0, R + ARM)
    ew("fb_es1", -S1, "s", R, R + ARM)
    ew("fb_wn1", S1, "n", -(R + ARM), -R)
    ew("fb_ws1", -S1, "s", -(R + ARM), -R)
    rects.extend(
        [
            ("pfb1", 45, 16, 5, 3),
            ("pfb2", 50, 42, 5, 3),
            ("pfb3", 20, 44, 4, 2.5),
        ]
    )
    return rects


def load_belt4_shrub_templates(proto_coll):
    if not BELT4_BLEND.exists():
        raise RuntimeError(f"Missing belt4 blend: {BELT4_BLEND}")
    with bpy.data.libraries.load(str(BELT4_BLEND), link=False) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith("Shrub_")]
    for obj in dst.objects:
        if obj is None:
            continue
        link_to_coll(obj, proto_coll)
        obj.hide_viewport = True
        obj.hide_render = True
    pairs = []
    for i in range(24):
        bark = bpy.data.objects.get(f"Shrub_{i}_bark")
        leaf = bpy.data.objects.get(f"Shrub_{i}_leaf")
        if bark and leaf:
            pairs.append((bark, leaf))
    if not pairs:
        raise RuntimeError("No belt4 shrub bark/leaf pairs loaded")
    print(f"[all14] Belt4 shrub template pairs loaded: {len(pairs)}", flush=True)
    return pairs


def place_belt4_shrub(tag, pair, loc, coll, scale=1.0, yaw=0.0):
    bark_src, leaf_src = pair
    bark = bark_src.copy()
    bark.data = bark_src.data
    bark.animation_data_clear()
    bark.name = tag + "_belt4_bark"
    bark.location = loc
    bark.rotation_euler.z = yaw
    bark.scale = (scale, scale, scale)
    bpy.context.collection.objects.link(bark)
    link_to_coll(bark, coll)

    leaf = leaf_src.copy()
    leaf.data = leaf_src.data
    leaf.animation_data_clear()
    leaf.name = tag + "_belt4_leaf"
    leaf.parent = bark
    leaf.location = (0, 0, 0)
    leaf.rotation_euler = (0, 0, 0)
    leaf.scale = (1, 1, 1)
    leaf.matrix_parent_inverse.identity()
    bpy.context.collection.objects.link(leaf)
    link_to_coll(leaf, coll)
    return bark, leaf


def populate_belt4_shrubs(pairs, coll):
    rng = np.random.default_rng(14014)
    count = 0
    for tag, cx, cy, dx, dy in belt_rects():
        nx = max(1, int(dx / 2.3))
        ny = max(1, int(dy / 2.3))
        # Keep very long narrow belts as one dense row, matching belt4's curb strip feel.
        if dx < 3.0:
            nx = 1
        if dy < 3.0:
            ny = 1
        for ix in range(nx):
            for iy in range(ny):
                x = cx - dx / 2 + (ix + 0.5) * dx / nx + rng.uniform(-0.35, 0.35)
                y = cy - dy / 2 + (iy + 0.5) * dy / ny + rng.uniform(-0.35, 0.35)
                pair = pairs[count % len(pairs)]
                scale = float(rng.uniform(0.82, 1.22))
                place_belt4_shrub(
                    f"{tag}_{count:03d}",
                    pair,
                    (x, y, 0.10),
                    coll,
                    scale=scale,
                    yaw=float(rng.uniform(0, math.tau)),
                )
                count += 1
    print(
        f"[all14] Belt4-style shrub instances placed in belts/flowerbeds: {count}",
        flush=True,
    )


def ensure_cycles_color_render():
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 900
    scene.render.image_settings.file_format = "PNG"
    scene.cycles.samples = 192
    scene.cycles.use_denoising = True
    try:
        scene.cycles.device = "GPU"
    except Exception:
        pass
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.exposure = -0.3
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


remove_lightweight_vegetation()

tree_coll = get_coll("All14_All8ComplexTrees")
belt_coll = get_coll("All14_Belt4GreenBelts")
proto_coll = get_coll("All14_Belt4Prototypes")

templates = all8_tree_templates()
for idx, (tag, loc, scale) in enumerate(road_and_yard_tree_positions()):
    template = templates[idx % len(templates)]
    place_all8_tree(
        tag,
        template,
        loc,
        tree_coll,
        scale=scale,
        yaw=float((idx * 0.73) % math.tau),
        seed=14000 + idx,
    )
print(
    f"[all14] All8 TreeFactory instances placed for roadside/yard trees: {len(road_and_yard_tree_positions())}",
    flush=True,
)

pairs = load_belt4_shrub_templates(proto_coll)
populate_belt4_shrubs(pairs, belt_coll)

ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all14.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all14] Blend saved: {out_blend}", flush=True)

cameras = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
scene = bpy.context.scene
for cam_name, filename in cameras:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(f"[all14] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all14] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all14] Done: {filename}", flush=True)

print("[all14] All complete.", flush=True)

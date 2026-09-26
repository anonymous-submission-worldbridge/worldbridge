"""
urban_v3_all39_fast4 — refined residential version generated from the all34 urban
scene + the infinigen house import pipeline.

  1. Residential ground uses marble paving with physical dark seams.
  2. House roof is rebuilt with a small eave and grey-blue/qingwa tile material.
  3. Facade gets visible wood door, wood window frames, glass panes, trim and
     hardware.
  4. A closed cut-stone + black wrought-iron fence surrounds the house, matching
     the urban_v3_fence3 iron style.
  5. Renders exterior views plus two interior views, with the window view square
     to the front window.

Base = all34 (urban scene, no house); the house is re-imported and improved.
This script does not read urban_v3_all37/all38 blend outputs.
Compared with all39, the base vegetation is rebuilt as a clean TreeFactory
prototype library plus collection instances. fast4 keeps the full-detail visible
TreeFactory bark meshes and creates explicit linked LeafFactory leaf instances
inside each mother-tree prototype, because the original Tree.xxx leaf-child node
objects evaluate to empty geometry in this pipeline.
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


from pathlib import Path
import math
import random
import re
import sys

import bpy
import bmesh
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all34/urban_v3_all34.blend"
HOUSE_BLEND = ROOT / "infinigen/outputs/indoor2/coarse/scene.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all39_fast4"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))

TARGET_FRONT_X = -10.5
TARGET_CY = 31.0
NEW_SCALE = 0.826 * math.sqrt(2.0)  # doubled footprint (as in all36)
WANT = lambda c: (
    c == "unique_assets" or c == "skirting" or c.startswith("door_base_elements")
)

print(f"[all39_fast4] Opening {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all39_fast4] GPU OPTIX", flush=True)
except Exception as e:
    print("[all39_fast4] gpu", e, flush=True)


# ─── compact instanced vegetation from the all34 base ─────────────────────────
def _base_name(name):
    return re.sub(r"\.\d+$", "", name)


def _faces(objs):
    return sum(
        len(o.data.polygons)
        for o in objs
        if getattr(o, "type", None) == "MESH" and o.data
    )


def _safe_height(obj):
    return max(float(obj.dimensions.z), 0.01)


def _bbox_world(objs):
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    found = False
    for o in objs:
        if o.type != "MESH":
            continue
        found = True
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            mn.x = min(mn.x, w.x)
            mn.y = min(mn.y, w.y)
            mn.z = min(mn.z, w.z)
            mx.x = max(mx.x, w.x)
            mx.y = max(mx.y, w.y)
            mx.z = max(mx.z, w.z)
    return (mn, mx) if found else (Vector((0, 0, 0)), Vector((0, 0, 0)))


def _get_target_collection(name):
    return bpy.data.collections.get(name) or bpy.context.scene.collection


def _new_collection_instance(name, proto_coll, target_coll, loc, yaw=0.0, scale=1.0):
    inst = bpy.data.objects.new(name, None)
    inst.empty_display_type = "PLAIN_AXES"
    inst.empty_display_size = 0.25
    inst.instance_type = "COLLECTION"
    inst.instance_collection = proto_coll
    inst.location = loc
    inst.rotation_euler.z = yaw
    inst.scale = (scale, scale, scale)
    target_coll.objects.link(inst)
    return inst


def _tree_roots():
    return [
        o
        for o in bpy.data.objects
        if o.type == "MESH"
        and o.name.startswith("TreeFactory(")
        and any(c.name == "Park" for c in o.users_collection)
        and not o.hide_render
    ]


def _protect_leaf_assets():
    for coll in bpy.data.collections:
        if "LeafFactory" in coll.name:
            coll.use_fake_user = True
    for obj in bpy.data.objects:
        if obj.name.startswith("LeafFactory"):
            obj.use_fake_user = True
            if obj.data:
                obj.data.use_fake_user = True
                for mat in obj.data.materials:
                    if mat:
                        mat.use_fake_user = True
    for group in bpy.data.node_groups:
        if group.name.startswith(("add_tree_children", "CollectionDistribute")):
            group.use_fake_user = True


def _local_bbox_mesh(mesh):
    mn = Vector((1e18, 1e18, 1e18))
    mx = Vector((-1e18, -1e18, -1e18))
    for v in mesh.vertices:
        co = v.co
        mn.x = min(mn.x, co.x)
        mn.y = min(mn.y, co.y)
        mn.z = min(mn.z, co.z)
        mx.x = max(mx.x, co.x)
        mx.y = max(mx.y, co.y)
        mx.z = max(mx.z, co.z)
    return mn, mx


def _tree_factory_id(obj):
    m = re.search(r"TreeFactory\((\d+)\)", obj.name)
    return m.group(1) if m else ""


def _leaf_assets_for_tree(root):
    tree_id = _tree_factory_id(root)
    assets = [
        o
        for o in bpy.data.objects
        if o.type == "MESH" and o.name.startswith("LeafFactory") and o.data
    ]
    exact = [o for o in assets if tree_id and f"({tree_id})" in o.name]
    if exact:
        return sorted(exact, key=lambda o: o.name)
    broadleaf = [o for o in assets if "Broadleaf" in o.name]
    return sorted(broadleaf or assets, key=lambda o: o.name)


def _sample_canopy_points(root, count, rng):
    mn, mx = _local_bbox_mesh(root.data)
    dims = mx - mn
    height = max(dims.z, 0.01)
    center = Vector(((mn.x + mx.x) * 0.5, (mn.y + mx.y) * 0.5, 0.0))
    radius = max(dims.x, dims.y, 0.01) * 0.5
    verts = root.data.vertices
    step = max(1, len(verts) // 32000)
    candidates = []
    for vi in range(0, len(verts), step):
        co = verts[vi].co
        zn = (co.z - mn.z) / height
        radial = math.hypot(co.x - center.x, co.y - center.y) / radius
        if zn < 0.34:
            continue
        if zn < 0.58 and radial < 0.24:
            continue
        noise = 0.5 + 0.5 * math.sin((vi + 1) * 12.9898 + count * 78.233)
        score = zn * 0.58 + min(radial, 1.45) * 0.52 + noise * 0.16
        candidates.append((score, co.copy(), zn, radial))
    if not candidates:
        return []
    candidates.sort(key=lambda item: item[0], reverse=True)
    pool = candidates[: min(len(candidates), max(count * 8, count))]
    rng.shuffle(pool)
    return pool[:count]


def _create_visible_leaf_canopy(root, coll, idx):
    assets = _leaf_assets_for_tree(root)
    if not assets:
        return []
    mn, mx = _local_bbox_mesh(root.data)
    dims = mx - mn
    height = max(dims.z, 0.01)
    crown_width = max(dims.x, dims.y, 0.01)
    leaf_count = int(max(150, min(390, 24.0 * (dims.x + dims.y) + 12.0 * height)))
    rng = random.Random(39017 + idx * 7919)
    points = _sample_canopy_points(root, leaf_count, rng)
    center = Vector(((mn.x + mx.x) * 0.5, (mn.y + mx.y) * 0.5, 0.0))
    leaves = []
    for leaf_idx, (_, co, zn, radial) in enumerate(points):
        src = assets[(leaf_idx * 7 + idx * 3) % len(assets)]
        leaf = bpy.data.objects.new(
            f"all39_fast4_tree_mother_{idx:02d}_leaf_{leaf_idx:03d}", src.data
        )
        outward = Vector((co.x - center.x, co.y - center.y, 0.0))
        if outward.length < 1e-4:
            yaw = rng.random() * math.tau
            outward = Vector((math.cos(yaw), math.sin(yaw), 0.0))
        else:
            outward.normalize()
            yaw = math.atan2(outward.y, outward.x) - math.pi * 0.5
        jitter = Vector(
            (
                (rng.random() - 0.5) * 0.34 * crown_width,
                (rng.random() - 0.5) * 0.34 * crown_width,
                (rng.random() - 0.45) * 0.38 * height,
            )
        )
        if zn < 0.64:
            jitter.z += 0.10 * height
        leaf.location = co + outward * (0.05 + 0.22 * rng.random()) + jitter
        leaf.rotation_euler = (
            rng.uniform(-0.95, 0.95),
            rng.uniform(-0.45, 0.45),
            yaw + rng.uniform(-0.95, 0.95),
        )
        scale = rng.uniform(0.42, 0.86) * (0.86 + 0.20 * min(radial, 1.0))
        leaf.scale = (scale, scale, scale)
        leaf.hide_viewport = False
        leaf.hide_render = False
        leaf.use_fake_user = True
        coll.objects.link(leaf)
        leaves.append(leaf)
    return leaves


def _make_tree_prototype(root, idx):
    coll = bpy.data.collections.new(f"All39Fast4_TreePrototype_{idx:02d}")
    proto = root.copy()
    proto.data = root.data
    proto.animation_data_clear()
    proto.name = f"all39_fast4_tree_mother_{idx:02d}"
    proto.location = (0, 0, 0)
    proto.rotation_euler = root.rotation_euler
    proto.scale = root.scale
    coll.objects.link(proto)
    visible_leaves = _create_visible_leaf_canopy(root, coll, idx)
    return coll, _safe_height(root), proto, visible_leaves


def _find_shrub_pairs():
    prefixes = ("fb_", "pfb", "pk_", "et_", "nt_", "st_", "wt_")
    groups = {}
    for o in bpy.data.objects:
        if o.type != "MESH":
            continue
        base = _base_name(o.name)
        if not base.startswith(prefixes) or base.endswith("_g"):
            continue
        m = re.match(r"(.+)_(bark|leaf)$", base)
        if not m:
            continue
        groups.setdefault(m.group(1), {})[m.group(2)] = o
    pairs = []
    for key, parts in groups.items():
        if "bark" in parts and "leaf" in parts:
            pairs.append((key, parts["bark"], parts["leaf"]))
    pairs.sort(key=lambda item: (item[1].location.x, item[1].location.y, item[0]))
    return pairs


def _make_shrub_prototype(key, bark, leaf, idx):
    coll = bpy.data.collections.new(f"All39Fast4_ShrubPrototype_{idx:02d}")
    anchor = bark.location.copy()
    proto_objs = []
    for src, suffix in ((bark, "bark"), (leaf, "leaf")):
        proto = src.copy()
        proto.data = src.data
        proto.animation_data_clear()
        proto.name = f"all39_fast4_shrub_mother_{idx:02d}_{suffix}"
        proto.location = src.location - anchor
        proto.rotation_euler = src.rotation_euler
        proto.scale = src.scale
        coll.objects.link(proto)
        proto_objs.append(proto)
    mn, mx = _bbox_world([bark, leaf])
    return coll, max(mx.z - mn.z, 0.01), proto_objs


def _purge_factory_asset_collections():
    for obj in list(bpy.data.objects):
        if obj.name.startswith("GenericTreeFactory("):
            bpy.data.objects.remove(obj, do_unlink=True)
    for coll in list(bpy.data.collections):
        if coll.name.startswith("assets:GenericTreeFactory") and len(coll.objects) == 0:
            bpy.data.collections.remove(coll)


def optimize_existing_vegetation():
    _protect_leaf_assets()
    tree_roots = _tree_roots()
    shrub_pairs = _find_shrub_pairs()
    before_faces = _faces(tree_roots) + _faces(
        [o for _, b, l in shrub_pairs for o in (b, l)]
    )
    before_meshes = len({o.data.name for o in tree_roots if o.data}) + len(
        {o.data.name for _, b, l in shrub_pairs for o in (b, l) if o.data}
    )

    park_coll = _get_target_collection("Park")
    if tree_roots:
        tree_specs = sorted(
            tree_roots, key=lambda o: len(o.data.polygons), reverse=True
        )
        mother_count = min(9, len(tree_specs))
        mothers = tree_specs[:mother_count]
        tree_protos = [_make_tree_prototype(root, i) for i, root in enumerate(mothers)]
        for idx, root in enumerate(tree_roots):
            proto_idx = (
                mothers.index(root) if root in mothers else idx % len(tree_protos)
            )
            _, proto_height, _, _ = tree_protos[proto_idx]
            base_scale = _safe_height(root) / proto_height
            scale_jitter = 0.985 + 0.0075 * ((idx * 7) % 5)
            scale = max(0.62, min(1.42, base_scale * scale_jitter))
            yaw = (idx * 0.071) % (math.tau)
            _new_collection_instance(
                f"all39_fast4_tree_inst_{idx:03d}",
                tree_protos[proto_idx][0],
                park_coll,
                root.location.copy(),
                yaw=yaw,
                scale=scale,
            )
        for root in tree_roots:
            for child in list(root.children):
                bpy.data.objects.remove(child, do_unlink=True)
            bpy.data.objects.remove(root, do_unlink=True)

    if shrub_pairs:
        mother_pairs = sorted(
            shrub_pairs,
            key=lambda item: _faces([item[1], item[2]]),
            reverse=True,
        )[: min(10, len(shrub_pairs))]
        shrub_protos = [
            _make_shrub_prototype(key, bark, leaf, i)
            for i, (key, bark, leaf) in enumerate(mother_pairs)
        ]
        for idx, (key, bark, leaf) in enumerate(shrub_pairs):
            proto_coll, proto_height, _ = shrub_protos[idx % len(shrub_protos)]
            mn, mx = _bbox_world([bark, leaf])
            base_scale = max(mx.z - mn.z, 0.01) / proto_height
            scale_jitter = 0.88 + 0.04 * ((idx * 11) % 7)
            scale = max(0.55, min(1.55, base_scale * scale_jitter))
            yaw = (idx * 1.61803398875) % (math.tau)
            target_coll = (
                bark.users_collection[0]
                if bark.users_collection
                else bpy.context.scene.collection
            )
            _new_collection_instance(
                f"all39_fast4_shrub_inst_{idx:03d}",
                proto_coll,
                target_coll,
                bark.location.copy(),
                yaw=yaw,
                scale=scale,
            )
        for _, bark, leaf in shrub_pairs:
            bpy.data.objects.remove(bark, do_unlink=True)
            bpy.data.objects.remove(leaf, do_unlink=True)

    _purge_factory_asset_collections()
    _protect_leaf_assets()
    try:
        bpy.ops.outliner.orphans_purge(
            do_local_ids=True, do_linked_ids=True, do_recursive=True
        )
    except TypeError:
        bpy.ops.outliner.orphans_purge(do_recursive=True)

    proto_meshes = {
        o.data.name
        for o in bpy.data.objects
        if o.type == "MESH"
        and (
            o.name.startswith("all39_fast4_tree_mother_")
            or o.name.startswith("all39_fast4_shrub_mother_")
        )
        and o.data
    }
    visible_leaves = [
        o
        for o in bpy.data.objects
        if o.name.startswith("all39_fast4_tree_mother_") and "_leaf_" in o.name
    ]
    leaf_assets = [o for o in bpy.data.objects if o.name.startswith("LeafFactory")]
    print(
        f"[all39_fast4] vegetation instanced: trees {len(tree_roots)} -> "
        f"{min(9, len(tree_roots))} full-detail TreeFactory mothers; shrubs {len(shrub_pairs)} -> "
        f"{min(10, len(shrub_pairs))} mothers; source faces {before_faces:,}; "
        f"source meshes {before_meshes} -> prototype meshes {len(proto_meshes)}; "
        f"visible linked leaves {len(visible_leaves)}; LeafFactory assets kept {len(leaf_assets)}",
        flush=True,
    )


optimize_existing_vegetation()


# ─── materials ────────────────────────────────────────────────────────────────
def _clear(n):
    m = bpy.data.materials.new(n)
    m.use_nodes = True
    for x in list(m.node_tree.nodes):
        m.node_tree.nodes.remove(x)
    return m


def _set(b, k, v):
    if k in b.inputs:
        b.inputs[k].default_value = v


def facade_mat():
    m = _clear("a39_facade")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    big = nd.new("ShaderNodeTexNoise")
    big.inputs["Scale"].default_value = 1.4
    lk.new(tex.outputs["Object"], big.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.52, 0.47, 0.40, 1.0)
    r.color_ramp.elements[1].color = (0.66, 0.61, 0.52, 1.0)
    lk.new(big.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.85)
    fn = nd.new("ShaderNodeTexNoise")
    fn.inputs["Scale"].default_value = 42.0
    fn.inputs["Detail"].default_value = 12.0
    lk.new(tex.outputs["Object"], fn.inputs["Vector"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.2
    lk.new(fn.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def tile_roof_mat():
    m = _clear("a39_roof_qingwa_grayblue")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    brick = nd.new("ShaderNodeTexBrick")
    brick.inputs["Color1"].default_value = (0.18, 0.27, 0.32, 1.0)
    brick.inputs["Color2"].default_value = (0.30, 0.40, 0.46, 1.0)
    brick.inputs["Mortar"].default_value = (0.065, 0.09, 0.105, 1.0)
    brick.inputs["Scale"].default_value = 1.05
    brick.inputs["Mortar Size"].default_value = 0.034
    if "Brick Width" in brick.inputs:
        brick.inputs["Brick Width"].default_value = 0.52
    if "Row Height" in brick.inputs:
        brick.inputs["Row Height"].default_value = 0.30
    lk.new(tex.outputs["Object"], brick.inputs["Vector"])
    lk.new(brick.outputs["Color"], b.inputs["Base Color"])
    _set(b, "Roughness", 0.68)
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.62
    bm.inputs["Distance"].default_value = 0.024
    lk.new(brick.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def glass_mat():
    m = _clear("a39_clear_window_glass")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (0.84, 0.93, 0.98, 0.42)
    _set(b, "Alpha", 0.42)
    _set(b, "Roughness", 0.012)
    _set(b, "Transmission Weight", 0.82)
    _set(b, "IOR", 1.45)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    m.blend_method = "BLEND"
    m.use_screen_refraction = True
    return m


def frame_mat():
    m = _clear("a39_window_frame_wood")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    w = nd.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    w.inputs["Scale"].default_value = 8.0
    w.inputs["Distortion"].default_value = 9.0
    lk.new(tex.outputs["Object"], w.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.10, 0.055, 0.028, 1.0)
    r.color_ramp.elements[1].color = (0.30, 0.17, 0.075, 1.0)
    lk.new(w.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.11
    bm.inputs["Distance"].default_value = 0.006
    lk.new(w.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.46)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def wood_mat():
    m = _clear("a39_oiled_wood_door")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    w = nd.new("ShaderNodeTexWave")
    w.wave_type = "RINGS"
    w.inputs["Scale"].default_value = 6.0
    w.inputs["Distortion"].default_value = 9.0
    lk.new(tex.outputs["Object"], w.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].color = (0.18, 0.085, 0.035, 1.0)
    r.color_ramp.elements[1].color = (0.42, 0.22, 0.095, 1.0)
    lk.new(w.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.13
    bm.inputs["Distance"].default_value = 0.007
    lk.new(w.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.48)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


MAT_FACADE = facade_mat()
MAT_TILE = tile_roof_mat()
MAT_GLASS = glass_mat()
MAT_FRAME = frame_mat()
MAT_WOOD = wood_mat()


def principled_mat(name, color, roughness=0.6, metallic=0.0):
    m = _clear(name)
    nt = m.node_tree
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = color
    _set(b, "Roughness", roughness)
    _set(b, "Metallic", metallic)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


def marble_mat():
    m = _clear("a39_marble_paving")
    nt = m.node_tree
    nd, lk = nt.nodes, nt.links
    out = nd.new("ShaderNodeOutputMaterial")
    b = nd.new("ShaderNodeBsdfPrincipled")
    tex = nd.new("ShaderNodeTexCoord")
    noise = nd.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 14.0
    noise.inputs["Roughness"].default_value = 0.58
    lk.new(tex.outputs["Object"], noise.inputs["Vector"])
    r = nd.new("ShaderNodeValToRGB")
    r.color_ramp.elements[0].position = 0.16
    r.color_ramp.elements[0].color = (0.62, 0.64, 0.64, 1.0)
    vein = r.color_ramp.elements.new(0.47)
    vein.color = (0.36, 0.39, 0.40, 1.0)
    r.color_ramp.elements[1].color = (0.91, 0.92, 0.89, 1.0)
    lk.new(noise.outputs["Fac"], r.inputs["Fac"])
    lk.new(r.outputs["Color"], b.inputs["Base Color"])
    bm = nd.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = 0.055
    bm.inputs["Distance"].default_value = 0.012
    lk.new(noise.outputs["Fac"], bm.inputs["Height"])
    lk.new(bm.outputs["Normal"], b.inputs["Normal"])
    _set(b, "Roughness", 0.34)
    lk.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m


MAT_ROOF_FASCIA = principled_mat(
    "a39_roof_fascia_bluegray", (0.105, 0.155, 0.18, 1.0), roughness=0.72
)
MAT_DARK = principled_mat(
    "a39_dark_hardware", (0.035, 0.032, 0.028, 1.0), roughness=0.42, metallic=0.30
)
MAT_MARBLE = marble_mat()
MAT_SEAM = principled_mat(
    "a39_dark_marble_seam", (0.075, 0.080, 0.078, 1.0), roughness=0.78
)
MAT_STONE = principled_mat(
    "a39_fence_cut_stone", (0.48, 0.47, 0.43, 1.0), roughness=0.86
)
MAT_CONCRETE = principled_mat(
    "a39_fence_concrete_cap", (0.58, 0.57, 0.53, 1.0), roughness=0.82
)
MAT_IRON = principled_mat(
    "a39_black_wrought_iron", (0.018, 0.019, 0.021, 1.0), roughness=0.38, metallic=0.72
)


def bevel(obj, width=0.006, segments=1):
    if width <= 0:
        return obj
    mod = obj.modifiers.new("a39_bevel", "BEVEL")
    mod.width = width
    mod.segments = segments
    mod.harden_normals = True
    obj.modifiers.new("a39_weighted_normal", "WEIGHTED_NORMAL")
    return obj


def box(name, cx, cy, cz, dx, dy, dz, mat, coll, bevel_width=0.006):
    hx, hy, hz = dx / 2, dy / 2, dz / 2
    verts = [
        (cx - hx, cy - hy, cz - hz),
        (cx + hx, cy - hy, cz - hz),
        (cx + hx, cy + hy, cz - hz),
        (cx - hx, cy + hy, cz - hz),
        (cx - hx, cy - hy, cz + hz),
        (cx + hx, cy - hy, cz + hz),
        (cx + hx, cy + hy, cz + hz),
        (cx - hx, cy + hy, cz + hz),
    ]
    faces = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (3, 7, 4, 0),
    ]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    if mat:
        o.data.materials.append(mat)
    bevel(o, bevel_width)
    coll.objects.link(o)
    return o


def cylinder(
    name, loc, radius, depth, mat, coll, vertices=24, rot=(0, 0, 0), bevel_width=0
):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=loc, rotation=rot
    )
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    bevel(o, bevel_width)
    coll.objects.link(o)
    for c in list(o.users_collection):
        if c is not coll:
            c.objects.unlink(o)
    return o


def pyramid(name, loc, base, height, mat, coll, rot=(0, 0, math.radians(45))):
    z0 = loc[2] - height / 2
    z1 = loc[2] + height / 2
    pts = [
        Vector((base, 0, z0)),
        Vector((0, base, z0)),
        Vector((-base, 0, z0)),
        Vector((0, -base, z0)),
    ]
    rz = rot[2]
    cr, sr = math.cos(rz), math.sin(rz)
    verts = []
    for p in pts:
        x = loc[0] + p.x * cr - p.y * sr
        y = loc[1] + p.x * sr + p.y * cr
        verts.append((x, y, p.z))
    verts.append((loc[0], loc[1], z1))
    faces = [(0, 1, 2, 3), (0, 4, 1), (1, 4, 2), (2, 4, 3), (3, 4, 0)]
    mesh = bpy.data.meshes.new(f"{name}_mesh")
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    o = bpy.data.objects.new(name, mesh)
    if mat:
        o.data.materials.append(mat)
    coll.objects.link(o)
    return o


def torus(name, loc, major, minor, mat, coll, rot=(0, 0, 0)):
    bpy.ops.mesh.primitive_torus_add(
        major_radius=major,
        minor_radius=minor,
        major_segments=24,
        minor_segments=8,
        location=loc,
        rotation=rot,
    )
    o = bpy.context.active_object
    o.name = name
    if mat:
        o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    coll.objects.link(o)
    for c in list(o.users_collection):
        if c is not coll:
            c.objects.unlink(o)
    return o


def pt(axis, t, fixed):
    return (t, fixed) if axis == "X" else (fixed, t)


def dims(axis, length, thick, height):
    return (length, thick, height) if axis == "X" else (thick, length, height)


# ─── import house ─────────────────────────────────────────────────────────────
with bpy.data.libraries.load(str(HOUSE_BLEND), link=False) as (s, d):
    d.collections = [c for c in s.collections if WANT(c)]
house_objs = set()
for c in [c for c in d.collections if c]:
    for o in c.all_objects:
        house_objs.add(o)
print(f"[all39_fast4] imported {len(house_objs)} house objects", flush=True)
House = bpy.data.collections.new("House_indoor")
bpy.context.scene.collection.children.link(House)
for o in house_objs:
    try:
        House.objects.link(o)
    except RuntimeError:
        pass


def in_coll(o, sub):
    return any(sub in c.name for c in o.users_collection)


# facade + glass materials on the imported shell
for o in house_objs:
    if o.type != "MESH":
        continue
    if in_coll(o, "room_exterior"):
        if o.data.materials:
            for i in range(len(o.data.materials)):
                o.data.materials[i] = MAT_FACADE
        else:
            o.data.materials.append(MAT_FACADE)
    elif in_coll(o, "windows") or in_coll(o, "doors") or in_coll(o, "door_base"):
        for i, sl in enumerate(o.material_slots):
            nm = (sl.material.name if sl.material else "").lower()
            if "glass" in nm:
                o.data.materials[i] = MAT_GLASS
            elif any(k in nm for k in ("metal", "plastic", "galv", "brush")):
                o.data.materials[i] = MAT_FRAME


# ─── group + orient + scale + anchor ──────────────────────────────────────────
def cxyz(o):
    cs = [o.matrix_world @ Vector(c) for c in o.bound_box]
    return Vector(
        (sum(c.x for c in cs) / 8, sum(c.y for c in cs) / 8, sum(c.z for c in cs) / 8)
    )


def hbbox(objs):
    mn = [1e18] * 3
    mx = [-1e18] * 3
    for o in objs:
        if o.type != "MESH":
            continue
        for c in o.bound_box:
            w = o.matrix_world @ Vector(c)
            for i in range(3):
                mn[i] = min(mn[i], w[i])
                mx[i] = max(mx[i], w[i])
    return mn, mx


empty = bpy.data.objects.new("House_root", None)
bpy.context.scene.collection.objects.link(empty)
for o in house_objs:
    if o.parent is None or o.parent not in house_objs:
        o.parent = empty
        o.matrix_parent_inverse = empty.matrix_world.inverted()
bpy.context.view_layer.update()

mnA, mxA = hbbox(house_objs)
hcx, hcy = (mnA[0] + mxA[0]) / 2, (mnA[1] + mxA[1]) / 2
wins0 = [o for o in house_objs if o.type == "MESH" and in_coll(o, "windows")]
fv = Vector((0.0, 0.0))
for w in wins0:
    c = cxyz(w)
    fv += Vector((c.x - hcx, c.y - hcy))
rot_z = (
    round((-math.atan2(fv.y, fv.x)) / (math.pi / 2)) * (math.pi / 2)
    if (wins0 and fv.length > 0.3)
    else (0.0 if (mxA[0] - mnA[0]) >= (mxA[1] - mnA[1]) else math.pi / 2)
)
empty.rotation_euler.z = rot_z
empty.scale = (NEW_SCALE, NEW_SCALE, NEW_SCALE)
bpy.context.view_layer.update()
mn2, mx2 = hbbox(house_objs)
empty.location.x += TARGET_FRONT_X - mx2[0]
empty.location.y += TARGET_CY - (mn2[1] + mx2[1]) / 2
empty.location.z += 0.0 - mn2[2]
bpy.context.view_layer.update()
mn3, mx3 = hbbox(house_objs)
print(
    f"[all39_fast4] house X[{mn3[0]:.1f},{mx3[0]:.1f}] Y[{mn3[1]:.1f},{mx3[1]:.1f}] Z[{mn3[2]:.1f},{mx3[2]:.1f}]",
    flush=True,
)

# room_exterior bbox = wall shell for roof + facade features
ext = [o for o in house_objs if o.type == "MESH" and in_coll(o, "room_exterior")]
emn, emx = hbbox(ext) if ext else (mn3, mx3)


# ─── LOW HIP / PYRAMID TILE ROOF over the shell ───────────────────────────────
def build_hip_roof(emn, emx, mat, fascia_mat, coll, overhang=0.22, pitch_frac=0.13):
    x0, y0, x1, y1 = (
        emn[0] - overhang,
        emn[1] - overhang,
        emx[0] + overhang,
        emx[1] + overhang,
    )
    zt = emx[2] - 0.02
    W, D = x1 - x0, y1 - y0
    rise = pitch_frac * min(W, D)
    zr = zt + rise
    if W >= D:
        ins = D / 2.0
        yc = (y0 + y1) / 2.0
        verts = [
            (x0, y0, zt),
            (x1, y0, zt),
            (x1, y1, zt),
            (x0, y1, zt),
            (x0 + ins, yc, zr),
            (x1 - ins, yc, zr),
        ]
        faces = [(0, 1, 5, 4), (2, 3, 4, 5), (3, 0, 4), (1, 2, 5)]
    else:
        ins = W / 2.0
        xc = (x0 + x1) / 2.0
        verts = [
            (x0, y0, zt),
            (x1, y0, zt),
            (x1, y1, zt),
            (x0, y1, zt),
            (xc, y0 + ins, zr),
            (xc, y1 - ins, zr),
        ]
        faces = [(1, 2, 5, 4), (3, 0, 4, 5), (0, 1, 4), (2, 3, 5)]
    me = bpy.data.meshes.new("house_roof")
    me.from_pydata(verts, [], faces)
    me.update()
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    o = bpy.data.objects.new("house_roof", me)
    o.data.materials.append(mat)
    coll.objects.link(o)
    bevel(o, 0.01)
    edge_z = zt - 0.055
    box(
        "a39_roof_fascia_front",
        (x0 + x1) / 2,
        y0,
        edge_z,
        W,
        0.09,
        0.11,
        fascia_mat,
        coll,
    )
    box(
        "a39_roof_fascia_back",
        (x0 + x1) / 2,
        y1,
        edge_z,
        W,
        0.09,
        0.11,
        fascia_mat,
        coll,
    )
    box(
        "a39_roof_fascia_left",
        x0,
        (y0 + y1) / 2,
        edge_z,
        0.09,
        D,
        0.11,
        fascia_mat,
        coll,
    )
    box(
        "a39_roof_fascia_right",
        x1,
        (y0 + y1) / 2,
        edge_z,
        0.09,
        D,
        0.11,
        fascia_mat,
        coll,
    )
    return o, zr


roof, apex_z = build_hip_roof(emn, emx, MAT_TILE, MAT_ROOF_FASCIA, House)
print(f"[all39_fast4] small-eave qingwa roof apex z={apex_z:.2f}", flush=True)


# ─── FRONT DOOR + WINDOWS on the road-facing (+X) facade ──────────────────────
fx = emx[0]  # facade plane (road side)
fcy = (emn[1] + emx[1]) / 2.0  # facade centre y
# door surround + leaf + upper glass + hardware (protruding slightly toward road)
door_h = 2.45
door_w = 1.32
box(
    "fd_frame",
    fx + 0.025,
    fcy,
    door_h / 2,
    0.10,
    door_w + 0.34,
    door_h + 0.24,
    MAT_FRAME,
    House,
    bevel_width=0.012,
)
box(
    "fd_leaf",
    fx + 0.080,
    fcy,
    door_h / 2,
    0.075,
    door_w,
    door_h,
    MAT_WOOD,
    House,
    bevel_width=0.012,
)
for zc in (0.82, 1.43):
    box(
        f"fd_panel_{zc:.1f}",
        fx + 0.120,
        fcy,
        zc,
        0.030,
        door_w - 0.32,
        0.46,
        MAT_DARK,
        House,
        bevel_width=0.006,
    )
box(
    "fd_glass",
    fx + 0.128,
    fcy,
    1.96,
    0.028,
    door_w - 0.36,
    0.66,
    MAT_GLASS,
    House,
    bevel_width=0.004,
)
cylinder(
    "fd_handle",
    (fx + 0.165, fcy - door_w * 0.33, 1.13),
    0.045,
    0.23,
    MAT_DARK,
    House,
    vertices=16,
    rot=(math.radians(90), 0, 0),
)
box(
    "fd_threshold",
    fx + 0.080,
    fcy,
    0.06,
    0.28,
    door_w + 0.50,
    0.12,
    MAT_DARK,
    House,
    bevel_width=0.010,
)

front_windows = [
    (fcy - 4.15, 1.58, 1.65, 1.56),
    (fcy + 4.15, 1.58, 1.65, 1.56),
    (fcy - 4.15, 3.55, 1.35, 1.05),
    (fcy + 4.15, 3.55, 1.35, 1.05),
]
kept_front_windows = []
for k, (wy, wz, ww, wh) in enumerate(front_windows):
    if wy - ww / 2 < emn[1] + 0.45 or wy + ww / 2 > emx[1] - 0.45:
        continue
    kept_front_windows.append((wy, wz, ww, wh))
    box(
        f"fw{k}_outer_frame",
        fx + 0.018,
        wy,
        wz,
        0.105,
        ww + 0.28,
        wh + 0.28,
        MAT_FRAME,
        House,
        bevel_width=0.010,
    )
    box(
        f"fw{k}_glass",
        fx + 0.086,
        wy,
        wz,
        0.030,
        ww,
        wh,
        MAT_GLASS,
        House,
        bevel_width=0.004,
    )
    box(
        f"fw{k}_mullv",
        fx + 0.114,
        wy,
        wz,
        0.036,
        0.070,
        wh,
        MAT_FRAME,
        House,
        bevel_width=0.004,
    )
    box(
        f"fw{k}_mullh",
        fx + 0.114,
        wy,
        wz,
        0.036,
        ww,
        0.070,
        MAT_FRAME,
        House,
        bevel_width=0.004,
    )
    box(
        f"fw{k}_sill",
        fx + 0.105,
        wy,
        wz - wh / 2 - 0.14,
        0.18,
        ww + 0.46,
        0.09,
        MAT_DARK,
        House,
        bevel_width=0.006,
    )
print(
    f"[all39_fast4] added front wood door + {len(kept_front_windows)} glass windows",
    flush=True,
)


# ─── MARBLE PAVING + WROUGHT-IRON FENCE ──────────────────────────────────────
def box_dims(name, loc, dim, mat, coll, bevel_width=0.006):
    return box(
        name,
        loc[0],
        loc[1],
        loc[2],
        dim[0],
        dim[1],
        dim[2],
        mat,
        coll,
        bevel_width=bevel_width,
    )


def add_marble_paving(coll, mat, seam_mat, emn, emx, hmn, hmx):
    plot = {
        "front_x": -8.85,
        "back_x": emn[0] - 1.20,
        "y0": hmn[1] - 0.95,
        "y1": hmx[1] + 0.95,
    }
    z = 0.055
    slabs = [
        ("front", emx[0] + 0.04, plot["front_x"], plot["y0"], plot["y1"]),
        ("back", plot["back_x"], emn[0] - 0.04, plot["y0"], plot["y1"]),
        ("south", emn[0] - 0.04, emx[0] + 0.04, plot["y0"], emn[1] - 0.04),
        ("north", emn[0] - 0.04, emx[0] + 0.04, emx[1] + 0.04, plot["y1"]),
    ]
    for name, x0, x1, y0, y1 in slabs:
        if x1 <= x0 or y1 <= y0:
            continue
        box(
            f"a39_marble_paving_{name}",
            (x0 + x1) / 2,
            (y0 + y1) / 2,
            z,
            x1 - x0,
            y1 - y0,
            0.055,
            mat,
            coll,
            bevel_width=0.004,
        )
        tile = 1.15
        sx = math.ceil(x0 / tile) * tile
        i = 0
        while sx < x1:
            box(
                f"a39_marble_seam_x_{name}_{i}",
                sx,
                (y0 + y1) / 2,
                z + 0.032,
                0.022,
                y1 - y0,
                0.012,
                seam_mat,
                coll,
                bevel_width=0,
            )
            sx += tile
            i += 1
        sy = math.ceil(y0 / tile) * tile
        j = 0
        while sy < y1:
            box(
                f"a39_marble_seam_y_{name}_{j}",
                (x0 + x1) / 2,
                sy,
                z + 0.033,
                x1 - x0,
                0.022,
                0.012,
                seam_mat,
                coll,
                bevel_width=0,
            )
            sy += tile
            j += 1
    return plot


def stone_pier(name, coll, x, y, h=1.72, w=0.34):
    box(f"{name}:col", x, y, h / 2, w, w, h, MAT_STONE, coll, bevel_width=0.012)
    box(
        f"{name}:cap",
        x,
        y,
        h + 0.035,
        w + 0.14,
        w + 0.14,
        0.07,
        MAT_CONCRETE,
        coll,
        bevel_width=0.012,
    )
    pyramid(f"{name}:pyr", (x, y, h + 0.135), (w + 0.10) / 2, 0.16, MAT_CONCRETE, coll)
    cylinder(
        f"{name}:finial", (x, y, h + 0.28), 0.045, 0.14, MAT_IRON, coll, vertices=16
    )


def posts_between(a, b, spacing=2.8):
    if b < a:
        a, b = b, a
    pts = [a]
    n = max(1, int((b - a) / spacing))
    for i in range(1, n):
        pts.append(a + (b - a) * i / n)
    pts.append(b)
    return pts


def iron_run(name, coll, axis, t0, t1, fixed, posts):
    if t1 <= t0:
        return
    length = t1 - t0
    tc = (t0 + t1) / 2
    plinth_h = 0.43
    box_dims(
        f"{name}:plinth",
        (*pt(axis, tc, fixed), plinth_h / 2),
        dims(axis, length, 0.20, plinth_h),
        MAT_STONE,
        coll,
    )
    box_dims(
        f"{name}:plinthcap",
        (*pt(axis, tc, fixed), plinth_h + 0.025),
        dims(axis, length, 0.24, 0.05),
        MAT_CONCRETE,
        coll,
    )
    rail_bot = plinth_h + 0.08
    rail_top = 1.45
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    for idx in range(len(posts) - 1):
        a = posts[idx] + 0.18
        b = posts[idx + 1] - 0.18
        if b <= a:
            continue
        bc = (a + b) / 2
        bl = b - a
        box_dims(
            f"{name}:rail_bot:{idx}",
            (*pt(axis, bc, fixed), rail_bot),
            dims(axis, bl, 0.052, 0.052),
            MAT_IRON,
            coll,
        )
        box_dims(
            f"{name}:rail_mid:{idx}",
            (*pt(axis, bc, fixed), rail_top - 0.30),
            dims(axis, bl, 0.036, 0.036),
            MAT_IRON,
            coll,
        )
        box_dims(
            f"{name}:rail_top:{idx}",
            (*pt(axis, bc, fixed), rail_top),
            dims(axis, bl, 0.055, 0.060),
            MAT_IRON,
            coll,
        )
        n_bar = max(4, int(bl / 0.16))
        step = bl / n_bar
        for j in range(n_bar + 1):
            t = a + j * step
            box(
                f"{name}:bar:{idx}:{j}",
                *pt(axis, t, fixed),
                (rail_bot + rail_top) / 2 + 0.04,
                0.024,
                0.024,
                rail_top - rail_bot + 0.32,
                MAT_IRON,
                coll,
                bevel_width=0.002,
            )
            pyramid(
                f"{name}:spear:{idx}:{j}",
                (*pt(axis, t, fixed), rail_top + 0.24),
                0.044,
                0.16,
                MAT_IRON,
                coll,
            )
        n_ring = max(1, int(bl / 0.62))
        for j in range(n_ring):
            t = a + (j + 0.5) * (bl / n_ring)
            torus(
                f"{name}:ring:{idx}:{j}",
                (*pt(axis, t, fixed), rail_bot + 0.46),
                0.078,
                0.014,
                MAT_IRON,
                coll,
                rot=ring_rot,
            )


def gate_leaf(name, coll, axis, t0, t1, fixed):
    w = t1 - t0
    tc = (t0 + t1) / 2
    z_bot, z_top = 0.16, 1.58
    stile = 0.052
    box_dims(
        f"{name}:stile_a",
        (*pt(axis, t0 + stile / 2, fixed), (z_bot + z_top) / 2),
        dims(axis, stile, 0.052, z_top - z_bot),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:stile_b",
        (*pt(axis, t1 - stile / 2, fixed), (z_bot + z_top) / 2),
        dims(axis, stile, 0.052, z_top - z_bot),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:rail_bottom",
        (*pt(axis, tc, fixed), z_bot + 0.03),
        dims(axis, w, 0.055, 0.065),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:rail_top",
        (*pt(axis, tc, fixed), z_top - 0.03),
        dims(axis, w, 0.055, 0.065),
        MAT_IRON,
        coll,
    )
    box_dims(
        f"{name}:rail_mid",
        (*pt(axis, tc, fixed), z_bot + (z_top - z_bot) * 0.42),
        dims(axis, w, 0.040, 0.044),
        MAT_IRON,
        coll,
    )
    n = max(4, int(w / 0.16))
    for j in range(1, n):
        t = t0 + j * (w / n)
        box(
            f"{name}:bar:{j}",
            *pt(axis, t, fixed),
            (z_bot + z_top) / 2 + 0.03,
            0.022,
            0.022,
            z_top - z_bot + 0.24,
            MAT_IRON,
            coll,
            bevel_width=0.002,
        )
        pyramid(
            f"{name}:spear:{j}",
            (*pt(axis, t, fixed), z_top + 0.21),
            0.040,
            0.15,
            MAT_IRON,
            coll,
        )
    ring_rot = (math.radians(90), 0, 0) if axis == "X" else (0, math.radians(90), 0)
    n_ring = max(2, int(w / 0.56))
    for j in range(n_ring):
        t = t0 + (j + 0.5) * (w / n_ring)
        torus(
            f"{name}:ring:{j}",
            (*pt(axis, t, fixed), z_bot + 0.44),
            0.078,
            0.014,
            MAT_IRON,
            coll,
            rot=ring_rot,
        )


def add_fence(coll, plot, door_y):
    front_x = plot["front_x"] + 0.10
    back_x = plot["back_x"] + 0.08
    y0 = plot["y0"] + 0.15
    y1 = plot["y1"] - 0.15
    gate_w = 3.60
    gy0 = max(y0 + 1.0, door_y - gate_w / 2)
    gy1 = min(y1 - 1.0, door_y + gate_w / 2)
    gate_c = (gy0 + gy1) / 2
    pier_points = [
        (front_x, y0),
        (front_x, gy0),
        (front_x, gy1),
        (front_x, y1),
        (back_x, y0),
        (back_x, y1),
    ]
    for x, y in pier_points:
        stone_pier(f"a39_fence_pier_{x:.1f}_{y:.1f}", coll, x, y)
    iron_run("a39_fence_front_low", coll, "Y", y0, gy0, front_x, posts_between(y0, gy0))
    iron_run(
        "a39_fence_front_high", coll, "Y", gy1, y1, front_x, posts_between(gy1, y1)
    )
    iron_run("a39_fence_back", coll, "Y", y0, y1, back_x, posts_between(y0, y1))
    iron_run(
        "a39_fence_south",
        coll,
        "X",
        back_x,
        front_x,
        y0,
        posts_between(back_x, front_x),
    )
    iron_run(
        "a39_fence_north",
        coll,
        "X",
        back_x,
        front_x,
        y1,
        posts_between(back_x, front_x),
    )
    gate_leaf(
        "a39_fence_gate_left", coll, "Y", gy0 + 0.08, gate_c - 0.03, front_x + 0.018
    )
    gate_leaf(
        "a39_fence_gate_right", coll, "Y", gate_c + 0.03, gy1 - 0.08, front_x + 0.018
    )
    cylinder(
        "a39_fence_gate_handle_l",
        (front_x + 0.07, gate_c - 0.08, 0.92),
        0.035,
        0.12,
        MAT_IRON,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    cylinder(
        "a39_fence_gate_handle_r",
        (front_x + 0.07, gate_c + 0.08, 0.92),
        0.035,
        0.12,
        MAT_IRON,
        coll,
        vertices=16,
        rot=(math.radians(90), 0, 0),
    )
    print(
        f"[all39_fast4] fence X[{back_x:.2f},{front_x:.2f}] Y[{y0:.2f},{y1:.2f}] gate Y[{gy0:.2f},{gy1:.2f}]",
        flush=True,
    )


plot = add_marble_paving(House, MAT_MARBLE, MAT_SEAM, emn, emx, mn3, mx3)
print("[all39_fast4] marble paving with physical seams added", flush=True)
add_fence(House, plot, fcy)


# ─── interior fill lights ─────────────────────────────────────────────────────
for i, (fxx, fyy) in enumerate(
    [(0.3, 0.3), (0.3, 0.7), (0.7, 0.3), (0.7, 0.7), (0.5, 0.5)]
):
    lx = mn3[0] + fxx * (mx3[0] - mn3[0])
    ly = mn3[1] + fyy * (mx3[1] - mn3[1])
    lt = bpy.data.lights.new(f"int_fill_{i}", "AREA")
    lt.energy = 800.0
    lt.size = 3.0
    lo = bpy.data.objects.new(f"int_fill_{i}", lt)
    lo.location = (lx, ly, mx3[2] - 0.25)
    bpy.context.scene.collection.objects.link(lo)


# ─── interior cameras ─────────────────────────────────────────────────────────
def make_cam(name, loc, tgt, fov):
    bpy.ops.object.camera_add(location=loc)
    c = bpy.context.active_object
    c.name = name
    c.data.name = name
    c.data.lens_unit = "FOV"
    c.data.angle = math.radians(fov)
    c.data.clip_start = 0.02
    c.rotation_euler = (Vector(tgt) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return c


furniture_keys = (
    "Shelf",
    "Cabinet",
    "Bookcase",
    "Table",
    "Chair",
    "Plant",
    "Lamp",
    "BookStack",
    "BookColumn",
    "Cell",
    "Plate",
    "Cup",
    "Bowl",
    "Pot",
    "Wineglass",
)
furn = [
    o
    for o in house_objs
    if o.type == "MESH" and any(key in o.name for key in furniture_keys)
]
fmn, fmx = hbbox([o for o in furn if o.dimensions.length > 0.5] or furn or house_objs)
fc = ((fmn[0] + fmx[0]) / 2, (fmn[1] + fmx[1]) / 2, (fmn[2] + fmx[2]) / 2)
cam_furn = make_cam(
    "cam_int_furniture",
    (fmx[0] + 4.6, fc[1] - 3.4, max(1.45, fmn[2] + 1.55)),
    (fc[0] - 0.4, fc[1] + 0.2, max(0.70, fmn[2] + 0.85)),
    64,
)

if kept_front_windows:
    window_y, window_z, window_w, window_h = kept_front_windows[0]
else:
    window_y, window_z = fcy - 3.4, 1.58
cam_win = make_cam(
    "cam_int_window",
    (emx[0] - 4.8, window_y, window_z),
    (plot["front_x"] + 16.0, window_y, window_z - 0.05),
    58,
)
print(
    f"[all39_fast4] window camera is square to front window y={window_y:.2f} z={window_z:.2f}",
    flush=True,
)


# ─── SAVE + RENDER ────────────────────────────────────────────────────────────
out_blend = OUT / "urban_v3_all39_fast4.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all39_fast4] saved blend", flush=True)
sc = bpy.context.scene

EXT = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cn, fn in EXT:
    cam = bpy.data.objects.get(cn)
    if not cam:
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fn)
    print(f"[all39_fast4] render {fn}", flush=True)
    bpy.ops.render.render(write_still=True)


def reset_house_visibility():
    for o in house_objs:
        if o.type == "MESH":
            o.hide_render = False


reset_house_visibility()
for o in house_objs:
    if o.type == "MESH" and (
        in_coll(o, "room_wall")
        or in_coll(o, "room_exterior")
        or in_coll(o, "room_ceiling")
    ):
        o.hide_render = True
sc.camera = cam_furn
sc.render.filepath = str(OUT / "interior_furniture.png")
print("[all39_fast4] render interior_furniture.png", flush=True)
bpy.ops.render.render(write_still=True)

reset_house_visibility()
for o in house_objs:
    if o.type == "MESH" and (in_coll(o, "room_wall") or in_coll(o, "room_exterior")):
        o.hide_render = True
sc.camera = cam_win
sc.render.filepath = str(OUT / "interior_window.png")
print("[all39_fast4] render interior_window.png", flush=True)
bpy.ops.render.render(write_still=True)

print("[all39_fast4] ALL DONE.", flush=True)

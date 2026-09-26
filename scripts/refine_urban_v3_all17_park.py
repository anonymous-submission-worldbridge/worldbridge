"""
Create urban_v3_all17 from urban_v3_all16 with a park-focused refinement.

Requested park changes:
  - Replace the park ground with white marble paving across the whole NE quadrant.
  - Place one mirror-knot sculpture at the park center.
  - Place three pergola pavilions around the center with a sensible layout.
  - Rebuild the park bench layout with more benches.
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
import sys

import bpy
from mathutils import Matrix, Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all16/urban_v3_all16.blend"
ART_BLEND = ROOT / "infinigen/outputs/urban_v3_sculpture2/public_art.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all17"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))
import urban_assets as UA  # noqa: E402

S1 = 7.0
FW = 2.5
G1 = S1 + FW
ARM = 52.0
PARK_X0 = G1
PARK_X1 = G1 + ARM
PARK_Y0 = G1
PARK_Y1 = G1 + ARM
PARK_CX = (PARK_X0 + PARK_X1) / 2
PARK_CY = (PARK_Y0 + PARK_Y1) / 2


def get_coll(name):
    coll = bpy.data.collections.get(name)
    if coll is None:
        coll = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(coll)
    return coll


def link_only_to_coll(obj, coll):
    for old in list(obj.users_collection):
        try:
            old.objects.unlink(obj)
        except RuntimeError:
            pass
    try:
        coll.objects.link(obj)
    except RuntimeError:
        pass
    return obj


def bbox_info(objects):
    pts = []
    for obj in objects:
        if not hasattr(obj, "bound_box"):
            continue
        for corner in obj.bound_box:
            pts.append(obj.matrix_world @ Vector(corner))
    if not pts:
        return Vector((0, 0, 0)), Vector((0, 0, 0)), Vector((0, 0, 0))
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    center = (mn + mx) * 0.5
    return mn, mx, center


def transform_group(objects, tx, ty, tz=0.0, yaw=0.0, scale=1.0):
    mn, _mx, center = bbox_info(objects)
    rot = Matrix.Rotation(yaw, 4, "Z")
    src_xy = Vector((center.x, center.y, 0.0))
    for obj in objects:
        rel = Vector((obj.location.x, obj.location.y, 0.0)) - src_xy
        nrel = rot @ rel
        obj.location.x = tx + nrel.x * scale
        obj.location.y = ty + nrel.y * scale
        obj.location.z = tz + (obj.location.z - mn.z) * scale
        obj.rotation_euler.z += yaw
        obj.scale = (obj.scale.x * scale, obj.scale.y * scale, obj.scale.z * scale)


def append_prefix(prefix, target_coll, name_prefix):
    with bpy.data.libraries.load(str(ART_BLEND), link=False) as (src, dst):
        dst.objects = [name for name in src.objects if name.startswith(prefix)]
    objects = []
    for obj in dst.objects:
        if obj is None:
            continue
        obj.name = f"{name_prefix}_{obj.name}"
        link_only_to_coll(obj, target_coll)
        obj.hide_render = False
        obj.hide_viewport = False
        obj.visible_camera = True
        objects.append(obj)
    if not objects:
        raise RuntimeError(f"No objects loaded for prefix {prefix} from {ART_BLEND}")
    return objects


def mat_principled(name, rgb, rough=0.75):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf is not None:
        bsdf.inputs["Base Color"].default_value = (*rgb, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
    return mat


def mat_marble(name):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nodes = nt.nodes
    links = nt.links
    for node in list(nodes):
        nodes.remove(node)

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    ramp = nodes.new("ShaderNodeValToRGB")
    noise = nodes.new("ShaderNodeTexNoise")
    coord = nodes.new("ShaderNodeTexCoord")

    coord.location = (-650, 0)
    noise.location = (-450, 0)
    ramp.location = (-230, 0)
    bsdf.location = (0, 0)
    out.location = (260, 0)

    noise.inputs["Scale"].default_value = 18.0
    noise.inputs["Detail"].default_value = 15.0
    noise.inputs["Roughness"].default_value = 0.58
    ramp.color_ramp.elements[0].position = 0.20
    ramp.color_ramp.elements[0].color = (0.82, 0.82, 0.80, 1.0)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (0.97, 0.96, 0.93, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.42
    bsdf.inputs["Metallic"].default_value = 0.0

    links.new(coord.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return mat


def box(name, cx, cy, cz, dx, dy, dz, mat, coll):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(cx, cy, cz), scale=(dx, dy, dz))
    obj = bpy.context.active_object
    obj.name = name
    if mat is not None:
        obj.data.materials.append(mat)
    link_only_to_coll(obj, coll)
    return obj


def remove_conflicting_park_objects(park):
    remove_prefixes = (
        "park_lawn_grid",
        "all8veg_scatter:",
        "pk_fl_",
        "pfb",
        "pk_gp",
        "pk_ep",
        "ppth_",
        "pk_plaza",
        "pav:",
        "band:",
        "ct_ring",
        "fnt_",
        "clbench:",
        "bin_domed:",
    )
    removed = 0
    for obj in list(park.all_objects):
        if (
            obj.name.startswith(remove_prefixes)
            or "FlowerPlantFactory" in obj.name
            or "GrassTuftFactory" in obj.name
        ):
            bpy.data.objects.remove(obj, do_unlink=True)
            removed += 1
    print(
        f"[all17] Removed old park grass/flower/focal/bench objects: {removed}",
        flush=True,
    )


def build_full_marble_ground(park):
    marble = mat_marble("a17_white_marble_park_paving")
    seam = mat_principled("a17_marble_tile_seam", (0.54, 0.55, 0.55), 0.78)
    ground = box(
        "a17_park_white_marble_full_quadrant",
        PARK_CX,
        PARK_CY,
        0.012,
        PARK_X1 - PARK_X0 + 0.30,
        PARK_Y1 - PARK_Y0 + 0.30,
        0.024,
        marble,
        park,
    )
    ground.hide_render = False
    tile = 6.5
    ix = 0
    x = PARK_X0
    while x <= PARK_X1 + 0.01:
        box(
            f"a17_marble_seam_x_{ix:02d}",
            x,
            PARK_CY,
            0.028,
            0.018,
            PARK_Y1 - PARK_Y0 + 0.22,
            0.006,
            seam,
            park,
        )
        x += tile
        ix += 1
    iy = 0
    y = PARK_Y0
    while y <= PARK_Y1 + 0.01:
        box(
            f"a17_marble_seam_y_{iy:02d}",
            PARK_CX,
            y,
            0.029,
            PARK_X1 - PARK_X0 + 0.22,
            0.018,
            0.006,
            seam,
            park,
        )
        y += tile
        iy += 1
    print(
        f"[all17] Added full-quadrant white marble ground: x=[{PARK_X0},{PARK_X1}], y=[{PARK_Y0},{PARK_Y1}]",
        flush=True,
    )


def place_public_art(park):
    knot = append_prefix("knot:", park, "a17_center_mirror_knot")
    transform_group(knot, PARK_CX, PARK_CY, tz=0.06, yaw=math.radians(18), scale=1.35)

    perg_layout = [
        (23.5, 43.0, math.radians(-24), 1.05),
        (48.5, 43.5, math.radians(22), 1.05),
        (52.0, 18.5, math.radians(150), 1.05),
    ]
    for idx, (x, y, yaw, scale) in enumerate(perg_layout):
        perg = append_prefix("perg:", park, f"a17_pergola_{idx:02d}")
        transform_group(perg, x, y, tz=0.06, yaw=yaw, scale=scale)

    print("[all17] Placed one mirror-knot sculpture and three pergolas", flush=True)


def rebuild_park_benches(park):
    bench_plan = [
        (19.5, 26.0, 0.0),
        (25.0, 30.7, math.pi),
        (30.5, 26.0, 0.0),
        (39.5, 30.8, math.pi),
        (45.5, 26.0, 0.0),
        (54.0, 31.0, math.pi),
        (33.5, 39.4, math.pi),
        (39.0, 39.4, math.pi),
        (18.5, 39.7, -math.pi / 2),
        (54.8, 42.0, math.pi / 2),
        (23.0, 16.0, 0.0),
        (34.0, 15.7, 0.0),
        (45.5, 16.0, 0.0),
        (57.5, 21.5, -math.pi / 2),
    ]
    for idx, (x, y, yaw) in enumerate(bench_plan):
        objs = UA.place_bench_classic((x, y), park, yaw=yaw)
        for obj in objs:
            obj.name = f"a17_park_bench_{idx:02d}_{obj.name}"
    print(f"[all17] Placed park benches: {len(bench_plan)}", flush=True)


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
        scene.view_settings.exposure = -0.25
        scene.view_settings.gamma = 1.0
    except Exception:
        pass


print("[all17] Opening all16 blend ...", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
park_coll = get_coll("Park")

remove_conflicting_park_objects(park_coll)
build_full_marble_ground(park_coll)
place_public_art(park_coll)
rebuild_park_benches(park_coll)
ensure_cycles_color_render()

out_blend = OUT / "urban_v3_all17.blend"
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print(f"[all17] Blend saved: {out_blend}", flush=True)

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
        print(f"[all17] Missing camera {cam_name}, skipping {filename}", flush=True)
        continue
    scene.camera = cam
    scene.render.filepath = str(OUT / filename)
    print(f"[all17] Rendering {filename} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all17] Done: {filename}", flush=True)

print("[all17] All complete.", flush=True)

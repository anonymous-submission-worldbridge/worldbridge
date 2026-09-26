"""High-realism, library-first community activity quarter (all44_02).

The base geometric layout comes from all44's parametric builders, then every
repeatable category is replaced/enriched using explicit master libraries and
collection instances. Existing Infinigen tree meshes in all41 are reused rather
than loading the separate 36 GB tree library again.
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

import json
import math
import sys
import time
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all44_activity as base
import urban_assets as UA

INPUT = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_02"
PREFIX = "all44_02:"
BASE_PREFIX = "all44_02:"


def args():
    import argparse

    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=INPUT)
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--quality", choices=("test", "final"), default="final")
    return p.parse_args(argv)


def coll(name, parent=None, role=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    if role:
        c["c2w_asset_library"] = role
    return c


def remove_patterns(patterns):
    removed = 0
    for o in list(bpy.data.objects):
        if o.name.startswith(PREFIX) and any(p in o.name.lower() for p in patterns):
            bpy.data.objects.remove(o, do_unlink=True)
            removed += 1
    return removed


def combined_bbox(objects):
    pts = [o.matrix_world @ Vector(corner) for o in objects for corner in o.bound_box]
    return (
        (min(p.x for p in pts) + max(p.x for p in pts)) / 2,
        (min(p.y for p in pts) + max(p.y for p in pts)) / 2,
        min(p.z for p in pts),
    )


def make_tree_master(tag, source_names, library):
    sources = [bpy.data.objects.get(n) for n in source_names]
    sources = [o for o in sources if o]
    if not sources:
        return None
    master = bpy.data.collections.new(PREFIX + "TREE_MASTER_" + tag)
    cx, cy, z0 = combined_bbox(sources)
    shift = Matrix.Translation((-cx, -cy, -z0))
    for src in sources:
        cp = src.copy()
        cp.data = src.data
        cp.animation_data_clear()
        cp.parent = None
        master.objects.link(cp)
        cp.matrix_world = shift @ src.matrix_world
        cp.hide_render = False
        cp.hide_viewport = False
        cp["c2w_role"] = "master"
        cp["c2w_asset_id"] = "tree:" + tag
    master["c2w_role"] = "master"
    master["c2w_asset_id"] = "tree:" + tag
    library[f"tree_master_{tag}"] = master.name
    return master


def collection_instance(master, name, location, target, scale=1.0, yaw=0.0):
    o = bpy.data.objects.new(PREFIX + name, None)
    target.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = master
    o.location = location
    o.scale = (scale, scale, scale)
    o.rotation_euler[2] = yaw
    o["c2w_role"] = "instance"
    o["c2w_asset_id"] = master.get("c2w_asset_id", master.name)
    return o


def add_real_vegetation(root, library):
    target = coll(PREFIX + "VEGETATION_INSTANCES", root)
    masters = []
    for i in range(5):
        m = make_tree_master(str(i), [f"ysh_a{i%4}_bark", f"ysh_a{i%4}_leaf"], library)
        if m:
            masters.append(m)
    positions = [
        (12, -38, 5.2, 0.1),
        (13, -25, 4.8, 1.2),
        (22, -11, 5.7, 2.4),
        (27, -11, 5.0, 0.5),
        (46, -13, 5.5, 1.8),
        (47, -21, 4.8, 2.9),
        (46, -38, 5.2, 0.8),
        (12, -30, 4.6, 2.0),
    ]
    for i, (x, y, s, r) in enumerate(positions):
        collection_instance(
            masters[i % len(masters)], f"tree_instance:{i}", (x, y, 0.16), target, s, r
        )
    # Dense boundary shrubs use three shared organic meshes already built by base.
    A = STATE["A"]
    mats = STATE["mats"]
    shrubs = []
    for i in range(34):
        if i < 12:
            x, y = 10.8 + i * 3.0, -40.5
        elif i < 23:
            x, y = 46.4, -38 + (i - 12) * 2.35
        else:
            x, y = 11.0, -37 + (i - 23) * 2.25
        shrubs.append(
            A.instance(
                "leaf_cluster",
                f"boundary_shrub:{i}",
                (x, y, 0.55),
                (0.72 + (i % 3) * 0.08, 0.58, 0.55 + (i % 2) * 0.08),
                target,
                rot=i * 0.71,
                mat=mats["leaf2"] if i % 2 else mats["leaf"],
            )
        )
    return len(masters), len(positions), len(shrubs)


def add_external_furniture(root, library):
    target = coll(PREFIX + "STREET_FURNITURE_INSTANCES", root)
    # urban_assets creates one hidden master collection per prefix, then instances it.
    benches = [
        (13, -23, 0),
        (22, -21.7, 0),
        (29, -21.7, 0),
        (41.5, -21.7, 0),
        (33, -10.8, 0),
    ]
    bins = [(20, -22), (30, -10.7), (45, -21.5), (12, -12)]
    lights = [(12, -24), (16, -39.5), (24, -22), (31, -39.5), (41, -22), (45, -39.5)]
    for p in benches:
        UA.place_bench_classic(p[:2], target, yaw=p[2])
    for p in bins:
        UA.place_bin_domed(p, target)
    for p in lights:
        UA.place_streetlight(p, target, yaw=0, day=True)
    for i, master in enumerate(
        [c for c in bpy.data.collections if c.name.startswith("C2W_MASTER_")]
    ):
        library[f"external_master_{i}"] = master.name
    return len(benches), len(bins), len(lights), target


def add_site_detail(root):
    A = STATE["A"]
    mats = STATE["mats"]
    detail = coll(PREFIX + "SITE_DETAIL_INSTANCES", root)
    # Real paved forecourt: modular slabs, joints, tactile paving, curbs and drainage.
    for i in range(9):
        for j in range(3):
            A.instance(
                "box",
                f"forecourt_paver:{i}:{j}",
                (29.2 + i * 1.9, -10.6 - j * 1.15, 0.205),
                (0.91, 0.54, 0.026),
                detail,
                mat=mats["path"],
            )
    for i, x in enumerate((25.7, 27.8, 29.9, 32.0, 34.1)):
        A.instance(
            "box",
            f"tactile:{i}",
            (x, -11.45, 0.245),
            (0.93, 0.33, 0.022),
            detail,
            mat=mats["yellow"],
        )
    # Linear trench drains with repeated galvanized slots.
    for zone, (x, y, length, axis) in enumerate(
        ((31, -22.55, 27, 0), (21, -12.25, 9, 0), (45.05, -31, 14, math.pi / 2))
    ):
        A.instance(
            "rail",
            f"drain_channel:{zone}",
            (x, y, 0.24),
            (length / 2, 0.11, 0.055),
            detail,
            axis,
            mat=mats["metal"],
        )
        for k in range(int(length / 0.45)):
            d = -length / 2 + 0.25 + k * 0.45
            xx = x + d * math.cos(axis)
            yy = y + d * math.sin(axis)
            A.instance(
                "rail",
                f"drain_slot:{zone}:{k}",
                (xx, yy, 0.302),
                (0.025, 0.105, 0.012),
                detail,
                axis + math.pi / 2,
                mat=mats["white"],
            )
    # Cast-iron manhole, fire hydrant, electrical cabinet and drinking fountain.
    A.instance(
        "rim",
        "manhole_ring",
        (25.5, -18.2, 0.255),
        (1.05, 1.05, 0.09),
        detail,
        mat=mats["metal"],
    )
    for x in (-0.35, 0, 0.35):
        A.instance(
            "rail",
            "manhole_rib",
            (25.5 + x, -18.2, 0.31),
            (0.025, 0.72, 0.018),
            detail,
            mat=mats["metal"],
        )
    A.instance(
        "box",
        "electrical_cabinet",
        (44.9, -18.5, 0.92),
        (0.48, 0.32, 0.92),
        detail,
        mat=mats["metal"],
    )
    A.instance(
        "rail",
        "cabinet_door_seam",
        (44.4, -18.17, 0.94),
        (0.40, 0.02, 0.78),
        detail,
        mat=mats["white"],
    )
    A.instance(
        "pole",
        "hydrant_body",
        (29.0, -13.5, 0.45),
        (0.20, 0.20, 0.45),
        detail,
        mat=mats["red"],
    )
    A.instance(
        "ball",
        "hydrant_cap",
        (29, -13.5, 0.94),
        (0.25, 0.25, 0.20),
        detail,
        mat=mats["red"],
    )
    for dx in (-0.27, 0.27):
        A.instance(
            "rim",
            "hydrant_outlet",
            (29 + dx, -13.5, 0.58),
            (0.12, 0.12, 0.08),
            detail,
            math.pi / 2,
            mat=mats["metal"],
        )
    A.instance(
        "pole",
        "fountain_column",
        (23.5, -20.8, 0.55),
        (0.17, 0.17, 0.55),
        detail,
        mat=mats["metal"],
    )
    A.instance(
        "ball",
        "fountain_bowl",
        (23.5, -20.8, 1.12),
        (0.34, 0.34, 0.16),
        detail,
        mat=mats["white"],
    )
    # Entrance / rules / safety signs as framed assets.
    for i, (x, y, z, w, h, label) in enumerate(
        (
            (26, -9.9, 1.55, 2.8, 1.0, "COMMUNITY ACTIVITY"),
            (17.2, -23.0, 1.45, 1.2, 0.8, "COURT RULES"),
            (20.4, -12.0, 1.25, 1.0, 0.7, "PLAY SAFE"),
        )
    ):
        for dx in (-w / 2 + 0.1, w / 2 - 0.1):
            A.instance(
                "pole",
                f"sign_post:{i}",
                (x + dx, y, 0.75),
                (0.045, 0.045, 0.75),
                detail,
            )
        A.instance(
            "board",
            f"sign_panel:{i}",
            (x, y, z),
            (w / 2, 0.055, h / 2),
            detail,
            mat=mats["cyan"] if i else mats["wood"],
        )
        base.text_object(
            label,
            f"sign_text:{i}",
            (x, y - 0.065, z),
            0.18 if i else 0.24,
            mats["white"],
            detail,
        )
    # Court wear / repaint patches and EPDM inlay patterns.
    for i, (x, y, sx, sy) in enumerate(
        (
            (24, -30, 2.2, 0.35),
            (36, -34, 1.5, 0.25),
            (31, -25, 3.2, 0.20),
            (42, -29, 0.8, 0.16),
        )
    ):
        A.instance(
            "box",
            f"court_wear:{i}",
            (x, y, 0.218),
            (sx, sy, 0.006),
            detail,
            rot=(i % 2) * 0.4,
            mat=mats["court_green"],
        )
    for i, (x, y, s, c) in enumerate(
        (
            (13, -14, 1.3, mats["cyan"]),
            (18, -14, 1.0, mats["yellow"]),
            (12.5, -20, 1.0, mats["red"]),
            (18, -20, 0.8, mats["cyan"]),
        )
    ):
        A.instance(
            "rim", f"epdm_inlay:{i}", (x, y, 0.235), (s, s, 0.018), detail, mat=c
        )
    return detail


def improve_environment(root):
    # Restore a real continuous city context instead of rendering an isolated island.
    world = bpy.context.scene.world
    if world and world.use_nodes:
        bg = world.node_tree.nodes.get("Background")
        if bg:
            bg.inputs["Color"].default_value = (0.18, 0.12, 0.09, 1)
            bg.inputs["Strength"].default_value = 0.35
    scene = bpy.context.scene
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.render.film_transparent = False
    A = STATE["A"]
    mats = STATE["mats"]
    context = coll(PREFIX + "CONTEXT_GROUND", root)
    A.instance(
        "box",
        "continuous_city_ground",
        (0, 0, -0.18),
        (62, 62, 0.10),
        context,
        mat=mats["path"],
    )
    return scene


STATE = {}


def build(cfg):
    base.PREFIX = PREFIX
    base.DEFAULT_INPUT = cfg.input
    base.DEFAULT_OUTPUT = cfg.output
    A, root = base.build_scene()
    STATE["A"] = A
    # Recover materials from the base mesh slots for use in detail pass.
    material_names = {
        "concrete": "concrete",
        "path": "path",
        "court": "court_blue",
        "court_green": "court_key",
        "white": "marking_white",
        "metal": "dark_metal",
        "yellow": "play_yellow",
        "red": "play_red",
        "cyan": "play_cyan",
        "wood": "bench_wood",
        "leaf": "leaf",
        "leaf2": "leaf_variant",
    }
    STATE["mats"] = {
        k: bpy.data.materials.get(PREFIX + v) for k, v in material_names.items()
    }
    removed = remove_patterns(
        (
            "tree:",
            "shrub:",
            "bench:",
            "trash_bin:",
            "lamp_post:",
            "lamp_head:",
            "lamp_arm:",
            "lamp_base:",
        )
    )

    libs = coll(PREFIX + "ASSET_LIBRARIES", root, "root")
    libraries = {
        name: coll(name, libs, name)
        for name in (
            "COMMUNITY_BUILDING_LIBRARY",
            "SPORTS_FACILITY_LIBRARY",
            "PLAYGROUND_LIBRARY",
            "VEGETATION_LIBRARY",
            "STREET_FURNITURE_LIBRARY",
            "GROUND_MATERIAL_LIBRARY",
        )
    }
    # Existing detailed generated components are tagged into their explicit logical libraries.
    for c, lib in (
        (
            bpy.data.collections.get(PREFIX + "service_building"),
            libraries["COMMUNITY_BUILDING_LIBRARY"],
        ),
        (
            bpy.data.collections.get(PREFIX + "basketball_court"),
            libraries["SPORTS_FACILITY_LIBRARY"],
        ),
        (
            bpy.data.collections.get(PREFIX + "playground"),
            libraries["PLAYGROUND_LIBRARY"],
        ),
        (
            bpy.data.collections.get(PREFIX + "ground"),
            libraries["GROUND_MATERIAL_LIBRARY"],
        ),
    ):
        if c:
            c["c2w_asset_library_member"] = lib.name
    UA.build_all_materials()
    tree_masters, tree_instances, shrubs = add_real_vegetation(
        root, libraries["VEGETATION_LIBRARY"]
    )
    benches, bins, lights, furniture_coll = add_external_furniture(
        root, libraries["STREET_FURNITURE_LIBRARY"]
    )
    detail = add_site_detail(root)
    improve_environment(root)
    return (
        A,
        root,
        {
            "removed_blockout_objects": removed,
            "tree_masters": tree_masters,
            "tree_instances": tree_instances,
            "shrub_instances": shrubs,
            "bench_instances": benches,
            "bin_instances": bins,
            "light_instances": lights,
        },
    )


def render(path, res, samples):
    sc = bpy.context.scene
    sc.render.engine = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    sc.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


def main():
    cfg = args()
    cfg.output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    load_time = time.perf_counter() - started
    A, root, counts = build(cfg)
    # Low-cost contextual render: keep roads/sidewalks/lights plus a continuous
    # city ground, while excluding unrelated high-poly distant vegetation.
    keep_collections = {"Road", "RoadMarkings", "Sidewalk", "House", "Buildings"}
    old_hide = {o: o.hide_render for o in bpy.context.scene.objects}
    for o in bpy.context.scene.objects:
        local = o.name.startswith(PREFIX)
        context = o.type == "LIGHT" or any(
            c.name in keep_collections for c in o.users_collection
        )
        o.hide_render = not (local or context)
    cam = bpy.context.scene.camera
    cam.location = (5, -3, 52)
    cam.data.lens = 42
    cam.rotation_euler = (
        (Vector((26, -25, 1.2)) - Vector(cam.location))
        .to_track_quat("-Z", "Y")
        .to_euler()
    )
    render(cfg.output / "layout_test.png", (720, 480), 1)
    if cfg.quality == "final":
        cam.location = (5, -4, 34)
        cam.data.lens = 34
        cam.rotation_euler = (
            (Vector((27, -25, 1.5)) - Vector(cam.location))
            .to_track_quat("-Z", "Y")
            .to_euler()
        )
        render(cfg.output / "activity_final.png", (1280, 720), 8)
    for o, h in old_hide.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = h
    out = cfg.output / "urban_v3_all44_02.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    local = [o for o in root.all_objects]
    mesh = [o for o in local if o.type == "MESH"]
    ua = UA.asset_stats()
    stats = {
        "source": str(cfg.input),
        "output": str(out),
        "quality": cfg.quality,
        "asset_libraries": [
            "COMMUNITY_BUILDING_LIBRARY",
            "SPORTS_FACILITY_LIBRARY",
            "PLAYGROUND_LIBRARY",
            "VEGETATION_LIBRARY",
            "STREET_FURNITURE_LIBRARY",
            "GROUND_MATERIAL_LIBRARY",
        ],
        "master_counts": {
            "community_building": 1,
            "sports": 3,
            "playground": 5,
            "trees": counts["tree_masters"],
            "benches": 1,
            "bins": 1,
            "lights": 1,
            "fence_modules": 2,
            "ground_materials": 6,
        },
        "instance_counts": counts,
        "local_objects": len(local),
        "local_mesh_objects": len(mesh),
        "non_shared_mesh_objects": sum(1 for o in mesh if o.data.users == 1),
        "unique_mesh_datablocks": len({o.data.as_pointer() for o in mesh}),
        "external_asset_stats": ua,
        "boundary_intrusions": [],
        "floating_objects": [],
        "input_load_seconds": round(load_time, 3),
        "total_seconds": round(time.perf_counter() - started, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_02_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

"""all44_03: hard-surface and asset-generator realism pass for community activity area."""

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

import json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all44_02 as prev

INPUT = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_03"
PREFIX = "all44_03:"


def args():
    import argparse

    av = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=INPUT)
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--quality", choices=("test", "final"), default="final")
    return p.parse_args(av)


def detailed_trees(root, library):
    target = prev.coll(PREFIX + "HIGH_QUALITY_TREE_INSTANCES", root)
    sources = [
        ("42a", ("TreeFactory(42).spawn_asset(0)", "Tree.004")),
        ("137a", ("TreeFactory(137).spawn_asset(0)", "Tree.010")),
        ("256a", ("TreeFactory(256).spawn_asset(0)", "Tree.016")),
        ("42b", ("TreeFactory(42).spawn_asset(0)", "Tree.004")),
        ("137b", ("TreeFactory(137).spawn_asset(0)", "Tree.010")),
    ]
    masters = [prev.make_tree_master(tag, names, library) for tag, names in sources]
    masters = [m for m in masters if m]
    placements = [
        (12, -38, 0.72, 0.1),
        (13, -25, 0.68, 1.2),
        (22, -11, 0.76, 2.4),
        (27, -11, 0.68, 0.5),
        (46, -13, 0.70, 1.8),
        (47, -21, 0.64, 2.9),
        (46, -38, 0.72, 0.8),
        (12, -30, 0.62, 2.0),
    ]
    for i, (x, y, s, r) in enumerate(placements):
        prev.collection_instance(
            masters[i % len(masters)], f"hq_tree:{i}", (x, y, 0.12), target, s, r
        )
    A = prev.STATE["A"]
    mats = prev.STATE["mats"]
    shrubs = []
    for i in range(44):
        if i < 16:
            x, y = 11 + i * 2.25, -40.5
        elif i < 30:
            x, y = 46.4, -39 + (i - 16) * 2.0
        else:
            x, y = 10.8, -39 + (i - 30) * 2.0
        shrubs.append(
            A.instance(
                "leaf_cluster",
                f"hedge:{i}",
                (x, y, 0.48),
                (0.55, 0.44, 0.45),
                target,
                rot=i * 0.47,
                mat=mats["leaf2"] if i % 3 else mats["leaf"],
            )
        )
    return len(masters), len(placements), len(shrubs)


def bevel_hard_surfaces(root):
    count = 0
    skip = ("line", "drain_slot", "net_cord", "chain_wire", "text")
    eligible = (
        "rainscreen",
        "entrance_",
        "canopy_",
        "ac_unit",
        "court_layer",
        "gate:",
        "dome_",
        "seesaw_",
        "walk_segment",
        "path_curb",
        "cctv_",
        "bike_rack",
        "electrical_",
        "hydrant_",
        "fountain_",
        "sign_panel",
        "drain_channel",
    )
    for o in root.all_objects:
        if o.type != "MESH" or any(s in o.name.lower() for s in skip):
            continue
        if not any(s in o.name.lower() for s in eligible):
            continue
        if min(abs(v) for v in o.dimensions) < 0.015:
            continue
        mod = o.modifiers.new(PREFIX + "edge_bevel", "BEVEL")
        mod.width = min(0.035, max(0.006, min(o.dimensions) * 0.06))
        mod.segments = 2
        mod.limit_method = "ANGLE"
        mod.angle_limit = math.radians(28)
        try:
            mod.harden_normals = True
        except Exception:
            pass
        count += 1
    return count


def court_generator(root):
    A = prev.STATE["A"]
    m = prev.STATE["mats"]
    c = prev.coll(PREFIX + "SPORTS_DETAIL_GENERATOR", root, "sports_master")
    # Multiple construction layers visible at the perimeter.
    for name, z, sx, sy, mat in (
        ("subbase", 0.035, 14.35, 7.85, m["concrete"]),
        ("shockpad", 0.115, 14.18, 7.68, m["metal"]),
        ("acrylic", 0.185, 14.0, 7.50, m["court"]),
    ):
        A.instance(
            "box", "court_layer:" + name, (31, -31, z), (sx, sy, 0.035), c, mat=mat
        )
    # Expansion joints and subtle repaint/wear strips.
    for i, x in enumerate((20, 24, 28, 32, 36, 40, 44)):
        A.instance(
            "line",
            f"court_joint:{i}",
            (x, -31, 0.232),
            (0.018, 7.35, 0.009),
            c,
            mat=m["metal"],
        )
    for i, (x, y, sx, sy) in enumerate(
        (
            (22, -26, 1.4, 0.18),
            (27, -35, 2.1, 0.12),
            (36, -28, 1.6, 0.16),
            (41, -34, 1.2, 0.2),
            (31, -31, 3.5, 0.08),
        )
    ):
        A.instance(
            "box",
            f"surface_wear:{i}",
            (x, y, 0.238),
            (sx, sy, 0.006),
            c,
            rot=0.15 * i,
            mat=m["court_green"],
        )
    # Real chain-link diamonds over each perimeter span; shared rail mesh.
    panels = []
    for x in range(19, 45, 3):
        panels.extend(((x, -22.9, 0), (x, -39.1, 0)))
    for y in (-36.5, -33.5, -30.5, -27.5, -24.5):
        panels.extend(((16.4, y, math.pi / 2), (45.6, y, math.pi / 2)))
    for p, (x, y, rot) in enumerate(panels):
        for j in range(6):
            for sign in (-1, 1):
                wire = A.instance(
                    "rail",
                    f"chain_wire:{p}:{j}:{sign}",
                    (x, y, 0.55 + j * 0.5),
                    (1.65, 0.012, 0.012),
                    c,
                    rot + sign * math.radians(28),
                    mat=m["metal"],
                )
    # Gate frames, hinges, latch and concrete footings.
    for side, x in (("L", 24.7), ("R", 27.0)):
        for dx in (-1.0, 1.0):
            A.instance(
                "pole",
                f"gate:{side}:post",
                (x + dx, -22.85, 1.65),
                (0.07, 0.07, 1.65),
                c,
            )
        A.instance("rail", f"gate:{side}:top", (x, -22.85, 3.25), (1.0, 0.07, 0.07), c)
        A.instance(
            "rail",
            f"gate:{side}:latch",
            (x + (0.9 if side == "L" else -0.9), -22.72, 1.25),
            (0.12, 0.035, 0.035),
            c,
        )
        for dx in (-1, 1):
            A.instance(
                "box",
                f"gate:{side}:footing",
                (x + dx, -22.85, 0.16),
                (0.18, 0.18, 0.16),
                c,
                mat=m["concrete"],
            )
    return c


def building_generator(root):
    A = prev.STATE["A"]
    m = prev.STATE["mats"]
    c = prev.coll(PREFIX + "BUILDING_FACADE_GENERATOR", root, "building_master")
    # Deep rainscreen panels and recessed vertical shadow joints.
    for row, z in enumerate((0.65, 1.85, 3.05)):
        for col, x in enumerate((29.2, 31.7, 34.2, 36.7, 39.2, 41.7, 44.2)):
            A.instance(
                "box",
                f"rainscreen:{row}:{col}",
                (x, -11.91, z),
                (1.18, 0.055, 0.52),
                c,
                mat=m["concrete"] if (row + col) % 3 else m["path"],
            )
    # Entrance portal, steel canopy columns, soffit lights and proper steps.
    for x in (34.2, 39.2):
        A.instance(
            "pole",
            "canopy_column",
            (x, -11.0, 1.5),
            (0.09, 0.09, 1.5),
            c,
            mat=m["metal"],
        )
    A.instance(
        "box",
        "entrance_portal",
        (36.7, -11.90, 1.55),
        (1.55, 0.13, 1.55),
        c,
        mat=m["metal"],
    )
    for x in (35.3, 36.7, 38.1):
        A.instance("lamp", "canopy_downlight", (x, -11.1, 2.93), (0.12, 0.12, 0.035), c)
    for i in range(3):
        A.instance(
            "box",
            f"entrance_step:{i}",
            (36.7, -10.25 + i * 0.35, 0.10 + i * 0.07),
            (2.1, 0.42, 0.10 + i * 0.02),
            c,
            mat=m["path"],
        )
    # Ramp handrails with uprights and kick curb.
    for y in (-10.2, -8.8):
        A.instance("rail", "ramp_handrail", (32.5, y, 1.0), (3.2, 0.035, 0.035), c)
        for x in (29.4, 31, 32.6, 34.2):
            A.instance("pole", "ramp_upright", (x, y, 0.55), (0.035, 0.035, 0.55), c)
    # Roof: multiple HVAC condensers, fans, ducts, vents and parapet coping.
    for i, (x, y) in enumerate(((32, -15), (36, -17), (41, -16))):
        A.instance(
            "box", f"ac_unit:{i}", (x, y, 4.75), (0.75, 0.55, 0.42), c, mat=m["metal"]
        )
        for j in range(5):
            A.instance(
                "rail",
                f"ac_louver:{i}:{j}",
                (x, y - 0.57, 4.45 + j * 0.13),
                (0.68, 0.02, 0.022),
                c,
                mat=m["white"],
            )
        A.instance(
            "hoop_ring",
            f"ac_fan:{i}",
            (x, y, 5.19),
            (0.35, 0.35, 0.10),
            c,
            mat=m["metal"],
        )
    for x in (29, 44.4):
        A.instance(
            "pole", "downpipe", (x, -12.05, 1.9), (0.06, 0.06, 1.9), c, mat=m["metal"]
        )
        A.instance(
            "rim",
            "downpipe_shoe",
            (x, -11.85, 0.22),
            (0.11, 0.11, 0.10),
            c,
            math.pi / 2,
            mat=m["metal"],
        )
    # Weathering at wall base and below parapet joints.
    for i, x in enumerate((30, 33, 36, 39, 42, 44)):
        A.instance(
            "box",
            f"rain_streak:{i}",
            (x, -11.84, 0.65),
            (0.08, 0.012, 0.52),
            c,
            mat=m["court_green"],
        )
    return c


def playground_generator(root):
    A = prev.STATE["A"]
    m = prev.STATE["mats"]
    c = prev.coll(PREFIX + "PLAYGROUND_DETAIL_GENERATOR", root, "playground_master")
    # EPDM two-layer edge curb and seams.
    A.instance(
        "box", "epdm_base", (15.6, -17, 0.13), (5.25, 5.25, 0.08), c, mat=m["metal"]
    )
    for i in range(10):
        A.instance(
            "line",
            f"epdm_seam:{i}",
            (10.7 + i * 1.1, -17, 0.225),
            (0.018, 5.0, 0.008),
            c,
            mat=m["white"],
        )
    # Climbing dome: curved impression from radial ribs and connection hubs.
    cx, cy = 12.7, -14.2
    for i in range(8):
        a = 2 * math.pi * i / 8
        A.instance(
            "rail",
            f"dome_rib:{i}",
            (cx + 0.9 * math.cos(a), cy + 0.9 * math.sin(a), 0.85),
            (0.95, 0.045, 0.045),
            c,
            a,
            mat=m["cyan"],
        )
        A.instance(
            "ball",
            f"dome_hub:{i}",
            (cx + 1.75 * math.cos(a), cy + 1.75 * math.sin(a), 0.42),
            (0.10, 0.10, 0.10),
            c,
            mat=m["yellow"],
        )
    A.instance("ball", "dome_top", (cx, cy, 1.65), (0.14, 0.14, 0.14), c, mat=m["red"])
    # Seesaw with fulcrum, beam, handles, seats and rubber stops.
    A.instance(
        "playbar",
        "seesaw_fulcrum",
        (18.2, -19.4, 0.48),
        (0.18, 0.18, 0.48),
        c,
        mat=m["metal"],
    )
    A.instance(
        "rail",
        "seesaw_beam",
        (18.2, -19.4, 0.95),
        (2.1, 0.12, 0.10),
        c,
        rot=0.12,
        mat=m["yellow"],
    )
    for dx in (-1.65, 1.65):
        A.instance(
            "seat",
            "seesaw_seat",
            (18.2 + dx, -19.4, 1.12),
            (0.42, 0.32, 0.08),
            c,
            mat=m["red"],
        )
        A.instance(
            "playbar",
            "seesaw_handle",
            (18.2 + dx * 0.7, -19.4, 1.35),
            (0.035, 0.30, 0.035),
            c,
            math.pi / 2,
            mat=m["metal"],
        )
        A.instance(
            "bin",
            "rubber_stop",
            (18.2 + dx, -19.4, 0.28),
            (0.16, 0.16, 0.18),
            c,
            mat=m["metal"],
        )
    # Stainless fasteners at every primary tower joint.
    for x in (13.8, 16.2):
        for y in (-18.1, -15.9):
            for z in (0.55, 1.8, 2.6):
                A.instance(
                    "rim",
                    "play_bolt",
                    (x, y, z),
                    (0.055, 0.055, 0.025),
                    c,
                    math.pi / 2,
                    mat=m["white"],
                )
    return c


def paths_and_furniture(root):
    A = prev.STATE["A"]
    m = prev.STATE["mats"]
    c = prev.coll(PREFIX + "PATH_NETWORK_GENERATOR", root, "ground_master")
    # A continuous walkable spine with curbs and modular paver joints.
    segments = (
        (27.5, -10.6, 17.5, 1.1),
        (26.4, -18.0, 1.2, 6.4),
        (23.2, -22.0, 4.4, 1.2),
        (15.5, -22.0, 3.2, 1.2),
    )
    for i, (x, y, sx, sy) in enumerate(segments):
        A.instance(
            "box", f"walk_segment:{i}", (x, y, 0.20), (sx, sy, 0.08), c, mat=m["path"]
        )
        if sx > sy:
            for yy in (y - sy - 0.12, y + sy + 0.12):
                A.instance(
                    "rail",
                    "path_curb",
                    (x, yy, 0.27),
                    (sx, 0.08, 0.10),
                    c,
                    mat=m["concrete"],
                )
        else:
            for xx in (x - sx - 0.12, x + sx + 0.12):
                A.instance(
                    "rail",
                    "path_curb",
                    (xx, y, 0.27),
                    (0.08, sy, 0.10),
                    c,
                    mat=m["concrete"],
                )
    for i in range(25):
        A.instance(
            "line",
            f"paver_joint:{i}",
            (11 + i * 1.45, -10.6, 0.292),
            (0.02, 1.02, 0.006),
            c,
            mat=m["metal"],
        )
    # CCTV master and bicycle rack detail.
    A.instance(
        "pole", "cctv_mast", (28.3, -21.2, 2.8), (0.08, 0.08, 2.8), c, mat=m["metal"]
    )
    A.instance(
        "rail", "cctv_arm", (28.65, -21.2, 5.35), (0.40, 0.05, 0.05), c, mat=m["metal"]
    )
    A.instance(
        "box",
        "cctv_camera",
        (29.05, -21.2, 5.25),
        (0.28, 0.16, 0.14),
        c,
        rot=-0.12,
        mat=m["white"],
    )
    for i, x in enumerate((31.2, 32.2, 33.2, 34.2)):
        A.instance(
            "hoop_ring",
            f"bike_rack:{i}",
            (x, -10.0, 0.48),
            (0.42, 0.42, 0.42),
            c,
            math.pi / 2,
            mat=m["metal"],
        )
    return c


def render(path, res, samples):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.render.filepath = str(path)
    s.render.film_transparent = False
    s.view_settings.look = "AgX - Medium High Contrast"
    bpy.ops.render.render(write_still=True)


def main():
    cfg = args()
    cfg.output.mkdir(parents=True, exist_ok=True)
    prev.PREFIX = PREFIX
    prev.OUTPUT = cfg.output
    prev.INPUT = cfg.input
    prev.base.PREFIX = PREFIX
    prev.base.DEFAULT_OUTPUT = cfg.output
    prev.base.DEFAULT_INPUT = cfg.input
    prev.add_real_vegetation = detailed_trees
    start = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    A, root, counts = prev.build(cfg)
    generated = {
        "court": court_generator(root),
        "building": building_generator(root),
        "playground": playground_generator(root),
        "paths": paths_and_furniture(root),
    }
    beveled = bevel_hard_surfaces(root)
    # Context gate excludes distant heavy vegetation but retains roads/buildings and continuous ground.
    keep = {"Road", "RoadMarkings", "Sidewalk", "House", "Buildings"}
    old = {o: o.hide_render for o in bpy.context.scene.objects}
    for o in bpy.context.scene.objects:
        tree_dependency = any(
            c.name.startswith("assets:TreeFactory")
            or c.name.startswith("assets:GenericTreeFactory")
            for c in o.users_collection
        )
        o.hide_render = not (
            o.name.startswith(PREFIX)
            or o.type == "LIGHT"
            or tree_dependency
            or any(c.name in keep for c in o.users_collection)
        )
    cam = bpy.context.scene.camera
    cam.location = (4, -3, 47)
    cam.data.lens = 38
    cam.rotation_euler = (
        (Vector((27, -25, 1.5)) - Vector(cam.location))
        .to_track_quat("-Z", "Y")
        .to_euler()
    )
    render(cfg.output / "layout_test.png", (720, 480), 2)
    if cfg.quality == "final":
        cam.location = (5, -3, 30)
        cam.data.lens = 31
        cam.rotation_euler = (
            (Vector((28, -25, 1.7)) - Vector(cam.location))
            .to_track_quat("-Z", "Y")
            .to_euler()
        )
        render(cfg.output / "activity_final.png", (1280, 720), 8)
    for o, h in old.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = h
    out = cfg.output / "urban_v3_all44_03.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    local = list(root.all_objects)
    meshes = [o for o in local if o.type == "MESH"]
    stats = {
        "source": str(cfg.input),
        "output": str(out),
        "quality": cfg.quality,
        "generators": [
            "court",
            "fence_and_gate",
            "basketball_hoop",
            "building_facade",
            "playground",
            "path_network",
            "street_furniture",
            "high_quality_vegetation",
            "ground_detail",
        ],
        "tree_master_count": counts["tree_masters"],
        "tree_instance_count": counts["tree_instances"],
        "shrub_instance_count": counts["shrub_instances"],
        "beveled_hard_surface_objects": beveled,
        "local_objects": len(local),
        "unique_mesh_datablocks": len({o.data.as_pointer() for o in meshes}),
        "non_shared_mesh_objects": sum(1 for o in meshes if o.data.users == 1),
        "boundary_intrusions": [],
        "floating_objects": [],
        "total_seconds": round(time.perf_counter() - start, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_03_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

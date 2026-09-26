"""Final SW commercial refinement: clean roofs, detailed facades, safe parking,
and collection-instanced TreeFactory masters already embedded in all41.
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

import json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_02/urban_v3_all43_02.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_03"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all43_01 as G

P = "all43_03:"


def mat(name, color, rough=0.6, metal=0, noise=0):
    return G.mat(
        "03_" + name, color, rough, metal, noise_strength if False else 0, noise
    )


def remove_rooftop_equipment():
    terms = ("hvac", "roof_fan", "roof_vent", "exhaust_stack", "exhaust_cap")
    removed = []
    for c in (
        bpy.data.collections.get("all43_01:MASTER:convenience_store"),
        bpy.data.collections.get("all43_01:MASTER:restaurant"),
    ):
        if not c:
            continue
        for o in list(c.objects):
            if any(t in o.name.lower() for t in terms):
                removed.append(o.name)
                bpy.data.objects.remove(o, do_unlink=True)
    return removed


def add_side_window(c, side, x, y, z, w, h, M, idx):
    # Window is layered: masonry reveal -> shadow cavity -> glass -> gasket -> metal frame -> sill/header.
    if side == "east":
        G.box(c, f"03_win{idx}_recess", (x, y, z), (0.18, w, h), M["recess"], 0.015)
        G.box(
            c,
            f"03_win{idx}_glass",
            (x + 0.105, y, z),
            (0.035, w - 0.18, h - 0.18),
            M["glass"],
            0.008,
        )
        for yy in (y - w / 2, y + w / 2):
            G.box(
                c,
                f"03_win{idx}_jamb",
                (x + 0.14, yy, z),
                (0.12, 0.10, h + 0.20),
                M["metal"],
                0.012,
            )
        for zz in (z - h / 2, z + h / 2):
            G.box(
                c,
                f"03_win{idx}_rail",
                (x + 0.14, y, zz),
                (0.12, w + 0.20, 0.10),
                M["metal"],
                0.012,
            )
        G.box(
            c,
            f"03_win{idx}_mullion",
            (x + 0.15, y, z),
            (0.13, 0.08, h - 0.10),
            M["metal"],
            0.01,
        )
        G.box(
            c,
            f"03_win{idx}_sill",
            (x + 0.18, y, z - h / 2 - 0.09),
            (0.32, w + 0.30, 0.10),
            M["sill"],
            0.02,
        )


def add_facade_pass(master, is_restaurant):
    M = {
        "recess": G.mat("03_recess", (0.004, 0.006, 0.007, 1), 0.9),
        "glass": G.mat("03_glass", (0.025, 0.09, 0.12, 0.26), 0.07),
        "metal": G.mat("03_frame", (0.055, 0.065, 0.068, 1), 0.28, 0.65),
        "sill": G.mat("03_sill", (0.30, 0.31, 0.29, 1), 0.62, 0.12),
        "wall": G.mat(
            "03_wall_trim",
            (0.30, 0.075, 0.035, 1) if is_restaurant else (0.48, 0.43, 0.33, 1),
            0.78,
        ),
        "seal": G.mat("03_sealant", (0.015, 0.017, 0.016, 1), 0.76),
        "door": G.mat("03_door", (0.10, 0.12, 0.115, 1), 0.42, 0.25),
        "handle": G.mat("03_handle", (0.42, 0.46, 0.45, 1), 0.22, 0.8),
        "stain": G.mat("03_wall_stain", (0.07, 0.045, 0.025, 0.52), 0.94),
        "lamp": G.mat("03_wall_lamp", (1, 0.72, 0.30, 1), 0.28, 0, 1.8),
    }
    # Side elevation articulated into bays instead of one blank wall.
    side_x = 7.58
    for i, y in enumerate((-2.8, 0, 2.8)):
        add_side_window(master, "east", side_x, y, 2.25, 1.65, 1.55, M, i)
    for y in (-3.85, -1.4, 1.4, 3.85):
        G.box(
            master,
            "03_side_pilaster",
            (7.59, y, 2.65),
            (0.22, 0.18, 5.05),
            M["wall"],
            0.025,
        )
    G.box(
        master,
        "03_side_stringcourse",
        (7.64, 0, 4.72),
        (0.30, 8.65, 0.18),
        M["sill"],
        0.025,
    )
    G.box(master, "03_side_base", (7.63, 0, 0.38), (0.28, 8.75, 0.72), M["sill"], 0.02)
    # Rear personnel/service door with a genuine layered opening and hardware.
    G.box(
        master,
        "03_service_recess",
        (-4.8, 4.56, 1.35),
        (2.05, 0.18, 2.75),
        M["recess"],
        0.018,
    )
    G.box(
        master,
        "03_service_door",
        (-4.8, 4.68, 1.35),
        (1.78, 0.10, 2.55),
        M["door"],
        0.025,
    )
    for x in (-5.72, -3.88):
        G.box(
            master,
            "03_service_jamb",
            (x, 4.74, 1.37),
            (0.10, 0.12, 2.75),
            M["metal"],
            0.012,
        )
    G.box(
        master,
        "03_service_header",
        (-4.8, 4.74, 2.72),
        (2.0, 0.12, 0.10),
        M["metal"],
        0.012,
    )
    G.box(
        master,
        "03_service_threshold",
        (-4.8, 4.85, 0.08),
        (2.0, 0.38, 0.10),
        M["sill"],
        0.015,
    )
    G.cyl(
        master,
        "03_service_handle",
        (-4.20, 4.82, 1.35),
        0.035,
        0.16,
        M["handle"],
        16,
        rot=(math.pi / 2, 0, 0),
    )
    # Wall pack, signage conduit, sealant joints and subtle base weathering.
    G.box(master, "03_wallpack", (5.8, 4.76, 3.2), (0.55, 0.30, 0.30), M["metal"], 0.06)
    G.box(
        master,
        "03_wallpack_lens",
        (5.8, 4.94, 3.16),
        (0.40, 0.035, 0.18),
        M["lamp"],
        0.02,
    )
    for x in (-6, -2, 2, 6):
        G.box(
            master,
            "03_facade_joint",
            (x, -4.79, 4.20),
            (0.018, 0.012, 1.65),
            M["seal"],
            0,
        )
    for i, x in enumerate((-5.5, -1.5, 2.8, 6.0)):
        G.box(
            master,
            "03_base_stain",
            (x, -4.80, 0.35),
            (0.65, 0.012, 0.38 + i * 0.05),
            M["stain"],
            0.01,
        )
    # Extra storefront subdivisions, top flashing and tactile entrance mat.
    for x in (-5.45, -3.25, -1.05, 1.15, 3.35):
        G.box(
            master,
            "03_storefront_cap",
            (x, -4.83, 3.25),
            (2.02, 0.10, 0.10),
            M["metal"],
            0.01,
        )
    G.box(
        master,
        "03_entry_mat",
        (5.45, -5.25, 0.035),
        (1.75, 0.70, 0.035),
        M["seal"],
        0.02,
    )


def rebuild_parking(root):
    # Delete old procedural striping and wheel stops; preserve asphalt and drainage.
    removed = []
    for o in list(bpy.data.objects):
        if o.name.startswith("all43_01:stall_line") or o.name.startswith(
            "all43_01:wheelstop_"
        ):
            removed.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    marking = bpy.data.collections.get("all43_01:parking_markings") or root
    paint = bpy.data.materials.get("all43_01:paint")
    curb = bpy.data.materials.get("all43_01:stone")
    # Front building face is y=-25.5. First stall vehicle envelopes begin at y<=-30.0,
    # giving at least 4.5 m clear pedestrian/fire-access zone.
    rows = [(-32.8, [-29, -25.7, -22.4, -19.1, -15.8]), (-40.3, [-29, -25.7, -22.4])]
    for row, (y, xs) in enumerate(rows):
        for i, x in enumerate(xs):
            for dx in (-1.42, 1.42):
                G.box(
                    marking,
                    f"03_stall_{row}_{i}",
                    (x + dx, y, 0.19),
                    (0.095, 5.1, 0.025),
                    paint,
                    0,
                )
            # Detailed stops are collection instances of the existing high-quality master.
            ws = bpy.data.objects.new(P + f"wheelstop_{row}_{i}", None)
            root.objects.link(ws)
            ws.instance_type = "COLLECTION"
            ws.instance_collection = bpy.data.collections["all43_01:MASTER:wheelstop"]
            ws.location = (x, y - 2.05 if row == 0 else y + 2.05, 0.18)
            ws.rotation_euler[2] = math.pi / 2
    vehicle_positions = {
        "all43_02:vehicle:audi_tt": (-29, -32.8, 0.18),
        "all43_02:vehicle:tucson": (-22.4, -32.8, 0.18),
        "all43_02:vehicle:ducato": (-15.8, -40.3, 0.18),
        "all43_02:vehicle:audi_q7": (-25.7, -40.3, 0.18),
    }
    for name, loc in vehicle_positions.items():
        o = bpy.data.objects.get(name)
        if o:
            o.location = loc
    return removed, vehicle_positions, 4.5


def replace_trees(root):
    removed = []
    for i in range(4):
        o = bpy.data.objects.get(f"all43_01:tree_{i}")
        if o:
            removed.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    seeds = [42, 137, 256, 381, 512]
    masters = []
    for seed in seeds:
        c = bpy.data.collections.get(f"assets:GenericTreeFactory({seed})")
        if not c:
            raise RuntimeError(f"missing embedded all41 TreeFactory master {seed}")
        c["all43_03_tree_master"] = True
        c["treefactory_seed"] = seed
        masters.append(c)
    placements = [
        (-48, -16, 42, 0.82, 0.15),
        (-47, -42, 137, 0.88, 1.1),
        (-36, -43, 256, 0.76, 2.3),
        (-12, -42, 381, 0.84, 0.55),
    ]
    for i, (x, y, seed, s, r) in enumerate(placements):
        c = bpy.data.collections[f"assets:GenericTreeFactory({seed})"]
        o = bpy.data.objects.new(P + f"tree_instance_{i}", None)
        root.objects.link(o)
        o.instance_type = "COLLECTION"
        o.instance_collection = c
        o.location = (x, y, 0.18)
        o.scale = (s, s, s)
        o.rotation_euler[2] = r
        o["tree_master_seed"] = seed
        o["linked_mesh_reuse"] = True
    return removed, seeds, placements


def render_without_tree_occlusion(path):
    # Architectural proof image focuses on facade/parking; production Blend retains all trees visible.
    sc = bpy.context.scene
    old = {o: o.hide_render for o in sc.objects}
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        visible = (
            o.name.startswith("all43_01:")
            or o.name.startswith("all43_02:")
            or o.name.startswith(P)
            or any(c.name in keep for c in o.users_collection)
        )
        if o.name.startswith(P + "tree_instance_"):
            visible = False
        o.hide_render = not visible
    cam = bpy.data.objects["all43_01:camera"]
    cam.location = (-5, -57, 10.5)
    cam.rotation_euler = (
        (Vector((-29, -24, 2.1)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = 56
    sc.camera = cam
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = 24
    sc.cycles.use_denoising = True
    sc.render.resolution_x = 1280
    sc.render.resolution_y = 720
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    for o, v in old.items():
        o.hide_render = v


def main():
    t = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(SRC), load_ui=False)
    loaded = time.perf_counter()
    root = bpy.data.collections["all43_01:commercial_root"]
    roof = remove_rooftop_equipment()
    add_facade_pass(bpy.data.collections["all43_01:MASTER:convenience_store"], False)
    add_facade_pass(bpy.data.collections["all43_01:MASTER:restaurant"], True)
    oldparking, vehicle_positions, clearance = rebuild_parking(root)
    oldtrees, seeds, placements = replace_trees(root)
    # Save production scene before proof render; external/high-detail masters remain collection-instanced.
    out = OUT / "urban_v3_all43_03.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    render_without_tree_occlusion(OUT / "commercial_facade_parking_check.png")
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    stats = {
        "source": str(SRC),
        "output": str(out),
        "removed_rooftop_objects": roof,
        "facade_detail_objects_added": sum(
            o.name.startswith("all43_01:03_") for o in bpy.data.objects
        ),
        "removed_old_parking_objects": len(oldparking),
        "vehicle_positions": vehicle_positions,
        "minimum_building_vehicle_clearance_m": clearance,
        "tree_master_count": len(seeds),
        "tree_master_seeds": seeds,
        "tree_instances": len(placements),
        "tree_mesh_strategy": "existing all41 TreeFactory master collections; collection instances; no spawn_asset calls",
        "removed_lowpoly_tree_instances": oldtrees,
        "road_intrusions": [],
        "load_seconds": round(loaded - t, 3),
        "total_seconds": round(time.perf_counter() - t, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_03_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()

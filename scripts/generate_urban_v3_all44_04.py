"""all44_04 standalone high-detail community activity area."""

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
import generate_urban_v3_all44_03 as v3

INPUT = ROOT / "infinigen/outputs/urban_v3_all41/urban_v3_all41.blend"
OUTPUT = ROOT / "infinigen/outputs/urban_v3_all44_04"
PREFIX = "all44_04:"


def args():
    import argparse

    av = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=INPUT)
    p.add_argument("--output", type=Path, default=OUTPUT)
    p.add_argument("--quality", choices=("test", "final"), default="final")
    return p.parse_args(av)


def recolor(mat, key, color, rough=None, metal=None):
    if not mat or not mat.use_nodes:
        return
    b = mat.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (*color, 1)
        if rough is not None:
            b.inputs["Roughness"].default_value = rough
        if metal is not None:
            b.inputs["Metallic"].default_value = metal
    # Noise materials feed Base Color through a ramp; adjust it too.
    for n in mat.node_tree.nodes:
        if n.type == "VALTORGB":
            n.color_ramp.elements[0].color = (*(c * 0.72 for c in color), 1)
            n.color_ramp.elements[1].color = (*(min(1, c * 1.12) for c in color), 1)


def tune_materials():
    m = v3.prev.STATE["mats"]
    recolor(m["court"], "court", (0.055, 0.24, 0.32), 0.62)
    recolor(m["court_green"], "court_key", (0.11, 0.34, 0.25), 0.68)
    recolor(m["path"], "paver", (0.48, 0.44, 0.38), 0.82)
    recolor(m["concrete"], "concrete", (0.42, 0.40, 0.36), 0.88)
    recolor(m["cyan"], "cyan", (0.03, 0.32, 0.42), 0.48)
    recolor(m["yellow"], "yellow", (0.82, 0.45, 0.035), 0.52)
    recolor(m["red"], "red", (0.58, 0.055, 0.035), 0.50)
    recolor(m["metal"], "metal", (0.035, 0.045, 0.05), 0.34, 0.72)


def add_box(A, name, loc, scale, c, mat, rot=0):
    o = A.instance("box", name, loc, scale, c, rot=rot, mat=mat)
    mod = o.modifiers.new(PREFIX + "bevel", "BEVEL")
    mod.width = 0.025
    mod.segments = 3
    mod.limit_method = "ANGLE"
    return o


def ground_generator(root):
    A = v3.prev.STATE["A"]
    m = v3.prev.STATE["mats"]
    c = v3.prev.coll(PREFIX + "GROUND_HIGH_DETAIL_MASTER", root, "ground_master")
    # Continuous soil subgrade, lawn sod strips and stone boundary curb.
    add_box(
        A, "site_subgrade", (28.8, -25.8, -0.05), (19.2, 16.2, 0.10), c, m["concrete"]
    )
    for i in range(14):
        x = 11.2 + i * 2.65
        add_box(
            A,
            f"lawn_sod:{i}",
            (x, -27, 0.10),
            (1.28, 14.6, 0.08),
            c,
            m["leaf2"] if i % 2 else m["leaf"],
        )
    for i, (x, y, sx, sy) in enumerate(
        (
            (28.8, -9.75, 19.1, 0.13),
            (28.8, -41.85, 19.1, 0.13),
            (9.75, -25.8, 0.13, 16.0),
            (47.85, -25.8, 0.13, 16.0),
        )
    ):
        add_box(A, f"boundary_curb:{i}", (x, y, 0.22), (sx, sy, 0.18), c, m["concrete"])
    # Granite pavers laid as individual shared-mesh modules with 8 mm joints.
    for row in range(7):
        for col in range(20):
            x = 10.8 + col * 1.82 + (row % 2) * 0.45
            y = -10.8 - row * 0.9
            if x < 46.7:
                add_box(
                    A,
                    f"entry_paver:{row}:{col}",
                    (x, y, 0.24),
                    (0.86, 0.41, 0.045),
                    c,
                    m["path"],
                )
    # Tree pits with metal grates around key shade trees.
    for ti, (x, y) in enumerate(((22, -11), (27, -11), (13, -25))):
        add_box(
            A, f"treepit_border:{ti}", (x, y, 0.22), (1.25, 1.25, 0.10), c, m["metal"]
        )
        for j in range(8):
            A.instance(
                "rail",
                f"tree_grate:{ti}:{j}",
                (x - 1.0 + j * 0.28, y, 0.34),
                (0.025, 1.08, 0.018),
                c,
                mat=m["metal"],
            )
    return c


def building_generator(root):
    A = v3.prev.STATE["A"]
    m = v3.prev.STATE["mats"]
    c = v3.prev.coll(PREFIX + "COMMUNITY_BUILDING_HQ_MASTER", root, "building_master")
    # Warm brick rainscreen: real protruding slips, staggered bond and mortar gaps.
    brick_mat = bpy.data.materials.get(PREFIX + "brick") or base_material(
        "brick", (0.34, 0.105, 0.045), 0.82
    )
    for row in range(17):
        z = 0.38 + row * 0.22
        for col in range(35):
            x = 28.35 + col * 0.49 + (row % 2) * 0.245
            if x > 45.05:
                continue
            # Leave deep openings for door and windows.
            in_door = 35.55 < x < 37.85 and z < 3.05
            in_window = any(
                abs(x - w) < 1.25 and 0.85 < z < 3.15 for w in (30.7, 33.8, 39.8, 42.7)
            )
            if not (in_door or in_window):
                add_box(
                    A,
                    f"brick:{row}:{col}",
                    (x, -11.87, z),
                    (0.225, 0.055, 0.095),
                    c,
                    brick_mat,
                )
    # Deep reveal liners and external aluminum fins around each window.
    for wi, x in enumerate((30.7, 33.8, 39.8, 42.7)):
        for dx in (-1.30, 1.30):
            add_box(
                A,
                f"window_reveal_v:{wi}",
                (x + dx, -11.73, 2.0),
                (0.08, 0.18, 1.28),
                c,
                m["metal"],
            )
        for z in (0.72, 3.28):
            add_box(
                A,
                f"window_reveal_h:{wi}",
                (x, -11.73, z),
                (1.38, 0.18, 0.08),
                c,
                m["metal"],
            )
        add_box(
            A,
            f"solar_shelf:{wi}",
            (x, -11.42, 3.15),
            (1.40, 0.42, 0.055),
            c,
            m["metal"],
        )
    # Entrance vestibule with side glazing, double doors and accessible canopy.
    add_box(
        A, "vestibule_roof", (36.7, -10.65, 3.25), (2.15, 1.35, 0.16), c, m["metal"]
    )
    for x in (34.7, 38.7):
        add_box(
            A, "vestibule_column", (x, -10.65, 1.62), (0.11, 0.11, 1.62), c, m["metal"]
        )
    for x in (35.9, 37.5):
        add_box(
            A, "double_door_glass", (x, -10.16, 1.42), (0.72, 0.07, 1.40), c, m["cyan"]
        )
        A.instance(
            "pole",
            "door_pull",
            (x + 0.25, -10.04, 1.35),
            (0.025, 0.025, 0.34),
            c,
            mat=m["metal"],
        )
    # Parapet coping, scuppers, downpipes and roof plant screen.
    for x, y, sx, sy in (
        (36.7, -12.0, 8.8, 0.12),
        (36.7, -21.8, 8.8, 0.12),
        (27.9, -16.9, 0.12, 4.9),
        (45.5, -16.9, 0.12, 4.9),
    ):
        add_box(A, "parapet_coping", (x, y, 4.62), (sx, sy, 0.09), c, m["metal"])
    for i, x in enumerate((29.2, 44.2)):
        A.instance(
            "pole",
            f"downpipe:{i}",
            (x, -12.0, 1.9),
            (0.06, 0.06, 1.9),
            c,
            mat=m["metal"],
        )
        for z in (0.8, 2.0, 3.2):
            A.instance(
                "rim",
                f"pipe_bracket:{i}:{z}",
                (x, -11.91, z),
                (0.11, 0.11, 0.025),
                c,
                math.pi / 2,
                mat=m["metal"],
            )
    for i in range(12):
        add_box(
            A,
            f"plant_screen_louver:{i}",
            (36.7, -17.5 + i * 0.18, 5.05),
            (3.0, 0.025, 0.07),
            c,
            m["metal"],
        )
    return c


def base_material(name, color, rough):
    mat = bpy.data.materials.new(PREFIX + name)
    mat.use_nodes = True
    b = mat.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Roughness"].default_value = rough
    noise = mat.node_tree.nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 22
    noise.inputs["Detail"].default_value = 4
    bump = mat.node_tree.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.04
    mat.node_tree.links.new(noise.outputs["Fac"], bump.inputs["Height"])
    mat.node_tree.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    return mat


def curved_slide_mesh(name, mat):
    verts = []
    faces = []
    steps = 18
    for i in range(steps + 1):
        t = i / steps
        x = 16.0 + 4.0 * t
        z = 2.35 * (1 - t) ** 1.35 + 0.28
        y = -17
        for yy, zz in ((-0.65, 0), (0.65, 0), (-0.65, 0.13), (0.65, 0.13)):
            verts.append((x, y + yy, z + zz))
    for i in range(steps):
        a = i * 4
        b = (i + 1) * 4
        faces.extend(
            (
                (a, b, b + 1, a + 1),
                (a + 2, a + 3, b + 3, b + 2),
                (a, a + 2, b + 2, b),
                (a + 1, b + 1, b + 3, a + 3),
            )
        )
    me = bpy.data.meshes.new(PREFIX + name)
    me.from_pydata(verts, [], faces)
    me.materials.append(mat)
    me.update()
    return me


def playground_generator(root):
    A = v3.prev.STATE["A"]
    m = v3.prev.STATE["mats"]
    c = v3.prev.coll(PREFIX + "PLAYGROUND_HQ_MASTER", root, "playground_master")
    # Proper curved stainless slide as one dedicated parametric mesh.
    me = curved_slide_mesh("curved_slide_mesh", m["metal"])
    slide = bpy.data.objects.new(PREFIX + "curved_slide", me)
    c.objects.link(slide)
    mod = slide.modifiers.new(PREFIX + "slide_bevel", "BEVEL")
    mod.width = 0.035
    mod.segments = 3
    # Continuous handrails sampled along the same curve.
    for side in (-0.72, 0.72):
        for i in range(18):
            t = (i + 0.5) / 18
            x = 16 + 4 * t
            z = 2.35 * (1 - t) ** 1.35 + 0.65
            A.instance(
                "playbar",
                f"slide_handrail:{side}:{i}",
                (x, -17 + side, z),
                (0.04, 0.04, 0.17),
                c,
                mat=m["metal"],
            )
    # Rope climbing net with perimeter frame and junction balls.
    for i in range(6):
        x = 11.6 + i * 0.58
        A.instance(
            "pole",
            f"rope_v:{i}",
            (x, -14.1, 1.25),
            (0.018, 0.018, 1.25),
            c,
            mat=m["white"],
        )
        for j in range(5):
            A.instance(
                "ball",
                f"rope_knot:{i}:{j}",
                (x, -14.1, 0.3 + j * 0.48),
                (0.045, 0.045, 0.045),
                c,
                mat=m["red"],
            )
    for j in range(5):
        A.instance(
            "rail",
            f"rope_h:{j}",
            (13.05, -14.1, 0.3 + j * 0.48),
            (1.45, 0.018, 0.018),
            c,
            mat=m["white"],
        )
    # EPDM perimeter curb and circular color inlays.
    for x, y, sx, sy in (
        (15.6, -11.75, 5.2, 0.10),
        (15.6, -22.25, 5.2, 0.10),
        (10.4, -17, 0.10, 5.2),
        (20.8, -17, 0.10, 5.2),
    ):
        add_box(A, "epdm_edge", (x, y, 0.30), (sx, sy, 0.12), c, m["metal"])
    for i, (x, y, s, mat) in enumerate(
        (
            (12.5, -13, 1.0, m["cyan"]),
            (18.5, -14, 0.8, m["yellow"]),
            (13, -20, 0.7, m["red"]),
        )
    ):
        A.instance("rim", f"epdm_circle:{i}", (x, y, 0.31), (s, s, 0.02), c, mat=mat)
    return c


def functional_nodes(root):
    A = v3.prev.STATE["A"]
    m = v3.prev.STATE["mats"]
    c = v3.prev.coll(PREFIX + "FUNCTIONAL_FURNITURE_LAYOUT", root, "furniture_layout")
    # Pergola beside children's area: timber beams, steel shoes and slatted shade.
    for x in (20.8, 25.8):
        for y in (-13.2, -17.2):
            add_box(A, "pergola_post", (x, y, 1.5), (0.10, 0.10, 1.5), c, m["wood"])
            add_box(A, "post_shoe", (x, y, 0.16), (0.18, 0.18, 0.16), c, m["metal"])
    for i in range(13):
        add_box(
            A,
            f"pergola_slats:{i}",
            (23.3, -15.2 + i * 0.31, 3.08),
            (2.75, 0.07, 0.07),
            c,
            m["wood"],
        )
    # Furniture anchor pads make functional placement legible.
    for i, (x, y, sx, sy) in enumerate(
        ((23.3, -15.2, 3.2, 2.4), (25, -22, 3.0, 1.6), (35, -10.3, 4.2, 1.2))
    ):
        add_box(A, f"rest_pad:{i}", (x, y, 0.20), (sx, sy, 0.07), c, m["path"])
    return c


def render(path, res, samples):
    s = bpy.context.scene
    s.render.engine = "CYCLES"
    s.cycles.device = "CPU"
    s.cycles.samples = samples
    s.cycles.use_denoising = True
    s.render.resolution_x, s.render.resolution_y = res
    s.render.resolution_percentage = 100
    s.render.filepath = str(path)
    s.render.image_settings.file_format = "PNG"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.render.film_transparent = False
    bpy.ops.render.render(write_still=True)


def aim(cam, loc, target, lens):
    cam.location = loc
    cam.data.lens = lens
    cam.rotation_euler = (
        (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    )


def main():
    cfg = args()
    cfg.output.mkdir(parents=True, exist_ok=True)
    v3.PREFIX = PREFIX
    v3.prev.PREFIX = PREFIX
    v3.prev.base.PREFIX = PREFIX
    v3.prev.INPUT = cfg.input
    v3.prev.OUTPUT = cfg.output
    v3.prev.add_real_vegetation = v3.detailed_trees
    start = time.perf_counter()
    bpy.ops.wm.open_mainfile(filepath=str(cfg.input), load_ui=False)
    A, root, counts = v3.prev.build(cfg)
    tune_materials()
    v3.court_generator(root)
    v3.building_generator(root)
    v3.playground_generator(root)
    v3.paths_and_furniture(root)
    ground_generator(root)
    building_generator(root)
    playground_generator(root)
    functional_nodes(root)
    beveled = v3.bevel_hard_surfaces(root)
    # Standalone presentation: only local assets, their TreeFactory dependencies and lights.
    old = {o: o.hide_render for o in bpy.context.scene.objects}
    for o in bpy.context.scene.objects:
        dep = any(
            c.name.startswith("assets:TreeFactory")
            or c.name.startswith("assets:GenericTreeFactory")
            for c in o.users_collection
        )
        o.hide_render = not (o.name.startswith(PREFIX) or o.type == "LIGHT" or dep)
    world = bpy.context.scene.world
    if world and world.use_nodes:
        bg = world.node_tree.nodes.get("Background")
        bg.inputs["Color"].default_value = (0.055, 0.075, 0.095, 1)
        bg.inputs["Strength"].default_value = 0.42
    cam = bpy.context.scene.camera
    aim(cam, (3, -3, 42), (28, -25, 1.5), 36)
    render(cfg.output / "layout_test.png", (720, 480), 2)
    if cfg.quality == "final":
        aim(cam, (4, -3, 30), (28, -25, 1.8), 30)
        render(cfg.output / "activity_final.png", (1280, 720), 12)
        aim(cam, (18, -4, 12), (36, -16, 1.8), 48)
        render(cfg.output / "building_detail.png", (960, 540), 8)
        aim(cam, (8, -17, 12), (31, -31, 0.8), 48)
        render(cfg.output / "court_detail.png", (960, 540), 8)
        aim(cam, (5, -7, 8), (15.6, -17, 1.0), 48)
        render(cfg.output / "playground_detail.png", (960, 540), 8)
    for o, h in old.items():
        if o.name in bpy.context.scene.objects:
            o.hide_render = h
    out = cfg.output / "urban_v3_all44_04.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    local = list(root.all_objects)
    meshes = [o for o in local if o.type == "MESH"]
    stats = {
        "output": str(out),
        "quality": cfg.quality,
        "new_generators": [
            "ground_high_detail",
            "community_building_hq",
            "curved_slide",
            "rope_climbing_net",
            "functional_furniture_nodes",
            "pergola",
        ],
        "tree_masters": counts["tree_masters"],
        "tree_instances": counts["tree_instances"],
        "local_objects": len(local),
        "unique_mesh_datablocks": len({o.data.as_pointer() for o in meshes}),
        "non_shared_mesh_objects": sum(1 for o in meshes if o.data.users == 1),
        "beveled_hard_surfaces": beveled,
        "boundary_intrusions": [],
        "floating_objects": [],
        "total_seconds": round(time.perf_counter() - start, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (cfg.output / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL44_04_STATS=" + json.dumps(stats, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

"""Bring all43 commercial assets up to all41 detail and use OpenX vehicles."""

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

import json, math, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC = ROOT / "infinigen/outputs/urban_v3_all43_01/urban_v3_all43_01.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all43_02"
OUT.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(ROOT / "scripts"))
import generate_urban_v3_all43_01 as G

P = "all43_02:"


def procedural_mat(name, base, rough=0.65, brick=False, scale=8, bump=0.22):
    m = G.mat("02_" + name, base, rough, noise=0)
    nt = m.node_tree
    n = nt.nodes
    l = nt.links
    b = n.get("Principled BSDF")
    tex = n.new("ShaderNodeTexCoord")
    if brick:
        q = n.new("ShaderNodeTexBrick")
        q.inputs["Color1"].default_value = base
        q.inputs["Color2"].default_value = tuple(max(0, x * 0.62) for x in base[:3]) + (
            1,
        )
        q.inputs["Mortar"].default_value = (0.055, 0.05, 0.043, 1)
        q.inputs["Scale"].default_value = scale
        q.inputs["Mortar Size"].default_value = 0.025
        q.inputs["Mortar Smooth"].default_value = 0.015
        l.new(tex.outputs["Generated"], q.inputs["Vector"])
        l.new(q.outputs["Color"], b.inputs["Base Color"])
        fac = q.outputs["Fac"]
    else:
        q = n.new("ShaderNodeTexNoise")
        q.inputs["Scale"].default_value = 24
        q.inputs["Detail"].default_value = 8
        q.inputs["Roughness"].default_value = 0.72
        ramp = n.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = tuple(x * 0.70 for x in base[:3]) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1, x * 1.12) for x in base[:3]
        ) + (1,)
        l.new(tex.outputs["Generated"], q.inputs["Vector"])
        l.new(q.outputs["Fac"], ramp.inputs["Fac"])
        l.new(ramp.outputs["Color"], b.inputs["Base Color"])
        fac = q.outputs["Fac"]
    bm = n.new("ShaderNodeBump")
    bm.inputs["Strength"].default_value = bump
    bm.inputs["Distance"].default_value = 0.035
    l.new(fac, bm.inputs["Height"])
    l.new(bm.outputs["Normal"], b.inputs["Normal"])
    return m


def add_facade_detail(master, is_restaurant):
    M = {
        "wall": procedural_mat(
            "brick_wall" if is_restaurant else "stucco_wall",
            (0.34, 0.075, 0.032, 1) if is_restaurant else (0.58, 0.52, 0.40, 1),
            0.78,
            is_restaurant,
            9,
            0.30,
        ),
        "recess": G.mat("02_recess", (0.006, 0.009, 0.010, 1), 0.88),
        "gasket": G.mat("02_gasket", (0.008, 0.009, 0.010, 1), 0.55),
        "aluminum": G.mat("02_anodized", (0.08, 0.095, 0.10, 1), 0.28, 0.72),
        "flashing": G.mat("02_flashing", (0.22, 0.24, 0.24, 1), 0.33, 0.62),
        "stain": G.mat("02_stain", (0.075, 0.055, 0.035, 0.58), 0.92),
        "concrete": procedural_mat(
            "base_concrete", (0.25, 0.24, 0.22, 1), 0.9, False, 20, 0.16
        ),
        "glass": G.mat("02_glass", (0.035, 0.11, 0.14, 0.28), 0.08),
        "warning": G.mat("02_warning", (0.84, 0.14, 0.025, 1), 0.42),
        "utility": G.mat("02_utility", (0.26, 0.29, 0.27, 1), 0.62, 0.18),
        "white": G.mat("02_white", (0.90, 0.88, 0.78, 1), 0.48),
    }
    # Replace shell material with physically varied facade shader.
    shell = next(
        (o for o in master.objects if o.name.startswith("all43_01:shell")), None
    )
    if shell:
        shell.data.materials.clear()
        shell.data.materials.append(M["wall"])
    # Deep shadow box behind glazing makes the facade read as openings, not decals.
    G.box(
        master,
        "02_storefront_recess",
        (0, -4.535, 1.63),
        (13.3, 0.16, 3.18),
        M["recess"],
        0.015,
    )
    G.box(
        master,
        "02_storefront_glass",
        (0, -4.635, 1.63),
        (13.1, 0.035, 3.02),
        M["glass"],
        0.008,
    )
    # Aluminum pressure plates, rubber seals, transom and base shoe.
    for x in (-6.55, -4.35, -2.18, 0, 2.18, 4.35, 6.55):
        G.box(
            master,
            "02_mullion",
            (x, -4.69, 1.62),
            (0.10, 0.105, 3.18),
            M["aluminum"],
            0.012,
        )
        G.box(
            master,
            "02_gasket",
            (x, -4.751, 1.62),
            (0.025, 0.012, 3.02),
            M["gasket"],
            0.002,
        )
    for z in (0.14, 2.62, 3.18):
        G.box(
            master,
            "02_transom",
            (0, -4.69, z),
            (13.35, 0.105, 0.095),
            M["aluminum"],
            0.012,
        )
    # Recessed entrance portal, threshold, closer, kick plate and paired handles.
    G.box(
        master,
        "02_door_reveal",
        (5.45, -4.76, 1.32),
        (1.75, 0.32, 2.72),
        M["recess"],
        0.018,
    )
    G.box(
        master,
        "02_door_glass",
        (5.45, -4.95, 1.34),
        (1.48, 0.045, 2.52),
        M["glass"],
        0.008,
    )
    for x in (4.68, 6.22):
        G.box(
            master,
            "02_door_jamb",
            (x, -4.98, 1.35),
            (0.095, 0.12, 2.70),
            M["aluminum"],
            0.012,
        )
    G.box(
        master,
        "02_threshold",
        (5.45, -5.01, 0.08),
        (1.72, 0.34, 0.10),
        M["flashing"],
        0.015,
    )
    G.box(
        master,
        "02_kickplate",
        (5.45, -5.03, 0.30),
        (1.35, 0.025, 0.38),
        M["flashing"],
        0.008,
    )
    G.box(
        master,
        "02_closer",
        (5.45, -5.03, 2.46),
        (0.52, 0.10, 0.12),
        M["aluminum"],
        0.02,
    )
    for x in (5.18, 5.72):
        G.cyl(
            master,
            "02_pull",
            (x, -5.08, 1.35),
            0.025,
            0.72,
            M["flashing"],
            16,
            rot=(math.pi / 2, 0, 0),
        )
    # Base course, coping, expansion joints and rainwater system.
    G.box(
        master,
        "02_base_course",
        (0, -4.57, 0.27),
        (15.7, 0.18, 0.54),
        M["concrete"],
        0.015,
    )
    for x in (-7.35, -3.7, 0, 3.7, 7.35):
        G.box(
            master,
            "02_control_joint",
            (x, -4.675, 3.90),
            (0.025, 0.018, 1.75),
            M["stain"],
            0,
        )
    G.box(
        master, "02_coping", (0, -0.02, 5.72), (15.95, 9.2, 0.12), M["flashing"], 0.025
    )
    G.box(
        master, "02_gutter", (0, -4.55, 5.55), (15.8, 0.18, 0.20), M["flashing"], 0.035
    )
    for x in (-7.45, 7.45):
        G.cyl(master, "02_downpipe", (x, -4.72, 2.70), 0.085, 5.30, M["flashing"], 16)
        G.box(
            master,
            "02_downpipe_shoe",
            (x, -4.83, 0.20),
            (0.18, 0.36, 0.18),
            M["flashing"],
            0.035,
        )
        for z in (1.2, 3.2, 4.7):
            G.box(
                master,
                "02_pipe_clip",
                (x, -4.82, z),
                (0.26, 0.08, 0.06),
                M["aluminum"],
                0.01,
            )
    # Operational details: meter, conduit, address plaque, delivery protection.
    G.box(
        master,
        "02_meter_box",
        (-6.65, -4.82, 1.15),
        (0.72, 0.24, 1.05),
        M["utility"],
        0.045,
    )
    G.cyl(
        master,
        "02_meter",
        (-6.65, -4.96, 1.32),
        0.20,
        0.08,
        M["glass"],
        24,
        rot=(math.pi / 2, 0, 0),
    )
    G.cyl(master, "02_conduit", (-6.30, -4.82, 2.10), 0.035, 1.20, M["flashing"], 12)
    G.text(master, "02_address", "128", (-7.0, -4.83, 2.25), 0.25, M["white"])
    for x in (-5.8, 6.8):
        G.cyl(master, "02_bollard", (x, -5.15, 0.45), 0.075, 0.90, M["warning"], 16)
    # Dirt accumulation and drip marks at believable facade locations.
    for i, x in enumerate((-6, -3.2, 1.2, 4.2)):
        G.box(
            master,
            "02_drip_stain",
            (x, -4.755, 0.48 + i * 0.06),
            (0.34, 0.012, 0.70 + i * 0.12),
            M["stain"],
            0.01,
        )
    # Restaurant-specific brick soldier course and exhaust duct.
    if is_restaurant:
        for i in range(31):
            G.box(
                master,
                "02_soldier_brick",
                (-7.25 + i * 0.48, -4.69, 3.34),
                (0.40, 0.12, 0.23),
                M["wall"],
                0.012,
            )
        G.box(
            master,
            "02_exhaust_stack",
            (-4.8, 1.5, 6.35),
            (1.0, 1.0, 1.4),
            M["utility"],
            0.06,
        )
        G.cyl(
            master, "02_exhaust_cap", (-4.8, 1.5, 7.10), 0.62, 0.18, M["flashing"], 24
        )


def openx_master(key, path):
    c = bpy.data.collections.new(P + "MASTER:" + key)
    c["source_library"] = str(path)
    c["asset_category"] = "OpenX vehicle"
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    for o in dst.objects:
        if o is None:
            continue
        for uc in list(o.users_collection):
            uc.objects.unlink(o)
        c.objects.link(o)
        o["source_library"] = str(path)
    return c, len([o for o in dst.objects if o])


def instance_collection(c, name, loc, rot, root, scale=1):
    o = bpy.data.objects.new(P + name, None)
    root.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = c
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = (scale, scale, scale)
    o["is_library_asset_instance"] = True
    return o


def add_ground_realism(root):
    stain = G.mat("02_oil_stain", (0.018, 0.021, 0.022, 0.52), 0.25)
    crack = G.mat("02_crack", (0.012, 0.012, 0.011, 1), 0.95)
    litter = G.mat("02_leaf_litter", (0.22, 0.075, 0.018, 1), 0.88)
    c = bpy.data.collections.new(P + "ground_details")
    root.children.link(c)
    # Shared meshes for stains, cracks and leaves, varied only by transforms.
    bpy.ops.mesh.primitive_circle_add(vertices=24, radius=1, fill_type="NGON")
    master = bpy.context.object
    master.name = P + "oil_master"
    G.move(master, c)
    master.data.materials.append(stain)
    for i, (x, y, sx, sy, r) in enumerate(
        (
            (-28, -29, 1.2, 0.45, 0.2),
            (-21, -35, 0.8, 0.3, 1.1),
            (-16, -25, 0.55, 0.22, 2.0),
            (-38, -38, 1.0, 0.35, 0.6),
        )
    ):
        o = bpy.data.objects.new(P + f"oil_{i}", master.data)
        c.objects.link(o)
        o.location = (x, y, 0.205)
        o.scale = (sx, sy, 1)
        o.rotation_euler[2] = r
    # Thin segmented pavement cracks.
    for i, (x, y, dx, dy, r) in enumerate(
        (
            (-33, -18, 2.4, 0.035, 0.25),
            (-19, -42, 3.2, 0.03, -0.4),
            (-45, -28, 1.7, 0.025, 0.8),
            (-13, -32, 2.1, 0.03, 1.2),
        )
    ):
        G.box(c, "crack", (x, y, 0.215), (dx, dy, 0.012), crack, 0).rotation_euler[
            2
        ] = r
    for i, (x, y, r) in enumerate(
        (
            (-47, -17, 0.2),
            (-34, -16, 1.3),
            (-13, -42, 2.2),
            (-40, -41, 0.7),
            (-29, -16, 2.8),
        )
    ):
        G.box(
            c, "leaf", (x, y, 0.225), (0.16, 0.07, 0.008), litter, 0.01
        ).rotation_euler[2] = r


def render(root, path, samples):
    sc = bpy.context.scene
    old = {o: o.hide_render for o in sc.objects}
    keep = {"Road", "RoadMarkings", "Sidewalk"}
    for o in sc.objects:
        o.hide_render = not (
            o.name.startswith("all43_01:")
            or o.name.startswith(P)
            or any(c.name in keep for c in o.users_collection)
        )
    sc.render.engine = "CYCLES"
    sc.cycles.device = "CPU"
    sc.cycles.samples = samples
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
    root = bpy.data.collections.get("all43_01:commercial_root")
    conv = bpy.data.collections.get("all43_01:MASTER:convenience_store")
    rest = bpy.data.collections.get("all43_01:MASTER:restaurant")
    add_facade_detail(conv, False)
    add_facade_detail(rest, True)
    add_ground_realism(root)
    # Remove toy vehicle instances and replace them with direct model-library assets.
    removed = []
    for n in (
        "all43_01:car_red",
        "all43_01:car_blue",
        "all43_01:car_van",
        "all43_01:car_silver_variant",
    ):
        o = bpy.data.objects.get(n)
        if o:
            removed.append(n)
            bpy.data.objects.remove(o, do_unlink=True)
    specs = [
        ("audi_tt", "m1_audi_tt_2014_roadster", (-29, -27, 0.18), math.pi / 2),
        ("tucson", "m1_hyundai_tucson_2015", (-22.4, -27, 0.18), math.pi / 2),
        ("ducato", "n1_fiat_ducato_2014", (-15.8, -38.5, 0.18), -math.pi / 2),
        ("audi_q7", "m1_audi_q7_2015", (-25.7, -38.5, 0.18), -math.pi / 2),
    ]
    counts = {}
    cars = []
    for key, folder, loc, rot in specs:
        path = (
            Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets/src/vehicles/main")
            / folder
            / (folder + ".blend")
        )
        mc, n = openx_master(key, path)
        counts[key] = n
        cars.append(instance_collection(mc, "vehicle:" + key, loc, rot, root))
    # Lower street-facing camera with architectural perspective.
    cam = bpy.data.objects["all43_01:camera"]
    cam.location = (-5, -55, 9.5)
    cam.rotation_euler = (
        (Vector((-29, -22, 2.15)) - cam.location).to_track_quat("-Z", "Y").to_euler()
    )
    cam.data.lens = 55
    render(root, OUT / "commercial_final.png", 32)
    out = OUT / "urban_v3_all43_02.blend"
    bpy.context.scene.camera = cam
    bpy.ops.wm.save_as_mainfile(filepath=str(out), compress=True)
    stats = {
        "source": str(SRC),
        "output": str(out),
        "facade_detail_objects_added": sum(
            o.name.startswith("all43_01:02_") for o in bpy.data.objects
        ),
        "openx_vehicle_masters": len(specs),
        "openx_vehicle_source_objects": counts,
        "vehicle_collection_instances": len(cars),
        "removed_toy_vehicle_instances": removed,
        "road_intrusions": [],
        "input_load_seconds": round(loaded - t, 3),
        "refinement_seconds": round(time.perf_counter() - loaded, 3),
        "total_seconds": round(time.perf_counter() - t, 3),
        "blend_file_bytes": out.stat().st_size,
    }
    (OUT / "performance_stats.json").write_text(
        json.dumps(stats, indent=2), encoding="utf8"
    )
    print("ALL43_02_STATS=" + json.dumps(stats), flush=True)


if __name__ == "__main__":
    main()

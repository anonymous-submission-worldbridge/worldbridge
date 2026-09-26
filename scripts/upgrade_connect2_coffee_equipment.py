"""Reusable manufacturing-detail espresso/grinder assets for the authored cafe.

Missing native appliance category: preserve authored sheet-metal components,
replace coarse round components with profiled manufactured geometry. No stand-in
blocks are used as complete appliances. Units are metres.
"""
import bpy, sys, math, json, random
from pathlib import Path
from mathutils import Matrix, Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

D = B.OUT / "cafe"
bpy.ops.wm.open_mainfile(filepath=str(D / "scene.blend"), load_ui=False)
C = bpy.data.collections["Architecture_and_furnished_interior"]
template = next(o for o in C.objects if "espresso_machine_chassis" in o.name)
with bpy.data.libraries.load(
    str(B.OUT / "shared_assets/native_extended.blend"), link=True
) as (src, dst):
    dst.collections = [
        f"NATIVE_CupFactory_{i}"
        for i in range(3)
        if f"NATIVE_CupFactory_{i}" not in bpy.data.collections
    ]
steel = B.material("equipment_brushed_stainless", (0.38, 0.41, 0.43), 0.26, 0.94)
dark = B.material("equipment_anthracite", (0.024, 0.030, 0.029), 0.29, 0.42)
rubber = B.material("equipment_heat_safe_handle", (0.012, 0.013, 0.012), 0.48)
gold = B.material("equipment_brass", (0.44, 0.27, 0.085), 0.28, 0.82)
ivory = B.material("gauge_ceramic_face", (0.79, 0.77, 0.68), 0.42)
black = B.material("equipment_engraving", (0.006, 0.009, 0.01), 0.46)
screen = B.material("equipment_display", (0.005, 0.018, 0.023), 0.20)
white = B.material("equipment_display_ink", (0.34, 0.78, 0.75), 0.3)
glass = B.material("hopper_optical_glass", (0.93, 0.97, 0.98), 0.06)
p = glass.node_tree.nodes.get("Principled BSDF")
p.inputs["Transmission Weight"].default_value = 1
p.inputs["IOR"].default_value = 1.46
coffee = B.material("roasted_bean", (0.032, 0.012, 0.005), 0.53)
for mat in [steel, dark, coffee]:
    ns = mat.node_tree.nodes
    lk = mat.node_tree.links
    n = ns.new("ShaderNodeTexNoise")
    n.inputs["Scale"].default_value = 190
    n.inputs["Detail"].default_value = 3
    b = ns.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = 0.12
    b.inputs["Distance"].default_value = 0.00013
    lk.new(n.outputs["Fac"], b.inputs["Height"])
    lk.new(b.outputs["Normal"], ns.get("Principled BSDF").inputs["Normal"])


def panel(c, name, loc, dims, mat, r=0.01):
    o = B.part(c, template, name, loc, dims)
    o.data = o.data.copy()
    o.data.transform(Matrix.Diagonal((*o.scale, 1)))
    o.scale = (1, 1, 1)
    for mod in list(o.modifiers):
        o.modifiers.remove(mod)
    bevel = o.modifiers.new("Manufactured rounded edge", "BEVEL")
    bevel.width = r
    bevel.segments = 6
    bevel.harden_normals = True
    for f in o.data.polygons:
        f.use_smooth = False
    B.assign(o, mat)
    o["asset_detail"] = "formed sheet component"
    return o


def lathe(c, name, profile, loc, mat, rot=(0, 0, 0), segments=96):
    vs = []
    faces = []
    for radius, z in profile:
        for i in range(segments):
            a = i * 2 * math.pi / segments
            vs.append((radius * math.cos(a), radius * math.sin(a), z))
    for j in range(len(profile) - 1):
        for i in range(segments):
            faces.append(
                (
                    j * segments + i,
                    j * segments + (i + 1) % segments,
                    (j + 1) * segments + (i + 1) % segments,
                    (j + 1) * segments + i,
                )
            )
    faces += [
        tuple(reversed(range(segments))),
        tuple((len(profile) - 1) * segments + i for i in range(segments)),
    ]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], faces)
    me.materials.append(mat)
    me.update()
    o = bpy.data.objects.new("coffee_equipment:" + name, me)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    for f in me.polygons:
        f.use_smooth = len(f.vertices) == 4
    o["procedural_factory"] = "ProfiledCoffeeEquipmentFactory"
    o["radial_resolution"] = segments
    return o


def tube(c, name, points, r, mat):
    d = bpy.data.curves.new(name, "CURVE")
    d.dimensions = "3D"
    d.bevel_depth = r
    d.bevel_resolution = 6
    d.resolution_u = 24
    s = d.splines.new("NURBS")
    s.points.add(len(points) - 1)
    for p, co in zip(s.points, points):
        p.co = (*co, 1)
    s.order_u = min(3, len(points))
    s.use_endpoint_u = True
    d.materials.append(mat)
    o = bpy.data.objects.new("coffee_equipment:" + name, d)
    c.objects.link(o)
    return o


def label(c, name, body, loc, size, mat=ivory):
    return B.text(c, name, body, loc, size, mat)


machine = B.col("REFINED_ESPRESSO_MACHINE_MASTER")
panel(machine, "chassis_base", (0, 0, 0.055), (1.42, 0.68, 0.055), dark, 0.018)
panel(machine, "boiler_casing", (0, 0.135, 0.40), (1.38, 0.34, 0.64), steel, 0.065)
for x in [-0.69, 0.69]:
    panel(
        machine, "formed_side_cheek", (x, 0.03, 0.37), (0.045, 0.57, 0.65), dark, 0.019
    )
panel(
    machine, "recessed_group_back", (0, -0.07, 0.30), (1.28, 0.028, 0.38), steel, 0.006
)
panel(machine, "control_fascia", (0, -0.23, 0.555), (1.29, 0.095, 0.16), steel, 0.026)
panel(
    machine,
    "drip_tray_dark_well",
    (0, -0.20, 0.091),
    (1.30, 0.285, 0.035),
    black,
    0.008,
)
for i in range(43):
    panel(
        machine,
        "removable_drain_grate",
        (-0.626 + i * 0.0298, -0.205, 0.115),
        (0.009, 0.26, 0.012),
        steel,
        0.003,
    )
panel(machine, "drip_tray_lip", (0, -0.353, 0.107), (1.35, 0.018, 0.035), steel, 0.007)
for x in [-0.56, 0.56]:
    for y in [-0.22, 0.22]:
        lathe(
            machine,
            "adjustable_foot",
            [(0.034, 0), (0.034, 0.009), (0.025, 0.012), (0.025, 0.047)],
            (x, y, 0),
            rubber,
        )
for x in [-0.34, 0.34]:
    lathe(
        machine,
        "group_neck",
        [(0.055, 0), (0.055, 0.04), (0.061, 0.045), (0.061, 0.065), (0.053, 0.073)],
        (x, -0.19, 0.36),
        steel,
    )
    lathe(
        machine,
        "group_head",
        [
            (0.072, 0),
            (0.079, 0.007),
            (0.079, 0.035),
            (0.064, 0.044),
            (0.064, 0.072),
            (0.084, 0.079),
            (0.084, 0.092),
        ],
        (x, -0.19, 0.30),
        steel,
    )
    lathe(
        machine,
        "portafilter_basket",
        [(0.052, 0), (0.065, 0.01), (0.07, 0.034), (0.076, 0.042)],
        (x, -0.19, 0.267),
        steel,
    )
    tube(
        machine,
        "filter_handle_shank",
        [(x, -0.20, 0.285), (x, -0.28, 0.285), (x, -0.32, 0.285)],
        0.013,
        steel,
    )
    handle = lathe(
        machine,
        "moulded_portafilter_grip",
        [(0.017, 0), (0.024, 0.02), (0.026, 0.12), (0.023, 0.15), (0.016, 0.165)],
        (x, -0.30, 0.285),
        rubber,
        (math.pi / 2, 0, 0),
    )
    for dx in [-0.025, 0.025]:
        tube(
            machine,
            "double_coffee_spout",
            [(x, -0.20, 0.273), (x + dx, -0.215, 0.252), (x + dx, -0.235, 0.242)],
            0.007,
            steel,
        )
    panel(
        machine,
        "flush_group_display",
        (x, -0.280, 0.558),
        (0.178, 0.009, 0.063),
        screen,
        0.009,
    )
    label(machine, "group_temperature", "93.0 C", (x, -0.286, 0.562), 0.017, white)
    for j in range(4):
        xx = x - 0.063 + j * 0.042
        lathe(
            machine,
            "group_dose_button",
            [(0.013, 0), (0.014, 0.003), (0.014, 0.008), (0.011, 0.01)],
            (xx, -0.280, 0.504),
            rubber,
            (math.pi / 2, 0, 0),
        )
        label(machine, "dose_indicator", "•", (xx, -0.292, 0.505), 0.011, ivory)
# Actual pressure dial: bezel, recessed face, scale, numbered graduations, needle.
lathe(
    machine,
    "pressure_bezel",
    [(0.050, 0), (0.057, 0.007), (0.057, 0.016), (0.050, 0.022)],
    (0, -0.277, 0.56),
    steel,
    (math.pi / 2, 0, 0),
)
lathe(
    machine,
    "pressure_dial_face",
    [(0.049, 0), (0.049, 0.003)],
    (0, -0.300, 0.56),
    ivory,
    (math.pi / 2, 0, 0),
)
for i in range(21):
    a = math.radians(-140 + i * 14)
    r0 = 0.034 if i % 5 == 0 else 0.039
    r1 = 0.046
    tube(
        machine,
        "etched_gauge_tick",
        [
            (math.sin(a) * r0, -0.304, 0.56 + math.cos(a) * r0),
            (math.sin(a) * r1, -0.304, 0.56 + math.cos(a) * r1),
        ],
        0.0008,
        black,
    )
    if i % 5 == 0:
        label(
            machine,
            "dial_numeral",
            str(i // 5 * 3),
            (math.sin(a) * 0.026, -0.305, 0.56 + math.cos(a) * 0.026),
            0.007,
            black,
        )
tube(
    machine, "gauge_needle", [(0, -0.307, 0.56), (0.020, -0.307, 0.590)], 0.0011, black
)
label(machine, "pressure_units", "bar", (0, -0.306, 0.543), 0.006, black)
for side in [-1, 1]:
    x = side * 0.59
    lathe(
        machine,
        "steam_valve_collar",
        [(0.035, 0), (0.038, 0.008), (0.038, 0.020)],
        (x, -0.274, 0.552),
        steel,
        (math.pi / 2, 0, 0),
    )
    lathe(
        machine,
        "ribbed_valve_knob",
        [(0.027, 0), (0.037, 0.007), (0.040, 0.022), (0.037, 0.043), (0.030, 0.048)],
        (x, -0.293, 0.552),
        rubber,
        (math.pi / 2, 0, 0),
    )
    for j in range(24):
        a = j * 2 * math.pi / 24
        tube(
            machine,
            "knob_grip_rib",
            [
                (x + 0.038 * math.cos(a), -0.307, 0.552 + 0.038 * math.sin(a)),
                (x + 0.038 * math.cos(a), -0.330, 0.552 + 0.038 * math.sin(a)),
            ],
            0.0011,
            rubber,
        )
    tube(
        machine,
        "articulated_steam_wand",
        [
            (x, -0.20, 0.40),
            (x + side * 0.055, -0.23, 0.38),
            (x + side * 0.06, -0.30, 0.29),
            (x + side * 0.045, -0.38, 0.18),
        ],
        0.008,
        steel,
    )
    lathe(
        machine,
        "steam_tip",
        [(0.010, 0), (0.012, 0.010), (0.011, 0.023)],
        (x + side * 0.045, -0.38, 0.16),
        steel,
    )
    label(machine, "steam_valve_mark", "STEAM", (x, -0.283, 0.608), 0.009, black)
panel(machine, "cup_warming_deck", (0, 0.08, 0.737), (1.35, 0.54, 0.027), steel, 0.009)
for i in range(31):
    panel(
        machine,
        "warming_tray_slot",
        (-0.61 + i * 0.0405, 0.07, 0.752),
        (0.009, 0.38, 0.004),
        black,
        0.002,
    )
tube(
    machine,
    "warming_rail",
    [
        (-0.65, -0.13, 0.797),
        (-0.65, 0.29, 0.797),
        (0.65, 0.29, 0.797),
        (0.65, -0.13, 0.797),
    ],
    0.008,
    steel,
)
for i in range(5):
    B.native(
        machine,
        "CupFactory",
        "native_warmer_cup",
        (-0.50 + i * 0.245, 0.05, 0.753),
        0.86,
        index=i % 3,
    )
label(
    machine,
    "engraved_machine_brand",
    "LEMON  /  PRECISION ESPRESSO",
    (0, -0.283, 0.637),
    0.018,
    black,
)
for x in [-0.68, 0.68]:
    for z in [0.14, 0.65]:
        lathe(
            machine,
            "casing_fastener",
            [(0.003, 0), (0.003, 0.003)],
            (x, -0.258, z),
            steel,
            (math.pi / 2, 0, 0),
            32,
        )
# A complete burr grinder: cast housing, adjuster, glass hopper and individual beans.
grinder = B.col("REFINED_BURR_GRINDER_MASTER")
panel(grinder, "grinder_foot", (0, 0, 0.023), (0.32, 0.37, 0.046), rubber, 0.032)
lathe(
    grinder,
    "cast_motor_housing",
    [(0.118, 0), (0.127, 0.025), (0.128, 0.13), (0.110, 0.29), (0.10, 0.33)],
    (0, 0.04, 0.04),
    dark,
)
lathe(
    grinder,
    "grind_adjustment_ring",
    [(0.11, 0), (0.129, 0.009), (0.129, 0.033), (0.11, 0.044)],
    (0, 0.04, 0.367),
    steel,
)
for i in range(48):
    a = i * 2 * math.pi / 48
    tube(
        grinder,
        "adjustment_knurl",
        [
            (0.13 * math.cos(a), 0.04 + 0.13 * math.sin(a), 0.38),
            (0.13 * math.cos(a), 0.04 + 0.13 * math.sin(a), 0.40),
        ],
        0.0015,
        steel,
    )
lathe(
    grinder,
    "thick_glass_hopper",
    [
        (0.052, 0),
        (0.055, 0.02),
        (0.139, 0.205),
        (0.141, 0.215),
        (0.143, 0.215),
        (0.141, 0.201),
        (0.057, 0.018),
        (0.054, 0),
    ],
    (0, 0.04, 0.408),
    glass,
)
lathe(
    grinder,
    "hopper_sealing_lid",
    [(0.145, 0), (0.146, 0.007), (0.137, 0.016)],
    (0, 0.04, 0.625),
    dark,
)
panel(
    grinder, "dose_control_head", (0, -0.093, 0.32), (0.145, 0.050, 0.10), dark, 0.018
)
panel(grinder, "dose_oled", (0, -0.121, 0.335), (0.093, 0.005, 0.044), screen, 0.006)
label(grinder, "grind_dose_readout", "18.0 g", (0, -0.125, 0.335), 0.013, white)
tube(
    grinder,
    "coffee_dosing_chute",
    [(0, -0.085, 0.27), (0, -0.137, 0.26), (0, -0.163, 0.22)],
    0.018,
    steel,
)
for side in [-1, 1]:
    tube(
        grinder,
        "portafilter_fork",
        [
            (side * 0.05, -0.07, 0.17),
            (side * 0.05, -0.15, 0.17),
            (side * 0.07, -0.18, 0.19),
        ],
        0.008,
        steel,
    )
panel(
    grinder, "grinder_drip_tray", (0, -0.135, 0.066), (0.24, 0.15, 0.015), steel, 0.012
)
label(grinder, "grinder_brand", "BURR  /  64", (0, -0.110, 0.23), 0.012, ivory)
vs = []
fs = []
for j in range(17):
    phi = 0.001 + (math.pi - 0.002) * j / 16
    for i in range(32):
        a = i * 2 * math.pi / 32
        x = 0.0045 * math.sin(phi) * math.cos(a)
        y = 0.0065 * math.sin(phi) * math.sin(a)
        z = 0.0034 * math.cos(phi) - 0.0010 * math.exp(-((x / 0.0010) ** 2)) * max(
            math.cos(phi), 0
        )
        vs.append((x, y, z))
for j in range(16):
    for i in range(32):
        fs.append(
            (
                j * 32 + i,
                j * 32 + (i + 1) % 32,
                (j + 1) * 32 + (i + 1) % 32,
                (j + 1) * 32 + i,
            )
        )
me = bpy.data.meshes.new("creased_roasted_coffee_bean")
me.from_pydata(vs, [], fs)
me.materials.append(coffee)
for p in me.polygons:
    p.use_smooth = True
rng = random.Random(92231)
for layer in range(7):
    z = 0.445 + layer * 0.020
    radius = 0.055 + (z - 0.43) * 0.40
    for iy in range(-6, 7):
        for ix in range(-6, 7):
            x = ix * 0.016 + rng.uniform(-0.002, 0.002)
            y = iy * 0.016 + rng.uniform(-0.002, 0.002)
            if x * x + y * y > (radius - 0.008) ** 2:
                continue
            o = bpy.data.objects.new("coffee_equipment:roasted_bean", me)
            grinder.objects.link(o)
            o.location = (x, 0.04 + y, z)
            o.rotation_euler = (
                rng.uniform(-0.5, 0.5),
                rng.uniform(-0.5, 0.5),
                rng.uniform(0, math.tau),
            )
# Replace all old appliance components atomically; keep authored counters/sinks.
for o in list(C.objects):
    if "espresso" in o.name or "grinder" in o.name:
        C.objects.unlink(o)
B.inst(C, machine, "refined_professional_espresso", (-3.88, 1.335, 1.36), math.pi)
for x in [-2.65, -2.05]:
    B.inst(C, grinder, "refined_burr_grinder", (x, 1.355, 1.40), math.pi)
for master in [machine, grinder]:
    master["asset_factory"] = "ProfiledCoffeeEquipmentFactory"
    master[
        "detail_contract"
    ] = "96-sided profiles, smooth curved tubing, fasteners, controls, physical glass and real beans"
bpy.data.libraries.write(
    str(B.OUT / "shared_assets/refined_coffee_equipment.blend"),
    {machine, grinder},
    compress=True,
)
m = json.loads((D / "scene_manifest.json").read_text())
m["equipment_upgrade"] = {
    "factory": "ProfiledCoffeeEquipmentFactory",
    "sheet_components_source": "commercial_mcdonalds_layout_generator_20.py",
    "round_component_resolution": 96,
    "steam_wands": "smooth NURBS tubes",
    "gauge": "geometry and typography",
    "grinder": "glass hopper with individual creased beans",
    "shared_library": "../shared_assets/refined_coffee_equipment.blend",
}
(D / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(D / "scene.blend"), compress=True)
print(
    "DETAILED_COFFEE_EQUIPMENT_READY",
    len(machine.objects),
    len(grinder.objects),
    flush=True,
)

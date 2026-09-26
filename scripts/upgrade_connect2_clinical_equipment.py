"""Fine clinical equipment assembled from authored bed parts and native linens."""
import bpy, sys, math, json
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

D = B.OUT / "hospital"
bpy.ops.wm.open_mainfile(filepath=str(D / "scene.blend"), load_ui=False)
C = bpy.data.collections["Architecture_and_furnished_interior"]
template = next(o for o in C.objects if "triage_" in o.name and ":frame" in o.name)
white = B.material("medical_moulded_polymer", (0.71, 0.75, 0.73), 0.34)
blue = B.material("medical_blue_insert", (0.085, 0.26, 0.32), 0.45)
steel = B.material("medical_brushed_steel", (0.42, 0.44, 0.46), 0.25, 0.92)
rubber = B.material("medical_caster_rubber", (0.018, 0.022, 0.023), 0.53)
linen = B.material("medical_woven_linen", (0.77, 0.78, 0.72), 0.72)
cloth = B.material("medical_quilt", (0.12, 0.29, 0.35), 0.75)
dark = B.material("monitor_glass", (0.003, 0.008, 0.012), 0.19)
green = B.material("monitor_wave", (0.03, 0.7, 0.24), 0.4)
p = green.node_tree.nodes.get("Principled BSDF")
p.inputs["Emission Color"].default_value = (0.03, 0.7, 0.24, 1)
p.inputs["Emission Strength"].default_value = 1.4
clear = B.material("medical_clear_polymer", (0.94, 0.98, 0.99), 0.15)
p = clear.node_tree.nodes.get("Principled BSDF")
p.inputs["Transmission Weight"].default_value = 0.93
p.inputs["IOR"].default_value = 1.38
for mat in [linen, cloth]:
    ns = mat.node_tree.nodes
    lk = mat.node_tree.links
    t = ns.new("ShaderNodeTexNoise")
    t.inputs["Scale"].default_value = 290
    b = ns.new("ShaderNodeBump")
    b.inputs["Strength"].default_value = 0.25
    b.inputs["Distance"].default_value = 0.0003
    lk.new(t.outputs["Fac"], b.inputs["Height"])
    lk.new(b.outputs["Normal"], ns.get("Principled BSDF").inputs["Normal"])


def panel(c, name, loc, dims, mat, r=0.008):
    o = B.part(c, template, name, loc, dims)
    o.data = o.data.copy()
    o.data.transform(Matrix.Diagonal((*o.scale, 1)))
    o.scale = (1, 1, 1)
    for mod in list(o.modifiers):
        o.modifiers.remove(mod)
    be = o.modifiers.new("Manufactured fillet", "BEVEL")
    be.width = min(r, min(dims) * 0.45)
    be.segments = 6
    be.harden_normals = True
    B.assign(o, mat)
    return o


def lathe(c, name, profile, loc, mat, rot=(0, 0, 0), n=64):
    vs = [
        (r * math.cos(i * math.tau / n), r * math.sin(i * math.tau / n), z)
        for r, z in profile
        for i in range(n)
    ]
    fs = [
        (j * n + i, j * n + (i + 1) % n, (j + 1) * n + (i + 1) % n, (j + 1) * n + i)
        for j in range(len(profile) - 1)
        for i in range(n)
    ]
    fs += [
        tuple(reversed(range(n))),
        tuple((len(profile) - 1) * n + i for i in range(n)),
    ]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.materials.append(mat)
    o = bpy.data.objects.new("clinical:" + name, me)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    for f in me.polygons:
        f.use_smooth = len(f.vertices) == 4
    return o


def tube(c, name, pts, r, mat):
    d = bpy.data.curves.new(name, "CURVE")
    d.dimensions = "3D"
    d.bevel_depth = r
    d.bevel_resolution = 6
    d.resolution_u = 24
    sp = d.splines.new("NURBS")
    sp.points.add(len(pts) - 1)
    for p, v in zip(sp.points, pts):
        p.co = (*v, 1)
    sp.order_u = min(3, len(pts))
    sp.use_endpoint_u = True
    d.materials.append(mat)
    o = bpy.data.objects.new("clinical:" + name, d)
    c.objects.link(o)
    return o


def profile_panel(c, name, x, mat):
    # Molded head/foot board with curved outline and a real carrying-handle cutout.
    outline = [(-0.40, 0.56), (-0.47, 0.63), (-0.48, 1.14)]
    for i in range(17):
        t = i / 16
        y = -0.48 + 0.96 * t
        outline.append((y, 1.14 + 0.14 * math.sin(math.pi * t) ** 0.45))
    outline += [(0.47, 0.63), (0.40, 0.56)]
    thick = 0.060
    vs = [(x + side * thick / 2, y, z) for side in [-1, 1] for y, z in outline]
    n = len(outline)
    fs = [tuple(reversed(range(n))), tuple(n + i for i in range(n))] + [
        (i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n)
    ]
    me = bpy.data.meshes.new(name)
    me.from_pydata(vs, [], fs)
    me.materials.append(mat)
    o = bpy.data.objects.new("clinical:" + name, me)
    c.objects.link(o)
    # Rounded slot cutter is temporary construction geometry, removed after use.
    cut = panel(c, "handle_slot_tool", (x, 0, 1.16), (0.18, 0.47, 0.085), white, 0.035)
    bpy.context.view_layer.objects.active = cut
    for mod in list(cut.modifiers):
        bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.context.view_layer.objects.active = o
    bo = o.modifiers.new("Molded handle opening", "BOOLEAN")
    bo.object = cut
    bo.operation = "DIFFERENCE"
    bo.solver = "EXACT"
    bpy.ops.object.modifier_apply(modifier=bo.name)
    bpy.data.objects.remove(cut, do_unlink=True)
    be = o.modifiers.new("Mold radius", "BEVEL")
    be.width = 0.009
    be.segments = 5
    return o


bed = B.col("REFINED_CLINICAL_BED_MASTER")
bpy.context.scene.collection.children.link(bed)
for y in [-0.34, 0.34]:
    panel(bed, "underframe_longitudinal", (0, y, 0.46), (1.97, 0.055, 0.10), steel)
for x in [-0.82, 0, 0.82]:
    panel(bed, "crossmember", (x, 0, 0.46), (0.055, 0.78, 0.085), steel)
panel(
    bed,
    "articulated_mattress_platform",
    (0, 0, 0.565),
    (2.04, 0.88, 0.09),
    white,
    0.022,
)
panel(bed, "soft_foam_mattress", (0, 0, 0.687), (1.96, 0.85, 0.19), linen, 0.07)
# Mattress welting follows its perimeter with rounded corners.
tube(
    bed,
    "mattress_seam",
    [
        (-0.91, -0.42, 0.715),
        (0.91, -0.42, 0.715),
        (0.975, -0.36, 0.715),
        (0.975, 0.36, 0.715),
        (0.91, 0.42, 0.715),
        (-0.91, 0.42, 0.715),
        (-0.975, 0.36, 0.715),
        (-0.975, -0.36, 0.715),
        (-0.91, -0.42, 0.715),
    ],
    0.0016,
    linen,
)
for x in [-1.055, 1.055]:
    profile_panel(bed, "moulded_endboard", x, white)
    panel(
        bed,
        "endboard_colored_inlay",
        (x + math.copysign(0.034, x), 0, 0.86),
        (0.009, 0.68, 0.28),
        blue,
        0.004,
    )
# Adjustable guard rails: formed top and bottom rails, joints and release levers.
for side in [-1, 1]:
    y = side * 0.48
    tube(
        bed,
        "rounded_safety_rail",
        [
            (-0.76, y, 0.83),
            (-0.76, y, 1.02),
            (-0.68, y, 1.075),
            (0.68, y, 1.075),
            (0.76, y, 1.02),
            (0.76, y, 0.83),
        ],
        0.018,
        steel,
    )
    tube(bed, "lower_rail", [(-0.72, y, 0.87), (0.72, y, 0.87)], 0.014, steel)
    for x in [-0.60, -0.2, 0.2, 0.60]:
        tube(bed, "rail_vertical", [(x, y, 0.87), (x, y, 1.065)], 0.009, steel)
    for x in [-0.75, 0.75]:
        lathe(
            bed,
            "rail_pivot",
            [(0.035, 0), (0.035, 0.025), (0.027, 0.035)],
            (x, y, 0.81),
            white,
            (math.pi / 2, 0, 0),
        )
        panel(
            bed,
            "rail_release",
            (x, y + side * 0.03, 0.75),
            (0.065, 0.028, 0.075),
            blue,
            0.012,
        )
for x in [-0.82, 0.82]:
    for y in [-0.34, 0.34]:
        lathe(
            bed,
            "swivel_stem",
            [(0.019, 0), (0.021, 0.08), (0.026, 0.105), (0.03, 0.12)],
            (x, y, 0.27),
            steel,
        )
        for side in [-1, 1]:
            lathe(
                bed,
                "caster_tire",
                [
                    (0.057, 0),
                    (0.070, 0.004),
                    (0.074, 0.012),
                    (0.070, 0.025),
                    (0.057, 0.029),
                ],
                (x, y + side * 0.025, 0.10),
                rubber,
                (math.pi / 2, 0, 0),
            )
            lathe(
                bed,
                "wheel_hub",
                [(0.024, 0), (0.032, 0.005), (0.032, 0.010)],
                (x, y + side * 0.043, 0.10),
                steel,
                (math.pi / 2, 0, 0),
            )
        panel(bed, "caster_fork", (x, y, 0.22), (0.050, 0.10, 0.15), steel, 0.012)
        panel(
            bed, "brake_pedal", (x + 0.065, y, 0.18), (0.085, 0.09, 0.018), blue, 0.006
        )
        tube(
            bed,
            "height_adjustment_link",
            [(x, y, 0.34), (x * 0.66, y, 0.45)],
            0.025,
            steel,
        )
# Draped quilt is a continuous thickened cloth surface, not a solid slab.
vs = []
fs = []
nx = 72
ny = 56
for ix in range(nx + 1):
    x = -0.25 + 1.17 * ix / nx
    for iy in range(ny + 1):
        y = -0.57 + 1.14 * iy / ny
        edge = max(abs(y) - 0.37, 0) / 0.20
        z = (
            0.797
            - 0.17 * edge**1.8
            + 0.004 * math.sin(x * 26 + y * 7)
            + 0.003 * math.sin(y * 44 + x * 3)
        )
        vs.append((x, y, z))
for ix in range(nx):
    for iy in range(ny):
        a = ix * (ny + 1) + iy
        fs.append((a, a + 1, a + ny + 2, a + ny + 1))
me = bpy.data.meshes.new("draped_quilt_surface")
me.from_pydata(vs, [], fs)
me.materials.append(cloth)
o = bpy.data.objects.new("clinical:draped_quilt", me)
bed.objects.link(o)
for p in me.polygons:
    p.use_smooth = True
so = o.modifiers.new("Quilt thickness", "SOLIDIFY")
so.thickness = 0.006
su = o.modifiers.new("Soft cloth surface", "SUBSURF")
su.levels = 1
src = bpy.data.collections["NATIVE_PillowFactory_0"]
pillow = B.col("NATIVE_CLINICAL_LINEN_PILLOW")
for ob in src.objects:
    n = B.copy(pillow, ob)
    B.assign(n, linen)
B.inst(bed, pillow, "native_clinical_pillow", (-0.68, 0, 0.784), 0, 1.0)
# Bedside observation module: real stand, LCD, controls, ECG and labelled values.
monitor = B.col("REFINED_PATIENT_OBSERVATION_MASTER")
bpy.context.scene.collection.children.link(monitor)
lathe(
    monitor,
    "monitor_stand",
    [(0.022, 0), (0.022, 1.2), (0.028, 1.22)],
    (0, 0, 0.12),
    steel,
)
for i in range(5):
    a = i * math.tau / 5
    tube(
        monitor,
        "stand_leg",
        [(0, 0, 0.18), (0.25 * math.cos(a), 0.25 * math.sin(a), 0.06)],
        0.016,
        steel,
    )
panel(monitor, "monitor_enclosure", (0, -0.04, 1.41), (0.49, 0.13, 0.35), white, 0.036)
panel(monitor, "lcd_cover", (0, -0.110, 1.43), (0.398, 0.009, 0.25), dark, 0.009)
B.text(
    monitor,
    "patient_readings",
    "72     98\n120 / 80",
    (0.067, -0.117, 1.45),
    0.036,
    green,
)
for row in range(2):
    pts = []
    for i in range(101):
        t = i / 100
        phase = (t * 4) % 1
        spike = (
            0.045 * math.exp(-(((phase - 0.42) / 0.035) ** 2))
            - 0.023 * math.exp(-(((phase - 0.48) / 0.025) ** 2))
            + 0.008 * math.sin(phase * math.tau)
        )
        pts.append((-0.182 + t * 0.17, -0.119, 1.40 + row * 0.075 + spike))
    tube(monitor, "physiological_waveform", pts, 0.00085, green)
B.text(monitor, "monitor_caption", "PATIENT MONITOR", (0, -0.112, 1.285), 0.016, blue)
for i in range(5):
    lathe(
        monitor,
        "monitor_key",
        [(0.009, 0), (0.009, 0.004)],
        (-0.15 + i * 0.054, -0.113, 1.275),
        blue,
        (math.pi / 2, 0, 0),
    )
lathe(
    monitor,
    "monitor_selector",
    [(0.023, 0), (0.025, 0.008), (0.021, 0.019)],
    (0.181, -0.115, 1.285),
    blue,
    (math.pi / 2, 0, 0),
)
tube(
    monitor,
    "monitor_power_cable",
    [(0.21, 0.02, 1.37), (0.28, 0.02, 1.15), (0.12, 0.07, 0.80), (0.12, 0.12, 0.30)],
    0.003,
    rubber,
)
# A profiled IV stand, hook, clear fluid pouch and curved administration tubing.
iv = B.col("REFINED_INFUSION_STAND_MASTER")
bpy.context.scene.collection.children.link(iv)
lathe(
    iv,
    "telescopic_lower_pole",
    [(0.021, 0), (0.021, 1.25), (0.027, 1.27), (0.027, 1.31)],
    (0, 0, 0.10),
    steel,
)
lathe(iv, "telescopic_upper_pole", [(0.013, 0), (0.013, 0.92)], (0, 0, 1.36), steel)
for side in [-1, 1]:
    tube(
        iv,
        "bag_hanger",
        [
            (0, 0, 2.21),
            (side * 0.16, 0, 2.21),
            (side * 0.18, 0, 2.27),
            (side * 0.13, 0, 2.29),
        ],
        0.006,
        steel,
    )
for i in range(5):
    a = i * math.tau / 5
    tube(
        iv,
        "IV_stand_leg",
        [(0, 0, 0.17), (0.22 * math.cos(a), 0.22 * math.sin(a), 0.05)],
        0.012,
        steel,
    )
# Sealed flexible pouch with a rounded, bloated profile and welded perimeter.
vs = []
fs = []
nu = 24
nv = 32
for side in [-1, 1]:
    for j in range(nv + 1):
        z = 1.84 + 0.31 * j / nv
        v = j / nv
        for i in range(nu + 1):
            u = i / nu
            x = 0.135 + (u - 0.5) * 0.145 * (0.84 + 0.16 * math.sin(math.pi * v))
            y = side * (0.001 + 0.014 * math.sin(math.pi * u) * math.sin(math.pi * v))
            vs.append((x, y, z))
count = (nu + 1) * (nv + 1)
for side in range(2):
    for j in range(nv):
        for i in range(nu):
            a = side * count + j * (nu + 1) + i
            face = (a, a + 1, a + nu + 2, a + nu + 1)
            fs.append(face if side else tuple(reversed(face)))
me = bpy.data.meshes.new("sealed_IV_fluid_pouch")
me.from_pydata(vs, [], fs)
me.materials.append(clear)
ob = bpy.data.objects.new("clinical:flexible_saline_pouch", me)
iv.objects.link(ob)
for p in me.polygons:
    p.use_smooth = True
so = ob.modifiers.new("Transparent pouch film", "SOLIDIFY")
so.thickness = 0.0008
panel(
    iv,
    "pouch_print_label",
    (0.135, -0.016, 2.015),
    (0.110, 0.001, 0.092),
    linen,
    0.0003,
)
B.text(iv, "fluid_label", "SALINE\n0.9%\n250 mL", (0.135, -0.018, 2.015), 0.012, blue)
tube(
    iv,
    "bag_hanging_loop",
    [(0.11, 0, 2.15), (0.10, 0, 2.26), (0.17, 0, 2.26), (0.16, 0, 2.15)],
    0.0025,
    clear,
)
lathe(
    iv,
    "drip_chamber",
    [(0.006, 0), (0.010, 0.009), (0.010, 0.052), (0.006, 0.062)],
    (0.135, 0, 1.772),
    clear,
)
tube(
    iv,
    "administration_tubing",
    [
        (0.135, 0, 1.78),
        (0.18, -0.03, 1.56),
        (0.20, -0.06, 1.28),
        (0.30, -0.17, 1.02),
        (0.25, -0.28, 0.89),
    ],
    0.0022,
    clear,
)
panel(iv, "roller_clamp", (0.18, -0.03, 1.56), (0.018, 0.018, 0.048), blue, 0.004)
for coll in [bed, monitor, iv]:
    bpy.context.scene.collection.children.unlink(coll)
    coll["asset_factory"] = "RefinedClinicalEquipmentFactory"
    coll[
        "source_asset"
    ] = "hospital4 articulated clinical bed and Infinigen PillowFactory"
for o in list(C.objects):
    if "triage_" in o.name or any(
        t in o.name
        for t in [
            "clinical_native_pillow",
            "clinical_safety_rail",
            "clinical_rail_post",
        ]
    ):
        C.objects.unlink(o)
B.inst(C, bed, "clinical_bed_full_assembly", (2.7, 10.55, 0.41))
B.inst(C, monitor, "patient_observation_assembly", (3.95, 11.1, 0.41))
B.inst(C, iv, "infusion_assembly", (1.50, 11.05, 0.41))
bpy.data.libraries.write(
    str(B.OUT / "shared_assets/refined_clinical_equipment.blend"),
    {bed, monitor, iv},
    compress=True,
)
m = json.loads((D / "scene_manifest.json").read_text())
m["clinical_equipment_upgrade"] = {
    "factory": "RefinedClinicalEquipmentFactory",
    "components": [
        "formed endboards with handle openings",
        "profiled swivel casters",
        "guard rails and release controls",
        "native linen pillow",
        "draped quilt mesh",
        "LCD with ECG geometry",
        "telescopic IV stand and transparent pouch",
    ],
    "library": "../shared_assets/refined_clinical_equipment.blend",
}
(D / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(D / "scene.blend"), compress=True)
print("CLINICAL_EQUIPMENT_REFINED", flush=True)

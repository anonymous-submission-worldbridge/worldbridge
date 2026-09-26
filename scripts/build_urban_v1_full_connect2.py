"""Six authored asset assemblies with real, traversable indoor/outdoor spaces.

Every visible mesh derives from the user's asset library or a full Infinigen
factory. Architectural booleans correct solid legacy cores, not camera cheats.
"""
from __future__ import annotations
import bpy, sys, json, math, os, random
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_urban_v1_full_connect as OLD

OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
PART = ROOT / "infinigen/outputs/outdoor_part_demo"
SOURCE = OLD.SOURCE
SPECS = {
    "restaurant": dict(
        old="corner_kitchen",
        title="Community Restaurant - Open-air Dining Terrace",
        center=-5.8,
        width=15.45,
        depth=9.0,
        floor=0.26,
        layout="asymmetric_dining_terrace",
    ),
    "cafe": dict(
        old="lemon_coffee",
        title="Corner Garden Coffee Shop",
        center=-3.0,
        width=8.4,
        depth=8.2,
        floor=0.26,
        layout="corner_garden",
    ),
    "market": dict(
        old="fresh_mart",
        title="Supermarket & Street Market",
        center=-0.62,
        width=15.45,
        depth=9.0,
        floor=0.26,
        layout="linear_market",
    ),
    "hospital": dict(
        title="Community Hospital - Medical Entrance Lobby",
        center=9.2,
        width=38.0,
        depth=28.0,
        floor=0.41,
        layout="arrival_and_healing_garden",
        file="urban_v3_hospital4",
        collection="hospital:HOSPITAL_A_TRADITIONAL_BRICK",
        origin=(-81.2, -6.45, 0),
    ),
    "pharmacy": dict(
        title="Community Pharmacy · Walking Commercial Street",
        center=9.5,
        width=25.4,
        depth=19.0,
        floor=0.08,
        layout="offset_pedestrian_street",
        file="urban_v3_pharmacy5",
        collection="pharmacy5:PHARMACY_02_WELL_HIGH_STREET",
        origin=(26.5, 0.45, 0),
        rotate=math.pi,
    ),
    "library": dict(
        title="Library · Tree Shade Reading Garden",
        center=0.0,
        width=46.0,
        depth=31.0,
        floor=0.16,
        layout="reading_garden",
        file="urban_v3_library4",
        collection="library4:LIBRARY_B_RED_MONUMENTAL",
        origin=(39.0, -10.45, 0),
    ),
}
LOG = []


def col(name, parent=None):
    c = bpy.data.collections.new(name)
    if parent is not None:
        parent.children.link(c)
    return c


def inst(c, master, name, loc, angle=0, scale=1):
    if isinstance(master, str):
        master = bpy.data.collections[master]
    o = bpy.data.objects.new("connect2:" + name, None)
    o.instance_type = "COLLECTION"
    o.instance_collection = master
    c.objects.link(o)
    o.location = loc
    o.rotation_euler.z = angle
    o.scale = (scale,) * 3
    o["asset_master"] = master.name
    return o


def copy(c, o, name=None, matrix=None):
    n = o.copy()
    c.objects.link(n)
    n["source_object"] = o.name
    n["asset_source_blend"] = o.get("asset_source_blend", str(SOURCE))
    mw = o.matrix_world.copy()
    n.parent = None
    n.matrix_world = (matrix @ mw) if matrix is not None else mw
    if name:
        n.name = "connect2:" + name
    return n


def part(c, source, name, loc, dims, angle=0):
    o = copy(c, bpy.data.objects[source] if isinstance(source, str) else source, name)
    o.location = loc
    o.rotation_euler = (0, 0, angle)
    o.scale = (1, 1, 1)
    bpy.context.view_layer.update()
    o.dimensions = dims
    return o


def native(c, f, name, loc, scale=1, angle=0, index=0):
    base = "NATIVE_" + f
    key = base if base in bpy.data.collections else base + "_" + str(index)
    return inst(
        c,
        "FINISH_" + key if "FINISH_" + key in bpy.data.collections else key,
        name,
        loc,
        angle,
        scale,
    )


def material(name, color, rough=0.5, metal=0):
    m = bpy.data.materials.new("connect2:" + name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Roughness"].default_value = rough
    p.inputs["Metallic"].default_value = metal
    return m


def assign(o, mat):
    if o.data and hasattr(o.data, "materials"):
        o.data = o.data.copy()
        o.data.materials.clear()
        o.data.materials.append(mat)
        for slot in o.material_slots:
            slot.link = "DATA"
            slot.material = mat


def text(c, name, body, loc, size, mat, rot=(math.pi / 2, 0, 0)):
    # Physical product/wayfinding print, never an image annotation.
    d = bpy.data.curves.new(name, "FONT")
    d.body = body
    d.size = size
    d.extrude = 0.00015
    d.align_x = "CENTER"
    d.align_y = "CENTER"
    d.resolution_u = 8
    o = bpy.data.objects.new("connect2:" + name, d)
    c.objects.link(o)
    o.location = loc
    o.rotation_euler = rot
    d.materials.append(mat)
    o["asset_detail"] = "procedural_print"
    return o


def bounds(o):
    p = [o.matrix_world @ Vector(v) for v in o.bound_box]
    return Vector([min(v[k] for v in p) for k in range(3)]), Vector(
        [max(v[k] for v in p) for k in range(3)]
    )


def cut(objects, lo, hi, reason):
    # Temporary solid cutter never appears in any saved scene or render.
    lo = Vector(lo)
    hi = Vector(hi)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(lo + hi) / 2)
    cutter = bpy.context.object
    cutter.name = "TEMP_ARCHITECTURAL_OPENING"
    cutter.dimensions = hi - lo
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    count = 0
    for o in list(objects):
        if o.type != "MESH" or o == cutter:
            continue
        mn, mx = bounds(o)
        if not all(mx[k] > lo[k] + 0.0001 and mn[k] < hi[k] - 0.0001 for k in range(3)):
            continue
        o.data = o.data.copy()
        bpy.context.view_layer.objects.active = o
        m = o.modifiers.new("Permanent usable room opening", "BOOLEAN")
        m.operation = "DIFFERENCE"
        m.solver = "EXACT"
        m.object = cutter
        try:
            bpy.ops.object.modifier_apply(modifier=m.name)
            count += 1
        except RuntimeError:
            o.modifiers.remove(m)
    bpy.data.objects.remove(cutter, do_unlink=True)
    LOG.append(
        dict(
            operation="architectural_boolean",
            reason=reason,
            objects=count,
            lo=list(lo),
            hi=list(hi),
        )
    )


def load_native():
    for f in [
        "native_indoor_assets.blend",
        "native_extended.blend",
        "native_fruit.blend",
        "reference08_tree.blend",
    ]:
        with bpy.data.libraries.load(str(OUT / "shared_assets" / f), link=True) as (
            a,
            b,
        ):
            b.collections = list(a.collections)


def stock_upgrade():
    rng = random.Random(260923)
    # Retain native geometry while specifying coordinated manufactured finishes.
    # Local variants avoid modifying the shared extraction or the previous demos.
    for f, color, rough in [
        ("PlateFactory", (0.73, 0.71, 0.65), 0.21),
        ("BowlFactory", (0.76, 0.73, 0.66), 0.23),
        ("VaseFactory", (0.20, 0.27, 0.24), 0.35),
    ]:
        original = bpy.data.collections.get("NATIVE_" + f)
        if original:
            styled = col("FINISH_NATIVE_" + f)
            finish = material("glazed_" + f, color, rough)
            for src in original.objects:
                ob = copy(styled, src)
                assign(ob, finish)
    for i in range(3):
        original = bpy.data.collections["NATIVE_CupFactory_" + str(i)]
        styled = col("FINISH_NATIVE_CupFactory_" + str(i))
        finish = material(
            "ceramic_coffee_cup_" + str(i),
            [(0.66, 0.60, 0.50), (0.13, 0.24, 0.22), (0.74, 0.72, 0.66)][i],
            0.24,
        )
        for src in original.objects:
            assign(copy(styled, src), finish)
    # Replace all elementary product masters, not just products nearest cameras.
    mapping = {
        "PRODUCT_BOTTLE": "BottleFactory",
        "PRODUCT_CAN": "JarFactory",
        "PRODUCT_BOX": "FoodBoxFactory",
        "PRODUCT_CARTON": "FoodBoxFactory",
        "PRODUCT_BAG": "FoodBagFactory",
    }
    for c in list(bpy.data.collections):
        kind = next((k for k in mapping if c.name.endswith(k)), None)
        if not kind:
            continue
        for o in list(c.objects):
            c.objects.unlink(o)
        native(c, mapping[kind], "full_native_" + kind, (0, 0, 0))
    # Populate supported shelf decks with actual bottom-normalized native assets.
    c = bpy.data.collections["GROCERY_SHELF_MASTER"]
    for o in list(c.objects):
        if "faced_product" in o.name:
            c.objects.unlink(o)
    decks = [o for o in c.objects if "supported_shelf_deck" in o.name]
    for j, d in enumerate(decks):
        z = d.location.z + d.dimensions.z / 2
        for i in range(16):
            f = ["BottleFactory", "FoodBoxFactory", "FoodBagFactory", "JarFactory"][
                (i // 4 + j) % 4
            ]
            scale = 0.80 if f == "FoodBagFactory" else 1
            for row in range(2):
                y = math.copysign(0.29 + row * 0.14, d.location.y)
                o = native(
                    c,
                    f,
                    "supported_retail_inventory",
                    (-1.22 + i * 0.162, y, z),
                    scale,
                    math.pi if y > 0 else 0,
                    index=(i // 5) % 2,
                )
                o["support_top_z"] = z
                o["support_object"] = d.name
    # More complete table settings; all utensils and crockery are native meshes.
    c = bpy.data.collections["DINING_CHAIR_MASTER"]
    for o in list(c.objects):
        c.objects.unlink(o)
    native(c, "ChairFactory", "native_dining_chair", (0, 0, 0))
    c = bpy.data.collections["DINING_TABLE_MASTER"]
    bare = col("AUTHORED_READING_TABLE_MASTER")
    for o in c.objects:
        copy(bare, o)
    for x in [-0.31, 0.31]:
        native(c, "PlateFactory", "ceramic_dinner_plate", (x, 0, 0.8), 0.77)
        native(c, "BowlFactory", "ceramic_side_bowl", (x, 0.005, 0.824), 0.70)
        native(
            c, "SpoonFactory", "dining_spoon", (x + 0.16, -0.03, 0.802), 1, math.pi / 2
        )
        native(c, "WineglassFactory", "stemmed_water_glass", (x, 0.25, 0.80), 0.85)
    native(c, "VaseFactory", "table_porcelain", (0, 0.22, 0.8), 0.44)


def floors(c, cx, cy, w, d, z, source, wood=False):
    # Modular finish made from the existing beveled architectural floor component.
    palette = []
    for i in range(5):
        m = material(
            ("oak" if wood else "stone") + str(i),
            (0.17 + i * 0.008, 0.092 + i * 0.006, 0.044 + i * 0.004)
            if wood
            else (0.30 + i * 0.013, 0.29 + i * 0.012, 0.255 + i * 0.01),
            0.46,
        )
        nodes = m.node_tree.nodes
        links = m.node_tree.links
        p = nodes.get("Principled BSDF")
        t = nodes.new("ShaderNodeTexNoise")
        t.inputs["Scale"].default_value = 125 if wood else 95
        t.inputs["Detail"].default_value = 3
        b = nodes.new("ShaderNodeBump")
        b.inputs["Strength"].default_value = 0.17
        b.inputs["Distance"].default_value = 0.0015
        links.new(t.outputs["Fac"], b.inputs["Height"])
        links.new(b.outputs["Normal"], p.inputs["Normal"])
        palette.append(m)
    dx, dy = (1.2, 0.18) if wood else (0.6, 0.6)
    nx = math.ceil(w / dx)
    ny = math.ceil(d / dy)
    dx = w / nx
    dy = d / ny
    template = part(
        c, source, "floor_tile_template", (0, 0, -100), (dx - 0.004, dy - 0.004, 0.02)
    )
    template.data = template.data.copy()
    # Apply scale once, then link shared mesh/material variations across many tiles.
    bpy.context.view_layer.objects.active = template
    template.select_set(True)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    template.select_set(False)
    meshes = []
    for m in palette:
        me = template.data.copy()
        me.materials.clear()
        me.materials.append(m)
        meshes.append(me)
    for iy in range(ny):
        for ix in range(nx):
            o = template.copy()
            o.data = meshes[(ix * 13 + iy * 7) % 5]
            c.objects.link(o)
            o.name = "connect2:modeled_floor_finish"
            o.location = (
                cx - w / 2 + (ix + 0.5) * dx,
                cy - d / 2 + (iy + 0.5) * dy,
                z - 0.01,
            )
            o["assembly"] = "floor finish with recessed seams"
            for slot in o.material_slots:
                slot.link = "DATA"
                slot.material = palette[(ix * 13 + iy * 7) % 5]
    bpy.data.objects.remove(template, do_unlink=True)


def improve_commercial(c, key):
    s = SPECS[key]
    old = s["old"]
    spec = OLD.SPECS[old]
    master = bpy.data.collections[spec["master"]]
    for o in list(master.objects):
        if o.hide_render:
            master.objects.unlink(o)
    LOG.extend(OLD.open_authored_doors(master, old))
    offset = Matrix.Translation(Vector((-spec["door"], -spec["front"], 0)))
    for o in master.objects:
        copy(c, o, matrix=offset)
    floor = next(o for o in c.objects if "floor_slab" in o.name)
    floors(
        c,
        s["center"],
        4.4,
        s["width"] - 0.6,
        7.8,
        0.265,
        floor,
        wood=key in ("restaurant", "cafe"),
    )
    if key == "restaurant":
        for x, y in [(-3.9, 2.5), (-4.3, 4.9)]:
            inst(c, "DINING_TABLE_MASTER", "additional_dining_setting", (x, y, 0.265))
            for dy, angle in [(-0.72, 0), (0.72, math.pi)]:
                native(
                    c,
                    "ChairFactory",
                    "additional_dining_chair",
                    (x, y + dy, 0.265),
                    1,
                    angle,
                )
        # Wall finish is a repeated authored oak counter panel, with physical joints.
        panel = next(
            (
                o
                for o in bpy.data.objects
                if "counter" in o.name and "panel" in o.name and o.type == "MESH"
            ),
            floor,
        )
        oak = material("restaurant_oak_wall", (0.16, 0.082, 0.04), 0.45)
        for i in range(26):
            ob = part(
                c,
                panel,
                "oak_wall_lining",
                (-13.06, 1.2 + i * 0.27, 1.05),
                (0.08, 0.255, 1.45),
            )
            assign(ob, oak)
        sign = material("restaurant_brass_type", (0.41, 0.25, 0.095), 0.28, 0.65)
        text(
            c,
            "restaurant_wall_identity",
            "SEASONAL KITCHEN",
            (-9.0, 8.72, 2.65),
            0.28,
            sign,
        )
        native(
            c,
            "OvenFactory",
            "native_kitchen_oven",
            (-0.3, 7.8, 0.265),
            0.65,
            math.pi / 2,
        )
        for x in [-7.2, -4.7]:
            native(c, "PotFactory", "native_stockpot", (x, 8.12, 1.19), 1.25)
            native(c, "PanFactory", "native_kitchen_pan", (x + 0.55, 8.18, 1.19), 1)
        for x, y in [
            (-11.35, 2.27),
            (-9.05, 2.67),
            (-6.35, 2.57),
            (-10.9, 5.07),
            (-7.95, 5.37),
        ]:
            native(
                c, "FruitFactoryApple", "table_fruit", (x - 0.27, y, 0.26 + 0.85), 0.7
            )
        # Existing service counter receives native jars and cups, leaving work space.
        for i in range(6):
            native(
                c,
                "JarFactory",
                "condiment_jar",
                (-2.7 + i * 0.20, 5.8, 1.43),
                0.62,
                index=i % 2,
            )
    elif key == "cafe":
        # Replace simple coffee bags and paper cups with full native profiles.
        for o in list(c.objects):
            if o.instance_collection and "TAKEAWAY_CUP" in o.instance_collection.name:
                o.instance_collection = bpy.data.collections[
                    "FINISH_NATIVE_CupFactory_" + str(len(o.name) % 3)
                ]
                o.scale = (1, 1, 1)
            if any(t in o.name for t in ("coffee_retail_bag", "coffee_bag_label")):
                if "coffee_retail_bag" in o.name:
                    native(
                        c,
                        "FoodBagFactory",
                        "detailed_roasted_coffee_bag",
                        (o.location.x, o.location.y, o.location.z - o.dimensions.z / 2),
                        0.90,
                        index=0,
                    )
                c.objects.unlink(o)
        for x, y in [(-5.3, 4.2), (-3.2, 5.3)]:
            inst(c, "DINING_TABLE_MASTER", "cafe_reading_table", (x, y, 0.265), 0, 0.86)
            for dy, ang in [(-0.72, 0), (0.72, math.pi)]:
                native(
                    c, "ChairFactory", "cafe_lounge_chair", (x, y + dy, 0.265), 1, ang
                )
            native(
                c,
                "BookStackFactory",
                "cafe_magazines",
                (x, y, 0.265 + 0.8 * 0.86),
                0.8,
                index=1,
            )
        # Fine espresso back: louvred casing, mechanical fasteners, genuine labelling.
        body = next(
            (o for o in c.objects if "espresso_machine_chassis" in o.name), None
        )
        if body:
            mn, mx = bounds(body)
            steel = material("brushed_espresso_steel", (0.32, 0.34, 0.35), 0.25, 0.86)
            dark = material("equipment_label", (0.025, 0.028, 0.029), 0.5)
            for i in range(24):
                p = part(
                    c,
                    body,
                    "espresso_rear_vent",
                    (
                        mn.x + 0.09 + i * (mx.x - mn.x - 0.18) / 23,
                        mx.y + 0.003,
                        (mn.z + mx.z) / 2,
                    ),
                    (0.016, 0.014, (mx.z - mn.z) * 0.46),
                )
                assign(p, dark)
            text(
                c,
                "espresso_service_mark",
                "LEMON  /  DUAL BOILER",
                (body.location.x, mx.y + 0.018, mx.z - 0.09),
                0.047,
                steel,
                (-math.pi / 2, 0, math.pi),
            )
    elif key == "market":
        # Reuse authored dining table as a wooden produce merchandising stand.
        bare = col("PRODUCE_DISPLAY_SUPPORT")
        for o in bpy.data.collections["DINING_TABLE_MASTER"].objects:
            if o.type == "MESH":
                copy(bare, o)
        for x, y in [(-4.0, 1.2), (3.0, 1.2)]:
            inst(c, bare, "produce_display", (x, y, 0.265))
            for ix in range(9):
                for iy in range(5):
                    native(
                        c,
                        "FruitFactoryApple",
                        "fresh_apple",
                        (x - 0.48 + ix * 0.119, y - 0.24 + iy * 0.12, 1.065),
                        1 + 0.05 * ((ix + iy) % 3),
                    )
            for k in range(4):
                native(
                    c,
                    "FruitFactoryPineapple",
                    "pineapple",
                    (x - 0.42 + k * 0.26, y + 0.22, 1.065),
                    0.78,
                )
    return c


def append_flat(c, s):
    path = PART / s["file"] / (s["file"] + ".blend")
    with bpy.data.libraries.load(str(path), link=False) as (a, b):
        b.collections = [s["collection"]]
    master = b.collections[0]
    rot = Matrix.Rotation(s.get("rotate", 0), 4, "Z")
    tr = rot @ Matrix.Translation(-Vector(s["origin"]))
    # Link temporarily so world transforms inherited through authored roots update.
    bpy.context.scene.collection.children.link(master)
    bpy.context.view_layer.update()
    for o in master.all_objects:
        if not o.hide_render:
            n = copy(c, o, matrix=tr)
            n["asset_source_blend"] = str(path)
    bpy.context.scene.collection.children.unlink(master)
    return list(c.objects)


def public_interior(c, key):
    s = SPECS[key]
    objects = append_flat(c, s)
    if key == "pharmacy":
        # Slide both leaves and their rails/decals together along the original track.
        for o in c.objects:
            if "well_main_sliding_entry" in o.name and any(
                t in o.name
                for t in (
                    ":leaf_",
                    ":stile_",
                    ":toprail_",
                    ":kickplate_",
                    ":safety_decal_",
                )
            ):
                side = -1 if o.location.x < 0 else 1
                o.location.x += side * 2.13
        # Replace toy stools with full native seats in consultation nook.
        for o in list(c.objects):
            if "well_consult_stool" in o.name:
                c.objects.unlink(o)
        for x in [-0.75, 0.55]:
            native(c, "ChairFactory", "consultation_chair", (x, 16.2, 0.08), 1, math.pi)
        return
    if key == "hospital":
        # Hollow the existing masonry into a 10 x 11 m furnished community lobby.
        cores = [
            o
            for o in c.objects
            if "brick_core" in o.name or "continuous_cornice_0.65" in o.name
        ]
        cut(
            cores,
            (-5.0, 0.2, 0.41),
            (5.0, 11.8, 4.35),
            "usable community hospital reception room",
        )
        # Full floor and ceiling use the authored layered structural slabs.
        floor = next(o for o in c.objects if "lobby_floor" in o.name)
        part(c, floor, "continuous_lobby_floor", (0, 5.7, 0.30), (10.0, 12.0, 0.22))
        ceiling = part(
            c, floor, "continuous_lobby_ceiling", (0, 5.7, 4.4), (10.0, 12.0, 0.16)
        )
        # Correct opaque curtain-wall backer; preserve only its perimeter reveals.
        backs = [o for o in c.objects if "atrium:deep_recess" in o.name]
        cut(
            backs,
            (-4.43, -1.0, 0.40),
            (4.43, 1.8, 4.25),
            "remove solid facade backing within real glazed lobby",
        )
        # Slide existing complete leaves. Keep track, threshold and exterior jambs.
        for o in c.objects:
            if "traditional:main_entry:" in o.name and any(
                t in o.name
                for t in [
                    ":leaf_",
                    ":top_frame_",
                    ":bottom_frame_",
                    ":pull_",
                    ":closer_",
                ]
            ):
                o.location.x += (-1 if o.location.x < 0 else 1) * 2.25
        # Remove duplicate curtain wall only in the actual doorway opening.
        front = [
            o
            for o in c.objects
            if "atrium:" in o.name or "traditional:main_entry:recess" in o.name
        ]
        cut(
            front,
            (-2.12, -1.0, 0.40),
            (2.12, 1.8, 3.65),
            "clear double-door aperture through duplicate atrium glazing",
        )
        cut(
            list(c.objects),
            (-2.12, -0.85, 0.41),
            (2.12, 2.2, 3.65),
            "carry the portal through all authored facade masonry layers",
        )
        # Shift service desk off the circulation line and furnish an L-shaped lobby.
        for o in list(c.objects):
            if "traditional:reception" in o.name:
                o.location.x -= 0.2
                o.location.y += 3.35
            if "traditional:waiting_" in o.name:
                c.objects.unlink(o)
        for x in [-3.8, -2.65, 2.55, 3.7]:
            for y in [5.0, 6.5, 8.0]:
                native(
                    c,
                    "ChairFactory",
                    "clinic_waiting_chair",
                    (x, y, 0.41),
                    1.15,
                    math.pi,
                )
        # Move one existing fully articulated clinical bed assembly to ground triage.
        for o in objects:
            if "traditional:patient_room_0:bed:" in o.name:
                n = copy(c, o, "triage_" + o.name)
                n.location += Vector((-10.5, 7.0, -7.74))
        native(
            c, "MonitorFactory", "reception_computer", (0, 7.5, 1.60), 0.75, math.pi / 2
        )
        for x in [-3.6, 3.5]:
            native(
                c, "PlantContainerFactory", "lobby_ceramic_planter", (x, 2.5, 0.41), 1
            )
        floors(c, 0, 5.8, 9.8, 11.5, 0.415, floor)
    elif key == "library":
        # A real ground-floor reading room is opened inside the original full shell.
        shell = [
            o
            for o in c.objects
            if any(
                t in o.name
                for t in ("occupied_shell", "dark_plinth", "plinth_weathering")
            )
        ]
        cut(
            shell,
            (-8.2, -0.5, 0.16),
            (8.2, 13.0, 4.28),
            "hollow authored red library shell into reading hall",
        )
        # Existing vestibule glazing becomes the two sidelights, leaving a passage.
        entrance = [
            o
            for o in c.objects
            if "B:main_entrance:" in o.name or "B:atrium_0_" in o.name
        ]
        cut(
            entrance,
            (-1.7, -1.0, 0.16),
            (1.7, 2.5, 3.95),
            "continuous library entry and vestibule aperture",
        )
        floor_src = bpy.data.objects["all43_15:commercial_floor_slab"]
        part(
            c,
            floor_src,
            "reading_hall_structural_floor",
            (0, 6.3, 0.06),
            (16.4, 13.4, 0.20),
        )
        part(c, floor_src, "reading_hall_ceiling", (0, 6.3, 4.37), (16.4, 13.4, 0.18))
        floors(c, 0, 6.3, 16.3, 13.2, 0.16, floor_src, True)
        # Reuse the user's detailed library shelf carcasses; native book meshes replace
        # single-block book spines in this occupied showcase room.
        groups = {}
        for o in objects:
            if "B:atrium_stack_" in o.name:
                groups.setdefault(
                    o.name.split(":atrium_stack_")[1].split(":")[0], []
                ).append(o)
        shelfparts = next(iter(groups.values()), [])
        if shelfparts:
            src_center = sum((o.location for o in shelfparts), Vector()) / len(
                shelfparts
            )
            mn = Vector(
                [
                    min(bounds(o)[0][k] for o in shelfparts if o.type == "MESH")
                    for k in range(3)
                ]
            )
            mx = Vector(
                [
                    max(bounds(o)[1][k] for o in shelfparts if o.type == "MESH")
                    for k in range(3)
                ]
            )
            source_origin = Vector(((mn.x + mx.x) / 2, (mn.y + mx.y) / 2, mn.z))
            for x in [-5.8, -2.0, 2.0, 5.8]:
                for o in shelfparts:
                    if ":book_" not in o.name:
                        n = copy(c, o, "reading_stack")
                        n.location += Vector((x, 11.7, 0.16)) - source_origin
                for z in [0.57, 1.15, 1.73, 2.31, 2.89]:
                    for i in range(10):
                        native(
                            c,
                            "BookColumnFactory",
                            "native_shelf_books",
                            (x - 1.2 + i * 0.27, 11.42, z),
                            1,
                            index=i % 2,
                        )
        # Separate reading islands leave an uninterrupted central route.
        for x in [-4.6, 4.6]:
            for y in [4.6, 7.7]:
                inst(
                    c,
                    "AUTHORED_READING_TABLE_MASTER",
                    "reading_table",
                    (x, y, 0.16),
                    0,
                    1.35,
                )
                for yy, a in [(y - 0.95, 0), (y + 0.95, math.pi)]:
                    native(c, "ChairFactory", "reading_chair", (x, yy, 0.16), 1.1, a)
                native(c, "DeskLampFactory", "reading_lamp", (x + 0.45, y, 1.24), 0.82)
                native(
                    c,
                    "BookStackFactory",
                    "open_reading_material",
                    (x - 0.34, y, 1.24),
                    1,
                    index=2,
                )
        for x in [-6.8, 6.8]:
            native(
                c,
                "SofaFactory",
                "reading_lounge",
                (x, 1.9, 0.16),
                1,
                math.pi / 2 if x < 0 else -math.pi / 2,
            )


def landscape(c, key, s):
    cx = s["center"]
    w = s["width"]
    rng = random.Random(130 + list(SPECS).index(key))
    z = 0.14
    base = bpy.data.objects["all43_20:relocated_rear_parking_asphalt"]
    paver = bpy.data.objects["all43_24:cafe_frontage_paver_field"]
    ground = part(c, base, "compact_site_base", (cx, 2.0, -0.09), (160, 160, 0.16))
    groundmat = material("landscape_soil", (0.095, 0.13, 0.065), 0.96)
    assign(ground, groundmat)
    part(c, paver, "pedestrian_forecourt", (cx, -6, 0.045), (w + 9, 12, 0.16))
    # Paving joints, street gutter, drain grate and edging remain authored parts.
    seam = next(
        (
            o
            for o in bpy.data.objects
            if o.name.startswith("all43_24:") and "joint" in o.name and o.type == "MESH"
        ),
        paver,
    )
    for j in range(-6, 7):
        part(
            c, seam, "paving_movement_joint", (cx, -6 + j, 0.13), (w + 9, 0.012, 0.006)
        )
    for j in range(math.ceil(w + 9)):
        part(
            c,
            seam,
            "paving_cross_joint",
            (cx - (w + 9) / 2 + j, -6, 0.13),
            (0.008, 12, 0.006),
        )
    bed = "COMPLEX_REAR_FLOWERBED_MASTER"
    seat = "OUTDOOR_CAFE_SET_MASTER"
    tree = "full02:MASTER:TreeFactory:42"
    if key == "restaurant":
        beds = [(-14, -4, math.pi / 2), (-4, -10, 0), (3, -6, math.pi / 2)]
        tables = [(-11, -3.5), (-7.5, -4.7), (-4, -3.3), (-10.5, -8), (-6.5, -8.5)]
        trees = [(-18, -6, 0.72), (7, -8, 0.65), (-18, 10, 0.70), (-8, -17, 0.75)]
    elif key == "cafe":
        beds = [(-8, -3, math.pi / 2), (-5, -9, 0), (5, -7, math.pi / 2)]
        tables = [(-5.5, -3), (-2.8, -4.5), (3.1, -5.8), (-5.8, -7.0)]
        trees = [(-13, -3, 0.72), (-12, -11, 0.74), (6, -13, 0.70), (-13, 9, 0.72)]
    elif key == "market":
        beds = [(-11, -5, math.pi / 2), (10, -5, math.pi / 2), (-6, -11, 0)]
        tables = [(-6, -7), (6, -8)]
        trees = [(-14, -8, 0.72), (14, -8, 0.72), (-14, 10, 0.75), (14, 11, 0.66)]
        # Repeated supported street merchandise creates an active market edge.
        for x in [-6.0, 6.0]:
            inst(
                c,
                "GROCERY_SHELF_MASTER",
                "outdoor_market_merchandise",
                (x, -2.8, z),
                0,
                0.75,
            )
    elif key == "hospital":
        beds = [(-7, -4, math.pi / 2), (-4, -10, 0), (14, -8, 0), (23, -5, math.pi / 2)]
        tables = []
        trees = [(-15, -6, 0.86), (34, -7, 0.90), (19, -16, 0.75), (-16, 15, 0.85)]
        # The authored waiting seats connect the lobby to the healing garden.
        for x in [-5.5, 8.0, 11.0]:
            for i in range(3):
                native(
                    c,
                    "ChairFactory",
                    "healing_garden_seat",
                    (x + i * 0.82, -7, z),
                    1.1,
                    0,
                )
    elif key == "pharmacy":
        beds = [(-5, -5, math.pi / 2), (7, -9, 0), (22, -6, math.pi / 2)]
        tables = [(9, -5), (17, -4)]
        trees = [(-9, -8, 0.82), (29, -9, 0.82), (16, -16, 0.74), (-9, 11, 0.72)]
    else:
        beds = [
            (-10, -4, math.pi / 2),
            (10, -4, math.pi / 2),
            (-7, -11, 0),
            (7, -11, 0),
        ]
        tables = [(-7, -5), (-4.3, -8.5), (4.5, -8.5), (7, -5)]
        trees = [(-13, -7, 0.85), (13, -7, 0.85), (-12, -15, 0.82), (12, -15, 0.82)]
    for x, y, a in beds:
        inst(c, bed, "authored_flower_border", (x, y, z), a, 0.85)
    for x, y in tables:
        inst(c, seat, "terrace_furniture", (x, y, z), rng.uniform(-0.35, 0.35), 1)
    for i, (x, y, sz) in enumerate(trees):
        o = inst(c, tree, "full08_mature_tree", (x, y, z), i * 1.37, sz)
        o["asset_source_blend"] = str(OLD.REFERENCE)
    for i in range(9):
        inst(
            c,
            tree,
            "distant_garden_canopy",
            (cx - 23 + i * 5.8, -23 - (i % 2) * 3, z),
            i * 0.93,
            0.90 + (i % 3) * 0.09,
        )
    # Enclose the view in living 3D foliage rather than an empty horizon.
    for i in range(4):
        inst(
            c,
            tree,
            "garden_boundary_tree",
            (cx - w / 2 - 6, 1 + i * 4.4, z),
            i * 0.85,
            0.60 + i * 0.025,
        )
    for x, y in [(cx - w / 2 - 2, -2), (cx + w / 2 + 2, -3)]:
        inst(
            c,
            "SHAREDBICYCLE4_SINGLE_BICYCLE_MASTER",
            "detailed_bicycle",
            (x, y, z),
            math.pi / 2,
        )
    # One side-facing contextual building produces an L junction only for cafe;
    # it is absent in all other compositions.
    if key == "cafe":
        inst(
            c, "HAWTHORN_STREET_BAR_MASTER", "corner_neighbor", (9, -1, 0), math.pi / 2
        )


def lighting(scene, c, key, s):
    world = bpy.data.worlds.new("Connect2 daylight")
    world.use_nodes = True
    scene.world = world
    n = world.node_tree.nodes
    l = world.node_tree.links
    bg = n.get("Background")
    sky = n.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING" if bpy.app.version >= (5, 0, 0) else "NISHITA"
    sky.sun_disc = False
    sky.sun_elevation = math.radians(36)
    sky.sun_rotation = math.radians(135)
    bg.inputs["Strength"].default_value = 0.055
    l.new(sky.outputs["Color"], bg.inputs["Color"])
    d = bpy.data.lights.new("Afternoon sun", "SUN")
    d.energy = 2.1
    d.angle = math.radians(5)
    o = bpy.data.objects.new("Afternoon sun", d)
    c.objects.link(o)
    o.rotation_euler = (0.55, -0.35, -0.48)
    OLD.add_area(
        c,
        "Facade sky fill",
        (s["center"] - 2, -8, 9),
        (s["center"], 2, 1),
        550,
        9,
        (0.78, 0.88, 1),
    )
    if key in ("restaurant", "cafe", "market"):
        for x in [s["center"] - 2, s["center"] + 2]:
            OLD.add_area(
                c,
                "Ceiling practical",
                (x, 4.4, 3.55),
                (x, 4.4, 0),
                100,
                3,
                (1, 0.85, 0.67),
            )
    elif key == "hospital":
        for y in [3, 7, 10]:
            OLD.add_area(
                c,
                "Lobby ceiling panel",
                (0, y, 4.22),
                (0, y, 0),
                140,
                3,
                (1, 0.91, 0.8),
            )
    elif key == "library":
        for x in [-5, 0, 5]:
            for y in [3, 8, 11]:
                OLD.add_area(
                    c,
                    "Reading ceiling panel",
                    (x, y, 4.18),
                    (x, y, 0),
                    130,
                    3,
                    (1, 0.86, 0.71),
                )
    # Clear physical glazing, not opaque diffuse fake glass.
    for m in bpy.data.materials:
        if m.library or not m.use_nodes:
            continue
        if any(
            t in m.name.lower()
            for t in [
                "glass_clear",
                "clear_glass",
                "laminated_glass",
                "storefront_glass",
                "glass_door",
                "glass_neutral",
            ]
        ):
            p = m.node_tree.nodes.get("Principled BSDF")
            if p:
                p.inputs["Transmission Weight"].default_value = 1
                p.inputs["Base Color"].default_value = (0.96, 0.98, 0.99, 1)
                p.inputs["Roughness"].default_value = 0.035
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0


def shots(key, s):
    cx = s["center"]
    w = s["width"]
    z = s["floor"] + 1.6

    def shot(p, t, lens=27):
        return dict(position=p, target=t, lens=lens)

    # 24 independent photographs, including six per connection direction.
    sh = {
        "exterior_wide": shot(
            (cx + w * 0.65, -w * 0.72 - 9, 7 if w < 20 else 13),
            (cx, 3, 3 if w < 20 else 7),
            32,
        ),
        "exterior_street_left": shot((cx - w * 0.67, -13, 3.0), (cx, 1, 2.4), 28),
        "exterior_street_right": shot((cx + w * 0.65, -10, 2.7), (cx, 2, 2.0), 28),
        "garden_overview": shot((cx - w * 0.56, -14, 9), (cx, -3, 1.0), 30),
        "entrance_context": shot((2, -8, 2.3), (cx * 0.22, 2, 1.6), 27),
        "outdoor_furniture": shot((cx - 5, -9, 2.0), (cx - 2, -4.4, 1.0), 35),
    }
    depths = (
        [1.2, 2.6, 4.2] if key in ("restaurant", "cafe", "market") else [1.4, 3.2, 5.3]
    )
    for label, d in zip(["near", "middle", "far"], depths):
        # Keep door in the frame; far shots show more indoor foreground and outdoor depth.
        for side in ["axial", "oblique"]:
            x = (
                0
                if side == "axial"
                else ((-0.8 if key == "cafe" else -0.9) if label == "far" else 0.4)
            )
            sh[f"inside_to_outside_{label}_{side}"] = shot(
                (x, d, z), (-x * 0.4, -7, 1.6), 24 if label != "near" else 28
            )
    for label, d in [("near", 1.8), ("middle", 4.7), ("far", 8.8)]:
        for side in ["axial", "oblique"]:
            x = 0 if side == "axial" else (1.8 if label == "far" else 0.55)
            sh[f"outside_to_inside_{label}_{side}"] = shot(
                (x, -d, z), (0, 4, 1.6), 28 if label == "far" else 25
            )
    interiors = {
        "restaurant": [
            ((-0.45, 1.4, z), (-9, 4, 1.25), 24),
            ((-3.2, 6.8, z), (-10, 2.4, 1.2), 26),
            ((-10.5, 5, z), (-2.2, 6, 1.45), 26),
            ((-6.5, 1.1, 2.0), (-9.05, 2.67, 1.1), 44),
            ((-6, 6.5, 2), (-5.5, 8, 1.25), 40),
            ((-1, 3.5, z), (-8.5, 1.8, 1.2), 25),
        ],
        "cafe": [
            ((-0.35, 1.2, z), (-4.3, 4.5, 1.45), 23),
            ((-1.5, 6.6, z), (-4.5, 2.8, 1.55), 24),
            ((-5.6, 5.8, z), (-0.8, 3.6, 1.35), 24),
            ((-1.6, 3.6, 2.1), (-4.0, 1.4, 1.65), 38),
            ((-4.6, 4.7, 2), (-5.3, 4.2, 1.0), 38),
            ((-2.4, 3.2, z), (-3, 7.1, 2.3), 27),
        ],
        "market": [
            ((0, 1.9, z), (-4.2, 5.2, 1.4), 24),
            ((-0.2, 6.9, z), (-5, 3.5, 1.3), 24),
            ((1.5, 1.3, z), (4, 5.6, 1.3), 25),
            ((-1.8, 1.4, 1.8), (-4, 1.2, 1.15), 45),
            ((-0.2, 4.4, 1.8), (-3.17, 4.4, 1.3), 45),
            ((3.4, 2.0, z), (2.5, 8.4, 1.6), 27),
        ],
        "hospital": [
            ((0, 2.2, z), (-2.4, 7.0, 1.4), 24),
            ((3.6, 9.8, z), (-2, 4, 1.35), 24),
            ((-3.8, 4.2, z), (1, 8.7, 1.5), 25),
            ((2, 5, 2), (0, 7.7, 1.5), 42),
            ((3.6, 6.4, 2), (-1.5, 3.3, 1.3), 36),
            ((0, 3.0, z), (3.2, 8.7, 1.2), 26),
        ],
        "pharmacy": [
            ((1.5, 2.8, z), (10.5, 8.8, 1.4), 24),
            ((12.8, 2.2, z), (8.8, 13.8, 1.6), 25),
            ((13.0, 12.0, z), (9.0, 4.0, 1.4), 25),
            ((5.5, 10.8, 1.9), (9.4, 14.8, 1.3), 38),
            ((12.8, 8.5, 1.8), (9.5, 8.5, 1.2), 42),
            ((13.0, 3.3, z), (19.0, 2.5, 1.1), 34),
        ],
        "library": [
            ((0, 2.3, z), (-3, 8, 1.5), 24),
            ((0, 10, z), (4, 3.4, 1.3), 24),
            ((-6.5, 9.2, z), (4.5, 5.5, 1.2), 26),
            ((-2.6, 6.1, 2), (-4.6, 4.6, 1.4), 42),
            ((1, 9.5, 1.9), (2, 11.4, 1.7), 45),
            ((3, 2.4, z), (6.5, 2.0, 1), 35),
        ],
    }
    for name, data in zip(
        [
            "interior_wide",
            "interior_reverse",
            "interior_diagonal",
            "detail_primary",
            "detail_secondary",
            "interior_activity",
        ],
        interiors[key],
    ):
        sh[name] = shot(*data)
    return sh


def main(key):
    s = SPECS[key]
    dest = OUT / key
    dest.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE), load_ui=False)
    old = bpy.context.scene
    scene = bpy.data.scenes.new("CONNECT2_" + key)
    bpy.context.window.scene = scene
    architecture = col("Architecture_and_furnished_interior", scene.collection)
    outside = col("Detailed_public_realm", scene.collection)
    lights = col("Lighting_and_cameras", scene.collection)
    load_native()
    stock_upgrade()
    if "old" in s:
        improve_commercial(architecture, key)
    else:
        public_interior(architecture, key)
    landscape(outside, key, s)
    lighting(scene, lights, key, s)
    camera = bpy.data.objects.new(
        "Presentation_camera", bpy.data.cameras.new("Presentation_camera")
    )
    lights.objects.link(camera)
    scene.camera = camera
    camera.data.clip_start = 0.06
    camera.data.clip_end = 300
    sh = shots(key, s)
    pose = sh["exterior_wide"]
    camera.location = pose["position"]
    camera.rotation_euler = (
        (Vector(pose["target"]) - camera.location).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = pose["lens"]
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 96
    scene.cycles.use_denoising = True
    scene.cycles.denoising_use_gpu = True
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 10
    scene.cycles.transparent_max_bounces = 16
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    bpy.context.preferences.filepaths.save_version = 0
    for sc in list(bpy.data.scenes):
        if sc != scene:
            bpy.data.scenes.remove(sc)
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.context.view_layer.update()
    deps = bpy.context.evaluated_depsgraph_get()
    hits = []
    for x in [-0.20, 0, 0.20]:
        for height in [0.55, 1.1, 1.6, 1.95]:
            hit, p, n, idx, o, m = scene.ray_cast(
                deps,
                Vector((x, -1.0, s["floor"] + height)),
                Vector((0, 1, 0)),
                distance=3.0,
            )
            if hit:
                hits.append(
                    {"x": x, "height": height, "object": o.name, "location": list(p)}
                )
    count = 0
    verts = 0
    for i in deps.object_instances:
        if i.object.type == "MESH" and not i.object.hide_render:
            count += 1
            verts += len(i.object.data.vertices)
    manifest = {
        "scene": key,
        "title": s["title"],
        "layout": s["layout"],
        "floor_z": s["floor"],
        "front_y": 0,
        "door_x": 0,
        "spec": s,
        "shots": sh,
        "geometry": {
            "evaluated_mesh_instances": count,
            "evaluated_vertices": verts,
            "decimation": False,
            "image_backdrops": False,
        },
        "portal_audit": {"tested_rays": 12, "clear": not hits, "hits": hits},
        "architectural_fixes": LOG,
        "native_source": "indoor_outdoor_villa_demo2/coarse/scene.blend",
        "reference_source": str(OLD.REFERENCE),
        "blend": "scene.blend",
    }
    (dest / "scene_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2)
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
    for lib in bpy.data.libraries:
        lib.filepath = "//" + os.path.relpath(bpy.path.abspath(lib.filepath), dest)
    bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
    print(
        "CONNECT2_BUILT",
        key,
        "meshes",
        count,
        "vertices",
        verts,
        "portal",
        manifest["portal_audit"],
        flush=True,
    )


if __name__ == "__main__":
    main(sys.argv[-1])

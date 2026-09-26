"""Metric district assembly from attributed existing full-resolution assets."""
import bpy, sys, math, json, os, random, copy
from pathlib import Path
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, A, SCENES, ENTERABLE, CORE
from build_urban_v1_full_connect import add_area
from fix_connect3_fonts import fix as fix_fonts

CACHE = {}
BUILDINGS = []
OCCUPIED = []
LEDGER = []
META = {}


def meta(key):
    if key not in META:
        META[key] = json.loads((A / (key + ".json")).read_text())
    return META[key]


def coll(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def load(key, local=False):
    if key not in CACHE:
        with bpy.data.libraries.load(str(A / (key + ".blend")), link=not local) as (
            src,
            dst,
        ):
            dst.collections = ["ASSET_" + key]
        CACHE[key] = dst.collections[0]
        if CACHE[key] is None:
            raise RuntimeError("Missing authored asset " + key)
    return CACHE[key]


def instance(c, key, name, position, angle=0, scale=1):
    asset = load(key) if isinstance(key, str) else key
    ob = bpy.data.objects.new("connect4:" + name, None)
    c.objects.link(ob)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = asset
    ob.location = position
    ob.rotation_euler.z = angle
    ob.scale = (scale,) * 3 if isinstance(scale, (float, int)) else scale
    ob["asset_source"] = asset.get(
        "source_blend", asset.library.filepath if asset.library else asset.name
    )
    return ob


def transformed_bounds(key, T):
    lo, hi = meta(key)["bounds"]
    ps = [
        T @ Vector((x, y, z))
        for x in [lo[0], hi[0]]
        for y in [lo[1], hi[1]]
        for z in [lo[2], hi[2]]
    ]
    return [
        [min(p[i] for p in ps) for i in range(3)],
        [max(p[i] for p in ps) for i in range(3)],
    ]


def add_building(c, key, p, angle=0, primary=False):
    asset = load(
        key, local=True
    )  # Local object instances retain shared mesh datablocks.
    if primary:
        c.children.link(asset)
    else:
        instance(c, asset, "building_" + key, p, angle)
    T = Matrix.Translation(Vector(p)) @ Matrix.Rotation(angle, 4, "Z")
    b = transformed_bounds(key, T)
    entry = {
        "asset": key,
        "position": list(p),
        "angle": angle,
        "bounds": b,
        "source": meta(key)["source"],
        "enterable": key in ENTERABLE,
        "matrix": [list(row) for row in T],
    }
    BUILDINGS.append(entry)
    return entry


def overlap(a, b, margin=0):
    return all(min(a[1][k], b[1][k]) - max(a[0][k], b[0][k]) > -margin for k in (0, 1))


def layout(spec, c, index):
    key, title, focus, neighbors, form, land, extras = spec
    main = add_building(c, focus, (0, 0, 0), primary=True)
    lo, hi = main["bounds"]
    cx = (lo[0] + hi[0]) / 2
    gap = 4.5 + (index % 3) * 0.8
    wing = form in {"court", "corner", "crescent"}
    for j, n in enumerate(neighbors):
        wing_here = wing and j < 2 and not (form == "corner" and j == 0)
        angle = (
            (
                (math.pi / 4 if form == "crescent" else math.pi / 2)
                * (1 if j == 0 else -1)
            )
            if wing_here
            else (math.pi if j == 2 and n != "townhouse" else 0)
        )
        if form == "canal" and j == 2:
            angle = math.pi / 2
        bb = transformed_bounds(n, Matrix.Rotation(angle, 4, "Z"))
        stagger = 7 if form in {"mews", "canal"} else 1.5 * (index % 3)
        if j == 0:
            p = (
                lo[0] - gap - bb[1][0],
                lo[1] - 4 - (bb[0][1] + bb[1][1]) / 2 if wing_here else stagger,
                0,
            )
        elif j == 1:
            p = (
                hi[0] + gap - bb[0][0],
                lo[1] - 6 - (bb[0][1] + bb[1][1]) / 2 if wing_here else -stagger,
                0,
            )
        elif j == 2:
            south = min(b["bounds"][0][1] for b in BUILDINGS)
            # Opposite building keeps a continuous 18-25 m planted pedestrian court.
            p = (
                cx - (bb[0][0] + bb[1][0]) / 2 + (9 if form == "promenade" else 0),
                south - 19 - (index % 4) * 2 - bb[1][1],
                0,
            )
        else:
            east = max(b["bounds"][1][0] for b in BUILDINGS)
            p = (
                east + gap - bb[0][0],
                min(b["bounds"][0][1] for b in BUILDINGS) - bb[0][1],
                0,
            )
        item = add_building(c, n, p, angle)
        for prev in BUILDINGS[:-1]:
            if overlap(item["bounds"], prev["bounds"], 0.5):
                raise RuntimeError("Building overlap " + str((n, prev["asset"])))
    return [
        [min(b["bounds"][0][k] for b in BUILDINGS) for k in range(3)],
        [max(b["bounds"][1][k] for b in BUILDINGS) for k in range(3)],
    ]


PARTS = {}
PART_BASE = {}


def surface(c, key, name, loc, dims, mat=None):
    src = PARTS[key]
    ob = src.copy()
    c.objects.link(ob)
    ob.parent = None
    ob.name = "connect4:" + name
    ob.location = loc
    ob.rotation_euler = (0, 0, 0)
    ob.scale = (1, 1, 1)
    ob.scale = tuple(dims[k] / PART_BASE[key][k] for k in range(3))
    ob["source_object"] = src.name
    ob["expected_dimensions"] = list(dims)
    if mat:
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = mat
    LEDGER.append(
        {
            "object": ob.name,
            "source_object": src.name,
            "operation": "dimensioned existing architectural component",
        }
    )
    return ob


def material(name, col, rough=0.8):
    m = bpy.data.materials.new("connect4:" + name)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*col, 1)
    p.inputs["Roughness"].default_value = rough
    return m


def furnishing(c, key, x, y, z=0.05, angle=0, scale=1, check=True):
    m = meta(key)
    lo, hi = m["bounds"]
    anchor = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
    rot = Matrix.Rotation(angle, 4, "Z")
    p = Vector((x, y, z)) - rot @ (anchor * scale)
    T = Matrix.Translation(p) @ rot @ Matrix.Scale(scale, 4)
    bb = transformed_bounds(key, T)
    if check:
        if any(overlap(bb, b["bounds"], 0.6) for b in BUILDINGS):
            return None
        if any(overlap(bb, b, 0.45) for b in OCCUPIED):
            return None
        # Every public entrance retains a full approach, not just the hero camera.
        for b in BUILDINGS:
            if not b["enterable"]:
                continue
            inv = Matrix(b["matrix"]).inverted()
            q = inv @ Vector((x, y, z))
            radius = max(hi[0] - lo[0], hi[1] - lo[1]) * scale / 2
            if abs(q.x) < 1.5 + radius and -9 - radius < q.y < 1.0 + radius:
                return None
    ob = instance(c, key, key, p, angle, scale)
    OCCUPIED.append(bb)
    LEDGER.append(
        {
            "object": ob.name,
            "asset": key,
            "source": m["source"],
            "position": list(p),
            "scale": scale,
        }
    )
    return ob


def site(spec, c, bounds, index):
    rng = random.Random(240924 + index)
    key, title, focus, neighbors, form, land, extras = spec
    lo, hi = bounds
    cx = (lo[0] + hi[0]) / 2
    cy = (lo[1] + hi[1]) / 2
    x0, x1 = lo[0] - 4, hi[0] + 4
    y0, y1 = lo[1] - 4, hi[1] + 4
    with bpy.data.libraries.load(str(A / "site_components.blend"), link=True) as (
        src,
        dst,
    ):
        dst.collections = list(src.collections)
    PARTS.update(
        {c.name.removeprefix("ASSET_"): list(c.objects)[0] for c in dst.collections}
    )
    for key, source in list(PARTS.items()):
        src = source.copy()
        src.data = source.data.copy()
        indices = [p.material_index for p in src.data.polygons]
        used = sorted(set(indices))
        mats = [source.material_slots[i].material for i in used]
        src.data.materials.clear()
        for mat in mats:
            src.data.materials.append(mat)
        remap = {j: i for i, j in enumerate(used)}
        for p, i in zip(src.data.polygons, indices):
            p.material_index = remap[i]
        for slot in src.material_slots:
            slot.link = "DATA"
        PARTS[key] = src
        PART_BASE[key] = tuple(
            max(v.co[k] for v in src.data.vertices)
            - min(v.co[k] for v in src.data.vertices)
            for k in range(3)
        )
    earth = material("soil", (0.12, 0.155, 0.072))
    ns = earth.node_tree.nodes
    lk = earth.node_tree.links
    noise = ns.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 7
    noise.inputs["Detail"].default_value = 4
    ramp = ns.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.065, 0.08, 0.029, 1)
    ramp.color_ramp.elements[1].color = (0.19, 0.23, 0.12, 1)
    lk.new(noise.outputs["Fac"], ramp.inputs[0])
    lk.new(ramp.outputs[0], ns["Principled BSDF"].inputs["Base Color"])
    ground = surface(
        c, "asphalt", "earth_context", (cx, cy, -0.20), (1200, 1200, 0.30), earth
    )
    surface(
        c,
        "paving",
        "continuous_walkable_court",
        (cx, cy, -0.03),
        (x1 - x0, y1 - y0, 0.14),
    )
    for x in range(math.ceil(x0), math.floor(x1), 3):
        surface(
            c, "joint", "plaza_expansion_joint", (x, cy, 0.043), (0.012, y1 - y0, 0.005)
        )
    for y in range(math.ceil(y0), math.floor(y1), 3):
        surface(
            c, "joint", "plaza_expansion_joint", (cx, y, 0.043), (x1 - x0, 0.012, 0.005)
        )
    # Full perimeter streets and sidewalks. Roads extend past both intersections.
    paint = material("mineral_road_paint", (0.76, 0.73, 0.61))
    roadwest, roadeast = x0 - 7, x1 + 7
    roadsouth, roadnorth = y0 - 7, y1 + 7
    for x in [roadwest, roadeast]:
        surface(c, "asphalt", "perimeter_road", (x, cy, -0.04), (7, y1 - y0 + 75, 0.12))
    for y in [roadsouth, roadnorth]:
        surface(c, "asphalt", "perimeter_road", (cx, y, -0.04), (x1 - x0 + 75, 7, 0.12))
    for x in [x0 - 1.6, x1 + 1.6]:
        surface(
            c, "paving", "raised_sidewalk", (x, cy, 0.01), (3.2, y1 - y0 + 6.4, 0.18)
        )
    for y in [y0 - 1.6, y1 + 1.6]:
        surface(c, "paving", "raised_sidewalk", (cx, y, 0.01), (x1 - x0, 3.2, 0.18))
    for x in [roadwest, roadeast]:
        for y in range(math.ceil(y0 - 20), math.floor(y1 + 21), 7):
            if min(abs(y - roadsouth), abs(y - roadnorth)) < 6:
                continue
            surface(
                c, "joint", "road_center_dash", (x, y, 0.025), (0.11, 3, 0.006), paint
            )
    for y in [roadsouth, roadnorth]:
        for x in range(math.ceil(x0 - 20), math.floor(x1 + 21), 7):
            if min(abs(x - roadwest), abs(x - roadeast)) < 6:
                continue
            surface(
                c, "joint", "road_center_dash", (x, y, 0.025), (3, 0.11, 0.006), paint
            )
    for y in [roadsouth, roadnorth]:
        for x in [roadwest + 7, roadeast - 7]:
            for j in range(6):
                surface(
                    c,
                    "joint",
                    "pedestrian_crossing",
                    (x, y - 2.7 + j * 1.08, 0.026),
                    (2.8, 0.48, 0.007),
                    paint,
                )
    # Parking is separated from the travel lanes and carries real bay markings.
    parkingy = roadnorth + 10
    surface(
        c,
        "asphalt",
        "parking_bays",
        (cx, parkingy, -0.035),
        (max(24, x1 - x0 - 8), 6.3, 0.12),
    )
    for j in range(min(12, int((x1 - x0 - 10) / 2.7))):
        x = cx - 13 + j * 2.7
        surface(
            c,
            "joint",
            "parking_bay_line",
            (x, parkingy, 0.026),
            (0.10, 5.5, 0.007),
            paint,
        )
        if j % 3 != 1:
            furnishing(c, "car", x + 1.33, parkingy, 0.03, math.pi / 2, check=False)
    # Reusable detailed fountain and native terrace sets; the central visual axis
    # stays open even in the denser plaza arrangements.
    court_y = (BUILDINGS[0]["bounds"][0][1] + BUILDINGS[3]["bounds"][1][1]) / 2
    court_x = (BUILDINGS[0]["bounds"][0][0] + BUILDINGS[0]["bounds"][1][0]) / 2
    if land == "fountain":
        furnishing(c, "fountain" + str(index % 4), court_x - 7, court_y, 0.05)
    for b in BUILDINGS:
        T = Matrix(b["matrix"])
        bl, bh = meta(b["asset"])["bounds"]
        mid = (bl[0] + bh[0]) / 2
        for j in range(4):
            q = T @ Vector((mid + (j - 1.5) * 3.5, bl[1] - 3.2, 0.05))
            if b["asset"] in {
                "cafe",
                "restaurant",
                "bar",
                "corner_store",
                "library",
                "market",
            }:
                furnishing(
                    c,
                    "native_terrace" + str((index + j) % 3),
                    q.x,
                    q.y,
                    angle=b["angle"] + (j % 2) * 0.1,
                )
            elif j % 2 == 0:
                furnishing(c, "bench", q.x, q.y, angle=b["angle"])
        for side in [-1, 1]:
            q = T @ Vector((side * 2.9, -3.2, 0.05))
            furnishing(c, "flowerbed", q.x, q.y, angle=b["angle"])
    # Botanical borders and planting islands are measured against every building,
    # furnishing and approach corridor. No plants are placed through facades.
    with bpy.data.libraries.load(str(A / "reference08_tree.blend"), link=True) as (
        src,
        dst,
    ):
        dst.collections = ["full02:MASTER:TreeFactory:42"]
    tree = dst.collections[0]
    tree_positions = []
    # Dense groundcover islands use the authored botanical meshes from fountain3.
    # Each island includes individual blades, broadleaf rosettes and thatch.
    planted_count = 0
    for iy in range(7):
        for ix in range(10):
            x = x0 + 6 + (x1 - x0 - 12) * ix / 9
            y = y0 + 6 + (y1 - y0 - 12) * iy / 6
            if (ix + iy + index) % 2 or planted_count >= 10:
                continue
            planted = furnishing(
                c,
                "botanical_island",
                x,
                y,
                0.05,
                rng.uniform(0, math.tau),
                rng.uniform(0.8, 1.05),
            )
            if planted:
                instance(
                    c,
                    tree,
                    "garden_island_tree",
                    (x, y, 0.10),
                    rng.uniform(0, math.tau),
                    rng.uniform(0.65, 0.88),
                )
                planted_count += 1
    if index % 3 == 0:
        furnishing(
            c,
            "tree619",
            x1 + 16,
            y1 + 18,
            0.02,
            angle=rng.uniform(0, math.tau),
            scale=0.8,
            check=False,
        )
    for side in [-1, 1]:
        for i in range(7):
            tree_positions.append(
                (x0 - 2 if side < 0 else x1 + 2, y0 + 4 + (y1 - y0 - 8) * i / 6)
            )
    for i in range(7):
        tree_positions.append((x0 + 4 + (x1 - x0 - 8) * i / 6, y1 + 18))
    for i, (x, y) in enumerate(tree_positions):
        # Source botanical root is already grounded in the reference scene.
        if any(
            b["bounds"][0][0] - 3 < x < b["bounds"][1][0] + 3
            and b["bounds"][0][1] - 3 < y < b["bounds"][1][1] + 3
            for b in BUILDINGS
        ):
            continue
        instance(
            c,
            tree,
            "full08_tree",
            (x, y, 0.04),
            rng.uniform(0, math.tau),
            rng.uniform(0.72, 0.94),
        )
    for j in range(5):
        for i in range(9):
            x = x0 + 5 + (x1 - x0 - 10) * i / 8
            y = y0 + 5 + (y1 - y0 - 10) * j / 4
            if (i + j + index) % 3 == 0:
                furnishing(
                    c,
                    "flowerbed",
                    x,
                    y,
                    0.05,
                    rng.uniform(0, math.tau),
                    rng.uniform(0.80, 1.1),
                )
            elif (i + j) % 4 == 0:
                furnishing(c, "bench", x, y, 0.05, math.pi / 2 if i % 2 else 0)
    for i in range(10):
        x = x0 + 3 + (x1 - x0 - 6) * i / 9
        furnishing(c, "streetlight", x, y0 - 2, 0.10, check=False)
        if i % 2 == 0:
            furnishing(c, "flowerbed", x + 1.5, y0 - 2, 0.1, check=False)
    for b in BUILDINGS:
        T = Matrix(b["matrix"])
        for dx, asset in [(-3.5, "bin"), (3.4, "bike")]:
            p = T @ Vector((dx, -3, 0.05))
            furnishing(c, asset, p.x, p.y, angle=b["angle"])
    for i, extra in enumerate(extras):
        placed = None
        candidates = [
            (court_x + dx, court_y + dy) for dy in [-5, 0, 5] for dx in [-10, -5, 5, 10]
        ]
        candidates += [
            (x0 + 5 + j * (x1 - x0 - 10) / 13, y0 + 5 + k * (y1 - y0 - 10) / 9)
            for k in range(10)
            for j in range(14)
        ]
        for x, y in candidates:
            placed = furnishing(c, extra, x, y, 0.05, math.pi)
            if placed:
                break
        if not placed:
            raise RuntimeError("No collision-free location for " + extra)
    # Landscaped waterside pocket outside the occupied block, using the real
    # recessed basin/channel and its original bridge/bank meshes.
    water_info = None
    if land in {"lake", "river"}:
        asset = load(land)
        wm = meta(land)
        ww, wd, wh = wm["dimensions"]
        wx = x0 - 18 - ww / 2
        wy = cy
        ob = furnishing(c, land, wx, wy, -2.0 if land == "lake" else -1.8, check=False)
        bpy.context.view_layer.update()
        # Cut terrain with the full water basin; keep original shore geometry.
        if land == "lake":
            src = next(o for o in asset.all_objects if "lake_water_volume" in o.name)
            cutter = src.copy()
            cutter.data = src.data.copy()
            cutter.parent = None
            cutter.constraints.clear()
            c.objects.link(cutter)
            cutter.matrix_world = ob.matrix_world @ src.matrix_world
            cutter.location.z += 1
            cutter.scale.z *= 3
            ground.data = ground.data.copy()
            bpy.context.view_layer.objects.active = ground
            mod = ground.modifiers.new("Existing basin terrain opening", "BOOLEAN")
            mod.operation = "DIFFERENCE"
            mod.solver = "EXACT"
            mod.object = cutter
            bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.data.objects.remove(cutter, do_unlink=True)
        else:
            src = next(
                o for o in asset.all_objects if "incised_alluvial_channel" in o.name
            )
            ps = [ob.matrix_world @ src.matrix_world @ Vector(v) for v in src.bound_box]
            wl = [min(p[k] for p in ps) for k in range(3)]
            whi = [max(p[k] for p in ps) for k in range(3)]
            bpy.data.objects.remove(ground, do_unlink=True)
            for xa, xb, ya, yb in [
                (cx - 600, wl[0], cy - 600, cy + 600),
                (whi[0], cx + 600, cy - 600, cy + 600),
                (wl[0], whi[0], cy - 600, wl[1]),
                (wl[0], whi[0], whi[1], cy + 600),
            ]:
                surface(
                    c,
                    "asphalt",
                    "terrain_around_channel",
                    ((xa + xb) / 2, (ya + yb) / 2, -0.2),
                    (xb - xa, yb - ya, 0.3),
                    earth,
                )
        water_info = {"asset": land, "center": [wx, wy], "bounds": OCCUPIED[-1]}
        for i in range(8):
            instance(
                c,
                tree,
                "waterside_tree",
                (wx - ww / 2 - 3, wy - wd / 2 + i * wd / 7, 0.04),
                i * 1.23,
                0.85,
            )
        surface(
            c,
            "paving",
            "waterside_walk",
            ((x0 + wx + ww / 2) / 2, cy, 0.01),
            (x0 - (wx + ww / 2), 3.1, 0.14),
        )
    # Long street edges have planting, so the block never ends in a naked plane.
    return dict(
        block_bounds=[[x0, y0, 0], [x1, y1, hi[2]]],
        water=water_info,
        parking=True,
        landscape=land,
        terrace_assets="three native furniture/tableware variants",
    )


def light(c, index):
    s = bpy.context.scene
    w = bpy.data.worlds.new("connect4:physical_daylight")
    w.use_nodes = True
    s.world = w
    n = w.node_tree.nodes
    l = w.node_tree.links
    sky = n.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(38 + index % 5 * 4)
    sky.sun_rotation = math.radians(100 + index % 6 * 17)
    sky.sun_disc = False
    n["Background"].inputs["Strength"].default_value = 0.10
    l.new(sky.outputs["Color"], n["Background"].inputs["Color"])
    data = bpy.data.lights.new("connect4:sun", "SUN")
    data.energy = 2.3
    data.angle = 0.045
    ob = bpy.data.objects.new(data.name, data)
    c.objects.link(ob)
    ob.rotation_euler = (0.50, -0.23, -0.8 + index % 4 * 0.2)
    for b in BUILDINGS:
        if not b["enterable"]:
            continue
        info = meta(b["asset"])
        T = Matrix(b["matrix"])
        z = info["floor_z"]
        rc = info["room_center"]
        for x, y in [(rc[0] - 1.8, 2.5), (rc[0] + 1.8, 4.5), (0, 1.5)]:
            height = 6.1 if b["asset"] == "fire" else z + 2.75
            add_area(
                c,
                "Occupied interior",
                T @ Vector((x, y, height)),
                T @ Vector((x, y, z)),
                160 if b["asset"] != "fire" else 700,
                2.2,
                (1, 0.92, 0.82),
            )
    s.view_settings.view_transform = "AgX"
    s.view_settings.look = "AgX - Medium High Contrast"
    s.view_settings.exposure = 0.1


def cameras(c, bounds, environment, index):
    s = bpy.context.scene
    cam = bpy.data.objects.new(
        "connect4:camera", bpy.data.cameras.new("connect4:camera")
    )
    c.objects.link(cam)
    s.camera = cam
    cam.data.clip_start = 0.05
    cam.data.clip_end = 1800
    s.render.resolution_x = 1920
    s.render.resolution_y = 1080
    s.render.resolution_percentage = 100
    shots = {}
    primary = BUILDINGS[0]
    info = meta(primary["asset"])
    z = info["floor_z"] + 1.6
    rc = info["room_center"]
    inside = info["inside_y"]

    def shot(name, p, t, lens=24, **kw):
        shots[name] = dict(position=list(p), target=list(t), lens=lens, **kw)

    if "source_shots" in info:
        for name in [
            "interior_wide",
            "interior_diagonal",
            "interior_activity",
            "interior_reverse",
            "detail_primary",
            "detail_secondary",
        ]:
            if name in info["source_shots"]:
                shots[name] = copy.deepcopy(info["source_shots"][name])
    else:
        shot("interior_wide", (0, 1.1, z), (*rc, info["floor_z"] + 1.3), 22)
        shot(
            "interior_activity",
            (0, inside, z),
            (rc[0], max(4, rc[1]), info["floor_z"] + 1.2),
            27,
        )
        shot("interior_reverse", (0, inside, z), (0, -7, z - 0.1), 22)
        shot("interior_diagonal", (0.25, 1.1, z), (rc[0], rc[1], z - 0.3), 24)
        shot("detail_primary", (0, inside, z), (rc[0], rc[1], z - 0.5), 42)
        shot("detail_secondary", (0.25, inside, z), (rc[0], rc[1] + 1, z - 0.3), 50)
    for dist, label in [(1.2, "near"), (3.2, "middle"), (6.5, "far")]:
        for sign, side in [(0, "axial"), (-1, "left"), (1, "right")]:
            shot(
                "outside_to_inside_" + label + "_" + side,
                (sign * min(0.45, dist * 0.1), -dist, z),
                (rc[0] * 0.10, 3.5, z - 0.1),
                25 if label != "far" else 32,
            )
    # Keep broad contextual views distinct from the traversable axial path.
    for dist, label in [(1.0, "near"), (min(inside, 2.0), "middle"), (inside, "far")]:
        for sign, side in [(0, "axial"), (-1, "left"), (1, "right")]:
            shot(
                "inside_to_outside_" + label + "_" + side,
                (sign * 0.24, dist, z),
                (sign * 1.2, -8, z - 0.08),
                22 + (label == "far") * 4,
            )
    if "source_shots" in info:
        for direction in ["inside_to_outside", "outside_to_inside"]:
            for label in ["middle", "far"]:
                source = direction + "_" + label + "_oblique"
                if source in info["source_shots"]:
                    shots[direction + "_room_context_" + label] = copy.deepcopy(
                        info["source_shots"][source]
                    )
    lo, hi = map(Vector, bounds)
    cx = (lo.x + hi.x) / 2
    cy = (lo.y + hi.y) / 2
    span = max(hi.x - lo.x, hi.y - lo.y)
    target = Vector((cx, cy, min(5, hi.z * 0.2)))
    points = [
        Vector((x, y, z0))
        for b in BUILDINGS
        for x in [b["bounds"][0][0], b["bounds"][1][0]]
        for y in [b["bounds"][0][1], b["bounds"][1][1]]
        for z0 in [0, b["bounds"][1][2]]
    ]
    for suffix, sgn in [("overview", 1), ("overview_reverse", -1)]:
        direction = Vector((span * 0.72 * sgn, -span * 0.85, span * 0.69))
        cam.data.lens = 40
        for _ in range(45):
            cam.location = target + direction
            cam.rotation_euler = (
                (target - cam.location).to_track_quat("-Z", "Y").to_euler()
            )
            bpy.context.view_layer.update()
            uv = [world_to_camera_view(s, cam, p) for p in points]
            if all(0.08 < v.x < 0.92 and 0.09 < v.y < 0.91 and v.z > 0 for v in uv):
                break
            direction *= 1.06
        shot("district_" + suffix, cam.location, target, 40)
    shot("district_street", (0, -8, z + 0.2), (0, 2, 3.0), 22)
    shot("entrance_context", (-2, -7, z + 0.1), (0, 1, 2), 25)
    shot("exterior_wide", (0, -13, 4), (rc[0], 3, 2.7), 24)
    shot("exterior_left", (-4, -9, 2.2), (0, 2, 2), 24)
    shot("exterior_right", (4, -9, 2.2), (rc[0], 2, 2), 24)
    shot("garden_context", (cx, lo.y - 6, 5), (cx, cy, 1.2), 30)
    # A second real interior proves that the district is more than a facade set.
    secondary = next(b for b in BUILDINGS[1:] if b["enterable"])
    si = meta(secondary["asset"])
    T = Matrix(secondary["matrix"])
    sz = si["floor_z"] + 1.6
    shot(
        "neighbor_interior",
        T @ Vector((0, 1.1, sz)),
        T @ Vector((*si["room_center"], sz - 0.3)),
        23,
    )
    shot(
        "neighbor_outside_to_inside",
        T @ Vector((0, -2.5, sz)),
        T @ Vector((0, 2, sz - 0.1)),
        25,
    )
    shot(
        "neighbor_inside_to_outside",
        T @ Vector((0, min(2, si["inside_y"]), sz)),
        T @ Vector((0, -8, sz - 0.1)),
        24,
    )
    if environment["water"]:
        wx, wy = environment["water"]["center"]
        shot("waterside_context", (wx - 18, wy - 23, 14), (cx, cy, 2), 30)
        shot("shore_detail", (wx - 7, wy - 10, 3), (wx, wy, 0), 35)
    else:
        shot("public_space_detail", (cx + 7, cy - 8, 2.2), (cx - 5, cy, 1.0), 30)
    return shots


def main(index):
    spec = SCENES[index]
    dest = O / spec[0]
    dest.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    s = bpy.context.scene
    s.name = "CONNECT4_" + spec[0]
    buildings = coll("Full_buildings_and_furnished_interiors")
    outside = coll("Connected_streets_and_landscape")
    lights = coll("Physical_lighting_and_cameras")
    bounds = layout(spec, buildings, index)
    print("LAYOUT_READY", spec[0], flush=True)
    environment = site(spec, outside, bounds, index)
    print("SITE_READY", spec[0], flush=True)
    light(lights, index)
    shots = cameras(lights, bounds, environment, index)
    # Parameterised material finishes vary authored cladding, without stretching or
    # reducing a building. All local instances share the same coherent palette.
    palettes = [
        (0.22, 0.30, 0.25),
        (0.30, 0.18, 0.115),
        (0.12, 0.20, 0.28),
        (0.33, 0.30, 0.23),
        (0.25, 0.22, 0.29),
    ]
    for mat in bpy.data.materials:
        if mat.library or not mat.use_nodes:
            continue
        if any(
            t in mat.name.lower()
            for t in ["awning_canvas", "facade_dark", "cladding_charcoal"]
        ):
            p = mat.node_tree.nodes.get("Principled BSDF")
            if p and not p.inputs["Base Color"].is_linked:
                p.inputs["Base Color"].default_value = (*palettes[index % 5], 1)
    fix_fonts()
    s.render.engine = "CYCLES"
    s.cycles.samples = 128
    s.cycles.max_bounces = 12
    s.cycles.transmission_bounces = 10
    s.cycles.transparent_max_bounces = 16
    s.cycles.use_denoising = True
    s.render.fps = 24
    bpy.context.view_layer.update()
    for ob in outside.objects:
        if ob.get("expected_dimensions"):
            expected = ob["expected_dimensions"]
            if any(
                abs(ob.dimensions[i] - expected[i]) > max(0.025, expected[i] * 0.005)
                for i in range(3)
            ):
                raise RuntimeError(
                    "Architectural surface scale mismatch "
                    + ob.name
                    + " "
                    + str(list(ob.dimensions))
                    + " "
                    + str(list(expected))
                )
    info = meta(spec[2])
    m = dict(
        builder_revision=5,
        scene=spec[0],
        title=spec[1],
        focus=spec[2],
        seed=240924 + index,
        layout=spec[4],
        landscape=spec[5],
        extras=spec[6],
        building_count=len(BUILDINGS),
        buildings=BUILDINGS,
        site_bounds=bounds,
        environment=environment,
        shots=shots,
        floor_z=info["floor_z"],
        video_inside_y=info["inside_y"],
        asset_policy="Only existing full-detail assets; no proxies, decimation, image backdrops or render-hidden architecture",
        blend="scene.blend",
        status="built_pending_geometry_and_visual_review",
    )
    for lib in bpy.data.libraries:
        path = Path(bpy.path.abspath(lib.filepath))
        candidate = A / path.name
        lib.filepath = str(candidate if candidate.exists() else path)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(dest / "scene.blend"), compress=True, relative_remap=True
    )
    (dest / "scene_manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2)
    )
    (dest / "asset_placements.json").write_text(
        json.dumps(LEDGER, ensure_ascii=False, indent=2)
    )
    from refine_connect4_site import refine

    refine(spec[0])
    print("CONNECT4_BUILT", spec[0], len(BUILDINGS), len(shots), flush=True)


if __name__ == "__main__":
    main(int(sys.argv[-1]))

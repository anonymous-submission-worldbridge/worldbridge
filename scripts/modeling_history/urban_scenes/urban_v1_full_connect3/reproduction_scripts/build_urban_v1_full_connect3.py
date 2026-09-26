"""Full 3D cluster generation using only attributed existing authored assets."""
import bpy, sys, json, math, os, random, copy
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect3_plan import SCENES
import build_urban_v1_full_connect as OLD

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
A = O / "shared_assets"
CORE = {"restaurant", "cafe", "market", "hospital", "pharmacy", "library"}
CACHE = {}
PLACEMENTS = []


def load(key, local=False):
    if key in CACHE:
        return CACHE[key]
    with bpy.data.libraries.load(str(A / (key + ".blend")), link=not local) as (a, b):
        b.collections = ["ASSET_" + key]
    c = b.collections[0]
    assert c, key
    CACHE[key] = c
    return c


def meta(key):
    return json.loads((A / (key + ".json")).read_text())


def col(name):
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def instance(c, asset, name, loc, angle=0, scale=1):
    ob = bpy.data.objects.new("connect3:" + name, None)
    c.objects.link(ob)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = asset
    ob.location = loc
    ob.rotation_euler.z = angle
    ob.scale = (scale,) * 3 if isinstance(scale, (int, float)) else scale
    ob["asset_source"] = asset.get(
        "source_blend",
        asset.library.filepath if asset.library else "existing_procedural_library",
    )
    return ob


def furniture(c, key, loc, angle=0, scale=1):
    m = meta(key)
    anchor = Vector((0, m["bounds"][0][1], m["bounds"][0][2]))
    factor = scale if isinstance(scale, (int, float)) else 1
    position = Vector(loc) - Matrix.Rotation(angle, 4, "Z") @ (anchor * factor)
    ob = instance(c, load(key), key, position, angle, scale)
    ob["normalized_anchor"] = True
    return ob


def place_building(c, key, x, y, angle=0, primary=False):
    m = meta(key)
    lo, hi = map(Vector, m["bounds"])
    asset = load(key, local=primary)
    center = Vector(((lo.x + hi.x) / 2, lo.y, 0))
    rot = Matrix.Rotation(angle, 4, "Z")
    p = Vector((x, y, 0)) - rot @ center
    if primary:
        p = Vector((0, 0, 0))
    if primary:
        c.children.link(asset)
    else:
        instance(c, asset, "building_" + key, p, angle)
    points = [
        rot @ Vector((xx, yy, zz)) + p
        for xx in (lo.x, hi.x)
        for yy in (lo.y, hi.y)
        for zz in (lo.z, hi.z)
    ]
    bounds = [
        [min(v[k] for v in points) for k in range(3)],
        [max(v[k] for v in points) for k in range(3)],
    ]
    PLACEMENTS.append(
        {
            "asset": key,
            "position": list(p),
            "angle": angle,
            "bounds": bounds,
            "source": m["source"],
            "geometry": {
                "meshes": m["mesh_instances"],
                "vertices": m["evaluated_vertices"],
            },
        }
    )
    return PLACEMENTS[-1]


def copy_part(c, src, name, location, dimensions):
    n = src.copy()
    c.objects.link(n)
    n.parent = None
    n.name = "connect3:" + name
    n.rotation_euler = (0, 0, 0)
    n.scale = (1, 1, 1)
    n.location = location
    bpy.context.view_layer.update()
    n.dimensions = dimensions
    n["source_object"] = src.name
    return n


def improve_interior(key, asset, seed):
    rng = random.Random(seed)
    with bpy.data.libraries.load(str(A / "native_variants.blend"), link=True) as (a, b):
        b.collections = list(a.collections)
    native = {c.name: c for c in b.collections}
    # The existing master furniture keeps its position and supports; the native
    # table replaces only the older body, preserving all individual place settings.
    table = bpy.data.collections.get("DINING_TABLE_MASTER")
    if table and not table.library and key in {"restaurant", "cafe"}:
        for ob in list(table.objects):
            if ob.type == "MESH":
                table.objects.unlink(ob)
        instance(
            table,
            native["NATIVE3_TableDiningFactory_0"],
            "native_dining_table",
            (0, 0, 0),
            scale=(0.62, 0.79, 0.8 / 0.845746),
        )
    for c in list(bpy.data.collections):
        if c.library:
            continue
        for ob in list(c.objects):
            old = ob.instance_collection
            if old and (
                "NATIVE_ChairFactory" in old.name or old.name == "DINING_CHAIR_MASTER"
            ):
                ob.instance_collection = native[
                    "NATIVE3_ChairFactory_" + str(rng.randrange(6))
                ]
            if old and "NATIVE_FoodBoxFactory" in old.name:
                ob.instance_collection = load("carton")
                ob.scale = tuple(s * 0.52 for s in ob.scale)
    # Additional working-room objects are native generated assets at real scale.
    manifest = json.loads(
        (O / "source_snapshots" / key / "scene_manifest.json").read_text()
    )
    floor = manifest["floor_z"]
    if key == "restaurant":
        instance(
            asset,
            native["NATIVE3_FloorLampFactory_0"],
            "dining_floor_lamp",
            (-12.5, 7.8, floor),
        )
        for x, y in [(-11.35, 2.27), (-9.05, 2.67), (-6.35, 2.57)]:
            furniture(asset, "pastry", (x - 0.15, y - 0.15, floor + 0.8), scale=0.55)
    if key == "cafe":
        instance(
            asset,
            native["NATIVE3_FloorLampFactory_1"],
            "cafe_floor_lamp",
            (-6.7, 7.3, floor),
        )
    # Existing exterior facades get material variants; geometry stays full detail.
    colors = [
        (0.22, 0.30, 0.27),
        (0.32, 0.19, 0.11),
        (0.13, 0.19, 0.25),
        (0.27, 0.25, 0.21),
    ]
    for mat in list(bpy.data.materials):
        if mat.library or not mat.use_nodes:
            continue
        low = mat.name.lower()
        if any(
            t in low
            for t in ["facade_dark", "fascia", "awning_canvas", "cladding_charcoal"]
        ):
            bs = mat.node_tree.nodes.get("Principled BSDF")
            if bs and not bs.inputs["Base Color"].is_linked:
                bs.inputs["Base Color"].default_value = (*colors[seed % 4], 1)
    return manifest


def layout_buildings(spec, c):
    key, title, focus, neighbors, layout, extras = spec
    main = meta(focus)
    lo, hi = map(Vector, main["bounds"])
    cx = (lo.x + hi.x) / 2
    place_building(c, focus, 0, 0, primary=True)
    gap = 2.8 + (list(s[0] for s in SCENES).index(key) % 3) * 0.55
    widths = [meta(n)["dimensions"][0] for n in neighbors]
    depths = [meta(n)["dimensions"][1] for n in neighbors]
    for j, n in enumerate(neighbors):
        w, d = widths[j], depths[j]
        if layout in {"courtyard", "offset_square", "garden"}:
            if j == 0:
                x, y, a = lo.x - gap, -2 if layout != "garden" else -5, math.pi / 2
            elif j == 1:
                x, y, a = (
                    cx + (3 if layout == "offset_square" else 0),
                    -19 - (2 if focus in {"hospital", "library", "pharmacy"} else 0),
                    math.pi,
                )
            else:
                x, y, a = hi.x + gap + w / 2, 0, 0
        elif layout in {"corner", "campus"}:
            if j == 0:
                x, y, a = hi.x + gap, -6, -math.pi / 2
            else:
                x, y, a = lo.x - gap - w / 2, 2 if layout == "campus" else 0, 0
        elif layout in {"staggered", "promenade", "service", "forecourt"}:
            if j == 0:
                x, y, a = (
                    lo.x - gap - w / 2,
                    3 if layout in {"staggered", "service"} else 0,
                    0,
                )
            else:
                x, y, a = hi.x + gap + w / 2, -3 if layout == "staggered" else 2, 0
        elif layout == "mews":
            if j == 0:
                x, y, a = lo.x - gap - w / 2, 0, 0
            elif j == 1:
                x, y, a = hi.x + gap + w / 2, 2, 0
            else:
                x, y, a = cx, -19, math.pi
        else:
            if j == 0:
                x, y, a = lo.x - gap - w / 2, 1, 0
            else:
                x, y, a = hi.x + gap + w / 2, 2, 0
        if layout == "offset_square" and j == 1:
            x = max(x, PLACEMENTS[1]["bounds"][1][0] + gap + w / 2)
        place_building(c, n, x, y, a)
    # Bounding-box intersection is conservative and includes signs/roof equipment.
    for j, b in enumerate(PLACEMENTS):
        for other in PLACEMENTS[:j]:
            if all(
                min(b["bounds"][1][k], other["bounds"][1][k])
                - max(b["bounds"][0][k], other["bounds"][0][k])
                > 0.05
                for k in (0, 1)
            ):
                raise RuntimeError(
                    "Building overlap " + str((b["asset"], other["asset"]))
                )
    return cx


def site(spec, c, cx):
    key, title, focus, neighbors, layout, extras = spec
    rng = random.Random(key)
    lo = Vector([min(b["bounds"][0][k] for b in PLACEMENTS) for k in range(3)])
    hi = Vector([max(b["bounds"][1][k] for b in PLACEMENTS) for k in range(3)])
    with bpy.data.libraries.load(str(A / "site_components.blend"), link=True) as (a, b):
        b.collections = list(a.collections)
    components = {x.name: list(x.objects)[0] for x in b.collections}
    pave = components["ASSET_paving"]
    asphalt = components["ASSET_asphalt"]
    joint = components["ASSET_joint"]
    mx, my = (lo.x + hi.x) / 2, (lo.y + hi.y) / 2
    ground = copy_part(
        c, asphalt, "continuous_ground", (mx, my, -0.12), (1800, 1800, 0.2)
    )
    # Material inherits textured asphalt; no fake image backdrop.
    ground.material_slots[0].link = "OBJECT"
    mat = bpy.data.materials.new("connect3:earth")
    mat.diffuse_color = (0.085, 0.105, 0.06, 1)
    mat.use_nodes = True
    bs = mat.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = (0.085, 0.105, 0.06, 1)
    bs.inputs["Roughness"].default_value = 0.96
    ground.material_slots[0].material = mat
    ns = mat.node_tree.nodes
    lk = mat.node_tree.links
    tex = ns.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 1.6
    tex.inputs["Detail"].default_value = 4
    geo = ns.new("ShaderNodeNewGeometry")
    lk.new(geo.outputs["Position"], tex.inputs["Vector"])
    ramp = ns.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.035, 0.042, 0.025, 1)
    ramp.color_ramp.elements[1].color = (0.15, 0.16, 0.09, 1)
    lk.new(tex.outputs["Fac"], ramp.inputs[0])
    lk.new(ramp.outputs["Color"], bs.inputs["Base Color"])
    bump = ns.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.3
    bump.inputs["Distance"].default_value = 0.025
    lk.new(tex.outputs["Fac"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bs.inputs["Normal"])
    # Compact forecourt with physical expansion joints and a connected service lane.
    x0, x1 = lo.x - 2, hi.x + 2
    y0 = -17 if layout not in {"courtyard", "offset_square", "garden", "mews"} else -19
    y1 = -1.9
    copy_part(
        c,
        pave,
        "connected_public_paving",
        ((x0 + x1) / 2, (y0 + y1) / 2, 0.065),
        (x1 - x0, y1 - y0, 0.13),
    )
    for x in range(math.ceil(x0), math.floor(x1), 2):
        copy_part(
            c,
            joint,
            "paving_joint_x",
            (x, (y0 + y1) / 2, 0.132),
            (0.012, y1 - y0, 0.004),
        )
    for y in range(math.ceil(y0), math.floor(y1), 2):
        copy_part(
            c,
            joint,
            "paving_joint_y",
            ((x0 + x1) / 2, y, 0.132),
            (x1 - x0, 0.012, 0.004),
        )
    # Detailed existing flower assemblies break up the paved perimeter.
    for i in range(8):
        x = x0 + 2 + (x1 - x0 - 4) * i / 7
        if abs(x) > 2.4:
            furniture(c, "flowerbed", (x, -16.1, 0.14), rng.uniform(-0.15, 0.15), 0.9)
    # The entrance apron meets the actual threshold while respecting the open leaf.
    copy_part(c, pave, "entrance_apron", (0, -1.0, 0.065), (2.4, 2.0, 0.13))
    # Keep the complete corridor |x|<1.5 empty from the main entrance to the street.
    positions = [(cx - 5, -5), (cx - 8, -10), (cx + 5, -6), (cx + 8, -11)]
    for i, (x, y) in enumerate(positions):
        if abs(x) < 2.2:
            x += 4.3
        if x < x0 + 2 or x > x1 - 2:
            continue
        furniture(c, "cafe_set", (x, y, 0.14), rng.uniform(-0.2, 0.2))
        furniture(
            c, "flowerbed", (x - 1.7, y + 1.8, 0.14), rng.uniform(0, math.pi * 2), 0.88
        )
    for i, x in enumerate([x0 + 2, x1 - 2, cx - 7, cx + 7]):
        if abs(x) > 2.2:
            furniture(c, "streetlight", (x, -14.5, 0.14), math.pi if i % 2 else 0)
    for x in [cx - 3.8, cx + 4.3]:
        if abs(x) > 1.8:
            furniture(c, "bin", (x, -3, 0.14))
            furniture(c, "bike", (x + 0.9, -3, 0.14), math.pi / 2)
    # Botanical geometry from the reference scene, with multiple sampled transforms.
    with bpy.data.libraries.load(str(A / "reference08_tree.blend"), link=True) as (
        a,
        b,
    ):
        b.collections = ["full02:MASTER:TreeFactory:42"]
    tree = b.collections[0]
    treepositions = [
        (x0 - 3, -7),
        (x1 + 3, -8),
        (cx - 9, -16),
        (cx + 9, -16),
        (lo.x - 4, hi.y + 3),
        (hi.x + 4, hi.y + 3),
    ]
    for i, (x, y) in enumerate(treepositions):
        if any(
            b["bounds"][0][0] - 2 < x < b["bounds"][1][0] + 2
            and b["bounds"][0][1] - 2 < y < b["bounds"][1][1] + 2
            for b in PLACEMENTS
        ):
            continue
        instance(
            c,
            tree,
            "reference_botanical_tree",
            (x, y, 0.0),
            rng.uniform(0, 6.28),
            rng.uniform(0.64, 0.82),
        )
    # Full second botanical species kept outside building envelopes.
    furniture(c, "tree619", (lo.x - 9, hi.y / 2, 0), math.pi / 2, 0.8)
    # Additional seating uses the existing manufactured bench assembly.
    if (A / "bench.blend").exists():
        for x in range(math.ceil(x0 + 4), math.floor(x1 - 3), 6):
            if abs(x) > 3:
                furniture(c, "bench", (x, -13.5, 0.14), 0)
    # All accessories have saved assembly provenance, no stand-in meshes.
    offset = 0
    for extra in extras:
        if extra in {"lake", "river"}:
            lm = meta(extra)
            if extra == "lake":
                water = furniture(c, extra, (cx, -17, -2.0), math.pi)
            else:
                water = furniture(c, extra, (cx + 21, -31, -1.8), math.pi / 2)
            # The existing land slab ends at the shoreline, exposing the recessed water.
            ground.location.y = 883.5
            ground.dimensions.y = 1800
            continue
        em = meta(extra)
        w, d, h = em["dimensions"]
        x = x0 + w / 2 + 1 + offset
        y = -15.0
        if abs(x) < w / 2 + 1.8:
            x = x1 - w / 2 - 1 - offset
        ob = furniture(c, extra, (x, y, 0.14))
        offset += w + 1.4
    return [list(lo), list(hi)]


def lighting(focus, manifest, c, seed):
    scene = bpy.context.scene
    world = bpy.data.worlds.new("connect3:daylight")
    world.use_nodes = True
    scene.world = world
    ns = world.node_tree.nodes
    lk = world.node_tree.links
    sky = ns.new("ShaderNodeTexSky")
    sky.sky_type = "MULTIPLE_SCATTERING"
    sky.sun_elevation = math.radians(36 + (seed % 4) * 5)
    sky.sun_rotation = math.radians(125 + (seed % 5) * 12)
    sky.sun_disc = False
    ns["Background"].inputs["Strength"].default_value = 0.08
    lk.new(sky.outputs["Color"], ns["Background"].inputs["Color"])
    sun = bpy.data.lights.new("connect3:sun", "SUN")
    sun.energy = 2.4
    sun.angle = math.radians(3)
    ob = bpy.data.objects.new("connect3:sun", sun)
    c.objects.link(ob)
    ob.rotation_euler = (0.55, -0.28, -0.45 + (seed % 4) * 0.1)
    for p in PLACEMENTS:
        key = p["asset"]
        if key not in CORE:
            continue
        s = json.loads(
            (O / "source_snapshots" / key / "scene_manifest.json").read_text()
        )["spec"]
        cx = s["center"]
        w = s["width"]
        mat = Matrix.Translation(Vector(p["position"])) @ Matrix.Rotation(
            p["angle"], 4, "Z"
        )
        for x in [cx - 2, cx + 2]:
            loc = mat @ Vector(
                (x, 4.6, 3.6 if key in {"cafe", "restaurant", "market"} else 4.0)
            )
            target = mat @ Vector((x, 4.6, 0))
            OLD.add_area(c, "Indoor practical", loc, target, 160, 3, (1, 0.88, 0.74))
    OLD.add_area(c, "Facade daylight", (0, -7, 10), (0, 3, 2), 750, 10, (0.80, 0.9, 1))
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = 0.15


def cameras(manifest, bounds, c, seed):
    shots = copy.deepcopy(manifest["shots"])
    lo, hi = map(Vector, bounds)
    cx = (lo.x + hi.x) / 2
    cy = (lo.y + hi.y) / 2
    width = hi.x - lo.x
    depth = hi.y - lo.y
    shots["cluster_overview"] = {
        "position": [hi.x + max(19, width * 0.43), -9, max(19, width * 0.40)],
        "target": [cx, -6, 2.6],
        "lens": 38,
    }
    shots["cluster_street"] = {
        "position": [cx, -16, 2.3],
        "target": [cx, 4, 3.0],
        "lens": 22,
    }
    # Distinct focal lengths and distances; both connection directions have 6 shots.
    # Preserve a separate main-building exterior photograph.
    # Additional room-context connections show furniture plus the exterior.
    focus = manifest["scene"]
    z = manifest["floor_z"] + 1.6
    xs = {
        "restaurant": [-1.6, -3.6],
        "cafe": [-1.1, -1.7],
        "market": [-0.6, 0.6],
        "hospital": [-1.2, 1.2],
        "pharmacy": [1.1, 1.8],
        "library": [-2.0, 2.0],
    }[focus]
    for j, x in enumerate(xs):
        shots["inside_to_outside_room_" + str(j)] = {
            "position": [x, 2.6 + j * 1.7, z],
            "target": [0, -6, z - 0.15],
            "lens": 21 + j * 2,
        }
        shots["outside_to_inside_room_" + str(j)] = {
            "position": [(j * 2 - 1) * 0.35, -1.4 - j * 0.6, z],
            "target": [xs[j] * 0.45, 4, z - 0.15],
            "lens": 22 + j * 2,
        }
    # Existing tested interior shots retain the entire building geometry.
    scene = bpy.context.scene
    ob = bpy.data.objects.new(
        "connect3:camera", bpy.data.cameras.new("connect3:camera")
    )
    c.objects.link(ob)
    scene.camera = ob
    ob.data.clip_start = 0.05
    ob.data.clip_end = 2500
    pose = shots["cluster_overview"]
    ob.location = pose["position"]
    ob.rotation_euler = (
        (Vector(pose["target"]) - ob.location).to_track_quat("-Z", "Y").to_euler()
    )
    ob.data.lens = pose["lens"]
    # Fit all complete building corners inside the overview image.
    from bpy_extras.object_utils import world_to_camera_view

    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    sh = shots["cluster_overview"]
    target = Vector(sh["target"])
    direction = Vector(sh["position"]) - target
    corners = [
        Vector((x, y, z))
        for b in PLACEMENTS
        for x in [b["bounds"][0][0], b["bounds"][1][0]]
        for y in [b["bounds"][0][1], b["bounds"][1][1]]
        for z in [b["bounds"][0][2], b["bounds"][1][2]]
    ]
    for _ in range(30):
        ob.location = target + direction
        ob.rotation_euler = (target - ob.location).to_track_quat("-Z", "Y").to_euler()
        ob.data.lens = sh["lens"]
        bpy.context.view_layer.update()
        uv = [world_to_camera_view(scene, ob, p) for p in corners]
        if all(0.055 < p.x < 0.945 and 0.07 < p.y < 0.94 and p.z > 0 for p in uv):
            break
        direction *= 1.07
    sh["position"] = list(ob.location)
    return shots


def main(index):
    spec = SCENES[index]
    key, title, focus, neighbors, layout, extras = spec
    dest = O / key
    dest.mkdir(exist_ok=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.name = "CONNECT3_" + key
    buildings = col("Full_buildings_and_furnished_interiors")
    outside = col("Connected_streets_and_landscape")
    lights = col("Physical_lighting_and_cameras")
    load(focus, local=True)
    manifest = improve_interior(focus, CACHE[focus], index + 9301)
    cx = layout_buildings(spec, buildings)
    bounds = site(spec, outside, cx)
    lighting(focus, manifest, lights, index)
    shots = cameras(manifest, bounds, lights, index)
    if focus == "restaurant":
        shots["detail_secondary"] = {
            "position": [-6.1, 3.85, 2.4],
            "target": [-7.95, 5.37, 1.13],
            "lens": 42,
        }
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 96
    scene.cycles.max_bounces = 10
    scene.cycles.transmission_bounces = 8
    scene.cycles.transparent_max_bounces = 16
    scene.cycles.use_denoising = True
    scene.render.fps = 24
    scene.render.resolution_x = 1920
    scene.render.resolution_y = 1080
    scene.render.resolution_percentage = 100
    m = {
        "scene": key,
        "title": title,
        "focus": focus,
        "layout": layout,
        "seed": index + 9301,
        "buildings": PLACEMENTS,
        "building_count": len(PLACEMENTS),
        "site_bounds": bounds,
        "shots": shots,
        "floor_z": manifest["floor_z"],
        "front_y": 0,
        "door_x": 0,
        "video_inside_y": 3.0,
        "blend": "scene.blend",
        "asset_policy": "Existing complete authored meshes and Infinigen assets only; no proxies, no decimation, no image backdrops",
        "extras": extras,
    }
    for lib in bpy.data.libraries:
        lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
    bpy.context.preferences.filepaths.save_version = 0
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.ops.wm.save_as_mainfile(
        filepath=str(dest / "scene.blend"), compress=True, relative_remap=True
    )
    for lib in bpy.data.libraries:
        lib.filepath = "//" + os.path.relpath(bpy.path.abspath(lib.filepath), dest)
    bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
    (dest / "scene_manifest.json").write_text(
        json.dumps(m, ensure_ascii=False, indent=2)
    )
    print("CONNECT3_BUILT", key, flush=True)


if __name__ == "__main__":
    main(int(sys.argv[-1]))

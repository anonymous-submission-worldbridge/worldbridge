"""Adapt the user's existing full-detail models into measured, usable buildings.

No asset mesh is substituted by proxy geometry. Door articulation and permanent
architectural openings are recorded, with the unmodified source kept intact.
"""
import bpy, json, math, os, sys, re
from mathutils import Matrix, Vector
from pathlib import Path

R = next(p for p in Path(__file__).resolve().parents if (p / "worldbridge").is_dir())
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, A, PREVIOUS, CORE
import build_urban_v1_full_connect as old
import build_urban_v1_full_connect2 as util
import prepare_connect3_assets as measures
from fix_connect3_fonts import fix as fix_fonts

CORE_SOURCE = dict(
    restaurant="dining_courtyard",
    cafe="coffee_corner",
    market="market_lane",
    hospital="medical_court",
    pharmacy="pharmacy_square",
    library="reading_court",
)


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


def load(path, name, link=False):
    with bpy.data.libraries.load(str(path), link=link) as (src, dst):
        dst.collections = [name]
    if dst.collections[0] is None:
        raise RuntimeError((path, name))
    return dst.collections[0]


def root(c):
    bpy.context.scene.collection.children.link(c)
    bpy.context.view_layer.update()


def inst(c, asset, name, loc, scale=1, angle=0):
    ob = bpy.data.objects.new("connect4:" + name, None)
    c.objects.link(ob)
    ob.instance_type = "COLLECTION"
    ob.instance_collection = asset
    ob.location = loc
    ob.scale = (scale,) * 3 if isinstance(scale, (float, int)) else scale
    ob.rotation_euler.z = angle
    ob["asset_source"] = asset.library.filepath if asset.library else asset.name
    return ob


def remap():
    for lib in bpy.data.libraries:
        p = Path(bpy.path.abspath(lib.filepath))
        candidate = A / p.name
        lib.filepath = str(candidate if candidate.exists() else p)


def save(key, c, source, extra=None):
    rootnames = {x.name for x in bpy.context.scene.collection.children}
    for child in list(bpy.context.scene.collection.children):
        if child != c:
            bpy.context.scene.collection.children.unlink(child)
    if c.name not in rootnames:
        root(c)
    data = measures.metadata(c)
    data.update(key=key, collection="ASSET_" + key, source=str(source), **(extra or {}))
    c.name = "ASSET_" + key
    c["source_blend"] = str(source)
    c["quality"] = "full_authored_geometry"
    fix_fonts()
    remap()
    bpy.data.libraries.write(
        str(A / (key + ".blend")), {c}, path_remap="RELATIVE_ALL", compress=True
    )
    (A / (key + ".json")).write_text(json.dumps(data, ensure_ascii=False, indent=2))
    print("READY", key, data["mesh_instances"], flush=True)


def core(key):
    reset()
    source = PREVIOUS / CORE_SOURCE[key] / "scene.blend"
    c = load(source, "ASSET_" + key)
    root(c)
    manifest = json.loads(
        (PREVIOUS / "source_snapshots" / key / "scene_manifest.json").read_text()
    )
    # Keep the corrected clinical equipment, espresso machine, supported shelf
    # inventory, tiled floors and full native furniture from the reviewed source.
    save(
        key,
        c,
        source,
        dict(
            enterable=True,
            door=[0, 0],
            floor_z=manifest["floor_z"],
            room_center=[manifest["spec"]["center"], 4.5],
            inside_y=1.8 if key == "pharmacy" else 3.0,
            source_shots=manifest["shots"],
            preparation="retained corrected full interior from final connect3 asset",
        ),
    )


def new_building(key):
    reset()
    source = PREVIOUS / "shared_assets" / (key + ".blend")
    c = load(source, "ASSET_" + key)
    root(c)
    edits = []
    rot = 0
    inside = 3.0
    if key == "bar":
        dx, dy, floor = -3.16, 0.79, 0.27
        leaf = [
            o
            for o in c.objects
            if any(
                t in o.name
                for t in (
                    "entry_laminated_glass",
                    "entry_door_rail",
                    "entry_pull_handle",
                    "entry_hydraulic_closer",
                )
            )
        ]
        old.rotate_leaf(leaf, (-3.95, 0.79, 0), -100)
        edits.append({"articulated_parts": len(leaf), "degrees": -100})
        bottles = [
            load(A / "native_extended.blend", "NATIVE_BottleFactory_" + str(i), True)
            for i in range(3)
        ]
        dimensions = {
            a["collection"]: a["dimensions"]
            for a in json.loads((A / "native_extended.json").read_text())
        }
        count = 0
        for ob in c.objects:
            if (
                ob.instance_collection
                and "SPIRIT_BOTTLE" in ob.instance_collection.name
            ):
                asset = bottles[count % 3]
                ob.instance_collection = asset
                ob.scale = (0.43 / dimensions[asset.name][2],) * 3
                count += 1
        # Use a complete existing branching/leaf model as a small indoor tree.
        tree = load(A / "reference08_tree.blend", "full02:MASTER:TreeFactory:42", True)
        bpy.context.scene.collection.children.unlink(c)
        root(tree)
        tm = measures.metadata(tree)
        bpy.context.scene.collection.children.unlink(tree)
        root(c)
        lo, hi = map(Vector, tm["bounds"])
        scale = 0.85 / (hi.z - lo.z)
        for ob in list(c.objects):
            if any(
                t in ob.name
                for t in [
                    "hawthorn_plant_living_leaf",
                    "hawthorn_plant_petiolated_stem",
                ]
            ):
                c.objects.unlink(ob)
        loc = (
            Vector((3.36, 2.06, 1.04))
            - Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z)) * scale
        )
        inst(c, tree, "existing_indoor_tree", loc, scale)
        edits.append(
            {
                "native_spirit_bottles": count,
                "planter_foliage": "complete existing full08 branching and leaf geometry",
            }
        )
        center = [0, 4.0]
    elif key == "corner_store":
        door = next(o for o in c.objects if "chamfered_corner_double_entry" in o.name)
        dx, dy = door.location.x, door.location.y
        floor = 0.26
        rot = -3 * math.pi / 4
        inside = 2.2
        center = [-1.0, 4.7]
        asset = door.instance_collection
        opened = bpy.data.collections.new("CONNECT4_711_OPEN_ENTRY")
        groups = {-1: [], 1: []}
        for src in asset.objects:
            ob = src.copy()
            opened.objects.link(ob)
            if any(
                t in src.name
                for t in [
                    "tempered_entry_glass",
                    "entry_door_",
                    "vertical_pull_handle",
                    "door_closer",
                ]
            ):
                side = -1 if src.location.x < -0.001 else 1
                if abs(src.location.x) < 0.001:
                    side = -1 if src.name.endswith(".001") else 1
                groups[side].append(ob)
        for side, parts in groups.items():
            old.rotate_leaf(parts, (side * 0.76, 0.08, 0), -side * 100)
        door.instance_collection = opened
        edits.append({"double_entry_articulation": 100})
        stock = load(A / "market.blend", "GROCERY_SHELF_MASTER")
        for ob in c.objects:
            if ob.instance_collection and ob.instance_collection.name.startswith(
                "GROCERY_SHELF_MASTER"
            ):
                ob.instance_collection = stock
        edits.append(
            {
                "retail_inventory": "full stocked native-asset shelves from existing market"
            }
        )
        if (A / "espresso_assembly.blend").exists():
            machine = load(
                A / "espresso_assembly.blend", "ASSET_espresso_assembly", True
            )
            for ob in list(c.objects):
                if any(
                    t in ob.name
                    for t in [
                        "coffee_machine",
                        "coffee_dispensing",
                        "coffee_group_head",
                    ]
                ):
                    c.objects.unlink(ob)
            inst(
                c,
                machine,
                "detailed_existing_espresso_machine",
                (2.15, 3.5, 1.21),
                0.65,
                math.pi,
            )
            edits.append(
                {"coffee_equipment": "full existing refined espresso assembly"}
            )
    elif key == "police":
        dx, dy, floor = 4.53, 7.54, 0.49
        inside = 3.7
        center = [4.5, 12.5]
        for side, index in [(-1, 0), (1, 1)]:
            parts = [
                o
                for o in c.objects
                if ":main_entry:" in o.name
                and any(
                    t in o.name
                    for t in [
                        f"leaf_mid_{index}",
                        f"leaf_head_{index}",
                        f"leaf_stile_{index}",
                        f"leaf_gasket_{index}",
                        f"leaf_inner_glass_{index}",
                        f"leaf_outer_glass_{index}",
                        f"leaf_bottom_{index}",
                        f"kickplate_{index}",
                        f"pull_bar_{index}",
                        f"pull_return_{index}",
                        f"panic_bar_{index}",
                        f"lock_cylinder_{index}",
                        f"closer_{index}",
                    ]
                )
            ]
            for ob in c.objects:
                if f":main_entry:hinge_{index}_" in ob.name:
                    ob.location.x = 3.16 if side < 0 else 5.9
                    parts.append(ob)
            bpy.context.view_layer.update()
            old.rotate_leaf(parts, (3.16 if side < 0 else 5.9, 7.54, 0), side * 100)
            edits.append(
                {"door_leaf": index, "parts": len(parts), "degrees": side * 100}
            )
        architecture = [
            o
            for o in c.objects
            if ":main_entry:" not in o.name
            or any(t in o.name for t in ["rough_opening", "vestibule_back_glass"])
        ]
        util.cut(
            architecture,
            (3.12, 7.15, 0.50),
            (5.94, 10.0, 3.04),
            "remove contradictory sealed backing behind real police entrance",
        )
        util.cut(
            [o for o in c.objects if "pale_cmu_core" in o.name],
            (-2.0, 9.1, 0.47),
            (11.45, 14.60, 4.50),
            "hollow structural mass around the already authored reception and lobby furniture; expose existing floor and ceiling finishes",
        )
        floorpart = next(o for o in c.objects if "lobby_floor" in o.name)
        util.part(
            c,
            floorpart,
            "police_entrance_floor_connection",
            (4.53, 8.5, 0.39),
            (2.8, 2.0, 0.20),
        )
        edits.extend(util.LOG)
        util.LOG.clear()
    elif key == "fire":
        dx, dy, floor = -0.094, 2.1, 0.63
        inside = 5.0
        center = [-0.1, 16.0]
        edits.append(
            {"entrance": "existing raised apparatus bay 3, full-depth equipment hall"}
        )
    elif key == "delivery":
        dx, dy, floor = 3.86, 0.46, 0.35
        inside = 2.7
        center = [0.4, 5.1]
        edits.append(
            {"entrance": "existing open sliding leaf and actual parcel aisles"}
        )
    elif key == "gas":
        dx, dy, floor = 2.15, 19.85, 1.16
        inside = 2.5
        center = [-2.2, 24.5]
        stems = [
            "entry_safety_glass",
            "entry_leaf_",
            "entry_glazing_gasket",
            "entry_pull_",
            "entry_bottom_sweep",
            "entry_mortise_lock",
        ]
        for side in [-1, 1]:
            parts = []
            for ob in c.objects:
                n = ob.name
                if ":store:" not in n:
                    continue
                if any(t in n for t in stems):
                    # Leaf index precedes the optional component suffix.
                    left = any(
                        re.search(t + r".*?_-1(?:[_.:]|$)", n)
                        for t in [
                            "entry_safety_glass",
                            "entry_leaf",
                            "entry_glazing_gasket",
                            "entry_pull",
                            "entry_bottom_sweep",
                            "entry_mortise_lock",
                        ]
                    )
                    # Use the geometry centre; shared central seals belong to the right leaf.
                    if (-1 if ob.location.x < 2.15 else 1) == side:
                        parts.append(ob)
                elif (
                    any(t in n for t in ["entry_meeting_seal", "entry_astragal"])
                    and side == 1
                ):
                    parts.append(ob)
            old.rotate_leaf(parts, (0.84 if side < 0 else 3.46, 19.85, 0), side * 100)
            edits.append(
                {"store_door_leaf": side, "parts": len(parts), "degrees": side * 100}
            )
        # Replace coarse refrigerator product bodies AND their old caps with complete
        # native bottle profiles; exact shelf bottom positions remain unchanged.
        native = [
            load(A / "native_extended.blend", "NATIVE_BottleFactory_" + str(i), True)
            for i in range(3)
        ]
        count = 0
        for ob in list(c.objects):
            if ":store:cooler_product_" in ob.name:
                lo, hi = util.bounds(ob)
                inst(
                    c,
                    native[count % 3],
                    "refrigerated_native_bottle",
                    ((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z),
                    1.35,
                )
                c.objects.unlink(ob)
                count += 1
            elif ":store:cooler_cap_" in ob.name:
                c.objects.unlink(ob)
        edits.append({"native_refrigerated_bottles": count})
        products = native + [
            load(
                A / "native_extended.blend",
                "NATIVE_" + kind + "Factory_" + str(i),
                True,
            )
            for kind in ["Jar", "FoodBag"]
            for i in range(2)
        ]
        # metadata measures the evaluated scene, so isolate each master explicitly.
        bpy.context.scene.collection.children.unlink(c)
        sizes = []
        for asset in products:
            root(asset)
            sizes.append(measures.metadata(asset))
            bpy.context.scene.collection.children.unlink(asset)
        root(c)
        replaced = 0
        for ob in list(c.objects):
            if ":store:shelf_" not in ob.name or ":product_" not in ob.name:
                continue
            if ":body" in ob.name:
                lo, hi = util.bounds(ob)
                j = replaced % len(products)
                info = sizes[j]
                a, b = map(Vector, info["bounds"])
                dim = b - a
                scale = min((hi.z - lo.z) / dim.z, 0.19 / max(dim.x, dim.y))
                loc = (
                    Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
                    - Vector(((a.x + b.x) / 2, (a.y + b.y) / 2, a.z)) * scale
                )
                inst(c, products[j], "native_retail_product", loc, scale)
                replaced += 1
            c.objects.unlink(ob)
        edits.append(
            {
                "native_shelf_products": replaced,
                "variants": "existing native bottle, jar and food bag assemblies; removed old body/cap/label proxies",
            }
        )
    else:
        raise ValueError(key)
    # Source-space doorway -> common local frame: entrance (0,0), interior +Y.
    bpy.context.view_layer.update()
    T = Matrix.Rotation(rot, 4, "Z") @ Matrix.Translation(Vector((-dx, -dy, 0)))
    for ob in c.objects:
        ob.matrix_world = T @ ob.matrix_world
    if key == "corner_store":
        # Move the complete checkout/register assembly away from the diagonal entry.
        # In source coordinates this is a westward shift, remaining inside the shop.
        for ob in c.objects:
            if "entry_checkout_counter" in ob.name:
                ob.location += Vector((1.0, 1.0, 0))
        edits.append(
            {
                "checkout_shift_normalized_m": [1, 1, 0],
                "reason": "0.7 m clear entrance approach",
            }
        )
    if key == "delivery":
        # Reposition the entire rack with all parcels, braces and labels together.
        for ob in c.objects:
            if "delivery:left_aisle_rack:" in ob.name:
                ob.location.x += 0.32
        edits.append(
            {
                "full_rack_translation_x_m": 0.32,
                "reason": "clear pedestrian aisle beside entry",
            }
        )
    if key == "fire" and (A / "fire_engine.blend").exists():
        engine = load(A / "fire_engine.blend", "ASSET_fire_engine", True)
        inst(c, engine, "existing_operational_ladder_engine", (10.5, 6.5, floor), 1, 0)
        edits.append(
            {
                "apparatus": "existing full-detail modern ladder engine in adjacent equipment bay"
            }
        )
    rc = T @ Vector((*center, 0))
    bpy.context.view_layer.update()
    save(
        key,
        c,
        source,
        dict(
            enterable=True,
            door=[0, 0],
            floor_z=floor,
            inside_y=inside,
            room_center=list(rc[:2]),
            preparation=edits,
        ),
    )


def extras():
    # Four intact fountain variants, including modeled water sheets and planting.
    source = (
        R
        / "infinigen/outputs/outdoor_part_demo/urban_v3_fountain3/urban_v3_fountain.blend"
    )
    for i in range(4):
        reset()
        with bpy.data.libraries.load(str(source), link=False) as (src, dst):
            names = [
                n for n in src.objects if f"fountain:{i}:" in n or f"fountain_{i}:" in n
            ]
            if not names:
                (O / "planning/fountain_object_names.json").write_text(
                    json.dumps(src.objects, indent=1)
                )
                raise RuntimeError("Inspect fountain object prefix")
            dst.objects = names
        c = bpy.data.collections.new("ASSET_fountain" + str(i))
        root(c)
        for ob in dst.objects:
            if ob.type not in {"LIGHT", "CAMERA"}:
                c.objects.link(ob)
        bpy.context.view_layer.update()
        poses = {o: o.matrix_world.copy() for o in c.objects}
        for ob, m in poses.items():
            ob.parent = None
            ob.matrix_world = m
        info = measures.metadata(c)
        lo, hi = map(Vector, info["bounds"])
        offset = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
        for ob in c.objects:
            ob.location += offset
        save("fountain" + str(i), c, source)
    # Weather-sheltered terrace settings use native chairs, table and tableware.
    for i in range(3):
        reset()
        c = bpy.data.collections.new("ASSET_native_terrace" + str(i))
        root(c)
        table = load(A / "native_variants.blend", "NATIVE3_TableDiningFactory_0", True)
        inst(c, table, "native_terrace_table", (0, 0, 0), (0.62, 0.79, 0.8 / 0.845746))
        chair = load(
            A / "native_variants.blend", "NATIVE3_ChairFactory_" + str(i * 2), True
        )
        for y, ang in [(-0.83, 0), (0.83, math.pi)]:
            inst(c, chair, "native_terrace_chair", (0, y, 0), 1, ang)
        for j, x in enumerate([-0.28, 0.28]):
            cup = load(
                A / "native_extended.blend",
                "NATIVE_CupFactory_" + str((i + j) % 3),
                True,
            )
            inst(c, cup, "native_cup", (x, 0.10, 0.803))
            spoon = load(A / "native_extended.blend", "NATIVE_SpoonFactory_0", True)
            inst(c, spoon, "native_spoon", (x, -0.11, 0.803), 1, math.pi / 2)
        save("native_terrace" + str(i), c, A / "native_variants.blend")


if __name__ == "__main__":
    args = sys.argv[sys.argv.index("--") + 1 :]
    for key in args:
        if key == "extras":
            extras()
        elif key in CORE:
            core(key)
        else:
            new_building(key)

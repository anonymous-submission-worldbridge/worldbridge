"""Refine the original pharmacy in place in a NEW sibling deliverable.
Preserves all camera data, building geometry, outdoor assets and shelf placements.
"""
import bpy, bmesh, json, math, sys, hashlib, re
from pathlib import Path
from collections import Counter, defaultdict
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from pharmacy2_asset_factory import PharmacyDetailFactory

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
SRC = O / "pharmacy"
DST = O / "pharmacy2"
(DST / "logs").mkdir(parents=True, exist_ok=True)
source_hash = hashlib.sha256((SRC / "scene.blend").read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(SRC / "scene.blend"), load_ui=False)
bpy.context.preferences.filepaths.save_version = 0
C = bpy.data.collections["Architecture_and_furnished_interior"]
original = list(C.objects)


def camera_record():
    return {
        o.name: {
            "matrix": [list(r) for r in o.matrix_world],
            "lens": o.data.lens,
            "sensor_width": o.data.sensor_width,
            "sensor_fit": o.data.sensor_fit,
            "shift": [o.data.shift_x, o.data.shift_y],
        }
        for o in bpy.data.objects
        if o.type == "CAMERA"
    }


dims = {o.name: tuple(o.dimensions) for o in original}
cameras_before = camera_record()
F = PharmacyDetailFactory(DST / "assets")
masters = {}
for sku in F.catalog:
    fn = {"carton": F.carton, "bottle": F.bottle, "tube": F.tube_pack}[sku["kind"]]
    masters[sku["id"]] = fn(sku)
print("PACKAGING_MASTERS_READY", flush=True)
counts = Counter()
placements = []


def instance(master, name, loc, scale=(1, 1, 1), angle=0):
    o = bpy.data.objects.new("pharmacy2:" + name, None)
    o.instance_type = "COLLECTION"
    o.instance_collection = master
    o.location = loc
    o.scale = scale
    o.rotation_euler.z = angle
    C.objects.link(o)
    o["c2w_asset_factory"] = "pharmacy2_asset_factory.py"
    o["c2w_semantic"] = "manufactured_assembly"
    return o


bygroup = defaultdict(list)
obsolete_products = []
for o in original:
    if ":sku_" in o.name:
        bygroup[o.name.rsplit(":", 1)[0]].append(o)
for name, parts in sorted(bygroup.items()):
    roots = [
        o
        for o in parts
        if o.get("c2w_product_form") in ["carton", "bottle", "tube_assembly_base"]
    ]
    if not roots:
        continue
    assert len(roots) == 1, (name, len(roots))
    root = roots[0]
    kind = {"tube_assembly_base": "tube"}.get(
        root["c2w_product_form"], root["c2w_product_form"]
    )
    base = float(root["c2w_base_z"])
    x, y = root.location[:2]
    labeltoken = {
        "carton": "printed_front",
        "bottle": "label_brand_ban",
        "tube": "tube_print",
    }[kind]
    label = next(o for o in parts if labeltoken in o.name)
    dx, dy = label.location.x - x, label.location.y - y
    angle = math.atan2(dy, dx) + math.pi / 2
    w, d, h = dims[root.name]
    if kind == "bottle":
        h = h / 0.78
        d = w
    if kind == "tube":
        body = next(o for o in parts if "tapered_tube" in o.name)
        w = dims[body.name][0] / 0.93
        d = max(dims[root.name][1], dims[body.name][1]) / 0.96
        h = dims[body.name][2] + dims[root.name][2] * 0.72
    ids = [s["id"] for s in F.catalog if s["kind"] == kind]
    variant = ids[int(hashlib.sha256(name.encode()).hexdigest()[:8], 16) % len(ids)]
    o = instance(
        masters[variant],
        "stock:" + name.split("well_", 1)[1],
        (x, y, base),
        (w, d, h),
        angle,
    )
    o["c2w_product_form"] = kind
    o["c2w_support_top_z"] = base
    o["source_product"] = root.name
    o["variant"] = variant
    placements.append(
        {
            "source": root.name,
            "kind": kind,
            "variant": variant,
            "base": [x, y, base],
            "scale": [w, d, h],
            "rotation_z": angle,
        }
    )
    counts[kind] += 1
    obsolete_products.extend(parts)
bpy.data.batch_remove(ids=obsolete_products)
print("PRODUCTS_REPLACED", dict(counts), flush=True)
# Counter devices: retain counter positions and create detailed reusable assemblies.
equip = {
    n: getattr(F, n)()
    for n in ["monitor", "keyboard", "mouse", "printer", "scanner", "blister"]
}
for i, x in enumerate([14.750001, 9.150001]):
    instance(equip["monitor"], f"clinical_POS_{i}", (x, 15.179998, 1.283))
    instance(equip["keyboard"], f"clinical_keyboard_{i}", (x + 0.67, 15.139998, 1.283))
    instance(equip["mouse"], f"clinical_mouse_{i}", (x + 0.27, 15.099998, 1.283))
    instance(equip["printer"], f"clinical_printer_{i}", (x - 0.67, 15.16, 1.283))
    instance(equip["scanner"], f"clinical_scanner_{i}", (x + 1.13, 15.10, 1.283))
    for j in range(2):
        instance(
            equip["blister"],
            f"dispensing_blister_{i}_{j}",
            (x - 1.37 - 0.12 + j * 0.22, 15.04, 1.354),
            angle=(j - 0.5) * 0.12,
        )
instance(equip["monitor"], "checkout_POS", (0.040001, 2.96, 1.331))
instance(
    equip["keyboard"],
    "checkout_keyboard",
    (0.36, 2.70, 1.331),
    (0.50 / 0.56, 0.24 / 0.27, 1),
)
instance(
    equip["printer"],
    "checkout_receipt_printer",
    (-0.18, 2.63, 1.331),
    (0.64, 0.80, 0.74),
)
instance(equip["scanner"], "checkout_scanner", (0.82, 2.65, 1.331))
guard_glass = F.mat("optical_clear_counter_glass", (0.98, 0.99, 1), 0.006)
gbs = guard_glass.node_tree.nodes.get("Principled BSDF")
gbs.inputs["Transmission Weight"].default_value = 1
gbs.inputs["IOR"].default_value = 1.47
remove = []
for o in original:
    # The old product objects have already been removed.
    try:
        n = o.name
    except ReferenceError:
        continue
    tail = n.rsplit(":", 1)[-1].split(".")[0]
    if ":well_clinical_counter:" in n:
        if ":terminal_" in n or re.match(
            r"^(keyboard_[01]|keyboard_key_[01]_\d+_\d+|mouse_[01]|rx_scanner_[01]|rx_scanner_lens_[01]|label_printer_[01]|printer_slot_[01]|label_roll_[01]|label_roll_core_[01]|printed_label_output_[01]|label_print_[01]_\d+|printer_cable_[01]|scale_digit_[01]_\d+)$",
            tail,
        ):
            remove.append(o)
        elif "scale_display_" in tail:
            F.plane(
                C,
                "precise_scale_LCD",
                tuple(o.location + Vector((0, -dims[n][1] / 2 - 0.0005, 0))),
                dims[n][0] * 0.99,
                dims[n][2] * 0.99,
                F.printed("scale_lcd.png", 0.15),
            )
        elif "guard_glass_" in tail:
            o.data = o.data.copy()
            bm = bmesh.new()
            bm.from_mesh(o.data)
            if bm.calc_volume(signed=True) < 0:
                bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
            bm.to_mesh(o.data)
            bm.free()
            for face in o.data.polygons:
                face.use_smooth = False
            o.dimensions.y = 0.006
            o.data.materials.clear()
            o.data.materials.append(guard_glass)
    if ":well_checkout:" in n:
        if (
            ":pos:" in n
            or tail in ["keyboard", "receipt_printer", "receipt_slot", "scanner"]
            or tail.startswith("key_")
        ):
            remove.append(o)
    if ":well_prescription_pickup_kiosk:screen_" in n and tail not in [
        "screen_bezel",
        "screen_glass",
    ]:
        if tail == "screen_lcd":
            F.plane(
                C,
                "pickup_touchscreen_UI",
                (o.location.x, o.location.y - dims[n][1] / 2 - 0.002, o.location.z),
                dims[n][0],
                dims[n][2],
                F.printed("collection_lcd.png", 0.25),
            )
        remove.append(o)
    if ":price_card_" in n or ":ticket_" in n:
        angle = o.rotation_euler.z + (
            math.pi if ":price_card_" in n or int(tail.split("_")[2]) == 1 else 0
        )
        front = Vector((math.sin(angle), -math.cos(angle), 0))
        loc = o.location + front * (dims[n][1] / 2 + 0.0005)
        F.plane(
            C,
            "printed_shelf_ticket",
            loc,
            dims[n][0] * 0.98,
            dims[n][2] * 0.96,
            F.printed("shelf_ticket.png"),
            (math.pi / 2, 0, angle),
        )
        counts["shelf_tickets"] += 1
bpy.data.batch_remove(ids=set(remove))
bpy.context.view_layer.update()
assert camera_record() == cameras_before, "Camera transform or lens changed"
# Standalone asset library, compressed; scene instances share these masters internally.
bpy.data.libraries.write(
    str(DST / "assets/refined_pharmacy_assets.blend"),
    set(F.masters),
    path_remap="RELATIVE",
    fake_user=True,
    compress=True,
)
manifest = json.loads((SRC / "scene_manifest.json").read_text())
manifest["scene"] = "pharmacy2"
manifest["title"] = "Community Pharmacy · Precision Indoor"
manifest["blend"] = str(DST / "scene.blend")
manifest["interior_refinement"] = {
    "source_scene": str(SRC / "scene.blend"),
    "source_sha256": source_hash,
    "camera_policy": "all original 24 shot definitions and all embedded cameras unchanged",
    "products": dict(counts),
    "new_equipment": {
        "POS_computers": 3,
        "keyboards": 3,
        "mice": 2,
        "label_printers": 3,
        "barcode_imagers": 3,
        "blister_strips": 4,
    },
    "procedural_factory": str(R / "scripts/pharmacy2_asset_factory.py"),
    "library": str(DST / "assets/refined_pharmacy_assets.blend"),
    "print_maps": "locally generated print artwork, packed on real 3D meshes",
    "downloads": 0,
}
(DST / "scene_manifest.json").write_text(
    json.dumps(manifest, ensure_ascii=False, indent=2)
)
(DST / "logs/camera_preservation.json").write_text(
    json.dumps(
        {"original": cameras_before, "refined": camera_record(), "identical": True},
        indent=2,
    )
)
(DST / "logs/product_placements.json").write_text(json.dumps(placements, indent=2))
for t in bpy.data.texts:
    if "manifest" in t.name.lower():
        t.clear()
        t.write(json.dumps(manifest, ensure_ascii=False, indent=2))
bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=False, do_recursive=True)
bpy.ops.wm.save_as_mainfile(filepath=str(DST / "scene.blend"), compress=True)
assert hashlib.sha256((SRC / "scene.blend").read_bytes()).hexdigest() == source_hash
print("PHARMACY2_READY", dict(counts), "MASTERS", len(F.masters), flush=True)

"""Replace facade-only legacy room blockers with physically occupied rooms."""
import bpy, sys, json, math
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

key = sys.argv[-1]
dest = B.OUT / key
bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
s = bpy.context.scene
c = bpy.data.collections["Architecture_and_furnished_interior"]
m = json.loads((dest / "scene_manifest.json").read_text())
if key == "hospital":
    targets = [
        o
        for o in c.objects
        if "tower_mass" in o.name
        or (o.get("c2w_role") == "traditional_cornice" and B.bounds(o)[0].z < 1)
    ]
    B.cut(
        targets,
        (-5.05, 0.18, 0.405),
        (5.05, 11.8, 3.97),
        "open complete atrium tower and lower cornice into the occupied clinic",
    )
    for o in s.objects:
        if o.type == "LIGHT" and "Lobby ceiling panel" in o.name:
            o.location.z = 3.88
            o.data.energy = 220
    ink = B.material("clinic_wayfinding", (0.03, 0.18, 0.20), 0.45)
    B.text(
        c,
        "clinic_reception_wayfinding",
        "RECEPTION  /  COMMUNITY CARE",
        (0, 11.72, 2.8),
        0.22,
        ink,
    )
    # Reuse actual medical bed parts and add the native soft pillow surface.
    pillows = [o for o in c.objects if "triage_" in o.name and ":pillow" in o.name]
    with bpy.data.libraries.load(
        str(B.OUT / "shared_assets/native_extended.blend"), link=True
    ) as (a, b):
        b.collections = ["NATIVE_PillowFactory_0"]
    for o in pillows:
        p = o.location.copy()
        bottom = p.z - o.dimensions.z / 2
        c.objects.unlink(o)
        B.native(
            c,
            "PillowFactory",
            "clinical_native_pillow",
            (p.x, p.y, bottom),
            1.05,
            math.pi / 2,
        )
    # Authored IV-pole cylindrical mesh provides fine rails and their fittings.
    pole = next(o for o in c.objects if "triage_" in o.name and ":iv_pole" in o.name)
    for side in [-1, 1]:
        rail = B.copy(c, pole, "clinical_safety_rail")
        rail.location = (2.7, 10.55 + side * 0.48, 1.30)
        rail.rotation_euler = (0, math.pi / 2, 0)
        rail.dimensions = (1.75, 0.035, 0.035)
        for x in [1.95, 3.45]:
            post = B.copy(c, pole, "clinical_rail_post")
            post.location = (x, 10.55 + side * 0.48, 1.10)
            post.dimensions = (0.035, 0.035, 0.40)
    m["shots"]["detail_secondary"] = {
        "position": (-0.7, 9.2, 2.05),
        "target": (2.7, 10.55, 1.13),
        "lens": 39,
    }
elif key == "library":
    # These were opaque panels used to imply depth behind windows. Real room
    # geometry now replaces them; keeping them would block both sight and light.
    for o in list(c.objects):
        if "B:atrium_0_" in o.name and o.get("c2w_role") == "interior_depth":
            c.objects.unlink(o)
    B.cut(
        [o for o in c.objects if "occupied_shell" in o.name or "dark_plinth" in o.name],
        (-8.20, -0.50, 0.10),
        (8.20, 13, 4.28),
        "recess structural subfloor under modeled reading-room boards",
    )
    # Ground-floor reading lights must sit below the existing atrium floor slab.
    for o in s.objects:
        if o.type == "LIGHT" and "Reading ceiling panel" in o.name:
            o.location.z = 4.08
            o.data.energy = 210
    decks = [
        o
        for o in c.objects
        if o.name.startswith("connect2:reading_stack")
        and o.type == "MESH"
        and o.dimensions.z < 0.22
        and o.dimensions.x > 2
    ]
    levels = sorted(set(round(B.bounds(o)[1].z, 4) for o in decks))
    if levels:
        for o in c.objects:
            if "native_shelf_books" in o.name:
                o.location.z = min(levels, key=lambda z: abs(z - o.location.z)) + 0.002
    m["shots"]["interior_wide"] = {
        "position": (0, 3.2, 1.8),
        "target": (-3.5, 8.4, 1.5),
        "lens": 24,
    }
    m["shots"]["exterior_wide"] = {
        "position": (33, -52, 21),
        "target": (0, 5, 13),
        "lens": 30,
    }
    # Maintain an open sight line from the reading garden to the monumental entry.
    for o in bpy.data.collections["Detailed_public_realm"].objects:
        if (
            o.instance_collection
            and o.instance_collection.name == "full02:MASTER:TreeFactory:42"
            and abs(o.location.x) < 18
            and o.location.y < 0
        ):
            o.location.x = math.copysign(
                20 + abs(o.location.x) * 0.25, o.location.x if o.location.x else 1
            )
for mat in bpy.data.materials:
    if mat.library or not mat.use_nodes or "glass" not in mat.name.lower():
        continue
    p = mat.node_tree.nodes.get("Principled BSDF")
    if p:
        p.inputs["Transmission Weight"].default_value = 1
        p.inputs["Roughness"].default_value = 0.035
        p.inputs["Base Color"].default_value = (0.95, 0.98, 0.99, 1)
m["architectural_fixes"].extend(B.LOG)
m["public_room_repair"] = True
(dest / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
print("PUBLIC_ROOM_REPAIRED", key, flush=True)

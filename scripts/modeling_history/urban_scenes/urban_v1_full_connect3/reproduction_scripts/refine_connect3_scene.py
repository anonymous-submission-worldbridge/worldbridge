"""Apply measured placement and camera refinements before production rendering."""
import bpy, sys, json, math, os
from pathlib import Path
from mathutils import Vector, Matrix
from bpy_extras.object_utils import world_to_camera_view

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect3 as B

k = sys.argv[-1]
d = B.O / k
m = json.loads((d / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
s = bpy.context.scene
c = bpy.data.collections["Connected_streets_and_landscape"]
cam = s.camera
if s.get("connect3_refinement_v1"):
    raise RuntimeError("Already refined")
for ob in c.objects:
    if (
        not ob.instance_collection
        or not ob.instance_collection.name.startswith("ASSET_")
        or ob.get("normalized_anchor")
    ):
        continue
    key = ob.instance_collection.name.removeprefix("ASSET_")
    p = B.A / (key + ".json")
    if not p.exists():
        continue
    meta = json.loads(p.read_text())
    lo = meta["bounds"][0]
    z = lo[2]
    if key in m["extras"] and abs(ob.location.z - (0.14 - z)) < 0.001:
        z = 0
    delta = Matrix.Rotation(ob.rotation_euler.z, 4, "Z") @ Vector(
        (0, lo[1] * ob.scale.y, z * ob.scale.z)
    )
    ob.location -= delta
    ob["normalized_anchor"] = True
lo, hi = map(Vector, m["site_bounds"])
cx = (lo.x + hi.x) / 2
width = hi.x - lo.x
if not any(
    ob.instance_collection and ob.instance_collection.name == "ASSET_bench"
    for ob in c.objects
):
    for x in range(math.ceil(lo.x + 2), math.floor(hi.x - 1), 6):
        if abs(x) > 3:
            B.furniture(c, "bench", (x, -13.5, 0.14))
# Camera views include more indoor foreground, and remain true 3D rays.
if m["focus"] == "restaurant":
    z = m["floor_z"] + 1.6
    m["shots"]["inside_to_outside_room_0"] = {
        "position": [-5.3, 4.8, z],
        "target": [-2.5, -6, z - 0.15],
        "lens": 21,
    }
    m["shots"]["inside_to_outside_room_1"] = {
        "position": [-9, 6.8, z],
        "target": [-3, -6, z - 0.15],
        "lens": 23,
    }
m["video_inside_y"] = 1.8 if m["focus"] == "pharmacy" else 3.0
# Restore distinct main-building and whole-cluster exterior pictures.
original = json.loads(
    (B.O / "source_snapshots" / m["focus"] / "scene_manifest.json").read_text()
)
m["shots"]["exterior_wide"] = original["shots"]["exterior_wide"]
sh = m["shots"]["cluster_overview"]
target = Vector((cx, -6, 2.6))
direction = Vector((hi.x + max(19, width * 0.43), -9, max(19, width * 0.4))) - target
s.render.resolution_x = 1920
s.render.resolution_y = 1080
cam.data.lens = 38
corners = [
    Vector((x, y, z))
    for b in m["buildings"]
    for x in [b["bounds"][0][0], b["bounds"][1][0]]
    for y in [b["bounds"][0][1], b["bounds"][1][1]]
    for z in [b["bounds"][0][2], b["bounds"][1][2]]
]
for _ in range(40):
    cam.location = target + direction
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    uv = [world_to_camera_view(s, cam, p) for p in corners]
    if all(0.06 < p.x < 0.94 and 0.07 < p.y < 0.94 and p.z > 0 for p in uv):
        break
    direction *= 1.07
sh.update(position=list(cam.location), target=list(target), lens=38)
# Lakeshore/river photographs include the actual water surface and shore.
if m["layout"] == "waterside":
    water = next(
        ob
        for ob in c.objects
        if ob.instance_collection
        and ob.instance_collection.name in {"ASSET_lake", "ASSET_river"}
    )
    key = water.instance_collection.name.removeprefix("ASSET_")
    focusmeta = B.meta(m["focus"])
    maincx = sum(bb[0] for bb in focusmeta["bounds"]) / 2
    water.location = (maincx, -17, -2.0) if key == "lake" else (maincx + 21, -31, -1.8)
    water.rotation_euler.z = math.pi if key == "lake" else math.pi / 2
    ground = next(ob for ob in c.objects if "continuous_ground" in ob.name)
    ground.location.y = 883.5
    ground.dimensions.y = 1800
    m["shots"]["garden_overview"] = {
        "position": [maincx + 30, -42, 15],
        "target": [maincx, -8, 1.0],
        "lens": 27,
    }
# Embedded original fonts remove machine-specific path dependencies.
for font in bpy.data.fonts:
    if font.library or font.name == "Bfont":
        continue
    name = Path(font.filepath).name
    path = Path("/usr/share/fonts/truetype/dejavu") / name
    if path.exists():
        font.filepath = str(path)
        try:
            font.pack()
        except RuntimeError:
            pass
s["connect3_refinement_v1"] = True
m[
    "refinement"
] = "measured furniture grounding, full cluster framing, deeper collision-checked doorway travel, original embedded fonts"
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
print("CONNECT3_REFINED", k, flush=True)

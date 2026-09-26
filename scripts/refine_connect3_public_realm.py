"""Extend the existing road/paving assets into a compact connected street edge."""
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
if m.get("environment_revision"):
    raise RuntimeError("Already refined")
lo, hi = map(Vector, m["site_bounds"])
cx = (lo.x + hi.x) / 2
cy = (lo.y + hi.y) / 2
width = hi.x - lo.x
with bpy.data.libraries.load(str(B.A / "site_components.blend"), link=True) as (a, b):
    b.collections = list(a.collections)
parts = {x.name: list(x.objects)[0] for x in b.collections}
pave = parts["ASSET_paving"]
asphalt = parts["ASSET_asphalt"]
joint = parts["ASSET_joint"]
# Existing pavement/asphalt components retain their authored geometry and shaders.
roadx = hi.x + 8
roady = lo.y - 8
B.copy_part(
    c, asphalt, "east_service_lane", (roadx, cy, 0.01), (7, hi.y - lo.y + 25, 0.14)
)
if m["layout"] != "waterside":
    B.copy_part(
        c, asphalt, "south_local_street", (cx, roady, 0.01), (width + 22, 7, 0.14)
    )
B.copy_part(
    c,
    pave,
    "east_street_sidewalk",
    (hi.x + 2.4, cy, 0.04),
    (3.8, hi.y - lo.y + 16, 0.20),
)
if m["layout"] != "waterside":
    B.copy_part(
        c, pave, "south_street_sidewalk", (cx, lo.y - 2.4, 0.04), (width + 8, 3.8, 0.20)
    )
paint = bpy.data.materials.new("connect3:road_marking_paint")
paint.diffuse_color = (0.72, 0.70, 0.61, 1)
paint.use_nodes = True
bs = paint.node_tree.nodes.get("Principled BSDF")
bs.inputs["Base Color"].default_value = (0.72, 0.70, 0.61, 1)
bs.inputs["Roughness"].default_value = 0.8
for y in range(math.ceil(lo.y - 6), math.floor(hi.y + 7), 7):
    ob = B.copy_part(c, joint, "street_lane_dash", (roadx, y, 0.084), (0.11, 3, 0.006))
    ob.material_slots[0].link = "OBJECT"
    ob.material_slots[0].material = paint
if m["layout"] != "waterside":
    for x in range(math.ceil(lo.x - 5), math.floor(hi.x + 5), 7):
        ob = B.copy_part(
            c, joint, "street_lane_dash", (x, roady, 0.084), (3, 0.11, 0.006)
        )
        ob.material_slots[0].link = "OBJECT"
        ob.material_slots[0].material = paint
for j, y in enumerate([lo.y + 2, cy, hi.y - 2]):
    B.furniture(
        c, "car", (roadx + 1.7, y, 0.09), math.pi / 2 if j % 2 else -math.pi / 2
    )
for ob in c.objects:
    if ob.instance_collection and ob.instance_collection.name in {
        "ASSET_parcel",
        "ASSET_food_locker",
    }:
        ob.rotation_euler.z += math.pi
# Densify activity around the shop-fronts, keeping the entrance corridor open.
focus = B.meta(m["focus"])
fcx = sum(bb[0] for bb in focus["bounds"]) / 2
existing = [ob.location.copy() for ob in c.objects if ob.instance_collection]
for x, y in [(fcx - 3.5, -8.5), (fcx + 3.7, -10), (fcx - 7, -5), (fcx + 7, -4.5)]:
    if abs(x) < 2.1 or any(
        (Vector((x, y, 0)) - Vector((p.x, p.y, 0))).length < 2.8 for p in existing
    ):
        continue
    B.furniture(c, "cafe_set", (x, y, 0.14), 0.12 if x > fcx else -0.1)
    existing.append(Vector((x, y, 0)))
# Angle is chosen from the open side of each layout instead of a fixed orbit.
if m["layout"] in {"corner", "campus"}:
    pos = Vector((lo.x - max(15, width * 0.28), lo.y - 23, max(15, width * 0.30)))
elif m["layout"] in {"courtyard", "offset_square", "garden", "mews"}:
    pos = Vector((hi.x + max(18, width * 0.38), -9, max(17, width * 0.36)))
else:
    pos = Vector(
        (cx + width * 0.28, lo.y - max(24, width * 0.45), max(18, width * 0.30))
    )
target = Vector((cx, cy, max(3, hi.z * 0.22)))
direction = pos - target
cam.data.lens = 38
cam.data.shift_x = 0
cam.data.shift_y = 0
corners = [
    Vector((x, y, z))
    for b in m["buildings"]
    for x in [b["bounds"][0][0], b["bounds"][1][0]]
    for y in [b["bounds"][0][1], b["bounds"][1][1]]
    for z in [b["bounds"][0][2], b["bounds"][1][2]]
]
s.render.resolution_x = 1920
s.render.resolution_y = 1080
for _ in range(40):
    cam.location = target + direction
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    bpy.context.view_layer.update()
    uv = [world_to_camera_view(s, cam, p) for p in corners]
    if all(0.06 < p.x < 0.94 and 0.07 < p.y < 0.94 and p.z > 0 for p in uv):
        break
    direction *= 1.06
# Optical shift centers the projected building envelope without image cropping.
for _ in range(3):
    uv = [world_to_camera_view(s, cam, p) for p in corners]
    dx = (min(p.x for p in uv) + max(p.x for p in uv)) / 2 - 0.5
    dy = (min(p.y for p in uv) + max(p.y for p in uv)) / 2 - 0.5
    cam.data.shift_x += dx
    cam.data.shift_y += dy * 1080 / 1920
m["shots"]["cluster_overview"] = {
    "position": list(cam.location),
    "target": list(target),
    "lens": 38,
    "shift_x": cam.data.shift_x,
    "shift_y": cam.data.shift_y,
}
m[
    "environment_revision"
] = "authored service lanes, sidewalks, vehicles, activity clusters and fitted optical framing"
m["video_inside_y"] = 1.8 if m["focus"] == "pharmacy" else 3.0
if k in {"community_reading_park", "health_promenade"}:
    m["shots"]["cluster_street"] = {
        "position": [0, -9, 2.0],
        "target": [0, 3, 3.0],
        "lens": 24,
    }
if k == "health_promenade":
    m["shots"]["cluster_street"] = {
        "position": [0, -5.2, 2.0],
        "target": [1.5, 1, 3.0],
        "lens": 22,
    }
if k == "community_reading_park":
    m["shots"]["exterior_street_left"] = {
        "position": [-8, -10, 2.3],
        "target": [0, 1, 3.0],
        "lens": 23,
    }
from fix_connect3_fonts import fix as fix_fonts

fix_fonts()
m["fonts_embedded"] = True
from refine_connect3_lighting import correct as correct_lighting

correct_lighting(m)
# Add source ownership for each adapted surface to the saved asset ledger.
for lib in bpy.data.libraries:
    lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
for lib in bpy.data.libraries:
    lib.filepath = "//" + os.path.relpath(bpy.path.abspath(lib.filepath), d)
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
print("PUBLIC_REALM_REFINED", k, flush=True)

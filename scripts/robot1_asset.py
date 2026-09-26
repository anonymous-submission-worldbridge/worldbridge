"""Reusable robot geometry and a neutral studio reference render."""
import bpy, sys, math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from robot1_tasks import OUT
from robot1_model import Robot, material, box

bpy.ops.wm.read_factory_settings(use_empty=True)
s = bpy.context.scene
r = Robot()
r.pose((0, 0, 0), 0, 0, 0)
asset = OUT / "robot_asset"
asset.mkdir(exist_ok=True)
collection = bpy.data.collections.new("Robot01")
s.collection.children.link(collection)
for ob in [r.root, *r.parts]:
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    collection.objects.link(ob)
bpy.data.libraries.write(str(asset / "robot.blend"), {collection}, compress=True)
box(
    "Studio floor",
    (0, 0, -0.06),
    (200, 200, 0.10),
    material("Studio slate", (0.065, 0.10, 0.15), 0.1, 0.75),
    bevel=0,
)
world = bpy.data.worlds.new("Studio")
world.use_nodes = True
world.node_tree.nodes["Background"].inputs[0].default_value = (0.3, 0.4, 0.55, 1)
world.node_tree.nodes["Background"].inputs[1].default_value = 0.4
s.world = world
for name, p, power, size in [
    ("Key", (3, 4, 5), 550, 4),
    ("Fill", (-3, 2, 3), 350, 3),
    ("Rim", (1, -3, 4), 700, 3),
]:
    l = bpy.data.lights.new(name, "AREA")
    l.energy = power
    l.shape = "DISK"
    l.size = size
    o = bpy.data.objects.new(name, l)
    s.collection.objects.link(o)
    o.location = p
    o.rotation_euler = (
        (Vector((0, 0, 0.8)) - o.location).to_track_quat("-Z", "Y").to_euler()
    )
cam = bpy.data.cameras.new("Studio camera")
o = bpy.data.objects.new("Studio camera", cam)
s.collection.objects.link(o)
o.location = (2.6, 4.3, 2.5)
o.rotation_euler = (
    (Vector((0, 0, 0.82)) - o.location).to_track_quat("-Z", "Y").to_euler()
)
cam.type = "ORTHO"
cam.ortho_scale = 2.05
s.camera = o
s.render.engine = "CYCLES"
s.cycles.device = "CPU"
s.cycles.samples = 24
s.cycles.use_denoising = True
s.render.resolution_x = 800
s.render.resolution_y = 800
s.render.resolution_percentage = 100
s.render.image_settings.file_format = "PNG"
s.render.filepath = str(asset / "robot_reference_3d.png")
bpy.ops.render.render(write_still=True)

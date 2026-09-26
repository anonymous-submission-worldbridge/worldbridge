"""Render six low-angle views around the residential part of urban_v3_all41."""

import math
import os
from pathlib import Path

import bpy
from mathutils import Vector


SCENE_DIR = Path(bpy.data.filepath).parent
OUTPUT_DIR = Path(os.environ.get("ORBIT_OUTPUT_DIR", SCENE_DIR / "residential_orbit"))
WIDTH = int(os.environ.get("ORBIT_WIDTH", "1920"))
HEIGHT = int(os.environ.get("ORBIT_HEIGHT", "1080"))
PERCENT = int(os.environ.get("ORBIT_PERCENT", "100"))
SAMPLES = int(os.environ.get("ORBIT_SAMPLES", "32"))
ENGINE = os.environ.get("ORBIT_ENGINE", "BLENDER_EEVEE_NEXT")
VIEW_FILTER = os.environ.get("ORBIT_VIEW", "")

# The three villas are rooted at roughly (-16, 15), (-13, 25), and (-17, 51).
# These positions circle the whole residential parcel at pedestrian/first-floor height.
VIEWS = (
    ("01_south_entrance", (-8.0, 4.0, 4.2), (-16.5, 16.0, 2.7), 38.0),
    ("02_southeast", (-10.0, 5.0, 4.6), (-16.5, 16.0, 2.8), 38.0),
    ("03_east_main", (11.0, 34.0, 5.2), (-15.0, 33.0, 3.3), 40.0),
    ("04_northeast", (4.0, 48.0, 5.0), (-17.0, 46.0, 3.0), 38.0),
    ("05_north", (-12.0, 64.0, 4.3), (-17.5, 51.0, 2.8), 38.0),
    ("06_northwest", (-28.0, 61.0, 4.8), (-17.5, 51.0, 2.8), 38.0),
)


def point_camera(camera, target):
    camera.rotation_euler = (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()


scene = bpy.context.scene
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

camera_data = bpy.data.cameras.get("residential_orbit_camera_data")
if camera_data is None:
    camera_data = bpy.data.cameras.new("residential_orbit_camera_data")
camera = bpy.data.objects.get("residential_orbit_camera")
if camera is None:
    camera = bpy.data.objects.new("residential_orbit_camera", camera_data)
    scene.collection.objects.link(camera)

camera.data.sensor_width = 36.0
camera.data.clip_start = 0.1
camera.data.clip_end = 1000.0
scene.camera = camera

scene.render.engine = ENGINE
scene.render.resolution_x = WIDTH
scene.render.resolution_y = HEIGHT
scene.render.resolution_percentage = PERCENT
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
scene.render.use_file_extension = True
scene.render.use_persistent_data = True
scene.render.image_settings.color_depth = "8"
scene.render.filepath = str(OUTPUT_DIR) + os.sep
scene.render.fps = 1

scene.cycles.samples = SAMPLES
scene.cycles.use_denoising = True
scene.cycles.use_adaptive_sampling = True

# Preserve the scene's original world lighting, but composite a warm neutral color
# behind transparent world rays where low-angle cameras see beyond the backdrop mesh.
scene.use_nodes = True
nodes = scene.node_tree.nodes
nodes.clear()
render_layers = nodes.new("CompositorNodeRLayers")
background = nodes.new("CompositorNodeRGB")
background.outputs[0].default_value = (0.72, 0.55, 0.43, 1.0)
alpha_over = nodes.new("CompositorNodeAlphaOver")
alpha_over.inputs[0].default_value = 1.0
composite = nodes.new("CompositorNodeComposite")
scene.node_tree.links.new(background.outputs[0], alpha_over.inputs[1])
scene.node_tree.links.new(render_layers.outputs["Image"], alpha_over.inputs[2])
scene.node_tree.links.new(alpha_over.outputs[0], composite.inputs[0])

scene.frame_set(1)
for name, location, target, lens in VIEWS:
    if VIEW_FILTER and not any(term in name for term in VIEW_FILTER.split(",")):
        continue
    camera.location = location
    camera.data.lens = lens
    point_camera(camera, target)
    scene.render.filepath = str(OUTPUT_DIR / f"residential_orbit_{name}.png")
    print(f"RENDERING {name}: camera={location}, target={target}, lens={lens}")
    bpy.ops.render.render(write_still=True)

print(f"DONE: {len(VIEWS)} views written to {OUTPUT_DIR}")

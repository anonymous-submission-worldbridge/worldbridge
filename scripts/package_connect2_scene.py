"""Embed all still cameras, actual video animation, and provenance in each blend."""
import bpy, sys, json, os
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B
from render_urban_v1_full_connect2 import animation

key = sys.argv[-1]
d = B.OUT / key
m = json.loads((d / "scene_manifest.json").read_text())
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
s = bpy.context.scene
if not s.get("presentation_cameras_embedded"):
    photos = B.col("Photographs_24_views", s.collection)
    videos = B.col("Walkthroughs_4_animated_cameras", s.collection)

    def camera(c, name):
        data = bpy.data.cameras.new(name)
        data.clip_start = 0.06
        data.clip_end = 2200
        data.display_size = 0.16
        o = bpy.data.objects.new(name, data)
        c.objects.link(o)
        return o

    def pose(o, p, t, l):
        o.location = p
        o.rotation_euler = (Vector(t) - Vector(p)).to_track_quat("-Z", "Y").to_euler()
        o.data.lens = l

    for name, shot in m["shots"].items():
        o = camera(photos, name)
        pose(o, shot["position"], shot["target"], shot["lens"])
        if name == "exterior_wide":
            s.camera = o
    for name in ["interior", "exterior", "inside_to_outside", "outside_to_inside"]:
        o = camera(videos, "video_" + name)
        for i in range(144):
            p, t, l = animation(m, name, i / 143)
            pose(o, p, t, l)
            o.keyframe_insert("location", frame=i + 1)
            o.keyframe_insert("rotation_euler", frame=i + 1)
        o["fps"] = 24
        o["duration_seconds"] = 6
        o["camera_path"] = "actual rendered path, every frame baked"
    s["presentation_cameras_embedded"] = True
s.frame_start = 1
s.frame_end = 144
s.frame_set(1)
s.render.fps = 24
s.cycles.device = "GPU"
s.cycles.samples = 96
s.render.resolution_x = 1920
s.render.resolution_y = 1080
s.render.resolution_percentage = 100
s.render.image_settings.file_format = "PNG"
s.render.image_settings.color_mode = "RGB"
bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
bpy.context.view_layer.update()
deps = bpy.context.evaluated_depsgraph_get()
num = 0
v = 0
meshes = {}
for i in deps.object_instances:
    if i.object.type == "MESH" and not i.object.hide_render:
        num += 1
        v += len(i.object.data.vertices)
        original = i.object.original.data
        if hasattr(original, "vertices"):
            meshes[original.as_pointer()] = original
m["geometry"].update(
    {
        "evaluated_mesh_instances": num,
        "evaluated_vertices_including_instances": v,
        "unique_source_meshes": len(meshes),
        "unique_source_mesh_vertices": sum(len(me.vertices) for me in meshes.values()),
    }
)
m["geometry"].pop("evaluated_vertices", None)
m["embedded_cameras"] = {
    "stills": 24,
    "animated": 4,
    "animation_frames": 144,
    "fps": 24,
}
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
for name, body in [
    ("scene_manifest.json", json.dumps(m, ensure_ascii=False, indent=2)),
    (
        "README",
        "Complete three-dimensional scene. The Photographs_24_views folder contains 24 photo positions; Walkthroughs_4_animated_cameras includes four animated camera trajectories (frames 1 to 144 at 24 fps) for real-time video baking. Shared assets use relative links and should be saved with the shared_assets folder. All images come from this scene's Cycles/OptiX render.",
    ),
]:
    t = bpy.data.texts.get(name) or bpy.data.texts.new(name)
    t.clear()
    t.write(body)
for lib in bpy.data.libraries:
    lib.filepath = "//" + os.path.relpath(bpy.path.abspath(lib.filepath), d)
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
print("PACKAGED_CAMERAS_AND_SCENE", key, json.dumps(m["geometry"]), flush=True)

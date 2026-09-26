"""Actual full-scene Cycles photographs and continuous doorway videos."""
import bpy, sys, json, argparse, os, fcntl, hashlib
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O
import render_urban_v1_full_connect as renderer

renderer.OUT = O
old_pose = renderer.pose


def pose(scene, position, target, lens, shift_x=0, shift_y=0):
    old_pose(scene, position, target, lens)
    scene.camera.data.shift_x = shift_x
    scene.camera.data.shift_y = shift_y


renderer.pose = pose


def animation(m, name, t):
    u = t * t * (3 - 2 * t)
    z = m["floor_z"] + 1.6
    inside = m["video_inside_y"]
    if name == "outside_to_inside":
        return Vector((0, -6.5 + (6.5 + inside) * u, z)), Vector((0, 5, z - 0.05)), 25
    if name == "inside_to_outside":
        return (
            Vector((0, inside - (6.5 + inside) * u, z)),
            Vector((0, -12, z - 0.1)),
            25,
        )
    sh = m["shots"]["district_overview" if name == "exterior" else "interior_wide"]
    p = Vector(sh["position"])
    target = Vector(sh["target"])
    if name == "exterior":
        p.x += 4 * (u - 0.5)
    else:
        target.x += 1.2 * (u - 0.5)
    return p, target, sh["lens"]


renderer.animation_pose = animation


def cpu_preview(scene, width, samples):
    if width > 960 or samples > 24:
        raise RuntimeError("CPU is limited to small diagnostic previews")
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = samples
    scene.cycles.use_denoising = True
    scene.cycles.denoising_use_gpu = False
    scene.render.resolution_x = width
    scene.render.resolution_y = width * 9 // 16
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.use_persistent_data = True
    return ["CPU diagnostic preview, not a delivery render"]


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scene", required=True)
    p.add_argument("--mode", choices=["preview", "final", "video"], default="preview")
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--samples", type=int, default=24)
    p.add_argument("--shots", default="")
    p.add_argument("--frames", type=int, default=144)
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--cpu-preview", action="store_true")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if a.cpu_preview:
        if a.mode != "preview":
            raise RuntimeError("Final deliverables require an available GPU")
        renderer.configure = cpu_preview
    if a.mode != "preview":
        audit = json.loads((O / a.scene / "geometry_audit.json").read_text())
        if not audit["passed"]:
            raise RuntimeError("Geometry audit must pass before production rendering")
    with (O / a.scene / ".render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        renderer.main(a)

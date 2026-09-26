"""GPU Cycles photographs and true 3D continuous doorway camera travel."""
import sys, argparse, json, fcntl
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import render_urban_v1_full_connect as render

render.OUT = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"


def animation(m, name, t):
    u = t * t * (3 - 2 * t)
    z = m["floor_z"] + 1.6
    inside = m.get("video_inside_y", 1.1)
    if name == "outside_to_inside":
        return Vector((0, -6.2 + (6.2 + inside) * u, z)), Vector((0, 5, z)), 25
    if name == "inside_to_outside":
        return (
            Vector((0, inside - (6.2 + inside) * u, z)),
            Vector((0, -12, z - 0.1)),
            25,
        )
    if name == "exterior":
        shot = m["shots"]["cluster_overview"]
        p = Vector(shot["position"])
        p.x += 3 * (u - 0.5)
        return p, Vector(shot["target"]), shot["lens"]
    shot = m["shots"]["interior_wide"]
    target = Vector(shot["target"])
    target.x += 1.2 * (u - 0.5)
    return Vector(shot["position"]), target, shot["lens"]


render.animation_pose = animation
_original_pose = render.pose


def pose(scene, position, target, lens, shift_x=0, shift_y=0):
    _original_pose(scene, position, target, lens)
    scene.camera.data.shift_x = shift_x
    scene.camera.data.shift_y = shift_y


render.pose = pose
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scene", required=True)
    p.add_argument("--mode", choices=["preview", "final", "video"], default="preview")
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--samples", type=int, default=24)
    p.add_argument("--shots", default="")
    p.add_argument("--frames", type=int, default=96)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if (
        args.mode == "final"
        and args.shots
        and args.scene in {"lakeside_reading", "waterside_dining"}
        and "garden_overview" not in args.shots.split(",")
    ):
        args.shots += ",garden_overview"
    with (render.OUT / args.scene / ".render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        render.main(args)

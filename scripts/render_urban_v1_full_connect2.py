"""Real Cycles/OptiX multi-view photography and continuous camera paths."""
import sys, argparse
from pathlib import Path
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import render_urban_v1_full_connect as render

render.OUT = (
    Path(__file__).resolve().parents[1]
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
)


def animation(m, name, t):
    u = t * t * (3 - 2 * t)
    z = m["floor_z"] + 1.6
    inside = m.get("video_inside_y", 1.1)
    if name == "outside_to_inside":
        return Vector((0, -6.2 + (6.2 + inside) * u, z)), Vector((0, 5, 1.55)), 25
    if name == "inside_to_outside":
        return Vector((0, inside - (6.2 + inside) * u, z)), Vector((0, -12, 1.55)), 25
    if name == "exterior":
        s = m["shots"]["exterior_street_left"]
        p = Vector(s["position"])
        p.x += 3.5 * u
        p.y -= 1.0 * u
        return p, Vector(s["target"]), s["lens"]
    s = m["shots"]["interior_wide"]
    p = Vector(s["position"])
    target = Vector(s["target"])
    target.x += 2.5 * (u - 0.5)
    return p, target, s["lens"]


render.animation_pose = animation
if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--scene", required=True)
    p.add_argument("--mode", choices=["preview", "final", "video"], default="preview")
    p.add_argument("--width", type=int, default=960)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--shots", default="")
    p.add_argument("--frames", type=int, default=144)
    p.add_argument("--overwrite", action="store_true")
    args = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
    if args.mode == "video":
        import fcntl, copy

        locks = render.OUT / "logs" / "locks"
        locks.mkdir(exist_ok=True)
        for clip in (
            args.shots.split(",")
            if args.shots
            else ["interior", "exterior", "inside_to_outside", "outside_to_inside"]
        ):
            with (locks / (args.scene + "_" + clip + ".lock")).open("w") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                one = copy.copy(args)
                one.shots = clip
                render.main(one)
    else:
        render.main(args)

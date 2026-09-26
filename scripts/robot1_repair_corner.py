"""Rebuild three task copies with clearance from the native checkout barrier."""
import json, os, shutil, subprocess, sys, time
from robot1_tasks import ROOT, OUT, write


def main():
    scenes = ["seven_corner", "seven_lake", "market_fountain"]
    env = os.environ.copy()
    env.update(XDG_CACHE_HOME="/tmp/robot1_cache", OMP_NUM_THREADS="12")
    write(
        OUT / "corner_repair_process.json", dict(pid=os.getpid(), started=time.time())
    )
    for scene in scenes:
        d = OUT / scene / "delivery"
        archive = OUT / "logs/diagnostic_archive" / ("corner_clearance_" + scene)
        archive.mkdir(parents=True, exist_ok=True)
        if not (archive / "animation.blend").exists():
            for name in [
                "images",
                "frames",
                "animation.blend",
                "trajectory.json",
                "path_audit.json",
                "animation_audit.json",
                "third_person_video_camera.json",
            ]:
                p = d / name
                if p.exists():
                    shutil.move(str(p), str(archive / name))
        cmd = [
            "blender",
            "-b",
            "-t",
            "12",
            "--python-exit-code",
            "1",
            "-P",
            str(ROOT / "scripts/build_render_robot1.py"),
            "--",
            "--scene",
            scene,
            "--kind",
            "delivery",
        ]
        with (OUT / "logs" / (scene + "_corner_repair.log")).open("a") as log:
            subprocess.run(
                cmd + ["--mode", "build", "--rebuild"],
                cwd=ROOT,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                check=True,
            )
        write(
            d / "corner_clearance_review.json",
            dict(
                revision=1,
                indoor_stop_y=0.55,
                stand_y=1.11,
                reason="Robot, feet and service stand moved before the native queue stanchion at y=1.563; original geometry unchanged",
                updated=time.time(),
            ),
        )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/robot1_captions.py")], cwd=ROOT, check=True
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/validate_robot1.py")], cwd=ROOT, check=True
    )
    write(
        OUT / "corner_repair_complete.json",
        dict(updated=time.time(), scenes=scenes, status="rebuilt_gpu_media_pending"),
    )


if __name__ == "__main__":
    main()

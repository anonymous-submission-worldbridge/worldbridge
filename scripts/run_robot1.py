"""Resumable single-worker task build/render queue with explicit progress."""
import argparse, fcntl, json, os, subprocess, sys, time, traceback, shutil
from pathlib import Path
from robot1_tasks import ROOT, OUT, SOURCE, write, png_complete


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--queue-id", default="main")
    p.add_argument(
        "--stage", choices=["build", "images", "video", "all"], default="all"
    )
    p.add_argument("--scenes", default="")
    p.add_argument("--gpu", default="auto")
    p.add_argument("--width", type=int, default=1280)
    p.add_argument("--samples", type=int, default=32)
    p.add_argument("--video-width", type=int, default=960)
    p.add_argument("--video-samples", type=int, default=12)
    p.add_argument("--fps", type=int, default=24)
    p.add_argument("--engine", default="CYCLES")
    a = p.parse_args()
    lock = (OUT / ("." + a.stage + "_" + a.queue_id + ".lock")).open("w")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tasks = json.loads((OUT / "task_catalogue.json").read_text())["tasks"]
    tasks = [t for t in tasks if not a.scenes or t["scene"] in a.scenes.split(",")]
    results = []
    write(
        OUT / ("queue_process_" + a.queue_id + ".json"),
        dict(pid=os.getpid(), stage=a.stage, started=time.time(), command=sys.argv),
    )
    for i, t in enumerate(tasks):
        d = OUT / t["scene"] / t["kind"]
        if (
            a.stage == "build"
            and (d / "animation.blend").exists()
            and json.loads((d / "task.json").read_text()).get("animation_revision") == 3
        ):
            continue
        if a.stage != "build":
            while not (
                (d / "animation.blend").exists()
                and json.loads((d / "task.json").read_text()).get("animation_revision")
                == 3
            ):
                if (d / "error.json").exists():
                    break
                write(
                    OUT / ("queue_status_" + a.queue_id + ".json"),
                    dict(
                        stage="waiting_for_animation", task=t["id"], updated=time.time()
                    ),
                )
                time.sleep(10)
            if not (
                (d / "animation.blend").exists()
                and json.loads((d / "task.json").read_text()).get("animation_revision")
                == 3
            ):
                results.append(
                    dict(
                        task=t["id"],
                        returncode=1,
                        reason="Animation build failed; see task error.json",
                    )
                )
                continue

        if (
            a.stage == "images"
            and sum(png_complete(p) for p in (d / "images").glob("*.png")) >= 12
        ):
            continue
        if a.stage in {"all", "video"} and all(
            (d / (view + ".mp4")).exists() for view in ["first_person", "third_person"]
        ):
            continue
        while True:
            ram = next(
                int(x.split()[1]) / 1048576
                for x in Path("/proc/meminfo").read_text().splitlines()
                if x.startswith("MemAvailable:")
            )
            if shutil.disk_usage(OUT).free < 25 * 2**30:
                raise RuntimeError("Insufficient free disk space")
            card = a.gpu
            gpu_lock = None
            if a.stage != "build":
                try:
                    txt = subprocess.check_output(
                        [
                            "nvidia-smi",
                            "--query-gpu=index,memory.free,utilization.gpu",
                            "--format=csv,noheader,nounits",
                        ],
                        text=True,
                    )
                    candidates = [
                        tuple(map(int, line.split(",")))
                        for line in txt.strip().splitlines()
                    ]
                    candidates = [
                        v
                        for v in candidates
                        if v[1] > 14500
                        and v[2] < 70
                        and (a.gpu == "auto" or str(v[0]) == a.gpu)
                    ]
                    card = None
                    for candidate in sorted(
                        candidates, key=lambda v: v[1] - v[2] * 30, reverse=True
                    ):
                        handle = (SOURCE / ("gpu_" + str(candidate[0]) + ".lock")).open(
                            "a"
                        )
                        try:
                            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            handle.close()
                            continue
                        gpu_lock = handle
                        card = str(candidate[0])
                        break
                except Exception:
                    card = None
            if ram > 24 and (card is not None or a.stage == "build"):
                break
            if gpu_lock:
                gpu_lock.close()
            write(
                OUT / ("queue_status_" + a.queue_id + ".json"),
                dict(
                    stage="waiting_for_resources",
                    task=t["id"],
                    available_ram_gib=ram,
                    updated=time.time(),
                ),
            )
            time.sleep(20)
        env = os.environ.copy()
        env.update(OMP_NUM_THREADS="6", XDG_CACHE_HOME="/tmp/robot1_cache")
        if a.stage != "build":
            env["CUDA_VISIBLE_DEVICES"] = card
        logfile = OUT / "logs" / (t["id"] + "_" + a.stage + ".log")
        cmd = [
            "blender",
            "-b",
            "-t",
            "6",
            "--python-exit-code",
            "1",
            "-P",
            str(ROOT / "scripts/build_render_robot1.py"),
            "--",
            "--scene",
            t["scene"],
            "--kind",
            t["kind"],
            "--mode",
            a.stage,
            "--width",
            str(a.width),
            "--samples",
            str(a.samples),
            "--video-width",
            str(a.video_width),
            "--video-samples",
            str(a.video_samples),
            "--fps",
            str(a.fps),
            "--engine",
            a.engine,
        ]
        write(
            OUT / ("queue_status_" + a.queue_id + ".json"),
            dict(
                stage=a.stage,
                task=t["id"],
                index=i + 1,
                total=len(tasks),
                gpu=card,
                log=str(logfile),
                updated=time.time(),
            ),
        )
        with logfile.open("a") as f:
            r = subprocess.run(
                cmd, env=env, cwd=ROOT, stdout=f, stderr=subprocess.STDOUT
            )
        if gpu_lock:
            gpu_lock.close()
        results.append(dict(task=t["id"], returncode=r.returncode))
        write(OUT / ("queue_" + a.stage + "_" + a.queue_id + "_results.json"), results)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts/robot1_gallery.py")],
            cwd=ROOT,
            check=True,
        )
    write(
        OUT / ("queue_status_" + a.queue_id + ".json"),
        dict(
            stage="queue_finished",
            requested_stage=a.stage,
            completed=sum(r["returncode"] == 0 for r in results),
            failed=[r for r in results if r["returncode"]],
            updated=time.time(),
        ),
    )


if __name__ == "__main__":
    main()

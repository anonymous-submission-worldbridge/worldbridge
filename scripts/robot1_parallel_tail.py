"""Render disjoint chunks of the final long task, then verify and encode complete views."""
import argparse, fcntl, hashlib, json, math, os, shutil, subprocess, sys, time
from pathlib import Path
from robot1_tasks import ROOT, OUT, SOURCE, write, png_valid

CHILDREN = []
HELD_TASK_LOCKS = []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", default="fire_industrial")
    parser.add_argument("--kind", default="delivery", choices=["delivery", "fetch"])
    parser.add_argument("--prefix", default="parallel_tail")
    parser.add_argument("--parts", type=int, default=4)
    args = parser.parse_args()
    if args.parts < 1 or not args.prefix.replace("_", "").isalnum():
        raise ValueError("Invalid chunk configuration")
    d = OUT / args.scene / args.kind
    lock = (d / ".media.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX)
    HELD_TASK_LOCKS.append(lock)
    task = json.loads((d / "task.json").read_text())
    n = task["frames"]
    fps = task["fps"]
    jobs = []
    for view in ["first_person", "third_person"]:
        if (d / (view + ".mp4")).exists():
            continue
        cached = {int(p.stem) for p in (d / "frames" / view).glob("*.png")}
        size = math.ceil(n / args.parts)
        for start in range(1, n + 1, size):
            end = min(n, start + size - 1)
            if any(f not in cached for f in range(start, end + 1)):
                jobs.append(
                    dict(view=view, start=start, end=end, id=view + "_" + str(start))
                )
    write(
        OUT / (args.prefix + "_plan.json"),
        dict(
            task=task["id"],
            pid=os.getpid(),
            total_frames_per_view=n,
            jobs=jobs,
            started=time.time(),
        ),
    )
    pending = list(jobs)
    running = {}
    locks = {}
    completed = []
    while pending or running:
        for key, job in list(running.items()):
            code = job["process"].poll()
            if code is None:
                continue
            job["log"].close()
            del running[key]
            if code:
                raise RuntimeError("Chunk failed: " + key + " exit " + str(code))
            completed.append(key)
        for card in list(locks):
            if not any(j["gpu"] == card for j in running.values()):
                locks.pop(card).close()
        ram = next(
            int(x.split()[1]) / 1048576
            for x in Path("/proc/meminfo").read_text().splitlines()
            if x.startswith("MemAvailable:")
        )
        if pending and len(running) < 6 and ram > 40:
            rows = (
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-gpu=index,memory.free,utilization.gpu",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                )
                .strip()
                .splitlines()
            )
            cards = [tuple(map(int, row.split(","))) for row in rows]
            allocations = (
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        "--query-compute-apps=pid,used_memory",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                )
                .strip()
                .splitlines()
            )
            used = {}
            for row in allocations:
                try:
                    pid, amount = map(int, row.split(","))
                    used[pid] = used.get(pid, 0) + amount
                except ValueError:
                    pass
            for card, free, util in sorted(
                cards, key=lambda c: c[1] - c[2] * 20, reverse=True
            ):
                own = [j for j in running.values() if j["gpu"] == card]
                if (
                    len(own) >= 2
                    or free
                    - sum(max(0, 9000 - used.get(j["process"].pid, 0)) for j in own)
                    < 11000
                ):
                    continue
                if card not in locks:
                    h = (SOURCE / f"gpu_{card}.lock").open("a")
                    try:
                        fcntl.flock(h, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        h.close()
                        continue
                    locks[card] = h
                chunk = pending.pop(0)
                env = os.environ.copy()
                env.update(
                    CUDA_VISIBLE_DEVICES=str(card),
                    OMP_NUM_THREADS="6",
                    XDG_CACHE_HOME="/tmp/robot1_cache",
                )
                log = (OUT / "logs" / (args.prefix + "_" + chunk["id"] + ".log")).open(
                    "a"
                )
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
                    args.scene,
                    "--kind",
                    args.kind,
                    "--mode",
                    "video",
                    "--views",
                    chunk["view"],
                    "--frame-start",
                    str(chunk["start"]),
                    "--frame-end",
                    str(chunk["end"]),
                    "--frames-only",
                    "--progress-id",
                    args.prefix + "_" + chunk["id"],
                ]
                proc = subprocess.Popen(
                    cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
                )
                CHILDREN.append(proc)
                running[chunk["id"]] = dict(
                    process=proc, gpu=card, log=log, chunk=chunk
                )
                break
        write(
            OUT / (args.prefix + "_status.json"),
            dict(
                updated=time.time(),
                stage="rendering_chunks",
                remaining_chunks=len(pending),
                completed=completed,
                running=[
                    dict(pid=j["process"].pid, gpu=j["gpu"], **j["chunk"])
                    for j in running.values()
                ],
            ),
        )
        time.sleep(20)
    for view in ["first_person", "third_person"]:
        target = d / (view + ".mp4")
        if target.exists():
            continue
        fd = d / "frames" / view
        invalid = [f for f in range(1, n + 1) if not png_valid(fd / f"{f:05d}.png")]
        if invalid:
            raise RuntimeError(
                "Missing or damaged frames before encoding: " + str(invalid)
            )
        temp = Path("/tmp") / f"robot1_tail_{os.getpid()}_{view}.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-y",
                "-threads",
                "2",
                "-framerate",
                str(fps),
                "-start_number",
                "1",
                "-i",
                str(fd / "%05d.png"),
                "-frames:v",
                str(n),
                "-c:v",
                "libx264",
                "-threads",
                "2",
                "-preset",
                "fast",
                "-crf",
                "19",
                "-pix_fmt",
                "yuv420p",
                "-movflags",
                "+faststart",
                str(temp),
            ],
            check=True,
        )
        subprocess.run(
            [
                "ffmpeg",
                "-v",
                "error",
                "-xerror",
                "-threads",
                "2",
                "-i",
                str(temp),
                "-f",
                "null",
                "-",
            ],
            stdout=subprocess.DEVNULL,
            check=True,
        )
        st = json.loads(
            subprocess.check_output(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_entries",
                    "stream=nb_frames,width,height,r_frame_rate",
                    "-of",
                    "json",
                    str(temp),
                ],
                text=True,
            )
        )["streams"][0]
        if int(st["nb_frames"]) != n or (st["width"], st["height"]) != (960, 540):
            raise RuntimeError("Encoded tail video specification mismatch")
        publish = d / (view + ".partial.mp4")
        with temp.open("rb") as src, publish.open("wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        with temp.open("rb") as src, publish.open("rb") as dst:
            if (
                hashlib.file_digest(src, "sha256").digest()
                != hashlib.file_digest(dst, "sha256").digest()
            ):
                raise RuntimeError("Tail video copy checksum mismatch")
        publish.replace(target)
        temp.unlink()
    task["status"] = "rendered_pending_review"
    write(d / "task.json", task)
    if (d / "error.json").exists():
        (d / "error.json").unlink()
    write(
        d / "render_settings.json",
        dict(
            engine="CYCLES",
            device="GPU",
            width=1280,
            samples=32,
            video_width=960,
            video_samples=12,
            fps=fps,
            views=["first_person", "third_person"],
            mode="video",
            parallel_chunks=jobs,
        ),
    )
    write(
        OUT / (args.prefix + "_status.json"),
        dict(updated=time.time(), stage="complete", completed=completed),
    )


if __name__ == "__main__":
    try:
        main()
    finally:
        for child in CHILDREN:
            if child.poll() is None:
                child.terminate()
        for child in CHILDREN:
            if child.poll() is None:
                try:
                    child.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()

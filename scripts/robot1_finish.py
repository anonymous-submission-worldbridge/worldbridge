"""Complete all Robot 01 movies with bounded, memory-aware GPU scheduling."""
import fcntl, json, os, shutil, signal, subprocess, sys, time
from pathlib import Path
from robot1_tasks import OUT, ROOT, SOURCE, write


class AdoptedProcess:
    def __init__(self, pid, d):
        self.pid = pid
        self.directory = d

    def poll(self):
        try:
            command = Path(f"/proc/{self.pid}/cmdline").read_text()
            if "build_render_robot1.py" in command:
                return None
        except FileNotFoundError:
            pass
        return (
            0
            if all(
                (self.directory / (v + ".mp4")).exists()
                for v in ["first_person", "third_person"]
            )
            else 1
        )


def main():
    lock = (OUT / ".finish_supervisor.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tasks = json.loads((OUT / "task_catalogue.json").read_text())["tasks"]
    # Finish visual repairs early so their corrected frames can be reviewed promptly.
    tasks.sort(key=lambda t: t["scene"] not in {"seven_lake", "market_fountain"})
    running = {}
    gpu_locks = {}
    attempts = {}
    finished = []
    if "--adopt" in sys.argv:
        previous = json.loads((OUT / "finish_status.json").read_text())
        attempts = previous.get("attempts", {})
        if (OUT / "finish_results.json").exists():
            finished = json.loads((OUT / "finish_results.json").read_text())
        for record in previous.get("running", []):
            task = next(t for t in tasks if t["id"] == record["task"])
            d = OUT / task["scene"] / task["kind"]
            proc = AdoptedProcess(record["pid"], d)
            if proc.poll() is not None:
                continue
            handle = (d / ".media.lock").open("a")
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            card = record["gpu"]
            if card not in gpu_locks:
                gl = (SOURCE / f"gpu_{card}.lock").open("a")
                try:
                    fcntl.flock(gl, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    gpu_locks[card] = gl
                except BlockingIOError:
                    gl.close()  # Existing render remains tracked; no new work admitted under another owner's lock.
            running[task["id"]] = dict(
                process=proc,
                gpu=card,
                log=open(os.devnull, "w"),
                lock=handle,
                started=record["started"],
            )
    write(
        OUT / "finish_process.json",
        dict(pid=os.getpid(), started=time.time(), max_workers=12),
    )
    last_gallery = 0
    while True:
        for ident, job in list(running.items()):
            code = job["process"].poll()
            if code is None:
                continue
            job["log"].close()
            job["lock"].close()
            finished.append(
                dict(task=ident, returncode=code, finished=time.time(), gpu=job["gpu"])
            )
            del running[ident]
            write(OUT / "finish_results.json", finished)
        for card in list(gpu_locks):
            if not any(j["gpu"] == card for j in running.values()):
                gpu_locks.pop(card).close()
        pending = []
        for task in tasks:
            d = OUT / task["scene"] / task["kind"]
            if not all(
                (d / (v + ".mp4")).exists() for v in ["first_person", "third_person"]
            ):
                pending.append(task)
        if not pending and not running:
            break
        if shutil.disk_usage(OUT).free < 30 * 2**30:
            raise RuntimeError("Low disk space; cached frames retained")
        ram = next(
            int(x.split()[1]) / 1048576
            for x in open("/proc/meminfo")
            if x.startswith("MemAvailable:")
        )
        rss = {}
        for j in running.values():
            try:
                rss[j["process"].pid] = (
                    int(
                        next(
                            x.split()[1]
                            for x in Path(f"/proc/{j['process'].pid}/status")
                            .read_text()
                            .splitlines()
                            if x.startswith("VmRSS:")
                        )
                    )
                    / 1048576
                )
            except (FileNotFoundError, StopIteration):
                rss[j["process"].pid] = 0
        reserved_ram = 0
        for ident, job in running.items():
            scene, kind = ident.rsplit("_", 1)
            progress = OUT / scene / kind / "render_progress.json"
            ready = (
                progress.exists()
                and json.loads(progress.read_text()).get("updated", 0) > job["started"]
            )
            # Loading reserves a full scene footprint; steady renders retain 2 GiB headroom.
            reserved_ram += 2 if ready else max(2, 15 - rss.get(job["process"].pid, 0))
        if len(running) < 12 and ram - reserved_ram > 34:
            lines = (
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
            cards = [tuple(map(int, line.split(","))) for line in lines]
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
            for line in allocations:
                try:
                    pid, amount = map(int, line.split(","))
                    used[pid] = used.get(pid, 0) + amount
                except ValueError:
                    pass
            reserved = {
                card: sum(
                    max(0, 9000 - used.get(j["process"].pid, 0))
                    for j in running.values()
                    if j["gpu"] == card
                )
                for card, _, _ in cards
            }
            cards = sorted(
                (
                    (i, f - reserved[i], u)
                    for i, f, u in cards
                    if f - reserved[i] > 11000
                ),
                key=lambda x: x[1] - x[2] * 10,
                reverse=True,
            )
            for task in pending:
                ident = task["id"]
                if ident in running or attempts.get(ident, 0) >= 4:
                    continue
                d = OUT / task["scene"] / task["kind"]
                handle = (d / ".media.lock").open("a")
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    handle.close()
                    continue
                selected = None
                for card, free, util in cards:
                    if sum(j["gpu"] == card for j in running.values()) >= 2:
                        continue
                    if card not in gpu_locks:
                        gl = (SOURCE / f"gpu_{card}.lock").open("a")
                        try:
                            fcntl.flock(gl, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            gl.close()
                            continue
                        gpu_locks[card] = gl
                    selected = card
                    break
                if selected is None:
                    handle.close()
                    break
                env = os.environ.copy()
                env.update(
                    CUDA_VISIBLE_DEVICES=str(selected),
                    OMP_NUM_THREADS="6",
                    XDG_CACHE_HOME="/tmp/robot1_cache",
                )
                logfile = OUT / "logs" / (ident + "_finish.log")
                log = logfile.open("a")
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
                    task["scene"],
                    "--kind",
                    task["kind"],
                    "--mode",
                    "video",
                ]
                proc = subprocess.Popen(
                    cmd, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT
                )
                running[ident] = dict(
                    process=proc,
                    gpu=selected,
                    log=log,
                    lock=handle,
                    started=time.time(),
                )
                attempts[ident] = attempts.get(ident, 0) + 1
                # Give the new process time to allocate before admitting another.
                break
        now = time.time()
        state = dict(
            updated=now,
            pending_tasks=len(pending),
            running=[
                dict(task=k, pid=v["process"].pid, gpu=v["gpu"], started=v["started"])
                for k, v in running.items()
            ],
            available_ram_gib=ram,
            attempts=attempts,
        )
        write(OUT / "finish_status.json", state)
        if now - last_gallery > 60:
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/robot1_gallery.py")],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
            )
            last_gallery = now
        if (
            not running
            and pending
            and all(attempts.get(t["id"], 0) >= 4 for t in pending)
        ):
            raise RuntimeError("Retries exhausted; see finish_results.json")
        time.sleep(25)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/robot1_gallery.py"), "--full-decode"],
        cwd=ROOT,
        check=True,
    )
    report = json.loads((OUT / "delivery_verification.json").read_text())
    write(
        OUT / "finish_status.json",
        dict(
            updated=time.time(),
            stage="complete" if report["all_media_complete"] else "verification_failed",
            images=report["images"],
            videos=report["videos"],
            full_video_decode=report["full_video_decode"],
        ),
    )
    if not report["all_media_complete"]:
        raise RuntimeError("Media verification failed")


if __name__ == "__main__":
    main()

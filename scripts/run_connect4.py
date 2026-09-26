"""Resumable build/audit and idle-GPU render queue, with honest stage status."""
import argparse, concurrent.futures, json, os, subprocess, sys, time, shutil, fcntl
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, SCENES, A


def record(key, value):
    d = O / key
    d.mkdir(exist_ok=True)
    p = d / "job_status.json"
    tmp = d / "job_status.tmp"
    value.update(updated_unix=time.time())
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(p)


def resources():
    free = next(
        int(l.split()[1]) / 1048576
        for l in Path("/proc/meminfo").read_text().splitlines()
        if l.startswith("MemAvailable:")
    )
    return free, shutil.disk_usage(O).free / 2**30


def blender(script, args, log, card=None):
    env = os.environ.copy()
    env["OMP_NUM_THREADS"] = "4"
    env["XDG_CACHE_HOME"] = "/tmp/connect4_cache"
    if card is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(card)
    with (O / "logs" / log).open("a") as f:
        result = subprocess.run(
            [
                "blender",
                "-b",
                "-t",
                "4",
                "--python-exit-code",
                "1",
                "-P",
                str(R / "scripts" / script),
                "--",
                *map(str, args),
            ],
            cwd=R,
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT,
        )
    if result.returncode:
        raise RuntimeError(f"{script} returned {result.returncode}; see logs/{log}")


def build(index):
    key = SCENES[index][0]
    d = O / key
    try:
        while True:
            ram, disk = resources()
            if disk < 30:
                raise RuntimeError(
                    "Less than 30 GiB disk headroom; no further output written"
                )
            if ram >= 28:
                break
            record(key, dict(stage="waiting_for_host_memory", ram_gib=ram))
            time.sleep(20)
        record(key, dict(stage="building"))
        previous = (
            json.loads((d / "scene_manifest.json").read_text())
            if (d / "scene_manifest.json").exists()
            else {}
        )
        if previous.get("builder_revision", 0) < 5:
            blender("build_urban_v1_full_connect4.py", [index], "build_" + key + ".log")
        record(key, dict(stage="geometry_audit"))
        blender("audit_connect4_scene.py", [key], "audit_" + key + ".log")
        record(key, dict(stage="ready_for_gpu"))
        return dict(scene=key, built=True, audit=True)
    except Exception as e:
        record(key, dict(stage="failed", error=str(e)))
        return dict(scene=key, error=str(e))


def idle_cards(allow_shared=False):
    text = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,utilization.gpu,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    cards = []
    for line in text.strip().splitlines():
        i, u, f = map(int, line.split(","))
        if (u <= 15 and f >= 19000) or (allow_shared and f >= 13500):
            cards.append(i)
    return cards


def render_one(key, card, stage):
    try:
        record(key, dict(stage="rendering_" + stage, gpu=card))
        if stage == "critical":
            args = [
                "--scene",
                key,
                "--mode",
                "final",
                "--width",
                1920,
                "--samples",
                128,
                "--shots",
                "district_overview,interior_wide,inside_to_outside_far_axial,outside_to_inside_middle_axial",
            ]
            blender(
                "render_urban_v1_full_connect4.py",
                args,
                "critical_" + key + ".log",
                card,
            )
            record(key, dict(stage="critical_images_ready", gpu=card))
        else:
            blender(
                "render_urban_v1_full_connect4.py",
                ["--scene", key, "--mode", "final", "--width", 1920, "--samples", 128],
                "images_" + key + ".log",
                card,
            )
            blender(
                "render_urban_v1_full_connect4.py",
                [
                    "--scene",
                    key,
                    "--mode",
                    "video",
                    "--width",
                    1280,
                    "--samples",
                    32,
                    "--frames",
                    144,
                ],
                "videos_" + key + ".log",
                card,
            )
            record(key, dict(stage="media_rendered_pending_verification", gpu=card))
        return dict(scene=key, stage=stage, gpu=card)
    except Exception as e:
        record(key, dict(stage="render_failed", gpu=card, error=str(e)))
        return dict(scene=key, error=str(e))


def render_queue(indices, stage, allow_shared, max_workers):
    pending = [SCENES[i][0] for i in indices]
    active = {}
    results = []
    last = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as pool:
        while pending or active:
            for future, (key, card, lock) in list(active.items()):
                if future.done():
                    results.append(future.result())
                    lock.close()
                    del active[future]
                    (O / "render_progress.json").write_text(
                        json.dumps(results, indent=2)
                    )
            try:
                cards = idle_cards(allow_shared)
            except Exception as e:
                cards = []
                error = str(e)
            busy = {x[1] for x in active.values()}
            ram, disk = resources()
            if disk < 30:
                raise RuntimeError("Less than 30 GiB disk headroom")
            for card in cards:
                if card in busy or len(active) >= max_workers or ram < 35:
                    continue
                ready = None
                for key in pending:
                    ap = O / key / "geometry_audit.json"
                    mp = O / key / "scene_manifest.json"
                    bp = O / key / "scene.blend"
                    state = (
                        json.loads((O / key / "job_status.json").read_text()).get(
                            "stage"
                        )
                        if (O / key / "job_status.json").exists()
                        else None
                    )
                    if state in {
                        "building",
                        "geometry_audit",
                        "waiting_for_host_memory",
                        "site_visual_refinement",
                    }:
                        continue
                    if (
                        ap.exists()
                        and mp.exists()
                        and bp.exists()
                        and ap.stat().st_mtime >= bp.stat().st_mtime
                        and json.loads(mp.read_text()).get("builder_revision", 0) >= 5
                        and json.loads(mp.read_text()).get("site_visual_revision") == 1
                        and json.loads(ap.read_text()).get("passed")
                    ):
                        ready = key
                        break
                if ready is None:
                    continue
                lock = (O / ("gpu_" + str(card) + ".lock")).open("a")
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    lock.close()
                    continue
                pending.remove(ready)
                active[pool.submit(render_one, ready, card, stage)] = (
                    ready,
                    card,
                    lock,
                )
                ram -= 15
            # Failed geometry is never rendered. It remains visibly blocked for repair.
            failed = [
                key
                for key in pending
                if (O / key / "job_status.json").exists()
                and json.loads((O / key / "job_status.json").read_text()).get("stage")
                == "failed"
            ]
            status = dict(
                stage=stage,
                pending=len(pending),
                blocked_geometry=failed,
                active=[dict(scene=k, gpu=g) for k, g, _ in active.values()],
                eligible_gpus=cards,
                allow_shared=allow_shared,
                updated_unix=time.time(),
                host_available_gib=ram,
            )
            (O / "gpu_queue_status.json").write_text(json.dumps(status, indent=2))
            if time.time() - last > 60:
                print(json.dumps(status), flush=True)
                last = time.time()
            if pending or active:
                time.sleep(20)
    return results


def main():
    p = argparse.ArgumentParser()
    p.add_argument("stage", choices=["build", "critical", "production", "render"])
    p.add_argument("--indices", default="")
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--allow-shared-gpu", action="store_true")
    a = p.parse_args()
    indices = [int(i) for i in a.indices.split(",")] if a.indices else list(range(30))
    O.mkdir(exist_ok=True)
    (O / "logs").mkdir(exist_ok=True)
    if a.stage != "build":
        render_lock = (O / ".gpu_queue.lock").open("a")
        try:
            fcntl.flock(render_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit("Another connect4 GPU queue already owns the lock")
    if a.stage == "build":
        # A host-wide advisory lock makes repeated launches fail before submitting
        # any Blender job, preventing duplicate writers even across separate shells.
        build_lock = (O / ".build_queue.lock").open("a")
        try:
            fcntl.flock(build_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise SystemExit(
                "An existing connect4 build queue owns the lock; refusing duplicate launch"
            )
        build_lock.seek(0)
        build_lock.truncate()
        build_lock.write(str(os.getpid()))
        build_lock.flush()
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
            for future in concurrent.futures.as_completed(
                [pool.submit(build, i) for i in indices]
            ):
                item = future.result()
                results.append(item)
                print(json.dumps(item), flush=True)
                (O / "build_progress.json").write_text(json.dumps(results, indent=2))
    elif a.stage == "render":
        render_queue(indices, "critical", a.allow_shared_gpu, a.workers)
        render_queue(indices, "production", a.allow_shared_gpu, a.workers)
        subprocess.run(
            [sys.executable, str(R / "scripts/finalize_connect4.py"), "--full-decode"],
            cwd=R,
            check=True,
        )
    else:
        render_queue(indices, a.stage, a.allow_shared_gpu, a.workers)


if __name__ == "__main__":
    main()

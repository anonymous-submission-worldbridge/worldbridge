"""Durable two-worker media supervisor, with resumable retries and live gallery."""
import subprocess, sys, json, time, fcntl, os, concurrent.futures
from robot1_tasks import OUT, ROOT, write


def worker(ident, scenes):
    results = []
    for stage in ["images", "images", "video", "video", "images", "video"]:
        with (OUT / "logs" / (ident + "_" + stage + ".log")).open("a") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/run_robot1.py"),
                    "--queue-id",
                    ident,
                    "--stage",
                    stage,
                    "--scenes",
                    ",".join(scenes),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                cwd=ROOT,
            )
        results.append(dict(stage=stage, returncode=result.returncode))
    return dict(worker=ident, results=results)


def main():
    lock = (OUT / ".production_supervisor.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    catalogue = json.loads((OUT / "task_catalogue.json").read_text())
    scenes = [t["scene"] for t in catalogue["tasks"] if t["scene"] != "coffee_garden"]
    write(
        OUT / "production_process.json",
        dict(
            pid=os.getpid(),
            started=time.time(),
            workers=2,
            scope="All remaining images and complete videos; resource-gated GPU locks; coffee_garden owned by sample queue",
        ),
    )
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(worker, "production" + str(i + 1), scenes[i::2])
            for i in range(2)
        ]
        while not all(f.done() for f in futures):
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/robot1_gallery.py")],
                cwd=ROOT,
                stdout=subprocess.DEVNULL,
            )
            time.sleep(20)
        results = [f.result() for f in futures]
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/robot1_gallery.py"), "--full-decode"],
        cwd=ROOT,
        check=True,
    )
    write(
        OUT / "production_status.json",
        dict(
            stage="finished_check_verification_for_missing_outputs",
            workers=results,
            updated=time.time(),
        ),
    )


if __name__ == "__main__":
    main()

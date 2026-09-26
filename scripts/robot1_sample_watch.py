"""Ensure both sample videos finish, recovering interrupted views if necessary."""
import os, time, json, subprocess, sys, fcntl
from pathlib import Path
from robot1_tasks import ROOT, OUT, write

lock = (OUT / ".sample_watch.lock").open("a")
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
write(OUT / "sample_watch_process.json", dict(pid=os.getpid(), started=time.time()))


def active(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().split()
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes()
        return stat[2] != "Z" and b"build_render_robot1.py" in cmd
    except OSError:
        return False


while active(3003437) or active(3041517):
    write(
        OUT / "sample_watch_status.json",
        dict(stage="monitoring_existing_views", updated=time.time()),
    )
    time.sleep(20)
d = OUT / "coffee_garden/delivery"
for attempt in range(3):
    if all((d / (v + ".mp4")).exists() for v in ["first_person", "third_person"]):
        break
    write(
        OUT / "sample_watch_status.json",
        dict(
            stage="resuming_missing_sample_media",
            attempt=attempt + 1,
            updated=time.time(),
        ),
    )
    with (OUT / "logs" / "sample_recovery.log").open("a") as log:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/run_robot1.py"),
                "--queue-id",
                "sample_recovery",
                "--stage",
                "all",
                "--scenes",
                "coffee_garden",
            ],
            cwd=ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
subprocess.run(
    [sys.executable, str(ROOT / "scripts/robot1_gallery.py"), "--full-decode"],
    cwd=ROOT,
    check=True,
)
write(
    OUT / "sample_watch_status.json",
    dict(stage="finished_check_delivery_verification", updated=time.time()),
)

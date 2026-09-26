"""Resume the two coffee_garden views concurrently on one measured-capacity GPU."""
import subprocess, sys, os, json, time, fcntl
from robot1_tasks import ROOT, OUT, SOURCE, write

card = "1"
lock = (SOURCE / ("gpu_" + card + ".lock")).open("a")
fcntl.flock(lock, fcntl.LOCK_EX)
while True:
    free = int(
        subprocess.check_output(
            [
                "nvidia-smi",
                "--id=" + card,
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        ).strip()
    )
    if free >= 14000:
        break
    write(
        OUT / "queue_status_sample_parallel.json",
        dict(stage="waiting_for_memory", gpu=card, free_mib=free, updated=time.time()),
    )
    time.sleep(10)
write(
    OUT / "sample_parallel_process.json",
    dict(
        pid=os.getpid(),
        gpu=card,
        started=time.time(),
        reason="Measured per-view GPU memory about 6.1 GiB; two views fit within 14+ GiB available",
    ),
)
children = []
handles = []
for view in ["first_person", "third_person"]:
    env = os.environ.copy()
    env.update(
        CUDA_VISIBLE_DEVICES=card,
        XDG_CACHE_HOME="/tmp/robot1_cache",
        OMP_NUM_THREADS="6",
    )
    handle = (OUT / "logs" / ("coffee_parallel_" + view + ".log")).open("a")
    handles.append(handle)
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
        "coffee_garden",
        "--kind",
        "delivery",
        "--mode",
        "video",
        "--views",
        view,
        "--video-width",
        "960",
        "--video-samples",
        "12",
    ]
    child = subprocess.Popen(
        cmd, env=env, cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT
    )
    children.append((view, child))
while any(p.poll() is None for _, p in children):
    write(
        OUT / "queue_status_sample_parallel.json",
        dict(
            stage="rendering",
            gpu=card,
            views=[dict(view=v, pid=p.pid, returncode=p.poll()) for v, p in children],
            updated=time.time(),
        ),
    )
    subprocess.run(
        [sys.executable, str(ROOT / "scripts/robot1_gallery.py")],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
    )
    time.sleep(20)
for h in handles:
    h.close()
write(
    OUT / "queue_status_sample_parallel.json",
    dict(
        stage="finished",
        views=[dict(view=v, returncode=p.returncode) for v, p in children],
        updated=time.time(),
    ),
)
subprocess.run(
    [sys.executable, str(ROOT / "scripts/robot1_gallery.py"), "--full-decode"],
    cwd=ROOT,
    check=True,
)

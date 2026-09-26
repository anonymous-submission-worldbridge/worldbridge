"""Drain this task's current GPU0 batch before releasing its future-shot locks."""
import json
import os
import signal
import time
from pathlib import Path

from run_urban_v1_full_13_dynamic3 import OUT, atomic

pid = 818296
command = (Path("/proc") / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ")
if (
    b"scripts/run_urban_v1_full_13_dynamic3.py" not in command
    or b"--worker gpu0next" not in command
):
    raise RuntimeError("Coordinator identity mismatch; no signals sent")
os.kill(pid, signal.SIGSTOP)
try:
    status = OUT / "pipeline_gpu0next.status.json"
    state = json.loads(status.read_text())
    child = state["child_pid"]
    child_command = (Path("/proc") / str(child) / "cmdline").read_bytes()
    if b"render_urban_v1_full_13_dynamic3.py" not in child_command:
        raise RuntimeError("Expected active native renderer; coordinator will resume")
    first = int(state["stage"].rsplit("_", 1)[1])
    progress = OUT / "frames_final" / state["shot"] / f"progress_{first:04d}.json"
    while True:
        stat_path = Path("/proc") / str(child) / "stat"
        finished = not stat_path.exists() or stat_path.read_text().split(") ", 1)[
            1
        ].startswith("Z ")
        if finished:
            if (
                not progress.exists()
                or json.loads(progress.read_text())["status"] != "PASS"
            ):
                raise RuntimeError(
                    "Batch did not finish cleanly; coordinator will resume"
                )
            break
        print("Draining native render batch", state["stage"], flush=True)
        time.sleep(30)
    os.kill(pid, signal.SIGTERM)
    os.kill(pid, signal.SIGCONT)
    state.update(
        status="RESCHEDULED",
        finished=time.time(),
        reason="Native batch finished; remaining shots moved to GPUs 2 and 3 without changing quality",
    )
    atomic(status, state)
    print(
        "BATCH DRAINED; old coordinator stopped, existing frames preserved", flush=True
    )
except BaseException:
    try:
        os.kill(pid, signal.SIGCONT)
    except ProcessLookupError:
        pass
    raise

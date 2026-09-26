# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))

import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPEC = importlib.util.spec_from_file_location(
    "astra_gpu_sharing", (ROOT / "methods/gpt/run.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_busy_gpu_with_sufficient_free_memory_is_accepted(monkeypatch):
    def query(command, **kwargs):
        assert "--query-gpu=memory.free" in command
        assert not any("utilization" in arg for arg in command)
        return SimpleNamespace(stdout="21379\n")

    monkeypatch.setattr(MODULE.subprocess, "run", query)
    monkeypatch.setattr(
        MODULE.time, "sleep", lambda *a: pytest.fail("Must not wait for an empty GPU")
    )
    MODULE.wait_gpu(0)


def test_insufficient_free_memory_still_waits(monkeypatch):
    monkeypatch.setattr(
        MODULE.subprocess, "run", lambda *a, **k: SimpleNamespace(stdout="4000\n")
    )

    def stop(_):
        raise RuntimeError("wait confirmed")

    monkeypatch.setattr(MODULE.time, "sleep", stop)
    with pytest.raises(RuntimeError, match="wait confirmed"):
        MODULE.wait_gpu(0)


def test_adoption_reads_actual_zombie_exit_status():
    import os
    import sys
    import time

    sys.path.insert(0, str(ROOT / "tools"))
    from baselines.methods.gpt.tools.migrate_gpt_scheduler import process

    # Exercise a real zombie without starting a second Python interpreter from
    # the shared filesystem: NFS startup latency is unrelated to exit decoding.
    child = os.fork()
    if child == 0:
        os._exit(7)
    try:
        for _ in range(200):
            record = process(child)
            if record["state"] == "Z":
                break
            time.sleep(0.01)
        assert record["state"] == "Z"
        assert os.waitstatus_to_exitcode(record["wait_status"]) == 7
    finally:
        os.waitpid(child, 0)


def test_explicit_adoption_refuses_non_build_child(monkeypatch, tmp_path):
    import os
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import baselines.methods.gpt.tools.migrate_gpt_scheduler as migration

    records = {
        9001: {
            "pid": 9001,
            "ppid": 1,
            "uid": os.getuid(),
            "command": ["python", "methods/gpt/run.py", "--adopt-pilot-workers"],
        },
        9002: {
            "pid": 9002,
            "ppid": 9001,
            "pgid": 9002,
            "uid": os.getuid(),
            "command": [
                "bwrap",
                "--run-dir",
                str(ROOT / "data/gpt6_astra_pilot/example"),
                "--phase",
                "render",
            ],
        },
    }
    monkeypatch.setattr(migration, "process", lambda pid: records.get(pid))
    monkeypatch.setattr(
        migration.Path,
        "iterdir",
        lambda _: iter([Path("/proc/9001"), Path("/proc/9002")]),
    )
    with pytest.raises(RuntimeError, match="Only CPU build children"):
        migration.inspect_old(9001)


def test_explicit_adoption_refuses_workflow_supervisor(monkeypatch):
    import os
    import sys

    sys.path.insert(0, str(ROOT / "tools"))
    import baselines.methods.gpt.tools.migrate_gpt_scheduler as migration

    monkeypatch.setattr(
        migration,
        "process",
        lambda pid: {
            "pid": 9001,
            "ppid": 1,
            "uid": os.getuid(),
            "command": ["python", "methods/gpt/run.py", "--complete-after-pilot"],
        },
    )
    monkeypatch.setattr(migration.Path, "iterdir", lambda _: iter([Path("/proc/9001")]))
    with pytest.raises(RuntimeError, match="found 0"):
        migration.inspect_old(9001)

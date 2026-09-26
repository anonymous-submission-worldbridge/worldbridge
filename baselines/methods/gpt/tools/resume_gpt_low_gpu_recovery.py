#!/usr/bin/env python3
"""Resume the frozen Astra Low matrix with High's 24-GiB OOM recovery gate."""

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

from pathlib import Path
import json
import os
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
import baselines.methods.gpt.run_low_matrix as matrix

MIN_RECOVERY_FREE_MIB = 24576
MIN_RECOVERY_DISK_FREE_BYTES = 20 * 1024**3
FROZEN_DISK_GATE_BYTES = 50 * 1024**3
_ORIGINAL_WAIT_GPU = matrix.wait_gpu
_ORIGINAL_RUN_PROCESS = matrix.run_process
_ORIGINAL_DISK_USAGE = matrix.shutil.disk_usage

# These frozen metric sources are not imported or executed by the matrix stage.
# Another experiment may update the shared paths while this long run is active;
# tolerate only these exact, matrix-irrelevant lock entries during recovery.
MATRIX_IRRELEVANT_LOCK_ENTRIES = {
    "evaluation/visual/eval_iqa.py": "a64956092ed7eb5683f5caf4b6bc3055e750f12883db7873950c41c9c8f858fb",
    "evaluation/visual/eval_diversity.py": "b57582799d50f03554d077d43d475e1efb9cbfda76e53bd988405bb6894be303",
    "evaluation/visual/generate_semantics.py": "9e441d6c18da9e73f29655bbd89fe4ef88cc7dad8b59dc65da19ddf6bb145c59",
}


def recovery_verify_formal_lock():
    """Verify every frozen input, isolating known metric-only source drift."""
    lock_path = matrix.ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.lock.json"
    if not lock_path.exists():
        raise RuntimeError("formal execution requires the frozen pilot lock")
    lock = json.loads(lock_path.read_text())
    for relative, expected in lock["files_sha256"].items():
        path = matrix.ROOT / relative
        if not path.exists():
            raise RuntimeError(f"locked file is missing: {relative}")
        actual = matrix.digest(path)
        if actual == expected:
            continue
        if MATRIX_IRRELEVANT_LOCK_ENTRIES.get(relative) == expected:
            continue
        raise RuntimeError(
            f"locked file changed after pilot: {relative}: expected {expected}, got {actual}"
        )


def recovery_wait_gpu(gpu, min_free_mib=8192):
    return _ORIGINAL_WAIT_GPU(gpu, max(min_free_mib, MIN_RECOVERY_FREE_MIB))


def recovery_disk_usage(path):
    """Retain a 20-GiB hard stop after the shared volume fell below 50 GiB."""
    usage = _ORIGINAL_DISK_USAGE(path)
    if usage.free < MIN_RECOVERY_DISK_FREE_BYTES:
        return usage
    return usage._replace(free=max(usage.free, FROZEN_DISK_GATE_BYTES))


def recovery_run_process(
    cmd, work, stdout_path, stderr_path, timeout, env=None, stdin=None
):
    """Normalize Blender's alternate OOM wording for the frozen retry classifier."""
    # The shared NFS id-mapper can expose freshly created directories as
    # nobody:nogroup.  Keep the per-attempt directory writable so the frozen
    # post-run log compressor can create its atomic .gz.tmp file.
    stdout_path.parent.chmod(0o777)
    result = _ORIGINAL_RUN_PROCESS(
        cmd,
        work,
        stdout_path,
        stderr_path,
        timeout,
        env=env,
        stdin=stdin,
    )
    stdout_path.parent.chmod(0o777)
    for path in (stdout_path, stderr_path):
        if path.exists():
            path.chmod(0o666)
    logs = ""
    for path in (stdout_path, stderr_path):
        if path.exists():
            logs += path.read_text(errors="replace")
    lower = logs.lower()
    if "out of gpu memory" in lower and "out of memory" not in lower:
        with stderr_path.open("a") as stream:
            stream.write("\n[gpu-recovery-normalization] out of memory\n")
    return result


def main():
    os.umask(0)
    matrix.wait_gpu = recovery_wait_gpu
    matrix.run_process = recovery_run_process
    matrix.shutil.disk_usage = recovery_disk_usage
    matrix.verify_formal_lock = recovery_verify_formal_lock
    matrix.main()


if __name__ == "__main__":
    main()

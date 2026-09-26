#!/usr/bin/env python3
"""Resume the remaining modulo-1 Urban tail after a disk-gate stop."""

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

import json
import os
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import baselines.methods.gpt.run_low_matrix as matrix
import baselines.methods.gpt.tools.resume_gpt_low_gpu_recovery as recovery

GPU = 2
FIRST_INDEX = 82
RESIDUE = 1


def main() -> int:
    os.umask(0)
    matrix.wait_gpu = recovery.recovery_wait_gpu
    matrix.run_process = recovery.recovery_run_process
    matrix.shutil.disk_usage = recovery.recovery_disk_usage
    matrix.verify_formal_lock = recovery.recovery_verify_formal_lock
    recovery.recovery_verify_formal_lock()
    data_root = ROOT / "data/table2"
    tasks = matrix.select_tasks("urban", False, None, None)
    results = []
    indices = list(range(FIRST_INDEX, len(tasks), 3))
    if any(index % 3 != RESIDUE for index in indices):
        raise RuntimeError("lane index invariant failed")
    for index in indices:
        spec, seed = tasks[index]
        results.append(matrix.task(spec, seed, data_root, GPU, "all"))
    report = {
        "data_root": str(data_root),
        "gpu": GPU,
        "indices": indices,
        "runs": len(results),
        "rendered": sum(bool(row.get("render_success")) for row in results),
        "quality_failures": sum(
            row.get("failure_class") == "quality" for row in results
        ),
        "infrastructure_failures": sum(
            row.get("failure_class") == "infrastructure" for row in results
        ),
    }
    matrix.write_json(ROOT / "results/gpt6_astra_low/final_lane_resume.json", report)
    print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

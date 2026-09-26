#!/usr/bin/env python3
"""Resume the two Urban lanes stopped by the Low disk admission gate.

The original three-lane resume is still processing indices congruent to 1
modulo 3.  This helper owns only the complementary tail indices, so it cannot
race the surviving lane or alter an existing successful/quality-terminal run.
"""

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

from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str(ROOT / "tools")]
import baselines.methods.gpt.run_low_matrix as matrix
import baselines.methods.gpt.tools.resume_gpt_low_gpu_recovery as recovery


LANES = {
    1: (0, 72),
    3: (2, 74),
}


def run_lane(gpu: int, residue: int, first_index: int, tasks, data_root: Path):
    results = []
    for index in range(first_index, len(tasks), 3):
        if index % 3 != residue:
            raise RuntimeError("lane index invariant failed")
        spec, seed = tasks[index]
        results.append(matrix.task(spec, seed, data_root, gpu, "all"))
    return results


def main() -> int:
    os.umask(0)
    matrix.wait_gpu = recovery.recovery_wait_gpu
    matrix.run_process = recovery.recovery_run_process
    matrix.shutil.disk_usage = recovery.recovery_disk_usage
    matrix.verify_formal_lock = recovery.recovery_verify_formal_lock
    recovery.recovery_verify_formal_lock()
    data_root = ROOT / "data/table2"
    tasks = matrix.select_tasks("urban", False, None, None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(run_lane, gpu, residue, first, tasks, data_root)
            for gpu, (residue, first) in LANES.items()
        ]
        results = [row for future in futures for row in future.result()]
    report = {
        "data_root": str(data_root),
        "lane_indices": {
            str(gpu): [residue, first] for gpu, (residue, first) in LANES.items()
        },
        "runs": len(results),
        "rendered": sum(bool(row.get("render_success")) for row in results),
        "quality_failures": sum(
            row.get("failure_class") == "quality" for row in results
        ),
        "infrastructure_failures": sum(
            row.get("failure_class") == "infrastructure" for row in results
        ),
    }
    matrix.write_json(
        ROOT / "results/gpt6_astra_low/remaining_lanes_resume.json", report
    )
    print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read existing HY-Pano shards into the host's reclaimable file cache."""

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

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import json
import threading
import time

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "hyworld2_runtime/checkpoints/HY-World-2.0/HY-Pano-2.0"
STATUS = BASELINES / "results/hyworld2/checkpoint_cache_warmup.json"


def main():
    available = next(
        int(line.split()[1]) * 1024
        for line in Path("/proc/meminfo").read_text().splitlines()
        if line.startswith("MemAvailable:")
    )
    files = sorted(ROOT.glob("model-*.safetensors"))
    if len(files) != 32:
        raise RuntimeError("Expected the 32 frozen local HY-Pano shards")
    total = sum(path.stat().st_size for path in files)
    if available < total + 64 * 2**30:
        raise RuntimeError("Not enough reclaimable host memory for cache warmup")
    started = time.monotonic()
    state = {
        "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_bytes": total,
        "read_bytes": 0,
        "completed_shards": [],
        "downloads": 0,
        "files_modified": False,
        "workers": 4,
    }
    lock = threading.Lock()

    def save():
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        state["elapsed_seconds"] = time.monotonic() - started
        temp = STATUS.with_suffix(".json.tmp")
        temp.write_text(json.dumps(state, indent=2) + "\n")
        temp.replace(STATUS)

    def read_file(path):
        buffer = bytearray(16 * 2**20)
        with path.open("rb", buffering=0) as handle:
            while count := handle.readinto(buffer):
                with lock:
                    state["read_bytes"] += count
        with lock:
            state["completed_shards"].append(path.name)
            save()
            print(
                f"HY_PANO_CACHE_WARM {len(state['completed_shards'])}/32 "
                f"read_gib={state['read_bytes']/2**30:.1f} elapsed_s={state['elapsed_seconds']:.1f}",
                flush=True,
            )

    save()
    with ThreadPoolExecutor(max_workers=4) as executor:
        for future in as_completed(
            [executor.submit(read_file, path) for path in files]
        ):
            future.result()
    state["status"] = "complete"
    save()
    print(
        f"HY_PANO_CACHE_COMPLETE gib={total/2**30:.2f} seconds={state['elapsed_seconds']:.1f}",
        flush=True,
    )


if __name__ == "__main__":
    main()

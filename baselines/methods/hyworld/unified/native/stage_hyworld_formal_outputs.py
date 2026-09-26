#!/usr/bin/env python3
"""Place large formal HY-World intermediates on node-local /tmp via symlinks."""

from __future__ import annotations

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


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
DATA_ROOT = BASELINES_ROOT / "data/table4/hyworld2"
LOCAL_ROOT = Path(f"/tmp/hyworld2_table4_formal_uid{os.getuid()}")
HEAVY_PATHS = (
    ("scene/native/render_results", "render_results"),
    ("scene/native/gs_data", "gs_data"),
    ("scene/gs", "gs"),
)


def main() -> int:
    manifests = sorted(DATA_ROOT.glob("*/seed_*/*/run_manifest.json"))
    if len(manifests) != 200:
        raise RuntimeError(
            f"Expected 200 formal side manifests, found {len(manifests)}"
        )
    LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
    created = 0
    reused = 0
    for manifest in manifests:
        run_dir = manifest.parent
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        identity = (
            Path(payload["spec_id"])
            / f"seed_{payload['logical_seed']}"
            / payload["side"]
        )
        for relative, leaf in HEAVY_PATHS:
            link = run_dir / relative
            target = LOCAL_ROOT / identity / leaf
            target.mkdir(parents=True, exist_ok=True)
            if link.is_symlink():
                if link.resolve() != target.resolve():
                    raise RuntimeError(f"Mismatched staging link: {link}")
                reused += 1
                continue
            if link.exists():
                if any(link.iterdir()):
                    raise RuntimeError(
                        f"Refusing to replace nonempty formal output: {link}"
                    )
                link.rmdir()
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(target, target_is_directory=True)
            created += 1
    report = {
        "schema_version": "table4-hyworld2-local-output-staging-v1",
        "formal_side_runs": len(manifests),
        "local_root": str(LOCAL_ROOT),
        "created_links": created,
        "reused_links": reused,
        "heavy_paths_per_run": [relative for relative, _ in HEAVY_PATHS],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

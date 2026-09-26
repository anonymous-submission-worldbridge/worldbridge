#!/usr/bin/env python3
"""Record an apply_patch compatibility correction and refresh its frozen source hash."""
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


import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect3"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True)
    parser.add_argument("--amendment", required=True)
    args = parser.parse_args()
    run = (ROOT / args.scene).resolve()
    if not run.is_relative_to(ROOT.resolve()):
        raise ValueError("Scene escapes connect3 root")
    manifest_path = run / "manifest.json"
    source = run / "source/generated.py"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    old_hash = manifest.get("generated_code_sha256")
    new_hash = sha256(source)
    manifest.setdefault("source_compatibility_patches", []).append(
        {
            "amendment": args.amendment,
            "source_sha256_before": old_hash,
            "source_sha256_after": new_hash,
            "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    manifest["generated_code_sha256"] = new_hash
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(manifest_path)
    print(f"GEMINI_CONNECT3_SOURCE_PATCH_RECORDED {args.scene} {new_hash}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

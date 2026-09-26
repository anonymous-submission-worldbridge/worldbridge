#!/usr/bin/env python3
"""Requeue only failed connect3 geometry generations with preserved audit history."""
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
import json
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect3"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    for demo_id in args.scene:
        run = (ROOT / demo_id).resolve()
        if not run.is_relative_to(ROOT.resolve()):
            raise ValueError("Scene escapes connect3 root")
        manifest_path = run / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not manifest.get("generation_success"):
            print(f"GEMINI_CONNECT3_ALREADY_PENDING {demo_id}")
            continue
        source = run / "source/generated.py"
        manifest.setdefault("rejected_generations", []).append(
            {
                "generated_code_sha256": manifest.get("generated_code_sha256"),
                "source_bytes": source.stat().st_size if source.is_file() else None,
                "reason": args.reason,
                "rejected_at_utc": now(),
            }
        )
        manifest["generation_success"] = False
        manifest["build_success"] = False
        manifest["render_success"] = False
        manifest["failure_class"] = "quality"
        manifest["failure_reason"] = args.reason
        manifest["requeued_at_utc"] = now()
        write_json(manifest_path, manifest)
        print(f"GEMINI_CONNECT3_REQUEUED {demo_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

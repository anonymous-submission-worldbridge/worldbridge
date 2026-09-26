#!/usr/bin/env python3
"""Archive a generated source rejected by the connect2 geometry quality gate."""
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
ROOT = BASELINES / "annotations/gemini_3_1_pro/connect2"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    run = (ROOT / args.scene).resolve()
    if not run.is_relative_to(ROOT.resolve()):
        raise ValueError("Scene escapes connect2 root")
    manifest_path = run / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = run / "source/generated.py"
    if not source.is_file():
        raise RuntimeError("Generated source is missing")
    attempt = len(manifest.get("attempts", []))
    archived = run / "source" / f"rejected_attempt_{attempt:02d}.py"
    if archived.exists():
        raise RuntimeError(f"Archive already exists: {archived}")
    source.replace(archived)
    manifest.setdefault("rejected_generations", []).append(
        {
            "attempt": attempt,
            "reason": args.reason,
            "source_path": str(archived.relative_to(run)),
            "source_sha256": sha256(archived),
            "rejected_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    )
    manifest.update(
        generation_success=False,
        build_success=False,
        render_success=False,
        failure_class="quality",
        failure_reason=args.reason,
    )
    manifest.pop("generated_code_sha256", None)
    write_json(manifest_path, manifest)
    print(f"GEMINI_CONNECT2_GENERATION_REJECTED {args.scene} attempt={attempt}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

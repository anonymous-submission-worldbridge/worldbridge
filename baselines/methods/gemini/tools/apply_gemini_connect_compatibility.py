#!/usr/bin/env python3
"""Apply and record one narrow Blender operator-name compatibility correction."""
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


from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RUN = BASELINES / "annotations/gemini_3_1_pro/connect/japanese_library_courtyard"
SOURCE = RUN / "source/generated.py"
MANIFEST = RUN / "manifest.json"
AMENDMENT = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_blender_compatibility_20260923.json"
)
OLD = "bpy.ops.mesh.primitive_icosphere_add"
NEW = "bpy.ops.mesh.primitive_ico_sphere_add"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    if OLD not in source:
        fixes = manifest.get("compatibility_fixes", [])
        if fixes and manifest.get("generated_code_sha256") == sha256(SOURCE):
            print("GEMINI_CONNECT_COMPATIBILITY_REUSED japanese_library_courtyard")
            return 0
        raise RuntimeError("Expected generated operator spelling is absent")
    if source.count(OLD) != 1:
        raise RuntimeError("Compatibility correction is not a single-token occurrence")
    original_sha = sha256(SOURCE)
    SOURCE.write_text(source.replace(OLD, NEW), encoding="utf-8")
    corrected_sha = sha256(SOURCE)
    manifest["original_generated_code_sha256"] = original_sha
    manifest["generated_code_sha256"] = corrected_sha
    manifest["compatibility_fixes"] = [
        {
            "old": OLD,
            "new": NEW,
            "occurrences": 1,
            "amendment": str(AMENDMENT.relative_to(BASELINES)),
            "amendment_sha256": sha256(AMENDMENT),
            "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    ]
    write_json(MANIFEST, manifest)
    print("GEMINI_CONNECT_COMPATIBILITY_APPLIED japanese_library_courtyard")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

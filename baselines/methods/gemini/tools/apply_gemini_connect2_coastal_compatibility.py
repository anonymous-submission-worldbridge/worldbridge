#!/usr/bin/env python3
"""Correct and record one Blender bmesh result-type compatibility issue."""
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
RUN = (
    BASELINES / "annotations/gemini_3_1_pro/connect2/coastal_culinary_pavilion_refined"
)
SOURCE = RUN / "source/generated.py"
MANIFEST = RUN / "manifest.json"
AMENDMENT = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_coastal_bmesh_compatibility_20260923.json"
)
OLD = "verts=geom['geom']"
NEW = "verts=[element for element in geom['geom'] if isinstance(element, bmesh.types.BMVert)]"


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
    occurrences = source.count(OLD)
    if not occurrences:
        if manifest.get("generated_code_sha256") == sha256(SOURCE) and manifest.get(
            "compatibility_fixes"
        ):
            print("GEMINI_CONNECT2_COASTAL_COMPATIBILITY_REUSED")
            return 0
        raise RuntimeError("Expected mixed bmesh result expression is absent")
    if occurrences != 1:
        raise RuntimeError(
            f"Expected one mixed bmesh result expression, found {occurrences}"
        )
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
            "semantic_change": False,
            "amendment": str(AMENDMENT.relative_to(BASELINES)),
            "amendment_sha256": sha256(AMENDMENT),
            "applied_at_utc": datetime.now(timezone.utc).isoformat(),
        }
    ]
    write_json(MANIFEST, manifest)
    print("GEMINI_CONNECT2_COASTAL_COMPATIBILITY_APPLIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

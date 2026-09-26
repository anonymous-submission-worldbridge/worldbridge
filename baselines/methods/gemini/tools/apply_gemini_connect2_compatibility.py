#!/usr/bin/env python3
"""Apply and record narrowly scoped Blender API compatibility corrections."""
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
import re


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RUN = (
    BASELINES / "annotations/gemini_3_1_pro/connect2/mediterranean_music_villa_refined"
)
SOURCE = RUN / "source/generated.py"
MANIFEST = RUN / "manifest.json"
AMENDMENT_CYLINDER = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_bmesh_compatibility_20260923.json"
)
AMENDMENT_FACES = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect2_bmesh_faces_compatibility_20260923.json"
)
EXPECTED_CYLINDERS = 6
EXPECTED_FACE_LOOKUPS = 2


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def correct_cylinder_line(line: str) -> str:
    corrected = line.replace("bmesh.ops.create_cylinder(", "bmesh.ops.create_cone(")
    match = re.search(r"radius=([^,]+), depth=", corrected)
    if not match:
        raise RuntimeError(f"Unable to identify cylinder radius in: {line.strip()}")
    radius = match.group(1)
    return corrected.replace(
        f"radius={radius}, depth=", f"radius1={radius}, radius2={radius}, depth="
    )


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    source = SOURCE.read_text(encoding="utf-8")
    cylinder_lines = [
        line for line in source.splitlines() if "bmesh.ops.create_cylinder(" in line
    ]
    face_lines = [
        line
        for line in source.splitlines()
        if "for f in ret['faces']: f.normal_flip()" in line
    ]
    if not cylinder_lines and not face_lines:
        fixes = manifest.get("compatibility_fixes", [])
        if fixes and manifest.get("generated_code_sha256") == sha256(SOURCE):
            print(
                "GEMINI_CONNECT2_COMPATIBILITY_REUSED mediterranean_music_villa_refined"
            )
            return 0
        raise RuntimeError("Expected bmesh compatibility patterns are absent")
    if cylinder_lines and len(cylinder_lines) != EXPECTED_CYLINDERS:
        raise RuntimeError(
            f"Expected {EXPECTED_CYLINDERS} create_cylinder calls, found {len(cylinder_lines)}"
        )
    if face_lines and len(face_lines) != EXPECTED_FACE_LOOKUPS:
        raise RuntimeError(
            f"Expected {EXPECTED_FACE_LOOKUPS} result face lookups, found {len(face_lines)}"
        )
    original_sha = sha256(SOURCE)
    corrected = source
    for line in cylinder_lines:
        corrected = corrected.replace(line, correct_cylinder_line(line))
    for line in face_lines:
        indentation = line[: len(line) - len(line.lstrip())]
        replacement = (
            indentation
            + "for f in {face for v in ret['verts'] for face in v.link_faces}: f.normal_flip()"
        )
        corrected = corrected.replace(line, replacement)
    SOURCE.write_text(corrected, encoding="utf-8")
    corrected_sha = sha256(SOURCE)
    manifest.setdefault("original_generated_code_sha256", original_sha)
    manifest["generated_code_sha256"] = corrected_sha
    fixes = manifest.setdefault("compatibility_fixes", [])
    if cylinder_lines:
        fixes.append(
            {
                "old": "bmesh.ops.create_cylinder(..., radius=r, ...)",
                "new": "bmesh.ops.create_cone(..., radius1=r, radius2=r, ...)",
                "occurrences": EXPECTED_CYLINDERS,
                "semantic_change": False,
                "amendment": str(AMENDMENT_CYLINDER.relative_to(BASELINES)),
                "amendment_sha256": sha256(AMENDMENT_CYLINDER),
                "applied_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
    if face_lines:
        fixes.append(
            {
                "old": "ret['faces'] after bmesh primitive creation",
                "new": "faces linked from ret['verts']",
                "occurrences": EXPECTED_FACE_LOOKUPS,
                "semantic_change": False,
                "amendment": str(AMENDMENT_FACES.relative_to(BASELINES)),
                "amendment_sha256": sha256(AMENDMENT_FACES),
                "applied_at_utc": datetime.now(timezone.utc).isoformat(),
            }
        )
    write_json(MANIFEST, manifest)
    print("GEMINI_CONNECT2_COMPATIBILITY_APPLIED mediterranean_music_villa_refined")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

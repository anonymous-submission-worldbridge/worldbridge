#!/usr/bin/env python3
"""Materialize a recorded raw Gemini response after a documented validation amendment."""
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
import sys


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RUN = BASELINES / "annotations/gemini_3_1_pro/connect/coastal_kitchen_deck"
RESPONSE = RUN / "logs/generation_03/response.txt"
AMENDMENT = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_bmesh_amendment_20260923.json"
)
sys.path.insert(0, str((BASELINES / "methods")))
from baselines.methods.gemini.adapter import parse_response  # noqa: E402
from baselines.methods.gemini.adapter_connect import check_code  # noqa: E402


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def main() -> int:
    source = parse_response(RESPONSE.read_text(encoding="utf-8"))
    check_code(source)
    generated = RUN / "source/generated.py"
    generated.parent.mkdir(parents=True, exist_ok=True)
    generated.write_text(source.rstrip() + "\n", encoding="utf-8")
    manifest_path = RUN / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        generation_success=True,
        failure_class=None,
        failure_reason=None,
        generated_code_sha256=sha256(generated),
        raw_response_sha256=sha256(RESPONSE),
        selected_generation_attempt=3,
        validation_amendment=str(AMENDMENT.relative_to(BASELINES)),
        validation_amendment_sha256=sha256(AMENDMENT),
        materialized_at_utc=datetime.now(timezone.utc).isoformat(),
    )
    write_json(manifest_path, manifest)
    print("GEMINI_CONNECT_RESPONSE_MATERIALIZED coastal_kitchen_deck attempt=3")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

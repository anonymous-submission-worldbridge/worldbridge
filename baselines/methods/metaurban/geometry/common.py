"""Shared paths, hashing, and atomic output helpers."""

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


import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
PACKAGE = BASELINES / "methods/metaurban/geometry"
PROTOCOL = BASELINES / "methods/metaurban/protocol/geometry"
TABLE2 = BASELINES / "data/table2/urban/metaurban"
TABLE3 = BASELINES / "data/table3_metaurban/urban/metaurban"
SOURCE = BASELINES / "sources/metaurban"
ENV_PYTHON = BASELINES / "envs/metaurban/bin/python"
RECAST_DIR = PACKAGE / "recast"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ensure_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def classify_table2(run_dir: Path) -> tuple[bool, str]:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return False, "missing_table2_manifest"
    manifest = read_json(manifest_path)
    checks = {
        "formal": manifest.get("trial_mode") == "formal",
        "full_assets": manifest.get("asset_mode") == "full",
        "success": manifest.get("success") is True,
        "validation": manifest.get("validation", {}).get("valid") is True,
        "success_marker": (run_dir / "SUCCESS").is_file(),
        "native_input": (run_dir / "input/native_input.json").is_file(),
        "scene_descriptor": (run_dir / "scene/scene.json").is_file(),
    }
    failed = [key for key, value in checks.items() if not value]
    return (not failed, "formal_success" if not failed else "+".join(failed))

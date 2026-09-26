#!/usr/bin/env python3
"""Build a frozen metadata-only index for SceneWeaver's 3D-FUTURE assets."""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_EXTERNAL = _wb_paths["WORLDBRIDGE_EXTERNAL"]


import argparse
import json
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_ROOT = Path(f"{_wb_WORLDBRIDGE_EXTERNAL}/SceneWeaver/data/3D-FUTURE-model")
DEFAULT_OUTPUT = BASELINES / "cache/sceneweaver/3d_future_index.json"


def build(root: Path) -> list[dict]:
    records = []
    metadata_path = root / "model_info.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Cannot read 3D-FUTURE metadata {metadata_path}: {exc}"
        ) from exc
    entries = payload if isinstance(payload, list) else [payload]
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        model_id = str(entry.get("model_id") or "")
        model_dir = root / model_id
        model_path = model_dir / "normalized_model.obj"
        if not model_path.is_file():
            model_path = model_dir / "raw_model.obj"
        if not model_path.is_file():
            continue
        records.append(
            {
                "model_id": model_id,
                "super_category": entry.get("super-category"),
                "category": entry.get("category"),
                "style": entry.get("style"),
                "theme": entry.get("theme"),
                "material": entry.get("material"),
                "path": str(model_path.resolve()),
            }
        )
    records.sort(key=lambda item: (item["model_id"], item["path"]))
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    records = build(args.asset_root.resolve())
    if not records:
        raise RuntimeError(f"No usable 3D-FUTURE assets found below {args.asset_root}")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(records, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(args.output)
    print(f"SCENEWEAVER_ASSET_INDEX records={len(records)} output={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

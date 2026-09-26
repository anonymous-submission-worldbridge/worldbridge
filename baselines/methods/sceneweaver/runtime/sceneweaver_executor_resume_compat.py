#!/usr/bin/env python3
"""Resume-path shim around SceneWeaver's frozen executor compatibility layer."""

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


import importlib.util
import sys
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
FROZEN_COMPAT = (
    BASELINES_ROOT
    / "methods/sceneweaver/runtime/sceneweaver_executor/generate_indoors_compat.py"
)


def load_frozen_compat():
    spec = importlib.util.spec_from_file_location(
        "sceneweaver_frozen_executor_compat", FROZEN_COMPAT
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Cannot load frozen executor compatibility code: {FROZEN_COMPAT}"
        )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def current_output_folder() -> Path:
    try:
        value = sys.argv[sys.argv.index("--output_folder") + 1]
    except (ValueError, IndexError) as exc:
        raise RuntimeError("SceneWeaver resume requires --output_folder") from exc
    return Path(value).expanduser().resolve()


def main() -> None:
    compat = load_frozen_compat()
    frozen_load_record = compat.compact_load_record

    def migrated_load_record(iteration: int):
        restored = frozen_load_record(iteration)
        state, solver = restored[:2]
        output_folder = current_output_folder()
        output_folder.mkdir(parents=True, exist_ok=True)
        previous = getattr(solver, "output_folder", None)
        solver.output_folder = output_folder
        if getattr(solver, "optim", None) is not None:
            solver.optim.output_folder = output_folder
        solver.state = state
        if previous != output_folder:
            print(
                "SCENEWEAVER_RESUME_REBASED " f"from={previous!s} to={output_folder!s}",
                flush=True,
            )
        return restored

    compat.compact_load_record = migrated_load_record
    compat.main()


if __name__ == "__main__":
    main()

"""SpatialGen Table-2 reuse discovery for the Table-3 surface-only track."""

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


import json
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
PILOT_ROOT = BASELINES_ROOT / "work/spatialgen/pilot_generated/table2/indoor/spatialgen"
FORMAL_ROOT = BASELINES_ROOT / "data/table2/indoor/spatialgen"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_specs(path: Path | None = None) -> list[dict[str, Any]]:
    path = path or (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def expected_runs(
    specs: list[dict[str, Any]], seeds: list[int]
) -> list[tuple[str, int]]:
    return [(spec["spec_id"], int(seed)) for spec in specs for seed in seeds]


def locate_artifacts(run_dir: Path) -> dict[str, Path]:
    manifest_path = run_dir / "run_manifest.json"
    spec_path = run_dir / "input/spec.json"
    native_input_path = run_dir / "input/native_input.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest = read_json(manifest_path)
    spec_id = str(manifest["spec_id"])
    compiled_camera_path = run_dir / "input/dataset" / spec_id / "cameras.json"
    gaussian_path = run_dir / str(manifest.get("native_gaussian", ""))
    candidates = list(
        run_dir.glob("scene/native/**/point_cloud/iteration_7000/point_cloud.ply")
    )
    if not gaussian_path.is_file() and len(candidates) == 1:
        gaussian_path = candidates[0]
    camera_candidates = list(
        run_dir.glob("scene/native/**/sparseradegs_out/cameras.json")
    )
    if len(camera_candidates) != 1:
        raise RuntimeError(
            f"Expected one final camera JSON under {run_dir}, got {len(camera_candidates)}"
        )
    paths = {
        "manifest": manifest_path,
        "spec": spec_path,
        "native_input": native_input_path,
        "compiled_cameras": compiled_camera_path,
        "gaussian": gaussian_path,
        "normalized_cameras": camera_candidates[0],
    }
    missing = [name for name, path in paths.items() if not path.is_file()]
    if missing:
        raise RuntimeError(f"Missing SpatialGen artifacts under {run_dir}: {missing}")
    if not manifest.get("generation_success"):
        raise RuntimeError(f"Table-2 generation was not successful: {run_dir}")
    if gaussian_path.stat().st_size <= 1024 * 1024:
        raise RuntimeError(f"Final Gaussian is implausibly small: {gaussian_path}")
    return paths


def source_run(root: Path, spec_id: str, seed: int) -> Path:
    return Path(root) / spec_id / f"seed_{int(seed)}"


def audit(root: Path, specs: list[dict[str, Any]], seeds: list[int]) -> dict[str, Any]:
    rows = []
    counts: dict[str, int] = {}
    for spec_id, seed in expected_runs(specs, seeds):
        run_dir = source_run(root, spec_id, seed)
        try:
            paths = locate_artifacts(run_dir)
            status = "reusable_final_gaussian"
            detail = {
                "gaussian": str(paths["gaussian"]),
                "gaussian_bytes": paths["gaussian"].stat().st_size,
            }
        except Exception as error:  # inventory must retain every planned run
            status = "missing_or_invalid"
            detail = {"error": f"{type(error).__name__}: {error}"}
        counts[status] = counts.get(status, 0) + 1
        rows.append({"spec_id": spec_id, "seed": seed, "status": status, **detail})
    return {
        "method": "spatialgen",
        "domain": "indoor",
        "track": "surface_only",
        "root": str(Path(root)),
        "planned_runs": len(rows),
        "counts": counts,
        "runs": rows,
    }

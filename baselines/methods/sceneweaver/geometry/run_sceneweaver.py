#!/usr/bin/env python3
"""Reuse and evaluate the complete 100-slot SceneWeaver Table-3 matrix."""

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
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
sys.path.insert(0, str(REPO))

from baselines.evaluation.geometry.common import BASELINES
from baselines.evaluation.geometry.common import SPEC_FILE
from baselines.evaluation.geometry.common import TABLE2_ROOT
from baselines.evaluation.geometry.common import TABLE3_ROOT
from baselines.evaluation.geometry.common import atomic_json
from baselines.evaluation.geometry.common import classify_table2_run
from baselines.evaluation.geometry.common import itt_navigation
from baselines.evaluation.geometry.common import itt_structural
from baselines.evaluation.geometry.common import load_specs
from baselines.evaluation.geometry.common import sha256
from baselines.evaluation.geometry.metrics.build_navmesh import (
    evaluate_run,
)  # noqa: E402


BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
EXPORTER = (
    BASELINES / "methods/sceneweaver/geometry/tools/export_sceneweaver_canonical.py"
)
AGENT = BASELINES / "protocol/geometry/agent.yaml"
THRESHOLDS = BASELINES / "protocol/geometry/reference_thresholds.json"
NAV_EVALUATOR = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def source_link(target: Path, link: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    if link.is_symlink() and link.resolve() == target.resolve():
        return
    if link.exists() or link.is_symlink():
        raise RuntimeError(f"Refusing to replace existing raw source link: {link}")
    link.symlink_to(target.resolve(), target_is_directory=True)


def initialize_run(
    spec: dict[str, Any], seed: int, source_root: Path, data_root: Path
) -> dict:
    source_run = source_root / spec["spec_id"] / f"seed_{seed}"
    run_dir = data_root / spec["spec_id"] / f"seed_{seed}"
    run_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    source_native = source_run / "input/native_input.json"
    if source_native.is_file():
        shutil.copy2(source_native, run_dir / "input/native_input.json")
    roi = spec["evaluation_roi"]
    atomic_json(
        run_dir / "input/boundaries.json",
        {
            "type": roi["type"],
            "selection": roi.get("selection"),
            "xy_fraction": roi.get("xy_fraction"),
            "resolution_policy": "resolved by canonical exporter from final native floor geometry",
            "allowed_boundary_crossings": spec["allowed_boundary_crossings"],
        },
    )
    source_link(source_run, run_dir / "scene/raw/table2_run")
    classification = classify_table2_run(source_run)
    old_manifest_path = run_dir / "run_manifest.json"
    old_manifest = (
        json.loads(old_manifest_path.read_text(encoding="utf-8"))
        if old_manifest_path.is_file()
        else {}
    )
    manifest = {
        "method": "sceneweaver",
        "method_label": "SceneWeaver (Indoor; mixed MiniMax/Codex planner)",
        "domain": "indoor",
        "track": "structured_physics_ready",
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "method_seed": int(spec["spec_index"]) * 4 + seed,
        "source_table2_run": str(source_run),
        "source_classification": classification,
        "source_manifest_sha256": (
            sha256(source_run / "run_manifest.json")
            if (source_run / "run_manifest.json").is_file()
            else None
        ),
        "table3_spec_sha256": sha256(run_dir / "input/spec.json"),
        "exporter_sha256": sha256(EXPORTER),
        "agent_sha256": sha256(AGENT),
        "initialized_at_utc": old_manifest.get("initialized_at_utc", utc_now()),
        "last_initialized_at_utc": utc_now(),
        "status": "initialized",
        "attempts": old_manifest.get("attempts", []),
    }
    atomic_json(run_dir / "run_manifest.json", manifest)
    return {
        "spec": spec,
        "seed": seed,
        "run_dir": run_dir,
        "source_run": source_run,
        "manifest": manifest,
    }


def terminal_is_current(item: dict) -> bool:
    """Resume only a terminal whose canonical inputs and evaluator hashes match."""
    run_dir: Path = item["run_dir"]
    geometry_path = run_dir / "scene/canonical/geometry_manifest.json"
    nav_path = run_dir / "metrics/navigability.json"
    if (
        not (run_dir / "EVALUATION_SUCCESS").is_file()
        or not geometry_path.is_file()
        or not nav_path.is_file()
    ):
        return False
    try:
        geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
        navigation = json.loads(nav_path.read_text(encoding="utf-8"))
        provenance = navigation.get("provenance", {})
        thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
        return bool(
            geometry.get("exporter_sha256") == sha256(EXPORTER)
            and provenance.get("evaluator_sha256") == sha256(NAV_EVALUATOR)
            and provenance.get("agent_sha256") == sha256(AGENT)
            and provenance.get("canonical_manifest_sha256") == sha256(geometry_path)
            and provenance.get("spec_sha256") == sha256(run_dir / "input/spec.json")
            and navigation.get("valid_thresholds")
            == {
                "navigable_area_ratio": float(thresholds["navigable_area_ratio"]),
                "connected_area_ratio": float(thresholds["connected_area_ratio"]),
            }
        )
    except (OSError, ValueError, TypeError):
        return False


def record_itt(item: dict, reason: str) -> None:
    run_dir = item["run_dir"]
    atomic_json(
        run_dir / "metrics/structural.json",
        itt_structural(item["spec"]["spec_id"], item["seed"], reason),
    )
    atomic_json(
        run_dir / "metrics/navigability.json",
        itt_navigation(item["spec"]["spec_id"], item["seed"], reason),
    )
    item["manifest"].update(
        {
            "status": "complete_itt_failure",
            "failure_reason": reason,
            "completed_at_utc": utc_now(),
        }
    )
    atomic_json(run_dir / "run_manifest.json", item["manifest"])
    (run_dir / "EVALUATION_FAILURE_ITT").touch()


def export_one(item: dict, timeout_s: int) -> tuple[dict, bool, str]:
    run_dir: Path = item["run_dir"]
    source_run: Path = item["source_run"]
    geometry_manifest = run_dir / "scene/canonical/geometry_manifest.json"
    if (run_dir / "CANONICAL_SUCCESS").is_file() and geometry_manifest.is_file():
        existing = json.loads(geometry_manifest.read_text(encoding="utf-8"))
        if existing.get("exporter_sha256") == sha256(EXPORTER):
            return item, True, "resumed_existing_canonical"
    # Blender may exit zero even when a --python script raises.  Clear only
    # derived Table-3 sentinels before a new attempt so stale markers cannot
    # turn that condition into a false success.
    for marker in (
        run_dir / "CANONICAL_SUCCESS",
        run_dir / "EVALUATION_SUCCESS",
        run_dir / "EVALUATION_FAILURE_ITT",
    ):
        marker.unlink(missing_ok=True)
    command = [
        str(BLENDER),
        "-b",
        str(source_run / "scene/scene.blend"),
        "--python",
        str(EXPORTER),
        "--",
        "--run-dir",
        str(run_dir),
        "--source-run",
        str(source_run),
        "--face-cap",
        "20000",
    ]
    log_path = run_dir / "logs/export_canonical.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    started_utc = utc_now()
    env = os.environ.copy()
    env.update({"TMPDIR": str(BASELINES / "tmp"), "PYTHONUNBUFFERED": "1"})
    try:
        with log_path.open("w", encoding="utf-8", errors="replace") as log:
            log.write("COMMAND_JSON=" + json.dumps(command) + "\n")
            log.flush()
            completed = subprocess.run(
                command,
                cwd=REPO,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=timeout_s,
                text=True,
            )
        ok = (
            completed.returncode == 0
            and (run_dir / "CANONICAL_SUCCESS").is_file()
            and geometry_manifest.is_file()
        )
        if ok:
            exported_manifest = json.loads(
                geometry_manifest.read_text(encoding="utf-8")
            )
            ok = exported_manifest.get("exporter_sha256") == sha256(EXPORTER)
        detail = "ok" if ok else f"blender_exit_{completed.returncode}"
        exit_code = completed.returncode
    except subprocess.TimeoutExpired:
        ok, detail, exit_code = False, "blender_timeout", None
    item["manifest"]["attempts"].append(
        {
            "phase": "canonical_export",
            "command": command,
            "log": str(log_path.relative_to(run_dir)),
            "started_at_utc": started_utc,
            "ended_at_utc": utc_now(),
            "wall_time_s": time.monotonic() - started,
            "exit_code": exit_code,
            "success": ok,
            "detail": detail,
        }
    )
    item["manifest"]["status"] = "canonical_complete" if ok else "canonical_failed"
    atomic_json(run_dir / "run_manifest.json", item["manifest"])
    return item, ok, detail


def export_with_retries(
    item: dict, timeout_s: int, max_retries: int
) -> tuple[dict, bool, str]:
    result = (item, False, "not_started")
    for _ in range(max_retries + 1):
        result = export_one(item, timeout_s)
        if result[1]:
            break
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, default=TABLE2_ROOT)
    parser.add_argument("--data-root", type=Path, default=TABLE3_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--phase", choices=("pilot", "formal"), default="formal")
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--export-timeout-s", type=int, default=1800)
    parser.add_argument("--max-retries-infra", type=int, default=2)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    specs = load_specs(args.spec_file)
    if args.phase == "pilot":
        first = {}
        for spec in specs:
            first.setdefault(spec["category"], spec)
        specs = list(first.values())
        seeds = (0, 1)
    else:
        seeds = (0, 1, 2, 3)
    items = [
        initialize_run(spec, seed, args.source_root, args.data_root)
        for spec in specs
        for seed in seeds
    ]
    reusable = []
    for item in items:
        classification = item["manifest"]["source_classification"]
        if not classification["reusable_raw"]:
            record_itt(item, classification["classification"])
        elif args.resume and terminal_is_current(item):
            item["manifest"]["status"] = "complete"
            item["manifest"]["resumed_current_terminal"] = True
            atomic_json(item["run_dir"] / "run_manifest.json", item["manifest"])
        else:
            reusable.append(item)

    exported: list[dict] = []
    failures = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [
            pool.submit(
                export_with_retries,
                item,
                args.export_timeout_s,
                max(0, args.max_retries_infra),
            )
            for item in reusable
        ]
        for future in as_completed(futures):
            item, ok, detail = future.result()
            print(
                f"EXPORT {item['spec']['spec_id']} seed={item['seed']} ok={ok} detail={detail}",
                flush=True,
            )
            if ok:
                exported.append(item)
            else:
                record_itt(item, f"canonical_export_failed:{detail}")
                failures.append(item)

    thresholds = json.loads(THRESHOLDS.read_text(encoding="utf-8"))
    for index, item in enumerate(exported, start=1):
        run_dir = item["run_dir"]
        payload = None
        last_error = None
        for nav_attempt in range(max(0, args.max_retries_infra) + 1):
            started = time.monotonic()
            started_utc = utc_now()
            try:
                payload = evaluate_run(
                    run_dir,
                    AGENT,
                    float(thresholds["navigable_area_ratio"]),
                    float(thresholds["connected_area_ratio"]),
                )
                item["manifest"]["attempts"].append(
                    {
                        "phase": "navigation_evaluation",
                        "attempt": nav_attempt + 1,
                        "started_at_utc": started_utc,
                        "ended_at_utc": utc_now(),
                        "wall_time_s": time.monotonic() - started,
                        "success": True,
                    }
                )
                break
            except Exception as error:
                last_error = error
                item["manifest"]["attempts"].append(
                    {
                        "phase": "navigation_evaluation",
                        "attempt": nav_attempt + 1,
                        "started_at_utc": started_utc,
                        "ended_at_utc": utc_now(),
                        "wall_time_s": time.monotonic() - started,
                        "success": False,
                        "error": f"{type(error).__name__}:{error}",
                    }
                )
                atomic_json(run_dir / "run_manifest.json", item["manifest"])
        if payload is not None:
            item["manifest"].update(
                {
                    "status": "complete",
                    "completed_at_utc": utc_now(),
                    "navmesh_success": payload["navmesh_success"],
                    "valid_scene": payload["valid_scene"],
                }
            )
            atomic_json(run_dir / "run_manifest.json", item["manifest"])
            print(
                f"NAV {index}/{len(exported)} {item['spec']['spec_id']} seed={item['seed']} "
                f"success={payload['navmesh_success']} valid={payload['valid_scene']}",
                flush=True,
            )
        else:
            assert last_error is not None
            error = last_error
            record_itt(
                item, f"navigation_evaluation_failed:{type(error).__name__}:{error}"
            )
            failures.append(item)
            print(
                f"NAV_ERROR {item['spec']['spec_id']} seed={item['seed']} {type(error).__name__}: {error}",
                flush=True,
            )
    print(
        f"TABLE3_SCENEWEAVER_MATRIX planned={len(items)} reusable_geometry={len(reusable)} "
        f"evaluated={len(exported) - len([x for x in failures if x in exported])} "
        f"itt_or_eval_failures={len(items) - len(exported) + len([x for x in failures if x in exported])}",
        flush=True,
    )
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())

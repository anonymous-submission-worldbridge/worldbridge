#!/usr/bin/env python3
"""Run the frozen Table-3 native-mesh navigation evaluation for GPT-6 Astra.

No model request is made: this runner only consumes frozen successful Table-2
``scene.blend`` artifacts. Missing/failed Table-2 generations receive the
pre-registered ITT worst-case navigation score.
"""

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
import hashlib
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
EXPORTER = BASELINES / "methods/gpt/tools/export_gpt_geometry.py"
EVALUATOR = BASELINES / "methods/gpt/tools/evaluate_gpt_geometry_nav.py"
RULES = BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json"
AGENT = BASELINES / "protocol/geometry/agent.yaml"
PROTOCOL = BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_geometry_protocol.json"
PILOT_INDEXES = {0, 5, 10, 15, 20}
SEEDS = range(4)

EXPECTED_PYTHON = BASELINES / "envs/hyworld2/bin/python"
if (
    EXPECTED_PYTHON.is_file()
    and Path(sys.prefix).resolve() != (BASELINES / "envs/hyworld2").resolve()
):
    os.execv(
        str(EXPECTED_PYTHON),
        [str(EXPECTED_PYTHON), "-B", str(Path(__file__).resolve()), *sys.argv[1:]],
    )

sys.path.insert(0, str(BASELINES / "tools"))
from baselines.methods.gpt.tools.evaluate_gpt_geometry_nav import (
    evaluate_run,
)  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def read_specs(domain: str) -> list[dict]:
    path = BASELINES / f"protocol/generation/{domain}_specs.jsonl"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def validate_frozen() -> None:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    if protocol.get("status") != "frozen":
        raise RuntimeError(
            "Formal execution requires a frozen GPT-6 Astra Table-3 protocol"
        )
    lock_path = BASELINES / "results/gpt6_astra/table3/metrics.lock.json"
    if not lock_path.is_file():
        raise RuntimeError("Formal execution requires metrics.lock.json")
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    mismatches = []
    for relative, expected in lock.get("files", {}).items():
        path = BASELINES / relative
        if not path.is_file() or sha256(path) != expected:
            mismatches.append(relative)
    if mismatches:
        raise RuntimeError(f"Frozen metric implementation mismatch: {mismatches}")


def source_status(source: Path) -> tuple[bool, str, dict | None]:
    manifest_path = source / "run_manifest.json"
    if not manifest_path.is_file():
        return False, "table2_manifest_missing", None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("generation_success"):
        return False, "table2_generation_failed", manifest
    if not manifest.get("build_success"):
        return False, "table2_build_failed", manifest
    if not (source / "scene/scene.blend").is_file():
        return False, "table2_blend_missing", manifest
    if not (source / "SUCCESS").is_file():
        return False, "table2_success_marker_missing", manifest
    return True, "reusable", manifest


def identity(source: Path, run_dir: Path) -> dict:
    files = {
        "source_blend_sha256": source / "scene/scene.blend",
        "source_manifest_sha256": source / "run_manifest.json",
        "spec_sha256": run_dir / "input/spec.json",
        "exporter_sha256": EXPORTER,
        "evaluator_sha256": EVALUATOR,
        "rules_sha256": RULES,
        "agent_sha256": AGENT,
        "protocol_sha256": PROTOCOL,
        "runner_sha256": Path(__file__),
    }
    return {key: sha256(path) for key, path in files.items()}


def completed_and_current(source: Path, run_dir: Path) -> bool:
    metric = run_dir / "metrics/navigability.json"
    manifest = run_dir / "run_manifest.json"
    if (
        not metric.is_file()
        or not manifest.is_file()
        or not (run_dir / "EVALUATION_SUCCESS").is_file()
    ):
        return False
    try:
        record = json.loads(manifest.read_text(encoding="utf-8"))
        return record.get("identity") == identity(source, run_dir)
    except (OSError, ValueError, KeyError):
        return False


def initialize(spec: dict, seed: int, source: Path, run_dir: Path) -> None:
    for relative in (
        "input",
        "logs",
        "metrics",
        "scene/raw",
        "scene/canonical",
        "navigation",
    ):
        (run_dir / relative).mkdir(parents=True, exist_ok=True)
    atomic_json(run_dir / "input/spec.json", spec)
    native = source / "input/native_input.json"
    if native.is_file():
        (run_dir / "input/native_input.json").write_bytes(native.read_bytes())
    pointer = run_dir / "scene/raw/table2_run"
    if not pointer.exists() and not pointer.is_symlink():
        pointer.symlink_to(source, target_is_directory=True)


def itt_metric(spec: dict, seed: int, reason: str) -> dict:
    return {
        "method": "gpt6_astra",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "success": False,
        "failure_policy": "itt_worst_case",
        "failure_reason": reason,
        "navigable_area_ratio": 0.0,
        "connected_area_ratio": 0.0,
        "navmesh_success": False,
        "valid_scene": None,
        "valid_scene_reason_code": "N/A-I",
    }


def structural_na(spec: dict, seed: int) -> dict:
    return {
        "method": "gpt6_astra",
        "domain": spec["domain"],
        "spec_id": spec["spec_id"],
        "logical_seed": seed,
        "status": "not_applicable",
        "reason_code": "N/A-I",
        "reason": "No verifiable independent object instances or native support graph",
        "collision_rate": None,
        "floating_rate": None,
        "oob_rate": None,
        "support_validity": None,
        "valid_scene_rate": None,
    }


def process_one(spec: dict, seed: int, force: bool) -> dict:
    domain, spec_id = spec["domain"], spec["spec_id"]
    source = BASELINES / f"data/table2/{domain}/gpt6_astra/{spec_id}/seed_{seed}"
    # The shared ``data/table3`` tree is read-only on this host. Keep this
    # method's isolated artifacts in its own writable sibling.
    run_dir = BASELINES / f"data/table3_gpt6_astra/{domain}/{spec_id}/seed_{seed}"
    reusable, reason, source_manifest = source_status(source)
    initialize(spec, seed, source, run_dir)
    if reusable and not force and completed_and_current(source, run_dir):
        return {"domain": domain, "spec_id": spec_id, "seed": seed, "status": "resumed"}
    started = now()
    if not reusable:
        atomic_json(run_dir / "metrics/structural.json", structural_na(spec, seed))
        atomic_json(
            run_dir / "metrics/navigability.json", itt_metric(spec, seed, reason)
        )
        atomic_json(
            run_dir / "run_manifest.json",
            {
                "method": "gpt6_astra",
                "domain": domain,
                "spec_id": spec_id,
                "logical_seed": seed,
                "table2_reusable": False,
                "failure_policy": "itt_worst_case",
                "failure_reason": reason,
                "source_run": str(source),
                "started_at_utc": started,
                "ended_at_utc": now(),
                "source_manifest": source_manifest,
            },
        )
        (run_dir / "EVALUATION_SUCCESS").touch()
        return {
            "domain": domain,
            "spec_id": spec_id,
            "seed": seed,
            "status": "itt",
            "reason": reason,
        }

    (run_dir / "GENERATION_SUCCESS").touch()
    run_manifest = {
        "method": "gpt6_astra",
        "domain": domain,
        "spec_id": spec_id,
        "logical_seed": seed,
        "table2_reusable": True,
        "source_run": str(source),
        "started_at_utc": started,
        "identity": identity(source, run_dir),
        "attempts": [],
    }
    atomic_json(run_dir / "run_manifest.json", run_manifest)
    for attempt in (1, 2):
        log_dir = run_dir / f"logs/export_{attempt:02d}"
        log_dir.mkdir(parents=True, exist_ok=True)
        command = [
            str(BLENDER),
            "-b",
            str(source / "scene/scene.blend"),
            "-t",
            "4",
            "--python-exit-code",
            "11",
            "--python",
            str(EXPORTER),
            "--",
            "--run-dir",
            str(run_dir),
            "--source-run",
            str(source),
        ]
        attempt_started = now()
        with (log_dir / "stdout.log").open("wb") as stdout, (
            log_dir / "stderr.log"
        ).open("wb") as stderr:
            completed = subprocess.run(
                command, stdout=stdout, stderr=stderr, timeout=1800, check=False
            )
        run_manifest["attempts"].append(
            {
                "index": attempt,
                "started_at_utc": attempt_started,
                "ended_at_utc": now(),
                "command": command,
                "exit_code": completed.returncode,
            }
        )
        atomic_json(run_dir / "run_manifest.json", run_manifest)
        if completed.returncode == 0 and (run_dir / "CANONICAL_SUCCESS").is_file():
            break
    else:
        run_manifest.update(
            {"ended_at_utc": now(), "failure_reason": "canonical_export_failed"}
        )
        atomic_json(run_dir / "run_manifest.json", run_manifest)
        raise RuntimeError(
            f"Canonical export failed twice: {domain}/{spec_id}/seed_{seed}"
        )

    try:
        metric = evaluate_run(run_dir)
    except Exception as error:
        run_manifest.update(
            {
                "ended_at_utc": now(),
                "failure_reason": f"navigation_evaluation_failed: {error}",
            }
        )
        atomic_json(run_dir / "run_manifest.json", run_manifest)
        raise
    run_manifest.update(
        {
            "ended_at_utc": now(),
            "failure_reason": None,
            "metric_sha256": sha256(run_dir / "metrics/navigability.json"),
        }
    )
    atomic_json(run_dir / "run_manifest.json", run_manifest)
    return {
        "domain": domain,
        "spec_id": spec_id,
        "seed": seed,
        "status": "evaluated",
        "navigable_area_ratio": metric["navigable_area_ratio"],
        "connected_area_ratio": metric["connected_area_ratio"],
        "navmesh_success": metric["navmesh_success"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    parser.add_argument("--domain", choices=("indoor", "urban", "both"), default="both")
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    if args.phase == "formal":
        validate_frozen()
    domains = ("indoor", "urban") if args.domain == "both" else (args.domain,)
    tasks = []
    for domain in domains:
        for spec in read_specs(domain):
            if args.phase == "pilot" and int(spec["spec_index"]) not in PILOT_INDEXES:
                continue
            for seed in range(2) if args.phase == "pilot" else SEEDS:
                tasks.append((spec, seed))
    result_path = BASELINES / f"results/gpt6_astra/table3/matrix_{args.phase}.jsonl"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    with result_path.open("a", encoding="utf-8") as stream:
        with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
            pending = {
                pool.submit(process_one, spec, seed, args.force): (spec, seed)
                for spec, seed in tasks
            }
            for future in as_completed(pending):
                spec, seed = pending[future]
                try:
                    result = future.result()
                except Exception as error:
                    result = {
                        "domain": spec["domain"],
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "status": "error",
                        "error": repr(error),
                    }
                    failures.append(result)
                result["recorded_at_utc"] = now()
                stream.write(json.dumps(result, sort_keys=True) + "\n")
                stream.flush()
                print(json.dumps(result, sort_keys=True), flush=True)
    print(
        json.dumps(
            {"phase": args.phase, "planned": len(tasks), "new_failures": len(failures)},
            sort_keys=True,
        )
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

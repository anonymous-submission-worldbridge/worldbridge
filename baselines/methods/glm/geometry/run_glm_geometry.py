#!/usr/bin/env python3
"""Reuse frozen GLM-5.3 Low Table-2 meshes for the Table-3 nav track.

This program never invokes GLM or any other remote model.  It exports retained
Blender geometry with the already frozen GPT-6 Astra canonicalizer, evaluates
the same Recast protocol, aggregates all planned slots under ITT, and audits
the complete provenance/arithmetic chain.
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
import csv
import hashlib
import json
import math
import os
import random
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "glm_5_3"
DISPLAY_NAME = "GLM-5.3 Low"
MODEL_ID = "glm-5.3"
BLENDER = Path(_wb_expand_paths("${BLENDER_BIN}"))
EXPORTER = BASELINES / "methods/gpt/tools/export_gpt_geometry.py"
EVALUATOR = BASELINES / "methods/gpt/tools/evaluate_gpt_geometry_nav.py"
RULES = BASELINES / "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json"
AGENT = BASELINES / "protocol/geometry/agent.yaml"
PROTOCOL = BASELINES / "methods/glm/protocol/geometry/glm_5_3_geometry_protocol.json"
SOURCE_LOCK = BASELINES / "methods/glm/protocol/generation/glm_5_3.lock.json"
RESULTS = BASELINES / "results/glm_5_3/table3"
DATA = BASELINES / "data/table3_glm_5_3"
METRICS_LOCK = RESULTS / "metrics.lock.json"
PILOT_INDEXES = {0, 5, 10, 15, 20}
METRICS = ("navigable_area_ratio", "connected_area_ratio", "navmesh_success_rate")

LOCAL_PYTHON = Path(_wb_expand_paths("${WORLDBRIDGE_PYTHON}"))
FALLBACK_PYTHON = BASELINES / "envs/hyworld2/bin/python"
EXPECTED_PYTHON = LOCAL_PYTHON if LOCAL_PYTHON.is_file() else FALLBACK_PYTHON
if (
    __name__ == "__main__"
    and EXPECTED_PYTHON.is_file()
    and Path(sys.prefix).resolve() != EXPECTED_PYTHON.parent.parent.resolve()
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


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


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


def source_path(domain: str, spec_id: str, seed: int) -> Path:
    return BASELINES / f"data/table2/{domain}/{METHOD}/{spec_id}/seed_{seed}"


def run_path(domain: str, spec_id: str, seed: int) -> Path:
    return DATA / domain / spec_id / f"seed_{seed}"


def source_status(source: Path) -> tuple[bool, str, dict | None]:
    manifest_path = source / "run_manifest.json"
    if not manifest_path.is_file():
        return False, "table2_manifest_missing", None
    manifest = read_json(manifest_path)
    lock = read_json(SOURCE_LOCK).get("files_sha256", {})
    identity = manifest.get("identity", {})
    identity_ok = (
        manifest.get("method") == METHOD
        and manifest.get("model_requested") == MODEL_ID
        and manifest.get("model_returned") == MODEL_ID
        and identity.get("protocol_sha256")
        == lock.get("methods/glm/protocol/generation/glm_5_3.json")
        and identity.get("adapter_sha256") == lock.get("methods/glm/adapter.py")
    )
    if not identity_ok:
        return False, "table2_identity_mismatch", manifest
    if not manifest.get("generation_success"):
        return False, "table2_generation_failed", manifest
    if not manifest.get("build_success"):
        return False, "table2_build_failed", manifest
    if not (source / "scene/scene.blend").is_file():
        return False, "table2_blend_missing", manifest
    if not (source / "SUCCESS").is_file():
        return False, "table2_success_marker_missing", manifest
    return True, "reusable", manifest


def identity(source: Path, output: Path) -> dict:
    files = {
        "source_blend_sha256": source / "scene/scene.blend",
        "source_manifest_sha256": source / "run_manifest.json",
        "spec_sha256": output / "input/spec.json",
        "shared_exporter_sha256": EXPORTER,
        "shared_evaluator_sha256": EVALUATOR,
        "rules_sha256": RULES,
        "agent_sha256": AGENT,
        "protocol_sha256": PROTOCOL,
        "runner_sha256": Path(__file__),
    }
    return {name: sha256(path) for name, path in files.items()}


def initialize(spec: dict, source: Path, output: Path) -> None:
    for relative in (
        "input",
        "logs",
        "metrics",
        "scene/raw",
        "scene/canonical",
        "navigation",
    ):
        (output / relative).mkdir(parents=True, exist_ok=True)
    atomic_json(output / "input/spec.json", spec)
    native = source / "input/native_input.json"
    if native.is_file():
        (output / "input/native_input.json").write_bytes(native.read_bytes())
    pointer = output / "scene/raw/table2_run"
    if not pointer.exists() and not pointer.is_symlink():
        pointer.symlink_to(source, target_is_directory=True)


def structural_na(spec: dict, seed: int) -> dict:
    return {
        "method": METHOD,
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


def itt_metric(spec: dict, seed: int, reason: str) -> dict:
    return {
        "method": METHOD,
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


def completed_and_current(source: Path, output: Path) -> bool:
    required = (
        output / "metrics/navigability.json",
        output / "metrics/structural.json",
        output / "run_manifest.json",
        output / "EVALUATION_SUCCESS",
    )
    if not all(path.is_file() for path in required):
        return False
    try:
        manifest = read_json(output / "run_manifest.json")
        metric = read_json(output / "metrics/navigability.json")
        expected = identity(source, output)
        observed = manifest.get("identity", {})
        stable_keys = set(expected) - {"protocol_sha256", "runner_sha256"}
        stable = all(observed.get(key) == expected[key] for key in stable_keys)
        if not stable or metric.get("method") != METHOD:
            return False
        if observed != expected:
            manifest["identity"] = expected
            manifest["cache_identity_refresh"] = {
                "at_utc": now(),
                "reason": "metadata-only protocol/runner amendment; all source and metric-defining hashes unchanged",
                "previous_protocol_sha256": observed.get("protocol_sha256"),
                "previous_runner_sha256": observed.get("runner_sha256"),
            }
            atomic_json(output / "run_manifest.json", manifest)
        return True
    except (OSError, ValueError, KeyError):
        return False


def deterministic_canonical_failure(output: Path) -> str | None:
    markers = (
        "Frozen semantic walkable selection produced no upward triangles",
        "No indoor floor node matched the frozen walkable-surface rule",
    )
    stderr_paths = [
        output / f"logs/export_{attempt:02d}/stderr.log" for attempt in (1, 2)
    ]
    if all(
        path.is_file()
        and any(
            marker in path.read_text(encoding="utf-8", errors="replace")
            for marker in markers
        )
        for path in stderr_paths
    ):
        return "canonical_no_walkable_surface"
    return None


def relabel_export_artifacts(output: Path) -> None:
    for relative in (
        "scene/canonical/instances.json",
        "scene/canonical/geometry_manifest.json",
        "metrics/structural.json",
    ):
        path = output / relative
        payload = read_json(path)
        payload["method"] = METHOD
        atomic_json(path, payload)


def process_one(spec: dict, seed: int, force: bool) -> dict:
    domain, spec_id = spec["domain"], spec["spec_id"]
    source = source_path(domain, spec_id, seed)
    output = run_path(domain, spec_id, seed)
    reusable, reason, source_manifest = source_status(source)
    initialize(spec, source, output)
    if reusable and not force and completed_and_current(source, output):
        return {"domain": domain, "spec_id": spec_id, "seed": seed, "status": "resumed"}
    started = now()
    if not reusable:
        atomic_json(output / "metrics/structural.json", structural_na(spec, seed))
        atomic_json(
            output / "metrics/navigability.json", itt_metric(spec, seed, reason)
        )
        atomic_json(
            output / "run_manifest.json",
            {
                "method": METHOD,
                "model_id": MODEL_ID,
                "domain": domain,
                "spec_id": spec_id,
                "logical_seed": seed,
                "table2_reusable": False,
                "model_requests": 0,
                "failure_policy": "itt_worst_case",
                "failure_reason": reason,
                "source_run": str(source),
                "started_at_utc": started,
                "ended_at_utc": now(),
                "source_manifest": source_manifest,
            },
        )
        (output / "EVALUATION_SUCCESS").touch()
        return {
            "domain": domain,
            "spec_id": spec_id,
            "seed": seed,
            "status": "itt",
            "reason": reason,
        }

    (output / "GENERATION_SUCCESS").touch()
    manifest = {
        "method": METHOD,
        "model_id": MODEL_ID,
        "domain": domain,
        "spec_id": spec_id,
        "logical_seed": seed,
        "table2_reusable": True,
        "model_requests": 0,
        "source_run": str(source),
        "started_at_utc": started,
        "identity": identity(source, output),
        "attempts": [],
    }
    atomic_json(output / "run_manifest.json", manifest)
    for attempt in (1, 2):
        log_dir = output / f"logs/export_{attempt:02d}"
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
            str(output),
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
        manifest["attempts"].append(
            {
                "index": attempt,
                "started_at_utc": attempt_started,
                "ended_at_utc": now(),
                "command": command,
                "exit_code": completed.returncode,
            }
        )
        atomic_json(output / "run_manifest.json", manifest)
        if completed.returncode == 0 and (output / "CANONICAL_SUCCESS").is_file():
            break
    else:
        deterministic_reason = deterministic_canonical_failure(output)
        if deterministic_reason:
            atomic_json(output / "metrics/structural.json", structural_na(spec, seed))
            atomic_json(
                output / "metrics/navigability.json",
                itt_metric(spec, seed, deterministic_reason),
            )
            manifest.update(
                ended_at_utc=now(),
                failure_reason=deterministic_reason,
                failure_policy="itt_worst_case",
                table3_evaluable=False,
            )
            atomic_json(output / "run_manifest.json", manifest)
            (output / "EVALUATION_SUCCESS").touch()
            return {
                "domain": domain,
                "spec_id": spec_id,
                "seed": seed,
                "status": "itt",
                "reason": deterministic_reason,
            }
        manifest.update(ended_at_utc=now(), failure_reason="canonical_export_failed")
        atomic_json(output / "run_manifest.json", manifest)
        raise RuntimeError(
            f"Canonical export failed twice: {domain}/{spec_id}/seed_{seed}"
        )

    relabel_export_artifacts(output)
    metric = evaluate_run(output)
    metric["method"] = METHOD
    atomic_json(output / "metrics/navigability.json", metric)
    manifest.update(
        ended_at_utc=now(),
        failure_reason=None,
        metric_sha256=sha256(output / "metrics/navigability.json"),
    )
    atomic_json(output / "run_manifest.json", manifest)
    return {
        "domain": domain,
        "spec_id": spec_id,
        "seed": seed,
        "status": "evaluated",
        "navigable_area_ratio": metric["navigable_area_ratio"],
        "connected_area_ratio": metric["connected_area_ratio"],
        "navmesh_success": metric["navmesh_success"],
    }


def validate_frozen() -> None:
    if read_json(PROTOCOL).get("status") != "frozen":
        raise RuntimeError(
            "Formal execution requires a frozen GLM-5.3 Low Table-3 protocol"
        )
    if not METRICS_LOCK.is_file():
        raise RuntimeError("Formal execution requires metrics.lock.json")
    mismatches = []
    for relative, expected in read_json(METRICS_LOCK).get("files", {}).items():
        path = BASELINES / relative
        if not path.is_file() or sha256(path) != expected:
            mismatches.append(relative)
    if mismatches:
        raise RuntimeError(f"Frozen GLM-5.3 Low Table-3 source changed: {mismatches}")


def run_matrix(phase: str, domain_arg: str, workers: int, force: bool) -> int:
    if phase == "formal":
        validate_frozen()
    domains = ("indoor", "urban") if domain_arg == "both" else (domain_arg,)
    tasks = []
    for domain in domains:
        for spec in read_specs(domain):
            if phase == "pilot" and int(spec["spec_index"]) not in PILOT_INDEXES:
                continue
            seeds = (0, 1) if phase == "pilot" else (0, 1, 2, 3)
            tasks.extend((spec, seed) for seed in seeds)
    RESULTS.mkdir(parents=True, exist_ok=True)
    result_path = RESULTS / f"matrix_{phase}.jsonl"
    failures = []
    with result_path.open("w", encoding="utf-8") as stream:
        with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
            pending = {
                pool.submit(process_one, spec, seed, force): (spec, seed)
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
            {"phase": phase, "planned": len(tasks), "new_failures": len(failures)},
            sort_keys=True,
        )
    )
    return 1 if failures else 0


def freeze() -> int:
    protocol = read_json(PROTOCOL)
    if protocol.get("status") != "frozen":
        raise RuntimeError("Set protocol status to frozen only after pilot review")
    shared_lock = BASELINES / "results/gpt6_astra/table3/metrics.lock.json"
    relative_files = [
        "methods/glm/protocol/geometry/glm_5_3_geometry_protocol.json",
        "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json",
        "protocol/geometry/agent.yaml",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "methods/glm/geometry/run_glm_geometry.py",
        "methods/gpt/tools/gpt_geometry_surface_rules.py",
        "methods/gpt/tools/export_gpt_geometry.py",
        "methods/gpt/tools/evaluate_gpt_geometry_nav.py",
        "methods/glm/tests/test_glm_geometry.py",
        "tools/recast_py311/recast.cpython-311-x86_64-linux-gnu.so",
    ]
    missing = [
        relative for relative in relative_files if not (BASELINES / relative).is_file()
    ]
    if missing:
        raise RuntimeError(f"Cannot freeze; missing files: {missing}")
    frozen_at = now()
    atomic_json(
        RESULTS / "method.lock.json",
        {
            "method": METHOD,
            "display_name": DISPLAY_NAME,
            "model_id": MODEL_ID,
            "provider_model": "glm-coding-plan/glm-5.3",
            "requested_thinking": {"type": "enabled"},
            "requested_reasoning_effort": "low",
            "source_table2_method_lock": "baselines/methods/glm/protocol/generation/glm_5_3.lock.json",
            "source_table2_method_lock_sha256": sha256(SOURCE_LOCK),
            "shared_table3_metrics_lock_sha256": sha256(shared_lock),
            "model_requests_in_table3": 0,
            "reuse_only": True,
            "frozen_at_utc": frozen_at,
        },
    )
    atomic_json(
        METRICS_LOCK,
        {
            "protocol_id": protocol["protocol_id"],
            "files": {
                relative: sha256(BASELINES / relative) for relative in relative_files
            },
            "blender": protocol["blender"],
            "recast_version": "RecastNavigation Python Bindings (custom)",
            "aggregation": protocol["navigation"]["aggregation"],
            "bootstrap_repeats": protocol["navigation"]["bootstrap_repeats"],
            "bootstrap_seed": protocol["navigation"]["bootstrap_seed"],
            "frozen_at_utc": frozen_at,
        },
    )
    print(
        json.dumps(
            {"locked_files": len(relative_files), "frozen_at_utc": frozen_at},
            sort_keys=True,
        )
    )
    return 0


def collect(domain: str) -> list[dict]:
    records = []
    for spec in read_specs(domain):
        for seed in range(4):
            path = run_path(domain, spec["spec_id"], seed) / "metrics/navigability.json"
            if not path.is_file():
                raise RuntimeError(f"Missing planned navigation metric: {path}")
            record = read_json(path)
            expected = (METHOD, domain, spec["spec_id"], seed)
            actual = (
                record.get("method"),
                record.get("domain"),
                record.get("spec_id"),
                record.get("logical_seed"),
            )
            if actual != expected:
                raise RuntimeError(f"Foreign or mis-keyed metric: {path}: {actual}")
            record["navmesh_success_rate"] = 100.0 if record["navmesh_success"] else 0.0
            records.append(record)
    return records


def summarize(domain: str, records: list[dict], protocol: dict) -> dict:
    import numpy as np

    grouped: dict[str, list[dict]] = {}
    for record in records:
        grouped.setdefault(record["spec_id"], []).append(record)
    if len(grouped) != 25 or any(len(rows) != 4 for rows in grouped.values()):
        raise RuntimeError(
            f"{domain}: aggregation requires exactly 25 clusters of four"
        )
    spec_ids = sorted(grouped)
    per_spec = {
        spec_id: {
            metric: float(np.mean([row[metric] for row in grouped[spec_id]]))
            for metric in METRICS
        }
        for spec_id in spec_ids
    }
    values = np.asarray(
        [[per_spec[spec_id][metric] for metric in METRICS] for spec_id in spec_ids],
        dtype=float,
    )
    means = values.mean(axis=0)
    rng = np.random.default_rng(int(protocol["navigation"]["bootstrap_seed"]))
    indexes = rng.integers(
        0,
        len(spec_ids),
        size=(int(protocol["navigation"]["bootstrap_repeats"]), len(spec_ids)),
    )
    bootstrap = values[indexes].mean(axis=1)
    lower, upper = np.percentile(bootstrap, 2.5, axis=0), np.percentile(
        bootstrap, 97.5, axis=0
    )
    summaries = {
        metric: {
            "mean": float(means[index]),
            "ci95": [float(lower[index]), float(upper[index])],
        }
        for index, metric in enumerate(METRICS)
    }
    evaluated = sum(bool(record.get("success")) for record in records)
    return {
        "domain": domain,
        "method": METHOD,
        "model_id": MODEL_ID,
        "track": "native_mesh_instance_incomplete",
        "planned_runs": 100,
        "evaluated_geometry_runs": evaluated,
        "itt_failure_runs": sum(
            record.get("failure_policy") == "itt_worst_case" for record in records
        ),
        "geometry_coverage_percent": float(evaluated),
        "native_instance_coverage_percent": 0.0,
        "aggregation": "mean_over_spec(mean_over_four_seeds)",
        "bootstrap": {
            "unit": "spec",
            "repeats": int(protocol["navigation"]["bootstrap_repeats"]),
            "seed": int(protocol["navigation"]["bootstrap_seed"]),
        },
        "metrics": summaries,
        "structural_metrics": {
            "collision_rate": "N/A-I",
            "floating_rate": "N/A-I",
            "oob_rate": "N/A-I",
            "support_validity": "N/A-I",
            "valid_scene_rate": "N/A-I",
        },
        "per_spec": per_spec,
        "per_run": records,
    }


def aggregate() -> int:
    validate_frozen()
    protocol = read_json(PROTOCOL)
    summaries = [
        summarize(domain, collect(domain), protocol) for domain in ("indoor", "urban")
    ]
    atomic_json(
        RESULTS / "table3_full.json",
        {"protocol_id": protocol["protocol_id"], "domains": summaries},
    )
    columns = [
        "method",
        "domain",
        "track",
        "collision_rate",
        "floating_rate",
        "oob_rate",
        "support_validity",
        "navigable_area_ratio",
        "connected_area_ratio",
        "navmesh_success_rate",
        "valid_scene_rate",
        "planned_runs",
        "evaluated_geometry_runs",
        "geometry_coverage_percent",
        "native_instance_coverage_percent",
    ]
    temporary = RESULTS / "table3.csv.tmp"
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for summary in summaries:
            writer.writerow(
                {
                    "method": METHOD,
                    "domain": summary["domain"],
                    "track": summary["track"],
                    "collision_rate": "N/A-I",
                    "floating_rate": "N/A-I",
                    "oob_rate": "N/A-I",
                    "support_validity": "N/A-I",
                    "navigable_area_ratio": f'{summary["metrics"]["navigable_area_ratio"]["mean"]:.9f}',
                    "connected_area_ratio": f'{summary["metrics"]["connected_area_ratio"]["mean"]:.9f}',
                    "navmesh_success_rate": f'{summary["metrics"]["navmesh_success_rate"]["mean"]:.9f}',
                    "valid_scene_rate": "N/A-I",
                    "planned_runs": 100,
                    "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
                    "geometry_coverage_percent": f'{summary["geometry_coverage_percent"]:.1f}',
                    "native_instance_coverage_percent": "0.0",
                }
            )
    temporary.replace(RESULTS / "table3.csv")
    for summary in summaries:
        print(
            json.dumps(
                {
                    "domain": summary["domain"],
                    "metrics": summary["metrics"],
                    "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
                    "itt_failure_runs": summary["itt_failure_runs"],
                },
                sort_keys=True,
            )
        )
    return 0


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-7, abs_tol=1e-7)


def audit() -> int:
    validate_frozen()
    protocol, source_lock = read_json(PROTOCOL), read_json(SOURCE_LOCK)["files_sha256"]
    errors: list[str] = []
    successful: list[Path] = []
    counts = {
        domain: {"planned": 0, "evaluated": 0, "itt": 0}
        for domain in ("indoor", "urban")
    }
    for domain in ("indoor", "urban"):
        for spec in read_specs(domain):
            for seed in range(4):
                counts[domain]["planned"] += 1
                output = run_path(domain, spec["spec_id"], seed)
                paths = (
                    output / "metrics/navigability.json",
                    output / "metrics/structural.json",
                    output / "run_manifest.json",
                )
                if (
                    not all(path.is_file() for path in paths)
                    or not (output / "EVALUATION_SUCCESS").is_file()
                ):
                    errors.append(f"missing terminal artifacts: {output}")
                    continue
                metric, structural, manifest = (read_json(path) for path in paths)
                key = (METHOD, domain, spec["spec_id"], seed)
                if (
                    metric.get("method"),
                    metric.get("domain"),
                    metric.get("spec_id"),
                    metric.get("logical_seed"),
                ) != key:
                    errors.append(f"metric key mismatch: {output}")
                if (
                    manifest.get("method"),
                    manifest.get("domain"),
                    manifest.get("spec_id"),
                    manifest.get("logical_seed"),
                ) != key:
                    errors.append(f"manifest key mismatch: {output}")
                if (
                    structural.get("method") != METHOD
                    or structural.get("reason_code") != "N/A-I"
                ):
                    errors.append(f"structural identity/N/A-I mismatch: {output}")
                if any(
                    structural.get(name) is not None
                    for name in (
                        "collision_rate",
                        "floating_rate",
                        "oob_rate",
                        "support_validity",
                        "valid_scene_rate",
                    )
                ):
                    errors.append(f"invalid structural N/A-I values: {output}")
                for name in ("navigable_area_ratio", "connected_area_ratio"):
                    value = float(metric.get(name, -1.0))
                    if not math.isfinite(value) or not 0.0 <= value <= 100.0:
                        errors.append(f"out-of-range {name}: {output}")
                if metric.get("failure_policy") == "itt_worst_case":
                    counts[domain]["itt"] += 1
                    if any(
                        float(metric.get(name, -1)) != 0.0
                        for name in ("navigable_area_ratio", "connected_area_ratio")
                    ):
                        errors.append(f"ITT continuous value is not zero: {output}")
                    valid_source_itt = (
                        manifest.get("table2_reusable") is True
                        and manifest.get("table3_evaluable") is False
                        and manifest.get("failure_reason")
                        == "canonical_no_walkable_surface"
                        and metric.get("failure_reason")
                        == "canonical_no_walkable_surface"
                    )
                    unavailable_source_itt = manifest.get("table2_reusable") is False
                    if metric.get("navmesh_success") is not False or not (
                        valid_source_itt or unavailable_source_itt
                    ):
                        errors.append(f"ITT status mismatch: {output}")
                    continue
                counts[domain]["evaluated"] += 1
                successful.append(output)
                geometry_path = output / "scene/canonical/geometry_manifest.json"
                contract = (
                    output / "input/native_input.json",
                    output / "input/boundaries.json",
                    output / "scene/canonical/instances.json",
                    output / "scene/canonical/transform.json",
                    output / "navigation/empty_reference.navmesh",
                    output / "navigation/final.navmesh",
                    output / "navigation/components.json",
                    output / "navigation/debug_topdown.png",
                )
                if (
                    not geometry_path.is_file()
                    or not (output / "CANONICAL_SUCCESS").is_file()
                    or not (output / "GENERATION_SUCCESS").is_file()
                    or not all(path.is_file() for path in contract)
                ):
                    errors.append(f"missing canonical output: {output}")
                    continue
                geometry = read_json(geometry_path)
                instances = read_json(output / "scene/canonical/instances.json")
                if (
                    geometry.get("method") != METHOD
                    or instances.get("method") != METHOD
                ):
                    errors.append(f"canonical method identity mismatch: {output}")
                artifacts = {
                    "empty_reference_ply": "empty_reference.ply",
                    "collision_ply": "collision.ply",
                    "empty_reference_glb": "empty_reference.glb",
                    "collision_glb": "collision.glb",
                }
                for name, filename in artifacts.items():
                    artifact = output / "scene/canonical" / filename
                    if (
                        not artifact.is_file()
                        or sha256(artifact) != geometry[name]["sha256"]
                    ):
                        errors.append(f"canonical hash mismatch {name}: {output}")
                source = source_path(domain, spec["spec_id"], seed)
                source_blend = source / "scene/scene.blend"
                if (
                    Path(geometry["source_blend"]) != source_blend
                    or not source_blend.is_file()
                ):
                    errors.append(f"wrong source blend: {output}")
                elif sha256(source_blend) != geometry.get("source_blend_sha256"):
                    errors.append(f"source blend hash mismatch: {output}")
                source_manifest = read_json(source / "run_manifest.json")
                source_identity = source_manifest.get("identity", {})
                if not (
                    source_manifest.get("method") == METHOD
                    and source_manifest.get("model_requested") == MODEL_ID
                    and source_manifest.get("model_returned") == MODEL_ID
                    and source_identity.get("protocol_sha256")
                    == source_lock.get("methods/glm/protocol/generation/glm_5_3.json")
                    and source_identity.get("adapter_sha256")
                    == source_lock.get("methods/glm/adapter.py")
                ):
                    errors.append(f"source is not frozen GLM-5.3 Low output: {output}")
                if geometry.get("exporter_sha256") != sha256(EXPORTER):
                    errors.append(f"exporter provenance mismatch: {output}")
                provenance = metric.get("provenance", {})
                if provenance.get("evaluator_sha256") != sha256(EVALUATOR):
                    errors.append(f"evaluator provenance mismatch: {output}")
                if provenance.get("canonical_manifest_sha256") != sha256(geometry_path):
                    errors.append(f"metric/canonical provenance mismatch: {output}")
                reference, final = float(metric["reference_navmesh_area_m2"]), float(
                    metric["final_navmesh_area_m2"]
                )
                expected_nav = (
                    100.0 * min(1.0, max(0.0, final / reference))
                    if reference > 0
                    else 0.0
                )
                components = metric["component_areas_m2"]
                expected_connected = (
                    100.0 * float(components[0]) / final
                    if final > 0 and components
                    else 0.0
                )
                expected_success = bool(
                    reference > 0
                    and final >= 0.01 * reference
                    and math.isfinite(final)
                    and metric["final_spawn_projection"].get("projected")
                )
                if not close(expected_nav, metric["navigable_area_ratio"]):
                    errors.append(f"navigable arithmetic mismatch: {output}")
                if not close(expected_connected, metric["connected_area_ratio"]):
                    errors.append(f"connected arithmetic mismatch: {output}")
                if expected_success != metric.get("navmesh_success"):
                    errors.append(f"NavMesh success arithmetic mismatch: {output}")

    expected = {
        domain: {"planned": 100, **protocol["reuse"]["expected_coverage"][domain]}
        for domain in ("indoor", "urban")
    }
    if counts != expected:
        errors.append(f"coverage mismatch: observed={counts}, expected={expected}")
    full_path, csv_path = RESULTS / "table3_full.json", RESULTS / "table3.csv"
    if not full_path.is_file() or not csv_path.is_file():
        errors.append("aggregate output missing")
    else:
        full = read_json(full_path)
        rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
        if full.get("protocol_id") != protocol["protocol_id"] or len(rows) != 2:
            errors.append("aggregate identity/row-count mismatch")
        else:
            by_domain = {item["domain"]: item for item in full["domains"]}
            for row in rows:
                if row.get("method") != METHOD:
                    errors.append(f"aggregate method mismatch: {row}")
                    continue
                for metric_name in METRICS:
                    if not close(
                        float(row[metric_name]),
                        by_domain[row["domain"]]["metrics"][metric_name]["mean"],
                    ):
                        errors.append(
                            f"CSV/full JSON mismatch: {row['domain']} {metric_name}"
                        )
    rng = random.Random(int(protocol["navigation"]["bootstrap_seed"]))
    spot = sorted(rng.sample(successful, min(10, len(successful))), key=str)
    spotchecks = []
    for output in spot:
        geometry_path = output / "scene/canonical/geometry_manifest.json"
        geometry, metric = read_json(geometry_path), read_json(
            output / "metrics/navigability.json"
        )
        passed = (
            sha256(Path(geometry["source_blend"])) == geometry["source_blend_sha256"]
        )
        passed = (
            passed
            and sha256(geometry_path)
            == metric["provenance"]["canonical_manifest_sha256"]
        )
        spotchecks.append({"run": str(output.relative_to(BASELINES)), "passed": passed})
        if not passed:
            errors.append(f"spot-chain mismatch: {output}")
    report = {
        "passed": not errors,
        "method": METHOD,
        "model_id": MODEL_ID,
        "model_requests_in_table3": 0,
        "counts": counts,
        "terminal_runs": sum(values["planned"] for values in counts.values()),
        "spotcheck_seed": int(protocol["navigation"]["bootstrap_seed"]),
        "spotcheck_count": len(spotchecks),
        "spotchecks": spotchecks,
        "errors": errors,
    }
    atomic_json(RESULTS / "audit.json", report)
    print(
        json.dumps(
            {"passed": report["passed"], "counts": counts, "errors": len(errors)},
            sort_keys=True,
        )
    )
    for error in errors[:50]:
        print(error)
    return 1 if errors else 0


def seal() -> int:
    required = (
        "method.lock.json",
        "metrics.lock.json",
        "table3.csv",
        "table3_full.json",
        "audit.json",
        "matrix_formal.jsonl",
    )
    missing = [name for name in required if not (RESULTS / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing final GLM-5.3 Low Table-3 results: {missing}")
    audit_report = read_json(RESULTS / "audit.json")
    protocol = read_json(PROTOCOL)
    expected = {
        domain: {"planned": 100, **protocol["reuse"]["expected_coverage"][domain]}
        for domain in ("indoor", "urban")
    }
    if audit_report.get("passed") is not True or audit_report.get("counts") != expected:
        raise RuntimeError("Refusing to seal a failing or incomplete audit")
    matrix_rows = [
        json.loads(line)
        for line in (RESULTS / "matrix_formal.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line
    ]
    matrix_counts = Counter(row.get("status") for row in matrix_rows)
    if len(matrix_rows) != 200 or matrix_counts.get("error", 0):
        raise RuntimeError(f"Formal matrix record mismatch: {matrix_counts}")
    domains = {}
    for summary in read_json(RESULTS / "table3_full.json")["domains"]:
        metrics = summary["metrics"]
        nav = float(metrics["navigable_area_ratio"]["mean"])
        connected = float(metrics["connected_area_ratio"]["mean"])
        success = float(metrics["navmesh_success_rate"]["mean"])
        domains[summary["domain"]] = {
            "planned_runs": 100,
            "evaluated_geometry_runs": summary["evaluated_geometry_runs"],
            "itt_runs": summary["itt_failure_runs"],
            "navigable_area_ratio": nav,
            "connected_area_ratio": connected,
            "navmesh_success_rate": success,
            "display_row": [
                "N/A-I",
                "N/A-I",
                "N/A-I",
                "N/A-I",
                f"{nav:.1f}",
                f"{connected:.1f}",
                f"{success:.1f}",
                "N/A-I",
            ],
        }
    payload = {
        "status": "both_domains_table3_verified_and_ready_to_fill",
        "method": METHOD,
        "display_name": DISPLAY_NAME,
        "model_id": MODEL_ID,
        "provider_model": "glm-coding-plan/glm-5.3",
        "model_requests_in_table3": 0,
        "sealed_at_utc": now(),
        "formal_matrix": {
            "planned_runs": 200,
            "evaluated_geometry_runs": sum(
                item["evaluated_geometry_runs"] for item in domains.values()
            ),
            "itt_runs": sum(item["itt_runs"] for item in domains.values()),
            "new_runner_failures": 0,
            "matrix_status_counts": dict(matrix_counts),
        },
        "domains": domains,
        "files_sha256": {
            "methods/glm/protocol/geometry/glm_5_3_geometry_protocol.json": sha256(
                PROTOCOL
            ),
            **{
                f"results/glm_5_3/table3/{name}": sha256(RESULTS / name)
                for name in required
            },
        },
    }
    atomic_json(RESULTS / "result.lock.json", payload)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    matrix = subparsers.add_parser("run")
    matrix.add_argument("--phase", choices=("pilot", "formal"), required=True)
    matrix.add_argument("--domain", choices=("indoor", "urban", "both"), default="both")
    matrix.add_argument("--workers", type=int, default=8)
    matrix.add_argument("--force", action="store_true")
    for command in ("freeze", "aggregate", "audit", "seal"):
        subparsers.add_parser(command)
    args = parser.parse_args()
    if args.command == "run":
        return run_matrix(args.phase, args.domain, args.workers, args.force)
    return {"freeze": freeze, "aggregate": aggregate, "audit": audit, "seal": seal}[
        args.command
    ]()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Rebuild only lost Extra-High slots that originally had final geometry.

The original Table-2 xhigh raw tree was moved into an ephemeral /tmp mount and
was subsequently removed.  The frozen formal audit still records exactly which
slots had a built scene.  This recovery reissues only those 183 frozen logical
slots, preserves the 17 original unbuilt slots as ITT, and stops after building
scene.blend (Table 2 rendering is not repeated).
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


import argparse
import fcntl
import hashlib
import json
import queue
import threading
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
RECOVERY_ROOT = Path(
    "/data2/outputs/worldbridge_table3_gpt6_astra_xhigh/source_recovery"
)
AUDIT = BASELINES / "results/gpt6_astra_xhigh/formal_audit.json"
MIGRATION = BASELINES / "results/gpt6_astra_xhigh/formal_storage_migration.json"
AMENDMENT = (
    BASELINES
    / "methods/gpt/protocol/geometry/gpt6_astra_xhigh_geometry_recovery_20260914.json"
)
REPORT = BASELINES / "results/gpt6_astra_xhigh_table3/source_recovery.json"
GUARD = BASELINES / "results/gpt6_astra_xhigh_table3/source_recovery.lock"
SANDBOX_RUN = BASELINES / "tmp/gpt6_astra_xhigh_table3_recovery_mount"

import sys

sys.path.insert(0, str(BASELINES))
sys.path.insert(0, str((BASELINES / "methods")))
import baselines.methods.gpt.run_xhigh_matrix as matrix  # noqa: E402
from baselines.methods.gpt.adapter_xhigh import generate  # noqa: E402

FROZEN_RUN_PROCESS = matrix.run_process


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


def specs() -> dict[tuple[str, str], dict]:
    result = {}
    for domain in ("indoor", "urban"):
        path = BASELINES / f"protocol/generation/{domain}_specs.jsonl"
        for line in path.read_text(encoding="utf-8").splitlines():
            if line:
                spec = json.loads(line)
                result[(domain, spec["spec_id"])] = spec
    return result


def frozen_slots() -> tuple[list[tuple[dict, int]], list[dict]]:
    audit = json.loads(AUDIT.read_text(encoding="utf-8"))
    if (
        audit.get("method") != "gpt6_astra_xhigh"
        or audit.get("reasoning_effort") != "xhigh"
    ):
        raise RuntimeError("Unexpected Extra High Table-2 audit identity")
    if audit.get("expected") != 200 or len(audit.get("records", [])) != 200:
        raise RuntimeError("Extra High Table-2 audit is not a complete 200-slot matrix")
    by_key = specs()
    eligible, frozen_itt = [], []
    for record in audit["records"]:
        key = (record["domain"], record["spec_id"])
        if record.get("scene_built") is True:
            eligible.append((by_key[key], int(record["seed"])))
        else:
            frozen_itt.append(record)
    if len(eligible) != 183 or len(frozen_itt) != 17:
        raise RuntimeError(
            f"Unexpected source recovery split: {len(eligible)} built, {len(frozen_itt)} ITT"
        )
    return eligible, frozen_itt


def validate_inputs() -> None:
    matrix.verify_formal_lock()
    amendment = json.loads(AMENDMENT.read_text(encoding="utf-8"))
    migration = json.loads(MIGRATION.read_text(encoding="utf-8"))
    policy = amendment["recovery_policy"]
    if (
        amendment.get("method") != "gpt6_astra_xhigh"
        or policy.get("model") != "gpt-6-astra"
        or policy.get("reasoning_effort") != "xhigh"
        or Path(policy.get("persistent_root", "")) != RECOVERY_ROOT
        or migration.get("tmp_data_root") != amendment["evidence"]["missing_tmp_root"]
    ):
        raise RuntimeError("Extra High recovery amendment identity mismatch")
    if Path(amendment["evidence"]["missing_tmp_root"]).exists():
        raise RuntimeError(
            "The original migrated source unexpectedly exists; use it instead of recovery"
        )


def output_confined(path: Path) -> Path:
    """Confine this exceptional recovery to its user-selected /data2 tree."""
    resolved = Path(path).resolve()
    allowed = RECOVERY_ROOT.resolve()
    if resolved != allowed and not resolved.is_relative_to(allowed):
        raise ValueError("Extra High recovery output escaped the /data2 recovery root")
    return resolved


def recovery_run_process(
    cmd, work, stdout_path, stderr_path, timeout, env=None, stdin=None
):
    """Map a /data2 run below baselines inside the frozen Blender sandbox."""
    if cmd and cmd[0] == "bwrap":
        run = str(Path(work).resolve())
        if not Path(run).is_relative_to(RECOVERY_ROOT.resolve()):
            raise RuntimeError("Unexpected Blender recovery path outside /data2")
        binding = next(
            (
                index
                for index in range(len(cmd) - 2)
                if cmd[index : index + 3] == ["--bind", run, run]
            ),
            None,
        )
        if binding is None:
            raise RuntimeError("Frozen Blender command lacks its run bind")
        del cmd[binding : binding + 3]
        sandbox = str(SANDBOX_RUN)
        for index, argument in enumerate(cmd):
            if argument == run or argument.startswith(run + "/"):
                cmd[index] = sandbox + argument[len(run) :]
        cmd[binding:binding] = ["--bind", run, sandbox]
        if env is None:
            raise RuntimeError("Frozen Blender command lacks its environment")
        env["TMPDIR"] = str(SANDBOX_RUN / "tmp")
    return FROZEN_RUN_PROCESS(
        cmd,
        work,
        stdout_path,
        stderr_path,
        timeout,
        env=env,
        stdin=stdin,
    )


def run_dir(spec: dict, seed: int) -> Path:
    return (
        RECOVERY_ROOT
        / spec["domain"]
        / matrix.METHOD
        / spec["spec_id"]
        / f"seed_{seed}"
    )


def record_provenance(spec: dict, seed: int, original: dict) -> None:
    run = run_dir(spec, seed)
    atomic_json(
        run / "table3_source_recovery.json",
        {
            "method": matrix.METHOD,
            "model": "gpt-6-astra",
            "reasoning_effort": "xhigh",
            "domain": spec["domain"],
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "original_table2_record": original,
            "original_table2_audit": str(AUDIT.relative_to(BASELINES.parent)),
            "original_table2_audit_sha256": sha256(AUDIT),
            "recovery_amendment": str(AMENDMENT.relative_to(BASELINES.parent)),
            "recovery_amendment_sha256": sha256(AMENDMENT),
            "exact_byte_recovery": False,
            "reason": "Original Table-2 source was lost from the recorded ephemeral /tmp root",
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--generators", type=int, default=16)
    parser.add_argument("--builders", type=int, default=16)
    args = parser.parse_args()
    if not 1 <= args.generators <= 16 or not 1 <= args.builders <= 16:
        raise ValueError("Recovery concurrency must be in 1..16")
    validate_inputs()
    generate.__globals__["confined"] = output_confined
    matrix.run_process = recovery_run_process
    tasks, frozen_itt = frozen_slots()
    original = {
        (row["domain"], row["spec_id"], int(row["seed"])): row
        for row in json.loads(AUDIT.read_text(encoding="utf-8"))["records"]
    }
    RECOVERY_ROOT.mkdir(parents=True, exist_ok=True)
    SANDBOX_RUN.mkdir(parents=True, exist_ok=True)
    if SANDBOX_RUN.is_symlink() or any(SANDBOX_RUN.iterdir()):
        raise RuntimeError(
            "Recovery Blender mount point must be an empty real directory"
        )
    GUARD.parent.mkdir(parents=True, exist_ok=True)
    pending: queue.Queue = queue.Queue()
    ready: queue.Queue = queue.Queue(maxsize=64)
    for task in tasks:
        pending.put(task)
    errors: list[str] = []
    terminal: list[dict] = []
    terminal_lock = threading.Lock()
    generation_done = threading.Event()

    def append_result(spec: dict, seed: int, manifest: dict, stage: str) -> None:
        with terminal_lock:
            terminal.append(
                {
                    "domain": spec["domain"],
                    "spec_id": spec["spec_id"],
                    "seed": seed,
                    "stage": stage,
                    "generation_success": bool(manifest.get("generation_success")),
                    "build_success": bool(manifest.get("build_success")),
                    "failure_class": manifest.get("failure_class"),
                    "failure_reason": manifest.get("failure_reason"),
                }
            )

    def producer() -> None:
        try:
            while True:
                try:
                    spec, seed = pending.get_nowait()
                except queue.Empty:
                    return
                run = run_dir(spec, seed)
                record_provenance(
                    spec, seed, original[(spec["domain"], spec["spec_id"], seed)]
                )
                manifest = generate(spec, seed, RECOVERY_ROOT)
                if not manifest.get("generation_success") and manifest.get(
                    "failure_class"
                ) in {"infrastructure", "access_blocked"}:
                    raise RuntimeError(f"unresolved generation infrastructure: {run}")
                if manifest.get("generation_success"):
                    ready.put((spec, seed))
                else:
                    append_result(spec, seed, manifest, "generation")
        except Exception as error:
            errors.append(repr(error))

    def consumer() -> None:
        try:
            while True:
                try:
                    spec, seed = ready.get(timeout=1)
                except queue.Empty:
                    if generation_done.is_set():
                        return
                    continue
                run = run_dir(spec, seed)
                manifest = matrix.render_run(run, None, build_only=True)
                if manifest.get("failure_class") in {
                    "infrastructure",
                    "access_blocked",
                }:
                    raise RuntimeError(f"unresolved build infrastructure: {run}")
                append_result(spec, seed, manifest, "build")
        except Exception as error:
            errors.append(repr(error))

    with GUARD.open("a") as guard:
        try:
            fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError(
                "An Extra High source recovery is already active"
            ) from error
        producers = [
            threading.Thread(target=producer, name=f"xhigh-recover-generate-{i}")
            for i in range(args.generators)
        ]
        consumers = [
            threading.Thread(target=consumer, name=f"xhigh-recover-build-{i}")
            for i in range(args.builders)
        ]
        for thread in consumers + producers:
            thread.start()
        for thread in producers:
            thread.join()
        generation_done.set()
        for thread in consumers:
            thread.join()

    if len(terminal) != len(tasks):
        errors.append(f"terminal accounting mismatch: {len(terminal)}/{len(tasks)}")
    terminal.sort(key=lambda row: (row["domain"], row["spec_id"], row["seed"]))
    report = {
        "method": matrix.METHOD,
        "reasoning_effort": "xhigh",
        "eligible_recovery_slots": len(tasks),
        "frozen_original_itt_slots": len(frozen_itt),
        "generation_success": sum(row["generation_success"] for row in terminal),
        "build_success": sum(row["build_success"] for row in terminal),
        "terminal_recovery_slots": len(terminal),
        "errors": errors,
        "recovery_root": str(RECOVERY_ROOT),
        "formal_audit_sha256": sha256(AUDIT),
        "amendment_sha256": sha256(AMENDMENT),
        "records": terminal,
    }
    atomic_json(REPORT, report)
    print(
        json.dumps(
            {key: value for key, value in report.items() if key != "records"},
            indent=2,
            sort_keys=True,
        )
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

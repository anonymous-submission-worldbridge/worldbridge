#!/usr/bin/env python3
"""Archive two response-free attempts left incomplete by a lost controller."""
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
import os
from pathlib import Path
import subprocess
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
import baselines.methods.gpt.run_xhigh_matrix as matrix

RECORD = (
    ROOT
    / "methods/gpt/protocol/generation/gpt6_astra_xhigh_controller_recovery_20260913.json"
)
DATA_ROOT = ROOT / "data/table2"
STAMP = "20260913T164000Z"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".recovery-tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    os.replace(temporary, path)


def main() -> int:
    matrix.verify_formal_lock()
    record = json.loads(RECORD.read_text())
    processes = subprocess.check_output(["ps", "-eo", "cmd="], text=True)
    if (
        "codex-gpt6-astra-xhigh-frozen exec" in processes
        or "methods/gpt/run_xhigh_matrix.py" in processes
    ):
        raise RuntimeError(
            "Refusing recovery while an Extra High generation process is active"
        )
    recovered = []
    for target in record["targets"]:
        run = (
            DATA_ROOT
            / target["domain"]
            / record["method"]
            / target["spec_id"]
            / f"seed_{target['seed']}"
        )
        manifest_path = run / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text())
        attempts = manifest.get("attempts", [])
        if not attempts or attempts[-1].get("index") != target["attempt_index"]:
            raise RuntimeError(f"Unexpected last attempt for {run}")
        attempt = attempts[-1]
        if manifest.get("generation_success") or attempt.get("ended_at_utc"):
            raise RuntimeError(
                f"Attempt is no longer eligible for interruption recovery: {run}"
            )
        source = run / f"logs/generation_{target['attempt_index']:02d}"
        events_path = source / "events.jsonl"
        response_path = source / "response.json"
        if response_path.exists() or not events_path.exists():
            raise RuntimeError(f"Response/evidence eligibility mismatch for {run}")
        events = [
            json.loads(line) for line in events_path.read_text().splitlines() if line
        ]
        thread_ids = [
            event.get("thread_id")
            for event in events
            if event.get("type") == "thread.started"
        ]
        if thread_ids != [target["thread_id"]]:
            raise RuntimeError(f"Thread identity mismatch for {run}")
        if any(event.get("type") == "turn.completed" for event in events):
            raise RuntimeError(
                f"Completed turn cannot be recovered as a controller interruption: {run}"
            )
        if any(
            event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
            for event in events
        ):
            raise RuntimeError(
                f"Agent response cannot be recovered as a controller interruption: {run}"
            )
        archive = (
            run
            / "logs"
            / f"generation_{target['attempt_index']:02d}_interrupted_controller_{STAMP}"
        )
        if archive.exists():
            raise RuntimeError(f"Recovery archive already exists: {archive}")
        evidence = {
            "recovered_at_utc": matrix.utc(),
            "record": str(RECORD.relative_to(ROOT)),
            "record_sha256": digest(RECORD),
            "attempt_index": target["attempt_index"],
            "thread_id": target["thread_id"],
            "original_attempt_record": attempt,
            "events_sha256": digest(events_path),
            "stderr_sha256": digest(source / "stderr.log"),
            "event_types": [event.get("type") for event in events],
            "model_response_present": False,
            "completed_attempt_removed": False,
            "archive": str(archive.relative_to(run)),
        }
        source.rename(archive)
        attempts.pop()
        manifest.setdefault("controller_interruptions", []).append(evidence)
        manifest["failure_class"] = None
        manifest["failure_reason"] = None
        write_json_atomic(manifest_path, manifest)
        recovered.append(
            {
                "run": str(run.relative_to(ROOT)),
                "archived_attempt": str(archive.relative_to(ROOT)),
                "events_sha256": evidence["events_sha256"],
                "remaining_completed_attempts": len(attempts),
            }
        )
    output = ROOT / "results/gpt6_astra_xhigh/controller_interrupt_recovery.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic(
        output,
        {
            "finished_at_utc": matrix.utc(),
            "method": record["method"],
            "record_sha256": digest(RECORD),
            "recovered": recovered,
        },
    )
    print(json.dumps(recovered, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

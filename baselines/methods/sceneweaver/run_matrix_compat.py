#!/usr/bin/env python3
"""Resume the SceneWeaver matrix using the local compatibility adapter."""

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
import json
import re
import threading
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
ORIGINAL_RUNNER = BASELINES_ROOT / "methods/sceneweaver/run.py"
COMPAT_ADAPTER = BASELINES_ROOT / "methods/sceneweaver/adapter_compat.py"
RATE_LIMIT_RESET_RE = re.compile(r"X-RateLimit-Reset[^0-9]+([0-9]{10,13})")


def rate_limit_reset_epoch_ms(text: str) -> int | None:
    """Extract a provider reset timestamp only from a terminal 429 response."""
    if "RateLimitError" not in text or not (
        "Daily limit reached" in text or "High demand" in text
    ):
        return None
    matches = [int(value) for value in RATE_LIMIT_RESET_RE.findall(text)]
    if not matches:
        return None
    reset = max(matches)
    return reset if reset >= 10**12 else reset * 1000


def codex_limit_reached(text: str) -> bool:
    return "SCENEWEAVER_CODEX_LIMIT" in text


def latest_generation_log(run_dir: Path) -> Path | None:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.is_file():
        return None
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    attempts = [
        attempt
        for attempt in manifest.get("attempts", [])
        if attempt.get("phase") == "generate"
    ]
    if not attempts:
        return None
    latest = attempts[-1]
    if latest.get("success") is not False or not latest.get("traceback_in_logs"):
        return None
    relative = latest.get("log")
    return run_dir / relative if isinstance(relative, str) and relative else None


def install_rate_limit_gate(runner) -> None:
    """Stop all queues from taking new work after a provider quota response."""
    original_run_queue = runner.run_queue
    pause_event = threading.Event()
    state_lock = threading.Lock()
    state = {"reset_epoch_ms": 0}

    def quota_aware_run_queue(args, gpu, tasks, journal_lock):
        failures = []
        for task_index, (spec_id, seed) in enumerate(tasks):
            run_dir = (
                Path(args.data_root) / "indoor/sceneweaver" / spec_id / f"seed_{seed}"
            )
            terminal_markers = [
                marker
                for marker in (
                    "SUCCESS",
                    "PLANNER_BUDGET_EXHAUSTED",
                    "RENDER_VALIDATION_FAILED",
                )
                if (run_dir / marker).is_file()
            ]
            if terminal_markers:
                print(
                    "SCENEWEAVER_RETAIN_TERMINAL_SKIP "
                    f"spec={spec_id} seed={seed} gpu={gpu} "
                    f"marker={terminal_markers[0]}",
                    flush=True,
                )
                continue
            if pause_event.is_set():
                print(
                    f"SCENEWEAVER_QUEUE_PAUSE gpu={gpu} task_index={task_index} "
                    f"reset_epoch_ms={state['reset_epoch_ms']}",
                    flush=True,
                )
                break
            current = original_run_queue(args, gpu, [(spec_id, seed)], journal_lock)
            failures.extend(current)
            if not current:
                continue
            log_path = latest_generation_log(run_dir)
            if log_path is None or not log_path.is_file():
                continue
            log_text = log_path.read_text(encoding="utf-8", errors="replace")
            reset = rate_limit_reset_epoch_ms(log_text)
            codex_limited = codex_limit_reached(log_text)
            if reset is None and not codex_limited:
                continue
            with state_lock:
                if reset is not None:
                    state["reset_epoch_ms"] = max(state["reset_epoch_ms"], reset)
                pause_event.set()
                print(
                    "SCENEWEAVER_PROVIDER_LIMIT_PAUSE "
                    f"spec={spec_id} seed={seed} gpu={gpu} "
                    f"provider={'codex' if codex_limited else 'openrouter'} "
                    f"reset_epoch_ms={state['reset_epoch_ms']}",
                    flush=True,
                )
        return failures

    runner.run_queue = quota_aware_run_queue


def main() -> int:
    spec = importlib.util.spec_from_file_location(
        "sceneweaver_frozen_runner", ORIGINAL_RUNNER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load SceneWeaver runner from {ORIGINAL_RUNNER}")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    runner.ADAPTER = COMPAT_ADAPTER
    install_rate_limit_gate(runner)
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())

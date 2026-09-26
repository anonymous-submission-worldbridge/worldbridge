#!/usr/bin/env python3
"""Run SynCity automated metrics and packages after the formal matrix ends."""

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
import concurrent.futures
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PYTHON = BASELINES_ROOT / "envs/syncity-3k/bin/python"
METRICS = BASELINES_ROOT / "methods/syncity/evaluate.py"
AUDIT = BASELINES_ROOT / "methods/syncity/tools/audit_syncity_matrix.py"
REVIEW_SHEETS = BASELINES_ROOT / "tools/make_rating_review_sheets.py"
FORMAL_REPORT = BASELINES_ROOT / "results/syncity3k/matrix_formal.json"
STATE = BASELINES_ROOT / "results/syncity3k/postprocess_state.json"
TERMINAL = {
    "success",
    "skipped_success",
    "quality_failure",
    "skipped_quality_failure",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_state(**payload: object) -> None:
    STATE.parent.mkdir(parents=True, exist_ok=True)
    temporary = STATE.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps({"updated_at_utc": utc_now(), **payload}, indent=2, sort_keys=True)
        + "\n"
    )
    temporary.replace(STATE)


def screen_is_live(name: str) -> bool:
    completed = subprocess.run(
        ["screen", "-ls"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return f".{name}" in completed.stdout


def gpu_state(gpu: int) -> tuple[int, int] | None:
    completed = subprocess.run(
        [
            "nvidia-smi",
            f"--id={gpu}",
            "--query-gpu=memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if completed.returncode != 0:
        return None
    free, utilization = completed.stdout.strip().split(",")
    return int(free.strip()), int(utilization.strip())


def wait_for_available_gpus(candidates: list[int], minimum_free_mib: int) -> list[int]:
    while True:
        available = []
        states = {}
        for gpu in candidates:
            state = gpu_state(gpu)
            states[gpu] = state
            if state is not None and state[0] >= minimum_free_mib and state[1] <= 10:
                available.append(gpu)
        # Start useful work as soon as one card is free, while still using all
        # currently free cards when both domains remain.  Requiring two cards
        # would unnecessarily strand post-processing on a shared server.
        if available:
            return available
        write_state(
            state="waiting_for_metric_gpus",
            requested_gpu_count=1,
            minimum_free_mib=minimum_free_mib,
            gpu_states={str(key): value for key, value in states.items()},
        )
        time.sleep(30)


def run(command: list[str]) -> int:
    print(f"SYNCITY3K_POSTPROCESS_RUN {' '.join(command)}", flush=True)
    return subprocess.run(command, cwd=BASELINES_ROOT.parent, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--formal-session", default="syncity3k-formal-supervisor")
    parser.add_argument("--gpus", nargs="+", type=int, default=[0, 1, 2, 3, 5, 6])
    parser.add_argument("--minimum-free-mib", type=int, default=20000)
    parser.add_argument("--max-metric-passes", type=int, default=20)
    parser.add_argument("--max-package-passes", type=int, default=5)
    args = parser.parse_args()
    write_state(state="waiting_for_formal", formal_session=args.formal_session)
    while screen_is_live(args.formal_session):
        time.sleep(30)

    if not FORMAL_REPORT.is_file():
        write_state(state="formal_failed", detail="matrix_formal.json is missing")
        return 2
    report = json.loads(FORMAL_REPORT.read_text(encoding="utf-8"))
    tasks = report.get("tasks", [])
    failures = [row for row in tasks if row.get("status") not in TERMINAL]
    if report.get("phase") != "formal" or len(tasks) != 200 or failures:
        write_state(
            state="formal_failed",
            task_count=len(tasks),
            infrastructure_failures=len(failures),
        )
        return 2
    if run([str(PYTHON), str(AUDIT)]) != 0:
        write_state(state="audit_failed")
        return 2

    if args.max_metric_passes < 1 or args.max_package_passes < 1:
        raise ValueError("postprocess pass counts must be positive")
    pending_domains = ["indoor", "urban"]
    for pass_number in range(1, args.max_metric_passes + 1):
        selected = wait_for_available_gpus(args.gpus, args.minimum_free_mib)
        domains_this_pass = pending_domains[: len(selected)]
        write_state(
            state="automated_metrics_running",
            gpus=selected,
            domains=domains_this_pass,
            pass_number=pass_number,
        )
        commands = [
            [
                str(PYTHON),
                str(METRICS),
                "--phase",
                "automated",
                "--domain",
                domain,
                "--gpu",
                str(gpu),
            ]
            for domain, gpu in zip(domains_this_pass, selected)
        ]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(commands)
        ) as executor:
            codes = list(executor.map(run, commands))
        failed_domains = [
            domain for domain, code in zip(domains_this_pass, codes) if code != 0
        ]
        pending_domains = pending_domains[len(domains_this_pass) :] + failed_domains
        if not pending_domains:
            break
        print(
            f"SYNCITY3K_METRICS_RETRY pass={pass_number} " f"domains={pending_domains}",
            flush=True,
        )
        time.sleep(60)
    if pending_domains:
        write_state(
            state="automated_metrics_failed",
            domains=pending_domains,
            max_passes=args.max_metric_passes,
        )
        return 2

    pending_domains = ["indoor", "urban"]
    for pass_number in range(1, args.max_package_passes + 1):
        write_state(
            state="annotation_packages_running",
            domains=pending_domains,
            pass_number=pass_number,
        )
        domains_this_pass = list(pending_domains)
        commands = [
            [str(PYTHON), str(METRICS), "--phase", "package", "--domain", domain]
            for domain in domains_this_pass
        ]
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=len(commands)
        ) as executor:
            codes = list(executor.map(run, commands))
        pending_domains = [
            domain for domain, code in zip(domains_this_pass, codes) if code != 0
        ]
        if not pending_domains:
            break
        print(
            f"SYNCITY3K_PACKAGES_RETRY pass={pass_number} "
            f"domains={pending_domains}",
            flush=True,
        )
        time.sleep(30)
    if pending_domains:
        write_state(
            state="annotation_packages_failed",
            domains=pending_domains,
            max_passes=args.max_package_passes,
        )
        return 2
    for domain in ("indoor", "urban"):
        if (
            run(
                [
                    str(PYTHON),
                    str(REVIEW_SHEETS),
                    "--package",
                    str(BASELINES_ROOT / "annotations/syncity3k" / domain),
                    "--output",
                    str(
                        BASELINES_ROOT
                        / "annotations/syncity3k"
                        / domain
                        / "review_20260910"
                    ),
                    "--items-per-sheet",
                    "10",
                ]
            )
            != 0
        ):
            write_state(state="review_sheets_failed", domain=domain)
            return 2
    write_state(
        state="ratings_pending",
        detail="automated metrics and two 100-item annotation packages complete",
    )
    print("SYNCITY3K_POSTPROCESS_END state=ratings_pending", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

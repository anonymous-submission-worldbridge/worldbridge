#!/usr/bin/env python3
"""Continue the SynCity 3000 formal matrix after the resumed pilot passes."""

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
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
PYTHON = BASELINES_ROOT / "envs/syncity-3k/bin/python"
MATRIX = BASELINES_ROOT / "methods/syncity/run.py"
PILOT_REPORT = BASELINES_ROOT / "results/syncity3k/matrix_pilot.json"
FORMAL_REPORT = BASELINES_ROOT / "results/syncity3k/matrix_formal.json"
STATE = BASELINES_ROOT / "results/syncity3k/supervisor_state.json"
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
        + "\n",
        encoding="utf-8",
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


def pilot_passed(data_root: Path) -> tuple[bool, str]:
    if not PILOT_REPORT.is_file():
        return False, f"missing pilot report: {PILOT_REPORT}"
    report = json.loads(PILOT_REPORT.read_text(encoding="utf-8"))
    tasks = report.get("tasks", [])
    if report.get("phase") != "pilot":
        return False, "pilot report phase is not pilot"
    if Path(report.get("data_root", "")).resolve() != data_root.resolve():
        return False, "pilot report points at a different data root"
    if len(tasks) != 20:
        return False, f"pilot report has {len(tasks)} tasks instead of 20"
    failures = [
        row
        for row in tasks
        if row.get("status")
        not in {
            "success",
            "skipped_success",
            "quality_failure",
            "skipped_quality_failure",
        }
    ]
    if failures:
        return False, f"pilot has {len(failures)} failed tasks"
    return True, "20/20 pilot tasks reached a frozen terminal state"


def formal_passed(data_root: Path) -> tuple[bool, str]:
    if not FORMAL_REPORT.is_file():
        return False, f"missing formal report: {FORMAL_REPORT}"
    try:
        report = json.loads(FORMAL_REPORT.read_text(encoding="utf-8"))
    except Exception as error:
        return False, f"invalid formal report: {error}"
    tasks = report.get("tasks", [])
    if report.get("phase") != "formal":
        return False, "formal report phase is not formal"
    if Path(report.get("data_root", "")).resolve() != data_root.resolve():
        return False, "formal report points at a different data root"
    if len(tasks) != 200:
        return False, f"formal report has {len(tasks)} tasks instead of 200"
    failures = [row for row in tasks if row.get("status") not in TERMINAL]
    if failures:
        return False, f"formal report has {len(failures)} infrastructure failures"
    return True, "200/200 formal tasks reached a frozen terminal state"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-session", default="syncity3k-pilot-0910")
    parser.add_argument("--gpus", nargs="+", type=int, default=[0, 1])
    parser.add_argument(
        "--data-root", type=Path, default=BASELINES_ROOT / "data/table2"
    )
    parser.add_argument("--minimum-free-mib", type=int, default=44000)
    parser.add_argument("--minimum-free-gib", type=float, default=100.0)
    parser.add_argument("--max-formal-passes", type=int, default=100)
    parser.add_argument("--retry-delay-seconds", type=int, default=60)
    args = parser.parse_args()
    data_root = args.data_root.resolve()
    data_root.relative_to(BASELINES_ROOT.resolve())

    write_state(
        state="waiting_for_pilot",
        pilot_session=args.pilot_session,
        data_root=str(data_root),
        gpus=args.gpus,
    )
    while screen_is_live(args.pilot_session):
        time.sleep(30)

    passed, detail = pilot_passed(data_root)
    if not passed:
        write_state(state="pilot_failed", detail=detail)
        print(f"SYNCITY3K_SUPERVISOR_STOP {detail}", flush=True)
        return 2

    command = [
        str(PYTHON),
        str(MATRIX),
        "--phase",
        "formal",
        "--domains",
        "indoor",
        "urban",
        "--gpus",
        *[str(gpu) for gpu in args.gpus],
        "--data-root",
        str(data_root),
        "--minimum-free-mib",
        str(args.minimum_free_mib),
        "--minimum-free-gib",
        str(args.minimum_free_gib),
    ]
    if args.max_formal_passes < 1:
        raise ValueError("--max-formal-passes must be positive")
    for pass_number in range(1, args.max_formal_passes + 1):
        write_state(
            state="formal_running",
            detail=detail,
            gpus=args.gpus,
            pass_number=pass_number,
            max_formal_passes=args.max_formal_passes,
        )
        print(
            f"SYNCITY3K_FORMAL_START pass={pass_number} {' '.join(command)}",
            flush=True,
        )
        completed = subprocess.run(command, cwd=BASELINES_ROOT.parent, check=False)
        passed, formal_detail = formal_passed(data_root)
        if completed.returncode == 0 and passed:
            write_state(
                state="formal_complete",
                exit_code=0,
                pass_number=pass_number,
                detail=formal_detail,
            )
            print(
                f"SYNCITY3K_SUPERVISOR_END state=formal_complete "
                f"pass={pass_number} detail={formal_detail}",
                flush=True,
            )
            return 0
        if pass_number < args.max_formal_passes:
            write_state(
                state="formal_retry_pending",
                exit_code=completed.returncode,
                pass_number=pass_number,
                detail=formal_detail,
            )
            print(
                f"SYNCITY3K_FORMAL_RETRY pass={pass_number} "
                f"exit_code={completed.returncode} detail={formal_detail}",
                flush=True,
            )
            time.sleep(args.retry_delay_seconds)
    write_state(
        state="formal_failed",
        exit_code=completed.returncode,
        pass_number=args.max_formal_passes,
        detail=formal_detail,
    )
    print(
        f"SYNCITY3K_SUPERVISOR_END state=formal_failed "
        f"exit_code={completed.returncode} detail={formal_detail}",
        flush=True,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

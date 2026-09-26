#!/usr/bin/env python3
"""Bound the migrated primary queue after seed 3, then relaunch specs 0--14."""

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


import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
SOURCE_UNIT = "legacyworld-majutsucity-table2-r1.service"
DESTINATION_UNIT = "legacyworld-majutsucity-table2-a-r2"
SEED3 = BASELINES / "data/table2/urban/majutsucity/urban_residential_four_way_00/seed_3"
REPORT = BASELINES / "results/majutsucity_4090/handoff_seed3.json"
PRIMARY_SPECS = [
    "urban_residential_four_way_00",
    "urban_residential_t_junction_01",
    "urban_residential_main_side_02",
    "urban_residential_offset_03",
    "urban_residential_irregular_04",
    "urban_commercial_four_way_05",
    "urban_commercial_t_junction_06",
    "urban_commercial_main_side_07",
    "urban_commercial_offset_08",
    "urban_commercial_irregular_09",
    "urban_mixed_use_four_way_10",
    "urban_mixed_use_t_junction_11",
    "urban_mixed_use_main_side_12",
    "urban_mixed_use_offset_13",
    "urban_mixed_use_irregular_14",
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def quality_terminal() -> bool:
    command_path = SEED3 / "render_command.json"
    validation_path = SEED3 / "renders/validation.json"
    if not command_path.is_file() or not validation_path.is_file():
        return False
    command = json.loads(command_path.read_text(encoding="utf-8"))
    validation = json.loads(validation_path.read_text(encoding="utf-8"))
    return (
        command.get("exit_code") == 0
        and command.get("validation_valid") is False
        and validation.get("valid") is False
        and "finished_at" in command
    )


def active(unit: str) -> bool:
    return (
        subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", unit], check=False
        ).returncode
        == 0
    )


def main() -> int:
    started_at = utc_now()
    while not (SEED3 / "SUCCESS").is_file() and not quality_terminal():
        if not active(SOURCE_UNIT):
            raise RuntimeError(
                f"Source unit exited before seed 3 became terminal: {SOURCE_UNIT}"
            )
        time.sleep(10)

    terminal = "success" if (SEED3 / "SUCCESS").is_file() else "quality_failure"
    subprocess.run(["systemctl", "--user", "stop", SOURCE_UNIT], check=True)
    deadline = time.monotonic() + 180
    while active(SOURCE_UNIT):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"Source unit did not stop: {SOURCE_UNIT}")
        time.sleep(2)

    command = [
        "systemd-run",
        "--user",
        f"--unit={DESTINATION_UNIT}",
        "--description=MajutsuCity Table2 formal shard A specs 0-14",
        _wb_expand_paths("--property=WorkingDirectory=${WORLDBRIDGE_ROOT}"),
        "--property=KillMode=control-group",
        "--property=TimeoutStopSec=120",
        "--collect",
        "/usr/bin/env",
        "PYTHONUNBUFFERED=1",
        _wb_expand_paths("${WORLDBRIDGE_ROOT}/baselines/envs/majutsucity/bin/python"),
        _wb_expand_paths(
            "${WORLDBRIDGE_ROOT}/baselines/methods/majutsucity/run_4090_matrix.py"
        ),
        "--trial-mode",
        "formal",
        "--render-gpu",
        "0",
        "--layout-gpu",
        "0",
        "--pipeline-gpus",
        "1",
        "2",
        "3",
        "4",
        "--minimum-free-mib",
        "20000",
        "--stable-gpu-seconds",
        "60",
        "--gpu-poll-seconds",
        "10",
        "--attempts",
        "3",
    ]
    for spec_id in PRIMARY_SPECS:
        command.extend(["--only-spec", spec_id])
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    if completed.returncode:
        raise RuntimeError(completed.stderr or completed.stdout)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(
        json.dumps(
            {
                "started_at": started_at,
                "seed3_terminal": terminal,
                "source_unit": SOURCE_UNIT,
                "destination_unit": f"{DESTINATION_UNIT}.service",
                "primary_specs": PRIMARY_SPECS,
                "systemd_run_stdout": completed.stdout.strip(),
                "finished_at": utc_now(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

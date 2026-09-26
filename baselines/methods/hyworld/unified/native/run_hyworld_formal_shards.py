#!/usr/bin/env python3
"""Launch disjoint, capacity-qualified HY-World Table-4 formal stage shards."""

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
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
TABLE4_ROOT = _BASELINE_PROJECT_ROOT / "baselines/methods/hyworld/unified/native"
SPECS_PATH = BASELINES_ROOT / "protocol/unified/specs.jsonl"
LOG_ROOT = BASELINES_ROOT / "results/table4/hyworld2/formal/logs/shards"
RUNNER = TABLE4_ROOT / "run_hyworld_matrix.py"
SUPERVISOR = TABLE4_ROOT / "supervise_hyworld.py"
GS_PARALLEL = TABLE4_ROOT / "run_hyworld_gs_parallel.py"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def spec_ids() -> list[str]:
    rows = [
        json.loads(line) for line in SPECS_PATH.read_text().splitlines() if line.strip()
    ]
    ids = [str(row["spec_id"]) for row in rows]
    if len(ids) != 25 or len(set(ids)) != 25:
        raise RuntimeError(f"Expected 25 unique formal specs, found {len(ids)}")
    return ids


def runner_command(
    python: str,
    stage: str,
    ids: list[str],
    gpus: list[int],
    min_free_mib: int,
    min_free_disk_gib: float,
    llm_port: int,
) -> list[str]:
    command = [
        python,
        str(RUNNER),
        "--stage",
        stage,
        "--trial",
        "formal",
        "--domains",
        "indoor",
        "urban",
        "--spec-ids",
        *ids,
        "--gpus",
        *(str(gpu) for gpu in gpus),
        "--min-free-mib",
        str(min_free_mib),
        "--min-free-disk-gib",
        str(min_free_disk_gib),
    ]
    if stage in {"trajectory_planning", "trajectory_rendering"}:
        command.extend(["--external-llm", "--llm-port", str(llm_port)])
    return command


def launch(commands: list[tuple[str, list[str]]], environment: dict[str, str]) -> int:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    children: list[tuple[str, subprocess.Popen[str], object, Path]] = []
    for label, command in commands:
        log_path = LOG_ROOT / f"{label}_{stamp}.log"
        handle = log_path.open("a", buffering=1, encoding="utf-8")
        handle.write(
            json.dumps({"started_at_utc": utc_now(), "command": command}) + "\n"
        )
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            env=environment,
            stdout=handle,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        children.append((label, process, handle, log_path))
        print(
            f"HYWORLD2_SHARD_START label={label} pid={process.pid} log={log_path}",
            flush=True,
        )
    failures = 0
    for label, process, handle, log_path in children:
        code = process.wait()
        handle.close()
        print(
            f"HYWORLD2_SHARD_END label={label} exit={code} log={log_path}", flush=True
        )
        failures += int(code != 0)
    return 0 if failures == 0 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stage",
        required=True,
        choices=(
            "trajectory_planning",
            "trajectory_rendering",
            "world_expansion",
            "gs_data",
            "gs_training",
            "canonical_render",
        ),
    )
    parser.add_argument("--gpus", nargs="+", type=int, default=[0, 1, 2, 3, 4])
    parser.add_argument("--min-free-mib", type=int, default=9000)
    parser.add_argument("--min-free-disk-gib", type=float, default=120.0)
    parser.add_argument("--llm-port", type=int, default=18080)
    args = parser.parse_args()
    if len(args.gpus) != len(set(args.gpus)) or not args.gpus:
        raise ValueError("GPU ids must be nonempty and unique")
    ids = spec_ids()
    python = os.environ.get("HYWORLD2_PYTHON", sys.executable)
    commands: list[tuple[str, list[str]]] = []
    if args.stage in {"trajectory_planning", "trajectory_rendering"}:
        if len(args.gpus) < 5:
            raise ValueError(f"{args.stage} formal sharding requires five GPUs")
        for index, gpu in enumerate(args.gpus[:5]):
            shard = ids[index * 5 : (index + 1) * 5]
            commands.append(
                (
                    f"{args.stage}_shard{index}_gpu{gpu}",
                    runner_command(
                        python,
                        args.stage,
                        shard,
                        [gpu],
                        args.min_free_mib,
                        args.min_free_disk_gib,
                        args.llm_port,
                    ),
                )
            )
    elif args.stage == "world_expansion":
        if len(args.gpus) < 2:
            raise ValueError("world_expansion requires two GPUs")
        # WorldStereo's validated fast path uses two ranks.  Formal retries
        # established that two independent model instances can contend in the
        # first compiled forward, while one resident two-rank batch progresses
        # normally.  Preserve one model instance and process all independent
        # scenes sequentially within it.
        gpus = args.gpus[:2]
        commands.append(
            (
                f"world_expansion_all_gpu{gpus[0]}-{gpus[1]}",
                runner_command(
                    python,
                    args.stage,
                    ids,
                    gpus,
                    args.min_free_mib,
                    args.min_free_disk_gib,
                    args.llm_port,
                ),
            )
        )
    elif args.stage == "gs_data":
        if len(args.gpus) < 4:
            raise ValueError("gs_data sharding requires four GPUs")
        groups = ((ids[:13], args.gpus[:2]), (ids[13:], args.gpus[2:4]))
        for index, (shard, gpus) in enumerate(groups):
            commands.append(
                (
                    f"gs_data_shard{index}_gpu{gpus[0]}-{gpus[1]}",
                    runner_command(
                        python,
                        args.stage,
                        list(shard),
                        list(gpus),
                        args.min_free_mib,
                        args.min_free_disk_gib,
                        args.llm_port,
                    ),
                )
            )
    elif args.stage == "gs_training":
        commands.append(
            (
                "gs_training_all",
                [
                    python,
                    str(GS_PARALLEL),
                    "--phase",
                    "formal",
                    "--domains",
                    "indoor",
                    "urban",
                    "--gpus",
                    *(str(gpu) for gpu in args.gpus),
                    "--min-free-mib",
                    str(args.min_free_mib),
                    "--min-free-disk-gib",
                    str(args.min_free_disk_gib),
                ],
            )
        )
    else:
        if len(args.gpus) < 5:
            raise ValueError("canonical_render formal sharding requires five GPUs")
        for index, gpu in enumerate(args.gpus[:5]):
            shard = ids[index * 5 : (index + 1) * 5]
            commands.append(
                (
                    f"canonical_render_shard{index}_gpu{gpu}",
                    [
                        python,
                        str(SUPERVISOR),
                        "--trial",
                        "formal",
                        "--domains",
                        "indoor",
                        "urban",
                        "--spec-ids",
                        *shard,
                        "--allowed-gpus",
                        str(gpu),
                        "--poll-seconds",
                        "15",
                        "--min-free-mib",
                        str(args.min_free_mib),
                        "--max-used-mib",
                        "49140",
                        "--max-utilization",
                        "100",
                        "--stable-idle-seconds",
                        "0",
                        "--min-free-disk-gib",
                        str(args.min_free_disk_gib),
                    ],
                )
            )
    return launch(commands, dict(os.environ))


if __name__ == "__main__":
    raise SystemExit(main())

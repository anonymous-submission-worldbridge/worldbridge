#!/usr/bin/env python3
"""Keep the in-flight WorldScore batch; parallelize the remaining exact specs."""

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

from concurrent.futures import ThreadPoolExecutor
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE), str(BASE / "tools"), str((BASE / "methods"))]
import baselines.methods.gpt.adapter as adapter
import baselines.methods.gpt.tools.stream_gpt_urban_metrics as stream
from baselines.methods.gpt.tools.accelerate_gpt import proc
from baselines.methods.gpt.tools.accelerate_gpt import children
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock
from baselines.methods.gpt.evaluate import check_consistency_records

OLD_PID = 3304820
FIRST = BASE / "results/gpt6_astra/urban_stream_metrics_20260909/batch_01"
OUTPUT = BASE / "results/gpt6_astra/urban_parallel_metrics_20260909"


def load_rows(path):
    return [json.loads(x) for x in path.read_text().splitlines() if x]


def spec_folder(prefix, specs):
    folder = OUTPUT / prefix
    folder.mkdir()
    (folder / "specs.jsonl").write_text(
        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in specs)
    )
    return folder


def merge(specs, diversity_folders):
    if not all(stream.terminal(s) for s in specs):
        raise RuntimeError("Partial matrix cannot be aggregated")
    final = BASE / "results/gpt6_astra/formal/urban"
    final.mkdir(parents=True, exist_ok=True)
    for metric, filename in (
        ("iqa", "iqa_per_scene.jsonl"),
        ("consistency_3d", "consistency_per_scene.jsonl"),
    ):
        rows = []
        for spec in specs:
            for seed in range(4):
                path = (
                    stream.DATA
                    / "urban/gpt6_astra"
                    / spec["spec_id"]
                    / f"seed_{seed}/metrics/{metric}.json"
                )
                row = json.loads(path.read_text())
                if (
                    row["spec_id"],
                    row["logical_seed"],
                    row["method"],
                    row["domain"],
                ) != (spec["spec_id"], seed, "gpt6_astra", "urban"):
                    raise RuntimeError("Foreign or incomplete metric record")
                rows.append(row)
        if metric == "consistency_3d":
            check_consistency_records(rows, stream.DATA, "urban")
        target = final / filename
        if target.exists():
            raise RuntimeError("Refuse overwrite formal results")
        target.write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        )
    rows = [
        r for f in diversity_folders for r in load_rows(f / "diversity_per_spec.jsonl")
    ]
    by_id = {r["spec_id"]: r for r in rows}
    if len(rows) != 25 or set(by_id) != {s["spec_id"] for s in specs}:
        raise RuntimeError("Diversity spec coverage mismatch")
    (final / "diversity_per_spec.jsonl").write_text(
        "".join(
            json.dumps(by_id[s["spec_id"]], ensure_ascii=False) + "\n" for s in specs
        )
    )
    adapter.write_json(
        final / "streaming_execution.json",
        dict(
            strategy="Unchanged frozen evaluators with exact terminal spec subsets and concurrent WorldScore lanes",
            first_batch=str(FIRST.relative_to(BASE)),
            parallel_execution=str(OUTPUT.relative_to(BASE)),
            diversity_batches=[str(f.relative_to(BASE)) for f in diversity_folders],
            expected_runs=100,
        ),
    )
    subprocess.run(
        [
            sys.executable,
            "-B",
            str((BASE / "evaluation/visual/aggregate_generation.py")),
            "--protocol",
            str((BASE / "methods/gpt/protocol/generation/gpt6_astra.json")),
            "--spec-file",
            str((BASE / "protocol/generation/urban_specs.jsonl")),
            "--data-root",
            str(stream.DATA),
            "--results-root",
            str(final),
            "--method",
            "gpt6_astra",
            "--domain",
            "urban",
        ],
        check=True,
        cwd=BASE.parent,
    )


def main():
    verify_lock()
    parent = proc(OLD_PID)
    if (
        not parent
        or parent["uid"] != os.getuid()
        or not any(x.endswith("stream_gpt_urban_metrics.py") for x in parent["command"])
    ):
        raise RuntimeError("Old metric controller identity changed")
    initial = load_rows(FIRST / "specs.jsonl")
    old_state = json.loads((FIRST.parent / "state.json").read_text())
    if old_state["batches"] != 1 or old_state["active"] != ["batch_01/consistency"]:
        raise RuntimeError("Not at the expected one-child migration boundary")
    for stage in ("iqa", "semantics", "diversity"):
        if (
            json.loads((FIRST / f"{stage}_execution.json").read_text()).get("exit_code")
            != 0
        ):
            raise RuntimeError("Cannot reuse incomplete first metric stages")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    guard = (OUTPUT / "controller.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (OUTPUT / "state.json").exists():
        raise RuntimeError("Existing migration record")
    os.kill(OLD_PID, signal.SIGSTOP)
    try:
        captured = children(OLD_PID)
        if len(captured) != 1:
            raise RuntimeError("Unexpected metric children")
        child = captured[0]
        cmd = child["command"]
        if (
            child["uid"] != os.getuid()
            or str(FIRST / "specs.jsonl") not in cmd
            or not any(x.endswith("eval_worldscore.py") for x in cmd)
        ):
            raise RuntimeError("Refuse unrelated child adoption")
        old_gpu = int(cmd[cmd.index("--gpu") + 1])
        stream.leases.add(old_gpu)
        state = dict(
            started_at_utc=adapter.utc(),
            status="running",
            old_parent=parent,
            adopted_child=child,
            controller_sha256=adapter.digest(__file__),
            first_batch_specs=[s["spec_id"] for s in initial],
            resource_change="Up to three additional WorldScore spec jobs, unchanged evaluator; old child continues",
            errors=[],
        )
        adapter.write_json(OUTPUT / "state.json", state)
        pid = os.fork()
        if pid:
            print(
                "DETACHED_PARALLEL_METRICS",
                pid,
                "preserved_child",
                child["pid"],
                flush=True,
            )
            return
        os.setsid()
        fd = os.open(
            OUTPUT / "controller.log", os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o664
        )
        os.dup2(fd, 1)
        os.dup2(fd, 2)
        os.close(fd)
        null = os.open("/dev/null", os.O_RDONLY)
        os.dup2(null, 0)
        os.close(null)
    except Exception:
        os.kill(OLD_PID, signal.SIGCONT)
        raise
    specs = load_rows((BASE / "protocol/generation/urban_specs.jsonl"))
    initial_ids = {s["spec_id"] for s in initial}
    iqa_done, diversity_done = set(initial_ids), set(initial_ids)
    consistency_done = set()
    iqa_assigned, diversity_assigned, consistency_assigned = (
        set(initial_ids),
        set(initial_ids),
        set(initial_ids),
    )
    jobs, diversity_folders, retired = {}, [FIRST], False
    state["controller_pid"] = os.getpid()
    with ThreadPoolExecutor(max_workers=5) as pool:
        while True:
            if not retired:
                current = proc(child["pid"])
                if not current or current["birth"] != child["birth"]:
                    raise RuntimeError(
                        "Adopted metric child disappeared before exit capture"
                    )
                if current["state"] == "Z":
                    rc = os.waitstatus_to_exitcode(current["wait_status"])
                    record = json.loads(
                        (FIRST / "consistency_execution.json").read_text()
                    )
                    record.update(
                        exit_code=rc,
                        ended_at_utc=adapter.utc(),
                        adopted_by=str(OUTPUT.relative_to(BASE)),
                    )
                    adapter.write_json(FIRST / "consistency_execution.json", record)
                    if rc:
                        raise RuntimeError("Adopted WorldScore failed")
                    rows = load_rows(FIRST / "consistency_per_scene.jsonl")
                    if len(rows) != len(initial) * 4:
                        raise RuntimeError("Incomplete adopted batch")
                    check_consistency_records(rows, stream.DATA, "urban")
                    consistency_done.update(initial_ids)
                    with stream.lease_lock:
                        stream.leases.remove(old_gpu)
                    os.kill(OLD_PID, signal.SIGTERM)
                    os.kill(OLD_PID, signal.SIGCONT)
                    retired = True
                    state["old_parent_retired_at_utc"] = adapter.utc()
            for future in list(jobs):
                if not future.done():
                    continue
                kind, ids, folder = jobs.pop(future)
                try:
                    future.result()
                    {
                        "iqa": iqa_done,
                        "consistency": consistency_done,
                        "semantics_diversity": diversity_done,
                    }[kind].update(ids)
                    if kind == "semantics_diversity":
                        diversity_folders.append(folder)
                except Exception as error:
                    state["errors"].append(str(error))
            if not state["errors"]:
                ready = [s for s in specs if stream.terminal(s)]
                for kind, assigned in (
                    ("iqa", iqa_assigned),
                    ("semantics_diversity", diversity_assigned),
                ):
                    candidates = [s for s in ready if s["spec_id"] not in assigned]
                    if any(k == kind for k, ids, folder in jobs.values()):
                        continue
                    if (
                        len(candidates) >= 3
                        or candidates
                        and len(assigned) + len(candidates) == 25
                    ):
                        folder = spec_folder(
                            kind + "_" + str(len(assigned)), candidates
                        )
                        ids = {s["spec_id"] for s in candidates}
                        assigned.update(ids)
                        future = (
                            pool.submit(stream.semantics_and_diversity, folder)
                            if kind == "semantics_diversity"
                            else pool.submit(stream.evaluate, folder, kind)
                        )
                        jobs[future] = kind, ids, folder
                available = 3 - sum(
                    k == "consistency" for k, ids, folder in jobs.values()
                )
                for spec in [
                    s for s in ready if s["spec_id"] not in consistency_assigned
                ][:available]:
                    sid = spec["spec_id"]
                    folder = spec_folder("consistency_" + sid, [spec])
                    consistency_assigned.add(sid)
                    jobs[pool.submit(stream.evaluate, folder, "consistency")] = (
                        "consistency",
                        {sid},
                        folder,
                    )
            state.update(
                updated_at_utc=adapter.utc(),
                completed_specs=dict(
                    iqa=len(iqa_done),
                    diversity=len(diversity_done),
                    consistency=len(consistency_done),
                ),
                active=[
                    dict(stage=k, specs=sorted(ids)) for k, ids, f in jobs.values()
                ],
                old_child_running=not retired,
            )
            if state["errors"] and not jobs and retired:
                state["status"] = "paused_error"
            elif len(iqa_done) == len(diversity_done) == len(consistency_done) == 25:
                merge(specs, diversity_folders)
                state["status"] = "automatic_metrics_complete"
            adapter.write_json(OUTPUT / "state.json", state)
            print(
                json.dumps(
                    {
                        k: state[k]
                        for k in (
                            "updated_at_utc",
                            "status",
                            "completed_specs",
                            "active",
                            "old_child_running",
                            "errors",
                        )
                    }
                ),
                flush=True,
            )
            if state["status"] != "running":
                break
            time.sleep(20)


if __name__ == "__main__":
    main()

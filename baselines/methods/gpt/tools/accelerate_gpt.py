"""Resource-only dispatcher replacement; retain every frozen experiment source.

Adopts the old dispatcher's live children without restarting them. New work uses
the original task implementation, prompts, timeouts, validators and metrics.
"""

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
from collections import Counter
from datetime import datetime
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(ROOT), str((ROOT / "methods")), str(ROOT / "tools")]
import baselines.methods.gpt.adapter as adapter
import baselines.methods.gpt.run as matrix
from baselines.methods.gpt.tools.migrate_gpt_scheduler import process


def verify_lock():
    lock = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json")).read_text()
    )
    for path, expected in lock["files_sha256"].items():
        if adapter.digest(ROOT / path) != expected:
            raise RuntimeError("Frozen source changed: " + path)
    return lock


def proc(pid):
    row = process(pid)
    if row:
        stat = (Path("/proc") / str(pid) / "stat").read_text()
        row["birth"] = stat[stat.rfind(")") + 2 :].split()[19]
    return row


def children(pid):
    rows = []
    for path in Path("/proc").iterdir():
        if path.name.isdigit():
            try:
                row = proc(int(path.name))
            except (FileNotFoundError, PermissionError, ProcessLookupError):
                continue
            if row and row["ppid"] == pid:
                rows.append(row)
    return rows


def target(child, runs):
    command = child["command"]
    if child["uid"] != os.getuid() or child["pgid"] != child["pid"]:
        raise RuntimeError("Child is not an owned independent process group")
    if command and Path(command[0]).name == "bwrap" and "--run-dir" in command:
        run = Path(command[command.index("--run-dir") + 1]).resolve()
        phase = command[-1] if command[-2] == "--phase" else None
        if phase not in ("build", "render"):
            raise RuntimeError("Unknown Blender phase")
    elif "--model" in command and "--output-schema" in command and "-C" in command:
        if command[command.index("--model") + 1] != "gpt-6-astra":
            raise RuntimeError("Wrong requested model")
        run = Path(command[command.index("-C") + 1]).resolve().parent
        phase = "generate"
    else:
        raise RuntimeError("Dispatcher is between tasks; retry a quiescent snapshot")
    if run not in runs:
        raise RuntimeError("Child is outside the exact formal Astra matrix")
    return run, phase


def stage(m):
    if m.get("failure_class") == "quality":
        return "quality"
    if m.get("render_success"):
        return "valid"
    if m.get("build_success"):
        return "render"
    if m.get("generation_success"):
        return "build"
    return "generate"


def finish_generation(run, m, attempt, rc, timed_out):
    """Match the frozen adapter's response acceptance and failure policy."""
    folder = run / ("logs/generation_%02d" % attempt["index"])
    events_text = (folder / "events.jsonl").read_text()
    events = []
    for line in events_text.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    attempt["thread_ids"] = [
        e["thread_id"] for e in events if e.get("type") == "thread.started"
    ]
    attempt["usage"] = [
        e.get("usage") for e in events if e.get("type") == "turn.completed"
    ]
    attempt["tool_events"] = [
        e.get("item", {}).get("type")
        for e in events
        if e.get("type") == "item.completed"
        and e.get("item", {}).get("type") != "agent_message"
    ]
    output = folder / "response.json"
    if rc == 0 and output.exists():
        try:
            response = json.loads(output.read_text())
            adapter.check_code(response["code"])
            if attempt["tool_events"]:
                raise ValueError(
                    "Generation used tools outside the frozen text-only interface"
                )
            (run / "scene").mkdir(exist_ok=True)
            (run / "scene/generated.py").write_text(response["code"] + "\n")
            m.update(
                generation_success=True,
                failure_class=None,
                failure_reason=None,
                generated_code_sha256=adapter.digest(run / "scene/generated.py"),
            )
        except (ValueError, KeyError, TypeError, SyntaxError) as error:
            m.update(
                failure_class="quality",
                failure_reason=type(error).__name__ + ": " + str(error),
            )
        m["ended_at_utc"] = adapter.utc()
    else:
        logs = events_text + (folder / "stderr.log").read_text()
        blocked = any(
            s in logs.lower()
            for s in (
                "usage limit",
                "rate limit",
                "not supported",
                "not found",
                "unauthorized",
                "authentication",
                "quota",
            )
        )
        m.update(
            failure_class="access_blocked" if blocked else "infrastructure",
            failure_reason="See generation logs; target model access or quota blocked"
            if blocked
            else "Codex process failed or timed out",
        )
    return m


def finish_blender(run, m, phase, attempt, rc, timed_out):
    folder = run / ("logs/%s_%02d" % (phase, attempt["index"]))
    logs = (folder / "stdout.log").read_text() + (folder / "stderr.log").read_text()
    if rc == 0 and not timed_out and "ASTRA_%s_COMPLETE" % phase.upper() in logs:
        m[phase + "_success"] = True
        m.update(failure_class=None, failure_reason=None)
        if phase == "render":
            validation = matrix.validate(run)
            m.update(
                render_success=validation["valid"],
                ended_at_utc=adapter.utc(),
                exit_code=0 if validation["valid"] else 2,
            )
            if validation["valid"]:
                (run / "SUCCESS").write_text(adapter.utc() + "\n")
            else:
                m.update(
                    failure_class="quality",
                    failure_reason="; ".join(validation["problems"]),
                )
    else:
        resource = any(
            s in logs.lower()
            for s in ("out of memory", "cannot allocate memory", "memoryerror")
        )
        quality = not resource and (
            (phase == "build" and rc == 11 and "generated.py" in logs)
            or any(
                s in logs
                for s in (
                    "No traversable camera cells",
                    "Traversable path too short",
                    "Generated scene contains",
                    "Generated scene has no mesh",
                )
            )
        )
        m.update(
            failure_class="quality" if quality else "infrastructure",
            failure_reason="%s failed: %s" % (phase, folder.relative_to(run)),
        )
        if (
            "bwrap:" in logs
            or "No CUDA/OPTIX" in logs
            or (rc == 11 and not resource and not quality)
        ):
            m["acceleration_setup_error"] = True
    return m


def adopt_child(child, run, phase, parent):
    path = run / "run_manifest.json"
    m = json.loads(path.read_text())
    attempt = m["attempts" if phase == "generate" else phase + "_attempts"][-1]
    config = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    limit = (
        config["generation_timeout_s"]
        if phase == "generate"
        else attempt["timeout_limit_s"]
    )
    deadline = datetime.fromisoformat(attempt["started_at_utc"]).timestamp() + limit
    timed_out, sent_at = False, None
    while True:
        current = proc(child["pid"])
        if not current or current["birth"] != child["birth"]:
            raise RuntimeError(
                "Adopted child disappeared before its real exit status was captured"
            )
        if current["state"] == "Z":
            rc = os.waitstatus_to_exitcode(current["wait_status"])
            break
        if time.time() > deadline and not timed_out:
            os.killpg(child["pid"], signal.SIGTERM)
            timed_out, sent_at = True, time.time()
        if timed_out and time.time() - sent_at > 10:
            os.killpg(child["pid"], signal.SIGKILL)
        time.sleep(2)
    attempt.update(
        exit_code=rc,
        timeout=timed_out,
        ended_at_utc=adapter.utc(),
        adopted_from_dispatcher_pid=parent,
        adopted_child_pid=child["pid"],
        adoption_note="Resource-only scheduling migration; original start and deadline retained",
    )
    if phase == "generate":
        m = finish_generation(run, m, attempt, rc, timed_out)
    else:
        m = finish_blender(run, m, phase, attempt, rc, timed_out)
    adapter.write_json(path, m)
    print(
        "ADOPTED_END",
        phase,
        run.parent.name,
        run.name,
        rc,
        m.get("failure_class"),
        flush=True,
    )
    return m


def take_over(parent_pid, supervisor_pid, runs):
    parent, supervisor = proc(parent_pid), proc(supervisor_pid)
    if not parent or not supervisor or parent["ppid"] != supervisor_pid:
        raise RuntimeError("Dispatcher/supervisor ancestry changed")
    for row in (parent, supervisor):
        if row["uid"] != os.getuid() or not any(
            x.endswith("methods/gpt/run.py") for x in row["command"]
        ):
            raise RuntimeError("Refuse to signal an unrelated process")
    if (
        "--complete-after-pilot" not in supervisor["command"]
        or "--data-root" not in parent["command"]
    ):
        raise RuntimeError("Unexpected original workflow role")
    if (
        Path(parent["command"][parent["command"].index("--data-root") + 1]).resolve()
        != ROOT / "data/table2"
    ):
        raise RuntimeError("Not the formal matrix")
    for index in range(12):
        before = {c["pid"]: c for c in children(parent_pid)}
        os.kill(parent_pid, signal.SIGSTOP)
        time.sleep(0.1)
        try:
            captured, active = [], {}
            for child in children(parent_pid):
                if (
                    not child["command"]
                    and child["pid"] in before
                    and child["birth"] == before[child["pid"]]["birth"]
                ):
                    child["command"] = before[child["pid"]]["command"]
                run, phase = target(child, runs)
                if run in active:
                    raise RuntimeError("Two old children share one run")
                active[run] = phase
                captured.append((child, run, phase))
            manifests = {}
            for run in runs:
                path = run / "run_manifest.json"
                m = json.loads(path.read_text()) if path.exists() else {}
                manifests[run] = m
                opened = [
                    p
                    for p in ("generate", "build", "render")
                    if m.get("attempts" if p == "generate" else p + "_attempts")
                    and not m["attempts" if p == "generate" else p + "_attempts"][
                        -1
                    ].get("ended_at_utc")
                ]
                if opened != ([active[run]] if run in active else []):
                    raise RuntimeError(
                        "Child/manifest boundary is not quiescent: " + str(run)
                    )
            return captured, manifests, parent, supervisor
        except Exception as error:
            os.kill(parent_pid, signal.SIGCONT)
            print("SNAPSHOT_RETRY", index, str(error), flush=True)
            if index == 11:
                raise
            time.sleep(5)


def gpu_free():
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    return {
        int(a): int(b) for a, b in (line.split(",") for line in output.splitlines())
    }


def domain_metrics(domain, gpu, output):
    def command(label, args):
        path = output / (domain + "_" + label + ".log")
        print("DOMAIN_STAGE", domain, label, "gpu", gpu, flush=True)
        with path.open("w") as log:
            result = subprocess.run(
                list(map(str, args)),
                cwd=ROOT.parent,
                stdout=log,
                stderr=subprocess.STDOUT,
            )
        if result.returncode:
            raise RuntimeError("Domain stage failed; inspect " + str(path))

    wrapper = [
        sys.executable,
        "-B",
        (ROOT / "methods/gpt/evaluate.py"),
        "--domain",
        domain,
        "--gpu",
        gpu,
    ]
    package = ROOT / "annotations/gpt6_astra" / domain
    if not package.exists():
        command("annotations", [*wrapper, "--stages", "annotations"])
    elif not all(
        (package / name).exists()
        for name in (
            "items.csv",
            "layout_ratings.csv",
            "prompt_ratings.csv",
            "PRIVATE_blind_map.json",
        )
    ):
        raise RuntimeError(
            "Partial annotation package; refusing to overwrite possible ratings"
        )
    command(
        "metrics",
        [*wrapper, "--stages", "iqa", "semantics", "consistency", "diversity"],
    )
    result = ROOT / "results/gpt6_astra/formal" / domain
    command(
        "aggregate",
        [
            sys.executable,
            "-B",
            (ROOT / "evaluation/visual/aggregate_generation.py"),
            "--protocol",
            (ROOT / "methods/gpt/protocol/generation/gpt6_astra.json"),
            "--spec-file",
            ROOT / ("protocol/" + domain + "_specs.jsonl"),
            "--data-root",
            ROOT / "data/table2",
            "--results-root",
            result,
            "--method",
            "gpt6_astra",
            "--domain",
            domain,
        ],
    )
    full = json.loads((result / "table2_full.json").read_text())
    keys = (
        "qalign",
        "clipiqa_plus",
        "consistency_3d",
        "appearance_diversity_itt",
        "layout_diversity_itt",
    )
    if any(full["metrics"][k]["status"] != "complete" for k in keys):
        raise RuntimeError("Five automatic columns incomplete: " + domain)
    return {k: full["metrics"][k]["mean"] for k in keys}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix-pid", type=int)
    parser.add_argument("--supervisor-pid", type=int)
    parser.add_argument(
        "--resume-id",
        help="New auditable execution directory after all previous workers have ended",
    )
    parser.add_argument("--defer-exhausted-infrastructure", action="store_true")
    parser.add_argument("--generators", type=int, choices=[8], default=8)
    parser.add_argument("--builders", type=int, choices=[16, 24, 32], default=16)
    parser.add_argument("--render-slots", type=int, choices=[1, 2], default=1)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if args.resume_id:
        if not all(c.isalnum() or c == "_" for c in args.resume_id):
            parser.error("Resume ID must be alphanumeric/underscore")
    elif args.matrix_pid is None or args.supervisor_pid is None:
        parser.error("Initial takeover needs both exact parent PIDs")
    lock = verify_lock()
    runs = {}
    for domain in ("indoor", "urban"):
        specs = [
            json.loads(l)
            for l in (ROOT / ("protocol/" + domain + "_specs.jsonl"))
            .read_text()
            .splitlines()
            if l
        ]
        for spec in specs:
            for seed in range(4):
                runs[
                    ROOT
                    / "data/table2"
                    / domain
                    / "gpt6_astra"
                    / spec["spec_id"]
                    / ("seed_" + str(seed))
                ] = (spec, seed)
    if args.check_only:
        print(
            json.dumps(
                {
                    "frozen_files_unchanged": len(lock["files_sha256"]),
                    "runs": len(runs),
                    "gpu_free_mib": gpu_free(),
                    "old_children": len(children(args.matrix_pid))
                    if args.matrix_pid
                    else None,
                }
            )
        )
        return
    output = (
        ROOT
        / "results/gpt6_astra"
        / ("resume_" + args.resume_id if args.resume_id else "acceleration_20260909")
    )
    output.mkdir(parents=True, exist_ok=True)
    guard = (output / "controller.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state_path = output / "state.json"
    if state_path.exists():
        raise RuntimeError("Existing takeover record; inspect instead of duplicating")
    state = {
        "started_at_utc": adapter.utc(),
        "status": "preparing",
        "resource_revision": {
            "reason": "User requested acceleration on 2026-09-09",
            "generators": args.generators,
            "builders": args.builders,
            "render_slots_per_gpu": args.render_slots,
            "domain_metrics_overlap_generation": True,
        },
        "experiment_sources_unchanged": lock["files_sha256"],
        "controller_sha256": adapter.digest(__file__),
        "errors": [],
        "domains": {},
    }
    adapter.write_json(state_path, state)
    if args.resume_id:
        # Closed attempts alone are not sufficient: also reject live generation
        # or Blender workers for the exact matrix, in the host PID namespace.
        for path in Path("/proc").iterdir():
            if not path.name.isdigit():
                continue
            try:
                row = proc(int(path.name))
            except (FileNotFoundError, PermissionError):
                continue
            if not row or row["uid"] != os.getuid() or row["pid"] == os.getpid():
                continue
            command = row["command"]
            if (
                any(x.endswith("accelerate_gpt.py") for x in command)
                and "--check-only" not in command
            ):
                raise RuntimeError("Another acceleration controller is live")
            for flag, parent_run in (("--run-dir", False), ("-C", True)):
                if flag in command:
                    candidate = Path(command[command.index(flag) + 1]).resolve()
                    if (candidate.parent if parent_run else candidate) in runs:
                        raise RuntimeError(
                            "An experiment worker is still live; refusing overlap"
                        )
        captured, manifests, parent, supervisor = [], {}, None, None
        for run in runs:
            path = run / "run_manifest.json"
            m = json.loads(path.read_text()) if path.exists() else {}
            for key in ("attempts", "build_attempts", "render_attempts"):
                if m.get(key) and not m[key][-1].get("ended_at_utc"):
                    raise RuntimeError("Unclosed attempt requires triage: " + str(run))
            if bool(m.get("render_success")) != (run / "SUCCESS").exists():
                raise RuntimeError("Render success/marker disagreement: " + str(run))
            manifests[run] = m
    else:
        captured, manifests, parent, supervisor = take_over(
            args.matrix_pid, args.supervisor_pid, runs
        )
    state.update(
        status="running",
        old_dispatcher=parent,
        old_supervisor=supervisor,
        adopted=[{"pid": c["pid"], "run": str(r), "phase": p} for c, r, p in captured],
    )
    try:
        adapter.write_json(state_path, state)
    except Exception:
        if args.matrix_pid:
            os.kill(args.matrix_pid, signal.SIGCONT)
        raise
    print(
        "TAKEOVER_READY",
        len(captured),
        "live children retained; frozen sources untouched",
        flush=True,
    )
    states = {r: stage(m) for r, m in manifests.items()}
    deferred = []
    if args.defer_exhausted_infrastructure:
        for run, m in manifests.items():
            phase = states[run]
            attempts = m.get(
                "attempts" if phase == "generate" else phase + "_attempts", []
            )
            if m.get("failure_class") == "infrastructure" and len(attempts) >= 3:
                states[run] = "deferred_infrastructure"
                deferred.append(str(run))
    state["deferred_exhausted_infrastructure"] = deferred
    active, metric_jobs, adopted = {}, {}, set()
    metrics_done, retired = {}, bool(args.resume_id)
    # Reuse only a completed domain whose independently audited source files
    # still match. Do not rerun the already completed indoor GPU evaluation.
    if args.resume_id:
        for domain in ("indoor", "urban"):
            audit_path = (
                ROOT / "results/gpt6_astra" / ("chain_audit_" + domain + ".json")
            )
            if not audit_path.exists():
                continue
            report = json.loads(audit_path.read_text())
            folder = ROOT / "results/gpt6_astra/formal" / domain
            if report.get("status") != "automatic_chain_passed" or not all(
                states[r] in ("valid", "quality")
                for r in runs
                if runs[r][0]["domain"] == domain
            ):
                raise RuntimeError("Existing completed-domain audit is not reusable")
            for filename, expected_hash in report["summary_sources_sha256"].items():
                if adapter.digest(folder / filename) != expected_hash:
                    raise RuntimeError("Audited metric output changed: " + filename)
            full = json.loads((folder / "table2_full.json").read_text())
            keys = (
                "qalign",
                "clipiqa_plus",
                "consistency_3d",
                "appearance_diversity_itt",
                "layout_diversity_itt",
            )
            metrics_done[domain] = {k: full["metrics"][k]["mean"] for k in keys}
            state["domains"][domain] = {
                "status": "automatic_metrics_complete",
                "values": metrics_done[domain],
                "reused_audit_sha256": adapter.digest(audit_path),
            }
    pool = ThreadPoolExecutor(max_workers=48)
    try:
        for child, run, phase in captured:
            gpu = (
                manifests[run].get("render_attempts", [{}])[-1].get("gpu")
                if phase == "render"
                else None
            )
            future = pool.submit(adopt_child, child, run, phase, args.matrix_pid)
            active[future] = (run, phase, gpu, True)
            adopted.add(future)
        last_update = 0
        while True:
            # These exact runs are never scheduled here. A separately authorized
            # recovery may complete them while other work proceeds; import only
            # terminal results with unchanged generation/renderer provenance.
            for name in list(deferred):
                run = Path(name)
                m = json.loads((run / "run_manifest.json").read_text())
                if not m.get("authorized_extra_render_attempt"):
                    continue
                if not (
                    (m.get("render_success") and (run / "SUCCESS").exists())
                    or m.get("failure_class") == "quality"
                ):
                    continue
                if m.get("renderer_sha256") != lock["files_sha256"][
                    "methods/gpt/tools/blender_render_gpt.py"
                ] or adapter.digest(run / "scene/generated.py") != m.get(
                    "generated_code_sha256"
                ):
                    raise RuntimeError("External recovery provenance mismatch")
                manifests[run], states[run] = m, stage(m)
                deferred.remove(name)
                state.setdefault("authorized_recoveries_observed", []).append(name)
            for future in list(active):
                if not future.done():
                    continue
                run, phase, gpu, was_adopted = active.pop(future)
                try:
                    m = future.result()
                    manifests[run] = m
                    states[run] = stage(m)
                    attempts = m.get(
                        "attempts" if phase == "generate" else phase + "_attempts", []
                    )
                    bad = m.get("failure_class")
                    if (
                        bad == "access_blocked"
                        or m.get("acceleration_setup_error")
                        or (
                            bad == "infrastructure"
                            and (not was_adopted or len(attempts) >= 3)
                        )
                    ):
                        raise RuntimeError("Unresolved " + str(bad) + ": " + str(run))
                except Exception as error:
                    state["errors"].append(repr(error))
                    states[run] = "infrastructure"
                adopted.discard(future)
            if not adopted and not retired:
                remaining = children(parent["pid"])
                if any(c["state"] != "Z" for c in remaining):
                    raise RuntimeError(
                        "Refusing retirement: an original child is still live; old parent remains paused"
                    )
                for original in (supervisor, parent):
                    current = proc(original["pid"])
                    if current and current["birth"] == original["birth"]:
                        os.kill(original["pid"], signal.SIGTERM)
                        if current["state"] in ("T", "t"):
                            os.kill(original["pid"], signal.SIGCONT)
                retired = True
                state["old_dispatcher_retired_at_utc"] = adapter.utc()
                print(
                    "OLD_WORKFLOW_RETIRED after all adopted children finalized",
                    flush=True,
                )
            for domain, (future, gpu) in list(metric_jobs.items()):
                if future.done():
                    del metric_jobs[domain]
                    try:
                        metrics_done[domain] = future.result()
                        state["domains"][domain] = {
                            "status": "automatic_metrics_complete",
                            "values": metrics_done[domain],
                        }
                    except Exception as error:
                        state["errors"].append(repr(error))
                        state["domains"][domain] = {
                            "status": "error",
                            "error": repr(error),
                        }
            if state["errors"]:
                if not active and not metric_jobs:
                    break
            else:
                busy = {info[0] for info in active.values()}
                counts = Counter(info[1] for info in active.values())
                gpu_counts = Counter(
                    info[2] for info in active.values() if info[1] == "render"
                )
                free = gpu_free()
                # Finished domains begin unchanged metrics immediately, overlapping
                # the other domain's generation/build instead of waiting for 200.
                for domain in ("indoor", "urban"):
                    if domain in metric_jobs or domain in metrics_done:
                        continue
                    if all(
                        states[r] in ("valid", "quality")
                        for r in runs
                        if runs[r][0]["domain"] == domain
                    ):
                        occupied = {g for _, g in metric_jobs.values()}
                        choices = [
                            g for g in free if free[g] >= 18432 and g not in occupied
                        ]
                        if choices:
                            gpu = max(
                                choices, key=lambda g: (gpu_counts[g] == 0, free[g])
                            )
                            metric_jobs[domain] = (
                                pool.submit(domain_metrics, domain, gpu, output),
                                gpu,
                            )
                            state["domains"][domain] = {"status": "running", "gpu": gpu}
                for run, (spec, seed) in runs.items():
                    phase = states[run]
                    if run in busy or phase in (
                        "valid",
                        "quality",
                        "deferred_infrastructure",
                    ):
                        continue
                    gpu = None
                    if phase in ("generate", "build"):
                        limit = (
                            args.generators if phase == "generate" else args.builders
                        )
                        if counts[phase] >= limit:
                            continue
                    elif phase == "render":
                        metric_gpus = {g for _, g in metric_jobs.values()}
                        choices = [
                            g
                            for g in free
                            if free[g] >= (18432 if g in metric_gpus else 8192)
                            and gpu_counts[g] < args.render_slots
                        ]
                        if not choices:
                            continue
                        gpu = max(
                            choices,
                            key=lambda g: (
                                g not in metric_gpus,
                                free[g] / (gpu_counts[g] + 1),
                            ),
                        )
                        gpu_counts[gpu] += 1
                        free[
                            gpu
                        ] -= 4096  # Conservative launch reservation; actual original GPU gate also runs.
                    else:
                        raise RuntimeError("Unexpected stage: " + phase)
                    active[
                        pool.submit(
                            matrix.task, spec, seed, ROOT / "data/table2", gpu, phase
                        )
                    ] = (run, phase, gpu, False)
                    counts[phase] += 1
            if time.time() - last_update > 50:
                state.update(
                    updated_at_utc=adapter.utc(),
                    status="draining_after_error" if state["errors"] else "running",
                    counts=dict(Counter(states.values())),
                    active=dict(Counter(info[1] for info in active.values())),
                    domain_counts={
                        d: dict(
                            Counter(
                                states[r] for r in runs if runs[r][0]["domain"] == d
                            )
                        )
                        for d in ("indoor", "urban")
                    },
                )
                adapter.write_json(state_path, state)
                print(
                    json.dumps(
                        {
                            k: state[k]
                            for k in (
                                "updated_at_utc",
                                "status",
                                "counts",
                                "active",
                                "domain_counts",
                            )
                        }
                    ),
                    flush=True,
                )
                last_update = time.time()
            if (
                not active
                and not metric_jobs
                and all(
                    s in ("valid", "quality", "deferred_infrastructure")
                    for s in states.values()
                )
            ):
                eligible = [
                    d
                    for d in ("indoor", "urban")
                    if all(
                        states[r] in ("valid", "quality")
                        for r in runs
                        if runs[r][0]["domain"] == d
                    )
                ]
                if all(d in metrics_done for d in eligible):
                    break
            time.sleep(2)
        state.update(
            status="paused_error"
            if state["errors"]
            else "awaiting_infrastructure_authorization"
            if deferred
            else "awaiting_real_ratings_and_table_review",
            updated_at_utc=adapter.utc(),
            counts=dict(Counter(states.values())),
        )
        adapter.write_json(state_path, state)
        if state["errors"]:
            raise RuntimeError(str(state["errors"]))
    finally:
        pool.shutdown(wait=True)
        guard.close()


if __name__ == "__main__":
    main()

"""Retire only the old Astra pilot scheduler while preserving running builds."""

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

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import json
import os
from pathlib import Path
import signal
import sys
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
sys.path.insert(0, str(ROOT))
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.adapter import digest


def process(pid):
    directory = Path("/proc") / str(pid)
    try:
        text = (directory / "stat").read_text()
        fields = text[text.rfind(")") + 2 :].split()
        return {
            "pid": pid,
            "state": fields[0],
            "ppid": int(fields[1]),
            "pgid": int(fields[2]),
            "wait_status": int(fields[49]),
            "uid": directory.stat().st_uid,
            "command": (directory / "cmdline")
            .read_bytes()
            .decode()
            .rstrip("\0")
            .split("\0"),
        }
    except FileNotFoundError:
        return None


def inspect_old(parent_pid=None):
    processes = [
        process(int(p.name)) for p in Path("/proc").iterdir() if p.name.isdigit()
    ]
    processes = [p for p in processes if p]
    parents = [
        p
        for p in processes
        if p["uid"] == os.getuid()
        and p["pid"] != os.getpid()
        and any(q.endswith("methods/gpt/run.py") for q in p["command"])
        and (
            (
                parent_pid is not None
                and p["pid"] == parent_pid
                and "--complete-after-pilot" not in p["command"]
            )
            or (
                parent_pid is None
                and "--refresh-pilot-build-budget" in p["command"]
                and "--refresh-pilot-renderer" in p["command"]
                and "--pilot" in p["command"]
                and "--adopt-pilot-workers" not in p["command"]
            )
        )
    ]
    if len(parents) != 1:
        raise RuntimeError(
            "Expected exactly one original Astra pilot scheduler, found "
            + str(len(parents))
        )
    parent = parents[0]
    children = [p for p in processes if p["ppid"] == parent["pid"]]
    for child in children:
        command = child["command"]
        if (
            not command
            or Path(command[0]).name != "bwrap"
            or child["pgid"] != child["pid"]
        ):
            raise RuntimeError("Unexpected original scheduler child; refuse migration")
        if "--run-dir" not in command or command[-2:] != ["--phase", "build"]:
            raise RuntimeError("Only CPU build children may be adopted")
        run = Path(command[command.index("--run-dir") + 1]).resolve()
        if not run.is_relative_to(ROOT / "data/gpt6_astra_pilot"):
            raise RuntimeError("Child is outside Astra pilot")
        child["run_dir"] = str(run)
    return {"parent": parent, "children": children, "captured_at_utc": utc()}


def adopt(gpus, parent_pid=None, build_timeout=None):
    from baselines.methods.gpt.run import render_run
    from baselines.methods.gpt.tools.audit_gpt import audit

    snapshot = inspect_old(parent_pid)
    parent = snapshot["parent"]["pid"]
    report_path = (
        ROOT
        / "results/gpt6_astra"
        / (
            "scheduler_migration.json"
            if parent_pid is None
            else f"scheduler_migration_{parent_pid}.json"
        )
    )
    if report_path.exists():
        raise RuntimeError(
            "Existing migration record requires review; do not start a duplicate"
        )
    snapshot.update(
        status="pausing_old_dispatcher",
        reason="Preserve active CPU builds; GPU sharing by remaining memory",
        revised_build_timeout_s=build_timeout,
    )
    write_json(report_path, snapshot)
    os.kill(parent, signal.SIGSTOP)
    time.sleep(0.1)
    snapshot.update(inspect_old(parent_pid), status="adopting_cpu_builds")
    write_json(report_path, snapshot)
    print("OLD_DISPATCHER_PAUSED; CPU build children continue running", flush=True)
    children = snapshot["children"]
    active = {Path(c["run_dir"]) for c in children}
    runs = []
    for row in audit(ROOT / "data/gpt6_astra_pilot", True)["records"]:
        run = (
            ROOT
            / f'data/gpt6_astra_pilot/{row["domain"]}/gpt6_astra/{row["spec_id"]}/seed_{row["seed"]}'
        )
        if row["status"] == "building" and run not in active:
            raise RuntimeError(
                "A build was between process exit and manifest update; inspect before proceeding"
            )
        if run not in active and row["status"] not in {"valid", "quality"}:
            runs.append(run)

    def finish_build(child):
        run = Path(child["run_dir"])
        path = run / "run_manifest.json"
        manifest = json.loads(path.read_text())
        attempt = manifest["build_attempts"][-1]
        if attempt.get("ended_at_utc") or manifest.get("build_success"):
            raise RuntimeError("Build manifest changed before adoption")
        if build_timeout is not None:
            if not attempt["timeout_limit_s"] <= build_timeout <= 21600:
                raise RuntimeError(
                    "Only a bounded extension of the original pilot CPU deadline is allowed"
                )
            attempt["original_timeout_limit_s"] = attempt["timeout_limit_s"]
            attempt["timeout_limit_s"] = build_timeout
            attempt["timeout_revised_at_utc"] = utc()
            attempt[
                "timeout_revision_reason"
            ] = "Pilot evidence showed finite Blender operator updates exceed 7200s; extend uniformly without restarting live builds"
            write_json(path, manifest)
        deadline = (
            datetime.fromisoformat(attempt["started_at_utc"]).timestamp()
            + attempt["timeout_limit_s"]
        )
        timed_out = False
        terminated_at = None
        while True:
            current = process(child["pid"])
            if current is None:
                raise RuntimeError(
                    "Adopted build disappeared before exit status was captured"
                )
            if current["state"] == "Z":
                exit_code = os.waitstatus_to_exitcode(current["wait_status"])
                break
            if time.time() > deadline and not timed_out:
                os.killpg(child["pid"], signal.SIGTERM)
                timed_out = True
                terminated_at = time.time()
            if timed_out and time.time() - terminated_at > 10:
                os.killpg(child["pid"], signal.SIGKILL)
            time.sleep(2)
        attempt.update(
            exit_code=exit_code,
            timeout=timed_out,
            ended_at_utc=utc(),
            adopted_from_dispatcher_pid=parent,
            adopted_child_pid=child["pid"],
        )
        logs = run / f'logs/build_{attempt["index"]:02d}'
        combined = (logs / "stdout.log").read_text() + (logs / "stderr.log").read_text()
        success = (
            exit_code == 0 and not timed_out and "ASTRA_BUILD_COMPLETE" in combined
        )
        if success:
            if not all(
                (run / "scene" / name).exists()
                for name in ["scene.blend", "geometry.json"]
            ):
                raise RuntimeError("Successful build lacks its artifacts")
            if digest(run / "scene/generated.py") != manifest["generated_code_sha256"]:
                raise RuntimeError("Generated code changed during build")
            manifest.update(build_success=True, failure_class=None, failure_reason=None)
        else:
            resource_error = any(
                token in combined.lower()
                for token in ["out of memory", "cannot allocate memory", "memoryerror"]
            )
            quality = (
                not resource_error and exit_code == 11 and "generated.py" in combined
            )
            manifest.update(
                failure_class="quality" if quality else "infrastructure",
                failure_reason="Adopted build failed; original code and attempt preserved",
            )
        write_json(path, manifest)
        print(
            f"ADOPTED_BUILD_END {run.parent.name} {run.name} success={success} exit={exit_code}",
            flush=True,
        )
        return run

    # Build-watching threads do not reserve GPUs; ready renders and the one
    # previously queued CPU build can run immediately on the shared-memory policy.
    import queue

    available = queue.Queue()
    for gpu in gpus:
        available.put(gpu)

    def render(run):
        gpu = available.get()
        try:
            print(f"MIGRATION_RUN {run.parent.name} {run.name} gpu={gpu}", flush=True)
            result = render_run(run, gpu)
            if result.get("failure_class") in {"infrastructure", "access_blocked"}:
                raise RuntimeError(
                    "Unresolved run after scheduler migration: " + str(run)
                )
            return result
        finally:
            available.put(gpu)

    with ThreadPoolExecutor(max_workers=len(gpus)) as workers, ThreadPoolExecutor(
        max_workers=max(1, len(children))
    ) as watchers:
        futures = [
            workers.submit(render, run)
            for run in sorted(
                runs, key=lambda r: not (r / "scene/scene.blend").exists()
            )
        ]
        observed = [watchers.submit(finish_build, child) for child in children]
        for future in as_completed(observed):
            futures.append(workers.submit(render, future.result()))
        # All original CPU children have ended and their real status was saved.
        # Killing the paused old dispatcher now cannot discard a live build.
        os.kill(parent, signal.SIGTERM)
        os.kill(parent, signal.SIGCONT)
        snapshot.update(status="old_dispatcher_retired", retired_at_utc=utc())
        write_json(report_path, snapshot)
        for future in as_completed(futures):
            future.result()
    report = audit(ROOT / "data/gpt6_astra_pilot", True)
    snapshot.update(
        status="complete", completed_at_utc=utc(), pilot_counts=report["counts"]
    )
    write_json(report_path, snapshot)
    print(
        json.dumps({"migration": "complete", "pilot_counts": report["counts"]}),
        flush=True,
    )

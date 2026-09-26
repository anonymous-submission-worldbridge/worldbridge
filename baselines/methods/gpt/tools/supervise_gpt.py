"""Continue the authorized Astra workflow; never fabricate subjective ratings."""

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

import json
import fcntl
from pathlib import Path
import subprocess
import sys
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.tools.audit_gpt import audit


def supervise(gpus, generators):
    output = ROOT / "results/gpt6_astra/workflow"
    output.mkdir(parents=True, exist_ok=True)
    guard = (output / "supervisor.lock").open("a")
    try:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        guard.close()
        raise RuntimeError("An Astra workflow supervisor is already running")
    state = {"started_at_utc": utc(), "status": "running", "stages": []}

    def update(stage, **kwargs):
        state.update(stage=stage, updated_at_utc=utc(), **kwargs)
        write_json(output / "state.json", state)
        print(json.dumps({k: v for k, v in state.items() if k != "stages"}), flush=True)

    def command(stage, args):
        update(stage)
        record = {
            "stage": stage,
            "command": list(map(str, args)),
            "started_at_utc": utc(),
        }
        state["stages"].append(record)
        log = output / (stage + "_" + utc().replace(":", "-") + ".log")
        record["log"] = str(log.relative_to(ROOT))
        write_json(output / "state.json", state)
        with log.open("w") as handle:
            completed = subprocess.run(
                record["command"],
                cwd=ROOT.parent,
                stdout=handle,
                stderr=subprocess.STDOUT,
            )
        record.update(exit_code=completed.returncode, ended_at_utc=utc())
        write_json(output / "state.json", state)
        if completed.returncode:
            raise RuntimeError(stage + " failed; see " + str(log))

    def shared_gpu(required=18432):
        while True:
            choices = []
            for gpu in gpus:
                result = subprocess.run(
                    [
                        "nvidia-smi",
                        f"--id={gpu}",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                free = int(result.stdout.strip())
                if free >= required:
                    choices.append((free, gpu))
            if choices:
                return max(choices)[1]
            update("waiting_for_sufficient_free_vram", required_mib=required)
            time.sleep(55)

    try:
        lock_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json"
        if not lock_path.exists():
            while True:
                report = audit(ROOT / "data/gpt6_astra_pilot", True)
                counts = report["counts"]
                update("waiting_for_pilot", pilot_counts=counts)
                if (
                    set(counts).issubset({"valid", "quality"})
                    and sum(counts.values()) == 20
                ):
                    break
                if any(counts.get(k, 0) for k in ["infrastructure", "access_blocked"]):
                    raise RuntimeError(
                        "Pilot has unresolved infrastructure/access errors; no formal work started"
                    )
                time.sleep(55)
            command(
                "freeze",
                [sys.executable, "-B", (ROOT / "methods/gpt/tools/freeze_gpt.py")],
            )
        lock = json.loads(lock_path.read_text())
        for relative, expected in lock["files_sha256"].items():
            if digest(ROOT / relative) != expected:
                raise RuntimeError("Frozen source changed: " + relative)
        command(
            "formal_matrix",
            [
                sys.executable,
                "-B",
                (ROOT / "methods/gpt/run.py"),
                "--domain",
                "both",
                "--data-root",
                ROOT / "data/table2",
                "--gpus",
                *gpus,
                "--generators",
                generators,
            ],
        )
        report = audit(ROOT / "data/table2", False)
        if (
            not set(report["counts"]).issubset({"valid", "quality"})
            or sum(report["counts"].values()) != 200
        ):
            raise RuntimeError("Formal matrix is not terminal")
        update("formal_matrix_validated", formal_counts=report["counts"])
        for domain in ["indoor", "urban"]:
            gpu = shared_gpu()
            command(
                "metrics_" + domain,
                [
                    sys.executable,
                    "-B",
                    (ROOT / "methods/gpt/evaluate.py"),
                    "--domain",
                    domain,
                    "--gpu",
                    gpu,
                    "--stages",
                    "iqa",
                    "semantics",
                    "consistency",
                    "diversity",
                ],
            )
            package = ROOT / "annotations/gpt6_astra" / domain
            if not package.exists():
                command(
                    "annotations_" + domain,
                    [
                        sys.executable,
                        "-B",
                        (ROOT / "methods/gpt/evaluate.py"),
                        "--domain",
                        domain,
                        "--gpu",
                        gpu,
                        "--stages",
                        "annotations",
                    ],
                )
            result_root = ROOT / "results/gpt6_astra/formal" / domain
            command(
                "aggregate_" + domain,
                [
                    sys.executable,
                    "-B",
                    (ROOT / "evaluation/visual/aggregate_generation.py"),
                    "--protocol",
                    (ROOT / "methods/gpt/protocol/generation/gpt6_astra.json"),
                    "--spec-file",
                    ROOT / f"protocol/generation/{domain}_specs.jsonl",
                    "--data-root",
                    ROOT / "data/table2",
                    "--results-root",
                    result_root,
                    "--method",
                    "gpt6_astra",
                    "--domain",
                    domain,
                ],
            )
            result = json.loads((result_root / "table2_full.json").read_text())
            automatic = [
                "qalign",
                "clipiqa_plus",
                "consistency_3d",
                "appearance_diversity_itt",
                "layout_diversity_itt",
            ]
            if any(result["metrics"][key]["status"] != "complete" for key in automatic):
                raise RuntimeError(
                    "Five automatic metric columns are not complete: " + domain
                )
        update(
            "automatic_metrics_complete",
            status="awaiting_ratings_and_table_review",
            note="Five automatic metrics and anonymous materials complete. No human or AI proxy ratings invented; the seven-column user task is not yet complete.",
        )
    except Exception as error:
        update(state.get("stage", "unknown"), status="paused_error", error=repr(error))
        raise
    finally:
        guard.close()

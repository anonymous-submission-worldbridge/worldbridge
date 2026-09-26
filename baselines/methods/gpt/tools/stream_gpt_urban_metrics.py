#!/usr/bin/env python3
"""Evaluate terminal Urban spec groups using unchanged frozen metric CLIs.

Never score an unfinished slot. Each group contains all four seeds of exact
frozen specs. Merge only after all 25 specs and all 100 slots are complete.
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
import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

BASE = _BASELINE_PROJECT_ROOT / "baselines"
sys.path[:0] = [str(BASE), str(BASE / "tools"), str((BASE / "methods"))]
import baselines.methods.gpt.adapter as adapter
from baselines.methods.gpt.tools.accelerate_gpt import verify_lock
from baselines.methods.gpt.tools.accelerate_gpt import gpu_free
from baselines.methods.gpt.evaluate import check_consistency_records

OUTPUT = BASE / "results/gpt6_astra/urban_stream_metrics_20260909"
PYTHON = BASE / "envs/worldscore/bin/python"
DATA = BASE / "data/table2"
leases = set()
lease_lock = threading.Lock()


def terminal(spec):
    for seed in range(4):
        run = DATA / "urban/gpt6_astra" / spec["spec_id"] / f"seed_{seed}"
        m = json.loads((run / "run_manifest.json").read_text())
        success = (run / "SUCCESS").exists()
        if success != bool(m.get("render_success")):
            raise RuntimeError("Manifest/marker disagreement")
        if not success and m.get("failure_class") != "quality":
            return False
        if (
            m.get("generation_success")
            and adapter.digest(run / "scene/generated.py") != m["generated_code_sha256"]
        ):
            raise RuntimeError("Generated code hash changed")
    return True


def acquire(stage):
    minimum = {"iqa": 18432, "semantics": 4096, "consistency": 8192, "diversity": 4096}[
        stage
    ]
    while True:
        with lease_lock:
            free = gpu_free()
            choices = [g for g in free if g not in leases and free[g] >= minimum]
            if choices:
                gpu = max(choices, key=free.get)
                leases.add(gpu)
                return gpu
        time.sleep(10)


def evaluate(folder, stage):
    verify_lock()
    selected = [
        json.loads(x) for x in (folder / "specs.jsonl").read_text().splitlines()
    ]
    if not all(terminal(s) for s in selected):
        raise RuntimeError("Refuse to evaluate incomplete spec")
    gpu = acquire(stage)
    try:
        env = dict(
            os.environ,
            CUDA_VISIBLE_DEVICES=str(gpu),
            TORCH_HOME=str(BASE / "cache/torch"),
            HF_HOME=str(BASE / "cache/huggingface"),
            HF_HUB_OFFLINE="1",
            TRANSFORMERS_OFFLINE="1",
            XDG_CACHE_HOME=str(BASE / "cache/xdg_metrics"),
            PYTHONDONTWRITEBYTECODE="1",
            PYTHONUNBUFFERED="1",
            TMPDIR=str(BASE / "tmp"),
        )
        common = [
            "--data-root",
            str(DATA),
            "--spec-file",
            str(folder / "specs.jsonl"),
            "--method",
            "gpt6_astra",
            "--domain",
            "urban",
        ]
        filenames = dict(
            iqa="iqa_per_scene.jsonl",
            consistency="consistency_per_scene.jsonl",
            diversity="diversity_per_spec.jsonl",
            semantics="semantic_model.json",
        )
        script = {
            "iqa": "eval_iqa.py",
            "consistency": "eval_worldscore.py",
            "diversity": "eval_diversity.py",
            "semantics": "generate_semantics.py",
        }[stage]
        command = [str(PYTHON), str((BASE / "evaluation/visual") / script), *common]
        if stage == "semantics":
            command += [
                "--device",
                "cuda",
                "--batch-size",
                "8",
                "--metadata-output",
                str(folder / filenames[stage]),
            ]
        elif stage == "consistency":
            env.pop("CUDA_VISIBLE_DEVICES", None)
            env["PYTHONPATH"] = str(BASE / "work/metaurban/worldscore_abi")
            command += ["--gpu", str(gpu), "--output", str(folder / filenames[stage])]
        else:
            command += ["--device", "cuda", "--output", str(folder / filenames[stage])]
        record = dict(
            stage=stage,
            gpu=gpu,
            command=command,
            started_at_utc=adapter.utc(),
            evaluator_sha256=adapter.digest((BASE / "evaluation/visual") / script),
            subset_spec_sha256=adapter.digest(folder / "specs.jsonl"),
            frozen_spec_source_sha256=adapter.digest(
                (BASE / "protocol/generation/urban_specs.jsonl")
            ),
        )
        adapter.write_json(folder / f"{stage}_execution.json", record)
        print(
            "METRIC_START",
            folder.name,
            stage,
            "gpu",
            gpu,
            "specs",
            len(selected),
            flush=True,
        )
        with (folder / f"{stage}.log").open("w") as log:
            result = subprocess.run(
                command, cwd=BASE.parent, env=env, stdout=log, stderr=subprocess.STDOUT
            )
        record.update(exit_code=result.returncode, ended_at_utc=adapter.utc())
        adapter.write_json(folder / f"{stage}_execution.json", record)
        if result.returncode:
            raise RuntimeError(f"{folder.name}/{stage} failed; inspect its log")
        if stage != "semantics":
            rows = [
                json.loads(x)
                for x in (folder / filenames[stage]).read_text().splitlines()
            ]
            expected = (
                {s["spec_id"] for s in selected}
                if stage == "diversity"
                else {(s["spec_id"], seed) for s in selected for seed in range(4)}
            )
            actual = (
                {r["spec_id"] for r in rows}
                if stage == "diversity"
                else {(r["spec_id"], r["logical_seed"]) for r in rows}
            )
            if (
                len(rows) != len(expected)
                or actual != expected
                or any(
                    r["method"] != "gpt6_astra" or r["domain"] != "urban" for r in rows
                )
            ):
                raise RuntimeError("Missing/duplicate/foreign metric records")
            if stage == "consistency":
                check_consistency_records(rows, DATA, "urban")
        print("METRIC_DONE", folder.name, stage, flush=True)
        return record
    finally:
        with lease_lock:
            leases.remove(gpu)


def semantics_and_diversity(folder):
    return [evaluate(folder, "semantics"), evaluate(folder, "diversity")]


def merge(specs, batches):
    verify_lock()
    if not all(terminal(s) for s in specs):
        raise RuntimeError("Refuse partial final matrix")
    final = BASE / "results/gpt6_astra/formal/urban"
    final.mkdir(parents=True, exist_ok=True)
    for name in (
        "iqa_per_scene.jsonl",
        "consistency_per_scene.jsonl",
        "diversity_per_spec.jsonl",
    ):
        rows = [
            json.loads(x)
            for folder in batches
            for x in (folder / name).read_text().splitlines()
        ]
        key = (
            (lambda r: r["spec_id"])
            if name.startswith("diversity")
            else (lambda r: (r["spec_id"], r["logical_seed"]))
        )
        indexed = {key(r): r for r in rows}
        order = (
            [s["spec_id"] for s in specs]
            if name.startswith("diversity")
            else [(s["spec_id"], seed) for s in specs for seed in range(4)]
        )
        if len(rows) != len(order) or set(indexed) != set(order):
            raise RuntimeError("Final merge missing or duplicate slots")
        target = final / name
        if target.exists():
            raise RuntimeError("Refuse overwrite existing formal metrics")
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_text(
            "".join(json.dumps(indexed[k], ensure_ascii=False) + "\n" for k in order)
        )
        tmp.replace(target)
    models = [
        json.loads((folder / "semantic_model.json").read_text()) for folder in batches
    ]
    # Metadata may include batch-specific counts; retain every original instead
    # of inventing a single evaluator invocation.
    adapter.write_json(
        final / "streaming_execution.json",
        dict(
            source="unchanged_frozen_evaluators_terminal_spec_groups",
            batches=[str(f.relative_to(BASE)) for f in batches],
            all_specs=25,
            all_runs=100,
            semantic_metadata=models,
            completed_at_utc=adapter.utc(),
        ),
    )
    command = [
        sys.executable,
        "-B",
        str((BASE / "evaluation/visual/aggregate_generation.py")),
        "--protocol",
        str((BASE / "methods/gpt/protocol/generation/gpt6_astra.json")),
        "--spec-file",
        str((BASE / "protocol/generation/urban_specs.jsonl")),
        "--data-root",
        str(DATA),
        "--results-root",
        str(final),
        "--method",
        "gpt6_astra",
        "--domain",
        "urban",
    ]
    subprocess.run(command, cwd=BASE.parent, check=True)


def main():
    verify_lock()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    guard = (OUTPUT / "controller.lock").open("a")
    fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (OUTPUT / "state.json").exists():
        raise RuntimeError("Existing stream execution; no implicit restart")
    specs = [
        json.loads(x)
        for x in ((BASE / "protocol/generation/urban_specs.jsonl"))
        .read_text()
        .splitlines()
    ]
    assigned, batches, jobs, completed, errors = set(), [], {}, set(), []
    state = dict(
        started_at_utc=adapter.utc(),
        status="running",
        controller_sha256=adapter.digest(__file__),
        strategy="Exact frozen spec subsets; full four-seed terminal groups only; original evaluators unchanged",
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        while True:
            for future in list(jobs):
                if future.done():
                    label = jobs.pop(future)
                    try:
                        future.result()
                        completed.add(label)
                    except Exception as error:
                        errors.append(str(error))
            if not jobs and not errors and len(assigned) < 25:
                ready = [
                    s for s in specs if s["spec_id"] not in assigned and terminal(s)
                ]
                if len(ready) >= 3 or ready and len(assigned) + len(ready) == 25:
                    folder = OUTPUT / f"batch_{len(batches)+1:02d}"
                    folder.mkdir()
                    (folder / "specs.jsonl").write_text(
                        "".join(json.dumps(s, ensure_ascii=False) + "\n" for s in ready)
                    )
                    batches.append(folder)
                    assigned.update(s["spec_id"] for s in ready)
                    for stage in ("iqa", "consistency", "semantics_diversity"):
                        future = (
                            pool.submit(semantics_and_diversity, folder)
                            if stage == "semantics_diversity"
                            else pool.submit(evaluate, folder, stage)
                        )
                        jobs[future] = folder.name + "/" + stage
            state.update(
                updated_at_utc=adapter.utc(),
                assigned_specs=len(assigned),
                batches=len(batches),
                active=list(jobs.values()),
                completed=sorted(completed),
                errors=errors,
            )
            if errors and not jobs:
                state["status"] = "paused_error"
            elif len(assigned) == 25 and not jobs:
                merge(specs, batches)
                state["status"] = "automatic_metrics_complete"
            adapter.write_json(OUTPUT / "state.json", state)
            print(json.dumps(state, ensure_ascii=False), flush=True)
            if state["status"] != "running":
                break
            time.sleep(20)
    guard.close()


if __name__ == "__main__":
    main()

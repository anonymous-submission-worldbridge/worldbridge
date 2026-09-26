"""Expand GPU metric QA to the currently valid pilot, without formal aggregation."""

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
import math
from pathlib import Path
import subprocess
import sys

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json
from baselines.methods.gpt.tools.audit_gpt import audit


def verify_metrics(row):
    sys.path.insert(0, str(ROOT))
    from baselines.methods.gpt.evaluate import check_consistency_records

    domain, spec, seed = row["domain"], row["spec_id"], row["logical_seed"]
    result = ROOT / f"results/gpt6_astra/smoke/{domain}/{spec}_seed_{seed}"
    loaded = {}
    for stage in ["iqa", "consistency"]:
        records = [
            json.loads(line)
            for line in (result / f"{stage}_per_scene.jsonl").read_text().splitlines()
            if line
        ]
        if len(records) != 1 or (
            records[0].get("method"),
            records[0].get("domain"),
            records[0].get("spec_id"),
            records[0].get("logical_seed"),
        ) != ("gpt6_astra", domain, spec, seed):
            raise RuntimeError(
                "Missing, duplicate, or foreign cached pilot metric: " + str(result)
            )
        loaded[stage] = records
    iqa = loaded["iqa"][0]
    if (
        not iqa.get("success")
        or len(iqa.get("views", [])) != 8
        or not all(math.isfinite(float(iqa[k])) for k in ["qalign", "clipiqa_plus"])
    ):
        raise RuntimeError("Invalid IQA result for valid pilot render")
    check_consistency_records(
        loaded["consistency"], ROOT / "data/gpt6_astra_pilot", domain
    )
    run = ROOT / f"data/gpt6_astra_pilot/{domain}/gpt6_astra/{spec}/seed_{seed}"
    if len(list((run / "renders/semantic_pred").glob("semantic_*.png"))) != 8:
        raise RuntimeError("Pilot semantic outputs are incomplete")


def validate_completed(gpus):
    output = ROOT / "results/gpt6_astra/expanded_pilot_metrics"
    output.mkdir(parents=True, exist_ok=True)
    with (output / "guard.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX | fcntl.LOCK_NB)
        rows = [
            r
            for r in audit(ROOT / "data/gpt6_astra_pilot", True)["records"]
            if r["status"] == "valid"
        ]
        report = {
            "started_at_utc": utc(),
            "formal": False,
            "status": "running",
            "selected_valid_runs": len(rows),
            "records": [],
        }
        write_json(output / "report.json", report)

        def lane(index, gpu):
            records = []
            for row in rows[index :: len(gpus)]:
                domain, spec, seed = row["domain"], row["spec_id"], row["seed"]
                result = ROOT / f"results/gpt6_astra/smoke/{domain}/{spec}_seed_{seed}"
                stages = [
                    name
                    for name, filename in [
                        ("iqa", "iqa_per_scene.jsonl"),
                        ("semantics", "semantic_model.json"),
                        ("consistency", "consistency_per_scene.jsonl"),
                    ]
                    if not (result / filename).exists()
                ]
                record = {
                    "domain": domain,
                    "spec_id": spec,
                    "logical_seed": seed,
                    "stages": stages,
                    "gpu": gpu,
                }
                if stages:
                    command = [
                        sys.executable,
                        "-B",
                        str((ROOT / "methods/gpt/evaluate.py")),
                        "--domain",
                        domain,
                        "--data-root",
                        str(ROOT / "data/gpt6_astra_pilot"),
                        "--smoke-spec-id",
                        spec,
                        "--seed",
                        str(seed),
                        "--gpu",
                        str(gpu),
                        "--stages",
                        *stages,
                    ]
                    log = output / f"{spec}_seed_{seed}.log"
                    print(
                        f"EXPANDED_QA_START {spec} seed={seed} gpu={gpu} stages={stages}",
                        flush=True,
                    )
                    with log.open("w") as handle:
                        completed = subprocess.run(
                            command,
                            cwd=ROOT.parent,
                            stdout=handle,
                            stderr=subprocess.STDOUT,
                        )
                    record.update(
                        exit_code=completed.returncode, log=str(log.relative_to(ROOT))
                    )
                else:
                    record.update(exit_code=0, reused_existing=True)
                if record["exit_code"] == 0:
                    try:
                        verify_metrics(record)
                    except Exception as error:
                        record.update(exit_code=1, validation_error=repr(error))
                record["ended_at_utc"] = utc()
                write_json(output / f"{spec}_seed_{seed}.json", record)
                records.append(record)
                print(
                    f'EXPANDED_QA_END {spec} seed={seed} exit={record["exit_code"]}',
                    flush=True,
                )
                if record["exit_code"]:
                    break
            return records

        with ThreadPoolExecutor(max_workers=len(gpus)) as workers:
            futures = [workers.submit(lane, i, gpu) for i, gpu in enumerate(gpus)]
            for future in futures:
                report["records"].extend(future.result())
                write_json(output / "report.json", report)
        passed = len(report["records"]) == len(rows) and all(
            r["exit_code"] == 0 for r in report["records"]
        )
        report.update(
            status="complete" if passed else "needs_triage", ended_at_utc=utc()
        )
        write_json(output / "report.json", report)
        return 0 if passed else 1


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Read-only verification of completed pilot metric outputs"
    )
    parser.add_argument("--verify-existing", action="store_true", required=True)
    parser.parse_args()
    report = json.loads(
        (ROOT / "results/gpt6_astra/expanded_pilot_metrics/report.json").read_text()
    )
    if (
        report.get("status") != "complete"
        or len(report["records"]) != report["selected_valid_runs"]
    ):
        raise RuntimeError("Expanded pilot report is not complete")
    for row in report["records"]:
        verify_metrics(row)
    print(
        json.dumps(
            {
                "verified_valid_runs": len(report["records"]),
                "formal": False,
                "verified_at_utc": utc(),
            }
        )
    )

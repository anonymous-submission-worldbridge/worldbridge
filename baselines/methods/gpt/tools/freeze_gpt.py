"""Freeze this method only after its complete pilot and numerical checks pass."""

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

import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone
import subprocess

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def verify_inputs(hashes):
    if not hashes:
        raise RuntimeError("Sanity report has no input hashes; rerun the check")
    for relative, expected in hashes.items():
        path = (ROOT / relative).resolve()
        if (
            not path.is_relative_to(ROOT)
            or hashlib.sha256(path.read_bytes()).hexdigest() != expected
        ):
            raise RuntimeError("Sanity report uses obsolete inputs: " + relative)


def main():
    from baselines.methods.gpt.tools.audit_gpt import audit

    target = ROOT / "methods/gpt/protocol/generation/gpt6_astra.lock.json"
    if target.exists():
        raise RuntimeError("Formal lock already exists; do not overwrite it")
    report = audit(ROOT / "data/gpt6_astra_pilot", True)
    allowed = {"valid", "quality"}
    if (
        not set(report["counts"]).issubset(allowed)
        or sum(report["counts"].values()) != 20
    ):
        raise RuntimeError("Pilot is not complete: " + str(report["counts"]))
    expanded = ROOT / "results/gpt6_astra/expanded_pilot_metrics/report.json"
    if (
        expanded.exists()
        and json.loads(expanded.read_text()).get("status") != "complete"
    ):
        raise RuntimeError(
            "Expanded pilot metric QA is still running or requires triage"
        )
    if expanded.exists():
        from baselines.methods.gpt.tools.validate_gpt_pilot_metrics import (
            verify_metrics,
        )

        for row in json.loads(expanded.read_text())["records"]:
            verify_metrics(row)
    for domain in ["indoor", "urban"]:
        if (
            sum(
                row["status"] == "valid"
                for row in report["records"]
                if row["domain"] == domain
            )
            < 2
        ):
            raise RuntimeError(
                "Need at least two valid pilot scenes per domain to validate the pipeline"
            )
    numerical = json.loads(
        (ROOT / "results/gpt6_astra/smoke/numerical_sanity.json").read_text()
    )
    if not numerical["passed"]:
        raise RuntimeError("Numerical sanity has not passed")
    if (
        numerical.get("production_iqa_batch_size") != 1
        or numerical.get("batch8_approved_for_production") is not False
    ):
        raise RuntimeError("Only the validated production IQA batch size 1 is allowed")
    verify_inputs(numerical.get("images_sha256"))
    for domain, spec in [
        ("indoor", "indoor_bedroom_00"),
        ("urban", "urban_residential_four_way_00"),
    ]:
        path = (
            ROOT
            / f"results/gpt6_astra/smoke/{domain}/{spec}_seed_0/consistency_per_scene.jsonl"
        )
        rows = [json.loads(l) for l in path.read_text().splitlines() if l]
        if len(rows) != 1 or not rows[0]["success"]:
            raise RuntimeError(
                "DROID-SLAM must track the fixed reference in each domain"
            )
        pair = json.loads(
            (ROOT / f"results/gpt6_astra/smoke/{domain}/{spec}_pair.json").read_text()
        )
        if (
            pair.get("formal") is not False
            or pair.get("logical_seeds") != [0, 1]
            or len(pair.get("views", [])) != 8
        ):
            raise RuntimeError("Missing real fixed two-seed diversity check: " + domain)
        for view in pair["views"]:
            verify_inputs(view.get("inputs_sha256"))
        if pair["appearance_valid_pair"] <= 0:
            raise RuntimeError(
                "Fixed independent logical seeds did not change appearance"
            )
    renderer = ROOT / "methods/gpt/tools/blender_render_gpt.py"
    renderer_hash = hashlib.sha256(renderer.read_bytes()).hexdigest()
    for row in report["records"]:
        run = (
            ROOT
            / f'data/gpt6_astra_pilot/{row["domain"]}/gpt6_astra/{row["spec_id"]}/seed_{row["seed"]}'
        )
        m = json.loads((run / "run_manifest.json").read_text())
        if m.get("build_success") and m.get("renderer_sha256") != renderer_hash:
            raise RuntimeError("Pilot contains an obsolete renderer: " + str(run))
    config_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra.json"
    config = json.loads(config_path.read_text())
    if config["status"] == "formal_frozen":
        raise RuntimeError("Already frozen; do not overwrite the formal lock")
    installed = subprocess.check_output(["codex", "--version"], text=True).strip()
    if installed != "codex-cli " + config["codex_version"]:
        raise RuntimeError("Codex version changed since pilot: " + installed)
    probes = [
        json.loads(p.read_text())
        for p in (ROOT / "results/gpt6_astra/codex_probe").glob("attempt_*/report.json")
    ]
    if not any(
        p.get("success")
        and p.get("model_requested") == "gpt-6-astra"
        and p.get("codex_version") == installed
        for p in probes
    ):
        raise RuntimeError(
            "No successful target-model probe for the installed Codex version"
        )
    config.update(
        status="formal_frozen",
        protocol_id="table2-gpt6-astra-v1",
        build_timeout_s=config.get("build_timeout_s", 7200),
        render_timeout_s=1800,
        build_threads=8,
        render_threads=8,
        iqa_batch_size=1,
        api_seed_note="Logical seeds index fresh independent Codex CLI sessions; no deterministic model seed is supported. Preserve the returned code for deterministic local reconstruction. CLI JSONL does not return a model snapshot identifier.",
    )
    config["notes"].append(
        "IQA production uses batch 1 only: repeat delta 0 on the fixed 10-image pilot. CLIP-IQA+ batch-8 diagnostic exceeded the suggested 1e-4 tolerance and is not approved. Q-Align batch 8 and CPU fp16 LLM validation were not supported/tested; do not claim all diagnostic modes passed."
    )
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    paths = [
        "methods/gpt/protocol/generation/gpt6_astra.json",
        "methods/gpt/protocol/generation/gpt6_astra_prompt.txt",
        "methods/gpt/protocol/generation/gpt6_astra_output.schema.json",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "protocol/generation/seeds.json",
        "protocol/generation/metrics.lock.json",
        "methods/gpt/adapter.py",
        "methods/gpt/run.py",
        "methods/gpt/evaluate.py",
        "methods/gpt/tools/blender_render_gpt.py",
        "methods/sceneweaver/tools/blender_render_sceneweaver.py",
        "methods/gpt/tools/gpt_camera.py",
        "evaluation/visual/eval_iqa.py",
        "evaluation/visual/eval_worldscore.py",
        "evaluation/visual/eval_diversity.py",
        "evaluation/visual/generate_semantics.py",
        "evaluation/visual/aggregate_generation.py",
        "evaluation/visual/import_human_ratings.py",
        "tools/make_annotation_package.py",
    ]
    paths += [
        "methods/gpt/tools/sanity_gpt_metrics.py",
        "methods/gpt/tools/pilot_pairs_gpt.py",
        "methods/gpt/tools/inspect_gpt_semantics.py",
        "methods/gpt/tools/freeze_gpt.py",
        "methods/gpt/tools/supervise_gpt.py",
        "methods/gpt/tools/migrate_gpt_scheduler.py",
        "methods/gpt/tools/audit_gpt.py",
        "methods/gpt/tools/validate_gpt_pilot_metrics.py",
    ]
    lock = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "gpt6_astra",
        "model": "gpt-6-astra",
        "transport": "codex_exec_saved_chatgpt_login",
        "codex_version": config["codex_version"],
        "pilot_counts": report["counts"],
        "files_sha256": {
            p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths
        },
    }
    with target.open("x") as handle:
        json.dump(lock, handle, indent=2)
        handle.write("\n")
    print(json.dumps(lock, indent=2))


if __name__ == "__main__":
    main()

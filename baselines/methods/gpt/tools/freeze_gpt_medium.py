#!/usr/bin/env python3
"""Freeze GPT-6 Astra Medium after its independent pilot and metric smoke tests."""
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


import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT / "tools"))
from baselines.methods.gpt.tools.audit_gpt_medium import audit


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_metric_smoke(domain: str, valid_slots: set[tuple[str, int]]) -> dict:
    root = ROOT / "results/gpt6_astra_medium/smoke" / domain
    candidates = []
    for directory in sorted(root.glob("*_seed_*")):
        try:
            seed = int(directory.name.rsplit("_seed_", 1)[1])
            spec_id = directory.name.rsplit("_seed_", 1)[0]
        except (IndexError, ValueError):
            continue
        if (spec_id, seed) not in valid_slots:
            continue
        iqa_path = directory / "iqa_per_scene.jsonl"
        consistency_path = directory / "consistency_per_scene.jsonl"
        semantics_path = directory / "semantic_model.json"
        execution_path = directory / "execution.json"
        if not all(
            path.exists()
            for path in (iqa_path, consistency_path, semantics_path, execution_path)
        ):
            continue
        iqa = [json.loads(line) for line in iqa_path.read_text().splitlines() if line]
        consistency = [
            json.loads(line)
            for line in consistency_path.read_text().splitlines()
            if line
        ]
        if len(iqa) != 1 or len(consistency) != 1:
            continue
        if not iqa[0].get("success") or not consistency[0].get("success"):
            continue
        execution = json.loads(execution_path.read_text())
        commands = [row.get("command", []) for row in execution.get("stages", [])]
        if not any(
            any(
                str(arg).endswith(
                    "evaluation/visual/eval_worldscore_gpt_high_frozen.py"
                )
                for arg in command
            )
            for command in commands
        ):
            continue
        candidates.append(
            {
                "spec_id": spec_id,
                "seed": seed,
                "iqa_sha256": digest(iqa_path),
                "consistency_sha256": digest(consistency_path),
                "semantics_sha256": digest(semantics_path),
            }
        )
    if not candidates:
        raise RuntimeError(
            "Need one successful IQA/semantic/WorldScore smoke run for " + domain
        )
    return candidates[0]


def main() -> int:
    config_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_medium.json"
    target = ROOT / "methods/gpt/protocol/generation/gpt6_astra_medium.lock.json"
    if target.exists():
        raise RuntimeError("Medium formal lock already exists; refusing overwrite")
    config = json.loads(config_path.read_text())
    if (
        config.get("status") != "pilot"
        or config.get("model") != "gpt-6-astra"
        or config.get("reasoning_effort") != "medium"
    ):
        raise RuntimeError("Medium pilot configuration drift")
    installed = subprocess.check_output(["codex", "--version"], text=True).strip()
    if installed != "codex-cli " + config["codex_version"]:
        raise RuntimeError("Codex CLI version changed after Medium pilot: " + installed)
    report = audit(ROOT / "data/gpt6_astra_medium_pilot", True)
    if (
        not set(report["counts"]).issubset({"valid", "quality"})
        or sum(report["counts"].values()) != 20
    ):
        raise RuntimeError("Medium pilot is not terminal: " + str(report["counts"]))
    renderer_hash = digest((ROOT / "methods/gpt/tools/blender_render_gpt.py"))
    valid_by_domain = {domain: set() for domain in ("indoor", "urban")}
    for row in report["records"]:
        run = (
            ROOT
            / "data/gpt6_astra_medium_pilot"
            / row["domain"]
            / "gpt6_astra_medium"
            / row["spec_id"]
            / f"seed_{row['seed']}"
        )
        manifest = json.loads((run / "run_manifest.json").read_text())
        if (
            manifest.get("method") != "gpt6_astra_medium"
            or manifest.get("reasoning_effort_requested") != "medium"
        ):
            raise RuntimeError("Pilot method identity mismatch: " + str(run))
        native = json.loads((run / "input/native_input.json").read_text())
        if (
            native.get("model") != "gpt-6-astra"
            or native.get("reasoning_effort") != "medium"
        ):
            raise RuntimeError("Pilot request configuration mismatch: " + str(run))
        command = manifest.get("attempts", [{}])[-1].get("command", [])
        if 'model_reasoning_effort="medium"' not in command:
            raise RuntimeError(
                "Pilot CLI command did not request medium effort: " + str(run)
            )
        if row["status"] == "valid":
            if manifest.get("renderer_sha256") != renderer_hash:
                raise RuntimeError("Pilot used stale shared High renderer: " + str(run))
            valid_by_domain[row["domain"]].add((row["spec_id"], row["seed"]))
    pair_evidence = {}
    for domain, slots in valid_by_domain.items():
        paired = sorted(
            spec_id
            for spec_id in {slot[0] for slot in slots}
            if (spec_id, 0) in slots and (spec_id, 1) in slots
        )
        if not paired:
            raise RuntimeError("Need a valid two-seed Medium pilot pair for " + domain)
        spec_id = paired[0]
        run0 = (
            ROOT
            / "data/gpt6_astra_medium_pilot"
            / domain
            / "gpt6_astra_medium"
            / spec_id
            / "seed_0/renders/anchors"
        )
        run1 = (
            ROOT
            / "data/gpt6_astra_medium_pilot"
            / domain
            / "gpt6_astra_medium"
            / spec_id
            / "seed_1/renders/anchors"
        )
        hashes0 = [digest(path) for path in sorted(run0.glob("rgb_*.png"))]
        hashes1 = [digest(path) for path in sorted(run1.glob("rgb_*.png"))]
        if len(hashes0) != 8 or len(hashes1) != 8 or hashes0 == hashes1:
            raise RuntimeError(
                "Independent Medium logical seeds did not change rendered appearance: "
                + domain
            )
        pair_evidence[domain] = {
            "spec_id": spec_id,
            "seed_0_anchor_hashes": hashes0,
            "seed_1_anchor_hashes": hashes1,
        }
    smoke = {
        domain: verify_metric_smoke(domain, valid_by_domain[domain])
        for domain in ("indoor", "urban")
    }
    config["status"] = "formal_frozen"
    config["frozen_at_utc"] = datetime.now(timezone.utc).isoformat()
    config["pilot_terminal_counts"] = report["counts"]
    config_path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n")
    paths = [
        "methods/gpt/protocol/generation/gpt6_astra_medium.json",
        "methods/gpt/protocol/generation/gpt6_astra_prompt.txt",
        "methods/gpt/protocol/generation/gpt6_astra_output.schema.json",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "protocol/generation/seeds.json",
        "protocol/generation/metrics.lock.json",
        "methods/gpt/adapter.py",
        "methods/gpt/adapter_medium.py",
        "methods/gpt/run_medium_matrix.py",
        "methods/gpt/run_medium_metrics.py",
        "methods/gpt/tools/blender_render_gpt.py",
        "methods/sceneweaver/tools/blender_render_sceneweaver.py",
        "methods/gpt/tools/gpt_camera.py",
        "methods/gpt/tools/audit_gpt_medium.py",
        "methods/gpt/tools/freeze_gpt_medium.py",
        "evaluation/visual/eval_iqa.py",
        "evaluation/visual/eval_worldscore_gpt_high_frozen.py",
        "evaluation/visual/eval_diversity.py",
        "evaluation/visual/generate_semantics.py",
        "evaluation/visual/aggregate_generation.py",
        "evaluation/visual/import_human_ratings.py",
        "methods/gpt/tools/make_annotation_package_gpt_high_frozen.py",
    ]
    lock = {
        "frozen_at_utc": config["frozen_at_utc"],
        "method": "gpt6_astra_medium",
        "model": "gpt-6-astra",
        "reasoning_effort": "medium",
        "transport": config["transport"],
        "codex_version": config["codex_version"],
        "reference_high_protocol_sha256": digest(
            (ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")
        ),
        "pilot_counts": report["counts"],
        "pair_evidence": pair_evidence,
        "metric_smoke": smoke,
        "files_sha256": {relative: digest(ROOT / relative) for relative in paths},
    }
    with target.open("x") as handle:
        json.dump(lock, handle, indent=2)
        handle.write("\n")
    print(json.dumps(lock, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

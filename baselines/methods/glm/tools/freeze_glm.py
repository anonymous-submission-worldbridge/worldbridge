#!/usr/bin/env python3
"""Freeze GLM-5.3 after its complete rendered and measured 5x2 pilot."""
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


from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT / "tools"))
from baselines.methods.glm.tools.audit_glm import audit


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line]


def main() -> int:
    target = ROOT / "methods/glm/protocol/generation/glm_5_3.lock.json"
    if target.exists():
        raise RuntimeError("Formal lock already exists; refusing to overwrite it")
    config_path = ROOT / "methods/glm/protocol/generation/glm_5_3.json"
    config = json.loads(config_path.read_text())
    report = audit(ROOT / "data/glm_5_3_pilot_v5_low_opencode", True)
    if sum(report["counts"].values()) != 20 or not set(report["counts"]).issubset(
        {"valid", "quality"}
    ):
        raise RuntimeError("Pilot is not terminal: " + str(report["counts"]))
    for domain in ("indoor", "urban"):
        domain_rows = [row for row in report["records"] if row["domain"] == domain]
        if sum(row["status"] == "valid" for row in domain_rows) < int(
            config["pilot_min_valid_per_domain"]
        ):
            raise RuntimeError("Too few valid pilot scenes to accept " + domain)
        output = ROOT / "results/glm_5_3/pilot" / domain
        wanted = {(row["spec_id"], row["seed"]) for row in domain_rows}
        for filename in ("iqa_per_scene.jsonl", "consistency_per_scene.jsonl"):
            rows = jsonl(output / filename)
            keys = {(row["spec_id"], row["logical_seed"]) for row in rows}
            if len(rows) != 10 or keys != wanted:
                raise RuntimeError("Incomplete pilot metric: " + str(output / filename))
        diversity = jsonl(output / "diversity_per_spec.jsonl")
        if len(diversity) != 5:
            raise RuntimeError("Incomplete pilot diversity: " + str(output))
    installed = subprocess.check_output(["opencode", "--version"], text=True).strip()
    if installed != config["opencode_version"]:
        raise RuntimeError("OpenCode version changed since pilot: " + installed)
    config.update(status="formal_frozen", protocol_id="table2-glm-5.3-v1")
    config_path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n")
    files = [
        "methods/glm/protocol/generation/glm_5_3.json",
        "methods/glm/protocol/generation/glm_5_3_prompt.txt",
        "methods/glm/protocol/generation/glm_5_3_output.schema.json",
        "methods/glm/protocol/generation/glm_5_3_rating_protocol.json",
        "methods/glm_flash/runtime/glm53_opencode/opencode.json",
        "protocol/generation/indoor_specs.jsonl",
        "protocol/generation/urban_specs.jsonl",
        "protocol/generation/seeds.json",
        "protocol/generation/metrics.lock.json",
        "methods/glm/adapter.py",
        "methods/glm/run.py",
        "methods/glm/evaluate.py",
        "methods/glm/tools/audit_glm.py",
        "methods/glm/tools/audit_glm_generation_chain.py",
        "methods/glm/tools/freeze_glm.py",
        "methods/glm/tools/make_glm_review_sheets.py",
        "methods/glm/tools/fill_simulated_glm_ratings.py",
        "methods/gpt/tools/blender_render_gpt.py",
        "methods/sceneweaver/tools/blender_render_sceneweaver.py",
        "methods/gpt/tools/gpt_camera.py",
        "evaluation/visual/eval_iqa.py",
        "evaluation/visual/eval_worldscore_gpt_high_frozen.py",
        "evaluation/visual/eval_diversity.py",
        "evaluation/visual/generate_semantics.py",
        "evaluation/visual/aggregate_generation.py",
        "evaluation/visual/import_human_ratings.py",
        "methods/gpt/tools/make_annotation_package_gpt_high_frozen.py",
    ]
    lock = {
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "method": "glm_5_3",
        "model": "glm-5.3",
        "transport": config["transport"],
        "opencode_version": config["opencode_version"],
        "thinking_mode": config["thinking_mode"],
        "reasoning_effort": config["reasoning_effort"],
        "pilot_counts": report["counts"],
        "files_sha256": {relative: digest(ROOT / relative) for relative in files},
    }
    with target.open("x") as handle:
        json.dump(lock, handle, indent=2)
        handle.write("\n")
    print(json.dumps(lock, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

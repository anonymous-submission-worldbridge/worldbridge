#!/usr/bin/env python3
"""Bounded, audit-visible recovery for GLM Coding Plan infrastructure pauses."""
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
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.glm_flash.adapter import METHOD
from baselines.methods.glm_flash.adapter import MODEL
from baselines.methods.glm_flash.adapter import PROVIDER
from baselines.methods.glm_flash.adapter import _opencode_environment
from baselines.methods.glm_flash.adapter import _parse_response
from baselines.methods.glm_flash.adapter import _verify_model_evidence
from baselines.methods.glm_flash.adapter import confined
from baselines.methods.glm_flash.adapter import digest
from baselines.methods.glm_flash.adapter import run_process
from baselines.methods.glm_flash.adapter import utc
from baselines.methods.glm_flash.adapter import write_json


AMENDMENT = (
    "methods/glm_flash/protocol/generation/glm53_flash_quota_recovery_20260917.json"
)


def verify_sources() -> None:
    lock = json.loads(
        (
            (ROOT / "methods/glm_flash/protocol/generation/glm53_flash.lock.json")
        ).read_text()
    )
    for relative, expected in lock["files_sha256"].items():
        if digest(ROOT / relative) != expected:
            raise RuntimeError("Frozen source changed: " + relative)
    amendment = json.loads((ROOT / AMENDMENT).read_text())
    if digest(ROOT / amendment["base_lock"]) != amendment["base_lock_sha256"]:
        raise RuntimeError("Base lock changed after quota amendment")
    if digest(__file__) != amendment["recovery_runner_sha256"]:
        raise RuntimeError("Quota recovery runner changed after amendment")


def identity(spec: dict) -> dict:
    return {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_template_sha256": digest(
            (ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt")
        ),
        "output_schema_sha256": digest(
            (ROOT / "methods/gpt/protocol/generation/gpt6_astra_output.schema.json")
        ),
        "protocol_sha256": digest(
            (ROOT / "methods/glm_flash/protocol/generation/glm53_flash.json")
        ),
        "opencode_config_sha256": digest(
            (ROOT / "methods/glm_flash/protocol/generation/glm53_flash_opencode.json")
        ),
        "adapter_sha256": digest((ROOT / "methods/glm_flash/adapter.py")),
    }


def initialize(spec: dict, seed: int, data_root: Path) -> tuple[Path, dict, str]:
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    frozen_identity = identity(spec)
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("identity") != frozen_identity:
            raise RuntimeError("Existing run has different frozen inputs: " + str(run))
    else:
        manifest = {
            "method": METHOD,
            "domain": spec["domain"],
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "method_seed": seed,
            "seed_supported": False,
            "identity": frozen_identity,
            "model_requested": MODEL,
            "model_returned": None,
            "model_identity_evidence": "OpenCode assistant metadata providerID/modelID",
            "auth_mode": "glm_coding_plan_opencode",
            "generation_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }
    amendments = manifest.setdefault("protocol_amendments", [])
    if AMENDMENT not in amendments:
        amendments.append(AMENDMENT)
    attempts = manifest.setdefault("attempts", [])
    if attempts and not attempts[-1].get("ended_at_utc"):
        attempts[-1].update(
            exit_code=-15,
            timeout=False,
            ended_at_utc=utc(),
            interruption="controlled_pause_after_explicit_coding_plan_usage_limit",
        )
        manifest.update(
            failure_class="infrastructure",
            failure_reason="Interrupted after explicit Coding Plan quota response; see amendment",
        )
    prompt = (
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt")).read_text()
        + "\n"
        + json.dumps(
            {"spec": spec, "logical_seed": seed},
            ensure_ascii=False,
        )
    )
    write_json(run / "input/spec.json", spec)
    write_json(
        run / "input/native_input.json",
        {
            "prompt": prompt,
            "model": MODEL,
            "seed": seed,
            "seed_supported": False,
            "transport": "opencode_openai_chat_completions",
            "thinking": {"type": "disabled"},
            "reasoning_effort": "none",
            "tools": [],
        },
    )
    write_json(manifest_path, manifest)
    return run, manifest, prompt


def run_one(spec: dict, seed: int, data_root: Path) -> dict:
    existing_run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    existing_manifest = existing_run / "run_manifest.json"
    if existing_manifest.exists():
        existing = json.loads(existing_manifest.read_text())
        if (
            existing.get("generation_success")
            or existing.get("failure_class") == "quality"
        ):
            return existing
    run, manifest, prompt = initialize(spec, seed, data_root)
    installed = subprocess.check_output(["opencode", "--version"], text=True).strip()
    if installed != "1.1.1":
        raise RuntimeError("OpenCode version drift: " + installed)
    index = len(manifest["attempts"]) + 1
    attempt_dir = run / f"logs/generation_{index:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    work = run / "work"
    work.mkdir(exist_ok=True)
    shutil.copyfile(
        (ROOT / "methods/glm_flash/protocol/generation/glm53_flash_opencode.json"),
        work / "opencode.json",
    )
    output = attempt_dir / "events.jsonl"
    command = [
        "opencode",
        "run",
        "--model",
        f"{PROVIDER}/{MODEL}",
        "--agent",
        "scene",
        "--format",
        "json",
        "--title",
        f"{spec['spec_id']}-seed-{seed}",
        prompt,
    ]
    attempt = {
        "index": index,
        "started_at_utc": utc(),
        "command": command[:-1] + ["<PROMPT_FROM_INPUT_NATIVE_INPUT_JSON>"],
        "endpoint": "https://open.bigmodel.cn/api/coding/paas/v4",
        "recovery_amendment": AMENDMENT,
    }
    manifest["attempts"].append(attempt)
    write_json(run / "run_manifest.json", manifest)
    environment = _opencode_environment()
    return_code, timed_out = run_process(
        command,
        work,
        output,
        attempt_dir / "stderr.log",
        json.loads(
            (
                (ROOT / "methods/glm_flash/protocol/generation/glm53_flash.json")
            ).read_text()
        )["generation_timeout_s"],
        env=environment,
    )
    attempt.update(exit_code=return_code, timeout=timed_out, ended_at_utc=utc())
    if return_code == 0 and output.exists():
        try:
            response, code = _parse_response(output)
            evidence = _verify_model_evidence(environment, response["session_id"])
            secret = environment["GLM53_API_KEY"]
            stderr = (attempt_dir / "stderr.log").read_text(errors="replace")
            if secret in output.read_text(errors="replace") or secret in stderr:
                raise ValueError("Secret appeared in persisted process output")
            attempt.update(
                session_id=response["session_id"],
                usage=response["usage"],
                event_types=response["event_types"],
                model_evidence={
                    "providerID": evidence["providerID"],
                    "modelID": evidence["modelID"],
                    "message_id": evidence["id"],
                },
            )
            manifest["model_returned"] = MODEL
            scene = run / "scene"
            scene.mkdir(exist_ok=True)
            (scene / "generated.py").write_text(code + "\n")
            manifest.update(
                generation_success=True,
                failure_class=None,
                failure_reason=None,
                generated_code_sha256=digest(scene / "generated.py"),
            )
        except (
            ValueError,
            KeyError,
            TypeError,
            SyntaxError,
            json.JSONDecodeError,
        ) as error:
            manifest.update(
                failure_class="quality",
                failure_reason=type(error).__name__ + ": " + str(error),
            )
    else:
        manifest.update(
            failure_class="infrastructure",
            failure_reason="Recovery OpenCode process failed or timed out without accepted assistant text",
        )
    manifest["ended_at_utc"] = utc()
    write_json(run / "run_manifest.json", manifest)
    return manifest


def tasks() -> list[tuple[dict, int]]:
    result = []
    for domain in ("indoor", "urban"):
        specs = [
            json.loads(line)
            for line in (ROOT / f"protocol/generation/{domain}_specs.jsonl")
            .read_text()
            .splitlines()
            if line
        ]
        result.extend((spec, seed) for spec in specs for seed in range(4))
    return result


def bounded_run(
    items: list[tuple[dict, int]], data_root: Path, workers: int
) -> list[dict]:
    results = []
    iterator = iter(items)
    stopped = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        for _ in range(workers):
            try:
                item = next(iterator)
            except StopIteration:
                break
            active[pool.submit(run_one, *item, data_root)] = item
        while active:
            completed, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in completed:
                spec, seed = active.pop(future)
                manifest = future.result()
                results.append(manifest)
                print(
                    f"RECOVERY_DONE {spec['spec_id']} seed={seed} "
                    f"generated={manifest.get('generation_success')} failure={manifest.get('failure_class')}",
                    flush=True,
                )
                if manifest.get("failure_class") in {
                    "infrastructure",
                    "access_blocked",
                }:
                    stopped = True
            if not stopped:
                for _ in completed:
                    try:
                        item = next(iterator)
                    except StopIteration:
                        break
                    active[pool.submit(run_one, *item, data_root)] = item
    if stopped:
        raise RuntimeError(
            "Recovery paused at the first unresolved infrastructure/access result"
        )
    return results


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api-key-file", type=Path, required=True)
    parser.add_argument("--workers", type=int, default=2, choices=(1, 2))
    args = parser.parse_args()
    token = args.api_key_file.read_text().strip()
    if not token:
        raise RuntimeError("API key file is empty")
    os.environ["GLM53_API_KEY"] = token
    verify_sources()
    data_root = confined(ROOT / "data/table2")
    results = bounded_run(tasks(), data_root, args.workers)
    report = {
        "finished_at_utc": utc(),
        "amendment": AMENDMENT,
        "processed": len(results),
        "generated": sum(bool(row.get("generation_success")) for row in results),
        "quality": sum(row.get("failure_class") == "quality" for row in results),
        "infrastructure": sum(
            row.get("failure_class") == "infrastructure" for row in results
        ),
    }
    write_json(ROOT / "results/glm53_flash/formal_generation_recovery.json", report)
    print(json.dumps(report), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

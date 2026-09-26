#!/usr/bin/env python3
"""GPT-6 Astra Medium adapter, isolated from the frozen High experiment."""
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
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str((ROOT / "methods")))
from baselines.methods.gpt.adapter import check_code
from baselines.methods.gpt.adapter import confined
from baselines.methods.gpt.adapter import digest
from baselines.methods.gpt.adapter import run_process
from baselines.methods.gpt.adapter import utc
from baselines.methods.gpt.adapter import write_json

METHOD = "gpt6_astra_medium"
CONFIG = ROOT / "methods/gpt/protocol/generation/gpt6_astra_medium.json"
PROMPT = ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt"
SCHEMA = ROOT / "methods/gpt/protocol/generation/gpt6_astra_output.schema.json"


def recover_pre_request_sandbox_failure(
    run: Path, manifest: dict, identity: dict
) -> bool:
    """Archive local Codex initialization failures that occurred before a request."""
    attempts = manifest.get("attempts", [])
    if manifest.get("generation_success") or not attempts:
        return False
    evidence = []
    for attempt in attempts:
        index = attempt.get("index")
        stderr = run / f"logs/generation_{index:02d}/stderr.log"
        if not stderr.exists():
            return False
        content = stderr.read_text()
        if (
            "failed to initialize in-process app-server client: Read-only file system"
            not in content
        ):
            return False
        if (
            attempt.get("thread_ids")
            or attempt.get("usage")
            or attempt.get("tool_events")
        ):
            return False
        evidence.append({**attempt, "stderr_sha256": digest(stderr)})
    stamp = utc().replace(":", "-")
    archive = run / "logs" / ("pre_request_sandbox_" + stamp)
    archive.mkdir(parents=True, exist_ok=False)
    for attempt in attempts:
        source = run / f"logs/generation_{attempt['index']:02d}"
        source.rename(archive / source.name)
    manifest.setdefault("pre_request_infrastructure_failures", []).append(
        {
            "reason": "Codex app-server could not initialize in the outer read-only execution sandbox; no remote request began",
            "archived_at_utc": utc(),
            "archive": str(archive.relative_to(run)),
            "attempts": evidence,
        }
    )
    manifest.update(
        identity=identity, attempts=[], failure_class=None, failure_reason=None
    )
    write_json(run / "run_manifest.json", manifest)
    return True


def generate(spec: dict, seed: int, data_root: Path) -> dict:
    """Run the frozen High text-only interface with medium reasoning effort."""
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_template_sha256": digest(PROMPT),
        "protocol_sha256": digest(CONFIG),
        "adapter_sha256": digest(__file__),
        "shared_high_renderer_sha256": digest(
            (ROOT / "methods/gpt/tools/blender_render_gpt.py")
        ),
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("identity") != identity:
            pilot_mode = json.loads(CONFIG.read_text()).get("status") == "pilot"
            if not pilot_mode or not recover_pre_request_sandbox_failure(
                run, manifest, identity
            ):
                raise RuntimeError(
                    "Existing Medium run has different frozen inputs; use a distinct data root"
                )
        elif len(manifest.get("attempts", [])) >= 3:
            recover_pre_request_sandbox_failure(run, manifest, identity)
        if (
            manifest.get("generation_success")
            or manifest.get("failure_class") == "quality"
        ):
            return manifest
    else:
        manifest = {
            "method": METHOD,
            "domain": spec["domain"],
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "method_seed": seed,
            "seed_supported": False,
            "identity": identity,
            "model_requested": "gpt-6-astra",
            "reasoning_effort_requested": "medium",
            "model_returned": None,
            "model_identity_evidence": "explicit CLI model and reasoning-effort selection; CLI JSONL has no returned model snapshot",
            "auth_mode": "codex_chatgpt_login",
            "generation_success": False,
            "build_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }
    config = json.loads(CONFIG.read_text())
    if config["model"] != "gpt-6-astra" or config["reasoning_effort"] != "medium":
        raise RuntimeError("Medium model configuration drift")
    installed = subprocess.check_output(["codex", "--version"], text=True).strip()
    if installed != "codex-cli " + config["codex_version"]:
        raise RuntimeError("CLI version drift before model request: " + installed)
    manifest["codex_version"] = installed
    prompt = (
        PROMPT.read_text()
        + "\n"
        + json.dumps({"spec": spec, "logical_seed": seed}, ensure_ascii=False)
    )
    write_json(run / "input/spec.json", spec)
    write_json(
        run / "input/native_input.json",
        {
            "prompt": prompt,
            "model": "gpt-6-astra",
            "seed": seed,
            "seed_supported": False,
            "reasoning_effort": "medium",
        },
    )
    for index in range(len(manifest["attempts"]) + 1, 4):
        attempt_dir = run / f"logs/generation_{index:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        work = run / "work"
        work.mkdir(exist_ok=True)
        output = attempt_dir / "response.json"
        command = [
            "codex",
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            "gpt-6-astra",
            "-c",
            'model_reasoning_effort="medium"',
            "--json",
            "--output-schema",
            str(SCHEMA),
            "-C",
            str(work),
            "-o",
            str(output),
            "-",
        ]
        attempt = {
            "index": index,
            "started_at_utc": utc(),
            "command": command,
            "reasoning_effort": "medium",
        }
        manifest["attempts"].append(attempt)
        write_json(manifest_path, manifest)
        code, timed_out = run_process(
            command,
            work,
            attempt_dir / "events.jsonl",
            attempt_dir / "stderr.log",
            config["generation_timeout_s"],
            stdin=prompt,
        )
        attempt.update(exit_code=code, timeout=timed_out, ended_at_utc=utc())
        events = []
        for line in (attempt_dir / "events.jsonl").read_text().splitlines():
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
        if code == 0 and output.exists():
            try:
                response = json.loads(output.read_text())
                check_code(response["code"])
                if attempt["tool_events"]:
                    raise ValueError(
                        "Generation used tools outside the frozen text-only interface"
                    )
                scene = run / "scene"
                scene.mkdir(exist_ok=True)
                (scene / "generated.py").write_text(response["code"] + "\n")
                manifest.update(
                    generation_success=True,
                    failure_class=None,
                    failure_reason=None,
                    generated_code_sha256=digest(scene / "generated.py"),
                )
            except (ValueError, KeyError, TypeError, SyntaxError) as exc:
                manifest.update(
                    failure_class="quality",
                    failure_reason=type(exc).__name__ + ": " + str(exc),
                )
            manifest["ended_at_utc"] = utc()
            write_json(manifest_path, manifest)
            return manifest
        logs = (attempt_dir / "events.jsonl").read_text() + (
            attempt_dir / "stderr.log"
        ).read_text()
        if any(
            token in logs.lower()
            for token in (
                "usage limit",
                "rate limit",
                "not supported",
                "not found",
                "unauthorized",
                "authentication",
                "quota",
            )
        ):
            manifest.update(
                failure_class="access_blocked",
                failure_reason="See generation logs; target model access or quota blocked",
            )
            write_json(manifest_path, manifest)
            raise RuntimeError(manifest["failure_reason"])
        manifest.update(
            failure_class="infrastructure",
            failure_reason="Codex process failed or timed out",
        )
        write_json(manifest_path, manifest)
        if index < 3:
            time.sleep(5)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gpt6_astra_medium_pilot"
    )
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    spec = next(row for row in specs if row["spec_id"] == args.spec_id)
    result = generate(spec, args.seed, confined(args.data_root))
    print(json.dumps(result, indent=2))
    return 0 if result.get("generation_success") else 2


if __name__ == "__main__":
    raise SystemExit(main())

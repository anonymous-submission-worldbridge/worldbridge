#!/usr/bin/env python3
"""GPT-6 Astra Extra High adapter, isolated from the frozen High experiment."""
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

METHOD = "gpt6_astra_xhigh"
CONFIG = ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.json"
PROMPT = ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt"
SCHEMA = ROOT / "methods/gpt/protocol/generation/gpt6_astra_output.schema.json"
CODEX = ROOT / "tools/codex-gpt6-astra-xhigh-frozen"
CODEX_HOST = ROOT / "tools/codex-code-mode-host"
AMENDMENT = (
    ROOT
    / "methods/gpt/protocol/generation/gpt6_astra_xhigh_generation_amendment_20260913.json"
)
MISSING_HOST_WARNING = "Code Mode is unavailable because failed to spawn code-mode host"
LEGACY_PRE_FORMAL_ADAPTER_HASHES = {
    "019924ac82daed1df98c2a7ff740195304905de8e3b617d5fef7518e713f31db",
    "36e44935c2c07a87a74c6aed5bc6dfb646967df9627e20be3d9829f7bbb58b38",
}
LEGACY_OPERATIONAL_AMENDMENT_HASHES = {
    None,
    "0d055e503837d3ab8d00f61fc1bc79caae15092be919455c427cdd00d557d620",
}


def load_operational_amendment(config: dict) -> dict:
    amendment = json.loads(AMENDMENT.read_text())
    if amendment.get("phase") != "pre_formal_pilot":
        raise RuntimeError("Unexpected Extra High operational amendment phase")
    unchanged = amendment.get("unchanged_registered_configuration", {})
    if unchanged.get("model") != config.get("model") or unchanged.get(
        "reasoning_effort"
    ) != config.get("reasoning_effort"):
        raise RuntimeError("Extra High operational amendment identity drift")
    if unchanged.get("generation_timeout_s_recorded_for_high_parity") != config.get(
        "generation_timeout_s"
    ):
        raise RuntimeError("Extra High registered timeout drift")
    effective = amendment.get("operational_changes", {}).get(
        "effective_generation_timeout_s"
    )
    if effective != 3600:
        raise RuntimeError("Extra High effective generation timeout drift")
    return amendment


def migrate_pre_formal_operational_identity(
    run: Path, manifest: dict, identity: dict, config: dict
) -> bool:
    """Attach the disclosed pre-formal operational amendment without rerunning a pilot slot."""
    if config.get("status") != "pilot":
        return False
    old = manifest.get("identity", {})
    old_adapter = old.get("adapter_sha256")
    old_amendment = old.get("operational_amendment_sha256")
    old_stable = {
        key: value
        for key, value in old.items()
        if key not in {"adapter_sha256", "operational_amendment_sha256"}
    }
    new_stable = {
        key: value
        for key, value in identity.items()
        if key not in {"adapter_sha256", "operational_amendment_sha256"}
    }
    if (
        old_stable != new_stable
        or old_adapter not in LEGACY_PRE_FORMAL_ADAPTER_HASHES
        or old_amendment not in LEGACY_OPERATIONAL_AMENDMENT_HASHES
    ):
        return False
    manifest.setdefault("pre_formal_identity_migrations", []).append(
        {
            "migrated_at_utc": utc(),
            "reason": "Attach or revise the pre-formal xhigh generation-timeout resource amendment",
            "old_adapter_sha256": old_adapter,
            "old_operational_amendment_sha256": old_amendment,
            "new_adapter_sha256": identity["adapter_sha256"],
            "amendment": str(AMENDMENT.relative_to(ROOT)),
            "amendment_sha256": identity["operational_amendment_sha256"],
            "model_response_repeated": False,
        }
    )
    manifest["identity"] = identity
    write_json(run / "run_manifest.json", manifest)
    return True


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


def recover_benign_missing_host_warning(
    run: Path, manifest: dict, identity: dict
) -> bool:
    """Accept an already returned text-only response after repairing its local CLI sidecar.

    The first xhigh probe returned valid structured code but also emitted one local
    `error` item before the turn because the 0.153.4 code-mode host executable had
    not yet been copied beside the frozen CLI.  That item is not a model tool call.
    Preserve the raw event and response, repair the installation, and reuse the
    response rather than issuing a duplicate model request.
    """
    if manifest.get("generation_success") or manifest.get("failure_reason") != (
        "ValueError: Generation used tools outside the frozen text-only interface"
    ):
        return False
    old_identity = manifest.get("identity", {})
    if any(
        old_identity.get(key) != value
        for key, value in identity.items()
        if key not in {"adapter_sha256", "codex_sidecar_sha256"}
    ):
        return False
    attempts = manifest.get("attempts", [])
    if (
        len(attempts) != 1
        or attempts[0].get("exit_code") != 0
        or attempts[0].get("timeout")
    ):
        return False
    attempt_dir = run / "logs/generation_01"
    response_path = attempt_dir / "response.json"
    events_path = attempt_dir / "events.jsonl"
    if (
        not response_path.exists()
        or not events_path.exists()
        or not CODEX_HOST.exists()
    ):
        return False
    events = [json.loads(line) for line in events_path.read_text().splitlines() if line]
    non_messages = [
        event.get("item", {})
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") != "agent_message"
    ]
    warnings = [
        item.get("message", "") for item in non_messages if item.get("type") == "error"
    ]
    if (
        len(non_messages) != 1
        or len(warnings) != 1
        or MISSING_HOST_WARNING not in warnings[0]
    ):
        return False
    response = json.loads(response_path.read_text())
    check_code(response["code"])
    scene = run / "scene"
    scene.mkdir(exist_ok=True)
    (scene / "generated.py").write_text(response["code"] + "\n")
    attempts[0]["tool_events"] = []
    attempts[0]["local_cli_warnings"] = warnings
    manifest.setdefault("pre_formal_infrastructure_recoveries", []).append(
        {
            "recovered_at_utc": utc(),
            "reason": "Missing frozen CLI code-mode sidecar emitted a local error item; the model made no tool call",
            "action": "Installed the matching 0.153.4 sidecar and accepted the existing valid structured response without a repeat request",
            "events_sha256": digest(events_path),
            "response_sha256": digest(response_path),
            "codex_sidecar_sha256": digest(CODEX_HOST),
        }
    )
    manifest.update(
        identity=identity,
        generation_success=True,
        failure_class=None,
        failure_reason=None,
        generated_code_sha256=digest(scene / "generated.py"),
        ended_at_utc=utc(),
    )
    write_json(run / "run_manifest.json", manifest)
    return True


def generate(spec: dict, seed: int, data_root: Path) -> dict:
    """Run the frozen High text-only interface with xhigh reasoning effort."""
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    config = json.loads(CONFIG.read_text())
    amendment = load_operational_amendment(config)
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
        "codex_executable_sha256": digest(CODEX),
        "codex_sidecar_sha256": digest(CODEX_HOST),
        "operational_amendment_sha256": digest(AMENDMENT),
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("identity") != identity:
            pilot_mode = config.get("status") == "pilot"
            if not pilot_mode or not (
                migrate_pre_formal_operational_identity(run, manifest, identity, config)
                or recover_benign_missing_host_warning(run, manifest, identity)
                or recover_pre_request_sandbox_failure(run, manifest, identity)
            ):
                raise RuntimeError(
                    "Existing Extra High run has different frozen inputs; use a distinct data root"
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
            "reasoning_effort_requested": "xhigh",
            "model_returned": None,
            "model_identity_evidence": "explicit CLI model and reasoning-effort selection; CLI JSONL has no returned model snapshot",
            "auth_mode": "codex_chatgpt_login",
            "generation_success": False,
            "build_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }
    if config["model"] != "gpt-6-astra" or config["reasoning_effort"] != "xhigh":
        raise RuntimeError("Extra High model configuration drift")
    installed = subprocess.check_output([str(CODEX), "--version"], text=True).strip()
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
            "reasoning_effort": "xhigh",
        },
    )
    effective_timeout = amendment["operational_changes"][
        "effective_generation_timeout_s"
    ]
    max_attempts = 3
    old_attempts = manifest["attempts"]
    if (
        config.get("status") == "pilot"
        and len(old_attempts) == 3
        and manifest.get("failure_class") == "infrastructure"
        and all(item.get("timeout") is True for item in old_attempts)
        and all(
            item.get("timeout_limit_s", config["generation_timeout_s"])
            in {config["generation_timeout_s"], 1800}
            for item in old_attempts
        )
    ):
        max_attempts += amendment["operational_changes"][
            "pilot_only_recovery_attempts_for_pre_amendment_exhaustion"
        ]
        manifest.setdefault(
            "pre_formal_timeout_recovery",
            {
                "authorized_by": str(AMENDMENT.relative_to(ROOT)),
                "amendment_sha256": digest(AMENDMENT),
                "preserved_pre_amendment_attempts": 3,
                "first_recovery_attempt": 4,
            },
        )
    for index in range(len(manifest["attempts"]) + 1, max_attempts + 1):
        attempt_dir = run / f"logs/generation_{index:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        work = run / "work"
        work.mkdir(exist_ok=True)
        output = attempt_dir / "response.json"
        command = [
            str(CODEX),
            "exec",
            "--ignore-user-config",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--model",
            "gpt-6-astra",
            "-c",
            'model_reasoning_effort="xhigh"',
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
            "reasoning_effort": "xhigh",
            "timeout_limit_s": effective_timeout,
            "operational_amendment": str(AMENDMENT.relative_to(ROOT)),
        }
        manifest["attempts"].append(attempt)
        write_json(manifest_path, manifest)
        code, timed_out = run_process(
            command,
            work,
            attempt_dir / "events.jsonl",
            attempt_dir / "stderr.log",
            effective_timeout,
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
        attempt["local_cli_errors"] = [
            e.get("item", {}).get("message")
            for e in events
            if e.get("type") == "item.completed"
            and e.get("item", {}).get("type") == "error"
        ]
        attempt["tool_events"] = [
            e.get("item", {}).get("type")
            for e in events
            if e.get("type") == "item.completed"
            and e.get("item", {}).get("type") not in {"agent_message", "error"}
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
        if index < max_attempts:
            time.sleep(5)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=("indoor", "urban"), required=True)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gpt6_astra_xhigh_pilot"
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

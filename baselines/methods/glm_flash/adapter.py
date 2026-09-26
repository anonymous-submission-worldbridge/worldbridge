#!/usr/bin/env python3
"""GLM-5.3 Flash via the GLM Coding Plan and OpenCode."""
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
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import time


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "glm53_flash"
MODEL = "glm-5.3-flash"
PROVIDER = "glm-coding-plan"


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def confined(path):
    path = Path(path).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError("Experiment output must remain under baselines")
    return path


def check_code(code):
    tree = ast.parse(code)
    allowed = {"bpy", "math", "random", "numpy", "mathutils", "collections"}
    forbidden = {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "globals",
        "locals",
        "input",
        "breakpoint",
    }
    forbidden_attrs = {
        "save_as_mainfile",
        "open_mainfile",
        "read_homefile",
        "load",
        "save",
        "write",
        "remove_doubles_exec",
        "handlers",
        "driver_add",
        "keyframe_insert",
        "filepath",
        "preferences",
        "libraries",
        "scripts",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] not in allowed for alias in node.names):
                raise ValueError("Unsupported import in generated scene")
        if isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in allowed:
                raise ValueError("Unsupported import in generated scene")
        if isinstance(node, ast.Name) and node.id in forbidden:
            raise ValueError("Unsupported builtin in generated scene: " + node.id)
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__") or node.attr in forbidden_attrs
        ):
            raise ValueError("Unsupported attribute in generated scene: " + node.attr)
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "build_scene"
        for node in tree.body
    ):
        raise ValueError("Generated code must define build_scene(seed)")
    return tree


def run_process(command, work, stdout_path, stderr_path, timeout, env=None, stdin=None):
    with stdout_path.open("w") as stdout, stderr_path.open("w") as stderr:
        try:
            process = subprocess.Popen(
                command,
                cwd=work,
                env=env,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            stderr.write(type(error).__name__ + ": " + str(error) + "\n")
            return 127, False
        try:
            process.communicate(stdin, timeout=timeout)
            return process.returncode, False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return process.returncode, True


def _opencode_environment():
    token = os.environ.get("GLM53_API_KEY", "").strip()
    if not token:
        raise RuntimeError("GLM53_API_KEY is required and must be supplied out of band")
    cache = ROOT / "cache/glm53_opencode"
    environment = dict(os.environ)
    environment.update(
        GLM53_API_KEY=token,
        XDG_DATA_HOME=str(cache / "data"),
        XDG_CONFIG_HOME=str(cache / "config"),
        XDG_CACHE_HOME=str(cache / "cache"),
        XDG_STATE_HOME=str(cache / "state"),
        OPENCODE_DISABLE_AUTOUPDATE="1",
        OPENCODE_DISABLE_MODELS_FETCH="1",
        OPENCODE_DISABLE_DEFAULT_PLUGINS="1",
        OPENCODE_DISABLE_LSP_DOWNLOAD="1",
        OPENCODE_DISABLE_TERMINAL_TITLE="1",
        OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER="1",
        OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX="65536",
    )
    environment.pop("ANTHROPIC_AUTH_TOKEN", None)
    environment.pop("ANTHROPIC_API_KEY", None)
    return environment


def _extract_json(text):
    fenced = re.search(
        r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE
    )
    candidates = [fenced.group(1)] if fenced else []
    decoder = json.JSONDecoder()
    for offset, character in enumerate(text):
        if character == "{":
            try:
                value, _ = decoder.raw_decode(text[offset:])
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                candidates.append(value)
    for candidate in candidates:
        try:
            value = json.loads(candidate) if isinstance(candidate, str) else candidate
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and set(value) == {"code"}
            and isinstance(value["code"], str)
        ):
            return value
    raise ValueError(
        "Missing schema-conforming JSON object with exactly one code field"
    )


def _parse_response(path):
    events, text_parts, finishes = [], [], []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        events.append(event)
        if event.get("type") == "text":
            text_parts.append(event.get("part", {}).get("text", ""))
        if event.get("type") == "step_finish":
            finishes.append(event)
    if (
        not events
        or len(finishes) != 1
        or finishes[0].get("part", {}).get("reason") != "stop"
    ):
        raise ValueError("OpenCode did not return one successful terminal step")
    forbidden_types = {"tool_use", "tool_call", "tool_result"}
    if any(event.get("type") in forbidden_types for event in events):
        raise ValueError(
            "Generation used a tool outside the frozen text-only interface"
        )
    session_ids = {event.get("sessionID") for event in events if event.get("sessionID")}
    if len(session_ids) != 1:
        raise ValueError("OpenCode response does not identify exactly one session")
    structured = _extract_json("".join(text_parts))
    check_code(structured["code"])
    return {
        "session_id": next(iter(session_ids)),
        "usage": finishes[0].get("part", {}).get("tokens", {}),
        "event_types": [event.get("type") for event in events],
    }, structured["code"]


def _verify_model_evidence(environment, session_id):
    messages = (
        Path(environment["XDG_DATA_HOME"]) / "opencode/storage/message" / session_id
    )
    records = [json.loads(path.read_text()) for path in sorted(messages.glob("*.json"))]
    assistant = [record for record in records if record.get("role") == "assistant"]
    if len(assistant) != 1:
        raise ValueError("OpenCode session must contain exactly one assistant message")
    evidence = assistant[0]
    if evidence.get("providerID") != PROVIDER or evidence.get("modelID") != MODEL:
        raise ValueError("OpenCode model evidence does not match glm-5.3-flash")
    if evidence.get("agent") != "scene" or evidence.get("finish") != "stop":
        raise ValueError(
            "OpenCode assistant message has unexpected agent or finish state"
        )
    return evidence


def generate(spec, seed, data_root):
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    prompt_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt"
    schema_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_output.schema.json"
    config_path = ROOT / "methods/glm_flash/protocol/generation/glm53_flash.json"
    opencode_config_path = (
        ROOT / "methods/glm_flash/protocol/generation/glm53_flash_opencode.json"
    )
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_template_sha256": digest(prompt_path),
        "output_schema_sha256": digest(schema_path),
        "protocol_sha256": digest(config_path),
        "opencode_config_sha256": digest(opencode_config_path),
        "adapter_sha256": digest(__file__),
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        if manifest.get("identity") != identity:
            raise RuntimeError(
                "Existing run has different frozen inputs; use a distinct data root"
            )
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
            "model_requested": MODEL,
            "model_returned": None,
            "model_identity_evidence": "OpenCode assistant metadata providerID/modelID",
            "auth_mode": "glm_coding_plan_opencode",
            "generation_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }

    config = json.loads(config_path.read_text())
    installed = subprocess.check_output(["opencode", "--version"], text=True).strip()
    if installed != config["opencode_version"]:
        raise RuntimeError("OpenCode version drift before model request: " + installed)
    manifest["opencode_version"] = installed
    prompt = (
        prompt_path.read_text()
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

    for index in range(len(manifest["attempts"]) + 1, 4):
        attempt_dir = run / f"logs/generation_{index:02d}"
        attempt_dir.mkdir(parents=True)
        work = run / "work"
        work.mkdir(exist_ok=True)
        shutil.copyfile(opencode_config_path, work / "opencode.json")
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
        recorded_command = command[:-1] + ["<PROMPT_FROM_INPUT_NATIVE_INPUT_JSON>"]
        attempt = {
            "index": index,
            "started_at_utc": utc(),
            "command": recorded_command,
            "endpoint": "https://open.bigmodel.cn/api/coding/paas/v4",
        }
        manifest["attempts"].append(attempt)
        write_json(manifest_path, manifest)
        environment = _opencode_environment()
        return_code, timed_out = run_process(
            command,
            work,
            output,
            attempt_dir / "stderr.log",
            config.get("generation_timeout_s", 1200),
            env=environment,
        )
        attempt.update(exit_code=return_code, timeout=timed_out, ended_at_utc=utc())
        if return_code == 0 and output.exists():
            try:
                response, code = _parse_response(output)
                evidence = _verify_model_evidence(environment, response["session_id"])
                secret = environment["GLM53_API_KEY"]
                if secret in output.read_text(errors="replace") or secret in (
                    attempt_dir / "stderr.log"
                ).read_text(errors="replace"):
                    raise ValueError("Secret appeared in persisted process output")
                attempt["session_id"] = response["session_id"]
                attempt["usage"] = response["usage"]
                attempt["event_types"] = response["event_types"]
                attempt["model_evidence"] = {
                    "providerID": evidence["providerID"],
                    "modelID": evidence["modelID"],
                    "message_id": evidence["id"],
                }
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
            manifest["ended_at_utc"] = utc()
            write_json(manifest_path, manifest)
            return manifest

        logs = output.read_text(errors="replace") + (
            attempt_dir / "stderr.log"
        ).read_text(errors="replace")
        lowered = logs.lower()
        if any(
            token in lowered
            for token in (
                "usage limit",
                "rate limit",
                "not supported",
                "not found",
                "unauthorized",
                "authentication",
                "quota",
                "insufficient balance",
            )
        ):
            manifest.update(
                failure_class="access_blocked",
                failure_reason="See generation logs; target model access or Coding Plan quota blocked",
            )
            write_json(manifest_path, manifest)
            raise RuntimeError(manifest["failure_reason"])
        manifest.update(
            failure_class="infrastructure",
            failure_reason="OpenCode failed or timed out",
        )
        write_json(manifest_path, manifest)
        if index < 3:
            time.sleep(5)
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/glm53_flash_pilot"
    )
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    spec = next(item for item in specs if item["spec_id"] == args.spec_id)
    result = generate(spec, args.seed, confined(args.data_root))
    print(json.dumps(result, indent=2))
    return 0 if result["generation_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

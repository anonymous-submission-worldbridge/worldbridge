#!/usr/bin/env python3
"""GLM-5.3 through the official Coding Plan OpenCode integration."""
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
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "glm_5_3"
MODEL = "glm-5.3"
PROVIDER = "glm-coding-plan"


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def digest(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temporary.replace(path)


def confined(path: Path) -> Path:
    resolved = Path(path).resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("Experiment output must remain under baselines")
    return resolved


def check_code(code: str) -> ast.AST:
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


def run_process(
    command: list[str],
    work: Path,
    stdout_path: Path,
    stderr_path: Path,
    timeout: int,
    env: dict[str, str] | None = None,
    stdin: str | None = None,
) -> tuple[int, bool]:
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


def extract_structured_output(text: str) -> dict:
    fenced = re.search(
        r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE
    )
    candidates: list[object] = [fenced.group(1)] if fenced else []
    decoder = json.JSONDecoder()
    for offset, character in enumerate(text):
        if character != "{":
            continue
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


def parse_opencode_events(raw: str) -> tuple[str, str, dict]:
    texts: list[str] = []
    sessions: set[str] = set()
    finishes: list[dict] = []
    event_types: list[str] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        event_types.append(event.get("type"))
        if event.get("sessionID"):
            sessions.add(event["sessionID"])
        if event.get("type") == "error":
            message = (
                event.get("error", {}).get("data", {}).get("message", "OpenCode error")
            )
            raise RuntimeError(message)
        part = event.get("part")
        if event.get("type") == "text" and isinstance(part, dict):
            text = part.get("text")
            if isinstance(text, str):
                texts.append(text)
        if event.get("type") == "step_finish" and isinstance(part, dict):
            finishes.append(part)
    if len(sessions) != 1:
        raise ValueError("OpenCode output must identify exactly one session")
    if not texts:
        raise ValueError("OpenCode output has no assistant text event")
    if len(finishes) != 1 or finishes[0].get("reason") != "stop":
        raise ValueError("OpenCode did not return one successful terminal step")
    if any(kind in {"tool_use", "tool_call", "tool_result"} for kind in event_types):
        raise ValueError(
            "Generation used a tool outside the frozen text-only interface"
        )
    structured = extract_structured_output("".join(texts))
    usage = finishes[0].get("tokens", {})
    return structured["code"], next(iter(sessions)), usage


def find_model_evidence(value: object) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    if isinstance(value, dict):
        provider = value.get("providerID")
        model = value.get("modelID")
        if isinstance(provider, str) and isinstance(model, str):
            evidence.append({"providerID": provider, "modelID": model})
        for child in value.values():
            evidence.extend(find_model_evidence(child))
    elif isinstance(value, list):
        for child in value:
            evidence.extend(find_model_evidence(child))
    return evidence


def verify_exported_model(payload: object) -> list[dict[str, str]]:
    evidence = find_model_evidence(payload)
    if not any(item == {"providerID": PROVIDER, "modelID": MODEL} for item in evidence):
        raise ValueError(
            "OpenCode evidence does not prove glm-coding-plan/glm-5.3 execution"
        )
    return evidence


def verify_session_model(environment: dict[str, str], session_id: str) -> dict:
    directory = (
        Path(environment["XDG_DATA_HOME"]) / "opencode/storage/message" / session_id
    )
    records = [
        json.loads(path.read_text()) for path in sorted(directory.glob("*.json"))
    ]
    assistant = [record for record in records if record.get("role") == "assistant"]
    if len(assistant) != 1:
        raise RuntimeError(
            "OpenCode session must contain exactly one assistant message"
        )
    evidence = assistant[0]
    verify_exported_model(evidence)
    if evidence.get("agent") != "scene" or evidence.get("finish") != "stop":
        raise RuntimeError(
            "OpenCode assistant message has unexpected agent or finish state"
        )
    return evidence


def compress_log(path: Path) -> dict | None:
    if not path.exists():
        return None
    target = path.with_suffix(path.suffix + ".gz")
    temporary = target.with_suffix(target.suffix + ".tmp")
    original_bytes = path.stat().st_size
    with path.open("rb") as source, gzip.open(
        temporary, "wb", compresslevel=1
    ) as destination:
        shutil.copyfileobj(source, destination, length=1024 * 1024)
    temporary.replace(target)
    path.unlink()
    return {
        "path": target.name,
        "original_bytes": original_bytes,
        "compressed_bytes": target.stat().st_size,
        "sha256": digest(target),
    }


def opencode_environment(api_key: str) -> dict[str, str]:
    environment = dict(os.environ)
    runtime = ROOT / "methods/glm_flash/runtime/glm53_opencode"
    environment.update(
        GLM53_API_KEY=api_key,
        XDG_DATA_HOME=str(runtime / "data"),
        XDG_CONFIG_HOME=str(runtime / "config"),
        XDG_CACHE_HOME=str(runtime / "cache"),
        XDG_STATE_HOME=str(runtime / "state"),
        OPENCODE_CONFIG=str(runtime / "opencode.json"),
        OPENCODE_DISABLE_AUTOUPDATE="1",
        OPENCODE_DISABLE_MODELS_FETCH="1",
        OPENCODE_DISABLE_DEFAULT_PLUGINS="1",
        OPENCODE_DISABLE_LSP_DOWNLOAD="1",
        OPENCODE_DISABLE_TERMINAL_TITLE="1",
        OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER="1",
        OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX="65536",
        OPENCODE_DISABLE_PRUNE="1",
    )
    return environment


def generate(spec: dict, seed: int, data_root: Path) -> dict:
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    prompt_path = ROOT / "methods/glm/protocol/generation/glm_5_3_prompt.txt"
    schema_path = ROOT / "methods/glm/protocol/generation/glm_5_3_output.schema.json"
    config_path = ROOT / "methods/glm/protocol/generation/glm_5_3.json"
    opencode_config_path = (
        ROOT / "methods/glm_flash/runtime/glm53_opencode/opencode.json"
    )
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_template_sha256": digest(prompt_path),
        "output_schema_sha256": digest(schema_path),
        "protocol_sha256": digest(config_path),
        "adapter_sha256": digest(Path(__file__)),
        "opencode_config_sha256": digest(opencode_config_path),
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
            "model_identity_evidence": "OpenCode assistant metadata must contain providerID glm-coding-plan and modelID glm-5.3",
            "auth_mode": "glm_coding_plan_api_key_process_environment_via_opencode",
            "generation_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }

    config = json.loads(config_path.read_text())
    installed = subprocess.check_output(["opencode", "--version"], text=True).strip()
    if installed != config["opencode_version"]:
        raise RuntimeError("OpenCode version drift before model request: " + installed)
    api_key = os.environ.get(config["api_key_env"], "")
    if not api_key:
        raise RuntimeError(
            config["api_key_env"] + " must be supplied in the process environment"
        )
    manifest["opencode_version"] = installed
    prompt = (
        prompt_path.read_text()
        + "\n"
        + json.dumps({"spec": spec, "logical_seed": seed}, ensure_ascii=False)
    )
    write_json(run / "input/spec.json", spec)
    write_json(
        run / "input/native_input.json",
        {
            "prompt": prompt,
            "model": MODEL,
            "cli_model": config["cli_model"],
            "seed": seed,
            "seed_supported": False,
            "transport": config["transport"],
            "max_output_tokens": config["max_output_tokens"],
            "thinking_mode": config["thinking_mode"],
            "reasoning_effort": config["reasoning_effort"],
        },
    )
    environment = opencode_environment(api_key)
    for index in range(len(manifest["attempts"]) + 1, 4):
        attempt_dir = run / f"logs/generation_{index:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        work = run / "work"
        work.mkdir(exist_ok=True)
        command = [
            "opencode",
            "run",
            "--format",
            "json",
            "--log-level",
            "ERROR",
            "--agent",
            "scene",
            "--title",
            f"glm53_{spec['spec_id']}_{seed}",
            "--model",
            config["cli_model"],
            prompt,
        ]
        recorded_command = command[:-1] + ["<PROMPT_FROM_INPUT_NATIVE_INPUT_JSON>"]
        attempt = {
            "index": index,
            "started_at_utc": utc(),
            "command": recorded_command,
            "api_key_source": config["api_key_env"],
            "agent": "scene",
            "max_output_tokens": config["max_output_tokens"],
            "thinking_mode": config["thinking_mode"],
            "reasoning_effort": config["reasoning_effort"],
        }
        manifest["attempts"].append(attempt)
        write_json(manifest_path, manifest)
        stdout_path = attempt_dir / "response.json"
        stderr_path = attempt_dir / "stderr.log"
        return_code, timed_out = run_process(
            command,
            work,
            stdout_path,
            stderr_path,
            int(config.get("generation_timeout_s", 900)),
            env=environment,
            stdin=None,
        )
        attempt.update(exit_code=return_code, timeout=timed_out, ended_at_utc=utc())
        raw_stdout = stdout_path.read_text(errors="replace")
        raw_stderr = stderr_path.read_text(errors="replace")
        logs = (raw_stdout + raw_stderr).lower()
        if any(
            token in logs
            for token in (
                "usage limit",
                "rate limit",
                "not supported",
                "model not found",
                "unauthorized",
                "authentication",
                "quota",
                "invalid api key",
                "credit balance",
                "within limits",
                "1308",
                "The model does not exist.",
            )
        ):
            attempt["log_compression"] = {
                "response.json": compress_log(stdout_path),
                "stderr.log": compress_log(stderr_path),
            }
            manifest.update(
                failure_class="access_blocked",
                failure_reason="See compressed generation logs; target model access, model code, or quota blocked",
            )
            write_json(manifest_path, manifest)
            raise RuntimeError(manifest["failure_reason"])
        if return_code == 0:
            try:
                code, session_id, usage = parse_opencode_events(raw_stdout)
                evidence = verify_session_model(environment, session_id)
                secret = environment["GLM53_API_KEY"]
                if secret in raw_stdout or secret in raw_stderr:
                    raise ValueError("Secret appeared in persisted process output")
                attempt.update(
                    session_id=session_id,
                    usage=usage,
                    model_evidence={
                        "providerID": evidence["providerID"],
                        "modelID": evidence["modelID"],
                        "message_id": evidence["id"],
                    },
                )
                check_code(code)
                scene = run / "scene"
                scene.mkdir(exist_ok=True)
                (scene / "generated.py").write_text(code.rstrip() + "\n")
                manifest.update(
                    generation_success=True,
                    failure_class=None,
                    failure_reason=None,
                    model_returned=MODEL,
                    provider_returned=PROVIDER,
                    generated_code_sha256=digest(scene / "generated.py"),
                )
            except RuntimeError as error:
                attempt["log_compression"] = {
                    "response.json": compress_log(stdout_path),
                    "stderr.log": compress_log(stderr_path),
                }
                manifest.update(
                    failure_class="infrastructure",
                    failure_reason=type(error).__name__ + ": " + str(error),
                )
                write_json(manifest_path, manifest)
                if index < 3:
                    time.sleep(5)
                    continue
                return manifest
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
            attempt["log_compression"] = {
                "response.json": compress_log(stdout_path),
                "stderr.log": compress_log(stderr_path),
            }
            manifest["ended_at_utc"] = utc()
            write_json(manifest_path, manifest)
            return manifest
        attempt["log_compression"] = {
            "response.json": compress_log(stdout_path),
            "stderr.log": compress_log(stderr_path),
        }
        manifest.update(
            failure_class="infrastructure",
            failure_reason="OpenCode process failed or timed out",
        )
        write_json(manifest_path, manifest)
        if index < 3:
            time.sleep(5)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/glm_5_3_pilot_v5_low_opencode"
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

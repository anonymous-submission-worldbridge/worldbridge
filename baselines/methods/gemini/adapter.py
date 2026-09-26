#!/usr/bin/env python3
"""Gemini 3.1 Pro via Antigravity account login; no API-key billing."""
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
import shutil
import signal
import subprocess
import time


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gemini_3_1_pro"
MODEL = "gemini-3.1-pro-high"


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


def parse_response(text: str) -> str:
    payload = text.strip()
    if payload.startswith("```json") and payload.endswith("```"):
        payload = payload[7:-3].strip()
    elif payload.startswith("```") and payload.endswith("```"):
        payload = payload[3:-3].strip()
    try:
        response = json.loads(payload)
    except json.JSONDecodeError:
        start, end = payload.find("{"), payload.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Gemini response does not contain a JSON object")
        response = json.loads(payload[start : end + 1])
    if set(response) != {"code"} or not isinstance(response["code"], str):
        raise ValueError("Response does not match the frozen code-only schema")
    return response["code"]


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


def client_environment(timeout_seconds: int) -> dict[str, str]:
    environment = dict(os.environ)
    environment.pop("GEMINI_API_KEY", None)
    environment.pop("GOOGLE_API_KEY", None)
    environment.pop("GOOGLE_GEMINI_BASE_URL", None)
    environment["GEMINI31_PRINT_TIMEOUT"] = str(timeout_seconds) + "s"
    environment["AGY_CLI_DISABLE_AUTO_UPDATE"] = "1"
    return environment


def verify_client(config: dict) -> str:
    helper = Path(config["client_helper"])
    binary = Path(config["antigravity_binary"])
    if digest(helper) != config["client_helper_sha256"]:
        raise RuntimeError("Gemini account-auth helper hash drift")
    if digest(binary) != config["antigravity_binary_sha256"]:
        raise RuntimeError("Antigravity CLI binary hash drift")
    installed = subprocess.check_output([str(binary), "--version"], text=True).strip()
    if installed != config["antigravity_version"]:
        raise RuntimeError("Antigravity CLI version drift: " + installed)
    for settings in (
        Path.home() / ".gemini/antigravity-cli/settings.json",
        Path.home() / ".gemini/config/config.json",
    ):
        if settings.exists():
            payload = json.loads(settings.read_text())
            if payload.get("modelProvider") == "gemini":
                raise RuntimeError(
                    "Gemini API-key provider mode is enabled; refusing to run"
                )
            if any(
                key in payload for key in ("apiKey", "geminiApiKey", "googleApiKey")
            ):
                raise RuntimeError(
                    "API-key field found in Antigravity settings; refusing to run"
                )
    return installed


def classify_identity(existing: dict, current: dict, config: dict) -> str | None:
    """Recognize the current identity or the exact pre-migration frozen identity."""
    if existing == current:
        return "current"
    legacy = config.get("legacy_run_identity", {})
    expected = dict(current)
    for key in ("protocol_sha256", "adapter_sha256", "client_helper_sha256"):
        if key not in legacy:
            return None
        expected[key] = legacy[key]
    return "legacy_pre_migration" if existing == expected else None


def generate(spec: dict, seed: int, data_root: Path) -> dict:
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    prompt_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt"
    schema_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_output.schema.json"
    config_path = ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json"
    config = json.loads(config_path.read_text())
    helper_path = Path(config["client_helper"])
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_template_sha256": digest(prompt_path),
        "output_schema_sha256": digest(schema_path),
        "protocol_sha256": digest(config_path),
        "adapter_sha256": digest(Path(__file__)),
        "client_helper_sha256": digest(helper_path),
    }
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        identity_class = classify_identity(
            manifest.get("identity", {}), identity, config
        )
        if identity_class is None:
            raise RuntimeError(
                "Existing run has different frozen inputs; use a distinct data root"
            )
        if (
            manifest.get("generation_success")
            or manifest.get("failure_class") == "quality"
        ):
            return manifest
        if identity_class == "legacy_pre_migration":
            manifest.setdefault("identity_history", []).append(
                {
                    "identity": manifest["identity"],
                    "reason": "interrupted run resumed after host migration",
                    "amendment": config["client_recovery_amendment"],
                    "recorded_at_utc": utc(),
                }
            )
            manifest["identity"] = identity
            manifest["client_recovery_amendment"] = config["client_recovery_amendment"]
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
            "model_identity_evidence": "frozen helper pins gemini-3.1-pro-high; client text mode exposes no returned snapshot",
            "auth_mode": "google_ai_pro_account_via_antigravity_no_api_key",
            "api_key_environment_cleared": [
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GOOGLE_GEMINI_BASE_URL",
            ],
            "client_recovery_amendment": config["client_recovery_amendment"],
            "generation_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }
    installed = verify_client(config)
    manifest["antigravity_version"] = installed
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
            "seed": seed,
            "seed_supported": False,
            "transport": config["transport"],
            "auth_mode": config["auth_mode"],
            "reasoning_effort": config["reasoning_effort"],
            "client_mode": config["client_mode"],
        },
    )
    timeout = int(config["generation_timeout_s"])
    for index in range(len(manifest["attempts"]) + 1, 4):
        attempt_dir = run / f"logs/generation_{index:02d}"
        attempt_dir.mkdir(parents=True, exist_ok=False)
        work = run / "work"
        work.mkdir(exist_ok=True)
        command = [str(helper_path)]
        attempt = {
            "index": index,
            "started_at_utc": utc(),
            "command": command,
            "prompt_via_stdin": True,
            "model": MODEL,
            "reasoning_effort": "high",
            "client_mode": "plan",
            "auth_mode": config["auth_mode"],
            "client_helper_sha256": config["client_helper_sha256"],
            "api_key_environment_cleared": [
                "GEMINI_API_KEY",
                "GOOGLE_API_KEY",
                "GOOGLE_GEMINI_BASE_URL",
            ],
        }
        manifest["attempts"].append(attempt)
        write_json(manifest_path, manifest)
        stdout_path = attempt_dir / "response.txt"
        stderr_path = attempt_dir / "stderr.log"
        return_code, timed_out = run_process(
            command,
            work,
            stdout_path,
            stderr_path,
            timeout,
            env=client_environment(timeout),
            stdin=prompt,
        )
        attempt.update(exit_code=return_code, timeout=timed_out, ended_at_utc=utc())
        raw_stdout = stdout_path.read_text(errors="replace")
        raw_stderr = stderr_path.read_text(errors="replace")
        if return_code == 0:
            try:
                code = parse_response(raw_stdout)
                check_code(code)
                scene = run / "scene"
                scene.mkdir(exist_ok=True)
                (scene / "generated.py").write_text(code.rstrip() + "\n")
                manifest.update(
                    generation_success=True,
                    failure_class=None,
                    failure_reason=None,
                    model_returned=MODEL,
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
            attempt["log_compression"] = {
                "response.txt": compress_log(stdout_path),
                "stderr.log": compress_log(stderr_path),
            }
            manifest["ended_at_utc"] = utc()
            write_json(manifest_path, manifest)
            return manifest
        logs = (raw_stdout + raw_stderr).lower()
        attempt["log_compression"] = {
            "response.txt": compress_log(stdout_path),
            "stderr.log": compress_log(stderr_path),
        }
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
                "api-key provider mode",
                "subscription",
            )
        ):
            manifest.update(
                failure_class="access_blocked",
                failure_reason="See compressed generation logs; target model login or subscription quota blocked",
            )
            write_json(manifest_path, manifest)
            raise RuntimeError(manifest["failure_reason"])
        manifest.update(
            failure_class="infrastructure",
            failure_reason="Antigravity client failed or timed out",
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
        "--data-root", type=Path, default=ROOT / "data/gemini_3_1_pro_pilot"
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

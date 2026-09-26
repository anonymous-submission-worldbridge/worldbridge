#!/usr/bin/env python3
"""GPT-6 Astra via saved Codex login; one independent code generation per run."""
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
import signal
import subprocess
import time

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
METHOD = "gpt6_astra"


def utc():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    temp.replace(path)


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
        isinstance(n, ast.FunctionDef) and n.name == "build_scene" for n in tree.body
    ):
        raise ValueError("Generated code must define build_scene(seed)")
    return tree


def run_process(cmd, work, stdout_path, stderr_path, timeout, env=None, stdin=None):
    with stdout_path.open("w") as out, stderr_path.open("w") as err:
        try:
            proc = subprocess.Popen(
                cmd,
                cwd=work,
                env=env,
                stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                text=True,
                start_new_session=True,
            )
        except OSError as error:
            err.write(type(error).__name__ + ": " + str(error) + "\n")
            return 127, False
        try:
            proc.communicate(stdin, timeout=timeout)
            return proc.returncode, False
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGTERM)
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait()
            return proc.returncode, True


def generate(spec, seed, data_root):
    run = confined(
        data_root / spec["domain"] / METHOD / spec["spec_id"] / f"seed_{seed}"
    )
    run.mkdir(parents=True, exist_ok=True)
    manifest_path = run / "run_manifest.json"
    prompt_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra_prompt.txt"
    config_path = ROOT / "methods/gpt/protocol/generation/gpt6_astra.json"
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode()
        ).hexdigest(),
        "prompt_template_sha256": digest(prompt_path),
        "protocol_sha256": digest(config_path),
        "adapter_sha256": digest(__file__),
    }
    if manifest_path.exists():
        old = json.loads(manifest_path.read_text())
        if old.get("identity") != identity:
            raise RuntimeError(
                "Existing run has different frozen inputs; use a distinct data root"
            )
        if old.get("generation_success") or old.get("failure_class") == "quality":
            return old
    else:
        old = {
            "method": METHOD,
            "domain": spec["domain"],
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "method_seed": seed,
            "seed_supported": False,
            "identity": identity,
            "model_requested": "gpt-6-astra",
            "model_returned": None,
            "model_identity_evidence": "explicit CLI model selection; JSONL has no returned model field",
            "auth_mode": "codex_chatgpt_login",
            "generation_success": False,
            "render_success": False,
            "started_at_utc": utc(),
            "attempts": [],
        }
    config = json.loads(config_path.read_text())
    installed = subprocess.check_output(["codex", "--version"], text=True).strip()
    if installed != "codex-cli " + config["codex_version"]:
        raise RuntimeError("CLI version drift before model request: " + installed)
    old["codex_version"] = installed
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
            "model": "gpt-6-astra",
            "seed": seed,
            "seed_supported": False,
            "reasoning_effort": config["reasoning_effort"],
        },
    )
    for index in range(len(old["attempts"]) + 1, 4):
        attempt_dir = run / f"logs/generation_{index:02d}"
        attempt_dir.mkdir(parents=True)
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
            'model_reasoning_effort="' + config["reasoning_effort"] + '"',
            "--json",
            "--output-schema",
            str(
                (ROOT / "methods/gpt/protocol/generation/gpt6_astra_output.schema.json")
            ),
            "-C",
            str(work),
            "-o",
            str(output),
            "-",
        ]
        attempt = {"index": index, "started_at_utc": utc(), "command": command}
        old["attempts"].append(attempt)
        write_json(manifest_path, old)
        code, timed_out = run_process(
            command,
            work,
            attempt_dir / "events.jsonl",
            attempt_dir / "stderr.log",
            config.get("generation_timeout_s", 900),
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
                old.update(
                    generation_success=True,
                    failure_class=None,
                    failure_reason=None,
                    generated_code_sha256=digest(scene / "generated.py"),
                )
            except (ValueError, KeyError, TypeError, SyntaxError) as exc:
                old.update(
                    failure_class="quality",
                    failure_reason=type(exc).__name__ + ": " + str(exc),
                )
            old["ended_at_utc"] = utc()
            write_json(manifest_path, old)
            return old
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
            old.update(
                failure_class="access_blocked",
                failure_reason="See generation logs; target model access or quota blocked",
            )
            write_json(manifest_path, old)
            raise RuntimeError(old["failure_reason"])
        old.update(
            failure_class="infrastructure",
            failure_reason="Codex process failed or timed out",
        )
        write_json(manifest_path, old)
        if index < 3:
            time.sleep(5)
    return old


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--domain", choices=["indoor", "urban"], required=True)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, choices=range(4), required=True)
    parser.add_argument(
        "--data-root", type=Path, default=ROOT / "data/gpt6_astra_pilot"
    )
    args = parser.parse_args()
    specs = [
        json.loads(line)
        for line in (ROOT / f"protocol/generation/{args.domain}_specs.jsonl")
        .read_text()
        .splitlines()
        if line
    ]
    spec = next(s for s in specs if s["spec_id"] == args.spec_id)
    result = generate(spec, args.seed, confined(args.data_root))
    print(json.dumps(result, indent=2))
    return 0 if result["generation_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

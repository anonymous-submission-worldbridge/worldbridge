#!/usr/bin/env python3
"""Generate six resumable GPT-6 Astra xhigh indoor/outdoor demo scripts."""
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
REPO = BASELINES.parent
OUTPUT = BASELINES / "annotations/gpt6_astra_xhigh/full"
SPECS = (
    BASELINES / "methods/gpt/protocol/generation/gpt6_astra_xhigh_full_demo_specs.json"
)
PROMPT = (
    BASELINES / "methods/gpt/protocol/generation/gpt6_astra_xhigh_full_demo_prompt.txt"
)
SCHEMA = (
    BASELINES
    / "methods/gpt/protocol/generation/gpt6_astra_xhigh_full_demo_output.schema.json"
)
CODEX = BASELINES / "tools/codex-gpt6-astra-xhigh-frozen"
CODEX_HOST = BASELINES / "tools/codex-code-mode-host"
sys.path.insert(0, str((BASELINES / "methods")))
from baselines.methods.gpt.adapter import check_code  # noqa: E402


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def select_specs(requested: list[str]) -> list[dict]:
    specs = json.loads(SPECS.read_text(encoding="utf-8"))
    if not requested:
        return specs
    wanted = set(requested)
    selected = [spec for spec in specs if spec["demo_id"] in wanted]
    missing = wanted - {spec["demo_id"] for spec in selected}
    if missing:
        raise ValueError(f"Unknown demo ids: {sorted(missing)}")
    return selected


def run_process(
    command: list[str], cwd: Path, stdin: str, stdout: Path, stderr: Path
) -> tuple[int, bool]:
    with stdout.open("w", encoding="utf-8") as out, stderr.open(
        "w", encoding="utf-8"
    ) as err:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=err,
            text=True,
            start_new_session=True,
        )
        try:
            process.communicate(stdin, timeout=3600)
            return int(process.returncode), False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return int(process.returncode), True


def generate_one(spec: dict) -> dict:
    demo_id = spec["demo_id"]
    root = OUTPUT / demo_id
    manifest_path = root / "manifest.json"
    generated_path = root / "source/generated.py"
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "prompt_sha256": sha256(PROMPT),
        "schema_sha256": sha256(SCHEMA),
        "codex_sha256": sha256(CODEX),
        "codex_host_sha256": sha256(CODEX_HOST),
        "generator_sha256": sha256(Path(__file__)),
    }
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        old_identity = manifest.get("identity", {})
        if old_identity != identity:
            old_stable = {
                key: value
                for key, value in old_identity.items()
                if key != "generator_sha256"
            }
            new_stable = {
                key: value
                for key, value in identity.items()
                if key != "generator_sha256"
            }
            if old_stable != new_stable:
                raise RuntimeError(
                    f"{demo_id}: existing inputs differ; refusing to overwrite"
                )
            manifest.setdefault("runner_migrations", []).append(
                {
                    "at_utc": now(),
                    "old_generator_sha256": old_identity.get("generator_sha256"),
                    "new_generator_sha256": identity["generator_sha256"],
                    "reason": "Increase infrastructure-only retry allowance after pre-request sandbox and transport/capacity failures",
                }
            )
            manifest["identity"] = identity
            write_json(manifest_path, manifest)
        if manifest.get("generation_success"):
            if not generated_path.is_file() or sha256(generated_path) != manifest.get(
                "generated_code_sha256"
            ):
                raise RuntimeError(f"{demo_id}: generated-code hash mismatch")
            print(f"FULL_DEMO_GENERATION_REUSED {demo_id}", flush=True)
            return manifest
    else:
        manifest = {
            "demo_id": demo_id,
            "method": "gpt6_astra_xhigh",
            "model_requested": "gpt-6-astra",
            "reasoning_effort_requested": "xhigh",
            "logical_seed": spec["logical_seed"],
            "seed_supported_by_remote_model": False,
            "interface": "frozen_codex_cli_text_only",
            "identity": identity,
            "generation_success": False,
            "build_success": False,
            "render_success": False,
            "started_at_utc": now(),
            "attempts": [],
        }
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / "input/spec.json", spec)
    native_prompt = (
        PROMPT.read_text(encoding="utf-8")
        + "\n"
        + json.dumps(
            {"demo_spec": spec, "logical_seed": spec["logical_seed"]},
            ensure_ascii=False,
        )
    )
    write_json(
        root / "input/native_input.json",
        {
            "model": "gpt-6-astra",
            "reasoning_effort": "xhigh",
            "logical_seed": spec["logical_seed"],
            "prompt": native_prompt,
        },
    )
    version = subprocess.check_output([str(CODEX), "--version"], text=True).strip()
    if version != "codex-cli 0.153.4":
        raise RuntimeError(f"{demo_id}: frozen CLI version drift: {version}")
    manifest["codex_version"] = version

    attempt_number = len(manifest["attempts"]) + 1
    if attempt_number > 5:
        raise RuntimeError(f"{demo_id}: infrastructure retry budget exhausted")
    attempt_dir = root / f"logs/generation_{attempt_number:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    work = root / "work"
    work.mkdir(exist_ok=True)
    response_path = attempt_dir / "response.json"
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
        str(response_path),
        "-",
    ]
    attempt = {
        "index": attempt_number,
        "started_at_utc": now(),
        "command": command,
        "timeout_limit_s": 3600,
    }
    manifest["attempts"].append(attempt)
    write_json(manifest_path, manifest)
    code, timed_out = run_process(
        command,
        work,
        native_prompt,
        attempt_dir / "events.jsonl",
        attempt_dir / "stderr.log",
    )
    attempt.update(exit_code=code, timeout=timed_out, ended_at_utc=now())
    events = []
    for line in (attempt_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    attempt["thread_ids"] = [
        event["thread_id"] for event in events if event.get("type") == "thread.started"
    ]
    attempt["usage"] = [
        event.get("usage") for event in events if event.get("type") == "turn.completed"
    ]
    attempt["tool_events"] = [
        event.get("item", {}).get("type")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") not in {"agent_message", "error"}
    ]
    attempt["local_cli_errors"] = [
        event.get("item", {}).get("message")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "error"
    ]
    if code != 0 or timed_out or not response_path.is_file():
        manifest.update(
            failure_class="infrastructure",
            failure_reason="frozen Codex process failed or timed out",
            ended_at_utc=now(),
        )
        write_json(manifest_path, manifest)
        raise RuntimeError(
            f"{demo_id}: generation process failed (exit={code}, timeout={timed_out})"
        )
    try:
        response = json.loads(response_path.read_text(encoding="utf-8"))
        source = response["code"]
        check_code(source)
        if attempt["tool_events"]:
            raise ValueError(f"unexpected tool events: {attempt['tool_events']}")
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text(source.rstrip() + "\n", encoding="utf-8")
    except (
        KeyError,
        TypeError,
        ValueError,
        SyntaxError,
        json.JSONDecodeError,
    ) as error:
        manifest.update(
            failure_class="quality",
            failure_reason=f"{type(error).__name__}: {error}",
            ended_at_utc=now(),
        )
        write_json(manifest_path, manifest)
        raise RuntimeError(f"{demo_id}: invalid generated response: {error}") from error
    manifest.update(
        generation_success=True,
        failure_class=None,
        failure_reason=None,
        generated_code_sha256=sha256(generated_path),
        ended_at_utc=now(),
    )
    write_json(manifest_path, manifest)
    print(f"FULL_DEMO_GENERATION_COMPLETE {demo_id}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", default=[])
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    specs = select_specs(args.scene)
    failures: list[str] = []
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, len(specs)))
    ) as executor:
        pending = {
            executor.submit(generate_one, spec): spec["demo_id"] for spec in specs
        }
        for future in as_completed(pending):
            demo_id = pending[future]
            try:
                future.result()
            except Exception as error:  # preserve other independent generations
                failures.append(f"{demo_id}: {error}")
                print(
                    f"FULL_DEMO_GENERATION_FAILED {demo_id}: {error}",
                    file=sys.stderr,
                    flush=True,
                )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

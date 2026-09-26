#!/usr/bin/env python3
"""Generate six resumable Gemini 3.1 Pro connected indoor/outdoor scenes."""
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
OUTPUT = BASELINES / "annotations/gemini_3_1_pro/connect"
SPECS = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_specs.json"
)
PROMPT = (
    BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_prompt.txt"
)
SCHEMA = (
    BASELINES
    / "methods/gemini/protocol/generation/gemini_3_1_pro_connect_output.schema.json"
)
CONFIG = BASELINES / "methods/gemini/protocol/generation/gemini_3_1_pro.json"
RETRY_MIN_POLYGONS = 60_000
RETRY_MIN_OBJECTS = 250
MAX_ATTEMPTS = 4
sys.path.insert(0, str((BASELINES / "methods")))
from baselines.methods.gemini.adapter import check_code
from baselines.methods.gemini.adapter import client_environment
from baselines.methods.gemini.adapter import parse_response
from baselines.methods.gemini.adapter import verify_client


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
    command: list[str],
    cwd: Path,
    stdin: str,
    stdout: Path,
    stderr: Path,
    environment: dict[str, str],
) -> tuple[int, bool]:
    with stdout.open("w", encoding="utf-8") as out, stderr.open(
        "w", encoding="utf-8"
    ) as err:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=out,
            stderr=err,
            text=True,
            start_new_session=True,
        )
        try:
            process.communicate(stdin, timeout=1800)
            return int(process.returncode), False
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            return int(process.returncode), True


def generate_one(spec: dict, config: dict, client_version: str) -> dict:
    demo_id = spec["demo_id"]
    root = OUTPUT / demo_id
    manifest_path = root / "manifest.json"
    generated_path = root / "source/generated.py"
    helper = Path(config["client_helper"])
    binary = Path(config["antigravity_binary"])
    identity = {
        "spec_sha256": hashlib.sha256(
            json.dumps(spec, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "prompt_sha256": sha256(PROMPT),
        "schema_sha256": sha256(SCHEMA),
        "client_helper_sha256": sha256(helper),
        "antigravity_binary_sha256": sha256(binary),
        "generator_sha256": sha256(Path(__file__)),
    }
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing_identity = manifest.get("identity", {})
        differing_identity_keys = {
            key
            for key in set(existing_identity) | set(identity)
            if existing_identity.get(key) != identity.get(key)
        }
        if differing_identity_keys - {"generator_sha256"}:
            raise RuntimeError(
                f"{demo_id}: existing frozen inputs differ; refusing to overwrite"
            )
        if manifest.get("generation_success"):
            if not generated_path.is_file() or sha256(generated_path) != manifest.get(
                "generated_code_sha256"
            ):
                raise RuntimeError(f"{demo_id}: generated-code hash mismatch")
            print(f"GEMINI_CONNECT_GENERATION_REUSED {demo_id}", flush=True)
            return manifest
        if differing_identity_keys:
            manifest.setdefault("generator_revisions", []).append(
                {
                    "superseded_generator_sha256": existing_identity.get(
                        "generator_sha256"
                    ),
                    "replacement_generator_sha256": identity["generator_sha256"],
                    "reason": "retry-quality-feedback support",
                    "changed_at_utc": now(),
                }
            )
            manifest["identity"] = identity
    else:
        manifest = {
            "demo_id": demo_id,
            "method": "gemini_3_1_pro",
            "model_requested": "gemini-3.1-pro-high",
            "reasoning_effort_requested": "high",
            "logical_seed": spec["logical_seed"],
            "seed_supported_by_remote_model": False,
            "transport": "antigravity_cli_google_ai_pro_account",
            "auth_mode": "account_subscription_no_api_key",
            "api_key_billing_forbidden": True,
            "identity": identity,
            "generation_success": False,
            "build_success": False,
            "render_success": False,
            "started_at_utc": now(),
            "attempts": [],
        }
    root.mkdir(parents=True, exist_ok=True)
    work = root / "work"
    work.mkdir(exist_ok=True)
    write_json(root / "input/spec.json", spec)
    native_prompt = (
        PROMPT.read_text(encoding="utf-8")
        + "\n"
        + json.dumps(
            {"demo_spec": spec, "logical_seed": spec["logical_seed"]},
            ensure_ascii=False,
        )
    )
    rejected = manifest.get("rejected_generations", [])
    if rejected:
        native_prompt += (
            "\n\nRETRY QUALITY FEEDBACK (mandatory): the previous generated scene was rejected by "
            "an automated Blender geometry audit. Its last rejection was: "
            + rejected[-1]["reason"]
            + ". Return a substantially denser replacement, not a minor variation. Ensure the executed "
            f"scene contains at least {RETRY_MIN_POLYGONS:,} real mesh polygons and "
            f"{RETRY_MIN_OBJECTS} separately inspectable visible "
            "mesh objects, using bevel segments, curved profiles, joinery, furniture components, plants, "
            "architectural trim, paving and facade depth as meaningful geometric detail."
        )
    write_json(
        root / "input/native_input.json",
        {
            "model": "gemini-3.1-pro-high",
            "reasoning_effort": "high",
            "transport": "account_subscription_no_api_key",
            "logical_seed": spec["logical_seed"],
            "prompt": native_prompt,
        },
    )
    manifest["antigravity_version"] = client_version
    attempt_number = len(manifest["attempts"]) + 1
    if attempt_number > MAX_ATTEMPTS:
        raise RuntimeError(f"{demo_id}: retry budget exhausted")
    attempt_dir = root / f"logs/generation_{attempt_number:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    raw_response = attempt_dir / "response.txt"
    command = [str(helper)]
    attempt = {
        "index": attempt_number,
        "started_at_utc": now(),
        "command": [
            str(helper),
            "--model",
            "gemini-3.1-pro-high",
            "--account-subscription",
        ],
        "timeout_limit_s": 1800,
        "api_keys_removed_from_child_environment": [
            "GEMINI_API_KEY",
            "GOOGLE_API_KEY",
            "GOOGLE_GEMINI_BASE_URL",
        ],
    }
    manifest["attempts"].append(attempt)
    write_json(manifest_path, manifest)
    code, timed_out = run_process(
        command,
        work,
        native_prompt,
        raw_response,
        attempt_dir / "stderr.log",
        client_environment(1800),
    )
    attempt.update(exit_code=code, timeout=timed_out, ended_at_utc=now())
    if code != 0 or timed_out:
        manifest.update(
            failure_class="infrastructure",
            failure_reason="subscription client failed or timed out",
            ended_at_utc=now(),
        )
        write_json(manifest_path, manifest)
        raise RuntimeError(
            f"{demo_id}: client failed (exit={code}, timeout={timed_out})"
        )
    try:
        source = parse_response(raw_response.read_text(encoding="utf-8"))
        check_code(source)
        generated_path.parent.mkdir(parents=True, exist_ok=True)
        generated_path.write_text(source.rstrip() + "\n", encoding="utf-8")
    except (TypeError, ValueError, SyntaxError, json.JSONDecodeError) as error:
        manifest.update(
            failure_class="quality",
            failure_reason=f"{type(error).__name__}: {error}",
            ended_at_utc=now(),
        )
        write_json(manifest_path, manifest)
        raise RuntimeError(f"{demo_id}: invalid Gemini response: {error}") from error
    manifest.update(
        generation_success=True,
        failure_class=None,
        failure_reason=None,
        generated_code_sha256=sha256(generated_path),
        raw_response_sha256=sha256(raw_response),
        ended_at_utc=now(),
    )
    write_json(manifest_path, manifest)
    print(f"GEMINI_CONNECT_GENERATION_COMPLETE {demo_id}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", action="append", default=[])
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    client_version = verify_client(config)
    specs = select_specs(args.scene)
    failures: list[str] = []
    with ThreadPoolExecutor(
        max_workers=max(1, min(args.workers, 2, len(specs)))
    ) as executor:
        pending = {
            executor.submit(generate_one, spec, config, client_version): spec["demo_id"]
            for spec in specs
        }
        for future in as_completed(pending):
            demo_id = pending[future]
            try:
                future.result()
            except Exception as error:
                failures.append(f"{demo_id}: {error}")
                print(
                    f"GEMINI_CONNECT_GENERATION_FAILED {demo_id}: {error}",
                    file=sys.stderr,
                    flush=True,
                )
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

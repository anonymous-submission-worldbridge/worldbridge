#!/usr/bin/env python3
"""Audit local prerequisites; optionally check official API model access.

Uses Python's standard library and does not generate scenes or install packages.
Credentials and API error bodies are never included in the report.
"""
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
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def confined(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT):
        raise ValueError("Output/config path must be inside baselines")
    return resolved


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(args: list[str]) -> dict:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=45)
        return {
            "exit_code": result.returncode,
            "stdout": result.stdout[-8000:],
            "stderr": result.stderr[-2000:],
        }
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {"exit_code": None, "error_type": type(exc).__name__}


def credential(config: dict, key_file: Path | None) -> str | None:
    if key_file is None and os.environ.get(config["api_key_file_env"]):
        key_file = Path(os.environ[config["api_key_file_env"]])
    if key_file is not None:
        value = key_file.read_text().strip()
    else:
        value = os.environ.get(config["api_key_env"], "").strip()
    if value and (any(c.isspace() for c in value) or value.startswith("{")):
        raise ValueError(
            "Credential must be one raw API key; JSON/session credentials are not supported"
        )
    return value or None


def probe_api(base_url: str, key: str | None, use_proxy: bool = False) -> dict:
    if not key:
        return {"status": "missing_credential", "generation_tested": False}
    parsed = urlsplit(base_url)
    # This probe never forwards credentials to unverified gateways or redirects.
    if (
        parsed.scheme != "https"
        or parsed.netloc != "api.openai.com"
        or parsed.path.rstrip("/") != "/v1"
        or parsed.query
        or parsed.fragment
    ):
        return {
            "status": "custom_endpoint_requires_adapter",
            "generation_tested": False,
        }
    from urllib.request import HTTPRedirectHandler

    class NoRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = build_opener(
        ProxyHandler() if use_proxy else ProxyHandler({}), NoRedirect()
    )
    req = Request(
        "https://api.openai.com/v1/models/gpt-6-astra",
        headers={"Authorization": "Bearer " + key},
    )
    try:
        with opener.open(req, timeout=30) as response:
            data = json.load(response)
            return {
                "status": "model_visible"
                if data.get("id") == "gpt-6-astra"
                else "model_mismatch",
                "model": data.get("id"),
                "http_status": response.status,
                "generation_tested": False,
            }
    except HTTPError as exc:
        return {
            "status": "http_error",
            "http_status": exc.code,
            "generation_tested": False,
        }
    except (URLError, TimeoutError, OSError, ValueError) as exc:
        return {
            "status": "transport_or_decode_error",
            "error_type": type(exc).__name__,
            "generation_tested": False,
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config",
        type=Path,
        default=(ROOT / "methods/gpt/protocol/generation/gpt6_astra.json"),
    )
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results/gpt6_astra/preflight.json"
    )
    parser.add_argument("--api-key-file", type=Path)
    parser.add_argument("--probe-api", action="store_true")
    parser.add_argument(
        "--use-proxy", action="store_true", help="Explicit opt-in; default is direct"
    )
    args = parser.parse_args()
    config_path, output = confined(args.config), confined(args.output)
    config = json.loads(config_path.read_text())
    if config["model"] != "gpt-6-astra" or config["method"] != "gpt6_astra":
        raise ValueError("This preflight only accepts GPT-6 Astra")
    report = {
        "method": "gpt6_astra",
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "config_sha256": sha256(config_path),
        "specs": {},
        "blockers": [],
        "formal_runs_started": 0,
        "formal_metrics_computed": False,
    }
    for domain, relative in config["spec_files"].items():
        path = confined(ROOT / relative)
        report["specs"][domain] = {
            "sha256": sha256(path),
            "validation": command(
                [
                    sys.executable,
                    "-B",
                    str(ROOT / "tools/validate_specs.py"),
                    str(path),
                    "--domain",
                    domain,
                ]
            ),
        }
        if report["specs"][domain]["validation"]["exit_code"] != 0:
            report["blockers"].append("invalid_specs_" + domain)
    report["metrics_lock_sha256"] = sha256(ROOT / config["metrics_lock"])
    report["seeds_sha256"] = sha256(ROOT / config["seeds_file"])
    report["gpu"] = command(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
            "--format=csv,noheader",
        ]
    )
    if report["gpu"]["exit_code"] != 0:
        report["blockers"].append("gpu_unavailable_in_execution_context")
    report["blender"] = command([config["blender_executable"], "--version"])
    if report["blender"]["exit_code"] != 0:
        report["blockers"].append("blender_unavailable")
    probe = "import importlib.metadata as m,json; print(json.dumps({p:m.version(p) for p in ['torch','torchvision','pyiqa','transformers','numpy']}))"
    report["metrics_environment"] = command(
        [str(ROOT / config["metrics_python"]), "-B", "-c", probe]
    )
    if report["metrics_environment"]["exit_code"] != 0:
        report["blockers"].append("metrics_environment_unavailable")
    try:
        key = credential(config, args.api_key_file)
        report["credential_present"] = bool(key)
        report["api"] = (
            probe_api(config["base_url"], key, args.use_proxy)
            if args.probe_api
            else {"status": "not_probed", "generation_tested": False}
        )
    except (OSError, ValueError) as exc:
        key = None
        report["credential_present"] = False
        report["api"] = {"status": "credential_error", "error_type": type(exc).__name__}
    if not key:
        report["blockers"].append("api_credential_missing_or_invalid")
    if report["api"]["status"] != "model_visible":
        report["blockers"].append("api_model_access_unverified")
    if config["method_definition"] is None:
        report["blockers"].append("scene_construction_method_not_confirmed")
    report["blockers"].extend(
        [
            "generation_adapter_and_renderer_not_implemented",
            "pilot_not_run",
            "human_ratings_not_collected",
        ]
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 2 if report["blockers"] else 0


if __name__ == "__main__":
    raise SystemExit(main())

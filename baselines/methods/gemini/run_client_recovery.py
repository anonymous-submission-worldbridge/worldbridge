#!/usr/bin/env python3
"""Resume the frozen Gemini matrix with a locally frozen Antigravity 1.2.6 client."""
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


import json
from pathlib import Path
import subprocess
import sys


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str((ROOT / "methods")))
import baselines.methods.gemini.adapter as adapter
import baselines.methods.gemini.run as matrix


AMENDMENT = (
    ROOT
    / "methods/gemini/protocol/generation/gemini_3_1_pro_client_recovery_20260918.json"
)
FROZEN_CLIENT = ROOT / "runtime/gemini_3_1_pro_client_1_2_6/agy"


def verify_client_amended(config: dict) -> str:
    amendment = json.loads(AMENDMENT.read_text())
    helper = Path(config["client_helper"])
    expected = amendment["recovery_client"]
    if adapter.digest(helper) != config["client_helper_sha256"]:
        raise RuntimeError("Gemini account-auth helper hash drift")
    if adapter.digest(FROZEN_CLIENT) != expected["sha256"]:
        raise RuntimeError("Frozen Antigravity recovery client hash drift")
    installed = subprocess.check_output(
        [str(FROZEN_CLIENT), "--version"], text=True
    ).strip()
    if installed != expected["version"]:
        raise RuntimeError("Frozen Antigravity recovery version drift: " + installed)
    settings = Path.home() / ".gemini/antigravity-cli/settings.json"
    if settings.exists():
        payload = json.loads(settings.read_text())
        if payload.get("modelProvider") == "gemini":
            raise RuntimeError(
                "Gemini API-key provider mode is enabled; refusing to run"
            )
        if any(key in payload for key in ("apiKey", "geminiApiKey", "googleApiKey")):
            raise RuntimeError(
                "API-key field found in Antigravity settings; refusing to run"
            )
    return installed


original_environment = adapter.client_environment


def client_environment_amended(timeout_seconds: int) -> dict[str, str]:
    environment = original_environment(timeout_seconds)
    environment["AGY_PATH"] = str(FROZEN_CLIENT)
    return environment


def main() -> int:
    adapter.verify_client = verify_client_amended
    adapter.client_environment = client_environment_amended
    matrix.generate = adapter.generate
    return matrix.main()


if __name__ == "__main__":
    raise SystemExit(main())

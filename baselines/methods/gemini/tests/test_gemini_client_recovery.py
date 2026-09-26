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

import importlib.util
import json
from pathlib import Path


ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RECOVERY = load(
    "gemini_client_recovery", (ROOT / "methods/gemini/run_client_recovery.py")
)


def test_recovery_changes_only_client_infrastructure():
    amendment = json.loads(RECOVERY.AMENDMENT.read_text())
    assert amendment["stage"] == "formal_after_97_terminal_slots"
    assert amendment["classification"].startswith("client infrastructure recovery")
    assert amendment["recovery_client"]["version"] == "1.2.6"
    assert "no download" in amendment["recovery_client"]["storage"]


def test_recovery_environment_still_removes_api_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "forbidden")
    monkeypatch.setenv("GOOGLE_API_KEY", "forbidden")
    environment = RECOVERY.client_environment_amended(60)
    assert "GEMINI_API_KEY" not in environment
    assert "GOOGLE_API_KEY" not in environment
    assert environment["AGY_PATH"] == str(RECOVERY.FROZEN_CLIENT)

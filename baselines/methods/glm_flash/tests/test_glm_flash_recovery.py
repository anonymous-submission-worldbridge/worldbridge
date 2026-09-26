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

import pytest


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPEC = importlib.util.spec_from_file_location(
    "recover_glm53_flash_generation",
    (ROOT / "methods/glm_flash/tools/recover_glm_flash_generation.py"),
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_quota_amendment_never_allows_quality_retry():
    amendment = json.loads(
        (
            (
                ROOT
                / "methods/glm_flash/protocol/generation/glm53_flash_quota_recovery_20260917.json"
            )
        ).read_text()
    )
    assert any("quality failure" in rule for rule in amendment["scope"]["forbidden"])
    assert amendment["scope"]["recovery_attempts_per_run_per_scheduler_pass"] == 1


def test_bounded_scheduler_stops_without_refilling(monkeypatch, tmp_path):
    calls = []

    def fake_run(spec, seed, data_root):
        calls.append((spec["spec_id"], seed))
        failure = "infrastructure" if spec["spec_id"] == "fail" else "quality"
        return {"generation_success": False, "failure_class": failure}

    monkeypatch.setattr(MODULE, "run_one", fake_run)
    items = [({"spec_id": name}, 0) for name in ("fail", "active", "must_not_start")]
    with pytest.raises(RuntimeError, match="paused"):
        MODULE.bounded_run(items, tmp_path, workers=2)
    assert sorted(calls) == [("active", 0), ("fail", 0)]


def test_recovery_source_contains_no_credential():
    source = (
        (ROOT / "methods/glm_flash/tools/recover_glm_flash_generation.py")
    ).read_text()
    assert "GLM53_API_KEY" in source
    assert "ef18f136" not in source

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


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADAPTER = load("gemini_3_1_pro", (ROOT / "methods/gemini/adapter.py"))
MATRIX = load("gemini_3_1_pro_matrix", (ROOT / "methods/gemini/run.py"))
AUDIT = load("gemini_3_1_pro_audit", (ROOT / "methods/gemini/tools/audit_gemini.py"))


def test_protocol_forbids_api_key_transport():
    protocol = json.loads(
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    assert protocol["model"] == "gemini-3.1-pro-high"
    assert protocol["transport"] == "antigravity_cli_google_ai_pro_account"
    assert protocol["auth_mode"] == "account_subscription_no_api_key"
    assert protocol["reasoning_effort"] == "high"
    assert protocol["client_mode"] == "plan"
    assert "api" not in protocol["transport"].lower()


def test_client_environment_removes_api_keys(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "forbidden")
    monkeypatch.setenv("GOOGLE_API_KEY", "forbidden")
    monkeypatch.setenv("GOOGLE_GEMINI_BASE_URL", "forbidden")
    environment = ADAPTER.client_environment(123)
    assert "GEMINI_API_KEY" not in environment
    assert "GOOGLE_API_KEY" not in environment
    assert "GOOGLE_GEMINI_BASE_URL" not in environment
    assert environment["GEMINI31_PRINT_TIMEOUT"] == "123s"
    assert environment["AGY_CLI_DISABLE_AUTO_UPDATE"] == "1"


def test_recovered_helper_is_subscription_only_and_version_pinned():
    protocol = json.loads(
        ((ROOT / "methods/gemini/protocol/generation/gemini_3_1_pro.json")).read_text()
    )
    helper = Path(protocol["client_helper"])
    source = helper.read_text()
    assert "GEMINI_API_KEY" in source and "GOOGLE_API_KEY" in source
    assert "GOOGLE_GEMINI_BASE_URL" in source
    assert "--model gemini-3.1-pro-high" in source
    assert "--effort high" in source
    assert "--mode plan" in source
    assert Path(protocol["antigravity_binary"]).name == "agy"


def test_parse_plain_and_fenced_json():
    expected = "def build_scene(seed):\n    return None"
    assert ADAPTER.parse_response(json.dumps({"code": expected})) == expected
    assert (
        ADAPTER.parse_response("```json\n" + json.dumps({"code": expected}) + "\n```")
        == expected
    )


@pytest.mark.parametrize(
    "payload", ["nonsense", "{}", '{"code": 3}', '{"code":"x","extra":1}']
)
def test_parse_rejects_non_schema_response(payload):
    with pytest.raises((ValueError, json.JSONDecodeError)):
        ADAPTER.parse_response(payload)


def test_code_policy():
    ADAPTER.check_code("def build_scene(seed):\n    return seed\n")
    with pytest.raises(ValueError):
        ADAPTER.check_code("import os\ndef build_scene(seed):\n    return seed\n")
    with pytest.raises(ValueError):
        ADAPTER.check_code("def nope(seed):\n    return seed\n")


def test_selection_is_five_specs_times_two_seeds_per_domain():
    tasks = MATRIX.select_tasks("both", True, None, None)
    assert len(tasks) == 20
    assert {spec["domain"] for spec, _ in tasks} == {"indoor", "urban"}
    assert {seed for _, seed in tasks} == {0, 1}


def test_confined_rejects_outside_baselines(tmp_path):
    with pytest.raises(ValueError):
        ADAPTER.confined(tmp_path)


def test_host_execution_amendment_is_pre_metric_and_preserves_ast_gate():
    amendment = json.loads(
        (
            (
                ROOT
                / "methods/gemini/protocol/generation/gemini_3_1_pro_pilot_infrastructure_amendment_20260917.json"
            )
        ).read_text()
    )
    assert amendment["stage"] == "pilot_before_any_metric_or_formal_run"
    assert "AST" in " ".join(amendment["unchanged"] + amendment["safety"])
    source = ((ROOT / "methods/gemini/run.py")).read_text()
    assert '"bwrap"' not in source
    assert "--factory-startup" in source


def test_completed_pilot_audit_with_metrics_passes():
    report = AUDIT.audit(ROOT / "data/gemini_3_1_pro_pilot", True, True)
    assert report["passed"]
    assert report["expected"] == report["terminal"] == 20
    assert report["success"] == 15
    assert report["quality_failure"] == 5

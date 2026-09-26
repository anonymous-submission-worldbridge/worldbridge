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
from unittest.mock import patch

import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
SPEC = importlib.util.spec_from_file_location(
    "astra_preflight", (ROOT / "methods/gpt/tools/preflight_gpt.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_output_cannot_escape_baselines():
    with pytest.raises(ValueError):
        MODULE.confined(ROOT / "../outside.json")


def test_missing_key_does_not_issue_request():
    with patch.object(MODULE, "build_opener") as opener:
        assert (
            MODULE.probe_api("https://api.openai.com/v1", None)["status"]
            == "missing_credential"
        )
        opener.assert_not_called()


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "https://api.openai.com.evil.test/v1",
        "https://gateway.example/v1",
    ],
)
def test_key_is_not_forwarded_to_unverified_endpoint(url):
    with patch.object(MODULE, "build_opener") as opener:
        assert (
            MODULE.probe_api(url, "secret-value")["status"]
            == "custom_endpoint_requires_adapter"
        )
        opener.assert_not_called()


def test_http_error_report_does_not_include_secrets():
    with patch.object(MODULE, "build_opener") as opener:
        opener.return_value.open.side_effect = MODULE.HTTPError(
            "https://api.openai.com/v1", 401, "secret-value", {}, None
        )
        report = MODULE.probe_api("https://api.openai.com/v1", "secret-value")
        assert report["http_status"] == 401
        assert "secret-value" not in json.dumps(report)


def test_model_visibility_does_not_claim_generation():
    with patch.object(MODULE, "build_opener") as opener:
        response = opener.return_value.open.return_value.__enter__.return_value
        response.read.return_value = '{"id":"gpt-6-astra"}'
        response.status = 200
        report = MODULE.probe_api("https://api.openai.com/v1", "secret-value")
        assert report["status"] == "model_visible"
        assert report["generation_tested"] is False

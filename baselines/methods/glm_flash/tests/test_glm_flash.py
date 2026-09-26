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
    "glm53_flash_adapter", (ROOT / "methods/glm_flash/adapter.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_protocol_identity_and_no_embedded_secret():
    protocol = json.loads(
        ((ROOT / "methods/glm_flash/protocol/generation/glm53_flash.json")).read_text()
    )
    assert protocol["method"] == "glm53_flash"
    assert protocol["model"] == "glm-5.3-flash"
    assert protocol["endpoint"] == "https://open.bigmodel.cn/api/coding/paas/v4"
    assert protocol["thinking"] == {"type": "disabled"}
    opencode = json.loads(
        (
            (ROOT / "methods/glm_flash/protocol/generation/glm53_flash_opencode.json")
        ).read_text()
    )
    assert opencode["agent"]["scene"]["steps"] == 2
    assert opencode["agent"]["scene"]["permission"] == {"*": "deny"}
    sources = "".join(
        (ROOT / path).read_text()
        for path in (
            "methods/glm_flash/adapter.py",
            "methods/glm_flash/protocol/generation/glm53_flash.json",
            "methods/glm_flash/protocol/generation/glm53_flash_opencode.json",
        )
    )
    assert "ef18f136" not in sources


def test_code_policy_accepts_scene_and_rejects_io():
    MODULE.check_code("import bpy\ndef build_scene(seed):\n    return seed\n")
    with pytest.raises(ValueError, match="Unsupported builtin"):
        MODULE.check_code(
            "import bpy\ndef build_scene(seed):\n    open('/tmp/x', 'w')\n"
        )


def test_response_requires_exclusive_target_model(tmp_path):
    session = "ses_test"
    events = [
        {"type": "step_start", "sessionID": session, "part": {}},
        {
            "type": "text",
            "sessionID": session,
            "part": {
                "text": json.dumps(
                    {"code": "import bpy\ndef build_scene(seed):\n    return seed\n"}
                ),
            },
        },
        {
            "type": "step_finish",
            "sessionID": session,
            "part": {
                "reason": "stop",
                "tokens": {"input": 1, "output": 1, "reasoning": 0},
            },
        },
    ]
    path = tmp_path / "events.jsonl"
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    result, code = MODULE._parse_response(path)
    assert "build_scene" in code
    assert result["session_id"] == session
    events.append({"type": "tool_call", "sessionID": session, "part": {}})
    path.write_text("".join(json.dumps(event) + "\n" for event in events))
    with pytest.raises(ValueError, match="tool"):
        MODULE._parse_response(path)


def test_auth_environment_requires_out_of_band_token(tmp_path, monkeypatch):
    monkeypatch.delenv("GLM53_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="out of band"):
        MODULE._opencode_environment()
    monkeypatch.setenv("GLM53_API_KEY", "sentinel-secret")
    environment = MODULE._opencode_environment()
    assert environment["GLM53_API_KEY"] == "sentinel-secret"
    assert environment["OPENCODE_DISABLE_MODELS_FETCH"] == "1"

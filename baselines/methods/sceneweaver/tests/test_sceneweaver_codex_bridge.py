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

import base64
import importlib.util
import json
from pathlib import Path


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
MODULE_PATH = (
    ROOT / "methods/sceneweaver/runtime/sceneweaver_pipeline/codex_llm_bridge.py"
)
SPEC = importlib.util.spec_from_file_location("sceneweaver_codex_bridge", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class Function:
    def __init__(self, name, arguments):
        self.name = name
        self.arguments = arguments


class ToolCall:
    def __init__(self, id, function):
        self.id = id
        self.function = function


class Message:
    def __init__(self, role, content=None, tool_calls=None, base64_image=None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.base64_image = base64_image

    @classmethod
    def assistant_message(cls, content):
        return cls("assistant", content)


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "terminate",
            "description": "Finish the scene",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def test_response_schema_is_strict_and_names_only_declared_tools():
    schema = MODULE.response_schema(["terminate", "add_gpt"])
    assert schema["additionalProperties"] is False
    assert schema["properties"]["tool_name"]["enum"] == ["add_gpt", "terminate"]


def test_prompt_excludes_base64_bytes_and_tracks_attachment():
    encoded = base64.b64encode(b"fake-jpeg").decode()
    prompt, images = MODULE.build_prompt(
        [Message("user", "inspect this", base64_image=encoded)], [], TOOLS, "required"
    )
    payload = json.loads(prompt)
    assert encoded not in prompt
    assert images == [encoded]
    assert payload["conversation"][0]["image_attachment_index"] == 0


def test_parse_response_builds_one_compact_tool_call():
    response = MODULE.parse_response(
        {
            "content": "done",
            "tool_name": "terminate",
            "arguments_json": '{"success": true}',
        },
        {"terminate"},
        Message,
        Function,
        ToolCall,
        "codex_call_0001",
    )
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].function.name == "terminate"
    assert response.tool_calls[0].function.arguments == '{"success":true}'


def test_parse_response_leaves_invalid_name_for_agent_repair():
    response = MODULE.parse_response(
        {"content": "bad", "tool_name": "undeclared", "arguments_json": "{}"},
        {"terminate"},
        Message,
        Function,
        ToolCall,
        "codex_call_0001",
    )
    assert response.tool_calls is None


def test_auxiliary_payload_strips_data_url_and_preserves_text():
    encoded = base64.b64encode(b"fake-png").decode()
    payload = {
        "messages": [
            {"role": "system", "content": "return json"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "inspect"},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{encoded}"},
                    },
                ],
            },
        ],
        "temperature": 0.0,
    }
    prompt, images = MODULE.build_text_prompt(payload)
    decoded = json.loads(prompt)
    assert encoded not in prompt
    assert images == [f"data:image/png;base64,{encoded}"]
    assert decoded["conversation"][1]["content"][0]["text"] == "inspect"
    assert decoded["conversation"][1]["content"][1] == {
        "type": "image_attachment",
        "image_attachment_index": 0,
    }
    assert decoded["source_request_parameters"]["temperature"] == 0.0

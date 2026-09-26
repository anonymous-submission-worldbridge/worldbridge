#!/usr/bin/env python3
"""One-call, non-formal smoke test for the SceneWeaver Codex bridge."""

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
import importlib.util
import json
import os
from pathlib import Path


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
BRIDGE_PATH = (
    ROOT / "methods/sceneweaver/runtime/sceneweaver_pipeline/codex_llm_bridge.py"
)


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "results/sceneweaver/codex_bridge_probe",
    )
    args = parser.parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.relative_to(ROOT.resolve())
    output_dir.mkdir(parents=True, exist_ok=True)
    os.environ["save_dir"] = str(output_dir)
    os.environ.setdefault("SCENEWEAVER_CODEX_MODEL", "gpt-6-astra")
    os.environ.setdefault("SCENEWEAVER_CODEX_REASONING_EFFORT", "low")

    spec = importlib.util.spec_from_file_location(
        "sceneweaver_codex_bridge", BRIDGE_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {BRIDGE_PATH}")
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    tools = [
        {
            "type": "function",
            "function": {
                "name": "terminate",
                "description": "Finish the probe.",
                "parameters": {
                    "type": "object",
                    "properties": {"reason": {"type": "string"}},
                    "required": ["reason"],
                    "additionalProperties": False,
                },
            },
        }
    ]
    response = bridge.ask_tool_with_codex(
        messages=[Message("user", "Select terminate with reason set to probe_ok.")],
        system_msgs=[Message("system", "This is a format probe only.")],
        tools=tools,
        tool_choice="required",
        message_class=Message,
        function_class=Function,
        tool_call_class=ToolCall,
        timeout_s=180,
    )
    call = response.tool_calls[0]
    arguments = json.loads(call.function.arguments)
    auxiliary = bridge.send_text_with_codex(
        {
            "messages": [
                {
                    "role": "system",
                    "content": "Return only a compact JSON object.",
                },
                {
                    "role": "user",
                    "content": 'Return {"probe":"auxiliary_ok"}.',
                },
            ],
            "temperature": 0.0,
        },
        timeout_s=180,
    )
    auxiliary_payload = json.loads(auxiliary)
    result = {
        "success": call.function.name == "terminate"
        and arguments.get("reason") == "probe_ok"
        and auxiliary_payload.get("probe") == "auxiliary_ok",
        "tool_name": call.function.name,
        "arguments": arguments,
        "auxiliary": auxiliary_payload,
    }
    (output_dir / "probe_result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))
    return 0 if result["success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

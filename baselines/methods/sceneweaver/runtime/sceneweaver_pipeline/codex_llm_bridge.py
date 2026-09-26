#!/usr/bin/env python3
"""Use saved Codex ChatGPT authentication as a SceneWeaver tool-call backend.

The bridge deliberately exposes no repository tools to the model.  Each
non-interactive Codex invocation receives the bounded SceneWeaver history and
declared tool schemas, then returns exactly one JSON-encoded tool call.  The
normal SceneWeaver agent remains responsible for validating and executing it.
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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Any


FROZEN_CODEX_CLI = Path(
    f"{_wb_WORLDBRIDGE_ROOT}/baselines/tools/codex-sceneweaver-frozen"
)


def resolve_codex_cli() -> str:
    """Resolve Codex without depending on a mutable global npm symlink."""

    configured = os.environ.get("SCENEWEAVER_CODEX_CLI")
    candidates = [configured, shutil.which("codex"), str(FROZEN_CODEX_CLI)]
    for candidate in candidates:
        if candidate and Path(candidate).is_file() and os.access(candidate, os.X_OK):
            return str(Path(candidate).resolve())
    raise FileNotFoundError(
        "Codex CLI is unavailable from SCENEWEAVER_CODEX_CLI, PATH, and the "
        f"frozen local fallback {FROZEN_CODEX_CLI}"
    )


def _value(item: Any, name: str, default: Any = None) -> Any:
    if isinstance(item, dict):
        return item.get(name, default)
    return getattr(item, name, default)


def _role_value(role: Any) -> str:
    return str(getattr(role, "value", role))


def serialize_messages(messages: list[Any]) -> tuple[list[dict[str, Any]], list[str]]:
    """Serialize messages without embedding image bytes in the text prompt."""

    serialized: list[dict[str, Any]] = []
    images: list[str] = []
    for message in messages:
        record: dict[str, Any] = {
            "role": _role_value(_value(message, "role", "user")),
            "content": _value(message, "content"),
        }
        calls = _value(message, "tool_calls") or []
        if calls:
            record["tool_calls"] = []
            for call in calls:
                function = _value(call, "function")
                record["tool_calls"].append(
                    {
                        "id": _value(call, "id"),
                        "name": _value(function, "name"),
                        "arguments": _value(function, "arguments"),
                    }
                )
        name = _value(message, "name")
        tool_call_id = _value(message, "tool_call_id")
        if name is not None:
            record["name"] = name
        if tool_call_id is not None:
            record["tool_call_id"] = tool_call_id
        encoded = _value(message, "base64_image")
        if encoded:
            record["image_attachment_index"] = len(images)
            images.append(str(encoded))
        serialized.append(record)
    return serialized, images


def response_schema(tool_names: list[str]) -> dict[str, Any]:
    if not tool_names:
        raise ValueError("Codex SceneWeaver bridge requires at least one declared tool")
    return {
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "content": {"type": "string"},
            "tool_name": {"type": "string", "enum": sorted(tool_names)},
            "arguments_json": {"type": "string"},
        },
        "required": ["content", "tool_name", "arguments_json"],
        "additionalProperties": False,
    }


def build_prompt(
    messages: list[Any],
    system_msgs: list[Any] | None,
    tools: list[dict[str, Any]],
    tool_choice: Any,
) -> tuple[str, list[str]]:
    history, history_images = serialize_messages(
        list(system_msgs or []) + list(messages)
    )
    names = [
        str(tool["function"]["name"])
        for tool in tools
        if isinstance(tool, dict)
        and tool.get("type") == "function"
        and isinstance(tool.get("function"), dict)
        and tool["function"].get("name")
    ]
    instruction = {
        "task": (
            "Act only as the next-step planner inside SceneWeaver. Select exactly one "
            "declared tool. Do not use shell, filesystem, web, MCP, or any Codex tool. "
            "Return only the object required by the output schema. Put a concise planning "
            "note in content. Put a JSON object encoded as a string in arguments_json; it "
            "must conform exactly to the selected SceneWeaver tool's parameters schema."
        ),
        "tool_choice": _role_value(tool_choice),
        "declared_tools": tools,
        "conversation": history,
        "image_note": (
            "CLI image attachments correspond to image_attachment_index values in the "
            "conversation, in ascending order."
        ),
        "required_response_example": {
            "content": "brief next-step rationale",
            "tool_name": names[0] if names else "",
            "arguments_json": "{}",
        },
    }
    return json.dumps(instruction, ensure_ascii=False, sort_keys=True), history_images


def parse_response(
    payload: dict[str, Any],
    allowed_names: set[str],
    message_class: Any,
    function_class: Any,
    tool_call_class: Any,
    call_id: str,
) -> Any:
    content = payload.get("content", "")
    name = payload.get("tool_name")
    arguments = payload.get("arguments_json")
    if not isinstance(content, str):
        content = str(content)
    if name not in allowed_names or not isinstance(arguments, str):
        return message_class.assistant_message(content)
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        parsed = None
    if not isinstance(parsed, dict):
        return message_class(
            role="assistant",
            content=content,
            tool_calls=[
                tool_call_class(
                    id=call_id,
                    function=function_class(name=name, arguments=arguments),
                )
            ],
        )
    compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return message_class(
        role="assistant",
        content=content,
        tool_calls=[
            tool_call_class(
                id=call_id,
                function=function_class(name=name, arguments=compact),
            )
        ],
    )


def _allocate_call_dir(root: Path) -> tuple[int, Path]:
    root.mkdir(parents=True, exist_ok=True)
    existing = []
    for path in root.glob("call_*"):
        try:
            existing.append(int(path.name.split("_", 1)[1]))
        except (IndexError, ValueError):
            continue
    index = max(existing, default=0) + 1
    while True:
        call_dir = root / f"call_{index:04d}"
        try:
            call_dir.mkdir()
            return index, call_dir
        except FileExistsError:
            index += 1


def _write_image(encoded: str, destination: Path) -> str:
    if encoded.startswith("data:") and "," in encoded:
        encoded = encoded.split(",", 1)[1]
    data = base64.b64decode(encoded, validate=True)
    destination.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def _stop_process(process: subprocess.Popen[Any]) -> None:
    """Stop one unresponsive CLI process without leaving a child behind."""

    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _run_codex_process(
    command: list[str],
    prompt: str,
    work_dir: Path,
    call_dir: Path,
    response_path: Path,
    timeout_s: int,
) -> tuple[subprocess.Popen[Any], bool, list[dict[str, Any]]]:
    """Run Codex, retrying only a transport that emits no first event.

    A successful Codex transport writes ``thread.started`` almost immediately,
    even when model inference itself takes longer.  A zero-byte event stream is
    therefore an infrastructure stall, not a SceneWeaver semantic planner step.
    Retrying it here preserves the frozen 15-step planner budget.
    """

    startup_timeout_s = max(
        15,
        int(os.environ.get("SCENEWEAVER_CODEX_STARTUP_TIMEOUT_S", "120")),
    )
    startup_retries = max(
        0,
        int(os.environ.get("SCENEWEAVER_CODEX_STARTUP_RETRIES", "2")),
    )
    records: list[dict[str, Any]] = []
    process: subprocess.Popen[Any] | None = None
    timed_out = False

    for transport_attempt in range(1, startup_retries + 2):
        events_path = call_dir / "events.jsonl"
        stderr_path = call_dir / "stderr.log"
        if response_path.exists():
            response_path.unlink()
        started = time.monotonic()
        no_start_event = False
        with events_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            process = subprocess.Popen(
                command,
                cwd=work_dir,
                stdin=subprocess.PIPE,
                stdout=stdout,
                stderr=stderr,
                text=True,
            )
            try:
                try:
                    process.communicate(
                        prompt,
                        timeout=min(timeout_s, startup_timeout_s),
                    )
                except subprocess.TimeoutExpired:
                    elapsed = time.monotonic() - started
                    if events_path.stat().st_size == 0:
                        no_start_event = True
                        _stop_process(process)
                    else:
                        remaining_s = max(1.0, timeout_s - elapsed)
                        try:
                            process.communicate(timeout=remaining_s)
                        except subprocess.TimeoutExpired:
                            timed_out = True
                            _stop_process(process)
                if process.poll() is None:
                    if time.monotonic() - started >= timeout_s:
                        timed_out = True
                        _stop_process(process)
                    else:
                        _stop_process(process)
            except BaseException:
                _stop_process(process)
                raise

        record = {
            "transport_attempt": transport_attempt,
            "wall_time_s": time.monotonic() - started,
            "exit_code": process.returncode,
            "no_start_event": no_start_event,
            "event_bytes": events_path.stat().st_size,
            "stderr_bytes": stderr_path.stat().st_size,
        }
        records.append(record)
        if no_start_event and transport_attempt <= startup_retries:
            events_path.replace(
                call_dir / f"events.no_start_{transport_attempt:02d}.jsonl"
            )
            stderr_path.replace(
                call_dir / f"stderr.no_start_{transport_attempt:02d}.log"
            )
            continue
        if no_start_event:
            timed_out = True
        break

    assert process is not None
    return process, timed_out, records


def serialize_openai_payload(
    payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Serialize an OpenAI-style chat payload without copying image bytes.

    SceneWeaver's auxiliary GPT4o wrapper uses multimodal OpenAI message
    dictionaries for scene evaluation and per-tool JSON generation.  Codex
    receives the same text plus the images as CLI attachments.
    """

    conversation: list[dict[str, Any]] = []
    images: list[str] = []
    for raw_message in payload.get("messages", []):
        if not isinstance(raw_message, dict):
            conversation.append({"role": "user", "content": str(raw_message)})
            continue
        record: dict[str, Any] = {
            "role": str(raw_message.get("role", "user")),
            "content": [],
        }
        content = raw_message.get("content", "")
        if isinstance(content, str):
            record["content"] = content
        elif isinstance(content, list):
            blocks: list[dict[str, Any]] = []
            for block in content:
                if not isinstance(block, dict):
                    blocks.append({"type": "text", "text": str(block)})
                    continue
                if block.get("type") != "image_url":
                    blocks.append(dict(block))
                    continue
                image_url = block.get("image_url", {})
                url = (
                    image_url.get("url")
                    if isinstance(image_url, dict)
                    else str(image_url)
                )
                if isinstance(url, str) and url.startswith("data:"):
                    blocks.append(
                        {
                            "type": "image_attachment",
                            "image_attachment_index": len(images),
                        }
                    )
                    images.append(url)
                else:
                    blocks.append({"type": "image_url", "url": url})
            record["content"] = blocks
        else:
            record["content"] = str(content)
        conversation.append(record)
    return conversation, images


def build_text_prompt(payload: dict[str, Any]) -> tuple[str, list[str]]:
    conversation, images = serialize_openai_payload(payload)
    instruction = {
        "task": (
            "Act only as SceneWeaver's internal language-model component. Follow the "
            "original conversation exactly and produce only the requested final response. "
            "Do not use shell, filesystem, web, MCP, or any Codex tool. If JSON is "
            "requested, return complete valid JSON in precisely the requested shape, with "
            "no analysis or commentary."
        ),
        "conversation": conversation,
        "image_note": (
            "CLI image attachments correspond to image_attachment_index values in the "
            "conversation, in ascending order."
        ),
        "source_request_parameters": {
            key: payload.get(key)
            for key in ("temperature", "max_tokens", "response_format")
            if key in payload
        },
    }
    return json.dumps(instruction, ensure_ascii=False, sort_keys=True), images


def send_text_with_codex(payload: dict[str, Any], timeout_s: int) -> str:
    """Run one SceneWeaver auxiliary chat request through saved Codex auth."""

    save_dir = Path(os.environ["save_dir"]).resolve()
    bridge_root = save_dir / "codex_bridge"
    index, call_dir = _allocate_call_dir(bridge_root / "calls")
    work_dir = bridge_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt, encoded_images = build_text_prompt(payload)
    (call_dir / "request.json").write_text(prompt + "\n", encoding="utf-8")

    image_paths: list[Path] = []
    image_records: list[dict[str, Any]] = []
    for image_index, encoded in enumerate(encoded_images):
        path = call_dir / f"input_{image_index:02d}.jpg"
        digest = _write_image(encoded, path)
        image_paths.append(path)
        image_records.append(
            {"path": path.name, "sha256": digest, "size_bytes": path.stat().st_size}
        )

    model = os.environ.get("SCENEWEAVER_CODEX_MODEL", "gpt-6-astra")
    effort = os.environ.get("SCENEWEAVER_CODEX_REASONING_EFFORT", "medium")
    codex = resolve_codex_cli()
    response_path = call_dir / "response.txt"
    command = [
        codex,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--json",
        "-C",
        str(work_dir),
        "-o",
        str(response_path),
    ]
    for image_path in image_paths:
        command.extend(["--image", str(image_path)])
    command.append("-")

    metadata: dict[str, Any] = {
        "backend": "codex_cli_saved_chatgpt_login",
        "call_kind": "sceneweaver_auxiliary_text",
        "model_requested": model,
        "reasoning_effort": effort,
        "command": command,
        "images": image_records,
        "started_epoch_s": time.time(),
        "timeout_s": timeout_s,
    }
    (call_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    process, timed_out, transport_attempts = _run_codex_process(
        command,
        prompt,
        work_dir,
        call_dir,
        response_path,
        timeout_s,
    )

    events: list[dict[str, Any]] = []
    for line in (
        (call_dir / "events.jsonl")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines()
    ):
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    item_types = [
        event.get("item", {}).get("type")
        for event in events
        if event.get("type") == "item.completed"
    ]
    forbidden_item_types = {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "computer_action",
    }
    metadata.update(
        {
            "ended_epoch_s": time.time(),
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "thread_ids": [
                event.get("thread_id")
                for event in events
                if event.get("type") == "thread.started"
            ],
            "usage": [
                event.get("usage")
                for event in events
                if event.get("type") == "turn.completed"
            ],
            "item_types": item_types,
            "transport_attempts": transport_attempts,
            "forbidden_item_types": sorted(
                {
                    item_type
                    for item_type in item_types
                    if item_type in forbidden_item_types
                }
            ),
        }
    )
    (call_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if (
        timed_out
        or process.returncode != 0
        or not response_path.is_file()
        or metadata["forbidden_item_types"]
    ):
        diagnostic = (
            (call_dir / "stderr.log").read_text(encoding="utf-8", errors="replace")
            + "\n"
            + (call_dir / "events.jsonl").read_text(encoding="utf-8", errors="replace")
        ).lower()
        if any(
            token in diagnostic
            for token in ("usage limit", "rate limit", "quota", "try again at")
        ):
            print(
                "SCENEWEAVER_CODEX_LIMIT "
                + json.dumps(
                    {"call": index, "model": model, "run_dir": str(save_dir)},
                    sort_keys=True,
                ),
                flush=True,
            )
        raise RuntimeError(
            f"Codex auxiliary call {index} failed exit={process.returncode} "
            f"timeout={timed_out} forbidden_items={metadata['forbidden_item_types']}; "
            f"see {call_dir}"
        )

    content = response_path.read_text(encoding="utf-8")
    if not content.strip():
        raise RuntimeError(f"Empty Codex auxiliary response in {response_path}")
    print(
        "SCENEWEAVER_CODEX_TEXT "
        + json.dumps(
            {"call": index, "model": model, "run_dir": str(save_dir)},
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return content


def ask_tool_with_codex(
    messages: list[Any],
    system_msgs: list[Any] | None,
    tools: list[dict[str, Any]] | None,
    tool_choice: Any,
    message_class: Any,
    function_class: Any,
    tool_call_class: Any,
    timeout_s: int,
) -> Any:
    declared_tools = list(tools or [])
    allowed_names = {
        str(tool["function"]["name"])
        for tool in declared_tools
        if isinstance(tool, dict)
        and tool.get("type") == "function"
        and isinstance(tool.get("function"), dict)
        and tool["function"].get("name")
    }
    if not allowed_names:
        raise ValueError("No declared SceneWeaver tools were supplied to Codex")

    save_dir = Path(os.environ["save_dir"]).resolve()
    bridge_root = save_dir / "codex_bridge"
    index, call_dir = _allocate_call_dir(bridge_root / "calls")
    work_dir = bridge_root / "work"
    work_dir.mkdir(parents=True, exist_ok=True)
    prompt, encoded_images = build_prompt(
        messages, system_msgs, declared_tools, tool_choice
    )
    schema = response_schema(sorted(allowed_names))
    (call_dir / "request.json").write_text(prompt + "\n", encoding="utf-8")
    (call_dir / "output_schema.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    image_paths: list[Path] = []
    image_records: list[dict[str, Any]] = []
    for image_index, encoded in enumerate(encoded_images):
        path = call_dir / f"input_{image_index:02d}.jpg"
        digest = _write_image(encoded, path)
        image_paths.append(path)
        image_records.append(
            {"path": path.name, "sha256": digest, "size_bytes": path.stat().st_size}
        )

    model = os.environ.get("SCENEWEAVER_CODEX_MODEL", "gpt-6-astra")
    effort = os.environ.get("SCENEWEAVER_CODEX_REASONING_EFFORT", "medium")
    codex = resolve_codex_cli()
    response_path = call_dir / "response.json"
    command = [
        codex,
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--skip-git-repo-check",
        "--sandbox",
        "read-only",
        "--model",
        model,
        "-c",
        f'model_reasoning_effort="{effort}"',
        "--json",
        "--output-schema",
        str(call_dir / "output_schema.json"),
        "-C",
        str(work_dir),
        "-o",
        str(response_path),
    ]
    for image_path in image_paths:
        command.extend(["--image", str(image_path)])
    command.append("-")

    metadata: dict[str, Any] = {
        "backend": "codex_cli_saved_chatgpt_login",
        "model_requested": model,
        "reasoning_effort": effort,
        "command": command,
        "images": image_records,
        "started_epoch_s": time.time(),
        "timeout_s": timeout_s,
    }
    (call_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    process, timed_out, transport_attempts = _run_codex_process(
        command,
        prompt,
        work_dir,
        call_dir,
        response_path,
        timeout_s,
    )

    metadata.update(
        {
            "ended_epoch_s": time.time(),
            "exit_code": process.returncode,
            "timed_out": timed_out,
            "transport_attempts": transport_attempts,
        }
    )
    events: list[dict[str, Any]] = []
    for line in (
        (call_dir / "events.jsonl")
        .read_text(encoding="utf-8", errors="replace")
        .splitlines()
    ):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        events.append(event)
    metadata["thread_ids"] = [
        event.get("thread_id")
        for event in events
        if event.get("type") == "thread.started"
    ]
    metadata["usage"] = [
        event.get("usage") for event in events if event.get("type") == "turn.completed"
    ]
    metadata["item_types"] = [
        event.get("item", {}).get("type")
        for event in events
        if event.get("type") == "item.completed"
    ]
    forbidden_item_types = {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "computer_action",
    }
    metadata["forbidden_item_types"] = sorted(
        {
            item_type
            for item_type in metadata["item_types"]
            if item_type in forbidden_item_types
        }
    )
    (call_dir / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    if (
        timed_out
        or process.returncode != 0
        or not response_path.is_file()
        or metadata["forbidden_item_types"]
    ):
        diagnostic = (
            (call_dir / "stderr.log").read_text(encoding="utf-8", errors="replace")
            + "\n"
            + (call_dir / "events.jsonl").read_text(encoding="utf-8", errors="replace")
        ).lower()
        if any(
            token in diagnostic
            for token in ("usage limit", "rate limit", "quota", "try again at")
        ):
            print(
                "SCENEWEAVER_CODEX_LIMIT "
                + json.dumps(
                    {"call": index, "model": model, "run_dir": str(save_dir)},
                    sort_keys=True,
                ),
                flush=True,
            )
        raise RuntimeError(
            f"Codex bridge call {index} failed exit={process.returncode} "
            f"timeout={timed_out} forbidden_items={metadata['forbidden_item_types']}; "
            f"see {call_dir}"
        )

    try:
        payload = json.loads(response_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"Invalid Codex bridge response in {response_path}: {error}")
    if not isinstance(payload, dict):
        raise RuntimeError(f"Codex bridge response must be an object: {response_path}")
    response = parse_response(
        payload,
        allowed_names,
        message_class,
        function_class,
        tool_call_class,
        f"codex_call_{index:04d}",
    )
    print(
        "SCENEWEAVER_CODEX_TOOL "
        + json.dumps(
            {
                "call": index,
                "model": model,
                "name": payload.get("tool_name"),
                "run_dir": str(save_dir),
            },
            ensure_ascii=False,
            sort_keys=True,
        ),
        flush=True,
    )
    return response

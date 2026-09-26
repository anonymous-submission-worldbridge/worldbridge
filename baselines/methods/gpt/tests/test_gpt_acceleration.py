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
import os
from pathlib import Path

import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
spec = importlib.util.spec_from_file_location(
    "astra_acceleration", (ROOT / "methods/gpt/tools/accelerate_gpt.py")
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value)


@pytest.mark.parametrize(
    "manifest,expected",
    [
        ({}, "generate"),
        ({"generation_success": True}, "build"),
        ({"build_success": True}, "render"),
        ({"render_success": True}, "valid"),
        ({"render_success": False, "failure_class": "quality"}, "quality"),
    ],
)
def test_stage(manifest, expected):
    assert mod.stage(manifest) == expected


@pytest.mark.parametrize(
    "code,expected",
    [
        ("def build_scene(seed):\n    pass", None),
        ("def build_scene(seed):\n    x = 1 broken", "quality"),
    ],
)
def test_adopt_generation_matches_original(tmp_path, monkeypatch, code, expected):
    protocol = tmp_path / "methods/gpt/protocol/generation"
    write(protocol / "gpt6_astra_prompt.txt", "fixed prompt")
    write(
        protocol / "gpt6_astra.json",
        json.dumps({"codex_version": "0.153.4", "reasoning_effort": "high"}),
    )
    monkeypatch.setattr(mod.adapter, "ROOT", tmp_path)
    monkeypatch.setattr(
        mod.adapter.subprocess, "check_output", lambda *a, **k: "codex-cli 0.153.4\n"
    )
    events = [
        {"type": "thread.started", "thread_id": "test"},
        {"type": "turn.completed", "usage": {"output_tokens": 10}},
    ]
    event_text = "\n".join(map(json.dumps, events))

    def fake_process(command, work, stdout, stderr, *a, **k):
        write(stdout, event_text)
        write(stderr, "")
        write(Path(command[command.index("-o") + 1]), json.dumps({"code": code}))
        return 0, False

    monkeypatch.setattr(mod.adapter, "run_process", fake_process)
    original = mod.adapter.generate(
        {"domain": "indoor", "spec_id": "s"}, 0, tmp_path / "data"
    )
    run = tmp_path / "adopted"
    write(run / "logs/generation_01/events.jsonl", event_text)
    write(run / "logs/generation_01/stderr.log", "")
    write(run / "logs/generation_01/response.json", json.dumps({"code": code}))
    attempt = {"index": 1}
    adopted = mod.finish_generation(
        run, {"generation_success": False}, attempt, 0, False
    )
    assert adopted.get("failure_class") == expected
    for key in (
        "generation_success",
        "failure_class",
        "failure_reason",
        "generated_code_sha256",
    ):
        assert adopted.get(key) == original.get(key)
    for key in ("thread_ids", "usage", "tool_events"):
        assert attempt[key] == original["attempts"][0][key]


def test_generation_tool_use_is_quality_not_repaired(tmp_path):
    run = tmp_path / "run"
    write(
        run / "logs/generation_01/events.jsonl",
        json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}),
    )
    write(run / "logs/generation_01/stderr.log", "")
    write(
        run / "logs/generation_01/response.json",
        json.dumps({"code": "def build_scene(seed): pass"}),
    )
    m = mod.finish_generation(run, {}, {"index": 1}, 0, False)
    assert m["failure_class"] == "quality"
    assert not (run / "scene/generated.py").exists()


def test_generation_quota_is_not_quality(tmp_path):
    run = tmp_path / "run"
    write(run / "logs/generation_01/events.jsonl", "")
    write(run / "logs/generation_01/stderr.log", "usage limit reached")
    m = mod.finish_generation(run, {}, {"index": 1}, 1, False)
    assert m["failure_class"] == "access_blocked"


@pytest.mark.parametrize(
    "rc,log,expected",
    [
        (0, "ASTRA_BUILD_COMPLETE", None),
        (11, "generated.py SyntaxError", "quality"),
        (11, "generated.py MemoryError", "infrastructure"),
        (1, "unexpected termination", "infrastructure"),
    ],
)
def test_build_exit_policy(tmp_path, rc, log, expected):
    write(tmp_path / "logs/build_01/stdout.log", log)
    write(tmp_path / "logs/build_01/stderr.log", "")
    m = mod.finish_blender(tmp_path, {}, "build", {"index": 1}, rc, False)
    assert m.get("failure_class") == expected
    assert bool(m.get("build_success")) == (expected is None)


def test_timeout_does_not_accept_completion_marker(tmp_path):
    write(tmp_path / "logs/build_01/stdout.log", "ASTRA_BUILD_COMPLETE")
    write(tmp_path / "logs/build_01/stderr.log", "")
    m = mod.finish_blender(tmp_path, {}, "build", {"index": 1}, 0, True)
    assert m["failure_class"] == "infrastructure"


def test_target_rejects_foreign_model_and_run(tmp_path):
    child = {
        "uid": os.getuid(),
        "pid": 10,
        "pgid": 10,
        "command": [
            "codex",
            "exec",
            "--model",
            "other",
            "--output-schema",
            "x",
            "-C",
            str(tmp_path / "work"),
        ],
    }
    with pytest.raises(RuntimeError, match="Wrong requested model"):
        mod.target(child, {tmp_path})
    child["command"][3] = "gpt-6-astra"
    with pytest.raises(RuntimeError, match="outside"):
        mod.target(child, set())
    assert mod.target(child, {tmp_path}) == (tmp_path, "generate")

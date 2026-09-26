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
import sys
from types import SimpleNamespace
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "astra_supervisor", (ROOT / "methods/gpt/tools/supervise_gpt.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_incomplete_pilot_never_starts_formal(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(
        MODULE,
        "audit",
        lambda *a: {"counts": {"valid": 15, "quality": 1, "building": 4}},
    )
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *a, **k: pytest.fail("No subprocess before pilot completion"),
    )

    def stop(_):
        raise RuntimeError("test pause")

    monkeypatch.setattr(MODULE.time, "sleep", stop)
    with pytest.raises(RuntimeError, match="test pause"):
        MODULE.supervise([0, 1], 4)
    state = json.loads(
        (tmp_path / "results/gpt6_astra/workflow/state.json").read_text()
    )
    assert state["stages"] == []
    assert state["status"] == "paused_error"


def test_infrastructure_failure_blocks_formal(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    monkeypatch.setattr(
        MODULE, "audit", lambda *a: {"counts": {"valid": 19, "infrastructure": 1}}
    )
    monkeypatch.setattr(
        MODULE.subprocess,
        "run",
        lambda *a, **k: pytest.fail("No formal or metric subprocess"),
    )
    with pytest.raises(RuntimeError, match="unresolved infrastructure"):
        MODULE.supervise([0], 1)


def test_five_metrics_complete_does_not_claim_human_completion(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    (tmp_path / "methods/gpt/protocol/generation").mkdir(parents=True)
    (tmp_path / "methods/gpt/protocol/generation/gpt6_astra.lock.json").write_text(
        json.dumps({"files_sha256": {}})
    )
    monkeypatch.setattr(MODULE, "audit", lambda *a: {"counts": {"valid": 200}})
    calls = []
    automatic = [
        "qalign",
        "clipiqa_plus",
        "consistency_3d",
        "appearance_diversity_itt",
        "layout_diversity_itt",
    ]

    def run(command, **kwargs):
        calls.append(command)
        if command[0] == "nvidia-smi":
            assert "--query-gpu=memory.free" in command
            return SimpleNamespace(stdout="22000\n", returncode=0)
        if any(str(c).endswith("aggregate_generation.py") for c in command):
            result = Path(command[command.index("--results-root") + 1])
            result.mkdir(parents=True)
            (result / "table2_full.json").write_text(
                json.dumps(
                    {"metrics": {key: {"status": "complete"} for key in automatic}}
                )
            )
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(MODULE.subprocess, "run", run)
    monkeypatch.setattr(
        MODULE.time,
        "sleep",
        lambda _: pytest.fail("Busy GPU with enough VRAM must not wait"),
    )
    MODULE.supervise([0, 1], 4)
    state = json.loads(
        (tmp_path / "results/gpt6_astra/workflow/state.json").read_text()
    )
    assert state["status"] == "awaiting_ratings_and_table_review"
    assert len(state["stages"]) == 7
    assert "No human or AI proxy ratings invented" in state["note"]


def test_duplicate_supervisor_refused(monkeypatch, tmp_path):
    import fcntl

    monkeypatch.setattr(MODULE, "ROOT", tmp_path)
    output = tmp_path / "results/gpt6_astra/workflow"
    output.mkdir(parents=True)
    with (output / "supervisor.lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(RuntimeError, match="already running"):
            MODULE.supervise([0], 1)

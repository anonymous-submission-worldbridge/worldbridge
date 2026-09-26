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


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADAPTER = load("glm_5_3", "methods/glm/adapter.py")
MATRIX = load("glm_5_3_matrix", "methods/glm/run.py")


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef build_scene(seed): pass",
        'def build_scene(seed): open("/tmp/a", "w")',
        'import bpy\ndef build_scene(seed): bpy.ops.wm.save_as_mainfile(filepath="/tmp/a")',
        'def build_scene(seed): eval("1")',
        "def other(seed): pass",
    ],
)
def test_rejects_out_of_contract_code(source):
    with pytest.raises(ValueError):
        ADAPTER.check_code(source)


def test_accepts_procedural_geometry():
    ADAPTER.check_code(
        "import bpy\nimport random\ndef build_scene(seed):\n"
        "    bpy.ops.mesh.primitive_cube_add(size=1)\n"
    )


def test_parses_opencode_json_events():
    raw = "\n".join(
        [
            json.dumps({"type": "step_start", "sessionID": "ses_test", "part": {}}),
            json.dumps(
                {
                    "type": "text",
                    "sessionID": "ses_test",
                    "part": {
                        "text": json.dumps({"code": "def build_scene(seed): pass"})
                    },
                }
            ),
            json.dumps(
                {
                    "type": "step_finish",
                    "sessionID": "ses_test",
                    "part": {
                        "reason": "stop",
                        "tokens": {"input": 10, "output": 3, "reasoning": 2},
                    },
                }
            ),
        ]
    )
    code, session, usage = ADAPTER.parse_opencode_events(raw)
    assert code.startswith("def build_scene")
    assert session == "ses_test"
    assert usage["reasoning"] == 2


def test_requires_exported_target_model_evidence():
    with pytest.raises(ValueError, match="does not prove"):
        ADAPTER.verify_exported_model(
            {"providerID": "glm-coding-plan", "modelID": "glm-5.3-flash"}
        )
    evidence = ADAPTER.verify_exported_model(
        {
            "messages": [
                {"info": {"providerID": "glm-coding-plan", "modelID": "glm-5.3"}}
            ]
        }
    )
    assert {"providerID": "glm-coding-plan", "modelID": "glm-5.3"} in evidence


def test_secret_only_enters_child_environment(monkeypatch, tmp_path):
    monkeypatch.setenv("UNRELATED", "kept")
    environment = ADAPTER.opencode_environment("secret-value")
    assert environment["GLM53_API_KEY"] == "secret-value"
    assert environment["OPENCODE_CONFIG"].endswith(
        "methods/glm_flash/runtime/glm53_opencode/opencode.json"
    )
    assert environment["OPENCODE_DISABLE_AUTOUPDATE"] == "1"
    assert environment["UNRELATED"] == "kept"


def test_opencode_config_fixes_low_reasoning_and_no_tools():
    config = json.loads(
        ((ROOT / "methods/glm_flash/runtime/glm53_opencode/opencode.json")).read_text()
    )
    model = config["provider"]["glm-coding-plan"]["models"]["glm-5.3"]
    assert model["limit"]["output"] == 65536
    scene = config["agent"]["scene"]
    assert scene["thinking"] == {"type": "enabled"}
    assert scene["reasoningEffort"] == "low"
    assert all(value is False for value in scene["tools"].values())


def test_task_selection_counts():
    assert len(MATRIX.select_tasks("both", True, None, None)) == 20
    assert len(MATRIX.select_tasks("both", False, None, None)) == 200


def test_pipeline_accounts_for_every_task(monkeypatch):
    def fake(spec, seed, root, gpu, phase):
        return {
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "generation_success": True,
            "build_success": phase in {"build", "render"},
            "render_success": phase == "render",
            "failure_class": None,
        }

    monkeypatch.setattr(MATRIX, "task", fake)
    tasks = [({"spec_id": str(index)}, 0) for index in range(8)]
    result = MATRIX.pipeline(tasks, ROOT / "tmp", [0, 1], 2, 3)
    assert len(result) == len(tasks)
    assert all(row["render_success"] for row in result)

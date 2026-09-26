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


ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADAPTER = load("gpt6_astra_medium_test", "methods/gpt/adapter_medium.py")
MATRIX = load("gpt6_astra_medium_matrix_test", "methods/gpt/run_medium_matrix.py")
AUDIT = load("gpt6_astra_medium_audit_test", "methods/gpt/tools/audit_gpt_medium.py")


def test_only_scientific_configuration_change_is_reasoning_effort():
    high = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    medium = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_medium.json")).read_text()
    )
    assert high["model"] == medium["model"] == "gpt-6-astra"
    assert high["reasoning_effort"] == "high"
    assert medium["reasoning_effort"] == "medium"
    for key in (
        "transport",
        "codex_version",
        "generation_timeout_s",
        "build_timeout_s",
        "render_timeout_s",
        "max_retries_infrastructure",
        "retry_quality_failures",
        "build_workers",
        "build_threads",
        "render_threads",
        "min_render_free_mib",
        "pilot_specs_per_domain",
        "pilot_seeds",
        "formal_specs_per_domain",
        "formal_seeds",
        "camera",
        "iqa_batch_size",
        "blender_executable",
        "metrics_python",
    ):
        assert medium[key] == high[key], key


def test_medium_adapter_requests_exact_model_and_effort(monkeypatch, tmp_path):
    monkeypatch.setattr(ADAPTER, "confined", lambda path: Path(path))
    monkeypatch.setattr(
        ADAPTER.subprocess,
        "check_output",
        lambda *args, **kwargs: "codex-cli 0.153.4\n",
    )

    def fake_run(command, work, stdout, stderr, timeout, env=None, stdin=None):
        assert command[command.index("--model") + 1] == "gpt-6-astra"
        assert 'model_reasoning_effort="medium"' in command
        assert "logical_seed" in stdin
        stdout.write_text("")
        stderr.write_text("")
        (stdout.parent / "response.json").write_text(
            json.dumps(
                {
                    "code": "import bpy\ndef build_scene(seed):\n    bpy.ops.mesh.primitive_cube_add(size=1)"
                }
            )
        )
        return 0, False

    monkeypatch.setattr(ADAPTER, "run_process", fake_run)
    spec = {"domain": "indoor", "spec_id": "indoor_test", "extent_m": [6, 5, 3]}
    result = ADAPTER.generate(spec, 2, tmp_path)
    assert result["method"] == "gpt6_astra_medium"
    assert result["reasoning_effort_requested"] == "medium"
    native = json.loads(
        (
            tmp_path
            / "indoor/gpt6_astra_medium/indoor_test/seed_2/input/native_input.json"
        ).read_text()
    )
    assert native["model"] == "gpt-6-astra"
    assert native["reasoning_effort"] == "medium"


def test_medium_pipeline_accounts_for_every_task(monkeypatch):
    calls = []

    def fake(spec, seed, root, gpu, phase):
        calls.append((spec["spec_id"], phase, gpu))
        return {
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "generation_success": True,
            "build_success": phase in {"build", "render"},
            "render_success": phase == "render",
            "failure_class": None,
        }

    monkeypatch.setattr(MATRIX, "task", fake)
    tasks = [({"spec_id": str(index)}, 0) for index in range(12)]
    results = MATRIX.pipeline(tasks, ROOT / "tmp", [0, 2, 3], generators=4, builders=4)
    assert len(results) == 12
    assert {row["spec_id"] for row in results} == {str(index) for index in range(12)}
    assert all(gpu is None for _, phase, gpu in calls if phase in {"generate", "build"})
    assert all(gpu in {0, 2, 3} for _, phase, gpu in calls if phase == "render")


def test_medium_audit_rejects_high_identity(tmp_path, monkeypatch):
    spec_root = tmp_path / "protocol/generation"
    spec_root.mkdir(parents=True)
    for domain in ("indoor", "urban"):
        (spec_root / f"{domain}_specs.jsonl").write_text(
            json.dumps({"domain": domain, "spec_id": f"{domain}_test", "spec_index": 0})
            + "\n"
        )
    monkeypatch.setattr(AUDIT, "ROOT", tmp_path)
    run = tmp_path / "data/indoor/gpt6_astra_medium/indoor_test/seed_0"
    run.mkdir(parents=True)
    (run / "run_manifest.json").write_text(
        json.dumps(
            {
                "method": "gpt6_astra",
                "reasoning_effort_requested": "high",
                "render_success": True,
            }
        )
    )
    (run / "SUCCESS").write_text("x\n")
    report = AUDIT.audit(tmp_path / "data", pilot=True)
    record = next(
        row
        for row in report["records"]
        if row["domain"] == "indoor" and row["seed"] == 0
    )
    assert record["status"] == "identity_mismatch"

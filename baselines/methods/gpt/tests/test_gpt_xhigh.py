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


ADAPTER = load("gpt6_astra_xhigh_test", "methods/gpt/adapter_xhigh.py")
MATRIX = load("gpt6_astra_xhigh_matrix_test", "methods/gpt/run_xhigh_matrix.py")
AUDIT = load("gpt6_astra_xhigh_audit_test", "methods/gpt/tools/audit_gpt_xhigh.py")


def test_only_scientific_configuration_change_is_reasoning_effort():
    high = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    xhigh = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.json")).read_text()
    )
    assert high["model"] == xhigh["model"] == "gpt-6-astra"
    assert high["reasoning_effort"] == "high"
    assert xhigh["reasoning_effort"] == "xhigh"
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
        assert xhigh[key] == high[key], key


def test_operational_amendment_preserves_scientific_inputs():
    config = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_xhigh.json")).read_text()
    )
    amendment = ADAPTER.load_operational_amendment(config)
    unchanged = amendment["unchanged_registered_configuration"]
    assert unchanged["model"] == "gpt-6-astra"
    assert unchanged["reasoning_effort"] == "xhigh"
    assert unchanged["generation_timeout_s_recorded_for_high_parity"] == 900
    assert amendment["operational_changes"]["effective_generation_timeout_s"] == 3600
    assert amendment["operational_changes"]["recommended_generation_concurrency"] == 2


def test_pre_formal_identity_migration_does_not_repeat_response(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    old = {
        "spec_sha256": "same",
        "protocol_sha256": "same",
        "adapter_sha256": "36e44935c2c07a87a74c6aed5bc6dfb646967df9627e20be3d9829f7bbb58b38",
        "operational_amendment_sha256": "0d055e503837d3ab8d00f61fc1bc79caae15092be919455c427cdd00d557d620",
    }
    new = {
        "spec_sha256": "same",
        "protocol_sha256": "same",
        "adapter_sha256": "new",
        "operational_amendment_sha256": "amendment",
    }
    manifest = {"identity": old, "generation_success": True, "attempts": [{"index": 1}]}
    assert ADAPTER.migrate_pre_formal_operational_identity(
        run, manifest, new, {"status": "pilot"}
    )
    written = json.loads((run / "run_manifest.json").read_text())
    assert written["identity"] == new
    assert written["generation_success"] is True
    assert written["attempts"] == [{"index": 1}]
    assert (
        written["pre_formal_identity_migrations"][0]["model_response_repeated"] is False
    )


def test_xhigh_adapter_requests_exact_model_and_effort(monkeypatch, tmp_path):
    monkeypatch.setattr(ADAPTER, "confined", lambda path: Path(path))
    monkeypatch.setattr(
        ADAPTER.subprocess,
        "check_output",
        lambda *args, **kwargs: "codex-cli 0.153.4\n",
    )

    def fake_run(command, work, stdout, stderr, timeout, env=None, stdin=None):
        assert command[command.index("--model") + 1] == "gpt-6-astra"
        assert 'model_reasoning_effort="xhigh"' in command
        assert "logical_seed" in stdin
        assert timeout == 3600
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
    assert result["method"] == "gpt6_astra_xhigh"
    assert result["reasoning_effort_requested"] == "xhigh"
    native = json.loads(
        (
            tmp_path
            / "indoor/gpt6_astra_xhigh/indoor_test/seed_2/input/native_input.json"
        ).read_text()
    )
    assert native["model"] == "gpt-6-astra"
    assert native["reasoning_effort"] == "xhigh"
    manifest = json.loads(
        (
            tmp_path / "indoor/gpt6_astra_xhigh/indoor_test/seed_2/run_manifest.json"
        ).read_text()
    )
    assert manifest["attempts"][0]["timeout_limit_s"] == 3600
    assert manifest["identity"]["operational_amendment_sha256"] == ADAPTER.digest(
        ADAPTER.AMENDMENT
    )


def test_xhigh_pipeline_accounts_for_every_task(monkeypatch):
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


def test_xhigh_audit_rejects_high_identity(tmp_path, monkeypatch):
    spec_root = tmp_path / "protocol/generation"
    spec_root.mkdir(parents=True)
    for domain in ("indoor", "urban"):
        (spec_root / f"{domain}_specs.jsonl").write_text(
            json.dumps({"domain": domain, "spec_id": f"{domain}_test", "spec_index": 0})
            + "\n"
        )
    monkeypatch.setattr(AUDIT, "ROOT", tmp_path)
    run = tmp_path / "data/indoor/gpt6_astra_xhigh/indoor_test/seed_0"
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

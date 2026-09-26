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
from collections import namedtuple
from pathlib import Path
import pytest

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ADAPTER = load("gpt6_astra_low", (ROOT / "methods/gpt/adapter_low.py"))
MATRIX = load("gpt6_astra_low_matrix", (ROOT / "methods/gpt/run_low_matrix.py"))
RATINGS = load(
    "gpt6_astra_low_ratings",
    (ROOT / "methods/gpt/tools/fill_simulated_gpt_low_ratings.py"),
)
RECOVERY = load(
    "gpt6_astra_low_recovery",
    (ROOT / "methods/gpt/tools/resume_gpt_low_gpu_recovery.py"),
)
METRICS = load("gpt6_astra_low_metrics", (ROOT / "methods/gpt/run_low_metrics.py"))


def test_only_reasoning_tier_and_identity_fields_differ_from_high():
    high = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra.json")).read_text()
    )
    low = json.loads(
        ((ROOT / "methods/gpt/protocol/generation/gpt6_astra_low.json")).read_text()
    )
    fields = [
        "model",
        "transport",
        "codex_version",
        "generation_timeout_s",
        "build_timeout_s",
        "build_workers",
        "domains",
        "spec_files",
        "seeds_file",
        "pilot_specs_per_domain",
        "pilot_seeds",
        "formal_specs_per_domain",
        "formal_seeds",
        "api_seed_supported",
        "max_output_tokens",
        "max_retries_infrastructure",
        "min_render_free_mib",
        "retry_quality_failures",
        "generation_weights",
        "formal_data_root",
        "metrics_lock",
        "blender_executable",
        "metrics_python",
        "camera",
        "render_timeout_s",
        "build_threads",
        "render_threads",
        "iqa_batch_size",
    ]
    assert {field: low[field] for field in fields} == {
        field: high[field] for field in fields
    }
    assert high["reasoning_effort"] == "high"
    assert low["reasoning_effort"] == "low"


@pytest.mark.parametrize(
    "source",
    [
        "import os\ndef build_scene(seed): pass",
        'def build_scene(seed): open("/tmp/a", "w")',
        'import bpy\ndef build_scene(seed): bpy.ops.wm.save_as_mainfile(filepath="/tmp/a")',
        "def other(seed): pass",
    ],
)
def test_rejects_out_of_contract_code(source):
    with pytest.raises(ValueError):
        ADAPTER.check_code(source)


def test_pipeline_accounts_for_every_task(monkeypatch):
    def fake(spec, seed, root, gpu, phase):
        return {
            "spec_id": spec["spec_id"],
            "generation_success": True,
            "build_success": phase in {"build", "render"},
            "render_success": phase == "render",
            "failure_class": None,
        }

    monkeypatch.setattr(MATRIX, "task", fake)
    tasks = [({"spec_id": str(index)}, 0) for index in range(12)]
    result = MATRIX.pipeline(tasks, ROOT / "tmp", [0, 1, 2], 4, builders=4)
    assert len(result) == 12
    assert all(row["render_success"] for row in result)


def test_formal_requires_lock(monkeypatch, tmp_path):
    monkeypatch.setattr(MATRIX, "ROOT", tmp_path)
    with pytest.raises(RuntimeError, match="frozen pilot lock"):
        MATRIX.verify_formal_lock()


def test_rating_review_parser_requires_complete_evidence(tmp_path):
    review = tmp_path / "review.txt"
    review.write_text("1|4443|013|2|Visible evidence only.\n2|3333|02|1|Second item.\n")
    rows = RATINGS.parse_review(review)
    assert rows[0]["neutral_layout"] == [4, 4, 4, 3]
    assert rows[1]["borderline_fact_indices"] == [1]


def test_rating_review_parser_rejects_overlap(tmp_path):
    review = tmp_path / "review.txt"
    review.write_text("1|4444|01|12|Overlap.\n")
    with pytest.raises(ValueError, match="overlap"):
        RATINGS.parse_review(review)


def test_gpu_recovery_never_uses_less_than_24_gib(monkeypatch):
    calls = []
    monkeypatch.setattr(
        RECOVERY,
        "_ORIGINAL_WAIT_GPU",
        lambda gpu, threshold: calls.append((gpu, threshold)) or threshold,
    )
    assert RECOVERY.recovery_wait_gpu(2, 8192) == 24576
    assert RECOVERY.recovery_wait_gpu(1, 30000) == 30000
    assert calls == [(2, 24576), (1, 30000)]


def test_disk_recovery_retains_20_gib_hard_stop(monkeypatch):
    usage = namedtuple("usage", "total used free")
    monkeypatch.setattr(
        RECOVERY,
        "_ORIGINAL_DISK_USAGE",
        lambda path: usage(100 * 1024**3, 70 * 1024**3, 30 * 1024**3),
    )
    assert RECOVERY.recovery_disk_usage(ROOT).free == 50 * 1024**3
    monkeypatch.setattr(
        RECOVERY,
        "_ORIGINAL_DISK_USAGE",
        lambda path: usage(100 * 1024**3, 90 * 1024**3, 10 * 1024**3),
    )
    assert RECOVERY.recovery_disk_usage(ROOT).free == 10 * 1024**3


def test_gpu_recovery_normalizes_blender_oom_wording(monkeypatch, tmp_path):
    stdout = tmp_path / "stdout.log"
    stderr = tmp_path / "stderr.log"

    def fake(*args, **kwargs):
        stdout.write_text("Error: System is out of GPU memory\n")
        stderr.write_text("")
        return 11, False

    monkeypatch.setattr(RECOVERY, "_ORIGINAL_RUN_PROCESS", fake)
    assert RECOVERY.recovery_run_process([], tmp_path, stdout, stderr, 10) == (
        11,
        False,
    )
    assert "out of memory" in stderr.read_text()


def test_gpu_recovery_lock_isolation_is_metric_only(monkeypatch, tmp_path):
    files = {
        "evaluation/visual/eval_iqa.py": "shared metric changed elsewhere",
        "tools/renderer.py": "frozen renderer",
    }
    for relative, content in files.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    lock_path = tmp_path / "methods/gpt/protocol/generation/gpt6_astra_low.lock.json"
    lock_path.parent.mkdir(parents=True)
    lock_path.write_text(
        json.dumps(
            {
                "files_sha256": {
                    "evaluation/visual/eval_iqa.py": RECOVERY.MATRIX_IRRELEVANT_LOCK_ENTRIES[
                        "evaluation/visual/eval_iqa.py"
                    ],
                    "tools/renderer.py": RECOVERY.matrix.digest(
                        tmp_path / "tools/renderer.py"
                    ),
                }
            }
        )
    )
    monkeypatch.setattr(RECOVERY.matrix, "ROOT", tmp_path)
    RECOVERY.recovery_verify_formal_lock()

    (tmp_path / "tools/renderer.py").write_text("drifted renderer")
    with pytest.raises(RuntimeError, match="locked file changed"):
        RECOVERY.recovery_verify_formal_lock()


def test_metric_lock_admits_only_exact_audited_evaluator_updates(monkeypatch, tmp_path):
    frozen = {
        relative: hashes["frozen"]
        for relative, hashes in METRICS.EQUIVALENT_SHARED_EVALUATORS.items()
    }
    frozen["tools/renderer.py"] = "renderer-frozen"
    lock = tmp_path / "methods/gpt/protocol/generation/gpt6_astra_low.lock.json"
    lock.parent.mkdir(parents=True)
    lock.write_text(json.dumps({"files_sha256": frozen}))
    actual = {
        relative: hashes["current"]
        for relative, hashes in METRICS.EQUIVALENT_SHARED_EVALUATORS.items()
    }
    actual["tools/renderer.py"] = "renderer-frozen"
    monkeypatch.setattr(
        METRICS, "digest", lambda path: actual[str(path.relative_to(tmp_path))]
    )
    assert METRICS.verify_evaluation_lock(tmp_path) == {
        relative: hashes["current"]
        for relative, hashes in METRICS.EQUIVALENT_SHARED_EVALUATORS.items()
    }

    actual["tools/renderer.py"] = "renderer-drift"
    with pytest.raises(RuntimeError, match="Frozen evaluation source changed"):
        METRICS.verify_evaluation_lock(tmp_path)

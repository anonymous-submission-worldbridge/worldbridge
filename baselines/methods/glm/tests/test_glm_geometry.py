"""Identity, reuse, ITT, and shared-stack guards for GLM-5.3 Low Table 3."""

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


import json
from pathlib import Path
import sys
import tempfile


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES))
import baselines.methods.glm.geometry.run_glm_geometry as runner  # noqa: E402


def test_protocol_is_glm_low_reuse_only() -> None:
    protocol = json.loads(runner.PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["method"] == "glm_5_3"
    assert protocol["model_id"] == "glm-5.3"
    assert protocol["provider_model"] == "glm-coding-plan/glm-5.3"
    assert protocol["requested_thinking"] == {"type": "enabled"}
    assert protocol["requested_reasoning_effort"] == "low"
    assert protocol["reuse"]["regenerate"] is False
    assert protocol["reuse"]["model_requests_in_table3"] == 0
    assert protocol["downloads_required"] is False
    assert protocol["output_root"].startswith("baselines/data/table3_glm_5_3/")


def test_shared_geometry_stack_is_frozen_high_stack() -> None:
    lock = json.loads(
        (BASELINES / "results/gpt6_astra/table3/metrics.lock.json").read_text(
            encoding="utf-8"
        )
    )
    for relative in (
        "methods/gpt/protocol/geometry/gpt6_astra_geometry_nav_rules.json",
        "protocol/geometry/agent.yaml",
        "methods/gpt/tools/gpt_geometry_surface_rules.py",
        "methods/gpt/tools/export_gpt_geometry.py",
        "methods/gpt/tools/evaluate_gpt_geometry_nav.py",
        "tools/recast_py311/recast.cpython-311-x86_64-linux-gnu.so",
    ):
        assert runner.sha256(BASELINES / relative) == lock["files"][relative]


def test_source_status_accepts_only_frozen_glm_success() -> None:
    good = BASELINES / "data/table2/indoor/glm_5_3/indoor_bedroom_00/seed_0"
    reusable, reason, manifest = runner.source_status(good)
    assert reusable and reason == "reusable"
    assert manifest["model_requested"] == "glm-5.3"
    assert manifest["model_returned"] == "glm-5.3"
    source_lock = json.loads(runner.SOURCE_LOCK.read_text(encoding="utf-8"))[
        "files_sha256"
    ]
    assert (
        manifest["identity"]["protocol_sha256"]
        == source_lock["methods/glm/protocol/generation/glm_5_3.json"]
    )
    assert (
        manifest["identity"]["adapter_sha256"] == source_lock["methods/glm/adapter.py"]
    )

    failed = BASELINES / "data/table2/indoor/glm_5_3/indoor_bedroom_00/seed_1"
    reusable, reason, _ = runner.source_status(failed)
    assert not reusable
    assert reason in {
        "table2_identity_mismatch",
        "table2_generation_failed",
        "table2_build_failed",
        "table2_blend_missing",
        "table2_success_marker_missing",
    }


def test_source_coverage_matches_preregistered_counts() -> None:
    protocol = json.loads(runner.PROTOCOL.read_text(encoding="utf-8"))
    for domain in ("indoor", "urban"):
        observed = {"reusable": 0, "unavailable": 0}
        for spec in runner.read_specs(domain):
            for seed in range(4):
                reusable, _, _ = runner.source_status(
                    runner.source_path(domain, spec["spec_id"], seed)
                )
                observed["reusable" if reusable else "unavailable"] += 1
        assert observed == protocol["reuse"]["source_eligible_coverage"][domain]


def test_itt_contract_is_exact_worst_case() -> None:
    spec = {"domain": "indoor", "spec_id": "fixture"}
    metric = runner.itt_metric(spec, 2, "fixture_failure")
    assert metric["method"] == "glm_5_3"
    assert metric["navigable_area_ratio"] == 0.0
    assert metric["connected_area_ratio"] == 0.0
    assert metric["navmesh_success"] is False
    assert metric["failure_policy"] == "itt_worst_case"
    structural = runner.structural_na(spec, 2)
    assert structural["reason_code"] == "N/A-I"
    assert all(
        structural[name] is None
        for name in (
            "collision_rate",
            "floating_rate",
            "oob_rate",
            "support_validity",
            "valid_scene_rate",
        )
    )


def test_deterministic_no_walkable_failure_is_recognized() -> None:
    markers = (
        "Frozen semantic walkable selection produced no upward triangles",
        "No indoor floor node matched the frozen walkable-surface rule",
    )
    for marker in markers:
        with tempfile.TemporaryDirectory(dir=BASELINES / "tmp") as temporary:
            root = Path(temporary)
            for attempt in (1, 2):
                path = root / f"logs/export_{attempt:02d}/stderr.log"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(f"RuntimeError: {marker}\n", encoding="utf-8")
            assert (
                runner.deterministic_canonical_failure(root)
                == "canonical_no_walkable_surface"
            )
            (root / "logs/export_02/stderr.log").write_text(
                "another failure\n", encoding="utf-8"
            )
            assert runner.deterministic_canonical_failure(root) is None


def test_relabel_does_not_modify_geometry_metadata() -> None:
    with tempfile.TemporaryDirectory(dir=BASELINES / "tmp") as temporary:
        root = Path(temporary)
        payloads = {
            "scene/canonical/instances.json": {"method": "foreign", "instances": []},
            "scene/canonical/geometry_manifest.json": {
                "method": "foreign",
                "empty_reference_ply": {"sha256": "x"},
            },
            "metrics/structural.json": {"method": "foreign", "reason_code": "N/A-I"},
        }
        for relative, payload in payloads.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        runner.relabel_export_artifacts(root)
        for relative, original in payloads.items():
            updated = json.loads((root / relative).read_text(encoding="utf-8"))
            assert updated["method"] == "glm_5_3"
            assert {
                key: value for key, value in updated.items() if key != "method"
            } == {key: value for key, value in original.items() if key != "method"}


def test_table3_files_have_no_auth_or_remote_generation_path() -> None:
    combined = runner.PROTOCOL.read_text(encoding="utf-8") + Path(
        runner.__file__
    ).read_text(encoding="utf-8")
    assert "GLM53_API_KEY" not in combined
    assert "opencode run" not in combined
    assert "api_key" not in combined.lower()
    assert 'model_requests_in_table3": 0' in combined


def main() -> None:
    tests = [
        test_protocol_is_glm_low_reuse_only,
        test_shared_geometry_stack_is_frozen_high_stack,
        test_source_status_accepts_only_frozen_glm_success,
        test_source_coverage_matches_preregistered_counts,
        test_itt_contract_is_exact_worst_case,
        test_deterministic_no_walkable_failure_is_recognized,
        test_relabel_does_not_modify_geometry_metadata,
        test_table3_files_have_no_auth_or_remote_generation_path,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"GLM-5.3 Low Table-3 regression tests: {len(tests)} passed")


if __name__ == "__main__":
    main()

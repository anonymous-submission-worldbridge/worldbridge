"""Identity, subscription provenance, reuse, and ITT guards for Gemini Table 3."""

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
import baselines.methods.gemini.geometry.run_gemini_geometry as runner  # noqa: E402


def test_protocol_is_reuse_only() -> None:
    protocol = json.loads(runner.PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["method"] == "gemini_3_1_pro"
    assert protocol["model_id"] == "gemini-3.1-pro-high"
    assert protocol["reuse"]["regenerate"] is False
    assert protocol["reuse"]["model_requests_in_table3"] == 0
    assert protocol["downloads_required"] is False
    assert protocol["output_root"].startswith("baselines/data/table3_gemini_3_1_pro/")


def test_shared_geometry_stack_matches_frozen_stack() -> None:
    lock = json.loads(
        (BASELINES / "results/gpt6_astra/table3/metrics.lock.json").read_text()
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


def test_source_coverage_and_subscription_identity() -> None:
    protocol = json.loads(runner.PROTOCOL.read_text())
    for domain in ("indoor", "urban"):
        observed = {"reusable": 0, "unavailable": 0}
        for spec in runner.read_specs(domain):
            for seed in range(4):
                source = runner.source_path(domain, spec["spec_id"], seed)
                manifest = json.loads((source / "run_manifest.json").read_text())
                assert runner.source_identity_valid(manifest)
                reusable, _, _ = runner.source_status(source)
                observed["reusable" if reusable else "unavailable"] += 1
        assert observed == protocol["reuse"]["source_eligible_coverage"][domain]


def test_itt_contract_is_exact_worst_case() -> None:
    spec = {"domain": "indoor", "spec_id": "fixture"}
    metric = runner.itt_metric(spec, 2, "fixture_failure")
    assert metric["method"] == "gemini_3_1_pro"
    assert metric["navigable_area_ratio"] == 0.0
    assert metric["connected_area_ratio"] == 0.0
    assert metric["navmesh_success"] is False
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
    with tempfile.TemporaryDirectory(dir=BASELINES / "tmp") as temporary:
        root = Path(temporary)
        marker = "Frozen semantic walkable selection produced no upward triangles"
        for attempt in (1, 2):
            path = root / f"logs/export_{attempt:02d}/stderr.log"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(f"RuntimeError: {marker}\n")
        assert (
            runner.deterministic_canonical_failure(root)
            == "canonical_no_walkable_surface"
        )
    assert runner.is_deterministic_navigation_failure(
        RuntimeError("Reference NavMesh has no connected component")
    )
    assert not runner.is_deterministic_navigation_failure(RuntimeError("unrelated"))


def test_table3_runner_has_no_remote_model_transport() -> None:
    text = Path(runner.__file__).read_text(encoding="utf-8")
    assert "subprocess" not in text
    assert "client_environment" not in text
    assert "generate(" not in text
    assert 'model_requests_in_table3": 0' in runner.PROTOCOL.read_text(encoding="utf-8")


def main() -> None:
    tests = [
        test_protocol_is_reuse_only,
        test_shared_geometry_stack_matches_frozen_stack,
        test_source_coverage_and_subscription_identity,
        test_itt_contract_is_exact_worst_case,
        test_deterministic_no_walkable_failure_is_recognized,
        test_table3_runner_has_no_remote_model_transport,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"Gemini 3.1 Pro Table-3 regression tests: {len(tests)} passed")


if __name__ == "__main__":
    main()

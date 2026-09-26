#!/usr/bin/env python3
"""Identity and reuse guards for GPT-6 Astra Medium Table 3."""

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
import baselines.methods.gpt.geometry.run_gpt_medium_geometry as runner  # noqa: E402


def test_protocol_is_medium_and_reuse_only() -> None:
    protocol = json.loads(runner.PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["method"] == "gpt6_astra_medium"
    assert protocol["model_id"] == "gpt-6-astra"
    assert protocol["reasoning_effort"] == "medium"
    assert protocol["reuse"]["regenerate"] is False
    assert protocol["downloads_required"] is False
    assert protocol["output_root"].startswith(
        "baselines/data/table3_gpt6_astra_medium/"
    )


def test_shared_geometry_stack_is_the_frozen_high_stack() -> None:
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


def test_source_status_accepts_only_medium_success() -> None:
    good = BASELINES / "data/table2/indoor/gpt6_astra_medium/indoor_bedroom_00/seed_0"
    reusable, reason, manifest = runner.source_status(good)
    assert reusable and reason == "reusable"
    assert manifest["reasoning_effort_requested"] == "medium"
    failed = BASELINES / "data/table2/indoor/gpt6_astra_medium/indoor_bedroom_02/seed_2"
    reusable, reason, _ = runner.source_status(failed)
    assert not reusable
    assert reason in {
        "table2_generation_failed",
        "table2_build_failed",
        "table2_success_marker_missing",
    }


def test_itt_contract_is_exact_worst_case() -> None:
    spec = {"domain": "indoor", "spec_id": "fixture"}
    metric = runner.itt_metric(spec, 2, "fixture_failure")
    assert metric["method"] == "gpt6_astra_medium"
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


def test_relabel_does_not_modify_geometry() -> None:
    with tempfile.TemporaryDirectory(dir=BASELINES / "tmp") as temporary:
        tmp_path = Path(temporary)
        payloads = {
            "scene/canonical/instances.json": {"method": "gpt6_astra", "instances": []},
            "scene/canonical/geometry_manifest.json": {
                "method": "gpt6_astra",
                "empty_reference_ply": {"sha256": "x"},
            },
            "metrics/structural.json": {"method": "gpt6_astra", "reason_code": "N/A-I"},
        }
        for relative, payload in payloads.items():
            path = tmp_path / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        runner.relabel_export_artifacts(tmp_path)
        for relative, original in payloads.items():
            updated = json.loads((tmp_path / relative).read_text(encoding="utf-8"))
            assert updated["method"] == "gpt6_astra_medium"
            assert {
                key: value for key, value in updated.items() if key != "method"
            } == {key: value for key, value in original.items() if key != "method"}


def main() -> None:
    test_protocol_is_medium_and_reuse_only()
    test_shared_geometry_stack_is_the_frozen_high_stack()
    test_source_status_accepts_only_medium_success()
    test_itt_contract_is_exact_worst_case()
    test_relabel_does_not_modify_geometry()
    print("GPT-6 Astra Medium Table-3 identity/reuse fixtures: PASS")


if __name__ == "__main__":
    main()

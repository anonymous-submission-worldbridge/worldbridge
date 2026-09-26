#!/usr/bin/env python3
"""Identity, recovery, and reuse guards for GPT-6 Astra Extra High Table 3."""

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
import baselines.methods.gpt.geometry.run_gpt_xhigh_geometry as runner  # noqa: E402

sys.path.insert(0, str(BASELINES / "tools"))
import baselines.methods.gpt.tools.aggregate_gpt_xhigh_geometry as aggregate  # noqa: E402


def test_protocol_is_xhigh_and_discloses_recovery() -> None:
    protocol = json.loads(runner.PROTOCOL.read_text(encoding="utf-8"))
    assert protocol["method"] == "gpt6_astra_xhigh"
    assert protocol["model_id"] == "gpt-6-astra"
    assert protocol["reasoning_effort"] == "xhigh"
    assert protocol["source_recovery"]["regenerate"] is True
    assert protocol["source_recovery"]["exact_byte_recovery"] is False
    assert protocol["downloads_required"] is False
    assert protocol["output_root"].startswith(
        "/data2/outputs/worldbridge_table3_gpt6_astra_xhigh/"
    )


def test_original_audit_freezes_183_recoverable_and_17_itt() -> None:
    records = runner.original_records().values()
    assert sum(row.get("scene_built") is True for row in records) == 183
    assert sum(row.get("scene_built") is not True for row in records) == 17


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


def test_source_status_requires_original_built_and_recovery_identity() -> None:
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        source = Path(temporary)
        assert runner.source_status(source, {"scene_built": False})[:2] == (
            False,
            "original_table2_unbuilt",
        )
        manifest = {
            "method": "gpt6_astra_xhigh",
            "reasoning_effort_requested": "xhigh",
            "generation_success": True,
            "build_success": True,
        }
        (source / "scene").mkdir()
        (source / "scene/scene.blend").write_bytes(b"fixture")
        (source / "run_manifest.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        (source / "table3_source_recovery.json").write_text("{}", encoding="utf-8")
        reusable, reason, _ = runner.source_status(source, {"scene_built": True})
        assert reusable and reason == "recovery_geometry_available"


def test_itt_contract_is_exact_worst_case() -> None:
    spec = {"domain": "indoor", "spec_id": "fixture"}
    metric = runner.itt_metric(spec, 2, "fixture_failure")
    assert metric["method"] == "gpt6_astra_xhigh"
    assert metric["navigable_area_ratio"] == metric["connected_area_ratio"] == 0.0
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
    with tempfile.TemporaryDirectory(dir="/tmp") as temporary:
        root = Path(temporary)
        payloads = {
            "scene/canonical/instances.json": {"method": "gpt6_astra", "instances": []},
            "scene/canonical/geometry_manifest.json": {
                "method": "gpt6_astra",
                "empty_reference_ply": {"sha256": "x"},
            },
            "metrics/structural.json": {"method": "gpt6_astra", "reason_code": "N/A-I"},
        }
        for relative, payload in payloads.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload), encoding="utf-8")
        runner.relabel_export_artifacts(root, Path("/data2/source_fixture"))
        for relative, original in payloads.items():
            updated = json.loads((root / relative).read_text(encoding="utf-8"))
            assert updated["method"] == "gpt6_astra_xhigh"
            assert {
                key: value for key, value in updated.items() if key != "method"
            } == {
                key: value for key, value in original.items() if key != "method"
            } or relative == "scene/canonical/geometry_manifest.json"


def test_export_command_maps_only_the_selected_data2_pair() -> None:
    run = runner.OUTPUT_ROOT / "indoor/spec/seed_0"
    source = runner.SOURCE_ROOT / "indoor/gpt6_astra_xhigh/spec/seed_0"
    command = runner.export_command(run, source)
    assert command[:4] == ["bwrap", "--die-with-parent", "--unshare-net", "--ro-bind"]
    assert ["--bind", str(run), str(runner.EXPORT_MOUNT / "seed_0")] == command[
        command.index("--bind") : command.index("--bind") + 3
    ]
    source_index = command.index("--ro-bind", command.index("--ro-bind") + 1)
    assert command[source_index : source_index + 3] == [
        "--ro-bind",
        str(source),
        str(runner.SOURCE_MOUNT / "seed_0"),
    ]
    assert str(run) not in command[command.index(str(runner.BLENDER)) :]
    assert str(source) not in command[command.index(str(runner.BLENDER)) :]


def test_aggregate_is_spec_clustered_and_keeps_itt_zero() -> None:
    records = []
    for spec_index in range(25):
        for seed in range(4):
            success = not (spec_index == 0 and seed == 0)
            records.append(
                {
                    "spec_id": f"spec_{spec_index:02d}",
                    "success": success,
                    "failure_policy": None if success else "itt_worst_case",
                    "navigable_area_ratio": 100.0 if success else 0.0,
                    "connected_area_ratio": 50.0 if success else 0.0,
                    "navmesh_success_rate": 100.0 if success else 0.0,
                }
            )
    protocol = {"navigation": {"bootstrap_seed": 20260909, "bootstrap_repeats": 100}}
    summary = aggregate.summarize("indoor", records, protocol)
    assert summary["evaluated_geometry_runs"] == 99
    assert summary["itt_failure_runs"] == 1
    assert summary["metrics"]["navigable_area_ratio"]["mean"] == 99.0
    assert summary["metrics"]["connected_area_ratio"]["mean"] == 49.5
    assert summary["exact_table2_byte_reuse"] is False


def main() -> None:
    test_protocol_is_xhigh_and_discloses_recovery()
    test_original_audit_freezes_183_recoverable_and_17_itt()
    test_shared_geometry_stack_is_the_frozen_high_stack()
    test_source_status_requires_original_built_and_recovery_identity()
    test_itt_contract_is_exact_worst_case()
    test_relabel_does_not_modify_geometry()
    test_export_command_maps_only_the_selected_data2_pair()
    test_aggregate_is_spec_clustered_and_keeps_itt_zero()
    print("GPT-6 Astra Extra High Table-3 identity/recovery fixtures: PASS")


if __name__ == "__main__":
    main()

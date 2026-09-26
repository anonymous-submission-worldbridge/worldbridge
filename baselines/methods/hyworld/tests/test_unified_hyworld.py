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


import importlib.util
import json
from pathlib import Path

from PIL import Image
import pytest


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def load(name: str, relative: str):
    path = BASELINES_ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hy = load("test_table4_hy", "methods/hyworld/unified/native/adapters/hyworld.py")
aqs = load("test_table4_aqs", "evaluation/unified/aqs.py")
cli = load("test_table4_cli", "methods/hyworld/unified/native/run.py")
formal_shards = load(
    "test_table4_formal_shards",
    "methods/hyworld/unified/native/run_hyworld_formal_shards.py",
)


def test_pair_specs_are_balanced_and_frozen() -> None:
    rows = hy.load_pair_specs()
    assert len(rows) == 25
    assert [row["spec_index"] for row in rows] == list(range(25))
    assert {row["function"] for row in rows} == {
        "residence",
        "food_service",
        "retail",
        "office",
        "civic_community",
    }
    assert {row["visual_theme"] for row in rows} == {
        "contemporary",
        "brick_industrial",
        "timber_traditional",
        "tropical",
        "futuristic_stylized",
    }
    assert len({(row["function"], row["visual_theme"]) for row in rows}) == 25


def test_formal_shards_cover_each_spec_once() -> None:
    ids = formal_shards.spec_ids()
    shards = [ids[index * 5 : (index + 1) * 5] for index in range(5)]
    assert [item for shard in shards for item in shard] == ids
    assert all(len(shard) == 5 for shard in shards)
    assert len(set(item for shard in shards for item in shard)) == 25


def test_vlm_shard_command_reuses_external_service() -> None:
    command = formal_shards.runner_command(
        "python", "trajectory_planning", ["spec-a"], [3], 9000, 120.0, 18080
    )
    assert command[command.index("--gpus") + 1] == "3"
    assert command[command.index("--spec-ids") + 1] == "spec-a"
    assert command[-3:] == ["--external-llm", "--llm-port", "18080"]


def test_independent_native_inputs_are_deterministic_and_disjoint() -> None:
    pair = hy.load_pair_specs()[12]
    exterior = hy._side_spec(pair, "urban")
    interior = hy._side_spec(pair, "indoor")
    ext_native = hy.compile_native_input(exterior, 3)
    int_native = hy.compile_native_input(interior, 3)
    assert ext_native == hy.compile_native_input(exterior, 3)
    assert ext_native["pair_id"] == int_native["pair_id"]
    assert ext_native["method_seed"] + 1 == int_native["method_seed"]
    assert ext_native["scene_type"] == "outdoor"
    assert int_native["scene_type"] == "indoor"
    assert ext_native["track"] == int_native["track"] == "matched_text_independent"
    assert ext_native["adapter_policy"]["independent_generation"] is True
    assert int_native["pipeline"]["gs_training"]["max_steps"] == 50


def test_prepare_is_idempotent_and_keeps_pilot_separate(tmp_path: Path) -> None:
    formal = BASELINES_ROOT / "tmp/table4_hyworld2_test/formal"
    pair = hy.load_pair_specs()[0]
    spec = hy._side_spec(pair, "urban")
    first = hy.prepare_run(spec, 0, formal)
    second = hy.prepare_run(spec, 0, formal)
    assert first == second
    assert first.name == "exterior"
    pair_spec = json.loads((first.parent / "input/pair_spec.json").read_text())
    assert pair_spec["native_shared_world_frame"] is False
    side_manifest = json.loads((first / "run_manifest.json").read_text())
    assert side_manifest["method_seed"] == 0
    pilot_runs = hy.select_runs("urban", "pilot", formal, logical_seeds=[0])
    assert all(str(run).startswith(str(hy.PILOT_DATA_ROOT)) for run in pilot_runs)
    assert not any(str(run).startswith(str(formal)) for run in pilot_runs)


def test_capability_audit_assigns_na_u() -> None:
    report = cli.capability_audit()
    assert report["assigned_track"] == "matched_text_independent"
    assert report["not_applicable_code"] == "N/A-U"
    assert report["evaluable_metrics"] == ["functional_aqs", "visual_aqs"]
    assert all(
        not hits
        for hits in report["required_unified_identity_field_occurrences"].values()
    )


def _make_anchors(root: Path, color: tuple[int, int, int]) -> None:
    anchor_root = root / "renders/anchors"
    anchor_root.mkdir(parents=True)
    for index in range(8):
        Image.new(
            "RGB", (1280, 720), tuple(min(255, value + index) for value in color)
        ).save(anchor_root / f"rgb_{index:03d}.png")


def test_pair_evidence_has_four_views_per_side(tmp_path: Path) -> None:
    pair_root = tmp_path / "pair"
    _make_anchors(pair_root / "exterior", (20, 30, 40))
    _make_anchors(pair_root / "interior", (120, 130, 140))
    output = tmp_path / "evidence.jpg"
    digest = aqs.make_pair_montage(pair_root, output, "P-TEST")
    assert digest == aqs.sha256_file(output)
    with Image.open(output) as image:
        assert image.size == (1920, 656)
        # Exterior and interior rows remain visibly distinct after JPEG encoding.
        assert image.getpixel((240, 200))[0] < image.getpixel((240, 520))[0]


@pytest.mark.parametrize(
    "payload",
    [
        {
            "functional_aqs": 0,
            "visual_aqs": 5,
            "functional_evidence": "x",
            "visual_evidence": "y",
        },
        {
            "functional_aqs": 5.0,
            "visual_aqs": 5,
            "functional_evidence": "x",
            "visual_evidence": "y",
        },
        {
            "functional_aqs": 5,
            "visual_aqs": 5,
            "functional_evidence": "",
            "visual_evidence": "y",
        },
    ],
)
def test_aqs_schema_rejects_invalid_responses(payload: dict) -> None:
    with pytest.raises(ValueError):
        aqs.validate_score(payload)


def test_aggregate_applies_itt_and_na_u(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    result_root = tmp_path / "results"
    annotation_root = tmp_path / "annotations"
    first_root = BASELINES_ROOT / "tmp/table4_aggregate_fixture/first"
    second_root = BASELINES_ROOT / "tmp/table4_aggregate_fixture/second"
    for root in (first_root, second_root):
        for side in ("exterior", "interior"):
            (root / side).mkdir(parents=True, exist_ok=True)
    for side in ("exterior", "interior"):
        (first_root / side / "SUCCESS").write_text("ok\n")
    (second_root / "exterior/SUCCESS").write_text("ok\n")
    (second_root / "interior/RENDER_QUALITY_FAILURE").write_text("bad\n")
    specs = [
        {
            "spec_id": "first",
            "spec_index": 0,
            "function": "residence",
            "visual_theme": "contemporary",
        },
        {
            "spec_id": "second",
            "spec_index": 1,
            "function": "retail",
            "visual_theme": "tropical",
        },
    ]
    pairs = [(specs[0], 0, first_root), (specs[1], 0, second_root)]
    monkeypatch.setattr(aqs, "RESULT_ROOT", result_root)
    monkeypatch.setattr(aqs, "ANNOTATION_ROOT", annotation_root)
    monkeypatch.setattr(aqs, "expected_pairs", lambda phase: pairs)
    package = annotation_root / "formal"
    aqs.atomic_json(
        package / "AQS_PROVENANCE.json",
        {"rating_source": aqs.RATING_SOURCE, "human_raters": 0},
    )
    item_id = aqs.blind_id("first", 0, "formal")
    for index, (functional, visual) in enumerate(((7, 5), (8, 6), (9, 7)), 1):
        aqs.atomic_json(
            package / "raw" / item_id / f"pass_{index:02d}.json",
            {
                "parsed": {
                    "functional_aqs": functional,
                    "visual_aqs": visual,
                    "functional_evidence": "visible evidence",
                    "visual_evidence": "visible evidence",
                }
            },
        )
    summary = aqs.aggregate("formal")
    assert summary["planned_pairs"] == 2
    assert summary["successful_pairs"] == 1
    assert summary["metrics"]["functional_aqs"]["mean"] == pytest.approx(4.5)
    assert summary["metrics"]["visual_aqs"]["mean"] == pytest.approx(3.5)
    assert set(summary["not_applicable"].values()) == {"N/A-U"}
    failed = json.loads((second_root / "metrics/per_run.json").read_text())
    assert failed["functional_aqs"] == failed["visual_aqs"] == 1.0
    assert failed["shape_iou"] is None

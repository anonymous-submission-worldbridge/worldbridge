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

import pytest

from baselines.methods.worldgen.unified.native.worldgen_unified import NATIVE_NA_METRICS
from baselines.methods.worldgen.unified.native.worldgen_unified import cluster_bootstrap
from baselines.methods.worldgen.unified.native.worldgen_unified import (
    compiled_native_input,
)
from baselines.methods.worldgen.unified.native.worldgen_unified import load_protocol
from baselines.methods.worldgen.unified.native.worldgen_unified import load_specs
from baselines.methods.worldgen.unified.native.worldgen_unified import macro_average
from baselines.methods.worldgen.unified.native.worldgen_unified import parse_aqs
from baselines.methods.worldgen.unified.native.worldgen_unified import (
    trial_specs_and_seeds,
)
from baselines.methods.worldgen.unified.native.worldgen_unified import validate_specs
from baselines.methods.worldgen.unified.native.worldgen_unified import (
    worker_environment,
)


def test_specs_are_complete_five_by_five_cross_product():
    result = validate_specs()
    assert result["passed"], result["errors"]
    specs = load_specs()
    protocol = load_protocol()
    assert {(row["function"], row["visual_theme"]) for row in specs} == {
        (function, theme)
        for function in protocol["functions"]
        for theme in protocol["visual_themes"]
    }


def test_pilot_and_formal_matrices_are_frozen_sizes():
    pilot_specs, pilot_seeds = trial_specs_and_seeds("pilot")
    formal_specs, formal_seeds = trial_specs_and_seeds("formal")
    assert len(pilot_specs) * len(pilot_seeds) == 10
    assert {row["function"] for row in pilot_specs} == set(load_protocol()["functions"])
    assert len(formal_specs) * len(formal_seeds) == 100


def test_native_inputs_are_independent_and_export_official_mesh():
    spec = load_specs()[0]
    exterior = compiled_native_input(spec, 2, "exterior")
    interior = compiled_native_input(spec, 2, "interior")
    assert exterior["method_seed"] == interior["method_seed"] == 2
    assert exterior["prompt"] != interior["prompt"]
    assert exterior["native_shared_world_frame"] is False
    assert interior["native_shared_world_frame"] is False
    assert exterior["return_mesh"] is True
    assert exterior["return_type"] == "gaussian_splat+official_triangle_mesh"
    indices = load_protocol()["render"]["aqs_anchor_indices_per_side"]
    assert indices["exterior"] == [4, 5, 6, 7]
    assert indices["interior"] == [0, 2, 5, 7]


def test_capability_contract_marks_exactly_seven_metrics_na_u():
    capability = load_protocol()["capability"]
    assert len(NATIVE_NA_METRICS) == 7
    assert all(capability[metric] == "N/A-U" for metric in NATIVE_NA_METRICS)
    assert capability["functional_aqs"] == "numeric"
    assert capability["visual_aqs"] == "numeric"


def test_l40s_renderer_reuses_frozen_table2_extension_cache():
    protocol = load_protocol()
    environment = worker_environment(0)
    assert protocol["resources"]["cuda_arch_list"] == "8.9"
    assert environment["TORCH_CUDA_ARCH_LIST"] == "8.9"
    assert environment["TORCH_EXTENSIONS_DIR"].endswith(
        "cache/worldgen/torch_extensions"
    )


def test_macro_average_weights_specs_equally_not_rows():
    rows = [
        {"spec_id": "a", "score": 2.0},
        {"spec_id": "a", "score": 4.0},
        {"spec_id": "b", "score": 9.0},
    ]
    assert macro_average(rows, "score") == 6.0


def test_cluster_bootstrap_is_deterministic():
    rows = [
        {"spec_id": f"s{spec}", "score": float(spec + seed)}
        for spec in range(5)
        for seed in range(4)
    ]
    assert cluster_bootstrap(rows, "score", 200, 123) == cluster_bootstrap(
        rows, "score", 200, 123
    )


def test_aqs_parser_requires_complete_integer_scores():
    good = {
        "choices": [
            {
                "message": {
                    "content": json.dumps(
                        {
                            "functional_aqs": 7,
                            "visual_aqs": 6,
                            "functional_evidence": "Visible restaurant tables and service counter.",
                            "visual_evidence": "Brick and dark metal recur across both rows.",
                        }
                    )
                }
            }
        ]
    }
    assert parse_aqs(good)["functional_aqs"] == 7
    bad = json.loads(json.dumps(good))
    bad["choices"][0]["message"]["content"] = bad["choices"][0]["message"][
        "content"
    ].replace('"visual_aqs": 6', '"visual_aqs": 11')
    with pytest.raises(ValueError):
        parse_aqs(bad)

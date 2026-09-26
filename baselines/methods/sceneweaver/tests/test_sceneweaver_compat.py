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
import ast
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np


ROOT = _BASELINE_PROJECT_ROOT / "baselines"
MODULE_PATH = ROOT / "methods/sceneweaver/runtime/sceneweaver_pipeline/main.py"
EXECUTOR_COMPAT_PATH = (
    ROOT / "methods/sceneweaver/runtime/sceneweaver_executor/generate_indoors_compat.py"
)
MATRIX_COMPAT_PATH = ROOT / "methods/sceneweaver/run_matrix_compat.py"
AGENT_PATH = ROOT / "vendor/SceneWeaver/Pipeline/app/agent/scenedesigner.py"
PLANES_PATH = (
    ROOT
    / "vendor/SceneWeaver/infinigen/core/constraints/example_solver/geometry/planes.py"
)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "sceneweaver_compat_runtime", MODULE_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_matrix_compat():
    spec = importlib.util.spec_from_file_location(
        "sceneweaver_matrix_compat", MATRIX_COMPAT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_executor_pure_function(name):
    tree = ast.parse(EXECUTOR_COMPAT_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {}
    exec(
        compile(
            ast.Module(body=[function], type_ignores=[]),
            str(EXECUTOR_COMPAT_PATH),
            "exec",
        ),
        namespace,
    )
    return namespace[name]


def load_agent_pure_function(name):
    tree = ast.parse(AGENT_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {"Path": Path, "json": json}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(AGENT_PATH), "exec"),
        namespace,
    )
    return namespace[name]


def load_planes_pure_function(name):
    tree = ast.parse(PLANES_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == name
    )
    namespace = {"np": np}
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(PLANES_PATH), "exec"),
        namespace,
    )
    return namespace[name]


class FakeMessage:
    def __init__(self, role, content="", tool_calls=None, name=None, tool_call_id=None):
        self.role = role
        self.content = content
        self.tool_calls = tool_calls
        self.name = name
        self.tool_call_id = tool_call_id

    @classmethod
    def assistant_message(cls, content):
        return cls("assistant", content)

    @classmethod
    def user_message(cls, content):
        return cls("user", content)


def test_openrouter_history_removes_provider_specific_tool_ids():
    module = load_module()
    call = SimpleNamespace(
        id="call_old",
        function=SimpleNamespace(name="init_gpt", arguments='{"roomtype":"bedroom"}'),
    )
    messages = [
        FakeMessage("user", "make a room"),
        FakeMessage("assistant", "planning", [call]),
        FakeMessage("tool", "done", name="init_gpt", tool_call_id="call_old"),
    ]

    flattened = module.flatten_openrouter_tool_history(messages, FakeMessage)

    assert [message.role for message in flattened] == ["user", "assistant", "user"]
    assert all(not message.tool_calls for message in flattened)
    assert "init_gpt" in flattened[1].content
    assert "done" in flattened[2].content
    assert "call_old" in flattened[1].content
    assert "not a new call" in flattened[1].content


def test_recovers_exact_trailing_openrouter_text_tool_call():
    module = load_module()
    tools = [
        {
            "type": "function",
            "function": {"name": "add_gpt", "parameters": {"type": "object"}},
        }
    ]
    content = (
        "The scene needs a window.\n"
        'Completed tool request: [{"arguments":{"ideas":"add window"},'
        '"id":"call_new","name":"add_gpt"}]'
    )

    cleaned, recovered = module.recover_openrouter_text_tool_calls(content, tools)

    assert cleaned == "The scene needs a window."
    assert recovered == [
        {
            "id": "call_new",
            "name": "add_gpt",
            "arguments": '{"ideas":"add window"}',
        }
    ]


def test_does_not_recover_undeclared_or_malformed_text_calls():
    module = load_module()
    tools = [{"type": "function", "function": {"name": "add_gpt"}}]
    undeclared = (
        'Completed tool request: [{"arguments":{},"id":"x","name":"delete_all"}]'
    )
    malformed = 'Completed tool request: [{"arguments":"{","id":"x","name":"add_gpt"}]'

    assert module.recover_openrouter_text_tool_calls(undeclared, tools) == (
        undeclared,
        [],
    )
    assert module.recover_openrouter_text_tool_calls(malformed, tools) == (
        malformed,
        [],
    )


def test_drops_only_arguments_not_declared_by_current_tool_schema():
    module = load_module()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "init_gpt",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "roomtype": {"type": "string"},
                        "ideas": {"type": "string"},
                    },
                },
            },
        }
    ]
    raw = '{"ideas":"warm room","roomtype":"bedroom","/invoke":"</tool_call>"}'

    cleaned, removed = module.sanitize_declared_tool_arguments("init_gpt", raw, tools)

    assert cleaned == '{"ideas":"warm room","roomtype":"bedroom"}'
    assert removed == ["/invoke"]
    assert module.sanitize_declared_tool_arguments("unknown", raw, tools) == (
        raw,
        [],
    )
    assert module.sanitize_declared_tool_arguments("init_gpt", "{", tools) == (
        "{",
        [],
    )


def test_detects_only_explicit_length_finish_reason():
    module = load_module()
    assert module.response_was_length_truncated(
        SimpleNamespace(choices=[SimpleNamespace(finish_reason="length")])
    )
    assert not module.response_was_length_truncated(
        SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop")])
    )


def test_required_architectural_factory_aliases_are_frozen():
    module = load_module()
    assert module.FACTORY_COMPATIBILITY["window"] == "windows.WindowFactory"
    assert module.FACTORY_COMPATIBILITY["door"] == "elements.PanelDoorFactory"
    assert module.FACTORY_COMPATIBILITY["dooropening"] == ("elements.PanelDoorFactory")
    assert module.FACTORY_COMPATIBILITY["windowopening"] == "windows.WindowFactory"
    assert module.FACTORY_COMPATIBILITY["refrigerator"] == (
        "appliances.BeverageFridgeFactory"
    )
    assert module.FACTORY_COMPATIBILITY["rugfactory"] == "elements.RugFactory"


def test_tool_json_normalizes_snake_case_schema_keys():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"room_size":[3.5,4.5],'
        '"category_list_of_big_object":{"Sink":"1"},'
        '"object_against_the_wall":["Sink"],'
        '"relation_between_big_objects":[]}'
    )

    assert parsed == {
        "Room size": [3.5, 4.5],
        "Category list of big object": {"Sink": "1"},
        "Object against the wall": ["Sink"],
        "Relation between big objects": [],
    }


def test_tool_json_uses_maximum_numeric_component_as_overall_size_axis():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"Placement_big":{"officechair":{"1":{"size":'
        '[0.6,0.6,[0.45,0.95]]}}},"unrelated":[1,[2,3],4]}'
    )

    assert parsed["Placement_big"]["officechair"]["1"]["size"] == [
        0.6,
        0.6,
        0.95,
    ]
    assert parsed["unrelated"] == [1, [2, 3], 4]


def test_size_component_repair_leaves_ambiguous_values_unchanged():
    module = load_module()
    payload = {"size": [1.0, ["low", "high"], [float("nan"), 2.0]]}

    repaired, records = module.normalize_nested_size_components(payload)

    assert repaired["size"][1] == ["low", "high"]
    assert repaired["size"][2][1] == 2.0
    assert records == []


def test_tool_json_keeps_first_valid_relation_from_overfull_parent():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"Placement":{"cabinet":{"1":{"parent":'
        '["1630547_BedFactory","side_by_side","newroom_0-0",'
        '"on_floor","against_wall"]}},"book":{"1":{"parent":'
        '["Shelf","2","ontop","extra"]}}}}'
    )

    assert parsed["Placement"]["cabinet"]["1"]["parent"] == [
        "1630547_BedFactory",
        "side_by_side",
    ]
    assert parsed["Placement"]["book"]["1"]["parent"] == [
        "Shelf",
        "2",
        "ontop",
    ]


def test_overfull_parent_repair_leaves_unknown_prefix_unchanged():
    module = load_module()
    payload = {"parent": ["object", "mystery", "relation", "extra"]}

    repaired, records = module.normalize_overfull_parents(payload)

    assert repaired == payload
    assert records == []


def test_executor_filters_only_positive_anyrelation_placeholders():
    without_any = load_executor_pure_function("without_unconstrained_relations")

    class AnyRelation:
        pass

    class ExplicitRelation:
        pass

    explicit = (ExplicitRelation(), "explicit-domain")
    negative_any = (object(), "negative-any-domain")
    relations = [(AnyRelation(), "any-domain"), explicit, negative_any]

    assert without_any(relations, AnyRelation) == [explicit, negative_any]


def test_planner_attempt_budget_recovers_largest_durable_evidence(tmp_path):
    load_attempts = load_agent_pure_function("load_persistent_planner_attempts")
    save_dir = tmp_path / "run/sceneweaver"
    (save_dir / "pipeline").mkdir(parents=True)
    (save_dir / "pipeline/planner_attempts.json").write_text(
        json.dumps({"attempts_used": 6})
    )
    for index in range(8):
        call = save_dir / f"codex_bridge/calls/call_{index:04d}"
        call.mkdir(parents=True)
        (call / "response.json").write_text("{}")
    (save_dir.parent / "logs").mkdir()
    (save_dir.parent / "logs/generate_attempt_01.log").write_text(
        "SceneDesigner selected 1 tools to use\n" * 7
    )

    used, path, evidence = load_attempts(str(save_dir), current_step=5)

    assert used == 8
    assert path == save_dir / "pipeline/planner_attempts.json"
    assert evidence == {
        "checkpoint_steps": 5,
        "codex_tool_calls": 8,
        "historical_log_calls": 7,
        "persisted": 6,
        "persisted_uncommitted_ignored": 0,
    }


def test_planner_attempt_budget_ignores_uncommitted_prewritten_attempts(tmp_path):
    load_attempts = load_agent_pure_function("load_persistent_planner_attempts")
    save_dir = tmp_path / "run/sceneweaver"
    (save_dir / "pipeline").mkdir(parents=True)
    (save_dir / "pipeline/planner_attempts.json").write_text(
        json.dumps({"attempts_used": 12})
    )

    used, _, evidence = load_attempts(str(save_dir), current_step=3)

    assert used == 3
    assert evidence["persisted_uncommitted_ignored"] == 9


def test_rejected_edit_prompt_prevents_blind_repeat():
    prompt_builder = load_agent_pure_function("rejected_edit_prompt")
    prompt_builder.__globals__["NEXT_STEP_PROMPT"] = "NEXT"

    prompt = prompt_builder("update_layout", 2)

    assert "update_layout" in prompt
    assert "iteration 2" in prompt
    assert "Do not repeat" in prompt
    assert "terminate" in prompt
    assert prompt.endswith("NEXT")


def test_polygon_mask_maps_to_current_loop_triangles():
    mapper = load_planes_pure_function("triangle_indices_from_polygon_mask")

    selected = mapper([False, True, False], [0, 1, 1, 2, 99])

    assert selected.tolist() == [1, 2]
    assert selected.dtype == np.int64


def test_short_free_space_path_is_a_terminal_render_contract_failure():
    source = ast.parse(((ROOT / "methods/sceneweaver/adapter_compat.py")).read_text())
    main = next(
        node
        for node in source.body
        if isinstance(node, ast.FunctionDef) and node.name == "main"
    )
    helper = next(
        node
        for node in main.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "render_contract_error_terminal"
    )
    namespace = {}
    exec(
        compile(
            ast.Module(body=[helper], type_ignores=[]), "sceneweaver_compat.py", "exec"
        ),
        namespace,
    )

    assert namespace["render_contract_error_terminal"](
        "RuntimeError: SceneWeaver free-space path is too short: 0.721 m"
    )
    assert not namespace["render_contract_error_terminal"](
        "RuntimeError: No CUDA/OPTIX Cycles device is available"
    )


def test_tool_json_accepts_python_style_nested_lists():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        "prose before {'Mirror': {'location': [3.0, 1.65, 0.5], "
        "'parent': [['wardrobe', 'against']]}} prose after"
    )

    assert parsed["Mirror"]["parent"] == [["wardrobe", "against"]]


def test_tool_json_merges_list_of_unique_singleton_objects():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '[{"table":{"location":[1,2,0]}},{"chair":{"location":[2,2,0]}}]'
    )

    assert set(parsed) == {"table", "chair"}


def test_tool_json_skips_coordinate_arrays_in_prose_before_layout():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        "Move it to [2.0, 1.8, 0.1]. Final layout: "
        '{"bed":{"location":[2.0,1.8,0.1]}}'
    )

    assert parsed == {"bed": {"location": [2.0, 1.8, 0.1]}}


def test_tool_json_normalizes_only_exact_relation_enum_spellings():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"Placement":{"sink":{"1":{"parent":["cabinet","1","on_top"]}}},'
        '"note":"put decor on top of the counter"}'
    )

    assert parsed["Placement"]["sink"]["1"]["parent"][-1] == "ontop"
    assert parsed["note"] == "put decor on top of the counter"


def test_tool_json_collapses_only_all_null_parent_triplets():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"Placement_big":{"Cabinet":{"1":{"parent":[null,null,null]},'
        '"2":{"parent":["Wall","1","against_wall"]}}}}'
    )

    instances = parsed["Placement_big"]["Cabinet"]
    assert instances["1"]["parent"] == []
    assert instances["2"]["parent"] == ["Wall", "1", "against_wall"]


def test_tool_json_maps_clear_relation_synonyms_and_drops_unknown_parent():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"Placement_big":{"CoffeeTable":{"1":{"parent":'
        '["Sofa","1","in_front_of"]}},"Chair":{"1":{"parent":'
        '["CoffeeTable","1","facing"]}},"Rug":{"1":{"parent":'
        '["CoffeeTable","1","under"]}}}}'
    )

    assert parsed["Placement_big"]["CoffeeTable"]["1"]["parent"][-1] == (
        "front_to_front"
    )
    assert parsed["Placement_big"]["Chair"]["1"]["parent"][-1] == ("front_against")
    assert parsed["Placement_big"]["Rug"]["1"]["parent"] == []


def test_tool_json_recovers_mapping_when_unused_sibling_list_is_unquoted():
    module = load_module()
    parsed = module.extract_sceneweaver_json(
        '{"List of given category names":[Sofa, Window],'
        '"Mapping results":{"Sofa":null,"Window":null}}'
    )

    assert parsed == {"Mapping results": {"Sofa": None, "Window": None}}


def test_exact_factory_repair_fixes_only_known_native_categories():
    module = load_module()
    repaired = module.repair_exact_factory_mapping(
        ["Cup", "wardrobe", "Window"],
        {
            "Cup": "tableware.CumpFactory",
            "wardrobe": None,
            "Window": None,
        },
        {
            "cup": "tableware.CupFactory",
            "window": "windows.WindowFactory",
        },
    )

    assert repaired == {
        "Cup": "tableware.CupFactory",
        "wardrobe": None,
        "Window": "windows.WindowFactory",
    }


def test_exact_factory_repair_rejects_valid_but_wrong_native_factory():
    module = load_module()
    repaired = module.repair_exact_factory_mapping(
        ["TV"],
        {"TV": "shelves.TVStandFactory"},
        {
            "tv": "appliances.TVFactory",
            "tvstand": "shelves.TVStandFactory",
        },
    )

    assert repaired == {"TV": "appliances.TVFactory"}


def test_exact_factory_repair_accepts_standard_factory_suffix():
    module = load_module()
    repaired = module.repair_exact_factory_mapping(
        ["WindowFactory", "ChairFactory"],
        {"WindowFactory": None, "ChairFactory": None},
        {
            "window": "windows.WindowFactory",
            "chair": "seating.ChairFactory",
        },
    )

    assert repaired == {
        "WindowFactory": "windows.WindowFactory",
        "ChairFactory": "seating.ChairFactory",
    }


def test_rotation_update_carries_forward_only_missing_sizes():
    module = load_module()
    repaired, names = module.repair_rotation_update_sizes(
        {
            "chair": {"location": [1, 2, 0], "rotation": [0, 0, 1.57]},
            "table": {
                "location": [2, 2, 0],
                "rotation": [0, 0, 0],
                "size": [2, 1, 0.8],
            },
        },
        {
            "chair": {"size": [0.5, 0.5, 0.9]},
            "table": {"size": [1.5, 0.8, 0.75]},
        },
    )

    assert repaired["chair"]["size"] == [0.5, 0.5, 0.9]
    assert repaired["table"]["size"] == [2, 1, 0.8]
    assert names == ["chair"]


def test_addition_filter_keeps_native_and_available_fallback_categories():
    module = load_module()
    payload = {
        "Number of new furniture": {
            "RangeHood": "1",
            "CuttingBoard": "1",
            "Wardrobe": "1",
        },
        "name_mapping": {
            "RangeHood": "wall_decorations.RangeHoodFactory",
            "CuttingBoard": None,
            "Wardrobe": None,
        },
        "category_against_wall": ["RangeHood", "CuttingBoard", "Wardrobe"],
        "category_on_the_floor": ["Wardrobe"],
        "Relation": [
            ["RangeHood", "oven", "ontop"],
            ["CuttingBoard", "counter", "ontop"],
            ["Wardrobe", "room", "onfloor"],
        ],
        "Placement": {
            "RangeHood": {"1": {}},
            "CuttingBoard": {"1": {}},
            "Wardrobe": {"1": {}},
        },
    }

    repaired, unavailable = module.filter_unavailable_additions(
        payload, lambda category: category == "Wardrobe"
    )

    assert unavailable == ["CuttingBoard"]
    assert set(repaired["Number of new furniture"]) == {"RangeHood", "Wardrobe"}
    assert set(repaired["Placement"]) == {"RangeHood", "Wardrobe"}
    assert [relation[0] for relation in repaired["Relation"]] == [
        "RangeHood",
        "Wardrobe",
    ]


def test_initial_filter_removes_only_unsupported_category_and_dangling_parent():
    module = load_module()
    payload = {
        "big_category_dict": {"Sofa": "1", "Painting": "1", "Wardrobe": "1"},
        "name_mapping": {
            "Sofa": "seating.SofaFactory",
            "Painting": None,
            "Wardrobe": None,
        },
        "category_against_wall": ["Sofa", "Painting", "Wardrobe", "Window"],
        "relation_big_object": [
            ["Painting", "Sofa", "side_by_side"],
            ["Wardrobe", "Sofa", "side_by_side"],
        ],
        "Placement_big": {
            "Sofa": {"1": {"position": [1, 1]}},
            "Painting": {"1": {"position": [2, 2]}},
            "Wardrobe": {
                "1": {
                    "position": [3, 3],
                    "parent": ["Painting", "1", "side_by_side"],
                }
            },
        },
    }

    repaired, unavailable, parents = module.filter_unavailable_initial_objects(
        payload, lambda category: category == "Wardrobe"
    )

    assert unavailable == ["Painting"]
    assert set(repaired["big_category_dict"]) == {"Sofa", "Wardrobe"}
    assert set(repaired["Placement_big"]) == {"Sofa", "Wardrobe"}
    assert repaired["Placement_big"]["Wardrobe"]["1"]["parent"] == []
    assert repaired["category_against_wall"] == ["Sofa", "Wardrobe"]
    assert repaired["relation_big_object"] == [["Wardrobe", "Sofa", "side_by_side"]]
    assert parents[0]["reason"] == "missing_parent_category"


def test_late_loaded_tool_references_are_rebound(monkeypatch):
    module = load_module()
    original_extract = object()
    original_mapping = object()
    compatible_extract = object()
    compatible_mapping = object()
    late_tool = SimpleNamespace(
        extract_json=original_extract,
        complete_factory_mapping=original_mapping,
    )
    unrelated = SimpleNamespace(extract_json=original_extract)
    monkeypatch.setitem(sys.modules, "app.tool.late_loaded", late_tool)
    monkeypatch.setitem(sys.modules, "unrelated.late_loaded", unrelated)

    module.patch_loaded_tool_references(compatible_extract, compatible_mapping)

    assert late_tool.extract_json is compatible_extract
    assert late_tool.complete_factory_mapping is compatible_mapping
    assert unrelated.extract_json is original_extract


def test_child_depth_contract_orders_dependents_before_supporters():
    # The runtime patch performs this ordering against each generated layout;
    # keep a small fixture documenting the expected child-first contract.
    layout = {
        "desk": {"parent": [["room", "onfloor"]]},
        "chair": {"parent": [["desk", "front_against"]]},
        "lamp": {"parent": [["desk", "on"]]},
    }
    selected = ["desk", "chair", "lamp"]
    selected_set = set(selected)

    def depth(name, visiting=None):
        visiting = set() if visiting is None else set(visiting)
        if name in visiting:
            return 0
        visiting.add(name)
        parents = [rel[0] for rel in layout[name]["parent"]]
        return 1 + max(
            (depth(parent, visiting) for parent in parents if parent in selected_set),
            default=-1,
        )

    ordered = sorted(selected, key=lambda name: (-depth(name), selected.index(name)))
    assert ordered == ["chair", "lamp", "desk"]


def test_extracts_daily_and_minute_rate_limit_reset_timestamps():
    module = load_matrix_compat()
    daily = (
        "openai.RateLimitError: Daily limit reached; "
        "'X-RateLimit-Reset': '1788739200000'"
    )
    minute = "RateLimitError: High demand; " "'X-RateLimit-Reset': '1788680160'"

    assert module.rate_limit_reset_epoch_ms(daily) == 1788739200000
    assert module.rate_limit_reset_epoch_ms(minute) == 1788680160000
    assert (
        module.rate_limit_reset_epoch_ms(
            "LLM_TRANSIENT_RETRY error_type=RateLimitError"
        )
        is None
    )


def test_latest_generation_log_requires_terminal_failed_attempt(tmp_path):
    module = load_matrix_compat()
    run_dir = tmp_path / "seed_0"
    (run_dir / "logs").mkdir(parents=True)
    (run_dir / "logs/generate_attempt_01.log").write_text("old transient")
    manifest = {
        "attempts": [
            {
                "phase": "generate",
                "success": True,
                "traceback_in_logs": False,
                "log": "logs/generate_attempt_01.log",
            }
        ]
    }
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest))
    assert module.latest_generation_log(run_dir) is None

    manifest["attempts"][0].update(success=False, traceback_in_logs=True)
    (run_dir / "run_manifest.json").write_text(json.dumps(manifest))
    assert module.latest_generation_log(run_dir) == (
        run_dir / "logs/generate_attempt_01.log"
    )

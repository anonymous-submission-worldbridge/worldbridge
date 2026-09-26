#!/usr/bin/env python3
"""Compatibility entry point for the frozen SceneWeaver Table-2 adapter.

The shared vendored checkout is read-only on some experiment hosts.  Keep the
small, auditable compatibility layer below ``baselines`` and patch the Python
objects in memory before constructing SceneWeaver's agent.
"""

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


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()


import argparse
import ast
import importlib.util
import json
import math
import os
import random
import re
import sys
from pathlib import Path
from typing import Any


def _find_baselines_root() -> Path:
    # The local compatibility layer lives at baselines/methods/sceneweaver/runtime/sceneweaver_pipeline.
    # Upstream dependencies are checked when the pipeline is executed.
    return _BASELINE_PROJECT_ROOT / "baselines"


BASELINES_ROOT = _find_baselines_root()
SCENEWEAVER_ROOT = BASELINES_ROOT / "vendor/SceneWeaver"
ORIGINAL_PIPELINE = SCENEWEAVER_ROOT / "Pipeline"


def _tool_call_summary(call: Any) -> dict[str, Any]:
    function = getattr(call, "function", None)
    return {
        "id": getattr(call, "id", None),
        "name": getattr(function, "name", None),
        "arguments": getattr(function, "arguments", None),
    }


def flatten_openrouter_tool_history(
    messages: list[Any], message_class: Any
) -> list[Any]:
    """Turn completed tool exchanges into ordinary conversational history.

    The sole provider behind the frozen free MiniMax endpoint rejects valid
    multi-turn histories intermittently with ``tool id not found``.  The tool
    name, arguments, assistant reasoning, and result remain in the context;
    only provider-specific call IDs are removed.  New calls still use the
    normal OpenAI tool schema.
    """

    flattened: list[Any] = []
    for message in messages:
        role = getattr(message, "role", None)
        if role == "assistant" and getattr(message, "tool_calls", None):
            content = getattr(message, "content", None) or ""
            calls = [_tool_call_summary(call) for call in message.tool_calls]
            suffix = (
                "Historical completed action (context only, not a new call): "
                + json.dumps(calls, ensure_ascii=False, sort_keys=True)
            )
            flattened.append(
                message_class.assistant_message((content + "\n\n" + suffix).strip())
            )
        elif role == "tool":
            name = getattr(message, "name", None) or "unknown"
            content = getattr(message, "content", None) or ""
            flattened.append(
                message_class.user_message(f"Result from tool {name}:\n{content}")
            )
        else:
            flattened.append(message)
    return flattened


def recover_openrouter_text_tool_calls(
    content: str | None, tools: list[dict[str, Any]] | None
) -> tuple[str, list[dict[str, str]]]:
    """Recover an otherwise-valid tool call serialized into message content.

    Some OpenRouter providers occasionally emit their tool-call rendering in
    text while leaving ``message.tool_calls`` empty.  Recovery is intentionally
    narrow: the rendering must be the final block, name a currently declared
    tool, contain an object-valued JSON arguments field, and provide an id.
    Ambiguous prose is left untouched for SceneWeaver's normal repair loop.
    """

    text = content or ""
    allowed = {
        tool.get("function", {}).get("name")
        for tool in (tools or [])
        if isinstance(tool, dict) and tool.get("type") == "function"
    }
    match = re.search(
        r"(?:^|\n)Completed tool request:\s*(\[.*\])\s*$", text, re.DOTALL
    )
    if not match:
        return text, []
    try:
        serialized = json.loads(match.group(1))
    except json.JSONDecodeError:
        return text, []
    if not isinstance(serialized, list) or len(serialized) != 1:
        return text, []

    call = serialized[0]
    if not isinstance(call, dict):
        return text, []
    name = call.get("name")
    call_id = call.get("id")
    raw_arguments = call.get("arguments")
    if name not in allowed or not isinstance(call_id, str) or not call_id:
        return text, []
    if isinstance(raw_arguments, dict):
        arguments = json.dumps(raw_arguments, ensure_ascii=False, separators=(",", ":"))
    elif isinstance(raw_arguments, str):
        arguments = raw_arguments
    else:
        return text, []
    try:
        parsed_arguments = json.loads(arguments)
    except json.JSONDecodeError:
        return text, []
    if not isinstance(parsed_arguments, dict):
        return text, []

    recovered = {"id": call_id, "name": name, "arguments": arguments}
    return text[: match.start()].rstrip(), [recovered]


def sanitize_declared_tool_arguments(
    name: str | None,
    arguments: str | None,
    tools: list[dict[str, Any]] | None,
) -> tuple[str | None, list[str]]:
    """Remove provider rendering markers that are not tool-schema properties.

    A MiniMax/OpenRouter response can append XML-ish rendering fields such as
    ``"/invoke": "</tool_call>"`` to an otherwise valid JSON argument object.
    Only a call whose current declared schema is known is touched; malformed
    arguments and schemas without explicit object properties remain unchanged
    for SceneWeaver's normal validation/repair path.
    """

    properties: dict[str, Any] | None = None
    for tool in tools or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        function = tool.get("function")
        if not isinstance(function, dict) or function.get("name") != name:
            continue
        parameters = function.get("parameters")
        if isinstance(parameters, dict) and isinstance(
            parameters.get("properties"), dict
        ):
            properties = parameters["properties"]
        break

    if properties is None or not isinstance(arguments, str):
        return arguments, []
    try:
        parsed = json.loads(arguments)
    except json.JSONDecodeError:
        return arguments, []
    if not isinstance(parsed, dict):
        return arguments, []

    removed = sorted(key for key in parsed if key not in properties)
    if not removed:
        return arguments, []
    cleaned = {key: value for key, value in parsed.items() if key in properties}
    return json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")), removed


def response_was_length_truncated(response: Any) -> bool:
    choices = getattr(response, "choices", None) or []
    return bool(choices and getattr(choices[0], "finish_reason", None) == "length")


FACTORY_COMPATIBILITY = {
    # Architectural elements that 3D-FUTURE intentionally does not contain.
    "window": "windows.WindowFactory",
    "windows": "windows.WindowFactory",
    "windowopening": "windows.WindowFactory",
    "door": "elements.PanelDoorFactory",
    "dooropening": "elements.PanelDoorFactory",
    "doorway": "elements.PanelDoorFactory",
    # Common prompt synonyms for factories already shipped by SceneWeaver.
    "refrigerator": "appliances.BeverageFridgeFactory",
    "fridge": "appliances.BeverageFridgeFactory",
    "stove": "appliances.OvenFactory",
    "cooktop": "appliances.OvenFactory",
    "counter": "shelves.CountertopFactory",
    "countertop": "shelves.CountertopFactory",
    "kitchenisland": "shelves.KitchenIslandFactory",
    # The official tool card spells this ``elements.RugFactory``.  Providers
    # commonly preserve the class name while dropping the module prefix.
    "rugfactory": "elements.RugFactory",
    "cabinet": "shelves.SingleCabinetFactory",
    "bookshelf": "shelves.SimpleBookcaseFactory",
    "bookcase": "shelves.SimpleBookcaseFactory",
    "diningchair": "seating.ChairFactory",
    "diningtable": "tables.TableDiningFactory",
    "ceilinglight": "lamp.CeilingLightFactory",
    "ceilinglamp": "lamp.CeilingLightFactory",
    "pendantlamp": "lamp.CeilingLightFactory",
    "television": "appliances.TVFactory",
    "plant": "tableware.PlantContainerFactory",
    "indoorplant": "tableware.PlantContainerFactory",
    "towel": "clothes.TowelFactory",
    "painting": "wall_decorations.WallArtFactory",
}


SCHEMA_KEY_COMPATIBILITY = {
    "roomsize": "Room size",
    "categorylistofbigobject": "Category list of big object",
    "objectagainstthewall": "Object against the wall",
    "relationbetweenbigobjects": "Relation between big objects",
    "numberofnewfurniture": "Number of new furniture",
    "categoryagainstwall": "category_against_wall",
    "categoryonthefloor": "category_on_the_floor",
    "mappingresults": "Mapping results",
    "placement": "Placement",
}


RELATION_COMPATIBILITY = {
    "againstwall": "against_wall",
    "sideagainstwall": "side_against_wall",
    "onfloor": "on_floor",
    "ontop": "ontop",
    "frontagainst": "front_against",
    "sidebyside": "side_by_side",
    "fronttofront": "front_to_front",
    "leftrightleftright": "leftright_leftright",
    "backtoback": "back_to_back",
    # Common natural-language spellings emitted despite the prompt's fixed
    # relation vocabulary.  These preserve the stated facing/support intent.
    "infrontof": "front_to_front",
    "facing": "front_against",
    "ontopof": "ontop",
    "above": "ontop",
}

VALID_PARENT_RELATIONS = set(RELATION_COMPATIBILITY.values()) | {
    "against_wall",
    "on_floor",
    "onfloor",
    "on",
}


def _compact_key(value: Any) -> str:
    return "".join(character for character in str(value).lower() if character.isalnum())


def _balanced_container(text: str, start: int) -> str | None:
    """Return one bracket-balanced container while respecting quoted strings."""

    if start < 0 or start >= len(text) or text[start] not in "{[":
        return None
    stack: list[str] = []
    quote: str | None = None
    escaped = False
    for index in range(start, len(text)):
        character = text[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            continue
        if character in {"'", '"'}:
            quote = character
        elif character in "{[":
            stack.append(character)
        elif character in "}]":
            expected = "{" if character == "}" else "["
            if not stack or stack[-1] != expected:
                return None
            stack.pop()
            if not stack:
                return text[start : index + 1]
    return None


def _parse_container_literal(serialized: str) -> Any:
    try:
        return json.loads(serialized)
    except json.JSONDecodeError:
        return ast.literal_eval(serialized)


def _coerce_tool_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        if (
            not isinstance(value, list)
            or not value
            or not all(isinstance(item, dict) and len(item) == 1 for item in value)
        ):
            raise ValueError("SceneWeaver tool response did not contain an object")
        merged: dict[str, Any] = {}
        for item in value:
            key, item_value = next(iter(item.items()))
            if key in merged:
                raise ValueError(f"Duplicate key in SceneWeaver object list: {key!r}")
            merged[key] = item_value
        value = merged
    return value


def _normalize_schema_keys(payload: dict[str, Any]) -> dict[str, Any]:
    """Normalize only the top-level keys prescribed by SceneWeaver prompts."""

    normalized: dict[str, Any] = {}
    for key, value in payload.items():
        canonical = SCHEMA_KEY_COMPATIBILITY.get(_compact_key(key), key)
        if canonical not in normalized or key == canonical:
            normalized[canonical] = value
    return normalized


def _normalize_relation_values(value: Any) -> Any:
    """Normalize exact relation-enum spellings without changing other text."""

    if isinstance(value, dict):
        return {key: _normalize_relation_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize_relation_values(item) for item in value]
    if isinstance(value, str):
        return RELATION_COMPATIBILITY.get(_compact_key(value), value)
    return value


def _normalize_absent_parents(value: Any) -> Any:
    """Canonicalize the provider's null-filled spelling of no dependency.

    SceneWeaver accepts either ``null`` or an empty list for an object without
    a parent.  Some providers instead emit ``[null, null, null]`` following the
    three-field parent schema.  The frozen solver treats any non-empty list as
    a dependency and then crashes while reading its first element, so collapse
    only this unambiguous all-null representation.
    """

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if (
                key == "parent"
                and isinstance(item, list)
                and item
                and all(element is None for element in item)
            ):
                normalized[key] = []
            else:
                normalized[key] = _normalize_absent_parents(item)
        return normalized
    if isinstance(value, list):
        return [_normalize_absent_parents(item) for item in value]
    return value


def normalize_nested_size_components(
    value: Any, path: tuple[str, ...] = ()
) -> tuple[Any, list[dict[str, Any]]]:
    """Convert numeric sub-dimensions into the required overall dimension.

    Providers occasionally describe an object's height as component heights,
    for example ``[seat_height, total_height]`` inside the third axis of the
    three-axis ``size`` field.  SceneWeaver's executor accepts only scalar
    extents.  A non-empty, finite, non-negative numeric sub-list is
    unambiguous here: its maximum is the object's overall extent.  All other
    shapes are retained for the upstream validation path.
    """

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        repairs: list[dict[str, Any]] = []
        for key, item in value.items():
            current_path = path + (str(key),)
            if key == "size" and isinstance(item, list) and len(item) == 3:
                dimensions = list(item)
                for axis, dimension in enumerate(dimensions):
                    if not isinstance(dimension, list) or not dimension:
                        continue
                    if not all(
                        isinstance(component, (int, float))
                        and not isinstance(component, bool)
                        and math.isfinite(float(component))
                        and float(component) >= 0
                        for component in dimension
                    ):
                        continue
                    overall = max(float(component) for component in dimension)
                    if overall <= 0:
                        continue
                    dimensions[axis] = overall
                    repairs.append(
                        {
                            "path": ".".join(current_path + (str(axis),)),
                            "before": dimension,
                            "after": overall,
                        }
                    )
                normalized[key] = dimensions
                continue
            normalized_item, item_repairs = normalize_nested_size_components(
                item, current_path
            )
            normalized[key] = normalized_item
            repairs.extend(item_repairs)
        return normalized, repairs
    if isinstance(value, list):
        normalized_items = []
        repairs = []
        for index, item in enumerate(value):
            normalized_item, item_repairs = normalize_nested_size_components(
                item, path + (str(index),)
            )
            normalized_items.append(normalized_item)
            repairs.extend(item_repairs)
        return normalized_items, repairs
    return value, []


def normalize_overfull_parents(
    value: Any, path: tuple[str, ...] = ()
) -> tuple[Any, list[dict[str, Any]]]:
    """Keep the first complete relation from a concatenated parent field.

    The frozen tool prompt permits exactly ``[old_object, relation]`` or
    ``[new_category, index, relation]`` and explicitly disallows multiple
    relations for one object.  Some providers concatenate a second relation
    onto that valid prefix.  Only overfull lists with a recognizable valid
    prefix are shortened; all ambiguous lists remain unchanged.
    """

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        repairs: list[dict[str, Any]] = []
        for key, item in value.items():
            current_path = path + (str(key),)
            if key == "parent" and isinstance(item, list) and len(item) > 3:
                prefix = None
                if isinstance(item[1], str) and item[1] in VALID_PARENT_RELATIONS:
                    prefix = item[:2]
                elif isinstance(item[2], str) and item[2] in VALID_PARENT_RELATIONS:
                    prefix = item[:3]
                if prefix is not None:
                    normalized[key] = prefix
                    repairs.append(
                        {
                            "path": ".".join(current_path),
                            "before": item,
                            "after": prefix,
                        }
                    )
                    continue
            normalized_item, item_repairs = normalize_overfull_parents(
                item, current_path
            )
            normalized[key] = normalized_item
            repairs.extend(item_repairs)
        return normalized, repairs
    if isinstance(value, list):
        normalized_items = []
        repairs = []
        for index, item in enumerate(value):
            normalized_item, item_repairs = normalize_overfull_parents(
                item, path + (str(index),)
            )
            normalized_items.append(normalized_item)
            repairs.extend(item_repairs)
        return normalized_items, repairs
    return value, []


def normalize_invalid_parents(
    value: Any, path: tuple[str, ...] = ()
) -> tuple[Any, list[dict[str, Any]]]:
    """Drop only unsupported parent relations while retaining absolute poses.

    SceneWeaver's placement prompt supplies an absolute position/rotation/size
    for every object, so an undeclared natural-language relation is redundant.
    Passing it through makes the executor call ``getattr`` on a missing
    constraint and abort the entire scene.  Recognized relation synonyms have
    already been canonicalized by ``_normalize_relation_values`` above.
    """

    if isinstance(value, dict):
        normalized: dict[str, Any] = {}
        repairs: list[dict[str, Any]] = []
        for key, item in value.items():
            current_path = path + (str(key),)
            if (
                key == "parent"
                and isinstance(item, list)
                and len(item) in (2, 3)
                and not any(isinstance(element, (list, dict)) for element in item)
            ):
                relation = (
                    item[1] if len(item) == 2 else item[2] if len(item) == 3 else None
                )
                if relation not in VALID_PARENT_RELATIONS:
                    normalized[key] = []
                    repairs.append(
                        {
                            "path": ".".join(current_path),
                            "before": item,
                            "after": [],
                            "reason": "unsupported_relation",
                        }
                    )
                    continue
            normalized_item, item_repairs = normalize_invalid_parents(
                item, current_path
            )
            normalized[key] = normalized_item
            repairs.extend(item_repairs)
        return normalized, repairs
    if isinstance(value, list):
        normalized_items = []
        repairs = []
        for index, item in enumerate(value):
            normalized_item, item_repairs = normalize_invalid_parents(
                item, path + (str(index),)
            )
            normalized_items.append(normalized_item)
            repairs.extend(item_repairs)
        return normalized_items, repairs
    return value, []


def extract_sceneweaver_json(input_string: str) -> dict[str, Any]:
    """Parse common provider JSON deviations without changing field values."""

    text = str(input_string)
    mapping_match = re.search(r"[\"']Mapping results[\"']\s*:\s*", text)
    mapping_start = text.find("{", mapping_match.end()) if mapping_match else -1
    last_error: Exception | None = None
    for match in re.finditer(r"[\{\[]", text):
        start = match.start()
        serialized = _balanced_container(text, start)
        if serialized is None:
            continue
        try:
            parsed = _coerce_tool_payload(_parse_container_literal(serialized))
            normalized = _normalize_absent_parents(
                _normalize_relation_values(_normalize_schema_keys(parsed))
            )
            normalized, size_repairs = normalize_nested_size_components(normalized)
            if size_repairs:
                print(
                    "SIZE_COMPONENT_REPAIR "
                    + json.dumps(size_repairs, ensure_ascii=False, sort_keys=True),
                    flush=True,
                )
            normalized, parent_repairs = normalize_overfull_parents(normalized)
            if parent_repairs:
                print(
                    "PARENT_RELATION_REPAIR "
                    + json.dumps(parent_repairs, ensure_ascii=False, sort_keys=True),
                    flush=True,
                )
            normalized, invalid_parent_repairs = normalize_invalid_parents(normalized)
            if invalid_parent_repairs:
                print(
                    "INVALID_PARENT_RELATION_REPAIR "
                    + json.dumps(
                        invalid_parent_repairs, ensure_ascii=False, sort_keys=True
                    ),
                    flush=True,
                )
            if start == mapping_start:
                return {"Mapping results": normalized}
            return normalized
        except (SyntaxError, ValueError) as error:
            # Prose often contains coordinate arrays before the requested JSON;
            # skip any container that cannot represent a tool payload.
            last_error = error
    if last_error is not None:
        raise ValueError(f"No usable SceneWeaver tool payload: {last_error}")
    raise ValueError("No complete container found in SceneWeaver tool response")


def repair_exact_factory_mapping(
    category_names: Any,
    mapping: dict[str, Any] | None,
    exact_mappings: dict[str, str],
) -> dict[str, Any]:
    """Enforce the advertised factory for known native category names."""

    repaired = dict(mapping or {})
    by_compact_name = {_compact_key(key): key for key in repaired}
    for category in category_names:
        compact_name = _compact_key(category)
        mapping_name = compact_name
        if mapping_name not in exact_mappings and mapping_name.endswith("factory"):
            mapping_name = mapping_name[: -len("factory")]
        if mapping_name not in exact_mappings:
            continue
        output_key = by_compact_name.get(compact_name, category)
        value = repaired.get(output_key)
        if value != exact_mappings[mapping_name]:
            repaired[output_key] = exact_mappings[mapping_name]
    return repaired


def repair_rotation_update_sizes(
    updated_layout: dict[str, Any], prior_layout: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    """Supply unchanged sizes omitted by the rotation-only prompt schema."""

    repaired = {
        name: dict(info) if isinstance(info, dict) else info
        for name, info in updated_layout.items()
    }
    repaired_names: list[str] = []
    for name, info in repaired.items():
        prior = prior_layout.get(name)
        if (
            isinstance(info, dict)
            and "size" not in info
            and isinstance(prior, dict)
            and isinstance(prior.get("size"), list)
        ):
            info["size"] = list(prior["size"])
            repaired_names.append(name)
    return repaired, repaired_names


def filter_unavailable_additions(
    payload: dict[str, Any], is_fallback_supported: Any
) -> tuple[dict[str, Any], list[str]]:
    """Drop only additions that have neither a factory nor a fallback asset."""

    repaired = dict(payload)
    categories = dict(payload.get("Number of new furniture", {}))
    mapping = dict(payload.get("name_mapping", {}))
    mapping_by_name = {_compact_key(name): value for name, value in mapping.items()}
    unavailable = [
        category
        for category in categories
        if mapping_by_name.get(_compact_key(category)) is None
        and not is_fallback_supported(category)
    ]
    if not unavailable:
        return repaired, []

    unavailable_keys = {_compact_key(name) for name in unavailable}
    repaired["Number of new furniture"] = {
        name: count
        for name, count in categories.items()
        if _compact_key(name) not in unavailable_keys
    }
    repaired["name_mapping"] = {
        name: factory
        for name, factory in mapping.items()
        if _compact_key(name) not in unavailable_keys
    }
    if isinstance(payload.get("Placement"), dict):
        repaired["Placement"] = {
            name: placement
            for name, placement in payload["Placement"].items()
            if _compact_key(name) not in unavailable_keys
        }
    for key in ("category_against_wall", "category_on_the_floor"):
        if isinstance(payload.get(key), list):
            repaired[key] = [
                name
                for name in payload[key]
                if _compact_key(name) not in unavailable_keys
            ]
    if isinstance(payload.get("Relation"), list):
        repaired["Relation"] = [
            relation
            for relation in payload["Relation"]
            if not (
                isinstance(relation, list)
                and relation
                and _compact_key(relation[0]) in unavailable_keys
            )
        ]
    return repaired, unavailable


def filter_unavailable_initial_objects(
    payload: dict[str, Any], is_fallback_supported: Any
) -> tuple[dict[str, Any], list[str], list[dict[str, Any]]]:
    """Remove unsupported initial categories and dangling parent references."""

    repaired = dict(payload)
    categories = dict(payload.get("big_category_dict", {}))
    mapping = dict(payload.get("name_mapping", {}))
    mapping_by_name = {_compact_key(name): value for name, value in mapping.items()}
    unavailable = [
        category
        for category in categories
        if mapping_by_name.get(_compact_key(category)) is None
        and not is_fallback_supported(category)
    ]
    unavailable_keys = {_compact_key(name) for name in unavailable}
    retained_categories = {
        _compact_key(name)
        for name in categories
        if _compact_key(name) not in unavailable_keys
    }
    repaired["big_category_dict"] = {
        name: count
        for name, count in categories.items()
        if _compact_key(name) in retained_categories
    }
    repaired["name_mapping"] = {
        name: factory
        for name, factory in mapping.items()
        if _compact_key(name) in retained_categories
    }
    placements = dict(payload.get("Placement_big", {}))
    parent_repairs: list[dict[str, Any]] = []
    filtered_placements: dict[str, Any] = {}
    for category, instances in placements.items():
        if _compact_key(category) not in retained_categories:
            continue
        if not isinstance(instances, dict):
            filtered_placements[category] = instances
            continue
        copied_instances: dict[str, Any] = {}
        for instance, placement in instances.items():
            copied = dict(placement) if isinstance(placement, dict) else placement
            if isinstance(copied, dict):
                parent = copied.get("parent")
                if (
                    isinstance(parent, list)
                    and parent
                    and _compact_key(parent[0]) not in retained_categories
                ):
                    parent_repairs.append(
                        {
                            "path": f"Placement_big.{category}.{instance}.parent",
                            "before": parent,
                            "after": [],
                            "reason": "missing_parent_category",
                        }
                    )
                    copied["parent"] = []
            copied_instances[instance] = copied
        filtered_placements[category] = copied_instances
    repaired["Placement_big"] = filtered_placements
    repaired["category_against_wall"] = [
        name
        for name in payload.get("category_against_wall", [])
        if _compact_key(name) in retained_categories
    ]
    repaired["relation_big_object"] = [
        relation
        for relation in payload.get("relation_big_object", [])
        if isinstance(relation, list)
        and len(relation) >= 2
        and _compact_key(relation[0]) in retained_categories
        and _compact_key(relation[1]) in retained_categories
    ]
    return repaired, unavailable, parent_repairs


def patch_loaded_tool_references(
    extract_json_compat: Any,
    factory_mapping_compat: Any,
) -> None:
    """Update names captured by ``from ... import ...`` in loaded tool modules."""

    for module_name, module in list(sys.modules.items()):
        if not module_name.startswith("app.tool."):
            continue
        if hasattr(module, "extract_json"):
            module.extract_json = extract_json_compat
        if hasattr(module, "complete_factory_mapping"):
            module.complete_factory_mapping = factory_mapping_compat


def seed_everything(seed: int) -> None:
    os.environ["SCENEWEAVER_SEED"] = str(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed)
    except ImportError:
        pass
    # The planner process performs no Torch computation; all stochastic 3-D
    # generation happens in the separately seeded executor.  Importing Torch
    # here used to scan thousands of files in the shared NFS environment and
    # could stall every planner launch for many minutes without changing any
    # SceneWeaver output.


def install_codex_provider_import_stubs() -> None:
    """Avoid importing provider SDKs that the Codex bridge never executes."""

    if os.environ.get("SCENEWEAVER_LLM_BACKEND") != "codex_cli":
        return
    import types

    if "openai" not in sys.modules:
        openai_stub = types.ModuleType("openai")

        class OpenAIError(Exception):
            pass

        class ProviderClient:
            def __init__(self, *args, **kwargs):
                self.chat = None

        for name in (
            "APIError",
            "APIConnectionError",
            "APITimeoutError",
            "AuthenticationError",
            "InternalServerError",
            "RateLimitError",
        ):
            setattr(openai_stub, name, type(name, (OpenAIError,), {}))
        openai_stub.OpenAIError = OpenAIError
        openai_stub.OpenAI = ProviderClient
        openai_stub.AzureOpenAI = ProviderClient
        sys.modules["openai"] = openai_stub

    if "tiktoken" not in sys.modules:
        tiktoken_stub = types.ModuleType("tiktoken")

        class UnusedTokenizer:
            def encode(self, value):
                return list(str(value).encode("utf-8"))

        tiktoken_stub.encoding_for_model = lambda model: UnusedTokenizer()
        tiktoken_stub.get_encoding = lambda name: UnusedTokenizer()
        sys.modules["tiktoken"] = tiktoken_stub


def install_compatibility() -> None:
    sys.path.insert(0, str(ORIGINAL_PIPELINE))

    # Upstream writes its process log beside the source checkout during import.
    # Redirect that mutable state before importing ``app.logger`` indirectly.
    from app import config as config_module

    planner_state = (
        BASELINES_ROOT / "methods/sceneweaver/runtime/sceneweaver_pipeline/state"
    )
    (planner_state / "logs").mkdir(parents=True, exist_ok=True)
    (planner_state / "workspace").mkdir(parents=True, exist_ok=True)
    config_module.PROJECT_ROOT = planner_state
    config_module.WORKSPACE_ROOT = planner_state / "workspace"

    install_codex_provider_import_stubs()
    print("SCENEWEAVER_INIT_STAGE provider_stubs_installed", flush=True)
    from app import utils as app_utils

    print("SCENEWEAVER_INIT_STAGE importing_llm", flush=True)
    from app.llm import LLM

    print("SCENEWEAVER_INIT_STAGE llm_imported", flush=True)
    from app.schema import Function, Message, ToolCall

    print("SCENEWEAVER_INIT_STAGE importing_tools", flush=True)
    from app.tool import init_gpt
    from app.tool.add_crowd import AddCrowdExecute
    from app.tool.add_gpt import AddGPTExecute
    from app.tool.remove_obj import RemoveExecute
    from app.tool.update_rotation import UpdateRotationExecute
    from TongGPT import GPT4o

    print("SCENEWEAVER_INIT_STAGE tools_imported", flush=True)

    # Install this before importing the remaining tool modules so their
    # ``from app.utils import extract_json`` references receive the compatible
    # parser.  ``init_gpt`` was imported above and needs its local reference
    # updated explicitly.
    app_utils.extract_json = extract_sceneweaver_json
    init_gpt.extract_json = extract_sceneweaver_json
    original_lst2str = app_utils.lst2str

    def compatible_lst2str(value):
        return "[]" if not value else original_lst2str(value)

    app_utils.lst2str = compatible_lst2str
    init_gpt.lst2str = compatible_lst2str
    init_gpt.EXACT_FACTORY_MAPPINGS.update(FACTORY_COMPATIBILITY)
    exact_factory_mappings = init_gpt.EXACT_FACTORY_MAPPINGS

    def compatible_factory_mapping(category_names, mapping):
        repaired = repair_exact_factory_mapping(
            category_names, mapping, exact_factory_mappings
        )
        if repaired != dict(mapping or {}):
            print(
                "FACTORY_MAPPING_REPAIR "
                + json.dumps(
                    {
                        "categories": list(category_names),
                        "before": mapping,
                        "after": repaired,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                flush=True,
            )
        return repaired

    init_gpt.complete_factory_mapping = compatible_factory_mapping
    patch_loaded_tool_references(extract_sceneweaver_json, compatible_factory_mapping)

    original_ask_tool = LLM.ask_tool

    def compatible_ask_tool(self, messages, *args, **kwargs):
        declared_tools = kwargs.get("tools")
        # ``tools`` is the third positional argument after ``messages`` in the
        # frozen upstream signature.  SceneWeaver currently passes it by name,
        # but retaining positional compatibility keeps this wrapper faithful.
        if declared_tools is None and len(args) >= 3:
            declared_tools = args[2]
        system_msgs = kwargs.get("system_msgs")
        if system_msgs is None and len(args) >= 1:
            system_msgs = args[0]
        tool_choice = kwargs.get("tool_choice")
        if tool_choice is None and len(args) >= 4:
            tool_choice = args[3]
        if tool_choice is None:
            tool_choice = "auto"
        if os.environ.get("SCENEWEAVER_LLM_BACKEND") == "codex_cli":
            from baselines.methods.sceneweaver.runtime.sceneweaver_pipeline.codex_llm_bridge import (
                ask_tool_with_codex,
            )

            response = ask_tool_with_codex(
                messages=list(messages),
                system_msgs=list(system_msgs or []),
                tools=declared_tools,
                tool_choice=tool_choice,
                message_class=Message,
                function_class=Function,
                tool_call_class=ToolCall,
                timeout_s=int(os.environ.get("SCENEWEAVER_CODEX_TIMEOUT_S", "900")),
            )
        else:
            if self.api_type.lower() == "openrouter":
                messages = flatten_openrouter_tool_history(list(messages), Message)
            response = original_ask_tool(self, messages, *args, **kwargs)
        if not getattr(response, "tool_calls", None):
            content, recovered = recover_openrouter_text_tool_calls(
                getattr(response, "content", None), declared_tools
            )
            if recovered:
                print(
                    "OPENROUTER_TEXT_TOOL_RECOVERY "
                    + json.dumps(
                        {"call_id": recovered[0]["id"], "name": recovered[0]["name"]},
                        sort_keys=True,
                    ),
                    flush=True,
                )
                response = Message(
                    role="assistant",
                    content=content,
                    tool_calls=[
                        ToolCall(
                            id=call["id"],
                            function=Function(
                                name=call["name"], arguments=call["arguments"]
                            ),
                        )
                        for call in recovered
                    ],
                )

        repaired_calls = []
        changed = False
        for call in getattr(response, "tool_calls", None) or []:
            function = getattr(call, "function", None)
            cleaned, removed = sanitize_declared_tool_arguments(
                getattr(function, "name", None),
                getattr(function, "arguments", None),
                declared_tools,
            )
            if removed:
                changed = True
                print(
                    "TOOL_ARGUMENT_SCHEMA_REPAIR "
                    + json.dumps(
                        {
                            "name": getattr(function, "name", None),
                            "removed": removed,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
            repaired_calls.append(
                ToolCall(
                    id=getattr(call, "id", None),
                    function=Function(
                        name=getattr(function, "name", None), arguments=cleaned
                    ),
                )
            )
        if changed:
            return Message(
                role="assistant",
                content=getattr(response, "content", None),
                tool_calls=repaired_calls,
            )
        return response

    LLM.ask_tool = compatible_ask_tool

    original_tool_send_request = GPT4o.send_request

    def send_request_with_length_repair(self, payload):
        if os.environ.get("SCENEWEAVER_LLM_BACKEND") == "codex_cli":
            from baselines.methods.sceneweaver.runtime.sceneweaver_pipeline.codex_llm_bridge import (
                send_text_with_codex,
            )
            from types import SimpleNamespace

            content = send_text_with_codex(
                payload,
                timeout_s=int(os.environ.get("SCENEWEAVER_CODEX_TIMEOUT_S", "900")),
            )
            return SimpleNamespace(
                id="sceneweaver_codex_auxiliary",
                model=os.environ.get("SCENEWEAVER_CODEX_MODEL", "gpt-6-astra"),
                choices=[
                    SimpleNamespace(
                        finish_reason="stop",
                        message=SimpleNamespace(content=content),
                    )
                ],
                usage=SimpleNamespace(
                    prompt_tokens=None,
                    completion_tokens=None,
                    total_tokens=None,
                ),
            )
        response = original_tool_send_request(self, payload)
        if not response_was_length_truncated(response):
            return response

        print(
            "LLM_LENGTH_REPAIR "
            + json.dumps({"endpoint": "tool.send_request", "retry": 1}, sort_keys=True),
            flush=True,
        )
        repaired_payload = dict(payload)
        repaired_payload["messages"] = list(payload["messages"]) + [
            {
                "role": "user",
                "content": (
                    "The previous answer reached the output limit. Restart from the "
                    "original instructions and return only the requested compact final "
                    "answer (valid JSON when JSON was requested), with no analysis or "
                    "commentary. Do not continue the truncated text."
                ),
            }
        ]
        return original_tool_send_request(self, repaired_payload)

    GPT4o.send_request = send_request_with_length_repair

    # Deleting a supporter before an object placed relative to it leaves a
    # dangling constraint and can terminate Blender natively.  Preserve the
    # LLM-selected set, but apply it child-first.
    original_remove_update = RemoveExecute.update_scene_gpt

    def child_first_remove_update(self, user_demand, ideas, iter, roomtype):
        result_path = Path(
            original_remove_update(self, user_demand, ideas, iter, roomtype)
        )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        selected = list(payload.get("objects to remove", []))
        layout_path = (
            Path(os.environ["save_dir"]) / f"record_scene/layout_{iter-1}.json"
        )
        layout = json.loads(layout_path.read_text(encoding="utf-8")).get("objects", {})
        selected_set = set(selected)

        def depth(name: str, visiting: set[str] | None = None) -> int:
            visiting = set() if visiting is None else set(visiting)
            if name in visiting:
                return 0
            visiting.add(name)
            parents = layout.get(name, {}).get("parent", [])
            parent_names = []
            for relation in parents:
                if isinstance(relation, list) and relation:
                    parent_names.append(str(relation[0]))
            return 1 + max(
                (
                    depth(parent, visiting)
                    for parent in parent_names
                    if parent in selected_set
                ),
                default=-1,
            )

        payload["objects to remove"] = sorted(
            selected, key=lambda name: (-depth(name), selected.index(name))
        )
        result_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4) + "\n", encoding="utf-8"
        )
        return str(result_path)

    RemoveExecute.update_scene_gpt = child_first_remove_update

    # The upstream rotation prompt intentionally requests only location and
    # rotation, while its shared ``update`` executor unconditionally reads a
    # size for every object.  Carry the unchanged size forward from the exact
    # preceding checkpoint rather than asking the provider to invent it.
    original_rotation_update = UpdateRotationExecute.update_scene_gpt

    def rotation_update_with_sizes(self, user_demand, ideas, iter, roomtype):
        result_path = Path(
            original_rotation_update(self, user_demand, ideas, iter, roomtype)
        )
        updated = json.loads(result_path.read_text(encoding="utf-8"))
        layout_path = (
            Path(os.environ["save_dir"]) / f"record_scene/layout_{iter-1}.json"
        )
        prior = json.loads(layout_path.read_text(encoding="utf-8")).get("objects", {})
        repaired, repaired_names = repair_rotation_update_sizes(updated, prior)
        if repaired_names:
            result_path.write_text(
                json.dumps(repaired, ensure_ascii=False, indent=4) + "\n",
                encoding="utf-8",
            )
            print(
                "ROTATION_SIZE_REPAIR "
                + json.dumps({"objects": repaired_names}, sort_keys=True),
                flush=True,
            )
        return str(result_path)

    UpdateRotationExecute.update_scene_gpt = rotation_update_with_sizes

    # The published Objaverse retrieval path depends on an unavailable
    # author-specific IDesign checkpoint.  This run uses the frozen local
    # 3D-FUTURE fallback.  Preserve every mapped/native addition and every
    # null-mapped category the fallback can actually resolve; omit only the
    # categories that would otherwise raise and discard the whole tool step.
    retrieve_spec = importlib.util.spec_from_file_location(
        "sceneweaver_local_retrieve_probe",
        SCENEWEAVER_ROOT / "infinigen/assets/objaverse_assets/local_retrieve.py",
    )
    if retrieve_spec is None or retrieve_spec.loader is None:
        raise RuntimeError("Cannot load SceneWeaver local asset retrieval policy")
    retrieve_probe = importlib.util.module_from_spec(retrieve_spec)
    retrieve_spec.loader.exec_module(retrieve_probe)
    index_records = json.loads(
        Path(os.environ["SCENEWEAVER_3D_FUTURE_INDEX"]).read_text(encoding="utf-8")
    )
    available_records = [
        record for record in index_records if Path(record["path"]).is_file()
    ]

    def fallback_supported(category: str) -> bool:
        retrieve_probe.ALIASES.setdefault("lshapedsofa", ("l shaped sofa",))
        return any(
            retrieve_probe.score(category, record) > 0 for record in available_records
        )

    original_init_generate = init_gpt.InitGPTExecute.generate_scene_iter0

    def compatible_init_generate(self, user_demand, ideas, roomtype):
        pipeline_dir = Path(os.environ["save_dir"]) / "pipeline"
        cached = sorted(pipeline_dir.glob("init_gpt_results_*.json"))
        if cached:
            result_path = cached[-1]
            print(
                "SCENEWEAVER_REUSE_INIT_JSON "
                + json.dumps({"path": str(result_path)}, sort_keys=True),
                flush=True,
            )
        else:
            result_path = Path(
                original_init_generate(self, user_demand, ideas, roomtype)
            )
        payload = json.loads(result_path.read_text(encoding="utf-8"))
        payload = _normalize_absent_parents(_normalize_relation_values(payload))
        payload, invalid_repairs = normalize_invalid_parents(payload)
        payload["name_mapping"] = compatible_factory_mapping(
            payload.get("big_category_dict", {}).keys(),
            payload.get("name_mapping", {}),
        )
        payload, unavailable, dangling_repairs = filter_unavailable_initial_objects(
            payload, fallback_supported
        )
        repairs = invalid_repairs + dangling_repairs
        if repairs:
            print(
                "INITIAL_PARENT_RELATION_REPAIR "
                + json.dumps(repairs, ensure_ascii=False, sort_keys=True),
                flush=True,
            )
        if unavailable:
            print(
                "INITIAL_UNAVAILABLE_CATEGORY_SKIPPED "
                + json.dumps(
                    {"categories": unavailable}, ensure_ascii=False, sort_keys=True
                ),
                flush=True,
            )
        result_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=4) + "\n",
            encoding="utf-8",
        )
        return str(result_path)

    init_gpt.InitGPTExecute.generate_scene_iter0 = compatible_init_generate

    def install_addition_filter(tool_class: Any) -> None:
        original = tool_class.generate_scene_iter1_gpt

        def generate_with_available_assets(self, user_demand, ideas, iter, roomtype):
            result = original(self, user_demand, ideas, iter, roomtype)
            if result == "Nothing":
                return result
            result_path = Path(result)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            repaired, unavailable = filter_unavailable_additions(
                payload, fallback_supported
            )
            if unavailable:
                result_path.write_text(
                    json.dumps(repaired, ensure_ascii=False, indent=4) + "\n",
                    encoding="utf-8",
                )
                print(
                    "UNAVAILABLE_ASSET_CATEGORY_SKIPPED "
                    + json.dumps(
                        {"categories": unavailable, "tool": self.name},
                        ensure_ascii=False,
                        sort_keys=True,
                    ),
                    flush=True,
                )
            return (
                str(result_path)
                if repaired.get("Number of new furniture")
                else "Nothing"
            )

        tool_class.generate_scene_iter1_gpt = generate_with_available_assets

    install_addition_filter(AddGPTExecute)
    install_addition_filter(AddCrowdExecute)


def run(prompt: str, save_dir: Path, seed: int) -> None:
    print("SCENEWEAVER_INIT_STAGE entry", flush=True)
    seed_everything(seed)
    print("SCENEWEAVER_INIT_STAGE seeded", flush=True)
    save_dir = save_dir.expanduser().resolve()
    save_dir.mkdir(parents=True, exist_ok=True)
    for name in ("pipeline", "args", "record_files", "record_scene"):
        (save_dir / name).mkdir(exist_ok=True)

    os.environ["save_dir"] = str(save_dir)
    os.environ["UserDemand"] = prompt
    os.environ["socket"] = "False"
    os.environ["sceneweaver_dir"] = str(SCENEWEAVER_ROOT)
    if not prompt.strip():
        raise ValueError("Prompt must not be empty")

    print("SCENEWEAVER_INIT_STAGE install_compatibility", flush=True)
    install_compatibility()
    print("SCENEWEAVER_INIT_STAGE compatibility_installed", flush=True)
    from app.agent.scenedesigner import SceneDesigner
    from app.logger import logger

    print("SCENEWEAVER_INIT_STAGE scenedesigner_imported", flush=True)

    # SceneDesigner imports several tools only after ``install_compatibility``
    # returns.  Rebind their module-local names now that the full tool set is
    # loaded; otherwise late imports keep the original strict JSON parser.
    from app.tool import init_gpt

    patch_loaded_tool_references(
        extract_sceneweaver_json, init_gpt.complete_factory_mapping
    )

    logger.warning("Processing your request...")
    agent = SceneDesigner()
    result = agent.run(prompt)
    logger.info("Request processing completed.")
    print(result)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--save-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_args()
    run(arguments.prompt, arguments.save_dir, arguments.seed)
    # OpenAI-compatible HTTP clients can leave non-daemon provider threads
    # alive after ``run`` has returned.  This file is a dedicated subprocess,
    # and all SceneWeaver outputs/checkpoints are already closed at this point;
    # flush the observable streams and avoid waiting until the outer six-hour
    # generation timeout for unrelated client cleanup.
    sys.stdout.flush()
    sys.stderr.flush()
    os._exit(0)

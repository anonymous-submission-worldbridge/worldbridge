#!/usr/bin/env python3
"""Validator for Gemini connected demos, including Blender's native bmesh module."""
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


import ast


def check_code(code: str) -> ast.AST:
    tree = ast.parse(code)
    allowed = {"bpy", "bmesh", "math", "random", "numpy", "mathutils", "collections"}
    forbidden = {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "globals",
        "locals",
        "input",
        "breakpoint",
    }
    forbidden_attrs = {
        "save_as_mainfile",
        "open_mainfile",
        "read_homefile",
        "load",
        "save",
        "write",
        "remove_doubles_exec",
        "handlers",
        "driver_add",
        "keyframe_insert",
        "filepath",
        "preferences",
        "libraries",
        "scripts",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name.split(".")[0] not in allowed for alias in node.names):
                raise ValueError("Unsupported import in generated scene")
        if isinstance(node, ast.ImportFrom):
            if node.level or (node.module or "").split(".")[0] not in allowed:
                raise ValueError("Unsupported import in generated scene")
        if isinstance(node, ast.Name) and node.id in forbidden:
            raise ValueError("Unsupported builtin in generated scene: " + node.id)
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__") or node.attr in forbidden_attrs
        ):
            raise ValueError("Unsupported attribute in generated scene: " + node.attr)
    if not any(
        isinstance(node, ast.FunctionDef) and node.name == "build_scene"
        for node in tree.body
    ):
        raise ValueError("Generated code must define build_scene(seed)")
    return tree

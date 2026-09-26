"""Relocation and compatibility checks for the new public entry points."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def test_descriptor_cli_works_outside_checkout(tmp_path):
    output = tmp_path / "descriptor.json"
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/infer.py"),
            "--seed",
            "42",
            "--topology",
            "offset",
            "--output",
            str(output),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    descriptor = json.loads(output.read_text())
    assert descriptor["scene_seed"] == 42
    assert descriptor["road_topology"] == "offset"
    evaluation = subprocess.run(
        [sys.executable, str(ROOT / "scripts/evaluate.py"), str(output)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert evaluation.returncode == 0, evaluation.stderr
    assert json.loads(evaluation.stdout) == {"valid": True, "errors": []}


def test_baseline_help_does_not_require_model_files(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/compare.py"),
            "--method",
            "worldgen",
            "--",
            "--help",
        ],
        cwd=tmp_path,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "compile" in result.stdout and "worker" in result.stdout


def test_legacy_llm_environment_alias_and_provider_priority():
    # A subprocess isolates this test from the existing resolver tests' LLM stub.
    code = """
import os
from worldbridge.llm_config import _first_env_with_name
os.environ['LEGACYWORLD_API_KEY'] = 'legacy-test-value'
os.environ['WORLDBRIDGE_API_KEY'] = 'new-test-value'
os.environ['OPENAI_API_KEY'] = 'provider-test-value'
assert _first_env_with_name('LEGACYWORLD_API_KEY') == ('new-test-value', 'WORLDBRIDGE_API_KEY')
assert _first_env_with_name('OPENAI_API_KEY', 'LEGACYWORLD_API_KEY') == ('provider-test-value', 'OPENAI_API_KEY')
del os.environ['WORLDBRIDGE_API_KEY']
assert _first_env_with_name('LEGACYWORLD_API_KEY') == ('legacy-test-value', 'LEGACYWORLD_API_KEY')
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

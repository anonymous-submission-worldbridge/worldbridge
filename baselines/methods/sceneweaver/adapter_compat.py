#!/usr/bin/env python3
"""Run the frozen SceneWeaver adapter through the local compatibility entry point."""

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
from worldbridge.paths import (
    expand_paths as _wb_expand_paths,
    path_variables as _wb_path_variables,
)

_wb_paths = _wb_path_variables()


import hashlib
import importlib.util
import argparse
import fcntl
import json
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path


BASELINES_ROOT = Path(_wb_expand_paths("${WORLDBRIDGE_ROOT}/baselines"))
REPO_ROOT = BASELINES_ROOT.parent
ORIGINAL_ADAPTER = BASELINES_ROOT / "methods/sceneweaver/adapter.py"
RUNTIME_PIPELINE = BASELINES_ROOT / "methods/sceneweaver/runtime/sceneweaver_pipeline"
RUNTIME_EXECUTOR = BASELINES_ROOT / "methods/sceneweaver/runtime/sceneweaver_executor"
COLLISION_FACE_BUDGET = 200000
CODEX_MODEL = "gpt-6-astra"
CODEX_REASONING_EFFORT = "medium"
CODEX_TIMEOUT_S = 900
FROZEN_CODEX_CLI = BASELINES_ROOT / "tools/codex-sceneweaver-frozen"
MIXED_PROTOCOL = (
    BASELINES_ROOT
    / "methods/sceneweaver/protocol/generation/sceneweaver_mixed_codex.json"
)


def retained_terminal_run(spec_id: str, logical_seed: int) -> bool:
    protocol = json.loads(MIXED_PROTOCOL.read_text(encoding="utf-8"))
    key = f"{spec_id}/seed_{logical_seed}"
    return key in set(protocol["retained_terminal_runs"])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_adapter():
    spec = importlib.util.spec_from_file_location(
        "sceneweaver_frozen_adapter", ORIGINAL_ADAPTER
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load SceneWeaver adapter from {ORIGINAL_ADAPTER}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def supervised_run_logged(
    command: list[str],
    log_path: Path,
    env: dict[str, str],
    cwd: Path,
    timeout_s: int,
) -> tuple[int, float, bool]:
    """Run a dedicated process group so interruption cannot orphan Blender."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write("COMMAND_JSON=" + json.dumps(command, ensure_ascii=False) + "\n")
        log.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        def stop_group(sig: signal.Signals, wait_s: int) -> int | None:
            try:
                os.killpg(process.pid, sig)
            except ProcessLookupError:
                pass
            try:
                return process.wait(timeout=wait_s)
            except subprocess.TimeoutExpired:
                return None

        try:
            exit_code = process.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            timed_out = True
            exit_code = stop_group(signal.SIGTERM, 30)
            if exit_code is None:
                exit_code = stop_group(signal.SIGKILL, 30)
            if exit_code is None:
                exit_code = process.wait()
        except KeyboardInterrupt:
            exit_code = stop_group(signal.SIGTERM, 10)
            if exit_code is None:
                stop_group(signal.SIGKILL, 10)
            raise
    return exit_code, time.monotonic() - started, timed_out


def main() -> int:
    adapter = load_adapter()
    adapter.BASELINES_ROOT = BASELINES_ROOT
    adapter.REPO_ROOT = REPO_ROOT
    adapter.SCENEWEAVER_ROOT = BASELINES_ROOT / "vendor/SceneWeaver"
    adapter.PIPELINE_ROOT = RUNTIME_PIPELINE
    adapter.EXECUTOR_PYTHON = BASELINES_ROOT / "runtime/sceneweaver_executor_launcher"
    adapter.ASSET_INDEX = BASELINES_ROOT / "cache/sceneweaver/3d_future_index.json"
    adapter.BLENDER_RENDER_SCRIPT = (
        BASELINES_ROOT / "methods/sceneweaver/tools/blender_render_sceneweaver.py"
    )
    adapter.DEFAULT_SPEC_FILE = (
        BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"
    )
    adapter.DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
    adapter.PROTOCOL_FILE = BASELINES_ROOT / "protocol/generation/protocol.yaml"
    original_source_hashes = adapter.source_hashes

    def source_hashes() -> dict[str, str]:
        hashes = original_source_hashes()
        hashes[
            "baselines/methods/sceneweaver/runtime/sceneweaver_pipeline/main.py"
        ] = sha256_file(RUNTIME_PIPELINE / "main.py")
        hashes[
            "baselines/methods/sceneweaver/runtime/sceneweaver_pipeline/codex_llm_bridge.py"
        ] = sha256_file(RUNTIME_PIPELINE / "codex_llm_bridge.py")
        hashes["baselines/methods/sceneweaver/adapter_compat.py"] = sha256_file(
            Path(__file__)
        )
        hashes[
            "baselines/methods/sceneweaver/runtime/sceneweaver_executor/generate_indoors_compat.py"
        ] = sha256_file(RUNTIME_EXECUTOR / "generate_indoors_compat.py")
        hashes["baselines/runtime/sceneweaver_executor_launcher"] = sha256_file(
            BASELINES_ROOT / "runtime/sceneweaver_executor_launcher"
        )
        hashes[
            "baselines/methods/sceneweaver/runtime/sceneweaver_executor_resume_compat.py"
        ] = sha256_file(
            BASELINES_ROOT
            / "methods/sceneweaver/runtime/sceneweaver_executor_resume_compat.py"
        )
        hashes[
            "baselines/envs/sceneweaver_executor/lib/python3.10/"
            "site-packages/dill/__init__.py"
        ] = sha256_file(
            BASELINES_ROOT / "envs/sceneweaver_executor/lib/python3.10/"
            "site-packages/dill/__init__.py"
        )
        hashes[
            "baselines/envs/sceneweaver_executor/lib/python3.10/"
            "site-packages/dill/_dill.py"
        ] = sha256_file(
            BASELINES_ROOT / "envs/sceneweaver_executor/lib/python3.10/"
            "site-packages/dill/_dill.py"
        )
        return hashes

    adapter.source_hashes = source_hashes
    adapter.__file__ = str(
        (BASELINES_ROOT / "methods/sceneweaver/adapter_compat.py").absolute()
    )
    adapter.run_logged = supervised_run_logged

    original_environment = adapter.baseline_environment
    original_native_input = adapter.build_native_input

    def compatible_native_input(spec: dict, logical_seed: int) -> dict:
        formal_run = (
            BASELINES_ROOT
            / "data/table2/indoor/sceneweaver"
            / spec["spec_id"]
            / f"seed_{logical_seed}"
        )
        existing_input = formal_run / "input/native_input.json"
        retained_terminal = retained_terminal_run(spec["spec_id"], logical_seed)
        if retained_terminal and existing_input.is_file():
            return json.loads(existing_input.read_text(encoding="utf-8"))
        archived_input = formal_run / "input/native_input.minimax_before_codex.json"
        if existing_input.is_file() and not archived_input.exists():
            archived_input.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(existing_input, archived_input)
        payload = original_native_input(spec, logical_seed)
        had_minimax_checkpoint = (
            formal_run / "sceneweaver/pipeline/memory_0.pkl"
        ).is_file()
        payload["planner"] = {
            "api_type": "codex_cli",
            "transport": "codex_exec_saved_chatgpt_login",
            "model": CODEX_MODEL,
            "reasoning_effort": CODEX_REASONING_EFFORT,
            "temperature": None,
            "max_tokens": None,
            "per_call_timeout_s": CODEX_TIMEOUT_S,
            "seed_supported": False,
            "history_policy": "bounded_sceneweaver_messages_plus_current_preview",
            "tool_policy": "one_strict_json_sceneweaver_tool_call",
            "run_mode": (
                "minimax_checkpoint_then_codex_resume"
                if had_minimax_checkpoint
                else "codex_only_new_run"
            ),
            "user_authorized_mixed_matrix": True,
            "mixed_protocol": str(MIXED_PROTOCOL),
            "mixed_protocol_sha256": sha256_file(MIXED_PROTOCOL),
        }
        payload["assets"]["collision_mesh"] = {
            "policy": "render_mesh_if_at_most_budget_else_bbox_proxy",
            "face_budget": COLLISION_FACE_BUDGET,
            "render_geometry_unchanged": True,
        }
        payload["executor_resource_controls"] = {
            "OMP_NUM_THREADS": 1,
            "OPENBLAS_NUM_THREADS": 1,
            "MKL_NUM_THREADS": 1,
            "NUMEXPR_NUM_THREADS": 1,
            "reason": "avoid_external_cpu_quota_sigkill",
        }
        payload["numerical_compatibility"] = {
            "anti_project_to_3d": "correct_y_axis_zero_cross_product_branch",
            "render_geometry_unchanged": True,
        }
        payload["infrastructure_retry"] = {
            "policy": "resume_highest_consecutive_sceneweaver_memory_checkpoint",
            "same_logical_and_method_seed": True,
            "archive_failed_step_inputs_and_logs": True,
        }
        return payload

    adapter.build_native_input = compatible_native_input

    original_initialize_run = adapter.initialize_run

    def mixed_initialize_run(spec, logical_seed, spec_file, data_root):
        run_dir = (
            Path(data_root)
            / "indoor/sceneweaver"
            / spec["spec_id"]
            / f"seed_{logical_seed}"
        )
        retained_terminal = retained_terminal_run(spec["spec_id"], logical_seed)
        had_minimax_checkpoint = (
            run_dir / "sceneweaver/pipeline/memory_0.pkl"
        ).is_file()
        actual_run_dir, manifest = original_initialize_run(
            spec, logical_seed, spec_file, data_root
        )
        if retained_terminal:
            run_mode = "retained_minimax_terminal"
        elif had_minimax_checkpoint:
            run_mode = "minimax_checkpoint_then_codex_resume"
        else:
            run_mode = "codex_only_new_run"
        manifest["planner_migration"] = {
            "aggregate_mixed_backends": True,
            "active_backend": (
                "openrouter_minimax" if retained_terminal else "codex_cli"
            ),
            "active_model": (
                "minimax/minimax-m3:free" if retained_terminal else CODEX_MODEL
            ),
            "mixed_protocol": str(MIXED_PROTOCOL),
            "mixed_protocol_sha256": sha256_file(MIXED_PROTOCOL),
            "run_mode": run_mode,
            "user_authorized": True,
        }
        if not retained_terminal:
            manifest["llm"] = {
                "api_type": "codex_cli",
                "auth": "saved_codex_chatgpt_login",
                "transport": "codex_exec_ephemeral_strict_json",
                "model": CODEX_MODEL,
                "reasoning_effort": CODEX_REASONING_EFFORT,
                "temperature": None,
                "max_tokens": None,
                "per_call_timeout_s": CODEX_TIMEOUT_S,
                "seed_supported": False,
                "api_key_recorded": False,
            }
        adapter.atomic_json(actual_run_dir / "run_manifest.json", manifest)
        return actual_run_dir, manifest

    adapter.initialize_run = mixed_initialize_run

    def writable_environment(gpu: int) -> dict[str, str]:
        env = original_environment(gpu)
        cache = BASELINES_ROOT / "runtime/sceneweaver_cache"
        paths = {
            "PYTHONPYCACHEPREFIX": cache / "pycache",
            "MPLCONFIGDIR": cache / "matplotlib",
            "XDG_CACHE_HOME": cache / "xdg",
            "XDG_CONFIG_HOME": cache / "config",
            "HF_HOME": cache / "huggingface",
            "TORCH_HOME": cache / "torch",
            "TIKTOKEN_CACHE_DIR": cache / "tiktoken",
            "TMPDIR": cache / "tmp",
        }
        for path in paths.values():
            path.mkdir(parents=True, exist_ok=True)
        env.update({name: str(path) for name, path in paths.items()})
        env["SCENEWEAVER_COLLISION_FACE_BUDGET"] = str(COLLISION_FACE_BUDGET)
        env["SCENEWEAVER_LLM_BACKEND"] = "codex_cli"
        env["SCENEWEAVER_CODEX_MODEL"] = CODEX_MODEL
        env["SCENEWEAVER_CODEX_REASONING_EFFORT"] = CODEX_REASONING_EFFORT
        env["SCENEWEAVER_CODEX_TIMEOUT_S"] = str(CODEX_TIMEOUT_S)
        env["SCENEWEAVER_CODEX_CLI"] = str(FROZEN_CODEX_CLI)
        env.update(
            {
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "NUMEXPR_NUM_THREADS": "1",
            }
        )
        return env

    adapter.baseline_environment = writable_environment

    original_generate = adapter.generate

    def planner_budget_exhausted(run_dir: Path) -> bool:
        manifest_path = run_dir / "run_manifest.json"
        if not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        generation_attempts = [
            attempt
            for attempt in manifest.get("attempts", [])
            if attempt.get("phase") == "generate"
        ]
        if not generation_attempts:
            return False
        latest = generation_attempts[-1]
        if (
            latest.get("success") is not False
            or latest.get("exit_code") != 0
            or latest.get("timed_out")
        ):
            return False
        log_path = run_dir / str(latest.get("log", ""))
        if not log_path.is_file():
            return False
        latest_log = log_path.read_text(encoding="utf-8", errors="replace")
        return (
            "Traceback (most recent call last):" not in latest_log
            and "Terminated: Reached frozen attempt budget" in latest_log
        )

    def record_generation_terminal(run_dir: Path, success: bool) -> bool:
        marker = run_dir / "PLANNER_BUDGET_EXHAUSTED"
        if success:
            marker.unlink(missing_ok=True)
            return success
        if not (marker.is_file() or planner_budget_exhausted(run_dir)):
            return success
        manifest_path = run_dir / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["failure_reason"] = "planner_attempt_budget_exhausted"
        adapter.atomic_json(manifest_path, manifest)
        marker.touch()
        print(
            "SCENEWEAVER_TERMINAL "
            + json.dumps(
                {
                    "reason": "planner_attempt_budget_exhausted",
                    "run_dir": str(run_dir),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return False

    def recover_committed_final_scene(run_dir: Path, success: bool) -> bool:
        """Accept a committed final scene despite a later optional eval error.

        Upstream evaluates once more after the ``terminate`` tool has already
        written ``finalize_scene`` with ``success=true``.  A provider-format
        error in that post-finalization score must not discard the committed
        scene.  The adapter's normal candidate check remains the authority for
        the live action, success flag, blend size, and matching layout.
        """

        if success:
            return True
        work_dir = run_dir / "sceneweaver"
        candidate = adapter.final_scene_candidate(work_dir)
        manifest_path = run_dir / "run_manifest.json"
        if candidate is None or not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        generation_attempts = [
            attempt
            for attempt in manifest.get("attempts", [])
            if attempt.get("phase") == "generate"
        ]
        if not generation_attempts:
            return False
        latest = generation_attempts[-1]
        log_path = run_dir / str(latest.get("log", ""))
        log_text = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.is_file()
            else ""
        )
        if "Successfully terminate." not in log_text:
            return False

        iteration, source_scene, source_layout = candidate
        scene_file = run_dir / "scene/scene.blend"
        scene_file.parent.mkdir(parents=True, exist_ok=True)
        link_mode = adapter.link_or_copy(source_scene, scene_file)
        shutil.copy2(source_layout, run_dir / "scene/layout.json")
        selected = {
            "iteration": iteration,
            "source_scene": str(source_scene.relative_to(run_dir)),
            "source_layout": str(source_layout.relative_to(run_dir)),
            "scene_materialization": link_mode,
            "scene_size_bytes": scene_file.stat().st_size,
            "scene_sha256": sha256_file(scene_file),
        }
        latest["selected_output"] = selected
        latest["success"] = True
        latest["post_finalize_evaluation_error_recovered"] = True
        manifest["generation_success"] = True
        manifest["render_success"] = False
        manifest["failure_reason"] = None
        adapter.atomic_json(manifest_path, manifest)
        (run_dir / "GENERATION_SUCCESS").touch()
        (run_dir / "PLANNER_BUDGET_EXHAUSTED").unlink(missing_ok=True)
        print(
            "SCENEWEAVER_COMMITTED_FINAL_RECOVERY "
            + json.dumps(
                {"iteration": iteration, "run_dir": str(run_dir)}, sort_keys=True
            ),
            flush=True,
        )
        return True

    def resumable_generate(
        scene_spec,
        logical_seed,
        spec_file,
        data_root,
        gpu,
        timeout_s,
        force,
    ):
        run_dir = (
            Path(data_root)
            / "indoor/sceneweaver"
            / scene_spec["spec_id"]
            / f"seed_{logical_seed}"
        )
        work_dir = run_dir / "sceneweaver"
        if not force and (
            (run_dir / "PLANNER_BUDGET_EXHAUSTED").is_file()
            or planner_budget_exhausted(run_dir)
        ):
            adapter.initialize_run(scene_spec, logical_seed, spec_file, data_root)
            return record_generation_terminal(run_dir, False)
        if (
            not force
            and not (run_dir / "GENERATION_SUCCESS").is_file()
            and adapter.final_scene_candidate(work_dir) is not None
        ):
            adapter.initialize_run(scene_spec, logical_seed, spec_file, data_root)
            if recover_committed_final_scene(run_dir, False):
                return True
        roominfo = work_dir / "roominfo.json"
        can_resume = (
            not force
            and roominfo.is_file()
            and (work_dir / "pipeline/memory_0.pkl").is_file()
            and (work_dir / "args/args_0.json").is_file()
            and not (run_dir / "GENERATION_SUCCESS").is_file()
        )
        if not can_resume:
            preserve_initial_json = not force and any(
                (work_dir / "pipeline").glob("init_gpt_results_*.json")
            )
            original_rmtree = adapter.shutil.rmtree

            def preserve_initial_tree(path, *args, **kwargs):
                if preserve_initial_json and Path(path) == work_dir:
                    return None
                return original_rmtree(path, *args, **kwargs)

            adapter.shutil.rmtree = preserve_initial_tree
            try:
                result = original_generate(
                    scene_spec,
                    logical_seed,
                    spec_file,
                    data_root,
                    gpu,
                    timeout_s,
                    force,
                )
            finally:
                adapter.shutil.rmtree = original_rmtree
            result = recover_committed_final_scene(run_dir, result)
            return record_generation_terminal(run_dir, result)

        resume_step = 0
        while (work_dir / f"pipeline/memory_{resume_step}.pkl").is_file() and (
            work_dir / f"args/args_{resume_step}.json"
        ).is_file():
            resume_step += 1
        manifest_path = run_dir / "run_manifest.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest_path.is_file()
            else {"attempts": []}
        )
        attempt_index = 1 + sum(
            attempt.get("phase") == "generate"
            for attempt in manifest.get("attempts", [])
        )
        suffix = f".pre_resume_attempt_{attempt_index:02d}"
        archive_candidates = [
            work_dir / "args.json",
            work_dir / f"args/args_{resume_step}.json",
            work_dir / f"logs/executor_iter_{resume_step:02d}.log",
            *sorted((work_dir / "pipeline").glob(f"*results_{resume_step}.json")),
        ]
        for source in archive_candidates:
            if source.is_file():
                destination = source.with_name(source.name + suffix)
                if not destination.exists():
                    shutil.copy2(source, destination)
        print(
            "SCENEWEAVER_RESUME "
            + json.dumps(
                {
                    "attempt": attempt_index,
                    "resume_step": resume_step,
                    "run_dir": str(run_dir),
                },
                sort_keys=True,
            ),
            flush=True,
        )

        original_rmtree = adapter.shutil.rmtree

        def preserve_checkpoint_tree(path, *args, **kwargs):
            if Path(path) == work_dir:
                return None
            return original_rmtree(path, *args, **kwargs)

        adapter.shutil.rmtree = preserve_checkpoint_tree
        try:
            result = original_generate(
                scene_spec,
                logical_seed,
                spec_file,
                data_root,
                gpu,
                timeout_s,
                force,
            )
            result = recover_committed_final_scene(run_dir, result)
            return record_generation_terminal(run_dir, result)
        finally:
            adapter.shutil.rmtree = original_rmtree

    adapter.generate = resumable_generate

    original_render = adapter.render

    def render_contract_error_terminal(log_text: str) -> bool:
        deterministic_contract_errors = (
            "SceneWeaver free-space path is too short:",
            "No free camera grid cell remains after collision clearance",
            "Degenerate camera direction at frame",
            "SceneWeaver layout has no two-dimensional roomsize",
            "Invalid SceneWeaver room size:",
        )
        return any(message in log_text for message in deterministic_contract_errors)

    def render_validation_terminal(run_dir: Path) -> bool:
        manifest_path = run_dir / "run_manifest.json"
        validation_path = run_dir / "renders/validation.json"
        if not manifest_path.is_file():
            return False
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        render_attempts = [
            attempt
            for attempt in manifest.get("attempts", [])
            if attempt.get("phase") == "render"
        ]
        if not render_attempts:
            return False
        latest = render_attempts[-1]
        if (
            latest.get("success") is False
            and not latest.get("timed_out")
            and isinstance(latest.get("log"), str)
        ):
            log_path = run_dir / latest["log"]
            if log_path.is_file() and render_contract_error_terminal(
                log_path.read_text(encoding="utf-8", errors="replace")
            ):
                return True
        if not validation_path.is_file():
            return False
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
        return (
            latest.get("success") is False
            and latest.get("exit_code") == 0
            and not latest.get("timed_out")
            and not latest.get("traceback_in_logs")
            and validation.get("valid") is False
        )

    def record_render_terminal(run_dir: Path, success: bool) -> bool:
        marker = run_dir / "RENDER_VALIDATION_FAILED"
        if success:
            marker.unlink(missing_ok=True)
            return success
        if not (marker.is_file() or render_validation_terminal(run_dir)):
            return success
        manifest_path = run_dir / "run_manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest["failure_reason"] = "render_validation_failed_terminal"
        adapter.atomic_json(manifest_path, manifest)
        marker.touch()
        print(
            "SCENEWEAVER_TERMINAL "
            + json.dumps(
                {
                    "reason": "render_validation_failed_terminal",
                    "run_dir": str(run_dir),
                },
                sort_keys=True,
            ),
            flush=True,
        )
        return False

    def resumable_render(
        scene_spec,
        logical_seed,
        spec_file,
        data_root,
        gpu,
        timeout_s,
        force,
    ):
        run_dir = (
            Path(data_root)
            / "indoor/sceneweaver"
            / scene_spec["spec_id"]
            / f"seed_{logical_seed}"
        )
        if not force and (run_dir / "SUCCESS").is_file():
            # ``initialize_run`` refreshes hashes while retaining status.  If
            # an older compatibility path reset only the status fields after
            # rendering, rebuild those fields from the immutable success
            # marker plus the already-written validation contract.  No scene
            # or image is regenerated here.
            validation_path = run_dir / "renders/validation.json"
            if validation_path.is_file():
                validation = json.loads(validation_path.read_text(encoding="utf-8"))
                if validation.get("valid") is True:
                    _, manifest = adapter.initialize_run(
                        scene_spec, logical_seed, spec_file, data_root
                    )
                    manifest["generation_success"] = True
                    manifest["render_success"] = True
                    manifest["failure_reason"] = None
                    adapter.atomic_json(run_dir / "run_manifest.json", manifest)
                    print(
                        "SCENEWEAVER_SUCCESS_MANIFEST_REFRESH "
                        + json.dumps({"run_dir": str(run_dir)}, sort_keys=True),
                        flush=True,
                    )
                    return True
        if not force and (
            (run_dir / "RENDER_VALIDATION_FAILED").is_file()
            or render_validation_terminal(run_dir)
        ):
            adapter.initialize_run(scene_spec, logical_seed, spec_file, data_root)
            return record_render_terminal(run_dir, False)
        result = original_render(
            scene_spec,
            logical_seed,
            spec_file,
            data_root,
            gpu,
            timeout_s,
            force,
        )
        return record_render_terminal(run_dir, result)

    adapter.render = resumable_render

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--spec-file", type=Path, default=adapter.DEFAULT_SPEC_FILE)
    parser.add_argument("--spec-id", required=True)
    parser.add_argument("--seed", type=int, required=True, dest="logical_seed")
    parser.add_argument("--data-root", type=Path, default=adapter.DEFAULT_DATA_ROOT)
    parser.add_argument("--phase", choices=("generate", "render", "all"), default="all")
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--generation-timeout-s", type=int, default=21600)
    parser.add_argument("--render-timeout-s", type=int, default=10800)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    def stable_path(path: Path) -> Path:
        text = str(path.expanduser())
        alias = _wb_expand_paths("${WORLDBRIDGE_ROOT}")
        if text.startswith(alias):
            text = str(REPO_ROOT) + text[len(alias) :]
        path = Path(text)
        return path if path.is_absolute() else REPO_ROOT / path

    args.spec_file = stable_path(args.spec_file)
    args.data_root = stable_path(args.data_root)
    adapter.assert_below_baselines(args.data_root)
    run_dir = (
        args.data_root
        / "indoor/sceneweaver"
        / args.spec_id
        / f"seed_{args.logical_seed}"
    )
    run_dir.mkdir(parents=True, exist_ok=True)
    lock_path = run_dir / ".sceneweaver_run.lock"
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        terminal_markers = [
            marker
            for marker in (
                "SUCCESS",
                "PLANNER_BUDGET_EXHAUSTED",
                "RENDER_VALIDATION_FAILED",
            )
            if (run_dir / marker).is_file()
        ]
        if terminal_markers and not args.force:
            print(
                "SCENEWEAVER_LOCKED_TERMINAL_SKIP "
                + json.dumps(
                    {
                        "marker": terminal_markers[0],
                        "run_dir": str(run_dir),
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
            return 0

        adapter.verify_prerequisites()
        specs = adapter.load_specs(args.spec_file)
        if args.spec_id not in specs:
            raise KeyError(f"Unknown spec_id={args.spec_id!r}")
        scene_spec = specs[args.spec_id]
        ok = True
        if args.phase in ("generate", "all"):
            ok = adapter.generate(
                scene_spec,
                args.logical_seed,
                args.spec_file,
                args.data_root,
                args.gpu,
                args.generation_timeout_s,
                args.force,
            )
        if ok and args.phase in ("render", "all"):
            ok = adapter.render(
                scene_spec,
                args.logical_seed,
                args.spec_file,
                args.data_root,
                args.gpu,
                args.render_timeout_s,
                args.force,
            )
        return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Resumable Table-4 evaluation for the requested Extra High system row.

Per the experiment request, this row reuses the completed GPT-6 Astra Low
Table-2 scenes. The source reasoning effort is recorded as ``low`` in every
protocol, manifest and lock; the user-facing row label remains the requested
``GPT-6 Astra Extra High + fixed IO adapter``. No GPT scene generation occurs.

The validated shared fixed-adapter geometry, Recast, AQS, aggregation and audit
implementation is reused in-process. This wrapper isolates all paths, blind
IDs and locks and validates the Low source identity before accepting evidence.
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


import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.gpt.unified.high import gpt_io_adapter as common


BASELINES = REPO / "baselines"
PROTOCOL_DIR = BASELINES / "methods/gpt/protocol/unified/low"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
BASE_PROTOCOL_PATH = BASELINES / "methods/gpt/protocol/unified/high/protocol.yaml"
PROMPT_PATH = BASELINES / "methods/gpt/protocol/unified/high/aqs_prompt.txt"
SOURCE_METHOD_LOCK = (
    BASELINES / "methods/gpt/protocol/generation/gpt6_astra_low.lock.json"
)
SOURCE_FORMAL_AUDIT = BASELINES / "results/gpt6_astra_low/formal_audit.json"
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_gpt6_astra_io_adapter/model_weight_audit.json"
)
SHARED_RUNNER = BASELINES / "methods/gpt/unified/high/gpt_io_adapter.py"
GEOMETRY_RUNNER = (
    BASELINES / "methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py"
)
BLIND_SALT = "worldbridge-table4-gpt6-astra-xhigh-label-low-source-fixed-io-adapter-v1"
ORIGINAL_SOURCE_SIDE_RECORD = common.source_side_record
ORIGINAL_BUILD_ONE = common.build_one
ORIGINAL_FREEZE = common.freeze


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_protocol() -> dict[str, Any]:
    base = json.loads(BASE_PROTOCOL_PATH.read_text(encoding="utf-8"))
    override = json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))
    return deep_merge(base, override)


def source_pair(spec: dict[str, Any], seed: int) -> dict[str, Any]:
    protocol = load_protocol()
    source = protocol["source"]
    ordinal = int(spec["spec_index"]) % 5
    function = spec["function"]
    urban = common.category_variant(
        common.jsonl(common.URBAN_SPECS),
        source["urban_category_by_function"][function],
        ordinal,
    )
    indoor = common.category_variant(
        common.jsonl(common.INDOOR_SPECS),
        source["indoor_category_by_function"][function],
        ordinal,
    )
    root = REPO / source["data_root"]
    method_dir = source["method_dir"]
    return {
        "exterior": {
            "spec": urban,
            "run": root / "urban" / method_dir / urban["spec_id"] / f"seed_{seed}",
        },
        "interior": {
            "spec": indoor,
            "run": root / "indoor" / method_dir / indoor["spec_id"] / f"seed_{seed}",
        },
    }


def source_side_record(side: str, entry: dict[str, Any]) -> dict[str, Any]:
    record = ORIGINAL_SOURCE_SIDE_RECORD(side, entry)
    record["source_model"] = "gpt-6-astra"
    record["source_reasoning_effort"] = "low"
    record["scene_regenerated"] = False
    manifest_path = entry["run"] / "run_manifest.json"
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if manifest.get("method") != "gpt6_astra_low":
            raise RuntimeError(f"Foreign Table-2 source method: {manifest_path}")
        if manifest.get("reasoning_effort_requested") not in (None, "low"):
            raise RuntimeError(
                f"Foreign Table-2 source reasoning effort: {manifest_path}"
            )
        source_lock = json.loads(SOURCE_METHOD_LOCK.read_text(encoding="utf-8"))
        expected_protocol = source_lock["files_sha256"][
            "methods/gpt/protocol/generation/gpt6_astra_low.json"
        ]
        if manifest.get("identity", {}).get("protocol_sha256") != expected_protocol:
            raise RuntimeError(f"Stale Table-2 Low protocol identity: {manifest_path}")
        if record["success"] and not (
            manifest.get("generation_success") and manifest.get("render_success")
        ):
            raise RuntimeError(
                f"SUCCESS disagrees with frozen Low generation/render state: {manifest_path}"
            )
    return record


def build_one(spec: dict[str, Any], seed: int, trial: str, output: Path) -> bool:
    """Invalidate a corrupted cached package before the shared resume check.

    The shared implementation checks file presence but does not compare saved
    hashes in its fast-path. This method-specific guard enforces the user's
    'existing and verified' requirement without editing other baseline runners.
    """
    manifest_path = output / "manifest.json"
    marker = output / "SUCCESS"
    if marker.is_file():
        if not manifest_path.is_file():
            marker.unlink()
        else:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if not manifest.get("outputs_sha256") or common.verify_output_hashes(
                manifest
            ):
                marker.unlink()
    return ORIGINAL_BUILD_ONE(spec, seed, trial, output)


def source_audit() -> dict[str, Any]:
    """Read-only audit of all planned pair sources and their frozen identity."""
    source_lock = json.loads(SOURCE_METHOD_LOCK.read_text(encoding="utf-8"))
    if (source_lock.get("method"), source_lock.get("reasoning_effort")) != (
        "gpt6_astra_low",
        "low",
    ):
        raise RuntimeError("The source method lock is not GPT-6 Astra Low")
    formal = json.loads(SOURCE_FORMAL_AUDIT.read_text(encoding="utf-8"))
    if (formal.get("expected"), formal.get("counts")) != (
        200,
        {"valid": 195, "quality": 5},
    ):
        raise RuntimeError("The completed Low Table-2 audit has changed")
    specs, seeds = common.trial_specs_and_seeds("formal")
    success = 0
    failed = []
    for spec in specs:
        for seed in seeds:
            pair = source_pair(spec, seed)
            refs = {
                side: source_side_record(side, entry) for side, entry in pair.items()
            }
            complete = all(ref["success"] for ref in refs.values())
            success += int(complete)
            if not complete:
                failed.append(
                    {
                        "spec_id": spec["spec_id"],
                        "seed": seed,
                        "source_specs": {
                            side: ref["spec_id"] for side, ref in refs.items()
                        },
                    }
                )
    result = {
        "source_method": "gpt6_astra_low",
        "source_reasoning_effort": "low",
        "planned_pairs": len(specs) * len(seeds),
        "source_successful_pairs": success,
        "source_failed_pairs": failed,
        "source_formal_audit_sha256": common.sha256_file(SOURCE_FORMAL_AUDIT),
        "scene_regenerated": False,
    }
    print(
        f"GPT6_ASTRA_TABLE4_LOW_SOURCE_AUDIT {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def choose_idle_gpu() -> int:
    """Use a genuinely idle physical GPU, never select by memory alone."""
    for attempt in range(3):
        try:
            states = common.gpu_state()
            break
        except subprocess.CalledProcessError as error:
            if attempt == 2:
                raise RuntimeError(
                    "Unable to inspect physical GPU utilization; refusing to launch VLM"
                ) from error
            time.sleep(1)
    eligible = [
        (state["free_mib"], -gpu)
        for gpu, state in states.items()
        if state["free_mib"] >= 32000 and state["utilization"] <= 10
    ]
    if not eligible:
        raise RuntimeError(f"No compute-idle GPU with >=32000 MiB free: {states}")
    _, neg_selected = max(eligible)
    selected = -neg_selected
    print(
        f"GPT6_ASTRA_TABLE4_IDLE_GPU_SELECTED gpu={selected} states={states}",
        flush=True,
    )
    return selected


def start_and_score(
    trial: str, gpu: int, port: int, workers: int, external: bool
) -> dict[str, Any]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    protocol = load_protocol()
    matrix.RUNTIME_ROOT = REPO / protocol["aqs"]["runtime_root"]
    matrix.BASELINES_ROOT = REPO / protocol["aqs"]["short_socket_root"]
    matrix.QWEN_ROOT = Path(protocol["aqs"]["model_root"])
    matrix.VLLM_PYTHON = Path(protocol["aqs"]["vllm_python"])
    if not matrix.VLLM_PYTHON.is_file():
        raise RuntimeError(
            f"Missing registered local vLLM Python: {matrix.VLLM_PYTHON}"
        )
    process = None
    try:
        if external:
            if not matrix.llm_health(port):
                raise RuntimeError(f"No healthy local VLM at port {port}")
        else:
            state = common.gpu_state().get(gpu)
            minimum = int(protocol["aqs"]["minimum_free_mib"])
            max_utilization = int(
                protocol["aqs"]["maximum_existing_utilization_percent"]
            )
            if (
                state is None
                or state["free_mib"] < minimum
                or state["utilization"] > max_utilization
            ):
                raise RuntimeError(
                    f"GPU {gpu} lacks the registered sharing headroom: {state}"
                )
            if not matrix.port_is_free(port):
                raise RuntimeError(f"LLM port {port} is already occupied")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            log_path = (
                matrix.RUNTIME_ROOT
                / "logs"
                / f"vllm_uid_{os.getuid()}"
                / f"qwen_gpu{gpu}_{stamp}.log"
            )
            log_path.parent.mkdir(parents=True, exist_ok=True)
            command = [
                str(matrix.VLLM_PYTHON),
                "-m",
                "vllm.entrypoints.cli.main",
                "serve",
                str(matrix.QWEN_ROOT),
                "--served-model-name",
                protocol["aqs"]["model"],
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--tensor-parallel-size",
                "1",
                "--pipeline-parallel-size",
                "1",
                "--max-model-len",
                str(protocol["aqs"]["vllm_max_model_len"]),
                "--gpu-memory-utilization",
                str(protocol["aqs"]["vllm_gpu_memory_utilization"]),
                "--cpu-offload-gb",
                str(protocol["aqs"]["vllm_cpu_offload_gb"]),
                "--enforce-eager",
                "--trust-remote-code",
            ]
            with log_path.open("a", encoding="utf-8") as log:
                log.write(f"\n[{common.utc_now()}] COMMAND {json.dumps(command)}\n")
                log.flush()
                process = subprocess.Popen(
                    command,
                    cwd=REPO,
                    env=matrix.vllm_environment(gpu),
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    text=True,
                )
            deadline = time.monotonic() + int(protocol["aqs"]["vllm_startup_timeout_s"])
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"vLLM exited with code {process.returncode}; see {log_path}"
                    )
                if matrix.llm_health(port):
                    print(
                        f"GPT6_ASTRA_TABLE4_VLLM_READY gpu={gpu} port={port} log={log_path}",
                        flush=True,
                    )
                    break
                time.sleep(2)
            else:
                matrix.stop_process_group(process)
                process = None
                raise RuntimeError(f"vLLM did not become healthy; see {log_path}")
        return common.score_package(trial, port, workers)
    finally:
        if process is not None:
            matrix.stop_process_group(process)


def freeze() -> dict[str, Any]:
    result = ORIGINAL_FREEZE()
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    for path in (
        SHARED_RUNNER,
        BASE_PROTOCOL_PATH,
        GEOMETRY_RUNNER,
        SOURCE_FORMAL_AUDIT,
    ):
        lock["files"][common.rel(path)] = common.sha256_file(path)
    lock.update(
        {
            "source_model": "gpt-6-astra",
            "source_reasoning_effort": "low",
            "requested_display_label": "GPT-6 Astra Extra High + fixed IO adapter",
            "source_identity_disclosure": (
                "The requested Extra High display row reuses GPT-6 Astra Low Table-2 scenes; "
                "no xhigh scene generation was run."
            ),
            "source_table2_method_lock_sha256": common.sha256_file(SOURCE_METHOD_LOCK),
            "source_table2_formal_audit_sha256": common.sha256_file(
                SOURCE_FORMAL_AUDIT
            ),
            "shared_fixed_adapter_implementation": common.rel(SHARED_RUNNER),
            "gpu_scheduling": load_protocol()["aqs"]["gpu_scheduling_note"],
            "vllm_python": load_protocol()["aqs"]["vllm_python"],
        }
    )
    common.atomic_json(LOCK_PATH, lock)
    common.verify_lock()
    return result


def configure_common() -> None:
    common.PROTOCOL_DIR = PROTOCOL_DIR
    common.PROTOCOL_PATH = PROTOCOL_PATH
    common.PROMPT_PATH = PROMPT_PATH
    common.LOCK_PATH = LOCK_PATH
    common.SOURCE_METHOD_LOCK = SOURCE_METHOD_LOCK
    common.MODEL_WEIGHT_AUDIT = MODEL_WEIGHT_AUDIT
    common.BLIND_SALT = BLIND_SALT
    common.__file__ = str(Path(__file__).resolve())
    common.load_protocol = load_protocol
    common.source_pair = source_pair
    common.source_side_record = source_side_record
    common.build_one = build_one
    common.start_and_score = start_and_score
    common.freeze = freeze


def main() -> int:
    configure_common()
    if len(sys.argv) == 2 and sys.argv[1] == "source-audit":
        source_audit()
        return 0
    if len(sys.argv) > 2 and sys.argv[1] == "score" and "--gpu" in sys.argv:
        gpu_position = sys.argv.index("--gpu") + 1
        if gpu_position < len(sys.argv) and sys.argv[gpu_position] == "auto":
            sys.argv[gpu_position] = str(choose_idle_gpu())
    return common.main()


if __name__ == "__main__":
    raise SystemExit(main())

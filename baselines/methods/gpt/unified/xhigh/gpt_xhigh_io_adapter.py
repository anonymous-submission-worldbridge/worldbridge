#!/usr/bin/env python3
"""Resumable Table-4 evaluation for GPT-6 Astra Extra High + fixed IO adapter.

The completed Extra High Table-2 scene directories were moved to an ephemeral
``/tmp`` tree by an earlier run and that tree is no longer present. This runner
therefore consumes only the immutable 8-view montages and videos retained by
the completed Table-2 experiment under ``baselines/annotations``. It never
regenerates a scene and never represents another reasoning effort as xhigh.

The validated fixed-adapter geometry, Recast, AQS, aggregation and audit code is
reused in-process. This wrapper isolates Extra High evidence, paths, IDs and lock.
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

from PIL import Image, ImageDraw


REPO = _BASELINE_PROJECT_ROOT
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from baselines.methods.gpt.unified.high import gpt_io_adapter as common


BASELINES = REPO / "baselines"
PROTOCOL_DIR = BASELINES / "methods/gpt/protocol/unified/xhigh"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
LOCK_PATH = (
    BASELINES
    / "methods/gpt/protocol/unified/xhigh/unified_gpt6_astra_extra_high_io_adapter.lock.json"
)
BASE_PROTOCOL_PATH = BASELINES / "methods/gpt/protocol/unified/high/protocol.yaml"
PROMPT_PATH = BASELINES / "methods/gpt/protocol/unified/high/aqs_prompt.txt"
SOURCE_METHOD_LOCK = (
    BASELINES / "methods/gpt/protocol/generation/gpt6_astra_xhigh.lock.json"
)
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_gpt6_astra_io_adapter/model_weight_audit.json"
)
SHARED_RUNNER = BASELINES / "methods/gpt/unified/high/gpt_io_adapter.py"
GEOMETRY_RUNNER = (
    BASELINES / "methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py"
)
ARCHIVE_ROOT = BASELINES / "annotations/gpt6_astra_xhigh"
EVIDENCE_INVENTORY = (
    BASELINES
    / "results/table4_gpt6_astra_extra_high_io_adapter/source_evidence_inventory.json"
)
FORMAL_AUDIT = BASELINES / "results/gpt6_astra_xhigh/formal_audit.json"
CHAIN_AUDITS = {
    domain: BASELINES / f"results/gpt6_astra_xhigh/chain_audit_{domain}.json"
    for domain in ("indoor", "urban")
}
PRIVATE_MAPS = {
    domain: ARCHIVE_ROOT / domain / "PRIVATE_blind_map.json"
    for domain in ("indoor", "urban")
}
ITEM_FILES = {
    domain: ARCHIVE_ROOT / domain / "items.csv" for domain in ("indoor", "urban")
}
BLIND_SALT = "worldbridge-table4-gpt6-astra-extra-high-fixed-io-adapter-v1"
TABLE2_TILE_SIZE = (480, 270)
TABLE2_HEADER_HEIGHT = 44


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


def compute_evidence_inventory() -> dict[str, Any]:
    formal = json.loads(FORMAL_AUDIT.read_text(encoding="utf-8"))
    if (
        formal.get("method") != "gpt6_astra_xhigh"
        or formal.get("reasoning_effort") != "xhigh"
    ):
        raise RuntimeError("The retained formal audit is not GPT-6 Astra Extra High")
    expected_counts = {
        "indoor": {"valid": 87, "quality": 13},
        "urban": {"valid": 82, "quality": 18},
    }
    records: list[dict[str, Any]] = []
    domain_counts: dict[str, dict[str, int]] = {}
    for domain in ("indoor", "urban"):
        private_payload = json.loads(PRIVATE_MAPS[domain].read_text(encoding="utf-8"))
        items = private_payload.get("items", [])
        if len(items) != 100:
            raise RuntimeError(
                f"Expected 100 retained Table-2 map rows for {domain}, found {len(items)}"
            )
        valid = 0
        for item in sorted(
            items, key=lambda row: (row["spec_id"], int(row["logical_seed"]))
        ):
            record: dict[str, Any] = {
                "domain": domain,
                "spec_id": item["spec_id"],
                "logical_seed": int(item["logical_seed"]),
                "blind_id": item["blind_id"],
                "success": bool(item["success"]),
                "logical_run_dir": (
                    f"baselines/data/table2/{domain}/gpt6_astra_xhigh/"
                    f"{item['spec_id']}/seed_{int(item['logical_seed'])}"
                ),
            }
            if record["success"]:
                valid += 1
                montage = ARCHIVE_ROOT / domain / "montages" / f"{item['blind_id']}.jpg"
                video = ARCHIVE_ROOT / domain / "videos" / f"{item['blind_id']}.mp4"
                if not montage.is_file() or not video.is_file():
                    raise RuntimeError(
                        f"Retained Table-2 visual evidence is incomplete: {item['blind_id']}"
                    )
                with Image.open(montage) as image:
                    if image.size != (1920, 584):
                        raise RuntimeError(
                            f"Unexpected retained montage size {image.size}: {montage}"
                        )
                record["montage"] = {
                    "path": common.rel(montage),
                    "sha256": common.sha256_file(montage),
                    "bytes": montage.stat().st_size,
                }
                record["video"] = {
                    "path": common.rel(video),
                    "sha256": common.sha256_file(video),
                    "bytes": video.stat().st_size,
                }
            records.append(record)
        quality = len(items) - valid
        domain_counts[domain] = {
            "planned": len(items),
            "valid": valid,
            "quality": quality,
        }
        if domain_counts[domain] != {"planned": 100, **expected_counts[domain]}:
            raise RuntimeError(
                f"Retained evidence counts disagree with frozen audit for {domain}: {domain_counts[domain]}"
            )
    if formal.get("counts") != {"valid": 169, "quality": 31}:
        raise RuntimeError(f"Unexpected frozen formal counts: {formal.get('counts')}")
    return {
        "schema_version": "gpt6-astra-xhigh-table2-retained-visual-evidence-v1",
        "method": "gpt6_astra_xhigh",
        "model": "gpt-6-astra",
        "reasoning_effort": "xhigh",
        "scene_regenerated": False,
        "original_scene_directory_status": "unavailable_after_ephemeral_tmp_cleanup",
        "retained_evidence": "completed Table-2 anonymous 8-view montage and 50-frame video",
        "formal_audit": {
            "path": common.rel(FORMAL_AUDIT),
            "sha256": common.sha256_file(FORMAL_AUDIT),
        },
        "chain_audits": {
            domain: {"path": common.rel(path), "sha256": common.sha256_file(path)}
            for domain, path in CHAIN_AUDITS.items()
        },
        "private_maps": {
            domain: {"path": common.rel(path), "sha256": common.sha256_file(path)}
            for domain, path in PRIVATE_MAPS.items()
        },
        "domain_counts": domain_counts,
        "records": records,
    }


def inventory_source_evidence() -> dict[str, Any]:
    payload = compute_evidence_inventory()
    if EVIDENCE_INVENTORY.is_file():
        existing = json.loads(EVIDENCE_INVENTORY.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError(
                "Retained xhigh evidence changed since its inventory was written"
            )
        print(
            f"GPT6_ASTRA_EXTRA_HIGH_EVIDENCE_INVENTORY_REUSED {common.rel(EVIDENCE_INVENTORY)}"
        )
        return existing
    common.atomic_json(EVIDENCE_INVENTORY, payload)
    print(
        f"GPT6_ASTRA_EXTRA_HIGH_EVIDENCE_INVENTORY_COMPLETE {common.rel(EVIDENCE_INVENTORY)}"
    )
    return payload


def inventory_index() -> dict[tuple[str, str, int], dict[str, Any]]:
    if not EVIDENCE_INVENTORY.is_file():
        raise RuntimeError(
            "Run the Extra High adapter 'inventory' command before build"
        )
    inventory = json.loads(EVIDENCE_INVENTORY.read_text(encoding="utf-8"))
    return {
        (row["domain"], row["spec_id"], int(row["logical_seed"])): row
        for row in inventory["records"]
    }


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

    def entry(domain: str, native_spec: dict[str, Any]) -> dict[str, Any]:
        logical = (
            f"baselines/data/table2/{domain}/{source['method_dir']}/"
            f"{native_spec['spec_id']}/seed_{seed}"
        )
        return {
            "domain": domain,
            "spec": native_spec,
            "run": REPO / logical,
            "logical_run": logical,
            "logical_seed": seed,
        }

    return {"exterior": entry("urban", urban), "interior": entry("indoor", indoor)}


def source_side_record(side: str, entry: dict[str, Any]) -> dict[str, Any]:
    key = (entry["domain"], entry["spec"]["spec_id"], int(entry["logical_seed"]))
    item = inventory_index().get(key)
    if item is None:
        raise RuntimeError(f"Frozen xhigh evidence inventory has no row for {key}")
    record: dict[str, Any] = {
        "side": side,
        "domain": entry["domain"],
        "spec_id": entry["spec"]["spec_id"],
        "logical_seed": int(entry["logical_seed"]),
        "run": entry["logical_run"],
        "success": bool(item["success"]),
        "missing_required": [],
        "source_model": "gpt-6-astra",
        "source_reasoning_effort": "xhigh",
        "scene_regenerated": False,
        "source_geometry_available": False,
        "evidence_recovery_mode": "retained_table2_montage_and_video",
        "evidence_inventory_sha256": common.sha256_file(EVIDENCE_INVENTORY),
    }
    if not record["success"]:
        return record
    for label in ("montage", "video"):
        evidence = item[label]
        path = REPO / evidence["path"]
        if not path.is_file() or common.sha256_file(path) != evidence["sha256"]:
            raise RuntimeError(f"Changed retained xhigh {label} evidence: {path}")
        record[f"archived_{label}"] = {**evidence, "immutable": True}
    return record


def archived_anchor(
    record: dict[str, Any], index: int, size: tuple[int, int]
) -> Image.Image:
    path = REPO / record["archived_montage"]["path"]
    with Image.open(path) as source:
        if source.size != (1920, 584):
            raise RuntimeError(f"Changed retained montage dimensions: {path}")
        column, row = index % 4, index // 4
        left = column * TABLE2_TILE_SIZE[0]
        top = TABLE2_HEADER_HEIGHT + row * TABLE2_TILE_SIZE[1]
        tile = source.crop(
            (left, top, left + TABLE2_TILE_SIZE[0], top + TABLE2_TILE_SIZE[1])
        ).convert("RGB")
        tile.thumbnail(size, Image.Resampling.LANCZOS)
    result = Image.new("RGB", size, (25, 25, 25))
    result.paste(tile, ((size[0] - tile.width) // 2, (size[1] - tile.height) // 2))
    return result


def make_montage(
    source_refs: dict[str, Any],
    overlay: Path,
    output: Path,
    anonymous: str,
    protocol: dict[str, Any],
) -> str:
    selected = protocol["source"]["selected_anchor_indices"]
    tile_size = (480, 250)
    margin, gap, header, label = 55, 10, 50, 30
    view_width = 4 * tile_size[0] + 3 * gap + 2 * margin
    view_height = header + 2 * (label + tile_size[1]) + gap
    views = Image.new("RGB", (view_width, view_height), "white")
    draw = ImageDraw.Draw(views)
    draw.text(
        (margin, 12), f"Anonymous pair {anonymous}", fill="black", font=common.font(22)
    )
    for row, side in enumerate(("exterior", "interior")):
        y = header + row * (label + tile_size[1] + gap)
        draw.rectangle((0, y, view_width, y + label), fill=(235, 235, 235))
        draw.text((margin, y + 4), side.upper(), fill="black", font=common.font(18))
        for column, anchor_index in enumerate(selected[side]):
            tile = archived_anchor(source_refs[side], int(anchor_index), tile_size)
            x = margin + column * (tile_size[0] + gap)
            views.paste(tile, (x, y + label))
            draw.rectangle((x + 5, y + label + 5, x + 48, y + label + 35), fill="black")
            draw.text(
                (x + 13, y + label + 7),
                str(anchor_index),
                fill="white",
                font=common.font(16),
            )
    with Image.open(overlay) as overlay_handle:
        lower = overlay_handle.convert("RGB")
        if lower.width != view_width:
            lower = lower.resize(
                (view_width, round(lower.height * view_width / lower.width)),
                Image.Resampling.LANCZOS,
            )
    combined = Image.new("RGB", (view_width, view_height + lower.height), "white")
    combined.paste(views, (0, 0))
    combined.paste(lower, (0, view_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jpg.tmp")
    combined.save(temporary, format="JPEG", quality=92, subsampling=0)
    temporary.replace(output)
    return common.sha256_file(output)


def start_and_score(
    trial: str, gpu: int, port: int, workers: int, external: bool
) -> dict[str, Any]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    protocol = load_protocol()
    matrix.RUNTIME_ROOT = REPO / protocol["aqs"]["runtime_root"]
    matrix.BASELINES_ROOT = REPO / protocol["aqs"]["short_socket_root"]
    matrix.QWEN_ROOT = Path(protocol["aqs"]["model_root"])
    process = None
    try:
        if external:
            if not matrix.llm_health(port):
                raise RuntimeError(f"No healthy local VLM at port {port}")
        else:
            gpus = [int(value) for value in protocol["aqs"]["physical_gpus"]]
            states = common.gpu_state()
            minimum = int(protocol["aqs"]["minimum_free_mib"])
            invalid = {
                index: states.get(index)
                for index in gpus
                if states.get(index) is None or states[index]["free_mib"] < minimum
            }
            if invalid:
                raise RuntimeError(
                    f"Configured shared GPUs lack the frozen memory budget: {invalid}"
                )
            if workers != int(protocol["aqs"]["request_workers"]):
                raise RuntimeError(
                    f"Frozen request worker count is {protocol['aqs']['request_workers']}, got {workers}"
                )
            process, _ = start_shared_gpu_vllm(
                matrix=matrix,
                gpus=gpus,
                port=port,
                max_model_len=int(protocol["aqs"]["vllm_max_model_len"]),
                timeout_s=int(protocol["aqs"]["vllm_startup_timeout_s"]),
                gpu_memory_utilization=float(
                    protocol["aqs"]["vllm_gpu_memory_utilization"]
                ),
            )
        return common.score_package(trial, port, workers)
    finally:
        if process is not None:
            matrix.stop_process_group(process)


def start_shared_gpu_vllm(
    matrix: Any,
    gpus: list[int],
    port: int,
    max_model_len: int,
    timeout_s: int,
    gpu_memory_utilization: float,
) -> tuple[subprocess.Popen[str], Path]:
    """Start the frozen Qwen evaluator within the current shared-GPU budget."""
    if not matrix.VLLM_PYTHON.is_file() or not matrix.VLLM_PACKAGE.is_file():
        raise RuntimeError(
            f"Incomplete isolated vLLM environment: {matrix.VLLM_PYTHON.parent.parent}"
        )
    if not (matrix.QWEN_ROOT / "config.json").is_file():
        raise RuntimeError(f"Missing local Qwen checkpoint: {matrix.QWEN_ROOT}")
    if not matrix.port_is_free(port):
        raise RuntimeError(f"LLM port {port} is already occupied")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_path = (
        matrix.RUNTIME_ROOT
        / "logs"
        / f"vllm_uid_{os.getuid()}"
        / f"qwen_gpu{'-'.join(map(str, gpus))}_util{gpu_memory_utilization:.2f}_{stamp}.log"
    )
    log_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(matrix.VLLM_PYTHON),
        "-m",
        "vllm.entrypoints.cli.main",
        "serve",
        str(matrix.QWEN_ROOT),
        "--served-model-name",
        "Qwen/Qwen3-VL-8B-Instruct",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--tensor-parallel-size",
        str(len(gpus)),
        "--pipeline-parallel-size",
        "1",
        "--max-model-len",
        str(max_model_len),
        "--gpu-memory-utilization",
        str(gpu_memory_utilization),
        "--trust-remote-code",
    ]
    with log_path.open("a", encoding="utf-8") as log:
        log.write(f"\n[{common.utc_now()}] COMMAND {json.dumps(command)}\n")
        log.flush()
        environment = matrix.vllm_environment(gpus[0])
        environment["CUDA_VISIBLE_DEVICES"] = ",".join(str(index) for index in gpus)
        process = subprocess.Popen(
            command,
            cwd=matrix.REPO_ROOT,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            text=True,
        )
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        exit_code = process.poll()
        if exit_code is not None:
            raise RuntimeError(f"vLLM exited with code {exit_code}; see {log_path}")
        if matrix.llm_health(port):
            print(
                f"GPT6_ASTRA_EXTRA_HIGH_VLLM_READY gpus={gpus} port={port} "
                f"memory_utilization={gpu_memory_utilization} log={log_path}",
                flush=True,
            )
            return process, log_path
        time.sleep(2)
    matrix.stop_process_group(process)
    raise TimeoutError(f"vLLM startup timed out; see {log_path}")


def freeze() -> dict[str, Any]:
    inventory_source_evidence()
    _, _, pilot_results = common.trial_paths("pilot")
    audit_result = json.loads(
        (pilot_results / "audit.json").read_text(encoding="utf-8")
    )
    summary = json.loads((pilot_results / "summary.json").read_text(encoding="utf-8"))
    if not audit_result.get("passed") or summary.get("planned_pairs") != 10:
        raise RuntimeError(
            "A passing 10-pair Extra High pilot is required before formal freeze"
        )
    protocol = load_protocol()
    files = [
        Path(__file__),
        PROTOCOL_PATH,
        PROMPT_PATH,
        common.TABLE4_SPECS,
        common.INDOOR_SPECS,
        common.URBAN_SPECS,
        SOURCE_METHOD_LOCK,
        common.NAVMESH_EVALUATOR,
        common.RECAST_BINARY,
        REPO / protocol["aqs"]["model_manifest"],
        SHARED_RUNNER,
        BASE_PROTOCOL_PATH,
        GEOMETRY_RUNNER,
        EVIDENCE_INVENTORY,
        FORMAL_AUDIT,
        *CHAIN_AUDITS.values(),
        *PRIVATE_MAPS.values(),
        *ITEM_FILES.values(),
    ]
    lock = {
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "frozen_at_utc": common.utc_now(),
        "pilot_summary_sha256": common.sha256_file(pilot_results / "summary.json"),
        "pilot_audit_sha256": common.sha256_file(pilot_results / "audit.json"),
        "files": {common.rel(path): common.sha256_file(path) for path in files},
        "source_scene_generation_reused": True,
        "no_scene_regeneration": True,
        "no_human_postprocessing": True,
        "source_model": "gpt-6-astra",
        "source_reasoning_effort": "xhigh",
        "source_table2_method_lock_sha256": common.sha256_file(SOURCE_METHOD_LOCK),
        "source_evidence_inventory_sha256": common.sha256_file(EVIDENCE_INVENTORY),
        "source_visual_evidence_mode": "retained_table2_montage_and_video",
        "source_original_scene_directories_available_at_freeze": False,
        "shared_fixed_adapter_implementation": common.rel(SHARED_RUNNER),
    }
    common.atomic_json(LOCK_PATH, lock)
    common.verify_lock()
    print(
        f"GPT6_ASTRA_EXTRA_HIGH_TABLE4_FREEZE_COMPLETE {json.dumps(lock, sort_keys=True)}",
        flush=True,
    )
    return lock


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
    common.make_montage = make_montage
    common.start_and_score = start_and_score
    common.freeze = freeze


def main() -> int:
    configure_common()
    if len(sys.argv) == 2 and sys.argv[1] == "inventory":
        inventory_source_evidence()
        return 0
    return common.main()


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Summarize final-run timing, cache, retry, RAM, and sampled GPU evidence."""

from __future__ import annotations

import csv
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CITY = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
PIPELINE_LOG = CITY / "pipeline.log"
RESOURCE_CSV = CITY / "resource_profile.csv"
OUTPUT = CITY / "resource_efficiency_audit.json"
STANDARD_LAYERS = (
    "river5_nature",
    "river3_residential",
    "artificial_lake",
    "all45_unique_buildings",
    "education_buildings",
    "commercial_services",
    "industrial",
    "public_safety",
    "residential_delivery",
    "all44_leisure",
    "park_leisure_support",
    "health",
    "full13_unique_urban_fabric",
    "full13_semantic_interiors",
    "full13_public_realm",
    "base",
)
DIRECT_LAYERS = (
    "direct_civic",
    "direct_commercial",
    "direct_residential",
    "direct_industrial_safety",
    "direct_park_lake",
    "direct_diagonal_street",
)


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def atomic_json(payload: dict) -> None:
    temporary = OUTPUT.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True),
        encoding="utf8",
    )
    os.replace(temporary, OUTPUT)


def main() -> None:
    layout = json.loads((CITY / "layout_plan.json").read_text(encoding="utf8"))
    run_id = layout["run_id"]
    direct_equivalence_path = CITY / "direct_zdepth_equivalence_audit.json"
    direct_equivalence = (
        json.loads(direct_equivalence_path.read_text(encoding="utf8"))
        if direct_equivalence_path.is_file()
        else {}
    )
    pipeline_unit = os.environ.get(
        "C2W_FULL13_PIPELINE_UNIT", "worldbridge-full13-pipeline.service"
    )
    text = PIPELINE_LOG.read_text(encoding="utf8", errors="replace")
    lines = text.splitlines()
    begin_match = re.search(
        r"FULL13_PIPELINE_BEGIN utc=(\S+) run_id=(\S+) unit=(\S+)", text
    )
    if not begin_match or begin_match.group(2) != run_id:
        raise RuntimeError("Missing current-run pipeline begin record")
    if begin_match.group(3) != pipeline_unit:
        raise RuntimeError("Pipeline unit does not match resource profiler contract")
    pipeline_started = timestamp(begin_match.group(1))

    stage_begins: dict[str, list[datetime]] = defaultdict(list)
    stage_records = []
    for line in lines:
        match = re.search(
            r"FULL13_STAGE_BEGIN utc=(\S+) run_id=(\S+) stage=(\S+)", line
        )
        if match and match.group(2) == run_id:
            stage_begins[match.group(3)].append(timestamp(match.group(1)))
        match = re.search(
            r"FULL13_STAGE_DONE utc=(\S+) run_id=(\S+) stage=(\S+) status=(\S+)", line
        )
        if match and match.group(2) == run_id:
            stage = match.group(3)
            end = timestamp(match.group(1))
            starts = stage_begins.get(stage, [])
            start = starts.pop(0) if starts else None
            stage_records.append(
                {
                    "stage": stage,
                    "started_utc": start.isoformat().replace("+00:00", "Z")
                    if start
                    else None,
                    "completed_utc": end.isoformat().replace("+00:00", "Z"),
                    "wall_seconds": (end - start).total_seconds() if start else None,
                    "status": match.group(4),
                }
            )
    cache_hits = re.findall(
        rf"FULL13_STAGE_CACHE_HIT run_id={re.escape(run_id)} stage=(\S+)", text
    )
    gpu_slots_match = re.search(
        r"FULL13_GPU_SELECTION .* gpu_slots=(.*?) backend=", text
    )
    if gpu_slots_match:
        selected_gpus = sorted(
            {int(slot.split(":", 1)[0]) for slot in gpu_slots_match.group(1).split()}
        )
    else:
        gpu_match = re.search(r"FULL13_GPU_SELECTION .* gpu_a=(\d+) gpu_b=(\d+)", text)
        selected_gpus = (
            sorted({int(value) for value in gpu_match.groups()}) if gpu_match else []
        )

    layer_records = {}
    rendered_frames = skipped_frames = retry_count = 0
    for layer in STANDARD_LAYERS:
        log_path = CITY / f"render_{layer}.log"
        log_text = (
            log_path.read_text(encoding="utf8", errors="replace")
            if log_path.is_file()
            else ""
        )
        rendered = len(
            re.findall(rf"FULL12_ZLAYER_DONE \d+/\d+ {re.escape(layer)}:", log_text)
        )
        skipped = len(
            re.findall(rf"FULL12_ZLAYER_SKIP \d+/\d+ {re.escape(layer)}:", log_text)
        )
        plans = re.findall(
            rf"FULL13_LAYER_FRAME_PLAN .* layer={re.escape(layer)} pending=(\d+)",
            log_text,
        )
        if plans:
            # Per-view Vulkan process isolation plans only missing frames, so
            # cache hits never enter Blender and therefore do not emit the
            # legacy FULL12_ZLAYER_SKIP marker.
            skipped += 80 - int(plans[-1])
        retries = len(re.findall(r"FULL13_(?:LAYER|FRAME)_RETRY", log_text))
        manifest_path = CITY / f"renders/zdepth_layers/layer_manifest_{layer}.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf8"))
            if manifest_path.is_file()
            else {}
        )
        view_seconds = sum(
            float(record.get("render_seconds", 0.0))
            for record in manifest.get("views", [])
        )
        layer_records[layer] = {
            "status": manifest.get("status"),
            "completed_count": manifest.get("completed_count", 0),
            "process_elapsed_seconds": manifest.get("elapsed_seconds"),
            "sum_recorded_frame_render_seconds": round(view_seconds, 3),
            "frames_rendered_this_final_run": rendered,
            "frames_reused_by_dependency_hash": skipped,
            "process_retries": retries,
            "vulkan_process_boundary": ("one_view" if plans else "legacy_whole_layer"),
            "render_dependency_hash": manifest.get("render_dependency_hash"),
        }
        rendered_frames += rendered
        skipped_frames += skipped
        retry_count += retries

    direct_records = {}
    direct_rendered = direct_skipped = 0
    direct_root = CITY / "renders/direct_validation_layers"
    for layer in DIRECT_LAYERS:
        log_path = CITY / f"render_{layer}.log"
        log_text = (
            log_path.read_text(encoding="utf8", errors="replace")
            if log_path.is_file()
            else ""
        )
        rendered = len(
            re.findall(rf"FULL12_ZLAYER_DONE \d+/\d+ {re.escape(layer)}:", log_text)
        )
        skipped = len(
            re.findall(rf"FULL12_ZLAYER_SKIP \d+/\d+ {re.escape(layer)}:", log_text)
        )
        manifest_path = direct_root / f"layer_manifest_{layer}.json"
        manifest = (
            json.loads(manifest_path.read_text(encoding="utf8"))
            if manifest_path.is_file()
            else {}
        )
        direct_records[layer] = {
            "manifest_status": manifest.get("status"),
            "completed_count": manifest.get("completed_count", 0),
            "frames_rendered_this_final_run": rendered,
            "frames_reused_by_dependency_hash": skipped,
            "render_dependency_hash": manifest.get("render_dependency_hash"),
        }
        direct_rendered += rendered
        direct_skipped += skipped

    samples = []
    final_unit_samples = []
    if RESOURCE_CSV.is_file():
        with RESOURCE_CSV.open(newline="", encoding="utf8") as handle:
            for row in csv.DictReader(handle):
                if row.get("run_id") == run_id:
                    samples.append(row)
                    if row.get("unit") == pipeline_unit:
                        final_unit_samples.append(row)
    memory_values = [
        int(row["service_memory_bytes"])
        for row in samples
        if row.get("service_memory_bytes", "").isdigit()
    ]
    cpu_by_unit: dict[str, list[int]] = defaultdict(list)
    for row in samples:
        if row.get("service_cpu_nsec", "").isdigit():
            cpu_by_unit[row["unit"]].append(int(row["service_cpu_nsec"]))
    gpu_rows: dict[int, list[dict]] = defaultdict(list)
    for row in samples:
        try:
            gpu_rows[int(row["gpu_index"])].append(row)
        except (KeyError, TypeError, ValueError):
            pass
    gpu_summary = {}
    for index, rows in sorted(gpu_rows.items()):
        utilization = [int(row["gpu_utilization_percent"]) for row in rows]
        memory = [int(row["gpu_memory_used_mib"]) for row in rows]
        gpu_summary[str(index)] = {
            "selected_for_render": index in selected_gpus,
            "sample_count": len(rows),
            "mean_server_utilization_percent": round(
                sum(utilization) / len(utilization), 3
            ),
            "peak_server_utilization_percent": max(utilization),
            "peak_server_memory_used_mib": max(memory),
            "memory_capacity_mib": int(rows[0]["gpu_memory_total_mib"]),
        }

    standard_complete = all(
        item["status"] == "PASS" and item["completed_count"] == 80
        for item in layer_records.values()
    )
    direct_complete = all(
        item["completed_count"] >= 1
        and item["frames_rendered_this_final_run"]
        + item["frames_reused_by_dependency_hash"]
        >= 1
        for item in direct_records.values()
    )
    failed_stages = [record for record in stage_records if record["status"] != "PASS"]
    recovered_stages = []
    unrecovered_stages = []
    for record in failed_stages:
        recovered = (
            record["stage"] == "direct_zdepth_equivalence"
            and direct_equivalence.get("run_id") == run_id
            and direct_equivalence.get("status") == "PASS"
            and direct_equivalence.get("reference_count") == 6
        )
        (recovered_stages if recovered else unrecovered_stages).append(record)
    checks = {
        "current_run_pipeline_log": True,
        "all_1280_standard_frames_accounted_in_final_run": rendered_frames
        + skipped_frames
        >= 1280,
        "all_standard_manifests_complete": standard_complete,
        "all_six_direct_references_accounted": direct_complete,
        "resource_samples_present_for_traceable_run": bool(samples),
        "selected_gpu_samples_present": bool(selected_gpus)
        and all(str(index) in gpu_summary for index in selected_gpus),
        "no_unrecovered_recorded_stage_failure": not unrecovered_stages,
    }
    payload = {
        "schema": "agent.full13.resource_efficiency.v1",
        "created_utc": utc_now(),
        "run_id": run_id,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "pipeline_unit": pipeline_unit,
        "pipeline_started_utc": pipeline_started.isoformat().replace("+00:00", "Z"),
        "observed_wall_seconds_to_summary": round(
            (datetime.now(timezone.utc) - pipeline_started).total_seconds(), 3
        ),
        "stage_records": stage_records,
        "stage_recovery": {
            "failed_stage_records": failed_stages,
            "recovered_stage_records": recovered_stages,
            "unrecovered_stage_records": unrecovered_stages,
            "recovery_contract": (
                "a failed attempt remains recorded and is recovered only by a "
                "same-run authoritative PASS artifact with its full expected count"
            ),
        },
        "cache": {
            "stage_cache_hits": cache_hits,
            "stage_cache_hit_count": len(cache_hits),
            "standard_frames_reused_by_dependency_hash": skipped_frames,
            "standard_frames_rendered": rendered_frames,
            "invalidation_contract": "SHA-256 of pack, dependencies, renderer, EXR processor, camera contract, engine, resolution, samples, and shadow settings",
        },
        "render_execution": {
            "standard_required_frames": 1280,
            "standard_frames_rendered": rendered_frames,
            "standard_frames_reused": skipped_frames,
            "standard_process_retry_count": retry_count,
            "direct_required_frames": 6,
            "direct_frames_rendered": direct_rendered,
            "direct_frames_reused": direct_skipped,
            "standard_layers": layer_records,
            "direct_references": direct_records,
        },
        "resources": {
            "sample_interval_seconds": 30,
            "sample_row_count": len(samples),
            "final_pipeline_unit_sample_row_count": len(final_unit_samples),
            "profiled_pipeline_units": sorted({row["unit"] for row in samples}),
            "sampling_scope": (
                "all restart-safe pipeline units sharing the immutable run ID; "
                "the final unit may have zero dedicated samples"
            ),
            "peak_pipeline_cgroup_memory_bytes": max(memory_values, default=0),
            "observed_pipeline_cpu_time_ns": sum(
                max(values) - min(values) for values in cpu_by_unit.values() if values
            ),
            "selected_gpu_indices": selected_gpus,
            "gpu_samples": gpu_summary,
            "gpu_metric_scope": "server-wide nvidia-smi samples; selected cards are identified, but other users' concurrent GPU work is not attributed to this process",
        },
    }
    atomic_json(payload)
    if payload["status"] != "PASS":
        raise SystemExit(2)


if __name__ == "__main__":
    main()

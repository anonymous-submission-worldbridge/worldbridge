#!/usr/bin/env python3
"""Unified Table-4 CLI for the HY-World 2.0 comparison row."""

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


import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
REPO_ROOT = BASELINES_ROOT.parent
TABLE4_ROOT = _BASELINE_PROJECT_ROOT / "baselines/methods/hyworld/unified/native"
RESULT_ROOT = BASELINES_ROOT / "results/table4/hyworld2"
PYTHON = Path(
    os.environ.get("HYWORLD2_PYTHON", BASELINES_ROOT / "envs/hyworld2/bin/python")
)
sys.path.insert(0, str(BASELINES_ROOT))


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


HY = load_module("table4_cli_hyworld2", (TABLE4_ROOT / "adapters/hyworld.py"))
AQS = load_module(
    "table4_cli_aqs", (TABLE4_ROOT / "../../../../evaluation/unified/aqs.py")
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def prepare(phase: str) -> dict[str, Any]:
    runs = [
        run
        for domain in ("indoor", "urban")
        for run in HY.select_runs(domain, phase, HY.DATA_ROOT)
    ]
    report = {
        "schema_version": "table4-hyworld2-prepare-v1",
        "phase": phase,
        "pair_count": len(runs) // 2,
        "side_run_count": len(runs),
        "spec_sha256": HY.SPEC_SHA256,
        "protocol_sha256": sha256_file(HY.PROTOCOL_PATH),
        "prepared_at_utc": utc_now(),
        "runs": [str(run.relative_to(BASELINES_ROOT)) for run in runs],
    }
    atomic_json(RESULT_ROOT / phase / "prepare.json", report)
    return report


def capability_audit() -> dict[str, Any]:
    source = HY.SOURCE_ROOT
    readme = source / "hyworld2/worldgen/README.md"
    source_files = sorted((source / "hyworld2").rglob("*.py"))
    fields = (
        "target_building_id",
        "interior_id",
        "entrance_id",
        "native_shared_world_frame",
    )
    occurrences = {}
    for field in fields:
        hits = []
        for path in source_files:
            text = path.read_text(encoding="utf-8", errors="replace")
            if field in text:
                hits.append(str(path.relative_to(source)))
        occurrences[field] = hits
    report = {
        "schema_version": "table4-hyworld2-capability-audit-v1",
        "method": "HY-World 2.0",
        "upstream_commit": HY.SOURCE_COMMIT,
        "audited_source_file_count": len(source_files),
        "official_worldgen_readme": str(readme.relative_to(REPO_ROOT)),
        "official_worldgen_readme_sha256": sha256_file(readme),
        "official_interface": "one panorama -> one 3DGS/mesh world",
        "required_unified_identity_field_occurrences": occurrences,
        "native_target_building_identity": False,
        "native_corresponding_interior_identity": False,
        "native_common_entrance_identity": False,
        "native_shared_indoor_outdoor_frame": False,
        "assigned_track": "matched_text_independent",
        "not_applicable_code": "N/A-U",
        "evaluable_metrics": ["functional_aqs", "visual_aqs"],
        "not_applicable_metrics": [
            "spatial_aqs",
            "shape_iou",
            "entrance_alignment",
            "entrance_passability",
            "transition_collision",
            "io_connectivity_rate",
            "cross_boundary_reachability",
        ],
        "audited_at_utc": utc_now(),
    }
    if any(occurrences.values()):
        raise RuntimeError(
            "Unified identity fields appeared in the frozen source; manual audit required"
        )
    atomic_json(RESULT_ROOT / "capability_audit.json", report)
    return report


def preflight() -> dict[str, Any]:
    required = [
        PYTHON,
        HY.PANO_MODEL_ROOT / "HY-Pano-2.0/config.json",
        HY.PANO_MODEL_ROOT / "HY-Pano-2.0/model-00032-of-00032.safetensors",
        HY.WORLDSTEREO_ROOT / "worldstereo-memory-dmd/model.safetensors",
        HY.WAN_BASE_ROOT / "model_index.json",
        HY.MOGE_MODEL_PATH,
        HY.SAM3_ROOT / "config.json",
        HY.GROUNDING_DINO_ROOT / "config.json",
        HY.ZIM_ROOT / "zim_vit_l_2092/encoder.onnx",
        HY.QWEN_VLM_ROOT / "config.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    report = {
        "schema_version": "table4-hyworld2-preflight-v1",
        "required_file_count": len(required),
        "missing": missing,
        "ready": not missing,
        "uses_existing_local_assets_only": True,
        "resolved_checkpoint_roots": {
            "hy_pano": str(HY.PANO_MODEL_ROOT),
            "worldstereo": str(HY.WORLDSTEREO_ROOT),
            "wan_base": str(HY.WAN_BASE_ROOT),
            "qwen_vlm": str(HY.QWEN_VLM_ROOT),
        },
        "node_local_cache_requires_exact_file_size_manifest": True,
        "checked_at_utc": utc_now(),
    }
    atomic_json(RESULT_ROOT / "preflight.json", report)
    if missing:
        raise FileNotFoundError(f"HY-World local runtime is incomplete: {missing}")
    return report


def generate(args: argparse.Namespace) -> int:
    prepare(args.phase)
    capability_audit()
    preflight()
    command = [
        str(PYTHON),
        str((TABLE4_ROOT / "supervise_hyworld.py")),
        "--trial",
        args.phase,
        "--domains",
        "indoor",
        "urban",
        "--allowed-gpus",
        *(str(gpu) for gpu in args.gpus),
        "--panorama-min-gpus",
        "2",
        "--panorama-gpu-max-memory-gib",
        "40",
        "--panorama-device-map",
        "auto",
        "--poll-seconds",
        str(args.poll_seconds),
        "--min-free-mib",
        "10000",
        "--llm-min-free-mib",
        "40000",
        "--max-used-mib",
        "49140",
        "--max-utilization",
        "100",
        "--stable-idle-seconds",
        str(args.stable_idle_seconds),
        "--min-free-disk-gib",
        str(args.min_free_disk_gib),
        "--log-file",
        str(RESULT_ROOT / args.phase / "supervisor.log"),
        "--state-file",
        str(RESULT_ROOT / args.phase / "supervisor_state.json"),
    ]
    if args.external_llm:
        command.extend(["--external-llm", "--llm-port", str(args.llm_port)])
    return subprocess.run(command, cwd=REPO_ROOT, check=False).returncode


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    evidence = AQS.build_evidence(args.phase, require_terminal=True)
    import baselines.methods.hyworld.unified.native.run_hyworld_matrix as matrix

    process = None
    try:
        if args.external_llm:
            if not matrix.llm_health(args.port):
                raise RuntimeError(f"No healthy local VLM at port {args.port}")
        else:
            if matrix.gpu_free_mib(args.gpu) < 30_000:
                raise RuntimeError(f"GPU {args.gpu} has less than 30,000 MiB free")
            process, _ = matrix.start_vllm(args.gpu, args.port, 16_384, 900)
        score = AQS.score_evidence(args.phase, args.port)
    finally:
        if process is not None:
            matrix.stop_process_group(process)
    return {"evidence": evidence, "scoring": score}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="action", required=True)
    for action in ("prepare", "status", "aggregate"):
        child = subparsers.add_parser(action)
        child.add_argument("--phase", choices=("pilot", "formal"), required=True)
    subparsers.add_parser("capability-audit")
    subparsers.add_parser("preflight")
    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    generate_parser.add_argument("--gpus", nargs="+", type=int, default=list(range(6)))
    generate_parser.add_argument("--poll-seconds", type=int, default=30)
    generate_parser.add_argument("--stable-idle-seconds", type=int, default=180)
    generate_parser.add_argument("--min-free-disk-gib", type=float, default=120.0)
    generate_parser.add_argument("--external-llm", action="store_true")
    generate_parser.add_argument("--llm-port", type=int, default=18080)
    evaluate_parser = subparsers.add_parser("evaluate")
    evaluate_parser.add_argument("--phase", choices=("pilot", "formal"), required=True)
    evaluate_parser.add_argument("--gpu", type=int, default=0)
    evaluate_parser.add_argument("--port", type=int, default=18082)
    evaluate_parser.add_argument("--external-llm", action="store_true")
    args = parser.parse_args()
    if args.action == "prepare":
        payload = prepare(args.phase)
    elif args.action == "capability-audit":
        payload = capability_audit()
    elif args.action == "preflight":
        payload = preflight()
    elif args.action == "generate":
        return generate(args)
    elif args.action == "status":
        payload = AQS.matrix_audit(args.phase)
    elif args.action == "evaluate":
        payload = evaluate(args)
    else:
        payload = AQS.aggregate(args.phase)
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

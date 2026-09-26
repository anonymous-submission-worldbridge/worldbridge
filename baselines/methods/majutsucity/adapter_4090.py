#!/usr/bin/env python3
"""Current-host launcher for the frozen MajutsuCity Table-2 adapter."""

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
import json
import os
import shutil
from pathlib import Path


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
ADAPTER_PATH = Path(__file__).with_name("adapter.py")
SPEC = importlib.util.spec_from_file_location("majutsucity_adapter_base", ADAPTER_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot load MajutsuCity adapter: {ADAPTER_PATH}")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)

# Reuse the checked-out and patched upstream source, the existing model files,
# and the previous host's native/formal output roots. No model or case copy is
# made during migration.
adapter.SOURCE_ROOT = BASELINES / "work/majutsucity_l40s/source"
adapter.CONFIG_FILE = (
    BASELINES
    / "methods/majutsucity/protocol/generation/majutsucity_4090.paths.local.yaml"
)
adapter.NATIVE_OUTPUT_ROOT = BASELINES / "data/majutsucity_native_l40s"
adapter.PILOT_DATA_ROOT = BASELINES / "data/pilot_l40s"
adapter.GENERATE_CITY = adapter.SOURCE_ROOT / "scripts/generate_city.py"
adapter.PYTHON = BASELINES / "envs/majutsucity/bin/python"


base_prepare_run = adapter.prepare_run


def resume_safe_prepare_run(trial_mode, spec, logical_seed):
    case_dir = adapter.native_case_dir(trial_mode, spec, logical_seed)
    # A previous L40S run staged one case in /dev/shm. Its public link remains,
    # but the volatile target cannot survive migration. Remove only that proven
    # dangling link; real directories and valid links are preserved verbatim.
    if case_dir.is_symlink() and not case_dir.exists():
        case_dir.unlink()
    return base_prepare_run(trial_mode, spec, logical_seed)


adapter.prepare_run = resume_safe_prepare_run

# These placement controls affect memory residency only. Frozen inference
# steps, CFG, seeds, prompts, assets, and output-selection policy are unchanged.
os.environ.setdefault("MAJUTSUCITY_QWEN_ENV_PLACEMENT", "group_cpu_offload")
os.environ.setdefault("MAJUTSUCITY_QWEN_WORKER_STAGGER_SECONDS", "5")
os.environ.setdefault("MAJUTSUCITY_QWEN_GROUP_OFFLOAD_TYPE", "leaf_level")
os.environ.setdefault("MAJUTSUCITY_QWEN_GROUP_OFFLOAD_STREAM", "1")
os.environ.setdefault(
    "MAJUTSUCITY_QWEN_PLACEMENT_BY_GROUP",
    json.dumps({str(gpu): "group_cpu_offload" for gpu in range(8)}),
)
os.environ.setdefault(
    "MAJUTSUCITY_QWEN_WEIGHT_BY_GROUP",
    json.dumps({str(gpu): 1 for gpu in range(8)}),
)
os.environ.setdefault("MAJUTSUCITY_SKIP_ASSEMBLY_PREVIEW", "1")

# /data is space constrained. Reuse model snapshots in place and keep every
# newly-created framework cache on the machine's temporary filesystem.
runtime_cache = Path("/tmp/majutsucity_4090")
os.environ.setdefault("MAJUTSUCITY_HOST_HF_HOME", str(runtime_cache / "huggingface"))
os.environ.setdefault(
    "MAJUTSUCITY_HOST_HF_HUB_CACHE",
    str(BASELINES / "cache/huggingface/majutsucity/hub"),
)
os.environ.setdefault("MAJUTSUCITY_HOST_TORCH_HOME", str(runtime_cache / "torch"))
os.environ.setdefault("MAJUTSUCITY_HOST_XDG_CACHE_HOME", str(runtime_cache / "xdg"))
os.environ.setdefault(
    "MAJUTSUCITY_HOST_MPLCONFIGDIR", str(runtime_cache / "matplotlib")
)
os.environ.setdefault("HF_MODULES_CACHE", str(runtime_cache / "huggingface/modules"))


base_generation_command = adapter.generation_command


def resume_aware_generation_command(trial_mode, spec, logical_seed, plan_path):
    command = base_generation_command(trial_mode, spec, logical_seed, plan_path)
    case_dir = adapter.native_case_dir(trial_mode, spec, logical_seed)
    pipeline_manifest = case_dir / f"assets_{adapter.STYLE}/pipeline_manifest.json"
    if pipeline_manifest.is_file():
        record = json.loads(pipeline_manifest.read_text(encoding="utf-8"))
        building_ids = record.get("resolved_building_ids", [])
        building_root = case_dir / f"assets_{adapter.STYLE}/buildings"
        buildings_complete = bool(building_ids) and all(
            all(
                (building_root / f"building_{building_id}" / name).is_file()
                for name in (
                    "building.glb",
                    "building_shape.json",
                    "building_paint.json",
                )
            )
            for building_id in building_ids
        )
        if record.get("status") == "completed" or buildings_complete:
            command.extend(["--stages", "environment,scene"])
    return command


adapter.generation_command = resume_aware_generation_command


def cleanup_successful_run(args) -> None:
    """Remove reproducible native assets after canonical output validation."""
    spec = adapter.load_spec(args.spec_id)
    destination = adapter.run_dir(args.trial_mode, spec, args.seed)
    if not (destination / "SUCCESS").is_file():
        return
    case_dir = adapter.native_case_dir(args.trial_mode, spec, args.seed)
    freed_bytes = 0
    removed = []
    if case_dir.is_dir():
        freed_bytes = sum(
            path.stat().st_size for path in case_dir.rglob("*") if path.is_file()
        )
        removed.append(str(case_dir.relative_to(BASELINES)))
        if case_dir.is_symlink():
            local_case_dir = case_dir.resolve()
            shutil.rmtree(local_case_dir)
            case_dir.unlink()
        else:
            shutil.rmtree(case_dir)
    adapter.atomic_json(
        destination / "native_cleanup.json",
        {
            "policy": "post_success_native_case_cleanup_v2",
            "retained": [str(destination)],
            "removed": removed,
            "freed_bytes": freed_bytes,
            "finished_at": adapter.utc_now(),
        },
    )


if __name__ == "__main__":
    parsed = adapter.parse_args()
    if parsed.minimum_free_gib == 200.0:
        parsed.minimum_free_gib = 20.0
    result = adapter.execute(parsed)
    if result == 0 and parsed.stage == "all":
        cleanup_successful_run(parsed)
    raise SystemExit(result)

#!/usr/bin/env python3
"""Host launcher for the frozen MajutsuCity adapter on four-card L40S nodes."""

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

# The migrated upstream checkout is read-only. Keep the method implementation
# untouched and select the baselines-local host config through its public
# CONFIG_FILE constant before parsing or preparing a run.
adapter.SOURCE_ROOT = BASELINES / "work/majutsucity_l40s/source"
adapter.CONFIG_FILE = (
    BASELINES / "methods/majutsucity/protocol/generation/majutsucity.paths.local.yaml"
)
adapter.NATIVE_OUTPUT_ROOT = BASELINES / "data/majutsucity_native_l40s"
adapter.PILOT_DATA_ROOT = BASELINES / "data/pilot_l40s"
adapter.GENERATE_CITY = adapter.SOURCE_ROOT / "scripts/generate_city.py"
local_python = Path("/dev/shm/worldbridge_majutsucity_l40s/majutsucity_env/bin/python")
if os.environ.get("MAJUTSUCITY_USE_RAM_STAGE") == "1" and local_python.is_file():
    adapter.PYTHON = local_python

# Keep the public/native path under baselines, but place newly-created case
# payloads in host RAM.  Existing real directories are deliberately left alone
# so an in-progress or resumed case is never relocated underneath a worker.
local_native_root = Path(
    "/dev/shm/worldbridge_majutsucity_l40s/majutsucity_native_l40s"
)
base_prepare_run = adapter.prepare_run


def ram_staged_prepare_run(trial_mode, spec, logical_seed):
    destination, plan_path = base_prepare_run(trial_mode, spec, logical_seed)
    case_dir = adapter.native_case_dir(trial_mode, spec, logical_seed)
    if (
        os.environ.get("MAJUTSUCITY_USE_RAM_STAGE") == "1"
        and local_native_root.parent.is_dir()
        and not case_dir.exists()
    ):
        local_case_dir = local_native_root / case_dir.name
        local_case_dir.mkdir(parents=True, exist_ok=True)
        case_dir.parent.mkdir(parents=True, exist_ok=True)
        case_dir.symlink_to(local_case_dir, target_is_directory=True)
    return destination, plan_path


adapter.prepare_run = ram_staged_prepare_run

# Environment textures use Qwen Image (not Qwen Image Edit).  Shard that model
# over the dedicated multi-GPU environment group while keeping building workers
# on the upstream CPU-offload placement, which is stable for Image Edit.
os.environ.setdefault("MAJUTSUCITY_QWEN_ENV_PLACEMENT", "group_cpu_offload")
os.environ.setdefault("MAJUTSUCITY_QWEN_WORKER_STAGGER_SECONDS", "5")
os.environ.setdefault("MAJUTSUCITY_QWEN_GROUP_OFFLOAD_TYPE", "leaf_level")
os.environ.setdefault("MAJUTSUCITY_QWEN_GROUP_OFFLOAD_STREAM", "1")
os.environ.setdefault(
    "MAJUTSUCITY_QWEN_PLACEMENT_BY_GROUP",
    json.dumps(
        {
            "0": "group_cpu_offload",
            "1": "group_cpu_offload",
            "2": "group_cpu_offload",
            "3": "group_cpu_offload",
        }
    ),
)
os.environ.setdefault(
    "MAJUTSUCITY_QWEN_WEIGHT_BY_GROUP",
    json.dumps({"0": 1, "1": 1, "2": 1, "3": 1}),
)
os.environ.setdefault("MAJUTSUCITY_SKIP_ASSEMBLY_PREVIEW", "1")
host_modules_cache = BASELINES / "cache/huggingface/majutsucity_l40s/modules"
host_modules_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("HF_MODULES_CACHE", str(host_modules_cache))
host_mpl_cache = BASELINES / "cache/matplotlib/majutsucity_l40s"
host_mpl_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MAJUTSUCITY_HOST_MPLCONFIGDIR", str(host_mpl_cache))
host_xdg_cache = BASELINES / "cache/xdg/majutsucity_l40s"
host_xdg_cache.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MAJUTSUCITY_HOST_XDG_CACHE_HOME", str(host_xdg_cache))

base_generation_command = adapter.generation_command


def resume_aware_generation_command(trial_mode, spec, logical_seed, plan_path):
    command = base_generation_command(trial_mode, spec, logical_seed, plan_path)
    case_dir = adapter.native_case_dir(trial_mode, spec, logical_seed)
    pipeline_manifest = case_dir / f"assets_{adapter.STYLE}/pipeline_manifest.json"
    if pipeline_manifest.is_file():
        import json

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
    """Drop the reproducible native case after canonical validation."""
    spec = adapter.load_spec(args.spec_id)
    destination = adapter.run_dir(args.trial_mode, spec, args.seed)
    if not (destination / "SUCCESS").is_file():
        return
    case_dir = adapter.native_case_dir(args.trial_mode, spec, args.seed)
    # Table-2 scoring consumes only the validated canonical renders under
    # ``destination``.  Keeping the native .blend, GLBs, and generated texture
    # assets after SUCCESS costs hundreds of MiB per case and would exhaust the
    # shared filesystem over the 100-case formal matrix.  The canonical input,
    # command/log provenance, 50 sequence frames, 8 anchors, validation report,
    # and SUCCESS marker remain intact, so completed cases still resume/skip.
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
    # The shared filesystem can no longer satisfy the upstream 200 GiB
    # reservation.  Successful runs are compacted immediately below, and one
    # in-flight scene needs less than 2 GiB, so retain a conservative 20 GiB
    # emergency margin on this host.
    if parsed.minimum_free_gib == 200.0:
        parsed.minimum_free_gib = 20.0
    result = adapter.execute(parsed)
    if result == 0 and parsed.stage == "all":
        cleanup_successful_run(parsed)
    raise SystemExit(result)

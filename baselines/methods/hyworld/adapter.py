#!/usr/bin/env python3
"""Deterministic Table-2 adapter for the official HY-World 2.0 pipeline.

This module deliberately keeps preparation and command construction free of
third-party imports so that the input mapping can be audited without a GPU.
Model execution lives in explicit stage scripts and always writes below the
``baselines`` tree.
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


import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
SOURCE_ROOT = Path(
    os.environ.get("HYWORLD2_SOURCE_ROOT", BASELINES_ROOT / "sources/HY-World-2.0")
)
RUNTIME_ROOT = BASELINES_ROOT / "hyworld2_runtime"
DATA_ROOT = RUNTIME_ROOT / "data/table2"
CHECKPOINT_ROOT = RUNTIME_ROOT / "checkpoints"
WORKSET_ROOT = RUNTIME_ROOT / "worksets"
PROTOCOL_PATH = BASELINES_ROOT / "methods/hyworld/protocol/generation/hyworld2.yaml"
SEEDS_PATH = BASELINES_ROOT / "protocol/generation/seeds.json"
SPEC_PATHS = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}
SPEC_HASHES = {
    "indoor": "38ba6b4eb2b65142b9a8223cb656720cd18904ca16d8e73075d5ba12a93ea657",
    "urban": "3c1fde2ec5725145ead3afc8bbf2d110ec78624183de988c1a51570e0f21d79b",
}
SOURCE_COMMIT = "df9988efb87bfc0f4947eb3889411cf957478b06"
PILOT_SPEC_INDICES = (0, 6, 12, 18, 24)
PHASE_SEEDS = {"pilot": (0, 1), "formal": (0, 1, 2, 3)}
PANO_MODEL_ROOT = CHECKPOINT_ROOT / "HY-World-2.0"
WORLDSTEREO_ROOT = CHECKPOINT_ROOT / "WorldStereo"
QWEN_VLM_ROOT = Path(
    os.environ.get(
        "HYWORLD2_QWEN_ROOT",
        CHECKPOINT_ROOT / "Qwen3-VL-8B-Instruct",
    )
)
WAN_BASE_ROOT = CHECKPOINT_ROOT / "Wan2.1-I2V-14B-480P-Diffusers"
SAM3_ROOT = CHECKPOINT_ROOT / "sam3"
MOGE_ROOT = CHECKPOINT_ROOT / "moge-2-vitl-normal"
MOGE_MODEL_PATH = MOGE_ROOT / "model.pt"
GROUNDING_DINO_ROOT = CHECKPOINT_ROOT / "grounding-dino-tiny"
ZIM_ROOT = CHECKPOINT_ROOT / "zim-anything-vitl"


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


def ensure_under_baselines(path: Path) -> Path:
    resolved = path.resolve(strict=False)
    root = BASELINES_ROOT.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Path must remain below {root}: {resolved}") from exc
    return resolved


def load_specs(domain: str) -> list[dict[str, Any]]:
    if domain not in SPEC_PATHS:
        raise ValueError(f"Unsupported domain: {domain}")
    path = SPEC_PATHS[domain]
    actual_hash = sha256_file(path)
    if actual_hash != SPEC_HASHES[domain]:
        raise RuntimeError(
            f"Frozen {domain} specs hash changed: {actual_hash} != {SPEC_HASHES[domain]}"
        )
    specs = [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(specs) != 25:
        raise ValueError(f"Expected 25 {domain} specs, found {len(specs)}")
    for index, spec in enumerate(specs):
        if spec.get("spec_index") != index or spec.get("domain") != domain:
            raise ValueError(f"Malformed frozen spec at {domain} index {index}")
        if not 6 <= len(spec.get("required_facts", [])) <= 10:
            raise ValueError(
                f"{spec.get('spec_id')}: required_facts must contain 6..10 items"
            )
        if len(spec.get("layout_rubric", [])) != 4:
            raise ValueError(
                f"{spec.get('spec_id')}: layout_rubric must contain 4 items"
            )
    return specs


def method_seed(spec: dict[str, Any], logical_seed: int) -> int:
    if logical_seed not in range(4):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    return int(spec["spec_index"]) * 4 + logical_seed


def panorama_prompt(spec: dict[str, Any]) -> str:
    """Apply only the method-required ERP wrapper to the common prompt."""
    return (
        "Create a seamless 360-degree equirectangular panorama depicting this scene: "
        + spec["prompt_en"].strip()
    )


def compile_native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    domain = spec["domain"]
    if domain not in SPEC_PATHS:
        raise ValueError(f"Unsupported domain: {domain}")
    seed = method_seed(spec, logical_seed)
    return {
        "schema_version": "table2-hyworld2-native-v1",
        "method": "hyworld2",
        "method_display_name": "HY-World 2.0",
        "domain": domain,
        "scene_type": "indoor" if domain == "indoor" else "outdoor",
        "spec_id": spec["spec_id"],
        "spec_index": spec["spec_index"],
        "logical_seed": logical_seed,
        "method_seed": seed,
        "common_prompt_en": spec["prompt_en"],
        "panorama_prompt_en": panorama_prompt(spec),
        "adapter_policy": {
            "input_mode": "text",
            "output_selection": "none",
            "quality_suffix": "none",
            "negative_prompt": "official_default",
        },
        "pipeline": {
            "panorama": {
                "backend": "hunyuan_image_3_core_text_to_image",
                "height": 960,
                "width_before_blend": 1952,
                "width_after_blend": 1920,
                "blend_width": 32,
                "bot_task": "image",
                "use_system_prompt": "en_unified",
                "diffusion_steps": 6,
                "attention_implementation": "sdpa",
                "moe_implementation": "eager",
                "taylor_cache": False,
                "taylor_cache_interval": 4,
                "taylor_cache_order": 2,
                "taylor_cache_enable_first_enhance": False,
                "taylor_cache_first_enhance_steps": 3,
                "taylor_cache_enable_tailing_enhance": False,
                "taylor_cache_tailing_enhance_steps": 1,
                "taylor_cache_low_freqs_order": 2,
                "taylor_cache_high_freqs_order": 2,
            },
            "worldnav": {
                "frames": 21,
                "apply_nav_traj": True,
                "apply_up_route": True,
                "apply_recon_iteration": True,
                "force_vlm": True,
            },
            "worldstereo": {
                "variant": "worldstereo-memory-dmd",
                "fsdp": True,
                "align_nframe": 8,
                "max_reference": 8,
                "downsampled_points": 2_000_000,
            },
            "gs_training": {
                "gpus": 4,
                "max_steps": 500,
                "strategy_scale_from_official_8gpu": 4.0 / 3.0,
                "throughput_first": True,
            },
        },
    }


def run_dir(data_root: Path, domain: str, spec_id: str, logical_seed: int) -> Path:
    data_root = ensure_under_baselines(data_root)
    return data_root / domain / "hyworld2" / spec_id / f"seed_{logical_seed}"


def prepare_run(
    spec: dict[str, Any], logical_seed: int, data_root: Path = DATA_ROOT
) -> Path:
    target = run_dir(data_root, spec["domain"], spec["spec_id"], logical_seed)
    native = compile_native_input(spec, logical_seed)
    input_dir = target / "input"
    native_scene = target / "scene/native"
    for directory in (
        input_dir,
        native_scene,
        target / "scene/gs",
        target / "renders/anchors",
        target / "renders/sequence",
        target / "renders/aux",
        target / "metrics",
        target / "logs",
    ):
        directory.mkdir(parents=True, exist_ok=True)

    manifest_path = target / "run_manifest.json"
    migration_allowed = not any(
        path.exists()
        for path in (
            native_scene / "panorama.png",
            native_scene / "render_results",
            native_scene / "world_expansion",
        )
    )
    if manifest_path.exists():
        prior_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        migration_allowed = (
            migration_allowed
            and not prior_manifest.get("generation_success")
            and not any(
                attempt.get("success") for attempt in prior_manifest.get("attempts", [])
            )
        )

    expected = {
        input_dir / "spec.json": spec,
        input_dir / "native_input.json": native,
        native_scene
        / "meta_info.json": {
            "scene_type": native["scene_type"],
            "method_seed": native["method_seed"],
            "logical_seed": logical_seed,
            "spec_id": spec["spec_id"],
            "domain": spec["domain"],
        },
    }
    for path, payload in expected.items():
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing != payload:
                acceleration_only = False
                if path.name == "native_input.json" and migration_allowed:
                    old_copy = json.loads(json.dumps(existing))
                    new_copy = json.loads(json.dumps(payload))
                    old_pano = old_copy.get("pipeline", {}).get("panorama", {})
                    new_pano = new_copy.get("pipeline", {}).get("panorama", {})
                    old_acceleration = {
                        key: old_pano.pop(key, None)
                        for key in (
                            "bot_task",
                            "diffusion_steps",
                            "taylor_cache",
                            "taylor_cache_interval",
                            "taylor_cache_order",
                            "taylor_cache_enable_first_enhance",
                            "taylor_cache_first_enhance_steps",
                            "taylor_cache_enable_tailing_enhance",
                            "taylor_cache_tailing_enhance_steps",
                            "taylor_cache_low_freqs_order",
                            "taylor_cache_high_freqs_order",
                        )
                    }
                    new_acceleration = {
                        key: new_pano.pop(key, None)
                        for key in (
                            "bot_task",
                            "diffusion_steps",
                            "taylor_cache",
                            "taylor_cache_interval",
                            "taylor_cache_order",
                            "taylor_cache_enable_first_enhance",
                            "taylor_cache_first_enhance_steps",
                            "taylor_cache_enable_tailing_enhance",
                            "taylor_cache_tailing_enhance_steps",
                            "taylor_cache_low_freqs_order",
                            "taylor_cache_high_freqs_order",
                        )
                    }
                    old_gs = old_copy.get("pipeline", {}).get("gs_training", {})
                    new_gs = new_copy.get("pipeline", {}).get("gs_training", {})
                    old_gs_acceleration = {
                        key: old_gs.pop(key, None)
                        for key in ("max_steps", "throughput_first")
                    }
                    new_gs_acceleration = {
                        key: new_gs.pop(key, None)
                        for key in ("max_steps", "throughput_first")
                    }
                    acceleration_only = (
                        old_copy == new_copy
                        and new_acceleration
                        == {
                            "bot_task": "image",
                            "diffusion_steps": 6,
                            "taylor_cache": False,
                            "taylor_cache_interval": 4,
                            "taylor_cache_order": 2,
                            "taylor_cache_enable_first_enhance": False,
                            "taylor_cache_first_enhance_steps": 3,
                            "taylor_cache_enable_tailing_enhance": False,
                            "taylor_cache_tailing_enhance_steps": 1,
                            "taylor_cache_low_freqs_order": 2,
                            "taylor_cache_high_freqs_order": 2,
                        }
                        and new_gs_acceleration
                        == {
                            "max_steps": 500,
                            "throughput_first": True,
                        }
                    )
                if not acceleration_only:
                    raise RuntimeError(
                        f"Refusing to overwrite mismatched frozen input: {path}"
                    )
                atomic_json(path, payload)
        else:
            atomic_json(path, payload)

    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = (
            manifest.get("domain"),
            manifest.get("spec_id"),
            manifest.get("logical_seed"),
        )
        expected_identity = (spec["domain"], spec["spec_id"], logical_seed)
        if identity != expected_identity:
            raise RuntimeError(f"Run manifest identity mismatch at {manifest_path}")
        current_protocol_hash = sha256_file(PROTOCOL_PATH)
        if manifest.get("protocol_sha256") != current_protocol_hash:
            attempts = manifest.get("attempts") or []
            has_successful_attempt = any(attempt.get("success") for attempt in attempts)
            has_native_output = any(
                path.exists()
                for path in (
                    native_scene / "panorama.png",
                    native_scene / "render_results",
                    native_scene / "world_expansion",
                )
            )
            if (
                has_successful_attempt
                or manifest.get("generation_success")
                or has_native_output
            ):
                raise RuntimeError(
                    f"Frozen protocol changed after execution began: {manifest_path}"
                )
            # Failed infrastructure/model-load attempts have no reusable model
            # output.  Preserve them, but allow a documented protocol migration
            # before the first successful stage (used for the official Taylor
            # Cache acceleration adopted after the 24-GiB OOM pilot).
            manifest.setdefault("protocol_migrations", []).append(
                {
                    "migrated_at_utc": utc_now(),
                    "from_sha256": manifest.get("protocol_sha256"),
                    "to_sha256": current_protocol_hash,
                    "reason": "pre-success acceleration migration; no native output reused",
                }
            )
            manifest["protocol_sha256"] = current_protocol_hash
            atomic_json(manifest_path, manifest)
    else:
        manifest = {
            "schema_version": "table2-run-manifest-v1",
            "method": "hyworld2",
            "domain": spec["domain"],
            "spec_id": spec["spec_id"],
            "logical_seed": logical_seed,
            "method_seed": native["method_seed"],
            "method_commit": SOURCE_COMMIT,
            "spec_sha256": SPEC_HASHES[spec["domain"]],
            "protocol": str(PROTOCOL_PATH.relative_to(REPO_ROOT)),
            "protocol_sha256": sha256_file(PROTOCOL_PATH),
            "native_input": "input/native_input.json",
            "native_scene": "scene/native",
            "prepared_at_utc": utc_now(),
            "attempts": [],
            "generation_success": False,
            "render_success": False,
            "failure_reason": None,
        }
        atomic_json(manifest_path, manifest)
    return target


def select_runs(
    domain: str,
    phase: str,
    data_root: Path = DATA_ROOT,
    spec_ids: Iterable[str] | None = None,
    logical_seeds: Iterable[int] | None = None,
) -> list[Path]:
    if phase not in PHASE_SEEDS:
        raise ValueError(f"Unsupported phase: {phase}")
    requested_ids = set(spec_ids or [])
    indices = set(PILOT_SPEC_INDICES if phase == "pilot" else range(25))
    specs = [spec for spec in load_specs(domain) if spec["spec_index"] in indices]
    if requested_ids:
        specs = [spec for spec in specs if spec["spec_id"] in requested_ids]
        unknown = requested_ids - {spec["spec_id"] for spec in specs}
        if unknown:
            raise KeyError(f"Unknown or out-of-phase spec ids: {sorted(unknown)}")
    seeds = tuple(PHASE_SEEDS[phase] if logical_seeds is None else logical_seeds)
    if not seeds or any(seed not in PHASE_SEEDS[phase] for seed in seeds):
        raise ValueError(f"Seeds {seeds} are not valid for phase={phase}")
    return [prepare_run(spec, seed, data_root) for spec in specs for seed in seeds]


def create_workset(run_dirs: Iterable[Path], phase: str, domain: str) -> Path:
    native_paths = [ensure_under_baselines(path) / "scene/native" for path in run_dirs]
    if not native_paths:
        raise ValueError("Cannot create an empty workset")
    payload = "\n".join(str(path.resolve()) for path in native_paths).encode("utf-8")
    key = hashlib.sha256(payload).hexdigest()[:12]
    workset = ensure_under_baselines(WORKSET_ROOT / f"{phase}_{domain}_{key}")
    workset.mkdir(parents=True, exist_ok=True)
    for index, native_path in enumerate(native_paths):
        link = workset / f"scene_{index:04d}"
        if link.is_symlink():
            if link.resolve() != native_path.resolve():
                raise RuntimeError(f"Workset symlink mismatch: {link}")
        elif link.exists():
            raise RuntimeError(f"Workset entry is not a symlink: {link}")
        else:
            link.symlink_to(native_path, target_is_directory=True)
    entries = sorted(workset.iterdir())
    if len(entries) != len(native_paths) or any(
        not entry.is_symlink() for entry in entries
    ):
        raise RuntimeError(f"Workset contains unexpected entries: {workset}")
    atomic_json(
        workset.with_suffix(".json"),
        {
            "phase": phase,
            "domain": domain,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "scenes": [str(path.relative_to(BASELINES_ROOT)) for path in native_paths],
        },
    )
    return workset


def runtime_environment() -> dict[str, str]:
    cache = RUNTIME_ROOT / "cache"
    private_cache = cache / f"uid_{os.getuid()}"
    worldgen = SOURCE_ROOT / "hyworld2/worldgen"
    runtime_python_root = Path(
        os.environ.get("HYWORLD2_RUNTIME_PYTHON_ROOT", RUNTIME_ROOT)
    )
    pytorch3d_root = Path(
        os.environ.get(
            "HYWORLD2_PYTORCH3D_ROOT", BASELINES_ROOT / "sources/pytorch3d-worldgen"
        )
    )
    python_paths = [
        runtime_python_root / "python_sm86",
        runtime_python_root / "python",
        SOURCE_ROOT,
        worldgen,
        worldgen / "third_party/gsplat_maskgaussian",
        pytorch3d_root,
        worldgen / "third_party/navmesh/build/lib.linux-x86_64-cpython-311",
    ]
    inherited_pythonpath = os.environ.get("PYTHONPATH")
    if inherited_pythonpath:
        pythonpath = os.pathsep.join(
            [*(str(path) for path in python_paths), inherited_pythonpath]
        )
    else:
        pythonpath = os.pathsep.join(str(path) for path in python_paths)
    environment = {
        "HF_HOME": str(cache / "huggingface"),
        "HUGGINGFACE_HUB_CACHE": str(cache / "huggingface/hub"),
        "HYWORLD2_HF_HUB_CACHE": str(cache / "huggingface/hub"),
        "TORCH_HOME": str(cache / "torch"),
        "TORCH_EXTENSIONS_DIR": str(cache / "torch_extensions"),
        "TORCHINDUCTOR_CACHE_DIR": str(private_cache / "torchinductor"),
        "TRITON_CACHE_DIR": str(private_cache / "triton"),
        "CUDA_CACHE_PATH": str(private_cache / "cuda"),
        "XDG_CACHE_HOME": str(private_cache / "xdg_hyworld2"),
        "TMPDIR": str(RUNTIME_ROOT / "tmp"),
        "PYTHONPYCACHEPREFIX": str(private_cache / "pycache/hyworld2"),
        # Allow a node-local read-only staging copy for large checkpoints.  The
        # canonical files remain under baselines; this only avoids four FSDP
        # ranks rereading 100+ GiB from the shared filesystem.
        "HYWORLD2_WORLDSTEREO_PATH": os.environ.get(
            "HYWORLD2_WORLDSTEREO_PATH", str(WORLDSTEREO_ROOT)
        ),
        "HYWORLD2_WAN_BASE_PATH": os.environ.get(
            "HYWORLD2_WAN_BASE_PATH", str(WAN_BASE_ROOT)
        ),
        "HYWORLD2_WORLDMIRROR_PATH": str(PANO_MODEL_ROOT),
        "HYWORLD2_SAM3_PATH": os.environ.get("HYWORLD2_SAM3_PATH", str(SAM3_ROOT)),
        # MoGeModel.from_pretrained treats any existing local Path as the
        # checkpoint itself (not as a Hugging Face-style model directory).
        "HYWORLD2_MOGE_PATH": os.environ.get(
            "HYWORLD2_MOGE_PATH", str(MOGE_MODEL_PATH)
        ),
        "HYWORLD2_GROUNDING_DINO_PATH": str(GROUNDING_DINO_ROOT),
        "HYWORLD2_ZIM_PATH": str(ZIM_ROOT),
        "PYTHONPATH": pythonpath,
        "CUDA_HOME": next(
            (
                str(path.resolve())
                for path in (
                    Path(os.environ.get("CUDA_HOME", "/usr/local/cuda-12.8")),
                    Path("/usr/local/cuda"),
                )
                if (path / "bin/nvcc").is_file()
            ),
            "/usr/local/cuda",
        ),
        "TORCH_CUDA_ARCH_LIST": "8.6",
        "MAX_JOBS": "8",
        "MPLCONFIGDIR": str(cache / "matplotlib"),
        "TOKENIZERS_PARALLELISM": "false",
    }
    for path_key in (
        "HF_HOME",
        "HUGGINGFACE_HUB_CACHE",
        "TORCH_HOME",
        "TORCH_EXTENSIONS_DIR",
        "XDG_CACHE_HOME",
        "TMPDIR",
        "TORCHINDUCTOR_CACHE_DIR",
        "TRITON_CACHE_DIR",
        "CUDA_CACHE_PATH",
        "PYTHONPYCACHEPREFIX",
        "MPLCONFIGDIR",
    ):
        ensure_under_baselines(Path(environment[path_key])).mkdir(
            parents=True, exist_ok=True
        )
    return environment


def stage_commands(workset: Path, llm_port: int = 18080) -> dict[str, list[str]]:
    python = Path(
        os.environ.get("HYWORLD2_PYTHON", BASELINES_ROOT / "envs/hyworld2/bin/python")
    )
    # Reuse the complete HY-World runtime.  The transferred dedicated pano
    # venv is only an empty shell, while this environment passes the official
    # HY-Pano import smoke test and already contains the pinned CUDA runtime.
    pano_python = python
    worldgen = SOURCE_ROOT / "hyworld2/worldgen"
    runtime_src_root = Path(
        os.environ.get("HYWORLD2_RUNTIME_SRC_ROOT", RUNTIME_ROOT / "src")
    )
    common_vlm = [
        "--llm_addr",
        "127.0.0.1",
        "--llm_port",
        str(llm_port),
        "--llm_name",
        "Qwen/Qwen3-VL-8B-Instruct",
    ]
    return {
        "panorama": [
            str(pano_python),
            str(
                (BASELINES_ROOT / "methods/hyworld/tools/hyworld_generate_panoramas.py")
            ),
            "--workset",
            str(workset),
            "--model-root",
            str(PANO_MODEL_ROOT),
        ],
        "trajectory_planning": [
            str(python),
            str(runtime_src_root / "traj_generate.py"),
            "--target_path",
            str(workset),
            "--seed",
            "0",
            "--apply_nav_traj",
            "--apply_up_route",
            "--apply_recon_iteration",
            "--force_vlm",
            "--skip_exist",
            *common_vlm,
        ],
        "trajectory_rendering": [
            str(python),
            "-m",
            "torch.distributed.run",
            "--standalone",
            "--nproc_per_node",
            "3",
            str(worldgen / "traj_render.py"),
            "--target_path",
            str(workset),
            "--seed",
            "0",
            *common_vlm,
        ],
        "world_expansion": [
            str(python),
            "-m",
            "torch.distributed.run",
            "--standalone",
            "--nproc_per_node",
            "4",
            str(worldgen / "video_gen.py"),
            "--target_path",
            str(workset),
            "--model_type",
            "worldstereo-memory-dmd",
            "--fsdp",
            "--local_files_only",
            "--skip_exist",
            "--seed",
            "0",
            "--fast_nframe",
            "3",
            "--fast_num_frames",
            "9",
            "--fast_dmd_steps",
            "1",
            "--max_trajectories",
            "1",
            "--demo_max_trajectories",
            "4",
            "--align_nframe",
            "2",
            "--max_reference",
            "4",
            "--downsampled_pts",
            "250000",
            "--prune_intermediates",
            "--fast_moge_alignment",
        ],
        "gs_data": [
            str(python),
            "-m",
            "torch.distributed.run",
            "--standalone",
            "--nproc_per_node",
            "4",
            str(worldgen / "gen_gs_data.py"),
            "--root_path",
            str(workset),
            "--save_normal",
            "--split_sky",
            "--pano_density_mult",
            "2",
            "--polar_up_density_mult",
            "4",
            "--polar_down_density_mult",
            "1",
        ],
    }


def gs_train_command(target: Path) -> list[str]:
    target = ensure_under_baselines(target)
    native = json.loads(
        (target / "input/native_input.json").read_text(encoding="utf-8")
    )
    python = Path(
        os.environ.get("HYWORLD2_PYTHON", BASELINES_ROOT / "envs/hyworld2/bin/python")
    )
    return [
        str(python),
        "-m",
        "world_gs_trainer",
        "default",
        "--data_dir",
        str(target / "scene/native/gs_data"),
        "--result_dir",
        str(target / "scene/gs"),
        "--seed",
        str(native["method_seed"]),
        "--max_steps",
        "500",
        "--save_steps",
        "500",
        "--eval_steps",
        "500",
        "--ply_steps",
        "500",
        "--save_ply",
        "--convert_to_spz",
        "--disable_video",
        "--use_scale_regularization",
        "--antialiased",
        "--depth_loss",
        "--normal_loss",
        "--sky_depth_from_pcd",
        "--use_mask_gaussian",
        "--mask_export_stochastic",
        "--no-mask-export-anchor-protection",
        "--use_anchor_protection",
        "--export_mesh",
        "--strategy.refine-start-iter",
        "50",
        "--strategy.refine-stop-iter",
        "250",
        "--strategy.refine-every",
        "33",
        "--strategy.refine-scale2d-stop-iter",
        "250",
        "--strategy.reset-every",
        "99990",
        "--strategy.grow-grad2d",
        "0.0001",
        "--strategy.prune-scale3d",
        "0.1",
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "plan"))
    parser.add_argument("--domain", required=True, choices=tuple(SPEC_PATHS))
    parser.add_argument("--phase", required=True, choices=tuple(PHASE_SEEDS))
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-id", action="append", default=[])
    parser.add_argument("--seed", action="append", type=int)
    parser.add_argument("--llm-port", type=int, default=18080)
    args = parser.parse_args()
    runs = select_runs(args.domain, args.phase, args.data_root, args.spec_id, args.seed)
    workset = create_workset(runs, args.phase, args.domain)
    payload: dict[str, Any] = {
        "phase": args.phase,
        "domain": args.domain,
        "run_count": len(runs),
        "workset": str(workset),
        "runs": [str(path) for path in runs],
    }
    if args.action == "plan":
        payload["commands"] = stage_commands(workset, args.llm_port)
        payload["gs_training_commands"] = [gs_train_command(path) for path in runs]
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

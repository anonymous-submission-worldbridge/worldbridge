#!/usr/bin/env python3
"""Frozen HY-World 2.0 adapter for Table 4's independent track."""

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
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
TABLE4_ROOT = BASELINES_ROOT / "methods/hyworld/unified/native"
PROTOCOL_ROOT = BASELINES_ROOT / "protocol/unified"
PROTOCOL_PATH = (
    PROTOCOL_ROOT / "../../methods/hyworld/protocol/unified/native/hyworld2.yaml"
)
CACHE_LOCK_PATH = (
    PROTOCOL_ROOT
    / "../../methods/hyworld/protocol/unified/native/hyworld2_local_cache.lock.json"
)
SPECS_PATH = PROTOCOL_ROOT / "specs.jsonl"
SPEC_SHA256 = "b3fe8e3d45cacea8d2fb5ea339dfbf3ea87c5e78a421f37a6167798d903e6362"
SOURCE_COMMIT = "df9988efb87bfc0f4947eb3889411cf957478b06"
RUNTIME_ROOT = BASELINES_ROOT / "hyworld2_runtime"
DATA_ROOT = BASELINES_ROOT / "data/table4/hyworld2"
PILOT_DATA_ROOT = BASELINES_ROOT / "data/table4_pilot/hyworld2"
WORKSET_ROOT = RUNTIME_ROOT / "worksets/table4"
PILOT_SPEC_INDICES = (0, 6, 12, 18, 24)
PHASE_SEEDS = {"pilot": (0, 1), "formal": (0, 1, 2, 3)}
SIDE_BY_DOMAIN = {"indoor": "interior", "urban": "exterior"}
SIDE_OFFSET = {"exterior": 0, "interior": 1}


def _load_table2_adapter():
    path = BASELINES_ROOT / "methods/hyworld/adapter.py"
    spec = importlib.util.spec_from_file_location(
        "table4_hyworld2_table2_runtime", path
    )
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot import shared HY-World runtime adapter: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


SHARED = _load_table2_adapter()
SOURCE_ROOT = SHARED.SOURCE_ROOT
CHECKPOINT_ROOT = SHARED.CHECKPOINT_ROOT
# Prefer a node-local, byte-identical staging copy when it is complete.  The
# canonical checkpoint remains under baselines; this avoids repeatedly paging
# 158 GiB across NFS during Accelerate CPU offload.
LOCAL_PANO_MODEL_ROOT = Path(
    os.environ.get(
        "HYWORLD2_TABLE4_PANO_ROOT",
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_models_uid2002/HY-World-2.0"),
    )
)
_local_pano_dir = LOCAL_PANO_MODEL_ROOT / "HY-Pano-2.0"
_cache_lock = json.loads(CACHE_LOCK_PATH.read_text(encoding="utf-8"))


def _matches_local_cache_lock(candidate: Path) -> bool:
    """Revalidate a previously canonical-compared local tree without NFS."""
    entry = _cache_lock.get("entries", {}).get(str(candidate))
    if not entry or not candidate.is_dir():
        return False
    digest = hashlib.sha256()
    file_count = 0
    total_bytes = 0
    rows = []
    for path in candidate.rglob("*"):
        if path.is_file():
            size = path.stat().st_size
            rows.append((str(path.relative_to(candidate)), size))
            file_count += 1
            total_bytes += size
    for relative, size in sorted(rows):
        digest.update(f"{relative}\t{size}\n".encode("utf-8"))
    return (
        file_count == entry.get("file_count")
        and total_bytes == entry.get("total_bytes")
        and digest.hexdigest() == entry.get("size_manifest_sha256")
    )


_local_pano_complete = (
    _matches_local_cache_lock(LOCAL_PANO_MODEL_ROOT)
    and (_local_pano_dir / "model.safetensors.index.json").is_file()
    and (_local_pano_dir / "model-00032-of-00032.safetensors").is_file()
    and len(list(_local_pano_dir.glob("model-*-of-00032.safetensors"))) == 32
)
PANO_MODEL_ROOT = (
    LOCAL_PANO_MODEL_ROOT if _local_pano_complete else SHARED.PANO_MODEL_ROOT
)
SHARED.PANO_MODEL_ROOT = PANO_MODEL_ROOT
QWEN_VLM_ROOT = SHARED.QWEN_VLM_ROOT
SAM3_ROOT = SHARED.SAM3_ROOT
MOGE_ROOT = SHARED.MOGE_ROOT
MOGE_MODEL_PATH = SHARED.MOGE_MODEL_PATH
GROUNDING_DINO_ROOT = SHARED.GROUNDING_DINO_ROOT
ZIM_ROOT = SHARED.ZIM_ROOT


def _same_file_sizes(
    canonical: Path, candidate: Path, required_roots: tuple[str, ...] | None = None
) -> bool:
    """Accept only a fully copied node-local checkpoint tree."""
    if not candidate.is_dir():
        return False
    if required_roots is None and _matches_local_cache_lock(candidate):
        return True

    def included(path: Path, root: Path) -> bool:
        if required_roots is None:
            return True
        relative = str(path.relative_to(root))
        return any(
            relative == item or relative.startswith(f"{item}/")
            for item in required_roots
        )

    canonical_files = {
        str(path.relative_to(canonical)): path.stat().st_size
        for path in canonical.rglob("*")
        if path.is_file() and included(path, canonical)
    }
    candidate_files = {
        str(path.relative_to(candidate)): path.stat().st_size
        for path in candidate.rglob("*")
        if path.is_file() and included(path, candidate)
    }
    return bool(canonical_files) and candidate_files == canonical_files


LOCAL_MODEL_ROOT = Path(
    os.environ.get(
        "HYWORLD2_TABLE4_LOCAL_MODEL_ROOT",
        _wb_expand_paths("${WORLDBRIDGE_CACHE}/hyworld2_models_uid2002"),
    )
)
_local_worldstereo = LOCAL_MODEL_ROOT / "WorldStereo"
_local_wan = LOCAL_MODEL_ROOT / "Wan2.1-I2V-14B-480P-Diffusers"
WORLDSTEREO_ROOT = (
    _local_worldstereo
    if _same_file_sizes(SHARED.WORLDSTEREO_ROOT, _local_worldstereo)
    else SHARED.WORLDSTEREO_ROOT
)
WAN_BASE_ROOT = (
    _local_wan
    if _same_file_sizes(SHARED.WAN_BASE_ROOT, _local_wan)
    else SHARED.WAN_BASE_ROOT
)
SHARED.WORLDSTEREO_ROOT = WORLDSTEREO_ROOT
SHARED.WAN_BASE_ROOT = WAN_BASE_ROOT
SAM3_ROOT = (
    LOCAL_MODEL_ROOT / "sam3"
    if _same_file_sizes(SHARED.SAM3_ROOT, LOCAL_MODEL_ROOT / "sam3")
    else SHARED.SAM3_ROOT
)
MOGE_ROOT = (
    LOCAL_MODEL_ROOT / "moge-2-vitl-normal"
    if _same_file_sizes(SHARED.MOGE_ROOT, LOCAL_MODEL_ROOT / "moge-2-vitl-normal")
    else SHARED.MOGE_ROOT
)
MOGE_MODEL_PATH = MOGE_ROOT / "model.pt"
GROUNDING_DINO_ROOT = (
    LOCAL_MODEL_ROOT / "grounding-dino-tiny"
    if _same_file_sizes(
        SHARED.GROUNDING_DINO_ROOT, LOCAL_MODEL_ROOT / "grounding-dino-tiny"
    )
    else SHARED.GROUNDING_DINO_ROOT
)
ZIM_ROOT = (
    LOCAL_MODEL_ROOT / "zim-anything-vitl"
    if _same_file_sizes(SHARED.ZIM_ROOT, LOCAL_MODEL_ROOT / "zim-anything-vitl")
    else SHARED.ZIM_ROOT
)
SHARED.SAM3_ROOT = SAM3_ROOT
SHARED.MOGE_ROOT = MOGE_ROOT
SHARED.MOGE_MODEL_PATH = MOGE_MODEL_PATH
SHARED.GROUNDING_DINO_ROOT = GROUNDING_DINO_ROOT
SHARED.ZIM_ROOT = ZIM_ROOT


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
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Path must stay below {BASELINES_ROOT}: {resolved}") from exc
    return resolved


def load_pair_specs() -> list[dict[str, Any]]:
    actual = sha256_file(SPECS_PATH)
    if actual != SPEC_SHA256:
        raise RuntimeError(f"Frozen Table 4 specs changed: {actual} != {SPEC_SHA256}")
    rows = [
        json.loads(line)
        for line in SPECS_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(rows) != 25:
        raise ValueError(f"Expected 25 pair specs, found {len(rows)}")
    if [row.get("spec_index") for row in rows] != list(range(25)):
        raise ValueError("Table 4 spec_index must be contiguous 0..24")
    if len({row.get("function") for row in rows}) != 5:
        raise ValueError("Table 4 requires five building functions")
    if len({row.get("visual_theme") for row in rows}) != 5:
        raise ValueError("Table 4 requires five visual styles")
    for row in rows:
        if not row.get("exterior_prompt_en") or not row.get("interior_prompt_en"):
            raise ValueError(f"Missing paired prompts: {row.get('spec_id')}")
        if len(row.get("visual_inheritance", [])) < 3:
            raise ValueError(f"Too few visual inheritance facts: {row.get('spec_id')}")
        program = row.get("interior_program", {})
        if len(program.get("required_zones", [])) < 3:
            raise ValueError(f"Too few required zones: {row.get('spec_id')}")
    return rows


def _side_spec(pair: dict[str, Any], domain: str) -> dict[str, Any]:
    if domain not in SIDE_BY_DOMAIN:
        raise ValueError(f"Unsupported HY-World Table 4 domain: {domain}")
    side = SIDE_BY_DOMAIN[domain]
    prompt_key = "interior_prompt_en" if side == "interior" else "exterior_prompt_en"
    required = (
        pair["interior_program"]["required_zones"]
        + pair["interior_program"]["required_objects"]
        if side == "interior"
        else [
            f"a clearly identifiable {pair['function']} target building",
            "a visible public approach to the target",
            *pair["visual_inheritance"],
        ]
    )
    return {
        "spec_id": pair["spec_id"],
        "spec_index": pair["spec_index"],
        "domain": domain,
        "side": side,
        "category": pair["function"],
        "style": pair["visual_theme"],
        "prompt_en": pair[prompt_key],
        "required_facts": required[:10],
        "layout_rubric": [
            "scene is visibly coherent",
            "objects and surfaces are supported",
            "human-scale circulation is plausible",
            "the intended building use is legible",
        ],
        "pair_spec_sha256": SPEC_SHA256,
    }


def load_specs(domain: str) -> list[dict[str, Any]]:
    return [_side_spec(pair, domain) for pair in load_pair_specs()]


def method_seed(spec: dict[str, Any], logical_seed: int) -> int:
    if logical_seed not in range(4):
        raise ValueError("Table 4 logical seed must be one of 0,1,2,3")
    side = str(spec["side"])
    return 2 * (int(spec["spec_index"]) * 4 + logical_seed) + SIDE_OFFSET[side]


def panorama_prompt(spec: dict[str, Any]) -> str:
    return (
        "Create a seamless 360-degree equirectangular panorama depicting this scene: "
        + str(spec["prompt_en"]).strip()
    )


def compile_native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    seed = method_seed(spec, logical_seed)
    return {
        "schema_version": "table4-hyworld2-independent-native-v1",
        "method": "hyworld2",
        "method_display_name": "HY-World 2.0",
        "track": "matched_text_independent",
        "domain": spec["domain"],
        "side": spec["side"],
        "scene_type": "indoor" if spec["side"] == "interior" else "outdoor",
        "spec_id": spec["spec_id"],
        "pair_id": f"{spec['spec_id']}__seed_{logical_seed}",
        "spec_index": spec["spec_index"],
        "logical_seed": logical_seed,
        "method_seed": seed,
        "common_prompt_en": spec["prompt_en"],
        "panorama_prompt_en": panorama_prompt(spec),
        "adapter_policy": {
            "input_mode": "text",
            "output_selection": "none",
            "quality_suffix": "none",
            "independent_generation": True,
        },
        "pipeline": {
            "panorama": {
                "diffusion_steps": 6,
                "bot_task": "image",
                "taylor_cache": False,
            },
            "worldstereo": {
                "variant": "worldstereo-memory-dmd",
                "dmd_steps": 1,
                "fast_nframe": 3,
                "fast_num_frames": 9,
                "align_nframe": 2,
                "max_reference": 4,
                "downsampled_points": 250_000,
                "max_trajectories": 1,
            },
            "gs_data": {"fast_density": True},
            "gs_training": {"max_steps": 50, "save_ply": True, "export_mesh": False},
        },
    }


def pair_root(data_root: Path, spec_id: str, logical_seed: int) -> Path:
    return ensure_under_baselines(data_root) / spec_id / f"seed_{logical_seed}"


def run_dir(data_root: Path, domain: str, spec_id: str, logical_seed: int) -> Path:
    return pair_root(data_root, spec_id, logical_seed) / SIDE_BY_DOMAIN[domain]


def _write_frozen(path: Path, payload: Any) -> None:
    if path.exists():
        existing = json.loads(path.read_text(encoding="utf-8"))
        if existing != payload:
            raise RuntimeError(f"Refusing to overwrite mismatched frozen input: {path}")
    else:
        atomic_json(path, payload)


def prepare_run(
    spec: dict[str, Any], logical_seed: int, data_root: Path = DATA_ROOT
) -> Path:
    target = run_dir(data_root, spec["domain"], spec["spec_id"], logical_seed)
    pair = load_pair_specs()[int(spec["spec_index"])]
    root = pair_root(data_root, spec["spec_id"], logical_seed)
    native = compile_native_input(spec, logical_seed)
    input_dir = target / "input"
    native_scene = target / "scene/native"
    for directory in (
        root / "input",
        root / "renders",
        root / "metrics/raw",
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

    pair_payload = {
        **pair,
        "pair_id": f"{pair['spec_id']}__seed_{logical_seed}",
        "logical_seed": logical_seed,
        "track": "matched_text_independent",
        "native_shared_world_frame": False,
    }
    _write_frozen(root / "input/pair_spec.json", pair_payload)
    _write_frozen(input_dir / "spec.json", spec)
    _write_frozen(input_dir / "native_input.json", native)
    _write_frozen(
        native_scene / "meta_info.json",
        {
            "scene_type": native["scene_type"],
            "method_seed": native["method_seed"],
            "logical_seed": logical_seed,
            "spec_id": spec["spec_id"],
            "domain": spec["domain"],
            "side": spec["side"],
            "pair_id": native["pair_id"],
        },
    )

    manifest_path = target / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        identity = (
            manifest.get("spec_id"),
            manifest.get("logical_seed"),
            manifest.get("side"),
        )
        expected = (spec["spec_id"], logical_seed, spec["side"])
        if identity != expected:
            raise RuntimeError(f"Side manifest identity mismatch: {manifest_path}")
    else:
        atomic_json(
            manifest_path,
            {
                "schema_version": "table4-hyworld2-side-run-v1",
                "method": "hyworld2",
                "track": "matched_text_independent",
                "domain": spec["domain"],
                "side": spec["side"],
                "spec_id": spec["spec_id"],
                "pair_id": native["pair_id"],
                "logical_seed": logical_seed,
                "method_seed": native["method_seed"],
                "method_commit": SOURCE_COMMIT,
                "spec_sha256": SPEC_SHA256,
                "protocol": str(PROTOCOL_PATH.relative_to(REPO_ROOT)),
                "protocol_sha256": sha256_file(PROTOCOL_PATH),
                "native_input": "input/native_input.json",
                "native_scene": "scene/native",
                "prepared_at_utc": utc_now(),
                "attempts": [],
                "generation_success": False,
                "render_success": False,
                "failure_reason": None,
            },
        )

    pair_manifest_path = root / "manifest.json"
    if not pair_manifest_path.exists():
        atomic_json(
            pair_manifest_path,
            {
                "schema_version": "table4-pair-manifest-v1",
                "method": "hyworld2",
                "track": "matched_text_independent",
                "pair_id": native["pair_id"],
                "spec_id": spec["spec_id"],
                "logical_seed": logical_seed,
                "method_seeds": {
                    "exterior": 2 * (int(spec["spec_index"]) * 4 + logical_seed),
                    "interior": 2 * (int(spec["spec_index"]) * 4 + logical_seed) + 1,
                },
                "native_shared_world_frame": False,
                "human_operations": False,
                "spec_sha256": SPEC_SHA256,
                "protocol_sha256": sha256_file(PROTOCOL_PATH),
                "prepared_at_utc": utc_now(),
                "pair_success": False,
            },
        )
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
    selected_root = (
        PILOT_DATA_ROOT if phase == "pilot" else ensure_under_baselines(data_root)
    )
    requested = set(spec_ids or [])
    allowed_indices = set(PILOT_SPEC_INDICES if phase == "pilot" else range(25))
    specs = [
        spec for spec in load_specs(domain) if spec["spec_index"] in allowed_indices
    ]
    if requested:
        available = {spec["spec_id"] for spec in specs}
        unknown = requested - available
        if unknown:
            raise KeyError(f"Unknown or out-of-phase spec ids: {sorted(unknown)}")
        specs = [spec for spec in specs if spec["spec_id"] in requested]
    seeds = tuple(PHASE_SEEDS[phase] if logical_seeds is None else logical_seeds)
    if not seeds or not set(seeds).issubset(set(PHASE_SEEDS[phase])):
        raise ValueError(f"Invalid seeds {seeds} for phase={phase}")
    # `run.py prepare` freezes every side before generation and records one
    # phase-level lock.  Once that lock matches the immutable spec/protocol,
    # avoid re-statting thousands of small NFS files on every resumable stage.
    # Individual stage validators still inspect their required artifacts.
    phase_lock = BASELINES_ROOT / f"results/table4/hyworld2/{phase}/prepare.json"
    if phase_lock.is_file():
        try:
            prepared = json.loads(phase_lock.read_text(encoding="utf-8"))
            expected_pairs = len(PILOT_SPEC_INDICES) * 2 if phase == "pilot" else 100
            if (
                prepared.get("phase") == phase
                and prepared.get("pair_count") == expected_pairs
                and prepared.get("side_run_count") == 2 * expected_pairs
                and prepared.get("spec_sha256") == SPEC_SHA256
                and prepared.get("protocol_sha256") == sha256_file(PROTOCOL_PATH)
            ):
                return [
                    selected_root / spec["spec_id"] / f"seed_{seed}" / spec["side"]
                    for spec in specs
                    for seed in seeds
                ]
        except (OSError, TypeError, json.JSONDecodeError):
            pass
    return [prepare_run(spec, seed, selected_root) for spec in specs for seed in seeds]


def create_workset(run_dirs: Iterable[Path], phase: str, domain: str) -> Path:
    natives = [ensure_under_baselines(path) / "scene/native" for path in run_dirs]
    if not natives:
        raise ValueError("Cannot create an empty workset")
    payload = "\n".join(str(path.resolve()) for path in natives).encode("utf-8")
    key = hashlib.sha256(payload).hexdigest()[:12]
    root = ensure_under_baselines(WORKSET_ROOT / f"{phase}_{domain}_{key}")
    root.mkdir(parents=True, exist_ok=True)
    for index, native in enumerate(natives):
        link = root / f"scene_{index:04d}"
        if link.is_symlink():
            if link.resolve() != native.resolve():
                raise RuntimeError(f"Mismatched workset link: {link}")
        elif link.exists():
            raise RuntimeError(f"Unexpected workset entry: {link}")
        else:
            link.symlink_to(native.resolve(), target_is_directory=True)
    atomic_json(
        root.with_suffix(".json"),
        {
            "phase": phase,
            "domain": domain,
            "sha256": hashlib.sha256(payload).hexdigest(),
            "scenes": [str(path.relative_to(BASELINES_ROOT)) for path in natives],
        },
    )
    return root


def runtime_environment() -> dict[str, str]:
    return SHARED.runtime_environment()


def stage_commands(workset: Path, llm_port: int = 18080) -> dict[str, list[str]]:
    return SHARED.stage_commands(workset, llm_port)


def gs_train_command(target: Path) -> list[str]:
    return SHARED.gs_train_command(target)

#!/usr/bin/env python3
"""Deterministic Table-2 adapter for paulengstler/syncity-3k.

The adapter compiles the shared semantic specifications into SynCity 3000's
native JSON layout format.  It deliberately invokes the upstream entry points
as subprocesses so the vendored source remains an unmodified, auditable
snapshot.  All writable paths are required to stay below ``baselines/``.
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
import random
import subprocess
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
SOURCE_ROOT = BASELINES_ROOT / "vendor/syncity-3k"
PYTHON = BASELINES_ROOT / "envs/syncity-3k/bin/python"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}
METHOD = "syncity3k"
UPSTREAM_COMMIT = "b4052154217a13cdbdec28ef77ae77581d90afff"
SCENE_SIZE = 3
WINDOW_SIZE = 2
STRIDE = 1
EXTRUSION_HEIGHT = 60


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require_below_baselines(path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASELINES_ROOT.resolve())
    except ValueError as exc:
        raise ValueError(
            f"Path must remain below {BASELINES_ROOT}: {resolved}"
        ) from exc
    return resolved


def load_specs(domain: str, spec_file: Path | None = None) -> dict[str, dict[str, Any]]:
    path = require_below_baselines(spec_file or SPEC_FILES[domain])
    specs: dict[str, dict[str, Any]] = {}
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            spec = json.loads(line)
            if spec.get("domain") != domain:
                raise ValueError(f"{path}:{line_number}: expected domain={domain!r}")
            spec_id = str(spec["spec_id"])
            if spec_id in specs:
                raise ValueError(f"{path}:{line_number}: duplicate spec_id={spec_id!r}")
            specs[spec_id] = spec
    return specs


def run_dir_for(data_root: Path, domain: str, spec_id: str, seed: int) -> Path:
    if domain not in SPEC_FILES:
        raise ValueError(f"Unsupported domain: {domain}")
    if seed not in (0, 1, 2, 3):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    if "/" in spec_id or spec_id in {".", ".."}:
        raise ValueError(f"Unsafe spec id: {spec_id!r}")
    return require_below_baselines(
        data_root / domain / METHOD / spec_id / f"seed_{seed}"
    )


INDOOR_CONSTRAINTS: dict[str, list[tuple[float, float, float, float, str]]] = {
    "bedroom": [
        (0.35, 0.40, 1.30, 1.05, "one bed with bedside tables"),
        (2.05, 0.45, 0.60, 0.85, "a wardrobe and bedroom storage"),
        (0.35, 2.15, 0.85, 0.45, "a bright window beside the bed"),
    ],
    "living_room": [
        (0.30, 0.45, 1.35, 0.80, "a sofa seating arrangement"),
        (1.20, 1.25, 0.70, 0.60, "a coffee table"),
        (2.15, 0.55, 0.55, 0.90, "a television and living-room storage"),
    ],
    "kitchen": [
        (0.25, 0.35, 1.55, 0.55, "a kitchen counter with sink and stove"),
        (2.10, 0.40, 0.55, 0.80, "a refrigerator and tall kitchen cabinets"),
        (0.80, 1.75, 1.10, 0.65, "a kitchen island or dining work surface"),
    ],
    "bathroom": [
        (0.35, 0.40, 1.20, 0.70, "a bathtub or shower enclosure"),
        (2.05, 0.45, 0.60, 0.65, "a toilet"),
        (1.15, 1.80, 0.80, 0.55, "a bathroom sink with mirror"),
    ],
    "dining_room": [
        (0.70, 0.75, 1.55, 1.10, "a dining table with chairs around it"),
        (2.20, 0.35, 0.50, 0.80, "a dining-room cabinet or sideboard"),
        (0.30, 2.05, 0.85, 0.45, "a bright dining-room window"),
    ],
}

URBAN_TOPOLOGY: dict[str, tuple[float, float, float, float, str]] = {
    "four_way": (0.70, 0.70, 1.60, 1.60, "a clearly marked four-way road intersection"),
    "t_junction": (0.65, 0.65, 1.70, 1.60, "a clearly marked T-junction"),
    "main_road_side_road": (
        0.45,
        0.65,
        2.10,
        1.55,
        "a main road joined by one side road",
    ),
    "offset_intersection": (
        0.55,
        0.60,
        1.90,
        1.70,
        "a staggered offset road intersection",
    ),
    "irregular_intersection": (
        0.55,
        0.55,
        1.90,
        1.90,
        "an irregular angled road intersection",
    ),
}

URBAN_CATEGORY: dict[str, tuple[float, float, float, float, str]] = {
    "residential": (0.20, 0.20, 0.75, 0.75, "residential houses with trees"),
    "commercial": (2.05, 0.20, 0.75, 0.75, "shops and commercial buildings"),
    "mixed_use": (
        2.05,
        2.05,
        0.75,
        0.75,
        "mixed-use buildings with ground-floor stores",
    ),
    "park_edge": (0.15, 1.95, 0.85, 0.85, "a landscaped park with paths and benches"),
    "leisure_civic": (
        1.95,
        1.95,
        0.85,
        0.85,
        "a civic or leisure building and public plaza",
    ),
}


def _constraint(row: tuple[float, float, float, float, str]) -> dict[str, Any]:
    x, y, width, height, prompt = row
    return {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "prompt": prompt,
    }


def compile_native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    """Compile one shared spec without inspecting any model output."""
    domain = str(spec["domain"])
    category = str(spec["category"])
    if logical_seed not in (0, 1, 2, 3):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    if domain == "indoor":
        if category not in INDOOR_CONSTRAINTS:
            raise KeyError(f"No indoor native layout for category={category!r}")
        constraints = [_constraint(row) for row in INDOOR_CONSTRAINTS[category]]
        theme = (
            "uniform bright midday interior light, matte non-reflective surfaces, "
            "8k, photorealistic natural textures, isometric perspective"
        )
    elif domain == "urban":
        topology = str(spec["topology"])
        if topology not in URBAN_TOPOLOGY:
            raise KeyError(f"No urban native layout for topology={topology!r}")
        if category not in URBAN_CATEGORY:
            raise KeyError(f"No urban native layout for category={category!r}")
        constraints = [
            _constraint(URBAN_TOPOLOGY[topology]),
            _constraint(URBAN_CATEGORY[category]),
        ]
        theme = (
            "uniform bright midday sunlight, matte non-reflective surfaces, "
            "8k, photorealistic natural textures, isometric perspective"
        )
    else:
        raise ValueError(f"Unsupported domain: {domain}")
    return {
        "method": METHOD,
        "implementation": "paulengstler/syncity-3k (SynCity 3000)",
        "logical_seed": logical_seed,
        "method_seed": logical_seed,
        "source_spec_id": spec["spec_id"],
        "scene_prompt": spec["prompt_en"],
        "scene_size": SCENE_SIZE,
        "grid_size": SCENE_SIZE,
        "window_size": WINDOW_SIZE,
        "stride": STRIDE,
        "theme_prompt": theme,
        "constraints": constraints,
        "extrusion_height": EXTRUSION_HEIGHT,
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _run_logged(
    command: list[str], log_path: Path, environment: dict[str, str]
) -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("w", encoding="utf-8") as handle:
        completed = subprocess.run(
            command,
            cwd=SOURCE_ROOT,
            env=environment,
            text=True,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    if completed.returncode != 0:
        tail = log_path.read_text(encoding="utf-8", errors="replace")[-6000:]
        raise RuntimeError(
            f"Command exited {completed.returncode}: {' '.join(command)}\n{tail}"
        )


def worker_environment() -> dict[str, str]:
    environment = dict(os.environ)
    # Formal runs are fully offline after the pinned assets have been staged.
    # In particular, do not silently spend the user's metered proxy traffic.
    for name in (
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "http_proxy",
        "https_proxy",
        "all_proxy",
    ):
        environment.pop(name, None)
    existing_hf = BASELINES_ROOT / "checkpoints/syncity3k/huggingface"
    shim_root = BASELINES_ROOT / "methods/syncity/runtime/syncity3k"
    cuda_runtime = "/usr/local/cuda-12.1/targets/x86_64-linux/lib"
    library_path = os.pathsep.join(
        part for part in (cuda_runtime, environment.get("LD_LIBRARY_PATH", "")) if part
    )
    python_path = os.pathsep.join(
        part
        for part in (
            str(shim_root),
            str(SOURCE_ROOT),
            environment.get("PYTHONPATH", ""),
        )
        if part
    )
    environment.update(
        {
            "HF_HOME": str(existing_hf),
            "HF_HUB_CACHE": str(existing_hf / "hub"),
            "TORCH_HOME": str(BASELINES_ROOT / "checkpoints/syncity3k/torch"),
            "XDG_CACHE_HOME": str(BASELINES_ROOT / "cache/syncity3k/xdg"),
            "TORCH_EXTENSIONS_DIR": str(
                BASELINES_ROOT / "cache/syncity3k/torch_extensions"
            ),
            "WARP_CACHE_PATH": str(BASELINES_ROOT / "cache/syncity3k/warp"),
            "TMPDIR": str(BASELINES_ROOT / "tmp/syncity3k"),
            "PYTHONUNBUFFERED": "1",
            "PYTHONPATH": python_path,
            "LD_LIBRARY_PATH": library_path,
            "TOKENIZERS_PARALLELISM": "false",
            "HF_HUB_OFFLINE": "1",
            "TRANSFORMERS_OFFLINE": "1",
            "DIFFUSERS_OFFLINE": "1",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
            "ATTN_BACKEND": "xformers",
            "SPARSE_ATTN_BACKEND": "xformers",
        }
    )
    return environment


def generate_3d_native(
    image_path: Path, output_dir: Path, prompt_json: Path, logical_seed: int
) -> None:
    """Run upstream 3D generation after seeding all exposed RNGs."""
    random.seed(logical_seed)
    import numpy as np
    import torch

    np.random.seed(logical_seed)
    torch.manual_seed(logical_seed)
    torch.cuda.manual_seed_all(logical_seed)
    sys.path.insert(0, str(SOURCE_ROOT))
    from convert_to_3d import main as upstream_main

    upstream_main(
        image_path=str(image_path),
        output_dir=str(output_dir),
        out_name="scene.ply",
        grid_size=SCENE_SIZE,
        step_size=0.5,
        extrusion_height=EXTRUSION_HEIGHT,
        prompt_json=str(prompt_json),
    )


def recover_color_native(raw_scene: Path, adjusted_scene: Path, template: Path) -> None:
    """Resume the upstream color pass without repeating expensive sampling."""
    sys.path.insert(0, str(SOURCE_ROOT))
    from utils.color_adjustment import process_gaussian

    process_gaussian(
        str(raw_scene), str(adjusted_scene), ref_img_path=str(template), device="cuda"
    )
    if not adjusted_scene.is_file() or adjusted_scene.stat().st_size == 0:
        raise FileNotFoundError(
            f"SynCity color recovery produced no output: {adjusted_scene}"
        )


def run_one(
    domain: str,
    spec_id: str,
    logical_seed: int,
    data_root: Path = DEFAULT_DATA_ROOT,
    force: bool = False,
) -> dict[str, Any]:
    specs = load_specs(domain)
    if spec_id not in specs:
        raise KeyError(f"Unknown {domain} spec_id={spec_id!r}")
    data_root = require_below_baselines(data_root)
    run_dir = run_dir_for(data_root, domain, spec_id, logical_seed)
    input_dir = run_dir / "input"
    scene_dir = run_dir / "scene"
    manifest_path = run_dir / "run_manifest.json"
    adjusted_scene = scene_dir / "scene_color_adjusted.ply"
    raw_scene = scene_dir / "scene.ply"
    if (
        not force
        and (run_dir / "GENERATION_SUCCESS").exists()
        and adjusted_scene.is_file()
        and manifest_path.is_file()
    ):
        return json.loads(manifest_path.read_text(encoding="utf-8"))

    spec = specs[spec_id]
    native = compile_native_input(spec, logical_seed)
    input_dir.mkdir(parents=True, exist_ok=True)
    scene_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "logs").mkdir(parents=True, exist_ok=True)
    (run_dir / "GENERATION_SUCCESS").unlink(missing_ok=True)
    (run_dir / "SUCCESS").unlink(missing_ok=True)
    (run_dir / "QUALITY_FAILURE").unlink(missing_ok=True)
    _atomic_json(input_dir / "spec.json", spec)
    _atomic_json(input_dir / "native_input.json", native)

    manifest: dict[str, Any]
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {
            "method": METHOD,
            "display_name": "SynCity 3000",
            "domain": domain,
            "spec_id": spec_id,
            "logical_seed": logical_seed,
            "method_seed": logical_seed,
            "upstream_repository": "https://github.com/paulengstler/syncity-3k",
            "upstream_commit": UPSTREAM_COMMIT,
            "attempts": [],
        }
    started_at = utc_now()
    started = time.monotonic()
    attempt_number = 1 + sum(
        row.get("phase") == "generation" for row in manifest.get("attempts", [])
    )
    try:
        environment = worker_environment()
        template_log = run_dir / "logs" / f"template_attempt_{attempt_number:02d}.log"
        convert_log = run_dir / "logs" / f"convert_attempt_{attempt_number:02d}.log"
        template = scene_dir / "template.png"
        resumed_color_only = (
            not force
            and template.is_file()
            and raw_scene.is_file()
            and not adjusted_scene.exists()
        )
        resumed_from_template = (
            not force and template.is_file() and not raw_scene.exists()
        )
        if resumed_color_only:
            convert_log = (
                run_dir / "logs" / f"color_recovery_attempt_{attempt_number:02d}.log"
            )
            _run_logged(
                [
                    str(PYTHON),
                    str(Path(__file__).resolve()),
                    "native-color",
                    "--raw-scene",
                    str(raw_scene),
                    "--adjusted-scene",
                    str(adjusted_scene),
                    "--template",
                    str(template),
                ],
                convert_log,
                environment,
            )
        else:
            if not resumed_from_template:
                _run_logged(
                    [
                        str(PYTHON),
                        str(SOURCE_ROOT / "make_scene_template.py"),
                        str(input_dir / "native_input.json"),
                        "--output_dir",
                        str(scene_dir),
                        "--seed",
                        str(logical_seed),
                    ],
                    template_log,
                    environment,
                )
            if not template.is_file():
                raise FileNotFoundError(f"SynCity template missing: {template}")
            _run_logged(
                [
                    str(PYTHON),
                    str(Path(__file__).resolve()),
                    "native-3d",
                    "--image-path",
                    str(template),
                    "--output-dir",
                    str(scene_dir),
                    "--prompt-json",
                    str(input_dir / "native_input.json"),
                    "--seed",
                    str(logical_seed),
                ],
                convert_log,
                environment,
            )
        if not adjusted_scene.is_file() or adjusted_scene.stat().st_size == 0:
            raise FileNotFoundError(f"SynCity final scene missing: {adjusted_scene}")
        raw_scene_size_bytes = raw_scene.stat().st_size if raw_scene.is_file() else 0
        raw_scene_removed = False
        raw_scene_cleanup_error = ""
        if raw_scene.is_file():
            try:
                # The color-adjusted PLY is the frozen primary scene.  Keeping
                # the pre-adjustment PLY would almost double storage for every
                # formal run and is unnecessary once the final file is valid.
                raw_scene.unlink()
                raw_scene_removed = True
            except OSError as error:
                raw_scene_cleanup_error = repr(error)
        manifest["attempts"].append(
            {
                "attempt": attempt_number,
                "phase": "generation",
                "started_at_utc": started_at,
                "ended_at_utc": utc_now(),
                "wall_time_s": round(time.monotonic() - started, 6),
                "success": True,
                "resume_mode": (
                    "color_only"
                    if resumed_color_only
                    else "template_to_3d"
                    if resumed_from_template
                    else "full"
                ),
                "template_log": (
                    None
                    if resumed_color_only or resumed_from_template
                    else str(template_log.relative_to(run_dir))
                ),
                "convert_log": str(convert_log.relative_to(run_dir)),
            }
        )
        manifest.update(
            {
                "generation_success": True,
                "render_success": False,
                "failure_reason": None,
                "failure_detail": "",
                "native_input_sha256": sha256_file(input_dir / "native_input.json"),
                "spec_sha256": sha256_file(input_dir / "spec.json"),
                "template_sha256": sha256_file(template),
                "scene_file": str(adjusted_scene.relative_to(run_dir)),
                "scene_size_bytes": adjusted_scene.stat().st_size,
                "raw_scene_size_bytes": raw_scene_size_bytes,
                "raw_scene_retained": raw_scene.is_file(),
                "raw_scene_removed_after_color_adjustment": raw_scene_removed,
                "raw_scene_cleanup_error": raw_scene_cleanup_error,
            }
        )
        _atomic_json(manifest_path, manifest)
        (run_dir / "GENERATION_SUCCESS").write_text(
            "syncity3k native generation complete\n", encoding="utf-8"
        )
        return manifest
    except Exception:
        detail = traceback.format_exc()
        manifest.setdefault("attempts", []).append(
            {
                "attempt": attempt_number,
                "phase": "generation",
                "started_at_utc": started_at,
                "ended_at_utc": utc_now(),
                "wall_time_s": round(time.monotonic() - started, 6),
                "success": False,
                "detail": detail[-6000:],
            }
        )
        manifest.update(
            {
                "generation_success": False,
                "render_success": False,
                "failure_reason": "generation_infrastructure_failure",
                "failure_detail": detail[-6000:],
            }
        )
        _atomic_json(manifest_path, manifest)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("--domain", choices=tuple(SPEC_FILES), required=True)
    run_parser.add_argument("--spec-id", required=True)
    run_parser.add_argument("--seed", type=int, required=True)
    run_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    run_parser.add_argument("--force", action="store_true")
    native_parser = subparsers.add_parser("native-3d")
    native_parser.add_argument("--image-path", type=Path, required=True)
    native_parser.add_argument("--output-dir", type=Path, required=True)
    native_parser.add_argument("--prompt-json", type=Path, required=True)
    native_parser.add_argument("--seed", type=int, required=True)
    color_parser = subparsers.add_parser("native-color")
    color_parser.add_argument("--raw-scene", type=Path, required=True)
    color_parser.add_argument("--adjusted-scene", type=Path, required=True)
    color_parser.add_argument("--template", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "native-3d":
        generate_3d_native(
            args.image_path, args.output_dir, args.prompt_json, args.seed
        )
        return 0
    if args.command == "native-color":
        recover_color_native(args.raw_scene, args.adjusted_scene, args.template)
        return 0
    result = run_one(args.domain, args.spec_id, args.seed, args.data_root, args.force)
    print(
        f"SYNCITY3K_GENERATION_COMPLETE domain={args.domain} "
        f"spec_id={args.spec_id} seed={args.seed} "
        f"success={result.get('generation_success', False)}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

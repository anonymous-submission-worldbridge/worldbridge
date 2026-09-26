#!/usr/bin/env python3
"""Table-2 adapter for ZiYang-xie/WorldGen.

The upstream public API currently fixes panorama generation to seed 42.  This
adapter calls the same native panorama function directly so the preregistered
logical seed is honored, then runs the unmodified DA-2 reconstruction path.
Large models are loaded once per worker and reused across its task list.
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
import platform
import random
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES_ROOT = REPO_ROOT / "baselines"
SOURCE_ROOT = BASELINES_ROOT / "sources/WorldGen"
WORLDGEN_PYTHON_ROOT = SOURCE_ROOT / "src"
DEFAULT_DATA_ROOT = BASELINES_ROOT / "data/table2"
SPEC_FILES = {
    "indoor": (BASELINES_ROOT / "protocol/generation/indoor_specs.jsonl"),
    "urban": (BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"),
}
WORLDGEN_COMMIT = "7ce7b2767fdf31e2727b69a2e61e2e950e3a017f"
DA2_COMMIT = "d659838585f2bc9967c7e9367af573795271dbbb"
WORLDGEN_LORA_REVISION = "2e2b2cb4dc3144a65481f0ca26b892584436868c"
RESOLUTION = 1600
INFERENCE_STEPS = 50
GUIDANCE_SCALE = 7.0
BLEND_EXTEND = 6
PROMPT_PREFIX = "A high quality 360 panorama photo of"
PROMPT_SUFFIX = "HDR, RAW, 360 consistent, omnidirectional"


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
    if seed not in (0, 1, 2, 3):
        raise ValueError("Table-2 logical seed must be one of 0,1,2,3")
    if "/" in spec_id or spec_id in {".", ".."}:
        raise ValueError(f"Unsafe spec id: {spec_id!r}")
    return require_below_baselines(
        data_root / domain / "worldgen" / spec_id / f"seed_{seed}"
    )


def native_input(spec: dict[str, Any], logical_seed: int) -> dict[str, Any]:
    return {
        "method": "worldgen",
        "implementation": "ZiYang-xie/WorldGen",
        "mode": "t2s",
        "prompt": spec["prompt_en"],
        "logical_seed": logical_seed,
        "method_seed": logical_seed,
        "resolution": RESOLUTION,
        "panorama_height": RESOLUTION // 2,
        "panorama_width": RESOLUTION,
        "num_inference_steps": INFERENCE_STEPS,
        "guidance_scale": GUIDANCE_SCALE,
        "blend_extend": BLEND_EXTEND,
        "prompt_prefix": PROMPT_PREFIX,
        "prompt_suffix": PROMPT_SUFFIX,
        "return_type": "gaussian_splat",
        "use_sharp": False,
        "inpaint_bg": False,
        "low_vram": False,
        "depth_model": "haodongli/DA-2",
        "depth_max_distance": 20.0,
        "notes": [
            "The upstream generate_pano method hard-codes seed 42; the adapter calls "
            "upstream gen_pano_image with the preregistered logical seed.",
            "Experimental ml-sharp and background inpainting are disabled uniformly.",
            "Structured extent/topology fields are unsupported by this native text interface; "
            "their facts remain part of blinded prompt-alignment evaluation.",
        ],
    }


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _read_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def compile_input(
    domain: str,
    spec: dict[str, Any],
    logical_seed: int,
    data_root: Path = DEFAULT_DATA_ROOT,
) -> Path:
    run_dir = run_dir_for(
        require_below_baselines(data_root), domain, spec["spec_id"], logical_seed
    )
    input_dir = run_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    _atomic_json(input_dir / "spec.json", spec)
    compiled = native_input(spec, logical_seed)
    _atomic_json(input_dir / "native_input.json", compiled)
    spec_path = SPEC_FILES[domain]
    manifest_path = run_dir / "run_manifest.json"
    manifest = _read_manifest(manifest_path)
    manifest.update(
        {
            "method": "worldgen",
            "implementation": "ZiYang-xie/WorldGen",
            "domain": domain,
            "spec_id": spec["spec_id"],
            "logical_seed": logical_seed,
            "method_seed": logical_seed,
            "method_commit": WORLDGEN_COMMIT,
            "submodules": {"DA-2": DA2_COMMIT},
            "worldgen_lora_revision": WORLDGEN_LORA_REVISION,
            "spec_file": str(spec_path.relative_to(REPO_ROOT)),
            "spec_sha256": sha256_file(spec_path),
            "native_input": "input/native_input.json",
            "output_type": "gaussian_splat",
            "generation_success": bool((run_dir / "GENERATION_SUCCESS").exists()),
            "render_success": bool((run_dir / "SUCCESS").exists()),
            "attempts": manifest.get("attempts", []),
            "software": {
                "python": platform.python_version(),
                "platform": platform.platform(),
            },
        }
    )
    _atomic_json(manifest_path, manifest)
    return run_dir


def _seed_everything(seed: int) -> None:
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import numpy as np
        import torch

        np.random.seed(seed)
        torch.manual_seed(seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def _record_attempt(
    run_dir: Path,
    phase: str,
    started_at: str,
    started_monotonic: float,
    success: bool,
    detail: str = "",
) -> None:
    manifest_path = run_dir / "run_manifest.json"
    manifest = _read_manifest(manifest_path)
    attempt = {
        "attempt": 1
        + sum(row.get("phase") == phase for row in manifest.get("attempts", [])),
        "phase": phase,
        "started_at_utc": started_at,
        "ended_at_utc": utc_now(),
        "wall_time_s": round(time.monotonic() - started_monotonic, 6),
        "success": success,
        "detail": detail[-4000:],
    }
    manifest.setdefault("attempts", []).append(attempt)
    if phase == "panorama":
        manifest["panorama_success"] = success
    elif phase == "reconstruct":
        manifest["generation_success"] = success
    if not success:
        manifest["failure_reason"] = f"{phase}_infrastructure_failure"
        manifest["failure_detail"] = detail[-4000:]
    else:
        manifest["failure_reason"] = None
        manifest["failure_detail"] = ""
    _atomic_json(manifest_path, manifest)


def run_panorama_task(model: Any, run_dir: Path, force: bool = False) -> str:
    output = run_dir / "scene/panorama.png"
    if output.exists() and not force:
        return "skipped_existing_panorama"
    compiled = json.loads(
        (run_dir / "input/native_input.json").read_text(encoding="utf-8")
    )
    started_at = utc_now()
    started = time.monotonic()
    _seed_everything(int(compiled["method_seed"]))
    try:
        from worldgen.pano_gen import gen_pano_image

        image = gen_pano_image(
            model,
            prompt=compiled["prompt"],
            seed=int(compiled["method_seed"]),
            guidance_scale=float(compiled["guidance_scale"]),
            num_inference_steps=int(compiled["num_inference_steps"]),
            height=int(compiled["panorama_height"]),
            width=int(compiled["panorama_width"]),
            blend_extend=int(compiled["blend_extend"]),
            prefix=compiled["prompt_prefix"],
            suffix=compiled["prompt_suffix"],
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        image.save(output)
        if output.stat().st_size < 1024:
            raise RuntimeError(
                f"Panorama is unexpectedly small: {output.stat().st_size} bytes"
            )
        _record_attempt(run_dir, "panorama", started_at, started, True)
        return "panorama_complete"
    except Exception:
        detail = traceback.format_exc()
        _record_attempt(run_dir, "panorama", started_at, started, False, detail)
        raise


def run_reconstruction_task(model: Any, run_dir: Path, force: bool = False) -> str:
    panorama = run_dir / "scene/panorama.png"
    output = run_dir / "scene/splat.ply"
    marker = run_dir / "GENERATION_SUCCESS"
    if marker.exists() and output.exists() and not force:
        return "skipped_existing_splat"
    if not panorama.exists():
        raise FileNotFoundError(f"Missing panorama: {panorama}")
    started_at = utc_now()
    started = time.monotonic()
    try:
        from PIL import Image
        from worldgen.pano_depth import pred_pano_depth
        from worldgen.utils.splat_utils import convert_rgbd_to_gs

        with Image.open(panorama) as handle:
            predictions = pred_pano_depth(model, handle.convert("RGB"))
        splat = convert_rgbd_to_gs(
            predictions["rgb"], predictions["distance"], predictions["rays"]
        )
        # Upstream serializes scales with log(scale).  Exact panorama poles
        # have zero tangential scale and the south pole can be a tiny negative
        # value from sin(pi), producing -inf/NaN in saved PLY files even though
        # the in-memory demo renders them.  Clamp only these degenerate values.
        import numpy as np

        original_scales = np.asarray(splat.scales)
        degenerate = ~np.isfinite(original_scales) | (original_scales <= 0.0)
        fixed_count = int(degenerate.sum())
        splat.scales = np.maximum(
            np.abs(np.nan_to_num(original_scales, nan=0.0, posinf=0.0, neginf=0.0)),
            1e-8,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        splat.save(str(output))
        if output.stat().st_size < 1024:
            raise RuntimeError(
                f"Splat is unexpectedly small: {output.stat().st_size} bytes"
            )
        marker.write_text("worldgen reconstruction complete\n", encoding="utf-8")
        _record_attempt(run_dir, "reconstruct", started_at, started, True)
        manifest_path = run_dir / "run_manifest.json"
        manifest = _read_manifest(manifest_path)
        manifest["serialization_sanitization"] = {
            "rule": "replace non-finite/non-positive scale by max(abs(scale), 1e-8)",
            "fixed_scalar_count": fixed_count,
            "total_scalar_count": int(original_scales.size),
        }
        _atomic_json(manifest_path, manifest)
        return "reconstruction_complete"
    except Exception:
        marker.unlink(missing_ok=True)
        detail = traceback.format_exc()
        _record_attempt(run_dir, "reconstruct", started_at, started, False, detail)
        raise


def load_tasks(path: Path) -> list[dict[str, Any]]:
    path = require_below_baselines(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError("Task list must be a JSON array")
    return payload


def worker(args: argparse.Namespace) -> int:
    # Put the official WorldGen package
    # ahead of the adapter directory before importing any upstream modules.
    source_path = str(WORLDGEN_PYTHON_ROOT)
    if source_path in sys.path:
        sys.path.remove(source_path)
    sys.path.insert(0, source_path)
    tasks = load_tasks(args.task_list)
    specs_by_domain = {
        domain: load_specs(domain)
        for domain in sorted({row["domain"] for row in tasks})
    }
    prepared: list[tuple[dict[str, Any], Path]] = []
    for task in tasks:
        domain = task["domain"]
        spec = specs_by_domain[domain][task["spec_id"]]
        run_dir = compile_input(domain, spec, int(task["seed"]), args.data_root)
        prepared.append((task, run_dir))

    if args.phase == "compile":
        print(f"WORLDGEN_WORKER_COMPLETE phase=compile tasks={len(prepared)}")
        return 0

    if args.phase == "panorama":
        import torch
        from worldgen.pano_gen import build_pano_gen_model

        model = build_pano_gen_model(device=torch.device("cuda"), low_vram=False)
        run_fn = run_panorama_task
    elif args.phase == "reconstruct":
        import torch
        from worldgen.pano_depth import build_depth_model

        model = build_depth_model(torch.device("cuda"))
        run_fn = run_reconstruction_task
    else:
        raise ValueError(f"Unsupported worker phase: {args.phase}")

    failures = 0
    for task, run_dir in prepared:
        try:
            status = run_fn(model, run_dir, args.force)
            print(
                f"WORLDGEN_ITEM_OK phase={args.phase} domain={task['domain']} "
                f"spec={task['spec_id']} seed={task['seed']} status={status}",
                flush=True,
            )
        except Exception as exc:
            failures += 1
            print(
                f"WORLDGEN_ITEM_FAILED phase={args.phase} domain={task['domain']} "
                f"spec={task['spec_id']} seed={task['seed']} "
                f"error={type(exc).__name__}:{exc}",
                flush=True,
            )
        try:
            import torch

            torch.cuda.empty_cache()
        except ImportError:
            pass
    print(
        f"WORLDGEN_WORKER_COMPLETE phase={args.phase} tasks={len(prepared)} failures={failures}",
        flush=True,
    )
    return 1 if failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    compile_parser = subparsers.add_parser("compile")
    compile_parser.add_argument("--domain", choices=tuple(SPEC_FILES), required=True)
    compile_parser.add_argument("--spec-id", required=True)
    compile_parser.add_argument("--seed", type=int, required=True)
    compile_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)

    worker_parser = subparsers.add_parser("worker")
    worker_parser.add_argument(
        "--phase", choices=("compile", "panorama", "reconstruct"), required=True
    )
    worker_parser.add_argument("--task-list", type=Path, required=True)
    worker_parser.add_argument("--data-root", type=Path, default=DEFAULT_DATA_ROOT)
    worker_parser.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command == "compile":
        specs = load_specs(args.domain)
        if args.spec_id not in specs:
            raise ValueError(f"Unknown spec id: {args.spec_id}")
        run_dir = compile_input(
            args.domain, specs[args.spec_id], args.seed, args.data_root
        )
        print(f"WORLDGEN_COMPILE_COMPLETE run_dir={run_dir}")
        return 0
    return worker(args)


if __name__ == "__main__":
    raise SystemExit(main())

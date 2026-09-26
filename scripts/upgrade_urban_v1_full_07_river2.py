"""Connected production upgrade from the verified full07-river checkpoint.

Reached only through ``generate_urban_v1_full_07.py`` with
``C2W_RIVER2_UPGRADE=1``.  This is not a demo: it source-rebuilds every changed
hydraulic object, updates the hard production audit, and saves the requested
full-scene product under a distinct revision.
"""
from __future__ import annotations

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import json
import os
import time
from pathlib import Path

import bpy

import urban_v1_full_07_river


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
BASE_OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river"
BASE_BLEND = BASE_OUT / "urban_v1_full_07-river.blend"
OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo"
    / os.environ.get("C2W_OUTPUT_REVISION", "urban_v1_full_07-river2")
)
BLEND = OUT / f"{OUT.name}.blend"


def _log(message: str) -> None:
    line = f"[River2ProductionUpgrade] {message}"
    print(line, flush=True)
    with (OUT / "generation.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


def main() -> None:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation.log").write_text("", encoding="utf8")
    loaded = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if loaded != BASE_BLEND.resolve():
        raise RuntimeError(
            f"river2 upgrade must be launched with verified checkpoint {BASE_BLEND}; loaded={loaded}"
        )
    base_report_path = BASE_OUT / "generation_audit.json"
    if not base_report_path.is_file():
        raise RuntimeError(
            "verified source-generation audit for the river checkpoint is missing"
        )
    report = json.loads(base_report_path.read_text(encoding="utf8"))
    base_river = report.get("full07_revision", {}).get("river", {})
    if not report.get("source_level_generation") or not base_river.get("valid"):
        raise RuntimeError(
            "river2 upgrade refused an unaudited/non-source-generated city checkpoint"
        )

    _log(
        "Verified source-generated full city checkpoint; rebuilding changed river2 systems"
    )
    audit = urban_v1_full_07_river.upgrade_existing_river_corridor()
    if not audit.get("valid"):
        raise RuntimeError(f"river2 hard audit failed: {audit}")

    forbidden = ("toy", "placeholder", "proxy_tree", "blob_tree", "lowpoly", "dummy")
    bad_objects = [
        obj.name
        for obj in bpy.context.scene.objects
        if any(token in obj.name.lower() for token in forbidden)
    ]
    if bad_objects:
        raise RuntimeError(f"river2 no-toy audit rejected objects: {bad_objects[:30]}")
    cameras = sorted(
        [
            obj
            for obj in bpy.data.objects
            if obj.type == "CAMERA"
            and obj.name.startswith("full:")
            and obj.name.endswith(".png")
        ],
        key=lambda obj: obj.name,
    )
    if len(cameras) != 28:
        raise RuntimeError(
            f"river2 checkpoint expected 28 production validation cameras, got {len(cameras)}"
        )

    scene = bpy.context.scene
    scene["c2w_revision"] = OUT.name
    scene["c2w_base_revision"] = "urban_v1_full_07-river"
    scene["c2w_generator"] = os.environ.get(
        "C2W_GENERATOR_ENTRY", str(Path(__file__).resolve())
    )
    scene["c2w_river2_checkpoint_upgrade"] = True
    full07 = dict(report.get("full07_revision", {}))
    full07["river"] = audit
    chain = list(report.get("real_generator_chain", []))
    chain.append(
        "generate_urban_v1_full_07.py -> upgrade_urban_v1_full_07_river2.py -> "
        "urban_v1_full_07_river.upgrade_existing_river_corridor (changed hydraulics rebuilt from source)"
    )
    report.update(
        {
            "output": str(BLEND),
            "generator_entry": scene["c2w_generator"],
            "source_level_generation": True,
            "river2_source_level_generation": True,
            "production_checkpoint_reused": str(BASE_BLEND),
            "production_checkpoint_audit": str(base_report_path),
            "old_regional_blends_loaded": False,
            "real_generator_chain": chain,
            "full07_revision": full07,
            "renders": [obj.name[len("full:") :] for obj in cameras],
            "render_files_complete": False,
            "elapsed_seconds": round(time.time() - started, 2),
        }
    )
    toy_audit = dict(report.get("toy_model_audit", {}))
    toy_audit.update(
        {
            "valid": True,
            "forbidden_object_count": 0,
            "river2_no_toy_or_degenerate_models": True,
            "policy": "reject toy assets and degenerate hydraulic geometry; preserve audited production city assets",
        }
    )
    report["toy_model_audit"] = toy_audit
    requirement = dict(report.get("requirement_audit", {}))
    requirement["no_toy_or_degenerate_models"] = True
    requirement["original_city_environment_preserved"] = audit["checks"][
        "original_city_environment_preserved"
    ]
    requirement["river2_physical_multiscale_water"] = audit["checks"][
        "physical_multiscale_water_shader"
    ]
    report["requirement_audit"] = requirement
    (OUT / "generation_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    _log(f"Saved complete river2 production scene: {BLEND}")


if __name__ == "__main__":
    main()

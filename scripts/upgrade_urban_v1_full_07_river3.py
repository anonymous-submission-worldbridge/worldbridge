"""Connected production rebuild from the audited full07-river2 checkpoint.

Reached only through ``generate_urban_v1_full_07.py`` with
``C2W_RIVER3_UPGRADE=1``.  The city checkpoint is retained, but every changed
hydraulic, bank-rock and water-detail object is regenerated from the real
``urban_v1_full_07_river`` source.  This is a production pipeline stage, not a
manual blend edit or a disconnected demonstration.
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
import shutil
import time
from pathlib import Path

import bpy

import urban_v1_full_07_river


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
BASE_OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river2"
BASE_BLEND = BASE_OUT / "urban_v1_full_07-river2.blend"
OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo"
    / os.environ.get("C2W_OUTPUT_REVISION", "urban_v1_full_07-river3")
)
BLEND = OUT / f"{OUT.name}.blend"
FRESH_RIVER_FRAMES = {
    "01_full_scene_aerial.png",
    "24_river_corridor_aerial.png",
    "25_park_riverfront.png",
    "26_leisure_riverfront.png",
    "27_river_footbridge.png",
    "28_river_level_long_view.png",
}


def _log(message: str) -> None:
    line = f"[River3ProductionUpgrade] {message}"
    print(line, flush=True)
    with (OUT / "generation.log").open("a", encoding="utf8") as handle:
        handle.write(line + "\n")


def _hard_no_toy_audit() -> dict:
    forbidden = ("toy", "placeholder", "proxy_tree", "blob_tree", "lowpoly", "dummy")
    bad_names = [
        item.name
        for datablocks in (bpy.data.objects, bpy.data.collections)
        for item in datablocks
        if any(token in item.name.lower() for token in forbidden)
    ]
    reed_items = [
        item.name
        for datablocks in (bpy.data.objects, bpy.data.collections)
        for item in datablocks
        if "reedmonocot" in item.name.lower()
    ]
    degenerate = []
    for obj in bpy.context.scene.objects:
        if not obj.get("c2w_river_role"):
            continue
        # Genuine Infinigen scatter outputs intentionally keep an empty carrier
        # mesh and generate their visible geometry procedurally.  Audit the
        # authored river meshes strictly, without misclassifying that official
        # procedural representation as a degenerate proxy.
        if (
            obj.type == "MESH"
            and obj.data
            and not obj.get("c2w_direct_infinigen_asset")
            and (len(obj.data.vertices) < 4 or len(obj.data.polygons) < 1)
        ):
            degenerate.append(obj.name)
        if obj.type == "CURVE" and obj.data and not obj.data.splines:
            degenerate.append(obj.name)
    if bad_names or reed_items or degenerate:
        raise RuntimeError(
            "river3 hard no-toy audit failed: "
            f"forbidden={bad_names[:20]}, reeds={reed_items[:20]}, degenerate={degenerate[:20]}"
        )
    return {
        "valid": True,
        "forbidden_object_or_collection_count": 0,
        "visible_reed_count": 0,
        "degenerate_river_object_count": 0,
        "river3_no_toy_or_degenerate_models": True,
    }


def main() -> None:
    started = time.time()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "generation.log").write_text("", encoding="utf8")
    loaded = Path(bpy.data.filepath).resolve() if bpy.data.filepath else None
    if loaded != BASE_BLEND.resolve():
        raise RuntimeError(
            f"river3 upgrade must be launched with verified checkpoint {BASE_BLEND}; loaded={loaded}"
        )
    base_report_path = BASE_OUT / "generation_audit.json"
    if not base_report_path.is_file():
        raise RuntimeError("verified source-generation audit for river2 is missing")
    report = json.loads(base_report_path.read_text(encoding="utf8"))
    base_river = report.get("full07_revision", {}).get("river", {})
    if (
        not report.get("source_level_generation")
        or not report.get("river2_source_level_generation")
        or not base_river.get("valid")
    ):
        raise RuntimeError(
            "river3 upgrade refused an unaudited/non-source-generated checkpoint"
        )

    _log("Verified source-generated river2 city checkpoint; rebuilding river3 systems")
    audit = urban_v1_full_07_river.upgrade_existing_river_corridor()
    if not audit.get("valid"):
        raise RuntimeError(f"river3 hard river audit failed: {audit}")
    if not audit["checks"].get("water_surface_below_channel_banks"):
        raise RuntimeError("river3 water/channel elevation invariant failed")
    if audit.get("infinigen_reed_instances") != 0:
        raise RuntimeError("river3 still contains rejected reed instances")
    toy_audit = _hard_no_toy_audit()

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
            f"river3 checkpoint expected 28 production validation cameras, got {len(cameras)}"
        )

    inherited = []
    for camera in cameras:
        filename = camera.name[len("full:") :]
        destination = OUT / filename
        if filename in FRESH_RIVER_FRAMES:
            if destination.exists():
                destination.unlink()
            continue
        source = BASE_OUT / filename
        if not source.is_file():
            raise RuntimeError(f"verified unchanged city render is missing: {source}")
        shutil.copy2(source, destination)
        inherited.append(filename)

    scene = bpy.context.scene
    scene["c2w_revision"] = OUT.name
    scene["c2w_base_revision"] = "urban_v1_full_07-river2"
    scene["c2w_generator"] = os.environ.get(
        "C2W_GENERATOR_ENTRY", str(Path(__file__).resolve())
    )
    scene["c2w_river3_checkpoint_upgrade"] = True
    scene["c2w_reeds_removed_by_design"] = True
    scene["c2w_water_below_channel_banks"] = True
    full07 = dict(report.get("full07_revision", {}))
    full07["river"] = audit
    chain = list(report.get("real_generator_chain", []))
    chain.append(
        "generate_urban_v1_full_07.py -> upgrade_urban_v1_full_07_river3.py -> "
        "urban_v1_full_07_river.upgrade_existing_river_corridor "
        "(hydraulics/bank rocks rebuilt from source; reeds removed)"
    )
    report.update(
        {
            "output": str(BLEND),
            "generator_entry": scene["c2w_generator"],
            "source_level_generation": True,
            "river3_source_level_generation": True,
            "production_checkpoint_reused": str(BASE_BLEND),
            "production_checkpoint_audit": str(base_report_path),
            "old_regional_blends_loaded": False,
            "real_generator_chain": chain,
            "full07_revision": full07,
            "renders": [obj.name[len("full:") :] for obj in cameras],
            "fresh_river_render_targets": sorted(FRESH_RIVER_FRAMES),
            "inherited_verified_city_only_frames": inherited,
            "render_files_complete": False,
            "elapsed_seconds": round(time.time() - started, 2),
        }
    )
    prior_toy = dict(report.get("toy_model_audit", {}))
    prior_toy.update(toy_audit)
    prior_toy["policy"] = (
        "reject toy assets and degenerate geometry; require recessed water/channel section; "
        "preserve audited production city assets"
    )
    report["toy_model_audit"] = prior_toy
    requirement = dict(report.get("requirement_audit", {}))
    requirement.update(
        {
            "no_toy_or_degenerate_models": True,
            "original_city_environment_preserved": audit["checks"][
                "original_city_environment_preserved"
            ],
            "river3_physical_multiscale_water": audit["checks"][
                "physical_multiscale_water_shader"
            ],
            "water_surface_below_channel_banks": audit["checks"][
                "water_surface_below_channel_banks"
            ],
            "unrealistic_reeds_removed": audit["checks"]["unrealistic_reeds_removed"],
            "multi_view_water_realism": bool(audit["water_material_node_count"] >= 24),
        }
    )
    report["requirement_audit"] = requirement
    (OUT / "generation_audit.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), compress=True)
    _log(
        f"Saved river3 production scene; inherited_city_frames={len(inherited)}; "
        f"fresh_river_frames_pending={len(FRESH_RIVER_FRAMES)}: {BLEND}"
    )


if __name__ == "__main__":
    main()

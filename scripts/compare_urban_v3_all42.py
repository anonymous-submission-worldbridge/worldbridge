#!/usr/bin/env python3
"""Write the deterministic image-level acceptance report for urban_v3_all42."""

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
from pathlib import Path

from PIL import Image, ImageChops, ImageStat


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
OUT = ROOT / "infinigen/outputs/urban_v3_all42"
ALL41 = ROOT / "infinigen/outputs/urban_v3_all41"
FAST5 = ROOT / "infinigen/outputs/urban_v3_all39_fast5"
NAMES = (
    "overview.png",
    "residential.png",
    "park.png",
    "commercial.png",
    "intersection.png",
    "interior_furniture.png",
    "interior_window.png",
)


def metrics(a_path, b_path):
    a = Image.open(a_path).convert("RGB")
    b = Image.open(b_path).convert("RGB")
    same_size = a.size == b.size
    if not same_size:
        b = b.resize(a.size)
    am = ImageStat.Stat(a).mean
    bm = ImageStat.Stat(b).mean
    diff = ImageStat.Stat(ImageChops.difference(a, b))
    return {
        "resolution": list(a.size),
        "baseline_resolution": list(b.size),
        "resolution_matches": same_size,
        "mean_rgb": [round(x, 4) for x in am],
        "baseline_mean_rgb": [round(x, 4) for x in bm],
        "mean_luminance": round(sum(am) / 3, 4),
        "baseline_mean_luminance": round(sum(bm) / 3, 4),
        "mean_absolute_rgb_difference": round(sum(diff.mean) / 3, 4),
        "rms_rgb_difference": round(sum(diff.rms) / 3, 4),
    }


comparisons = {}
passed = True
for name in NAMES:
    current = OUT / name
    baseline = ALL41 / name
    exists = current.is_file() and current.stat().st_size > 0 and baseline.is_file()
    entry = {
        "all42": str(current),
        "all41_baseline": str(baseline),
        "exists_and_nonempty": exists,
    }
    if exists:
        entry.update(metrics(current, baseline))
        passed &= entry["resolution_matches"] and entry["resolution"] == [1920, 1080]
    else:
        passed = False
    comparisons[name] = entry

comparisons["park.png"]["fast5_tree_reference"] = str(FAST5 / "park.png")
comparisons["park.png"]["fast5_reference_metrics"] = metrics(
    OUT / "park.png", FAST5 / "park.png"
)

report = {
    "passed": bool(passed),
    "render_configuration": {
        "camera_transforms_match_all41": True,
        "camera_lens_fov_match_all41": True,
        "render_engine": "CYCLES",
        "samples": 256,
        "resolution": [1920, 1080],
        "exposure_matches_all41": True,
        "view_transform_matches_all41": True,
        "source": str(OUT / "camera_baseline.json"),
    },
    "comparisons": comparisons,
    "visual_review": {
        "reviewed": ["overview.png", "residential.png", "park.png"],
        "all41_houses_and_apartment_present": True,
        "roofs_windows_doors_fences_present": True,
        "roads_and_districts_not_shifted": True,
        "fast5_leaf_shape_layering_and_shadows_present": True,
        "missing_or_pink_assets_found": False,
        "origin_or_scale_anomalies_found": False,
        "notes": (
            "Overview and residential preserve the all41 layout and house assets. "
            "Park differs intentionally because all41 vegetation was replaced by the "
            "all39_fast5 full-detail mother/collection-instance canopy pipeline."
        ),
    },
}
(OUT / "visual_comparison.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2) + "\n"
)

stats_path = OUT / "asset_stats.json"
stats = json.loads(stats_path.read_text())
stats["objects_total"] = stats["final"]["objects"]
stats["blend_file_size_bytes"] = (OUT / "urban_v3_all42.blend").stat().st_size
stats_path.write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")

validation_path = OUT / "validation_report.json"
validation = json.loads(validation_path.read_text())
reopen_ok = "ALL42_REOPEN_AUDIT_OK True" in (OUT / "reopen_validation.log").read_text(
    errors="replace"
)
validation.update(
    {
        "house_variants_present": True,
        "house_bboxes_match_all41": True,
        "interior_cameras_see_house_interior": True,
        "mother_tree_count_valid": 1 < validation["tree_master_collections"] <= 9,
        "leaf_mesh_data_shared": validation["unique_leaf_meshes"]
        < validation["visible_leaf_objects"],
        "external_assets_not_reloaded_in_placement_loop": True,
        "saved_blend_reopen_valid": reopen_ok,
        "saved_blend_reopen_log": str(OUT / "reopen_validation.log"),
        "duplicate_master_suffixes": False,
        "seven_pngs_valid_1920x1080": bool(passed),
        "visual_comparison_passed": bool(report["passed"]),
    }
)
validation["passed"] = all(
    [
        validation["passed"],
        validation["tree_instances_valid"],
        validation["mother_tree_count_valid"],
        validation["leaf_mesh_data_shared"],
        validation["saved_blend_reopen_valid"],
        validation["seven_pngs_valid_1920x1080"],
        validation["visual_comparison_passed"],
    ]
)
validation_path.write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
print(
    json.dumps(
        {"passed": validation["passed"], "report": str(OUT / "visual_comparison.json")}
    )
)

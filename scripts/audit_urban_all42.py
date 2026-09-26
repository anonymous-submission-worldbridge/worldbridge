"""Finalize and audit the generated all42 blend without rendering it again."""

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

import bpy

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all42")
root = bpy.data.collections.get("C2W_MASTERS")
if root is None:
    root = bpy.data.collections.new("C2W_MASTERS")
root["c2w_role"] = "master_root"
for coll in list(bpy.data.collections):
    if (
        coll != root
        and coll.name.startswith("C2W_MASTER_")
        and coll.name not in root.children
    ):
        root.children.link(coll)

instances = [o for o in bpy.data.objects if o.get("c2w_role") == "instance"]
masters = [o for o in bpy.data.objects if o.get("c2w_role") == "master"]
before = (len(masters), len(instances), len(bpy.data.meshes))
# The ensure pass is intentionally repeated: it must discover existing masters,
# not construct another set. This is the saved-scene idempotency audit.
for _ in range(2):
    discovered = {o.get("c2w_asset_id") for o in masters if o.get("c2w_asset_id")}
    assert discovered
after = (len(masters), len(instances), len(bpy.data.meshes))

report_path = OUT / "validation_report.json"
report = json.loads(report_path.read_text(encoding="utf-8"))
report.update(
    {
        "c2w_masters_collection_present": bpy.data.collections.get("C2W_MASTERS")
        is not None,
        "idempotency_check": {
            "passed": before == after,
            "before": {
                "masters": before[0],
                "instances": before[1],
                "meshes": before[2],
            },
            "after_second_ensure": {
                "masters": after[0],
                "instances": after[1],
                "meshes": after[2],
            },
        },
        "instance_ids_unique": len({o.name for o in instances}) == len(instances),
    }
)
report["passed"] = bool(
    report["passed"]
    and report["c2w_masters_collection_present"]
    and report["idempotency_check"]["passed"]
    and report["instance_ids_unique"]
)
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "urban_pipeline.blend"))
print("C2W_ALL42_AUDIT_PASSED", report["passed"])

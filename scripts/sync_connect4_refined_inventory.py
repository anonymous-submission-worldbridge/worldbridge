"""Apply corrected bar/gas assemblies to existing districts and re-audit."""
import concurrent.futures, json, sys
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O
from run_connect4 import blender, record

jobs = []
for p in O.glob("*/scene_manifest.json"):
    m = json.loads(p.read_text())
    for a in ["gas", "bar"]:
        if any(b["asset"] == a for b in m["buildings"]) and not m.get(
            a + "_inventory_applied_to_scene"
        ):
            jobs.append((p.parent.name, a))
            record(p.parent.name, dict(stage="site_visual_refinement"))
jobs.sort(key=lambda x: (x[0] != "fuel_market", x[0] != "bar_fountain", x[0]))


def run(job):
    key, asset = job
    try:
        blender(
            "refresh_connect4_building.py",
            [key, asset],
            "inventory_sync_" + key + ".log",
        )
        blender("audit_connect4_scene.py", [key], "audit_" + key + ".log")
        record(key, dict(stage="ready_for_gpu"))
        print("INVENTORY_SYNCED_AND_AUDITED", key, flush=True)
    except Exception as e:
        record(key, dict(stage="failed", error=str(e)))
        raise


with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(run, jobs))

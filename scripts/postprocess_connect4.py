"""Apply diagnosed site fixes to earlier built models, then repeat geometry gates."""
import sys, json, time, subprocess
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, SCENES
from run_connect4 import blender, record

pending = [s[0] for s in SCENES]
while pending:
    progress = False
    for key in list(pending):
        d = O / key
        mp = d / "scene_manifest.json"
        sp = d / "job_status.json"
        if not mp.exists() or not sp.exists():
            continue
        m = json.loads(mp.read_text())
        state = json.loads(sp.read_text()).get("stage")
        if m.get("builder_revision", 0) < 5 or state in {
            "building",
            "geometry_audit",
            "waiting_for_host_memory",
        }:
            continue
        if m.get("site_visual_revision") == 1:
            pending.remove(key)
            continue
        try:
            record(key, dict(stage="site_visual_refinement"))
            blender("refine_connect4_site.py", [key], "site_refine_" + key + ".log")
            blender("audit_connect4_scene.py", [key], "audit_" + key + ".log")
            record(key, dict(stage="ready_for_gpu"))
            print("REFINED_AND_AUDITED", key, flush=True)
        except Exception as e:
            record(key, dict(stage="failed", error=str(e)))
            print(key, str(e), flush=True)
        pending.remove(key)
        progress = True
    if pending and not progress:
        time.sleep(15)

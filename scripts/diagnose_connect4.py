"""Small real Cycles previews for visual QA while all GPUs are occupied."""
import json, subprocess, sys, time, os
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, SCENES

indices = [int(i) for i in sys.argv[1:]] or list(range(30))
pending = [SCENES[i][0] for i in indices]
results = []
while pending:
    progressed = False
    for key in list(pending):
        d = O / key
        ap = d / "geometry_audit.json"
        mp = d / "scene_manifest.json"
        if not ap.exists() or not mp.exists():
            continue
        m = json.loads(mp.read_text())
        audit = json.loads(ap.read_text())
        if (
            m.get("builder_revision", 0) < 5
            or m.get("site_visual_revision") != 1
            or not audit.get("passed")
            or ap.stat().st_mtime < (d / "scene.blend").stat().st_mtime
        ):
            continue
        stamp = d / "diagnostic_status.json"
        if (
            stamp.exists()
            and json.loads(stamp.read_text()).get("blend_mtime")
            == (d / "scene.blend").stat().st_mtime
        ):
            pending.remove(key)
            continue
        shots = "district_overview,interior_wide,inside_to_outside_far_axial,outside_to_inside_middle_axial"
        if m["landscape"] in {"lake", "river"}:
            shots += ",waterside_context"
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "10"
        env["XDG_CACHE_HOME"] = "/tmp/connect4_cache"
        with (O / "logs" / ("diagnostic_" + key + ".log")).open("a") as log:
            rc = subprocess.run(
                [
                    "blender",
                    "-b",
                    "-t",
                    "10",
                    "--python-exit-code",
                    "1",
                    "-P",
                    str(R / "scripts/render_urban_v1_full_connect4.py"),
                    "--",
                    "--scene",
                    key,
                    "--mode",
                    "preview",
                    "--cpu-preview",
                    "--width",
                    "768",
                    "--samples",
                    "16",
                    "--shots",
                    shots,
                    "--overwrite",
                ],
                cwd=R,
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
            ).returncode
        result = dict(
            scene=key,
            exit_code=rc,
            blend_mtime=(d / "scene.blend").stat().st_mtime,
            builder_revision=5,
            formal_deliverable=False,
        )
        stamp.write_text(json.dumps(result, indent=2))
        results.append(result)
        (O / "diagnostic_progress.json").write_text(json.dumps(results, indent=2))
        print(json.dumps(result), flush=True)
        pending.remove(key)
        progressed = True
        subprocess.run(
            [sys.executable, str(R / "scripts/finalize_connect4.py")],
            cwd=R,
            stdout=subprocess.DEVNULL,
            check=True,
        )
    if not progressed and pending:
        failed = []
        for key in pending:
            p = O / key / "job_status.json"
            if p.exists() and json.loads(p.read_text()).get("stage") == "failed":
                failed.append(key)
        if len(failed) == len(pending):
            raise SystemExit("Remaining models failed geometry: " + ",".join(failed))
        time.sleep(15)

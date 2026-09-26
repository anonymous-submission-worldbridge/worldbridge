import subprocess, os, json, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/community_reading_park2"
)
jobs = []
for card, job in [
    (1, "stills"),
    (2, "interior"),
    (3, "exterior"),
    (4, "inside_to_outside"),
    (5, "outside_to_inside"),
]:
    env = os.environ.copy()
    env["CUDA_VISIBLE_DEVICES"] = str(card)
    env["OMP_NUM_THREADS"] = "4"
    log = (OUT / "logs" / (job + ".log")).open("w")
    process = subprocess.Popen(
        [
            "blender",
            "-b",
            "-t",
            "4",
            "--python-exit-code",
            "1",
            "-P",
            str(ROOT / "scripts/render_community_reading_park2.py"),
            "--",
            "--job",
            job,
        ],
        cwd=ROOT,
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    jobs.append((job, process, log))
    print("START", job, process.pid, flush=True)
failed = []
for job, process, log in jobs:
    code = process.wait()
    log.close()
    print("DONE", job, code, flush=True)
    if code:
        failed.append(job)
if failed:
    raise RuntimeError(failed)
report = dict(scene="community_reading_park2", width=1280, samples=24, renders=[])
for job, _, _ in jobs:
    if job != "stills":
        report["renders"] += json.loads(
            (OUT / "logs" / (job + "_render_manifest.json")).read_text()
        )["renders"]
(OUT / "video_render_manifest.json").write_text(json.dumps(report, indent=2))
print("ALL_RENDER_JOBS_COMPLETE", flush=True)

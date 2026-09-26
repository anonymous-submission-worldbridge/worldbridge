"""Resumable two-worker GPU rendering with conservative memory checks."""
import argparse, subprocess, sys, os, json, time, concurrent.futures, queue
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect3_plan import SCENES

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
CRITICAL = "cluster_overview,interior_wide,inside_to_outside_room_1,outside_to_inside_middle_axial"


def run_blender(script, key, stage, card=None, args=None):
    env = os.environ.copy()
    if card is not None:
        env["CUDA_VISIBLE_DEVICES"] = str(card)
    env["OMP_NUM_THREADS"] = "4"
    cmd = [
        "blender",
        "-b",
        "-t",
        "4",
        "--python-exit-code",
        "1",
        "-P",
        str(R / "scripts" / script),
        "--",
    ] + (args or [key])
    with (O / "logs" / (stage + "_" + key + ".log")).open("a") as log:
        code = subprocess.run(
            cmd, cwd=R, env=env, stdout=log, stderr=subprocess.STDOUT
        ).returncode
    if code:
        raise RuntimeError(f"{key}: {stage} exited {code}")


def gpu_free(card):
    data = subprocess.check_output(
        [
            "nvidia-smi",
            "-i",
            str(card),
            "--query-gpu=memory.free",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    return int(data.strip())


def host_free_gb():
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(line.split()[1]) / 1048576
    return 0


def job(key, card, stage):
    d = O / key
    if stage == "production":
        while not (d / "visual_review.json").exists():
            time.sleep(15)
    while not (d / "scene_manifest.json").exists():
        time.sleep(15)
    m = json.loads((d / "scene_manifest.json").read_text())
    if not m.get("refinement"):
        run_blender("refine_connect3_scene.py", key, "refine")
    m = json.loads((d / "scene_manifest.json").read_text())
    if not m.get("environment_revision"):
        run_blender("refine_connect3_public_realm.py", key, "public_realm")
    m = json.loads((d / "scene_manifest.json").read_text())
    if not m.get("fonts_embedded"):
        run_blender("fix_connect3_fonts.py", key, "fonts")
    audit_path = d / "geometry_audit.json"
    if not audit_path.exists() or audit_path.stat().st_mtime < max(
        (d / "scene.blend").stat().st_mtime, (d / "scene_manifest.json").stat().st_mtime
    ):
        run_blender("audit_connect3_scene.py", key, "audit_final")
    a = json.loads((d / "geometry_audit.json").read_text())
    assert a["passed"], key
    while gpu_free(card) < 9000 or host_free_gb() < 32:
        time.sleep(20)
    if stage == "critical":
        args = [
            "--scene",
            key,
            "--mode",
            "final",
            "--width",
            "1920",
            "--samples",
            "96",
            "--shots",
            CRITICAL,
        ]
        run_blender("render_urban_v1_full_connect3.py", key, "critical", card, args)
    else:
        while not (d / "visual_review.json").exists():
            time.sleep(15)
        run_blender(
            "render_urban_v1_full_connect3.py",
            key,
            "final",
            card,
            ["--scene", key, "--mode", "final", "--width", "1920", "--samples", "96"],
        )
        run_blender(
            "render_urban_v1_full_connect3.py",
            key,
            "video",
            card,
            [
                "--scene",
                key,
                "--mode",
                "video",
                "--width",
                "1280",
                "--samples",
                "24",
                "--frames",
                "96",
            ],
        )
    return {"scene": key, "stage": stage, "gpu": card, "status": "rendered"}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--stage", choices=["critical", "production"], required=True)
    p.add_argument("--gpus", default="1,5")
    p.add_argument("--scenes", default="")
    a = p.parse_args()
    keys = a.scenes.split(",") if a.scenes else [s[0] for s in SCENES]
    q = queue.Queue()
    for key in keys:
        q.put(key)

    def worker(card):
        while not q.empty():
            try:
                key = q.get_nowait()
            except queue.Empty:
                return
            try:
                r = job(key, card, a.stage)
            except Exception as e:
                r = {
                    "scene": key,
                    "stage": a.stage,
                    "gpu": card,
                    "status": "failed",
                    "error": str(e),
                }
            (O / key / (a.stage + "_job.json")).write_text(json.dumps(r, indent=2))
            print(json.dumps(r), flush=True)
            q.task_done()

    with concurrent.futures.ThreadPoolExecutor(
        max_workers=len(a.gpus.split(","))
    ) as ex:
        list(ex.map(worker, [int(x) for x in a.gpus.split(",")]))


if __name__ == "__main__":
    main()

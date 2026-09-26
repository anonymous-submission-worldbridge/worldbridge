"""Resumable native-scene build/render/encode coordinator; never invent frames."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic3"
SHOTS = [
    "lake_impact",
    "river_detail",
    "lake_environment",
    "river_environment",
    "fountain_environment",
    "fountain_detail",
    "street_environment",
]


def atomic(path, data):
    temporary = path.with_suffix(".writing.json")
    temporary.write_text(json.dumps(data, indent=2))
    os.replace(temporary, path)


def valid(path):
    try:
        with Image.open(path) as im:
            if im.size != (1920, 1080):
                return False
            im.verify()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--gpu", default="1")
    p.add_argument("--phase", choices=["preview", "production"], default="preview")
    p.add_argument("--shots", default=",".join(SHOTS))
    p.add_argument("--batch", type=int, default=4)
    p.add_argument("--worker", default="main")
    p.add_argument(
        "--wait-for",
        type=Path,
        help="Wait for a JSON stage with PASS, PREVIEWS_READY, or VIDEOS_ENCODED status",
    )
    args = p.parse_args()
    shots = args.shots.split(",")
    if any(s not in SHOTS for s in shots) or not 1 <= args.batch <= 8:
        p.error("Invalid shot or batch size")
    OUT.mkdir(parents=True, exist_ok=True)
    logs = OUT / "logs"
    logs.mkdir(exist_ok=True)
    if not args.worker.replace("_", "").isalnum():
        p.error("Worker name must be alphanumeric")
    lock = (OUT / f"pipeline_{args.worker}.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    shot_locks = []
    for shot in sorted(shots):
        handle = (OUT / f"{args.phase}_{shot}.lock").open("a")
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        shot_locks.append(handle)
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES=args.gpu,
        OMP_NUM_THREADS="8",
        OPENBLAS_NUM_THREADS="1",
    )
    state = {
        "status": "RUNNING",
        "phase": args.phase,
        "shots": shots,
        "gpu": args.gpu,
        "started": time.time(),
    }
    status = OUT / f"pipeline_{args.worker}.status.json"
    atomic(status, state)
    if args.wait_for:
        while True:
            dependency = (
                json.loads(args.wait_for.read_text()) if args.wait_for.exists() else {}
            )
            if dependency.get("status") in ("PASS", "PREVIEWS_READY", "VIDEOS_ENCODED"):
                break
            if dependency.get("status") == "FAILED":
                state.update(
                    status="FAILED", error="Dependency failed: " + str(args.wait_for)
                )
                atomic(status, state)
                raise RuntimeError(state["error"])
            state.update(
                status="WAITING", dependency=str(args.wait_for), updated=time.time()
            )
            atomic(status, state)
            time.sleep(20)
        state["status"] = "RUNNING"
        atomic(status, state)

    def run(command, label):
        log = logs / (label + "_" + str(time.time_ns()) + ".log")
        state.update(stage=label, log=str(log), updated=time.time())
        atomic(status, state)
        with log.open("w") as stream:
            process = subprocess.Popen(
                command, cwd=ROOT, env=env, stdout=stream, stderr=subprocess.STDOUT
            )
            state["child_pid"] = process.pid
            atomic(status, state)
            result = process.wait()
        if result:
            raise RuntimeError(f"{label} exited {result}: {log}")

    try:
        for shot in shots:
            state["shot"] = shot
            build = OUT / f"build_{shot}.json"
            pack = OUT / "render_packs" / f"{shot}.blend"
            if not build.exists():
                run(
                    [
                        "blender",
                        "--factory-startup",
                        "--disable-depsgraph-on-file-load",
                        "-b",
                        "--threads",
                        "8",
                        "--python-exit-code",
                        "1",
                        "--python",
                        str(ROOT / "scripts/build_urban_v1_full_13_dynamic3.py"),
                        "--",
                        "--shot",
                        shot,
                    ],
                    shot + "_build",
                )
            report = json.loads(build.read_text())
            record = next(s for s in report["shots"] if s["name"] == shot)
            if report["status"] != "BUILT" or sha256(pack) != record["pack_sha256"]:
                raise RuntimeError("Pack provenance failed: " + shot)
            numbers = (
                [1, 48, 96, 144] if args.phase == "preview" else list(range(1, 145))
            )
            folder = (
                OUT
                / (
                    "frames_final"
                    if args.phase == "production"
                    else "previews_denoised"
                )
                / shot
            )
            folder.mkdir(parents=True, exist_ok=True)
            previous_contract = folder / "render_contract.json"
            if previous_contract.exists() and any(folder.glob("frame_*.png")):
                prior = json.loads(previous_contract.read_text())
                if (
                    prior["blend_sha256"] != record["pack_sha256"]
                    or prior["renderer_sha256"]
                    != sha256(ROOT / "scripts/render_urban_v1_full_13_dynamic3.py")
                    or prior["resolution"] != [1920, 1080]
                    or prior["samples"] != 128
                    or not prior["denoising"]
                ):
                    raise RuntimeError(
                        "Existing frames have a different scene/render contract; archive that frame folder first: "
                        + str(folder)
                    )
            for frame in numbers:
                target = folder / f"frame_{frame:04d}.png"
                if target.exists() and not valid(target):
                    target.rename(
                        logs
                        / (
                            shot
                            + "_"
                            + target.stem
                            + "_corrupt_"
                            + str(time.time_ns())
                            + ".png"
                        )
                    )
            missing = [f for f in numbers if not valid(folder / f"frame_{f:04d}.png")]
            for begin in range(0, len(missing), args.batch):
                batch = missing[begin : begin + args.batch]
                run(
                    [
                        "blender",
                        "--disable-depsgraph-on-file-load",
                        "-b",
                        str(pack),
                        "--threads",
                        "8",
                        "--python-exit-code",
                        "1",
                        "--python",
                        str(ROOT / "scripts/render_urban_v1_full_13_dynamic3.py"),
                        "--",
                        "--output-dir",
                        str(folder),
                        "--frames",
                        ",".join(map(str, batch)),
                        "--denoise",
                    ],
                    shot + "_frames_" + str(batch[0]),
                )
                if any(not valid(folder / f"frame_{f:04d}.png") for f in batch):
                    raise RuntimeError("Rendered PNG validation failed")
                state["completed_frames"] = sum(
                    valid(folder / f"frame_{f:04d}.png") for f in range(1, 145)
                )
                atomic(status, state)
            if args.phase == "production":
                videos = OUT / "videos"
                videos.mkdir(exist_ok=True)
                video = videos / (shot + ".mp4")
                run(
                    [
                        "ffmpeg",
                        "-nostdin",
                        "-y",
                        "-framerate",
                        "24",
                        "-start_number",
                        "1",
                        "-i",
                        str(folder / "frame_%04d.png"),
                        "-frames:v",
                        "144",
                        "-c:v",
                        "libx264",
                        "-preset",
                        "slow",
                        "-crf",
                        "16",
                        "-pix_fmt",
                        "yuv420p",
                        "-movflags",
                        "+faststart",
                        str(video),
                    ],
                    shot + "_encode",
                )
                probe = json.loads(
                    subprocess.check_output(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-count_frames",
                            "-select_streams",
                            "v:0",
                            "-show_entries",
                            "stream=width,height,r_frame_rate,nb_read_frames,duration",
                            "-of",
                            "json",
                            str(video),
                        ],
                        text=True,
                    )
                )["streams"][0]
                if (
                    probe["width"],
                    probe["height"],
                    int(probe["nb_read_frames"]),
                    probe["r_frame_rate"],
                ) != (1920, 1080, 144, "24/1"):
                    raise RuntimeError("Video verification failed")
                run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-xerror",
                        "-i",
                        str(video),
                        "-f",
                        "null",
                        "-",
                    ],
                    shot + "_decode",
                )
                atomic(
                    OUT / f"delivery_{shot}.json",
                    {
                        "status": "PASS",
                        "video": str(video),
                        "sha256": sha256(video),
                        "stream": probe,
                        "verified_native_png_frames": 144,
                        "pack_sha256": record["pack_sha256"],
                        "render_contract": json.loads(
                            (folder / "render_contract.json").read_text()
                        ),
                    },
                )
                if shot == "river_detail":
                    run(
                        [
                            "python3",
                            str(
                                ROOT
                                / "scripts/audit_urban_v1_full_13_dynamic3_frames.py"
                            ),
                            str(folder),
                            "--frames",
                            "1,48,96,144",
                        ],
                        shot + "_localized_motion_audit",
                    )
        state["status"] = (
            "PREVIEWS_READY" if args.phase == "preview" else "VIDEOS_ENCODED"
        )
        state["finished"] = time.time()
        atomic(status, state)
    except BaseException as error:
        state.update(status="FAILED", error=repr(error), updated=time.time())
        atomic(status, state)
        raise


if __name__ == "__main__":
    main()

"""Bounded native render batches; release Blender caches between batches.

Does not alter the renderer/scene contract or interpolate/copy image content.
Partial PNGs are verified before resumption. Final skip-only pass writes the
normal full-shot progress report, followed by the separate video audit.
"""
import argparse
import fcntl
import json
import os
import subprocess
import time
from pathlib import Path
from PIL import Image


def valid(path):
    try:
        with Image.open(path) as im:
            if im.size != (1280, 720):
                return False
            im.verify()
        return True
    except (OSError, ValueError, SyntaxError):
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--shot", required=True, choices=["river_and_wind", "lake_and_wind"]
    )
    parser.add_argument("--gpu", required=True)
    parser.add_argument("--batch", type=int, default=2)
    parser.add_argument(
        "--tail-from",
        type=int,
        help="Independent tail worker; publish only verified same-contract PNGs",
    )
    args = parser.parse_args()
    if not 1 <= args.batch <= 16:
        parser.error("--batch must be between 1 and 16")
    root = Path(__file__).resolve().parents[1]
    output = root / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic2"
    shot = next(
        s
        for s in json.loads((output / "dynamic2_manifest.json").read_text())["shots"]
        if s["name"] == args.shot
    )
    numbers = list(range(shot["start"], shot["end"] + 1))
    if args.tail_from is not None:
        if args.tail_from not in numbers:
            parser.error("--tail-from must be inside this shot")
        numbers = [i for i in numbers if i >= args.tail_from]
    frames = output / "frames"
    render_frames = (
        frames
        if args.tail_from is None
        else output / f"frames_helper_{args.shot}_{args.tail_from}"
    )
    render_frames.mkdir(exist_ok=True)
    worker = (
        args.shot if args.tail_from is None else f"{args.shot}_tail_{args.tail_from}"
    )
    logs = output / "batch_logs"
    logs.mkdir(exist_ok=True)
    lock = (logs / (worker + ".lock")).open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise RuntimeError("Another batch worker already owns this shot")
    environment = dict(os.environ, CUDA_VISIBLE_DEVICES=args.gpu)
    base = [
        "blender",
        "--disable-depsgraph-on-file-load",
        "-b",
        str(output / "render_packs" / (args.shot + ".blend")),
        "--python-exit-code",
        "1",
        "--python",
        str(root / "scripts/render_urban_v1_full_13_dynamic2.py"),
        "--",
        "--output-dir",
        str(render_frames),
        "--shot",
        args.shot,
        "--engine",
        "cycles",
        "--width",
        "1280",
        "--height",
        "720",
        "--samples",
        "32",
    ]
    stalls = 0
    while True:
        missing = [
            i for i in numbers if not valid(output / "frames" / f"frame_{i:04d}.png")
        ]
        selected = missing[: args.batch]
        if not selected and args.tail_from is not None:
            print("DYNAMIC2 TAIL COMPLETE", worker, flush=True)
            break
        stamp = time.time_ns()
        for frame in selected:
            png = render_frames / f"frame_{frame:04d}.png"
            if png.exists() and not valid(png):
                # Recoverable quarantine: renderer's fast header check must not
                # cause a truncated PNG to be skipped indefinitely.
                archive = logs / f"corrupt_frame_{frame:04d}_{stamp}.png"
                os.replace(png, archive)
                print("DYNAMIC2 QUARANTINED incomplete PNG", archive, flush=True)
        logfile = logs / f"{worker}_{stamp}.log"
        command = base + (
            ["--frames", ",".join(map(str, selected))] if selected else []
        )
        measurements = []
        with logfile.open("w") as stream:
            process = subprocess.Popen(
                command,
                cwd=root,
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            print(
                "DYNAMIC2 BATCH",
                args.shot,
                selected or "FINAL_VERIFY",
                "PID",
                process.pid,
                flush=True,
            )
            while process.poll() is None:
                status = Path(f"/proc/{process.pid}/status")
                try:
                    metrics = {
                        line.split(":")[0]: line.split(":")[1].strip()
                        for line in status.read_text().splitlines()
                        if line.startswith(("VmRSS:", "VmHWM:", "VmPeak:"))
                    }
                    metrics["time"] = time.time()
                    measurements.append(metrics)
                except FileNotFoundError:
                    pass
                time.sleep(5)
        published = []
        if args.tail_from is not None:
            contract_name = "render_contract_" + args.shot + ".json"
            helper_contract = render_frames / contract_name
            if helper_contract.exists():
                if json.loads(helper_contract.read_text()) != json.loads(
                    (frames / contract_name).read_text()
                ):
                    raise RuntimeError("Tail frame provenance differs from main render")
                for frame in selected:
                    png = render_frames / f"frame_{frame:04d}.png"
                    if valid(png):
                        try:
                            # Atomic non-overwriting publication; never replace
                            # an active main-worker output or unverified image.
                            os.link(png, frames / png.name)
                            published.append(frame)
                        except FileExistsError:
                            pass
        remaining = [
            i for i in numbers if not valid(output / "frames" / f"frame_{i:04d}.png")
        ]
        result = {
            "shot": args.shot,
            "frames": selected,
            "exit_code": process.returncode,
            "remaining": len(remaining),
            "published_tail_frames": published,
            "log": str(logfile),
            "memory_samples": measurements,
        }
        (logs / f"{worker}_{stamp}.json").write_text(json.dumps(result, indent=2))
        print(
            "DYNAMIC2 BATCH DONE",
            args.shot,
            "exit",
            process.returncode,
            "remaining",
            len(remaining),
            flush=True,
        )
        if not selected:
            if process.returncode:
                raise RuntimeError("Full-shot verification failed")
            break
        stalls = stalls + 1 if len(remaining) >= len(missing) else 0
        if stalls >= 3:
            raise RuntimeError(
                "Three consecutive batches made no progress; inspect logs"
            )


if __name__ == "__main__":
    main()

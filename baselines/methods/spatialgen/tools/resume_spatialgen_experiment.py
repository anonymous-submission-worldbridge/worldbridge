#!/usr/bin/env python3
"""Recover verified migrated SpatialGen artifacts and resume missing pilot stages."""
from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


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
_wb_WORLDBRIDGE_PYTHON = _wb_paths["WORLDBRIDGE_PYTHON"]

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import shutil
import threading
import queue as queue_module
import fcntl
import signal

B = Path(f"{_wb_WORLDBRIDGE_ROOT}/baselines").resolve()
PILOT = B / "work/spatialgen/pilot_generated/table2"
PYTHON = B / "envs/spatialgen/bin/python"
os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True
s = importlib.util.spec_from_file_location(
    "spatialgen_resume_adapter", B / "methods/spatialgen/adapter.py"
)
a = importlib.util.module_from_spec(s)
sys.modules[s.name] = a
s.loader.exec_module(a)


def digest(p):
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def recover():
    from PIL import Image

    report = []
    for p in sorted(
        PILOT.glob("indoor/spatialgen/*/seed_*/scene/intermediate/flux_reference.json")
    ):
        r = p.parents[2]
        j = json.loads(p.read_text())
        spec = json.loads((r / "input/spec.json").read_text())
        native = json.loads((r / "input/native_input.json").read_text())
        assert (
            j["spec_id"] == spec["spec_id"]
            and j["method_seed"] == native["method_seed"]
        )
        assert j["prompt"] == spec["prompt_en"]
        files = {
            "control_image_sha256": r
            / "input/dataset"
            / spec["spec_id"]
            / "condition/frame_0.jpg",
            "reference_1024_sha256": p.parent / "flux_reference_1024.png",
            "reference_512_sha256": p.parent / "flux_reference_512.jpg",
        }
        for key, path in files.items():
            assert digest(path) == j[key], (str(path), key)
        assert (p.parent / "flux_generator_state.pt").is_file()
        target = r / "input/dataset" / spec["spec_id"] / "rgb/frame_0.jpg"
        restored = digest(target) != j["native_frame_sha256"]
        if restored:
            temp = target.with_suffix(".recovered.jpg")
            Image.open(files["reference_512_sha256"]).convert("RGB").save(
                temp, format="JPEG"
            )
            assert (
                digest(temp) == j["native_frame_sha256"]
            ), "Pillow recompression differs; original reference retained"
            # Keep the overwritten placeholder for audit; never modify the saved reference.
            backup = target.with_suffix(".pre_reference_recovery.jpg")
            if not backup.exists():
                target.rename(backup)
            temp.replace(target)
        assert a._reference_output_valid(r, spec, native["logical_seed"])
        (r / "REFERENCE_SUCCESS").touch()
        row = {
            "run_dir": str(r),
            "restored": restored,
            "reference_metadata_sha256": digest(p),
            "native_frame_sha256": digest(target),
            "operation": "restore_existing_verified_reference_not_regeneration",
        }
        report.append(row)
        print(
            "RECOVERED", spec["spec_id"], native["logical_seed"], restored, flush=True
        )
    a.atomic_json(B / "results/spatialgen/reference_recovery_20260905.json", report)


def pilot(gpus, selected=None):
    pilot_lock = (B / "work/spatialgen/pilot_execution.lock").open("a")
    fcntl.flock(pilot_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    tasks = sorted(PILOT.glob("indoor/spatialgen/*/seed_*/run_manifest.json"))
    if selected:
        tasks = [
            p for p in tasks if p.parent.parent.name + "/" + p.parent.name in selected
        ]
    pending = queue_module.Queue()
    for task in tasks:
        pending.put(task)

    def available(gpu):
        reported = False
        while not pending.empty():
            free = int(
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        f"--id={gpu}",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                ).strip()
            )
            if free < 35000:
                if not reported:
                    print("PILOT_WAIT_GPU", gpu, free, flush=True)
                    reported = True
                time.sleep(30)
                continue
            try:
                yield pending.get_nowait()
            except queue_module.Empty:
                return

    def queue(gpu, paths):
        for p in paths:
            r = p.parent
            j = json.loads(p.read_text())
            if (r / "SUCCESS").exists():
                check = a.inspect_rendered_output(r)
                assert check["valid"], check
                print(
                    "PILOT_REUSE_COMPLETED", j["spec_id"], j["logical_seed"], flush=True
                )
                continue
            free = int(
                subprocess.check_output(
                    [
                        "nvidia-smi",
                        f"--id={gpu}",
                        "--query-gpu=memory.free",
                        "--format=csv,noheader,nounits",
                    ],
                    text=True,
                ).strip()
            )
            if free < 35000:
                raise RuntimeError(f"GPU {gpu} insufficient free memory: {free}")
            for phase in ("generate", "render"):
                if (
                    phase == "generate"
                    and (r / "GENERATION_SUCCESS").exists()
                    and j.get("verified_generation_recovery")
                ):
                    print(
                        "PILOT_REUSE_VERIFIED_GAUSSIAN",
                        j["spec_id"],
                        j["logical_seed"],
                        flush=True,
                    )
                    continue
                logdir = B / "work/spatialgen/resume_20260905"
                logdir.mkdir(parents=True, exist_ok=True)
                log = logdir / f"{j['spec_id']}_seed_{j['logical_seed']}_{phase}.log"
                cmd = [
                    str(PYTHON),
                    str(B / "methods/spatialgen/adapter.py"),
                    "run",
                    "--spec-id",
                    j["spec_id"],
                    "--seed",
                    str(j["logical_seed"]),
                    "--data-root",
                    str(PILOT),
                    "--phase",
                    phase,
                    "--gpu",
                    str(gpu),
                ]
                env = dict(
                    os.environ,
                    CUDA_VISIBLE_DEVICES=str(gpu),
                    PYTHONDONTWRITEBYTECODE="1",
                )
                print(
                    "PILOT_START",
                    j["spec_id"],
                    j["logical_seed"],
                    phase,
                    gpu,
                    flush=True,
                )
                with log.open("a") as f:
                    result = subprocess.run(
                        cmd, cwd=B, env=env, stdout=f, stderr=subprocess.STDOUT
                    )
                print(
                    "PILOT_END",
                    j["spec_id"],
                    j["logical_seed"],
                    phase,
                    result.returncode,
                    flush=True,
                )
                if result.returncode:
                    raise RuntimeError(f"Stage failed; inspect {log}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as pool:
        futures = [pool.submit(queue, gpu, available(gpu)) for gpu in gpus]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def status():
    subprocess.run(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.used,memory.free,utilization.gpu",
            "--format=csv",
        ]
    )
    proc = subprocess.run(
        ["ps", "-eo", "pid,ppid,etime,stat,pcpu,pmem,wchan:24,args"],
        text=True,
        stdout=subprocess.PIPE,
    )
    for line in proc.stdout.splitlines():
        if any(
            x in line
            for x in [
                "inference_sd.py",
                "resume_spatialgen",
                "Sparse-RaDeGS",
                "methods/spatialgen/adapter.py run",
                "eval_iqa.py",
                "python train.py",
            ]
        ):
            print(line[:230])
    for p in sorted((B / "work/spatialgen/resume_20260905").glob("*.log")):
        print(p.name, p.read_text(errors="replace")[-1200:])


def io_diagnostics():
    from collections import Counter

    proc = subprocess.check_output(
        ["ps", "-eo", "pid,ppid,pcpu,nlwp,stat,wchan:24,args"], text=True
    )
    for line in proc.splitlines():
        if "python train.py" not in line or "/spatialgen/" not in line:
            continue
        print(line[:600], flush=True)
        pid = line.split()[0]
        root = Path("/proc") / pid
        print("IO", (root / "io").read_text(), flush=True)
        print(
            "THREAD_WAITS",
            Counter(p.read_text().strip() for p in (root / "task").glob("*/wchan")),
            flush=True,
        )
        print(
            "FD_TARGETS",
            [os.readlink(p) for p in (root / "fd").glob("*") if p.exists()][-15:],
            flush=True,
        )
    print("PRESSURE", (Path("/proc/pressure/io")).read_text(), flush=True)


def nfs_event_buffer():
    root = B / "work/spatialgen/runtime_compat"
    root.mkdir(parents=True, exist_ok=True)
    module = root / "spatialgen_nfs_events.py"
    module.write_text(
        f'"""Buffer only SpatialGen TensorBoard event bytes; preserve training arithmetic."""\nimport atexit, io, os\ndef install():\n    from tensorboard.summary.writer import event_file_writer as ew\n    original_file=ew.tf.io.gfile.GFile\n    original_init=ew.EventFileWriter.__init__\n    baseline="{_wb_WORLDBRIDGE_ROOT}/baselines/"\n    def event_file(filename, mode="r"):\n        path=os.path.realpath(os.fsdecode(filename))\n        if path.startswith(baseline) and os.path.basename(path).startswith("events.out.tfevents.") and mode in ("wb","ab"):\n            print("SPATIALGEN_NFS_EVENT_BUFFER", path, flush=True)\n            return io.open(filename,mode,buffering=1024*1024)\n        return original_file(filename,mode)\n    def initialize(self,*args,**kwargs):\n        original_init(self,*args,**kwargs)\n        atexit.register(self.close)\n    ew.tf.io.gfile.GFile=event_file\n    ew.EventFileWriter.__init__=initialize\n'
    )
    probe = root / "event_buffer_probe.py"
    probe.write_text(
        """import sys,time,json,hashlib
from pathlib import Path
from tensorboard.summary.writer.record_writer import RecordWriter
from tensorboard.summary.writer import event_file_writer as ew
from tensorboard.compat.proto.event_pb2 import Event
from tensorboard.compat.proto.summary_pb2 import Summary
root=Path(__file__).parent
mode=sys.argv[1]
if mode=="buffered":
    import spatialgen_nfs_events
    spatialgen_nfs_events.install()
path=root/("events.out.tfevents.probe_"+mode)
started=time.monotonic()
writer=RecordWriter(ew.tf.io.gfile.GFile(str(path),"wb"))
for step in range(64):
    event=Event(wall_time=1234.5,step=step,summary=Summary(value=[Summary.Value(tag="fixed_scalar",simple_value=step/64)]))
    writer.write(event.SerializeToString())
writer.flush();writer.close()
print(json.dumps({"mode":mode,"wall_s":time.monotonic()-started,"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"bytes":path.stat().st_size}))
"""
    )
    report = (
        B / "methods/spatialgen/environment/spatialgen/nfs_event_buffer_20260905.json"
    )
    if report.exists():
        print("NFS_EVENT_BUFFER_ALREADY_INSTALLED")
        return
    results = []
    for mode in ["original", "buffered"]:
        result = subprocess.check_output(
            [str(PYTHON), str(probe), mode], env=a.baseline_environment(0), text=True
        )
        print(result, flush=True)
        results.append(json.loads(result.splitlines()[-1]))
    assert (
        results[0]["sha256"] == results[1]["sha256"]
        and results[0]["bytes"] == results[1]["bytes"]
    )
    pth = (
        B
        / "envs/spatialgen/lib/python3.10/site-packages/spatialgen_table2_nfs_events.pth"
    )
    pth.write_text(
        'import os,sys; os.environ.get("SPATIALGEN_TABLE2_CANONICAL_ONLY")=="1" and os.path.basename(sys.argv[0])=="train.py" and (sys.path.insert(0,'
        + repr(str(root))
        + '),__import__("spatialgen_nfs_events").install())\n'
    )
    a.atomic_json(
        report,
        {
            "installed_at_utc": a.utc_now(),
            "purpose": "Host NFS event-log buffering only; no RNG, model, training, iteration, checkpoint or render changes. Existing processes retain their original logger.",
            "probe": results,
            "module_sha256": digest(module),
            "pth_sha256": digest(pth),
            "activation": "Only official train.py with SPATIALGEN_TABLE2_CANONICAL_ONLY=1; all files remain under baselines.",
            "log_format_validation": "All 64 fixed protobuf records produce byte-identical TFRecord files; only file open/flush batching changes. Close at interpreter exit drains the writer queue.",
        },
    )
    print("NFS_EVENT_BUFFER_INSTALLED", flush=True)


def nfs_buffer_smoke():
    root = B / "work/spatialgen/runtime_compat"
    probe = root / "train.py"
    probe.write_text(
        """from tensorboard.summary.writer import event_file_writer as ew
from tensorboard.compat.proto.event_pb2 import Event
from pathlib import Path
import json
writer=ew.EventFileWriter(str(Path(__file__).parent/"startup_probe"))
writer.add_event(Event(wall_time=1.0,step=1));writer.flush();writer.close()
assert ew.tf.io.gfile.GFile.__module__=="spatialgen_nfs_events"
print("STARTUP_EVENT_BUFFER_VERIFIED")
"""
    )
    env = a.baseline_environment(0)
    env["SPATIALGEN_TABLE2_CANONICAL_ONLY"] = "1"
    result = subprocess.run(
        [str(PYTHON), str(probe)],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    (root / "startup_probe.log").write_text(result.stdout)
    print(result.stdout, flush=True)
    assert result.returncode == 0 and "STARTUP_EVENT_BUFFER_VERIFIED" in result.stdout
    (root / "startup_probe.done").touch()


def command(cmd, gpu, logfile, worldscore=False):
    env = dict(
        os.environ,
        CUDA_VISIBLE_DEVICES=str(gpu),
        PYTHONDONTWRITEBYTECODE="1",
        TORCH_HOME=str(B / "cache/torch"),
        HF_HOME=str(B / "cache/huggingface"),
        HF_HUB_OFFLINE="1",
        XDG_CACHE_HOME=str(B / "cache/xdg_metrics"),
        TMPDIR=str(B / "work/spatialgen/tmp"),
        PYTHONUNBUFFERED="1",
    )
    env["PYTHONPATH"] = str(B.parent)
    if worldscore:
        env["PYTHONPATH"] = (
            str(B / "work/metaurban/worldscore_abi") + os.pathsep + str(B.parent)
        )
    logfile.parent.mkdir(parents=True, exist_ok=True)
    print("COMMAND_START", cmd, flush=True)
    with logfile.open("a") as f:
        r = subprocess.run(cmd, cwd=B, env=env, stdout=f, stderr=subprocess.STDOUT)
    print("COMMAND_END", r.returncode, logfile, flush=True)
    if r.returncode:
        raise RuntimeError(logfile.read_text(errors="replace")[-4000:])


def metrics_smoke(gpu):
    result = B / "work/spatialgen/metric_smoke_20260905"
    common = [
        "--data-root",
        str(PILOT),
        "--spec-file",
        str(a.DEFAULT_SPEC_FILE),
        "--method",
        "spatialgen",
        "--domain",
        "indoor",
        "--spec-id",
        "indoor_bedroom_00",
        "--seed",
        "0",
    ]
    iqa = f"{_wb_WORLDBRIDGE_PYTHON}"
    jobs = [
        (
            "cuda",
            [str(PYTHON), str(B / "methods/spatialgen/tools/smoke_spatialgen_cuda.py")],
        ),
        (
            "iqa",
            [
                iqa,
                str(B / "evaluation/visual/eval_iqa.py"),
                *common,
                "--device",
                "cuda",
                "--output",
                str(result / "iqa.jsonl"),
            ],
        ),
        (
            "semantic",
            [
                iqa,
                str(B / "evaluation/visual/generate_semantics.py"),
                *common,
                "--device",
                "cuda",
                "--metadata-output",
                str(result / "semantic.json"),
            ],
        ),
        (
            "consistency",
            [
                str(B / "envs/worldscore/bin/python"),
                str(B / "evaluation/visual/eval_worldscore.py"),
                *common,
                "--gpu",
                str(gpu),
                "--output",
                str(result / "consistency.jsonl"),
            ],
        ),
    ]
    for name, cmd in jobs:
        marker = result / (name + ".done")
        if marker.exists():
            continue
        command(cmd, gpu, result / (name + ".log"), name == "consistency")
        marker.touch()


def test():
    command(
        [
            "python3",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(B / "tmp/spatialgen_pytest_20260905"),
            str(B / "methods/spatialgen/tests/test_spatialgen_adapter.py"),
            str(B / "tests/test_eval_worldscore.py"),
            str(B / "tests/test_aggregate_generation.py"),
        ],
        0,
        B / "work/spatialgen/resume_tests.log",
    )


def validate_assets():
    j = json.loads(
        (B / "methods/spatialgen/environment/spatialgen/assets.json").read_text()
    )
    files = []
    for group, key in [("spatialgen", "files"), ("flux_base", "core_weights")]:
        for rel, info in j[group][key].items():
            files.append(
                (B / Path(j[group]["root"]).relative_to("baselines") / rel, info)
            )
    info = j["wireframe_lora"]
    files.append((B / Path(info["path"]).relative_to("baselines"), info))
    report = []
    for path, info in files:
        assert path.is_file() and path.stat().st_size == info["size_bytes"], path
        value = digest(path)
        assert value == info["sha256"], path
        report.append(
            {"path": str(path), "size_bytes": path.stat().st_size, "sha256": value}
        )
        print("ASSET_VERIFIED", path, flush=True)
    a.atomic_json(B / "results/spatialgen/assets_verified_20260905.json", report)


def formal_preflight():
    specs = a.load_specs(a.DEFAULT_SPEC_FILE)
    report = []
    for spec in specs.values():
        boxes = a.compile_boxes(spec)
        cameras = a.build_cameras(spec)
        for seed in range(4):
            r = a.run_directory(B / "data/table2", spec, seed)
            native = a.build_native_input(spec, seed, boxes, cameras)
            assert json.loads((r / "input/spec.json").read_text()) == spec
            assert json.loads((r / "input/native_input.json").read_text()) == native
            scene = r / "input/dataset" / spec["spec_id"]
            assert json.loads(
                (scene / "room_layout.json").read_text()
            ) == a.build_room_layout(spec, boxes)
            assert json.loads((scene / "cameras.json").read_text()) == cameras
            m = json.loads((r / "run_manifest.json").read_text())
            prior = [
                v for v in m["attempts"] if v["phase"] == "prepare" and v["success"]
            ][-1]
            assert prior["prepare_script_sha256"] == digest(
                B / "methods/spatialgen/tools/prepare_spatialgen_inputs.py"
            )
            assert prior["native_input_sha256"] == digest(r / "input/native_input.json")
            assert a._prepared_inputs_valid(r, spec["spec_id"])
            report.append(
                {
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "native_input_sha256": digest(r / "input/native_input.json"),
                    "prepare_script_sha256": prior["prepare_script_sha256"],
                    "reuse_basis": "identical compiler output, renderer source, input hashes and complete prepared files",
                }
            )
    a.atomic_json(B / "results/spatialgen/formal_input_reuse_20260905.json", report)
    print("FORMAL_INPUTS_VERIFIED", len(report), flush=True)


def freeze():
    lock = B / "methods/spatialgen/protocol/generation/spatialgen_formal.lock.json"
    if lock.exists():
        print("ALREADY_FROZEN", digest(lock))
        return
    characterize_reproduction()
    pilot_rows = []
    for p in sorted(PILOT.glob("indoor/spatialgen/*/seed_*/run_manifest.json")):
        r = p.parent
        j = json.loads(p.read_text())
        assert (r / "SUCCESS").exists() and a.inspect_rendered_output(r)["valid"], r
        assert (
            len(
                list(
                    (r / "scene/native").glob(
                        "**/point_cloud/iteration_7000/point_cloud.ply"
                    )
                )
            )
            == 1
        )
        pilot_rows.append(
            {
                "run_dir": str(r),
                "manifest_sha256": digest(p),
                "validation_sha256": digest(r / "renders/validation.json"),
            }
        )
    assert len(pilot_rows) == 10
    smoke = B / "work/spatialgen/metric_smoke_20260905"
    for f in [
        "cuda.done",
        "iqa.done",
        "iqa_repeat.done",
        "semantic.done",
        "consistency.done",
        "diversity.done",
    ]:
        assert (smoke / f).exists(), f
    for f in ["iqa.jsonl", "consistency.jsonl"]:
        rows = [json.loads(x) for x in (smoke / f).read_text().splitlines() if x]
        assert len(rows) == 1 and rows[0]["success"], (f, rows)
    assert (
        len(
            json.loads(
                (B / "results/spatialgen/assets_verified_20260905.json").read_text()
            )
        )
        == 14
    )
    assert (
        len(
            json.loads(
                (B / "results/spatialgen/formal_input_reuse_20260905.json").read_text()
            )
        )
        == 100
    )
    protocol = B / "methods/spatialgen/protocol/generation/spatialgen_protocol.yaml"
    old = protocol.read_text()
    backup = protocol.with_name("spatialgen_protocol.preformal_20260905.yaml")
    if not backup.exists():
        backup.write_text(old)
    new = old.replace("status: preflight", "status: formal_frozen")
    new = new.replace(
        "    iterations: 7000\n",
        "    iterations: 7000\n    seed: 0\n    seed_policy: official_hardcoded_safe_state_seed\n",
    )
    new = new.replace(
        "minimum_free_gpu_memory_mib: 20000", "minimum_free_gpu_memory_mib: 40000"
    )
    new = new.replace(
        "base_protocol_sha256: 46990b34f92a2400e616d22ede1cb49a7e0fb1cb218368e9f67693f9202adeda",
        "base_protocol_sha256: " + digest(B / "protocol/generation/protocol.yaml"),
    )
    temp = protocol.with_suffix(".yaml.tmp")
    temp.write_text(new)
    temp.replace(protocol)
    sources = {
        str(p.relative_to(B)): digest(p)
        for p in [
            B / "methods/spatialgen/adapter.py",
            B / "methods/spatialgen/tools/prepare_spatialgen_inputs.py",
            B / "methods/spatialgen/tools/spatialgen_generate_reference.py",
            B / "methods/spatialgen/tools/render_spatialgen_generation.py",
            protocol,
            B / "protocol/generation/indoor_specs.jsonl",
            B / "vendor/SpatialGen/src/inference_sd.py",
            B / "vendor/SpatialGen/src/recons/Sparse-RaDeGS/train.py",
            B / "vendor/SpatialGen/src/recons/Sparse-RaDeGS/utils/general_utils.py",
        ]
    }
    environment = B / "methods/spatialgen/environment/spatialgen/formal_20260905"
    environment.mkdir(parents=True, exist_ok=True)
    (environment / "pip-freeze.txt").write_text(
        subprocess.check_output([str(PYTHON), "-m", "pip", "freeze"], text=True)
    )
    (environment / "gpu.csv").write_text(
        subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,driver_version",
                "--format=csv",
            ],
            text=True,
        )
    )
    a.atomic_json(
        lock,
        {
            "method": "spatialgen",
            "status": "formal_frozen",
            "frozen_at_utc": a.utc_now(),
            "sources": sources,
            "pilot_runs": pilot_rows,
            "assets_manifest_sha256": digest(
                B / "results/spatialgen/assets_verified_20260905.json"
            ),
            "reuse_policy": "Prepared inputs and FLUX reference artifacts may be reused only after exact specification, source and file hash validation. Pilot Gaussian scenes do not enter formal results.",
            "retry_policy": "one same-seed retry per failed infrastructure stage; no quality retry",
            "native_seed_limitation": "FLUX and MVD receive method_seed. Official Sparse-RaDeGS safe_state hardcodes seed 0; that native reconstruction behavior is retained and explicitly reported.",
            "reproducibility_report_sha256": digest(
                B / "results/spatialgen/reproducibility_20260905.json"
            ),
            "environment_pip_freeze_sha256": digest(environment / "pip-freeze.txt"),
        },
    )
    print("FORMAL_FROZEN", digest(lock), flush=True)


def initialize_formal(spec, seed):
    r = a.run_directory(B / "data/table2", spec, seed)
    m = json.loads((r / "run_manifest.json").read_text())
    if m.get("formal_trial_started_at_utc"):
        return r
    archive_preformal_logs(r)
    backup = r / "run_manifest.preformal_20260905.json"
    if not backup.exists():
        shutil.copyfile(r / "run_manifest.json", backup)
    a.compile_run_input(spec, seed, r, a.DEFAULT_SPEC_FILE)
    m = json.loads((r / "run_manifest.json").read_text())
    m.update(
        attempts=[],
        preformal_manifest=str(backup.relative_to(r)),
        preformal_manifest_sha256=digest(backup),
        formal_trial_started_at_utc=a.utc_now(),
        generation_success=False,
        render_success=False,
        failure_reason=None,
        native_stage_seeds={
            "flux": a.method_seed(spec, seed),
            "multiview": a.method_seed(spec, seed),
            "sparse_radegs": 0,
        },
        prepared_input_reuse={
            "audit": "results/spatialgen/formal_input_reuse_20260905.json",
            "native_input_sha256": digest(r / "input/native_input.json"),
        },
    )
    a.atomic_json(r / "run_manifest.json", m)
    source = PILOT / "indoor/spatialgen" / spec["spec_id"] / f"seed_{seed}"
    reference = source / "scene/intermediate/flux_reference.json"
    if reference.is_file() and a._reference_output_valid(source, spec, seed):
        j = json.loads(reference.read_text())
        assert (
            digest(r / "input/dataset" / spec["spec_id"] / "condition/frame_0.jpg")
            == j["control_image_sha256"]
        )
        target = r / "scene/intermediate"
        target.mkdir(parents=True, exist_ok=True)
        for name in [
            "flux_reference.json",
            "flux_reference_1024.png",
            "flux_reference_512.jpg",
            "flux_generator_state.pt",
        ]:
            shutil.copyfile(reference.parent / name, target / name)
        frame = r / "input/dataset" / spec["spec_id"] / "rgb/frame_0.jpg"
        tmp = frame.with_suffix(".reference.tmp")
        shutil.copyfile(
            source / "input/dataset" / spec["spec_id"] / "rgb/frame_0.jpg", tmp
        )
        tmp.replace(frame)
        assert a._reference_output_valid(r, spec, seed)
        (r / "REFERENCE_SUCCESS").touch()
        m["reference_artifact_reuse"] = {
            "source_run": str(source),
            "metadata_sha256": digest(reference),
            "native_frame_sha256": digest(frame),
        }
        a.atomic_json(r / "run_manifest.json", m)
    return r


def archive_preformal_logs(only_run=None):
    from datetime import datetime

    runs = (
        [only_run]
        if only_run
        else [
            p.parent
            for p in (B / "data/table2/indoor/spatialgen").glob(
                "*/seed_*/run_manifest.json"
            )
        ]
    )
    for r in runs:
        output = r / "preformal_logs_20260905"
        report = output / "archive.json"
        if report.exists():
            continue
        output.mkdir(exist_ok=True)
        m = json.loads((r / "run_manifest.json").read_text())
        start = m.get("formal_trial_started_at_utc")
        cutoff = (
            datetime.fromisoformat(start.replace("Z", "+00:00")).timestamp()
            if start
            else float("inf")
        )
        copied = []
        already_replaced = []
        backup = r / "run_manifest.preformal_20260905.json"
        history = json.loads(backup.read_text()) if backup.exists() else m
        historical_names = {v.get("log") for v in history.get("attempts", [])}
        for p in (r / "logs").glob("*.log"):
            if p.stat().st_mtime >= cutoff:
                if str(p.relative_to(r)) in historical_names:
                    already_replaced.append(str(p.relative_to(r)))
                continue
            shutil.copyfile(p, output / p.name)
            copied.append(
                {"log": str(p.relative_to(r)), "sha256": digest(output / p.name)}
            )
        a.atomic_json(
            report,
            {
                "copied": copied,
                "historical_logs_overwritten_before_archive": already_replaced,
                "note": "Historical manifests remain unchanged. Formal generation reused attempt numbers after resetting the attempt list; early overwritten preflight logs cannot be recovered and are explicitly listed. All later historical logs were archived before reuse.",
            },
        )
    print("PREFORMAL_LOG_ARCHIVE_CHECKED", len(runs), flush=True)


def formal(gpus):
    os.environ["SPATIALGEN_TABLE2_CANONICAL_ONLY"] = "1"
    run_lock = (B / "work/spatialgen/formal_execution.lock").open("a")
    fcntl.flock(run_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    lock = json.loads(
        (
            B / "methods/spatialgen/protocol/generation/spatialgen_formal.lock.json"
        ).read_text()
    )
    for path, value in lock["sources"].items():
        assert digest(B / path) == value, path
    specs = a.load_specs(a.DEFAULT_SPEC_FILE)
    tasks = [(s, seed) for s in specs.values() for seed in range(4)]
    active = active_formal_adapters()
    tasks.sort(key=lambda item: (item[0]["spec_id"], item[1]) in active)
    print("DEFERRED_EXISTING_ADAPTERS", active, flush=True)
    pending = queue_module.Queue()
    for item in tasks:
        pending.put(item)
    report_lock = threading.Lock()
    abort = threading.Event()
    progress = B / "results/spatialgen/formal_resume_progress.jsonl"

    def gpu_free(gpu):
        return int(
            subprocess.check_output(
                [
                    "nvidia-smi",
                    f"--id={gpu}",
                    "--query-gpu=memory.free",
                    "--format=csv,noheader,nounits",
                ],
                text=True,
            ).strip()
        )

    def wait_stable_gpu(gpu):
        """Require the frozen memory guard twice before launching a stage."""
        while not abort.is_set():
            first = gpu_free(gpu)
            if first >= 40000:
                time.sleep(5)
                second = gpu_free(gpu)
                if second >= 40000:
                    return second
            print("FORMAL_WAIT_STABLE_GPU", gpu, first, flush=True)
            time.sleep(25)
        raise RuntimeError("Formal queue aborted while waiting for GPU")

    def eligible_items(gpu):
        last_wait = None
        while not abort.is_set() and not pending.empty():
            free = gpu_free(gpu)
            if free < 40000:
                if last_wait is None or time.monotonic() - last_wait > 600:
                    print("FORMAL_WAIT_GPU", gpu, free, flush=True)
                    last_wait = time.monotonic()
                time.sleep(30)
                continue
            try:
                yield pending.get_nowait()
            except queue_module.Empty:
                return

    def queue(gpu):
        for spec, seed in eligible_items(gpu):
            if abort.is_set():
                return
            while (spec["spec_id"], seed) in active_formal_adapters():
                print("WAIT_EXISTING_ADAPTER", spec["spec_id"], seed, flush=True)
                time.sleep(30)
            r = a.run_directory(B / "data/table2", spec, seed)
            m = json.loads((r / "run_manifest.json").read_text())
            if m.get("formal_terminal_status"):
                print(
                    "FORMAL_SKIP_TERMINAL",
                    spec["spec_id"],
                    seed,
                    m["formal_terminal_status"],
                    flush=True,
                )
                continue
            wait_stable_gpu(gpu)
            if shutil.disk_usage(B).free < 100 * 1024**3:
                raise RuntimeError("Disk guard: below 100 GiB")
            r = initialize_formal(spec, seed)
            terminal = "formal_success"
            for phase in ["reference", "generate", "render"]:
                if (
                    phase == "reference"
                    and (r / "REFERENCE_SUCCESS").exists()
                    and a._reference_output_valid(r, spec, seed)
                ):
                    continue
                previous = json.loads((r / "run_manifest.json").read_text())["attempts"]
                failed = sum(
                    v["phase"] == phase
                    and not v["success"]
                    and not v.get("excluded_from_retry_budget")
                    for v in previous
                )
                if failed >= 2:
                    terminal = "infrastructure_failure"
                    break
                for retry in range(failed, 2):
                    free_at_launch = wait_stable_gpu(gpu)
                    print(
                        "FORMAL_STAGE_START",
                        spec["spec_id"],
                        seed,
                        phase,
                        gpu,
                        flush=True,
                    )
                    cmd = [
                        str(PYTHON),
                        str(B / "methods/spatialgen/adapter.py"),
                        "run",
                        "--spec-id",
                        spec["spec_id"],
                        "--seed",
                        str(seed),
                        "--data-root",
                        str(B / "data/table2"),
                        "--phase",
                        phase,
                        "--gpu",
                        str(gpu),
                        "--flux-offload",
                        "sequential",
                    ]
                    log = (
                        B
                        / "work/spatialgen/formal_20260905"
                        / f"{spec['spec_id']}_seed_{seed}_{phase}.log"
                    )
                    try:
                        command(cmd, gpu, log)
                        break
                    except RuntimeError:
                        m = json.loads((r / "run_manifest.json").read_text())
                        last = m["attempts"][-1]
                        last["scheduler_free_mib_before_launch"] = free_at_launch
                        last["scheduler_free_mib_after_failure"] = gpu_free(gpu)
                        a.atomic_json(r / "run_manifest.json", m)
                        if (
                            phase == "render"
                            and last["exit_code"] == 0
                            and not last["timed_out"]
                            and not a.log_has_traceback(r / last["log"])
                        ):
                            terminal = "quality_failure"
                            break
                        if retry == 1:
                            terminal = "infrastructure_failure"
                            break
                if terminal != "formal_success":
                    break
            m = json.loads((r / "run_manifest.json").read_text())
            m["formal_terminal_status"] = terminal
            m["formal_trial_ended_at_utc"] = a.utc_now()
            m[
                "stage_seed_policy"
            ] = "FLUX and MVD use method_seed; official Sparse-RaDeGS reconstruction retains its hardcoded safe_state seed 0."
            a.atomic_json(r / "run_manifest.json", m)
            row = {
                "spec_id": spec["spec_id"],
                "logical_seed": seed,
                "status": terminal,
                "gpu": gpu,
                "ended_at_utc": m["formal_trial_ended_at_utc"],
            }
            with report_lock:
                with progress.open("a") as f:
                    f.write(json.dumps(row) + "\n")
            print("FORMAL_ITEM_END", row, flush=True)
            if terminal == "infrastructure_failure":
                abort.set()
                raise RuntimeError(
                    "Formal queue paused after exhausted infrastructure retries; inspect logs before continuing other items."
                )

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(gpus)) as pool:
        futures = [pool.submit(queue, gpu) for gpu in gpus]
        for future in concurrent.futures.as_completed(futures):
            future.result()


def active_formal_adapters():
    import shlex

    output = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    active = {}
    for line in output.splitlines()[1:]:
        pid, _, args = line.strip().partition(" ")
        if str(B / "methods/spatialgen/adapter.py") not in args:
            continue
        words = shlex.split(args)
        if "--data-root" not in words or words[words.index("--data-root") + 1] != str(
            B / "data/table2"
        ):
            continue
        if "--spec-id" not in words or "--seed" not in words:
            continue
        active[
            (words[words.index("--spec-id") + 1], int(words[words.index("--seed") + 1]))
        ] = int(pid)
    return active


def handoff_formal():
    import shlex

    output = subprocess.check_output(["ps", "-eo", "pid,args"], text=True)
    controllers = []
    for line in output.splitlines()[1:]:
        pid, _, args = line.strip().partition(" ")
        words = shlex.split(args)
        if (
            len(words) > 2
            and words[1]
            == str(B / "methods/spatialgen/tools/resume_spatialgen_experiment.py")
            and words[2] == "formal"
        ):
            controllers.append(int(pid))
    assert len(controllers) == 1, controllers
    pid = controllers[0]
    os.kill(pid, signal.SIGSTOP)
    try:
        active = active_formal_adapters()
        assert active, "No active stages to preserve"
        a.atomic_json(
            B / "results/spatialgen/formal_controller_handoff_20260905.json",
            {
                "at_utc": a.utc_now(),
                "retired_controller_pid": pid,
                "preserved_adapters": [
                    {"spec_id": key[0], "logical_seed": key[1], "pid": value}
                    for key, value in active.items()
                ],
                "reason": "Preserve existing training while allowing the new scheduler to use GPU capacity satisfying the frozen 40000 MiB gate. Active runs are deferred, then integrity-checked completed stages are reused.",
                "replacement_controller_sha256": digest(
                    B / "methods/spatialgen/tools/resume_spatialgen_experiment.py"
                ),
            },
        )
        os.kill(pid, signal.SIGTERM)
    finally:
        try:
            os.kill(pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
    for _ in range(100):
        path = Path("/proc") / str(pid) / "stat"
        if not path.exists() or path.read_text().split()[2] == "Z":
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Retired controller still exists")
    assert (
        active_formal_adapters() == active
    ), "Active adapters changed during handoff; inspect before relaunch"
    print("FORMAL_CONTROLLER_RETIRED_TRAINING_PRESERVED", active, flush=True)


def gate_overlapping_inference():
    import shlex

    rows = subprocess.check_output(
        ["ps", "-eo", "pid,ppid,args"], text=True
    ).splitlines()[1:]
    groups = {}
    for row in rows:
        pid, ppid, args = row.strip().split(None, 2)
        if (
            "src/inference_sd.py" not in args
            or str(B / "data/table2/indoor/spatialgen") not in args
        ):
            continue
        words = shlex.split(args)
        output = words[words.index("--output_dir") + 1]
        groups.setdefault(output, []).append((int(pid), int(ppid)))
    gated = []
    for output, pids in groups.items():
        if len(pids) < 2:
            continue
        old = [pid for pid, ppid in pids if ppid == 1]
        new = [pid for pid, ppid in pids if ppid != 1]
        assert len(old) == len(new) == 1, (output, pids)
        os.kill(new[0], signal.SIGSTOP)
        gated.append(
            {
                "output_dir": output,
                "preserved_native_pid": old[0],
                "waiting_native_pid": new[0],
            }
        )
    assert gated, "No overlapping inference processes found"
    report = B / "results/spatialgen/formal_native_wait_20260905.json"
    a.atomic_json(
        report,
        {
            "at_utc": a.utc_now(),
            "gated": gated,
            "incident": "Execution-session cleanup removed original adapter processes after the controller exited, while native inference/training sessions survived. Replacement adapter detection missed these orphaned native sessions. Replacement native processes were paused until original training completed; no completed stage is intentionally rerun.",
        },
    )
    print("WAITING_FOR_PRESERVED_NATIVE", gated, flush=True)
    try:
        for row in gated:
            pid = row["preserved_native_pid"]
            state = Path("/proc") / str(pid) / "stat"
            while state.exists() and state.read_text().split()[2] != "Z":
                time.sleep(10)
            outputs = list(
                Path(row["output_dir"]).glob(
                    "**/point_cloud/iteration_7000/point_cloud.ply"
                )
            )
            assert len(outputs) == 1 and outputs[0].stat().st_size > 0, (row, outputs)
            row["completed_ply_sha256"] = digest(outputs[0])
            row["resumed_at_utc"] = a.utc_now()
            os.kill(row["waiting_native_pid"], signal.SIGCONT)
            row["resumed"] = True
            print("PRESERVED_NATIVE_COMPLETED_RESUMED_VERIFIER", row, flush=True)
    finally:
        for row in gated:
            if not row.get("resumed"):
                try:
                    os.kill(row["waiting_native_pid"], signal.SIGCONT)
                except ProcessLookupError:
                    pass
        a.atomic_json(
            report,
            {
                "at_utc": a.utc_now(),
                "gated": gated,
                "incident": "Original adapters exited with retired controller session; original native training survived. New native processes were paused until original 7000-step outputs existed, then resumed to reuse verified artifacts.",
            },
        )


def correct_invalid_gpu_retry():
    r = B / "data/table2/indoor/spatialgen/indoor_bedroom_01/seed_0"
    p = r / "run_manifest.json"
    m = json.loads(p.read_text())
    failures = [
        x for x in m["attempts"] if x["phase"] == "generate" and not x["success"]
    ]
    assert len(failures) == 2 and all(
        x["exit_code"] == 1 and not x["timed_out"] for x in failures
    ), failures
    for item in failures:
        log = (r / item["log"]).read_text(errors="replace")
        assert "torch.cuda.OutOfMemoryError" in log
    failures[1]["excluded_from_retry_budget"] = True
    failures[1][
        "exclusion_reason"
    ] = "Scheduler retry launched immediately without reapplying frozen 40000 MiB GPU-free guard after an external process occupied GPU 5."
    m.pop("formal_terminal_status", None)
    m.pop("formal_trial_ended_at_utc", None)
    m["failure_reason"] = "infrastructure_retry_pending_after_invalid_scheduler_retry"
    a.atomic_json(p, m)
    report = B / "results/spatialgen/formal_gpu_retry_correction_20260905.json"
    a.atomic_json(
        report,
        {
            "at_utc": a.utc_now(),
            "spec_id": "indoor_bedroom_01",
            "logical_seed": 0,
            "kept_failure_logs": [x["log"] for x in failures],
            "decision": "Exclude only attempt 2 from retry budget and rerun the one allowed same-seed infrastructure retry after a stable 40000 MiB guard. Attempt 1 remains the original failed attempt.",
            "evidence": "Both attempts failed while moving the model to CUDA after GPU 5 was occupied by an external workload; attempt 2 was launched without a new memory check.",
            "scientific_outputs_changed": False,
            "quality_based_retry": False,
        },
    )
    print("INVALID_GPU_RETRY_CORRECTED", report, flush=True)


def document_status():
    pilot_runs = list(PILOT.glob("indoor/spatialgen/*/seed_*/run_manifest.json"))
    pilot_success = sum((p.parent / "SUCCESS").exists() for p in pilot_runs)
    text = """\n## 22. Actual Execution Record: SpatialGen\n\n<!-- SPATIALGEN_STATUS_START -->\n"""
    text += f"- This run only continues SpatialGen; check time `{a.utc_now()}`. All new tools, audits, logs, and outputs are located at `baselines/`. \n"
    text += "- Reuse `envs/spatialgen`, fixed SpatialGen/Sparse-RaDeGS source code with local FLUX, Wireframe LoRA, and SpatialGen weights; offline loading without re-downloading. \n"
    text += "- Verified 100 pre-generated inputs for formal `25 specs × 4 seeds`: current compiler output matches the existing spec/native/layout/camera JSON, preparation script SHA-256 is the same, all preparation files are complete. Audit see `results/spatialgen/formal_input_reuse_20260905.json`, no need for repeated rendering input. \n"
    text += "- All 10 pilot FLUX reference images before migration are already present; subsequent prepare reruns covered the first frame in model input. This time, we validated the condition image, 1024/512 reference images, and restored the first frame based on the original records, with 10/10 first frame SHA-256 values matching the original; retained the placeholder images before coverage, records see `results/spatialgen/reference_recovery_20260905.json`. \n"
    text += f"- The current pilot scenario is {pilot_success}/10; where the old `indoor_bedroom_00/seed_0` serves as a historical pilot saved through the current render integrity check and does not count towards formal statistics. Missing tasks continue to be generated from reference images after that point, with each task being gated by the available GPU memory using sequential selection. \n"
    text += "- Both CUDA extensions on this machine passed the forward pass; 16 tests including SpatialGen adapter, WorldScore input/method identification, and aggregation interface passed. All 14 core weight SHA-256 values fully match the fixed list; five automatic metric links and IQA repeated measurements were accepted. \n"
    text += "- The same as Seed MVD for 15 target RGB images with an output PSNR of 52.98 dB, average absolute error of 0.2214/255; different seeds show an average absolute error of 34.4260/255. The original array is not claimed to be bit-level deterministic; full record can be found at `results/spatialgen/reproducibility_20260905.json`. \n"
    text += "- Retain official seed behavior: FLUX and MVD use `method_seed = spec_index × 4 + logical_seed`; Sparse-RaDeGS uses an internal fixed seed of 0 for its official `safe_state` algorithm without modifications. \n"
    text += "- NFS lifecycle compatibility fix is applied only before closing shared resources sockets during DataLoader worker termination, preserving original worker initialization and random number behavior. After completing 7000 steps of Gaussian reconstruction, the native preview that is no longer needed will be skipped by the unified renderer, while still outputting 8 anchor point images and 50 frame sequences. The patch and backup files are located at `methods/spatialgen/environment/spatialgen/`. \n"
    if (
        B / "methods/spatialgen/environment/spatialgen/nfs_event_buffer_20260905.json"
    ).exists():
        text += "- In the initial formal run, NFS opens and closes TensorBoard event logs one by one, causing GPU training to wait for writes. Subsequently, formal `train.py` will start a dedicated `.pth` layer to buffer write event files and flush them upon exit; 64 fixed protobuf/TFRecord records are byte-consistent, reducing write time from 9.286 s to 0.204 s. The first batch of started processes retain the original writer; model, random numbers, loss, iteration, and scene files remain unchanged. Compatibility layer hash, installation time, and testing are seen in `methods/spatialgen/environment/spatialgen/nfs_event_buffer_20260905.json`. \n"
    text += "- Old pre-check logs have been archived to each run's `preformal_logs_20260905/` directory. Before number reuse was confirmed, `indoor_bedroom_00/seed_0`'s old `generate_attempt_01.log` had already been officially covered by the log; it cannot be restored. This audit restriction is explicitly retained in this directory's `archive.json`, with the old manifest and other historical logs still preserved. \n"
    lock = B / "methods/spatialgen/protocol/generation/spatialgen_formal.lock.json"
    formal_runs = list(
        (B / "data/table2/indoor/spatialgen").glob("*/seed_*/run_manifest.json")
    )
    manifests = [json.loads(p.read_text()) for p in formal_runs]
    terminals = [m for m in manifests if m.get("formal_terminal_status")]
    text += f'- Formal configuration freeze: {"Completed" if lock.exists() else "Pending"}; Formal completion {len(terminals)}/100, successful {sum(m.get("formal_terminal_status")=="formal_success" for m in terminals)} items. At least 40000 MiB of free GPU memory is required before starting a new scene on each GPU; capacity check actually runs when 41687 MiB of free memory is available, and it has not been proven that stable execution can occur at lower free levels. \n'
    text += '- The continuation run entry is `methods/spatialgen/tools/resume_spatialgen_experiment.py`; the task log is located at `work/spatialgen/resume_20260905/`, and the indicator "smoke" is located at `work/spatialgen/metric_smoke_20260905/`. \n'
    if not (B / "results/spatialgen/indoor/table2_full.json").exists():
        text += "- There are currently no official SpatialGen 100-run aggregated numbers available. \n"
    text += "- Layout Plausibility / Prompt Alignment According to the original plan, three real blind reviewers are needed; we have asked the user whether to switch to using three clearly labeled simulated score proxy values, and no simulated scores will be generated until instructions are received. \n<!-- SPATIALGEN_STATUS_END -->\n"
    p = B / "Comparison Experiment - Table 2.md"
    old = p.read_text()
    if "<!-- SPATIALGEN_STATUS_START -->" in old:
        start = old.index("## 22. Actual Execution Record: SpatialGen")
        end = old.index("<!-- SPATIALGEN_STATUS_END -->", start) + len(
            "<!-- SPATIALGEN_STATUS_END -->"
        )
        new = old[:start].rstrip() + text + old[end:]
    else:
        new = old.rstrip() + "\n" + text
    temp = p.with_suffix(".md.spatialgen.tmp")
    temp.write_text(new)
    temp.replace(p)
    print("DOCUMENT_STATUS_UPDATED", p, flush=True)


def nfs_probe():
    code = """import multiprocessing as mp
import multiprocessing.resource_sharer as sharer
import multiprocessing.util as util
import os, sys
def worker(q,event):
    if sys.argv[1]=='fixed': util.Finalize(None,sharer.stop,exitpriority=10)
    fd=os.open(__file__,os.O_RDONLY)
    q.put(sharer.DupFd(fd));q.close();q.join_thread()
    event.wait(30);os.close(fd)
if __name__=='__main__':
    mp.set_start_method('spawn')
    q=mp.Queue();event=mp.Event();p=mp.Process(target=worker,args=(q,event));p.start()
    value=q.get(timeout=30);fd=value.detach();print('PAYLOAD',os.read(fd,24));os.close(fd)
    event.set();p.join(30);q.close();q.join_thread();assert p.exitcode==0
"""
    path = B / "work/spatialgen/nfs_exit_probe.py"
    path.write_text(code)
    for mode in ["original", "fixed"]:
        command(
            [str(PYTHON), str(path), mode],
            0,
            B / f"work/spatialgen/nfs_exit_probe_{mode}.log",
        )
    fixed = (B / "work/spatialgen/nfs_exit_probe_fixed.log").read_text()
    assert "Traceback" not in fixed, fixed
    print("NFS_FINALIZER_PROBE_PASSED", flush=True)


def apply_nfs_patch():
    p = B / "vendor/SpatialGen/src/inference_sd.py"
    old = p.read_text()
    if "def nfs_safe_worker_init_fn" in old:
        return
    proc = subprocess.run(["ps", "-eo", "args"], text=True, stdout=subprocess.PIPE)
    # Apply between attempts so source fingerprints describe the code actually run.
    assert not any(
        "python src/inference_sd.py " in line for line in proc.stdout.splitlines()
    ), "Wait for active inference attempts to finish first"
    probe = (B / "work/spatialgen/nfs_exit_probe_fixed.log").read_text()
    assert "Traceback" not in probe and "PAYLOAD" in probe
    addition = """def nfs_safe_worker_init_fn(worker_id):
    # Preserve the official RNG initialization exactly. Close descriptor-sharing
    # sockets before multiprocessing unlinks them: open sockets on NFS otherwise
    # leave .nfs files that make temporary-directory finalization fail.
    worker_init_fn(worker_id)
    import multiprocessing.resource_sharer as resource_sharer
    import multiprocessing.util as multiprocessing_util
    multiprocessing_util.Finalize(None, resource_sharer.stop, exitpriority=10)


"""
    marker = "def compose_fixed_view_indices("
    assert marker in old and old.count("worker_init_fn=worker_init_fn,") == 1
    new = old.replace(marker, addition + marker, 1).replace(
        "worker_init_fn=worker_init_fn,", "worker_init_fn=nfs_safe_worker_init_fn,"
    )
    import ast, difflib

    ast.parse(new)
    backup = (
        B / "methods/spatialgen/environment/spatialgen/inference_sd.pre_nfs_20260905.py"
    )
    backup.write_text(old)
    diff = "".join(
        difflib.unified_diff(
            old.splitlines(True),
            new.splitlines(True),
            fromfile="inference_sd.py.before",
            tofile="inference_sd.py.after",
        )
    )
    (
        B / "methods/spatialgen/environment/spatialgen/nfs_finalizer_compat.patch"
    ).write_text(diff)
    temp = p.with_suffix(".py.nfs.tmp")
    temp.write_text(new)
    temp.replace(p)
    print("NFS_COMPAT_PATCH_APPLIED", digest(p), flush=True)


def recover_pilot_generation():
    import re

    for p in sorted(PILOT.glob("indoor/spatialgen/*/seed_*/run_manifest.json")):
        r = p.parent
        m = json.loads(p.read_text())
        if (r / "GENERATION_SUCCESS").exists():
            continue
        attempts = [v for v in m["attempts"] if v["phase"] == "generate"]
        if not attempts:
            continue
        last = attempts[-1]
        if last["exit_code"] != 0 or last["timed_out"]:
            continue
        log = r / last["log"]
        text = log.read_text(errors="replace")
        tracebacks = re.findall(
            r"Traceback \(most recent call last\):.*?OSError: \[Errno 16\] Device or resource busy: \'\.nfs[^\n]+",
            text,
            re.S,
        )
        assert (
            len(tracebacks) == text.count("Traceback (most recent call last):")
            and tracebacks
        ), (log, "unexpected traceback")
        for block in tracebacks:
            assert (
                "multiprocessing/util.py" in block
                and "_remove_temp_dir" in block
                and block.count("Traceback") == 1
            )
        archives = list((r / "scene/native").glob("**/inference_results.npz"))
        gaussians = list(
            (r / "scene/native").glob("**/point_cloud/iteration_7000/point_cloud.ply")
        )
        assert len(archives) == len(gaussians) == 1 and a._valid_mvd_archive(
            archives[0]
        ), r
        with gaussians[0].open("rb") as f:
            header = f.read(4096)
        assert (
            b"element vertex " in header
            and b"property float opacity" in header
            and gaussians[0].stat().st_size > 1024 * 1024
        )
        m["verified_generation_recovery"] = {
            "verified_at_utc": a.utc_now(),
            "original_attempt_log_sha256": digest(log),
            "inference_results_sha256": digest(archives[0]),
            "gaussian_sha256": digest(gaussians[0]),
            "basis": "Original generation and reconstruction exited 0; the only traceback is the independently reproduced multiprocessing NFS finalizer error. Complete ZIP payload and final 7000-step Gaussian verified. No model execution repeated.",
            "original_failed_attempt_preserved": True,
            "table2_eligible": False,
        }
        m["generation_success"] = True
        m["failure_reason"] = None
        m["native_inference_results"] = str(archives[0].relative_to(r))
        m["native_gaussian"] = str(gaussians[0].relative_to(r))
        a.atomic_json(p, m)
        (r / "GENERATION_SUCCESS").touch()
        print("PILOT_GAUSSIAN_RECOVERED", m["spec_id"], m["logical_seed"], flush=True)


def repeat_iqa(gpu):
    result = B / "work/spatialgen/metric_smoke_20260905"
    command(
        [
            f"{_wb_WORLDBRIDGE_PYTHON}",
            str(B / "evaluation/visual/eval_iqa.py"),
            "--data-root",
            str(PILOT),
            "--method",
            "spatialgen",
            "--domain",
            "indoor",
            "--spec-id",
            "indoor_bedroom_00",
            "--seed",
            "0",
            "--device",
            "cuda",
            "--output",
            str(result / "iqa_repeat.jsonl"),
        ],
        gpu,
        result / "iqa_repeat.log",
    )
    x = json.loads((result / "iqa.jsonl").read_text())
    y = json.loads((result / "iqa_repeat.jsonl").read_text())
    for key in ["qalign", "clipiqa_plus"]:
        assert abs(x[key] - y[key]) < 1e-5, (key, x[key], y[key])
    (result / "iqa_repeat.done").touch()
    print("IQA_REPEAT_STABLE", flush=True)


def stop_waiting_pilot():
    lines = subprocess.check_output(
        ["ps", "-eo", "pid,ppid,args"], text=True
    ).splitlines()[1:]
    rows = [line.strip().split(None, 2) for line in lines]
    parents = [
        int(row[0])
        for row in rows
        if len(row) == 3 and "/tools/resume_spatialgen_experiment.py pilot " in row[2]
    ]
    for pid in parents:
        children = [row for row in rows if int(row[1]) == pid]
        if any("methods/spatialgen/adapter.py" in row[2] for row in children):
            print("PRESERVED_ACTIVE_PILOT_CONTROLLER", pid, flush=True)
            continue
        os.kill(pid, signal.SIGTERM)
        print("STOPPED_IDLE_PILOT_CONTROLLER", pid, flush=True)


def diversity_smoke(gpu):
    result = B / "work/spatialgen/metric_smoke_20260905"
    spec = a.load_specs(a.DEFAULT_SPEC_FILE)["indoor_bathroom_00"]
    spec_file = result / "bathroom_spec.jsonl"
    spec_file.write_text(json.dumps(spec) + "\n")
    common = [
        "--data-root",
        str(PILOT),
        "--spec-file",
        str(spec_file),
        "--method",
        "spatialgen",
        "--domain",
        "indoor",
        "--device",
        "cuda",
    ]
    python = f"{_wb_WORLDBRIDGE_PYTHON}"
    command(
        [
            python,
            str(B / "evaluation/visual/generate_semantics.py"),
            *common,
            "--metadata-output",
            str(result / "bathroom_semantic.json"),
        ],
        gpu,
        result / "bathroom_semantic.log",
    )
    command(
        [
            python,
            str(B / "evaluation/visual/eval_diversity.py"),
            *common,
            "--output",
            str(result / "diversity.jsonl"),
        ],
        gpu,
        result / "diversity.log",
    )
    row = json.loads((result / "diversity.jsonl").read_text())
    assert row["valid_seeds"] == [0, 1], row
    (result / "diversity.done").touch()
    print("DIVERSITY_SMOKE_OK", flush=True)


def render_ready(gpu):
    for p in sorted(PILOT.glob("indoor/spatialgen/*/seed_*/run_manifest.json")):
        r = p.parent
        if (r / "SUCCESS").exists() or not (r / "GENERATION_SUCCESS").exists():
            continue
        m = json.loads(p.read_text())
        command(
            [
                str(PYTHON),
                str(B / "methods/spatialgen/adapter.py"),
                "run",
                "--phase",
                "render",
                "--data-root",
                str(PILOT),
                "--spec-id",
                m["spec_id"],
                "--seed",
                str(m["logical_seed"]),
                "--gpu",
                str(gpu),
            ],
            gpu,
            B
            / "work/spatialgen/resume_20260905"
            / f"ready_{m['spec_id']}_seed_{m['logical_seed']}_render.log",
        )


def metrics_final(gpu):
    runs = list(
        (B / "data/table2/indoor/spatialgen").glob("*/seed_*/run_manifest.json")
    )
    assert len(runs) == 100 and all(
        json.loads(p.read_text()).get("formal_terminal_status")
        in ["formal_success", "quality_failure", "infrastructure_failure"]
        for p in runs
    ), "Formal matrix is incomplete; refusing to score unstarted runs as failures"
    evaluation_lock()
    assert audit_formal(gpu)["complete"], "Formal provenance audit failed"
    result = B / "results/spatialgen/indoor"
    result.mkdir(parents=True, exist_ok=True)
    common = [
        "--data-root",
        str(B / "data/table2"),
        "--spec-file",
        str(a.DEFAULT_SPEC_FILE),
        "--method",
        "spatialgen",
        "--domain",
        "indoor",
    ]
    iqa = f"{_wb_WORLDBRIDGE_PYTHON}"
    jobs = [
        (
            "semantic",
            [
                iqa,
                str(B / "evaluation/visual/generate_semantics.py"),
                *common,
                "--device",
                "cuda",
                "--metadata-output",
                str(result / "semantic_model.json"),
            ],
            "semantic_model.json",
            None,
        ),
        (
            "iqa",
            [
                iqa,
                str(B / "evaluation/visual/eval_iqa.py"),
                *common,
                "--device",
                "cuda",
                "--output",
                str(result / "iqa_per_scene.jsonl"),
            ],
            "iqa_per_scene.jsonl",
            100,
        ),
        (
            "consistency",
            [
                str(B / "envs/worldscore/bin/python"),
                str(B / "evaluation/visual/eval_worldscore.py"),
                *common,
                "--gpu",
                str(gpu),
                "--output",
                str(result / "consistency_per_scene.jsonl"),
            ],
            "consistency_per_scene.jsonl",
            100,
        ),
        (
            "diversity",
            [
                iqa,
                str(B / "evaluation/visual/eval_diversity.py"),
                *common,
                "--device",
                "cuda",
                "--output",
                str(result / "diversity_per_spec.jsonl"),
            ],
            "diversity_per_spec.jsonl",
            25,
        ),
    ]
    for name, cmd, filename, count in jobs:
        output = result / filename
        marker = result / (name + ".completion.json")
        if (
            marker.exists()
            and output.exists()
            and json.loads(marker.read_text())["output_sha256"] == digest(output)
        ):
            continue
        command(
            cmd,
            gpu,
            B / "work/spatialgen/formal_metrics" / f"{name}.log",
            name == "consistency",
        )
        if count is not None:
            assert len([x for x in output.read_text().splitlines() if x]) == count
        a.atomic_json(
            marker,
            {
                "completed_at_utc": a.utc_now(),
                "output_sha256": digest(output),
                "command": cmd,
            },
        )
    package = B / "annotations/spatialgen/indoor"
    if not (package / "PRIVATE_blind_map.json").exists():
        command(
            [
                str(PYTHON),
                str(B / "tools/make_annotation_package.py"),
                *common,
                "--output",
                str(package),
            ],
            gpu,
            B / "work/spatialgen/formal_metrics/package.log",
        )
    command(
        [
            str(PYTHON),
            str(B / "evaluation/visual/aggregate_generation.py"),
            *common,
            "--protocol",
            str(B / "methods/spatialgen/protocol/generation/spatialgen_protocol.yaml"),
            "--results-root",
            str(result),
        ],
        gpu,
        B / "work/spatialgen/formal_metrics/aggregate.log",
    )
    print("AUTOMATED_METRICS_AND_RATING_PACKAGE_COMPLETE", flush=True)


def evaluation_lock():
    path = B / "methods/spatialgen/protocol/generation/spatialgen_evaluation.lock.json"
    sources = {
        str(p.relative_to(B)): digest(p)
        for p in [
            B / "evaluation/visual" / f
            for f in [
                "eval_iqa.py",
                "eval_worldscore.py",
                "eval_diversity.py",
                "generate_semantics.py",
                "aggregate_generation.py",
                "import_human_ratings.py",
            ]
        ]
        + [
            B / f
            for f in [
                "tools/make_annotation_package.py",
                "methods/spatialgen/tools/audit_spatialgen_matrix.py",
            ]
        ]
    }
    if path.exists():
        assert (
            json.loads(path.read_text())["sources"] == sources
        ), "Evaluation source drift"
        return
    code = 'import importlib.metadata as m,json; print(json.dumps({k:m.version(k) for k in ["pyiqa","torch","torchvision","transformers","lpips"]}))'
    versions = json.loads(
        subprocess.check_output([f"{_wb_WORLDBRIDGE_PYTHON}", "-c", code], text=True)
    )
    a.atomic_json(
        path,
        {
            "frozen_at_utc": a.utc_now(),
            "sources": sources,
            "iqa_python": f"{_wb_WORLDBRIDGE_PYTHON}",
            "iqa_versions": versions,
            "iqa_repeat_max_abs_tolerance": 1e-5,
            "bootstrap_unit": "spec_id",
            "bootstrap_replicates": 10000,
            "bootstrap_seed": 20260827,
            "worldscore_python": str(B / "envs/worldscore/bin/python"),
            "human_ratings": "three actual independent raters; synthetic proxy requires explicit instruction for SpatialGen",
        },
    )
    print("EVALUATION_FROZEN", digest(path), flush=True)


def audit_formal(gpu):
    command(
        [str(PYTHON), str(B / "methods/spatialgen/tools/audit_spatialgen_matrix.py")],
        gpu,
        B / "work/spatialgen/formal_metrics/matrix_audit.log",
    )
    j = json.loads((B / "results/spatialgen/matrix_audit.json").read_text())
    print("FORMAL_AUDIT", j["counts"], j["complete"], flush=True)
    return j


def write_table(gpu):
    import math

    runs = list(
        (B / "data/table2/indoor/spatialgen").glob("*/seed_*/run_manifest.json")
    )
    assert len(runs) == 100 and all(
        json.loads(p.read_text()).get("formal_terminal_status") for p in runs
    ), "Refusing table update: formal matrix is incomplete"
    audit = audit_formal(gpu)
    assert audit["complete"], "Formal provenance audit failed"
    result = B / "results/spatialgen/indoor/table2_full.json"
    full = json.loads(result.read_text())
    assert full["method"] == "spatialgen" and full["domain"] == "indoor"
    automatic = [
        "qalign",
        "clipiqa_plus",
        "consistency_3d",
        "appearance_diversity_itt",
        "layout_diversity_itt",
    ]
    assert all(
        full["metrics"][k]["status"] == "complete"
        and full["metrics"][k]["spec_count"] == 25
        and math.isfinite(full["metrics"][k]["mean"])
        for k in automatic
    )
    names = [
        "qalign",
        "clipiqa_plus",
        "layout_plausibility",
        "prompt_alignment",
        "consistency_3d",
        "appearance_diversity_itt",
        "layout_diversity_itt",
    ]
    precisions = [2, 3, 1, 1, 1, 3, 3]
    values = []
    for key, precision in zip(names, precisions):
        item = full["metrics"][key]
        values.append(
            f'{item["mean"]:.{precision}f}'
            if item["status"] == "complete"
            else "Awaiting three-person blind review"
        )
    row = "| SpatialGen (Indoor) | " + " | ".join(values) + " |"
    document_status()
    p = B / "Comparison Experiment - Table 2.md"
    old = p.read_text()
    lines = old.splitlines()
    matched = [
        i for i, line in enumerate(lines) if line.startswith("| SpatialGen (Indoor) |")
    ]
    assert len(matched) <= 1
    if matched:
        lines[matched[0]] = row
    else:
        anchor = next(
            i
            for i, line in enumerate(lines)
            if line.startswith("| WorldGen (Indoor) |")
        )
        lines.insert(anchor, row)
    note = (
        "- Official ITT automatic indicators with 95% spec-cluster bootstrap confidence interval:"
        + "; ".join(
            f'{k}={full["metrics"][k]["mean"]:.6f} [{full["metrics"][k]["ci95"][0]:.6f}, {full["metrics"][k]["ci95"][1]:.6f}]'
            for k in automatic
        )
        + "The complete result is `results/spatialgen/indoor/table2_full.json` (SHA-256)"
        + digest(result)
        + "The anonymous annotated package is located at `annotations/spatialgen/indoor/`."
    )
    marker = lines.index("<!-- SPATIALGEN_STATUS_END -->")
    lines.insert(marker, note)
    new = "\n".join(lines) + "\n"
    assert p.read_text() == old, "Concurrent document edit; retry update"
    temp = p.with_suffix(".md.spatialgen.tmp")
    temp.write_text(new)
    temp.replace(p)
    print("SPATIALGEN_TABLE_UPDATED", row, flush=True)


def pilot_review():
    sys.path.insert(0, str(B.parent))
    from baselines.tools.make_annotation_package import make_montage

    output = B / "work/spatialgen/pilot_review"
    output.mkdir(parents=True, exist_ok=True)
    rows = []
    for p in sorted(PILOT.glob("indoor/spatialgen/*/seed_*/run_manifest.json")):
        r = p.parent
        m = json.loads(p.read_text())
        success = (r / "SUCCESS").exists()
        row = {
            "spec_id": m["spec_id"],
            "logical_seed": m["logical_seed"],
            "complete": success,
        }
        if success:
            path = output / f"{m['spec_id']}_seed_{m['logical_seed']}.jpg"
            if not path.exists():
                make_montage(
                    sorted((r / "renders/anchors").glob("rgb_*.png")),
                    path,
                    path.stem,
                    "indoor",
                )
            row["montage"] = str(path)
        rows.append(row)
    a.atomic_json(
        B / "results/spatialgen/pilot_progress.json",
        {
            "checked_at_utc": a.utc_now(),
            "complete_count": sum(r["complete"] for r in rows),
            "runs": rows,
            "controller_handoff_note": "During the 2026-09-05 resource-gate transition, indoor_bathroom_00/seed_1 was rendered a second time (26.7 s). No model generation was repeated; both controller log lines remain in resume_20260905. The obsolete controller was stopped and future pilot controllers use an exclusive execution lock.",
        },
    )
    print("PILOT_REVIEW_READY", sum(r["complete"] for r in rows), flush=True)


def profile_memory(duration_s):
    import csv

    started = time.monotonic()
    maxima = {}
    rows = []
    while time.monotonic() - started < duration_s:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,gpu_uuid,process_name,used_gpu_memory",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        )
        totals = {}
        processes = []
        for row in csv.reader(output.splitlines()):
            if len(row) != 4 or "/envs/spatialgen/" not in row[2]:
                continue
            pid, uuid, name, memory = [x.strip() for x in row]
            if not memory.isdigit():
                continue
            memory = int(memory)
            totals[uuid] = totals.get(uuid, 0) + memory
            processes.append({"pid": int(pid), "gpu_uuid": uuid, "memory_mib": memory})
        for uuid, value in totals.items():
            maxima[uuid] = max(value, maxima.get(uuid, 0))
        rows.append(
            {
                "elapsed_s": round(time.monotonic() - started, 2),
                "spatialgen_gpu_totals_mib": totals,
                "processes": processes,
            }
        )
        if len(rows) % 10 == 0:
            a.atomic_json(
                B / "results/spatialgen/gpu_memory_profile_20260905.json",
                {"complete": False, "peak_mib_by_gpu": maxima, "samples": rows},
            )
        time.sleep(1)
    a.atomic_json(
        B / "results/spatialgen/gpu_memory_profile_20260905.json",
        {"complete": True, "peak_mib_by_gpu": maxima, "samples": rows},
    )
    print("GPU_MEMORY_PROFILE_COMPLETE", maxima, flush=True)


def skip_native_previews():
    p = B / "vendor/SpatialGen/src/inference_sd.py"
    old = p.read_text()
    if "SPATIALGEN_TABLE2_CANONICAL_ONLY" in old:
        return
    protocol = B / "methods/spatialgen/protocol/generation/spatialgen_protocol.yaml"
    text = protocol.read_text()
    assert "status: preflight" in text, "Do not alter a frozen protocol"
    proc = subprocess.check_output(["ps", "-eo", "args"], text=True)
    assert not any(
        "python src/inference_sd.py " in line for line in proc.splitlines()
    ), "Wait for active inference attempts to finish first"
    marker = "        gs_render_command = [\n"
    assert old.count(marker) == 1
    addition = """        # The Table-2 renderer consumes only the completed NPZ and Gaussian PLY.
        # Its 8 anchors and 50 sequence frames replace these unused diagnostic
        # training views and 240-frame previews; reconstruction is unchanged.
        if os.environ.get("SPATIALGEN_TABLE2_CANONICAL_ONLY") == "1":
            logger.info("Table-2 mode: use canonical renderer; skip native previews")
            continue

"""
    new = old.replace(marker, addition + marker)
    memory_marker = (
        "    del rooms_infer_res_dict, val_loader, val_dataset, pipeline, unet\n"
    )
    assert new.count(memory_marker) == 1
    memory_log = """    print("SPATIALGEN_MVD_MEMORY_JSON=" + json.dumps({
        "peak_allocated_mib": torch.cuda.max_memory_allocated() / (1024 ** 2),
        "peak_reserved_mib": torch.cuda.max_memory_reserved() / (1024 ** 2),
    }), flush=True)
"""
    new = new.replace(memory_marker, memory_log + memory_marker)
    final_call = "    run_gaussian_reconstruction(infer_dir)\n        \nif __name__"
    assert new.count(final_call) == 1
    new = new.replace(
        final_call,
        '    if os.environ.get("SPATIALGEN_TABLE2_MVD_ONLY") == "1":\n        return\n'
        + final_call,
    )
    new = new.replace(
        "        run_gaussian_reconstruction(infer_dir)\n        return\n",
        '        if os.environ.get("SPATIALGEN_TABLE2_MVD_ONLY") != "1":\n            run_gaussian_reconstruction(infer_dir)\n        return\n',
        1,
    )
    import ast, difflib

    ast.parse(new)
    (
        B
        / "methods/spatialgen/environment/spatialgen/inference_sd.before_preview_policy.py"
    ).write_text(old)
    (
        B / "methods/spatialgen/environment/spatialgen/canonical_only_preview.patch"
    ).write_text(
        "".join(
            difflib.unified_diff(
                old.splitlines(True),
                new.splitlines(True),
                fromfile="inference_sd.py.before",
                tofile="inference_sd.py.after",
            )
        )
    )
    temp = p.with_suffix(".py.preview.tmp")
    temp.write_text(new)
    temp.replace(p)
    text = text.replace(
        "    iterations: 7000\n",
        "    iterations: 7000\n    native_diagnostic_previews_in_formal: false\n    canonical_table2_renders_in_formal: true\n",
    )
    temp = protocol.with_suffix(".yaml.preview.tmp")
    temp.write_text(text)
    temp.replace(protocol)
    print("CANONICAL_ONLY_PREVIEW_POLICY_READY", digest(p), flush=True)


def capacity_probe(gpu):
    source = PILOT / "indoor/spatialgen/indoor_bathroom_00/seed_0"
    dest = B / "work/spatialgen/capacity_probe_20260905"
    dest.mkdir(parents=True, exist_ok=True)
    if (dest / "verification.json").exists():
        print("CAPACITY_PROBE_ALREADY_VERIFIED")
        return
    free = int(
        subprocess.check_output(
            [
                "nvidia-smi",
                f"--id={gpu}",
                "--query-gpu=memory.free",
                "--format=csv,noheader,nounits",
            ],
            text=True,
        ).strip()
    )
    assert free >= 28000, free
    if not (dest / "input").exists():
        shutil.copytree(source / "input", dest / "input")
    m = json.loads((source / "run_manifest.json").read_text())
    previous = [v for v in m["attempts"] if v["phase"] == "generate"][-1]
    cmd = list(previous["command"])
    for i, value in enumerate(cmd):
        if str(source) in value:
            cmd[i] = value.replace(str(source), str(dest))
    # Some historical paths used /data aliases; normalize only path arguments.
    for i, value in enumerate(cmd):
        if value.startswith("/") and "/indoor_bathroom_00/seed_0" in value:
            cmd[i] = value.replace(str(source), str(dest))
    assert str(dest / "scene/native") in cmd, cmd
    env = a.baseline_environment(gpu)
    env["SPATIALGEN_TABLE2_MVD_ONLY"] = "1"
    env["SPATIALGEN_TABLE2_CANONICAL_ONLY"] = "1"
    execution = dest / "execution.json"
    if not execution.exists() or json.loads(execution.read_text())["exit_code"] != 0:
        code, wall, timed = a.run_logged(
            cmd, dest / "probe.log", env, 3600, B / "vendor/SpatialGen"
        )
        a.atomic_json(
            execution,
            {
                "command": cmd,
                "gpu": gpu,
                "free_mib_at_start": free,
                "exit_code": code,
                "wall_time_s": wall,
                "timed_out": timed,
                "table2_eligible": False,
            },
        )
        assert code == 0 and not timed, (code, timed)
    import numpy as np, re

    original = next((source / "scene/native").glob("**/inference_results.npz"))
    generated = next((dest / "scene/native").glob("**/inference_results.npz"))
    assert a._valid_mvd_archive(generated)
    with np.load(original, allow_pickle=True) as z:
        x = z[z.files[0]][()]
    with np.load(generated, allow_pickle=True) as z:
        y = z[z.files[0]][()]
    differences = {}
    assert x.keys() == y.keys()

    def compare(key, left, right):
        if isinstance(left, list):
            assert isinstance(right, list) and len(left) == len(right), (
                key,
                "list lengths",
            )
            for index, (xx, yy) in enumerate(zip(left, right)):
                compare(f"{key}[{index}]", xx, yy)
            return
        xx = np.asarray(left)
        yy = np.asarray(right)
        assert xx.shape == yy.shape, (key, xx.shape, yy.shape)
        if np.issubdtype(xx.dtype, np.number):
            with np.errstate(invalid="ignore"):
                delta = np.abs(xx.astype(np.float64) - yy.astype(np.float64))
                differences[key] = {
                    "max_abs_difference": float(np.nanmax(delta, initial=0.0)),
                    "equal": bool(np.array_equal(xx, yy, equal_nan=True)),
                }

    for key in x:
        compare(key, x[key], y[key])
    text = (dest / "probe.log").read_text()
    records = re.findall(r"SPATIALGEN_MVD_MEMORY_JSON=(\{[^\n]+\})", text)
    assert records, text[-1000:]
    result = {
        "table2_eligible": False,
        "purpose": "same-seed MVD reproducibility and live-memory capacity verification",
        "method_seed": 60,
        "source_run": str(source),
        "gpu": gpu,
        "memory": json.loads(records[-1]),
        "differences": differences,
        "all_numeric_outputs_equal": all(v["equal"] for v in differences.values()),
        "original_npz_sha256": digest(original),
        "probe_npz_sha256": digest(generated),
    }
    a.atomic_json(dest / "verification.json", result)
    print(
        "CAPACITY_AND_REPRODUCIBILITY_PROBE",
        json.dumps(
            {
                "memory": result["memory"],
                "numeric_arrays": len(differences),
                "all_equal": result["all_numeric_outputs_equal"],
            }
        ),
        flush=True,
    )


def characterize_reproduction():
    import numpy as np

    dest = B / "results/spatialgen/reproducibility_20260905.json"
    if dest.exists():
        return
    original = next(
        (PILOT / "indoor/spatialgen/indoor_bathroom_00/seed_0/scene/native").glob(
            "**/inference_results.npz"
        )
    )
    repeat = next(
        (B / "work/spatialgen/capacity_probe_20260905/scene/native").glob(
            "**/inference_results.npz"
        )
    )
    other = next(
        (PILOT / "indoor/spatialgen/indoor_bathroom_00/seed_1/scene/native").glob(
            "**/inference_results.npz"
        )
    )

    def rgb(p):
        with np.load(p, allow_pickle=True) as z:
            return np.stack(z[z.files[0]][()]["target_rgbs"]).astype(np.float32)

    x = rgb(original)

    def stats(p):
        delta = np.abs(x - rgb(p))
        rmse = float(np.sqrt(np.mean(delta**2)))
        return {
            "rgb_shape": list(x.shape),
            "mae_0_255": float(delta.mean()),
            "rmse_0_255": rmse,
            "psnr_db": float(20 * np.log10(255 / rmse)),
            "p99_absolute_error": float(np.percentile(delta, 99)),
            "maximum_absolute_error": float(delta.max()),
            "npz_sha256": digest(p),
        }

    report = {
        "table2_eligible": False,
        "original_npz_sha256": digest(original),
        "same_seed_60": stats(repeat),
        "different_seed_61": stats(other),
        "bitwise_deterministic": False,
        "interpretation": "Same-seed MVD outputs are numerically close but not bit-identical. Native stochastic algorithms and CUDA kernels are retained; no output-based tuning.",
        "capacity_probe_execution": json.loads(
            (B / "work/spatialgen/capacity_probe_20260905/execution.json").read_text()
        ),
        "capacity_probe_verification_sha256": digest(
            B / "work/spatialgen/capacity_probe_20260905/verification.json"
        ),
    }
    a.atomic_json(dest, report)
    print("REPRODUCIBILITY_RECORDED", report["same_seed_60"], flush=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "phase",
        choices=[
            "recover",
            "pilot",
            "status",
            "metrics-smoke",
            "test",
            "validate-assets",
            "formal-preflight",
            "freeze",
            "formal",
            "document-status",
            "nfs-probe",
            "apply-nfs-patch",
            "recover-pilot-generation",
            "repeat-iqa",
            "stop-waiting-pilot",
            "diversity-smoke",
            "render-ready",
            "metrics-final",
            "pilot-review",
            "profile-memory",
            "skip-native-previews",
            "capacity-probe",
            "archive-preformal-logs",
            "io-diagnostics",
            "evaluation-lock",
            "audit-formal",
            "write-table",
            "nfs-event-buffer",
            "nfs-buffer-smoke",
            "handoff-formal",
            "gate-overlapping-inference",
            "correct-invalid-gpu-retry",
        ],
    )
    p.add_argument("--gpus", nargs="+", type=int, default=[4, 5, 6])
    p.add_argument("--items", nargs="+")
    p.add_argument("--duration-s", type=int, default=600)
    args = p.parse_args()
    if args.phase == "recover":
        recover()
    elif args.phase == "pilot":
        pilot(args.gpus, args.items)
    elif args.phase == "status":
        status()
    elif args.phase == "metrics-smoke":
        metrics_smoke(args.gpus[0])
    elif args.phase == "test":
        test()
    elif args.phase == "validate-assets":
        validate_assets()
    elif args.phase == "formal-preflight":
        formal_preflight()
    elif args.phase == "freeze":
        freeze()
    elif args.phase == "formal":
        formal(args.gpus)
    elif args.phase == "document-status":
        document_status()
    elif args.phase == "nfs-probe":
        nfs_probe()
    elif args.phase == "apply-nfs-patch":
        apply_nfs_patch()
    elif args.phase == "recover-pilot-generation":
        recover_pilot_generation()
    elif args.phase == "repeat-iqa":
        repeat_iqa(args.gpus[0])
    elif args.phase == "stop-waiting-pilot":
        stop_waiting_pilot()
    elif args.phase == "diversity-smoke":
        diversity_smoke(args.gpus[0])
    elif args.phase == "render-ready":
        render_ready(args.gpus[0])
    elif args.phase == "metrics-final":
        metrics_final(args.gpus[0])
    elif args.phase == "pilot-review":
        pilot_review()
    elif args.phase == "profile-memory":
        profile_memory(args.duration_s)
    elif args.phase == "skip-native-previews":
        skip_native_previews()
    elif args.phase == "capacity-probe":
        capacity_probe(args.gpus[0])
    elif args.phase == "archive-preformal-logs":
        archive_preformal_logs()
    elif args.phase == "io-diagnostics":
        io_diagnostics()
    elif args.phase == "evaluation-lock":
        evaluation_lock()
    elif args.phase == "audit-formal":
        audit_formal(args.gpus[0])
    elif args.phase == "write-table":
        write_table(args.gpus[0])
    elif args.phase == "nfs-event-buffer":
        nfs_event_buffer()
    elif args.phase == "nfs-buffer-smoke":
        nfs_buffer_smoke()
    elif args.phase == "handoff-formal":
        handoff_formal()
    elif args.phase == "gate-overlapping-inference":
        gate_overlapping_inference()
    elif args.phase == "correct-invalid-gpu-retry":
        correct_invalid_gpu_retry()


if __name__ == "__main__":
    main()

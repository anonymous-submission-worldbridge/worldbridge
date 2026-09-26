import sys, subprocess, json, time, concurrent.futures
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect3_plan import SCENES

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"


def build(i):
    key = SCENES[i][0]
    dest = O / key
    with (O / "logs" / ("build_" + key + ".log")).open("w") as log:
        p = subprocess.run(
            [
                "blender",
                "-b",
                "-t",
                "4",
                "--python-exit-code",
                "1",
                "-P",
                str(R / "scripts/build_urban_v1_full_connect3.py"),
                "--",
                str(i),
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=R,
        )
    if p.returncode:
        return {"scene": key, "stage": "build", "exit": p.returncode}
    with (O / "logs" / ("audit_" + key + ".log")).open("w") as log:
        p = subprocess.run(
            [
                "blender",
                "-b",
                "-t",
                "4",
                "--python-exit-code",
                "1",
                "-P",
                str(R / "scripts/audit_connect3_scene.py"),
                "--",
                key,
            ],
            stdout=log,
            stderr=subprocess.STDOUT,
            cwd=R,
        )
    return {"scene": key, "stage": "audit", "exit": p.returncode}


if __name__ == "__main__":
    indices = [int(x) for x in sys.argv[1:]] or list(range(20))
    result = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        for f in concurrent.futures.as_completed(
            [ex.submit(build, i) for i in indices]
        ):
            item = f.result()
            result.append(item)
            print(json.dumps(item), flush=True)
            (O / "build_progress.json").write_text(json.dumps(result, indent=2))

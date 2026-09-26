"""Check the pilot camera bug on real geometry, without changing any scene."""

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

import ast
from collections import deque
import json
import math
from pathlib import Path

import numpy as np
from baselines.methods.gpt.tools.gpt_camera import corner_preserving_resample

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def main():
    source = ROOT / "methods/gpt/tools/blender_render_gpt.py"
    tree = ast.parse(source.read_text())
    function = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "plan_path"
    )
    namespace = {
        "math": math,
        "np": np,
        "deque": deque,
        "corner_preserving_resample": corner_preserving_resample,
    }
    exec(
        compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"),
        namespace,
    )
    output = []
    for domain, spec, seed in [
        ("indoor", "indoor_bathroom_00", 0),
        ("indoor", "indoor_dining_room_00", 1),
        ("urban", "urban_commercial_t_junction_06", 0),
    ]:
        run = ROOT / f"data/gpt6_astra_pilot/{domain}/gpt6_astra/{spec}/seed_{seed}"
        try:
            poses, _, _, metadata = namespace["plan_path"](
                json.loads((run / "input/spec.json").read_text()),
                json.loads((run / "scene/geometry.json").read_text()),
            )
            record = {
                "spec_id": spec,
                "seed": seed,
                "original_error": None,
                "fixed_path_length_m": metadata["path_length_m"],
                "frames": len(poses),
                "clearance_pass": True,
            }
        except ValueError as error:
            if "Resampled path cuts" not in str(error):
                raise
            tb = error.__traceback__
            while tb.tb_next:
                tb = tb.tb_next
            state = tb.tb_frame.f_locals
            poses = corner_preserving_resample(state["raw"])
            free = state["free"]
            valid = all(
                free((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
                for a, b in zip(poses, poses[1:])
                for t in np.linspace(0, 1, max(3, math.ceil(math.dist(a, b) / 0.025)))
            )
            record = {
                "spec_id": spec,
                "seed": seed,
                "original_error": str(error),
                "frames": len(poses),
                "fixed_path_length_m": sum(
                    math.dist(a, b) for a, b in zip(poses, poses[1:])
                ),
                "clearance_pass": valid,
            }
        output.append(record)
    report = {
        "formal": False,
        "purpose": "camera infrastructure regression; no scene modification",
        "records": output,
        "passed": all(r["clearance_pass"] and r["frames"] == 50 for r in output),
    }
    (ROOT / "results/gpt6_astra/smoke/corner_regression.json").write_text(
        json.dumps(report, indent=2) + "\n"
    )
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

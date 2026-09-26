"""Check native lake-impact frames: stationary bank and moving water."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from run_urban_v1_full_13_dynamic3 import OUT, atomic, sha256

folder = OUT / "frames_final/lake_impact"
regions = {
    "static_path": (700, 180, 880, 260),
    "static_ground": (1500, 260, 1800, 350),
    "impact_water": (950, 720, 1500, 950),
}
reference = np.asarray(
    Image.open(folder / "frame_0001.png").convert("RGB"), dtype=float
)
result = {
    "status": "PASS",
    "regions_xyxy": regions,
    "comparisons": [],
    "render_contract_sha256": sha256(folder / "render_contract.json"),
}
for frame in (48, 96, 144):
    current = np.asarray(
        Image.open(folder / f"frame_{frame:04d}.png").convert("RGB"), dtype=float
    )
    for name, (x0, y0, x1, y1) in regions.items():
        difference = np.abs(reference[y0:y1, x0:x1] - current[y0:y1, x0:x1])
        mean = float(difference.mean())
        changed = float((difference.max(axis=2) > 3).mean())
        passed = (
            (mean < 0.1 and changed < 0.001)
            if name.startswith("static_")
            else changed > 0.01
        )
        result["comparisons"].append(
            {
                "frame": frame,
                "region": name,
                "mean_absolute_delta_255": mean,
                "fraction_delta_gt3": changed,
                "passed": passed,
            }
        )
        if not passed:
            result["status"] = "FAIL"
atomic(folder / "localized_motion_audit.json", result)
print(json.dumps(result, indent=2))
if result["status"] != "PASS":
    raise SystemExit(1)

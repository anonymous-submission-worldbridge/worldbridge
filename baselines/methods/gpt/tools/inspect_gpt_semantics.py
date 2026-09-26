"""Diagnostic visualization of existing RGB/semantic data; never metric input."""

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

import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw

ROOT = _BASELINE_PROJECT_ROOT / "baselines"


def main():
    records = []
    for domain, spec in [
        ("indoor", "indoor_bedroom_00"),
        ("urban", "urban_residential_four_way_00"),
    ]:
        run = ROOT / f"data/gpt6_astra_pilot/{domain}/gpt6_astra/{spec}/seed_0"
        names = json.loads(
            (
                ROOT
                / f"results/gpt6_astra/smoke/{domain}/{spec}_seed_0/semantic_model.json"
            ).read_text()
        )["id2label"]
        canvas = Image.new("RGB", (1200, 4 * 240), (255, 255, 255))
        draw = ImageDraw.Draw(canvas)
        for j, i in enumerate([0, 2, 4, 6]):
            rgb = Image.open(run / f"renders/anchors/rgb_{i:03d}.png").convert("RGB")
            labels = np.asarray(
                Image.open(run / f"renders/semantic_pred/semantic_{i:03d}.png")
            )
            ids, counts = np.unique(labels, return_counts=True)
            top = sorted(zip(ids.tolist(), counts.tolist()), key=lambda x: -x[1])[:8]
            colors = {
                int(k): (
                    (int(k) * 71 + 83) % 256,
                    (int(k) * 137 + 39) % 256,
                    (int(k) * 47 + 191) % 256,
                )
                for k in ids
            }
            colored = np.zeros((*labels.shape, 3), dtype=np.uint8)
            for k, c in colors.items():
                colored[labels == k] = c
            rgb.thumbnail((420, 236))
            sem = Image.fromarray(colored).resize((420, 236), Image.Resampling.NEAREST)
            canvas.paste(rgb, (0, j * 240))
            canvas.paste(sem, (420, j * 240))
            summary = []
            for n, (k, count) in enumerate(top):
                name = names[str(k)].strip()
                percentage = count / labels.size * 100
                y = j * 240 + n * 27
                draw.rectangle((848, y + 2, 865, y + 18), fill=colors[k])
                draw.text(
                    (875, y + 2), f"{k} {name}: {percentage:.1f}%", fill=(0, 0, 0)
                )
                summary.append({"class_id": k, "label": name, "percent": percentage})
            records.append(
                {"domain": domain, "spec_id": spec, "view": i, "top_classes": summary}
            )
        canvas.save(
            ROOT / f"results/gpt6_astra/smoke/{domain}/semantic_visual_check.png"
        )
    (ROOT / "results/gpt6_astra/smoke/semantic_visual_check.json").write_text(
        json.dumps({"formal": False, "records": records}, indent=2) + "\n"
    )


if __name__ == "__main__":
    main()

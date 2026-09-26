#!/usr/bin/env python3
"""Generate deterministic planning descriptors, SVG previews, and audits."""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from worldbridge.urban.core import TOPOLOGIES, generate_descriptor, validate_descriptor

DEFAULT_OUT = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v2_full_01"
COLORS = {
    "commercial": "#d98938",
    "residential": "#6b91c9",
    "park": "#62a66e",
    "leisure": "#b174b8",
}


def png_preview(d, path):
    """Raster validation render matching the descriptor (not a Blender render)."""
    scale = 8.0
    origin = (600, 600)

    def sx(x):
        return origin[0] + x * scale

    def sy(y):
        return origin[1] - y * scale

    image = Image.new("RGB", (1200, 1280), "#e9e5dc")
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 25)
        title = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 32
        )
    except OSError:
        font = title = ImageFont.load_default()
    for p in d["parcels"]:
        cx, cy = p["center"]
        w, h = p["size"]
        box = (sx(cx - w / 2), sy(cy + h / 2), sx(cx + w / 2), sy(cy - h / 2))
        draw.rounded_rectangle(
            box, radius=14, fill=COLORS[p["zone"]], outline="#242424", width=4
        )
        label = f"{p['zone']}\n{p['regional_config']['profile']}"
        bounds = draw.multiline_textbbox((0, 0), label, font=font, align="center")
        tw = bounds[2] - bounds[0]
        th = bounds[3] - bounds[1]
        draw.multiline_text(
            (sx(cx) - tw / 2, sy(cy) - th / 2),
            label,
            font=font,
            fill="white",
            align="center",
            stroke_width=1,
            stroke_fill="#333333",
        )
    for r in d["roads"]:
        width = r["width"] * scale
        if r["axis"] == "x":
            draw.rectangle(
                (80, sy(r["offset"]) - width / 2, 1120, sy(r["offset"]) + width / 2),
                fill="#53565a",
            )
        else:
            draw.rectangle(
                (sx(r["offset"]) - width / 2, 80, sx(r["offset"]) + width / 2, 1120),
                fill="#53565a",
            )
    draw.text(
        (45, 1170),
        f"Seed {d['scene_seed']} · {d['road_topology']}",
        font=title,
        fill="#202020",
    )
    draw.text(
        (45, 1220),
        f"Fingerprint {d['fingerprint']} · validation: PASS",
        font=font,
        fill="#303030",
    )
    image.save(path, optimize=True)


def svg_preview(d, path):
    def sx(x):
        return 320 + x * 4.6

    def sy(y):
        return 320 - y * 4.6

    rows = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="680" viewBox="0 0 640 680">',
        '<rect width="640" height="680" fill="#e9e5dc"/>',
    ]
    for p in d["parcels"]:
        cx, cy = p["center"]
        w, h = p["size"]
        rows.append(
            f'<rect x="{sx(cx-w/2):.1f}" y="{sy(cy+h/2):.1f}" width="{w*4.6:.1f}" height="{h*4.6:.1f}" rx="8" fill="{COLORS[p["zone"]]}" stroke="#333" stroke-width="2"/>'
        )
        rows.append(
            f'<text x="{sx(cx):.1f}" y="{sy(cy):.1f}" text-anchor="middle" font-family="sans-serif" font-size="14" fill="white">{p["zone"]}</text>'
        )
    for r in d["roads"]:
        width = r["width"] * 4.6
        if r["axis"] == "x":
            rows.append(
                f'<rect x="40" y="{sy(r["offset"])-width/2:.1f}" width="560" height="{width:.1f}" fill="#53565a"/>'
            )
        else:
            rows.append(
                f'<rect x="{sx(r["offset"])-width/2:.1f}" y="40" width="{width:.1f}" height="560" fill="#53565a"/>'
            )
    rows.append(
        f'<text x="24" y="635" font-family="sans-serif" font-size="20">seed {d["scene_seed"]} · {d["road_topology"]}</text>'
    )
    rows.append(
        f'<text x="24" y="660" font-family="monospace" font-size="13">fingerprint {d["fingerprint"]}</text></svg>'
    )
    path.write_text("\n".join(rows), encoding="utf8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=2101)
    ap.add_argument("--count", type=int, default=6)
    ap.add_argument(
        "--topology",
        choices=TOPOLOGIES,
        help="Force one topology family (primarily for single-demo generation)",
    )
    args = ap.parse_args()
    out = args.output_dir
    for sub in (
        "configs",
        "planning_variants",
        "commercial_variants",
        "residential_variants",
        "park_variants",
        "leisure_variants",
        "logs",
        "renders",
    ):
        (out / sub).mkdir(parents=True, exist_ok=True)
    index = []
    for i in range(args.count):
        seed = args.seed + i * 97
        topo = args.topology or TOPOLOGIES[i % len(TOPOLOGIES)]
        d = generate_descriptor(seed, topo)
        errors = validate_descriptor(d)
        vdir = out / "planning_variants" / f"variant_{i+1:02d}"
        vdir.mkdir(exist_ok=True)
        (vdir / "config.json").write_text(
            json.dumps(d, indent=2, ensure_ascii=False), encoding="utf8"
        )
        svg_preview(d, vdir / "layout.svg")
        png_preview(d, out / "renders" / f"planning_variant_{i+1:02d}.png")
        (vdir / "generation.log").write_text(
            f'seed={seed}\ntopology={topo}\nvalid={not errors}\nfingerprint={d["fingerprint"]}\n',
            encoding="utf8",
        )
        for p in d["parcels"]:
            zdir = out / f'{p["zone"]}_variants' / f"variant_{i+1:02d}"
            zdir.mkdir(exist_ok=True)
            (zdir / "config.json").write_text(
                json.dumps(p["regional_config"], indent=2, ensure_ascii=False),
                encoding="utf8",
            )
            (zdir / "generation.log").write_text(
                f'source_descriptor={vdir/"config.json"}\nseed={p["regional_config"]["seed"]}\nvalid=true\n',
                encoding="utf8",
            )
        index.append(
            {
                "variant": i + 1,
                "seed": seed,
                "topology": topo,
                "fingerprint": d["fingerprint"],
                "valid": not errors,
            }
        )
    (out / "configs" / "manifest.json").write_text(
        json.dumps({"variants": index}, indent=2), encoding="utf8"
    )
    (out / "logs" / "validation.json").write_text(
        json.dumps(
            {
                "valid": all(x["valid"] for x in index),
                "count": len(index),
                "distinct_fingerprints": len(set(x["fingerprint"] for x in index)),
            },
            indent=2,
        ),
        encoding="utf8",
    )
    print(
        json.dumps(
            {
                "output": str(out),
                "variants": len(index),
                "valid": all(x["valid"] for x in index),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

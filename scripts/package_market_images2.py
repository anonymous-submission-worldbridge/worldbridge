"""Make contact sheets and a local browser for completed market photographs."""
import argparse
import html
import json
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
DEST = (
    ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/market/images2"
)
p = argparse.ArgumentParser()
p.add_argument("--preview", action="store_true")
args = p.parse_args()
source = DEST / ".previews" if args.preview else DEST
groups = [
    ("inside", "Indoor to outdoor", 1, 12),
    ("outside", "Outdoor to Indoor", 13, 22),
    ("overall", "overall landscape", 23, 30),
]
sections = []
count = 0
for key, title, start, end in groups:
    files = [
        f
        for f in sorted(source.glob("*.png"))
        if f.name[:2].isdigit() and start <= int(f.name[:2]) <= end
    ]
    if not files:
        continue
    sheet = Image.new("RGB", (1440, ((len(files) + 2) // 3) * 294), "#20252b")
    draw = ImageDraw.Draw(sheet)
    cards = []
    for i, f in enumerate(files):
        with Image.open(f) as im:
            im.load()
            if not args.preview:
                assert im.size == (1920, 1080), (f, im.size)
            thumb = im.convert("RGB")
            thumb.thumbnail((480, 270))
        x = i % 3 * 480
        y = i // 3 * 294
        sheet.paste(thumb, (x, y))
        draw.text((x + 8, y + 275), f.stem, fill="white")
        cards.append(
            f'<a href="{f.name}" target="_blank"><img loading="lazy" src="{f.name}"><span>{html.escape(f.stem)}</span></a>'
        )
    sheet.save(source / f"contact_{key}.jpg", quality=92)
    sections.append(
        f'<section><h2>{title} · {len(files)} Zhang</h2><div class="grid">'
        + "".join(cards)
        + "</div></section>"
    )
    count += len(files)
if not args.preview:
    page = """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>Market · New Perspective</title><style>body{background:#151b22;color:#edf2f5;font:16px system-ui;margin:32px}h1{font-size:28px}h2{margin-top:38px;font-size:22px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:18px}a{color:inherit;text-decoration:none;background:#242e39;border-radius:8px;overflow:hidden}img{width:100%;display:block}span{display:block;padding:12px;font-size:14px}p{color:#b5c5d4}</style><h1>Market · New Rendering Perspective</h1>"""
    page += f"<p>{count} images · 1920 × 1080 · Cycles / OptiX · Click an image to open the original</p>" + "".join(
        sections
    )
    (DEST / "index.html").write_text(page)
    (DEST / "README.txt").write_text(
        f"{count} high-resolution renders, 1920 × 1080, Cycles / OptiX, 128 samples. \n01–12: from indoor to outdoor, shelves, fruits and vegetables, entrance, and outdoor scenery. \n13–22: from outdoor to indoor, full store, entrance, and left and right display windows. \n23–30: overall scenery, tightened composition, reduced empty background. \nindex.html: local image browsing page; contact_*.jpg: categorized overview. \nrender_manifest.json: positions, orientations, focal lengths, and rendering records of each camera. \noriginal scene.blend, geometry, lighting, materials, and original images are all preserved. \n"
    )
print("Validated photographs:", count)

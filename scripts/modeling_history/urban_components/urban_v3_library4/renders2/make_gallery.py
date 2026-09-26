"""Validate finished renders and build a local selection gallery/contact sheet."""
import html
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageStat

out = Path(__file__).resolve().parent
manifest = json.loads((out / 'manifest_all.json').read_text())
font_path = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
font = ImageFont.truetype(font_path, 24)
small = ImageFont.truetype(font_path, 18)
sheet = Image.new('RGB', (1640, 1530), '#17202a')
draw = ImageDraw.Draw(sheet)
draw.text((25, 16), 'LIBRARY 4 | MULTI-VIEW SELECTION', font=font, fill='white')
cards = []
checks = []
for i, view in enumerate(manifest['views']):
    path = out / view['file']
    with Image.open(path) as im:
        im.load()
        assert list(im.size) == view['resolution'], (path, im.size)
        stat = ImageStat.Stat(im.resize((128, 128)))
        assert max(stat.var) > 100, (path, stat.var)
        checks.append(dict(file=path.name, resolution=list(im.size), bytes=path.stat().st_size, verified=True))
        thumb = im.copy()
        thumb.thumbnail((790, 310))
    x = 20 + (i % 2) * 815
    y = 60 + (i // 2) * 365
    sheet.paste(thumb, (x+(790-thumb.width)//2, y+(310-thumb.height)//2))
    draw.text((x+8, y+315), path.stem.replace('_', ' ').upper(), font=small, fill='white')
    cards.append(f'<a href="{path.name}"><img src="{path.name}" loading="lazy"><span>{html.escape(view["title"])} · {im.width} × {im.height}</span></a>')
sheet.save(out / '00_contact_sheet.jpg', quality=94)
(out / 'index.html').write_text('''<!doctype html><html lang="en"><meta charset="utf-8"><title>Library view gallery</title>
<style>body{margin:32px;background:#17202a;color:#eaf0f5;font:16px system-ui}h1{font-size:26px}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:24px}a{color:inherit;text-decoration:none;background:#243241;padding:14px;border-radius:8px}img{width:100%;height:310px;object-fit:contain}span{display:block;padding-top:12px}@media(max-width:800px){.grid{grid-template-columns:1fr}}</style>
<h1>Library: eight presentation views</h1><p>Click an image for the full-resolution PNG. Recommended: 02 for both libraries, 04 for the white library, and 06 for the red library.</p><div class="grid">'''+''.join(cards)+'</div></html>')
(out / 'validation.json').write_text(json.dumps(checks, ensure_ascii=False, indent=2))
(out / 'README.md').write_text('''# Library multiview rendering

Eight original PNG images with a long edge of 2600-3200 pixels. Open `index.html` for the gallery or `00_contact_sheet.jpg` for an overview.

Recommended: 02 (both libraries from the southwest), 04 (white library exterior), and 06 (red library exterior). Views 01/05/07 show front facades; 03/08 show opposite directions.

Low cameras, vertical shift correction, and compact framing reduce empty foreground and background. Wide panoramas retain the complete roofs and entrances of both libraries. The original surrounding vegetation remains; no surrounding buildings, generated images, or replacement backgrounds were added.

Uses urban_v3_library4.blend without overwriting it, preserving geometry, materials, and lighting. Cycles / OptiX, 160 samples, adaptive sampling and denoising, AgX, exposure -1.15. Camera settings and resolutions are in manifest_all.json; timings are in each image JSON.

Reproduce with `blender -b -t 8 --python render_views.py -- --gpu 7 --samples 160`. Adjust the GPU index for the host. `_preview` contains initial low-resolution framing trials; the final images are PNG files 01-08.
''')
print(json.dumps(checks, ensure_ascii=False, indent=2))

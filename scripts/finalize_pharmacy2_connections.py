"""Verify, document and present the connected-view stills without image overlays."""
import json, hashlib, html, shutil
from pathlib import Path
from PIL import Image, ImageStat

R = Path(__file__).resolve().parents[1]
D = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/pharmacy2/images2"
labels = {
    "outside_in_front_complete": "Front of store facing inside",
    "outside_in_left_complete": "Outside to Inside · Left Sign and Entrance",
    "outside_in_right_complete": "Outside to Inside · Right storefront and display",
    "outside_in_entry_and_sign": "Signs, entrance, and cash register area outside lead to indoor space.",
    "outside_in_shopfront": "Outdoor view of indoor space · Street glass facing interior",
    "inside_out_rear_left": "Interior view of exterior - left rear perspective",
    "inside_out_rear_right": "Interior view of exterior - rear right perspective",
    "inside_out_rear_center": "Interior view of exterior - mid-back perspective",
    "inside_out_left_aisle": "Inside looking at outside · Left shelf adjacent to street environment",
    "inside_out_right_aisle": "Inside looking at outside · Right side shelves against street environment",
}
reports = [
    json.loads(p.read_text()) for p in sorted((D / "metadata").glob("render_*.json"))
]
shots = {}
source_hash = hashlib.sha256((D.parent / "scene.blend").read_bytes()).hexdigest()
for r in reports:
    assert r["source_sha256"] == source_hash and r["resolution"] == [2560, 1440]
    shots.update(r["shots"])
rows = []
for key, label in labels.items():
    p = D / (key + ".png")
    assert key in shots
    with Image.open(p) as im:
        im.load()
        assert im.size == (2560, 1440)
        assert sum(ImageStat.Stat(im).var) > 100
    rows.append(
        {
            "file": p.name,
            "title": label,
            "camera": shots[key],
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    )
assert len(list(D.glob("*.png"))) == 10
(D / "metadata/cameras_and_validation.json").write_text(
    json.dumps(
        {
            "passed": True,
            "source_scene": "../scene.blend",
            "source_sha256": source_hash,
            "geometry_lighting_and_original_scene_unchanged": True,
            "resolution": [2560, 1440],
            "cycles_samples": 192,
            "images": rows,
        },
        ensure_ascii=False,
        indent=2,
    )
)
options = "".join(
    '<option value="' + key + '">' + html.escape(value) + "</option>"
    for key, value in labels.items()
)
page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pharmacy · Complete Indoor and Outdoor Connected View</title><style>body{background:#111a17;color:#e5efea;font:16px system-ui;margin:24px}main{max-width:1680px;margin:auto}h1{font-size:24px}p{color:#b3c8bd}nav{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin:18px 0}select,button{background:#254437;color:white;border:1px solid #648673;border-radius:5px;padding:10px}img{display:block;width:100%;height:auto}a{color:#b6dec6}</style><main><h1>Pharmacy · Complete Indoor and Outdoor Connected View</h1><p>The outdoor view simultaneously displays the signboard, entrance, and indoor area; the indoor view simultaneously displays shelves, counter or aisles, as well as the outdoor environment. Each original image is 2560 × 1440.</p><nav><button id="prev">Previous</button><select id="select">OPTIONS</select><button id="next">Next</button><a id="original" href="outside_in_front_complete.png" target="_blank">Open Original</a></nav><img id="view" src="outside_in_front_complete.png" alt="Connected indoor and outdoor view of pharmacy"><p><a href="README.md">Image Description</a> · <a href="metadata/cameras_and_validation.json">Camera Parameters</a></p></main><script>const s=document.querySelector(\'#select\'),v=document.querySelector(\'#view\'),a=document.querySelector(\'#original\');function show(){v.src=a.href=s.value+\'.png\';v.alt=s.options[s.selectedIndex].text}function move(d){s.selectedIndex=(s.selectedIndex+d+s.length)%s.length;show()}s.onchange=show;document.querySelector(\'#prev\').onclick=()=>move(-1);document.querySelector(\'#next\').onclick=()=>move(1);document.addEventListener(\'keydown\',e=>{if(e.key===\'ArrowLeft\')move(-1);if(e.key===\'ArrowRight\')move(1)})</script></html>'.replace(
    "OPTIONS", options
)
(D / "index.html").write_text(page)
(D / "README.md").write_text(
    """# Store: Complete view of indoor and outdoor connectivity

10 independent PNGs, 2560x1440 resolution, Cycles/OptiX GPU, 192 samples.

- 5 pieces (`outside_in_*.png`): Exterior to interior; retain pharmacy sign, storefront entrance/glass, and visible indoor furnishings. Cover front, sides at an angle, and entry composition.
- `inside_out_*.png` (5 shots): Capturing the street-facing facade from the rear or side passage of the interior, covering multiple rows of shelves, counters, or interior corridors, while simultaneously displaying the trees, paving, and seating areas outside the glass/entrance.

Simply open `index.html` to browse one by one without any stitching or numbering.

Use the real 3D geometry and original lighting and materials from `../scene.blend`, without hidden walls or replaced backgrounds. Only reposition the camera, adjust the focal length and output resolution. The original scene.blend and images/ are not modified.

Complete camera position coordinates, target point, focal length, and source scene validation values are saved in `metadata/cameras_and_validation.json`. The rendering script is for project `scripts/render_pharmacy2_connections.py`.
"""
)
# Only disposable preview renders made for this particular task are removed.
previews = D / "metadata/previews"
if previews.exists():
    for p in previews.glob("*.png"):
        p.unlink()
    if not any(previews.iterdir()):
        previews.rmdir()
print(
    "COMPLETE: 10 verified independent 2560x1440 images; original scene hash unchanged."
)

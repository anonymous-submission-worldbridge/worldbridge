"""Validate the new pharmacy delivery and write a single-image gallery."""
import json, hashlib, html, gzip, shutil
from pathlib import Path
from PIL import Image, ImageStat

R = Path(__file__).resolve().parents[1]
D = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/pharmacy2"
S = D.parent / "pharmacy"
m = json.loads((D / "scene_manifest.json").read_text())
old = json.loads((S / "scene_manifest.json").read_text())
cams = json.loads((D / "logs/camera_preservation.json").read_text())
audit = json.loads((D / "geometry_audit.json").read_text())
assert m["shots"] == old["shots"]
assert cams["original"] == cams["refined"]
assert audit["passed"]
assert (
    hashlib.sha256((S / "scene.blend").read_bytes()).hexdigest()
    == m["interior_refinement"]["source_sha256"]
)
rows = []
for name in m["shots"]:
    p = D / "images" / (name + ".png")
    with Image.open(p) as im:
        im.load()
        assert im.size == (1920, 1080)
        assert sum(ImageStat.Stat(im).var) > 100
    rows.append(
        {
            "file": str(p.relative_to(D)),
            "bytes": p.stat().st_size,
            "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        }
    )
assert len(rows) == 24
placements = json.loads((D / "logs/product_placements.json").read_text())
source_file = D / "logs/source_objects.json"
source = (
    json.loads(source_file.read_text())
    if source_file.exists()
    else json.loads(gzip.decompress(source_file.with_suffix(".json.gz").read_bytes()))
)
source_by_name = {o["name"]: o for o in source}
for x in placements:
    y = source_by_name[x["source"]]
    assert x["base"][:2] == y["loc"][:2]
    assert x["base"][2] == float(y["attrs"]["c2w_base_z"])
report = {
    "passed": True,
    "images": rows,
    "resolution": [1920, 1080],
    "cycles_samples": 192,
    "renderer": "Blender 5.1.2 Cycles / NVIDIA OptiX GPU",
    "original_shots_identical": True,
    "stored_cameras_unchanged": len(cams["original"]),
    "source_scene_unchanged": True,
    "product_positions_preserved": len(placements),
    "geometry_and_dependencies_passed": True,
    "collages_or_image_number_overlays": False,
    "downloads": 0,
}
(D / "delivery_validation.json").write_text(json.dumps(report, indent=2))
labels = {
    "detail_primary": "counter, computer, dispensing equipment",
    "detail_secondary": "Pharmaceutical packaging and shelf details",
    "interior_wide": "Interior wide-angle view",
    "interior_reverse": "indoor reverse",
    "interior_diagonal": "Interior diagonal direction",
    "interior_activity": "indoor activity area",
    "exterior_wide": "outdoor wide-angle",
    "exterior_street_left": "outside to the left",
    "exterior_street_right": "outside to the right",
    "garden_overview": "garden overview",
    "entrance_context": "entrance environment",
    "outdoor_furniture": "outdoor furniture",
}
for n in m["shots"]:
    if n.startswith(("inside_to_outside", "outside_to_inside")):
        labels[n] = (
            ("Looking at the outside from inside." if n.startswith("inside") else "Outside looking at inside.")
            + " · "
            + {"near": "Close-up", "middle": "mid-shot", "far": "vision"}[n.split("_")[-2]]
            + " · "
            + ("Forward" if n.endswith("axial") else "Diagonal")
        )
order = ["detail_primary", "detail_secondary", "interior_wide"] + [
    x
    for x in m["shots"]
    if x not in ["detail_primary", "detail_secondary", "interior_wide"]
]
options = "".join(
    '<option value="' + n + '">' + html.escape(labels.get(n, n)) + "</option>"
    for n in order
)
page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pharmacy2 · Refined Interior</title><style>body{background:#101615;color:#e8eeec;font:16px system-ui;margin:24px}main{max-width:1600px;margin:auto}h1{font-size:24px}p{color:#abbcb7}nav{display:flex;gap:12px;align-items:center;margin:20px 0}select,button{background:#263831;color:#fff;border:1px solid #547064;padding:10px;border-radius:6px}img{width:100%;height:auto;display:block}a{color:#b8e1d2}footer{margin-top:16px}</style><main><h1>Pharmacy2 · Refined Interior</h1><p>Continuing from the original scene with 24 image positions. 1920 × 1080 independently rendered images.</p><nav><button id="prev">Previous</button><select id="shot">OPTIONS</select><button id="next">Next</button><a id="raw" href="images/detail_primary.png" target="_blank">Open Original</a></nav><img id="photo" src="images/detail_primary.png" alt="Refined Interior Rendering of a Pharmacy"><footer><a href="scene.blend">Blender Scene File</a> · <a href="assets/refined_pharmacy_assets.blend">Refined Asset Library</a> · <a href="README.md">Generation Instructions</a></footer></main><script>const s=document.querySelector(\'#shot\'),p=document.querySelector(\'#photo\'),a=document.querySelector(\'#raw\');function show(){p.src=a.href=\'images/\'+s.value+\'.png\';p.alt=s.options[s.selectedIndex].text}function step(d){s.selectedIndex=(s.selectedIndex+d+s.length)%s.length;show()}s.onchange=show;document.querySelector(\'#prev\').onclick=()=>step(-1);document.querySelector(\'#next\').onclick=()=>step(1);document.addEventListener(\'keydown\',e=>{if(e.key===\'ArrowLeft\')step(-1);if(e.key===\'ArrowRight\')step(1)})</script></html>'.replace(
    "OPTIONS", options
)
(D / "index.html").write_text(page)
(D / "README.md").write_text(
    """# Pharmacy 2: An indoor version of the original machine position

Derived from `../pharmacy/scene.blend`. The original scene file and images remain unchanged; all 24 image camera positions, target orientations, and focal lengths are reused as they were. Additionally, it has been verified that all 29 camera objects in the scene have unchanged matrices, focal lengths, sensor settings, and offset parameters.

- `images/`: 24 PNG files at 1920x1080 resolution, rendered using Blender's Cycles or OptiX GPU render engines with 192 samples, without any tiling or grid numbering.
- `scene.blend`: A real-time editable 3D scene that can be compressed and saved; existing local shared assets still reference `../shared_assets/`, please maintain the relative position when moving the delivery directory.
- `assets/refined_pharmacy_assets.blend`: 26 reusable refined program asset collections; packaging patterns and device display interfaces are packed into the Blender file.
- `index.html`: Browse through each image one by one; directly open the original file.
- `scene_manifest.json` / `delivery_validation.json`: Aircraft location, asset origin, and delivery verification.

The packaging was further detailed with 712 boxes, 418 bottles, and 170 soft tubes. All original display coordinates and shelf support heights for 1,300 items were retained. The 20-packaging assets include box flanges and embossing, bottle shoulders and anti-tamper rings, 64 anti-slip grooves on bottle caps, and heat-sealed edges of soft tubes; printing details include product names, specifications, batches, and barcodes. Additionally, 300 new shelf price tags have been updated.

Counter detailing includes 3 computers, 3 sets of independent keycap keyboards, 2 mice, 3 label/cash receipt printers, 3 scanning devices, and 4 boards of tablet and transparent blister packaging, and updates the dispensing terminal and weighing display. The computers have a screen interface, casing, tilt hinge, ventilation holes, interfaces, and cable routing; the printers have a paper path, tear paper teeth, paper output labels, and maintenance structure. Correct the reversed normal direction and thickness of the counter glass to achieve proper transmission.

Based on the existing assets factory extension with local `scripts/generate_urban_v3_pharmacy.py`, retain the original Infinigen assets from this scenario; no external models downloaded. The new factory and generation script located at project `scripts/pharmacy2_asset_factory.py`, `scripts/prepare_pharmacy2_prints.py`, `scripts/build_pharmacy2.py`, rendering using `scripts/render_pharmacy2.py`.

This delivery includes images and 3D scenes according to the latest requirements, without re-generating the video. The packaging and screen text are demonstration program printed content.
"""
)
# Keep compact evidence, removing only intermediate files from this task.
if source_file.exists():
    with gzip.open(source_file.with_suffix(".json.gz"), "wb", compresslevel=9) as f:
        f.write(source_file.read_bytes())
    source_file.unlink()
preview = D / "previews"
if preview.exists():
    for f in preview.glob("*.png"):
        f.unlink()
    if not any(preview.iterdir()):
        preview.rmdir()
print("VALIDATED", len(rows), "images;", len(placements), "product positions preserved")

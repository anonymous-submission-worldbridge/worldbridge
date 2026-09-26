"""Verify media/geometry and publish a local, single-image-at-a-time gallery."""
import json, subprocess, hashlib, html, sys
from pathlib import Path
from PIL import Image

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
names = ["restaurant", "cafe", "market", "hospital", "pharmacy", "library"]
report = {"scenes": [], "errors": []}
gallery = []
for key in names:
    d = O / key
    m = json.loads((d / "scene_manifest.json").read_text())
    a = json.loads((d / "geometry_audit.json").read_text())
    images = []
    videos = []
    if not a["passed"]:
        report["errors"].append(key + ": geometry audit failed")
    if not (d / "scene.blend").exists():
        report["errors"].append(key + ": missing .blend")
    if m.get("embedded_cameras") != {
        "stills": 24,
        "animated": 4,
        "animation_frames": 144,
        "fps": 24,
    }:
        report["errors"].append(key + ": embedded cameras metadata missing")
    if not m.get("tree_ground_contact", {}).get("passed"):
        report["errors"].append(key + ": tree root support check missing")
    revision = (d / "scene.blend").stat().st_mtime
    for shot in m["shots"]:
        p = d / "images" / (shot + ".png")
        if not p.exists():
            report["errors"].append(str(p) + ": missing")
            continue
        if p.stat().st_mtime < revision:
            report["errors"].append(str(p) + ": predates final geometry revision")
        with Image.open(p) as im:
            im.load()
            size = im.size
            if size != (1920, 1080):
                report["errors"].append(str(p) + ": unexpected resolution")
            # Blank/black-image detection supplements, not replaces, visual review.
            small = im.convert("L").resize((64, 36))
            v = list(small.getdata())
            mean = sum(v) / len(v)
            if mean < 8 or max(v) - min(v) < 15:
                report["errors"].append(str(p) + ": nearly blank")
        images.append(
            {
                "name": shot,
                "file": str(p.relative_to(O)),
                "width": size[0],
                "height": size[1],
                "mean_luminance": round(mean, 2),
                "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
            }
        )
    for clip in ["interior", "exterior", "inside_to_outside", "outside_to_inside"]:
        p = d / "videos" / (clip + ".mp4")
        if not p.exists():
            report["errors"].append(str(p) + ": missing")
            continue
        if (
            clip != "interior" or key in ["restaurant", "cafe"]
        ) and p.stat().st_mtime < revision:
            report["errors"].append(str(p) + ": predates final geometry revision")
        if clip != "interior" or key in ["restaurant", "cafe"]:
            worker = "grounded_video_" + key
            if key in ["restaurant", "cafe"] and clip in [
                "inside_to_outside",
                "outside_to_inside",
            ]:
                worker = "grounded_portals_" + key
            if key in ["market", "hospital"] and clip == "outside_to_inside":
                worker = "grounded_entry_" + key
            logs = [
                O / "logs" / (worker + ".log"),
                O / "logs" / (worker + "_assist.log"),
                O / "logs" / ("video_" + key + ".log"),
            ]
            if not any(
                log.exists()
                and log.stat().st_mtime >= revision
                and "CONNECT_VIDEO " + str(p) in log.read_text()
                for log in logs
            ):
                report["errors"].append(
                    str(p) + ": final revision render not completed"
                )
        meta = json.loads(
            subprocess.check_output(
                [
                    "/usr/bin/ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-count_frames",
                    "-show_entries",
                    "stream=width,height,nb_read_frames,r_frame_rate,duration",
                    "-of",
                    "json",
                    str(p),
                ]
            )
        )["streams"][0]
        valid = (
            meta["width"] == 1280
            and meta["height"] == 720
            and int(meta["nb_read_frames"]) == 144
            and meta["r_frame_rate"] == "24/1"
        )
        if not valid:
            report["errors"].append(str(p) + ": incorrect video metadata")
        proc = subprocess.run(
            ["/usr/bin/ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"],
            capture_output=True,
        )
        if proc.returncode or proc.stderr:
            report["errors"].append(
                str(p) + ": decode error " + proc.stderr.decode()[:200]
            )
        videos.append({"name": clip, "file": str(p.relative_to(O)), **meta})
    entry = {
        "scene": key,
        "title": m["title"],
        "layout": m["layout"],
        "images": images,
        "videos": videos,
        "geometry_audit_passed": a["passed"],
        "blend": str((d / "scene.blend").relative_to(O)),
    }
    entry["blend_sha256"] = hashlib.sha256((d / "scene.blend").read_bytes()).hexdigest()
    report["scenes"].append(entry)
    gallery.append(entry)
report["shared_assets"] = [
    {
        "file": str(p.relative_to(O)),
        "bytes": p.stat().st_size,
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
    }
    for p in sorted((O / "shared_assets").glob("*.blend"))
]
report["image_count"] = sum(len(s["images"]) for s in report["scenes"])
report["video_count"] = sum(len(s["videos"]) for s in report["scenes"])
report["passed"] = not report["errors"]
report["files_bytes"] = sum(p.stat().st_size for p in O.rglob("*") if p.is_file())
(O / "delivery_verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)
data = json.dumps(gallery, ensure_ascii=False).replace("</", "<\\/")
page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Joint Indoor and Outdoor Generation · Six Realistic 3D Scenes</title>\n<style>body{margin:0;background:#101614;color:#e8eee9;font:16px system-ui,sans-serif}main{max-width:1320px;margin:auto;padding:30px}h1{font-size:28px;font-weight:550}p{color:#bbc7bf;line-height:1.7}button,select,a.link{background:#263c32;color:#f5fff8;border:1px solid #42624e;border-radius:5px;padding:10px;margin:4px;cursor:pointer}nav{display:flex;flex-wrap:wrap;margin:20px 0}figure{margin:20px 0}img{display:block;width:100%;height:auto;background:#080c0a}figcaption{padding:15px 0;color:#b9cbbf}video{width:100%;max-height:74vh;background:#080c0a}a{color:#a3d9b6}.toolbar{display:flex;align-items:center;flex-wrap:wrap}.download{margin-left:auto}section{margin:30px 0}</style>\n<main>   <h1>Joint Indoor-Outdoor Generation</h1>   <p>Six editable three-dimensional scenes. Independent images showcase indoor/outdoor views along with near, medium, and far distance perspectives from two directions. Video shows real camera movement within the same complete scene.</p>   <nav id="scenes"></nav>   <h2 id="title"></h2>   <div class="toolbar">     <button id="prev">Previous</button>     <select id="views"></select>     <button id="next">Next</button>     <a class="download" id="download">Open Original Image</a>   </div>   <figure>     <img id="photo">     <figcaption id="caption"></figcaption>   </figure>   <section>     <h2>Spatial Exploration</h2>     <div id="clips"></div>     <video id="video" controls preload="metadata"></video>   </section>   <p>     <a id="blend">Download Blender Scene</a>     · Delivery Verification Record: <a href="delivery_verification.json">here</a>     · Scene & Reproduction Instructions: <a href="README.md">here</a>   </p> </main>  <script>\nconst DATA=__DATA__;let si=0,vi=0;const $=x=>document.getElementById(x);const labels={exterior_wide:\'Outdoor wide view\',exterior_street_left:\'Outdoor left view\',exterior_street_right:\'Outdoor right view\',garden_overview:\'Courtyard aerial view\',entrance_context:\'Entrance and surroundings\',outdoor_furniture:\'Outdoor furniture\',interior_wide:\'Indoor wide view\',interior_reverse:\'Indoor reverse view\',interior_diagonal:\'Indoor oblique view\',detail_primary:\'Interior details\',detail_secondary:\'Interior details, alternate view\',interior_activity:\'Functional area\',interior:\'Indoor walkthrough\',exterior:\'Outdoor walkthrough\',inside_to_outside:\'Indoor to outdoor walkthrough\',outside_to_inside:\'Outdoor to indoor walkthrough\'};\nfunction label(n){if(labels[n])return labels[n];let d=n.startsWith(\'inside_to_outside\')?\'Inside looking outside\':\'Outside looking inside\';let dist=n.includes(\'_near_\')?\'Close-up\':n.includes(\'_middle_\')?\'Medium view\':\'Wide view\';return d+\' · \'+dist+\' · \'+(n.endsWith(\'oblique\')?\'Oblique\':\'Axial\')}\nfunction show(){let s=DATA[si],p=s.images[vi];$(\'photo\').src=p.file;$(\'photo\').alt=label(p.name);$(\'views\').value=vi;$(\'caption\').textContent=s.title+\' / \'+label(p.name)+\' / 1920 × 1080\';$(\'download\').href=p.file}\nfunction choose(i){si=i;vi=0;let s=DATA[i];$(\'title\').textContent=s.title;$(\'views\').innerHTML=\'\';s.images.forEach((p,j)=>{let o=document.createElement(\'option\');o.value=j;o.textContent=label(p.name);$(\'views\').append(o)});$(\'blend\').href=s.blend;$(\'clips\').innerHTML=\'\';s.videos.forEach(v=>{let b=document.createElement(\'button\');b.textContent=label(v.name);b.onclick=()=>{$(\'video\').src=v.file};$(\'clips\').append(b)});if(s.videos.length)$(\'video\').src=s.videos[0].file;if(s.images.length)show()}\nDATA.forEach((s,i)=>{let b=document.createElement(\'button\');b.textContent=s.title;b.onclick=()=>choose(i);$(\'scenes\').append(b)});$(\'views\').onchange=e=>{vi=+e.target.value;show()};$(\'prev\').onclick=()=>{vi=(vi+DATA[si].images.length-1)%DATA[si].images.length;show()};$(\'next\').onclick=()=>{vi=(vi+1)%DATA[si].images.length;show()};choose(0);\n</script></html>'.replace(
    "__DATA__", data
)
(O / "index.html").write_text(page)
readme = """# Outdoor/Indoor Joint Generation Showcase (Connect2)

Six independent, editable Blender scenes: community restaurant, specialty coffee shop, fresh produce supermarket, community hospital, pharmacy, and library. Each scene retains a complete 3D structure, with interior, exterior, and bidirectional connection views captured within the same model. The images are not stitched together and have no added numbering.

Open `index.html` to browse images and play videos one by one. Each scene directory contains `scene.blend` as an actual model, `images/` as an independent 1920x1080 PNG image, and `videos/` as a 1280x720, 24 fps, 6-second MP4 video. Each set consists of 24 images, with each direction containing near, mid, and far distances along with forward and oblique viewpoints.

The model saving and rendering use native Blender 5.1.2 (`/usr/local/bin/blender`), with the renderer being Cycles / OptiX GPU. Official images use 96 samples, videos use 24 samples, and denoising is enabled. `generation_scripts.zip` saved a snapshot of this generation, correction, rendering, and inspection script, which is organized according to the project root directory.

Assets come from the existing commercial all43_25, hospital4, pharmacy5, and library4 scenes, together with previously generated native Infinigen indoor assets. Vegetation reuses complete trees from the specified successful full08 example. Apples, strawberries, and pineapples are generated with locally installed native Infinigen factories. No external assets were downloaded, no meshes were decimated, and no image backgrounds replaced 3D objects. Procedural modifications include real architectural openings, interior finishes, merchandise placement, and equipment details.

The detailed models of coffee equipment and medical devices have been saved at `shared_assets/refined_coffee_equipment.blend` and `shared_assets/refined_clinical_equipment.blend`, which can be used as reusable assets for subsequent scenarios. Coffee equipment includes smooth brew heads, pressure gauges, steam pipes, drip pans, and an independent coffee grinder with its own coffee beans; medical devices include bed headboards with holes, railings, caster wheels, original pillows, drooping sheets, monitors, and infusion racks.

Each `scene.blend` contains 24 photo stations, with four 144-frame, 24-fps real animation camera trajectories embedded within it. The photo stations are located at `Photographs_24_views`, while video stations are located at `Walkthroughs_4_animated_cameras`. Switching between active cameras allows for continued editing and rendering.

The historical assets of the hospital and library were originally housed within solid cores and behind back panels for display purposes. This version forms actual indoor spaces through architectural geometry while preserving the entire exterior wall and upper structure. The entrance is not achieved by hiding walls during rendering. Public building shots focus on the surroundings and local interiors around the entry point, with the original building shell retained.

Shared assets should be accessed via relative paths under `shared_assets/`. When moving delivery files, please retain the entire directory structure. Shared files have hard links to old versions to save disk space; do not modify shared files directly while editing; instead, create copies of them for changes.

Reproduce order (run from the project root directory):

```sh
blender -b -t 4 -P scripts/build_urban_v1_full_connect2.py -- restaurant
blender -b -t 4 -P scripts/refine_connect2_scene.py -- restaurant
# The hospital and library still need to run repair_connect2_public_rooms.py
# Then run finish_connect2_public_rooms.py; library also runs refine_connect2_books.py.
# run upgrade_connect2_coffee_equipment.py again
# The hospital will run the upgrade_connect2_clinical_equipment.py script again.
blender -b -t 4 -P scripts/ground_connect2_trees.py -- restaurant
blender -b -t 4 -P scripts/package_connect2_scene.py -- restaurant
blender -b -t 4 -P scripts/audit_connect2_scene.py -- restaurant
CUDA_VISIBLE_DEVICES=1 blender -b -t 6 -P scripts/render_urban_v1_full_connect2.py -- --scene restaurant --mode final --width 1920 --samples 96 --overwrite
CUDA_VISIBLE_DEVICES=1 blender -b -t 6 -P scripts/render_urban_v1_full_connect2.py -- --scene restaurant --mode video --width 1280 --samples 24 --frames 144 --overwrite > infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/logs/video_restaurant.log 2>&1
python scripts/finalize_connect2_delivery.py
```

Actual lenses align with each scene's `scene_manifest.json`; some shots were adjusted after render tests for position. Geometric validation checks near-camera, entry corridor, and model dependencies; media validation ensures that every image decodes correctly, has proper dimensions, brightness range, frame rates per video segment, resolution, and full decoding is possible. They do not equate to comprehensive physical collision verification across the entire scene.
"""
(O / "README.md").write_text(readme)
print(
    json.dumps(
        {k: v for k, v in report.items() if k != "scenes"}, ensure_ascii=False, indent=2
    )
)
sys.exit(0 if report["passed"] else 1)

"""Verify real scene/media files and maintain a single-image gallery."""
import json, subprocess, sys, hashlib, html
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageStat

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect3_plan import SCENES

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
report = {
    "verified_at_utc": datetime.now(timezone.utc).isoformat(),
    "full_video_decode": "--full-decode" in sys.argv,
    "scenes": [],
    "errors": [],
    "expected_scenes": 20,
    "expected_images": 600,
    "expected_videos": 80,
}
gallery = []
for key, title, *_ in SCENES:
    d = O / key
    mp = d / "scene_manifest.json"
    if not mp.exists():
        report["errors"].append(key + ": scene missing")
        continue
    m = json.loads(mp.read_text())
    entry = {
        "scene": key,
        "title": title,
        "layout": m["layout"],
        "building_count": m["building_count"],
        "blend": key + "/scene.blend",
        "images": [],
        "videos": [],
    }
    a = (
        json.loads((d / "geometry_audit.json").read_text())
        if (d / "geometry_audit.json").exists()
        else {}
    )
    entry["geometry_passed"] = a.get("passed", False)
    if not entry["geometry_passed"]:
        report["errors"].append(key + ": geometry checks incomplete")
    if not (d / "visual_review.json").exists():
        report["errors"].append(key + ": visual review pending")
    for name in m["shots"]:
        p = d / "images" / (name + ".png")
        if not p.exists():
            report["errors"].append(key + ": missing " + name)
            continue
        try:
            with Image.open(p) as im:
                im.load()
                size = im.size
                st = ImageStat.Stat(im.convert("L"))
                mean = st.mean[0]
                std = st.stddev[0]
            if size != (1920, 1080) or mean < 8 or std < 4:
                report["errors"].append(key + ": suspect image " + name)
            entry["images"].append(
                {
                    "name": name,
                    "file": str(p.relative_to(O)),
                    "width": size[0],
                    "height": size[1],
                    "mean": round(mean, 2),
                    "std": round(std, 2),
                }
            )
        except Exception as e:
            report["errors"].append(key + ": corrupt " + name + " " + str(e))
    for name in ["interior", "exterior", "inside_to_outside", "outside_to_inside"]:
        p = d / "videos" / (name + ".mp4")
        if not p.exists():
            report["errors"].append(key + ": missing video " + name)
            continue
        try:
            data = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
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
            if (
                data["width"] != 1280
                or data["height"] != 720
                or int(data["nb_read_frames"]) != 96
                or data["r_frame_rate"] != "24/1"
            ):
                report["errors"].append(key + ": bad video " + name)
            if "--full-decode" in sys.argv:
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"],
                    check=True,
                    capture_output=True,
                )
            entry["videos"].append(
                {"name": name, "file": str(p.relative_to(O)), **data}
            )
        except Exception as e:
            report["errors"].append(key + ": corrupt video " + name + " " + str(e))
    report["scenes"].append(entry)
    gallery.append(entry)
report["image_count"] = sum(len(x["images"]) for x in gallery)
report["video_count"] = sum(len(x["videos"]) for x in gallery)
report["scene_count"] = len(gallery)
report["passed"] = not report["errors"] and len(gallery) == 20
(O / "delivery_verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)
page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect3 · Indoor and Outdoor Joint 3D Scenes</title><style>body{background:#121b19;color:#e5ede9;margin:0;font:16px system-ui}main{max-width:1450px;margin:auto;padding:28px}h1{font-size:28px}p{color:#bac7c1;line-height:1.7}select,button{background:#263b33;color:#fff;border:1px solid #577364;padding:9px;margin:4px;border-radius:5px}img,video{display:block;width:100%;max-height:80vh;object-fit:contain;background:#09100d}a{color:#a9d2bc}nav{display:flex;flex-wrap:wrap;gap:5px}figure{margin:20px 0}figcaption{padding:12px 0}</style><main><h1>Indoor and Outdoor Joint Generation · 20 3D Blocks</h1><p id="status"></p><nav><select id="scene"></select><select id="view"></select><button id="prev">Previous Image</button><button id="next">Next Image</button><a id="original">Open Original Image</a></nav><figure><img id="image"><figcaption id="caption"></figcaption></figure><nav id="clips"></nav><video id="video" controls preload="metadata"></video><p><a id="blend">Blender 3D Scene</a> · <a href="delivery_verification.json">Verification Record</a> · <a href="README.md">Asset and Reproduction Notes</a></p></main><script>const DATA=__DATA__;const SUMMARY=__SUMMARY__;let si=0,vi=0;const $=x=>document.getElementById(x);$(\'status\').textContent=SUMMARY;const label=n=>n.replaceAll(\'inside_to_outside\',\'Inside looking outside\').replaceAll(\'outside_to_inside\',\'Outside looking inside\').replaceAll(\'near\',\'Close-up\').replaceAll(\'middle\',\'Medium view\').replaceAll(\'far\',\'Wide view\').replaceAll(\'axial\',\'Axial\').replaceAll(\'oblique\',\'Oblique\').replaceAll(\'_\',\' · \');function show(){const s=DATA[si],p=s.images[vi];if(!p){$(\'image\').removeAttribute(\'src\');$(\'caption\').textContent=\'Images are being generated\';return}$(\'image\').src=p.file;$(\'view\').value=vi;$(\'caption\').textContent=s.title+\' / \'+label(p.name);$(\'original\').href=p.file}function choose(i){si=+i;vi=0;const s=DATA[si];$(\'view\').innerHTML=\'\';s.images.forEach((p,j)=>{$(\'view\').add(new Option(label(p.name),j))});$(\'clips\').innerHTML=\'\';$(\'video\').removeAttribute(\'src\');s.videos.forEach(v=>{let b=document.createElement(\'button\');b.textContent=label(v.name);b.onclick=()=>{$(\'video\').src=v.file};$(\'clips\').append(b)});if(s.videos.length)$(\'video\').src=s.videos[0].file;$(\'blend\').href=s.blend;show()}DATA.forEach((s,i)=>$(\'scene\').add(new Option(s.title,i)));$(\'scene\').onchange=e=>choose(e.target.value);$(\'view\').onchange=e=>{vi=+e.target.value;show()};$(\'prev\').onclick=()=>{vi=(vi-1+DATA[si].images.length)%DATA[si].images.length;show()};$(\'next\').onclick=()=>{vi=(vi+1)%DATA[si].images.length;show()};if(DATA.length)choose(0);</script></html>'
status = (
    ("The file has been completed and validated." if report["passed"] else "Generation and verification are ongoing.")
    + f"Current: {report['scene_count']}/20 models, {report['image_count']}/600 images, {report['video_count']}/80 video segments."
)
(O / "index.html").write_text(
    page.replace(
        "__DATA__", json.dumps(gallery, ensure_ascii=False).replace("</", "<\\/")
    ).replace("__SUMMARY__", json.dumps(status, ensure_ascii=False))
)
print(
    json.dumps(
        {k: v for k, v in report.items() if k not in ["scenes", "errors"]},
        ensure_ascii=False,
    )
)
print("issues", len(report["errors"]))
if "--require-complete" in sys.argv and not report["passed"]:
    sys.exit(1)

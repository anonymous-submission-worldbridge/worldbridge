"""Generate a truthful single-image gallery and verify actual deliverables."""
import json, subprocess, sys, html
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageStat

R = next(p for p in Path(__file__).resolve().parents if (p / "worldbridge").is_dir())
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, SCENES


def main():
    report = dict(
        verified_at_utc=datetime.now(timezone.utc).isoformat(),
        expected_scenes=30,
        scenes=[],
        errors=[],
        full_video_decode="--full-decode" in sys.argv,
    )
    for key, title, focus, neighbors, layout, land, extras in SCENES:
        d = O / key
        m = (
            json.loads((d / "scene_manifest.json").read_text())
            if (d / "scene_manifest.json").exists()
            else {}
        )
        entry = dict(
            scene=key,
            title=title,
            focus=focus,
            landscape=land,
            layout=layout,
            images=[],
            previews=[],
            videos=[],
            blend=key + "/scene.blend",
            model_exists=(d / "scene.blend").exists(),
            expected_images=len(m.get("shots", {})),
            job=json.loads((d / "job_status.json").read_text())
            if (d / "job_status.json").exists()
            else {},
        )
        if not m or not entry["model_exists"]:
            report["errors"].append(key + ": model incomplete")
        ap = d / "geometry_audit.json"
        audit = json.loads(ap.read_text()) if ap.exists() else {}
        entry["geometry_passed"] = (
            audit.get("passed", False)
            and m.get("builder_revision", 0) >= 5
            and ap.stat().st_mtime >= (d / "scene.blend").stat().st_mtime
            if ap.exists() and (d / "scene.blend").exists()
            else False
        )
        entry["site_refined"] = m.get("site_visual_revision") == 1
        if not entry["site_refined"]:
            report["errors"].append(key + ": site visual refinements pending")
        if not entry["geometry_passed"]:
            report["errors"].append(key + ": geometric verification pending or failed")
        review = (
            json.loads((d / "visual_review.json").read_text())
            if (d / "visual_review.json").exists()
            else {}
        )
        entry["visual_review"] = review
        if (
            review.get("verdict") != "accepted"
            or review.get("builder_revision") != m.get("builder_revision")
            or not entry["model_exists"]
            or review.get("blend_mtime") != (d / "scene.blend").stat().st_mtime
        ):
            report["errors"].append(key + ": visual review pending")
        for name in m.get("shots", {}):
            p = d / "images" / (name + ".png")
            if not p.exists():
                report["errors"].append(key + ": missing image " + name)
                continue
            try:
                if p.stat().st_mtime < (d / "scene.blend").stat().st_mtime:
                    raise ValueError("image predates current scene")
                with Image.open(p) as im:
                    im.load()
                    size = im.size
                    st = ImageStat.Stat(im.convert("L"))
                if size != (1920, 1080) or st.stddev[0] < 4 or st.mean[0] < 8:
                    raise ValueError("incorrect size or suspect image")
                entry["images"].append(
                    dict(name=name, file=str(p.relative_to(O)), size=list(size))
                )
            except Exception as e:
                report["errors"].append(key + ": image " + name + " " + str(e))
        for p in (
            sorted((d / "previews").glob("*.png")) if (d / "previews").exists() else []
        ):
            stale = (
                entry["model_exists"]
                and p.stat().st_mtime < (d / "scene.blend").stat().st_mtime
            )
            entry["previews"].append(
                dict(
                    name=p.stem
                    + (
                        " (Earlier diagnostic preview)"
                        if stale
                        else " (Diagnostic preview)"
                    ),
                    file=str(p.relative_to(O)),
                    stale=stale,
                )
            )
        for name in ["interior", "exterior", "inside_to_outside", "outside_to_inside"]:
            p = d / "videos" / (name + ".mp4")
            if not p.exists():
                report["errors"].append(key + ": missing video " + name)
                continue
            try:
                if p.stat().st_mtime < (d / "scene.blend").stat().st_mtime:
                    raise ValueError("video predates current scene")
                stream = json.loads(
                    subprocess.check_output(
                        [
                            "ffprobe",
                            "-v",
                            "error",
                            "-select_streams",
                            "v:0",
                            "-count_frames",
                            "-show_entries",
                            "stream=width,height,nb_read_frames,r_frame_rate",
                            "-of",
                            "json",
                            str(p),
                        ]
                    )
                )["streams"][0]
                if (
                    stream["width"],
                    stream["height"],
                    int(stream["nb_read_frames"]),
                    stream["r_frame_rate"],
                ) != (1280, 720, 144, "24/1"):
                    raise ValueError("incorrect video specification")
                if "--full-decode" in sys.argv:
                    subprocess.run(
                        ["ffmpeg", "-v", "error", "-i", str(p), "-f", "null", "-"],
                        check=True,
                        capture_output=True,
                    )
                entry["videos"].append(
                    dict(name=name, file=str(p.relative_to(O)), **stream)
                )
            except Exception as e:
                report["errors"].append(key + ": video " + name + " " + str(e))
        report["scenes"].append(entry)
    report.update(
        scene_count=sum(s["model_exists"] for s in report["scenes"]),
        geometry_passed_count=sum(s["geometry_passed"] for s in report["scenes"]),
        site_refined_count=sum(s["site_refined"] for s in report["scenes"]),
        image_count=sum(len(s["images"]) for s in report["scenes"]),
        video_count=sum(len(s["videos"]) for s in report["scenes"]),
        expected_videos=120,
        passed=not report["errors"],
    )
    (O / "delivery_verification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect4 · 3D neighborhood</title><style>body{background:#15211c;color:#f0eee4;font:16px system-ui;margin:0}main{max-width:1440px;margin:auto;padding:24px}p{line-height:1.8;color:#cbd4c9}select,button{background:#2c4135;color:white;border:1px solid #7e9984;border-radius:5px;padding:10px;margin:5px}img,video{display:block;max-height:77vh;width:100%;object-fit:contain;background:#09100c}a{color:#b7d2b2}nav{display:flex;flex-wrap:wrap}#caption{margin:12px 0}</style><main><h1>Connected indoor and outdoor 3D neighborhood · Connect4</h1><p id="status"></p><nav><select id="scene"></select><select id="view"></select><button id="prev">Previous</button><button id="next">Next</button><a id="original">Original image</a></nav><p id="caption"></p><img id="photo"><nav id="clips"></nav><video id="video" controls preload="metadata"></video><p><a id="blend">3D model</a> · <a href="delivery_verification.json">Verification records</a> · <a href="gpu_queue_status.json">GPU  queue</a> · <a href="README.md">Documentation</a></p></main><script>const D=__DATA__,S=__SUMMARY__,$=x=>document.getElementById(x);let si=0,vi=0,V=[];$('status').textContent=S;function show(){let p=V[vi];if(!p){$('photo').removeAttribute('src');$('caption').textContent='No rendered images for this scene yet';return}$('photo').src=p.file;$('original').href=p.file;$('view').value=vi;$('caption').textContent=D[si].title+' / '+p.name}function choose(i){si=+i;vi=0;let s=D[si];V=s.images.length?s.images:s.previews;$('view').innerHTML='';V.forEach((v,i)=>$('view').add(new Option(v.name,i)));$('blend').href=s.blend;$('clips').innerHTML='';$('video').removeAttribute('src');s.videos.forEach(v=>{let b=document.createElement('button');b.textContent=v.name;b.onclick=()=>$('video').src=v.file;$('clips').append(b)});show()}D.forEach((s,i)=>$('scene').add(new Option(s.title,i)));$('scene').onchange=e=>choose(e.target.value);$('view').onchange=e=>{vi=+e.target.value;show()};$('prev').onclick=()=>{if(V.length)vi=(vi+V.length-1)%V.length;show()};$('next').onclick=()=>{if(V.length)vi=(vi+1)%V.length;show()};choose(0);</script></html>"""
    summary = f"{'All complete and verified.' if report['passed'] else 'Incomplete; current outputs are shown below.'}  models {report['scene_count']}/30, geometry checks {report['geometry_passed_count']}/30, final images {report['image_count']}, videos {report['video_count']}/120. Diagnostic previews are excluded from final image totals."
    (O / "index.html").write_text(
        page.replace(
            "__DATA__",
            json.dumps(report["scenes"], ensure_ascii=False).replace("</", "<\\/"),
        ).replace("__SUMMARY__", json.dumps(summary, ensure_ascii=False))
    )
    print(summary)
    if "--require-complete" in sys.argv and not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

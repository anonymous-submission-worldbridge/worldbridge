"""Build a local browsing page and verify actual delivered media."""
import json, html, subprocess, time
from fractions import Fraction
from pathlib import Path
from robot1_tasks import OUT, SOURCE, write, png_complete

ACTION_LABELS = {
    "start": "Indoor starting point",
    "pickup": "Pick up the item with both hands",
    "exit_and_approach": "Exit toward the pickup point",
    "carry_to_destination": "Carry the item to the destination building",
    "carry_home": "Carry the item indoors",
    "place": "Place the item",
    "return_home": "Return empty-handed to the source building",
    "complete": "Task complete",
    "outdoor": "Outdoor travel",
}


def caption(stem):
    for view, label in [
        ("third_person", "Third-person view"),
        ("first_person", "First-person view"),
    ]:
        if stem.startswith(view + "_"):
            return label + " · " + ACTION_LABELS.get(stem[len(view) + 1 :], stem)
    return stem


def main(full=False):
    c = json.loads((OUT / "task_catalogue.json").read_text())
    cards = []
    results = []
    for t in c["tasks"]:
        d = OUT / t["scene"] / t["kind"]
        state = json.loads((d / "task.json").read_text())
        rel = d.relative_to(OUT).as_posix()
        imgs = sorted(p for p in (d / "images").glob("*.png") if png_complete(p))
        videos = []
        bad = []
        if full:
            from PIL import Image

            for png in imgs:
                try:
                    with Image.open(png) as im:
                        if im.size != (1280, 720):
                            raise ValueError("Unexpected still-image dimensions")
                        im.verify()
                except Exception as exc:
                    bad.append(png.name + ": " + str(exc))
        for name in ["first_person", "third_person"]:
            p = d / (name + ".mp4")
            if p.exists():
                try:
                    r = json.loads(
                        subprocess.check_output(
                            [
                                "ffprobe",
                                "-v",
                                "error",
                                "-select_streams",
                                "v:0",
                                "-show_entries",
                                "stream=codec_name,width,height,nb_frames,r_frame_rate:format=duration",
                                "-of",
                                "json",
                                str(p),
                            ],
                            text=True,
                        )
                    )
                    if full:
                        subprocess.run(
                            [
                                "ffmpeg",
                                "-v",
                                "error",
                                "-xerror",
                                "-i",
                                str(p),
                                "-f",
                                "null",
                                "-",
                            ],
                            check=True,
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.PIPE,
                        )
                    st = r["streams"][0]
                    if int(st["nb_frames"]) != state.get("frames"):
                        raise ValueError("Frame count differs from trajectory")
                    if (st["width"], st["height"]) != (960, 540):
                        raise ValueError(
                            "Video dimensions differ from delivery specification"
                        )
                    if Fraction(st["r_frame_rate"]) != state.get("fps"):
                        raise ValueError("Video frame rate differs from trajectory")
                    if st["codec_name"] != "h264":
                        raise ValueError("Unexpected video codec")
                    videos.append(
                        dict(
                            file=name + ".mp4",
                            **st,
                            duration=float(r["format"]["duration"]),
                        )
                    )
                except Exception as e:
                    bad.append(str(e))
        trajectory = d / "trajectory.json"
        audit = d / "path_audit.json"
        valid = (
            json.loads(audit.read_text()).get("passed", False)
            if audit.exists()
            else False
        )
        animation_ok = (d / "animation_audit.json").exists() and json.loads(
            (d / "animation_audit.json").read_text()
        ).get("passed", False)
        complete = (
            len(videos) == 2 and len(imgs) >= 12 and valid and animation_ok and not bad
        )
        if full and complete:
            state["status"] = "complete"
            state["verified_at"] = time.time()
            write(d / "task.json", state)
        result = dict(
            task=t["id"],
            status=state["status"],
            image_count=len(imgs),
            videos=videos,
            path_audit_passed=valid,
            animation_audit_passed=animation_ok,
            media_complete=complete,
            errors=bad,
        )
        if (d / "error.json").exists():
            result["last_error"] = json.loads((d / "error.json").read_text())
        results.append(result)
        phases = (
            [
                "start",
                "pickup",
                "carry_to_destination",
                "place",
                "return_home",
                "complete",
            ]
            if t["kind"] == "delivery"
            else [
                "start",
                "exit_and_approach",
                "pickup",
                "carry_home",
                "place",
                "complete",
            ]
        )
        imgs.sort(
            key=lambda p: (
                next(
                    (
                        i
                        for i, a in enumerate(phases)
                        if p.stem in ["first_person_" + a, "third_person_" + a]
                    ),
                    99,
                ),
                not p.stem.startswith("third_person"),
            )
        )
        figure = ""
        captions = (
            json.loads((d / "captions.json").read_text())
            if (d / "captions.json").exists()
            else []
        )
        caption_data = html.escape(json.dumps(captions, ensure_ascii=False), quote=True)
        for name, label in [
            ("third_person", "Third-person view"),
            ("first_person", "First-person view"),
        ]:
            poster = f"{rel}/images/{name}_start.png"
            if (d / (name + ".mp4")).exists():
                figure += f'<figure><video controls preload="none" poster="{poster}" src="{rel}/{name}.mp4" data-captions="{caption_data}" ontimeupdate="stageCaption(this)"></video><figcaption>{label} · <span class="stage">Complete task</span> · <a href="{rel}/{name}.en.srt" download>Captions</a></figcaption></figure>'
        if len(videos) == 2:
            figure += '<div><button onclick="playTwin(this)">Play both views from the beginning</button><button onclick="pauseTwin(this)">Pause both views</button></div>'
        thumbs = "".join(
            f'<a href="{rel}/images/{p.name}" target="_blank"><img loading="lazy" src="{rel}/images/{p.name}"><span>{html.escape(caption(p.stem))}</span></a>'
            for p in imgs
        )
        if not imgs or not any(p.name.startswith("third_person") for p in imgs):
            thumbs += "".join(
                f'<a href="{rel}/previews/{p.name}"><img loading="lazy" src="{rel}/previews/{p.name}"><span>Preview · {html.escape(caption(p.stem))}</span></a>'
                for p in sorted((d / "previews").glob("*.png"))
            )
        links = " ".join(
            f'<a href="{rel}/{n}">{label}</a>'
            for n, label in [
                ("task.json", "Task details"),
                ("trajectory.json", "Per-frame trajectory"),
                ("path_audit.json", "Path checks"),
                ("animation.blend", "3D animation"),
            ]
            if (d / n).exists()
        )
        progress = ""
        counts = {}
        for view, label in [
            ("first_person", "First-person view"),
            ("third_person", "Third-person view"),
        ]:
            count = sum(1 for p in (d / "frames" / view).glob("*.png"))
            counts[view] = count
            if count and not (d / (view + ".mp4")).exists():
                progress += f" · {label} {count}/{state.get('frames',0)}  frames"
        result["rendered_frame_counts"] = counts
        status = (
            "Media complete"
            if complete
            else "Rendering video"
            if progress
            else {
                "planned": "Planned",
                "built": "Animation built; awaiting rendering",
                "rendered_pending_review": "Media generated",
            }.get(state["status"], state["status"])
        )
        gallery = (
            f'<details open><summary>Key-step images</summary><div class="images">{thumbs}</div></details>'
            if thumbs
            else ""
        )
        cards.append(
            f'<article id="{t["id"]}" data-kind="{t["kind"]}"><h2>{html.escape(t["scene_title"])} <small>{"Building-to-building delivery" if t["kind"]=="delivery" else "Outdoor pickup"}</small></h2><p>{html.escape(t["title"])}</p><p class="status">{html.escape(status)}{progress} · {len(imgs)}  images / {len(videos)}  videos</p><div class="videos">{figure}</div>{gallery}<nav>{links}</nav></article>'
        )
    report = dict(
        updated=time.time(),
        scene_count=c["scene_count"],
        task_count=len(results),
        complete_tasks=sum(x["media_complete"] for x in results),
        images=sum(x["image_count"] for x in results),
        videos=sum(len(x["videos"]) for x in results),
        full_video_decode=full,
        all_media_complete=all(x["media_complete"] for x in results),
        visual_review="Selected stills and sampled video frames reviewed; see per-task visual_review.json. Full videos are checked by decoding, not end-to-end visual playback.",
        tasks=results,
    )
    write(OUT / "delivery_verification.json", report)
    write(
        OUT / "status.json",
        dict(
            updated=report["updated"],
            scenes=30,
            tasks=len(results),
            animations_verified=sum(
                x["animation_audit_passed"] and x["path_audit_passed"] for x in results
            ),
            images=report["images"],
            planned_images=len(results) * 12,
            videos=report["videos"],
            planned_videos=len(results) * 2,
            rendered_video_frames=sum(
                sum(x["rendered_frame_counts"].values()) for x in results
            ),
            complete_tasks=report["complete_tasks"],
            all_media_complete=report["all_media_complete"],
        ),
    )
    page = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Robot 01 · Connected indoor and outdoor tasks</title><style>body{margin:0;background:#0c1520;color:#e7eef5;font:16px/1.7 system-ui,sans-serif}header,main{max-width:1400px;margin:auto;padding:30px}header{padding-top:55px}h1{font-size:38px;margin:0}h2{font-size:24px}small{font-size:15px;color:#60cdf2}p{max-width:1050px}.status{color:#96b4c8}article{background:#152332;border:1px solid #273e52;border-radius:15px;padding:24px;margin-bottom:28px}.videos{display:grid;grid-template-columns:repeat(auto-fit,minmax(350px,1fr));gap:15px}figure{margin:0}video{width:100%;background:#000;border-radius:8px}.images{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px;margin-top:20px}img{width:100%;border-radius:6px}a{color:#77d7fa;text-decoration:none}.images span{display:block;font-size:12px}nav{margin-top:20px;display:flex;gap:22px}button{background:#26445b;color:#fff;border:0;border-radius:6px;padding:10px 20px;margin-right:10px;cursor:pointer}.badge{color:#67daf0;font-size:20px}summary{cursor:pointer;color:#77d7fa;margin-top:18px}input{padding:10px;border:1px solid #48647a;background:#172b3b;color:white;border-radius:6px;margin:15px 0;width:300px}</style><header><h1>Robot 01 · Connected indoor and outdoor tasks</h1><p>The same white robot collects, carries, delivers, and returns through connected neighborhoods. First-person views show navigation and carrying; third-person views show walking and handoff.</p><p class="badge">SUMMARY</p><div style="display:flex;gap:18px;align-items:center"><figure><img style="width:145px" src="robot_asset/input_reference.png"><figcaption>Input reference</figcaption></figure><figure><img style="width:145px" src="robot_asset/robot_reference_3d.png"><figcaption>Articulated 3D robot</figcaption></figure><nav><a href="task_design.md">30  task designs</a><a href="tasks.csv">Task list CSV</a><a href="delivery_verification.json">Delivery verification</a></nav></div><p>Robot geometry follows  robot.png ; motion is a kinematic demonstration. Each video covers the complete task and retains trajectories, sampled path checks, and editable Blender animation. Status reflects existing files; planned totals are not counted as completed.</p><button onclick="filter('all')">All tasks</button><button onclick="filter('delivery')">Building-to-building delivery</button><button onclick="filter('fetch')">Outdoor pickup</button><br><input id="search" placeholder="Search scenes, buildings, or items" oninput="filter(currentKind)"></header><main>CARDS</main><script>function playTwin(button){const vs=button.closest('article').querySelectorAll('video');vs.forEach(v=>{v.currentTime=0;v.play().catch(()=>{})})}function pauseTwin(button){button.closest('article').querySelectorAll('video').forEach(v=>v.pause())}let currentKind='all';function filter(k){currentKind=k;const q=document.getElementById('search').value.toLowerCase();document.querySelectorAll('article').forEach(x=>x.hidden=(k!='all'&&x.dataset.kind!=k)||!x.innerText.toLowerCase().includes(q))}</script></html>"""
    page = page.replace(
        "<script>",
        '<script>function stageCaption(video){if(!video.stageRows)video.stageRows=JSON.parse(video.dataset.captions||"[]");const row=video.stageRows.find(x=>video.currentTime>=x.start&&video.currentTime<x.end);if(row)video.closest("figure").querySelector(".stage").textContent=row.text}',
    )
    page = page.replace(
        "SUMMARY",
        f"30  scenes · {len(results)}  tasks · Generated {report['images']}  images / {report['videos']}  videos · {report['complete_tasks']}  tasks with complete media",
    ).replace("CARDS", "".join(cards))
    (OUT / "index.html").write_text(page)
    print(
        json.dumps(
            {k: v for k, v in report.items() if k != "tasks"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--full-decode", action="store_true")
    a = p.parse_args()
    main(a.full_decode)

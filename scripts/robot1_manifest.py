"""Record checksums for the 420 formal image/video delivery files after validation."""
import hashlib, json, time
from robot1_tasks import OUT, write


def main():
    report = json.loads((OUT / "delivery_verification.json").read_text())
    if not report["all_media_complete"] or not report["full_video_decode"]:
        raise RuntimeError(
            "Finish full media verification before creating the final manifest"
        )
    catalogue = json.loads((OUT / "task_catalogue.json").read_text())
    files = []
    for task in catalogue["tasks"]:
        d = OUT / task["scene"] / task["kind"]
        selected = sorted((d / "images").glob("*.png")) + [
            d / "first_person.mp4",
            d / "third_person.mp4",
        ]
        if len(selected) != 14:
            raise RuntimeError("Expected 12 stills and 2 videos per task")
        for p in selected:
            with p.open("rb") as f:
                digest = hashlib.file_digest(f, "sha256").hexdigest()
            files.append(
                dict(
                    task=task["id"],
                    file=p.relative_to(OUT).as_posix(),
                    bytes=p.stat().st_size,
                    sha256=digest,
                )
            )
    write(
        OUT / "media_manifest.json",
        dict(
            updated=time.time(),
            scene_count=30,
            task_count=30,
            images=360,
            videos=60,
            file_count=len(files),
            total_bytes=sum(f["bytes"] for f in files),
            files=files,
        ),
    )
    (OUT / "media_checksums.sha256").write_text(
        "".join(f"{f['sha256']}  {f['file']}\n" for f in files)
    )
    print("Manifest complete:", len(files), "formal media files")


if __name__ == "__main__":
    main()

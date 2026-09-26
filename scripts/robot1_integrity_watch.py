"""Check completed cache writes and movies; archive damaged files for automatic retry."""
import json, os, shutil, subprocess, time, fcntl
from robot1_tasks import OUT, write, png_valid


def main():
    lock = (OUT / ".integrity_watch.lock").open("a")
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    seen = {}
    records = []
    archive = OUT / "logs/diagnostic_archive/damaged_media"
    archive.mkdir(parents=True, exist_ok=True)
    write(
        OUT / "integrity_watch_process.json", dict(pid=os.getpid(), started=time.time())
    )
    tasks = json.loads((OUT / "task_catalogue.json").read_text())["tasks"]

    def quarantine(path, reason):
        rel = path.relative_to(OUT)
        target = archive / (
            str(time.time_ns()) + "_" + rel.as_posix().replace("/", "__")
        )
        shutil.move(str(path), str(target))
        records.append(
            dict(
                file=str(rel),
                reason=reason,
                archive=str(target.relative_to(OUT)),
                time=time.time(),
            )
        )
        write(OUT / "media_recovery_log.json", records)

    while True:
        checked = 0
        for task in tasks:
            d = OUT / task["scene"] / task["kind"]
            for view in ["first_person", "third_person"]:
                damaged = False
                for p in (d / "frames" / view).glob("*.png"):
                    stat = p.stat()
                    version = (stat.st_mtime_ns, stat.st_size)
                    if time.time() - stat.st_mtime < 20 or seen.get(str(p)) == version:
                        continue
                    checked += 1
                    if not png_valid(p):
                        quarantine(p, "PNG chunk CRC or compressed pixel data failed")
                        damaged = True
                    else:
                        seen[str(p)] = version
                mp4 = d / (view + ".mp4")
                if damaged and mp4.exists():
                    quarantine(
                        mp4, "Rebuild movie after damaged source frame detection"
                    )
                if not mp4.exists():
                    continue
                stat = mp4.stat()
                version = (stat.st_mtime_ns, stat.st_size)
                if time.time() - stat.st_mtime < 10 or seen.get(str(mp4)) == version:
                    continue
                try:
                    st = json.loads(
                        subprocess.check_output(
                            [
                                "ffprobe",
                                "-v",
                                "error",
                                "-select_streams",
                                "v:0",
                                "-show_entries",
                                "stream=nb_frames,width,height",
                                "-of",
                                "json",
                                str(mp4),
                            ],
                            text=True,
                        )
                    )["streams"][0]
                    expected = json.loads((d / "task.json").read_text())["frames"]
                    if int(st["nb_frames"]) != expected or (
                        st["width"],
                        st["height"],
                    ) != (960, 540):
                        raise ValueError("Unexpected frame count or dimensions")
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-v",
                            "error",
                            "-xerror",
                            "-threads",
                            "2",
                            "-i",
                            str(mp4),
                            "-f",
                            "null",
                            "-",
                        ],
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.PIPE,
                        check=True,
                    )
                    seen[str(mp4)] = version
                except Exception as exc:
                    quarantine(mp4, "Video validation: " + str(exc))
        write(
            OUT / "integrity_watch_status.json",
            dict(
                updated=time.time(),
                checked_new_frames=checked,
                validated_files=len(seen),
                quarantined_files=len(records),
            ),
        )
        state = json.loads((OUT / "status.json").read_text())
        if state["all_media_complete"] and not checked:
            write(
                OUT / "integrity_watch_complete.json",
                dict(
                    updated=time.time(),
                    validated_files=len(seen),
                    recovered_files=len(records),
                ),
            )
            return
        time.sleep(30)


if __name__ == "__main__":
    main()

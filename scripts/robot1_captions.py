"""Write frame-aligned English task stage captions, without changing video pixels."""
import json
from robot1_tasks import OUT, NAMES, write


def stamp(seconds, separator="."):
    ms = round(seconds * 1000)
    seconds, ms = divmod(ms, 1000)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours:02}:{minutes:02}:{seconds:02}{separator}{ms:03}"


def main():
    for task in json.loads((OUT / "task_catalogue.json").read_text())["tasks"]:
        d = OUT / task["scene"] / task["kind"]
        trajectory = json.loads((d / "trajectory.json").read_text())
        rows = trajectory["frames"]
        fps = trajectory["fps"]
        home = NAMES[task["source_building"]["asset"]]
        target = (
            NAMES[task["target_building"]["asset"]] if task["target_building"] else home
        )
        labels = dict(
            start=f"Start at {home} interior",
            pickup=f"Pick up with both hands: {task['item']}",
            exit_and_approach="Pass through the entrance toward the outdoor handoff point",
            carry_to_destination=f"Carry the item outside and deliver it to {target} interior",
            carry_home=f"Carry the item back to {home} interior",
            place="Place the item on the handoff counter and release it",
            return_home=f"Return empty-handed to {home} starting position",
            complete="Task complete: the robot returns home and leaves the item at the handoff counter",
        )
        labels["turn"] = "Turn in place to face the travel direction"
        segments = []
        for row in rows:
            if not segments or segments[-1]["action"] != row["action"]:
                segments.append(
                    dict(
                        action=row["action"],
                        start=(row["frame"] - 1) / fps,
                        end=row["frame"] / fps,
                        text=labels[row["action"]],
                    )
                )
            else:
                segments[-1]["end"] = row["frame"] / fps
        write(d / "captions.json", segments)
        for view in ["first_person", "third_person"]:
            vtt = ["WEBVTT", ""]
            srt = []
            for i, seg in enumerate(segments, 1):
                vtt.extend(
                    [
                        str(i),
                        f"{stamp(seg['start'])} --> {stamp(seg['end'])}",
                        seg["text"],
                        "",
                    ]
                )
                srt.extend(
                    [
                        str(i),
                        f"{stamp(seg['start'],',')} --> {stamp(seg['end'],',')}",
                        seg["text"],
                        "",
                    ]
                )
            (d / (view + ".en.vtt")).write_text("\n".join(vtt), encoding="utf-8")
            (d / (view + ".en.srt")).write_text("\n".join(srt), encoding="utf-8")
    print("Wrote aligned Chinese stage captions for 30 tasks / 60 views")


if __name__ == "__main__":
    main()

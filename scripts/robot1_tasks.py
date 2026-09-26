"""Task catalogue and output paths for the connect4 robot demonstration."""
import json, math, os, struct, zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect4"
OUT = SOURCE.with_name(SOURCE.name + "_robot1")
NAMES = dict(
    cafe="cafe",
    restaurant="restaurant",
    market="fresh market",
    hospital="hospital",
    pharmacy="pharmacy",
    library="library",
    corner_store="711 convenience store",
    bar="bar",
    delivery="parcel station",
    police="police station",
    fire="fire station",
    gas="gas station shop",
)
ITEMS = dict(
    cafe="coffee takeaway box",
    restaurant="meal box",
    market="produce box",
    hospital="care supplies box",
    pharmacy="medicine delivery box",
    library="book parcel",
    corner_store="household supplies parcel",
    bar="beverage supplies box",
    delivery="parcel",
    police="lost-property parcel",
    fire="emergency equipment box",
    gas="supply parcel",
)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2))
    tmp.replace(path)


def png_complete(path):
    try:
        with Path(path).open("rb") as f:
            header = f.read(24)
            f.seek(-12, 2)
            end = f.read(12)
        return (
            header[:8] == b"\x89PNG\r\n\x1a\n"
            and header[12:16] == b"IHDR"
            and end == b"\x00\x00\x00\x00IEND\xaeB`\x82"
        )
    except (OSError, ValueError):
        return False


def png_valid(path):
    """Check chunk CRCs and pixel compression before reusing cached render frames."""
    try:
        data = Path(path).read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            return False
        cursor = 8
        compressed = []
        dimensions = None
        while cursor + 12 <= len(data):
            size = struct.unpack_from(">I", data, cursor)[0]
            kind = data[cursor + 4 : cursor + 8]
            end = cursor + 8 + size
            if end + 4 > len(data):
                return False
            payload = data[cursor + 8 : end]
            if (
                zlib.crc32(kind + payload) & 0xFFFFFFFF
                != struct.unpack_from(">I", data, end)[0]
            ):
                return False
            if kind == b"IHDR":
                dimensions = struct.unpack(">IIBBBBB", payload)
            if kind == b"IDAT":
                compressed.append(payload)
            cursor = end + 4
            if kind == b"IEND":
                if cursor != len(data) or dimensions is None or not compressed:
                    return False
                zlib.decompress(b"".join(compressed))
                return True
        return False
    except (OSError, ValueError, struct.error, zlib.error):
        return False


def catalogue(both=False):
    from connect4_plan import SCENES

    tasks = []
    for i, (key, *_) in enumerate(SCENES):
        m = json.loads((SOURCE / key / "scene_manifest.json").read_text())
        start = m["buildings"][0]
        targets = [b for b in m["buildings"][1:] if b["enterable"]]
        target = min(targets, key=lambda b: math.hypot(*b["position"][:2]))
        for kind in (
            ["delivery", "fetch"] if both else ["delivery" if i % 2 == 0 else "fetch"]
        ):
            item = (
                ITEMS[start["asset"]]
                if kind == "delivery"
                else (
                    "returned book parcel"
                    if start["asset"] == "library"
                    else "outdoor supply box"
                )
            )
            title = (
                f"Start at {NAMES[start['asset']]}pick up {item}, deliver it to {NAMES[target['asset']]}, place it down, and return to the starting point"
                if kind == "delivery"
                else f"Start at {NAMES[start['asset']]}go outside to the handoff point and collect {item}, bring it indoors, and place it down"
            )
            task = dict(
                id=key + "_" + kind,
                scene=key,
                scene_title=m["title"],
                kind=kind,
                title=title,
                item=item,
                source_building=start,
                target_building=target if kind == "delivery" else None,
                source_blend=str(SOURCE / key / "scene.blend"),
                robot_reference=str(ROOT / "robot.png"),
                robot_representation="Articulated procedural 3D interpretation of the supplied single-view image; not an exact reconstructed mesh",
                status="planned",
                outputs=[
                    "first_person.mp4",
                    "third_person.mp4",
                    "images/first_person_*.png",
                    "images/third_person_*.png",
                    "animation.blend",
                    "trajectory.json",
                    "path_audit.json",
                ],
            )
            d = OUT / key / kind
            d.mkdir(parents=True, exist_ok=True)
            if not (d / "task.json").exists():
                write(d / "task.json", task)
            tasks.append(task)
    write(
        OUT / "task_catalogue.json",
        dict(scene_count=30, task_count=len(tasks), tasks=tasks),
    )
    return tasks


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--both", action="store_true")
    a = p.parse_args()
    print("Tasks:", len(catalogue(a.both)))

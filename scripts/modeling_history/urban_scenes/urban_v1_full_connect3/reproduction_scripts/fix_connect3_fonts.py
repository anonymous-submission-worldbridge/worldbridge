"""Embed the installed original font faces, repairing legacy relative font paths."""
import bpy, sys, os, json
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3"
A = O / "shared_assets"
FONT_ROOT = Path("/usr/share/fonts")
fontmap = {
    p.name: p
    for p in FONT_ROOT.rglob("*")
    if p.suffix.lower() in {".ttf", ".ttc", ".otf"}
}


def fix():
    count = 0
    cache = {}
    for ob in bpy.data.objects:
        if ob.type != "FONT":
            continue
        f = ob.data.font
        if f.name == "Bfont" and not any(ord(ch) > 127 for ch in ob.data.body):
            continue
        p = (
            fontmap["NotoSansCJK-Bold.ttc"]
            if any("\u4e00" <= ch <= "\u9fff" for ch in ob.data.body)
            else fontmap.get(Path(f.filepath).name)
        )
        if p is None:
            p = (
                fontmap["NotoSansCJK-Bold.ttc"]
                if any(ord(ch) > 127 for ch in ob.data.body)
                else fontmap["DejaVuSans.ttf"]
            )
        if str(p) not in cache:
            new = bpy.data.fonts.load(str(p), check_existing=True)
            new.pack()
            cache[str(p)] = new
        ob.data.font = cache[str(p)]
        count += 1
    return count


if __name__ == "__main__":
    arg = sys.argv[-1]
    if arg == "assets":
        keys = [
            "restaurant",
            "cafe",
            "market",
            "hospital",
            "pharmacy",
            "library",
            "school",
            "gym",
            "police",
            "fire",
            "delivery",
            "parcel",
            "food_locker",
            "atm",
            "gas",
            "bank",
            "bar",
            "fastfood",
            "corner_store",
            "factory",
            "townhouse",
        ]
        for key in keys:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            p = A / (key + ".blend")
            with bpy.data.libraries.load(str(p), link=False) as (a, b):
                b.collections = ["ASSET_" + key]
            n = fix()
            if n:
                for lib in bpy.data.libraries:
                    lib.filepath = os.path.abspath(bpy.path.abspath(lib.filepath))
                tmp = A / (key + ".fonts.blend")
                bpy.data.libraries.write(
                    str(tmp),
                    set(b.collections),
                    path_remap="RELATIVE_ALL",
                    compress=True,
                )
                tmp.replace(p)
            print("FONTS_PACKED", key, n, flush=True)
    else:
        d = O / arg
        bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
        n = fix()
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
        m = json.loads((d / "scene_manifest.json").read_text())
        m["fonts_embedded"] = True
        (d / "scene_manifest.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2)
        )
        print("SCENE_FONTS_PACKED", arg, n, flush=True)

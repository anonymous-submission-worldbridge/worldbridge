"""Replace an appended building assembly with the refined existing asset."""
import bpy, sys, json, fcntl, os
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, A

key, asset = sys.argv[-2:]
d = O / key
with (d / ".render.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
    print("REFRESH_OPENED", key, flush=True)
    old = bpy.data.collections["ASSET_" + asset]
    old.name = "RETIRED_" + asset
    with bpy.data.libraries.load(str(A / (asset + ".blend")), link=False) as (src, dst):
        dst.collections = ["ASSET_" + asset]
    print("REFRESH_LOADED_ASSET", key, asset, flush=True)
    new = dst.collections[0]
    for c in list(bpy.data.collections) + [bpy.context.scene.collection]:
        if old in list(c.children):
            c.children.unlink(old)
            c.children.link(new)
    for ob in bpy.data.objects:
        if ob.instance_collection == old:
            ob.instance_collection = new
    bpy.data.collections.remove(old)
    print("REFRESH_REPLACED_COLLECTION", key, flush=True)
    for lib in bpy.data.libraries:
        p = A / Path(lib.filepath).name
        if p.exists():
            lib.filepath = "//" + os.path.relpath(p, d)
    m = json.loads((d / "scene_manifest.json").read_text())
    m[asset + "_inventory_revision"] = 2
    m[asset + "_inventory_applied_to_scene"] = True
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
    (d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
    print("BUILDING_REFRESHED", key, asset, flush=True)

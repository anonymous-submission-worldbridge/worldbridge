"""Backfill the measured ceiling lights into early, already-refined models."""
import bpy, json, sys, fcntl
from pathlib import Path
from mathutils import Matrix, Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, A

key = sys.argv[-1]
d = O / key
with (d / ".render.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    m = json.loads((d / "scene_manifest.json").read_text())
    if "ceiling-measured hospital reception and clinical lighting" not in m.get(
        "site_visual_fixes", []
    ):
        bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
        s = bpy.context.scene
        dg = bpy.context.evaluated_depsgraph_get()
        lights = bpy.data.collections["Physical_lighting_and_cameras"]
        for b in m["buildings"]:
            if b["asset"] != "hospital":
                continue
            T = Matrix(b["matrix"])
            floor = json.loads((A / "hospital.json").read_text())["floor_z"]
            for x, y in [(-3, 3), (3, 3), (-3, 6.5), (3, 6.5), (2.7, 10.3)]:
                base = T @ Vector((x, y, floor + 1.7))
                hit, p, n, f, ob, ma = s.ray_cast(
                    dg, base, Vector((0, 0, 1)), distance=5
                )
                z = min(floor + 2.65, p.z - 0.08) if hit else floor + 2.65
                data = bpy.data.lights.new("Measured reception practical", "AREA")
                data.energy = 135
                data.shape = "DISK"
                data.size = 2.0
                data.color = (1, 0.94, 0.87)
                lamp = bpy.data.objects.new(data.name, data)
                lights.objects.link(lamp)
                lamp.location = (base.x, base.y, z)
                print("MEASURED_LIGHT", tuple(lamp.location), flush=True)
        m.setdefault("site_visual_fixes", []).append(
            "ceiling-measured hospital reception and clinical lighting"
        )
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
        (d / "scene_manifest.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2)
        )

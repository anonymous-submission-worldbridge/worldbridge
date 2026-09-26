"""Build explicit structural shells where legacy boolean topology is unreliable."""
import bpy, sys, json, math
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

key = sys.argv[-1]
dest = B.OUT / key
bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
c = bpy.data.collections["Architecture_and_furnished_interior"]
m = json.loads((dest / "scene_manifest.json").read_text())


def shell(old, source_name, hole_a, hole_b):
    a, b = B.bounds(old)
    h0 = Vector([max(a[i], hole_a[i]) for i in range(3)])
    h1 = Vector([min(b[i], hole_b[i]) for i in range(3)])
    path = B.PART / m["spec"]["file"] / (m["spec"]["file"] + ".blend")
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = [source_name]
    src = dst.objects[0]
    pieces = []
    # Disjoint slab decomposition of the original authored mass minus the room.
    for axis in range(3):
        for side in [-1, 1]:
            lo = a.copy()
            hi = b.copy()
            for k in range(axis):
                lo[k] = h0[k]
                hi[k] = h1[k]
            if side < 0:
                hi[axis] = h0[axis]
            else:
                lo[axis] = h1[axis]
            if min(hi - lo) < 0.00001:
                continue
            o = B.part(
                c,
                src,
                "authored_structural_shell_" + source_name,
                (lo + hi) / 2,
                hi - lo,
            )
            for mod in o.modifiers:
                if mod.type == "BEVEL":
                    mod.width = min(0.004, min(hi - lo) / 6)
                    mod.segments = 3
            pieces.append(o.name)
    c.objects.unlink(old)
    m.setdefault("structural_shell_repairs", []).append(
        {
            "source": source_name,
            "retained_pieces": pieces,
            "void": [list(hole_a), list(hole_b)],
        }
    )


if key == "hospital":
    old = next(o for o in c.objects if "traditional:tower_mass" in o.name)
    shell(
        old,
        "hospital:traditional:tower_mass",
        Vector((-5.05, 0, 0.405)),
        Vector((5.05, 11.8, 3.97)),
    )
    # Clinical washable wall liners reuse the authored interior wall finish mesh.
    src = next(o for o in c.objects if "lobby_floor" in o.name)
    pale = B.material("clinical_wall_finish", (0.57, 0.66, 0.65), 0.62)
    for name, p, d in [
        ("left", (-4.97, 7, 2.15), (0.065, 9.4, 3.45)),
        ("right", (4.97, 7, 2.15), (0.065, 9.4, 3.45)),
        ("rear", (0, 11.73, 2.15), (9.95, 0.065, 3.45)),
    ]:
        o = B.part(c, src, "washable_clinic_wall_" + name, p, d)
        B.assign(o, pale)
    # Reposition front-facing counter monitors so their bases rest on the counter.
    for o in list(c.objects):
        if o.name.startswith("connect2:reception_computer"):
            c.objects.unlink(o)
    ink = B.material("clinical_information_ink", (0.025, 0.12, 0.15), 0.4)
    B.text(c, "clinical_service_sign", "COMMUNITY CARE", (0, 11.68, 3.1), 0.28, ink)
    # Retain manufactured bed geometry; round the authored head/foot panels.
    for o in c.objects:
        if "triage_" in o.name and ":endboard_" in o.name:
            for mod in o.modifiers:
                if mod.type == "BEVEL":
                    mod.width = 0.065
                    mod.segments = 6
    # Extend entry videos farther into the now continuous reception space.
    m["video_inside_y"] = 2.9
    m["shots"]["detail_secondary"] = {
        "position": [2.7, 8.0, 2.3],
        "target": [2.7, 10.55, 1.23],
        "lens": 37,
    }
elif key == "library":
    for token, source in [
        ("B:occupied_shell", "library4:B:occupied_shell"),
        ("B:dark_plinth", "library4:B:dark_plinth"),
    ]:
        old = next(o for o in c.objects if token in o.name)
        shell(old, source, Vector((-8.2, -0.5, 0.10)), Vector((8.2, 13, 4.28)))
    # All native books rest on the real shelf footprint, including its depth.
    for o in list(c.objects):
        if "native_shelf_books" in o.name:
            o.location.y = 11.73
            # Taller hardbacks, fewer repeated columns, and varied book-block sizes.
            xx = o.location.x
            center = min([-5.8, -2.0, 2.0, 5.8], key=lambda x: abs(x - xx))
            idx = round((xx - center + 1.2) / 0.27)
            if idx % 2:
                c.objects.unlink(o)
            else:
                o.location.x = center - 1.00 + (idx // 2) * 0.48
                o.scale = (1.45, 1.45, 1.45)
    # A neutral limewashed interior keeps masonry's exterior identity, without
    # exposing raw structural brick as every interior room surface.
    src = next(
        o
        for o in c.objects
        if o.name.startswith("connect2:reading_hall_structural_floor")
    )
    wall = B.material("reading_room_limewash", (0.48, 0.43, 0.34), 0.72)
    for name, p, d in [
        ("left", (-8.15, 7.8, 2.20), (0.06, 10.4, 4.06)),
        ("right", (8.15, 7.8, 2.20), (0.06, 10.4, 4.06)),
        ("rear", (0, 12.94, 2.20), (16.35, 0.06, 4.06)),
    ]:
        ob = B.part(c, src, "reading_room_finish_" + name, p, d)
        B.assign(ob, wall)
    m["video_inside_y"] = 2.9
(dest / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
print("PUBLIC_SHELL_FINISHED", key)

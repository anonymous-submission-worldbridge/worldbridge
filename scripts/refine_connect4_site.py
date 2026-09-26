"""Fix observed site rendering artifacts without changing building assets."""
import bpy, sys, json, os, fcntl
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import O, A


def refine(key):
    d = O / key
    with (d / ".render.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        m = json.loads((d / "scene_manifest.json").read_text())
        if m.get("site_visual_revision") == 1:
            return
        if Path(bpy.data.filepath).resolve() != (d / "scene.blend").resolve():
            bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
        c = bpy.data.collections["Connected_streets_and_landscape"]
        s = bpy.context.scene
        for ob in c.objects:
            if (
                "perimeter_road" in ob.name or "raised_sidewalk" in ob.name
            ) and ob.dimensions.x > ob.dimensions.y:
                ob.location.z += 0.001
        for mat in bpy.data.materials:
            if (
                mat.library
                or not mat.name.startswith("connect4:soil")
                or not mat.use_nodes
            ):
                continue
            ns = mat.node_tree.nodes
            lk = mat.node_tree.links
            geo = ns.new("ShaderNodeNewGeometry")
            for node in ns:
                if node.type == "TEX_NOISE":
                    lk.new(geo.outputs["Position"], node.inputs["Vector"])
        # The hospital's authored entry-room ceiling is lower than the large outer
        # building envelope. Place illumination below the measured occupied ceiling.
        dg = bpy.context.evaluated_depsgraph_get()
        lights = bpy.data.collections["Physical_lighting_and_cameras"]
        for building in m["buildings"]:
            if building["asset"] != "hospital":
                continue
            T = Matrix(building["matrix"])
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
        if m["landscape"] == "river":
            water = next(
                o
                for o in c.objects
                if o.instance_collection and o.instance_collection.name == "ASSET_river"
            )
            with bpy.data.libraries.load(
                str(A / "river_extension.blend"), link=True
            ) as (src, dst):
                dst.collections = ["ASSET_river_extension"]
            length = json.loads((A / "river.json").read_text())["dimensions"][1]
            for side in [-1, 1]:
                ob = bpy.data.objects.new("connect4:continuous_river_bank", None)
                c.objects.link(ob)
                ob.instance_type = "COLLECTION"
                ob.instance_collection = dst.collections[0]
                ob.matrix_world = water.matrix_world @ Matrix.Translation(
                    Vector((0, side * length, 0))
                )
                ob["asset_source"] = "existing river meshes excluding bridge"
            channel = next(
                o
                for o in water.instance_collection.objects
                if "incised_alluvial_channel" in o.name
            )
            ps = [
                water.matrix_world @ channel.matrix_world @ Vector(v)
                for v in channel.bound_box
            ]
            lo = [min(p[k] for p in ps) for k in range(3)]
            hi = [max(p[k] for p in ps) for k in range(3)]
            lo[1] -= length
            hi[1] += length
            pieces = [o for o in c.objects if "terrain_around_channel" in o.name]
            src = pieces[0]
            center = Vector(m["site_bounds"][0]) + Vector(m["site_bounds"][1])
            center *= 0.5
            for i, (xa, xb, ya, yb) in enumerate(
                [
                    (center.x - 600, lo[0], center.y - 600, center.y + 600),
                    (hi[0], center.x + 600, center.y - 600, center.y + 600),
                    (lo[0], hi[0], center.y - 600, lo[1]),
                    (lo[0], hi[0], hi[1], center.y + 600),
                ]
            ):
                ob = pieces[i]
                ob.location = ((xa + xb) / 2, (ya + yb) / 2, -0.20)
                bpy.context.view_layer.update()
                ob.dimensions = (xb - xa, yb - ya, 0.30)
                ob["expected_dimensions"] = [xb - xa, yb - ya, 0.30]
            m["river_extent_m"] = length * 3
        m["site_visual_revision"] = 1
        m["site_visual_fixes"] = [
            "separate intersecting road and sidewalk surfaces by 1mm",
            "world-space soil texture",
            "existing continuous river bank meshes and native groundcover where applicable",
            "ceiling-measured hospital reception and clinical lighting",
        ]
        for lib in bpy.data.libraries:
            candidate = A / Path(lib.filepath).name
            if candidate.exists():
                lib.filepath = "//" + os.path.relpath(candidate, d)
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
        (d / "scene_manifest.json").write_text(
            json.dumps(m, ensure_ascii=False, indent=2)
        )
        print("SITE_VISUAL_FIXED", key, flush=True)


if __name__ == "__main__":
    refine(sys.argv[-1])

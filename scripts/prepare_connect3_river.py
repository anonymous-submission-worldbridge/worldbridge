"""Reuse a 42 m segment of the user's fully modeled river and timber bridge."""
import bpy, bmesh, sys
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import prepare_connect3_assets as A

A.reset()
f = (
    R
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_07-river5/urban_v1_full_07-river5.blend"
)
with bpy.data.libraries.load(str(f), link=False) as (a, b):
    b.objects = [
        n
        for n in a.objects
        if n.startswith("full07_river5:")
        and not any(t in n for t in ["MASTER", "grass", "botanical", "scatter"])
    ]
c = bpy.data.collections.new("river_segment")
bpy.context.scene.collection.children.link(c)
for ob in b.objects:
    c.objects.link(ob)
bpy.context.view_layer.update()
poses = {ob: ob.matrix_world.copy() for ob in c.objects}
for ob, m in poses.items():
    ob.parent = None
    ob.constraints.clear()
    ob.animation_data_clear()
    ob.matrix_world = m
    if ob.type != "MESH":
        if not 5 < ob.location.y < 47:
            c.objects.unlink(ob)
        continue
    lo = min((m @ Vector(v)).y for v in ob.bound_box)
    hi = max((m @ Vector(v)).y for v in ob.bound_box)
    if hi < 5 or lo > 47:
        c.objects.unlink(ob)
        continue
    if lo < 5 or hi > 47:
        ob.data = ob.data.copy()
        ob.data.transform(m)
        ob.matrix_world.identity()
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        for y, normal in [(5, (0, -1, 0)), (47, (0, 1, 0))]:
            bmesh.ops.bisect_plane(
                bm,
                geom=list(bm.verts) + list(bm.edges) + list(bm.faces),
                dist=0.00001,
                plane_co=(0, y, 0),
                plane_no=normal,
                clear_outer=True,
                clear_inner=False,
            )
        bm.to_mesh(ob.data)
        bm.free()
        ob.data.update()
A.save("river", c, f)
A.external(
    "bench", "urban_v3_lake3", ["urban:lake3:MASTER_reused_complex_classic_bench"]
)

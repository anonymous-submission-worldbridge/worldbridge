"""Extract existing individual botanical blades/groundcover, never flat green proxies."""
import bpy, sys
from pathlib import Path
from mathutils import Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
from connect4_plan import A
from prepare_connect4_assets import reset, root, save
import prepare_connect3_assets as measures

reset()
source = A / "fountain0.blend"
with bpy.data.libraries.load(str(source), link=False) as (src, dst):
    dst.objects = [
        n for n in src.objects if "presentation_lawn" in n or "natural_lawn" in n
    ]
c = bpy.data.collections.new("ASSET_botanical_island")
root(c)
for ob in dst.objects:
    c.objects.link(ob)
bpy.context.view_layer.update()
m = measures.metadata(c)
lo, hi = map(Vector, m["bounds"])
offset = Vector((-(lo.x + hi.x) / 2, -(lo.y + hi.y) / 2, -lo.z))
poses = {ob: ob.matrix_world.copy() for ob in c.objects}
for ob, T in poses.items():
    ob.parent = None
    ob.matrix_world = T
    ob.location += offset
save(
    "botanical_island",
    c,
    source,
    dict(
        geometry_policy="original tapered grass blades, thatch and broadleaf rosettes"
    ),
)

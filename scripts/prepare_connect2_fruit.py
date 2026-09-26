"""Generate full-resolution native fruit factories in the installed Infinigen env."""
import sys, json, os, traceback
from pathlib import Path

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "infinigen"))
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import bpy
from mathutils import Vector
from infinigen.assets.objects.fruits.apple import FruitFactoryApple
from infinigen.assets.objects.fruits.strawberry import FruitFactoryStrawberry
from infinigen.assets.objects.fruits.pineapple import FruitFactoryPineapple

O = R / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2/shared_assets"
bpy.ops.wm.read_factory_settings(use_empty=True)
cols = []
report = []
for i, F in enumerate(
    [FruitFactoryApple, FruitFactoryStrawberry, FruitFactoryPineapple]
):
    try:
        f = F(92231 + i)
        o = f.spawn_asset(0)
        f.finalize_assets([o])
        bpy.context.view_layer.update()
        c = bpy.data.collections.new("NATIVE_" + F.__name__)
        bpy.context.scene.collection.children.link(c)
        # Include factory children, maintaining their transforms.
        objects = [o] + list(o.children_recursive)
        for ob in objects:
            if ob.name not in c.objects:
                c.objects.link(ob)
        pts = [
            ob.matrix_world @ Vector(v)
            for ob in objects
            if ob.type == "MESH"
            for v in ob.bound_box
        ]
        mn = Vector([min(p[k] for p in pts) for k in range(3)])
        mx = Vector([max(p[k] for p in pts) for k in range(3)])
        # Native fruit defaults are botanical units; use realistic retail dimensions.
        size = [0.085, 0.04, 0.28][i]
        s = size / (mx.z - mn.z)
        for ob in objects:
            mw = ob.matrix_world.copy()
            ob.parent = None
            ob.matrix_world = mw
        for ob in objects:
            ob.location -= Vector(((mx.x + mn.x) / 2, (mx.y + mn.y) / 2, mn.z))
            ob.location *= s
            ob.scale *= s
            ob["asset_factory"] = F.__name__
            ob["factory_seed"] = 92231 + i
        cols.append(c)
        report.append({"factory": F.__name__, "seed": 92231 + i, "height_m": size})
        print("FRUIT_READY", F.__name__, flush=True)
    except Exception:
        traceback.print_exc()
bpy.data.libraries.write(str(O / "native_fruit.blend"), set(cols), compress=True)
(O / "native_fruit.json").write_text(json.dumps(report, indent=2))

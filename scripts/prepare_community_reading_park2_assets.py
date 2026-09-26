"""Generate original Infinigen factory geometry, including a width-parameterized bench."""
import os, sys, json, math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "infinigen"))
os.environ["OPENCV_IO_ENABLE_OPENEXR"] = "1"
import bpy
from mathutils import Vector
from infinigen.assets.objects.seating.chairs.chair import ChairFactory
from infinigen.assets.objects.tables.dining_table import TableDiningFactory
from infinigen.assets.objects.tableware.cup import CupFactory
from infinigen.assets.objects.tableware.plate import PlateFactory
from infinigen.assets.objects.tableware.spoon import SpoonFactory
from infinigen.assets.objects.tableware.fork import ForkFactory
from infinigen.assets.materials.wood.wood import Wood
from infinigen.assets.materials.ceramic.ceramic import Ceramic
from infinigen.assets.materials.metal.brushed_metal import BrushedMetal

OUT = (
    ROOT
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect3/community_reading_park2/assets"
)
OUT.mkdir(parents=True, exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
from infinigen.core.util.math import FixedSeed

with FixedSeed(932020):
    wood = Wood()()
    ceramic = Ceramic()()
    metal = BrushedMetal()()
collections = []
report = []
for i, (label, F) in enumerate(
    [
        ("table", TableDiningFactory),
        ("chair", ChairFactory),
        ("bench", ChairFactory),
        ("cup", CupFactory),
        ("plate", PlateFactory),
        ("spoon", SpoonFactory),
        ("fork", ForkFactory),
    ]
):
    seed = 932020 + i
    f = F(
        seed,
        coarse=False,
        **({"dimensions": (1.55, 1.05, 0.77)} if label == "table" else {})
    )
    overrides = {}
    if label == "table":
        f.params["TopMaterial"] = wood
        f.params["LegMaterial"] = metal
    if label in {"chair", "bench"}:
        overrides = dict(
            width=1.70 if label == "bench" else 0.46,
            size=0.46,
            leg_height=0.45,
            back_height=0.44,
            has_arm=True,
            back_type="horizontal-bar",
            is_seat_round=False,
            leg_type="vertical",
            has_leg_x_bar=True,
            has_leg_y_bar=True,
        )
        for k, v in overrides.items():
            setattr(f, k, v)
        f.post_init()
        f.surface = wood
        f.panel_surface = wood
        f.limb_surface = metal
    if label in {"cup", "plate"}:
        f.surface = f.inside_surface = f.guard_surface = ceramic
        f.scratch = f.edge_wear = None
    if label == "cup":
        overrides = dict(
            is_short=True,
            is_profile_straight=True,
            depth=0.43,
            scale=0.22,
            has_wrap=False,
            has_inside=True,
            has_guard=True,
            handle_location=0.60,
            handle_radius=0.14,
            handle_inner_radius=0.027,
            handle_taper_x=0.2,
            handle_taper_y=0.2,
        )
        for k, v in overrides.items():
            setattr(f, k, v)
    if label in {"spoon", "fork"}:
        f.surface = metal
        f.scratch = f.edge_wear = None
    o = f.spawn_asset(0)
    f.finalize_assets([o])
    bpy.context.view_layer.update()
    objects = [o] + list(o.children_recursive)
    # ChairFactory's built-in +pi/2 produces a chair facing +X. Bench faces -Y.
    if label == "bench":
        o.rotation_euler.z -= math.pi / 2
    bpy.context.view_layer.update()
    for ob in objects:
        mw = ob.matrix_world.copy()
        ob.parent = None
        ob.matrix_world = mw
    pts = [
        ob.matrix_world @ Vector(v)
        for ob in objects
        if ob.type == "MESH"
        for v in ob.bound_box
    ]
    lo = Vector([min(v[k] for v in pts) for k in range(3)])
    hi = Vector([max(v[k] for v in pts) for k in range(3)])
    offset = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    c = bpy.data.collections.new("PARK2_NATIVE_" + label)
    for ob in objects:
        ob.location -= offset
        c.objects.link(ob)
        ob["asset_factory"] = F.__name__
        ob["factory_seed"] = seed
        ob["native_role"] = label
        if ob.type == "MESH":
            for face in ob.data.polygons:
                face.use_smooth = True
    collections.append(c)
    r = dict(
        role=label,
        collection=c.name,
        factory=F.__name__,
        seed=seed,
        parameters=overrides,
        dimensions=list(hi - lo),
        vertices=sum(len(ob.data.vertices) for ob in objects if ob.type == "MESH"),
        source_module=F.__module__,
    )
    report.append(r)
    print("NATIVE_READY", json.dumps(r), flush=True)
bpy.data.libraries.write(
    str(OUT / "native_furniture.blend"), set(collections), compress=True
)
(OUT / "native_furniture.json").write_text(json.dumps(report, indent=2))
print("NATIVE_GENERATION_COMPLETE", flush=True)

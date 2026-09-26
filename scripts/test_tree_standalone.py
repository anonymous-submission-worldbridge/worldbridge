"""
test_tree_standalone.py — Generate ONE TreeFactory tree in an empty scene and render it.
Tests if the tree itself looks correct in isolation (without FlowerPlant/other objects).
Output: ${WORLDBRIDGE_ROOT}/infinigen/outputs/test_tree_standalone/
"""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths["WORLDBRIDGE_SITE_PACKAGES"]

import sys
from pathlib import Path

REPO = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen")
CONDA = Path(f"{_wb_WORLDBRIDGE_SITE_PACKAGES}")
sys.path.insert(0, str(REPO))
if CONDA.exists():
    sys.path.insert(0, str(CONDA))
sys.path.insert(0, f"{_wb_WORLDBRIDGE_ROOT}/scripts")

import bpy
import gin
from infinigen.core import init as _inf_init
from infinigen.core.util.math import FixedSeed

gin.clear_config()
_inf_init.apply_gin_configs(
    config_folders=[str(REPO / "infinigen_examples/configs_nature")],
    configs=[],
    overrides=[],
    skip_unknown=True,
    finalize_config=False,
    mandatory_folders=[],
)

OUT = Path(f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/test_tree_standalone")
OUT.mkdir(parents=True, exist_ok=True)

# Reset scene
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.scene.render.engine = "CYCLES"

# GPU
for dtype in ("OPTIX", "CUDA", "HIP"):
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = dtype
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
        print(f"[test] GPU: {dtype}")
        break
    except:
        pass

sc = bpy.context.scene
sc.cycles.samples = 128
sc.cycles.use_denoising = True
sc.render.resolution_x = 1280
sc.render.resolution_y = 720

# Sky
world = bpy.data.worlds.new("Sky")
bpy.context.scene.world = world
world.use_nodes = True
nt = world.node_tree
bg = nt.nodes.get("Background") or nt.nodes.new("ShaderNodeBackground")
env = nt.nodes.new("ShaderNodeTexSky")
env.sky_type = "NISHITA"
env.sun_elevation = 0.7
nt.links.new(env.outputs["Color"], bg.inputs["Color"])
bg.inputs["Strength"].default_value = 1.0
out_node = nt.nodes.get("World Output") or nt.nodes.new("ShaderNodeOutputWorld")
nt.links.new(bg.outputs["Background"], out_node.inputs["Surface"])
bpy.context.scene.render.film_transparent = False

# Camera
bpy.ops.object.camera_add(location=(5, -8, 6))
cam = bpy.context.active_object
cam.rotation_euler = (1.1, 0, 0.5)
bpy.context.scene.camera = cam
bpy.context.scene.render.use_sequencer = False

# Ground plane
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0))
ground = bpy.context.active_object
ground.name = "ground"
bpy.ops.object.material_slot_add()
mat_g = bpy.data.materials.new("ground_mat")
mat_g.use_nodes = True
mat_g.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (
    0.1,
    0.35,
    0.08,
    1.0,
)
mat_g.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
ground.data.materials.append(mat_g)

# Sun lamp
bpy.ops.object.light_add(type="SUN", location=(5, 5, 10))
sun = bpy.context.active_object
sun.data.energy = 3.0

print("[test] Generating TreeFactory tree (seed=42) ...")
try:
    from infinigen.assets.objects.trees.generate import TreeFactory

    with FixedSeed(42):
        fac = TreeFactory(seed=42, season="summer", coarse=False, fruit_chance=0.0)
        root = fac.spawn_asset(0, loc=(0, 0, 0), rot=(0, 0, 0))
    if root:
        print(
            f"[test] Tree root: {root.name}, dims={root.dimensions.x:.2f},{root.dimensions.y:.2f},{root.dimensions.z:.2f}"
        )
        print(
            f"[test] Tree loc: {root.location.x:.2f},{root.location.y:.2f},{root.location.z:.2f}"
        )
        print(
            f"[test] Tree scale: {root.scale.x:.3f},{root.scale.y:.3f},{root.scale.z:.3f}"
        )
        C_tree = bpy.data.collections.new("Trees")
        bpy.context.scene.collection.children.link(C_tree)
        for oc in list(root.users_collection):
            try:
                oc.objects.unlink(root)
            except:
                pass
        try:
            C_tree.objects.link(root)
        except:
            pass
        for o in list(bpy.data.objects):
            if o != root and o.parent == root:
                for oc in list(o.users_collection):
                    try:
                        oc.objects.unlink(o)
                    except:
                        pass
                try:
                    C_tree.objects.link(o)
                except:
                    pass
    print("[test] Tree done")
except Exception as e:
    import traceback

    print(f"[test] ERROR: {e}")
    traceback.print_exc()

# Save blend
blend_path = str(OUT / "test_tree.blend")
bpy.ops.wm.save_as_mainfile(filepath=blend_path)
print(f"[test] Saved {blend_path}")

# Render
sc.render.filepath = str(OUT / "test_tree.png")
sc.render.image_settings.file_format = "PNG"
sc.view_settings.view_transform = "AgX"
sc.view_settings.exposure = -0.5
bpy.ops.render.render(write_still=True)
print("[test] Render done")

"""Quick 1-frame render to verify vehicle is visible."""

# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath
_wb_root = next(p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir())
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables
_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths['WORLDBRIDGE_ROOT']
_wb_WORLDBRIDGE_EXTERNAL = _wb_paths['WORLDBRIDGE_EXTERNAL']
_wb_WORLDBRIDGE_SITE_PACKAGES = _wb_paths['WORLDBRIDGE_SITE_PACKAGES']

import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
CONDA = Path(f'{_wb_WORLDBRIDGE_SITE_PACKAGES}')
if CONDA.exists(): sys.path.insert(0, str(CONDA))

import bpy
import infinigen.core.tagging as _tag_mod
_tag_mod.tag_object = lambda obj, s, **kw: obj.__setitem__("semantic", s)

from infinigen.assets.objects.vehicles.openx_vehicle import OpenXVehicleFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

OUT = f'{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_vehicle/single_frame.png'

def enable_gpu():
    prefs = bpy.context.preferences
    cp = prefs.addons.get("cycles")
    if not cp: return
    cp = cp.preferences
    for backend in ("OPTIX","CUDA","HIP","METAL"):
        try:
            cp.compute_device_type = backend; cp.refresh_devices()
            devs = cp.get_devices_for_type(backend)
            if devs:
                for d in devs: d.use = (d.type != "CPU")
                print(f"[GPU] {backend}: {[d.name for d in devs if d.use]}")
                break
        except Exception: continue
    bpy.context.scene.cycles.device = "GPU"

def _mat(name, color, roughness=0.55, metallic=0.0, emission_strength=0.0):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = color
        bsdf.inputs["Roughness"].default_value = roughness
        bsdf.inputs["Metallic"].default_value = metallic
        if emission_strength > 0:
            for k in ("Emission Color","Emission"):
                if k in bsdf.inputs: bsdf.inputs[k].default_value = color; break
            if "Emission Strength" in bsdf.inputs:
                bsdf.inputs["Emission Strength"].default_value = emission_strength
    return mat

def _glass(name):
    mat = bpy.data.materials.new(name); mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        bsdf.inputs["Base Color"].default_value = (0.04,0.07,0.10,1.0)
        bsdf.inputs["Roughness"].default_value = 0.02
        for k in ("Transmission Weight","Transmission"):
            if k in bsdf.inputs: bsdf.inputs[k].default_value = 0.92; break
    return mat

def _car_paint(name, color):
    mat = _mat(name, color, roughness=0.18, metallic=0.82)
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    if bsdf:
        for k in ("Coat Weight","Clearcoat"):
            if k in bsdf.inputs: bsdf.inputs[k].default_value = 0.88; break
        for k in ("Coat Roughness","Clearcoat Roughness"):
            if k in bsdf.inputs: bsdf.inputs[k].default_value = 0.032; break
    return mat

enable_gpu()
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)

M = {}
M["car_red"]=_car_paint("car_red",(0.58,0.04,0.03,1.0))
M["car_blue"]=_car_paint("car_blue",(0.03,0.12,0.52,1.0))
M["car_white"]=_car_paint("car_white",(0.82,0.84,0.80,1.0))
M["car_black"]=_car_paint("car_black",(0.04,0.04,0.042,1.0))
M["car_silver"]=_car_paint("car_silver",(0.55,0.57,0.60,1.0))
M["car_glass"]=_glass("car_glass")
M["tire"]=_mat("tire",(0.022,0.020,0.018,1.0),roughness=0.90)
M["rim_metal"]=_mat("rim_metal",(0.80,0.80,0.84,1.0),metallic=0.96,roughness=0.10)
M["chrome"]=_mat("chrome",(0.88,0.88,0.90,1.0),metallic=1.0,roughness=0.03)
M["metal"]=_mat("metal",(0.18,0.18,0.18,1.0),roughness=0.62,metallic=0.22)
M["brake_disc"]=_mat("brake_disc",(0.30,0.28,0.26,1.0),metallic=0.55,roughness=0.52)
M["headlight"]=_mat("headlight",(1.0,0.92,0.70,1.0),emission_strength=2.5)
M["headlight_led"]=_mat("headlight_led",(0.94,0.96,1.0,1.0),emission_strength=5.0)
M["tail_light"]=_mat("tail_light",(0.90,0.02,0.01,1.0),emission_strength=2.0)
M["tail_indicator"]=_mat("tail_indicator",(0.90,0.42,0.02,1.0),emission_strength=1.2)
M["tail_reverse"]=_mat("tail_reverse",(0.95,0.95,0.95,1.0),emission_strength=0.9)
M["license_plate"]=_mat("license_plate",(0.92,0.90,0.78,1.0),roughness=0.42)
M["signal_box"]=_mat("signal_box",(0.030,0.032,0.030,1.0),roughness=0.72)
M["car_interior"]=_mat("car_interior",(0.04,0.04,0.05,1.0),roughness=0.86)
M["bus_yellow"]=_car_paint("bus_yellow",(0.92,0.66,0.08,1.0))

factory = OpenXVehicleFactory(M, assets_root=f'{_wb_WORLDBRIDGE_EXTERNAL}/openx-assets', fallback=True)
req = UrbanAssetRequest(asset_type="vehicle", location=(0.0,0.0,0.0),
                        semantic="vehicle", yaw=0.0,
                        params={"id":"0","axis":"x","variant":"sedan","color":"car_blue"})
objects, meta = factory.create(req)
print(f"[diag] {len(objects)} objects  source={meta.get('source')}  name={meta.get('name')}")

# print world bboxes of mesh objects after transform
bpy.context.view_layer.update()
xs, ys, zs = [], [], []
for obj in objects:
    if obj.type != "MESH": continue
    from mathutils import Vector
    mw = obj.matrix_world
    for c in obj.bound_box:
        w = mw @ Vector(c)
        xs.append(w.x); ys.append(w.y); zs.append(w.z)
if xs:
    print(f"[diag] World bbox after placement:")
    print(f"  X [{min(xs):.3f}, {max(xs):.3f}]  len={max(xs)-min(xs):.3f}")
    print(f"  Y [{min(ys):.3f}, {max(ys):.3f}]  wid={max(ys)-min(ys):.3f}")
    print(f"  Z [{min(zs):.3f}, {max(zs):.3f}]  hgt={max(zs)-min(zs):.3f}")

# ground
bpy.ops.mesh.primitive_plane_add(size=30.0, location=(0,0,0))
gp = bpy.context.active_object
gp.data.materials.append(_mat("asphalt",(0.032,0.034,0.036,1.0),roughness=0.92))

# world sky
world = bpy.context.scene.world
world.use_nodes = True; nt = world.node_tree; nt.nodes.clear()
bg = nt.nodes.new("ShaderNodeBackground")
sky = nt.nodes.new("ShaderNodeTexSky"); out = nt.nodes.new("ShaderNodeOutputWorld")
sky.sky_type = "NISHITA"; sky.sun_elevation = math.radians(35)
bg.inputs["Strength"].default_value = 1.2
nt.links.new(sky.outputs["Color"], bg.inputs["Color"])
nt.links.new(bg.outputs["Background"], out.inputs["Surface"])

# sun
bpy.ops.object.light_add(type="SUN", location=(4,-6,12))
sun = bpy.context.active_object
sun.data.energy = 800; sun.rotation_euler = (math.radians(40),math.radians(20),math.radians(60))

# camera — side view for easy inspection
bpy.ops.object.camera_add(location=(8, 0, 2.0))
cam = bpy.context.active_object; cam.name = "Camera"
bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0,0,0.72))
tgt = bpy.context.active_object
track = cam.constraints.new("TRACK_TO")
track.target = tgt; track.track_axis = "TRACK_NEGATIVE_Z"; track.up_axis = "UP_Y"
bpy.context.scene.camera = cam

sc = bpy.context.scene
sc.render.engine = "CYCLES"; sc.cycles.samples = 64
sc.cycles.use_denoising = True
sc.render.resolution_x = 1920; sc.render.resolution_y = 1080
sc.render.image_settings.file_format = "PNG"
sc.render.filepath = OUT
bpy.ops.render.render(write_still=True)
print(f"[done] {OUT}")

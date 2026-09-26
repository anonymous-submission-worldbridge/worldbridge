"""
Build urban_v3_all32 by refining the existing urban_v3_all30 blend in place.

Two targeted edits requested (continuing from all30):

  1. Give the carriageway the deep-asphalt look of urban_v3_all18. NOTE: this
     scene renders through the AgX view transform (exposure -2.2), which lifts
     dark surfaces to grey — so importing all18's own material is NOT enough
     (it came out medium-grey). Instead we build a genuinely deep-charcoal
     asphalt material (very low albedo ~0.008 + near-zero specular) so it reads
     as dark asphalt THROUGH AgX, and assign it to the Road-collection objects
     (road_n/s/e/w + isect). Keep the white dashed lane lines (short dashes, NOT
     arrows — already the case in all30) + yellow centre line + zebra crossings
     + sidewalks.
  2. Clear the roadway of non-vehicle props: remove the two K6 telephone booths
     (all their K6_* objects, incl. the oversized K6_Facade white panels).
     Only vehicles remain on/over the road.

Everything else (park, marble sculpture, vegetation, cameras, world/sky,
render settings) is inherited unchanged from the all30 blend.
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


from pathlib import Path
import sys

import bpy

ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
SRC_BLEND = ROOT / "infinigen/outputs/urban_v3_all30/urban_v3_all30.blend"
A18_BLEND = ROOT / "infinigen/outputs/urban_v3_all18/urban_v3_all18.blend"
OUT = ROOT / "infinigen/outputs/urban_v3_all32"
OUT.mkdir(parents=True, exist_ok=True)

sys.path.insert(0, str(ROOT / "scripts"))

# ─────────────────────────────────────────────────────────────────────────────
# OPEN THE all30 BLEND
# ─────────────────────────────────────────────────────────────────────────────
print(f"[all32] Opening base blend: {SRC_BLEND}", flush=True)
bpy.ops.wm.open_mainfile(filepath=str(SRC_BLEND))
print(f"[all32] Opened. objects={len(bpy.data.objects)}", flush=True)

# ─── GPU ──────────────────────────────────────────────────────────────────────
bpy.context.scene.render.engine = "CYCLES"
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.compute_device_type = "OPTIX"
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    bpy.context.scene.cycles.device = "GPU"
    print("[all32] GPU: OPTIX", flush=True)
except Exception as _e:
    print(f"[all32] OPTIX: {_e}", flush=True)
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
        for d in prefs.devices:
            d.use = True
        bpy.context.scene.cycles.device = "GPU"
        print("[all32] GPU: CUDA", flush=True)
    except Exception as _e2:
        print(f"[all32] CUDA: {_e2}", flush=True)
print(f"[all32] cycles.device = {bpy.context.scene.cycles.device}", flush=True)


# ═════════════════════════════════════════════════════════════════════════════
# TASK 1 — DEEP ASPHALT (AgX-safe deep-charcoal material on the carriageway)
# ═════════════════════════════════════════════════════════════════════════════
print("[all32] TASK 1: building deep-charcoal asphalt material ...", flush=True)


def deep_asphalt_mat(name="a32_asphalt"):
    m = bpy.data.materials.get(name)
    if m:
        return m
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nodes, links = nt.nodes, nt.links
    for n in list(nodes):
        nodes.remove(n)
    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    tex = nodes.new("ShaderNodeTexCoord")

    # fine aggregate grain -> very dark base color ramp
    grain = nodes.new("ShaderNodeTexNoise")
    grain.inputs["Scale"].default_value = 28.0
    grain.inputs["Detail"].default_value = 10.0
    links.new(tex.outputs["Object"], grain.inputs["Vector"])

    # broad poured-section variation
    broad = nodes.new("ShaderNodeTexNoise")
    broad.inputs["Scale"].default_value = 0.6
    broad.inputs["Detail"].default_value = 4.0
    links.new(tex.outputs["Object"], broad.inputs["Vector"])

    ramp = nodes.new("ShaderNodeValToRGB")
    # extremely dark charcoal so it survives AgX lift as "deep asphalt"
    ramp.color_ramp.elements[0].position = 0.30
    ramp.color_ramp.elements[0].color = (0.006, 0.006, 0.007, 1.0)
    ramp.color_ramp.elements[1].position = 0.80
    ramp.color_ramp.elements[1].color = (0.020, 0.020, 0.022, 1.0)
    links.new(grain.outputs["Fac"], ramp.inputs["Fac"])

    # blend in a touch of the broad variation
    mix = nodes.new("ShaderNodeMixRGB")
    mix.blend_type = "MIX"
    mix.inputs["Fac"].default_value = 0.25
    links.new(ramp.outputs["Color"], mix.inputs["Color1"])
    dk = nodes.new("ShaderNodeValToRGB")
    dk.color_ramp.elements[0].color = (0.005, 0.005, 0.006, 1.0)
    dk.color_ramp.elements[1].color = (0.016, 0.016, 0.018, 1.0)
    links.new(broad.outputs["Fac"], dk.inputs["Fac"])
    links.new(dk.outputs["Color"], mix.inputs["Color2"])
    links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])

    # matte + near-zero specular so the bright sky can't add a grey sheen
    try:
        bsdf.inputs["Roughness"].default_value = 0.92
    except Exception:
        pass
    for spec_key in ("Specular IOR Level", "Specular"):
        if spec_key in bsdf.inputs:
            bsdf.inputs[spec_key].default_value = 0.12
            break

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.18
    bump.inputs["Distance"].default_value = 0.004
    links.new(grain.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])
    return m


road_mat = deep_asphalt_mat()
rc = bpy.data.collections.get("Road")
targets = []
if rc:
    targets = [o for o in rc.objects if o.type == "MESH"]
for o in bpy.data.objects:
    if o.type == "MESH" and (o.name.startswith("road_") or o.name == "isect"):
        if o not in targets:
            targets.append(o)
n = 0
for o in targets:
    if o.data.materials:
        o.data.materials[0] = road_mat
    else:
        o.data.materials.append(road_mat)
    n += 1
print(
    f"[all32]   assigned deep-charcoal asphalt to {n} carriageway objects", flush=True
)

# Lane markings (dash_*, cl_*, stop_*, xwk_*) and sidewalks/kerbs are inherited
# unchanged. all30 already has short white dashes (no arrows) + yellow centre
# line + zebra crossings + sidewalks, which now sit on the deep asphalt.


# ═════════════════════════════════════════════════════════════════════════════
# TASK 2 — CLEAR ROADWAY OF NON-VEHICLE PROPS (remove telephone booths)
# ═════════════════════════════════════════════════════════════════════════════
print("[all32] TASK 2: removing telephone booths (K6_*) ...", flush=True)
booth = [o for o in bpy.data.objects if o.name.startswith("K6_")]
for o in booth:
    try:
        bpy.data.objects.remove(o, do_unlink=True)
    except Exception:
        pass
print(
    f"[all32]   removed {len(booth)} phone-booth objects (incl. K6_Facade panels)",
    flush=True,
)


# ═════════════════════════════════════════════════════════════════════════════
# SAVE + RENDER
# ═════════════════════════════════════════════════════════════════════════════
out_blend = OUT / "urban_v3_all32.blend"
print(f"[all32] Saving blend -> {out_blend}", flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(out_blend))
print("[all32] Blend saved.", flush=True)

sc = bpy.context.scene
RENDERS = [
    ("cam_overview", "overview.png"),
    ("cam_residential", "residential.png"),
    ("cam_park", "park.png"),
    ("cam_commercial", "commercial.png"),
    ("cam_intersection", "intersection.png"),
]
for cam_name, fname in RENDERS:
    cam = bpy.data.objects.get(cam_name)
    if cam is None:
        print(f"[all32] MISSING camera {cam_name}, skipping {fname}", flush=True)
        continue
    sc.camera = cam
    sc.render.filepath = str(OUT / fname)
    print(f"[all32] Rendering {fname} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"[all32] Done: {fname}", flush=True)

print("[all32] ALL DONE.", flush=True)

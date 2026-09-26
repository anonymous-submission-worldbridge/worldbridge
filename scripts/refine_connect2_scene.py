"""Final physical/optical refinements discovered through actual Cycles previews."""
import bpy, sys, json, math
from pathlib import Path
from mathutils import Matrix, Vector

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

key = sys.argv[-1]
dest = B.OUT / key
bpy.ops.wm.open_mainfile(filepath=str(dest / "scene.blend"), load_ui=False)
scene = bpy.context.scene
m = json.loads((dest / "scene_manifest.json").read_text())
c = bpy.data.collections["Architecture_and_furnished_interior"]
outside = bpy.data.collections["Detailed_public_realm"]
if scene.get("connect2_final_refinement"):
    raise RuntimeError("Refinement already applied; rebuild before reapplying")
for o in c.objects:
    if o.name.startswith("connect2:modeled_floor_finish"):
        for mod in o.modifiers:
            if mod.type == "BEVEL":
                mod.width = 0.0007
                mod.segments = 2
    if key in ("restaurant", "cafe") and (
        "interior_finished_floor" in o.name or "oak_wall_lining" in o.name
    ):
        for mod in o.modifiers:
            if mod.type == "BEVEL":
                mod.width = 0.002
        if "interior_finished_floor" in o.name:
            B.assign(o, B.material("floor_seam_underlay", (0.055, 0.035, 0.02), 0.6))
# Mottled dry earth continues beyond the compact authored paving.
ground = next(
    o for o in outside.objects if o.name.startswith("connect2:compact_site_base")
)
ground.dimensions = (1800, 1800, 0.16)
mat = ground.active_material
nodes = mat.node_tree.nodes
links = mat.node_tree.links
p = nodes.get("Principled BSDF")
tc = nodes.new("ShaderNodeTexCoord")
noise = nodes.new("ShaderNodeTexNoise")
noise.inputs["Scale"].default_value = 0.85
noise.inputs["Detail"].default_value = 4
links.new(tc.outputs["Object"], noise.inputs["Vector"])
ramp = nodes.new("ShaderNodeValToRGB")
ramp.color_ramp.elements[0].color = (0.045, 0.058, 0.024, 1)
ramp.color_ramp.elements[1].color = (0.17, 0.18, 0.08, 1)
links.new(noise.outputs["Fac"], ramp.inputs[0])
links.new(ramp.outputs["Color"], p.inputs["Base Color"])
# Rear boundary foliage stays safely beyond each complete building footprint.
s = m["spec"]
cx = s["center"]
w = s["width"]
d = s["depth"]
for i in range(6):
    B.inst(
        outside,
        "full02:MASTER:TreeFactory:42",
        "rear_garden_context",
        (cx - w / 2 - 6 + i * (w + 12) / 5, d + 9 + (i % 2) * 2, 0.14),
        i * 1.31,
        0.85,
    )
if key == "cafe":
    center = Vector((-3.88, 1.335, 0))
    T = (
        Matrix.Translation(center)
        @ Matrix.Rotation(math.pi, 4, "Z")
        @ Matrix.Translation(-center)
    )
    for o in list(c.objects):
        if "espresso_service_mark" in o.name:
            o.rotation_euler = (math.pi / 2, 0, math.pi)
        if "espresso" in o.name:
            o.matrix_world = T @ o.matrix_world
            if "plumbed_water_line" in o.name:
                o.location.y = 1.18
    # Interior photograph of the working machine, rather than its casing.
    m["shots"]["detail_primary"] = {
        "position": (-1.8, 3.5, 2.15),
        "target": (-3.88, 1.34, 1.78),
        "lens": 40,
    }
if key in ("restaurant", "market"):
    source = bpy.data.collections.get("NATIVE_FruitFactoryApple")
    if source:
        ripe = B.col("FINISH_NATIVE_APPLE_SKIN")
        red = B.material("apple_skin", (0.32, 0.01, 0.008), 0.32)
        nd = red.node_tree.nodes
        lk = red.node_tree.links
        bs = nd.get("Principled BSDF")
        bs.inputs["Subsurface Weight"].default_value = 0.045
        tex = nd.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 28
        tex.inputs["Detail"].default_value = 3
        ramp = nd.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].color = (0.075, 0.002, 0.001, 1)
        ramp.color_ramp.elements[1].color = (0.40, 0.035, 0.012, 1)
        lk.new(tex.outputs["Fac"], ramp.inputs[0])
        lk.new(ramp.outputs["Color"], bs.inputs["Base Color"])
        micro = nd.new("ShaderNodeTexNoise")
        micro.inputs["Scale"].default_value = 380
        bump = nd.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.16
        bump.inputs["Distance"].default_value = 0.00025
        lk.new(micro.outputs["Fac"], bump.inputs["Height"])
        lk.new(bump.outputs["Normal"], bs.inputs["Normal"])
        for o in source.objects:
            n = B.copy(ripe, o)
            if n.type == "MESH":
                B.assign(n, red)
        for o in c.objects:
            if o.instance_collection == source:
                o.instance_collection = ripe
    if key == "market":
        # Shorten apple rows to leave the pineapples a separate supported rear row.
        for o in list(c.objects):
            if "fresh_apple" in o.name:
                yy = o.location.y - 1.2
                if yy > 0.065:
                    c.objects.unlink(o)
                else:
                    o.rotation_euler.z = (len(o.name) % 7) * 0.19
if key == "library":
    # All reading islands use the undressed table variant.
    pass
if key == "pharmacy":
    for name in [
        "inside_to_outside_middle_axial",
        "inside_to_outside_middle_oblique",
        "inside_to_outside_far_axial",
    ]:
        m["shots"][name]["position"][0] = -1.25 if name.endswith("axial") else -1.75
        m["shots"][name]["target"] = [0, -4, 1.5]
    m["shots"]["interior_wide"] = {
        "position": [12.6, 10.2, 1.78],
        "target": [7.2, 15.8, 1.65],
        "lens": 24,
    }
scene["connect2_final_refinement"] = True
m["refinements"] = [
    "camera-reviewed architectural openings",
    "continuous native geometry",
    "coordinated ceramic finishes",
    "physical wood-floor joints",
    "non-intersecting landscape context",
    "corrected equipment operation orientation",
]
(dest / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(dest / "scene.blend"), compress=True)
print("CONNECT2_REFINED", key, flush=True)

"""Render validation views for the production PublicSpaceFactory fountains.

This is intentionally only a renderer: all fountain geometry comes from
``infinigen.assets.objects.decor.urban_public_space.PublicSpaceFactory``, the
same factory called by ``generate_urban.py``.
"""

from __future__ import annotations

import json
import importlib.util
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import bpy
from mathutils import Vector

from infinigen.assets.utils.urban_primitives import UrbanAssetRequest, cube_obj

# Loading the production module by file location avoids unrelated eager decor
# imports (aquariums/fluid/terrain) in a minimal Blender validation environment.
_FACTORY_PATH = ROOT / "infinigen" / "assets" / "objects" / "decor" / "urban_public_space.py"
_FACTORY_SPEC = importlib.util.spec_from_file_location("urban_public_space_runtime", _FACTORY_PATH)
_FACTORY_MODULE = importlib.util.module_from_spec(_FACTORY_SPEC)
_FACTORY_SPEC.loader.exec_module(_FACTORY_MODULE)
FOUNTAIN_VARIANTS = _FACTORY_MODULE.FOUNTAIN_VARIANTS
PublicSpaceFactory = _FACTORY_MODULE.PublicSpaceFactory


OUTPUT = ROOT / "outputs" / "outdoor_part_demo" / "urban_v3_fountain"
REFERENCE_URLS = [
    "https://preview.free3d.com/img/2013/10/1688663323047887977/8jgtcddo.jpg",
    "https://fbi.cults3d.com/uploaders/41230908/illustration-file/6829bd1f-f868-4896-811b-99c28b134a7b/3ddd1.jpg",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQiX8DVgwRuHPMYTLEE9ivBwdhl6ykiEDszHuc6ydNn6g&s=10",
    "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQTWFGoYDAd11dVB8yBB9_scHUU8koXMW6cf5aRjaLSbg&s=10",
]


def _make_mat(name, color, roughness=0.55, metallic=0.0, noise_strength=0.0, bump_strength=0.0):
    """Small Blender-4-compatible material helper for validation rendering."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = color[3]
    if color[3] < 1:
        try:
            mat.surface_render_method = "DITHERED"
        except Exception:
            pass
        if "Transmission Weight" in bsdf.inputs:
            bsdf.inputs["Transmission Weight"].default_value = 0.14
        if "Coat Weight" in bsdf.inputs:
            bsdf.inputs["Coat Weight"].default_value = 0.25
    if noise_strength or bump_strength:
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 24
        noise.inputs["Detail"].default_value = 6
        if noise_strength:
            ramp = nodes.new("ShaderNodeValToRGB")
            low = tuple(max(0.0, c * (1.0 - noise_strength)) for c in color[:3]) + (color[3],)
            high = tuple(min(1.0, c * (1.0 + noise_strength)) for c in color[:3]) + (color[3],)
            ramp.color_ramp.elements[0].color = low
            ramp.color_ramp.elements[1].color = high
            links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
            links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
        if bump_strength:
            bump = nodes.new("ShaderNodeBump")
            bump.inputs["Strength"].default_value = bump_strength
            bump.inputs["Distance"].default_value = 0.04
            links.new(noise.outputs["Fac"], bump.inputs["Height"])
            links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def clear_scene():
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for datablocks in (bpy.data.meshes, bpy.data.curves, bpy.data.materials, bpy.data.cameras, bpy.data.lights):
        for block in list(datablocks):
            if block.users == 0:
                datablocks.remove(block)


def materials():
    return {
        "stone": _make_mat("showcase_stone", (0.54, 0.52, 0.47, 1), roughness=0.72, noise_strength=0.10, bump_strength=0.025),
        "fountain_ivory": _make_mat("showcase_ivory", (0.86, 0.83, 0.74, 1), roughness=0.63, noise_strength=0.09, bump_strength=0.024),
        "fountain_sandstone": _make_mat("showcase_sandstone", (0.62, 0.43, 0.30, 1), roughness=0.72, noise_strength=0.15, bump_strength=0.035),
        "fountain_gray": _make_mat("showcase_gray", (0.36, 0.37, 0.36, 1), roughness=0.70, noise_strength=0.13, bump_strength=0.030),
        "water": _make_mat("showcase_water", (0.045, 0.38, 0.68, 0.72), roughness=0.025),
        "grass": _make_mat("showcase_grass", (0.055, 0.25, 0.07, 1), roughness=0.92, noise_strength=0.20, bump_strength=0.025),
        "grass_tuft": _make_mat("showcase_grass_tuft", (0.025, 0.20, 0.045, 1), roughness=0.90),
        "shrub": _make_mat("showcase_shrub", (0.035, 0.22, 0.055, 1), roughness=0.90),
        "soil": _make_mat("showcase_soil", (0.105, 0.050, 0.022, 1), roughness=0.96, noise_strength=0.24, bump_strength=0.04),
        "flower_pink": _make_mat("showcase_flower_pink", (0.95, 0.11, 0.42, 1), roughness=0.42),
        "flower_purple": _make_mat("showcase_flower_purple", (0.50, 0.10, 0.68, 1), roughness=0.44),
        "flower_yellow": _make_mat("showcase_flower_yellow", (1.0, 0.72, 0.06, 1), roughness=0.40),
        "bronze": _make_mat("showcase_bronze", (0.48, 0.26, 0.09, 1), roughness=0.45, metallic=0.38),
        "paving": _make_mat("showcase_paving", (0.37, 0.34, 0.30, 1), roughness=0.84, noise_strength=0.15, bump_strength=0.035),
        "paving_light": _make_mat("showcase_paving_light", (0.60, 0.56, 0.49, 1), roughness=0.82, noise_strength=0.10, bump_strength=0.025),
    }


def setup_daylight():
    world = bpy.data.worlds.new("Fountain Daylight World")
    world.use_nodes = True
    background = world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = (0.50, 0.67, 0.90, 1)
    background.inputs["Strength"].default_value = 0.42
    bpy.context.scene.world = world

    bpy.ops.object.light_add(type="SUN", location=(-7, -10, 15))
    sun = bpy.context.active_object
    sun.name = "showcase:morning_sun"
    sun.rotation_euler = (math.radians(34), math.radians(-18), math.radians(-32))
    sun.data.energy = 3.0
    sun.data.angle = math.radians(5.0)

    bpy.ops.object.light_add(type="AREA", location=(0, -8, 10))
    fill = bpy.context.active_object
    fill.name = "showcase:sky_fill"
    fill.data.energy = 900
    fill.data.shape = "DISK"
    fill.data.size = 12
    look_at(fill, (0, 0, 1.0))


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_camera():
    bpy.ops.object.camera_add(location=(0, -30, 8))
    camera = bpy.context.active_object
    camera.name = "showcase:camera"
    camera.data.lens = 44
    camera.data.sensor_width = 36
    camera.data.dof.use_dof = False
    bpy.context.scene.camera = camera
    return camera


def setup_render():
    scene = bpy.context.scene
    try:
        scene.render.engine = "BLENDER_EEVEE_NEXT"
    except TypeError:
        scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 1100
    scene.render.resolution_y = 700
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    scene.render.image_settings.color_mode = "RGBA"
    if hasattr(scene, "eevee"):
        for attribute, value in (
            ("taa_render_samples", 48),
            ("use_gtao", True),
            ("gtao_distance", 4),
            ("gtao_factor", 1.25),
            ("use_soft_shadows", True),
            ("use_ssr", True),
            ("use_ssr_refraction", True),
        ):
            if hasattr(scene.eevee, attribute):
                setattr(scene.eevee, attribute, value)
    try:
        scene.view_settings.look = "AgX - Medium High Contrast"
    except TypeError:
        try:
            scene.view_settings.look = "Medium High Contrast"
        except TypeError:
            pass
    scene.view_settings.exposure = 0.1
    scene.render.filepath = str(OUTPUT / "overview_day.png")


def add_showcase_ground(mats):
    cube_obj("showcase:paved_terrace", (0, 0, -0.10), (27.0, 12.0, 0.20), mats["paving"], "plaza", bevel=0.10)
    for row in range(-4, 5):
        y = row * 1.20 + 0.18 * (row % 2)
        seam = cube_obj(f"showcase:paving_joint_h:{row}", (0, y, 0.008), (26.4, 0.022, 0.012), mats["paving_light"], "plaza-detail", bevel=0.0)
        seam.hide_render = False
    for col in range(-11, 12):
        x = col * 1.15
        cube_obj(f"showcase:paving_joint_v:{col}", (x, 0, 0.009), (0.020, 10.8, 0.014), mats["paving_light"], "plaza-detail", bevel=0.0)


def render_view(camera, name, location, target, lens):
    camera.location = location
    camera.data.lens = lens
    look_at(camera, target)
    bpy.context.scene.render.filepath = str(OUTPUT / f"{name}.png")
    bpy.ops.render.render(write_still=True)


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    clear_scene()
    mats = materials()
    setup_daylight()
    setup_render()
    add_showcase_ground(mats)
    factory = PublicSpaceFactory(mats)
    centers = (-9.3, -3.15, 3.05, 9.25)
    assets = []
    all_objects = []
    for index, (variant, x) in enumerate(zip(FOUNTAIN_VARIANTS, centers)):
        objects, asset = factory.create_fountain(
            UrbanAssetRequest(
                asset_type="fountain",
                location=(x, 0.0, 0.02),
                semantic="fountain",
                params={"id": index, "variant": variant},
            )
        )
        all_objects.extend(objects)
        assets.append(asset)

    camera = setup_camera()
    views = [
        ("overview_day", (0.0, -30.5, 8.0), (0.0, 0.0, 1.55), 40),
        ("overview_reverse_day", (0.0, 27.5, 7.0), (0.0, 0.0, 1.45), 41),
        ("royal_quatrefoil_close", (-12.8, -7.0, 4.0), (centers[0], 0.0, 1.62), 54),
        ("planted_three_tier_close", (-6.2, -7.0, 3.9), (centers[1], 0.0, 1.72), 56),
        ("compact_four_tier_close", (0.0, -6.8, 3.7), (centers[2], 0.0, 1.65), 58),
        ("radial_garden_close", (6.0, -7.4, 4.2), (centers[3], 0.0, 1.25), 52),
        ("garden_high_angle", (10.8, -8.5, 8.2), (centers[3], 0.0, 0.75), 53),
    ]
    for view in views:
        render_view(camera, *view)

    scene_path = OUTPUT / "urban_v3_fountain.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(scene_path))

    mesh_vertices = sum(len(obj.data.vertices) for obj in all_objects if obj.type == "MESH")
    mesh_polygons = sum(len(obj.data.polygons) for obj in all_objects if obj.type == "MESH")
    audit = {
        "generator": "infinigen.assets.objects.decor.urban_public_space.PublicSpaceFactory.create_fountain",
        "pipeline_integration": "infinigen_examples.generate_urban._outdoor_assets",
        "procedural_only": True,
        "arrangement": "single row, four distinct variants",
        "lighting": "daylight sun plus sky fill",
        "variants": assets,
        "fountain_object_count": len(all_objects),
        "water_object_count": sum("water" in obj.name or "stream" in obj.name or "spray" in obj.name or "droplet" in obj.name for obj in all_objects),
        "mesh_vertices": mesh_vertices,
        "mesh_polygons": mesh_polygons,
        "render_views": [f"{view[0]}.png" for view in views],
        "blend_file": scene_path.name,
        "reference_images": REFERENCE_URLS,
    }
    with (OUTPUT / "fountain_audit.json").open("w", encoding="utf-8") as handle:
        json.dump(audit, handle, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()

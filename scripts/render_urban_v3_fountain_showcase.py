#!/usr/bin/env python3
"""QA renderer for the production urban fountain factory.

This file contains no fountain geometry.  It instantiates
``PublicSpaceFactory.create_fountain`` exactly as the urban generation pipeline
does, then saves a daylight multi-view validation scene and an audit report.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INFINIGEN_ROOT = REPO_ROOT / "infinigen"
if str(INFINIGEN_ROOT) not in sys.path:
    sys.path.insert(0, str(INFINIGEN_ROOT))
os.environ["INFINIGEN_SKIP_TAGGING"] = "1"

import bpy  # noqa: E402
from mathutils import Vector  # noqa: E402

from infinigen.assets.objects.decor.urban_public_space import (  # noqa: E402
    FOUNTAIN_REFERENCES,
    FOUNTAIN_VARIANTS,
    PublicSpaceFactory,
    make_fountain_materials,
)
from infinigen.assets.utils.urban_primitives import (  # noqa: E402
    UrbanAssetRequest,
    cube_obj,
)

print("FOUNTAIN_QA: production factory imports ready", flush=True)


DEFAULT_OUTPUT = (
    REPO_ROOT / "infinigen" / "outputs" / "outdoor_part_demo" / "urban_v3_fountain3"
)


def _make_mat(
    name,
    color,
    roughness=0.55,
    metallic=0.0,
    emission_strength=0.0,
    noise_strength=0.0,
    bump_strength=0.0,
    noise_scale=22.0,
    bump_scale=48.0,
    transmission=0.0,
    ior=1.45,
    coat_weight=0.0,
):
    """Small QA-side material constructor matching the production parameters."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")

    def set_input(names, value):
        for input_name in names:
            if input_name in bsdf.inputs:
                bsdf.inputs[input_name].default_value = value
                return

    bsdf.inputs["Base Color"].default_value = color
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    set_input(("Transmission Weight", "Transmission"), transmission)
    set_input(("IOR",), ior)
    set_input(("Coat Weight", "Clearcoat"), coat_weight)
    if len(color) > 3 and color[3] < 1.0 and "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = color[3]
        try:
            if hasattr(mat, "surface_render_method"):
                mat.surface_render_method = "DITHERED"
            elif hasattr(mat, "blend_method"):
                mat.blend_method = "BLEND"
        except (TypeError, ValueError):
            pass
    if emission_strength > 0:
        set_input(("Emission Color", "Emission"), color)
        set_input(("Emission Strength",), emission_strength)
    if noise_strength > 0:
        noise = nodes.new(type="ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = noise_scale
        noise.inputs["Detail"].default_value = 8
        noise.inputs["Roughness"].default_value = 0.58
        ramp = nodes.new(type="ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.2
        ramp.color_ramp.elements[0].color = tuple(
            max(0.0, channel * (1.0 - noise_strength)) for channel in color[:3]
        ) + (color[3],)
        ramp.color_ramp.elements[1].color = tuple(
            min(1.0, channel * (1.0 + noise_strength)) for channel in color[:3]
        ) + (color[3],)
        links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
        links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    if bump_strength > 0 and "Normal" in bsdf.inputs:
        bump_noise = nodes.new(type="ShaderNodeTexNoise")
        bump_noise.inputs["Scale"].default_value = bump_scale
        bump_noise.inputs["Detail"].default_value = 10
        bump = nodes.new(type="ShaderNodeBump")
        bump.inputs["Strength"].default_value = bump_strength
        bump.inputs["Distance"].default_value = 0.045
        links.new(bump_noise.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def parse_args():
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--resolution-x", type=int, default=1440)
    parser.add_argument("--resolution-y", type=int, default=810)
    parser.add_argument("--samples", type=int, default=96)
    parser.add_argument(
        "--engine",
        choices=("cycles", "eevee"),
        default="cycles",
        help="Cycles is the photoreal final; Eevee remains available for quick QA.",
    )
    parser.add_argument("--skip-render", action="store_true")
    parser.add_argument(
        "--views",
        default=None,
        help="Optional comma-separated output filenames for a partial QA render.",
    )
    return parser.parse_args(argv)


def clear_scene():
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for datablocks in (
        bpy.data.curves,
        bpy.data.meshes,
        bpy.data.materials,
        bpy.data.cameras,
        bpy.data.lights,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def look_at(obj, target):
    direction = Vector(target) - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def make_materials():
    mats = {
        "stone": _make_mat(
            "fountain_qa_neutral_stone",
            (0.46, 0.44, 0.39, 1),
            roughness=0.78,
            noise_strength=0.18,
            bump_strength=0.07,
            noise_scale=29,
            bump_scale=70,
        ),
        "grass": _make_mat(
            "fountain_qa_lawn",
            (0.055, 0.22, 0.065, 1),
            roughness=0.91,
            noise_strength=0.26,
            bump_strength=0.055,
            noise_scale=35,
            bump_scale=78,
        ),
        "grass_tuft": _make_mat(
            "fountain_qa_grass_blade",
            (0.025, 0.15, 0.04, 1),
            roughness=0.88,
            noise_strength=0.18,
            bump_strength=0.02,
            noise_scale=31,
        ),
        "shrub": _make_mat(
            "fountain_qa_shrub",
            (0.035, 0.20, 0.055, 1),
            roughness=0.87,
            noise_strength=0.18,
            bump_strength=0.02,
            noise_scale=28,
        ),
        "soil": _make_mat(
            "fountain_qa_soil",
            (0.075, 0.037, 0.016, 1),
            roughness=0.96,
            noise_strength=0.34,
            bump_strength=0.11,
            noise_scale=42,
            bump_scale=92,
        ),
        "flower_yellow": _make_mat(
            "fountain_qa_flower_yellow",
            (0.92, 0.58, 0.035, 1),
            roughness=0.47,
            noise_strength=0.06,
        ),
        "flower_purple": _make_mat(
            "fountain_qa_flower_purple",
            (0.36, 0.055, 0.56, 1),
            roughness=0.49,
            noise_strength=0.08,
        ),
    }
    mats.update(make_fountain_materials(_make_mat))
    return mats


def configure_world_and_lighting():
    is_cycles = bpy.context.scene.render.engine == "CYCLES"
    world = bpy.data.worlds.new("fountain_qa_daylight_world")
    bpy.context.scene.world = world
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    sky.sky_type = "NISHITA"
    sky.sun_elevation = math.radians(42)
    sky.sun_rotation = math.radians(125)
    sky.altitude = 0.08
    sky.air_density = 0.85
    sky.dust_density = 0.55
    background.inputs["Strength"].default_value = 0.27 if is_cycles else 0.36
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])

    bpy.ops.object.light_add(type="SUN", location=(-9, -12, 18))
    sun = bpy.context.active_object
    sun.name = "fountain_qa_sun"
    sun.data.energy = 1.75 if is_cycles else 3.15
    sun.data.angle = math.radians(2.2)
    sun.rotation_euler = (math.radians(39), math.radians(-18), math.radians(-124))

    bpy.ops.object.light_add(type="AREA", location=(-4, -11, 11))
    key = bpy.context.active_object
    key.name = "fountain_qa_sky_key"
    key.data.energy = 160 if is_cycles else 350
    key.data.shape = "DISK"
    key.data.size = 9.0
    look_at(key, (0, 0, 1.1))

    bpy.ops.object.light_add(type="AREA", location=(12, 8, 7))
    fill = bpy.context.active_object
    fill.name = "fountain_qa_bounce_fill"
    fill.data.energy = 55 if is_cycles else 115
    fill.data.size = 11.0
    look_at(fill, (0, 0, 1.0))


def configure_render(args):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES" if args.engine == "cycles" else "BLENDER_EEVEE_NEXT"
    scene.render.resolution_x = args.resolution_x
    scene.render.resolution_y = args.resolution_y
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "8"
    scene.render.film_transparent = False
    scene.render.use_file_extension = True
    if args.engine == "cycles":
        scene.cycles.samples = args.samples
        scene.cycles.use_denoising = True
        scene.cycles.use_adaptive_sampling = True
        scene.cycles.adaptive_threshold = 0.035
        scene.cycles.max_bounces = 7
        scene.cycles.transmission_bounces = 5
        scene.cycles.transparent_max_bounces = 6
        scene.cycles.use_fast_gi = True
    elif hasattr(scene, "eevee") and hasattr(scene.eevee, "taa_render_samples"):
        scene.eevee.taa_render_samples = args.samples
    try:
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
    except (TypeError, ValueError):
        scene.view_settings.look = "Medium High Contrast"
    scene.view_settings.exposure = -0.95 if args.engine == "cycles" else -0.42
    scene.view_settings.gamma = 1.0


def add_plaza():
    plaza = _make_mat(
        "fountain_qa_plaza_travertine",
        (0.205, 0.195, 0.175, 1),
        roughness=0.80,
        noise_strength=0.24,
        bump_strength=0.075,
        noise_scale=18,
        bump_scale=58,
    )
    cube_obj(
        "fountain_qa:continuous_stone_plaza",
        (0, 2, -0.10),
        (58, 44, 0.20),
        plaza,
        "plaza",
        bevel=0.0,
    )


def add_camera():
    bpy.ops.object.camera_add(location=(0, -24, 6))
    camera = bpy.context.active_object
    camera.name = "fountain_qa_camera"
    camera.data.sensor_width = 36
    camera.data.lens = 40
    camera.data.dof.use_dof = True
    camera.data.dof.aperture_fstop = 7.1
    camera.data.dof.aperture_blades = 9
    bpy.ops.object.empty_add(type="PLAIN_AXES", location=(0, 0, 1.2))
    focus = bpy.context.active_object
    focus.name = "fountain_qa_focus"
    camera.data.dof.focus_object = focus
    bpy.context.scene.camera = camera
    return camera, focus


def world_bounds(objects):
    points = []
    for obj in objects:
        if not hasattr(obj, "bound_box"):
            continue
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))
    if not points:
        return None
    minimum = [min(point[i] for point in points) for i in range(3)]
    maximum = [max(point[i] for point in points) for i in range(3)]
    return {
        "min": minimum,
        "max": maximum,
        "dimensions": [maximum[i] - minimum[i] for i in range(3)],
    }


def render_view(scene, camera, focus, output_dir, spec, variant_objects):
    camera.location = spec["camera"]
    camera.data.lens = spec["lens"]
    camera.data.dof.aperture_fstop = spec.get("fstop", 7.1)
    focus.location = spec["target"]
    look_at(camera, spec["target"])
    bpy.context.view_layer.update()
    scene.render.filepath = str(output_dir / spec["name"])
    hidden = []
    isolate = spec.get("isolate")
    if isolate:
        for variant, objects in variant_objects.items():
            if variant == isolate:
                continue
            for obj in objects:
                if not obj.hide_render:
                    obj.hide_render = True
                    hidden.append(obj)
    try:
        bpy.ops.render.render(write_still=True)
    finally:
        for obj in hidden:
            obj.hide_render = False


def collect_audit(variant_records, render_names, blend_path):
    mesh_objects = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    curve_objects = [obj for obj in bpy.context.scene.objects if obj.type == "CURVE"]
    fountain_objects = [
        obj
        for obj in bpy.context.scene.objects
        if obj.name.startswith("urban:fountain:")
    ]
    water_objects = [
        obj
        for obj in fountain_objects
        if any(
            token in obj.name
            for token in (
                "water",
                "stream",
                "spray",
                "splash",
                "droplet",
                "ripple",
                "plume",
                "dome",
                "spill",
            )
        )
    ]
    return {
        "generator": "infinigen.assets.objects.decor.urban_public_space.PublicSpaceFactory.create_fountain",
        "production_entrypoint": "infinigen_examples.generate_urban._outdoor_assets",
        "validation_renderer": "scripts/render_urban_v3_fountain_showcase.py",
        "generator_revision": "fountain3_closed_flowing_sheets_dense_leaf_lawn_and_moulded_details",
        "procedural_only": True,
        "arrangement": "single row, four independently modeled reference variants",
        "lighting": "physical daylight sky, sun, large-area sky fill and bounce fill",
        "render_engine": bpy.context.scene.render.engine,
        "variants": variant_records,
        "reference_images": FOUNTAIN_REFERENCES,
        "fountain_object_count": len(fountain_objects),
        "water_object_count": len(water_objects),
        "mesh_object_count": len(mesh_objects),
        "curve_object_count": len(curve_objects),
        "mesh_vertices": sum(len(obj.data.vertices) for obj in mesh_objects),
        "mesh_polygons": sum(len(obj.data.polygons) for obj in mesh_objects),
        "curve_splines": sum(len(obj.data.splines) for obj in curve_objects),
        "material_count": len(bpy.data.materials),
        "royal_procedural_lawn_blade_count": 7000,
        "water_representation": "closed refractive liquid ribbons with continuous width variation, breakup fragments, droplets, foam, ripples and curved impact filaments",
        "detail_feature_object_counts": {
            "carved_relief": sum(
                "rose" in obj.name or "acanthus" in obj.name for obj in fountain_objects
            ),
            "fluting_and_ribs": sum(
                "rib" in obj.name or "pedestal" in obj.name for obj in fountain_objects
            ),
            "jointed_pavers_or_tiles": sum(
                "paver" in obj.name or "tile" in obj.name or "radial_walk" in obj.name
                for obj in fountain_objects
            ),
            "weathered_wet_stone": sum(
                "wet" in obj.name or "streak" in obj.name for obj in fountain_objects
            ),
            "water_droplet_and_splash_systems": sum(
                "droplet" in obj.name or "splash" in obj.name
                for obj in fountain_objects
            ),
            "torn_water_sheets_and_tapered_jets": sum(
                "laminar" in obj.name
                or "pressure_jet" in obj.name
                or "jet_fragments" in obj.name
                for obj in fountain_objects
            ),
            "natural_lawn_leaf_systems": sum(
                "tapered_blade" in obj.name
                or "thatch" in obj.name
                or "broadleaf" in obj.name
                for obj in fountain_objects
            ),
            "rounded_moulded_or_dressed_stone": sum(
                "rounded_moulded" in obj.name or "dressed_wedge" in obj.name
                for obj in fountain_objects
            ),
        },
        "render_views": render_names,
        "blend_file": blend_path.name,
    }


def main():
    args = parse_args()
    output_dir = args.output.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"FOUNTAIN_QA: building scene in {output_dir}", flush=True)

    clear_scene()
    configure_render(args)
    configure_world_and_lighting()
    add_plaza()
    mats = make_materials()
    factory = PublicSpaceFactory(mats)

    centers = (-10.8, -3.6, 3.6, 10.8)
    variant_records = []
    variant_objects = {}
    for index, (variant, center_x) in enumerate(zip(FOUNTAIN_VARIANTS, centers)):
        print(f"FOUNTAIN_QA: building {variant}", flush=True)
        request = UrbanAssetRequest(
            asset_type="fountain",
            location=(center_x, 0.0, 0.02),
            semantic="fountain",
            params={"id": index, "variant": variant},
        )
        objects, metadata = factory.create_fountain(request)
        bpy.context.view_layer.update()
        metadata["bounds"] = world_bounds(objects)
        metadata["mesh_vertices"] = sum(
            len(obj.data.vertices) for obj in objects if obj.type == "MESH"
        )
        metadata["mesh_polygons"] = sum(
            len(obj.data.polygons) for obj in objects if obj.type == "MESH"
        )
        metadata["curve_splines"] = sum(
            len(obj.data.splines) for obj in objects if obj.type == "CURVE"
        )
        variant_records.append(metadata)
        variant_objects[variant] = objects
        print(
            f"FOUNTAIN_QA: built {variant}: {len(objects)} objects, "
            f"{metadata['mesh_polygons']} polygons, {metadata['curve_splines']} curve splines",
            flush=True,
        )

    camera, focus = add_camera()
    view_specs = [
        {
            "name": "overview_day.png",
            "camera": (0.0, -24.5, 4.9),
            "target": (0.0, 0.0, 1.48),
            "lens": 30,
            "fstop": 10.0,
        },
        {
            "name": "overview_reverse_day.png",
            "camera": (0.0, 24.0, 5.4),
            "target": (0.0, 0.0, 1.42),
            "lens": 30,
            "fstop": 10.0,
        },
        {
            "name": "overview_oblique_day.png",
            "camera": (-21.0, -25.0, 7.0),
            "target": (0.0, 0.0, 1.34),
            "lens": 32,
            "fstop": 10.0,
        },
        {
            "name": "royal_quatrefoil_complete_day.png",
            "camera": (-10.8, -15.0, 3.25),
            "target": (-10.8, 0.0, 1.86),
            "lens": 55,
            "fstop": 8.4,
            "isolate": "royal_quatrefoil",
        },
        {
            "name": "planted_three_tier_complete_day.png",
            "camera": (-3.6, -14.7, 3.30),
            "target": (-3.6, 0.0, 1.82),
            "lens": 55,
            "fstop": 8.4,
            "isolate": "planted_three_tier",
        },
        {
            "name": "compact_four_tier_complete_day.png",
            "camera": (3.6, -13.2, 3.10),
            "target": (3.6, 0.0, 1.67),
            "lens": 56,
            "fstop": 8.4,
            "isolate": "compact_four_tier",
        },
        {
            "name": "radial_garden_complete_day.png",
            "camera": (10.8, -14.3, 4.60),
            "target": (10.8, 0.0, 1.22),
            "lens": 52,
            "fstop": 8.8,
            "isolate": "radial_garden",
        },
        {
            "name": "royal_water_and_lawn_detail.png",
            "camera": (-10.8, -7.1, 1.62),
            "target": (-10.8, -2.05, 0.72),
            "lens": 76,
            "fstop": 8.5,
            "isolate": "royal_quatrefoil",
        },
        {
            "name": "royal_natural_lawn_macro.png",
            "camera": (-10.8, -6.0, 0.62),
            "target": (-10.8, -2.55, 0.18),
            "lens": 72,
            "fstop": 10.0,
            "isolate": "royal_quatrefoil",
        },
        {
            "name": "planted_cascade_water_detail.png",
            "camera": (-3.6, -6.2, 2.52),
            "target": (-3.6, -0.45, 1.92),
            "lens": 74,
            "fstop": 8.5,
            "isolate": "planted_three_tier",
        },
        {
            "name": "compact_cascade_water_detail.png",
            "camera": (3.6, -5.9, 2.35),
            "target": (3.6, -0.35, 1.72),
            "lens": 76,
            "fstop": 8.5,
            "isolate": "compact_four_tier",
        },
        {
            "name": "radial_water_garden_detail.png",
            "camera": (10.8, -8.0, 5.65),
            "target": (10.8, 0.0, 0.92),
            "lens": 63,
            "fstop": 9.0,
            "isolate": "radial_garden",
        },
    ]

    selected_names = set(args.views.split(",")) if args.views else None
    selected_specs = [
        spec
        for spec in view_specs
        if selected_names is None or spec["name"] in selected_names
    ]
    if not args.skip_render:
        for spec in selected_specs:
            print(f"FOUNTAIN_QA: rendering {spec['name']}", flush=True)
            render_view(
                bpy.context.scene, camera, focus, output_dir, spec, variant_objects
            )

    blend_path = output_dir / "urban_v3_fountain.blend"
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    audit = collect_audit(
        variant_records, [spec["name"] for spec in selected_specs], blend_path
    )
    (output_dir / "fountain_audit.json").write_text(
        json.dumps(audit, indent=2), encoding="utf-8"
    )
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()

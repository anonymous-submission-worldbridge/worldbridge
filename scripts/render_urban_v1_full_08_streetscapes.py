#!/usr/bin/env python3
"""Render additional publication streetscapes from the existing FULL08 scene.

This companion to render_urban_v1_full_08_paper_views.py focuses on broad,
legible views of the road network and its surrounding districts. It opens the
authored Blend read-only, creates a temporary camera and daylight rig in
memory, and never saves changes back to the source file.

Environment variables are the same as the base paper renderer:
    C2W_PAPER_MODE         preview or final
    C2W_PAPER_ENGINE       WORKBENCH, EEVEE, or CYCLES
    C2W_PAPER_DEVICE       GPU or CPU for Cycles
    C2W_PAPER_RESOLUTION   WIDTHxHEIGHT
    C2W_PAPER_SHOTS        comma-separated shot names
    C2W_PAPER_OUT          output directory
    C2W_PAPER_SAMPLES      sample budget
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))

import render_urban_v1_full_08_paper_views as base


def configure_daylight(scene: bpy.types.Scene) -> dict:
    """Create the paper renderer's daylight rig with Blender 5 support."""
    disabled_suns = []
    for obj in scene.objects:
        if obj.type == "LIGHT" and obj.data.type == "SUN" and not obj.hide_render:
            obj.hide_render = True
            disabled_suns.append(obj.name)

    world = bpy.data.worlds.new(base.TEMP_PREFIX + "world")
    world.use_nodes = True
    nodes = world.node_tree.nodes
    links = world.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputWorld")
    background = nodes.new("ShaderNodeBackground")
    sky = nodes.new("ShaderNodeTexSky")
    try:
        sky.sky_type = "NISHITA"
        sky_model = "Nishita"
    except TypeError:
        sky.sky_type = "MULTIPLE_SCATTERING"
        sky_model = "Multiple-scattering atmosphere"
    for attribute, value in (
        ("sun_disc", False),
        ("sun_elevation", math.radians(34.0)),
        ("sun_rotation", math.radians(132.0)),
        ("altitude", 0.15),
        ("air_density", 1.0),
        ("dust_density", 1.25),
        ("ozone_density", 1.0),
    ):
        if hasattr(sky, attribute):
            setattr(sky, attribute, value)
    background.inputs["Strength"].default_value = 0.32
    links.new(sky.outputs["Color"], background.inputs["Color"])
    links.new(background.outputs["Background"], output.inputs["Surface"])
    scene.world = world

    sun_data = bpy.data.lights.new(base.TEMP_PREFIX + "sun_data", type="SUN")
    sun_data.energy = 2.35
    sun_data.angle = math.radians(4.0)
    sun_data.color = (1.0, 0.78, 0.61)
    sun = bpy.data.objects.new(base.TEMP_PREFIX + "sun", sun_data)
    scene.collection.objects.link(sun)
    sun.rotation_euler = (
        math.radians(31.0),
        math.radians(-22.0),
        math.radians(-38.0),
    )

    # Blender 5's multiple-scattering sky returns black below the mathematical
    # horizon. A broad plane just under the authored grade supplies neutral
    # context beyond the modeled blocks without changing streets or buildings.
    mesh = bpy.data.meshes.new(base.TEMP_PREFIX + "backdrop_mesh")
    span = 4000.0
    mesh.from_pydata(
        [
            (-span, -span, -0.18),
            (span, -span, -0.18),
            (span, span, -0.18),
            (-span, span, -0.18),
        ],
        [],
        [(0, 1, 2, 3)],
    )
    mesh.update()
    backdrop = bpy.data.objects.new(base.TEMP_PREFIX + "backdrop", mesh)
    scene.collection.objects.link(backdrop)
    material = bpy.data.materials.new(base.TEMP_PREFIX + "backdrop_material")
    material.diffuse_color = (0.22, 0.16, 0.13, 1.0)
    material.roughness = 1.0
    mesh.materials.append(material)

    return {
        "world": f"{sky_model} clear daylight",
        "sun_energy": sun_data.energy,
        "sun_angle_degrees": 4.0,
        "disabled_existing_suns": disabled_suns,
        "neutral_backdrop": {
            "size_m": span * 2.0,
            "elevation_m": -0.18,
            "diffuse_color_linear": list(material.diffuse_color),
        },
    }


base.configure_daylight = configure_daylight


# The candidate bank is deliberately wider than the final delivery. Preview
# mode makes it inexpensive to compare nearby positions before the selected
# views are rendered in Cycles.
base.SHOTS = (
    base.Shot(
        "01_south_boulevard_center",
        (0.0, -55.0, 4.4),
        (0.0, 18.0, 3.0),
        44,
        "Eye-level northbound view showing the full boulevard, central crossroads, and layered district frontage.",
    ),
    base.Shot(
        "02_south_boulevard_offset",
        (-8.5, -48.0, 5.2),
        (5.0, 18.0, 3.2),
        46,
        "Offset northbound boulevard view with commercial frontage, traffic, and the crossroads in depth.",
    ),
    base.Shot(
        "03_north_approach_center",
        (0.0, 54.0, 4.5),
        (0.0, -18.0, 3.0),
        44,
        "Eye-level southbound view connecting the residential approach to the main crossroads.",
    ),
    base.Shot(
        "04_north_approach_offset",
        (8.0, 47.0, 5.2),
        (-5.0, -16.0, 3.0),
        46,
        "Offset southbound view with the park edge and residential frontage framing the road.",
    ),
    base.Shot(
        "05_west_crossroad_axis",
        (-54.0, 0.0, 4.4),
        (17.0, 0.0, 3.0),
        44,
        "Eastbound axial streetscape through the complete crossroads toward the park and leisure edge.",
    ),
    base.Shot(
        "06_west_crossroad_offset",
        (-47.0, -8.0, 5.2),
        (17.0, 5.0, 3.1),
        46,
        "Offset eastbound street view combining storefronts, moving traffic, crossings, and park trees.",
    ),
    base.Shot(
        "07_east_crossroad_axis",
        (54.0, 0.0, 4.4),
        (-17.0, 0.0, 3.0),
        44,
        "Westbound axial streetscape through the crossroads toward the commercial district.",
    ),
    base.Shot(
        "08_east_crossroad_offset",
        (47.0, 8.0, 5.2),
        (-17.0, -5.0, 3.1),
        46,
        "Offset westbound road view with the park foreground and commercial frontage beyond.",
    ),
    base.Shot(
        "09_southwest_intersection_oblique",
        (-48.0, -48.0, 26.0),
        (2.0, 3.0, 2.6),
        56,
        "Elevated diagonal showing the crossroads as a complete urban scene with commercial and civic edges.",
    ),
    base.Shot(
        "10_southeast_intersection_oblique",
        (46.0, -48.0, 24.0),
        (-2.0, 3.0, 2.6),
        56,
        "Elevated reverse diagonal across the leisure district and crossroads toward the built frontage.",
    ),
    base.Shot(
        "11_northeast_intersection_oblique",
        (46.0, 46.0, 24.0),
        (-2.0, -3.0, 2.6),
        56,
        "Elevated park-side diagonal that layers trees, crossings, traffic, and commercial buildings.",
    ),
    base.Shot(
        "12_northwest_intersection_oblique",
        (-46.0, 46.0, 24.0),
        (2.0, -3.0, 2.6),
        56,
        "Elevated residential-side diagonal across the complete intersection and public realm.",
    ),
    base.Shot(
        "13_park_edge_street",
        (49.0, 24.0, 4.0),
        (-18.0, 18.0, 2.8),
        48,
        "Low street panorama from the park edge toward the crossroads and opposite district frontage.",
    ),
    base.Shot(
        "14_commercial_edge_street",
        (-49.0, -20.0, 4.2),
        (18.0, -8.0, 2.8),
        48,
        "Low commercial-edge panorama with storefronts, road activity, crossings, and leisure buildings.",
    ),
    base.Shot(
        "15_north_community_axis",
        (0.0, 62.0, 4.2),
        (0.0, 121.0, 5.0),
        45,
        "Northbound community street framed by detached houses, trees, and apartment buildings.",
    ),
    base.Shot(
        "16_north_community_reverse",
        (0.0, 128.0, 5.2),
        (0.0, 69.0, 3.2),
        46,
        "Southbound reverse view connecting the apartment cluster, houses, and distant urban core.",
    ),
    base.Shot(
        "17_northwest_community_oblique",
        (-50.0, 69.0, 9.0),
        (2.0, 104.0, 4.5),
        48,
        "Elevated diagonal across the connected northern community street and its full residential frontage.",
    ),
    base.Shot(
        "18_northeast_community_oblique",
        (50.0, 69.0, 9.0),
        (-2.0, 104.0, 4.5),
        48,
        "Reverse elevated diagonal across houses, paths, trees, and apartment buildings.",
    ),
    base.Shot(
        "19_north_link_wide",
        (34.0, 48.0, 8.0),
        (-8.0, 82.0, 3.4),
        46,
        "Wide view of the crosswalk and street connection between the core city and northern community.",
    ),
    base.Shot(
        "20_core_to_north_long_view",
        (-6.0, 12.0, 5.5),
        (3.0, 92.0, 4.0),
        48,
        "Long view from the urban core toward the northern homes, emphasizing continuous street depth.",
    ),
)


if __name__ == "__main__":
    base.main()

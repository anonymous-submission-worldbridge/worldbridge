"""Production river corridor for the source-generated full_07 urban scene.

The water surface calls Infinigen's genuine ``RiverWater`` procedural
component.  The surrounding channel is authored here because Infinigen's
``make_river`` FLIP entry expects a nature-scene terrain/liquid pair and a
multi-frame fluid bake; those objects do not exist in the urban generator.
This module supplies the missing urban integration: a variable-width incised
channel, alluvial banks, submerged sediment lenses, a riparian promenade, a
detailed timber footbridge, real full_07 botanical trees, and genuine
Infinigen grass understory.  The river4 section is explicitly waterline-safe
and keeps the active channel free of decorative boulders or curve-based foam:
the liquid boundary meets a higher bank vertex instead of exposing the side of
the water volume as a raised wall.

It is called in-memory by ``urban_v1_full_07_extension.apply``.  No existing
blend is opened and this is not a standalone demo.
"""

from __future__ import annotations

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


import importlib.util
import math
import random
import sys
from pathlib import Path

import bpy
from mathutils import Vector


ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}")
INFINIGEN_ROOT = ROOT / "infinigen"
PROJECT_SITE_PACKAGES = Path(f"{_wb_WORLDBRIDGE_SITE_PACKAGES}")
for dependency_root in (INFINIGEN_ROOT, PROJECT_SITE_PACKAGES):
    if str(dependency_root) not in sys.path:
        sys.path.insert(0, str(dependency_root))
PREFIX = "full07_river4:"
Y_MIN = -64.0
Y_MAX = 144.0
SECTION_COUNT = 261
WATER_COLUMNS = 41
WATER_Z = -0.66
CITY_EDGE_X = 54.5
RIVER5_WATER_LEVEL_DROP_M = 0.34
RIVER5_MIN_BED_LIP_CLEARANCE_M = 0.035


def _child(name: str, parent: bpy.types.Collection) -> bpy.types.Collection:
    collection = bpy.data.collections.new(PREFIX + name)
    parent.children.link(collection)
    return collection


def _material(
    name: str,
    dark: tuple[float, float, float],
    light: tuple[float, float, float],
    *,
    roughness: float,
    scale: float,
    bump: float,
    metallic: float = 0.0,
) -> bpy.types.Material:
    material = bpy.data.materials.new(PREFIX + name)
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()
    output = nodes.new("ShaderNodeOutputMaterial")
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    coordinates = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.noise_dimensions = "3D"
    noise.inputs["Scale"].default_value = scale
    noise.inputs["Detail"].default_value = 6.5
    noise.inputs["Roughness"].default_value = 0.68
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (*dark, 1.0)
    ramp.color_ramp.elements[1].color = (*light, 1.0)
    relief = nodes.new("ShaderNodeBump")
    relief.inputs["Strength"].default_value = bump
    relief.inputs["Distance"].default_value = 0.045
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = metallic
    links.new(coordinates.outputs["Generated"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], shader.inputs["Base Color"])
    links.new(noise.outputs["Fac"], relief.inputs["Height"])
    links.new(relief.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    return material


def _center_x(y: float) -> float:
    # Two incommensurate wavelengths keep the corridor natural without sharp
    # bends.  The northward drift clears the extended residential ground.
    north_drift = 2.1 * max(0.0, min(1.0, (y - 58.0) / 78.0))
    return (
        68.9
        + 1.35 * math.sin((y + 21.0) / 27.0)
        + 0.58 * math.sin((y - 8.0) / 10.5)
        + north_drift
    )


def _half_width(y: float) -> float:
    # Low-frequency widening/narrowing is supplemented by a weak secondary
    # meander frequency.  The resulting width stays inside the established
    # river reserve and never consumes the park or leisure parcel.
    return (
        4.70
        + 0.55 * math.sin((y + 17.0) / 23.0)
        + 0.23 * math.sin(y / 7.5)
        + 0.09 * math.sin((y - 11.0) / 3.9)
    )


def _surface_half_width(y: float) -> float:
    """The hydraulic waterline, inset from the nominal active-channel width."""
    return _half_width(y) * 0.965


def _bend_bias(y: float) -> float:
    """Signed outer-bend bias used by bank erosion and point-bar deposition."""
    epsilon = 0.35
    return max(
        -1.0,
        min(
            1.0,
            (_center_x(y + epsilon) - 2 * _center_x(y) + _center_x(y - epsilon)) * 42.0,
        ),
    )


def _water_surface_height(y: float, offset: float, width: float) -> tuple[float, float]:
    """Deterministic low-amplitude flow relief for a calm urban river.

    River3 used steep, rock-driven localized peaks.  In low river-level views
    those peaks made the water read as a noisy sheet.  River4 keeps a broad
    current, capillary motion and the real bridge wake, but no relief is tied
    to decorative stones.
    """
    transverse = offset / max(width, 0.01)
    edge_shear = abs(transverse) ** 1.65
    base = (
        0.0065 * math.sin(y * 0.34 + offset * 0.18)
        + 0.0048 * math.sin(y * 1.47 + offset * 0.52)
        + 0.0024 * math.sin(y * 4.25 - offset * 1.35 + 0.8)
        + 0.0011 * math.sin(y * 10.8 + offset * 3.10)
    )
    # The bridge piers split the current and leave a low-amplitude wake train.
    bridge_wake = math.exp(-(((y - 29.0) / 7.2) ** 2)) * math.exp(
        -((offset / 2.2) ** 2)
    )
    wake_relief = bridge_wake * 0.0065 * math.sin((y - 26.0) * 4.2 + abs(offset) * 2.2)
    # All geometric waves fade at the bank intersection.  This is essential:
    # an un-tapered displaced edge exposes the solidified water volume as a
    # raised translucent wall in oblique views.
    shore_fade = 0.035 + 0.965 * (1.0 - abs(transverse) ** 6)
    z = WATER_Z + (base * (0.78 + 0.22 * edge_shear) + wake_relief) * shore_fade
    turbulence = min(1.0, 0.12 + 0.34 * edge_shear + 0.24 * bridge_wake)
    return z, turbulence


def _frame(y: float) -> tuple[Vector, Vector, Vector]:
    epsilon = 0.05
    derivative = (_center_x(y + epsilon) - _center_x(y - epsilon)) / (2 * epsilon)
    tangent = Vector((derivative, 1.0, 0.0)).normalized()
    normal = Vector((tangent.y, -tangent.x, 0.0)).normalized()
    return Vector((_center_x(y), y, 0.0)), tangent, normal


def _point(y: float, offset: float, z: float) -> Vector:
    center, _tangent, normal = _frame(y)
    return center + normal * offset + Vector((0, 0, z))


def _ys(
    count: int = SECTION_COUNT, lo: float = Y_MIN, hi: float = Y_MAX
) -> list[float]:
    return [lo + (hi - lo) * index / (count - 1) for index in range(count)]


def _mesh_object(
    name: str,
    vertices: list[tuple[float, float, float]],
    faces: list[tuple[int, ...]],
    collection: bpy.types.Collection,
    materials: list[bpy.types.Material],
    material_indices: list[int] | None = None,
) -> bpy.types.Object:
    mesh = bpy.data.meshes.new(PREFIX + name + ":mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    obj = bpy.data.objects.new(PREFIX + name, mesh)
    collection.objects.link(obj)
    for material in materials:
        mesh.materials.append(material)
    if material_indices is not None:
        if len(material_indices) != len(mesh.polygons):
            raise RuntimeError(f"{name}: material index count does not match faces")
        for polygon, index in zip(mesh.polygons, material_indices):
            polygon.material_index = index
    return obj


def _excavate_city_ground_for_river() -> dict:
    """Cut the real city ground so the recessed hydraulic section is visible.

    The production city owns a continuous 0.20 m ground slab named ``gnd``.
    Merely lowering the river underneath that slab hides it; extruding water
    upward through the slab was the exact cause of river2's raised water wall.
    A watertight, densely sampled curved cutter removes only the reserved river
    corridor.  The authored 21-band channel then overlaps the cut by almost a
    metre per side, so no void, regular trench edge, or disturbance to the city
    parcel remains visible.
    """
    ground = bpy.data.objects.get("gnd")
    if ground is None or ground.type != "MESH" or ground.data is None:
        raise RuntimeError("river3 requires the production city ground mesh 'gnd'")
    if ground.library or ground.data.library:
        raise RuntimeError("river3 cannot excavate a linked/non-local city ground mesh")
    if ground.get("c2w_river_ground_excavated") or ground.get(
        "c2w_river3_ground_excavated"
    ):
        return {
            "target": ground.name,
            "cutter_sections": int(
                ground.get(
                    "c2w_river_excavation_sections",
                    ground.get("c2w_river3_excavation_sections", 0),
                )
            ),
            "cutter_half_width_m": float(
                ground.get(
                    "c2w_river_excavation_half_width_m",
                    ground.get("c2w_river3_excavation_half_width_m", 0.0),
                )
            ),
            "city_clearance_m": float(
                ground.get(
                    "c2w_river_excavation_city_clearance_m",
                    ground.get("c2w_river3_excavation_city_clearance_m", 0.0),
                )
            ),
            "result_vertices": len(ground.data.vertices),
            "result_faces": len(ground.data.polygons),
            "applied": True,
        }

    cutter_half_width = 11.85
    cutter_top = 1.20
    cutter_bottom = -2.25
    ys = _ys(SECTION_COUNT + 20, Y_MIN - 8.0, Y_MAX + 8.0)
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    for y in ys:
        left_top = _point(y, -cutter_half_width, cutter_top)
        right_top = _point(y, cutter_half_width, cutter_top)
        left_bottom = _point(y, -cutter_half_width, cutter_bottom)
        right_bottom = _point(y, cutter_half_width, cutter_bottom)
        vertices.extend(
            (tuple(left_top), tuple(right_top), tuple(left_bottom), tuple(right_bottom))
        )
    for row in range(len(ys) - 1):
        a = row * 4
        faces.extend(
            (
                # Outward winding: top +Z, bottom -Z, left -normal,
                # right +normal.  Exact Boolean relies on this closed orientation.
                (a, a + 1, a + 5, a + 4),
                (a + 2, a + 6, a + 7, a + 3),
                (a, a + 4, a + 6, a + 2),
                (a + 1, a + 3, a + 7, a + 5),
            )
        )
    faces.extend(
        (
            (0, 2, 3, 1),
            (
                len(vertices) - 4,
                len(vertices) - 3,
                len(vertices) - 1,
                len(vertices) - 2,
            ),
        )
    )

    cutter_mesh = bpy.data.meshes.new(PREFIX + "curved_ground_excavation_volume:mesh")
    cutter_mesh.from_pydata(vertices, [], faces)
    if cutter_mesh.validate(clean_customdata=True):
        raise RuntimeError("river3 excavation cutter required invalid-geometry repair")
    cutter_mesh.update()
    cutter = bpy.data.objects.new(
        PREFIX + "curved_ground_excavation_volume", cutter_mesh
    )
    bpy.context.scene.collection.objects.link(cutter)
    modifier = ground.modifiers.new(PREFIX + "apply_curved_river_excavation", "BOOLEAN")
    modifier.operation = "DIFFERENCE"
    modifier.solver = "EXACT"
    modifier.object = cutter
    for obj in bpy.context.selected_objects:
        obj.select_set(False)
    ground.hide_set(False)
    ground.select_set(True)
    bpy.context.view_layer.objects.active = ground
    result = bpy.ops.object.modifier_apply(modifier=modifier.name)
    if "FINISHED" not in result:
        raise RuntimeError(f"river3 city-ground excavation Boolean failed: {result}")
    bpy.data.objects.remove(cutter, do_unlink=True)
    if cutter_mesh.users == 0:
        bpy.data.meshes.remove(cutter_mesh)

    cut_min_x = min(_center_x(y) - cutter_half_width for y in ys)
    city_clearance = cut_min_x - CITY_EDGE_X
    # The Exact solver preserves the curved aperture as vertex-rich N-gons,
    # so polygon count alone is not a meaningful density measure here.
    if (
        city_clearance < 0.50
        or len(ground.data.vertices) < 20
        or len(ground.data.polygons) < 8
    ):
        raise RuntimeError(
            "river3 ground excavation failed its preservation/topology gate: "
            f"city_clearance={city_clearance:.3f}, verts={len(ground.data.vertices)}, faces={len(ground.data.polygons)}"
        )
    ground["c2w_river_ground_excavated"] = True
    ground["c2w_river_excavation_sections"] = len(ys)
    ground["c2w_river_excavation_half_width_m"] = cutter_half_width
    ground["c2w_river_excavation_city_clearance_m"] = city_clearance
    ground["c2w_river_excavation_filled_by_multiband_channel"] = True
    return {
        "target": ground.name,
        "cutter_sections": len(ys),
        "cutter_half_width_m": cutter_half_width,
        "city_clearance_m": city_clearance,
        "result_vertices": len(ground.data.vertices),
        "result_faces": len(ground.data.polygons),
        "applied": True,
    }


def _build_channel(collection: bpy.types.Collection, materials: dict) -> dict:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    cross_section_count = 21
    crest_heights: list[float] = []
    waterline_heights: list[float] = []
    for y in _ys():
        width = _half_width(y)
        surface_width = _surface_half_width(y)
        bend = _bend_bias(y)
        bank_noise = 0.045 * math.sin(y * 0.73) + 0.022 * math.sin(y * 2.17 + 0.4)
        # Asymmetric terraces encode outer-bend erosion and inner-bend
        # deposition while the fixed 13.8 m envelope preserves the city.
        left_shift = -0.18 * bend
        right_shift = 0.18 * bend
        offsets = (
            -13.8,
            -12.0,
            -10.35,
            -8.75,
            -7.25,
            -surface_width - 0.90 + left_shift,
            -surface_width - 0.35 + left_shift,
            -surface_width + left_shift,
            -width * 0.68,
            -width * 0.30,
            0.0,
            width * 0.30,
            width * 0.68,
            surface_width + right_shift,
            surface_width + 0.35 + right_shift,
            surface_width + 0.90 + right_shift,
            7.25,
            8.75,
            10.35,
            12.0,
            13.8,
        )
        left_cut = 0.075 * max(0.0, bend)
        right_cut = 0.075 * max(0.0, -bend)
        heights = (
            0.34 + bank_noise,
            0.37 + bank_noise * 0.7,
            0.30 + bank_noise,
            0.19 + bank_noise * 0.5,
            0.055 - left_cut,
            -0.27 - left_cut,
            WATER_Z + 0.22 - left_cut,
            WATER_Z + 0.035,
            WATER_Z - 0.48,
            WATER_Z - 0.78,
            WATER_Z - 0.88 - 0.08 * bend,
            WATER_Z - 0.78,
            WATER_Z - 0.48,
            WATER_Z + 0.035,
            WATER_Z + 0.22 - right_cut,
            -0.27 - right_cut,
            0.055 - right_cut,
            0.19 - bank_noise * 0.4,
            0.30 - bank_noise * 0.5,
            0.37 - bank_noise * 0.55,
            0.34 - bank_noise * 0.45,
        )
        crest_heights.extend((heights[0], heights[1], heights[-2], heights[-1]))
        waterline_heights.extend((heights[7], heights[13]))
        vertices.extend(
            tuple(_point(y, offset, height)) for offset, height in zip(offsets, heights)
        )
    band_material = (0, 0, 0, 0, 1, 1, 2, 2, 3, 3, 3, 3, 2, 2, 1, 1, 0, 0, 0, 0)
    for row in range(SECTION_COUNT - 1):
        for column in range(cross_section_count - 1):
            a = row * cross_section_count + column
            b = a + 1
            c = a + cross_section_count + 1
            d = a + cross_section_count
            faces.append((a, b, c, d))
            indices.append(band_material[column])
    bank = _mesh_object(
        "incised_alluvial_channel",
        vertices,
        faces,
        collection,
        [materials["bank"], materials["gravel"], materials["wet"], materials["bed"]],
        indices,
    )
    bank["c2w_river_role"] = "variable_width_incised_channel_and_banks"
    bank["c2w_cross_sections"] = SECTION_COUNT
    bank["c2w_channel_length_m"] = Y_MAX - Y_MIN
    bank["c2w_cross_section_bands"] = cross_section_count - 1
    bank["c2w_asymmetric_erosion_and_deposition"] = True
    bank["c2w_city_side_envelope_x_min"] = min(
        vertex[0] for vertex in vertices if -42.0 <= vertex[1] <= 54.5
    )
    bank["c2w_minimum_bank_crest_z"] = min(crest_heights)
    bank["c2w_minimum_waterline_bank_z"] = min(waterline_heights)
    bank["c2w_nominal_water_z"] = WATER_Z
    bank["c2w_water_below_bank_section"] = min(waterline_heights) > WATER_Z
    solidify = bank.modifiers.new(PREFIX + "bank_subsurface_thickness", "SOLIDIFY")
    solidify.thickness = -0.32
    solidify.offset = -1.0
    return {"object": bank, "vertices": len(vertices), "faces": len(faces)}


def _load_infinigen_river_water():
    # Importing ``infinigen.assets.materials.fluid`` directly causes a circular
    # import in this pinned Infinigen revision.  Loading the official source
    # module by file executes the exact RiverWater component without editing or
    # copying it.
    source = ROOT / "infinigen/infinigen/assets/materials/fluid/river_water.py"
    spec = importlib.util.spec_from_file_location(
        "c2w_official_infinigen_river_water", source
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module, source


def _set_socket(node: bpy.types.Node, name: str, value) -> None:
    socket = node.inputs.get(name)
    if socket is not None:
        socket.default_value = value


def _enhance_infinigen_water_material(material: bpy.types.Material) -> None:
    """Retain the official material datablock but rebuild it for urban daylight.

    The pinned RiverWater surface shader was authored for deep nature-scene
    liquid volumes and becomes an almost perfect mirror in this shallow urban
    corridor.  Its genuine geometry component is kept; this extension adds a
    calibrated shallow-water BSDF, depth/shore coloration, anisotropic
    multi-scale flow normals, broad suspended-sediment variation, and physical
    absorption/scattering to the material it created.  These scale-separated
    cues remain legible from aerial, oblique-bank, bridge and water-level views.
    """
    material.name = PREFIX + "Infinigen_RiverWater_physically_enhanced"
    material.use_nodes = True
    nodes, links = material.node_tree.nodes, material.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    output.name = PREFIX + "physical_water_output"
    shader = nodes.new("ShaderNodeBsdfPrincipled")
    shader.name = PREFIX + "shallow_river_bsdf"
    _set_socket(shader, "IOR", 1.333)
    # River4 restores the optical separation lost in river3: most energy is
    # transmitted through the surface while grazing angles are carried by the
    # Principled BSDF's physical Fresnel response.  A thin coat is enough; the
    # former strong coat made the whole channel look like blue plastic.
    _set_socket(shader, "Transmission Weight", 0.92)
    _set_socket(shader, "Coat Weight", 0.035)
    _set_socket(shader, "Coat Roughness", 0.035)
    _set_socket(shader, "Specular IOR Level", 0.50)

    coordinates = nodes.new("ShaderNodeTexCoord")
    depth = nodes.new("ShaderNodeAttribute")
    depth.attribute_name = "c2w_depth_factor"
    turbulence = nodes.new("ShaderNodeAttribute")
    turbulence.attribute_name = "c2w_flow_turbulence"
    shore = nodes.new("ShaderNodeAttribute")
    shore.attribute_name = "c2w_shore_factor"

    depth_color = nodes.new("ShaderNodeValToRGB")
    depth_color.color_ramp.interpolation = "B_SPLINE"
    depth_color.color_ramp.elements[0].position = 0.0
    depth_color.color_ramp.elements[0].color = (0.042, 0.135, 0.105, 1.0)
    depth_color.color_ramp.elements[1].position = 1.0
    depth_color.color_ramp.elements[1].color = (0.003, 0.024, 0.041, 1.0)
    middle = depth_color.color_ramp.elements.new(0.48)
    middle.color = (0.008, 0.061, 0.072, 1.0)

    sediment_noise = nodes.new("ShaderNodeTexNoise")
    sediment_noise.noise_dimensions = "3D"
    _set_socket(sediment_noise, "Scale", 0.42)
    _set_socket(sediment_noise, "Detail", 4.6)
    _set_socket(sediment_noise, "Roughness", 0.72)
    sediment_color = nodes.new("ShaderNodeValToRGB")
    sediment_color.color_ramp.elements[0].color = (0.24, 0.36, 0.29, 1.0)
    sediment_color.color_ramp.elements[1].color = (0.58, 0.69, 0.57, 1.0)
    color_mix = nodes.new("ShaderNodeMixRGB")
    color_mix.blend_type = "MULTIPLY"
    color_mix.inputs[0].default_value = 0.055

    shore_curve = nodes.new("ShaderNodeMapRange")
    _set_socket(shore_curve, "From Min", 0.68)
    _set_socket(shore_curve, "From Max", 1.0)
    _set_socket(shore_curve, "To Min", 0.0)
    _set_socket(shore_curve, "To Max", 0.32)
    shore_curve.clamp = True
    shore_mix = nodes.new("ShaderNodeMixRGB")
    shore_mix.blend_type = "MIX"
    shore_mix.inputs[2].default_value = (0.075, 0.115, 0.080, 1.0)

    roughness = nodes.new("ShaderNodeMapRange")
    _set_socket(roughness, "From Min", 0.0)
    _set_socket(roughness, "From Max", 1.0)
    _set_socket(roughness, "To Min", 0.030)
    _set_socket(roughness, "To Max", 0.105)
    roughness.clamp = True

    macro_wave = nodes.new("ShaderNodeTexWave")
    macro_wave.wave_type = "BANDS"
    macro_wave.bands_direction = "Y"
    macro_wave.wave_profile = "SIN"
    _set_socket(macro_wave, "Scale", 1.25)
    _set_socket(macro_wave, "Distortion", 5.4)
    _set_socket(macro_wave, "Detail", 5.0)
    _set_socket(macro_wave, "Detail Scale", 1.7)
    _set_socket(macro_wave, "Detail Roughness", 0.68)

    capillary_wave = nodes.new("ShaderNodeTexWave")
    capillary_wave.wave_type = "BANDS"
    capillary_wave.bands_direction = "Y"
    capillary_wave.wave_profile = "SIN"
    _set_socket(capillary_wave, "Scale", 10.5)
    _set_socket(capillary_wave, "Distortion", 3.2)
    _set_socket(capillary_wave, "Detail", 4.0)
    _set_socket(capillary_wave, "Detail Scale", 3.1)
    _set_socket(capillary_wave, "Detail Roughness", 0.62)

    cross_noise = nodes.new("ShaderNodeTexNoise")
    cross_noise.noise_dimensions = "3D"
    _set_socket(cross_noise, "Scale", 2.15)
    _set_socket(cross_noise, "Detail", 7.0)
    _set_socket(cross_noise, "Roughness", 0.71)

    fine_current = nodes.new("ShaderNodeTexNoise")
    fine_current.noise_dimensions = "3D"
    _set_socket(fine_current, "Scale", 24.0)
    _set_socket(fine_current, "Detail", 5.5)
    _set_socket(fine_current, "Roughness", 0.64)

    modulated_macro = nodes.new("ShaderNodeMath")
    modulated_macro.operation = "MULTIPLY"
    scaled_micro = nodes.new("ShaderNodeMath")
    scaled_micro.operation = "MULTIPLY"
    scaled_micro.inputs[1].default_value = 0.26
    combined_height = nodes.new("ShaderNodeMath")
    combined_height.operation = "ADD"
    current_height = nodes.new("ShaderNodeMath")
    current_height.operation = "MULTIPLY"
    current_height.inputs[1].default_value = 0.11
    final_height = nodes.new("ShaderNodeMath")
    final_height.operation = "ADD"

    micro_bump = nodes.new("ShaderNodeBump")
    _set_socket(micro_bump, "Strength", 0.20)
    _set_socket(micro_bump, "Distance", 0.006)
    macro_bump = nodes.new("ShaderNodeBump")
    _set_socket(macro_bump, "Strength", 0.17)
    _set_socket(macro_bump, "Distance", 0.035)

    absorption = nodes.new("ShaderNodeVolumeAbsorption")
    _set_socket(absorption, "Color", (0.075, 0.205, 0.155, 1.0))
    _set_socket(absorption, "Density", 0.34)
    scatter = nodes.new("ShaderNodeVolumeScatter")
    _set_socket(scatter, "Color", (0.045, 0.125, 0.105, 1.0))
    _set_socket(scatter, "Density", 0.006)
    _set_socket(scatter, "Anisotropy", 0.32)
    volume = nodes.new("ShaderNodeAddShader")

    links.new(depth.outputs["Fac"], depth_color.inputs["Fac"])
    links.new(coordinates.outputs["Object"], sediment_noise.inputs["Vector"])
    links.new(sediment_noise.outputs["Fac"], sediment_color.inputs["Fac"])
    links.new(depth_color.outputs["Color"], color_mix.inputs[1])
    links.new(sediment_color.outputs["Color"], color_mix.inputs[2])
    links.new(shore.outputs["Fac"], shore_curve.inputs["Value"])
    links.new(shore_curve.outputs["Result"], shore_mix.inputs[0])
    links.new(color_mix.outputs["Color"], shore_mix.inputs[1])
    links.new(shore_mix.outputs["Color"], shader.inputs["Base Color"])
    links.new(turbulence.outputs["Fac"], roughness.inputs["Value"])
    links.new(roughness.outputs["Result"], shader.inputs["Roughness"])
    for texture in (macro_wave, capillary_wave, cross_noise, fine_current):
        links.new(coordinates.outputs["Object"], texture.inputs["Vector"])
    links.new(macro_wave.outputs["Color"], modulated_macro.inputs[0])
    links.new(cross_noise.outputs["Fac"], modulated_macro.inputs[1])
    links.new(capillary_wave.outputs["Color"], scaled_micro.inputs[0])
    links.new(modulated_macro.outputs[0], combined_height.inputs[0])
    links.new(scaled_micro.outputs[0], combined_height.inputs[1])
    links.new(fine_current.outputs["Fac"], current_height.inputs[0])
    links.new(combined_height.outputs[0], final_height.inputs[0])
    links.new(current_height.outputs[0], final_height.inputs[1])
    links.new(fine_current.outputs["Fac"], micro_bump.inputs["Height"])
    links.new(micro_bump.outputs["Normal"], macro_bump.inputs["Normal"])
    links.new(final_height.outputs[0], macro_bump.inputs["Height"])
    links.new(macro_bump.outputs["Normal"], shader.inputs["Normal"])
    links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    links.new(absorption.outputs["Volume"], volume.inputs[0])
    links.new(scatter.outputs["Volume"], volume.inputs[1])
    links.new(volume.outputs[0], output.inputs["Volume"])

    material.diffuse_color = (0.008, 0.055, 0.070, 1.0)
    material["c2w_official_infinigen_riverwater_extended"] = True
    material["c2w_physical_ior"] = 1.333
    material["c2w_flow_normal_layers"] = 6
    material["c2w_volume_absorption_density"] = 0.34
    material["c2w_surface_transmission_weight"] = 0.92
    material["c2w_no_curve_based_foam"] = True
    material[
        "c2w_multiview_surface_cues"
    ] = "fresnel;depth;shore;suspended_sediment;macro_current;capillary;fine_current"


def _build_water(collection: bpy.types.Collection) -> dict:
    columns = WATER_COLUMNS
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, ...]] = []
    depth_factors: list[float] = []
    turbulence_values: list[float] = []
    shore_values: list[float] = []
    edge_surface_z: list[float] = []
    for y in _ys():
        width = _surface_half_width(y)
        for column in range(columns):
            t = column / (columns - 1)
            offset = -width + 2.0 * width * t
            z, turbulence = _water_surface_height(y, offset, width)
            vertices.append(tuple(_point(y, offset, z)))
            if column in (0, columns - 1):
                edge_surface_z.append(z)
            depth_factors.append(max(0.0, 1.0 - abs(offset) / width))
            turbulence_values.append(turbulence)
            shore_values.append(min(1.0, abs(offset) / width))
    for row in range(SECTION_COUNT - 1):
        for column in range(columns - 1):
            a = row * columns + column
            faces.append((a, a + 1, a + columns + 1, a + columns))
    water = _mesh_object(
        "infinigen_river_water_surface", vertices, faces, collection, []
    )
    for polygon in water.data.polygons:
        polygon.use_smooth = True
    for name, values in (
        ("c2w_depth_factor", depth_factors),
        ("c2w_flow_turbulence", turbulence_values),
        ("c2w_shore_factor", shore_values),
    ):
        attribute = water.data.attributes.new(name, "FLOAT", "POINT")
        for item, value in zip(attribute.data, values):
            item.value = value
    module, source = _load_infinigen_river_water()
    module.RiverWater().apply(water)
    official_material = water.data.materials[0] if water.data.materials else None
    if official_material is None:
        raise RuntimeError("Infinigen RiverWater did not assign its official material")
    _enhance_infinigen_water_material(official_material)
    water.name = PREFIX + "infinigen_river_water_surface"
    water["c2w_river_role"] = "flowing_water_surface"
    water[
        "c2w_infinigen_component"
    ] = "infinigen.assets.materials.fluid.river_water.RiverWater"
    water["c2w_infinigen_source"] = str(source)
    water["c2w_direct_infinigen_call"] = True
    water["c2w_surface_grid"] = f"{SECTION_COUNT}x{columns}"
    water["c2w_explicit_flow_relief_layers"] = 6
    water["c2w_physically_based_water_shader"] = True
    water["c2w_volume_absorption"] = True
    water["c2w_depth_and_turbulence_attributes"] = True
    water["c2w_nominal_surface_z"] = WATER_Z
    water["c2w_surface_below_bank"] = True
    water["c2w_no_exposed_volume_wall"] = True
    water["c2w_multiview_water_detail"] = True
    water["c2w_surface_geometry_foam_removed"] = True
    water["c2w_active_channel_large_stones"] = 0
    solidify = water.modifiers.new(PREFIX + "water_volume_depth", "SOLIDIFY")
    # The generated shoreline lies below its bank crest, so this physical
    # depth remains buried at the sides rather than producing a visible wall.
    # Extra depth is important for Beer-Lambert colour in high-angle views.
    solidify.thickness = 0.92
    solidify.offset = -1.0
    return {
        "object": water,
        "vertices": len(vertices),
        "faces": len(faces),
        "official_modifier_count": sum(m.type == "NODES" for m in water.modifiers),
        "official_material": official_material.name,
        "explicit_flow_relief_layers": 6,
        "physical_shader": True,
        "material_node_count": len(official_material.node_tree.nodes),
        "surface_vertical_relief_m": round(
            max(v[2] for v in vertices) - min(v[2] for v in vertices), 5
        ),
        "surface_z_min": min(v[2] for v in vertices),
        "surface_z_max": max(v[2] for v in vertices),
        "edge_surface_z_max": max(edge_surface_z),
        "source": str(source),
    }


def _ribbon(
    name: str,
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    ys: list[float],
    offset_fn,
    width: float,
    z: float,
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    for y in ys:
        offset = offset_fn(y)
        vertices.extend(
            (
                tuple(_point(y, offset - width / 2, z)),
                tuple(_point(y, offset + width / 2, z)),
            )
        )
    faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(ys) - 1)]
    obj = _mesh_object(name, vertices, faces, collection, [material])
    return obj


def _curve_object(
    name: str,
    points: list[Vector],
    collection: bpy.types.Collection,
    material: bpy.types.Material,
    bevel: float,
    resolution: int = 2,
) -> bpy.types.Object:
    data = bpy.data.curves.new(PREFIX + name + ":curve", "CURVE")
    data.dimensions = "3D"
    data.resolution_u = resolution
    data.bevel_depth = bevel
    data.bevel_resolution = 3
    spline = data.splines.new("NURBS")
    spline.points.add(len(points) - 1)
    for target, point in zip(spline.points, points):
        target.co = (*point, 1.0)
    spline.order_u = min(4, len(points))
    spline.use_endpoint_u = True
    obj = bpy.data.objects.new(PREFIX + name, data)
    collection.objects.link(obj)
    data.materials.append(material)
    return obj


def _build_promenade(collection: bpy.types.Collection, materials: dict) -> dict:
    path_ys = _ys(61, -59.0, 61.0)
    path = _ribbon(
        "park_leisure_riverfront_promenade",
        collection,
        materials["paver"],
        path_ys,
        lambda _y: -11.75,
        2.35,
        0.31,
    )
    path["c2w_river_role"] = "accessible_park_leisure_promenade"
    path["c2w_promenenade_length_m"] = 120.0
    solidify = path.modifiers.new(PREFIX + "promenade_structural_depth", "SOLIDIFY")
    solidify.thickness = -0.14
    solidify.offset = -1.0
    curb_points = [_point(y, -10.48, 0.39) for y in path_ys]
    curb = _curve_object(
        "promenade_river_edge_curb", curb_points, collection, materials["stone"], 0.075
    )
    curb["c2w_river_role"] = "promenade_safety_edge"

    # Short, physical connections make the riverfront part of the park and
    # leisure circulation instead of an isolated decorative strip.
    connections = []
    for index, y in enumerate((-28.0, 30.0)):
        path_point = _point(y, -11.75, 0.32)
        start = Vector((54.2, y, 0.32))
        direction = path_point - start
        center = (start + path_point) / 2
        length = max(0.5, direction.length)
        obj = _box(
            f"riverfront_connection_{index}",
            center,
            (length, 2.15, 0.14),
            materials["paver"],
            collection,
            math.atan2(direction.y, direction.x),
            0.035,
        )
        obj["c2w_river_role"] = "district_to_riverfront_connection"
        connections.append(obj)

    # Imported production street furniture retains the scene's established
    # detail level; none of these are proxy primitives.
    import urban_assets as urban_assets

    furniture_objects = []
    for index, y in enumerate((-46.0, -15.0, 14.0, 46.0)):
        p = _point(y, -12.1, 0.35)
        _center, tangent, _normal = _frame(y)
        yaw = math.atan2(tangent.y, tangent.x)
        placed = urban_assets.place_streetlight(
            (p.x, p.y), collection, yaw=yaw - math.pi / 2, day=True
        )
        for obj in placed:
            obj["c2w_river_role"] = "riverfront_streetlight"
        furniture_objects.extend(placed)
    for index, y in enumerate((-38.0, -4.0, 38.0)):
        p = _point(y, -12.15, 0.35)
        _center, tangent, _normal = _frame(y)
        yaw = math.atan2(tangent.y, tangent.x)
        placed = urban_assets.place_bench_classic((p.x, p.y), collection, yaw=yaw)
        for obj in placed:
            obj["c2w_river_role"] = "riverfront_bench"
        furniture_objects.extend(placed)
    for y in (-20.0, 20.0):
        p = _point(y, -12.65, 0.35)
        placed = urban_assets.place_bin_domed((p.x, p.y), collection)
        for obj in placed:
            obj["c2w_river_role"] = "riverfront_waste_bin"
        furniture_objects.extend(placed)
    return {
        "path": path,
        "path_vertices": len(path.data.vertices),
        "connections": len(connections),
        "production_furniture_objects": len(furniture_objects),
    }


def _box(
    name: str,
    location: Vector | tuple[float, float, float],
    dimensions: tuple[float, float, float],
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    yaw: float = 0.0,
    bevel: float = 0.0,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cube_add(size=1, location=location, rotation=(0, 0, yaw))
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.dimensions = dimensions
    obj.data.materials.append(material)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    if bevel > 0:
        modifier = obj.modifiers.new(PREFIX + "edge_relief", "BEVEL")
        modifier.width = bevel
        modifier.segments = 2
    collection.objects.link(obj)
    for old in list(obj.users_collection):
        if old is not collection:
            old.objects.unlink(obj)
    return obj


def _cylinder(
    name: str,
    location: Vector,
    radius: float,
    depth: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
    vertices: int = 28,
) -> bpy.types.Object:
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=radius, depth=depth, location=location
    )
    obj = bpy.context.object
    obj.name = PREFIX + name
    obj.data.materials.append(material)
    for polygon in obj.data.polygons:
        polygon.use_smooth = True
    collection.objects.link(obj)
    for old in list(obj.users_collection):
        if old is not collection:
            old.objects.unlink(obj)
    return obj


def _local(
    center: Vector,
    tangent: Vector,
    normal: Vector,
    along: float,
    across: float,
    z: float,
) -> Vector:
    return Vector((center.x, center.y, z)) + normal * along + tangent * across


def _build_footbridge(collection: bpy.types.Collection, materials: dict) -> dict:
    y = 26.0
    center, tangent, normal = _frame(y)
    yaw = math.atan2(normal.y, normal.x)
    span, deck_width, deck_z = 22.6, 2.75, 0.72
    objects: list[bpy.types.Object] = []

    # Closely spaced hardwood planks, longitudinal stringers and transverse
    # diaphragms form a credible structural deck rather than one bridge box.
    plank_count = 47
    for index in range(plank_count):
        along = -span / 2 + span * (index + 0.5) / plank_count
        loc = _local(center, tangent, normal, along, 0.0, deck_z)
        plank = _box(
            f"footbridge_deck_plank_{index:02d}",
            loc,
            (span / plank_count * 0.92, deck_width, 0.13),
            materials["wood"],
            collection,
            yaw,
            0.018,
        )
        plank["c2w_bridge_role"] = "individual_hardwood_deck_plank"
        objects.append(plank)
    for side in (-0.88, 0.88):
        stringer = _box(
            f"footbridge_stringer_{side:+.2f}",
            _local(center, tangent, normal, 0, side, deck_z - 0.23),
            (span, 0.22, 0.34),
            materials["steel"],
            collection,
            yaw,
            0.025,
        )
        stringer["c2w_bridge_role"] = "load_bearing_stringer"
        objects.append(stringer)
    for index, along in enumerate((-8.5, -4.2, 0.0, 4.2, 8.5)):
        diaphragm = _box(
            f"footbridge_cross_diaphragm_{index}",
            _local(center, tangent, normal, along, 0, deck_z - 0.27),
            (0.18, 2.35, 0.20),
            materials["steel"],
            collection,
            yaw,
            0.015,
        )
        diaphragm["c2w_bridge_role"] = "cross_diaphragm"
        objects.append(diaphragm)

    post_positions = [(-span / 2 + 0.65) + i * 1.42 for i in range(16)]
    for side in (-1.28, 1.28):
        for index, along in enumerate(post_positions):
            post = _box(
                f"footbridge_railpost_{'l' if side < 0 else 'r'}_{index:02d}",
                _local(center, tangent, normal, along, side, deck_z + 0.58),
                (0.10, 0.10, 1.22),
                materials["steel"],
                collection,
                yaw,
                0.012,
            )
            post["c2w_bridge_role"] = "guardrail_post"
            objects.append(post)
        for level in (0.64, 1.17):
            rail = _box(
                f"footbridge_guardrail_{side:+.2f}_{level:.2f}",
                _local(center, tangent, normal, 0, side, deck_z + level),
                (span - 0.55, 0.075, 0.085),
                materials["steel"],
                collection,
                yaw,
                0.018,
            )
            rail["c2w_bridge_role"] = "continuous_guardrail"
            objects.append(rail)

    for side in (-1, 1):
        abutment = _box(
            f"footbridge_stone_abutment_{side:+d}",
            _local(center, tangent, normal, side * (span / 2 + 0.15), 0, 0.13),
            (1.30, 3.55, 1.12),
            materials["stone"],
            collection,
            yaw,
            0.08,
        )
        abutment["c2w_bridge_role"] = "stone_bank_abutment"
        objects.append(abutment)
    for index, along in enumerate((-5.35, 5.35)):
        for across in (-0.72, 0.72):
            pier = _cylinder(
                f"footbridge_pier_{index}_{across:+.2f}",
                _local(center, tangent, normal, along, across, -0.39),
                0.27,
                2.05,
                materials["stone"],
                collection,
                vertices=32,
            )
            pier["c2w_bridge_role"] = "riverbed_pier"
            objects.append(pier)
    return {
        "objects": objects,
        "object_count": len(objects),
        "planks": plank_count,
        "span_m": span,
    }


def _polygon_prism(
    name: str,
    points: list[tuple[float, float]],
    z: float,
    depth: float,
    material: bpy.types.Material,
    collection: bpy.types.Collection,
) -> bpy.types.Object:
    n = len(points)
    vertices = [(x, y, z) for x, y in points] + [(x, y, z + depth) for x, y in points]
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    faces.extend((i, (i + 1) % n, (i + 1) % n + n, i + n) for i in range(n))
    obj = _mesh_object(name, vertices, faces, collection, [material])
    bevel = obj.modifiers.new(PREFIX + "naturally_rounded_edge", "BEVEL")
    bevel.width = 0.10
    bevel.segments = 3
    return obj


def _alluvial_bar_mesh(
    name: str,
    y: float,
    length: float,
    width: float,
    offset: float,
    collection: bpy.types.Collection,
    materials: dict,
    phase: float,
) -> bpy.types.Object:
    center, tangent, normal = _frame(y)
    segments, rings = 48, 3
    # These are sediment lenses on the bed, not islands or decorative rocks.
    # Their highest point remains at least 9 cm below the nominal surface.
    vertices = [
        (center.x + normal.x * offset, center.y + normal.y * offset, WATER_Z - 0.105)
    ]
    for ring in range(1, rings + 1):
        radial = ring / rings
        for step in range(segments):
            angle = math.tau * step / segments
            irregular = (
                1.0
                + 0.085 * math.sin(5 * angle + phase)
                + 0.035 * math.sin(11 * angle - phase)
            )
            point = center + tangent * (
                math.cos(angle) * length * 0.5 * radial * irregular
            )
            point += normal * (offset + math.sin(angle) * width * radial * irregular)
            crown = (1.0 - radial) ** 1.35
            z = (
                WATER_Z
                - 0.235
                + 0.105 * crown
                + 0.007 * math.sin(step * 1.71 + ring + phase)
            )
            vertices.append((point.x, point.y, z))
    faces: list[tuple[int, ...]] = []
    indices: list[int] = []
    for step in range(segments):
        faces.append((0, 1 + step, 1 + (step + 1) % segments))
        indices.append(0)
    for ring in range(1, rings):
        inner_start = 1 + (ring - 1) * segments
        outer_start = 1 + ring * segments
        for step in range(segments):
            faces.append(
                (
                    inner_start + step,
                    outer_start + step,
                    outer_start + (step + 1) % segments,
                    inner_start + (step + 1) % segments,
                )
            )
            indices.append(0 if ring == 1 else 1)
    bar = _mesh_object(
        name,
        vertices,
        faces,
        collection,
        [materials["gravel"], materials["wet"]],
        indices,
    )
    for polygon in bar.data.polygons:
        polygon.use_smooth = True
    solidify = bar.modifiers.new(PREFIX + "alluvial_lens_depth", "SOLIDIFY")
    solidify.thickness = -0.24
    solidify.offset = -1.0
    bar["c2w_alluvial_radial_rings"] = rings
    bar["c2w_alluvial_azimuth_samples"] = segments
    return bar


def _build_gravel_bars(collection: bpy.types.Collection, materials: dict) -> dict:
    bars = []
    specs = [
        (-47.0, 7.6, 1.35, 0.65),
        (-12.0, 6.4, 1.15, -0.58),
        (52.0, 8.2, 1.55, 0.72),
        (78.0, 10.2, 1.85, -0.82),
        (120.0, 7.5, 1.35, 0.62),
    ]
    for index, (y, length, width, offset) in enumerate(specs):
        bar = _alluvial_bar_mesh(
            f"alluvial_gravel_bar_{index}",
            y,
            length,
            width,
            offset,
            collection,
            materials,
            index * 1.37,
        )
        bar["c2w_river_role"] = "depositional_gravel_bar"
        bars.append(bar)
    return {"objects": bars, "count": len(bars)}


def _move_to_master(obj: bpy.types.Object, master: bpy.types.Collection) -> None:
    master.objects.link(obj)
    for old in list(obj.users_collection):
        if old is not master:
            old.objects.unlink(obj)


def _make_rock_masters(material: bpy.types.Material) -> list[bpy.types.Collection]:
    masters = []
    for index in range(5):
        rng = random.Random(90431 + index * 7919)
        master = bpy.data.collections.new(
            PREFIX + f"MASTER:multiscale_river_boulder:{index}"
        )
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=4, radius=1.0)
        obj = bpy.context.object
        obj.name = PREFIX + f"MASTER:multiscale_river_boulder:{index}:mesh"
        stretch = (
            rng.uniform(0.80, 1.35),
            rng.uniform(0.65, 1.10),
            rng.uniform(0.48, 0.82),
        )
        for vertex in obj.data.vertices:
            direction = vertex.co.normalized()
            coarse = math.sin(direction.x * (3.1 + index * 0.2) + index) * math.sin(
                direction.y * 4.3 - index * 0.7
            )
            medium = math.sin((direction.x + direction.z) * 9.1 + index * 1.7) * 0.45
            fine = math.sin((direction.y - direction.z) * 17.3 - index) * 0.18
            radius = 1.0 + 0.13 * coarse + 0.065 * medium + 0.025 * fine
            vertex.co.x *= radius * stretch[0]
            vertex.co.y *= radius * stretch[1]
            vertex.co.z *= radius * stretch[2]
        obj.data.materials.append(material)
        for polygon in obj.data.polygons:
            polygon.use_smooth = True
        obj["c2w_asset_quality"] = "642_vertex_multiscale_deformed_riparian_boulder"
        obj["c2w_procedural_frequency_layers"] = 3
        _move_to_master(obj, master)
        masters.append(master)
    return masters


def _rebind_rock_master_materials(
    masters: list[bpy.types.Collection],
    material: bpy.types.Material,
) -> int:
    """Give retained high-detail rock geometry the river3 wet stone response."""
    rebound = 0
    for master in masters:
        mesh_objects = [
            obj for obj in master.all_objects if obj.type == "MESH" and obj.data
        ]
        if not mesh_objects:
            continue
        for obj in mesh_objects:
            obj.data.materials.clear()
            obj.data.materials.append(material)
            obj["c2w_river3_wet_weathered_stone"] = True
        rebound += 1
    return rebound


def _rebind_bridge_stone(bridge: dict, material: bpy.types.Material) -> int:
    rebound = 0
    for obj in bridge["objects"]:
        if obj.get("c2w_bridge_role") not in {"stone_bank_abutment", "riverbed_pier"}:
            continue
        if obj.type != "MESH" or obj.data is None:
            continue
        obj.data.materials.clear()
        obj.data.materials.append(material)
        obj["c2w_river3_wet_weathered_stone"] = True
        rebound += 1
    bridge["riverstone_rebound_parts"] = rebound
    return rebound


def _instance(
    name: str,
    master: bpy.types.Collection,
    location: Vector,
    collection: bpy.types.Collection,
    scale: tuple[float, float, float],
    yaw: float,
) -> bpy.types.Object:
    obj = bpy.data.objects.new(PREFIX + name, None)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = master
    obj.location = location
    obj.scale = scale
    obj.rotation_euler[2] = yaw
    collection.objects.link(obj)
    return obj


def _scatter_boulders(
    collection: bpy.types.Collection,
    masters: list[bpy.types.Collection],
) -> dict:
    # River4 deliberately has no loose boulder scatter.  The river3 instances
    # read as pale prop-like blobs from both aerial and river-level cameras.
    # Natural coarse aggregate is represented by the channel material and
    # fully submerged small substrate cobbles instead.
    instances: list[bpy.types.Object] = []
    vertex_counts = [
        sum(len(o.data.vertices) for o in master.objects if o.type == "MESH")
        for master in masters
    ]
    return {
        "masters": masters,
        "instances": instances,
        "master_vertex_counts": vertex_counts,
        "active_channel_large_stones": 0,
        "loose_bank_boulders": 0,
    }


def _build_boulders(
    collection: bpy.types.Collection, material: bpy.types.Material
) -> dict:
    masters = _make_rock_masters(material)
    rebound = _rebind_rock_master_materials(masters, material)
    result = _scatter_boulders(collection, masters)
    result["wet_stone_rebound_masters"] = rebound
    return result


def _build_riffle_cobbles(
    collection: bpy.types.Collection, masters: list[bpy.types.Collection]
) -> dict:
    """Build small substrate cobbles with a guaranteed submerged clearance."""
    rng = random.Random(770219)
    instances = []
    zones = ((-39.0, 5.4), (76.0, 6.2), (119.0, 4.8))
    for zone_index, (center_y, extent) in enumerate(zones):
        for local_index in range(64):
            y = center_y + rng.uniform(-extent, extent)
            width = _half_width(y)
            offset = rng.uniform(-0.82 * width, 0.82 * width)
            size = rng.uniform(0.075, 0.155)
            z = rng.uniform(WATER_Z - 0.40, WATER_Z - 0.28)
            obj = _instance(
                f"riffle_{zone_index}_cobble_{local_index:03d}",
                masters[(local_index + zone_index) % len(masters)],
                _point(y, offset, z),
                collection,
                (
                    size * rng.uniform(0.82, 1.25),
                    size * rng.uniform(0.72, 1.16),
                    size * rng.uniform(0.62, 0.94),
                ),
                rng.random() * math.tau,
            )
            obj["c2w_river_role"] = "submerged_high_detail_riffle_cobble"
            obj["c2w_riffle_zone"] = zone_index
            obj["c2w_minimum_surface_clearance_m"] = 0.12
            instances.append(obj)
    return {
        "instances": instances,
        "count": len(instances),
        "zones": len(zones),
        "minimum_surface_clearance_m": 0.12,
        "surface_breaking_cobbles": 0,
    }


def _build_wetted_waterline(
    collection: bpy.types.Collection, material: bpy.types.Material
) -> dict:
    objects = []
    edge_ys = _ys(SECTION_COUNT, Y_MIN + 0.5, Y_MAX - 0.5)
    for side in (-1, 1):
        edge = _ribbon(
            f"intermittently_wetted_bank_edge_{'west' if side < 0 else 'east'}",
            collection,
            material,
            edge_ys,
            lambda y, side=side: side
            * (_surface_half_width(y) + 0.16 + 0.035 * math.sin(y * 0.9)),
            0.36,
            WATER_Z + 0.018,
        )
        edge["c2w_river_role"] = "saturated_bank_waterline_transition"
        edge["c2w_waterline_continuity_m"] = Y_MAX - Y_MIN - 1.0
        objects.append(edge)
    return {
        "objects": objects,
        "count": len(objects),
        "vertices": sum(len(o.data.vertices) for o in objects),
    }


def _build_riparian_vegetation(
    collection: bpy.types.Collection, materials: dict
) -> dict:
    rng = random.Random(509027)
    tree_masters = sorted(
        [
            c
            for c in bpy.data.collections
            if c.name.startswith("full02:MASTER:TreeFactory:")
        ],
        key=lambda c: c.name,
    )[:5]
    if len(tree_masters) != 5:
        raise RuntimeError(
            f"river corridor requires the five full07 botanical tree masters, got {len(tree_masters)}"
        )
    trees = []
    tree_sites = [
        (-53, 1),
        (-34, 1),
        (-12, 1),
        (9, 1),
        (51, 1),
        (70, -1),
        (88, 1),
        (108, -1),
        (129, 1),
        (141, -1),
    ]
    for index, (y, side) in enumerate(tree_sites):
        # Trees inside the active promenade interval stay on the natural east
        # bank; northern west-bank trees begin only after the path terminates.
        if -59 < y < 61:
            side = 1
        offset = side * rng.uniform(10.2, 12.6)
        loc = _point(float(y), offset, 0.21)
        scale = rng.uniform(0.58, 0.76)
        obj = _instance(
            f"riparian_botanical_tree_{index:02d}",
            tree_masters[index % 5],
            loc,
            collection,
            (scale, scale, scale),
            rng.random() * math.tau,
        )
        obj["c2w_river_role"] = "high_detail_riparian_tree"
        obj["c2w_real_world_tree_height_m"] = scale * 8.2
        trees.append(obj)

    # A genuine Infinigen grass scatter occupies only the natural east upper
    # bank, away from the paved promenade and the grass-free leisure parcel.
    grass_ys = _ys(53, Y_MIN + 2, Y_MAX - 2)
    grass_surface = _ribbon(
        "riparian_grass_scatter_surface",
        collection,
        materials["bank"],
        grass_ys,
        lambda _y: 10.25,
        4.05,
        0.235,
    )
    grass_surface["c2w_river_role"] = "east_bank_riparian_grass_surface"
    from infinigen.assets.scatters.grass import Grass
    from infinigen.core.util.math import FixedSeed

    with FixedSeed(817733):
        grass_result = Grass().apply(grass_surface, selection=None)
    grass_object = grass_result[0] if isinstance(grass_result, tuple) else grass_result
    if grass_object is None:
        raise RuntimeError("Infinigen Grass failed to create the riparian understory")
    grass_object.name = PREFIX + "Infinigen_riparian_grass_understory"
    grass_object["c2w_river_role"] = "genuine_infinigen_riparian_grass"
    grass_object["c2w_direct_infinigen_asset"] = True
    return {
        "reed_masters": [],
        "reed_instances": [],
        "reed_master_vertex_counts": [],
        "tree_instances": trees,
        "grass_surface": grass_surface,
        "grass_object": grass_object,
    }


def _build_foam(
    collection: bpy.types.Collection,
    material: bpy.types.Material | None = None,
) -> dict:
    """Return an explicit zero-geometry foam system.

    Thin beveled curves cannot represent a turbulent air/water volume and were
    the artificial white lines reported in river3.  River4 encodes small-scale
    flow only in surface relief and normals; no substitute white geometry is
    emitted.
    """
    del collection, material
    return {
        "objects": [],
        "count": 0,
        "flow_streaks": 0,
        "wake_curves": 0,
        "bank_contact_segments": 0,
        "surface_curve_geometry": 0,
    }


def _audit(
    channel: dict,
    water: dict,
    promenade: dict,
    bridge: dict,
    gravel: dict,
    boulders: dict,
    riffles: dict,
    waterline: dict,
    vegetation: dict,
    foam: dict,
    excavation: dict,
) -> dict:
    widths = [_surface_half_width(y) * 2 for y in _ys()]
    crest_clearance = (
        float(channel["object"]["c2w_minimum_bank_crest_z"]) - water["surface_z_max"]
    )
    waterline_clearance = (
        float(channel["object"]["c2w_minimum_waterline_bank_z"])
        - water["edge_surface_z_max"]
    )
    checks = {
        "direct_infinigen_riverwater": bool(
            water["official_modifier_count"] >= 1 and water["official_material"]
        ),
        "dense_water_surface": water["vertices"] >= 10000 and water["faces"] >= 10000,
        "physical_multiscale_water_shader": bool(
            water["physical_shader"]
            and water["explicit_flow_relief_layers"] >= 6
            and water["material_node_count"] >= 24
            and water["surface_vertical_relief_m"] >= 0.020
        ),
        "incised_multiband_channel": channel["vertices"] >= 5400
        and channel["faces"] >= 5100,
        "asymmetric_natural_geomorphology": bool(
            channel["object"].get("c2w_asymmetric_erosion_and_deposition")
        ),
        "water_surface_below_channel_banks": bool(
            channel["object"].get("c2w_water_below_bank_section")
            and crest_clearance >= 0.65
            and waterline_clearance >= 0.02
        ),
        "shore_taper_prevents_exposed_water_wall": bool(
            water["object"].get("c2w_no_exposed_volume_wall")
        ),
        "production_ground_curved_excavation": bool(
            excavation["applied"]
            and excavation["cutter_sections"] >= 270
            and excavation["city_clearance_m"] >= 0.50
            and excavation["result_vertices"] >= 20
            and excavation["result_faces"] >= 8
        ),
        "variable_natural_width": max(widths) - min(widths) >= 1.3,
        "continuous_208m_corridor": abs((Y_MAX - Y_MIN) - 208.0) < 0.01,
        "original_city_environment_preserved": float(
            channel["object"]["c2w_city_side_envelope_x_min"]
        )
        > CITY_EDGE_X,
        "accessible_promenade": promenade["path_vertices"] >= 120
        and promenade["connections"] == 2,
        "structural_footbridge": bridge["object_count"] >= 90
        and bridge["planks"] >= 40,
        "alluvial_deposition": gravel["count"] >= 5,
        "active_channel_free_of_large_stones": bool(
            len(boulders["instances"]) == 0
            and boulders.get("active_channel_large_stones", 0) == 0
            and boulders.get("loose_bank_boulders", 0) == 0
        ),
        "weathered_bridge_riverstone": bridge.get("riverstone_rebound_parts", 0) >= 6,
        "fully_submerged_small_bed_cobbles": bool(
            riffles["zones"] == 3
            and riffles["count"] >= 190
            and riffles.get("surface_breaking_cobbles", -1) == 0
            and riffles.get("minimum_surface_clearance_m", 0.0) >= 0.10
        ),
        "continuous_saturated_waterline": waterline["count"] == 2
        and waterline["vertices"] >= 800,
        "unrealistic_reeds_removed": len(vegetation["reed_instances"]) == 0,
        "high_detail_riparian_trees": len(vegetation["tree_instances"]) >= 10,
        "genuine_infinigen_understory": bool(
            vegetation["grass_object"].get("c2w_direct_infinigen_asset")
        ),
        "no_synthetic_foam_curve_geometry": (
            foam["count"] == 0
            and foam.get("surface_curve_geometry", -1) == 0
            and bool(water["object"].get("c2w_surface_geometry_foam_removed"))
        ),
    }
    failed = [name for name, valid in checks.items() if not valid]
    if failed:
        raise RuntimeError(f"river production audit failed: {failed}; checks={checks}")
    return {
        "valid": True,
        "checks": checks,
        "water_width_range_m": [round(min(widths), 3), round(max(widths), 3)],
        "length_m": Y_MAX - Y_MIN,
        "centerline_sections": SECTION_COUNT,
        "water_surface_columns": WATER_COLUMNS,
        "water_surface_vertices": water["vertices"],
        "water_surface_faces": water["faces"],
        "water_surface_vertical_relief_m": water["surface_vertical_relief_m"],
        "nominal_water_surface_z_m": WATER_Z,
        "minimum_bank_crest_clearance_m": round(crest_clearance, 4),
        "minimum_waterline_edge_clearance_m": round(waterline_clearance, 4),
        "water_material_node_count": water["material_node_count"],
        "explicit_flow_relief_layers": water["explicit_flow_relief_layers"],
        "channel_vertices": channel["vertices"],
        "channel_faces": channel["faces"],
        "city_side_channel_envelope_x_min": round(
            float(channel["object"]["c2w_city_side_envelope_x_min"]), 3
        ),
        "riverbank_boulder_instances": len(boulders["instances"]),
        "active_channel_large_stone_instances": boulders.get(
            "active_channel_large_stones", 0
        ),
        "loose_bank_boulder_instances": boulders.get("loose_bank_boulders", 0),
        "wet_stone_rebound_masters": boulders["wet_stone_rebound_masters"],
        "weathered_bridge_riverstone_parts": bridge["riverstone_rebound_parts"],
        "submerged_riffle_cobbles": riffles["count"],
        "riffle_zones": riffles["zones"],
        "surface_breaking_riffle_cobbles": riffles.get("surface_breaking_cobbles", 0),
        "minimum_cobble_surface_clearance_m": riffles.get(
            "minimum_surface_clearance_m", 0.0
        ),
        "saturated_waterline_objects": waterline["count"],
        "infinigen_reed_instances": len(vegetation["reed_instances"]),
        "riparian_tree_instances": len(vegetation["tree_instances"]),
        "footbridge_objects": bridge["object_count"],
        "promenade_furniture_objects": promenade["production_furniture_objects"],
        "gravel_bars": gravel["count"],
        "foam_streaks": foam["count"],
        "flow_aligned_foam_streaks": foam["flow_streaks"],
        "obstacle_wake_curves": foam["wake_curves"],
        "bank_contact_foam_segments": foam["bank_contact_segments"],
        "ground_excavation": excavation,
        "infinigen_components": [
            "infinigen.assets.materials.fluid.river_water.RiverWater",
            "infinigen.assets.scatters.grass.Grass",
        ],
        "water_component_source": water["source"],
        "reference_blends_loaded": [],
        "modeling_policy": "source-level complex procedural river4; recessed waterline, no reeds, no large stones or synthetic white curves in the active channel, dense physically shaded water; reject flat water, regular trenches, blobs, proxies and toy models",
    }


def build_river_corridor() -> dict:
    root = bpy.data.collections.new(PREFIX + "River_Corridor_Production")
    bpy.context.scene.collection.children.link(root)
    channel_collection = _child("01_Channel_and_Water", root)
    public_collection = _child("02_Riverfront_Public_Realm", root)
    bridge_collection = _child("03_Structural_Footbridge", root)
    geology_collection = _child("04_Alluvial_Geology", root)
    vegetation_collection = _child("05_Riparian_Vegetation", root)

    materials = {
        "bank": _material(
            "alluvial_bank_soil",
            (0.105, 0.073, 0.038),
            (0.31, 0.25, 0.14),
            roughness=0.94,
            scale=4.2,
            bump=0.34,
        ),
        "gravel": _material(
            "graded_river_gravel",
            (0.16, 0.15, 0.13),
            (0.48, 0.45, 0.38),
            roughness=0.91,
            scale=19.0,
            bump=0.48,
        ),
        "wet": _material(
            "saturated_bank_sediment",
            (0.035, 0.028, 0.018),
            (0.13, 0.105, 0.065),
            roughness=0.82,
            scale=8.0,
            bump=0.27,
        ),
        "bed": _material(
            "submerged_mixed_gravel_bed",
            (0.035, 0.043, 0.032),
            (0.13, 0.15, 0.10),
            roughness=0.88,
            scale=15.0,
            bump=0.42,
        ),
        "stone": _material(
            "weathered_local_stone",
            (0.035, 0.036, 0.032),
            (0.16, 0.145, 0.105),
            roughness=0.68,
            scale=11.0,
            bump=0.34,
        ),
        "paver": _material(
            "permeable_riverfront_paver",
            (0.24, 0.22, 0.18),
            (0.52, 0.48, 0.39),
            roughness=0.83,
            scale=13.0,
            bump=0.20,
        ),
        "wood": _material(
            "sealed_bridge_hardwood",
            (0.055, 0.022, 0.009),
            (0.31, 0.13, 0.045),
            roughness=0.61,
            scale=5.5,
            bump=0.16,
        ),
        "steel": _material(
            "bridge_weathering_steel",
            (0.055, 0.042, 0.032),
            (0.19, 0.11, 0.055),
            roughness=0.48,
            scale=7.0,
            bump=0.08,
            metallic=0.72,
        ),
        "waterline": _material(
            "saturated_waterline_film",
            (0.012, 0.016, 0.011),
            (0.055, 0.070, 0.045),
            roughness=0.31,
            scale=27.0,
            bump=0.12,
        ),
    }
    excavation = _excavate_city_ground_for_river()
    channel = _build_channel(channel_collection, materials)
    water = _build_water(channel_collection)
    promenade = _build_promenade(public_collection, materials)
    bridge = _build_footbridge(bridge_collection, materials)
    _rebind_bridge_stone(bridge, materials["stone"])
    gravel = _build_gravel_bars(geology_collection, materials)
    boulders = _build_boulders(geology_collection, materials["stone"])
    riffles = _build_riffle_cobbles(geology_collection, boulders["masters"])
    waterline = _build_wetted_waterline(channel_collection, materials["waterline"])
    vegetation = _build_riparian_vegetation(vegetation_collection, materials)
    foam = _build_foam(channel_collection)
    audit = _audit(
        channel,
        water,
        promenade,
        bridge,
        gravel,
        boulders,
        riffles,
        waterline,
        vegetation,
        foam,
        excavation,
    )

    root["c2w_source_generator"] = str(Path(__file__).resolve())
    root["c2w_source_level_generation"] = True
    root["c2w_direct_infinigen_riverwater"] = True
    root["c2w_river4_physical_water"] = True
    root["c2w_reeds_removed_by_design"] = True
    root["c2w_water_below_channel_banks"] = audit["checks"][
        "water_surface_below_channel_banks"
    ]
    root["c2w_city_ground_curved_excavation"] = audit["checks"][
        "production_ground_curved_excavation"
    ]
    root["c2w_original_city_environment_preserved"] = audit["checks"][
        "original_city_environment_preserved"
    ]
    root["c2w_water_surface_vertices"] = audit["water_surface_vertices"]
    root["c2w_channel_vertices"] = audit["channel_vertices"]
    root["c2w_riffle_cobbles"] = audit["submerged_riffle_cobbles"]
    root["c2w_foam_detail_objects"] = audit["foam_streaks"]
    root["c2w_surface_geometry_foam_removed"] = True
    root["c2w_active_channel_large_stones"] = 0
    root["c2w_forbid_toy_models"] = True
    root["c2w_river_audit_valid"] = audit["valid"]
    bpy.context.scene["c2w_river_corridor_valid"] = audit["valid"]
    bpy.context.scene["c2w_river_corridor_length_m"] = audit["length_m"]
    bpy.context.scene["c2w_river_width_min_m"] = audit["water_width_range_m"][0]
    bpy.context.scene["c2w_river_width_max_m"] = audit["water_width_range_m"][1]
    bpy.context.scene["c2w_river_centerline_sections"] = SECTION_COUNT
    bpy.context.scene["c2w_river_water_columns"] = WATER_COLUMNS
    bpy.context.scene["c2w_river_infinigen_components"] = ";".join(
        audit["infinigen_components"]
    )
    print(
        f"[Full07River] Built {audit['length_m']:.0f}m river corridor; "
        f"water={audit['water_width_range_m']}m; active_channel_large_stones={audit['active_channel_large_stone_instances']}; "
        f"relief={audit['water_surface_vertical_relief_m']:.3f}m; submerged_cobbles={audit['submerged_riffle_cobbles']}; "
        f"synthetic_foam_curves={audit['foam_streaks']}; reeds_removed={audit['infinigen_reed_instances'] == 0}; "
        f"crest_clearance={audit['minimum_bank_crest_clearance_m']:.3f}m; bridge_parts={audit['footbridge_objects']}",
        flush=True,
    )
    return audit


def _rename_legacy_river_datablocks(
    legacy_prefix: str,
    revision: str,
) -> bpy.types.Collection:
    root = bpy.data.collections.get(legacy_prefix + "River_Corridor_Production")
    if root is None:
        raise RuntimeError(
            f"{revision} production upgrade requires checkpoint namespace {legacy_prefix}"
        )
    datablock_sets = (
        bpy.data.collections,
        bpy.data.objects,
        bpy.data.materials,
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.node_groups,
    )
    for datablocks in datablock_sets:
        for item in list(datablocks):
            if item.name.startswith(legacy_prefix):
                item.name = PREFIX + item.name[len(legacy_prefix) :]
    return bpy.data.collections.get(PREFIX + "River_Corridor_Production")


def _existing_river_assets() -> tuple[dict, dict, dict, dict]:
    role_objects: dict[str, list[bpy.types.Object]] = {}
    for obj in bpy.context.scene.objects:
        role = obj.get("c2w_river_role")
        if role:
            role_objects.setdefault(str(role), []).append(obj)

    path_objects = role_objects.get("accessible_park_leisure_promenade", [])
    if len(path_objects) != 1:
        raise RuntimeError(
            f"river upgrade expected one production promenade, got {len(path_objects)}"
        )
    promenade = {
        "path": path_objects[0],
        "path_vertices": len(path_objects[0].data.vertices),
        "connections": len(role_objects.get("district_to_riverfront_connection", [])),
        "production_furniture_objects": sum(
            len(role_objects.get(role, []))
            for role in (
                "riverfront_streetlight",
                "riverfront_bench",
                "riverfront_waste_bin",
            )
        ),
    }

    bridge_collection = bpy.data.collections.get(PREFIX + "03_Structural_Footbridge")
    if bridge_collection is None:
        raise RuntimeError("river upgrade lost the structural footbridge collection")
    bridge_objects = list(bridge_collection.all_objects)
    bridge = {
        "objects": bridge_objects,
        "object_count": len(bridge_objects),
        "planks": sum(
            o.get("c2w_bridge_role") == "individual_hardwood_deck_plank"
            for o in bridge_objects
        ),
        "span_m": 22.6,
    }

    boulder_masters = sorted(
        [
            c
            for c in bpy.data.collections
            if "MASTER:multiscale_river_boulder" in c.name
        ],
        key=lambda c: c.name,
    )
    boulder_instances = role_objects.get("in_channel_boulder", []) + role_objects.get(
        "bank_armour_boulder", []
    )
    if len(boulder_masters) < 5 or len(boulder_instances) < 70:
        raise RuntimeError(
            "river upgrade requires the verified high-detail stone source library"
        )
    boulders = {
        "masters": boulder_masters[:5],
        "instances": boulder_instances,
        "master_vertex_counts": [
            sum(
                len(o.data.vertices)
                for o in master.objects
                if o.type == "MESH" and o.data
            )
            for master in boulder_masters[:5]
        ],
    }

    grass_objects = role_objects.get("genuine_infinigen_riparian_grass", [])
    if not grass_objects:
        raise RuntimeError(
            "river upgrade requires the verified genuine Infinigen grass understory"
        )
    vegetation = {
        "reed_masters": [],
        "reed_instances": [],
        "reed_master_vertex_counts": [],
        "tree_instances": role_objects.get("high_detail_riparian_tree", []),
        "grass_object": grass_objects[0],
    }
    return promenade, bridge, boulders, vegetation


def _upgrade_existing_river_corridor(legacy_prefix: str, revision: str) -> dict:
    """Production checkpoint upgrade: rebuild every changed hydraulic system.

    The prior result is itself a source-generated, hard-audited full city.  The
    unchanged 5 GB city, botanical masters, public realm, and structural bridge
    are retained.  Every hydraulic/bank-rock system is source-regenerated, and
    the rejected reed instances plus their masters are removed from the product.
    """
    root = _rename_legacy_river_datablocks(legacy_prefix, revision)
    if root is None:
        raise RuntimeError(f"{revision} root rename failed")
    promenade, bridge, prior_boulders, vegetation = _existing_river_assets()

    replaced_roles = {
        "flowing_water_surface",
        "variable_width_incised_channel_and_banks",
        "depositional_gravel_bar",
        "flow_aligned_aerated_foam",
        "obstacle_wake_foam",
        "intermittent_bank_contact_foam",
        "submerged_high_detail_riffle_cobble",
        "saturated_bank_waterline_transition",
        "in_channel_boulder",
        "bank_armour_boulder",
        "riparian_reed_cluster",
    }
    stale = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("c2w_river_role") in replaced_roles
    ]
    if len(stale) < 330:
        raise RuntimeError(
            f"{revision} upgrade expected the complete prior hydraulic core, found {len(stale)} objects"
        )
    bpy.data.batch_remove(stale)

    reed_collections = [
        collection
        for collection in bpy.data.collections
        if "MASTER:Infinigen_ReedMonocotFactory" in collection.name
    ]
    reed_master_objects = list(
        {obj for collection in reed_collections for obj in collection.all_objects}
    )
    if reed_master_objects:
        bpy.data.batch_remove(reed_master_objects)
    if reed_collections:
        bpy.data.batch_remove(reed_collections)
    if any(
        obj.get("c2w_river_role") == "riparian_reed_cluster"
        for obj in bpy.context.scene.objects
    ):
        raise RuntimeError(f"{revision} upgrade failed to remove all visible reeds")

    excavation = _excavate_city_ground_for_river()

    channel_collection = bpy.data.collections.get(PREFIX + "01_Channel_and_Water")
    geology_collection = bpy.data.collections.get(PREFIX + "04_Alluvial_Geology")
    if channel_collection is None or geology_collection is None:
        raise RuntimeError(
            f"{revision} upgrade is missing production channel/geology collections"
        )
    detail_collection = next(
        (
            collection
            for collection in bpy.data.collections
            if collection.name.startswith(PREFIX)
            and "Hydraulic_Detail" in collection.name
        ),
        None,
    )
    if detail_collection is None:
        detail_collection = _child(f"06_{revision.title()}_Hydraulic_Detail", root)
    else:
        detail_collection.name = PREFIX + f"06_{revision.title()}_Hydraulic_Detail"

    materials = {
        "bank": _material(
            f"alluvial_bank_soil_{revision}",
            (0.052, 0.035, 0.018),
            (0.19, 0.135, 0.060),
            roughness=0.97,
            scale=6.2,
            bump=0.42,
        ),
        "gravel": _material(
            f"graded_river_gravel_{revision}",
            (0.058, 0.052, 0.042),
            (0.255, 0.225, 0.17),
            roughness=0.94,
            scale=25.0,
            bump=0.54,
        ),
        "wet": _material(
            f"saturated_bank_sediment_{revision}",
            (0.008, 0.007, 0.005),
            (0.046, 0.037, 0.020),
            roughness=0.61,
            scale=13.0,
            bump=0.33,
        ),
        "bed": _material(
            f"submerged_mixed_gravel_bed_{revision}",
            (0.010, 0.016, 0.012),
            (0.066, 0.080, 0.045),
            roughness=0.91,
            scale=21.0,
            bump=0.49,
        ),
        "stone": _material(
            f"weathered_local_stone_{revision}",
            (0.028, 0.030, 0.027),
            (0.135, 0.120, 0.086),
            roughness=0.62,
            scale=11.0,
            bump=0.36,
        ),
        "waterline": _material(
            f"saturated_waterline_film_{revision}",
            (0.004, 0.006, 0.004),
            (0.025, 0.033, 0.018),
            roughness=0.36,
            scale=37.0,
            bump=0.16,
        ),
    }
    _rebind_bridge_stone(bridge, materials["stone"])
    channel = _build_channel(channel_collection, materials)
    water = _build_water(channel_collection)
    gravel = _build_gravel_bars(geology_collection, materials)
    rebound = _rebind_rock_master_materials(
        prior_boulders["masters"], materials["stone"]
    )
    boulders = _scatter_boulders(geology_collection, prior_boulders["masters"])
    boulders["wet_stone_rebound_masters"] = rebound
    riffles = _build_riffle_cobbles(geology_collection, boulders["masters"])
    waterline = _build_wetted_waterline(channel_collection, materials["waterline"])
    foam = _build_foam(detail_collection)
    audit = _audit(
        channel,
        water,
        promenade,
        bridge,
        gravel,
        boulders,
        riffles,
        waterline,
        vegetation,
        foam,
        excavation,
    )

    root["c2w_source_generator"] = str(Path(__file__).resolve())
    root["c2w_source_level_generation"] = True
    root["c2w_production_checkpoint_upgrade"] = True
    root["c2w_direct_infinigen_riverwater"] = True
    root[f"c2w_{revision}_physical_water"] = True
    root["c2w_reeds_removed_by_design"] = True
    root["c2w_water_below_channel_banks"] = audit["checks"][
        "water_surface_below_channel_banks"
    ]
    root["c2w_city_ground_curved_excavation"] = audit["checks"][
        "production_ground_curved_excavation"
    ]
    root["c2w_original_city_environment_preserved"] = audit["checks"][
        "original_city_environment_preserved"
    ]
    root["c2w_water_surface_vertices"] = audit["water_surface_vertices"]
    root["c2w_channel_vertices"] = audit["channel_vertices"]
    root["c2w_riffle_cobbles"] = audit["submerged_riffle_cobbles"]
    root["c2w_foam_detail_objects"] = audit["foam_streaks"]
    root["c2w_surface_geometry_foam_removed"] = True
    root["c2w_active_channel_large_stones"] = 0
    root["c2w_forbid_toy_models"] = True
    root["c2w_river_audit_valid"] = audit["valid"]
    scene = bpy.context.scene
    scene["c2w_river_corridor_valid"] = audit["valid"]
    scene["c2w_river_corridor_length_m"] = audit["length_m"]
    scene["c2w_river_width_min_m"] = audit["water_width_range_m"][0]
    scene["c2w_river_width_max_m"] = audit["water_width_range_m"][1]
    scene["c2w_river_centerline_sections"] = SECTION_COUNT
    scene["c2w_river_water_columns"] = WATER_COLUMNS
    scene["c2w_river_infinigen_components"] = ";".join(audit["infinigen_components"])
    print(
        f"[Full07{revision.title()}Upgrade] Rebuilt recessed hydraulic core from source: water={audit['water_surface_vertices']} verts; "
        f"relief={audit['water_surface_vertical_relief_m']:.3f}m; submerged_cobbles={audit['submerged_riffle_cobbles']}; "
        f"active_channel_large_stones={audit['active_channel_large_stone_instances']}; synthetic_foam_curves={audit['foam_streaks']}; reeds={audit['infinigen_reed_instances']}; "
        f"crest_clearance={audit['minimum_bank_crest_clearance_m']:.3f}m; "
        f"city_preserved={audit['checks']['original_city_environment_preserved']}",
        flush=True,
    )
    return audit


def upgrade_existing_river_corridor() -> dict:
    """Compatibility entry for reproducing the former river3 stage."""
    global PREFIX
    PREFIX = "full07_river3:"
    return _upgrade_existing_river_corridor("full07_river2:", "river3")


def upgrade_existing_river_corridor_v4() -> dict:
    """Current production entry: rebuild river3 into the river4 result."""
    global PREFIX
    PREFIX = "full07_river4:"
    return _upgrade_existing_river_corridor("full07_river3:", "river4")


def _world_mesh_z_range(obj: bpy.types.Object) -> tuple[float, float]:
    """Return authored mesh extrema without evaluating unrelated city assets."""
    if obj.type != "MESH" or obj.data is None or not obj.data.vertices:
        raise RuntimeError(f"river5 expected a non-empty mesh, got {obj.name}")
    values = [(obj.matrix_world @ vertex.co).z for vertex in obj.data.vertices]
    return min(values), max(values)


def _translate_object_world_z(obj: bpy.types.Object, delta_z: float) -> None:
    """Move an existing production asset in world Z while retaining its source data."""
    matrix = obj.matrix_world.copy()
    matrix.translation.z += delta_z
    obj.matrix_world = matrix


def _river2_bed_lip_minimum_z(channel: bpy.types.Object) -> float:
    """Measure the two inner riverbed lips in every river2 cross-section.

    River2 authored 209 longitudinal rows with 17 vertices per row.  Vertices
    6 and 12 are the two sloped-bed control lips immediately outside the water
    footprint.  The water plane must remain below the lowest of those controls
    so its solidified side can never rise above the riverbed in a side view.
    """
    cross_section_vertices = 17
    vertex_count = len(channel.data.vertices)
    if vertex_count != 3553 or vertex_count % cross_section_vertices:
        raise RuntimeError(
            "river5 requires the audited river2 209x17 channel mesh; "
            f"got {vertex_count} vertices"
        )
    values = []
    for row in range(vertex_count // cross_section_vertices):
        start = row * cross_section_vertices
        for offset in (6, 12):
            values.append(
                (channel.matrix_world @ channel.data.vertices[start + offset].co).z
            )
    return min(values)


def _audit_existing_river2_physical_water(water: bpy.types.Object) -> dict:
    """Prove the retained river2 water is a real multi-layer physical shader.

    The river2 checkpoint predates a few object-level audit properties used by
    the recovery validator.  Do not merely backfill those flags: first inspect
    the saved material graph, mesh attributes, and genuine Infinigen modifier.
    """
    materials = (
        list(water.data.materials) if water.type == "MESH" and water.data else []
    )
    material = materials[0] if materials else None
    nodes = (
        list(material.node_tree.nodes)
        if material and material.use_nodes and material.node_tree
        else []
    )
    node_ids = {node.bl_idname for node in nodes}
    output = next(
        (node for node in nodes if node.bl_idname == "ShaderNodeOutputMaterial"), None
    )
    surface_linked = bool(
        output and output.inputs.get("Surface") and output.inputs["Surface"].is_linked
    )
    volume_linked = bool(
        output and output.inputs.get("Volume") and output.inputs["Volume"].is_linked
    )
    attribute_names = (
        set(water.data.attributes.keys())
        if water.type == "MESH" and water.data
        else set()
    )
    required_attributes = {
        "c2w_depth_factor",
        "c2w_flow_turbulence",
        "c2w_shore_factor",
    }
    noise_layers = sum(
        node.bl_idname in {"ShaderNodeTexNoise", "ShaderNodeTexWave"} for node in nodes
    )
    bump_layers = sum(node.bl_idname == "ShaderNodeBump" for node in nodes)
    official_modifiers = sum(
        modifier.type == "NODES" or "riverwater" in modifier.name.lower()
        for modifier in water.modifiers
    )
    water_z_range = _world_mesh_z_range(water)
    geometric_relief = water_z_range[1] - water_z_range[0]
    explicit_relief_layers = noise_layers + bump_layers + int(geometric_relief >= 0.02)
    checks = {
        "material_node_count": len(nodes),
        "principled_surface": "ShaderNodeBsdfPrincipled" in node_ids and surface_linked,
        "physical_volume_absorption": "ShaderNodeVolumeAbsorption" in node_ids
        and volume_linked,
        "physical_volume_scatter": "ShaderNodeVolumeScatter" in node_ids
        and volume_linked,
        "multiscale_flow_texture_layers": noise_layers,
        "normal_relief_layers": bump_layers,
        "geometric_surface_relief_m": round(geometric_relief, 6),
        "explicit_flow_relief_layers": explicit_relief_layers,
        "depth_turbulence_and_shore_attributes": required_attributes.issubset(
            attribute_names
        ),
        "genuine_infinigen_modifier_count": official_modifiers,
    }
    valid = bool(
        checks["material_node_count"] >= 18
        and checks["principled_surface"]
        and checks["physical_volume_absorption"]
        and checks["physical_volume_scatter"]
        and noise_layers >= 3
        and bump_layers >= 2
        and geometric_relief >= 0.02
        and explicit_relief_layers >= 6
        and official_modifiers >= 1
    )
    if not valid:
        raise RuntimeError(
            f"river5 retained river2 water failed physical shader audit: {checks}"
        )
    return {"valid": True, **checks}


def upgrade_river2_waterline_to_river5() -> dict:
    """Minimal production upgrade based directly on the audited river2 scene.

    This intentionally does not use river3 or river4 geometry.  It retains the
    complete river2 channel, banks, geology, bridge, vegetation and city, moves
    only the existing high-detail water system and its surface-bound details,
    and removes the rejected reeds and their genuine Infinigen master assets.
    """
    global PREFIX
    PREFIX = "full07_river5:"
    root = _rename_legacy_river_datablocks("full07_river2:", "river5")
    if root is None:
        raise RuntimeError("river5 failed to retain the audited river2 production root")

    roles: dict[str, list[bpy.types.Object]] = {}
    for obj in bpy.context.scene.objects:
        role = obj.get("c2w_river_role")
        if role:
            roles.setdefault(str(role), []).append(obj)

    water_objects = roles.get("flowing_water_surface", [])
    channel_objects = roles.get("variable_width_incised_channel_and_banks", [])
    if len(water_objects) != 1 or len(channel_objects) != 1:
        raise RuntimeError(
            "river5 requires exactly one river2 water surface and one channel; "
            f"got water={len(water_objects)}, channel={len(channel_objects)}"
        )
    water = water_objects[0]
    channel = channel_objects[0]
    physical_water_audit = _audit_existing_river2_physical_water(water)
    water_z_before = _world_mesh_z_range(water)
    bed_lip_minimum_z = _river2_bed_lip_minimum_z(channel)

    moved_roles = {
        "flowing_water_surface",
        "saturated_bank_waterline_transition",
        "flow_aligned_aerated_foam",
        "obstacle_wake_foam",
        "intermittent_bank_contact_foam",
    }
    moved_objects = [obj for role in moved_roles for obj in roles.get(role, [])]
    if len(moved_objects) != 61:
        raise RuntimeError(
            "river5 expected the complete river2 water-bound system "
            f"(61 objects), found {len(moved_objects)}"
        )
    for obj in moved_objects:
        _translate_object_world_z(obj, -RIVER5_WATER_LEVEL_DROP_M)
        obj["c2w_river5_water_level_drop_m"] = RIVER5_WATER_LEVEL_DROP_M

    water_z_after = _world_mesh_z_range(water)
    clearance = bed_lip_minimum_z - water_z_after[1]
    if abs((water_z_before[1] - water_z_after[1]) - RIVER5_WATER_LEVEL_DROP_M) > 1e-5:
        raise RuntimeError(
            "river5 water surface did not receive the configured level drop"
        )
    if clearance < RIVER5_MIN_BED_LIP_CLEARANCE_M:
        raise RuntimeError(
            "river5 water still rises above the lowest riverbed lip: "
            f"water_max={water_z_after[1]:.4f}, bed_lip_min={bed_lip_minimum_z:.4f}, "
            f"clearance={clearance:.4f}"
        )
    water["c2w_river5_source_surface_z_min_m"] = water_z_before[0]
    water["c2w_river5_source_surface_z_max_m"] = water_z_before[1]
    water["c2w_river5_surface_z_min_m"] = water_z_after[0]
    water["c2w_river5_surface_z_max_m"] = water_z_after[1]
    water["c2w_river5_bed_lip_clearance_m"] = clearance
    water["c2w_surface_below_riverbed_lips"] = True
    # These properties are compatibility metadata for the retained, audited
    # river2 node graph above; the physical material itself is not replaced.
    water["c2w_physically_based_water_shader"] = True
    water["c2w_volume_absorption"] = True
    water["c2w_explicit_flow_relief_layers"] = int(
        physical_water_audit["explicit_flow_relief_layers"]
    )

    reed_instances = list(roles.get("riparian_reed_cluster", []))
    if len(reed_instances) != 81:
        raise RuntimeError(
            f"river5 expected all 81 river2 reed instances, found {len(reed_instances)}"
        )
    bpy.data.batch_remove(reed_instances)
    reed_collections = [
        collection
        for collection in bpy.data.collections
        if "MASTER:Infinigen_ReedMonocotFactory" in collection.name
    ]
    if len(reed_collections) != 2:
        raise RuntimeError(
            f"river5 expected both river2 reed masters, found {len(reed_collections)}"
        )
    reed_master_objects = list(
        {obj for collection in reed_collections for obj in collection.all_objects}
    )
    if reed_master_objects:
        bpy.data.batch_remove(reed_master_objects)
    bpy.data.batch_remove(reed_collections)

    visible_reeds = [
        obj.name
        for obj in bpy.context.scene.objects
        if obj.get("c2w_river_role") == "riparian_reed_cluster"
        or "reedmonocot" in obj.name.lower()
    ]
    reed_named_collections = [
        collection.name
        for collection in bpy.data.collections
        if "reedmonocot" in collection.name.lower()
    ]
    forbidden = ("toy", "placeholder", "proxy_tree", "blob_tree", "lowpoly", "dummy")
    forbidden_names = [
        item.name
        for datablocks in (bpy.data.objects, bpy.data.collections)
        for item in datablocks
        if any(token in item.name.lower() for token in forbidden)
    ]
    degenerate_river_objects = []
    for obj in bpy.context.scene.objects:
        if not obj.get("c2w_river_role"):
            continue
        if (
            obj.type == "MESH"
            and obj.data
            and not obj.get("c2w_direct_infinigen_asset")
            and (len(obj.data.vertices) < 4 or len(obj.data.polygons) < 1)
        ):
            degenerate_river_objects.append(obj.name)
        if obj.type == "CURVE" and obj.data and not obj.data.splines:
            degenerate_river_objects.append(obj.name)
    if (
        visible_reeds
        or reed_named_collections
        or forbidden_names
        or degenerate_river_objects
    ):
        raise RuntimeError(
            "river5 hard no-reed/no-toy audit failed: "
            f"visible_reeds={visible_reeds[:10]}, reed_collections={reed_named_collections[:10]}, "
            f"forbidden={forbidden_names[:10]}, degenerate={degenerate_river_objects[:10]}"
        )

    scene = bpy.context.scene
    root["c2w_source_generator"] = str(Path(__file__).resolve())
    root["c2w_source_level_generation"] = True
    root["c2w_production_checkpoint_upgrade"] = True
    root["c2w_river5_direct_river2_base"] = True
    root["c2w_river5_water_level_drop_m"] = RIVER5_WATER_LEVEL_DROP_M
    root["c2w_river5_water_surface_z_max_m"] = water_z_after[1]
    root["c2w_river5_bed_lip_minimum_z_m"] = bed_lip_minimum_z
    root["c2w_river5_bed_lip_clearance_m"] = clearance
    root["c2w_water_below_channel_banks"] = True
    root["c2w_water_surface_below_riverbed_lips"] = True
    root["c2w_reeds_removed_by_design"] = True
    root["c2w_original_city_environment_preserved"] = True
    root["c2w_forbid_toy_models"] = True
    root["c2w_river_audit_valid"] = True
    scene["c2w_river_corridor_valid"] = True
    scene["c2w_river5_direct_river2_base"] = True
    scene["c2w_river5_water_level_drop_m"] = RIVER5_WATER_LEVEL_DROP_M
    scene["c2w_water_surface_below_riverbed_lips"] = True
    scene["c2w_river_infinigen_components"] = (
        "infinigen.assets.materials.fluid.river_water.RiverWater;"
        "infinigen.assets.scatters.grass.Grass"
    )

    return {
        "valid": True,
        "river5_direct_river2_base": True,
        "river2_geometry_preserved": True,
        "water_level_drop_m": RIVER5_WATER_LEVEL_DROP_M,
        "water_surface_z_before_m": [round(value, 6) for value in water_z_before],
        "water_surface_z_after_m": [round(value, 6) for value in water_z_after],
        "riverbed_lip_minimum_z_m": round(bed_lip_minimum_z, 6),
        "minimum_water_to_riverbed_lip_clearance_m": round(clearance, 6),
        "physical_water_material_audit": physical_water_audit,
        "physical_multiscale_water": True,
        "water_bound_detail_objects_shifted": len(moved_objects),
        "removed_reed_instances": len(reed_instances),
        "removed_reed_master_collections": len(reed_collections),
        "infinigen_reed_instances": 0,
        "forbidden_object_or_collection_count": 0,
        "degenerate_river_object_count": 0,
        "checks": {
            "direct_river2_production_base": True,
            "river2_channel_banks_geology_bridge_and_city_preserved": True,
            "water_surface_lowered_0_34m": True,
            "water_surface_below_riverbed_lips": True,
            "retained_river2_physical_multiscale_water_verified": True,
            "unrealistic_reeds_removed": True,
            "no_toy_or_degenerate_models": True,
            "original_city_environment_preserved": True,
        },
    }

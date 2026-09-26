"""Focused realism pass for the existing all43_06 commercial zone."""
import math, random
import bpy

P = "all43_07:"


def mat(name, color, rough=0.5, metal=0, emit=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit:
        b.inputs["Emission Color"].default_value = color
        b.inputs["Emission Strength"].default_value = emit
    tex = n.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 7
    tex.inputs["Detail"].default_value = 3
    tex.inputs["Roughness"].default_value = 0.45
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.045
    bump.inputs["Distance"].default_value = 0.012
    l.new(tex.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def glass_material():
    m = mat("fresnel_commercial_glass", (0.035, 0.065, 0.06, 0.10), 0.075)
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    b.inputs["Transmission Weight"].default_value = 1
    b.inputs["IOR"].default_value = 1.46
    out = n.get("Material Output")
    [l.remove(x) for x in list(out.inputs["Surface"].links)]
    transparent = n.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (0.94, 0.98, 0.97, 1)
    mix = n.new("ShaderNodeMixShader")
    mix.inputs[0].default_value = 0.16
    l.new(transparent.outputs[0], mix.inputs[1])
    l.new(b.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    m.surface_render_method = "DITHERED"
    return m


def cube():
    m = bpy.data.meshes.get(P + "shared_cube")
    if m:
        return m
    v = [
        (-0.5, -0.5, -0.5),
        (0.5, -0.5, -0.5),
        (0.5, 0.5, -0.5),
        (-0.5, 0.5, -0.5),
        (-0.5, -0.5, 0.5),
        (0.5, -0.5, 0.5),
        (0.5, 0.5, 0.5),
        (-0.5, 0.5, 0.5),
    ]
    f = [
        (0, 1, 2, 3),
        (4, 7, 6, 5),
        (0, 4, 5, 1),
        (1, 5, 6, 2),
        (2, 6, 7, 3),
        (4, 0, 3, 7),
    ]
    m = bpy.data.meshes.new(P + "shared_cube")
    m.from_pydata(v, [], f)
    return m


def box(c, n, loc, size, M, bevel=0.012, rot=0):
    o = bpy.data.objects.new(P + n, cube())
    c.objects.link(o)
    o.location = loc
    o.scale = size
    o.rotation_euler[2] = rot
    if not o.data.materials:
        o.data.materials.append(M)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
    if bevel:
        q = o.modifiers.new("scale_bevel", "BEVEL")
        q.width = min(bevel, min(size) * 0.12)
        q.segments = 3
    o["shared_mesh_data"] = True
    return o


def master(n):
    c = bpy.data.collections.new(P + "MASTER:" + n)
    c["high_quality_master"] = True
    return c


def inst(c, m, n, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + n, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = m
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def shared_materials():
    return {
        "glass": glass_material(),
        "metal": mat("anodized_metal", (0.06, 0.07, 0.072, 1), 0.27, 0.72),
        "paint": mat("painted_metal", (0.22, 0.23, 0.21, 1), 0.42, 0.32),
        "concrete": mat("architectural_concrete", (0.42, 0.41, 0.38, 1), 0.82),
        "asphalt": mat("asphalt", (0.035, 0.038, 0.039, 1), 0.93),
        "line": mat("aged_line", (0.72, 0.69, 0.54, 1), 0.72),
        "dark": mat("service_dark", (0.025, 0.028, 0.027, 1), 0.72),
        "warm": mat("wall_light", (1, 0.58, 0.24, 1), 0.28, emit=2.5),
        "product1": mat("product_blue", (0.04, 0.18, 0.35, 1), 0.5),
        "product2": mat("product_orange", (0.52, 0.16, 0.025, 1), 0.52),
        "shelf": mat("shelf", (0.54, 0.56, 0.53, 1), 0.48),
    }


def create_shelf_variant(M, variant):
    c = master("shelf_variant_" + str(variant))
    length = (1.45, 1.70, 1.30)[variant]
    levels = (5, 6, 4)[variant]
    box(c, "back", (0, 0.18, 1.0), (length, 0.04, 2.0), M["shelf"])
    for j in range(levels + 1):
        box(
            c,
            "board",
            (0, 0, 0.12 + j * (1.78 / levels)),
            (length + 0.06, 0.32, 0.026),
            M["metal"],
            0.004,
        )
    rng = random.Random(700 + variant)
    for j in range(levels):
        for i in range(8):
            if rng.random() < (0.18 + 0.07 * variant):
                continue
            x = -length * 0.82 + i * (length * 1.64 / 7)
            box(
                c,
                "product",
                (x, -0.18, 0.27 + j * (1.78 / levels)),
                (0.10 + rng.random() * 0.035, 0.11, 0.11 + rng.random() * 0.05),
                M["product1"] if rng.random() < 0.5 else M["product2"],
                0.01,
            )
    return c


def upgrade_glazing(M):
    changed = []
    for o in bpy.data.objects:
        if o.get("commercial_transparent_glazing"):
            for s in o.material_slots:
                s.link = "OBJECT"
                s.material = M["glass"]
            solid = o.modifiers.get("glass_thickness") or o.modifiers.new(
                "glass_thickness", "SOLIDIFY"
            )
            solid.thickness = 0.006
            solid.offset = 0
            bevel = o.modifiers.get("glass_edge_bevel") or o.modifiers.new(
                "glass_edge_bevel", "BEVEL"
            )
            bevel.width = 0.004
            bevel.segments = 2
            changed.append(o.name)
    return changed


def diversify_shelves(M):
    variants = [create_shelf_variant(M, i) for i in range(3)]
    changed = []
    instances = [
        o for o in bpy.data.objects if o.name.startswith("all43_06:retail_shelf_")
    ]
    placements = [
        (-4.7, -1.7, 0.12, math.pi / 2, (0.94, 1, 1)),
        (-2.3, -0.55, 0.12, math.pi / 2, (1.03, 1, 1)),
        (0.1, -1.45, 0.12, math.pi / 2, (0.98, 1, 1)),
        (2.5, -0.25, 0.12, math.pi / 2, (1.06, 1, 1)),
    ]
    for i, o in enumerate(instances):
        o.instance_collection = variants[i % 3]
        o.location = placements[i % len(placements)][:3]
        o.rotation_euler[2] = placements[i % len(placements)][3]
        o.scale = placements[i % len(placements)][4]
        changed.append(o.name)
    return variants, changed


def organize_restaurant():
    tables = sorted(
        [o for o in bpy.data.objects if o.name.startswith("all43_06:dining_table_")],
        key=lambda o: o.name,
    )
    chairs = sorted(
        [o for o in bpy.data.objects if o.name.startswith("all43_06:dining_chair_")],
        key=lambda o: o.name,
    )
    layout = [
        (-4.4, -2.1, 0.12, 0.08),
        (-1.8, -2.35, 0.12, -0.05),
        (1.0, -1.9, 0.12, 0.12),
        (-3.5, 0.65, 0.12, -0.10),
        (-0.5, 0.80, 0.12, 0.06),
        (2.2, 0.35, 0.12, -0.08),
    ]
    for i, o in enumerate(tables):
        x, y, z, r = layout[i % len(layout)]
        o.location = (x, y, z)
        o.rotation_euler[2] = r
    for i, o in enumerate(chairs):
        ti = i // 2
        x, y, z, r = layout[ti % len(layout)]
        side = -1 if i % 2 == 0 else 1
        o.location = (x + side * 0.72 * math.sin(r), y + side * 0.72 * math.cos(r), z)
        o.rotation_euler[2] = r + (0 if side < 0 else math.pi)
    counters = [
        o for o in bpy.data.objects if o.name.startswith("all43_06:service_counter")
    ]
    for o in counters:
        o.location = (4.35, 1.8, 0.12)
        o.rotation_euler[2] = math.pi
    return len(tables) + len(chairs) + len(counters)


def hard_surface_pass():
    terms = (
        "frame",
        "jamb",
        "rail",
        "sill",
        "threshold",
        "awning",
        "gutter",
        "flashing",
        "wheelstop",
        "curb",
        "bollard",
    )
    count = 0
    for o in bpy.data.objects:
        if o.type != "MESH" or not any(t in o.name.lower() for t in terms):
            continue
        if not o.modifiers.get("07_real_edge_bevel"):
            q = o.modifiers.new("07_real_edge_bevel", "BEVEL")
            q.width = max(
                0.002, min(0.025, min(max(abs(v), 0.001) for v in o.dimensions) * 0.025)
            )
            q.segments = 2
            count += 1
    return count


def material_realism_pass():
    changed = []
    for m in bpy.data.materials:
        if not m.use_nodes or not any(
            k in m.name.lower()
            for k in ("wall", "stucco", "green", "orange", "terracotta", "facade")
        ):
            continue
        n = m.node_tree.nodes
        l = m.node_tree.links
        b = n.get("Principled BSDF")
        if not b:
            continue
        tex = n.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = 5
        tex.inputs["Detail"].default_value = 2
        bump = n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.035
        bump.inputs["Distance"].default_value = 0.008
        l.new(tex.outputs["Fac"], bump.inputs["Height"])
        l.new(bump.outputs["Normal"], b.inputs["Normal"])
        changed.append(m.name)
    return changed


def create_attachment_masters(M):
    ac = master("AC_unit")
    box(ac, "ac_case", (0, 0, 0.45), (0.72, 0.28, 0.45), M["paint"], 0.035)
    box(ac, "fan_recess", (0, -0.30, 0.46), (0.34, 0.025, 0.32), M["dark"], 0.012)
    for x in (-0.22, 0, 0.22):
        box(ac, "fan_grille", (x, -0.33, 0.46), (0.012, 0.018, 0.29), M["metal"], 0.003)
    hv = master("HVAC_rooftop")
    box(hv, "hvac_case", (0, 0, 0.55), (1.25, 0.85, 0.55), M["paint"], 0.045)
    box(hv, "vent", (0, -0.87, 0.55), (0.82, 0.025, 0.30), M["dark"], 0.008)
    for x in (-0.55, -0.27, 0, 0.27, 0.55):
        box(hv, "louver", (x, -0.90, 0.55), (0.015, 0.02, 0.27), M["metal"], 0.003)
    elec = master("electrical_box")
    box(elec, "cabinet", (0, 0, 0.58), (0.38, 0.18, 0.58), M["paint"], 0.025)
    box(elec, "door", (0, -0.20, 0.58), (0.33, 0.025, 0.50), M["metal"], 0.008)
    box(elec, "lock", (0.22, -0.23, 0.58), (0.02, 0.015, 0.035), M["dark"], 0.003)
    cam = master("security_camera")
    box(cam, "mount", (0, 0, 0.08), (0.10, 0.08, 0.08), M["metal"], 0.018)
    box(cam, "camera", (0, -0.18, 0.04), (0.09, 0.18, 0.07), M["paint"], 0.025)
    box(cam, "lens", (0, -0.37, 0.04), (0.045, 0.015, 0.045), M["dark"], 0.008)
    light = master("wall_pack")
    box(light, "housing", (0, 0, 0.18), (0.28, 0.12, 0.18), M["metal"], 0.025)
    box(light, "lens", (0, -0.14, 0.16), (0.22, 0.025, 0.12), M["warm"], 0.012)
    return {"ac": ac, "hvac": hv, "electrical": elec, "camera": cam, "light": light}


def place_attachments(M):
    masters = create_attachment_masters(M)
    conv = bpy.data.collections["all43_01:MASTER:convenience_store"]
    rest = bpy.data.collections["all43_01:MASTER:restaurant"]
    for c in (conv, rest):
        inst(c, masters["ac"], "side_AC", (7.72, 1.2, 1.5), math.pi / 2)
        inst(c, masters["electrical"], "rear_electrical", (-5.8, 4.55, 0.25), math.pi)
        inst(c, masters["camera"], "security_camera", (6.8, -4.82, 3.45))
        inst(c, masters["light"], "wall_light", (-6.8, -4.82, 3.2))
    # Prompt requests rooftop equipment in small quantities; use one detailed shared HVAC instance per building.
    inst(conv, masters["hvac"], "roof_HVAC", (3.2, 1.3, 5.15), 0.08)
    inst(rest, masters["hvac"], "roof_HVAC", (-2.8, 1.4, 5.15), -0.06)
    return masters


def frontage_and_parking(M):
    root = bpy.data.collections["all43_01:commercial_root"]
    c = bpy.data.collections.new(P + "frontage_realism")
    root.children.link(c)
    box(
        c,
        "entrance_paving",
        (-31, -29.0, 0.20),
        (31.5, 2.5, 0.10),
        M["concrete"],
        0.018,
    )
    box(c, "curb", (-31, -30.38, 0.145), (31.5, 0.24, 0.145), M["concrete"], 0.018)
    box(c, "drain_channel", (-31, -30.18, 0.10), (31.0, 0.18, 0.045), M["metal"], 0.008)
    for i in range(17):
        box(
            c,
            "drain_slot",
            (-46 + i * 1.85, -30.20, 0.15),
            (1.45, 0.022, 0.012),
            M["dark"],
            0.002,
        )
    # Asphalt patches, restrained oil stains and paired tire wear marks.
    for i, (x, y, s) in enumerate(((-29, -35, 2.4), (-20, -39, 1.8), (-14, -34, 1.4))):
        box(
            c,
            "asphalt_patch",
            (x, y, 0.125),
            (s, s * 0.65, 0.012),
            M["asphalt"],
            0.035,
            rot=0.08 * (i - 1),
        )
    oil = mat("oil_stain", (0.012, 0.014, 0.013, 1), 0.38)
    for i, (x, y) in enumerate(((-25, -35.5), (-18, -40.0))):
        box(c, "oil_stain", (x, y, 0.142), (0.75, 0.42, 0.006), oil, 0.08, rot=0.15 * i)
    for x in (-29, -25.7, -22.4, -19.1, -15.8):
        for dx in (-0.72, 0.72):
            box(
                c,
                "tire_mark",
                (x + dx, -34.2, 0.145),
                (0.10, 2.0, 0.004),
                M["dark"],
                0.015,
            )
    return c


def run():
    M = shared_materials()
    glass = upgrade_glazing(M)
    variants, shelves = diversify_shelves(M)
    restaurant = organize_restaurant()
    facade_mats = material_realism_pass()
    bevels = hard_surface_pass()
    attachments = place_attachments(M)
    frontage = frontage_and_parking(M)
    return {
        "materials": M,
        "glass": glass,
        "shelves": shelves,
        "restaurant_objects": restaurant,
        "facade_materials": facade_mats,
        "bevels": bevels,
        "attachment_masters": attachments,
        "frontage": frontage,
    }

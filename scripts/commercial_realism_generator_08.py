"""all43_08: focused storefront, interior, frontage, material and service-detail pass."""
import math, random
import bpy

P = "all43_08:"


def material(name, color, rough=0.5, metallic=0.0, noise_scale=0.0, bump=0.0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get("Principled BSDF")
    bs.inputs["Base Color"].default_value = color
    bs.inputs["Roughness"].default_value = rough
    bs.inputs["Metallic"].default_value = metallic
    if noise_scale:
        tex = n.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = noise_scale
        tex.inputs["Detail"].default_value = 3.0
        tex.inputs["Roughness"].default_value = 0.58
        ramp = n.new("ShaderNodeValToRGB")
        ramp.color_ramp.elements[0].position = 0.28
        ramp.color_ramp.elements[1].position = 0.72
        ramp.color_ramp.elements[0].color = tuple(
            max(0, c * 0.88) for c in color[:3]
        ) + (1,)
        ramp.color_ramp.elements[1].color = tuple(
            min(1, c * 1.10 + 0.008) for c in color[:3]
        ) + (1,)
        l.new(tex.outputs["Fac"], ramp.inputs["Fac"])
        l.new(ramp.outputs["Color"], bs.inputs["Base Color"])
        if bump:
            bn = n.new("ShaderNodeBump")
            bn.inputs["Strength"].default_value = bump
            bn.inputs["Distance"].default_value = 0.025
            l.new(tex.outputs["Fac"], bn.inputs["Height"])
            l.new(bn.outputs["Normal"], bs.inputs["Normal"])
        rm = n.new("ShaderNodeMapRange")
        rm.inputs["From Min"].default_value = 0.15
        rm.inputs["From Max"].default_value = 0.85
        rm.inputs["To Min"].default_value = max(0.02, rough - 0.10)
        rm.inputs["To Max"].default_value = min(1, rough + 0.10)
        l.new(tex.outputs["Fac"], rm.inputs["Value"])
        l.new(rm.outputs["Result"], bs.inputs["Roughness"])
    return m


def glass_material():
    m = material("architectural_glass", (0.018, 0.045, 0.052, 1), 0.105)
    n, l = m.node_tree.nodes, m.node_tree.links
    bs = n.get("Principled BSDF")
    bs.inputs["Transmission Weight"].default_value = 1.0
    bs.inputs["IOR"].default_value = 1.46
    bs.inputs["Coat Weight"].default_value = 0.24
    bs.inputs["Coat Roughness"].default_value = 0.06
    out = n.get("Material Output")
    [l.remove(x) for x in list(out.inputs["Surface"].links)]
    transparent = n.new("ShaderNodeBsdfTransparent")
    transparent.inputs["Color"].default_value = (0.82, 0.92, 0.91, 1)
    fresnel = n.new("ShaderNodeFresnel")
    fresnel.inputs["IOR"].default_value = 1.46
    ramp = n.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0
    ramp.inputs["From Max"].default_value = 1
    ramp.inputs["To Min"].default_value = 0.18
    ramp.inputs["To Max"].default_value = 0.48
    mix = n.new("ShaderNodeMixShader")
    l.new(fresnel.outputs["Fac"], ramp.inputs["Value"])
    l.new(ramp.outputs["Result"], mix.inputs[0])
    l.new(transparent.outputs[0], mix.inputs[1])
    l.new(bs.outputs[0], mix.inputs[2])
    l.new(mix.outputs[0], out.inputs["Surface"])
    m.surface_render_method = "DITHERED"
    m.use_transparency_overlap = False
    return m


def mesh_cube():
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


def box(c, n, loc, size, mat, bevel=0.012, rot=0):
    o = bpy.data.objects.new(P + n, mesh_cube())
    c.objects.link(o)
    o.location = loc
    o.scale = size
    o.rotation_euler[2] = rot
    o.data.materials.clear()
    o.data.materials.append(mat)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = mat
    if bevel:
        q = o.modifiers.new("real_scale_bevel", "BEVEL")
        q.width = min(bevel, min(size) * 0.18)
        q.segments = 3
    o["shared_mesh_data"] = True
    return o


def master(name):
    c = bpy.data.collections.new(P + "MASTER:" + name)
    c["high_quality_master"] = True
    return c


def instance(c, m, n, loc, rot=0, scale=(1, 1, 1)):
    o = bpy.data.objects.new(P + n, None)
    c.objects.link(o)
    o.instance_type = "COLLECTION"
    o.instance_collection = m
    o.location = loc
    o.rotation_euler[2] = rot
    o.scale = scale
    o["linked_collection_instance"] = True
    return o


def materials():
    return dict(
        glass=glass_material(),
        frame=material(
            "anodized_frame", (0.035, 0.045, 0.048, 1), 0.24, 0.72, 38, 0.035
        ),
        dark=material("recess_shadow", (0.012, 0.016, 0.017, 1), 0.72),
        sill=material("brushed_sill", (0.18, 0.20, 0.20, 1), 0.31, 0.68, 55, 0.025),
        concrete=material("paving_concrete", (0.39, 0.40, 0.38, 1), 0.78, 0, 24, 0.14),
        curb=material("curb_concrete", (0.47, 0.47, 0.43, 1), 0.82, 0, 31, 0.11),
        asphalt=material(
            "aggregate_asphalt", (0.027, 0.032, 0.034, 1), 0.91, 0, 68, 0.22
        ),
        line=material("worn_line", (0.69, 0.66, 0.51, 1), 0.69, 0, 18, 0.05),
        green=material(
            "green_facade_micro", (0.23, 0.58, 0.38, 1), 0.43, 0.08, 42, 0.07
        ),
        orange=material(
            "orange_facade_micro", (0.78, 0.28, 0.12, 1), 0.46, 0.08, 39, 0.07
        ),
        steel=material("service_steel", (0.20, 0.22, 0.21, 1), 0.39, 0.58, 46, 0.045),
        white=material(
            "interior_warm_white", (0.70, 0.68, 0.60, 1), 0.55, 0, 30, 0.025
        ),
        wood=material("restaurant_wood", (0.24, 0.095, 0.035, 1), 0.40, 0, 12, 0.05),
        product=material("product_color", (0.11, 0.31, 0.43, 1), 0.48, 0, 20, 0.03),
        rubber=material("rubber", (0.018, 0.019, 0.018, 1), 0.67),
        glow=material("lamp_lens", (0.82, 0.57, 0.28, 1), 0.24),
    )


def storefront_bay(M):
    c = master("storefront_bay")
    # Deep wall reveal, robust outer frame, inset inner stop and recessed glass.
    box(c, "recess", (0, 0.055, 1.56), (1.48, 0.08, 1.56), M["dark"], 0.025)
    for x in (-1.42, 1.42):
        box(c, "outer_jamb", (x, -0.09, 1.56), (0.085, 0.105, 1.56), M["frame"], 0.018)
    for z in (0.10, 3.02):
        box(c, "outer_rail", (0, -0.09, z), (1.50, 0.105, 0.085), M["frame"], 0.018)
    for x in (-1.30, 1.30):
        box(c, "inner_stop", (x, -0.19, 1.62), (0.028, 0.035, 1.36), M["frame"], 0.007)
    for z in (0.25, 2.94):
        box(c, "inner_stop", (0, -0.19, z), (1.33, 0.035, 0.028), M["frame"], 0.007)
    box(c, "inset_glass", (0, -0.155, 1.60), (1.295, 0.012, 1.315), M["glass"], 0.003)
    box(c, "metal_spandrel", (0, -0.23, 0.22), (1.31, 0.075, 0.18), M["sill"], 0.012)
    box(c, "projecting_sill", (0, -0.29, 0.405), (1.47, 0.16, 0.045), M["sill"], 0.012)
    return c


def entrance_door(M):
    c = master("storefront_entrance")
    box(c, "door_reveal", (0, 0.06, 1.58), (1.02, 0.08, 1.58), M["dark"], 0.02)
    for x in (-0.96, 0.96):
        box(c, "door_jamb", (x, -0.10, 1.58), (0.085, 0.11, 1.58), M["frame"], 0.018)
    box(c, "door_head", (0, -0.10, 3.08), (1.04, 0.11, 0.085), M["frame"], 0.018)
    for x in (-0.78, 0.78):
        box(c, "leaf_stile", (x, -0.22, 1.58), (0.055, 0.045, 1.42), M["frame"], 0.008)
    for z in (0.18, 2.97):
        box(c, "leaf_rail", (0, -0.22, z), (0.82, 0.045, 0.055), M["frame"], 0.008)
    box(c, "door_glass", (0, -0.19, 1.58), (0.74, 0.012, 1.34), M["glass"], 0.003)
    box(c, "threshold", (0, -0.34, 0.075), (1.08, 0.27, 0.055), M["sill"], 0.012)
    box(c, "pull_handle", (0.56, -0.31, 1.53), (0.025, 0.035, 0.34), M["steel"], 0.012)
    box(c, "handle_mount", (0.56, -0.30, 1.20), (0.06, 0.04, 0.035), M["steel"], 0.008)
    box(c, "handle_mount", (0.56, -0.30, 1.86), (0.06, 0.04, 0.035), M["steel"], 0.008)
    return c


def install_storefronts(M):
    bay, door = storefront_bay(M), entrance_door(M)
    count = 0
    for cname in ("all43_01:MASTER:convenience_store", "all43_01:MASTER:restaurant"):
        c = bpy.data.collections.get(cname)
        if not c:
            continue
        # The original local facade plane is y=-4.82. Deliberate unequal bay rhythm frames the entrances.
        xs = (-5.65, -2.75, 0.25, 3.15, 5.72)
        for i, x in enumerate(xs):
            instance(
                c,
                bay,
                "storefront_bay",
                (x, -4.93, 0.24),
                scale=(0.89 if i in (0, 4) else 1, 1, 1),
            )
            count += 1
        instance(c, door, "storefront_door", (1.73, -4.95, 0.23))
        count += 1
    return count


def shelf_master(M):
    c = master("retail_shelf_quality")
    box(c, "back", (0, 0.23, 1.0), (1.12, 0.04, 1.0), M["steel"], 0.018)
    for z in (0.10, 0.48, 0.87, 1.28, 1.72):
        box(c, "shelf", (0, 0, z), (1.18, 0.34, 0.025), M["steel"], 0.006)
    rng = random.Random(4308)
    for row, z in enumerate((0.23, 0.61, 1.01, 1.42, 1.84)):
        for i in range(9):
            if rng.random() < 0.18:
                continue
            box(
                c,
                "product",
                (-0.94 + i * 0.235, -0.20, z),
                (0.075, 0.09, 0.10 + rng.random() * 0.045),
                M["product"],
                0.008,
            )
    return c


def table_master(M):
    c = master("restaurant_table")
    box(c, "top", (0, 0, 0.73), (0.66, 0.55, 0.045), M["wood"], 0.035)
    box(c, "pedestal", (0, 0, 0.39), (0.075, 0.075, 0.35), M["steel"], 0.015)
    box(c, "foot", (0, 0, 0.055), (0.34, 0.28, 0.035), M["steel"], 0.018)
    return c


def chair_master(M):
    c = master("restaurant_chair")
    box(c, "seat", (0, 0, 0.46), (0.27, 0.27, 0.035), M["wood"], 0.028)
    box(c, "back", (0, 0.25, 0.78), (0.27, 0.035, 0.31), M["wood"], 0.035)
    for x in (-0.22, 0.22):
        for y in (-0.20, 0.20):
            box(c, "leg", (x, y, 0.23), (0.026, 0.026, 0.23), M["steel"], 0.008)
    return c


def counter_master(M):
    c = master("service_counter")
    box(c, "body", (0, 0, 0.50), (1.45, 0.48, 0.50), M["white"], 0.035)
    box(c, "toe_kick", (0, -0.46, 0.12), (1.36, 0.045, 0.11), M["dark"], 0.008)
    box(c, "worktop", (0, 0, 0.99), (1.52, 0.55, 0.055), M["steel"], 0.025)
    box(c, "register", (0.65, -0.18, 1.15), (0.23, 0.18, 0.16), M["dark"], 0.025)
    return c


def reorganize_interiors(M):
    # Remove the visible regimented all43_06 arrays, retaining shell, lighting and back walls.
    hidden = 0
    for o in bpy.data.objects:
        if o.name.startswith(
            (
                "all43_06:retail_shelf_",
                "all43_06:dining_table_",
                "all43_06:dining_chair_",
                "all43_06:service_counter",
            )
        ):
            o.hide_render = True
            hidden += 1
    shelf, table, chair, counter = (
        shelf_master(M),
        table_master(M),
        chair_master(M),
        counter_master(M),
    )
    conv = bpy.data.collections.get("all43_01:MASTER:convenience_store")
    rest = bpy.data.collections.get("all43_01:MASTER:restaurant")
    # Entry/front display -> staggered aisles -> wall cooling -> checkout -> back wall.
    retail = [
        (-4.5, -2.55, 0.13, 1.51, 0.72),
        (-2.15, -1.20, 0.13, 1.61, 1.0),
        (0.35, -2.05, 0.13, 1.48, 0.94),
        (3.05, -0.75, 0.13, 1.67, 1.05),
        (-4.95, 1.05, 0.13, 0.03, 0.82),
    ]
    for i, (x, y, z, r, s) in enumerate(retail):
        instance(conv, shelf, "retail_zone", (x, y, z), r, (s, 1, 1))
    # Wall freezer run and checkout define a clear, non-grid circulation path.
    for x in (-3.7, -0.9, 1.9):
        instance(conv, shelf, "wall_cooler", (x, 3.62, 0.13), 0, (1.02, 0.82, 1.08))
    instance(conv, counter, "checkout", (4.45, 1.68, 0.13), -1.53, (1.20, 1, 1))
    # Restaurant: open entrance path, varied seating islands, counter and rear service zone.
    layouts = [
        (-4.5, -2.0, 0.08),
        (-1.65, -2.42, -0.11),
        (1.25, -1.55, 0.14),
        (-3.55, 0.48, -0.16),
        (-0.20, 0.82, 0.06),
    ]
    for i, (x, y, r) in enumerate(layouts):
        instance(
            rest, table, "dining_table", (x, y, 0.13), r, (1 if i != 3 else 0.86, 1, 1)
        )
        for side in (-1, 1):
            instance(
                rest,
                chair,
                "dining_chair",
                (x + side * 0.72 * math.sin(r), y + side * 0.72 * math.cos(r), 0.13),
                r + (0 if side < 0 else math.pi),
            )
    instance(
        rest, counter, "service_counter", (3.85, 1.70, 0.13), math.pi, (1.28, 1, 1)
    )
    instance(rest, counter, "rear_prep", (0.75, 3.45, 0.13), 0, (1.08, 0.82, 1))
    return hidden, 5 + 3 + 1 + 5 + 10 + 2


def frontage(M):
    old = bpy.data.collections.get("all43_07:frontage_realism")
    if old:
        for o in old.objects:
            o.hide_render = True
    root = (
        bpy.data.collections.get("all43_01:commercial_root")
        or bpy.context.scene.collection
    )
    c = bpy.data.collections.new(P + "frontage")
    root.children.link(c)
    # Separate slabs and real vertical transitions: facade -> apron -> sidewalk -> curb -> asphalt.
    box(
        c,
        "entrance_apron",
        (-31, -27.38, 0.31),
        (31.4, 0.72, 0.10),
        M["concrete"],
        0.018,
    )
    box(c, "sidewalk", (-31, -28.72, 0.22), (31.4, 0.62, 0.12), M["concrete"], 0.018)
    box(c, "curb", (-31, -29.53, 0.105), (31.4, 0.18, 0.205), M["curb"], 0.022)
    box(c, "gutter", (-31, -29.86, 0.075), (31.4, 0.15, 0.055), M["asphalt"], 0.012)
    # Expansion joints stop the foreground reading as one giant plane.
    for x in range(-60, 0, 3):
        box(
            c,
            "paving_joint",
            (x, -28.70, 0.345),
            (0.025, 0.60, 0.007),
            M["dark"],
            0.002,
        )
    for x in (-51, -43, -35, -27, -19, -11, -5):
        box(c, "threshold", (x, -27.05, 0.43), (1.15, 0.22, 0.045), M["sill"], 0.012)
    for x in (-51, -35, -19):
        box(
            c, "drain_grate", (x, -29.84, 0.145), (1.08, 0.13, 0.025), M["steel"], 0.006
        )
        for j in range(7):
            box(
                c,
                "drain_slot",
                (x - 0.82 + j * 0.27, -29.85, 0.175),
                (0.055, 0.10, 0.012),
                M["dark"],
                0.002,
            )
    # Restrained asphalt breakup and wheel/oil traces remain subordinate to the architecture.
    for x, y, s, r in (
        (-44, -34, 2.1, 0.05),
        (-29, -37, 1.5, -0.08),
        (-16, -34.5, 1.75, 0.03),
    ):
        box(
            c,
            "asphalt_tone",
            (x, y, 0.142),
            (s, s * 0.55, 0.008),
            M["asphalt"],
            0.08,
            r,
        )
    for x, y in ((-38, -35.8), (-22, -39.2)):
        box(c, "oil_trace", (x, y, 0.152), (0.62, 0.34, 0.006), M["rubber"], 0.10, 0.14)
    for x in (-47, -40.5, -34, -27.5, -21):
        for dx in (-0.66, 0.66):
            box(
                c,
                "tire_wear",
                (x + dx, -34.8, 0.152),
                (0.075, 1.55, 0.004),
                M["rubber"],
                0.02,
            )
    return c


def attachment_masters(M):
    ac = master("AC_detailed")
    box(ac, "case", (0, 0, 0.48), (0.72, 0.30, 0.48), M["steel"], 0.045)
    box(ac, "fan_recess", (0, -0.32, 0.48), (0.34, 0.025, 0.34), M["dark"], 0.02)
    for a in range(0, 360, 30):
        r = math.radians(a)
        box(
            ac,
            "fan_grille",
            (0.28 * math.cos(r), -0.355, 0.48 + 0.28 * math.sin(r)),
            (0.025, 0.018, 0.025),
            M["steel"],
            0.008,
        )
    for x in (-0.58, 0.58):
        box(ac, "bracket", (x, 0.16, 0.08), (0.06, 0.30, 0.06), M["steel"], 0.012)
    box(ac, "pipe_port", (0.62, 0.20, 0.20), (0.08, 0.08, 0.08), M["steel"], 0.015)
    hv = master("roof_HVAC_detailed")
    box(hv, "cabinet", (0, 0, 0.55), (1.20, 0.82, 0.55), M["steel"], 0.055)
    box(hv, "top", (0, 0, 1.10), (1.25, 0.87, 0.055), M["steel"], 0.025)
    for x in (-0.72, -0.36, 0, 0.36, 0.72):
        box(hv, "louver", (x, -0.85, 0.58), (0.025, 0.025, 0.34), M["dark"], 0.005)
    box(hv, "duct", (1.38, 0.12, 0.33), (0.22, 0.55, 0.33), M["steel"], 0.035)
    elec = master("electrical_detailed")
    box(elec, "cabinet", (0, 0, 0.62), (0.40, 0.20, 0.62), M["steel"], 0.035)
    box(elec, "door", (0, -0.22, 0.62), (0.35, 0.025, 0.54), M["steel"], 0.009)
    box(elec, "hinge", (-0.31, -0.25, 0.83), (0.025, 0.02, 0.10), M["dark"], 0.006)
    box(elec, "lock", (0.25, -0.25, 0.62), (0.025, 0.02, 0.045), M["dark"], 0.006)
    pipe = master("downpipe_detailed")
    box(pipe, "vertical", (0, 0, 1.55), (0.07, 0.07, 1.55), M["steel"], 0.025)
    box(pipe, "shoe", (0, -0.16, 0.12), (0.07, 0.20, 0.07), M["steel"], 0.025)
    cam = master("camera_light")
    box(cam, "mount", (0, 0, 0.10), (0.11, 0.09, 0.10), M["steel"], 0.025)
    box(cam, "camera", (0, -0.19, 0.06), (0.10, 0.18, 0.08), M["steel"], 0.035)
    box(cam, "lens", (0, -0.38, 0.06), (0.05, 0.02, 0.05), M["dark"], 0.015)
    box(cam, "wall_light", (0.42, 0, 0.12), (0.25, 0.12, 0.16), M["steel"], 0.025)
    box(cam, "lens", (0.42, -0.14, 0.10), (0.20, 0.025, 0.11), M["glow"], 0.012)
    return dict(ac=ac, hvac=hv, electrical=elec, pipe=pipe, camera=cam)


def attachments(M):
    ms = attachment_masters(M)
    for cname in ("all43_01:MASTER:convenience_store", "all43_01:MASTER:restaurant"):
        c = bpy.data.collections.get(cname)
        instance(c, ms["ac"], "AC", (7.68, 1.20, 1.40), math.pi / 2)
        instance(c, ms["electrical"], "electrical", (-5.8, 4.55, 0.25), math.pi)
        instance(c, ms["pipe"], "downpipe", (-7.45, -4.68, 0.10))
        instance(c, ms["camera"], "camera_light", (6.55, -4.82, 3.28))
    conv = bpy.data.collections.get("all43_01:MASTER:convenience_store")
    rest = bpy.data.collections.get("all43_01:MASTER:restaurant")
    instance(conv, ms["hvac"], "roof_HVAC", (3.1, 1.25, 5.16), 0.06)
    instance(rest, ms["hvac"], "roof_HVAC", (-2.9, 1.35, 5.16), -0.05)
    return ms


def facade_materials(M):
    changed = 0
    for o in bpy.data.objects:
        low = o.name.lower()
        target = (
            M["green"]
            if any(k in low for k in ("green", "fresh"))
            else M["orange"]
            if any(k in low for k in ("orange", "terracotta", "kitchen"))
            else None
        )
        if not target or o.type != "MESH":
            continue
        for s in o.material_slots:
            s.link = "OBJECT"
            s.material = target
        changed += 1
    return changed


def edge_pass():
    changed = 0
    for o in bpy.data.objects:
        if o.type != "MESH" or not any(
            k in o.name.lower()
            for k in (
                "frame",
                "jamb",
                "rail",
                "sill",
                "threshold",
                "awning",
                "wall",
                "curb",
            )
        ):
            continue
        if o.modifiers.get("08_scaled_bevel"):
            continue
        q = o.modifiers.new("08_scaled_bevel", "BEVEL")
        q.width = 0.008
        q.segments = 2
        changed += 1
    return changed


def run():
    M = materials()
    bays = install_storefronts(M)
    hidden, interior = reorganize_interiors(M)
    front = frontage(M)
    attach = attachments(M)
    return {
        "storefront_instances": bays,
        "old_array_objects_hidden": hidden,
        "new_interior_instances": interior,
        "frontage": front.name,
        "attachment_categories": list(attach),
        "facade_materials": facade_materials(M),
        "bevel_objects": edge_pass(),
    }

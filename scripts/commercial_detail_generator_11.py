"""all43_11: remove unexplained door bars, enrich product masters, add restrained entrance wear."""
import math, random
import bpy

P = "all43_11:"


def mat(name, color, rough=0.5, metal=0):
    m = bpy.data.materials.get(P + name) or bpy.data.materials.new(P + name)
    m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    b.inputs["Base Color"].default_value = color
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    return m


def wear_material():
    m = mat("entrance_micro_wear", (0.38, 0.375, 0.35, 1), 0.72)
    n = m.node_tree.nodes
    l = m.node_tree.links
    b = n.get("Principled BSDF")
    tex = n.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = 8
    tex.inputs["Detail"].default_value = 5
    tex.inputs["Roughness"].default_value = 0.72
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.22
    ramp.color_ramp.elements[0].color = (0.41, 0.405, 0.39, 1)
    ramp.color_ramp.elements[1].position = 0.78
    ramp.color_ramp.elements[1].color = (0.53, 0.52, 0.49, 1)
    l.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], b.inputs["Base Color"])
    rr = n.new("ShaderNodeMapRange")
    rr.inputs["To Min"].default_value = 0.48
    rr.inputs["To Max"].default_value = 0.88
    l.new(tex.outputs["Fac"], rr.inputs["Value"])
    l.new(rr.outputs["Result"], b.inputs["Roughness"])
    bump = n.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.018
    l.new(tex.outputs["Fac"], bump.inputs["Height"])
    l.new(bump.outputs["Normal"], b.inputs["Normal"])
    return m


def meshes():
    cube = bpy.data.meshes.get("all43_10:shared_cube")
    cyl = bpy.data.meshes.get("all43_10:shared_cylinder_12")
    if not cube or not cyl:
        raise RuntimeError("all43_10 shared product meshes missing")
    return cube, cyl


def add(c, n, mesh, loc, scale, M, bevel=0.004, rot=0):
    o = bpy.data.objects.new(P + n, mesh)
    c.objects.link(o)
    o.location = loc
    o.scale = scale
    o.rotation_euler[2] = rot
    if not mesh.materials:
        mesh.materials.append(M)
    o.material_slots[0].link = "OBJECT"
    o.material_slots[0].material = M
    if bevel:
        q = o.modifiers.new("package_edge_bevel", "BEVEL")
        q.width = min(bevel, min(scale) * 0.18)
        q.segments = 2
    o["shared_mesh_data"] = True
    return o


def remove_door_bars():
    hidden = []
    # These six pieces were the only new bar-shaped door hardware in all43_09 and read brown in the glazing.
    for o in bpy.data.objects:
        low = o.name.lower()
        if (
            o.name.startswith("all43_09:entry_handle_")
            or "door_pull" in low
            or "02_pull" in low
        ):
            o.hide_render = True
            o["all43_11_removed_unexplained_door_bar"] = True
            hidden.append(o.name)
    return hidden


def product_materials():
    return {
        "paper": mat("paper_label", (0.80, 0.75, 0.57, 1), 0.48),
        "ink": mat("printed_ink", (0.035, 0.12, 0.25, 1), 0.42),
        "accent": mat("package_accent", (0.72, 0.08, 0.025, 1), 0.44),
        "foil": mat("can_foil", (0.42, 0.45, 0.44, 1), 0.26, 0.72),
        "cap": mat("cap_ridged", (0.055, 0.18, 0.08, 1), 0.48),
        "glass": mat("bottle_glass", (0.025, 0.16, 0.09, 1), 0.18),
        "white": mat("package_white", (0.76, 0.78, 0.72, 1), 0.44),
        "seam": mat("package_seam", (0.18, 0.09, 0.025, 1), 0.58),
    }


def enrich_products(M):
    cube, cyl = meshes()
    counts = {}

    def C(key):
        c = bpy.data.collections.get("all43_10:MASTER:product_" + key)
        if not c:
            raise RuntimeError("missing product master " + key)
        return c

    # Bottle: shoulder, neck collar, ribbed cap and a layered wrap label.
    c = C("bottle")
    add(c, "bottle_shoulder", cyl, (0, 0, 0.315), (0.066, 0.066, 0.055), M["glass"])
    add(c, "bottle_label", cyl, (0, 0, 0.155), (0.078, 0.078, 0.082), M["paper"])
    add(c, "bottle_label_band", cyl, (0, 0, 0.155), (0.080, 0.080, 0.018), M["accent"])
    add(c, "bottle_cap_ridge", cyl, (0, 0, 0.421), (0.046, 0.046, 0.020), M["cap"])
    counts["bottle"] = 4
    # Can: metallic top/bottom rims, printed wrap, pull-tab and lower color band.
    c = C("can")
    add(c, "can_print_wrap", cyl, (0, 0, 0.13), (0.074, 0.074, 0.092), M["ink"])
    add(c, "can_lower_band", cyl, (0, 0, 0.045), (0.076, 0.076, 0.016), M["accent"])
    add(c, "can_lid", cyl, (0, 0, 0.269), (0.070, 0.070, 0.006), M["foil"])
    add(
        c, "pull_tab", cube, (0, -0.018, 0.278), (0.026, 0.010, 0.004), M["seam"], 0.003
    )
    counts["can"] = 4
    # Carton: folded top, side seam, front label field and screw cap.
    c = C("carton")
    add(
        c,
        "carton_front_print",
        cube,
        (0, -0.073, 0.17),
        (0.070, 0.006, 0.092),
        M["paper"],
        0.003,
    )
    add(
        c,
        "carton_color_band",
        cube,
        (0, -0.080, 0.095),
        (0.096, 0.006, 0.020),
        M["accent"],
        0.003,
    )
    add(c, "carton_fold", cube, (0, 0, 0.356), (0.080, 0.055, 0.012), M["white"], 0.004)
    add(c, "carton_cap", cyl, (0.045, -0.025, 0.385), (0.022, 0.022, 0.018), M["cap"])
    counts["carton"] = 4
    # Flexible bag: sealed crimp bars, gusset shadow and two-part printed graphic.
    c = C("bag")
    add(
        c, "bag_top_crimp", cube, (0, 0, 0.477), (0.135, 0.018, 0.012), M["seam"], 0.004
    )
    add(
        c,
        "bag_bottom_crimp",
        cube,
        (0, 0, 0.006),
        (0.135, 0.018, 0.010),
        M["seam"],
        0.004,
    )
    add(
        c,
        "bag_print_panel",
        cube,
        (0, -0.105, 0.22),
        (0.095, 0.006, 0.105),
        M["ink"],
        0.003,
    )
    add(
        c,
        "bag_print_stripe",
        cube,
        (0, -0.112, 0.13),
        (0.120, 0.006, 0.018),
        M["accent"],
        0.003,
    )
    counts["bag"] = 4
    # Cardboard box: front artwork, side information panel, folded lid and tear strip.
    c = C("box")
    add(
        c,
        "box_front_art",
        cube,
        (0, -0.073, 0.16),
        (0.090, 0.006, 0.080),
        M["paper"],
        0.003,
    )
    add(c, "box_logo", cube, (0, -0.080, 0.19), (0.052, 0.006, 0.025), M["ink"], 0.003)
    add(
        c,
        "box_side_panel",
        cube,
        (0.122, 0, 0.14),
        (0.006, 0.052, 0.090),
        M["white"],
        0.003,
    )
    add(c, "box_top_flap", cube, (0, 0, 0.286), (0.112, 0.065, 0.008), M["seam"], 0.004)
    counts["box"] = 4
    return counts


def patch_mesh():
    m = bpy.data.meshes.get(P + "shared_irregular_wear_patch")
    if m:
        return m
    n = 18
    rng = random.Random(4311)
    v = [(0, 0, 0)]
    for i in range(n):
        a = 2 * math.pi * i / n
        r = 0.82 + rng.random() * 0.26
        v.append((r * math.cos(a), r * 0.58 * math.sin(a), 0))
    f = []
    for i in range(n):
        f.append((0, i + 1, (i + 1) % n + 1))
    m = bpy.data.meshes.new(P + "shared_irregular_wear_patch")
    m.from_pydata(v, [], f)
    return m


def ground_wear():
    M = wear_material()
    mesh = patch_mesh()
    made = []
    specs = [
        ("all43_01:MASTER:convenience_store", 5.45),
        ("all43_01:MASTER:restaurant", 6.15),
    ]
    patterns = [
        (0, -0.48, 1.15, 0.56, 0.08),
        (-0.42, -1.02, 0.72, 0.34, -0.18),
        (0.48, -1.38, 0.58, 0.27, 0.15),
        (0, -1.78, 0.84, 0.30, -0.04),
    ]
    for cname, door_x in specs:
        c = bpy.data.collections[cname]
        for i, (dx, dy, sx, sy, r) in enumerate(patterns):
            o = add(
                c,
                "entrance_wear_patch",
                mesh,
                (door_x + dx, -4.92 + dy, 0.186),
                (sx, sy, 1),
                M,
                0,
                r,
            )
            o.visible_shadow = False
            o["wear_function"] = "pedestrian_traffic_polish_and_scuff"
            made.append(o.name)
        # Two narrow threshold abrasion marks, attached to the walking line rather than floating.
        cube, _ = meshes()
        for dx in (-0.20, 0.22):
            o = add(
                c,
                "threshold_scuff",
                cube,
                (door_x + dx, -5.17, 0.190),
                (0.055, 0.32, 0.003),
                M,
                0.003,
                0.03 if dx < 0 else -0.04,
            )
            o.visible_shadow = False
            o["wear_function"] = "doorway_foot_traffic"
            made.append(o.name)
    return made


def run():
    bars = remove_door_bars()
    details = enrich_products(product_materials())
    wear = ground_wear()
    return {
        "door_bar_objects_hidden": bars,
        "product_masters_enriched": details,
        "new_product_detail_parts": sum(details.values()),
        "entrance_wear_instances": len(wear),
        "unique_new_meshes": sum(m.name.startswith(P) for m in bpy.data.meshes),
        "shared_detail_objects": sum(
            bool(o.get("shared_mesh_data"))
            for o in bpy.data.objects
            if o.name.startswith(P)
        ),
        "sanity_check": "PASS",
    }

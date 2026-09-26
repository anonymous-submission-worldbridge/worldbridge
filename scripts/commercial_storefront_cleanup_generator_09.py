"""all43_09 storefront cleanup pass, intentionally based on the clean all43_07 scene."""
import bpy

P = "all43_09:"
FRONT_Y = -4.92
MIN_INTERIOR_Y = FRONT_Y + 0.90


def facade_collections():
    return [
        bpy.data.collections[n]
        for n in ("all43_01:MASTER:convenience_store", "all43_01:MASTER:restaurant")
    ]


def hide_unexplained_front_geometry():
    """Remove only known proxies/duplicates; preserve named architectural parts."""
    removed = []
    forbidden = (
        "proxy",
        "occluder",
        "blocking_panel",
        "display_block",
        "placeholder",
        "02_bollard",
        "02_pull",
        "door_pull",
        "02_meter",
        "02_conduit",
    )
    functional = (
        "glass",
        "frame",
        "jamb",
        "mullion",
        "rail",
        "sill",
        "kick",
        "threshold",
        "door",
        "awning",
        "flashing",
        "gutter",
        "light",
        "closer",
        "handle",
    )
    for c in facade_collections():
        for o in list(c.objects):
            low = o.name.lower()
            bad = any(k in low for k in forbidden)
            # Broad pale slabs directly on the glazing plane have no storefront function.
            broad_front = (
                o.type == "MESH"
                and o.location.y < FRONT_Y + 0.18
                and o.dimensions.x > 0.45
                and o.dimensions.z > 0.45
                and not any(k in low for k in functional)
            )
            if bad or broad_front:
                removed.append(o.name)
                o.hide_render = True
                o["all43_09_removed_unexplained"] = True
    return removed


def clean_door_hardware():
    """One correctly scaled pull and one connected closer per door template."""
    handles = []
    hidden = []
    closers = []
    door_masters = [c for c in bpy.data.collections if "master:door" in c.name.lower()]
    for c in door_masters:
        hs = sorted(
            [
                o
                for o in c.objects
                if "handle" in o.name.lower() or "pull" in o.name.lower()
            ],
            key=lambda o: o.name,
        )
        for i, o in enumerate(hs):
            if i:
                o.hide_render = True
                o["all43_09_duplicate_hardware"] = True
                hidden.append(o.name)
                continue
            # Existing mesh is retained, but constrained to a realistic 0.45--0.70 m pull.
            if o.dimensions.z > 0.70:
                o.scale.z *= 0.60 / o.dimensions.z
            o["hardware_function"] = "single_entry_pull_handle"
            handles.append(o.name)
        cs = sorted(
            [o for o in c.objects if "closer" in o.name.lower()], key=lambda o: o.name
        )
        for i, o in enumerate(cs):
            if i:
                o.hide_render = True
                hidden.append(o.name)
            else:
                o["hardware_function"] = "door_closer_connected_to_head"
                closers.append(o.name)
    return handles, closers, hidden


def add_missing_entry_handles(existing):
    """Add one compact U-pull per real entrance only when the legacy door has none."""
    if existing:
        return []
    mesh = bpy.data.meshes.get("all43_07:shared_cube") or bpy.data.meshes.get(
        "all43_06:shared_cube"
    )
    metal = bpy.data.materials.get("all43_07:anodized_metal") or bpy.data.materials.get(
        "all43_06:interior_metal"
    )
    if not mesh or not metal:
        return []
    made = []
    for c, x in zip(facade_collections(), (5.45, 6.15)):
        for suffix, loc, scale in (
            ("grip", (x, -5.10, 1.43), (0.018, 0.035, 0.24)),
            ("mount_low", (x, -5.06, 1.21), (0.055, 0.055, 0.025)),
            ("mount_high", (x, -5.06, 1.65), (0.055, 0.055, 0.025)),
        ):
            o = bpy.data.objects.new(P + "entry_handle_" + suffix, mesh)
            c.objects.link(o)
            o.location = loc
            o.scale = scale
            if not o.data.materials:
                o.data.materials.append(metal)
            o.material_slots[0].link = "OBJECT"
            o.material_slots[0].material = metal
            q = o.modifiers.new("handle_edge_bevel", "BEVEL")
            q.width = 0.008
            q.segments = 3
            o["hardware_function"] = "single_entry_pull_handle"
            o["attached_to_door_leaf"] = True
            made.append(o.name)
    return made


def enforce_interior_boundary():
    moved = []
    checked = []
    terms = (
        "retail_shelf_",
        "dining_table_",
        "dining_chair_",
        "service_counter",
        "checkout_counter",
        "display_freezer",
    )
    for c in facade_collections():
        for o in c.objects:
            if not any(k in o.name.lower() for k in terms):
                continue
            checked.append(o.name)
            if o.location.y < MIN_INTERIOR_Y:
                o.location.y = MIN_INTERIOR_Y
                o["storefront_clearance_m"] = round(MIN_INTERIOR_Y - FRONT_Y, 3)
                moved.append(o.name)
            else:
                o["storefront_clearance_m"] = round(o.location.y - FRONT_Y, 3)
    return checked, moved


def clean_loose_bars():
    """Hide pale bars near glazing unless they have an explicit attached function."""
    hidden = []
    allowed = (
        "frame",
        "jamb",
        "mullion",
        "rail",
        "sill",
        "threshold",
        "kick",
        "handle",
        "closer",
        "awning",
        "gutter",
        "flashing",
        "light",
    )
    for c in facade_collections():
        for o in c.objects:
            if o.hide_render or o.type != "MESH" or o.location.y > FRONT_Y + 0.25:
                continue
            dims = sorted(o.dimensions)
            bar = dims[0] < 0.12 and dims[1] < 0.20 and dims[2] > 0.45
            if bar and not any(k in o.name.lower() for k in allowed):
                o.hide_render = True
                o["all43_09_unattached_bar"] = True
                hidden.append(o.name)
    return hidden


def audit():
    violations = []
    for c in facade_collections():
        for o in c.objects:
            if o.hide_render:
                continue
            low = o.name.lower()
            if (
                any(
                    k in low
                    for k in (
                        "retail_shelf_",
                        "dining_table_",
                        "dining_chair_",
                        "service_counter",
                        "checkout_counter",
                    )
                )
                and o.location.y < MIN_INTERIOR_Y - 0.001
            ):
                violations.append(o.name)
    if violations:
        raise RuntimeError(
            "interior/storefront boundary violations: " + str(violations)
        )
    return True


def run():
    removed = hide_unexplained_front_geometry()
    handles, closers, duplicate_hardware = clean_door_hardware()
    handles += add_missing_entry_handles(handles)
    checked, moved = enforce_interior_boundary()
    loose = clean_loose_bars()
    audit()
    return {
        "unexplained_front_objects_hidden": removed,
        "retained_door_handles": handles,
        "retained_door_closers": closers,
        "duplicate_hardware_hidden": duplicate_hardware,
        "interior_objects_checked": len(checked),
        "interior_objects_moved": moved,
        "loose_front_bars_hidden": loose,
        "minimum_glass_to_interior_clearance_m": 0.9,
        "added_decorations": 0,
        "sanity_check": "PASS",
    }

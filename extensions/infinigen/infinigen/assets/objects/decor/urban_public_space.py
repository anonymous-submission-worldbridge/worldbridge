"""Procedural civic ornaments used by the urban scene generator.

The fountain builder deliberately keeps every visible part procedural. The four
variants are distinct real-world fountain typologies (quatrefoil court, planted
three-tier, compact four-tier, and radial garden) and share the same
``UrbanAssetRequest`` interface as the rest of the urban pipeline.
"""

import math

from mathutils import Vector

from infinigen.assets.utils.urban_primitives import (
    UrbanAssetRequest,
    cube_obj,
    curve_obj,
    cylinder_between,
    cylinder_obj,
    ellipsoid_obj,
    mesh_obj,
    multi_curve_obj,
    sphere_obj,
    torus_obj,
)


FOUNTAIN_VARIANTS = (
    "royal_quatrefoil",
    "planted_three_tier",
    "compact_four_tier",
    "radial_garden",
)

FOUNTAIN_REFERENCES = {
    "royal_quatrefoil": "https://preview.free3d.com/img/2013/10/1688663323047887977/8jgtcddo.jpg",
    "planted_three_tier": "https://fbi.cults3d.com/uploaders/41230908/illustration-file/6829bd1f-f868-4896-811b-99c28b134a7b/3ddd1.jpg",
    "compact_four_tier": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQiX8DVgwRuHPMYTLEE9ivBwdhl6ykiEDszHuc6ydNn6g&s=10",
    "radial_garden": "https://encrypted-tbn0.gstatic.com/images?q=tbn:ANd9GcQTWFGoYDAd11dVB8yBB9_scHUU8koXMW6cf5aRjaLSbg&s=10",
}


def _profile_obj(
    name,
    center,
    profile,
    mat,
    semantic,
    *,
    segments=96,
    lobes=0,
    lobe_amplitude=0.0,
    phase=0.0,
):
    """Spin a detailed radial profile, optionally modulating it into scallops.

    Profile rows may be ``(radius, height)`` or ``(radius, height,
    row_amplitude)``.  Per-row amplitudes let the lip stay circular while the
    underside is deeply fluted, which is essential for classical fountain
    bowls and avoids the soft, uniformly-wavy silhouette of the old asset.
    """
    x, y, z = center
    verts = []
    for row in profile:
        radius, height = row[:2]
        row_amplitude = row[2] if len(row) > 2 else lobe_amplitude
        for i in range(segments):
            angle = math.tau * i / segments
            modulation = 1.0
            if lobes:
                modulation += row_amplitude * math.cos(lobes * angle + phase)
            rr = max(0.001, radius * modulation)
            verts.append((x + rr * math.cos(angle), y + rr * math.sin(angle), z + height))
    faces = []
    for row in range(len(profile) - 1):
        a0 = row * segments
        a1 = (row + 1) * segments
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((a0 + i, a0 + j, a1 + j, a1 + i))
    return mesh_obj(name, verts, faces, mat, semantic, smooth=True)


def _radial_surface(
    name,
    center,
    radius,
    mat,
    semantic,
    *,
    segments=96,
    lobes=0,
    lobe_amplitude=0.0,
    inner_radius=0.0,
    phase=0.0,
):
    """Create a horizontal disk or annulus with a scalloped outer boundary."""
    x, y, z = center
    verts = []
    faces = []
    if inner_radius <= 0:
        verts.append((x, y, z))
        for i in range(segments):
            a = math.tau * i / segments
            rr = radius * (1.0 + (lobe_amplitude * math.cos(lobes * a + phase) if lobes else 0.0))
            verts.append((x + rr * math.cos(a), y + rr * math.sin(a), z))
        for i in range(segments):
            faces.append((0, i + 1, ((i + 1) % segments) + 1))
    else:
        for i in range(segments):
            a = math.tau * i / segments
            outer = radius * (1.0 + (lobe_amplitude * math.cos(lobes * a + phase) if lobes else 0.0))
            verts.extend(
                [
                    (x + inner_radius * math.cos(a), y + inner_radius * math.sin(a), z),
                    (x + outer * math.cos(a), y + outer * math.sin(a), z),
                ]
            )
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((i * 2, j * 2, j * 2 + 1, i * 2 + 1))
    return mesh_obj(name, verts, faces, mat, semantic, smooth=True)


def _ring_profile(bottom, outer, inner, height, lip=0.05):
    """Closed moulded cross-section for a pool or planter wall."""
    return [
        (outer - lip, bottom),
        (outer, bottom + lip),
        (outer, bottom + height - lip),
        (outer - lip, bottom + height),
        (inner + lip, bottom + height),
        (inner, bottom + height - lip),
        (inner, bottom + lip),
        (inner + lip, bottom),
        (outer - lip, bottom),
    ]


def _leaf_relief(
    name,
    center,
    angle,
    width,
    height,
    depth,
    mat,
    semantic="fountain-ornament",
    *,
    rows=9,
):
    """Create a pointed, veined botanical relief on a radial vertical face."""
    x, y, z = center
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-math.sin(angle), math.cos(angle))
    verts = []
    for row in range(rows):
        t = row / (rows - 1)
        envelope = max(0.015, math.sin(math.pi * t) ** 0.72)
        half_width = width * 0.5 * envelope * (0.94 + 0.06 * math.cos(4 * math.pi * t))
        crown = depth * math.sin(math.pi * t) ** 1.35
        for lane in (-1.0, 0.0, 1.0):
            lateral = lane * half_width
            ridge = crown * (1.0 - 0.58 * abs(lane))
            verts.append(
                (
                    x + tangent[0] * lateral + radial[0] * ridge,
                    y + tangent[1] * lateral + radial[1] * ridge,
                    z + (t - 0.5) * height + 0.035 * height * math.sin(math.pi * t),
                )
            )
    faces = []
    for row in range(rows - 1):
        base = row * 3
        nxt = (row + 1) * 3
        faces.extend(
            [
                (base, base + 1, nxt + 1, nxt),
                (base + 1, base + 2, nxt + 2, nxt + 1),
            ]
        )
    return mesh_obj(name, verts, faces, mat, semantic, smooth=True)


def _annular_pavers(objects, prefix, x, y, z, inner, outer, mats, *, rings=2, segments=48):
    """Lay individually jointed wedge pavers, batched by subtle colour family."""
    buckets = [[] for _ in mats]
    ring_width = (outer - inner) / rings
    for ring in range(rings):
        r0 = inner + ring * ring_width + 0.014
        r1 = inner + (ring + 1) * ring_width - 0.014
        offset = (ring % 2) * math.pi / segments
        for i in range(segments):
            gap = 0.010
            a0 = offset + math.tau * i / segments + gap
            a1 = offset + math.tau * (i + 1) / segments - gap
            buckets[(i + ring * 3) % len(mats)].append(
                (
                    (x + r0 * math.cos(a0), y + r0 * math.sin(a0), z),
                    (x + r1 * math.cos(a0), y + r1 * math.sin(a0), z),
                    (x + r1 * math.cos(a1), y + r1 * math.sin(a1), z),
                    (x + r0 * math.cos(a1), y + r0 * math.sin(a1), z),
                )
            )
    for index, facespecs in enumerate(buckets):
        verts, faces = [], []
        for quad in facespecs:
            base = len(verts)
            verts.extend(quad)
            faces.append((base, base + 1, base + 2, base + 3))
        if verts:
            objects.append(mesh_obj(f"{prefix}:pavers:{index}", verts, faces, mats[index], "plaza"))


def _quatrefoil_tiles(objects, prefix, x, y, z, radius, mats, *, step=0.29):
    """Build a clipped checker of submerged stone tiles below a quatrefoil pool."""
    buckets = [[] for _ in mats]
    count = int(math.ceil(radius / step))
    for ix in range(-count, count + 1):
        for iy in range(-count, count + 1):
            px = ix * step
            py = iy * step
            rr = math.hypot(px, py)
            angle = math.atan2(py, px)
            boundary = radius * (1.0 + 0.13 * math.cos(4 * angle))
            if rr + step * 0.58 > boundary:
                continue
            half = step * 0.455
            buckets[(ix + iy) % len(mats)].append(
                (
                    (x + px - half, y + py - half, z),
                    (x + px + half, y + py - half, z),
                    (x + px + half, y + py + half, z),
                    (x + px - half, y + py + half, z),
                )
            )
    for index, facespecs in enumerate(buckets):
        verts, faces = [], []
        for quad in facespecs:
            base = len(verts)
            verts.extend(quad)
            faces.append((base, base + 1, base + 2, base + 3))
        if verts:
            objects.append(mesh_obj(f"{prefix}:submerged_tile:{index}", verts, faces, mats[index], "fountain-tile"))


def _batched_droplets(name, droplets, mat, semantic="fountain-water", *, sides=7):
    """Merge hundreds of anisotropic droplets into one smooth mesh."""
    if not droplets:
        return None
    verts, faces = [], []
    for x, y, z, radius, length in droplets:
        base = len(verts)
        verts.append((x, y, z + length * 0.55))
        verts.append((x, y, z - length * 0.55))
        for ring_z, ring_scale in ((z + length * 0.12, 0.86), (z - length * 0.17, 1.0)):
            for i in range(sides):
                a = math.tau * i / sides
                verts.append((x + radius * ring_scale * math.cos(a), y + radius * ring_scale * math.sin(a), ring_z))
        upper = base + 2
        lower = upper + sides
        for i in range(sides):
            j = (i + 1) % sides
            faces.extend(
                [
                    (base, upper + i, upper + j),
                    (upper + i, lower + i, lower + j, upper + j),
                    (base + 1, lower + j, lower + i),
                ]
            )
    return mesh_obj(name, verts, faces, mat, semantic, smooth=True)


def _rippled_water_surface(
    name,
    center,
    radius,
    mat,
    *,
    segments=112,
    rings=13,
    lobes=0,
    lobe_amplitude=0.0,
    agitation=1.0,
    phase=0.0,
):
    """Build a subtly displaced water skin instead of a perfectly flat disk.

    The low-amplitude crossed wave field is geometry, not a shader-only trick,
    so highlights break up correctly in both the production Cycles path and the
    lighter preview renderer.  The boundary can follow a scalloped stone bowl.
    """
    x, y, z = center
    verts = [(x, y, z + 0.0025 * agitation)]
    faces = []
    for ring in range(1, rings + 1):
        t = ring / rings
        for i in range(segments):
            a = math.tau * i / segments
            boundary = radius * (
                1.0 + (lobe_amplitude * math.cos(lobes * a + phase) if lobes else 0.0)
            )
            rr = boundary * t
            edge_fade = math.sin(math.pi * min(0.985, t)) ** 0.42
            wave = agitation * edge_fade * (
                0.0048 * math.sin(rr * 19.0 + a * 3.0 + phase)
                + 0.0031 * math.sin(rr * 31.0 - a * 5.0 + 0.7)
                + 0.0017 * math.cos(rr * 47.0 + a * 9.0)
            )
            # A gentle meniscus at the stone edge keeps the pool from reading
            # as a rigid blue plate.
            meniscus = 0.0065 * agitation * max(0.0, (t - 0.88) / 0.12) ** 2
            verts.append((x + rr * math.cos(a), y + rr * math.sin(a), z + wave + meniscus))
    for i in range(segments):
        faces.append((0, 1 + i, 1 + ((i + 1) % segments)))
    for ring in range(rings - 1):
        inner = 1 + ring * segments
        outer = inner + segments
        for i in range(segments):
            j = (i + 1) % segments
            faces.append((inner + i, outer + i, outer + j, inner + j))
    return mesh_obj(name, verts, faces, mat, "fountain-water", smooth=True)


def _variable_tube_mesh(name, paths, mat, semantic="fountain-water", *, sides=7):
    """Merge tapered, wobbling liquid filaments into a closed smooth mesh.

    Each path point is ``(x, y, z, radius)``.  Variable radii and separated
    path fragments are important: a constant bevel-depth curve looks like a
    cable, while a closed tapered liquid core catches irregular highlights and
    naturally breaks into droplets.
    """
    verts, faces = [], []
    for path_index, path in enumerate(paths):
        if len(path) < 2:
            continue
        path_start = len(verts)
        for index, point in enumerate(path):
            position = Vector(point[:3])
            if index == 0:
                tangent = Vector(path[1][:3]) - position
            elif index == len(path) - 1:
                tangent = position - Vector(path[index - 1][:3])
            else:
                tangent = Vector(path[index + 1][:3]) - Vector(path[index - 1][:3])
            if tangent.length < 1e-7:
                tangent = Vector((0.0, 0.0, 1.0))
            tangent.normalize()
            reference = Vector((0.0, 0.0, 1.0)) if abs(tangent.z) < 0.88 else Vector((1.0, 0.0, 0.0))
            axis_u = tangent.cross(reference).normalized()
            axis_v = tangent.cross(axis_u).normalized()
            base_radius = max(0.0008, point[3])
            for side in range(sides):
                a = math.tau * side / sides + path_index * 0.37
                irregularity = 1.0 + 0.13 * math.sin(side * 2.31 + index * 1.77 + path_index)
                offset = (
                    axis_u * (math.cos(a) * base_radius * irregularity)
                    + axis_v * (math.sin(a) * base_radius * (0.86 + 0.11 * math.sin(index + side)))
                )
                verts.append(tuple(position + offset))
        ring_count = len(path)
        for ring in range(ring_count - 1):
            a0 = path_start + ring * sides
            a1 = a0 + sides
            for side in range(sides):
                nxt = (side + 1) % sides
                faces.append((a0 + side, a0 + nxt, a1 + nxt, a1 + side))
        faces.append(tuple(path_start + side for side in reversed(range(sides))))
        last = path_start + (ring_count - 1) * sides
        faces.append(tuple(last + side for side in range(sides)))
    if not verts:
        return None
    return mesh_obj(name, verts, faces, mat, semantic, smooth=True)


def _liquid_ribbon_mesh(name, ribbons, mat, semantic="fountain-water", *, sides=10):
    """Merge thin closed water sheets with changing width and thickness.

    Ribbon points are ``(x, y, z, tangent_angle, width, thickness)``.  The
    elliptical cross section provides a real refractive volume but remains
    sheet-like, producing the stretched, torn appearance of water leaving a
    stone lip instead of the circular silhouette of wire geometry.
    """
    verts, faces = [], []
    for ribbon_index, ribbon in enumerate(ribbons):
        if len(ribbon) < 2:
            continue
        start = len(verts)
        for row, (px, py, pz, angle, width, depth) in enumerate(ribbon):
            tangent = Vector((-math.sin(angle), math.cos(angle), 0.0))
            radial = Vector((math.cos(angle), math.sin(angle), 0.0))
            centre = Vector((px, py, pz))
            for side in range(sides):
                q = math.tau * side / sides
                flutter = 1.0 + 0.10 * math.sin(row * 1.43 + side * 2.07 + ribbon_index)
                offset = tangent * (0.5 * width * math.cos(q) * flutter)
                offset += radial * (0.5 * depth * math.sin(q))
                verts.append(tuple(centre + offset))
        for row in range(len(ribbon) - 1):
            a0 = start + row * sides
            a1 = a0 + sides
            for side in range(sides):
                nxt = (side + 1) % sides
                faces.append((a0 + side, a0 + nxt, a1 + nxt, a1 + side))
        faces.append(tuple(start + side for side in reversed(range(sides))))
        last = start + (len(ribbon) - 1) * sides
        faces.append(tuple(last + side for side in range(sides)))
    if not verts:
        return None
    return mesh_obj(name, verts, faces, mat, semantic, smooth=True)


def _splash_geometry(objects, prefix, impacts, water_mat, foam_mat):
    """Create curved impact filaments, droplets and irregular foam patches."""
    splash_paths = []
    foam_verts, foam_faces = [], []
    spray_drops = []
    for impact_index, (px, py, pz, angle, scale) in enumerate(impacts):
        for fin in range(3):
            q = angle + math.tau * fin / 3 + 0.31 * math.sin(impact_index * 1.7 + fin)
            rise = scale * (0.11 + 0.065 * (0.5 + 0.5 * math.sin(impact_index * 2.1 + fin)))
            reach = scale * (0.10 + 0.05 * ((fin + 1) % 3))
            rx, ry = math.cos(q), math.sin(q)
            path = []
            for row in range(8):
                t = row / 7
                lateral = scale * 0.010 * math.sin(math.pi * t) * math.sin(impact_index + fin * 1.9)
                tx, ty = -ry, rx
                path.append(
                    (
                        px + rx * reach * t + tx * lateral,
                        py + ry * reach * t + ty * lateral,
                        pz + rise * 4.0 * t * (1.0 - t) - scale * 0.006 * t,
                        scale * (0.011 - 0.0065 * t) * (0.88 + 0.12 * math.sin(row * 1.7 + fin) ** 2),
                    )
                )
            splash_paths.append(path)
            if (impact_index + fin) % 2 == 0:
                spray_drops.append(
                    (
                        px + rx * reach * 1.12,
                        py + ry * reach * 1.12,
                        pz + rise * 0.82,
                        scale * 0.010,
                        scale * 0.030,
                    )
                )
        base = len(foam_verts)
        foam_verts.append((px, py, pz + 0.003))
        patch_radius = scale * (0.10 + 0.025 * (impact_index % 4))
        for side in range(9):
            q = math.tau * side / 9 + angle
            rr = patch_radius * (0.74 + 0.24 * math.sin(side * 2.6 + impact_index))
            foam_verts.append((px + rr * math.cos(q), py + rr * math.sin(q), pz + 0.0035))
        for side in range(9):
            foam_faces.append((base, base + 1 + side, base + 1 + ((side + 1) % 9)))
    splash_obj = _variable_tube_mesh(f"{prefix}:curved_splash_filaments", splash_paths, water_mat, sides=6)
    if splash_obj:
        objects.append(splash_obj)
    if foam_verts:
        objects.append(mesh_obj(f"{prefix}:aerated_foam_patches", foam_verts, foam_faces, foam_mat, "fountain-water", smooth=True))
    drop_obj = _batched_droplets(f"{prefix}:impact_spray_drops", spray_drops, foam_mat, sides=6)
    if drop_obj:
        objects.append(drop_obj)


def _surface_ripples(objects, prefix, x, y, z, radii, mat, *, broken=False):
    """Add fine highlight rings where falling water disturbs a pool."""
    if not broken:
        for index, radius in enumerate(radii):
            objects.append(torus_obj(f"{prefix}:ripple:{index}", (x, y, z), radius, 0.003, mat, "fountain-water"))
        return
    paths = []
    for index, radius in enumerate(radii):
        for arc in range(3):
            start = arc * math.tau / 3 + 0.19 * index
            points = []
            for k in range(7):
                a = start + 0.36 * k / 6
                rr = radius * (1.0 + 0.012 * math.sin(k * 1.7 + index))
                points.append((x + rr * math.cos(a), y + rr * math.sin(a), z))
            paths.append(points)
    objects.append(multi_curve_obj(f"{prefix}:broken_ripples", paths, 0.0012, mat, "fountain-water", resolution=2))


def _stone_base(objects, prefix, x, y, z, mat, radius, semantic="fountain"):
    profile = [
        (0.01, 0.00),
        (radius * 0.88, 0.00),
        (radius, 0.055),
        (radius, 0.13),
        (radius * 0.93, 0.19),
        (radius * 0.83, 0.22),
        (radius * 0.80, 0.28),
        (0.01, 0.28),
    ]
    objects.append(_profile_obj(f"{prefix}:moulded_foot", (x, y, z), profile, mat, semantic))


def _pedestal(objects, prefix, x, y, z, height, radius, mat, *, lobes=0, ornate=True):
    flute_count = max(8, lobes or 12)
    profile = [
        (0.01, 0.00, 0.0),
        (radius * 1.14, 0.00, 0.0),
        (radius * 1.21, height * 0.055, 0.0),
        (radius * 1.18, height * 0.13, 0.015),
        (radius * 0.86, height * 0.20, -0.018),
        (radius * 0.68, height * 0.35, -0.085),
        (radius * 0.64, height * 0.55, -0.090),
        (radius * 0.82, height * 0.68, -0.055),
        (radius * 1.08, height * 0.75, 0.045),
        (radius * 1.18, height * 0.82, 0.030),
        (radius * 1.09, height * 0.91, 0.015),
        (radius * 0.82, height * 0.97, 0.0),
        (radius * 0.84, height, 0.0),
        (0.01, height, 0.0),
    ]
    objects.append(
        _profile_obj(
            f"{prefix}:pedestal",
            (x, y, z),
            profile,
            mat,
            "fountain",
            segments=128,
            lobes=flute_count,
        )
    )
    for suffix, zz, rr, minor in (
        ("lower_bead", z + height * 0.14, radius * 1.04, radius * 0.055),
        ("waist_bead", z + height * 0.61, radius * 0.69, radius * 0.038),
        ("capital_bead", z + height * 0.88, radius * 1.03, radius * 0.045),
    ):
        objects.append(torus_obj(f"{prefix}:{suffix}", (x, y, zz), rr, minor, mat, "fountain-ornament"))
    if ornate:
        relief_count = min(12, flute_count)
        for i in range(relief_count):
            a = math.tau * i / relief_count
            rr = radius * 0.79
            objects.append(
                _leaf_relief(
                    f"{prefix}:pedestal_acanthus:{i}",
                    (x + rr * math.cos(a), y + rr * math.sin(a), z + height * 0.735),
                    a,
                    radius * 0.26,
                    height * 0.28,
                    radius * 0.075,
                    mat,
                )
            )


def _ornate_bowl(
    objects,
    prefix,
    x,
    y,
    z,
    radius,
    depth,
    mat,
    water,
    *,
    lobes=12,
    accent=None,
    ripple_mat=None,
):
    """Deep structural bowl with a fluted soffit, hollow interior and wet lip."""
    accent = accent or mat
    ripple_mat = ripple_mat or water
    profile = [
        (radius * 0.17, 0.00, 0.0),
        (radius * 0.31, 0.025 * depth, -0.025),
        (radius * 0.52, 0.12 * depth, -0.075),
        (radius * 0.74, 0.35 * depth, -0.110),
        (radius * 0.91, 0.67 * depth, -0.092),
        (radius * 1.01, 0.84 * depth, -0.052),
        (radius * 1.075, 0.91 * depth, 0.018),
        (radius * 1.095, 1.01 * depth, 0.020),
        (radius * 1.045, 1.10 * depth, 0.010),
        (radius * 0.91, 1.12 * depth, 0.006),
        (radius * 0.80, 0.98 * depth, 0.004),
        (radius * 0.49, 0.32 * depth, -0.018),
        (radius * 0.19, 0.015 * depth, 0.0),
        (radius * 0.17, 0.00, 0.0),
    ]
    objects.append(
        _profile_obj(
            f"{prefix}:scalloped_bowl",
            (x, y, z),
            profile,
            mat,
            "fountain",
            segments=128,
            lobes=lobes,
            phase=math.pi,
        )
    )
    objects.append(
        _profile_obj(
            f"{prefix}:rolled_rim",
            (x, y, z),
            [
                (radius * 0.965, depth * 0.88, 0.018),
                (radius * 1.09, depth * 0.90, 0.018),
                (radius * 1.12, depth * 1.015, 0.016),
                (radius * 1.075, depth * 1.105, 0.010),
                (radius * 0.94, depth * 1.085, 0.006),
                (radius * 0.965, depth * 0.88, 0.018),
            ],
            mat,
            "fountain",
            lobes=lobes,
            phase=math.pi,
        )
    )
    objects.append(
        _profile_obj(
            f"{prefix}:wet_inner_lip",
            (x, y, z),
            [
                (radius * 0.905, depth * 0.945, 0.004),
                (radius * 0.945, depth * 1.045, 0.006),
                (radius * 0.915, depth * 1.075, 0.005),
                (radius * 0.885, depth * 0.97, 0.004),
                (radius * 0.905, depth * 0.945, 0.004),
            ],
            accent,
            "fountain-wet-stone",
            segments=128,
            lobes=lobes,
            phase=math.pi,
        )
    )
    objects.append(
        _rippled_water_surface(
            f"{prefix}:agitated_water_skin",
            (x, y, z + depth * 1.025),
            radius * 0.895,
            water,
            segments=96,
            rings=11,
            lobes=lobes,
            lobe_amplitude=0.006,
            agitation=0.72,
            phase=math.pi,
        )
    )
    # Raised stone ribs and separate acanthus panels keep the soffit readable
    # under grazing daylight instead of dissolving into a single smooth blob.
    for i in range(lobes):
        a = math.tau * i / lobes
        objects.append(
            cylinder_between(
                f"{prefix}:soffit_rib:{i}",
                (x + radius * 0.27 * math.cos(a), y + radius * 0.27 * math.sin(a), z + depth * 0.09),
                (x + radius * 0.92 * math.cos(a), y + radius * 0.92 * math.sin(a), z + depth * 0.78),
                max(0.007, radius * 0.017),
                mat,
                "fountain-ornament",
                vertices=12,
            )
        )
        rr = radius * 0.70
        objects.append(
            _leaf_relief(
                f"{prefix}:soffit_acanthus:{i}",
                (x + rr * math.cos(a), y + rr * math.sin(a), z + depth * 0.53),
                a,
                radius * 0.18,
                depth * 0.48,
                radius * 0.040,
                mat,
                rows=7,
            )
        )
    water_z = z + depth * 1.027
    _surface_ripples(objects, f"{prefix}:surface", x, y, water_z + 0.004, (radius * 0.31, radius * 0.61), ripple_mat, broken=True)
    return water_z


def _waterfall(
    objects,
    prefix,
    x,
    y,
    start_z,
    end_z,
    start_radius,
    end_radius,
    mat,
    count,
    *,
    thickness=0.012,
    phase=0.0,
    droplets=True,
    water_mat=None,
    foam_mat=None,
):
    """Build torn laminar sheets that break into rivulets, drops and foam.

    Fountain water leaving a broad stone lip is not a collection of constant
    radius hoses.  This builder gives every spill a closed, flattened liquid
    cross-section, varies its width under gravity, tears it at a different
    height, and finishes it with a three-dimensional impact crown.
    """
    sheet_mat = water_mat or mat
    foam_mat = foam_mat or mat
    ribbons = []
    highlight_fragments = []
    aerated_streaks = []
    drop_specs = []
    crest_paths = []
    impacts = []

    def sample(i, angle, t):
        gravity_t = 0.035 * t + 0.965 * t * t
        radial_t = 0.055 * t + 0.945 * t ** 1.72
        rr = start_radius + (end_radius - start_radius) * radial_t
        rr += thickness * (1.4 + 1.1 * t) * math.sin(i * 1.91 + t * 18.7)
        aa = angle + (
            0.014 * math.sin(i * 0.77 + t * 14.9)
            + 0.006 * math.sin(i * 1.91 + t * 31.0)
        ) * t ** 1.15
        zz = start_z - (start_z - end_z) * gravity_t
        return rr, aa, zz

    for i in range(count):
        # Deterministic missing teeth keep the edge from looking mechanically
        # perforated, while broad neighbouring ribbons merge into short sheets.
        if (i * 11 + 5) % 13 in (0, 1, 2):
            continue
        a = phase + math.tau * i / count + 0.014 * math.sin(i * 3.17)
        width_noise = 0.5 + 0.5 * math.sin(i * 2.43 + 0.8)
        base_width = thickness * (9.0 + 15.0 * width_noise)
        if i % 9 in (2, 3):
            base_width *= 1.38
        break_t = 0.50 + 0.29 * (0.5 + 0.5 * math.sin(i * 1.63 + 0.4))
        main = []
        main_rows = 27
        for k in range(main_rows):
            t = break_t * k / (main_rows - 1)
            rr, aa, zz = sample(i, a, t)
            local_t = k / (main_rows - 1)
            breakup_taper = 0.23 + 0.77 * (1.0 - local_t) ** 0.55
            width_undulation = (
                0.86
                + 0.12 * math.sin(i * 1.33 + local_t * math.tau * 1.15)
                + 0.07 * math.sin(i * 0.71 + local_t * math.tau * 2.45)
            )
            width = base_width * breakup_taper * width_undulation
            depth = thickness * (
                0.78
                + 0.13 * math.sin(i * 0.91 + local_t * math.tau * 1.7)
                + 0.07 * math.sin(i * 1.4 + local_t * math.tau * 3.1)
            )
            main.append((x + rr * math.cos(aa), y + rr * math.sin(aa), zz, aa, width, depth))
        ribbons.append(main)

        # Some sheets briefly reconnect below the first tear; others atomise
        # completely.  These asymmetric fragments are a strong visual cue for
        # moving liquid rather than cable geometry.
        if i % 4 != 1:
            fragment_start = min(0.88, break_t + 0.045 + 0.025 * (i % 3))
            fragment_end = min(0.97, fragment_start + 0.11 + 0.035 * (i % 4))
            fragment = []
            fragment_rows = 11
            for k in range(fragment_rows):
                local_t = k / (fragment_rows - 1)
                t = fragment_start + (fragment_end - fragment_start) * local_t
                rr, aa, zz = sample(i, a, t)
                envelope = 0.18 + 0.82 * math.sin(math.pi * local_t) ** 0.58
                width = base_width * envelope * (
                    0.25 + 0.07 * math.sin(i * 0.8 + local_t * math.tau) ** 2
                )
                fragment.append(
                    (
                        x + rr * math.cos(aa),
                        y + rr * math.sin(aa),
                        zz,
                        aa,
                        width,
                        thickness * 0.58,
                    )
                )
            ribbons.append(fragment)

        # Entrained air forms short pale streaks inside a transparent sheet.
        # They never span the whole fall, so they read as moving turbulence
        # rather than as a second set of wires.
        for streak in range(1 if i % 3 else 2):
            streak_start = 0.10 + 0.18 * ((i * 3 + streak * 5) % 7) / 6
            streak_start += 0.08 * streak
            streak_end = min(break_t - 0.035, streak_start + 0.045 + 0.022 * ((i + streak) % 3))
            if streak_end <= streak_start + 0.025:
                continue
            foam_path = []
            for k in range(5):
                t = streak_start + (streak_end - streak_start) * k / 4
                rr, aa, zz = sample(i, a, t)
                lateral = base_width * (0.13 + 0.07 * streak) * math.sin(i * 1.9 + k)
                radius = thickness * (0.25 + 0.09 * math.sin(k * math.pi / 4) ** 2)
                foam_path.append(
                    (
                        x + rr * math.cos(aa) - lateral * math.sin(aa),
                        y + rr * math.sin(aa) + lateral * math.cos(aa),
                        zz,
                        radius,
                    )
                )
            aerated_streaks.append(foam_path)

        # Short broken specular seams show the sheet folds without outlining
        # the entire fall as another bright wire.
        if i % 4 == 0:
            glint_path = []
            for k in range(4):
                t = 0.10 + break_t * 0.42 * k / 3
                rr, aa, zz = sample(i, a, t)
                side = base_width * 0.42
                glint_path.append(
                    (
                        x + rr * math.cos(aa) - side * math.sin(aa),
                        y + rr * math.sin(aa) + side * math.cos(aa),
                        zz,
                    )
                )
            highlight_fragments.append(glint_path)

        crest = []
        angular_half = min(0.055, base_width * 0.48 / max(0.1, start_radius))
        for k in range(5):
            q = a - angular_half + 2.0 * angular_half * k / 4
            crest.append(
                (
                    x + start_radius * math.cos(q),
                    y + start_radius * math.sin(q),
                    start_z + thickness * (0.20 + 0.20 * math.sin(k * 2.1 + i)),
                )
            )
        crest_paths.append(crest)

        if droplets:
            for d in range(5):
                tt = min(0.985, break_t + 0.035 + d * (1.0 - break_t) / 5 + 0.018 * math.sin(i + d * 2.1))
                rr, aa, zz = sample(i, a, tt)
                lateral = base_width * 0.34 * math.sin(i * 1.4 + d * 2.2)
                drop_specs.append(
                    (
                        x + rr * math.cos(aa) - lateral * math.sin(aa),
                        y + rr * math.sin(aa) + lateral * math.cos(aa),
                        zz,
                        thickness * (0.72 + 0.34 * ((i + d) % 3)),
                        thickness * (2.1 + 0.75 * d),
                    )
                )
        landing_angle = a + 0.008 * math.sin(i * 0.77 + 14.9)
        landing_x = x + end_radius * math.cos(landing_angle)
        landing_y = y + end_radius * math.sin(landing_angle)
        impacts.append((landing_x, landing_y, end_z + 0.006, landing_angle, 0.39 + 0.08 * (i % 3)))

    ribbon_obj = _liquid_ribbon_mesh(f"{prefix}:torn_laminar_sheets", ribbons, sheet_mat)
    if ribbon_obj:
        objects.append(ribbon_obj)
    if highlight_fragments:
        objects.append(
            multi_curve_obj(
                f"{prefix}:broken_sheet_highlights",
                highlight_fragments,
                max(0.0011, thickness * 0.25),
                mat,
                "fountain-water",
                resolution=2,
            )
        )
    if crest_paths:
        objects.append(
            multi_curve_obj(
                f"{prefix}:aerated_lip_foam",
                crest_paths,
                max(0.0020, thickness * 0.52),
                foam_mat,
                "fountain-water",
                resolution=2,
            )
        )
    streak_obj = _variable_tube_mesh(f"{prefix}:entrained_air_streaks", aerated_streaks, mat, sides=6)
    if streak_obj:
        objects.append(streak_obj)
    droplet_obj = _batched_droplets(f"{prefix}:broken_droplets", drop_specs, foam_mat)
    if droplet_obj:
        objects.append(droplet_obj)
    _splash_geometry(objects, f"{prefix}:landing", impacts, sheet_mat, foam_mat)


def _crown_spray(
    objects,
    prefix,
    x,
    y,
    nozzle_z,
    landing_z,
    reach,
    mat,
    count=24,
    *,
    peak_height=0.68,
    centre=True,
    water_mat=None,
    foam_mat=None,
):
    """Build pressure jets with tapered cores, breakup and atomised tails."""
    liquid_mat = water_mat or mat
    foam_mat = foam_mat or mat
    core_paths = []
    fragment_paths = []
    drops = []
    impacts = []
    for i in range(count):
        if (i * 7 + 3) % 23 == 0:
            continue
        a = math.tau * i / count + 0.018 * math.sin(i * 2.73)
        height = peak_height * (0.80 + 0.30 * (0.5 + 0.5 * math.sin(i * 2.17)))
        reach_i = reach * (0.84 + 0.25 * (0.5 + 0.5 * math.cos(i * 1.47)))
        origin_radius = 0.020 + 0.028 * (0.5 + 0.5 * math.sin(i * 1.83))
        break_t = 0.72 + 0.18 * (0.5 + 0.5 * math.sin(i * 1.29 + 0.5))

        def jet_point(t):
            rr = origin_radius + (reach_i - origin_radius) * t
            rr += 0.009 * math.sin(i * 1.73 + t * 19.0) * t ** 1.4
            zz = nozzle_z + height * 4.0 * t * (1.0 - t) - (nozzle_z - landing_z) * t
            aa = a + 0.008 * math.sin(i + t * 16.0) * t
            return x + rr * math.cos(aa), y + rr * math.sin(aa), zz

        core = []
        for k in range(16):
            t = break_t * k / 15
            px, py, pz = jet_point(t)
            radius = 0.0082 * (1.0 - 0.48 * t) * (
                0.84 + 0.22 * math.sin(i * 1.7 + k * 1.3) ** 2
            )
            core.append((px, py, pz, radius))
        core_paths.append(core)

        if i % 3 != 1:
            frag_start = min(0.94, break_t + 0.035)
            frag_end = min(0.975, frag_start + 0.10)
            fragment = []
            for k in range(5):
                t = frag_start + (frag_end - frag_start) * k / 4
                px, py, pz = jet_point(t)
                fragment.append((px, py, pz, 0.0036 * (1.0 - 0.35 * k / 4)))
            fragment_paths.append(fragment)

        for d in range(5):
            t = min(0.99, break_t + 0.025 + d * (1.0 - break_t) / 5)
            px, py, pz = jet_point(t)
            lateral = 0.012 * math.sin(i * 1.31 + d * 2.47)
            drops.append(
                (
                    px - lateral * math.sin(a),
                    py + lateral * math.cos(a),
                    pz,
                    0.0042 + 0.0014 * ((i + d) % 3),
                    0.014 + 0.004 * (d % 3),
                )
            )
        impacts.append(
            (
                x + reach_i * math.cos(a),
                y + reach_i * math.sin(a),
                landing_z + 0.006,
                a,
                0.34 + 0.06 * (i % 3),
            )
        )

    core_obj = _variable_tube_mesh(f"{prefix}:tapered_pressure_jet_cores", core_paths, liquid_mat, sides=7)
    if core_obj:
        objects.append(core_obj)
    fragment_obj = _variable_tube_mesh(f"{prefix}:broken_jet_fragments", fragment_paths, liquid_mat, sides=6)
    if fragment_obj:
        objects.append(fragment_obj)
    drop_obj = _batched_droplets(f"{prefix}:airborne_mist_drops", drops, foam_mat, sides=6)
    if drop_obj:
        objects.append(drop_obj)
    _splash_geometry(objects, f"{prefix}:jet_landings", impacts, liquid_mat, foam_mat)
    if centre:
        plume_height = peak_height * 1.18
        objects.append(
            _profile_obj(
                f"{prefix}:cohesive_centre_plume",
                (x, y, nozzle_z),
                [
                    (0.006, 0.00, 0.0),
                    (0.027, plume_height * 0.05, 0.08),
                    (0.040, plume_height * 0.28, 0.13),
                    (0.029, plume_height * 0.56, 0.18),
                    (0.050, plume_height * 0.78, 0.22),
                    (0.025, plume_height * 0.94, 0.20),
                    (0.006, plume_height, 0.0),
                ],
                liquid_mat,
                "fountain-water",
                segments=48,
                lobes=7,
            )
        )
        plume_drops = []
        for i in range(26):
            a = i * 2.399963229728653
            rr = 0.025 + 0.045 * ((i * 17) % 23) / 22
            plume_drops.append(
                (
                    x + rr * math.cos(a),
                    y + rr * math.sin(a),
                    nozzle_z + plume_height * (0.72 + 0.30 * ((i * 13) % 29) / 28),
                    0.0035 + 0.0015 * (i % 3),
                    0.012 + 0.005 * (i % 4),
                )
            )
        plume_drop_obj = _batched_droplets(f"{prefix}:plume_breakup_drops", plume_drops, foam_mat, sides=6)
        if plume_drop_obj:
            objects.append(plume_drop_obj)


def _rosette(objects, prefix, x, y, z, angle, radius, mat):
    """Layered pointed-petal rose bouquet carved into a basin panel."""
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-math.sin(angle), math.cos(angle))
    verts, faces = [], []

    def add_petal(center_u, center_v, petal_angle, inner, length, width, depth, *, rows=7, serrated=False):
        start = len(verts)
        for row in range(rows):
            t = row / (rows - 1)
            envelope = max(0.006, math.sin(math.pi * t) ** 0.68)
            if serrated:
                envelope *= 1.0 + 0.09 * math.cos(5 * math.pi * t)
            along = inner + length * t
            petal_u = center_u + along * math.cos(petal_angle)
            petal_v = center_v + along * math.sin(petal_angle)
            across_u = -math.sin(petal_angle)
            across_v = math.cos(petal_angle)
            crown = depth * math.sin(math.pi * t) ** 1.25
            curl = depth * 0.28 * max(0.0, (t - 0.72) / 0.28) ** 2
            for lane in (-1.0, 0.0, 1.0):
                lateral = lane * width * 0.5 * envelope
                relief = radius * 0.018 + crown * (1.0 - 0.58 * abs(lane)) + curl
                local_u = petal_u + across_u * lateral
                local_v = petal_v + across_v * lateral
                verts.append(
                    (
                        x + tangent[0] * local_u + radial[0] * relief,
                        y + tangent[1] * local_u + radial[1] * relief,
                        z + local_v,
                    )
                )
        for row in range(rows - 1):
            base = start + row * 3
            nxt = base + 3
            faces.extend(((base, base + 1, nxt + 1, nxt), (base + 1, base + 2, nxt + 2, nxt + 1)))

    def add_bloom(center_u, center_v, bloom_radius, phase):
        for ring, (petals, inner, length, width, depth) in enumerate(
            (
                (10, 0.03, 0.82, 0.42, 0.18),
                (7, 0.02, 0.56, 0.39, 0.22),
                (5, 0.01, 0.34, 0.34, 0.25),
            )
        ):
            for i in range(petals):
                pa = phase + math.tau * i / petals + ring * 0.29
                add_petal(
                    center_u,
                    center_v,
                    pa,
                    bloom_radius * inner,
                    bloom_radius * length,
                    bloom_radius * width,
                    bloom_radius * depth,
                    rows=7,
                )

    add_bloom(0.0, 0.01 * radius, radius * 0.76, 0.10)
    add_bloom(-0.56 * radius, -0.05 * radius, radius * 0.46, 0.31)
    add_bloom(0.56 * radius, -0.05 * radius, radius * 0.46, -0.18)
    for side in (-1, 1):
        leaf_angle = 0.16 if side > 0 else math.pi - 0.16
        add_petal(
            side * radius * 0.62,
            -radius * 0.12,
            leaf_angle,
            0.0,
            radius * 0.63,
            radius * 0.35,
            radius * 0.12,
            rows=10,
            serrated=True,
        )
    objects.append(mesh_obj(f"{prefix}:carved_rose_bouquet", verts, faces, mat, "fountain-ornament", smooth=True))


def _natural_lawn(objects, prefix, x, y, z, inner, outer, mats, *, count=3000):
    """Create a dense mown lawn from curved, tapered leaf ribbons.

    This deliberately avoids bevelled curves: round constant-width curves read
    as green drinking straws at close range.  Each blade here has a flat leaf
    section, a tapered tip, independent lean and a small longitudinal curl.
    Several colour families, low dry thatch and broadleaf rosettes break the
    uniformity expected from a procedural point scatter.
    """
    blade_mats = [
        mats.get("fountain_lawn_dark", mats.get("grass_tuft", mats.get("grass"))),
        mats.get("fountain_lawn_mid", mats.get("grass", mats.get("grass_tuft"))),
        mats.get("fountain_lawn_light", mats.get("fountain_foliage_light", mats.get("grass"))),
    ]
    dry_mat = mats.get("fountain_lawn_dry", blade_mats[1])
    clover_mat = mats.get("fountain_clover", blade_mats[2])
    buckets = [[[], []] for _ in blade_mats]
    thatch_verts, thatch_faces = [], []

    def add_blade(bucket, bx, by, height, width, orientation, lean, curl, base_z):
        verts, faces = bucket
        start = len(verts)
        side_x, side_y = -math.sin(orientation), math.cos(orientation)
        lean_x, lean_y = math.cos(orientation), math.sin(orientation)
        rows = 6
        for row in range(rows):
            t = row / (rows - 1)
            centre_x = bx + lean_x * lean * t ** 1.45 + side_x * curl * math.sin(math.pi * t)
            centre_y = by + lean_y * lean * t ** 1.45 + side_y * curl * math.sin(math.pi * t)
            centre_z = base_z + height * (t - 0.055 * t * t)
            half_width = width * 0.5 * max(0.028, (1.0 - t) ** 0.72)
            # Slightly rotate the leaf section as it rises so highlights do
            # not align into a synthetic comb.
            twist = 0.22 * math.sin(t * math.pi + orientation * 1.7)
            sx = side_x * math.cos(twist) - lean_x * math.sin(twist)
            sy = side_y * math.cos(twist) - lean_y * math.sin(twist)
            verts.extend(
                [
                    (centre_x - sx * half_width, centre_y - sy * half_width, centre_z),
                    (centre_x + sx * half_width, centre_y + sy * half_width, centre_z),
                ]
            )
        for row in range(rows - 1):
            base = start + row * 2
            faces.append((base, base + 1, base + 3, base + 2))

    for i in range(count):
        angle = i * 2.399963229728653 + 0.11 * math.sin(i * 0.73)
        lane = ((i * 97) % 997 + 0.5) / 998.0
        rr = math.sqrt(inner * inner + (outer * outer - inner * inner) * lane)
        rr += 0.012 * math.sin(i * 2.91)
        bx = x + rr * math.cos(angle)
        by = y + rr * math.sin(angle)
        height = 0.035 + 0.050 * (0.5 + 0.5 * math.sin(i * 1.731 + 0.4))
        width = 0.0035 + 0.0035 * (0.5 + 0.5 * math.sin(i * 2.113))
        orientation = angle + 1.9 * math.sin(i * 1.217)
        lean = 0.012 + 0.038 * (0.5 + 0.5 * math.cos(i * 0.917))
        curl = 0.004 + 0.010 * math.sin(i * 1.313)
        add_blade(buckets[(i * 7 + i // 11) % len(buckets)], bx, by, height, width, orientation, lean, curl, z)

        # Low, pale cuttings form a physically plausible thatch layer between
        # the upright leaves and the dark ground surface.
        if i % 3 == 0:
            q = orientation + 1.15
            length = 0.030 + 0.035 * (0.5 + 0.5 * math.sin(i * 2.07))
            half_width = 0.0022
            base = len(thatch_verts)
            tx, ty = math.cos(q), math.sin(q)
            sx, sy = -ty, tx
            thatch_verts.extend(
                [
                    (bx - sx * half_width, by - sy * half_width, z + 0.0015),
                    (bx + sx * half_width, by + sy * half_width, z + 0.0015),
                    (bx + tx * length + sx * half_width * 0.15, by + ty * length + sy * half_width * 0.15, z + 0.006),
                    (bx + tx * length - sx * half_width * 0.15, by + ty * length - sy * half_width * 0.15, z + 0.006),
                ]
            )
            thatch_faces.append((base, base + 1, base + 2, base + 3))

    for index, ((verts, faces), mat) in enumerate(zip(buckets, blade_mats)):
        if verts:
            objects.append(mesh_obj(f"{prefix}:tapered_blade_family:{index}", verts, faces, mat, "landscaping", smooth=True))
    if thatch_verts:
        objects.append(mesh_obj(f"{prefix}:cut_thatch", thatch_verts, thatch_faces, dry_mat, "landscaping"))

    clover_verts, clover_faces = [], []
    rosette_count = max(48, count // 26)
    for i in range(rosette_count):
        angle = i * 2.399963229728653 + 0.47
        lane = ((i * 71) % 313 + 0.5) / 314.0
        rr = math.sqrt(inner * inner + (outer * outer - inner * inner) * lane)
        cx, cy = x + rr * math.cos(angle), y + rr * math.sin(angle)
        for leaflet in range(3):
            q = angle + math.tau * leaflet / 3 + 0.5 * math.sin(i)
            length = 0.020 + 0.012 * ((i + leaflet) % 4) / 3
            width = length * 0.70
            stem_x = cx + 0.005 * math.cos(q)
            stem_y = cy + 0.005 * math.sin(q)
            tip_x = cx + length * math.cos(q)
            tip_y = cy + length * math.sin(q)
            sx, sy = -math.sin(q), math.cos(q)
            base = len(clover_verts)
            clover_verts.extend(
                [
                    (stem_x, stem_y, z + 0.007),
                    (cx + length * 0.46 * math.cos(q) + sx * width * 0.5, cy + length * 0.46 * math.sin(q) + sy * width * 0.5, z + 0.011),
                    (tip_x + sx * width * 0.18, tip_y + sy * width * 0.18, z + 0.014),
                    (tip_x - sx * width * 0.18, tip_y - sy * width * 0.18, z + 0.014),
                    (cx + length * 0.46 * math.cos(q) - sx * width * 0.5, cy + length * 0.46 * math.sin(q) - sy * width * 0.5, z + 0.011),
                ]
            )
            clover_faces.append((base, base + 1, base + 2, base + 3, base + 4))
    if clover_verts:
        objects.append(mesh_obj(f"{prefix}:broadleaf_rosettes", clover_verts, clover_faces, clover_mat, "landscaping", smooth=True))


def _moulded_buttress(objects, prefix, x, y, z, angle, mat):
    """Classical tapered buttress with rounded mouldings and carved panel."""
    radial = (math.cos(angle), math.sin(angle))
    tangent = (-math.sin(angle), math.cos(angle))
    rings = (
        (0.00, 0.34, 0.39, -0.015),
        (0.055, 0.40, 0.44, 0.000),
        (0.125, 0.37, 0.41, 0.008),
        (0.185, 0.30, 0.34, 0.020),
        (0.470, 0.27, 0.30, 0.035),
        (0.585, 0.30, 0.33, 0.040),
        (0.640, 0.38, 0.40, 0.030),
        (0.705, 0.41, 0.43, 0.018),
        (0.765, 0.36, 0.39, 0.008),
    )
    segments = 20
    verts, faces = [], []
    exponent = 3.8
    for height, half_width, half_depth, shift in rings:
        for side in range(segments):
            q = math.tau * side / segments
            cu = math.copysign(abs(math.cos(q)) ** (2.0 / exponent), math.cos(q))
            cv = math.copysign(abs(math.sin(q)) ** (2.0 / exponent), math.sin(q))
            u = half_width * cu
            v = half_depth * cv + shift
            verts.append(
                (
                    x + tangent[0] * u + radial[0] * v,
                    y + tangent[1] * u + radial[1] * v,
                    z + height,
                )
            )
    for ring in range(len(rings) - 1):
        a0 = ring * segments
        a1 = a0 + segments
        for side in range(segments):
            nxt = (side + 1) % segments
            faces.append((a0 + side, a0 + nxt, a1 + nxt, a1 + side))
    faces.append(tuple(reversed(range(segments))))
    top = (len(rings) - 1) * segments
    faces.append(tuple(top + side for side in range(segments)))
    objects.append(mesh_obj(f"{prefix}:rounded_moulded_body", verts, faces, mat, "fountain", smooth=True))
    outer_depth = rings[4][2] + rings[4][3]
    objects.append(
        _leaf_relief(
            f"{prefix}:carved_acanthus_panel",
            (x + radial[0] * outer_depth, y + radial[1] * outer_depth, z + 0.385),
            angle,
            0.27,
            0.38,
            0.048,
            mat,
            rows=10,
        )
    )


def _wedge_paver(name, x, y, z, inner, outer, angle, half_angle, depth, mat):
    """Slightly irregular radial stone paver, replacing rotated cuboids."""
    a0 = angle - half_angle * (0.94 + 0.04 * math.sin(angle * 7.0))
    a1 = angle + half_angle * (0.96 + 0.03 * math.cos(angle * 5.0))
    r0 = inner + 0.006 * math.sin(angle * 11.0)
    r1 = outer + 0.008 * math.cos(angle * 9.0)
    top_z, bottom_z = z + depth * 0.5, z - depth * 0.5
    top = [
        (x + r0 * math.cos(a0), y + r0 * math.sin(a0), top_z),
        (x + r1 * math.cos(a0), y + r1 * math.sin(a0), top_z),
        (x + r1 * math.cos(a1), y + r1 * math.sin(a1), top_z),
        (x + r0 * math.cos(a1), y + r0 * math.sin(a1), top_z),
    ]
    bottom = [(px, py, bottom_z) for px, py, _ in top]
    obj = mesh_obj(
        name,
        top + bottom,
        [
            (0, 1, 2, 3),
            (7, 6, 5, 4),
            (0, 4, 5, 1),
            (1, 5, 6, 2),
            (2, 6, 7, 3),
            (3, 7, 4, 0),
        ],
        mat,
        "plaza",
    )
    bevel = obj.modifiers.new(name="hand_dressed_edges", type="BEVEL")
    bevel.width = min(0.008, depth * 0.12)
    bevel.segments = 2
    bevel.affect = "EDGES"
    obj.modifiers.new(name="stone_weighted_normals", type="WEIGHTED_NORMAL")
    return obj


def _basin_relief_band(objects, prefix, x, y, z, radius, mat, *, count=16, width=0.20, height=0.24):
    """Wrap individually modeled floral medallions around a basin wall."""
    for i in range(count):
        angle = math.tau * i / count
        _rosette(
            objects,
            f"{prefix}:carved_medallion:{i}",
            x + radius * math.cos(angle),
            y + radius * math.sin(angle),
            z,
            angle,
            min(width, height) * (0.46 + 0.04 * math.sin(i * 1.7) ** 2),
            mat,
        )


def _flower_bed(
    objects,
    prefix,
    x,
    y,
    z,
    inner,
    outer,
    mats,
    count=44,
    sectors=None,
    *,
    palette=None,
    cluster_count=1,
):
    """Build dense naturalistic foliage and clustered blossoms in batched meshes."""
    greens = [
        mats.get("fountain_foliage_dark", mats.get("grass_tuft", mats.get("shrub"))),
        mats.get("fountain_foliage_light", mats.get("shrub", mats.get("grass_tuft"))),
    ]
    palette = palette or ("flower_pink", "flower_purple", "flower_red", "flower_blue", "flower_white")
    flower_mats = [mats.get(key, mats.get("flower_pink", mats.get("flower_purple"))) for key in palette]
    yellow = mats.get("flower_yellow", flower_mats[0])
    stems = []
    leaf_buckets = [[[], []] for _ in greens]
    petal_buckets = [[[], []] for _ in flower_mats]
    center_verts, center_faces = [], []

    def allowed(angle):
        if not sectors:
            return True
        return any(lo <= (angle % math.tau) <= hi for lo, hi in sectors)

    bloom_index = 0
    for i in range(count * 3):
        a = (i * 2.399963229728653 + 0.17) % math.tau
        if not allowed(a):
            continue
        lane = ((i * 37) % 101 + 0.5) / 102.0
        rr = math.sqrt(inner * inner + (outer * outer - inner * inner) * lane)
        rr += 0.028 * math.sin(i * 3.7)
        px = x + rr * math.cos(a)
        py = y + rr * math.sin(a)
        h = 0.16 + 0.19 * (0.5 + 0.5 * math.sin(i * 1.71))
        lean_x = 0.025 * math.sin(i * 1.07)
        lean_y = 0.025 * math.cos(i * 0.83)
        stems.append(
            [
                (px, py, z),
                (px + lean_x * 0.18, py + lean_y * 0.18, z + h * 0.30),
                (px + lean_x * 0.58 + 0.006 * math.sin(i), py + lean_y * 0.58, z + h * 0.67),
                (px + lean_x, py + lean_y + 0.005 * math.cos(i * 1.3), z + h),
            ]
        )
        bucket = leaf_buckets[i % len(leaf_buckets)]
        for blade in range(3):
            la = a + (blade - 1) * 0.72 + 0.27 * math.sin(i * 0.51 + blade)
            blade_len = 0.13 + 0.075 * ((i + blade * 3) % 7) / 6
            blade_w = 0.022 + 0.008 * ((i + blade) % 3)
            base = len(bucket[0])
            side_x, side_y = -math.sin(la), math.cos(la)
            forward_x, forward_y = math.cos(la), math.sin(la)
            leaf_rows = 5
            for row in range(leaf_rows):
                t = row / (leaf_rows - 1)
                half_width = blade_w * 0.50 * max(0.035, math.sin(math.pi * min(0.94, t + 0.04)) ** 0.62)
                along = blade_len * (t + 0.08 * math.sin(math.pi * t))
                lift = h * 0.08 + h * (0.40 + 0.10 * blade) * math.sin(t * math.pi * 0.58)
                curl = 0.018 * math.sin(math.pi * t + i * 0.31)
                cx = px + forward_x * along + side_x * curl
                cy = py + forward_y * along + side_y * curl
                bucket[0].extend(
                    [
                        (cx - side_x * half_width, cy - side_y * half_width, z + lift),
                        (cx + side_x * half_width, cy + side_y * half_width, z + lift + 0.003 * math.sin(math.pi * t)),
                    ]
                )
            for row in range(leaf_rows - 1):
                row_base = base + row * 2
                bucket[1].append((row_base, row_base + 1, row_base + 3, row_base + 2))
        if i % 4 == 0 or bloom_index >= count * 2:
            continue
        bz = z + h
        for floret in range(cluster_count):
            floret_angle = math.tau * floret / max(1, cluster_count) + 0.31 * i
            offset = 0.033 if cluster_count > 1 else 0.0
            fx = px + offset * math.cos(floret_angle)
            fy = py + offset * math.sin(floret_angle)
            fz = bz + (0.014 * math.sin(floret_angle * 1.7) if cluster_count > 1 else 0.0)
            petal_bucket = petal_buckets[(i // 5 + i + floret) % len(petal_buckets)]
            petal_count = (5 + (i + floret) % 2) if cluster_count > 1 else 7 + i % 3
            bloom_scale = (0.027 if cluster_count > 1 else 0.042) + 0.010 * (0.5 + 0.5 * math.sin(i * 0.83 + floret))
            for p in range(petal_count):
                pa = math.tau * p / petal_count + 0.3 * math.sin(i + floret)
                base = len(petal_bucket[0])
                inner_x = fx + bloom_scale * 0.20 * math.cos(pa)
                inner_y = fy + bloom_scale * 0.20 * math.sin(pa)
                outer_x = fx + bloom_scale * 1.25 * math.cos(pa)
                outer_y = fy + bloom_scale * 1.25 * math.sin(pa)
                tangent_x = -math.sin(pa) * bloom_scale * 0.42
                tangent_y = math.cos(pa) * bloom_scale * 0.42
                petal_bucket[0].extend(
                    [
                        (inner_x, inner_y, fz + 0.005),
                        (outer_x + tangent_x, outer_y + tangent_y, fz + 0.011),
                        (outer_x, outer_y, fz + 0.022),
                        (outer_x - tangent_x, outer_y - tangent_y, fz + 0.011),
                    ]
                )
                petal_bucket[1].append((base, base + 1, base + 2, base + 3))
            base = len(center_verts)
            centre_radius = 0.012 if cluster_count > 1 else 0.020
            for k in range(8):
                q = math.tau * k / 8
                center_verts.append((fx + centre_radius * math.cos(q), fy + centre_radius * math.sin(q), fz + 0.024))
            center_faces.append(tuple(base + k for k in range(8)))
        bloom_index += 1
    if stems:
        objects.append(multi_curve_obj(f"{prefix}:curved_tapered_stems", stems, 0.0032, greens[0], "flowerplant", resolution=2))
    for index, ((verts, faces), mat) in enumerate(zip(leaf_buckets, greens)):
        if verts:
            objects.append(mesh_obj(f"{prefix}:blade_foliage:{index}", verts, faces, mat, "flowerplant"))
    for index, ((verts, faces), mat) in enumerate(zip(petal_buckets, flower_mats)):
        if verts:
            objects.append(mesh_obj(f"{prefix}:petal_cluster:{index}", verts, faces, mat, "flowerplant"))
    if center_verts:
        objects.append(mesh_obj(f"{prefix}:flower_centres", center_verts, center_faces, yellow, "flowerplant"))


def _pinecone_finial(objects, prefix, x, y, z, radius, height, mat, *, scales=9):
    """Classical acorn/pinecone terminal built from a turned core and relief scales."""
    objects.append(
        _profile_obj(
            f"{prefix}:turned_core",
            (x, y, z),
            [
                (0.01, 0.0),
                (radius * 0.75, height * 0.02),
                (radius, height * 0.14),
                (radius * 0.92, height * 0.58),
                (radius * 0.56, height * 0.86),
                (0.01, height),
            ],
            mat,
            "fountain-ornament",
            segments=96,
            lobes=scales,
            lobe_amplitude=0.035,
        )
    )
    for row, (row_z, row_radius, row_count) in enumerate(
        ((0.24, 0.92, scales), (0.43, 0.82, scales), (0.61, 0.66, max(6, scales - 2)), (0.77, 0.48, max(5, scales - 3)))
    ):
        for i in range(row_count):
            a = math.tau * (i + row * 0.5) / row_count
            rr = radius * row_radius
            objects.append(
                _leaf_relief(
                    f"{prefix}:scale:{row}:{i}",
                    (x + rr * math.cos(a), y + rr * math.sin(a), z + height * row_z),
                    a,
                    radius * 0.32,
                    height * 0.25,
                    radius * 0.085,
                    mat,
                    rows=6,
                )
            )
    objects.append(sphere_obj(f"{prefix}:top_bead", (x, y, z + height * 0.97), radius * 0.17, mat, "fountain-ornament"))


def _add_liquid_flow_detail(mat, *, lateral_scale=42.0, vertical_scale=2.6, strength=0.105):
    """Layer long, broken flow striations over a generic transparent material.

    The material callback is intentionally shared by the full urban generator
    and the standalone QA renderer.  Adding this node layer here keeps the
    production asset self-contained while turning isotropic glass noise into
    elongated turbulence that follows the predominantly vertical water sheets.
    """
    if mat is None or not mat.use_nodes or mat.node_tree is None:
        return
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    bsdf = nodes.get("Principled BSDF")
    if bsdf is None or "Normal" not in bsdf.inputs:
        return

    texcoord = nodes.new(type="ShaderNodeTexCoord")
    mapping = nodes.new(type="ShaderNodeMapping")
    mapping.vector_type = "POINT"
    mapping.inputs["Scale"].default_value = (lateral_scale, lateral_scale, vertical_scale)
    flow_noise = nodes.new(type="ShaderNodeTexNoise")
    flow_noise.inputs["Scale"].default_value = 1.0
    flow_noise.inputs["Detail"].default_value = 8.0
    flow_noise.inputs["Roughness"].default_value = 0.68
    flow_noise.inputs["Distortion"].default_value = 0.32
    flow_bump = nodes.new(type="ShaderNodeBump")
    flow_bump.inputs["Strength"].default_value = strength
    flow_bump.inputs["Distance"].default_value = 0.012

    existing_normal = None
    if bsdf.inputs["Normal"].is_linked:
        existing_normal = bsdf.inputs["Normal"].links[0].from_socket
    links.new(texcoord.outputs["Generated"], mapping.inputs["Vector"])
    links.new(mapping.outputs["Vector"], flow_noise.inputs["Vector"])
    links.new(flow_noise.outputs["Fac"], flow_bump.inputs["Height"])
    if existing_normal is not None:
        links.new(existing_normal, flow_bump.inputs["Normal"])
    links.new(flow_bump.outputs["Normal"], bsdf.inputs["Normal"])


def make_fountain_materials(make_mat):
    """Return the production material family used by both the pipeline and QA render."""
    specs = {
        "fountain_ivory": ((0.58, 0.55, 0.47, 1.0), dict(roughness=0.74, noise_strength=0.19, bump_strength=0.095, noise_scale=32, bump_scale=82)),
        "fountain_ivory_wet": ((0.27, 0.29, 0.24, 1.0), dict(roughness=0.28, noise_strength=0.14, bump_strength=0.050, noise_scale=18, coat_weight=0.20)),
        "fountain_sandstone": ((0.39, 0.25, 0.15, 1.0), dict(roughness=0.80, noise_strength=0.25, bump_strength=0.12, noise_scale=27, bump_scale=74)),
        "fountain_sandstone_wet": ((0.20, 0.12, 0.07, 1.0), dict(roughness=0.30, noise_strength=0.16, bump_strength=0.050, noise_scale=20, coat_weight=0.18)),
        "fountain_gray": ((0.245, 0.25, 0.24, 1.0), dict(roughness=0.77, noise_strength=0.21, bump_strength=0.105, noise_scale=36, bump_scale=88)),
        "fountain_gray_wet": ((0.13, 0.15, 0.15, 1.0), dict(roughness=0.26, noise_strength=0.10, bump_strength=0.038, noise_scale=18, coat_weight=0.22)),
        "fountain_moss": ((0.10, 0.16, 0.075, 1.0), dict(roughness=0.90, noise_strength=0.32, bump_strength=0.10, noise_scale=54, bump_scale=95)),
        "fountain_tile_blue": ((0.13, 0.31, 0.34, 1.0), dict(roughness=0.34, noise_strength=0.13, bump_strength=0.025, noise_scale=12, coat_weight=0.10)),
        "fountain_tile_gray": ((0.31, 0.35, 0.34, 1.0), dict(roughness=0.42, noise_strength=0.12, bump_strength=0.024, noise_scale=15)),
        "fountain_tile_light": ((0.58, 0.57, 0.51, 1.0), dict(roughness=0.46, noise_strength=0.11, bump_strength=0.025, noise_scale=18)),
        "fountain_paver_warm": ((0.49, 0.43, 0.34, 1.0), dict(roughness=0.78, noise_strength=0.19, bump_strength=0.07, noise_scale=28, bump_scale=65)),
        "fountain_paver_mid": ((0.40, 0.40, 0.36, 1.0), dict(roughness=0.80, noise_strength=0.18, bump_strength=0.065, noise_scale=31, bump_scale=71)),
        "fountain_paver_cool": ((0.34, 0.38, 0.39, 1.0), dict(roughness=0.77, noise_strength=0.17, bump_strength=0.06, noise_scale=25, bump_scale=68)),
        "water": ((0.035, 0.14, 0.17, 0.52), dict(roughness=0.045, noise_strength=0.024, bump_strength=0.030, noise_scale=8, bump_scale=13, transmission=0.94, ior=1.333, coat_weight=0.25)),
        "water_sheet": ((0.16, 0.34, 0.37, 0.27), dict(roughness=0.032, noise_strength=0.035, bump_strength=0.018, noise_scale=12, bump_scale=26, transmission=0.94, ior=1.333, coat_weight=0.25)),
        "water_foam": ((0.78, 0.91, 0.91, 0.55), dict(roughness=0.20, noise_strength=0.11, bump_strength=0.045, noise_scale=24, bump_scale=38, transmission=0.24, ior=1.333, coat_weight=0.16)),
        "water_glint": ((0.48, 0.73, 0.75, 0.28), dict(roughness=0.045, noise_strength=0.040, bump_strength=0.020, noise_scale=18, bump_scale=31, transmission=0.72, ior=1.333, coat_weight=0.30)),
        "fountain_lawn_base": ((0.018, 0.062, 0.014, 1.0), dict(roughness=0.97, noise_strength=0.42, bump_strength=0.12, noise_scale=43, bump_scale=96)),
        "fountain_lawn_dark": ((0.018, 0.105, 0.025, 1.0), dict(roughness=0.93, noise_strength=0.25, bump_strength=0.018, noise_scale=38)),
        "fountain_lawn_mid": ((0.045, 0.205, 0.052, 1.0), dict(roughness=0.92, noise_strength=0.23, bump_strength=0.020, noise_scale=34)),
        "fountain_lawn_light": ((0.105, 0.285, 0.065, 1.0), dict(roughness=0.91, noise_strength=0.20, bump_strength=0.018, noise_scale=31)),
        "fountain_lawn_dry": ((0.30, 0.24, 0.095, 1.0), dict(roughness=0.97, noise_strength=0.27, bump_strength=0.018, noise_scale=41)),
        "fountain_clover": ((0.052, 0.175, 0.040, 1.0), dict(roughness=0.90, noise_strength=0.19, bump_strength=0.016, noise_scale=28)),
        "fountain_foliage_dark": ((0.025, 0.16, 0.045, 1.0), dict(roughness=0.88, noise_strength=0.20, bump_strength=0.025, noise_scale=34)),
        "fountain_foliage_light": ((0.08, 0.31, 0.08, 1.0), dict(roughness=0.86, noise_strength=0.18, bump_strength=0.022, noise_scale=29)),
        "flower_pink": ((0.80, 0.16, 0.36, 1.0), dict(roughness=0.49, noise_strength=0.10, bump_strength=0.014, noise_scale=18)),
        "flower_red": ((0.65, 0.035, 0.025, 1.0), dict(roughness=0.50, noise_strength=0.10, bump_strength=0.014, noise_scale=19)),
        "flower_blue": ((0.18, 0.25, 0.74, 1.0), dict(roughness=0.48, noise_strength=0.09, bump_strength=0.012, noise_scale=17)),
        "flower_white": ((0.90, 0.88, 0.78, 1.0), dict(roughness=0.52, noise_strength=0.06, bump_strength=0.010, noise_scale=16)),
    }
    materials = {
        key: make_mat(f"urban_mat_{key}", color, **settings)
        for key, (color, settings) in specs.items()
    }
    _add_liquid_flow_detail(materials["water_sheet"], strength=0.115)
    _add_liquid_flow_detail(materials["water_glint"], lateral_scale=55.0, vertical_scale=3.2, strength=0.075)
    return materials


class PublicSpaceFactory:
    def __init__(self, mats):
        self.mats = mats

    def _mat(self, key, fallback="stone"):
        return self.mats.get(key, self.mats[fallback])

    def _royal_quatrefoil(self, x, y, z, fid):
        objects = []
        prefix = f"urban:fountain:{fid}:royal_quatrefoil"
        stone = self._mat("fountain_ivory")
        wet = self._mat("fountain_ivory_wet", "fountain_ivory")
        water = self._mat("water")
        sheet = self._mat("water_sheet", "water")
        glint = self._mat("water_glint", "water")
        foam = self._mat("water_foam", "water")
        grass = self._mat("fountain_lawn_base", "grass")
        tiles = [
            self._mat("fountain_tile_blue", "stone"),
            self._mat("fountain_tile_gray", "stone"),
            self._mat("fountain_tile_light", "stone"),
        ]

        objects.append(cylinder_obj(f"{prefix}:presentation_plinth", (x, y, z + 0.045), 3.08, 0.09, stone, "fountain", vertices=160))
        objects.append(cylinder_obj(f"{prefix}:presentation_lawn", (x, y, z + 0.102), 2.86, 0.035, grass, "landscaping", vertices=160))
        objects.append(torus_obj(f"{prefix}:perimeter_bead", (x, y, z + 0.105), 2.96, 0.055, stone, "fountain"))
        _natural_lawn(objects, f"{prefix}:natural_lawn", x, y, z + 0.121, 2.43, 2.82, self.mats, count=7000)
        objects.append(
            _profile_obj(
                f"{prefix}:quatrefoil_basin",
                (x, y, z),
                [
                    (1.98, 0.13, 0.13),
                    (2.15, 0.18, 0.14),
                    (2.24, 0.28, 0.14),
                    (2.22, 0.49, 0.14),
                    (2.13, 0.60, 0.14),
                    (1.82, 0.66, 0.13),
                    (1.66, 0.57, 0.13),
                    (1.67, 0.27, 0.13),
                    (1.98, 0.13, 0.13),
                ],
                stone,
                "fountain",
                segments=160,
                lobes=4,
            )
        )
        objects.append(
            _profile_obj(
                f"{prefix}:quatrefoil_rolled_rim",
                (x, y, z),
                [(1.72, 0.55, 0.13), (1.84, 0.64, 0.13), (2.00, 0.67, 0.14), (2.10, 0.61, 0.14), (1.96, 0.55, 0.14), (1.72, 0.55, 0.13)],
                stone,
                "fountain",
                segments=160,
                lobes=4,
            )
        )
        objects.append(
            _profile_obj(
                f"{prefix}:inner_wetline",
                (x, y, z),
                [(1.64, 0.48, 0.13), (1.71, 0.55, 0.13), (1.72, 0.62, 0.13), (1.64, 0.59, 0.13), (1.64, 0.48, 0.13)],
                wet,
                "fountain-wet-stone",
                segments=160,
                lobes=4,
            )
        )
        _quatrefoil_tiles(objects, prefix, x, y, z + 0.285, 1.61, tiles, step=0.27)
        objects.append(
            _rippled_water_surface(
                f"{prefix}:lower_pool_agitated_skin",
                (x, y, z + 0.585),
                1.66,
                water,
                segments=160,
                rings=16,
                lobes=4,
                lobe_amplitude=0.13,
                agitation=1.18,
            )
        )
        for i in range(4):
            a = math.pi / 4 + i * math.pi / 2
            bx, by = x + 1.95 * math.cos(a), y + 1.95 * math.sin(a)
            _moulded_buttress(objects, f"{prefix}:corner_buttress:{i}", bx, by, z + 0.04, a, stone)
        for i in range(4):
            a = i * math.pi / 2
            rr = 2.59
            _rosette(objects, f"{prefix}:panel:{i}", x + rr * math.cos(a), y + rr * math.sin(a), z + 0.38, a, 0.38, stone)

        _stone_base(objects, prefix, x, y, z + 0.585, stone, 0.68)
        _pedestal(objects, f"{prefix}:lower", x, y, z + 0.86, 0.74, 0.50, stone, lobes=16)
        lower_water_z = _ornate_bowl(objects, f"{prefix}:lower", x, y, z + 1.48, 1.13, 0.47, stone, water, lobes=18, accent=wet, ripple_mat=water)
        _pedestal(objects, f"{prefix}:upper", x, y, z + 1.93, 0.54, 0.35, stone, lobes=12)
        upper_water_z = _ornate_bowl(objects, f"{prefix}:upper", x, y, z + 2.38, 0.75, 0.36, stone, water, lobes=16, accent=wet, ripple_mat=water)
        objects.append(
            _profile_obj(
                f"{prefix}:jet_finial",
                (x, y, z + 2.72),
                [(0.01, 0), (0.21, 0.02), (0.24, 0.10), (0.16, 0.19), (0.20, 0.31), (0.10, 0.42), (0.055, 0.48), (0.01, 0.50)],
                stone,
                "fountain-ornament",
                segments=96,
                lobes=8,
                lobe_amplitude=0.055,
            )
        )
        _waterfall(objects, f"{prefix}:upper_spill", x, y, upper_water_z + 0.018, lower_water_z + 0.015, 0.81, 1.01, glint, 34, thickness=0.0048, water_mat=sheet, foam_mat=foam)
        _waterfall(objects, f"{prefix}:lower_spill", x, y, lower_water_z + 0.018, z + 0.60, 1.22, 1.55, glint, 48, phase=math.pi / 48, thickness=0.0052, water_mat=sheet, foam_mat=foam)
        _crown_spray(objects, f"{prefix}:inner_spray", x, y, z + 3.22, upper_water_z, 0.70, glint, count=24, peak_height=0.78, centre=True, water_mat=glint, foam_mat=foam)
        _crown_spray(objects, f"{prefix}:outer_dome", x, y, z + 3.20, lower_water_z, 1.36, glint, count=38, peak_height=0.98, centre=False, water_mat=glint, foam_mat=foam)
        _surface_ripples(objects, f"{prefix}:lower_pool", x, y, z + 0.596, (0.44, 0.86, 1.31), water, broken=True)
        return objects

    def _planted_three_tier(self, x, y, z, fid):
        objects = []
        prefix = f"urban:fountain:{fid}:planted_three_tier"
        stone = self._mat("fountain_sandstone")
        wet = self._mat("fountain_sandstone_wet", "fountain_sandstone")
        water = self._mat("water")
        sheet = self._mat("water_sheet", "water")
        glint = self._mat("water_glint", "water")
        foam = self._mat("water_foam", "water")
        soil = self._mat("soil", "stone")
        pavers = [
            self._mat("fountain_paver_warm", "stone"),
            self._mat("fountain_paver_mid", "stone"),
        ]

        objects.append(cylinder_obj(f"{prefix}:foundation", (x, y, z + 0.035), 2.82, 0.07, pavers[0], "plaza", vertices=160))
        _annular_pavers(objects, prefix, x, y, z + 0.074, 2.58, 2.82, pavers, rings=1, segments=56)
        objects.append(
            _profile_obj(
                f"{prefix}:outer_planter",
                (x, y, z),
                [
                    (2.43, 0.06), (2.64, 0.08), (2.70, 0.16), (2.67, 0.25),
                    (2.58, 0.31), (2.58, 0.47), (2.65, 0.54), (2.47, 0.59),
                    (2.34, 0.51), (2.31, 0.18), (2.43, 0.06),
                ],
                stone,
                "fountain",
                segments=160,
            )
        )
        objects.append(torus_obj(f"{prefix}:planter_lower_bead", (x, y, z + 0.17), 2.61, 0.055, stone, "fountain-ornament"))
        objects.append(torus_obj(f"{prefix}:planter_crown_bead", (x, y, z + 0.55), 2.52, 0.065, stone, "fountain-ornament"))
        _basin_relief_band(objects, f"{prefix}:outer_planter_relief", x, y, z + 0.37, 2.62, stone, count=20, width=0.19, height=0.23)
        objects.append(_radial_surface(f"{prefix}:flower_soil", (x, y, z + 0.515), 2.32, soil, "soil", inner_radius=1.28, segments=160))
        _flower_bed(
            objects,
            f"{prefix}:flower_ring",
            x,
            y,
            z + 0.525,
            1.38,
            2.29,
            self.mats,
            count=150,
            palette=("flower_pink", "flower_pink", "flower_white", "flower_purple"),
            cluster_count=3,
        )
        objects.append(_profile_obj(f"{prefix}:inner_pool_wall", (x, y, z), _ring_profile(0.41, 1.34, 1.10, 0.27, lip=0.060), stone, "fountain", segments=128))
        objects.append(_profile_obj(f"{prefix}:inner_pool_wetline", (x, y, z), [(1.08, 0.54), (1.14, 0.60), (1.17, 0.66), (1.08, 0.64), (1.08, 0.54)], wet, "fountain-wet-stone", segments=128))
        objects.append(_rippled_water_surface(f"{prefix}:lower_pool_agitated_skin", (x, y, z + 0.625), 1.095, water, segments=128, rings=14, agitation=1.05))
        _stone_base(objects, prefix, x, y, z + 0.625, stone, 0.60)

        _pedestal(objects, f"{prefix}:tier1", x, y, z + 0.90, 0.66, 0.45, stone, lobes=14)
        z1 = _ornate_bowl(objects, f"{prefix}:tier1", x, y, z + 1.45, 1.04, 0.39, stone, water, lobes=16, accent=wet, ripple_mat=water)
        _pedestal(objects, f"{prefix}:tier2", x, y, z + 1.82, 0.47, 0.34, stone, lobes=12)
        z2 = _ornate_bowl(objects, f"{prefix}:tier2", x, y, z + 2.21, 0.74, 0.31, stone, water, lobes=14, accent=wet, ripple_mat=water)
        _pedestal(objects, f"{prefix}:tier3", x, y, z + 2.50, 0.34, 0.25, stone, lobes=10)
        z3 = _ornate_bowl(objects, f"{prefix}:tier3", x, y, z + 2.78, 0.48, 0.24, stone, water, lobes=12, accent=wet, ripple_mat=water)
        _pinecone_finial(objects, f"{prefix}:acorn_finial", x, y, z + 3.01, 0.22, 0.47, stone, scales=8)
        _waterfall(objects, f"{prefix}:spill3", x, y, z3 + 0.012, z2, 0.52, 0.67, glint, 26, thickness=0.0046, water_mat=sheet, foam_mat=foam)
        _waterfall(objects, f"{prefix}:spill2", x, y, z2 + 0.014, z1, 0.80, 0.95, glint, 34, phase=0.08, thickness=0.0048, water_mat=sheet, foam_mat=foam)
        _waterfall(objects, f"{prefix}:spill1", x, y, z1 + 0.016, z + 0.64, 1.13, 1.00, glint, 44, phase=0.035, thickness=0.0050, water_mat=sheet, foam_mat=foam)
        _crown_spray(objects, f"{prefix}:top_spray", x, y, z + 3.50, z3, 0.47, glint, count=22, peak_height=0.55, centre=True, water_mat=glint, foam_mat=foam)
        _surface_ripples(objects, f"{prefix}:lower_pool", x, y, z + 0.634, (0.36, 0.67, 0.96), water, broken=True)
        return objects

    def _compact_four_tier(self, x, y, z, fid):
        objects = []
        prefix = f"urban:fountain:{fid}:compact_four_tier"
        stone = self._mat("fountain_gray")
        wet = self._mat("fountain_gray_wet", "fountain_gray")
        water = self._mat("water")
        sheet = self._mat("water_sheet", "water")
        glint = self._mat("water_glint", "water")
        foam = self._mat("water_foam", "water")
        pavers = [
            self._mat("fountain_paver_cool", "stone"),
            self._mat("fountain_paver_mid", "stone"),
        ]

        objects.append(cylinder_obj(f"{prefix}:subbase", (x, y, z + 0.035), 2.34, 0.07, pavers[0], "plaza", vertices=160))
        _annular_pavers(objects, prefix, x, y, z + 0.073, 2.10, 2.34, pavers, rings=1, segments=48)
        objects.append(
            _profile_obj(
                f"{prefix}:stepped_basin",
                (x, y, z),
                [
                    (0.01, 0.03), (2.08, 0.03), (2.21, 0.09), (2.24, 0.17),
                    (2.17, 0.24), (2.03, 0.29), (2.04, 0.37), (1.91, 0.43),
                    (1.86, 0.50), (1.66, 0.55), (1.52, 0.50), (1.49, 0.36),
                    (0.01, 0.36),
                ],
                stone,
                "fountain",
                segments=160,
            )
        )
        for suffix, zz, rr, minor in (
            ("lower_roll", z + 0.14, 2.15, 0.055),
            ("middle_roll", z + 0.30, 2.00, 0.050),
            ("crown_roll", z + 0.49, 1.78, 0.060),
        ):
            objects.append(torus_obj(f"{prefix}:{suffix}", (x, y, zz), rr, minor, stone, "fountain-ornament"))
        _basin_relief_band(objects, f"{prefix}:basin_relief", x, y, z + 0.355, 2.055, stone, count=22, width=0.17, height=0.20)
        objects.append(_profile_obj(f"{prefix}:basin_wetline", (x, y, z), [(1.47, 0.40), (1.54, 0.48), (1.58, 0.53), (1.48, 0.51), (1.47, 0.40)], wet, "fountain-wet-stone", segments=160))
        objects.append(_rippled_water_surface(f"{prefix}:catch_water_agitated_skin", (x, y, z + 0.505), 1.50, water, segments=160, rings=15, agitation=1.12))
        _stone_base(objects, prefix, x, y, z + 0.505, stone, 0.53)
        tier_specs = [
            (0.78, 0.43, 0.90, 0.34, 18, 0.44),
            (1.46, 0.34, 0.70, 0.29, 16, 0.36),
            (2.04, 0.27, 0.52, 0.24, 14, 0.29),
            (2.52, 0.21, 0.37, 0.19, 12, 0.23),
        ]
        water_levels = []
        for index, (base_z, ped_r, bowl_r, bowl_d, lobes, ped_h) in enumerate(tier_specs):
            _pedestal(objects, f"{prefix}:tier{index}", x, y, z + base_z, ped_h, ped_r, stone, lobes=max(8, lobes - 4))
            water_levels.append(
                _ornate_bowl(
                    objects,
                    f"{prefix}:tier{index}",
                    x,
                    y,
                    z + base_z + ped_h * 0.82,
                    bowl_r,
                    bowl_d,
                    stone,
                    water,
                    lobes=lobes,
                    accent=wet,
                    ripple_mat=water,
                )
            )
        _pinecone_finial(objects, f"{prefix}:pinecone_finial", x, y, z + 2.89, 0.18, 0.39, stone, scales=8)
        targets = [z + 0.515] + water_levels[:-1]
        for index, (level, target, spec) in enumerate(zip(water_levels, targets, tier_specs)):
            bowl_r = spec[2]
            _waterfall(
                objects,
                f"{prefix}:spill{index}",
                x,
                y,
                level + 0.012,
                target,
                bowl_r * 1.10,
                max(0.39, bowl_r * (1.06 if index == 0 else 1.18)),
                glint,
                max(24, 42 - index * 5),
                phase=index * 0.07,
                thickness=0.0042 + 0.00025 * (3 - index),
                water_mat=sheet,
                foam_mat=foam,
            )
        _crown_spray(objects, f"{prefix}:finial_spray", x, y, z + 3.30, water_levels[-1], 0.34, glint, count=18, peak_height=0.45, centre=True, water_mat=glint, foam_mat=foam)
        _surface_ripples(objects, f"{prefix}:catch_pool", x, y, z + 0.515, (0.38, 0.77, 1.19), water, broken=True)
        return objects

    def _radial_garden(self, x, y, z, fid):
        objects = []
        prefix = f"urban:fountain:{fid}:radial_garden"
        stone = self._mat("fountain_ivory")
        wet = self._mat("fountain_ivory_wet", "fountain_ivory")
        water = self._mat("water")
        sheet = self._mat("water_sheet", "water")
        glint = self._mat("water_glint", "water")
        foam = self._mat("water_foam", "water")
        soil = self._mat("soil", "stone")
        pavers = [
            self._mat("fountain_paver_warm", "stone"),
            self._mat("fountain_paver_mid", "stone"),
            self._mat("fountain_paver_cool", "stone"),
        ]

        objects.append(cylinder_obj(f"{prefix}:paved_roundel", (x, y, z + 0.035), 3.18, 0.07, pavers[1], "plaza", vertices=160))
        _annular_pavers(objects, prefix, x, y, z + 0.074, 2.73, 3.16, pavers, rings=2, segments=56)
        objects.append(torus_obj(f"{prefix}:perimeter_curb", (x, y, z + 0.105), 3.02, 0.075, stone, "fountain"))
        objects.append(torus_obj(f"{prefix}:garden_inner_curb", (x, y, z + 0.125), 1.35, 0.052, stone, "fountain"))
        objects.append(_radial_surface(f"{prefix}:garden_soil", (x, y, z + 0.105), 2.72, soil, "soil", inner_radius=1.34, segments=160))
        # Four jointed stone walks divide the planting into the same formal
        # quadrants as reference 4.  Individual blocks keep the paths tactile.
        for quadrant in range(4):
            a = quadrant * math.pi / 2
            for slab in range(5):
                inner = 1.39 + slab * 0.265
                outer = inner + 0.242
                objects.append(
                    _wedge_paver(
                        f"{prefix}:radial_walk_dressed_wedge:{quadrant}:{slab}",
                        x,
                        y,
                        z + 0.145,
                        inner,
                        outer,
                        a + 0.006 * math.sin(quadrant * 3 + slab),
                        0.165 / ((inner + outer) * 0.5),
                        0.075,
                        pavers[(quadrant + slab) % len(pavers)],
                    )
                )
        sectors = []
        gap = 0.15
        for q in range(4):
            sectors.append((q * math.pi / 2 + gap, (q + 1) * math.pi / 2 - gap))
        _flower_bed(objects, f"{prefix}:quartered_beds", x, y, z + 0.125, 1.49, 2.64, self.mats, count=190, sectors=sectors)

        objects.append(_profile_obj(f"{prefix}:central_pool_wall", (x, y, z), _ring_profile(0.12, 1.31, 1.07, 0.43, lip=0.070), stone, "fountain", segments=144))
        _basin_relief_band(objects, f"{prefix}:central_pool_relief", x, y, z + 0.315, 1.305, stone, count=14, width=0.15, height=0.18)
        objects.append(_profile_obj(f"{prefix}:central_wetline", (x, y, z), [(1.05, 0.43), (1.10, 0.49), (1.12, 0.54), (1.05, 0.52), (1.05, 0.43)], wet, "fountain-wet-stone", segments=144))
        objects.append(_rippled_water_surface(f"{prefix}:central_pool_agitated_skin", (x, y, z + 0.515), 1.06, water, segments=144, rings=14, agitation=1.08))
        _stone_base(objects, prefix, x, y, z + 0.515, stone, 0.50)
        _pedestal(objects, f"{prefix}:column", x, y, z + 0.79, 0.60, 0.37, stone, lobes=14)
        z1 = _ornate_bowl(objects, f"{prefix}:lower", x, y, z + 1.30, 0.87, 0.34, stone, water, lobes=16, accent=wet, ripple_mat=water)
        _pedestal(objects, f"{prefix}:upper_column", x, y, z + 1.62, 0.37, 0.27, stone, lobes=12)
        z2 = _ornate_bowl(objects, f"{prefix}:upper", x, y, z + 1.93, 0.55, 0.25, stone, water, lobes=14, accent=wet, ripple_mat=water)
        _pinecone_finial(objects, f"{prefix}:bud_finial", x, y, z + 2.17, 0.16, 0.31, stone, scales=7)
        _waterfall(objects, f"{prefix}:upper_spill", x, y, z2 + 0.012, z1, 0.60, 0.78, glint, 30, thickness=0.0045, water_mat=sheet, foam_mat=foam)
        _waterfall(objects, f"{prefix}:lower_spill", x, y, z1 + 0.014, z + 0.525, 0.95, 0.96, glint, 38, phase=0.055, thickness=0.0048, water_mat=sheet, foam_mat=foam)
        _crown_spray(objects, f"{prefix}:top_spray", x, y, z + 2.50, z2, 0.48, glint, count=20, peak_height=0.50, centre=True, water_mat=glint, foam_mat=foam)
        _surface_ripples(objects, f"{prefix}:central_pool", x, y, z + 0.525, (0.34, 0.65, 0.91), water, broken=True)
        return objects

    def create_fountain(self, request: UrbanAssetRequest):
        fid = request.params.get("id", "0")
        x, y, z = request.location
        variant = request.params.get("variant", 0)
        if isinstance(variant, str):
            try:
                variant_index = FOUNTAIN_VARIANTS.index(variant)
            except ValueError as exc:
                raise ValueError(f"Unknown fountain variant {variant!r}; expected one of {FOUNTAIN_VARIANTS}") from exc
        else:
            variant_index = int(variant) % len(FOUNTAIN_VARIANTS)
        builders = (
            self._royal_quatrefoil,
            self._planted_three_tier,
            self._compact_four_tier,
            self._radial_garden,
        )
        objects = builders[variant_index](x, y, z, fid)
        variant_name = FOUNTAIN_VARIANTS[variant_index]
        return objects, {
            "id": f"fountain_{fid}",
            "type": "fountain",
            "variant": variant_name,
            "center": [x, y, z],
            "component_count": len(objects),
            "procedural": True,
            "reference_image": FOUNTAIN_REFERENCES[variant_name],
            "modeling_quality": "production_high_detail",
            "detail_systems": [
                "deep_profiled_stonework",
                "fluted_bowls_and_pedestals",
                "botanical_bas_relief",
                "wet_stone_weathering",
                "submerged_tiles_or_jointed_pavers",
                "dense_procedural_planting",
                "rounded_moulded_architectural_supports",
                "tapered_leaf_lawn_and_broadleaf_groundcover",
                "geometrically_displaced_water_surfaces",
            ],
            "water_system": "closed_torn_liquid_sheets_tapered_pressure_jets_breakup_droplets_impact_crowns_foam_and_ripples",
        }

    def create_sculpture(self, request: UrbanAssetRequest):
        sid = request.params.get("id", "0")
        x, y, _ = request.location
        objs = [
            cube_obj(f"urban:sculpture:plinth:{sid}", (x, y, 0.32), (1.65, 1.65, 0.64), self.mats["stone"], "sculpture", bevel=0.06),
            torus_obj(f"urban:sculpture:ring_outer:{sid}", (x, y, 1.45), 0.55, 0.055, self.mats["bronze"], "sculpture", rotation=(math.radians(72), 0, math.radians(20))),
            torus_obj(f"urban:sculpture:ring_inner:{sid}", (x, y, 1.52), 0.32, 0.045, self.mats["bronze"], "sculpture", rotation=(math.radians(30), math.radians(68), 0)),
            ellipsoid_obj(f"urban:sculpture:bronze_core:{sid}", (x, y, 1.48), (0.24, 0.18, 0.36), self.mats["bronze"], "sculpture", segments=24),
            cylinder_between(f"urban:sculpture:support_a:{sid}", (x - 0.35, y - 0.22, 0.64), (x - 0.10, y, 1.15), 0.045, self.mats["bronze"], "sculpture"),
            cylinder_between(f"urban:sculpture:support_b:{sid}", (x + 0.35, y + 0.22, 0.64), (x + 0.12, y, 1.18), 0.045, self.mats["bronze"], "sculpture"),
        ]
        return objs, {"id": f"sculpture_{sid}", "type": "sculpture", "center": [x, y, 0]}

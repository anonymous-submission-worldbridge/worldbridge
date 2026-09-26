"""Lossless (float-roundoff tolerance) factoring of baked native LeafFactory leaves.

This is NOT decimation/LOD: every original polygon and leaf is rendered. The
authoring generator's deterministic transforms recover repeated leaf meshes.
Fails closed before replacing a canopy when reconstruction cannot be proven.
"""
import gc
import math
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix, Vector
import urban_v1_full_07_trees as botanical
from build_urban_v1_full_13_dynamic2 import Nodes, attribute


def leaf_transforms(seed):
    records = []
    previous_templates, previous_append = (
        botanical._leaf_templates,
        botanical._append_leaf,
    )

    def record(verts, faces, template, location, direction, size, roll):
        r = Vector(direction).normalized().to_track_quat(
            "Z", "Y"
        ).to_matrix().to_4x4() @ Matrix.Rotation(roll, 4, "Z")
        records.append(
            (
                np.array(location, dtype=np.float64),
                np.array(r.to_3x3(), dtype=np.float64),
                float(size),
                int(template),
            )
        )

    temp = bpy.data.collections.new("DYN2_TRANSFORM_REPLAY_ONLY")
    try:
        botanical._leaf_templates = lambda _: list(range(5))
        botanical._append_leaf = record
        botanical.build_botanical_tree_master(temp, seed, [])
    finally:
        botanical._leaf_templates, botanical._append_leaf = (
            previous_templates,
            previous_append,
        )
        for obj in list(temp.objects):
            bpy.data.objects.remove(obj, do_unlink=True)
        bpy.data.collections.remove(temp)
    return records


def factor_legacy(canopy):
    mesh = canopy.data
    seed = int(canopy["c2w_treefactory_seed"])
    records = leaf_transforms(seed)
    if len(records) != int(canopy["c2w_merged_leaffactory_instances"]):
        raise RuntimeError("Leaf replay count mismatch")
    nv, nf, nl = len(mesh.vertices), len(mesh.polygons), len(mesh.loops)
    vertices = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", vertices)
    vertices = vertices.reshape(-1, 3)
    starts = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    totals = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    loops = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loops)
    pmax = np.maximum.reduceat(loops, starts)
    pmin = np.minimum.reduceat(loops, starts)
    prefix = np.maximum.accumulate(pmax)
    cuts = np.flatnonzero(pmin[1:] > prefix[:-1]) + 1
    # Retain unreferenced native vertices too. Some LeafFactory templates have
    # unused trailing points, so max(referenced vertex)+1 is NOT the leaf size.
    ends = np.concatenate(
        (prefix[cuts - 1] + 1, pmin[cuts], np.array([nv], dtype=np.int32))
    )
    polyends = np.concatenate((cuts, cuts, np.array([nf], dtype=np.int64)))
    order = np.argsort(ends, kind="stable")
    ends, polyends = ends[order], polyends[order]
    del pmax, pmin, prefix, cuts
    templates = []
    assignments = []
    begin = 0
    facebegin = 0
    maxerror = 0.0
    maxpolys = 0
    for number, (location, rotation, size, template_index) in enumerate(records):
        # A normalized native leaf has a centered AABB and maximum extent 1.
        # Select the first complete centered native leaf, not an overlapping
        # stem fragment belonging to the following leaf.
        limit = min(nv, begin + 80000)
        local = (
            (vertices[begin:limit].astype(np.float64) - location)
            @ np.linalg.inv(rotation).T
            / size
        )
        outside = np.flatnonzero(np.max(np.abs(local), axis=1) > 0.50008)
        stop = begin + int(outside[0]) if len(outside) else limit
        possible = np.flatnonzero((ends > begin) & (ends <= stop))
        chosen = None
        for candidate in possible:
            end = int(ends[candidate])
            part = local[: end - begin]
            lo, hi = part.min(axis=0), part.max(axis=0)
            if (
                np.max(np.abs(lo + hi)) < 0.00008
                and abs(float(np.max(hi - lo)) - 1) < 0.00008
            ):
                chosen = int(candidate)
                break
        if chosen is None:
            nearby = []
            for candidate in np.flatnonzero((ends > begin) & (ends < stop + 100))[-8:]:
                part = local[: int(ends[candidate]) - begin]
                lo, hi = part.min(axis=0), part.max(axis=0)
                nearby.append(
                    (
                        int(ends[candidate]) - begin,
                        list(lo + hi),
                        float(np.max(hi - lo)),
                    )
                )
            raise RuntimeError(
                f'Cannot recover native leaf boundary: seed={seed}, leaf={number}, offset={begin}, stop={stop}, templates={len(templates)}, sizes={[len(t["vertices"]) for t in templates]}, nearby={nearby}'
            )
        end, faceend = int(ends[chosen]), int(polyends[chosen])
        coordinates = local[: end - begin]
        loopbegin = int(starts[facebegin])
        loopend = int(starts[faceend]) if faceend < nf else nl
        face_indices = loops[loopbegin:loopend] - begin
        face_sizes = totals[facebegin:faceend]
        if face_indices.min() < 0 or face_indices.max() >= end - begin:
            raise RuntimeError("Face crosses leaf boundary")
        match = None
        for k, t in enumerate(templates):
            if (
                t["vertices"].shape != coordinates.shape
                or t["sizes"].shape != face_sizes.shape
            ):
                continue
            if np.max(np.abs(t["vertices"] - coordinates)) > 0.00008:
                continue
            if not np.array_equal(t["sizes"], face_sizes) or not np.array_equal(
                t["indices"], face_indices
            ):
                continue
            match = k
            break
        if match is None:
            templates.append(
                {
                    "vertices": coordinates.copy(),
                    "sizes": face_sizes.copy(),
                    "indices": face_indices.copy(),
                }
            )
            match = len(templates) - 1
            if len(templates) > 128:
                raise RuntimeError(
                    "Too many unique native templates; refusing approximate replacement"
                )
        reconstructed = (templates[match]["vertices"] @ rotation.T) * size + location
        error = float(np.max(np.abs(reconstructed - vertices[begin:end])))
        maxerror = max(maxerror, error)
        if error > 2e-5:
            raise RuntimeError(
                "Rest-geometry reconstruction error exceeds 20 micrometres"
            )
        assignments.append(match)
        maxpolys += faceend - facebegin
        begin, facebegin = end, faceend
    if begin != nv or facebegin != nf or maxpolys != nf:
        raise RuntimeError("Incomplete native geometry coverage")
    del vertices, starts, totals, loops, ends, polyends, local
    gc.collect()
    return (
        records,
        templates,
        assignments,
        {
            "source_mesh": mesh.name,
            "source_library": mesh.library.filepath if mesh.library else None,
            "original_vertices": nv,
            "original_polygons": nf,
            "leaves": len(records),
            "unique_templates": len(templates),
            "max_rest_coordinate_error_m": maxerror,
            "instanced_polygon_count": sum(
                len(templates[i]["sizes"]) for i in assignments
            ),
            "instanced_vertex_count": sum(
                len(templates[i]["vertices"]) for i in assignments
            ),
            "decimated_polygons": 0,
        },
    )


def factor(canopy):
    """Recover vertex blocks by repeated native leaf transforms, not face order.

    Blender mesh validation can reorder faces and leave unused vertices. The
    five-template sequence repeats inside the first authored leaf cluster.
    Every inferred block is subsequently verified over the ENTIRE canopy.
    """
    mesh = canopy.data
    seed = int(canopy["c2w_treefactory_seed"])
    records = leaf_transforms(seed)
    nv, nf, nl = len(mesh.vertices), len(mesh.polygons), len(mesh.loops)
    if len(records) != int(canopy["c2w_merged_leaffactory_instances"]):
        raise RuntimeError("Leaf replay count mismatch")
    xyz = np.empty(nv * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", xyz)
    xyz = xyz.reshape(-1, 3)

    def to_local(values, record):
        return (values - record[0]) @ np.linalg.inv(record[1]).T / record[2]

    def to_world(values, record):
        return values @ record[1].T * record[2] + record[0]

    expected = to_world(to_local(xyz[0], records[0]), records[5])
    candidates = np.flatnonzero(np.max(np.abs(xyz[:150000] - expected), axis=1) < 2e-5)
    lengths = None
    for stride in candidates:
        stride = int(stride)
        if stride < 1000 or stride * 2 > nv:
            continue
        labels = np.full(stride, -1, dtype=np.int8)
        for k in range(5):
            mapped = to_world(to_local(xyz[:stride], records[k]), records[k + 5])
            match = np.max(np.abs(mapped - xyz[stride : 2 * stride]), axis=1) < 2e-5
            labels[match] = k
        change = np.flatnonzero(np.diff(labels) != 0) + 1
        if len(change) != 4 or not np.array_equal(
            labels[np.r_[0, change]], np.arange(5)
        ):
            continue
        sizes = np.diff(np.r_[0, change, stride])
        candidate = {records[k][3]: int(sizes[k]) for k in range(5)}
        if sum(candidate[r[3]] for r in records) != nv:
            continue
        lengths = candidate
        break
    if lengths is None:
        raise RuntimeError("Native five-template repetition could not be proven")
    print("NATIVE_VERTEX_BLOCKS", seed, lengths, flush=True)
    sizes = np.array([lengths[r[3]] for r in records], dtype=np.int64)
    ends = np.cumsum(sizes)
    begins = np.r_[0, ends[:-1]]
    canonical = {}
    maxerror = 0.0
    for begin, end, record in zip(begins, ends, records):
        index = record[3]
        if index not in canonical:
            canonical[index] = to_local(xyz[begin:end].astype(np.float64), record)
        error = float(
            np.max(np.abs(to_world(canonical[index], record) - xyz[begin:end]))
        )
        if error > 2e-5:
            raise RuntimeError(f"Native coordinate mismatch {seed=} {begin=} {error=}")
        maxerror = max(maxerror, error)
    del xyz
    starts = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_start", starts)
    totals = np.empty(nf, dtype=np.int32)
    mesh.polygons.foreach_get("loop_total", totals)
    loops = np.empty(nl, dtype=np.int32)
    mesh.loops.foreach_get("vertex_index", loops)
    mins = np.minimum.reduceat(loops, starts)
    maxs = np.maximum.reduceat(loops, starts)
    ids = np.searchsorted(ends, mins, side="right")
    if np.any(ids != np.searchsorted(ends, maxs, side="right")):
        raise RuntimeError("A native polygon crosses recovered leaf blocks")
    counts = np.bincount(ids, minlength=len(records))
    order = np.argsort(ids, kind="stable")
    offsets = np.r_[0, np.cumsum(counts)]
    print(
        "NATIVE_TOPOLOGY_VARIANTS",
        seed,
        {
            t: len(set(int(counts[i]) for i, r in enumerate(records) if r[3] == t))
            for t in lengths
        },
        flush=True,
    )
    del mins, maxs, ids
    templates = []
    assignments = []
    known = {}
    for number, record in enumerate(records):
        faces = order[offsets[number] : offsets[number + 1]]
        lengths_face = totals[faces]
        maximum = int(lengths_face.max())
        grid = starts[faces, None] + np.arange(maximum)[None, :]
        valid = np.arange(maximum)[None, :] < lengths_face[:, None]
        indices = np.full(grid.shape, -1, dtype=np.int32)
        indices[valid] = loops[grid[valid]] - begins[number]
        sorted_faces = np.lexsort(
            tuple(indices[:, k] for k in range(maximum - 1, -1, -1))
        )
        indices = indices[sorted_faces]
        lengths_face = lengths_face[sorted_faces]
        flat = indices[indices >= 0]
        import hashlib

        key = (
            record[3],
            hashlib.sha256(flat.tobytes() + lengths_face.tobytes()).digest(),
        )
        if key not in known:
            known[key] = len(templates)
            templates.append(
                {
                    "vertices": canonical[record[3]],
                    "indices": flat.copy(),
                    "sizes": lengths_face.copy(),
                }
            )
            if len(templates) > 128:
                raise RuntimeError(
                    "Too many true native topology variants to share safely"
                )
        assignments.append(known[key])
    proof = {
        "source_mesh": mesh.name,
        "source_library": mesh.library.filepath if mesh.library else None,
        "original_vertices": nv,
        "original_polygons": nf,
        "leaves": len(records),
        "unique_templates": len(templates),
        "max_rest_coordinate_error_m": maxerror,
        "instanced_polygon_count": sum(len(templates[i]["sizes"]) for i in assignments),
        "instanced_vertex_count": sum(
            len(templates[i]["vertices"]) for i in assignments
        ),
        "decimated_polygons": 0,
    }
    if proof["instanced_polygon_count"] != nf or proof["instanced_vertex_count"] != nv:
        raise RuntimeError("Incomplete native coverage")
    gc.collect()
    return records, templates, assignments, proof


def install(canopy):
    records, templates, assignments, proof = factor(canopy)
    original_materials = list(canopy.data.materials)
    collection = bpy.data.collections.new("DYN2_NATIVE_LEAF_TEMPLATES::" + canopy.name)
    pivots = []
    for index, t in enumerate(templates):
        ends = np.cumsum(t["sizes"])
        begins = np.concatenate(([0], ends[:-1]))
        faces = [tuple(t["indices"][a:b]) for a, b in zip(begins, ends)]
        mesh = bpy.data.meshes.new("DYN2_ExactLeafMesh_" + str(index))
        mesh.from_pydata(t["vertices"], [], faces)
        mesh.update()
        for mat in original_materials:
            mesh.materials.append(mat)
        obj = bpy.data.objects.new(f"DYN2_ExactLeaf_{index:03d}", mesh)
        collection.objects.link(obj)
        # First native vertex is the pivot: an actual source-mesh vertex, fixed
        # under the local breeze, not a made-up trunk/global rotation centre.
        pivots.append(t["vertices"][0])
    points = bpy.data.meshes.new("DYN2_LeafAttachmentPoints")
    points.from_pydata([r[0] for r in records], [], [])
    points.update()
    rotations = [tuple(Matrix(r[1]).to_euler()) for r in records]
    scales = np.array([r[2] for r in records])
    attribute(points, "dyn2_rotation", rotations)
    attribute(points, "dyn2_scale", scales)
    attribute(points, "dyn2_template", assignments)
    attribute(
        points, "dyn2_pivot", [pivots[i] * s for i, s in zip(assignments, scales)]
    )
    canopy.data = points
    for modifier in list(canopy.modifiers):
        canopy.modifiers.remove(modifier)
    n = Nodes(canopy, "DYN2_NativeLeafInstances_Breeze")
    original = n.attr("dyn2_rotation", "FLOAT_VECTOR")
    phase = n.math(
        "ADD", n.math("MULTIPLY", n.xyz[0], 1.3), n.math("MULTIPLY", n.xyz[1], 0.8)
    )
    flutter = n.math(
        "MULTIPLY",
        n.math("SINE", n.math("ADD", phase, n.math("MULTIPLY", n.time, 7.3))),
        0.075,
    )
    slow = n.math("MULTIPLY", n.wave(0.7, 0.5, 2.4), 0.055)
    rotation = n.vector(
        "ADD", original, n.vec(flutter, slow, n.math("MULTIPLY", flutter, 0.18))
    )
    pivot = n.attr("dyn2_pivot", "FLOAT_VECTOR")

    def rotated(angle):
        node = n.n.new("ShaderNodeVectorRotate")
        node.rotation_type = "EULER_XYZ"
        n.l.new(pivot, node.inputs["Vector"])
        n.l.new(angle, node.inputs["Rotation"])
        return node.outputs["Vector"]

    offset = n.vector("SUBTRACT", rotated(original), rotated(rotation))
    n.l.new(offset, n.set.inputs["Offset"])
    info = n.n.new("GeometryNodeCollectionInfo")
    info.inputs["Collection"].default_value = collection
    info.inputs["Separate Children"].default_value = True
    info.inputs["Reset Children"].default_value = True
    instance = n.n.new("GeometryNodeInstanceOnPoints")
    instance.inputs["Pick Instance"].default_value = True
    n.l.new(n.set.outputs["Geometry"], instance.inputs["Points"])
    n.l.new(info.outputs["Instances"], instance.inputs["Instance"])
    n.l.new(n.attr("dyn2_template"), instance.inputs["Instance Index"])
    n.l.new(rotation, instance.inputs["Rotation"])
    scale = n.attr("dyn2_scale")
    n.l.new(n.vec(scale, scale, scale), instance.inputs["Scale"])
    out = next(node for node in n.n if node.bl_idname == "NodeGroupOutput")
    n.l.new(instance.outputs["Instances"], out.inputs["Geometry"])
    canopy["dynamic2_native_instance_proof"] = str(proof)
    return proof

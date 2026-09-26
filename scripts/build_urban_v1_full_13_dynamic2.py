#!/usr/bin/env python3
"""Non-destructive full-scene dynamics: exact assets, bounded local deformation.

Open the STATIC master with --disable-depsgraph-on-file-load before this script.
All placement roots/interiors survive. This is analytical animation, not CFD.
"""
from __future__ import annotations
import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_urban_v1_full_13_dynamic as old

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
OUT = STATIC.with_name(STATIC.name + "-dynamic2")
FPS, END, G, SPEED = 24, 384, 9.81, 2.0
UPPER_WATER, LOWER_WATER = 0.02 + 2.38 + 0.36 * 1.027, 0.02 + 1.48 + 0.47 * 1.027


def matrix(o):
    return (
        matrix(o.parent) @ o.matrix_parent_inverse @ o.matrix_basis
        if o.parent
        else o.matrix_basis.copy()
    )


def bounds(o, m):
    p = [m @ Vector(v) for v in o.bound_box]
    return np.array(
        [
            [min(v[i] for v in p) for i in range(3)],
            [max(v[i] for v in p) for i in range(3)],
        ]
    )


def overlap(a, b, margin=0.0):
    return bool(np.all(a[0] < b[1] + margin) and np.all(b[0] < a[1] + margin))


def swept_collision(a, va, b, vb, seconds, margin=0.12):
    """Continuous slab test; no frame-sampling tunnelling for fixed heading cars."""
    enter, leave = 0.0, seconds
    for k in range(3):
        clearance = margin if k < 2 else 0.0
        v = va[k] - vb[k]
        if abs(v) < 1e-10:
            if a[1, k] + clearance <= b[0, k] or b[1, k] + clearance <= a[0, k]:
                return False
        else:
            t0 = (b[0, k] - a[1, k] - clearance) / v
            t1 = (b[1, k] - a[0, k] + clearance) / v
            enter, leave = max(enter, min(t0, t1)), min(leave, max(t0, t1))
            if leave < enter:
                return False
    return leave >= enter


class Nodes:
    def __init__(self, obj, name):
        self.g = bpy.data.node_groups.new(name, "GeometryNodeTree")
        self.g.interface.new_socket(
            name="Geometry", in_out="INPUT", socket_type="NodeSocketGeometry"
        )
        self.g.interface.new_socket(
            name="Geometry", in_out="OUTPUT", socket_type="NodeSocketGeometry"
        )
        self.n, self.l = self.g.nodes, self.g.links
        inp, out = self.n.new("NodeGroupInput"), self.n.new("NodeGroupOutput")
        self.set = self.n.new("GeometryNodeSetPosition")
        self.l.new(inp.outputs["Geometry"], self.set.inputs["Geometry"])
        self.l.new(self.set.outputs["Geometry"], out.inputs["Geometry"])
        obj.modifiers.new(name, "NODES").node_group = self.g
        self.pos = self.n.new("GeometryNodeInputPosition").outputs[0]
        self.time = self.n.new("GeometryNodeInputSceneTime").outputs["Seconds"]
        sep = self.n.new("ShaderNodeSeparateXYZ")
        self.l.new(self.pos, sep.inputs[0])
        self.xyz = list(sep.outputs)

    def wire(self, value, target):
        if isinstance(value, (float, int, tuple, list)):
            target.default_value = value
        else:
            self.l.new(value, target)

    def math(self, op, a, b=0):
        n = self.n.new("ShaderNodeMath")
        n.operation = op
        self.wire(a, n.inputs[0])
        self.wire(b, n.inputs[1])
        return n.outputs[0]

    def vec(self, x=0.0, y=0.0, z=0.0):
        n = self.n.new("ShaderNodeCombineXYZ")
        for value, s in zip((x, y, z), n.inputs):
            self.wire(value, s)
        return n.outputs[0]

    def vector(self, op, a, b):
        n = self.n.new("ShaderNodeVectorMath")
        n.operation = op
        self.wire(a, n.inputs[0])
        self.wire(b, n.inputs["Scale"] if op == "SCALE" else n.inputs[1])
        return n.outputs[0]

    def attr(self, name, kind="FLOAT"):
        n = self.n.new("GeometryNodeInputNamedAttribute")
        n.data_type = kind
        n.inputs["Name"].default_value = name
        return n.outputs["Attribute"]

    def wave(self, kx, ky, omega, phase=0.0):
        p = self.math(
            "ADD",
            self.math("MULTIPLY", self.xyz[0], kx),
            self.math("MULTIPLY", self.xyz[1], ky),
        )
        return self.math(
            "SINE",
            self.math(
                "ADD",
                self.math("SUBTRACT", p, self.math("MULTIPLY", self.time, omega)),
                phase,
            ),
        )


def attribute(mesh, name, array):
    a = np.asarray(array, dtype=np.float32)
    vec = a.ndim == 2
    attr = mesh.attributes.new(name, "FLOAT_VECTOR" if vec else "FLOAT", "POINT")
    attr.data.foreach_set("vector" if vec else "value", a.ravel())


def localize(root):
    target, mapping = old.copy_collection_objects(
        root.instance_collection, "DYN2::" + root["placement_id"]
    )
    root.instance_collection = target
    for original, o in mapping.items():
        o.name = "DYN2::" + original.name
        o["dynamic2_source_object"] = original.name
    return mapping


def wind(mapping, cache, report):
    for original, o in mapping.items():
        source = original.instance_collection
        if not source or not source.name.startswith(old.TREE_COLLECTION_PREFIX):
            continue
        if source.as_pointer() not in cache:
            coll, parts = old.copy_collection_objects(
                source, "DYN2::Wind::" + source.name
            )
            for native, part in parts.items():
                part.name = "DYN2::" + native.name
                if part.type != "MESH" or not native.get(
                    "c2w_genuine_leaffactory_mesh"
                ):
                    continue
                n = Nodes(part, "DYN2_LocalFoliageBreeze")
                # The trunk/root never moves. Spatially varying centimetre-scale
                # response avoids a rigid whole-canopy rotation or screen warp.
                height = n.math(
                    "MINIMUM",
                    n.math(
                        "MAXIMUM",
                        n.math("DIVIDE", n.math("SUBTRACT", n.xyz[2], 1.8), 5.5),
                        0.0,
                    ),
                    1.0,
                )
                weight = n.math("MULTIPLY", height, height)
                phase = (sum(map(ord, source.name)) % 61) * 0.17
                sway = n.math("MULTIPLY", n.wave(0.7, 0.45, 2.4, phase), 0.045)
                flutter = n.math("MULTIPLY", n.wave(7.2, 5.7, 10.7, phase), 0.008)
                x = n.math("MULTIPLY", weight, n.math("ADD", sway, flutter))
                y = n.math(
                    "MULTIPLY",
                    weight,
                    n.math("MULTIPLY", n.wave(0.6, 0.8, 3.1, phase), 0.018),
                )
                n.l.new(
                    n.vec(x, y, n.math("MULTIPLY", flutter, 0.25)),
                    n.set.inputs["Offset"],
                )
                part["dynamic2_role"] = "foliage_only"
                report["canopies"].append(
                    {
                        "object": part.name,
                        "vertices": len(part.data.vertices),
                        "source_mesh": part.data.name,
                        "max_component_offset_m": [0.053, 0.018, 0.002],
                    }
                )
            cache[source.as_pointer()] = coll
        o.instance_collection = cache[source.as_pointer()]
        report["instances"] += 1


def advect_material(o, velocity, cache, gravity_top=None):
    """Advect original texture inputs in physical object coordinates (no 4D morph)."""
    for idx, slot in enumerate(o.material_slots):
        src = slot.material
        if not src or not src.use_nodes:
            continue
        key = (src.as_pointer(), tuple(velocity), gravity_top)
        if key not in cache:
            mat = src.copy()
            mat.name = "DYN2::" + src.name
            nt = mat.node_tree
            for node in list(nt.nodes):
                if node.bl_idname not in {
                    "ShaderNodeTexNoise",
                    "ShaderNodeTexWave",
                    "ShaderNodeTexVoronoi",
                }:
                    continue
                s = node.inputs.get("Vector")
                if s is None:
                    continue
                prior = (
                    s.links[0].from_socket
                    if s.is_linked
                    else nt.nodes.new("ShaderNodeTexCoord").outputs["Object"]
                )
                if gravity_top is not None:
                    # Material coordinates follow free-fall travel time instead
                    # of translating falling-water detail at constant velocity.
                    coord = nt.nodes.new("ShaderNodeTexCoord")
                    separate = nt.nodes.new("ShaderNodeSeparateXYZ")
                    nt.links.new(coord.outputs["Object"], separate.inputs[0])
                    height = nt.nodes.new("ShaderNodeMath")
                    height.operation = "SUBTRACT"
                    height.inputs[0].default_value = gravity_top
                    nt.links.new(separate.outputs["Z"], height.inputs[1])
                    clamp = nt.nodes.new("ShaderNodeMath")
                    clamp.operation = "MAXIMUM"
                    nt.links.new(height.outputs[0], clamp.inputs[0])
                    factor = nt.nodes.new("ShaderNodeMath")
                    factor.operation = "MULTIPLY"
                    factor.inputs[1].default_value = 2 / G
                    nt.links.new(clamp.outputs[0], factor.inputs[0])
                    travel = nt.nodes.new("ShaderNodeMath")
                    travel.operation = "SQRT"
                    nt.links.new(factor.outputs[0], travel.inputs[0])
                    combine = nt.nodes.new("ShaderNodeCombineXYZ")
                    nt.links.new(separate.outputs["X"], combine.inputs[0])
                    nt.links.new(separate.outputs["Y"], combine.inputs[1])
                    nt.links.new(travel.outputs[0], combine.inputs[2])
                    prior = combine.outputs[0]
                add = nt.nodes.new("ShaderNodeVectorMath")
                add.operation = "ADD"
                nt.links.new(prior, add.inputs[0])
                for frame in (1, END):
                    add.inputs[1].default_value = (
                        (0.0, 0.0, -(frame - 1) / FPS)
                        if gravity_top is not None
                        else tuple(-v * (frame - 1) / FPS for v in velocity)
                    )
                    add.inputs[1].keyframe_insert("default_value", frame=frame)
                nt.links.new(add.outputs[0], s)
            old.finish_animation(nt, linear=True)
            cache[key] = mat
        old.local_material_slot(o, idx, cache[key])


def surface(o, river):
    # Pin every boundary vertex, not a rectangular bounding-box approximation.
    o.data = o.data.copy()
    edges = np.zeros(len(o.data.vertices), dtype=np.int32)
    counts = defaultdict(int)
    for p in o.data.polygons:
        for e in p.edge_keys:
            counts[tuple(sorted(e))] += 1
    for e, c in counts.items():
        if c == 1:
            edges[list(e)] = 1
    attribute(o.data, "dyn2_interior", 1.0 - edges)
    n = Nodes(o, "DYN2_DispersiveSurface")
    waves = []
    # Long waves resolved by the native grid; small ripples stay in the shader.
    for wavelength, angle, a in (
        ((10.0, math.pi / 2, 0.010), (6.0, 1.0, 0.004))
        if river
        else ((4.0, 0.9, 0.009), (2.8, 2.1, 0.004))
    ):
        k = math.tau / wavelength
        kx, ky = k * math.cos(angle), k * math.sin(angle)
        omega = math.sqrt(G * k * math.tanh(k * (0.65 if river else 1.85))) + (
            0.3 * ky if river else 0.0
        )
        waves.append(n.math("MULTIPLY", n.wave(kx, ky, omega), a))
    z = n.math("MULTIPLY", n.math("ADD", *waves), n.attr("dyn2_interior"))
    n.l.new(n.vec(z=z), n.set.inputs["Offset"])
    o["dynamic2_role"] = "river_surface" if river else "lake_surface"
    return {
        "object": o.name,
        "boundary_vertices_pinned": int(edges.sum()),
        "amplitude_bound_m": 0.014 if river else 0.013,
        "mean_current_mps": 0.3 if river else 0.0,
        "dispersion": "omega = sqrt(g*k*tanh(k*h)) + U dot k",
    }


def fountain_drops(o):
    """Reuse every native droplet component; assign an exact ballistic trajectory."""
    name = o.name
    if not any(
        x in name
        for x in (
            "airborne_mist",
            "broken_droplets",
            "plume_breakup",
            "landings:impa",
            ":landing:impact",
        )
    ):
        return None
    count = len(o.data.vertices)
    block = 16 if "broken_droplets" in name else 14
    if count % block:
        raise RuntimeError("Unexpected native droplet topology: " + name)
    coords = np.empty(count * 3, dtype=np.float32)
    o.data.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    centres = coords.reshape(-1, block, 3).mean(axis=1)
    records = []
    for j, c in enumerate(centres):
        angle = math.atan2(c[1], c[0] + 10.8)
        if "airborne_mist" in name:
            inner = "inner_spray" in name
            ids = [i for i in range(24 if inner else 38) if (i * 7 + 3) % 23 != 0]
            i = ids[j // 5]
            angle = math.tau * i / (24 if inner else 38) + 0.018 * math.sin(i * 2.73)
            H = (0.78 if inner else 0.98) * (
                0.8 + 0.3 * (0.5 + 0.5 * math.sin(i * 2.17))
            )
            reach = (0.7 if inner else 1.36) * (
                0.84 + 0.25 * (0.5 + 0.5 * math.cos(i * 1.47))
            )
            radius = 0.020 + 0.028 * (0.5 + 0.5 * math.sin(i * 1.83))
            T = math.sqrt(8 * H / G)
            nozzle = 3.24 if inner else 3.22
            land = UPPER_WATER if inner else LOWER_WATER
            vz = (4 * H - (nozzle - land)) / T
            vr = (reach - radius) / T
            t0 = (0.72 + 0.18 * (0.5 + 0.5 * math.sin(i * 1.29 + 0.5))) * T
            p = (
                Vector(
                    (-10.8 + radius * math.cos(angle), radius * math.sin(angle), nozzle)
                )
                + Vector((vr * math.cos(angle), vr * math.sin(angle), vz)) * t0
                + Vector((0, 0, -0.5 * G * t0 * t0))
            )
            v = (vr * math.cos(angle), vr * math.sin(angle), vz - G * t0)
            life = T - t0
        elif "broken_droplets" in name:
            upper = "upper_spill" in name
            top, land, r0, r1 = (
                (UPPER_WATER + 0.018, LOWER_WATER + 0.015, 0.81, 1.01)
                if upper
                else (LOWER_WATER + 0.018, 0.62, 1.22, 1.55)
            )
            T = math.sqrt(2 * (top - land) / G)
            t0 = 0.60 * T
            vr = (r1 - r0) / T
            p = Vector(
                (
                    -10.8 + (r0 + vr * t0) * math.cos(angle),
                    (r0 + vr * t0) * math.sin(angle),
                    top - 0.5 * G * t0 * t0,
                )
            )
            v = (vr * math.cos(angle), vr * math.sin(angle), -G * t0)
            life = T - t0
        elif "plume_breakup" in name:
            p = Vector((-10.8 + 0.04 * math.cos(angle), 0.04 * math.sin(angle), 4.16))
            v = (0.52 * math.cos(angle), 0.52 * math.sin(angle), 0.0)
            life = math.sqrt(2 * (4.16 - UPPER_WATER) / G)
        else:
            land = (
                UPPER_WATER + 0.006
                if "inner_spray" in name
                else LOWER_WATER + 0.006
                if ("outer_dome" in name or "upper_spill" in name)
                else 0.626
            )
            p = Vector((c[0], c[1], land))
            vz = 0.65 + 0.2 * (j % 5) / 4
            v = (0.16 * math.cos(angle), 0.16 * math.sin(angle), vz)
            life = 2 * vz / G
        records.append((tuple(p), v, life, ((j * 0.61803398875) % 1) * life))
    return install_ballistic_geometry(o, block, records, coords, centres)


def fit_crown_to_receiving_bowl(o):
    # The authored static outer crown landed beyond the lower bowl's water
    # surface. Reduce horizontal jet reach, keeping height/gravity and topology.
    # This time-independent affine change also moves its impact geometry onto
    # actual receiving water. The stone/nozzle object is never transformed.
    factor = (
        0.90 / 1.36
        if ":outer_dome:" in o.name
        else 0.60 / 0.70
        if ":inner_spray:" in o.name
        else None
    )
    if factor is None:
        return
    o.scale.x = factor
    o.scale.y = factor
    o.location.x = -10.8 * (1 - factor)
    o["dynamic2_receiving_bowl_reach_factor"] = factor


def install_ballistic_geometry(o, block, records, coords, centres):
    o.data = o.data.copy()
    for field, k in (("emit", 0), ("velocity", 1), ("life", 2), ("phase", 3)):
        attribute(
            o.data,
            "dyn2_" + field,
            np.repeat(np.array([r[k] for r in records]), block, axis=0),
        )
    attribute(o.data, "dyn2_shape", coords - np.repeat(centres, block, axis=0))
    n = Nodes(o, "DYN2_Gravity9p81")
    age = n.math(
        "FLOORED_MODULO",
        n.math("ADD", n.time, n.attr("dyn2_phase")),
        n.attr("dyn2_life"),
    )
    pos = n.vector(
        "ADD",
        n.attr("dyn2_emit", "FLOAT_VECTOR"),
        n.vector("SCALE", n.attr("dyn2_velocity", "FLOAT_VECTOR"), age),
    )
    pos = n.vector(
        "ADD", pos, n.vec(z=n.math("MULTIPLY", n.math("MULTIPLY", age, age), -0.5 * G))
    )
    pos = n.vector("ADD", pos, n.attr("dyn2_shape", "FLOAT_VECTOR"))
    n.l.new(pos, n.set.inputs["Position"])
    o["dynamic2_role"] = "ballistic_native_droplets"
    return {
        "object": o.name,
        "droplets": len(records),
        "gravity_mps2": G,
        "max_lifetime_seconds": max(r[2] for r in records),
        "respawn": "emitter/breakup to receiving water only",
        "trajectories": records,
    }


def lake_drops(o):
    if "fountain_ballistic_breakup" not in o.name:
        return None
    count = len(o.data.vertices)
    block = 30
    if count % block:
        raise RuntimeError("Unexpected native lake droplet topology")
    coords = np.empty(count * 3, dtype=np.float32)
    o.data.vertices.foreach_get("co", coords)
    coords = coords.reshape(-1, 3)
    centres = coords.reshape(-1, block, 3).mean(axis=1)
    records = []
    for j, c in enumerate(centres):
        angle = math.atan2(c[1] - 5.5, c[0] - 8.2)
        # Exact source droplets, emission from the existing water-only nozzle
        # region, apices within the authored plume, receiving surface z=0.
        height = 2.8 + 2.3 * ((j * 0.61803398875) % 1)
        vz = math.sqrt(2 * G * height)
        life = (vz + math.sqrt(vz * vz + 2 * G * 0.055)) / G
        reach = 0.6 + 1.9 * ((j * 0.41421356) % 1)
        vr = reach / life
        records.append(
            (
                (8.2 + 0.05 * math.cos(angle), 5.5 + 0.05 * math.sin(angle), 0.055),
                (vr * math.cos(angle), vr * math.sin(angle), vz),
                life,
                ((j * 0.754877666) % 1) * life,
            )
        )
    return install_ballistic_geometry(o, block, records, coords, centres)


def rolling_wheels(root, velocity):
    children = list(root.children_recursive)
    result = []
    for wheel in children:
        if "grp_wheel_steering_rotating" not in wheel.name.lower():
            continue
        pts = []
        for mesh in children:
            if mesh.type != "MESH":
                continue
            parent = mesh.parent
            while parent is not None and parent != wheel:
                parent = parent.parent
            if parent == wheel:
                pts.extend(matrix(mesh) @ Vector(v) for v in mesh.bound_box)
        if not pts:
            raise RuntimeError("Wheel has no native mesh: " + wheel.name)
        radius = (max(p.z for p in pts) - min(p.z for p in pts)) * 0.5
        if not 0.15 < radius < 0.65:
            raise RuntimeError("Invalid native tire radius: " + str(radius))
        transform = matrix(wheel).to_3x3()
        axle = (transform @ Vector((0, 1, 0))).normalized()
        if transform.determinant() < 0:
            axle = -axle
        rate = Vector((0, 0, 1)).cross(Vector(velocity)).dot(axle) / radius
        base = wheel.rotation_euler.y
        wheel.animation_data_clear()
        old.keyframe(wheel, "rotation_euler", 1, index=1)
        wheel.rotation_euler.y = base + rate * ((END - 1) / FPS)
        old.keyframe(wheel, "rotation_euler", END, index=1)
        old.finish_animation(wheel, linear=True)
        wheel.rotation_euler.y = base
        result.append(
            {
                "object": wheel.name,
                "radius_m": radius,
                "angular_velocity_rad_s": rate,
                "axle_world": list(axle),
            }
        )
    return result


def traffic(root):
    mapping = localize(root)
    cars = sorted(
        [
            o
            for original, o in mapping.items()
            if original.parent is None
            and re.fullmatch(r"v[nsew]\d+_Grp_Root", original.name, re.I)
        ],
        key=lambda o: o.name,
    )
    counts = defaultdict(int)
    report = []
    for o in cars:
        yaw = o.rotation_euler.z
        axis = 0 if abs(math.cos(yaw)) > 0.7 else 1
        sign = 1 if (math.cos(yaw) if axis == 0 else math.sin(yaw)) > 0 else -1
        key = (axis, sign)
        index = counts[key]
        counts[key] += 1
        # X traffic has right of way. Y traffic is already downstream of
        # the intersection, never entering either conflicting crossing.
        along = (
            (-54.0 + index * 14.0)
            if axis == 0 and sign > 0
            else (48.0 - index * 14.0)
            if axis == 0
            else sign * (18.0 + index * 13.0)
        )
        o.location[axis] = along
        o.location[1 - axis] = (-sign if axis == 0 else sign) * 2.25
        vel = np.zeros(3)
        vel[axis] = sign * SPEED
        p = o.location.copy()
        old.keyframe(o, "location", 1)
        o.location = Vector(p) + Vector(vel) * ((END - 1) / FPS)
        old.keyframe(o, "location", END)
        old.finish_animation(o, linear=True)
        o.location = p
        o["dynamic2_role"] = "vehicle"
        o["dynamic2_velocity"] = list(vel)
        pts = []
        for child in o.children_recursive:
            if child.type == "MESH":
                pts.extend(matrix(child) @ Vector(v) for v in child.bound_box)
        bb = np.array(
            [
                [min(v[i] for v in pts) for i in range(3)],
                [max(v[i] for v in pts) for i in range(3)],
            ]
        ) + np.array(root.location)
        wheels = rolling_wheels(o, vel)
        report.append(
            {
                "object": o.name,
                "start": list(p),
                "velocity": list(vel),
                "bounds": bb.tolist(),
                "axis": axis,
                "sign": sign,
                "wheel_rigs": len(wheels),
                "wheel_measurements": wheels,
            }
        )
    return report


def static_boxes(collection, transform, excluded, path=""):
    for o in collection.all_objects:
        if o in excluded:
            continue
        m = transform @ matrix(o)
        if o.type in {"MESH", "CURVE", "SURFACE"}:
            yield path + o.name, bounds(o, m), o, m
        if o.instance_collection:
            yield from static_boxes(
                o.instance_collection,
                m @ Matrix.Translation(-o.instance_collection.instance_offset),
                excluded,
                path + o.name + "/",
            )


def audit_traffic(rows, roots):
    duration = (END - 1) / FPS
    conflicts = []
    pairs = 0
    for i, a in enumerate(rows):
        for b in rows[i + 1 :]:
            pairs += 1
            if swept_collision(
                np.array(a["bounds"]),
                a["velocity"],
                np.array(b["bounds"]),
                b["velocity"],
                duration,
            ):
                conflicts.append([a["object"], b["object"]])
    dynroots = [bpy.data.objects[r["object"]] for r in rows]
    excluded = set(dynroots)
    for o in dynroots:
        excluded.update(o.children_recursive)
    candidates = []
    examined = 0
    sweeps = []
    for r in rows:
        bb = np.array(r["bounds"])
        end = bb + np.array(r["velocity"]) * duration
        sweeps.append(np.array([np.minimum(bb[0], end[0]), np.maximum(bb[1], end[1])]))
    corridor = np.array(
        [np.min([b[0] for b in sweeps], axis=0), np.max([b[1] for b in sweeps], axis=0)]
    )
    layout = {
        r["placement_id"]: r
        for r in json.loads((STATIC / "layout_plan.json").read_text())["placements"]
    }
    for root in roots:
        record = layout.get(root["placement_id"], {})
        foot = record.get("footprint")
        if foot and not overlap(np.array([foot["min"], foot["max"]]), corridor, 0.3):
            continue
        for name, bb, obj, transform in static_boxes(
            root.instance_collection, matrix(root), excluded
        ):
            examined += 1
            if not any(overlap(bb, b, 0.12) for b in sweeps):
                continue
            # Road support/paint is allowed contact, but never sidewalks,
            # planters, furniture or buildings. Audit includes all placement roots.
            if bb[1, 2] <= 0.13:
                continue
            if obj.type == "MESH" and max(bb[1, :2] - bb[0, :2]) > 20:
                # The large terrain's bounds include elevated outer terrain.
                # Refine broad-phase hits to native triangles, never exempt it.
                obj.data.calc_loop_triangles()
                for tri in obj.data.loop_triangles:
                    points = np.array(
                        [
                            list(transform @ obj.data.vertices[i].co)
                            for i in tri.vertices
                        ]
                    )
                    tb = np.array([points.min(axis=0), points.max(axis=0)])
                    if any(overlap(tb, b, 0.12) for b in sweeps):
                        candidates.append((name + ":triangle:" + str(tri.index), tb))
            else:
                candidates.append((name, bb))
    for r in rows:
        for name, bb in candidates:
            if swept_collision(
                np.array(r["bounds"]), r["velocity"], bb, np.zeros(3), duration
            ):
                conflicts.append([r["object"], name])
    lane = []
    for r in rows:
        bb = np.array(r["bounds"])
        cross = 1 - r["axis"]
        center = (272.5 if cross == 0 else 0) + r["start"][cross]
        lane.append(
            {
                "object": r["object"],
                "center": center,
                "max_halfwidth": float(max(abs(bb[:, cross] - center))),
                "pass": bool(max(abs(bb[:, cross] - center)) < 1.7),
            }
        )
    result = {
        "method": "continuous swept world AABB, fixed heading and constant velocity, 0.12 m clearance",
        "duration_s": duration,
        "vehicle_pairs": pairs,
        "static_mesh_bounds_examined": examined,
        "static_candidates": len(candidates),
        "conflicts": conflicts,
        "lane_containment": lane,
        "speed_mps": SPEED,
        "status": "PASS" if not conflicts and all(r["pass"] for r in lane) else "FAIL",
    }
    return result


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--output-dir", type=Path, default=OUT)
    args = p.parse_args(
        sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    )
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (
        Path(bpy.data.filepath).resolve()
        != (STATIC / "urban_v1_full_13.blend").resolve()
    ):
        raise RuntimeError("Open the original STATIC full master")
    scene = bpy.context.scene
    roots = [
        o for o in scene.objects if o.get("placement_id") and o.instance_collection
    ]
    report = {
        "schema": "agent.full13.dynamic2.v1",
        "status": "BUILDING",
        "source_master_sha256": old.sha256(Path(bpy.data.filepath)),
        "source_placement_count": len(roots),
        "physics_model": "analytical prescribed motion, not a Navier-Stokes/FSI solver",
        "timeline": {"fps": FPS, "end": END},
        "wind": {"instances": 0, "canopies": []},
        "water": [],
        "droplets": [],
    }
    rootmap = {o["placement_id"]: o for o in roots}
    report["vehicles"] = traffic(rootmap["full13_single_road_activity_module"])
    trees = {}
    mats = {}
    for name in (
        "park_river5_corridor",
        "park_original_sculpture_nature",
        "park_single_fountain",
        "education_artificial_lake_civic_enclosure",
    ):
        print("DYNAMIC2 localize", name, flush=True)
        mapping = localize(rootmap[name])
        wind(mapping, trees, report["wind"])
        for original, o in mapping.items():
            if o.type not in {"MESH", "CURVE"}:
                continue
            isriver = original.get("c2w_river_role") == "flowing_water_surface"
            islake = "procedural_lake_water_volume" in original.name
            isfountain = original.get("urban_semantic") == "fountain-water"
            if isriver or islake:
                report["water"].append(surface(o, isriver))
                advect_material(o, (0.0, 0.3 if isriver else 0.06, 0.0), mats)
            elif isfountain:
                fit_crown_to_receiving_bowl(o)
                top = (
                    UPPER_WATER + 0.018
                    if "upper_spill" in o.name
                    else LOWER_WATER + 0.018
                    if "lower_spill" in o.name
                    else None
                )
                advect_material(
                    o,
                    (0.0, 0.0, -1.2 if "spill" in o.name else 0.8),
                    mats,
                    gravity_top=top,
                )
                if o.type == "MESH":
                    result = fountain_drops(o)
                    if result:
                        report["droplets"].append(result)
            elif original.get("urban_semantic") == "lake-water":
                advect_material(o, (0.0, 0.0, 0.8), mats)
                if o.type == "MESH":
                    result = lake_drops(o)
                    if result:
                        report["droplets"].append(result)
    print("DYNAMIC2 audit traffic", flush=True)
    report["traffic_audit"] = audit_traffic(report["vehicles"], roots)
    print("DYNAMIC2 TRAFFIC", json.dumps(report["traffic_audit"]), flush=True)
    # Keep the entire static city and all interiors. Fixed cameras, hard cuts.
    shots = [
        ("traffic", (301.0, -30.0, 34.0), (272.5, 0.0, 0.0), 38.0),
        ("river_and_wind", (-291.0, -138.0, 8.0), (-309.0, -95.0, 2.4), 48.0),
        ("fountain", (-232.8, -118.2, 10.0), (-240.0, -105.0, 1.8), 60.0),
        ("lake_and_wind", (-120.0, -92.0, 13.0), (-128.0, -65.0, 1.5), 42.0),
    ]
    report["shots"] = []
    scene.timeline_markers.clear()
    for i, (name, position, target, lens) in enumerate(shots):
        data = bpy.data.cameras.new("DYN2_Camera_" + name)
        data.lens = lens
        data.clip_end = 2000
        camera = bpy.data.objects.new(data.name, data)
        scene.collection.objects.link(camera)
        camera.location = position
        old.look_at(camera, Vector(target))
        marker = scene.timeline_markers.new(name, frame=1 + 96 * i)
        marker.camera = camera
        report["shots"].append(
            {
                "name": name,
                "camera": camera.name,
                "start": 1 + 96 * i,
                "end": 96 * (i + 1),
                "position": position,
                "target": target,
                "lens": lens,
            }
        )
        if i == 0:
            scene.camera = camera
    for o in list(scene.objects):
        if o.type == "LIGHT":
            scene.collection.objects.unlink(
                o
            ) if o.name in scene.collection.objects else None
    old.configure_daylight(scene)
    old.configure_render(scene, output, 1, END, FPS)
    scene.use_nodes = False
    scene.render.use_compositing = False
    scene.eevee.shadow_pool_size = "1024"
    scene["dynamic2_manifest"] = "dynamic2_manifest.json"
    scene["dynamic2_full_static_placements_preserved"] = len(roots)
    scene["dynamic2_no_image_warp"] = True
    # Do not evaluate the entire 40 GB linked city merely to save its master.
    bpy.context.preferences.filepaths.save_version = 0
    blend = output / "urban_v1_full_13_dynamic2.blend"
    # The regular save operator evaluates the entire >40 GB linked city;
    # library-write serializes its complete dependency graph without evaluation.
    bpy.data.libraries.write(str(blend), {scene}, path_remap="ABSOLUTE", fake_user=True)
    report["output_blend_sha256"] = old.sha256(blend)
    report["status"] = (
        "BUILT" if report["traffic_audit"]["status"] == "PASS" else "AUDIT_FAILED"
    )
    (output / "dynamic2_manifest.json").write_text(json.dumps(report, indent=2))
    if report["traffic_audit"]["status"] != "PASS":
        raise RuntimeError("Traffic audit failed; see manifest; do not render delivery")
    print("DYNAMIC2 BUILD PASS", flush=True)


if __name__ == "__main__":
    main()

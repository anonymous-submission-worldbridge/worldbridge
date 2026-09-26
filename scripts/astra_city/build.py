"""Actual city mesh realization from the shared indoor/outdoor plan."""
from __future__ import annotations
from collections import Counter
import json
import math
import random
import time
from pathlib import Path
import bpy
from mathutils import Matrix, Vector
from shapely import constrained_delaunay_triangles
from shapely.geometry import Polygon, LineString, Point, shape
from shapely.ops import unary_union

from .plan import OUT, ROOT, polygons, world_point
from .geometry import Batch, collection, instance_mesh, transform


def log(message):
    line = time.strftime("%H:%M:%S") + " " + message
    print(line, flush=True)
    with (OUT / "generation.log").open("a") as f:
        f.write(line + "\n")


def surface(batch, geometry, z, material, thickness=0):
    for poly in polygons(geometry):
        for tri in constrained_delaunay_triangles(poly).geoms:
            pts = list(tri.exterior.coords)[:-1]
            # Explicit CCW top normals, independent of the triangulator's winding.
            if (pts[1][0] - pts[0][0]) * (pts[2][1] - pts[0][1]) - (
                pts[1][1] - pts[0][1]
            ) * (pts[2][0] - pts[0][0]) < 0:
                pts.reverse()
            batch.geometry([(x, y, z) for x, y in pts], [(0, 1, 2)], material)
        if thickness:
            for linear in [poly.exterior, *poly.interiors]:
                pts = list(linear.coords)
                for a, b in zip(pts, pts[1:]):
                    batch.geometry(
                        [
                            (a[0], a[1], z),
                            (b[0], b[1], z),
                            (b[0], b[1], z - thickness),
                            (a[0], a[1], z - thickness),
                        ],
                        [(0, 1, 2, 3)],
                        material,
                    )


class CityBuilder:
    def __init__(self, plan):
        self.plan = plan
        self.collisions = {}
        self.furniture_records = []
        self.door_records = []
        self.room_records = []
        self.props = []
        self.building_records = []
        self.crosswalks = []
        self.outdoor_colliders = []
        self.root = collection("ASTRA_CITY")
        self.blocks = {b["id"]: collection(b["id"], self.root) for b in plan["blocks"]}
        index = json.loads((OUT / "asset_library_index.json").read_text())
        with bpy.data.libraries.load(str(OUT / "asset_library.blend"), link=False) as (
            src,
            dst,
        ):
            dst.meshes = sorted(set(index["meshes"].values()))
            dst.materials = sorted(set(index["materials"].values()))
        self.meshes = {k: bpy.data.meshes[n] for k, n in index["meshes"].items()}
        self.m = {k: bpy.data.materials[n] for k, n in index["materials"].items()}
        self.bounds = index["native_bounds"]
        self.mesh_bounds = {}
        for key, mesh in self.meshes.items():
            if key.startswith("tree_"):
                continue
            low = [min(v.co[i] for v in mesh.vertices) for i in range(3)]
            high = [max(v.co[i] for v in mesh.vertices) for i in range(3)]
            if key in (
                "sofa",
                "bed",
                "chair",
                "cabinet",
                "kitchen",
                "toilet",
                "sink",
                "side_table",
                "cafe_table",
                "cafe_chair",
                "counter",
                "shelf",
            ):
                offset = Vector(
                    (-(low[0] + high[0]) / 2, -(low[1] + high[1]) / 2, -low[2])
                )
                mesh.transform(Matrix.Translation(offset))
                low = [low[i] + offset[i] for i in range(3)]
                high = [high[i] + offset[i] for i in range(3)]
            self.mesh_bounds[key] = (low, high)
        self.source_assets = index
        self.wood = self.m["wood"]
        self.finish_materials()

    def finish_materials(self):
        # The old factories used Generated coordinates. On a merged full building
        # those patterns become building-sized; use our metric UVs instead.
        wood = self.m["wood"]
        nodes = wood.node_tree.nodes
        links = wood.node_tree.links
        uv = nodes.new("ShaderNodeTexCoord")
        for node in nodes:
            if node.type == "TEX_WAVE":
                links.new(uv.outputs["UV"], node.inputs["Vector"])
                node.inputs["Scale"].default_value = 18
                node.inputs["Distortion"].default_value = 1.5
            if node.type == "VALTORGB":
                node.color_ramp.elements[0].color = (0.085, 0.038, 0.014, 1)
                node.color_ramp.elements[-1].color = (0.20, 0.11, 0.045, 1)
        floor = self.m["interior_floor"]
        nodes = floor.node_tree.nodes
        links = floor.node_tree.links
        for node in list(nodes):
            nodes.remove(node)
        out = nodes.new("ShaderNodeOutputMaterial")
        p = nodes.new("ShaderNodeBsdfPrincipled")
        uv = nodes.new("ShaderNodeTexCoord")
        brick = nodes.new("ShaderNodeTexBrick")
        brick.inputs["Scale"].default_value = 1
        brick.inputs["Brick Width"].default_value = 0.9
        brick.inputs["Row Height"].default_value = 0.16
        brick.inputs["Mortar Size"].default_value = 0.0018
        brick.inputs["Color1"].default_value = (0.27, 0.15, 0.07, 1)
        brick.inputs["Color2"].default_value = (0.39, 0.25, 0.13, 1)
        brick.inputs["Mortar"].default_value = (0.10, 0.07, 0.04, 1)
        links.new(uv.outputs["UV"], brick.inputs["Vector"])
        scale = nodes.new("ShaderNodeVectorMath")
        scale.operation = "MULTIPLY"
        scale.inputs[1].default_value = (2, 65, 1)
        noise = nodes.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value = 1
        noise.inputs["Detail"].default_value = 2
        links.new(uv.outputs["UV"], scale.inputs[0])
        links.new(scale.outputs[0], noise.inputs["Vector"])
        mix = nodes.new("ShaderNodeMixRGB")
        mix.blend_type = "MULTIPLY"
        mix.inputs[0].default_value = 0.25
        links.new(brick.outputs["Color"], mix.inputs[1])
        links.new(noise.outputs["Fac"], mix.inputs[2])
        bump = nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15
        bump.inputs["Distance"].default_value = 0.003
        links.new(brick.outputs["Fac"], bump.inputs["Height"])
        links.new(bump.outputs["Normal"], p.inputs["Normal"])
        links.new(mix.outputs["Color"], p.inputs["Base Color"])
        p.inputs["Roughness"].default_value = 0.60
        links.new(p.outputs[0], out.inputs["Surface"])

    def mesh_instance(
        self,
        key,
        name,
        parent,
        position,
        yaw=0,
        scale=1,
        base=None,
        role="furniture",
        bid="",
    ):
        mat = transform(position, yaw, scale)
        if base is not None:
            mat = base @ mat
        return instance_mesh(self.meshes[key], name, parent, mat, role, bid)

    def framed_window(self, batch, glass, center, width, height, angle=0, style=0):
        x, y, z = center
        c, s = math.cos(angle), math.sin(angle)

        def box(name, p, d, mat):
            lx, ly, lz = p
            batch.box(
                name,
                (x + c * lx - s * ly, y + s * lx + c * ly, z + lz),
                d,
                mat,
                rotation=angle,
            )

        for xx in (-width / 2, width / 2):
            box(
                "window_jamb", (xx, 0, 0), (0.085, 0.20, height + 0.08), self.m["metal"]
            )
        for zz in (-height / 2, height / 2):
            box("window_rail", (0, 0, zz), (width + 0.08, 0.20, 0.085), self.m["metal"])
        box("window_mullion", (0, -0.035, 0), (0.052, 0.12, height), self.m["metal"])
        box(
            "window_transom",
            (0, -0.04, height * 0.22),
            (width, 0.10, 0.045),
            self.m["metal"],
        )
        box(
            "stone_sill",
            (0, -0.10, -height / 2 - 0.09),
            (width + 0.28, 0.42, 0.11),
            self.m["stone"],
        )
        box(
            "window_header",
            (0, -0.01, height / 2 + 0.13),
            (width + 0.22, 0.23, 0.15),
            self.m["concrete"],
        )
        glass.box(
            "glass",
            (x, y, z),
            (width - 0.09, 0.032, height - 0.09),
            self.m["glazing"],
            rotation=angle,
            collision=True,
        )
        if style in (1, 4):
            # Real slatted shutters, kept beside the window opening.
            for side in (-1, 1):
                for i in range(10):
                    box(
                        "shutter_slat",
                        (
                            side * (width / 2 + 0.25),
                            -0.05,
                            -height / 2 + (i + 0.5) * height / 10,
                        ),
                        (0.30, 0.09, 0.095),
                        self.m["wood"],
                    )

    def wall(self, batch, detail, glass, a, b, z, height, openings, mat, style):
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        angle = math.atan2(dy, dx)
        c, s = dx / length, dy / length
        points = sorted(
            set(
                [0, length]
                + [
                    max(0, min(length, v))
                    for o in openings
                    for v in [o["x"] - o["width"] / 2, o["x"] + o["width"] / 2]
                ]
            )
        )
        for lo, hi in zip(points, points[1:]):
            if hi - lo < 1e-5:
                continue
            mid = (lo + hi) / 2
            opening = next(
                (
                    o
                    for o in openings
                    if o["x"] - o["width"] / 2 < mid < o["x"] + o["width"] / 2
                ),
                None,
            )
            spans = (
                [(0, height)]
                if opening is None
                else [
                    (0, opening["bottom"]),
                    (opening["bottom"] + opening["height"], height),
                ]
            )
            for bottom, top in spans:
                if top - bottom < 0.001:
                    continue
                batch.box(
                    "wall",
                    (a[0] + c * mid, a[1] + s * mid, z + (bottom + top) / 2),
                    (hi - lo, 0.24, top - bottom),
                    mat,
                    rotation=angle,
                    collision=True,
                )
        for o in openings:
            if o.get("window"):
                self.framed_window(
                    detail,
                    glass,
                    (
                        a[0] + c * o["x"],
                        a[1] + s * o["x"],
                        z + o["bottom"] + o["height"] / 2,
                    ),
                    o["width"],
                    o["height"],
                    angle,
                    style,
                )

    def door(self, portal, detail, parent, base):
        w, h = portal["width_m"], portal["height_m"]
        x, y, z = portal["local"]
        angle = math.radians(portal["yaw_local_deg"])
        c, s = math.cos(angle), math.sin(angle)
        for side in (-1, 1):
            detail.box(
                "door_jamb",
                (
                    x + c * side * (w / 2 + 0.04),
                    y + s * side * (w / 2 + 0.04),
                    z + h / 2,
                ),
                (0.08, 0.27, h),
                self.m["metal"],
                rotation=angle,
            )
        detail.box(
            "door_lintel",
            (x, y, z + h + 0.04),
            (w + 0.16, 0.27, 0.08),
            self.m["metal"],
            rotation=angle,
        )
        # The mesh origin is the hinge; both Blender and UE rotate this same object.
        hinge = (x - c * w / 2, y - s * w / 2, z)
        leaf = Batch(portal["id"] + "_leaf")
        leaf.box(
            "door_panel",
            (w / 2, 0, h / 2),
            (w - 0.045, 0.065, h - 0.025),
            self.m["wood"],
        )
        for zz in (0.35, h - 0.35):
            leaf.box(
                "raised_panel",
                (w / 2, -0.044, zz),
                (w - 0.24, 0.025, 0.43),
                self.m["panel_dark"],
            )
        leaf.box(
            "handle", (w - 0.17, -0.095, 1.04), (0.15, 0.035, 0.035), self.m["bronze"]
        )
        leaf.box(
            "handle_rosette",
            (w - 0.23, -0.05, 1.04),
            (0.05, 0.025, 0.17),
            self.m["bronze"],
        )
        open_angle = angle + math.radians(portal["open_angle_deg"])
        mat = base @ transform(hinge, open_angle)
        obj = leaf.finish(parent, mat, role="door", building_id=portal["building_id"])
        obj["portal_id"] = portal["id"]
        obj["open_angle_deg"] = portal["open_angle_deg"]
        obj["hinge_axis"] = "Z"
        self.door_records.append(
            {
                **portal,
                "object": obj.name,
                "hinge_local": list(hinge),
                "closed_yaw_local": angle,
                "open_yaw_local": open_angle,
                "world_matrix": [list(row) for row in mat],
            }
        )
        # Open-state collision proxy mirrors the actual wooden leaf, including its hinge transform.
        mx = hinge[0] + math.cos(open_angle) * w / 2
        my = hinge[1] + math.sin(open_angle) * w / 2
        self.collisions[portal["building_id"]].append(
            {
                "name": portal["id"],
                "center": [mx, my, z + h / 2],
                "dimensions": [w - 0.045, 0.065, h - 0.025],
                "yaw": open_angle,
                "dynamic": True,
            }
        )

    def furniture(self, b, room, parent, base):
        x0, y0, x1, y1 = room["local_bounds"]
        z = room["floor_z"]
        rw = x1 - x0
        rd = y1 - y0
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        # Furnish against the outside wall; reserve the complete centre aisle from the hall door.
        side = -1 if cx < 0 else 1
        outer = x0 if side < 0 else x1
        kind = room["kind"]
        placements = []
        if kind == "living":
            placements = [
                ("sofa", outer - side * 1.0, cy, 0),
                ("side_table", outer - side * 2.35, cy - 1.3, 0),
                ("cabinet", cx, y1 - 0.6, 0),
            ]
        elif kind == "bedroom":
            placements = [
                ("bed", outer - side * 1.12, cy, side * math.pi / 2),
                ("side_table", outer - side * 0.65, y0 + 0.65, 0),
                ("cabinet", cx, y1 - 0.7, 0),
            ]
        elif kind == "kitchen":
            placements = [
                ("kitchen", outer - side * 0.75, cy, 0),
                ("cafe_table", cx, y0 + 1.0, 0),
                ("cafe_chair", cx, y0 + 1.95, math.pi),
            ]
        elif kind == "bathroom":
            placements = [
                ("toilet", outer - side * 0.65, y1 - 1.0, 0),
                ("sink", outer - side * 0.6, y0 + 1.0, math.pi / 2),
                ("cabinet", cx, y1 - 0.55, 0),
            ]
        elif kind in ("shop", "library"):
            placements = [
                ("shelf", outer - side * 0.70, cy, math.pi / 2),
                ("shelf", cx, y1 - 0.6, 0),
                ("counter", cx, y0 + 0.7, 0),
            ]
        elif kind == "dining":
            placements = [
                ("cafe_table", outer - side * 1.6, cy, 0),
                ("cafe_chair", outer - side * 1.6, cy - 1.08, 0),
                ("cafe_chair", outer - side * 1.6, cy + 1.08, math.pi),
                ("counter", cx, y1 - 0.55, 0),
            ]
        else:
            placements = [
                ("cafe_table", outer - side * 1.5, cy, 0),
                ("chair", outer - side * 2.5, cy, math.pi / 2),
                ("shelf", cx, y1 - 0.6, 0),
            ]
        accepted = []
        from shapely.affinity import rotate, translate

        room_poly = Polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
        door_x = -1.21 if side < 0 else 1.21
        clear = LineString([(door_x, cy), (cx, cy)]).buffer(0.5, cap_style=2)
        # Targets are placed near the hall edge, so navigation is meaningful without crossing furniture.
        target_x = (x1 - 0.7) if side < 0 else (x0 + 0.7)
        clear = LineString([(door_x, cy), (target_x, cy)]).buffer(0.55, cap_style=1)
        target_local = [target_x, cy, z]
        for j, (key, x, y, angle) in enumerate(placements):
            mesh = self.meshes[key]
            low, high = self.mesh_bounds[key]
            dx, dy, dz = [high[i] - low[i] for i in range(3)]
            # Uniform scaling is limited to room fit, recorded explicitly for audit.
            scale = min(1.0, (rw - 0.5) / max(dx, dy), (rd - 0.5) / max(dx, dy))
            if scale < 0.65:
                raise RuntimeError(
                    f'Furniture cannot fit at realistic scale: {room["id"]} {key}'
                )
            dx *= scale
            dy *= scale
            dz *= scale
            fp = Polygon(
                [
                    (-dx / 2, -dy / 2),
                    (dx / 2, -dy / 2),
                    (dx / 2, dy / 2),
                    (-dx / 2, dy / 2),
                ]
            )
            fp = rotate(fp, angle, origin=(0, 0), use_radians=True)
            # Clamp the physical extent inside its room, then resolve local furniture intersections.
            bx0, by0, bx1, by1 = fp.bounds
            x = max(x0 + 0.08 - bx0, min(x1 - 0.08 - bx1, x))
            y = max(y0 + 0.08 - by0, min(y1 - 0.08 - by1, y))
            candidates = [(x, y)]
            for yy in (y0 + 0.12 - by0, y1 - 0.12 - by1):
                for xx in (x0 + 0.12 - bx0, x1 - 0.12 - bx1):
                    candidates.append((xx, yy))
            chosen = None
            for xx, yy in candidates:
                poly = translate(fp, xx, yy)
                if (
                    room_poly.covers(poly)
                    and not poly.intersects(clear)
                    and not any(poly.buffer(0.07).intersects(q) for q in accepted)
                ):
                    chosen = (xx, yy, poly)
                    break
            if chosen is None:
                # A compact native side table remains a real asset and satisfies a useful room function.
                if j == 0:
                    raise RuntimeError("Primary furniture blocks room: " + room["id"])
                continue
            x, y, poly = chosen
            accepted.append(poly)
            obj = self.mesh_instance(
                key,
                room["id"] + "_" + key + str(j),
                parent,
                (x, y, z),
                angle,
                scale,
                base,
                bid=b["id"],
            )
            self.furniture_records.append(
                {
                    "id": obj.name,
                    "room_id": room["id"],
                    "building_id": b["id"],
                    "asset": key,
                    "local_position": [x, y, z],
                    "yaw": angle,
                    "scale": scale,
                    "footprint_local": list(map(list, poly.exterior.coords)),
                    "height_m": dz,
                }
            )
            self.collisions[b["id"]].append(
                {
                    "name": obj.name,
                    "center": [x, y, z + dz / 2],
                    "dimensions": [dx, dy, dz],
                    "yaw": angle,
                    "furniture": True,
                }
            )
        self.room_records.append(
            {
                "id": room["id"],
                "building_id": b["id"],
                "floor": room["floor"],
                "kind": kind,
                "furniture_count": len(accepted),
                "target_local": target_local,
                "floor_z": z,
                "bounds": room["local_bounds"],
            }
        )

    def building(self, b):
        bid = b["id"]
        self.collisions[bid] = []
        parent = collection(bid, self.blocks[b["block_id"]])
        parent["building_id"] = bid
        base = transform((*b["origin"], 0), math.radians(b["yaw_deg"]))
        w, d = b["width"], b["depth"]
        height = b["floors"] * 3.2 + 0.16
        structure = Batch(bid + "_structure")
        detail = Batch(bid + "_details")
        glass = Batch(bid + "_glass")
        mat = self.m[
            [
                "brick_red",
                "brick_ochre",
                "plaster_sage",
                "plaster_cream",
                "plaster_blue",
                "brick_dark",
            ][b["style"]]
        ]
        for floor in range(b["floors"]):
            z = 0.16 + floor * 3.2
            # Shared hall/stair lighting is part of the saved scene, not a render-only fill.
            for lx, ly, power, rotation in [
                (0, (d - 6) / 2, 95, Matrix.Identity(4)),
                (w / 2 - 0.20, d - 2.6, 160, Matrix.Rotation(math.pi / 2, 4, "Y")),
            ]:
                lamp = bpy.data.lights.new(f"{bid}_f{floor}_circulation_light", "AREA")
                lamp.energy = power
                lamp.size = 0.65
                lamp.color = (1, 0.93, 0.82)
                lo = bpy.data.objects.new(lamp.name, lamp)
                parent.objects.link(lo)
                lo.matrix_world = (
                    base @ Matrix.Translation((lx, ly, z + 2.76)) @ rotation
                )
                lo["astra_role"] = "interior_light"
                lo["building_id"] = bid
                detail.box(
                    "circulation_fixture",
                    (lx, ly, z + 2.81),
                    (0.35, 0.35, 0.07),
                    self.m["warm_light"],
                )
            detail.box(
                "hall_ceiling",
                (0, (d - 4.8) / 2, z + 2.985),
                (2.17, d - 4.8, 0.015),
                self.m["interior_wall"],
            )
            # Floors have actual stairwell holes; no overlapping solid slab hides the stair opening.
            if floor == 0:
                structure.box(
                    "floor",
                    (0, d / 2, z - 0.10),
                    (w, d, 0.20),
                    self.m["interior_floor"],
                    collision=True,
                )
            else:
                sy = d - 4.8
                structure.box(
                    "floor_front",
                    (0, sy / 2, z - 0.10),
                    (w, sy, 0.20),
                    self.m["interior_floor"],
                    collision=True,
                )
                for side in (-1, 1):
                    structure.box(
                        "floor_side",
                        (side * (w / 2 + 2.0) / 2, (sy + d) / 2, z - 0.10),
                        (w / 2 - 2.0, d - sy, 0.20),
                        self.m["interior_floor"],
                        collision=True,
                    )
                structure.box(
                    "floor_rear",
                    (0, d - 0.16, z - 0.10),
                    (4.0, 0.32, 0.20),
                    self.m["interior_floor"],
                    collision=True,
                )
            for face, (a, bb) in enumerate(
                [
                    ((-w / 2, 0), (w / 2, 0)),
                    ((w / 2, 0), (w / 2, d)),
                    ((w / 2, d), (-w / 2, d)),
                    ((-w / 2, d), (-w / 2, 0)),
                ]
            ):
                length = math.dist(a, bb)
                count = max(2, int(length / 3.9))
                openings = []
                for i in range(count):
                    xx = (i + 0.5) * length / count
                    if floor == 0 and face == 0 and abs(xx - length / 2) < 2.0:
                        continue
                    if face in (1, 3):
                        world_y = xx if face == 1 else d - xx
                        if world_y > d - 5.7:
                            continue
                    openings.append(
                        {
                            "x": xx,
                            "width": 1.8 if b["style"] % 2 else 2.15,
                            "bottom": 0.88,
                            "height": 1.75,
                            "window": True,
                        }
                    )
                if floor == 0 and face == 0:
                    openings.append(
                        {"x": length / 2, "width": 1.5, "bottom": 0, "height": 2.55}
                    )
                self.wall(
                    structure, detail, glass, a, bb, z, 3.2, openings, mat, b["style"]
                )
            rooms = [
                r
                for r in self.plan["rooms"]
                if r["id"].startswith(bid + "_") and r["floor"] == floor
            ]
            mid = (d - 6.0) / 2
            for side in (-1, 1):
                relevant = [
                    r
                    for r in rooms
                    if (r["local_bounds"][0] + r["local_bounds"][2]) * side > 0
                ]
                openings = [
                    {
                        "x": (r["local_bounds"][1] + r["local_bounds"][3]) / 2 - 0.12,
                        "width": 1.1,
                        "bottom": 0,
                        "height": 2.35,
                    }
                    for r in relevant
                ]
                self.wall(
                    structure,
                    detail,
                    glass,
                    (side * 1.21, 0.12),
                    (side * 1.21, d - 6.0),
                    z,
                    3.2,
                    openings,
                    self.m["interior_wall"],
                    0,
                )
                a = (-w / 2 + 0.12, mid + 0.07) if side < 0 else (1.33, mid + 0.07)
                bb = (-1.33, mid + 0.07) if side < 0 else (w / 2 - 0.12, mid + 0.07)
                self.wall(
                    structure,
                    detail,
                    glass,
                    a,
                    bb,
                    z,
                    3.2,
                    [],
                    self.m["interior_wall"],
                    0,
                )
                self.wall(
                    structure,
                    detail,
                    glass,
                    (a[0], d - 6.0),
                    (bb[0], d - 6.0),
                    z,
                    3.2,
                    [],
                    self.m["interior_wall"],
                    0,
                )
            # Every room has a real ceiling, skirting and occupied furnishings.
            for room in rooms:
                x0, y0, x1, y1 = room["local_bounds"]
                detail.box(
                    "room_ceiling",
                    ((x0 + x1) / 2, (y0 + y1) / 2, z + 2.985),
                    (x1 - x0, y1 - y0, 0.015),
                    self.m["interior_wall"],
                )
                for xx in (x0, x1):
                    detail.box(
                        "skirting",
                        (xx, (y0 + y1) / 2, z + 0.08),
                        (0.035, y1 - y0, 0.16),
                        self.m["wood"],
                    )
                for yy in (y0, y1):
                    detail.box(
                        "skirting",
                        ((x0 + x1) / 2, yy, z + 0.08),
                        (x1 - x0, 0.035, 0.16),
                        self.m["wood"],
                    )
                detail.box(
                    "ceiling_lamp",
                    ((x0 + x1) / 2, (y0 + y1) / 2, z + 3.01),
                    (0.5, 0.5, 0.07),
                    self.m["warm_light"],
                )
                lamp = bpy.data.lights.new(room["id"] + "_light", "AREA")
                lamp.energy = 180
                lamp.shape = "DISK"
                lamp.size = 1.0
                lamp.color = (1.0, 0.93, 0.82)
                lo = bpy.data.objects.new(lamp.name, lamp)
                parent.objects.link(lo)
                lo.matrix_world = base @ Matrix.Translation(
                    ((x0 + x1) / 2, (y0 + y1) / 2, z + 2.94)
                )
                lo["astra_role"] = "interior_light"
                lo["building_id"] = bid
                self.furniture(b, room, parent, base)
            # Per-floor horizontal cornices and fine pilasters give all elevations a continuous rhythm.
            for a, bb in [
                ((-w / 2, 0), (w / 2, 0)),
                ((w / 2, 0), (w / 2, d)),
                ((w / 2, d), (-w / 2, d)),
                ((-w / 2, d), (-w / 2, 0)),
            ]:
                angle = math.atan2(bb[1] - a[1], bb[0] - a[0])
                length = math.dist(a, bb)
                detail.box(
                    "cornice",
                    ((a[0] + bb[0]) / 2, (a[1] + bb[1]) / 2, z + 3.08),
                    (length + 0.16, 0.34, 0.13),
                    self.m["concrete"],
                    rotation=angle,
                )
            if floor < b["floors"] - 1:
                # Two ten-riser flights, 16 cm rise and 31 cm going, joined by a full landing.
                ystart = d - 4.8
                run = 0.31
                rise = 0.16
                for i in range(10):
                    zz = z + (i + 1) * rise
                    structure.box(
                        "stair_up",
                        (-1.0, ystart + (i + 0.5) * run, zz - 0.11),
                        (1.5, run, 0.22),
                        self.m["concrete"],
                        collision=True,
                    )
                    zz2 = z + 1.6 + (i + 1) * rise
                    structure.box(
                        "stair_return",
                        (1.0, ystart + (9 - i + 0.5) * run, zz2 - 0.11),
                        (1.5, run, 0.22),
                        self.m["concrete"],
                        collision=True,
                    )
                structure.box(
                    "stair_half_landing",
                    (0, d - 1.0, z + 1.6 - 0.11),
                    (3.6, 1.4, 0.22),
                    self.m["concrete"],
                    collision=True,
                )
                # Guard posts and rails stay outside the usable stair width.
                for sx in (-1.84, 1.84):
                    for i in range(10):
                        sy = ystart + (i + 0.5) * run
                        sz = z + ((i + 1) * rise if sx < 0 else 3.2 - i * rise)
                        detail.cylinder(
                            (sx, sy, sz + 0.48), 0.026, 0.96, self.m["metal"], 10
                        )
                for sx in (-0.2, 0.2):
                    for i in range(10):
                        sy = ystart + (i + 0.5) * run
                        sz = z + ((i + 1) * rise if sx < 0 else 3.2 - i * rise)
                        detail.cylinder(
                            (sx, sy, sz + 0.48), 0.025, 0.96, self.m["metal"], 10
                        )
                for sx in (-1.84, -0.2, 0.2, 1.84):
                    first = z + (0.16 if sx < 0 else 3.2) + 0.98
                    last = z + (1.6 if sx < 0 else 1.76) + 0.98
                    detail.beam(
                        (sx, ystart + 0.155, first),
                        (sx, ystart + 2.945, last),
                        0.065,
                        self.m["metal"],
                    )
                    # A narrow conservative guard proxy prevents falling through non-colliding visual rail posts.
                    structure.colliders.append(
                        {
                            "name": "stair_guard",
                            "center": [sx, ystart + 1.55, z + 1.72],
                            "dimensions": [0.075, 3.1, 3.12],
                            "yaw": 0,
                        }
                    )
        for portal in [p for p in self.plan["portals"] if p["building_id"] == bid]:
            self.door(portal, detail, parent, base)
        # Roof is retained in every view. Pitched roof variants are above the same full top-floor ceiling.
        structure.box(
            "roof",
            (0, d / 2, height + 0.02),
            (w + 0.14, d + 0.14, 0.20),
            self.m["panel_dark"],
            collision=True,
        )
        if b["style"] in (0, 1, 3):
            rise = 1.4 if b["floors"] < 4 else 0.9
            pts = [
                (-w / 2 - 0.25, -0.25, height + 0.12),
                (w / 2 + 0.25, -0.25, height + 0.12),
                (w / 2 + 0.25, d + 0.25, height + 0.12),
                (-w / 2 - 0.25, d + 0.25, height + 0.12),
                (0, -0.25, height + rise),
                (0, d + 0.25, height + rise),
            ]
            detail.geometry(
                pts,
                [(0, 1, 4), (3, 5, 2), (0, 4, 5, 3), (4, 1, 2, 5)],
                self.m["roof_warm"] if b["style"] == 1 else self.m["roof_tile"],
            )
            for xx in (-w / 2 - 0.26, w / 2 + 0.26):
                detail.box(
                    "roof_gutter",
                    (xx, d / 2, height + 0.05),
                    (0.12, d + 0.65, 0.15),
                    self.m["gutter"],
                )
        else:
            for x, y, ww, dd in [
                (0, 0, w + 0.35, 0.24),
                (0, d, w + 0.35, 0.24),
                (-w / 2, d / 2, 0.24, d),
                (w / 2, d / 2, 0.24, d),
            ]:
                detail.box("parapet", (x, y, height + 0.45), (ww, dd, 0.70), mat)
                detail.box(
                    "coping",
                    (x, y, height + 0.83),
                    (ww + 0.1, dd + 0.1, 0.08),
                    self.m["concrete"],
                )
            for x in (-w * 0.22, w * 0.22):
                self.mesh_instance(
                    "hvac",
                    bid + "_hvac",
                    parent,
                    (x, d * 0.60, height + 0.14),
                    base=base,
                    role="roof_detail",
                    bid=bid,
                )
        for x in (-w / 2 + 0.22, w / 2 - 0.22):
            detail.cylinder((x, -0.20, height / 2), 0.047, height, self.m["gutter"], 12)
        # Functional frontage stays recessed clear of the shared sidewalk.
        detail.box(
            "entrance_canopy", (0, -0.75, 2.98), (3.5, 1.5, 0.16), self.m["panel_dark"]
        )
        self.mesh_instance(
            "mailbox",
            bid + "_mailbox",
            parent,
            (1.32, -0.21, 0.16),
            scale=0.7,
            base=base,
            role="facade_detail",
            bid=bid,
        )
        if b["use"] != "residential":
            sign_colors = [
                self.m["plaster_sage"],
                self.m["brick_red"],
                self.m["plaster_blue"],
                self.m["bronze"],
            ]
            detail.box(
                "store_sign",
                (0, -0.25, 3.0),
                (min(w - 1.0, 9), 0.20, 0.70),
                sign_colors[b["style"] % 4],
            )
            textdata = bpy.data.curves.new(bid + "_sign", "FONT")
            textdata.body = {
                "retail": "CORNER MARKET",
                "cafe": "CEDAR COFFEE",
                "pharmacy": "NEIGHBORHOOD PHARMACY",
                "office": "WORKSHOP & STUDIO",
                "library": "PUBLIC READING ROOM",
                "clinic": "COMMUNITY CLINIC",
            }[b["use"]]
            textdata.align_x = "CENTER"
            textdata.align_y = "CENTER"
            textdata.size = 0.30
            textdata.extrude = 0.008
            textdata.materials.append(self.m["white"])
            obj = bpy.data.objects.new(bid + "_sign", textdata)
            parent.objects.link(obj)
            obj.matrix_world = (
                base
                @ Matrix.Translation((0, -0.37, 3.0))
                @ Matrix.Rotation(math.pi / 2, 4, "X")
            )
            obj["astra_role"] = "sign"
            obj["building_id"] = bid
        for batch, role in [
            (structure, "structure"),
            (detail, "detail"),
            (glass, "glass"),
        ]:
            batch.finish(parent, base, role, bid)
        self.collisions[bid].extend(structure.colliders)
        self.collisions[bid].extend(glass.colliders)
        self.building_records.append(
            {
                "id": bid,
                "collection": parent.name,
                "structural_faces": len(structure.faces),
                "detail_faces": len(detail.faces),
                "floors_built": b["floors"],
                "room_count": len(b["room_ids"]),
                "colliders": len(self.collisions[bid]),
                "base_matrix": [list(row) for row in base],
            }
        )

    def outdoors(self):
        parent = collection("STREETS_AND_PUBLIC_REALM", self.root)
        roads = Batch("astra_road_surface")
        sidewalk = Batch("astra_pedestrian_surface")
        details = Batch("astra_street_details")
        boundary = Polygon(self.plan["boundary"])
        road = shape(self.plan["road_surface"])
        context = Batch("astra_context_terrain")
        surface(
            context,
            boundary.buffer(600).difference(boundary),
            -0.05,
            self.m["lawn_dry"],
            0.1,
        )
        context.finish(parent, role="context_outside_city_boundary")
        surface(roads, boundary, -0.03, self.m["site_soil"], 0.28)
        surface(roads, road, 0, self.m["asphalt"], 0.15)
        surface(
            sidewalk, shape(self.plan["sidewalk_surface"]), 0.16, self.m["paving"], 0.16
        )
        # The common ground outside road reservations closes all outer edge slivers.
        blocks_union = unary_union([Polygon(b["polygon"]) for b in self.plan["blocks"]])
        outer = boundary.difference(
            road.union(shape(self.plan["sidewalk_surface"])).union(blocks_union)
        )
        surface(sidewalk, outer, 0.16, self.m["paving"], 0.15)
        nodes = [Point(v) for v in self.plan["road_graph"]["nodes"].values()]
        rng = random.Random(self.plan["seed"])
        tree_points = []
        occupied = unary_union(
            [Polygon(b["footprint"]) for b in self.plan["buildings"]]
        )
        for r in self.plan["roads"]:
            line = LineString(r["centerline"])
            for i in range(int(line.length / 5.0)):
                pos = (i + 0.5) * 5
                p = line.interpolate(pos)
                if any(p.distance(n) < 7 for n in nodes):
                    continue
                p0 = line.interpolate(max(0, pos - 0.1))
                p1 = line.interpolate(min(line.length, pos + 0.1))
                ang = math.atan2(p1.y - p0.y, p1.x - p0.x)
                details.box(
                    "lane_dash",
                    (p.x, p.y, 0.008),
                    (2.6, 0.13, 0.015),
                    self.m["white"],
                    rotation=ang,
                )
            for side in (-1, 1):
                for i in range(int(line.length / 18)):
                    pos = (i + 0.5) * 18
                    p = line.interpolate(pos)
                    if any(p.distance(n) < 10 for n in nodes):
                        continue
                    p0 = line.interpolate(max(0, pos - 0.1))
                    p1 = line.interpolate(min(line.length, pos + 0.1))
                    ang = math.atan2(p1.y - p0.y, p1.x - p0.x)
                    nx, ny = -math.sin(ang) * side, math.cos(ang) * side
                    x, y = p.x + nx * (r["width"] / 2 + 0.8), p.y + ny * (
                        r["width"] / 2 + 0.8
                    )
                    if not boundary.covers(Point(x, y)):
                        continue
                    # Street furniture sits in the curbside strip, leaving the walking strip and building entrances clear.
                    details.cylinder((x, y, 2.95), 0.055, 5.58, self.m["metal"], 12)
                    details.box(
                        "lamp_arm",
                        (x - nx * 0.35, y - ny * 0.35, 5.65),
                        (0.9, 0.11, 0.11),
                        self.m["metal"],
                        rotation=ang + math.pi / 2,
                    )
                    details.box(
                        "lamp_head",
                        (x - nx * 0.65, y - ny * 0.65, 5.60),
                        (0.70, 0.32, 0.10),
                        self.m["ac"],
                        rotation=ang + math.pi / 2,
                    )
                    self.props.append({"kind": "streetlamp", "position": [x, y, 0.16]})
                    self.outdoor_colliders.append(
                        {
                            "name": "streetlamp",
                            "center": [x, y, 2.95],
                            "dimensions": [0.12, 0.12, 5.58],
                            "yaw": 0,
                        }
                    )
                    if i % 2 == 0:
                        tx, ty = x + math.cos(ang) * 3.0, y + math.sin(ang) * 3.0
                        if (
                            boundary.covers(Point(tx, ty))
                            and occupied.distance(Point(tx, ty)) > 2.3
                        ):
                            tree_points.append((tx, ty, 0.16, 0.62))
        # Zebra markings are centred on each road arm at every real intersection.
        degrees = Counter()
        for edge in self.plan["road_graph"]["edges"]:
            degrees[edge["from"]] += 1
            degrees[edge["to"]] += 1
        crosswalks = []
        for node, degree in degrees.items():
            if degree < 3:
                continue
            x, y = self.plan["road_graph"]["nodes"][node]
            for edge in self.plan["road_graph"]["edges"]:
                if node not in (edge["from"], edge["to"]):
                    continue
                other = edge["to"] if edge["from"] == node else edge["from"]
                ox, oy = self.plan["road_graph"]["nodes"][other]
                angle = math.atan2(oy - y, ox - x)
                cx, cy = x + math.cos(angle) * 8.5, y + math.sin(angle) * 8.5
                for j in range(-4, 5):
                    px, py = (
                        cx - math.sin(angle) * j * 0.8,
                        cy + math.cos(angle) * j * 0.8,
                    )
                    if road.covers(Point(px, py)):
                        details.box(
                            "zebra",
                            (px, py, 0.011),
                            (2.6, 0.43, 0.019),
                            self.m["white"],
                            rotation=angle,
                        )
                crosswalks.append({"center": [cx, cy], "road_yaw": angle})
        self.crosswalks = crosswalks
        for block in self.plan["blocks"]:
            poly = Polygon(block["polygon"])
            public = block["use"] == "public_park"
            if public:
                surface(sidewalk, poly, 0.16, self.m["lawn"], 0.16)
                center = poly.representative_point()
                paths = unary_union(
                    [
                        LineString([center.coords[0], a]).buffer(1.65)
                        for a in list(poly.exterior.coords)[:-1]
                    ]
                ).intersection(poly)
                surface(sidewalk, paths, 0.18, self.m["paving"], 0.1)
                # A complete fountain, curving planted beds and usable benches establish a finished park.
                details.cylinder(
                    (center.x, center.y, 0.35), 4.0, 0.38, self.m["stone"], 64
                )
                details.cylinder(
                    (center.x, center.y, 0.56), 3.6, 0.08, self.m["water"], 64
                )
                details.cylinder(
                    (center.x, center.y, 1.12), 0.35, 1.15, self.m["bronze"], 24
                )
                details.cylinder(
                    (center.x, center.y, 1.72), 1.05, 0.12, self.m["stone"], 48
                )
                self.props.append(
                    {"kind": "fountain", "position": [center.x, center.y, 0.16]}
                )
                self.outdoor_colliders.append(
                    {
                        "name": "fountain",
                        "center": [center.x, center.y, 0.97],
                        "dimensions": [8, 8, 1.62],
                        "yaw": 0,
                    }
                )
                inset = poly.buffer(-5)
                for _ in range(70):
                    minx, miny, maxx, maxy = poly.bounds
                    p = Point(rng.uniform(minx, maxx), rng.uniform(miny, maxy))
                    if (
                        inset.covers(p)
                        and p.distance(center) > 7
                        and not paths.buffer(2.2).covers(p)
                        and all(
                            math.hypot(p.x - t[0], p.y - t[1]) > 5 for t in tree_points
                        )
                    ):
                        tree_points.append((p.x, p.y, 0.16, rng.uniform(0.8, 1.0)))
            else:
                fp = unary_union(
                    [
                        Polygon(b["footprint"])
                        for b in self.plan["buildings"]
                        if b["block_id"] == block["id"]
                    ]
                )
                courtyard = poly.difference(fp)
                surface(sidewalk, courtyard, 0.16, self.m["paving"], 0.16)
                usable = courtyard.buffer(-3.5)
                for p in polygons(usable):
                    if p.area < 10:
                        continue
                    q = p.representative_point()
                    tree_points.append((q.x, q.y, 0.16, 0.72))
                    details.box(
                        "planter", (q.x, q.y, 0.40), (2.0, 2.0, 0.48), self.m["stone"]
                    )
                    details.box(
                        "planter_soil",
                        (q.x, q.y, 0.66),
                        (1.7, 1.7, 0.04),
                        self.m["mulch"],
                    )
                    self.outdoor_colliders.append(
                        {
                            "name": "planter",
                            "center": [q.x, q.y, 0.42],
                            "dimensions": [2, 2, 0.52],
                            "yaw": 0,
                        }
                    )
        for i, (x, y, z, sc) in enumerate(tree_points):
            key = "tree_42" if i % 3 else "tree_512"
            self.mesh_instance(
                key,
                f"astra_tree_{i:03d}",
                parent,
                (x, y, z),
                rng.uniform(0, math.tau),
                sc,
                role="vegetation",
            )
            self.props.append(
                {
                    "kind": "botanical_tree",
                    "asset": key,
                    "position": [x, y, z],
                    "scale": sc,
                }
            )
            self.outdoor_colliders.append(
                {
                    "name": f"tree_{i}",
                    "center": [x, y, z + 1.5],
                    "dimensions": [0.55 * sc, 0.55 * sc, 3],
                    "yaw": 0,
                }
            )
        # Slatted benches, litter bins, tactile paving and drain grilles are modelled parts.
        for i, t in enumerate(tree_points):
            if i % 3:
                continue
            x, y, z, _ = t
            if occupied.distance(Point(x + 2.2, y)) < 1.6:
                continue
            bench_area = Polygon(
                [
                    (x + 1.3, y - 0.5),
                    (x + 4, y - 0.5),
                    (x + 4, y + 0.5),
                    (x + 1.3, y + 0.5),
                ]
            )
            if not boundary.covers(bench_area) or bench_area.intersects(road):
                continue
            for j in range(6):
                details.box(
                    "bench_seat",
                    (x + 2.2, y + (j - 2.5) * 0.09, z + 0.46),
                    (1.65, 0.075, 0.065),
                    self.m["wood"],
                )
            for j in range(4):
                details.box(
                    "bench_back",
                    (x + 2.2, y + 0.30, z + 0.61 + j * 0.09),
                    (1.65, 0.065, 0.07),
                    self.m["wood"],
                )
            for side in (-1, 1):
                details.box(
                    "bench_leg",
                    (x + 2.2 + side * 0.64, y, z + 0.23),
                    (0.055, 0.42, 0.46),
                    self.m["metal"],
                )
            details.cylinder((x + 3.5, y, z + 0.44), 0.24, 0.88, self.m["metal"], 24)
            self.props.extend(
                [
                    {"kind": "bench", "position": [x + 2.2, y, z]},
                    {"kind": "litter_bin", "position": [x + 3.5, y, z]},
                ]
            )
            self.outdoor_colliders.extend(
                [
                    {
                        "name": "bench",
                        "center": [x + 2.2, y, z + 0.47],
                        "dimensions": [1.65, 0.65, 0.94],
                        "yaw": 0,
                    },
                    {
                        "name": "bin",
                        "center": [x + 3.5, y, z + 0.44],
                        "dimensions": [0.48, 0.48, 0.88],
                        "yaw": 0,
                    },
                ]
            )
        roads.finish(parent, role="road")
        sidewalk.finish(parent, role="sidewalk")
        details.finish(parent, role="street_detail")

    def save(self):
        scene = bpy.context.scene
        scene.unit_settings.system = "METRIC"
        scene.unit_settings.scale_length = 1
        scene["astra_revision"] = "urban_v1_full_astra"
        scene["plan_sha256"] = self.plan["plan_sha256"]
        scene["all_buildings_have_all_floors"] = True
        text = bpy.data.texts.new("ASTRA_WORLD_MANIFEST.json")
        text.write(json.dumps(self.plan, ensure_ascii=False))
        (OUT / "world_manifest.json").write_text(
            json.dumps(self.plan, indent=2, ensure_ascii=False)
        )
        geometry_report = {
            "schema": "agent.astra.geometry.v1",
            "status": "BUILT_PENDING_VALIDATION",
            "plan_sha256": self.plan["plan_sha256"],
            "buildings": self.building_records,
            "rooms": self.room_records,
            "furniture": self.furniture_records,
            "doors": self.door_records,
            "props": self.props,
            "colliders": self.collisions,
            "crosswalks": self.crosswalks,
            "outdoor_colliders": self.outdoor_colliders,
            "scene_objects": len(scene.objects),
            "unique_meshes": len(bpy.data.meshes),
            "mesh_polygons": sum(
                len(o.data.polygons) for o in scene.objects if o.type == "MESH"
            ),
            "ue_runtime_status": "NOT_RUN",
        }
        (OUT / "geometry_manifest.json").write_text(
            json.dumps(geometry_report, indent=2, ensure_ascii=False)
        )
        scene.render.engine = "CYCLES"
        scene.cycles.samples = 48
        scene.cycles.use_denoising = True
        scene.render.resolution_x = 1920
        scene.render.resolution_y = 1080
        scene.render.resolution_percentage = 100
        scene.view_settings.view_transform = "AgX"
        scene.view_settings.look = "AgX - Medium High Contrast"
        world = bpy.data.worlds.new("Astra Daylight")
        world.use_nodes = True
        scene.world = world
        nodes = world.node_tree.nodes
        links = world.node_tree.links
        sky = nodes.new("ShaderNodeTexSky")
        sky.sky_type = "NISHITA"
        sky.sun_elevation = math.radians(38)
        sky.sun_rotation = math.radians(225)
        sky.sun_intensity = 0.4
        nodes["Background"].inputs["Strength"].default_value = 0.08
        links.new(sky.outputs["Color"], nodes["Background"].inputs["Color"])
        light = bpy.data.lights.new("Astra Sun", "SUN")
        light.energy = 2.0
        light.angle = 0.03
        sun = bpy.data.objects.new("Astra Sun", light)
        self.root.objects.link(sun)
        sun.rotation_euler = (math.radians(30), math.radians(-20), math.radians(-30))
        scene.render.film_transparent = False
        bpy.context.preferences.filepaths.save_version = 0
        bpy.ops.wm.save_as_mainfile(
            filepath=str(OUT / "urban_v1_full_astra.blend"), compress=True
        )
        log(
            f"CITY_SAVED {len(self.building_records)} buildings / {len(self.room_records)} rooms / {len(self.furniture_records)} furniture instances"
        )


def build(plan):
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for c in list(bpy.data.collections):
        bpy.data.collections.remove(c)
    city = CityBuilder(plan)
    for i, b in enumerate(plan["buildings"]):
        city.building(b)
        if i % 6 == 0:
            log(f'BUILDING {i+1}/{len(plan["buildings"])}')
    city.outdoors()
    city.save()
    return city

"""Efficient mesh construction with explicit collision semantics and metric UVs."""
from __future__ import annotations
import math
import bpy
from mathutils import Matrix, Vector


def collection(name, parent=None):
    c = bpy.data.collections.new(name)
    (parent or bpy.context.scene.collection).children.link(c)
    return c


class Batch:
    def __init__(self, name):
        self.name = name
        self.vertices = []
        self.faces = []
        self.indices = []
        self.materials = []
        self.colliders = []

    def material_index(self, material):
        if material is not None and material.is_evaluated:
            material = material.original
        if material not in self.materials:
            self.materials.append(material)
        return self.materials.index(material)

    def geometry(self, vertices, faces, material, matrix=None):
        offset = len(self.vertices)
        self.vertices.extend(
            [tuple(matrix @ Vector(v)) for v in vertices]
            if matrix is not None
            else vertices
        )
        self.faces.extend(tuple(offset + i for i in f) for f in faces)
        self.indices.extend([self.material_index(material)] * len(faces))

    def box(self, name, center, dimensions, material, rotation=0, collision=False):
        if min(dimensions) <= 0:
            return
        x, y, z = center
        a, b, c = [d / 2 for d in dimensions]
        ca, sa = math.cos(rotation), math.sin(rotation)
        vertices = [
            (x + ca * dx - sa * dy, y + sa * dx + ca * dy, z + dz)
            for dx, dy, dz in [
                (-a, -b, -c),
                (a, -b, -c),
                (a, b, -c),
                (-a, b, -c),
                (-a, -b, c),
                (a, -b, c),
                (a, b, c),
                (-a, b, c),
            ]
        ]
        faces = [
            (0, 3, 2, 1),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]
        self.geometry(vertices, faces, material)
        if collision:
            self.colliders.append(
                {
                    "name": name,
                    "center": list(center),
                    "dimensions": list(dimensions),
                    "yaw": rotation,
                }
            )

    def cylinder(self, center, radius, height, material, sides=16):
        x, y, z = center
        vertices = [
            (
                x + radius * math.cos(i * math.tau / sides),
                y + radius * math.sin(i * math.tau / sides),
                z + dz,
            )
            for dz in (-height / 2, height / 2)
            for i in range(sides)
        ]
        faces = [tuple(reversed(range(sides))), tuple(range(sides, 2 * sides))]
        faces.extend(
            (i, (i + 1) % sides, (i + 1) % sides + sides, i + sides)
            for i in range(sides)
        )
        self.geometry(vertices, faces, material)

    def beam(self, a, b, width, material):
        a, b = Vector(a), Vector(b)
        delta = b - a
        helper = Batch("beam")
        helper.box("beam", (0, 0, 0), (width, width, delta.length), material)
        matrix = (
            Matrix.Translation((a + b) / 2)
            @ delta.to_track_quat("Z", "Y").to_matrix().to_4x4()
        )
        self.geometry(helper.vertices, helper.faces, material, matrix)

    def mesh(self, mesh, matrix=None, materials=None):
        offset = len(self.vertices)
        self.vertices.extend(
            tuple(matrix @ v.co) if matrix is not None else tuple(v.co)
            for v in mesh.vertices
        )
        for face in mesh.polygons:
            self.faces.append(tuple(offset + i for i in face.vertices))
            slots = materials if materials is not None else mesh.materials
            material = slots[face.material_index] if slots else None
            self.indices.append(self.material_index(material))

    def finish(self, parent, matrix=None, role="detail", building_id=""):
        if not self.faces:
            return None
        mesh = bpy.data.meshes.new(self.name + "_mesh")
        mesh.from_pydata(self.vertices, [], self.faces)
        mesh.update()
        for mat in self.materials:
            mesh.materials.append(mat)
        for p, mi in zip(mesh.polygons, self.indices):
            p.material_index = mi
        uv = mesh.uv_layers.new(name="UVMap")
        for face in mesh.polygons:
            normal = face.normal
            axis = max(range(3), key=lambda i: abs(normal[i]))
            axes = ((1, 2), (0, 2), (0, 1))[axis]
            for loop in face.loop_indices:
                co = mesh.vertices[mesh.loops[loop].vertex_index].co
                uv.data[loop].uv = (co[axes[0]], co[axes[1]])
        obj = bpy.data.objects.new(self.name, mesh)
        parent.objects.link(obj)
        if matrix is not None:
            obj.matrix_world = matrix
        obj["astra_role"] = role
        obj["building_id"] = building_id
        obj["source_recipe"] = "scripts/astra_city/build.py"
        return obj


def instance_mesh(mesh, name, parent, matrix, role="furniture", building_id=""):
    obj = bpy.data.objects.new(name, mesh)
    parent.objects.link(obj)
    obj.matrix_world = matrix
    obj["astra_role"] = role
    obj["building_id"] = building_id
    return obj


def transform(position=(0, 0, 0), yaw=0, scale=1):
    return (
        Matrix.Translation(Vector(position))
        @ Matrix.Rotation(yaw, 4, "Z")
        @ Matrix.Scale(scale, 4)
    )

"""Articulated, real geometry robot inspired by robot.png. Local forward is +Y."""
import bpy, math
from mathutils import Vector


def material(name, color, metallic=0, rough=0.3, emission=0):
    m = bpy.data.materials.new("robot1:" + name)
    m.diffuse_color = (*color, 1)
    m.use_nodes = True
    p = m.node_tree.nodes.get("Principled BSDF")
    p.inputs["Base Color"].default_value = (*color, 1)
    p.inputs["Metallic"].default_value = metallic
    p.inputs["Roughness"].default_value = rough
    if emission:
        p.inputs["Emission Color"].default_value = (*color, 1)
        p.inputs["Emission Strength"].default_value = emission
    return m


def sphere(name, location, scale, mat, parent=None):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=16, location=(0, 0, 0))
    o = bpy.context.object
    o.name = "robot1:" + name
    o.parent = parent
    o.location = location
    o.scale = scale
    o.data.materials.append(mat)
    for p in o.data.polygons:
        p.use_smooth = True
    return o


def box(name, location, scale, mat, parent=None, bevel=0.06):
    bpy.ops.mesh.primitive_cube_add(size=1)
    o = bpy.context.object
    o.name = "robot1:" + name
    o.parent = parent
    o.location = location
    for v in o.data.vertices:
        v.co.x *= scale[0]
        v.co.y *= scale[1]
        v.co.z *= scale[2]
    o.data.materials.append(mat)
    if bevel:
        mod = o.modifiers.new("Rounded shell", "BEVEL")
        mod.width = bevel
        mod.segments = 4
        o.modifiers.new("Normals", "WEIGHTED_NORMAL")
    return o


def line(name, points, mat, radius, parent=None):
    c = bpy.data.curves.new(name, "CURVE")
    c.dimensions = "3D"
    c.bevel_depth = radius
    c.bevel_resolution = 3
    s = c.splines.new("POLY")
    s.points.add(len(points) - 1)
    for p, q in zip(s.points, points):
        p.co = (*q, 1)
    o = bpy.data.objects.new("robot1:" + name, c)
    bpy.context.scene.collection.objects.link(o)
    o.data.materials.append(mat)
    o.parent = parent
    return o


class Robot:
    def __init__(self):
        self.white = material("Pearl ceramic", (0.82, 0.87, 0.92), 0.25, 0.24)
        self.dark = material("Graphite joints", (0.035, 0.048, 0.063), 0.55, 0.3)
        self.black = material("Visor glass", (0.009, 0.02, 0.029), 0.38, 0.18)
        self.cyan = material("Cyan light", (0.005, 0.52, 0.95), 0.25, 0.22, 2.5)
        self.root = bpy.data.objects.new("robot1:ROOT", None)
        bpy.context.scene.collection.objects.link(self.root)
        self.parts = []
        before = set(bpy.data.objects)
        sphere("Hip", (0, 0, 0.55), (0.20, 0.14, 0.15), self.dark, self.root)
        sphere("Torso", (0, 0, 0.85), (0.235, 0.175, 0.32), self.white, self.root)
        sphere("Neck", (0, 0, 1.11), (0.105, 0.10, 0.09), self.dark, self.root)
        sphere("Head shell", (0, 0, 1.31), (0.285, 0.245, 0.29), self.white, self.root)
        sphere(
            "Visor gasket",
            (0, 0.201, 1.32),
            (0.244, 0.079, 0.205),
            self.dark,
            self.root,
        )
        sphere("Visor", (0, 0.239, 1.33), (0.215, 0.055, 0.174), self.black, self.root)
        for side in [-1, 1]:
            sphere(
                "Ear joint",
                (side * 0.271, 0, 1.30),
                (0.04, 0.119, 0.137),
                self.dark,
                self.root,
            )
            sphere(
                "Ear blue ring",
                (side * 0.3, 0, 1.30),
                (0.018, 0.092, 0.106),
                self.cyan,
                self.root,
            )
            sphere(
                "Ear cap",
                (side * 0.315, 0, 1.30),
                (0.016, 0.072, 0.083),
                self.white,
                self.root,
            )
            pts = [
                (side * 0.10 + 0.045 * math.cos(t), 0.293, 1.33 + 0.049 * math.sin(t))
                for t in [math.pi * j / 20 for j in range(21)]
            ]
            line("Smiling eye", pts, self.cyan, 0.011, self.root)
        box(
            "Forehead blue accent",
            (0, 0.10, 1.573),
            (0.115, 0.05, 0.008),
            self.cyan,
            self.root,
            0.004,
        )
        box(
            "Chest badge",
            (0, 0.170, 0.96),
            (0.10, 0.012, 0.025),
            self.cyan,
            self.root,
            0.008,
        )
        line(
            "Waist light",
            [(-0.09, 0.138, 0.625), (0, 0.16, 0.61), (0.09, 0.138, 0.625)],
            self.cyan,
            0.007,
            self.root,
        )
        self.legs = []
        self.arms = []
        for side in [-1, 1]:
            leg = bpy.data.objects.new("robot1:Leg pivot", None)
            bpy.context.scene.collection.objects.link(leg)
            leg.parent = self.root
            leg.location = (side * 0.115, 0, 0.56)
            self.legs.append(leg)
            sphere("Thigh", (0, 0, -0.11), (0.095, 0.10, 0.16), self.white, leg)
            sphere("Knee", (0, 0.012, -0.235), (0.074, 0.08, 0.077), self.dark, leg)
            sphere("Shin", (0, 0, -0.34), (0.08, 0.09, 0.13), self.white, leg)
            box(
                "Foot sole",
                (0, 0.058, -0.505),
                (0.205, 0.32, 0.075),
                self.dark,
                leg,
                0.035,
            )
            sphere("Boot", (0, 0.065, -0.46), (0.106, 0.174, 0.10), self.white, leg)
            box(
                "Boot lamp",
                (0, 0.209, -0.453),
                (0.07, 0.022, 0.015),
                self.cyan,
                leg,
                0.006,
            )
            shoulder = (side * 0.251, 0, 1.025)
            sphere("Shoulder", shoulder, (0.08, 0.09, 0.105), self.dark, self.root)
            upper = sphere(
                "Upper arm", (0, 0, 0), (0.074, 0.077, 0.16), self.white, self.root
            )
            elbow = sphere(
                "Elbow", (0, 0, 0), (0.062, 0.062, 0.062), self.dark, self.root
            )
            lower = sphere(
                "Forearm", (0, 0, 0), (0.070, 0.075, 0.135), self.white, self.root
            )
            hand = sphere(
                "Palm", (0, 0, 0), (0.050, 0.058, 0.065), self.dark, self.root
            )
            self.arms.append((Vector(shoulder), upper, elbow, lower, hand))
        self.parts = list(set(bpy.data.objects) - before)

    def limb(self, obj, a, b, radius):
        obj.location = (a + b) / 2
        obj.rotation_euler = (b - a).to_track_quat("Z", "Y").to_euler()
        obj.scale = (radius, radius, (b - a).length / 2 + 0.018)

    def pose(self, p, yaw, phase, grasp, hand_y=0.385, hand_z=0.82):
        self.root.location = p
        self.root.rotation_euler.z = yaw
        for i, leg in enumerate(self.legs):
            leg.rotation_euler.x = 0.32 * math.sin(phase + i * math.pi)
        for i, (s, u, e, l, h) in enumerate(self.arms):
            side = -1 if i == 0 else 1
            rest = Vector(
                (side * 0.29, 0.05 + 0.06 * math.sin(phase + i * math.pi), 0.57)
            )
            holding = Vector((side * 0.16, hand_y, hand_z))
            hand = rest.lerp(holding, grasp)
            elbow = Vector((side * 0.33, 0.025 + 0.12 * grasp, 0.81))
            self.limb(u, s, elbow, 0.071)
            e.location = elbow
            self.limb(l, elbow, hand, 0.065)
            h.location = hand

    def keyframe(self, frame):
        for o in [self.root, *self.parts]:
            if o.type in {"MESH", "EMPTY"}:
                for prop in ["location", "rotation_euler", "scale"]:
                    o.keyframe_insert(data_path=prop, frame=frame)

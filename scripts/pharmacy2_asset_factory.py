"""Manufacturing-detail extensions of the authored pharmacy5 asset factories.

Real mesh packaging, cap fluting, carton folds, blister pockets, LCD housings,
keycaps and serviceable counter equipment. Print maps are procedural artwork.
"""
import bpy, math, json, sys
from pathlib import Path
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate_urban_v3_pharmacy as P

P.PREFIX = "pharmacy2:"


class PharmacyDetailFactory:
    def __init__(self, assets):
        self.assets = Path(assets)
        self.catalog = json.loads((self.assets / "catalog.json").read_text())
        self.masters = []
        self.cache = {}
        self.white = self.mat("moulded_HDPE", (0.78, 0.79, 0.75), 0.30)
        self.paper = self.mat("carton_board", (0.81, 0.80, 0.73), 0.62)
        self.black = self.mat("anthracite_ABS", (0.020, 0.027, 0.031), 0.34)
        self.rubber = self.mat("rubber", (0.009, 0.012, 0.013), 0.68)
        self.silver = self.mat("anodized_aluminum", (0.42, 0.46, 0.48), 0.26, 0.85)
        self.ink = self.mat("laser_legend", (0.63, 0.70, 0.69), 0.53)
        self.foil = self.mat("embossed_foil", (0.63, 0.64, 0.61), 0.32, 0.92)
        self.teal = self.mat("clinical_teal", (0.06, 0.23, 0.24), 0.37)
        self.clear = self.mat("clear_PET", (0.92, 0.96, 0.98), 0.07)
        bs = self.clear.node_tree.nodes.get("Principled BSDF")
        bs.inputs["Transmission Weight"].default_value = 1.0
        bs.inputs["IOR"].default_value = 1.47
        self.led = self.mat("status_LED", (0.025, 0.55, 0.33), 0.3)
        bs = self.led.node_tree.nodes.get("Principled BSDF")
        bs.inputs["Emission Color"].default_value = (0.03, 0.55, 0.30, 1)
        bs.inputs["Emission Strength"].default_value = 0.7
        for mat, scale, strength in [
            (self.black, 850, 0.08),
            (self.white, 650, 0.065),
            (self.paper, 980, 0.13),
            (self.foil, 190, 0.14),
        ]:
            nd = mat.node_tree.nodes
            lk = mat.node_tree.links
            n = nd.new("ShaderNodeTexNoise")
            n.inputs["Scale"].default_value = scale
            b = nd.new("ShaderNodeBump")
            b.inputs["Strength"].default_value = strength
            b.inputs["Distance"].default_value = 0.00007
            lk.new(n.outputs["Fac"], b.inputs["Height"])
            lk.new(b.outputs["Normal"], nd.get("Principled BSDF").inputs["Normal"])

    def mat(self, name, rgb, rough=0.4, metal=0):
        m = bpy.data.materials.new("pharmacy2:" + name)
        m.use_nodes = True
        p = m.node_tree.nodes.get("Principled BSDF")
        p.inputs["Base Color"].default_value = (*rgb, 1)
        p.inputs["Roughness"].default_value = rough
        p.inputs["Metallic"].default_value = metal
        return m

    def printed(self, file, emission=0):
        key = (file, emission)
        if key in self.cache:
            return self.cache[key]
        m = self.mat(file, (1, 1, 1), 0.29 if emission else 0.55)
        n = m.node_tree.nodes.new("ShaderNodeTexImage")
        n.image = bpy.data.images.load(str(self.assets / file), check_existing=True)
        n.image.pack()
        p = m.node_tree.nodes.get("Principled BSDF")
        m.node_tree.links.new(n.outputs["Color"], p.inputs["Base Color"])
        if emission:
            m.node_tree.links.new(n.outputs["Color"], p.inputs["Emission Color"])
            p.inputs["Emission Strength"].default_value = emission
        self.cache[key] = m
        return m

    def col(self, name):
        c = bpy.data.collections.new("PHARMACY2_" + name)
        c["factory"] = "PharmacyDetailFactory"
        c["source_factory"] = "generate_urban_v3_pharmacy.py"
        self.masters.append(c)
        return c

    def box(self, c, name, loc, dim, mat, r=0.004, rot=(0, 0, 0)):
        o = P.box(
            c, name, loc, dim, mat, min(r, min(dim) * 0.45), rot, "manufactured_detail"
        )
        # The legacy box helper winds its six faces inward; manufactured shells
        # require outward normals, particularly at transmissive interfaces.
        o.data.flip_normals()
        for mod in o.modifiers:
            if mod.type == "BEVEL":
                mod.segments = 5
                mod.harden_normals = True
        return o

    def mesh(self, c, name, verts, faces, mat, smooth=False):
        me = bpy.data.meshes.new(name)
        me.from_pydata(verts, [], faces)
        me.materials.append(mat)
        me.update()
        o = bpy.data.objects.new("pharmacy2:" + name, me)
        c.objects.link(o)
        for p in me.polygons:
            p.use_smooth = smooth
        return o

    def plane(self, c, name, loc, w, h, mat, rot=(math.pi / 2, 0, 0)):
        o = self.mesh(
            c,
            name,
            [
                (-w / 2, -h / 2, 0),
                (w / 2, -h / 2, 0),
                (w / 2, h / 2, 0),
                (-w / 2, h / 2, 0),
            ],
            [(0, 1, 2, 3)],
            mat,
        )
        uv = o.data.uv_layers.new()
        coords = [(0, 0), (1, 0), (1, 1), (0, 1)]
        for k, v in enumerate(coords):
            uv.data[k].uv = v
        o.location = loc
        o.rotation_euler = rot
        return o

    def lathe(self, c, name, profile, mat, loc=(0, 0, 0), rot=(0, 0, 0), n=96, ribs=0):
        vs = []
        for j, (r, z) in enumerate(profile):
            for i in range(n):
                a = i * math.tau / n
                rr = r + (
                    0.009 * (0.5 + 0.5 * math.cos(ribs * a))
                    if ribs and 1 < j < len(profile) - 2
                    else 0
                )
                vs.append((rr * math.cos(a), rr * math.sin(a), z))
        fs = [
            (j * n + i, j * n + (i + 1) % n, (j + 1) * n + (i + 1) % n, (j + 1) * n + i)
            for j in range(len(profile) - 1)
            for i in range(n)
        ]
        fs.extend(
            [
                tuple(reversed(range(n))),
                tuple((len(profile) - 1) * n + i for i in range(n)),
            ]
        )
        o = self.mesh(c, name, vs, fs, mat, True)
        o.data.polygons[-1].use_smooth = False
        o.data.polygons[-2].use_smooth = False
        o.location = loc
        o.rotation_euler = rot
        return o

    def tube(self, c, name, pts, r, mat):
        o = P.curve_tube(c, name, pts, r, mat)
        o.data.resolution_u = 16
        o.data.bevel_resolution = 4
        return o

    def text(self, c, name, body, loc, size, mat=None, rot=(math.pi / 2, 0, 0)):
        cu = bpy.data.curves.new(name, "FONT")
        cu.body = body
        cu.size = size
        cu.align_x = "CENTER"
        cu.align_y = "CENTER"
        cu.extrude = 0.00004
        cu.resolution_u = 4
        cu.materials.append(mat or self.ink)
        o = bpy.data.objects.new("pharmacy2:" + name, cu)
        c.objects.link(o)
        o.location = loc
        o.rotation_euler = rot
        return o

    def ellipsoid(self, c, name, loc, scale, mat, n=32, rings=16):
        vs = []
        for j in range(rings + 1):
            a = math.pi * j / rings
            for i in range(n):
                t = math.tau * i / n
                vs.append(
                    (
                        scale[0] * math.sin(a) * math.cos(t),
                        scale[1] * math.sin(a) * math.sin(t),
                        scale[2] * math.cos(a),
                    )
                )
        fs = [
            (j * n + i, (j + 1) * n + i, (j + 1) * n + (i + 1) % n, j * n + (i + 1) % n)
            for j in range(rings)
            for i in range(n)
        ]
        o = self.mesh(c, name, vs, fs, mat, True)
        o.location = loc
        return o

    def wrapped_surface(self, c, name, rings, mat, n=128):
        # u=.5 is the printed front facing -Y.
        vs = [
            (
                rx * math.cos(math.tau * i / n + math.pi / 2),
                ry * math.sin(math.tau * i / n + math.pi / 2),
                z,
            )
            for rx, ry, z in rings
            for i in range(n + 1)
        ]
        fs = [
            (
                j * (n + 1) + i,
                j * (n + 1) + i + 1,
                (j + 1) * (n + 1) + i + 1,
                (j + 1) * (n + 1) + i,
            )
            for j in range(len(rings) - 1)
            for i in range(n)
        ]
        o = self.mesh(c, name, vs, fs, mat, True)
        uv = o.data.uv_layers.new()
        for poly in o.data.polygons:
            for k in poly.loop_indices:
                ix = o.data.loops[k].vertex_index
                uv.data[k].uv = (ix % (n + 1) / n, ix // (n + 1) / (len(rings) - 1))
        return o

    def carton(self, sku):
        c = self.col("CARTON_" + str(sku["id"]))
        pre = sku["prefix"]
        self.box(c, "folded_cardboard_shell", (0, 0, 0.5), (1, 1, 1), self.paper, 0.006)
        self.plane(
            c,
            "printed_front",
            (0, -0.5006, 0.5),
            0.983,
            0.986,
            self.printed(pre + "_front.png"),
        )
        self.plane(
            c,
            "printed_back",
            (0, 0.5006, 0.5),
            0.982,
            0.986,
            self.printed(pre + "_back.png"),
            (math.pi / 2, 0, math.pi),
        )
        for side in [-1, 1]:
            self.plane(
                c,
                "printed_side",
                (side * 0.5006, 0, 0.5),
                0.982,
                0.98,
                self.printed(pre + "_back.png"),
                (math.pi / 2, 0, side * math.pi / 2),
            )
        # Individual tucked flaps, score line, paper edge and small tamper seals.
        self.box(
            c,
            "top_tuck_flap",
            (0, -0.035, 1.002),
            (0.97, 0.91, 0.005),
            self.paper,
            0.001,
        )
        self.box(
            c,
            "tuck_overlap",
            (0, 0.452, 1.003),
            (0.93, 0.032, 0.003),
            self.white,
            0.001,
        )
        self.box(
            c, "bottom_fold", (0, 0, 0.002), (0.97, 0.96, 0.004), self.paper, 0.001
        )
        self.plane(
            c,
            "printed_top_batch",
            (0, 0, 1.005),
            0.90,
            0.83,
            self.printed(pre + "_back.png"),
            (0, 0, 0),
        )
        self.box(
            c,
            "glue_tab_seam",
            (0.496, 0.37, 0.5),
            (0.002, 0.005, 0.97),
            self.white,
            0.0005,
        )
        for j in range(3):
            for k in range(4):
                self.ellipsoid(
                    c,
                    "embossed_braille",
                    (-0.34 + k * 0.058, -0.502, 0.20 + j * 0.044),
                    (0.008, 0.0024, 0.009),
                    self.paper,
                    12,
                    6,
                )
        return c

    def bottle(self, sku):
        c = self.col("BOTTLE_" + str(sku["id"]))
        i = sku["id"]
        body = self.mat(
            "bottle_resin_" + str(i),
            [(0.27, 0.10, 0.027), (0.74, 0.77, 0.71), (0.65, 0.72, 0.73)][i % 3],
            0.25,
        )
        self.lathe(
            c,
            "profiled_bottle",
            [
                (0.39, 0),
                (0.46, 0.012),
                (0.489, 0.036),
                (0.493, 0.075),
                (0.493, 0.58),
                (0.489, 0.64),
                (0.46, 0.70),
                (0.40, 0.752),
                (0.30, 0.79),
                (0.279, 0.81),
                (0.279, 0.855),
            ],
            body,
            n=128,
        )
        self.wrapped_surface(
            c,
            "printed_paper_wrap",
            [(0.495, 0.495, 0.15), (0.495, 0.495, 0.60)],
            self.printed(sku["prefix"] + "_wrap.png"),
        )
        cap = self.white if i % 3 else self.teal
        self.lathe(
            c,
            "tamper_evident_band",
            [(0.302, 0.795), (0.333, 0.802), (0.335, 0.827), (0.303, 0.831)],
            cap,
            n=128,
        )
        self.lathe(
            c,
            "safety_cap_fluted",
            [
                (0.306, 0.828),
                (0.335, 0.839),
                (0.342, 0.855),
                (0.342, 0.958),
                (0.335, 0.982),
                (0.31, 0.997),
            ],
            cap,
            n=256,
            ribs=64,
        )
        self.lathe(
            c,
            "top_cap_disc",
            [(0.0, 0.994), (0.295, 0.994), (0.303, 0.998), (0.285, 1.0)],
            cap,
            n=96,
        )
        self.text(
            c,
            "cap_embossing",
            "PUSH\n& TURN",
            (0, 0, 1.001),
            0.075,
            self.white,
            (0, 0, 0),
        )
        for j in range(12):
            a = math.tau * j / 12
            self.box(
                c,
                "tamper_bridge",
                (0.323 * math.cos(a), 0.323 * math.sin(a), 0.829),
                (0.018, 0.012, 0.018),
                cap,
                0.002,
                (0, 0, a),
            )
        return c

    def tube_pack(self, sku):
        c = self.col("TUBE_" + str(sku["id"]))
        self.lathe(
            c,
            "tube_screw_cap",
            [(0.27, 0), (0.31, 0.01), (0.326, 0.025), (0.326, 0.15), (0.30, 0.18)],
            self.white,
            n=128,
            ribs=32,
        )
        rings = [
            (0.29, 0.36, 0.14),
            (0.39, 0.44, 0.21),
            (0.46, 0.48, 0.30),
            (0.465, 0.43, 0.52),
            (0.46, 0.32, 0.74),
            (0.45, 0.18, 0.88),
            (0.44, 0.045, 0.972),
        ]
        self.wrapped_surface(
            c, "printed_laminate_tube", rings, self.printed(sku["prefix"] + "_wrap.png")
        )
        self.box(
            c,
            "heat_sealed_crimp",
            (0, 0, 0.983),
            (0.90, 0.094, 0.026),
            self.paper,
            0.005,
        )
        for i in range(28):
            self.box(
                c,
                "crimp_tooth",
                (-0.425 + i * 0.0315, -0.049, 0.982),
                (0.005, 0.007, 0.019),
                self.white,
                0.001,
            )
        self.box(
            c,
            "crimp_batch_tab",
            (0.25, -0.052, 0.98),
            (0.24, 0.003, 0.019),
            self.paper,
            0.0005,
        )
        return c

    def screw(self, c, loc, r=0.003):
        self.lathe(
            c,
            "recessed_screw",
            [(r * 0.8, 0), (r, 0.001), (r, 0.0018), (r * 0.7, 0.0022)],
            self.silver,
            loc,
            (math.pi / 2, 0, 0),
            n=24,
        )
        self.box(
            c,
            "screw_drive",
            (loc[0], loc[1] - 0.0022, loc[2]),
            (r * 1.25, 0.0005, r * 0.22),
            self.rubber,
            0.0001,
        )

    def monitor(self):
        c = self.col("POS_COMPUTER")
        self.box(
            c,
            "cast_monitor_foot",
            (0, 0.025, 0.019),
            (0.42, 0.28, 0.038),
            self.black,
            0.017,
        )
        for x in [-0.14, 0.14]:
            for y in [-0.065, 0.10]:
                self.box(
                    c,
                    "rubber_foot",
                    (x, y, 0.004),
                    (0.065, 0.04, 0.008),
                    self.rubber,
                    0.004,
                )
        self.box(
            c,
            "stand_alloy_stem",
            (0, 0.05, 0.178),
            (0.063, 0.074, 0.29),
            self.silver,
            0.015,
            (-0.12, 0, 0),
        )
        self.lathe(
            c,
            "tilt_hinge",
            [(0.037, 0), (0.043, 0.01), (0.043, 0.11), (0.037, 0.12)],
            self.silver,
            (-0.06, 0.038, 0.31),
            (0, math.pi / 2, 0),
        )
        before = set(c.objects)
        self.box(
            c,
            "screen_front_moulding",
            (0, 0, 0.53),
            (0.62, 0.086, 0.46),
            self.black,
            0.014,
        )
        self.box(
            c,
            "rear_service_shell",
            (0, 0.051, 0.53),
            (0.565, 0.035, 0.393),
            self.black,
            0.016,
        )
        self.box(
            c,
            "rear_panel_seam",
            (0, 0.070, 0.53),
            (0.51, 0.008, 0.34),
            self.rubber,
            0.006,
        )
        self.plane(
            c,
            "real_LCD",
            (0, -0.044, 0.543),
            0.568,
            0.355,
            self.printed("dispensing_lcd.png", 0.35),
        )
        self.text(
            c,
            "bezel_etching",
            "WELL / POINT OF CARE",
            (0, -0.0445, 0.334),
            0.009,
            self.ink,
        )
        for j in range(30):
            self.box(
                c,
                "rear_vent",
                (-0.235 + j * 0.0162, 0.076, 0.669),
                (0.009, 0.004, 0.047),
                self.rubber,
                0.001,
            )
        for x in [-0.051, 0.051]:
            for z in [0.472, 0.574]:
                self.screw(c, (x, 0.079, z), 0.0032)
        self.lathe(
            c,
            "power_status",
            [(0.0016, 0), (0.0016, 0.0012)],
            self.led,
            (0.264, -0.044, 0.335),
            (math.pi / 2, 0, 0),
            n=24,
        )
        for j in range(3):
            self.box(
                c,
                "USB_port_recess",
                (0.307, 0.023, 0.46 + j * 0.038),
                (0.002, 0.026, 0.011),
                self.rubber,
                0.001,
            )
            self.box(
                c,
                "USB_contact_tongue",
                (0.308, 0.024, 0.46 + j * 0.038),
                (0.002, 0.017, 0.003),
                self.silver,
                0.0005,
            )
        T = (
            Matrix.Translation((0, 0, 0.53))
            @ Matrix.Rotation(-0.13, 4, "X")
            @ Matrix.Translation((0, 0, -0.53))
        )
        for o in set(c.objects) - before:
            o.matrix_world = T @ Matrix.LocRotScale(
                o.location, o.rotation_euler.to_quaternion(), o.scale
            )
        self.tube(
            c,
            "monitor_power_data_cable",
            [
                (0.06, 0.092, 0.35),
                (0.10, 0.13, 0.23),
                (0.09, 0.12, 0.08),
                (0.22, 0.14, 0.01),
                (0.28, 0.05, 0.008),
            ],
            0.004,
            self.rubber,
        )
        return c

    def keyboard(self):
        c = self.col("FULL_KEYBOARD")
        self.box(
            c,
            "keyboard_lower_shell",
            (0, 0, 0.011),
            (0.56, 0.27, 0.022),
            self.black,
            0.010,
        )
        self.box(
            c,
            "keyboard_upper_deck",
            (0, 0.002, 0.024),
            (0.55, 0.259, 0.019),
            self.black,
            0.008,
        )
        rows = [
            [
                "Esc",
                "F1",
                "F2",
                "F3",
                "F4",
                "F5",
                "F6",
                "F7",
                "F8",
                "F9",
                "F10",
                "F11",
                "F12",
            ],
            ["`", "1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "=", "Back"],
            ["Tab", "Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P", "[", "]", "\\"],
            ["Caps", "A", "S", "D", "F", "G", "H", "J", "K", "L", ";", "'", "Enter"],
            ["Shift", "Z", "X", "C", "V", "B", "N", "M", ",", ".", "/", "Shift"],
            ["Ctrl", "Win", "Alt", "SPACE", "Alt", "Fn", "Ctrl"],
        ]
        key_count = 0

        def key(label, x, y, w=0.019):
            nonlocal key_count
            self.box(
                c,
                "sculpted_keycap_" + label,
                (x, y, 0.042),
                (w, 0.026, 0.018),
                self.black,
                0.0035,
            )
            self.text(
                c,
                "key_legend_" + label,
                "" if label == "SPACE" else label,
                (x, y, 0.0514),
                0.005 if len(label) > 2 else 0.008,
                self.ink,
                (0, 0, 0),
            )
            key_count += 1

        for row, labels in enumerate(rows):
            y = 0.100 - row * 0.033
            x = -0.264
            widths = [1] * len(labels)
            if row == 2:
                widths[0] = 1.35
            if row == 3:
                widths[0] = 1.5
                widths[-1] = 1.75
            if row == 4:
                widths[0] = 2
                widths[-1] = 2.25
            if row == 5:
                widths = [1.25, 1.25, 1.25, 6, 1.25, 1.25, 1.25]
            for label, units in zip(labels, widths):
                w = 0.022 * units - 0.003
                key(label, x + w / 2, y, w)
                x += 0.022 * units
        for row, labels in enumerate(
            [
                ["Prt", "Scr", "Pau"],
                ["Ins", "Home", "PgU"],
                ["Del", "End", "PgD"],
                [],
                ["", "Up", ""],
                ["Left", "Dn", "Right"],
            ]
        ):
            for j, label in enumerate(labels):
                if label:
                    key(label, 0.104 + j * 0.023, 0.100 - row * 0.033)
        for row, labels in enumerate(
            [
                ["Num", "/", "*", "-"],
                ["7", "8", "9", "+"],
                ["4", "5", "6", "+"],
                ["1", "2", "3", "Ent"],
                ["0", "0", ".", "Ent"],
            ]
        ):
            for j, label in enumerate(labels):
                key(label, 0.182 + j * 0.023, 0.067 - row * 0.033)
        for i in range(3):
            self.lathe(
                c,
                "keyboard_status_LED",
                [(0.001, 0), (0.001, 0.001)],
                self.led,
                (0.195 + i * 0.018, 0.111, 0.035),
                n=16,
            )
        self.tube(
            c,
            "keyboard_USB_cable",
            [
                (0.12, 0.134, 0.012),
                (0.12, 0.18, 0.012),
                (0.20, 0.22, 0.009),
                (0.28, 0.18, 0.007),
            ],
            0.0027,
            self.rubber,
        )
        c["independent_keycaps"] = key_count
        return c

    def mouse(self):
        c = self.col("OPTICAL_MOUSE")
        self.box(
            c, "mouse_base", (0, 0, 0.003), (0.066, 0.109, 0.006), self.rubber, 0.003
        )
        self.ellipsoid(
            c,
            "ergonomic_mouse_shell",
            (0, 0, 0.018),
            (0.035, 0.057, 0.016),
            self.black,
            64,
            24,
        )
        self.box(
            c,
            "button_divide",
            (0, -0.025, 0.033),
            (0.0012, 0.051, 0.001),
            self.rubber,
            0.0003,
        )
        self.lathe(
            c,
            "scroll_wheel",
            [(0.008, 0), (0.009, 0.003), (0.009, 0.009), (0.008, 0.012)],
            self.rubber,
            (-0.006, -0.029, 0.033),
            (0, math.pi / 2, 0),
            n=48,
        )
        self.tube(
            c,
            "mouse_cable",
            [
                (0, 0.052, 0.01),
                (0.03, 0.10, 0.008),
                (0.07, 0.12, 0.007),
                (0.12, 0.11, 0.006),
            ],
            0.002,
            self.rubber,
        )
        return c

    def printer(self):
        c = self.col("THERMAL_LABEL_PRINTER")
        self.box(
            c,
            "printer_lower_chassis",
            (0, 0, 0.07),
            (0.55, 0.39, 0.14),
            self.black,
            0.024,
        )
        self.box(
            c,
            "printer_upper_shell",
            (0, 0.012, 0.207),
            (0.56, 0.39, 0.235),
            self.white,
            0.045,
        )
        self.box(
            c,
            "lid_separation",
            (0, -0.007, 0.164),
            (0.559, 0.397, 0.006),
            self.rubber,
            0.002,
        )
        self.box(
            c,
            "lid_view_window",
            (0, -0.02, 0.326),
            (0.33, 0.24, 0.003),
            self.black,
            0.012,
        )
        self.box(
            c,
            "feed_aperture",
            (0, -0.199, 0.137),
            (0.393, 0.009, 0.052),
            self.rubber,
            0.006,
        )
        self.lathe(
            c,
            "feed_roller",
            [(0.015, 0), (0.018, 0.009), (0.018, 0.37), (0.015, 0.38)],
            self.rubber,
            (-0.19, -0.206, 0.127),
            (0, math.pi / 2, 0),
        )
        # Curved printed stock projects from the working feed slot.
        o = self.plane(
            c,
            "printed_dispensing_label",
            (0, -0.284, 0.124),
            0.35,
            0.19,
            self.printed("dispensing_label.png"),
            (0, 0, 0),
        )
        o.rotation_euler.x = -0.06
        self.box(
            c,
            "tear_off_serration",
            (0, -0.214, 0.148),
            (0.39, 0.011, 0.005),
            self.silver,
            0.001,
        )
        for j in range(25):
            self.box(
                c,
                "tear_bar_tooth",
                (-0.18 + j * 0.015, -0.222, 0.148),
                (0.006, 0.010, 0.005),
                self.silver,
                0.001,
            )
        for side in [-1, 1]:
            self.box(
                c,
                "lid_release",
                (side * 0.284, -0.09, 0.184),
                (0.013, 0.07, 0.05),
                self.teal,
                0.005,
            )
            for j in range(11):
                self.box(
                    c,
                    "side_vent",
                    (side * 0.278, 0.008 + j * 0.013, 0.064),
                    (0.004, 0.006, 0.061),
                    self.rubber,
                    0.001,
                )
        self.lathe(
            c,
            "feed_button",
            [(0.015, 0), (0.019, 0.003), (0.018, 0.006)],
            self.teal,
            (0.21, -0.09, 0.327),
            n=48,
        )
        self.lathe(
            c,
            "printer_ready_LED",
            [(0.002, 0), (0.002, 0.002)],
            self.led,
            (0.21, -0.045, 0.329),
            n=24,
        )
        self.text(
            c, "printer_model", "WELL / LABEL 420", (0, -0.202, 0.061), 0.017, self.ink
        )
        self.tube(
            c,
            "printer_USB_power",
            [
                (0.22, 0.195, 0.065),
                (0.26, 0.23, 0.04),
                (0.30, 0.23, 0.012),
                (0.37, 0.18, 0.008),
            ],
            0.0037,
            self.rubber,
        )
        return c

    def scanner(self):
        c = self.col("BARCODE_IMAGER")
        self.box(
            c,
            "scanner_weighted_base",
            (0, 0, 0.016),
            (0.22, 0.18, 0.032),
            self.black,
            0.013,
        )
        self.box(
            c,
            "scanner_tilted_stem",
            (0, 0.018, 0.074),
            (0.064, 0.055, 0.12),
            self.black,
            0.020,
            (-0.3, 0, 0),
        )
        self.box(
            c,
            "scanner_head",
            (0, -0.012, 0.16),
            (0.23, 0.14, 0.117),
            self.black,
            0.025,
            (-0.15, 0, 0),
        )
        self.box(
            c,
            "optical_window",
            (0, -0.085, 0.163),
            (0.17, 0.004, 0.073),
            self.rubber,
            0.012,
        )
        self.lathe(
            c,
            "imager_optics",
            [(0.016, 0), (0.022, 0.005), (0.020, 0.010)],
            self.silver,
            (0, -0.088, 0.165),
            (math.pi / 2, 0, 0),
            n=64,
        )
        self.lathe(
            c,
            "imager_glass",
            [(0.015, 0), (0.015, 0.001)],
            self.clear,
            (0, -0.099, 0.165),
            (math.pi / 2, 0, 0),
            n=64,
        )
        self.box(
            c,
            "scan_aiming_illumination",
            (0, -0.089, 0.14),
            (0.114, 0.002, 0.002),
            self.led,
            0.0005,
        )
        self.tube(
            c,
            "scanner_data_cable",
            [
                (0, 0.08, 0.02),
                (0.05, 0.12, 0.015),
                (0.11, 0.14, 0.008),
                (0.16, 0.15, 0.007),
            ],
            0.003,
            self.rubber,
        )
        return c

    def blister(self):
        c = self.col("BLISTER_STRIP")
        self.box(
            c,
            "rounded_foil_card",
            (0, 0, 0.0007),
            (0.090, 0.17, 0.0014),
            self.foil,
            0.00065,
        )
        for j in range(5):
            for i in range(2):
                x = -0.021 + i * 0.042
                y = -0.064 + j * 0.032
                self.ellipsoid(
                    c,
                    "scored_tablet",
                    (x, y, 0.0045),
                    (0.0085, 0.011, 0.0035),
                    self.white,
                    32,
                    12,
                )
                self.box(
                    c,
                    "tablet_score",
                    (x, y, 0.0079),
                    (0.013, 0.0006, 0.00025),
                    self.paper,
                    0.0001,
                )
                # Formed clear pocket is a hollow dome with physical film thickness.
                n = 40
                rows = 10
                vs = []
                for k in range(rows + 1):
                    a = math.pi / 2 * k / rows
                    for l in range(n):
                        t = math.tau * l / n
                        vs.append(
                            (
                                x + 0.013 * math.cos(a) * math.cos(t),
                                y + 0.0145 * math.cos(a) * math.sin(t),
                                0.0017 + 0.011 * math.sin(a),
                            )
                        )
                fs = [
                    (
                        k * n + l,
                        k * n + (l + 1) % n,
                        (k + 1) * n + (l + 1) % n,
                        (k + 1) * n + l,
                    )
                    for k in range(rows)
                    for l in range(n)
                ]
                o = self.mesh(c, "thermoformed_PET_pocket", vs, fs, self.clear, True)
                mod = o.modifiers.new("PET film thickness", "SOLIDIFY")
                mod.thickness = 0.0002
        self.text(
            c,
            "blister_batch",
            "WC26  042  |  EXP 09/28",
            (0, -0.081, 0.0016),
            0.0025,
            self.black,
            (0, 0, 0),
        )
        return c

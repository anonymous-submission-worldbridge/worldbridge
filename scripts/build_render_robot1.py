"""Build measured routes, articulated manipulation, and two real camera renders."""
import bpy, sys, json, math, argparse, heapq, time, shutil, subprocess, os, hashlib
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from robot1_tasks import SOURCE, OUT, write, png_complete, png_valid
from robot1_model import Robot, box, material
from robot1_camera import stable_positions


def log(*args):
    print("ROBOT1", *args, flush=True)


def smooth(t):
    return t * t * (3 - 2 * t)


def heading(v):
    return math.atan2(-v.x, v.y)


def aim(camera, p, target, lens=24):
    camera.location = p
    camera.rotation_euler = (
        (Vector(target) - Vector(p)).to_track_quat("-Z", "Y").to_euler()
    )
    camera.data.lens = lens


def camera(name):
    d = bpy.data.cameras.new(name)
    o = bpy.data.objects.new(name, d)
    bpy.context.scene.collection.objects.link(o)
    d.clip_start = 0.055
    d.clip_end = 1200
    return o


class Planner:
    def __init__(self, scene, m):
        self.s = scene
        self.m = m
        self.dg = bpy.context.evaluated_depsgraph_get()
        self.cache = {}
        self.tests = 0
        self.ramps = []

    def ray(self, p, v, d):
        self.tests += 1
        return self.s.ray_cast(self.dg, Vector(p), Vector(v), distance=d)

    def floor(self, x, y, guess=0.04):
        hit, p, n, idx, ob, mat = self.ray((x, y, guess + 0.65), (0, 0, -1), 3.4)
        if hit and any(
            word in ob.name.lower()
            for word in ["water_surface", "lake_water", "river_water"]
        ):
            return None
        return p.z if hit else None

    def segment(self, a, b, radius=0.32):
        a, b = Vector(a), Vector(b)
        vec = b - a
        length = vec.length
        if length < 0.0001:
            return True
        side = Vector((-vec.y, vec.x, 0)).normalized() * radius
        for off in [-side, Vector((0, 0, 0)), side]:
            for h in [0.22, 0.72, 1.35, 1.58]:
                # Horizontal torso rays permit ordinary small ground steps, checked below.
                p = a + off + Vector((0, 0, h))
                hit, *_ = self.ray(p, vec.normalized(), length)
                if hit:
                    return False
        if length > 1.3:
            for j in range(1, math.ceil(length / 0.5)):
                q = a.lerp(b, j / math.ceil(length / 0.5))
                z = self.floor(q.x, q.y, q.z)
                if z is None or abs(z + 0.025 - q.z) > 0.18:
                    return False
        return True

    def outside(self, x, y):
        k = (round(x, 4), round(y, 4))
        if k in self.cache:
            return self.cache[k]
        hit, loc, normal, idx, ob, mat = self.ray((x, y, 2.35), (0, 0, -1), 4.0)
        ground_words = [
            "paver",
            "concrete",
            "paving",
            "asphalt",
            "floor",
            "deck",
            "slab",
            "walk",
            "platform",
            "forecourt",
            "ground",
            "road",
            "ramp",
            "earth_context",
        ]
        valid = (
            hit
            and normal.z > 0.82
            and -0.2 < loc.z < 1.35
            and any(word in ob.name.lower() for word in ground_words)
        )
        p = Vector((x, y, loc.z + 0.025)) if valid else None
        if p is not None:
            for v in [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0)]:
                if any(
                    self.ray(p + Vector((0, 0, h)), v, 0.36)[0]
                    for h in [0.28, 0.85, 1.4]
                ):
                    p = None
                    break
        self.cache[k] = p
        return p

    def astar(self, a, b):
        a, b = Vector(a), Vector(b)
        if self.segment(a, b):
            return [a, b]
        step = 0.6
        origin = Vector((a.x, a.y, 0))
        end = (round((b.x - a.x) / step), round((b.y - a.y) / step))

        def pos(k):
            return self.outside(origin.x + k[0] * step, origin.y + k[1] * step)

        start = (0, 0)
        q = [((a - b).length, 0, start)]
        cost = {start: 0}
        prev = {}
        found = None
        closed = set()
        margin = 18
        minx = min(0, end[0]) - int(margin / step)
        maxx = max(0, end[0]) + int(margin / step)
        miny = min(0, end[1]) - int(margin / step)
        maxy = max(0, end[1]) + int(margin / step)
        while q and len(closed) < 22000:
            _, g, k = heapq.heappop(q)
            if k in closed:
                continue
            closed.add(k)
            p = a if k == start else pos(k)
            if p is None:
                continue
            if (p - b).length < 1.25 and self.segment(p, b):
                found = k
                break
            for dx, dy in [
                (1, 0),
                (-1, 0),
                (0, 1),
                (0, -1),
                (1, 1),
                (-1, 1),
                (1, -1),
                (-1, -1),
            ]:
                nk = (k[0] + dx, k[1] + dy)
                if (
                    not (minx <= nk[0] <= maxx and miny <= nk[1] <= maxy)
                    or nk in closed
                ):
                    continue
                np = pos(nk)
                if np is None or abs(np.z - p.z) > 0.25 or not self.segment(p, np):
                    continue
                ng = g + (np - p).length
                if ng < cost.get(nk, 1e9):
                    cost[nk] = ng
                    prev[nk] = k
                    heapq.heappush(q, (ng + (np - b).length, ng, nk))
        if found is None:
            raise RuntimeError(
                f"No collision-checked outdoor path: {list(a)} -> {list(b)}; explored {len(closed)} nodes"
            )
        ks = [found]
        while ks[-1] != start:
            ks.append(prev[ks[-1]])
        points = [a] + [pos(k) for k in reversed(ks[:-1])] + [b]
        result = [points[0]]
        i = 0
        while i < len(points) - 1:
            j = len(points) - 1
            while j > i + 1 and not self.segment(points[i], points[j]):
                j -= 1
            result.append(points[j])
            i = j
        return result

    def access_ramp(self, b, meta, T):
        inside = min(1.6, meta["inside_y"] - 0.8)
        end = -13.0
        n = math.ceil((inside - end) / 0.23)
        ys = [inside + (end - inside) * i / n for i in range(n + 1)]
        heights = []
        for y in ys:
            zs = []
            for x in [-0.30, 0, 0.30]:
                p = T @ Vector((x, y, meta["floor_z"]))
                z = self.floor(p.x, p.y, meta["floor_z"])
                if z is None:
                    raise RuntimeError(
                        "Missing support beneath access ramp: " + b["asset"]
                    )
                zs.append(z)
            heights.append(max(zs) + 0.008)
        # Small removable access bridge sits above existing steps; original geometry stays intact.
        step = abs(ys[1] - ys[0])
        slope = 0.18
        for i in range(1, len(heights)):
            heights[i] = max(heights[i], heights[i - 1] - slope * step)
        for i in range(len(heights) - 2, -1, -1):
            heights[i] = max(heights[i], heights[i + 1] - slope * step)
        if heights[0] > meta["floor_z"] + 0.20:
            raise RuntimeError(
                "Access ramp would obstruct indoor doorway: " + b["asset"]
            )
        verts = []
        for y, z in zip(ys, heights):
            for x, h in [(-0.36, z), (0.36, z), (-0.36, z - 0.045), (0.36, z - 0.045)]:
                verts.append(tuple(T @ Vector((x, y, h))))
        faces = []
        for i in range(n):
            a = i * 4
            c = (i + 1) * 4
            faces.extend(
                [
                    (a, c, c + 1, a + 1),
                    (a + 2, a + 3, c + 3, c + 2),
                    (a, a + 2, c + 2, c),
                    (a + 1, c + 1, c + 3, a + 3),
                ]
            )
        faces.extend([(0, 1, 3, 2), (n * 4, n * 4 + 2, n * 4 + 3, n * 4 + 1)])
        mesh = bpy.data.meshes.new("Robot task removable access ramp")
        mesh.from_pydata(verts, [], faces)
        mesh.update()
        ob = bpy.data.objects.new("task_access_ramp:" + b["asset"], mesh)
        self.s.collection.objects.link(ob)
        ob.data.materials.append(
            material("Access ramp gray", (0.25, 0.31, 0.34), 0.35, 0.6)
        )
        bpy.context.view_layer.update()
        self.dg = bpy.context.evaluated_depsgraph_get()
        self.cache.clear()
        self.ramps.append(
            dict(
                building=b["asset"],
                object=ob.name,
                width_m=0.72,
                max_slope=slope,
                start_y=inside,
                end_y=end,
                reason="Removable task access ramp over high entry steps; source scene unchanged",
            )
        )
        return end

    def entrance(self, b):
        meta = json.loads(
            (SOURCE / "shared_assets" / (b["asset"] + ".json")).read_text()
        )
        T = Matrix(b["matrix"])
        pts = []
        end = (
            self.access_ramp(b, meta, T)
            if b["asset"] in {"police", "fire", "gas", "delivery"}
            else -6.5
        )
        # Trace the real center of the already-open door, including actual stair heights.
        for j in range(31):
            # Keep the robot and the complete stand clear of the native checkout stanchion.
            inside = (
                0.55
                if b["asset"] == "corner_store"
                else min(1.6, meta["inside_y"] - 0.8)
            )
            y = inside + (end - inside) * j / 30
            v = T @ Vector((0, y, meta["floor_z"]))
            z = self.floor(v.x, v.y, meta["floor_z"])
            if z is None:
                raise RuntimeError("Missing ground at doorway " + b["asset"])
            v.z = z + 0.025
            pts.append(v)
        for a, c in zip(pts, pts[1:]):
            if abs(a.z - c.z) > 0.40:
                raise RuntimeError(
                    f"Doorway step too high for walking: {b['asset']} {a.z-c.z}"
                )
            if not self.segment(a, c, 0.28):
                raise RuntimeError(
                    "Doorway body collision "
                    + b["asset"]
                    + " "
                    + str(list(a))
                    + " -> "
                    + str(list(c))
                )
        return pts


def path_length(points):
    return sum((b - a).length for a, b in zip(points, points[1:]))


def resample(points, spacing=0.18):
    out = [points[0]]
    for a, b in zip(points, points[1:]):
        n = max(1, math.ceil((b - a).length / spacing))
        out.extend(a.lerp(b, j / n) for j in range(1, n + 1))
    return out


def make_timeline(task, planner):
    entry = planner.entrance(task["source_building"])
    home = entry[0]
    outside = entry[-1]
    if task["kind"] == "delivery":
        targetentry = planner.entrance(task["target_building"])
        outpath = planner.astar(outside, targetentry[-1])
        route = entry + outpath[1:] + list(reversed(targetentry))[1:]
        pickup = home
        drop = targetentry[0]
        direction = -(entry[1] - entry[0]).normalized()
        # Service stands sit along the clear center aisle; robot stops 0.56 m short.
        pickup_pos = pickup + direction * 0.56
        drop_dir = -(targetentry[1] - targetentry[0]).normalized()
        drop_pos = drop + drop_dir * 0.56
        actions = [
            ("start", home, home, 1.0, 0),
            ("pickup", home, home, 1.8, 0),
            ("carry_to_destination", route, None, path_length(route) / 2.2, 1),
            ("place", drop, drop, 1.8, 1),
            ("return_home", list(reversed(route)), None, path_length(route) / 2.5, 0),
            ("complete", home, home, 1.2, 0),
        ]
        initial_yaw = heading(direction)
        drop_yaw = heading(drop_dir)
    else:
        # Find a physically clear outdoor pickup approach, away from the doorway.
        pick = None
        route = None
        T = Matrix(task["source_building"]["matrix"])
        for x, y in [
            (3, -10),
            (-3, -10),
            (0, -12),
            (4, -8),
            (-4, -8),
            (0, -9),
            (3, -17),
            (-3, -17),
            (0, -17),
            (3, -15),
            (-3, -15),
            (0, -16),
        ]:
            v = T @ Vector((x, y, 0))
            q = planner.outside(v.x, v.y)
            if q is None:
                continue
            try:
                op = planner.astar(outside, q)
            except RuntimeError as exc:
                log("pickup_candidate_rejected", x, y, str(exc))
                continue
            forward = (q - op[-2]).normalized()
            support = q + forward * 0.56
            if planner.outside(support.x, support.y) is None:
                continue
            pick = q
            route = entry + op[1:]
            break
        if pick is None:
            raise RuntimeError("No clear outdoor pickup station")
        pickup = pick
        drop = home
        pickup_pos = pick + forward * 0.56
        direction = -(entry[1] - entry[0]).normalized()
        drop_pos = home + direction * 0.56
        actions = [
            ("start", home, home, 1.0, 0),
            ("exit_and_approach", route, None, path_length(route) / 1.5, 0),
            ("pickup", pick, pick, 1.8, 0),
            ("carry_home", list(reversed(route)), None, path_length(route) / 1.5, 1),
            ("place", home, home, 1.8, 1),
            ("complete", home, home, 1.2, 0),
        ]
        initial_yaw = heading(entry[1] - entry[0])
        drop_yaw = heading(direction)
    pick_yaw = heading(pickup_pos - pickup)
    rows = []
    t = 0
    last_yaw = initial_yaw
    walk_distance = 0

    # Explicit turn holds keep heading continuous and do not teleport at pickup/return.
    def add(p, yaw, grasp, state, phase=0, action="turn", u=0):
        rows.append(
            dict(
                position=list(p),
                yaw=yaw,
                grasp=grasp,
                object_state=state,
                walk_phase=phase,
                action=action,
                action_progress=u,
            )
        )

    state = "at_pickup"
    grasp = 0
    last_p = home
    for name, a, b, duration, carry in actions:
        moving = isinstance(a, list)
        desired = (
            heading(a[1] - a[0])
            if moving
            else pick_yaw
            if name == "pickup"
            else drop_yaw
            if name == "place"
            else last_yaw
        )
        delta = (desired - last_yaw + math.pi) % (2 * math.pi) - math.pi
        if abs(delta) > 0.04:
            count = max(8, round(abs(delta) * 0.3 * ARGS.fps))
            for j in range(count):
                add(
                    last_p,
                    last_yaw + delta * smooth((j + 1) / count),
                    grasp,
                    state,
                    action="turn",
                )
            last_yaw = desired
        if moving:
            points = resample(a)
            lengths = [0]
            for p, q in zip(points, points[1:]):
                lengths.append(lengths[-1] + (q - p).length)
            count = max(2, round(duration * ARGS.fps))
            ix = 0
            for j in range(count):
                distance = lengths[-1] * (j + 1) / count
                while ix + 1 < len(points) - 1 and lengths[ix + 1] < distance:
                    ix += 1
                f = (distance - lengths[ix]) / max(
                    0.0001, lengths[ix + 1] - lengths[ix]
                )
                pos = points[ix].lerp(points[ix + 1], f)
                desired = heading(points[ix + 1] - points[ix])
                delta = (desired - last_yaw + math.pi) % (2 * math.pi) - math.pi
                last_yaw += max(-0.15, min(0.15, delta))
                walk_distance += lengths[-1] / count
                add(
                    pos,
                    last_yaw,
                    carry,
                    state,
                    walk_distance * 8,
                    name,
                    (j + 1) / count,
                )
            last_p = Vector(points[-1])
            grasp = carry
        else:
            count = max(2, round(duration * ARGS.fps))
            for j in range(count):
                u = (j + 1) / count
                if name == "pickup":
                    grasp = smooth(min(1, u * 1.8))
                    state = "carried" if u >= 0.55 else "at_pickup"
                elif name == "place":
                    grasp = 1 - smooth(max(0, (u - 0.5) * 2))
                    state = "placed" if u >= 0.55 else "carried"
                add(a, last_yaw, grasp, state, action=name, u=u)
            last_p = Vector(a)
    for i, row in enumerate(rows):
        row["frame"] = i + 1
        row["time_s"] = i / ARGS.fps
    return rows, dict(
        pickup=list(pickup_pos),
        drop=list(drop_pos),
        pickup_yaw=pick_yaw,
        drop_yaw=drop_yaw,
        route=[list(p) for p in route],
        length_m=path_length(route) * 2,
        radius_m=0.28,
        ray_tests=planner.tests,
        access_ramps=planner.ramps,
        passed=True,
        scope="Sampled body rays along open door centerlines and A* exterior route; measured ground and stair height. Kinematic animation, not a physics/controller evaluation.",
    )


def object_position(row, audit):
    p = Vector(row["position"])
    yaw = row["yaw"]
    offset = Matrix.Rotation(yaw, 3, "Z") @ Vector((0, 0.385, 0.82))
    held = p + offset
    pickup = Vector(audit["pickup"]) + Vector((0, 0, 0.82))
    drop = Vector(audit["drop"]) + Vector((0, 0, 0.82))
    u = row["action_progress"]
    if row["action"] == "pickup":
        return pickup.lerp(held, smooth(max(0, min(1, (u - 0.35) / 0.4))))
    if row["action"] == "place":
        return held.lerp(drop, smooth(max(0, min(1, (u - 0.2) / 0.4))))
    return (
        held
        if row["object_state"] == "carried"
        else drop
        if row["object_state"] == "placed"
        else pickup
    )


def build(task, d):
    bpy.ops.wm.open_mainfile(filepath=task["source_blend"], load_ui=False)
    s = bpy.context.scene
    planner = Planner(
        s, json.loads((SOURCE / task["scene"] / "scene_manifest.json").read_text())
    )
    log("planning", task["id"])
    rows, audit = make_timeline(task, planner)
    write(d / "path_audit.json", audit)
    log("route_ready", len(rows), audit["length_m"], audit["ray_tests"])
    # Compute camera clearance before adding animated objects, avoiding per-frame scene rebuilds.
    for row in rows:
        p = Vector(row["position"])
        yaw = row["yaw"]
        forward = Vector((-math.sin(yaw), math.cos(yaw), 0))
        side = Vector((math.cos(yaw), math.sin(yaw), 0))
        focus = p + Vector((0, 0, 0.90))
        offset = forward * 2.5 + side * 0.90 + Vector((0, 0, 0.90))
        hit, loc, *_ = planner.ray(focus, offset.normalized(), offset.length)
        distance = (
            min(offset.length, (loc - focus).length - 0.20) if hit else offset.length
        )
        if distance < 1.35:
            offset = -forward * 2.35 + Vector((0, 0, 0.95))
            hit, loc, *_ = planner.ray(focus, offset.normalized(), offset.length)
            distance = (
                min(offset.length, (loc - focus).length - 0.20)
                if hit
                else offset.length
            )
        row["third_camera"] = list(focus + offset.normalized() * max(0.75, distance))
    log("camera_clearance_ready")
    assembly = bpy.data.scenes.new("robot1:Assembly")
    bpy.context.window.scene = assembly
    robot = Robot()
    for ob in list(assembly.objects):
        s.collection.objects.link(ob)
    bpy.context.window.scene = s
    bpy.data.scenes.remove(assembly)
    orange = material("Cargo orange", (0.92, 0.27, 0.035), 0.12, 0.3)
    paper = material("Label", (0.86, 0.92, 0.94), 0, 0.6)
    steel = material("Service stand", (0.13, 0.22, 0.28), 0.6, 0.32)
    prop = box("TASK_OBJECT", (0, 0, 0), (0.29, 0.235, 0.21), orange, bevel=0.025)
    label = box("Cargo label", (0, 0.119, 0), (0.15, 0.006, 0.07), paper, prop, 0.004)
    for name, point in [("Pickup", audit["pickup"]), ("Drop", audit["drop"])]:
        p = Vector(point)
        box(
            name + " table top",
            p + Vector((0, 0, 0.685)),
            (0.48, 0.40, 0.045),
            steel,
            bevel=0.016,
        )
        box(
            name + " table stem",
            p + Vector((0, 0, 0.36)),
            (0.07, 0.07, 0.63),
            steel,
            bevel=0.012,
        )
        box(
            name + " table foot",
            p + Vector((0, 0, 0.045)),
            (0.36, 0.30, 0.06),
            steel,
            bevel=0.012,
        )
    fp = camera("robot1:First person")
    tp = camera("robot1:Third person")
    # Fill travels with the camera/robot: soft unobtrusive bounce for indoor clarity.
    ld = bpy.data.lights.new("robot1:Soft camera bounce", "AREA")
    ld.energy = 65
    ld.shape = "DISK"
    ld.size = 2.5
    fill = bpy.data.objects.new("robot1:Soft camera bounce", ld)
    s.collection.objects.link(fill)
    eye_pitch = 0.10
    for row in rows:
        frame = row["frame"]
        if frame % 120 == 0:
            log("baking", frame, len(rows))
        p = Vector(row["position"])
        yaw = row["yaw"]
        forward = Vector((-math.sin(yaw), math.cos(yaw), 0))
        side = Vector((math.cos(yaw), math.sin(yaw), 0))
        objpos = object_position(row, audit)
        local = Matrix.Rotation(-yaw, 3, "Z") @ (objpos - p)
        robot.pose(p, yaw, row["walk_phase"], row["grasp"], local.y, local.z)
        robot.keyframe(frame)
        prop.location = object_position(row, audit)
        prop.rotation_euler.z = (
            yaw
            if row["object_state"] == "carried"
            else audit["drop_yaw"]
            if row["object_state"] == "placed"
            else audit["pickup_yaw"]
        )
        prop.keyframe_insert(data_path="location", frame=frame)
        prop.keyframe_insert(data_path="rotation_euler", frame=frame)
        # First-person optics look down slightly while manipulating, then level for navigation.
        target_pitch = 1.335 if row["action"] in {"pickup", "place"} else 0.10
        eye_pitch += max(-0.05, min(0.05, target_pitch - eye_pitch))
        eye = p + forward * 0.255 + Vector((0, 0, 1.36))
        aim(
            fp,
            eye,
            eye
            + forward * math.cos(eye_pitch) * 3
            - Vector((0, 0, math.sin(eye_pitch) * 3)),
            22,
        )
        focus = p + Vector((0, 0, 0.90))
        aim(tp, row["third_camera"], focus, 21)
        for cam in [fp, tp]:
            cam.keyframe_insert(data_path="location", frame=frame)
            cam.keyframe_insert(data_path="rotation_euler", frame=frame)
        fill.location = p + Vector((0, 0, 2.3))
        fill.keyframe_insert(data_path="location", frame=frame)
    for action in bpy.data.actions:
        # Modern layered actions retain Bezier at dense integer frames; renders sample exactly these frames.
        pass
    s.frame_start = 1
    s.frame_end = len(rows)
    s.render.fps = ARGS.fps
    s.camera = tp
    s["robot1_task"] = task["title"]
    s["robot1_source"] = task["source_blend"]
    s["robot1_reference"] = str(ROOT / "robot.png")
    for lib in bpy.data.libraries:
        lib.filepath = bpy.path.abspath(lib.filepath)
    for im in bpy.data.images:
        if im.source == "FILE" and im.filepath and not im.library:
            im.filepath = bpy.path.abspath(im.filepath)
    write(d / "trajectory.json", dict(fps=ARGS.fps, frames=rows))
    checks = []
    for index in sorted(
        set([0, len(rows) - 1, *range(0, len(rows), max(1, len(rows) // 12))])
    ):
        row = rows[index]
        s.frame_set(row["frame"])
        actual = robot.root.location.copy()
        expected = Vector(row["position"])
        error = (actual - expected).length
        if error > 0.001:
            raise RuntimeError(
                f"Evaluated robot animation differs from trajectory at {index}: {error}"
            )
        pe = (prop.location - object_position(row, audit)).length
        if pe > 0.001:
            raise RuntimeError(f"Evaluated cargo differs at {index}: {pe}")
        checks.append(
            dict(
                frame=row["frame"],
                robot_position_error_m=error,
                cargo_position_error_m=pe,
            )
        )
    write(d / "animation_audit.json", dict(passed=True, checks=checks, revision=3))
    s.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(d / "animation.blend"), compress=True)
    if (d / "error.json").exists():
        (d / "error.json").unlink()
    task.update(
        status="built",
        animation_revision=3,
        frames=len(rows),
        fps=ARGS.fps,
        duration_seconds=len(rows) / ARGS.fps,
    )
    write(d / "task.json", task)
    return s, rows


def configure(s, width, samples):
    s.render.engine = ARGS.engine
    if ARGS.engine == "CYCLES" and not ARGS.cpu:
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        devices = []
        for dev in prefs.devices:
            dev.use = dev.type == "OPTIX"
            if dev.use:
                devices.append(dev.name)
        if not devices:
            raise RuntimeError("No OptiX GPU available")
        s.cycles.device = "GPU"
        s.cycles.samples = samples
        s.cycles.use_denoising = True
        s.cycles.denoising_use_gpu = True
        s.cycles.use_adaptive_sampling = True
        s.cycles.adaptive_threshold = 0.08
        s.cycles.max_bounces = 5
        s.cycles.diffuse_bounces = 3
        s.cycles.glossy_bounces = 3
        s.cycles.transmission_bounces = 4
        s.render.use_persistent_data = True
    elif ARGS.engine == "CYCLES":
        s.cycles.device = "CPU"
        s.cycles.samples = samples
        s.cycles.use_denoising = True
        s.cycles.denoising_use_gpu = False
        s.cycles.use_adaptive_sampling = True
        s.cycles.adaptive_threshold = 0.08
        s.cycles.max_bounces = 5
        s.cycles.diffuse_bounces = 3
        s.cycles.glossy_bounces = 3
        s.cycles.transmission_bounces = 4
        s.render.use_persistent_data = True
    elif hasattr(s, "eevee"):
        s.eevee.taa_render_samples = samples
    s.render.resolution_x = width
    s.render.resolution_y = width * 9 // 16
    s.render.resolution_percentage = 100
    s.render.image_settings.file_format = "PNG"
    s.render.image_settings.color_mode = "RGB"
    s.render.image_settings.compression = 15
    s.render.film_transparent = False


def visibility(view):
    for o in bpy.data.objects:
        if (
            o.name.startswith("robot1:")
            and o.type in {"MESH", "CURVE"}
            and not any(
                x in o.name
                for x in ["TASK_OBJECT", "Cargo label", " table ", "Forearm", "Palm"]
            )
        ):
            o.hide_render = view == "first_person"


def render_png(s, destination):
    # Stage on local temporary storage, validate, then atomically publish each frame.
    local = Path("/tmp") / f"robot1_render_{os.getpid()}.png"
    s.render.filepath = str(local)
    bpy.ops.render.render(write_still=True)
    if not png_valid(local):
        raise RuntimeError("Invalid freshly rendered PNG: " + str(destination))
    destination = Path(destination)
    temp = destination.with_suffix(f".{os.getpid()}.tmp")
    for _ in range(3):
        with local.open("rb") as src, temp.open("wb") as dst:
            shutil.copyfileobj(src, dst)
            dst.flush()
            os.fsync(dst.fileno())
        if png_valid(temp):
            temp.replace(destination)
            local.unlink()
            return
    raise RuntimeError("PNG copy verification failed: " + str(destination))


def video_camera(s, rows, task, d):
    name = "robot1:Third person video"
    if name in bpy.data.objects and s.get("robot1_video_camera_revision") == 1:
        return bpy.data.objects[name]
    cam = camera(name)
    positions = stable_positions(rows)
    records = []
    for row, p in zip(rows, positions):
        target = Vector(row["position"]) + Vector((0, 0, 0.9))
        aim(cam, p, target, 21)
        cam.keyframe_insert(data_path="location", frame=row["frame"])
        cam.keyframe_insert(data_path="rotation_euler", frame=row["frame"])
        records.append(
            dict(
                frame=row["frame"],
                position=p,
                target=list(target),
                action=row["action"],
            )
        )
    cuts = [
        records[i]["frame"]
        for i in range(1, len(records))
        if (Vector(positions[i]) - Vector(positions[i - 1])).length > 2
    ]
    write(
        d / "third_person_video_camera.json",
        dict(
            revision=1,
            mode="Observer holds position during in-place turns; phase-boundary shot cuts; short avoidance flicker suppressed",
            intentional_cut_frames=cuts,
            frames=records,
        ),
    )
    s["robot1_video_camera_revision"] = 1
    s.camera = cam
    s.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(d / "animation.blend"), compress=True)
    task["video_camera_revision"] = 1
    write(d / "task.json", task)
    return cam


def render(s, rows, task, d):
    if (
        ARGS.mode == "video"
        and sum(png_valid(p) for p in (d / "images").glob("*.png")) < 12
    ):
        ARGS.mode = "images"
        render(s, rows, task, d)
        ARGS.mode = "video"
    if ARGS.mode == "all":
        ARGS.mode = "images"
        render(s, rows, task, d)
        ARGS.mode = "all"
    image_dir = d / "images"
    image_dir.mkdir(exist_ok=True)
    frames_dir = d / "frames"
    frames_dir.mkdir(exist_ok=True)
    selected = []
    for action in [
        "start",
        "pickup",
        "exit_and_approach",
        "carry_to_destination",
        "carry_home",
        "place",
        "return_home",
        "complete",
    ]:
        r = [v for v in rows if v["action"] == action]
        if r:
            selected.append(
                (
                    action,
                    r[
                        int(
                            (len(r) - 1)
                            * (0.8 if action in ["pickup", "place"] else 0.5)
                        )
                    ]["frame"],
                )
            )
    if ARGS.mode == "preview" and not ARGS.actions:
        selected = [
            (
                "pickup",
                next(
                    r["frame"]
                    for r in rows
                    if r["action"] == "pickup" and r["action_progress"] > 0.8
                ),
            ),
            ("outdoor", min(rows, key=lambda r: abs(r["position"][1] + 5))["frame"]),
        ]
    if ARGS.actions:
        selected = [item for item in selected if item[0] in ARGS.actions.split(",")]
    views = ARGS.views.split(",")
    for view in views:
        s.camera = bpy.data.objects[
            "robot1:" + ("First person" if view == "first_person" else "Third person")
        ]
        visibility(view)
        if ARGS.mode in {"all", "images", "preview"}:
            configure(s, ARGS.width, ARGS.samples)
            for action, frame in selected:
                target = (
                    d / ARGS.preview_subdir if ARGS.mode == "preview" else image_dir
                ) / (view + "_" + action + ".png")
                target.parent.mkdir(exist_ok=True)
                if png_complete(target) and not ARGS.rebuild:
                    continue
                s.frame_set(frame)
                start = time.monotonic()
                render_png(s, target)
                log("image", str(target), round(time.monotonic() - start, 2))
        if ARGS.mode in {"all", "video"}:
            target = d / (view + ".mp4")
            if target.exists():
                continue
            if view == "third_person":
                s.camera = video_camera(s, rows, task, d)
            configure(s, ARGS.video_width, ARGS.video_samples)
            fd = frames_dir / view
            fd.mkdir(exist_ok=True)
            for row in rows:
                f = row["frame"]
                dest = fd / f"{f:05d}.png"
                if f < ARGS.frame_start or (
                    ARGS.frame_end is not None and f > ARGS.frame_end
                ):
                    continue
                if png_valid(dest):
                    continue
                s.frame_set(f)
                render_png(s, dest)
                progress_file = (
                    "render_progress"
                    + ("_" + ARGS.progress_id if ARGS.progress_id else "")
                    + ".json"
                )
                write(
                    d / progress_file,
                    dict(
                        view=view,
                        frame=f,
                        total=len(rows),
                        updated=time.time(),
                        status="rendering",
                    ),
                )
            if ARGS.frames_only:
                continue
            temp = Path("/tmp") / f"robot1_video_{os.getpid()}_{view}.mp4"
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-xerror",
                    "-y",
                    "-threads",
                    "2",
                    "-framerate",
                    str(ARGS.fps),
                    "-start_number",
                    "1",
                    "-i",
                    str(fd / "%05d.png"),
                    "-frames:v",
                    str(len(rows)),
                    "-c:v",
                    "libx264",
                    "-threads",
                    "2",
                    "-preset",
                    "fast",
                    "-crf",
                    "19",
                    "-pix_fmt",
                    "yuv420p",
                    "-movflags",
                    "+faststart",
                    str(temp),
                ],
                check=True,
            )
            subprocess.run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-xerror",
                    "-threads",
                    "2",
                    "-i",
                    str(temp),
                    "-f",
                    "null",
                    "-",
                ],
                check=True,
            )
            probe = json.loads(
                subprocess.check_output(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-select_streams",
                        "v:0",
                        "-show_entries",
                        "stream=nb_frames",
                        "-of",
                        "json",
                        str(temp),
                    ],
                    text=True,
                )
            )
            if int(probe["streams"][0]["nb_frames"]) != len(rows):
                raise RuntimeError("Encoded video frame count differs from trajectory")
            publish = d / (view + ".partial.mp4")
            with temp.open("rb") as src, publish.open("wb") as dst:
                shutil.copyfileobj(src, dst)
                dst.flush()
                os.fsync(dst.fileno())
            with temp.open("rb") as src, publish.open("rb") as dst:
                if (
                    hashlib.file_digest(src, "sha256").digest()
                    != hashlib.file_digest(dst, "sha256").digest()
                ):
                    raise RuntimeError("MP4 copy checksum mismatch")
            publish.replace(target)
            temp.unlink()
            # Retain all rendered frames: resumability and transparent review.
            log("video", str(target))
    if (
        all((d / (v + ".mp4")).exists() for v in ["first_person", "third_person"])
        and len(list(image_dir.glob("*.png"))) >= 12
    ):
        task["status"] = "rendered_pending_review"
        write(d / "task.json", task)
        if (d / "error.json").exists():
            (d / "error.json").unlink()
    if not ARGS.frames_only:
        write(
            d / "render_settings.json",
            dict(
                engine=ARGS.engine,
                device="CPU" if ARGS.cpu else "GPU",
                width=ARGS.width,
                samples=ARGS.samples,
                video_width=ARGS.video_width,
                video_samples=ARGS.video_samples,
                fps=ARGS.fps,
                views=views,
                mode=ARGS.mode,
            ),
        )


p = argparse.ArgumentParser()
p.add_argument("--scene", required=True)
p.add_argument("--kind", choices=["delivery", "fetch"], required=True)
p.add_argument(
    "--mode", choices=["build", "preview", "images", "video", "all"], default="all"
)
p.add_argument("--engine", default="CYCLES", choices=["CYCLES", "BLENDER_EEVEE"])
p.add_argument("--fps", type=int, default=24)
p.add_argument("--width", type=int, default=1280)
p.add_argument("--samples", type=int, default=32)
p.add_argument("--video-width", type=int, default=960)
p.add_argument("--video-samples", type=int, default=12)
p.add_argument("--views", default="third_person,first_person")
p.add_argument("--rebuild", action="store_true")
p.add_argument("--preview-subdir", default="previews")
p.add_argument("--cpu", action="store_true")
p.add_argument("--actions", default="")
p.add_argument("--frame-start", type=int, default=1)
p.add_argument("--frame-end", type=int)
p.add_argument("--frames-only", action="store_true")
p.add_argument("--progress-id", default="")
ARGS = p.parse_args(sys.argv[sys.argv.index("--") + 1 :])
d = OUT / ARGS.scene / ARGS.kind
task = json.loads((d / "task.json").read_text())
try:
    if (
        not (d / "animation.blend").exists()
        or task.get("animation_revision") != 3
        or ARGS.rebuild
    ):
        s, rows = build(task, d)
    else:
        bpy.ops.wm.open_mainfile(filepath=str(d / "animation.blend"), load_ui=False)
        s = bpy.context.scene
        trajectory = json.loads((d / "trajectory.json").read_text())
        rows = trajectory["frames"]
        ARGS.fps = trajectory["fps"]
    if ARGS.mode != "build":
        render(s, rows, task, d)
except Exception as e:
    write(d / "error.json", dict(error=str(e), mode=ARGS.mode, time=time.time()))
    raise

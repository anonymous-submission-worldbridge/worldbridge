"""Select an unobstructed elevated pharmacy shot without changing task motion."""
import bpy, sys, json, shutil
from pathlib import Path
from mathutils import Vector, Matrix

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from robot1_tasks import OUT, SOURCE, write

for task in json.loads((OUT / "task_catalogue.json").read_text())["tasks"]:
    buildings = [
        b
        for b in [task["source_building"], task["target_building"]]
        if b and b["asset"] == "pharmacy"
    ]
    if not buildings:
        continue
    d = OUT / task["scene"] / task["kind"]
    bpy.ops.wm.open_mainfile(filepath=str(d / "animation.blend"), load_ui=False)
    s = bpy.context.scene
    trajectory = json.loads((d / "trajectory.json").read_text())
    rows = trajectory["frames"]
    camera = bpy.data.objects["robot1:Third person"]
    hidden = []
    for o in bpy.data.objects:
        if (
            o.name.startswith("robot1:")
            and o.type in {"MESH", "CURVE"}
            and " table " not in o.name
        ):
            hidden.append((o, o.hide_viewport))
            o.hide_viewport = True
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    changed = set()
    report = []
    for b in buildings:
        T = Matrix(b["matrix"])
        inv = T.inverted()
        floor = 0.08
        targets = [
            T @ Vector((x, y, floor + z))
            for x, y, z in [
                (0, 1, 1.3),
                (0, 1, 0.9),
                (-0.2, 1, 0.9),
                (0.2, 1, 0.9),
                (0, 1.56, 0.845),
                (0, 1.385, 0.845),
            ]
        ]
        selected = None
        failures = []
        for local in [
            (-0.8, 2.6, 2.3),
            (0, 2.9, 2.65),
            (-0.5, 2.8, 2.55),
            (1.7, 2.6, 2.7),
            (2.5, 2.8, 2.7),
            (0, 2.3, 2.65),
        ]:
            pos = T @ Vector(local)
            hits = []
            for target in targets:
                direction = target - pos
                hit, loc, n, i, ob, mat = s.ray_cast(
                    dg, pos, direction.normalized(), distance=direction.length - 0.04
                )
                if hit:
                    hits.append(ob.name)
            if not hits:
                selected = pos
                break
            failures.append(dict(candidate=local, occluders=hits))
        if selected is None:
            raise RuntimeError(
                "No unobstructed pharmacy camera " + json.dumps(failures)
            )
        print("CAMERA_FIX", task["id"], list(selected), flush=True)
        for row in rows:
            p = Vector(row["position"])
            q = inv @ p
            if abs(q.x) < 0.72 and 0.25 <= q.y <= 1.85:
                row["third_camera"] = list(selected)
                camera.location = selected
                camera.rotation_euler = (
                    (p + Vector((0, 0, 0.9)) - selected)
                    .to_track_quat("-Z", "Y")
                    .to_euler()
                )
                camera.keyframe_insert(data_path="location", frame=row["frame"])
                camera.keyframe_insert(data_path="rotation_euler", frame=row["frame"])
                changed.add(row["frame"])
        report.append(
            dict(
                building="pharmacy",
                camera=list(selected),
                clearance_targets=[list(v) for v in targets],
                failed_candidates=failures,
            )
        )
    for o, value in hidden:
        o.hide_viewport = value
    s.frame_set(1)
    s["robot1_pharmacy_camera_revision"] = 1
    bpy.ops.wm.save_as_mainfile(filepath=str(d / "animation.blend"), compress=True)
    write(d / "trajectory.json", trajectory)
    write(
        d / "camera_occlusion_review.json",
        dict(passed=True, revision=1, changes=report, changed_frames=len(changed)),
    )
    archive = OUT / "logs/diagnostic_archive" / task["id"]
    archive.mkdir(parents=True, exist_ok=True)
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
        rr = [r for r in rows if r["action"] == action]
        if not rr:
            continue
        frame = rr[
            int((len(rr) - 1) * (0.8 if action in ["pickup", "place"] else 0.5))
        ]["frame"]
        png = d / "images" / ("third_person_" + action + ".png")
        if frame in changed and png.exists():
            shutil.move(str(png), str(archive / png.name))

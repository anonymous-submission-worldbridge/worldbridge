"""Validate task completion semantics and continuous robot trajectories from disk."""
import json, math
from robot1_tasks import OUT, write

reports = []
for t in json.loads((OUT / "task_catalogue.json").read_text())["tasks"]:
    d = OUT / t["scene"] / t["kind"]
    task = json.loads((d / "task.json").read_text())
    errors = []
    if task.get("animation_revision") != 3:
        reports.append(dict(task=t["id"], passed=False, status="not_built"))
        continue
    trajectory = json.loads((d / "trajectory.json").read_text())
    rows = trajectory["frames"]
    fps = trajectory["fps"]
    states = []
    for r in rows:
        if not states or states[-1] != r["object_state"]:
            states.append(r["object_state"])
    home_error = math.dist(rows[0]["position"], rows[-1]["position"])
    max_step = max(
        math.dist(a["position"], b["position"]) for a, b in zip(rows, rows[1:])
    )
    if home_error > 0.001:
        errors.append("Robot did not return to its starting position")
    if states != ["at_pickup", "carried", "placed"]:
        errors.append("Object state order is invalid")
    if [r["frame"] for r in rows] != list(range(1, len(rows) + 1)):
        errors.append("Missing or duplicate trajectory frames")
    if max_step * fps > 2.6:
        errors.append("Robot exceeds the designed 2.5 m/s travel speed")
    if rows[-1]["action"] != "complete" or rows[-1]["grasp"] != 0:
        errors.append("Invalid completion pose")
    if not json.loads((d / "animation_audit.json").read_text()).get("passed"):
        errors.append("Evaluated Blender animation audit failed")
    if not json.loads((d / "path_audit.json").read_text()).get("passed"):
        errors.append("Sampled path audit failed")
    reports.append(
        dict(
            task=t["id"],
            passed=not errors,
            errors=errors,
            frames=len(rows),
            seconds=len(rows) / fps,
            return_error_m=home_error,
            max_speed_m_s=max_step * fps,
            object_state_sequence=states,
        )
    )
write(
    OUT / "task_logic_verification.json",
    dict(
        passed_tasks=sum(r["passed"] for r in reports),
        total_tasks=len(reports),
        all_passed=all(r["passed"] for r in reports),
        tasks=reports,
    ),
)
print(
    json.dumps(
        dict(
            passed=sum(r["passed"] for r in reports),
            total=len(reports),
            failures=[r for r in reports if not r["passed"]],
        ),
        ensure_ascii=False,
    )
)

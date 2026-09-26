"""Stable third-person video shots: hold the observer through in-place turns.
Short front/back avoidance flicker is removed within each motion phase. Deliberate
shot changes at phase boundaries remain; the camera never blends through the robot.
"""
import math


def stable_positions(rows):
    raw = [list(r["third_camera"]) for r in rows]
    result = [p[:] for p in raw]

    def side(i):
        r = rows[i]
        q = raw[i]
        p = r["position"]
        return (q[0] - p[0]) * (-math.sin(r["yaw"])) + (q[1] - p[1]) * math.cos(
            r["yaw"]
        ) >= 0

    for i, r in enumerate(rows):
        if r["action"] == "turn" and i:
            result[i] = result[i - 1][:]
            continue
        group = [
            j
            for j in range(max(0, i - 3), min(len(rows), i + 4))
            if rows[j]["action"] == r["action"]
        ]
        if not group:
            continue
        majority = sum(side(j) for j in group) > len(group) / 2
        if side(i) != majority:
            same = [j for j in group if side(j) == majority]
            if same:
                j = min(same, key=lambda j: abs(j - i))
                p = r["position"]
                other = rows[j]["position"]
                result[i] = [raw[j][k] + p[k] - other[k] for k in range(3)]
    return result

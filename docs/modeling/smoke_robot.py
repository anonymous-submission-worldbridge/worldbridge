"""Exercise recovered robot geometry in memory without exporting model files."""
import json
from pathlib import Path
import sys
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from robot1_model import Robot

bpy.ops.wm.read_factory_settings(use_empty=True)
robot = Robot()
assert len(robot.arms) == len(robot.legs) == 2
robot.pose((1, 2, 0), 0.5, 0.7, 1)
robot.keyframe(1)
robot.pose((2, 3, 0), 1.0, 1.2, 0)
robot.keyframe(12)
meshes = [o for o in bpy.data.objects if o.type == "MESH"]
assert len(meshes) > 20
assert all(len(o.data.vertices) > 0 for o in meshes)
assert robot.root.animation_data and robot.root.animation_data.action
result = {
    "passed": True,
    "blender_version": bpy.app.version_string,
    "objects": len(bpy.data.objects),
    "meshes": len(meshes),
    "arms": len(robot.arms),
    "legs": len(robot.legs),
    "keyframed_poses": 2,
    "model_files_written": 0,
}
(ROOT / "docs/modeling/robot_smoke.json").write_text(
    json.dumps(result, indent=2) + "\n"
)
print(json.dumps(result))

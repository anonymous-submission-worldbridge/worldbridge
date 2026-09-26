"""Read saved models to verify embedded cameras and portable dependencies."""
import bpy, json
from pathlib import Path

O = (
    Path(__file__).resolve().parents[1]
    / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect2"
)
report = {"scenes": [], "external_dependencies": [], "errors": []}
for key in ["restaurant", "cafe", "market", "hospital", "pharmacy", "library"]:
    bpy.ops.wm.open_mainfile(filepath=str(O / key / "scene.blend"), load_ui=False)
    still = bpy.data.collections.get("Photographs_24_views")
    video = bpy.data.collections.get("Walkthroughs_4_animated_cameras")
    n = len(still.objects) if still else 0
    v = len(video.objects) if video else 0
    if n != 24 or v != 4:
        report["errors"].append(key + ": camera count mismatch")
    animation = []
    if video:
        for camera in video.objects:
            action = camera.animation_data.action if camera.animation_data else None
            span = list(action.frame_range) if action else []
            animation.append({"camera": camera.name, "frame_range": span})
            if span != [1.0, 144.0]:
                report["errors"].append(key + ": incomplete animation " + camera.name)
    files = []
    for lib in bpy.data.libraries:
        files.append(Path(bpy.path.abspath(lib.filepath)).resolve())
    for im in bpy.data.images:
        if im.source == "FILE" and not im.packed_file and im.filepath:
            files.append(
                Path(bpy.path.abspath(im.filepath, library=im.library)).resolve()
            )
    for p in files:
        if not p.exists():
            report["errors"].append(key + ": missing " + str(p))
        if not p.is_relative_to(O.resolve()):
            report["external_dependencies"].append({"scene": key, "file": str(p)})
    report["scenes"].append(
        {
            "scene": key,
            "still_cameras": n,
            "animated_cameras": v,
            "animations": animation,
            "dependencies": [
                str(p.relative_to(O.resolve()))
                if p.is_relative_to(O.resolve())
                else str(p)
                for p in files
            ],
        }
    )
report["passed"] = not report["errors"] and not report["external_dependencies"]
(O / "portability_verification.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2)
)
print("PORTABILITY", json.dumps(report), flush=True)

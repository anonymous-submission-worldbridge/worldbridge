"""Apply validated v2-only water/camera refinements without rebuilding static assets."""
import json
import sys
from pathlib import Path
import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_urban_v1_full_13_dynamic2 as d


def main():
    path = Path(bpy.data.filepath)
    if path.parent.name != "urban_v1_full_13-dynamic2":
        raise RuntimeError("Only dynamic2 output is writable here")
    report = json.loads((path.parent / "dynamic2_manifest.json").read_text())
    scene = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
    scene.use_nodes = False
    camera = bpy.data.objects[report["shots"][0]["camera"]]
    camera.location = (301.0, -30.0, 34.0)
    d.old.look_at(camera, Vector((272.5, 0.0, 0.0)))
    camera.data.lens = 38.0
    report["shots"][0].update(
        position=list(camera.location), target=[272.5, 0.0, 0.0], lens=38.0
    )
    cache = {}
    drops = []
    for o in list(bpy.data.objects):
        if not o.name.startswith("DYN2::"):
            continue
        semantic = o.get("urban_semantic")
        if semantic not in ("fountain-water", "lake-water"):
            continue
        if "procedural_lake_water_volume" in o.name:
            continue
        for slot in o.material_slots:
            if slot.material and slot.material.name.startswith("DYN2::"):
                original = bpy.data.materials.get(slot.material.name[len("DYN2::") :])
                if original:
                    slot.material = original
        top = (
            d.UPPER_WATER + 0.018
            if "upper_spill" in o.name
            else d.LOWER_WATER + 0.018
            if "lower_spill" in o.name
            else None
        )
        d.advect_material(o, (0, 0, 0.8), cache, gravity_top=top)
        if o.type != "MESH":
            continue
        for modifier in list(o.modifiers):
            if modifier.name.startswith("DYN2_Gravity"):
                o.modifiers.remove(modifier)
        for attr in list(o.data.attributes):
            if attr.name.startswith("dyn2_") and o.data.library is None:
                o.data.attributes.remove(attr)
        result = (
            d.fountain_drops(o) if semantic == "fountain-water" else d.lake_drops(o)
        )
        if result:
            drops.append(result)
    report["droplets"] = drops
    report[
        "water_refinement"
    ] = "Gravity travel-time material coordinates on spills; native lake fountain droplets animated; exact authored bowl levels"
    d.bpy.data.libraries.write(
        str(path), {scene}, path_remap="ABSOLUTE", fake_user=True
    )
    report["output_blend_sha256"] = d.old.sha256(path)
    (path.parent / "dynamic2_manifest.json").write_text(json.dumps(report, indent=2))
    print("DYNAMIC2 REFINEMENT PASS", flush=True)


if __name__ == "__main__":
    main()

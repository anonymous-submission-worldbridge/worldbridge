"""Factor only dynamic2 render-pack foliage after proving native geometry equality."""
import hashlib, json, os, sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dynamic2_native_leaf_instances as native
from build_urban_v1_full_13_dynamic import sha256

path = Path(bpy.data.filepath)
if (
    path.parent.name != "render_packs"
    or path.parent.parent.name != "urban_v1_full_13-dynamic2"
):
    raise RuntimeError("Only dynamic2 render packs may be factored")
proof_path = path.with_suffix(".native_leaf_proof.json")
if proof_path.exists() and json.loads(proof_path.read_text()).get(
    "output_pack_sha256"
) == sha256(path):
    print("DYNAMIC2 NATIVE INSTANCES ALREADY VERIFIED", path, flush=True)
else:
    scene = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
    candidates = [
        o
        for o in bpy.data.objects
        if o.name.startswith("DYN2::")
        and o.get("c2w_genuine_leaffactory_mesh")
        and any(m.name == "DYN2_LocalFoliageBreeze" for m in o.modifiers)
    ]
    proofs = []
    for obj in candidates:
        print("DYNAMIC2 FACTOR", obj.name, flush=True)
        proofs.append(native.install(obj))
        print("DYNAMIC2 FACTOR VERIFIED", proofs[-1], flush=True)
    if not proofs:
        raise RuntimeError("No native canopy found; refusing a vacuous optimization")
    temporary = path.with_suffix(".native.writing.blend")
    bpy.data.libraries.write(
        str(temporary), {scene}, path_remap="ABSOLUTE", fake_user=True
    )
    result = {
        "status": "PASS",
        "input_pack_sha256": sha256(path),
        "output_pack_sha256": sha256(temporary),
        "factor_code_sha256": sha256(Path(native.__file__)),
        "proofs": proofs,
        "geometry_policy": "all source vertices/polygons/leaves preserved at rest within float32 roundoff; zero decimation; native leaf instances rotate about fixed native-vertex pivots",
    }
    os.replace(temporary, path)
    proof_path.write_text(json.dumps(result, indent=2))
    print("DYNAMIC2 FACTOR PACK PASS", path, flush=True)

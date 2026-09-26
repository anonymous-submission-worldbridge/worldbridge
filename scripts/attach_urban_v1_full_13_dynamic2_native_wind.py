"""Attach verified, exact native leaf instances to the complete dynamic2 master.

The render packs remain immutable; the master links their proven geometry and
node groups, keeping the full 82-placement scene and the rendered wind identical.
"""
import ast
import json
import os
import sys
from pathlib import Path
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_urban_v1_full_13_dynamic import sha256

path = Path(bpy.data.filepath)
if path.parent.name != "urban_v1_full_13-dynamic2":
    raise RuntimeError("Only the dynamic2 master may be updated")
manifest_path = path.parent / "dynamic2_manifest.json"
report = json.loads(manifest_path.read_text())
if report["output_blend_sha256"] != sha256(path):
    raise RuntimeError("Master differs from its manifest")
if report["wind"].get("representation") == "exact_native_leaf_instances":
    print("DYNAMIC2 MASTER NATIVE WIND ALREADY ATTACHED", flush=True)
else:
    local = {
        c["object"]: bpy.data.objects[c["object"]] for c in report["wind"]["canopies"]
    }
    metadata = {c["object"]: c for c in report["wind"]["canopies"]}
    attached = set()
    dependencies = []
    for shot in ("river_and_wind", "lake_and_wind"):
        pack = path.parent / "render_packs" / (shot + ".blend")
        proof = json.loads(pack.with_suffix(".native_leaf_proof.json").read_text())
        digest = sha256(pack)
        if proof["status"] != "PASS" or proof["output_pack_sha256"] != digest:
            raise RuntimeError("Unverified native leaf pack: " + str(pack))
        expected = {p["source_mesh"]: p for p in proof["proofs"]}
        # Exact names are retained in each per-shot pack, including lake .001.
        with bpy.data.libraries.load(str(pack), link=True) as (available, loaded):
            loaded.objects = [n for n in available.objects if n in local]
        for source in loaded.objects:
            if source is None or not source.get("dynamic2_native_instance_proof"):
                raise RuntimeError("Missing native instance proof")
            p = ast.literal_eval(source["dynamic2_native_instance_proof"])
            if p != expected[p["source_mesh"]]:
                raise RuntimeError("Object proof differs from verified pack")
            name = source.name
            if name in attached:
                raise RuntimeError("Duplicate canopy dependency: " + name)
            target = local[name]
            native = next(
                m
                for m in source.modifiers
                if m.name == "DYN2_NativeLeafInstances_Breeze"
            )
            target.data = source.data
            for modifier in list(target.modifiers):
                target.modifiers.remove(modifier)
            modifier = target.modifiers.new("DYN2_NativeLeafInstances_Breeze", "NODES")
            modifier.node_group = native.node_group
            target["dynamic2_native_instance_proof"] = source[
                "dynamic2_native_instance_proof"
            ]
            metadata[name].pop("max_component_offset_m", None)
            metadata[name]["native_instance_proof"] = p
            attached.add(name)
        dependencies.append({"path": str(pack), "sha256": digest})
    if attached != set(local):
        raise RuntimeError("Not all ten native canopies were attached")
    scene = next(s for s in bpy.data.scenes if s.get("dynamic2_manifest"))
    report["wind"]["representation"] = "exact_native_leaf_instances"
    report["wind"]["dependencies"] = dependencies
    report["wind"][
        "motion"
    ] = "Independent local leaf rotations about fixed native-vertex pivots; static trunks and object transforms"
    previous_sha = report["output_blend_sha256"]
    temporary = path.with_suffix(".native_wind.writing.blend")
    print("DYNAMIC2 MASTER NATIVE WIND saving", flush=True)
    bpy.data.libraries.write(
        str(temporary), {scene}, path_remap="ABSOLUTE", fake_user=True
    )
    os.replace(temporary, path)
    report["output_blend_sha256"] = sha256(path)
    report["native_wind_attachment"] = {
        "previous_master_sha256": previous_sha,
        "script_sha256": sha256(Path(__file__)),
    }
    manifest_path.write_text(json.dumps(report, indent=2))
    # Preserve the original pack-build contract as provenance, not a rewritten
    # claim that the packs were built from the now compacted master.
    lineage_path = path.parent / "render_packs" / "native_wind_master_lineage.json"
    lineage_path.write_text(
        json.dumps(
            {
                "status": "PASS",
                "original_master_sha256": previous_sha,
                "attached_master_sha256": report["output_blend_sha256"],
                "dependencies": dependencies,
            },
            indent=2,
        )
    )
    print("DYNAMIC2 MASTER NATIVE WIND PASS", flush=True)

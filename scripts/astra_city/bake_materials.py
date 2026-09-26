"""Bake source procedural surface color/roughness into reusable metric UV tiles.

These are representative 1 m surface swatches, not an exact bake of each object's
Generated/Object-coordinate texture. This limitation is recorded, not hidden.
"""
import json, sys, time
from pathlib import Path
import bpy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT
from astra_city.export_ue import safe


def run():
    out = OUT / "ue5/Textures"
    out.mkdir(parents=True, exist_ok=True)
    # All referenced source materials are present in the saved native city.
    source_materials = [m for m in bpy.data.materials if m.users > 0 and m.use_nodes]
    scene = bpy.data.scenes.new("Astra_Texture_Baking")
    bpy.context.window.scene = scene
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.cycles.device = "CPU"
    scene.render.bake.use_clear = True
    scene.view_settings.view_transform = "Standard"
    mesh = bpy.data.meshes.new("tile")
    mesh.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)], [], [(0, 1, 2, 3)])
    mesh.update()
    uv = mesh.uv_layers.new()
    for i, p in enumerate(((0, 0), (1, 0), (1, 1), (0, 1))):
        uv.data[i].uv = p
    obj = bpy.data.objects.new("tile", mesh)
    scene.collection.objects.link(obj)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    records = []
    for i, source in enumerate(source_materials):
        mat = source.copy()
        mesh.materials.clear()
        mesh.materials.append(mat)
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        p = next((n for n in nodes if n.type == "BSDF_PRINCIPLED"), None)
        output = next(
            (n for n in nodes if n.type == "OUTPUT_MATERIAL" and n.is_active_output),
            None,
        )
        if not output:
            records.append({"material": source.name, "status": "UNSUPPORTED_SHADER"})
            bpy.data.materials.remove(mat)
            continue
        original_surface = (
            output.inputs["Surface"].links[0].from_socket
            if output.inputs["Surface"].is_linked
            else None
        )
        em = nodes.new("ShaderNodeEmission")
        mid = "M_" + safe(source.name)
        for input_name, suffix in [
            ("Base Color", "BaseColor"),
            ("Roughness", "Roughness"),
        ]:
            for link in list(em.inputs["Color"].links):
                links.remove(link)
            inp = p.inputs[input_name] if p else None
            if inp is not None and inp.is_linked:
                links.new(inp.links[0].from_socket, em.inputs["Color"])
            else:
                v = (
                    inp.default_value
                    if inp is not None
                    else (source.diffuse_color if input_name == "Base Color" else 0.6)
                )
                em.inputs["Color"].default_value = (
                    tuple(v) if input_name == "Base Color" else (v, v, v, 1)
                )
            im = bpy.data.images.new(
                mid + "_" + suffix, 512, 512, alpha=False, is_data=suffix != "BaseColor"
            )
            im.colorspace_settings.name = (
                "sRGB" if suffix == "BaseColor" else "Non-Color"
            )
            tex = nodes.new("ShaderNodeTexImage")
            tex.image = im
            nodes.active = tex
            if (
                p is None
                and input_name == "Base Color"
                and original_surface is not None
            ):
                links.new(original_surface, output.inputs["Surface"])
                bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"}, margin=8)
            else:
                links.new(em.outputs[0], output.inputs["Surface"])
                bpy.ops.object.bake(type="EMIT", margin=8)
            im.filepath_raw = str(out / (mid + "_" + suffix + ".png"))
            im.file_format = "PNG"
            im.save()
            nodes.remove(tex)
            bpy.data.images.remove(im)
        records.append(
            {
                "material": source.name,
                "id": mid,
                "status": "BAKED",
                "tile_size_m": 1,
                "resolution": 512,
                "roughness_fallback": p is None,
                "method": "principled socket emission"
                if p
                else "nested shader diffuse-color bake; roughness fallback 0.6",
            }
        )
        bpy.data.materials.remove(mat)
        print("MATERIAL_BAKED", i + 1, len(source_materials), mid, flush=True)
    (OUT / "ue5/material_bake_audit.json").write_text(
        json.dumps(
            {
                "scope": "Representative source procedural BaseColor/Roughness tiles. Generated-space and object-specific patterns are approximated; Blender native materials remain the fidelity reference. No normal-map bake or shader-equivalence claim.",
                "records": records,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    run()

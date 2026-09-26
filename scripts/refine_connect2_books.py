"""Fine cloth bindings and spine typography on existing native book geometry."""
import bpy, sys, math, json
from pathlib import Path
from mathutils import Vector, Matrix

R = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(R / "scripts"))
import build_urban_v1_full_connect2 as B

d = B.OUT / "library"
bpy.ops.wm.open_mainfile(filepath=str(d / "scene.blend"), load_ui=False)
c = bpy.data.collections["Architecture_and_furnished_interior"]
src = bpy.data.collections["NATIVE_BookColumnFactory_0"]
colors = [
    (0.05, 0.12, 0.115),
    (0.16, 0.045, 0.035),
    (0.13, 0.12, 0.075),
    (0.09, 0.12, 0.17),
    (0.21, 0.12, 0.055),
    (0.24, 0.21, 0.16),
]
cloth = [B.material("book_cloth_" + str(i), v, 0.58) for i, v in enumerate(colors)]
paper = B.material("book_cut_pages", (0.71, 0.67, 0.56), 0.78)
ink = B.material("book_spine_foil", (0.69, 0.56, 0.28), 0.42, 0.18)
for mat in cloth:
    ns = mat.node_tree.nodes
    lk = mat.node_tree.links
    noise = ns.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 320
    bump = ns.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.20
    bump.inputs["Distance"].default_value = 0.00015
    lk.new(noise.outputs["Fac"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], ns.get("Principled BSDF").inputs["Normal"])
variants = []
titles = [
    "BOTANY",
    "CITIES",
    "HISTORY",
    "DESIGN",
    "ECOLOGY",
    "POETRY",
    "ATLAS",
    "SCIENCE",
]
for variant in range(6):
    out = B.col("NATIVE_BOUND_BOOKS_" + str(variant))
    variants.append(out)
    for original in src.objects:
        ob = B.copy(out, original)
        ob.data = original.data.copy()
        me = ob.data
        cover = me.attributes.get("cover")
        groups = {}
        for poly in me.polygons:
            if not cover or cover.data[poly.index].value < 0.5:
                groups.setdefault(poly.material_index, set()).update(poly.vertices)
        blocks = []
        for ids in groups.values():
            points = [me.vertices[i].co for i in ids]
            lo = Vector([min(p[k] for p in points) for k in range(3)])
            hi = Vector([max(p[k] for p in points) for k in range(3)])
            blocks.append((lo, hi))
        blocks.sort(key=lambda bb: (bb[0].x + bb[1].x) / 2)
        old_cover = [cover.data[p.index].value > 0.5 for p in me.polygons]
        me.materials.clear()
        me.materials.append(paper)
        for mat in cloth:
            me.materials.append(mat)
        for poly, is_cover in zip(me.polygons, old_cover):
            if is_cover:
                x = sum(me.vertices[i].co.x for i in poly.vertices) / len(poly.vertices)
                b = min(
                    range(len(blocks)),
                    key=lambda i: abs(x - (blocks[i][0].x + blocks[i][1].x) / 2),
                )
                poly.material_index = 1 + (b + variant) % len(cloth)
            else:
                poly.material_index = 0
        for sl in ob.material_slots:
            sl.link = "DATA"
        for i, (lo, hi) in enumerate(blocks):
            loc = ob.matrix_world @ Vector(
                ((lo.x + hi.x) / 2, lo.y - 0.001, lo.z + (hi.z - lo.z) * 0.55)
            )
            rot = (
                Matrix.Rotation(math.pi / 2, 4, "X")
                @ Matrix.Rotation(math.pi / 2, 4, "Z")
            ).to_euler()
            B.text(
                out,
                "bound_book_spine",
                titles[(i + variant) % len(titles)],
                loc,
                0.0045,
                ink,
                rot,
            )
for i, o in enumerate(o for o in c.objects if "native_shelf_books" in o.name):
    o.instance_collection = variants[(i * 7 + i // 5) % len(variants)]
m = json.loads((d / "scene_manifest.json").read_text())
m[
    "book_refinement"
] = "native geometry, cloth binding, page blocks, physical spine typography, supported shelf placements"
(d / "scene_manifest.json").write_text(json.dumps(m, ensure_ascii=False, indent=2))
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(d / "scene.blend"), compress=True)
print("NATIVE_BOOK_BINDINGS_REFINED", flush=True)

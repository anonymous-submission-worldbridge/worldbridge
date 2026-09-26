"""Replace terrace props with full Infinigen assets and render matching cameras."""
import argparse
from collections import Counter
import json
import math
from pathlib import Path
import sys
import time

import bpy

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from render_urban_v1_full_connect import configure, pose
from render_corner_kitchen_images2 import VIEWS

BASE = ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_connect"
OUT = BASE / "corner_kitchen2"
ASSETS = OUT / "assets/native_outdoor.blend"
META = json.loads((OUT / "assets/native_outdoor.json").read_text())
LOOKUP = {r["collection"]: r for r in META}
SELECTED = [
    "08_courtyard_eye_level",
    "05_front_full_facade",
    "06_front_left_angle",
    "07_front_right_angle",
    "09_patio_and_windows",
    "19_patio_table_close",
]
SHOTS = [next(v for v in VIEWS if v[0] == name) for name in SELECTED] + [
    (
        "21_native_tableware_detail",
        "Close-up of original furniture and tableware with cups and plates",
        (5.7, -15.8, 2.3),
        (4.02, -13.72, 0.8),
        45,
    ),
    (
        "22_native_planters_detail",
        "Close-up of an indoor plant nursery",
        (7.8, -15.8, 2.1),
        (5.87, -12.82, 0.65),
        40,
    ),
    next(v for v in VIEWS if v[0] == "02_far_right_overview"),
]
# Cover every delivered still in both source image directories, using the
# recorded cameras rather than estimating poses from the rendered pictures.
REFERENCE_VIEWS = {}
original = json.loads((BASE / "corner_kitchen/scene_manifest.json").read_text())
labels = {
    "exterior": "Original perspective: Building exterior",
    "courtyard": "First-person perspective: courtyard",
    "interior": "Original perspective: Full indoor panorama",
    "inside_to_outside": "Original perspective: Looking out of the window onto the outside world.",
    "outside_to_inside": "Original perspective: Looking at the indoor from outside.",
    "detail": "Original perspective: Details of the dining table",
}
for name, shot in original["shots"].items():
    REFERENCE_VIEWS[name] = dict(
        shot, reference_image=f"images/{name}.png", description=labels[name]
    )
expanded = json.loads(
    (BASE / "corner_kitchen/images2/render_manifest.json").read_text()
)
for shot in expanded["renders"]:
    REFERENCE_VIEWS[shot["name"]] = dict(
        position=shot["position"],
        target=shot["target"],
        lens=shot["lens_mm"],
        reference_image=f"images2/{shot['name']}.png",
        description=shot["description"],
    )
known = {shot[0]: shot for shot in SHOTS}
for name, shot in REFERENCE_VIEWS.items():
    if name in known:
        existing = known[name]
        assert (
            list(existing[2]) == shot["position"]
            and list(existing[3]) == shot["target"]
        )
        assert existing[4] == shot["lens"]
    else:
        SHOTS.append(
            (name, shot["description"], shot["position"], shot["target"], shot["lens"])
        )
PLACEMENTS = []


def native(collection, factory, index, name, loc, scale=1.0, rotation=0.0):
    key = f"CK2_NATIVE_{factory}_{index}"
    obj = bpy.data.objects.new("corner2:" + name, None)
    collection.objects.link(obj)
    obj.instance_type = "COLLECTION"
    obj.instance_collection = bpy.data.collections[key]
    obj.location = loc
    obj.scale = (scale,) * 3
    obj.rotation_euler.z = rotation
    obj["asset_factory"] = factory
    obj["asset_source_object"] = LOOKUP[key]["original_object"]
    obj["asset_source_library"] = str(ASSETS)
    PLACEMENTS.append(
        dict(
            name=obj.name,
            parent_collection=collection.name,
            factory=factory,
            asset_collection=key,
            location=list(loc),
            scale=scale,
            rotation_z=rotation,
        )
    )
    return obj


def clear(collection):
    removed = [o.name for o in collection.objects]
    for obj in list(collection.objects):
        collection.objects.unlink(obj)
    for child in list(collection.children):
        collection.children.unlink(child)
    return removed


def instance_counts(collection, multiplier=1, active=None):
    active = set() if active is None else active
    if collection.name in active:
        raise RuntimeError("Collection cycle: " + collection.name)
    active = active | {collection.name}
    counts = Counter()
    for obj in collection.objects:
        if obj.hide_render:
            continue
        if obj.get("asset_factory") and obj.instance_collection:
            counts[obj["asset_factory"]] += multiplier
        if obj.instance_collection:
            counts.update(instance_counts(obj.instance_collection, multiplier, active))
    for child in collection.children:
        counts.update(instance_counts(child, multiplier, active))
    return counts


def build():
    bpy.ops.wm.open_mainfile(
        filepath=str(BASE / "corner_kitchen/scene.blend"), load_ui=False
    )
    needed = [
        "CK2_NATIVE_TableDiningFactory_0",
        "CK2_NATIVE_ChairFactory_0",
        "CK2_NATIVE_PlateFactory_0",
        "CK2_NATIVE_CupFactory_4",
        "CK2_NATIVE_CupFactory_5",
        "CK2_NATIVE_PlantContainerFactory_1",
        "CK2_NATIVE_PlantContainerFactory_3",
        "CK2_NATIVE_LargePlantContainerFactory_3",
    ]
    with bpy.data.libraries.load(str(ASSETS), link=True) as (available, requested):
        assert set(needed) <= set(available.collections)
        requested.collections = list(needed)

    removed = {}
    terrace = bpy.data.collections["OUTDOOR_CAFE_SET_MASTER"]
    removed[terrace.name] = clear(terrace)
    table_scale = 0.90
    top_z = LOOKUP["CK2_NATIVE_TableDiningFactory_0"]["dimensions"][2] * table_scale
    native(
        terrace, "TableDiningFactory", 0, "terrace_dining_table", (0, 0, 0), table_scale
    )
    for i, (x, y) in enumerate([(0, -0.84), (0, 0.84), (-1.08, 0), (1.08, 0)]):
        # Native ChairFactory faces +X, after its own baked pi/2 rotation.
        native(
            terrace,
            "ChairFactory",
            0,
            f"terrace_chair_{i}",
            (x, y, 0),
            1.0,
            math.atan2(-y, -x),
        )
    for i, (x, y) in enumerate([(-0.50, 0), (0.50, 0), (0, -0.28), (0, 0.28)]):
        native(
            terrace, "PlateFactory", 0, f"dinner_plate_{i}", (x, y, top_z + 0.001), 0.76
        )
    for i, (x, y) in enumerate(
        [(-0.50, -0.23), (0.50, 0.23), (0.23, -0.28), (-0.23, 0.28)]
    ):
        native(
            terrace,
            "CupFactory",
            4 + i % 2,
            f"tea_cup_{i}",
            (x, y, top_z + 0.001),
            1.0,
            i * math.pi / 2,
        )

    planter = bpy.data.collections["REFINED_COMMERCIAL_PLANTER_MASTER"]
    removed[planter.name] = clear(planter)
    native(
        planter,
        "LargePlantContainerFactory",
        3,
        "large_native_potted_plant",
        (0, 0, 0),
        1.15,
    )

    # The old low rectangular forecourt planters are replaced as complete
    # planted containers, including their pot, soil and plant geometry.
    flowerbed = bpy.data.collections["COMPLEX_REAR_FLOWERBED_MASTER"]
    removed[flowerbed.name] = clear(flowerbed)
    native(
        flowerbed,
        "LargePlantContainerFactory",
        3,
        "native_planter_group_tall",
        (0, 0.08, 0),
        1.0,
        0.3,
    )
    native(
        flowerbed,
        "PlantContainerFactory",
        1,
        "native_planter_group_left",
        (-0.43, -0.14, 0),
        1.45,
        0.6,
    )
    native(
        flowerbed,
        "PlantContainerFactory",
        3,
        "native_planter_group_right",
        (0.43, -0.14, 0),
        1.45,
        -0.8,
    )

    scene = bpy.context.scene
    pose(scene, SHOTS[0][2], SHOTS[0][3], SHOTS[0][4])
    scene.camera.data.dof.use_dof = False
    bpy.context.preferences.filepaths.save_version = 0
    bpy.context.view_layer.update()
    counts = instance_counts(scene.collection)
    # Only the new exterior instances carry factory metadata on instance objects.
    assert counts["TableDiningFactory"] == 6, counts
    assert counts["ChairFactory"] == 24, counts
    assert counts["CupFactory"] == counts["PlateFactory"] == 24, counts
    report = dict(
        source_blend=str(BASE / "corner_kitchen/scene.blend"),
        replacement_method="Linked complete cached Infinigen factory meshes and materials",
        original_factory_source=str(
            ROOT / "infinigen/outputs/indoor_outdoor_villa_demo2/coarse/scene.blend"
        ),
        native_assets=[LOOKUP[k] for k in needed],
        replaced_collections=removed,
        placements=PLACEMENTS,
        rendered_exterior_asset_counts=dict(counts),
        table_top_local_z=top_z,
        matching_camera=dict(
            position=SHOTS[0][2], target=SHOTS[0][3], lens_mm=SHOTS[0][4]
        ),
    )
    (OUT / "asset_replacement_manifest.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene.blend"), compress=True)
    print("CORNER2_BUILD " + json.dumps(dict(counts)), flush=True)


def render(preview, names, overwrite):
    bpy.ops.wm.open_mainfile(filepath=str(OUT / "scene.blend"), load_ui=False)
    scene = bpy.context.scene
    devices = configure(scene, 800 if preview else 1920, 24 if preview else 128)
    output = OUT / (".previews" if preview else "images")
    output.mkdir(exist_ok=True)
    report_path = output / "render_manifest.json"
    report = (
        json.loads(report_path.read_text())
        if report_path.exists()
        else dict(
            source_blend=str(OUT / "scene.blend"),
            resolution=[scene.render.resolution_x, scene.render.resolution_y],
            samples=scene.cycles.samples,
            devices=devices,
            renders=[],
        )
    )
    for name, label, position, target, lens in SHOTS:
        if names and name not in names:
            continue
        dest = output / (name + ".png")
        if dest.exists() and not overwrite:
            continue
        pose(scene, position, target, lens)
        scene.render.filepath = str(dest)
        start = time.monotonic()
        bpy.ops.render.render(write_still=True)
        report["renders"] = [r for r in report["renders"] if r["name"] != name]
        report["renders"].append(
            dict(
                name=name,
                description=label,
                file=str(dest),
                position=position,
                target=target,
                lens_mm=lens,
                seconds=round(time.monotonic() - start, 2),
            )
        )
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2))
        print("CORNER2_RENDER " + name, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--build", action="store_true")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--shots", default="")
    p.add_argument("--overwrite", action="store_true")
    a = p.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])
    OUT.mkdir(exist_ok=True)
    if a.build:
        build()
    render(a.preview, set(a.shots.split(",")) if a.shots else None, a.overwrite)

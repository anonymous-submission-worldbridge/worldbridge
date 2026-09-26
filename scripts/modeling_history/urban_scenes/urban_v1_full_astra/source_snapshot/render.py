"""Render evidence from the saved full city, never from an isolated asset island."""
import json, math, os, sys, time
from pathlib import Path
import bpy
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT, world_point


def main():
    scene = bpy.context.scene
    plan = json.loads((OUT / "world_manifest.json").read_text())
    geom = json.loads((OUT / "geometry_manifest.json").read_text())
    views = [
        ("01_city_aerial_SW", (-205, -230, 205), (0, 0, 2), "PERSP", 30),
        ("02_city_aerial_NE", (210, 210, 195), (0, 0, 3), "PERSP", 29),
        ("03_city_aerial_NW", (-240, 180, 170), (0, 0, 2), "PERSP", 29),
        ("04_city_aerial_SE", (220, -210, 155), (0, 0, 4), "PERSP", 28),
        ("05_city_topdown", (0, 0, 350), (0, 0, 0), "ORTHO", 340),
        ("06_main_street", (-115, -35, 1.82), (-25, -31, 4.0), "PERSP", 24),
        ("07_garden_street", (-38, 48, 1.82), (55, 39, 4.0), "PERSP", 24),
    ]
    selected = []
    for use in ("cafe", "retail", "residential"):
        b = next(x for x in plan["buildings"] if x["use"] == use and x["width"] >= 15)
        selected.append(b)
    b = selected[0]
    views.append(
        (
            "08_seamless_entrance",
            world_point(b, -0.3, -3.5, 1.82),
            world_point(b, 0, 6, 1.82),
            "PERSP",
            20,
        )
    )
    for i, b in enumerate(selected):
        kind = {"cafe": "dining", "retail": "shop", "residential": "living"}[b["use"]]
        room = next(
            r
            for r in geom["rooms"]
            if r["building_id"] == b["id"] and r["kind"] == kind and r["floor"] == 0
        )
        x0, y0, x1, y1 = room["bounds"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        eye = (x1 - 0.4, y0 + 0.55, 1.72) if cx < 0 else (x0 + 0.4, y0 + 0.55, 1.72)
        views.append(
            (
                f"{9+i:02d}_interior_{kind}",
                world_point(b, *eye),
                world_point(b, cx, cy + 0.7, 1.15),
                "PERSP",
                18,
            )
        )
    b = selected[-1]
    views.append(
        (
            "12_stair_connection",
            world_point(b, -0.1, b["depth"] - 6.1, 1.82),
            world_point(b, -0.6, b["depth"] - 1.8, 3.0),
            "PERSP",
            16,
        )
    )
    views.append(("13_street_360", (-38, 48, 1.82), (-25, 46, 1.82), "PANO", 20))
    for j, kind in enumerate(("bedroom", "kitchen", "bathroom")):
        room = next(
            r
            for r in geom["rooms"]
            if r["building_id"] == b["id"] and r["kind"] == kind and r["floor"] == 0
        )
        x0, y0, x1, y1 = room["bounds"]
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        eye = (x1 - 0.35, y0 + 0.45, 1.72) if cx < 0 else (x0 + 0.35, y0 + 0.45, 1.72)
        views.append(
            (
                f"{14+j:02d}_interior_{kind}",
                world_point(b, *eye),
                world_point(b, cx, cy + 0.45, 1.1),
                "PERSP",
                17,
            )
        )
    camera_data = bpy.data.cameras.new("Astra Evidence Camera")
    camera = bpy.data.objects.new(camera_data.name, camera_data)
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.samples = int(os.environ.get("ASTRA_SAMPLES", "32"))
    scene.cycles.use_denoising = True
    scene.cycles.use_light_tree = True
    scene.cycles.max_bounces = 6
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    if os.environ.get("ASTRA_CPU") != "1":
        prefs = bpy.context.preferences.addons["cycles"].preferences
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        gpu = [d for d in prefs.devices if d.type == "OPTIX"]
        if not gpu:
            raise RuntimeError(
                "No OPTIX GPU visible. Use approved GPU execution or ASTRA_CPU=1."
            )
        for d in prefs.devices:
            d.use = d.type == "OPTIX"
        scene.cycles.device = "GPU"
        print("RENDER_DEVICES", [d.name for d in gpu], flush=True)
    result = []
    dest = OUT / "renders"
    dest.mkdir(exist_ok=True)
    subset = set(os.environ.get("ASTRA_VIEWS", "").split(",")) - {""}
    for name, position, target, kind, lens in views:
        if subset and name not in subset:
            continue
        camera_data = bpy.data.cameras.new("Evidence_" + name)
        camera = bpy.data.objects.new(camera_data.name, camera_data)
        scene.collection.objects.link(camera)
        scene.camera = camera
        camera.location = position
        camera.rotation_euler = (
            (Vector(target) - camera.location).to_track_quat("-Z", "Y").to_euler()
        )
        camera_data.type = kind
        camera_data.lens = lens
        camera_data.clip_end = 2000
        if kind == "ORTHO":
            camera_data.ortho_scale = lens
        if kind == "PANO":
            camera_data.panorama_type = "EQUIRECTANGULAR"
        scene.render.resolution_x = (
            2560 if kind == "PANO" else int(os.environ.get("ASTRA_WIDTH", "1920"))
        )
        scene.render.resolution_y = (
            1280 if kind == "PANO" else round(scene.render.resolution_x * 9 / 16)
        )
        scene.render.resolution_percentage = 100
        scene.render.filepath = str(dest / (name + ".png"))
        if "city_aerial" in name or "topdown" in name:
            from bpy_extras.object_utils import world_to_camera_view

            # Fit the complete city boundary at ground and rooftop elevation, including the near corners.
            roof = max(b["floors"] for b in plan["buildings"]) * 3.2 + 2
            corners = [
                Vector((x, y, z)) for x, y in plan["boundary"] for z in (0, roof)
            ]
            for _ in range(60):
                bpy.context.view_layer.update()
                projected = [world_to_camera_view(scene, camera, p) for p in corners]
                if all(
                    0.035 < p.x < 0.965 and 0.035 < p.y < 0.965 and p.z > 0
                    for p in projected
                ):
                    break
                if kind == "ORTHO":
                    camera_data.ortho_scale *= 1.045
                else:
                    camera.location = (
                        Vector(target) + (camera.location - Vector(target)) * 1.045
                    )
            else:
                raise RuntimeError("Unable to frame complete city " + name)
        scene.view_settings.exposure = (
            0.5
            if "interior" in name or "stair" in name
            else (-0.4 if "aerial" in name or "topdown" in name else 0)
        )
        begin = time.time()
        bpy.ops.render.render(write_still=True)
        result.append(
            {
                "name": name,
                "camera": list(camera.location),
                "target": list(target),
                "type": kind,
                "seconds": time.time() - begin,
                "source_scene": str(OUT / "urban_v1_full_astra.blend"),
                "plan_sha256": plan["plan_sha256"],
                "all_buildings_enabled_for_render": True,
                "city_boundary_in_frame": True
                if "city_aerial" in name or "topdown" in name
                else None,
            }
        )
        (dest / "render_manifest.json").write_text(json.dumps(result, indent=2))
        print("EVIDENCE_SAVED", name, flush=True)
    bpy.context.preferences.filepaths.save_version = 0
    scene.camera = bpy.data.objects.get("Evidence_01_city_aerial_SW") or camera
    # Camera-only evidence project references the same complete mesh scene.
    bpy.ops.wm.save_as_mainfile(
        filepath=str(OUT / "urban_v1_full_astra.blend"), compress=True
    )


if __name__ == "__main__":
    main()

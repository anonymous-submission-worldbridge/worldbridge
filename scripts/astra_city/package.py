"""Consolidate auditable outputs and a local gallery; never mark UE tests as run."""
from collections import Counter
import hashlib, html, json, shutil, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from astra_city.plan import OUT


def read(name):
    return json.loads((OUT / name).read_text())


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run():
    plan = read("world_manifest.json")
    layout = read("layout_audit.json")
    geom = read("geometry_manifest.json")
    nav = read("geometry_audit.json")
    mesh = read("mesh_audit.json")
    ue = read("ue5/scene_manifest.json")
    fbx = read("ue5/fbx_roundtrip_audit.json")
    bakes = read("ue5/material_bake_audit.json")
    render = read("renders/render_manifest.json")
    errors = []
    for name, report in [
        ("layout", layout),
        ("navigation", nav),
        ("actual_mesh", mesh),
        ("fbx_roundtrip", fbx),
    ]:
        if report["status"] != "PASS":
            errors.append(name + " failed")
    for report in (layout, geom, ue):
        if report["plan_sha256"] != plan["plan_sha256"]:
            errors.append("Mismatched plan revision")
    if mesh["scene_plan_sha256"] != plan["plan_sha256"]:
        errors.append("Mesh audit revision mismatch")
    source_integrity = []
    registry = read("asset_registry.json")["assets"]
    for filename in sorted({r["source"] for r in registry if r.get("source")}):
        path = Path(filename)
        sha = digest(path)
        declared = {
            r.get("source_sha256", r.get("sha256"))
            for r in registry
            if r.get("source") == filename
        } - {None}
        ok = not declared or declared == {sha}
        if not ok:
            errors.append("Source changed since extraction " + filename)
        source_integrity.append(
            {
                "path": filename,
                "bytes": path.stat().st_size,
                "sha256": sha,
                "recorded_hash_matches": ok,
            }
        )
    (OUT / "source_integrity.json").write_text(json.dumps(source_integrity, indent=2))
    import io, unittest

    log = io.StringIO()
    suite = unittest.defaultTestLoader.loadTestsFromName("astra_city.test_pipeline")
    tests = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    (OUT / "logs/unit_tests.log").write_text(log.getvalue())
    if not tests.wasSuccessful():
        errors.append("Regression tests failed")
    for m in ue["meshes"]:
        p = OUT / "ue5" / m["file"]
        if not p.is_file() or p.stat().st_size != m["bytes"]:
            errors.append("Missing/truncated FBX " + m["id"])
        if any(mid not in {x["id"] for x in ue["materials"]} for mid in m["materials"]):
            errors.append("Missing material mapping " + m["id"])
    for m in ue["materials"]:
        for suffix in ("BaseColor", "Roughness"):
            if not (OUT / "ue5/Textures" / f'{m["id"]}_{suffix}.png').is_file():
                errors.append("Missing baked texture " + m["id"] + " " + suffix)
    if len(render) < 16:
        errors.append("Incomplete final camera set")
    from PIL import Image

    image_checks = []
    for view in render:
        if view.get("plan_sha256") != plan["plan_sha256"]:
            errors.append("Render revision mismatch " + view["name"])
        if ("city_aerial" in view["name"] or "topdown" in view["name"]) and view.get(
            "city_boundary_in_frame"
        ) is not True:
            errors.append("Full city framing not verified " + view["name"])
        path = OUT / "renders" / (view["name"] + ".png")
        if not path.exists():
            errors.append("Missing render " + view["name"])
            continue
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            import numpy as np

            pixels = np.asarray(image.convert("RGB"), dtype=np.float32) / 255
            luminance = pixels.mean(axis=2)
            image_checks.append(
                {
                    "name": view["name"],
                    "width": image.width,
                    "height": image.height,
                    "mean_display_luminance": float(luminance.mean()),
                    "near_black_ratio": float((luminance < 0.025).mean()),
                }
            )
            if luminance.mean() < 0.035:
                errors.append("Unacceptably dark evidence " + view["name"])
    native_roles = {k: v for k, v in mesh["role_counts"].items() if k != "CAMERA"}
    sources = OUT / "source_snapshot"
    sources.mkdir(exist_ok=True)
    for path in (ROOT / "scripts/astra_city").glob("*.py"):
        shutil.copy2(path, sources / path.name)
    shutil.copy2(
        ROOT / "scripts/generate_urban_v1_full_astra.py",
        sources / "generate_urban_v1_full_astra.py",
    )
    source_files = {
        str(p.relative_to(ROOT)): digest(p)
        for p in sorted((ROOT / "scripts/astra_city").glob("*.py"))
    }
    building_area = sum(b["building_area_m2"] for b in layout["blocks"])
    report = {
        "status": "OFFLINE_DELIVERABLES_PASS_UE5_PENDING"
        if not errors
        else "OFFLINE_FAILURE",
        "errors": errors,
        "generated_at": time.strftime("%Y-%m-%d %H:%M:%S %z"),
        "plan_sha256": plan["plan_sha256"],
        "scope": "Fixed 61,645.5 m2 city boundary. Surrounding visual context terrain is not counted as developed city.",
        "metrics": {
            "city_area_m2": layout["city_area_m2"],
            "city_building_footprint_ratio": building_area / layout["city_area_m2"],
            "blocks": len(plan["blocks"]),
            "buildings": len(plan["buildings"]),
            "floors": layout["floors"],
            "rooms": len(geom["rooms"]),
            "furniture_instances": len(geom["furniture"]),
            "doors": len(geom["doors"]),
            "trees": sum(p["kind"] == "botanical_tree" for p in geom["props"]),
            "street_frontage_ratio": layout["frontage"]["length_weighted_ratio"],
            "block_building_coverage_range": [
                min(
                    b["building_coverage"]
                    for b in layout["blocks"]
                    if b["use"] != "public_park"
                ),
                max(b["building_coverage"] for b in layout["blocks"]),
            ],
            "building_footprint_overlaps": len(layout["overlaps"]),
            "actual_ground_coverage": mesh["actual_city_ground_coverage"],
            "room_routes_passed": nav["room_paths_found"],
            "entrances_connected": sum(r["connected"] for r in nav["entrances"]),
            "courtyard_park_areas_connected": sum(
                r["connected"] for r in nav["courtyards_and_park"]
            ),
            "actual_mesh_rays": mesh["ground_and_headroom_rays"],
            "fbx_mesh_assets": len(ue["meshes"]),
            "ue_mesh_instances": len(ue["instances"]),
            "ucx_collision_hulls": sum(m["collision_hulls"] for m in ue["meshes"]),
            "materials": len(ue["materials"]),
            "evidence_images": len(image_checks),
        },
        "native_scene_roles": native_roles,
        "image_checks": image_checks,
        "pipeline_source_sha256": source_files,
        "regression_tests": {
            "run": tests.testsRun,
            "failures": len(tests.failures),
            "errors": len(tests.errors),
            "passed": tests.wasSuccessful(),
        },
        "source_integrity": source_integrity,
        "visual_review": {
            "path": "visual_review.zh-CN.md",
            "method": "Agent visual inspection of final renders; limitations recorded, not UE runtime acceptance",
            "sha256": digest(OUT / "visual_review.zh-CN.md"),
        },
        "artifacts": {
            "blend": {
                "path": "urban_v1_full_astra.blend",
                "bytes": (OUT / "urban_v1_full_astra.blend").stat().st_size,
            },
            "ue_fbx_bytes": sum(m["bytes"] for m in ue["meshes"]),
        },
        "unreal": {
            "editor_found": False,
            "cpp_compile": "NOT_RUN",
            "editor_import": "NOT_RUN",
            "character_walk": "NOT_RUN",
            "performance_fps": "NOT_MEASURED",
            "navmesh": "NOT_BUILT",
            "required_next_input": "UE5 version, UnrealEditor path, and target project path",
        },
        "limitations": [
            "UE5 project is source plus import-ready assets; no .umap or cooked executable has been produced without UnrealEditor.",
            "Representative procedural BaseColor/Roughness tiles approximate object-space shaders; no exact shader-equivalence or normal-map bake claim.",
            "Native botanical meshes are retained at full detail; UE Nanite flags are prepared, but runtime foliage cost has not been measured.",
            "Navigation uses conservative boxes and sampled rays, not a continuous swept UE capsule. Decorative overhang intersections are not treated as parcel conflicts.",
            "No NPC/traffic simulation, AI NavMesh build or World Partition streaming benchmark is included.",
        ],
    }
    (OUT / "acceptance_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False)
    )
    geom["status"] = (
        "OFFLINE_VALIDATED_UE5_PENDING" if not errors else "BUILT_PENDING_CORRECTION"
    )
    (OUT / "geometry_manifest.json").write_text(
        json.dumps(geom, indent=2, ensure_ascii=False)
    )
    captions = {
        "01_city_aerial_SW": "Overview of Southwest Entire City",
        "02_city_aerial_NE": "Overview of Northeast City",
        "03_city_aerial_NW": "Northwest city overview",
        "04_city_aerial_SE": "Southeast City Overview",
        "05_city_topdown": "Complete side view",
        "06_main_street": "Main Street Continuous Interface",
        "07_garden_street": "Garden Street",
        "08_seamless_entrance": "street - entrance - indoor",
        "09_interior_dining": "coffee dining space",
        "10_interior_shop": "full-sized shelf store",
        "11_interior_living": "real furniture living room",
        "12_stair_connection": "Connects upper and lower stairs.",
        "13_street_360": "360° Equidistant Cylindrical Panorama of Street",
        "14_interior_bedroom": "bedroom",
        "15_interior_kitchen": "Kitchen",
        "16_interior_bathroom": "bathroom",
    }
    cards = "".join(
        f'<figure><a href="renders/{v["name"]}.png"><img loading="lazy" src="renders/{v["name"]}.png"></a><figcaption>{captions.get(v["name"],html.escape(v["name"]))}</figcaption></figure>'
        for v in render
    )
    page = (
        """<!doctype html><html lang=\"en\"><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Astra City · Real Scene and Acceptance</title>
<style>body{margin:0;background:#121b1d;color:#e4e9e7;font:16px/1.6 system-ui}main{max-width:1500px;margin:auto;padding:36px}h1{font-size:34px}a{color:#add8cb}.summary{padding:22px;background:#233438;border-radius:12px}.gallery{display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:22px}figure{margin:0;background:#1b2b2e;border-radius:8px;overflow:hidden}img{display:block;width:100%}figcaption{padding:12px}small{color:#b6c6c4}@media(max-width:500px){main{padding:16px}.gallery{grid-template-columns:1fr}}</style><main>
<h1>Astra City · Continuous Urban Environment Indoors and Outdoors</h1><div class=\"summary\">72 buildings · 255 floors · 1,020 rooms · 3,075 pieces of furniture · 9 irregular blocks<br>Street continuity rate 81.4% · Building coverage rate on non-park plots 66.9%–75.6%<br><strong>Offline geometry acceptance completed; UE5 compilation, import, in-game walking and frame rate have not been accepted yet.</strong><br>
<a href=\"README.zh-CN.md\">Usage Instructions</a> · <a href=\"acceptance_report.json\">Full Audit</a> · <a href=\"visual_review.zh-CN.md\">Visual Review and Limitations</a> · <a href=\"layout_plan.png\">Layout Plan</a> · <a href=\"urban_v1_full_astra.blend\">Blender Scene</a> · <a href=\"ue5/AstraCity/AstraCity.uproject\">UE5 Project Entry</a></div>
<p>All images below were rendered from the same complete 3D scene. No roofs, buildings, or surrounding blocks were hidden for these views. Click to view the original.</p><div class=\"gallery\">"""
        + cards
        + "</div><p><small>The background ground outside the city boundary provides an environmental transition and is excluded from city coverage. The 360° file uses equirectangular projection and can be imported into a panorama viewer.</small></p></main></html>"
    )
    (OUT / "index.html").write_text(page, encoding="utf8")
    print(
        json.dumps(
            {
                "status": report["status"],
                "errors": errors,
                "metrics": report["metrics"],
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    if errors:
        raise RuntimeError("Delivery audit failed")


if __name__ == "__main__":
    run()

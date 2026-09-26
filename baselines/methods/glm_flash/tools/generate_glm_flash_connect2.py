#!/usr/bin/env python3
"""Generate six ordinary residential/retail connected scenes with GLM-5.3 Flash."""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import json
from pathlib import Path
import sys

import baselines.methods.glm_flash.tools.generate_glm_flash_connect as base


OUTPUT = base.BASELINES / "annotations/glm53_flash/connect2"

SCENES = (
    {
        "scene_id": "apartment_living_room",
        "brief": "an ordinary contemporary apartment living and dining room opening through a wide sliding doorway to a small furnished balcony, shared courtyard and neighboring apartment buildings",
        "palette": "warm white walls, pale oak floor, oatmeal upholstery, muted blue, black metal, leafy green",
        "interior_program": "sectional sofa with layered cushions, coffee and side tables, television console, books, framed pictures, floor lamp, dining table and four chairs, curtains, radiator, plants and small household accessories",
        "exterior_program": "balcony railing, two balcony chairs, planters, courtyard paving, bicycle rack, shrubs, trees, benches and restrained apartment facades",
    },
    {
        "scene_id": "suburban_kitchen_dining",
        "brief": "a normal family kitchen and breakfast room opening through glazed patio doors to a modest backyard patio, lawn, fence, garden shed and quiet residential lane",
        "palette": "soft cream, natural oak, sage cabinet fronts, pale quartz, stainless steel, terracotta",
        "interior_program": "detailed base and wall cabinets, sink, oven, cooktop, refrigerator, kitchen island, stools, dining table, chairs, pendant lights, crockery, plants and practical countertop objects",
        "exterior_program": "patio dining set, paving, lawn, timber fence, planters, barbecue, shed, trees and glimpses of ordinary neighboring houses",
    },
    {
        "scene_id": "townhouse_entry_lounge",
        "brief": "a conventional townhouse front lounge and entry hall opening through the front door to a covered porch, planted front path and quiet residential street",
        "palette": "off white, mid oak, soft gray, brick red, navy accents, warm brass",
        "interior_program": "sofa and armchairs, rug, coffee table, media cabinet, console and mirror, coat storage, shoe bench, side lamps, books, pictures, plants, stair suggestion and small domestic objects",
        "exterior_program": "covered porch, door furniture, house-number-free mailbox, front path, low hedge, flower beds, sidewalk, parked bicycles, street trees and neighboring townhouse fronts",
    },
    {
        "scene_id": "neighborhood_bakery",
        "brief": "an everyday neighborhood bakery sales floor with an open glazed entrance to a normal sidewalk and mixed residential retail street",
        "palette": "cream tile, honey oak, warm white, muted terracotta, charcoal, soft brass",
        "interior_program": "service counter, glass pastry display, bread shelves filled with varied loaves, menu-board shapes without text, till, packaging, small cafe tables and chairs, pendant lights, wall tile and visible preparation counter",
        "exterior_program": "simple awning, sidewalk tables, planters, bicycle, street lamps, curb, narrow road, street trees and ordinary neighboring storefronts without logos",
    },
    {
        "scene_id": "corner_convenience_store",
        "brief": "a small ordinary convenience store with a broad open entrance connected to a sidewalk, curbside parking bay and typical neighborhood street",
        "palette": "clean white, light gray, birch, subdued green, red accents, dark rubber and stainless steel",
        "interior_program": "several fully stocked gondola shelves, refrigerated display cases, checkout counter, basket stack, beverage cooler, end caps, ceiling lights, price-rail shapes without text and a clear central aisle",
        "exterior_program": "simple canopy, sidewalk, bollards, waste bin, bicycle, compact parked car forms, curb, asphalt street, planters, street tree and ordinary nearby facades",
    },
    {
        "scene_id": "small_clothing_boutique",
        "brief": "a modest independent clothing shop with an open storefront connecting directly to a pedestrian shopping street",
        "palette": "warm white, pale timber, dusty rose, muted olive, charcoal metal, brushed brass",
        "interior_program": "wall rails, freestanding clothing racks with many individual garments, folded-clothes shelves, display tables, checkout desk, mirrors, fitting-room fronts, bench, rug, plants and track lighting",
        "exterior_program": "restrained shopfront, small awning, sidewalk display rack, planters, bench, paving, street lamps, trees and ordinary neighboring retail facades without logos",
    },
)


def prompt_for(scene: dict[str, str]) -> str:
    return f"""You are the procedural scene-planning component of a 3D generation benchmark.
Create one HIGH-DETAIL but efficient Blender blueprint for a believable, ordinary
residential or neighborhood retail environment. Avoid resorts, galleries, fantasy,
monumental spaces, luxury showrooms and stylized theme-park layouts.

SCENE_ID: {scene['scene_id']}
CONCEPT: {scene['brief']}
PALETTE: {scene['palette']}
INTERIOR REQUIREMENTS: {scene['interior_program']}
EXTERIOR REQUIREMENTS: {scene['exterior_program']}

The result must be one continuous true 3D environment in a shared coordinate frame:
- X is left/right, Y runs from indoor to outdoor, Z is up.
- The conventional rectangular interior is x=-6..6, y=-9..0, z=0..3.65.
- The exterior is x=-15..15, y=0..20.
- Keep a physically open 2.2 m entrance centered at x=0, y=0. Never put geometry
  across x=-1.1..1.1 at the facade below z=2.8. Keep the threshold flush.
- Preserve a clear 1.25 m camera/walking aisle from (0,-8,0) through (0,0,0)
  to (0,5,0), while densely furnishing the rest of the interior.
- At least 70 percent of semantic attention and visible detail must be indoors.
- Give furniture realistic proportions and layered construction: frames, fronts,
  handles, cushions, shelves, products, trim and small accessories. Do not represent
  a major furnishing as a single plain box when a semantic helper exists.
- Build spatial depth at foreground/midground/background. Add multiple recognizable
  furnishing clusters along both side walls and at the rear, but do not block views.
- Exterior context should be ordinary and restrained, subordinate to the interior.
- Use many unique descriptive object names. Avoid text, numbers, signs and logos.
- No external files/assets/downloads, image textures, booleans, geometry nodes,
  physics, particles or simulations. Use only the safe procedural API below.

Return EXACTLY one JSON object whose only key is "code". Its value must be valid
Python source defining SCENE_SPEC and build_scene(api). No markdown or prose. No
imports and no file I/O. Create all materials before geometry. Use 110-210 API calls.

Safe API methods:
api.mat(name, color_rgb, metallic=0.0, roughness=0.5, emission=0.0)
api.box(name, location_xyz, scale_xyz, material, bevel=0.04)
api.cylinder(name, location_xyz, radius, depth, material, vertices=32)
api.sphere(name, location_xyz, scale_xyz, material, segments=32)
api.arch(name, location_xyz, width, height, depth, material)
api.table(name, location_xyz, size_xyz, top_material, leg_material)
api.chair(name, location_xyz, yaw_degrees, material, accent_material)
api.sofa(name, location_xyz, yaw_degrees, size_xyz, material, accent_material)
api.shelf(name, location_xyz, size_xyz, frame_material, item_material)
api.cabinet(name, location_xyz, size_xyz, body_material, front_material, handle_material)
api.counter(name, location_xyz, size_xyz, body_material, top_material, front_material, handle_material)
api.appliance(name, location_xyz, size_xyz, body_material, face_material, accent_material)
api.window(name, location_xyz, size_xyz, frame_material, glass_material)
api.plant(name, location_xyz, height, pot_material, leaf_material)
api.ceiling_light(name, location_xyz, radius, fixture_material, glow_material, energy=250)
api.display_unit(name, location_xyz, size_xyz, frame_material, product_material, accent_material)
api.clothes_rack(name, location_xyz, width, height, frame_material, garment_material, accent_material)
api.tree(name, location_xyz, trunk_height, crown_radius, trunk_material, leaf_material)
api.lamp(name, location_xyz, height, pole_material, light_material)
api.art(name, location_xyz, scale_xyz, material, frame_material)
api.rug(name, location_xyz, size_xy, material)
api.road(name, location_xyz, size_xyz, road_material, line_material)

SCENE_SPEC must be a plain dictionary with scene_id, concept, palette,
entrance_clear_width_m, object_intent (a rich list), scene_category and
interior_detail_level set to "high". build_scene(api) must create a complete scene.
The harness already supplies structural floor, ceiling, walls and an open entrance,
so spend most calls on detailed semantic contents, built-ins and finish accents;
do not duplicate large room shells. Include a few windows and credible exterior
context. Do not create cameras, lights except through api.ceiling_light, render
settings, worlds, save operations or exports.
"""


base.DEFAULT_OUTPUT = OUTPUT
base.SCENES = SCENES
base.prompt_for = prompt_for


def recover_latest_direct_response(scene_id: str) -> int:
    """Accept a genuine Coding Plan response that added harmless JSON metadata."""
    scene = next(item for item in SCENES if item["scene_id"] == scene_id)
    scene_root = OUTPUT / scene_id
    response_path = scene_root / "logs/generation_01/response.json"
    value = json.loads(response_path.read_text(encoding="utf-8"))
    choices = value.get("choices") or []
    if len(choices) != 1:
        raise ValueError("latest Coding Plan response does not contain one choice")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str):
        raise ValueError("latest Coding Plan response contains no text")
    payload, _ = json.JSONDecoder().raw_decode(content.lstrip())
    code = payload.get("code") if isinstance(payload, dict) else None
    if not isinstance(code, str):
        raise ValueError("latest Coding Plan response contains no code field")
    code = code.rstrip() + "\n"
    model_spec = base.validate_code(code, scene_id)
    source_path = scene_root / "source/generated.py"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = source_path.with_suffix(".py.tmp")
    temporary.write_text(code, encoding="utf-8")
    temporary.replace(source_path)
    manifest_path = scene_root / "generation_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest.update(
        completed_at_utc=base.utc(),
        generated_code_sha256=base.sha256(source_path),
        generated_scene_spec=model_spec,
        response={
            "response_id": value.get("id"),
            "model_returned": value.get("model"),
            "finish_reason": choices[0].get("finish_reason"),
            "usage": value.get("usage", {}),
            "extra_response_keys": sorted(set(payload) - {"code"}),
            "recovered_from_latest_direct_response": True,
        },
        generation_success=True,
        secret_persisted=False,
    )
    base.atomic_json(manifest_path, manifest)
    print(f"GLM53_CONNECT2_RESPONSE_RECOVERED scene={scene_id}")
    return 0


if __name__ == "__main__":
    if "--recover-latest" in sys.argv:
        index = sys.argv.index("--recover-latest")
        raise SystemExit(recover_latest_direct_response(sys.argv[index + 1]))
    raise SystemExit(base.main())

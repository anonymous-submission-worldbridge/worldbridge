#!/usr/bin/env python3
"""Generate eight dense ordinary connected scenes with GLM-5.3 Flash."""

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


import ast
import json
from pathlib import Path
import sys

sys.path.insert(0, str((_BASELINE_PROJECT_ROOT / "baselines/tools")))
import baselines.methods.glm_flash.tools.generate_glm_flash_connect as base


OUTPUT = base.BASELINES / "annotations/glm53_flash/connect3"

SCENES = (
    {
        "scene_id": "rowhouse_living_dining",
        "brief": "a normal urban rowhouse living and dining room opening through the front entrance to a small stoop, planted sidewalk and continuous street of neighboring rowhouses",
        "palette": "warm white, medium oak, oatmeal, muted navy, brick red, black metal",
        "interior_program": "large sofa and two armchairs, layered cushions, rug, coffee and side tables, television console, bookcases, dining table with six chairs, entry console, coat and shoe storage, lamps, curtains, framed art, plants and small domestic accessories",
        "context_program": "stoop and railings, front planting, broad sidewalk, parked cars and bicycles, street trees and lamps, plus at least six detailed neighboring rowhouse or corner-shop facades enclosing both sides and the far background",
        "category": "residential",
    },
    {
        "scene_id": "apartment_kitchen_balcony",
        "brief": "an ordinary apartment kitchen and breakfast area opening to a furnished balcony overlooking a dense shared residential courtyard",
        "palette": "soft cream, pale oak, sage green, quartz white, stainless steel, terracotta",
        "interior_program": "full kitchen with base and wall cabinets, oven, cooktop, refrigerator, sink, breakfast peninsula and stools, small dining table, pendant lights, backsplash, shelves, crockery, countertop appliances, food containers, plants and curtains",
        "context_program": "balcony furniture and planters, railings, courtyard paths and benches, bicycles, shrubs and trees, and multiple surrounding apartment blocks with repeated windows, balconies and ground-floor doors on every visible side",
        "category": "residential",
    },
    {
        "scene_id": "suburban_family_room",
        "brief": "a conventional family room and casual dining space opening through patio doors to a modest backyard in a close suburban neighborhood",
        "palette": "ivory, walnut, warm gray, dusty blue, olive green, natural brick",
        "interior_program": "sectional sofa, armchair, media cabinet, books and toys, layered rug and tables, dining set, sideboard, floor and table lamps, curtains, radiator, pictures, plants and realistic small household clutter",
        "context_program": "patio table, barbecue, lawn and planting beds, fence and shed, neighboring two-story homes close behind the fence, side garages, visible rooflines, trees and a residential lane so no horizon opens into empty space",
        "category": "residential",
    },
    {
        "scene_id": "duplex_home_office_lounge",
        "brief": "a practical ground-floor duplex home office and lounge opening to a compact front garden and an ordinary dense residential lane",
        "palette": "off white, birch, charcoal, muted green, rust orange, brushed steel",
        "interior_program": "desk with monitor and storage, office chair, wall shelving full of books and files, sofa and lounge chair, rug, coffee table, console, task lamps, printer cabinet, entry bench, plants, artwork and small desk accessories",
        "context_program": "front path, low wall and gate, planting beds, bins and bicycles, parked compact cars, trees, and multiple neighboring duplex and small apartment facades on both sides and behind the camera-visible street",
        "category": "residential",
    },
    {
        "scene_id": "neighborhood_pharmacy",
        "brief": "an ordinary neighborhood pharmacy sales floor with an open glazed entrance to a busy mixed-use sidewalk",
        "palette": "clean white, pale birch, soft green, muted blue, stainless steel, charcoal",
        "interior_program": "several stocked wall and gondola display units, pharmacy counter with cabinets and screens, refrigerated case, checkout, basket stack, waiting chairs, consultation divider, ceiling lights, product groupings and price rails without text",
        "context_program": "continuous storefront frontage, sidewalk planters, bench, bicycle and street lamps, curb and parked cars, with at least six neighboring shop and apartment facades filling the left, right and far background without blank lots",
        "category": "retail",
    },
    {
        "scene_id": "local_grocery_market",
        "brief": "a compact everyday grocery and produce market with a broad entrance connected directly to a neighborhood shopping street",
        "palette": "warm white, natural timber, produce green, tomato red, kraft brown, dark metal",
        "interior_program": "dense produce islands with many individual crates and goods, stocked grocery shelves, beverage refrigerator, bread display, checkout counter, baskets, hanging lights, end caps and small practical retail details while keeping a central aisle",
        "context_program": "sidewalk produce crates, awning, bicycle, bollards and planters, parked delivery van and cars, street trees and a continuous row of detailed neighboring buildings and storefronts enclosing every wide view",
        "category": "retail",
    },
    {
        "scene_id": "casual_family_restaurant",
        "brief": "a modest casual family restaurant dining room with an open storefront leading to sidewalk seating and a lively ordinary commercial street",
        "palette": "cream plaster, honey oak, muted terracotta, forest green, charcoal, warm brass",
        "interior_program": "many dining tables and chairs, banquette seating, service counter and register, open shelving, table settings, pendant lights, wall art without text, plants, host stand and glimpses of a practical preparation area",
        "context_program": "several sidewalk tables, planters, awning, bicycle rack, street lamps and parked cars, backed by continuous mixed-use facades, upper windows and side streets with no empty exterior horizon",
        "category": "retail",
    },
    {
        "scene_id": "hardware_home_store",
        "brief": "a small ordinary neighborhood hardware and home-goods store with an open entrance onto a dense local main street",
        "palette": "warm gray, plywood, subdued orange, deep green, galvanized steel, black rubber",
        "interior_program": "multiple stocked shelving runs, pegboard-like wall displays without text, tool and paint-can forms, household goods, checkout counter, storage cabinets, product islands, baskets, ceiling lights and a clear central aisle",
        "context_program": "sidewalk display bins, restrained canopy, utility bicycle, bollards, planters and parked vehicle forms, surrounded by at least six detailed shop-house facades with windows, awnings, doors, rooflines and street trees",
        "category": "retail",
    },
)


def prompt_for(scene: dict[str, str]) -> str:
    return f"""You are the procedural scene-planning component of a 3D generation benchmark.
Create one HIGH-DETAIL, believable ordinary residential or neighborhood retail
environment. The richness target is a fully furnished townhouse interior, not a
minimal showroom. Avoid luxury, monumental, fantasy, gallery or resort aesthetics.

SCENE_ID: {scene['scene_id']}
CATEGORY: {scene['category']}
CONCEPT: {scene['brief']}
PALETTE: {scene['palette']}
INTERIOR PROGRAM: {scene['interior_program']}
SURROUNDING CONTEXT: {scene['context_program']}

Use one genuine shared-coordinate 3D environment:
- X left/right, Y indoor-to-outdoor, Z up.
- Interior is a conventional room approximately x=-6..6, y=-9..0, z=0..3.65.
- Exterior occupies x=-18..18, y=0..24.
- Preserve an open 2.2 m-wide entrance centered at x=0,y=0 below z=2.8 and
  a flush threshold. Keep a 1.25 m route through the doorway.
- Interior must be dense and coherent: at least five furnishing clusters, layered
  foreground/midground/background, detailed multi-part furniture, built-ins, trim,
  lighting, accessories and small objects. Spend at least 65 percent of semantic
  calls indoors. Major furniture must use semantic helpers, not one plain box.
- Design sightlines from rear room corners toward the exterior so a far camera can
  see a broad interior composition plus exterior depth through the same doorway.
- Exterior must never read as an empty plane. Enclose wide views with a continuous
  neighborhood: at least six surrounding building masses using api.building,
  repeated facade windows and doors, sidewalks/curbs, trees, planters, lamps,
  bicycles or parked vehicles. Put context on both sides and at y=14..24, but keep
  the central doorway sightline open. No blank lot or open horizon in any direction.
- Use unique descriptive names. Do not create text, signs, numbers or logos.
- No external assets, files, downloads, image textures, booleans, geometry nodes,
  physics, particles or simulations. Use only the API below.

Return exactly one JSON object containing a string field named "code". Harmless
metadata fields are tolerated, but no markdown or prose outside the JSON. The code
must define SCENE_SPEC and build_scene(api), import at most math, perform no file I/O,
and create materials before geometry. Use 130-230 high-level API calls.

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
api.building(name, location_xyz, size_xyz, facade_material, trim_material, glass_material)
api.parked_car(name, location_xyz, yaw_degrees, body_material, trim_material, glass_material)
api.tree(name, location_xyz, trunk_height, crown_radius, trunk_material, leaf_material)
api.lamp(name, location_xyz, height, pole_material, light_material)
api.art(name, location_xyz, scale_xyz, material, frame_material)
api.rug(name, location_xyz, size_xy, material)
api.road(name, location_xyz, size_xyz, road_material, line_material)

SCENE_SPEC must be a plain dictionary containing scene_id, concept, palette,
entrance_clear_width_m, object_intent (at least 12 concise items), scene_category,
interior_detail_level="high", and context_density="dense". The harness supplies
the main room shell and also adds a secondary neighborhood context pass; do not
duplicate the room shell. Do create the semantic interior and distinct scene-specific
exterior context. Cameras, world/render settings, saving and exporting belong to the
harness and must not appear in generated code.
"""


def tolerant_extract_code(events_path: Path):
    events = []
    text_parts = []
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        events.append(event)
        if event.get("type") == "text":
            text_parts.append(event.get("part", {}).get("text", ""))
    text = "".join(text_parts).strip()
    decoder = json.JSONDecoder()
    payload = None
    scene_spec = None
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            candidate, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        if (
            isinstance(candidate, dict)
            and isinstance(candidate.get("scene_id"), str)
            and isinstance(candidate.get("object_intent"), list)
        ):
            scene_spec = candidate
        if isinstance(candidate, dict) and isinstance(candidate.get("code"), str):
            payload = candidate
            break
    if payload is None:
        for marker in ("```python", "```py"):
            start = text.find(marker)
            if start < 0:
                continue
            start = text.find("\n", start) + 1
            end = text.find("```", start)
            if start > 0 and end > start:
                payload = {"code": text[start:end].strip()}
                break
    if payload is None:
        raise ValueError(
            "response did not contain a JSON code field or Python code fence"
        )
    code = payload["code"].rstrip() + "\n"
    # GLM occasionally emits the requested SCENE_SPEC as a harmless leading
    # JSON object instead of putting it inside the code string.  Reattach that
    # model-produced metadata locally so the response can be reused without a
    # second Coding Plan call.
    if "SCENE_SPEC" not in code and scene_spec is not None:
        lines = code.splitlines()
        insert_at = 1 if lines and lines[0].startswith(("import ", "from ")) else 0
        lines[insert_at:insert_at] = ["", f"SCENE_SPEC = {scene_spec!r}", ""]
        code = "\n".join(lines).rstrip() + "\n"
    # Another observed GLM formatting variant defines a zero-argument
    # SCENE_SPEC function.  Materialize its returned model-authored dictionary
    # after definitions, again avoiding a redundant provider request.
    parsed_tree = ast.parse(code)
    if any(
        isinstance(node, ast.FunctionDef) and node.name == "SCENE_SPEC"
        for node in parsed_tree.body
    ):
        code = code.rstrip() + "\n\nSCENE_SPEC = SCENE_SPEC()\n"
    metadata = {
        "event_types": [event.get("type") for event in events],
        "session_ids": sorted(
            {event.get("sessionID") for event in events if event.get("sessionID")}
        ),
        "extra_response_keys": sorted(set(payload) - {"code"}),
        "scene_spec_recovered_from_response": "SCENE_SPEC" not in payload["code"],
    }
    return code, metadata


ORIGINAL_VALIDATE = base.validate_code


def validate_code(code: str, scene_id: str):
    spec = ORIGINAL_VALIDATE(code, scene_id)
    tree = ast.parse(code)
    namespace = {
        "__builtins__": {
            "__import__": __import__,
            "range": range,
            "enumerate": enumerate,
            "zip": zip,
            "len": len,
            "min": min,
            "max": max,
            "round": round,
            "abs": abs,
            "str": str,
            "float": float,
            "int": int,
            "list": list,
            "tuple": tuple,
        }
    }
    exec(compile(tree, "<glm53_connect3_scene>", "exec"), namespace)

    class DryAPI:
        def __getattr__(self, name):
            return lambda *args, **kwargs: str(args[0]) if args else name

    namespace["build_scene"](DryAPI())
    if (
        spec.get("interior_detail_level") != "high"
        or spec.get("context_density") != "dense"
    ):
        raise ValueError("scene detail/context metadata is incomplete")
    if len(spec.get("object_intent", [])) < 12:
        raise ValueError("object_intent is too sparse")
    return spec


base.DEFAULT_OUTPUT = OUTPUT
base.SCENES = SCENES
base.prompt_for = prompt_for
base.extract_code = tolerant_extract_code
base.validate_code = validate_code


if __name__ == "__main__":
    raise SystemExit(base.main())

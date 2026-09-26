# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]

import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from worldbridge.llm_config import (
    complete_text,
    describe_llm_exception,
    get_llm_config,
    make_openai_client,
)

INPUT_MANIFEST = Path("./output/urban/manifest_scene_urban.json")
OUTPUT_PARAMS = Path("./output/urban/urban_params.json")

# ─── CROSSROADS GEOMETRY CONSTANTS ────────────────────────────────────────────
_R = 4.5  # road half-width
_SW = 3.5  # sidewalk width
_FW = 2.5  # roadside flower-belt width
_ARM = 50.0  # arm length from intersection centre to zone edge
_S1 = _R + _SW  # 8.0  – outer sidewalk edge
_G1 = _R + _SW + _FW  # 10.5 – inner zone boundary
_LC = _R / 2  # 2.25 – lane-centre offset

# Pre-validated safe tree positions inside the NE park zone
_PARK_TREE_POOL = [
    (22, 14, 42, 1.00),
    (35, 14, 137, 1.08),
    (44, 14, 256, 0.96),
    (53, 16, 381, 1.12),
    (53, 38, 512, 1.04),
    (50, 50, 619, 1.10),
    (38, 50, 734, 0.98),
    (24, 50, 851, 1.06),
    (20, 38, 923, 1.00),
    (25, 39, 1044, 1.08),
    (44, 38, 1157, 1.02),
    (54, 25, 1261, 0.96),
    (32, 52, 1369, 1.10),
    (19, 52, 1471, 1.04),
]

_SHRUB_POSITIONS = [
    (-20, 20, 3),
    (-22, 45, 7),
    (-38, 20, 11),
    (-36, 48, 15),
    (-48, 32, 19),
    (-26, 38, 23),
    (-44, 22, 27),
]

_DENSITY_TREES = {"none": 0, "sparse": 4, "standard": 6, "lush": 8}
_DENSITY_BENCHES = {"sparse": 2, "standard": 3, "lush": 5}
_DENSITY_BINS = {"sparse": 1, "standard": 2, "lush": 3}
_DENSITY_SHRUBS = {"sparse": 3, "standard": 5, "lush": 7}


def _compute_zone_params(manifest):
    """
    Deterministically compute per-zone asset parameters from the manifest.
    Zone positions are derived from the fixed crossroads geometry.
    Asset counts/toggles honour density hints from the manifest.
    """
    zones_mf = manifest.get("zones", {})

    # ── NW: Residential ──────────────────────────────────────────────────────
    nw_mf = zones_mf.get("NW", {})
    density_nw = nw_mf.get("density", "standard")
    n_shrubs = _DENSITY_SHRUBS.get(density_nw, 5)
    zone_NW = {
        "role": "residential",
        "ground": nw_mf.get("ground", "marble"),
        "fence_style": nw_mf.get("fence_style", "iron"),
        "compound": {
            "E": -(_G1 + 1.5),  # -12.0
            "W": -55.0,
            "S": _G1 + 1.5,  #  12.0
            "N": 58.0,
        },
        "apartment": {
            "CX": -33.5,
            "CY": 34.0,
            "W": 30.0,
            "D": 14.0,
            "floors": 6,
        },
        "shrubs": [list(p) for p in _SHRUB_POSITIONS[:n_shrubs]],
        "gate_path": True,
    }

    # ── NE: Park ─────────────────────────────────────────────────────────────
    ne_mf = zones_mf.get("NE", {})
    tree_density = ne_mf.get("tree_density", "lush")
    n_trees = _DENSITY_TREES.get(tree_density, 10)
    n_trees = int(ne_mf.get("tree_count", n_trees))
    n_trees = max(0, min(n_trees, len(_PARK_TREE_POOL)))
    bench_count = int(ne_mf.get("bench_count", _DENSITY_BENCHES.get(tree_density, 5)))
    bin_count = int(ne_mf.get("bin_count", _DENSITY_BINS.get(tree_density, 3)))

    _all_benches = [
        [18.5, 26.0, math.pi / 2],
        [26.0, 38.0, 0.0],
        [40.0, 24.0, math.pi / 2],
        [44.0, 40.0, 0.0],
        [16.0, 44.0, 0.0],
    ]
    _all_bins = [[22.0, 32.0], [38.0, 46.0], [48.0, 28.0]]

    zone_NE = {
        "role": "park",
        "ground": ne_mf.get("ground", "grass"),
        "trees": [
            {"x": t[0], "y": t[1], "seed": t[2], "scale": t[3]}
            for t in _PARK_TREE_POOL[:n_trees]
        ],
        "pavilion": [34, 32] if ne_mf.get("has_pavilion", True) else None,
        "bandstand": [22, 22] if ne_mf.get("has_bandstand", True) else None,
        "fountain": [26, 20] if ne_mf.get("has_fountain", True) else None,
        "flower_beds": [[45, 16, 5, 3], [50, 42, 5, 3], [20, 44, 4, 2.5]],
        "benches": _all_benches[: max(0, min(bench_count, 5))],
        "bins": _all_bins[: max(0, min(bin_count, 3))],
    }

    # ── SE: Commercial ────────────────────────────────────────────────────────
    se_mf = zones_mf.get("SE", {})
    has_delivery_hub = bool(se_mf.get("has_delivery_hub", False))
    # The complete delivery row occupies the shop frontage.  Reserve the zone
    # for it instead of allowing generic shop shells or street props to overlap.
    shop_count = 0 if has_delivery_hub else int(se_mf.get("shop_count", 3))
    _all_shops = [
        {"x": round(_G1 + 10.0, 2), "y": -17.0, "mat": "w", "awning": "r"},
        {"x": round(_G1 + 10.0, 2), "y": -32.0, "mat": "r", "awning": "g"},
        {"x": round(_G1 + 10.0, 2), "y": -47.0, "mat": "b", "awning": "b"},
    ]
    zone_SE = {
        "role": "commercial",
        "ground": se_mf.get("ground", "marble"),
        "shops": _all_shops[: max(0, min(shop_count, 3))],
        "delivery_hub": [22.0, -35.0, round(math.pi / 2, 4)]
        if has_delivery_hub
        else None,
        "bicycle_station": [round(_G1 + 5.0, 2), -21.0, 0.0]
        if se_mf.get("has_bicycle_station", True) and not has_delivery_hub
        else None,
        "kiosk": [round(_S1 - _SW / 2, 2), -38.0, -round(math.pi / 2, 4), 0.85]
        if se_mf.get("has_kiosk", True) and not has_delivery_hub
        else None,
        "phone_booth": [round(_G1 + 1.5, 2), -14.0, -round(math.pi / 2, 4)]
        if se_mf.get("has_phone_booth", True) and not has_delivery_hub
        else None,
        "benches": []
        if has_delivery_hub
        else [
            [round(_G1 + 2.0, 2), -27.0, round(math.pi / 2, 4)],
            [round(_G1 + 2.0, 2), -42.0, round(math.pi / 2, 4)],
        ],
        "bins": [] if has_delivery_hub else [[round(_G1 + 2.0, 2), -34.0]],
    }

    # ── SW: Empty ─────────────────────────────────────────────────────────────
    sw_mf = zones_mf.get("SW", {})
    zone_SW = {
        "role": "empty",
        "ground": sw_mf.get("ground", "grass"),
    }

    return {"NW": zone_NW, "NE": zone_NE, "SE": zone_SE, "SW": zone_SW}


def _build_scene_plan(zones, road):
    """Build the stable, Blender-independent asset/instance portion of schema v2."""
    apartment = zones["NW"]["apartment"]
    assets = {
        "residential.apartment.v1": {
            "kind": "procedural_collection",
            "builder": "build_apartment_master",
            "variant": {
                "width": apartment["W"],
                "depth": apartment["D"],
                "floors": apartment["floors"],
            },
            "version": 1,
        },
        "street.streetlight.day": {
            "kind": "blend_collection",
            "builder": "place_streetlight",
            "variant": {"emission": False},
            "version": 1,
        },
        "street.trafficlight.v1": {
            "kind": "blend_collection",
            "builder": "place_trafficlight",
            "variant": {},
            "version": 1,
        },
        "furniture.bench.classic": {
            "kind": "blend_collection",
            "builder": "place_bench_classic",
            "variant": {},
            "version": 1,
        },
        "furniture.bin.domed": {
            "kind": "blend_collection",
            "builder": "place_bin_domed",
            "variant": {},
            "version": 1,
        },
    }
    instances = [
        {
            "instance_id": "residential.apartment.000",
            "asset_id": "residential.apartment.v1",
            "collection": "Residential",
            "transform": {
                "location": [apartment["CX"], apartment["CY"], 0.0],
                "rotation_euler": [0.0, 0.0, 0.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "metadata": {"zone": "NW", "role": "residential"},
        }
    ]
    if road.get("has_traffic_lights", True):
        for index in range(4):
            instances.append(
                {
                    "instance_id": f"street.trafficlight.{index:03d}",
                    "asset_id": "street.trafficlight.v1",
                    "collection": "TrafficLights",
                }
            )
    if road.get("has_street_lamps", True):
        for index in range(48):
            instances.append(
                {
                    "instance_id": f"street.streetlight.{index:03d}",
                    "asset_id": "street.streetlight.day",
                    "collection": "Lamps",
                }
            )
    delivery = zones["SE"].get("delivery_hub")
    if delivery:
        assets["commercial.delivery_hub.reference.v1"] = {
            "kind": "procedural_collection",
            "builder": "build_delivery_reference_row",
            "variant": {
                "assets": ["food_delivery_locker", "parcel_locker", "parcel_station"],
                "include_site": False,
            },
            "version": 1,
        }
        instances.append(
            {
                "instance_id": "commercial.delivery_hub.000",
                "asset_id": "commercial.delivery_hub.reference.v1",
                "collection": "Commercial",
                "transform": {
                    "location": [delivery[0], delivery[1], 0.0],
                    "rotation_euler": [0.0, 0.0, delivery[2]],
                    "scale": [1.0, 1.0, 1.0],
                },
                "metadata": {"zone": "SE", "role": "delivery_hub"},
            }
        )
    return assets, instances


def _atmosphere_to_render(manifest, client, model_name):
    """
    Use a lightweight LLM call to translate atmosphere → render parameters.
    Falls back to sensible defaults if the call fails.
    """
    _defaults = {
        "sun_elevation": 40.0,
        "sun_rotation": 210.0,
        "sky_strength": 1.0,
        "exposure": 1.1,
        "samples": 256,
        "fog_density": 0.0,
    }

    atm = manifest.get("atmosphere", {})
    if not atm:
        return _defaults
    if client is None:
        return _defaults

    system_prompt = """
You translate an urban scene atmosphere description into render parameters.
Return ONLY a raw JSON object with these keys (no markdown):
{
  "sun_elevation": float (degrees, 0-90),
  "sun_rotation": float (degrees, azimuth 0-360),
  "sky_strength": float (0.5-2.0),
  "exposure": float (0.8-2.5),
  "samples": int (128|256|512|1024),
  "fog_density": float (0.0-0.025)
}

Rules:
- time_of_day → sun_elevation: dawn=8, morning=25, noon=65, afternoon=40, evening=12, night=0
- weather=sunny → fog=0.0; partly_cloudy → 0.002; overcast → 0.008; rainy → 0.015; foggy → 0.022
- lighting_mood=dramatic or moody → samples=512; neon → samples=1024; else 256
- night → exposure≥2.0; fog>0.01 → boost exposure by 0.3
- sun_rotation: morning≈90, noon≈180, afternoon≈210, evening≈270
"""

    atm_str = json.dumps(atm, indent=2)
    try:
        from worldbridge.llm_config import complete_text

        result = complete_text(
            client,
            model=model_name,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Atmosphere:\n{atm_str}"},
            ],
            temperature=0.1,
        )
        result = result.strip()
        if result.startswith("```json"):
            result = result[7:]
        if result.startswith("```"):
            result = result[3:]
        if result.endswith("```"):
            result = result[:-3]
        parsed = json.loads(result.strip())
        return {**_defaults, **parsed}
    except Exception as e:
        print(f"[Urban Resolver] atmosphere→render fallback: {e}")
        return _defaults


class UrbanParameterResolver:
    def __init__(self, api_key=None, base_url=None, model_name=None):
        try:
            config = get_llm_config(default_model=model_name)
            self.config = config
            self.client = make_openai_client(config, api_key=api_key, base_url=base_url)
            self.model_name = model_name or config.model
        except RuntimeError as exc:
            # Crossroads layout is deterministic; an API key is only an optional
            # atmosphere enhancement and must not block --from-plan execution.
            print(f"[Urban Resolver] deterministic mode: {exc}")
            self.config = None
            self.client = None
            self.model_name = model_name or "deterministic"

    def resolve_crossroads(self, manifest):
        """
        Resolve a crossroads_4zone manifest into per-zone + render parameters.
        Zone layout is deterministic; only render params use an LLM call.
        """
        render = _atmosphere_to_render(manifest, self.client, self.model_name)
        zones = _compute_zone_params(manifest)
        road = manifest.get("road", {})

        assets, instances = _build_scene_plan(zones, road)
        params = {
            "schema_version": 2,
            "scene_type": "crossroads_4zone",
            "seed": 42,
            "output_dir": f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_pipeline",
            "geometry": {
                "R": _R,
                "SW": _SW,
                "FW": _FW,
                "ARM": _ARM,
                "S1": _S1,
                "G1": _G1,
                "LC": _LC,
            },
            "zones": zones,
            "road": {
                "has_traffic_lights": road.get("has_traffic_lights", True),
                "has_crosswalks": road.get("has_crosswalks", True),
                "has_lane_markings": road.get("has_lane_markings", True),
                "has_bus_stop": road.get("has_bus_stop", True),
                "has_street_lamps": road.get("has_street_lamps", True),
                "has_roadside_flower_beds": road.get("has_roadside_flower_beds", True),
            },
            "render": {
                "sun_elevation": render["sun_elevation"],
                "sun_rotation": render["sun_rotation"],
                "sky_strength": render["sky_strength"],
                "exposure": render["exposure"],
                "samples": int(render["samples"]),
                "fog_density": render["fog_density"],
            },
            "assets": assets,
            "instances": instances,
            "unique_geometry": [],
        }
        return params

    def resolve_flat(self, manifest_data, user_prompt=None):
        """
        Legacy: translate a flat urban manifest into gin parameters (existing logic).
        """
        manifest_str = json.dumps(manifest_data, indent=2)
        user_prompt_section = (
            f"\n### ORIGINAL USER PROMPT:\n{user_prompt}\n\n" if user_prompt else ""
        )

        system_prompt = f"""
You are the **Urban Parameter Resolver** (Agent 2) for WorldBridge urban scene generation.
Your task is to translate a qualitative Urban Manifest into precise quantitative parameters.

### INPUT MANIFEST:
{user_prompt_section}{manifest_str}

### OUTPUT FORMAT:
Return ONLY a raw JSON object (no markdown). All integer values must be integers, not floats.

{{
    "scene_type": "flat",
    "compose_urban.block_extent": float,
    "compose_urban.road_width": float,
    "compose_urban.sidewalk_width": float,
    "compose_urban.curb_height": float,
    "compose_urban.min_building_height": float,
    "compose_urban.max_building_height": float,
    "_outdoor_assets.n_street_lamps": int,
    "_outdoor_assets.has_bus_stop": bool,
    "_outdoor_assets.n_bike_racks": int,
    "_outdoor_assets.has_fire_hydrant": bool,
    "_outdoor_assets.n_trees": int,
    "_outdoor_assets.tree_season": "string",
    "_outdoor_assets.n_grass_tufts": int,
    "_outdoor_assets.n_shrubs": int,
    "_outdoor_assets.n_flower_plants": int,
    "_outdoor_assets.has_fountain": bool,
    "_outdoor_assets.has_sculpture": bool,
    "_outdoor_assets.n_planters": int,
    "_outdoor_assets.n_vehicles": int,
    "_outdoor_assets.n_pedestrians": int,
    "_outdoor_assets.n_benches": int,
    "_outdoor_assets.n_trash_bins": int,
    "_outdoor_assets.has_traffic_lights": bool,
    "_outdoor_assets.has_traffic_signs": bool,
    "configure_render_cycles.exposure": float,
    "configure_render_cycles.num_samples": int,
    "nishita_lighting.sun_elevation": float,
    "atmosphere.fog_density": float
}}
"""

        try:
            content = complete_text(
                self.client,
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": "Resolve all parameters."},
                ],
                temperature=0.1,
            )
            content = content.strip()
            for prefix in ("```json", "```"):
                if content.startswith(prefix):
                    content = content[len(prefix) :]
            if content.endswith("```"):
                content = content[:-3]
            return json.loads(content.strip())
        except Exception as e:
            print("API Error in Urban Parameter Resolver (flat):")
            print(describe_llm_exception(e))
            return None


def main():
    user_prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    if not INPUT_MANIFEST.exists():
        print(f"Error: {INPUT_MANIFEST} not found. Please run the Urban Planner first.")
        sys.exit(1)

    manifest_data = json.loads(INPUT_MANIFEST.read_text(encoding="utf-8"))
    print(f"[Urban Resolver] Read manifest from: {INPUT_MANIFEST}")

    # Deterministic execution path for environments without an LLM planner.
    # It deliberately does not overwrite the user's existing manifest file.
    if "crossroads" in user_prompt.casefold() and "scene_type" not in manifest_data:
        print(
            "[Urban Resolver] Using deterministic crossroads manifest from user prompt"
        )
        manifest_data = {
            "scene_type": "crossroads_4zone",
            "atmosphere": {
                "time_of_day": "afternoon",
                "weather": "sunny",
                "lighting_mood": "bright",
                "season": "summer",
            },
            "zones": {},
            "road": {},
        }

    resolver = UrbanParameterResolver()
    scene_type = manifest_data.get("scene_type", "flat")

    if scene_type == "crossroads_4zone":
        print("[Urban Resolver] Resolving crossroads_4zone layout ...")
        params = resolver.resolve_crossroads(manifest_data)
    else:
        print("[Urban Resolver] Resolving flat urban layout (legacy) ...")
        params = resolver.resolve_flat(manifest_data, user_prompt)

    if params is None:
        print("Failed to resolve urban parameters.")
        sys.exit(1)

    if output_dir and params.get("scene_type") == "crossroads_4zone":
        params["output_dir"] = str(Path(output_dir).resolve())

    OUTPUT_PARAMS.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PARAMS.write_text(
        json.dumps(params, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    print(f"[Urban Resolver] Parameters saved to: {OUTPUT_PARAMS}")
    print(json.dumps(params, indent=4, ensure_ascii=False))


if __name__ == "__main__":
    main()

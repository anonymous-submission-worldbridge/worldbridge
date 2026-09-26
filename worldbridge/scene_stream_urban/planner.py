import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from worldbridge.llm_config import (
    complete_text,
    describe_llm_exception,
    get_llm_config,
    make_openai_client,
)

OUTPUT_MANIFEST = Path("./output/urban/manifest_scene_urban.json")


class UrbanEnvironmentPlanner:
    def __init__(self, api_key=None, base_url=None, model_name=None):
        config = get_llm_config(default_model=model_name)
        self.config = config
        self.client = make_openai_client(config, api_key=api_key, base_url=base_url)
        self.model_name = model_name or config.model

    def infer_manifest(self, user_instruction):
        system_prompt = """
You are the **Urban Environment Planner** (Agent 1) for a procedural city scene generation system.
Your goal is to parse a user's natural-language description of an outdoor urban street scene and produce a structured JSON manifest.

### SCENE TYPES

**crossroads_4zone** (default, recommended):
  A 4-way crossroads that divides the surrounding area into 4 quadrants.
  Use this type whenever the user mentions crossroads, intersection, zones, quadrants,
  residential/park/commercial districts, or simply asks for a rich urban street scene.

  Default zone layout (NW/NE/SE/SW from the intersection center):
    NW — Residential : marble ground, iron fence compound, apartment block, shrubs, stone paths
    NE — Park        : grass lawn, tall trees, flower beds, pavilion, bandstand, fountain, benches
    SE — Commercial  : marble ground, shops with awnings, bicycle station, kiosk, phone booth,
                       or a detailed delivery hub (food locker + parcel locker + parcel station)
    SW — Empty       : clean grass lawn (reserved for future use)

**flat** (legacy):
  A single-axis urban block or street (output only when user explicitly describes a single
  street segment without zoning, e.g. "a quiet alley" or "a one-way highway").

---
### WHEN TO USE crossroads_4zone

Default to this type when:
- User mentions "crossroads", "intersection", "crossroad", "4 zones", "zones", "quadrant"
- User lists multiple district types (residential + park + commercial etc.)
- User gives no specific layout → default to crossroads_4zone for richness

Only use "flat" when the user clearly describes a single-axis scene.

---
### VALID FIELD VALUES (shared)

atmosphere.time_of_day  : "dawn" | "morning" | "noon" | "afternoon" | "evening" | "night"
atmosphere.weather      : "sunny" | "partly_cloudy" | "overcast" | "rainy" | "foggy"
atmosphere.lighting_mood: "bright" | "warm" | "cool" | "dramatic" | "moody" | "neon"
atmosphere.season       : "spring" | "summer" | "autumn" | "winter"

zones.*.density         : "sparse" | "standard" | "lush"
zones.NE.tree_density   : "none" | "sparse" | "standard" | "lush"
zones.NE.bench_count    : integer 1-6
zones.NE.bin_count      : integer 1-4
zones.NE.has_pavilion   : true/false
zones.NE.has_bandstand  : true/false
zones.NE.has_fountain   : true/false
zones.SE.shop_count     : integer 1-3
zones.SE.has_bicycle_station : true/false
zones.SE.has_kiosk      : true/false
zones.SE.has_phone_booth: true/false
zones.SE.has_delivery_hub: true/false (set true when the user asks for parcel lockers, food delivery lockers, parcel pickup stations or delivery facilities)
zones.NW.fence_style    : "iron" | "brick" | "slat"
zones.NW.density        : "standard" (only one apartment block)

---
### OUTPUT FORMAT

For crossroads_4zone:
{
  "scene_type": "crossroads_4zone",
  "atmosphere": {
    "time_of_day": "string",
    "weather": "string",
    "lighting_mood": "string",
    "season": "string"
  },
  "zones": {
    "NW": {
      "role": "residential",
      "ground": "marble",
      "fence_style": "iron",
      "density": "standard"
    },
    "NE": {
      "role": "park",
      "ground": "grass",
      "tree_density": "lush",
      "has_pavilion": true,
      "has_bandstand": true,
      "has_fountain": true,
      "bench_count": 5,
      "bin_count": 3
    },
    "SE": {
      "role": "commercial",
      "ground": "marble",
      "shop_count": 3,
      "has_bicycle_station": true,
      "has_kiosk": true,
      "has_phone_booth": true,
      "has_delivery_hub": false
    },
    "SW": {
      "role": "empty",
      "ground": "grass"
    }
  },
  "road": {
    "has_traffic_lights": true,
    "has_crosswalks": true,
    "has_lane_markings": true,
    "has_bus_stop": true,
    "has_street_lamps": true,
    "has_roadside_flower_beds": true
  }
}

For flat (legacy):
{
  "scene_type": "flat",
  "atmosphere": { ... },
  "block": { "type": "string", "scale": "string" },
  "buildings": { ... },
  "vegetation": { ... },
  "street_furniture": { ... },
  "traffic": { ... },
  "surface_condition": { ... }
}

Return ONLY the raw JSON object. No markdown formatting.
"""

        try:
            content = complete_text(
                self.client,
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": f"User Instruction: {user_instruction}",
                    },
                ],
                temperature=0.7,
            )
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            return content.strip()
        except Exception as e:
            print("API Error in Urban Planner:")
            print(
                f"provider={self.config.provider}, "
                f"base_url={self.config.base_url or 'OpenAI default'}, "
                f"model={self.model_name}"
            )
            print(describe_llm_exception(e))
            return None


def main():
    planner = UrbanEnvironmentPlanner()

    user_prompt = sys.argv[1] if len(sys.argv) > 1 else ""
    if not user_prompt:
        print("Warning: No user prompt provided.")
    else:
        print(f"[Urban Planner] User Prompt: {user_prompt}")

    json_result = planner.infer_manifest(user_prompt)

    if json_result:
        try:
            parsed_data = json.loads(json_result)
            OUTPUT_MANIFEST.parent.mkdir(parents=True, exist_ok=True)
            OUTPUT_MANIFEST.write_text(
                json.dumps(parsed_data, indent=4, ensure_ascii=False),
                encoding="utf-8",
            )
            scene_type = parsed_data.get("scene_type", "unknown")
            print(f"[Urban Planner] scene_type: {scene_type}")
            print("-" * 40)
            print(json.dumps(parsed_data, indent=4, ensure_ascii=False))
            print("-" * 40)
            print(f"Urban manifest saved to: {OUTPUT_MANIFEST}")
        except json.JSONDecodeError:
            print("Raw output:", json_result)
            print("Error: Urban Planner output is not valid JSON.")
            raise SystemExit(1)
    else:
        print("Failed to generate urban manifest.")
        raise SystemExit(1)


if __name__ == "__main__":
    main()

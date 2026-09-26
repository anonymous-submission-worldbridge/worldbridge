from pathlib import Path
import sys
import types


# These deterministic resolver tests do not exercise an LLM.  Keep them usable
# in Blender/minimal CI environments where optional HTTP client packages are
# intentionally absent.
if "worldbridge.llm_config" not in sys.modules:
    llm_stub = types.ModuleType("worldbridge.llm_config")
    llm_stub.complete_text = lambda *args, **kwargs: "{}"
    llm_stub.describe_llm_exception = str
    llm_stub.get_llm_config = lambda *args, **kwargs: None
    llm_stub.make_openai_client = lambda *args, **kwargs: None
    sys.modules["worldbridge.llm_config"] = llm_stub

from worldbridge.scene_stream_urban.resolver import (
    _build_scene_plan,
    _compute_zone_params,
)


ROOT = Path(__file__).resolve().parents[1]


def test_delivery_hub_reserves_commercial_frontage_and_enters_scene_plan():
    zones = _compute_zone_params(
        {
            "zones": {
                "SE": {
                    "has_delivery_hub": True,
                    "has_bicycle_station": True,
                    "has_kiosk": True,
                    "has_phone_booth": True,
                }
            }
        }
    )
    commercial = zones["SE"]
    assert commercial["delivery_hub"] == [22.0, -35.0, 1.5708]
    assert commercial["shops"] == []
    assert commercial["bicycle_station"] is None
    assert commercial["kiosk"] is None
    assert commercial["phone_booth"] is None
    assets, instances = _build_scene_plan(zones, {})
    assert (
        assets["commercial.delivery_hub.reference.v1"]["builder"]
        == "build_delivery_reference_row"
    )
    assert any(
        item["asset_id"] == "commercial.delivery_hub.reference.v1" for item in instances
    )


def test_delivery_is_opt_in_and_live_source_adapter_is_present():
    zones = _compute_zone_params({"zones": {"SE": {}}})
    assert zones["SE"]["delivery_hub"] is None
    assets, instances = _build_scene_plan(zones, {})
    assert "commercial.delivery_hub.reference.v1" not in assets
    assert not any(
        item.get("asset_id") == "commercial.delivery_hub.reference.v1"
        for item in instances
    )

    adapter = (ROOT / "scripts/urban_assets.py").read_text(encoding="utf8")
    generator = (ROOT / "scripts/generate_urban_v3_delivery.py").read_text(
        encoding="utf8"
    )
    assert "def build_delivery_reference_row" in adapter
    assert "generate_urban_v3_delivery.py" in adapter
    assert "def build_food_delivery_locker" in generator
    assert "def build_parcel_locker" in generator
    assert "def build_delivery_station" in generator
    assert "bpy.data.libraries.load" not in generator

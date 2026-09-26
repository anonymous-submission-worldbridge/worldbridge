import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from worldbridge.urban.core import TOPOLOGIES, generate_descriptor, validate_descriptor


def test_same_seed_is_exactly_reproducible():
    assert generate_descriptor(42, "offset") == generate_descriptor(42, "offset")


def test_topology_families_are_valid_and_distinct():
    plans = [
        generate_descriptor(100 + i, topology) for i, topology in enumerate(TOPOLOGIES)
    ]
    assert all(not validate_descriptor(plan) for plan in plans)
    assert len({plan["fingerprint"] for plan in plans}) == len(TOPOLOGIES)
    assert {plan["road_topology"] for plan in plans} == set(TOPOLOGIES)


def test_all_regions_expose_integration_contract():
    descriptor = generate_descriptor(99, "four_way")
    assert {p["zone"] for p in descriptor["parcels"]} == {
        "commercial",
        "residential",
        "park",
        "leisure",
    }
    for parcel in descriptor["parcels"]:
        config = parcel["regional_config"]
        assert {
            "region_boundary",
            "orientation_deg",
            "road_facing_direction",
            "seed",
            "design_language",
        } <= config.keys()

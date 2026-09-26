"""Pure-Python specification for bounded Full-13 direct references."""

DIRECT_VALIDATIONS = {
    "direct_civic": {
        "shot": "school_library_shared_street",
        "layers": (
            "education_buildings",
            "artificial_lake",
            "public_safety",
            "full14_unique_urban_fabric",
            "full14_semantic_interiors",
            "full14_public_realm",
        ),
    },
    "direct_commercial": {
        "shot": "commercial_far",
        "layers": (
            "commercial_services",
            "health",
            "full14_unique_urban_fabric",
            "full14_semantic_interiors",
            "full14_public_realm",
        ),
    },
    "direct_residential": {
        "shot": "residential_far",
        "layers": (
            "river3_residential",
            "all45_unique_buildings",
            "residential_delivery",
            "full14_public_realm",
        ),
    },
    "direct_industrial_safety": {
        "shot": "industrial_far",
        "layers": (
            "industrial",
            "public_safety",
            "all44_leisure",
            "full14_public_realm",
        ),
    },
    "direct_park_lake": {
        "shot": "artificial_lake_high",
        "layers": (
            "river5_nature",
            "park_leisure_support",
            "artificial_lake",
            "full14_public_realm",
        ),
    },
    "direct_diagonal_street": {
        "shot": "diagonal_road_near",
        "layers": (
            "commercial_services",
            "education_buildings",
            "full14_unique_urban_fabric",
            "full14_public_realm",
        ),
    },
}

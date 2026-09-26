import json

import pytest

from worldbridge.postprocess.dynamics_schema import (
    DEFAULT_CONFIG,
    load_config,
    validate_config,
)


def test_default_dynamics_config_is_valid_and_static_pipeline_is_opt_in():
    validate_config(DEFAULT_CONFIG)
    assert DEFAULT_CONFIG["timeline"]["fps"] == 24
    assert set(DEFAULT_CONFIG["effects"]) == {"vehicles", "wind", "river", "fountain"}


def test_partial_config_deep_merges_without_losing_other_effects(tmp_path):
    path = tmp_path / "dynamics.json"
    path.write_text(
        json.dumps({"effects": {"wind": {"angle_degrees": 4.5}}}), encoding="utf-8"
    )
    config = load_config(path)
    assert config["effects"]["wind"]["angle_degrees"] == 4.5
    assert config["effects"]["vehicles"]["enabled"] is True
    assert config["render"]["resolution_x"] == 1280


def test_invalid_timeline_and_vehicle_route_are_rejected(tmp_path):
    bad_timeline = tmp_path / "bad_timeline.json"
    bad_timeline.write_text(
        json.dumps({"timeline": {"frame_start": 10, "frame_end": 10}}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="frame_end"):
        load_config(bad_timeline)

    bad_route = tmp_path / "bad_route.json"
    bad_route.write_text(
        json.dumps(
            {
                "effects": {
                    "vehicles": {"routes": [{"object": "car", "points": [[0, 0]]}]}
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="points"):
        load_config(bad_route)

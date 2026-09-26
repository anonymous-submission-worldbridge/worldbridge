#!/usr/bin/env python3
"""Full-13 OpenEXR validator using the proven native-float implementation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "scripts/process_urban_v1_full_12_exr.py"
spec = importlib.util.spec_from_file_location("full14_exr_base", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError(f"Cannot import {BASE_PATH}")
base = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = base
spec.loader.exec_module(base)

base.REVISION = "urban_v1_full_14"
base.CITY = (ROOT / "infinigen/outputs/outdoor_full_demo/urban_v1_full_14").resolve()
base.ASSET_LAYERS = (
    "river5_nature",
    "river3_residential",
    "all45_unique_buildings",
    "all44_leisure",
    "commercial_services",
    "residential_delivery",
    "park_leisure_support",
    "artificial_lake",
    "education_buildings",
    "public_safety",
    "health",
    "industrial",
    "full14_unique_urban_fabric",
    "full14_semantic_interiors",
    "full14_public_realm",
)
base.LAYERS = ("base", *base.ASSET_LAYERS)


def convert_blender45_bundle(
    input_token: str,
    output_token: str,
    layer: str,
    width: int,
    height: int,
):
    """Promote Blender 4.5 multilayer channels to named multipart EXR.

    The operation copies the decoded float arrays exactly and then reopens the
    result through the same strict bundle validator used by every final frame.
    """
    source = base.inside_city(input_token, must_exist=True)
    output = base.inside_city(output_token)
    color_name, depth_name = base.authoritative_names(layer)
    source_exr = base.OpenEXR.File(str(source))
    if len(source_exr.parts) != 1:
        raise ValueError(
            f"Expected one Blender 4.5 source part, got {len(source_exr.parts)}"
        )
    source_part = source_exr.parts[0]
    expected_channels = {color_name, f"{depth_name}.V"}
    if set(source_part.channels) != expected_channels:
        raise ValueError(
            f"Unexpected Blender 4.5 channels: expected={sorted(expected_channels)} "
            f"got={sorted(source_part.channels)}"
        )
    color = base.pixels_for(source_part, color_name)
    depth = base.pixels_for(source_part, f"{depth_name}.V")
    if color.shape != (height, width, 4):
        raise ValueError(f"Bad Blender 4.5 color shape: {color.shape}")
    if depth.shape != (height, width):
        raise ValueError(f"Bad Blender 4.5 depth shape: {depth.shape}")
    provenance = (
        "Blender 4.5 single-part multilayer channels promoted to named "
        "multipart EXR; float samples copied exactly without conversion"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.promoting.exr")
    temporary.unlink(missing_ok=True)
    try:
        base.OpenEXR.File(
            [
                base.OpenEXR.Part(
                    base.stitched_header(source_part, provenance),
                    {color_name: color},
                    color_name,
                ),
                base.OpenEXR.Part(
                    base.stitched_header(source_part, provenance),
                    {f"{depth_name}.V": depth},
                    depth_name,
                ),
            ]
        ).write(str(temporary))
        output_metrics, output_exr = base.validate_parts(
            temporary,
            color_name,
            depth_name,
            width,
            height,
            exact_parts={color_name, depth_name},
        )
        output_parts = base.part_map(output_exr)
        if not (
            base.np.array_equal(
                base.pixels_for(output_parts[color_name], color_name), color
            )
            and base.np.array_equal(
                base.pixels_for(output_parts[depth_name], f"{depth_name}.V"),
                depth,
            )
        ):
            raise ValueError("Blender 4.5 multipart promotion changed float samples")
        base.os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    output_metrics["path"] = str(output)
    output_metrics["bytes"] = output.stat().st_size
    return {
        "status": "PASS",
        "layer": layer,
        **output_metrics,
        "source": str(source),
        "operation": "lossless_blender45_single_part_to_named_multipart",
        "all_float_samples_preserved_exactly": True,
        "color_conversion": False,
        "depth_quantization": False,
        "resizing": False,
        "resampling": False,
        "interpolation": False,
    }


def convert_blender45_main() -> None:
    parser = base.argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--layer", choices=base.LAYERS, required=True)
    parser.add_argument("--width", type=int, required=True)
    parser.add_argument("--height", type=int, required=True)
    args = parser.parse_args(sys.argv[2:])
    result = convert_blender45_bundle(
        args.input, args.output, args.layer, args.width, args.height
    )
    print(base.json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    if sys.argv[1:2] == ["convert-blender45-bundle"]:
        convert_blender45_main()
    else:
        base.main()

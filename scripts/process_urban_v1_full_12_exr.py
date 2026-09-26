#!/usr/bin/env python3
"""Content-aware OpenEXR processing for the full-12 delivery pipeline.

Blender 5.1 can return an uninitialized dense 1920x1080 Workbench buffer for
the largest linked city partitions. The active renderer therefore writes four
stable 960x540 complementary pixel-center lattices. This helper validates
their actual float pixels, interlaces them directly onto the exact 1920x1080
parity grid, and proves that every color/alpha/depth sample survives unchanged.
It also provides the independent pixel-level final matrix scan and a native-
resolution calibration comparison used by the completion gate. The legacy
part-extraction command remains available for reproducing earlier diagnostics.

The script deliberately lives in the active generator repository and refuses
to read or write EXRs outside the full-12 output directory.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import OpenEXR


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY = (ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION).resolve()
ASSET_LAYERS = (
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
)
LAYERS = ("base", *ASSET_LAYERS)
MIN_BYTES = 256 * 1024
MIN_COLOR_STDDEV = 1.0e-5
MIN_NONZERO_COLOR_VALUES = 1_000
MIN_DEPTH_SPAN_METERS = 1.0e-3


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def inside_city(token: str | Path, *, must_exist: bool = False) -> Path:
    path = Path(token).resolve()
    if not path.is_relative_to(CITY):
        raise ValueError(f"EXR path must remain inside {CITY}: {path}")
    if must_exist and not path.is_file():
        raise FileNotFoundError(path)
    return path


def finite_float(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError(f"Non-finite statistic: {value}")
    return float(value)


def part_map(exr: OpenEXR.File) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for part in exr.parts:
        name = part.name()
        if not name or name in result:
            raise ValueError(f"Missing or duplicate EXR part name: {name!r}")
        result[name] = part
    return result


def pixels_for(part: Any, channel_name: str) -> np.ndarray:
    channel = part.channels.get(channel_name)
    if channel is None:
        raise ValueError(
            f"Part {part.name()!r} does not contain channel {channel_name!r}; "
            f"got {sorted(part.channels)}"
        )
    pixels = np.asarray(channel.pixels)
    if pixels.dtype not in (np.dtype("float16"), np.dtype("float32")):
        raise ValueError(
            f"Unexpected dtype for {part.name()}/{channel_name}: {pixels.dtype}"
        )
    if not np.isfinite(pixels).all():
        raise ValueError(f"Non-finite pixels in {part.name()}/{channel_name}")
    return pixels


def validate_parts(
    path: Path,
    color_part: str,
    depth_part: str,
    width: int,
    height: int,
    *,
    exact_parts: set[str] | None,
) -> tuple[dict[str, Any], OpenEXR.File]:
    if path.stat().st_size < MIN_BYTES:
        raise ValueError(f"Degenerate EXR byte size {path.stat().st_size}: {path}")
    exr = OpenEXR.File(str(path))
    parts = part_map(exr)
    if exact_parts is not None and set(parts) != exact_parts:
        raise ValueError(
            f"Unexpected EXR parts for {path.name}: "
            f"expected={sorted(exact_parts)} got={sorted(parts)}"
        )
    if color_part not in parts or depth_part not in parts:
        raise ValueError(
            f"Missing authoritative parts in {path.name}: "
            f"{color_part}, {depth_part}; got={sorted(parts)}"
        )
    color = pixels_for(parts[color_part], color_part)
    depth_channel = f"{depth_part}.V"
    depth = pixels_for(parts[depth_part], depth_channel)
    if color.shape != (height, width, 4):
        raise ValueError(
            f"Bad color shape in {path.name}: {color.shape}, "
            f"expected={(height, width, 4)}"
        )
    if depth.shape != (height, width):
        raise ValueError(
            f"Bad depth shape in {path.name}: {depth.shape}, "
            f"expected={(height, width)}"
        )
    rgb = color[..., :3]
    color_stddev = finite_float(float(np.std(rgb, dtype=np.float64)))
    nonzero_color_values = int(np.count_nonzero(np.abs(rgb) > 1.0e-7))
    depth_min = finite_float(float(np.min(depth)))
    depth_max = finite_float(float(np.max(depth)))
    depth_span = finite_float(depth_max - depth_min)
    if color_stddev <= MIN_COLOR_STDDEV:
        raise ValueError(
            f"Degenerate color stddev {color_stddev} in {path.name}/{color_part}"
        )
    if nonzero_color_values < MIN_NONZERO_COLOR_VALUES:
        raise ValueError(
            f"Too few nonzero color values ({nonzero_color_values}) in "
            f"{path.name}/{color_part}"
        )
    if depth_span <= MIN_DEPTH_SPAN_METERS or depth_max <= 0.0:
        raise ValueError(
            f"Degenerate depth range [{depth_min}, {depth_max}] in "
            f"{path.name}/{depth_part}"
        )
    metrics = {
        "path": str(path),
        "bytes": path.stat().st_size,
        "parts": sorted(parts),
        "color_part": color_part,
        "depth_part": depth_channel,
        "resolution": [width, height],
        "color_rgb_stddev": color_stddev,
        "nonzero_rgb_values": nonzero_color_values,
        "depth_min": depth_min,
        "depth_max": depth_max,
        "depth_span": depth_span,
        "pixel_content_nondegenerate": True,
    }
    return metrics, exr


def extract_combined(
    source_token: str, output_token: str, width: int, height: int
) -> dict[str, Any]:
    source = inside_city(source_token, must_exist=True)
    output = inside_city(output_token)
    source_metrics, source_exr = validate_parts(
        source,
        "CombinedColor",
        "CombinedDepth",
        width,
        height,
        exact_parts={
            "WarmupColor",
            "WarmupDepth",
            "CombinedColor",
            "CombinedDepth",
        },
    )
    by_name = part_map(source_exr)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.extracting.exr")
    temporary.unlink(missing_ok=True)
    try:
        # Reusing the decoded Part objects preserves every float sample and
        # header field. OpenEXR merely re-encodes the same arrays with their
        # authored ZIP compression; there is no color conversion or depth
        # quantization.
        OpenEXR.File([by_name["CombinedColor"], by_name["CombinedDepth"]]).write(
            str(temporary)
        )
        output_metrics, _ = validate_parts(
            temporary,
            "CombinedColor",
            "CombinedDepth",
            width,
            height,
            exact_parts={"CombinedColor", "CombinedDepth"},
        )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    output_metrics["path"] = str(output)
    output_metrics["bytes"] = output.stat().st_size
    return {
        "status": "PASS",
        "operation": "lossless_authoritative_part_extraction",
        "source": source_metrics,
        "output": output_metrics,
        "warmup_parts_retained": False,
        "color_conversion": False,
        "depth_quantization": False,
    }


def validate_bundle(
    path_token: str,
    layer: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    path = inside_city(path_token, must_exist=True)
    if layer == "base":
        color_part, depth_part = "BaseColor", "BaseDepth"
    elif layer in ASSET_LAYERS:
        color_part, depth_part = "CombinedColor", "CombinedDepth"
    else:
        raise ValueError(f"Unknown full-12 layer: {layer}")
    metrics, _ = validate_parts(
        path,
        color_part,
        depth_part,
        width,
        height,
        exact_parts={color_part, depth_part},
    )
    return {"status": "PASS", "layer": layer, **metrics}


def relabel_bundle(
    input_token: str,
    output_token: str,
    source_layer: str,
    target_layer: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    source = inside_city(input_token, must_exist=True)
    output = inside_city(output_token)
    source_color, source_depth = authoritative_names(source_layer)
    target_color, target_depth = authoritative_names(target_layer)
    source_metrics, source_exr = validate_parts(
        source,
        source_color,
        source_depth,
        width,
        height,
        exact_parts={source_color, source_depth},
    )
    source_parts = part_map(source_exr)
    color = pixels_for(source_parts[source_color], source_color)
    depth = pixels_for(source_parts[source_depth], f"{source_depth}.V")
    provenance = (
        f"exact float channel relabel {source_color}/{source_depth} to "
        f"{target_color}/{target_depth}; no pixel conversion"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.relabeling.exr")
    temporary.unlink(missing_ok=True)
    try:
        OpenEXR.File(
            [
                OpenEXR.Part(
                    stitched_header(source_parts[source_color], provenance),
                    {target_color: color},
                    target_color,
                ),
                OpenEXR.Part(
                    stitched_header(source_parts[source_depth], provenance),
                    {f"{target_depth}.V": depth},
                    target_depth,
                ),
            ]
        ).write(str(temporary))
        output_metrics, output_exr = validate_parts(
            temporary,
            target_color,
            target_depth,
            width,
            height,
            exact_parts={target_color, target_depth},
        )
        output_parts = part_map(output_exr)
        if not (
            np.array_equal(pixels_for(output_parts[target_color], target_color), color)
            and np.array_equal(
                pixels_for(output_parts[target_depth], f"{target_depth}.V"), depth
            )
        ):
            raise ValueError("Relabeled EXR changed one or more float samples")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    output_metrics["path"] = str(output)
    output_metrics["bytes"] = output.stat().st_size
    return {
        "status": "PASS",
        "operation": "lossless_float_channel_relabel",
        "source": source_metrics,
        "output": output_metrics,
        "all_float_samples_preserved_exactly": True,
        "color_conversion": False,
        "depth_quantization": False,
    }


def authoritative_names(layer: str) -> tuple[str, str]:
    if layer == "base":
        return "BaseColor", "BaseDepth"
    if layer in ASSET_LAYERS:
        return "CombinedColor", "CombinedDepth"
    raise ValueError(f"Unknown full-12 layer: {layer}")


def stitched_header(part: Any, provenance: str) -> dict[str, Any]:
    # Pixel windows, part names, channel lists, and chunk counts are derived
    # from the new full-height arrays by OpenEXR. Preserve all remaining
    # authored metadata, compression, and color/data interpretation.
    generated = {
        "channels",
        "chunkCount",
        "dataWindow",
        "displayWindow",
        "name",
        "type",
    }
    header = {key: value for key, value in part.header.items() if key not in generated}
    header["compression"] = OpenEXR.ZIP_COMPRESSION
    header["type"] = OpenEXR.scanlineimage
    header["worldbridge_full12_tiled_render"] = provenance
    return header


def stitch_halves(
    top_token: str,
    bottom_token: str,
    output_token: str,
    layer: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    if height % 2:
        raise ValueError(f"Full height must be even, got {height}")
    half_height = height // 2
    top = inside_city(top_token, must_exist=True)
    bottom = inside_city(bottom_token, must_exist=True)
    output = inside_city(output_token)
    color_name, depth_name = authoritative_names(layer)
    expected_parts = {color_name, depth_name}
    top_metrics, top_exr = validate_parts(
        top,
        color_name,
        depth_name,
        width,
        half_height,
        exact_parts=expected_parts,
    )
    bottom_metrics, bottom_exr = validate_parts(
        bottom,
        color_name,
        depth_name,
        width,
        half_height,
        exact_parts=expected_parts,
    )
    top_parts = part_map(top_exr)
    bottom_parts = part_map(bottom_exr)
    top_color = pixels_for(top_parts[color_name], color_name)
    bottom_color = pixels_for(bottom_parts[color_name], color_name)
    top_depth = pixels_for(top_parts[depth_name], f"{depth_name}.V")
    bottom_depth = pixels_for(bottom_parts[depth_name], f"{depth_name}.V")
    color = np.concatenate((top_color, bottom_color), axis=0)
    depth = np.concatenate((top_depth, bottom_depth), axis=0)
    provenance = (
        "native 1920x540 top/bottom subfrusta concatenated into the exact "
        "1920x1080 raster; float samples copied without interpolation"
    )
    parts = [
        OpenEXR.Part(
            stitched_header(top_parts[color_name], provenance),
            {color_name: color},
            color_name,
        ),
        OpenEXR.Part(
            stitched_header(top_parts[depth_name], provenance),
            {f"{depth_name}.V": depth},
            depth_name,
        ),
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.stitching.exr")
    temporary.unlink(missing_ok=True)
    try:
        OpenEXR.File(parts).write(str(temporary))
        output_metrics, output_exr = validate_parts(
            temporary,
            color_name,
            depth_name,
            width,
            height,
            exact_parts=expected_parts,
        )
        output_parts = part_map(output_exr)
        output_color = pixels_for(output_parts[color_name], color_name)
        output_depth = pixels_for(output_parts[depth_name], f"{depth_name}.V")
        # Prove the operation was a lossless array concatenation, not an image
        # resize. This includes alpha and the exact float camera-space Z.
        if not (
            np.array_equal(output_color[:half_height], top_color)
            and np.array_equal(output_color[half_height:], bottom_color)
            and np.array_equal(output_depth[:half_height], top_depth)
            and np.array_equal(output_depth[half_height:], bottom_depth)
        ):
            raise ValueError("Stitched EXR changed one or more float samples")
        seam_rgb = np.abs(
            output_color[half_height - 1, :, :3] - output_color[half_height, :, :3]
        )
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    output_metrics["path"] = str(output)
    output_metrics["bytes"] = output.stat().st_size
    return {
        "status": "PASS",
        "operation": "lossless_native_subfrustum_vertical_stitch",
        "layer": layer,
        "top": top_metrics,
        "bottom": bottom_metrics,
        "output": output_metrics,
        "tile_resolution": [width, half_height],
        "full_resolution": [width, height],
        "tile_count": 2,
        "tile_order_in_exr_rows": ["top", "bottom"],
        "all_float_samples_preserved_exactly": True,
        "resampling": False,
        "interpolation": False,
        "color_conversion": False,
        "depth_quantization": False,
        "seam_rgb_absolute_difference_mean": finite_float(
            float(np.mean(seam_rgb, dtype=np.float64))
        ),
        "seam_rgb_absolute_difference_p95": finite_float(
            float(np.percentile(seam_rgb, 95.0))
        ),
    }


def interlace_four(
    negative_negative_token: str,
    negative_positive_token: str,
    positive_negative_token: str,
    positive_positive_token: str,
    output_token: str,
    layer: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    if width % 2 or height % 2:
        raise ValueError(f"Full resolution must be even, got {width}x{height}")
    tile_width, tile_height = width // 2, height // 2
    color_name, depth_name = authoritative_names(layer)
    expected_parts = {color_name, depth_name}
    tokens = {
        "negative_negative": negative_negative_token,
        "negative_positive": negative_positive_token,
        "positive_negative": positive_negative_token,
        "positive_positive": positive_positive_token,
    }
    metrics: dict[str, Any] = {}
    colors: dict[str, np.ndarray] = {}
    depths: dict[str, np.ndarray] = {}
    reference_parts: dict[str, Any] | None = None
    for lattice, token in tokens.items():
        path = inside_city(token, must_exist=True)
        metric, exr = validate_parts(
            path,
            color_name,
            depth_name,
            tile_width,
            tile_height,
            exact_parts=expected_parts,
        )
        parts = part_map(exr)
        metrics[lattice] = metric
        colors[lattice] = pixels_for(parts[color_name], color_name)
        depths[lattice] = pixels_for(parts[depth_name], f"{depth_name}.V")
        if reference_parts is None:
            reference_parts = parts
    if reference_parts is None:
        raise ValueError("No interlaced source lattices were supplied")

    color = np.empty((height, width, 4), dtype=colors["negative_negative"].dtype)
    depth = np.empty((height, width), dtype=depths["negative_negative"].dtype)
    # Array rows are top-to-bottom. Camera shift contributes -2*shift to X
    # NDC and -2*aspect*shift to Y NDC. At half resolution a shift magnitude
    # of 1/full_width therefore lands each sample exactly on one parity of the
    # full-resolution pixel-center grid.
    lattice_slices = {
        "negative_positive": (slice(0, None, 2), slice(0, None, 2)),
        "positive_positive": (slice(0, None, 2), slice(1, None, 2)),
        "negative_negative": (slice(1, None, 2), slice(0, None, 2)),
        "positive_negative": (slice(1, None, 2), slice(1, None, 2)),
    }
    for lattice, target_slice in lattice_slices.items():
        color[target_slice] = colors[lattice]
        depth[target_slice] = depths[lattice]

    provenance = (
        "four native half-resolution complementary pixel-center lattices "
        "interlaced onto the exact full-resolution parity grid; no resize, "
        "resampling, or interpolation"
    )
    output = inside_city(output_token)
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f"{output.name}.interlacing.exr")
    temporary.unlink(missing_ok=True)
    try:
        OpenEXR.File(
            [
                OpenEXR.Part(
                    stitched_header(reference_parts[color_name], provenance),
                    {color_name: color},
                    color_name,
                ),
                OpenEXR.Part(
                    stitched_header(reference_parts[depth_name], provenance),
                    {f"{depth_name}.V": depth},
                    depth_name,
                ),
            ]
        ).write(str(temporary))
        output_metrics, output_exr = validate_parts(
            temporary,
            color_name,
            depth_name,
            width,
            height,
            exact_parts=expected_parts,
        )
        output_parts = part_map(output_exr)
        output_color = pixels_for(output_parts[color_name], color_name)
        output_depth = pixels_for(output_parts[depth_name], f"{depth_name}.V")
        if any(
            not (
                np.array_equal(output_color[target_slice], colors[lattice])
                and np.array_equal(output_depth[target_slice], depths[lattice])
            )
            for lattice, target_slice in lattice_slices.items()
        ):
            raise ValueError("Interlaced EXR changed one or more float samples")
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    output_metrics["path"] = str(output)
    output_metrics["bytes"] = output.stat().st_size
    return {
        "status": "PASS",
        "operation": "exact_target_pixel_grid_interlace",
        "layer": layer,
        "lattices": metrics,
        "output": output_metrics,
        "lattice_resolution": [tile_width, tile_height],
        "full_resolution": [width, height],
        "lattice_count": 4,
        "camera_shift_magnitude": 1.0 / (2.0 * width),
        "parity_map_top_to_bottom_rows": {
            key: [
                0 if value[0].start == 0 else 1,
                0 if value[1].start == 0 else 1,
            ]
            for key, value in lattice_slices.items()
        },
        "all_float_samples_preserved_exactly": True,
        "target_pixel_centers_sampled_exactly": True,
        "resizing": False,
        "resampling": False,
        "interpolation": False,
        "color_conversion": False,
        "depth_quantization": False,
    }


def compare_interlace_reference(
    native_token: str,
    interlaced_token: str,
    report_token: str,
    layer: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    native = inside_city(native_token, must_exist=True)
    interlaced = inside_city(interlaced_token, must_exist=True)
    color_name, depth_name = authoritative_names(layer)
    exact_parts = {color_name, depth_name}
    native_metrics, native_exr = validate_parts(
        native,
        color_name,
        depth_name,
        width,
        height,
        exact_parts=exact_parts,
    )
    interlaced_metrics, interlaced_exr = validate_parts(
        interlaced,
        color_name,
        depth_name,
        width,
        height,
        exact_parts=exact_parts,
    )
    native_parts = part_map(native_exr)
    interlaced_parts = part_map(interlaced_exr)
    native_rgb = pixels_for(native_parts[color_name], color_name)[..., :3]
    interlaced_rgb = pixels_for(interlaced_parts[color_name], color_name)[..., :3]
    color_delta = np.abs(native_rgb - interlaced_rgb)
    mse = float(np.mean(color_delta * color_delta, dtype=np.float64))
    psnr = finite_float(float(-10.0 * math.log10(max(mse, 1.0e-20))))
    correlation = finite_float(
        float(np.corrcoef(native_rgb.ravel(), interlaced_rgb.ravel())[0, 1])
    )
    native_depth = pixels_for(native_parts[depth_name], f"{depth_name}.V")
    interlaced_depth = pixels_for(interlaced_parts[depth_name], f"{depth_name}.V")
    native_hit = native_depth < 1.0e9
    interlaced_hit = interlaced_depth < 1.0e9
    both_hit = native_hit & interlaced_hit
    if not np.any(both_hit):
        raise ValueError("Reference comparison has no shared depth hits")
    depth_delta = np.abs(native_depth[both_hit] - interlaced_depth[both_hit])
    color_mae = finite_float(float(np.mean(color_delta, dtype=np.float64)))
    color_p95 = finite_float(float(np.percentile(color_delta, 95.0)))
    depth_mae = finite_float(float(np.mean(depth_delta, dtype=np.float64)))
    depth_p95 = finite_float(float(np.percentile(depth_delta, 95.0)))
    hit_agreement = finite_float(float(np.mean(native_hit == interlaced_hit)))
    exact_depth_fraction = finite_float(float(np.mean(depth_delta == 0.0)))
    passed = bool(
        psnr >= 35.0
        and correlation >= 0.995
        and hit_agreement >= 0.999
        and depth_p95 <= 0.01
    )
    report = {
        "schema": "agent.full12.interlaced_projection_validation.v1",
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "scene_revision": REVISION,
        "layer": layer,
        "camera": "city_northwest_panorama",
        "native_reference": native_metrics,
        "interlaced_candidate": interlaced_metrics,
        "resolution": [width, height],
        "method": (
            "four complementary half-resolution camera lattices shifted by "
            "+/-1/(2*full_width), placed directly on target pixel parities"
        ),
        "camera_shift_magnitude": 1.0 / (2.0 * width),
        "target_pixel_centers_sampled_exactly": True,
        "resizing": False,
        "resampling": False,
        "interpolation": False,
        "all_float_samples_preserved_exactly": True,
        "metrics": {
            "color_mae": color_mae,
            "color_p95": color_p95,
            "color_psnr_db": psnr,
            "color_correlation": correlation,
            "both_depth_hit_pixels": int(np.count_nonzero(both_hit)),
            "depth_mae_meters": depth_mae,
            "depth_p95_meters": depth_p95,
            "exact_depth_fraction": exact_depth_fraction,
            "depth_hit_agreement": hit_agreement,
        },
        "thresholds": {
            "minimum_color_psnr_db": 35.0,
            "minimum_color_correlation": 0.995,
            "minimum_depth_hit_agreement": 0.999,
            "maximum_depth_p95_meters": 0.01,
        },
        "pass": passed,
    }
    report_path = inside_city(report_token)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, report_path)
    if not passed:
        raise ValueError(f"Interlaced projection validation failed: {report}")
    return report


def compare_instance_expansion(
    source_token: str,
    expanded_token: str,
    report_token: str,
    layer: str,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Prove transient object-shell expansion preserves an authored instance."""

    source = inside_city(source_token, must_exist=True)
    expanded = inside_city(expanded_token, must_exist=True)
    color_name, depth_name = authoritative_names(layer)
    exact_parts = {color_name, depth_name}
    source_metrics, source_exr = validate_parts(
        source, color_name, depth_name, width, height, exact_parts=exact_parts
    )
    expanded_metrics, expanded_exr = validate_parts(
        expanded, color_name, depth_name, width, height, exact_parts=exact_parts
    )
    source_parts = part_map(source_exr)
    expanded_parts = part_map(expanded_exr)
    source_rgb = pixels_for(source_parts[color_name], color_name)[..., :3]
    expanded_rgb = pixels_for(expanded_parts[color_name], color_name)[..., :3]
    color_delta = np.abs(source_rgb - expanded_rgb)
    mse = float(np.mean(color_delta * color_delta, dtype=np.float64))
    psnr = finite_float(float(-10.0 * math.log10(max(mse, 1.0e-20))))
    correlation = finite_float(
        float(np.corrcoef(source_rgb.ravel(), expanded_rgb.ravel())[0, 1])
    )
    source_depth = pixels_for(source_parts[depth_name], f"{depth_name}.V")
    expanded_depth = pixels_for(expanded_parts[depth_name], f"{depth_name}.V")
    source_hit = source_depth < 1.0e9
    expanded_hit = expanded_depth < 1.0e9
    both_hit = source_hit & expanded_hit
    if not np.any(both_hit):
        raise ValueError("Instance expansion comparison has no shared depth hits")
    depth_delta = np.abs(source_depth[both_hit] - expanded_depth[both_hit])
    metrics = {
        "color_mae": finite_float(float(np.mean(color_delta, dtype=np.float64))),
        "color_p95": finite_float(float(np.percentile(color_delta, 95.0))),
        "color_psnr_db": psnr,
        "color_correlation": correlation,
        "both_depth_hit_pixels": int(np.count_nonzero(both_hit)),
        "depth_mae_meters": finite_float(float(np.mean(depth_delta, dtype=np.float64))),
        "depth_p95_meters": finite_float(float(np.percentile(depth_delta, 95.0))),
        "exact_depth_fraction": finite_float(float(np.mean(depth_delta == 0.0))),
        "depth_hit_agreement": finite_float(float(np.mean(source_hit == expanded_hit))),
    }
    passed = bool(
        metrics["color_psnr_db"] >= 50.0
        and metrics["color_correlation"] >= 0.9999
        and metrics["color_p95"] <= 1.0e-6
        and metrics["depth_hit_agreement"] == 1.0
        and metrics["depth_p95_meters"] == 0.0
        and metrics["exact_depth_fraction"] == 1.0
    )
    report = {
        "schema": "agent.full12.instance_expansion_equivalence.v1",
        "created_utc": utc_now(),
        "status": "PASS" if passed else "FAIL",
        "scene_revision": REVISION,
        "layer": layer,
        "camera": "city_northwest_panorama",
        "resolution": [width, height],
        "source_collection_instance": source_metrics,
        "expanded_shared_data_objects": expanded_metrics,
        "method": (
            "same camera, resolution, materials, receivers, and evaluated GN; "
            "compare authored collection instance against transient object shells"
        ),
        "source_data_shared": True,
        "modifiers_applied": False,
        "mesh_data_realized": False,
        "resizing": False,
        "resampling": False,
        "interpolation": False,
        "metrics": metrics,
        "thresholds": {
            "minimum_color_psnr_db": 50.0,
            "minimum_color_correlation": 0.9999,
            "maximum_color_p95": 1.0e-6,
            "required_depth_hit_agreement": 1.0,
            "maximum_depth_p95_meters": 0.0,
            "required_exact_depth_fraction": 1.0,
        },
        "all_camera_depth_samples_preserved_exactly": bool(
            metrics["depth_hit_agreement"] == 1.0
            and metrics["exact_depth_fraction"] == 1.0
        ),
        "pass": passed,
    }
    report_path = inside_city(report_token)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, report_path)
    if not passed:
        raise ValueError(f"Instance expansion equivalence failed: {report}")
    return report


def scan_matrix(
    root_token: str,
    report_token: str,
    width: int,
    height: int,
    expected_count: int,
) -> dict[str, Any]:
    layer_root = inside_city(root_token, must_exist=False)
    if not layer_root.is_dir():
        raise FileNotFoundError(layer_root)
    records: dict[str, Any] = {}
    total_bytes = 0
    for layer in LAYERS:
        directory = inside_city(layer_root / layer)
        files = sorted(directory.glob("*.exr")) if directory.is_dir() else []
        writing = sorted(directory.glob(".writing*.exr")) if directory.is_dir() else []
        if writing:
            raise ValueError(
                f"Uncommitted EXRs remain in {layer}: {[p.name for p in writing]}"
            )
        if len(files) != expected_count:
            raise ValueError(
                f"Expected {expected_count} EXRs in {layer}, got {len(files)}"
            )
        color_stddev_min = float("inf")
        nonzero_min = 2**63 - 1
        depth_span_min = float("inf")
        layer_bytes = 0
        for path in files:
            metric = validate_bundle(str(path), layer, width, height)
            color_stddev_min = min(color_stddev_min, metric["color_rgb_stddev"])
            nonzero_min = min(nonzero_min, metric["nonzero_rgb_values"])
            depth_span_min = min(depth_span_min, metric["depth_span"])
            layer_bytes += int(metric["bytes"])
        records[layer] = {
            "count": len(files),
            "bytes": layer_bytes,
            "minimum_color_rgb_stddev": color_stddev_min,
            "minimum_nonzero_rgb_values": nonzero_min,
            "minimum_depth_span": depth_span_min,
            "exact_authoritative_parts_only": True,
            "all_pixel_content_nondegenerate": True,
        }
        total_bytes += layer_bytes
    report = {
        "schema": "agent.full12.openexr_content_audit.v1",
        "created_utc": utc_now(),
        "status": "PASS",
        "scene_revision": REVISION,
        "root": str(layer_root),
        "resolution": [width, height],
        "layer_count": len(LAYERS),
        "expected_per_layer": expected_count,
        "validated_file_count": len(LAYERS) * expected_count,
        "total_bytes": total_bytes,
        "warmup_parts_retained": False,
        "color_conversion": False,
        "depth_quantization": False,
        "layers": records,
    }
    report_path = inside_city(report_token)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(".writing.json")
    temporary.write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary, report_path)
    return report


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    subparsers = result.add_subparsers(dest="command", required=True)
    extract = subparsers.add_parser("extract-combined")
    extract.add_argument("--input", required=True)
    extract.add_argument("--output", required=True)
    extract.add_argument("--width", type=int, required=True)
    extract.add_argument("--height", type=int, required=True)
    validate = subparsers.add_parser("validate-bundle")
    validate.add_argument("--input", required=True)
    validate.add_argument("--layer", choices=LAYERS, required=True)
    validate.add_argument("--width", type=int, required=True)
    validate.add_argument("--height", type=int, required=True)
    relabel = subparsers.add_parser("relabel-bundle")
    relabel.add_argument("--input", required=True)
    relabel.add_argument("--output", required=True)
    relabel.add_argument("--source-layer", choices=LAYERS, required=True)
    relabel.add_argument("--target-layer", choices=LAYERS, required=True)
    relabel.add_argument("--width", type=int, required=True)
    relabel.add_argument("--height", type=int, required=True)
    stitch = subparsers.add_parser("stitch-halves")
    stitch.add_argument("--top", required=True)
    stitch.add_argument("--bottom", required=True)
    stitch.add_argument("--output", required=True)
    stitch.add_argument("--layer", choices=LAYERS, required=True)
    stitch.add_argument("--width", type=int, required=True)
    stitch.add_argument("--height", type=int, required=True)
    interlace = subparsers.add_parser("interlace-four")
    interlace.add_argument("--negative-negative", required=True)
    interlace.add_argument("--negative-positive", required=True)
    interlace.add_argument("--positive-negative", required=True)
    interlace.add_argument("--positive-positive", required=True)
    interlace.add_argument("--output", required=True)
    interlace.add_argument("--layer", choices=LAYERS, required=True)
    interlace.add_argument("--width", type=int, required=True)
    interlace.add_argument("--height", type=int, required=True)
    compare = subparsers.add_parser("compare-interlace-reference")
    compare.add_argument("--native", required=True)
    compare.add_argument("--interlaced", required=True)
    compare.add_argument("--report", required=True)
    compare.add_argument("--layer", choices=LAYERS, required=True)
    compare.add_argument("--width", type=int, required=True)
    compare.add_argument("--height", type=int, required=True)
    expansion = subparsers.add_parser("compare-instance-expansion")
    expansion.add_argument("--source", required=True)
    expansion.add_argument("--expanded", required=True)
    expansion.add_argument("--report", required=True)
    expansion.add_argument("--layer", choices=LAYERS, required=True)
    expansion.add_argument("--width", type=int, required=True)
    expansion.add_argument("--height", type=int, required=True)
    scan = subparsers.add_parser("scan-matrix")
    scan.add_argument("--root", required=True)
    scan.add_argument("--report", required=True)
    scan.add_argument("--width", type=int, required=True)
    scan.add_argument("--height", type=int, required=True)
    scan.add_argument("--expected-count", type=int, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    if args.command == "extract-combined":
        result = extract_combined(args.input, args.output, args.width, args.height)
    elif args.command == "validate-bundle":
        result = validate_bundle(args.input, args.layer, args.width, args.height)
    elif args.command == "relabel-bundle":
        result = relabel_bundle(
            args.input,
            args.output,
            args.source_layer,
            args.target_layer,
            args.width,
            args.height,
        )
    elif args.command == "stitch-halves":
        result = stitch_halves(
            args.top,
            args.bottom,
            args.output,
            args.layer,
            args.width,
            args.height,
        )
    elif args.command == "interlace-four":
        result = interlace_four(
            args.negative_negative,
            args.negative_positive,
            args.positive_negative,
            args.positive_positive,
            args.output,
            args.layer,
            args.width,
            args.height,
        )
    elif args.command == "compare-interlace-reference":
        result = compare_interlace_reference(
            args.native,
            args.interlaced,
            args.report,
            args.layer,
            args.width,
            args.height,
        )
    elif args.command == "compare-instance-expansion":
        result = compare_instance_expansion(
            args.source,
            args.expanded,
            args.report,
            args.layer,
            args.width,
            args.height,
        )
    else:
        result = scan_matrix(
            args.root,
            args.report,
            args.width,
            args.height,
            args.expected_count,
        )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()

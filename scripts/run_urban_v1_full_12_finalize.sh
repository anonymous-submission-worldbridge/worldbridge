#!/bin/sh

# Portable defaults; caller-provided environment variables take precedence.
_wb_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
while [ ! -d "$_wb_dir/worldbridge" ] && [ "$_wb_dir" != / ]; do
    _wb_dir=$(dirname -- "$_wb_dir")
done
WORLDBRIDGE_ROOT=${WORLDBRIDGE_ROOT:-$_wb_dir}
WORLDBRIDGE_EXTERNAL=${WORLDBRIDGE_EXTERNAL:-$WORLDBRIDGE_ROOT/external}
WORLDBRIDGE_MODELS=${WORLDBRIDGE_MODELS:-$WORLDBRIDGE_ROOT/models}
WORLDBRIDGE_CACHE=${WORLDBRIDGE_CACHE:-$WORLDBRIDGE_ROOT/.cache}
WORLDBRIDGE_PYTHON=${WORLDBRIDGE_PYTHON:-python}
WORLDBRIDGE_SITE_PACKAGES=${WORLDBRIDGE_SITE_PACKAGES:-$WORLDBRIDGE_EXTERNAL/site-packages}
BLENDER_BIN=${BLENDER_BIN:-blender}
BLENDER_RESOURCES=${BLENDER_RESOURCES:-$WORLDBRIDGE_EXTERNAL/blender/resources}
export WORLDBRIDGE_ROOT WORLDBRIDGE_EXTERNAL WORLDBRIDGE_MODELS WORLDBRIDGE_CACHE
set -eu

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_runtime="$c2w_city/render_runtime/finalize"
c2w_status="$c2w_city/finalize.status"
c2w_log="$c2w_city/finalize.log"
c2w_matrix_status="$c2w_city/render_matrix.status"
c2w_reframe_status="$c2w_city/camera_reframe_matrix.status"
c2w_base_status="$c2w_city/render_base.status"
c2w_quality_status="$c2w_city/material_fidelity.status"
c2w_eevee_base_status="$c2w_city/eevee_fallback_base.status"
c2w_openexr_audit="$c2w_city/openexr_content_audit.json"
c2w_openexr_python="${WORLDBRIDGE_PYTHON}"
c2w_gpu_backend="${C2W_FULL12_GPU_BACKEND:-vulkan}"
c2w_stage="initialization"

c2w_fail() {
    c2w_code="$1"
    printf 'FAIL %s stage=%s exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_stage" "$c2w_code" > "$c2w_status"
    exit "$c2w_code"
}

case "$c2w_gpu_backend" in
    opengl|vulkan) ;;
    *) c2w_fail 89 ;;
esac

mkdir -p "$c2w_runtime/tmp" "$c2w_runtime/cache"
: > "$c2w_log"
printf 'WAITING %s for=render_matrix\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

while :; do
    c2w_matrix_state="MISSING"
    if [ -f "$c2w_matrix_status" ]; then
        read -r c2w_matrix_state c2w_rest < "$c2w_matrix_status" || true
    fi
    case "$c2w_matrix_state" in
        PASS) break ;;
        FAIL)
            printf 'FAIL %s stage=render_matrix\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
            exit 91
            ;;
    esac
    sleep 30
done

# If a source-authored camera recovery matrix is present, it is part of this
# delivery and must complete before any fallback-base or composition stage.
if [ -f "$c2w_reframe_status" ]; then
    printf 'WAITING %s for=camera_reframe_matrix\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    while :; do
        read -r c2w_reframe_state c2w_rest < "$c2w_reframe_status" || true
        case "$c2w_reframe_state" in
            PASS) break ;;
            FAIL)
                printf 'FAIL %s stage=camera_reframe_matrix\n' \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
                exit 90
                ;;
        esac
        sleep 30
    done
fi

# The matrix originally completed the opaque base before the exact camera
# no-hit alpha correction was introduced.  A forced replacement job updates
# all 80 BaseColor/BaseDepth bundles in place.  Never begin delivery
# composition while one of those atomic replacements is still running.
printf 'WAITING %s for=transparent_base\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
while :; do
    c2w_base_state="MISSING"
    if [ -f "$c2w_base_status" ]; then
        read -r c2w_base_state c2w_rest < "$c2w_base_status" || true
    fi
    case "$c2w_base_state" in
        PASS) break ;;
        FAIL)
            printf 'FAIL %s stage=transparent_base\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
            exit 92
            ;;
    esac
    sleep 30
done

# A small number of high-reference river/park or artificial-lake frames may
# use the bounded Eevee fallback when Blender 5.1 returns a proven all-zero
# Workbench buffer. Render an exact same-camera Eevee base reference for those
# frames so the delivery compositor can transfer relative shadows/reflections
# onto the common Workbench base.
printf 'RUNNING %s stage=eevee_fallback_base\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="eevee_fallback_base"
if ! /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_eevee_fallback_base.sh" \
    >> "$c2w_log" 2>&1
then
    c2w_fail 96
fi
if [ ! -f "$c2w_eevee_base_status" ] || \
    ! grep -q '^PASS ' "$c2w_eevee_base_status"
then
    c2w_fail 96
fi

# The primary exact partition renderer uses transient Principled constants ->
# viewport material fields, 16-sample Workbench AA, outdoor studio light,
# shadows, specular, and world/screen cavity. Only river/park or artificial-
# lake frames with a validated Blender 5.1 all-zero Workbench buffer may use
# 64-sample Eevee; the same-camera baseline stage above preserves their
# relative receiver lighting. This gate proves all 13x80 bundles carry an
# allowed provenance and proves no node graph, source file, or production
# Blend was written.
printf 'RUNNING %s stage=material_fidelity_validation\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="material_fidelity_validation"
if ! python3 - "$c2w_city" >> "$c2w_log" 2>&1 <<'PY'
import json
import pathlib
import sys

city = pathlib.Path(sys.argv[1])
layers = (
    "base", "river5_nature", "river3_residential",
    "all45_unique_buildings", "all44_leisure", "commercial_services",
    "residential_delivery", "park_leisure_support", "artificial_lake",
    "education_buildings", "public_safety", "health", "industrial",
)
expected_gn_controllers = {"river5_nature": 1, "artificial_lake": 2}
eevee_fallback_layers = {"river5_nature", "artificial_lake"}
frame_engine_counts = {}

def valid(settings, layer):
    sync = settings.get("workbench_material_sync", {})
    common = (
        settings.get("resolution") == [1920, 1080]
        and settings.get("mesh_simplification") is False
        and int(sync.get("materials_examined") or 0) > 0
        and int(sync.get("write_failures") or 0) == 0
        and sync.get("node_graphs_changed") is False
        and sync.get("source_files_saved") is False
        and sync.get("production_blend_saved") is False
    )
    if not common:
        return False
    if settings.get("engine") == "BLENDER_WORKBENCH":
        return (
            int(settings.get("workbench_antialiasing_samples") or 0) >= 16
            and settings.get("workbench_color_type") == "MATERIAL"
            and settings.get("workbench_studio_light") == "outdoor.sl"
            and settings.get("workbench_shadows_and_cavity") is True
            and sync.get("enabled") is True
        )
    return (
        layer in eevee_fallback_layers
        and settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
        and int(settings.get("samples") or 0) >= 32
        and settings.get("denoising") is False
        and settings.get("eevee_shadow_quality", {}).get("policy")
        == "full12_complete_virtual_shadow_residency_v1"
        and settings.get("eevee_shadow_quality", {}).get("pool_size_mb")
        == 1024
        and settings.get("eevee_shadow_quality", {}).get("resolution_scale")
        == 0.5
        and settings.get("eevee_shadow_quality", {}).get(
            "missing_shadow_pages_allowed"
        )
        is False
        and sync.get("enabled") is False
        and sync.get("method") == "not applicable outside Workbench"
        and settings.get("workbench_antialiasing_samples") is None
        and settings.get("workbench_color_type") is None
        and settings.get("workbench_studio_light") is None
        and settings.get("workbench_shadows_and_cavity") is None
    )

for layer in layers:
    path = city / "renders/zdepth_layers" / f"layer_manifest_{layer}.json"
    data = json.loads(path.read_text(encoding="utf8"))
    assert data.get("status") == "PASS" and data.get("complete") is True
    assert data.get("completed_count") == 80 and len(data.get("views", [])) == 80
    assert valid(data.get("render_settings", {}), layer)
    assert all(
        valid(frame.get("render_settings", {}), layer)
        for frame in data["views"]
    )
    for frame in data["views"]:
        engine = frame.get("render_settings", {}).get("engine")
        assert engine in {
            "BLENDER_WORKBENCH", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"
        }
        assert engine not in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"} or layer in eevee_fallback_layers
        frame_engine_counts[engine] = frame_engine_counts.get(engine, 0) + 1
    expected_layers = ["Base"] if layer == "base" else ["Combined"]
    expected_depth = "BaseDepth.V" if layer == "base" else "CombinedDepth.V"
    expected_warmup = "not_used_single_exact_receiver_view"
    assert data.get("view_layers") == expected_layers
    assert data.get("non_delivery_warmup_content") == expected_warmup
    assert data.get("non_delivery_warmup_retained") is False
    assert data.get("content_aware_exr_validation") is True
    assert data.get("minimum_nondegenerate_exr_bytes") == 256 * 1024
    assert data.get("authoritative_exr_pixel_validation") is True
    assert data.get("authoritative_exr_exact_parts_only") is True
    assert data.get("warmup_parts_retained_in_committed_bundle") is False
    assert data.get("native_resolution") == [1920, 1080]
    assert data.get("lattice_resolution") is None
    assert data.get("lattice_count") == 0
    assert data.get("target_pixel_centers_sampled_exactly") is True
    assert data.get("resizing") is False
    assert data.get("resampling") is False
    assert data.get("interpolation") is False
    assert all(frame.get("view_layers") == expected_layers for frame in data["views"])
    assert all(
        frame.get("non_delivery_warmup_content") == expected_warmup
        for frame in data["views"]
    )
    assert all(frame.get("depth_channel") == expected_depth for frame in data["views"])
    expected_extraction = "not_used_direct_exact_two_part_bundle"
    assert data.get("combined_part_extraction") == expected_extraction
    assert data.get("render_settings", {}).get("combined_part_extraction") == expected_extraction
    for frame in data["views"]:
        evidence = frame.get("authoritative_exr_validation", {})
        assert evidence.get("status") == "PASS"
        expected_parts = (
            ["BaseColor", "BaseDepth"]
            if layer == "base"
            else ["CombinedColor", "CombinedDepth"]
        )
        assert evidence.get("operation") == "native_full_resolution_raster"
        assert evidence.get("resolution") == [1920, 1080]
        assert evidence.get("full_resolution") == [1920, 1080]
        assert evidence.get("native_resolution") == [1920, 1080]
        assert evidence.get("target_pixel_centers_sampled_exactly") is True
        assert evidence.get("resizing") is False
        assert evidence.get("resampling") is False
        assert evidence.get("interpolation") is False
        assert evidence.get("color_conversion") is False
        assert evidence.get("depth_quantization") is False
        assert evidence.get("pixel_content_nondegenerate") is True
        assert evidence.get("parts") == expected_parts
        projection = frame.get("camera", {}).get("target_grid_projection", {})
        assert projection.get("method") == "single native full-resolution raster"
        assert projection.get("full_resolution") == [1920, 1080]
        assert projection.get("native_resolution") == [1920, 1080]
        assert projection.get("camera_shift") == [0.0, 0.0]
        assert projection.get("target_pixel_centers_sampled_exactly") is True
        assert projection.get("resizing") is False
        assert projection.get("resampling") is False
        assert projection.get("interpolation") is False
    assert all(
        frame.get("camera", {}).get("matrix_validation", {}).get("pass") is True
        for frame in data["views"]
    )
    gn = data.get("temporary_exact_evaluated_gn_replacements", {})
    expected_controller_count = expected_gn_controllers.get(layer, 0)
    if expected_controller_count:
        controllers = gn.get("controllers", [])
        assert gn.get("enabled") is True
        assert gn.get("evaluation_view_layer") == "Combined"
        assert gn.get("controller_count") == expected_controller_count
        assert gn.get("replacement_object_count", 0) >= expected_controller_count
        assert gn.get("replacement_polygon_count", 0) > 0
        assert gn.get("omitted_visible_geometry_count") == 0
        assert gn.get("geometry_simplification") is False
        assert gn.get("node_graphs_changed") is False
        assert gn.get("source_files_saved") is False
        assert gn.get("production_blend_saved") is False
        assert len(controllers) == expected_controller_count
        assert all(
            controller.get("exact_evaluated_geometry") is True
            and controller.get("replacement_object_count", 0) > 0
            and controller.get("replacement_polygon_references", 0) > 0
            for controller in controllers
        )
        assert all(
            frame.get("exact_evaluated_gn_replacement", {}).get("enabled") is True
            and frame.get("exact_evaluated_gn_replacement", {}).get("controller_count")
            == expected_controller_count
            and frame.get("exact_evaluated_gn_replacement", {}).get(
                "omitted_visible_geometry_count"
            )
            == 0
            for frame in data["views"]
        )
    else:
        assert gn.get("enabled") is False
    expansion = data.get("temporary_exact_collection_instance_expansion", {})
    if layer == "base":
        assert expansion.get("enabled") is False
        assert expansion.get("placement_root_count") == 0
        assert expansion.get("expanded_object_count") == 0
        assert expansion.get("omitted_visible_geometry_count") == 0
    else:
        assert expansion.get("enabled") is True
        assert expansion.get("evaluation_view_layer") == "Combined"
        assert expansion.get("placement_root_count") == data.get(
            "assigned_placement_count"
        )
        assert expansion.get("expanded_object_count", 0) > 0
        assert expansion.get("shared_authored_data_count") == expansion.get(
            "expanded_object_count"
        )
        assert expansion.get("all_authored_data_shared") is True
        assert expansion.get("all_world_matrices_preserved") is True
        assert (
            float(expansion.get("maximum_world_matrix_error", 1.0)) <= 1.0e-4
            or float(
                expansion.get("maximum_world_matrix_relative_error", 1.0)
            ) <= 5.0e-7
        )
        assert expansion.get("maximum_world_matrix_absolute_error_allowed") == 1.0e-4
        assert expansion.get("maximum_world_matrix_relative_error_allowed") == 5.0e-7
        assert expansion.get("exact_svd_affine_factorization") is True
        assert expansion.get("affine_transform_helper_count", -1) == 2 * expansion.get(
            "sheared_object_count", -1
        )
        assert float(
            expansion.get("maximum_svd_factorization_error", 1.0)
        ) <= 1.0e-10
        assert expansion.get("modifiers_applied") is False
        assert expansion.get("mesh_data_realized") is False
        assert expansion.get("geometry_simplification") is False
        assert expansion.get("source_scale_changed") is False
        assert expansion.get("placement_roots_hidden_after_exact_expansion") is True
        assert expansion.get("omitted_visible_geometry_count") == 0
        assert expansion.get("source_data_copied") is False
        assert expansion.get("source_files_saved") is False
        assert expansion.get("production_blend_saved") is False
        assert len(expansion.get("per_placement_object_counts", {})) == data.get(
            "assigned_placement_count"
        )
        assert all(
            frame.get("exact_collection_instance_expansion", {}).get("enabled")
            is True
            and frame.get("exact_collection_instance_expansion", {}).get(
                "placement_root_count"
            )
            == expansion.get("placement_root_count")
            and frame.get("exact_collection_instance_expansion", {}).get(
                "expanded_object_count"
            )
            == expansion.get("expanded_object_count")
            and frame.get("exact_collection_instance_expansion", {}).get(
                "all_world_matrices_preserved"
            ) is True
            and frame.get("exact_collection_instance_expansion", {}).get(
                "omitted_visible_geometry_count"
            ) == 0
            for frame in data["views"]
        )
(city / "material_fidelity.status").write_text(
    "PASS layers=13 views_per_layer=80 engines="
    + json.dumps(frame_engine_counts, sort_keys=True, separators=(",", ":"))
    + " workbench_aa=16 eevee_fallback_samples=64 "
    "relative_receiver_lighting=true\n",
    encoding="utf8",
)
PY
then
    c2w_fail 93
fi
if [ ! -f "$c2w_quality_status" ] || ! grep -q '^PASS ' "$c2w_quality_status"; then
    c2w_fail 93
fi

# Independently reopen every committed float bundle with OpenEXR. This checks
# exact part names, 1920x1080 array shapes, finite samples, color variance,
# nonzero RGB population, and nonconstant camera-space depth. It therefore
# catches valid-header/all-zero files even if a rolling manifest were stale.
printf 'RUNNING %s stage=source_openexr_pixel_audit\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="source_openexr_pixel_audit"
if ! "$c2w_openexr_python" \
    "$c2w_root/scripts/process_urban_v1_full_12_exr.py" scan-matrix \
    --root "$c2w_city/renders/zdepth_layers" \
    --report "$c2w_openexr_audit" \
    --width 1920 --height 1080 --expected-count 80 \
    >> "$c2w_log" 2>&1
then
    c2w_fail 94
fi

cd "$c2w_root"
printf 'RUNNING %s stage=delivery_composition\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="delivery_composition"
TMPDIR="$c2w_runtime/tmp" XDG_CACHE_HOME="$c2w_runtime/cache" \
    C2W_FULL12_COMPOSE_FORCE="1" \
    /usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
    -b --factory-startup \
    --python "$c2w_root/scripts/compose_urban_v1_full_12_zdepth.py" \
    >> "$c2w_log" 2>&1 || c2w_fail "$?"

printf 'RUNNING %s stage=projection_layers\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="projection_layers"
/bin/sh "$c2w_root/scripts/run_urban_v1_full_12_projection_matrix.sh" \
    >> "$c2w_log" 2>&1 || c2w_fail "$?"

printf 'RUNNING %s stage=projection_union\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="projection_union"
TMPDIR="$c2w_runtime/tmp" XDG_CACHE_HOME="$c2w_runtime/cache" \
    /usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
    -b --factory-startup \
    --python "$c2w_root/scripts/compose_urban_v1_full_12_projection_audit.py" \
    >> "$c2w_log" 2>&1 || c2w_fail "$?"

# Rebuild the small dependency indices with the corrected serialized
# matrix_basis policy so the handed-off pipeline and its current artifacts are
# identical.  All temporary/cache paths remain inside the full-12 output.
printf 'RUNNING %s stage=render_pack_rebuild\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="render_pack_rebuild"
TMPDIR="$c2w_runtime/tmp" XDG_CACHE_HOME="$c2w_runtime/cache" \
    /usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
    --disable-depsgraph-on-file-load -b \
    "$c2w_city/urban_v1_full_12.blend" \
    --python "$c2w_root/scripts/build_urban_v1_full_12_render_packs.py" \
    >> "$c2w_log" 2>&1 || c2w_fail "$?"

printf 'RUNNING %s stage=strict_audit\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
c2w_stage="strict_audit"
python3 "$c2w_root/scripts/audit_urban_v1_full_12.py" >> "$c2w_log" 2>&1 || c2w_fail "$?"

printf 'PASS %s stages=8\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_FINALIZE_PASS utc=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"

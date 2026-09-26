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
set -u

# Render each exact asset partition in short-lived four-camera Blender
# processes.  Long-lived Workbench/depsgraph allocations can accumulate even
# when every source collection is linked read-only; recycling the process
# prevents late exit-137 failures while preserving the exact geometry,
# materials, transforms, cameras, Z passes, and shared receiver lighting.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_layer="${1:?expected full-12 z-depth layer key}"
c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
c2w_runtime="$c2w_city/render_runtime/$c2w_layer"
c2w_log="$c2w_city/render_${c2w_layer}.log"
c2w_status="$c2w_city/render_${c2w_layer}.status"
c2w_manifest="$c2w_city/renders/zdepth_layers/layer_manifest_${c2w_layer}.json"
c2w_force="${C2W_FULL12_RENDER_FORCE:-0}"
c2w_view_filter="${C2W_FULL12_VIEW_FILTER:-}"
c2w_gpu_backend="${C2W_FULL12_GPU_BACKEND:-opengl}"
c2w_batch_index=0
c2w_lock="$c2w_runtime/layer_render.lock"
c2w_shared_cache="$c2w_city/render_runtime/shared_material_cache"
c2w_eevee_lock="$c2w_city/render_runtime/eevee_fallback_render.lock"

case "$c2w_gpu_backend" in
    opengl|vulkan) ;;
    *)
        printf 'FAIL %s layer=%s reason=invalid_gpu_backend value=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
            "$c2w_gpu_backend" > "$c2w_status"
        exit 95
        ;;
esac

mkdir -p "$c2w_runtime" "$c2w_shared_cache"
# Prefetch jobs and the authoritative matrix may converge on the same layer.
# Serialize before touching its status/log/manifest; completed atomic bundles
# are then detected below and reused by the waiter.
exec 9> "$c2w_lock"
flock -x 9
touch "$c2w_log"
printf 'FULL12_ZLAYER_RUN_BEGIN utc=%s layer=%s force=%s gpu_backend=%s view_filter=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_force" \
    "$c2w_gpu_backend" "${c2w_view_filter:-ALL}" \
    >> "$c2w_log"

if [ ! -s "$c2w_pack" ]; then
    printf 'FAIL %s layer=%s reason=missing_pack\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"
    exit 97
fi

# A Blender process can occasionally be terminated during shutdown after it
# has atomically committed its fourth frame and PASS manifest.  Treat the
# manifest plus all 80 hashes and native-raster evidence as authoritative, and
# repair only the stale wrapper status.  This also makes a clean matrix retry
# O(1) per completed layer and preserves the original render provenance log.
if [ -z "$c2w_view_filter" ] && [ "$c2w_force" != "1" ] && \
    python3 - "$c2w_manifest" <<'PY' >> "$c2w_log" 2>&1
import hashlib
import json
import os
import pathlib
import sys

manifest = pathlib.Path(sys.argv[1])
if not manifest.is_file():
    raise SystemExit(1)
try:
    data = json.loads(manifest.read_text(encoding="utf8"))
except (OSError, ValueError, TypeError):
    raise SystemExit(1)
records = data.get("views", [])
allow_legacy_eevee = (
    os.environ.get("C2W_FULL12_ALLOW_LEGACY_EEVEE_RESUME", "0") == "1"
)
if not (
    data.get("status") == "PASS"
    and data.get("complete") is True
    and data.get("completed_count") == 80
    and len(data.get("completed_view_names", [])) == 80
    and len(records) == 80
):
    raise SystemExit(1)
for record in records:
    try:
        path = pathlib.Path(record["outputs"]["bundle"])
        expected_sha = record["sha256"]["bundle"]
        evidence = record["authoritative_exr_validation"]
        projection = record["camera"]["target_grid_projection"]
        settings = record["render_settings"]
    except (KeyError, TypeError):
        raise SystemExit(1)
    if not (
        path.is_file()
        and path.stat().st_size >= 256 * 1024
        and evidence.get("status") == "PASS"
        and evidence.get("operation") == "native_full_resolution_raster"
        and evidence.get("resolution") == [1920, 1080]
        and evidence.get("pixel_content_nondegenerate") is True
        and projection.get("method") == "single native full-resolution raster"
        and projection.get("native_resolution") == [1920, 1080]
        and projection.get("resizing") is False
        and projection.get("resampling") is False
        and projection.get("interpolation") is False
        and settings.get("native_resolution") == [1920, 1080]
        and settings.get("lattice_count") == 0
    ):
        raise SystemExit(1)
    if settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        if not allow_legacy_eevee:
            shadow = settings.get("eevee_shadow_quality", {})
            if not (
                shadow.get("policy")
                == "full12_complete_virtual_shadow_residency_v1"
                and shadow.get("pool_size_mb") == 1024
                and shadow.get("resolution_scale") == 0.5
                and shadow.get("missing_shadow_pages_allowed") is False
            ):
                raise SystemExit(1)
    with path.open("rb") as handle:
        if handle.read(4) != b"v/1\x01":
            raise SystemExit(1)
        handle.seek(0)
        hasher = hashlib.sha256()
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
        digest = hasher.hexdigest()
    if digest != expected_sha:
        raise SystemExit(1)
PY
then
    printf 'PASS %s layer=%s views=80 chunked=true chunk_size=4 reused=true\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"
    printf 'FULL12_ZLAYER_REUSE_COMPLETE utc=%s layer=%s views=80 validation=sha256_native_evidence\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
    exit 0
fi

printf 'RUNNING %s layer=%s chunk_size=4\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"

batch_complete() {
    c2w_names="$1"
    [ "$c2w_force" != "1" ] || return 1
    python3 - "$c2w_manifest" "$c2w_names" <<'PY' \
        >> "$c2w_log" 2>&1
import hashlib
import json
import os
import pathlib
import sys

manifest = pathlib.Path(sys.argv[1])
names = [name for name in sys.argv[2].split(",") if name]
if not manifest.is_file():
    raise SystemExit(1)
try:
    data = json.loads(manifest.read_text(encoding="utf8"))
    records = {record["name"]: record for record in data.get("views", [])}
    pairs = [
        (name, pathlib.Path(records[name]["outputs"]["bundle"]))
        for name in names
    ]
except (OSError, ValueError, KeyError, TypeError):
    raise SystemExit(1)

allow_legacy_eevee = (
    os.environ.get("C2W_FULL12_ALLOW_LEGACY_EEVEE_RESUME", "0") == "1"
)

def frame_quality_valid(record):
    settings = record.get("render_settings", {})
    if settings.get("engine") not in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
        return True
    if allow_legacy_eevee:
        return True
    shadow = settings.get("eevee_shadow_quality", {})
    return (
        shadow.get("policy")
        == "full12_complete_virtual_shadow_residency_v1"
        and shadow.get("pool_size_mb") == 1024
        and shadow.get("resolution_scale") == 0.5
        and shadow.get("missing_shadow_pages_allowed") is False
    )

def bundle_sha_valid(record, path):
    expected = record.get("sha256", {}).get("bundle")
    if not isinstance(expected, str) or len(expected) != 64:
        return False
    try:
        with path.open("rb") as handle:
            hasher = hashlib.sha256()
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                hasher.update(chunk)
            return hasher.hexdigest() == expected
    except OSError:
        return False

valid = all(
    path.is_file()
    and path.stat().st_size >= 256 * 1024
    and path.open("rb").read(4) == b"v/1\x01"
    and records[name].get("render_settings", {}).get("native_resolution")
    == [1920, 1080]
    and records[name].get("render_settings", {}).get("lattice_count") == 0
    and records[name].get("authoritative_exr_validation", {}).get("status")
    == "PASS"
    and records[name].get("authoritative_exr_validation", {}).get("operation")
    == "native_full_resolution_raster"
    and records[name].get("authoritative_exr_validation", {}).get("resolution")
    == [1920, 1080]
    and records[name].get("authoritative_exr_validation", {}).get(
        "pixel_content_nondegenerate"
    ) is True
    and records[name].get("camera", {}).get("target_grid_projection", {}).get(
        "method"
    ) == "single native full-resolution raster"
    and records[name].get("exact_collection_instance_expansion", {}).get(
        "enabled"
    ) is True
    and frame_quality_valid(records[name])
    and bundle_sha_valid(records[name], path)
    for name, path in pairs
)
raise SystemExit(0 if valid else 1)
PY
}

run_batches() {
    while IFS= read -r c2w_batch; do
        if [ -n "$c2w_view_filter" ]; then
            c2w_batch="$(filter_batch "$c2w_batch")"
        fi
        [ -n "$c2w_batch" ] || continue
        c2w_batch_index=$((c2w_batch_index + 1))
        if batch_complete "$c2w_batch"; then
            printf 'FULL12_ZLAYER_BATCH_SKIP utc=%s layer=%s batch=%s reason=valid_atomic_bundles\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                "$c2w_batch_index" >> "$c2w_log"
            continue
        fi
        c2w_batch_runtime="$c2w_runtime/batch_$(printf '%02d' "$c2w_batch_index")"
        mkdir -p "$c2w_batch_runtime/tmp"
        printf 'FULL12_ZLAYER_BATCH_BEGIN utc=%s layer=%s batch=%s views=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
            "$c2w_batch_index" "$c2w_batch" >> "$c2w_log"
        cd "$c2w_root" || return 98
        c2w_process_attempt=0
        c2w_code=1
        c2w_workbench_attempt_limit=3
        # The exact 707M-reference river/park partition and 725M-reference
        # lake partition both expose a deterministic Blender 5.1 Workbench
        # empty-buffer defect in particular cameras, while the identical
        # geometry/camera passes Eevee at native resolution.  One Workbench
        # attempt still handles ordinary transient failures; a pixel-validated
        # Eevee process is the bounded fallback only for these exact layers.
        case "$c2w_layer" in
            river5_nature|artificial_lake) c2w_workbench_attempt_limit=1 ;;
        esac
        while [ "$c2w_process_attempt" -lt "$c2w_workbench_attempt_limit" ]; do
            c2w_process_attempt=$((c2w_process_attempt + 1))
            TMPDIR="$c2w_batch_runtime/tmp" \
            XDG_CACHE_HOME="$c2w_shared_cache" \
            C2W_FULL12_RENDER_ENGINE="WORKBENCH" \
            C2W_FULL12_WORKBENCH_AA="16" \
            C2W_FULL12_RENDER_FORCE="$c2w_force" \
            /usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
                --disable-depsgraph-on-file-load -b "$c2w_pack" \
                --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
                -- "$c2w_layer" "$c2w_batch" >> "$c2w_log" 2>&1
            c2w_code=$?
            if [ "$c2w_code" -eq 0 ]; then
                break
            fi
            printf 'FULL12_ZLAYER_PROCESS_RETRY utc=%s layer=%s batch=%s attempt=%s exit=%s reason=fresh_workbench_process\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                "$c2w_batch_index" "$c2w_process_attempt" "$c2w_code" \
                >> "$c2w_log"
        done
        if [ "$c2w_code" -ne 0 ]; then
            case "$c2w_layer" in
                river5_nature|artificial_lake)
                    # Headless Blender selects one graphics device for Eevee.
                    # Serialize these rare high-memory fallbacks so two exact
                    # 700M-reference scenes never contend for the same VRAM.
                    exec 8> "$c2w_eevee_lock"
                    flock -x 8
                    # Never carry Eevee GPU state from one 700M-reference
                    # camera into the next. Blender 5.1 can abort or return a
                    # valid-header empty buffer after a successful first frame
                    # in the same process. Render each still-pending view in
                    # its own process and validate the atomic bundle before
                    # moving on. Geometry, camera, native grid, samples,
                    # materials, and complete-shadow policy stay unchanged.
                    c2w_eevee_views="$c2w_batch_runtime/eevee_views.txt"
                    printf '%s\n' "$c2w_batch" | tr ',' '\n' > "$c2w_eevee_views"
                    c2w_code=0
                    while IFS= read -r c2w_eevee_view; do
                        [ -n "$c2w_eevee_view" ] || continue
                        if [ "$c2w_force" != "1" ] && \
                            batch_complete "$c2w_eevee_view"
                        then
                            continue
                        fi
                        c2w_eevee_attempt=0
                        c2w_view_code=1
                        while [ "$c2w_eevee_attempt" -lt 4 ]; do
                            c2w_eevee_attempt=$((c2w_eevee_attempt + 1))
                            printf 'FULL12_ZLAYER_ENGINE_FALLBACK utc=%s layer=%s batch=%s view=%s attempt=%s from=BLENDER_WORKBENCH to=BLENDER_EEVEE reason=validated_workbench_empty_buffer process_scope=single_view\n' \
                                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                                "$c2w_batch_index" "$c2w_eevee_view" \
                                "$c2w_eevee_attempt" >> "$c2w_log"
                            TMPDIR="$c2w_batch_runtime/tmp" \
                            XDG_CACHE_HOME="$c2w_shared_cache" \
                            C2W_FULL12_RENDER_ENGINE="EEVEE" \
                            C2W_FULL12_EEVEE_SAMPLES="64" \
                            C2W_FULL12_RENDER_FORCE="$c2w_force" \
                            /usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
                                --disable-depsgraph-on-file-load -b "$c2w_pack" \
                                --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
                                -- "$c2w_layer" "$c2w_eevee_view" >> "$c2w_log" 2>&1
                            c2w_view_code=$?
                            if [ "$c2w_view_code" -eq 0 ] && \
                                { [ "$c2w_force" = "1" ] || \
                                    batch_complete "$c2w_eevee_view"; }
                            then
                                break
                            fi
                            printf 'FULL12_ZLAYER_EEVEE_PROCESS_RETRY utc=%s layer=%s batch=%s view=%s attempt=%s exit=%s reason=fresh_single_view_eevee_process\n' \
                                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                                "$c2w_batch_index" "$c2w_eevee_view" \
                                "$c2w_eevee_attempt" "$c2w_view_code" >> "$c2w_log"
                        done
                        if [ "$c2w_view_code" -ne 0 ] || \
                            { [ "$c2w_force" != "1" ] && \
                                ! batch_complete "$c2w_eevee_view"; }
                        then
                            c2w_code="$c2w_view_code"
                            [ "$c2w_code" -ne 0 ] || c2w_code=96
                            break
                        fi
                    done < "$c2w_eevee_views"
                    flock -u 8
                    ;;
            esac
        fi
        if [ "$c2w_code" -ne 0 ]; then
            printf 'FAIL %s layer=%s batch=%s exit=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                "$c2w_batch_index" "$c2w_code" > "$c2w_status"
            return "$c2w_code"
        fi
        printf 'FULL12_ZLAYER_BATCH_DONE utc=%s layer=%s batch=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
            "$c2w_batch_index" >> "$c2w_log"
    done
}

filter_batch() {
    c2w_filter_input="$1"
    c2w_filter_output=""
    c2w_filter_old_ifs="$IFS"
    IFS=,
    for c2w_filter_name in $c2w_filter_input; do
        case ",$c2w_view_filter," in
            *",$c2w_filter_name,"*)
                if [ -z "$c2w_filter_output" ]; then
                    c2w_filter_output="$c2w_filter_name"
                else
                    c2w_filter_output="$c2w_filter_output,$c2w_filter_name"
                fi
                ;;
        esac
    done
    IFS="$c2w_filter_old_ifs"
    printf '%s\n' "$c2w_filter_output"
}

if [ -n "$c2w_view_filter" ]; then
    # Repack a filtered recovery set into four-camera processes.  Keeping the
    # original 80-view row boundaries would turn a sparse 19-view correction
    # into ten expensive dependency-pack reloads; this preserves the same
    # renderer and per-view records while reducing it to five clean processes.
    c2w_filtered_batches="$c2w_runtime/filtered_batches.txt"
    printf '%s\n' "$c2w_view_filter" | tr ',' '\n' | awk '
        NF {
            line = line (line ? "," : "") $0
            count += 1
            if (count == 4) {
                print line
                line = ""
                count = 0
            }
        }
        END { if (count > 0) print line }
    ' > "$c2w_filtered_batches"
    run_batches < "$c2w_filtered_batches"
else
    run_batches <<'EOF'
city_southwest_panorama,city_southeast_panorama,city_northwest_panorama,city_northeast_panorama
city_high_aerial_panorama,city_top_down_coverage,residential_far,residential_near
commercial_far,commercial_near,park_far,park_near
leisure_far,leisure_near,education_far,education_near
civic_far,civic_near,health_far,health_near
industrial_far,industrial_near,roads_far,roads_near
school_far,school_main_gate_near,library_far,library_modern_entrance_near
school_library_shared_street,bank_commercial_far,bank_low_row_entrance_near,bank_headquarters_near
hospital_central_far,hospital_central_emergency_near,hospital_outskirts_far,hospital_outskirts_atrium_near
gas_pair_far,gas_north_near,gas_south_near,gas_west_far
gas_west_near,factory_group_far,factory_01_gable_near,factory_02_white_near
factory_03_gated_near,factory_04_highbay_near,fire_police_far,fire_station_near
police_west_near,police_east_near,police_library_near,artificial_lake_high
artificial_lake_pavilion_near,artificial_lake_shore_near,park_sculpture_near,park_fountain_near
park_fitness_near,leisure_facilities_relational,leisure_courts_near,leisure_fitness_near
residential_01_river3_indoor_near,residential_02_river3_north_extension_near,residential_03_all45_09_native_indoor_near,residential_delivery_01_food_delivery_locker_near
residential_delivery_02_parcel_locker_near,residential_delivery_03_delivery_station_near,commercial_streetfront_near,pharmacy_cvs_near
pharmacy_well_near,atm_row_front,road_intersection_street_level,crosswalk_oblique
diagonal_road_near,continuous_road_far,interior_residential_native,interior_commercial_bar
interior_school_cafeteria_threshold,interior_library_reading_room,interior_bank_atrium,interior_hospital_lobby
EOF
fi
c2w_code=$?
if [ "$c2w_code" -ne 0 ]; then
    exit "$c2w_code"
fi

python3 - "$c2w_manifest" <<'PY' >> "$c2w_log" 2>&1
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf8"))
assert data.get("status") == "PASS"
assert data.get("complete") is True
assert data.get("completed_count") == 80
assert len(data.get("completed_view_names", [])) == 80
for record in data.get("views", []):
    path = pathlib.Path(record["outputs"]["bundle"])
    assert path.stat().st_size >= 256 * 1024
    with path.open("rb") as handle:
        assert handle.read(4) == b"v/1\x01"
PY
c2w_code=$?
if [ "$c2w_code" -ne 0 ]; then
    printf 'FAIL %s layer=%s reason=final_manifest exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_code" \
        > "$c2w_status"
    exit "$c2w_code"
fi

printf 'PASS %s layer=%s views=80 chunked=true chunk_size=4\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"
printf 'FULL12_ZLAYER_FINISH layer=%s status=PASS views=80 chunked=true chunk_size=4\n' \
    "$c2w_layer" >> "$c2w_log"

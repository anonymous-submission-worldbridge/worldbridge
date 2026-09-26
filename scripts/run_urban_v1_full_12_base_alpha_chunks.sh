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

# Render the exact common base in short-lived Blender processes.  The base is
# dependency-heavy even though the compact scene has 46 structural roots;
# process every eight cameras prevents long-lived depsgraph/GPU allocations
# from accumulating.  Every frame is still rendered from the same production
# pack, at full resolution, with no simplify flag or geometry substitution.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_pack="$c2w_city/render_dependency_packs/base.blend"
c2w_runtime="$c2w_city/render_runtime/base_alpha_chunks"
c2w_log="$c2w_city/render_base.log"
c2w_status="$c2w_city/render_base.status"
c2w_mode="${1:-all}"
c2w_force="${C2W_FULL12_RENDER_FORCE:-0}"
c2w_batch_index=0
c2w_shared_cache="$c2w_city/render_runtime/shared_material_cache"

mkdir -p "$c2w_runtime" "$c2w_shared_cache"
if [ "$c2w_mode" = "resume_after_34" ]; then
    # Frames 1--34 were atomically replaced by the initial transparent-base
    # process before the host killed that long-lived process with exit 137.
    c2w_force=1
    printf '\nFULL12_BASE_ALPHA_RESUME utc=%s after=34\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
else
    touch "$c2w_log"
fi
printf 'FULL12_BASE_ALPHA_RUN_BEGIN utc=%s mode=%s force=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_mode" "$c2w_force" \
    >> "$c2w_log"

if [ ! -s "$c2w_pack" ]; then
    printf 'FAIL %s layer=base reason=missing_pack\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 97
fi

c2w_manifest="$c2w_city/renders/zdepth_layers/layer_manifest_base.json"
if [ "$c2w_mode" = "all" ] && [ "$c2w_force" != "1" ] && \
    python3 - "$c2w_manifest" <<'PY' >> "$c2w_log" 2>&1
import hashlib
import json
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
        and evidence.get("parts") == ["BaseColor", "BaseDepth"]
        and evidence.get("pixel_content_nondegenerate") is True
        and projection.get("method") == "single native full-resolution raster"
        and projection.get("native_resolution") == [1920, 1080]
        and projection.get("resizing") is False
        and projection.get("resampling") is False
        and projection.get("interpolation") is False
        and settings.get("engine") == "BLENDER_WORKBENCH"
        and settings.get("native_resolution") == [1920, 1080]
        and settings.get("lattice_count") == 0
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
    printf 'PASS %s layer=base views=80 transparent_no_hit_alpha=true chunked=true reused=true\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    printf 'FULL12_BASE_ALPHA_REUSE_COMPLETE utc=%s views=80 validation=sha256_native_evidence\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"
    exit 0
fi

printf 'RUNNING %s layer=base mode=%s chunk_size=8\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_mode" > "$c2w_status"

run_batches() {
    while IFS= read -r c2w_batch; do
        [ -n "$c2w_batch" ] || continue
        c2w_batch_index=$((c2w_batch_index + 1))
        c2w_batch_runtime="$c2w_runtime/batch_$(printf '%02d' "$c2w_batch_index")"
        mkdir -p "$c2w_batch_runtime/tmp"
        printf 'FULL12_BASE_ALPHA_BATCH_BEGIN utc=%s batch=%s views=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_batch_index" "$c2w_batch" \
            >> "$c2w_log"
        cd "$c2w_root" || exit 98
        c2w_process_attempt=0
        c2w_code=1
        while [ "$c2w_process_attempt" -lt 3 ]; do
            c2w_process_attempt=$((c2w_process_attempt + 1))
            TMPDIR="$c2w_batch_runtime/tmp" \
            XDG_CACHE_HOME="$c2w_shared_cache" \
            C2W_FULL12_RENDER_ENGINE="WORKBENCH" \
            C2W_FULL12_WORKBENCH_AA="16" \
            C2W_FULL12_RENDER_FORCE="$c2w_force" \
            /usr/local/bin/blender --disable-depsgraph-on-file-load -b "$c2w_pack" \
                --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
                -- base "$c2w_batch" >> "$c2w_log" 2>&1
            c2w_code=$?
            if [ "$c2w_code" -eq 0 ]; then
                break
            fi
            printf 'FULL12_BASE_ALPHA_PROCESS_RETRY utc=%s batch=%s attempt=%s exit=%s reason=fresh_workbench_process\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_batch_index" \
                "$c2w_process_attempt" "$c2w_code" >> "$c2w_log"
        done
        if [ "$c2w_code" -ne 0 ]; then
            printf 'FAIL %s layer=base batch=%s exit=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_batch_index" "$c2w_code" \
                > "$c2w_status"
            return "$c2w_code"
        fi
        printf 'FULL12_BASE_ALPHA_BATCH_DONE utc=%s batch=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_batch_index" >> "$c2w_log"
    done
}

if [ "$c2w_mode" = "resume_after_34" ]; then
    run_batches <<'EOF' || exit $?
hospital_outskirts_far,hospital_outskirts_atrium_near,gas_pair_far,gas_north_near,gas_south_near,gas_west_far,gas_west_near,factory_group_far
factory_01_gable_near,factory_02_white_near,factory_03_gated_near,factory_04_highbay_near,fire_police_far,fire_station_near,police_west_near,police_east_near
police_library_near,artificial_lake_high,artificial_lake_pavilion_near,artificial_lake_shore_near,park_sculpture_near,park_fountain_near,park_fitness_near,leisure_facilities_relational
leisure_courts_near,leisure_fitness_near,residential_01_river3_indoor_near,residential_02_river3_north_extension_near,residential_03_all45_09_native_indoor_near,residential_delivery_01_food_delivery_locker_near,residential_delivery_02_parcel_locker_near,residential_delivery_03_delivery_station_near
commercial_streetfront_near,pharmacy_cvs_near,pharmacy_well_near,atm_row_front,road_intersection_street_level,crosswalk_oblique,diagonal_road_near,continuous_road_far
interior_residential_native,interior_commercial_bar,interior_school_cafeteria_threshold,interior_library_reading_room,interior_bank_atrium,interior_hospital_lobby
EOF
elif [ "$c2w_mode" = "all" ]; then
    run_batches <<'EOF' || exit $?
city_southwest_panorama,city_southeast_panorama,city_northwest_panorama,city_northeast_panorama,city_high_aerial_panorama,city_top_down_coverage,residential_far,residential_near
commercial_far,commercial_near,park_far,park_near,leisure_far,leisure_near,education_far,education_near
civic_far,civic_near,health_far,health_near,industrial_far,industrial_near,roads_far,roads_near
school_far,school_main_gate_near,library_far,library_modern_entrance_near,school_library_shared_street,bank_commercial_far,bank_low_row_entrance_near,bank_headquarters_near
hospital_central_far,hospital_central_emergency_near,hospital_outskirts_far,hospital_outskirts_atrium_near,gas_pair_far,gas_north_near,gas_south_near,gas_west_far
gas_west_near,factory_group_far,factory_01_gable_near,factory_02_white_near,factory_03_gated_near,factory_04_highbay_near,fire_police_far,fire_station_near
police_west_near,police_east_near,police_library_near,artificial_lake_high,artificial_lake_pavilion_near,artificial_lake_shore_near,park_sculpture_near,park_fountain_near
park_fitness_near,leisure_facilities_relational,leisure_courts_near,leisure_fitness_near,residential_01_river3_indoor_near,residential_02_river3_north_extension_near,residential_03_all45_09_native_indoor_near,residential_delivery_01_food_delivery_locker_near
residential_delivery_02_parcel_locker_near,residential_delivery_03_delivery_station_near,commercial_streetfront_near,pharmacy_cvs_near,pharmacy_well_near,atm_row_front,road_intersection_street_level,crosswalk_oblique
diagonal_road_near,continuous_road_far,interior_residential_native,interior_commercial_bar,interior_school_cafeteria_threshold,interior_library_reading_room,interior_bank_atrium,interior_hospital_lobby
EOF
else
    printf 'FAIL %s layer=base reason=unknown_mode mode=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_mode" > "$c2w_status"
    exit 96
fi

python3 -c "import json,pathlib; p=pathlib.Path('$c2w_city/renders/zdepth_layers/layer_manifest_base.json'); d=json.loads(p.read_text()); assert d.get('status') == 'PASS' and d.get('complete') is True and d.get('completed_count') == 80 and len(d.get('completed_view_names', [])) == 80" \
    >> "$c2w_log" 2>&1
c2w_code=$?
if [ "$c2w_code" -ne 0 ]; then
    printf 'FAIL %s layer=base reason=final_manifest exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" > "$c2w_status"
    exit "$c2w_code"
fi

printf 'PASS %s layer=base views=80 transparent_no_hit_alpha=true chunked=true\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
printf 'FULL12_BASE_ALPHA_FINISH utc=%s status=PASS views=80\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "$c2w_log"

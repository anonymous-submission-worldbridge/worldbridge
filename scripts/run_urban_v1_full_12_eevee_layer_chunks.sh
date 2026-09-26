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

# Upgrade one exact production render partition to Eevee in short-lived
# four-camera processes.  Every camera keeps the same production collection
# instances, matrices, materials, 1920x1080 raster, transparent no-hit alpha,
# shared road/ground receivers, and 32-bit camera-space depth.  The only
# changed variable is the final shading engine: Eevee evaluates the authored
# node materials that Workbench cannot represent.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_layer="${1:?expected full-12 z-depth layer key}"
c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
c2w_runtime="$c2w_city/render_runtime/eevee_quality/$c2w_layer"
c2w_log="$c2w_city/render_quality_${c2w_layer}.log"
c2w_status="$c2w_city/render_quality_${c2w_layer}.status"
c2w_manifest="$c2w_city/renders/zdepth_layers/layer_manifest_${c2w_layer}.json"
c2w_samples="${C2W_FULL12_EEVEE_SAMPLES:-32}"
c2w_batch_index=0
c2w_lock="$c2w_city/render_runtime/$c2w_layer/layer_render.lock"

mkdir -p "$c2w_runtime" "$(dirname "$c2w_lock")"
# The Workbench production matrix and this upgrade share output paths.  The
# lock guarantees the quality pass starts only after the authoritative layer
# writer has completed, even when an independently prefetched layer converges.
exec 9> "$c2w_lock"
flock -x 9
touch "$c2w_log"
printf '\nFULL12_EEVEE_LAYER_RUN utc=%s layer=%s samples=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_samples" \
    >> "$c2w_log"
printf 'RUNNING %s layer=%s engine=BLENDER_EEVEE samples=%s chunk_size=4\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_samples" \
    > "$c2w_status"

if [ ! -s "$c2w_pack" ]; then
    printf 'FAIL %s layer=%s reason=missing_pack\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" > "$c2w_status"
    exit 97
fi

# A resumed quality run skips only bundles whose own frame record proves they
# were rendered by Eevee at the requested sample budget.  A valid older
# Workbench EXR is deliberately not considered complete.
batch_complete() {
    c2w_names="$1"
    python3 - "$c2w_manifest" "$c2w_names" "$c2w_samples" <<'PY' \
        >> "$c2w_log" 2>&1
import json
import pathlib
import sys

manifest = pathlib.Path(sys.argv[1])
names = [name for name in sys.argv[2].split(",") if name]
minimum_samples = int(sys.argv[3])
if not manifest.is_file():
    raise SystemExit(1)
try:
    data = json.loads(manifest.read_text(encoding="utf8"))
    records = {record["name"]: record for record in data.get("views", [])}
    selected = [records[name] for name in names]
    paths = [pathlib.Path(record["outputs"]["bundle"]) for record in selected]
except (OSError, ValueError, KeyError, TypeError):
    raise SystemExit(1)
valid_quality = all(
    record.get("render_settings", {}).get("engine")
        in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
    and int(record.get("render_settings", {}).get("samples") or 0)
        >= minimum_samples
    for record in selected
)
valid_files = all(
    path.is_file()
    and path.stat().st_size > 1024
    and path.read_bytes()[:4] == b"v/1\x01"
    for path in paths
)
raise SystemExit(0 if valid_quality and valid_files else 1)
PY
}

run_batches() {
    while IFS= read -r c2w_batch; do
        [ -n "$c2w_batch" ] || continue
        c2w_batch_index=$((c2w_batch_index + 1))
        if batch_complete "$c2w_batch"; then
            printf 'FULL12_EEVEE_BATCH_SKIP utc=%s layer=%s batch=%s reason=verified_eevee_bundles\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                "$c2w_batch_index" >> "$c2w_log"
            continue
        fi
        c2w_batch_runtime="$c2w_runtime/batch_$(printf '%02d' "$c2w_batch_index")"
        mkdir -p "$c2w_batch_runtime/tmp" "$c2w_batch_runtime/cache"
        printf 'FULL12_EEVEE_BATCH_BEGIN utc=%s layer=%s batch=%s views=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
            "$c2w_batch_index" "$c2w_batch" >> "$c2w_log"
        cd "$c2w_root" || return 98
        TMPDIR="$c2w_batch_runtime/tmp" \
        XDG_CACHE_HOME="$c2w_batch_runtime/cache" \
        C2W_FULL12_RENDER_ENGINE="EEVEE" \
        C2W_FULL12_EEVEE_SAMPLES="$c2w_samples" \
        C2W_FULL12_RENDER_FORCE="1" \
        /usr/local/bin/blender --disable-depsgraph-on-file-load -b "$c2w_pack" \
            --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
            -- "$c2w_layer" "$c2w_batch" >> "$c2w_log" 2>&1
        c2w_code=$?
        if [ "$c2w_code" -ne 0 ]; then
            printf 'FAIL %s layer=%s batch=%s exit=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                "$c2w_batch_index" "$c2w_code" > "$c2w_status"
            return "$c2w_code"
        fi
        printf 'FULL12_EEVEE_BATCH_DONE utc=%s layer=%s batch=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
            "$c2w_batch_index" >> "$c2w_log"
    done
}

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
c2w_code=$?
if [ "$c2w_code" -ne 0 ]; then
    exit "$c2w_code"
fi

python3 - "$c2w_manifest" "$c2w_samples" <<'PY' >> "$c2w_log" 2>&1
import json
import pathlib
import sys

data = json.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf8"))
minimum_samples = int(sys.argv[2])
assert data.get("status") == "PASS"
assert data.get("complete") is True
assert data.get("completed_count") == 80
assert len(data.get("completed_view_names", [])) == 80
settings = data.get("render_settings", {})
assert settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
assert int(settings.get("samples") or 0) >= minimum_samples
records = data.get("views", [])
assert len(records) == 80
for record in records:
    frame_settings = record.get("render_settings", {})
    assert frame_settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
    assert int(frame_settings.get("samples") or 0) >= minimum_samples
    path = pathlib.Path(record["outputs"]["bundle"])
    assert path.stat().st_size > 1024
    assert path.read_bytes()[:4] == b"v/1\x01"
PY
c2w_code=$?
if [ "$c2w_code" -ne 0 ]; then
    printf 'FAIL %s layer=%s reason=final_quality_manifest exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_code" \
        > "$c2w_status"
    exit "$c2w_code"
fi

printf 'PASS %s layer=%s views=80 engine=BLENDER_EEVEE samples=%s chunked=true chunk_size=4\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_samples" \
    > "$c2w_status"
printf 'FULL12_EEVEE_LAYER_FINISH layer=%s status=PASS views=80 samples=%s\n' \
    "$c2w_layer" "$c2w_samples" >> "$c2w_log"

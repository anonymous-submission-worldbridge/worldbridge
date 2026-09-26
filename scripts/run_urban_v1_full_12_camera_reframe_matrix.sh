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

# Authoritative recovery matrix for the source-authored camera revision.  It
# invokes the production per-layer renderer and rewrites only the 19 views
# whose framing changed; every other committed 1920x1080 EXR remains intact.
# The layer manifests are still finalized as complete 80-view manifests.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_status="$c2w_city/camera_reframe_matrix.status"
c2w_log="$c2w_city/camera_reframe_matrix.log"
c2w_views="residential_near,park_near,bank_low_row_entrance_near,bank_headquarters_near,police_library_near,artificial_lake_pavilion_near,artificial_lake_shore_near,park_fitness_near,leisure_fitness_near,residential_01_river3_indoor_near,residential_02_river3_north_extension_near,residential_delivery_01_food_delivery_locker_near,residential_delivery_02_parcel_locker_near,residential_delivery_03_delivery_station_near,diagonal_road_near,interior_residential_native,interior_school_cafeteria_threshold,interior_bank_atrium,interior_hospital_lobby"

# Pair each very large exact-reference pack with a smaller pack.  Two
# short-lived Blender processes is the already validated memory-safe ceiling.
c2w_layers="river5_nature base artificial_lake health river3_residential education_buildings all45_unique_buildings commercial_services industrial public_safety residential_delivery all44_leisure park_leisure_support"
c2w_force="${C2W_FULL12_RENDER_FORCE:-1}"
c2w_fail=0

: > "$c2w_log"
printf 'RUNNING %s parallelism=2 layers=13 views=19 revision=full12_authored_asset_framing_v2\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
set -- $c2w_layers

while [ "$#" -gt 0 ]; do
    c2w_pids=""
    c2w_pair=""
    c2w_index=0
    while [ "$#" -gt 0 ] && [ "$c2w_index" -lt 2 ]; do
        c2w_layer="$1"
        shift
        c2w_index=$((c2w_index + 1))
        printf 'FULL12_REFRAME_MATRIX_LAUNCH utc=%s layer=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
        C2W_FULL12_RENDER_FORCE="$c2w_force" \
        C2W_FULL12_VIEW_FILTER="$c2w_views" \
        C2W_FULL12_GPU_BACKEND=vulkan \
            /bin/sh "$c2w_root/scripts/run_urban_v1_full_12_zdepth_layer_chunks.sh" \
            "$c2w_layer" &
        c2w_pids="$c2w_pids $!"
        c2w_pair="$c2w_pair $c2w_layer"
    done
    c2w_position=1
    for c2w_pid in $c2w_pids; do
        c2w_layer="$(printf '%s\n' "$c2w_pair" | awk -v n="$c2w_position" '{print $n}')"
        if wait "$c2w_pid"; then
            printf 'FULL12_REFRAME_MATRIX_DONE utc=%s layer=%s status=PASS\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
        else
            c2w_wait_code="$?"
            c2w_layer_status="$c2w_city/render_${c2w_layer}.status"
            c2w_layer_state="MISSING"
            if [ -f "$c2w_layer_status" ]; then
                read -r c2w_layer_state c2w_rest < "$c2w_layer_status" || true
            fi
            if [ "$c2w_layer_state" = "PASS" ]; then
                printf 'FULL12_REFRAME_MATRIX_DONE utc=%s layer=%s status=PASS recovered_from_wrapper_exit=%s authoritative_layer_status=PASS\n' \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                    "$c2w_wait_code" >> "$c2w_log"
            else
                c2w_fail=1
                printf 'FULL12_REFRAME_MATRIX_DONE utc=%s layer=%s status=FAIL exit=%s layer_status=%s\n' \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" \
                    "$c2w_wait_code" "$c2w_layer_state" >> "$c2w_log"
            fi
        fi
        c2w_position=$((c2w_position + 1))
    done
done

# A wrapper PASS is not enough for a camera repair.  Independently require the
# canonical base shot hash, evaluated pose and revision to match all 12 asset
# layers for every corrected view before publishing matrix PASS.
if [ "$c2w_fail" -eq 0 ]; then
    if ! python3 - "$c2w_city" "$c2w_views" >> "$c2w_log" 2>&1 <<'PY'
import json
import pathlib
import sys

city = pathlib.Path(sys.argv[1])
names = [name for name in sys.argv[2].split(",") if name]
layer_root = city / "renders/zdepth_layers"
layers = (
    "base", "river5_nature", "river3_residential",
    "all45_unique_buildings", "all44_leisure", "commercial_services",
    "residential_delivery", "park_leisure_support", "artificial_lake",
    "education_buildings", "public_safety", "health", "industrial",
)
records = {}
for layer in layers:
    data = json.loads(
        (layer_root / f"layer_manifest_{layer}.json").read_text(encoding="utf8")
    )
    assert data.get("status") == "PASS" and data.get("complete") is True
    assert data.get("completed_count") == 80
    records[layer] = {item["name"]: item for item in data.get("views", [])}
    assert len(records[layer]) == 80

for name in names:
    base = records["base"][name]
    revision = base.get("camera_composition_revision")
    shot_hash = base.get("shot_spec_sha256")
    assert revision == "full12_authored_asset_framing_v2"
    assert isinstance(shot_hash, str) and len(shot_hash) == 64
    pose = {
        key: base["camera"].get(key)
        for key in (
            "mode", "projection", "location", "target", "lens_mm", "ortho_scale"
        )
    }
    for layer in layers:
        record = records[layer][name]
        assert record.get("camera_composition_revision") == revision
        assert record.get("shot_spec_sha256") == shot_hash
        assert record.get("camera", {}).get("matrix_validation", {}).get("pass") is True
        candidate = {
            key: record["camera"].get(key)
            for key in pose
        }
        assert candidate == pose, (layer, name, candidate, pose)
        bundle = pathlib.Path(record["outputs"]["bundle"])
        assert bundle.is_file() and bundle.stat().st_size >= 256 * 1024
print(
    f"FULL12_REFRAME_MATRIX_CAMERA_AUDIT PASS layers={len(layers)} "
    f"views={len(names)} bundles={len(layers) * len(names)}"
)
PY
    then
        c2w_fail=1
        printf 'FULL12_REFRAME_MATRIX_CAMERA_AUDIT FAIL\n' >> "$c2w_log"
    fi
fi

if [ "$c2w_fail" -eq 0 ]; then
    printf 'PASS %s parallelism=2 layers=13 views=19 revision=full12_authored_asset_framing_v2\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
else
    printf 'FAIL %s parallelism=2 layers=13 views=19 revision=full12_authored_asset_framing_v2\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
fi
exit "$c2w_fail"

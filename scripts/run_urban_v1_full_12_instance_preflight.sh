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

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_output="$c2w_city/render_runtime/diagnostics/instance_preflight_all"
c2w_log="$c2w_output/preflight.log"
c2w_status="$c2w_output/preflight.status"
c2w_layers="river5_nature river3_residential all45_unique_buildings all44_leisure commercial_services residential_delivery park_leisure_support artificial_lake education_buildings public_safety health industrial"

mkdir -p "$c2w_output/cache"
: > "$c2w_log"
printf 'RUNNING %s layers=12\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

for c2w_layer in $c2w_layers; do
    c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
    c2w_tmp="$c2w_output/tmp_$c2w_layer"
    mkdir -p "$c2w_tmp"
    printf 'FULL12_PREFLIGHT_BEGIN utc=%s layer=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
    TMPDIR="$c2w_tmp" \
        XDG_CACHE_HOME="$c2w_output/cache" \
        C2W_FULL12_LAYER_ROOT="$c2w_output" \
        C2W_FULL12_PREFLIGHT_ONLY="1" \
        C2W_FULL12_RENDER_ENGINE="WORKBENCH" \
        C2W_FULL12_WORKBENCH_AA="16" \
        /usr/local/bin/blender --disable-depsgraph-on-file-load -b "$c2w_pack" \
            --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
            -- "$c2w_layer" city_northwest_panorama >> "$c2w_log" 2>&1
    c2w_code="$?"
    if [ "$c2w_code" -ne 0 ]; then
        printf 'FAIL %s layer=%s exit=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_code" \
            > "$c2w_status"
        exit 1
    fi
    printf 'FULL12_PREFLIGHT_DONE utc=%s layer=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_log"
done

python3 - "$c2w_output" <<'PY' >> "$c2w_log" 2>&1
import json
import pathlib
import sys

root = pathlib.Path(sys.argv[1])
reports = sorted(root.glob("preflight_*.json"))
assert len(reports) == 12
for path in reports:
    data = json.loads(path.read_text(encoding="utf8"))
    assert data.get("status") == "PASS"
    assert data.get("production_blend_unchanged") is True
    evidence = data.get("exact_collection_instance_expansion", {})
    assert evidence.get("enabled") is True
    assert evidence.get("expanded_object_count", 0) > 0
    assert evidence.get("all_authored_data_shared") is True
    assert evidence.get("all_world_matrices_preserved") is True
    assert (
        float(evidence.get("maximum_world_matrix_error", 1.0)) <= 1.0e-4
        or float(evidence.get("maximum_world_matrix_relative_error", 1.0))
        <= 5.0e-7
    )
    assert evidence.get("maximum_world_matrix_absolute_error_allowed") == 1.0e-4
    assert evidence.get("maximum_world_matrix_relative_error_allowed") == 5.0e-7
    assert evidence.get("exact_svd_affine_factorization") is True
    assert evidence.get("affine_transform_helper_count", -1) == 2 * evidence.get(
        "sheared_object_count", -1
    )
    assert float(evidence.get("maximum_svd_factorization_error", 1.0)) <= 1.0e-10
    assert evidence.get("modifiers_applied") is False
    assert evidence.get("mesh_data_realized") is False
    assert evidence.get("geometry_simplification") is False
    assert evidence.get("omitted_visible_geometry_count") == 0
    assert evidence.get("source_files_saved") is False
    assert evidence.get("production_blend_saved") is False
print("FULL12_PREFLIGHT_MATRIX_PASS layers=12")
PY
if [ "$?" -ne 0 ]; then
    printf 'FAIL %s stage=aggregate_validation\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 2
fi

printf 'PASS %s layers=12\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

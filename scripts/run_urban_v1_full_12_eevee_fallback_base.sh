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

# Render same-camera Eevee base references only for river/park or artificial-
# lake frames that had to use the validated Eevee fallback.  The delivery
# compositor divides the fallback Combined receiver color by this baseline and
# applies the exact relative illumination to the authoritative Workbench base.
# This preserves shadows/reflections without importing Eevee's darker ground
# palette.

c2w_root="${WORLDBRIDGE_ROOT}"
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_12"
c2w_river5_manifest="$c2w_city/renders/zdepth_layers/layer_manifest_river5_nature.json"
c2w_lake_manifest="$c2w_city/renders/zdepth_layers/layer_manifest_artificial_lake.json"
c2w_layer_root="$c2w_city/render_runtime/eevee_fallback_base"
c2w_runtime="$c2w_city/render_runtime/eevee_fallback_base_runtime"
c2w_manifest="$c2w_layer_root/layer_manifest_base.json"
c2w_log="$c2w_city/eevee_fallback_base.log"
c2w_status="$c2w_city/eevee_fallback_base.status"
c2w_pack="$c2w_city/render_dependency_packs/base.blend"
c2w_gpu_backend="${C2W_FULL12_GPU_BACKEND:-vulkan}"

case "$c2w_gpu_backend" in
    opengl|vulkan) ;;
    *)
        printf 'FAIL %s reason=invalid_gpu_backend value=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_gpu_backend" \
            > "$c2w_status"
        exit 94
        ;;
esac

mkdir -p "$c2w_layer_root" "$c2w_runtime/tmp" "$c2w_runtime/cache"
: > "$c2w_log"
printf 'RUNNING %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"

c2w_names_file="$c2w_runtime/fallback_view_names.txt"
if ! python3 - "$c2w_river5_manifest" "$c2w_lake_manifest" \
    > "$c2w_names_file" <<'PY'
import json
import pathlib
import sys

names = set()
for source in sys.argv[1:]:
    data = json.loads(pathlib.Path(source).read_text(encoding="utf8"))
    layer = data.get("layer_key")
    if layer not in {"river5_nature", "artificial_lake"}:
        raise SystemExit(f"unsupported fallback layer manifest: {layer}")
    if data.get("status") != "PASS" or data.get("complete") is not True:
        raise SystemExit(f"{layer} must be complete before fallback-base rendering")
    for record in data.get("views", []):
        engine = record.get("render_settings", {}).get("engine")
        if engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
            names.add(record["name"])
        elif engine != "BLENDER_WORKBENCH":
            raise SystemExit(
                f"unsupported {layer} frame engine: "
                f"{record.get('name')}={engine}"
            )
print(",".join(sorted(names)))
PY
then
    printf 'FAIL %s stage=select_fallback_views\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 95
fi
c2w_names="$(tr -d '\n' < "$c2w_names_file")"

if [ -z "$c2w_names" ]; then
    printf 'PASS %s views=0 reason=no_eevee_fallback_frames\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_status"
    exit 0
fi

c2w_attempt=0
c2w_code=1
while [ "$c2w_attempt" -lt 2 ]; do
    c2w_attempt=$((c2w_attempt + 1))
    cd "$c2w_root"
    if TMPDIR="$c2w_runtime/tmp" \
        XDG_CACHE_HOME="$c2w_runtime/cache" \
        C2W_FULL12_LAYER_ROOT="$c2w_layer_root" \
        C2W_FULL12_RENDER_ENGINE="EEVEE" \
        C2W_FULL12_EEVEE_SAMPLES="64" \
        /usr/local/bin/blender --gpu-backend "$c2w_gpu_backend" \
            --disable-depsgraph-on-file-load -b "$c2w_pack" \
            --python "$c2w_root/scripts/render_urban_v1_full_12_zdepth_layer.py" \
            -- base "$c2w_names" >> "$c2w_log" 2>&1
    then
        c2w_code=0
    else
        c2w_code=$?
    fi
    if [ "$c2w_code" -eq 0 ]; then
        break
    fi
    printf 'FULL12_EEVEE_BASE_PROCESS_RETRY utc=%s attempt=%s exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_attempt" "$c2w_code" \
        >> "$c2w_log"
done
if [ "$c2w_code" -ne 0 ]; then
    printf 'FAIL %s stage=render exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" > "$c2w_status"
    exit "$c2w_code"
fi

if python3 - "$c2w_manifest" "$c2w_names" "$c2w_city" \
    "$c2w_river5_manifest" "$c2w_lake_manifest" <<'PY' \
    >> "$c2w_log" 2>&1
import hashlib
import json
import pathlib
import sys

manifest_path = pathlib.Path(sys.argv[1]).resolve()
expected = {name for name in sys.argv[2].split(",") if name}
city = pathlib.Path(sys.argv[3]).resolve()
fallback_sources = {}
for source in sys.argv[4:]:
    source_data = json.loads(pathlib.Path(source).read_text(encoding="utf8"))
    layer = source_data.get("layer_key")
    assert layer in {"river5_nature", "artificial_lake"}
    assert source_data.get("status") == "PASS"
    assert source_data.get("complete") is True
    for source_record in source_data.get("views", []):
        engine = source_record.get("render_settings", {}).get("engine")
        assert engine in {
            "BLENDER_WORKBENCH", "BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"
        }
        if engine in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}:
            fallback_sources.setdefault(source_record["name"], []).append(
                (layer, source_record)
            )
data = json.loads(manifest_path.read_text(encoding="utf8"))
records = {record["name"]: record for record in data.get("views", [])}
assert expected and expected == set(fallback_sources) and expected.issubset(records)
assert data.get("production_blend_unchanged") is True
for name in expected:
    record = records[name]
    settings = record.get("render_settings", {})
    sync = settings.get("workbench_material_sync", {})
    assert settings.get("engine") in {"BLENDER_EEVEE", "BLENDER_EEVEE_NEXT"}
    assert settings.get("resolution") == [1920, 1080]
    assert int(settings.get("samples") or 0) >= 32
    assert settings.get("mesh_simplification") is False
    assert sync.get("enabled") is False
    assert sync.get("node_graphs_changed") is False
    assert sync.get("source_files_saved") is False
    assert sync.get("production_blend_saved") is False
    assert record.get("camera", {}).get("matrix_validation", {}).get("pass") is True
    baseline_camera = record.get("camera", {})
    for layer, source_record in fallback_sources[name]:
        source_camera = source_record.get("camera", {})
        for key in (
            "mode", "projection", "location", "target", "lens_mm", "ortho_scale"
        ):
            assert baseline_camera.get(key) == source_camera.get(key), (layer, name, key)
        source_revision = source_record.get("camera_composition_revision")
        source_spec = source_record.get("shot_spec_sha256")
        if source_revision is not None or source_spec is not None:
            assert record.get("camera_composition_revision") == source_revision
            assert record.get("shot_spec_sha256") == source_spec
    evidence = record.get("authoritative_exr_validation", {})
    assert evidence.get("status") == "PASS"
    assert evidence.get("operation") == "native_full_resolution_raster"
    assert evidence.get("resolution") == [1920, 1080]
    assert evidence.get("parts") == ["BaseColor", "BaseDepth"]
    assert evidence.get("pixel_content_nondegenerate") is True
    path = pathlib.Path(record["outputs"]["bundle"]).resolve()
    assert path.is_relative_to((city / "render_runtime/eevee_fallback_base/base").resolve())
    assert path.is_file() and path.stat().st_size >= 256 * 1024
    assert path.read_bytes()[:4] == b"v/1\x01"
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert record["sha256"]["bundle"] == digest
print(json.dumps({"status": "PASS", "validated_views": sorted(expected)}))
PY
then
    c2w_code=0
else
    c2w_code=$?
    printf 'FAIL %s stage=validation exit=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_code" > "$c2w_status"
    exit "$c2w_code"
fi

c2w_count="$(printf '%s\n' "$c2w_names" | awk -F, '{print NF}')"
printf 'PASS %s views=%s relative_lighting_reference=true\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_count" > "$c2w_status"

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
c2w_city="$c2w_root/infinigen/outputs/outdoor_full_demo/urban_v1_full_13"
c2w_run_id="${C2W_FULL13_RUN_ID:-full13-$(date -u +%Y%m%dT%H%M%S)}"
c2w_blender="/usr/local/bin/blender"
c2w_openexr_python="${WORLDBRIDGE_PYTHON}"
c2w_log="$c2w_city/pipeline.log"
c2w_status="$c2w_city/pipeline.status.json"
c2w_pipeline_unit="${C2W_FULL13_PIPELINE_UNIT:-worldbridge-full13-pipeline.service}"
c2w_layers="river5_nature river3_residential artificial_lake all45_unique_buildings education_buildings commercial_services industrial public_safety residential_delivery all44_leisure park_leisure_support health full13_unique_urban_fabric full13_semantic_interiors full13_public_realm base"

mkdir -p "$c2w_city/render_runtime" "$c2w_city/renders/zdepth_layers"
: > "$c2w_log"
printf 'FULL13_PIPELINE_BEGIN utc=%s run_id=%s unit=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" "$c2w_pipeline_unit" >> "$c2w_log"

status() {
    c2w_state="$1"
    c2w_stage="$2"
    printf '{"schema":"agent.full13.pipeline.status.v1","run_id":"%s","status":"%s","stage":"%s","updated_utc":"%s"}\n' \
        "$c2w_run_id" "$c2w_state" "$c2w_stage" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
        > "$c2w_status.writing"
    mv "$c2w_status.writing" "$c2w_status"
}

run_stage() {
    c2w_name="$1"
    shift
    status RUNNING "$c2w_name"
    printf 'FULL13_STAGE_BEGIN utc=%s run_id=%s stage=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" "$c2w_name" >> "$c2w_log"
    if C2W_FULL13_RUN_ID="$c2w_run_id" "$@" >> "$c2w_log" 2>&1; then
        printf 'FULL13_STAGE_DONE utc=%s run_id=%s stage=%s status=PASS\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" "$c2w_name" >> "$c2w_log"
    else
        c2w_code=$?
        printf 'FULL13_STAGE_DONE utc=%s run_id=%s stage=%s status=FAIL exit=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" "$c2w_name" "$c2w_code" >> "$c2w_log"
        status FAIL "$c2w_name"
        exit "$c2w_code"
    fi
}

cd "$c2w_root"

# Stage gates and hashes inside each script make completed immutable work O(1)
# to validate on restart.  The procedural pack is rebuilt for this run ID so
# every final artifact shares one traceable run.
if python3 -c 'import hashlib,json,pathlib,sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); q=pathlib.Path(d["pack"]); H=lambda x:hashlib.sha256(pathlib.Path(x).read_bytes()).hexdigest(); assert d["status"]=="PASS" and d["run_id"]==sys.argv[2] and q.is_file() and q.stat().st_size==d["bytes"] and H(q)==d["sha256"] and H(sys.argv[3])==d["consuming_generator_sha256"] and H(sys.argv[4])==d["builder_sha256"] and d["production_connection"]["detached_demo"] is False and min(d["observed_part_counts"]["bank_atrium"],d["observed_part_counts"]["hospital_lobby"])>=150' \
    "$c2w_city/asset_packs/full13_semantic_public_interiors.json" "$c2w_run_id" \
    "$c2w_root/scripts/generate_urban_v1_full_13.py" \
    "$c2w_root/scripts/build_urban_v1_full_13_semantic_pack.py" 2>/dev/null
then
    printf 'FULL13_STAGE_CACHE_HIT run_id=%s stage=semantic_public_interiors_pack\n' "$c2w_run_id" >> "$c2w_log"
else
    run_stage semantic_public_interiors_pack "$c2w_blender" -b --factory-startup \
        --python "$c2w_root/scripts/build_urban_v1_full_13_semantic_pack.py"
fi
if python3 -c 'import hashlib,json,pathlib,sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); q=pathlib.Path(d["pack"]); H=lambda x:hashlib.sha256(pathlib.Path(x).read_bytes()).hexdigest(); assert d["status"]=="PASS" and d["run_id"]==sys.argv[2] and q.is_file() and q.stat().st_size==d["bytes"] and H(q)==d["sha256"] and H(sys.argv[3])==d["consuming_generator_sha256"] and H(sys.argv[4])==d["builder_sha256"]' \
    "$c2w_city/asset_packs/full13_same_run_procedural_assets.json" "$c2w_run_id" \
    "$c2w_root/scripts/generate_urban_v1_full_13.py" \
    "$c2w_root/scripts/build_urban_v1_full_13_procedural_pack.py" 2>/dev/null
then
    printf 'FULL13_STAGE_CACHE_HIT run_id=%s stage=procedural_pack\n' "$c2w_run_id" >> "$c2w_log"
else
    run_stage procedural_pack "$c2w_blender" -b --factory-startup \
        --python "$c2w_root/scripts/build_urban_v1_full_13_procedural_pack.py"
fi
if python3 -c 'import hashlib,json,pathlib,sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); q=pathlib.Path(d["production_blend"]); s=json.loads(pathlib.Path(sys.argv[3]).read_text()); g=pathlib.Path(sys.argv[4]); m=json.loads(pathlib.Path(sys.argv[5]).read_text()); n=json.loads(pathlib.Path(sys.argv[6]).read_text()); assert d["status"]=="PASS" and s["status"]=="PASS" and d["run_id"]==sys.argv[2]==s["run_id"] and q.is_file() and q.stat().st_size==d["production_blend_bytes"] and hashlib.sha256(q.read_bytes()).hexdigest()==d["production_blend_sha256"] and hashlib.sha256(g.read_bytes()).hexdigest()==d["active_generator_sha256"] and d["procedural_pack_sha256"]==m["sha256"] and d["semantic_pack_sha256"]==n["sha256"]' \
    "$c2w_city/generation_audit.json" "$c2w_run_id" "$c2w_city/generation.status.json" "$c2w_root/scripts/generate_urban_v1_full_13.py" "$c2w_city/asset_packs/full13_same_run_procedural_assets.json" "$c2w_city/asset_packs/full13_semantic_public_interiors.json" 2>/dev/null
then
    printf 'FULL13_STAGE_CACHE_HIT run_id=%s stage=city_generation\n' "$c2w_run_id" >> "$c2w_log"
else
    run_stage city_generation "$c2w_blender" -b --factory-startup \
        --python "$c2w_root/scripts/generate_urban_v1_full_13.py"
fi
if python3 -c 'import hashlib,json,pathlib,sys; p=pathlib.Path(sys.argv[1]); d=json.loads(p.read_text()); g=json.loads(pathlib.Path(sys.argv[3]).read_text()); H=lambda q:hashlib.sha256(pathlib.Path(q).read_bytes()).hexdigest(); assert d["status"]=="PASS" and d["run_id"]==sys.argv[2] and d["production_blend_sha256"]==g["production_blend_sha256"] and d["pack_count"]==16 and d.get("content_hash_cache",{}).get("all_layers_have_dependency_hash") is True and all(len(v.get("dependency_hash",""))==64 and pathlib.Path(v["target"]).is_file() and H(v["target"])==v["dependency_fingerprints"]["render_pack"]["sha256"] and all(H(f["path"])==f["sha256"] for f in v["dependency_fingerprints"]["render_contract_files"]) for v in d["packs"].values())' \
    "$c2w_city/render_dependency_packs/render_pack_lineage.json" "$c2w_run_id" "$c2w_city/generation_audit.json" 2>/dev/null
then
    printf 'FULL13_STAGE_CACHE_HIT run_id=%s stage=render_dependency_packs\n' "$c2w_run_id" >> "$c2w_log"
else
    run_stage render_dependency_packs "$c2w_blender" --disable-depsgraph-on-file-load \
        -b "$c2w_city/urban_v1_full_13.blend" \
        --python "$c2w_root/scripts/build_urban_v1_full_13_render_packs.py"
fi

# Expand and inspect every exact child mesh before any final GPU raster.  The
# public-realm layer goes first because it contains the complete entrance
# network and is the most likely place for a late path/furniture regression.
c2w_exact_preflight_log="$c2w_city/exact_layer_preflight.log"
touch "$c2w_exact_preflight_log"
status RUNNING exact_layer_preflight
printf 'FULL13_STAGE_BEGIN utc=%s run_id=%s stage=exact_layer_preflight\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" >> "$c2w_log"
for c2w_layer in full13_public_realm river5_nature river3_residential artificial_lake all45_unique_buildings education_buildings commercial_services industrial public_safety residential_delivery all44_leisure park_leisure_support health full13_unique_urban_fabric full13_semantic_interiors base
do
    if C2W_FULL13_RUN_ID="$c2w_run_id" \
        python3 "$c2w_root/scripts/cache_urban_v1_full_13_direct_preflight.py" \
            validate "$c2w_layer" --standard >> "$c2w_exact_preflight_log" 2>&1
    then
        printf 'FULL13_EXACT_PREFLIGHT_CACHE_HIT utc=%s layer=%s exact_input_binding=PASS\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_exact_preflight_log"
        continue
    fi
    printf 'FULL13_EXACT_PREFLIGHT_BEGIN utc=%s layer=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_exact_preflight_log"
    if ! C2W_FULL13_RUN_ID="$c2w_run_id" C2W_FULL12_PREFLIGHT_ONLY=1 \
        "$c2w_blender" --disable-depsgraph-on-file-load \
            -b "$c2w_city/render_dependency_packs/$c2w_layer.blend" \
            --python "$c2w_root/scripts/render_urban_v1_full_13_zdepth_layer.py" \
            -- "$c2w_layer" all >> "$c2w_exact_preflight_log" 2>&1
    then
        printf 'FULL13_EXACT_PREFLIGHT_FAIL layer=%s process_exit_nonzero\n' "$c2w_layer" >> "$c2w_log"
        status FAIL exact_layer_preflight
        exit 94
    fi
    if ! python3 -c 'import json,pathlib,sys; a=json.loads(pathlib.Path(sys.argv[1]).read_text()); b=json.loads(pathlib.Path(sys.argv[2]).read_text()); assert a["scene_revision"]=="urban_v1_full_13" and a["status"]=="PASS" and a["production_blend_unchanged"] is True and b["run_id"]==sys.argv[3] and b["status"]=="PASS" and b["camera_count_passed"]==80 and b["camera_count_failed"]==0 and b["evaluated_child_mesh_bvh_audit"]["pass"] is True' \
        "$c2w_city/renders/zdepth_layers/preflight_$c2w_layer.json" \
        "$c2w_city/renders/zdepth_layers/camera_mesh_preflight_$c2w_layer.json" \
        "$c2w_run_id" >> "$c2w_exact_preflight_log" 2>&1
    then
        printf 'FULL13_EXACT_PREFLIGHT_FAIL layer=%s artifact_gate\n' "$c2w_layer" >> "$c2w_log"
        status FAIL exact_layer_preflight
        exit 94
    fi
    if ! C2W_FULL13_RUN_ID="$c2w_run_id" \
        python3 "$c2w_root/scripts/cache_urban_v1_full_13_direct_preflight.py" \
            write "$c2w_layer" --standard >> "$c2w_exact_preflight_log" 2>&1
    then
        printf 'FULL13_EXACT_PREFLIGHT_FAIL layer=%s receipt_gate\n' "$c2w_layer" >> "$c2w_log"
        status FAIL exact_layer_preflight
        exit 94
    fi
    printf 'FULL13_EXACT_PREFLIGHT_PASS utc=%s layer=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" >> "$c2w_exact_preflight_log"
done
printf 'FULL13_STAGE_DONE utc=%s run_id=%s stage=exact_layer_preflight status=PASS\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" >> "$c2w_log"

# Validate every one of the 80 final camera contracts before spending GPU
# hours.  This is deliberately not cached: it is fast and detects camera
# changes independently of existing frame files.
run_stage camera_preflight "$c2w_blender" -b --factory-startup \
    --python "$c2w_root/scripts/preflight_urban_v1_full_13_cameras.py"
run_stage road_furniture_mesh_audit "$c2w_blender" --disable-depsgraph-on-file-load \
    -b "$c2w_city/render_dependency_packs/base.blend" \
    --python "$c2w_root/scripts/audit_urban_v1_full_13_road_furniture.py"
if python3 -c 'import hashlib,json,pathlib,sys; d=json.loads(pathlib.Path(sys.argv[1]).read_text()); g=json.loads(pathlib.Path(sys.argv[3]).read_text()); root=pathlib.Path(sys.argv[4]); H=lambda q:hashlib.sha256(pathlib.Path(q).read_bytes()).hexdigest(); assert d["status"]=="PASS" and d["run_id"]==sys.argv[2] and d["production_blend_sha256"]==g["production_blend_sha256"] and d["pack_count"]==6 and all(len(v.get("dependency_hash",""))==64 and pathlib.Path(v["target"]).is_file() and H(v["target"])==v["dependency_inputs"]["pack_sha256"] and all(H(root/k)==h for k,h in v["dependency_inputs"]["render_contract_sha256"].items()) for v in d["packs"].values())' \
    "$c2w_city/render_dependency_packs/direct_validation_packs.json" "$c2w_run_id" "$c2w_city/generation_audit.json" "$c2w_root/scripts" 2>/dev/null
then
    printf 'FULL13_STAGE_CACHE_HIT run_id=%s stage=direct_validation_packs\n' "$c2w_run_id" >> "$c2w_log"
else
    run_stage direct_validation_packs "$c2w_blender" --disable-depsgraph-on-file-load \
        -b "$c2w_city/urban_v1_full_13.blend" \
        --python "$c2w_root/scripts/build_urban_v1_full_13_direct_validation_packs.py"
fi
# Blender can return zero even when a --python script raises.  Treat the
# artifact contract, not Blender's process code, as the authoritative gate.
if ! python3 -c 'import json,pathlib,sys; d=json.loads(pathlib.Path(sys.argv[1]).read_text()); g=json.loads(pathlib.Path(sys.argv[3]).read_text()); assert d["status"]=="PASS" and d["run_id"]==sys.argv[2] and d["production_blend_sha256"]==g["production_blend_sha256"] and d["pack_count"]==6 and set(d["packs"])=={"direct_civic","direct_commercial","direct_residential","direct_industrial_safety","direct_park_lake","direct_diagonal_street"} and all(len(v.get("dependency_hash",""))==64 and pathlib.Path(v["target"]).is_file() for v in d["packs"].values())' \
    "$c2w_city/render_dependency_packs/direct_validation_packs.json" "$c2w_run_id" "$c2w_city/generation_audit.json"
then
    printf 'FULL13_ARTIFACT_GATE_FAIL run_id=%s stage=direct_validation_packs\n' "$c2w_run_id" >> "$c2w_log"
    status FAIL direct_validation_packs
    exit 95
fi

# Representative direct packs deliberately combine several semantic layers.
# Certify their cross-layer evaluated meshes and all cameras before the long
# standard-layer raster phase, so direct-reference failures cannot arrive at
# the end of an otherwise complete render.
c2w_direct_preflight_log="$c2w_city/direct_exact_preflight.log"
# Preserve the append-only evidence log across a recovery.  Per-pack receipts
# below are accepted only when the exact pack/dependency/audit hashes and every
# strict 80-camera/no-simplification invariant still match.
touch "$c2w_direct_preflight_log"
status RUNNING direct_exact_preflight
printf 'FULL13_STAGE_BEGIN utc=%s run_id=%s stage=direct_exact_preflight\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" >> "$c2w_log"
for c2w_direct_contract in \
    direct_civic:school_library_shared_street \
    direct_commercial:commercial_far \
    direct_residential:residential_far \
    direct_industrial_safety:industrial_far \
    direct_park_lake:artificial_lake_high \
    direct_diagonal_street:diagonal_road_near
do
    c2w_direct_key="${c2w_direct_contract%%:*}"
    c2w_direct_shot="${c2w_direct_contract#*:}"
    if C2W_FULL13_RUN_ID="$c2w_run_id" \
        python3 "$c2w_root/scripts/cache_urban_v1_full_13_direct_preflight.py" \
            validate "$c2w_direct_key" >> "$c2w_direct_preflight_log" 2>&1
    then
        printf 'FULL13_DIRECT_PREFLIGHT_CACHE_HIT utc=%s key=%s exact_input_binding=PASS\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" >> "$c2w_direct_preflight_log"
        continue
    fi
    printf 'FULL13_DIRECT_PREFLIGHT_BEGIN utc=%s key=%s shot=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" "$c2w_direct_shot" >> "$c2w_direct_preflight_log"
    if ! C2W_FULL13_RUN_ID="$c2w_run_id" C2W_FULL12_PREFLIGHT_ONLY=1 \
        "$c2w_blender" --disable-depsgraph-on-file-load \
            -b "$c2w_city/render_dependency_packs/$c2w_direct_key.blend" \
            --python "$c2w_root/scripts/render_urban_v1_full_13_direct_validation.py" \
            -- "$c2w_direct_key" "$c2w_direct_shot" >> "$c2w_direct_preflight_log" 2>&1
    then
        printf 'FULL13_DIRECT_PREFLIGHT_FAIL key=%s process_exit_nonzero\n' "$c2w_direct_key" >> "$c2w_log"
        status FAIL direct_exact_preflight
        exit 93
    fi
    if ! python3 -c 'import json,pathlib,sys; a=json.loads(pathlib.Path(sys.argv[1]).read_text()); b=json.loads(pathlib.Path(sys.argv[2]).read_text()); assert a["scene_revision"]=="urban_v1_full_13" and a["status"]=="PASS" and a["production_blend_unchanged"] is True and b["run_id"]==sys.argv[3] and b["status"]=="PASS" and b["camera_count_passed"]==80 and b["camera_count_failed"]==0 and b["evaluated_child_mesh_bvh_audit"]["pass"] is True' \
        "$c2w_city/renders/direct_validation_layers/preflight_$c2w_direct_key.json" \
        "$c2w_city/renders/direct_validation_layers/camera_mesh_preflight_$c2w_direct_key.json" \
        "$c2w_run_id" >> "$c2w_direct_preflight_log" 2>&1
    then
        printf 'FULL13_DIRECT_PREFLIGHT_FAIL key=%s artifact_gate\n' "$c2w_direct_key" >> "$c2w_log"
        status FAIL direct_exact_preflight
        exit 93
    fi
    if ! C2W_FULL13_RUN_ID="$c2w_run_id" \
        python3 "$c2w_root/scripts/cache_urban_v1_full_13_direct_preflight.py" \
            write "$c2w_direct_key" >> "$c2w_direct_preflight_log" 2>&1
    then
        printf 'FULL13_DIRECT_PREFLIGHT_FAIL key=%s receipt_gate\n' "$c2w_direct_key" >> "$c2w_log"
        status FAIL direct_exact_preflight
        exit 93
    fi
    printf 'FULL13_DIRECT_PREFLIGHT_PASS utc=%s key=%s\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" >> "$c2w_direct_preflight_log"
done
printf 'FULL13_STAGE_DONE utc=%s run_id=%s stage=direct_exact_preflight status=PASS\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" >> "$c2w_log"

# Dependency-only Blender packs are exact but their container serialization is
# not byte deterministic.  If a restart rebuilt those packs, rebind already
# certified frames only after current-pack BVH/camera preflights plus every
# original frame byte/SHA/native-EXR/PBR contract have all passed.
if [ "${C2W_FULL13_FORCE_FRESH_RENDER:-0}" = "1" ]; then
    # This run changes actual production geometry and camera composition.
    # Historical non-raster receipts CANNOT justify recycling its old images.
    # Certify fresh provenance only after all 1,280 new same-run PBR renders.
    printf 'FULL13_FRESH_RENDER_GATE run_id=%s geometry_and_camera_changed=1 prior_raster_rebind_forbidden=1\n' \
        "$c2w_run_id" >> "$c2w_log"
elif [ "${C2W_FULL13_SELECTIVE_SEMANTIC_UPGRADE:-0}" = "1" ]; then
    c2w_upgrade_root="$c2w_city/render_runtime/semantic_upgrade_r3"
    [ -f "$c2w_upgrade_root/prior/procedural_collection_fingerprints.json" ] || {
        printf 'Missing prior procedural collection fingerprint for selective semantic upgrade\n' >&2
        exit 96
    }
    # A recovery after all 16 current layer manifests are complete must not
    # reapply the historical rebind and deliberately invalidate the same 272
    # frames a second time.  Reuse is allowed only after every frame planner
    # re-hashes its current native EXRs and the selective provenance audit is
    # still bound to this run/current production blend.
    c2w_complete_layer_cache=1
    for c2w_layer in $c2w_layers; do
        if ! C2W_FULL13_RUN_ID="$c2w_run_id" \
            python3 "$c2w_root/scripts/plan_urban_v1_full_13_layer_frames.py" \
                "$c2w_layer" --assert-complete >> "$c2w_log" 2>&1
        then
            c2w_complete_layer_cache=0
            break
        fi
    done
    if [ "$c2w_complete_layer_cache" -eq 1 ] && \
        python3 -c 'import json,pathlib,sys; a=json.loads(pathlib.Path(sys.argv[1]).read_text()); g=json.loads(pathlib.Path(sys.argv[2]).read_text()); assert a["schema"]=="agent.full13.selective_semantic_upgrade_rebind.v1" and a["status"]=="PASS" and a["run_id"]==sys.argv[3] and a["current_production_blend_sha256"]==g["production_blend_sha256"] and a["changed_geometry_layers"]==["full13_public_realm","full13_semantic_interiors"] and a["unchanged_frame_sha256_verified"]==1120 and a["full_layer_frames_deliberately_left_invalid"]==160 and a["camera_frames_deliberately_left_invalid"]==112' \
            "$c2w_city/layer_provenance_rebind_audit.json" \
            "$c2w_city/generation_audit.json" "$c2w_run_id"
    then
        printf 'FULL13_STAGE_CACHE_HIT run_id=%s stage=layer_provenance_rebind all_current_layers_sha_verified=PASS\n' \
            "$c2w_run_id" >> "$c2w_log"
    else
        run_stage current_procedural_collection_fingerprint \
            "$c2w_blender" --disable-depsgraph-on-file-load \
            -b "$c2w_city/asset_packs/full13_same_run_procedural_assets.blend" \
            --python "$c2w_root/scripts/fingerprint_urban_v1_full_13_procedural_collections.py" \
            -- "$c2w_upgrade_root/current_procedural_collection_fingerprints.json"
        run_stage layer_provenance_rebind "$c2w_openexr_python" \
            "$c2w_root/scripts/rebind_urban_v1_full_13_semantic_upgrade.py"
    fi
else
    run_stage layer_provenance_rebind "$c2w_openexr_python" \
        "$c2w_root/scripts/rebind_urban_v1_full_13_layer_provenance.py"
fi

# Choose the available GPUs at the moment rendering begins.  Eevee's
# headless OpenGL context always landed on physical GPU 0 on this eight-4090
# server even with CUDA_VISIBLE_DEVICES.  Vulkan plus an exact DRI_PRIME PCI
# tag was production-probed against this scene and gives each Blender process
# an independently verified physical device.  A controlled production run
# showed that eight simultaneous Vulkan contexts trigger severe driver-wide
# contention (multi-hour frames despite 342 GiB available RAM), whereas six
# contexts produced the same frames in minutes.  Six is therefore the measured
# throughput optimum on this host and still leaves two GPUs as fault reserve.
c2w_parallel="${C2W_FULL13_GPU_CONCURRENCY:-6}"
case "$c2w_parallel" in
    1|2|3|4|5|6|7|8) ;;
    *) printf 'Invalid C2W_FULL13_GPU_CONCURRENCY=%s\n' "$c2w_parallel" >&2; exit 98 ;;
esac
c2w_gpu_rows="$(nvidia-smi --query-gpu=index,utilization.gpu,memory.used --format=csv,noheader,nounits | sort -t, -k2,2n -k3,3n | head -n "$c2w_parallel")"
c2w_gpu_indices="$(printf '%s\n' "$c2w_gpu_rows" | sed 's/,.*//' | tr -d ' ')"
c2w_gpu_slots=""
for c2w_gpu in $c2w_gpu_indices; do
    c2w_pci_bus="$(nvidia-smi --query-gpu=index,pci.bus_id --format=csv,noheader,nounits | awk -F, -v wanted="$c2w_gpu" '{gsub(/ /,"",$1); gsub(/ /,"",$2); if ($1==wanted) print $2}')"
    c2w_prime="$(printf '%s' "$c2w_pci_bus" | sed 's/^00000000:/0000_/; s/:/_/g; s/\./_/g' | tr '[:upper:]' '[:lower:]')"
    [ -n "$c2w_prime" ] || { printf 'Missing PCI address for GPU %s\n' "$c2w_gpu" >&2; exit 98; }
    c2w_gpu_slots="$c2w_gpu_slots $c2w_gpu:pci-$c2w_prime"
done
set -- $c2w_gpu_slots
c2w_slot_a="$1"
c2w_slot_b="${2:-$1}"
c2w_gpu_a="${c2w_slot_a%%:*}"
c2w_gpu_b="${c2w_slot_b%%:*}"
printf 'FULL13_GPU_SELECTION utc=%s rows=%s gpu_a=%s gpu_b=%s gpu_slots=%s backend=vulkan concurrency=%s\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(printf '%s' "$c2w_gpu_rows" | tr '\n' ';')" \
    "$c2w_gpu_a" "$c2w_gpu_b" "$(printf '%s' "$c2w_gpu_slots" | sed 's/^ //')" \
    "$c2w_parallel" >> "$c2w_log"

render_layer_inline_fallback() {
    c2w_layer="$1"
    c2w_gpu="$2"
    c2w_prime="$3"
    c2w_pack="$c2w_city/render_dependency_packs/$c2w_layer.blend"
    c2w_layer_log="$c2w_city/render_${c2w_layer}.log"
    c2w_layer_status="$c2w_city/render_${c2w_layer}.status.json"
    c2w_frame_planner="$c2w_root/scripts/plan_urban_v1_full_13_layer_frames.py"
    # Keep each Vulkan process' shader/cache state private.  Sharing one
    # XDG cache across several simultaneously active drivers can serialize
    # cache locks and leaves no useful cross-layer reuse because every pack
    # has different exact geometry and materials.
    mkdir -p "$c2w_city/render_runtime/$c2w_layer/tmp" \
        "$c2w_city/render_runtime/$c2w_layer/cache"
    : > "$c2w_layer_log"
    c2w_pending_shots="$(C2W_FULL13_RUN_ID="$c2w_run_id" \
        python3 "$c2w_frame_planner" "$c2w_layer")"
    c2w_pending_count="$(printf '%s\n' "$c2w_pending_shots" | awk 'NF {count++} END {print count+0}')"
    printf 'FULL13_LAYER_FRAME_PLAN utc=%s layer=%s pending=%s process_boundary=one_view\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_pending_count" >> "$c2w_layer_log"

    # A fresh Blender/Vulkan process per view is intentional.  These exact
    # packs reference hundreds of millions of authored polygons; a long-lived
    # process retains device allocations even with persistent data disabled
    # and eventually changes later frames from minutes to hours.  The rolling
    # manifest and frame SHA-256 contract make each process boundary resumable.
    for c2w_shot in $c2w_pending_shots; do
        c2w_attempt=0
        c2w_shot_pass=0
        while [ "$c2w_attempt" -lt 3 ]; do
            c2w_attempt=$((c2w_attempt + 1))
            printf 'FULL13_FRAME_ATTEMPT_BEGIN utc=%s layer=%s shot=%s gpu=%s pci=%s backend=vulkan attempt=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_shot" \
                "$c2w_gpu" "$c2w_prime" "$c2w_attempt" >> "$c2w_layer_log"
            printf '{"run_id":"%s","stage":"frame_render","layer":"%s","shot":"%s","gpu":"%s","pci":"%s","gpu_backend":"vulkan","attempt":%s,"status":"RUNNING","updated_utc":"%s"}\n' \
                "$c2w_run_id" "$c2w_layer" "$c2w_shot" "$c2w_gpu" "$c2w_prime" \
                "$c2w_attempt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_layer_status"
        # Eevee persistent data retains the expanded high-poly scene on the
        # Vulkan device between cameras.  With these exact packs that fills a
        # 24 GiB card and changes later frames from minutes to hours.  Turning
        # it off only controls cache lifetime; geometry, materials, samples,
        # resolution, and output precision remain unchanged.
            c2w_process_exit=0
            DRI_PRIME="$c2w_prime" \
                CUDA_VISIBLE_DEVICES="$c2w_gpu" \
                C2W_FULL13_RUN_ID="$c2w_run_id" \
                C2W_FULL13_RENDER_ENGINE=EEVEE \
                C2W_FULL13_EEVEE_SAMPLES=64 \
                C2W_FULL12_RENDER_ENGINE=EEVEE \
                C2W_FULL12_EEVEE_SAMPLES=64 \
                C2W_FULL12_PERSISTENT_DATA=0 \
                TMPDIR="$c2w_city/render_runtime/$c2w_layer/tmp" \
                XDG_CACHE_HOME="$c2w_city/render_runtime/$c2w_layer/cache" \
                "$c2w_blender" --gpu-backend vulkan --disable-depsgraph-on-file-load \
                    -b "$c2w_pack" \
                    --python "$c2w_root/scripts/render_urban_v1_full_13_zdepth_layer.py" \
                    -- "$c2w_layer" "$c2w_shot" >> "$c2w_layer_log" 2>&1 \
                || c2w_process_exit=$?
            if C2W_FULL13_RUN_ID="$c2w_run_id" \
                python3 "$c2w_frame_planner" "$c2w_layer" \
                    --assert-shot "$c2w_shot" >> "$c2w_layer_log" 2>&1
            then
                c2w_shot_pass=1
                printf 'FULL13_FRAME_ATTEMPT_DONE utc=%s layer=%s shot=%s attempt=%s process_exit=%s status=PASS\n' \
                    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_shot" \
                    "$c2w_attempt" "$c2w_process_exit" >> "$c2w_layer_log"
                break
            fi
            printf 'FULL13_FRAME_RETRY utc=%s layer=%s shot=%s gpu=%s attempt=%s process_exit=%s\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_layer" "$c2w_shot" \
                "$c2w_gpu" "$c2w_attempt" "$c2w_process_exit" >> "$c2w_layer_log"
        done
        if [ "$c2w_shot_pass" -ne 1 ]; then
            printf '{"run_id":"%s","stage":"frame_render","layer":"%s","shot":"%s","gpu":"%s","pci":"%s","gpu_backend":"vulkan","attempt":%s,"status":"FAIL","updated_utc":"%s"}\n' \
                "$c2w_run_id" "$c2w_layer" "$c2w_shot" "$c2w_gpu" "$c2w_prime" \
                "$c2w_attempt" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_layer_status"
            return 1
        fi
    done
    if ! C2W_FULL13_RUN_ID="$c2w_run_id" \
        python3 "$c2w_frame_planner" "$c2w_layer" --assert-complete \
            >> "$c2w_layer_log" 2>&1
    then
        printf 'FULL13_LAYER_FINAL_CERTIFICATION_FAIL layer=%s\n' "$c2w_layer" >> "$c2w_layer_log"
        return 1
    fi
    printf '{"run_id":"%s","stage":"layer_render","layer":"%s","gpu":"%s","pci":"%s","gpu_backend":"vulkan","attempt":1,"status":"PASS","updated_utc":"%s"}\n' \
        "$c2w_run_id" "$c2w_layer" "$c2w_gpu" "$c2w_prime" \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" > "$c2w_layer_status"
    return 0
}

# Keep the restart-safe view worker independently invocable so an otherwise
# idle physical GPU can pull forward a later exact layer.  Its output and
# manifest gates are identical to the inline implementation above.
render_layer() {
    C2W_FULL13_RUN_ID="$c2w_run_id" \
        /bin/sh "$c2w_root/scripts/run_urban_v1_full_13_layer_worker.sh" \
            "$1" "$2" "$3"
}

status RUNNING all_eevee_layers
set -- $c2w_layers
while [ "$#" -gt 0 ]; do
    c2w_batch_pids=""
    for c2w_slot in $c2w_gpu_slots; do
        [ "$#" -gt 0 ] || break
        c2w_layer="$1"
        shift
        c2w_gpu="${c2w_slot%%:*}"
        c2w_prime="${c2w_slot#*:}"
        render_layer "$c2w_layer" "$c2w_gpu" "$c2w_prime" &
        c2w_batch_pids="$c2w_batch_pids $!"
    done
    c2w_batch_fail=0
    for c2w_pid in $c2w_batch_pids; do
        wait "$c2w_pid" || c2w_batch_fail=1
    done
    if [ "$c2w_batch_fail" -ne 0 ]; then
        status FAIL all_eevee_layers
        exit 96
    fi
done

if [ "${C2W_FULL13_FORCE_FRESH_RENDER:-0}" = "1" ]; then
    run_stage certify_fresh_full_scene_provenance "$c2w_openexr_python" \
        "$c2w_root/scripts/certify_urban_v1_full_13_fresh_render.py"
fi

# Six bounded multi-layer references are rendered directly in one Eevee scene
# per semantic class.  They preserve local relationships while avoiding the
# measured full-city OOM, and are compared against the identical Z layers.
render_direct_reference() {
    c2w_direct_key="$1"
    c2w_direct_shot="$2"
    c2w_direct_gpu="$3"
    c2w_direct_prime="$4"
    c2w_direct_pack="$c2w_city/render_dependency_packs/$c2w_direct_key.blend"
    c2w_direct_log="$c2w_city/render_${c2w_direct_key}.log"
    mkdir -p "$c2w_city/render_runtime/$c2w_direct_key/tmp" \
        "$c2w_city/render_runtime/$c2w_direct_key/cache"
    # Direct frames are expensive multi-layer exact rasters.  On recovery,
    # retain one only when its current dependency hash, run id, engine/PBR
    # contract, native dimensions, authoritative pixel validation, file size,
    # and file SHA all still agree with the current direct-pack lineage.
    if python3 -c 'import hashlib,json,pathlib,sys; m=pathlib.Path(sys.argv[1]); q=json.loads(m.read_text()); l=json.loads(pathlib.Path(sys.argv[2]).read_text()); r=next(x for x in q["views"] if x["name"]==sys.argv[4]); p=pathlib.Path(r["outputs"]["bundle"]); h=hashlib.sha256(p.read_bytes()).hexdigest(); a=r["authoritative_exr_validation"]; assert q["status"]=="PASS" and q["complete"] is True and q["run_id"]==sys.argv[5] and q["layer_key"]==sys.argv[3] and q["geometry_simplification"] is False and q["disabled_visible_geometry_count"]==0 and q["all_frames_pbr_eevee"] is True and r["status"]=="rendered" and r["render_dependency_hash"]==q["render_dependency_hash"]==l["packs"][sys.argv[3]]["dependency_hash"] and r["render_settings"]["engine"] in {"BLENDER_EEVEE","BLENDER_EEVEE_NEXT"} and r["render_settings"]["resolution"]==[1920,1080] and r["render_settings"]["samples"]==64 and r["render_settings"]["mesh_simplification"] is False and r["render_settings"]["final_pbr_required"] is True and r["render_settings"]["workbench_final_allowed"] is False and a["status"]=="PASS" and a["resolution"]==[1920,1080] and a["direct_non_base_combined_parts_contract"] is True and a["pixel_content_nondegenerate"] is True and p.is_file() and p.stat().st_size==r["bytes"]["bundle"] and h==r["sha256"]["bundle"]' \
        "$c2w_city/renders/direct_validation_layers/layer_manifest_$c2w_direct_key.json" \
        "$c2w_city/render_dependency_packs/direct_validation_packs.json" \
        "$c2w_direct_key" "$c2w_direct_shot" "$c2w_run_id" 2>/dev/null
    then
        printf 'FULL13_DIRECT_FRAME_CACHE_HIT utc=%s key=%s shot=%s current_dependency_and_sha=PASS\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" "$c2w_direct_shot" \
            >> "$c2w_direct_log"
        return 0
    fi
    : > "$c2w_direct_log"
    c2w_direct_attempt=0
    while [ "$c2w_direct_attempt" -lt 3 ]; do
        c2w_direct_attempt=$((c2w_direct_attempt + 1))
        printf 'FULL13_DIRECT_FRAME_ATTEMPT_BEGIN utc=%s key=%s shot=%s gpu=%s pci=%s attempt=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" \
            "$c2w_direct_shot" "$c2w_direct_gpu" "$c2w_direct_prime" \
            "$c2w_direct_attempt" >> "$c2w_direct_log"
        c2w_direct_process_exit=0
        DRI_PRIME="$c2w_direct_prime" \
            CUDA_VISIBLE_DEVICES="$c2w_direct_gpu" \
            C2W_FULL13_RUN_ID="$c2w_run_id" \
            C2W_FULL13_RENDER_ENGINE=EEVEE \
            C2W_FULL13_EEVEE_SAMPLES=64 \
            C2W_FULL12_RENDER_ENGINE=EEVEE \
            C2W_FULL12_EEVEE_SAMPLES=64 \
            C2W_FULL12_PERSISTENT_DATA=0 \
            TMPDIR="$c2w_city/render_runtime/$c2w_direct_key/tmp" \
            XDG_CACHE_HOME="$c2w_city/render_runtime/$c2w_direct_key/cache" \
            "$c2w_blender" --gpu-backend vulkan --disable-depsgraph-on-file-load \
                -b "$c2w_direct_pack" \
                --python "$c2w_root/scripts/render_urban_v1_full_13_direct_validation.py" \
                    -- "$c2w_direct_key" "$c2w_direct_shot" >> "$c2w_direct_log" 2>&1 \
            || c2w_direct_process_exit=$?
        if [ "$c2w_direct_process_exit" -eq 0 ] && \
            python3 -c 'import json,pathlib,sys; d=json.loads(pathlib.Path(sys.argv[1]).read_text()); r=next(x for x in d["views"] if x["name"]==sys.argv[2]); v=r["authoritative_exr_validation"]; assert d["run_id"]==sys.argv[3] and r["render_settings"]["engine"] in {"BLENDER_EEVEE","BLENDER_EEVEE_NEXT"} and r["render_dependency_hash"]==d["render_dependency_hash"] and v["layer"]==sys.argv[4] and v["direct_non_base_combined_parts_contract"] is True and pathlib.Path(r["outputs"]["bundle"]).is_file()' \
                "$c2w_city/renders/direct_validation_layers/layer_manifest_${c2w_direct_key}.json" \
                "$c2w_direct_shot" "$c2w_run_id" "$c2w_direct_key" \
                >> "$c2w_direct_log" 2>&1
        then
            printf 'FULL13_DIRECT_FRAME_ATTEMPT_DONE utc=%s key=%s shot=%s attempt=%s status=PASS\n' \
                "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" \
                "$c2w_direct_shot" "$c2w_direct_attempt" >> "$c2w_direct_log"
            return 0
        fi
        printf 'FULL13_DIRECT_FRAME_RETRY utc=%s key=%s shot=%s attempt=%s process_exit=%s\n' \
            "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_direct_key" \
            "$c2w_direct_shot" "$c2w_direct_attempt" \
            "$c2w_direct_process_exit" >> "$c2w_direct_log"
    done
    return 1
}

status RUNNING direct_eevee_references
c2w_direct_contracts="\
direct_civic:school_library_shared_street \
direct_commercial:commercial_far \
direct_residential:residential_far \
direct_industrial_safety:industrial_far \
direct_park_lake:artificial_lake_high \
direct_diagonal_street:diagonal_road_near"
set -- $c2w_direct_contracts
while [ "$#" -gt 0 ]; do
    c2w_direct_pids=""
    for c2w_slot in $c2w_gpu_slots; do
        [ "$#" -gt 0 ] || break
        c2w_direct_contract="$1"
        shift
        c2w_direct_key="${c2w_direct_contract%%:*}"
        c2w_direct_shot="${c2w_direct_contract#*:}"
        c2w_direct_gpu="${c2w_slot%%:*}"
        c2w_direct_prime="${c2w_slot#*:}"
        render_direct_reference "$c2w_direct_key" "$c2w_direct_shot" \
            "$c2w_direct_gpu" "$c2w_direct_prime" &
        c2w_direct_pids="$c2w_direct_pids $!"
    done
    c2w_direct_fail=0
    for c2w_pid in $c2w_direct_pids; do
        wait "$c2w_pid" || c2w_direct_fail=1
    done
    [ "$c2w_direct_fail" -eq 0 ] || { status FAIL direct_eevee_references; exit 97; }
done
run_stage direct_manifest_certification python3 \
    "$c2w_root/scripts/certify_urban_v1_full_13_direct_manifests.py"
run_stage direct_zdepth_equivalence "$c2w_openexr_python" \
    "$c2w_root/scripts/compare_urban_v1_full_13_direct_validation.py"

run_stage zdepth_composition "$c2w_blender" -b --factory-startup \
    --python "$c2w_root/scripts/compose_urban_v1_full_13_zdepth.py"
run_stage resource_efficiency_audit "$c2w_openexr_python" \
    "$c2w_root/scripts/summarize_urban_v1_full_13_resources.py"
run_stage strict_final_audit "$c2w_openexr_python" \
    "$c2w_root/scripts/audit_urban_v1_full_13.py"
status PASS complete
printf 'FULL13_PIPELINE_FINISH utc=%s run_id=%s status=PASS\n' \
    "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$c2w_run_id" >> "$c2w_log"

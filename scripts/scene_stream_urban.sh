#!/bin/bash

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
# Urban Scene Stream Pipeline
# Supports two scene types:
#   crossroads_4zone — 4-quadrant crossroads with residential/park/commercial/empty zones
#                      Realizer produces a Blender Python script → executed directly with Blender
#   flat             — legacy single-axis street (gin config → generate_urban.py)
#
# Usage:
#   bash scripts/scene_stream_urban.sh "A crossroads scene with residential, park, and commercial areas" [output_dir]
#   bash scripts/scene_stream_urban.sh "A busy downtown commercial street" outputs/urban_flat

set -e

if [ $# -eq 0 ]; then
    echo "Error: Please provide a user_prompt parameter."
    echo "Usage: bash scripts/scene_stream_urban.sh \"your urban scene prompt\" [output_dir]"
    exit 1
fi

if [ -z "${OPENAI_API_KEY:-}${SAYMYCODE_API_KEY:-}${WORLDBRIDGE_API_KEY:-}${LEGACYWORLD_API_KEY:-}" ]; then
    echo "Error: No LLM API key is set."
    echo "Set OPENAI_API_KEY, SAYMYCODE_API_KEY, or LEGACYWORLD_API_KEY first."
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
USER_PROMPT="$1"
OUTPUT_BASE="${2:-outputs/urban}"

# Blender binary detection
BLENDER="${BLENDER_BIN:-}"
if [ -z "$BLENDER" ]; then
    for CANDIDATE in ${BLENDER_BIN} blender; do
        if command -v "$CANDIDATE" &>/dev/null; then
            BLENDER="$CANDIDATE"; break
        fi
    done
fi
if [ -z "$BLENDER" ]; then
    echo "Warning: blender binary not found. Set BLENDER_BIN env var for Blender execution."
fi

cd "$REPO_ROOT"

echo "============================================"
echo "  WorldBridge — Urban Scene Stream Pipeline"
echo "============================================"
echo "User Prompt: $USER_PROMPT"
echo ""

# ---------- Agent 1: Urban Environment Planner ----------
echo "[Agent 1] Urban Environment Planner: Inferring scene manifest..."
python worldbridge/scene_stream_urban/planner.py "$USER_PROMPT"
if [ $? -ne 0 ]; then
    echo "Error: Urban Planner failed."
    exit 1
fi
echo "[Agent 1] Planner complete. Manifest saved to output/urban/manifest_scene_urban.json"
echo ""

# ---------- Agent 2: Urban Parameter Resolver ----------
echo "[Agent 2] Urban Parameter Resolver: Translating manifest to quantitative parameters..."
python worldbridge/scene_stream_urban/resolver.py "$USER_PROMPT" "$OUTPUT_BASE"
if [ $? -ne 0 ]; then
    echo "Error: Urban Resolver failed."
    exit 1
fi
echo "[Agent 2] Resolver complete. Parameters saved to output/urban/urban_params.json"
echo ""

# ---------- Agent 3: Urban Scene Realizer ----------
echo "[Agent 3] Urban Scene Realizer: Compiling scene artifacts..."
python worldbridge/scene_stream_urban/realizer.py "$USER_PROMPT"
if [ $? -ne 0 ]; then
    echo "Error: Urban Realizer failed."
    exit 1
fi
echo "[Agent 3] Realizer complete."
echo ""

# ---------- Determine execution path from scene_type ----------
SCENE_TYPE=$(python -c "
import json, sys
try:
    d = json.loads(open('output/urban/urban_params.json').read())
    print(d.get('scene_type','flat'))
except Exception as e:
    print('flat')
")
echo "Scene type: $SCENE_TYPE"
echo ""

if [ "$SCENE_TYPE" = "crossroads_4zone" ]; then
    # ── Crossroads path: run the generated Blender Python script ──────────────
    SCENE_PY="$REPO_ROOT/output/urban/urban_scene.py"
    if [ ! -f "$SCENE_PY" ]; then
        echo "Error: Expected Blender script not found: $SCENE_PY"
        exit 1
    fi
    if [ -z "$BLENDER" ]; then
        echo "============================================"
        echo "  Blender binary not found — SKIPPING render"
        echo "  Run manually:"
        echo "    blender --background --python $SCENE_PY"
        echo "============================================"
    else
        echo "[Blender] Running crossroads scene script ..."
        "$BLENDER" --background --python "$SCENE_PY"
        if [ $? -ne 0 ]; then
            echo "Error: Blender scene execution failed."
            exit 1
        fi
        echo "[Blender] Crossroads scene generation complete."
        OUT_DIR=$(python -c "
import json
d = json.loads(open('output/urban/urban_params.json').read())
print(d.get('output_dir','output/urban_pipeline'))
")
        echo "Output directory: $OUT_DIR"
    fi
else
    # ── Flat/legacy path: gin config → generate_urban.py ─────────────────────
    GENERATED_GIN="$REPO_ROOT/infinigen/infinigen_examples/configs_urban/generated_urban_scene.gin"
    if [ ! -s "$GENERATED_GIN" ]; then
        echo "Error: Generated gin file was not created or is empty: $GENERATED_GIN"
        exit 1
    fi

    echo "[Infinigen] Running Urban Coarse Generation..."
    cd infinigen || { echo "Error: infinigen/ folder not found"; exit 1; }

    python -m infinigen_examples.generate_urban \
        --seed 1 \
        --task coarse \
        --output_folder "${OUTPUT_BASE}/coarse" \
        -g base_urban generated_urban_scene
    if [ $? -ne 0 ]; then
        echo "Error: Infinigen Urban Coarse Generation failed."
        exit 1
    fi
    echo "Coarse generation complete."
    echo ""

    echo "[Infinigen] Running Urban Render..."
    python -m infinigen_examples.generate_urban \
        --seed 1 \
        --task render \
        --input_folder "${OUTPUT_BASE}/coarse" \
        --output_folder "${OUTPUT_BASE}/frames" \
        -g base_urban generated_urban_scene
    if [ $? -ne 0 ]; then
        echo "Error: Infinigen Urban Render failed."
        exit 1
    fi
    echo "Render complete: infinigen/${OUTPUT_BASE}/frames/"
    cd ..
fi

echo ""
echo "============================================"
echo "  Urban Scene Pipeline Complete!"
echo "============================================"

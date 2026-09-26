#!/usr/bin/env bash

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
set -euo pipefail

# Subscription-only Gemini transport.  API-key routes are deliberately made
# unavailable even when the parent shell happens to define them.
unset GEMINI_API_KEY GOOGLE_API_KEY GOOGLE_GEMINI_BASE_URL
export AGY_CLI_DISABLE_AUTO_UPDATE=1

readonly AGY_BIN="${WORLDBRIDGE_ROOT}/baselines/tools/antigravity_cli_1_2_5_frozen/agy"
readonly PRINT_TIMEOUT="${GEMINI31_PRINT_TIMEOUT:-1000s}"
readonly PROMPT="$(cat)"

exec "${AGY_BIN}" \
  --model gemini-3.1-pro-high \
  --effort high \
  --mode plan \
  --output-format text \
  --print-timeout "${PRINT_TIMEOUT}" \
  --print "${PROMPT}"

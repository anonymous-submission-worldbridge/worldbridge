#!/bin/bash

set -e

# Configure one of these before running:
#   export OPENAI_API_KEY="..."
#   export OPENAI_BASE_URL="https://api.openai.com/v1"  # optional for official OpenAI
#   export OPENAI_MODEL="gpt-4o"
#
# Or for the saymycode OpenAI-compatible gateway:
#   export SAYMYCODE_API_KEY="..."
#   export SAYMYCODE_BASE_URL="https://saymycode.xyz/v1"  # optional default
#   export SAYMYCODE_MODEL="gpt-5.5"                      # optional default

CUDA_VISIBLE_DEVICES=1 bash scripts/scene.sh nature "Create a spooky forest scene with fog, wind-blown trees, drifting leaves, and animated mist"
CUDA_VISIBLE_DEVICES=1 python worldbridge/postprocess/generate.py


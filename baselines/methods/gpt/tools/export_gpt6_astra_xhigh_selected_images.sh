#!/usr/bin/env bash
set -euo pipefail

BASELINES="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
ANNOTATIONS="$BASELINES/annotations/gpt6_astra_xhigh"

export_domain() {
  local domain="$1"
  shift
  local output="$ANNOTATIONS/$domain/images"
  local map="$ANNOTATIONS/$domain/PRIVATE_blind_map.json"
  mkdir -p "$output"

  local blind_id run_dir source index destination
  for blind_id in "$@"; do
    run_dir="$(jq -er --arg id "$blind_id" '.items[] | select(.blind_id == $id and .success == true) | .run_dir' "$map")"
    for index in 0 1 2 3 4 5 6 7; do
      source="$run_dir/renders/anchors/rgb_$(printf '%03d' "$index").png"
      destination="$output/${blind_id}_view_$(printf '%02d' "$((index + 1))").png"
      test -f "$source"
      cp --reflink=auto --preserve=mode,timestamps "$source" "$destination"
    done
  done
}

export_domain indoor \
  I-0D1FEA2830C6 \
  I-0FA0A89F15C1 \
  I-02FF505E37D9 \
  I-5D4FB3D5E896

export_domain urban \
  U-1AB067C5D745 \
  U-F9C8FE675D71 \
  U-F860C047A70A \
  U-055B11D0B894

echo "Exported 32 indoor and 32 urban anchor renders without overlays."

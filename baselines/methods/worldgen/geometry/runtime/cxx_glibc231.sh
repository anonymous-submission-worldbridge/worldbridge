#!/usr/bin/env bash
set -euo pipefail

args=()
skip_next=0
for arg in "$@"; do
  if [[ "$skip_next" == 1 ]]; then
    skip_next=0
    continue
  fi
  if [[ "$arg" == "-isystem" ]]; then
    skip_next=1
    continue
  fi
  if [[ "$arg" == -B*/compiler_compat ]]; then
    continue
  fi
  args+=("$arg")
done
exec /usr/bin/g++ "${args[@]}"

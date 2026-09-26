#!/usr/bin/env bash
set -Eeuo pipefail

# Losslessly archive completed Table 2 formal-output trees. Small metric and
# annotation results stay online; only the large per-run data trees are packed.

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
ARCHIVE_ROOT="$REPO_ROOT/baselines/archives/table2_completed_20260907"
ZSTD_BIN="${ZSTD_BIN:-$(command -v zstd)}"

mkdir -p -- "$ARCHIVE_ROOT"
cd -- "$REPO_ROOT"

items=(
  "spatialgen_indoor|baselines/data/table2/indoor/spatialgen"
  "infinigen_indoors_indoor|baselines/data/table2/indoor/infinigen_indoors"
  "worldgen_indoor|baselines/data/table2/indoor/worldgen"
  "worldgen_urban|baselines/data/table2/urban/worldgen"
  "metaurban_urban|baselines/data/table2/urban/metaurban"
)

require_completed_result() {
  local label="$1"
  local result_file
  case "$label" in
    spatialgen_indoor)
      result_file="baselines/results/spatialgen/indoor/table2_full.json"
      ;;
    infinigen_indoors_indoor)
      result_file="baselines/results/table2_full.json"
      ;;
    worldgen_indoor)
      result_file="baselines/results/worldgen/indoor/table2_full.json"
      ;;
    worldgen_urban)
      result_file="baselines/results/worldgen/urban/table2_full.json"
      ;;
    metaurban_urban)
      result_file="baselines/results/metaurban/urban/table2_full.json"
      ;;
    *)
      printf 'Unknown archive label: %s\n' "$label" >&2
      return 1
      ;;
  esac

  test -s "$result_file"
  test "$(grep -cE '"status"[[:space:]]*:[[:space:]]*"complete"' "$result_file")" -eq 7
}

archive_one() {
  local label="$1"
  local source_rel="$2"
  local source_abs="$REPO_ROOT/$source_rel"
  local expected_prefix="$REPO_ROOT/baselines/data/table2/"
  local archive="$ARCHIVE_ROOT/$label.tar.zst"
  local partial="$archive.partial"
  local inventory="$ARCHIVE_ROOT/$label.inventory.tsv"
  local hashes="$ARCHIVE_ROOT/$label.files.sha256"
  local members="$ARCHIVE_ROOT/$label.members.txt"
  local summary="$ARCHIVE_ROOT/$label.summary.tsv"
  local marker="$(dirname -- "$source_abs")/$(basename -- "$source_abs").ARCHIVED.json"
  local bytes files links dirs nodes archive_bytes archive_sha

  require_completed_result "$label"

  if test ! -e "$source_abs"; then
    test -s "$archive"
    "$ZSTD_BIN" -q -t -- "$archive"
    printf '[%s] already archived and verified; skipping\n' "$label"
    return 0
  fi

  case "$(realpath -e -- "$source_abs")/" in
    "$expected_prefix"*) ;;
    *)
      printf '[%s] refusing unexpected source path: %s\n' "$label" "$source_abs" >&2
      return 1
      ;;
  esac

  if test -e "$archive" || test -e "$partial"; then
    printf '[%s] refusing to overwrite an existing archive or partial file\n' "$label" >&2
    return 1
  fi

  bytes="$(du -s -B1 -- "$source_abs" | awk '{print $1}')"
  files="$(find "$source_abs" -type f -printf '.' | wc -c)"
  links="$(find "$source_abs" -type l -printf '.' | wc -c)"
  dirs="$(find "$source_abs" -type d -printf '.' | wc -c)"
  nodes=$((files + links + dirs))
  printf '[%s] inventory: bytes=%s files=%s links=%s dirs=%s\n' \
    "$label" "$bytes" "$files" "$links" "$dirs"

  find "$source_rel" -printf '%y\t%m\t%U\t%G\t%s\t%T@\t%p\t%l\n' \
    | LC_ALL=C sort > "$inventory.partial"
  mv -- "$inventory.partial" "$inventory"

  printf '[%s] hashing all regular files before packing\n' "$label"
  if test "${REUSE_HASHES:-0}" = 1 \
      && test -s "$hashes" \
      && test "$(wc -l < "$hashes")" -eq "$files"; then
    printf '[%s] reusing the complete pre-pack hash manifest\n' "$label"
  else
    find "$source_rel" -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r -n 16 -P 4 sha256sum --binary > "$hashes.partial"
    test "$(wc -l < "$hashes.partial")" -eq "$files"
    mv -- "$hashes.partial" "$hashes"
  fi

  printf '[%s] creating %s\n' "$label" "$partial"
  tar --acls --xattrs --numeric-owner --sparse -C "$REPO_ROOT" -cpf - "$source_rel" \
    | nice -n 10 "$ZSTD_BIN" -T4 -3 --long=27 --check -q -o "$partial"

  printf '[%s] testing compressed frame and tar member stream\n' "$label"
  "$ZSTD_BIN" -q -t -- "$partial"
  tar -I "$ZSTD_BIN" -tf "$partial" > "$members.partial"
  test "$(wc -l < "$members.partial")" -eq "$nodes"
  mv -- "$members.partial" "$members"

  archive_bytes="$(stat -c '%s' -- "$partial")"
  archive_sha="$(sha256sum --binary "$partial" | awk '{print $1}')"
  printf 'label\tsource\toriginal_allocated_bytes\tregular_files\tsymlinks\tdirectories\tarchive_bytes\tarchive_sha256\n' > "$summary.partial"
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' \
    "$label" "$source_rel" "$bytes" "$files" "$links" "$dirs" \
    "$archive_bytes" "$archive_sha" >> "$summary.partial"
  mv -- "$summary.partial" "$summary"
  mv -- "$partial" "$archive"

  printf '[%s] archive verified; deleting only the archived source tree\n' "$label"
  find "$source_abs" -depth -delete
  test ! -e "$source_abs"

  printf '{\n  "archive": "%s",\n  "archive_sha256": "%s",\n  "original_allocated_bytes": %s,\n  "archive_bytes": %s,\n  "restore_command": "tar -I zstd -xpf %s -C %s"\n}\n' \
    "${archive#"$REPO_ROOT/"}" "$archive_sha" "$bytes" "$archive_bytes" \
    "${archive#"$REPO_ROOT/"}" "$REPO_ROOT" > "$marker"
  printf '[%s] complete: archive_bytes=%s reclaimed_bytes=%s\n' \
    "$label" "$archive_bytes" "$((bytes - archive_bytes))"
}

for item in "${items[@]}"; do
  IFS='|' read -r label source_rel <<< "$item"
  archive_one "$label" "$source_rel"
done

printf 'All selected completed Table 2 outputs are archived and verified.\n'

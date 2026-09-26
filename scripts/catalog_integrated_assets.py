"""Build an English catalog of retained modeling files and their provenance."""
from pathlib import Path
from urllib.parse import unquote
from collections import Counter
import json

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"


def main():
    plan = json.loads((AUDIT / "integration_plan.json").read_text())
    copied = {
        r["destination"]: r
        for r in map(
            json.loads, (AUDIT / "integration_copies.jsonl").read_text().splitlines()
        )
    }
    rebasing = (
        json.loads((AUDIT / "dependency_rebasing.json").read_text())
        if (AUDIT / "dependency_rebasing.json").exists()
        else {"files": [], "pending_files": []}
    )
    rebased = {r["destination"]: r for r in rebasing["files"]}
    rebase_journal = AUDIT / "dependency_rebasing.jsonl"
    if rebase_journal.exists():
        rebased.update(
            {
                r["destination"]: r
                for r in map(json.loads, rebase_journal.read_text().splitlines())
            }
        )
    entries = []
    pending = []
    for row in plan["files"]:
        destination = row["destination"]
        path = ROOT / destination
        record = copied.get(destination)
        if not record or not path.is_file():
            pending.append(destination)
            continue
        current = rebased.get(destination, {})
        if current.get("before_sha256") not in (
            None,
            record.get("stored_sha256", record["sha256"]),
        ):
            current = {}  # A refreshed source snapshot superseded this rebase record.
        entry = {
            **row,
            "stored_bytes": path.stat().st_size,
            "source_sha256": record["sha256"],
            "stored_sha256": current.get(
                "after_sha256", record.get("stored_sha256", record["sha256"])
            ),
            "storage": record.get("storage", "original_bytes"),
            "path_fields_rebased": current.get("path_fields_changed", 0),
        }
        entries.append(entry)
    aliases = plan.get("source_aliases", [])
    retained = {row["destination"] for row in entries}
    aliases = [
        {
            **row,
            "retained_in_selected_collection": row["canonical_destination"] in retained,
        }
        for row in aliases
    ]
    resolution = (
        json.loads((AUDIT / "dependency_resolution.json").read_text())
        if (AUDIT / "dependency_resolution.json").exists()
        else {}
    )
    known = {row["destination"] for row in plan["files"]}
    historical_copies = [
        {
            **row,
            "status": "additional historical snapshot",
            "stored_bytes": (ROOT / name).stat().st_size,
        }
        for name, row in copied.items()
        if name not in known and (ROOT / name).is_file()
    ]
    report = {
        "scope": plan["scope"],
        "assets": entries,
        "source_aliases": aliases,
        "pending_model_files": pending,
        "missing_original_dependencies": resolution.get(
            "missing_original_dependencies", []
        ),
        "pending_dependency_files": rebasing["pending_files"],
        "source_root_uri": plan["source_root_uri"],
        "historical_city_and_backup_index": plan.get("index_only", []),
        "note": "Compressed Blender files preserve the complete decoded source content. Dependency rebasing changes only path fields. Existing historical signage and model appearance are preserved.",
    }
    report.update(
        {
            "additional_historical_copies": historical_copies,
            "external_dependencies": resolution.get("external_files_copied", []),
            "support_file_manifest": "../docs/assets/support_copy_manifest.json",
            "modeling_source_manifest": "../docs/assets/modeling_source_manifest.json",
            "concurrent_source_update_snapshots": "../docs/assets/refreshed_snapshots.json",
            "historical_copy_note": "Additional historical snapshots preserve source bytes and may retain original external paths. The selected asset collection is tracked separately in assets.",
        }
    )
    (ROOT / "assets/catalog.json").write_text(json.dumps(report, indent=2) + "\n")
    groups = Counter("/".join(Path(row["destination"]).parts[2:4]) for row in entries)
    lines = [
        "# Authored asset collection",
        "",
        "This directory contains copied model files, supporting textures and metadata, and historical modeling scripts. It does not use symbolic links or hard links to the original project.",
        "",
        "## Layout",
        "",
        "```text",
        "assets/",
        "  models/urban_components/  Individual objects, buildings, vegetation, and authored collections",
        "  models/urban_scenes/      Extracted scene components and authored neighborhood scenes",
        "  models/indoor_scenes/     Interior and villa models",
        "  dependencies/            Referenced fonts, HDR images, and external vehicle libraries\n  history/                 Additional historical source snapshots and backups",
        "  catalog.json             Model paths, source provenance, checksums, and dependency status",
        "```",
        "",
        "The [catalog](catalog.json) is the authoritative inventory. Source paths containing non-ASCII characters are percent-encoded; decode them with `urllib.parse.unquote` when needed. The [integration report](../docs/assets/integration_report.md) documents coverage and validation.",
        "",
        "Native Blender compression is lossless and can be opened directly by Blender. Geometry, materials, and existing modeled signage retain their source appearance. Dependency paths are converted to local relative paths. Use Blender 5.1.2 for the complete collection: some source files use its newer file format.",
        "",
        "Historical scripts beside the models retain their version-specific algorithms. Current modeling entry points remain in `scripts/` and `extensions/infinigen/`; full regeneration still requires the documented Infinigen installation and dependencies. Complete-city histories and automatic backups outside the selected asset scope remain indexed in the catalog.",
        "",
        "## Model groups",
        "",
        "| Group | Files |",
        "|---|---:|",
    ]
    for group, count in sorted(groups.items()):
        lines.append(f"| [{group}](models/{group}/) | {count} |")
    if pending:
        lines += [
            "",
            f"Integration is in progress: {len(pending)} selected model files are still being copied.",
        ]
    (ROOT / "assets/README.md").write_text("\n".join(lines) + "\n")
    legacy = json.loads((AUDIT / "original_location_survey.json").read_text())
    family_lines = [
        "# Find assets by type",
        "",
        "Use the links below for object and scene families. Each directory retains authored revisions and any associated modeling scripts. The complete inventory, including additional collections, is in [catalog.json](catalog.json).",
        "",
        "| Asset family | Level | Local directories |",
        "|---|---|---|",
    ]
    for family in legacy["assets"]:
        prefixes = [
            unquote(p).split("/infinigen/", 1)[1]
            for p in family["original_output_directories"]
        ]
        alias_targets = {
            a["canonical_destination"]
            for a in aliases
            if any(
                unquote(a["source_relative_uri"]).startswith(prefix + "/")
                for prefix in prefixes
            )
        }
        paths = sorted(
            {
                str(Path(row["destination"]).parent)
                for row in entries
                if row["destination"] in alias_targets
                or any(
                    unquote(row["source_relative_uri"]).startswith(prefix + "/")
                    for prefix in prefixes
                )
            }
        )
        if family["id"] == "parks":
            family = {**family, "name": "Community and neighborhood parks"}
            paths = sorted(
                {
                    str(Path(row["destination"]).parent)
                    for row in entries
                    if "park" in row["destination"]
                    and "archive_" not in row["destination"]
                    and Path(row["destination"]).name == "scene.blend"
                }
            )
        links = ", ".join(
            f'[{Path(path).name}]({path.removeprefix("assets/")}/)' for path in paths
        )
        family_lines.append(
            f'| {family["name"]} | {family["level"]} | {links or "See pending files in the catalog"} |'
        )
    (ROOT / "assets/FAMILIES.md").write_text("\n".join(family_lines) + "\n")
    readme = ROOT / "assets/README.md"
    readme.write_text(
        readme.read_text().replace(
            "## Model groups",
            "The [asset family index](FAMILIES.md) provides direct links for bicycles, delivery lockers, factories, schools, police stations, parks, and other named families.\n\n## Model groups",
        )
    )
    print(
        json.dumps(
            {
                "model_files": len(entries),
                "pending": len(pending),
                "logical_bytes": sum(x["bytes"] for x in entries),
                "stored_bytes": sum(x["stored_bytes"] for x in entries),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

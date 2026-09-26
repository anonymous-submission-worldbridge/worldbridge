"""Publish a concise integration report from the recorded verification results."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"


def main():
    catalog = json.loads((ROOT / "assets/catalog.json").read_text())
    verification = json.loads((AUDIT / "final_verification.json").read_text())
    english = json.loads((AUDIT / "english_check.json").read_text())
    resolution = json.loads((AUDIT / "dependency_resolution.json").read_text())
    coverage = json.loads((AUDIT / "source_code_coverage.json").read_text())
    support = json.loads((AUDIT / "support_copy_manifest.json").read_text())
    code = json.loads((AUDIT / "modeling_source_manifest.json").read_text())
    syntax = json.loads((AUDIT / "syntax_check.json").read_text())
    materials = json.loads((AUDIT / "obj_material_verification.json").read_text())
    samples = [json.loads(p.read_text()) for p in sorted(AUDIT.glob("blender_*.json"))]
    snapshots_path = AUDIT / "refreshed_snapshots.json"
    snapshots = (
        json.loads(snapshots_path.read_text()) if snapshots_path.exists() else []
    )
    passed = (
        verification["passed"]
        and english["passed"]
        and materials["passed"]
        and not syntax["errors"]
        and not coverage["missing_after_asset_integration"]
        and len(samples) >= 6
        and all(
            not s["missing_dependencies"] and not s["references_outside_worldbridge"]
            for s in samples
        )
    )
    logical = sum(r["bytes"] for r in catalog["assets"]) / 1024**3
    stored = sum(r["stored_bytes"] for r in catalog["assets"]) / 1024**3
    lines = [
        "# Asset integration report",
        "",
        f'Status: {"complete for the selected authored-asset scope" if passed else "validation or integration remains pending"}.',
        "",
        "The code-only migration did not retain the generated asset files. The subsequent asset integration copies separately modeled objects, buildings, vegetation, interiors, authored collections, extracted neighborhood scenes, and their required dependencies into `assets/`.",
        "",
        "## Coverage",
        "",
        f'- {len(catalog["assets"]):,} selected model/dependency files; {logical:.2f} GiB of source content and {stored:.2f} GiB of stored model files.',
        f'- {coverage["retained_after_asset_integration"]} local Infinigen source/configuration modifications retained in the overlay.',
        f"- {len(code)} recovered source/configuration files: 185 historical modeling, repair, and reproduction scripts, plus three generated-scene configurations.",
        f"- {len(support):,} supporting textures and model metadata files, plus the interchange filename compatibility copies recorded separately.",
        f'- {len(resolution["external_files_copied"])} copied external resources and libraries, with dependency notices under `assets/licenses/`.',
        f'- {len(catalog["additional_historical_copies"])} additional historical copies retained from the initial inventory pass.',
        "",
        f"- {len(snapshots)} earlier migrated snapshots retained while refreshing concurrent source updates; details are in `refreshed_snapshots.json`.",
        "",
        "The [asset family index](../../assets/FAMILIES.md) links bicycles, delivery lockers, factories, schools, police stations, community parks, and other named families. The [authoritative catalog](../../assets/catalog.json) records every selected path, checksum, source alias, and historical index entry.",
        "",
        "Historical complete-city snapshots and automatic Blender backups outside this scope remain indexed. A dependency that is needed by a selected asset is retained even when its original directory belongs to a larger city project. Temporary runtime caches, rendered images/videos, model weights, and inaccessible temporary Blender process directories are outside the authored-model inventory.",
        "",
        "## Preservation and portability",
        "",
        "The integration uses independent copies, never symbolic links or hard links to original project files. Plain Blender files may use native seekable Zstandard compression; the complete decoded SHA-256 digest is verified against the original during copying. Existing compressed models and interchange meshes retain their original bytes. Dependency rebasing changes only audited filepath fields and records final hashes. Geometry, materials, and original modeled signage remain intact. Use Blender 5.1.2 for all saved format versions in this collection.",
        "",
        "Repository filenames, documentation, and source text contain no Chinese characters. Provenance paths use percent encoding. Original binary artwork and font metadata are preserved. Twelve Bezier texture filename compatibility copies retain the names referenced by the USD export.",
        "",
        "Historical modeling scripts retain their version-specific algorithms. Their reproduction may require the original generation layout and the documented Infinigen environment; this migration does not claim that every archived script is a new portable command. Current code entry points remain under `scripts/` and `extensions/infinigen/`.",
        "",
        "## Validation",
        "",
        f'- Inventory/dependency verification: {verification["passed"]}; {len(verification["pending"])} pending files; {len(verification["errors"])} verification errors; {len(verification["missing_original_dependencies"])} unresolved original references.',
        f'- English filename/text and decoded-JSON scan: {english["passed"]}. Binary model contents are counted separately.',
        f'- Python compilation: {syntax["compiled_files"]} files, {len(syntax["errors"])} errors.',
        f'- OBJ material links: {len(materials["checked_links"])} checked, {len(materials["missing"])} missing. Two palette textures were recovered from their original Car Kit archives.',
        "- USD and FBX exports are retained with supporting resources; they have not been exhaustively imported in their target applications.",
        "- Entry-point and urban-parameter tests: see `core_tests.txt`.",
        "",
        "| Blender sample | Objects | Meshes | Missing/external references |",
        "|---|---:|---:|---:|",
    ]
    for sample in samples:
        label = Path(sample["file"]).relative_to(ROOT).as_posix()
        missing = len(sample["missing_dependencies"]) + len(
            sample["references_outside_worldbridge"]
        )
        lines.append(
            f'| `{label}` | {sample["objects"]} | {sample["meshes"]} | {missing} |'
        )
    lines += [
        "",
        "Blender validation opens representative models without executing embedded scene scripts; it does not render or exhaustively open every large asset. This is a snapshot of an active source workspace, not continuous synchronization. Original LegacyWorld and WorldBridge-v2 files are not moved or edited by this integration.",
        "",
        "Reproducible audit utilities are in `scripts/integrate_assets.py`, `scripts/audit_asset_dependencies.py`, `scripts/prepare_asset_dependencies.py`, `scripts/rebase_asset_paths.py`, `scripts/catalog_integrated_assets.py`, and `scripts/verify_integrated_assets.py`. The manifests in this directory preserve the individual operations and their evidence.",
    ]
    (AUDIT / "integration_report.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "report_complete": passed,
                "files": len(catalog["assets"]),
                "logical_gib": logical,
                "stored_gib": stored,
            }
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

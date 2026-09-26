"""Index retained modeling source by provenance and asset family."""
import ast
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/modeling"
FAMILIES = [
    (
        "Shared bicycles and docking stations",
        ["scripts/generate_urban_v3_sharedbicycle*.py"],
        "Procedural bicycles, docks, and stations.",
    ),
    (
        "Food lockers, parcel lockers, and delivery stations",
        ["scripts/generate_urban_v3_delivery.py", "scripts/urban_assets.py"],
        "Live procedural builders, including articulated doors.",
    ),
    (
        "Factory buildings",
        ["extensions/infinigen/infinigen/assets/objects/urban/factory_building.py"],
        "FactoryBuildingFactory creates industrial geometry.",
    ),
    (
        "Schools and campuses",
        ["scripts/generate_urban_v3_school.py"],
        "Campus buildings, interiors, sports grounds, and site geometry.",
    ),
    (
        "Police stations",
        ["scripts/generate_urban_v3_police.py"],
        "Three reference-driven station variants and their sites.",
    ),
    (
        "Parks and public spaces",
        [
            "extensions/infinigen/infinigen/assets/objects/decor/urban_public_space.py",
            "scripts/build_community_reading_park2.py",
            "scripts/build_urban_v1_full_connect3.py",
            "scripts/refine_urban_v3_all*_park.py",
        ],
        "Public-space factories and scene assembly; assembly requires generated inputs.",
    ),
    (
        "Benches and trash bins",
        [
            "scripts/generate_urban_v3_bench_trashbin*.py",
            "extensions/infinigen/infinigen/assets/objects/street_furniture/street_assets.py",
        ],
        "Street furniture geometry and shared factories.",
    ),
    (
        "Streetlights",
        [
            "extensions/infinigen/infinigen_examples/streetlight_render.py",
            "extensions/infinigen/infinigen/assets/objects/street_furniture/street_assets.py",
        ],
        "Streetlight construction and preview entry point.",
    ),
    (
        "Traffic signals",
        [
            "scripts/generate_urban_v3_trafficlight*.py",
            "extensions/infinigen/infinigen/assets/objects/traffic/traffic_light.py",
        ],
        "Traffic signal geometry and variants.",
    ),
    (
        "Phone booths",
        [
            "extensions/infinigen/infinigen_examples/phonebooth*_render.py",
            "extensions/infinigen/infinigen/assets/objects/street_furniture/street_assets.py",
        ],
        "Phone booth geometry and versioned preview scripts.",
    ),
    (
        "Bus stops",
        ["scripts/generate_urban_v3_busstop*.py"],
        "Bus shelter and stop geometry.",
    ),
    (
        "Kiosks and ATMs",
        ["scripts/generate_urban_v3_kiosk*.py", "scripts/generate_urban_v3_atm*.py"],
        "Kiosk revisions and ATM facilities.",
    ),
    (
        "Trees and groundcover",
        [
            "extensions/infinigen/infinigen/assets/objects/trees/urban_tree.py",
            "extensions/infinigen/infinigen/assets/objects/grassland/urban_groundcover.py",
            "extensions/infinigen/infinigen_examples/grass*_render.py",
        ],
        "Procedural tree and groundcover factories.",
    ),
    (
        "Sculptures and pavilions",
        ["scripts/generate_urban_v3_sculpture*.py"],
        "Sculpture and pavilion geometry.",
    ),
    (
        "Fountains",
        [
            "extensions/infinigen/infinigen/assets/objects/decor/urban_public_space.py",
            "scripts/render_urban_v3_fountain_showcase.py",
        ],
        "Fountain construction and variants.",
    ),
    (
        "Outdoor fitness facilities",
        ["scripts/generate_urban_v3_fitness.py"],
        "Exercise equipment and outdoor fitness sites.",
    ),
    (
        "Libraries",
        ["scripts/generate_urban_v3_library.py"],
        "Library buildings and interiors.",
    ),
    (
        "Fire stations",
        ["scripts/generate_urban_v3_fire.py"],
        "Station architecture; imported vehicle meshes remain external inputs.",
    ),
    (
        "Hospitals",
        ["scripts/generate_urban_v3_hospital.py"],
        "Hospital architecture and clinical spaces.",
    ),
    (
        "Gas stations",
        ["scripts/generate_urban_v3_gass.py"],
        "Station canopy, pumps, shop, and site.",
    ),
    (
        "Pharmacies",
        [
            "scripts/generate_urban_v3_pharmacy.py",
            "scripts/build_pharmacy2.py",
            "scripts/pharmacy2_asset_factory.py",
        ],
        "Pharmacy geometry, fixtures, and later scene variants.",
    ),
    (
        "Commercial buildings and shops",
        ["scripts/commercial_*.py", "scripts/generate_urban_v3_all43*.py"],
        "Shop and commercial-block builders and refinements.",
    ),
    (
        "Playgrounds and sports areas",
        ["scripts/generate_urban_v3_all44*.py"],
        "Recreation and sports scene variants.",
    ),
    (
        "Residential buildings",
        [
            "scripts/generate_urban_v3_all45*.py",
            "scripts/run_generate_indoors_all4*.py",
        ],
        "Residential layouts, interiors, and assembly stages.",
    ),
    (
        "Lakes and waterfronts",
        [
            "scripts/generate_urban_v3_lake.py",
            "extensions/infinigen/infinigen/assets/objects/decor/urban_lake.py",
        ],
        "Lake geometry, shoreline, and environment construction.",
    ),
    (
        "Roads, fences, and green belts",
        [
            "scripts/generate_urban_v3_road*.py",
            "scripts/generate_urban_v3_fence*.py",
            "extensions/infinigen/infinigen_examples/curb_belt*_render.py",
        ],
        "Road and boundary geometry.",
    ),
    (
        "Vehicles",
        [
            "extensions/infinigen/infinigen/assets/objects/vehicles/*.py",
            "extensions/infinigen/infinigen_examples/vehicle_demo*.py",
        ],
        "Vehicle factories and external OpenX import adapters.",
    ),
    (
        "Robots and articulated task animation",
        [
            "scripts/robot1_model.py",
            "scripts/build_render_robot1.py",
            "scripts/robot1_tasks.py",
            "scripts/robot1_*.py",
        ],
        "Robot geometry, joints, poses, task plans, and media helpers.",
    ),
    (
        "Connected neighborhood scenes",
        [
            "scripts/build_urban_v1_full_connect*.py",
            "scripts/connect*_plan.py",
            "scripts/prepare_connect*_assets.py",
        ],
        "Layout and composition code; generate referenced component assets first.",
    ),
]


def main():
    audit = json.loads((AUDIT / "source_audit.json").read_text())
    added = json.loads((AUDIT / "added_sources.json").read_text())
    moved = json.loads((AUDIT / "relocated_sources.json").read_text())
    replacements = {"infinigen/" + r["source_relative_uri"]: r for r in moved}
    replacements.update(
        {
            r["source_relative_uri"]: r
            for r in added
            if "source_updates/" not in r["destination"]
        }
    )
    snapshots = {
        r["source_relative_uri"]: r
        for r in added
        if "source_updates/" in r["destination"]
    }
    records = []
    for row in audit["files"]:
        current = {**row, **replacements.get(row["source_relative_uri"], {})}
        target = ROOT / current["destination"]
        current["present"] = target.is_file()
        current["current_sha256"] = (
            hashlib.sha256(target.read_bytes()).hexdigest()
            if target.is_file()
            else None
        )
        if row["source_relative_uri"] in snapshots:
            current["later_source_revision"] = snapshots[row["source_relative_uri"]][
                "destination"
            ]
        records.append(current)
    known = {r["source_relative_uri"] for r in records}
    records.extend(r for r in added if r["source_relative_uri"] not in known)
    missing = [
        r["destination"] for r in records if not (ROOT / r["destination"]).is_file()
    ]
    families = []
    lines = [
        "# Modeling source index",
        "",
        "This collection preserves the code that constructs the assets. Saved models and model export files are not packaged.",
        "",
        "Main generators remain in `scripts/`; local Infinigen factories and configurations remain in `extensions/infinigen/`. Historical project versions are under `scripts/modeling_history/`. Floor plans and camera routes recovered from output directories are under `configs/modeling/`.",
        "",
        "## Find a modeling implementation",
        "",
        "The table links the implementation files. `catalog.json` lists every audited source and all matching family files, with checksums and source provenance.",
        "",
        "| Family | Implementation | Role |",
        "|---|---|---|",
    ]
    for name, patterns, description in FAMILIES:
        paths = list(
            dict.fromkeys(p for pattern in patterns for p in sorted(ROOT.glob(pattern)))
        )
        assert paths, name
        entries = []
        for p in paths:
            tree = ast.parse(p.read_text())
            symbols = [
                {"name": n.name, "line": n.lineno}
                for n in tree.body
                if isinstance(n, (ast.FunctionDef, ast.ClassDef))
            ]
            entries.append({"path": str(p.relative_to(ROOT)), "symbols": symbols})
        families.append(
            {"name": name, "description": description, "implementations": entries}
        )
        links = ", ".join(f"[{p.name}](../../{p.relative_to(ROOT)})" for p in paths[:3])
        if len(paths) > 3:
            links += f" (plus {len(paths)-3} versions in the catalog)"
        lines.append(f"| {name} | {links} | {description} |")
    lines += [
        "",
        "## Running the code",
        "",
        "Install Blender and the documented Infinigen environment, then apply the overlay with `python scripts/setup_extensions.py --apply`. A saved model is a generated output, not a repository deliverable.",
        "",
        "Individual procedural builders construct geometry in Blender. Scene assembly, repair, and rendering scripts can require previously generated component scenes or third-party resources. This source audit does not assert that all scripts can regenerate a complete city from an empty directory. Configure external resources and generate prerequisites before running those stages.",
        "",
        "Historical snapshots retain their original algorithms and revision-specific assumptions. Use the current entry points above for active development; the history directory is for reference and reproduction of earlier versions.",
        "",
        "## Audit",
        "",
        f"- {len(records)} authored source/configuration paths checked; {len(missing)} missing.",
        "- 25 previously omitted scripts recovered, plus four floor-plan/camera-route configurations.",
        "- 59 historical project scripts relocated out of the former model directory.",
        "- Three later source revisions retained separately without overwriting refactored entry points.",
        "- The earlier count of 185 historical scripts included 126 third-party Shapely files. Those files are excluded from the authored-code inventory and removed from the project copy.",
        "- Model and support-file removals are recorded in `removal_summary.json` and `removed_files.jsonl`.",
        "- The source projects are read-only inputs to this correction.",
        "",
        "See [verification.json](verification.json) for the final source, syntax, language, and model-removal checks. Older binary-copy reports under `docs/assets/` are historical records superseded by this source-only inventory.",
    ]
    catalog = {
        "scope": "Authored modeling source and configurations; generated model files excluded.",
        "files": records,
        "families": families,
        "missing": missing,
        "additional_source_revisions": list(snapshots.values()),
        "excluded_third_party": audit["excluded_third_party"],
    }
    (AUDIT / "catalog.json").write_text(json.dumps(catalog, indent=2) + "\n")
    (AUDIT / "README.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "source_paths": len(records),
                "families": len(families),
                "missing": missing,
            }
        )
    )


if __name__ == "__main__":
    main()

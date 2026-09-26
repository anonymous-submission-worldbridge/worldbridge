"""Refresh source files changed during migration while retaining earlier copies."""
from pathlib import Path
from urllib.parse import unquote, quote
import json
from blend_dependencies import inspect
from integrate_assets import copy_one, digest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"
SOURCE = ROOT.parent / "LegacyWorld/infinigen"


def main():
    plan = json.loads((AUDIT / "integration_plan.json").read_text())
    journal = AUDIT / "integration_copies.jsonl"
    copied = {
        r["destination"]: r for r in map(json.loads, journal.read_text().splitlines())
    }
    initial = {
        r["source_relative_uri"]: r["mtime_ns"]
        for r in json.loads((AUDIT / "source_inventory.json").read_text())["files"]
    }
    snapshots_path = AUDIT / "refreshed_snapshots.json"
    snapshots = (
        json.loads(snapshots_path.read_text()) if snapshots_path.exists() else []
    )
    refreshed = []
    for row in plan["files"]:
        old = copied.get(row["destination"])
        if old is None:
            continue
        source = SOURCE / unquote(row["source_relative_uri"])
        stat = source.stat()
        recorded_mtime = old.get(
            "source_mtime_ns", initial.get(row["source_relative_uri"])
        )
        if stat.st_size == old["bytes"] and (
            recorded_mtime is None or stat.st_mtime_ns == recorded_mtime
        ):
            continue
        target = ROOT / row["destination"]
        previous_hash = digest(target)
        archived = target.with_name(
            target.stem + ".snapshot_" + previous_hash[:12] + target.suffix
        )
        if archived.exists():
            raise RuntimeError("Snapshot destination already exists: " + str(archived))
        print("Refreshing changed source:", row["destination"], flush=True)
        target.rename(archived)
        updated = {**row, "bytes": stat.st_size}
        try:
            record = copy_one(updated)
        except Exception:
            if not target.exists():
                archived.rename(target)
            raise
        with journal.open("a") as out:
            out.write(json.dumps(record) + "\n")
        with (AUDIT / "dependency_rebasing.jsonl").open("a") as out:
            out.write(
                json.dumps(
                    {
                        "destination": row["destination"],
                        "status": "requires_rebase",
                        "path_fields_changed": 0,
                        "source_sha256": record["sha256"],
                    }
                )
                + "\n"
            )
        row.update(updated)
        snapshots.append(
            {
                "destination": str(archived.relative_to(ROOT)),
                "sha256": previous_hash,
                "replaced_destination": row["destination"],
                "previous_source_sha256": old["sha256"],
                "new_source_sha256": record["sha256"],
                "new_source_mtime_ns": record.get("source_mtime_ns"),
            }
        )
        snapshots_path.write_text(json.dumps(snapshots, indent=2) + "\n")
        if target.suffix == ".blend":
            metadata = inspect(target)
            for item in metadata["dependencies"]:
                item["path_uri"] = quote(item.pop("path"), safe="/+_.-<>")
            with (AUDIT / "blend_dependencies.jsonl").open("a") as out:
                out.write(
                    json.dumps(
                        {
                            "source_relative_uri": row["source_relative_uri"],
                            "audited_snapshot_sha256": record.get(
                                "stored_sha256", record["sha256"]
                            ),
                            **metadata,
                        }
                    )
                    + "\n"
                )
        refreshed.append(row["destination"])
        plan["bytes"] = sum(r["bytes"] for r in plan["files"])
        (AUDIT / "integration_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    print(json.dumps({"refreshed_files": refreshed}), flush=True)


if __name__ == "__main__":
    main()

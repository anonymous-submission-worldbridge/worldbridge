"""Verify inventory coverage, independent storage, support hashes, and local links."""
from pathlib import Path
from urllib.parse import unquote
import json
from integrate_assets import digest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"
SOURCE = ROOT.parent / "LegacyWorld/infinigen"


def main():
    catalog = json.loads((ROOT / "assets/catalog.json").read_text())
    copies = {
        r["destination"]: r
        for r in map(
            json.loads, (AUDIT / "integration_copies.jsonl").read_text().splitlines()
        )
    }
    initial = {
        r["source_relative_uri"]: r
        for r in json.loads((AUDIT / "source_inventory.json").read_text())["files"]
    }
    errors = []
    checked = 0
    for row in catalog["assets"]:
        target = ROOT / row["destination"]
        source = SOURCE / unquote(row["source_relative_uri"])
        if not target.is_file():
            errors.append({"file": row["destination"], "error": "missing model"})
            continue
        original, copied = source.stat(), target.stat()
        if target.is_symlink() or (original.st_dev, original.st_ino) == (
            copied.st_dev,
            copied.st_ino,
        ):
            errors.append(
                {"file": row["destination"], "error": "model links to source"}
            )
        if copied.st_size != row["stored_bytes"] or original.st_size != row["bytes"]:
            errors.append(
                {"file": row["destination"], "error": "size changed since integration"}
            )
        stamp = copies[row["destination"]].get(
            "source_mtime_ns",
            initial.get(row["source_relative_uri"], {}).get("mtime_ns"),
        )
        if stamp is not None and original.st_mtime_ns != stamp:
            errors.append(
                {
                    "file": row["destination"],
                    "error": "source updated since the verified snapshot",
                }
            )
        if not row.get("source_sha256") or not row.get("stored_sha256"):
            errors.append(
                {"file": row["destination"], "error": "missing verified copy digest"}
            )
        checked += 1
    manifests = (
        "support_copy_manifest.json",
        "modeling_source_manifest.json",
        "interchange_compatibility_manifest.json",
        "openx_metadata_manifest.json",
        "asset_package_notice_manifest.json",
        "obj_texture_recovery_manifest.json",
    )
    support = 0
    for name in manifests:
        for row in json.loads((AUDIT / name).read_text()):
            path = ROOT / row["destination"]
            expected = row.get("current_sha256", row.get("sha256"))
            if not path.is_file() or digest(path) != expected:
                errors.append(
                    {
                        "file": row["destination"],
                        "error": "support/source digest mismatch",
                    }
                )
            support += 1
    resolution = json.loads((AUDIT / "dependency_resolution.json").read_text())
    for row in resolution["links"]:
        base = ROOT / row.get("path_base_destination", row["owner_destination"])
        target = (base.parent / row["new_path"][2:]).resolve()
        expected = (ROOT / row["dependency_destination"]).resolve()
        if (
            target != expected
            or not target.is_relative_to(ROOT)
            or not target.is_file()
        ):
            errors.append(
                {
                    "file": row["owner_destination"],
                    "error": "invalid local dependency",
                    "dependency": row["dependency_destination"],
                }
            )
    pending = catalog["pending_model_files"] + catalog["pending_dependency_files"]
    pending += resolution.get("pending_primary_metadata", [])
    result = {
        "models_checked": checked,
        "support_and_source_hashes_checked": support,
        "dependency_paths_checked": len(resolution["links"]),
        "errors": errors,
        "pending": pending,
        "missing_original_dependencies": resolution["missing_original_dependencies"],
        "model_digest_policy": "Each copy was hashed and read back during integration. Path rebasing records final hashes. This final pass checks inventory, sizes, independent inodes, support hashes, and dependency paths without redundantly rereading all large mesh payloads.",
        "passed": not errors
        and not pending
        and not resolution["missing_original_dependencies"],
    }
    (AUDIT / "final_verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("model_digest_policy",)}
        ),
        flush=True,
    )
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

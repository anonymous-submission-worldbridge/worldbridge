"""Resolve and copy the dependency closure of integrated Blender assets."""
from __future__ import annotations
from pathlib import Path
from urllib.parse import quote, unquote
import hashlib
import argparse
import json
import os
import shutil
import sys
from blend_dependencies import inspect
from integrate_assets import english_name, model_destination, digest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "LegacyWorld/infinigen"
AUDIT = ROOT / "docs/assets"


def canonical(path):
    value = str(path)
    for prefix in (
        "./external/",
        "./external/",
        "./external/",
    ):
        if value.startswith(prefix):
            return Path(os.path.normpath(str(ROOT.parent / value[len(prefix) :])))
    return Path(os.path.normpath(value))


def resolve(path, owner):
    candidate = canonical(
        owner.parent / path[2:]
        if path.startswith("//")
        else Path(path)
        if path.startswith("/")
        else owner.parent / path
    )
    if candidate.is_file():
        return candidate, None
    if "/usr/share/fonts/" in str(candidate):
        alternate = (
            Path("/usr/share/fonts") / str(candidate).split("/usr/share/fonts/", 1)[1]
        )
        if alternate.is_file():
            return alternate, "Same installed font recovered from a stale relative path"
    if "/openx-assets/" in str(candidate):
        alternate = (
            ROOT.parent / "openx-assets" / str(candidate).split("/openx-assets/", 1)[1]
        )
        if alternate.is_file():
            return (
                alternate,
                "Existing OpenX resource at its current workspace location",
            )
    if "/blender-4.5.4-linux-x64/" in str(candidate):
        alternate = (
            ROOT.parent
            / "blender-4.5.4"
            / str(candidate).split("/blender-4.5.4-linux-x64/", 1)[1]
        )
        if alternate.is_file():
            return (
                alternate,
                "Same Blender 4.5.4 resource in the installed distribution",
            )
    return None, str(candidate)


def dependency_target(path):
    if path.is_relative_to(SOURCE):
        return model_destination(str(path.relative_to(SOURCE)))
    if path.is_relative_to(ROOT.parent / "openx-assets"):
        return Path(
            "assets/dependencies/openx",
            *map(english_name, path.relative_to(ROOT.parent / "openx-assets").parts),
        ).as_posix()
    name = (
        hashlib.sha256(str(path).encode()).hexdigest()[:12]
        + "_"
        + english_name(path.name)
    )
    return "assets/dependencies/resources/" + name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--available-only",
        action="store_true",
        help="Resolve scanned primary assets while the metadata audit is still running.",
    )
    args = parser.parse_args()
    plan = json.loads((AUDIT / "integration_plan.json").read_text())
    full = json.loads((AUDIT / "complete_model_inventory.json").read_text())
    mapping = {
        canonical(SOURCE / unquote(r["source_relative_uri"])): r["destination"]
        for r in full["files"]
    }
    for r in full["source_aliases"]:
        mapping[canonical(SOURCE / unquote(r["source_relative_uri"]))] = r[
            "canonical_destination"
        ]
    selected = {
        canonical(SOURCE / unquote(r["source_relative_uri"])): r["destination"]
        for r in plan["files"]
    }
    metadata = {
        canonical(SOURCE / unquote(r["source_relative_uri"])): r
        for r in map(
            json.loads, (AUDIT / "blend_dependencies.jsonl").read_text().splitlines()
        )
    }
    closure_cache = AUDIT / "closure_metadata.jsonl"
    if closure_cache.exists():
        metadata.update(
            {
                canonical(unquote(r["source_uri"])): r
                for r in map(json.loads, closure_cache.read_text().splitlines())
            }
        )
    by_destination = {
        r["destination"]: canonical(SOURCE / unquote(r["source_relative_uri"]))
        for r in full["files"]
    }
    for origin, record in list(metadata.items()):
        representative = by_destination.get(mapping.get(origin))
        if representative is not None:
            metadata.setdefault(representative, record)
    for alias in full["source_aliases"]:
        origin = by_destination[alias["canonical_destination"]]
        if origin in metadata:
            metadata[
                canonical(SOURCE / unquote(alias["source_relative_uri"]))
            ] = metadata[origin]
    deferred = (
        [s for s in selected if s.suffix == ".blend" and s not in metadata]
        if args.available_only
        else []
    )
    queue = [s for s in selected if s.suffix == ".blend" and s not in deferred]
    seen = set()
    links = []
    missing = []
    copies = []
    additions = []
    while queue:
        source = queue.pop()
        if source in seen:
            continue
        seen.add(source)
        record = metadata.get(source)
        if record is None:
            print(
                "Inspecting dependency:", quote(str(source), safe="/+_.-"), flush=True
            )
            record = inspect(source)
            for item in record["dependencies"]:
                item["path_uri"] = quote(item.pop("path"), safe="/+_.-<>")
            metadata[source] = record
            with closure_cache.open("a") as cache:
                cache.write(
                    json.dumps(
                        {"source_uri": quote(str(source), safe="/+_.-"), **record}
                    )
                    + "\n"
                )
        if "error" in record:
            missing.append(
                {"owner_uri": quote(str(source), safe="/"), "error": record["error"]}
            )
            continue
        libraries = {}
        # Library entries define the origin of linked image/font ID paths.
        for item in record["dependencies"]:
            if item["kind"] == "Library":
                dep, _ = resolve(unquote(item["path_uri"]), source)
                if dep:
                    libraries[item["block_address"]] = dep
        for item in record["dependencies"]:
            if item["packed"]:
                continue
            owner = libraries.get(item["library_address"], source)
            dep, note = resolve(unquote(item["path_uri"]), owner)
            if dep is None:
                missing.append(
                    {
                        "owner_uri": quote(str(source), safe="/"),
                        "path_uri": item["path_uri"],
                        "kind": item["kind"],
                        "resolved_candidate_uri": quote(note, safe="/"),
                    }
                )
                continue
            target = mapping.get(dep, dependency_target(dep))
            mapping[dep] = target
            if dep not in selected and target not in selected.values():
                selected[dep] = target
                if dep.is_relative_to(SOURCE):
                    additions.append(
                        {
                            "source_relative_uri": quote(
                                str(dep.relative_to(SOURCE)), safe="/+_.-"
                            ),
                            "destination": target,
                            "bytes": dep.stat().st_size,
                            "kind": "linked_dependency",
                        }
                    )
                else:
                    destination = ROOT / target
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    expected = digest(dep)
                    if destination.exists():
                        if digest(destination) != expected:
                            raise RuntimeError(
                                "Existing dependency differs: " + str(destination)
                            )
                    else:
                        shutil.copyfile(dep, destination)
                    if digest(destination) != expected:
                        raise RuntimeError("Dependency copy mismatch")
                    copies.append(
                        {
                            "source_uri": quote(str(dep), safe="/+_.-"),
                            "destination": target,
                            "bytes": dep.stat().st_size,
                            "sha256": expected,
                            "relocation_note": note,
                        }
                    )
            selected.setdefault(dep, target)
            # Linked ID paths are interpreted relative to their owning library,
            # even when the ID block is cached in a different parent scene.
            path_base = (
                mapping.get(owner, dependency_target(owner))
                if owner != source
                else selected[source]
            )
            relative = "//" + os.path.relpath(ROOT / target, (ROOT / path_base).parent)
            links.append(
                {
                    "owner_destination": selected[source],
                    "path_base_destination": path_base,
                    "source_owner_uri": quote(str(source), safe="/+_.-"),
                    "dependency_destination": target,
                    "original_path_uri": item["path_uri"],
                    "new_path": relative,
                    "offset": item["offset"],
                    "capacity": item["capacity"],
                    "kind": item["kind"],
                    "relocation_note": note,
                }
            )
            if item["kind"] == "Library" and dep not in deferred:
                library_source = by_destination.get(target, dep)
                selected.setdefault(library_source, target)
                queue.append(library_source)
    unique_links = {}
    for link in links:
        key = (link["owner_destination"], link["offset"])
        if key in unique_links and unique_links[key]["new_path"] != link["new_path"]:
            raise RuntimeError(
                "Conflicting dependency paths through source aliases: "
                + link["owner_destination"]
            )
        unique_links.setdefault(key, link)
    links = list(unique_links.values())
    # Several original paths are aliases of one physical library. Keep one
    # retained file per destination and record promotion out of the history index.
    unique = {}
    for row in plan["files"] + additions:
        unique.setdefault(row["destination"], row)
    plan["files"] = list(unique.values())
    plan["bytes"] = sum(r["bytes"] for r in plan["files"])
    promoted = [r for r in plan.get("index_only", []) if r["destination"] in unique]
    plan.setdefault("promoted_dependencies", []).extend(promoted)
    plan["index_only"] = [
        r for r in plan.get("index_only", []) if r["destination"] not in unique
    ]
    (AUDIT / "integration_plan.json").write_text(json.dumps(plan, indent=2) + "\n")
    (AUDIT / "dependency_resolution.json").write_text(
        json.dumps(
            {
                "libraries_scanned": len(seen),
                "links": links,
                "missing_original_dependencies": missing,
                "external_files_copied": copies,
                "model_dependencies_added": additions,
                "pending_primary_metadata": [
                    quote(str(s), safe="/+_.-") for s in deferred
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "libraries_scanned": len(seen),
                "links": len(links),
                "missing": len(missing),
                "external_files": len(copies),
                "model_additions": len(additions),
            }
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()

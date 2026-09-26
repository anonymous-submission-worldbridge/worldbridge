"""Make copied Blender libraries portable by changing only dependency path fields."""
from __future__ import annotations
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote
import bisect
import argparse
import hashlib
import json
import os
import struct
import zstandard
from blend_dependencies import BlendReader
from integrate_assets import digest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"


def rebase(path, links):
    reader = BlendReader(path)
    patches = []
    try:
        for item in links:
            expected = unquote(item["original_path_uri"]).encode("utf-8")
            value = item["new_path"].encode("utf-8")
            offset = item["offset"]
            capacity = item["capacity"]
            if len(value) >= capacity:
                raise ValueError("Dependency path exceeds Blender field capacity")
            current = reader.read(offset, capacity).split(b"\0", 1)[0]
            if current == value:
                continue
            if current != expected:
                raise ValueError("Unexpected existing dependency field: " + str(path))
            patches.append((offset, value + b"\0" * (capacity - len(value))))
        if not patches:
            return {"path_fields_changed": 0}
        if reader.frames is None:
            before = digest(path)
            reader.close()
            reader = None
            with path.open("r+b") as writer:
                for offset, value in patches:
                    writer.seek(offset)
                    writer.write(value)
        else:
            changes = defaultdict(list)
            for offset, value in patches:
                cursor = 0
                while cursor < len(value):
                    i = bisect.bisect_right(reader.offsets, offset + cursor) - 1
                    at = offset + cursor - reader.offsets[i]
                    take = min(len(value) - cursor, reader.frames[i][2] - at)
                    changes[i].append((at, value[cursor : cursor + take]))
                    cursor += take
            partial = path.with_name(path.name + ".rebase_partial")
            table = []
            compressor = zstandard.ZstdCompressor(level=1)
            original_hash = hashlib.sha256()
            with partial.open("wb") as writer:
                for i, (offset, csize, dsize) in enumerate(reader.frames):
                    reader.file.seek(offset)
                    original_encoded = reader.file.read(csize)
                    if len(original_encoded) != csize:
                        raise RuntimeError("Incomplete original compressed frame")
                    original_hash.update(original_encoded)
                    if i in changes:
                        data = bytearray(
                            zstandard.ZstdDecompressor().decompress(
                                original_encoded, max_output_size=dsize
                            )
                        )
                        for at, value in changes[i]:
                            data[at : at + len(value)] = value
                        encoded = compressor.compress(data)
                        # Re-decode every altered frame; all other compressed
                        # frames are copied verbatim, preserving all mesh data.
                        if zstandard.ZstdDecompressor().decompress(encoded) != data:
                            raise RuntimeError("Altered frame verification failed")
                    else:
                        encoded = original_encoded
                    writer.write(encoded)
                    table.append((len(encoded), dsize))
                writer.write(struct.pack("<II", 0x184D2A5E, len(table) * 8 + 9))
                for csize, dsize in table:
                    writer.write(struct.pack("<II", csize, dsize))
                writer.write(struct.pack("<IBI", len(table), 0, 0x8F92EAB1))
            last_offset, last_size, _ = reader.frames[-1]
            reader.file.seek(last_offset + last_size)
            original_hash.update(reader.file.read())
            before = original_hash.hexdigest()
            reader.close()
            reader = None
            partial.replace(path)
        verifier = BlendReader(path)
        try:
            for offset, value in patches:
                if verifier.read(offset, len(value)) != value:
                    raise RuntimeError("Rebased dependency field mismatch")
        finally:
            verifier.close()
        return {
            "path_fields_changed": len(patches),
            "before_sha256": before,
            "after_sha256": digest(path),
            "stored_bytes": path.stat().st_size,
        }
    finally:
        if reader is not None:
            reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-bytes",
        type=int,
        help="Temporarily defer larger files while a primary copy is running.",
    )
    parser.add_argument(
        "--only-pending",
        action="store_true",
        help="Retry pending or explicitly invalidated owners and retain prior completed validation.",
    )
    args = parser.parse_args()
    data = json.loads((AUDIT / "dependency_resolution.json").read_text())
    owners = defaultdict(list)
    for link in data["links"]:
        owners[link["owner_destination"]].append(link)
    previous_path = AUDIT / "dependency_rebasing.json"
    previous = (
        {r["destination"]: r for r in json.loads(previous_path.read_text())["files"]}
        if previous_path.exists()
        else {}
    )
    journal = AUDIT / "dependency_rebasing.jsonl"
    if journal.exists():
        previous.update(
            {
                r["destination"]: r
                for r in map(json.loads, journal.read_text().splitlines())
            }
        )
    previous = {
        name: row
        for name, row in previous.items()
        if row.get("status") != "requires_rebase"
    }
    retry = set(owners)
    if args.only_pending:
        old_pending = (
            set(json.loads(previous_path.read_text())["pending_files"])
            if previous_path.exists()
            else set()
        )
        retry = {
            name
            for name, links in owners.items()
            if name not in previous
            or name in old_pending
            or any(link["dependency_destination"] in old_pending for link in links)
        }
    records = [
        row for name, row in previous.items() if name in owners and name not in retry
    ]
    missing = []
    copied = {
        json.loads(line)["destination"]
        for line in (AUDIT / "integration_copies.jsonl").read_text().splitlines()
    }
    copied.update(row["destination"] for row in data["external_files_copied"])
    for name, links in sorted(
        owners.items(),
        key=lambda pair: (ROOT / pair[0]).stat().st_size
        if (ROOT / pair[0]).is_file()
        else float("inf"),
    ):
        if name not in retry:
            continue
        path = ROOT / name
        if not path.is_file() or name not in copied:
            missing.append(name)
            continue
        if args.max_bytes is not None and path.stat().st_size > args.max_bytes:
            missing.append(name)
            continue
        absent = [
            x["dependency_destination"]
            for x in links
            if not (ROOT / x["dependency_destination"]).is_file()
        ]
        if absent:
            missing.extend(absent)
            continue
        result = rebase(path, links)
        if not result["path_fields_changed"] and name in previous:
            result = {k: v for k, v in previous[name].items() if k != "destination"}
            if result.get("after_sha256") and digest(path) != result["after_sha256"]:
                raise RuntimeError("Previously rebased asset changed: " + name)
        record = {"destination": name, **result}
        records.append(record)
        with journal.open("a") as out:
            out.write(json.dumps(record) + "\n")
        if len(records) % 25 == 0:
            print("Rebased/verified", len(records), "libraries", flush=True)
    (AUDIT / "dependency_rebasing.json").write_text(
        json.dumps({"files": records, "pending_files": sorted(set(missing))}, indent=2)
        + "\n"
    )
    print(
        json.dumps({"verified_libraries": len(records), "pending": len(set(missing))}),
        flush=True,
    )
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())

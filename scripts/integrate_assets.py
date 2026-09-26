"""Copy the audited modeling collection into this checkout without source links."""
from __future__ import annotations
import argparse
import concurrent.futures
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import time
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"
SOURCE = ROOT.parent / "LegacyWorld/infinigen"


def english_name(value):
    translations = {"\u5546\u94fa": "shops", "\u4f4f\u5b85": "residential"}
    for before, after in translations.items():
        value = value.replace(before, after)
    value = value.replace("\u2014", "_").replace("\u2013", "_").replace(" ", "_")
    return "".join(c if ord(c) < 128 else "_u%04x_" % ord(c) for c in value)


def model_destination(relative):
    parts = Path(relative).parts
    if parts[:2] == ("outputs", "outdoor_part_demo"):
        base, tail = "urban_components", parts[2:]
    elif parts[:2] == ("outputs", "outdoor_full_demo"):
        base, tail = "urban_scenes", parts[2:]
    elif parts[0] == "outputs":
        base, tail = "indoor_scenes", parts[1:]
    else:
        base, tail = "other", parts
    return Path("assets/models", base, *(english_name(p) for p in tail)).as_posix()


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def copy_one(row):
    source = SOURCE / unquote(row["source_relative_uri"])
    target = ROOT / row["destination"]
    before = source.stat()
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        source_hash = digest(source)
        stored_hash = digest(target)
        storage = "original_bytes"
        if source_hash != stored_hash:
            from blend_storage import decoded_digest

            if not source.suffix.startswith(".blend") or decoded_digest(target) != (
                source_hash,
                before.st_size,
            ):
                raise RuntimeError("Existing target differs: " + row["destination"])
            storage = "blender_seekable_zstandard"
        after = source.stat()
        if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
            raise RuntimeError(
                "Source changed during verification: " + row["source_relative_uri"]
            )
        return dict(
            row,
            sha256=source_hash,
            stored_sha256=stored_hash,
            stored_bytes=target.stat().st_size,
            storage=storage,
            source_mtime_ns=before.st_mtime_ns,
            status="verified_existing",
        )
    partial = target.with_name(target.name + ".integration_partial")
    with source.open("rb") as header:
        compress = source.suffix.startswith(".blend") and header.read(7) == b"BLENDER"
    if compress:
        from blend_storage import compress_copy, decoded_digest

        expected, decoded_size = compress_copy(source, partial)
        decoded_hash, verified_size, stored_hash = decoded_digest(
            partial, include_storage=True
        )
        if (decoded_hash, verified_size) != (expected, decoded_size):
            raise RuntimeError("Lossless Blender copy mismatch: " + row["destination"])
        storage = "blender_seekable_zstandard"
    else:
        h = hashlib.sha256()
        with source.open("rb") as reader, partial.open("wb") as writer:
            for block in iter(lambda: reader.read(8 * 1024 * 1024), b""):
                h.update(block)
                writer.write(block)
        expected = h.hexdigest()
        if digest(partial) != expected:
            raise RuntimeError("Copy checksum mismatch: " + row["destination"])
        stored_hash = expected
        storage = "original_bytes"
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise RuntimeError("Source changed during copy: " + row["source_relative_uri"])
    partial.replace(target)
    os.chmod(target, 0o664)
    return dict(
        row,
        sha256=expected,
        stored_sha256=stored_hash,
        stored_bytes=target.stat().st_size,
        storage=storage,
        source_mtime_ns=before.st_mtime_ns,
        status="copied_and_sha256_verified",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    plan = json.loads((AUDIT / "integration_plan.json").read_text())
    rows = plan["files"]
    existing = set()
    journal = AUDIT / "integration_copies.jsonl"
    if journal.exists():
        for line in journal.read_text().splitlines():
            row = json.loads(line)
            if (ROOT / row["destination"]).is_file():
                existing.add(row["destination"])
    pending = [r for r in rows if r["destination"] not in existing]
    required = sum(r["bytes"] for r in pending)
    if shutil.disk_usage(ROOT).free < required + 25 * 1024**3:
        raise RuntimeError("Insufficient free space for the audited copy and reserve")
    print(
        json.dumps({"pending_files": len(pending), "pending_bytes": required}),
        flush=True,
    )
    started = time.monotonic()
    total = 0
    done = 0
    errors = []
    # Small objects become available first; large scene libraries follow.
    pending.sort(key=lambda r: r["bytes"])
    with journal.open("a") as out, concurrent.futures.ThreadPoolExecutor(
        max_workers=args.workers
    ) as pool:
        futures = {pool.submit(copy_one, row): row for row in pending}
        for future in concurrent.futures.as_completed(futures):
            row = futures[future]
            try:
                result = future.result()
            except Exception as exc:
                errors.append(
                    {
                        "source_relative_uri": row["source_relative_uri"],
                        "error": str(exc),
                    }
                )
                print(json.dumps(errors[-1]), flush=True)
                continue
            out.write(json.dumps(result) + "\n")
            out.flush()
            total += row["bytes"]
            done += 1
            if done % 25 == 0 or row["bytes"] >= 1024**3:
                print(
                    json.dumps(
                        {
                            "copied": done,
                            "bytes": total,
                            "elapsed_seconds": round(time.monotonic() - started),
                            "last": row["destination"],
                        }
                    ),
                    flush=True,
                )
    summary = {
        "completed_files": done + len(existing),
        "new_copied_bytes": total,
        "errors": errors,
        "elapsed_seconds": round(time.monotonic() - started),
    }
    (AUDIT / "integration_copy_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary), flush=True)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

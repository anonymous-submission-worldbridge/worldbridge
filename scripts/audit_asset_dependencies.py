"""Audit external references in every inventoried Blender asset."""
from pathlib import Path
from urllib.parse import quote, unquote
import concurrent.futures
import json
import time
from blend_dependencies import inspect

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"
SOURCE = ROOT.parent / "LegacyWorld/infinigen"


def one(row):
    rel = unquote(row["source_relative_uri"])
    source = SOURCE / rel
    result = inspect(source)
    for item in result["dependencies"]:
        value = item.pop("path")
        item["path_uri"] = quote(value, safe="/+_.-<>")
    return {"source_relative_uri": row["source_relative_uri"], **result}


def main():
    rows = [
        x
        for x in json.loads((AUDIT / "integration_plan.json").read_text())["files"]
        if Path(unquote(x["source_relative_uri"])).suffix.startswith(".blend")
    ]
    journal = AUDIT / "blend_dependencies.jsonl"
    completed = (
        {
            json.loads(line)["source_relative_uri"]
            for line in journal.read_text().splitlines()
        }
        if journal.exists()
        else set()
    )
    rows = [row for row in rows if row["source_relative_uri"] not in completed]
    rows.sort(key=lambda row: row["bytes"])
    done = 0
    errors = []
    start = time.monotonic()
    with (AUDIT / "blend_dependencies.jsonl").open(
        "a"
    ) as out, concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(one, row): row for row in rows}
        for future in concurrent.futures.as_completed(futures):
            try:
                result = future.result()
            except Exception as e:
                result = {
                    "source_relative_uri": futures[future]["source_relative_uri"],
                    "error": str(e),
                }
                errors.append(result)
            out.write(json.dumps(result) + "\n")
            out.flush()
            done += 1
            if done % 25 == 0:
                print(
                    json.dumps(
                        {
                            "scanned": done,
                            "total": len(rows),
                            "errors": len(errors),
                            "seconds": round(time.monotonic() - start),
                        }
                    ),
                    flush=True,
                )
    (AUDIT / "dependency_scan_summary.json").write_text(
        json.dumps({"scanned": done, "errors": errors}, indent=2) + "\n"
    )
    print("Dependency scan complete:", done, "errors:", len(errors), flush=True)


if __name__ == "__main__":
    main()

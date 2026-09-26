"""Copy newly discovered model dependencies independently of the primary copy.

The explicit initial destination list prevents overlap with an already running
primary copier. Both append complete records to the same copy journal.
"""
from pathlib import Path
import json
from integrate_assets import copy_one

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "docs/assets"


def main():
    plan = json.loads((AUDIT / "integration_plan.json").read_text())
    primary = set(json.loads((AUDIT / "primary_copy_destinations.json").read_text()))
    journal = AUDIT / "integration_copies.jsonl"
    completed = {
        json.loads(line)["destination"] for line in journal.read_text().splitlines()
    }
    rows = {
        r["destination"]: r
        for r in plan["files"]
        if r["destination"] not in primary | completed
    }
    errors = []
    for row in sorted(rows.values(), key=lambda r: r["bytes"]):
        print("Copying dependency:", row["destination"], row["bytes"], flush=True)
        try:
            result = copy_one(row)
        except Exception as error:
            errors.append({"file": row["destination"], "error": str(error)})
            continue
        with journal.open("a") as out:
            out.write(json.dumps(result) + "\n")
        print("Verified dependency:", row["destination"], flush=True)
    result = {"files": len(rows), "errors": errors}
    (AUDIT / "additional_copy_summary.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())

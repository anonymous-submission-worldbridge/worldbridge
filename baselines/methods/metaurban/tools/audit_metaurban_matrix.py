#!/usr/bin/env python3
"""Read-only provenance and completion audit for the 100-run MetaUrban matrix."""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


BASELINES_ROOT = _BASELINE_PROJECT_ROOT / "baselines"
ADAPTER = BASELINES_ROOT / "methods/metaurban/adapter.py"
PROTOCOL = (
    BASELINES_ROOT / "methods/metaurban/protocol/generation/metaurban_protocol.yaml"
)
SPEC_FILE = BASELINES_ROOT / "protocol/generation/urban_specs.jsonl"
DATA_ROOT = BASELINES_ROOT / "data/table2"
DEFAULT_OUTPUT = BASELINES_ROOT / "results/metaurban/matrix_audit.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_specs(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def classify(run_dir: Path, adapter_sha: str, protocol_sha: str) -> tuple[str, str]:
    manifest_path = run_dir / "run_manifest.json"
    if not manifest_path.exists():
        return "not_started", "missing manifest"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception as error:
        return "infrastructure_failure", f"invalid manifest: {error}"
    if manifest.get("trial_mode") != "formal" or manifest.get("asset_mode") != "full":
        return "stale_or_nonformal", "run is not formal/full-assets"
    if (
        manifest.get("adapter_sha256") != adapter_sha
        or manifest.get("protocol_sha256") != protocol_sha
    ):
        return "stale_or_nonformal", "adapter/protocol hash mismatch"
    if (
        manifest.get("success")
        and manifest.get("validation", {}).get("valid")
        and (run_dir / "SUCCESS").exists()
    ):
        return "formal_success", ""
    if manifest.get("failure_reason") == "output_validation_failed":
        return "quality_failure", "frozen output validator failed"
    return "infrastructure_failure", str(
        manifest.get("failure_reason") or "unknown failure"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, default=DATA_ROOT)
    parser.add_argument("--spec-file", type=Path, default=SPEC_FILE)
    parser.add_argument("--json-output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    adapter_sha = sha256_file(ADAPTER)
    protocol_sha = sha256_file(PROTOCOL)
    rows = []
    for spec in load_specs(args.spec_file):
        for seed in range(4):
            run_dir = (
                args.data_root / "urban/metaurban" / spec["spec_id"] / f"seed_{seed}"
            )
            status, detail = classify(run_dir, adapter_sha, protocol_sha)
            rows.append(
                {
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "status": status,
                    "detail": detail,
                    "run_dir": str(run_dir),
                }
            )
    counts = Counter(row["status"] for row in rows)
    payload = {
        "method": "metaurban",
        "domain": "urban",
        "expected": 100,
        "adapter_sha256": adapter_sha,
        "protocol_sha256": protocol_sha,
        "counts": dict(sorted(counts.items())),
        "complete": counts.get("formal_success", 0) + counts.get("quality_failure", 0)
        == 100,
        "runs": rows,
    }
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.json_output.with_suffix(args.json_output.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(args.json_output)
    print(
        json.dumps(
            {key: payload[key] for key in ("expected", "counts", "complete")},
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Verify source coverage and the removal of generated model files."""
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/modeling"
MODEL_SUFFIXES = {
    ".blend",
    ".blend1",
    ".blend2",
    ".fbx",
    ".obj",
    ".glb",
    ".gltf",
    ".usd",
    ".usdc",
    ".usda",
    ".stl",
    ".ply",
}


def main():
    catalog = json.loads((AUDIT / "catalog.json").read_text())
    missing = [
        r["destination"]
        for r in catalog["files"]
        if not (ROOT / r["destination"]).is_file()
    ]
    hashes = []
    for manifest in [
        "added_sources.json",
        "relocated_sources.json",
        "reference_metadata.json",
    ]:
        for row in json.loads((AUDIT / manifest).read_text()):
            path = ROOT / row["destination"]
            expected = row.get("current_sha256", row.get("sha256"))
            if (
                not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected
            ):
                hashes.append(row["destination"])
    models = [
        str(p.relative_to(ROOT))
        for p in ROOT.rglob("*")
        if p.is_file()
        and (
            p.suffix.lower() in MODEL_SUFFIXES
            or re.search(r"\.blend\d*\.(integration_partial|rebase_partial)$", p.name)
        )
    ]
    compile_errors = []
    python_files = list(ROOT.rglob("*.py"))
    for path in python_files:
        try:
            compile(path.read_bytes(), str(path), "exec")
        except Exception as error:
            compile_errors.append(
                {"file": str(path.relative_to(ROOT)), "error": str(error)}
            )
    shell_errors = []
    added = json.loads((AUDIT / "added_sources.json").read_text())
    for row in added:
        path = ROOT / row["destination"]
        if path.suffix == ".sh":
            result = subprocess.run(
                ["bash", "-n", str(path)], capture_output=True, text=True
            )
            if result.returncode:
                shell_errors.append(
                    {"file": row["destination"], "error": result.stderr}
                )
    links = []
    for name in [
        "README.md",
        "assets/README.md",
        "assets/FAMILIES.md",
        "docs/modeling/README.md",
        "scripts/modeling_history/README.md",
    ]:
        path = ROOT / name
        for target in re.findall(r"\]\(([^)]+)\)", path.read_text()):
            if "://" in target or target.startswith("#"):
                continue
            if (
                not (path.parent / target.split("#")[0]).exists()
                and target != "verification.json"
            ):
                links.append({"file": name, "target": target})
    english = json.loads((AUDIT / "english_check.json").read_text())
    robot = json.loads((AUDIT / "robot_smoke.json").read_text())
    core = (AUDIT / "core_tests.txt").read_text()
    result = {
        "authored_source_paths": len(catalog["files"]),
        "family_groups": len(catalog["families"]),
        "missing_sources": missing,
        "source_hash_mismatches": hashes,
        "remaining_model_files": models,
        "python_files_compiled": len(python_files),
        "python_errors": compile_errors,
        "shell_errors": shell_errors,
        "broken_current_documentation_links": links,
        "english_check_passed": english["passed"],
        "robot_geometry_smoke_passed": robot["passed"],
        "core_tests_passed": "6 passed" in core and "failed" not in core,
        "scope_limit": "Source preservation and targeted validation; complete scene regeneration and all archived scripts were not executed.",
    }
    result["passed"] = (
        not any([missing, hashes, models, compile_errors, shell_errors, links])
        and english["passed"]
        and robot["passed"]
        and result["core_tests_passed"]
    )
    (AUDIT / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

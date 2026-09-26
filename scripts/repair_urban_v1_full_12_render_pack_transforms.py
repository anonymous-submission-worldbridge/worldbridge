#!/usr/bin/env python3
"""Reassert full-12 production placement transforms in derived render packs.

The first render-pack build was performed with Blender's dependency graph
disabled to avoid loading the whole city.  In that mode ``matrix_world`` is an
unevaluated identity matrix, while ``matrix_basis`` contains the serialized
transform.  The active pack builder now copies ``matrix_basis`` directly.
This one-time migration updates already-built dependency-only packs from the
authoritative layout formula used by ``generate_urban_v1_full_10.place`` and
records a hash-backed validation in their lineage file.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Matrix


ROOT = Path(__file__).resolve().parents[1]
REVISION = "urban_v1_full_12"
CITY = ROOT / "infinigen/outputs/outdoor_full_demo" / REVISION
LAYOUT_PATH = CITY / "layout_plan.json"
PACK_ROOT = CITY / "render_dependency_packs"
LINEAGE_PATH = PACK_ROOT / "render_pack_lineage.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def utc_now() -> str:
    return (
        datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    )


def production_basis(record: dict) -> Matrix:
    at = tuple(float(value) for value in record["location"])
    center = tuple(float(value) for value in record["source_center"])
    yaw = float(record["yaw_radians"])
    return (
        Matrix.Translation(at)
        @ Matrix.Rotation(yaw, 4, "Z")
        @ Matrix.Translation((-center[0], -center[1], 0.0))
    )


def matrix_values(matrix: Matrix) -> list[float]:
    return [
        round(float(matrix[row][column]), 6) for row in range(4) for column in range(4)
    ]


def matrices_match(left: Matrix, right: Matrix, tolerance: float = 1e-6) -> bool:
    return all(
        abs(float(left[row][column]) - float(right[row][column])) <= tolerance
        for row in range(4)
        for column in range(4)
    )


def main() -> None:
    layout = json.loads(LAYOUT_PATH.read_text(encoding="utf8"))
    by_id = {record["placement_id"]: record for record in layout["placements"]}
    lineage = json.loads(LINEAGE_PATH.read_text(encoding="utf8"))
    if lineage.get("status") != "PASS" or lineage.get("placement_count") != len(by_id):
        raise RuntimeError("Render-pack lineage is incomplete or stale")

    tokens = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    requested = tokens[0] if tokens else None
    if requested is not None and requested not in lineage["packs"]:
        raise RuntimeError(f"Unknown render-pack layer: {requested}")
    selected_layers = [requested] if requested else list(lineage["packs"])
    validation = dict(lineage.get("serialized_transform_packs", {}))
    for layer_key in selected_layers:
        pack_record = lineage["packs"][layer_key]
        pack = Path(pack_record["target"])
        if pack.parent.resolve() != PACK_ROOT.resolve() or not pack.is_file():
            raise RuntimeError(f"Invalid render-pack target: {pack}")
        if Path(bpy.data.filepath).resolve() != pack.resolve():
            bpy.ops.wm.open_mainfile(
                filepath=str(pack), load_ui=False, use_scripts=False
            )
        if bpy.context.scene.get("render_pack_layer_key") != layer_key:
            raise RuntimeError(f"Pack scene/layer mismatch: {layer_key}")

        roots = [obj for obj in bpy.context.scene.objects if obj.get("placement_id")]
        expected_count = int(pack_record["base_placement_count"]) + int(
            pack_record["asset_placement_count"]
        )
        if len(roots) != expected_count:
            raise RuntimeError(
                f"Pack root count mismatch for {layer_key}: {len(roots)} != {expected_count}"
            )
        seen = set()
        serialized = []
        for obj in roots:
            placement_id = str(obj["placement_id"])
            if placement_id in seen or placement_id not in by_id:
                raise RuntimeError(
                    f"Invalid placement ID in {layer_key}: {placement_id}"
                )
            seen.add(placement_id)
            if obj.parent is not None or obj.instance_type != "COLLECTION":
                raise RuntimeError(
                    f"Render root is not a parentless collection instance: {obj.name}"
                )
            expected = production_basis(by_id[placement_id])
            obj.matrix_basis = expected
            actual = matrix_values(obj.matrix_basis)
            wanted = matrix_values(expected)
            if not matrices_match(obj.matrix_basis, expected):
                raise RuntimeError(f"Transform serialization mismatch: {placement_id}")
            serialized.append([placement_id, wanted])

        temporary = PACK_ROOT / f".{layer_key}.transform_repair.blend"
        if temporary.exists():
            temporary.unlink()
        # Write only the derived pack Scene and its linked dependencies.  A
        # full ``save_as_mainfile`` may inspect unrelated loaded datablocks in
        # especially dense source files and is both slower and unnecessary.
        bpy.data.libraries.write(
            str(temporary),
            {bpy.context.scene},
            path_remap="ABSOLUTE",
            fake_user=True,
            compress=False,
        )
        if not temporary.is_file() or temporary.stat().st_size <= 0:
            raise RuntimeError(f"Failed to serialize repaired pack: {layer_key}")
        os.replace(temporary, pack)
        serialized.sort(key=lambda item: item[0])
        transform_hash = hashlib.sha256(
            json.dumps(serialized, separators=(",", ":"), ensure_ascii=False).encode(
                "utf8"
            )
        ).hexdigest()
        pack_record["bytes"] = pack.stat().st_size
        pack_record["sha256"] = sha256(pack)
        pack_record["serialized_transform_validation"] = "PASS"
        pack_record["serialized_transform_count"] = len(serialized)
        pack_record["serialized_transform_sha256"] = transform_hash
        validation[layer_key] = {
            "status": "PASS",
            "root_count": len(serialized),
            "transform_sha256": transform_hash,
        }
        print(
            f"FULL12_PACK_TRANSFORM_PASS layer={layer_key} roots={len(serialized)}",
            flush=True,
        )

        # Persist each independently validated layer.  The operational wrapper
        # launches one clean Blender process per pack so heavyweight linked
        # libraries cannot accumulate between layers.
        lineage["serialized_transform_packs"] = validation
        temporary_lineage = LINEAGE_PATH.with_suffix(".writing.json")
        temporary_lineage.write_text(
            json.dumps(lineage, indent=2, ensure_ascii=False), encoding="utf8"
        )
        os.replace(temporary_lineage, LINEAGE_PATH)

    all_valid = set(validation) == set(lineage["packs"]) and all(
        record.get("status") == "PASS" for record in validation.values()
    )
    lineage["serialized_transform_validation"] = "PASS" if all_valid else "IN_PROGRESS"
    lineage["serialized_transform_source"] = (
        "layout location/yaw/source_center via the production place() matrix formula; "
        "equivalent to parentless production matrix_basis"
    )
    lineage["serialized_transform_validation_utc"] = utc_now()
    lineage["serialized_transform_packs"] = validation
    temporary_lineage = LINEAGE_PATH.with_suffix(".writing.json")
    temporary_lineage.write_text(
        json.dumps(lineage, indent=2, ensure_ascii=False), encoding="utf8"
    )
    os.replace(temporary_lineage, LINEAGE_PATH)
    print(
        "FULL12_PACK_TRANSFORM_FINISH "
        f"status={lineage['serialized_transform_validation']} packs={len(validation)}",
        flush=True,
    )


if __name__ == "__main__":
    main()

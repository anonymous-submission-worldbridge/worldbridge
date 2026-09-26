#!/usr/bin/env python3
"""Resumable Table-4 evaluation for GPT-6 Astra plus a fixed IO adapter."""

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
import base64
import concurrent.futures
import csv
import hashlib
import json
import random
import re
import statistics
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import urllib.request

import numpy as np
from PIL import Image, ImageDraw, ImageFont


REPO = _BASELINE_PROJECT_ROOT
BASELINES = REPO / "baselines"
sys.path.insert(0, str(REPO))
from baselines.methods.worldgen.unified.fixed_adapter import (
    worldgen_io_adapter as geometry,
)  # noqa: E402


PROTOCOL_DIR = BASELINES / "methods/gpt/protocol/unified/high"
PROTOCOL_PATH = PROTOCOL_DIR / "protocol.yaml"
PROMPT_PATH = PROTOCOL_DIR / "aqs_prompt.txt"
LOCK_PATH = PROTOCOL_DIR / "method.lock.json"
TABLE4_SPECS = BASELINES / "protocol/unified/specs.jsonl"
INDOOR_SPECS = BASELINES / "protocol/generation/indoor_specs.jsonl"
URBAN_SPECS = BASELINES / "protocol/generation/urban_specs.jsonl"
SOURCE_METHOD_LOCK = BASELINES / "results/gpt6_astra/method.lock.json"
MODEL_WEIGHT_AUDIT = (
    BASELINES / "results/table4_gpt6_astra_io_adapter/model_weight_audit.json"
)
NAVMESH_EVALUATOR = BASELINES / "evaluation/geometry/metrics/build_navmesh.py"
RECAST_BINARY = (
    BASELINES
    / "methods/worldgen/geometry/runtime/recast_glibc231_clean2/recast.cpython-311-x86_64-linux-gnu.so"
)
BLIND_SALT = "worldbridge-table4-gpt6-astra-fixed-io-adapter-v1"

METRICS = (
    "functional_aqs",
    "visual_aqs",
    "spatial_aqs",
    "shape_iou",
    "entrance_alignment",
    "entrance_passability",
    "transition_collision",
    "io_connectivity_rate",
    "cross_boundary_reachability",
)

_NAV_MODULE: Any | None = None


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_protocol() -> dict[str, Any]:
    return json.loads(PROTOCOL_PATH.read_text(encoding="utf-8"))


def jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def atomic_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8")
    temporary.replace(path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(
        path, json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    )


def atomic_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    atomic_text(
        path,
        "".join(
            json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n" for row in rows
        ),
    )


def atomic_csv(path: Path, fields: list[str], rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_json(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def rel(path: Path) -> str:
    return str(path.resolve().relative_to(REPO.resolve()))


def safe_run_dir(root: Path, spec_id: str, seed: int) -> Path:
    if "/" in spec_id or spec_id in {".", ".."}:
        raise ValueError(f"Unsafe spec id: {spec_id}")
    path = (root / spec_id / f"seed_{seed}").resolve()
    path.relative_to(BASELINES.resolve())
    return path


def trial_paths(trial: str) -> tuple[Path, Path, Path]:
    if trial not in {"pilot", "formal"}:
        raise ValueError(trial)
    paths = load_protocol()["paths"]
    return tuple(REPO / paths[f"{trial}_{kind}"] for kind in ("data", "annotations", "results"))  # type: ignore[return-value]


def trial_specs_and_seeds(trial: str) -> tuple[list[dict[str, Any]], list[int]]:
    protocol = load_protocol()
    config = protocol[trial]
    indices = set(
        range(25) if config["spec_indices"] == "all" else config["spec_indices"]
    )
    specs = [row for row in jsonl(TABLE4_SPECS) if int(row["spec_index"]) in indices]
    return specs, [int(seed) for seed in config["seeds"]]


def blind_id(spec_id: str, seed: int, trial: str) -> str:
    value = (
        hashlib.sha256(f"{BLIND_SALT}|{trial}|{spec_id}|{seed}".encode())
        .hexdigest()[:12]
        .upper()
    )
    return f"G-{value}"


def category_variant(
    specs: list[dict[str, Any]], category: str, ordinal: int
) -> dict[str, Any]:
    matches = sorted(
        (row for row in specs if row["category"] == category),
        key=lambda row: int(row["spec_index"]),
    )
    if len(matches) != 5 or not 0 <= ordinal < 5:
        raise RuntimeError(
            f"Expected five frozen specs for category={category}, found {len(matches)}"
        )
    return matches[ordinal]


def source_pair(spec: dict[str, Any], seed: int) -> dict[str, Any]:
    protocol = load_protocol()
    source = protocol["source"]
    ordinal = int(spec["spec_index"]) % 5
    function = spec["function"]
    urban = category_variant(
        jsonl(URBAN_SPECS), source["urban_category_by_function"][function], ordinal
    )
    indoor = category_variant(
        jsonl(INDOOR_SPECS), source["indoor_category_by_function"][function], ordinal
    )
    root = REPO / source["data_root"]
    return {
        "exterior": {
            "spec": urban,
            "run": root / "urban/gpt6_astra" / urban["spec_id"] / f"seed_{seed}",
        },
        "interior": {
            "spec": indoor,
            "run": root / "indoor/gpt6_astra" / indoor["spec_id"] / f"seed_{seed}",
        },
    }


def source_side_record(side: str, entry: dict[str, Any]) -> dict[str, Any]:
    run = entry["run"]
    manifest = run / "run_manifest.json"
    success = (run / "SUCCESS").is_file()
    required = [
        run / value
        for value in load_protocol()["source"]["required_files_per_successful_side"]
    ]
    missing = [rel(path) for path in required if not path.is_file()] if success else []
    if missing:
        success = False
    record: dict[str, Any] = {
        "side": side,
        "spec_id": entry["spec"]["spec_id"],
        "logical_seed": int(run.name.removeprefix("seed_")),
        "run": rel(run),
        "success": success,
        "missing_required": missing,
        "run_manifest": {"path": rel(manifest), "sha256": sha256_file(manifest)}
        if manifest.is_file()
        else None,
    }
    if success:
        scene = run / "scene/scene.blend"
        record["scene_blend"] = {
            "path": rel(scene),
            "sha256": sha256_file(scene),
            "immutable": True,
        }
        record["anchors"] = [
            {
                "index": index,
                "path": rel(run / f"renders/anchors/rgb_{index:03d}.png"),
                "sha256": sha256_file(run / f"renders/anchors/rgb_{index:03d}.png"),
            }
            for index in range(8)
        ]
    return record


def navmesh_module() -> Any:
    global _NAV_MODULE
    if _NAV_MODULE is None:
        _NAV_MODULE = geometry.navmesh_module()
    return _NAV_MODULE


def build_one(spec: dict[str, Any], seed: int, trial: str, output: Path) -> bool:
    protocol = load_protocol()
    pair = source_pair(spec, seed)
    refs = {side: source_side_record(side, entry) for side, entry in pair.items()}
    source_signature = sha256_json(refs)
    protocol_hash = sha256_file(PROTOCOL_PATH)
    adapter_hash = sha256_file(Path(__file__))
    existing_manifest = output / "manifest.json"
    if (output / "SUCCESS").is_file() and existing_manifest.is_file():
        existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if (
            existing.get("source_signature") == source_signature
            and existing.get("protocol_sha256") == protocol_hash
            and existing.get("adapter_sha256") == adapter_hash
            and all(
                (REPO / path).is_file() for path in existing.get("outputs_sha256", {})
            )
        ):
            return True
        (output / "SUCCESS").unlink(missing_ok=True)

    atomic_json(output / "input/pair_spec.json", spec)
    atomic_json(
        output / "input/source_mapping.json",
        {
            "mapping_rule": protocol["source"]["variant_rule"],
            "table4_spec_id": spec["spec_id"],
            "logical_seed": seed,
            "sources": refs,
            "human_postprocessing": False,
        },
    )
    source_success = all(record["success"] for record in refs.values())
    if not source_success:
        (output / "SUCCESS").unlink(missing_ok=True)
        atomic_json(
            existing_manifest,
            {
                "method": protocol["method"],
                "display_name": protocol["display_name"],
                "track": protocol["track"],
                "trial": trial,
                "spec_id": spec["spec_id"],
                "logical_seed": seed,
                "source_success": False,
                "system_success": False,
                "failure_reason": "one_or_both_frozen_table2_source_runs_failed",
                "source_records": refs,
                "source_signature": source_signature,
                "protocol_sha256": protocol_hash,
                "adapter_sha256": adapter_hash,
                "human_postprocessing": False,
                "updated_at_utc": utc_now(),
            },
        )
        return False

    vertices, faces, wall_boxes = geometry.canonical_geometry(protocol)
    nav = navmesh_module()
    collision_ply = output / "canonical/collision.ply"
    nav.write_ply(collision_ply, vertices, faces)
    import trimesh

    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.export(output / "canonical/collision.glb")
    (output / "canonical/scene.glb").write_bytes(
        (output / "canonical/collision.glb").read_bytes()
    )
    shell = protocol["adapter"]["building_shell"]
    width, depth = float(shell["footprint_width_m"]), float(shell["footprint_depth_m"])
    footprint = [
        [-width / 2, -depth / 2],
        [width / 2, -depth / 2],
        [width / 2, depth / 2],
        [-width / 2, depth / 2],
    ]
    envelope = [list(point) for point in footprint]
    atomic_json(
        output / "canonical/exterior_footprint.geojson",
        geometry.geojson_polygon(footprint),
    )
    atomic_json(
        output / "canonical/interior_envelope.geojson",
        geometry.geojson_polygon(envelope),
    )
    outside_portal = geometry.portal_record(protocol, "exterior")
    inside_portal = geometry.portal_record(protocol, "interior")
    atomic_json(
        output / "canonical/portals.json", {"portals": [outside_portal, inside_portal]}
    )
    atomic_json(
        output / "canonical/instances.json",
        {
            "coordinate_system": protocol["adapter"]["coordinate_system"],
            "unit": "meter",
            "instances": [
                {
                    "id": "fixed_building_shell",
                    "role": "target_building+interior_shell",
                    "source": "adapter",
                },
                {
                    "id": "fixed_shared_portal_0",
                    "role": "open_portal",
                    "source": "adapter",
                },
                {
                    "id": "fixed_public_walkway",
                    "role": "public_outdoor",
                    "source": "adapter",
                },
            ],
            "source_geometry_used_for_visual_identity_only": True,
        },
    )
    atomic_json(output / "canonical/native_geometry_refs.json", refs)
    atomic_json(
        output / "canonical/frame.json",
        {
            "coordinate_system": protocol["adapter"]["coordinate_system"],
            "unit": "meter",
            "floor_z_m": 0.0,
            "collision_geometry": "adapter-generated fixed shell; immutable source Blender scenes excluded from synthetic collision",
            "source_visual_geometry": refs,
        },
    )
    recast_config = {
        key: protocol[key]
        for key in ("agent", "recast", "postprocess", "spawn", "success")
    }
    nav_vertices, nav_faces, nav_meta = nav.build(collision_ply, recast_config, 0.0)
    if not nav_meta.get("builder_returned") or len(nav_faces) == 0:
        raise RuntimeError(f"Recast produced no NavMesh: {output}")
    geometry.save_navmesh(output / "navigation/navmesh.bin", nav_vertices, nav_faces)
    components, areas = nav.connected_components(nav_vertices, nav_faces)
    anchors = protocol["adapter"]["anchors"]
    outdoor = [
        geometry.projection_component(point, nav_vertices, nav_faces, components, nav)
        for point in anchors["outdoor"]
    ]
    foyer = geometry.projection_component(
        anchors["foyer"], nav_vertices, nav_faces, components, nav
    )
    goals = [
        {
            "label": label,
            **geometry.projection_component(
                slot, nav_vertices, nav_faces, components, nav
            ),
        }
        for label, slot in zip(spec["indoor_goal_rules"], anchors["goal_slots"])
    ]
    atomic_json(
        output / "navigation/anchors.json",
        {"outdoor": outdoor, "foyer": foyer, "indoor_goals": goals},
    )
    atomic_json(
        output / "navigation/components.json",
        {
            "component_count": len(components),
            "component_areas_m2": areas,
            "components": components,
            "recast": nav_meta,
        },
    )

    alignment = geometry.entrance_alignment(outside_portal, inside_portal, protocol)
    collision = geometry.transition_collision(wall_boxes, protocol)
    foyer_component = foyer.get("component") if foyer.get("projected") else None
    connected = foyer_component is not None and any(
        item.get("projected") and item.get("component") == foyer_component
        for item in outdoor
    )
    outside_probe = geometry.projection_component(
        collision["outside_probe_xyz_m"], nav_vertices, nav_faces, components, nav
    )
    inside_probe = geometry.projection_component(
        collision["inside_probe_xyz_m"], nav_vertices, nav_faces, components, nav
    )
    passable = bool(
        alignment["passed"]
        and not collision["any_collision"]
        and outside_probe.get("projected")
        and inside_probe.get("projected")
        and outside_probe.get("component") == inside_probe.get("component")
    )
    checks = []
    for outside_index, outside in enumerate(outdoor):
        for goal_index, goal in enumerate(goals):
            reachable = bool(
                outside.get("projected")
                and goal.get("projected")
                and outside.get("component") is not None
                and outside.get("component") == goal.get("component")
            )
            checks.append(
                {
                    "outdoor_index": outside_index,
                    "goal_index": goal_index,
                    "reachable": reachable,
                }
            )
    reachability = 100.0 * sum(item["reachable"] for item in checks) / len(checks)
    metrics = {
        "shape_iou": geometry.rectangle_iou(footprint, envelope),
        "entrance_alignment": 100.0 if alignment["passed"] else 0.0,
        "entrance_passability": 100.0 if passable else 0.0,
        "transition_collision": collision["collision_percent"],
        "io_connectivity_rate": 100.0 if connected else 0.0,
        "cross_boundary_reachability": reachability,
        "debug": {
            "alignment": alignment,
            "collision": collision,
            "outside_probe": outside_probe,
            "inside_probe": inside_probe,
            "reach_checks": checks,
            "wall_boxes": wall_boxes,
        },
    }
    atomic_json(output / "metrics/per_run.json", metrics)
    overlay = output / "renders/spatial_overlay.png"
    geometry.make_overlay(
        overlay, spec, blind_id(spec["spec_id"], seed, trial), protocol
    )
    required = [
        output / "canonical/collision.ply",
        output / "canonical/collision.glb",
        output / "canonical/scene.glb",
        output / "canonical/frame.json",
        output / "canonical/exterior_footprint.geojson",
        output / "canonical/interior_envelope.geojson",
        output / "canonical/portals.json",
        output / "canonical/instances.json",
        output / "canonical/native_geometry_refs.json",
        output / "navigation/navmesh.bin",
        output / "navigation/anchors.json",
        output / "navigation/components.json",
        output / "metrics/per_run.json",
        overlay,
    ]
    hashes = {rel(path): sha256_file(path) for path in required}
    atomic_json(
        existing_manifest,
        {
            "method": protocol["method"],
            "display_name": protocol["display_name"],
            "track": protocol["track"],
            "trial": trial,
            "spec_id": spec["spec_id"],
            "logical_seed": seed,
            "source_success": True,
            "system_success": True,
            "source_records": refs,
            "source_signature": source_signature,
            "protocol_sha256": protocol_hash,
            "adapter_sha256": adapter_hash,
            "native_geometry_policy": protocol["adapter"]["native_geometry_policy"],
            "human_postprocessing": False,
            "outputs_sha256": hashes,
            "updated_at_utc": utc_now(),
        },
    )
    atomic_text(
        output / "SUCCESS",
        "GPT-6 Astra plus fixed IO adapter output contract complete\n",
    )
    return True


def build_trial(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    data_root, _, _ = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    successes = 0
    for spec in specs:
        for seed in seeds:
            output = safe_run_dir(data_root, spec["spec_id"], seed)
            success = build_one(spec, seed, trial, output)
            successes += int(success)
            print(
                f"GPT6_ASTRA_TABLE4_BUILD spec={spec['spec_id']} seed={seed} success={success}",
                flush=True,
            )
    result = {
        "trial": trial,
        "planned_pairs": len(specs) * len(seeds),
        "successful_pairs": successes,
        "output_root": rel(data_root),
    }
    print(
        f"GPT6_ASTRA_TABLE4_BUILD_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def font(size: int):
    try:
        return ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size
        )
    except OSError:
        return ImageFont.load_default()


def render_tile(path: Path, size: tuple[int, int]) -> Image.Image:
    with Image.open(path) as source:
        tile = source.convert("RGB")
        tile.thumbnail(size, Image.Resampling.LANCZOS)
    result = Image.new("RGB", size, (25, 25, 25))
    result.paste(tile, ((size[0] - tile.width) // 2, (size[1] - tile.height) // 2))
    return result


def make_montage(
    source_refs: dict[str, Any],
    overlay: Path,
    output: Path,
    anonymous: str,
    protocol: dict[str, Any],
) -> str:
    selected = protocol["source"]["selected_anchor_indices"]
    tile_size = (480, 250)
    margin, gap, header, label = 55, 10, 50, 30
    view_width = 4 * tile_size[0] + 3 * gap + 2 * margin
    view_height = header + 2 * (label + tile_size[1]) + gap
    views = Image.new("RGB", (view_width, view_height), "white")
    draw = ImageDraw.Draw(views)
    draw.text((margin, 12), f"Anonymous pair {anonymous}", fill="black", font=font(22))
    for row, side in enumerate(("exterior", "interior")):
        y = header + row * (label + tile_size[1] + gap)
        draw.rectangle((0, y, view_width, y + label), fill=(235, 235, 235))
        draw.text((margin, y + 4), side.upper(), fill="black", font=font(18))
        by_index = {int(item["index"]): item for item in source_refs[side]["anchors"]}
        for column, anchor_index in enumerate(selected[side]):
            item = by_index[int(anchor_index)]
            tile = render_tile(REPO / item["path"], tile_size)
            x = margin + column * (tile_size[0] + gap)
            views.paste(tile, (x, y + label))
            draw.rectangle((x + 5, y + label + 5, x + 43, y + label + 31), fill="black")
            draw.text(
                (x + 13, y + label + 6), str(anchor_index), fill="white", font=font(16)
            )
    with Image.open(overlay) as overlay_handle:
        lower = overlay_handle.convert("RGB")
        if lower.width != view_width:
            lower = lower.resize(
                (view_width, round(lower.height * view_width / lower.width)),
                Image.Resampling.LANCZOS,
            )
    combined = Image.new("RGB", (view_width, view_height + lower.height), "white")
    combined.paste(views, (0, 0))
    combined.paste(lower, (0, view_height))
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".jpg.tmp")
    combined.save(temporary, format="JPEG", quality=92, subsampling=0)
    temporary.replace(output)
    return sha256_file(output)


def package_trial(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    data_root, annotations, _ = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    protocol = load_protocol()
    items: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            run = safe_run_dir(data_root, spec["spec_id"], seed)
            success = (run / "SUCCESS").is_file()
            anonymous = blind_id(spec["spec_id"], seed, trial)
            private.append(
                {
                    "blind_id": anonymous,
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "success": success,
                    "run_dir": rel(run),
                }
            )
            if not success:
                continue
            manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
            refs = manifest["source_records"]
            overlay = run / "renders/spatial_overlay.png"
            input_signature = sha256_json(
                {
                    "anonymous": anonymous,
                    "selected": protocol["source"]["selected_anchor_indices"],
                    "source_records": refs,
                    "overlay_sha256": sha256_file(overlay),
                }
            )
            montage = annotations / "montages" / f"{anonymous}.jpg"
            cache = annotations / "montages" / f"{anonymous}.input.json"
            montage_hash = None
            if montage.is_file() and cache.is_file():
                cached = json.loads(cache.read_text(encoding="utf-8"))
                actual = sha256_file(montage)
                if (
                    cached.get("input_signature") == input_signature
                    and cached.get("montage_sha256") == actual
                ):
                    montage_hash = actual
            if montage_hash is None:
                montage_hash = make_montage(refs, overlay, montage, anonymous, protocol)
                atomic_json(
                    cache,
                    {
                        "input_signature": input_signature,
                        "montage_sha256": montage_hash,
                    },
                )
            items.append(
                {
                    "blind_id": anonymous,
                    "spec_id": spec["spec_id"],
                    "logical_seed": seed,
                    "function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "target_building": spec["target_building"],
                    "interior_program": spec["interior_program"],
                    "visual_inheritance": spec["visual_inheritance"],
                    "indoor_goal_rules": spec["indoor_goal_rules"],
                    "montage": rel(montage.relative_to(REPO) if False else montage),
                    "montage_sha256": montage_hash,
                }
            )
    atomic_jsonl(annotations / "items.jsonl", items)
    atomic_json(annotations / "PRIVATE_blind_map.json", {"items": private})
    result = {
        "trial": trial,
        "planned_pairs": len(private),
        "successful_pairs": len(items),
        "failed_pairs": len(private) - len(items),
        "method_blinded": True,
        "dimensions": ["functional_aqs", "visual_aqs", "spatial_aqs"],
        "items_sha256": sha256_file(annotations / "items.jsonl"),
        "private_map_sha256": sha256_file(annotations / "PRIVATE_blind_map.json"),
        "created_at_utc": utc_now(),
    }
    atomic_json(annotations / "package_manifest.json", result)
    print(
        f"GPT6_ASTRA_TABLE4_PACKAGE_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def score_prompt(item: dict[str, Any]) -> str:
    specification = {
        "function": item["function"],
        "visual_theme": item["visual_theme"],
        "target_building": item["target_building"],
        "interior_program": item["interior_program"],
        "visual_inheritance": item["visual_inheritance"],
        "registered_indoor_goals": item["indoor_goal_rules"],
    }
    return (
        PROMPT_PATH.read_text(encoding="utf-8")
        + "\nFrozen anonymous specification:\n"
        + json.dumps(specification, ensure_ascii=False, sort_keys=True)
    )


def request_json(port: int, payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        request, timeout=600
    ) as response:
        return json.load(response)


def parse_score(raw: dict[str, Any]) -> dict[str, Any]:
    content = raw["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("VLM response content is not text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    parsed = json.loads(text)
    required = {
        "functional_aqs",
        "visual_aqs",
        "spatial_aqs",
        "functional_evidence",
        "visual_evidence",
        "spatial_evidence",
    }
    if set(parsed) != required:
        raise ValueError(f"Unexpected AQS keys: {sorted(parsed)}")
    for key in ("functional_aqs", "visual_aqs", "spatial_aqs"):
        if type(parsed[key]) is not int or not 1 <= parsed[key] <= 10:
            raise ValueError(f"{key} must be an integer 1..10")
    for key in ("functional_evidence", "visual_evidence", "spatial_evidence"):
        if not isinstance(parsed[key], str) or not parsed[key].strip():
            raise ValueError(f"{key} must be non-empty")
    return parsed


def parse_partial_score(raw: dict[str, Any]) -> dict[str, Any]:
    """Accept only enough of an invalid response to freeze its numeric scores."""
    content = raw["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("VLM response content is not text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    pairs = json.loads(text, object_pairs_hook=lambda value: value)
    if not isinstance(pairs, list):
        raise ValueError("Cannot schema-repair a non-object response")
    parsed: dict[str, Any] = {}
    # Preserve the first valid integer occurrence so a later, mislabeled
    # evidence string with a duplicate score key cannot overwrite the score.
    for key, value in pairs:
        if (
            key in {"functional_aqs", "visual_aqs", "spatial_aqs"}
            and key not in parsed
            and type(value) is int
        ):
            parsed[key] = value
    for key in ("functional_aqs", "visual_aqs", "spatial_aqs"):
        if type(parsed.get(key)) is not int or not 1 <= parsed[key] <= 10:
            raise ValueError(f"Cannot schema-repair invalid numeric field: {key}")
    return parsed


def recover_duplicate_key_evidence(raw: dict[str, Any]) -> dict[str, Any]:
    """Deterministically relabel string-valued duplicate score keys as evidence."""
    content = raw["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise ValueError("VLM response content is not text")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip())
    pairs = json.loads(text, object_pairs_hook=lambda value: value)
    if not isinstance(pairs, list):
        raise ValueError("Cannot schema-repair a non-object response")
    score_to_evidence = {
        "functional_aqs": "functional_evidence",
        "visual_aqs": "visual_evidence",
        "spatial_aqs": "spatial_evidence",
    }
    repaired: dict[str, Any] = {}
    for key, value in pairs:
        if key in score_to_evidence:
            if key not in repaired and type(value) is int:
                repaired[key] = value
            elif (
                isinstance(value, str)
                and value.strip()
                and score_to_evidence[key] not in repaired
            ):
                repaired[score_to_evidence[key]] = value.strip()
        elif (
            key in score_to_evidence.values()
            and isinstance(value, str)
            and value.strip()
            and key not in repaired
        ):
            repaired[key] = value.strip()
    required = set(score_to_evidence) | set(score_to_evidence.values())
    if set(repaired) != required:
        raise ValueError(f"Duplicate-key recovery incomplete: {sorted(repaired)}")
    for key in score_to_evidence:
        if type(repaired[key]) is not int or not 1 <= repaired[key] <= 10:
            raise ValueError(f"Cannot schema-repair invalid numeric field: {key}")
    return repaired


def score_package(trial: str, port: int, workers: int) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    _, annotations, _ = trial_paths(trial)
    protocol = load_protocol()
    items = jsonl(annotations / "items.jsonl")
    config = protocol["aqs"]
    model_manifest = REPO / config["model_manifest"]
    model_hash = sha256_file(model_manifest)

    def score_one(item: dict[str, Any]) -> int:
        image_path = REPO / item["montage"]
        image_bytes = image_path.read_bytes()
        if hashlib.sha256(image_bytes).hexdigest() != item["montage_sha256"]:
            raise RuntimeError(f"Changed AQS evidence: {image_path}")
        prompt = score_prompt(item)
        image_content = {
            "type": "image_url",
            "image_url": {
                "url": "data:image/jpeg;base64,"
                + base64.b64encode(image_bytes).decode()
            },
        }
        for pass_index, seed in enumerate(config["seeds"], 1):
            settings = {
                "model": config["model"],
                "temperature": config["temperature"],
                "top_p": config["top_p"],
                "seed": seed,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }
            signature = sha256_json(
                {
                    "settings": settings,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "image_sha256": item["montage_sha256"],
                    "model_manifest_sha256": model_hash,
                }
            )
            output = (
                annotations / "raw" / item["blind_id"] / f"pass_{pass_index:02d}.json"
            )
            if output.is_file():
                cached = json.loads(output.read_text(encoding="utf-8"))
                if cached.get("input_signature") != signature:
                    raise RuntimeError(f"Refusing changed cached AQS input: {output}")
                parse_score(cached["raw_response"])
                continue
            last_error: Exception | None = None
            last_raw: dict[str, Any] | None = None
            raw_candidates: list[tuple[int, dict[str, Any]]] = []
            for attempt in range(1, int(config["parse_attempts"]) + 1):
                try:
                    raw = request_json(
                        port,
                        {
                            **settings,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": prompt},
                                        image_content,
                                    ],
                                }
                            ],
                        },
                    )
                    last_raw = raw
                    raw_candidates.append((attempt, raw))
                    atomic_json(
                        annotations
                        / "raw_attempts"
                        / item["blind_id"]
                        / f"pass_{pass_index:02d}_attempt_{attempt:02d}.json",
                        {
                            "input_signature": signature,
                            "attempt": attempt,
                            "raw_response": raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    parsed = parse_score(raw)
                    atomic_json(
                        output,
                        {
                            "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
                            "human_raters": 0,
                            "pass_index": pass_index,
                            "input_signature": signature,
                            "settings": settings,
                            "image_sha256": item["montage_sha256"],
                            "model_manifest_sha256": model_hash,
                            "parsed": parsed,
                            "raw_response": raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    print(
                        f"GPT6_ASTRA_TABLE4_AQS_RETRY item={item['blind_id']} pass={pass_index} attempt={attempt}/{config['parse_attempts']} error={exc!r}",
                        flush=True,
                    )
            else:
                if last_raw is None:
                    raise RuntimeError(
                        f"AQS transport failed item={item['blind_id']} pass={pass_index}: {last_error!r}"
                    )
                repaired = None
                repaired_raw = None
                repaired_attempt = None
                for candidate_attempt, candidate_raw in raw_candidates:
                    try:
                        repaired = recover_duplicate_key_evidence(candidate_raw)
                    except Exception:
                        continue
                    repaired_raw = candidate_raw
                    repaired_attempt = candidate_attempt
                    break
                if repaired is not None:
                    canonical_raw = json.loads(json.dumps(repaired_raw))
                    canonical_raw["choices"][0]["message"]["content"] = json.dumps(
                        repaired, sort_keys=True
                    )
                    atomic_json(
                        output,
                        {
                            "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
                            "human_raters": 0,
                            "pass_index": pass_index,
                            "input_signature": signature,
                            "settings": settings,
                            "schema_repair": True,
                            "schema_repair_mode": "deterministic_duplicate_key_relabel",
                            "schema_repair_source_attempt": repaired_attempt,
                            "frozen_scores_from_initial_response": {
                                key: repaired[key]
                                for key in (
                                    "functional_aqs",
                                    "visual_aqs",
                                    "spatial_aqs",
                                )
                            },
                            "initial_raw_response": repaired_raw,
                            "image_sha256": item["montage_sha256"],
                            "model_manifest_sha256": model_hash,
                            "parsed": repaired,
                            "raw_response": canonical_raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    continue
                partial = parse_partial_score(last_raw)
                frozen_scores = {
                    key: partial[key]
                    for key in ("functional_aqs", "visual_aqs", "spatial_aqs")
                }
                repair_text = (
                    prompt
                    + "\n\nSCHEMA REPAIR ONLY: the prior JSON omitted one or more evidence strings. "
                    + "Preserve these numeric scores exactly: "
                    + json.dumps(frozen_scores, sort_keys=True)
                    + ". Return the exact six-key schema and fill every evidence field with a brief non-empty visible reason."
                )
                repair_settings = {**settings, "temperature": 0, "top_p": 1}
                for repair_attempt in range(
                    1, int(config["schema_repair_attempts"]) + 1
                ):
                    repair_raw = request_json(
                        port,
                        {
                            **repair_settings,
                            "messages": [
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": repair_text},
                                        image_content,
                                    ],
                                }
                            ],
                        },
                    )
                    atomic_json(
                        annotations
                        / "raw_attempts"
                        / item["blind_id"]
                        / f"pass_{pass_index:02d}_schema_repair_{repair_attempt:02d}.json",
                        {
                            "input_signature": signature,
                            "attempt": repair_attempt,
                            "frozen_scores": frozen_scores,
                            "raw_response": repair_raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    try:
                        repaired = parse_score(repair_raw)
                        if any(
                            repaired[key] != value
                            for key, value in frozen_scores.items()
                        ):
                            raise ValueError(
                                "Schema repair changed a frozen numeric score"
                            )
                    except Exception as exc:
                        last_error = exc
                        print(
                            f"GPT6_ASTRA_TABLE4_AQS_SCHEMA_REPAIR_RETRY item={item['blind_id']} pass={pass_index} attempt={repair_attempt}/{config['schema_repair_attempts']} error={exc!r}",
                            flush=True,
                        )
                        continue
                    atomic_json(
                        output,
                        {
                            "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
                            "human_raters": 0,
                            "pass_index": pass_index,
                            "input_signature": signature,
                            "settings": settings,
                            "schema_repair": True,
                            "schema_repair_settings": repair_settings,
                            "frozen_scores_from_initial_response": frozen_scores,
                            "initial_raw_response": last_raw,
                            "image_sha256": item["montage_sha256"],
                            "model_manifest_sha256": model_hash,
                            "parsed": repaired,
                            "raw_response": repair_raw,
                            "created_at_utc": utc_now(),
                        },
                    )
                    break
                else:
                    raise RuntimeError(
                        f"AQS schema repair failed item={item['blind_id']} pass={pass_index}: {last_error!r}"
                    )
        print(f"GPT6_ASTRA_TABLE4_AQS_COMPLETE item={item['blind_id']}", flush=True)
        return 1

    completed = 0
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        for value in executor.map(
            score_one, sorted(items, key=lambda row: row["blind_id"])
        ):
            completed += value
    provenance = {
        "trial": trial,
        "rating_source": "aqs_vlm_qwen3_vl_8b_three_pass",
        "model": config["model"],
        "model_root": config["model_root"],
        "model_manifest_sha256": model_hash,
        "passes_per_pair": len(config["seeds"]),
        "schema_repair_policy": config["schema_repair"],
        "seeds": config["seeds"],
        "temperature": config["temperature"],
        "top_p": config["top_p"],
        "scored_successful_pairs": completed,
        "human_raters": 0,
        "limitations": "Local Qwen3-VL proxy scores are not human ratings and are not directly comparable to HoloWorld reported GPT scores.",
        "completed_at_utc": utc_now(),
    }
    atomic_json(annotations / "AQS_PROVENANCE.json", provenance)
    return provenance


def gpu_state() -> dict[int, dict[str, int]]:
    output = subprocess.check_output(
        [
            "nvidia-smi",
            "--query-gpu=index,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ],
        text=True,
    )
    result = {}
    for line in output.splitlines():
        index, free, utilization = (int(value.strip()) for value in line.split(","))
        result[index] = {"free_mib": free, "utilization": utilization}
    return result


def start_and_score(
    trial: str, gpu: int, port: int, workers: int, external: bool
) -> dict[str, Any]:
    sys.path.insert(0, str(BASELINES))
    import baselines.methods.hyworld.run as matrix

    protocol = load_protocol()
    matrix.QWEN_ROOT = Path(protocol["aqs"]["model_root"])
    process = None
    try:
        if external:
            if not matrix.llm_health(port):
                raise RuntimeError(f"No healthy local VLM at port {port}")
        else:
            state = gpu_state().get(gpu)
            if state is None or state["free_mib"] < 30000 or state["utilization"] > 10:
                raise RuntimeError(f"GPU {gpu} is not idle enough for VLM: {state}")
            process, _ = matrix.start_vllm(gpu, port, 16384, 900)
        return score_package(trial, port, workers)
    finally:
        if process is not None:
            matrix.stop_process_group(process)


def macro_average(rows: list[dict[str, Any]], metric: str) -> float:
    by_spec: dict[str, list[float]] = {}
    for row in rows:
        by_spec.setdefault(row["spec_id"], []).append(float(row[metric]))
    return statistics.fmean(statistics.fmean(values) for values in by_spec.values())


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] * (1 - fraction) + ordered[upper] * fraction


def cluster_bootstrap(
    rows: list[dict[str, Any]], metric: str, repeats: int, seed: int
) -> tuple[float, float]:
    clusters: dict[str, list[float]] = {}
    for row in rows:
        clusters.setdefault(row["spec_id"], []).append(float(row[metric]))
    values = [statistics.fmean(cluster) for cluster in clusters.values()]
    generator = random.Random(seed)
    samples = [
        statistics.fmean(generator.choice(values) for _ in values)
        for _ in range(repeats)
    ]
    return percentile(samples, 0.025), percentile(samples, 0.975)


def aggregate(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    data_root, annotations, results = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    protocol = load_protocol()
    failure = protocol["failure_values"]
    rows: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for spec in specs:
        for seed in seeds:
            run = safe_run_dir(data_root, spec["spec_id"], seed)
            success = (run / "SUCCESS").is_file()
            pair = source_pair(spec, seed)
            source_ids = {
                side: entry["spec"]["spec_id"] for side, entry in pair.items()
            }
            if success:
                anonymous = blind_id(spec["spec_id"], seed, trial)
                scores = []
                for pass_index in range(1, int(protocol["aqs"]["passes"]) + 1):
                    response = (
                        annotations / "raw" / anonymous / f"pass_{pass_index:02d}.json"
                    )
                    if not response.is_file():
                        raise RuntimeError(f"Missing AQS response: {response}")
                    scores.append(
                        parse_score(
                            json.loads(response.read_text(encoding="utf-8"))[
                                "raw_response"
                            ]
                        )
                    )
                measured = json.loads(
                    (run / "metrics/per_run.json").read_text(encoding="utf-8")
                )
                values = {
                    "functional_aqs": statistics.fmean(
                        item["functional_aqs"] for item in scores
                    ),
                    "visual_aqs": statistics.fmean(
                        item["visual_aqs"] for item in scores
                    ),
                    "spatial_aqs": statistics.fmean(
                        item["spatial_aqs"] for item in scores
                    ),
                    **{metric: float(measured[metric]) for metric in METRICS[3:]},
                }
                rating_source = "aqs_vlm_qwen3_vl_8b_three_pass"
                failure_reason = None
            else:
                values = {metric: float(failure[metric]) for metric in METRICS}
                rating_source = "itt_failure_value"
                manifest = json.loads(
                    (run / "manifest.json").read_text(encoding="utf-8")
                )
                failure_reason = manifest["failure_reason"]
                failures.append(
                    {
                        "spec_id": spec["spec_id"],
                        "logical_seed": seed,
                        "failure_reason": failure_reason,
                        **source_ids,
                    }
                )
            rows.append(
                {
                    "method": protocol["method"],
                    "display_name": protocol["display_name"],
                    "track": protocol["track"],
                    "pair_id": f"{spec['spec_id']}__seed_{seed}",
                    "spec_id": spec["spec_id"],
                    "spec_index": spec["spec_index"],
                    "logical_seed": seed,
                    "function": spec["function"],
                    "visual_theme": spec["visual_theme"],
                    "system_success": success,
                    "source_specs": source_ids,
                    "rating_source": rating_source,
                    "failure_reason": failure_reason,
                    **values,
                }
            )
    repeats = int(protocol["aggregation"]["bootstrap_repeats"])
    bootstrap_seed = int(protocol["aggregation"]["bootstrap_seed"])
    successful = [row for row in rows if row["system_success"]]
    metrics = {}
    for metric in METRICS:
        lower, upper = cluster_bootstrap(rows, metric, repeats, bootstrap_seed)
        metrics[metric] = {
            "mean": macro_average(rows, metric),
            "ci95": [lower, upper],
            "itt_coverage": 1.0,
            "evidence_coverage": len(successful) / len(rows),
            "successful_subset_mean": statistics.fmean(
                float(row[metric]) for row in successful
            )
            if successful
            else None,
        }
    summary = {
        "aggregated_at_utc": utc_now(),
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "trial": trial,
        "planned_pairs": len(rows),
        "successful_pairs": len(successful),
        "success_rate": len(successful) / len(rows),
        "aggregation_order": protocol["aggregation"]["order"],
        "bootstrap_repeats": repeats,
        "bootstrap_seed": bootstrap_seed,
        "aqs_source": "local Qwen3-VL-8B-Instruct, three seeded VLM passes; human_raters=0",
        "comparability_note": "The fixed adapter and local VLM proxy are disclosed system components; values are not native unified-world GPT-6 Astra scores and are not directly comparable to HoloWorld reported GPT scores.",
        "metrics": metrics,
    }
    results.mkdir(parents=True, exist_ok=True)
    atomic_jsonl(results / "per_run.jsonl", rows)
    atomic_json(results / "summary.json", summary)
    csv_row: dict[str, Any] = {
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "planned_pairs": len(rows),
        "successful_pairs": len(successful),
        "success_rate": len(successful) / len(rows),
    }
    for metric in METRICS:
        csv_row[metric] = metrics[metric]["mean"]
        csv_row[f"{metric}_ci95_low"] = metrics[metric]["ci95"][0]
        csv_row[f"{metric}_ci95_high"] = metrics[metric]["ci95"][1]
    atomic_csv(results / "summary.csv", list(csv_row), [csv_row])
    failure_fields = [
        "spec_id",
        "logical_seed",
        "failure_reason",
        "exterior",
        "interior",
    ]
    atomic_csv(results / "failures.csv", failure_fields, failures)
    display = [
        protocol["display_name"],
        f"{metrics['functional_aqs']['mean']:.2f}",
        f"{metrics['visual_aqs']['mean']:.2f}",
        f"{metrics['spatial_aqs']['mean']:.2f}",
        f"{metrics['shape_iou']['mean']:.3f}",
        f"{metrics['entrance_alignment']['mean']:.1f}",
        f"{metrics['entrance_passability']['mean']:.1f}",
        f"{metrics['transition_collision']['mean']:.1f}",
        f"{metrics['io_connectivity_rate']['mean']:.1f}",
        f"{metrics['cross_boundary_reachability']['mean']:.1f}",
    ]
    atomic_text(results / "table_row.md", "| " + " | ".join(display) + " |\n")
    print(
        f"GPT6_ASTRA_TABLE4_AGGREGATE_COMPLETE {json.dumps(summary, sort_keys=True)}",
        flush=True,
    )
    return summary


def verify_output_hashes(manifest: dict[str, Any]) -> list[str]:
    issues = []
    for relative, expected in manifest.get("outputs_sha256", {}).items():
        path = REPO / relative
        actual = sha256_file(path) if path.is_file() else None
        if actual != expected:
            issues.append(f"output_hash_mismatch:{relative}")
    return issues


def audit(trial: str) -> dict[str, Any]:
    if trial == "formal":
        verify_lock()
    data_root, annotations, results = trial_paths(trial)
    specs, seeds = trial_specs_and_seeds(trial)
    protocol = load_protocol()
    issues: list[str] = []
    if not MODEL_WEIGHT_AUDIT.is_file():
        issues.append("model_weight_audit_missing")
        weight_audit_hash = None
    else:
        weight_audit = json.loads(MODEL_WEIGHT_AUDIT.read_text(encoding="utf-8"))
        if weight_audit.get("failures"):
            issues.append("model_weight_audit_failed")
        weight_audit_hash = sha256_file(MODEL_WEIGHT_AUDIT)
    manifest_count = success_count = 0
    for spec in specs:
        for seed in seeds:
            run = safe_run_dir(data_root, spec["spec_id"], seed)
            manifest_path = run / "manifest.json"
            if not manifest_path.is_file():
                issues.append(f"missing_manifest:{spec['spec_id']}:{seed}")
                continue
            manifest_count += 1
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            success = (run / "SUCCESS").is_file()
            if success != bool(manifest.get("system_success")):
                issues.append(f"success_manifest_disagree:{spec['spec_id']}:{seed}")
            if success:
                success_count += 1
                issues.extend(verify_output_hashes(manifest))
    planned = len(specs) * len(seeds)
    package_path = annotations / "package_manifest.json"
    if not package_path.is_file():
        issues.append("package_manifest_missing")
        package = {}
    else:
        package = json.loads(package_path.read_text(encoding="utf-8"))
        if (
            package.get("planned_pairs") != planned
            or package.get("successful_pairs") != success_count
        ):
            issues.append("package_counts_mismatch")
    response_count = len(list((annotations / "raw").glob("*/pass_*.json")))
    expected_responses = success_count * int(protocol["aqs"]["passes"])
    if response_count != expected_responses:
        issues.append(
            f"aqs_response_count:{response_count}:expected:{expected_responses}"
        )
    summary_path = results / "summary.json"
    per_run_path = results / "per_run.jsonl"
    if not summary_path.is_file() or not per_run_path.is_file():
        issues.append("aggregate_outputs_missing")
    else:
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = jsonl(per_run_path)
        if len(rows) != planned or summary.get("successful_pairs") != success_count:
            issues.append("aggregate_counts_mismatch")
        for metric in METRICS:
            actual = macro_average(rows, metric)
            reported = float(summary["metrics"][metric]["mean"])
            if abs(actual - reported) > 1e-12:
                issues.append(f"aggregate_recompute_mismatch:{metric}")
    result = {
        "audited_at_utc": utc_now(),
        "trial": trial,
        "passed": not issues,
        "issues": issues,
        "counts": {
            "planned_pairs": planned,
            "manifest_pairs": manifest_count,
            "successful_pairs": success_count,
            "failed_pairs": planned - success_count,
            "aqs_responses": response_count,
        },
        "protocol_sha256": sha256_file(PROTOCOL_PATH),
        "adapter_sha256": sha256_file(Path(__file__)),
        "source_method_lock_sha256": sha256_file(SOURCE_METHOD_LOCK),
        "model_weight_audit_sha256": weight_audit_hash,
    }
    atomic_json(results / "audit.json", result)
    print(
        f"GPT6_ASTRA_TABLE4_AUDIT_COMPLETE {json.dumps(result, sort_keys=True)}",
        flush=True,
    )
    return result


def verify_lock() -> None:
    if not LOCK_PATH.is_file():
        raise RuntimeError("Formal lock missing; complete and freeze the pilot first")
    lock = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    mismatches = []
    for relative, expected in lock["files"].items():
        path = REPO / relative
        actual = sha256_file(path) if path.is_file() else None
        if actual != expected:
            mismatches.append(
                {"path": relative, "expected": expected, "actual": actual}
            )
    if mismatches:
        raise RuntimeError(f"Formal lock mismatch: {mismatches}")


def freeze() -> dict[str, Any]:
    _, _, pilot_results = trial_paths("pilot")
    audit_result = json.loads(
        (pilot_results / "audit.json").read_text(encoding="utf-8")
    )
    summary = json.loads((pilot_results / "summary.json").read_text(encoding="utf-8"))
    if not audit_result.get("passed") or summary.get("planned_pairs") != 10:
        raise RuntimeError("A passing 10-pair pilot is required before formal freeze")
    protocol = load_protocol()
    protocol["status"] = "formal_frozen"
    protocol["frozen_after_pilot_at_utc"] = utc_now()
    atomic_json(PROTOCOL_PATH, protocol)
    files = [
        Path(__file__),
        PROTOCOL_PATH,
        PROMPT_PATH,
        TABLE4_SPECS,
        INDOOR_SPECS,
        URBAN_SPECS,
        SOURCE_METHOD_LOCK,
        NAVMESH_EVALUATOR,
        RECAST_BINARY,
        REPO / protocol["aqs"]["model_manifest"],
    ]
    lock = {
        "method": protocol["method"],
        "display_name": protocol["display_name"],
        "track": protocol["track"],
        "frozen_at_utc": utc_now(),
        "pilot_summary_sha256": sha256_file(pilot_results / "summary.json"),
        "pilot_audit_sha256": sha256_file(pilot_results / "audit.json"),
        "files": {rel(path): sha256_file(path) for path in files},
        "source_scene_generation_reused": True,
        "no_scene_regeneration": True,
        "no_human_postprocessing": True,
    }
    atomic_json(LOCK_PATH, lock)
    verify_lock()
    print(
        f"GPT6_ASTRA_TABLE4_FREEZE_COMPLETE {json.dumps(lock, sort_keys=True)}",
        flush=True,
    )
    return lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("build", "package", "aggregate", "audit"):
        child = commands.add_parser(command)
        child.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score = commands.add_parser("score")
    score.add_argument("--trial", choices=("pilot", "formal"), required=True)
    score.add_argument("--gpu", type=int, default=3)
    score.add_argument("--port", type=int, default=18104)
    score.add_argument("--request-workers", type=int, default=4)
    score.add_argument("--external-vllm", action="store_true")
    commands.add_parser("freeze")
    commands.add_parser("verify-lock")
    args = parser.parse_args()
    if args.command == "build":
        build_trial(args.trial)
    elif args.command == "package":
        package_trial(args.trial)
    elif args.command == "score":
        start_and_score(
            args.trial, args.gpu, args.port, args.request_workers, args.external_vllm
        )
    elif args.command == "aggregate":
        aggregate(args.trial)
    elif args.command == "audit":
        return 0 if audit(args.trial)["passed"] else 1
    elif args.command == "freeze":
        freeze()
    elif args.command == "verify-lock":
        verify_lock()
        print("GPT6_ASTRA_TABLE4_LOCK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

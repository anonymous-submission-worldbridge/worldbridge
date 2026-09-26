#!/usr/bin/env python3
"""Expose selected WorldGen indoor views as clean standalone images.

The blind-review montages are JPEG contact sheets with a title and burned-in
view numbers.  Their original unlabelled 1280x720 PNG anchors are retained in
the Table-2 run directories.  This utility verifies each retained source
against its montage outside the label area, then hard-links it into the
requested annotation directory without recompression or duplicated data.

One requested scene (I-F3B172EC630E) was already exported from its official
WorldGen triangle mesh by ``worldgen_mesh_visualization.py``.  That verified
clean export is reused as requested instead of rerendering it.
"""

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


import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageStat


REPO_ROOT = _BASELINE_PROJECT_ROOT
BASELINES = REPO_ROOT / "baselines"
ANNOTATIONS = BASELINES / "annotations/worldgen/indoor"
PRIVATE_MAP = ANNOTATIONS / "PRIVATE_blind_map.json"
OUTPUT_ROOT = ANNOTATIONS / "images"
SELECTION_MANIFEST = OUTPUT_ROOT / "selection_manifest_20260921.json"

TILE_SIZE = (480, 270)
MONTAGE_SIZE = (1920, 584)
HEADER_HEIGHT = 44
SOURCE_SIZE = (1280, 720)
REUSED_MESH_RENDER_ID = "I-F3B172EC630E"
SELECTED_IDS = (
    "I-09AC868927BF",
    "I-F34387957465",
    REUSED_MESH_RENDER_ID,
    "I-E976915DA278",
    "I-5526A68E2F63",
    "I-179AB3D6F17A",
    "I-9F2F77ECAD85",
)


def relative(path: Path) -> str:
    return str(path.resolve().relative_to(REPO_ROOT.resolve()))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def load_runs() -> dict[str, Path]:
    payload = json.loads(PRIVATE_MAP.read_text(encoding="utf-8"))
    runs: dict[str, Path] = {}
    for row in payload["items"]:
        blind_id = row["blind_id"]
        if blind_id not in SELECTED_IDS:
            continue
        if not row.get("success"):
            raise RuntimeError(f"Selected item is not successful: {blind_id}")
        run = Path(row["run_dir"]).resolve()
        run.relative_to(BASELINES.resolve())
        runs[blind_id] = run
    missing = sorted(set(SELECTED_IDS) - set(runs))
    if missing:
        raise RuntimeError(f"Missing selected blind IDs in private map: {missing}")
    return runs


def source_images(run: Path) -> list[Path]:
    sources = sorted((run / "renders/anchors").glob("rgb_*.png"))
    expected = [f"rgb_{index:03d}.png" for index in range(8)]
    if [source.name for source in sources] != expected:
        raise RuntimeError(f"Expected {expected} in {run / 'renders/anchors'}")
    for source in sources:
        with Image.open(source) as handle:
            if handle.size != SOURCE_SIZE or handle.mode != "RGB":
                raise RuntimeError(
                    f"Expected 1280x720 RGB source, got {handle.size} {handle.mode}: {source}"
                )
    return sources


def montage_mae(montage: Image.Image, source: Path, view_index: int) -> float:
    with Image.open(source) as handle:
        reference = handle.convert("RGB")
        reference.thumbnail(TILE_SIZE, Image.Resampling.LANCZOS)
    if reference.size != TILE_SIZE:
        raise RuntimeError(
            f"Unexpected downsampled source size {reference.size}: {source}"
        )

    col, row = view_index % 4, view_index // 4
    left = col * TILE_SIZE[0]
    top = HEADER_HEIGHT + row * TILE_SIZE[1]
    tile = montage.crop((left, top, left + TILE_SIZE[0], top + TILE_SIZE[1]))

    # The montage number occupies x=6..46, y=5..35.  Replace a slightly larger
    # area before comparison so JPEG ringing from the label is also ignored.
    tile.paste(reference.crop((0, 0, 56, 45)), (0, 0))
    means = ImageStat.Stat(ImageChops.difference(tile, reference)).mean
    return float(sum(means) / len(means))


def verify_against_montage(blind_id: str, sources: list[Path]) -> list[float]:
    montage_path = ANNOTATIONS / "montages" / f"{blind_id}.jpg"
    with Image.open(montage_path) as handle:
        montage = handle.convert("RGB")
    if montage.size != MONTAGE_SIZE:
        raise RuntimeError(f"Unexpected montage size {montage.size}: {montage_path}")
    errors = [
        montage_mae(montage, source, index) for index, source in enumerate(sources)
    ]
    if max(errors) > 3.0:
        raise RuntimeError(
            f"Source/montage mismatch for {blind_id}; maximum MAE={max(errors):.6f}"
        )
    return errors


def hardlink(source: Path, destination: Path) -> str:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        source_stat = source.stat()
        destination_stat = destination.stat()
        if (
            source_stat.st_dev == destination_stat.st_dev
            and source_stat.st_ino == destination_stat.st_ino
        ):
            return "reused"
        raise FileExistsError(f"Refusing to replace unrelated file: {destination}")
    os.link(source, destination)
    return "created"


def validate_reused_mesh_export(blind_id: str) -> dict[str, Any]:
    manifest_path = OUTPUT_ROOT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    item = next((row for row in manifest["items"] if row["id"] == blind_id), None)
    if item is None or manifest.get("images_have_overlays") is not False:
        raise RuntimeError(f"Missing verified clean mesh export for {blind_id}")
    images = []
    for index, old_record in enumerate(item["images"], start=1):
        path = OUTPUT_ROOT / blind_id / f"view_{index:02d}.png"
        with Image.open(path) as handle:
            if handle.size != SOURCE_SIZE or handle.mode != "RGB":
                raise RuntimeError(f"Unexpected reused image: {path}")
        digest = sha256_file(path)
        if digest != old_record["sha256"]:
            raise RuntimeError(f"Hash mismatch in reused image: {path}")
        images.append(
            {
                "path": relative(path),
                "sha256": digest,
                "width": SOURCE_SIZE[0],
                "height": SOURCE_SIZE[1],
            }
        )
    return {
        "id": blind_id,
        "source_kind": "existing_official_triangle_mesh_render",
        "source_run": item["source_run"],
        "renderer": item["renderer"],
        "images_have_overlays": False,
        "images": images,
    }


def main() -> None:
    runs = load_runs()
    counts = {"created": 0, "reused": 0}
    items: list[dict[str, Any]] = []
    for blind_id in SELECTED_IDS:
        if blind_id == REUSED_MESH_RENDER_ID:
            items.append(validate_reused_mesh_export(blind_id))
            counts["reused"] += 8
            continue

        sources = source_images(runs[blind_id])
        errors = verify_against_montage(blind_id, sources)
        images = []
        for index, source in enumerate(sources, start=1):
            destination = OUTPUT_ROOT / blind_id / f"view_{index:02d}.png"
            counts[hardlink(source, destination)] += 1
            images.append(
                {
                    "path": relative(destination),
                    "source": relative(source),
                    "sha256": sha256_file(destination),
                    "width": SOURCE_SIZE[0],
                    "height": SOURCE_SIZE[1],
                    "montage_mae_without_label": round(errors[index - 1], 6),
                }
            )
        items.append(
            {
                "id": blind_id,
                "source_kind": "native_worldgen_anchor",
                "source_run": relative(runs[blind_id]),
                "images_have_overlays": False,
                "images": images,
            }
        )

    atomic_json(
        SELECTION_MANIFEST,
        {
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "method": "worldgen",
            "domain": "indoor",
            "selection": list(SELECTED_IDS),
            "processing": (
                "Six scenes are hard links to verified native unlabelled anchors; "
                "the already completed clean official-mesh export is reused for one scene."
            ),
            "images_have_overlays": False,
            "items": items,
        },
    )
    print(
        f"Standalone images ready: {counts['created']} created, "
        f"{counts['reused']} reused; manifest={SELECTION_MANIFEST}"
    )


if __name__ == "__main__":
    main()

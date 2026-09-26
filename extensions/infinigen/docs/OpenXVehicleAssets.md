# OpenX Vehicle Assets Integration

This document describes how to use `OpenXVehicleFactory` to load real vehicle
geometry from an [OpenX](https://www.asam.net/standards/detail/openx/) asset
pack and render it inside the Infinigen urban pipeline.

## Overview

`OpenXVehicleFactory` is a drop-in replacement for the procedural
`VehicleFactory`.  It:

1. Scans an asset root for `.xoma` + `.blend` pairs.
2. Picks a vehicle at random (or by category).
3. Normalises scale so every car is ~4.5 m long with its bottom at z = 0.
4. Randomises body-paint colour while leaving the original `.blend` unchanged.
5. Adds a procedural license plate, optional dirt/scratch overlay, and an
   invisible bounding-box empty with custom properties.
6. Returns the same `(objects_list, metadata_dict)` tuple as `VehicleFactory`,
   so it can be plugged directly into the urban scene pipeline.

When no OpenX assets are found (e.g. `OPENX_ASSETS_ROOT` is not set), the
factory automatically falls back to the procedural `VehicleFactory`.

---

## Quick start

### 1. Set the asset root

```bash
export OPENX_ASSETS_ROOT=/path/to/openx_assets
```

The factory expects `.xoma` metadata files and `.blend` geometry files to be
co-located under:

```
$OPENX_ASSETS_ROOT/
  src/
    vehicles/
      main/
        <vehicle_id>/
          <vehicle_id>.xoma
          <vehicle_id>.blend
```

If the directory layout differs, the scanner also accepts a flat directory of
`.blend` files (with or without `.xoma` companions).

### 2. Run the preview script

```bash
cd ./infinigen
blender -b --python infinigen_examples/openx_vehicle_preview.py
```

Output:
- `outputs/urban_v3_vehicle/openx_preview0001-0150.mp4` — 150-frame orbit video
- `outputs/urban_v3_vehicle/openx_metadata.json` — vehicle metadata
- `outputs/urban_v3_vehicle/openx_preview.blend` — saved scene

---

## API reference

### `OpenXManifest`

```python
from infinigen.assets.objects.vehicles.openx_vehicle import OpenXManifest

manifest = OpenXManifest(assets_root="/path/to/openx")
print(len(manifest))           # number of vehicles found
entry = manifest.pick("car")   # random car
entry = manifest.pick(seed=42) # deterministic pick
```

**`OpenXVehicleEntry` fields**

| Field        | Type    | Description                               |
|--------------|---------|-------------------------------------------|
| `vehicle_id` | str     | Identifier derived from the .xoma / .blend filename |
| `name`       | str     | Human-readable name from .xoma metadata  |
| `blend_path` | Path    | Absolute path to the .blend file          |
| `xoma_path`  | Path?   | Absolute path to the .xoma file, or None  |
| `length`     | float   | Vehicle length in metres (default 4.50)   |
| `width`      | float   | Vehicle width in metres (default 1.88)    |
| `height`     | float   | Vehicle height in metres (default 1.45)   |
| `category`   | str     | `car` \| `truck` \| `bus` \| `motorcycle` |
| `mass`       | float   | Mass in kg (default 1500)                 |

### `OpenXVehicleFactory`

```python
from infinigen.assets.objects.vehicles.openx_vehicle import OpenXVehicleFactory
from infinigen.assets.utils.urban_primitives import UrbanAssetRequest

factory = OpenXVehicleFactory(mats, assets_root=None, fallback=True)

request = UrbanAssetRequest(
    asset_type = "vehicle",
    location   = (10.0, 3.5, 0.0),
    semantic   = "vehicle",
    yaw        = 0.0,
    params     = {
        "vehicle_category": "car",  # optional: filter by category
        "id": "0",
        "axis": "x",
    },
)
objects, meta = factory.create(request)
```

**Constructor parameters**

| Parameter     | Default | Description                                                         |
|---------------|---------|---------------------------------------------------------------------|
| `mats`        | —       | Material dict (same format as `VehicleFactory`)                    |
| `assets_root` | `None`  | Override `OPENX_ASSETS_ROOT`; `None` reads from env                |
| `fallback`    | `True`  | Use procedural `VehicleFactory` when no OpenX assets are found      |

**`create()` return value**

```python
objects: list[bpy.types.Object]   # all Blender objects for the vehicle
meta: {
    "id":       str,    # vehicle_id from manifest
    "name":     str,    # human-readable name
    "type":     str,    # category
    "center":   [x, y, 0.0],
    "yaw":      float,
    "length":   float,
    "width":    float,
    "height":   float,
    "mass":     float,
    "source":   "openx",   # or "procedural" if fallback was used
    "blend":    str,    # absolute path to source .blend
}
```

---

## .xoma metadata format

The factory supports both XML and JSON `.xoma` files.  The following fields
are parsed (all optional — defaults are used when absent):

**XML example**
```xml
<vehicle>
  <id>sedan_01</id>
  <name>Generic Sedan</name>
  <vehicleCategory>car</vehicleCategory>
  <mass>1420</mass>
  <boundingBox>
    <length>4.55</length>
    <width>1.82</width>
    <height>1.44</height>
  </boundingBox>
</vehicle>
```

**JSON example**
```json
{
  "id": "sedan_01",
  "name": "Generic Sedan",
  "vehicleCategory": "car",
  "mass": 1420,
  "boundingBox": { "length": 4.55, "width": 1.82, "height": 1.44 }
}
```

---

## Material randomisation

Body paint is replaced with a freshly created Principled BSDF material chosen
from an 8-colour palette (white, black, red, blue, grey, green, champagne,
copper).  A small random jitter is applied to the RGB values so no two vehicles
look identical.

Glass slots (detected by slot name containing `glass`, `window`, `windshield`,
or `windscreen`) are swapped with a shared semi-transparent glass material.

The original `.blend` file on disk is **never modified**.

### Dirt / scratch overlay

A procedural noise-driven dirt layer is injected into the paint material node
tree at a random intensity (0–15 %).  This is purely additive: it mixes a dark
brown diffuse shader over the paint using a noise ramp.

---

## Scale normalisation

After loading, the factory:

1. Computes the bounding box of all mesh objects in world space.
2. Scales uniformly so the X-axis extent equals `entry.length`.
3. Translates so the centroid is at the origin and the minimum Z is 0 (bottom
   of vehicle on the road surface).
4. Applies a small yaw jitter (±2°) to simulate lane positioning variation.

---

## Integration with the urban pipeline

```python
from infinigen.assets.objects.vehicles.openx_vehicle import OpenXVehicleFactory

# In your urban scene realizer, replace VehicleFactory with:
vehicle_factory = OpenXVehicleFactory(mats, fallback=True)

# Then use it exactly as before:
objs, meta = vehicle_factory.create(request)
for obj in objs:
    bpy.context.collection.objects.link(obj)
```

The returned `objects` list can be parented to a collection or passed to the
semantic tagging and export pipeline without any other changes.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| "No OpenX assets found" warning + fallback used | `OPENX_ASSETS_ROOT` not set or path doesn't exist | Export the env var or pass `assets_root=` to the constructor |
| Vehicle appears as a white cube | `.blend` file has no mesh objects | Verify the asset .blend is a valid Blender scene |
| Vehicle is the wrong size | `.xoma` bounding box values are in different units | Edit the `.xoma` or override `entry.length` in a subclass |
| Dirt overlay is too heavy | `max_intensity` default 0.15 | Call `_add_dirt_overlay(..., max_intensity=0.05)` directly |

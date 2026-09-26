# Dynamicization and Video Rendering for Multi-Sensory Environments

The dynamic methods of WorldBridge do not generate a new set of scenes; instead, they add an additional dynamic post-processing stage after the static scene.

```text
Static generation (maintain the original flow)
        │
        ▼
There is already scene.blend → Dynamic Object Detection → Vehicle/Wind/Water/Fountain Animations → New dynamic.blend
                                                               │
                                                               ▼
                                                            MP4 video
```

The repository's `generate.py` remains suitable for open-ended, one-off physical effects, using an LLM to generate Blender scripts. `dynamics.py` provides deterministic production workflows for vehicles, vegetation, rivers, and fountains. Both can coexist.

## `urban_v1_full_13` Production-grade Dedicated Pipeline

The combined scenario is very large, with assets linked through multiple `collection_instance` instances. Please use dedicated scripts; it will not modify the original static `.blend`.

```bash
sh scripts/run_urban_v1_full_13_dynamic.sh
```

Default output to:

```text
infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic/
├── urban_v1_full_13_dynamic.blend
├── dynamic_manifest.json
├── frames/frame_0001.png ...
├── render_progress.json
└── urban_v1_full_13_dynamic.mp4
```

This dedicated version implements strict `no-toy` policies: vehicle use scenarios have already been covered with 18 complete OpenX body, interior, light, and wheel layers; rivers, lakes, and fountains use existing high-resolution surfaces and PBR materials; trees use five high-detail trunk and crown assets. The script adds animation wrappers, deformers, and material time-driven effects without creating blocky vehicles, low-polygon trees, or spherical water droplets as alternatives.

Dynamic display consists of four consecutive shots: vehicle and wheel linkage, river and riverbank trees, native fountain water droplets/water jets/sprays, and lake surface with tree canopy movement. Default is 144 frames, 24 fps, 1280×720. If the machine is busy, you can first do a low-resolution preview, and then still use the same `.blend` to restore the official rendering:

```bash
blender -b \
  infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic/urban_v1_full_13_dynamic.blend \
  --python scripts/render_urban_v1_full_13_dynamic.py -- \
  --output-dir infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic/preflight_frames \
  --frames 1,37,73,109 --resolution-x 640 --resolution-y 360 --samples 8 \
  --tree-mode none --overwrite
```

Official support for progressive rendering: PNGs that have been decoded and are already present will be skipped. To rebuild an animation layer, set `C2W_DYNAMIC_REBUILD=1`; to override resolution or sampling rate, set `C2W_DYNAMIC_RESOLUTION_X`, `C2W_DYNAMIC_RESOLUTION_Y`, and `C2W_DYNAMIC_SAMPLES`.

Blender 5.1's Vulkan single buffer cannot simultaneously accommodate the five million 1100–3000 vertex crowns in this scene. The default video therefore adopts the original post-process approach from the warehouse: the first three segments are directly rendered by dynamic `.blend`, and the final tree/lake segment generates restricted crown sways and directional water ripples from an audited full-13 1080p lake sequence. It does not create low-poly models, proxies, or billboards, nor does it modify production `.blend`. The dynamic `.blend` itself still retains the full animation of all 50 trees. If the GPU/driver supports ultra-large buffers, set `C2W_DYNAMIC_HYBRID_WIND_TAIL=0 C2W_DYNAMIC_TREE_MODE=all` to render everything directly.

## A single command is executed.

```bash
sh scripts/dynamic_scene.sh \
  /path/to/static_scene.blend \
  output/dynamics/my_scene_dynamic.blend \
  configs/dynamics/default.json \
  output/dynamics/my_scene.mp4
```

Generate only the `.blend` with animation, do not render video for now:

```bash
C2W_APPLY_ONLY=1 sh scripts/dynamic_scene.sh /path/to/static_scene.blend
```

The script refuses to allow input and output to point to the same file, so existing static scenes will not be overwritten. The original `scene.sh`, `scene_stream*.sh`, and city generation scripts do not need to be changed.

## Four categories of effects

- Vehicle: Reads `c2w_dynamic_role=vehicle` root object first, also compatible with `Vehicles` sets and `Grp_Root/car/vehicle` etc. Default follows vehicle local forward axis; configurable for precise route with wheel rotation.
- Wind: Generates oscillation with reversed phase for root or leaf objects in `Trees`/`Vegetation`, with smaller amplitude to avoid bending of tree trunks like rubber.
- River: Copy target water material at the Noise/Wave node with time-based looping; if no Wave nodes exist in the original material, insert dynamic normal perturb without breaking the workflow.
- Waterfall: Creates looping water droplets at the center of discovered waterfalls without relying on Mantaflow baking, suitable for quick preview and video display in large scenes.

After execution, a `*.dynamics.json` will be generated next to `.blend`, listing the actual objects, materials recognized and animated, and reasons for skipping. Check this report first before proceeding with long-duration video rendering.

## Large-scale joint scenarios should use explicit configuration.

Automatically discover suitable naming conventions for scenarios. For very large scenarios composed of multiple collection instances, it is recommended to copy.
`configs/dynamics/unified_scene.example.json` and fill in the key objectives.

The vehicle uses world coordinates for its route:

```json
{
  "effects": {
    "vehicles": {
      "routes": [
        {
          "object": "vn1_Grp_Root",
          "forward_axis": "X",
          "points": [[2.25, -48.0, 0.0], [2.25, 48.0, 0.0]]
        }
      ]
    }
  }
}
```

When using fountain instances to infer world coordinates is unreliable, explicitly fill in the center:

```json
{
  "effects": {
    "fountain": {
      "center": [26.0, 20.0, 0.0]
    }
  }
}
```

Panoramic view that switches to a track camera:

```json
{
  "camera": {
    "mode": "orbit",
    "target": [0.0, 0.0, 8.0],
    "radius": 75.0,
    "height": 28.0,
    "start_degrees": -35.0,
    "end_degrees": 35.0
  }
}
```

## Semantics to be written for the generator

New assets should be assigned custom properties to "movable root objects" instead of assigning vehicle tags to each part of vehicles.

```python
vehicle_root["c2w_dynamic_role"] = "vehicle"
vehicle_root["c2w_forward_axis"] = "X"
tree_root["c2w_dynamic_role"] = "tree"
fountain_pool["c2w_dynamic_role"] = "fountain"
river_surface["c2w_dynamic_role"] = "river"
```

This decouples the dynamic layer from specific asset filenames, allowing old assets to continue working with the collection/name fallback rules.

## Quality and Performance

- Default: 120 frames/second, 24 fps, 5 seconds video; dynamic loop is closed with `frame_end + 1`.
- Default settings: Eevee, 720p, H.264 for initial viewing to ensure correct motion. Final presentation can be improved by increasing resolution, sampling, or switching to Cycles.
- The vehicle should provide an explicit route along the centerline of the road; automatic straight-line motion is suitable for rapid validation.
- Do not animate large amounts of leaves individually. For distant shots, use tree roots/tree canopies to sway. For close-ups with heroes, use bones, Geometry Nodes, or cloth simulation for the trees.
- The default implementations of rivers and fountains do not have expensive physical caching. If the lens is set to a water body close-up, replace the fountain with the high-quality version of Mantaflow/Geometry Nodes.
- Dynamic post-processing will retain existing user animations; an entry marked with `preserved existing animation` indicates that the object was not covered by it.

## Closed-loop with VLM-Motion Critic

The motion evaluator from the original repository can still be used after video rendering:

```bash
python worldbridge/postprocess/reflect.py \
  "The vehicle travels smoothly along the road, leaves slightly sway, the river flows continuously, and the fountain sprays steadily." \
  output/dynamics/my_scene.mp4
```

Write evaluation results to `output/postprocess/dynreflection_feedback.json`. For general open-ended effects, feedback can be passed to `generate.py` for further processing; for deterministic pipelines, typically adjust JSON parameters such as speed, wind sway angle, fountain height, and period directly based on feedback.

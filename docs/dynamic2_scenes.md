# Full-13 dynamic2

Independent entrance: `scripts/run_urban_v1_full_13_dynamic2.sh`.
The original static generator, Original `.blend`, the first version of dynamic scripts, and the output do not cover.
Output directory: `infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic2/`.
The full scene name in the main file is `urban_v1_full_13`; if opened to the default blank scene in library mode,
Select this scene by dragging with the selection box in Blender. The rendering and audit scripts will automatically choose the correct scene.

## Implementing boundaries

This version is procedural animation with physical constraints, not a full Navier-Stokes fluid, elastic trees, or vehicle dynamics solver.
Follow the "Edit Scene - Render Video - Check Physical Consistency - Correct" workflow from WorldBridge.
Refer to implementation: <ANONYMOUS_SOURCE>.
Local determinism audits do not equate to requiring external model services for VLM critics.

- The complete master file retains static scenes with buildings, interiors, roads, and all placements; not reconstructed from low-poly models for dynamic demonstrations.
- 18 original OpenX vehicles with fixed straight lanes, linear position keyframes, 2 m/s speed, no loop teleportation.
  The horizontal traffic flow is separated from the vertical traffic flow at the conflict zone; 72 original wheel skeletons rotate according to measured tire radii and correct rolling directions.
  Scanline sweep bounding box checks should cover the entire 384-frame time range, not just a few frames.
  Refine large areas to original triangular patches; allow normal tires to contact the ground without exempting terrain penetration.
- Only apply a small localized rotation around fixed native vertices to the real LeafFactory leaves, while trees, roads, buildings, and positions remain unaffected by wind motion.
  All original tree species should be retained; no use of screen color masking, full-screen shaking, billboards, or simplified alternative grids.
  By replaying deterministic leaf transformations from the original generator, restore the merged grid to its native leaf instances; verify vertex static coordinate errors are less than
  0.00002 meters, fully validated coverage of the original grid is achieved, with no reduction in face count. A total of 289,350,825 original polygons were retained for both tree canopies.
  The complete main file link `render_packs/` contains the same instance geometry and aerodynamic nodes, so please retain the entire output directory and static asset dependencies.
- The surface uses the finite depth gravity wave dispersion relation `ω²=gk tanh(kh)`, superimposed with a unidirectional 0.3 m/s advection, with fixed grid boundaries.
- The fountains can only be selected by `urban_semantic == fountain-water`; sculptures and nozzles cannot be chosen mistakenly based on any of the `jet` style names.
  Continuing with the original water droplet geometry, updated to `p=p0+v0 t+(0,0,-g t²/2)`, with gravity at 9.81 m/s².
  At the spray breakage location / overflow outlet, it is produced at the receiving water surface for recovery without any time-varying overall scaling.
  The original outer ring spray misses the lower water basin; the horizontal range of the static retracted body now places the splash point within the true surface, preserving the stone sculpture as intended.
  The details of overflow flow follow ballistic trajectories under free fall, just as the original 1660 water droplets from the fountain in the lake do.
- 4 fixed shots, each 96 frames long, totaling 16 seconds at 24 FPS. Render with the original assets within the lens cone and shadow buffer.
  Do not prune by tree species; cones from outside the tree remain in the complete main file. Use the per-scene exact dependency package of `render_packs/` for official rendering.
  Each shot uses an independent Blender process to avoid cache accumulation across shots.
  Use Cycles/OptiX with 32 samples, noise removal, 1280x720 resolution; no screen space animation or frame interpolation.

## Running and Acceptance Testing

Need actual GPU device access permissions; failure in software Vulkan/llvmpipe environment cannot be used as evidence of NVIDIA memory limit.
For example, select the appropriate system for the device:

```sh
CUDA_VISIBLE_DEVICES=0 sh scripts/run_urban_v1_full_13_dynamic2.sh
python3 scripts/test_dynamic2_math.py
```

The post-rendering has been built with `--render-only`. The GPU number should be selected based on the result of the local machine's `nvidia-smi` check.
If the long-running process is terminated by the system, use `python3 scripts/resume_urban_v1_full_13_dynamic2.py --shot river_and_wind --gpu 0`.
Alternatively, use `--shot lake_and_wind` to resume rendering in batches of two frames. Batch logs and memory samples are in `batch_logs/`.
If there is no new valid frame for three consecutive batches, it will stop and report an error; it will not consider failed batches as successful ones, nor will it change the scene, quality, or frame rate.
Generate frame strip main file, render code, parameters, and library file fingerprints; if the fingerprint changes, select a new frame output directory to avoid mixing old frames.
The construction/traffic inspection of `dynamic2_manifest.json` and the rendering status of `progress_*.json` are in different stages;
Only having the main file does not mean that the video is complete. Actual frame count and frame/animation changes should also be checked for final delivery.
`dynamic2_audit.json` Check the keyframe speed after saving, the no-slip condition of the tires, fixed camera, static stone sculpture, gravity, and the falling point inside the pot.
Only when `delivery_audit.json` is `PASS` does it indicate that 384 complete PNGs, motion for four shots, and a 16-second video have all passed verification.
Acceptance checks also compare fixed leaf, water, building, and sky regions in the river shot to verify that movement is confined to the areas intended to move.

## Known boundaries

Preserve strong daylight, white buildings, and material style of the original scene without redoing the art assets.
The cycles node system reports `Maximum number of closures exceeded: 76 > 64` for some of the original complex materials.
[Introduction to Blender Source Code](https://github.com/blender/blender/blob/main/intern/cycles/scene/scene.cpp)
Static counting warnings of this kind are harmless because they are discarded when mixed branches or low-weight branches are eliminated, but there is an upper bound on closures that cannot be used to claim material convergence with infinite precision.
Video inspection includes actual images and complete decoding; physical inspection covers preset 16-second trajectories without guaranteeing no conflicts after any arbitrary time extension.

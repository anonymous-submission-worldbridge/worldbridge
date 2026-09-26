# Full-13 dynamic3

Target directory: `infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic3/`.

Adopt the dynamic post-processing workflow of WorldBridge: add semantically constrained animations to existing static scenes, render actual 3D frames, and then check the motion range and physical constraints. Do not overwrite the original static, dynamic, and dynamic2 files.

## Dynamic and Models

- The wind acts only on leaf instances that have been validated with native vertices and faces. Maintain the native leaf anchor points fixed, reducing the amplitude of the two rotational components from 0.075/0.055 radians to 0.021/0.0154 radians; cameras, world sky, tree trunk, buildings, and roads remain fixed.
- The original micro-amplitude of long waves on both river surfaces and lake surfaces has been reduced to 35%. The entire set of textures based on the original material is removed; deposition colors and fountain wave patterns remain fixed while water waves change only their surface normals and small surface displacements.
- Reuse the circular Wave Texture and spatial decay material nodes from `infinigen/assets/objects/decor/urban_lake.py`. The fountain ripple wave length is 0.57 meters, propagating according to gravity/surface tension dispersion relationships.
- The lake surface retains its original water color and volume absorption while calibrating the water's IOR = 1.333, Specular IOR level = 0.5, roughness range 0.16-0.24, and existing wave normal weights to make the touch-water ripple identifiable in reflections; no replacement of the lake geometry is made.
- All 1,660 native water droplets use the dynamic2 gravity trajectory. They propagate outward from their impact points over time, with wave packets that decay over time based on previous impacts; this avoids hard resets. The original mesh has 16,900 vertices, 16,641 faces, and maintains the same Basis coordinates/topology (SHA-256 unchanged). Actual peak displacement is approximately 7.3 mm.
- This is an animation of fluid dynamics and linear wave response, not a full fluid solver. The original material, art, and static geometry inherent to the source still exist, precluding any claim of complete physical reality replication.
- -No alternative grid, reduction of faces, billboards, screen-space distortion, or frame buffering. Visible assets and conservative shadow range will be loaded per lens; original 82-placement joint scene remains intact.

## Lenses and Deliveries

Each shot is fixed camera position, 6 seconds, 24 fps, 144 original frames per second (fps). The formal quality is Cycles/OptiX with 1920x1080 resolution, 128 samples, fixed random seed, adaptive sampling disabled, and Simplify turned off. Noise reduction is performed using OIDN accurate/high with static area pixel comparison. High sample noise reduction scheme has been applied to static areas.

| Video filename | View |
| --- | --- |
| `river_environment.mp4` | River, bridge, riverbank and surrounding area as a whole |
| `river_detail.mp4` | Fixed trunk, leaf movement and local river surface |
| `lake_environment.mp4` | Complete lake area, wharf, pavilion and surrounding environment |
| `lake_impact.mp4` | Fountain in the lake, water droplets touching water and ripples |
| `fountain_environment.mp4` | Stone Sculpture Fountain and Surrounding Environment |
| `fountain_detail.mp4` | Original stone carving details, layered waterfalls and droplets |
| `street_environment.mp4` | Native vehicle movement, tire rolling, and street areas |

The official video is at `videos/`, while the complete frame is at `frames_final/<shot>/`. `frames/` is an early noise-free check frame, and `denoise_check/` is a comparison of noise reduction stability; both are not considered as final delivery videos. `previews_denoised/` serves as a check frame after subsequent calibration.

`build_*.json` records the model source, geometric proof, and scene package fingerprint; `render_contract.json` records the actual rendering parameters and dependencies. `pipeline_<worker>.status.json` is the running status and does not represent delivery. Only the final `delivery_audit.json`'s `PASS` indicates that all seven video segments have been checked.

## Running

```sh
python3 scripts/run_urban_v1_full_13_dynamic3.py --gpu 1 --phase preview
python3 scripts/run_urban_v1_full_13_dynamic3.py --gpu 1 --phase production --batch 8
```

`--shots river_detail,... --worker gpu0` can assign non-overlapping shots to another idle GPU without parallelizing tasks of the same stage; lock coordinator for each shot. Exit Blender after batch rendering and release cache; restore by fully validating PNGs then skipping completed frames, moving damaged ones to the log directory.

Generate the overall main file separately to avoid overwriting already verified rendering packages:

```sh
blender --disable-depsgraph-on-file-load -b infinigen/outputs/outdoor_full_demo/urban_v1_full_13-dynamic2/urban_v1_full_13_dynamic2.blend --threads 4 --python-exit-code 1 --python scripts/assemble_urban_v1_full_13_dynamic3_master.py
```

This operation requires first completing and validating the `river_detail` and `lake_impact` lens packages, then linking the same verified native dynamic grid, materials, and blade nodes back to the complete combined scene to avoid redundant baking. The complete main file still contains all 82 original placements; it uses linked assets, so the main file size does not represent the scene's geometric scale. Please retain `render_packs/`, the original static asset library, and the native blade library dependency for dynamic2. `master_build.json` records the linked packages and their SHA-256 hashes.

Early builds that were terminated due to full load and re-bake early were completed using the reuse method; this process did not degrade geometric or render quality.

The file is saved using the Blender library system. If an empty default scene appears when interacting, select either `urban_v1_full_13` (Complete Main File) from the Scene dropdown or `DYN3_<Lens Name>` (Lens Package) under the Scene dropdown; the rendering script will automatically choose the actual scene.

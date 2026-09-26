# HY-World 2.0 Table 3

This package evaluates only HY-World 2.0 for the two Table-3 surface-only
rows. It reuses all 200 completed Table-2 generations and never invokes
HY-Pano, WorldNav, WorldStereo, or Gaussian training.

The scored surface is reconstructed from the final trained Gaussian PLY by
rendering expected depth from a frozen subset of final training cameras. The
native WorldNav NavMesh is explicitly excluded. Scale is recovered from the
camera-height/floor anchor in the initial generated panorama geometry; that
point cloud is used only for calibration, never as the scored surface.

Run with the existing HY environment and three idle GPUs:

```bash
PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/envs/hyworld2/bin/python -B \
  baselines/methods/hyworld/geometry/hyworld_geometry.py inventory

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/envs/hyworld2/bin/python -B \
  baselines/methods/hyworld/geometry/hyworld_geometry.py run \
  --phase pilot --domains indoor urban --gpus 0 1 2

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/envs/hyworld2/bin/python -B \
  baselines/methods/hyworld/geometry/hyworld_geometry.py lock

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/envs/hyworld2/bin/python -B \
  baselines/methods/hyworld/geometry/hyworld_geometry.py run \
  --phase formal --domains indoor urban --gpus 0 1 2

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/envs/hyworld2/bin/python -B \
  baselines/methods/hyworld/geometry/hyworld_geometry.py aggregate

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/envs/hyworld2/bin/python -B \
  baselines/methods/hyworld/geometry/hyworld_geometry.py audit
```

All persistent outputs stay below `baselines/data/table3_hyworld2` and
`baselines/methods/hyworld/geometry`; no source Table-2 file is modified.

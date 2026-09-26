# MetaUrban — Table 3

This directory is the isolated MetaUrban implementation of the frozen Table 3
urban structured/physics-ready protocol.  It does not run or modify any other
baseline.  The isolation is intentional because the pre-existing shared
`baselines/evaluation/geometry/` and `baselines/protocol/geometry/` trees are read-only in this
workspace.

## Reuse and final-output definition

- Source runs: `baselines/data/table2/urban/metaurban` (25 specs × 4 seeds).
- Table 2 manifests, native inputs and scene descriptors are reused read-only.
- Table 2 did not retain final Panda3D/Bullet instances, so the same official
  commit, full asset pack, native map/config and method seed are deterministically
  reconstructed.  Object count, block IDs and lane geometry must match Table 2.
- RGB/video and Table 2 quality metrics are never regenerated.
- The evaluated final output is the native, meter-scale `AssetManager` instance
  set.  Native Bullet dimensions/poses define OBB collision proxies; final
  Panda3D tight bounds define support height.
- Dynamic traffic and pedestrian/robot populations are frozen at zero.

## Frozen metric protocol

- ROI: 112 m square centered on the final native block's positive-lane endpoint.
- Collision: OBB SAT plus exact horizontal overlap × vertical overlap; significant
  at penetration > 1 cm, or overlap > 1e-5 m³ and > 0.5% of the smaller object.
- Floating: final visual bottom > 2 cm above the 0.15 m native support surface.
- OOB: footprint centroid outside its semantic container, or outside area > 1%.
- Support: gap ≤ 2 cm, embedding ≤ 1 cm (30 cm for roots), projection ≥ 5%,
  centroid in container, and no significant collision.
- Navigation: locally rebuilt external Recast, 1.70 m × 0.30 m pedestrian,
  climb 0.20 m, slope 45°, cell 0.05 m × 0.05 m.  No component connection and
  no largest-component filtering.
- Valid thresholds: fifth percentiles from the independent deterministic 50-scene
  urban reference suite in `results/reference_urban_calibration.json`.
- Aggregation: mean over four seeds per spec, then equal mean over 25 specs;
  10,000 spec-cluster bootstrap replicates for 95% CIs.

## Reproduction

```bash
baselines/envs/metaurban/bin/python -m unittest discover \
  -s baselines/methods/metaurban/geometry/tests -v

baselines/envs/metaurban/bin/python \
  baselines/methods/metaurban/geometry/tools/calibrate_reference.py

baselines/envs/metaurban/bin/python baselines/methods/metaurban/geometry/run_matrix.py \
  --phase pilot --gpus 0 1 2 3 --workers 4

baselines/envs/metaurban/bin/python baselines/methods/metaurban/geometry/run_matrix.py \
  --phase formal --gpus 0 1 2 3 --workers 4

baselines/envs/metaurban/bin/python \
  baselines/methods/metaurban/geometry/metrics/aggregate.py

# Post-hoc supplement only: primary Table 3 Valid remains frozen.
baselines/envs/metaurban/bin/python \
  baselines/methods/metaurban/geometry/metrics/analyze_valid_sensitivity.py

# Post-hoc visual/operational collision sensitivity; primary Collision is unchanged.
baselines/envs/metaurban/bin/python \
  baselines/methods/metaurban/geometry/metrics/analyze_collision_sensitivity.py

baselines/envs/metaurban/bin/python \
  baselines/methods/metaurban/geometry/tools/audit.py
```

All experiment outputs are under
`baselines/data/table3_metaurban/urban/metaurban`; all implementation, protocol,
logs and results remain under `baselines/`.

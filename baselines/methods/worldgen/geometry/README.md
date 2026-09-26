# WorldGen Table 3 evaluation

This directory contains the isolated Table 3 evaluation for the frozen
`ZiYang-xie/WorldGen` Table 2 outputs. It does not run or modify any other
baseline method.

WorldGen's default final output is a Gaussian splat without native object
instances. The evaluation results follow those of "Baselines/Comparison Experiments - Table 3.md".
surface-only track: Collision, Floating, OOB, Support, and Valid Scene are
`N/A-I`; only Navigable Area, Connected Area, and NavMesh Success are numeric.

The evaluation reuses all 200 Table 2 splats through relative symlinks. It does
not regenerate panoramas, rerun DA-2, or download weights. The ordered splat
centers are triangulated with one frozen extraction configuration. Metric scale
is recovered per scene from the already-preregistered Table 2 camera height and
the median nadir-floor cap. WorldGen/OpenCV coordinates are converted to metric
right-handed Z-up coordinates before the common Recast build. Recast component
connection and largest-component filtering are both disabled.

Configuration and locks:

- `baselines/methods/worldgen/protocol/geometry/geometry_worldgen.yaml`
- `baselines/methods/worldgen/protocol/geometry/geometry_worldgen_method.lock.json`
- `baselines/methods/worldgen/protocol/geometry/geometry_worldgen_metrics.lock.json`

Execution:

```bash
PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/worldgen_geometry.py inventory

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/worldgen_geometry.py lock

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/worldgen_geometry.py run --phase pilot --workers 4

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/worldgen_geometry.py run --phase formal --workers 4

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/worldgen_geometry.py aggregate

PYTHONPATH=baselines/methods/worldgen/geometry/runtime/recast_glibc231_clean2 \
  baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/worldgen_geometry.py audit

baselines/environments/worldgen/bin/python \
  baselines/methods/worldgen/geometry/spotcheck.py
```

The original HY-World Recast extension required glibc 2.32, while this host has
glibc 2.31. `build_recast.sh` reproducibly builds the same checked-in binding
with the host compiler; no network access is used.

Outputs are under `baselines/data/table3_worldgen` and aggregate/audit artifacts
are under `baselines/results/table3_worldgen`.

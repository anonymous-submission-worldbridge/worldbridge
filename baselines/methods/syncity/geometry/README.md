# SynCity 3000 — Table 3

This package evaluates only SynCity 3000 under the frozen Table-3 surface-only
protocol. It reuses Table-2 outputs read-only and never regenerates scenes.

```bash
python3 baselines/methods/syncity/geometry/syncity_geometry.py inventory
python3 -m pytest -q baselines/methods/syncity/geometry/test_syncity_geometry.py
python3 baselines/methods/syncity/geometry/syncity_geometry.py lock
python3 baselines/methods/syncity/geometry/syncity_geometry.py run --phase pilot --gpus 6 7
python3 baselines/methods/syncity/geometry/syncity_geometry.py audit --phase pilot
python3 baselines/methods/syncity/geometry/syncity_geometry.py run --phase formal --gpus 6 7
python3 baselines/methods/syncity/geometry/syncity_geometry.py aggregate
python3 baselines/methods/syncity/geometry/syncity_geometry.py audit --phase formal
```

The GPU extraction subprocess uses the existing
`baselines/envs/syncity-3k` Python 3.10 environment. The driver uses Python
3.11 and the already-built common Recast binding. All caches, logs, canonical
meshes, metrics, and aggregate results remain below `baselines/`.

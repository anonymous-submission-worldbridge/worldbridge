# HY-World 2.0 + fixed IO adapter — Table 4

This package adds a separate `fixed_io_adapter_system` row. It does not replace
the native HY-World 2.0 or WorldGen rows and it never regenerates a HY-World
scene. The 100 frozen HY-World pairs and their Functional/Visual AQS values are
immutable inputs.

The geometry, portal, collision, Recast navigation and Spatial AQS definitions
match the frozen WorldGen fixed-IO-adapter system track. The adapter adds the
same deterministic 12 m × 10 m synthetic shell and open portal to every source
pair. Native HY-World point clouds remain hash-addressed visual provenance and
are excluded from the disclosed synthetic collision geometry.

All commands are resumable. Existing outputs are reused only when their source,
protocol and adapter hashes match.

```bash
PY=baselines/environments/worldgen/bin/python
RUN=baselines/methods/hyworld/unified/fixed_adapter/hyworld_io_adapter.py

$PY -m pytest -q baselines/methods/hyworld/unified/fixed_adapter/tests
$PY $RUN run-all --gpu 5 --port 18084 --request-workers 4
$PY $RUN verify-lock
```

# WorldGen + fixed IO adapter — Table 4

This directory adds a separate system row; it does not replace or modify the
native `WorldGen (ZiYang-xie)` row.  The adapter reuses the completed WorldGen
Table 4 outputs and adds one frozen synthetic building shell, shared open
portal, public approach, floor transition, and registered navigation targets.

Every spec and seed uses the same 12 m × 10 m shell and the same transform,
portal, and anchor rules.  Per-sample ICP, scaling, metric-aware repair, and
human adjustment are forbidden.  Native WorldGen mesh paths and hashes are
preserved in each canonical record; they are not overwritten or duplicated.
The synthetic adapter collision is disclosed separately from native geometry.

Functional and Visual AQS are reused exactly from the frozen native WorldGen
evaluation because the visual outputs do not change. Spatial AQS is newly
scored on the original eight-view montage plus a fixed-scale canonical overlay.
All geometry/navigation values are attributed to the complete adapter system,
not to native WorldGen.

```bash
PY=baselines/environments/worldgen/bin/python
RUN=baselines/methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py

$PY -m pytest -q baselines/methods/worldgen/unified/fixed_adapter/tests
$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score-spatial --trial pilot --gpu 0 --request-workers 4
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score-spatial --trial formal --gpu 0 --request-workers 4
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
```

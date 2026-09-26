# syncity-3k + fixed IO adapter — Table 4

This package evaluates a separate fixed-adapter system row. It reuses the
completed syncity-3k Table-2 scenes and eight-view renders without regenerating
any scene or downloading any model. A preregistered semantic mapping pairs each
Table-4 function/theme/seed with one urban and one indoor Table-2 run without
inspecting success or scores.

The geometry/navigation protocol is the same 12 m x 10 m synthetic shell, open
portal, public approach, collision model, and Recast configuration used by the
other fixed-IO rows. Those six values describe the adapter system, not native
syncity-3k unified-world capability. Functional, Visual, and Spatial AQS are
scored in three seeded passes on anonymous evidence with the existing local
Qwen3-VL-8B checkpoint.

```bash
PY=baselines/environments/worldgen/bin/python
RUN=baselines/methods/syncity/unified/fixed_adapter/syncity_io_adapter.py

$PY -m pytest -q baselines/methods/syncity/unified/fixed_adapter/tests
$PY $RUN audit-weights
$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score --trial pilot --gpu 3 --request-workers 4
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score --trial formal --gpu 3 --request-workers 4
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
$PY $RUN verify-lock
```

Every command is resumable. A cached build is reused only when its source
signature, protocol hash, adapter hash, and output hashes still match. A cached
AQS response is reused only when its evidence, prompt, settings, and model
manifest signature match. The large source PLY files are checked by frozen
matrix status, manifest state, existence, and exact byte size; they are excluded
from adapter metrics and are not repeatedly rehashed.

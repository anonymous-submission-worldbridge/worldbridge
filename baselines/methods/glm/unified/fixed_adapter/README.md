# GLM-5.3 + fixed IO adapter (Table 4)

This isolated system-track runner reuses the completed and audited GLM-5.3
Low Table-2 scenes. It does not invoke GLM Coding Plan, regenerate scenes, or
download models. Source Blender scenes provide immutable visual evidence; the
fixed shell, portal, collision geometry, and Recast NavMesh are disclosed
adapter components rather than native GLM capabilities.

```bash
PY=baselines/envs/hyworld2/bin/python
RUN=baselines/methods/glm/unified/fixed_adapter/glm_io_adapter.py

$PY $RUN source-audit
$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score --trial pilot --gpu auto --port 18414 --request-workers 1
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score --trial formal --gpu auto --port 18415 --request-workers 1
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
$PY $RUN verify-lock
```

Stages are idempotent and validate input signatures plus SHA-256 hashes before
reusing cached outputs. Scoring uses only the local Qwen3-VL checkpoint, so
the workflow makes zero remote GLM requests and incurs zero Coding Plan cost.

# GLM-5.3 Flash + fixed IO adapter (Table 4)

This isolated system-track runner reuses the completed and audited GLM-5.3
Flash Table-2 scenes. It does not invoke GLM Coding Plan, regenerate scenes or
download models. Source Blender scenes contribute immutable visual evidence;
the fixed 12 m x 10 m shell, portal, collision geometry and Recast NavMesh are
explicit adapter components and are not presented as native GLM capabilities.

Resumable execution sequence:

```bash
PY=baselines/envs/hyworld2/bin/python
RUN=baselines/methods/glm_flash/unified/fixed_adapter/glm_flash_io_adapter.py

$PY $RUN source-audit
$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score --trial pilot --gpu auto --port 18404 --request-workers 1
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score --trial formal --gpu auto --port 18405 --request-workers 1
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
$PY $RUN verify-lock
```

Every stage is idempotent. Existing packages and ratings are reused only when
their frozen input signatures and SHA-256 hashes match. Do not run `freeze`
again after a passing Pilot has frozen the protocol. The scoring stages use
only the local Qwen3-VL checkpoint and therefore incur no Coding Plan cost.

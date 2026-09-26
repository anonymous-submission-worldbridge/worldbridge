# Gemini 3.1 Pro + fixed IO adapter (Table 4)

This isolated system-track runner reuses the completed and audited Gemini 3.1
Pro Table-2 scenes. It never invokes Antigravity/Gemini, never uses an API key,
never regenerates a scene, and never downloads a model. Source Blender scenes
are immutable visual evidence; the fixed shell, portal, collision geometry and
Recast NavMesh are disclosed adapter components rather than native Gemini
capabilities.

```bash
PY=baselines/envs/hyworld2/bin/python
RUN=baselines/methods/gemini/unified/fixed_adapter/gemini_io_adapter.py

$PY $RUN source-audit
$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score --trial pilot --gpu auto --port 18416 --request-workers 1
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score --trial formal --gpu auto --port 18417 --request-workers 1
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
$PY $RUN verify-lock
```

Every stage is resumable. Cached outputs are reused only when their input
signature and recorded SHA-256 values still validate. AQS uses only the local
`models/Qwen/Qwen3-VL-8B-Instruct` checkpoint; Gemini Coding Plan
requests and Gemini API-key requests are both fixed at zero for this workflow.
`--gpu auto` waits in 30-second intervals without loading weights until the
frozen remaining-memory admission rule passes.

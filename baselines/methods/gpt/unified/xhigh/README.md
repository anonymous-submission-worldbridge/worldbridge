# GPT-6 Astra Extra High + fixed IO adapter (Table 4)

This isolated system track reuses only completed **GPT-6 Astra Extra High**
Table-2 evidence. It never invokes GPT-6 Astra, never regenerates a scene, and
never substitutes Low, Medium, High, or another method for xhigh.

The former xhigh formal scene directories were stored in `/tmp` and are now
absent. The retained, hashed 8-view montages and videos in
`baselines/annotations/gpt6_astra_xhigh/` are therefore the visual source
artifacts consumed here. The missing Blender geometry is not reconstructed or
claimed. The fixed adapter's synthetic collision geometry is evaluated with the
same shared Recast and AQS code used by the existing system rows.

```bash
PY=baselines/envs/hyworld2/bin/python
RUN=baselines/methods/gpt/unified/xhigh/gpt_xhigh_io_adapter.py

$PY $RUN inventory
$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score --trial pilot --gpu 7 --port 18404 --request-workers 1
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score --trial formal --gpu 7 --port 18404 --request-workers 1
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
$PY $RUN verify-lock
```

All stages are resumable and hash-validated. The formal lock is
`baselines/methods/gpt/protocol/unified/xhigh/unified_gpt6_astra_extra_high_io_adapter.lock.json`.
The local launch uses tensor parallelism across physical GPUs 6 and 7, reserves
70% of each card, and uses one request worker. This avoids the observed
single-card visual-encoder profile OOM while keeping the same full model and all
AQS prompt/seed/decoding settings.

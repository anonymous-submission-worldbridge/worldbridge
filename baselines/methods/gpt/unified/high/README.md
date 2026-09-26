# GPT-6 Astra + fixed IO adapter — Table 4

This package evaluates a separate system row. It reuses immutable GPT-6 Astra
Table-2 Blender scenes and fixed anchor renders; it does not regenerate scenes,
download weights, or alter the original results. A preregistered semantic
mapping pairs each Table-4 function/theme/seed with one urban and one indoor
Table-2 run without inspecting success or scores.

The adapter adds the same 12 m x 10 m synthetic shell, open portal, public
approach, collision, and Recast navigation layout used by the other fixed-IO
system baselines. Geometry/navigation scores describe the complete adapter
system, not native GPT-6 Astra unified-world capability. Three AQS dimensions
are scored on anonymous evidence with the existing local Qwen3-VL checkpoint.

```bash
PY=baselines/environments/worldgen/bin/python
RUN=baselines/methods/gpt/unified/high/gpt_io_adapter.py

$PY -m pytest -q baselines/methods/gpt/unified/high/tests
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

Every command is resumable. Cached artifacts are reused only when their frozen
input signatures and SHA-256 hashes still match.

If three retries return valid integer scores but omit or mislabel a required
evidence text field, the frozen schema-repair policy checks the retained
responses from that same seeded pass in attempt order, without mixing fields
between responses, and keeps the first valid occurrence of all three scores in
one response unchanged. A later string under the same duplicate score key is
deterministically relabeled as that dimension's evidence when this produces
the exact six-field schema; otherwise the local model is asked only for the
missing explanations. Every
rejected response and repair is saved, the repair mode is marked, and a repair
that changes any score is rejected.

The reused local Qwen snapshot is verified with `audit_weight_manifest.py`.
The two ignored entries are repository metadata (`.gitattributes` and the
absent `configuration.json`); all 15 model/tokenizer files, including every
safetensors shard, must match the frozen manifest.

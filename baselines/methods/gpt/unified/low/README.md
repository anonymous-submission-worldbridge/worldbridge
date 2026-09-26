# GPT-6 Astra Low + fixed IO adapter (Table 4)

This isolated system-track runner implements the Table 4 Low comparison row
while reusing the completed **GPT-6 Astra Low** Table-2 scenes. The Low source
identity is explicit in the protocol, every source record, and the formal lock.
The runner never invokes GPT-6 Astra, never regenerates a scene, and never
downloads a model.

It reuses the same fixed 12 m × 10 m shell, shared portal, collision geometry,
Recast evaluator, and local Qwen3-VL AQS protocol as the existing WorldGen,
HY-World 2.0, GPT-6 Astra and GPT-6 Astra Medium system rows. Original Low
Blender scenes provide immutable visual evidence only; they are excluded from
the synthetic adapter collision geometry.

The Pilot and formal experiments are complete: Pilot 10/10 pairs and 30/30
ratings, formal 100/100 manifests, 95 successful paired sources and 285/285
ratings, formal audit passed with no issues. All nine ITT values, confidence
Intervals and low-source disclosures are in "Baselines/Comparison Experiment - Table 4.md" section 29.
The original instruction mistakenly named this Low-source row Extra High.
The paper-facing §29 label is now **GPT-6 Astra Low + fixed IO adapter**;
historical runner paths and frozen protocol/result display fields retain the
original label for hash-locked provenance. The genuine Extra High row in §28
was not changed.

Resumable command sequence:

```bash
PY=baselines/envs/hyworld2/bin/python
RUN=baselines/methods/gpt/unified/low/gpt_low_io_adapter.py

$PY $RUN build --trial pilot
$PY $RUN package --trial pilot
$PY $RUN score --trial pilot --gpu auto --port 18304 --request-workers 1
$PY $RUN aggregate --trial pilot
$PY $RUN audit --trial pilot
$PY $RUN freeze

$PY $RUN build --trial formal
$PY $RUN package --trial formal
$PY $RUN score --trial formal --gpu auto --port 18305 --request-workers 1
$PY $RUN aggregate --trial formal
$PY $RUN audit --trial formal
$PY $RUN verify-lock
```

The sequence above documents the original run. The Pilot is **already
frozen**: do not call `freeze` again, because that would assign a new frozen
timestamp and change the protocol hash. For the completed experiment, start
with `verify-lock`, the existing formal `audit.json` and the published
results; only rerun build/package/score if an input or output really needs
checking or repair. `audit --trial formal` recomputes the audit but refreshes
its timestamp and therefore its published SHA-256. If port 18305 is
temporarily unavailable after stopping the local
server, use another verified free localhost port; port is not a scoring input.

Two frozen formal responses required evidence-only recovery from their first
already saved schema-repair response, with identical original integer scores.
`python baselines/methods/gpt/unified/low/recover_schema.py`
idempotently rechecks all source hashes and canonical response hashes without
calling any model. The post-Pilot rule, script and source-hash journal are
included in the formal lock. A response without lossless same-reply evidence
is rejected rather than filled by hand.

Before Pilot or formal resume, `$PY $RUN source-audit` checks the frozen Low
identity and all 100 deterministic pair sources without making changes. The
runner rehashes any cached canonical outputs before reusing a `SUCCESS` package.

`--gpu auto` only selects a compute-idle card (utilization <=10% and at
least 32 GiB free). The registered 55% GPU reservation is ~26 GiB on an
A6000, with no CPU weight offload; ~20 GiB remains unreserved on a vacant
48 GiB card. It fails safely without changing ratings when no card is idle;
rerunning resumes previously validated passes.

Build/package/score products are reused only when their frozen input
signatures and SHA-256 hashes match. The one-time Pilot `freeze` is an
exception and must not be rerun after formal results exist.

Earlier diagnostic runs reserved 30%, then 18% of GPU 2, with 12 GiB
of exact model weights offloaded to CPU. Even when GPU 2's compute was
initially idle, the 18% profile generated only ~0.2 tokens/s and the first
600-second AQS request timed out. Immediately before freezing the Pilot,
two full A6000 cards became idle. The registered profile now loads the
unchanged local Qwen weights fully onto a truly idle GPU with 55% reservation.
Only one request is issued at a time; model/prompt/sampling settings are
unchanged from the other fixed-adapter rows.

To avoid the saturated `/data` mount delaying Python package discovery, the
runner reuses the existing local `.cache/worldgen_io_vllm_env_uid2002` vLLM
environment. The Qwen weights remain at the requested local Hugging Face path;
no package or model download is performed.

The first diagnostic launch on a busy GPU compiled the vision graph, then
showed that capturing all CUDA Graphs would take roughly two hours. The
registered launch uses vLLM eager execution, which skips that optimization
while preserving weights, dtype, prompt, seeds, temperature and top-p.
Rerun `score --trial pilot --gpu auto` only when a card meets the registered
idle compute and memory criteria; do not mark transport timeouts as scene
failures or fabricate AQS values.

# WorldGen Table 4 experiment

This directory implements only the `ZiYang-xie/WorldGen` row of Table 4. It
uses the matched-text independent track frozen in
`baselines/methods/worldgen/protocol/unified/native/protocol.yaml`. Each planned pair is two native
WorldGen text-to-scene calls (exterior and interior) with the same logical seed
and matched function/style specification. No post-hoc transform, building ID,
portal, collision repair, or IO adapter is introduced.

Consequently, Functional AQS-VLM and Visual AQS-VLM are numeric. Spatial AQS,
Shape IoU, Entrance Alignment, Entrance Passability, Transition Collision,
I-O Connectivity, and Cross-boundary Reachability are `N/A-U`. The official
WorldGen triangle mesh is still exported beside the Gaussian splat so that the
native geometry claim and lack of a shared frame remain auditable.

The reused Table 2 renderer still writes 8 anchors and 50 sequence frames per
side. Table 4 success depends on the four preregistered AQS anchors per side and
both geometry exports. The stricter Table 2 sequence verdict is retained as a
diagnostic; it cannot invalidate an otherwise complete Table 4 evidence pair.

The Table 2 source, environment, weights, and renderer are reused offline. No
download is required. Pilot data is isolated under `baselines/work/`; formal
data is under `baselines/data/table4_worldgen/`.

On the resumed host, prior files under `baselines/results/table4/worldgen` were
owned by an unavailable account. The WorldGen-only writable roots are therefore
`baselines/results/table4_worldgen`, `baselines/data/table4_worldgen`, and
`baselines/annotations/table4_worldgen`; no other Table 4 method directory is
modified.

```bash
WG=baselines/environments/worldgen/bin/python
RUN=baselines/methods/worldgen/unified/native/worldgen_unified.py

$WG $RUN validate
$WG $RUN preflight
$WG $RUN capability-audit
$WG $RUN calibrate-evidence
$WG -m pytest -q baselines/methods/worldgen/unified/native/tests

$WG $RUN run --trial pilot --phase compile
$WG $RUN run --trial pilot --phase panorama --gpus 0 1 --workers 2
$WG $RUN run --trial pilot --phase reconstruct --gpus 0 1 --workers 2
$WG $RUN run --trial pilot --phase render --gpus 0 1 --workers 2
$WG $RUN package --trial pilot
$WG $RUN score --trial pilot --gpu 0 --request-workers 4
$WG $RUN aggregate --trial pilot
$WG $RUN audit --trial pilot
$WG $RUN freeze

$WG $RUN run --trial formal --phase compile
$WG $RUN run --trial formal --phase panorama --gpus 0 1 2 3 --workers 4
$WG $RUN run --trial formal --phase reconstruct --gpus 0 1 2 3 --workers 4
$WG $RUN run --trial formal --phase render --gpus 0 1 2 3 --workers 4
$WG $RUN package --trial formal
$WG $RUN score --trial formal --gpu 0 --request-workers 4
$WG $RUN aggregate --trial formal
$WG $RUN audit --trial formal
```

If all cards are occupied, wait for a card to satisfy the memory/utilization
gate for three consecutive samples before starting (this avoids taking a brief
gap between another user's queued jobs):

```bash
$WG $RUN wait-run --trial pilot --phase panorama \
  --candidate-gpus 0 1 2 3 4 --workers 1 --poll-seconds 30 --stable-samples 3
```

GPU phases enforce both the frozen free-memory threshold and a utilization
threshold before starting. Exit code 75 means that the selected GPU is busy;
it is a resource gate, not a method failure. Every phase is resumable and skips
validated existing artifacts unless `--force` is explicitly supplied.

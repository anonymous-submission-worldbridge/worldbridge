# Baselines

Each method owns its adapters, runners, protocols, tools, and tests. Shared evaluation code is organized by task instead of paper table number.

```text
baselines/
  methods/<method>/
    adapter.py             Generation adapter
    run.py                 Generation matrix runner, where available
    evaluate.py            Method-specific visual evaluation, where available
    geometry/              Geometry and navigation evaluation
    unified/               Unified indoor/outdoor evaluation
      native/              Native method pipeline, where available
      fixed_adapter/       Fixed adaptation pipeline, where available
    protocol/              Frozen method configurations and prompts
    tools/                 Method-specific utilities
    tests/                 Method-specific tests
    environment/           Method dependencies, where available
  evaluation/
    visual/                Shared generation and visual evaluation
    geometry/              Shared geometry metrics
    unified/               Shared indoor/outdoor protocol and metrics
  protocol/                Shared generation, geometry, and unified specifications
  tools/                   Shared utilities
  tests/                   Shared evaluator tests
  registry.py              Public generation adapter names
```

The method families are `gemini`, `glm`, `glm_flash`, `gpt`, `hyworld`, `infinigen`, `majutsucity`, `metaurban`, `sceneweaver`, `spatialgen`, `syncity`, and `worldgen`. Only implemented workflows are present; the directory pattern does not imply every method supports every task.

GPT reasoning variants share the `gpt` family. Generation adapters are `adapter.py`, `adapter_low.py`, `adapter_medium.py`, and `adapter_xhigh.py`. Unified workflows use `unified/high`, `unified/low`, `unified/medium`, and `unified/xhigh`. The historical directory labeled `gpt6_astra_xhigh_io_adapter` actually used Low evidence; it is now correctly under `unified/low`. The former `extra_high` implementation is under `unified/xhigh`. Their scientific identities and source-evidence limitations are retained.

## Entry points

From the WorldBridge root:

```bash
python scripts/compare.py --method worldgen -- --help
python scripts/compare.py --method worldgen -- compile --domain indoor --spec-id indoor_bedroom_00 --seed 0
python baselines/evaluation/visual/aggregate_generation.py --help
python baselines/methods/worldgen/geometry/worldgen_geometry.py --help
python baselines/methods/worldgen/unified/fixed_adapter/worldgen_io_adapter.py --help
```

`compare.py` retains the public method aliases and forwards all arguments to the independent generation adapter. Geometry and unified evaluation use their respective method entry points. Full inference requires each method's external sources, environment, models, and data; no model is bundled here.

Former Table 2 code is generation/visual evaluation, Table 3 is geometry/navigation evaluation, and Table 4 is unified indoor/outdoor evaluation. Frozen schema identifiers, experimental record keys, and historical data/results paths may still contain table numbers: changing those would change the experiment's identity or break existing artifacts. They are not source-package names. The complete file mapping is in [baseline_organization.json](../docs/migration/baseline_organization.json).

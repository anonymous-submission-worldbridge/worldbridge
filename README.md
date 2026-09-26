# WorldBridge

WorldBridge converts text and parameterized scene descriptions into code for generating, rendering, and evaluating 3D and dynamic scenes.

```text
worldbridge/           Core scene, object, dynamics, planning, and metric modules
baselines/             Method adapters, protocols, execution, and evaluation
configs/               Inference examples and dynamics configurations
scripts/               Common entry points and retained scene generation/rendering scripts
scripts/modeling_history/ Historical modeling implementations and reproduction scripts
configs/modeling/      Authored floor plans and camera routes
extensions/infinigen/  Local Infinigen additions and modifications
library/               Runtime prompt and code templates
docs/modeling/         Modeling source index, provenance, and verification
tests/                 Core tests
docs/                  Dynamic scene documentation and migration records
```

## Environment and resources

Use Python 3.11 and the dependency constraints in `requirements.txt`:

```bash
python -m pip install -r requirements.txt
python -m pip install -e . --no-deps
```

Parameterized planning and descriptor validation require only the Python standard library; the first two commands below work without additional dependencies. The project provides generation, inference, rendering, and evaluation workflows. It has no training entry point.

For full scene generation, configure Blender and native dependencies following the [Infinigen installation instructions](https://github.com/princeton-vl/infinigen). Install the Infinigen source in this directory's `infinigen/` subdirectory. The original upstream revision is `05a09759fe9478595a3323ec2d6e26ce3513223f`. Apply the local customizations after installation:

```bash
python scripts/setup_extensions.py --apply
```

The repository retains modeling source and configurations. Generated `.blend` files, interchange meshes, and their exported textures are excluded. External generation libraries default to `external/` and learned-model weights to `models/`; configure third-party assets such as OpenX vehicles separately when a generator requires them. Override generation paths with `WORLDBRIDGE_EXTERNAL`, `WORLDBRIDGE_MODELS`, `WORLDBRIDGE_CACHE`, `WORLDBRIDGE_PYTHON`, `WORLDBRIDGE_SITE_PACKAGES`, and `BLENDER_BIN`.

Baseline dependency versions and model/data paths are specified in each method's `baselines/methods/<method>/protocol/` and `environment/` directories. Install a separate environment for each method. Place third-party sources and models in locations such as `baselines/sources/`, `baselines/vendor/`, and `baselines/checkpoints/`, as specified by the relevant protocol. Do not point writable outputs at the original projects.

## Running WorldBridge

Run these commands from the project root:

```bash
python scripts/infer.py --config configs/infer.json --output output/descriptor.json
python scripts/evaluate.py output/descriptor.json

export OPENAI_API_KEY="your_api_key"
# Optional: OPENAI_BASE_URL and OPENAI_MODEL. WORLDBRIDGE_* and legacy aliases are also supported.
python scripts/infer.py --mode nature --prompt "Create a spooky forest scene with fog"
python scripts/infer.py --mode indoor --prompt "Create a cozy bedroom with warm lighting"
python scripts/infer.py --mode urban --prompt "A crossroads with homes, a park and shops"
python scripts/infer.py --mode object --prompt "A heavy iron anvil crushing a soda can"

sh scripts/dynamic_scene.sh input/scene.blend output/dynamic.blend configs/dynamics/default.json output/dynamic.mp4
```

The `descriptor` mode uses the original deterministic planner without an API, Blender, datasets, or models. Other modes invoke the full original generation workflows and require their dependencies and resources. Descriptors are written to `--output`; the original workflows retain their `output/` and `infinigen/outputs/` conventions. Dynamic scene processing preserves the input `.blend` file. Configurations are in `configs/infer.json` and `configs/dynamics/`.

## Running and evaluating baselines

```bash
python scripts/compare.py --help
python scripts/compare.py --method worldgen -- --help
python scripts/compare.py --method worldgen -- compile --domain indoor --spec-id indoor_bedroom_00 --seed 0
python baselines/evaluation/visual/aggregate_generation.py --help
python baselines/evaluation/visual/aggregate_generation.py --method worldgen --domain indoor
```

`compare.py` forwards arguments; each original adapter defines its algorithm and default inference parameters. Supported methods include syncity, worldgen, hyworld, gemini, glm, glm_flash, gpt and its low/medium/xhigh variants, infinigen, sceneweaver, spatialgen, metaurban, and majutsucity. `compile` compiles inputs only; see each adapter's `--help` for model inference parameters.

Generate results before evaluation. Default data and output locations are `baselines/data/` and `baselines/results/`. Method-specific protocols are in `baselines/methods/<method>/protocol/`; shared specifications are in `baselines/protocol/`. See the [baseline guide](baselines/README.md) for generation, geometry, and unified indoor/outdoor entry points. Frozen experiment identifiers retain their original values.

The [modeling source index](docs/modeling/README.md) links the implementations for bicycles, delivery lockers, factories, schools, police stations, parks, robots, and other families. The [source catalog](docs/modeling/catalog.json) records retained files and provenance. Procedural generators construct geometry; scene assembly and rendering stages may require previously generated components or external resources. The earlier model-file copies have been removed. Original project files remain untouched. 

## Anonymous review snapshot

This snapshot contains the WorldBridge source and baseline adapters. Author metadata, original repository links, local account paths, development conversations, and migration logs are omitted for anonymous review. No original Git history is included. Third-party license notices are retained.

The project page is in `demo/`. The selected media are qualitative examples, not a quantitative evaluation. Robot demonstrations use authored kinematic animation; dynamic effects use procedural animation. External assets, generated Blender scenes, learned weights, and baseline datasets must be configured separately as described above. Legacy configuration aliases and frozen experiment identifiers are retained for compatibility.

Run the core tests with `PYTHONDONTWRITEBYTECODE=1 python -m pytest -q tests`. Baseline integration tests additionally require their external environments and data.

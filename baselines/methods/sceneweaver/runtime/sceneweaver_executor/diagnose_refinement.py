#!/usr/bin/env python3
"""Exercise SceneWeaver refinement through solving, without save or render."""

from __future__ import annotations

# Resolve the checkout independently of this method package's depth.
import sys as _baseline_sys
from pathlib import Path as _BaselinePath

_BASELINE_PROJECT_ROOT = next(
    p
    for p in _BaselinePath(__file__).resolve().parents
    if (p / "worldbridge").is_dir() and (p / "baselines/registry.py").is_file()
)
if str(_BASELINE_PROJECT_ROOT) not in _baseline_sys.path:
    _baseline_sys.path.insert(0, str(_BASELINE_PROJECT_ROOT))


# Allow direct execution as well as package imports.
import sys as _wb_sys
from pathlib import Path as _WBPath

_wb_root = next(
    p for p in _WBPath(__file__).resolve().parents if (p / "worldbridge").is_dir()
)
if str(_wb_root) not in _wb_sys.path:
    _wb_sys.path.insert(0, str(_wb_root))
from worldbridge.paths import path_variables as _wb_path_variables

_wb_paths = _wb_path_variables()

_wb_WORLDBRIDGE_ROOT = _wb_paths["WORLDBRIDGE_ROOT"]


import argparse
import os
import sys
from pathlib import Path


BASELINES_ROOT = Path(f"{_wb_WORLDBRIDGE_ROOT}/baselines")
SCENEWEAVER_ROOT = BASELINES_ROOT / "vendor/SceneWeaver"
sys.path.insert(0, str(SCENEWEAVER_ROOT))
sys.path.insert(
    0,
    str(
        (
            _BASELINE_PROJECT_ROOT
            / "baselines/methods/sceneweaver/runtime/sceneweaver_executor"
        )
    ),
)

from baselines.methods.sceneweaver.runtime.sceneweaver_executor.generate_indoors_compat import (
    compact_load_record,
)
from baselines.methods.sceneweaver.runtime.sceneweaver_executor.generate_indoors_compat import (
    install_collision_mesh_budget,
)
from baselines.methods.sceneweaver.runtime.sceneweaver_executor.generate_indoors_compat import (
    install_plane_projection_fix,
)
from infinigen.core import execute_tasks
from infinigen.core import init  # noqa: E402, F401
from infinigen.core.constraints import checks  # noqa: E402
from infinigen.core.constraints.example_solver import populate  # noqa: E402
from infinigen.core.constraints.example_solver.room import constants  # noqa: E402
from infinigen.core.util import pipeline  # noqa: E402
from infinigen_examples.indoor_constraint_examples import home_constraints  # noqa: E402
from infinigen_examples import generate_indoors as _generate_indoors  # noqa: E402, F401
from infinigen_examples.steps import (
    basic_scene,
    solve_objects,
    update_graph,
)  # noqa: E402
from infinigen_examples.util import constraint_util as cu  # noqa: E402
from infinigen_examples.util.generate_indoors_util import restrict_solving  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-dir", type=Path, required=True)
    parser.add_argument("--json-name", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--iteration", type=int, default=1)
    parser.add_argument("--steps", type=int, default=10)
    args = parser.parse_args()

    os.environ["save_dir"] = str(args.save_dir)
    os.environ["JSON_RESULTS"] = str(args.json_name)
    install_collision_mesh_budget()
    install_plane_projection_fix()
    scene_seed = init.apply_scene_seed(str(args.seed))
    overrides = [
        "compose_indoors.terrain_enabled=False",
        "compose_indoors.invisible_room_ceilings_enabled=True",
        f"compose_indoors.solve_steps_large={args.steps}",
    ]
    init.apply_gin_configs(
        configs=["base_indoors.gin", "fast_solve.gin", "overhead.gin", "studio.gin"],
        overrides=overrides,
        config_folders=[
            "infinigen_examples/configs_indoor",
            "infinigen_examples/configs_nature",
        ],
    )
    constants.initialize_constants()
    consgraph = home_constraints()
    stages = basic_scene.default_greedy_stages()
    all_vars = [cu.variable_room, cu.variable_obj]
    checks.check_all(consgraph, stages, all_vars)
    stages, consgraph, limits = restrict_solving(stages, consgraph)

    state, solver, *_ = compact_load_record(args.iteration - 1)
    work_dir = args.save_dir / "executor_work" / "diagnostic_refinement"
    work_dir.mkdir(parents=True, exist_ok=True)
    executor = pipeline.RandomStageExecutor(scene_seed, work_dir, {})
    state, solver = update_graph.update(solver, state, executor)
    executor.run_stage(
        "populate_assets",
        populate.populate_state_placeholders_mid,
        state,
        use_chance=False,
    )
    state, solver = solve_objects.solve_large_object(
        stages,
        limits,
        solver,
        state,
        executor,
        consgraph,
        {"solve_steps_large": args.steps, "abort_unsatisfied_large": False},
    )
    print(
        f"REFINEMENT_SOLVE_OK iteration={args.iteration} steps={args.steps} "
        f"objects={len(state.objs)} geometry={len(state.trimesh_scene.geometry)}"
    )


if __name__ == "__main__":
    main()

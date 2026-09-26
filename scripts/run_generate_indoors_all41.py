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

from pathlib import Path
import json
import os
import runpy
import sys
import time

import infinigen
import infinigen.core.execute_tasks as execute_tasks
from mathutils import Vector
from numpy.random import uniform

from infinigen.assets.objects import elements, seating, shelves, tableware
from infinigen.core.constraints import usage_lookup
from infinigen.core.constraints import constraint_language as cl
from infinigen.core.util.logging import Timer, create_text_file
from infinigen.core.util.math import FixedSeed
from infinigen.core.tags import Semantics
from infinigen_examples.constraints import home as indoor_home
from infinigen_examples.constraints import semantics as indoor_semantics


# all45_09 forbids toy/figurine and visibly blob-like assets.
# NatureShelfTrinketsFactory can choose
# procedural creature figurines (and its herbivore branch is not Blender 4.5
# compatible). PlantContainerFactory variants produced opaque brown masses in
# the production render. Remove all three factories from every Indoor semantic
# before home constraints are constructed; no proxy replacements are added.
_home_asset_usage = indoor_semantics.home_asset_usage


def home_asset_usage_without_toy_or_blob_items():
    used_as = _home_asset_usage()
    for factories in used_as.values():
        if hasattr(factories, "discard"):
            factories.discard(elements.NatureShelfTrinketsFactory)
            factories.discard(tableware.PlantContainerFactory)
            factories.discard(tableware.LargePlantContainerFactory)
            factories.discard(shelves.KitchenIslandFactory)
    assert elements.NatureShelfTrinketsFactory not in used_as[Semantics.OfficeShelfItem]
    assert all(
        tableware.PlantContainerFactory not in factories
        and tableware.LargePlantContainerFactory not in factories
        for factories in used_as.values()
        if hasattr(factories, "__contains__")
    )
    assert all(
        shelves.KitchenIslandFactory not in factories
        for factories in used_as.values()
        if hasattr(factories, "__contains__")
    )
    return used_as


indoor_semantics.home_asset_usage = home_asset_usage_without_toy_or_blob_items
# home.py imports this function into its own module namespace, so patch that
# cached alias as well as the defining semantics module.
indoor_home.home_asset_usage = home_asset_usage_without_toy_or_blob_items

# home_furniture_constraints directly constructs zero-to-N plant expressions
# after initializing usage_lookup.  Temporarily register their required
# generic Object tag so upstream can construct those expressions, then remove
# the complete plant constraint/score terms and unregister both factories in
# production_home_furniture_constraints below.  They never remain available
# to any greedy proposal stage.
_initialize_usage_lookup = usage_lookup.initialize_from_dict
_temporarily_registered_factories = {
    tableware.PlantContainerFactory: {Semantics.Object},
    tableware.LargePlantContainerFactory: {Semantics.Object},
    shelves.KitchenIslandFactory: {
        Semantics.Object,
        Semantics.Furniture,
        Semantics.KitchenCounter,
    },
}


def initialize_usage_lookup_without_plant_proposals(used_as):
    _initialize_usage_lookup(used_as)
    for factory, tags in _temporarily_registered_factories.items():
        usage_lookup._factory_lookup[factory].update(tags)
        for tag in tags:
            usage_lookup._tag_lookup[tag].add(factory)


usage_lookup.initialize_from_dict = initialize_usage_lookup_without_plant_proposals


# Remove plant variables for every all45_09 Indoor role. The upstream living-
# room program also allows zero sofas; add a native wall-sofa constraint only
# for the designated showcase rather than inserting furniture after solving.
_home_furniture_constraints = indoor_home.home_furniture_constraints


def production_home_furniture_constraints():
    problem = _home_furniture_constraints()
    problem.constraints.pop("plants", None)
    problem.score_terms.pop("plants", None)
    rooms = cl.scene()[{Semantics.Room, -Semantics.Object}]
    objects = cl.scene()[{Semantics.Object, -Semantics.Room}]
    furniture = objects[Semantics.Furniture].related_to(rooms, indoor_home.cu.on_floor)
    kitchens = rooms[Semantics.Kitchen].excludes(indoor_home.cu.room_types)
    wall_counters = furniture[Semantics.KitchenCounter][
        shelves.KitchenSpaceFactory
    ].related_to(rooms, indoor_home.cu.against_wall)
    # Replace upstream's wall-counter * island constraint with a wall-only
    # production constraint. KitchenIslandFactory is excluded because this
    # Blender/Infinigen combination evaluates it as an empty mesh.
    problem.constraints["kitchen_counters"] = kitchens.all(
        lambda room: wall_counters.related_to(room).count().in_range(1, 2)
    )
    if os.environ.get("INFINIGEN_INDOOR_ROLE") == "showcase":
        livingrooms = rooms[Semantics.LivingRoom].excludes(indoor_home.cu.room_types)
        # Restrict the required sofa domain to the solver's single
        # on-floor-and-wall greedy stage. A bare SofaFactory count overlaps all
        # four placement stages and is rejected by Infinigen's coverage check.
        sofas = furniture[seating.SofaFactory]
        problem.constraints["all45_09_showcase_sofa_required"] = livingrooms.all(
            lambda room: sofas.related_to(room, indoor_home.cu.against_wall)
            .count()
            .in_range(1, 4)
        )
    for factory, tags in _temporarily_registered_factories.items():
        usage_lookup._factory_lookup.pop(factory, None)
        for tag in tags:
            usage_lookup._tag_lookup[tag].discard(factory)
    return problem


indoor_home.home_furniture_constraints = production_home_furniture_constraints


# Keep the genuine KitchenSpaceFactory but constrain its along-wall span to a
# realistic compact-residence range. The upstream 1.7-5.0 m span can exceed
# every usable wall segment in a solved low-rise kitchen, making the mandatory
# counter impossible to initialize even after many annealing iterations.
_kitchen_space_init = shelves.KitchenSpaceFactory.__init__


def compact_kitchen_space_init(
    self, factory_seed, coarse=False, dimensions=None, island=False
):
    if dimensions is None and not island:
        with FixedSeed(factory_seed):
            dimensions = Vector(
                (
                    uniform(0.72, 0.92),
                    uniform(1.80, 2.65),
                    uniform(2.30, 2.45),
                )
            )
    return _kitchen_space_init(
        self,
        factory_seed,
        coarse=coarse,
        dimensions=dimensions,
        island=island,
    )


shelves.KitchenSpaceFactory.__init__ = compact_kitchen_space_init


def patched_main(
    input_folder, output_folder, scene_seed, task, task_uniqname, **kwargs
):
    execute_tasks.logger.info(f"infinigen version {infinigen.__version__}")
    execute_tasks.logger.info(
        f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')}"
    )

    input_folder = Path(input_folder).absolute() if input_folder is not None else None
    output_folder = Path(output_folder).absolute()
    output_folder.mkdir(exist_ok=True, parents=True)

    if task_uniqname is not None:
        create_text_file(filename=f"START_{task_uniqname}")

    with Timer("MAIN TOTAL"):
        execute_tasks.execute_tasks(
            input_folder=input_folder,
            output_folder=output_folder,
            task=task,
            scene_seed=scene_seed,
            **kwargs,
        )

    if task_uniqname is not None:
        create_text_file(filename=f"FINISH_{task_uniqname}")


execute_tasks.main = patched_main

variant = os.environ.get("ALL41_HOUSE_VARIANT", "large")
configs = {
    "large": (
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all41_house_large",
        "all41villa_large_011",
    ),
    "small_a": (
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all41_house_small_a",
        "all41villa_small_a_017",
    ),
    "small_b": (
        f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all41_house_small_b",
        "all41villa_small_b_023",
    ),
}
if variant not in configs:
    raise ValueError(
        f"Unknown ALL41_HOUSE_VARIANT={variant!r}; expected one of {sorted(configs)}"
    )

output_folder, seed = configs[variant]
# Residential generators may request a fresh native Indoor solve in their own
# output tree.  Keeping this override here means the urban entry invokes the
# real compose_indoors pipeline instead of copying or patching an old blend.
output_folder = os.environ.get("INFINIGEN_INDOOR_OUTPUT", output_folder)
seed = os.environ.get("INFINIGEN_INDOOR_SEED", seed)
print(
    f"[all41 indoor] variant={variant} output={output_folder} seed={seed}", flush=True
)
gin_configs = [
    "base_indoors",
    os.environ.get("INFINIGEN_INDOOR_SOLVE_CONFIG", "fast_solve"),
]
if variant.startswith("small_"):
    gin_configs.append("singleroom")

sys.argv = [
    "generate_indoors",
    "--output_folder",
    output_folder,
    "-s",
    seed,
    "-t",
    "coarse",
    "-g",
    *gin_configs,
]

runpy.run_module("infinigen_examples.generate_indoors", run_name="__main__")

# Blender can exit with status 0 even after a Python traceback. Emit a marker
# only after the genuine compose_indoors entrypoint returns successfully; the
# production shell driver requires a fresh marker and a fresh scene.blend.
success_marker = Path(output_folder) / "all45_09_indoor_success.json"
success_marker.write_text(
    json.dumps(
        {
            "output_folder": str(Path(output_folder).resolve()),
            "seed": seed,
            "variant": variant,
            "role": os.environ.get("INFINIGEN_INDOOR_ROLE", ""),
            "solve_config": os.environ.get(
                "INFINIGEN_INDOOR_SOLVE_CONFIG", "fast_solve"
            ),
            "completed_at_epoch": time.time(),
        },
        indent=2,
        sort_keys=True,
    )
    + "\n",
    encoding="utf-8",
)
print(f"[all41 indoor] SUCCESS marker={success_marker}", flush=True)

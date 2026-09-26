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
import os
import runpy
import sys

import infinigen
import infinigen.core.execute_tasks as execute_tasks
from infinigen.core.util.logging import Timer, create_text_file


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

sys.argv = [
    "generate_indoors",
    "--output_folder",
    f"{_wb_WORLDBRIDGE_ROOT}/infinigen/outputs/urban_v3_all40_house",
    "-s",
    "all40villa007",
    "-t",
    "coarse",
    "-g",
    "base_indoors",
    "fast_solve",
]

runpy.run_module("infinigen_examples.generate_indoors", run_name="__main__")

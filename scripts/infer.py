#!/usr/bin/env python3
"""Generate a WorldBridge descriptor or run an existing scene pipeline."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldbridge.pipeline import SCENE_SCRIPTS, generate_scene, infer_descriptor
from worldbridge.urban.core import TOPOLOGIES


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--config", type=Path, help="Optional JSON inference configuration"
    )
    parser.add_argument("--mode", choices=["descriptor", *SCENE_SCRIPTS])
    parser.add_argument("--seed", type=int)
    parser.add_argument("--topology", choices=TOPOLOGIES)
    parser.add_argument("--prompt")
    parser.add_argument(
        "--output", type=Path, help="Descriptor JSON; stdout if omitted"
    )
    args = parser.parse_args()
    config = json.loads(args.config.read_text()) if args.config else {}
    allowed = {"mode", "seed", "topology", "prompt", "output"}
    if not isinstance(config, dict) or config.keys() - allowed:
        parser.error(
            "Configuration must be an object containing only: "
            + ", ".join(sorted(allowed))
        )
    config.update(
        {k: v for k, v in vars(args).items() if k in allowed and v is not None}
    )
    mode = config.get("mode", "descriptor")
    if mode not in ["descriptor", *SCENE_SCRIPTS]:
        parser.error(f"Unknown mode: {mode}")
    if mode != "descriptor":
        if not config.get("prompt"):
            parser.error("--prompt is required for scene generation")
        if config.get("output") or config.get("topology") or "seed" in config:
            parser.error(
                "--output, --seed and --topology apply only to descriptor mode; scene defaults are defined by the existing scripts"
            )
        return generate_scene(mode, config["prompt"])
    if config.get("topology") not in (None, *TOPOLOGIES):
        parser.error("Unknown topology in configuration")
    result = infer_descriptor(config.get("seed", 42), config.get("topology"))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if config.get("output"):
        path = Path(config["output"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

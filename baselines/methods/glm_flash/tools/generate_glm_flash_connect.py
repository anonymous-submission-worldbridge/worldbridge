#!/usr/bin/env python3
"""Generate six connected indoor/outdoor scene blueprints with GLM-5.3 Flash.

The model is accessed only through the GLM Coding Plan OpenCode provider.  The
secret is accepted through ``GLM53_API_KEY`` and is never persisted.  Outputs
are resumable and confined below ``baselines/annotations/glm53_flash/connect``.
"""

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


import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request


BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
DEFAULT_OUTPUT = BASELINES / "annotations/glm53_flash/connect"
MODEL = "glm-coding-plan/glm-5.3-flash"
ENDPOINT = "https://open.bigmodel.cn/api/coding/paas/v4"

SCENES = (
    {
        "scene_id": "courtyard_cafe",
        "brief": "warm contemporary street-corner cafe opening through a broad glass door to a brick courtyard, sidewalk, trees, bicycles and mixed-use facades",
        "palette": "terracotta, cream plaster, walnut, forest green, aged brass",
    },
    {
        "scene_id": "garden_villa",
        "brief": "sunlit residential living room connected by open French doors to a lush garden terrace, quiet lane, neighboring villas and flowering trees",
        "palette": "ivory, pale oak, sage green, dusty rose, natural stone",
    },
    {
        "scene_id": "bookshop_arcade",
        "brief": "intimate independent bookshop whose entrance opens into a covered urban arcade with storefronts, benches, street lamps and a small plaza",
        "palette": "deep teal, dark oak, burgundy, warm amber, charcoal stone",
    },
    {
        "scene_id": "coastal_bungalow",
        "brief": "airy coastal bungalow dining room connected to a timber deck, sandy path, dune plants, palms and glimpses of a seaside promenade",
        "palette": "whitewash, turquoise, light rattan, sand, ocean blue",
    },
    {
        "scene_id": "mountain_lodge",
        "brief": "cozy timber lodge lounge opening directly to a stone patio, pine forest road, cabins, rocks and distant mountain forms",
        "palette": "cedar, slate, moss green, rust, warm firelight",
    },
    {
        "scene_id": "gallery_plaza",
        "brief": "minimal art gallery lobby with a seamless accessible entrance to a modern civic plaza, sculptures, planters, offices and transit shelter",
        "palette": "off-white, concrete gray, cobalt, brushed steel, vivid red accents",
    },
)


def utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def confined(path: Path) -> Path:
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def prompt_for(scene: dict[str, str]) -> str:
    return f"""You are the procedural scene-planning component of a 3D generation benchmark.
Create one detailed but efficient Blender scene blueprint for this concept:

SCENE_ID: {scene['scene_id']}
CONCEPT: {scene['brief']}
PALETTE: {scene['palette']}

The scene MUST be one genuine, continuous, shared-coordinate 3D environment:
- Blender coordinates use X left/right, Y indoor-to-outdoor, Z up.
- Interior spans approximately x=-6..6, y=-9..0 and has floor, ceiling and walls.
- Exterior spans approximately x=-14..14, y=0..20.
- A physically open, unobstructed entrance centered at x=0 in the y=0 facade
  must connect both regions. Door clear width must be at least 2.2 m and the
  floor/threshold must be flush enough for a walking camera to cross.
- Furnish the interior richly without obstructing a 1.2 m-wide path from
  (0,-7.5,0) to (0,4,0). Build a recognizable exterior streetscape/landscape.
- Include at least 22 purposeful objects total, semantic variety, layered
  depth, coherent colors, and architectural detail. Avoid text and logos.
- No external assets, files, downloads, image textures, booleans, geometry
  nodes, or expensive simulations. Use primitives only.

Return EXACTLY one JSON object with exactly one key named \"code\". The value
must be valid Python source that defines SCENE_SPEC and build_scene(api).
Do not use markdown fences or prose. Do not import anything and do not do file
I/O. The function must only call the following safe API methods:

api.mat(name, color_rgb, metallic=0.0, roughness=0.5, emission=0.0)
api.box(name, location_xyz, scale_xyz, material, bevel=0.04)
api.cylinder(name, location_xyz, radius, depth, material, vertices=16)
api.sphere(name, location_xyz, scale_xyz, material, segments=20)
api.arch(name, location_xyz, width, height, depth, material)
api.table(name, location_xyz, size_xyz, top_material, leg_material)
api.chair(name, location_xyz, yaw_degrees, material, accent_material)
api.sofa(name, location_xyz, yaw_degrees, size_xyz, material, accent_material)
api.shelf(name, location_xyz, size_xyz, frame_material, item_material)
api.tree(name, location_xyz, trunk_height, crown_radius, trunk_material, leaf_material)
api.lamp(name, location_xyz, height, pole_material, light_material)
api.art(name, location_xyz, scale_xyz, material, frame_material)
api.rug(name, location_xyz, size_xy, material)
api.road(name, location_xyz, size_xyz, road_material, line_material)

SCENE_SPEC must be a plain dictionary containing scene_id, concept, palette,
entrance_clear_width_m, and object_intent (a list of concise semantic labels).
build_scene(api) must create materials first and then all scene geometry. Keep
primitive counts between 70 and 220. Use unique object names. The facade at
y=0 must be made of separate left/right/top pieces so the entrance is truly
open; never place any box across the opening below z=2.8. Include interior
floor/ceiling/side/back walls, exterior ground, and exterior context. Do not
create cameras, lights, worlds, render settings, save operations, or exports;
the benchmark harness owns those.
"""


def extract_code(events_path: Path) -> tuple[str, dict[str, object]]:
    events = []
    text_parts = []
    for line in events_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        events.append(event)
        if event.get("type") == "text":
            text_parts.append(event.get("part", {}).get("text", ""))
    text = "".join(text_parts).strip()
    decoder = json.JSONDecoder()
    candidates = []
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S | re.I)
    if fenced:
        candidates.append(fenced.group(1))
    for index, character in enumerate(text):
        if character != "{":
            continue
        try:
            value, _ = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        candidates.append(value)
    payload = None
    for candidate in candidates:
        try:
            value = json.loads(candidate) if isinstance(candidate, str) else candidate
        except json.JSONDecodeError:
            continue
        if (
            isinstance(value, dict)
            and set(value) == {"code"}
            and isinstance(value["code"], str)
        ):
            payload = value
            break
    if payload is None:
        raise ValueError("response did not contain exactly one JSON code field")
    metadata: dict[str, object] = {
        "event_types": [event.get("type") for event in events],
        "session_ids": sorted(
            {event.get("sessionID") for event in events if event.get("sessionID")}
        ),
    }
    finishes = [event for event in events if event.get("type") == "step_finish"]
    if finishes:
        metadata["usage"] = finishes[-1].get("part", {}).get("tokens", {})
        metadata["finish_reason"] = finishes[-1].get("part", {}).get("reason")
    return payload["code"].rstrip() + "\n", metadata


def validate_code(code: str, scene_id: str) -> dict[str, object]:
    tree = ast.parse(code)
    forbidden_names = {
        "open",
        "exec",
        "eval",
        "compile",
        "__import__",
        "getattr",
        "setattr",
        "input",
    }
    forbidden_attrs = {
        "save_as_mainfile",
        "open_mainfile",
        "libraries",
        "handlers",
        "preferences",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name != "math" for alias in node.names):
                raise ValueError("only an optional math import is permitted")
        if isinstance(node, ast.ImportFrom):
            if node.module != "math" or node.level:
                raise ValueError("only an optional math import is permitted")
        if isinstance(node, ast.Name) and node.id in forbidden_names:
            raise ValueError(f"forbidden name: {node.id}")
        if isinstance(node, ast.Attribute) and (
            node.attr.startswith("__") or node.attr in forbidden_attrs
        ):
            raise ValueError(f"forbidden attribute: {node.attr}")
    namespace: dict[str, object] = {"__builtins__": {"__import__": __import__}}
    exec(compile(tree, "<glm53_flash_scene>", "exec"), namespace)
    spec = namespace.get("SCENE_SPEC")
    function = namespace.get("build_scene")
    if not isinstance(spec, dict) or spec.get("scene_id") != scene_id:
        raise ValueError("SCENE_SPEC scene_id mismatch")
    if not callable(function):
        raise ValueError("build_scene(api) is missing")
    if float(spec.get("entrance_clear_width_m", 0.0)) < 2.2:
        raise ValueError("entrance_clear_width_m is too small")
    return spec


def model_environment(cache_root: Path) -> dict[str, str]:
    secret = os.environ.get("GLM53_API_KEY", "").strip()
    if not secret:
        raise RuntimeError("GLM53_API_KEY must be supplied in the process environment")
    environment = dict(os.environ)
    environment.update(
        GLM53_API_KEY=secret,
        XDG_DATA_HOME=str(cache_root / "data"),
        XDG_CONFIG_HOME=str(cache_root / "config"),
        XDG_CACHE_HOME=str(cache_root / "cache"),
        XDG_STATE_HOME=str(cache_root / "state"),
        OPENCODE_DISABLE_AUTOUPDATE="1",
        OPENCODE_DISABLE_MODELS_FETCH="1",
        OPENCODE_DISABLE_DEFAULT_PLUGINS="1",
        OPENCODE_DISABLE_LSP_DOWNLOAD="1",
        OPENCODE_DISABLE_TERMINAL_TITLE="1",
        OPENCODE_EXPERIMENTAL_DISABLE_FILEWATCHER="1",
        OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX="65536",
    )
    environment.pop("ANTHROPIC_AUTH_TOKEN", None)
    environment.pop("ANTHROPIC_API_KEY", None)
    return environment


def direct_coding_plan_call(
    prompt: str, environment: dict[str, str], response_path: Path
) -> tuple[str, dict[str, object]]:
    payload = {
        "model": "glm-5.3-flash",
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "temperature": 0.65,
        "max_tokens": 32768,
        "thinking": {"type": "disabled"},
    }
    request = urllib.request.Request(
        ENDPOINT + "/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + environment["GLM53_API_KEY"],
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "WorldBridge-GLM53-Connect/1.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=1200) as response:
            raw = response.read()
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Coding Plan HTTP {error.code}: {body[:1200]}") from error
    value = json.loads(raw)
    response_path.write_bytes(
        json.dumps(value, indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
    )
    return parse_direct_response(value, response_path)


def parse_direct_response(
    value: dict[str, object], response_path: Path
) -> tuple[str, dict[str, object]]:
    choices = value.get("choices") or []
    if len(choices) != 1:
        raise ValueError("Coding Plan response did not contain exactly one choice")
    message = choices[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") for part in content if isinstance(part, dict)
        )
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Coding Plan response contained no text content")
    # Reuse the robust JSON/code extraction by presenting one synthetic text event.
    synthetic = response_path.with_suffix(".events.jsonl")
    synthetic.write_text(
        json.dumps({"type": "text", "part": {"text": content}}) + "\n", encoding="utf-8"
    )
    try:
        code, parsed = extract_code(synthetic)
    finally:
        synthetic.unlink(missing_ok=True)
    metadata = {
        "response_id": value.get("id"),
        "model_returned": value.get("model"),
        "finish_reason": choices[0].get("finish_reason"),
        "usage": value.get("usage", {}),
        **parsed,
    }
    return code, metadata


def generate_one(
    scene: dict[str, str], output: Path, force: bool, transport: str
) -> dict[str, object]:
    scene_root = output / scene["scene_id"]
    source_path = scene_root / "source/generated.py"
    manifest_path = scene_root / "generation_manifest.json"
    prompt = prompt_for(scene)
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    if not force and source_path.is_file() and manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (
            manifest.get("generation_success")
            and manifest.get("prompt_sha256") == prompt_hash
        ):
            validate_code(source_path.read_text(encoding="utf-8"), scene["scene_id"])
            print(
                f"GLM53_CONNECT_GENERATION_REUSE scene={scene['scene_id']}", flush=True
            )
            return manifest

    scene_root.mkdir(parents=True, exist_ok=True)
    work = scene_root / "work"
    work.mkdir(exist_ok=True)
    shutil.copyfile(
        (BASELINES / "methods/glm_flash/protocol/generation/glm53_flash_opencode.json"),
        work / "opencode.json",
    )
    logs = scene_root / "logs/generation_01"
    logs.mkdir(parents=True, exist_ok=True)
    events_path = logs / "events.jsonl"
    stderr_path = logs / "stderr.log"
    cache_root = BASELINES / "cache/glm53_connect_opencode"
    environment = model_environment(cache_root)
    started = utc()
    print(f"GLM53_CONNECT_GENERATION_START scene={scene['scene_id']}", flush=True)
    if transport == "opencode":
        command = [
            "opencode",
            "run",
            "--pure",
            "--model",
            MODEL,
            "--agent",
            "scene",
            "--format",
            "json",
            "--title",
            f"glm53-connect-{scene['scene_id']}",
            prompt,
        ]
        with events_path.open("w", encoding="utf-8") as stdout, stderr_path.open(
            "w", encoding="utf-8"
        ) as stderr:
            completed = subprocess.run(
                command,
                cwd=work,
                env=environment,
                stdout=stdout,
                stderr=stderr,
                text=True,
                timeout=1200,
                check=False,
            )
        if completed.returncode != 0:
            raise RuntimeError(
                f"OpenCode failed for {scene['scene_id']} (exit {completed.returncode}); see {events_path}"
            )
        code, response = extract_code(events_path)
    else:
        response_path = logs / "response.json"
        if response_path.is_file() and not force:
            print(f"GLM53_CONNECT_RESPONSE_REUSE scene={scene['scene_id']}", flush=True)
            code, response = parse_direct_response(
                json.loads(response_path.read_text(encoding="utf-8")), response_path
            )
        else:
            code, response = direct_coding_plan_call(prompt, environment, response_path)
    persisted = list(logs.glob("*"))
    if any(
        environment["GLM53_API_KEY"] in path.read_text(errors="replace")
        for path in persisted
        if path.is_file()
    ):
        raise RuntimeError("secret appeared in persisted model logs")
    model_spec = validate_code(code, scene["scene_id"])
    source_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = source_path.with_suffix(".py.tmp")
    temporary.write_text(code, encoding="utf-8")
    temporary.replace(source_path)
    manifest = {
        "schema_version": 1,
        "method": "glm53_flash",
        "model_requested": "glm-5.3-flash",
        "provider": "glm-coding-plan",
        "endpoint": ENDPOINT,
        "billing_route": "GLM Coding Plan OpenCode provider",
        "transport": transport,
        "scene_id": scene["scene_id"],
        "brief": scene["brief"],
        "palette": scene["palette"],
        "started_at_utc": started,
        "completed_at_utc": utc(),
        "generation_success": True,
        "prompt_sha256": prompt_hash,
        "generated_code_sha256": sha256(source_path),
        "generated_scene_spec": model_spec,
        "response": response,
        "opencode_version": subprocess.check_output(
            ["opencode", "--version"], text=True
        ).strip(),
        "secret_persisted": False,
    }
    atomic_json(manifest_path, manifest)
    print(f"GLM53_CONNECT_GENERATION_COMPLETE scene={scene['scene_id']}", flush=True)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--only", action="append", default=[])
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--transport", choices=("direct", "opencode"), default="direct")
    args = parser.parse_args()
    output = confined(args.output)
    selected = set(args.only)
    known = {scene["scene_id"] for scene in SCENES}
    if selected - known:
        parser.error(f"unknown scenes: {sorted(selected - known)}")
    output.mkdir(parents=True, exist_ok=True)
    manifests = [
        generate_one(scene, output, args.force, args.transport)
        for scene in SCENES
        if not selected or scene["scene_id"] in selected
    ]
    atomic_json(
        output / "GENERATION_MANIFEST.json",
        {
            "schema_version": 1,
            "method": "glm53_flash",
            "model": "glm-5.3-flash",
            "provider": "glm-coding-plan",
            "generated_at_utc": utc(),
            "scene_count": len(manifests),
            "expected_scene_count": len(SCENES),
            "scenes": [manifest["scene_id"] for manifest in manifests],
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

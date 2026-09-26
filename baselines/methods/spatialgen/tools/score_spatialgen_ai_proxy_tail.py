#!/usr/bin/env python3
"""Score completed SpatialGen scenes with a local VLM, explicitly as AI proxies."""
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
import base64
import csv
import hashlib
import io
import json
import shutil
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

BASELINES = _BASELINE_PROJECT_ROOT / "baselines"
sys.path.insert(0, str(BASELINES))
MODEL = "Qwen/Qwen3-VL-8B-Instruct"
SOURCE = "ai_proxy_qwen3_vl_8b_three_pass"
FIELDS = ("boundary_collision", "support_pose", "scale_density", "function_circulation")
SEEDS = (102, 203, 304)
LAYOUT_PROMPT = """Evaluate the visible spatial layout in this anonymous scene.
Image 1 contains eight high resolution anchor views. Image 2 contains all 50
walkthrough frames in row-major chronological order. Score each field 1 to 5:
boundary_collision: 1 widespread intersections/out-of-bounds objects, 3 a few
visible collisions, 5 no visible collisions; support_pose: 1 many floating or
unsupported objects, 3 a few questionable supports, 5 physically valid supports;
scale_density: 1 implausible scale or unusable clutter/emptiness, 3 mixed,
5 coherent scale and plausible density; function_circulation: 1 unusable function
or blocked circulation, 3 partly usable, 5 functional with clear movement.
Use 2 and 4 for intermediate cases. Do not reward photorealism as layout quality.
Do not infer invisible geometry. Return JSON with exactly two objects: "scores"
and "evidence". Both objects must have the four field names above as keys.
Each score is an integer; each evidence is a short description of what is visible.
"""
ALIGNMENT_PROMPT = """Evaluate only visible evidence for each preregistered fact.
Image 1 contains eight anchor views. Image 2 contains all 50 walkthrough frames
in row-major chronological order. Respond yes if visibly satisfied, no if
contradicted or absent despite adequate coverage, not-visible if coverage does
not support a decision. Do not infer facts from the prompt. Return JSON with
"responses" and "evidence" arrays in the original fact order, with exactly one
response and a short visible-evidence explanation per fact.
"""


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def write_csv(path, fields, rows):
    temp = path.with_suffix(".csv.tmp")
    with temp.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def atomic_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    temporary.replace(path)


def below_baselines(path):
    resolved = path.resolve()
    resolved.relative_to(BASELINES.resolve())
    return resolved


def sequence_sheet(paths):
    if len(paths) != 50:
        raise ValueError(f"Expected 50 walkthrough frames, found {len(paths)}")
    canvas = Image.new("RGB", (1600, 800), "black")
    draw = ImageDraw.Draw(canvas)
    for index, path in enumerate(paths):
        with Image.open(path) as source:
            tile = source.convert("RGB").resize((160, 160), Image.Resampling.LANCZOS)
        x, y = (index % 10) * 160, (index // 10) * 160
        canvas.paste(tile, (x, y))
        draw.rectangle((x, y, x + 24, y + 15), fill="black")
        draw.text((x + 2, y + 2), str(index), fill="white")
    output = io.BytesIO()
    canvas.save(output, format="JPEG", quality=90)
    return output.getvalue()


def validate_response(data, kind, fact_count):
    if kind == "layout":
        scores, evidence = data.get("scores", {}), data.get("evidence", {})
        if set(scores) != set(FIELDS) or set(evidence) != set(FIELDS):
            raise ValueError("Incomplete layout fields")
        if not all(type(v) is int and 1 <= v <= 5 for v in scores.values()):
            raise ValueError("Layout scores must be integers 1..5")
        descriptions = evidence.values()
    else:
        responses, descriptions = data.get("responses", []), data.get("evidence", [])
        if len(responses) != fact_count or len(descriptions) != fact_count:
            raise ValueError("Prompt response count does not match frozen facts")
        if not all(value in {"yes", "no", "not-visible"} for value in responses):
            raise ValueError("Invalid fact response")
    if not all(isinstance(value, str) and value.strip() for value in descriptions):
        raise ValueError("Every score must include visible-evidence notes")


def request_score(port, payload):
    # Loopback only: no remote API or external image transfer is used.
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=600) as response:
        return json.load(response)


def validate_formal_run(run, private_row):
    if not (run / "SUCCESS").is_file():
        raise RuntimeError(f"Stale rating package: {private_row['blind_id']}")
    manifest = json.loads((run / "run_manifest.json").read_text())
    expected = {
        "method": "spatialgen",
        "domain": private_row["domain"],
        "spec_id": private_row["spec_id"],
        "logical_seed": private_row["logical_seed"],
        "formal_terminal_status": "formal_success",
        "generation_success": True,
        "render_success": True,
    }
    for key, value in expected.items():
        if manifest.get(key) != value:
            raise RuntimeError(
                f"Formal run mismatch for {private_row['blind_id']}: "
                f"{key}={manifest.get(key)!r}, expected {value!r}"
            )


def preserve_blank_templates(package):
    for name in ("layout_ratings.csv", "prompt_ratings.csv"):
        source = package / name
        blank = package / name.replace(".csv", ".blank.csv")
        if not blank.exists():
            shutil.copyfile(source, blank)
        rows = read_csv(blank)
        score_fields = FIELDS if name.startswith("layout") else ("response",)
        if any(
            any((row.get(field) or "").strip() for field in score_fields)
            for row in rows
        ):
            raise RuntimeError(f"Preserved template is not blank: {blank}")


def score_package(package, port, start_index, end_index, raw_only):
    all_items = read_csv(package / "items.csv")
    private = json.loads((package / "PRIVATE_blind_map.json").read_text())["items"]
    if len(all_items) != 100 or len(private) != 100:
        raise ValueError("Expected a completed 100-scene SpatialGen package")
    if any(row["method"] != "spatialgen" or not row["success"] for row in private):
        raise ValueError("Expected 100 successful SpatialGen formal runs")
    preserve_blank_templates(package)
    mapping = {row["blind_id"]: row for row in private}
    model_manifest = (
        BASELINES / "hyworld2_runtime/manifests/qwen3_vl_8b_modelscope.json"
    )
    model_manifest_hash = hashlib.sha256(model_manifest.read_bytes()).hexdigest()
    layout_rows, prompt_rows = [], []
    ordered_items = sorted(all_items, key=lambda row: row["blind_id"])
    items = ordered_items[start_index:end_index]
    if not raw_only or not items:
        raise ValueError("This helper is restricted to a nonempty raw-only shard")
    for item in items:
        item_id = item["blind_id"]
        run = below_baselines(Path(mapping[item_id]["run_dir"]))
        facts = json.loads(item["required_facts_json"])
        validate_formal_run(run, mapping[item_id])
        anchor = below_baselines(package / item["montage"]).read_bytes()
        sequence_paths = sorted((run / "renders/sequence").glob("rgb_*.png"))
        sequence = sequence_sheet(sequence_paths)
        image_hashes = [hashlib.sha256(data).hexdigest() for data in (anchor, sequence)]
        image_content = [
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64," + base64.b64encode(data).decode()
                },
            }
            for data in (anchor, sequence)
        ]

        def score_pass(pass_index, seed):
            rater = f"ai_proxy_pass_{pass_index:02d}"
            pass_results = {}
            for kind in ("layout", "alignment"):
                prompt = LAYOUT_PROMPT + f"\nDomain: {item['domain']}"
                if kind == "alignment":
                    prompt = (
                        ALIGNMENT_PROMPT
                        + "\n"
                        + json.dumps(
                            {"prompt": item["prompt_en"], "facts": facts},
                            ensure_ascii=False,
                        )
                    )
                output = package / "ai_proxy_raw" / item_id / f"{rater}_{kind}.json"
                # Keep every already-valid response under its original signed
                # settings. New alignment responses get more room after one
                # observed 1,536-token truncation of otherwise valid evidence.
                max_tokens = (
                    3072 if kind == "alignment" and not output.is_file() else 1536
                )
                settings = {
                    "model": MODEL,
                    "temperature": 0.2,
                    "top_p": 0.9,
                    "seed": seed,
                    "max_tokens": max_tokens,
                    "response_format": {"type": "json_object"},
                }
                signature = hashlib.sha256(
                    json.dumps(
                        {
                            "settings": settings,
                            "prompt": prompt,
                            "images": image_hashes,
                            "model_manifest_sha256": model_manifest_hash,
                        },
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                if output.is_file():
                    record = json.loads(output.read_text())
                    if record.get("input_signature") != signature:
                        raise RuntimeError(
                            f"Refusing to reuse changed proxy inputs: {output}"
                        )
                    data = record["parsed"]
                else:
                    payload = {
                        **settings,
                        "messages": [
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": prompt},
                                    *image_content,
                                ],
                            }
                        ],
                    }
                    last_error = None
                    for _ in range(3):
                        raw = request_score(port, payload)
                        raw_directory = output.parent / "attempts"
                        attempt = (
                            len(list(raw_directory.glob(f"{output.stem}_*.json"))) + 1
                        )
                        attempt_path = (
                            raw_directory / f"{output.stem}_{attempt:02d}.json"
                        )
                        attempt_record = {
                            "input_signature": signature,
                            "settings": settings,
                            "prompt": prompt,
                            "image_sha256": image_hashes,
                            "created_at_utc": datetime.now(timezone.utc).isoformat(),
                            "raw_response": raw,
                        }
                        try:
                            data = json.loads(raw["choices"][0]["message"]["content"])
                            validate_response(data, kind, len(facts))
                        except (
                            json.JSONDecodeError,
                            KeyError,
                            IndexError,
                            TypeError,
                            ValueError,
                        ) as error:
                            last_error = error
                            attempt_record["validation_error"] = repr(error)
                            atomic_json(attempt_path, attempt_record)
                            continue
                        attempt_record["validation_ok"] = True
                        atomic_json(attempt_path, attempt_record)
                        atomic_json(
                            output,
                            {
                                "rating_source": SOURCE,
                                "human_raters": 0,
                                "input_signature": signature,
                                "image_sha256": image_hashes,
                                "prompt": prompt,
                                "settings": settings,
                                "model_manifest_sha256": model_manifest_hash,
                                "created_at_utc": datetime.now(
                                    timezone.utc
                                ).isoformat(),
                                "parsed": data,
                                "raw_response": raw,
                            },
                        )
                        break
                    else:
                        raise RuntimeError(
                            f"Three invalid proxy responses for {item_id} {rater} {kind}"
                        ) from last_error
                validate_response(data, kind, len(facts))
                pass_results[kind] = data
            return pass_index, rater, pass_results

        # The three explicitly labelled proxy passes are independent requests and
        # can be batched by vLLM without changing their seeds or saved evidence.
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = [
                executor.submit(score_pass, pass_index, seed)
                for pass_index, seed in enumerate(SEEDS, 1)
            ]
            results = [future.result() for future in futures]
        for pass_index, rater, pass_results in results:
            layout_rows.append(
                {
                    "rater_id": rater,
                    "blind_id": item_id,
                    **pass_results["layout"]["scores"],
                }
            )
            prompt_rows.extend(
                {
                    "rater_id": rater,
                    "blind_id": item_id,
                    "fact_index": index,
                    "fact": fact,
                    "response": pass_results["alignment"]["responses"][index],
                }
                for index, fact in enumerate(facts)
            )
            print(f"AI_PROXY_SCORED item={item_id} pass={pass_index}", flush=True)
    print(
        f"AI_PROXY_RAW_SHARD_COMPLETE start={start_index} end={end_index} "
        f"items={len(items)}",
        flush=True,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--gpu", type=int, default=0)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--start-index", type=int, required=True)
    parser.add_argument("--end-index", type=int, required=True)
    parser.add_argument("--raw-only", action="store_true", required=True)
    parser.add_argument("--external-llm", action="store_true")
    args = parser.parse_args()
    package = below_baselines(args.package)
    import baselines.methods.hyworld.run as matrix

    if args.model_root is not None:
        model_root = args.model_root.resolve()
        if not (model_root / "config.json").is_file():
            raise RuntimeError(f"Incomplete local model cache: {model_root}")
        matrix.QWEN_ROOT = model_root
    private = json.loads((package / "PRIVATE_blind_map.json").read_text())["items"]
    domains = {row["domain"] for row in private}
    if len(domains) != 1:
        raise ValueError("One domain per proxy package is required")
    if len(private) != 100 or any(row.get("method") != "spatialgen" for row in private):
        raise ValueError("Expected one complete SpatialGen domain package")
    process = None
    try:
        if args.external_llm:
            if not matrix.llm_health(args.port):
                raise RuntimeError("Local VLM is not healthy")
        else:
            if matrix.gpu_free_mib(args.gpu) < 30000:
                raise RuntimeError("AI proxy server requires at least 30,000 MiB free")
            original_vllm_environment = matrix.vllm_environment

            def isolated_vllm_environment(gpu):
                environment = original_vllm_environment(gpu)
                environment["CODEX_VLLM_NVML_VISIBLE_ONLY"] = "1"
                environment["PYTHONPATH"] = str(
                    BASELINES / "tools/vllm_nvml_visible_only"
                )
                return environment

            matrix.vllm_environment = isolated_vllm_environment
            process, _ = matrix.start_vllm(args.gpu, args.port, 16384, 900)
        score_package(
            package, args.port, args.start_index, args.end_index, args.raw_only
        )
    finally:
        if process is not None:
            matrix.stop_process_group(process)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

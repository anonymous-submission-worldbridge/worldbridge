#!/usr/bin/env python
import json
import os
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from worldbridge.llm_config import (
    complete_text,
    describe_llm_exception,
    get_llm_config,
    make_openai_client,
)


TESTS = [
    {
        "name": "minimal_chat",
        "messages": [
            {"role": "user", "content": "Reply with exactly OK."},
        ],
        "kwargs": {"temperature": 0},
    },
    {
        "name": "simple_json_text",
        "messages": [
            {
                "role": "user",
                "content": 'Return only this JSON object: {"ok": true}',
            },
        ],
        "kwargs": {"temperature": 0},
    },
    {
        "name": "simple_json_response_format",
        "messages": [
            {
                "role": "user",
                "content": 'Return a JSON object with one key "ok" set to true.',
            },
        ],
        "kwargs": {"temperature": 0, "response_format": {"type": "json_object"}},
    },
    {
        "name": "scene_short_prompt",
        "messages": [
            {
                "role": "system",
                "content": (
                    "You convert a natural language scene description into a compact "
                    "JSON manifest for a procedural 3D scene generator."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Create a misty autumn forest with dense fog, moving trees, "
                    "drifting leaves, and soft animated haze. Return only JSON."
                ),
            },
        ],
        "kwargs": {"temperature": 0.2},
    },
    {
        "name": "planner_like_terms",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON. Valid scene fields include season, weather, "
                    "terrain, ecosystem, vegetation, creatures, surface coverage, "
                    "particles, wind, turbulence, rocks, boulders, river, lake, "
                    "forest, cave, desert, arctic, snow, rain, fog, leaves."
                ),
            },
            {
                "role": "user",
                "content": (
                    "User Instruction: Create a misty autumn forest with dense fog, "
                    "moving trees, drifting leaves, and soft animated haze."
                ),
            },
        ],
        "kwargs": {"temperature": 0.2},
    },
]


def candidate_models(config_model):
    raw = os.getenv("LEGACYWORLD_DIAG_MODELS")
    if raw:
        models = [item.strip() for item in raw.split(",") if item.strip()]
    else:
        models = [config_model]
    deduped = []
    for model in models:
        if model not in deduped:
            deduped.append(model)
    return deduped


def print_exception(exc):
    print("FAIL")
    print(describe_llm_exception(exc))


def proxy_summary():
    names = [
        "http_proxy",
        "https_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
        "all_proxy",
    ]
    configured = [name for name in names if os.getenv(name)]
    if not configured:
        return "system proxy env not set"
    return "using system proxy env: " + ", ".join(configured)


def key_summary(config):
    key = config.api_key
    return {
        "source": config.api_key_source,
        "length": len(key),
        "prefix": key[:3],
        "suffix": key[-4:],
        "has_surrounding_whitespace": key != key.strip(),
    }


def raw_http_client():
    ignore_proxy = os.getenv("LEGACYWORLD_IGNORE_PROXY", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }
    return httpx.Client(timeout=60, trust_env=not ignore_proxy)


def raw_post_responses(config, model):
    url = config.base_url.rstrip("/") + "/responses"
    payload = {
        "model": model,
        "input": "Reply with exactly OK.",
        "max_output_tokens": 16,
        "store": False,
        "reasoning": {"effort": config.reasoning_effort or "high"},
    }
    headers = {
        "Authorization": f"Bearer {config.api_key.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": os.getenv("LEGACYWORLD_USER_AGENT", "codex"),
    }
    with raw_http_client() as client:
        response = client.post(url, headers=headers, json=payload)
    return response


def main():
    config = get_llm_config()
    client = make_openai_client(config)

    print("LLM diagnostic")
    print(f"provider: {config.provider}")
    print(f"base_url: {config.base_url or 'OpenAI default'}")
    print(f"model: {config.model}")
    print(f"wire_api: {config.wire_api}")
    print(f"reasoning_effort: {config.reasoning_effort or '(unset)'}")
    print(f"disable_response_storage: {config.disable_response_storage}")
    print("api_key: configured (hidden)")
    print(f"api_key_source: {config.api_key_source}")
    print(f"api_key_debug: {json.dumps(key_summary(config), ensure_ascii=False)}")
    if os.getenv("LEGACYWORLD_IGNORE_PROXY", "0").lower() in {"1", "true", "yes", "on"}:
        print("proxy: ignored because LEGACYWORLD_IGNORE_PROXY is enabled")
    else:
        print(f"proxy: {proxy_summary()}")
    print(f"candidate_models: {', '.join(candidate_models(config.model))}")
    print("extended_sdk_tests: set LEGACYWORLD_DIAG_EXTENDED=1 to run SDK/chat checks")
    print()

    failures = 0
    critical_failures = 0

    print("== raw_http_responses_by_model ==")
    for model in candidate_models(config.model):
        print(f"-- {model} --")
        try:
            response = raw_post_responses(config, model)
            print(f"status_code: {response.status_code}")
            print(response.text[:1000])
            if response.status_code >= 400:
                failures += 1
                critical_failures += 1
        except Exception as exc:
            failures += 1
            critical_failures += 1
            print_exception(exc)
    print()

    print("== project_wire_minimal_by_model ==")
    for model in candidate_models(config.model):
        print(f"-- {model} --")
        try:
            content = complete_text(
                client,
                model=model,
                messages=[{"role": "user", "content": "Reply with exactly OK."}],
                temperature=0,
                max_tokens=16,
            )
            print("OK")
            print(content[:1000])
        except Exception as exc:
            failures += 1
            critical_failures += 1
            print_exception(exc)
    print()

    if os.getenv("LEGACYWORLD_DIAG_EXTENDED", "0").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }:
        print("== models_list ==")
        try:
            models = client.models.list()
            model_ids = [item.id for item in getattr(models, "data", [])]
            print("OK")
            print("\n".join(model_ids[:50]) if model_ids else "(no model ids returned)")
        except Exception as exc:
            failures += 1
            print_exception(exc)
        print()

        print("== responses_minimal_by_model ==")
        for model in candidate_models(config.model):
            print(f"-- {model} --")
            try:
                response = client.responses.create(
                    model=model,
                    input="Reply with exactly OK.",
                    max_output_tokens=16,
                )
                print("OK")
                print((getattr(response, "output_text", "") or str(response))[:1000])
            except Exception as exc:
                failures += 1
                print_exception(exc)
        print()

        print("== chat_minimal_by_model ==")
        for model in candidate_models(config.model):
            print(f"-- {model} --")
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": "Reply with exactly OK."}],
                    temperature=0,
                )
                content = response.choices[0].message.content
                print("OK")
                print((content or "").strip()[:1000])
            except Exception as exc:
                failures += 1
                print_exception(exc)
        print()

        for test in TESTS:
            print(f"== {test['name']} ==")
            try:
                response = client.chat.completions.create(
                    model=config.model,
                    messages=test["messages"],
                    **test["kwargs"],
                )
                content = response.choices[0].message.content
                print("OK")
                print((content or "").strip()[:1000])
            except Exception as exc:
                failures += 1
                print("FAIL")
                print(describe_llm_exception(exc))
            print()

    print(
        json.dumps(
            {
                "critical_failures": critical_failures,
                "all_failures_including_optional": failures,
            },
            indent=2,
        )
    )
    raise SystemExit(1 if critical_failures else 0)


if __name__ == "__main__":
    main()

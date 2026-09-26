import os
from dataclasses import dataclass

import httpx
from openai import OpenAI

SAYMYCODE_BASE_URL = "https://saymycode.xyz/v1"
OPENAI_DEFAULT_MODEL = "gpt-4o"
SAYMYCODE_DEFAULT_MODEL = "gpt-5.5"


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    api_key_source: str
    base_url: str | None
    model: str
    provider: str
    wire_api: str
    reasoning_effort: str | None
    disable_response_storage: bool


def _first_env(*names: str) -> str | None:
    return _first_env_with_name(*names)[0]


def _first_env_with_name(*names: str) -> tuple[str | None, str | None]:
    for name in names:
        candidates = (name,)
        if name.startswith("LEGACYWORLD_"):
            candidates = (name.replace("LEGACYWORLD_", "WORLDBRIDGE_", 1), name)
        for candidate in candidates:
            value = os.getenv(candidate)
            if value:
                return value, candidate
    return None, None


def _detect_provider(base_url: str | None, has_saymycode_env: bool) -> str:
    if has_saymycode_env:
        return "saymycode"
    if base_url and "saymycode.xyz" in base_url.lower():
        return "saymycode"
    if not base_url or "api.openai.com" in base_url.lower():
        return "openai"
    return "openai_compatible"


def get_llm_config(default_model: str | None = None) -> LLMConfig:
    base_url = _first_env(
        "OPENAI_BASE_URL",
        "SAYMYCODE_BASE_URL",
        "LEGACYWORLD_BASE_URL",
    )

    has_saymycode_env = bool(
        os.getenv("SAYMYCODE_API_KEY")
        or os.getenv("SAYMYCODE_BASE_URL")
        or os.getenv("SAYMYCODE_MODEL")
    )
    provider = _detect_provider(base_url, has_saymycode_env)

    if provider == "saymycode" and not base_url:
        base_url = SAYMYCODE_BASE_URL

    if provider == "saymycode":
        api_key, api_key_source = _first_env_with_name(
            "SAYMYCODE_API_KEY",
            "OPENAI_API_KEY",
            "LEGACYWORLD_API_KEY",
        )
    elif provider == "openai":
        api_key, api_key_source = _first_env_with_name(
            "OPENAI_API_KEY",
            "LEGACYWORLD_API_KEY",
            "SAYMYCODE_API_KEY",
        )
    else:
        api_key, api_key_source = _first_env_with_name(
            "LEGACYWORLD_API_KEY",
            "OPENAI_API_KEY",
            "SAYMYCODE_API_KEY",
        )

    provider_default_model = (
        SAYMYCODE_DEFAULT_MODEL if provider == "saymycode" else OPENAI_DEFAULT_MODEL
    )
    provider_default_wire_api = "responses" if provider == "saymycode" else "chat"
    model = (
        _first_env(
            "OPENAI_MODEL",
            "SAYMYCODE_MODEL",
            "LEGACYWORLD_MODEL",
        )
        or default_model
        or provider_default_model
    )
    wire_api = (
        _first_env("OPENAI_WIRE_API", "SAYMYCODE_WIRE_API", "LEGACYWORLD_WIRE_API")
        or provider_default_wire_api
    ).lower()
    reasoning_effort = _first_env(
        "OPENAI_REASONING_EFFORT",
        "SAYMYCODE_REASONING_EFFORT",
        "LEGACYWORLD_REASONING_EFFORT",
    ) or ("high" if provider == "saymycode" else None)
    disable_response_storage = (
        _first_env(
            "OPENAI_DISABLE_RESPONSE_STORAGE",
            "SAYMYCODE_DISABLE_RESPONSE_STORAGE",
            "LEGACYWORLD_DISABLE_RESPONSE_STORAGE",
        )
        or ("true" if provider == "saymycode" else "false")
    ).lower() in {"1", "true", "yes", "on"}

    if not api_key:
        raise RuntimeError(
            "No LLM API key configured. Set OPENAI_API_KEY, SAYMYCODE_API_KEY, "
            "or LEGACYWORLD_API_KEY."
        )

    return LLMConfig(
        api_key=api_key,
        api_key_source=api_key_source or "(unknown)",
        base_url=base_url or None,
        model=model,
        provider=provider,
        wire_api=wire_api,
        reasoning_effort=reasoning_effort,
        disable_response_storage=disable_response_storage,
    )


def build_openai_client(default_model: str | None = None) -> tuple[OpenAI, str]:
    config = get_llm_config(default_model=default_model)
    client = make_openai_client(config)
    return client, config.model


def _ignore_proxy_for_provider(provider: str) -> bool:
    value = (_first_env("LEGACYWORLD_IGNORE_PROXY") or "0").lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", "auto"}:
        return False
    return False


def make_openai_client(
    config: LLMConfig,
    api_key: str | None = None,
    base_url: str | None = None,
) -> OpenAI:
    kwargs = {
        "api_key": api_key or config.api_key,
        "base_url": base_url or config.base_url,
    }
    if _ignore_proxy_for_provider(config.provider):
        kwargs["http_client"] = httpx.Client(trust_env=False)
    client = OpenAI(**kwargs)
    client._worldbridge_config = config
    return client


def _raw_http_client() -> httpx.Client:
    return httpx.Client(timeout=120, trust_env=not _ignore_proxy_for_provider(""))


def _extract_response_text(data: dict) -> str:
    output_text = data.get("output_text")
    if output_text:
        return str(output_text).strip()

    texts = []
    for item in data.get("output", []):
        if item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if text:
                    texts.append(text)
    return "\n".join(texts).strip()


def _raw_responses_create(config: LLMConfig, payload: dict) -> dict:
    if not config.base_url:
        raise RuntimeError("Responses API requires a base_url for raw HTTP mode.")

    url = config.base_url.rstrip("/") + "/responses"
    headers = {
        "Authorization": f"Bearer {config.api_key.strip()}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": (_first_env("LEGACYWORLD_USER_AGENT") or "codex"),
    }
    with _raw_http_client() as http_client:
        response = http_client.post(url, headers=headers, json=payload)

    if response.status_code >= 400:
        raise RuntimeError(
            f"Responses API error {response.status_code}: {response.text[:2000]}"
        )
    return response.json()


def _message_content_to_responses_content(content):
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return str(content)

    converted = []
    for item in content:
        item_type = item.get("type")
        if item_type == "text":
            converted.append({"type": "input_text", "text": item.get("text", "")})
        elif item_type == "image_url":
            image_url = item.get("image_url", {})
            if isinstance(image_url, dict):
                image_url = image_url.get("url", "")
            converted.append({"type": "input_image", "image_url": image_url})
        else:
            converted.append({"type": "input_text", "text": str(item)})
    return converted


def _messages_to_responses_payload(messages):
    instructions = []
    inputs = []
    text_inputs = []
    has_multimodal = False
    for message in messages:
        role = message.get("role", "user")
        content = message.get("content", "")
        if role == "system":
            instructions.append(content if isinstance(content, str) else str(content))
            continue
        if isinstance(content, str):
            text_inputs.append((role, content))
            continue
        has_multimodal = True
        responses_role = "assistant" if role == "assistant" else "user"
        inputs.append(
            {
                "role": responses_role,
                "content": _message_content_to_responses_content(content),
            }
        )
    if not has_multimodal:
        if len(text_inputs) == 1:
            response_input = text_inputs[0][1]
        else:
            response_input = "\n\n".join(
                f"{role}: {content}" for role, content in text_inputs
            )
        return "\n\n".join(instructions) or None, response_input
    return "\n\n".join(instructions) or None, inputs


def complete_text(
    client: OpenAI,
    model: str,
    messages: list[dict],
    temperature: float | None = None,
    response_format: dict | None = None,
    max_tokens: int | None = None,
) -> str:
    config = getattr(client, "_worldbridge_config", None)
    wire_api = getattr(config, "wire_api", "chat")

    if wire_api == "responses":
        instructions, response_input = _messages_to_responses_payload(messages)
        payload = {
            "model": model,
            "input": response_input,
        }
        if instructions:
            payload["instructions"] = instructions
        if temperature is not None:
            payload["temperature"] = temperature
        if max_tokens is not None:
            payload["max_output_tokens"] = max_tokens
        if config and config.reasoning_effort:
            payload["reasoning"] = {"effort": config.reasoning_effort}
        if config and config.disable_response_storage:
            payload["store"] = False
        if response_format and response_format.get("type") == "json_object":
            payload["text"] = {"format": {"type": "json_object"}}

        if config and config.provider == "saymycode":
            return _extract_response_text(_raw_responses_create(config, payload))

        response = client.responses.create(**payload)
        return (getattr(response, "output_text", None) or "").strip()

    kwargs = {
        "model": model,
        "messages": messages,
    }
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    if response_format is not None:
        kwargs["response_format"] = response_format
    response = client.chat.completions.create(**kwargs)
    return (response.choices[0].message.content or "").strip()


def has_llm_api_key() -> bool:
    return bool(
        _first_env("OPENAI_API_KEY", "SAYMYCODE_API_KEY", "LEGACYWORLD_API_KEY")
    )


def describe_llm_exception(exc: Exception, max_body_chars: int = 2000) -> str:
    lines = [f"{exc.__class__.__name__}: {exc}"]

    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        lines.append(f"status_code: {status_code}")

    request_id = getattr(exc, "request_id", None)
    if request_id:
        lines.append(f"request_id: {request_id}")

    body = getattr(exc, "body", None)
    if body:
        lines.append(f"body: {str(body)[:max_body_chars]}")

    response = getattr(exc, "response", None)
    if response is not None:
        try:
            text = response.text
            if text:
                lines.append(f"response_text: {text[:max_body_chars]}")
        except Exception:
            pass

    return "\n".join(lines)

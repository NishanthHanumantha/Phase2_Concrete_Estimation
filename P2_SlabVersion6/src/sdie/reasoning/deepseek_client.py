from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from sdie.reasoning.env import get_deepseek_api_key

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"
DEFAULT_MODEL = "deepseek-chat"
REASONER_MODEL = "deepseek-reasoner"
DEFAULT_TIMEOUT_S = 120.0
REASONER_TIMEOUT_S = 180.0


def resolve_model(model: str, *, prefer_reasoner: bool = False) -> str:
    """auto → chat; upgrade to reasoner when prefer_reasoner (failed/ambiguous run)."""
    if model and model != "auto":
        return model
    return REASONER_MODEL if prefer_reasoner else DEFAULT_MODEL


class DeepSeekError(RuntimeError):
    pass


def chat_json(
    messages: list[dict[str, str]],
    *,
    model: str = DEFAULT_MODEL,
    base_url: str = DEFAULT_BASE_URL,
    temperature: float = 0.1,
    timeout_s: float | None = None,
) -> dict[str, Any]:
    """
    Call DeepSeek chat completions with JSON object response.
    Model: deepseek-chat (structured slab reasoning on drawing context).
    """
    api_key = get_deepseek_api_key()
    if not api_key:
        raise DeepSeekError(
            "DEEPSEEK_API_KEY not set. Add it to Phase2_Concrete_Estimation/.env"
        )

    resolved = resolve_model(model)
    if timeout_s is None:
        timeout_s = (
            REASONER_TIMEOUT_S
            if resolved == REASONER_MODEL
            else DEFAULT_TIMEOUT_S
        )

    url = f"{base_url.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": resolved,
        "messages": messages,
        "temperature": temperature,
    }
    if resolved != REASONER_MODEL:
        payload["response_format"] = {"type": "json_object"}
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise DeepSeekError(
                f"DeepSeek HTTP {resp.status_code}: {resp.text[:500]}"
            )
        data = resp.json()

    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise DeepSeekError(f"Unexpected DeepSeek response shape: {data}") from exc

    text = content.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        text = "\n".join(
            ln for ln in lines if not ln.strip().startswith("```")
        ).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise DeepSeekError(f"DeepSeek returned non-JSON content: {content[:300]}") from exc

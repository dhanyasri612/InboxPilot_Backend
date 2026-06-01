"""Groq client with automatic failover when a key hits rate limits."""

from __future__ import annotations

import os
import re
from typing import Any

from dotenv import load_dotenv
from groq import APIStatusError, Groq, RateLimitError

load_dotenv()

_EXHAUSTED_KEY_FINGERPRINTS: set[str] = set()

_PRIMARY_KEY_NAMES = (
    "GROQ_API_KEY",
    "GROQ_API_KEY1",
    "GROQ_API_KEY2",
    "GROQ_API_KEY3",
)


def _strip_key(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = value.strip()
    return cleaned or None


def load_groq_api_keys() -> list[str]:
    """Collect unique Groq keys from .env (GROQ_API_KEY, GROQ_API_KEY1, ...)."""
    keys: list[str] = []
    seen: set[str] = set()

    for name in _PRIMARY_KEY_NAMES:
        key = _strip_key(os.getenv(name))
        if key and key not in seen:
            keys.append(key)
            seen.add(key)

    numbered = []
    for env_name in os.environ:
        if re.fullmatch(r"GROQ_API_KEY\d+", env_name) and env_name not in _PRIMARY_KEY_NAMES:
            numbered.append(env_name)
    for env_name in sorted(numbered, key=lambda n: int(n.replace("GROQ_API_KEY", "") or "0")):
        key = _strip_key(os.environ.get(env_name))
        if key and key not in seen:
            keys.append(key)
            seen.add(key)

    return keys


def has_groq_keys() -> bool:
    return bool(load_groq_api_keys())


def is_rate_limit_error(error: Exception) -> bool:
    if isinstance(error, RateLimitError):
        return True
    if isinstance(error, APIStatusError) and getattr(error, "status_code", None) == 429:
        return True

    message = str(error).lower()
    markers = (
        "rate limit",
        "rate_limit",
        "429",
        "tokens per day",
        "tpd",
        "quota",
        "too many requests",
    )
    return any(marker in message for marker in markers)


def _key_fingerprint(api_key: str) -> str:
    return api_key[-8:] if len(api_key) >= 8 else api_key


def _keys_to_try() -> list[str]:
    all_keys = load_groq_api_keys()
    if not all_keys:
        return []

    available = [
        key for key in all_keys if _key_fingerprint(key) not in _EXHAUSTED_KEY_FINGERPRINTS
    ]
    if available:
        return available

    # All keys were marked exhausted this session; try again from the top.
    _EXHAUSTED_KEY_FINGERPRINTS.clear()
    return all_keys


def mark_key_exhausted(api_key: str) -> None:
    _EXHAUSTED_KEY_FINGERPRINTS.add(_key_fingerprint(api_key))


def reset_exhausted_keys() -> None:
    _EXHAUSTED_KEY_FINGERPRINTS.clear()


def chat_completions_create(
    *,
    messages: list[dict[str, Any]],
    model: str | None = None,
    temperature: float = 0,
    **kwargs: Any,
):
    """
    Call Groq chat completions, rotating to the next API key on rate-limit errors.
    """
    keys = _keys_to_try()
    if not keys:
        raise RuntimeError(
            "No Groq API keys configured. Set GROQ_API_KEY and/or GROQ_API_KEY1 in .env"
        )

    model_name = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    last_error: Exception | None = None

    for index, api_key in enumerate(keys):
        client = Groq(api_key=api_key)
        try:
            return client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
        except Exception as error:
            last_error = error
            if is_rate_limit_error(error):
                mark_key_exhausted(api_key)
                if index < len(keys) - 1:
                    continue
            raise

    raise last_error or RuntimeError("All Groq API keys are rate-limited")

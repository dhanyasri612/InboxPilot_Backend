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
    If all keys are exhausted, sleeps and retries.
    """
    import time

    model_name = model or os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    last_error: Exception | None = None

    # Try up to 3 main loops (each loop tries all available keys)
    for attempt in range(3):
        keys = _keys_to_try()
        if not keys:
            raise RuntimeError(
                "No Groq API keys configured. Set GROQ_API_KEY and/or GROQ_API_KEY1 in .env"
            )

        for api_key in keys:
            # Disable SDK internal retries (max_retries=0) so we can rotate keys instantly on rate limit errors
            client = Groq(api_key=api_key, max_retries=0)
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
                    # Rotate to next key
                    continue
                # For non-rate-limit errors (like syntax error or invalid model), raise immediately
                raise

        # If we reached here, all keys in `keys` were rate-limited in this attempt.
        # Wait a bit before retrying the next attempt loop (exponential backoff)
        if attempt < 2:
            sleep_time = (attempt + 1) * 3
            print(f"All Groq keys rate-limited. Retrying attempt {attempt+2}/3 in {sleep_time}s...")
            time.sleep(sleep_time)
            # Clear exhausted key fingerprints so we can try them again in the next loop
            reset_exhausted_keys()

    raise last_error or RuntimeError("All Groq API keys are rate-limited after multiple retries")


def generate_reply_draft(subject: str, sender: str, body: str, reply_type: str) -> str:
    """Generate a contextual email reply draft using the Groq LLM client."""
    intent_prompts = {
        "confirm_time": "confirm the proposed meeting, event, or interview time slot",
        "reschedule": "politely ask to reschedule the proposed meeting or interview slot to a different time",
        "decline": "politely decline the request, job offer, or inquiry gracefully",
        "inquiry": "ask for more details, clarify next steps, or request additional information"
    }

    intent_desc = intent_prompts.get(reply_type, "reply professionally and contextually")

    prompt = f"""You are a professional assistant writing an email draft response.
Write a response email that is concise, polite, and directly addresses the incoming email.

Incoming Email Details:
Sender: {sender}
Subject: {subject}
Body: {body}

Your Intent:
{intent_desc}

Guidelines:
- Return ONLY the raw body of the reply email draft.
- Do NOT include subject lines, formatting headers, or meta-commentary (like "Here is your draft:").
- Keep it under 150 words.
- Use square brackets for variables that need user input, like [My Name] or [Alternative Time].
- Be extremely professional and friendly.
"""

    messages = [
        {"role": "system", "content": "You are a professional email writing assistant. You write clean, direct, and professional email responses."},
        {"role": "user", "content": prompt}
    ]

    response = chat_completions_create(messages=messages, temperature=0.7)
    return response.choices[0].message.content.strip()


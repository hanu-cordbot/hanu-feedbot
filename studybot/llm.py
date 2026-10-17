"""Thin async wrapper over Gemini that always returns parsed JSON."""
import asyncio
import json
import logging
import re
from typing import Any, Optional

from google import genai
from google.genai import types

from . import config

log = logging.getLogger(__name__)

_client: Optional[genai.Client] = None
# /generate fans out over several passages; cap parallel calls to stay under rate limits.
_slots = asyncio.Semaphore(3)


def client() -> genai.Client:
    global _client
    if _client is None:
        if not config.GEMINI_API_KEY:
            raise RuntimeError("GEMINI_API_KEY is not set")
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


class LLMError(RuntimeError):
    pass


async def generate_json(
    prompt: str,
    *,
    system: str,
    audio: Optional[tuple[bytes, str]] = None,
    temperature: float = 0.7,
    tries: int = 3,
) -> Any:
    """Calls the generation model (falling back on rate limits) and parses its JSON reply.

    `audio` is an optional (bytes, mime_type) pair sent alongside the prompt; Gemini
    listens to it directly, so voice answers need no separate speech-to-text step.
    """
    contents: list[Any] = [prompt]
    if audio:
        contents.append(types.Part.from_bytes(data=audio[0], mime_type=audio[1]))
    cfg = types.GenerateContentConfig(
        system_instruction=system,
        temperature=temperature,
        response_mime_type="application/json",
    )
    models = [config.GENERATION_MODEL]
    if config.FALLBACK_MODEL and config.FALLBACK_MODEL != config.GENERATION_MODEL:
        models.append(config.FALLBACK_MODEL)

    last_error: Exception | None = None
    for model in models:
        for attempt in range(tries):
            try:
                async with _slots:
                    rsp = await client().aio.models.generate_content(model=model, contents=contents, config=cfg)
                return parse_json(rsp.text or "")
            except Exception as exc:  # SDK raises several error types; all are retryable here
                last_error = exc
                text = str(exc).lower()
                log.warning("Gemini %s failed (attempt %d/%d): %s", model, attempt + 1, tries, exc)
                if any(s in text for s in ("429", "quota", "rate", "resource_exhausted", "404", "not found")):
                    break  # move on to the fallback model rather than hammering this one
                await asyncio.sleep(2**attempt)
    raise LLMError(f"Gemini request failed: {last_error}")


def parse_json(text: str) -> Any:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, flags=re.S)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Model did not return valid JSON: {text[:200]!r}") from exc

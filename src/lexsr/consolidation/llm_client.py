"""
Shared LLM call helper for the consolidation pipeline.

DocumentClassifier and AmendmentParser both fall back to an LLM pass when
regex confidence is too low. Historically that meant a local Qwen model
served via vLLM's legacy `/v1/completions` endpoint. This module adds
support for OpenRouter (or any OpenAI-compatible `/chat/completions`
endpoint) alongside that, selected purely by URL shape:

- URL contains "chat/completions" -> chat payload, Bearer auth, message
  content is read from choices[0]["message"]["content"].
- Anything else (e.g. the local vLLM completions endpoint) -> legacy
  completions payload, no auth header unless an api_key is supplied,
  text is read from choices[0]["text"].

Stdlib only, matching the rest of the core pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DOTENV_PATH = _PROJECT_ROOT / ".env"


def _load_dotenv_value(key: str) -> Optional[str]:
    """Read a single KEY=VALUE from .env without adding a dependency."""
    if not _DOTENV_PATH.is_file():
        return None
    try:
        for line in _DOTENV_PATH.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            if name.strip() == key:
                return value.strip().strip('"').strip("'")
    except OSError:
        pass
    return None


def resolve_api_key(api_key: Optional[str], env_var: str = "OPENROUTER_API_KEY") -> Optional[str]:
    """Explicit key wins, then the environment, then .env in the repo root."""
    if api_key:
        return api_key
    return os.environ.get(env_var) or _load_dotenv_value(env_var)


def call_llm(
    prompt: str,
    llm_url: str,
    model: str,
    temperature: float,
    max_tokens: int,
    api_key: Optional[str] = None,
    timeout: int = 20,
) -> Optional[str]:
    """
    Call an LLM completion endpoint and return the raw generated text.

    Returns None on any network/parse failure so callers can fall back
    to their regex result.
    """
    is_chat = "chat/completions" in llm_url

    if is_chat:
        payload = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")
    else:
        payload = json.dumps({
            "model": model,
            "prompt": prompt,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    req = urllib.request.Request(llm_url, data=payload, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        text = (
            body["choices"][0]["message"]["content"]
            if is_chat
            else body["choices"][0]["text"]
        )
        if not text:
            logger.warning("LLM returned empty content (finish_reason=%s)",
                            body["choices"][0].get("finish_reason"))
            return None
        return text.strip()
    except (urllib.error.URLError, KeyError, IndexError, json.JSONDecodeError, OSError) as exc:
        logger.warning("LLM call failed: %s", exc)
        return None

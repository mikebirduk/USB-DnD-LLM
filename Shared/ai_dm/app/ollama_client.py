"""Minimal Ollama chat client (standard library only).

Talks to a locally running Ollama server over ``127.0.0.1`` and returns
the assistant's reply as a plain string. No cloud calls, no telemetry.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, List

# Local Ollama server only — never a remote host.
OLLAMA_HOST = "http://127.0.0.1:11434"
CHAT_ENDPOINT = f"{OLLAMA_HOST}/api/chat"

# Repo layout: Shared/ai_dm/app/ollama_client.py -> parents[2] == Shared/
SHARED_ROOT = Path(__file__).resolve().parents[2]
INSTALLED_MODELS_FILE = SHARED_ROOT / "models" / "installed-models.txt"

NO_MODEL_MESSAGE = (
    "No AI model found. Run Mac/install.command first, then start "
    "Mac/start.command."
)


class OllamaError(RuntimeError):
    """Raised when the local Ollama server cannot be reached or errors."""


def read_first_installed_model() -> str | None:
    """Return the first model name from ``installed-models.txt``, or None.

    Each line is ``local_model_name|Display Name|LABEL``; the model name is
    the first field before the first ``|``. Blank lines are skipped.
    """
    if not INSTALLED_MODELS_FILE.exists():
        return None

    for raw_line in INSTALLED_MODELS_FILE.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        name = line.split("|", 1)[0].strip()
        if name:
            return name
    return None


def get_model() -> str:
    """Resolve the model name to use.

    Selection order:
        1. Environment variable ``AI_DM_MODEL`` if set.
        2. First installed model from ``Shared/models/installed-models.txt``.
        3. Otherwise raise :class:`OllamaError` with install guidance.
    """
    env_model = os.environ.get("AI_DM_MODEL", "").strip()
    if env_model:
        return env_model

    installed = read_first_installed_model()
    if installed:
        return installed

    raise OllamaError(NO_MODEL_MESSAGE)


def chat(
    messages: List[Dict[str, str]],
    model: str | None = None,
    timeout: float = 120.0,
    json_mode: bool = False,
) -> str:
    """Send a non-streaming chat request to the local Ollama server.

    Args:
        messages: A list of ``{"role": ..., "content": ...}`` dicts.
        model: Model name to use. Defaults to :func:`get_model`.
        timeout: Socket timeout in seconds.
        json_mode: If True, ask Ollama to constrain output to valid JSON by
            setting ``"format": "json"`` on the request. Callers should still
            defensively parse the result, since not every model honours it.

    Returns:
        The assistant message content as a string.

    Raises:
        OllamaError: If the server is unreachable or returns an error.
    """
    model_name = model or get_model()
    payload = {
        "model": model_name,
        "messages": messages,
        "stream": False,
    }
    if json_mode:
        payload["format"] = "json"

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        CHAT_ENDPOINT,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(
            f"Ollama returned HTTP {exc.code} for model {model_name!r}.\n{detail}\n"
            "If the model is missing, pull it with: "
            f"ollama pull {model_name}"
        ) from exc
    except urllib.error.URLError as exc:
        raise OllamaError(
            "Could not reach the local Ollama server at "
            f"{OLLAMA_HOST}. Is it running?\n"
            "Start it with:  ollama serve\n"
            f"Underlying error: {exc.reason}"
        ) from exc

    try:
        parsed = json.loads(body)
    except json.JSONDecodeError as exc:
        raise OllamaError(f"Could not parse Ollama response as JSON:\n{body}") from exc

    message = parsed.get("message") or {}
    content = message.get("content")
    if not content:
        raise OllamaError(f"Ollama response contained no message content:\n{body}")

    return content

"""Call an OpenAI-compatible chat completion endpoint."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# from_env() reads these variables from the environment.
# LLM_BASE_URL, LLM_API_KEY, LLM_MODEL, LLM_TIMEOUT


class LLMError(Exception):
    """Raised when the endpoint cannot return a usable answer."""


class LLMClient:
    """Client for one OpenAI-compatible chat completion endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"LLMClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls) -> LLMClient:
        """Build a client from the LLM_* environment variables."""
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", ""),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", ""),
            timeout=float(os.environ.get("LLM_TIMEOUT", "120")),
        )

    def chat(
        self,
        prompt: str,
        *,
        image_path: Path | None = None,
        json_mode: bool = True,
    ) -> str:
        """Send a prompt, optionally with one image, and return the reply."""
        if not (self.base_url and self.api_key and self.model):
            raise LLMError(f"llm endpoint is not configured: {self!r}")

        content: str | list = prompt
        if image_path is not None:
            image_part = {
                "type": "image_url",
                "image_url": {"url": _to_data_url(image_path)},
            }
            text_part = {"type": "text", "text": prompt}
            content = [image_part, text_part]

        messages = []
        if json_mode:
            # The endpoint rejects json_object unless "json" appears
            # somewhere in the messages.
            messages.append({"role": "system", "content": "Respond in JSON."})
        messages.append({"role": "user", "content": content})
        payload = {"model": self.model, "messages": messages}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        return self._post(payload)

    def _post(self, payload: dict) -> str:
        url = self.base_url.rstrip("/") + "/chat/completions"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )

        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:300]
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise LLMError(f"cannot reach {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise LLMError(f"timeout after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed response from endpoint") from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        return str(content)


# Supported image suffixes and their MIME types.
_MIME_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".bmp": "image/bmp",
}


# Convert a local image file to a data URL.
def _to_data_url(path: Path) -> str:
    mime = _MIME_TYPES.get(path.suffix.lower())
    if mime is None:
        raise LLMError(f"unsupported image type: {path.suffix}")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def extract_json(text: str) -> dict:
    """Return the first JSON object found in text."""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in text")

    try:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc

    return obj

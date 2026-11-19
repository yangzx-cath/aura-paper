"""Call an OpenAI-compatible chat completion endpoint."""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .utils import data_url

# The endpoint drops calls when it runs out of capacity, so repeat those.
RETRY_STATUS = (429, 500, 502, 503, 504)
RETRIES = 4
RETRY_DELAY = 2.0


class LLMError(Exception):
    """Error for LLM calls."""


class LLMClient:
    """Client for one OpenAI-compatible chat completion endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float
    reasoning_effort: str

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = 120.0,
        reasoning_effort: str = "",
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.reasoning_effort = reasoning_effort

    def __repr__(self) -> str:
        return (
            f"LLMClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls, effort: str = "") -> LLMClient:
        """Build a client from the LLM_* environment variables.

        The effort argument overrides LLM_REASONING_EFFORT.
        """
        return cls(
            base_url=os.environ.get("LLM_BASE_URL", ""),
            api_key=os.environ.get("LLM_API_KEY", ""),
            model=os.environ.get("LLM_MODEL", ""),
            timeout=float(os.environ.get("LLM_TIMEOUT", "120")),
            reasoning_effort=(
                effort or os.environ.get("LLM_REASONING_EFFORT", "")
            ),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        names = ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL")
        values = (self.base_url, self.api_key, self.model)
        return [name for name, value in zip(names, values) if not value]

    # Settings that change the reply, so callers can cache on them.
    @property
    def signature(self) -> tuple[str, str]:
        return (self.model, self.reasoning_effort)

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
                "image_url": {"url": data_url(image_path)},
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
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort

        return self._post(payload)

    def _post(self, payload: dict) -> str:
        data = self._send(payload)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed reply from endpoint") from exc

        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        return str(content)

    def _send(self, payload: dict) -> dict:
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

        delay = RETRY_DELAY
        raw = ""
        for attempt in range(1, RETRIES + 1):
            try:
                with urllib.request.urlopen(
                    request, timeout=self.timeout
                ) as response:
                    raw = response.read().decode("utf-8", errors="replace")
                break
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", errors="replace")[:300]
                if exc.code not in RETRY_STATUS or attempt == RETRIES:
                    raise LLMError(f"HTTP {exc.code}: {detail}") from exc
                time.sleep(delay)
                delay *= 2
            except urllib.error.URLError as exc:
                raise LLMError(f"cannot reach {url}: {exc.reason}") from exc
            except TimeoutError as exc:
                raise LLMError(f"timeout after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LLMError("malformed reply from endpoint") from exc
        if not isinstance(data, dict):
            raise LLMError("malformed reply from endpoint")
        return data

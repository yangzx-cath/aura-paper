"""Access the vision model through an OpenAI-compatible endpoint."""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

# Environment variables:
#   VISION_BASE_URL, VISION_API_KEY, VISION_MODEL, VISION_TIMEOUT


class VisionError(Exception):
    """Raised when the endpoint cannot return a usable answer."""


class VisionClient:
    """Client for one OpenAI-compatible vision endpoint."""

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
            f"VisionClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls) -> VisionClient:
        """Build a client from the VISION_* environment variables."""
        return cls(
            base_url=os.environ.get("VISION_BASE_URL", ""),
            api_key=os.environ.get("VISION_API_KEY", ""),
            model=os.environ.get("VISION_MODEL", ""),
            timeout=float(os.environ.get("VISION_TIMEOUT", "120")),
        )

    def analyze(
        self,
        prompt: str,
        image_path: Path,
        *,
        json_mode: bool = True,
    ) -> str:
        """Send one image with a prompt and return the reply text."""
        if not self.base_url or not self.api_key or not self.model:
            raise VisionError("vision endpoint is not configured")

        image_part = {
            "type": "image_url",
            "image_url": {"url": _to_data_url(image_path)},
        }
        text_part = {"type": "text", "text": prompt}
        messages = []
        if json_mode:
            # The endpoint rejects json_object unless "json" appears
            # somewhere in the messages.
            messages.append({"role": "system", "content": "Respond in JSON."})
        messages.append({"role": "user", "content": [image_part, text_part]})
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
            raise VisionError(f"HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise VisionError(f"cannot reach {url}: {exc.reason}") from exc
        except TimeoutError as exc:
            raise VisionError(f"timeout after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
            content = data["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
            raise VisionError("malformed response from endpoint") from exc

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
        raise VisionError(f"unsupported image type: {path.suffix}")
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

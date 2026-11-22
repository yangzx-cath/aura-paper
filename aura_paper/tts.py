"""Call the Volcengine speech synthesis API.

One call turns one line of text into audio. The reply carries the audio as
base64 plus its measured length, so the caller never has to decode the file
to learn how long the line takes.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://openspeech.bytedance.com"
DEFAULT_PATH = "/api/v1/tts"
DEFAULT_CLUSTER = "volcano_tts"

# Children's book narration, one of the Doubao 2.0 voices.
DEFAULT_VOICE = "zh_female_xiaoxue_uranus_bigtts"
DEFAULT_FORMAT = "mp3"
DEFAULT_RATE = 24000

# The only code that means the audio was produced.
OK_CODE = 3000


class TTSError(Exception):
    """Error for speech synthesis calls."""


@dataclass
class Speech:
    """One synthesized line of text."""

    text: str
    voice: str
    data: bytes = b""
    duration_ms: int = 0

    def save(self, path: str | Path) -> Path:
        """Write the audio to path and return it."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.data)
        return target


class TTSClient:
    """Client for one speech synthesis endpoint."""

    base_url: str
    app_id: str
    token: str
    cluster: str
    voice: str
    timeout: float

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        app_id: str = "",
        token: str = "",
        cluster: str = DEFAULT_CLUSTER,
        voice: str = DEFAULT_VOICE,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url
        self.app_id = app_id
        self.token = token
        self.cluster = cluster
        self.voice = voice
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"TTSClient(base_url={self.base_url!r}, "
            f"cluster={self.cluster!r}, voice={self.voice!r})"
        )

    @classmethod
    def from_env(cls) -> TTSClient:
        """Build a client from the TTS_* environment variables."""
        return cls(
            base_url=os.environ.get("TTS_BASE_URL", DEFAULT_BASE_URL),
            app_id=os.environ.get("TTS_APP_ID", ""),
            token=os.environ.get("TTS_ACCESS_TOKEN", ""),
            cluster=os.environ.get("TTS_CLUSTER", DEFAULT_CLUSTER),
            voice=os.environ.get("TTS_VOICE", DEFAULT_VOICE),
            timeout=float(os.environ.get("TTS_TIMEOUT", "60")),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        missing = []
        if not self.app_id:
            missing.append("TTS_APP_ID")
        if not self.token:
            missing.append("TTS_ACCESS_TOKEN")
        return missing

    def synthesize(
        self,
        text: str,
        *,
        voice: str = "",
        emotion: str = "",
        speed: float = 1.0,
    ) -> Speech:
        """Turn one line of text into audio."""
        if not text.strip():
            raise TTSError("text is required")
        payload = self._payload(text, voice or self.voice, emotion, speed)
        return self._speech(text, payload, self._post(payload))

    def _payload(
        self,
        text: str,
        voice: str,
        emotion: str,
        speed: float,
    ) -> dict:
        audio = {
            "voice_type": voice,
            "encoding": DEFAULT_FORMAT,
            "rate": DEFAULT_RATE,
            "speed_ratio": speed,
        }
        if emotion:
            audio["emotion"] = emotion
        request = {
            "reqid": uuid.uuid4().hex,
            "text": text,
            "text_type": "plain",
            "operation": "query",
        }
        return {
            "app": {
                "appid": self.app_id,
                "token": self.token,
                "cluster": self.cluster,
            },
            "user": {"uid": "aura-paper"},
            "audio": audio,
            "request": request,
        }

    @staticmethod
    def _speech(text: str, payload: dict, reply: dict) -> Speech:
        code = reply.get("code")
        if code != OK_CODE:
            message = reply.get("message") or f"code {code}"
            raise TTSError(f"synthesis failed: {message}")
        encoded = reply.get("data") or ""
        if not encoded:
            raise TTSError("reply carries no audio")
        try:
            data = base64.b64decode(encoded)
        except (ValueError, TypeError) as exc:
            raise TTSError("reply audio is not base64") from exc
        addition = reply.get("addition")
        addition = addition if isinstance(addition, dict) else {}
        voice = payload["audio"]["voice_type"]
        return Speech(
            text=text,
            voice=voice,
            data=data,
            duration_ms=_duration_ms(addition.get("duration")),
        )

    def _post(self, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self._send(body)

    def _send(self, body: bytes) -> dict:
        if not self.app_id or not self.token:
            raise TTSError("speech endpoint is not configured")

        url = self.base_url.rstrip("/") + DEFAULT_PATH
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                # The endpoint wants a semicolon, not a space.
                "Authorization": f"Bearer;{self.token}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout
            ) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TTSError(f"HTTP {exc.code}: {detail[:200]}") from exc
        except urllib.error.URLError as exc:
            raise TTSError(f"cannot reach the endpoint: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TTSError("request timed out") from exc

        try:
            reply = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise TTSError("reply is not JSON") from exc
        if not isinstance(reply, dict):
            raise TTSError("reply is not an object")
        return reply


# Read the audio length from the reply, which reports milliseconds.
def _duration_ms(value: object) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return 0

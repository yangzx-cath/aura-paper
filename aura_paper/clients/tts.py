"""Call the Volcengine speech synthesis API, v3 with an API key.

One call turns one line of text into audio. The reply arrives as a stream
of JSON objects, each carrying a piece of the audio in base64. The line is
asked for as 16-bit mono PCM, so its length is exact arithmetic and the
caller never has to decode the file to learn how long the line takes.
"""

from __future__ import annotations

import base64
import json
import os
import struct
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

DEFAULT_BASE_URL = "https://openspeech.bytedance.com"
DEFAULT_PATH = "/api/v3/tts/unidirectional"

# Ask for the format whose length is simple arithmetic.
DEFAULT_FORMAT = "pcm"
DEFAULT_RATE = 24000

# 16-bit mono, so one second holds rate * 2 bytes.
BYTES_PER_SAMPLE = 2

# The code that marks a piece of audio inside the stream.
CHUNK_CODE = 0

# The code that means the whole line was synthesized.
DONE_CODE = 20000000

# Speech rate is a percentage offset from normal speed.
MIN_RATE_OFFSET = -50
MAX_RATE_OFFSET = 100


class TTSError(Exception):
    """Error for speech synthesis calls."""


@dataclass
class Speech:
    """One synthesized line of text."""

    text: str
    voice: str
    data: bytes = b""
    duration_ms: int = 0
    sample_rate: int = DEFAULT_RATE

    def save(self, path: str | Path) -> Path:
        """Write the audio to path and return it."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(self.data)
        return target


class TTSClient:
    """Client for one speech synthesis endpoint."""

    base_url: str
    api_key: str
    resource_id: str
    timeout: float

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        resource_id: str = "",
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.resource_id = resource_id
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"TTSClient(base_url={self.base_url!r}, "
            f"resource_id={self.resource_id!r})"
        )

    # Settings that change the audio, so callers can cache on them.
    @property
    def signature(self) -> tuple[str, str]:
        return (self.base_url, self.resource_id)

    @classmethod
    def from_env(cls) -> TTSClient:
        """Build a client from the TTS_* environment variables."""
        return cls(
            base_url=os.environ.get("TTS_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("TTS_API_KEY", ""),
            resource_id=os.environ.get("TTS_RESOURCE_ID", ""),
            timeout=float(os.environ.get("TTS_TIMEOUT", "60")),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        missing = []
        if not self.api_key:
            missing.append("TTS_API_KEY")
        if not self.resource_id:
            missing.append("TTS_RESOURCE_ID")
        return missing

    def synthesize(
        self,
        text: str,
        *,
        voice: str,
        speed: float = 1.0,
        emotion: str = "",
    ) -> Speech:
        """Turn one line of text into audio."""
        if not text.strip():
            raise TTSError("text is required")
        if not voice.strip():
            raise TTSError("voice is required")
        pcm = self._audio(self._post(_payload(text, voice, speed, emotion)))
        return Speech(
            text=text,
            voice=voice,
            data=_wav(pcm, DEFAULT_RATE),
            duration_ms=_duration_ms(len(pcm), DEFAULT_RATE),
            sample_rate=DEFAULT_RATE,
        )

    def _post(self, payload: dict) -> str:
        if not self.api_key or not self.resource_id:
            raise TTSError("speech endpoint is not configured")

        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url.rstrip("/") + DEFAULT_PATH,
            data=body,
            method="POST",
            headers={
                "X-Api-Key": self.api_key,
                "X-Api-Resource-Id": self.resource_id,
                "X-Api-Request-Id": uuid.uuid4().hex,
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(
                request, timeout=self.timeout
            ) as response:
                return response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise TTSError(f"HTTP {exc.code}: {detail[:200]}") from exc
        except urllib.error.URLError as exc:
            raise TTSError(f"cannot reach the endpoint: {exc.reason}") from exc
        except TimeoutError as exc:
            raise TTSError("request timed out") from exc

    @staticmethod
    def _audio(reply: str) -> bytes:
        """Join the audio pieces of a reply into one PCM buffer."""
        decoder = json.JSONDecoder()
        audio = bytearray()
        at = 0
        while at < len(reply):
            while at < len(reply) and reply[at].isspace():
                at += 1
            if at >= len(reply):
                break
            try:
                piece, at = decoder.raw_decode(reply, at)
            except json.JSONDecodeError as exc:
                raise TTSError("reply is not JSON") from exc
            if not isinstance(piece, dict):
                raise TTSError("reply is not an object")

            code = piece.get("code")
            if code == DONE_CODE:
                break
            if code not in (CHUNK_CODE, None):
                message = piece.get("message") or f"code {code}"
                raise TTSError(f"synthesis failed: {message}")

            encoded = piece.get("data") or ""
            if not encoded:
                continue
            try:
                audio += base64.b64decode(encoded)
            except (ValueError, TypeError) as exc:
                raise TTSError("reply audio is not base64") from exc

        if not audio:
            raise TTSError("reply carries no audio")
        return bytes(audio)


# Build the request body for one line.
def _payload(text: str, voice: str, speed: float, emotion: str) -> dict:
    audio = {
        "format": DEFAULT_FORMAT,
        "sample_rate": DEFAULT_RATE,
    }
    offset = _rate_offset(speed)
    if offset:
        audio["speech_rate"] = offset
    if emotion:
        audio["emotion"] = emotion
    return {
        "user": {"uid": "aura-paper"},
        "req_params": {
            "text": text,
            "speaker": voice,
            "audio_params": audio,
        },
    }


# Turn a speed multiplier into the percentage offset the service wants.
def _rate_offset(speed: float) -> int:
    offset = round((speed - 1.0) * 100)
    return max(MIN_RATE_OFFSET, min(MAX_RATE_OFFSET, offset))


# Wrap raw PCM in a WAV container so the file plays anywhere.
def _wav(pcm: bytes, rate: int) -> bytes:
    header = struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF",
        36 + len(pcm),
        b"WAVE",
        b"fmt ",
        16,
        1,
        1,
        rate,
        rate * BYTES_PER_SAMPLE,
        BYTES_PER_SAMPLE,
        16,
        b"data",
        len(pcm),
    )
    return header + pcm


# Return how many milliseconds a PCM buffer lasts.
def _duration_ms(size: int, rate: int) -> int:
    return round(size * 1000 / (rate * BYTES_PER_SAMPLE))

"""Turn speech into text with the Volcengine streaming ASR endpoint.

The endpoint reads the audio as a websocket stream: one request that says
what the audio is, one message per slice of PCM, then a last message whose
sequence number is negative. Every reply carries the text so far, and the
last one carries the whole line along with the language it was spoken in.

The audio must already be 16 kHz, 16-bit, mono PCM. Nothing here converts
anything.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import os
import time
import uuid
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass

import websockets
from websockets.exceptions import WebSocketException

from ..schema.content import language_of

DEFAULT_BASE_URL = "wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async"
DEFAULT_TIMEOUT = 30.0

# The endpoint reads nothing else, so the rate is fixed here.
RATE = 16000
BITS = 16
CHANNELS = 1

# 16-bit mono, so one second holds RATE * 2 bytes.
BYTES_PER_SAMPLE = 2

# Audio is sent in slices of this many milliseconds, which is what the
# endpoint tunes its buffering for.
CHUNK_MS = 200
CHUNK_BYTES = RATE * BYTES_PER_SAMPLE * CHUNK_MS // 1000

# A short pause between slices keeps the stream close to live audio.
CHUNK_PAUSE = 0.02

# The endpoint drops a connection now and then, so one line is worth
# asking for again.
RETRIES = 3
RETRY_DELAY = 1.0

# Protocol constants of the binary websocket frames.
VERSION = 0b0001
HEADER_WORDS = 0b0001
FULL_REQUEST = 0b0001
AUDIO_REQUEST = 0b0010
FULL_RESPONSE = 0b1001
ERROR_RESPONSE = 0b1111
FLAG_NONE = 0b0000
FLAG_SEQUENCE = 0b0001
FLAG_LAST = 0b0011
SERIAL_NONE = 0b0000
SERIAL_JSON = 0b0001
COMPRESS_GZIP = 0b0001

# Codes from here up are the service's own trouble, not a bad request.
SERVER_ERROR_CODE = 50000000

# The few client-side codes that are still worth asking again.
TRANSIENT_CODES = frozenset({45000081, 55000031})

# How the endpoint names the language of a spoken line.
LANGUAGE_BY_LABEL = {
    "speech_mand": "zh",
    "speech_en": "en",
    "singing_mand": "zh",
    "singing_en": "en",
}


class ASRError(Exception):
    """Error for speech recognition calls."""


class TransientError(ASRError):
    """A failure that is worth asking for again."""


@dataclass
class Hearing:
    """One spoken line, turned into text."""

    text: str = ""
    language: str = ""
    duration_ms: int = 0


class ASRClient:
    """Client for one streaming speech recognition endpoint."""

    base_url: str
    api_key: str
    resource_id: str
    timeout: float

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        resource_id: str = "",
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.resource_id = resource_id
        self.timeout = timeout

    def __repr__(self) -> str:
        return (
            f"ASRClient(base_url={self.base_url!r}, "
            f"resource_id={self.resource_id!r})"
        )

    @classmethod
    def from_env(cls) -> ASRClient:
        """Build a client from the ASR_* environment variables.

        The key falls back to TTS_API_KEY, since one app is expected to
        both speak and listen.
        """
        return cls(
            base_url=os.environ.get("ASR_BASE_URL", DEFAULT_BASE_URL),
            api_key=(
                os.environ.get("ASR_API_KEY")
                or os.environ.get("TTS_API_KEY", "")
            ),
            resource_id=os.environ.get("ASR_RESOURCE_ID", ""),
            timeout=float(os.environ.get("ASR_TIMEOUT", DEFAULT_TIMEOUT)),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        missing = []
        if not self.api_key:
            missing.append("ASR_API_KEY")
        if not self.resource_id:
            missing.append("ASR_RESOURCE_ID")
        return missing

    # Settings that change the text, so callers can cache on them.
    @property
    def signature(self) -> tuple[str, str]:
        return (self.base_url, self.resource_id)

    def transcribe(
        self,
        pcm: bytes,
        *,
        hotwords: Sequence[str] = (),
        on_text: Callable[[str], None] | None = None,
    ) -> Hearing:
        """Turn one finished recording into text."""
        if not pcm:
            raise ASRError("audio is required")

        delay = RETRY_DELAY
        last = "cannot reach the endpoint"
        for attempt in range(1, RETRIES + 1):
            try:
                return asyncio.run(
                    self.listen(
                        _slices(pcm), hotwords=hotwords, on_text=on_text
                    )
                )
            except TransientError as exc:
                last = str(exc)
                if attempt == RETRIES:
                    raise
            except (OSError, WebSocketException) as e:
                last = f"cannot reach the endpoint: {e}"
                if attempt == RETRIES:
                    raise ASRError(last) from e
            time.sleep(delay)
            delay *= 2
        raise ASRError(last)

    async def listen(
        self,
        chunks: AsyncIterator[bytes],
        *,
        hotwords: Sequence[str] = (),
        on_text: Callable[[str], None] | None = None,
    ) -> Hearing:
        """Turn a stream of PCM slices into text as they are spoken.

        The slices are sent while the replies are read, so the caller can
        show the text growing. A stream cannot be replayed, so a failure
        here is not retried; the caller decides whether to record again.
        """
        if not self.api_key or not self.resource_id:
            raise ASRError("speech endpoint is not configured")

        headers = {
            "X-Api-Key": self.api_key,
            "X-Api-Resource-Id": self.resource_id,
            "X-Api-Request-Id": uuid.uuid4().hex,
            "X-Api-Connect-Id": uuid.uuid4().hex,
        }
        async with _connect(self.base_url, headers) as socket:
            await socket.send(_request_frame(self._config(hotwords)))
            sender = asyncio.create_task(self._send(socket, chunks))
            try:
                return await self._read(socket, on_text)
            finally:
                await _stop(sender)

    # Build the request that describes the audio about to be sent.
    def _config(self, hotwords: Sequence[str]) -> dict:
        request = {
            "model_name": "bigmodel",
            "enable_itn": True,
            "enable_punc": True,
            "enable_lid": True,
            "show_utterances": True,
            "end_window_size": 800,
        }
        if hotwords:
            words = [{"word": word} for word in hotwords]
            request["corpus"] = {
                "context": json.dumps({"hotwords": words}, ensure_ascii=False)
            }
        return {
            "user": {"uid": "aura-paper"},
            "audio": {
                "format": "pcm",
                "rate": RATE,
                "bits": BITS,
                "channel": CHANNELS,
            },
            "request": request,
        }

    # Send every slice, holding one back so the last one can close the line.
    async def _send(
        self, socket: websockets.ClientConnection, chunks: AsyncIterator[bytes]
    ) -> None:
        sequence = 1
        held = b""
        async for chunk in chunks:
            if held:
                sequence += 1
                frame = _audio_frame(held, sequence, last=False)
                await socket.send(frame)
                await asyncio.sleep(CHUNK_PAUSE)
            held = chunk
        sequence += 1
        await socket.send(_audio_frame(held, sequence, last=True))

    # Read the replies until the endpoint says the line is finished.
    async def _read(
        self,
        socket: websockets.ClientConnection,
        on_text: Callable[[str], None] | None,
    ) -> Hearing:
        text = ""
        while True:
            try:
                message = await asyncio.wait_for(socket.recv(), self.timeout)
            except asyncio.TimeoutError as exc:
                raise ASRError("no reply before the timeout") from exc
            flags, body = _unpack(message)

            result = body.get("result") or {}
            spoken = str(result.get("text") or "")
            if spoken and spoken != text:
                text = spoken
                if on_text is not None:
                    on_text(text)
            if flags == FLAG_LAST:
                audio = body.get("audio_info") or {}
                return Hearing(
                    text=text,
                    language=_language(result),
                    duration_ms=int(audio.get("duration") or 0),
                )


# Open one websocket, so tests can hand in a stand-in.
def _connect(url: str, headers: dict[str, str]):
    """Open the endpoint as an async context manager."""
    return websockets.connect(url, additional_headers=headers, max_size=None)


# Stop one task, without letting its own failure hide the real one.
async def _stop(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


# Cut one recording into the slices the endpoint likes to receive.
async def _slices(pcm: bytes) -> AsyncIterator[bytes]:
    for start in range(0, len(pcm), CHUNK_BYTES):
        yield pcm[start : start + CHUNK_BYTES]


# Build the four header bytes of one frame.
def _head(kind: int, flags: int, serial: int, compression: int) -> bytes:
    return bytes(
        [
            (VERSION << 4) | HEADER_WORDS,
            (kind << 4) | flags,
            (serial << 4) | compression,
            0x00,
        ]
    )


# Build the request frame that opens the stream.
def _request_frame(config: dict) -> bytes:
    body = gzip.compress(
        json.dumps(config, ensure_ascii=False).encode("utf-8")
    )
    return _head(FULL_REQUEST, FLAG_NONE, SERIAL_JSON, COMPRESS_GZIP) + (
        len(body).to_bytes(4, "big") + body
    )


# Build one frame of audio, whose sequence turns negative on the last one.
def _audio_frame(pcm: bytes, sequence: int, *, last: bool) -> bytes:
    flags = FLAG_LAST if last else FLAG_SEQUENCE
    number = -sequence if last else sequence
    body = gzip.compress(pcm)
    return (
        _head(AUDIO_REQUEST, flags, SERIAL_NONE, COMPRESS_GZIP)
        + number.to_bytes(4, "big", signed=True)
        + len(body).to_bytes(4, "big")
        + body
    )


# Read the flags and the JSON body out of one reply.
def _unpack(message: bytes) -> tuple[int, dict]:
    kind = message[1] >> 4
    flags = message[1] & 0x0F
    compression = message[2] & 0x0F
    at = (message[0] & 0x0F) * 4
    if flags in (FLAG_SEQUENCE, FLAG_LAST):
        at += 4
    if kind == ERROR_RESPONSE:
        code = int.from_bytes(message[at : at + 4], "big")
        at += 4
        size = int.from_bytes(message[at : at + 4], "big")
        at += 4
        detail = message[at : at + size].decode("utf-8", errors="replace")
        raise _error(code, detail)
    size = int.from_bytes(message[at : at + 4], "big")
    at += 4
    body = message[at : at + size]
    if compression == COMPRESS_GZIP:
        body = gzip.decompress(body)
    return flags, json.loads(body.decode("utf-8", errors="replace"))


# Name the failure of one error frame, keeping the ones worth retrying.
def _error(code: int, detail: str) -> ASRError:
    message = f"ASR code {code}: {detail[:200]}"
    if code >= SERVER_ERROR_CODE or code in TRANSIENT_CODES:
        return TransientError(message)
    return ASRError(message)


# Read the language of the line off its last utterance, then off the words.
def _language(result: dict) -> str:
    for utterance in result.get("utterances") or []:
        additions = utterance.get("additions") or {}
        tongue = LANGUAGE_BY_LABEL.get(str(additions.get("lid_lang") or ""))
        if tongue:
            return tongue
    return language_of(str(result.get("text") or ""))

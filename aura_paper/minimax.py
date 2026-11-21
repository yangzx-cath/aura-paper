"""Call the MiniMax video generation API (v2)."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .utils import data_url
from .video_types import VideoError
from .video_types import VideoRequest as _VideoRequest
from .video_types import VideoTask as _VideoTask

DEFAULT_BASE_URL = "https://api.minimax.io"
DEFAULT_MODEL = "MiniMax-H3"

# Request limits from the video endpoint.
_MAX_IMAGE_BYTES = 30 * 1024 * 1024
_MAX_BODY_BYTES = 64 * 1024 * 1024


class MiniMaxError(VideoError):
    """Error for MiniMax calls."""


@dataclass
class VideoRequest(_VideoRequest):
    """One MiniMax video generation request."""

    resolution: str = "768P"

    def __post_init__(self) -> None:
        super().__post_init__()
        images = [self.first_frame, self.last_frame]
        images += self.reference_images
        for path in images:
            if path is None:
                continue
            if path.stat().st_size > _MAX_IMAGE_BYTES:
                raise ValueError(f"image is larger than 30MB: {path}")

    def to_payload(self, model: str) -> dict:
        """Return the request body for the video generation endpoint."""
        content: list[dict] = [{"type": "text", "text": self.prompt}]
        images = [
            (self.first_frame, "first_frame"),
            (self.last_frame, "last_frame"),
        ]
        images += [(path, "reference_image") for path in self.reference_images]
        for path, role in images:
            if path is None:
                continue
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": data_url(path)},
                    "role": role,
                }
            )

        payload = {
            "model": model,
            "content": content,
            "duration": self.duration,
            "resolution": self.resolution,
        }
        if self.ratio is not None:
            payload["ratio"] = self.ratio
        return payload


@dataclass
class VideoTask(_VideoTask):
    """Snapshot of one MiniMax video task."""

    @classmethod
    def from_response(cls, data: dict) -> VideoTask:
        """Build a task from a create or query response body."""
        task = data.get("task", data)
        if not isinstance(task, dict):
            raise MiniMaxError("malformed task reply")

        content = task.get("content")
        content = content if isinstance(content, dict) else {}
        error = task.get("error")
        if isinstance(error, dict):
            error = error.get("message") or error.get("code") or ""
        elif not isinstance(error, str):
            error = ""

        return cls(
            task_id=str(task.get("id") or task.get("task_id") or ""),
            status=str(task.get("status") or ""),
            video_url=str(content.get("url") or ""),
            resolution=str(task.get("resolution") or ""),
            duration=int(task.get("duration") or 0),
            error=str(error),
        )


class MiniMaxClient:
    """Client for one MiniMax video generation endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float
    poll_interval: float
    max_wait: float

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        poll_interval: float = 5.0,
        max_wait: float = 600.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.poll_interval = poll_interval
        self.max_wait = max_wait

    def __repr__(self) -> str:
        return (
            f"MiniMaxClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls) -> MiniMaxClient:
        """Build a client from the MINIMAX_* environment variables."""
        return cls(
            base_url=os.environ.get("MINIMAX_BASE_URL", DEFAULT_BASE_URL),
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            model=os.environ.get("MINIMAX_VIDEO_MODEL", DEFAULT_MODEL),
            timeout=float(os.environ.get("MINIMAX_TIMEOUT", "60")),
            poll_interval=float(os.environ.get("MINIMAX_POLL_INTERVAL", "5")),
            max_wait=float(os.environ.get("MINIMAX_MAX_WAIT", "600")),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        if not self.api_key:
            return ["MINIMAX_API_KEY"]
        return []

    # POST /v2/video_generation
    def create_task(self, request: VideoRequest) -> VideoTask:
        """Submit one generation task and return its first snapshot."""
        payload = request.to_payload(self.model)
        data = self._post("/v2/video_generation", payload)
        task = VideoTask.from_response(data)
        if not task.task_id:
            raise MiniMaxError("reply carries no task_id")
        if not task.status:
            task.status = "queued"
        return task

    # Send one JSON POST and return the parsed body.
    def _post(self, path: str, payload: dict) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > _MAX_BODY_BYTES:
            raise ValueError("request body exceeds 64MB")
        return self._send(path, body, "POST")

    def _send(self, path: str, body: bytes | None, method: str) -> dict:
        if not self.api_key:
            raise MiniMaxError("minimax endpoint is not configured")

        url = self.base_url.rstrip("/") + path
        request = urllib.request.Request(
            url,
            data=body,
            method=method,
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
            raw = exc.read().decode("utf-8", errors="replace")
            detail = self._error_message(raw) or f"HTTP {exc.code}"
            raise MiniMaxError(detail) from exc
        except urllib.error.URLError as exc:
            detail = f"cannot reach {url}: {exc.reason}"
            raise MiniMaxError(detail) from exc
        except TimeoutError as exc:
            raise MiniMaxError(f"timeout after {self.timeout}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise MiniMaxError("malformed reply from endpoint") from exc
        if not isinstance(data, dict):
            raise MiniMaxError("malformed reply from endpoint")
        return self._check(data)

    # Pull the message out of an OpenAI-style error body.
    @staticmethod
    def _error_message(raw: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw[:300]
        error = data.get("error") if isinstance(data, dict) else None
        if isinstance(error, dict):
            return str(error.get("message") or "")
        return raw[:300]

    @staticmethod
    def _check(data: dict) -> dict:
        error = data.get("error")
        if isinstance(error, dict):
            message = error.get("message") or "request failed"
            raise MiniMaxError(str(message))
        return data

    # GET /v2/query/video_generation/{task_id}
    def get_task(self, task_id: str) -> VideoTask:
        """Return the current snapshot of one task."""
        quoted = urllib.parse.quote(task_id, safe="")
        path = f"/v2/query/video_generation/{quoted}"
        return VideoTask.from_response(self._get(path, {}))

    # Send one GET and return the parsed body.
    def _get(self, path: str, params: dict) -> dict:
        query = urllib.parse.urlencode(params)
        if query:
            path = f"{path}?{query}"
        return self._send(path, None, "GET")

    def wait_task(self, task_id: str) -> VideoTask:
        """Poll a task until it finishes or max_wait elapses."""
        deadline = time.monotonic() + self.max_wait
        while True:
            task = self.get_task(task_id)
            if task.done:
                return task
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                task.error = f"timed out after {self.max_wait:.0f}s"
                return task
            time.sleep(min(self.poll_interval, remaining))

    # The URL is time-limited, so download right away.
    def download(self, url: str, path: str | Path) -> Path:
        """Fetch a finished video to path and return the path."""
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)

        fd, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                with urllib.request.urlopen(
                    url, timeout=self.timeout
                ) as response:
                    shutil.copyfileobj(response, f)
            os.replace(temp_name, target)
        except urllib.error.HTTPError as exc:
            raise MiniMaxError(f"download HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            detail = f"cannot download video: {exc.reason}"
            raise MiniMaxError(detail) from exc
        except TimeoutError as exc:
            raise MiniMaxError("download timed out") from exc
        finally:
            Path(temp_name).unlink(missing_ok=True)
        return target

    def generate(
        self,
        request: VideoRequest,
        path: str | Path,
    ) -> VideoTask:
        """Create, wait and download a video in one call."""
        task = self.create_task(request)
        task = self.wait_task(task.task_id)
        if not task.succeeded:
            return task
        if not task.video_url:
            task.error = "task succeeded without a video URL"
            return task
        self.download(task.video_url, path)
        return task

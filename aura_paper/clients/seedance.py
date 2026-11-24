"""Call the Seedance video generation API.

The client submits one video task, polls it until it finishes, and
downloads the resulting clip.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ..media.image import data_url
from .video import VideoError, VideoRequest, VideoTask

DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_MODEL = "doubao-seedance-2-0-fast-260128"
DEFAULT_RESOLUTION = "720p"

# A clip is a few megabytes, so its download reads for much longer than a
# JSON reply does.
DEFAULT_DOWNLOAD_TIMEOUT = 300.0

# The create call carries the reference images inline, so its body is a few
# megabytes and needs more time than a poll.
DEFAULT_UPLOAD_TIMEOUT = 180.0

# Waits before each retry of a finished download.
RETRY_DELAYS = (2.0, 5.0, 10.0)

# Request limits from the video endpoint.
_MAX_IMAGE_BYTES = 30 * 1024 * 1024
_MAX_BODY_BYTES = 64 * 1024 * 1024

# Resolution presets accepted by the video endpoint.
_RESOLUTIONS = frozenset(("480p", "720p", "1080p", "4k"))


class SeedanceError(VideoError):
    """Error for Seedance calls."""


class SeedanceClient:
    """Client for one Seedance video generation endpoint."""

    base_url: str
    api_key: str
    model: str
    timeout: float
    download_timeout: float
    upload_timeout: float
    poll_interval: float
    max_wait: float

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        api_key: str = "",
        model: str = DEFAULT_MODEL,
        timeout: float = 60.0,
        download_timeout: float = DEFAULT_DOWNLOAD_TIMEOUT,
        upload_timeout: float = DEFAULT_UPLOAD_TIMEOUT,
        poll_interval: float = 5.0,
        max_wait: float = 1200.0,
    ) -> None:
        self.base_url = base_url
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.download_timeout = download_timeout
        self.upload_timeout = upload_timeout
        self.poll_interval = poll_interval
        self.max_wait = max_wait

    def __repr__(self) -> str:
        return (
            f"SeedanceClient(base_url={self.base_url!r}, "
            f"model={self.model!r}, timeout={self.timeout})"
        )

    @classmethod
    def from_env(cls) -> SeedanceClient:
        """Build a client from ARK_API_KEY and the SEEDANCE_* variables."""
        return cls(
            base_url=os.environ.get("SEEDANCE_BASE_URL", DEFAULT_BASE_URL),
            api_key=(
                os.environ.get("ARK_API_KEY")
                or os.environ.get("SEEDANCE_API_KEY", "")
            ),
            model=os.environ.get("SEEDANCE_MODEL", DEFAULT_MODEL),
            timeout=float(os.environ.get("SEEDANCE_TIMEOUT", "60")),
            download_timeout=float(
                os.environ.get("SEEDANCE_DOWNLOAD_TIMEOUT", "300")
            ),
            upload_timeout=float(
                os.environ.get("SEEDANCE_UPLOAD_TIMEOUT", "180")
            ),
            poll_interval=float(os.environ.get("SEEDANCE_POLL_INTERVAL", "5")),
            max_wait=float(os.environ.get("SEEDANCE_MAX_WAIT", "1200")),
        )

    def missing_settings(self) -> list[str]:
        """Return the names of the settings that are still empty."""
        if not self.api_key:
            return ["ARK_API_KEY"]
        return []

    def create_task(self, request: VideoRequest) -> VideoTask:
        """Submit one generation task and return its first snapshot."""
        payload = self._payload(request)
        data = self._post(
            "/contents/generations/tasks",
            payload,
            timeout=self.upload_timeout,
        )
        task = self._task_from(data)
        if not task.task_id:
            raise SeedanceError("reply carries no task_id")
        if not task.status:
            task.status = "queued"
        return task

    def get_task(self, task_id: str) -> VideoTask:
        """Return the current snapshot of one task."""
        quoted = urllib.parse.quote(task_id, safe="")
        path = f"/contents/generations/tasks/{quoted}"
        return self._task_from(self._get(path, {}))

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

    def download(self, url: str, path: str | Path) -> Path:
        """Fetch a finished video to path and return the path.

        A stalled transfer is retried, because the task has already been
        paid for and its URL still points at the same clip.
        """
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        for delay in RETRY_DELAYS:
            try:
                return self._fetch(url, target)
            except SeedanceError:
                time.sleep(delay)
        return self._fetch(url, target)

    def _fetch(self, url: str, target: Path) -> Path:
        """Download once into a temporary file, then move it into place."""
        fd, temp_name = tempfile.mkstemp(dir=target.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                with urllib.request.urlopen(
                    url, timeout=self.download_timeout
                ) as response:
                    shutil.copyfileobj(response, f)
            os.replace(temp_name, target)
        except urllib.error.HTTPError as exc:
            raise SeedanceError(f"download HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            detail = f"cannot download video: {exc.reason}"
            raise SeedanceError(detail) from exc
        except TimeoutError as exc:
            raise SeedanceError("download timed out") from exc
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

    def _payload(self, request: VideoRequest) -> dict:
        """Return the request body for the create-task endpoint."""
        self._check_images(request)
        content: list[dict] = [{"type": "text", "text": request.prompt}]
        images = [
            (request.first_frame, "first_frame"),
            (request.last_frame, "last_frame"),
        ]
        images += [
            (path, "reference_image") for path in request.reference_images
        ]
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
        for path in request.reference_audios:
            content.append(
                {
                    "type": "audio_url",
                    "audio_url": {"url": _audio_url(path)},
                    "role": "reference_audio",
                }
            )

        payload = {
            "model": self.model,
            "content": content,
            "duration": request.duration,
            "resolution": _resolution(
                request.resolution or DEFAULT_RESOLUTION
            ),
        }
        if request.ratio is not None:
            payload["ratio"] = request.ratio
        if request.generate_audio is not None:
            payload["generate_audio"] = request.generate_audio
        return payload

    @staticmethod
    def _check_images(request: VideoRequest) -> None:
        images = [request.first_frame, request.last_frame]
        images += request.reference_images
        for path in images:
            if path is None:
                continue
            if path.stat().st_size > _MAX_IMAGE_BYTES:
                raise ValueError(f"image is larger than 30MB: {path}")

    def _post(
        self,
        path: str,
        payload: dict,
        *,
        timeout: float,
    ) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        if len(body) > _MAX_BODY_BYTES:
            raise ValueError("request body exceeds 64MB")
        return self._send(path, body, "POST", timeout=timeout, what="create")

    def _get(self, path: str, params: dict) -> dict:
        query = urllib.parse.urlencode(params)
        if query:
            path = f"{path}?{query}"
        return self._send(path, None, "GET", timeout=self.timeout, what="poll")

    def _send(
        self,
        path: str,
        body: bytes | None,
        method: str,
        *,
        timeout: float,
        what: str,
    ) -> dict:
        if not self.api_key:
            raise SeedanceError("seedance endpoint is not configured")

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
            with urllib.request.urlopen(request, timeout=timeout) as response:
                raw = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace")
            detail = self._error_message(raw) or f"HTTP {exc.code}"
            raise SeedanceError(detail) from exc
        except urllib.error.URLError as exc:
            detail = f"cannot reach {url}: {exc.reason}"
            raise SeedanceError(detail) from exc
        except TimeoutError as exc:
            raise SeedanceError(f"{what} timed out after {timeout}s") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise SeedanceError("malformed reply from endpoint") from exc
        if not isinstance(data, dict):
            raise SeedanceError("malformed reply from endpoint")
        return self._check(data)

    @staticmethod
    def _error_text(error: object) -> str:
        if not isinstance(error, dict):
            return error if isinstance(error, str) else ""
        code = str(error.get("code") or "")
        message = str(error.get("message") or "")
        if code and message:
            return f"{code}: {message}"
        return message or code

    @staticmethod
    def _error_message(raw: str) -> str:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return raw[:300]
        if isinstance(data, dict):
            return SeedanceClient._error_text(data.get("error"))
        return raw[:300]

    @staticmethod
    def _check(data: dict) -> dict:
        error = data.get("error")
        if isinstance(error, dict):
            message = SeedanceClient._error_text(error)
            raise SeedanceError(message or "request failed")
        return data

    @staticmethod
    def _task_from(data: dict) -> VideoTask:
        task = data.get("task", data)
        if not isinstance(task, dict):
            raise SeedanceError("malformed task reply")
        content = task.get("content")
        content = content if isinstance(content, dict) else {}
        return VideoTask(
            task_id=str(task.get("id") or task.get("task_id") or ""),
            status=str(task.get("status") or ""),
            video_url=str(content.get("video_url") or ""),
            resolution=str(task.get("resolution") or ""),
            duration=int(task.get("duration") or 0),
            error=SeedanceClient._error_text(task.get("error")),
        )


# Normalize a request preset to a Seedance resolution value.
def _resolution(value: str) -> str:
    result = value.strip().lower()
    if result not in _RESOLUTIONS:
        raise ValueError(f"unsupported resolution: {value}")
    return result


# Audio suffixes the endpoint takes, and the MIME type each one needs.
_AUDIO_MIME = {".wav": "audio/wav", ".mp3": "audio/mpeg"}


# Turn a local audio file into the data URL the endpoint reads.
def _audio_url(path: Path) -> str:
    mime = _AUDIO_MIME.get(path.suffix.lower())
    if mime is None:
        raise ValueError(f"unsupported audio type: {path.suffix}")
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"

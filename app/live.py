"""Bounded live capture while sampling YouTube chat.

Only a temporary segment is captured, not the whole livestream. It begins at
approximately the current stream edge; playback/live-chat latency can offset
wall-clock and footage, so exact synchronization cannot be guaranteed.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import math
import logging
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

from .media import VIDEO_ID_PATTERN, classify_media_error

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class BufferedClip:
    start: float
    duration: float


def buffer_window(clip_start: float, clip_end: float, broadcast_start: datetime,
                  recording_start: datetime, recorded_seconds: float,
                  clock_shift_seconds: float = 0) -> BufferedClip | None:
    """Map live-stream-relative timestamps to the temporary capture's seconds.

    clock_shift_seconds corrects measured chat vs. media latency. A window is
    only valid if ALL 30 seconds are present; don't silently shift highlights.
    """
    if not (broadcast_start and recording_start and clip_end > clip_start):
        return None
    offset = (recording_start - broadcast_start).total_seconds()
    clip_position = clip_start - offset + clock_shift_seconds
    length = clip_end - clip_start
    if clip_position < 0 or clip_position + length > recorded_seconds:
        return None
    return BufferedClip(round(clip_position, 3), round(length, 3))


class LiveBuffer:
    """Start a single, bounded ffmpeg recording as the live chat is polled."""

    def __init__(self, video_id: str, seconds: int = 150):
        if not VIDEO_ID_PATTERN.fullmatch(video_id):
            raise ValueError("Invalid YouTube video ID")
        if not (30 <= seconds <= 300):
            raise ValueError("Live capture length must be 30..300 seconds")
        self.video_id = video_id
        self.seconds = seconds
        self._temp: TemporaryDirectory | None = None
        self.proc: subprocess.Popen | None = None
        self.started_at: datetime | None = None
        self.path: Path | None = None
        self.recorded_seconds: float = 0.0

    def __enter__(self):
        self._temp = TemporaryDirectory(prefix="gta6-live-buffer-")
        self.path = Path(self._temp.name) / "live_segment.mkv"
        try:
            # 'b' means a single combined audio+video stream, unlike bv+ba.
            completed = subprocess.run(
                [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-live-from-start",
                 "--no-warnings", "-f", "b", "--get-url",
                 f"https://www.youtube.com/watch?v={self.video_id}"],
                capture_output=True, text=True, timeout=60, check=True,
            )
            urls = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
            if len(urls) != 1 or urlparse(urls[0]).scheme != "https":
                raise RuntimeError("No single HTTPS live audio/video playback URL available")
            self.started_at = datetime.now(timezone.utc)
            self.proc = subprocess.Popen(
                ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
                 "-i", urls[0], "-t", str(self.seconds), "-c", "copy", str(self.path)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            LOG.info("Started bounded %ss live capture for %s", self.seconds, self.video_id)
            return self
        except subprocess.CalledProcessError as exc:
            self.__exit__(None, None, None)
            raise classify_media_error(exc.stderr or exc.stdout) from exc
        except Exception:
            self.__exit__(None, None, None)
            raise

    def wait(self) -> Path:
        if not self.proc or not self.path:
            raise RuntimeError("Capture not started")
        try:
            code = self.proc.wait(timeout=self.seconds + 35)
        except subprocess.TimeoutExpired as exc:
            self.proc.kill()
            self.proc.wait()
            raise RuntimeError("Live recording exceeded time limit") from exc
        if code != 0 or not self.path.exists() or self.path.stat().st_size == 0:
            raise RuntimeError("FFmpeg could not record the selected live stream")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(self.path)],
            capture_output=True, text=True, check=True, timeout=25,
        )
        try:
            self.recorded_seconds = float(probe.stdout.strip())
        except ValueError as exc:
            raise RuntimeError("Cannot measure recorded live segment duration") from exc
        if not math.isfinite(self.recorded_seconds) or self.recorded_seconds < 30:
            raise RuntimeError("Captured live segment too short for a Short")
        return self.path

    def __exit__(self, exc_type, exc, tb):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                self.proc.wait()
        if self._temp:
            self._temp.cleanup()

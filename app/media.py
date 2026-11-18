"""Small time-window clips from media files, HTTPS sources, or yt-dlp.

SOURCE_MODE=yt_dlp uses yt-dlp's --download-sections instead of downloading
an entire 10+ hour source first. It can fail for live streams and restricted
playback, or consume more than 30 seconds of network data depending on formats.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlparse

VIDEO_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{11}$")

class MediaAccessError(RuntimeError):
    def __init__(self, reason:str):
        self.reason=reason
        super().__init__(reason)

def classify_media_error(stderr)->MediaAccessError:
    # Never include raw stderr or signed media URLs in reports.
    s=(stderr.decode("utf8","replace") if isinstance(stderr,bytes) else str(stderr or "")).casefold()
    if "sign in to confirm" in s or "not a bot" in s:return MediaAccessError("youtube_bot_check")
    if "private video" in s or "members-only" in s:return MediaAccessError("private_video")
    if "not available in your country" in s:return MediaAccessError("geo_restricted")
    if "403" in s or "forbidden" in s:return MediaAccessError("playback_forbidden")
    return MediaAccessError("playback_unavailable")



def find_media_source(video_id: str, media_dir: Path):
    """Use local file or configured direct HTTPS media URL if present."""
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        return None
    directory = media_dir.resolve()
    path = (directory / f"{video_id}.mp4").resolve()
    if path.is_relative_to(directory) and path.is_file():
        return str(path)
    try:
        mapping = json.loads(os.getenv("MEDIA_SOURCE_MAP_JSON", "{}"))
    except (json.JSONDecodeError, TypeError):
        return None
    url = mapping.get(video_id) if isinstance(mapping, dict) else None
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    # A normal YouTube watch URL is not a direct FFmpeg media input.
    if parsed.scheme != "https" or not parsed.hostname:
        return None
    if parsed.hostname.lower() in {"youtube.com", "www.youtube.com", "youtu.be", "m.youtube.com"}:
        return None
    return url


def clip_media(source: str, video_id: str, start: float, duration: float,
               output_dir: Path, fmt: str = "vertical") -> Path:
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError("Invalid source video ID")
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"{video_id}_{int(start)}_{int(duration)}.mp4"
    args = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", "-ss", str(max(0, start)),
            "-i", source, "-t", str(max(1, duration))]
    if fmt == "vertical":
        args += ["-vf", "scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,setsar=1"]
    args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-c:a", "aac", "-b:a", "128k",
             "-movflags", "+faststart", str(out)]
    # Signed media URLs can contain credentials; never print FFmpeg stderr.
    try:
        subprocess.run(args, check=True, timeout=900, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        raise classify_media_error(exc.stderr or exc.stdout) from exc
    except subprocess.TimeoutExpired as exc:
        raise MediaAccessError("media_processing_timeout") from exc
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError("FFmpeg produced no output")
    return out


def section_command(video_id: str, start: float, duration: float, template: Path) -> list[str]:
    """Build yt-dlp command without shell interpolation or full-video downloads."""
    if not VIDEO_ID_PATTERN.fullmatch(video_id):
        raise ValueError("Invalid source video ID")
    if start < 0 or not (0 < duration <= 180):
        raise ValueError("Invalid clip window")
    return [sys.executable, "-m", "yt_dlp", "--no-playlist", "--no-progress", "--no-warnings",
            "--download-sections", f"*{start:.3f}-{start+duration:.3f}",
            "--force-keyframes-at-cuts", "--merge-output-format", "mp4",
            "-f", "bv*+ba/b", "-o", str(template),
            f"https://www.youtube.com/watch?v={video_id}"]


def clip_youtube_section(video_id: str, start: float, duration: float,
                         output_dir: Path, fmt: str = "vertical") -> Path:
    """Fetch the selected time window only, then export a vertical 30s clip.

    Uses yt-dlp rather than the YouTube Data API (which does not supply media).
    Live streams without seekable DVR may fail. No continuous buffering.
    """
    with TemporaryDirectory(prefix="gta6-section-") as directory:
        tmp = Path(directory)
        cmd = section_command(video_id, start, duration, tmp / "segment.%(ext)s")
        try:
            subprocess.run(cmd, check=True, timeout=900, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise classify_media_error(exc.stderr or exc.stdout) from exc
        segments = [p for p in tmp.glob("segment.*") if p.suffix.lower() in {".mp4", ".mkv", ".webm"}]
        if not segments:
            raise RuntimeError("yt-dlp did not produce a playable segment")
        # Section was already cut, so reframe from timestamp 0 rather than
        # seeking the original 10-hour timeline a second time.
        rendered = clip_media(str(segments[0]), video_id, 0, duration, output_dir, fmt)
    target = output_dir / f"{video_id}_{int(start)}_{int(duration)}.mp4"
    if rendered != target:
        rendered.replace(target)
    return target

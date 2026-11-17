"""Typed config with safe defaults: never auto-publish by default."""
from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv

load_dotenv()


def csv_env(name: str, default: str = "") -> tuple[str, ...]:
    return tuple(v.strip() for v in os.getenv(name, default).split(",") if v.strip())


@dataclass(frozen=True)
class Settings:
    youtube_api_key: str = os.getenv("YOUTUBE_API_KEY", "")
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    oauth_token: str = os.getenv("YOUTUBE_OAUTH_TOKEN", "")
    instagram_user_id: str = os.getenv("IG_USER_ID", "")
    instagram_page_token: str = os.getenv("INSTAGRAM_PAGE_ACCESS_TOKEN", "")
    instagram_graph_version: str = os.getenv("INSTAGRAM_GRAPH_VERSION", "v26.0")
    instagram_auto_upload: bool = os.getenv("INSTAGRAM_AUTO_UPLOAD", "false").lower() == "true"
    max_instagram_reels_per_run: int = int(os.getenv("MAX_INSTAGRAM_REELS_PER_RUN", "3"))
    search_terms: tuple[str, ...] = csv_env("SEARCH_TERMS", "GTA 6 live,GTA VI gameplay,GTA 6 shorts")
    region_codes: tuple[str, ...] = csv_env("REGION_CODES", "US,IN,GB,JP,BR")
    min_subscribers: int = int(os.getenv("MIN_SUBSCRIBERS", "1000000"))
    min_long_seconds: int = int(os.getenv("MIN_LONG_SECONDS", "36000"))
    max_search_calls: int = int(os.getenv("MAX_SEARCH_CALLS_PER_RUN", "3"))
    max_videos: int = int(os.getenv("MAX_VIDEOS_PER_RUN", "8"))
    max_clips_per_video: int = int(os.getenv("MAX_CLIPS_PER_VIDEO", "9"))
    target_clips_per_video: int = int(os.getenv("TARGET_CLIPS_PER_VIDEO", "8"))
    min_support: int = int(os.getenv("MIN_SUPPORT", "2"))
    min_score: float = float(os.getenv("MIN_SCORE", "0.35"))
    max_gemini_evals: int = int(os.getenv("MAX_GEMINI_EVALUATIONS_PER_RUN", "2"))
    clip_lead: float = float(os.getenv("CLIP_LEAD_SECONDS", "20"))
    clip_after: float = float(os.getenv("CLIP_AFTER_SECONDS", "10"))
    live_chat_delay: float = float(os.getenv("LIVE_CHAT_DELAY_SECONDS", "0"))
    live_search_term: str = os.getenv("LIVE_SEARCH_TERM", "GTA 6 gameplay live")
    live_capture_enabled: bool = os.getenv("LIVE_CAPTURE_ENABLED", "true").lower() == "true"
    live_capture_seconds: int = int(os.getenv("LIVE_CAPTURE_SECONDS", "150"))
    max_live_captures: int = int(os.getenv("MAX_LIVE_CAPTURES_PER_RUN", "1"))
    live_clock_shift: float = float(os.getenv("LIVE_CLOCK_SHIFT_SECONDS", "0"))
    live_polls: int = int(os.getenv("LIVE_POLLS", "6"))
    live_poll_seconds: float = float(os.getenv("LIVE_POLL_SECONDS", "20"))
    free_models: tuple[str, ...] = csv_env(
        "FREE_MODEL_CANDIDATES", "gemini-2.5-flash-lite,gemini-2.5-flash,gemini-3-flash-preview"
    )
    source_mode: str = os.getenv("SOURCE_MODE", "yt_dlp")
    media_dir: Path = Path(os.getenv("MEDIA_DIR", "media"))
    auto_upload: bool = os.getenv("AUTO_UPLOAD", "false").lower() == "true"
    upload_privacy: str = os.getenv("UPLOAD_PRIVACY", "private")
    output_format: str = os.getenv("OUTPUT_FORMAT", "vertical")
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", "output"))
    state_path: Path = Path(os.getenv("STATE_PATH", "state/processed.json"))
    report_path: Path = Path(os.getenv("REPORT_PATH", "reports/latest.json"))
    max_api_comments: int = int(os.getenv("MAX_API_COMMENTS", "200"))

    def validate(self) -> None:
        if self.max_gemini_evals < 0 or self.max_gemini_evals > 30:
            raise ValueError("MAX_GEMINI_EVALUATIONS_PER_RUN must be 0..30")
        if self.max_search_calls > 4 or self.max_search_calls < 1:
            raise ValueError("MAX_SEARCH_CALLS_PER_RUN must be between 1 and 4 to protect daily quota")
        if self.source_mode not in {"yt_dlp", "provided"}:
            raise ValueError("SOURCE_MODE must be yt_dlp or provided")
        if self.output_format not in {"vertical", "source"}:
            raise ValueError("OUTPUT_FORMAT must be vertical or source")
        if self.clip_lead != 20 or self.clip_after != 10:
            raise ValueError("GTA 6 Shorts are fixed to 20s lead + 10s after = 30s")
        if not (8 <= self.target_clips_per_video <= self.max_clips_per_video <= 9):
            raise ValueError("TARGET_CLIPS_PER_VIDEO must be 8 or 9 and MAX_CLIPS_PER_VIDEO must be <=9")
        if not (30 <= self.live_capture_seconds <= 300):
            raise ValueError("LIVE_CAPTURE_SECONDS must be 30..300")
        if not (0 <= self.max_live_captures <= 2):
            raise ValueError("MAX_LIVE_CAPTURES_PER_RUN must be 0..2")
        if not self.live_search_term.strip():
            raise ValueError("LIVE_SEARCH_TERM must be specified")
        if self.live_polls < 1 or self.live_polls > 12:
            raise ValueError("LIVE_POLLS must be 1..12")
        if not self.search_terms:
            raise ValueError("SEARCH_TERMS must not be empty")
        if self.upload_privacy not in {"private", "unlisted", "public"}:
            raise ValueError("UPLOAD_PRIVACY must be private, unlisted or public")
        if self.auto_upload and not self.oauth_token:
            raise ValueError("AUTO_UPLOAD=true requires YOUTUBE_OAUTH_TOKEN")
        if not 0 <= self.max_instagram_reels_per_run <= 9:
            raise ValueError("MAX_INSTAGRAM_REELS_PER_RUN must be between 0 and 9")
        if self.instagram_auto_upload:
            if not self.instagram_page_token or not self.instagram_user_id:
                raise ValueError("INSTAGRAM_AUTO_UPLOAD=true requires IG_USER_ID and INSTAGRAM_PAGE_ACCESS_TOKEN")
            if not self.instagram_user_id.isdecimal():
                raise ValueError("IG_USER_ID must be numeric")
            if self.output_format != "vertical":
                raise ValueError("Instagram Reels output must be vertical")

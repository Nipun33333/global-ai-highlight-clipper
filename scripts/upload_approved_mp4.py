"""Upload a user-approved direct HTTPS MP4 as a private YouTube Short.

Manual GitHub Actions workflow only. This does not scrape YouTube or claim
that metadata proves actual GTA VI gameplay. The operator verifies footage.
The URL is stored in APPROVED_GTA6_MP4_URL, a GitHub Actions secret.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from app.media import MediaAccessError, clip_media
from app.state import load, mark, mark_platform, hour_has_attempt, reserve_hour, save
from app.uploader import upload


def direct_https_media_url(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        return False
    if parsed.hostname.casefold() in {
        "youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be",
        "drive.google.com", "www.drive.google.com",
    }:
        return False
    return parsed.path.casefold().endswith(".mp4")


def run() -> dict:
    url = os.getenv("APPROVED_GTA6_MP4_URL", "").strip()
    token = os.getenv("YOUTUBE_OAUTH_TOKEN", "").strip()
    title = os.getenv("APPROVED_UPLOAD_TITLE", "GTA VI gameplay #Shorts").strip()[:100]
    try:
        start = int(os.getenv("APPROVED_UPLOAD_START", "0"))
    except ValueError:
        start = -1

    report = {"created_at": datetime.now(timezone.utc).isoformat(),
              "status": "not_attempted", "privacy": "private"}
    if not direct_https_media_url(url):
        report["status"] = "missing_or_invalid_direct_mp4_url"
        return report
    if not token:
        report["status"] = "missing_youtube_oauth_token"
        return report
    if start < 0 or start > 86400:
        report["status"] = "invalid_start_seconds"
        return report

    # Do not write signed URLs or credentials into GitHub reports.
    source_id = hashlib.sha256(url.encode("utf8")).hexdigest()[:11]
    clip_id = f"approved:{source_id}:{start}"
    hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    state_path = Path(os.getenv("STATE_PATH", "state/processed.json"))
    state = load(state_path)
    if hour_has_attempt(state, "youtube", hour):
        report["status"] = "youtube_hourly_limit_already_used"
        return report

    try:
        clip = clip_media(url, source_id, float(start), 30.0, Path("output"), "vertical")
    except (MediaAccessError, OSError, RuntimeError, ValueError) as exc:
        report["status"] = "approved_media_not_playable"
        report["reason"] = exc.reason if isinstance(exc, MediaAccessError) else type(exc).__name__
        return report

    if not reserve_hour(state, "youtube", hour, clip_id):
        report["status"] = "youtube_hourly_limit_already_used"
        return report
    # Reserve BEFORE the network upload, including uncertain timeout results.
    save(state_path, state)
    report["attempted_hour"] = hour
    try:
        media_id = upload(
            clip, token, title or "GTA VI gameplay #Shorts",
            "Operator-approved gameplay clip. #GTA6 #GTAVI #Shorts",
            privacy="private",
        )
        mark_platform(state, clip_id, "youtube", media_id)
        mark(state, clip_id, "uploaded_private", media_id)
        report["status"] = "published_private"
        report["youtube_url"] = f"https://www.youtube.com/watch?v={media_id}"
    except Exception as exc:
        # Do not persist exception text containing tokens, URLs or raw API data.
        report["status"] = "youtube_upload_error"
        report["reason"] = type(exc).__name__
    finally:
        save(state_path, state)
    return report


def main() -> int:
    try:
        report = run()
    except Exception as exc:
        report = {"created_at": datetime.now(timezone.utc).isoformat(),
                  "status": "internal_error", "reason": type(exc).__name__}
    path = Path(os.getenv("APPROVED_UPLOAD_REPORT", "reports/approved_upload_latest.json"))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2), encoding="utf8")
    print("Private approved upload:", report["status"])
    if report.get("youtube_url"):
        print("Video:", report["youtube_url"])
    return 0  # Permit the workflow to persist the hour reservation first.


if __name__ == "__main__":
    raise SystemExit(main())

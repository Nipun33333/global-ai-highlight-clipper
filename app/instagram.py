"""Publish a local MP4 as an Instagram Reel using Meta's official Graph API.

Facebook Login for Business path: the Instagram professional account is
linked to a Facebook Page. A Page access token with instagram_content_publish
is required. Meta's resumable upload avoids public/paid video hosting.
"""
import re
import time
from pathlib import Path
from urllib.parse import urlparse

import requests


class InstagramPublishError(RuntimeError):
    """A Meta container/upload/publish request could not complete."""


def _json(response: requests.Response, stage: str) -> dict:
    if not (200 <= response.status_code < 300):
        # Never log a token, request body, or authenticated URL.
        raise InstagramPublishError(f"Instagram {stage}: HTTP {response.status_code}")
    try:
        data = response.json()
    except (ValueError, TypeError) as exc:
        raise InstagramPublishError(f"Instagram {stage}: non-JSON reply") from exc
    if not isinstance(data, dict) or data.get("error"):
        raise InstagramPublishError(f"Instagram {stage}: invalid API reply")
    return data


def publish_reel(
    path: Path, access_token: str, ig_user_id: str, caption: str,
    version: str = "v26.0", session: requests.Session | None = None,
    poll_attempts: int = 12, poll_wait_seconds: float = 5,
) -> str:
    """Publish one MP4 and return the Instagram Media ID.

    Upload: create resumable container -> stream local bytes -> poll FINISHED
    -> publish. Publishing cannot be dry-run with the real Meta API; the
    caller keeps INSTAGRAM_AUTO_UPLOAD=false until the account is configured.
    """
    path = Path(path)
    if path.suffix.lower() != ".mp4" or not path.is_file() or path.stat().st_size == 0:
        raise ValueError("Instagram publisher needs a nonempty local .mp4 file")
    if not access_token or not re.fullmatch(r"\d+", str(ig_user_id)):
        raise ValueError("Instagram Page access token and numeric IG_USER_ID are required")
    if not re.fullmatch(r"v\d+\.\d+", version):
        raise ValueError("Unexpected Instagram Graph API version")
    if poll_attempts < 1:
        raise ValueError("poll_attempts must be positive")

    http = session or requests.Session()
    graph = f"https://graph.facebook.com/{version}"
    auth = {"Authorization": f"Bearer {access_token}"}
    created = _json(http.post(
        f"{graph}/{ig_user_id}/media", headers=auth,
        data={"media_type": "REELS", "upload_type": "resumable",
              "caption": caption[:2200], "share_to_feed": "true"},
        timeout=(20, 60), allow_redirects=False,
    ), "create")
    cid = str(created.get("id", ""))
    if not re.fullmatch(r"\d+", cid):
        raise InstagramPublishError("Instagram create: container id missing")
    uri = created.get("uri") or f"https://rupload.facebook.com/ig-api-upload/{version}/{cid}"
    parsed = urlparse(uri)
    if parsed.scheme != "https" or parsed.hostname != "rupload.facebook.com":
        raise InstagramPublishError("Instagram create: unexpected upload host")

    size = path.stat().st_size
    with path.open("rb") as video:
        uploaded = _json(http.post(
            uri, headers={"Authorization": f"OAuth {access_token}", "offset": "0",
                          "file_size": str(size), "Content-Type": "application/octet-stream"},
            data=video, timeout=(20, 240), allow_redirects=False,
        ), "transfer")
    if uploaded.get("success") is False:
        raise InstagramPublishError("Instagram transfer: upload rejected")

    for attempt in range(poll_attempts):
        status = _json(http.get(
            f"{graph}/{cid}", headers=auth,
            params={"fields": "status_code,status"}, timeout=(20, 40),
            allow_redirects=False,
        ), "status")
        code = status.get("status_code")
        if code == "FINISHED":
            break
        if code in {"ERROR", "EXPIRED"}:
            raise InstagramPublishError(f"Instagram processing failed ({code})")
        if attempt + 1 < poll_attempts:
            time.sleep(poll_wait_seconds)
    else:
        raise InstagramPublishError("Instagram processing not ready before polling timeout")

    published = _json(http.post(
        f"{graph}/{ig_user_id}/media_publish", headers=auth,
        data={"creation_id": cid}, timeout=(20, 60), allow_redirects=False,
    ), "publish")
    media_id = str(published.get("id", ""))
    if not re.fullmatch(r"\d+", media_id):
        raise InstagramPublishError("Instagram publish: Media ID missing")
    return media_id

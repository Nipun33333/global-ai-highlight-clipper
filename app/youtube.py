"""YouTube Data API metadata search and timecoded chat/comments.

This module never retrieves audiovisual material; see app.live/app.media.
"""
from datetime import datetime, timezone
import re
import time
from typing import Any

from .gta6 import is_gta6_gameplay_video

import requests

BASE = "https://www.googleapis.com/youtube/v3"


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def duration_seconds(value: str | None) -> int:
    """Parse YouTube ISO8601 durations including 10+ hour videos."""
    match = re.fullmatch(r"P(?:(\d+)D)?(?:T(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?)?", value or "")
    if not match:
        return 0
    d, h, m, s = (int(g or 0) for g in match.groups())
    return d * 86400 + h * 3600 + m * 60 + s


class YouTubeData:
    def __init__(self, api_key: str):
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY missing")
        self.api_key = api_key
        self.session = requests.Session()

    def get(self, endpoint: str, **params: Any) -> dict:
        params["key"] = self.api_key
        for attempt in range(3):
            response = self.session.get(f"{BASE}/{endpoint}", params=params, timeout=30)
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                time.sleep(2 ** attempt)
                continue
            if not response.ok:
                raise RuntimeError(f"YouTube {endpoint}: HTTP {response.status_code}: {response.text[:350]}")
            return response.json()
        raise RuntimeError("YouTube API unavailable")

    def search(self, query: str, mode: str, region: str | None = None) -> list[dict]:
        # Use the API duration/event filters, not contradictory textual search terms.
        # Recent-first is helpful around a new game launch; result sets are not exhaustive.
        params = dict(part="snippet", type="video", q=query, maxResults=50, safeSearch="moderate")
        if mode == "live":
            params["eventType"] = "live"
            params["order"] = "date"
        elif mode in {"long", "short"}:
            params["videoDuration"] = mode  # long >20min; short <4min, refine exact duration below.
            params["order"] = "date"
        else:
            raise ValueError("Unexpected search mode")
        if region:
            params["regionCode"] = region
        return self.get("search", **params).get("items", [])

    def video_details(self, ids: list[str]) -> list[dict]:
        if not ids:
            return []
        results = []
        for offset in range(0, len(ids), 50):
            results.extend(self.get("videos", part="snippet,contentDetails,liveStreamingDetails",
                                    id=",".join(ids[offset:offset + 50])).get("items", []))
        return results

    def channel_subs(self, ids: list[str]) -> dict[str, int]:
        if not ids:
            return {}
        items = []
        for offset in range(0, len(ids), 50):
            items.extend(self.get("channels", part="statistics",
                                  id=",".join(ids[offset:offset + 50])).get("items", []))
        out = {}
        for item in items:
            stats = item.get("statistics", {})
            if not stats.get("hiddenSubscriberCount", False):
                out[item["id"]] = int(stats.get("subscriberCount", 0))
        return out

    def comments(self, video_id: str, max_comments: int = 200) -> list[dict]:
        items = []
        token = None
        while len(items) < max_comments:
            params = dict(part="snippet", videoId=video_id, order="relevance", maxResults=min(100, max_comments - len(items)), textFormat="plainText")
            if token:
                params["pageToken"] = token
            try:
                data = self.get("commentThreads", **params)
            except RuntimeError as exc:
                if any(t in str(exc) for t in ("commentsDisabled", "404", "403")):
                    return items
                raise
            for entry in data.get("items", []):
                top = entry.get("snippet", {}).get("topLevelComment", {})
                snip = top.get("snippet", {})
                items.append({"id": top.get("id"), "text": snip.get("textDisplay", ""), "likeCount": snip.get("likeCount", 0)})
            token = data.get("nextPageToken")
            if not token:
                break
        return items

    def live_chat(self, chat_id: str, start_time: datetime, polls: int = 3, poll_seconds: float = 20, delay_seconds: float = 0) -> list[dict]:
        """Small bounded sampling window per scheduled job, not continuous monitoring."""
        messages: dict[str, dict] = {}
        token = None
        for i in range(polls):
            params = dict(liveChatId=chat_id, part="snippet", maxResults=200)
            if token:
                params["pageToken"] = token
            data = self.get("liveChat/messages", **params)
            for entry in data.get("items", []):
                snip = entry.get("snippet", {})
                at = parse_time(snip.get("publishedAt"))
                if not at or not entry.get("id"):
                    continue
                seconds = max(0, (at - start_time).total_seconds() - delay_seconds)
                messages[entry["id"]] = {"id": entry["id"], "text": snip.get("displayMessage", ""), "seconds": seconds}
            token = data.get("nextPageToken")
            if i + 1 < polls:
                # Official polling interval should be respected even if configured lower.
                time.sleep(max(poll_seconds, data.get("pollingIntervalMillis", 0) / 1000))
        return list(messages.values())


def clean_search_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    """The API handles live/long/short filters: don't put conflicting words in q."""
    result: list[str] = []
    for value in terms:
        stripped = re.sub(r"\b(?:live|long|shorts?)\b", " ", value, flags=re.IGNORECASE)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if stripped and stripped not in result:
            result.append(stripped)
    return tuple(result) or ("GTA 6 gameplay", "GTA VI gameplay")


def discover(yt: YouTubeData, terms: tuple[str, ...], regions: tuple[str, ...], min_subs: int,
             min_long_seconds: int, max_calls: int = 3,
             live_search_term: str = "GTA 6 gameplay",
             diagnostics: dict | None = None) -> list[dict]:
    """Always search live first, then long (10h+) and Shorts.

    Each call searches at most 50 results. With three calls per hour we stay
    within the intended search budget; neither search nor title metadata can
    prove a genuine game is being played.
    """
    stats = diagnostics if diagnostics is not None else {}
    stats.update(search_calls=0, search_items=0, unique_ids=0,
                 rejected_topic_or_gameplay=0, rejected_subscribers=0,
                 rejected_duration=0, rejected_live_state=0, selected=0)
    hour = int(datetime.now(timezone.utc).timestamp() // 3600)
    queries = clean_search_terms(terms)
    matches: dict[str, dict] = {}
    search_modes = ("live", "long", "short")
    for index in range(max_calls):
        mode = search_modes[index % len(search_modes)]
        if mode == "live":
            query = re.sub(r"\b(?:live|shorts?|long)\b", " ", live_search_term, flags=re.I).strip() or "GTA 6 gameplay"
        else:
            query = queries[(hour + (index - 1)) % len(queries)]
        # Global unlocalized search for lives. Rotate other regions each hour.
        region = (regions[(hour + index) % len(regions)] if regions else None) if index else None
        found = yt.search(query, mode=mode, region=region)
        stats["search_calls"] += 1
        stats["search_items"] += len(found)
        for result in found:
            video_id = result.get("id", {}).get("videoId")
            if video_id:
                matches[video_id] = result
    stats["unique_ids"] = len(matches)
    if not matches:
        return []
    videos = yt.video_details(list(matches))
    channel_ids = sorted({
        video.get("snippet", {}).get("channelId", "")
        for video in videos if video.get("snippet", {}).get("channelId")
    })
    subs = yt.channel_subs(channel_ids)
    selected = []
    for video in videos:
        snip = video.get("snippet", {})
        if not is_gta6_gameplay_video(
            snip.get("title", ""), snip.get("description", ""), snip.get("tags", [])
        ):
            stats["rejected_topic_or_gameplay"] += 1
            continue
        channel_id = snip.get("channelId", "")
        count = subs.get(channel_id, 0)
        if count < min_subs:
            stats["rejected_subscribers"] += 1
            continue
        duration = duration_seconds(video.get("contentDetails", {}).get("duration"))
        details = video.get("liveStreamingDetails", {})
        is_live = snip.get("liveBroadcastContent") == "live"
        is_short = bool(duration and duration <= 180 and not is_live)
        if is_live and not details.get("actualStartTime"):
            stats["rejected_live_state"] += 1
            continue
        if not is_live and not is_short and duration < min_long_seconds:
            stats["rejected_duration"] += 1
            continue
        selected.append({
            "id": video["id"], "title": snip.get("title", ""),
            "description": snip.get("description", "")[:1200],
            "tags": snip.get("tags", [])[:30],
            "channel_id": channel_id, "channel_title": snip.get("channelTitle", ""),
            "subscribers": count, "duration": duration, "is_live": is_live,
            "is_short": is_short, "chat_id": details.get("activeLiveChatId"),
            "actual_start": details.get("actualStartTime")
        })
    stats["selected"] = len(selected)
    return sorted(selected, key=lambda v: (not v["is_live"], -v["subscribers"]))

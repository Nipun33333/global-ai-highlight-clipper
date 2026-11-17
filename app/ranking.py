"""Turn time-coded comments or timestamped live chat into highlight candidates."""
import re
from collections import defaultdict

# Strict, Unicode-friendly; do not confuse digits in surrounding text with timecodes.
TIMECODE_RE = re.compile(r"(?<![\d:])(?:\d{1,3}:)?\d{1,2}:\d{2}(?![\d:])")
GOOD_WORDS = (
    "amazing", "best", "insane", "crazy", "legend", "epic", "hype", "wow", "goat",
    "clutch", "nice", "fire", "incredible", "op", "damn", "funny", "hilarious",
    "mast", "gazab", "bahut badhiya", "kya baat", "शानदार", "कमाल", "मस्त", "गजब",
    "😂", "🤣", "🔥", "❤️", "😍", "👏", "😱", "🤯", "💀", "🙌", "🥳", "🚀",
)
BAD_WORDS = ("boring", "dislike", "worst", "hate", "terrible", "disappointing", "fake", "scam")


def extract_timecodes(text: str, max_seconds: float | None = None) -> list[int]:
    results = []
    for m in TIMECODE_RE.finditer(text):
        parts = [int(x) for x in m.group().split(":")]
        if parts[-1] >= 60 or (len(parts) == 3 and parts[-2] >= 60):
            continue
        seconds = parts[-1] + 60 * parts[-2] + (3600 * parts[0] if len(parts) == 3 else 0)
        if max_seconds is None or seconds <= max_seconds:
            results.append(seconds)
    return list(dict.fromkeys(results))


def comment_positive(text: str) -> bool:
    s = text.casefold()
    good = any(word in s for word in GOOD_WORDS) or s.count("!") >= 2
    bad = any(word in s for word in BAD_WORDS)
    return good and not (bad and not any(x in s for x in ("😂", "🤣", "🔥")))


def build_candidates(messages: list[dict], *, is_live: bool, duration: int, bin_size: int = 30, min_support: int = 2) -> list[dict]:
    """For VOD, ONLY explicit textual timecodes identify a scene.
    For live, chat publishedAt is mapped approximately relative to broadcast start.
    """
    bins: dict[int, list[dict]] = defaultdict(list)
    for entry in messages:
        text = entry.get("text", "")
        if not comment_positive(text):
            continue
        if is_live:
            moments = [entry["seconds"]] if isinstance(entry.get("seconds"), (int, float)) else []
        else:
            moments = extract_timecodes(text, max_seconds=duration)
        for moment in moments:
            if moment < 0:
                continue
            center = int(moment // bin_size) * bin_size + bin_size // 2
            bins[center].append(entry)
    candidates = []
    for center, votes in bins.items():
        unique = list({str(x.get("id") or i): x for i, x in enumerate(votes)}.values())
        if len(unique) < min_support:
            continue
        # Engagement size and likes are positive but bounded; Gemini will re-rank.
        like_boost = min(1, sum(int(x.get("likeCount", 0)) for x in unique) / 100)
        score = min(1., 0.2 + len(unique) / 12 + like_boost * 0.1)
        candidates.append({"timestamp": center, "support": len(unique), "heuristic_score": round(score, 3),
                           "sample_comments": [x.get("text", "")[:300] for x in unique[:12]]})
    return sorted(candidates, key=lambda c: (-c["heuristic_score"], -c["support"], c["timestamp"]))


def non_overlapping(candidates: list[dict], limit: int, lead: float, after: float, min_score: float, duration: float = 0) -> list[dict]:
    """Select non-overlapping windows; when duration is known keep ~30s inside it."""
    chosen = []
    for item in sorted(candidates, key=lambda c: -c.get("score", c["heuristic_score"])):
        if item.get("score", item["heuristic_score"]) < min_score:
            continue
        length = lead + after
        start = max(0., item["timestamp"] - lead)
        if duration > 0:
            # Near the end of a recording, shift backward to keep the full 30s.
            start = min(start, max(0., duration - length))
        end = start + length
        if duration > 0:
            end = min(end, duration)  # A Short shorter than 30s remains short.
        if end <= start:
            continue
        if any(start < other["end"] and end > other["start"] for other in chosen):
            continue
        chosen.append({**item, "start": start, "end": end})
        if len(chosen) >= limit:
            break
    return chosen

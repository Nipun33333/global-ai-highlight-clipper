"""Non-configurable GTA 6-only topic gate for video discovery and publishing.

A title match is required; a generic gaming tag or description does not qualify.
This checks metadata, not whether the video actually contains GTA 6 footage.
"""
import re

GTA6_TITLE_RE = re.compile(
    r"(?<![\w])(?:gta\s*[-:]?\s*(?:6|vi)|grand\s+theft\s+auto\s*[-:]?\s*(?:6|vi|six))(?![\w])",
    re.IGNORECASE,
)


def is_gta6_video(title: str) -> bool:
    """True for explicit GTA 6 / GTA VI / Grand Theft Auto VI in the title."""
    return bool(GTA6_TITLE_RE.search(title or ""))

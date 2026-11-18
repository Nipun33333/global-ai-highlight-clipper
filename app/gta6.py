"""Conservative GTA VI gameplay candidate detection using public metadata.

This code checks claims, not pixels: it cannot certify that any stream contains
authentic gameplay. Trailers, countdowns, news, reactions, leaks and mods are
excluded even when their descriptions include SEO gameplay keywords.
"""
import re

TOPIC = re.compile(
    r"(?<![\w])(?:gta\s*[-:]?\s*(?:6|vi)|grand\s+theft\s+auto\s*[-:]?\s*(?:6|vi|six))(?![\w])",
    re.IGNORECASE,
)
PLAY = re.compile(
    r"\bgame[\s-]?play\b|\bplay[\s-]?through\b|\bwalk[\s-]?through\b|"
    r"\blet['’]?s\s*play\b|\bplaying\b|\bin[\s-]?game\b|"
    r"\bjugando\b|\bpartida\b|\bjogando\b|ゲームプレイ|ゲーム実況|गेमप्ले",
    re.IGNORECASE,
)
NOT = re.compile(
    r"\bcount[\s-]?down\b|\brelease[\s-]?date\b|\blaunch\s*(?:date|time)\b|"
    r"\btrailer\b|\bteaser\b|\bnews\b|\bleak(?:ed|s)?\b|"
    r"\brumou?r\b|\bprediction\b|\bconcept\b|\bfan[\s-]?made\b|"
    r"\bmods?\b|\bmodded\b|\breact(?:ion|s|ing)?\b|\breview\b|\bexplained\b|"
    r"\bvs\.?\s*real\s*life\b|\bfirst\s+to\s+buy\b|"
    r"\bgta\s*[-:]?\s*5\b|\bgta\s*[-:]?\s*v(?!i)\b",
    re.IGNORECASE,
)
# Avoid earlier GTA Online coverage and date/timed launch livestreams.
OTHER_GAME = re.compile(
    r"\bgta\s*[-:]?\s*(?:online|5|v(?!i))\b|\bgrand\s+theft\s+auto\s+(?:online|v(?!i)|5)\b|"
    r"\bfive[\s-]?m\b|\brole[\s-]?play(?:ing)?\b|\bgta\s*rp\b",
    re.IGNORECASE,
)
LAUNCH_SCHEDULE = re.compile(
    r"\b(?:nov(?:ember)?|launch|release|pre[\s-]?release|before|until|"
    r"tomorrow|midnight|12\s*a\.?m\.?|2026[\s/-]11[\s/-]19|"
    r"time\s*zones?|early\s*access)\b",
    re.IGNORECASE,
)

LIVE_TITLE = re.compile(
    r"\blive\b|\bstream(?:ing)?\b|\ben\s+vivo\b|\bao\s+vivo\b|\bepisode\b",
    re.IGNORECASE,
)


def is_gta6_video(title: str) -> bool:
    """GTA VI mention in title; not evidence of gameplay."""
    return bool(TOPIC.search(title or ""))


def is_gta6_gameplay_video(
    title: str, description: str = "", tags: list[str] | tuple[str, ...] | None = None
) -> bool:
    """Find explicitly gameplay-labelled GTA VI candidates, rejecting lookalikes.

    Strong signal: gameplay/playthrough named in title. Secondary signal:
    live/stream/episode title with clear gameplay in description or tags.
    Descriptions alone can't qualify generic news/trailer titles.
    """
    title = title or ""
    if not is_gta6_video(title) or NOT.search(title):
        return False
    if OTHER_GAME.search(title) or LAUNCH_SCHEDULE.search(title):
        return False
    if PLAY.search(title):
        return True
    if not LIVE_TITLE.search(title):
        return False
    supplementary = " ".join([str(description or "")[:1200], *(str(tag) for tag in (tags or ())[:30])])
    return bool(PLAY.search(supplementary))

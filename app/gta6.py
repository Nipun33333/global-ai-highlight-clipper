"""Conservative title-only GTA VI gameplay gate (not footage verification)."""
import re
TOPIC=re.compile(r"(?<![\w])(?:gta\s*[-:]?\s*(?:6|vi)|grand\s+theft\s+auto\s*[-:]?\s*(?:6|vi|six))(?![\w])",re.I)
PLAY=re.compile(r"\bgame[\s-]?play\b|\bplay[\s-]?through\b|\bwalk[\s-]?through\b|\blet['’]?s\s*play\b|\bplaying\b|\bin[\s-]?game\b|\bjugando\b|\bpartida\b|\bjogando\b|ゲームプレイ|ゲーム実況|गेमप्ले",re.I)
NOT=re.compile(r"\bcount[\s-]?down\b|\brelease[\s-]?date\b|\blaunch\s*(?:date|time)\b|\btrailer\b|\bteaser\b|\bnews\b|\bleak(?:ed|s)?\b|\brumou?r\b|\bprediction\b|\bconcept\b|\bfan[\s-]?made\b|\bmods?\b|\bmodded\b|\breact(?:ion|s|ing)?\b|\breview\b|\bexplained\b|\bvs\.?\s*real\s*life\b|\bfirst\s+to\s+buy\b|\bgta\s*[-:]?\s*5\b|\bgta\s*[-:]?\s*v(?!i)\b",re.I)
def is_gta6_video(title:str)->bool:
    return bool(TOPIC.search(title or ""))
def is_gta6_gameplay_video(title:str)->bool:
    title=title or ""
    return bool(TOPIC.search(title) and PLAY.search(title) and not NOT.search(title))

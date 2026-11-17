"""GitHub Actions summary: a green scan does not mean video was published."""
import os,json
from pathlib import Path
try: r=json.loads(Path(os.getenv("REPORT_PATH","reports/latest.json")).read_text(encoding="utf8"))
except (OSError,ValueError):r={"status":"report_missing","stats":{}}
s=r.get("stats",{})
lines=["## GTA 6 gameplay scan",f"**Outcome:** {r.get('status','unknown')}","","| Metric | Count |","|---|---:|"]
for k in ("discovered","live_found","live_analyzed","analyzed","gemini_fallbacks","clipped","media_restricted","uploaded","instagram_uploaded"):
    lines.append(f"| {k} | {s.get(k,0)} |")
lines.append("\nA successful scanner run does **not** mean a clip was published.")
if s.get("media_restricted"):lines.append("⚠️ YouTube playback blocked on this runner. Provide approved MP4 or direct HTTPS media; YouTube Data API does not provide media bytes.")
if s.get("gemini_fallbacks"):lines.append("⚠️ Gemini unavailable for some highlights; local heuristic used. No paid models were selected.")
if not s.get("clipped"):lines.append("⚠️ **Zero clips generated.**")
message="\n".join(lines)+"\n"
if os.getenv("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"],"a",encoding="utf8") as f:f.write(message)
print(message)

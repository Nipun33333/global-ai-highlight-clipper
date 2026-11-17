"""Offline proof of concept with time-coded comments; no credentials needed."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.ranking import build_candidates, non_overlapping
from app.gemini import GeminiRouter

messages = json.loads(Path("examples/sample_comments.json").read_text(encoding="utf8"))
candidates = build_candidates(messages, is_live=False, duration=39000, min_support=2)
results = [GeminiRouter("", ()).evaluate(candidate) for candidate in candidates]
print(json.dumps(non_overlapping(results, 3, lead=20, after=10, min_score=0.35), indent=2, ensure_ascii=False))
print("\nOffline demo only: no downloading, clipping, YouTube publishing, or Gemini API calls.")

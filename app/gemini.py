"""Free-tier *allowlist* router; availability != price/free-tier eligibility.

ListModels only proves API access, NOT whether model is free. Therefore only
operator-reviewed model IDs from FREE_MODEL_CANDIDATES will ever be tried.
When all candidates fail, use conservative local heuristic (no paid fallback).
"""
import json
import logging
import re
import time
from typing import Any

import requests

LOG = logging.getLogger(__name__)
BASE = "https://generativelanguage.googleapis.com/v1beta"


def safe_label(text: str, fallback: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()[:90]
    return text or fallback


class GeminiRouter:
    def __init__(self, api_key: str, model_ids: tuple[str, ...]):
        self.api_key = api_key
        # Don't use arbitrary autodiscovered models: listModels has no free-tier flag.
        self.model_ids = tuple(dict.fromkeys(m.removeprefix("models/") for m in model_ids if m.startswith("gemini-") or m.startswith("models/gemini-")))
        self.session = requests.Session()
        self._discovered: list[str] | None = None
        self._disabled_models: set[str] = set()
        self.fallback_count = 0

    def available_models(self) -> list[str]:
        if self._discovered is not None:
            return self._discovered
        if not self.api_key:
            return []
        try:
            supported = set()
            token = None
            for _ in range(5):
                params = {"pageSize": 1000}
                if token:
                    params["pageToken"] = token
                r = self.session.get(f"{BASE}/models", headers={"x-goog-api-key": self.api_key}, params=params, timeout=20)
                r.raise_for_status()
                doc = r.json()
                supported.update(m["name"].removeprefix("models/") for m in doc.get("models", [])
                                 if "generateContent" in m.get("supportedGenerationMethods", []))
                token = doc.get("nextPageToken")
                if not token:
                    break
            self._discovered = [model for model in self.model_ids if model in supported]
            return self._discovered
        except (requests.RequestException, KeyError, ValueError) as exc:
            LOG.warning("Gemini model listing failed: %s; using configured allowlist", exc)
            self._discovered = list(self.model_ids)
            return self._discovered

    def evaluate(self, candidate: dict) -> dict:
        backup = {**candidate, "score": candidate["heuristic_score"], "label": "Audience reaction highlight", "model_used": "local-heuristic"}
        if not self.api_key:
            self.fallback_count += 1
            return backup
        prompt = (
            "You are evaluating YouTube comments/live chat ONLY, not watching any video. "
            "Do not invent what occurs on screen. Assess whether reactions indicate an exciting/funny/positive moment. "
            "Return ONLY JSON with score 0.0..1.0 and label <= 60 characters; "
            "label must describe the *reaction*, not imagined gameplay. "
            "Prefer clearly positive/hype comments, penalize spam and ambiguity. "
            f"Candidate: {json.dumps({'timestamp': candidate['timestamp'], 'support': candidate['support'], 'comments': candidate['sample_comments']}, ensure_ascii=False)}"
        )
        for model in self.available_models():
            if model in self._disabled_models:
                continue
            payload = {"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json", "maxOutputTokens": 1024}}
            try:
                r = self.session.post(f"{BASE}/models/{model}:generateContent",
                                      headers={"x-goog-api-key": self.api_key, "Content-Type": "application/json"},
                                      json=payload, timeout=35)
                if r.status_code in {429, 404, 403, 500, 502, 503, 504}:
                    if r.status_code in {403, 404}: self._disabled_models.add(model)
                    LOG.warning("Model %s unavailable (HTTP %s), trying next free-tier candidate", model, r.status_code)
                    continue
                r.raise_for_status()
                response = r.json()
                first = response.get("candidates", [{}])[0]
                parts = first.get("content", {}).get("parts", [])
                raw = "".join(p.get("text", "") for p in parts).strip()
                if not raw: raise ValueError("Empty JSON; finishReason="+str(first.get("finishReason", "unknown")))
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I).strip()
                obj: dict[str, Any] = json.loads(raw)
                score = max(0., min(1., float(obj["score"])))
                return {**candidate, "score": round(score, 3),
                        "label": safe_label(str(obj.get("label", "")), "Audience reaction highlight"), "model_used": model}
            except (ValueError, KeyError, IndexError, TypeError, requests.RequestException) as exc:
                LOG.warning("Gemini model %s error: %s", model, str(exc)[:130])
                continue
        self.fallback_count += 1
        return backup
